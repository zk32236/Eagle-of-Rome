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

## WP-L L1 同步注记（2026-10-02，DA-Execute；append-only）

> 权威：SA-Development-Task WP-L L1 v1.1（`a74489cb…`）§3 FC-L1-11/12；规格 `specifications/MVP0.5-04_舰队建造合同.md` §5.2.1。

- **强度展示契约（FC-L1-11 / ODR-L-03）**：界面显示的折算实际战力**必须等于**权威读模型字段
  （`get_war_fleet_strength_read_model(...).fleet_quality_adjusted_base` / `fleet_effective_combat_strength`）；
  QML 只渲染不重算（禁第二套经济真值）；**展示面 = 战争卡 post-build（唯一）**，竞标对话框预览行按 G2 ③ 撤回。
- **单入队点 parity（FC-L1-12）**：GUI/CLI/AI/API 均经 `forum_api.place_bid` 单点入队；GUI 可传显式 D，
  CLI/AI 用 rate 派生路径（ODR-L-04 不变）；无第二经济真值。
- **四权威推广（WP-L L1）**：A/B/C/D + 显式 D + quality=D/A 现统一适用于全部 PUBLIC_WORKS（含普通公共工程，
  见 MVP0.5-03 §2.4）；舰队下游差异（Fleet 实体/build_time/无质保）保持。

## WP-L L2 同步注记（2026-10-02，DA-Execute；append-only）

> 权威：SA-Development-Task WP-L L2 **v1.2**；规格 `specifications/MVP0.5-04_舰队建造合同.md` §2.2/§2.9/§2.10/§5.2/§5.5/§5.6。

- `NavalSystem.apply_maintenance()` — **短款全额扣费**（`treasury -= initial_due`，可为负）；**删除短款自动解散分支**
  （候选循环 / `Fleet.disband()` / `war.remove_fleet()` / `reason=treasury_shortfall` 事件）；DTO 退化常量
  （`disbanded=0`/`disbanded_fleet_ids=[]`/`fleet_costs=[]`/`unpaid=0`/`success=True`/`required_after_disband=total`；
  `charged=total`）键形状保留（FC-L2-02/11）。
- `AutoFleetDisbandDecider.should_disband_fleet()` — 决策序（D2.5）：resolved-target 退役 → ACTIVE/THREAT/未批准-TRUCE
  保留 → approved-TRUCE 退役 → 无相关海战战争保留（FC-L2-05/06）。
- `NavalSystem._has_existing_fleet_or_contract_for_war()` — 舰队子句 `status ∉ {DESTROYED, DISBANDED}`（FC-L2-13）；
  `generate_replacement_contracts` usable 集不变（已排除 DISBANDED）。
- 零新增持久化字段；`economic_service.apply_naval_maintenance` DTO shape 不变（值退化）；`Fleet.disband()` 保留 `_target_war_id` provenance 不变。

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.3 | 2026-10-02 | WP-L L2：维护短款全额扣费+零解散 / decider 收窄（保留 resolved-target + approved-TRUCE 退役）/ THREAT 建造预算排除 DISBANDED（DA-Execute） |
| v1.2 | 2026-10-02 | WP-L L1：强度展示契约（post-build 战争卡单一源，QML 只渲染）+ 单入队点 parity + 四权威推广至全部 PUBLIC_WORKS（DA-Execute） |
| v1.1 | 2026-09-05 | R3-G-03/04 同步：四权威持久链 + nominal replacement + package 聚合器 + legacy 边界（DA-R3-B3） |
| v1.0 | 2026-07-12 | 初版 |
