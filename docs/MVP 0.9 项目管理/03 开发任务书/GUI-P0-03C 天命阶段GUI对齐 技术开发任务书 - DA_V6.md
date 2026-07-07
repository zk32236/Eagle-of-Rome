# GUI-P0-03C 天命阶段GUI对齐 技术开发任务书 — DA（V6 — V5 + Phase-5 精修叠盖版）

## 一、任务基本信息

| 项目 | 内容 |
|------|------|
| 任务编号 | GUI-P0-03C |
| 任务名称 | 天命阶段 GUI 全视觉收敛 |
| 执行对象 | DA |
| 任务类型 | GUI 全视觉对齐 / 布局、结构、信息架构与交互调整 |
| 优先级 | P0 |
| 所属阶段 | 阶段 GUI 对齐 Sprint |
| 代码基线 | `2c2de94e0d8931325d737f5957c6d18569275557` |
| 技术边界审查 | `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03C 技术边界审查报告.md` |
| 视觉分析参考 | Phase-1 + Phase-2 + Phase-3 + Phase-4 + **Phase-5 视觉收敛规范**（本版本新增） |

## 二、任务目标

将天命阶段整体 GUI 与 V3.23 原型及《EOR GUI设计文档 V2.0》全面对齐。

**V4 已实现（Phase-2 6 Pass + Phase-3 5 Pass）：** 包括结构删除、中央工作区对齐、右边栏 IA 重建、顶部标题栏对齐、视觉 Token 对齐、最终密度调整、以及 Phase-3 的 5 项精修。

**V5 已实现（Phase-2 6 Pass + Phase-3 5 Pass + Phase-4 5 Pass）：** 包括结构删除、中央工作区对齐、右边栏 IA 重建、顶部标题栏对齐、视觉 Token 对齐、密度调整、Phase-3 精修、以及 Phase-4 的容器扁平化/状态权威/边框精简/区域微对齐。

**V6 目标：** 基于 **Phase-5 视觉收敛规范** 执行新一轮 4 Pass 精修，聚焦**状态语义清晰化**（去重复指令、天命已执行 vs 执行天命冲突）、**中央内容放置节奏感**、以及剩余区域微调。

**战略原则（来自 Phase-1 §1 / Phase-5 §1）：**
> The next pass should not reintroduce bordered panels. It should solve **content placement, state clarity, and visual rhythm.**
> Do not redesign the GUI. Continue convergence toward the existing prototype.
> Clarify state authority first.

## 三、背景说明

| 项目 | 内容 |
|------|------|
| 前序版本 | V4（Phase-2 6 Pass + Phase-3 5 Pass）已实现并全量测试通过 |
| V4 验收状态 | 定向测试 15/15 通过 ✅ / 全量回归 773 通过 ✅ |
| V4 交付物 | 任务书 V3/V4 + 开发验收报告 DA（V4） |
| 视觉分析来源 | Phase-4 规范，§1~§19 完整 |
| 本轮目标 | 消除 Phase-4 列出的剩余视觉偏差（容器扁平化 + 状态权威 + 边框精简 + 区域微对齐） |

## 四、依据文档

- `E:\OpenClaw\Projects\EOR\workspace\vision analysis\EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-4.md`（核心依据，§1~§19）
- V4 任务书（Phase-2 + Phase-3 已完成参考）
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI_Prototype_v3.23.html`

## 五、V4 实现状态确认

V4 已实现以下全部内容，本版本不需要重做：

```text
Phase-2: 6 Pass
  Pass 1 — 结构删除 ✅
  Pass 2 — 中央工作区对齐 ✅
  Pass 3 — 右侧边栏重建 ✅
  Pass 4 — 顶部标题栏对齐 ✅
  Pass 5 — 视觉 Token 对齐 ✅
  Pass 6 — 最终密度调整 ✅

Phase-3: 5 Pass
  Pass 1 — 结构清理 ✅（移除就绪标签 / 中央透明 / 无残留）
  Pass 2 — 中央工作区精修 ✅（Header 38 / 指令面板双行 / 横幅紧凑 / 按钮 100×26）
  Pass 3 — 右侧边栏精修 ✅（推进按钮紧金色 / 日志空白精调）
  Pass 4 — 标题栏与底栏精修 ✅（间距 / 活跃态）
  Pass 5 — Token 与密度最终调整 ✅
