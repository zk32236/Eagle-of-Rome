# GUI-P0-02-H — Mortality Phase State Binding Table

**Date:** 2026-07-12  
**Source files:** `MortalityStage.qml`, `GameShell.qml`, `StageDesktop.qml`  
**Store class:** `GuiSessionStore` (`session_store.py`)

---

## 1. StageHeaderSlot — 阶段标题区

| QML 属性 / 位置 | 绑定表达式 | Store 字段 / 来源 | 类型 | 更新信号 | 备注 |
|----------------|-----------|------------------|:----:|:--------:|------|
| badge `text` | `"1 / 7"` | 硬编码占位符 | `string` | — | PM 意图包明确允许静态占位符；未来可从 `phaseNavigation` 派生 |
| badge `color` | `"#84250A"` | 设计契约固定值 | `color` | — | — |
| badge `radius` | `999` | 设计契约固定值 | `int` | — | 999px pill shape |
| title `text` | `"🎴 " + GuiText.mortalityTitle` | `GuiText.mortalityTitle` (i18n) = `"天命阶段"` | `string` | — | i18n 键值，从硬编码改进 |
| title `color` | `"#681B07"` | 设计契约固定值 | `color` | — | — |
| description `text` | `sessionStore.selectedPhaseSummary.description \|\| GuiText.mortalityIntro` | `sessionStore.selectedPhaseSummary` → `description` 键；回退 `GuiText.mortalityIntro` | `string` | `phaseChanged` | Store 优先，不可用时回退 i18n 文本 |
| description `color` | `"#766652"` | 设计契约固定值 | `color` | — | — |

---

## 2. StageInstructionSlot — 步骤条

| QML 属性 / 位置 | 绑定表达式 | Store 字段 / 来源 | 类型 | 更新信号 | 备注 |
|----------------|-----------|------------------|:----:|:--------:|------|
| 容器 `visible` | `sessionStore.selectedPhaseId === "mortality"` | `sessionStore.selectedPhaseId` | `string` | `phaseChanged` | 仅天命阶段显示 |
| Step 1 circle `color` | `"#E8B84B"` | 固定 current 色 | `color` | — | 静态标记为"当前" |
| Step 1 circle Text `text` | `"1"` | 固定 | `string` | — | — |
| Step 1 label `text` | `"⚡ 执行天命"` | 固定 | `string` | — | — |
| Step 2 circle `color` | `"#E8D5C4"` | 固定 todo 色 | `color` | — | 静态标记为"待办" |
| Step 2 circle Text `text` | `"2"` | 固定 | `string` | — | — |
| Step 2 label `text` | `"📜 查看事件结果"` | 固定 | `string` | — | — |

**注意：** 步骤条着色当前为静态。若未来 Store 新增 `mortalityPhaseStatus`，可改为 `canExecuteMortality`/`mortalityResult` 驱动。

---

## 3. StageContentSlot — 事件内容区 (MortalityStage.qml)

| QML 属性 / 位置 | 绑定表达式 | Store 字段 / 来源 | 类型 | 更新信号 | 备注 |
|----------------|-----------|------------------|:----:|:--------:|------|
| 空状态 Text `visible` | `(sessionStore.mortalityEvents \|\| []).length === 0` | `sessionStore.mortalityEvents` | `list[dict]` | `mortalityViewChanged` | 列表为空或 null 时显示提示 |
| 空状态 Text `text` | `"🎴 点击下方「执行天命」按钮，触发一个随机事件。\n事件类型：猝死"` | 硬编码提示文案 | `string` | — | 后续可移至 i18n |
| Repeater `model` | `sessionStore.mortalityEvents \|\| []` | `sessionStore.mortalityEvents` | `list[dict]` | `mortalityViewChanged` | `mortality_result.events` 优先，回退 `mortality_view.events` |
| Repeater delegate → name `text` | `modelData.name \|\| ""` | `mortalityEvents[].name` | `string` | — | 事件名称 |
| Repeater delegate → summary `text` | `modelData.summary \|\| ""` | `mortalityEvents[].summary` | `string` | — | 事件摘要 |

### store.mortalityEvents 数据合约

```python
mortalityEvents: List[Dict[str, Any]] = [
    {
        "name": str,       # 事件名称，如 "瘟疫爆发"
        "summary": str,    # 事件摘要，如 "某地爆发瘟疫，人口减少 5%"
        # 其他字段（impact 等）当前未在 QML 中使用
    }
]
```

---

## 4. StageActionSlot — 执行按钮

