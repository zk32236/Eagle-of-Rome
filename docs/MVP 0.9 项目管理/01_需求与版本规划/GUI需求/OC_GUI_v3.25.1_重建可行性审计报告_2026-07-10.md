# OC GUI v3.25.1 重建可行性审计报告

任务编号：GUI-P0-REBUILD-AUDIT-2026-07-10  
审计日期：2026-07-10  
审计执行：奥古斯都（OC）  
代码基准：`main` 分支（HEAD: `65bbf67`）

---

## 1. 当前 GUI 结构摘要

### 1.1 启动入口

**文件：** `src/ui/gui/app.py` 中的 `GuiApp` 类

```
GuiApp.__init__(state) → 创建 GuiSessionStore
GuiApp.run()           → 创建 QGuiApplication
                       → 注册 QML 类型（FigureListModel / CandidateListModel / EventListModel）
                       → 加载 Theme.qml → 暴露为 sessionStore / theme / guiApp 上下文属性
                       → 加载 Main.qml
```

当前入口干净、结构清晰，**无需重构**。

### 1.2 Python 与 QML 连接

通过 `QQmlApplicationEngine.rootContext().setContextProperty()` 暴露三个对象：

| 上下文属性 | 类型 | 职责 |
|---|---|---|
| `sessionStore` | `GuiSessionStore` | 所有只读属性和可调用 Slot |
| `theme` | `Theme.qml` 实例 | 色彩、边框、字体常量 |
| `guiApp` | `GuiApp` 自身 | QML 调回 Python 的桥梁（目前仅 `confirmHandoff`） |

### 1.3 GuiSessionStore

**文件：** `src/ui/gui/session_store.py`（398 行）

设计良好。核心特征：

- 只读属性暴露给 QML（`@Property`），不暴露写权限
- 所有操作入口为 `@Slot` 方法（`doCampaign`, `doVote`, `doExecuteMortality`, `doAdvanceMortality`, `doCompletePlayer`, `doGlobalQuery`, `selectPhase` 等）
- 每次操作后自动刷新快照并发射信号
- 内置反馈机制（`feedbackRaised` / `handoffRequired` 信号）
- 内置 disabled_reason 逻辑

**可复用度：100%**。无需修改即可在新 GUI 中继续使用。

### 1.4 GuiApiAdapter

**文件：** `src/ui/gui/api_adapter.py`（197 行）

设计良好。核心特征：

- 统一 API 调用包装器 `call()`，处理成功/失败/异常映射
- 每个阶段有专用方法（`campaign`, `vote`, `execute_mortality`, `advance_mortality` 等）
- Session 查询方法（`get_snapshot`, `get_population_view`, `get_mortality_view`, `get_senate_view`, `get_global_query_result`）
- 成功后自动调用 `refresh_callback`

**可复用度：100%**。API 层完整，Adapter 无需修改。

### 1.5 调用链验证

```text
QML 组件
↓ 读取 Property / 调用 Slot
GuiSessionStore
↓ 调用 Adapter 方法
GuiApiAdapter.call()
↓ 调用 API 函数
API (mortality_api, population_api, senate_api, session_api, gui_query_api, etc.)
↓ 调用 Core / System / Service
Core 层
```

✅ **无偏离**。测试 `test_opc_shell_boundary_and_i18n_scans` 已验证以下禁止调用全部不存在：

- `game_api.execute_phase` ❌ 未发现
- `game_api.execute_turn` ❌ 未发现
- `CombatCommand` ❌ 未发现
- `phase_senate`, `phase_forum`, `phase_revenue`, `phase_combat` ❌ 未发现

### 1.6 当前 QML 结构

