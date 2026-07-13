# GUI v3.25.1 阶段集成计划

> 文件 3/3 | 2026-07-10 | 代码基准: `main` (65bbf67)
> 基于: `GUI_CONTROL_MAPPING_MATRIX.md` + `GUI_DTO_GAP_REPORT.md`
> 角色: PM + SA — 阶段划分、依赖分析、实施排序

---

## 1. 设计原则

### 1.1 递增交付

每次 Phase 交付一个可运行、可验证的 GUI 子集。不得跨 Phase 打包依赖。

### 1.2 Shell First, Content Second

视觉外壳（顶栏/导航/右侧栏/底部栏/弹窗）先对齐 v3.25.1，内容区逐步替换。

### 1.3 Vertical Slice 验证

每个 Phase 必须至少有一条完整的 API→Adapter→Store→QML 链路可执行验证，不得仅交付"纯视觉无数据"的页面。

### 1.4 Backend Gap 不阻塞 Phase 1

需要后端新增功能（子环节状态机、通用 advancePhase、combat_api.py 等）的条目推迟到 Phase 2+，Phase 1 只做 API Existing 的工作。

### 1.5 重建 vs 复用

| 状态 | 原则 |
|------|------|
| **Existing / Reuse** | 不动 QML，仅确认字段名一致。 |
| **Reuse + style update** | 修改现有 QML 的样式绑定，不重构逻辑。 |
| **Rebuild** | 整体或用新 QML 替代。样式严格对齐 v3.25.1 HTML。 |
| **New QML** | Matrix / Gap Report 中标注 New 的组件需新建。 |
| **Deferred** | 保持占位，Phase 1 不碰。 |

---

## 2. Phase 架构总览

```
Phase 1  →  Shell (A-E) + Mortality (F)
                ↓ 验证：天命全链路可用
Phase 2  →  Population (I) + Revenue DTO (G 数据层)
                ↓ 验证：人口全链路 + 收入数据可用
Phase 3  →  Forum (H) — API存在，GUI 重建
                ↓ 验证：广场全链路
Phase 4  →  Senate Interactive (J 交互扩展)
                ↓ 验证：提案/投票/否决/结算
Phase 5  →  Combat (K) + Resolution (L) — API 新建
                ↓ 验证：战斗 + 新年循环完整
Phase 6  →  Deferred Items + Polish + Decisions
```

### 各 Phase 工作量估算

| Phase | 范围 | 文件涉及量 | 测试影响 | 依赖性 |
|-------|------|-----------|---------|--------|
| **Phase 1** | A-E Shell 视觉对齐 + F 视觉重建 | ~6 QML 文件修改 + ~2 Store/Slot | 本地影响，无 API 变更 | 无 — 独立 |
| **Phase 2a** | I QML 视觉重建 | ~3 QML 子视图文件修改 | 无 API 变更 | 依赖 Phase 1 Shell (样式基线) |
| **Phase 2b** | G 收入 DTO + API 层 | `revenue_api.py`(新) + DTO 类 + Adapter + Store 属性 | 需新增 revenue_api 测试 | 无 (独立) |
| **Phase 3** | H Forum 全重建 | Adapter + Store + ForumStage.qml | 需 forum_api 单元测试 → 存在 | 依赖 Phase 1 Shell |
| **Phase 4** | J Senate 交互升级 | Adapter 新增方法 + Store Slot + SenateStage.qml | 需 senate_api 测试 | 依赖 Phase 1 Shell |
| **Phase 5** | K+L Combat + Resolution | `combat_api.py`(新) + `resolution_api.py`(新) + QML | 需完整新 API 测试 | 依赖 Phase 1+2+3+4 完成 |
| **Phase 6** | 底部查询按钮 + 决策项 + 稳定度 | 多处小改 | 本地 QML | 无 |

---

## 3. Phase 1 详细计划 — Shell 外壳 + 天命垂直切片

### 3.1 目标

