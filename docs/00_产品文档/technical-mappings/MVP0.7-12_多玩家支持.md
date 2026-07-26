# MVP0.7-12 — 多玩家支持（技术映射）

## 1. 代码目录
```
src/core/entities/player.py      # Player + PlayerType
src/core/game_state.py           # 玩家系统字段
src/api/player_api.py            # 玩家API
src/ui/commands/func_player.py   # players/end_turn命令
src/ui/debug_cli.py              # 提示符前缀
```

## 2. 核心方法
- `next_player()` — 回合轮流
- `is_current_player()` — 权限校验
- `_ensure_interactive_player()` — AI不占交互位
- `get_session_snapshot()` — GUI信息隔离

## 3. 版本日志 | v1.0 | 2026-07-13 | 初版 |
