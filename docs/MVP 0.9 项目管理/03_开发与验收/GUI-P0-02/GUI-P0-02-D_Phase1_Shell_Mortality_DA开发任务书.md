# DA 开发任务书 — Phase 1: Shell 外壳 + 天命阶段垂直切片

**Sequence Deliverable #3**
**角色：DA（奥古斯都 — DA 任务书起草）**
**日期：2026-07-11**
**代码基准：`main` (65bbf67)**
**上游：** PM 意图包 ✅ | SA 边界审查 ✅ READY_FOR_DA

---

## 1. 目标

将 EOR GUI 的 Shell 外壳 + 天命阶段视觉对齐 v3.25.1 HTML 原型，形成一条完整的可运行垂直切片。

---

## 2. 文件清单

### 2.1 新建文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| N1 | `PhaseRailIcon.qml` | `src/ui/gui/qml/components/` | 44px 圆形图标组件，hover 弹名称 |
| N2 | `StepBar.qml` | `src/ui/gui/qml/components/` | 通用步骤引导条组件 |

### 2.2 修改文件

| # | 文件 | 路径 | 改动类型 |
|---|------|------|---------|
| M1 | `TopStatusBar.qml` | `src/ui/gui/qml/shell/` | 样式更新 + `warCount` 绑定 |
| M2 | `PhaseRail.qml` | `src/ui/gui/qml/shell/` | 内嵌 `PhaseRailIcon` 组件替换文本列表 |
| M3 | `ContextPanel.qml` | `src/ui/gui/qml/shell/` | 样式更新，移除 C3 进度指示 |
| M4 | `BottomQueryBar.qml` | `src/ui/gui/qml/shell/` | 深朱红背景色 |
| M5 | `QueryResultOverlay.qml` | `src/ui/gui/qml/shell/` | 遮罩/标题/内容区对齐 |
| M6 | `MortalityStage.qml` | `src/ui/gui/qml/stages/` | 视觉重建（StepBar + 羊皮纸卡片 + 按钮对齐） |
| M7 | `session_store.py` | `src/ui/gui/` | 新增 `warCount` Property + fallback phase 修复（SA-01） |

### 2.3 不修改但需确认的文件

| 文件 | 原因 |
|------|------|
| `GameShell.qml` | 阶段切换逻辑不变，仅确认 PhaseRail 父布局兼容 44px 图标高度 |
| `Main.qml` | 主入口不动 |

---

## 3. 实施顺序（建议执行顺序）

### Step 1: fallback phase 修复（SA-01）
**文件：** `session_store.py`
**改动：**
- `_refresh_snapshot()` (L452-453): 将 `self._snapshot.get("selected_phase_id", "mortality")` → `self._snapshot.get("current_phase_id", "mortality")`
- `doAdvanceMortality()` (L329): 删除 `self._selected_phase_id = self._snapshot.get("current_phase_id", "revenue")` 行，因为下一行 `_refresh_snapshot()` 已经在 snapshot 刷新后自动设置 `_selected_phase_id`
- 验证：运行全量 pytest → 确认 773 passed

### Step 2: 新增 `Store.warCount`
**文件：** `session_store.py`
**改动：**
```python
@property
def warCount(self) -> int:
    return len(self._senate_view.get("active_foreign_wars", []))
```
- 作为只读 Property，不添加 `@Slot`（QML 仅读取，不调用）
- 需要 `senateViewChanged` 通知信号

### Step 3: 新建 `StepBar.qml`
**文件：** `src/ui/gui/qml/components/StepBar.qml`
**设计：**
- 输入：`steps`（字符串数组）+ `currentStep`（int，0-indexed）
- 渲染：水平排列圆圈+连线，当前步骤高亮
- 使用 `Repeater` + `ListModel` 实现
- 参考 v3.25.1 HTML 中天命阶段顶部的 2 步骤条

```qml
// 接口设计
property var steps: []
property int currentStep: 0
```

### Step 4: 新建 `PhaseRailIcon.qml`
**文件：** `src/ui/gui/qml/components/PhaseRailIcon.qml`
**设计：**
- 输入：单个 phase 字典（含 `id`, `name`, `index` 等字段）
- 渲染：44px 圆形背景 + Unicode 图标 + hover 显示完整名称
- 图标映射（建议硬编码在组件内，后期可提取到常量字典）：
  - mortality → ⚖️ (或 🎴)
  - revenue → 💰
  - forum → 🏛️
  - population → 👥
  - senate → ⚔️
  - combat → ⚔️
  - resolution → 📜
- 状态：当前阶段高亮、可操作指示、已执行指示

### Step 5: 修改 `PhaseRail.qml`
**文件：** `src/ui/gui/qml/shell/PhaseRail.qml`
**改动：**
- 删除现有 `Repeater` 中的 48px 文本条目 delegate
- 嵌入 `PhaseRailIcon` 组件，使用相同 `sessionStore.phaseNavigation` 模型
- 保持底部刷新/说明按钮不变
- 确认 `ColumnLayout` 能自适应新高度

### Step 6: 修改 `TopStatusBar.qml`
**文件：** `src/ui/gui/qml/shell/TopStatusBar.qml`
**改动：**
- 在国库/派系金库行后添加活跃战争数显示
- `visible: sessionStore.warCount > 0`
- 字体/间距/颜色对齐 v3.25.1