将 EOR 游戏 GUI 的 5 个 Shell 区域（A 顶栏 / B 阶段导航 / C 右侧栏 / D 底部栏 / E 弹窗）视觉对齐 v3.25.1 HTML 原型，同时重建天命阶段（F）的视觉呈现——形成一条完整的垂直切片。

### 3.2 范围

#### ✅ IN SCOPE

| 区域 | 条目 | 动作 | 类型 | 工作量 |
|------|------|------|------|--------|
| **A 顶栏** | A1-A4, A7-A8 | QML 样式调整（字体/间距/颜色） | Reuse + style update | ⚪ 轻量 |
| **A 顶栏** | A6 战争数 | Store 新增 `warCount` Property | Store Missing | ⚪ 轻量 |
| **B 导航** | B1-B4 | PhaseRail -> 44px 圆形图标 + hover 名称 | Rebuild (New QML) | 🟡 中等 |
| **B 导航** | B5-B6 | 刷新/说明按钮 — 保持 | Reuse | ⚪ 轻量 |
| **C 右栏** | C1, C4-C8 | 样式更新（内容区布局/日志终端风格） | Reuse + style update | ⚪ 轻量 |
| **C 右栏** | C2 advancePhase | 标记为 Phase 2+，Phase 1 不动 | 推迟 | — |
| **C 右栏** | C3 进度指示 | 标记为 Phase 2，Phase 1 隐藏 | 推迟 | — |
| **D 底栏** | D1 | 视觉改色（深朱红） | Rebuild (style) | ⚪ 轻量 |
| **D 底栏** | D2, D4, D10, D11 | 现有 4 个查询按钮 — 样式更新 | Reuse + style update | ⚪ 轻量 |
| **D 底栏** | D3,D5-D9,D12,D13 | 占位按钮 — 保持不变 | Deferred | — |
| **E 弹窗** | E1-E6 | Modal/Overlay 视觉对齐 | Reuse + style update | ⚪ 轻量 |
| **F 天命** | F1-F3 | 徽章/标题/描述 — 样式更新 | Reuse + style update | ⚪ 轻量 |
| **F 天命** | F4-F6 | 步骤引导条（2步骤） | New QML Only | 🟡 中等 |
| **F 天命** | F7-F14 | 事件展示区 → 羊皮纸卡片风格 | Rebuild (style) | 🟡 中等 |
| **F 天命** | F16-F19 | 执行/推进按钮 — 样式更新 | Reuse + style update | ⚪ 轻量 |

#### ❌ OUT OF SCOPE (Phase 1)

| 条目 | 原因 |
|------|------|
| A5 稳定度 | Deferred — 待产品规则确认 |
| C2 通用 advancePhase | Phase 2+ — Codex 决策 |
| C3 子步骤计数 DTO | Phase 2+ |
| F15 war_threat 类型确认 | 待确认 API 返回值 |
| G 收入阶段全区域 | Phase 2 |
| H 广场阶段全区域 | Phase 3 |
| I 人口阶段（保留现有QML） | Phase 2 (仅样式重建，数据不动) |
| J 元老院交互扩展 | Phase 4 |
| K+L 战争+决算 | Phase 5 |
| D 底部 8 个占位按钮 | Phase 6 |

### 3.3 实施步骤

#### Step 1: 新建 Shell 组件

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P1-01 | `PhaseRailIcon.qml` (新建) | 44px 圆形图标 + hover 名称弹出 | 替代现有 176px 文本条目，7 个图标映射由 Store.phaseNavigation[].id 驱动 |
| P1-02 | `StepBar.qml` (新建) | 通用步骤引导条组件 | 传入 steps[] + currentStep，水平排列圆圈+连线。首次在天命阶段实例化。 |

