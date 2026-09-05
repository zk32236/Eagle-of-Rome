# MVP0.5-04 — 舰队建造合同

> **功能简述：** 通过合同系统建造海军舰队，用于应对需要海战的战争威胁，实现海军建造、维护、战斗的全流程

## 1. 功能目的

在罗马共和时期，海军力量对于控制地中海至关重要。本功能通过合同系统实现舰队的建造和管理：

- 在皮洛士战争（技术解锁事件）胜利后方可解锁海军建造能力
- 元老院审批预算后，通过广场竞标将舰队建造任务授予骑士
- 骑士中标后按合同规定建造舰队，舰队建造完成后自动指派给相应战争
- 形成"战争威胁→合同生成→竞标→建造→指派→海战"的完整链路
- 国库不足时可解散可用舰队以节约维护费

## 2. 玩家/系统行为

### 2.1 技术解锁检查

```python
def _can_build_fleet(self) -> bool:
    return getattr(self.state, "pyrrhic_war_won", False)
```

- **锁定状态：** `state.pyrrhic_war_won == False` → `generate_construction_contracts()` 返回 `[]`
- **解锁状态：** `state.pyrrhic_war_won == True` → 允许生成建造合同

### 2.2 建造合同生成

1. 在回合推进过程中（通常是元老院阶段或回合开始时），系统检查是否需要生成舰队建造合同
2. `NavalSystem.generate_construction_contracts(current_turn)` 步骤：
   - 检查技术解锁（见 2.1）
   - 获取需要海战的威胁战争：`war_system.get_naval_threat_wars()`
   - 对每个威胁战争，检查是否已有活跃合同或非摧毁舰队（防重复）
   - 计算所需舰队数：`ceil(enemy_strength / base_strength)`
   - 计算总预算：`needed_ships * build_cost_per_ship`
   - 创建 `ContractType.PUBLIC_WORKS` 类型的合同，标记 `_is_fleet_construction = True`
   - 存储舰队组成建议、敌方强度、总预算到合同对象

### 2.3 补充合同生成（G1-11 同战 deficit + R1-G-04 committed 去重，WP-G GC / WP-G-R1）

1. 活跃海战战争（`naval_required = true` 且 `ACTIVE`）由 `generate_replacement_contracts(current_turn)` 按**同战权威 deficit** 生成补充合同（R1-G-04 冻结模型，取代旧二值守卫 blanket skip）：

```
required          = war.enemy_naval_current                          （当前敌方海军强度）
usable            = Σ 同战完成舰队实际战力                           （_target_war_id == war.id 且
                                                                      状态非 DESTROYED/BUILDING/DISBANDED；
                                                                      含 AVAILABLE staging 与 ON_MISSION）
committed_building= Σ 同战 BUILDING live fleets 实际战力            （ACTIVE 合同已物化容量权威——含竞标折价
                                                                      后真实强度；ACTIVE 合同不再按合同另计）
committed_pending = Σ 同战 PENDING/BUDGETED 舰队建造合同约定容量     （未物化容量，按合同组成
                                                                      needed_ships × base_strength 计）
committed         = committed_building + committed_pending          （同一容量只计一次）
deficit           = required - usable - committed
Deficit > 0 → 补充合同数 = ceil(Deficit / 默认舰型 base_strength)
Deficit ≤ 0 → 无补充合同
```

2. 关键语义（G1-11 / R-12 / P1-02）：
   - **禁跨战舰队满足 deficit**——War A 专属舰队不计入 War B 的 usable/committed
   - **禁全局阻断**——任一全局 AVAILABLE 舰队不再阻断所有战争的补充（旧偏差 §11.11 已修复）
   - **ACTIVE 不以合同计 committed**：已中标合同容量 = 其 BUILDING 舰队容量，二者取一
     （取 BUILDING live fleets），不叠加；旧 `_has_active_fleet_contract_for_war`
     （PENDING/BUDGETED/ACTIVE blanket skip）与「building_fleets → continue」二值守卫已删除
   - **示例**：存活 1 艘战力 4、target 10、base 3 → deficit 6 → 补 ceil(6/3)=2 艘
   - **竞标折价 true deficit**：折价中标致 BUILDING 实际强度 < target 时，deficit > 0 →
     生成精确差额（旧 ACTIVE blanket skip 会使该场景不可达，已修复）

