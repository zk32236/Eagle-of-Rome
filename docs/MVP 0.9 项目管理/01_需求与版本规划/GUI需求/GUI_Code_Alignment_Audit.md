# EOR GUI 设计 ↔ 代码实现对齐审计

> 版本: V1.0（2026-07-05）
> 基线原型: V3.23
> 代码基准: src/ 目录 (MVP 0.9)
> 审计前提: 本轮 GUI 开发不动现有代码功能

---

## 摘要

| 阶段 | GUI 原型状态 | 对应 API | GUI Adapter 封装 | 对齐度 |
|------|-------------|---------|-----------------|--------|
| **天命** | V3.20 | `mortality_api` ✅ | ✅ 已封装 | 🟢 完全对齐 |
| **收入** | V3.3 | `game_api.execute_phase` | ❌ 未封装 | 🟡 API 存在但无专用适配 |
| **广场** | V3.20 | `forum_api` (8 函数) ✅ | ❌ 未封装 | 🟡 API 完整，需封装适配器 |
| **人口** | V3.20 | `population_api` ✅ | ⚠️ 部分封装 | 🟢 基本对齐 |
| **元老院** | V3.22 | `senate_api` (11 函数) ✅ | ❌ 未封装 | 🟡 API 完整，需封装适配器 |
| **战斗** | V3.23 | 无独立 combat_api | ❌ 未封装 | 🔴 无专用 API |
| **决算** | 设计文档 | `game_api.execute_phase` | ❌ 未封装 | 🟡 无专用适配 |

---

## 1. 天命阶段 — 对齐检查

### GUI 控件 ↔ API 映射

| GUI 控件 | 对应 API | 参数匹配 | 返回值匹配 |
|----------|---------|---------|-----------|
| 「⚡ 执行天命」按钮 | `mortality_api.execute_mortality_phase(state, viewer_player_id)` | ✅ viewer_player_id 匹配 | ✅ 返回 events, next_phase_id |
| 「进入收入」按钮 | `mortality_api.advance_mortality_phase(state, viewer_player_id)` | ✅ | ✅ |
| 死亡事件展示 | `mortality_api.get_mortality_view(state, viewer_player_id)` | ✅ | ✅ data.result.events 含死者信息 |
| 事件结果展示 | `mortality_api.execute_mortality_phase` 返回 data | ✅ | ✅ events 列表 |

### GuiApiAdapter 封装
```python
# ✅ 已存在
def execute_mortality(self, player_id: str)
def advance_mortality(self, player_id: str)
def get_mortality_view(self, viewer_id: str)
```

### ⚠️ 差异
- API `execute_mortality_phase` 接受 `viewer_player_id` 参数，但原型使用 `player_id`（当前应无区别）
- 原型默认为单人模式，`viewer_player_id` 应与当前玩家 ID 一致

### 结论: 🟢 完全对齐，可作为 CODEX 开发参考

---

## 2. 收入阶段 — 对齐检查

### GUI 控件 ↔ API 映射

| GUI 控件 | 对应 API | 参数匹配 | 返回值匹配 |
|----------|---------|---------|-----------|
| 国家收入/支出列表 | `EconomicService.settle_revenue_phase()` | — | 返回 indemnities, national_opex, public_land_income, maintenance |
| 派系财政列表 | 同上 | — | 返回 faction_rows (faction_id, name, subsidy, member_contribution, total) |
| 地主私人收益列表 | 同上 | — | 返回 private_land_rows (figure_id, name, income, wealth) |
| 「确认收入结算」按钮 | `game_api.execute_phase(state, "revenue", player_id)` | ✅ | 阶段执行成功 |

### GuiApiAdapter 封装
```python
# ❌ 未封装
# 需要通过 game_api.execute_phase 调用
```

### ⚠️ 差异
- 无专用 `revenue_api`，收入通过 `EconomicService.settle_revenue_phase()` 结算
- `game_api.execute_phase` 以 CLI 命令方式运行，返回纯文本输出
- 原型展示的 mock 数据格式与实际 CLI 输出的格式差异较大
- **需新增**: 一个专用的 `revenue_api` 或 `get_revenue_view` 返回结构化数据

