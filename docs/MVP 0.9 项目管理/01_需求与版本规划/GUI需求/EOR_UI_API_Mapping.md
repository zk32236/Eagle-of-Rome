# EOR UI-API 映射文档

> 版本: v2.0（2026-07-05）
> 基线设计: `EOR_GUI设计文档.md` V2.0
> 最新原型: `EOR_GUI_Prototype_v3.23.html`
> 作用: GUI 开发的数据契约 — 明确每个 UI 元素从哪个 API 获取数据、触发什么操作
> 适用对象: CODEX（GUI 开发）

---

## 通用框架（所有阶段共享）

### 顶部全局信息栏

```
💰 142 T 国库 │ 👛 12 T 派系金库 │ ⚖️ 68 影响力 │ 🏛️ 78% 稳定度 │ ⚔️ 2 战争 │ ⚓ 3 舰队
```

| 字段 | API 路径 | 代码来源 |
|------|---------|---------|
| 国库 | `get_session_snapshot().data.public_resources.treasury` | `state.treasury` |
| 派系金库 | `get_session_snapshot().data.faction_resources.treasury` | `faction.treasury` |
| 影响力 | `get_session_snapshot().data.faction_resources.total_influence` | `sum(m.influence)` |
| 稳定度 | 暂无 → 建议新增 `game_api.get_stability()` 或 state 新增字段 | `state.stability` |
| 战争数 | `get_session_snapshot()` 建议新增 | `len(war_system.get_active_wars())` |
| 舰队数 | 暂从 `state.naval_system.get_active_fleet_count()` | naval_system |
| 存活人数 | `get_session_snapshot().data.public_resources.living_members` | `len(state.get_living_members())` |
| 回合/年份 | `get_session_snapshot().data.public_resources.{turn_number, year_display}` | `state.turn` |

### 左侧阶段导航栏（7 步竖排圆钮）

数据来源: `get_session_snapshot().data.phase_navigation[]`

```
phase_navigation: [{
  id: "mortality" | "revenue" | "forum" | "population" | "senate" | "combat" | "resolution"
  index: int          # 0-6
  name: str           # 本地化名称
  status: "current" | "done" | "todo"
  actionable: bool    # 当前阶段 + 当前玩家 + 已实现
  locked_reason: str  # 占位提示（未实现阶段）
}, ...]
```

### 中央面板（各阶段独立内容）

- 根据 `current_phase_id` 切换显示对应的 `phase-content`
- 每个阶段包含：*阶段标签 → 标题 → 阶段步骤指示器 → 公示区 → 子环节面板区*

### 右侧上下文面板

| 区域 | 数据来源 |
|------|---------|
| 🎯 当前阶段目标 | `_build_phase_summary(current_phase_id).description`（本地化） |
| ⚡ 操作按钮 | 「推进到下一阶段」→ `game_api.execute_phase(next_phase)` |
| 📋 进度 | `phase_navigation[current].status` + `STEPS[i]` |
| 👤 玩家信息 | `get_session_snapshot().data.{current_player_id, viewer_faction_id, my_figures}` |
| 📢 事件日志 | 纯客户端 JS → `addLog(type, message)`，无服务端持久化 |

### 底部查询操作栏（12 个全局按钮）

| 按钮 | 建议 API / 数据来源 |
|------|-------------------|
| 📋 派系信息 | `get_session_snapshot().data.faction_resources` + 遍历 factions |
| 👤 人物查询 | `get_session_snapshot().data.my_figures[]` + 弹窗展示详情 |
| 📊 游戏状态 | `game_api.get_status_summary()` |
| 💰 派系金库 | `faction.treasury`（仅本派系可见） |
| 🌾 公地信息 | `game_api.get_public_land_info()` |
| 🏡 私地信息 | 遍历 `state.figures` 的私有土地（仅本派系可见） |
| 📦 合同状态 | 待新增 `contract_api.get_all_contracts()` |
| 🏛️ 行省信息 | `province_api.get_provinces()` |
| ⚔️ 战争列表 | `war_system.get_active_wars()` + `war_system.get_resolved_wars()` |
| 🗡️ 军团状态 | `military_system.get_all_legions()` |
| ⚓ 舰队状态 | `naval_system.get_all_fleets()` |
| ❓ 帮助 | 静态文本，无需 API |

---

## 阶段 1: 天命 (Mortality)

### 数据契约

