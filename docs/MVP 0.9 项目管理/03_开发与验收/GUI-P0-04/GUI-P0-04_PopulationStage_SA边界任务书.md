# GUI-P0-04 PopulationStage SA边界任务书

日期：2026-07-16
角色：SA
任务类型：GUI 边界审查 + 布局约束 + Store/API 接入边界

## 1. 依据文档

| 文档 | 用途 |
| --- | --- |
| `EOR_GUI_Prototype_v3.25.1.html` | Phase 4 主视觉与交互蓝图 |
| `EOR_GUI_SA-DA_开发任务书规范模板_v1.1.md` | GUI 任务书结构与回归要求 |
| `EOR_GUI_QML_Rebuild_Supplement_v3.25.1.md` | QML 职责边界与 Store/API 路径 |
| `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` | A-F Shell 布局基线 |
| `GUI design - Phase 4A/B/C.PNG` | 原型状态辅助对照 |

## 2. 布局约束

本任务只允许填充 `StageDesktop.StageContentSlot` 中的 `PopulationStage.qml`，可按需在 Store/API 增加 DTO 字段和 Slot，但不得重建主 Shell。

| 区域 | 约束 |
| --- | --- |
| A 顶栏 | 不修改 |
| B 左侧阶段栏 | 不修改，人口阶段仍为第 4 阶段 |
| C 中央桌面 | 仅替换 PopulationStage 内部内容 |
| D 右侧状态栏 | 可复用现有阶段推进按钮，不承载候选人主表 |
| E 底部查询栏 | 不修改 |
| F 主操作 | 本轮主操作保留在 PopulationStage 内部双面板按钮，不新增 Shell action layer |

## 3. 允许修改范围

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 修改 | `src/ui/gui/qml/stages/PopulationStage.qml` | 主 UI 改造 |
| 修改 | `src/ui/gui/session_store.py` | 暴露人口阶段 DTO、结果、状态与 Slot |
| 修改 | `src/ui/gui/api_adapter.py` | 改用 session 结算入口 |
| 修改 | `src/api/session_api.py` | 补齐人口阶段 GUI DTO 和结果记录 |
| 修改/可选 | `src/api/population_api.py` | 仅可补结构化返回，不改核心规则 |
| 修改 | `src/tests/test_gui/` | GUI 回归 |
| 修改 | `src/tests/test_api/test_population_api.py` | API 回归 |

## 4. 禁止事项

- 不直接从 QML 访问 `population_api`、`GameState` 或 Core 对象。
- 不在 QML 计算候选资格、投票权重、选举胜者。
- 不修改 `src/core/` 规则层。
- 不改变 `GameShell.qml` 的五区布局和主锚点。
- 不删除或重命名现有全局查询入口。

## 5. 接口边界

QML 可使用：

- `sessionStore.populationView`
- `sessionStore.populationCandidates`
- `sessionStore.myVotes`
- `sessionStore.populationCampaigns`
- `sessionStore.populationCurrentStep`
- `sessionStore.populationResolved`
- `sessionStore.populationElectionResults`
- `sessionStore.doCampaign(figure_id, amount)`
- `sessionStore.doVote(office, figure_id)`
- `sessionStore.doResolveElection()`

如字段不存在，DA 需在 Store/API 层补齐。

## 6. 验收重点

| 编号 | 验收点 |
| --- | --- |
| SA-01 | 页面结构与 HTML 原型一致：候选人表在上，双面板在下 |
| SA-02 | 投票面板有锁定态、开放态、完成态 |
| SA-03 | 结果态在中央主区域可见 |
| SA-04 | 所有动作经 Store/API |
| SA-05 | 测试覆盖 DTO、Store 流程、QML 结构 |

## 7. SA 结论

本任务边界清晰，可进入 DA 实施。若 DA 发现 `population_api.resolve_election` 无法提供候选人结果映射，应优先在 `session_api.resolve_population_slice` 做 GUI 结构化包装，不应把规则搬入 QML。
