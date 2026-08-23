# MVP0.5-10 — 土地法案（分地/买地）

> **功能简述：** 元老院阶段提出土地法案，将公地分给公民或出售公地

## 1. 功能目的

土地法案是罗马共和国政治经济斗争的核心机制。平民派（Populares）可通过元老院提出**公地分配法案（平民分地）**，将国家公地分配给罗马公民；贵族派（Optimates）可提出**公地出售法案（贵族买地）**，促进贵族资本购买国家公地。

此机制确保：
1. 派系可通过元老院程序提出土地法案
2. 法案经元老院投票表决、保民官否决审查后方可执行
3. 通过的法案在实际执行阶段（广场阶段/收入阶段）生效

## 2. 玩家/系统行为

### 2.1 触发时机

土地法案在**元老院阶段（Senate Phase）**中作为提案类型之一提出。由 `SenateCommand` 在 Step 1（提案环节）中处理。

### 2.2 法案类型

支持两种土地法案类型：

| 类型 | 标识符 | 说明 |
|------|--------|------|
| 公地分配法案 | `distribution` | 平民分地：将国家公地按比例分配给罗马公民 |
| 公地出售法案 | `sale` | 贵族买地：将国家公地按比例挂牌出售 |

### 2.3 自动提案生成（AI/自动模式）

在 `SenateCommand._auto_generate_proposals()` 中：

1. 遍历所有活跃派系
2. 对每个派系，调用所有注册的 `LandProposalDecider` 决策器
3. 每个决策器返回 `(act_type, percent)` 元组或 `None`
4. 对非 `None` 的结果，调用 `senate_api.propose()` 提交土地法案提案
5. 成功提案通过日志记录描述信息

默认注册的决策器：
- `AutoLandProposalDecider("populares", "distribution")` — 平民派提交分地法案
- `AutoLandProposalDecider("optimates", "sale")` — 贵族派提交卖地法案

### 2.4 手动提案（玩家模式）

玩家（执政官玩家）在提案环节输入 `propose B<ID> <百分比>`：

```
propose B05 0.05   # 公地出售法案，出售 5% 国家公地
propose B06 0.06   # 公地分配法案，分配 6% 国家公地
```

- 百分比为**小数**格式（如 0.05 表示 5%）
- 提案 ID 根据当前可选提案动态分配（`self._proposals_map`）
- `propose` 命令调用 `senate_api.propose()` 发起提案

### 2.5 投票表决

土地法案与其他提案类型一起进入 Step 2（表决环节）：
1. 各派系按影响力权重投票
2. `SenateVoteDecider.decide_vote()` 决定派系投票倾向
3. 支持率 > 50% 的提案通过
4. 通过标准：`support_influence / total_influence > 0.5`

### 2.6 保民官否决

通过表决的提案进入 Step 4（否决环节）：
1. 保民官（Tribune）可行使否决权
2. 使用 `TribuneVoteDecider.decide_veto()` 决定是否否决
3. 被否决的提案标记为否决，不执行

### 2.7 法案执行

最终通过的法案在 `PoliticalSystem.resolve_senate()` → `execute_passed_proposal()` 中执行：

**公地出售法案（`sale`）：**
```python
amount = int(national_land * percent)
state.set_pending_land_sale_quota(amount)
```
- 计算待出售公地数量：`amount = int(national_public_land × percent)`
- 通过 `GameState.set_pending_land_sale_quota()` 存储出售配额
- 出售配额在广场阶段（Forum Phase）供贵族玩家购买

**公地分配法案（`distribution`）：**
```python
amount = int(national_land * percent)
state.add_pending_land_act({
    "type": "distribution",
    "percent": percent,
    "amount": amount,
    "description": "平民分地法案..."
})
```
- 计算待分配公地数量：`amount = int(national_public_land × percent)`
- 通过 `GameState.add_pending_land_act()` 存储分地法案
- 分地法案在收入阶段（Revenue Phase）由 `EconomicService` 执行分配

### 2.8 多次执行防护

- `is_phase_executed("senate")` 检查：元老院阶段已执行则跳过
- `clear_senate_pending()` 清空上一回合的提案记录

## 3. 自动决策器逻辑

### 3.1 AutoLandProposalDecider

**构造函数参数：**
- `target_faction`：目标派系 ID，如 `populares` 或 `optimates`
- `proposal_type`：法案类型，`distribution` 或 `sale`

**决策流程：**
1. 检查当前派系 ID 是否等于 `target_faction`，不匹配则返回 `None`
2. 从配置读取 `political_rules.land_proposal.{proposal_type}_chance`（默认 `0.3` = 30%）
3. 随机判断是否触发提案（`random.random() >= chance` 时返回 `None`）
4. 从配置读取比例范围：
   - `land_percent_min`：默认 `0.05`（5%）
   - `land_percent_max`：默认 `0.10`（10%）
5. 在范围内随机生成百分比
6. 返回 `(proposal_type, percent)`

**配置键：**