---

## 3. 广场阶段 — 对齐检查

### GUI 控件 ↔ API 映射

| GUI 控件 | 对应 API | 参数匹配 | 返回值匹配 |
|----------|---------|---------|-----------|
| 解雇成员 | `forum_api.retire_figure(state, player_id, figure_id)` | ✅ | ✅ data.figure_id |
| 人才市场列表 | `state.curia.get_all_available()` | — | 返回 Figure 列表 |
| 招募 | `forum_api.recruit_figure(state, player_id, figure_id, amount)` | ✅ figure_id 为 int | ✅ data.figure_id, amount |
| 合同竞标 | `forum_api.place_bid(state, player_id, figure_id, contract_id, amount, profit_rate)` | ⚠️ **格式差异** | ✅ |
| 公地认购 | `forum_api.buy_land(state, player_id, figure_id, amount)` | ✅ | ✅ data.figure_id, amount |
| 凯旋投票 | `forum_api.vote_triumph(state, player_id, war_id, vote)` | ✅ war_id 为 str | ✅ data.vote |
| 公示结算 | `forum_api.resolve_forum(state)` | ✅ | ✅ data.results (list of str) |
| 私地交易 | `forum_api.transact_land(state, player_id, seller_id, buyer_id, land, price)` | ✅ | ✅ |

### GuiApiAdapter 封装
```python
# ❌ 未封装 — 需要新增
def retire_figure(self, player_id: str, figure_id: int)
def recruit_figure(self, player_id: str, figure_id: int, amount: int)
def place_bid(self, player_id: str, figure_id: int, contract_id: int, amount: int, profit_rate: float = None)
def buy_land(self, player_id: str, figure_id: int, amount: int)
def vote_triumph(self, player_id: str, war_id: str, vote: bool)
def resolve_forum(self)
```

### ⚠️ 差异
1. ⚠️ **原型使用字符串 name**（如 "Gaius Manlius"），API 使用 **整数 ID** (`figure_id: int`)。需要将 GUI 的人物选择改为 ID 驱动
2. ⚠️ `place_bid` 需要 `profit_rate` 参数（0~1 浮点数），原型未涉及
3. ⚠️ CLI 广场阶段分为 **5 个步骤**（公告→裁员→市场→公示→交易），且**按玩家轮流**，原型的 "2 子环节" 设计忽略了玩家轮次逻辑

---

## 4. 人口阶段 — 对齐检查

### GUI 控件 ↔ API 映射

| GUI 控件 | 对应 API | 参数匹配 | 返回值匹配 |
|----------|---------|---------|-----------|
| 庆典赞助 | `population_api.campaign(state, player_id, figure_id, amount)` | ✅ | ✅ |
| 投票选举 | `population_api.vote(state, player_id, office, figure_id)` | ✅ office 为 str | ✅ |
| 下一位玩家 | `player_api.next_player(state, player_id)` | ✅ | ✅ |
| 选举结算 | `population_api.resolve_election(state)` | ✅ | ✅ |
| 候选人列表 | `session_api.get_population_view(state, viewer_player_id)` | ✅ | data 含 candidates, offices |
| 选举结果 | `population_api.resolve_election` | ✅ | data 含 results |

### GuiApiAdapter 封装
```python
# ✅ 已存在
def campaign(self, player_id: str, figure_id: int, amount: int)
def vote(self, player_id: str, office: str, figure_id: int)
def next_player(self, player_id: str)
def resolve_election(self)
def get_population_view(self, viewer_id: str)
```

### ⚠️ 差异
1. ⚠️ 原型使用字符串候选人名，API 使用 `figure_id: int`
2. ⚠️ `campaign` API 按 **单个 figure_id** 操作，原型界面允许同时赞助多人（需循环调用或新增批量接口）
3. ⚠️ `vote` API 需要 `office` 和 `figure_id`，原型使用 radio button 单选，对齐良好

---

## 5. 元老院阶段 — 对齐检查

### GUI 控件 ↔ API 映射

