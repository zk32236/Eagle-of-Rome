# GUI DTO 缺口报告

> 文件 2/3 | 2026-07-10 | 代码基准: `main` (65bbf67)
> 基于: `GUI_CONTROL_MAPPING_MATRIX.md` (含 Codex 审阅修正)
> 角色: DTO 缺失分析与补充建议

---

## 阅读指南

### Gap 类型

| 类型 | 定义 | 严重度 |
|------|------|-------|
| **Existing** | DTO 字段和 Store 属性均已存在 | ✅ 无缺口 |
| **Derived** | DTO 字段可组合现有数据计算得出 | 🟡 轻量缺口 |
| **Store Missing** | DTO 后端有数据, Store 未暴露 Property | 🟡 轻量缺口 |
| **DTO Missing** | 需要新建数据结构, 后端无对应字段 | 🔴 主要缺口 |
| **API Missing** | 需要新建 API 包装, 后端逻辑存在但未封装 | 🔴 主要缺口 |
| **Permission** | 数据存在但需 viewer 过滤/权限限制 | ⚠️ 设计关注 |
| **Deferred** | 暂不实现, 占位处理 | ⬜ 待定 |

### 字段结构(每元素)

```
Element | Region | Type | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action
```

---

## 区域 A: 顶栏 (TopBar)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| A1 | Logo "SPQR" | N/A (Hardcoded) | N/A | N/A | N/A | N/A | Public | Existing | 无需操作 |
| A2 | 国库数值 | public_resources.treasury | `session_api._build` → `treasury` ✅ | `Store.treasury` ✅ | 0 (默认) | Transport→0 | Public | ✅ Existing | 确认字段名一致 |
| A3 | 派系金库 | faction_resources.treasury | ✅ | `Store.factionTreasury` ✅ | 0 | Transport→0 | Own faction only | ✅ Existing | 确认权限过滤 |
| A4 | 影响力 | faction_resources.total_influence | ✅ | `Store.factionInfluence` ✅ | 0 | Transport→0 | Own faction only | ✅ Existing | 确认 |
| A5 | 稳定度 | **缺失** — GameState 无 stability 字段 | `province.grievance` 可为推导基础(每级25%) | 暂不新增 | 0% | N/A | Public | ⚠️ **Decision Needed / Deferred** | 暂不新增DTO. v3.25.1稳定度可能是视觉占位, 待产品确认规则后再设计. 新Shell顶栏先隐藏或替换. |
| A6 | 战争数 | **缺失** — Store 无 warCount | `senate_view.summary.active_foreign_war_count` 可用 ✅ | 需新增 `Store.warCount` | 0 | 0 | Public | 🟡 **Store Missing** | 新增 Store property |
| A7 | 回合/年 | public_resources.year_display, turn_number | ✅ | `Store.yearDisplay`, `Store.turnNumber` ✅ | " "+0 | 默认值 | Public | ✅ Existing | 确认 |
| A8 | 当前玩家 | current_player_id, faction_resources.name | ✅ | `Store.currentPlayerId`, `Store.viewerFactionName` ✅ | 默认文本 | 默认文本 | Viewer only | ✅ Existing | 确认 |

### A 区缺口汇总
- **DTO Missing: 1** (A5 稳定度 — 需新建推导)
- **Store Missing: 1** (A6 战争数 — 数据已存在, 仅需暴露)
- **Existing: 6**

---

## 区域 B: 左侧阶段导航 (PhaseRail)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| B1 | 阶段圆形图标(7个) | phase_navigation[].id | `_build_phase_navigation` ✅ | `Store.phaseNavigation` ✅ | N/A | N/A | Public | ✅ Existing | 确认 id→图标映射 |
| B2 | 阶段 hover 名称 | phase_navigation[].name | ✅ | Store.phaseNavigation → name | N/A | N/A | Public | ✅ Existing | 确认 |
| B3 | 阶段状态(done/current/todo) | phase_navigation[].executed, .current, .implemented | ✅ | ✅ | N/A | Transport→全部todo | Public | ✅ Existing | 确认 |
| B4 | 阶段高亮(当前选中) | selected_phase_id | session_api → snapshot | `Store.selectedPhaseId` ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| B5 | 刷新状态按钮 | N/A | N/A | `Store.refreshSnapshot()` Slot ✅ | N/A | 失败→feedback | Public | ✅ Existing | 确认 |
| B6 | 阶段说明按钮 | N/A | N/A | `Store.logUiEvent()` Slot ✅ | N/A | N/A | Public | ✅ Existing | 确认 |

