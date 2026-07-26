# MVP0.5-14-sys — 结构化调试日志系统 Technical Mapping

## 1. 代码目录
```
src/core/game_state.py  # _setup_logging(), log_event(), log_exception(), close_logging()
```

## 2. 关键方法
- `_setup_logging()` — 初始化RotatingFileHandler + 独立Logger
- `log_event(message, level, extra)` — 记录到内存+文件
- `log_exception(e, context, extra)` — 异常日志

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