示例实现：

```python
needed_ships = max(1, (deficit + base_strength - 1) // base_strength)
```

3. **原始预算不变量（R1-G-04 / v1.6 §7.12.2 最小实现契约）：** 两个 fleet generator
   （`generate_construction_contracts` 与 `generate_replacement_contracts`）创建合同后立即写
   `contract._original_budget = total_budget`——新生成 fleet 合同离开 generator 时满足
   `_original_budget == base_cost == total_budget == total_budget > 0`（§2.5/§3.5
   `cost_ratio = actual_cost / original_budget` 的分母；修复前漏设 → 0 → ratio=1.0 fallback，
   折价 bid 无法调低舰队实际强度 = MVP0.5-04 既有规则（§2.5/§3.5/§6#12）的实现缺陷）。
   `on_contract_awarded` 的 `<=0 → ratio=1.0` 兼容分支保留，仅服务旧存档/旧数据。

### 2.4 元老院审批与竞标

1. 舰队建造合同通过标准的公共工程合同流程处理：
   - 元老院审批预算 → 状态变 `BUDGETED`
   - 广场竞标 → 骑士出价（可打折）
   - 中标者确定后触发 `naval_system.on_contract_awarded()`

### 2.5 中标后的舰队建造

1. `NavalSystem.on_contract_awarded(contract, winner_id)` 步骤：
   - 计算成本比例：`cost_ratio = actual_cost / original_budget`
   - 生成 Fleet 实体：根据合同中的舰队组成建议，为每艘舰队创建 `Fleet` 对象
   - 设置舰队的实际强度：`actual_strength = int(round(base_strength * cost_ratio))`
   - 保证强度在 `[1, base_strength * 2]` 范围内
   - 调用 `fleet.start_building()` 开始建造
   - 记录建造中的舰队到 `_construction_contracts` 字典

### 2.6 建造完成

1. `NavalSystem.process_fleet_construction(current_turn)` 每回合检查：
   - 遍历所有建造中的舰队
   - 当 `build_end_turn == current_turn` 时：
     - 调用 `fleet.complete_building()` 完成建造（状态变为 `AVAILABLE`）
     - 调用 `contract.mark_complete()` 标记合同完成
     - 如果舰队有目标战争（`_target_war_id`），自动尝试指派给该战争

### 2.7 自动指派

1. 建造完成后，若目标战争为 `ACTIVE` 状态且需要海战，自动调用 `assign_fleet_to_war()`
2. 指派成功：舰队状态变为 `ON_MISSION`
3. 指派失败或战争已结束：舰队保持 `AVAILABLE` 状态

### 2.8 海战（G1-10 冻结伤亡数学，WP-G GC）

1. `NavalSystem.resolve_naval_battle(war)` 执行海战判定：
   - 排除建造中的舰队后计算罗马海军战力（基础 + 经验 + **War Commander martial**，G1-20）
   - 与敌方海军战力对比，投骰子（2d6）
   - 根据CRT结果判定：TRIUMPH / VICTORY / STALEMATE / DEFEAT / DISASTER
2. **舰队伤亡（冻结矩阵，G1-10 / D 件 §3）：**

| 结果 | 舰队损失 | 伤亡方式 |
|------|---------|---------|
| TRIUMPH | 0 | — |
| VICTORY | 0 | — |
| STALEMATE | 0 | —（旧「损 1 艘」规则已废弃） |
| DEFEAT | ceil(N/2) | `random.sample(参战舰队, ceil(N/2))` 无放回 → DESTROYED |
| DISASTER | N（全部） | 全部参战舰队 → DESTROYED |

   `ceil(N/2)` 全表（N=参战舰队数）：N=1→1、N=2→1、N=3→2、N=4→2、N=5→3、N=6→3。
   伤亡舰队同步 `war.remove_fleet()`（退出 `assigned_fleet_ids`）。

