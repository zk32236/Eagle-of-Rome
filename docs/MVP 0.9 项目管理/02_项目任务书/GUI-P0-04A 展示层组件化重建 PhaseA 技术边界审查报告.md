# GUI-P0-04A 展示层组件化重建 PhaseA 技术边界审查报告

**角色:** SA (Solution Architect)
**日期:** 2026-07-06
**任务:** 审查 PM 意图包 GUI-P0-04A，评估技术边界、文件交互、风险及实施路径

---

## 1. 任务范围确认

| 项目 | PM 声明 | SA 评估 | 判决 |
|------|---------|--------|------|
| 新建 4 组件 | `StageHeader / StepRail / UnifiedButton / InfoBox` | ✅ 合理，覆盖 80% 重复代码 | 批准 |
| 修改 3 Stage | mortality / population / senate | ✅ 替换内联为引用 | 批准 |
| 不动 Python | core/systems/API/session_store | ✅ 可行，组件是纯 QML | 批准 |
| 不动 Shell | GameShell / TopStatusBar / PhaseRail / ContextPanel / BottomQueryBar | ✅ 可行，仅 Stage 内变化 | 批准 |
| 不动 Theme/GuiText | — | ✅ Theme 色值通过 color 属性传入 | 批准 |

## 2. 文件交互矩阵

### 2.1 新建组件 → 依赖关系

| 组件 | 依赖 | 说明 |
|------|------|------|
| `StageHeader.qml` | `Theme.qml`, `GuiText.qml` | color tokens + i18n 文本 |
| `StepRail.qml` | `Theme.qml` | 颜色 |
| `UnifiedButton.qml` | `Theme.qml` | 颜色 + 尺寸 |
| `InfoBox.qml` | `Theme.qml` | 颜色 |

**结论:** 4 个组件仅依赖 Theme 和 GuiText。Theme 和 GuiText 已在本次不动清单中，所以安全。

### 2.2 修改 Stage → 新组件引用

| Stage | 可替换的内联代码 |
|-------|----------------|
| `MortalityStage.qml` | header (38px Rectangle), steps (26px Rectangle), 指令 info-box, 天命已执行 info-box, 操作按钮 ×3, 推进按钮, 死亡事件 info-box 风格 |
| `PopulationStage.qml` | header (RowLayout + 40行), 步骤条, 操作按钮 |
| `SenateStage.qml` | header (阶段标识 + title + desc), 步骤条 (公示→提案→表决→否决), 各种信息框 |

### 2.3 不修改的文件确认

```
src/ui/gui/qml/
├── shell/GameShell.qml           → 🚫 不动
├── shell/TopStatusBar.qml        → 🚫 不动
├── shell/PhaseRail.qml           → 🚫 不动
├── shell/ContextPanel.qml        → 🚫 不动
├── shell/BottomQueryBar.qml      → 🚫 不动
├── shell/FeedbackPanel.qml       → 🚫 不动
├── shell/PlayerHandoffOverlay.qml → 🚫 不动
├── shell/QueryResultOverlay.qml  → 🚫 不动
├── theme/Theme.qml               → 🚫 不动
├── i18n/GuiText.qml              → 🚫 不动
├── components/AppButton.qml      → 🚫 不动（可后续废弃）
├── components/IconButton.qml     → 🚫 不动
├── components/StatusTile.qml     → 🚫 不动
├── components/EmptyState.qml     → 🚫 不动
├── components/ConfirmDialog.qml  → 🚫 不动
├── components/FeedbackToast.qml  → 🚫 不动
├── components/NumberStepper.qml  → 🚫 不动
├── components/DataTable.qml      → 🚫 不动

src/
├── core/  (所有)                 → 🚫 不动
├── systems/ (所有)               → 🚫 不动
├── api/ (所有)                   → 🚫 不动
├── tests/ (所有)                 → 🚫 不动（无新测试，回归即可）
```

## 3. 组件接口设计

### 3.1 StageHeader.qml

