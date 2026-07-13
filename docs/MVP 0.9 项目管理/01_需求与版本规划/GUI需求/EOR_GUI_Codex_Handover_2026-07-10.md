# EOR GUI 工作交接报告（交接给 CODEX）

**日期：** 2026-07-10  
**项目：** Eagle of Rome（EOR）  
**交接范围：** GUI 视觉基线、HTML 原型、GUI 与后端功能对齐方法  
**当前状态：** GUI 视觉方向已确认；下一阶段必须先完成 GUI-Control/API Mapping，不应直接开始全量 GUI 实现。

## 1. 本轮目标

本轮对比了 `EOR_GUI_Prototype_v3.2.4` 与 `EOR_GUI_Prototype_Codex_v4.0`。目标是在不改变 v3.2.4 界面布局、功能、DOM 和 JS 行为逻辑的前提下，吸收 v4.0 的视觉质量与层次感。

最终确认的新视觉基线为 **v3.25.1**。

## 2. 已确认的设计决策

### 2.1 保留 v3.2.4 产品模型

保留顶栏、左侧 7 阶段导航、中央阶段业务区、右侧状态/日志区、底部查询/操作栏，以及现有阶段内容、按钮、交互逻辑和信息密度。

### 2.2 吸收 v4.0 的视觉层级，而非复制其布局

正式材质体系：

> **深墨环境壳层 → 象牙白阶段桌面 → 羊皮纸事务卡片 → 朱红/铜金操作元素**

- 深墨色：应用外壳、左侧阶段导航、右侧状态与日志区。
- 深朱红：顶栏、底部查询栏、关键标题和主操作。
- 象牙白：中央阶段区，模拟共和国议事桌面。
- 羊皮纸：法案、候选人、战争、收入、事件等具体事务对象。
- 铜金：边框、强调、选中状态和身份提示。

核心语义：

> **桌面是空间，羊皮纸是对象。**

### 2.3 v3.25

在 v3.2.4 基础上完成视觉升级：深色外壳、象牙白阶段桌面、羊皮纸事务卡，并强化朱红、铜金、阴影、边框和 hover 层次。不做功能重构。

### 2.4 v3.25.1

继续优化顶部和底部 HUD：

- 顶栏控件增加高度和填充。
- Logo、状态块和回合信息更饱满。
- 底部查询按钮均分并填满查询栏。
- 增强 hover 和边框反馈。
- 不改变布局、功能、DOM 或 JS。

**v3.25.1 是后续开发的正式视觉参考原型。**

## 3. 后续开发基线

后续 CODEX / OC 应同时使用：

1. `EOR_GUI_Prototype_v3.25.1.html`
2. `EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md`

规范定义原则、边界和验收标准；HTML 原型定义已确认的视觉效果、信息密度和控件表现。

不得仅凭 HTML 外观推断后端功能。

## 4. 下一阶段核心问题

下一阶段重点从“视觉设计”转为：

> **确保 GUI 上每一个控件和信息显示，都与现有代码功能、API、DTO、权限和阶段状态正确匹配。**

禁止直接“照 HTML 写 GUI”，因为 HTML 中可能存在视觉占位，后端可能缺少 API，信息可能受玩家权限限制，按钮可能仅在特定阶段启用。

## 5. 强制工作方法：GUI Mapping Matrix

全量 GUI 实现前必须先输出：

1. `GUI_CONTROL_MAPPING_MATRIX.md`
2. `GUI_DTO_GAP_REPORT.md`
3. `GUI_PHASE_INTEGRATION_PLAN.md`

每个 GUI 元素至少记录：

| 字段 | 内容 |
| --- | --- |
| GUI Element | 控件或信息块 |
| Region | 顶栏/阶段导航/中央区/右栏/底栏 |
| Type | Action/Read-only/Placeholder |
| Displayed Data | 显示内容 |
| Data Source | 数据来源 |
| DTO Field | DTO 字段 |
| API / Adapter | API 或 Adapter |
| Action | 点击行为 |
| Phase Rule | 阶段限制 |
| Permission Rule | 权限限制 |
| Enabled Rule | 启用条件 |
| Disabled Reason | 禁用原因 |
| Empty State | 空状态 |
| Error State | 错误状态 |
| Backend Status | Existing/Gap/Deferred |
| Implementation Status | 接入状态 |

## 6. HTML 原型元素必须分类

### A. 真实功能控件

例如执行阶段动作、提交提案、投票、招募、任命、战争操作、进入下一阶段。

必须有明确 API/Adapter、阶段限制、权限限制以及成功/失败反馈。

### B. 只读信息显示

例如国库、派系资金、当前阶段、当前玩家、战争状态、候选人列表和日志。

必须来自稳定 DTO/ViewModel；不得直接读取 Core 私有字段；不得绕过隐藏信息权限。

### C. 占位/未实现控件

后端尚无能力时必须标记 Deferred/Not Implemented，保持 disabled 并显示原因，不得伪装为已完成。