### B 区缺口汇总
- **Existing: 6** — 阶段导航全通

---

## 区域 C: 右侧面板 (ContextPanel)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| C1 | 当前阶段标题 | selected_phase_summary | ✅ | `Store.selectedPhaseSummary` ✅ | "尚未迁移" | Transport→默认 | Public | ✅ Existing | 确认 |
| C2 | 推进到下一阶段按钮 | **缺失** — Store 无通用 canAdvance | 需新增 Phase 2+ | 需新增 `canAdvance` + `doAdvancePhase()` | disabled | Transport→disabled | Current player | 🔴 **API Missing + Store Missing** | Codex 建议 Phase 2+. 天命用现有 doAdvanceMortality() |
| C3 | 进度指示(x/y) | **缺失** — 无子步骤计数 | N/A | 需新增 | "0/0" | "0/0" | Public | 🔴 **DTO Missing** | Phase 2 新增子步骤计数 DTO |
| C4 | 状态标签 | selected_phase_summary.status_text | ✅ | ✅ | "后续任务承接" | "未知" | Public | ✅ Existing | 确认 |
| C5 | 派系名 | faction_resources.name | ✅ | `Store.viewerFactionName` ✅ | "" | "" | Own faction | ✅ Existing | 确认 |
| C6 | 人物数 | faction_resources.member_count | ✅ | `Store.factionMemberCount` ✅ | "0人" | "0人" | Own faction | ✅ Existing | 确认 |
| C7 | 事件日志 | **决策待定** — Store vs QML本地 | 当前 FeedbackPanel 是QML本地 | 暂不新增 | 空日志区 | N/A | Public | ⚠️ **Decision Needed** | 短期保留QML本地FeedbackPanel. Phase 1不做Store统一日志. 如需跨阶段历史日志再评估. |
| C8 | 清空日志按钮 | N/A(本地QML操作) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认(本地操作) |

### C 区缺口汇总
- **DTO Missing: 1** (C3 子步骤计数)
- **API Missing + Store Missing: 1** (C2 advancePhase — Phase 2+)
- **Decision Needed: 1** (C7 日志归属)
- **Existing: 5**

---

## 区域 D: 底部操作栏 (BottomBar)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| D1 | 操作栏标题 | N/A(Hardcoded) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| D2 | 📋派系信息 | `global_query_result` | `gui_query_api.get_faction_info()` ✅ | `Store.doGlobalQuery("faction_info")` ✅ | "暂无记录" | 显示错误 | Own/public filtered | ✅ Existing | 确认 |
| D3 | 👤人物查询 | N/A (Deferred) | 未实现 | `doGlobalQuery("figure_search")` → 占位 | placeholder | placeholder | Permission? | ⬜ **Deferred** | 保持占位 |
| D4 | 📊游戏状态 | `global_query_result` | `gui_query_api.get_game_status()` ✅ | `doGlobalQuery("game_status")` ✅ | 公开摘要 | 显示错误 | Public | ✅ Existing | 确认 |
| D10 | ⚔️战争列表 | `global_query_result` | `gui_query_api.get_war_list()` ✅ | `doGlobalQuery("war_list")` ✅ | 公开战争列表 | API 异常 | Public | ✅ Existing | 确认 |
| D11 | 🗡️军团状态 | `global_query_result` | `gui_query_api.get_legion_status()` ✅ | `doGlobalQuery("legion_status")` ✅ | 公开军团列表 | API 异常 | Public | ✅ Existing | 确认 |
| D3,D5-D9,D12,D13 | 其余8个查询 | N/A (Deferred) | 未实现 | `doGlobalQuery()` → 占位响应 | placeholder | placeholder | Permission? (各查询不同) | ⬜ **Deferred (×8)** | 保持占位 |

