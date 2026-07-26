# MVP0.5-01 — 国家公地系统 Technical Mapping

## 1. 代码目录
```
src/core/game_state.py          # _national_public_land + 同步方法
src/core/entities/province.py   # Province 实体
src/core/entities/figure.py     # Figure._land_private
src/api/game_api.py             # get_public_land_info()
src/api/forum_api.py            # resolve_forum() 公地认购结算
```

## 2. 关键方法
- `add_national_public_land()` — 增减公地 + 同步意大利
- `sync_italy_public_land()` — 意大利行省同步
- `_update_global_public_land()` — 全局公地缓存刷新

## 3. 版本日志
| v1.0 | 2026-07-12 | 初版 |
