# BUG-P0-20260623 Forum current player sync 开发验收报告 - CGT-01

日期：2026-06-23

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件清单

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_forum.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\debug_cli.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_cmd_layer.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_ui\test_command_framework.py`

## 根因确认

缺陷根因与 SA 定位一致：

- `ForumCommand._handle_next()` 从 step 0 进入 step 1 时，会重建 `_players` 并将 `_current_player_index` 置为 `0`。
- 该路径此前没有同步 `GameState.current_player`。
- 当第二回合继承上一阶段残留的 AI current player 时，广场阶段内部提示显示的步骤玩家与 `forum_api._check_player_permission()` 使用的全局 current player 不一致。
- 因此 Optimates 玩家执行 `retire` 会被 API 正确拒绝为“当前不是您的回合”。

## 实现摘要

- 在 `ForumCommand._handle_next()` 的 step 0 -> step 1 路径中补充：

```python
if self._players:
    self.state.set_current_player(self._players[0])
```

- 在 `DebugCLI` 中新增 `_ensure_interactive_player()`：
  - 当顶层 CLI current player 是 AI，且存在 human player 时，恢复到首个人类玩家。
  - 在 `_get_prompt_prefix()` 和 `_execute_phase_with_ui()` 前调用该保护。
  - 使用 `state.log_event()` 写 DEBUG 日志，包含 `from_player`、`to_player`、`reason`。
- 未修改 `forum_api._check_player_permission()`。
- 未使用 `testing.bypass_player_check` 掩盖问题。
- 未修改 AS-P0-04 土地交易 API 化相关文件和规则。

## 新增测试说明

- `test_step0_to_step1_syncs_state_current_player_before_retire`
  - 构造 `current_player = p2`（AI 残留）。
  - 调用 `ForumCommand._handle_next([])` 从 step 0 进入 step 1。
  - 断言命令内部当前玩家与 `GameState.current_player` 均为 `p1`。
  - 随后执行 `_handle_retire(["2"])`，确认不会因 `error_not_your_turn` 被拒绝。

- `test_cli_prompt_restores_ai_current_player_to_human`
  - 构造 CLI state 中 current player 为 AI，且存在 human player。
  - 调用 `_get_prompt_prefix()`。
  - 断言提示符和 `GameState.current_player` 都恢复为 human player。

## pytest 执行结果

使用解释器：

`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

执行结果：

```text
src/tests/test_commands/test_phase_forum_cmd_layer.py: 19 passed
src/tests/test_ui/test_command_framework.py: 14 passed
src/tests/test_api/test_forum_api.py: 57 passed
src/tests/test_commands/test_func_forum.py: 5 passed
src/tests/test_api/test_game_api.py: 11 passed
src/tests/test_commands/test_phase_forum_fleet.py: 3 passed
src/tests/test_commands/test_phase_forum_triumph.py: 4 passed
```

## git diff --check

结果：通过。

说明：仅有工作区 CRLF 换行提示，无空白错误。

## 未解决风险 / 建议登记项

- `DebugCLI._ensure_interactive_player()` 只在 CLI 顶层交互提示和阶段执行入口做保护，不改变阶段内部 AI 自动处理流程。
- 若未来支持多 human 玩家轮流交互，CLI 顶层“首个人类玩家”策略可能需要升级为更明确的人类玩家选择策略；当前修复满足本 P0 缺陷范围。
- `test_command_framework.py` 中 DebugCLI 构造改为使用测试隔离 state，避免同一秒多次创建真实日志文件造成文件句柄冲突；不影响生产逻辑。

## SA review request

CGT-01 请求 SA-01 对 BUG-P0-20260623 Forum current player sync 修复进行最终验收。CGT-01 未自动提交 Git。
