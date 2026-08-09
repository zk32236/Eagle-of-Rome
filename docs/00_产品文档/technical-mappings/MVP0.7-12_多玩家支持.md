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

## 3. AC-12 M2-BUG3 R2 变更 (2026-08-09)
- `turn_order` 保持 ScenarioLoader 全序（含 AI），不再被 `create_gui_prototype_session` 覆盖为仅 HUMAN
- `session_store.doCompletePlayer()`: 新增 `_drain_ai_population_turns()` — 人类完成后自动消费所有连续 AI 玩家（庆典+投票）
- handoff 信号改为 player_type 条件：仅人类玩家触发 `handoffRequired.emit()`
- `api_adapter.resolve_population_slice()`: 新增方法，委托到 `session_api.resolve_population_slice()` 统一入口（FC-09）

## 4. 版本日志
| v1.0 | 2026-07-13 | 初版 |
| v1.1 | 2026-08-09 | DA-Exec (AC-12 M2-BUG3 R2) | turn_order 全序 + AI drain + player_type 条件 handoff + resolve_population_slice 统一入口 |