| QML 属性 / 位置 | 绑定表达式 | Store 字段 / 来源 | 类型 | 更新信号 | 备注 |
|----------------|-----------|------------------|:----:|:--------:|------|
| 容器 `visible` | `sessionStore.selectedPhaseId === "mortality"` | `sessionStore.selectedPhaseId` | `string` | `phaseChanged` | 仅天命阶段显示 |
| Button `visible` | `sessionStore.selectedPhaseId === "mortality"` | `sessionStore.selectedPhaseId` | `string` | `phaseChanged` | — |
| MouseArea `enabled` | `sessionStore.canExecuteMortality !== false` | `sessionStore.canExecuteMortality` | `bool` | `mortalityViewChanged` | `sessionStore._mortality_view.can_execute` |
| MouseArea `onClicked` | `var result = sessionStore.doExecuteMortality()` | `sessionStore.doExecuteMortality()` | Slot → `dict` | — | 调用后自动 `mortalityViewChanged` |
| MouseArea `onClicked` → error | `if (!result.success) mortalityStage.showFeedback("error", result.message)` | 结果 `result.message` | `string` | — | 失败时向上冒泡反馈 |

### sessionStore.doExecuteMortality() 返回合约

```python
doExecuteMortality() -> Dict[str, Any]:
{
    "success": bool,
    "message": str,
    "data": Dict or None,       # 成功时含 events 列表
    "errors": List[str],        # 失败时含错误信息
    "feedback_type": str,        # "success" | "error" | "warning" | "info"
    "feedback_message": str,     # 已在 store 内广播
}
```

成功时 Store 自动触发：
- `mortality_result` 更新
- `mortalityViewChanged.emit()`
- `snapshotChanged.emit()`

---

## 5. 非 Mortality 阶段的 Store 绑定（参考）

以下绑定用于非天命阶段的 slot 内容：

| QML 属性 / 位置 | 绑定表达式 | Store 字段 | 更新信号 |
|----------------|-----------|-----------|:--------:|
| 非 Mortality Header `visible` | `sessionStore.selectedPhaseId !== "mortality"` | `selectedPhaseId` | `phaseChanged` |
| 非 Mortality 标题 | `sessionStore.selectedPhaseName \|\| sessionStore.currentPhaseName \|\| GuiText.populationFallbackName` | `selectedPhaseName` / `currentPhaseName` | `phaseChanged` / `snapshotChanged` |
| 非 Mortality 描述 | `sessionStore.selectedPhaseSummary.description \|\| GuiText.placeholderFallbackDescription` | `selectedPhaseSummary.description` | `phaseChanged` |

---

## 6. 全部 Store → QML 属性映射索引

| Store Property/Method | 绑定位置 | QML 文件 |
|----------------------|---------|---------|
| `selectedPhaseId` | StageHeaderSlot visible、StageInstructionSlot visible、StageActionSlot visible、StageContentSlot stageContainer visibility | GameShell.qml |
| `selectedPhaseName` | 非 Mortality 标题 | GameShell.qml |
| `currentPhaseName` | 非 Mortality 标题（回退） | GameShell.qml |
| `selectedPhaseSummary` → `description` | Mortality 描述、非 Mortality 描述 | GameShell.qml |
| `selectedPhaseSummary` → `actionable` | 非 Mortality 模式状态颜色 | GameShell.qml |
| `selectedPhaseSummary` → `interaction_mode` | 非 Mortality 模式状态文本 | GameShell.qml |
| `mortalityEvents` | Repeater model、空状态可见性 | MortalityStage.qml |
| `mortalityEvents[].name` | 事件卡片标题 | MortalityStage.qml |
| `mortalityEvents[].summary` | 事件卡片摘要 | MortalityStage.qml |
| `canExecuteMortality` | 按钮 enabled | GameShell.qml |
| `doExecuteMortality()` | 按钮 onClicked | GameShell.qml |

---

## 7. 信号 → QML 响应映射

| Store 信号 | 触发时机 | 影响 QML 绑定 |
|-----------|---------|-------------|
| `phaseChanged` | `selectPhase()`, `_refresh_snapshot()` | 全部 `selectedPhase*` 绑定 |
| `mortalityViewChanged` | `doExecuteMortality()`, `doAdvanceMortality()`, `selectPhase("mortality")`, 刷新 | `mortalityEvents`, `canExecuteMortality` |
| `snapshotChanged` | 刷新、API 操作成功 | 非 Mortality 标题/描述 |
| `feedbackRaised` | 所有 Store 操作 | 由 Store 内部 `_raise_feedback()` 直接发射到 ContextPanel |

---

**文档状态：** 完成 ✅
**下次审核者：** SA / Codex Reviewer