```
Main.qml
└── GameShell.qml (5 区域)
    ├── TopStatusBar.qml (顶栏)
    ├── PhaseRail.qml (左侧阶段导航, 176px)
    ├── ContextPanel.qml (右侧状态/日志)
    ├── BottomQueryBar.qml (底部 12 查询按钮)
    ├── 中央区:
    │   ├── StageAnnouncement (阶段公告头)
    │   └── StageContainer:
    │       ├── MortalityStage.qml (195 行)
    │       ├── PopulationStage.qml (88 行)
    │       ├── SenateStage.qml (272 行)
    │       └── LockedStagePlaceholder.qml
    ├── PlayerHandoffOverlay.qml (交接遮罩)
    └── QueryResultOverlay.qml (查询结果浮窗)
```

### 1.7 现有阶段页面实现状态

| 阶段 | QML 文件 | 行数 | 实现状态 | 交互模式 |
|---|---|---|---|---|
| 天命 | MortalityStage.qml | 195 | ✅ 完整（执行+推进） | interactive |
| 收入 | — | — | ❌ 占位（LockedStagePlaceholder） | placeholder |
| 广场 | — | — | ❌ 占位 | placeholder |
| 人口 | PopulationStage.qml | 88 | ✅ 完整（庆典+投票+完成） | interactive |
| 元老院 | SenateStage.qml | 272 | ⚠️ 只读展示 | readonly |
| 战争 | — | — | ❌ 占位 | placeholder |
| 决算 | — | — | ❌ 占位 | placeholder |

---

## 2. 可复用清单

| 模块/文件 | 当前职责 | 可复用程度 | 复用条件 | 风险 |
|---|---|---|---|---|
| `app.py` / `GuiApp` | 应用入口、QML 引擎初始化 | **100%** | 无需修改 | 无 |
| `session_store.py` / `GuiSessionStore` | 状态管理、Slot 方法、信号 | **100%** | 无需修改（新 QML 按相同 property/slot 接口消费） | 低：新 QML 需保持接口一致 |
| `api_adapter.py` / `GuiApiAdapter` | API 统一调用封装 | **100%** | 无需修改 | 无 |
| `localization.py` | Python 侧 i18n 文本目录 | **100%** | 无需修改 | 无 |
| `GuiText.qml` | QML 侧 i18n 单例 | **100%** | 可继续使用，新阶段页面按相同模式扩展 | 低：需追加新键 |
| `Theme.qml` | 颜色/字体/边框常量 | **90%** | 结构完好；颜色值需更新为 v3.25.1 色彩体系 | 低：纯粹的配色替换 |
| `components/*.qml` | AppButton/DataTable/StatusTile 等 | **70%** | 结构概念保留；样式、颜色、阴影需按 v3.25.1 视觉规范更新 | 中：AppButton 的 type 系统需改色，DataTable 需支持羊皮纸风格 |
| `controllers/population_controller.py` | 人口阶段控制逻辑 | **50%** | 当前通过 Store 直接调用 Adapter，此文件实际未被主流程引用 | 低：可废弃或改造为 ViewModel |
| `models/*.py` | QAbstractListModel 子类 | **50%** | 三个 model 类已注册 QML 类型，但目前未被 QML 页面实际使用 | 低：新 GUI 若需要则保留 |
| `shell/GameShell.qml` | 5 区域布局容器 | **90%** | 布局结构正确，与新 Shell 结构一致 | 低：需更新配色、间距和子组件引用 |
| `shell/TopStatusBar.qml` | 顶部状态栏 | **60%** | 概念保留；布局结构、显示项需对齐 v3.25.1（当前缺稳定度/战争数），视觉需重做 | 中 |
| `shell/PhaseRail.qml` | 阶段导航 | **40%** | 概念保留，但宽度从 176px→44px、圆形图标替代文本条目是需要重做的主要变化 | 中-高 |
| `shell/ContextPanel.qml` | 右侧状态/日志 | **60%** | 概念保留；布局结构和资源瓦片逻辑可维持，但视觉需更新 | 中 |
| `shell/BottomQueryBar.qml` | 12 查询按钮 | **80%** | 按钮逻辑和数据绑定完好；视觉需改深红底色+饱满 HUD 风格 | 低 |
| `shell/FeedbackPanel.qml` | 日志/反馈区 | **70%** | 逻辑完好；外观需羊皮纸风格调整 | 低 |
| `shell/PlayerHandoffOverlay.qml` | 玩家交接遮罩 | **80%** | 逻辑完好；外观需视觉对齐 | 低 |
| `shell/QueryResultOverlay.qml` | 查询结果浮窗 | **80%** | 逻辑完好；外观需视觉对齐 | 低 |
| `stages/MortalityStage.qml` | 天命阶段页面 | **20%** | 功能逻辑不可复用（需按新 Store 接口重写）；视觉完全不符 | 高 |
| `stages/PopulationStage.qml` | 人口阶段页面 | **20%** | 同上 | 高 |
| `stages/SenateStage.qml` | 元老院只读展示 | **20%** | 同上 | 高 |
| `stages/FestivalView.qml` | 庆典组件 | **10%** | 视觉、数据绑定均需重写 | 高 |
| `stages/VoteView.qml` | 投票组件 | **10%** | 同上 | 高 |
| `stages/ElectionResultView.qml` | 选举结果组件 | **10%** | 同上 | 高 |
| `test_gui/test_adapter.py` | Adapter 测试 | **100%** | 无需修改 | 无 |
| `test_gui/test_qml_startup.py` | QML 启动测试 | **100%** | 无需修改；新 QML 加载后更新 objectName 断言即可 | 低 |
| `test_gui/test_session_api.py` | Session API 测试 | **100%** | 无需修改 | 无 |