```
get_mortality_view(state, viewer_player_id):
  phase_id: "mortality"
  executed: bool
  is_current_player: bool
  can_execute: bool      # 未执行 + 当前玩家
  can_advance: bool      # 已执行 + 当前玩家
  events: [{              # 事件列表
    type: str             # "death" / "talent" / "disaster" / "peace" / "abundance"
    description: str
    actor: str (optional) # 死者/人才名称
  }]
  result: dict (optional) # execute_mortality_phase 执行后返回
```

### 操作映射

| UI 元素 / 用户操作 | 触发 API | 成功 → | 失败 → |
|---|---|---|---|
| 「⚡ 执行天命」按钮 | `mortality_api.execute_mortality_phase(state, player_id)` | 灰化按钮，显示事件结果 | Toast "执行失败" |
| 事件结果展示区 | `get_mortality_view().data.result.events` | 渲染死/生/灾列表 | 空状态"众神沉默" |
| 「进入收入」按钮 | `mortality_api.advance_mortality_phase(state, player_id)` | 切换到收入阶段 | Toast "条件不足" |

### 多玩家角色

- **操作者：** 任意一名玩家点击即可，结果全局共享
- **AI 模式：** 自动执行，无需 UI

---

## 阶段 2: 收入 (Revenue)

### 数据契约

已实现为独立 `revenue_api.py`（2026-07-12 Phase 2 交付）：

```python
# src/api/revenue_api.py

def get_revenue_view(state, viewer_player_id) -> dict:
    """收入阶段只读状态（是否可执行/已结算/可否推进）。"""

def execute_revenue_phase(state, viewer_player_id) -> dict:
    """执行收入结算：调用 EconomicService.settle_revenue_phase()。"""

def advance_revenue_phase(state, viewer_player_id) -> dict:
    """推进到广场阶段（mark_phase_executed("revenue") → next: forum）。"""
```

`EconomicService.settle_revenue_phase()` 完整返回结构：

```
{
  "success": bool,
  "data": {
    "starting_treasury": int,
    "ending_treasury": int,
    "treasury_delta": int,
    "indemnities": [{"name": str, "amount": int, "direction": "income"|"expense"}],
    "national_opex": {"provinces": [...], "total": int},
    "public_land_income": int,
    "private_land_rows": [{"figure_id": int, "name": str, "income": int, "wealth": int}],  # ← Dict 格式
    "contract_rows": [...],
    "warranty_rows": [...],
    "maintenance": {"military": {...}, "naval": {...}},
    "faction_rows": [...],
    "debug_events": []
  }
}
```

### 数据流（实际实现）

```
QML RevenueStage.qml
  ↓ 通过 sessionStore.revenueSettledData / revenueView
session_store.py (Property: revenueResult, revenueView, canExecuteRevenue, canAdvanceRevenue)
  ↓ _adapter.settle_revenue() / _adapter.get_revenue_view()
api_adapter.py (settle_revenue / get_revenue_view / advance_revenue)
  ↓
revenue_api.py (execute_revenue_phase / get_revenue_view / advance_revenue_phase)
  ↓
EconomicService.settle_revenue_phase()
```

### 操作映射

| UI 元素 | 触发 API | 说明 |
|---------|---------|------|
| 国家收入/支出（左右并排） | `sessionStore.revenueSettledData` → `private_land_rows` / `national_opex` / `indemnities` | 收入左/支出右 |
| 派系财政列表 | `sessionStore.revenueSettledData.faction_rows[]` | 各派系可见本派系金库 |
| 地主收入列表 | `sessionStore.revenueSettledData.private_land_rows[]` | Dict 格式，`modelData.name` 访问 |
| 净变化 + 新余额 | `sessionStore.revenueSettledData.treasury_delta` + `ending_treasury` | 底部金色框 |
| 「确认收入结算」按钮 | `sessionStore.doExecuteRevenue()` → `api_adapter.settle_revenue()` → `revenue_api.execute_revenue_phase()` | 按钮在 StageActionSlot（中央桌面底部） |
| 「推进到广场」按钮 | `sessionStore.doAdvanceRevenue()` → `api_adapter.advance_revenue()` → `revenue_api.advance_revenue_phase()` | 按钮在 ContextPanel.OperationSection（右侧面板） |

### 多玩家角色

- **操作者：** 任意一名玩家确认即可
- **AI 模式：** 自动结算
- 派系金库数据仅本派系可见

### `private_land_rows` 数据格式（v1.1）

