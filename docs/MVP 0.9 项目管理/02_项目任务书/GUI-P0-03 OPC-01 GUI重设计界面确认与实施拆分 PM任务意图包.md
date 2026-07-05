# GUI-P0-03 OPC-01 GUI重设计界面确认与实施拆分 PM任务意图包

- 日期：2026-07-05
- 发布方：项目经理 PM
- 接收方：系统架构师 SA-01
- 后续执行方：CGT-01（仅在界面确认门禁通过后）
- 优先级：P0
- 任务类型：GUI 产品界面确认 / 技术边界审查 / Sprint 子任务拆分
- 当前代码与文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## 一、背景说明

OPC-01 已提交新版 EOR GUI 设计方案，对当前 PySide6/QML GUI 原型和元老院只读界面进行全面升级。该方案不是单一编码任务，而是一组跨阶段 GUI 闭环任务，涉及主壳、阶段视图、GuiApiAdapter、多人轮流、角色锁定、i18n 和 UI/API 映射。

PM 判断：本任务必须先由 SA 基于 OPC-01 方案完成界面确认包和技术拆分，再由项目负责人确认任务界面。确认前，SA 不应直接向 CGT-01 发布开发任务书。

## 二、任务目标

请 SA 完成以下工作：

1. 阅读 OPC-01 GUI 设计方案、原型、UI/API 映射和代码对齐审计。
2. 将 OPC-01 的设计方案整理为可供项目负责人确认的“任务界面确认包”。
3. 明确哪些内容是新模块、哪些内容是现有 GUI 的增量修改。
4. 按 Sprint 方法拆分为若干可单独验证闭环的小任务。
5. 在项目负责人确认任务界面后，再为 CGT-01 定稿并发布技术开发任务书。

## 三、依据文档

