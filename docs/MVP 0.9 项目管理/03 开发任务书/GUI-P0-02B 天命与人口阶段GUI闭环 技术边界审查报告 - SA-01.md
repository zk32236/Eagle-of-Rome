# GUI-P0-02B 天命与人口阶段 GUI 闭环 技术边界审查报告 - SA-01

日期：2026-07-02
发布角色：SA-01 / 系统架构师
依据任务：GUI-P0-02B《天命与人口阶段GUI闭环》PM任务意图包

## Decision

READY_FOR_TECH_TASK

## Reasons

1. GUI-P0-02A 已提供主壳、阶段导航、状态栏、反馈区、placeholder 阶段容器和 i18n 预留，具备承接 GUI-P0-02B 的结构基础。
2. GUI-P0-01 人口阶段切片已有 `population_api`、`session_api.get_population_view()`、`GuiSessionStore`、QML 页面和 GUI 测试基础，可被整合进新主壳继续使用。
3. 天命阶段当前没有 GUI 安全 API，也没有服务层入口；核心规则集中在 `src/ui/commands/phase_mortality.py` 命令层。若 GUI 直接调用 `MortalityCommand` 或 `game_api.execute_phase()`，将破坏 `GUI -> API -> Core/System/Service -> Entity` 边界。
4. 该风险可以通过窄范围新增 `MortalityService` + `mortality_api` 解决，不需要扩大为全阶段迁移或 P1 新玩法开发。
5. GUI-P0-02B 可以进入技术任务定稿，但任务书必须明确：天命阶段完成后只推进到真实下一阶段 `revenue`，不得为了演示闭环直接跳转到 `population`。

## Files reviewed

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-02B 天命与人口阶段GUI闭环 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`
- `src/api/session_api.py`
- `src/api/population_api.py`
- `src/ui/commands/phase_mortality.py`
- `src/ui/commands/phase_population.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/app.py`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/stages/PopulationStage.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`
- `src/tests/test_commands/test_phase_mortality.py`
- `src/tests/test_commands/test_phase_population.py`
- `src/tests/test_api/test_population_api.py`

## Fate stage API/session readiness

当前状态：不足，但可在本任务内窄范围补齐。

已存在：

- `phase_mortality.py` 已包含天命阶段旧规则：事件抽取、死亡、丰收、和平、猛男、灾害、阶段标记和日志。
- `GameState` 已有 `active_events` 只读属性、`hero_spawned_this_turn` / `hero_to_spawn` 属性、`draw_mortality_number()`、`mark_phase_executed()`、`is_phase_executed()`、`mark_member_dead()`。
- `EconomicService` 已消费 `active_events`，说明天命事件结果仍需写入权威 Core 状态。

缺口：

- 无 `src/api/mortality_api.py`。
- 无 `src/core/service/mortality_service.py`。
- `session_api.create_gui_prototype_session()` 当前直接标记 `mortality/revenue/forum` 已执行，并固定进入人口阶段，不适合 GUI-P0-02B 主流程。
- `session_api.get_session_snapshot()` 当前固定 `current_phase_id = "population"`，未按真实阶段执行状态推导当前阶段。
- `GameShell.qml` 当前只有 `PopulationStage` 与 `LockedStagePlaceholder`，缺少 `MortalityStage`。

边界建议：

- 新增 `MortalityService`，将 `phase_mortality.py` 中核心规则迁入服务层或由服务层集中承载，返回结构化天命结果。
- 新增 `mortality_api.execute_mortality_phase(state, viewer_player_id)` 和必要的只读 view API，统一返回 `{success, message, data, errors}`。
- `phase_mortality.py` 应变为 CLI 包装层，调用服务/API 或至少与服务共用同一核心实现，不得保留一套 GUI 规则、一套 CLI 规则。
- 如需写入 active event，应优先补充 `GameState` 公共方法，例如 `record_active_event(key, payload)`，不得从 GUI/API 层直写 `_active_events`。

## Population stage integration plan

- 人口阶段继续复用 `population_api.campaign()`、`population_api.vote()`、`population_api.resolve_election()`、`session_api.get_population_view()`、`resolve_population_slice()`。
- `PopulationStage.qml` 继续作为真实人口切片，但必须挂入 GUI-P0-02A 阶段容器和导航状态。
- 人口阶段只有在 `current_phase_id == "population"` 且 viewer 是当前玩家时才 actionable。
- GUI-P0-02B 不得为了连接天命和人口而跳过收入、广场阶段；如果天命完成后的下一阶段是 `revenue`，GUI 应显示收入 placeholder 或后续任务承接状态。
- 可保留测试/开发用 session fixture 直接进入人口阶段，但必须与正式 GUI 主流程区分，避免误导玩家流程。