### D 区缺口汇总
- **Existing: 4** (D1, D2, D4, future D10-D11 war_list/legion_status)
- **Deferred: 8** (D3,D5-D9,D12,D13)

---

## 区域 E: Modal / Overlay

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| E1 | 模态框遮罩 | N/A(纯UI) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 视觉对齐 |
| E2 | 模态框标题 | global_query_result.title | ✅ | `Store.globalQueryResult.title` ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| E3 | 关闭按钮 | N/A(本地QML) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认 |
| E4 | 内容区 | global_query_result.items[] + summary | ✅ | `Store.globalQueryResult.items` + `summary` ✅ | "暂无记录" | 错误消息 | Per-query filtered | ✅ Existing | 确认 |
| E5 | 确认/关闭按钮 | N/A(回调驱动) | N/A | `ConfirmDialog.qml` ✅ | N/A | N/A | Phase-dependent | ✅ Existing | 视觉更新 |
| E6 | 玩家交接遮罩 | handoff 信号 | `Store.handoffRequired` ✅ | `PlayerHandoffOverlay.qml` ✅ | N/A | N/A | Current player only | ✅ Existing | 视觉更新 |

### E 区缺口汇总
- **Existing: 6** — Modal/Overlay 全通

---

## 区域 F: 天命阶段 (Mortality − CenterStage)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| F1 | 阶段徽章 "1/7" | phase_navigation[0].index | ✅ | `Store.phaseNavigation` ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| F2 | 阶段标题 | selected_phase_summary.name | ✅ | `Store.selectedPhaseName` ✅ | 占位名称 | N/A | Public | ✅ Existing | 确认 |
| F3 | 阶段描述 | selected_phase_summary.description | ✅ | `Store.selectedPhaseSummary.description` ✅ | "后续任务承接" | N/A | Public | ✅ Existing | 确认 |
| F4 | 步骤引导条(2步骤) | **缺失** — 无步骤概念 | N/A | N/A | 两步骤可见 | N/A | Public | 🟡 **New QML Only** | 纯视觉, 无后端依赖 |
| F5 | 步骤1状态(current) | 同上 | N/A | N/A | 全部todo | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| F6 | 步骤2状态(todo/current) | 同上 | N/A | N/A | 全部todo | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| F7 | 事件展示区 | mortality_view.events[] + impacts[] | `mortality_api.get_mortality_view` ✅ | `Store.mortalityEvents` ✅ | "尚未执行天命" | 错误文本 | Public | ✅ Existing | 视觉→羊皮纸 |
| F8 | 事件名称 | events[].name | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F9 | 事件摘要 | events[].summary | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F10 | 影响项列表 | events[].impacts[] | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F11 | 人物死亡影响 | impact.type="figure_death" | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F12 | 英雄登场 | impact.type="hero_spawn" | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F13 | 灾害 | impact.type="disaster" | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F14 | 民怨 | impact.type="province_grievance" | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 视觉重建 |
| F15 | 战争威胁 | impact.type="war_threat" | **确认是否需要** — API 是否返回此类型 | 同上 | N/A | N/A | Public | ⚠️ **Decision Needed** | 需确认 mortality_api 输出 |
| F16 | ⚡执行天命按钮 | can_execute | `mortality_view.can_execute` ✅ | `Store.canExecuteMortality` ✅ | disabled | API 失败→feedback | Current player | ✅ Existing | 视觉更新 |
| F17 | 📜进入收入阶段按钮 | can_advance | `mortality_view.can_advance` ✅ | `Store.canAdvanceMortality` ✅ | disabled | API 失败→feedback | Current player | ✅ Existing | 确认(Phase1仍使用) |
| F18 | disabled_reason | selected_phase_summary.disabled_reason | ✅ | ✅ | "" | N/A | Public | ✅ Existing | 确认 |
| F19 | 状态标签 | mortality_view.can_execute | ✅ | ✅ | "准备执行天命" | N/A | Public | ✅ Existing | 视觉更新 |

