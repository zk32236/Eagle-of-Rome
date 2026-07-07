# AS-P0-03 私有字段访问收束第一批 开发验收报告 - CGT-01

日期：2026-06-24

基线：`6ea1281 BUG-P0 Fix forum current player sync`

Decision by CGT-01: `READY_FOR_SA_REVIEW`

## Changed files

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

## Implementation summary

1. 人口阶段 pending 已迁入 `GameState` 公共接口管理；查询均返回列表副本。
2. `population_api.campaign()` / `vote()` 增加显式 `bypass_permission=False`；自动庆典和自动投票始终调用 API。
3. 自动投票通过 `replace=True` 覆盖同一玩家、同一官职旧票；手动重复投票继续拒绝。
4. 广场、人口和海军生产路径已改用 `WarSystem` 公共查询与登记方法。
5. 起义战争登记由 `WarSystem` 保证 ACTIVE 状态和按战争 ID 幂等。
6. 待解散军团队列通过 `clear_legions_to_disband()` 取出；解散失败编号会重新登记，已解决战争的失败军团也转入该队列。
7. 总督交接由 `Province.complete_governor_transition()` 原子处理；无效或死亡候任人不会替换现任总督，但临时字段仍清理。
8. 公地认购改用 `Figure.buy_land()`，人物扣款/私地增加成功后才更新国库和国家公地。

## Public interfaces

- `GameState.record_population_campaign(player_id, figure_id, amount) -> None`
- `GameState.get_population_campaigns() -> list`
- `GameState.record_population_vote(player_id, office, figure_id, replace=False) -> bool`
- `GameState.get_population_votes() -> list`
- `GameState.get_population_pending_snapshot() -> dict`
- `GameState.clear_population_pending() -> None`
- `population_api.campaign(..., bypass_permission=False) -> dict`
- `population_api.vote(..., bypass_permission=False) -> dict`
- `WarSystem.get_resolved_wars() -> List[War]`
- `WarSystem.get_naval_threat_wars() -> List[War]`
- `WarSystem.register_rebellion_war(war) -> bool`
- `Province.complete_governor_transition(turn, promote_designate=True) -> tuple[Optional[int], Optional[int]]`

## Removed direct accesses

精确静态复查确认以下跨层访问均已移除：

- `population_api.py` / `auto_player_processor.py` / `phase_population.py` -> `state._population_pending`
- `forum_api.py` / `phase_forum.py` / `auto_player_processor.py` / `phase_population.py` -> `WarSystem._war_discard`
- `phase_population.py` -> `WarSystem._legions_to_disband`
- `naval_system.py` -> `war_system._threats`
- `phase_forum.py` -> `war_system._active_wars`
- `forum_api.py` -> `figure._land_private`
- `phase_resolution.py` -> Province 三个总督私有字段

## Tests executed

指定测试逐项结果：

- `test_population_api.py`: 29 passed
- `test_phase_population.py`: 21 passed
- `test_phase_population_disband.py`: 6 passed
- `test_phase_population_truce.py`: 4 passed
- `test_phase_resolution.py`: 15 passed
- `test_phase_resolution_truce.py`: 4 passed
- `test_phase_senate_governor.py`: 4 passed
- `test_war_system.py`: 8 passed
- `test_naval_system.py`: 14 passed
- `test_forum_api.py`: 58 passed
- `test_phase_forum_cmd_layer.py`: 19 passed
- `test_phase_forum_triumph.py`: 4 passed

指定测试合并运行：`187 passed in 3.53s`

额外海军公共接口测试：`3 passed in 0.07s`

全量测试：`721 passed in 7.32s`

## Static and diff checks

- 目标私有字段精确扫描：无匹配。
- `git diff --check`：通过。
- 仅出现工作区 CRLF 换行提示，无空白错误。
- 当前 Git HEAD：`6ea1281`。
- 未执行 Git 提交。

## Known risks and remaining debt

- `testing.bypass_player_check` 为现有测试兼容仍保留；自动玩家生产路径已不再依赖它，而是显式传入 `bypass_permission=True`。
- WarSystem 查询返回容器副本，但战争对象本身仍为可变实体；本任务只要求禁止返回内部可变容器。
- `Contract` 私有字段、场景加载器、死亡资产回收、调试工具和全局测试夹具私有字段访问按任务边界未处理。
- 公共接口/函数索引文档尚待后续文档一致性任务同步。

## SA review request

请 SA-01 复核：

1. 自动/手动人口操作是否已满足统一 API 和权限边界。
2. 军团解散失败回填、起义登记、总督交接和公地认购的原子性。
3. 静态扫描目标是否全部消失。
4. 是否批准进入项目负责人手工复测与后续 Git 归档。
