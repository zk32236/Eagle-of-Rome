# 任务书 — GUI-P0-02-H0.5

**任务编号：** GUI-P0-02-H0.5  
**任务名称：** Phase 1 Page Information Hierarchy Fix + Final Polish  
**任务类型：** Visual Calibration  
**优先级：** P1  

---

## 一、任务背景

R2.1 差异报告确认：中央桌面 **Page Information Hierarchy 缺失**（badge、标题、说明、步骤条、信息卡不可见）。

## 二、根因

StageDesktop.qml 第 66 行：

```qml
Layout.preferredHeight: implicitHeight
```

`Item.implicitHeight` 默认值为 0 → stageHeaderSlot 高度为 0 → 所有 `anchors.fill: parent` 的内容坍缩为 0px。

## 三、任务目标

### 第一批：P1 层次修复（必须先做）

1. stageHeaderSlot: `implicitHeight` → `80` （容纳 badge 22px + 间距 + 标题 ~24px + 间距 + 说明 ~18px）
2. stageInstructionSlot: 检查 32px 是否足够容纳步骤条内容
3. 验证四层级（badge → 标题 → 步骤条 → 信息卡）在截图中可见

### 第二批：抛光（P1 验证通过后再执行 D-01~D-06）

- D-01: 左栏按钮 +6px 高、间距 -2px
- D-02: 上边距已调（H0.4），保持
- D-03: 水平边距已调（H0.4），保持
- D-04: 右栏标题 +SemiBold + 亮度
- D-06: 主按钮阴影/高光

## 四、保持 / 允许 / 禁止

| 类型 | 区域 | 要求 |
|---|---|---|
| 保持项 | 测试基线 | GUI startup 7/7, regression ≥ 773 |
| 保持项 | A/B/E/F 主要区域 | H0.3 结构不回退 |
| 允许改项 | C stageHeaderSlot | preferredHeight 从 implicitHeight → 80 |
| 允许改项 | C stageInstructionSlot | preferredHeight 必要时调整 |
| 允许改项 | B 左栏 | D-01 按钮高+6px、间距-2px |
| 允许改项 | D 右栏 | D-04 标题半粗体+亮度 |
| 允许改项 | F 主按钮 | D-06 阴影+高光 |
| 禁止改项 | Core/System/Service/Entity | 不得修改 |
| 禁止改项 | 五区尺寸契约 | 不得改变 |

## 五、测试要求

```bash
python3 -m pytest src/tests/test_gui/test_qml_startup.py -v
python3 -m pytest src/tests/ -q
```

## 六、交付物

1. 修改文件清单
2. 修复摘要（P1 + D-01~D-06）
3. A-F 层次可见性说明
4. 测试结果
