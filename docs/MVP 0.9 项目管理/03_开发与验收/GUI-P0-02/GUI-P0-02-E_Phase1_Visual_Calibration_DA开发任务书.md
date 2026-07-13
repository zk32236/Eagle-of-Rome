# DA 开发任务书 — GUI-P0-02-E Phase 1 视觉校准返修

**序列交付件 #3（版本 2）**
**角色：SA（奥古斯都）**
**日期：2026-07-11**
**依据：** SA 规范模板 v1.0 §十五（GUI 视觉校准返修任务类型）
**配套：** `EOR_GUI_Prototype_v3.25.1.html`（目标设计稿）
**代码基准：** `main` (65bbf67) + 此前 GUI-P0-02-D 改动
**Python：** `python3`

---

## 一、任务目标

将 Phase 1 的 9 个 QML 文件按 `EOR_GUI_Prototype_v3.25.1.html` 精确复刻视觉结构，确保运行截图与设计稿逐区域一致。

不允许修改 Core/System/Service/Entity，不允许新阶段功能。

---

## 二、视觉不可偏移清单

### 2.1 A — 顶部状态栏（TopStatusBar.qml）

| 约束 | 值 |
|------|-----|
| 背景色 | `#8B2500`（深朱红），纯色，无渐变 |
| 高度 | 48px |
| 内边距 | 水平 16px |
| 颜色 | 文字 #FFEEDD，数值 #FFD700，标签 rgba(255,255,255,0.55) |
| 字体 | 0.78rem stat 值，0.62rem stat 标签 |

**从左到右的块顺序：**
```
[Logo] 🏛️ EAGLE OF ROME · SPQR
  → [国库] 💰 142 国库
  → [派系] 👛 12 派系
  → [影响力] ⚖️ 68 影响力
  → [稳定度] 🏛️ 78% 稳定度
  → [战争] ⚔️ 1 战争（warCount > 0 时显示）
  → [回合] 282 BC · 回合 1（右对齐）
```

**状态项分隔：** 每个 stat-item 之间有 `border-left: 1px solid rgba(255,255,255,0.15)`，第一个无左边框。

**不可偏移：** 严禁擅自删除稳定度栏位。稳定度数据暂缺时用安全占位（`"--"` 或 Store 只读派生值）。

### 2.2 B — 左侧阶段导航（PhaseRail.qml + PhaseRailIcon.qml）

| 约束 | 值 |
|------|-----|
| 导轨宽度 | **44px**（窄轨道，不是宽按钮列表） |
| 背景 | `#FAF5EE`，边框 `#D4A574` |
| 圆形尺寸 | **34px × 34px**（不是 38px 或 44px） |
| 圆形圆角 | `border-radius: 50%` |
| 已执行态 | 背景 `#CD853F`，白色文字 |
| 当前态 | 背景 `#E8B84B`，深色文字，`border 2px solid #C9A84C`，`box-shadow` |
| 待执行态 | 背景 `#E8D5C4`，灰色文字 |
| 图标字体 | 0.75rem（emoji 图标） |
| Hover | `transform: scale(1.1)`，显示 tooltip 标签在右侧弹出 |

**7 个图标的顺序和 emoji：**
```
🎴 天命 → 💰 收入 → 🏛️ 广场 → ⚖️ 人口 → 🏺 元老院 → ⚔️ 战斗 → 📊 决算
```

**不可偏移：** 禁止改宽轨道。禁止把圆形图标改为矩形或文字列表。hover 弹出文字，不是常驻显示。

### 2.3 C — 中央阶段桌面（panel-center）

| 约束 | 值 |
|------|-----|
| 背景色 | **`#FAF5EE`**（象牙白，不是深色） |
| 边框 | `1px solid #D4A574` |
| 圆角 | 6px |
| 内边距 | 14px |
| 内容 | 完整的 **象牙白阶段桌面** |

**Phase 1 只实现天命阶段（p0）的内容。** 其他阶段保持占位或隐藏。

**不可偏移：** 中央区域必须是完整象牙白桌面，不得实现为深色背景加一个大羊皮纸卡片。羊皮纸色（`#FFFDF5`）只用于 `info-box` 和 `stage-steps` 等局部内容，不得取代桌面底色。

### 2.4 D — 右侧状态面板（ContextPanel.qml）

| 约束 | 值 |
|------|-----|
| 宽度 | **240px** |
| 背景 | `#FAF5EE`，边框 `#D4A574` |
| 圆角 | 6px |