```

---

# ==================== Phase-4 叠盖层 ====================

> 以下内容叠盖在 V4（Phase-2 6 Pass + Phase-3 5 Pass）之上。
> V4 已实现，Phase-4 新增 5 Pass 精修。

## Phase-4 任务定位

参考：`EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-4.md`

> Actual 4 is a meaningful improvement over Actual 3. The macro five-region architecture is now clearly established.
> However, Actual 4 is no longer a structural reconstruction task. **The next objective is: remove unnecessary containers, clarify action authority, and refine visual hierarchy.**

### V4 → Phase-4 差距概要

| 模块 | V4 状态 | Phase-4 要求 |
|------|---------|-------------|
| 中央工作区 | 无嵌套外边框；事件区 `bgSurface1` | **进一步扁平化** — 移除空容器边框痕迹；整个中央区应读为一张开放式 parchment |
| 空窄带 | 已移除边框但 layout 容器仍在 | **视觉压平** — 空容器不可见 |
| 空大内面板 | 已移除边框 | **视觉压平** — 无可见空卡片效果 |
| Phase header | 38px 紧凑 | **边框降重** — 更像工作区集成元素而非独立卡片 |
| 步骤条 | 26px 紧凑左对齐 | **边框降重** — 进一步弱化外边框 |
| 指令面板 | 双行紧凑 | **卡片感降低** — 暖色分隔线代替卡片边框 |
| 天命已执行 | 紧凑奶油色横幅 | **状态逻辑验证** — 与「执行天命」按钮不冲突 |
| 执行按钮 | 100×26, #E8A030 边 | **状态一致性微调** |
| 右侧边栏 | IA 重建完成 | **推进按钮降重** — 不竞争主操作；**日志底部 artifact 消除** |
| HUD | 5 指标 + SPQR | **间距平衡** — 指标不再左聚 |
| PhaseRail | 圆形活跃态 + 隐藏 dev | **图标大小/节奏微调** — 活跃态略重，垂直间距略松 |
| Bottom Nav | 活跃色 #E8A030 | **再降饱和** — 活跃导航不成为最亮元素 |
| 空日志区域 | 无假事件填充 | **保持中性** — 验证底部裁剪/锚定 |

## Phase-4 5 Pass 实现序列

根据 Phase-4 §16 定义的优先级：P0（中央工作区简化）→ P1（状态/操作权威）→ P2（边框层次）→ P3（区域微对齐）。

---

### Pass 1 — 中央工作区容器扁平化（P0）

参考：Phase-4 §5、§14、§15

#### 1.1 移除窄空带边框痕迹（Phase-4 §5.3 P0）

**依据：** Phase-4 §5 — 中央工作区当前结构：

```text
central workspace
├── bordered phase header
├── bordered workflow strip
├── bordered instruction strip
├── centred "天命已执行" status badge/button
├── × empty bordered horizontal strip ×    ← 此处
├── huge bordered empty panel
└── bottom-centred "执行天命" button
```

V4 已移除大多数可见边框，但 layout 容器的 border 可能仍有残余或空容器仍占据视觉高度。

**操作：** 检查并确保：
- 空窄横条 Rectangle 的 `color: "transparent"`、`border.width: 0`
- 如果该容器无内容，将 `visible: false` 或高度设为 0
- 空大面板 Rectangle：`color: "transparent"`、`border.width: 0`、`radius: 0`
- 整体中央工作区读为一张开放羊皮纸，**不呈现为空卡片内的空卡片**

**文件：** `MortalityStage.qml`

#### 1.2 移除空容器可见背景色（Phase-4 §5.3）

所有中央工作区内的 layout-only 容器（无实性子组件填充时）应使用 `color: "transparent"`，不保留任何有色背景。

**文件：** `MortalityStage.qml`

#### 1.3 确认「就绪」标签无残留

V4（Phase-3）已删除，**不需要重复操作**。仅作为确认项。

#### 1.4 验收标准（Phase-4 §5.3 Acceptance）

```text
[ ] 中央工作区中央没有可见空边框或空卡片背景
[ ] 整个中央区读为一张开放羊皮纸
[ ] 布局容器不因空状态而产生可视边框
```

---

### Pass 2 — 状态与操作权威统一（P1）

参考：Phase-4 §9、§10、§15

#### 2.1 审查「天命已执行」与「执行天命」的关系（Phase-4 §9 / §10）

此 Pass **不修改游戏逻辑**。只做 UI 呈现层面的一致性调整。

**审查要点：**

```text
IF phase is already executed:
    show completion/result state
    do not present "执行天命" as an equally active primary action

IF execution can be repeated by design:
    distinguish "completed state" from "repeat action"

IF "天命已执行" is only a transient notification:
    it should not remain as a permanent central control-like element
```

**具体操作：**

**2.1.1 验证状态逻辑差异**
1. 在 `session_store.py` 中检查 `canExecuteMortality` 和 `canAdvanceMortality` 的切换时机
2. 确认执行后 `canExecuteMortality = false` 时「执行天命」按钮自动禁用/隐藏
3. 如果已存在逻辑区分，**只记录**；如果不存在但 UI 呈现模糊，**报告给 SA**

**2.1.2 阶段推进后按钮状态**
- 当 `canExecuteMortality = false` 且 `canAdvanceMortality = true` 时：
  - 执行按钮应 disabled 或隐藏
  - 推进按钮应保持启用
- 当 `canAdvanceMortality = false` 时：推进按钮 disabled

**2.1.3 确认不重复强调**
- 「天命已执行」横幅：一次，非全宽
- 「执行天命」按钮：执行完成后不显示为同等活跃状态

**文件：** `MortalityStage.qml`（检查按钮状态绑定）+ `session_store.py`（检查 state 属性）

#### 2.2 侧边栏推进按钮降重（Phase-4 §11.2 / §15）

**依据：** Phase-4 §11.2 — 侧边栏操作按钮在视觉上仍过于强势，与主底栏按钮形成竞争。

**操作：**
- 侧边栏推进按钮保持 V4 的紧凑风格（已改 `#E8A030`），但不做进一步放大/加亮
- 确保 `Layout.preferredHeight` 不超过 24
- 文字 `font.pixelSize` 保持 ≤9
- 确认其 `visible` 绑定与 `canAdvanceMortality` 一致

**文件：** `ContextPanel.qml`

#### 2.3 验收标准（Phase-4 §9 Acceptance / §15）

```text
[ ] 执行按钮在阶段执行后不显示为活跃状态
[ ] 推进按钮在不可推进时 disabled
[ ] 侧边栏操作按钮不竞争主底栏按钮
[ ] 状态逻辑验证记录（如有发现）
```

