# AS-P0-01 PoliticalSystem 重构开发任务书

任务编号：AS-P0-01  
任务名称：PoliticalSystem 重构开发任务  
任务类型：架构重构  
优先级：P0  
目标版本：MVP 0.7 架构收口 Sprint  
发布角色：系统架构师 SA  
执行角色：DeepSeek 模块程序员  
发布日期：2026-06-21

## 一、背景说明

当前 EOR 项目处于 MVP 0.7 功能完成后、MVP 0.9 / MVP 1.0 P1 功能开发前的“架构收口 Sprint”阶段。

根据项目经理 PM 发布的任务意图，以及系统架构师 SA 对 `PoliticalSystem` 的边界审查结论，当前元老院/政治逻辑仍分散在：

- `src/ui/commands/phase_senate.py`
- `src/api/senate_api.py`
- `src/core/game_state.py`
- `src/core/systems/war_system.py`
- `src/core/entities/province.py`

其中 `phase_senate.py` 和 `senate_api.py` 承担了过多政治业务规则，包括提案构建、自动提案、投票统计、提案执行、总督候任字段写入、停战草案恢复、战争接管等逻辑。这会阻碍后续腐败、审判、忠诚度、派系收买、政治影响力等 P1 功能开发。

本任务目标不是新增玩法，而是将现有政治/元老院核心业务规则收束到系统层，降低 UI/API 与核心政治规则的耦合。

## 二、任务目标

新增并实现 `src/core/systems/political_system.py`，将适合迁移的元老院/政治核心业务规则从 UI/API 层收束到 `PoliticalSystem`。

本任务完成后应达到：

1. `senate_api.py` 保留对外 API 入口，但不再承载核心投票统计和提案执行规则。
2. `phase_senate.py` 主要负责阶段步骤、玩家输入、输出展示和调用 API。
3. `PoliticalSystem` 负责提案构建、提案合法性校验、投票统计、否决处理、自动补投、提案执行调度。
4. 减少 `_senate_pending`、战争私有列表、总督候任字段等私有字段在 UI/API 层的直接访问。
5. 保持自动模式、手动模式、多玩家信息隔离和现有玩家可见流程不退化。

## 三、依据文档

### 项目管理与任务依据

- `E:\Eagle of Rome\MVP 0.9 项目管理\架构收口 Sprint 任务包.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\文档-代码一致性审计清单.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\02_项目任务书\AS-P0-01 PoliticalSystem 边界审查任务书.md`

### 架构与函数索引依据

- `E:\Eagle of Rome\MVP 0.7 架构文档`
- `E:\Eagle of Rome\MVP 0.7 函数索引说明书`

### 代码与运行基线

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`
- 代码根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- Python 解释器：`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`
- 测试框架：`pytest`

## 四、允许修改范围

| 范围 | 允许操作 |
| --- | --- |
| `src/core/systems/political_system.py` | 新增 `PoliticalSystem` 主实现 |
| `src/core/systems/__init__.py` | 如需要，导出 `PoliticalSystem` |
| `src/api/senate_api.py` | 保留 API 函数名，改为调用 `PoliticalSystem` |
| `src/ui/commands/phase_senate.py` | 只做必要瘦身，保持 UI 流程与输出兼容 |
| `src/core/game_state.py` | 新增 senate pending 只读快照/封装方法 |
| `src/core/systems/war_system.py` | 新增政治阶段需要的战争状态公共方法 |
| `src/core/entities/province.py` | 新增候任总督公共方法 |
| `src/tests/test_systems/` | 新增 `test_political_system.py` |
| `src/tests/test_api/test_senate_api.py` | 调整/补充 API 回归测试 |
| `src/tests/test_commands/test_phase_senate.py` | 必要时调整命令层回归测试 |
| `src/tests/test_commands/test_phase_senate_governor.py` | 保持并补充总督任命回归测试 |
| `src/tests/test_commands/test_rebellion_command.py` | 保持起义/总督指挥相关回归测试 |

## 五、禁止事项

DeepSeek 本次实现必须遵守：

1. 不得改变元老院阶段玩家可见流程。
2. 不得让 UI 绕过 `senate_api` 直接调用 `PoliticalSystem` 执行玩家操作。
3. 不得新增 UI 层直接修改私有字段。
4. 不得删除现有提案类型：
   - 宣战 `war`
   - 停战 `peace`
   - 总督任命 `governor`
   - 预算 `budget`
   - 土地法 `land`
5. 不得删除战争接管、停战草案、预算加成、总督候任逻辑。
6. 不得引入腐败、审判、忠诚度、派系收买、人物养成等 P1 新玩法。
7. 不得做无关格式化、大范围重命名或跨模块重构。
8. 不得修改 `E:\Eagle of Rome` 下的历史文档作为代码交付。
9. 不得为了测试通过而删除或弱化现有功能。
10. 不得改变 API 返回格式，仍应使用 `{success, message, data, errors}`。

## 六、实现要求

### 6.1 新增 PoliticalSystem

新增文件：

```text
src/core/systems/political_system.py
```

建议类结构：

```python
class PoliticalSystem:
    def __init__(self, state):
        self.state = state
