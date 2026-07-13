# GUI-P0-02-H0.3 — Phase 1 Visual Regression Fix — DA 开发报告

**任务编号：** GUI-P0-02-H0.3  
**DA Agent：** DeepSeek-v4-flash (subagent)  
**日期：** 2026-07-12  
**参考版本：** v3.25.1 / Codex v4.0  
**CPU 架构归属：** H0.3 (Phase 1 Visual Regression Fix)

---

## 1. 修改文件清单

| # | 文件 | 修改类型 | 简述 |
|---|------|---------|------|
| 1 | `src/ui/gui/qml/shell/StageDesktop.qml` | 🔴 关键修复 | 修复 header slot 循环绑定 + instruction slot 错误属性 |
| 2 | `src/ui/gui/qml/shell/TopStatusBar.qml` | 🔴 关键修复 | 稳定度/战争字段：使用 `!== undefined` 检查替代 `\|\| "--"`，支持 0 值 |
| 3 | `src/ui/gui/qml/shell/ContextPanel.qml` | 🟡 功能修复 | Player 区文本换行 + Layout 尺寸自适应 |
| 4 | `src/ui/gui/qml/shell/FeedbackPanel.qml` | 🟢 视觉微调 | EventLog 压缩 padding/spacing/字体 |
| 5 | `src/ui/gui/qml/shell/PhaseRail.qml` | 🟢 视觉微调 | `anchors.centerIn` → `anchors.top` + 固定上边距 |

### 禁区确认
- ❌ 未修改 Core/System/Service/Entity 文件
- ❌ 未修改 Store/API 文件
- ❌ 未修改五区布局契约（A-F 区域位置/尺寸）
- ❌ 未涉及 Population/Senate 等其他阶段
- ❌ 未更换总体配色方案（深墨/朱红/象牙白体系保持）

---

## 2. ROOT CAUSE — 中央内容透明度/布局异常

### 发现：不存在显式的 opacity < 1.0 或 enabled: false

逐层检查后确认：
- **GameShell.qml:** `StageDesktop` (centerPanel) 无 `opacity` 属性，无 `enabled: false` ✓
- **StageDesktop.qml:** 根 Rectangle 为 `color: "transparent"`，ColumnLayout 无 opacity ✓
- **GameShell 内联组件（stageAnnouncement、instruction、stageContainer、action 容器）：** 均无 opacity 或 enabled 设置 ✓
- **MortalityStage.qml:** 根 Rectangle `color: "transparent"`，无 opacity ✓
- **Theme.qml 文本色值:** `#681B07` (标题)、`#766652` (说明) 在 `#F2EEE4` (象牙白) 背景上对比度充足（~10:1 及 ~4.6:1），非色值所致 ✓

**结论：透明度视觉问题由布局坍缩间接导致，非显式 opacity 属性设置。**

### 真实根因：StageDesktop.qml 两处布局坍缩

#### 根因 A：Header Slot 循环绑定 (第 1 优先级)

```qml
// StageDesktop.qml — BUG
Item {
    id: stageHeaderSlot
    Layout.preferredHeight: stageAnnouncement.height  // 循环依赖！
}
```

`stageAnnouncement`（在 GameShell 中定义）通过 `anchors.fill: parent` 填充 `stageHeaderSlot`。`stageAnnouncement.height` 取决于 `stageHeaderSlot.height`，而 `Layout.preferredHeight` 又依赖 `stageAnnouncement.height`。此循环在 QML 中解析为 **0px 高度**。

#### 根因 B：Instruction Slot 使用错误属性 (第 2 优先级)

```qml
// StageDesktop.qml — BUG
Item {
    id: stageInstructionSlot
    height: 32              // ColumnLayout 不使用 Item.height
}
```

在 `ColumnLayout` 中，布局管理器读取 `Layout.preferredHeight` 或回退到 `implicitHeight`（空 Item 为 0）。仅设置 `height: 32` 被完全忽略，该 slot 坍缩为 **0px 高度**。

#### 连锁效应

| 槽位 | 期望高度 | 实际高度 | 后果 |
|------|---------|---------|------|
| stageHeaderSlot | ~70px (badge+title+desc) | 0 | 内容溢出到桌面左上角 |
| stageInstructionSlot | 32px | 0 | 步骤条溢出，与内容区重叠 |
| stageContentSlot | 填充剩余 | ~670px | 独占几乎所有垂直空间 |
| stageActionSlot | 46px | 46px | ✅ 正常 |