---

### Pass 3 — 边框层次精简（P2）

参考：Phase-4 §6、§7、§8、§14、§15

按照 Phase-4 §14 的边框分类规则：

```text
KEEP: major region boundaries, sidebar boundary, navigation boundary
REDUCE: phase header card border, workflow strip border, instruction card border
REMOVE/FLATTEN: empty horizontal strip border, giant empty inner panel border
```

#### 3.1 Phase header 边框降重（Phase-4 §6）

**依据：** Phase-4 §6 — 当前 phase header 整行仍有较强卡片状边框。

**操作：**
- 检查 `MortalityStage.qml` 中 phase header Rectangle 的 `border.color` 和 `border.width`
- 如果存在 `border.color: theme.borderNormal` + `border.width: 1`，改为更弱的变体：
  - 方案 A：`border.color: Qt.rgba(0,0,0,0.08)`（极弱线条）
  - 方案 B：移除 border，保留浅背景作为标识

**文件：** `MortalityStage.qml`

#### 3.2 步骤条外边框降重（Phase-4 §7）

**依据：** Phase-4 §7 — 步骤条外边框仍过于突出。

**操作：**
- 步骤条容器的 `border.width` 从 `1` 改为 `0`（如果当前状态设为 0，保留）
- 仅通过内部分隔/步骤颜色表达步骤关系
- 高度保持 26，不额外加高

**文件：** `MortalityStage.qml`

#### 3.3 指令面板卡片感降低（Phase-4 §8）

**依据：** Phase-4 §8 — 指令区域仍被包围在全宽带边框卡片中。

**操作：**
- 指令面板外层 Rectangle 的 `border.color` → `"transparent"`（移除边框）
- `color` → 使用极浅暖色背景（`#FDF8F0` 或 `theme.bgSurface2` 已有）
- 或使用 1px 暖色顶部细线作为分隔 `Rectangle { height: 1; color: "#E8D5C4" }` 代替全卡片边框

**文件：** `MortalityStage.qml`

#### 3.4 验收标准（Phase-4 §14 / §15）

```text
[ ] Phase header 不读为独立仪表板卡片
[ ] 步骤条外边框已移除（仅内部分隔可见）
[ ] 指令面板不用全卡片边框（暖色分隔线或极浅背景）
[ ] 大三区域边界（sidebar / navigation）完整保留
[ ] 空容器无可见边框
```

---

### Pass 4 — 区域微对齐 — 顶部 HUD + 左侧 Rail（P3）

参考：Phase-4 §3、§4、§15

#### 4.1 顶部 HUD 间距平衡（Phase-4 §3.2）

**依据：** Phase-4 §3.2 — 标题/指标集群仍偏向左；指标间间距需均匀；右键图标基线需对齐。

**操作：**
- 检查 `TopStatusBar.qml` 中 title 与第一项指标之间的 spacing
- 检查各指标 RowLayout 之间的 spacing 是否均匀
- 使用一致的图标大小（emojis 在不同平台的渲染不同，用 Text 的 `font.pixelSize` 控制）
- 各项指标的 `baselineAlignment` 对齐

**具体调整建议：**

```qml
// 在 Title 与第一个指标之间添加弹性 Item
Text {
    text: "🏛 EAGLE OF ROME · SPQR"
    // ...
}
Item { Layout.minimumWidth: 12 }  // 固定间距

// 指标之间使用均匀 spacing
RowLayout {
    spacing: 8  // 统一
    Text { text: "💰 142 国库" }
    Text { text: "🛡 12 派系" }
    // ...
}

// 所有指标 font.pixelSize 统一
// 所有指标 baseline 对齐
```

**文件：** `TopStatusBar.qml`

#### 4.2 左侧 PhaseRail 微调（Phase-4 §4.2）

**依据：** Phase-4 §4.2 — 活跃阶段图标略大，垂直间距略松，部分非活跃图标圆圈处理不一致。

**操作：**
- 检查所有阶段按钮直径是否严格一致（活跃与非活跃使用同一尺寸，仅颜色不同）
- 活跃态圆形使用 `border.width: 2; border.color: "#E8A030"` 作为外圈
- 非活跃态使用 `border.width: 1; border.color: "#D4A574"`，填充 `"transparent"`
- 按钮之间的垂直间距统一；总高度不超过 rail width（60px）
- 按钮居中于 rail，左右间距对称

**文件：** `PhaseRail.qml`

#### 4.3 确认无 debug/utility 控件残留（Phase-4 §4.2 / §15）

**操作：**
- PhaseRail 底部确认无 `visible: true` 的 refresh/settings 按钮
- 检查代码中是否添加了 `visible: developmentMode` 的替代方案（如有，确认 `developmentMode` 默认为 `false`）

**文件：** `PhaseRail.qml`

#### 4.4 验收标准（Phase-4 §3 Acceptance / §4.2 Acceptance / §15）

```text
[ ] HUD 读为一条平衡的状态条，而非左聚集群 + 空中间
[ ] 所有指标使用一致图标大小、baseline 对齐、均匀 spacing
[ ] PhaseRail 所有按钮直径一致
[ ] 活跃态圆形 + 金边，非活跃态圆 + 暖边
[ ] 垂直节奏紧凑
[ ] 无 debug/utility 控件可见
```

---

### Pass 5 — 区域微对齐 — 侧边栏 + 日志 + 底部导航（P3）

