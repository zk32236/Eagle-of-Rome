# GUI-P0-02-H0.4 — Phase 1 Visual Polish — DA 开发报告

**日期：** 2026-07-12  
**任务编号：** GUI-P0-02-H0.4  
**任务类型：** Visual Calibration  
**目标版本：** Phase 1 视觉达标  
**DA 执行模式：** Subagent (OpenClaw)

---

## 一、修复摘要

### D-01 — 左栏按钮 +6px 高，垂直间距 -2px ✅

| 文件 | 修改内容 |
|---|---|
| `src/ui/gui/qml/components/PhaseRailIcon.qml` | 按钮高度 `54px → 60px`（Item 和 Rectangle 均调整）|
| `src/ui/gui/qml/shell/PhaseRail.qml` | ColumnLayout `spacing: 8 → 6`（垂直间距 -2px）|

**说明：** 按钮 pill 形状保持 `radius: 10` 不变，图标和标签字号维持原样。布局契约 B 区外框 `74×60`，总 rail 高度不变（7×60 + 6×6 + 上下 padding 20 = 476px，仍在 736px 容器内）。

---

### D-02 — 中央内容区上边距减 8px ✅

| 文件 | 修改内容 |
|---|---|
| `src/ui/gui/qml/shell/StageDesktop.qml` | `anchors.margins: 18` → 拆分后 `anchors.topMargin: 10`（原 18 - 8 = 10）|

**说明：** 仅修改 topMargin，保持 left/right/bottom 分别为后续 D-03 调整值。

---

### D-03 — 水平内容边距左右各缩 8-10px ✅

| 文件 | 修改内容 |
|---|---|
| `src/ui/gui/qml/shell/StageDesktop.qml` | `anchors.leftMargin: 10, anchors.rightMargin: 10`（原 18 - 8 = 10）|

**说明：** 水平内边距从 18px 缩至 10px，减少 8px。C 区外框尺寸（1022×736）不变，仅内部内容区域水平扩展 16px。符合布局契约。

---

### D-04 — 右栏标题加 SemiBold + 亮度 +10% ✅

| 文件 | 修改内容 |
|---|---|
| `src/ui/gui/qml/shell/ContextPanel.qml` | 5 个 section header Text 项 |

**修改的具体项：**
1. "🎯 当前阶段"（currentPhaseSection）
2. "⚡ 操作"（operationSection）
3. "📋 进度"（progressSection）
4. "👤 玩家"（playerSection）
5. "📢 事件日志"（eventLogSection 内）

**每项修改：**
- 添加 `font.weight: Font.DemiBold`
- 颜色从 `theme.accentGoldSoft`（`#F7D778`）→ `"#FFE896"`（~10% 亮度提升）

**亮度计算参考：** `#F7D778` → `#FFE896`，RGB 通道从 `(247,215,120)` 提升至 `(255,232,150)`，综合亮度约 +10%。

---

### D-06 — 主按钮加外阴影 + 顶部高光线 ✅

| 文件 | 修改内容 |
|---|---|
| `src/ui/gui/qml/shell/GameShell.qml` | `executeBtn`（StageActionSlot 主按钮）|

**具体修改：**
1. **新增 import：** `import Qt5Compat.GraphicalEffects`（PySide6 6.8.3 兼容）
2. **外部阴影：** `layer.enabled: true` + `layer.effect: DropShadow`（offset 3px, radius 8px, opacity 0.69）
3. **顶部高光：** 新增 1px 高 Rectangle（`width: 172`, 左右缩进 4px）带有上白下透渐变 `#66FFFFFF → transparent`

**保留项：** 原有渐变（hover 态 `#A33A17→#7A210B`、默认 `#84250A→#671B07`）、180×34px 尺寸、4px radius 均未改动。

---

## 二、文件修改清单

| # | 文件路径 | 修改类型 | 相关 D 项 |
|---|---|---|---|
| 1 | `src/ui/gui/qml/components/PhaseRailIcon.qml` | 高度调整 | D-01 |
| 2 | `src/ui/gui/qml/shell/PhaseRail.qml` | 间距调整 | D-01 |
| 3 | `src/ui/gui/qml/shell/StageDesktop.qml` | 边距拆分+压缩 | D-02, D-03 |
| 4 | `src/ui/gui/qml/shell/ContextPanel.qml` | 标题样式 | D-04 |
| 5 | `src/ui/gui/qml/shell/GameShell.qml` | import + 阴影 + 高光 | D-06 |

---

## 三、测试结果

### GUI startup test（7/7 ✅）

```
src/tests/test_gui/test_qml_startup.py::test_main_qml_loads_root_window PASSED
src/tests/test_gui/test_qml_startup.py::test_main_qml_exposes_core_gui_regions PASSED
src/tests/test_gui/test_qml_startup.py::test_opc_shell_exposes_twelve_bottom_query_buttons PASSED
src/tests/test_gui/test_qml_startup.py::test_shell_store_exposes_seven_phase_navigation_items PASSED
src/tests/test_gui/test_qml_startup.py::test_shell_text_catalog_labels_treasury PASSED
src/tests/test_gui/test_qml_startup.py::test_senate_stage_detail_copy_uses_gui_text_catalog PASSED
src/tests/test_gui/test_qml_startup.py::test_opc_shell_boundary_and_i18n_scans PASSED
```

**结果：** 7/7 ✅

### Regression test suite

```
773 passed in 26.26s
```

**结果：** 773/773 ✅（H0.3 基线保持，无回归）

---

## 四、合规检查

| 检查项 | 状态 | 说明 |
|---|---|---|
| ❌ 未修改 Core/System/Service/Entity | ✅ | 仅修改 Shell QML 组件 |
| ❌ 未改动五区尺寸契约 | ✅ | C 区外框 1022×736 不变，B 区 92×736 不变，D 区 286×736 不变 |
| ❌ 未扩及其他阶段 | ✅ | 仅限 Phase 1 文件 |
| ✅ H0.3 修复保持 | ✅ | 透明度（rgba 保持）、布局锚点（未回退） |
| ✅ 测试基线 | ✅ | startup 7/7, regression 773 |

---

## 五、额外说明

### D-06 DropShadow 导入选择

PySide6 6.8.3 环境中 `DropShadow` 位于 `Qt5Compat.GraphicalEffects` 模块。初始尝试 `QtGraphicalEffects 1.15` 时会报 `DropShadow is not a type`。经检查 QML 导入路径确认后改为 `import Qt5Compat.GraphicalEffects` 解决。

### 布局契约合规性

- D-02/D-03 仅修改 StageDesktop 的内部 `ColumnLayout` 边距（即 C 区内部 padding），不影响 C 区在 GameShell 中的定位尺寸（`x=112, y=82, w=1022, h=736`）。
- D-01 按钮高度增大后总高度 476px，仍适配 B 区 736px 容器（上下各留约 130px 空白）。

---

## 六、后续建议

1. **D-07（中央工作区摘要卡片）** 如需实现，建议在 `StageContentSlot` 之上加一层 `StageSummaryCard`，使用 `FadeAnimation` 过渡。
2. **交互一致性：** 当前按钮 hover/pressed/disabled 状态已经就绪，建议后续关注全 UI 交互细节对齐。
3. **GUI ↔ Control 绑定：** 按钮点击已绑定 `sessionStore.doExecuteMortality()`，后续需关注异常路径和异步反馈。
