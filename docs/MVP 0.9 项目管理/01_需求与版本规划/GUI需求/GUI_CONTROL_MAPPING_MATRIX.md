# GUI 控件/API 映射矩阵 — Shell 外壳

> 文件 1/3 | 2026-07-10 | 代码基准: `main` (65bbf67)
> 完成轮次: 1/7

---

## 区域 A: 顶栏 (TopBar)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|------------|--------|------|---------------|-------------|-----------|---------------|--------|------------|----------------|-------------|----------------|-------------|-------------|----------------|----------------------|----------|
| A1 | Logo "🏛️ EAGLE OF ROME · SPQR" | TopBar | Static Text | 游戏标题+SPQR 副标 | N/A (Hardcoded) | N/A | N/A | None | 总是显示 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Reuse | `v3.25.1.html:1111`, `TopStatusBar.qml:27-36` |
| A2 | 国库数值 (#hTreasury) | TopBar | Read-only | 国库金额 (142 T) | `Store.treasury` | `public_resources.treasury` | `session_api:get_session_snapshot` → `_build` | None (只读) | 总是 | 对所有玩家公开 | 总是 | N/A | 0 | Transport error → 0 | Existing | Reuse (style update) | `session_store.py:82`, `session_api.py:119` |
| A3 | 派系金库数值 (#hFaction) | TopBar | Read-only | 本派系金库 (12 T) | `Store.factionTreasury` | `faction_resources.treasury` | `session_api:get_session_snapshot` → `_build` | None (只读) | 总是 | 仅本派系可见 | 总是 | N/A | 0 | Transport error → 0 | Existing | Reuse (style update) | `session_store.py:88`, `session_api.py:132-134` |
| A4 | 影响力数值 (#hInf) | TopBar | Read-only | 本派系总影响力 (68) | `Store.factionInfluence` | `faction_resources.total_influence` | 同上 | None (只读) | 总是 | 仅本派系可见 | 总是 | N/A | 0 | Transport error → 0 | Existing | Reuse (style update) | `session_store.py:93`, `session_api.py:136` |
| **A5** | **稳定度 (#hStab)** | **TopBar** | **Read-only** | **稳定度百分比 (78%)** | **N/A** | **N/A** | **N/A** | **None** | **N/A** | **N/A** | **N/A** | **N/A** | **Hide element** | **Hide element** | **Backend Gap** | **Deferred** | **`v3.25.1.html:1117`; GameState 无 stability 字段** |
| **A6** | **战争数 (#hWar)** | **TopBar** | **Read-only** | **活跃战争数 (1)** | **Store 无此 Property** | **需新增** | **可用 `senateView.summary.active_foreign_war_count`** | **None** | **总是** | **对所有玩家公开** | **总是** | **N/A** | **0** | **Transport error → 0** | **DTO Gap (Store Property 缺, 但后端数据存在)** | **Phase 1 新增** | **`senate_view.py:93` 有 active_foreign_war_count; Store 未暴露** |
| A7 | 回合/年信息 (#roundInfo) | TopBar | Read-only | "282 BC · 回合 1" | `Store.yearDisplay` + `Store.turnNumber` | `public_resources.year_display`, `turn_number` | 同上 | None (只读) | 总是 | 公开 | 总是 | N/A | 默认值: "" + 0 | Transport error → 默认值 | Existing | Reuse (style update) | `session_store.py:77,82`, `TopStatusBar.qml:44-49` |
| A8 | 当前玩家/派系 | TopBar | Read-only | "player1 / Optimates" | `Store.viewerFactionName` + `Store.currentPlayerId` | `faction_resources.name`, `current_player_id` | 同上 | None | 总是 | 仅当前 viewer | 总是 | N/A | 默认文本 | Transport error → 默认文本 | Existing | Reuse (style update) | `session_store.py:123`, `TopStatusBar.qml:72-77` |

---

## 区域 B: 左侧阶段导航 (PhaseRail)

`v3.25.1` HTML 使用 44px 宽圆形图标 (+ hover 名称)；当前 QML 使用 176px 宽文本条目。

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|------------|--------|------|---------------|-------------|-----------|---------------|--------|------------|----------------|-------------|----------------|-------------|-------------|----------------|----------------------|----------|
| B1 | 阶段圆形图标 (7×) | PhaseRail | Action | 图标(🎴💰🏛️⚖️🏺⚔️📊) | `Store.phaseNavigation[].id` | `phase_navigation[].id` | 同上 | 点击切换阶段 | 总是 | 所有玩家 | 当前/已完成可查; 占位阶段显示 disabled_reason | 未接入阶段: "后续任务承接" | 7 个图标始终显示 | Transport → 仅图标无文字 | Existing (id 存在) | Rebuild (44px 圆形图标替代 176px 文本) | `v3.25.1.html:1125-1132`; `PhaseRail.qml` |
| B2 | 阶段 hover 名称 | PhaseRail | Read-only | "天命","收入"等 | N/A (从 Store 取) | `phase_navigation[].name` | N/A | 无 | hover 时 | 公开 | 总是 | N/A | N/A | N/A | Existing | Rebuild | `v3.25.1.html:1126 ".rl"` |
| B3 | 阶段状态 (done/current/todo) | PhaseRail | State Indicator | 已完成/当前/未解锁 | `Store.phaseNavigation[].executed, .current, .implemented` | `phase_navigation[].executed, .current` | 同上 | 无 | 总是 | 公开 | 总是 | N/A | 无状态 => todo | Transport → 全部 todo | Existing | Rebuild (视觉更新) | `PhaseRail.qml:32-38` `session_api.py:412-437` |
| B4 | 阶段高亮 (当前选中) | PhaseRail | State Indicator | 铜金边框+阴影 | `Store.selectedPhaseId` | `selected_phase_id` | 同上 | 无 | 总是 | 公开 | 总是 | N/A | 无 | Transport → 默认 | Existing | Rebuild | `PhaseRail.qml:33-35` |
| B5 | 刷新状态按钮 | PhaseRail | Action | "刷新状态" | N/A | N/A | `Store.refreshSnapshot()` | 点击刷新 | 总是 | 总是 | 总是 | N/A | N/A | 失败→feedback | Existing | Reuse | `PhaseRail.qml:78` |
| B6 | 阶段说明按钮 | PhaseRail | Action | "阶段说明" | N/A | N/A | `Store.logUiEvent()` | 点击记录事件 | 总是 | 总是 | 总是 | N/A | N/A | N/A | Existing | Reuse | `PhaseRail.qml:84` |

---

## 区域 C: 右侧面板 (ContextPanel)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|------------|--------|------|---------------|-------------|-----------|---------------|--------|------------|----------------|-------------|----------------|-------------|-------------|----------------|----------------------|----------|
| C1 | 当前阶段标题 | ContextPanel | Read-only | "当前阶段" + 描述文本 | `Store.selectedPhaseSummary` | `selected_phase_summary` | 同上 | 无 | 总是 | 公开 | 总是 | N/A | "尚未迁移"等 | Transport→默认描述 | Existing | Reuse (style update) | `ContextPanel.qml:51-68`, `session_api.py:454-510` |
| C2 | 推进到下一阶段按钮 | ContextPanel | Action | "⏭️ 推进到下一阶段" | N/A | N/A | 当前无通用 `advancePhase` Slot | 点击推进 | **仅当前阶段可推进** | 仅当前玩家 | **依赖: 当前玩家+可推进状态** | **Store 无通用 canAdvance 属性** | 隐藏/disabled | Transport→disabled | **Adapter Gap** (已有 advance_mortality 但无通用 advancePhase) | Phase 1 新增通用 Slot | `v3.25.1.html:1788` |
| C3 | 进度指示 (x/y) | ContextPanel | Read-only | "流程 4/4" | `Store.phaseNavigation[].executed` + 子步骤计数 | 无子步骤计数 | N/A | 无 | 总是 | 公开 | 总是 | N/A | "0/0" | Transport→"0/0" | **DTO Gap** (无子步骤计数字段) | Phase 2 新增 | `v3.25.1.html:1793` |
| C4 | 状态标签 | ContextPanel | Read-only | "可操作"/"只读"/"占位" | `Store.selectedPhaseSummary.status_text` | `selected_phase_summary.status_text` | 同上 | 无 | 总是 | 公开 | 总是 | N/A | "后续任务承接" | Transport→"未知" | Existing | Reuse (style update) | `session_store.py:294-308` |
| C5 | 派系名 | ContextPanel | Read-only | "Optimates" | `Store.viewerFactionName` | `faction_resources.name` | 同上 | 无 | 总是 | 仅本派系 | 总是 | N/A | "" | Transport→"" | Existing | Reuse | `ContextPanel.qml:85` |
| C6 | 人物数 | ContextPanel | Read-only | "5 人" | `Store.factionMemberCount` | `faction_resources.member_count` | 同上 | 无 | 总是 | 仅本派系 | 总是 | N/A | "0 人" | Transport→"0 人" | Existing | Reuse | `ContextPanel.qml:52-55` |
| C7 | 事件日志 | ContextPanel | Read-only | 事件条目列表 | `Store 无日志记录` | N/A | N/A | 无 | 总是 | 公开 | 总是 | N/A | 空日志区 | N/A | **Decision Needed**: 日志是 QML 本地状态(FeedbackPanel)还是从 Store 获取? 当前 FeedbackPanel 是本地队列 | 保留现有 | `ContextPanel.qml:93` 引用 feedbackPanel |
| C8 | 清空日志按钮 | ContextPanel | Action | "清空" | N/A | N/A | 本地 QML 操作 | 点击清空 | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing (QML 本地) | Reuse | `FeedbackPanel.qml` |

---

## 区域 D: 底部操作栏 (BottomBar)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|------------|--------|------|---------------|-------------|-----------|---------------|--------|------------|----------------|-------------|----------------|-------------|-------------|----------------|----------------------|----------|
| D1 | 操作栏标题/背景 | BottomBar | Static | 深朱红栏位 | N/A | N/A | N/A | 无 | 总是 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (视觉改色) | `v3.25.1.html:1811-1823` |
| D2 | 📋派系信息按钮 | BottomBar | Action | "派系信息" | N/A | N/A | `Store.doGlobalQuery("faction_info")` | 点击→显示弹窗 | 总是 | 玩家可查本派系; 其他派系仅公开摘要 | 总是 (readonly) | N/A | 查询结果弹窗显示"暂无记录" | API 异常→显示错误 | Existing (Adapter 已封装, API 已实现) | Reuse | `gui_query_api.py:130-168`, `BottomQueryBar.qml`, `test_gui_query_api.py` |
| D3 | 👤人物查询按钮 | BottomBar | Action | "人物查询" | N/A | N/A | `Store.doGlobalQuery("figure_search")` | 点击→显示弹窗 | 总是 | 需 viewer 权限 | 总是 | "GUI-P0-03G 后续任务承接" | 弹窗显示 placeholder 信息 | API 异常→显示错误 | Deferred Placeholder | 保留 placeholder | `gui_query_api.py:211-218` handlers 中无 figure_search |
| D4 | 📊游戏状态按钮 | BottomBar | Action | "游戏状态" | N/A | N/A | `Store.doGlobalQuery("game_status")` | 点击→显示弹窗 | 总是 | 公开 | 总是 | N/A | 显示公开摘要 | API 异常→显示错误 | Existing | Reuse | `gui_query_api.py:93-127` |
| D5 | 💰派系金库按钮 | BottomBar | Action | "派系金库" | N/A | N/A | `Store.doGlobalQuery("faction_treasury")` | 点击→显示弹窗 | 总是 | **仅本派系可见详情** | 总是 | "GUI-P0-03G 后续任务承接" | placeholder | API 异常→显示错误 | Deferred Placeholder | 保留 placeholder | 同上 |
| D6 | 🌾公地信息按钮 | BottomBar | Action | "公地信息" | N/A | N/A | `Store.doGlobalQuery("public_land")` | 同上 | 总是 | 公开 | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |
| D7 | 🏡私地信息按钮 | BottomBar | Action | "私地信息" | N/A | N/A | `Store.doGlobalQuery("private_land")` | 同上 | 总是 | 仅本派系可见 | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |
| D8 | 📦合同状态按钮 | BottomBar | Action | "合同状态" | N/A | N/A | `Store.doGlobalQuery("contract_status")` | 同上 | 总是 | 公开? (需确认) | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |
| D9 | 🏛️行省信息按钮 | BottomBar | Action | "行省信息" | N/A | N/A | `Store.doGlobalQuery("province_info")` | 同上 | 总是 | 公开? (需确认) | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |
| D10 | ⚔️战争列表按钮 | BottomBar | Action | "战争列表" | N/A | N/A | `Store.doGlobalQuery("war_list")` | 点击→显示弹窗 | 总是 | 公开 | 总是 | N/A | 公开战争列表 | API 异常→显示错误 | Existing | Reuse | `gui_query_api.py:181-218` |
| D11 | 🗡️军团状态按钮 | BottomBar | Action | "军团状态" | N/A | N/A | `Store.doGlobalQuery("legion_status")` | 点击→显示弹窗 | 总是 | 公开 | 总是 | N/A | 公开军团列表 | API 异常→显示错误 | Existing | Reuse | `gui_query_api.py:224-262` |
| D12 | ⚓舰队状态按钮 | BottomBar | Action | "舰队状态" | N/A | N/A | `Store.doGlobalQuery("fleet_status")` | 同上 | 总是 | 公开? | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |
| D13 | ❓帮助按钮 | BottomBar | Action | "帮助" | N/A | N/A | `Store.doGlobalQuery("help")` | 同上 | 总是 | 公开 | 总是 | placeholder | placeholder | placeholder | Deferred Placeholder | 保留 | 同上 |

---

## 区域 E: Modal / Overlay

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|------------|--------|------|---------------|-------------|-----------|---------------|--------|------------|----------------|-------------|----------------|-------------|-------------|----------------|----------------------|----------|
| E1 | 模态框遮罩 | Modal | Static | 半透明深色遮罩 | N/A | N/A | N/A | 点击遮罩关闭 | 总是 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (视觉对齐) | `v3.25.1.html:150-159, 1824` |
| E2 | 模态框标题 (#mTitle) | Modal | Read-only | 查询或操作标题 | `Store.globalQueryResult.title` 或调用方提供 | `result.title` | `Store.doGlobalQuery()` 返回 | 无 | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse (style update) | `QueryResultOverlay.qml` |
| E3 | 模态框关闭按钮 | Modal | Action | "×" | N/A | N/A | 本地 QML 操作 | 点击关闭 | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | `QueryResultOverlay.qml` |
| E4 | 模态框内容区 (#mBody) | Modal | Read-only | 查询或操作详情 | `Store.globalQueryResult.items` + `summary` | `result.items[]` | `Store.doGlobalQuery()` 返回 | 无 | 总是 | 公开或 viewer 受限 (依赖查询类型) | 总是 | N/A | "暂无记录" | 显示错误消息 | Existing (4 queries) | Reuse (style update) | `SessionStore.globalQueryResult`, `QueryResultOverlay.qml` |
| E5 | 行内 modal 确认/关闭按钮 | Modal | Action | "确认" "关闭" | N/A | N/A | 调用方回调 | 点击→确认/关闭 | 阶段相关 | 阶段相关 | 阶段相关 | 阶段相关 | N/A | N/A | Existing (ConfirmDialog) | Reuse (style update) | `ConfirmDialog.qml` |
| E6 | 玩家交接遮罩 | Overlay | Read-only/Action | 玩家切换提示 | `Store` handoff 信号 | N/A | `Store.switchViewer()` | 确认交接 | 所有阶段可能 | 仅当前玩家 | 收到 `handoffRequired` 信号时 | N/A | N/A | N/A | Existing | Reuse | `PlayerHandoffOverlay.qml` |

---

## 汇总

| 状态 | Shell 外壳数量 | 说明 |
|------|---------------|------|
| Existing (fully reusable) | 19 | A1,A2,A3,A4,A7,A8,B5,B6,C4,C5,C6,C8,D2,D4,D10,D11,E2,E3,E5 |
| 🟡 Reuse + style update | 10 | B3,B4,C1,D1,E1,E4,E6 等 |
| 🔴 Rebuild | 3 | B1,B2 (PhaseRail 圆形图标), D1 (底部栏视觉) |
| 🔵 New in Phase 1 | 2 | A6 (战争数 Store Property), C2 (通用 advancePhase Slot) |
| ⚪ DTO Gap | 2 | A6 (Store 缺 warCount), C3 (缺子步骤计数) |
| ⚫ Backend Gap | 1 | A5 (稳定度 — 后端无此字段) |
| ⬜ Deferred Placeholder | 8 | D3,D5,D6,D7,D8,D9,D12,D13 (查询按钮) |
| ❓ Decision Needed | 1 | C7 (日志系统: Store 管理 vs QML 本地) |

---

## 未确认事项

0. **C2/H15: 通用 advancePhase Slot** — Codex 建议推迟到 Phase 2+，不阻塞 Phase 1 新 Shell + 天命 Vertical Slice。天命阶段继续使用现有 doAdvanceMortality()。

1. **A5: 稳定度是否重新引入？** 当前 GameState 无 stability 字段。v3.25.1 展示 78% 但后端不支持。需决定: (a) 从顶栏移除; (b) 后端新增; (c) 从现有数据推导。
2. **C7: 日志存储在哪？** 当前 FeedbackPanel 是 QML 本地队列，不经过 Store。新 Shell 是否改为 Store 统一管理？需确认。
3. **C2: 通用 advancePhase Slot 的设计？** 当前 Store 只有 `doAdvanceMortality()` (天命专用)。通用推进需新增: `canAdvance`, `doAdvancePhase()`。

---

*审计执行人: 奥古斯都 (OC)*  
*审计日期: 2026-07-10*  
*代码基准: `main` (65bbf67)*  
*完成轮次: 1/7 — Shell 外壳 (顶栏/导航/右侧栏/底部栏/弹窗)*  

---

## 区域 F: 天命阶段 (Mortality − CenterStage)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F1 | 阶段徽章 "1 / 7" | CenterStage | Static Text | "1 / 7" | `Store.phaseNavigation[0].index` | `phase_navigation[0].index` | `session_api._build_phase_navigation` 中的 index | None | 总是显示 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse (视觉更新) | `v3.25.1.html:1140`, `session_api.py:412` index=1 |
| F2 | 阶段标题 "🎴 天命阶段" | CenterStage | Static Text | 阶段名称 | `Store.selectedPhaseName` / `GuiText.mortalityTitle` | 静态文本或 `selected_phase_summary.name` | N/A | None | 总是显示 | 公开 | 总是 | N/A | "人口"等占位 | N/A | Existing | Reuse (视觉更新) | `v3.25.1.html:1141`, `MortalityStage.qml:23` |
| F3 | 阶段描述文字 | CenterStage | Static Text | "众神降下命运...无玩家操作" | `Store.selectedPhaseSummary.description` | `selected_phase_summary.description` | `session_api._build_phase_summary` | None | 总是显示 | 公开 | 总是 | N/A | "后续任务承接" | N/A | Existing | Reuse | `v3.25.1.html:1142`, `session_api.py:476` |
| F4 | 步骤引导条 (2 个步骤) | CenterStage | Static / State | 步骤1: 执行天命 → 步骤2: 查看事件结果 | 当前代码无此概念 | N/A | N/A | None | 总是显示 | 公开 | 总是 | N/A | 两步骤始终可见 | N/A | Pure Static UI Text (视觉元素，无后端依赖) | Rebuild (新增步骤条组件) | `v3.25.1.html:1143-1146`; 当前 QML 无步骤条 |
| F5 | 步骤 1 状态 "current" | CenterStage | State Indicator | 圆圈+图标 | 无步骤概念 | N/A | N/A | None | 执行前: 步骤1 current; 执行后: 步骤1 done | 公开 | 总是 | N/A | 全部 todo | N/A | Pure Static UI Text | Rebuild | `v3.25.1.html:1144` |
| F6 | 步骤 2 状态 "todo" / "current" | CenterStage | State Indicator | 同上 | 无步骤概念 | N/A | N/A | None | 执行前: todo; 执行后: current | 公开 | 总是 | N/A | 全部 todo | N/A | Pure Static UI Text | Rebuild | `v3.25.1.html:1146` |
| F7 | 信息框/事件展示区 (#mortalityView) | CenterStage | Read-only | 事件执行结果 | `Store.mortalityEvents` + `Store.mortalityResult` | `_mortality_result.data` events/impacts | `_adapter.get_mortality_view()` + `_adapter.execute_mortality()` | None (展示) | 仅天命阶段 | 公开 (天命结果所有人可见) | 总是 | N/A | "尚未执行天命"/"点击下方执行天命按钮" | API 失败→显示错误 | Existing (DTO + Adapter 完整) | Rebuild (视觉→羊皮纸卡片) | `MortalityStage.qml:54-108`, `mortality_api.py:execute_mortality_phase` |
| F8 | 事件卡片 — 事件名称 | CenterStage | Read-only | 事件名 e.g. "国泰民安" | `Store.mortalityEvents[].name` | `events[].name` | 同上 | None | 仅执行后显示 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild (视觉→羊皮纸) | `MortalityStage.qml:83` |
| F9 | 事件卡片 — 事件摘要 | CenterStage | Read-only | 事件描述 | `Store.mortalityEvents[].summary` | `events[].summary` | 同上 | None | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild | `MortalityStage.qml:89` |
| F10 | 事件卡片 — 影响项列表 | CenterStage | Read-only | 死亡/增益/灾害等影响 | `Store.mortalityEvents[].impacts[]` | `events[].impacts[].type/.figure_name/.province_name` 等 | 同上 | None | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild (视觉→羊皮纸) | `MortalityStage.qml:93-107`, `GuiText.qml:mortalityImpactText` |
| F11 | 影响项 — 人物死亡 | CenterStage | Read-only | "死亡: Sextilis" | `impact.type="figure_death"`, `impact.figure_name` | 同上 | 同上 | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild | `GuiText.qml:mortalityImpactText` |
| F12 | 影响项 — 英雄登场 | CenterStage | Read-only | "英雄登场: Marcus Furius" | `impact.type="hero_spawn"`, `impact.name`, `impact.subtype` | 同上 | 同上 | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild | 同上 |
| F13 | 影响项 — 灾害 | CenterStage | Read-only | "灾害: 意大利 损失 40%" | `impact.type="disaster"`, `impact.province_name`, `impact.loss_ratio` | 同上 | 同上 | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild | 同上 |
| F14 | 影响项 — 民怨 | CenterStage | Read-only | "民怨: 意大利 0 → 1" | `impact.type="province_grievance"` | 同上 | 同上 | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | Existing | Rebuild | 同上 |
| F15 | 影响项 — 战争威胁 | CenterStage | Read-only | "战争威胁: ..." | `impact.type="war_threat"` | 同上 | 同上 | 同上 | 公开 | 事件存在 | N/A | N/A | N/A | **Decision Needed**: API 是否返回 war_threat 类型? | Rebuild | 同上 |
| F16 | **⚡ 执行天命按钮** | CenterStage | Action | "⚡ 执行天命" | N/A | N/A | `Store.doExecuteMortality()` → `Adapter.execute_mortality()` → `mortality_api.execute_mortality_phase()` | 点击→执行天命 | 必须在天命阶段 | 必须是当前玩家 | `canExecuteMortality == true` | "不是当前玩家" / "天命已执行" | 按钮隐藏/disabled | API 失败→feedback | Existing (完整 API 链) | Reuse (视觉更新) | `MortalityStage.qml:115`, `session_store.py:186-198`, `mortality_api.py:50-77` |
| F17 | **📜 进入收入阶段按钮** | CenterStage | Action | "进入收入阶段" / "📜 查看事件结果" | N/A | N/A | `Store.doAdvanceMortality()` → `Adapter.advance_mortality()` → `mortality_api.advance_mortality_phase()` | 点击→推进到下一阶段 | 必须在天命阶段且已执行 | 必须是当前玩家 | `canAdvanceMortality == true` | "天命尚未执行" / "不是当前玩家" | 按钮隐藏/disabled | API 失败→feedback | Existing (完整 API 链) | Reuse | `MortalityStage.qml:122`, `session_store.py:201-226`, `mortality_api.py:80-110` |
| F18 | disabled_reason 文本 | CenterStage | Static Text | 禁用原因 | `Store.selectedPhaseSummary.disabled_reason` | `selected_phase_summary.disabled_reason` | `session_api._build_phase_summary` | None | 按钮禁用时 | 公开 | 总是 | N/A | "" | N/A | Existing | Reuse | `MortalityStage.qml:130-136` |
| F19 | 状态标签 (准备/已执行) | CenterStage | State Indicator | "准备执行天命" / "天命已执行" | `Store.canExecuteMortality` | `mortality_view.can_execute` | `_adapter.get_mortality_view()` | None | 仅天命阶段 | 公开 | 总是 | N/A | "准备执行天命" | N/A | Existing | Reuse (视觉更新) | `MortalityStage.qml:32` |

---

## 区域 G: 收入阶段 (Revenue − CenterStage)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G1 | 阶段徽章 "2 / 7" | CenterStage | Static Text | "2 / 7" | Store phaseNavigation index | `phase_navigation[].index` | session_api._build_phase_navigation | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | v3.25.1.html:1158 |
| G2 | 阶段标题 "💰 收入阶段" | CenterStage | Static Text | "收入阶段" | Store.currentPhaseName | `selected_phase_summary.name` | session_api | None | 总是 | 公开 | 总是 | N/A | "收入" | N/A | Existing | Reuse | v3.25.1.html:1159 |
| G3 | 阶段描述文字 | CenterStage | Static Text | "年度财政结算..." | Store.selectedPhaseSummary.description | `selected_phase_summary.description` | session_api._build_phase_summary | None | 总是 | 公开 | 总是 | N/A | "后续任务承接" | N/A | Existing | Reuse | v3.25.1.html:1160 |
| G4 | 步骤引导条 (2 步骤) | CenterStage | State/Indicator | 步骤1: 查看收支明细 → 步骤2: 确认收入 | 无步骤概念 | N/A | N/A | None | 总是显示 | 公开 | 总是 | N/A | 两步骤始终可见 | N/A | Pure Static UI Text (视觉元素) | Rebuild (步骤条组件) | v3.25.1.html:1161-1165 |
| G5 | 📈 国家收入副标题 | CenterStage | Static Text | "📈 国家收入" | N/A | N/A | N/A | None | 仅收入阶段 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Reuse | v3.25.1.html:1169 |
| G6 | 国家公地收益行 | CenterStage | Read-only | "国家公地收益 +60 T" | N/A | 无 DTO | N/A | None | 仅收入阶段 | 公开 | 阶段激活时 | "收入阶段尚未迁移" | 隐藏该区域 | N/A | API Missing | Deferred | v3.25.1.html:1170; 无 revenue API |
| G7 | 战争赔款收入行 | CenterStage | Read-only | "战争赔款收入 +0 T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1171 |
| G8 | 行省税收入行 | CenterStage | Read-only | "行省税收入 +XX T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1172 |
| G9 | 其他收入行 | CenterStage | Read-only | "合同/商税 +XX T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1173 |
| G10 | 📉 国家支出副标题 | CenterStage | Static Text | "📉 国家支出" | N/A | N/A | N/A | None | 同上 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Reuse | v3.25.1.html:1174 |
| G11 | 军团维护费行 | CenterStage | Read-only | "军团维护费 -0 T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1175 |
| G12 | 舰队维护费行 | CenterStage | Read-only | "舰队维护费 -0 T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1176 |
| G13 | 行省运营费行 | CenterStage | Read-only | "行省运营费 -18 T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1177 |
| G14 | 其他支出行 | CenterStage | Read-only | "其他支出 -XX T" | N/A | 无 DTO | N/A | None | 同上 | 公开 | 同上 | 同上 | 同上 | N/A | API Missing | Deferred | v3.25.1.html:1178 |
| G15 | 🏛️ 派系财政副标题 | CenterStage | Static Text | "🏛️ 派系财政" | N/A | N/A | N/A | None | 同上 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Reuse | v3.25.1.html:1182 |
| G16 | 派系财政行 (Optimates) | CenterStage | Read-only | "Optimates +5 T · 会员 +3 T · 合计 +8 T" | N/A | 无 DTO | N/A | None | 同上 | **仅本派系可见己方; 其他派系摘要?** | 同上 | 同上 | 隐藏 | N/A | API Missing | Deferred | v3.25.1.html:1183 |
| G17 | 派系财政行 (Populares) | CenterStage | Read-only | 同上 | N/A | 同上 | N/A | None | 同上 | **其他派系金库不应可见** | 同上 | 同上 | 隐藏 | N/A | DTO Gap + Permission Issue | Deferred | v3.25.1.html:1184; 权限需 Data Owner 确认 |
| G18 | 派系财政行 (Equites) | CenterStage | Read-only | 同上 | N/A | 同上 | N/A | None | 同上 | 同上 | 同上 | 同上 | 隐藏 | N/A | DTO Gap + Permission Issue | Deferred | v3.25.1.html:1185 |
| G19 | 🌾 地主私人收益副标题 | CenterStage | Static Text | "🌾 地主私人收益" | N/A | N/A | N/A | None | 同上 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Reuse | v3.25.1.html:1188 |
| G20 | 地主收益行 (人物) | CenterStage | Read-only + Click | "Gaius +3 T" (点击查看详情) | N/A | 无 DTO | N/A | 点击→显示人物详情 Modal | 同上 | **仅本派系人物? 私有财产隐私?** | 同上 | 同上 | 隐藏 | N/A | DTO Gap + Permission Issue | Deferred | v3.25.1.html:1189-1191 |
| G21 | 国库净变化行 | CenterStage | Read-only | "国库净变化: +72 T → 新余额: 142 T" | N/A | 可用 Store.treasury + 收入差值计算 | 需新增 DTO | None | 同上 | 公开 | 同上 | 同上 | 隐藏 | N/A | DTO Gap | Deferred | v3.25.1.html:1195 |
| G22 | ✅ 确认收入结算按钮 | CenterStage | Action | "✅ 确认收入结算" | N/A | N/A | 需新增: doExecuteRevenue() | 点击→执行收入结算 | 同上 | 必须是当前玩家 | 阶段激活+是当前玩家 | "收入阶段未接入" / "不是当前玩家" | disabled | API 失败→feedback | API Missing + DTO Gap | Deferred | v3.25.1.html:1199 |

---

## 深度审查说明（2026-07-10 第二轮）

本区域经过完整 Python API 层追溯。关键发现：

- **`forum_api.py`**（472 行）含完整后端函数：`retire_figure`, `recruit_figure`, `place_bid`, `buy_land`, `vote_triumph`, `transact_land`, `resolve_forum`, `resolve_land_trades` — **API 层 100% 完备**
- **GUI 连接层全部缺失**：`api_adapter.py` 无 forum 方法、`session_store.py` 无 forum 属性/Slot、`GuiText.qml` 无 forum 键
- **无 ForumStage.qml**：`src/ui/gui/qml/stages/` 下不存在
- 原标 "API Missing" 应改为 **"API Existing / GUI Missing"**（后端功能齐全，缺 Adapter+Store+QML 链路）

## 区域 H: 广场阶段 (Forum − CenterStage) — 修正版

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 阶段徽章 "3 / 7" | CenterStage | Static Text | "3 / 7" | Store phaseNavigation index | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | v3.25.1.html:1205 |
| H2 | 阶段标题 "🏛️ 广场阶段" | CenterStage | Static Text | "广场阶段" | Store.currentPhaseName | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "广场" | N/A | Existing | Reuse | v3.25.1.html:1206 |
| H3 | 阶段描述文字 | CenterStage | Static Text | "解雇 → 人才市场（招募·竞标·公地·凯旋）→ 公示" | Store.selectedPhaseSummary.description | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "承接GUI-P0-03D" | N/A | Existing | Reuse | v3.25.1.html:1207 |
| H4 | 步骤引导条 (3 步骤) | CenterStage | State/Indicator | 公示区 → 解雇成员 → 人才市场 | 无步骤概念 | N/A | N/A | None | 总是 | 公开 | 总是 | N/A | 三步骤可见 | N/A | Pure Static UI Text | Rebuild (步骤条) | v3.25.1.html:1208-1211 |
| H5 | 公示区文本 | CenterStage | Read-only | "广场阶段开始..." | state.active_wars + state.curia 可用 | 现有字段 | forum_api 已存在 → 新增 get_forum_view() + Store forumView | None | 广场阶段 | 公开 | 阶段激活 | "广场 GUI 未接入" | 从 snapshot 派生战况 | N/A | Adapter Gap | Phase 2 Build | v3.25.1.html:1214 |
| H6 | 面板1: 解雇成员 — 人物列表 | CenterStage | Action Region | 本派系人物卡片 + 解雇按钮 | Store.myFigures (已暴露) | my_figures[].id/.name/.class_tier/.influence | forum_api.retire_figure() 完整 (非领袖/无合同/存活) | 点击解雇→Store.doRetireFigure(figId) | 广场+子环节1 | 仅本派系人物 | 存活+非领袖+无合同 | "不可解雇(领袖/有合同/已死)" | "无可解雇成员" | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:18-51 |
| H7 | 面板1: 完成解雇按钮 | CenterStage | Action | "⏭️ 完成解雇" | N/A | N/A | resolve_forum() 统一结算, 无独立 complete_dismissals | 点击→标记完成 | 子环节1 | 当前玩家已操作 | 已解雇≥1人 | "请先选择要解雇的人物" | disabled | N/A | Backend Gap | Phase 2+ Deferred | forum_api.py:resolve_forum() |
| H8 | 面板2: 人才市场 — 锁定态 | CenterStage | State | "⏳ 等待子环节1完成" | N/A | N/A | N/A | None | 子环节1完成 | 公开 | 子环节1完成 | "子环节1未完成" | N/A | N/A | Pure Static UI Text | Rebuild | v3.25.1.html:1234 |
| H9 | 面板2: 人才列表表格 | CenterStage | Read-only + Action | 姓名/军略/智略/魅力/热忱/阶级/费用/招募 | state.curia.get_all_available() | Figure.id/.name/.martial/.intel/.charisma/.zeal/.class_tier | forum_api.recruit_figure() 完整 | [招募]→确认→Store.doRecruitFigure(figId, amount) | 子环节2 | 仅本派系可操作 | 广场+派系有空位+当前玩家 | "国库不足"/"派系已满" | "无待招募人物" | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:53-73 |
| H10 | 面板2: 合同竞标栏 | CenterStage | Action | 可竞标合同+出价输入 | state.get_contracts() status=BUDGETED | Contract.id/.name/.contract_type/.base_cost | forum_api.place_bid() 完整 (金额/利润率/骑士/BUDGETED) | 出价→确认→Store.doBid(contractId, figId, amount) | 子环节2 | 仅本派系(需骑士人物) | 人物骑士+合同BUDGETED+金额合规+当前玩家 | "骑士不足"/"金额不合规" | "无可竞标合同" | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:76-150 |
| H11 | 面板2: 认购公地栏 | CenterStage | Action | 可认购单位+总价+[确认] | state.pending_land_sale_quota + land_price_per_unit | 需 Store 暴 forumView.pendingLandQuota | forum_api.buy_land() 完整 (额度/财富/配额) | 选择人物+数量→Store.doBuyLand(figId, amount) | 子环节2 | 仅本派系可操作 | 有可用配额+人物财富足够 | "无公地配额"/"资金不足" | "本回合无可认购" | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:153-181 |
| H12 | 面板2: 凯旋投票栏 | CenterStage | Action | 待决凯旋战争+[支持/反对] | war_system.get_resolved_wars() | War.id/.name/.triumph_commander_id | forum_api.vote_triumph() 完整 | 支持/反对→Store.doTriumphVote(warId, vote) | 子环节2 | 所有派系可投票 | 存在可投票凯旋+当前玩家 | "本回合无凯旋投票" | "无待决凯旋" | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:184-215 |
| H13 | 面板3: 公示结算区 | CenterStage | Action | 结算汇总报告 | resolve_forum().data.results | N/A | forum_api.resolve_forum() 完整 (4项统一结算) | 点击→Store.doResolveForum() | 子环节完成 | 公开 | 所有派系完成 | "子环节尚未全部完成" | disabled | API 异常 | Adapter Gap | Phase 2 Build | forum_api.py:249-414 |
| H14 | 结算结果展示区 | CenterStage | Read-only | 逐行结算文本 | resolve_forum().data.results[] | N/A | 同上 | None | 结算后 | 公开 | 有结算结果 | N/A | "等待公示结算" | N/A | Adapter Gap | Phase 2 Build | forum_api.py:resolve_forum() |
| H15 | 进度+推进按钮 | CenterStage | Action | "进度 2/5" / "⏭️ 进入公示" | N/A | N/A | 依赖 C2 通用 advance_phase | 点击→推进 | 子环节完成 | 当前玩家 | 子环节全部完成 | "请先完成子环节" | disabled | N/A | Backend Gap | Phase 2 (依赖 C2) | 见 C2 决策 |

### 广场阶段汇总

| 状态 | 数量 | 说明 |
|------|------|------|
| Existing | 3 | H1-H3 外壳元素 |
| Pure Static UI Text | 2 | H4 步骤条, H8 锁定态 |
| Adapter Gap (Adapter+Store+QML需新建) | 8 | H5,H6,H9,H10,H11,H12,H13,H14 |
| Backend Gap | 2 | H7 (子环节状态机), H15 (advance_phase) |


## 区域 I: 人口阶段 (Population − CenterStage) — 修正版

**深度审查结论：人口阶段是三个复杂阶段中 GUI 链路最完整的。**

| 层级 | 状态 |
|------|------|
| population_api.py | ✅ 完整 (campaign, vote, get_candidates, resolve_election) |
| api_adapter.py | ✅ 完整 (campaign, vote, resolve_election, get_population_view) |
| session_store.py | ✅ 完整 (8个属性+5个Slot) |
| QML: PopulationStage.qml | ✅ (3个子视图: FestivalView/VoteView/ElectionResultView) |
| 视觉对齐 v3.25.1 | ❌ QML 样式为旧版, 需视觉重建 |

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| I1 | 阶段徽章 "4 / 7" | CenterStage | Static | "4 / 7" | Store phaseNavigation | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | phase_nav index=3 |
| I2 | 阶段标题 "⚖️ 人口阶段" | CenterStage | Static | "人口阶段" | Store.currentPhaseName | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | population_stage |
| I3 | 阶段描述文字 | CenterStage | Static | 年度人口普查+官职选举 | Store.selectedPhaseSummary | N/A | session_api | None | 总是 | 公开 | 总是 | "后续承接" | N/A | N/A | Existing | Reuse | session_api |
| I4 | 步骤引导条 | CenterStage | State | API 决定步骤数 | 无步骤概念 | N/A | N/A | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (步骤条) | v3.25.1.html (预期) |
| I5 | 本派系人物列表 | CenterStage | Read-only | 人物姓名/影响力/官职/财富 | Store.myFigures[] | my_figures[].name/.influence/.office/.wealth | session_api.get_session_snapshot | None | 仅人口阶段 | 仅本派系 | 阶段激活 | "人口阶段未接入" | "无人物" | API 异常→均标0 | Existing | Rebuild (视觉→卡片) | session_store.py:106, PopulationStage.qml |
| I6 | 庆典赞助(输入+按钮) | CenterStage | Action | 选择人物+赞助金额 | doCampaign(figId, amount) | N/A | Adapter.campaign() → population_api.campaign() | 点击→赞助庆典 | 人口+未完成 | 仅当前玩家 | canCampaign==true | "不是当前玩家" / "已赞助完毕" | disabled | API 失败→feedback | Existing (API完整) | Rebuild (视觉) | PopulationStage.qml, FestivalView.qml |
| I7 | 官职投票区 | CenterStage | Action | 官职列表+候选人 | Store.populationView | population_view.candidates | Adapter.get_population_view() → population_api | 为职位投票 | 人口+未完成 | 仅当前玩家 | canVote==true | "不是当前玩家" | 无候选职务→隐藏 | API 异常→feedback | Existing (API完整) | Rebuild (视觉) | VoteView.qml, population_api.py |
| I8 | 投票已完成指示 | CenterStage | State | "已投票: 职务名" | Store.myVotes | population_view.my_votes[] | 同上 | None | 已投票 | 仅个人可见 | 已完成 | N/A | "" | N/A | Existing | Rebuild | session_api.py:133-137 |
| I9 | 完成玩家操作按钮 | CenterStage | Action | "完成当前玩家操作" | N/A | N/A | Adapter.complete_player() → population_api | 点击→轮到下一玩家 | 人口+已操作 | 仅当前玩家 | is_current && populated | "不是当前玩家" | disabled | API 异常 | Existing (API完整) | Reuse (视觉更新) | PopulationStage.qml, session_store.py |

---

---

## 区域 J: 元老院阶段 (Senate − CenterStage) — 修正版

**深度审查结论：元老院是最特殊的阶段 — API 层有完整交互能力，但 GUI 层被设计为只读。**

| 层级 | 状态 | 说明 |
|------|------|------|
| senate_api.py | ✅ 完整 | 含 propose(), vote(), veto(), resolve_senate() — 不仅限于只读 |
| api_adapter.py | ⚠️ 只读 | 仅暴露 get_senate_view(), 无 propose/vote/veto/resolve |
| session_store.py | ⚠️ 只读 | 6个只读属性, 无操作 Slot |
| SenateStage.qml (272行) | ⚠️ 只读 | 6个 SenateReadOnlySection, 无交互组件 |
| GuiText 键 (17个) | ✅ 完整 | senateTitle 至 senateLeaderCount |

**设计选择：代码注明明示"元老院已接入只读状态；提案、投票与结算由后续任务承接"。**

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J1 | 阶段徽章 "5 / 7" | CenterStage | Static | "5 / 7" | Store phaseNavigation | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | phase_nav index=4 |
| J2 | 阶段标题 "🏺 元老院阶段" | CenterStage | Static | "元老院阶段" | Store.currentPhaseName | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | GUI design doc |
| J3 | 阶段描述 | CenterStage | Static | "提案→报告→投票→保民官否决" | Store.selectedPhaseSummary | N/A | session_api | None | 总是 | 公开 | 总是 | "后续任务承接" | N/A | N/A | Existing | Reuse | session_api._build_phase_summary |
| J4 | 步骤引导条 | CenterStage | State | 提案→报告→投票→否决 | 无步骤 | N/A | N/A | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (步骤条) | v3.25.1.html (预期) |
| J5 | 主持官信息 | CenterStage | Read-only | "主持官: XXX" | senate_view.presiding_officer | senate_view | senate_api.get_senate_view → Adapter → Store | None | 元老院阶段 | 公开 | 阶段激活 | "元老院未接入" | "暂无主持官" | N/A | Existing | Rebuild (视觉) | SenateStage.qml, senate_api.py |
| J6 | 派系领袖列表 | CenterStage | Read-only | "Optimates: Gaius(影响力45)" | senate_view.faction_leaders[] | senate_view | 同上 | None | 同上 | 公开 | 阶段激活 | 同上 | "无领袖" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J7 | 进行中战争列表 | CenterStage | Read-only | "第一次布匿战争 ⚔️ 迦太基" | senate_view.active_foreign_wars[] | senate_view | 同上 | None | 同上 | 公开 | 阶段激活 | 同上 | "无战争" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J8 | 战争威胁列表 | CenterStage | Read-only | "伊庇鲁斯: 威胁中" | senate_view.war_threats[] | senate_view | 同上 | None | 同上 | 公开(摘要) | 阶段激活 | 同上 | "无威胁" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J9 | 待审停战草案 | CenterStage | Read-only | "迦太基: 赔款120T·10年" | senate_view.pending_peace_treaties[] | senate_view | 同上 | None | 同上 | 公开 | 阶段激活 | 同上 | "无停战草案" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J10 | 总督空缺列表 | CenterStage | Read-only | "西西里: 空缺" | senate_view.governor_vacancies[] | senate_view | 同上 | None | 同上 | 公开 | 阶段激活 | 同上 | "无空缺" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J11 | 待处理合同列表 | CenterStage | Read-only | "建造合同 ID:3" | senate_view.pending_contracts[] | senate_view | 同上 | None | 同上 | 公开 | 阶段激活 | 同上 | "无合同" | N/A | Existing | Rebuild (视觉) | SenateStage.qml |
| J12 | 只读状态标签 | CenterStage | State | "只读状态" | Store.selectedPhaseSummary | interaction_mode | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | session_store.py:300, GuiText.qml |
| J13 | "政治行动暂未开放" 提示 | CenterStage | Static | "提案创建、表决、否决与结算将在后续子任务承接" | GuiText.senateActionsDisabled | N/A | N/A | None | 元老院阶段 | 公开 | 总是 | N/A | N/A | N/A | Existing (占位文本) | Reuse | SenateStage.qml, GuiText.qml |
| J14 | 无记录占位 | CenterStage | Static | "暂无记录" | GuiText.senateNoItems | N/A | N/A | None | 列表为空 | 公开 | 列表为空 | N/A | N/A | N/A | Existing | Reuse | GuiText.qml |

---


## 区域 K: 战争阶段 (Combat − CenterStage)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K1 | 阶段徽章 "6 / 7" | CenterStage | Static | "6 / 7" | Store phaseNavigation | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | phase_nav index=5 |
| K2 | 阶段标题 "⚔️ 战争阶段" | CenterStage | Static | "战争阶段" | Store.currentPhaseName | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "战争" | N/A | Existing | Reuse | phase_nav name |
| K3 | 阶段描述 | CenterStage | Static | "多战争并排·军力对比·战斗裁定·停战" | Store.selectedPhaseSummary | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "后续任务承接" | N/A | Existing | Reuse | session_api |
| K4 | 步骤引导条 | CenterStage | State | 预期: 选择战争→战斗→停战谈判 | 无 | N/A | N/A | None | 总显示 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (步骤条) | v3.25.1.html (预期) |
| K5 | 多战争面板 (并排) | CenterStage | Read-only + Action | 战争名/指挥官/我军力/敌军力/状态 | N/A | 无 combat DTO | WarSystem + CombatCommand 存在但无 GUI 安全 API | None | 战争阶段 | 公开(战争摘要) | 阶段激活 | "战争阶段未接入" | "无战争" | N/A | API Missing | Deferred | v3.25.1.html:1355-1415; 无 combat_api.py |
| K6 | 战斗按钮 (每战争) | CenterStage | Action | "⚔️ 进攻" | N/A | N/A | 需新建 combat_api.py | 点击→执行战斗 | 战争阶段+未作战 | 当前玩家+指挥官 | 已指派+未攻击 | "已进攻" / "无指挥官" | disabled | API 异常 | API Missing | Deferred | v3.25.1.html:1392 |
| K7 | 战斗结果展示区 | CenterStage | Read-only | 掷骰结果/胜/败/平局+停战草案 | N/A | 需 combat DTO | 需新建 combat_api.py | None | 战斗后 | 公开 | 已执行战斗 | N/A | "尚未战斗" | API 异常 | API Missing + DTO Gap | Deferred | v3.25.1.html:1398-1410 |
| K8 | 停战谈判区 | CenterStage | Action | 赔款/期限/领土变更 | N/A | 需 combat DTO | 需新建 combat_api.py | 谈判 | 平局后 | 当前玩家 | 有停战草案 | "无停战草案" | "无" | API 异常 | API Missing + DTO Gap | Deferred | v3.25.1.html:1410-1415 |

## 区域 L: 决算阶段 (Resolution − CenterStage)

| # | GUI Element | Region | Type | Displayed Data | Data Source | DTO Field | API / Adapter | Action | Phase Rule | Permission Rule | Enabled Rule | Disabled Reason | Empty State | Error State | Backend Status | Implementation Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1 | 阶段徽章 "7 / 7" | CenterStage | Static | "7 / 7" | Store phaseNavigation | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | N/A | N/A | Existing | Reuse | phase_nav index=6 |
| L2 | 阶段标题 "📊 决算阶段" | CenterStage | Static | "决算阶段" | Store.currentPhaseName | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "决算" | N/A | Existing | Reuse | phase_nav name |
| L3 | 阶段描述 | CenterStage | Static | "各省总督轮换 / 民变检查 / 进入新年" | Store.selectedPhaseSummary | N/A | session_api | None | 总是 | 公开 | 总是 | N/A | "后续任务承接" | N/A | Existing | Reuse | session_api |
| L4 | 步骤引导条 | CenterStage | State | 预期: 总督轮换→民变→新年 | 无 | N/A | N/A | None | 总显示 | 公开 | 总是 | N/A | N/A | N/A | Pure Static UI Text | Rebuild (步骤条) | v3.25.1.html (预期) |
| L5 | 总督轮换面板 | CenterStage | Action | 总督列表+轮换/解任操作 | N/A | 无 resolution DTO | ResolutionCommand + advance_year 存在但无 GUI 安全包装 | 交互操作 | 决算阶段 | 当前玩家 | 阶段激活 | "决算阶段未接入" | "无总督" | N/A | API Missing | Deferred | src/api/ 无 resolution_api.py |
| L6 | 民变检查面板 | CenterStage | Read-only | 行省民变等级列表 | N/A | 可用 province.grievance (需确认) | 需新建 resolution_api.py | None | 同上 | 公开 | 阶段激活 | 同上 | "无行省" | N/A | API Missing + DTO Gap | Deferred | 需检查 province 数据支持 |
| L7 | 进入新年按钮 | CenterStage | Action | "📅 进入下一年" | N/A | N/A | advance_year 存在但仅 CLI, 需 GUI 安全封装 | 点击→新年 | 所有阶段完成后 | 当前玩家 | 所有阶段已执行 | "有阶段未完成" | disabled | API 异常 | API Missing (advance_year 仅 CLI) | Deferred | v3.25.1.html:1835, game_api.py:advance_year |

---



## Codex 审阅修正说明（2026-07-10）

**审阅文件：** `Codex_Review_GUI_CONTROL_MAPPING_MATRIX_2026-07-10.md`

### 修改清单

| # | 修改内容 | 区域 | 说明 |
|---|---------|------|------|
| 1 | 收入阶段 G6-G22 分类修正 | 区域 G | `Backend Gap` → `API Missing` / `DTO Gap` / `API Missing + DTO Gap`。Core Service(EconomicService) 存在，缺 revenue_api.py。 |
| 2 | Backend Status 枚举统一 | 区域 H,I,J,K,L | 非标准写法 (如`API有/Adapter Store QML缺`、`New QML`等) 统一为：Existing / Adapter Gap / DTO Gap / API Missing / Backend Gap / Deferred Placeholder / Pure Static UI Text。 |
| 3 | 人口表格字段补齐 | 区域 I | 补齐 Empty State / Error State / Evidence 列。修正 I6 空状态(disabled)、I7 无候选人状态。 |
| 4 | 元老院表格字段补齐 | 区域 J | 补齐 Empty State / Error State / Evidence 列。各只读列表补充空状态描述。 |
| 5 | 战争/决算表述精确化 | 区域 K,L | 从 `Backend Gap` 改为 `API Missing`，注明 WarSystem + CombatCommand / ResolutionCommand + advance_year 存在但无 GUI 安全包装。 |
| 6 | advancePhase 推迟 | C2,H15 | 通用 advancePhase 标记为 Phase 2+ 决策，不阻塞 Phase 1。天命 Vertical Slice 继续使用 doAdvanceMortality()。 |

### 未处理项

- 提交修复时间较晚。未重新验证每个字段值。
- 底层 `├─` 表格线条可能存在渲染兼容问题。

### 修正后状态

✅ **可以进入下一阶段：** `GUI_DTO_GAP_REPORT.md` + `GUI_PHASE_INTEGRATION_PLAN.md`
