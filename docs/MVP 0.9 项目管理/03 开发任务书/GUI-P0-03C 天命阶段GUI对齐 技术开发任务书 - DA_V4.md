# GUI-P0-03C 天命阶段GUI对齐 技术开发任务书 — DA（V4 — V3 + Phase-3 精修叠盖版）

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
| 视觉分析参考 | 综合 Phase-1 + Phase-2 视觉收敛分析（Phase-2 §1~§26 完整） |

## 二、任务目标

将天命阶段整体 GUI 与 V3.23 原型及《EOR GUI设计文档 V2.0》全面对齐，**基于 Phase-2 视觉收敛规范（26 节）执行完整的 6 Pass 收敛**。

**战略原则（来自 Phase-1 §1 / Phase-2 §26）：**
> 目标不是复制每个像素。先再现设计稿的**布局层次、区域比例、信息放置、组件密度和色彩语义**。
> 保留可用的游戏逻辑。先改呈现和UI构成。
> 不要因为组件已经实现就保留它。不要引入设计稿中不存在的新UI概念。
> 当前的五区宏观架构（header + left rail + central workspace + right sidebar + bottom nav）是正确的。**不要重头 redesign。**

## 三、背景说明

| 项目 | 内容 |
|------|------|
| 当前产品目录 | 主壳骨架（P0-03A）+ GuiApiAdapter（P0-03B）已完成 |
| Senate 对齐 | GUI-P0-03F（原 TASK-001）已改 6 QML 等待验收 |
| 当前状态 | V2 已修改 MortalityStage.qml / ContextPanel.qml / session_store.py / mortality_service.py 四个文件（颜色修正 + 单事件 + 死亡详情），**但仍存在 7 项重大结构差异** |
| 视觉分析来源 | Phase-2 规范，26 节完整对比，定义了 6 Pass 实现顺序 |
| 本轮目标 | 消除 Phase-2 列出的全部结构、布局和风格偏差 |

## 四、依据文档

- `E:\OpenClaw\Projects\EOR\workspace\vision analysis\EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-2.md`（核心依据，§1~§26）
- `E:\OpenClaw\Projects\EOR\workspace\vision analysis\EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-1.md`（Phase-1 参考）
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI设计文档.md`（§3.1 天命阶段）
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_GUI_Prototype_v3.23.html`
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/EOR_UI_API_Mapping.md`
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/GUI_Code_Alignment_Audit.md`
- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03C 技术边界审查报告.md`

## 五、Phase-2 6 Pass 实现序列

> 严格遵循 Phase-2 §24 定义的实现顺序。不得重新排列或跳过。

```text
Pass 1 — 结构删除（P0）
Pass 2 — 中央工作区对齐（P1）
Pass 3 — 右侧边栏重建（P1）
Pass 4 — 顶部标题栏对齐（P2）
Pass 5 — 视觉 Token 对齐（P3）
Pass 6 — 最终密度调整（P4）
```

---

## Pass 1 — 结构删除（P0）

### 1.1 移除外部阶段公告块（Phase-2 §3 / §23）

**依据：** Phase-2 §3 — Design 原型中不存在外部阶段公告块。该块位于全局 header 与中央工作区之间，显示「阶段公告 / 天命 / 抽取天命事件……」，是重复的阶段身份信息。

**文件：** `src/ui/gui/qml/shell/GameShell.qml`

**操作：** 删除 `stageAnnouncement` Rectangle（约第 42~96 行，含 ColumnLayout、RowLayout、Text 等子组件）。

**后果：** 此前该区域的 `height: 96` 回收后，中央工作区（centerPanel）自然占据垂直空间。`anchors.top: topBar.bottom` 保持不变。

**不做：** 不修改 centerPanel 内其他布局；不修改任何子阶段 Stage 的 `anchors`。

### 1.2 移除右上角阶段徽标（Phase-2 §4.2 / §23）

**依据：** Phase-2 §4.2 — 右上角的「天命阶段」徽标（TopStatusBar 末端 Rectangle）在 Design 中不存在。

**文件：** `src/ui/gui/qml/shell/TopStatusBar.qml`

**操作：** 删除最末的 Rectangle（`id: phaseLabel` 的父容器，含 `"当前阶段名+阶段"` 文字）。

### 1.3 移除左侧 rail 开发工具按钮（Phase-2 §5 / §23）

**依据：** Phase-2 §5 — 左侧 PhaseRail 底部的 `refresh` 和 `settings` 按钮是开发控制工具，Design 原型中不存在。

**操作：** 在 PhaseRail.qml 中移除或 `visible: developmentMode`（建议先注释/隐藏）。明确为本次迭代做，不引入developmentMode机制——直接隐藏。

**文件：** `src/ui/gui/qml/shell/PhaseRail.qml`

### 1.4 移除 2×2 资源卡片网格（Phase-2 §12 / §14 / §23）

**依据：** Phase-2 §12 — 右侧 ContextPanel 顶部的 2×2 资源卡片网格在 Design 中不存在。Design 要求紧凑的行式信息展示，而非大卡片。

**文件：** `src/ui/gui/qml/shell/ContextPanel.qml`

**操作：** 删除 `StatusTile` 2×2 GridLayout 及上方的 `GuiText.factionResources` 标题。**保留**阶段摘要/派系权限/当前阶段标签等后续区域（Pass 3 会重组）。

### 1.5 移除底部操作栏中的开发控件（Phase-2 §18 / §23）

**依据：** Phase-2 §18 — 「刷新权威状态」等基础设施控制不属于玩家 UI。

**文件：** `src/ui/gui/qml/shell/ContextPanel.qml`

**操作：** 删除底部 RowLayout 中的 `AppButton(text: GuiText.refreshAuthoritativeState)`. 保留 `AppButton(text: GuiText.completeCurrentPlayer)` 但随整个 flow control 区域一起在 Pass 3 重构。

---

## Pass 2 — 中央工作区对齐（P1）

### 2.1 阶段 header 紧凑化（Phase-2 §6 / §23）

**减少** 阶段 header 的高度：
- `Rectangle` 的 `Layout.preferredHeight` 从 `60` → `44`
- 阶段编号 `1/7` 徽标：`width: 36; height: 36; radius: 18` → `width: 28; height: 28; radius: 14`
- 标题 font.pixelSize: `16` → `14`
- 描述 font.pixelSize: `10` → `9`
- 状态「就绪」/「已完成」标签：保持

**操作文件：** `src/ui/gui/qml/stages/MortalityStage.qml`

### 2.2 步骤条左对齐 + 紧凑化（Phase-2 §7 / §23）

**布局变更：**
- 当前：`anchors.centerIn: parent` → **改为 `anchors.left: parent.left; anchors.leftMargin: 10`**
- 当前 `Layout.preferredHeight: 32` → `26`
- 步骤圆圈：`width: 18; height: 18` → `14; radius: 7`
- 文字：`font.pixelSize: 11` → `10`

**步骤条颜色（维持 V2 修正）：**
- 步骤② 已完成：金色 `#FFD700`（非绿色）
- 步骤② 未完成：浅色 `#E8D5C4`
- 箭头文字：`"→"` 保持