### 2.9 维护费（G1-14，WP-G GC）

1. `NavalSystem.calculate_maintenance()` 计算所有非 BUILDING/DESTROYED/**DISBANDED** 状态舰队的维护费
   - **战争结束后召回 → AVAILABLE 幸存者仍计维护**（下个 Revenue 最后一次维护，G1-14）
   - 仅 DISBANDED 后不再产生维护
2. `NavalSystem.apply_maintenance()` 在收入阶段扣除维护费：
   - 国库充足时直接扣除
   - 国库不足时尝试解散部分可用舰队以节约开支（行政退役 → DISBANDED，R-11）
3. 维护费从 `state.config.economic_rules.fleet_types[type].maintenance_cost` 读取

### 2.10 舰队解散（DISBANDED vs DESTROYED，G1-13 / R-11，WP-G GC）

1. `AutoFleetDisbandDecider.should_disband_fleet()` 决策逻辑：
   - 建造中/已摧毁/已退役的舰队不解散
   - 没有需要海战的战争 → 解散
   - 有需要海战的活跃/威胁战争 → 不解散
   - 停战已批准的战争 → 不解散（但如果还有活跃海战需要→不解散）
2. `NavalSystem.disband_unused_fleets()` 执行**行政退役**：调用 `Fleet.disband()` → `DISBANDED`
   （非战斗伤亡；**禁走 mark_destroyed → DESTROYED**，R-11）
3. `apply_maintenance()` 国库不足解散分支同样走 `disband()` → `DISBANDED`

> **状态语义分离（G1-13）：** `DESTROYED` = 仅战斗伤亡（海战 DEFEAT/DISASTER）；`DISBANDED` = 正常行政退役（决策器/国库解散/战争结束 Population 退役）。两者均不可复用。

## 3. 核心规则

### 3.1 舰队建造合同状态机

```
战争威胁 → generate_construction_contracts() → Contract(PENDING)
  → 元老院审批 → BUDGETED
  → 广场竞标中标 → on_contract_awarded()
  → Fleet(BUILDING) → process_fleet_construction(工期到期)
  → Fleet(AVAILABLE) + Contract(COMPLETED)
```

### 3.2 舰队实体状态机（G1-12/G1-13，WP-G GC）

```
BUILDING ──[工期到期]──→ AVAILABLE ──[指派战争（同战专属）]──→ ON_MISSION
                                                              │
                                                          ┌───┴───┐
                                                          │ 海战   │
                                                          │ 伤亡   │
                                                          └───┬───┘
                                                              ↓
                                                          DESTROYED（仅战斗伤亡）

ON_MISSION / AVAILABLE ──[战争结束召回]──→ AVAILABLE
AVAILABLE ──[下个 Revenue 最后维护]──→ AVAILABLE
AVAILABLE ──[下个 Population / 决策器 / 国库不足]──→ DISBANDED（行政退役）
```

- `DESTROYED` 与 `DISBANDED` 均为终端态，不可复用（G1-13）
- **禁跨战复用（R-12 / G1-12）**：`Fleet._target_war_id` 为单战专属归属；指派守卫拒绝跨战（`_target_war_id` 为空 = legacy 放行）

### 3.3 合同与舰队的关联

| 合同字段 | 用途 | 舰队字段 | 用途 |
|---------|------|---------|------|
| `_is_fleet_construction` | 标记舰队建造合同 | `_contract_id` | 关联的建造合同ID |
| `_recommended_fleet_composition` | 推荐舰队组成 | `_target_war_id` | 目标战争ID（单战归属 provenance，**持久化**，G1-12） |
| `_enemy_strength` | 敌方海军强度 | `_strength_base` | 基础战力 |
| `_total_budget` | 总预算 | `_fleet_type` | 舰队类型 |
| `_build_time` | 建造周期 | `_build_start/end_turn` | 建造起止回合 |

> **`_target_war_id` 持久化契约（G1-12 / O 件 §3，WP-G GC）：** 必须纳入 `Fleet.to_dict/from_dict`（缺省 None）；旧存档缺键 → None 不崩。同战归属/补充 deficit 判定依赖该字段的 save/load 安全。

### 3.4 合同类型复用

舰队建造合同复用 `ContractType.PUBLIC_WORKS` 类型，通过 `_is_fleet_construction` 布尔标记区分。这意味着：
- 舰队合同走公共工程合同的审批和竞标流程
- 中标后的处理逻辑（`on_contract_awarded`）与公共工程不同
- 铸造合同不执行公共工程的质保期逻辑（`warranty_remaining` 设为 0）

### 3.5 舰队战力计算（G1-20，WP-G GC）

```
combat_strength = _strength_base + experience + commander.martial

指挥官 martial 权威 = War Commander（war.commander_id）——Fleet 指派绑定 = War Commander
（无独立海军指挥官）；Fleet._commander_id 为绑定镜像/兼容；无指派（AVAILABLE staging）
或 war.commander_id 为空时回退舰队私有绑定。

注：实际强度 = int(round(base_strength * cost_ratio))
     cost_ratio = actual_cost / original_budget
     范围: [1, base_strength * 2]
```

### 3.6 舰队类型配置（game_config.json）

| 类型 | 建造费用 | 建造时间 | 维护费 | 基础战力 |
|------|---------|---------|-------|---------|
| trireme | 40 | 1 回合 | 120 | 3 |
| quadrireme | 120 | 2 回合 | 200 | 4 |
| quinquereme | 160 | 3 回合 | 320 | 5 |

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 技术解锁状态 | `state.pyrrhic_war_won` | 布尔值，皮洛士战争胜利后解锁 |
| 威胁战争列表 | `war_system.get_naval_threat_wars()` | 需要海战的威胁战争 |
| 舰队类型配置 | `state.config["economic_rules.fleet_types"]` | 各类型舰队的 build_cost/build_time/strength_base 等 |
| 骑士出价 | `forum_api.place_bid()` | 中标者和出价金额 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 建造合同 | `state.contracts` | `ContractType.PUBLIC_WORKS` + `_is_fleet_construction` |
| Fleet 实体 | `NavalSystem._fleets` | 新创建的舰队对象 |
| 建造状态 | 日志 / 查询 | 建造进度和完成通知 |
| 维护费扣除 | `state.treasury` | 每年在收入阶段扣除 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `NavalSystem` | 核心海军系统，管理舰队全套生命周期 |
| `Fleet` / `FleetStatus` | 舰队实体和状态枚举 |
| `Contract` / `ContractType.PUBLIC_WORKS` | 复用公共工程合同类型 |
| `WarSystem.get_naval_threat_wars()` | 获取需要海战的威胁战争 |
| `WarSystem.get_active_wars()` | 获取活跃战争（用于补充合同） |
| `GameState.pyrrhic_war_won` | 技术解锁标记 |
| `EconomicService.collect_contract_revenues()` | 舰队合同资金结算 |
| `AutoFleetDisbandDecider` | 自动解散决策器 |

## 5. 状态与边界

### 5.1 技术锁定边界

- 皮洛士战争未胜利前：`generate_construction_contracts()` 返回空列表
- `generate_replacement_contracts()` 受同样限制
- 测试已验证：`test_naval_unlock.py::test_naval_unlock_before_pyrrhic`

### 5.2 合同重复保护

- `_has_existing_fleet_or_contract_for_war()` 检查防止同一战争生成多个**初始建造**合同
  （仅 `generate_construction_contracts` 路径）
- 检查范围包括：PENDING/BUDGETED/ACTIVE 状态的合同、非 DESTROYED 状态的舰队
- **补充合同**（G1-11 + R1-G-04）：不再使用二值守卫 blanket skip——同战权威 deficit
  公式四要素（required/usable/committed_building/committed_pending）计算；PENDING/BUDGETED
  合同容量按合同组成计 `committed_pending`，ACTIVE 合同容量以 BUILDING live fleets 计
  `committed_building`（同一容量只计一次），`deficit <= 0 → 无新合同`

### 5.2.1 战斗读模型（R1-G-08 冻结唯一 schema，WP-G-R1）

| 字段 | 作用域 | 计入状态集 | 权威源 | 定义 |
|---|---|---|---|---|
| `assigned_fleet_count` | **per-war**（war card / combat view war 条目） | 完成且已指派该战的舰队（`ON_MISSION`；明确排除 BUILDING/DESTROYED/DISBANDED） | `len(war._assigned_fleet_ids)` 过滤已 DESTROYED/BUILDING/DISBANDED 编号（以 `naval_system.get_fleet` live 实体为准） | 该战争当前可参战舰队数 |
| `naval_ready` | **per-war**（war card） | `assigned_fleet_count >= 1` | 同 `assigned_fleet_count` | 该战争海军 ready 布尔（GUI「舰队已就绪」） |
| `built_fleet_count` | **全局**（combat_view 顶层，共和国军力总览） | 完成状态（`AVAILABLE` + `ON_MISSION`；明确排除 BUILDING/DESTROYED/DISBANDED） | `len([f for f in naval_system.get_all_fleets() if f.status in (AVAILABLE, ON_MISSION)])` | 全局「已建成舰队」数（替代旧 `fleet_count = len(get_available_fleets())`——完工→指派 ON_MISSION 后旧值归零的误读） |

- **兼容 alias（本 R1 保留，P2-N01）**：`fleet_count = built_fleet_count`（全局，`combat_api.get_combat_view` 顶层）；`fleets_assigned = assigned_fleet_count`（per-war，`gui_query_api._war_summary`）。GUI（`CombatStage.qml`/`session_store.py`）**改读新字段**；`war.fleets_assigned` 镜像字段不再作为任何生产读源（正式移除列 backlog）。

### 5.3 舰队生命周期边界（G1-12/G1-13/G1-14，WP-G GC）

| 操作 | 前置条件 | 目标状态 |
|------|---------|---------|
| `start_building()` | 新建 | BUILDING |
| `complete_building()` | BUILDING 且工期到期 | AVAILABLE |
| `assign_to_war()` | AVAILABLE 且同战专属（R-12） | ON_MISSION |
| `recall()` | ON_MISSION | AVAILABLE |
| `mark_destroyed()` | 战斗伤亡（海战 DEFEAT/DISASTER） | DESTROYED |
| `disband()` | 行政退役（决策器/国库不足/Population） | DISBANDED |

> **G1-14 战争结束时序：** TRIUMPH/VICTORY/批准和约 → 幸存舰队召回 → AVAILABLE → **下个 Revenue 付最后维护**（AVAILABLE 仍计维护）→ 下个 Population → DISBANDED。立即解散会逃避最后维护（禁止）。

### 5.4 无效操作

- 不可指派建造中的舰队进行战争
- 不可指派已摧毁的舰队
- 不可指派给不存在或不需要海战的战争
- 不可重复指派同一舰队

### 5.5 无威胁战争

- 当没有需要海战的威胁战争时，`generate_construction_contracts()` 返回空列表
- 当没有活跃战争时，`generate_replacement_contracts()` 返回空列表

### 5.6 费用不足

- 国库不足以支付舰队维护费时，自动解散部分可用舰队
- 如果解散后仍不足，返回失败并记录日志

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 | 测试文件 |
|---|----------|---------|---------|
| 1 | 皮洛士战争前无法建造舰队 | `generate_construction_contracts()` 返回空列表 | `test_naval_unlock.py::test_naval_unlock_before_pyrrhic` |
| 2 | 皮洛士战争后可建造舰队 | 返回非空合同列表 | `test_naval_unlock.py::test_naval_unlock_after_pyrrhic` |
| 3 | 舰队完整生命周期（生成→中标→建造→完成→指派） | 合同生成、舰队建造、到期完成、自动指派 | `test_fleet_construction.py::test_fleet_construction_lifecycle` |
| 4 | 建造中舰队不解散 | `should_disband_fleet()` 返回 False | `test_naval_system.py::test_ignore_building_fleet` |
| 5 | 已摧毁舰队不解散 | `should_disband_fleet()` 返回 False | `test_naval_system.py::test_ignore_destroyed_fleet` |
| 6 | 无海战战争时解散 | `should_disband_fleet()` 返回 True | `test_naval_system.py::test_no_wars_should_disband` |
| 7 | 有海战活跃战争时不解散 | `should_disband_fleet()` 返回 False | `test_naval_system.py::test_active_war_with_naval_required` |
| 8 | 舰队创建默认状态 BUILDING | `fleet.status == FleetStatus.BUILDING` | `test_fleet.py::test_fleet_creation` |
| 9 | 舰队指派战争和召回 | assign→ON_MISSION, recall→AVAILABLE | `test_fleet.py::test_fleet_assign_to_war` / `test_fleet_assign_to_war` |
| 10 | 舰队战力计算（基础+经验+指挥官） | 正确的战力加成 | `test_fleet.py::test_fleet_get_combat_strength` |
| 11 | 舰队合同资金流（中标→收入阶段结算） | 国库支付中标价，骑士收入调整 | `test_func_contracts.py::test_fleet_contract_financial_flow` |
| 12 | 多舰队合同战斗力调整 | 多艘舰队均按成本比例调整强度 | `test_func_contracts.py::test_fleet_contract_multiple_ships` |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.5 (2026-02-24)
- **初始实现：** Fleet 实体 + NavalSystem 基础 → 舰队建造合同生成 + 建造过程
- **MVP 0.7 扩展：** 补充合同生成（`generate_replacement_contracts`）、海战系统（`resolve_naval_battle`）、舰队解散决策器、维护费自动管理
- **合同类型复用：** 舰队建造合同复用 `PUBLIC_WORKS` 类型，通过 `_is_fleet_construction` 标记区分
- **代码入口：** `naval_system.py` (核心逻辑) + `fleet.py` (实体) + `contract.py` (合同扩展字段)

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-04_舰队建造合同.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-09-05 | DA Sub-Agent (WP-G-R1 B2) | R1-G-04/R1-G-08 冻结语义同步：§2.3 补充合同改四要素权威 deficit（required-usable-committed_building-committed_pending，P1-02 committed 去重模型，删二值守卫 blanket skip）+ 两个 fleet generator 创建时 `_original_budget=total_budget` 原始预算不变量（§7.12.2，MVP0.5-04 既有折价规则实现缺陷修复，GAME_RULE_CHANGE=NO）；§5.2 合同重复保护改权威公式；§5.2.1 新增战斗读模型冻结 schema（per-war `assigned_fleet_count`/`naval_ready` + 全局 `built_fleet_count`，兼容 alias `fleet_count`/`fleets_assigned` 本 R1 保留，GUI 改读新字段） |
| v1.0 | 2026-07-12 | Document Officer Sub-Agent G | 初版创建 |
| v1.1 | 2026-08-31 | DA Sub-Agent (WP-G GC) | 冻结语义同步（G1-10/11/12/13/14/20）：§2.3 补充合同改同战 deficit 公式（禁全局阻断/全量重建）；§2.8 海战伤亡改冻结矩阵（STALEMATE 0 损、DEFEAT ceil(N/2) 随机无放回）；§2.9 维护排除 DISBANDED + AVAILABLE 幸存者仍计维护；§2.10/§3.2/§5.3 新增 DISBANDED 行政退役态（禁 mark_destroyed 退役，R-11）；§3.3 补 `_target_war_id` 持久化契约；§3.5 战力 martial 权威 = War Commander（G1-20） |
