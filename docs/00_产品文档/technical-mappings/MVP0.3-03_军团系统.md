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

## WP-O 同步注记（2026-09-27，DA-Execute WP-O/O-S3；append-only）

> 权威：SA-Design WP-O v1.0（`075f873b…`）§B1；规格 `specifications/MVP0.3-03_军团系统.md` §「WP-O 同步注记」（§5.3/§2.6）。

- **绑定-only 清理**：`MilitarySystem.clear_deceased_commander_bindings(member_id)` —— 仅清**精确匹配死者**的 Legion `commander_id` 镜像；保留 `war_id`/status/`is_veteran`/维护/经验面；**不** recall/disband/destroy/recruit。
- **owner 分离**：WarSystem 为生命周期编排者，本 helper 非独立策略引擎；非指挥官死亡 = 无关 Legion 零变化。

### 版本日志（续）
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.1 | 2026-09-27 | WP-O O-S3：死亡绑定-only Legion 镜像清理（DA-Execute） |
