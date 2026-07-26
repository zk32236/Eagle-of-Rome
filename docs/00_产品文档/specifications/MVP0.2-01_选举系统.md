# MVP0.2-01 — 选举系统

> **功能简述：** 选举系统 — 罗马共和国年度公职选举的完整流程

## 1. 功能目的

选举系统是实现罗马共和国政治轮替的核心机制。每年在人口阶段（Population Phase），现任官员（除战场指挥官外）悉数卸任，各派系通过竞选（庆典）和投票活动，竞争执政官（Consul）、监察官（Censor）、裁判官（Praetor）、财务官（Quaestor）、保民官（Tribune）等公职。

选举系统确保：

1. **政治流动性**：官职每年轮换，防止权力固化
2. **派系博弈**：各派系通过资金投入庆典提升候选人声望，通过加权投票争夺职位
3. **职业路径（Cursus Honorem）**：候选人必须满足各公职的任职资格链（如执政官需曾任裁判官）
4. **影响力体现**：派系总影响力决定投票权重，高影响力派系在选举中占优

## 2. 玩家/系统行为

### 2.1 触发时机

选举在 **人口阶段（Population Phase）** 中执行，广场阶段（Forum Phase）之后、元老院阶段（Senate Phase）之前。

完整人口阶段流程（4 步骤）：

```
人口阶段入口
  ├─ Step 0: 公告 ── 军团凯旋/解散、清除广场未招募人物、卸任官员、转换战场指挥官
  ├─ Step 1: 庆典+投票 ── 玩家轮流举办庆典和投票（合并环节）
  ├─ Step 2: 公示 ── 计票、宣布当选、展示影响力变化
  └─ Step 3: 完成标记
```

人口阶段受 `testing.auto_population` 配置控制，可设置为自动模式（AI 全权处理）或手动模式（逐玩家交互）。

**入口点：** `src/ui/commands/phase_population.py` → `PopulationCommand.execute()`

**条件：**
- 广场阶段必须已执行（`state.is_phase_executed("forum")` 检查）
- 人口阶段尚未执行（`state.is_phase_executed("population")` 检查）

---

### 2.2 公告（Step 0）

在 Election Campaign 开始前，系统执行以下准备工作：

**2.2.1 军团凯旋与解散**
- 遍历已结束且获凯旋批准的战争（`war.triumph_approved == True`），举行凯旋式（凯旋指挥官获得声望）
- 解散已结束战争关联的军团（调用 `ms.disband_legions_for_war()`）
- 解散因停战而降级的战争中返回的军团（`ws.clear_legions_to_disband()`）

**2.2.2 舰队解散**
- 如无需要海战的战争，自动解散闲置舰队（`naval_system.disband_unused_fleets()`）

**2.2.3 清除广场人物**
- 广场阶段未招募的人物从游戏中移除（`curia.clear()`）

**2.2.4 卸任官员（战场指挥官除外）**
按以下顺序卸任全部存活人物的现任官职：

| 卸任顺序 | 官职 | 处理方式 |
|---------|------|---------|
| 1 | consul | → ex-consul（`is_absent=False`，即在罗马） |
| 2 | censor | → ex-censor |
| 3 | praetor | → ex-praetor |
| 4 | quaestor | → ex-quaestor |
| 5 | tribune | → ex-tribune |

- 战场指挥官（`is_absent=True` 且 office 为 consul/praetor）**跳过卸任**，由 `_convert_battlefield_commanders()` 单独处理
- 卸任后更新影响力
- 如果卸任的是 consul，从 `turn.leader_ids` 中移除

**2.2.5 战场指挥官转换**
- 战场上的 consul → proconsul，praetor → propraetor
- 添加任期记录（含 assigned_turn 作为起始回合）
- 更新 war 的 `commander_assigned_turn`

---

### 2.3 候选人提名（`get_candidates`）

在庆典和投票开始前，系统按官职优先级生成候选人列表。

**处理顺序（从高到低）：**
1. consul（执政官）
2. censor（监察官）
3. praetor（裁判官）
4. quaestor（财务官）
5. tribune（保民官）

**候选人资格条件（来自 `Figure.can_hold_office`）：**
1. 存活、未死亡
2. 不在战场（`is_absent == False`）
3. 未当选更高官职（按优先级，高官职已录用者不在低官职候选人中重复出现）
4. 满足 `can_hold_office()` 的所有检查。

**`can_hold_office()` 检查规则：**

| 检查项 | 条件 |
|--------|------|
| 现任官职 | 如持有非 ex- 现任官职，禁止参选其他官职 |
| 担任过低阶官职 | 曾担任高阶官职者不能竞选低阶（监察官censor除外） |
| 年龄 | 符合配置 `min_ages`（consul ≥ 40, censor ≥ 42, praetor ≥ 35, quaestor ≥ 30, tribune ≥ 30） |
| 同官职连任 | 不能现任同官职 |
| 冷却期 | 历史中同官职任期距离当前回合 < 冷却年数（由配置 `office_cooldowns` 决定，各官职不同） |
| 前置官职 | consul: 需曾任 praetor；praetor: 需曾任 quaestor；censor: 需曾任 consul；tribune: 仅限骑士和平民 |