### Step 7: 修改 `BottomQueryBar.qml`
**文件：** `src/ui/gui/qml/shell/BottomQueryBar.qml`
**改动：**
- `color:` 从 `theme.bgSurface1` → 深朱红色（`"#8B2500"` 或 `"#A03A1A"` 参考 v3.25.1）
- 现有 4 个 connected status 按钮样式更新（字体/间距）

### Step 8: 修改 `QueryResultOverlay.qml`
**文件：** `src/ui/gui/qml/shell/QueryResultOverlay.qml`
**改动：**
- 遮罩颜色/透明度对齐 v3.25.1
- 标题/内容区字体间距对齐

### Step 9: 修改 `ContextPanel.qml`
**文件：** `src/ui/gui/qml/shell/ContextPanel.qml`
**改动：**
- 内容区布局/字体对齐 v3.25.1
- 移除 C3 进度指示器（`votedOffices` 等暂时保留，Phase 2 确认）
- 保持 FeedbackPanel 不变

### Step 10: 重建 `MortalityStage.qml`
**文件：** `src/ui/gui/qml/stages/MortalityStage.qml`
**改动：**
- 顶部插入 `StepBar` 组件（2 步骤：执行天命 → 查看事件）
- 事件展示区从普通矩形 → 羊皮纸卡片风格（`Rectangle` + `color: "#f5e6c8"` + `border` + `radius`）
- 影响项列表改用 `ListItem` 风格
- 执行/推进按钮样式对齐 v3.25.1
- **重要：** 所有功能绑定不动（`doExecuteMortality()`, `doAdvanceMortality()`, `mortalityEvents`, `canExecuteMortality`, `canAdvanceMortality`）

### Step 11: 回归测试 + Git commit

---

## 4. 各文件改动详情

### 4.1 `session_store.py` — 改动说明

**新增代码块（放在 senate 相关 Property 区域附近）：**
```python
@Property(int, notify=senateViewChanged)
def warCount(self) -> int:
    return len(self._senate_view.get("active_foreign_wars", []))
```

**修改 `_refresh_snapshot()` (L452-453)：**
```python
# 修改前
if not self._selected_phase_id:
    self._selected_phase_id = self._snapshot.get("selected_phase_id", "mortality")

# 修改后
if not self._selected_phase_id:
    self._selected_phase_id = self._snapshot.get("current_phase_id", "mortality")
```

**修改 `doAdvanceMortality()` (L329)：**
```python
# 修改前
self._selected_phase_id = self._snapshot.get("current_phase_id", "revenue")

# 修改后
# 删除该行——_refresh_snapshot() 下一行已自动设置
```

### 4.2 QML 改动要点

所有 QML 改动遵循以下原则：
1. **不改 `onClicked` 回调** — Store 方法调用路径不变
2. **不改 `model` 绑定** — 数据来自 sessionStore 的路径不变
3. **仅改视觉属性** — `color`, `font.*`, `Layout.margins`, `border.*`, `radius`, 子控件布局
4. **样式参考** — `EOR_GUI_Prototype_v3.25.1.html` 为唯一视觉参考

---

## 5. 测试策略

| 类型 | 命令 | 预期 |
|------|------|------|
| 回归测试 | `python -m pytest src/tests/ -q` | ≥773 passed |
| 增量测试 | 无新测试 | 零 API 变更，不需新 pytest |
| 视觉验证 | 启动游戏 GUI | Shell 5 区域视觉对齐 v3.25.1 |
| 功能验证 | 天命阶段执行→推进 | 全链路可走通 |
| 启动验证 | 加载非天命阶段存档 | Shell 正确显示当前阶段 |

---

## 6. 回滚计划

| 场景 | 回滚操作 |
|------|---------|
| Phase 1 全部文件改动 | `git checkout -- src/ui/gui/qml/` + `git checkout -- src/ui/gui/session_store.py` |
| 单个文件改动 | `git checkout -- <filepath>` |
| 已 commit 但需撤销 | `git revert HEAD`（如果 Phase 1 单次 commit） |

Pre-Task Baseline: `65bbf67` + 干净工作区。

---

## 7. 实施约束

| 约束 | 说明 |
|------|------|
| 无 API 变更 | 不得新增/修改 `api/` 目录任何文件 |
| 无功能逻辑改动 | 所有 Store 方法/Slot/QML onClicked 保持原样 |
| 样式严格对齐 | 以 `v3.25.1.html` 为准，不得带入主观设计 |
| 渐进式修改 | 一次改一个文件，每步运行 pytest 确认 |
| SA-01 优先 | 必须先完成 fallback phase 修复再改 QML |

---

## 8. 交付检查清单

```
[ ] 新建 2 个 QML 组件已创建
[ ] 6 个现有 QML 已修改并验证
[ ] session_store.py 修改完成（warCount + fallback 修复）
[ ] 全量 pytest ≥773 passed
[ ] Step 1-11 全部完成
[ ] 启动游戏验证 Shell + 天命阶段
[ ] 启动游戏验证非天命阶段存档
[ ] Git commit（建议分 3 次：① session_store ② StepBar+PhaseRailIcon ③ 5 Shell + Mortality）
```

---

**交付状态：DA 开发任务书（Sequence Deliverable #3）— 完成 ✅**
**等待 Main Session 确认 → 确认后启动 DA-Exec 编码**