#### Step 2: 修改 Shell QML

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P1-03 | `TopStatusBar.qml` | 样式更新 | 字体/间距/颜色对齐 v3.25.1。新增 `Store.warCount` 绑定（Phase 1 展示，若无数据则隐藏）。 |
| P1-04 | `PhaseRail.qml` | 替换为 PhaseRailIcon | 删除 176px 文本列表，嵌入 PhaseRailIcon 组件。保留刷新/说明按钮。 |
| P1-05 | `ContextPanel.qml` | 样式更新 | 内容区布局/字体/颜色对齐 v3.25.1。删除进度指示（Phase 2 重做）。保留 C7 日志区为当前 FeedbackPanel。 |
| P1-06 | `BottomQueryBar.qml` | 样式更新 | 深朱红背景。现有 4 个按钮样式更新，占位按钮保持原样。 |
| P1-07 | `QueryResultOverlay.qml` | 样式更新 | 模态框遮罩/标题/内容区/关闭按钮视觉对齐。 |

#### Step 3: 修改天命 QML

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P1-08 | `MortalityStage.qml` | 视觉重建 | 插入 StepBar 组件（2步骤：执行天命→查看事件）。事件展示区改为羊皮纸卡片。影响项列表改用 `ListItem` 风格。按钮样式对齐 v3.25.1。 |

#### Step 4: Store 层修改

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P1-09 | `session_store.py` | `Store.warCount` 新增 | 从 senate_view.summary.active_foreign_war_count 暴露。只读 Property。 |

#### Step 5: 回归测试确认

- 运行全量 `pytest`
- 验证：773 passed ✅（如有新增测试，应 ≥773）
- 无需新测试（无 API 级别变更）

### 3.4 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| AC1 | 顶栏显示：图标/国库/派系金库/影响力/回合/玩家，战争数从后端数据获取 | 手动检查 |
| AC2 | 阶段导航为 44px 圆形图标，hover 显示名称，当前阶段高亮 | 手动检查 |
| AC3 | 右侧面板显示当前阶段摘要/派系名/人物数 | 手动检查 |
| AC4 | 底部栏深朱红，4 个有效查询按钮可用，占位按钮保持占位 | 手动检查 |
| AC5 | 弹窗遮罩/标题/内容区视觉对齐 v3.25.1 | 手动检查 |
| AC6 | 天命阶段显示 2 步骤条、羊皮纸事件卡片、执行/推进按钮 | 手动检查 |
| AC7 | 天命按钮功能正常（执行→推进→进入收入阶段） | 手动启动游戏 |
| AC8 | 回归测试 ≥773 passed（新增 0） | pytest |

### 3.5 风险

| 风险 | 缓解 |
|------|------|
| PhaseRailIcon 44px 圆形图标不够清晰（中文图标集） | 确认图标使用现有 HTML 字符映射（🎴💰🏛️等），hover 显示完整名称 |
| 羊皮纸卡片风格在 QML 实现有性能开销 | 使用简单 Rectangle+Border+DropShadow，不要复杂纹理 |
| 现有测试不覆盖 QML 视觉 | 依赖性低 — 视觉不影响后端逻辑 |
| Phase 1 改动不满足 Codex 内容提交规范 | Phase 1 交付前做 SA 审查 |

---

## 4. Phase 2 计划大纲 — 人口 + 收入数据层

### 4.1 人口阶段（I）— 视觉重建

人口是全链路最完整的阶段（8/9 Existing），Phase 2 只需视觉对齐。

#### 范围

| 条目 | 动作 | 工作量 |
|------|------|--------|
| I4 步骤引导条 | 新建 StepBar（本阶段: 赞助庆典→官职投票→选举结果） | 🟡 中等 |
| I5 人物列表 → 卡片 | QML 视觉重建 | 🟡 中等 |
| I6 庆典赞助 → 视觉对齐 | 输入+按钮样式更新 | ⚪ 轻量 |
| I7 官职投票 → 视觉对齐 | 候选人卡片样式更新 | ⚪ 轻量 |
| I8-I9 状态按钮 → 样式更新 | 按钮/指示器对齐 | ⚪ 轻量 |

#### 预估工作量：~3 QML 子视图文件修改

### 4.2 收入阶段（G）— 数据层构筑