**提名数量：**
- 每个官职按配置 `candidates_per_election` 取资格属性最高的前 N 名（默认值均为 2）

**排序依据（资格属性）：**

| 官职 | 排序属性 |
|------|---------|
| consul | charisma（魅力） |
| praetor | intelligence（智略） |
| quaestor | martial（军略） |
| censor | zeal（热忱） |
| tribune | 未单独配置（保民官为最低优先级） |

**去重：** 一旦某个角色被高优先级官职录用，不再出现在低优先级官职候选人列表中。

---

### 2.4 庆典（Campaign）

**触发：** 在 Step 1 中，玩家对自己的派系候选人操作。

**规则：**
1. 玩家只能为**本派系**的候选人举办庆典（权限检查）
2. 花费候选人**私库财富**（`figure.wealth`），不能为负或超出
3. 花费 X 塔兰特 → 人气 +X（`popularity += amount`），并触发 `update_influence()`
4. 费用不能超过候选人当前财富

**效果：**
- `figure.wealth -= amount`
- `figure.popularity += amount`
- `figure.update_influence()` → 影响力重新计算，人气提升会增加影响力（`base = land_private*10 + veterans*10 + popularity`）

**记录：**
- 调用 `state.record_population_campaign(player_id, figure_id, amount)` 记录到临时存储
- 记录示例如 `("p1", 1, 10)` 表示玩家 p1 为人物 1 举办花费 10 的庆典

**数据存储：**
```python
state._population_pending["campaigns"]: List[Tuple[player_id, figure_id, amount]]
```

**快捷操作（手动模式）：**
- `campaign <figure_id> <amount>` — 为指定人物举办庆典
- `campaign all [比例]` — 为本派系全部候选人自动举办庆典，每人花费 `wealth × 比例（默认1.0）`
- `investigate` — 查看本派系人物私库余额

**自动模式（`auto_population=True`）：**
- 使用 `AutoFestivalDecider`：为每位符合条件的候选人随机花费 1~wealth 举办庆典
- 条件：年龄 ≥ 30（配置 `min_festival_age`）、非现任官职、财富 > 0

---

### 2.5 投票（Vote）

**触发：** 在 Step 1 中，玩家依次为各公职投票。

**规则：**
1. 每个玩家在每个公职上**只能投一次票**（`record_population_vote` 检查重复）
2. 投票对象必须是该公职的合法候选人（通过 `get_candidates` 验证）
3. 候选人资格在**投票开始时已锁定**，庆典不会改变候选人列表
4. 支持 `bypass_permission`（自动模式/测试模式跳过回合权限检查）

**快捷操作（手动模式）：**
- `vote <office> <figure_id>` — 为指定公职投票给指定人物
- `vote all` — 为本派系全部公职自动投票给本派系影响力最高的候选人

**自动模式：**
- 使用 `AutoVoteDecider`：优先选择本派系候选人中影响力最高者；无本派系候选人则随机选择

**数据存储：**
```python
state._population_pending["votes"]: List[Tuple[player_id, office, figure_id]]
```

---

### 2.6 选票统计与当选（`resolve_election`）

**触发：** Step 2 公示环节，调用 `population_api.resolve_election()`。

**计票规则（加权投票 Weighted Voting）：**
1. 按官职分组票数（按选举顺序 consul → censor → praetor → quaestor → tribune）
2. 计算每个派系的**总影响力**（遍历所有存活人物，`member.influence` 求和，按 `faction_id` 分组）
3. 每位候选人获得其支持者所属派系影响力的总和 = `Σ faction_influence_for_supporter`
4. 总得票（加权）最高的候选人当选

**平局处理：**
- 如果加权得票相同，使用 `random.choice()` 随机选择一名当选者

**当选效果：**
- 当选者 `figure.office = office`
- 当选者调用 `figure.update_influence()`（官职影响加成即时生效）
- consul 当选者自动添加到 `turn.leader_ids`（派系领袖列表）
- 所有派系调用 `faction.update_faction_leader(state)` 更新派系领袖标记

**当前限制：**
- 每个官职只选举 1 名当选者（尽管配置 `offices_per_election` 支持多个名额）

---

### 2.7 公示与影响力统计（Step 2 公示环节）

选举结果公示包含：
1. 选举结果表格（各官职当选者及所属派系）
2. 各派系影响力对比表（庆典前 vs. 庆典后）

