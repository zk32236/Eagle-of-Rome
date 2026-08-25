# MVP0.3-03 — 军团系统（技术映射）

## 1. 代码目录
```
src/core/entities/legion.py         # Legion 实体
src/core/systems/military_system.py  # 征召/解散/指派/维护/恢复
src/ui/commands/phase_combat.py, func_military.py, phase_revenue.py
```

## 2. 关键模块
- `legion.py` — Legion 实体 + LegionStatus 枚举
- `military_system.py` — 征召(recruit)、解散(disband)、指派(assign)、维护(maintenance)、恢复(recovery)

## 3. 核心规则
状态机: UNRAISED → ACTIVE → AVAILABLE → DISBANDED/DESTROYED
恢复: interval 回合后 DESTROYED → DISBANDED

## 4. WP-E-R3 复用边界（2026-08-24）

- R3 不修改 `MilitarySystem` primitive：`recruit_multiple`、`assign_to_war`、`recall_from_war`、`disband_legions_for_war` 保持唯一底层实现。
- `WarSystem` 只负责编排；宣战、接管、TRUCE 到期共享 mobilize family，批准/降级共享 release family，禁止第二套 recruit/disband 循环。
- 重征沿用既有国库成本、军团池和部分成功语义：请求 N、实际 K 时，仅 K 个 Legion 为 ACTIVE 且绑定 war，所有投影显示 K。
- approved TRUCE 解散后 Legion 必须为 `DISBANDED`、`war_id=None`；不新增 commander/fleet/免费征兵规则。

## 5. 版本日志
| v1.1 | 2026-08-24 | WP-E-R3：记录 Military primitives 复用边界、partial recruit 与 approved-TRUCE 实体状态 |
| v1.0 | 2026-07-12 | 初版 |