## Allowed implementation scope

- 新增：`src/core/service/mortality_service.py`
- 修改：`src/core/service/__init__.py`
- 新增：`src/api/mortality_api.py`
- 修改：`src/api/session_api.py`
- 修改：`src/ui/commands/phase_mortality.py`，仅限改为服务/API 包装层并保持 CLI 行为
- 修改：`src/ui/gui/api_adapter.py`
- 修改：`src/ui/gui/session_store.py`
- 新增/修改：`src/ui/gui/qml/stages/MortalityStage.qml`
- 修改：`src/ui/gui/qml/shell/GameShell.qml`、`ContextPanel.qml`、必要的 i18n 文案
- 新增/修改：`src/tests/test_gui/`、`src/tests/test_api/`、`src/tests/test_commands/`、必要的 `src/tests/test_core/`
- 必要时补充 `GameState` 公共方法以避免服务/API/UI 直接写私有字段

## Required public API/session/store changes

1. `mortality_api.execute_mortality_phase(state, viewer_player_id)`
   - 校验当前阶段与重复执行。
   - 调用服务层执行天命规则。
   - 返回结构化事件列表、影响对象、状态变化、`phase_executed`、`next_phase_id`。

2. `session_api.get_session_snapshot()`
   - 不再固定 `population`。
   - 应按阶段顺序和 `state.is_phase_executed()` 推导 `current_phase_id`。
   - 保持阶段导航顺序：`mortality, revenue, forum, population, senate, combat, resolution`。
   - `implemented/actionable` 应至少支持 `mortality` 与 `population`，但 actionability 必须受真实当前阶段和当前玩家限制。

3. `GuiApiAdapter`
   - 新增天命 API 调用包装。
   - 不得导入 `src.ui.commands.phase_mortality`。

4. `GuiSessionStore`
   - 新增天命视图数据、执行天命 Slot、天命执行后刷新 snapshot 和反馈。
   - 保持人口视图现有 API，不维护第二套权威状态。

5. QML
   - 新增 `MortalityStage.qml`。
   - `GameShell.qml` 根据 selected phase 显示 `MortalityStage`、`PopulationStage` 或 `LockedStagePlaceholder`。
   - 新增文本进入 `GuiText.qml` 或 Python GUI catalog，默认 zh-CN，不要求运行时语言切换。

## Required tests

CGT-01 至少执行并报告：

- `src/tests/test_gui`：GUI shell、QML startup、session store、mortality stage、population stage 回归。
- `src/tests/test_api/test_population_api.py`：人口 API 回归。
- 新增 `src/tests/test_api/test_mortality_api.py`：天命 API 成功、重复执行失败、无事件牌、死亡/事件摘要、下一阶段不跳人口。
- `src/tests/test_commands/test_phase_mortality.py` 及相关 mortality command tests：CLI 行为不退化。
- `src/tests/test_commands/test_phase_population.py`、`test_phase_population_disband.py`、`test_phase_population_truce.py`：人口命令回归。
- full `src/tests`：CGT-01 应执行；若报告完整，SA 后续可按当前规范采信，不重复跑全量。
- `git diff --check`：仅允许 CRLF 提示，无空白错误。

不要求 CGT-01 提交 GUI 截图。GUI 视觉由项目负责人/SA 在真实 Windows GUI 窗口人工验证。

## Risks

- 最大风险是把 `phase_mortality.py` 命令层当成 API 复用，造成 GUI -> API -> UI command 的反向依赖。任务书必须禁止。
- 天命事件会影响收入阶段、战争威胁、英雄生成和死亡合同清理，服务层迁移必须保持旧行为测试。
- 当前 `session_api.resolve_population_slice()` 仍有 API -> UI processor 历史债，本任务不扩大处理，但不得新增同类依赖。
- 如果 `create_gui_prototype_session()` 默认行为调整，必须更新 GUI 测试并保留必要的测试辅助入口。
- 当前工作区仍有项目负责人自行修改的版本规划 Excel，CGT-01 不得读取、暂存或修改该文件。

## Technical task archive path

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02B 天命与人口阶段GUI闭环 技术开发任务书 - CGT-01.md`

## Next handoff target

CGT-01