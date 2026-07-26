# MVP0.7-20 — 多玩家信息隔离（技术映射）

## 1. 代码目录
```
src/core/entities/player.py      # Player + PlayerType
src/core/game_state.py           # 玩家系统字段/next_player/is_current_player
src/api/session_api.py           # 安全快照
src/ui/debug_cli.py              # _ensure_interactive_player()
```

## 2. 版本日志 | v1.0 | 2026-07-13 | 初版 |
