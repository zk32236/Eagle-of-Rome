# MVP0.5-03 — 公共工程合同

> **功能简述：** 公共基础设施工程的合同生成、预算审批、竞标、施工结算、质保验收全生命周期管理

## 1. 功能目的

在罗马共和时期，监察官（Censor）负责将公共建设项目发包给骑士阶层（Equites）。本功能实现：
- 元老院对工程预算进行审批（可调整预算金额）
- 审批通过后进入广场竞标阶段，骑士出价竞争
- 中标后骑士按合同规定施工，每年从国库获取付款和利润
- 工程完工后进入质保期，质保期内若工程存在问题，骑士承担维护费用
- 形成"需求提出→预算审批→竞标→施工→质保→验收"的完整链路

## 2. 玩家/系统行为

### 2.1 合同创建

```python
@classmethod
def create_public_works(cls, id: int, project: str, budget: int, profit_margin: float = 0.2) -> "Contract":
    """创建工程合同"""
```

- 合同类型：`ContractType.PUBLIC_WORKS`
- 默认工期：2年（`duration_years = 2`）
- 利润率：20%（`profit_margin = 0.2`，可配置）
- 预期利润 = `int(budget * profit_margin)`
- 创建时状态为 `PENDING`

### 2.2 合同关键字段

```python
# PUBLIC_WORKS 专有字段
_original_budget: int = 0          # 原始预算（预算可能被元老院修改）
_construction_years: int = 0       # 实际施工周期
_warranty_years: int = 0           # 实际质保周期
_warranty_remaining: int = 0       # 剩余质保年限
_annual_income: int = 0            # 骑士年收入（中标价含利润）
_annual_cost: int = 0              # 骑士年支出（施工维护成本）
_is_extended: bool = False         # 是否续约
_standard_warranty: int = 0        # 标准质保年限
```

### 2.3 元老院预算审批

1. 在元老院阶段（`phase_senate.py`），执政官提出 `budget` 类型提案
2. 提案参数包含 `contract_id` 和可选的 `modified_budget`
3. 执政官可在提案时修改预算金额（`propose B02 80` 表示将预算改为80塔兰特）
4. 提案经元老院表决（支持率 > 50%）后执行
5. `PoliticalSystem.execute_passed_proposal()` 处理 `budget` 提案：
   - 若 `modified_budget != contract.base_cost`：
     - 将 `contract._original_budget` 设为原始预算
     - 将 `contract.base_cost` 更新为修改后的预算
   - 将合同状态设为 `BUDGETED`
   - 释放到广场等待竞标

### 2.4 广场竞标与中标

1. 状态为 `BUDGETED` 的合同进入广场竞标阶段
2. 骑士人物出价竞争，最低出价者中标（见 MVP0.4-02 包税权合同竞标逻辑）
3. `Contract.mark_winner(winner_id, current_turn, profit_base)` 标记中标：
   - 前置条件：必须为 `BUDGETED` 状态
   - 设置 `awarded_to`、`awarded_turn`
   - 状态变更：`BUDGETED → ACTIVE`
   - 设置 `remaining_years = duration_years`
   - 设置 `_is_under_execution = True`

### 2.5 施工结算

每年在收入阶段（Revenue Phase）由 `EconomicService._settle_public_works_contract()` 处理结算。最终调用 `Contract.mark_complete(current_turn)` 标记完工：

```python
def mark_complete(self, current_turn: int) -> None:
    """标记合同完成（状态变更与回合记录）"""
    self._is_under_execution = False
    self.status = ContractStatus.COMPLETED
    self._complete_turn = current_turn
```

**结算流程：**
1. 国库每年支付剩余款项（末年为尾款，其余年为 `annual_income`）
2. 骑士承担 `annual_cost` 施工成本并获取（付款-成本）利润
3. 骑士利润按税率纳税
4. 年数递减，当 `remaining_years <= 0` 时调用 `mark_complete()` 标记完成
5. 状态变更 `ACTIVE → COMPLETED`
6. 合同关联行省解除项目绑定

### 2.6 质保期管理

工程完工后进入质保期：

```python
def advance_warranty(self) -> int:
    """递减工程质保期；质保结束时合同过期。"""
    if self.status != ContractStatus.COMPLETED or self._warranty_remaining <= 0:
        return self._warranty_remaining
    self._warranty_remaining -= 1
    if self._warranty_remaining <= 0:
        self.status = ContractStatus.EXPIRED
    return self._warranty_remaining
```

- 质保期内，骑士承担维护费（`_annual_cost`）
- 质保期满后合同状态变为 `EXPIRED`

### 2.7 AI自动预算加成

AI执政官自动提案时，对公共工程合同（含舰队建造合同）进行随机预算加成：

```python
if contract.contract_type == ContractType.PUBLIC_WORKS:
    margin_range = self.state.config.get("economic_rules.public_work_budget_margin_range", [0.05, 0.20])
    r = random.uniform(margin_range[0], margin_range[1])
    modified_budget = int(contract.base_cost * (1 + r))
```

## 3. 核心规则

### 3.1 公共工程合同状态机