参考：Phase-4 §11、§12、§13、§15

#### 5.1 侧边栏间距精调（Phase-4 §11.2 / §11.3）

**依据：** Phase-4 §11.2 — 描述过于紧凑略挤；§11.3 — label/value 基线对齐、分隔线间距一致、行高一致。

**操作：**
- 「当前阶段」摘要区域的 `Layout.preferredHeight` 从 `implicitHeight + 16` → 检查实际占用
- 阶段摘要文字的 `Layout.fillWidth: true` 确认，`wrapMode: Text.Wrap` 启用
- 各信息行（进度/玩家）RowLayout 中的 label 和 value 使用 `Layout.alignment: Qt.AlignVCenter` + `font.pixelSize` 统一
- 分隔线 Rectangle 的左右边距与段首对齐（`Layout.leftMargin: 8; Layout.rightMargin: 8`）

**文件：** `ContextPanel.qml`

#### 5.2 事件日志底部 artifact 修复（Phase-4 §12）

**依据：** Phase-4 §12 — 日志区域下方有 stray 文字/状态内容可见。

**操作：**
- 检查 `ContextPanel.qml` 中日志区域结束处和 BottomQueryBar 上方之间是否有溢出文字
- 检查 EventLog 组件的底部 `anchors.bottom` 锚定和 `clip: true`
- 移除 `/` 下半截或任何残留的状态文字片断
- 如果日志区域必须填充剩余高度，确认空部分使用 `color: "transparent"`（不显示为暗底终端风格）

**具体操作：**
```qml
// 在日志 ListView/日志容器处：
clip: true
// 确保日志容器底部没有 anchor 到多余内容
```

**文件：** `ContextPanel.qml`（日志相关区域）

#### 5.3 底部导航活跃色降饱和（Phase-4 §13）

**依据：** Phase-4 §13 — 活跃「游戏状态」按钮仍过亮过饱和；活跃边框比 Design 强。

**操作：**
- `BottomQueryBar.qml` 中活跃按钮颜色：从 `#E8A030` → 更柔和的 `#C8942E`（减弱约 15% 亮度）
- 活跃按钮边框宽度保持 `1`，颜色使用 `#C8942E`
- 非活跃按钮文字色使用 `#C0A88E`（浅暖棕，保持可读）
- 按钮区域总高度保持 32

**文件：** `BottomQueryBar.qml`

#### 5.4 验收标准（Phase-4 §11.3 / §12 / §13 / §15）

```text
[ ] 侧边栏各段间距紧凑且一致
[ ] 信息行 label/value 基线对齐
[ ] 分隔线边距与段首对齐
[ ] 事件日志无 clipped text / stray status fragment / debug artefact
[ ] 日志空区域不显示为暗底终端风格
[ ] 底部导航活跃色为柔和暗金（非亮黄），不比屏幕其他区域更亮
[ ] 底部导航保持 32px 高度不变
```

---

## 六、修改文件清单汇总（Phase-4 增量）

| Pass | 文件 | 主要操作 | 风险 |
|------|------|---------|------|
| P1 | `MortalityStage.qml` | 空容器 flatten（transparent / visible=false / height=0） | 🟢 |
| P2 | `MortalityStage.qml` + `ContextPanel.qml` + `session_store.py` | 状态逻辑审查；侧边栏按钮降重 | 🟡 |
| P3 | `MortalityStage.qml` | Phase header / 步骤条 / 指令面板边框降重 | 🟢 |
| P4 | `TopStatusBar.qml` + `PhaseRail.qml` | HUD 间距平衡；Rail 大小/节奏标准化 | 🟢 |
| P5 | `ContextPanel.qml` + `BottomQueryBar.qml` | 侧边栏间距/日志 artifact/底部 nav 活跃色 | 🟢 |

**V4+V5 完整修改文件清单（所有版本累计）：**

| 文件 | V4 已有操作 | V5 Phase-4 增量操作 |
|------|-----------|-------------------|
| `GameShell.qml` | 移除公告块 / ContextPanel width / 间距 | 不变 |
| `TopStatusBar.qml` | SPQR / 指标精简 / 日期 RHS / 移徽标 | HUD 间距平衡 |
| `PhaseRail.qml` | 隐藏 dev / 活跃态圆形 | 图标大小/节奏标准化 |
| `ContextPanel.qml` | 完整 IA 重建 + 精修 | 推进按钮降重 / 间距 / 日志 artifact |
| `MortalityStage.qml` | 紧凑 / 指令 / 去嵌套 / 按钮 + 精修 | 空容器 flatten / 状态审查 / 边框降重 |
| `BottomQueryBar.qml` | 活跃色 #E8A030 | 活跃色降饱和 #C8942E |
| `session_store.py` | mortalityEvent property（V2 保留） | 状态逻辑审查（只读/不修改逻辑） |

## 七、禁止事项（Phase-4 补充）

除 V4 已有的禁止事项外，补充：

1. **不得改变游戏阶段状态机** — 不修改 `canExecuteMortality` / `canAdvanceMortality` 的业务逻辑
2. **不得添加假数据填充空日志区域** — 只裁剪/锚定
3. **不得为截图匹配而修改真实数据值** — 不伪造国库值、派系数、年份等
4. **不得改变五区宏观架构** — header / left rail / central / right sidebar / bottom nav 不变
5. **不得增加新建组件或 UI 概念** — 只减少/精调/扁平化

## 八、实施顺序要求

按以下顺序实施，每 Pass 完成后验证：

