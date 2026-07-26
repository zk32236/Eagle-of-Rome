# MVP0.5-01 — 国家公地系统

> **功能简述：** GameState 管理国家公地总量，支持公地分配、出售和死亡回收

## 1. 功能目的

国家公地（National Public Land）是罗马共和国的集体所有土地资源，包括行省公地和意大利本土公地。该机制管理公地的总量增减，支持三种核心操作：分地法案（将公地分配给平民）、卖地法案（贵族认购公地）和人物死亡回（私地回收为国家公地）。公地总量影响国家税收和民怨系统。

## 2. 玩家/系统行为

### 2.1 核心数据

国家公地由两个字段管理：

| 字段 | 类型 | 说明 |
|------|------|------|
| `GameState._national_public_land` | int | 国家公地总量（核心值） |
| `GameState._public_land_total` | int | 全局行省公地总和（缓存值，通过 `_update_global_public_land()` 刷新） |

意大利行省（ID=0）的公地 `land_public` 与国家公地同步：
- `sync_italy_public_land()`：将 `national_public_land` 写入 Italy 的 `_land_public`
- 每次 `add_national_public_land()` 后自动同步

### 2.2 分地法案执行（广场阶段·公示环节）

在 `ForumCommand._execute_land_distribution()` 中：

1. 获取当前 `national_public_land`
2. 从元老院通过的法案中读取 `percent`（百分比，如 0.1 表示 10%）
3. 计算 `amount = int(national_land * percent)`
4. 如果 `amount <= 0`，输出警告并跳过
5. 调用 `state.add_national_public_land(-amount)` 减少公地
6. 调用 `italy.update_land_type(0, amount)` 增加意大利私地
7. 重置意大利自上次分地以来的回合数
8. 重置意大利民怨至 0

### 2.3 卖地法案执行（广场阶段·公示环节）

在 `forum_api.resolve_forum()` 中的公地认购结算：

1. 检查 `pending_land_sale_quota`（由元老院卖地法案设置）
2. 如果有配额，处理所有 `land_purchases` 记录
3. 按人物影响力从高到低排序
4. 对每个人物：
   - 计算最大可购买量：`min(requested, remaining_quota, wealth // land_price)`
   - 实际购买后：`figure.buy_land(actual_buy, land_price)`，扣款
   - `figure.update_influence()` 重新计算影响力
   - `state.add_treasury(cost)` 国库加款
   - `state.add_national_public_land(-actual_buy)` 公地减少
5. 剩余未使用配额作废

### 2.4 死亡土地回收

在 `GameState.mark_member_dead()` 中（`transfer_land=True` 时）：

1. 读取死亡人物的 `land_private`
2. 调用 `state.add_national_public_land(land)` 将私地转为国家公地
3. 清零人物的 `land_private`
4. 控制台输出土地回收前后国家公地数量

### 2.5 状态查询

通过 `StatusPublicLandCommand`（`func_status.py`）查询：

1. 调用 `game_api.get_public_land_info()`
2. 显示国家公地总量、土地单价、总值、年税收、国库金额
3. 年税收计算：`annual_income = int(value * national_public_land_tax_rate)`

### 2.6 初始化和序列化

- 初始化：`_national_public_land = 0`（reset 后），或在 `create_for_testing()` 中从配置读取 `initial_national_public_land`
- 序列化：`to_dict()` 和 `load_from_dict()` 包含 `_national_public_land` 字段
- 加载存档后自动调用 `_update_global_public_land()` 刷新缓存

## 3. 核心规则

### 3.1 公地增减途径

| 操作 | 方向 | 触发 | 说明 |
|------|------|------|------|
| 分地法案 | 减少 → 平民私地 | 广场阶段公示结算 | 按百分比分配 |
| 卖地法案认购 | 减少 → 国库+人物私地 | 广场阶段公示结算 | 贵族按配额认购 |
| 死亡回收 | 增加 ← 人物私地 | 人物死亡时 | `mark_member_dead(transfer_land=True)` |
| 新行省征服 | 增加（行省公地） | 行省添加 | 通过 `add_province()` 自动更新 |

### 3.2 配置项

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `economic_rules.initial_national_public_land` | `1000` | 初始国家公地量（测试用） |
| `economic_rules.land_price_per_unit` | `10` | 土地单价（塔兰特/C） |
| `economic_rules.national_public_land_tax_rate` | `0.02` (2%) | 国家公地年税率 |
| `economic_rules.private_land_income_rate` | `0.05` | 私地收入率（行省税收计算用） |
| `economic_rules.province_tax_rate` | `0.1` | 行省税率 |

