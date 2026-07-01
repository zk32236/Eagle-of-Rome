# GUI-P0-02A GUI主壳与阶段导航扩展 技术边界审查报告 - SA-01

审查日期：2026-06-30

审查角色：SA-01 / 系统架构师

任务来源：`docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包.md`

当前代码基线：Git HEAD `bbd5240 Add GUI-P0-02A PM intent package`

说明：本地工作区存在 `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx` 未提交修改。本审查未读取或修改该文件。

## Decision

`READY_FOR_TECH_TASK`

## Reasons

1. GUI-P0-01 已经提供可运行的 PySide6/QML 主壳、阶段容器、结构化反馈、玩家交接遮罩、Session Store、API Adapter 和人口阶段真实可玩切片，适合在此基础上扩展主壳和导航。
2. GUI-P0-02A 的 PM 范围清晰：只做主壳、阶段导航、通用状态摘要、反馈区和后续阶段扩展点，不要求完成所有阶段业务操作。
3. 现有 `session_api.get_session_snapshot()` 已提供按 viewer 过滤的 DTO，可作为全局状态摘要和阶段导航的数据来源；但目前阶段顺序、当前阶段、阶段可操作性仍偏 GUI-P0-01 人口切片，需要补强为通用 shell DTO。
4. 现有 QML `GameShell`、`PhaseRail`、`TopStatusBar`、`ContextPanel`、`FeedbackPanel` 可延续方案 A“共和国议事厅”视觉方向，不需要大范围视觉重做。
5. 本任务不需要改写 Core/System/Entity，不需要修复历史 `game_api -> ui.commands` 反向依赖；只需避免新增同类依赖。

## Files reviewed

- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包.md`
- `docs/MVP 0.9 项目管理/P1功能最小可用GUI开发与验收标准.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-01 MVP0.7可玩GUI原型 技术开发任务书 - KIMI-01.md`
- `AGENTS.md`
- `.agents/runtime_profile.md`
- `gui_main.py`
- `gui_screenshot.py`
- `src/ui/gui/app.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/qml/Main.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/shell/FeedbackPanel.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/api/session_api.py`
- `src/api/game_api.py`
- `src/tests/test_gui/test_qml_startup.py`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_adapter.py`

## GUI architecture boundary

### GUI/QML layer

允许承担：

- 展示完整 MVP0.7/P0 阶段序列。
- 切换阶段容器中的只读页面或占位页面。
- 展示全局状态摘要、当前玩家、当前派系、公开资源、反馈消息和未实现提示。
- 对已实现的人口阶段继续展示真实操作入口。
- 对未实现阶段显示“后续任务承接 / 暂不可操作”，不得伪装为可完成业务闭环。

禁止承担：

- 不得复制人口、元老院、收入、广场、战争、决算阶段核心规则。
- 不得直接访问或修改 `GameState`、System、Service、Entity 私有字段。
- 不得通过 QML 直接调用 Core/System/Service/Entity。
- 不得通过 `game_api.execute_phase()` / `execute_turn()` 执行 CLI Command。

### Store / Adapter layer

允许承担：

- 持有 GUI 会话状态中的 viewer、selected phase、反馈队列和只读 DTO 缓存。
- 调用 `session_api` 和已有阶段 API。
- 把 `{success, message, data, errors}` 映射为 GUI 反馈状态。
- 操作成功后从权威 API 重新刷新快照。

禁止承担：

- 不得维护第二套权威游戏状态。
- 不得在 Store 中推演阶段业务结果。
- 不得绕过 API 写入 Core。

### API / session layer

允许承担：

- 补强 `session_api` 的只读 GUI shell DTO，例如阶段导航、全局摘要、阶段卡片元数据、未实现状态、权限提示、关键警告。
- 继续按 viewer 过滤玩家可见信息。
- 使用 `src.api.api_response` 返回统一结构。

禁止承担：

- 不得新增 API -> UI 命令依赖。
- 不得在本任务中修复或扩大 `game_api.py` 历史反向依赖。
- 不得直接执行尚未 API 化的阶段业务。

