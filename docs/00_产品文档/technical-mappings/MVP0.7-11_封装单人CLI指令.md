# MVP0.7-11 — 封装单人CLI指令（技术映射）

## 1. 代码目录
```
src/ui/debug_cli.py              # DebugCLI 主循环 (主入口)
src/ui/commands/                 # 40个命令类
src/ui/commands/sys_base.py      # Command基类
src/ui/commands/sys_registry.py  # CommandRegistry
src/api/*.py                     # API层
src/core/i18n.py                 # 多语言
```

## 2. 关键组件
- DebugCLI.run() — 主循环
- CommandRegistry — 自动扫描注册
- Phase状态机 — Forum(6步)/Population(4步)/Senate(6步)

## 3. 版本日志 | v1.0 | 2026-07-17 | 初版 |
