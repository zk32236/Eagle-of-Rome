# MVP0.5-04 — 舰队建造合同（技术映射）

## 1. 代码目录
```
src/core/entities/contract.py    # 合同扩展字段
src/core/entities/fleet.py       # Fleet 实体
src/core/systems/naval_system.py # 海军系统
```

## 2. 关键方法
- `generate_construction_contracts()` — 生成建造合同
- `on_contract_awarded()` — 中标后建造
- `process_fleet_construction()` — 建造完成检查

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
