# GUI-P0-04 PopulationStage DA开发任务书

日期：2026-07-16
角色：DA
任务类型：GUI Phase Content Implementation + Store/API Binding

## 一、任务目标

实现 v3.25.1 HTML 原型中的 Phase 4 人口阶段：

1. 庆典赞助。
2. 投票选举。
3. 结果展示。

不得重建 Shell，不得绕过 Store/API。

## 二、依据文档

- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-04_PopulationStage_Phase4_PM意图包.md`
- `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-04/GUI-P0-04_PopulationStage_SA边界任务书.md`
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/00_GUI产品基线/EOR_GUI_Prototype_v3.25.1.html`
- `docs/MVP 0.9 项目管理/01_需求与版本规划/GUI需求/00_GUI产品基线/EOR_GUI_QML_Rebuild_Supplement_v3.25.1.md`

## 三、允许修改范围

| 文件 | 要求 |
| --- | --- |
| `src/ui/gui/qml/stages/PopulationStage.qml` | 重写为原型双面板结构 |
| `src/ui/gui/session_store.py` | 补人口阶段状态、结果、campaign/vote/resolve 刷新 |
| `src/ui/gui/api_adapter.py` | 选举结算改用 session API |
| `src/api/session_api.py` | 补齐人口阶段 GUI DTO 和结果记录 |
| `src/tests/test_gui/test_adapter.py` | 增加 Store 流程测试 |
| `src/tests/test_gui/test_qml_startup.py` | 增加结构挂载/对象名测试 |
| `src/tests/test_gui/test_session_api.py` | 增加 DTO 字段测试 |

## 四、实现要求

### 4.1 PopulationStage

必须包含以下对象名，便于 QML 测试：

| objectName | 说明 |
| --- | --- |
| `populationStageRoot` | 根节点 |
| `populationAnnouncement` | 公示区 |
| `populationCandidateTable` | 候选人信息表 |
| `populationCampaignPanel` | 庆典赞助面板 |
| `populationVotePanel` | 投票选举面板 |
| `populationVoteLock` | 投票锁定提示 |
| `populationResolveButton` | 完成投票/结算按钮 |

### 4.2 Store/API

- `doResolveElection()` 必须调用 `session_api.resolve_population_slice`。
- 结算成功后必须刷新 snapshot 与 population view。
- API DTO 应至少提供：
  - `current_step`
  - `resolved`
  - `my_campaigns`
  - `my_votes`
  - `election_results`
  - `faction_influence_before`
  - `faction_influence_after`

### 4.3 结果展示

结果展示优先使用 API 返回的结构化结果。若结果为空，显示可解释空态，不得只依赖事件日志。

## 五、测试要求

至少运行：

```text
py -m pytest src/tests/test_api/test_population_api.py src/tests/test_gui
git diff --check
```

如沙箱阻止日志或缓存写入，需授权重跑并记录原因。

## 六、验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | QML 可加载，PopulationStage 对象存在 |
| AC-02 | 庆典按钮调用 Store Slot 并刷新 DTO |
| AC-03 | 投票区锁定态随庆典完成变化 |
| AC-04 | 投票可逐官职记录 |
| AC-05 | 结算后 `populationResolved == true` |
| AC-06 | 中央公示区和候选人表显示选举结果 |
| AC-07 | Focused GUI/API tests pass |

## 七、交付物

- 修改文件清单。
- 实现摘要。
- 测试结果。
- 风险与遗留问题。
- DA 开发报告。