### F 区缺口汇总
- **New QML Only (无后端依赖): 3** (F4,F5,F6 步骤条)
- **Decision Needed: 1** (F15 war_threat 类型)
- **Existing: 15** — 天命是全链路最完整的阶段

---

## 区域 G: 收入阶段 (Revenue − CenterStage)

**背景:** 后端有 `EconomicService.settle_revenue_phase()`, 但无 revenue_api.py, 无 DTO, 无 Store 属性.

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| G1 | 阶段徽章 "2/7" | phase_navigation[1].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| G2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "收入" | N/A | Public | ✅ Existing | 确认 |
| G3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "后续任务承接" | N/A | Public | ✅ Existing | 确认 |
| G4 | 步骤引导条(2步骤) | N/A | N/A | N/A | 两步骤可见 | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| G5 | 📈国家收入副标题 | N/A(Hardcoded) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认 |
| G6 | 国家公地收益 | **缺失** — 需新建 revenue DTO: public_land_income | EconomicService 有数据 | 需新增 | 隐藏区域 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 revenue_view.public_land_income |
| G7 | 战争赔款收入 | **缺失** — revenue DTO: war_indemnity_income | EconomicService 有? | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G8 | 行省税收入 | **缺失** — revenue DTO: province_tax_income | EconomicService 有 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G9 | 其他收入 | **缺失** — revenue DTO: other_income | 待确认 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G10 | 📉国家支出副标题 | N/A(Hardcoded) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认 |
| G11 | 军团维护费 | **缺失** — revenue DTO: legion_maintenance | EconomicService 有 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G12 | 舰队维护费 | **缺失** — revenue DTO: fleet_maintenance | EconomicService 有 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G13 | 行省运营费 | **缺失** — revenue DTO: province_operation | EconomicService 有 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G14 | 其他支出 | **缺失** — revenue DTO: other_expenses | 待确认 | 需新增 | 隐藏 | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 |
| G15 | 🏛️派系财政副标题 | N/A(Hardcoded) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认 |
| G16 | 派系财政(Optimates) | **缺失** — revenue DTO: faction_revenue[] | **需设计** | 需新增 | 隐藏 | "数据不可用" | **Own faction only** | 🔴 **DTO Missing + Permission** | 建议: 变动金额公开, 余额保密. 待产品规则正式确认. |
| G17 | 派系财政(Populares) | 同上 | 需设计 | 需新增 | 隐藏 | "数据不可用" | Other factions: summary only | 🔴 **DTO Missing + Permission** | 建议: 他派系仅显示摘要/变动金额. 待产品确认. |
| G18 | 派系财政(Equites) | 同上 | 需设计 | 需新增 | 隐藏 | "数据不可用" | 同上 | 🔴 **DTO Missing + Permission** | 同上 |
| G19 | 🌾地主私人收益副标题 | N/A(Hardcoded) | N/A | N/A | N/A | N/A | Public | ✅ Existing | 确认 |
| G20 | 地主收益行(人物) | **缺失** — revenue DTO: figure_private_income[] | **需设计** | 需新增 | 隐藏 | "数据不可用" | **Own faction: income public, balance secret** | 🔴 **DTO Missing + Permission** | 建议: 收入金额公开, 私产余额保密. 待产品确认. |
| G21 | 国库净变化 | **缺失** — 可用 treasury 当前值 + 收入差值 | 可 Derived: `new_treasury - old_treasury` | 可计算 | 隐藏 | "数据不可用" | Public | 🟡 **Derived** | 不需新建 DTO, 快照比较即可 |
| G22 | ✅确认收入结算按钮 | **缺失** — 需 revenue_api.execute_revenue() + Store.doExecuteRevenue() | 无API | 需新增 Slot | disabled | API 失败 | Current player | 🔴 **API Missing** | 新建 revenue_api.py + Adapter + Store |

