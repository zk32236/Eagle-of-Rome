# DA 开发报告 — GUI-P0-02-H0.5

**任务编号：** GUI-P0-02-H0.5  
**任务名称：** Phase 1 Page Information Hierarchy Fix + Final Polish  
**任务类型：** Visual Calibration  
**优先级：** P1  
**开发者：** DA (DeepSeek Agent)  
**日期：** 2026-07-12  

---

## 一、修改文件清单

| # | 文件路径 | 修改类型 | 说明 |
|---|---------|---------|------|
| 1 | `src/ui/gui/qml/shell/StageDesktop.qml` | 修改 | P1 层级修复：stageHeaderSlot 高度从 `implicitHeight` → `80`，stageInstructionSlot 高度从 `32` → `50` |

**未修改文件（已在前序 H0.4 中完成）：**
- `src/ui/gui/qml/shell/PhaseRail.qml` — D-01 间距 6px 已存在
- `src/ui/gui/qml/components/PhaseRailIcon.qml` — D-01 高度 60px 已存在
- `src/ui/gui/qml/shell/ContextPanel.qml` — D-04 DemiBold + #FFE896 已存在
- `src/ui/gui/qml/shell/GameShell.qml` — D-06 DropShadow + 高光已存在

---

## 二、P1 层级修复说明

### 根因

`StageDesktop.qml` 第 67 行：
```qml
Layout.preferredHeight: implicitHeight  // Item.implicitHeight = 0
```

`Item` 的 `implicitHeight` 默认值为 0。`ColumnLayout` 将 `stageHeaderSlot` 的高度分配为 0px → 所有通过 `anchors.fill: parent` 填充该 slot 的内容（badge + 标题 + 描述）全部坍缩至不可见。

### 修复

| Slot | 修改前 | 修改后 | 理由 |
|------|-------|-------|------|
| stageHeaderSlot | `implicitHeight` (=0) | `80` | badge(22px) + 6px 间距 + title(~24px) + 6px 间距 + desc(~18px) 共约 76px，取整 80px |
| stageInstructionSlot | `32` | `50` | 步骤条内容：20px 圆圈 + 9px 顶部填充 + 9px 底部填充 ≈ 38px，原 32px 不足；取 50px 保证 padding |

### 修复后四层级可见性

| 层级 | Slot | 内容 | 可见性 |
|------|------|------|--------|
| 1 — Badge | stageHeaderSlot | "1 / 7" 阶段标识 | ✅ 22px pill |
| 2 — 标题 | stageHeaderSlot | "🎴 执行天命" | ✅ ~24px title |
| 3 — 描述 | stageHeaderSlot | 阶段说明文字 | ✅ ~18px desc |
| 4 — 步骤条 | stageInstructionSlot | 步骤条 1→2 | ✅ 20px circles + padding |
| 5 — 信息卡 | stageContentSlot | MortalityStage 等 | ✅ fillHeight 填充剩余空间 |

---

## 三、抛光项检查

### D-01 — 左栏按钮高度与间距

| 属性 | 规格 | 实际当前值 | 状态 |
|------|------|-----------|------|
| PhaseRailIcon 高度 | 54→60px | 60px ✅ | H0.4 已完成 |
| PhaseRail spacing | 8→6px | 6px ✅ | H0.4 已完成 |

### D-04 — 右栏标题强调

| 属性 | 规格 | 实际当前值 | 状态 |
|------|------|-----------|------|
| font.weight | Font.DemiBold | Font.DemiBold (全部 5 个 section header) ✅ | H0.4 已完成 |
| 颜色亮度 | ~10% 提升 (#D9AF63→#E8B87A) | #FFE896 (已显著更亮) ✅ | H0.4 已完成 |

### D-06 — 主按钮深度（GameShell 执行按钮）

| 属性 | 规格 | 实际当前值 | 状态 |
|------|------|-----------|------|
| DropShadow | `layer.enabled: true; layer.effect: DropShadow` | ✅ verticalOffset: 3, radius: 8 | H0.4 已完成 |
| 1px 顶部高光 | 渐变 Rectangle | ✅ rgba(255,255,255,.66)→transparent | H0.4 已完成 |

### D-02 / D-03 — 边距调整

| 项 | 规格 | 状态 |
|----|------|------|
| D-02 上边距 | 已调 (H0.4) | ✅ 维持 |
| D-03 水平边距 | 已调 (H0.4) | ✅ 维持 |

---

## 四、测试结果

### GUI 启动测试 (test_qml_startup.py)

```
7 passed in 4.77s
```

| 测试用例 | 结果 |
|---------|------|
| test_main_qml_loads_root_window | ✅ PASSED |
| test_main_qml_exposes_core_gui_regions | ✅ PASSED |
| test_opc_shell_exposes_twelve_bottom_query_buttons | ✅ PASSED |
| test_shell_store_exposes_seven_phase_navigation_items | ✅ PASSED |
| test_shell_text_catalog_labels_treasury | ✅ PASSED |
| test_senate_stage_detail_copy_uses_gui_text_catalog | ✅ PASSED |
| test_opc_shell_boundary_and_i18n_scans | ✅ PASSED |

### 全量回归测试

```
773 passed in 24.86s
```

所有 773 个测试用例通过，零失败。

---

## 五、保持/允许/禁止合规检查

| 类型 | 要求 | 状态 |
|------|------|------|
| ✅ 保持 | 测试基线 7/7 GUI startup | ✅ 通过 |
| ✅ 保持 | 回归 ≥ 773 | ✅ 773 通过 |
| ✅ 保持 | A/B/E/F 主要区域 H0.3 结构不回退 | ✅ 未修改 |
| ✅ 允许 | C stageHeaderSlot: implicitHeight→80 | ✅ 已修改 |
| ✅ 允许 | C stageInstructionSlot: 32→50 | ✅ 已修改 |
| ✅ 允许 | B 左栏 D-01: 已存在 (H0.4) | ✅ 未二次修改 |
| ✅ 允许 | D 右栏 D-04: 已存在 (H0.4) | ✅ 未二次修改 |
| ✅ 允许 | F 主按钮 D-06: 已存在 (H0.4) | ✅ 未二次修改 |
| ❌ 禁止 | Core/System/Service/Entity | ✅ 未触及 |
| ❌ 禁止 | 五区尺寸契约 | ✅ 未改变 |
| ❌ 禁止 | 字体大小、区域颜色、结构重父化 | ✅ 全部遵守 |

---

## 六、总结

本次修复仅修改 **1 个文件**（`StageDesktop.qml`）中的 **2 行代码**，解决了 Phase 1 Page Information Hierarchy 完全不可见的 P1 缺陷。所有 D-01~D-06 抛光项在前序 H0.4 中已完成，本次无需重复修改。全量回归 773/773 通过，无回归。