```text
Pass 1（容器扁平化）
  → 验证：中央工作区无可见空边框
  → 验证：所有阶段页面布局未受影响

Pass 2（状态/操作权威）
  → 验证：天命阶段执行→推进全链路
  → 验证：按钮/横幅不同时活跃

Pass 3（边框层次）
  → 验证：Phase header / 步骤条 / 指令面板不再卡片化
  → 验证：三项大区域边界完整

Pass 4（HUD + Rail）
  → 验证：TopStatusBar 指标均匀分布
  → 验证：PhaseRail 按钮直径一致、无 dev 控件

Pass 5（Sidebar + 日志 + Bottom Nav）
  → 验证：日志无 artifact
  → 验证：BottomQueryBar 活跃色暗金
  → 验证：全量回归 773/773 通过
```

## 九、测试要求

### 9.1 测试策略

- **Pass 1~5 渐进测试：** 每个 Pass 完成后运行定向 GUI + Mortality API 测试
- **验收前全量回归：** 最终 Pass 5 完成后执行全量 pytest

### 9.2 执行命令

```bash
# 定向测试（每 Pass 完成后）
cd /mnt/c/Users/Kerl/PycharmProjects/Eagle\ of\ Rome
python -m pytest src/tests/test_gui/ src/tests/test_api/test_mortality_api.py -v

# 全量回归（最终验收前）
python -m pytest src/tests/ -v
```

### 9.3 验证逻辑

Phase-4 的文件修改主要影响 QML 布局和颜色。`test_qml_startup.py` 的 `test_main_qml_exposes_core_gui_regions()` 中组件存在性不受影响（无组件被删除，只有属性/可见性变更）。

```bash
# 确认以下测试继续通过
- test_opc_shell_exposes_twelve_bottom_query_buttons  — 操作按钮列表，颜色改动不影响
- test_opc_shell_boundary_and_i18n_scans                — 硬编码中文引用不受影响
- 各项 Core/API 测试                                   — QML 布局变更不影响
```

## 十、颜色系统参考（Phase-4 §14 / §15）

| Token | 色值 | 用途 |
|-------|------|------|
| 罗马深红 | `#8B2500` | 主按钮、标题、强调、header 底 |
| 金色 | `#FFD700` | 文字高亮、完成态 |
| 柔和金 | `#E8A030` | 侧边栏推进按钮、步骤条完成（V4 已应用） |
| 暗金降饱和 | `#C8942E` | **底部导航活跃态**（Phase-4 新增） |
| 羊皮纸底 | `#F5F0E8` / `theme.bgApp` | 全局背景 |
| 浅羊皮纸 | `#FAF5EE` / `theme.bgSurface1` | 面板 |
| 奶油白 | `#FFFDF5` / `theme.bgSurface2` | 数据行/卡片 |
| 暖边框 | `#D4A574` / `theme.borderNormal` | 面板边框 |
| 极弱线条 | `Qt.rgba(0,0,0,0.08)` | **Phase header 降重后**（Phase-4 新增） |
| 暖分隔线 | `#E8D5C4` | **指令面板卡替代**（Phase-4 新增） |
| 主文字 | `#3A3530` / `theme.textPrimary` | 深棕 |
| 次文字 | `#8B7355` / `theme.textSecondary` | 棕灰 |
| 非活跃导航文字 | `#C0A88E` | **底部导航非活跃态**（Phase-4 新增） |

## 十一、Phase-4 验收标准矩阵

基于 Phase-4 §18（所有新验收项）：

```text
[ ] 中央工作区读为一张开放 parchment 表面（P1）
[ ] 窄空边框带已移除或视觉压平（P1）
[ ] 空大内面板不再读为空卡片（P1）
[ ] Phase header 集成而非卡片状（P3）
[ ] 步骤条紧凑且从属（P3）
[ ] 指令区域盒子感降低（P3）
[ ] 只有一项权威主操作在视觉上占主导（P2）
[ ] 天命已执行 与 执行天命 不产生矛盾强调（P2）
[ ] 右侧边栏紧凑，不重建（P5）
[ ] 事件日志无 clipped / stray 底部 artifact（P5）
[ ] 底部活跃导航用暗金，非亮黄（P5）
[ ] 左侧 rail 窄且一致（P4）
[ ] 无 debug/utility 控件在正常玩家模式可见（P4）
[ ] 不因截图匹配而修改游戏逻辑或真实数据（全 Pass）
[ ] V4 已实现的全部验收项保持通过
```

## 十二、DA 交付格式

开发验收报告归档到：

```text
docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03C 天命阶段GUI对齐 开发验收报告 - DA.md
```

报告必须包含：

```text
Decision by DA: READY_FOR_SA_REVIEW / BLOCKED / RETURN_FOR_SCOPE_CONFIRMATION

基线: 2c2de94e0d8931325d737f5957c6d18569275557

V4 已实现内容:
  - Phase-2 6 Pass ✅（结构删除 / 中央工作区 / 右边栏 IA / 标题栏 / Token / 密度）
  - Phase-3 5 Pass ✅（结构清理 / 中央精修 / 右边栏精修 / 标题底栏 / Token 最终）

V5 Phase-4 增量:
  Pass 1 — 容器扁平化 → 状态
  Pass 2 — 状态/操作权威 → 状态
  Pass 3 — 边框层次精简 → 状态
  Pass 4 — HUD + Rail 微对齐 → 状态
  Pass 5 — Sidebar + 日志 + Bottom Nav → 状态

Phase-4 合规性:
  - §5 中央工作区简化 → ...
  - §6 Phase header 集成 → ...
  - §7 步骤条降重 → ...
  - §8 指令降重 → ...
  - §9 天命已执行逻辑 → ...
  - §10 主操作按钮 → ...
  - §11 侧边栏精调 → ...
  - §12 事件日志 → ...
  - §13 底部导航 → ...
  - §14 边框精简 → ...
  - §15 增删改矩阵 → 逐项通过

测试结果:
  定向: X tests passed
  全量: XXXX passed, X failed

已知风险:
  需要 SA/项目负责人确认的问题:
```