### G 区缺口汇总
- **Existing: 6** (G1,G2,G3,G5,G10,G15,G19)
- **New QML Only: 1** (G4)
- **Derived: 1** (G21)
- **DTO Missing: 14** (G6-G9,G11-G14,G16-G18,G20 — 需统一 revenue DTO 设计)
- **API Missing: 1** (G22 — 收入结算 API+Adapter+Slot)
- **Permission: 3** (G16,G17,G18 派系余额保密, G20 私人余额保密)

**收入阶段是 DTO 缺口最大的区域.** 但从头构筑 revenue_api.py + revenue_view DTO 的工作量是一次性的.

---

## 区域 H: 广场阶段 (Forum − CenterStage)

**背景:** `forum_api.py` 已有8个完整API函数, 但无 Adapter/Store/QML.

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| H1 | 阶段徽章 "3/7" | phase_navigation[2].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| H2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "广场" | N/A | Public | ✅ Existing | 确认 |
| H3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "承接GUI-P0-03D" | N/A | Public | ✅ Existing | 确认 |
| H4 | 步骤引导条(3步骤) | N/A | N/A | N/A | 三步骤可见 | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| H5 | 公示区文本 | **缺失** — 需 forum_view 摘要 | `state.active_wars` + `curia` 可用 | 需新增 `Store.forumView.summary` | 从 snapshot 派生 | N/A | Public | 🟡 **Store Missing** | 新增 forum_view DTO |
| H6 | 解雇成员 — 人物列表 | **Store.myFigures** 可用 | ✅ forum_api.retire_figure() | 需新增 `Store.doRetireFigure()` Slot | "无可解雇成员" | API 异常→feedback | Own faction | 🟡 **Store Missing** | 新增 Slot (API已有) |
| H7 | 完成解雇按钮 | **缺失** — 子环节状态机 | forum_api 无此概念 | 需新增 `canCompleteDismissals` | disabled | N/A | Current player | 🔴 **Backend Gap (Phase 2+)** | 广场复杂交互, 不进入 Phase 1. Phase 2+ Forum-specific 设计. |
| H8 | 人才市场锁定态 | N/A(纯视觉) | N/A | N/A | 锁定面板 | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| H9 | 人才列表表格 | **缺失** — 需 forum_view.available_figures[] | `state.curia.get_all_available()` 可用 | 需新增 `Store.forumView.availableFigures` | "无待招募人物" | API 异常 | Public | 🟡 **Store Missing** | 新增 forum_view DTO (API已有) |
| H10 | 合同竞标栏 | **缺失** — 需 forum_view.contracts[] | `state.get_contracts()` BUDGETED 可用 | 需新增 Store 属性 | "无可竞标合同" | API 异常 | Own faction (骑士) | 🟡 **Store Missing** | 新增 forum_view DTO (API已有) |
| H11 | 认购公地栏 | **缺失** — 需 forum_view.land_quota | `state.pending_land_sale_quota` 可用 | 需新增 Store 属性 | "本回合无可认购" | API 异常 | Own faction | 🟡 **Store Missing** | 新增 forum_view DTO (API已有) |
| H12 | 凯旋投票栏 | **缺失** — 需 forum_view.triumph_wars[] | `war_system` 可用 | 需新增 Store 属性 | "无待决凯旋" | API 异常 | All factions | 🟡 **Store Missing** | 新增 forum_view DTO (API已有) |
| H13 | 公示结算区 | **缺失** — 需 forum_view.settlement_result | `resolve_forum().data.results` | 需新增 `Store.doResolveForum()` Slot | disabled | API 异常 | Public(结算后) | 🟡 **Store Missing** | 新增 Slot (API已有) |
| H14 | 结算结果展示 | **缺失** — 承接 resolve_forum 返回值 | 同上 | 需 Store `forumView.settlementResults` | "等待公示结算" | N/A | Public | 🟡 **Store Missing** | 新增 Store 属性 |
| H15 | 进度+推进按钮 | **缺失** — 依赖 C2 advance_phase | 通用 advance 未实现 | 需新增 | disabled | N/A | Current player | 🔴 **Backend Gap (Phase 2+)** | 不进入 Phase 1. 天命使用现有 doAdvanceMortality(). | |