| 配置路径 | 默认值 | 说明 |
|---------|--------|------|
| `political_rules.land_proposal.distribution_chance` | `0.3` | 分地法案提案概率 |
| `political_rules.land_proposal.sale_chance` | `0.3` | 卖地法案提案概率 |
| `political_rules.land_proposal.land_percent_min` | `0.05` | 最小比例（5%） |
| `political_rules.land_proposal.land_percent_max` | `0.10` | 最大比例（10%） |

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 活跃派系列表 | `GameState.get_active_factions()` | 决定哪些派系可提交土地法案 |
| 国家公地总量 | `GameState.get_national_public_land()` | 用于计算实际处置公地数量 |
| 土地法案配置 | `Config.get("political_rules.land_proposal")` | 概率和比例范围 |
| 提案记录 | `GameState.get_senate_proposals()` | 已提交的提案列表 |
| 派系投票记录 | `GameState.get_senate_votes_copy()` | 各派系投票结果 |
| 保民官否决记录 | `GameState.get_senate_vetoes_copy()` | 被否决的提案 ID |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 待出售公地配额 | `GameState._pending_land_sale_quota` | 卖地法案通过后设置 |
| 待执行分地法案 | `GameState._pending_land_acts` | 分地法案通过后追加 |
| 元老院结算结果 | `PoliticalSystem.resolve_senate()` 返回值 | 包含 passed/rejected 提案信息 |
| 日志 | 文件日志 + 内存日志 | 提案、投票、否决、执行全程记录 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `SenateCommand` | 元老院阶段主控命令 |
| `LandProposalDecider` | 土地法案决策器抽象基类 |
| `AutoLandProposalDecider` | 默认自动决策器实现 |
| `SenateVoteDecider` | 元老院投票决策器 |
| `TribuneVoteDecider` | 保民官否决决策器 |
| `PoliticalSystem.resolve_senate()` | 元老院结算逻辑 |
| `GameState.set_pending_land_sale_quota()` | 设置卖地配额 |
| `GameState.add_pending_land_act()` | 追加分地法案 |
| `GameState.get_national_public_land()` | 获取国家公地总量 |
| `Config` | 配置读取 |

## 5. 状态与边界

### 5.1 正常流程

1. 元老院阶段开始 → 提案环节 → 表决环节 → 否决环节 → 宣布环节
2. 通过的土地法案被记录为待执行状态
3. 对应执行阶段（广场/收入）处理具体执行

### 5.2 边界情况

| 场景 | 处理 |
|------|------|
| 国家公地为 0 | `amount = int(0 × percent) = 0`，卖地/分地均无实质效果 |
| 百分比极小 | `amount` 通过 `int()` 截断，极小比例可能导致 `amount = 0` |
| 已有同类型未决提案 | `SenateCommand._handle_propose()` 对 war/budget/peace/governor 类型做重复检查；land 类型暂未实现重复防护，手动模式下同一土地法案类型可被多次提交 |
| 保民官否决已通过法案 | 法案被标记为否决，不执行，不移入待执行列表 |
| 自动模式下无执政官 | 打印警告"⚠️ 没有执政官，无法进行提案"，跳过提案环节 |
| 手动模式无执政官 | 返回警告，跳过提案环节 |

### 5.3 多派系

- 每个派系都可触发土地法案提案（由注册的决策器决定）
- 默认配置：Populares 派系提出分地法案，Optimates 派系提出卖地法案
- 投票按派系影响力加权计算

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 自动模式下土地法案提案生成 | Populares 派系在概率触发时提交分地法案，Optimates 派系提交卖地法案 |
| 2 | 土地法案通过表决 | 支持率 > 50%，法案进入待执行列表 |
| 3 | 土地法案被保民官否决 | 法案被标记否决，不进入待执行列表 |
| 4 | 卖地法案执行 | 设置 `pending_land_sale_quota = int(national_land × percent)` |
| 5 | 分地法案执行 | `pending_land_acts` 中追加分地记录 |
| 6 | 手动提案：propose B05 0.05 | 提交公地出售法案，比例 5% |
| 7 | 手动提案：propose B06 0.06 | 提交公地分配法案，比例 6% |

## 7. 历史演化

- 首次实现版本：MVP 0.5
- 后续集成：MVP 0.7 元老院重建中作为标准提案类型之一
- 相关演化：土地法案执行与广场阶段（Forum Phase）土地交易联动

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-10_土地法案.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-08-23 | DA-Exec (WP-E Slice 11 PU-04) | 新增 §10：sale 法案并行写入 turn_land_sale_total（同 tech 映射 v1.3，GUI-BETA-011） |
| v1.1 | 2026-07-13 | Audit Subagent (DS) | 修正5.2边界情况：land类型手动提案无重复检查（与代码一致） |
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。

## 10. WP-E 更新（2026-08-23）

- **sale 法案双写入**：`political_system.py:510` 执行 sale 时并行 `set_pending_land_sale_quota(amount_C)` +
  `set_turn_land_sale_total(amount_C)`（同一 amount_C 权威值零换算）——quota 供 Forum resolve 消费
  （remaining），total 供本年度展示（贯穿 resolve 稳定，次年清除）。
