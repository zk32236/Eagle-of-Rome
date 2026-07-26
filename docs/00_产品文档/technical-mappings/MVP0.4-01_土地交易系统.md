# MVP0.4-01 — 土地交易系统 Technical Mapping

## 1. 代码目录
```
src/core/service/land_trading_service.py  # 土地交易核心 (189行)
src/ui/commands/func_land.py              # CLI 命令 (98行)
```

## 2. 关键类
- `LandTradingService` — calculate_land_price(), execute_trade(), get_trade_preview()
- `TradeCommand` / `LandCommand` — CLI 命令入口

## 3. 核心规则
价格 = BASE_LAND_PRICE × (1 + 卖方溢价 - 买方折扣)，范围 [5, 20]

## 4. 版本日志
| v1.0 | 2026-07-12 | 初版 |