### 可复用总结

| 层面 | 可复用程度 | 说明 |
|---|---|---|
| **Python 连接层** (app/store/adapter/localization) | 100% | 零修改 |
| **QML i18n/Theme/Components** | 70-100% | 需更新视觉值，概念保留 |
| **QML Shell** (5 区域容器) | 40-90% | 区域布局概念保留，视觉和部分组件需重建 |
| **QML Stages** (所有阶段页面) | 10-20% | 建议全部重建 |
| **测试** | 100% | 可作为重建期回归保护线 |

---

## 3. 应废弃或重建清单

| 模块/文件 | 问题类型 | 具体问题 | 建议处理 | 理由 |
|---|---|---|---|---|
| `MortalityStage.qml` | 视觉结构与 v3.25.1 严重不符 | 当前使用 flat 现代风格（深色背景+白色文本+蓝色强调），v3.25.1 要求深朱红外壳+象牙白桌面+羊皮纸卡片 | **重建** | 改造成本 ≈ 重写成本 |
| `PopulationStage.qml` | 同上 | 同上 | **重建** | 同上 |
| `SenateStage.qml` | 同上 | 同上。272 行只读展示全部需要重做视觉 | **重建** | 同上 |
| `FestivalView.qml` | 同上 | 庆典子组件视觉不符 | **重建** | 同上 |
| `VoteView.qml` | 同上 | 投票子组件视觉不符 | **重建** | 同上 |
| `ElectionResultView.qml` | 同上 | 选举结果子组件视觉不符 | **重建** | 同上 |
| `PhaseRail.qml` | 视觉结构与 v3.25.1 严重不符 | 当前 176px 宽文本条目，v3.25.1 使用 44px 宽圆形图标+悬浮标签 | **重建** | 宽度差异过大，无法修补 |
| `TopStatusBar.qml` | 视觉结构与 v3.25.1 不符 | 当前显示项/布局与 v3.25.1 不同（缺稳定度、战争数等状态项） | **重建或大改** | 布局结构可保留但视觉需重做 |
| `BottomQueryBar.qml` | 视觉不符 | 当前使用深灰/深色表面风格，v3.25.1 要求深朱红饱满 HUD | **重建或大改** | 按钮绑定逻辑可保留 |
| `ContextPanel.qml` | 视觉不符 | 当前布局可接受但视觉质感和配色需对齐 v3.25.1 | **大改** | 结构保留，视觉重做 |
| `GameShell.qml` | 视觉不符 | 当前颜色引用基于旧 Theme.qml 值，全部需要更新 | **大改** | 布局不变，颜色/间距更新 |