### 2.3 恢复指令面板（Phase-2 §8 / §23）

**依据：** Phase-2 §8 — Design 中步骤条下方有一条指令面板，显示「📕 点击下方[执行天命]按钮，触发一个随机事件。事件类型：猝死」。当前代码为空栏。

**操作：** 在步骤条 Rectangle 下方新增紧凑 Rectangle，结构如下：

```qml
// 指令面板（步骤条与中央内容区之间）
Rectangle {
    Layout.fillWidth: true
    Layout.preferredHeight: 24
    color: theme.bgSurface2
    border.color: theme.borderNormal
    radius: theme.radius

    Text {
        anchors.left: parent.left; anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: "📕 点击下方「执行天命」按钮，触发一个随机事件。"
        color: theme.textSecondary
        font.pixelSize: 9
    }
}
```

### 2.4 移除巨型嵌套空面板边界（Phase-2 §9 / §23）

**依据：** Phase-2 §9 — 中央内容区当前是一个大边框矩形（`theme.bgSurface1` + `border`），内部再嵌套事件展示区，造成过度嵌套。

**操作：** 移除中央事件展示区 Rectangle 的外层 `border.color` 和独立的矩形背景。让事件展示区的两个状态（初始提示 / 结果卡片）直接使用相近的 parchment 背景。

**具体方案（二选一，推荐 A）：**

**方案 A — 轻量（推荐）：** 保留外层 Rectangle 但移除 border，只保留 `color: theme.bgSurface1`。内部两个状态（初始提示 / 事件结果）直接填充。

**方案 B — 无外层：** 去掉外层 Rectangle，让 ColumnLayout 直接包含两个状态组件 + `fillHeight: true`。**风险：** 初始提示可能垂直居中异常。

**采纳方案 A**，修改如下特性：
```qml
// 移除：
border.color: theme.borderNormal
border.width: 1

// 保留：
color: theme.bgSurface1
```

### 2.5 主操作按钮缩小（Phase-2 §10 / §23）

**依据：** Phase-2 §10 — 当前执行按钮是 Design 的 2~3 倍宽，亮黄边框过于醒目。

**操作：** 缩小底部操作按钮区：
- 按钮容器 `Layout.preferredHeight: 64` → `44`
- 按钮 `width: 180` → `120~140`
- 按钮 `height: 44` → `32`
- 按钮文字 `font.pixelSize: 13` → `11`
- 按钮边框 `border.width: 2` → `1`
- 移除亮黄色边框，仅保留细金色 border