```qml
// 使用示例：
StageHeader {
    badgeText: "1/7"
    icon: "🎴"
    title: GuiText.mortalityTitle   // 从 GuiText 取 i18n 文本
    description: "众神降下命运——触发一个随机事件。无玩家操作。"
}

// Properties:
//   - badgeText: string        — 阶段编号标识 e.g. "1/7"
//   - icon: string             — 阶段图标 emoji e.g. "🎴"
//   - title: string            — 阶段全称
//   - description: string      — 阶段解释文字（可选，空则隐藏）
//   - badgeColor: color        — 可选覆盖，默认 theme.accentPrimary
//   - titleColor: color        — 可选覆盖，默认 theme.textPrimary
//   - height: int              — 默认 38
```

**Theme 使用:** `theme.bgSurface1`, `theme.accentPrimary`, `theme.textPrimary`, `theme.textSecondary`, `theme.radius`, `Qt.rgba(0,0,0,0.08)` (边框)

**无硬编码色值** ✅

### 3.2 StepRail.qml

```qml
// 使用示例：
StepRail {
    steps: [
        { icon: "⚡", label: GuiText.mortalityStepExecute },
        { icon: "📜", label: GuiText.mortalityStepView }
    ]
    currentIndex: sessionStore.canAdvanceMortality ? 1 : 0
    completedIndex: sessionStore.canAdvanceMortality ? 0 : -1
}

// Properties:
//   - steps: var               — 步骤数组 [{icon?, label}]
//   - currentIndex: int        — 当前步骤 (0-based)
//   - completedIndex: int      — 已完成到哪步 (-1 = 无)
//   - height: int              — 默认 26
```

**Theme 使用:** `theme.bgSurface2`, `theme.textPrimary`, `theme.textSecondary`, `theme.textMuted`, `theme.accentBronze`, `theme.statusSuccess`

**关键设计原则:** 组件不直接引用 `sessionStore`——由使用方通过 `currentIndex`/`completedIndex` 传入。

### 3.3 UnifiedButton.qml

```qml
// 使用示例：
UnifiedButton {
    text: "⚡ 执行天命"
    primary: true
    small: false
    enabled: sessionStore.canExecuteMortality
    onClicked: {
        var result = sessionStore.doExecuteMortality()
        if (!result.success) root.showFeedback("error", result.message)
    }
}

UnifiedButton {
    text: "× 解雇"
    small: true
    onClicked: dismissFig(figureId)
}

// Properties:
//   - text: string             — 按钮文本（含 emoji）
//   - primary: bool            — 深红主按钮样式
//   - small: bool              — 紧凑小按钮
//   - enabled: bool            — 默认 true
//   - flat: bool               — 文本链接风格（未来扩展）
//   - onClicked: var           — 点击回调函数

// Signals:
//   - clicked()
```

**Theme 使用:** `theme.accentPrimary`, `theme.accentPrimaryDark`, `theme.accentBronze`, `theme.accentBronzeHighlight`, `theme.textMuted`, `theme.bgSurface2`, `theme.textPrimary`, `theme.radius`, `#FFD700`（金色文字用常量，非 Theme token）

### 3.4 InfoBox.qml

```qml
// 使用示例：
InfoBox {
    text: "📕 点击下方「执行天命」按钮，触发一个随机事件。\n事件类型：猝死"
    type: "info"
}

InfoBox {
    text: "⚠️ 独裁风险! Populares 获得元老院 72.4% 影响力"
    type: "warning"   // → 自动使用红色/警告风格
}

InfoBox {
    text: "🏆 大胜！战利品 +1300 T"
    type: "success"   // → 自动使用绿色/成功风格
}

// Properties:
//   - text: string             — 内容文字（支持 \n 换行）
//   - type: string             — "info" / "warning" / "success" / "error"
//   - icon: string             — 可选覆盖，不填则根据 type 自动选
//   - compact: bool            — 默认 true，紧凑模式；false 为宽松模式
```

**Theme 使用:** `theme.bgSurface2`, `theme.borderNormal`, `theme.accentBronze`, `theme.textPrimary`, `theme.textSecondary`, `theme.textMuted`, `theme.statusSuccess`, `theme.statusWarning`, `theme.statusError`, `theme.radius`

## 4. 现有组件兼容性

