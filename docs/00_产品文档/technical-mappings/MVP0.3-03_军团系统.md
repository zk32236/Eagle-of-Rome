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

## 4. 版本日志
| v1.0 | 2026-07-12 | 初版 |
