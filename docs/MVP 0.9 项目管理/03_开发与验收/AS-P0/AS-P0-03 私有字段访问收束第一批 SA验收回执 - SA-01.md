# AS-P0-03 私有字段访问收束第一批 SA验收回执 - SA-01

验收日期：2026-06-24

代码基线：Git HEAD `6ea1281`

Decision: CONDITIONAL_PASS

## Reasons

- CGT-01 的实际修改严格限定在 SA 技术任务书允许范围内，未扩展为全项目私有字段清理。
- 人口阶段自动与手动操作已统一通过 `population_api`，显式 bypass 只绕过玩家回合/派系权限，人物、候选资格、金额和财富校验仍然保留。
- WarSystem 查询返回容器副本；起义战争登记、已解决战争查询、海战威胁查询和待解散军团管理已形成受控公共入口。
- 总督交接由 Province 原子方法管理；无效或死亡候任人不会替换现任总督，临时交接状态仍会清理。
- 公地认购使用 `Figure.buy_land()` 完成人物财富与私地原子变更，成功后才更新国库和国家公地。
- SA 独立执行指定测试和全量回归均通过。
- 条件项仅为新增公共接口尚未同步 MVP 0.7 函数索引；已形成明确待同步清单，不构成功能或架构阻塞。

## Files reviewed

生产代码：

- `src/core/game_state.py`
- `src/core/entities/province.py`
- `src/core/systems/war_system.py`
- `src/core/systems/naval_system.py`
- `src/api/population_api.py`
- `src/api/forum_api.py`
- `src/ui/processors/auto_player_processor.py`
- `src/ui/commands/phase_population.py`
- `src/ui/commands/phase_forum.py`
- `src/ui/commands/phase_resolution.py`

测试代码：

- `src/tests/test_api/test_population_api.py`
- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_commands/test_phase_population.py`
- `src/tests/test_commands/test_phase_population_disband.py`
- `src/tests/test_commands/test_phase_resolution.py`
- `src/tests/test_systems/test_war_system.py`
- `src/tests/test_systems/test_fleet_construction.py`
- `src/tests/test_systems/test_naval_unlock.py`

## Selected first-batch targets

1. `_population_pending` 的记录、查询、替票和清理。
2. WarSystem 已解决战争、海战威胁、起义登记和待解散军团队列。
3. Province 旧总督/候任总督原子交接。
4. 广场公地认购对 Figure 私地的受控变更。

## Public interfaces added or changed

- `GameState.record_population_campaign(...)`
- `GameState.get_population_campaigns()`
- `GameState.record_population_vote(..., replace=False)`
- `GameState.get_population_votes()`
- `GameState.get_population_pending_snapshot()`
- `GameState.clear_population_pending()`
- `population_api.campaign(..., bypass_permission=False)`
- `population_api.vote(..., bypass_permission=False)`
- `WarSystem.get_resolved_wars()`
- `WarSystem.get_naval_threat_wars()`
- `WarSystem.register_rebellion_war(war)`
- `Province.complete_governor_transition(turn, promote_designate=True)`

以上接口需在后续文档一致性任务中同步至 MVP 0.7 函数索引。

## Direct private-field accesses removed

静态复查确认以下目标生产访问已消除：

- `population_api.py`、`auto_player_processor.py`、`phase_population.py` 对 `_population_pending` 的直接访问。
- `forum_api.py`、`phase_forum.py`、`auto_player_processor.py`、`phase_population.py` 对 `_war_discard` 的直接访问。
- `phase_population.py` 对 `_legions_to_disband` 的直接访问。
- `naval_system.py` 对 `war_system._threats` 的直接访问。
- `phase_forum.py` 对 `war_system._active_wars` 的直接访问。
- `forum_api.py` 对 `figure._land_private` 的直接访问。
- `phase_resolution.py` 对 Province 总督交接私有字段的直接访问。

## Test status

SA 使用项目基线解释器独立复验：

```text
指定 12 个测试目标：187 passed in 3.05s
全量 src/tests：721 passed in 7.70s
git diff --check：通过，仅有 CRLF 工作区提示
```

未发现失败、跳过或新增回归。

## Architecture risks

- `testing.bypass_player_check` 仍作为历史测试兼容存在；本次自动玩家生产路径已改用显式 API 参数，不再依赖该配置。
- WarSystem 查询返回的是列表副本，但其中 War 实体仍可变；符合本任务“不暴露内部容器”的边界，实体不可变性不在本轮范围。
- 军团解散失败项可能在同一次人口结算中重试一次；若仍失败会重新进入待处理队列，不会静默丢失。
- 全局仍存在既有 `game_api -> UI command` 依赖和重复 `api_response`，不是本次引入，应继续作为后续架构债务登记。

## Remaining private-field debt

| 技术债 | 建议优先级 |
| --- | --- |
| Contract 预算、施工、质保内部字段的跨层写入 | P1 |
| `GameState.mark_member_dead()` 的人物私地资产回收接口 | P1 |
| 新增公共接口同步 MVP 0.7 函数索引 | P1 文档任务 |
| `game_api` 对 UI 命令层的反向依赖 | P1 |
| forum/senate 重复 `api_response` | P2 |
| 场景加载器、调试工具和测试夹具私有字段访问 | P2 |
| 影子 Province 与历史兼容接口 | P2 |

## Required condition

在进入大规模 P1 功能开发前，由 PM 安排一次文档一致性任务，将本回执列出的新增/变更公共接口同步到 MVP 0.7 函数索引。该条件不要求返工当前代码。

## Sprint closeout recommendation

AS-P0-03 已达到架构收口 Sprint 的代码与测试完成条件。建议 PM 提请项目负责人：

1. 完成一次全流程手工复测。
2. 手工复测通过后授权 SA Git 归档。
3. 批准结束架构收口 Sprint。
4. 进入 GUI 原型/下一阶段开发，同时保留 P1/P2 技术债任务池。

当前代码状态：未提交 Git，等待项目负责人手工复测及归档授权。