**从上到下顺序：**
```
ctx-top:
  [当前阶段] — 当前阶段名称、说明、子标题
  [操作] — 执行天命按钮（可操作时启用）
  [进度] — 阶段进度/状态指示
  [玩家] — 权限提示：玩家派系名
  [分隔线] border-top: 1px solid #D4A574
ctx-log:
  [事件日志] h4: "📢 事件日志" + 清空按钮
  [日志条目列表] feedback entries
```

**不可偏移：** 顺序必须严格按 "当前阶段→操作→进度→玩家→事件日志"。禁止用派系资源瓦片替换前三个块。

### 2.5 E — 底部查询栏（BottomQueryBar.qml）

| 约束 | 值 |
|------|-----|
| 背景 | `#3A2520`（深褐），不是 `#8B2500` |
| 风格 | 图标+文字按钮，**不是状态点按钮** |

**按钮区：** 图标+文字排成一行，每个按钮格式：
```
<button class="op-btn">
  <span class="ico">📋</span>派系信息
</button>
```

**全部 12 个按钮的图标和文字（与 HTML 原型完全一致）：**
```
📋 派系信息  |  👤 人物查询  |  📊 游戏状态
💰 派系金库  |  🌾 公地信息  |  🏡 私地信息
📦 合同状态  |  🏛️ 行省信息  |  ⚔️ 战争列表
🗡️ 军团状态  |  ⚓ 舰队状态  |  ❓ 帮助
```

**按钮 4 个状态：** CSS class 对应 `connected` / `readonly` / `placeholder` 由 DA 自行区分。**不使用状态圆点**。

**不可偏移：** 按钮必须是图标+文字格式，不是圆点+状态标签。背景色调 `#3A2520`。

### 2.6 F — 主操作控件（天命阶段按钮）

| 约束 | 值 |
|------|-----|
| 按钮位置 | 中央桌面**底部居中** |
| 对齐 | `display:flex; justify-content:center` |
| 按钮文字 | `⚡ 执行天命` |
| 按钮样式 | `btn primary`：背景 `#8B2500`，金色文字 `#FFD700`，边框同色 |
| Hover | 背景过渡到 `#A0522D` |
| 按钮容器 | `margin-top: 6px` |

**不可偏移：** 按钮必须在中央桌面底部、水平居中，不是左下角或右侧。

### 2.7 天命阶段内容（MortalityStage.qml）

| 元素 | 描述 |
|------|------|
| 阶段徽标 | `1 / 7`，`#8B2500` 背景，`#FFD700` 文字，`border-radius: 8px` |
| 阶段标题 | `🎴 天命阶段`，颜色 `#6B1C00`（header-bg），1rem，bold |
| 阶段描述 | 斜体文字，`#8B7355`，0.72rem |
| 步骤引导条 | `stage-steps`：`#FFFDF5` 背景，`#C9A84C` 边框，6px 圆角 |
| 步骤1 | 圆形 `sn current` → 步骤号 "1" + 文字 "⚡ 执行天命" |
| 步骤2 | 圆形 `sn todo` → 步骤号 "2" + 文字 "📜 查看事件结果" |
| 步骤间箭头 | `→` 灰色间隔 |
| 事件区 | `info-box`：`#FFFDF5` 背景，`#C9A84C` 边框，6px 圆角，0.72rem |
| 执行按钮 | 居中位置（见 2.6 F） |

---

## 三、功能绑定表

| 控件 | 区域 | Store 来源 | 可用条件 | 禁用条件 |
|------|------|-----------|---------|---------|
| 国库值 | A | `sessionStore.treasury` | 会话存在 | 显示 0 或 `"--"` |
| 派系金库 | A | `sessionStore.factionTreasury` | 会话存在 | 同上 |
| 影响力 | A | `sessionStore.factionInfluence` 或 `_snapshot` | 会话存在 | 同上 |
| 稳定度 | A | 占位（`_snapshot` 暂时不存在则显示 `"--"`） | 始终 | 不删除栏位 |
| 战争数 | A | `sessionStore.warCount` | `warCount > 0` | 隐藏整块 |
| 回合信息 | A | `sessionStore.yearDisplay / turnNumber` | 会话存在 | 占位 |
| 执行天命 | F/C | `sessionStore.doExecuteMortality()` | `canExecuteMortality` | 非天命阶段或无会话 |
| 事件展示 | C | `sessionStore.mortalityEvents` | 已执行 | 显示提示文字 |
| 当前阶段 | D | `sessionStore.selectedPhaseName` | 会话存在 | 安全占位 |
| 当前玩家 | D | `sessionStore.viewerFactionName` | 会话存在 | 安全占位 |
| 事件日志 | D | `sessionStore._feedback_queue` 或 `_log` | 始终 | 空状态 |
| 查询按钮 | E | `sessionStore.executeQuery()` / `globalQueryResult` | 按钮状态决定 | 占位按钮显示占位 |

