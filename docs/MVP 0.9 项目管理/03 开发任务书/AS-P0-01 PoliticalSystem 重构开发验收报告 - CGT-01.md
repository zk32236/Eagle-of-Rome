# AS-P0-01 PoliticalSystem 重构开发验收报告 - CGT-01

日期：2026-06-21

执行角色：CGT-01

代码根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## 一、修改文件清单

代码项目修改：

- `src/core/systems/political_system.py`：新增 `PoliticalSystem`，收束元老院核心业务规则。
- `src/api/senate_api.py`：重写为薄 API 层，保留原公共函数名与 `{success, message, data, errors}` 返回结构。
- `src/ui/commands/phase_senate.py`：最小必要瘦身，宣布环节统一调用 API 结算，移除 UI 层提案执行和停战恢复直改。
- `src/core/game_state.py`：新增元老院投票/否决只读副本与清票公共方法。
- `src/core/systems/war_system.py`：新增停战草案失败恢复与威胁战争激活公共方法。
- `src/core/entities/province.py`：新增候任总督设置/清除公共方法。
- `src/core/systems/__init__.py`：保持包初始化为空，避免循环导入。
- `src/tests/test_systems/test_political_system.py`：新增系统层专项测试。
- `src/tests/test_api/test_senate_api.py`：调整 `resolve_senate` 测试断言到系统层执行边界。

文档交付：

- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-01 PoliticalSystem 重构开发验收报告 - CGT-01.md`

## 二、实现摘要

本轮新增 `PoliticalSystem`，负责：

- 元老院初始信息构建。
- `war`、`peace`、`governor`、`budget`、`land` 五类提案构建与校验。
- 投票统计、未投票派系自动补投、保民官否决处理。
- 通过提案执行：宣战、停战批准、总督候任、预算、土地法。
- 停战草案未通过后的战争恢复。
- 战争接管调度。
- 总督候选人资格与任职占用检查。

`senate_api.py` 保留原入口函数：

- `get_senate_initial_info`
- `propose`
- `vote`
- `veto`
- `resolve_senate`
- 兼容辅助函数：`execute_war_declaration`、`execute_passed_peace_treaty`、`process_war_takeover`、`get_eligible_governor_candidates`、`is_governor_position_occupied`、`assign_fleets_to_active_wars`

## 三、迁移前后职责说明

迁移前：

- `senate_api.py` 直接承担提案构建、投票统计、提案执行、战争接管、总督资格检查。
- `phase_senate.py` 在宣布环节重复执行通过法案，并直接恢复停战战争、写候任总督字段。
- UI/API 层存在对 `_senate_pending`、`WarSystem` 私有战争列表、`Province` 候任字段的直接访问。

迁移后：

- `PoliticalSystem` 承担核心政治/元老院规则。
- `senate_api.py` 主要负责参数入口、调用 `PoliticalSystem`、包装标准 API 返回。
- `phase_senate.py` 保留阶段控制、输入输出、展示、调用 API；宣布环节使用 `resolve_senate` 返回的 `passed_proposals_snapshot` 展示，不再依赖清空后的 pending 数据。
- 停战恢复只处理本轮明确被否决或未通过且有有效投票影响力的 peace proposal；无元老在场时不把草案当作明确否决。

## 四、新增/修改公共接口

新增：

- `PoliticalSystem.build_initial_info()`
- `PoliticalSystem.create_proposal(...)`
- `PoliticalSystem.record_vote(...)`
- `PoliticalSystem.record_veto(...)`
- `PoliticalSystem.resolve_senate(...)`
- `PoliticalSystem.build_issue_from_proposal(...)`
- `PoliticalSystem.calculate_vote_result(...)`
- `PoliticalSystem.execute_passed_proposal(...)`
- `PoliticalSystem.restore_rejected_peace_wars(...)`
- `PoliticalSystem.process_war_takeover(...)`
- `PoliticalSystem.get_eligible_governor_candidates(...)`
- `PoliticalSystem.is_governor_position_occupied(...)`
- `GameState.get_senate_votes_copy()`
- `GameState.get_senate_vetoes_copy()`
- `GameState.has_senate_vote(...)`
- `GameState.clear_senate_votes()`
- `WarSystem.restore_rejected_peace_treaty(...)`
- `WarSystem.activate_threat_as_war(...)`
- `Province.set_governor_designate(...)`
- `Province.clear_governor_designate()`

保留兼容：

- `senate_api` 的玩家可见 API 函数名与返回结构未改变。
- `phase_senate.py` 中若干旧辅助方法保留，以兼容现有测试和局部流程，但关键执行路径已转到 API/Core。

## 五、测试命令与结果

已运行：

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_senate_api.py -q
```

结果：`13 passed in 0.11s`

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_senate.py -q
```

结果：`35 passed in 0.24s`

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_senate_governor.py -q
```

结果：`4 passed in 0.11s`

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_rebellion_command.py -q
```

结果：`5 passed in 0.12s`

新增专项：

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems\test_political_system.py -q
```

结果：`6 passed in 0.05s`

## 六、未解决问题与风险

- 测试夹具仍有少量直接填充 `WarSystem._threats/_truce_wars`、`Province` 私有字段的历史构造方式。本轮未扩大测试基础设施，以避免无关重构；产品路径已通过公共方法减少私有直改。
- `phase_senate.py` 仍保留部分投票展示/辅助计算方法，主要用于公示和否决环节展示。核心执行和最终结算已迁移到 `PoliticalSystem`。
- `assign_fleets_to_active_wars` 仍保留在 API 层作为补漏函数，未纳入本轮 `PoliticalSystem`，原因是它更偏海军/战争补漏且现有调用面稳定。
- 本轮未自动提交 git。

建议提交 git：是。当前指定回归与新增系统测试均通过，架构边界比基线明显改善。

## 七、待同步文档/函数索引

建议后续同步：

- MVP 0.7 架构文档：新增 `PoliticalSystem` 职责说明。
- MVP 0.7 函数索引说明书：新增 `PoliticalSystem` 方法索引。
- API 层说明：标注 `senate_api.py` 已变为薄包装层。
- Core 公共接口索引：补充 `GameState`、`WarSystem`、`Province` 新增公共方法。
- 元老院阶段流程文档：说明宣布环节使用 `passed_proposals_snapshot`，避免清空 pending 后展示退化。
