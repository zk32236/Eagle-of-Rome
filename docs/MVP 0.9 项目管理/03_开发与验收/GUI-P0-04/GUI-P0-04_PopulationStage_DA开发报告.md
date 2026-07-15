# GUI-P0-04 PopulationStage DA开发报告

日期：2026-07-16
执行角色：Codex / DA
任务：Phase 4 人口阶段 GUI 闭环

## 1. 目标

按 `EOR_GUI_Prototype_v3.25.1.html` 实现 Phase 4 人口阶段：

- 庆典赞助
- 投票选举
- 结果展示

附件 Phase 4A / 4B / 4C 截图作为同一 HTML 原型状态对照。

## 2. 修改文件

| 文件 | 变更 |
| --- | --- |
| `src/ui/gui/qml/stages/PopulationStage.qml` | 重写为候选人表 + 庆典赞助/投票选举双面板 + 公示结果结构 |
| `src/api/session_api.py` | 补齐人口阶段 DTO 字段、选举结果记录、派系影响力快照 |
| `src/api/population_api.py` | 候选人 DTO 增加 `influence`、`wealth`，供 GUI 展示 |
| `src/ui/gui/api_adapter.py` | GUI 选举结算改走 `session_api.resolve_population_slice` |
| `src/ui/gui/session_store.py` | 暴露 `populationView`、`populationCurrentStep`、`populationResolved`、结果与影响力属性 |
| `src/tests/test_gui/test_session_api.py` | 覆盖人口阶段 DTO 与结算后结果态 |
| `src/tests/test_gui/test_adapter.py` | 覆盖 Store 结算后保持 population 结果页可见 |
| `src/tests/test_gui/test_qml_startup.py` | 覆盖 Phase 4 QML 关键对象 |
| `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-04_PopulationStage_Phase4_PM意图包.md` | 新增 PM 意图包 |
| `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-04/GUI-P0-04_PopulationStage_SA边界任务书.md` | 新增 SA 边界任务书 |
| `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-04/GUI-P0-04_PopulationStage_DA开发任务书.md` | 新增 DA 开发任务书 |

## 3. 实现摘要

### 3.1 PopulationStage

已从旧 Tab 结构改为 HTML 原型对应结构：

- 顶部公示区 `populationAnnouncement`
- 候选人信息表 `populationCandidateTable`
- 左侧庆典赞助面板 `populationCampaignPanel`
- 右侧投票选举面板 `populationVotePanel`
- 庆典完成前的投票锁定提示 `populationVoteLock`
- 完成投票/结算按钮 `populationResolveButton`

### 3.2 Store/API

人口阶段新增/补齐 GUI 可消费字段：

- `current_step`
- `resolved`
- `office_count`
- `campaign_done`
- `vote_done`
- `election_results`
- `faction_influence_before`
- `faction_influence_after`

`GuiApiAdapter.resolve_election()` 已改为调用 `session_api.resolve_population_slice()`，避免 GUI 绕过 session 结算流程。

### 3.3 结果展示

结算成功后：

- `state.record_phase_result("population", ...)` 保存结构化结果。
- `PopulationStage` 中央公示区展示选举完成状态。
- 候选人表按官职展示当选者。
- `GuiSessionStore` 在刷新后保持选中 `population`，避免用户无法看到 Phase 4C 结果态。

## 4. 验证结果

| 命令 | 结果 |
| --- | --- |
| `py -m pytest src/tests/test_api/test_population_api.py src/tests/test_gui -q` | `67 passed in 4.98s` |
| `py -m pytest src/tests/test_commands/test_phase_population.py src/tests/test_commands/test_func_population.py src/tests/test_deciders/test_population_deciders.py -q` | `39 passed in 0.31s` |
| `py -m pytest src/tests -q` | `782 passed in 12.58s` |
| `git diff --check` | PASS |

## 5. 设计对照

| 原型要求 | 实现状态 |
| --- | --- |
| 候选人信息表在上方 | 已实现 |
| 庆典赞助左面板 | 已实现 |
| 投票选举右面板 | 已实现 |
| 投票区等待庆典完成锁定态 | 已实现 |
| 完成投票后结果在公示区展示 | 已实现 |
| 候选人表展示选举结果 | 已实现 |

## 6. 风险与遗留

| 项目 | 说明 |
| --- | --- |
| 按人物赞助 vs 按官职赞助 | 当前核心 API 是按人物 `figure_id` 赞助；HTML 原型中同一人物可在多个官职行出现。本轮不扩展核心规则，保持 GUI 经现有 API 操作。 |
| 截图自动验收 | 现有截图脚本默认启动天命阶段，未作为本轮正式视觉证据；本轮以 QML 结构测试 + 原型对象对照 + 完整测试回归验收。 |
| 结果后阶段状态 | `resolve_population_slice()` 按既有测试要求标记 population 已执行；Store 额外保持选中人口阶段以展示结果。 |

## 7. 结论

Decision: PASS

Phase 4 人口阶段已按 v3.25.1 HTML 原型完成 GUI 闭环实现，相关 API/Store/QML 测试与完整回归均通过，可进入归档提交准备。