⚠️ **DA 不得提交 Git。** Git 归档由 SA 在项目负责人确认验收后执行。


---

# ==================== Phase-5 叠盖层 ====================

> 以下内容叠盖在 V5（Phase-2 6 Pass + Phase-3 5 Pass + Phase-4 5 Pass）之上。
> V5 已实现，Phase-5 新增 4 Pass 精修。

## Phase-5 任务定位

参考：`EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-5.md`

> Actual 5 has solved the biggest empty-panel problem.
> The next objective is: **clearer state semantics, less duplicate instruction content, better central content placement, and cleanup of remaining visual artefacts.**
> Do not reintroduce bordered panels. Solve content placement, state clarity, and visual rhythm.

### V5 → Phase-5 差距概要

| 模块 | V5 状态 | Phase-5 要求 |
|------|---------|-------------|
| 中央工作区 | 扁平化完成，无空面板 | 内容仍漂浮/滞留；需修复节奏和占位 |
| 顶部指令面板 | 暖色分隔线 + 双行 | 与中央空状态块内容重复 |
| 中央空状态块 | 提示+事件类型（浮动过低） | 仅保留一个权威指令；中央块上移或精简 |
| 天命已执行 vs 执行天命 | 逻辑已验证正确 | 仍可能语义冲突；需再检查状态一致性 |
| 侧边栏推进按钮 | 已降重（暖边框） | 仍略显突出，需进一步降重 |
| 事件日志 | clip: true 确认 | 空白区域过大；可能仍有 artifact |
| 底部导航活跃色 | 已改 #C8942E | 仍需确认不成为屏幕最亮元素 |
| PhaseRail | 高度 44 + 活跃 #E8A030 | 中下部有小点/工具 artifact 残留 |

## Phase-5 4 Pass 实现序列

根据 Phase-5 §16 定义的优先级：P0（状态与指令权威）→ P1（中央工作区节奏）→ P2（侧边栏与 artifact 清理）→ P3（微对齐）。

---

### Phase-5 Pass 1 — 状态与指令权威（P0）

参考：Phase-5 §4、§5、§6、§7、§8

#### 1.1 决策：选择哪个指令块为权威

**依据：** Phase-5 §4.3 — 当前存在两个重复的指令块：顶部指令面板（暖色分隔线下）和中央空状态块（页面居中）。

**选择方案 A（推荐）：保持顶部指令面板为权威源，移除中央重复文本**

理由：
- Phase-2/3/4 已投资顶部指令面板的设计
- 顶部指令面板位于工作流上下文中（步骤条下方），逻辑位置正确
- 中央区域应保持开放的 parchment 感觉，而非放置另一块文本

**操作：**

1.1.1 将中央空状态块从双行指令精简为仅保留图标和极简提示：

```qml
// 中央空状态（执行前）
ColumnLayout {
    anchors.centerIn: parent
    anchors.verticalCenterOffset: -20  // 上移，略高于数学中心
    spacing: 6
    visible: !sessionStore.mortalityEvent || !sessionStore.mortalityEvent.name

    Text {
        Layout.alignment: Qt.AlignHCenter
        text: "🎴"
        font.pixelSize: 24  // 缩小
    }
    // 移除重复指令文本行
    // 移除事件类型行
    // 可保留一行很淡的状态提示或完全不保留
}
```

**文件：** `MortalityStage.qml`

#### 1.2 审查「天命已执行」与「执行天命」状态关系（Phase-5 §7）

**依据：** Phase-5 §7 — 当 `canExecuteMortality = false` 且 `canAdvanceMortality = true` 时，「天命已执行」和「执行天命」按钮同时可见存在语义冲突。

**V5 状态审查回顾：**
- 执行前：`canExecuteMortality = true`, `canAdvanceMortality = false` → 执行按钮可见有效，推进按钮隐藏
- 执行后：`canExecuteMortality = false`, `canAdvanceMortality = true` → 执行按钮隐藏/禁用，推进按钮可见

**Phase-5 §7 要求进一步验证：**

检查 `session_store.py` 中 `canExecuteMortality` 和 `doExecuteMortality()` 的实际切换时机：

```python
# 在 session_store.py 中确认以下行为：
# 1. doExecuteMortality() 执行后 canExecuteMortality → false
# 2. canAdvanceMortality → true 在结果可用时发生
# 3. 按钮可见性绑定正确（visible / enabled）
```

如果以上逻辑正确，则没有语义冲突。**只记录，不改代码。**

**文件：** `session_store.py`（只读审查）

#### 1.3 如果状态冲突存在：标签语义调整（Phase-5 §7 E）

如果审查发现执行按钮在 `canExecuteMortality = false` 时仍可见为「✅ 已完成」状态，而同时「天命已执行」横幅也可见，则两者视觉上存在二次确认的感觉。

**可选修复（如果需要）：**