```

`PoliticalSystem` 应承担以下职责：

1. 构建并校验元老院提案。
2. 统一处理提案类型：`war`、`peace`、`governor`、`budget`、`land`。
3. 统计投票结果。
4. 处理保民官否决。
5. 对未投票玩家使用 `SenateVoteDecider` 自动补投。
6. 执行通过的提案。
7. 返回结构化执行结果，供 API 包装后返回给 UI。

### 6.2 建议 public methods

`PoliticalSystem` 建议至少提供：

```python
build_initial_info() -> dict
create_proposal(player_id: str, proposal_type: str, **kwargs) -> dict
record_vote(player_id: str, proposal_ids: list[int], votes: list[bool]) -> dict
record_veto(player_id: str, proposal_ids: list[int]) -> dict
resolve_senate(vote_decider=None) -> dict
build_issue_from_proposal(proposal: dict)
calculate_vote_result(proposal: dict, vote_decider=None) -> dict
execute_passed_proposal(proposal: dict) -> dict
```

返回值可以是内部结构化结果，但最终经 `senate_api` 返回时必须符合：

```python
{
    "success": bool,
    "message": str,
    "data": dict | None,
    "errors": list[str],
}
```

### 6.3 从 senate_api.py 迁移的逻辑

从 `src/api/senate_api.py` 迁移：

1. `propose()` 内的提案构建与业务校验。
2. `resolve_senate()` 内的投票统计、自动补投、通过/否决判定。
3. 通过提案后的执行逻辑：
   - 宣战
   - 停战
   - 总督任命
   - 预算
   - 土地法
4. `process_war_takeover()` 可迁入 `PoliticalSystem`，或由 `PoliticalSystem` 统一调用。
5. `get_eligible_governor_candidates()`、`is_governor_position_occupied()` 应迁入 `PoliticalSystem` 或作为系统层辅助函数。

迁移后 `senate_api.py` 应保留以下对外函数名：

```python
get_senate_initial_info
propose
vote
veto
resolve_senate
```

这些 API 函数应主要负责：

- 参数接收
- 玩家权限入口检查
- 调用 `PoliticalSystem`
- 包装标准 API 返回

### 6.4 从 phase_senate.py 迁移的逻辑

从 `src/ui/commands/phase_senate.py` 迁移或封装：

1. 自动生成提案逻辑。
2. 手动/自动投票统计辅助逻辑。
3. 自动补投逻辑。
4. 停战草案被否决后的恢复逻辑。
5. 总督任命执行逻辑。

迁移后 `phase_senate.py` 应保留：

- 阶段步骤控制。
- 玩家输入解析。
- 菜单与提示文本输出。
- 调用 `senate_api`。
- 将 API 返回结果转换为 CLI 输出。

### 6.5 新增/补充公共方法

为减少私有字段直改，建议补充：

#### GameState

```python
get_senate_votes_copy()
get_senate_vetoes_copy()
has_senate_vote(player_id: str, proposal_id: int) -> bool
```

如果 `PoliticalSystem` 需要内部修改 `_senate_pending`，应优先通过现有：

```python
add_senate_proposal()
record_senate_vote()
record_senate_veto()
clear_senate_pending()
get_senate_proposals()
```

#### Province

```python
set_governor_designate(new_governor_id: int, old_governor_id: int | None) -> None
clear_governor_designate() -> None
```

不得继续在 UI/API 层直接写：

```python
province._governor_designate_id
province._old_governor_id
```

#### WarSystem

```python
restore_rejected_peace_treaty(war_id: str, preserve_commander: bool = True) -> bool
activate_threat_as_war(war_id: str, commander_id: int, legions: int) -> bool
```

如已有等价方法，请复用并在报告中说明；不得在 UI/API 层直接操作：

```python
ws._truce_wars
ws._active_wars
ws._threats
```

### 6.6 自动模式与手动模式

必须保持：

1. 自动模式提案类型、数量、结果不退化。
2. 手动模式玩家投票、否决、提案流程不退化。
3. 未投票玩家的自动补投规则与当前行为一致。
4. 多玩家信息隔离不退化。

### 6.7 文档同步

如果新增公共接口或新增 `PoliticalSystem`，请在交付报告中列出需要同步的文档/函数索引清单。

本任务不要求 DeepSeek 直接修改 Word 文档，但必须输出“待同步文档清单”。

## 七、调试日志要求

关键路径必须保留或补充 `GameState.log_event()`：

1. 提案创建成功/失败。
2. 投票记录。
3. 保民官否决记录。
4. 元老院结算开始与完成。
5. 提案通过/否决统计。
6. 宣战、停战、总督、预算、土地法提案执行。
7. 战争接管执行。

日志应尽量使用结构化 `extra` 字段，例如：

```python
extra={
    "proposal_id": proposal_id,
    "proposal_type": proposal_type,
    "player_id": player_id,
}
```

## 八、测试要求

DeepSeek 必须运行并报告以下测试：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_senate_api.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_senate.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_senate_governor.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_rebellion_command.py" -q
```

