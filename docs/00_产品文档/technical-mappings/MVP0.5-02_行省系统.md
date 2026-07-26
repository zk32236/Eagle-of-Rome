# MVP0.5-02 — 行省系统 Technical Mapping

## 1. 代码目录
```
src/core/entities/province.py          # Province 实体 (392行)
src/core/game_state.py                 # 行省集合管理
src/core/scenario_loader.py            # 场景加载初始化
src/core/systems/province_unrest_system.py  # 行省民变检测系统 (Wave-02)
src/api/province_api.py                # 行省查询 API (185行)
src/api/forum_api.py                   # check_province_unrest() 民变API (Wave-02)
data/cards/provinces.json              # 8个行省数据
```

## 2. 关键字段 (29个)
province_id, name, total_land, land_public/private, grievance, governor_id/type/designate, conquered, infrastructure, resources, culture, religion, event_flags, loyalty, city_ids等

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-26 | 新增 ProvinceUnrestSystem + forum_api 民变检测调用链 |
| v1.0 | 2026-07-17 | 初版 |
