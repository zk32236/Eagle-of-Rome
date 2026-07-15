# GUI-P0-04 PopulationStage Phase 4 PM意图包

日期：2026-07-16
角色：EOR PM
目标版本：EOR GUI v3.25.1 Phase 4 人口阶段
状态：Ready for SA Boundary / DA Implementation

## 1. 当前判断

Phase 3 广场阶段已完成本地归档并推送到远端 `main`。Phase 4 可以在当前 GUI Shell、Store、Adapter、API 基线之上启动。

本阶段不是重建 Shell，而是在既有 A-F 布局与 `PopulationStage.qml` 挂载点内，实现 v3.25.1 HTML 原型中的人口阶段真实 GUI 闭环。

主蓝图：

- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/00_GUI产品基线/EOR_GUI_Prototype_v3.25.1.html`

辅助对照：

- `C:/Users/Kerl/Downloads/GUI design - Phase 4A.PNG`
- `C:/Users/Kerl/Downloads/GUI design - Phase 4B.PNG`
- `C:/Users/Kerl/Downloads/GUI design - Phase 4C.PNG`

## 2. 阶段目标

Phase 4 人口阶段由两个可操作子阶段和一个结果展示状态组成：

| 子阶段 | 目标 |
| --- | --- |
| 庆典赞助 | 为本派系候选人输入赞助金额并调用人口阶段 campaign API |
| 投票选举 | 按官职选择候选人并调用 vote API |
| 结果展示 | 结算选举，中央公示区与候选人表展示结果，并允许推进后续阶段 |

## 3. 产品目标

按 HTML 原型复刻以下结构：

- 顶部阶段信息：`4 / 7`、`人口阶段 — 选举`、`庆典赞助 -> 投票选举 -> 结果公示`
- 步骤条：`公示区 -> 庆典赞助 -> 投票选举`
- 公示区：显示庆典决议、选举前/后派系影响力、选举完成摘要
- 候选人信息表：按官职聚合候选人，展示属性、影响力、派系、选举结果
- 下方面板：左侧庆典赞助，右侧投票选举
- 投票面板在庆典完成前显示锁定状态
- 完成投票后展示结果态，不仅依赖右侧事件日志

## 4. 允许范围

| 类型 | 路径 |
| --- | --- |
| 修改 | `src/ui/gui/qml/stages/PopulationStage.qml` |
| 修改/可选 | `src/ui/gui/session_store.py` |
| 修改/可选 | `src/ui/gui/api_adapter.py` |
| 修改/可选 | `src/api/session_api.py` |
| 修改/可选 | `src/api/population_api.py` |
| 修改/新增 | `src/tests/test_gui/` |
| 修改/新增 | `src/tests/test_api/test_population_api.py` |
| 新增 | `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-04/` |

## 5. 禁止范围

| 禁止项 | 说明 |
| --- | --- |
| 不重排 Shell | 不改变 TopStatusBar、PhaseRail、StageDesktop、ContextPanel、BottomQueryBar 的父子关系和主锚点 |
| 不绕过 Store/API | QML 只能通过 `GuiSessionStore` 属性与 Slot 操作 |
| 不在 QML 写核心规则 | 候选资格、扣财富、计票、授职必须由 API/Core 承担 |
| 不修改无关阶段 | 不回归 Mortality / Revenue / Forum / Senate |
| 不引入多玩家泄漏 | 不向 viewer 暴露不应显示的其他玩家隐私资源 |

## 6. 验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | PopulationStage 不再使用旧 Tab 结构，改为原型一致的候选人表 + 双面板 |
| AC-02 | 庆典赞助可对本派系候选人提交金额，成功后刷新财富/影响力并开放投票 |
| AC-03 | 投票区在赞助未完成前有明确锁定态 |
| AC-04 | 投票可按官职选择候选人并记录 `my_votes` |
| AC-05 | 选举结算使用 GUI session 入口，能产生结果并标记 population 已执行 |
| AC-06 | 结果在中央公示区与候选人表可见 |
| AC-07 | QML 启动测试通过，GUI session/adapter 测试通过 |
| AC-08 | 输出 SA/DA/开发报告，记录测试结果与遗留风险 |

## 7. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 现有 GUI 直接调用 `population_api.resolve_election`，可能不标记阶段完成 | 改为通过 `session_api.resolve_population_slice` 统一结算入口 |
| 旧 PopulationStage 文本和布局已偏离 v3.25.1 | 以 HTML 原型为蓝图重写阶段内容区 |
| QML 单选状态难以跨 ListView 稳定保存 | 使用阶段页本地选择状态，仅将确认动作交给 Store Slot |
| 多玩家完成状态未完整表达 | 本轮先达成人类当前玩家可操作闭环，AI/其他玩家由 session 结算入口补齐 |

## 8. 下一步

进入 SA 边界任务书与 DA 开发任务书，然后由 Codex 按开发 loop 本地实现、测试、回归并提交报告。