**注意**：按钮颜色/文字/切换逻辑（执行→推进）保持 V2 版本不变。

---

## Pass 3 — 右侧边栏重建（P1）

这是最大重构项。Phase-2 §11~§18 完整描述了目标 IA。

### 3.1 目标信息架构（Phase-2 §11.1 / §14 / §15 / §16）

替换当前 `ContextPanel.qml` 的 Top section 为：

```text
🎯 当前阶段
⚡ 一键执行天命，查看众神降下的事件。    ← 阶段摘要（紧凑一行）

⚡ 操作
[推进到下一阶段]                        ← 紫色/金色矩形按钮

📋 进度
流程                      2/2            ← compact rows
状态                    可操作

👤 玩家
派系              Optimates               ← compact rows
人物                   5人

📣 事件日志           清空                  ← compact list（保留日志功能）
timestamp + event
timestamp + event
```

### 3.2 详细实现

#### 3.2.1 当前阶段/摘要区域（取代之前的资源卡片 + 选中阶段 + 派系权限块）

```qml
// 当前阶段摘要
Rectangle {
    color: "transparent"
    Layout.preferredHeight: currentPhaseColumn.implicitHeight + 16
    ColumnLayout {
        id: currentPhaseColumn
        anchors.left: parent.left; anchors.right: parent.right
        anchors.margins: 8; anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        // 当前阶段标题
        RowLayout {
            spacing: 4
            Text {
                text: "🎯 当前阶段"
                color: "#8B2500"
                font.pixelSize: 10; font.bold: true
            }
        }

        // 阶段摘要
        Text {
            text: "⚡ 一键执行天命，查看众神降下的事件。"
            color: theme.textSecondary
            font.pixelSize: 9
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
}
```

#### 3.2.2 操作按钮（取代底部 flow control 中凌乱的按钮组）

```qml
// 操作
Rectangle {
    Layout.fillWidth: true
    Layout.preferredHeight: 32
    color: "transparent"

    Rectangle {
        anchors.fill: parent; anchors.margins: 8
        color: "#8B2500"  // 深红
        radius: theme.radius
        visible: sessionStore.canAdvanceMortality

        Text {
            anchors.centerIn: parent
            text: "⚡ 推进到下一阶段"
            color: "#FFD700"
            font.pixelSize: 10; font.bold: true
        }

        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            onClicked: {
                var result = sessionStore.doAdvanceMortality()
                if (!result.success) {
                    root.showFeedback("error", result.message)
                }
            }
        }
    }
}
```

**注意：** 此处的推进按钮与 MortalityStage 底部的推进按钮**不冲突**——此处是当前阶段概览中的操作入口，MortalityStage 底部是阶段内操作。两者可以共存（原型如此）。**保留 MortalityStage 底部执行/推进切换逻辑不变。**

#### 3.2.3 进度行

```qml
// 进度
ColumnLayout {
    Layout.fillWidth: true
    Layout.leftMargin: 8; Layout.rightMargin: 8
    spacing: 2

    Text { text: "📋 进度"; color: "#8B2500"; font.pixelSize: 10; font.bold: true }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "流程"; color: theme.textSecondary; font.pixelSize: 9 }
        Item { Layout.fillWidth: true }
        Text { text: "2/2"; color: theme.textPrimary; font.pixelSize: 9; font.bold: true }
    }

    Rectangle { Layout.fillWidth: true; height: 1; color: theme.borderNormal }

    RowLayout {
        Layout.fillWidth: true
        Text { text: "状态"; color: theme.textSecondary; font.pixelSize: 9 }
        Item { Layout.fillWidth: true }
        Text { text: sessionStore.canExecuteMortality ? "可操作" : "已完成";
               color: sessionStore.canExecuteMortality ? theme.statusSuccess : theme.textMuted;
               font.pixelSize: 9; font.bold: true }
    }
}
```

#### 3.2.4 玩家信息

取代当前散落在各处的派系信息：

```qml
// 玩家
ColumnLayout {
    Layout.fillWidth: true
    Layout.leftMargin: 8; Layout.rightMargin: 8
    spacing: 2

    Text { text: "👤 玩家"; color: "#8B2500"; font.pixelSize: 10; font.bold: true }

    RowLayout { Layout.fillWidth: true
        Text { text: "派系"; color: theme.textSecondary; font.pixelSize: 9 }
        Item { Layout.fillWidth: true }
        Text { text: sessionStore.viewerFactionName || "Optimates";
               color: theme.textPrimary; font.pixelSize: 9; font.bold: true }
    }

    Rectangle { Layout.fillWidth: true; height: 1; color: theme.borderNormal }

    RowLayout { Layout.fillWidth: true
        Text { text: "人物"; color: theme.textSecondary; font.pixelSize: 9 }
        Item { Layout.fillWidth: true }
        Text { text: (sessionStore.factionMemberCount || "5") + "人";
               color: theme.textPrimary; font.pixelSize: 9; font.bold: true }
    }
}
```

