# GUI-P0-02-CX1 Codex Implementation Report

日期：2026-07-12  
任务：Phase 1 Central Page Hierarchy Rendering Failure — Independent Diagnosis and Repair  
执行者：Codex  
结论：已完成最小修复，GUI startup 与有效完整回归通过。截图已保存，但离屏截图文字仍为方块，仅作为布局粗验证据。

---

## 1. 确认根因

H0.5 的判断只覆盖了 `StageDesktop.qml` 中 slot 高度不足的问题，但没有发现更关键的运行时挂载错误。

实际根因是：`GameShell.qml` 中阶段层级内容使用了 `parent: stageHeaderSlot`、`parent: stageInstructionSlot`、`parent: stageContentSlot`、`parent: stageActionSlot`。这些名称是 `StageDesktop.qml` 内部 id，并不是 `StageDesktop` 对外稳定 API。

运行时结果是：

| 对象 | 修复前运行时表现 |
| --- | --- |
| `stageAnnouncement` | 未进入 `StageHeaderSlot`，直接挂到 `centerPanel`，尺寸为 `1022x736` |
| `stageContainer` | 未进入 `StageContentSlot`，直接挂到 `centerPanel`，尺寸为 `1022x736` |
| `mortalityStage` | 随 `stageContainer` 铺满整个中央面板 |

由于 `stageContainer/MortalityStage` 后声明并铺满中央面板，中央信息层级被覆盖，只剩半透明残影。  
所以 H0.5 把 slot 高度改为 `80/50` 仍无法恢复界面，因为内容并没有被正确挂入这些 slot。

---

## 2. 运行时证据

### 修复前关键值

```text
centerPanel       w=1022 h=736
stageHeaderSlot   w=1002 h=80
stageContentSlot  w=1002 h=502
stageAnnouncement parent=centerPanel w=1022 h=736
stageContainer    parent=centerPanel w=1022 h=736
mortalityStage    parent=stageContainer w=1022 h=736
```

### 修复后关键值

```text
centerPanel       w=1022 h=736
stageHeaderSlot   w=1002 h=80
stageInstructionSlot w=1002 h=50
stageContentSlot  w=1002 h=502
stageActionSlot   w=1002 h=46
stageAnnouncement w=1002 h=80
stageContainer    w=1002 h=502
mortalityStage    w=1002 h=502
```

说明：Python 的 `QObject.parent()` 仍可能显示创建时 QObject 所属对象，因此本次新增测试采用几何契约判断，验证内容不再铺满 `centerPanel`，而是匹配对应 slot 尺寸。

---

## 3. 修改文件

| 文件 | 修改 |
| --- | --- |
| `src/ui/gui/qml/shell/GameShell.qml` | 将四个阶段区域改为挂载到 `centerPanel.stageHeader`、`centerPanel.stageInstruction`、`centerPanel.stageContent`、`centerPanel.stageAction` |
| `src/ui/gui/qml/stages/MortalityStage.qml` | 将天命内容区从整区大卡片改为顶部提示卡，避免覆盖中央桌面层级 |
| `src/tests/test_gui/test_qml_startup.py` | 新增 `test_mortality_stage_hierarchy_is_attached_to_desktop_slots`，防止 header/content 再次铺满中央面板 |

未修改 Core / Service / Entity / 游戏规则。

---

## 4. 为什么旧修复失败

H0.5 只修复了 `StageDesktop` slot 的高度：

- `stageHeaderSlot: 80`
- `stageInstructionSlot: 50`

但 `GameShell` 的内容没有真正进入这些 slot。  
因此 slot 变高以后，真正可见区域仍被 `stageContainer/MortalityStage` 的整区覆盖层遮住，视觉上仍表现为标题、说明、步骤条半透明或不可见。

---

## 5. 为什么自动测试原来通过

原有 GUI startup 测试只检查：

- QML 能加载；
- 核心 objectName 存在；
- bottom query / phase navigation / i18n 边界存在。

它没有检查：

- `stageAnnouncement` 是否匹配 `stageHeaderSlot` 尺寸；
- `stageContainer` 是否匹配 `stageContentSlot` 尺寸；
- 中央 header/content 是否被整区覆盖；
- 可见层级是否符合设计图。

