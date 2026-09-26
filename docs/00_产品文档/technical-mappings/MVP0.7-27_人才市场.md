# MVP0.7-27 — 人才市场（技术映射）

## 1. 代码目录
```
src/core/entities/curia.py        # Curia 实体
src/core/game_state.py            # 权威招募容量 resolver（get_faction_capacity / get_remaining_recruitment_slots …；WP-I）
src/ui/commands/phase_forum.py    # 招募环节
src/ui/commands/func_forum.py     # PersuadeCommand
src/api/forum_api.py              # retire_figure(), recruit_figure(), resolve_forum(), _available_figure_row(), _viewer_recruitment()
src/ui/gui/session_store.py       # forumRecruitment* / forumViewerPendingRecruitmentTargetIds 只读透传（WP-I）
src/ui/gui/qml/stages/ForumStage.qml  # 人才市场行渲染（招募行门控消费权威剩余槽位；WP-I）
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

## 2.1 viewer 作用域招募容量读模型（WP-I 新增字段，2026-09-26）

```text
get_forum_view(state, viewer_player_id).data 新增（viewer 作用域，仅本派系）：

viewer_recruitment: {
  capacity: int,                          # GameState.get_faction_capacity()
  current_member_count: int,              # len(faction.get_members(state))（存活）
  physical_vacancies: int,                # max(0, capacity - current_member_count)
  pending_recruitment_target_count: int,  # 本派系 distinct figure_id 数
  remaining_recruitment_slots: int,       # max(0, physical_vacancies - pending_target_count)
  can_submit_recruitment_bid: bool        # remaining_recruitment_slots > 0
}
viewer_pending_recruitment_target_ids: [int, ...]   # viewer 作用域 distinct 目标（多玩家隔离）

权威来源：GameState.get_faction_capacity() / get_faction_physical_vacancies() /
  get_pending_recruitment_target_count() / get_remaining_recruitment_slots()
  （单一 resolver，DESIGN FROZEN 2026-09-26；无第二张容量表）。

GUI 消费链：api_adapter.get_forum_view（整体透传 data）→ session_store
  （forumRecruitment / forumRecruitmentCapacity / forumRecruitmentRemainingSlots /
   forumRecruitmentCanSubmit / forumViewerPendingRecruitmentTargetIds … 只读透传）
  → ForumStage.qml 招募行门控（marketUnlocked && canExecuteForum && recruitActionAllowed）。

既有 pending_actions.recruitment_bids（记录条数）保持不变（零破坏）。
```

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-09-26 | WP-I：新增 §2.1 viewer 作用域招募容量读模型契约（viewer_recruitment / viewer_pending_recruitment_target_ids）+ 权威来源与 GUI 消费链 |
| v1.1 | 2026-08-29 | WP-F 021：available_figures 补 is_hero/hero_type（实体持久 → DTO 透出 → 人才市场 🌟） |
| v1.0 | 2026-07-12 | 初版 |
