# MVP0.5-15-sys — 游戏输出与日志规范（技术映射）

## 1. 代码目录
```
src/core/i18n.py           # I18n 单例
src/core/game_state.py     # 日志系统
src/api/__init__.py        # api_response()
src/ui/debug_cli.py        # Tee 输出
src/ui/utils.py            # get_progress_bar()
```

## 2. 关键格式
- API响应: `{success, message, data, errors}`
- 日志格式: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- 进度条: `[▓▓▓░░░░] 3/7`

## 3. 版本日志 | v1.0 | 2026-07-13 | 初版 |