### Core/System/Entity layer

本任务原则上不修改 Core/System/Entity。若确需新增公开只读方法，必须满足：

- 仅用于读取 shell DTO 所需状态。
- 不改变现有业务语义。
- 有测试覆盖。
- 在开发报告中说明调用方和原因。

## Allowed implementation scope

建议允许修改：

- `src/api/session_api.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/app.py`
- `src/ui/gui/qml/Main.qml`
- `src/ui/gui/qml/shell/*.qml`
- `src/ui/gui/qml/components/*.qml`
- `src/ui/gui/qml/stages/*.qml`
- `src/tests/test_gui/*.py`
- `gui_screenshot.py`（仅用于补充 GUI-P0-02A 截图流程）
- `src/ui/gui/README.md`（如需更新运行说明）

谨慎允许：

- `gui_main.py`：仅限启动日志或初始化参数，不得改成 CLI 阶段执行入口。
- `data/scenarios/gui_prototype.json`：仅限最小测试场景补强，必须保持 GUI-P0-01 人口切片可用。

默认禁止修改：

- `src/core/`
- `src/ui/commands/`
- `src/ui/processors/`
- `src/api/game_api.py`
- `src/api/population_api.py`、`senate_api.py`、`forum_api.py`、`contract_api.py` 等阶段业务 API，除非 SA 另行授权。
- `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`

## Required public API/session/store changes

建议新增或补强以下只读结构，名称可由实现 Agent 按现有风格微调，但语义必须保留：

1. `session_api.get_session_snapshot()` 增加 shell 所需 DTO 字段，或新增 `session_api.get_gui_shell_snapshot(state, viewer_player_id)`：
   - `phase_navigation`：完整阶段序列。
   - `current_phase_id`：当前权威阶段或 GUI 原型当前阶段。
   - `phase_summary`：阶段说明、状态、是否已实现、后续任务编号。
   - `global_warnings`：权限、未实现、测试场景提示等。
2. 阶段序列建议使用 GUI-P0 Sprint 口径展示：
   - `mortality`：天命
   - `population`：人口
   - `senate`：元老院
   - `revenue`：收入
   - `forum`：广场
   - `combat`：战争/海战
   - `resolution`：革命/决算
3. 每个阶段导航项至少包含：
   - `id`
   - `index`
   - `name`
   - `subtitle` 或 `description`
   - `status`：`current` / `completed` / `available` / `locked` / `placeholder`
   - `implemented`：人口阶段为 true，未迁移阶段为 false
   - `enabled`：是否可点击查看容器
   - `actionable`：是否存在本轮真实业务操作入口
   - `handoff_task`：后续承接任务编号，例如 GUI-P0-02B/C/D/E/F
4. `GuiSessionStore` 建议新增：
   - `selectedPhaseId`
   - `selectedPhaseName`
   - `selectedPhaseSummary`
   - `globalWarnings`
   - `selectPhase(phase_id)` Slot
   - `refreshShellSnapshot()` 或复用 `_refresh_snapshot()`
   - `raiseFeedback(type, message)` 或等价内部方法
5. QML 应通过 Store 属性渲染，不得硬编码当前玩家/阶段文本。


## GUI multilingual / i18n boundary

当前 GUI 只能确认“可显示中文/Unicode”，尚未形成真正多语言切换能力。GUI-P0-02A 不应扩大为完整多语言改造任务，但必须从主壳阶段开始预留 i18n 边界，避免后续 GUI-P0-02B-F 和 P1 GUI 反复返工。

本任务新增或大幅改动的 GUI 文案应遵守：

1. 不得把新增阶段名、状态名、按钮、占位提示、反馈提示、权限提示大量散落硬编码在 QML 中。
2. 应建立或使用一个 GUI 文案集中层，例如：
   - Python 侧 `src/ui/gui/localization.py` / `gui_text.py`；或
   - QML 侧 `src/ui/gui/qml/i18n/GuiText.qml` / Singleton；或
   - 复用项目现有 `i18n`，但不得让 QML 直接依赖 Core 私有状态。