### 3.3 日志区域风格保持

V2 中 ContextPanel 日志已改为奶油色背景。**保留**当前日志实现（cream bg、compact headers、timestamp + type + message），仅做微调：
- 日志标题「📋 事件日志」改为与顶部一致的 `#8B2500` 文字色
- 移除底部「⚡ 操作事件将记录在此」辅助文字
- 日志区域高度：保持 FillHeight 占比，不做限制

### 3.4 移除底部 flow control 整段

Pass 1.5 已删除刷新按钮。现在进一步删除整个底部 RowLayout（含 `completeCurrentPlayer` 按钮）——因其在 Design 中不存在于 ContextPanel 右下角。**阶段推进操作统一由 Pass 3.2.2 的「推进到下一阶段」按钮提供。**

---

## Pass 4 — 顶部标题栏对齐（P2）

### 4.1 标题增强 + SPQR（Phase-2 §4.1 / §21 / §23）

**目标：** 从当前 `"🏛️ Eagle of Rome"` 改为 `"🏛 EAGLE OF ROME · SPQR"`，增大字号，增加标题权重。

**文件：** `src/ui/gui/qml/shell/TopStatusBar.qml`

**修改：**
```qml
// 原：
Text {
    text: "🏛️ Eagle of Rome"
    color: "#FFD700"
    font.pixelSize: 12
    font.family: theme.fontTitle
    font.bold: true
    Layout.preferredWidth: 130
}

// 改为：
Text {
    text: "🏛 EAGLE OF ROME · SPQR"
    color: "#FFD700"
    font.pixelSize: 13
    font.family: theme.fontTitle
    font.bold: true
    Layout.preferredWidth: 180
}
```

### 4.2 指标选择与排序（Phase-2 §4.1 / §23）

**依据：** Phase-2 §4.1 — Design 只显示 5 个关键指标：
```text
💰 142 国库
🛡 12 派系
⚖ 68 影响力
🏛 78% 稳定度
⚔ 1 战争
```

**当前代码指标过多重复**（国库/公地/军团/舰队/行省/存活人数）。

**操作要求：** 隐藏或移除以下指标显示：
- 公地（🌾 C）→ 从 header 移除
- 军团（⚔️ 个）→ 从 header 移除（战争指标已包含）
- 舰队（⚓ 个）→ 从 header 移除
- 行省（🏛️ 个）→ 从 header 移除
- 存活人数（👤 人）→ 从 header 移除

**保留的指标** = 国库（`sessionStore.treasury`）作为第一项显示。

**新增/保留指标（对齐 Design）：**
```qml
💰 (sessionStore.treasury || 0) + " T"          → 国库
🛡 (sessionStore.factionCount || sessionStore.viewerFactionCount || 12) + " 派系"  → 派系数
⚖ (sessionStore.influence || 68) + " 影响力"     → 影响力
🏛 (sessionStore.stability || 78) + "% 稳定度"    → 稳定度
⚔ (sessionStore.warCount || 0) + " 战争"         → 战争数
```

**指标标签文字改为中文**（非 `T` / 纯数字），对齐 Design：
```qml
"💰 " + treasury + " 国库"
"🛡 " + factions + " 派系"
"⚖ " + influence + " 影响力"
"🏛 " + stability + "% 稳定度"
"⚔ " + wars + " 战争"
```

### 4.3 日期移到右侧（Phase-2 §4.1）

**当前：** 年份紧跟在标题之后。
**目标：** 将日期/回合显示提取到右侧（RHS），与 Design 的 `282 BC · 回合 1` 一致。

操作：
1. 把当前 `年份RowLayout` 从标题旁移除
2. 在 header RHS 添加新的 RowLayout：

```qml
Item { Layout.fillWidth: true }  // 弹性空间

// 分隔线
Rectangle { width: 1; height: 22; color: "#55FFD700" }

// 回合/年份（右端）
RowLayout {
    spacing: 4
    Layout.alignment: Qt.AlignVCenter
    Text {
        text: (sessionStore.yearDisplay || "282 BC") + "  ·  回合 " + (sessionStore.turnNumber || 1)
        color: "#FFD9A0"
        font.pixelSize: 11
        font.bold: true
    }
}
```

**注意：** Phase-2 §4 提到 Design header 中的年份在 RHS 且相邻无阶段 badge（Pass 1.2 已移除）。

---

## Pass 5 — 视觉 Token 对齐（P3）

### 5.1 PhaseRail 活跃状态圆形化（Phase-2 §5 / §23）

**依据：** Phase-2 §5 — 当前活跃阶段使用大暗色矩形块，Design 要求圆形按钮，与未激活一致仅高亮色不同。

**操作：** 将 PhaseRail.qml 中活跃阶段按钮的样式从矩形高亮改为圆形高亮。颜色使用 `#8B2500` 深红填充 + 金色边框，未激活保持浅色圆形。