### 3.3 意大利本土同步机制

```
add_national_public_land(amount)
  └─> self._national_public_land += amount
  └─> sync_italy_public_land()
       └─> italy._land_public = self._national_public_land
       └─> italy.recalc_total_land()
```

### 3.4 全局公地缓存

`_update_global_public_land()`：遍历所有行省，求和 `province.land_public` 存入 `_public_land_total`。但注意：此缓存与 `_national_public_land` 是两个独立字段，`_national_public_land` 是权威值。

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 国家公地增减量 | `add_national_public_land(amount)` | 增/减公地 |
| 土地法案 | `_pending_land_acts` | 分地/卖地法案 |
| 待售公地配额 | `_pending_land_sale_quota` | 卖地法案可认购量 |
| 死亡人物土地 | `mark_member_dead(member_id)` | 土地回收 |
| 认购请求 | `_forum_pending["land_purchases"]` | 贵族认购请求 |
| 行省公地 | `Province.land_public` | 全局缓存计算 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 分地结果 | 控制台 | 显示分配数量、百分比 |
| 认购结果 | 控制台 | 显示认购数量、花费 |
| 死亡回收 | 控制台 | 显示回收前后公地 |
| 状态查询 | `game_api.get_public_land_info()` | 公地总量、价值、税收等 |
| 意大利公地同步 | `Province._land_public` | 与国家公地保持一致 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `GameState._national_public_land` | 国家公地核心字段 |
| `GameState._public_land_total` | 全局公地缓存 |
| `Province._land_public` | 行省公地（Italy 与国家同步） |
| `Province.recalc_total_land()` | 更新行省总土地 |
| `Figure._land_private` | 人物私地 |
| `Figure.buy_land()` / `sell_land()` | 土地买卖操作 |
| `ForumCommand._execute_land_distribution()` | 分地法案执行 |
| `forum_api.resolve_forum()` 公地认购逻辑 | 卖地法案执行 |
| `game_api.get_public_land_info()` | 状态查询 |
| `StatusPublicLandCommand` | 状态查询命令 |
| 配置 `economic_rules` | 价格和税率 |
| 存档系统 `to_dict()` / `load_from_dict()` | 序列化 |

## 5. 状态与边界

### 5.1 分地法案边界

- `amount = int(national_land * percent)`，百分比为 `0 ~ 1` 之间的浮点数
- 如果计算后 `amount <= 0`，跳过（公地不足）
- 分配后意大利民怨重置为 0

### 5.2 卖地认购边界

- 按影响力从高到低排序处理
- 购买量不能超过 `wealth // land_price`（资金限制）
- 购买量不能超过剩余配额
- 剩余配额作废，不清入下回合
- 每个人物按最大可购量处理

### 5.3 死亡回收边界

- 如果死亡人物无私地（`land_private == 0`），不产生任何变化
- 回收操作在 `mark_member_dead` 内部，可通过 `transfer_land=False` 关闭

### 5.4 数据一致性

- `_national_public_land` 与 Italy 的 `_land_public` 必须保持同步
- `add_national_public_land()` 自动同步
- Italy 的 `_total_land = _land_public + _land_private`，通过 `recalc_total_land()` 维护
- 存档加载后 `_public_land_total` 自动通过 `_update_global_public_land()` 刷新

### 5.5 配置默认值

- 无公地相关配置时，`get_economic_rule` 返回默认值
- `land_price_per_unit` 默认 10
- `national_public_land_tax_rate` 默认 0.02

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 查询公地信息 | 返回国家公地总量、价值、税收信息 |
| 2 | 分地法案执行 | 公地减少，意大利私地增加，民怨重置 |
| 3 | 公地不足时 | 分地跳过并输出警告 |
| 4 | 贵族认购公地 | 公地减少，国库增加，人物土地增加 |
| 5 | 公地认购财富不足 | 跳过该人物，处理下一个 |
| 6 | 无待售配额 | 认购请求被拒绝 |

## 7. 历史演化与证据

- 历史审计入口：HF-039（国家公地系统）
- 历史名称：国家公地系统
- 首次实现版本：MVP 0.5
- 演化：从 GameState 的基础字段 `_national_public_land` 逐步扩展。MVP 0.5 增加了分地法案执行和死亡土地回收，State 查询命令（`status_public_land`），序列化支持等。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-01_国家公地系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent E | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