这是 Phase 2 最重的工作，但数据设计和 API 实现与视觉可以独立进行。

#### 范围

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P2-R1 | `revenue_api.py` (新建) | 收入阶段 API | `get_revenue_view()`, `execute_revenue()`。Service 层 `EconomicService.settle_revenue_phase()` 已存在，需包装为安全 GUI API。 |
| P2-R2 | Revenue DTO 类 | `revenue_view` 数据类 | 含：public_land_income, war_indemnity, province_tax, other_income, legion_maintenance, fleet_maintenance, province_operation, other_expenses, faction_revenue[] (每个派系: name, revenue_change, total_after), figure_private_income[] (人物: name, income, faction), treasury_before, treasury_after, net_change |
| P2-R3 | `api_adapter.py` | 新增 revenue 方法 | `get_revenue_view()`, `execute_revenue()` |
| P2-R4 | `session_store.py` | 新增收入阶段属性 | `revenueView` (dict), `canExecuteRevenue` (bool), `doExecuteRevenue()` Slot |
| P2-R5 | `RevenueStage.qml` (新建或重建) | 收入阶段视觉 | 基于 v3.25.1 HTML 的布局：📈 国家收入列表 → 📉 国家支出列表 → 🏛️ 派系财政列表 → 🌾 地主私人收益 → 国库净变化 → ✅ 确认按钮 |

#### 权限规则（已获克劳狄乌斯确认）

| 区域 | 权限 |
|------|------|
| 国家收入/支出明细 | 对**所有玩家公开** |
| 各派系财政**变动金额** | 公开（可看到各派系 +XX T / -XX T） |
| 各派系**现有金库余额** | **仅本派系可见**（保密） |
| 人物土地**收入金额** | 公开 |
| 人物**现有私产** | **仅本派系可见**（保密） |

---

## 5. Phase 3 计划大纲 — 广场重建（Forum）

### 背景

`forum_api.py` 包含 8 个完整后端 API 函数（retire_figure / recruit_figure / place_bid / buy_land / vote_triumph / transact_land / resolve_forum / resolve_land_trades），全链路 API Existing。但 GUI 连接层零存在（无 Adapter 方法、无 Store 属性、无 ForumStage.qml）。

### 范围

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P3-01 | `api_adapter.py` | 新增 forum 方法 | `get_forum_view()`, `retire_figure()`, `recruit_figure()`, `place_bid()`, `buy_land()`, `vote_triumph()`, `resolve_forum()` |
| P3-02 | `session_store.py` | 新增 forum 属性 | `forumView` (dict), `canRetire` / `canRecruit` / `canBid` / `canBuyLand` / `canVoteTriumph` / `canResolveForum` (bools), 对应 doXxx() Slot |
| P3-03 | `ForumStage.qml` (新建) | 广场阶段全 UI | 3 子环节布局：解雇面板 / 人才市场（招募+竞标+公地+凯旋） / 公示结算。3 步骤 StepBar。 |
| P3-04 | 回归测试 | 确认 forum_api 测试 + 新 Adapter 测试 | 新增 pytest 测试覆盖 Adapter 层 |

---

## 6. Phase 4 计划大纲 — 元老院交互化

### 背景

元老院 API 层存在完整交互能力（senate_api.py: propose / vote / veto / resolve_senate），但 Adapter/Store/QML 全部只读。交互化需确定范围——克劳狄乌斯已确认需单独规划。

### 范围

| # | 文件 | 动作 | 说明 |
|---|------|------|------|
| P4-01 | `api_adapter.py` | 新增 senate 交互方法 | `propose()`, `vote()`, `veto()`, `resolve_senate()` |
| P4-02 | `session_store.py` | 新增交互属性/Slot | `senateProposals`, `canPropose` / `canVote` / `canVeto` / `canResolve`, 对应 doXxx() Slot |
| P4-03 | `SenateStage.qml` | 重大改建 | 从 6 个只读 Section → 3 面板交互布局：提案面板（创建/查看提案） / 投票面板（对提案表决） / 主持官面板（否决/结算）。保留只读信息区。 |

