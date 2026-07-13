# OC GUI v3.25.1 Mapping / Gap / Plan 指令

任务编号：GUI-P0-MAPPING-GAP-PLAN-2026-07-10  
任务名称：EOR GUI v3.25.1 控件/API 对齐、DTO 缺口与阶段集成计划  
任务类型：架构审计 / GUI 改造前置规划 / 文档同步  
优先级：P0  
目标版本：MVP 0.9 GUI 重建准备阶段  
任务发起：GUI 开发顾问 / Codex  
执行对象：OC  

## 一、背景说明

根据 `OC_GUI_v3.25.1_重建可行性审计报告_2026-07-10.md`，顾问正式确认后续 GUI 改造采用 **B 路线**：

> 保留启动入口、Adapter、Store 等连接层，重建 QML 页面与组件。

本决策含义如下：

- 保留 `GuiApp`、`GuiSessionStore`、`GuiApiAdapter`、API/DTO、测试入口和本地化机制。
- 重建或大改 QML Shell、页面、阶段组件和视觉组件。
- 不重写 Core、System、Service、Entity。
- 不绕过现有 API。
- 不直接照 HTML 外观实现按钮和功能，必须先完成 GUI 控件与后端能力对齐。

下一步不进入编码。OC 需先输出三份对齐文件，为后续新 Shell 和天命阶段 Vertical Slice 提供依据。

## 二、任务目标

请 OC 基于以下输入完成 GUI v3.25.1 的完整对齐审计：

1. `EOR_GUI_Prototype_v3.25.1.html`
2. `EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md`
3. 当前 `src/ui/gui/` 中的 Store / Adapter / QML 结构
4. 当前 `src/api/` 中可供 GUI 使用的 API / DTO
5. 既有 GUI 映射和审计资料

本任务必须输出：

1. `GUI_CONTROL_MAPPING_MATRIX.md`
2. `GUI_DTO_GAP_REPORT.md`
3. `GUI_PHASE_INTEGRATION_PLAN.md`

三份文件完成并经顾问审阅前，不得开始新 Shell 或天命阶段 Vertical Slice 编码。

## 三、依据文档

| 类型 | 路径 |
| --- | --- |
| B 路线审计报告 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/OC_GUI_v3.25.1_重建可行性审计报告_2026-07-10.md` |
| GUI 交接报告 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI_Codex_Handover_2026-07-10.md` |
| 目标 HTML 原型 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI_Prototype_v3.25.1.html` |
| GUI 设计规范 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md` |
| 既有 GUI 设计文档 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI设计文档.md` |
| 既有 GUI/API 映射 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_UI_API_Mapping.md` |
| 既有 GUI/代码审计 | `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_Code_Alignment_Audit.md` |

请至少检查以下代码路径：

| 类型 | 路径 |
| --- | --- |
| GUI 连接层 | `src/ui/gui/` |
| QML Shell / 页面 / 组件 | `src/ui/gui/qml/` |
| GUI Adapter | `src/ui/gui/api_adapter.py` |
| GUI Store | `src/ui/gui/session_store.py` |
| GUI i18n | `src/ui/gui/localization.py`, `src/ui/gui/qml/i18n/GuiText.qml` |
| API 层 | `src/api/` |
| GUI 测试 | `src/tests/test_gui/` |

## 四、允许修改范围

本任务只允许新增或更新以下三份文档：

| 文件 | 目标 |
| --- | --- |
| `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_CONTROL_MAPPING_MATRIX.md` | GUI 元素逐项映射矩阵 |
| `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_DTO_GAP_REPORT.md` | DTO / API / Adapter 缺口报告 |
| `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_PHASE_INTEGRATION_PLAN.md` | 阶段接入顺序与 Vertical Slice 计划 |

除上述三份文档外，不得修改其他文件。

## 五、禁止事项

1. 不得修改 Core、System、Service、Entity。
2. 不得修改 API、Adapter、Store。
3. 不得修改 QML 或 Python GUI 代码。
4. 不得开始新 Shell 实现。
5. 不得开始天命阶段 Vertical Slice 实现。
6. 不得基于 HTML 外观直接假定后端能力存在。
7. 不得把 placeholder 控件标记为已实现功能。
8. 不得建议 GUI 调用 CLI Command。
9. 不得建议 GUI 直接读取或修改 Core 私有字段。
10. 不得建议 GUI 复制阶段、权限、投票、收入、战争等核心规则。
11. 不得忽略多玩家信息隔离、阶段限制、权限限制、disabled reason、empty state、error state。

