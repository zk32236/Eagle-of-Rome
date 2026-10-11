# MVP0.5-12-sys — 决策器框架（技术映射）

## 1. 代码目录
```
src/core/deciders/           # 15个抽象基类 (309行)
src/core/deciders/impl/      # 15个自动实现 (892行)
src/core/deciders/manual_*   # 5个手动骨架 (75行)
```

## 2. 决策器清单（15个）
vote, bid, land_proposal, land_trade, peace_treaty, budget, festival, recruitment, retirement, triumph, tribune_veto, senate_vote, war, war_takeover, fleet_disband

## 3. WP-K S2/S3 注记（2026-10-11，DA-Execute）

> 权威：SA-Development-Task-WP-K-v1.4（FC-K-10…22；FC-K-30）；对应规格 `specifications/MVP0.5-12-sys_决策器框架.md` §3.2/§7。

- `src/core/deciders/impl/auto_bid_decider.py`：`decide_fleet_bid` / `decide_tax_bid` /
  `decide_works_bid` 的折扣·利润率/加价率区间读 config（`state.get_economic_rule`；缺键回退现状字面量）：
  - fleet/works 折扣 = `project_bid_discount_min/max`；利润率 = `project_bid_profit_rate_min/max`；
  - tax 加价 = `tax_bid_increment_min/max`（单 draw；加价语义）。
- works 折扣（定 C）与利润率（定 D）为**两次独立 draw**（解耦）；返回 5 元组第 3 项 = `profit_rate`。
- 键同步登记于 `data/config/game_config.json` + `src/core/config.py DEFAULTS`。

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.1 | 2026-10-11 | WP-K S2/S3：竞价折扣·利润率/加价率 config 化 + works 解耦 |
| v1.0 | 2026-07-13 | 初版 |
