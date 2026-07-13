# Codex 审阅意见：GUI_DTO_GAP_REPORT

审阅日期：2026-07-10  
审阅对象：`GUI_DTO_GAP_REPORT.md`  
审阅角色：EOR GUI 开发顾问 / Codex  
结论：**有条件通过，需小范围修正后可继续进入 `GUI_PHASE_INTEGRATION_PLAN`。**

## 一、总体判断

OC 本轮 DTO Gap Report 基本承接了 `GUI_CONTROL_MAPPING_MATRIX.md` 与 Codex 上轮审阅意见，尤其做对了以下几点：

- 收入阶段已从“后端完全缺失”修正为“`EconomicService` 已有，缺 GUI API / DTO / Store / QML”。
- 广场阶段正确识别为 `forum_api.py` 已有能力，主要缺 Adapter / Store / QML 暴露。
- 人口阶段识别为当前 GUI 链路最完整阶段。
- 元老院阶段正确区分“只读 DTO 已通”和“交互能力 API 有但 GUI 未暴露”。
- 战争、决算阶段已避免简单说 Core 完全缺失，而是标记为缺 GUI API / DTO / Store。

因此，这份报告可以作为 Phase Plan 的主要依据。  
但有几处会影响优先级和范围控制，建议先修正。

## 二、必须修正项

### 1. A5 稳定度不应直接列为 P1 DTO Missing

当前报告：

> A5 稳定度：DTO Missing，建议新增 `snapshot.stability`，从 `province.grievance` 加权推导。

问题：

- v3.25.1 HTML 中的稳定度更像视觉占位或未来状态指标。
- 当前 EOR 没有明确“国家稳定度”游戏规则。
- `province.grievance` 是行省民怨，不等价于全局稳定度。
- 将它作为 P1 DTO Missing 会诱导 OC 在 GUI 阶段发明规则或强行推导产品概念。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| DTO Missing | Decision Needed / Deferred Placeholder |
| 新增 `snapshot.stability` | 暂不新增，等待产品/规则确认 |
| 从 grievance 加权推导 | 仅作为可选方案记录，不进入 P1 |

建议在 Phase Plan 中处理为：

- 新 Shell 顶栏先隐藏或替换稳定度。
- 不阻塞天命 Vertical Slice。
- 后续若项目确认“稳定度”是正式规则，再单独设计 DTO。

### 2. C7 日志归属不能写成“Codex 确认 Store 统一管理”

当前报告：

> Decision Needed；Action: Codex 确认 Store 统一管理。

问题：

- Codex 上轮审阅只要求标记为 Decision Needed。
- 尚未正式确认日志必须进入 Store。
- 当前 `FeedbackPanel` 是 QML 本地队列，短期内可继续使用。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| Codex 确认 Store 统一管理 | Decision Needed：短期保留 QML 本地，长期评估 Store 统一 |
| Store 环形缓冲区 | 可选方案，不作为 Phase 1 必须项 |

Phase Plan 建议：

- New Shell 阶段保留现有反馈/日志链路。
- 不因日志 Store 化阻塞 Shell 和天命切片。
- 如果后续要做跨阶段历史日志，再建立 Store 统一日志任务。

### 3. 底部查询 D 区统计需要拆清 D10 / D11

当前报告中 D 区使用：

> D5-D13 其余 8 个查询 Deferred

但汇总又写：

> Existing: 4 (D1, D2, D4, future D10-D11 war_list/legion_status)

问题：

- `war_list` 与 `legion_status` 在 Matrix 中已标记 Existing。
- D5-D13 合并行容易误读为 D10/D11 也 Deferred。
- 汇总数量虽大体正确，但表格表达不清。

建议修正：

请将 D 区拆成：

| 元素 | 建议状态 |
| --- | --- |
| D10 战争列表 | Existing |
| D11 军团状态 | Existing |
| D3、D5-D9、D12、D13 | Deferred |