请 SA 优先参考以下文档：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\PM_Instruction.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_GUI_Prototype_v3.23.html`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_GUI设计文档.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_UI_API_Mapping.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\GUI_Code_Alignment_Audit.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 四、PM 对设计方案的初步理解

### 4.1 全局界面结构

OPC-01 方案采用统一 GUI 主壳：顶部全局信息栏、左侧七阶段导航、中央阶段内容区、右侧上下文/日志面板、底部 12 个全局查询按钮。阶段顺序固定为：天命、收入、广场、人口、元老院、战争、决算。

### 4.2 多玩家与阶段操作规则

- 天命：任意玩家执行一次，结果全局共享。
- 收入：任意玩家确认结算，确认后全局推进。
- 广场：所有玩家轮流操作，AI 后台自动。
- 人口：所有玩家轮流进行庆典和投票。
- 元老院：执政官提案、所有玩家表决、保民官否决。
- 战争：任意玩家可依次对各战争执行战斗裁定。
- 决算：自动执行，无玩家操作。

### 4.3 界面开发类型划分

| 类别 | 模块 | PM 判断 |
|---|---|---|
| 全新模块 | 战斗阶段 GUI 视图 | 当前无专用 GUI 和 combat_api，需要 SA 先审查 API 边界。 |
| 全新模块 | 收入阶段 GUI 视图 | 当前无专用 revenue view API，需要从 EconomicService 输出结构化视图。 |
| 全新模块 | 广场阶段 GUI 视图 | CLI 与 forum_api 已有，GUI 视图和适配器缺失。 |
| 增量修改 | 元老院 GUI 只读版到交互版 | 应最大复用 `senate_api.get_senate_view()` 与现有只读 GUI 基线。 |
| 增量修改 | 人口 GUI 多玩家轮流增强 | 现有人口切片可用，但 controller/轮流流程需要加强。 |
| 增量修改 | GuiApiAdapter 方法扩展 | 以 `EOR_UI_API_Mapping.md` 的操作映射和增量清单为准。 |

### 4.4 优先级建议

| 优先级 | 内容 | PM 理由 |
|---|---|---|
| P0 | GuiApiAdapter 增量 + 元老院交互化 | 复用最多，且承接当前 GUI-P0-02C 元老院只读基线。 |
| P1 | 战斗视图 + 广场视图 | 两者是 P0 核心 GUI 闭环的关键缺口，且交互风险较高。 |
| P2 | 收入视图 + 决算优化 | 收入需要结构化 view，决算更多是自动流程展示和推进。 |
| P3 | i18n 语言包 + 多玩家最终调试 | 作为全 GUI 闭环收尾，但新写 UI 文字应从一开始按 i18n 规范设计。 |

## 五、SA 必须先执行的界面确认门禁

SA 在给 CGT-01 发开发任务书前，必须先向项目负责人提交界面确认包，至少包含：

1. OPC-01 方案是否作为后续 GUI 主方案采用。
2. 当前 GUI-P0-02A/02B/02C 已完成成果与 OPC-01 方案的关系：复用、调整或替换范围。
3. 七阶段主壳布局是否保持 OPC-01 方案。
4. 元老院三栏交互界面是否作为第一批交互化目标。
5. 战斗、广场、收入、决算是否按 PM_Instruction 的优先级进入后续 Sprint。
6. 底部 12 个全局查询按钮是否本轮只做入口/占位，还是部分接入真实 API。
7. i18n 是否作为所有新增 UI 的硬门禁。
8. 多玩家轮流、AI 后台、角色锁定和死锁逃生按钮的最小验收口径。

项目负责人确认前，SA 不得向 CGT-01 下达任何编码任务书。

## 六、允许修改范围（后续 CGT 阶段，仅供 SA 拆分参考）

SA 拆分技术任务时，可考虑以下范围，但每个子任务必须可单独验证闭环：

- `src/ui/gui/qml/` 下的 GUI 视图、主壳、组件和阶段页面。
- `src/ui/gui/api_adapter.py` 的 GUI API 封装方法。
- `src/ui/gui/session_store.py` 的状态刷新和阶段数据缓存。
- 必要的 GUI controller / store 辅助文件。
- 必要的 `src/api/*_api.py` 结构化 view API，但必须保持薄 API 层。
- 必要的 `src/core/service/*` 只读 view/结算结果导出，但不得引入 P1 新玩法。
- `data/i18n/zh-CN.json` 与 `data/i18n/en.json`。
- `src/tests/test_gui/`、`src/tests/test_api/` 中对应测试。

## 七、禁止事项

- 不得在界面确认前直接派发 CGT-01 编码任务。
- 不得让 GUI 直接调用 CLI Command 或 `game_api.execute_phase()` 来绕过 API 边界，除非 SA 明确登记为过渡性技术债并限定在只读/占位场景。
- 不得在 GUI 层直接修改 Core、Entity 或私有字段。
- 不得引入 P1 新玩法、数值改动或后端规则重写。
- 不得删除 CLI 路径；GUI 必须与 CLI/自动模式兼容。
- 不得把 OPC-01 HTML 原型中的 mock 数据当成真实状态来源。
- 不得将所有阶段合并成一个大任务交给 CGT-01；必须拆成可验收的小 Sprint。

## 八、实现要求（供 SA 技术拆分时遵守）

1. 继续保持 `GUI -> GuiApiAdapter/SessionStore -> API -> Core/System/Service -> Entity` 的依赖方向。
2. API 返回结构继续使用 `{success, message, data, errors}`。
3. 新增 GUI 操作必须以真实 `player_id`、`figure_id`、`proposal_id`、`war_id` 等 ID 驱动，不得使用人物名字符串作为业务参数。
4. 所有新增玩家可见文本默认走 i18n key；如 SA 认为某个子任务无法一次完成 i18n，应在任务书中明确临时范围和补齐任务。
5. 多玩家信息隔离必须延续：派系金库、人物私产等私有信息只对本派系可见。
6. 每个子任务都必须包含 GUI 层测试或可替代的 API/Adapter 测试，并说明是否需要项目负责人真实窗口人工确认。
7. GUI-P0-02C 已有元老院只读成果不得被无理由推倒；SA 应优先评估其可复用路径。

## 九、建议 Sprint 拆分方向

请 SA 审查后给出最终拆分。PM 建议先按以下方向评估：

| 子任务 | 建议目标 | 验证闭环 |
|---|---|---|
| GUI-P0-03A | OPC-01 界面基线确认与主壳差异审查 | 项目负责人确认界面任务边界。 |
| GUI-P0-03B | GuiApiAdapter 增量第一批 + 元老院交互化 | 可完成提案、表决、否决、结算的最小闭环。 |
| GUI-P0-03C | 广场阶段 GUI 轮流操作闭环 | 解雇、市场、竞标/认购、凯旋投票、结算。 |
| GUI-P0-03D | 战斗阶段 GUI 与 combat_api 边界 | 可查看战争并逐场执行战斗裁定。 |
| GUI-P0-03E | 收入阶段 GUI 与 revenue view API | 可查看财政明细并确认收入结算。 |
| GUI-P0-03F | 决算阶段 GUI 与年度推进展示 | 可展示决算结果并进入下一年。 |
| GUI-P0-03G | i18n、底部查询栏、多玩家最终打磨 | 全局查询入口、语言包、权限与刷新回归。 |

如果 SA 认为某个子任务过大，请继续拆小；如果发现已有 GUI-P0-02C 子任务能覆盖部分目标，请明确合并或替代关系。

## 十、测试要求

SA 后续给 CGT-01 的每个开发任务书至少应包含：

- 对应 API 测试。
- `src/tests/test_gui` 中的 QML/Adapter/Session 测试。
- 涉及阶段的 CLI/命令层回归测试，确保 GUI 不破坏 CLI。
- 必要时运行 full `src/tests`。
- `git diff --check`。
- 若涉及真实视觉布局，标记“待项目负责人 Windows GUI 手工确认”。

## 十一、验收标准

本 PM 意图包的验收标准是：

1. SA 输出界面确认包，并列出需要项目负责人确认的问题。
2. SA 明确 OPC-01 方案与当前 GUI 基线的复用/调整/替换关系。
3. SA 给出可逐个闭环的小 Sprint 拆分方案。
4. 项目负责人确认任务界面后，SA 再向 CGT-01 发布第一份技术开发任务书。
5. CGT-01 不需要自行决定界面主方案、优先级或 API 边界。

## 十二、SA 期望回执格式

请 SA 按以下格式回执 PM：

```text
Decision: READY_FOR_UI_CONFIRMATION / RETURN_FOR_PM_CLARIFICATION / DEFER

Reasons:

Files reviewed:

OPC-01 design summary:

Relationship to current GUI baseline:

Interface confirmation checklist for project owner:

Proposed Sprint/subtask split:

Recommended first CGT-01 task after confirmation:

API and architecture boundary risks:

Items requiring project owner confirmation:

Items explicitly not for CGT yet:
```