## 7. 强制架构边界

```text
GUI / QML
↓
GuiSessionStore
↓
GuiApiAdapter
↓
API
↓
Core / System / Service
↓
Entity
```

禁止：

- GUI 调用 CLI Command。
- GUI 读取或修改 Core 私有字段。
- GUI 复制元老院、收入、广场、战争等核心规则。
- GUI 根据中文文本判断业务逻辑。
- GUI 自行推断权限。
- GUI 暴露其他玩家隐藏资产或决策。
- GUI 假装未实现后端功能已经可用。

GUI 应消费明确状态，例如 `current_phase`、`current_player`、`is_enabled`、`disabled_reason`、`visible_items`、`permitted_actions` 和 `action_result`。

## 8. 推荐开发顺序

### Phase 0 — Mapping & Gap Analysis

先完成三份报告。在评审通过前，不进入全量 GUI 实现。

### Phase 1 — Global Shell

依次接入：

1. 顶栏全局状态。
2. 左侧阶段导航。
3. 右侧状态/日志。
4. 底部查询按钮。

### Phase 2 — One Phase Vertical Slice

只选择一个阶段完成完整闭环，验证：

1. 当前阶段正确。
2. 当前玩家正确。
3. 决策数据可见。
4. 按钮权限正确。
5. 调用正确 API。
6. 结果在中央区可见。
7. 日志产生反馈。
8. 失败原因清楚。
9. 下一阶段入口明确。
10. CLI、自动模式、多玩家权限不退化。

### Phase 3 — Expand Phase by Phase

按真实流程逐阶段接入：天命、收入、广场、人口、元老院、战争、决算。复杂阶段继续拆分子功能。

## 9. 建议 CODEX 下一任务

任务名称：

# GUI-Control/API Alignment Audit

目标：

- 扫描 v3.25.1 HTML 原型中的全部控件和信息块。
- 对照当前 EOR 代码、API、DTO、GuiApiAdapter、GuiSessionStore。
- 建立完整 Mapping Matrix。
- 标记 Existing、Adapter Gap、DTO Gap、Backend Gap、Deferred Placeholder。
- 提出第一个 Vertical Slice 候选方案。
- 审计阶段不得擅自修改 Core 规则。

## 10. 可直接使用的 CODEX / OC 指令

```markdown
# EOR GUI-Control/API Alignment Audit

## Objective

Use the approved GUI baseline:

- EOR_GUI_Prototype_v3.25.1.html
- EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md

Audit the current EOR codebase and establish a complete mapping between visible GUI elements and implemented backend capabilities before full GUI integration begins.

## Mandatory Rule

Do not implement GUI controls directly from visual appearance alone.

Every visible control, status field, table, card, modal, and action button must be classified as one of:

1. Existing API / DTO-backed capability
2. Existing backend capability requiring adapter exposure
3. Backend / DTO capability gap
4. Deferred / placeholder UI
5. Pure static UI text

## Required Deliverables

1. GUI_CONTROL_MAPPING_MATRIX.md
2. GUI_DTO_GAP_REPORT.md
3. GUI_PHASE_INTEGRATION_PLAN.md

Save all report files into the designated EOR working directory.

## Required Audit Coverage

- Top bar global state
- Left phase rail
- Central phase pages
- Right status / permission / log panel
- Bottom query controls
- Modals
- Tables
- Action buttons
- Disabled states
- Empty states
- Error states

## For Every GUI Element Identify

- data source
- DTO field
- API / adapter
- action behavior
- phase rule
- permission rule
- enabled rule
- disabled reason
- empty state
- error state
- backend implementation status

## Architecture Boundary

GUI/QML
↓
GuiSessionStore
↓
GuiApiAdapter
↓
API
↓
Core/System/Service
↓
Entity

## Prohibited

- GUI calling CLI commands
- GUI reading Core private fields
- GUI duplicating game rules
- GUI inferring permissions from display text
- GUI exposing hidden player information
- GUI pretending unimplemented backend features are working

## Implementation Gate

Do not begin full GUI implementation until the Mapping Matrix, DTO Gap Report, and Phase Integration Plan have been reviewed.

After review, implement one phase vertical slice only.
```

## 11. 交接结论

本轮已完成：

- v3.2.4 与 v4.0 视觉方向比较。
- 确认不重构 v3.2.4 产品模型。
- 确认深墨外壳 + 象牙白阶段桌面 + 羊皮纸事务卡。
- 确认顶部/底部 HUD 应更饱满并填满栏位。
- 输出并确认 v3.25。
- 输出并确认 v3.25.1。
- 更新 GUI 设计规范。
- 确立 GUI 与后端磨合方法。

**下一阶段重点：GUI-Control/API 对齐治理。**

CODEX 必须先做 Mapping 和 Gap Audit，再开始单阶段 Vertical Slice，不应直接启动完整 GUI 开发。