这样后续 Phase Plan 才能正确安排底部查询栏：已接入查询可以随 Shell 视觉重建保留，Deferred 查询继续 disabled/placeholder。

### 4. 收入阶段权限规则不要写成“Codex 已确认”

当前报告中 G17/G20 等写：

> Codex 已确认权限规则。

问题：

- Codex 确认的是“必须注意多玩家信息隔离”，并未正式确认具体收入隐私规则。
- 派系财政、私人收益、私人余额是否公开，需要产品/规则层确认。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| Codex 已确认权限规则 | Permission Decision Needed |
| 变动金额公开，余额保密 | 建议方案，待确认 |
| income public, balance secret | 建议方案，待确认 |

这不阻塞 Phase 1 / 天命 Vertical Slice，但会阻塞收入阶段正式接入。

### 5. H7 / H15 不宜作为近期 Backend Gap 主线

当前报告将 H7 子环节状态机、H15 advance_phase 作为 Backend Gap。

这个分类可以保留，但建议在优先级上降级：

- H7 子环节状态机属于广场阶段复杂交互设计，不应进入新 Shell 或天命切片。
- H15 通用 advance_phase 已在上轮确认不应阻塞 Phase 1。
- 天命阶段继续使用 `doAdvanceMortality()`。

建议：

| 项 | 建议 |
| --- | --- |
| H7 | Phase 2+ / Forum-specific design |
| H15 | Phase 2+ / Unified phase advancement governance |
| P3 Backend Gap | 不进入近期执行队列 |

## 三、可以保留的关键判断

以下判断建议保留，并用于 `GUI_PHASE_INTEGRATION_PLAN.md`：

1. **天命阶段适合第一个 Vertical Slice**
   - Existing 15。
   - 仅步骤条是 New QML。
   - execute / result / advance / disabled reason 链路完整。

2. **人口阶段链路完整，但不适合作为第一片**
   - 功能完整，但交互比天命复杂。
   - 更适合作为天命之后的第二个阶段切片。

3. **收入阶段是主要 DTO/API 设计任务**
   - `EconomicService` 已有。
   - 需要 `revenue_api.py`、revenue view DTO、Store 暴露、权限过滤。
   - 不应塞进第一轮 QML Shell。

4. **广场阶段主要是 Store / Adapter / QML 暴露任务**
   - `forum_api.py` 已有能力。
   - 后续需要 forum view DTO 和 Slot 设计。

5. **元老院交互化应单独规划**
   - 当前只读全链路已通。
   - 提案/投票/否决/结算 API 存在，但 Adapter/Store/QML 未暴露。

6. **战争/决算需要后续 API 化治理**
   - 不应直接复用 CLI Command。
   - 需要 GUI 安全 API 和稳定 DTO。

## 四、是否允许继续下一步

建议：

1. OC 先小修 `GUI_DTO_GAP_REPORT.md`：
   - A5 稳定度改为 Deferred / Decision Needed。
   - C7 日志归属改为 Decision Needed，不写 Codex 已确认。
   - D 区拆出 D10/D11 Existing。
   - 收入权限规则改为待确认建议，不写 Codex 已确认。
   - H7/H15 标明 Phase 2+，不进入近期计划。

2. 修正后可继续输出 `GUI_PHASE_INTEGRATION_PLAN.md`。

3. Phase Plan 必须明确：
   - Phase 1 不新增稳定度 DTO。
   - Phase 1 不做 Store 统一日志。
   - Phase 1 不做通用 advancePhase。
   - 第一个 Vertical Slice 仍为天命阶段。

## 五、最终结论

结论：**有条件通过。**

这份 DTO Gap Report 的总体方向是正确的，已经足够支撑阶段计划；但需要修正少量“把未来产品决策误写成已确认需求”的问题。修正后，可以进入 `GUI_PHASE_INTEGRATION_PLAN.md`。
