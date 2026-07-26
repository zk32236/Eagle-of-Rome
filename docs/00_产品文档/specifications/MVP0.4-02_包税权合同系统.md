# MVP0.4-02 — 包税权合同系统

> **功能简述：** 行省税收承包权的合同化系统，玩家以骑士身份竞标获取包税权，预付费用后在合同期内持续获得税收收益

## 1. 功能目的

在罗马共和时期，包税制（Publicani）是罗马政府将行省税收收集权外包给私人承包商（通常为骑士阶层）的制度。该功能将这一历史制度抽象为游戏内的合同系统，实现：

- 行省每年产生税收收入，政府通过拍卖将税收征收权出售给骑士
- 骑士预付费用获得包税权，在合同有效期内收取行省税收作为回报
- 增加元老院阶段的策略深度（合同需要元老院预算审批后再竞标）
- 为骑士阶层提供稳定的收益渠道

## 2. 玩家/系统行为

### 2.1 合同生成

1. 系统在回合推进过程中（如元老院阶段或收入阶段前）根据需要生成包税合同
2. 创建方式：`GameState.create_contract(ContractType.TAX_FARMING, province_id, base_cost, current_turn)`
3. 也通过 `Contract.create_tax_farming(id, province, base_cost, expected_profit)` 工厂方法创建
4. 初始状态为 `ContractStatus.PENDING`

### 2.2 元老院预算审批

1. 执政官在元老院阶段提出预算提案（`senate_api.propose`），指定待审批的合同
2. 元老院投票表决，通过后合同状态变为 `ContractStatus.BUDGETED`
3. 合同进入可竞标阶段

### 2.3 广场竞标（Forum）

1. `BUDGETED` 状态的合同在广场阶段进行公开竞标
2. 骑士人物（`class_tier == "eques"`）可参与出价：`forum_api.place_bid()`
3. 包税合同出价规则：
   - 出价金额不得低于底价（`base_cost * tax_auction_ratio`，默认80%）
   - 出价金额必须为正整数
   - 携带利润率参数 `profit_rate`
4. 竞标结算（`forum_api.resolve_forum()` / `GameState.resolve_auction()`）：出价最高者中标
5. 中标后：
   - 调用 `contract.mark_winner()` 标记中标并激活合同
   - 状态变为 `ACTIVE`，记录中标者、中标回合、利润基数

### 2.4 手动投票授予（VoteCommand）

1. 玩家通过 CLI 命令 `vote contract <ID>` 手动授予包税合同
2. 系统列出所有符合条件的骑士候选人及其财富状况
3. 玩家选择中标者，系统自动扣除骑士财富并增加国库

### 2.5 合同执行

1. 每年在收入阶段（`RevenueCommand._collect_contract_revenues()`）对 `ACTIVE` 状态的合同执行结算：
   - 调用 `execute_tax_collection()`：按年限分配预期利润
   - 每回合扣除骑士成本，计算净收入
   - 从国库向骑士支付约定金额
   - 从骑士收入中按比例（`faction_tax_rate`）扣除派系抽成
   - 合同期限到期后状态变为 `COMPLETED`

### 2.6 合同过期

1. 未经授予的 `PENDING` 合同可通过 `contract.expire()` 置为 `EXPIRED`
2. 被终止的合同通过 `contract.terminate()` 置为 `EXPIRED`

## 3. 核心规则

### 3.1 合同状态机

```
PENDING ──[元老院审批通过]──→ BUDGETED ──[竞标中标]──→ ACTIVE ──[期限届满]──→ COMPLETED
                                                                       ──[终止]──────→ EXPIRED
  │                                                                                    
  └──[直接过期]──→ EXPIRED
```

| 状态 | 含义 | 可执行操作 |
|------|------|-----------|
| PENDING | 待审批 | `expire()`, 元老院提案 |
| BUDGETED | 可竞标 | 广场出价, `mark_winner()` |
| ACTIVE | 执行中 | `execute_tax_collection()`, `terminate()` |
| COMPLETED | 已完成 | 仅查询 |
| EXPIRED | 过期/终止 | 仅查询 |

### 3.2 包税合同参数

| 参数 | 说明 | 配置来源 |
|------|------|---------|
| `base_cost` | 底价/预付金 | 根据行省税收和 `tax_auction_ratio` 计算 |
| `expected_profit` | 5年预期总利润 | 行省税收 × 合同年限 |
| `duration_years` | 合同年限（默认5年） | 配置 `tax_contract_duration` |
| `tax_auction_ratio` | 底价占年收益比例（默认80%） | 配置 `tax_auction_ratio` |
| `tax_contract_profit_rate` | 利润率（默认20%） | 配置 `tax_contract_profit_rate` |

### 3.3 竞标规则

- 出价金额 > 底价（底价 = `base_cost * tax_auction_ratio`）
- 最高出价者中标（`max(amount)`）
- 中标后直接扣除骑士财富

### 3.4 年收益结算