### 废弃/重建逻辑

- **重建（Rebuild）**：文件从头重写，不保留旧文件内容
- **大改（Major Rework）**：保留文件框架和绑定逻辑，重做视觉部分

---

## 4. 与 v3.25.1 的差距分析

### 4.1 逐区域差距

| GUI 区域 | v3.25.1 目标 | 当前实现状态 | 差距等级 | 改造建议 |
|---|---|---|---|---|
| **顶栏全局状态** | 深朱红底色 + 饱满 HUD：国库/派系/影响力/稳定度/战争数/回合年 | 深色表面栏：Logo+年/回合+国库+当前玩家 | **中** | 布局逻辑不必全盘推翻，但视觉、显示项对齐、饱满 HUD 风格需实现 |
| **左侧 7 阶段导航** | 44px宽，圆形图标，hover悬浮名称，已执行/当前/未解锁三态 | 176px宽，文本条目，三态已实现 | **高** | 宽度和视觉差异太大，建议重建 |
| **中央阶段业务区** | 象牙白桌面 + 阶段徽章 + 阶段标题描述 + 子步骤引导条 + 羊皮纸事务卡 | 深色背景 + 阶段公告头 + 阶段容器 | **高** | 核心区域差异最大：颜色体系、卡片质感、信息组织方式完全不同 |
| **右侧状态/日志区** | 深色外壳 + 派系资源卡片 + 权限提示 + 结构化日志 | 深色表面 + 资源瓦片 + 日志 + 流程按钮 | **中** | 布局概念一致，视觉对齐即可 |
| **底部查询/操作栏** | 深朱红饱满 HUD 12 按钮，均分填满 | 深色表面 12 按钮，4 个已连接 | **低-中** | 按钮逻辑完全可复用；视觉改色、高度填满 |
| **Modal / 弹窗** | 深朱红标题栏 + 羊皮纸内容区 + 铜金边框 | 灰调弹窗（ConfirmDialog / QueryResultOverlay） | **中** | 视觉对齐 |
| **表格 / 列表 / 卡片** | 羊皮纸质感卡片 + 铜金强调边框 | 扁平卡片 + 灰调边框 | **中** | 视觉对齐 |
| **disabled / empty / error 状态** | 灰度不可用 + 明确 disabled_reason | 部分实现（disabled_reason 从 Store 获取） | **低** | 已有 disabled_reason 链路，只需前端补齐视觉呈现 |

### 4.2 差距等级分布

| 等级 | 数量 | 影响区域 |
|---|---|---|
| **高** | 3 | 阶段导航、中央业务区、阶段子页面 |
| **中** | 5 | 顶栏、右侧栏、弹窗、表格卡片、disabled 状态 |
| **低** | 1 | 底部查询栏 |

### 4.3 功能差距

除了视觉差距外，当前实现的功能覆盖：

| 阶段 | v3.25.1 功能 | 当前实现 | 差距 |
|---|---|---|---|
| 天命 | 执行天命 → 展示事件 → 推进 | ✅ 完全实现 | 无 |
| 收入 | 国家收支 / 派系财政 / 地主收益 → 确认结算 | ❌ placeholder | 需 API + QML |
| 广场 | 解雇 / 人才市场（招募/竞标/凯旋等） | ❌ placeholder | 需 API + QML |
| 人口 | 庆典赞助 / 投票选举 / 结算 | ✅ 完全实现 | 无 |
| 元老院 | 提案 → 表决 → 保民官否决 | ⚠️ 只读 | 需交互功能 |
| 战争 | 多战争面板 / 军力对比 / 战斗 / 和约 | ❌ placeholder | 需 API + QML |
| 决算 | 总督轮换 / 革命检查 | ❌ placeholder | 需 API + QML |
| 底部查询 | 12 按钮，4 个已连接 | ✅ 4/12 已实现 | 8 个 placeholder |