## 六、实现要求

### 6.1 `GUI_CONTROL_MAPPING_MATRIX.md`

请从 `EOR_GUI_Prototype_v3.25.1.html` 出发，逐区域扫描全部可见 GUI 元素。

必须覆盖：

- 顶栏全局状态
- 左侧 7 阶段导航
- 中央阶段业务区
- 右侧状态 / 权限 / 日志区
- 底部查询 / 操作栏
- Modal / Overlay
- 表格
- 列表
- 卡片
- 按钮
- disabled 状态
- empty 状态
- error 状态
- 纯静态文本

每个 GUI 元素至少记录以下字段：

| 字段 | 说明 |
| --- | --- |
| GUI Element | 控件、信息块、卡片、按钮、表格、弹窗等 |
| Region | TopBar / PhaseRail / CenterStage / ContextPanel / BottomBar / Modal |
| Type | Action / Read-only / Placeholder / Static Text |
| Displayed Data | 显示内容 |
| Data Source | Store / Adapter / API / Static / Unknown |
| DTO Field | 对应 DTO 字段，没有则写 N/A |
| API / Adapter | 对应 API 或 Adapter 方法，没有则写 N/A |
| Action | 点击或交互行为，没有则写 N/A |
| Phase Rule | 阶段限制 |
| Permission Rule | 权限限制 |
| Enabled Rule | 启用条件 |
| Disabled Reason | 禁用原因来源 |
| Empty State | 空状态表现 |
| Error State | 错误状态表现 |
| Backend Status | Existing / Adapter Gap / DTO Gap / Backend Gap / Deferred Placeholder / Pure Static UI Text |
| Implementation Status | Reuse / Rebuild QML / New API Needed / Deferred |
| Evidence | 文档或代码路径证据 |

要求：

1. 不允许只做概览表，必须逐控件、逐信息块登记。
2. 对 HTML 中仅为视觉占位的元素，明确标记 `Deferred Placeholder`。
3. 对纯说明文字、标题、装饰标签，明确标记 `Pure Static UI Text`。
4. 对可以由现有 Store / Adapter / API 支撑的元素，明确标记 `Existing`。
5. 对需要 Adapter 暴露但后端已有能力的元素，标记 `Adapter Gap`。
6. 对 API 返回中缺字段的元素，标记 `DTO Gap`。
7. 对后端当前缺能力的元素，标记 `Backend Gap`。

### 6.2 `GUI_DTO_GAP_REPORT.md`

请基于 Mapping Matrix 汇总 DTO / API / Adapter 缺口。

报告至少包含：

| 缺口编号 | GUI 需求 | 当前状态 | 缺口类型 | 涉及 API/DTO/Adapter | 建议处理 | 优先级 | 是否阻塞 Vertical Slice |
| --- | --- | --- | --- | --- | --- | --- | --- |

缺口类型建议使用：

- DTO Field Missing
- Adapter Method Missing
- API Missing
- API Exists But Shape Mismatch
- Permission Field Missing
- Disabled Reason Missing
- Empty/Error State Missing
- Backend Capability Missing
- Deferred Placeholder

请特别检查：

1. 顶栏是否缺少稳定度、战争数、影响力等状态字段。
2. 阶段导航是否已有阶段状态、当前阶段、已完成/锁定状态。
3. 天命阶段是否已有完整 DTO 和 action_result。
4. 人口阶段是否已有庆典、投票、完成阶段相关 DTO。
5. 元老院阶段是否只有只读 DTO，交互式提案/表决/否决是否缺口。
6. 收入、广场、战争、决算是否属于 Backend Gap 或 Deferred Placeholder。
7. 底部 12 个查询中哪些已有 API，哪些为 placeholder。
8. 多玩家视角过滤是否需要额外 DTO 字段支撑。
9. disabled reason 是否能被所有 action 统一消费。
10. empty/error 状态是否有统一字段或前端规则。

### 6.3 `GUI_PHASE_INTEGRATION_PLAN.md`

请基于 Mapping Matrix 和 DTO Gap Report 制定阶段集成计划。

必须包含：

1. B 路线确认：
   - 保留：GuiApp / GuiSessionStore / GuiApiAdapter / API / DTO / 测试入口。
   - 重建：QML Shell / 页面 / 阶段组件 / 视觉组件。