2026-07-12 从 `List[Tuple[int, str, int, int]]` 变更为 `List[Dict]`（键名访问）。

**变更原因：** PySide6 QML Repeater 无法可靠索引元组，`modelData[1]` 返回 `undefined`。改为 Dict 后使用 `modelData.name` / `modelData.income` 访问。

---

## 阶段 3: 广场 (Forum) — 多玩家轮流

### 数据契约

建议新增 `get_forum_view()`：

```
get_forum_view(state, viewer_player_id):
  current_player_id: str
  current_step: "announce" | "retirement" | "market" | "resolution"
  my_figures: [{id, name, faction, influence, ...}]
  available_figures: [{id, name, martial, intellect, charisma, zeal, class_tier, cost,
                      is_hero, hero_type}]   # WP-F 021：is_hero/hero_type 由 Figure 实体持久字段透出（非瞬态）
  pending_contracts: [{id, name, type, base_cost, ...}]
  land_sale_quota: int
  triumph_wars: [{war_id, commander_name, commander_faction_id, ...}]  # WP-F 003：凯旋行补 commander_faction_id
```

### 操作映射

| UI 元素 | 触发 API | 参数要求 |
|---------|---------|---------|
| 本派系成员列表 | `my_figures` | figure_id: int |
| 「解雇」按钮 | `forum_api.retire_figure(state, player_id, figure_id)` | figure_id: int |
| 人才市场表格 | `available_figures` | 属性用纯数字；姓名格 = 姓名 + 🌟（hero 时，星在名后，严格 `is_hero === true`），长名 ElideRight 截断（WP-F 021/F-POST-R1-03） |
| 「招募」按钮 → 弹窗 | `forum_api.recruit_figure(state, player_id, figure_id, amount)` | amount: int |
| 合同列表 | `pending_contracts` | — |
| 「竞标」按钮 → 弹窗 | `forum_api.place_bid(state, player_id, figure_id, contract_id, amount, profit_rate)` | profit_rate: 0~1 float |
| 公地认购 → 弹窗 | `forum_api.buy_land(state, player_id, figure_id, amount)` | amount ≤ quota |
| 「赞成/否决」凯旋 | `forum_api.vote_triumph(state, player_id, war_id, vote)` | vote: bool |
| 公示结算 | `forum_api.resolve_forum(state)` | 自动在全部操作后调用 |
| 「⏭️ 完成操作」→ 下一位 | `player_api.next_player(state, player_id)` | 切换玩家 |
| AI 自动操作 | `Auto*Decider` 系列 | 人类完成后台执行 |

### 多玩家角色

```
子环节1（解雇）: 人类轮流 → AI 后台 → 全部完成 → 解锁子环节2
子环节2（市场）: 人类轮流 → AI 后台 → 全部完成 → resolve_forum → 公示
```

### faction_style_map 消费链（WP-F 003 键名纠正）

```text
config faction_style_map 键 = 权威 faction_id 全名：optimates / populares / equites（+ 占位 f4/f5/f6）
  → faction_api.get_faction_style_map()（零改动，迭代 state.factions）
  → Store factionStyleMap（纯透传）
  → FactionStyle.qml factionColor/Name/Short
  → GUI 消费者（Senate/Forum/Combat/Revenue/Population/Resolution/Mortality/GovernorAppointmentPanel）
未知/无派系 → 中性 fallback #3A3530（禁随机色）
```

---

## 阶段 4: 人口 (Population) — 多玩家轮流

### 数据契约

```
get_population_view(state, viewer_player_id):
  current_player_id: str
  current_step: "announce" | "campaign" | "vote" | "resolution"
  offices: {
    "consul": [{figure_id, name, faction, martial, intellect, charisma, zeal, influence, wealth}],
    "censor": [...],
    "praetor": [...],
    "quaestor": [...],
    "tribune": [...]
  }
  my_candidates: [{figure_id, name, office, wealth}]  # 本派系候选人
  faction_influence: {faction_id: influence_before}
```

### 操作映射

