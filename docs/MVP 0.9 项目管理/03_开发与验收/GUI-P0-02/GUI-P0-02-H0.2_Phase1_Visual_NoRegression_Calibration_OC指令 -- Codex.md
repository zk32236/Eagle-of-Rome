# OC 指令 — GUI-P0-02-H0.2 Phase 1 Visual No-Regression Calibration

日期：2026-07-12  
发布人：Codex / OpenClaw Main Session  
任务类型：Visual Calibration / Regression Fix  
目标对象：OC / SA / DA  
结论：H0.1 门禁已开，但 H 阶段实际截图出现视觉回退，必须先执行 H0.2 视觉不回退校准任务。

## 1. 任务背景

H0.1 已恢复 GUI startup 与完整回归：

```text
773 passed in 24.57s
```

但最新实测截图显示，Phase 1 天命界面出现视觉回退：

```text
C:\Users\Kerl\Downloads\GUI acutal phase 1 - 3.PNG
```

对照目标截图：

```text
C:\Users\Kerl\Downloads\GUI design - Phase 1.PNG
```

当前问题不是后端、Store 或 API 问题，而是 GUI 技术重构后缺少视觉回归保护，导致原本较正确的布局在槽位收束和后续绑定后发生偏移。

## 2. 必须遵守的资产规范

本任务必须遵守以下 OpenClaw Agent 资产规范：

```text
E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_Development_Governance_v1.0.md
E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_SA-DA_开发任务书规范模板_v1.2.md
```

本任务不要求把上述规范同步到产品目录。OpenClaw Agent 资产目录是唯一信源。

## 3. 本轮任务目标

启动：

```text
GUI-P0-02-H0.2_Phase1_Visual_NoRegression_Calibration
```

目标：

1. 修复 Phase 1 天命界面最新实测截图中的视觉回退。
2. 保持 H0/H0.1 已修复的槽位结构和测试基线。
3. 不改变 Core/System/Service/Entity。
4. 不扩展收入、广场、人口、元老院、战斗、决算等后续阶段功能。
5. 输出目标图 vs 实测图的 A-F 区域差异表。

## 4. 错误定位

本次错误属于：

```text
技术重构造成视觉回退
```

具体原因：

1. H0 将 header / instruction / content / action 技术上归入 `StageDesktop` 四槽位，但没有同步保护槽位内部视觉位置。
2. `StageActionSlot` 中主按钮位置接近视觉中心，而不是中央桌面底部居中。
3. `StageHeaderSlot` / `StageInstructionSlot` 内容可读性异常，徽章、标题、步骤条在实测截图中几乎半透明或弱化消失。
4. `StageContentSlot` 空状态提示漂浮在中央桌面中部偏左，没有形成目标稿中的上方说明卡/内容卡层级。
5. 左栏、右栏颜色向紫黑偏移，目标应更接近深墨/深棕 Roman HUD。
6. 自动测试通过没有覆盖视觉回退，导致问题进入实际运行截图阶段才暴露。

## 5. 保持项 / 允许改项 / 禁止改项 / 风险项

| 类型 | 区域 | 要求 |
| --- | --- | --- |
| 保持项 | A 顶栏 | 保持 62px 高度、分块 HUD、核心栏位稳定显示 |
| 保持项 | B 左栏 | 保持 92px 宽度、7 阶段 pill 按钮、icon + label 常显 |
| 保持项 | E 底栏 | 保持 62px 高度、12 个查询入口、icon + text 形式 |
| 保持项 | H0/H0.1 | 保持 `773 passed` 回归基线，不重新引入 QML startup failure |
| 允许改项 | C 中央桌面 | 调整 header / instruction / content / action 的垂直布局、可见性、z-order、颜色和 padding |
| 允许改项 | D 右栏 | 校正颜色、section 密度、事件日志比例，但不得改变 section 顺序 |
| 允许改项 | Theme/QML 样式 | 可调整 token 或局部颜色以贴近目标图 |
| 禁止改项 | Core/System/Service/Entity | 不得修改 |
| 禁止改项 | Store/API | 不得扩展接口或新增业务能力 |
| 禁止改项 | 后续阶段功能 | 不得启动 Phase 2+ 功能 |
| 风险项 | F 主按钮 | 防止主按钮停留在中央桌面视觉中心 |
| 风险项 | C Header/Step | 防止标题、徽章、步骤条弱化不可读 |
| 风险项 | B/D 背景 | 防止深墨外壳偏紫，破坏 Roman HUD 材质 |

## 6. A-F 区域修复要求

### A — TopStatusBar

保持当前 H0.1 结构：

- 62px 高度。
- 分块 HUD。
- 国库、派系、影响力、稳定度、战争、回合信息稳定显示。
- 不允许恢复硬编码稳定度。
- 不允许隐藏战争栏。

本轮只允许做轻微颜色/边框校准，不得重排。

### B — PhaseRail

保持：

- 92px 宽度。
- 7 个阶段按钮。
- pill 形态。
- icon + label 常显。

需要校正：

- 背景颜色不要偏紫黑，应接近 v3.25.1 深墨/深棕外壳。
- 按钮垂直分布应贴近目标图，不要显得过度漂浮或过度稀疏。