### H 区缺口汇总
- **Existing: 3** (H1,H2,H3)
- **New QML Only: 2** (H4,H8)
- **Store Missing (API Existing): 8** (H5,H6,H9,H10,H11,H12,H13,H14 — 核心工作)
- **Backend Gap: 2** (H7子环节机, H15 advance_phase)

**广场的核心缺口是 Store 属性/Slot 暴露.** API 已经完整, 无需新建 DTO 结构.

---

## 区域 I: 人口阶段 (Population − CenterStage)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| I1 | 阶段徽章 "4/7" | phase_navigation[3].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| I2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "人口" | N/A | Public | ✅ Existing | 确认 |
| I3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "后续承接" | N/A | Public | ✅ Existing | 确认 |
| I4 | 步骤引导条 | N/A | N/A | N/A | N/A | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| I5 | 本派系人物列表 | my_figures[].name/.influence/.office/.wealth | ✅ snapshot → my_figures | `Store.myFigures` ✅ | "无人物" | API异常→均标0 | Own faction | ✅ Existing | 视觉→卡片 |
| I6 | 庆典赞助 | doCampaign(figId, amount) | ✅ Adapter.campaign() → population_api | `Store.doCampaign()` ✅ `Store.canCampaign` ✅ | disabled | API 失败→feedback | Current player | ✅ Existing | 视觉重建 |
| I7 | 官职投票区 | population_view.candidates | ✅ get_population_view() | `Store.populationCandidates` ✅ `Store.canVote` ✅ | 无候选职务 | API 异常→feedback | Current player | ✅ Existing | 视觉重建 |
| I8 | 投票已完成指示 | population_view.my_votes | ✅ | `Store.myVotes` ✅ | "" | N/A | Personal | ✅ Existing | 视觉重建 |
| I9 | 完成玩家操作按钮 | doCompletePlayer() → population_api.complete_player_turn() | ✅ | `Store.doCompletePlayer()` ✅ `Store.canComplete` ✅ | disabled | API 异常→feedback | Current player | ✅ Existing | 视觉更新 |

### I 区缺口汇总
- **Existing: 8** (I1-I3, I5-I9) — 全链路完整
- **New QML Only: 1** (I4 步骤条)

---

## 区域 J: 元老院阶段 (Senate − CenterStage)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| J1 | 阶段徽章 "5/7" | phase_navigation[4].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| J2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "元老院" | N/A | Public | ✅ Existing | 确认 |
| J3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "后续任务承接" | N/A | Public | ✅ Existing | 确认 |
| J4 | 步骤引导条 | N/A | N/A | N/A | N/A | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| J5 | 主持官信息 | senate_view.presiding_officer | ✅ senate_api.get_senate_view() | `Store.senatePresidingOfficer` ✅ | "暂无主持官" | N/A | Public | ✅ Existing | 视觉重建 |
| J6 | 派系领袖列表 | senate_view.faction_leaders[] | ✅ | `Store.senateFactionLeaders` ✅ | "无领袖" | N/A | Public | ✅ Existing | 视觉重建 |
| J7 | 进行中战争 | senate_view.active_foreign_wars[] | ✅ | `Store.senateActiveForeignWars` ✅ | "无战争" | N/A | Public | ✅ Existing | 视觉重建 |
| J8 | 战争威胁 | senate_view.war_threats[] | ✅ | `Store.senateWarThreats` ✅ | "无威胁" | N/A | Public | ✅ Existing | 视觉重建 |
| J9 | 待审停战草案 | senate_view.pending_peace_treaties[] | ✅ | `Store.senatePendingPeaceTreaties` ✅ | "无停战草案" | N/A | Public | ✅ Existing | 视觉重建 |
| J10 | 总督空缺 | senate_view.governor_vacancies[] | ✅ | `Store.senateGovernorVacancies` ✅ | "无空缺" | N/A | Public | ✅ Existing | 视觉重建 |
| J11 | 待处理合同 | senate_view.pending_contracts[] | ✅ | `Store.senatePendingContracts` ✅ | "无合同" | N/A | Public | ✅ Existing | 视觉重建 |
| J12 | 只读状态标签 | interaction_mode="readonly" | ✅ | ✅ | "只读状态" | N/A | Public | ✅ Existing | 确认 |
| J13 | "政治行动暂未开放" | GuiText 占位 | ✅ | N/A | N/A | N/A | Public | ✅ Existing | 保持占位 |
| J14 | 无记录占位 | GuiText 占位 | ✅ | N/A | "暂无记录" | N/A | Public | ✅ Existing | 确认 |

