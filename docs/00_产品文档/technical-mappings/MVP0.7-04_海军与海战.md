# MVP0.7-04 — 海军与海战-P0（技术映射）

## 1. 代码目录
```
src/core/systems/naval_system.py  # 海军系统核心
src/core/entities/fleet.py         # Fleet 实体 + FleetStatus
src/ui/commands/phase_combat.py    # 海战集成
src/core/entities/contract.py      # 舰队建造合同
```

## 2. 核心方法
- `resolve_naval_battle()` — 海战判定
- `generate_construction_contracts()` — 建造合同生成
- `assign_fleet_to_war()` — 指派舰队

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
