# AS-P0-01 PoliticalSystem 重构 SA 验收回执 - SA-04

审查日期：2026-06-21

审查角色：SA / 系统架构师

执行来源：CGT-01

CGT-01 验收报告：

`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-01 PoliticalSystem 重构开发验收报告 - CGT-01.md`

代码根目录：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## Decision

CONDITIONAL_PASS

验收通过。

## Reasons

1. 核心系统层已建立

   新增 `src/core/systems/political_system.py`，并承接元老院初始信息、提案创建、投票记录、否决、结算、通过提案执行、停战恢复、战争接管、总督候选校验等核心路径。

2. API 层已明显瘦身

   `src/api/senate_api.py` 保留原公共函数名与 `{success, message, data, errors}` 返回结构，主要职责变为调用 `PoliticalSystem` 并包装返回值。

3. 宣布/结算环节风险已收口

   `src/ui/commands/phase_senate.py` 的 `_handle_step_5()` 已改为统一调用 `senate_api.resolve_senate()`，使用 `passed_proposals_snapshot` 展示，不再在 UI 层自行执行通过法案，也不再依赖 `clear_senate_pending()` 后的 pending 数据。

4. 私有字段直改明显减少

   本轮新增：

   - `GameState.get_senate_votes_copy()`
   - `GameState.get_senate_vetoes_copy()`
   - `GameState.has_senate_vote()`
   - `GameState.clear_senate_votes()`
   - `WarSystem.restore_rejected_peace_treaty()`
   - `WarSystem.activate_threat_as_war()`
   - `Province.set_governor_designate()`
   - `Province.clear_governor_designate()`

   `phase_senate.py` 中关键路径已改用这些公共方法。

5. 指定回归测试与新增系统测试全部通过

   SA 已在本机复跑 CGT-01 声明的测试，结果一致。

## Files Reviewed

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\political_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\api\senate_api.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_senate.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\game_state.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\war_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\province.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_senate_api.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems\test_political_system.py`

## Test Status

SA 复跑结果：

```text
test_senate_api.py: 13 passed
test_phase_senate.py: 35 passed
test_phase_senate_governor.py: 4 passed
test_rebellion_command.py: 5 passed
test_political_system.py: 6 passed
```

使用解释器：

`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

## Architecture Risks

1. 自动提案生成逻辑仍保留在 `phase_senate.py`

   `_auto_generate_proposals()` 仍包含宣战、停战、总督、预算、土地法自动提案选择逻辑。它通过 `senate_api.propose()` 写入，不再直接写战争私有列表，但规则选择仍偏业务层。

   该问题不阻断 AS-P0-01 关闭，因为宣布/结算与提案执行核心风险已经迁移，且现有回归测试通过。建议作为后续架构债处理。

2. 历史测试夹具和其他旧模块仍有私有字段访问

   本轮任务范围内的 `phase_senate.py` 关键路径已有改善，但项目其他历史文件和测试夹具仍存在 `_active_wars`、`_truce_wars`、`_threats`、`_old_governor_id` 等访问。这属于既有架构债，不应阻断本任务。

3. 文档/函数索引尚未同步

   CGT-01 已列出待同步文档清单。建议在架构收口 Sprint 后续文档任务中统一更新。

## Required Follow-Up Changes

本任务不要求返工。

建议后续单独排任务：

1. 将 `phase_senate.py::_auto_generate_proposals()` 的规则选择进一步迁入 `PoliticalSystem` 或独立 `SenateProposalService`。
2. 同步 MVP 0.7 架构文档与函数索引，登记 `PoliticalSystem` 和新增公共接口。
3. 逐步清理测试夹具中直接操作战争私有列表的构造方式。

## Final Acceptance

AS-P0-01 PoliticalSystem 重构达到 SA 验收标准。

验收通过。
