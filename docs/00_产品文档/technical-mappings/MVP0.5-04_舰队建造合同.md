# MVP0.5-04 — 舰队建造合同（技术映射）

## 1. 代码目录
```
src/core/entities/contract.py    # 合同扩展字段
src/core/entities/fleet.py       # Fleet 实体
src/core/systems/naval_system.py # 海军系统
```

## 2. 关键方法
- `generate_construction_contracts()` — 生成建造合同（A 基线 `_original_budget=total_budget` 一次冻结；
  composition 存 nominal 快照，R3）
- `generate_replacement_contracts()` — 补充合同（**nominal 唯一权威**：required/usable/committed_building/
  committed_pending 全 nominal；禁 `get_combat_strength` 作 replacement 源，R3 §4.3）
- `on_contract_awarded()` — 中标后建造（固化 C/D + `_construction_package_id=contract.id`；逐舰快照
  `_nominal_strength_base` + `q=D/A` 精确整数比；不再 per-fleet round/floor，R3）
- `process_fleet_construction()` — 建造完成检查
- `get_fleet_strength_breakdown(fleets)` — [NEW R3] 只读 package 聚合器（raw→upper-cap→round 一次）
- `Fleet.get_combat_strength()` — 兼容单舰查询（有效贡献 + 原 modifiers）；禁作海战聚合/补充源

## 2.1 持久字段链（R3，2026-09-05）
```
Contract A/B/C/D（_original_budget/_approved_budget/_contract_price/_actual_cost + _target_war_id/
_fleet_type/_build_time）→ Senate PASS（Fleet 分支写 B、冻结 A，political_system）
→ Forum place_bid 8 元组（C + 显式 construction_cost=D；admission 守卫）→ resolve_forum award 固化
（失效候选过滤 → 最低价 → 平手；不重放 current-player guard）
→ NavalSystem on_contract_awarded 物化 BUILDING（nominal/quality/package 落盘）
→ Fleet/Contract serializer roundtrip → combat_api/gui_query_api DTO → SessionStore → CombatStage

legacy 边界：旧存档 B 不可恢复 → approved_budget=None + authority_source=legacy_unknown（禁伪造 350）；
已烘焙强度 → legacy_baked_quality（不还原 240/280）；缺省不创造 target
```

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-09-05 | R3-G-03/04 同步：四权威持久链 + nominal replacement + package 聚合器 + legacy 边界（DA-R3-B3） |
| v1.0 | 2026-07-12 | 初版 |