2. 推荐实施顺序：
   - Phase 0：Mapping & Gap Review。
   - Phase 1：New Global Shell。
   - Phase 2：One Phase Vertical Slice。
   - Phase 3：Phase-by-Phase Expansion。

3. Global Shell 接入顺序：
   - Theme.qml 色彩体系。
   - GameShell.qml 五区布局。
   - PhaseRail.qml 44px 阶段导航。
   - TopStatusBar.qml 深朱红 HUD。
   - ContextPanel.qml 右侧状态 / 日志。
   - BottomQueryBar.qml 底部查询栏。
   - Overlay / Modal 统一视觉。

4. 第一个 Vertical Slice 候选：
   - 默认候选为天命阶段。
   - 请确认是否仍推荐天命阶段。
   - 如果不推荐，必须说明替代阶段和理由。

5. 每个阶段的接入计划：

| 阶段 | 当前后端状态 | GUI 当前状态 | 建议接入时机 | 前置条件 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 天命 |  |  |  |  |  |
| 收入 |  |  |  |  |  |
| 广场 |  |  |  |  |  |
| 人口 |  |  |  |  |  |
| 元老院 |  |  |  |  |  |
| 战争 |  |  |  |  |  |
| 决算 |  |  |  |  |  |

6. 新 Shell 和天命 Vertical Slice 的验收标准草案。

## 七、调试日志要求

本任务不修改代码，因此不要求新增运行时日志。

但三份文档中所有判断必须提供证据来源：

- HTML 元素位置或描述。
- 设计规范章节。
- Store Property / Slot 名称。
- Adapter 方法名称。
- API 函数名称。
- DTO 字段名称。
- 测试文件名称。

凡是无法确认的内容，不得臆测，应标记为 `Unknown` 或 `Decision Needed`。

## 八、测试要求

本任务不要求新增或修改测试。

但 `GUI_PHASE_INTEGRATION_PLAN.md` 必须列出后续编码阶段的最低测试保护线，包括：

| 阶段 | 必须通过的测试 | 备注 |
| --- | --- | --- |
| Phase 1 New Shell | QML 启动测试、Session API 测试、i18n 硬编码扫描 | 需要更新 objectName 断言 |
| Phase 2 天命 Vertical Slice | Adapter 测试、Session API 测试、QML 启动测试、天命 API 测试 | 确认 Store → Adapter → API → QML 闭环 |
| Phase 3 阶段扩展 | 相关阶段 API 测试 + GUI slice 测试 | 每阶段单独增加保护 |

请同时说明现有测试是否足以覆盖：

- GUI 启动。
- Adapter 调用。
- Session DTO。
- 多玩家信息过滤。
- QML 无散落中文硬编码。
- disabled reason 展示。
- empty/error 状态。

## 九、验收标准

| 验收项 | 标准 |
| --- | --- |
| 文件完整 | 三份指定文件均已输出到 GUI 需求目录 |
| Mapping 完整 | 覆盖 v3.25.1 HTML 的主要区域、控件、信息块、按钮、状态 |
| 分类清楚 | 每个元素均标记 Existing / Adapter Gap / DTO Gap / Backend Gap / Deferred Placeholder / Pure Static UI Text |
| 证据充分 | 关键判断有文档或代码路径证据 |
| 缺口可执行 | DTO / API / Adapter 缺口可转化为后续开发任务 |
| 阶段计划明确 | 明确新 Shell、天命 Vertical Slice、后续阶段扩展顺序 |
| 架构边界正确 | 保持 `GUI/QML -> GuiSessionStore -> GuiApiAdapter -> API -> Core/System/Service -> Entity` |
| 无越界建议 | 不建议 GUI 调 CLI、不建议 GUI 读私有字段、不建议 GUI 复制核心规则 |
| 决策点明确 | 明确哪些事项需要顾问或项目负责人确认 |

## 十、交付物

请输出以下三份文件：

1. `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_CONTROL_MAPPING_MATRIX.md`
2. `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_DTO_GAP_REPORT.md`
3. `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_PHASE_INTEGRATION_PLAN.md`

每份文件末尾请附：

- 审计执行人。
- 审计日期。
- 代码基准分支 / commit。
- 未确认事项。
- 建议顾问决策点。

## 十一、后续流程

1. OC 输出三份对齐文件。
2. 顾问审阅并确认是否允许进入编码。
3. 若通过，顾问输出下一份指令：`New Global Shell + Mortality Vertical Slice`。
4. OC 按下一份指令开始 QML 重建，不提前越界实现其他阶段。