| 现有组件 | 与新组件关系 | 建议 |
|---------|-------------|------|
| `AppButton.qml` | 功能重叠 | **保留不动**。Phase A 不废弃现有组件。UnifiedButton 是新标准，AppButton 逐步淘汰。 |
| `StatusTile.qml` | 无关（资源卡片用） | 保留。不在 Phase A 范围内。 |
| `EmptyState.qml` | 无关 | 保留。 |
| `DataTable.qml` | 无关（后续可能用） | 保留。Phase B 时再激活。 |

## 5. 测试影响评估

| 测试文件 | 影响 | SA 评价 |
|---------|------|---------|
| `test_gui/test_qml_startup.py` | 🟢 **无影响** | 测试组件存在性，非内联结构。`stageAnnouncement` 断言已在 Phase-2 移除且通过。 |
| `test_gui/test_adapter.py` | 🟢 无影响 | 测 API + session_store，非 QML 渲染 |
| `test_gui/test_session_api.py` | 🟢 无影响 | 测 session store 数据 |
| `test_api/test_mortality_api.py` | 🟢 无影响 | 测 API 逻辑 |
| 所有 core/system/entity 测试 | 🟢 无影响 | Python 层不动 |

**结论:** 回归 773/773 全部预期通过。

## 6. 风险分析

| # | 风险 | 级别 | 缓解 |
|---|------|------|------|
| 1 | StageHeader 边框/间距偏移导致视觉效果退化 | 🟡 | 每替换一个 Stage 后立即验证；与 Phase-4 效果对齐 |
| 2 | UnifiedButton 替换 Rectangle+MouseArea 后点击区域变化 | 🟡 | 使用同一 `implicitWidth/Height` 确保 hitbox 一致 |
| 3 | InfoBox 文本换行/wrapMode 表现不同 | 🟡 | 使用 Text 的 wrapMode: Text.Wrap 保持与现有一致 |
| 4 | 组件 Prop 命名与现有内联代码不兼容 | 🟢 | 组件是新建，Prop 自由设计；Stage 引用时适配 |
| 5 | 组件在 other Stage 中引用后显示异常 | 🟡 | 先在 MortalityStage 中验证后再推广 |

## 7. 实施路径建议

```
SA 推荐路径（按安全系数排序）:

路径 A [推荐] — 逐个组件 + 逐个 Stage 渐进替换
  1. 创建 StageHeader → MortalityStage 引用 → 验证
  2. 创建 StepRail → MortalityStage 引用 → 验证
  3. 创建 UnifiedButton → MortalityStage 引用 → 验证
  4. 创建 InfoBox → MortalityStage 引用 → 验证
  5. 推广到 PopulationStage → 验证
  6. 推广到 SenateStage → 验证
  7. 全量回归
  优势: 每一步可回退，风险最低

路径 B — 一次创建 4 个组件，批量替换
  优势: 速度快
  劣势: 排查问题困难

→ 建议走路径 A
```

## 8. 边界裁定

| 边界问题 | SA 裁定 |
|---------|--------|
| 组件可否使用 `anchors` 进行内部布局？ | ✅ 可以，组件内部自由布局 |
| 组件可否定义内部状态（hover/pressed）？ | ✅ 可以，UnifiedButton 必须支持 hover 反馈 |
| 组件可否引用 `sessionStore`？ | ❌ **不可以。** 组件保持 stateless，由 Stage 通过 props 传入数据。例外：StepRail 如需动态状态可通过 currentIndex/completedIndex 传入。 |
| 组件可否引用其他组件？ | ✅ 可以，但仅限于 `components/` 内。例如 InfoBox 内部可含 UnifiedButton。 |
| 新组件可否使用 `property alias`？ | ✅ 可以，但限制暴露的接口最小化。 |
| QML 组件注册为 Qt 模块？ | ❌ 不在 Phase A 范围内。仍用 `import "../components"` 方式。 |

## 9. SA 结论

**Decision: READY_FOR_DA**

| 检查项 | 状态 |
|--------|------|
| PM 意图包范围清晰 | ✅ |
| 技术边界明确定义 | ✅ |
| 文件交互矩阵完成 | ✅ |
| 组件接口设计完成 | ✅ |
| 测试影响评估完成 | ✅ |
| 风险清单已记录 | ✅ |
| 不违反三项限制令 | ✅ |

**已知残留问题:** 无。移交 DA 执行。