| UI 元素 | 触发 API | 说明 |
|---------|---------|------|
| 候选人表格（9列） | `offices[]` | flex 对齐，不适用 table |
| 庆典赞助输入（子环节1） | `population_api.campaign(state, player_id, figure_id, amount)` | **注意**：每个 figure_id 单独调用 |
| 「⏭️ 完成庆典」→ 下一位 | `player_api.next_player(state, player_id)` | 所有玩家完成 → 解锁子环节2 |
| 投票 radio（子环节2） | `population_api.vote(state, player_id, office, figure_id)` | office 为 str |
| 「⏭️ 完成投票」→ 下一位 | `player_api.next_player(state, player_id)` | 所有玩家完成 → resolve |
| 选举结算 | `population_api.resolve_election(state)` | 更新公示区结果 |
| AI 自动庆典 | `AutoFestivalDecider` | 人类完成后台执行 |
| AI 自动投票 | `AutoVoteDecider` | 人类完成后台执行 |

### 多玩家角色

```
子环节1（庆典）: 人类轮流赞助本派系 → AI 后台 → 解锁
子环节2（投票）: 人类可投任意派系候选人 → AI 后台 → resolve → 公示
```

---

## 阶段 5: 元老院 (Senate) — 角色锁定三栏

### 数据契约

```
get_senate_view(state, viewer_player_id):
  phase_id: "senate"
  is_current_player: bool
  current_phase_id: str
  presiding_officer: {name: str, faction: str}
  faction_leaders: [{name, faction, influence}]
  seat_share: {faction_id: percent}
  active_foreign_wars: [{war_id, name, threat_level, ...}]
  pending_peace_treaties: [{war_id, name, indemnity, truce_years, territory}]
  governor_vacancies: {"proconsul": [{province_id, name}], "propraetor": [...]}
  pending_contracts: [{contract_id, name, type, base_cost}]
```

### 操作映射

| UI 元素 | 触发 API | 参数要求 |
|---------|---------|---------|
| 公示区（会议信息） | `get_senate_view().data.{presiding_officer, faction_leaders, seat_share}` | 只读 |
| **子环节1：执政官提案** | | |
| 宣战 checkbox + 军团数 | `senate_api.propose(state, player_id, "war", war_id=..., legions=...)` | war_id: str, legions: int |
| 停战 checkbox（展示条约） | `senate_api.propose(state, player_id, "peace", war_id=...)` | 自动取 war.peace_treaty |
| 总督任命 checkbox + 人选 | `senate_api.propose(state, player_id, "governor", province_id=..., candidate_id=...)` | candidate 从 `get_eligible_governor_candidates()` 获取 |
| 建造合同 checkbox + 预算 | `senate_api.propose(state, player_id, "budget", contract_id=..., modified_budget=...)` | 滑块值 |
| 包税合同 checkbox + 金额 | `senate_api.propose(state, player_id, "budget", contract_id=..., modified_budget=...)` | 滑块值 |
| 卖地法案 checkbox + 数量 | `senate_api.propose(state, player_id, "land", act_type="sale", percent=...)` | percent = amount / national_land |
| 分地法案 checkbox + 数量 | `senate_api.propose(state, player_id, "land", act_type="distribution", percent=...)` | 同上 |
| 接管战争 checkbox（跳过表决） | `senate_api.process_war_takeover(state, decider)` | 不进入 vote/veto 流程 |
| 「提交」按钮 | 循环调用 `propose()`，然后 `syncBillsToVotePanel()` | 提交后解锁子环节2 |
| **子环节2：元老表决** | | |
| 法案同意 checkbox | `senate_api.vote(state, player_id, proposal_ids, votes)` | votes: [bool, ...] 与 ids 对应 |
| 「确认表决」按钮 | 调用 vote() 后解锁子环节3 或 逃生 | 无同意的跳过否决 |
| **子环节3：保民官否决** | | |
| 否决 checkbox | `senate_api.veto(state, player_id, proposal_ids)` | 勾选 = 否决 |
| 「确认否决」→ 公示结果 | `senate_api.resolve_senate(state, vote_decider, takeover_decider)` | 自动调用 |
| 逃生出口：「结束元老院」 | 同 resolve_senate（无法案时直接跳过） | 防死锁 |

### 多玩家角色

```
子环节1（提案）: 仅执政官玩家操作 → 提交 → 锁定
子环节2（表决）: 所有玩家轮流 → 全部完成 → 解锁子环节3 或 逃生
子环节3（否决）: 仅保民官玩家操作 → 提交 → 公示
AI 模式: 调用 AutoSenateVoteDecider / AutoTribuneVetoDecider
```

### GuiApiAdapter 需要新增的方法

