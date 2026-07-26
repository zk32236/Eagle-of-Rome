# MVP0.4-01 — 土地交易系统

> **功能简述：** 人物间的私人土地买卖系统，支持价格计算预览与执行

## 1. 功能目的

为罗马式经济博弈提供土地再分配机制。人物（元老、骑士）之间可以通过交易直接买卖土地，影响各自的土地私地数额、派系总土地以及个人影响力。土地交易系统构成派系经济竞争的重要工具。

## 2. 玩家/系统行为

### 2.1 系统行为

1. 系统在任意时刻接受 `trade land` 或 `land price` 指令（CLI 命令层）
2. `land price` 指令：接收卖家 ID、买家 ID，调用 `LandTradingService.get_trade_preview()` 计算预览
3. `trade land` 指令：接收卖家 ID、买家 ID、数量，调用 `LandTradingService.execute_trade()` 执行交易
4. 交易执行包含以下步骤：
   - 验证买卖双方存在且存活
   - 验证卖家土地充足
   - 验证买家资金充足
   - 执行卖家售地（`Figure.sell_land()`）
   - 执行买家购地（`Figure.buy_land()`），失败则回滚卖家
   - 更新双方影响力（`update_influence()`）
   - 更新双方所属派系总土地（`faction.update_total_land()`）
   - 记录交易历史到卖家 `land_trade_history`
   - 打印交易结果

### 2.2 玩家行为

1. 玩家通过 CLI 命令发起土地交易
2. `trade land <卖家ID> <买家ID> <数量>` — 执行交易（子命令 `land`）
3. `land price <卖家ID> <买家ID>` — 预览单价（子命令 `price`）
4. `land price` 仅预览 1 单位土地的价格；玩家可自行计算多单位总价

### 2.3 异常场景

| 场景 | 系统行为 |
|------|----------|
| 人物不存在或已死亡 | 返回错误消息 `"Figure not found"` 或 `"Deceased figure cannot trade"` |
| 买卖双方为同一人 | 返回错误 `"Cannot trade with yourself"` |
| 数量 <= 0 | 返回错误 `"Invalid amount"` |
| 卖家土地不足 | 返回 `"<卖家名> has insufficient land (<持有> < <需求>)"` |
| 买家资金不足 | 返回 `"<买家名> cannot afford <总价> <货币单位> (has <持有>)"` |
| 执行过程异常 | 捕获异常，调用 `state.log_exception()` 记录，返回 `"Internal error during trade: <异常>"` |

## 3. 核心规则

### 3.1 土地价格计算

基本公式：
```
价格 = BASE_LAND_PRICE × (1 + 卖方溢价 - 买方折扣)
```

| 因素 | 条件 | 修正值 |
|------|------|--------|
| 卖方人气优势 | `seller.popularity >= buyer.popularity` | +0.20 |
| 卖方影响力优势 | `seller.influence >= buyer.influence` | +0.10 |
| 买方人气折扣 | `buyer.popularity >= 10` | -0.10 |
| 同派系折扣 | `seller.faction_id == buyer.faction_id` | -0.20 |
| 敌对派系溢价 | 派系关系为 hostile | +0.30 |

价格限定范围：`[0.5 × BASE_LAND_PRICE, 2.0 × BASE_LAND_PRICE]`

### 3.2 基础价格常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `BASE_LAND_PRICE` | 10 | 基础土地价格，单位：塔兰特/单位土地 |

### 3.3 派系关系

当前 MVP 简化实现，`_get_faction_relation()` 始终返回 `"neutral"`（预留为 future work）。

### 3.4 交易后数据更新

执行成功的交易将触发：
1. **卖家：** 土地减少 `amount`，财富增加 `amount × price_per_unit`
2. **买家：** 土地增加 `amount`，财富减少 `amount × price_per_unit`
3. **双方影响力：** 调用 `update_influence()` 重新计算
4. **派系总土地：** 卖方派系更新；买卖方不同派系时，买方派系也更新
5. **交易历史：** 卖家 `land_trade_history` 列表追加记录（含回合号、双方 ID、数量、单价、总价）

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 卖家 ID | CLI 参数（整数） | 人物实体 ID |
| 买家 ID | CLI 参数（整数） | 人物实体 ID |
| 交易数量 | CLI 参数（整数） | 正数 |
| 单价（可选） | CLI 参数或自动计算 | 默认调用 `calculate_land_price()` |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 交易结果消息 | 控制台 | 成功：显示双方土地变化；失败：显示错误消息 |
| `land price 预览` | 控制台 | 单价 + 示例（5 单位总价） |
| 交易历史 | `seller.land_trade_history` | 卖家对象属性追加记录 |
| 异常日志 | `state.log_exception()` | 异常时记录详细上下文 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `GameState.get_member()` | 获取人物实体 |
| `Figure.sell_land()` / `Figure.buy_land()` | 执行土地增减（含财富变更） |
| `Figure.update_influence()` | 交易后更新影响力 |
| `Faction.update_total_land()` | 更新派系总土地 |
| `Faction.get_members()` | 获取派系成员列表 |
| `TerminologyService` | 获取货币单位等术语 |

## 5. 状态与边界

### 5.1 合法交易条件

- 买卖双方均为存活人物，不可为同一人
- 卖家土地 >= 交易数量（`land_private >= amount`）
- 买家财富 >= 总价（`wealth >= amount × price_per_unit`）

### 5.2 边界值

| 条件 | 结果 |
|------|------|
| `amount` = 1 | 最小单位交易 |
| 单价下限 5 | 修改范围为 `max(0.5 × base, min(2.0 × base))`，即最低 5 塔兰特 |
| 单价上限 20 | 最高 20 塔兰特 |
| 同派系买家 | 享 20% 折扣，价格更低 |

### 5.3 回滚机制

如果 `buyer.buy_land()` 失败，系统会调用 `seller.buy_land(amount, price_per_unit)` 回滚卖家资产，确保数据一致性。

### 5.4 交易历史

记录格式（`seller.land_trade_history` 列表）：

```python
{
    "turn": int,           # 回合号
    "seller_id": int,      # 卖家 ID
    "buyer_id": int,       # 买家 ID
    "amount": int,         # 数量
    "price_per_unit": int, # 单价
    "total_value": int     # 总价
}
```

交易历史仅记录在卖家侧。不存在买家侧交易历史记录。

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | `trade land 1 2 5`（合法） | 执行成功，返回 True |
| 2 | `trade land`（缺参数） | 返回 `❌ 用法: trade land <卖家ID> <买家ID> <数量>`，返回 False |
| 3 | `trade sell 1 2 5`（子命令错误） | 返回 False |
| 4 | `trade land abc 2 5`（ID 非整数） | 返回 False |
| 5 | `trade land 1 2 0`（非正数量） | 返回 False |
| 6 | `trade land 1 2 -5`（负数） | 返回 False |
| 7 | `trade land 1 2 5`（执行失败） | 返回 False，显示错误消息 |
| 8 | `land price 1 2` | 预览成功，返回 True |
| 9 | `land price abc 2`（ID 非整数） | 返回 False |
| 10 | `land price 1 2`（预览返回 None） | 返回 False |

## 7. 历史演化与证据

- 首次实现版本：MVP 0.4 (~2025)
- 核心代码：`land_trading_service.py` (189行)
- CLI 包装：`func_land.py` (98行)
- 测试：`test_func_land.py`（12 个测试用例）
- 类注释标明版本为 "MVP 0.4.4"

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.4-01_土地交易系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent F | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