---

## 四、允许修改范围

| 文件 | 路径 | 动作 |
|------|------|------|
| `TopStatusBar.qml` | `src/ui/gui/qml/shell/` | ✅ **按 2.1 视觉约束重写** |
| `PhaseRail.qml` | `src/ui/gui/qml/shell/` | ✅ **按 2.2 视觉约束重写** |
| `PhaseRailIcon.qml` | `src/ui/gui/qml/components/` | ✅ **按 2.2 视觉约束重写** |
| `ContextPanel.qml` | `src/ui/gui/qml/shell/` | ✅ **按 2.4 视觉约束重写** |
| `BottomQueryBar.qml` | `src/ui/gui/qml/shell/` | ✅ **按 2.5 视觉约束重写** |
| `QueryResultOverlay.qml` | `src/ui/gui/qml/shell/` | ✅ 视觉对齐 |
| `MortalityStage.qml` | `src/ui/gui/qml/stages/` | ✅ **按 2.7 视觉约束重写** |
| `StepBar.qml` | `src/ui/gui/qml/components/` | ✅ 按 2.7 步骤条修改 |
| `session_store.py` | `src/ui/gui/` | ❌ **不动**（上一轮 DA 已修复完成） |
| `GameShell.qml` | `src/ui/gui/qml/shell/` | ❌ 不动 |
| `Main.qml` | `src/ui/gui/` | ❌ 不动 |

---

## 五、禁止修改范围

- ❌ 不得修改 `src/core/`、`src/api/`、`src/systems/`、`src/entities/`
- ❌ 不得修改 `src/ui/gui/session_store.py`（上一轮已完成）
- ❌ 不得修改 `src/ui/gui/api_adapter.py`
- ❌ 不得在 QML 中复制业务规则
- ❌ 不得直接用硬编码数据伪装 Store/API 已完成

---

## 六、测试要求

| 测试 | 命令 | 最低要求 |
|------|------|---------|
| 回归测试 | `python3 -m pytest src/tests/ -q` | 报告实际 passed/failed/skip 数量 |
| QML 启动 | 启动游戏验证无 QML fatal error | 报告启动是否成功 |
| GUI 相关测试 | `python3 -m pytest src/tests/test_gui/ -q` 如存在 | 报告实际结果 |

测试结果必须写明：命令、实际通过/失败/跳过数量、失败项、遗留风险。禁止只写"已测试"。

---

## 七、截图自查表（DA 交付时必须填写）

| 区域 | 目标要求 | 实际结论 | 差异说明 | 是否需返修 |
|------|---------|---------|---------|:---------:|
| A 顶栏 | 48px, #8B2500, 5 stat 块 + 回合, 正确顺序 | | | |
| B 左导航 | 44px 窄轨, 34px 圆, done/current/todo 三态 | | | |
| C 中央桌面 | #FAF5EE 象牙白, 1px #D4A574 边框 | | | |
| D 右面板 | 240px, 顺序:当前阶段→操作→进度→玩家→日志 | | | |
| E 底栏 | #3A2520 背景, 图标+文字按钮 | | | |
| F 主按钮 | 中央桌面底部居中, #8B2500 | | | |
| 天命徽标 | 1/7, #8B2500/#FFD700 | | | |
| 步骤引导 | 2-step, #FFFDF5背景, #C9A84C边框 | | | |

**没有填写此表的交付不进入验收。**

---

## 八、返修条件

出现以下任一情况直接退回：

1. 中央区域不是完整象牙白桌面（#FAF5EE），而是深色背景加巨大卡片
2. 右侧面板未按"当前阶段→操作→进度→玩家→事件日志"组织
3. 左侧导航脱离窄轨道形态（宽于 44px 或不是圆形图标）
4. 底部查询栏使用状态点替代图标+文字入口
5. 主操作按钮不在中央桌面底部居中
6. 顶栏缺少稳定度栏位（可用占位，不可删除）
7. DA 未提交实际运行截图
8. DA 未提交区域自查表
9. 出现 Core/System/Service/Entity 非授权修改
10. 硬编码数据伪装 Store/API 已完成

---

## 九、执行方式

DA-Exec disposable subagent。执行完成后写入报告到：
```
E:\OpenClaw\Projects\EOR\agents\DA-Exec\reports\2026-07-11-gui-p0-02-e-da-report.md
```

返回：
1. 报告路径
2. 变更文件清单
3. 测试结果
4. 截图自查表（按 §七 格式填好）
5. 阻塞项或无
6. 结论（PASS / FAIL）