3. Session/API DTO 应优先提供稳定 ID/key，例如 `phase_id`、`name_key`、`description_key`、`status_key`，显示文本可提供默认中文 fallback。
4. 本轮默认语言可以继续是 `zh-CN`，不强制完成运行时语言切换；但 key 命名和文本集中方式必须能支持后续 `en-US`。
5. 既有 GUI-P0-01 人口切片中的旧硬编码文本可暂不全量迁移；但本任务触碰或新增的主壳/导航/占位/反馈文本应优先集中。
6. 截图和测试应至少验证主壳在默认中文下正常渲染，且文案 key 缺失时不会导致 QML 空白或崩溃。

建议将完整 GUI 多语言切换登记为后续独立任务 `GUI-I18N-01`，在 GUI-P0 主壳稳定后统一处理旧文案迁移、语言切换入口、英文资源和视觉适配。
## Required tests

最低要求：

1. `src/tests/test_gui/test_session_api.py`
   - 快照包含完整 7 阶段导航。
   - 阶段顺序为：天命、人口、元老院、收入、广场、战争/海战、革命/决算。
   - 人口阶段保持已实现/可操作；其他阶段标记为后续任务承接或只读占位。
   - viewer 仍只看到本派系资源和本派系人物。
2. `src/tests/test_gui/test_adapter.py`
   - GUI Adapter 仍能获取快照。
   - 反馈映射仍符合 success/error/warning/info。
3. `src/tests/test_gui/test_qml_startup.py`
   - Main.qml root 非空。
   - 可定位 `gameShell`、`phaseRail`、`topStatusBar`、`contextPanel`、`feedbackPanel`、`populationStage`、`lockedStagePlaceholder`。
   - 阶段导航可见 7 项或可由 QML 对象/Store 数据验证 7 项。
4. 新增 GUI shell/navigation 测试：
   - `selectPhase("senate")` 等未实现阶段不崩溃，显示占位/未实现反馈。
   - 切回 `population` 后 GUI-P0-01 人口切片仍可用。
5. 回归测试：
   - `src/tests/test_gui -q`
   - `src/tests/test_api/test_population_api.py -q`
   - `src/tests/test_commands/test_phase_population.py -q`
   - `src/tests -q` 全量回归，若失败必须说明是否为环境权限问题或非本任务原因。
6. 可视验收：
   - 运行 `gui_screenshot.py` 或等价脚本，至少生成 1440x900 和 1280x720 主壳截图。
   - 截图需能看见完整阶段导航、顶部状态、右侧上下文/资源摘要、底部反馈区、人口阶段或占位阶段。

## Risks

1. `session_api.py` 当前仍有 `resolve_population_slice()` 导入 `src.ui.processors.auto_player_processor` 的历史 API -> UI 债务。本任务不得扩大修复，但实现 Agent 必须避免新增 API -> UI 依赖。
2. `game_api.py` 当前仍导入 CLI Command 并用于 CLI 阶段执行，这是 AS-P1-01 已记录的历史债务。本任务不得让 GUI 依赖 `game_api.execute_phase()` 或 `execute_turn()`。
3. 当前 GUI 原型 session 固定跳过 `mortality/revenue/forum` 并进入人口阶段；GUI-P0-02A 只负责导航和容器框架，不应在本轮尝试完成完整年流程推进。
4. QML 容器若一次性新增过多阶段页面，容易滑入 GUI-P0-02B-F 业务范围；本轮未实现阶段应保持占位/只读摘要。
5. 多玩家信息隔离是硬门禁：全局摘要可显示公开资源，派系资源只显示 viewer 本派系。

## Technical task archive path

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md`

## Next handoff target

`CGT-01`

理由：CGT-01 已完成 GUI-P0-01 QML 启动阻塞修复，并具备本项目本地代码、QML、pytest 验收经验。本任务是代码仓库内增量实现，适合由 CGT-01 执行。

## Baseline test status

SA 在派工前复跑：

```text
src/tests/test_gui: 13 passed in 1.43s
```