| GUI 控件 | 对应 API | 参数匹配 |
|----------|---------|---------|
| 提案配置 | `senate_api.propose(state, player_id, proposal_type, **kwargs)` | ✅ proposal_type + kwargs |
| 提交法案 → 解锁表决 | `senate_api.propose`（逐条调用） | ✅ |
| 元老表决 | `senate_api.vote(state, player_id, proposal_ids, votes)` | ✅ proposal_ids: List[int], votes: List[bool] |
| 保民官否决 | `senate_api.veto(state, player_id, proposal_ids)` | ✅ proposal_ids: List[int] |
| 公示结果 | `senate_api.resolve_senate(state, vote_decider, takeover_decider)` | ✅ |
| 元老院视图 | `senate_api.get_senate_view(state, viewer_player_id)` | ✅ 数据非常丰富 |
| 接管战争 | `senate_api.process_war_takeover(state, decider)` | ✅ |
| 宣战 | `senate_api.execute_war_declaration(state, war, consul_id, legions)` | ⚠️ 需要 war 对象 |
| 总督任命 | `senate_api.get_eligible_governor_candidates(state, governor_type)` | ✅ 返回 List[Figure] |

### GuiApiAdapter 封装
```python
# ❌ 未封装 — 需要新增
def propose(self, player_id: str, proposal_type: str, **kwargs)
def vote(self, player_id: str, proposal_ids: List[int], votes: List[bool])
def veto(self, player_id: str, proposal_ids: List[int])
def resolve_senate(self)
def get_senate_view(self, viewer_id: str)
```

### ⚠️ 差异
1. **提案类型与参数**: API 的 `propose` 参数与原型基本对齐：
   - `proposal_type` 为字符串（如 `"war_declaration"`, `"peace_treaty"`, `"governor_appointment"` 等）
   - `**kwargs` 传递参数（legions, nominee_id, budget 等）
   - 原型使用提案 ID (bill_type) 字符串，需映射到 `proposal_type`
2. **投票机制**: API `vote(state, player_id, proposal_ids, votes)` 接受批量投票
   - 原型使用复选框勾选，可以批量提交，对齐良好
3. **总督任命 API**: `get_eligible_governor_candidates(state, governor_type)` 返回 `List[Figure]`，不是标准 `api_response` 格式

---

## 6. 战斗阶段 — 对齐检查

### 当前对齐状态

