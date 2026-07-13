# Codex 审阅意见：GUI_PHASE_INTEGRATION_PLAN

审阅日期：2026-07-10  
审阅对象：`GUI_PHASE_INTEGRATION_PLAN.md`  
审阅角色：EOR GUI 开发顾问 / Codex  
结论：**有条件通过。Phase 1 方向正确，但需小范围修正后才能作为正式执行计划。**

## 一、总体判断

OC 本轮 Phase Integration Plan 的主线是正确的：

- 采用 B 路线：保留 `GuiApp / GuiSessionStore / GuiApiAdapter`，重建 QML 页面与组件。
- Phase 1 聚焦 Shell 外壳 + 天命 Vertical Slice。
- 明确把收入、广场、元老院交互、战争、决算放到后续阶段。
- 明确通用 `advancePhase`、子步骤计数、复杂 Backend Gap 不阻塞 Phase 1。
- 底部已实现查询按钮和 Deferred 查询按钮做了区分。
- 第一个 Vertical Slice 选择天命阶段，符合前两份审阅结论。

因此，这份计划可以作为后续开发路线的基础。  
但仍有几处范围和决策表述需要修正，避免 OC 在执行时扩大 Phase 1 或提前实现未确认规则。

## 二、必须修正项

### 1. Phase 6 中 A5 稳定度“最终处理”仍然越界

当前计划第 8 节写：

> A5 稳定度：从行省民变推导（每级 25%，多行省加权平均），顶栏恢复展示。

问题：

- 这与 DTO Gap 审阅意见冲突。
- 当前 EOR 尚未正式定义“国家稳定度”规则。
- `province.grievance` 是行省民怨，不等价于全局稳定度。
- 不能在 Phase Plan 中把“可选方案”写成最终处理。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| 从行省民变推导，顶栏恢复展示 | Decision Needed：暂不实现；如需稳定度，另立产品/规则设计任务 |
| Phase 6 稳定度 | Phase 6 仅保留决策项，不承诺实现 |

Phase 1 保持隐藏/替换稳定度是正确的，请保留。

### 2. 收入阶段权限规则不能写“已获克劳狄乌斯确认”

当前计划第 4.2 节写：

> 权限规则（已获克劳狄乌斯确认）

问题：

- 前一轮 DTO Gap 审阅已经指出：Codex 尚未确认具体收入隐私规则。
- 本轮对话中也没有看到项目负责人正式确认“变动金额公开、余额保密”等细则。
- 收入权限规则会影响多玩家信息隔离，必须作为产品/规则确认项。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| 已获克劳狄乌斯确认 | 建议权限方案，待项目负责人确认 |
| 各派系变动金额公开 | 建议方案 |
| 派系余额仅本派系可见 | 建议方案 |
| 人物土地收入公开 / 私产保密 | 建议方案 |

这不影响 Phase 1，但会阻塞收入阶段正式开发。

### 3. Phase 1 “无 API 变更”表述不够准确

当前计划中 Phase 1 工作量估算写：

> 本地影响，无 API 变更

但 Phase 1 同时包含：

> `session_store.py` 新增 `Store.warCount` Property，从 `senate_view.summary.active_foreign_war_count` 暴露。

这不是 API 层变更，但属于 Store 对 QML 的公开接口变化。

建议修正：

- “无 API 变更”改为“无 Core/API 业务变更；有轻量 Store 只读 Property 新增”。
- 测试要求中增加：
  - `test_gui/test_session_api.py`
  - `test_gui/test_adapter.py`
  - `test_gui/test_qml_startup.py`
  - 新增或更新 Store/QML 对 `warCount` 的最小断言。

### 4. Phase 1 测试要求不应硬编码 `773 passed`

当前计划多处写：

> 773 passed  
> ≥773 passed

问题：

- 测试数量会随分支和新增测试变化。
- 硬编码数字容易造成误判。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| 773 passed / ≥773 passed | 当前基准全量测试通过；新增测试不得减少覆盖；若测试数量变化，报告实际数量 |

Phase 验收应关注：

- 全量回归通过。
- 新增/更新 GUI 测试通过。
- 失败测试必须说明是否与本任务相关。

### 5. 验收条件中的 Git commit 不应作为强制条件

当前计划第 12 节写：

> Git 已 commit

问题：

- 当前工作流中，Git push 明确需要授权；commit 是否由 OC 执行也应受项目负责人安排。
- 文档计划不应把 commit 作为 GUI 验收必要条件。

建议修正：

| 当前写法 | 建议写法 |
| --- | --- |
| Git 已 commit | 如项目负责人要求，由执行者提交 commit；否则交付修改清单、测试结果、审查报告即可 |

### 6. Phase 5 依赖关系前后不一致

当前文档中存在两种说法：

- Phase 5 依赖 Phase 1+2+3+4 完成。
- Phase 决策矩阵中 Phase 5 依赖写为 Phase 1-3。

建议统一为：

> Phase 5 依赖 Phase 1 完成，并建议在 Phase 2-4 主要 GUI/API 模式稳定后启动；如果资源允许，可单独做 Combat/Resolution API 预研，但不进入正式 GUI 集成。

不要让 Phase 5 的依赖过硬或过松。战争/决算确实复杂，但不一定必须等元老院交互化完成才能做 API 预研。

### 7. 角色名缩写需要明确或删除

当前计划中出现：

- SA 审查
- DA 验收报告
- QGD 审查
- T03 仓库架构冻结

如果这些是 EOR 项目内已有角色/流程，可以保留，但需要在文档中定义。  
如果不是正式流程，建议删除或改成通用表述：

- 架构审查
- GUI 验收报告
- 设计/规则审查
- 仓库架构变更风险

避免 OC 后续不知道找谁验收。

## 三、可以保留的关键决策

以下内容建议保留：

1. **Phase 1 = Shell + Mortality**
   - 这是正确的第一阶段目标。
   - 可验证外壳、主题、导航、弹窗、底部查询、天命动作链路。

2. **Phase 1 不做 A5 稳定度、C2 通用 advancePhase、C3 子步骤计数**
   - 这是正确的范围控制。
   - 天命继续使用现有 `doAdvanceMortality()`。

3. **Phase 2a / 2b 拆分人口视觉与收入数据层**
   - 人口视觉可做较快成果。
   - 收入数据层较重，适合作为独立任务。

4. **广场阶段排在 Forum 专项**
   - `forum_api.py` 已有能力，但 GUI 连接层缺失。
   - 适合单独作为 Phase 3。

5. **元老院交互化单独作为 Phase 4**
   - 只读已有，交互扩展风险较高。
   - 单独规划合理。

6. **战争/决算放后**
   - 需要 GUI 安全 API。
   - 禁止直接复用 CLI Command。

## 四、Phase 1 是否可以进入执行

建议：**修正文档后，可以进入 Phase 1 开发任务书编写。**

Phase 1 开发任务书必须明确：

- 只做 Shell + 天命 Vertical Slice。
- 不实现稳定度。
- 不实现 Store 统一日志。
- 不实现通用 `advancePhase`。
- 不实现收入、广场、人口、元老院、战争、决算。
- 不新增 Core 规则。
- 不调用 CLI Command。
- 新 QML 只通过 `sessionStore` 读写。

## 五、最终结论

结论：**有条件通过。**

这份 Phase Plan 的大方向已经可用，尤其 Phase 1 的范围基本正确。请 OC 按本审阅意见修正少量越界表述和验收条件后，即可由顾问输出下一份正式开发指令：`New Global Shell + Mortality Vertical Slice`。