---

## 5. 架构风险检查

| 检查项 | 是否存在 | 证据文件/位置 | 风险说明 | 建议 |
|---|---|---|---|---|
| GUI 调用 CLI Command | ❌ **否** | 测试 `test_opc_shell_boundary_and_i18n_scans` 已验证 | 无风险 | — |
| GUI 直接读写 Core 私有字段 | ❌ **否** | 同上；所有数据通过 Store Property + API DTO 获取 | 无风险 | — |
| GUI 复制核心业务规则 | ❌ **否** | 同上；无 `CombatCommand`/`phase_senate` 等引用 | 无风险 | — |
| GUI 根据中文文本判断逻辑 | ❌ **否** | 测试已验证 QML 中的文案全部通过 `GuiText` 引用，无散落中文 | 无风险 | — |
| GUI 自行推断权限 | ❌ **否** | 权限由 `session_api` 按 `viewer_player_id` 过滤，GUI 消费 `is_current_player`/`can_vote`/`can_campaign` 等布尔属性 | 无风险 | — |
| GUI 暴露隐藏玩家信息风险 | ❌ **否** | `session_api.get_session_snapshot` 按 viewer 过滤；其他派系金库不返回 | 无风险 | — |
| Adapter 返回结构不稳定 | ⚠️ **部分有** | `gui_query_api.get_global_query_result` 对未实现查询返回占位 DTO；Adapter 有 fallback | 低 | 新建阶段 API 时应保持 DTO 格式一致 |
| disabled reason 缺失 | ⚠️ **部分有** | Store 中 `disabled_reason` 已实现；但 QML 前端仅 MortalityStage 使用；其他阶段页面未展示 | 低 | 新 QML 应统一消费 `summary.disabled_reason` |
| empty/error 状态缺失 | ⚠️ **部分有** | `EmptyState.qml` 组件已存在但未在所有阶段页面中使用 | 低 | 新阶段页面应统一使用 |

### 结论

**当前架构风险极低。** 代码层严格遵守了架构边界。所有风险点均为前端视觉呈现层面的缺失，不影响 Core/API 安全。

---

## 6. 推荐路线：**B**

> **保留启动入口、Adapter、Store 等连接层，重建 QML 页面与组件。**

### 理由

1. **Python 连接层零问题。** 代码审计确认 `GuiApp`、`GuiSessionStore`、`GuiApiAdapter` 完全可复用。它们遵循正确的架构边界，与 API/Core 完全解耦。

2. **当前 QML 视觉与 v3.25.1 差距过大，不值得修补。** 差距分析显示：
   - 阶段导航宽度差 4 倍（176px vs 44px），图标 vs 文字 — 必须从零重建
   - 中央区的颜色体系、卡片风格、信息层级完全不同 — 修补成本 ≈ 重建成本
   - 所有阶段页面（Mortality/Population/Senate）的 QML 如果只改色，仍然不是"羊皮纸卡片在象牙白桌面上"的视觉

3. **复用成本极低。** app/store/adapter 零修改即可在新 QML 中继续使用。新 QML 只需保持相同的 `sessionStore` property/slot 接口约定。

4. **测试可保护。** 现有 `test_qml_startup.py` 可更新 `objectName` 断言后继续作为 QML 加载保护；`test_adapter.py` 和 `test_session_api.py` 完全无需修改。

### 为什么不选 A 或 C

- **不选 A（局部改造）**：视觉差距太大。修补旧 QML 到 v3.25.1 标准涉及的颜色/宽度/卡片/质感改动，本质上是一次重写。在旧文件上修补会产生技术债务。
- **不选 C（整体重建）**：Python 连接层干净且无风险。整体重建意味着丢掉已经验证的 Store/Adapter/API 集成逻辑，纯属浪费。

### 注意事项