### C — StageDesktop

这是本轮重点。

必须修复：

1. `StageHeaderSlot` 必须在中央桌面顶部清晰显示：
   - `1 / 7` badge
   - `天命阶段` 标题
   - 天命说明文案
2. `StageInstructionSlot` 必须紧跟 header 下方，显示清晰步骤条。
3. `StageContentSlot` 的空状态提示必须位于上方内容卡/信息框内，不得漂浮在桌面中部偏左。
4. `StageActionSlot` 主按钮必须位于中央桌面底部居中附近，不得处在视觉中心。
5. 中央桌面应保持象牙白桌面层，不得出现深色公告横区。

推荐锚点：

```text
StageHeaderSlot: top, implicit height, visible and opaque
StageInstructionSlot: below header, fixed/implicit height
StageContentSlot: fill remaining area, content aligned top
StageActionSlot: fixed height at bottom
MainActionButton: anchors.horizontalCenter = parent.horizontalCenter; anchors.verticalCenter = parent.verticalCenter
```

注意：`StageActionSlot` 在 `StageDesktop` 的 ColumnLayout 底部时，按钮居中于 action slot，而不是居中于整个桌面。

### D — ContextPanel

保持 section 顺序：

```text
CurrentPhase → Operation → Progress → Player → EventLog
```

需要校正：

- 背景不要偏紫，应接近深墨/深棕。
- EventLog 不得压垮上方四个 section。
- 操作按钮和当前阶段信息要保持可读。

### E — BottomQueryBar

保持：

- 12 个查询入口。
- icon + text。
- 当前顺序。
- 62px HUD 高度。

本轮不做大改。

### F — MainAction

必须修复：

- `执行天命` 按钮必须在 `StageActionSlot` 内底部居中。
- 不得漂浮在中央桌面视觉中心。
- 尺寸保持 180×34。
- 颜色保持深朱红 + 金色文字。

## 7. 允许修改范围

仅允许修改：

```text
src/ui/gui/qml/theme/Theme.qml
src/ui/gui/qml/shell/GameShell.qml
src/ui/gui/qml/shell/StageDesktop.qml
src/ui/gui/qml/shell/PhaseRail.qml
src/ui/gui/qml/components/PhaseRailIcon.qml
src/ui/gui/qml/shell/ContextPanel.qml
src/ui/gui/qml/shell/BottomQueryBar.qml
src/ui/gui/qml/stages/MortalityStage.qml
src/tests/test_gui/
```

如需修改其他文件，必须先说明原因并等待确认。

## 8. 禁止事项

不得：

1. 修改 Core/System/Service/Entity。
2. 修改后端 API 语义。
3. 扩展 Store/API 功能。
4. 新增后续阶段功能。
5. 重新设计整体 GUI。
6. 改变 A-F 主区域位置和尺寸契约。
7. 牺牲 H0/H0.1 已通过的测试基线。
8. 用 `773 passed` 替代视觉验收。

## 9. 必交证据

DA/OC 必须提交：

1. 修改文件清单。
2. 修复摘要。
3. 目标截图路径。
4. 实测截图路径。
5. A-F 区域差异表。
6. 保持项 / 允许改项 / 禁止改项执行情况。
7. GUI startup 测试结果。
8. 完整回归测试结果。
9. 未解决问题清单。

## 10. A-F 差异表模板

| 区域 | 目标要求 | 实测表现 | 差异级别 | 处理结果 |
| --- | --- | --- | --- | --- |
| A 顶栏 | 62px 分块 HUD，栏位稳定 |  | 无/轻微/阻塞 |  |
| B 左栏 | 深墨/深棕 92px rail，7 pill nav |  | 无/轻微/阻塞 |  |
| C 中央桌面 | header/step/content/action 清晰垂直层级 |  | 无/轻微/阻塞 |  |
| D 右栏 | 五 section 顺序与密度正确 |  | 无/轻微/阻塞 |  |
| E 底栏 | 12 查询入口，HUD 密度稳定 |  | 无/轻微/阻塞 |  |
| F 主按钮 | StageActionSlot 底部居中，180×34 |  | 无/轻微/阻塞 |  |

## 11. 验收门禁

H0.2 通过条件：

1. GUI startup 通过。
2. 完整回归保持通过。
3. 最新实测截图中 C 区 header、step、content、action 层级清晰。
4. 主按钮位于中央桌面底部 action slot，而不是视觉中心。
5. A/B/D/E 不发生新的明显视觉回退。
6. 提交 A-F 差异表。

若 H0.2 未通过，不得继续完整 H 阶段。

## 12. 给 OC 的一句话指令

请启动 `GUI-P0-02-H0.2_Phase1_Visual_NoRegression_Calibration`，按照 `EOR_GUI_Development_Governance_v1.0.md` 和 `EOR_GUI_SA-DA_开发任务书规范模板_v1.2.md` 执行。目标是修复最新实测图中的视觉回退，重点恢复中央桌面的 header/step/content/action 层级和主按钮底部锚定，同时保持 H0/H0.1 已通过的槽位结构与 `773 passed` 测试基线。