因此 QML 启动正常、对象存在，测试仍会通过。

---

## 6. 新增测试

新增测试：

```text
src/tests/test_gui/test_qml_startup.py::test_mortality_stage_hierarchy_is_attached_to_desktop_slots
```

该测试验证：

- `stageHeaderSlot / stageInstructionSlot / stageContentSlot / stageActionSlot` 存在且高度有效；
- `stageAnnouncement` 尺寸等于 `stageHeaderSlot`；
- `stageContainer` 尺寸等于 `stageContentSlot`；
- `stageAnnouncement` 和 `stageContainer` 不得再铺满 `centerPanel`。

这能覆盖本次真实缺陷。

---

## 7. 测试结果

### GUI startup

```text
8 passed in 3.92s
```

说明：原 7 条 GUI startup 测试全部通过，新增 1 条层级回归测试通过。

### 有效完整回归

```text
774 passed in 11.25s
```

命令范围：

```text
py -3.10 -m pytest src\tests -q
```

说明：直接运行仓库根目录 `pytest -q` 会收集 `docs/MVP 0.4` 历史测试与文本文件，产生历史文档测试冲突和编码错误；这不是本次 GUI 修复引入的问题。因此本报告采用项目有效测试目录 `src/tests` 作为完整回归范围。

---

## 8. 截图证据

修复后截图：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\GUI-P0-02-CX1_After_Fix.png
```

截图可读性说明：

- 截图由离屏 PySide6 环境生成。
- 中文和 emoji 在截图中仍显示为方块。
- 根据 `EOR_GUI_Development_Governance_v1.0.md`，该截图只能作为布局粗验证据，不能作为完整文字视觉验收依据。
- 人工本机截图仍需用于最终中文可读性验收。

布局粗验结论：

- `1 / 7` 徽章回到中央桌面顶部；
- 阶段标题和说明回到顶部层级；
- 步骤条回到标题下方；
- 提示卡回到步骤条下方；
- 主按钮保留在底部操作槽；
- 右栏、左栏、顶栏、底栏未在本次修复中重构。

---

## 9. 未决项

1. 离屏截图字体不可读问题未修复，按既定规范降级为布局粗验。
2. 当前截图结构已恢复，但最终视觉是否完全接近设计图仍需用户在本机运行后人工确认。
3. 仓库中存在大量本次任务前已经存在的未提交/未跟踪变更，本次未处理、未回退。

---

## 10. CX1 完成确认

| 要求 | 状态 |
| --- | --- |
| 独立诊断真实原因 | 已完成 |
| 回答为什么 H0.5 失败 | 已完成 |
| 最小 QML 修复 | 已完成 |
| 恢复中央层级布局 | 已完成，截图布局粗验通过 |
| 新增防回归测试 | 已完成 |
| GUI startup | 8 passed |
| 有效完整回归 | 774 passed |
| 截图保存 | 已完成 |
| 未修改核心规则 | 已确认 |

---

## 11. Phase 1 Complete 状态收尾修复

用户追加验收后发现：点击“执行天命”后的 complete 状态与目标设计仍有轻微差异。Codex 已继续收尾。

### 11.1 修改内容

| 文件 | 修改 |
| --- | --- |
| `src/ui/gui/qml/stages/MortalityStage.qml` | 按 `mortalityEvents.length` 区分执行前/执行后：执行后显示绿色“天命已执行”状态条、`事件结果` 标题和紧凑事件行 |
| `src/ui/gui/qml/shell/GameShell.qml` | 主按钮在 `canExecuteMortality === false` 时切换为小号禁用态 `已执行`，并提升为中央桌面底部 overlay，避免完成态按钮在离屏渲染中消失 |

### 11.2 截图

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\GUI-P0-02-CX1_Phase1_Complete_After_Fix.png
```

截图可读性说明不变：离屏截图中文字仍显示为方块，仅作为布局粗验；最终中文可读性仍以用户本机人工截图为准。

### 11.3 测试结果

```text
GUI startup: 8 passed in 4.00s
有效完整回归: 774 passed in 12.60s
```

本次收尾仍未修改 Core / Service / Entity / 游戏规则。