- 重建 QML 时需**保持 `sessionStore` Property 和 Slot 接口不变**（`sessionStore.selectedPhaseId`, `sessionStore.doExecuteMortality()`, `sessionStore.doGlobalQuery()` 等）
- `Theme.qml` 的 color 值需按 v3.25.1 色彩规范重新定义
- 现有测试 `test_opc_shell_boundary_and_i18n_scans` 中的 `objectName` 断言需要在重建后更新

---

## 7. 风险与决策阻塞信息

### 已确认无阻塞项

| 潜在阻塞 | 状态 | 说明 |
|---|---|---|
| Adapter 功能不足 | ✅ 不阻塞 | 现有 Adapter + API 层已覆盖人口/天命完整交互 + 元老院只读 + 4 个查询 |
| Store 接口不完整 | ✅ 不阻塞 | 18 个 Property + 8 个 Slot，足够支撑新 Shell |
| 架构违规 | ✅ 不阻塞 | 零违规 |
| 测试缺失 | ✅ 不阻塞 | 3 套 GUI 测试均可复用 |

### 待确认项（非阻塞，但后续需回答）

1. **收入/广场/战争/决算的 API 状态** — 审计指令要求不推断，需后续 Mapping Matrix 确认
2. **Senate 的交互式操作 API** — 当前为 readonly，后续 `GUI-P0-02C` 需确认
3. **BottomQueryBar 余下 8 个查询的 backend 状态** — 当前为 placeholder，需 DTO Gap Report
4. **v3.25.1 HTML 原型中是否有新增的 API 需求** — 需后续 Mapping Matrix 逐元素检查
5. **多玩家交接逻辑在 QML 侧是否完整** — PlayerHandoffOverlay 存在但需在重建中验证

---

## 8. 第一阶段建议任务

按 Codex 推荐的开发顺序，Phase 0 (Mapping & Gap) 先于 Phase 1 (Global Shell)：

### Phase 0 — Mapping & Gap Analysis（优先级：P0）

| 任务 | 输出物 | 预估 |
|---|---|---|
| 0.1 GUI_CONTROL_MAPPING_MATRIX | 逐元素对照 v3.25.1 vs API | ~3h |
| 0.2 GUI_DTO_GAP_REPORT | DTO 缺口分析 | ~2h |
| 0.3 GUI_PHASE_INTEGRATION_PLAN | 阶段实施路线图 | ~1h |

### Phase 1 — 新 Shell 重建（优先级：P1）

| 顺序 | 组件 | 复用策略 | 难度 |
|---|---|---|---|
| 1.1 | Theme.qml 配色更新 → v3.25.1 色彩体系 | 修改颜色值 | 低 |
| 1.2 | PhaseRail.qml 重建 → 44px 圆形图标 | 同一 Store 接口 | 中 |
| 1.3 | TopStatusBar.qml 重建 → 饱满深朱红 HUD | 同一 Store 接口 | 中 |
| 1.4 | GameShell.qml 视觉更新 → 引用新 Theme | 修改颜色值+间距 | 低 |
| 1.5 | BottomQueryBar.qml 视觉更新 → 深朱红饱满 HUD | 修改颜色值+高度 | 低 |
| 1.6 | ContextPanel.qml 视觉更新 → 羊皮纸风格 | 修改颜色值+质感 | 低 |
| 1.7 | FeedbackPanel / HandoffOverlay / QueryResultOverlay 视觉更新 | 修改颜色值 | 低 |

### Phase 2 — 一个阶段 Vertical Slice（P1）

推荐选择**天命阶段**作为第一个 Vertical Slice，因为：
- 功能最简单（单事件 → 读取展示）
- API 已完整（`mortality_api` ✅）
- Adapter 已封装（`execute_mortality` / `advance_mortality` ✅）
- 可快速验证新组件体系

### Phase 3 — 逐阶段扩展（P2）

天命 → 人口（已有 API）→ 元老院（只读已有，交互需后续）→ 收入/广场/战争/决算

---

## 9. 建议测试保护线

### 当前测试状态

