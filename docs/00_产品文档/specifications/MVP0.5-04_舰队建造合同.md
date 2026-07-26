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

### 2.3 补充合同生成

1. 当活跃的海战战争缺少可用舰队时，系统调用 `generate_replacement_contracts(current_turn)`
2. 与新建合同逻辑相同，但只检查活跃战争（非威胁战争）
3. 避免针对同一战争生成重复合同

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

### 2.8 海战

1. `NavalSystem.resolve_naval_battle(war)` 执行海战判定：
   - 排除建造中的舰队后计算罗马海军战力
   - 与敌方海军战力对比，投骰子（2d6）
   - 根据CRT结果判定：TRIUMPH / VICTORY / STALEMATE / DEFEAT / DISASTER
   - 应用舰队损失：
     - DISASTER：全部摧毁
     - DEFEAT：损失一半
     - STALEMATE：损失1艘
     - VICTORY/TRIUMPH：无损

### 2.9 维护费

1. `NavalSystem.calculate_maintenance()` 计算所有非 BUILDING/DESTROYED 状态舰队的维护费
2. `NavalSystem.apply_maintenance()` 在收入阶段扣除维护费：
   - 国库充足时直接扣除
   - 国库不足时尝试解散部分可用舰队以节约开支
3. 维护费从 `state.config.economic_rules.fleet_types[type].maintenance_cost` 读取

### 2.10 舰队解散

1. `AutoFleetDisbandDecider.should_disband_fleet()` 决策逻辑：
   - 建造中/已摧毁的舰队不解散
   - 没有需要海战的战争 → 解散
   - 有需要海战的活跃/威胁战争 → 不解散
   - 停战已批准的战争 → 不解散（但如果还有活跃海战需要→不解散）
2. `NavalSystem.disband_unused_fleets()` 执行解散

## 3. 核心规则

### 3.1 舰队建造合同状态机

```
战争威胁 → generate_construction_contracts() → Contract(PENDING)
  → 元老院审批 → BUDGETED
  → 广场竞标中标 → on_contract_awarded()
  → Fleet(BUILDING) → process_fleet_construction(工期到期)
  → Fleet(AVAILABLE) + Contract(COMPLETED)
```

### 3.2 舰队实体状态机

```
BUILDING ──[工期到期]──→ AVAILABLE ──[指派战争]──→ ON_MISSION
                                                      │
                                                  ┌───┴───┐
                                                  │ 海战   │
                                                  │ 解散   │
                                                  └───┬───┘
                                                      ↓
                                                  DESTROYED
```

### 3.3 合同与舰队的关联

| 合同字段 | 用途 | 舰队字段 | 用途 |
|---------|------|---------|------|
| `_is_fleet_construction` | 标记舰队建造合同 | `_contract_id` | 关联的建造合同ID |
| `_recommended_fleet_composition` | 推荐舰队组成 | `_target_war_id` | 目标战争ID |
| `_enemy_strength` | 敌方海军强度 | `_strength_base` | 基础战力 |
| `_total_budget` | 总预算 | `_fleet_type` | 舰队类型 |
| `_build_time` | 建造周期 | `_build_start/end_turn` | 建造起止回合 |

### 3.4 合同类型复用

舰队建造合同复用 `ContractType.PUBLIC_WORKS` 类型，通过 `_is_fleet_construction` 布尔标记区分。这意味着：
- 舰队合同走公共工程合同的审批和竞标流程
- 中标后的处理逻辑（`on_contract_awarded`）与公共工程不同
- 铸造合同不执行公共工程的质保期逻辑（`warranty_remaining` 设为 0）

### 3.5 舰队战力计算

```
combat_strength = _strength_base + experience + (commander.martial if commander exists)

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

- `_has_existing_fleet_or_contract_for_war()` 检查防止同一战争生成多个合同
- 检查范围包括：PENDING/BUDGETED/ACTIVE 状态的合同、非 DESTROYED 状态的舰队
- 补充合同生成也受该检查保护

### 5.3 舰队生命周期边界

| 操作 | 前置条件 | 目标状态 |
|------|---------|---------|
| `start_building()` | 新建 | BUILDING |
| `complete_building()` | BUILDING 且工期到期 | AVAILABLE |
| `assign_to_war()` | AVAILABLE | ON_MISSION |
| `recall()` | ON_MISSION | AVAILABLE |
| `mark_destroyed()` | 任何非 DESTROYED | DESTROYED |

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
| v1.0 | 2026-07-12 | Document Officer Sub-Agent G | 初版创建 |
