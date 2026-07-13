# SA 边界审查报告 — Phase 1: Shell 外壳 + 天命阶段垂直切片

**Sequence Deliverable #2**
**角色：SA（奥古斯都）**
**日期：2026-07-11**
**审查对象：PM 意图包 — `PM_INTENT_PACKAGE_Phase1_Shell_Mortality.md`**
**代码基准：`main` (65bbf67)**

---

## 审查结论

**✅ READY_FOR_DA**

SA 审查确认：PM 意图包的目标、范围、约束和验收标准已完成。Phase 1 无 API 变更、无数据模型变更、无存档兼容问题、无平衡影响、无非后端依赖。技术边界清晰，可进入 DA 阶段。

---

## 1. 模块影响分析

| 模块 | 修改类型 | SA 评估 |
|------|---------|---------|
| `qml/shell/TopStatusBar.qml` | 样式更新 (Reuse) | ✅ 安全。现有 Property 绑定保持不变，仅改字体/间距/颜色。新增 `Store.warCount` 绑定为只读，数据不存在时隐藏。 |
| `qml/shell/PhaseRail.qml` | 组件替换 (New PhaseRailIcon.qml) | ✅ 安全。现有 `sessionStore.phaseNavigation` 数据模型和分析保持不变。`sessionStore.selectPhase()` 调用路径不变。从 176px 文本条目 → 44px 圆形图标，垂直空间显著减少，需确认不影响父布局。 |
| `qml/shell/ContextPanel.qml` | 样式更新 + 移除进度指示 | ✅ 安全。现有数据绑定不变。移除 C3 进度指示器不破坏功能（Phase 2 重建）。 |
| `qml/shell/BottomQueryBar.qml` | 背景色 + 现有按钮样式 | ✅ 安全。`queryButtons` 数组和 `queryRequested` 信号不变。占位按钮的 `status: "placeholder"` 不变。 |
| `qml/shell/QueryResultOverlay.qml` | 遮罩/标题/内容区视觉对齐 | ✅ 安全。现有 `open()`/`close()` API 和 `sessionStore.globalQueryResult` 绑定不变。 |
| `qml/stages/MortalityStage.qml` | 视觉重建 | ✅ 安全。现有功能绑定全部保持不变：`sessionStore.mortalityEvents`、`sessionStore.canExecuteMortality`、`sessionStore.canAdvanceMortality`、`sessionStore.doExecuteMortality()`、`sessionStore.doAdvanceMortality()`。仅改视觉呈现（插入 StepBar、羊皮纸卡片、按钮对齐）。**这是 Phase 1 中影响最大的文件，但功能逻辑零变更。** |
| **新建** `PhaseRailIcon.qml` | 新组件 | ✅ PhaseRail 内嵌。独立组件，不影响其他模块。 |
| **新建** `StepBar.qml` | 新组件 | ✅ 首次在天命阶段实例化。通用组件，Phase 2 可在人口阶段复用。 |
| `session_store.py` | 新增 Property + fallback 修复 | ✅ 见 §2.1 和 §2.2 |

---

## 2. 技术审查发现

### 2.1 Fallback Phase 不统一（SA-01）— 确认存在，需修复

实际代码审计确认 `session_store.py` 中有三处不一致：

| 位置 | 代码 | Fallback | 键名 |
|------|------|----------|------|
| `_refresh_snapshot()` (L452-453) | `self._snapshot.get("selected_phase_id", "mortality")` | `"mortality"` | `selected_phase_id` |
| `doAdvanceMortality()` (L329) | `self._snapshot.get("current_phase_id", "revenue")` | `"revenue"` | `current_phase_id` |
| `currentPhaseId` property (L128) | `self._snapshot.get("current_phase_id", "mortality")` | `"mortality"` | `current_phase_id` |

**问题：**
- 同一数据使用了两个不同的键名：`selected_phase_id` vs `current_phase_id`
- 两个不同的 fallback 默认值：`"mortality"` vs `"revenue"`
- 如果 snapshot 缺少这两个字段（极少情况），游戏可能从 `"revenue"` 阶段启动

**修复方案（DA 实施）：**
- 统一使用 `current_phase_id`（这是后端返回的真实当前阶段）
- `_refresh_snapshot()` 和 `doAdvanceMortality()` 中的赋值方式一致
- fallback 统一为 `"mortality"`（既符合游戏流程设计，也与 HTML 原型对齐）
- 删除 `doAdvanceMortality()` 中对 `_selected_phase_id` 的手动设置（因为接下来会调用 `_refresh_snapshot()`，snapshot 已经包含更新后的 `current_phase_id`）

### 2.2 warCount 数据源（PM 意图包 A6）— 确认可行

