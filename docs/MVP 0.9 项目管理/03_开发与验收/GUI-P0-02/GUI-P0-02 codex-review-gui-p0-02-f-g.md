# Codex Review — GUI-P0-02-F/G Phase 1 Layout Contract & Shell Skeleton

日期：2026-07-12  
评审人：Codex / OpenClaw Main Session  
评审对象：SA GUI-P0-02-F/G 交付件  
评审结论：退回修改  

## 1. 审查对象

本次审查覆盖以下交付件：

| 类型 | 路径 | 状态 |
| --- | --- | --- |
| 布局契约 | `E:\OpenClaw\Projects\EOR\agents\SA\reports\GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` | 已提交 |
| SA 报告 | `E:\OpenClaw\Projects\EOR\agents\SA\reports\2026-07-11-sa-f-g-report.md` | 已提交 |
| Shell 新增 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\shell\StageDesktop.qml` | 已提交 |
| Shell 修改 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\shell\GameShell.qml` | 已提交 |
| 右栏修改 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\shell\ContextPanel.qml` | 已提交 |
| 底栏修改 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\shell\BottomQueryBar.qml` | 已提交 |
| 天命阶段修改 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\stages\MortalityStage.qml` | 已提交 |

审查依据：

- `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_SA-DA_开发任务书规范模板_v1.1.md`
- `E:\OpenClaw\Projects\EOR\bible\EOR_OpenClaw_Project_Management_Standard_v0.9_Trial_Revision_4.md`
- Phase 1 目标截图与 v3.25.1 HTML 目标形态

## 2. 总体结论

本批交付不建议进入 `GUI-P0-02-H`。

SA 已经形式上响应 v1.1 要求，产出了布局契约、`StageDesktop.qml`、Shell 组件改造和测试报告。但交付没有达到 v1.1 的核心目标：把 v3.25.1 目标形态锁定为可执行布局契约，并通过静态 Shell 骨架限制 DA 自由重排页面。

主要阻塞点是：布局契约采用了“原始 CSS 层，排除视觉抛光/Codex/HUD 密度覆盖”的基线，而当前项目目标是已经多轮迭代稳定的 v3.25.1 GUI 视觉形态。该基线选择会继续诱导 DA 实现偏离目标截图。

## 3. 关键不符合项

### 3.1 布局契约目标基线错误

`GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` 明确写明：

```text
原型来源：EOR_GUI_Prototype_v3.25.1.html（原始 CSS 层，排除视觉抛光/Codex/HUD密度覆盖）
```

这与当前 GUI 改造目标不一致。项目目标不是复刻 HTML 的原始 CSS 层，而是复刻 v3.25.1 目标 GUI 视觉形态。

由此导致契约采用：

- TopStatusBar：48px
- PhaseRail：44px
- RightStatusPanel：240px

而此前目标截图中的 v3.25.1 视觉形态更接近：

- 顶栏更高、更有 HUD 分块感
- 左侧阶段栏不是 44px 的纯圆形图标窄栏
- 右侧栏宽度和内容密度更接近 v3.25.1 refit，而非原始 CSS

该问题属于目标基线错误，不是小范围视觉偏差。

### 3.2 SA 报告已承认阻塞，却仍建议进入下一步

`2026-07-11-sa-f-g-report.md` 中已写明：

```text
Layout contract uses original CSS values, not v3.25.1 visual refit overrides.
Immediate prerequisite: Resolve unresolved issue #4 before proceeding with DA content filling.
```

这说明 SA 自己已识别出 F/G 交付件不能直接支撑 H 阶段。但报告仍给出了 `GUI-P0-02-H` 的下一步建议，存在门禁判断不一致。

验收意见：在基线冲突解决前，不应启动 H 阶段。

### 3.3 StageDesktop 槽位没有成为唯一承载结构

`StageDesktop.qml` 已定义：

- `stageHeaderSlot`
- `stageInstructionSlot`
- `stageContentSlot`
- `stageActionSlot`

但实际实现中：

- `stageInstructionSlot` 默认 `visible: false`
- `stageActionSlot` 默认 `visible: false`
- `MortalityStage.qml` 内部仍自建 `mortalityHeaderSlot`、`mortalityInstructionSlot`、`mortalityContentSlot`、`mortalityActionSlot`
- 天命按钮仍在 `MortalityStage.qml` 内部调用 `sessionStore.doExecuteMortality()`

这说明当前只是“形式上有 StageDesktop 槽位”，但阶段内容仍由 `MortalityStage.qml` 自行组织。它没有真正实现 v1.1 要求的“DA 只能在 SA 指定槽位中填充内容”。

验收意见：StageDesktop 槽位必须成为阶段内容的唯一主承载结构；阶段组件不得继续自建一套平行槽位体系。

### 3.4 顶部状态栏栏位稳定性不符合目标

`TopStatusBar.qml` 中存在两个问题：

- 稳定度被硬编码为 `78%`
- 战争栏通过 `visible: (sessionStore.warCount || 0) > 0` 控制显示

v3.25.1 顶部栏要求栏位顺序和占位稳定。缺失数据应使用安全占位，不应隐藏目标栏位，也不应在 Shell 层硬编码产品状态。

验收意见：TopStatusBar 应保留目标栏位结构，缺值使用 `--` 或 Store 派生字段，避免硬编码和条件隐藏核心栏位。

### 3.5 缺少像素级验收表和实际截图证据

v1.1 要求 GUI 任务必须提交 A-F 区域像素级验收表：

| 区域 | 契约值 | 实际值 | 误差 | 是否通过 |
| --- | --- | --- | --- | --- |
| A 顶栏 |  |  |  |  |
| B 左栏 |  |  |  |  |
| C 中央桌面 |  |  |  |  |
| D 右栏 |  |  |  |  |
| E 底栏 |  |  |  |  |
| F 主操作 |  |  |  |  |

本批报告只提供测试结果，没有提供 1440x900 实际截图、A-F 区域实测值、误差说明和是否通过结论。

验收意见：没有像素级验收表，不能证明 Shell 已经按契约落地。

## 4. 可保留成果

以下成果方向正确，可以作为返修基础保留：

1. `StageDesktop.qml` 的组件拆分方向正确。
2. Shell 中引入 A-F 区域概念是正确的。
3. `ContextPanel.qml` 增加右侧 section objectName 有价值。
4. `BottomQueryBar.qml` 已避免状态点语义，改为图标加文字查询入口，方向正确。
5. 测试报告提供了基本回归信息，可保留为功能未破坏的参考证据。

但上述成果不能抵消布局契约基线错误。

## 5. 返修要求

### 5.1 返修 F：重做 Phase 1 布局契约

SA 必须返修：

```text
E:\OpenClaw\Projects\EOR\agents\SA\reports\GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md
```

要求：

1. 明确基线为 v3.25.1 目标截图 / visual-refit 形态。
2. 不得再写“排除视觉抛光/Codex/HUD 密度覆盖”。
3. 重新确认 A-F 区域尺寸：
   - A TopStatusBar
   - B PhaseRail
   - C StageDesktop
   - D RightStatusPanel
   - E BottomQueryBar
   - F MainAction
4. 对 BottomQueryBar 如果 HTML DOM 不存在，必须将 v3.25.1 目标截图与现有 GUI 设计决策作为契约来源，而不是标记为弱约束。
5. 输出完整颜色、字体、间距、栏位顺序和禁止偏移清单。

### 5.2 返修 G：重做静态 Shell 骨架

SA/DA 必须返修：

- `StageDesktop.qml`
- `GameShell.qml`
- `ContextPanel.qml`
- `TopStatusBar.qml`
- 必要时同步 `BottomQueryBar.qml`

要求：

1. `StageDesktop` 的四个槽位必须真实承载阶段内容。
2. 不得让 `MortalityStage.qml` 自建平行槽位体系。
3. `StageActionSlot` 必须承载主操作按钮。
4. `StageInstructionSlot` 必须承载步骤条。
5. `StageHeaderSlot` 必须承载阶段徽章、标题、说明。
6. `StageContentSlot` 只承载阶段内容区。
7. 顶栏核心栏位必须稳定显示，缺值使用安全占位。

### 5.3 补充验收证据

返修后必须补交：

1. 1440x900 实际运行截图。
2. A-F 区域像素级验收表。
3. 修改文件清单。
4. 测试命令与实际结果。
5. 未解决问题清单。

## 6. 下一步门禁

当前状态：

```text
GUI-P0-02-F/G：退回修改
GUI-P0-02-H：暂缓，不得启动
```

进入 H 阶段的前置条件：

1. Phase 1 布局契约重写完成，并明确采用 v3.25.1 目标形态。
2. 静态 Shell 骨架通过截图验收。
3. A-F 区域像素级验收表通过。
4. StageDesktop 槽位成为阶段内容唯一主承载结构。
5. TopStatusBar 栏位稳定性问题修复。

## 7. 给 SA/OC 的简短指令

请不要继续让 DA 在当前 F/G 基础上进入 H 阶段。

请先发布 `GUI-P0-02-FR1/G-R1` 返修任务：

- FR1：重做 Phase 1 布局契约，基线改为 v3.25.1 目标截图 / visual-refit。
- G-R1：按新契约返修静态 Shell 骨架，确保 StageDesktop 槽位真实承载内容。
- 返修交付必须包含 1440x900 截图和 A-F 像素级验收表。

只有 FR1/G-R1 验收通过后，才允许启动 `GUI-P0-02-H`。