### 5.2 BottomQueryBar 活跃色修正（Phase-2 §19 / §23）

**依据：** Phase-2 §19 — 当前活跃按钮为亮饱和黄色，Design 要求受控的金色/赭色高亮。

**操作：** 将 BottomQueryBar.qml 中活跃按钮的颜色从亮黄色改为 `#E8A030` 柔和金色。文字保持可读深色。

### 5.3 全局罗马深红统一

检查并统一以下组件的 accentPrimary 使用：
- TopStatusBar header 底色：保持 `#8B2500`
- ContextPanel 深红分隔线：保持
- 死亡卡片标题色：保持 `#8B2500`
- 侧边栏标题色（当前阶段/进度/玩家/事件日志）：统一使用 `#8B2500`

### 5.4 金色/赭色 Accent 统一

统一金色/赭色使用场景：
- 进度状态「可操作」：`theme.statusSuccess`（绿色，仅语义状态）
- 推进按钮文字：`#FFD700`
- 步骤条完成态：`#FFD700`
- 边框强调：`theme.borderNormal` / `#D4A574`

---

## Pass 6 — 最终密度调整（P4）

### 6.1 侧边栏宽度压缩（Phase-2 §13）

**当前：** ContextPanel `width: 320`
**目标：** `width: 260`

**文件：** `src/ui/gui/qml/shell/GameShell.qml`（ContextPanel 实例化处）

### 6.2 全局边距审查

| 位置 | 当前 | 目标 | 文件 |
|------|------|------|------|
| MortalityStage margins | 10 | 8 | MortalityStage.qml |
| MortalityStage spacing | 6 | 4~6 | MortalityStage.qml |
| ContextPanel 各段 margins | 8 | 6 | ContextPanel.qml |
| 左 rail width | 68 | 60 | GameShell.qml / PhaseRail.qml |
| BottomQueryBar height | 36 | 32 | GameShell.qml / BottomQueryBar.qml |

---

## 六、修改文件清单汇总

| Pass | 文件 | 主要操作 | 风险 |
|------|------|---------|------|
| P1.1 | `src/ui/gui/qml/shell/GameShell.qml` | 删除 `stageAnnouncement` 区块 | 🟢 |
| P1.2 | `src/ui/gui/qml/shell/TopStatusBar.qml` | 删除右上阶段徽标 | 🟢 |
| P1.3 | `src/ui/gui/qml/shell/PhaseRail.qml` | 隐藏/移除 refresh/settings 按钮；活跃状态圆形化（P5） | 🟢 |
| P1.4 | `src/ui/gui/qml/shell/ContextPanel.qml` | 删除 2×2 卡片网格 + 底部刷新按钮；重建 IA（P3） | 🟡 |
| P2.1~2.5 | `src/ui/gui/qml/stages/MortalityStage.qml` | 紧凑 header / 指令面板 / 去嵌套 / 缩小按钮 | 🟢 |
| P3 | `src/ui/gui/qml/shell/ContextPanel.qml` | 完整 IA 重组（当前阶段→操作→进度→玩家→日志） | 🟡 |
| P4 | `src/ui/gui/qml/shell/TopStatusBar.qml` | 标题增强 + SPQR；指标精简；日期移右 | 🟢 |
| P5.1 | `src/ui/gui/qml/shell/PhaseRail.qml` | 活跃状态圆形化 | 🟢 |
| P5.2 | `src/ui/gui/qml/shell/BottomQueryBar.qml` | 活跃色从亮黄 → 柔和金 | 🟢 |
| P6 | `GameShell.qml` + 各 QML | 边距/宽度/密度微调 | 🟢 |
| (已有) | `src/ui/gui/session_store.py` | 已改：mortalityEvent property（V2 保留） | ✅ |
| (已有) | `src/core/service/mortality_service.py` | 已改：lost_wealth/lost_land（V2 保留） | ✅ |

## 七、禁止事项

1. **不得修改任何 Core 层代码**（GameState、Entity、阶段状态机、API 签名）
2. **不得修改任何游戏逻辑**（事件触发、概率、收入结算、规则）
3. **不得修改多玩家流程或 AI 自动执行逻辑**
4. **不得重命名已有模块或做无关大范围重构**
5. **不得硬编码 UI 文案** — 新增文案通过 GuiText 集中管理
6. **不得引入设计稿中不存在的新 UI 概念**
7. **PhaseRail 不得引入大型矩形活跃态** — 必须圆形
8. **不得保留亮绿色导航/大按钮** — 绿色仅用于语义状态标签
9. **不得保留暗色终端风格日志面板**
10. **不得修改 i18n 字符串体系**

## 八、实施顺序要求

> 按指定顺序实施，每 Pass 完成后验证无回归再进下一 Pass：