- 执行按钮标签从 `canExecuteMortality ? "⚡ 执行天命" : "✅ 已完成"` 改为：
  - 执行后不可见（`visible: !sessionStore.canAdvanceMortality` 已实现）
  - 如保留可见，仅用极淡的灰色文字标示过往状态

**文件：** `MortalityStage.qml`（仅在审查有发现时修改）

#### 1.4 验收标准（Phase-5 §4 Acceptance / §5 / §6 / §7 / §8）

```text
[ ] 顶部指令面板和中央空状态块不重复指令文本
[ ] 指令信息只有一个权威来源
[ ] 中央空状态如保留则只含图标或极淡标
[ ] 中央空状态上移，不精确居中
[ ] 「天命已执行」与「执行天命」状态不产生语义冲突
[ ] 玩家在任何时刻清楚：操作是否可用 / 阶段步骤是否完成 / 下一步操作
```

---

### Phase-5 Pass 2 — 中央工作区节奏（P1）

参考：Phase-5 §4、§6

#### 2.1 中央工作区空白节奏感（Phase-5 §4.2 / §6）

**依据：** Phase-5 §4.2 — 移除空面板后，中央区域变得「过于空白且无结构」，内容看起来「悬浮」。V5 已无嵌套边框，但中间内容区域看起来不完整。

**操作：**

- 保持中央 Rectangle 为透明/无边框
- 确认 `Layout.fillHeight: true` 正确分配垂直空间
- 内容（图标/初始提示）使用 `anchors.verticalCenterOffset: -20` 上移，不过度靠下
- 事件结果内容通过 `ColumnLayout` 自然排列，不额外加边框

**文件：** `MortalityStage.qml`

#### 2.2 保持开放羊皮纸表面（Phase-5 §3 / §14）

**不得重新引入：**
- 大的嵌套边框面板
- 内容片的卡片背景或边框
- 围绕中央区域的额外容器

**文件：** `MortalityStage.qml`

#### 2.3 验收标准（Phase-5 §4 Acceptance / §6 / §14）

```text
[ ] 中央工作区仍读为开放 parchment 表面
[ ] 中央内容不再在过度空白空间中感觉漂泊
[ ] 未重新引入大型有边框的空面板
[ ] 未引入新的 UI 概念
[ ] 执行前和事件结果后视觉效果均合理
```

---

### Phase-5 Pass 3 — 侧边栏与 Artifact 清理（P2）

参考：Phase-5 §9、§10

#### 3.1 侧边栏推进按钮进一步降重（Phase-5 §9.2）

**依据：** Phase-5 §9.2 — 侧边栏操作按钮仍然「visually prominent」，与中央主操作形成竞争。

**操作：**
- 确认 V5 已实现的降重（`theme.bgSurface2` + `theme.borderNormal` + `#8B2500` 文字）
- 如需进一步降重：
  - 移除按钮背景色：`color: "transparent"` + `border.width: 0`
  - 改为纯文本链接风格：`color: theme.textSecondary` + `underline: false`
  - 仅在 `canAdvanceMortality = true` 时显示
- 确保 `Layout.preferredHeight` 保持 22

**文件：** `ContextPanel.qml`

#### 3.2 事件日志底部 artifact 修复（Phase-5 §10）

**依据：** Phase-5 §10 — 日志底部仍可能有「clipped/stray text visible at lower edge」。

**操作：**
- 确认 ScrollView/ListView 使用 `clip: true`
- 检查日志区域底部和 FeedbackPanel 之间的间距
- 移除日志区域下方的任何残留文字组件
- 确认日志列表的 `anchors.fill` 正确绑定

**文件：** `ContextPanel.qml`

#### 3.3 验收标准（Phase-5 §9.2 Acceptance / §10）

```text
[ ] 侧边栏操作按钮视觉上从属于中央主操作
[ ] 事件日志无 clipped text / stray lower-edge content
[ ] 日志空区域中性且不显示为暗底终端风格
[ ] 日志底部无 clutter / stray 片段
```

---

### Phase-5 Pass 4 — 微对齐 (P3)

参考：Phase-5 §11、§12、§13、§14

#### 4.1 顶部 HUD 间距微调（Phase-5 §11）

**依据：** Phase-5 §11 — metrics 仍略左聚集；间距可更均匀。

**操作（检查确认）：**
- V5 已添加 `Item { Layout.minimumWidth: 12 }` 在标题与首分隔线之间
- 确认标题 `Layout.preferredWidth: 200` 合适
- 确认各指标 spacing: 6 一致
- 确认图标 font.pixelSize: 12 一致
- **如果 V5 改动已充分，只需验证，无需改动代码**

**文件：** `TopStatusBar.qml`（只读验证）

#### 4.2 左侧 PhaseRail 图标节奏 + artifact 清理（Phase-5 §12）

**依据：** Phase-5 §12 — 中下部有小点/工具 artifact 残留；垂直间距略松。

**操作：**
- 检查 PhaseRail 底部是否有非阶段导航按钮存在
- 确认 `Layout.preferredHeight: 44` 已应用（V5 已改）
- 检查 `spacing: 2` 和顶部 `Layout.preferredHeight: 4` 是否合理
- 如果 artifact 是 Repeater 之外的额外组件，移除或隐藏

**文件：** `PhaseRail.qml`

#### 4.3 底部导航活跃色确认（Phase-5 §13）

**依据：** Phase-5 §13 — 活跃色仍过亮。

