# MVP0.7-09 — 行省起义-P0（技术映射）

## 1. 代码目录
```
src/core/systems/war_system.py              # create_rebellion_war(), register_rebellion_war()
src/core/systems/province_unrest_system.py  # ProvinceUnrestSystem — 民变检测核心逻辑 (Wave-02)
src/api/forum_api.py                        # check_province_unrest() — 民变检测API入口 (Wave-02)
src/ui/commands/phase_forum.py              # _update_civil_unrest() → 委托 forum_api (Wave-02)
src/ui/commands/phase_senate.py             # _assign_rebellion_commanders()
src/core/entities/province.py               # event_flags 起义标记
```

## 2. 调用链变更 (Wave-02 CLI下沉)

CLI `phase_forum._update_civil_unrest()`
  → **委托至** `forum_api.check_province_unrest()`
    → `ProvinceUnrestSystem.check_and_trigger_unrest()`
      → 检测各省民怨 → 达阈值则创建 Rebellion 实体
      → 返回 `{rebellions: [...], province_updates: [{id, name, grievance, reason}]}`

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-26 | 民变检测 CLI→API 下沉：新增 ProvinceUnrestSystem + forum_api |
| v1.0 | 2026-07-12 | 初版 |