```text
Pass 1（结构删除）
  → 验证：其他阶段页面布局未受影响
  → 验证：游戏启动正常

Pass 2（中央工作区）
  → 验证：天命阶段执行/推进全链路
  → 验证：28/28 测试通过

Pass 3（右侧边栏）
  → 验证：ContextPanel 信息正确渲染
  → 验证：其他阶段 ContextPanel 不受影响
  → 验证：全局测试通过

Pass 4（顶部标题栏）
  → 验证：所有阶段 header 一致
  → 验证：指标数据正确

Pass 5（视觉 Token）
  → 验证：颜色统一

Pass 6（密度）
  → 验证：布局无截断/重叠
```

## 九、测试要求

### 9.0 ⚠️ 测试更新（Pass 1 前置）

`test_qml_startup.py:test_main_qml_exposes_core_gui_regions()` 中 `expected_objects` 列表包含 `"stageAnnouncement"`（第 95 行）。

该对象在 Pass 1.1 删除外部公告块后不复存在，**必须移除该断言**，否则测试失败。

```python
# 修改前：
expected_objects = [
    ...
    "stageAnnouncement",   # ← 删除
    ...
]

# 修改后：
expected_objects = [
    ...
    # "stageAnnouncement" 已移除（对齐 Design 原型）
    ...
]
```

理由：Design 原型中不存在外部阶段公告块。删除公告块是对齐设计规范的必要操作，测试随之更新是合理变更。

其余测试不受影响：
- `test_opc_shell_exposes_twelve_bottom_query_buttons()` — 只测按钮列表，颜色改动不影响
- `test_opc_shell_boundary_and_i18n_scans()` — 只测硬编码中文，移除公告块反而消除引用
- 772 个 Core/API 测试完全不受 QML 布局变更影响

### 9.1 执行命令

```bash
cd /mnt/c/Users/Kerl/PycharmProjects/Eagle\ of\ Rome
python -m pytest src/tests/ -v
```

### 9.2 验收检查项（基于 Phase-2 §25）

- [ ] 外部阶段公告块已移除（多阶段 header 只出现一次）
- [ ] 右上角阶段徽标已移除
- [ ] TopStatusBar 显示 `🏛 EAGLE OF ROME · SPQR`
- [ ] header 指标精简到 5 项（国库/派系/影响力/稳定度/战争）
- [ ] 日期/回合显示在 RHS
- [ ] PhaseRail 活跃态圆形、refresh/settings 隐藏
- [ ] Phase header 紧凑（高度 ~44）
- [ ] 步骤条左对齐、紧凑（高度 ~26）
- [ ] 指令面板存在（步骤条下方）
- [ ] 中央区域无额外嵌套边框
- [ ] 执行按钮紧凑（宽 120~140 × 高 32）
- [ ] 右侧 2×2 资源卡片已移除
- [ ] 右边栏宽 260
- [ ] 右边栏 IA 当前阶段→操作→进度→玩家→日志
- [ ] 操作按钮深红/金色、存在
- [ ] 进度/状态使用紧凑行
- [ ] 玩家信息使用紧凑行
- [ ] 日志使用奶油色背景
- [ ] 底部开发控件已隐藏
- [ ] BottomQueryBar 活跃色柔和金（非亮黄）
- [ ] 全量测试通过
- [ ] 代码不影响其他阶段布局

## 十、颜色系统参考（Phase-2 §20 / §5）

### 10.1 调色板规范

| Token | 色值 | 用途 |
|-------|------|------|
| 罗马深红 | `#8B2500` | 主按钮、标题、强调、header 底 |
| 金色 | `#FFD700` | 文字高亮、完成态 |
| 柔和金 | `#E8A030` | 活跃态、边框 |
| 羊皮纸底 | `#F5F0E8` / `theme.bgApp` | 全局背景 |
| 浅羊皮纸 | `#FAF5EE` / `theme.bgSurface1` | 面板 |
| 奶油白 | `#FFFDF5` / `theme.bgSurface2` | 数据行/卡片 |
| 暖边框 | `#D4A574` / `theme.borderNormal` | 面板边框 |
| 主文字 | `#3A3530` / `theme.textPrimary` | 深棕 |
| 次文字 | `#8B7355` / `theme.textSecondary` | 棕灰 |
| 语义绿 | `#228B22` / `theme.statusSuccess` | 仅状态标签 |

### 10.2 场景对照

| 元素 | 色值 | 来源 |
|------|------|------|
| header 底色 | `#8B2500` | Phase-2 §4 |
| 推进按钮底 | `#8B2500` | Phase-2 §10 |
| 执行按钮底（可执行） | `#8B2500` | Phase-2 §10 |
| 推进/执行文字 | `#FFD700` | Phase-2 §10 |
| 步骤条步骤② 完成 | `#FFD700` | Phase-2 §7 |
| 活跃 PhaseRail 填充 | `#8B2500` + 金边 | Phase-2 §5 |
| 活跃 BottomQueryBar | 柔和金（非亮黄） | Phase-2 §19 |
| 日志背景 | cream | Phase-2 §17 |
| 死亡卡片 | cream 底 + 金色边 + 深红标题 | Phase-2 §7.2 |