**操作（检查确认）：**
- V5 已将活跃色从 `#E8A030` 改为 `#C8942E`
- 确认背景 `#55C8942E`、边框 `#C8942E`、文字 `#C8942E`
- **如果已改，只需验证，无需改动代码**

**文件：** `BottomQueryBar.qml`（只读验证）

#### 4.4 减少剩余卡片风格边框（Phase-5 §14）

**依据：** Phase-5 §14 — 减少 phase header / 步骤条 / 指令面板的边框。

**操作（检查确认）：**
- V5 Phase-4 P3 已完成以下改动：
  - Phase header 边框：`Qt.rgba(0,0,0,0.08)` ✅
  - 步骤条外边框：`border.width: 0` ✅
  - 指令面板：暖色分隔线代替全卡片 ✅
- **如已改，只需验证，无需改动代码**

**文件：** `MortalityStage.qml`（只读验证）

#### 4.5 验收标准（Phase-5 §11 / §12 / §13 / §14）

```text
[ ] HUD metrics 均匀分布（V5 确认）
[ ] Left rail 仅包含已批准的玩家阶段导航图标（无 debug/utility 控件）
[ ] 底部导航活跃色为柔和暗金（V5 确认）
[ ] 活跃导航不成为屏幕最亮元素（V5 确认）
[ ] 没有重新引入大的有边框面板
```

---

## 六（Phase-5）、修改文件清单汇总（Phase-5 增量）

| Pass | 文件 | 主要操作 | 风险 |
|------|------|---------|------|
| P1 | `MortalityStage.qml` + `session_store.py` | 中央空状态精简/上移；状态逻辑审查 | 🟡 |
| P2 | `MortalityStage.qml` | 中央节奏确认，不引入新边框 | 🟢 |
| P3 | `ContextPanel.qml` | 按钮进一步降重（如需要）；日志 artifact | 🟢 |
| P4 | `TopStatusBar.qml` / `PhaseRail.qml` / `BottomQueryBar.qml` | 微对齐验证（只读/微调） | 🟢 |

**V5+V6 完整修改文件清单（所有版本累计）：**

| 文件 | V4+V5 已有操作 | V6 Phase-5 增量操作 |
|------|-------------|-------------------|
| `GameShell.qml` | 移除公告块 / ContextPanel width / 间距 | 不变 |
| `TopStatusBar.qml` | SPQR / 指标精简 / 日期 RHS / 间距平衡 | 验证（只读） |
| `PhaseRail.qml` | 隐藏 dev / 活跃态圆形 / 高度/颜色 | artifact 清理 |
| `ContextPanel.qml` | IA 重建 + 精修 + 按钮降重 + 间距 | 按钮进一步降重；日志 artifact |
| `MortalityStage.qml` | 紧凑 / 指令 / 去嵌套 / 精修 / 扁平 / 边框 | 中央状态精简上移 |
| `BottomQueryBar.qml` | 活跃色 #E8A030 → #C8942E | 验证（只读） |
| `session_store.py` | mortalityEvent property（V2） | 状态逻辑审查（只读） |

## 七（Phase-5）、禁止事项（Phase-5 补充）

除 V4/V5 已有的禁止事项外，补充：

1. **不得重新引入大的嵌套边框面板** — Phase-5 整个主题是保持开放表面
2. **不得添加假事件日志填充空空间** — 只清理 artifact
3. **不得改变游戏逻辑仅用于视觉对齐** — 包括 `canExecuteMortality` / `canAdvanceMortality`
4. **不得创建第二个指令权威** — 只有一个指令源
5. **不得增加七阶段导航外的额外 rail 图标**
6. **不得修改真实游戏数据值以匹配截图**

## 八（Phase-5）、实施顺序要求

```text
Pass 1（状态/指令权威）
  → 验证：中央空状态不重复指令
  → 验证：天命已执行 vs 执行天命语义清晰

Pass 2（中央工作区节奏）
  → 验证：中央内容不感觉漂浮
  → 验证：未引入新边框

Pass 3（侧边栏 + Artifact）
  → 验证：侧边栏按钮视觉从属
  → 验证：日志底部无 artifact

Pass 4（微对齐）
  → 验证：V5 改动保持有效
  → 验证：全量回归 773/773 通过
```

## 九（Phase-5）、测试要求

同 V5。每 Pass 后运行定向测试，最终全量回归。

## 十（Phase-5）、颜色系统参考

与 V5 一致。无新增颜色 Token。

## 十一（Phase-5）、验收标准矩阵

基于 Phase-5 §18：

```text
[ ] 巨大的内部空面板仍保持移除
[ ] 中央工作区仍读为开放 parchment
[ ] 中央内容不再在过度空白中感觉漂泊
[ ] 执行天命只有一个权威指令消息
[ ] 天命已执行 与 执行天命 不产生语义冲突
[ ] 主操作/状态关系视觉清晰
[ ] 顶部指令面板与中央空状态不重复
[ ] 右侧边栏紧凑，不重建
[ ] 侧边栏操作视觉从属
[ ] 事件日志无 clipped / stray 底部文字
[ ] 底部导航活跃色为柔和暗金
[ ] 左侧 rail 仅包含已批准的玩家导航图标
[ ] 没有重新引入大的有边框面板
[ ] 不因截图匹配而修改真实游戏数据
[ ] V5 已实现的全部验收项保持通过
```

## 十二（Phase-5）、DA 交付格式

与 V5 同。验收报告追加 Phase-5 增量到对应列表。