```python
def propose(self, player_id, proposal_type, **kwargs)       # senate_api.propose
def vote(self, player_id, proposal_ids, votes)                # senate_api.vote
def veto(self, player_id, proposal_ids)                       # senate_api.veto
def resolve_senate(self)                                      # senate_api.resolve_senate
def get_eligible_governors(self, governor_type)               # 返回 List[Figure]
def get_senate_view(self, viewer_id)                          # 已有
```

---

## 阶段 6: 战斗 (Combat) — 三栏并排

### 数据契约

无专用 combat_api，需新增 `get_combat_view()`：

```
建议新增 get_combat_view(state, viewer_player_id):
  active_wars: [{
    war_id: str
    name: str
    commander: {name: str, faction: str, martial: int}
    ally_forces: int               # commander.martial + sum(legion_strength)
    enemy_forces: int              # war.get_total_strength()
    legions: [legion_number, ...]
    fleets: [fleet_number, ...]
    attacked_this_turn: bool
    result: str (optional)         # 上次进攻结果
  }]
  military_summary: {
    active_wars_count: int
    mobilized_legions: int
    available_legions: int
    fleet_count: int
    treasury: int
  }
  max_wars: 3                      # 第4场 = game over
```

### 操作映射

| UI 元素 | 触发 API | 说明 |
|---------|---------|------|
| 公示区（军力总览） | `get_combat_view().data.military_summary` | 激活战争数/军团/舰队/国库 |
| 战争面板 × 3 | `get_combat_view().data.active_wars[]` | 每场一个面板 |
| 「⚔️ 发动进攻」按钮 | 建议新增 `combat_api.execute_battle(state, war_id)` | 包装 `CombatCommand._resolve_battle()` |
| 战斗结果展示 | `execute_battle` 返回值 | 面板内展示军力计算+结果+停战草案 |
| AI 自动进攻 | `AutoWarDecider` | 人类完成后台执行 |

### 战斗结果数据结构

```python
execute_battle 返回值建议:
{
  "war_id": str,
  "result": "TRIUMPH" | "VICTORY" | "STALEMATE" | "DEFEAT" | "DISASTER",
  "dice_roll": int,        # 1-6
  "ally_total": int,       # ally_forces + dice
  "enemy_total": int,
  "loot": int (optional),  # TRIUMPH 时
  "stability_change": int (optional),  # DEFEAT/DISASTER 时
  "treaty": {              # STALEMATE 时
    "indemnity": int,
    "truce_years": int,
    "territory": str
  },
  "message": str            # 本地化战斗结果描述
}
```

### 多玩家角色

- **操作者：** 任意玩家点击任意可进攻战争的按钮
- 各战争独立，同一战争每回合仅一次
- 所有战争操作完毕后 → 推进

### GuiApiAdapter 需要新增

```python
def get_combat_view(self, viewer_id)        # 新增专用查询
def execute_battle(self, war_id)             # 新增战斗触发器
```

---

## 阶段 7: 决算 (Resolution)

### 数据契约

```
game_api.advance_year(state, player_id) → {
  success: bool
  message: str           # 年度总结
  data: {
    "year_display": str
  }
}
```

### 操作映射

| UI 元素 | 触发 API | 说明 |
|---------|---------|------|
| 总督轮换信息 | 自动计算，无需 UI 触发 | 决算阶段纯自动 |
| 合同到期处理 | 同上 | — |
| 革命检查 | 同上 | — |
| 年度衰减 | 同上 | — |
| ⚠️ 警告面板 | `game_api.get_status_summary()` 扩展 | 独裁/财政/军事预警 |
| 📈 年度总结 | `advance_year()` 返回值 | 显示在 UI 中 |
| 「⏭️ 进入下一年度」按钮 | `game_api.advance_year(state, player_id)` | 推进年份，重置所有阶段 |

### 多玩家角色

全阶段自动执行，无玩家操作。

---

## 附录 A: GuiApiAdapter 增量开发清单

### 当前已有方法（保留）

```python
# 天命 ✅
execute_mortality(player_id)
advance_mortality(player_id)
get_mortality_view(viewer_id)

# 人口 ✅
campaign(player_id, figure_id, amount)
vote(player_id, office, figure_id)
next_player(player_id)
resolve_election()
get_population_view(viewer_id)

# 会话 ✅
get_snapshot(viewer_id)
get_senate_view(viewer_id)
```

### 需要新增的方法

