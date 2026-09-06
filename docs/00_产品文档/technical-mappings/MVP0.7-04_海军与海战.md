# MVP0.7-04 — 海军与海战-P0（技术映射）

## 1. 代码目录
```
src/core/systems/naval_system.py  # 海军系统核心
src/core/entities/fleet.py         # Fleet 实体 + FleetStatus
src/ui/commands/phase_combat.py    # 海战集成
src/core/entities/contract.py      # 舰队建造合同
```

## 2. 核心方法
- `resolve_naval_battle()` — 海战判定（canonical 海军门；罗马方战力**消费 package 聚合器**
  `get_fleet_strength_breakdown`，R3-G-04 §4.2，不再 sum per-fleet int）
- `generate_construction_contracts()` — 建造合同生成
- `generate_replacement_contracts()` — 补充合同（**nominal**，禁 `get_combat_strength` 作源；R3 §4.3）
- `assign_fleet_to_war()` — 指派舰队
- `combat_api._war_card` / `gui_query_api._war_summary` — 强度读模型字段
  （`assigned_fleet_ids`/nominal/quality_adjusted_base/experience/commander/effective，同集合；
  `assigned_fleet_count`/`naval_ready` 语义不变，R3 §5.2.1）

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-09-05 | R3-G-04 同步：package 聚合消费 + nominal replacement + strength DTO 字段（DA-R3-B3） |
| v1.0 | 2026-07-12 | 初版 |