```
┌──────────────────────────────────────────────────────────────────────┐
│                     ⚠️ 需要注意                                        │
│                                                                      │
│  战斗阶段在代码中没有独立的 combat_api.py                               │
│  战斗通过 CLI 命令层 CombatCommand 自动执行                              │
│  战斗结果由 WarSystem + NavalSystem 内部逻辑决定                        │
│                                                                      │
│  GUI 需要:                                                           │
│  1. war_system.get_active_wars() 获取战争列表                          │
│  2. War 实体的 strength/commander 字段显示军力                         │
│  3. 直接调用 CombatCommand._resolve_battle() 来执行战斗                 │
│     （或新增一个 combat_api 包装层）                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 战斗结果映射

| 代码内部结果 | 原型对应 | API 路径 | 数据来源 |
|------------|---------|---------|---------|
| TRIUMPH | 大胜 | 无独立 API | CombatCommand._resolve_battle |
| VICTORY | 险胜 | 无独立 API | CombatCommand._resolve_battle |
| STALEMATE | 平局 | 无独立 API | CombatCommand._resolve_battle |
| DEFEAT | 败退 | 无独立 API | CombatCommand._resolve_battle |
| DISASTER | — | 无独立 API | CombatCommand._resolve_battle |

### ⚠️ 差异
1. 原型使用简化模型（`allyForces: int` + dice），实际模型使用 `commander.martial + legion_strength`
2. 实际战斗需要军团列表（`legions`）、舰队（`naval`），原型的简单数字不够
3. 战斗结果在代码中是全自动的，原型要求**手动按按钮**，需要在 GUI 中新增一个按钮触发 `CombatCommand.execute()`

---

## 7. 数据格式对齐检查

### 人物 (Figure) 数据结构

| 字段 | 原型显示 | 代码中字段 | 类型 | 对齐 |
|------|---------|-----------|------|------|
| 姓名 | name | `figure.get_formal_name()` | str | ✅ |
| 军略 | 数字 | `figure.martial` | int | ⚠️ 原型字段名不匹配 |
| 智略 | 数字 | `figure.intellect` | int | ⚠️ 原型字段名不匹配 |
| 魅力 | 数字 | `figure.charisma` | int | ⚠️ 原型字段名不匹配 |
| 热忱/热诚 | 数字 | `figure.zeal` | int | ⚠️ 原型字段名不匹配 |
| 影响力 | 数字 | `figure.influence` | int | ✅ |
| 派系 | 文本 | `figure.faction_id` | int | ⚠️ 原型存文本 |
| 阶级 | 文本 | `figure.class_tier.value` | str | ✅ |
| 财富 | 数字 | `figure.wealth` | int | ✅ |
| 费用 | 数字 | 无直接字段 | — | ⚠️ 需计算 |
| 私产(不可见) | 隐藏 | `figure.wealth` | int | ✅ |

### 战争 (War) 数据结构

| 字段 | 原型 | 代码中字段 | 类型 | 对齐 |
|------|------|-----------|------|------|
| ID | str | `war.id` | str | ✅ |
| 名称 | str | `war.name` | str | ✅ |
| 罗马战力 | 数字 | `warrior_combat_strength()` | int | ⚠️ callable 方法 |
| 敌方战力 | 数字 | `war.get_total_strength()` | int | ⚠️ callable 方法 |
| 指挥官 | str | `war.commander_id` | int | ⚠️ 需 look up |
| 军团 | 文本 | `war.legion_numbers` | List[int] | ✅ |
| 舰队 | 文本 | `war.assigned_fleet_ids` | List[int] | ✅ |

### 派系 (Faction) 数据结构

| 字段 | 原型 | 代码中字段 | 对齐 |
|------|------|-----------|------|
| 名称 | text | `faction.name` | ✅ |
| 金库 | 数字 | `faction.treasury` | ✅ |
| 影响力 | 数字 | 派系成员影响力之和 | ⚠️ 需计算 |
| 成员数 | 数字 | `len(faction.member_ids)` | ✅ |
| 领袖 | 文本 | 通过 member_ids 查找 | ⚠️ 需计算 |

---

## 8. 总体建议

### 优先级 P0（必须对齐才能开发）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **人物 ID vs 名称** | 所有阶段 | 原型使用字符串名，API 使用 `figure_id: int`。GUI 需改为 ID 驱动 |
| 2 | **战斗阶段无独立 API** | 战斗 | 需新增 `combat_api` 或通过 `get_war_system` + `CombatCommand` 封装 |
| 3 | **GUI Adapter 大幅空缺** | 广场/元老院 | 需为 `forum_api`、`senate_api` 新增约 10 个适配器方法 |

### 优先级 P1（需注意的差异）

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 4 | **广场阶段实际流程为 5 步 + 按玩家轮流** | 广场 | 原型 2 子环节过于简化，实际需要玩家轮次逻辑 |
| 5 | **战斗结果计算模型差异** | 战斗 | 原型 dice+allyForces vs real: commander.martial + legion_strength |
| 6 | **人物属性字段名** | 所有阶段 | 原型用「军略/智略/魅力/热忱」，代码用 martial/intellect/charisma/zeal |
| 7 | **收入阶段无结构化 API** | 收入 | `EconomicService.settle_revenue_phase()` 返回结构化 dict，需封装为 get_revenue_view |

### 优先级 P2（优化项）

| # | 问题 | 建议 |
|---|------|------|
| 8 | 原型属性值 | 改为与实际场景数据一致 |
| 9 | 多玩家轮次 | 原型的 "下一位" 按钮应调用 `player_api.next_player` |

---

## 9. 下一步行动

1. **CODEX**: 先完成 GUI Adapter 的 forum_api 和 senate_api 封装
2. **CODEX**: 新增 combat_api 包装 CombatCommand
3. **CODEX**: 人物选择器改为 ID 驱动
4. **我（奥古斯都）**: 更新原型使用 figure_id 而非字符串名
5. **克劳狄乌斯确认**: 以上差异是否需要在当前原型中体现，还是留给 CODEX 实际开发时处理