---

## 7. Phase 5 计划大纲 — 战争 + 决算

### 要求

两个阶段都需要新建 API（combat_api.py / resolution_api.py），因此排到最后。

### 战争阶段

| 文件 | 动作 |
|------|------|
| `combat_api.py` (新建) | 安全包装 WarSystem + CombatCommand。函数：`get_war_view()`, `execute_battle()`, `negotiate_treaty()`。 |
| Adapter + Store | 对应方法/属性 |
| `CombatStage.qml` (新建) | 多战争并排面板 | 军力对比 / 战斗动画 / 结果展示 / 停战谈判 |

### 决算阶段

| 文件 | 动作 |
|------|------|
| `resolution_api.py` (新建) | 安全包装 ResolutionCommand + advance_year。函数：`get_resolution_view()`, `rotate_governors()`, `check_grievances()`, `advance_year()`。 |
| Adapter + Store | 对应方法/属性 |
| `ResolutionStage.qml` (新建) | 总督轮换 / 民变检查 / 进入新年 |

---

## 8. Phase 6 — 收尾 + 决策项

### 底部占位按钮

8 个占位查询按钮（人物查询/派系金库/公地/私地/合同/行省/舰队/帮助）。逐个实现或批量实现。

### 待定决策

| # | 决策 | Phase 1 立场 | 最终处理 |
|---|------|-------------|---------|
| A5 稳定度 | 隐藏/替换 | 从行省民变推导（每级 25%，多行省加权平均），顶栏恢复展示 |
| C7 日志归属 | 保留 QML 本地 | 如需跨阶段历史日志 → 迁移到 Store。否则保持。 |
| F15 war_threat 类型 | 保持现有 | 确认 mortality_api 是否返回 war_threat → 补齐渲染 |
| C2 advancePhase | Phase 2+ | 新建 `session_api.advance_phase()` + Store `doAdvancePhase()` — 所有阶段推进按钮统一调用 |

---

## 9. 依赖图

```
Phase 1 ─── Shell + Mortality
   │
   ├──→ Phase 2a ─── Population (视觉独立，可并行于 2b)
   │
   ├──→ Phase 2b ─── Revenue DTO + API (数据独立，可并行于 2a)
   │
   ├──→ Phase 3 ──── Forum (依赖 Phase 1 Shell 基线)
   │
   ├──→ Phase 4 ──── Senate Interactive (依赖 Phase 1 Shell 基线)
   │
   └──→ Phase 5 ──── Combat + Resolution (依赖 Phase 1-4 全部完成)
                              │
                              └──→ Phase 6 ──── Polish + Deferred
```

### 并行可能性

| 并行组 | 任务 | 约束 |
|--------|------|------|
| Group A | Phase 1 (Shell + Mortality) | 必须最先完成 |
| Group B | Phase 2a (Population 视觉) + Phase 2b (Revenue 数据层) | 可并行，依赖 Phase 1 Shell 基线 |
| Group C | Phase 3 (Forum) + Phase 4 (Senate Interactive) | 可并行，依赖 Phase 1 Shell 基线 |
| Group D | Phase 5 (Combat + Resolution) | 需 Phase 1-4 完成 |
| Group E | Phase 6 (Polish) | 全局收尾，最后 |

### 最小可玩版本

如果资源有限，可按以下优先级裁断：

```
Phase 1 → Shell + Mortality
    就是最小可玩版本。（有外壳 + 天命全流程）

Phase 1 + Phase 2b → 收入结算可用
    预算+经济可视化。

Phase 1 + Phase 3 → 广场玩家交互可用
    如果目标是"让玩家先在广场阶段有操作感"。

Phase 1 + Phase 2a → 人口选举可用
    最简单的内容补全（代码工作量最小）。
```

---

## 10. Phase 决策矩阵

