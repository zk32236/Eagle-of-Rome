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
| v1.2 | 2026-10-09 | WP-J Group D：起义事件只读捕获（`_forum_rebellion_events`，镜像 `_forum_war_events`）→ `get_forum_view().rebellion_events` → ForumStage 公告框内警示行（DA-Execute） |
| v1.1 | 2026-07-26 | 民变检测 CLI→API 下沉：新增 ProvinceUnrestSystem + forum_api |

## WP-J Group D 同步注记（2026-10-09，DA-Execute；append-only）

> 权威：WP-J Group D v1.1 §5.4；对应规格 MVP0.7-09 §1/§2.1 注记。

- **只读捕获链（不变写边界）**：`initialize_forum_turn()` 在 `check_province_unrest()` 之后将权威 `rebellions[]` 写入 `state.set_forum_rebellion_events(...)`（`GameState._forum_rebellion_events` + 访问器 + `_commit_settlement` 同区清理）；**不改**起义创建路径。→ `forum_api.get_forum_view()` 增 `rebellion_events`（additive 只读）→ `session_store.forumRebellionEvents` → `ForumStage.qml` 既有 `announceArea` 框内追加「⚠️ 起义爆发：<province_name>（<name>）」行。
| v1.0 | 2026-07-12 | 初版 |
