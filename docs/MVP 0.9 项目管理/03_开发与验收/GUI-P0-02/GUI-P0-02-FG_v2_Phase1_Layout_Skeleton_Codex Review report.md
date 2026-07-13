# Codex 正式验收 — GUI-P0-02-F/G Phase 1 Layout Contract & Shell Skeleton v2

日期：2026-07-12  
评审人：Codex / OpenClaw Main Session  
评审对象：`GUI-P0-02-F-G_Phase1_Layout_Skeleton_SA报告_v2.md`  
结论：有条件通过，允许 OC 启动下一轮受控执行，但不允许直接视为 F/G 完全闭环

正式应归档路径：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\Codex_Review_GUI-P0-02-FG_v2_Phase1_Layout_Skeleton_2026-07-12.md
```

当前写入路径：

```text
E:\OpenClaw\Projects\EOR\workspace\Codex_Review_GUI-P0-02-FG_v2_Phase1_Layout_Skeleton_2026-07-12.md
```

说明：当前会话尝试写入产品目录时返回 `Access denied`，因此本文件先作为待归档正式稿保存在 OpenClaw workspace。

## 1. 审查范围

本次验收覆盖以下交付件：

| 类型 | 路径 |
| --- | --- |
| SA v2 报告 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\GUI-P0-02-F-G_Phase1_Layout_Skeleton_SA报告_v2.md` |
| 布局契约 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\00_GUI产品基线\GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` |
| QML Shell | `src/ui/gui/qml/shell/GameShell.qml` |
| StageDesktop | `src/ui/gui/qml/shell/StageDesktop.qml` |
| 顶栏 | `src/ui/gui/qml/shell/TopStatusBar.qml` |
| 左栏 | `src/ui/gui/qml/shell/PhaseRail.qml` / `components/PhaseRailIcon.qml` |
| 右栏 | `src/ui/gui/qml/shell/ContextPanel.qml` |
| 底栏 | `src/ui/gui/qml/shell/BottomQueryBar.qml` |
| 天命阶段 | `src/ui/gui/qml/stages/MortalityStage.qml` |

审查依据：

- `EOR_GUI_SA-DA_开发任务书规范模板_v1.1.md`
- `EOR_OpenClaw_Project_Management_Standard_v0.9_Trial_Revision_4.md`
- v3.25.1 HTML / Codex v4.0 visual refit / HUD density override
- Phase 1 目标截图与当前 QML 实现

## 2. 总体结论

本次 v2 交付相较上一版有实质改进，已经修复最关键的基线错误：布局契约不再使用原始 CSS 的 48/44/240 方案，而是切换到 v3.25.1 visual refit / HUD density override 基线。

因此，F/G 不再需要整体退回重做。  
但本批交付仍存在三个未闭合点：

1. `StageDesktop` 槽位架构尚未真正成为唯一承载结构。
2. `TopStatusBar` 仍存在硬编码稳定度与战争栏条件隐藏问题。
3. 测试报告仍引用 prior baseline，没有证明当前 11 文件改动后的完整测试结果。

验收结论为：

```text
GUI-P0-02-F/G v2：有条件通过
OC：可以开始下一轮受控执行
但：不得直接进入无约束的 H 阶段功能扩展
```

## 3. 已通过项

### 3.1 布局契约基线已修正

新版 `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` 明确采用：

```text
EOR_GUI_Prototype_v3.25.1.html
Codex v4.0 visual refit + v3.25.1 HUD density override
Base viewport: 1440 × 900
```

关键参数已经回到目标形态：

| 区域 | v2 契约值 | 验收意见 |
| --- | --- | --- |
| A TopStatusBar | x=10, y=10, w=1420, h=62 | 通过 |
| B PhaseRail | x=10, y=82, w=92, h=736 | 通过 |
| C StageDesktop | x=112, y=82, w=1022, h=736 | 通过 |
| D ContextPanel | x=1144, y=82, w=286, h=736 | 通过 |
| E BottomQueryBar | x=10, y=828, w=1420, h=62 | 通过 |
| F MainAction | StageDesktop 内底部居中，180×34 | 方向通过 |

这解决了上一轮“错误使用原始 CSS 基线”的阻塞问题。

### 3.2 Shell 主布局已按 v3.25.1 目标值重建

`GameShell.qml` 当前已使用：

- 顶栏高度 62
- 左栏宽度 92
- 右栏宽度 286
- 底栏高度 62
- 外边距与区域间距 10

这与 v2 契约一致。

### 3.3 左侧 PhaseRail 已从圆形图标改为目标 pill 结构

`PhaseRail.qml` 与 `PhaseRailIcon.qml` 已实现：

- 92px 左栏
- 74×54 pill 按钮
- icon + label 常显
- done/current/todo 三态视觉
- 去除旧版 title 与底部按钮

该项通过。

### 3.4 右栏与底栏方向正确

`ContextPanel.qml` 已按 CurrentPhase / Operation / Progress / Player / EventLog 顺序组织。  
`BottomQueryBar.qml` 已恢复 12 个 icon + text 查询入口，并使用 v3.25.1 深色 HUD 底栏。

该项通过。

### 3.5 Theme token 化方向正确

`Theme.qml` 已建立 v3.25.1 色彩、字体、半径 token。后续 DA 应优先使用 `theme.*`，减少自由取色。

该项通过。

## 4. 未闭合问题

### 4.1 StageDesktop 槽位尚未真正成为唯一承载结构

`StageDesktop.qml` 已定义：

- `stageHeaderSlot`
- `stageInstructionSlot`
- `stageContentSlot`
- `stageActionSlot`

但实际 `GameShell.qml` 仍将 `MortalityStage` 整体放入 `stageContentSlot`，而 `MortalityStage.qml` 内部继续自建：

- `mortalityHeaderSlot`
- `mortalityInstructionSlot`
- `mortalityContentSlot`
- `mortalityActionSlot`

这意味着 v1.1 要求的“DA 只能在 StageDesktop 指定槽位内填充内容”尚未完全落地。

影响：

- 可能出现通用 StageHeader 与 MortalityStage 内部 Header 重复。
- StageInstructionSlot / StageActionSlot 在 Shell 层仍未实际启用。
- 下一步 H 阶段如果继续在 MortalityStage 内自建布局，会重新打开 DA 自由重排空间。

验收要求：下一轮必须优先完成槽位归位。

### 4.2 TopStatusBar 仍有两个栏位稳定性问题

`TopStatusBar.qml` 中：

```qml
statValue: "78%"
```

稳定度仍是硬编码。

同时：

```qml
visible: (sessionStore.warCount || 0) > 0
```

战争栏在 `warCount` 为 0 或缺失时仍会隐藏。v3.25.1 目标要求顶部栏位结构稳定，缺值应显示 `--` 或安全占位，不应删除栏位。

验收要求：下一轮修正为：

- 稳定度使用 Store 字段或安全占位。
- 战争栏始终占位显示，值为 `sessionStore.warCount || "--"`。

### 4.3 测试证据不足

SA v2 报告写明：

```text
773 tests passed on prior QML baseline.
The skeleton changes should require test updates...
```

这说明当前 11 个文件重写后，并没有在报告中给出新的完整测试结果。它是“预期需要更新测试”，不是“当前代码已完成测试闭环”。

验收要求：下一轮必须提供：

- GUI startup 测试结果。
- 更新后的 shell 尺寸测试结果。
- 相关 `test_gui` 测试结果。
- 若测试暂未更新，必须明确列为未闭合项。

## 5. 架构与边界判断

未发现 Core/System/Service/Entity 修改证据。  
未发现 QML 直接访问 Core 私有字段。  
QML 仍通过 `sessionStore` 调用 GUI Store 层，未见绕过 API/Adapter 的明显问题。

但需要注意：

- `MortalityStage.qml` 仍包含 `sessionStore.doExecuteMortality()` 调用。
- 这属于既有 Phase 1 功能绑定，不应在 F/G 静态骨架阶段继续扩散。
- 下一步如果进入 H，应把该调用归入正式 Store/API 绑定验收，而不是把它混在 Shell 骨架验收中。

## 6. 正式验收结论

```text
结论：有条件通过
范围：GUI-P0-02-F/G v2 可作为下一步受控执行基础
限制：不得宣布 F/G 完全闭环；不得直接开展无边界功能扩展
```

OC 可以开始执行，但应执行以下受控任务之一：

### 允许启动的任务

```text
GUI-P0-02-H0：Phase 1 Slot Consolidation & TopBar Stabilization
```

目标：

1. 将 MortalityStage 的 header / instruction / action 归位到 StageDesktop 四槽位。
2. 删除或降级 MortalityStage 内部平行槽位结构。
3. 修复 TopStatusBar 稳定度硬编码。
4. 修复战争栏条件隐藏。
5. 更新 shell 相关测试或提交未更新说明。

### 暂不建议启动的任务

```text
GUI-P0-02-H：Phase 1 天命内容填充与 Store/API 扩展
```

原因：StageDesktop 槽位尚未完全生效，若直接进入功能扩展，DA 仍可能继续在阶段组件内部自由重排布局。

## 7. 给 OC 的执行指令

请 OC 不要直接进入完整 H 阶段。  
请先发布并执行 `GUI-P0-02-H0` 小步修正任务。

任务边界：

- 只允许修改 QML Shell / MortalityStage / 相关 GUI 测试。
- 不允许修改 Core/System/Service/Entity。
- 不允许新增阶段业务规则。
- 不允许扩展查询功能。
- 不允许新增后端 API。

交付物：

1. H0 开发报告。
2. 修改文件清单。
3. 1440×900 实际运行截图。
4. A-F 像素级验收表。
5. GUI startup / shell tests 结果。
6. 未闭合问题清单。

## 8. 最终门禁

当前门禁状态：

| 项目 | 状态 |
| --- | --- |
| F：Layout Contract | 通过 |
| G：Static Shell Skeleton | 有条件通过 |
| H0：Slot Consolidation & TopBar Stabilization | 应立即启动 |
| H：功能填充与 Store/API 扩展 | H0 通过后再启动 |

最终答复：

```text
OC 可以开始执行，但应执行 H0 受控修正任务，而不是直接进入完整 H 阶段。
```