### 交互扩展缺口 (Phase 2+)

| # | Element | DTO Field (Required) | Current DTO | Store Property | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|----------|--------|
| JX1 | 提案创建 | **缺失** — 需 senate_proposals[] DTO | senate_api.propose() 存在 | 需新增 Store + Slot | 🔴 **Store Missing (API exists)** | Phase 2+ |
| JX2 | 投票 | **缺失** — 需 senate_votes[] DTO | senate_api.vote() 存在 | 需新增 Store + Slot | 🔴 **Store Missing (API exists)** | Phase 2+ |
| JX3 | 否决 | **缺失** — 需 senate_veto DTO | senate_api.veto() 存在 | 需新增 Store + Slot | 🔴 **Store Missing (API exists)** | Phase 2+ |
| JX4 | 结算 | **缺失** — 需 senate_resolution DTO | senate_api.resolve_senate() 存在 | 需新增 Store + Slot | 🔴 **Store Missing (API exists)** | Phase 2+ |

### J 区缺口汇总
- **Existing (只读): 14** — 元老院只读 DTO 全通
- **Store Missing (API exists, 交互): 4** — 提案/投票/否决/结算的 Store 属性+Slot 待建

---

## 区域 K: 战争阶段 (Combat − CenterStage)

**背景:** `WarSystem` 在 core 层存在, `CombatCommand` 在 CLI 层存在, 无 combat_api.py.

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| K1 | 阶段徽章 "6/7" | phase_navigation[5].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| K2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "战争" | N/A | Public | ✅ Existing | 确认 |
| K3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "后续任务承接" | N/A | Public | ✅ Existing | 确认 |
| K4 | 步骤引导条 | N/A | N/A | N/A | N/A | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| K5 | 多战争面板 | **缺失** — 需 combat_view.wars[] 含军力/指挥官/状态 | WarSystem 有底层数据, 无 GUI DTO | 需新增 Store | "无战争" | "数据不可用" | Public(summary) | 🔴 **API Missing + DTO Missing** | 新建 combat_api.py + war_view DTO |
| K6 | 战斗按钮 | **缺失** — 需 combat_api.execute_battle() | WarSystem.resolve_war() + CombatCommand 存在 | 需新增 Slot | disabled | API 异常 | Current player (commander) | 🔴 **API Missing** | 新建 combat_api.execute_battle() |
| K7 | 战斗结果展示 | **缺失** — 需 combat_view.battle_result | CombatCommand._resolve_battle() 逻辑存在 | 需新增 Store 属性 | "尚未战斗" | API 异常 | Public | 🔴 **DTO Missing** | 新建 battle_result DTO |
| K8 | 停战谈判 | **缺失** — 需 combat_view.treaty_proposal | WarSystem.enter_truce() + CombatCommand._maybe_generate_treaty() | 需新增 Slot | "无停战草案" | API 异常 | Current player | 🔴 **API Missing + DTO Missing** | 新建 treaty DTO + API |

### K 区缺口汇总
- **Existing: 3** (K1,K2,K3)
- **New QML Only: 1** (K4)
- **API Missing + DTO Missing: 4** (K5-K8 — 需完整 combat_api.py + war_view DTO)

---

## 区域 L: 决算阶段 (Resolution − CenterStage)

**背景:** `ResolutionCommand` 在 CLI 层存在, `game_api.advance_year()` 存在, 无 resolution_api.py.

