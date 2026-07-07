# GUI-P0-03C 天命阶段GUI对齐 技术边界审查报告

- **日期：** 2026-07-06
- **角色：** SA（系统架构师）
- **代码基线：** `2c2de94e0d8931325d737f5957c6d18569275557`

---

## 一、审查结果

| 项目 | 结论 |
|------|------|
| API 可用性 | ⚠️ 需微调 — 见下方发现#4 |
| 架构影响 | 🟢 无 — 纯 GUI/Service DTO 层面改动 |
| 数据模型影响 | 🟡 微调 — `mortality_service._handle_death_event` 返回数据需补充字段 |
| 测试影响 | 🟢 无 — 测试逻辑不变 |
| 多玩家影响 | 🟢 无 |
| 回滚风险 | 🟢 低 — 仅修改 3~4 个文件，不涉及 Core/GameState 逻辑 |

---

## 二、代码差异分析

### 差异① — 中央操作按钮：圆形→矩形

| 维度 | 当前代码 | 目标（V3.23 + 设计文档） |
|------|---------|------------------------|
| 形状 | `Rectangle { radius: width/2 }` → 120×120 圆 | **矩形**，深红底色 #8B2500 + 金色文字 #FFD700 |
| 尺寸 | 120×120 | ~180×52 |
| 布局 | 中央 ColumnLayout，⚡+文字上下排列 | 居中独立矩形，无超大图标 |
| 执行后状态 | 灰化，文字「已执行」 | 灰化 + 红勾，文字「已完成」 |
| 可重复点击 | 按钮禁用 + opacity 渐变 | 同（已有机制，无需大改） |

**当前代码位置：** `MortalityStage.qml` 底部 `execBtn` Rectangle

**修改方案：**
- 去除 `radius: width / 2` 设定
- 宽度 120→180，高度 120→52，radius 改为 theme.radius (≈4)
- 布局从 ColumnLayout 改为 RowLayout 或单一 Text 居中
- 执行后文案从「已执行」改为「已完成」

### 差异② — 推进入口位置：底部 + ContextPanel 双入口

| 维度 | 当前代码 | 目标 |
|------|---------|------|
| 主入口 | 底部 RowLayout（箭头+推进按钮同一行） | **ContextPanel 右侧栏**下方 |
| 辅助入口 | 无 | 底部保留作为辅助 |
| 当前推进按钮 | 在 execBtn 同一 RowLayout，`visible: canAdvanceMortality` | 主入口移到 ContextPanel，底部保留 |

**当前代码位置：**
- `MortalityStage.qml`：推进按钮在底部 RowLayout
- `ContextPanel.qml`：无推进按钮区域

**修改方案：**
- ContextPanel.qml 底部 "flow control buttons" 区域（当前 `AppButton` × 2 的位置）增加「⏭️ 进入收入」按钮，仅在 Mortality 阶段且 `canAdvanceMortality===true` 时显示
- MortalityStage.qml 底部保留辅助推进按钮（可选，可移除）
- 新增按钮逻辑：调用 `sessionStore.doAdvanceMortality()`

### 差异③ — 死亡事件详情：泛化渲染→四项明确字段

| 维度 | 当前代码 | 目标 |
|------|---------|------|
| 死者名称 | `modelData.name` | 明确显示 **死者名称** |
| 所属派系 | — | 明确显示 **所属派系** |
| 损失土地 | — | 显示 **损失土地数量（收归国库）** |
| 损失财富 | — | 显示 **损失财富数量（收归国库）** |
| 渲染方式 | `Repeater model: impacts` → `ImpactDetail` 泛化组件 | 特定死亡事件卡片 |

**当前代码位置：** `MortalityStage.qml` 中央 ScrollView → Repeater → delegate

**技术发现 #4 相关：** 当前 `mortality_service._handle_death_event` 返回的 `impact` 对象 **不含 land/wealth 数据**。参见差异④。

### 差异④ — 事件结果模型：数组→单事件

| 维度 | 当前代码 | 目标 |
|------|---------|------|
| 数据源 | `sessionStore.mortalityEvents`（数组） | **单事件**（取数组第一项） |
| QML 渲染 | `Repeater { model: sessionStore.mortalityEvents }` | 单事件卡片 |
| API 返回 | `{"events": [event]}`（`event_draw_count=1`，但结构为数组） | 设计规范触发一个事件，取 `events[0]` |

**当前代码位置：** `MortalityStage.qml` 中央 ScrollView → Repeater
**辅助：** `session_store.py` 的 `mortalityEvents` property

**修改方案：**
- 在 `session_store.py` 新增 `mortalityEvent`（单数）property：
  ```python
  @Property(dict, notify=mortalityViewChanged)
  def mortalityEvent(self) -> Dict[str, Any]:
      events = self._mortality_result.get("events", [])
      if events:
          return events[0]
      # 回退到 mortality_view 中的 events
      view_events = self._mortality_view.get("events", [])
      return view_events[0] if view_events else {}
  ```
