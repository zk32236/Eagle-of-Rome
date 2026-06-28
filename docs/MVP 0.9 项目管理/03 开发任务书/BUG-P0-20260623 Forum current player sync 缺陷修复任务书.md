# BUG-P0-20260623 Forum current player sync 缺陷修复任务书

日期：2026-06-23

发布人：SA-01 / 系统架构师

执行人：CGT-01

任务类型：缺陷修复

优先级：P0

目标版本：MVP 0.9 架构收口 Sprint

代码根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

当前代码基线：`24c1933 AS-P0-04 Forum land trade API closeout`

## 一、背景说明

项目负责人在 AS-P0-04 后进行全流程手工测试时发现可疑缺陷：

1. CLI 顶层提示符有时显示 `[player_equites Equites]`。
2. 广场阶段内部操作提示仍显示 `PLAYER player_optimates Optimates`。
3. 第二回合广场阶段，Optimates 玩家执行 `retire 5` 时提示：

```text
当前不是您的回合，请等待其他玩家。
```

相关日志：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\logs\cli_20260623_194239.log`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\logs\game_20260623_194239.log`

SA 初步定位：

- 人类玩家应为 `player_optimates / Optimates`。
- `player_equites / Equites` 是 AI 派系。
- CLI 顶层提示符来自 `GameState.get_current_player()`。
- 广场阶段内部提示来自 `ForumCommand._players/_current_player_index`。
- `ForumCommand._handle_next()` 从 step 0 进入 step 1 时设置了 `_players` 和 `_current_player_index`，但没有同步 `state.set_current_player(self._players[0])`。
- 第一回合未暴露，是因为开局 `current_player` 正好是 `player_optimates`。
- 第二回合继承上一阶段留下的 `player_equites`，导致 `forum_api.retire_figure()` 的 `_check_player_permission()` 判断 `player_optimates` 不是当前玩家。

关键代码位置：

- `src/ui/commands/phase_forum.py`
  - `_handle_next()` step 0 -> step 1 路径。
  - `_execute_normal()` 初始化阶段。
  - `_get_current_player_id()` 和 `_players/_current_player_index`。
- `src/ui/debug_cli.py`
  - `_get_prompt_prefix()` 使用 `state.get_current_player()`。
- `src/api/forum_api.py`
  - `_check_player_permission()` 使用 `state.is_current_player(player_id)`。

## 二、任务目标

修复广场阶段玩家状态不同步缺陷，确保：

1. 从广场公告环节进入裁员环节时，`GameState.current_player` 与 `ForumCommand` 当前步骤玩家同步。
2. 第二回合即使此前全局 current player 残留为 AI 玩家，进入广场裁员环节后也应恢复为首个可操作玩家。
3. CLI 顶层提示符不应长期显示 AI 玩家，若当前为 AI 且存在 human player，应在交互式提示/阶段执行前恢复到 human player。
4. 修复必须有复现测试和回归测试，确认问题修复且未引入新缺陷。

## 三、依据文档

- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-04 广场阶段土地交易 API化收尾 开发任务书.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-04 广场阶段土地交易 API化收尾 SA验收回执 - SA-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 四、允许修改范围

主要允许修改：

- `src/ui/commands/phase_forum.py`
- `src/ui/debug_cli.py`
- `src/tests/test_commands/test_phase_forum_cmd_layer.py`

按需允许小范围修改：

- `src/tests/test_api/test_game_api.py`
- `src/tests/test_commands/test_func_forum.py`
- 其他与 CLI prompt / ForumCommand current player 同步直接相关的测试文件

除非测试证明必须，不应修改：

- `src/api/forum_api.py`
- `src/core/game_state.py`
- `src/api/game_api.py`

## 五、禁止事项

- 不得放松或绕过 `forum_api._check_player_permission()`。
- 不得把 `testing.bypass_player_check` 作为正式修复手段。
- 不得让 UI 层直接修改核心业务数据或 pending。
- 不得改变广场阶段裁员、招募、竞标、土地交易、凯旋投票规则。
- 不得改变 AS-P0-04 已验收的土地交易 API 化成果。
- 不得引入 GUI 或 P1 新玩法。
- 不得做无关格式化、大范围重构或跨阶段重写。
- 不得自动提交 Git。

