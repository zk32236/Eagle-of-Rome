# GUI-P0-03 ForumStage DA开发报告

日期：2026-07-13

执行方：Codex

## 1. 任务目标

本轮目标为一次性完成 GUI Phase 3「广场阶段」的可操作 Vertical Slice，使其符合 v3.25.1 GUI 设计原型的阶段结构，并遵守既定 B 路线：

- 保留启动入口、Adapter、Store、Shell 等连接层。
- 不修改内核实体、系统、服务与阶段命令实现。
- 通过 `QML -> GuiSessionStore -> GuiApiAdapter -> forum_api` 连接真实广场 API。
- 使用既有 `StageDesktop` 槽位，不破坏 Phase 1/2 已稳定的视觉骨架。

## 2. 本轮交付内容

### 2.1 PM/SA/DA工作流文档

已按项目工作流补齐阶段 3 交付链：

- `02_项目任务书/GUI-P0-03_ForumStage_PM意图包.md`
- `03_开发与验收/GUI-P0-03/GUI-P0-03_ForumStage_SA边界审查报告.md`
- `03_开发与验收/GUI-P0-03/GUI-P0-03_ForumStage_DA开发任务书.md`
- `03_开发与验收/GUI-P0-03/GUI-P0-03_ForumStage_DA开发报告.md`

### 2.2 API层

修改文件：

- `src/api/forum_api.py`
- `src/api/session_api.py`

主要变更：

- 新增 `get_forum_view(state, viewer_player_id)`，向 GUI 输出广场阶段 DTO。
- 新增 `advance_forum_phase(state, viewer_player_id)`，在广场结算后推进至人口阶段。
- `resolve_forum()` 现在会写入 `forum` 阶段结果，供 GUI 展示结算结果与判断推进状态。
- `session_api` 将 `forum` 纳入已实现 interactive 阶段。
- `session_api` 暴露广场阶段可用动作：解雇、招募、竞标、公地购买、凯旋投票、结算广场。

### 2.3 Adapter / Store连接层

修改文件：

- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`

主要变更：

- `GuiApiAdapter` 新增广场查询与操作方法。
- `GuiSessionStore` 新增 `forumView`、`forumCurrentStep`、`forumMyFigures`、`forumAvailableFigures`、`forumPendingContracts`、`forumLandQuota`、`forumTriumphWars` 等 QML 可绑定属性。
- 新增 Store Slots：
  - `doRetireFigure`
  - `doRecruitFigure`
  - `doPlaceBid`
  - `doBuyLand`
  - `doVoteTriumph`
  - `doCompleteForumStep`
  - `doResolveForum`
  - `doAdvanceForum`
- 广场阶段采用两步 UI 状态：`retirement -> market -> resolution`。

### 2.4 QML界面

新增文件：

- `src/ui/gui/qml/stages/ForumStage.qml`

修改文件：

- `src/ui/gui/qml/shell/GameShell.qml`

主要变更：

- 在 `StageContentSlot` 挂载 `ForumStage`。
- 在 `StageHeaderSlot` 增加广场阶段专用标题与说明。
- 在 `StageInstructionSlot` 增加广场阶段步骤条。
- 在 `StageActionSlot` 增加广场阶段主操作按钮：
  - 解雇阶段：完成解雇
  - 市场阶段：结算广场
  - 结算后：推进到人口阶段
- `ForumStage` 提供解雇成员、可招募人物、待竞标合同、公地购买、凯旋表决、结算结果展示等区域。

### 2.5 测试

修改文件：

- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_qml_startup.py`

新增覆盖：

- `forum_api.get_forum_view` DTO 查询。
- Adapter 广场 DTO 暴露。
- Store 广场阶段状态流转：`retirement -> market -> resolved -> population`。
- Shell 阶段导航中 `forum` 的 implemented / interactive / actionable 状态。
- QML 启动测试确认 `forumStage` 存在，并挂载在 `stageContainer`。
- QML 结构测试确认 `forumActionLayer` 挂载在 `centerPanel`，避免动作层侵入内容槽。

## 3. 验证结果

### 3.1 聚焦验证

命令范围：

- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_gui`

结果：

```text
95 passed in 5.85s
```

### 3.2 完整回归

命令范围：

- `src/tests`

结果：

```text
780 passed in 13.21s
```

### 3.3 静态检查

执行 `git diff --check`：

- 未发现空白错误。
- 仅存在 Git 对 LF/CRLF 的换行提示，不影响功能。

## 4. 边界遵守情况

本轮未修改：

- `src/core/`
- 内核实体、系统、服务
- CLI 阶段命令
- `Main.qml`
- GUI 启动入口

本轮只在允许范围内修改：

- `src/api/`
- `src/ui/gui/`
- `src/tests/`
- GUI-P0-03 项目文档目录

## 5. 风险与后续建议

### 5.1 已知非阻断问题

测试过程中曾出现一次 Windows 日志文件瞬时占用，复跑后聚焦测试与完整回归均通过。该问题来自 `GameState` 测试会话在同一秒内复用日志文件名，不属于本轮广场 GUI 功能缺陷。

### 5.2 建议

- Phase 4 开发前，继续沿用本轮的 `PM意图包 -> SA边界审查 -> DA任务书 -> DA开发报告` 四件套。
- 后续阶段仍应避免直接在 QML 中访问 core/API，只能通过 Store/Adapter 暴露动作。
- 如果后续需要提高 GUI 视觉一致性，应继续使用槽位结构测试与人工设计图对照验收，不建议回到大范围无边界修补。

## 6. 结论

GUI-P0-03 ForumStage 已完成阶段 3 Vertical Slice。功能链路、QML 结构、连接层边界与测试门禁均通过，可进入人工视觉验收与 Git 归档准备。