## 十一、DA 交付格式

请将开发验收报告归档到：

```text
docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03C 天命阶段GUI对齐 开发验收报告 - DA.md
```

报告必须包含：

```text
Decision by DA: READY_FOR_SA_REVIEW / BLOCKED / RETURN_FOR_SCOPE_CONFIRMATION

基线: 2c2de94e0d8931325d737f5957c6d18569275557

修改文件清单:
- GameShell.qml — 移除公告块 + ContextPanel width + 间距
- TopStatusBar.qml — SPQR 标题 / 指标精简 / 日期RHS / 移徽标
- PhaseRail.qml — 隐藏 dev 工具 / 活跃态圆形
- ContextPanel.qml — 完整 IA 重建
- MortalityStage.qml — 紧凑 / 指令面板 / 去嵌套 / 按钮缩小
- BottomQueryBar.qml — 活跃色修正

Phase-2 合规性:
- §3 外部公告块已移除
- §4 header 对齐
- §5 PhaseRail 圆形活跃态
- §6 阶段 header 紧凑
- §7 步骤条左对齐
- §8 指令面板已恢复
- §9 嵌套边框已处理
- §10 按钮紧凑
- §11~§18 右边栏 IA 重建
- §19 BottomQueryBar 活跃色修正
- §20~§22 色彩/字型/间距对齐
- §23 矩阵逐项通过

测试结果:
- pytest: XXXX passed, X failed

已知风险:
需要 SA/项目负责人确认的问题:
```

⚠️ **DA 不得提交 Git。** Git 归档由 SA 在项目负责人确认验收后执行。


---

# ==================== Phase-3 精修叠盖层 ====================

> 以下内容叠盖在 V3（Phase-2 6 Pass）之上。V3 已执行，Phase-3 新增 5 Pass 精修。

## Phase-3 任务定位

参考：`EOR_GUI_Design_vs_Actual_AI_Modification_Spec_Mortality Phase-3.md`

> This is no longer a full redesign task. It is a precision visual convergence task.
> The screen still feels heavier, more boxed, and less clean than the Design.
>
> Design: compact parchment strategy-game interface
> Actual 3: prototype-like GUI with too many borders, nested panels, and dense boxed regions

### V3 → Phase-3 差距概要

| 模块 | V3 状态 | Phase-3 要求 |
|------|---------|-------------|
| Phase header | 高度 44，「就绪」标签 | 移除「就绪」标签；高度→38 |
| Instruction panel | 只有 Line 1 | 加 Line 2：事件类型 |
| 「天命已执行」横幅 | 全宽深红 32px | 紧凑奶油色非全宽 |
| Central workspace | bgSurface1 Rectangle 事件区 | 移除内层，让 workspace 背景自然空 |
| Execute button | 130×32, 金色边 | 100×26, 柔和金 #E8A030 边 |
| Sidebar action button | 全宽深红 #8B2500 | 紧凑柔和金 #E8A030 |
| Event log | 无残留文字 | 减少空白，确认无 artifact |
| Top header metric 间距 | 接近 | 再精调 spacing/权重 |

---

## Phase-3 5 Pass 实现序列

### Pass 1 — 结构清理

#### 1.1 移除「就绪」标签（Phase-3 §6.3 / §20 / §22）

**文件：** `MortalityStage.qml`

删除 Phase header 右端的状态标签 Rectangle（显示「就绪」/「已完成」）。

理由：Design 原型中不存在。阶段状态已通过步骤条和按钮启用/禁用表达。

#### 1.2 消除中央嵌套面板（Phase-3 §5 / §10 / §20）

**文件：** `MortalityStage.qml`

将事件展示区外层 Rectangle 从 `color: theme.bgSurface1` 改为 `color: "transparent"`，让 workspace 的 `theme.bgApp` 自然充当空区域。

#### 1.3 确认无底部残留（Phase-3 §17.3）

**文件：** `ContextPanel.qml`

确认 Event Log 底部无 stray text / debug artifact。

---

### Pass 2 — 中央工作区精修

#### 2.1 压缩 Phase header（Phase-3 §6.3）

| 元素 | 当前 | 目标 |
|------|------|------|
| Header height | 44 | 38 |
| 编号徽标 | 28×28, r=14 | 24×24, r=12 |
| 标题 font | 14 | 13 |
| 说明 font | 9 | 8 |
| Margins | 8 | 6 |

#### 2.2 指令面板加事件类型行（Phase-3 §8.3）