年收益 = `expected_profit // duration_years`

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 合同创建请求 | `game_state.create_contract()` | 传入类型、行省、底价、回合 |
| 竞标出价 | `forum_api.place_bid()` | 骑士ID、金额、利润率 |
| 投票授予 | `VoteCommand.execute()` | 用户交互式选择中标者 |
| 元老院审批 | `senate_api.propose()` | 指定待审批合同和修改预算 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 合同状态查询 | stdout / `contract_api.get_contracts_status()` | 分组显示各状态合同 |
| 竞标结果 | stdout / 玩家通知 | 中标者、金额信息 |
| 年收益 | 国库/骑士财富 | 每年在收入阶段结算 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `ContractType.TAX_FARMING` | 实体类型标记 |
| `ContractStatus` | 状态枚举（PENDING/BUDGETED/ACTIVE/COMPLETED/EXPIRED） |
| `Figure.class_tier == "eques"` | 骑士身份的判断依据 |
| `GameState._contracts_dict` | 合同存储容器 |
| `GameState.add_figure_wealth()` | 骑士财富管理 |
| `GameState.add_treasury()` | 国库管理 |
| `senate_api.propose()` / `resolve_senate()` | 元老院审批流程 |
| `forum_api.place_bid()` / `resolve_forum()` | 广场竞标流程 |
| `EconomicService.collect_contract_revenues()` | 收入阶段合同结算 |

## 5. 状态与边界

### 5.1 有效状态转换

| 源状态 | 目标状态 | 触发条件 |
|--------|---------|---------|
| PENDING | BUDGETED | 元老院审批通过 |
| PENDING | EXPIRED | 合同过期（未在有效期内审批） |
| BUDGETED | ACTIVE | 竞标中标（`mark_winner()`） |
| ACTIVE | COMPLETED | 年限届满（`mark_complete()`） |
| ACTIVE | EXPIRED | 强制终止（`terminate()`） |

### 5.2 无效操作

- 非 `PENDING` 状态的合同不能进行元老院提案
- 非 `BUDGETED` 状态的合同不能竞标
- 非 `ACTIVE` 状态的合同不能执行收益结算
- 非骑士身份的人物不能竞标包税合同
- 已授予的合同不能重复授予

### 5.3 财富不足

- 中标骑士财富必须 `>= base_cost`，否则禁止授予
- 若竞标结算时财富不足，视同流拍

### 5.4 无骑士场景

- 当游戏中没有存活骑士人物时，包税合同无法授予
- 如果没有候选人，`VoteCommand` 返回失败

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 | 测试文件 |
|---|----------|---------|---------|
| 1 | 创建包税合同 | 类型为 TAX_FARMING，状态 PENDING，正确设置 name/base_cost/profit/duration | `test_entity_contract.py::test_create_tax_farming` |
| 2 | 授予合同（award） | 状态变 ACTIVE，记录获奖者和回合，不可重复授予 | `test_entity_contract.py::test_award` |
| 3 | 多年包税收益结算 | 每年按比例累加，5年后状态 COMPLETED | `test_entity_contract.py::test_execute_tax_collection` |
| 4 | 合同过期 | PENDING 状态下 expire() 后状态变为 EXPIRED | `test_entity_contract.py::test_expire` |
| 5 | 年收益查询 | 未激活返回 0，激活后返回 `expected_profit // duration` | `test_entity_contract.py::test_get_annual_revenue` |
| 6 | mark_winner 方法 | 要求 BUDGETED 状态，设置中标者和利润基数 | `test_contract_ext.py::test_mark_winner_sets_fields_correctly` |
| 7 | 无合同状态 | 返回空结果，提示"无合同" | `test_contract_api.py::test_get_contracts_status_no_contracts` |
| 8 | 包税合同竞标出价低于底价 | 出价被拒绝，提示低于底价 | `test_func_contracts.py::test_manual_bid_invalid_amount` |
| 9 | 投票授予包税合同 | 选择候选人后成功授予，扣财富+加国库 | `test_func_contracts.py::test_vote_success` |
| 10 | 投票授予时骑士财富不足 | 禁止授予，提示不可支付 | `test_func_contracts.py::test_vote_cannot_afford` |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.4 (~2025)
- **初始实现：** Contract 实体 + ContractType.TAX_FARMING + 基础 award/execute 流程
- **MVP 0.5 扩展：** 新增 BUDGETED 状态、`mark_winner()` 流程、竞标字段、完整的元老院预算审批 → 广场竞标 → 收入结算链路
- **MVP 0.7 扩展：** 舰队建造合同复用 PUBLIC_WORKS 类型，包税权合同系统本身未做更改
- **代码入口：** `contract.py` (实体定义) + `func_contracts.py` (命令) + `contract_api.py` (API)
- **测试覆盖：** 包含实体单元测试、API 测试、命令测试、资金流集成测试

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.4-02_包税权合同系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent G | 初版创建 |
