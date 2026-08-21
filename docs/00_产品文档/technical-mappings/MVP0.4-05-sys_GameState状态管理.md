# MVP0.4-05-sys — GameState状态管理 Technical Mapping

> **功能简述：** 全局游戏状态单例管理

## 1. 代码目录
待代码审计。

## 2. 关键模块
- `src/core/game_state.py` — 全局游戏状态单例；`_forum_pending` 持久化字典（含 `forum_initialized` canonical init 守卫 key，2026-08-21 WP-C 新增，复刻 `market_opened`；`clear_forum_pending` L482 全 key 跨回合重置；`to_dict`/`load_from_dict` 自动序列化/补齐）

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-21 | GUI-BETA-R1 WP-C: `_forum_pending` 新增 `forum_initialized` key（__init__/load_from_dict 默认字面量 + required_forum_keys 补齐 + create_for_testing 三处） |
