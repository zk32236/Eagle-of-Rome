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

## WP-G-R4 同步注记（2026-09-09，DA-R4-B3；append-only）

> 权威：SA-Design-WP-G-R4 v1.7（FROZEN）§3/§5；对应规格 MVP0.7-04 §2.2 注记。
>
> - **readiness helper**：`NavalSystem.get_ready_fleets_for_war(war)`（read-only 单一事实源，
>   `resolve_naval_battle` 前置守卫与 `get_war_fleet_strength_read_model` 共用）；resolver
>   扩展 NOT_READY 返回（executed:false/reason/零参与集，原两元解包兼容）。
> - **resolve 新返回 details**：真实五结果增 executed:true、participating/casualty_fleet_ids
>   （损失前后差集）、roman_losses/enemy_loss、stage 海权快照。
> - **API→GUI/CLI 消费**：`do_combat_action` v2 envelope（schema_version=2，naval/land 并列
>   executed；未执行 stage omitted keys）；get_combat_view war card 透传 `result`（active/
>   truce/resolved 三类同回合）；主 CLI（phase_combat）与 GUI Store 消费同一 envelope。

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-09-09 | WP-G-R4 B3：readiness helper/新 resolve details/API→GUI+CLI v2 envelope 消费（DA-R4-B3） |
| v1.1 | 2026-09-05 | R3-G-04 同步：package 聚合消费 + nominal replacement + strength DTO 字段（DA-R3-B3） |
| v1.0 | 2026-07-12 | 初版 |