| 测试类型 | 当前是否存在 | 建议保留/新增 | 用途 |
|---|---|---|---|
| GUI 启动测试 | ✅ `test_qml_startup.py` (6 tests) | **保留并更新** | 确保新 QML 能成功加载，所有 objectName 可达 |
| Adapter 测试 | ✅ `test_adapter.py` (6 tests) | **保留** | 验证 Adapter 调用 → API → 反馈链完整 |
| Session API 测试 | ✅ `test_session_api.py` (10 tests) | **保留** | 验证 DTO 结构完整、viewer 过滤正确、阶段导航正确 |
| GUI Query API 测试 | ✅ `test_gui_query_api.py` | **保留** | 验证 4 个已连接查询的 DTO 结构 |
| i18n/QML 文字测试 | ✅ 嵌入 `test_qml_startup.py` | **保留并更新** | 检查新 QML 无散落中文硬编码 |

### 重建期最低保护线

| 阶段 | 必须通过的测试 | 说明 |
|---|---|---|
| Phase 0 (Mapping) | 全部现有测试 | 不改代码，测试应全部通过 |
| Phase 1 (Shell) | `test_qml_startup.py` (更新后) + `test_session_api.py` | 确保新 Shell 加载成功 + 数据流正常 |
| Phase 2 (Vertical Slice) | 全部现有测试 + 新 MigrationSlice 测试 | 确保新阶段页面与 Store 集成正确 |
| Phase 3 (逐阶段扩展) | 全部测试 + 每阶段新增 slice 测试 | 增量保护 |

### 建议新增测试

| 测试类型 | 建议时机 | 用途 |
|---|---|---|
| Vertical Slice 端到端测试 | Phase 2 | 模拟单阶段完整操作流程（API → Store → QML render） |
| 多玩家交接测试 | Phase 2 | 验证 PlayerHandoffOverlay + switchViewer 流程 |
| 主题色一致性测试 | Phase 1 | 自动检查 QML 中使用已定义的 Theme 属性 vs 硬编码颜色 |

---

## 附录 A：参考资料

| 类型 | 路径 | 用途 |
|---|---|---|
| ✅ 审计指令 | `docs/.../GUI需求/OC_GUI_v3.25.1_重建可行性审计指令_2026-07-10.md` | 本任务依据 |
| ✅ 目标原型 | `docs/.../GUI需求/EOR_GUI_Prototype_v3.25.1.html` | 视觉参考（2446 行） |
| ✅ 设计规范 | `docs/.../GUI需求/EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md` | 色彩/材质/验收标准 |
| ✅ Codex 交接 | `docs/.../GUI需求/EOR_GUI_Codex_Handover_2026-07-10.md` | Mapping Matrix 方法论 |
| ✅ GUI 设计文档 | `docs/.../GUI需求/EOR_GUI设计文档.md` | 旧设计规范参考 |
| ✅ API 映射 | `docs/.../GUI需求/EOR_UI_API_Mapping.md` | 旧 API 映射参考 |
| ✅ 代码对齐审计 | `docs/.../GUI需求/GUI_Code_Alignment_Audit.md` | 旧审计参考 |
| ✅ 代码实现 | `src/ui/gui/` | 当前 GUI 全部代码 |

*注：文档路径前缀均为 `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/`*

---

## 附录 B：当前资源占用

| 层面 | 文件数 | 总行数 | 重建影响 |
|---|---|---|---|
| Python 连接层 (app/store/adapter) | 3 | ~650 | 零修改 |
| Python 本地化 | 1 | 73 | 零修改 |
| Python 模型/控制器 | 5 | ~200 | 可选保留 |
| QML Theme/i18n | 2 | ~250 | 改色（Theme）+ 扩键（GuiText） |
| QML Shell | 8 | ~700 | 重建视觉 |
| QML Stages | 6 | ~690 | 重建 |
| QML Components | 8 | ~460 | 改色 |
| 测试 | 3 | ~400 | 保留并更新 |
| **总计** | **~36** | **~3400** | |

---

*报告完 — 奥古斯都（OC）| 2026-07-10*
