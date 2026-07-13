# Codex 验收 — GUI-P0-02-H0 Phase 1 Slot Consolidation & TopBar Fix

日期：2026-07-12  
评审人：Codex / OpenClaw Main Session  
评审对象：`GUI-P0-02-H0_Phase1_Slot_Consolidation_TopBar_Fix_DA开发报告.md`  
结论：有条件通过，但不得进入完整 H 阶段；必须先修复 GUI startup 阻塞

正式应归档路径：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\Codex_Review_GUI-P0-02-H0_Phase1_Slot_Consolidation_TopBar_Fix_2026-07-12.md
```

当前写入路径：

```text
E:\OpenClaw\Projects\EOR\workspace\Codex_Review_GUI-P0-02-H0_Phase1_Slot_Consolidation_TopBar_Fix_2026-07-12.md
```

说明：当前会话对产品目录写入仍受系统权限限制，因此本文件先作为待归档正式稿保存在 OpenClaw workspace。

## 1. 审查对象

本次审查覆盖以下交付件：

| 类型 | 路径 |
| --- | --- |
| DA 开发报告 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-02\GUI-P0-02-H0_Phase1_Slot_Consolidation_TopBar_Fix_DA开发报告.md` |
| GameShell | `src/ui/gui/qml/shell/GameShell.qml` |
| StageDesktop | `src/ui/gui/qml/shell/StageDesktop.qml` |
| TopStatusBar | `src/ui/gui/qml/shell/TopStatusBar.qml` |
| MortalityStage | `src/ui/gui/qml/stages/MortalityStage.qml` |
| PhaseRailIcon | `src/ui/gui/qml/components/PhaseRailIcon.qml` |
| GUI startup tests | `src/tests/test_gui/test_qml_startup.py` |

审查依据：

- `GUI-P0-02-H0_Phase1_Slot_Consolidation_TopBar_Fix_PM意图包.md`
- `Codex_Review_GUI-P0-02-FG_v2_Phase1_Layout_Skeleton_2026-07-12.md`
- `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md`
- `EOR_GUI_SA-DA_开发任务书规范模板_v1.1.md`

## 2. 总体结论

H0 的核心目标基本完成：

1. `MortalityStage.qml` 已被精简为内容区组件，不再自建 header / instruction / action 平行槽位。
2. `GameShell.qml` 已将天命阶段的 header、step bar、action button 分布到 `StageDesktop` 的四个槽位。
3. `StageDesktop.qml` 已将 `stageInstructionSlot` 和 `stageActionSlot` 改为可见。
4. `TopStatusBar.qml` 已修复稳定度硬编码与战争栏条件隐藏问题。

但当前仍存在一个阻塞级问题：

```text
PhaseRailIcon.qml 存在 QML 语法错误，导致 GUI startup 测试失败，QQmlApplicationEngine.load() 无法完成。
```

因此本次结论不是完全通过，而是：

```text
H0：有条件通过
OC：可以继续执行，但只能先执行 H0.1 startup quickfix
完整 H 阶段：暂缓，不得启动
```

## 3. 已通过项

### 3.1 MortalityStage 已完成槽位瘦身

`MortalityStage.qml` 当前只保留事件内容区：

- 无 `mortalityHeaderSlot`
- 无 `mortalityInstructionSlot`
- 无 `mortalityActionSlot`
- 无 `sessionStore.doExecuteMortality()` 调用
- 保留事件列表、空状态提示和 `showFeedback()`

这符合 H0 要求：`MortalityStage` 不再自建平行槽位结构。

### 3.2 GameShell 已接管天命阶段四槽位

`GameShell.qml` 已在 `StageDesktop` 内分配：

| StageDesktop 槽位 | H0 实现 |
| --- | --- |
| `StageHeaderSlot` | 天命 badge / title / description |
| `StageInstructionSlot` | 天命 step bar |
| `StageContentSlot` | 精简后的 `MortalityStage` 内容区 |
| `StageActionSlot` | 执行天命按钮 |

这解决了上一轮“StageDesktop 槽位没有真正生效”的主要问题。

### 3.3 StageDesktop 四槽位已启用

`StageDesktop.qml` 中：

```qml
stageInstructionSlot.visible: true
stageActionSlot.visible: true
```

四槽位均可承载内容。该项通过。

### 3.4 TopStatusBar 栏位稳定性已修复

`TopStatusBar.qml` 中：

```qml
statValue: sessionStore.stability || "--"
```

稳定度不再硬编码 `78%`。