```qml
// 当前：单行
Text {
    text: "📕 点击下方「执行天命」按钮，触发一个随机事件。"
}

// 目标：两行
ColumnLayout {
    spacing: 2
    Text { text: "📕 点击下方「执行天命」按钮，触发一个随机事件。" }
    Text { text: "事件类型：猝死" }  // 或 sessionStore 中的实际 event type
}
```

#### 2.3 精简「天命已执行」横幅（Phase-3 §9）

```qml
// 当前：全宽深红
Rectangle {
    Layout.fillWidth: true; height: 32
    color: "#8B2500"
}

// 目标：紧凑奶油色
Rectangle {
    Layout.alignment: Qt.AlignHCenter
    implicitWidth: resultLabel.implicitWidth + 16
    height: 24
    color: theme.bgSurface2
    border.color: theme.borderNormal; radius: 4
    Text {
        anchors.centerIn: parent
        text: "🎴 天命已执行"
        color: "#8B2500"
        font.pixelSize: 10; font.bold: true
    }
}
```

#### 2.4 缩小 Execute 按钮（Phase-3 §11.3）

| 元素 | V3 | Phase-3 |
|------|----|---------|
| width | 130 | 100 |
| height | 32 | 26 |
| font | 11 | 10 |
| border | #FFD700 | #E8A030（柔和金） |
| container height | 44 | 34 |

---

### Pass 3 — 右侧边栏精修

#### 3.1 推进按钮 → 紧凑柔和金（Phase-3 §14 / §12.3）

```qml
// 当前：全宽深红 #8B2500
Rectangle { anchors.fill: parent; color: "#8B2500" }

// 目标：紧凑 #E8A030
Rectangle {
    anchors.horizontalCenter: parent.horizontalCenter
    width: implicitWidth + 16; height: 24
    color: "#E8A030"
    radius: 4
}
```

#### 3.2 事件日志空白修复（Phase-3 §17.3）

- 当日志为空或只有 2-3 条时，减少日志面板的留白比例
- 不改变 layout 结构，只调小 `anchors.margins` 或移除多余间距

---

### Pass 4 — 标题栏与底栏精修

#### 4.1 TopStatusBar 间距（Phase-3 §3.3）

左对齐边距 match Design，metric 之间的 spacing 均匀，分隔线颜色统一 `#55FFD700`。

#### 4.2 BottomQueryBar 活跃态（Phase-3 §18.3）

V3 已改用 `#E8A030`，确保 border 不厚、不过度显眼。

---

### Pass 5 — Token 与密度最终调整

扫一遍所有修改文件，确认无临时/调试色值残留。全局边距微调：

| 位置 | V3 | Phase-3 |
|------|----|---------|
| MortalityStage margins | 8 | 6 |
| MortalityStage spacing | 4 | 3 |
| ContextPanel 各段 margins | 8 | 6 |

---

## Phase-3 修改文件清单

| Pass | 文件 | 操作 |
|------|------|------|
| P1.1 | MortalityStage.qml | 移除「就绪」标签 |
| P1.2 | MortalityStage.qml | 中央展示区 transparent |
| P1.3 | ContextPanel.qml | 确认无残留 |
| P2.1 | MortalityStage.qml | Header 压缩 44→38 |
| P2.2 | MortalityStage.qml | 指令面板加事件类型行 |
| P2.3 | MortalityStage.qml | 横幅紧凑奶油色 |
| P2.4 | MortalityStage.qml | 按钮 130×32→100×26 |
| P3.1 | ContextPanel.qml | 推进按钮深红→紧凑金 |
| P3.2 | ContextPanel.qml | 日志空白精调 |
| P4 | TopStatusBar.qml | 间距均匀 |
| P4 | BottomQueryBar.qml | active 色验证 |
| P5 | 全文件 | Token + 边距 |

---

## Phase-3 验收标准（Phase-3 §22）

- [ ] Phase header 无「就绪」标签
- [ ] Phase header 紧凑（高度 ≤38）
- [ ] 指令面板含事件类型行
- [ ] 中央工作区无嵌套面板
- [ ] Execute 按钮紧凑（100×26, 柔和金边）
- [ ] 「天命已执行」横幅非全宽奶油色
- [ ] 侧边栏推进按钮紧凑柔和金
- [ ] 事件日志无残留文字
- [ ] TopStatusBar metric 间距均匀
- [ ] BottomQueryBar 活跃色柔和金
- [ ] 无边距超标
- [ ] 无临时/调试色值
- [ ] 全量测试通过

---

## Phase-3 测试

按 AI-GOV-2026-07-06-001 的分层回归协议执行。

```bash
# 开发中：定向测试
python3 -m pytest src/tests/test_gui/ src/tests/test_api/test_mortality_api.py -v

# 验收前：全量回归（仅输出机器摘要）
python3 -m pytest src/tests/ -v
```

全量通过时仅保留：命令 + 结果摘要 + 耗时 + 报告路径。