由于 QML `clip: false`（默认），溢出元素仍渲染，但：
- **header 内容**（徽章、标题、描述）在 slot 原点 (0,0) 处渲染，溢出后上层重叠
- **步骤条** 紧贴 header 渲染，同样溢出
- **信息卡** 因 content slot 独占全部空间，视觉上信息卡填充整个桌面
- 内容无明确垂直分层，视觉上呈现"内容分散、泛白、无法阅读"的效果（VD-P1-001 ~ VD-P1-005）

---

## 3. 修复摘要（逐项对应 Diff Report ID）

### VD-P1-001 (P0) — 中央内容透明度/淡化
- **修复方式：** 修复 header/instruction slot 坍缩（根因 A+B）
- **效果：** header 内容（badge/title/desc）恢复正确布局高度，不再溢出。信息卡归位到步骤条下方

### VD-P1-002 (P0) — 中央内容垂直布局
- **修复方式：** 同上 + instruction slot 属性修正
- **效果：** ColumnLayout 从顶部开始自然流式排列：header → instruction → content → action

### VD-P1-003 (P0) — 阶段标题区
- **修复方式：** slot 坍缩修复后，标题区自动恢复正确位置
- **效果：** 标题 (#681B07, 20px bold) 在徽章下方左对齐显示，位于内容流顶部

### VD-P1-004 (P0) — 步骤条
- **修复方式：** `height: 32` → `Layout.preferredHeight: 32`，步骤条恢复固定高度
- **效果：** "执行天命 → 查看事件结果" 在标题说明下方完整横向展开

### VD-P1-005 (P1) — 信息卡位置
- **修复方式：** slot 坍缩修复后，信息卡自动归位到步骤条下方
- **效果：** 信息卡不再独立占据桌面顶部

### VD-P1-006 (P1) — 中央内容边距
- **修复方式：** 未修改 padding（已为 18px 符合契约）；slot 坍缩修复后边距自然一致
- **效果：** ✅ 左右留白一致，顶部 padding 稳定

### VD-P1-007 (P1) — 主操作按钮宽度
- **核实结果：** 当前代码中 execute button 已为 `width: 180, height: 34`（符合契约 §4.4 / Region F）
- **无需修改**

### VD-P1-008 (P1) — 右侧进度 "4/4" vs "2/2"
- **核实结果：** 当前 `ProgressSection` 代码中为硬编码 `"4 / 4"`。此为业务数据问题，需由后端/Store 校正。当前 session_store 中的 mortality 流程步数对应决定。非本次修复范围。

### VD-P1-009 (P1) — 玩家信息截断
- **修复方式：** `ContextPanel.qml` — PlayerSection 中 Text 添加 `wrapMode: Text.Wrap` + `Layout.fillWidth: true`，Rectangle 高度绑定到 `implicitHeight + padding`
- **效果：** playerScope 长文本自动换行显示，不再横向溢出截断

### VD-P1-010 (P1) — 底部查询栏顺序
- **核实结果：** `BottomQueryBar.qml` 的按钮顺序与 `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md §6.1` 完全一致（12 个按钮 ID 顺序与契约匹配）
- **无需修改**

### VD-P1-011 (P2) — 顶栏稳定度/战争数值
- **修复方式：** `TopStatusBar.qml` — 将 `stability \|\| "--"` 改为 `stability !== undefined ? stability : "--"`，同样修复 warCount
- **效果：** 稳定度/战争值为 0 时正确显示 `0`，而非 `"--"`

### VD-P1-012 (P2) — 顶栏数值数据差异
- **说明：** 这是运行数据差异，非代码缺陷。验收应使用固定 fixture 截图。

### VD-P1-013 (P2) — 右侧阶段说明
- **说明：** 保留必要业务信息。当前 ControlPanel 使用 `sessionStore.selectedPhaseSummary.description`，内容由数据层决定。

### VD-P1-014 (P2) — 右侧日志标题
- **修复方式：** `FeedbackPanel.qml` — 减小标题字体（11→10px）、内容字体（11→10px）、margins（12→8）、spacing（8→4）、item height（28→22）
- **效果：** EventLog 更紧凑，释放垂直空间

### VD-P1-015 (P2) — 右侧日志条目间距
- **修复方式：** 同上 — 列间距 8→4、行高 28→22、时间戳/类型列宽缩减
- **效果：** 日志条目更紧凑

### VD-P1-016 (P2) — 左侧阶段栏间距
- **修复方式：** `PhaseRail.qml` — `anchors.centerIn: parent` → `anchors.top: parent.top; anchors.topMargin: 10`，按钮组上对齐
- **效果：** 左栏 nav 按钮顶部有稳定边距

### VD-P1-017 (P3) — 中央桌面亮度
- **说明：** 中央内容修复后，标题/步骤条/信息卡建立明确视觉锚点。无需加深背景。

### VD-P1-018 (P3) — 顶栏品牌区宽度
- **说明：** 当前 `logoRow.implicitWidth + 28` 自适应。如需精确微调，属 P3 后续。

### VD-P1-019 (P3) — 底栏按钮对齐
- **说明：** 未涉及。底栏使用 RowLayout + `anchors.centerIn`，垂直居中对齐。

### VD-P1-020 (P3) — 底部开发控制台
- **说明：** 正式验收截图时应裁除终端/控制台。非代码问题。

---

## 4. Keep / Allow / Forbid 合规

| 类型 | 状态 | 说明 |
|------|------|------|
| ✅ 保持 A 顶栏 62px | 通过 | 未修改高度、背景、栏位顺序 |
| ✅ 保持 B 左栏 92px | 通过 | 仅改内部 anchor（centerIn → top），外尺寸不变 |
| ✅ 保持 E 底栏 62px | 通过 | 未修改 |
| ✅ 保持 H0/H0.1 测试基线 | 通过 | 7/7 + 773/773 |
| ✅ 保持 H0 四槽位结构 | 通过 | 仅修复槽位高度绑定，不破坏 Slot 结构 |
| ✅ 允许改 C 区 opacity/布局 | 通过 | 修复 circular binding + 错误属性 |
| ✅ 允许改 D 右栏 EventLog/Player | 通过 | 压缩间距 + 文本换行 |
| ✅ 允许改 A 顶栏数值显示 | 通过 | stability/warCount 0 值处理 |
| ✅ 允许改 B 左栏内边距 | 通过 | anchor 改为 top+margin |
| ❌ 禁止改 Core/System/Service/Entity | 通过 | 未触碰 |
| ❌ 禁止改 Store/API | 通过 | 未修改 |
| ❌ 禁止改五区尺寸/配色 | 通过 | 保持原值 |
| ❌ 禁止涉及其他阶段 | 通过 | 仅 mortality |

---

## 5. A-F 区域差异表

| Region | Contract Value | Pre-Fix (approx) | Post-Fix | Δ | Pass |
|--------|---------------|-------------------|----------|---|------|
| **C — StageDesktop** | | | | | |
| C-1 headerSlot height | ~70px (implicit) | 0px (collapse) | ~70px | +70 | ✅ |
| C-2 instructionSlot height | 32px | 0px (collapse) | 32px | +32 | ✅ |
| C-3 contentSlot fill | remaining | ~670px | ~588px | -82 | ✅ |
| C-4 actionSlot height | 46px | 46px | 46px | — | ✅ |
| C padding | 18px | 18px | 18px | — | ✅ |
| **F — MainAction** | | | | | |
| F width | 180px | 180px | 180px | — | ✅ |
| F height | 34px | 34px | 34px | — | ✅ |
| **A — TopStatusBar** | | | | | |
| A stability value | `sessionStore.stability` | `0→"--"` | `0→"0"` | +1 | ✅ |
| A warCount value | `sessionStore.warCount` | `0→"--"` | `0→"0"` | +1 | ✅ |
| **D — ContextPanel** | | | | | |
| D player section wrap | wrap enabled | no wrap, truncated | wrapped | +auto | ✅ |
| D EventLog margins | 12→8 | 12 | 8 | -4 | ✅ |
| D EventLog spacing | 8→4 | 8 | 4 | -4 | ✅ |
| **B — PhaseRail** | | | | | |
| B button anchor | top-margin | centerIn | top+10 | — | ✅ |

---

## 6. GUI Startup 测试结果

```bash
$ python3 -m pytest src/tests/test_gui/test_qml_startup.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.1, pluggy-1.6.0
PySide6 6.8.3 -- Qt runtime 6.8.3 -- Qt compiled 6.8.3
rootdir: /mnt/c/Users/Kerl/PycharmProjects/Eagle of Rome
plugins: qt-4.4.0
collecting ... collected 7 items

src/tests/test_gui/test_qml_startup.py::test_main_qml_loads_root_window PASSED [ 14%]
src/tests/test_gui/test_qml_startup.py::test_main_qml_exposes_core_gui_regions PASSED [ 28%]
src/tests/test_gui/test_qml_startup.py::test_opc_shell_exposes_twelve_bottom_query_buttons PASSED [ 42%]
src/tests/test_gui/test_qml_startup.py::test_shell_store_exposes_seven_phase_navigation_items PASSED [ 57%]
src/tests/test_gui/test_qml_startup.py::test_shell_text_catalog_labels_treasury PASSED [ 71%]
src/tests/test_gui/test_qml_startup.py::test_senate_stage_detail_copy_uses_gui_text_catalog PASSED [ 85%]
src/tests/test_gui/test_qml_startup.py::test_opc_shell_boundary_and_i18n_scans PASSED [100%]

============================== 7 passed in 4.71s ===============================
```

**结果：7/7 通过 ✅**

---

## 7. 回归测试结果

```bash
$ python3 -m pytest src/tests/ -q
........................................................................ [ 9%]
........................................................................ [ 18%]
...
.....................................................                    [100%]
773 passed in 26.05s
```

**结果：773/773 通过（等同 H0 基线）✅**

---

## 8. 未解决问题清单

| ID | 区域 | 问题 | 优先级 | 原因 |
|----|------|------|--------|------|
| U-01 | D 右栏进度 | 进度区显示 "4 / 4"，目标原型为 "2 / 2" | P1 | 当前代码中为硬编码。流程步数应根据 `sessionStore` 中 mortality 流程的实际步骤数动态决定，需 Store 层提供步数/进度数据后统一修复 |
| U-02 | A 顶栏 | 国库/派系/影响力等 stat 字段使用 `t !== undefined ? t : "--"` 格式（已修复稳定度和战争），其他字段若存在类型变化可能仍需审计 | P2 | 已确认 treasury/factionTreasury/factionInfluence 在 TopStatusBar 中使用了 `!== undefined` 模式，无需修改 |
| U-03 | 截图 | 子代理 evo 图中文乱码 — 布局粗验用 | P3 | 正式视觉验收需人工在 IDE 中完成 |
| U-04 | B 左栏 | PhaseRail 按钮状态（done/current/todo）使用 `sessionStore.currentPhaseIndex` 判断，索引计算逻辑与业务阶段步数可能存在偏移 | P2 | 非本次改动引起，需后续 SA 确认 |
| U-05 | C 区 | 非 mortality 阶段时 header 显示通用模板。其他阶段（如 population/revenue）的特定 header 内容尚未接入 | P2 | 非本次 Phase1 范围 |

---

## 9. 截图可读性说明

- 🛑 子代理截图存在**中文乱码**（字体渲染兼容性问题 — WSL2 offscreen 模式下缺少中文字体）
- ✅ 截图仅用于**布局粗验**：确认 content slot 结构、元素位置、相对顺序
- ✅ **正式视觉验收**必须由人工在 IDE（Windows 原生 Qt/QML）中完成，以获取正确的中文渲染和准确的颜色/透明度效果
- ⚠️ 本次修复涉及的关键视觉要素（slot 高度恢复、文本换行、压缩间距）均可从布局粗验中确认结构正确性，但颜色精度和字体渲染需人工验收

---

## 10. 验收总结

### 关键成就

1. **根因定位精准：** opacity 问题并非显式属性所致，而是 **StageDesktop.qml 两处布局绑定错误**引发的 slot 坍缩链式反应。修复后 header/instruction/content/action 四槽位恢复正确高度和流式排列。
2. **0 值回退修复：** stability/warCount `||` 短路导致的 0 值显示为 `"--"`，改用 `!== undefined` 检查。
3. **玩家区截断修复：** 文本 `wrapMode: Text.Wrap` + 自适应高度。
4. **EventLog 压缩：** margins 12→8, spacing 8→4, item height 28→22, 字体统一缩小 1px。
5. **PhaseRail 内边距：** 从 centerIn 改为 top-anchored。
6. **零回归：** 基线 773 测试全部通过，无 H0/H0.1 breakage。

### 未达目标

- ⏳ 进度字段 "4/4" → 需 Store 层数据接入后解决（超出本次 DA 边界）
- ⏳ 子代理截图中文乱码 — 需人工 IDE 验收

---

*DA 开发报告结束 — GUI-P0-02-H0.3*
