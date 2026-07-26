# MVP0.4-04-sys — Command命令体系架构 Technical Mapping

## 1. 代码目录

| 目录 | 角色 |
|------|------|
| `src/ui/commands/` | 所有命令类 |
| `src/api/` | API 层 |
| `src/core/deciders/` | 决策器层 |

## 2. 关键文件
- `sys_base.py` (167行) — Command 基类
- `sys_registry.py` (120行) — 命令自动注册
- `phase_forum.py` (1601行) — 广场阶段状态机
- `phase_senate.py` (1855行) — 元老院阶段状态机

## 3. 版本日志
| v1.0 | 2026-07-17 | 初版 |