战争栏已移除条件隐藏：

```qml
statValue: sessionStore.warCount || "--"
```

没有 `visible: (sessionStore.warCount || 0) > 0`。该项通过。

### 3.5 架构边界未见新增违规

未发现 Core/System/Service/Entity 修改。  
未发现 QML 直接访问 Core 私有字段。  
天命执行仍通过 `sessionStore.doExecuteMortality()`，未见绕过 Store/API 的新增问题。

## 4. 阻塞问题

### 4.1 GUI startup 测试失败，不能进入完整 H 阶段

DA 报告写明：

```text
766 passed, 3 failed in 25.39s
3 项失败全部来自 test_gui/test_qml_startup.py
根因是 PhaseRailIcon.qml 第 41 行 QML 语法错误
```

实际文件中仍存在：

```qml
gradient: {
    if (root.state === "done") {
        return Gradient {
            ...
        }
    }
}
```

该写法不符合 QML 对复合类型属性的声明规则，`Gradient` 不能通过 JavaScript block `return` 作为复合类型实例返回。

影响：

- `QQmlApplicationEngine.load()` 失败。
- GUI startup 测试不可用。
- 无法证明 Phase 1 Shell 能实际启动。
- 不能进入完整 H 阶段。

该问题即便是 SA v2 预存问题，也已经成为 H0 验收门禁问题。H0 是进入 H 的前置修复任务，不能带着 GUI startup blocker 放行。

## 5. 测试状态

DA 报告测试结果：

```text
766 passed, 3 failed
```

排除 startup 测试后：

```text
766 passed
```

验收解释：

- 非 startup 回归未显示新增破坏。
- 但 GUI startup 失败是阻塞项。
- `AC-H0-09 回归测试 ≥ 773 passed` 未满足。
- `AC-H0-11 从任意阶段启动游戏，Shell 正确渲染` 未完成。

因此测试项不能完全通过。

## 6. 验收结论

| 项目 | 状态 |
| --- | --- |
| MortalityStage 槽位瘦身 | 通过 |
| GameShell 四槽位接管 | 通过 |
| StageDesktop 槽位启用 | 通过 |
| TopStatusBar 稳定度修复 | 通过 |
| TopStatusBar 战争栏稳定显示 | 通过 |
| Core/API 边界 | 通过 |
| GUI startup 测试 | 未通过 |
| 完整 H 阶段门禁 | 未放行 |

正式结论：

```text
H0 有条件通过。
H0 的目标改动基本完成，但 GUI startup blocker 未修复。
OC 可以继续执行，但只能进入 H0.1 快修，不得直接进入完整 H。
```

## 7. 给 OC 的下一步指令

请 OC 启动：

```text
GUI-P0-02-H0.1_PhaseRailIcon_QML_Startup_Fix
```

任务目标：

1. 修复 `PhaseRailIcon.qml` 的 `gradient` 复合类型声明错误。
2. 不改变 PhaseRail 的目标视觉形态。
3. 不修改 Core/System/Service/Entity。
4. 不新增阶段业务规则。
5. 重新运行 `src/tests/test_gui/test_qml_startup.py`。
6. 重新运行相关 GUI 回归测试。
7. 提交启动截图或说明无头启动验证结果。

建议修复方式：

```qml
gradient: Gradient {
    orientation: Gradient.Vertical
    GradientStop {
        position: 0.0
        color: root.state === "done" ? "#B34F8B57"
             : root.state === "current" ? "#EFD27D"
             : "#0EFFFFFF"
    }
    GradientStop {
        position: 1.0
        color: root.state === "done" ? "#B8375F3C"
             : root.state === "current" ? "#D2A144"
             : "#0EFFFFFF"
    }
}
```

也可以使用多个 `Rectangle` 分层并通过 `visible` 控制状态，但必须保持 74×54 pill、done/current/todo 三态颜色与目标契约一致。

## 8. 完整 H 阶段放行条件

只有满足以下条件后，才允许启动完整 `GUI-P0-02-H`：

1. `PhaseRailIcon.qml` startup blocker 修复。
2. `test_gui/test_qml_startup.py` 通过。
3. GUI Shell 能在无头测试中成功加载 root object。
4. H0.1 报告提交修改文件清单、测试结果和风险说明。
5. 若截图环境可用，补交 1440×900 实际运行截图。

最终答复：

```text
OC 可以开始执行，但应执行 H0.1 快修任务。
不允许直接进入完整 H 阶段。
```