| 维度 | 确认结果 |
|------|---------|
| 数据来源 | `senate_api.get_senate_summary()` 的 `summary.active_foreign_war_count` |
| Store 已有数据 | `_senate_view` 已包含完整 `active_foreign_wars` 列表 |
| 现有 Property | `activeForeignWars` (L217) 已返回 wars 列表 |
| 推荐实现 | `Store.warCount = len(self.activeForeignWars)` 或 `self._senate_view.get("summary", {}).get("active_foreign_war_count", 0)` |
| 风险 | 🟢 低 — 纯只读，数据不存在时返回 0 或隐藏 |

### 2.3 PhaseNavigation 数据结构确认

`session_api.py` 中 `_build_phase_navigation()` 输出的 phase 字典字段：

| 字段 | 类型 | 说明 | PhaseRailIcon 用途 |
|------|------|------|-------------------|
| `id` | str | 阶段标识（`"mortality"`, `"revenue"` 等） | 点击时传给 `selectPhase()` |
| `name` | str | 阶段中文名（"天命"等） | hover 时显示 |
| `index` | int | 阶段序号 (1-7) | 可选显示序号 |
| `actionable` | bool | 当前是否可操作 | 颜色/状态指示 |
| `implemented` | bool | GUI 是否已实现 | 颜色/状态指示 |
| `current` | bool | 是否为当前真实阶段 | 高亮指示 |
| `executed` | bool | 是否已执行完毕 | 状态指示 |

**评估结论：** 数据模型完全可支持 44px 圆形图标 + hover 名称。图标映射建议使用 Unicode/Emoji（🎴💰🏛️⚔️等），不引入图片资源依赖。

### 2.4 布局风险评估

| 风险 | 评估 |
|------|------|
| PhaseRail 从 176px 文本条目 → 44px 圆形图标，垂直布局变化 | 🟡 中。需要确认 PhaseRail 父容器（GameShell 中的左侧栏）是否固定高度。如果固定，空间节省无影响；如果是 `Layout.fillHeight`，左侧栏会变矮，右侧内容区自动扩展。**建议：DA 实施时确认 GameShell 布局为 `Layout.fillHeight: true`，这样 PhaseRail 自适应内容高度，不会留白。** |
| MortalityStage 视觉重建后布局是否错位 | 🟢 低。`ColumnLayout` + `anchors.fill: parent` 结构不变，仅更改内部控件样式。 |
| StepBar 在天命阶段首次使用，是否影响其他阶段显示 | 🟢 低。StepBar 仅嵌入 MortalityStage，该 QML 仅当 `selectedPhaseId === "mortality"` 时可见。 |

### 2.5 测试影响

| 测试类别 | 评估 |
|---------|------|
| 现有 pytest (773 passed) | ✅ 无影响。零 API 变更，零后端逻辑变更。 |
| QML 测试 | 项目当前无 QML 自动化测试。视觉验收依赖手动检查。 |

---

## 3. PM 意图包验证

| PM 意图包声明 | SA 验证结果 |
|---------------|------------|
| 无 API 变更 | ✅ 确认 |
| 无数据模型变更 | ✅ 确认 |
| 无存档兼容影响 | ✅ 确认 |
| 无 AI 影响 | ✅ 确认 |
| Balance Impact = None | ✅ 确认 — QGD 不参与 |
| 文件涉及量：6 QML 修改 + 2 新建 + 1 Store | ✅ 确认 |
| AC1-AC9 可在 Phase 1 范围内实现 | ✅ 确认（AC9 需加载存档手动验证） |
| SA-01 fallback 修复 | ✅ 确认修复方案 |

---

## 4. 附加 SA 建议（非阻妥）

以下建议不影响 READY_FOR_DA 结论，DA 可在实施中参考：

| # | 建议 | 理由 |
|---|------|------|
| S1 | PhaseRailIcon 的 icon 映射建议使用常量字典，不 hardcode 在 QML | 方便后期 i18n 或换图标集 |
| S2 | StepBar 的 steps 传入方式：使用 `model: ListModel` + `Repeater`，不使用 QML `property var` 数组 | 更好的 QML 重构响应 |
| S3 | warCount 在 TopStatusBar 中建议用条件可见：`visible: store.warCount > 0` | 无战争时不显示多余 UI |
| S4 | Phase 1 改动完成后建议立即 `git commit` 分次提交，不一次 commit 全部 9 个文件 | 方便回滚 |

---

## 5. 结论

```text
SA 边界审查结论：
✅ READY_FOR_DA

技术边界评估：安全
API 变更：0
数据模型变更：0
Balance Impact：None
存档兼容：无影响
AI 行为：无影响
测试基线：≥773 passed

阻塞项：无
非阻塞修复项：1（SA-01 fallback phase 统一 — 已确认修复方案）

下一环节：DA 开发任务书
```

---

**交付状态：SA 边界审查报告（Sequence Deliverable #2）— 完成 ✅**
**结论：READY_FOR_DA**
**下一环节：DA 开发任务书（Sequence Deliverable #3）**
