# MVP0.5-06 — 派系资金抽成系统（技术映射）

## 1. 代码目录
```
src/core/service/economic_service.py  # 核心抽成逻辑
src/core/entities/entities.py         # Faction.treasury
src/core/game_state.py                # add_faction_treasury()
```

## 2. 关键方法
- `settle_revenue_phase()` — 收入结算入口
- `collect_private_land_income()` — 私地抽成
- `collect_contract_revenues()` — 合同抽成
- `apply_faction_income()` — 派系收入结算

## 3. 核心规则
税率: faction_tax_rate = 0.1 (10%)
拨款: faction_stipend = 5 (JSON配置)

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-29 | WP-F 003（弱触发）：`faction_style_map` 键名纠正说明——config 键 = 权威 faction_id 全名（optimates/populares/equites + 占位 f4/f5/f6）；语义不变（键 → 色族 → GUI 展示名映射链不变）；三族色族 F-02（RED/BLUE/ORANGE） |
| v1.0 | 2026-07-12 | 初版 |