当前 SA 审查基线结果为：

| 测试目标 | 当前结果 |
| --- | --- |
| `test_senate_api.py` | 13 passed |
| `test_phase_senate.py` | 35 passed |
| `test_phase_senate_governor.py` | 4 passed |
| `test_rebellion_command.py` | 5 passed |

DeepSeek 实现后不得低于该基线。

### 新增测试要求

新增：

```text
src/tests/test_systems/test_political_system.py
```

至少覆盖：

1. 创建 `war` 提案。
2. 创建 `peace` 提案。
3. 创建 `governor` 提案。
4. 创建 `budget` 提案。
5. 创建 `land` 提案。
6. 投票统计通过。
7. 投票统计否决。
8. 保民官否决。
9. 总督候任字段通过公共方法设置。
10. 停战草案被拒绝后通过 `WarSystem` 公共方法恢复。

## 九、验收标准

| 类别 | 验收标准 |
| --- | --- |
| 功能 | 现有元老院阶段流程、提案、投票、否决、结算行为不退化 |
| 架构 | 新增 `PoliticalSystem`，核心政治规则从 UI/API 收束到系统层 |
| API | `senate_api` 对外函数名保持兼容，返回格式保持 `{success, message, data, errors}` |
| UI | `phase_senate.py` 不新增业务规则，不新增私有字段直改 |
| 私有字段 | `_senate_pending`、战争私有列表、总督候任字段访问明显减少 |
| 自动模式 | 自动提案、自动补投、自动结算行为不退化 |
| 手动模式 | 玩家输入、投票、否决、公示、结算流程不退化 |
| 多玩家 | 不泄露其他玩家不应可见的信息 |
| 测试 | 指定 pytest 目标通过，新增 `test_political_system.py` 通过 |
| 文档 | 交付报告列出需同步的文档/函数索引 |

SA 验收结论至少达到 `CONDITIONAL_PASS`，本任务才可关闭。

## 十、交付物

DeepSeek 必须输出以下内容：

1. 修改文件清单。
2. 新增 `PoliticalSystem` 的职责说明。
3. 从 `senate_api.py` 迁移了哪些逻辑。
4. 从 `phase_senate.py` 迁移了哪些逻辑。
5. 未迁移逻辑清单及原因。
6. 新增/修改公共方法清单。
7. 测试命令与完整测试结果。
8. 架构风险与遗留问题。
9. 待同步文档/函数索引清单。

交付报告必须使用以下格式：

```text
一、修改文件清单

二、实现摘要

三、迁移前后职责说明

四、新增/修改公共接口

五、测试命令与结果

六、未解决问题与风险

七、待同步文档/函数索引
```

## 十一、SA 验收流程

DeepSeek 输出后，由系统架构师 SA 先执行：

1. 检查修改文件是否在允许范围内。
2. 检查是否违反禁止事项。
3. 检查 UI/API/Core 分层是否改善。
4. 检查是否新增私有字段直改。
5. 运行指定 pytest。
6. 根据结果输出：

```text
Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER
Reasons:
Files reviewed:
Test status:
Architecture risks:
Required DeepSeek changes:
```

未经 SA 验收，不进入 PM 级任务关闭。