| # | Element | DTO Field (Required) | Current DTO | Store Property | Empty State | Error State | Permission | Gap Type | Action |
|---|---------|---------------------|-------------|----------------|-------------|-------------|------------|----------|--------|
| L1 | 阶段徽章 "7/7" | phase_navigation[6].index | ✅ | ✅ | N/A | N/A | Public | ✅ Existing | 确认 |
| L2 | 阶段标题 | selected_phase_summary.name | ✅ | ✅ | "决算" | N/A | Public | ✅ Existing | 确认 |
| L3 | 阶段描述 | selected_phase_summary.description | ✅ | ✅ | "后续任务承接" | N/A | Public | ✅ Existing | 确认 |
| L4 | 步骤引导条 | N/A | N/A | N/A | N/A | N/A | Public | 🟡 **New QML Only** | 纯视觉 |
| L5 | 总督轮换面板 | **缺失** — 需 resolution_view.governors[] | ResolutionCommand 有底层逻辑 | 需新增 Store | "无总督" | "数据不可用" | Current player | 🔴 **API Missing + DTO Missing** | 新建 resolution_api.py + governor_view DTO |
| L6 | 民变检查面板 | **缺失** — 可用 province.grievance | Province 有 grievance 字段 | 需新增 Store 属性 | "无行省" | "数据不可用" | Public | 🔴 **DTO Missing** | 新建 grievance_view DTO |
| L7 | 进入新年按钮 | **缺失** — 需 resolution_api.advance_year() | game_api.advance_year() 存在但仅 CLI | 需新增 Slot | disabled | API 异常 | Current player | 🔴 **API Missing** | 新建 GUI 安全 advance_year 封装 |

### L 区缺口汇总
- **Existing: 3** (L1,L2,L3)
- **New QML Only: 1** (L4)
- **API Missing + DTO Missing: 3** (L5,L6,L7)

---

## 全报告汇总

| 阶段 | Existing | New QML Only | Derived | Store Missing | DTO Missing | API Missing | Backend Gap | Deferred | Permission | Decision Needed |
|------|----------|-------------|---------|--------------|-------------|-------------|-------------|----------|------------|----------------|
| A 顶栏 | 6 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| B 导航 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C 右面板 | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| D 底栏 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 |
| E Modal | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| F 天命 | 15 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| G 收入 | 7 | 1 | 1 | 0 | 14 | 1 | 0 | 0 | 3 | 0 |
| **H 广场** | **3** | **2** | **0** | **8** | **0** | **0** | **2** | **0** | **0** | **0** |
| I 人口 | 8 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| J 元老院 | 14 | 1 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| K 战争 | 3 | 1 | 0 | 0 | 1 | 4 | 0 | 0 | 0 | 0 |
| L 决算 | 3 | 1 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 |
| **总计** | **80** | **10** | **1** | **13** | **18** | **7** | **2** | **8** | **3** | **2** |

### 按 Gap 类型排序的优先级

| 优先级 | Gap 类型 | 数量 | 说明 |
|--------|---------|------|------|
| P0 | Existing | 80 | 无需修改, 确认字段名一致即可 |
| P1 | **Store Missing** | **13** | 后端数据存在, 仅需在 Store 新增 Property/Slot. 广场(8) + 元老院(4) + 顶栏(1) |
| P1 | **DTO Missing** | **18** | 需新建数据结构. 收入(14) + 战争(1) + 决算(1) + 顶栏(1) + 右栏(1) |
| P1 | **API Missing** | **7** | 需新建 API 包装. 战争(4) + 决算(2) + 收入(1) |
| P2 | **New QML Only** | 10 | 纯视觉元素(步骤条), 无后端依赖, 可随时重建 |
| P2 | **Permission** | 3 | 收入阶段权限规则已确认, 需在 DTO 层实现过滤 |
| P3 | **Backend Gap** | 2 | H7(子环节机) + H15(advance_phase), 需新功能 |
| P3 | **Deferred** | 8 | 底部占位查询按钮 |
| — | **Decision Needed** | 2 | F15(war_threat 类型) + C7(日志归属) |

---

*报告生成: 奥古斯都 (OC) | 2026-07-10 22:28*
*代码基准: `main` (65bbf67)*
*附注: 此报告应配合 `GUI_CONTROL_MAPPING_MATRIX.md` 和 `GUI_PHASE_INTEGRATION_PLAN.md` 使用*
