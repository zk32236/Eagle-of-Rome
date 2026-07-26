# MVP0.5-06 — 派系资金抽成系统

> **功能简述：** 派系从所属元老收入中按比例抽取资金的自动抽成机制

## 1. 功能目的

派系资金抽成系统是罗马共和国政治经济的基础机制之一。派系需要资金来维持其政治运作（如竞选拨款、广场竞标等）。此机制确保：

1. 派系从所属元老（Senator/Figure）的私人收入中按比例自动抽取部分收入作为派系金库资金
2. 每个派系每回合获得一笔固定财政拨款（Stipend）
3. 抽成动作在收入阶段（Revenue Phase）自动执行，无需玩家干预

## 2. 玩家/系统行为

### 2.1 触发时机

派系抽成在 **收入阶段（Revenue Phase）** 中自动触发，由 `EconomicService.settle_revenue_phase()` 统一调度。

### 2.2 抽成数据初始化

在收入阶段的开始，系统初始化两个映射表：

```python
faction_tax_collected: Dict[str, float]  # 派系ID → 累计税赋金额（浮点数）
faction_stipend: Dict[str, int]          # 派系ID → 固定财政拨款
```

- 每个活跃派系获得一个 `faction_stipend` 值（从配置 `economic_rules.faction_stipend` 读取）
- 每个活跃派系的 `faction_tax_collected` 初始化为 `0.0`
- 税率为 `economic_rules.faction_tax_rate`（默认 0.1，即 10%）

### 2.3 私地收入抽成

在 `EconomicService.collect_private_land_income()` 中：

1. 遍历所有存活人物（Figure）
2. 对有私地（`land_private > 0`）的人物计算私地收入：
   - `income_float = land_private × land_price_per_unit × private_land_income_rate`
   - 默认：`land_price_per_unit = 10`，`private_land_income_rate = 0.05`
3. 对收入征收派系税：
   - `tax_float = income_float × faction_tax_rate`（默认 10%）
   - `net_income = int(round(income_float - tax_float))`
4. 人物获得净收入（累加到 `figure.wealth`）
5. 税费累加到所属派系的 `faction_tax_collected[faction_id]` 中

### 2.4 合同收入抽成

在 `EconomicService.collect_contract_revenues()` 中，对状态为 `ACTIVE` 的活跃合同：

**包税合同（TAX_FARMING）：**
1. 计算毛利润：`gross_profit = contract_price × profit_rate`
2. 征收派系税：`tax_float = gross_profit × faction_tax_rate`
3. 骑士净得：`net_profit = gross_profit - tax_int`
4. 国库收到合同价（`contract_price`），骑士获得净利
5. 税费累加到骑士所属派系的 `faction_tax_collected` 中

**工程合同（PUBLIC_WORKS）：**
1. 每期支付：`payment = contract.base_cost - contract.total_spent`（最后一期）或 `annual_income`
2. 成本：`cost = annual_cost`
3. 利润：`profit_float = payment - cost`
4. 利润 > 0 时征税：`tax_float = profit_float × faction_tax_rate`
5. 骑士净得：`knight_net_gain = int(round(profit_float - tax_float))`
6. 税费累加到骑士所属派系

### 2.5 派系收入结算

在 `EconomicService.apply_faction_income()` 中：

1. 遍历所有派系，计算每个派系的总收入：
   - `treasury_add = stipend + tax_int`
2. 调用 `GameState.add_faction_treasury(faction_id, treasury_add)` 更新派系金库
3. 日志记录两项：
   - `faction_tax`：记录派系抽成金额
   - `faction_stipend`：记录派系财政拨款
4. 返回每派系的结算详情 `{"stipend": N, "tax": N, "final": N}`

### 2.6 UI 展示

在收入阶段的 UI 层（`RevenueCommand._print_faction_table()`）中：
1. 按派系名称排序展示所有活跃派系
2. 三行数据展示：
   - 「财政拨款」：固定津贴（Stipend）
   - 「会员贡献」：成员抽成总额（Tax）
   - 「现有资金」：结算后派系资金余额（Final Treasury）

## 3. 核心规则

### 3.1 抽成比例

| 配置键 | 默认值（config.py） | 实际值（game_config.json） | 说明 |
|--------|-------------------|--------------------------|------|
| `economic_rules.faction_tax_rate` | `0.1` (10%) | `0.1` (10%) | 从成员收入中抽成的比例 |
| `economic_rules.faction_stipend` | `10` | `5` | 每回合固定财政拨款 |

### 3.2 私地收入计算

```
private_income = land_private × land_price_per_unit × private_land_income_rate
faction_tax = private_income × faction_tax_rate
figure_net = int(round(private_income - faction_tax))
```

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `land_price_per_unit` | `10` | 每单位土地价格 |
| `private_land_income_rate` | `0.05` | 私地收入率 |

