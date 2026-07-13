# 任务书 — GUI-P0-02-H0.4

**任务编号：** GUI-P0-02-H0.4  
**任务名称：** Phase 1 Visual Polish — Final Calibration  
**任务类型：** Visual Calibration  
**优先级：** Low  
**目标版本：** Phase 1 视觉达标  

---

## 一、任务背景

Phase 1 视觉 Round 2 差异报告确认 layout 和视觉语言已基本对齐（~90%）。剩余 4 项 Low/Cosmetic 抛光项。

## 二、任务目标

修复以下 4 项（D-01/02/03/04/06，D-05 已合规，D-07 超出原型范围跳过）：

| ID | 内容 | 文件 |
|---|---|---|
| D-01 | 左栏按钮 +6px 高，垂直间距 -2px | `PhaseRail.qml` / `PhaseRailIcon.qml` |
| D-02 | 中央内容区上边距减 8px | `StageDesktop.qml` 或 `GameShell.qml` |
| D-03 | 水平内容边距左右各缩 8-10px | `StageDesktop.qml` padding |
| D-04 | 右栏标题加 SemiBold + 亮度+10% | `ContextPanel.qml` |
| D-06 | 主按钮加外阴影 + 顶部高光线 | `GameShell.qml` StageActionSlot 按钮 |

## 三、依据文档

| 文档 | 用途 |
|---|---|
| `EOR_GUI_Visual_Diff_Report_v3.25_Phase1_R2.md` | 差异来源 |
| `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` | 布局契约 |
| `EOR_GUI_Development_Governance_v1.0.md` | 治理规范 |

## 四、保持 / 允许 / 禁止

| 类型 | 区域 | 要求 |
|---|---|---|
| 保持项 | A/B/C/D/E/F 所有区域 | H0.3 修复的布局和透明度不得回退 |
| 保持项 | 测试基线 | GUI startup 7/7, regression ≥ 773 |
| 允许改项 | B 左栏 | 按钮高度 +6px, 间距 -2px |
| 允许改项 | C 中央桌面 | 上边距 -8px, 水平内边距缩 8-10px |
| 允许改项 | D 右栏 | 标题字体加粗 + 亮度 |
| 允许改项 | F 主按钮 | 添加阴影和高光 |
| 禁止改项 | Core/System/Service/Entity | 不得修改 |
| 禁止改项 | 五区尺寸契约 | 不得改变 |
| 禁止改项 | 其他阶段 | 不得涉及 |

## 五、测试要求

```bash
python3 -m pytest src/tests/test_gui/test_qml_startup.py -v
python3 -m pytest src/tests/ -q
```

## 六、交付物

1. 修改文件清单
2. 修复摘要（逐项对应 D-01~D-06）
3. GUI startup 7/7 + regression ≥ 773
