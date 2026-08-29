# MVP0.7-27 — 人才市场（技术映射）

## 1. 代码目录
```
src/core/entities/curia.py        # Curia 实体
src/ui/commands/phase_forum.py    # 招募环节
src/ui/commands/func_forum.py     # PersuadeCommand
src/api/forum_api.py              # retire_figure(), recruit_figure(), resolve_forum(), _available_figure_row()
src/ui/gui/qml/stages/ForumStage.qml  # 人才市场行渲染
```

## 2. 读模型契约（WP-F 021 更新，2026-08-29）

```text
get_forum_view(state, viewer_player_id).available_figures: [{...}]
每行字段（_available_figure_row 生产）：
  id / name / martial / intellect / charisma / zeal / influence / wealth /
  class_tier / class_label / cost /
  is_hero: bool        ← Figure 实体持久字段透出（S2-5；refresh/re-entry/招募后保留）
  hero_type: str|None  ← "historical" / "random" / None（可选透传）

渲染契约（ForumStage.qml 人才市场姓名格）：
  姓名（中性 #2E251B）+ 🌟（hero，星在名后，严格 modelData.is_hero === true）；
  普通人物无星；长名 ElideRight 截断（F-POST-R1-03）；左缘对齐一致（021-04）。
```

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-29 | WP-F 021：available_figures 补 is_hero/hero_type（实体持久 → DTO 透出 → 人才市场 🌟） |
| v1.0 | 2026-07-12 | 初版 |