### 3.3 包税合同收入计算

```
gross_profit = contract_price × profit_rate
faction_tax = int(round(gross_profit × 0.1))
knight_net = gross_profit - faction_tax
treasury_income = contract_price
```

### 3.4 工程合同收入计算

```
per_period_payment = annual_income（通常）或 base_cost - total_spent（最后一期）
per_period_cost = annual_cost
profit = per_period_payment - per_period_cost
faction_tax = int(round(profit × 0.1))  （仅 profit > 0 时）
knight_net = int(round(profit - tax_float))
```

### 3.5 派系资金

- 每个 Faction 拥有 `treasury: int` 字段
- 初始值：`economic_rules.faction_initial_treasury`（默认 10）
- 通过 `GameState.add_faction_treasury(faction_id, amount)` 统一操作

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 存活人物列表 | `GameState.get_living_members()` | 遍历所有存活人物 |
| 人物私地 | `Figure._land_private` | 用于计算私地收入 |
| 活跃合同列表 | `GameState.get_all_contracts()` | 筛选 `ACTIVE` 状态的合同 |
| 税率 | `Config.get("economic_rules.faction_tax_rate")` | 默认 0.1 |
| 财政拨款 | `Config.get("economic_rules.faction_stipend")` | 默认 5（JSON）/ 10（代码） |
| 活跃派系 | `GameState.factions` | 所有注册派系 |
| 天命事件 | `GameState.active_events` | 丰收/灾难影响收入计算 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 派系金库更新 | 各 `Faction.treasury` 字段 | 直接修改派系资金 |
| 人物财富更新 | `Figure.wealth` 字段 | 网收入累加到人物财富 |
| 收入阶段结算 | `settle_revenue_phase()` 返回字典 | 包含 `faction_rows` 等数据 |
| UI 展示 | 控制台输出 | 「派系金库收益」表格 |
| 日志 | 文件日志 + 内存日志 | `faction_tax` / `faction_stipend` 事件 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Faction.treasury` | 派系资金存储字段 |
| `Figure.wealth` | 人物财富字段，用于接收净收入 |
| `GameState.add_faction_treasury()` | 派系资金管理方法 |
| `GameState.add_figure_wealth()` | 人物财富管理方法 |
| `EconomicService` | 收入阶段结算服务 |
| `RevenueCommand` | UI 层输出命令 |
| `Contract.contract_price` / `profit_rate` | 包税合同利润计算 |
| `Config` / `GameState.get_economic_rule()` | 配置读取 |

## 5. 状态与边界

### 5.1 正常流程

- 收入阶段已执行则跳过（`is_phase_executed("revenue")` 检查）
- 所有活跃派系获得财政拨款 + 抽成
- 无人物的派系仍获得财政拨款

### 5.2 边界情况

| 场景 | 处理 |
|------|------|
| 无存活人物 | 派系仍获得财政拨款，抽成为 0 |
| 人物无私地（land_private ≤ 0） | 跳过私地收入计算 |
| 合同骑士已死亡 | 合同终止（terminate），解除行省绑定 |
| 人物无隶属派系（faction_id 为空） | 触发放置不到 `faction_tax_collected` 中的检查，税费不会累积 |
| 天命事件影响 | 丰收（bumper_harvest）使用乘数，灾难（disaster）减少收入 |
| 派系 ID 不存在于初始化的映射中 | `faction_tax_collected[fig.faction_id]` 通过 `in` 检查跳过 |

### 5.3 多派系

- 所有派系独立结算
- 私地收入按人物所属派系分别累计
- 合同收入按中标骑士所属派系分别累计

### 5.4 多合同

- 同一骑士可持有多个合同
- 每个合同独立结算、独立征税
- 税费统一累加到骑士所属派系

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 私地收入抽成：人物有私地 10 单位，税率 10% | 人物净得 4，派系税累计 0.5，私地收入行正确返回 |
| 2 | 派系拨款：每派系获得固定财政拨款 | `faction_stipend` 值正确（配置 5/默认 10） |
| 3 | 派系税收分配：人物和合同的税收正确分配到所属派系 | `faction_tax_collected[faction_id]` 正确累加 |
| 4 | 收入阶段成功执行完整流程 | 国库、人物财富、派系金库全部正确更新 |
| 5 | 多次执行防护：收入阶段已执行则跳过 | 返回 False |

## 7. 历史演化与证据

- 历史审计入口：HF-030（派系资金抽成）
- 历史名称：派系资金抽成系统
- 首次实现版本：MVP 0.5
- 演化：初始在 MVP 0.5 的核心抽成逻辑。扩展了私地收入抽成、合同收入抽成和财政拨款三部分。Config 默认值与 JSON 配置值有分化（stipend 代码默认 10，JSON 配置 5）。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-06_派系资金抽成系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent I | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
