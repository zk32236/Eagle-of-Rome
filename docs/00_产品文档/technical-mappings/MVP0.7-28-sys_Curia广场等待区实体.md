# MVP0.7-28-sys — Curia广场等待区实体（技术映射）

## 1. 代码目录
```
src/core/entities/curia.py        # Curia dataclass
src/core/game_state.py            # 持有curia实例
src/api/forum_api.py              # recruit_figure() 调用curia.remove_figure()
src/ui/commands/func_turn_control.py  # 回合推进时curia.clear()
```

## 2. 核心方法
- `add_figure()` — 人物进入广场
- `remove_figure()` — 人物离开广场
- `clear()` — 清空队列
- `record_recruitment()` — 招募历史

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