## 六、实现要求

### 1. 修复 ForumCommand step 0 -> step 1 同步缺口

在 `ForumCommand._handle_next()` 中，step 0 进入 step 1 后，设置 `_players` 和 `_current_player_index` 的同时，应同步：

```python
if self._players:
    self.state.set_current_player(self._players[0])
```

要求：

- 与 step 1/2/3 进入新步骤时已有同步逻辑保持一致。
- 不改变 `_get_step_players()` 返回规则。
- 不改变 AI / human 玩家列表顺序。

### 2. 增加 CLI 顶层 current player 保护

在 `src/ui/debug_cli.py` 中增加轻量保护：

- 当 CLI 需要显示提示符或执行交互阶段时，如果当前玩家是 AI，且存在 human player，则恢复到首个 human player。
- 该保护应尽量集中为一个小方法，例如 `_ensure_interactive_player()`。
- 不得改变 `GameState` 的玩家系统语义。
- 不得影响自动测试模式下的 AI 阶段内部处理。

建议行为：

```text
若 current_player 是 AI 且存在 human player：
    state.set_current_player(first_human_player.player_id)
```

可选 DEBUG 日志：

```python
state.log_event(
    "CLI current player restored to human player",
    level=logging.DEBUG,
    extra={"from_player": old_id, "to_player": new_id}
)
```

### 3. 保持 API 权限校验严格

不得修改 `forum_api._check_player_permission()` 来规避问题。权限校验失败是正确防线；本任务应修复 UI/CLI current player 同步源头。

## 七、调试日志要求

如新增 CLI current player 自动恢复逻辑，请使用 `GameState.log_event()` 记录 DEBUG 日志，extra 至少包含：

- `from_player`
- `to_player`
- `reason`

不要向玩家界面打印额外噪音提示。

## 八、测试要求

必须新增或补强测试，覆盖以下场景：

### 1. 复现并验证 Forum step 0 -> step 1 同步

构造：

- `current_player = player_equites` 或等价 AI 玩家。
- `ForumCommand` 当前处于 step 0。
- 调用 `_handle_next([])` 进入 step 1。

断言：

- `cmd._get_current_player_id()` 为首个步骤玩家。
- `state.get_current_player().player_id` 同步为同一玩家。
- 手动 `retire` 不会因为 current player 残留 AI 而报 `error_not_your_turn`。

### 2. CLI prompt 保护测试

构造：

- `state.current_player` 为 AI 玩家。
- 存在至少一个 human player。
- 调用 `DebugCLI._get_prompt_prefix()` 或新增保护方法。

断言：

- 返回提示符应为 human player。
- `state.get_current_player()` 被恢复为 human player。

### 3. 回归测试

至少执行：

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_cmd_layer.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_forum_api.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_func_forum.py -q
```

如修改 `debug_cli.py`，还需执行相关 CLI / game API 测试：

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_game_api.py -q
```

同时执行：

```powershell
git diff --check
```

## 九、验收标准

| 类别 | 验收标准 |
| --- | --- |
| 功能 | 第二回合广场裁员环节不再因 current player 残留 AI 而拒绝 Optimates 玩家操作 |
| 显示 | CLI 顶层提示符不再长期显示 AI 玩家作为人类交互身份 |
| 权限 | API 当前玩家权限校验保持严格，不通过 bypass 掩盖问题 |
| 架构 | 修复限定在 UI/CLI 玩家同步，不改变核心业务规则 |
| 测试 | 新增复现测试和 CLI prompt 保护测试；指定回归测试通过 |
| 交付 | 开发报告说明根因、修改点、测试结果和风险 |

## 十、交付物

完成后请输出并归档开发验收报告：

`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\BUG-P0-20260623 Forum current player sync 开发验收报告 - CGT-01.md`

报告必须包含：

- 修改文件清单。
- 根因确认。
- 实现摘要。
- 新增测试说明。
- pytest 执行结果。
- `git diff --check` 结果。
- 未解决风险或建议登记项。

完成后请回执 SA-01 进行最终验收。