| 维度 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 |
|------|---------|---------|---------|---------|---------|---------|
| **API 新建** | 0 | 1 (revenue) | 0 | 0 | 2 (combat+resolution) | 0 |
| **DTO 新建** | 0 | 14 (revenue) | 0 | 4 (senate交互) | 2 (war+resolution) | 0 |
| **Store 修改** | 1 (warCount) | ~10 (revenue+population) | ~8 (forum+adapter) | ~4 (senate slots) | ~8 (combat+resolution) | ~4 (queries) |
| **QML 新建** | 2 (PhaseRailIcon+StepBar) | 1 (RevenueStage) | 1 (ForumStage) | 1 (SenateStage重型) | 2 (CombatStage+ResolutionStage) | 8 (query dialogs) |
| **QML 修改** | 6 | ~3 (PopulationStage) | 0 | 0 | 0 | 多处小改 |
| **回归测试** | ≥773 | ≥773 + new | ≥773 + new | ≥773 + new | ≥773 + new | ≥773 + new |
| **依赖** | 无 | Phase 1 | Phase 1 | Phase 1 | Phase 1-3 | Phase 1-5 |

---

## 11. 推荐执行顺序

### 推荐路线

```
Phase 1 (Shell + Mortality)
   ↓ 验收 → 确认外壳 + 天命垂直切片可用
Phase 2b (Revenue DTO + API)  ← 优先收入数据层，因工作量最大
   ║
Phase 2a (Population Visual)  ← 可并行于 2b，视觉独立
   ↓
Phase 3 (Forum)
   ↓
Phase 4 (Senate Interactive)
   ↓
Phase 5 (Combat + Resolution)
   ↓
Phase 6 (Polish + Deferred)
```

### 替代路线（玩家交互优先）

```
Phase 1 (Shell + Mortality)
   ↓
Phase 3 (Forum — 玩家有广场操作)
   ↓
Phase 2b (Revenue — 经济可视化)
   ↓
Phase 2a (Population — 选举)
   ↓
Phase 4 (Senate — 元老院交互)
   ↓
Phase 5 (Combat + Resolution)
   ↓
Phase 6 (Polish)
```

---

## 12. 每 Phase 交付检查清单

### 📦 Phase 交付件

```
Phase N 交付包:
├── 修改文件清单
├── 新建文件清单
├── 测试结果（≥773 passed + 新增测试数）
├── SA 审查报告
└── 验收状态（PASS / FAIL / PARTIAL）
```

### 验收通过条件

```
1. 回归测试全部通过
2. 该 Phase 范围的 Acceptance Criteria 全部满足
3. 无新的 BLOCKED 依赖产生
4. DA 验收报告已创建
5. Git 已 commit（在该 Phase 范围内，不跨 Phase 堆积）
```

---

## 13. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Phase 1 Shell 改动与现有 QML 布局冲突 | 中 | 中 | 每次只改一个文件，逐文件回归测试 |
| Revenue DTO 设计完成后发现 EconomicService 数据不足 | 低 | 高 | Phase 2b 开始前先审计 EconomicService 输出 |
| Forum API 过于紧密耦合（resolve_forum 一次结算全部） | 中 | 中 | Adapter 层拆分为独立 Slot，不与前端子环节直接耦合 |
| Senate 交互范围待定 → Phase 4 可能重新设计 | 高 | 中 | Phase 4 启动前单独做 SA 边界审查 |
| Combat + Resolution API 设计复杂（战争模拟） | 中 | 高 | Phase 5 前 QGD 审查；第一次只做最小战斗接口 |
| T03 仓库架构冻结恢复 → 文件路径变更 | 低 | 高 | 代码库以 Git 为准，Phase 1 尽量不改现有目录结构 |

---

*计划生成: 奥古斯都 (OC) | 2026-07-10 22:55*
*代码基准: `main` (65bbf67)*
*配套文件: `GUI_CONTROL_MAPPING_MATRIX.md` + `GUI_DTO_GAP_REPORT.md`*