**影响力计算公式（`Figure.update_influence`）：**
```python
base = land_private * 10 + veterans * 10 + popularity
family_bonus = family_prestige * 10
office_bonus = OFFICE_INFLUENCE_BONUS.get(office, 0) 或 EX_OFFICE_INFLUENCE_BONUS
temp_bonus = get_temp_influence()
influence = base + family_bonus + office_bonus + temp_bonus
```

**官职影响力加成：**

| 官职 | 影响力加成 | 卸任后加成 |
|------|-----------|-----------|
| dictator | 60 | 30 |
| censor | 50 | 25 |
| consul | 40 | 20 |
| praetor | 30 | 15 |
| tribune | 20 | 10 |
| quaestor | 10 | 5 |
| proconsul | 0 | 20 |
| propraetor | 0 | 15 |

**公示结束后：**
- 调用 `state.clear_population_pending()` 清空庆典和投票临时数据
- 清除 `_pre_election_influences` 快照

---

## 3. 历史演化

| 阶段 | 变更 |
|------|------|
| MVP 0.2 | 选举系统初始实现，包含候选人提名、投票、计票基础逻辑 |
| MVP 0.4.5 | 引入加权投票（按派系影响力）；派系领袖动态更新；资格链检查完善 |
| MVP 0.5 | 庆典和投票合并为单一步骤；引入 API 层、Decider 模式；支持自动/手动模式切换 |
| 当前 | 庆典+投票合并步骤已稳定；快捷命令（campaign all / vote all）支持；测试覆盖完善 |

## 4. 与其他功能的关系

| 功能 | 关系 |
|------|------|
| **派系系统** | 选举结果影响派系在元老院的控制力；派系领袖可能因当选而变更 |
| **影响力系统** | 当选官职提供影响力加成；庆典增加人气从而增加影响力 |
| **战争系统** | 战场指挥官（consul/praetor）免于卸任，转换为 proconsul/propraetor |
| **经济系统** | 庆典消耗人物私库财富，影响下回合经济表现 |
| **元老院系统** | 选举在元老院阶段之前；当选官员影响元老院提案和投票 |
| **广场阶段** | 广场阶段招募的人物可在本回合选举中竞选 |
| **玩家系统** | 多个玩家按回合依次进行庆典和投票操作 |

## 5. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 正常庆典：人物有财富 50，花费 10 举办庆典 | 财富→40，人气→原+10，影响力按公式重算 |
| 2 | 庆典财富不足：花费超过人物财富 | 返回失败，财富不变 |
| 3 | 庆典权限：非当前玩家或非本派系人物 | 返回失败 |
| 4 | 正常投票：为合法候选人投 consul | 投票记录 (`p1, consul, fig_id`) 成功写入 |
| 5 | 重复投票：同一玩家对同一官职投两次 | 第一次成功，第二次失败（`already_voted`） |
| 6 | 投票非法候选人：人物不在候选人列表中 | 返回失败 |
| 7 | 候选人提名：按资格属性降序，取前 N 名 | consul 取 2 名，praetor 取 2 名（默认值） |
| 8 | 候选人去重：已入选高官职不在低官职中出现 | fig1 入选 consul，不在 praetor 候选列表 |
| 9 | 缺席人物不参选：`is_absent=True` 不在候选人中 | 候选人列表不含出征人物 |
| 10 | 加权计票：f1 高影响力 → f1 支持的候选人当选 | 支持者派系影响力高者胜出 |
| 11 | 平局随机：两个候选人得票相同 | `random.choice` 随机选一 |
| 12 | 当选后影响力更新：当选 consul 后影响力加 40 | 当选者 `influence` 增加 |
| 13 | 派系领袖更新：选举后调用 `update_faction_leader` | 各派系领袖标记正确设置 |
| 14 | 选举前卸任：原官员卸任，ex- 前缀 | consul → ex-consul，影响力降为卸任加成 |
| 15 | 战场指挥官保留：`is_absent=True` 的 consul 不卸任 | 转为 proconsul，继续指挥 |
| 16 | 无投票记录：无任何人投票 | 返回"无投票记录"消息 |
| 17 | 自动模式：`auto_population=True` | 全程 AI 自动，无等待输入 |
| 18 | 多个公职同时选举 | consul + praetor 各自独立计票，互不影响 |

## 6. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.2-01_选举系统.md)

## 7. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-07-17 | Audit Sub-Agent | 审计修复：修正 §2.2.4 卸任表格冗余表述 `is_absent=False 且 is_absent 不在战场` → `is_absent=False（即在罗马）` |
| v1.1 | 2026-07-17 | Audit Sub-Agent | 审计修复：修正 §2.3 提名数量默认值（3→2）及冷却期描述；修正 §2.4 字段名 `land`→`land_private`；修正 §2.6 限制描述；修正 §5 AC #7 提名人数（3→2） |
| v1.0 | 2026-07-13 | Document Officer Sub-Agent | 初版创建 |