```python
# 广场（forum_api 封装）
retire_figure(player_id, figure_id)
recruit_figure(player_id, figure_id, amount)
place_bid(player_id, figure_id, contract_id, amount, profit_rate=None)
buy_land(player_id, figure_id, amount)
vote_triumph(player_id, war_id, vote)
resolve_forum()
get_forum_view(viewer_id)                 # 新增

# 元老院（senate_api 封装）
propose(player_id, proposal_type, **kwargs)
vote_senate(player_id, proposal_ids, votes)
veto(player_id, proposal_ids)
resolve_senate()
get_eligible_governors(governor_type)

# 战斗（combat_api 封装 — 需新建）
get_combat_view(viewer_id)                # 新增
execute_battle(war_id)                     # 新增

# 收入（revenue_api 封装 — 需新建）
get_revenue_view(viewer_id)               # 新增

# 通用
get_status_summary()                       # 已有 game_api.get_status_summary
get_contracts()                            # 新增 contract_api 封装
get_provinces()                            # 新增 province_api 封装
execute_phase(phase_name, player_id)       # game_api.execute_phase
advance_year(player_id)                    # game_api.advance_year
```

---

## 附录 B: 多玩家交互 API 参考

```python
# 玩家切换
player_api.next_player(state, player_id)           # 切换到下一位
state.is_current_player(viewer_player_id)           # 判断是否轮到此玩家
state.get_current_player()                           # 获取当前玩家对象
state.get_player(player_id)                          # 获取指定玩家

# AI 决策器（各阶段自动模式）
AutoRetirementDecider     # 广场-解雇
AutoRecruitmentDecider    # 广场-招募
AutoBidDecider             # 广场-竞标
AutoTriumphDecider         # 广场-凯旋投票
AutoFestivalDecider        # 人口-庆典
AutoVoteDecider            # 人口-投票
AutoSenateVoteDecider      # 元老院-表决
AutoTribuneVetoDecider     # 元老院-否决
AutoWarDecider             # 战斗-进攻
AutoWarTakeoverDecider     # 元老院-接管战争
```

---

## 附录 C: 版本对照

| 映射文档版本 | 对应设计文档版本 | 对应原型 | 说明 |
|-------------|----------------|---------|------|
| v0.1（草案） | — | — | CODEX 原始 mapping，仅覆盖人口+元老院只读 |
| **v2.0（当前）** | **V2.0** | **V3.23** | 完整覆盖 7 阶段，含多玩家/AI/i18n |
| v2.1（WP-E，2026-08-23） | GUI-BETA-R1 WP-E | — | Forum DTO 新字段 + buy_land 防重 + doAdvanceResolution 两段式（见附录 D） |
| **v2.2（WP-E-G7R，2026-08-24）** | GUI-BETA-R1 WP-E-G7R | — | doAdvanceResolution 单命令重写（附录 D.3 修订）+ preview DTO（附录 D.4，005-01~14 traceability） |

## 附录 D: WP-E 更新（2026-08-23，GUI-BETA-R1）

### D.1 Forum DTO 新字段（`get_forum_view`）

| 字段 | 语义 | 权威源 |
|:--|:--|:--|
| `land_sale_total` | 本年度公地出售总额 | `turn_land_sale_total`（game_state） |
| `land_price_per_unit` | 公地单价 | `state.get_economic_rule("land_price_per_unit")`（权威，禁硬编码） |
| `viewer_land_requests` | 当前查看者派系的认购请求（按 faction_id 过滤派生） | `pending["land_purchases"]` |
| `land_allocation` | resolve 后结构化分配结果 | `resolve_forum` 返回 `land_allocation` |
| `war_events` | 本回合战争事件字符串（保留载体） | `state._forum_war_events` |
| `has_active_war` | 是否存在活跃战争 | `ws.get_active_wars()`（war_system 权威） |

### D.2 buy_land 防重语义（E-G7-07 同族）

- `buy_land`：pending 内已存在同 figure 认购 → 显式拒绝「该人物本回合已提交公地认购请求」
  （E-10 失败面；非静默替换）；quantity 由 landDialog 配置（IntValidator 1..999），
  不再固定 amount=1。
- `place_bid`：同 (contract_id, figure_id) 已出价 → 显式拒绝「该人物已对本合同出价」（E-G7-07 恰一次）。

### D.3 doAdvanceResolution 单命令（WP-E-G7R 修订，E-05 / GUI-BETA-005）

