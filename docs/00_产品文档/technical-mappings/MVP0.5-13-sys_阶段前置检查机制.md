# MVP0.5-13-sys — 阶段前置检查机制（技术映射）

## 1. 代码目录
```
src/core/game_state.py  # is_phase_executed(), mark_phase_executed(), record_phase_result()
```

## 2. 核心方法
- `is_phase_executed(phase_name)` → bool
- `mark_phase_executed(phase_name)`
- `advance_year()` → 清空阶段标记

## 3. 版本日志 | v1.0 | 2026-07-13 | 初版 |