- `MortalityStage.qml` 中 `Repeater` 替换为**条件渲染**：
  - 死亡事件：专用死亡详情卡片（四项字段）
  - 丰收事件：摘要展示
  - 和平事件：摘要展示
  - 英雄事件：摘要展示

### 差异⑤ — 全局边距密度

| 维度 | 当前代码 | 目标（参照 Senate 对齐经验） |
|------|---------|---------------------------|
| MortalityStage 容器 margins | `anchors.margins: 20` | **≤12** |
| ColumnLayout spacing | `12` | **4~8** |
| 中央 ScrollView margins | `anchors.margins: 12` | 可保留或压缩至 **8** |

**当前代码位置：** `MortalityStage.qml` 顶层 ColumnLayout

---

## 三、技术发现

### 发现 #1 — 土地/财富数据不在事件结果中（⚠️ 需微调 Core DTO）

**问题：** `mortality_service._handle_death_event()` 调用 `self.state.mark_member_dead(victim.id, transfer_land=True, transfer_wealth=True)` 执行了资产回收，但**没有捕获 `victim.wealth` 和 `victim._land_private` 的值**放入返回的 impact 对象。

**影响：** QML 无法从现有数据获取损失土地/财富数量。

**解决方案（推荐）：** 在 `mortality_service._handle_death_event()` 中，在调用 `mark_member_dead` 之前先读取数值，然后添加到 impact 中：

```python
# 在 _handle_death_event 中，在 mark_member_dead 调用前：
lost_wealth = victim.wealth
lost_land = victim._land_private

# ... 然后调用 mark_member_dead ...

# 在 impact 中添加：
impacts.append({
    "type": "figure_death",
    "figure_id": victim.id,
    "figure_name": victim.name,
    "faction_id": victim.faction_id,
    "faction_name": faction_name,
    "lost_wealth": lost_wealth,    # ← 新增
    "lost_land": lost_land,        # ← 新增
    "terminated_contracts": terminated_contracts,
})
```

**影响范围：** 仅 `src/core/service/mortality_service.py`，不改变 Core 规则逻辑，仅补充返回数据字段。

### 发现 #2 — 其他事件类型数据结构

| 事件类型 | union 字段 | 展示方式 |
|---------|-----------|---------|
| `death` | `effect: "death"` | 四项死亡详情卡片（新增） |
| `bountiful_harvest` | `effect: "bountiful_harvest"` | 摘要文字（已有） |
| `peace` | `effect: "peace"` | 摘要文字 + 影响列表（已有） |
| `hero` | `effect: "hero"` | 摘要文字（如果存在，需验证） |

### 发现 #3 — ContextPanel 推进按钮须限定阶段

ContextPanel 底部的推进按钮仅在 `sessionStore.currentPhaseId === "mortality"` 且 `sessionStore.canAdvanceMortality === true` 时可见。修改 `ContextPanel.qml` 时需添加阶段判断条件。

---

## 四、修改文件清单（建议）

| 文件 | 修改内容 | 风险 |
|------|---------|------|
| `src/core/service/mortality_service.py` | `_handle_death_event` 补充 `lost_wealth`/`lost_land` 到 impact | 🟢 低 — 纯添加字段 |
| `src/ui/gui/session_store.py` | 新增 `mortalityEvent`（单数）property | 🟢 低 |
| `src/ui/gui/qml/stages/MortalityStage.qml` | 按钮形状/布局/单事件渲染/边距压缩 | 🟢 低 |
| `src/ui/gui/qml/shell/ContextPanel.qml` | 添加推进按钮（带阶段判断） | 🟢 低 |

## 五、不修改文件

| 文件 | 理由 |
|------|------|
| `GameShell.qml` | 阶段容器布局已在 Senate 对齐时调整（`stageAnnouncement` 高度从 96→压缩版时已处理），本次无需改动 |
| `TopStatusBar.qml` / `BottomQueryBar.qml` | 已在 Senate 对齐中调整，本次不涉及 |
| 任何 Core / Entity / API 层文件 | OOS — 纯 GUI 布局调整 |

## 六、回滚方案

如果修改后需要回滚：

```bash
git checkout -- src/ui/gui/qml/stages/MortalityStage.qml
git checkout -- src/ui/gui/qml/shell/ContextPanel.qml
git checkout -- src/ui/gui/session_store.py
git checkout -- src/core/service/mortality_service.py
```

无需重置 Git HEAD 或影响其他文件。

---

**SA 审查结论：** 🟢 可交付 DA — 含 1 个 Core DTO 微调发现（#4），不影响规则逻辑

**交付给：** DA
**后续步骤：** 产出 DA 技术开发任务书 → DA 执行