```
需求产生 → create_public_works() → Contract(PENDING)
  → 元老院审批 → BUDGETED
  → 广场竞标中标 → mark_winner() → ACTIVE（施工中）
  → 施工结算 → _settle_public_works_contract() / mark_complete()
  → 工期结束 → COMPLETED（质保期）
  → advance_warranty() → 质保期满 → EXPIRED
```

### 3.2 合同类型区分

| 合同类型 | 施工结算 | 质保逻辑 | 预算审批 | 后续处理 |
|---------|---------|---------|---------|---------|
| `PUBLIC_WORKS` | `mark_complete()`（通过 `_settle_public_works_contract()`） | `advance_warranty()` 递减质保期 | 元老院可修改预算 | 质保期满后 `EXPIRED` |
| `TAX_FARMING` | `execute_tax_collection()` | 无质保 | 不可修改预算 | 到期后 `COMPLETED` |

### 3.3 财务核算

- **国库年支出：** `base_cost // duration_years`（分期付款）
- **骑士年利润：** `expected_profit // duration_years`
- **质保期维护费：** `_annual_cost`（骑士承担，非国库支出）
- **预算修改记录：** 若元老院修改预算，`_original_budget` 保存原始值

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 项目名称和预算 | 场景配置 / 系统生成 | `project`, `budget` |
| 预算修改 | 执政官提案参数 | `modified_budget` |
| 中标者信息 | 广场竞标系统 | `winner_id`, `profit_base` |
| 配置利润率 | `game_config.json` | `profit_margin` |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 工程合同 | `state.contracts` | PUBLIC_WORKS 类型的合同对象 |
| 年付款 | `state.treasury` | 国库每年扣除施工款 |
| 年利润 | 骑士人物 | 骑士获取年利润 |
| 质保到期 | `ContractStatus.EXPIRED` | 质保期满后合同终止 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Contract` / `ContractType.PUBLIC_WORKS` | 合同实体和类型枚举 |
| `ContractStatus` | PENDING → BUDGETED → ACTIVE → COMPLETED → EXPIRED |
| `PoliticalSystem._populate_proposal("budget")` | 预算提案的数据填充 |
| `PoliticalSystem.execute_passed_proposal("budget")` | 预算通过后执行 |
| `SenateCommand._auto_generate_proposals()` | AI自主提案（含预算加成） |
| `EconomicService.collect_contract_revenues()` | 收入阶段合同结算 |
| `game_config.json::economic_rules.public_work_budget_margin_range` | AI预算加成范围配置 |

## 5. 状态与边界

### 5.1 合同状态转换

| 操作 | 前置状态 | 目标状态 |
|------|---------|---------|
| 创建 | — | PENDING |
| 元老院预算审批通过 | PENDING | BUDGETED |
| 竞标中标 | BUDGETED | ACTIVE |
| 施工完成（工期到期） | ACTIVE | COMPLETED |
| 质保期满 | COMPLETED | EXPIRED |
| 过期（未及时审批） | PENDING | EXPIRED |

### 5.2 状态准入条件

- `mark_winner()` 仅允许 `BUDGETED` 状态（`raise ValueError` 拒绝其他状态）
- `execute_works_payment()` 仅允许 `ACTIVE` 状态
- `advance_warranty()` 仅允许 `COMPLETED` 状态

### 5.3 预算修改边界

- 元老院可增加或减少预算
- 修改后 `_original_budget` 保留原始值用于审计
- 若未修改，`_original_budget` 保持为0

### 5.4 最小值边界

- 工期 `duration_years` 不能为0（默认2年）
- 预期利润不能为负数

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|---------|
| 1 | 创建公共工程合同 | 类型为 PUBLIC_WORKS，状态 PENDING，默认2年工期，20%利润率 |
| 2 | 元老院审批通过 | 状态变 BUDGETED，若修改预算则 base_cost 更新且 original_budget 保留旧值 |
| 3 | 竞标中标 | 仅 BUDGETED 可中标；标记 awarded_to、awarded_turn，状态变 ACTIVE |
| 4 | 施工付款 | 每年国库支出 base_cost/duration，状态到期变 COMPLETED |
| 5 | 质保递减 | COMPLETED 后递减 warranty_remaining，期满变 EXPIRED |
| 6 | 非 BUDGETED 合同禁止中标 | 非 BUDGETED 状态调用 mark_winner 抛出 ValueError |
| 7 | AI预算加成 | 公共工程合同自动预算加成在配置范围内随机 |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.5
- **代码入口：** `contract.py`（实体与生命周期） + `political_system.py`（预算审批） + `phase_senate.py`（元老院提案）
- **合同类型复用：** 舰队建造合同（MVP 0.5-04）复用 PUBLIC_WORKS 类型，通过 `_is_fleet_construction` 标记区分
- **与 MVP0.4-02 关系：** 共享合同实体（Contract），但质保逻辑和预算审批为公共工程独有

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-03_公共工程合同.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |
| v1.1 | 2026-07-12 | DA Sub-Agent (GLM Audit Fix) | 修复：更新 §2.5 施工结算描述，实际业务逻辑调用 `mark_complete()` 而非 `execute_works_payment()` 直接设置 COMPLETED；补充结算流程及 `mark_complete()` 方法签名 |