- **单命令语义**：一键 → `advance_year` 恰好一次 → 成功**直接导航 mortality**
  （删除原第二段导航分支）；失败 → 停留 resolution + `_refresh_resolution_view()`
  + advancing 复位 → **可重试**（EC-09）；finally 补发 `phaseChanged`（P0
  notify 闭合：复位后按钮绑定重算 enabled）。
- **重入防护（EC-08）**：`_resolution_advancing` guard + 成功后
  `selectedPhaseId="mortality"`（后续点击分派 mortality）+ `game_api.advance_year`
  内部重入 guard → 双点击 ≤1 次推进。
- **标签唯一化**：`advanceCurrentPhaseText` 无两段标签，统一
  「⏭️ 进入下一年度」（`_PHASE_ADVANCE_DISPATCH["resolution"]["label"]`）。
- **退役字段**：`_resolution_settled` / `resolutionSettled` /
  `resolutionStepStatuses` 删除；`get_resolution_view` 的 `step_statuses` 键
  与 `results.settled` 键移除；`resolved` 单源化 =
  `is_phase_executed("resolution")`（跨年毒化闭合）。

### D.4 Resolution Preview DTO + 005-01~14 目标行为（WP-E-G7R，Doc-7 traceability）

**preview 四信息类目**（`get_resolution_view` 返回体 `preview` 键，只读投影，
直连 `_plan_*`，零变异 EC-01）：

| 类目 | DTO 字段 | E-03/E-04 呈现契约 |
|:--|:--|:--|
| 1. 总督返回 | `preview.governor_returns[]`（province_name/governor_name/successor_name） | `{province}总督{governor}将返回罗马`；空态「本年度结束时无总督返回」 |
| 2. 合同到期 | `preview.contract_expiries[]`（contract_id/name/contract_type，身份行） | `{contract_name} → 将于本年度结束时到期`；空态「本年度结束时无合同到期」 |
| 3. 和约到期 | `preview.truce_expiries[]`（war_name） | `{war_name} → 和约将在本年度结束时到期`；空态「本年度结束时无和约到期」 |
| 4. 年度衰减 | `preview.faction_influence[]`（faction_name/influence_before/after/delta） | 派系聚合（decay-only，ODR-C1）；`{faction} → 将减少 {abs(delta)} 点影响力，降至 {after}`；空态「本年度结束时无派系影响力衰减」 |
| 独立 B 区 | `warnings`（现状扫描，现在时） | 「⚠️ 风险检查」独立区；空态「当前无重大年度风险」 |

**GUI-BETA-005 目标行为（005-01~14，acceptance traceability 载体 = 本附录 D.4）**：

| ID | 目标行为 | 落地（测试） |
|:--|:--|:--|
| 005-01 | 无顺序 StepBar / 无 x/4 进度隐喻 | `test_no_visible_stepbar`（EC-03） |
| 005-02 | 总督返回将来时文案 | `test_future_tense_copy_family`（EC-04） |
| 005-03 | 合同到期身份行（禁仅计数） | `test_future_tense_copy_family` + `test_read_model_contract_expiries_identity_rows` |
| 005-04 | 风险检查独立现在时区 | `test_render_four_categories_and_risk_zone_present` |
| 005-05 | 年度衰减派系聚合（禁 per-figure） | `test_faction_influence_aggregate_projection` + `test_no_per_figure_decay_dump`（EC-05） |
| 005-06 | 空态显式（E-04） | `test_preview_empty_states` |
| 005-07 | 无 StepBar（E-02） | `test_no_visible_stepbar`（EC-03） |
| 005-09 | 和约到期将来时文案 | `test_future_tense_copy_family`（EC-04） |
| 005-11 | preview 零变异 + 刷新稳定 | `test_preview_zero_mutation`（EC-01）/ `test_preview_refresh_stable`（EC-02） |
| 005-12 | 单命令 → advance 恰好一次 → mortality | `test_single_command_advance_navigates_mortality` / `test_advance_year_called_exactly_once`（EC-07） |
| 005-13 | preview=commit parity | `test_preview_commit_parity`（EC-10，decay-only ODR-C1） |
| 005-14 | 失败可重试 + 双点击 ≤1 | `test_advance_failure_no_partial_and_retryable`（EC-09）/ `test_double_click_advances_at_most_once`（EC-08） |

---

*本文档将随原型迭代持续更新。CODEX 开发时以本文档 + `EOR_GUI设计文档.md` V2.0 为最终依据。*
