# MVP0.4-04-sys — Command命令体系架构

> **功能简述：** 基于 Command 设计模式的插件式命令架构。包括 Command 抽象基类、命令自动注册（文件扫描 + 动态导入）、命令别名、命令参数解析、命令冲突检测（Fail Fast）、调试命令注入、命令多玩家隔离与回合切换、以及命令调用链（UI Command → API Layer → Core Business Logic/Deciders）。

---

## 1. 功能目的

1.1. 提供统一的命令抽象接口，使新功能可以以"插件"形式加入，无需修改主循环。

1.2. 实现命令的自动发现与动态注册：扫描指定目录下所有 `.py` 文件，提取继承 `Command` 的子类，自动注册为可用命令。

1.3. 提供命令别名校验和冲突检测机制，在注册阶段即抛出异常（Fail Fast），防止运行时歧义。

1.4. 支撑游戏阶段（Phase）的完整生命周期：每个阶段（Mortality/Revenue/Forum/Population/Senate/Combat/Resolution）均为一个 `Command` 子类，状态机驱动。

1.5. 实现多玩家信息隔离：不同玩家在同一阶段轮流操作时，清屏显示当前玩家信息、等待 PIN 码输入、切换玩家上下文。

1.6. 提供调试命令注入机制，便于测试和开发阶段直接操作底层数据（如直接创建/指派舰队、强制战斗结果）。

---

## 2. 玩家/系统行为

### 2.1 玩家行为（手动模式）

- 玩家在 CLI 提示符下输入命令名及参数，如 `trade land 1 2 5`。
- 输入 `help` 显示所有已注册命令及其别名和描述。
- 输入 `exit` 或 `quit` 退出游戏。
- 在元老院阶段输入 `vote B01 B02` 投票支持。
- 在广场阶段输入 `recruit 5 100` 招募广场中的人物。
- 在回合控制阶段输入 `next` 或 `next force` 推进回合。
- 每个玩家的操作结果通过 `print()` 显示在终端。

### 2.2 系统行为（自动/混合模式）

- 自动模式（通过配置 `testing.auto_forum` / `testing.auto_population` / `testing.auto_senate` 控制）：系统自动调用决策器（Decider）完成玩家操作，但保留 UI 展示。
- 混合模式：人类玩家手动输入，AI 玩家通过决策器自动决策，由 `AutoPlayerProcessor` 统一调度。
- 全人工测试模式（`testing.bypass_player_check=True`）：所有玩家（含 AI）均进入手动交互模式。

### 2.3 注册行为

- 系统启动时，`CommandRegistry` 扫描 `commands/` 目录，忽略 `__pycache__` 和 `_` 开头的文件。
- 每个 `.py` 文件被动态导入，检查其中所有继承 `Command` 且不是 `Command` 本身的类。
- 注册过程中检测命令名冲突和别名冲突，一旦冲突立即抛出 `ValueError`（Fail Fast）。

---

## 3. 核心规则

### 3.1 Command 契约

| 属性/方法 | 类型 | 必需 | 说明 |
|-----------|------|------|------|
| `name` | ClassVar[str] | 是 | 主命令名，唯一标识 |
| `aliases` | ClassVar[List[str]] | 是 | 别名列表（可空） |
| `description` | ClassVar[str] | 是 | 帮助文本 |
| `__init__(self, state)` | 方法 | 是 | 接收 GameState 实例 |
| `execute(self, args) → bool` | 抽象方法 | 是 | 执行命令逻辑 |

### 3.2 注册规则

- 自动扫描目录 `src/ui/commands/` 下所有 `*.py` 文件（排除 `_` 开头文件）。
- 动态导入模块（使用 `importlib.util.spec_from_file_location`），异常隔离（单个文件导入失败不影响其他文件）。
- 类级别去重：通过 `id(cmd_class)` 记录已注册类，防止重复注册。
- 主命令名和别名共享同一个名称空间 `_commands: Dict[str, Type[Command]]`。
- 冲突检测：主命令名和所有别名逐一检查，发现冲突立即抛出 `ValueError`。

### 3.3 多玩家隔离规则

- 仅当 `_is_multiplayer_manual()` 返回 True（存在多个人类玩家且非自动模式）时生效。
- 玩家切换时：清屏 → 显示当前玩家派系信息（金库、人物、影响力）→ 等待 PIN 码输入。
- PIN 码输入预留验证逻辑，当前版本仅为交互占位。
- `_switch_to_next_player()` 支持两种模式：
  - **子类维护模式**：使用子类的 `_players` 列表和 `_current_player_index` 索引。
  - **状态回退模式**：调用 `state.next_player()` 获取下一个玩家。

### 3.4 阶段命令状态机规则

- 每个阶段命令（Phase Command）使用内部 `_step` 整数状态机控制流程。
- 各阶段因功能复杂度不同，状态机步骤数各不相同：
  - **Forum（广场阶段，6步）：** 0=公告 → 1=裁员 → 2=市场 → 3=公示 → 4=交易 → 5=完成
  - **Population（人口阶段，4步）：** 0=公告 → 1=庆典+投票（合并环节）→ 2=公示 → 3=完成（原5步已合并简化）
  - **Senate（元老院阶段，6步）：** 0=入门/公告 → 1=提案 → 2=投票 → 3=公示 → 4=否决 → 5=宣布
  - 其余阶段（Mortality, Revenue, Combat, Resolution）为一次性执行，无多步状态机。
- 每个步骤可指定参与玩家列表，玩家逐个操作后进入下一步。
- 所有步骤完成后调用 `state.mark_phase_executed()` 标记阶段完成。

### 3.5 回合推进规则

- `next` 命令：优先检查决议阶段（resolution）是否已完成（因决议阶段负责胜利条件检查和下一年准备），若未完成则拒绝推进；再检查其他 6 个缺失阶段并提示。
- `next force` 命令：强制推进，跳过缺失阶段。
- `turn` 命令：自动依次执行所有未执行阶段。
- `step` 命令：逐步执行所有未执行阶段，每阶段后暂停等待 Enter 确认。

---

## 4. 输入、输出与依赖

### 4.1 输入

| 输入项 | 来源 | 格式 |
|--------|------|------|
| 命令行输入 | 玩家终端 | `command [arg1 [arg2 ...]]` |
| 游戏状态 | `GameState` 实例 | Python 对象引用 |
| 配置文件 | `src/core/config.py` | JSON 格式 |
| 本地化术语 | `TerminologyService` | 预设字符串集 |

### 4.2 输出

| 输出项 | 目标 | 格式 |
|--------|------|------|
| 执行结果 | CLI 终端 | `print()` 文本输出（含 emoji 图标） |
| 错误信息 | CLI 终端 | `print()` 红色/警告文本 |
| 帮助信息 | CLI 终端 | 格式化表格（命令名、别名、描述） |
| 事件日志 | 文件日志 + 内存日志 | RotatingFileHandler + List[str] |

### 4.3 依赖

| 依赖组件 | 方向 | 说明 |
|----------|------|------|
| `Command` → `GameState` | 强依赖 | 命令执行上下文 |
| `Command` → API 层（`src.api.*`） | 强依赖 | 业务逻辑隔离 |
| `Command` → `TerminologyService` | 弱依赖 | 本地化显示 |
| `PhaseCommand` → Decision Deciders | 强依赖 | AI 自动决策 |
| `PhaseCommand` → `AutoPlayerProcessor` | 强依赖 | 自动玩家处理 |
| `CommandRegistry` → `importlib` | 强依赖 | 动态模块加载 |
| `HelpCommand` → `CommandRegistry` | 强依赖 | 获取命令列表 |

---

## 5. 状态与边界

### 5.1 命令执行上下文

- `state` 参数在 `__init__` 传入，`execute` 方法不接收 state。
- 命令实例是"无状态化"的：每次执行时创建新实例（`cmd_class(state)`），不保留前次执行状态。
- 阶段命令例外：因状态机需要跨步骤存储数据，使用实例属性（如 `_step`, `_players`, `_current_player_index`）维护状态。

### 5.2 边界条件

| 场景 | 处理方式 |
|------|----------|
| 命令目录不存在 | 注册器打印 WARN 日志并返回 |
| 个别命令文件导入失败 | 异常捕获，打印 WARN，不影响其他命令 |
| 非 `Command` 子类文件 | 被 `_extract_commands` 过滤掉 |
| 命令名/别名冲突 | `_register` 抛出 `ValueError`（Fail Fast） |
| 未知命令 | Registry 返回 `False`，打印提示信息 |
| 命令执行异常 | 外层 `try/except` 捕获，打印 traceback，返回 `False` |
| 阶段命令前置条件不满足 | 检查 `is_phase_executed()`，失败时打印警告并返回 |
| 阶段重复执行 | 检查后打印警告并返回 |
| 无参数命令 | `args` 为空列表，命令内部自行校验 |
| 参数类型错误 | 命令内部校验，一般返回 `False` 并打印用法提示 |
| KeyboardInterrupt | 部分交互式命令捕获并返回 `False` |

### 5.3 配置开关

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `testing.auto_forum` | bool | false | 广场阶段全自动 |
| `testing.auto_population` | bool | false | 人口阶段全自动 |
| `testing.auto_senate` | bool | false | 元老院阶段全自动 |
| `testing.bypass_player_check` | bool | false | 全人工测试模式 |
| `testing.force_battle_result` | str | nil | 强制战斗结果 |
| `forum_rules.enable_private_land_trade` | bool | false | 私地交易开关 |

---

## 6. 验收标准

1. ✅ 新命令文件放入 `commands/` 目录后自动被扫描注册，无需修改其他任何代码。
2. ✅ 命令别名与主命令名共享名称空间，输入别名可执行对应命令。
3. ✅ 冲突检测：两个命令文件使用相同 `name` 时，注册过程抛出 `ValueError` 并终止。
4. ✅ 冲突检测：别名与已有主命令名或别名冲突时，同样抛出 `ValueError`。
5. ✅ 类级别去重：同一命令类不会重复注册。
6. ✅ 命令目录不存在或个别文件导入失败时，不影响已注册的命令。
7. ✅ `help` 命令显示所有已注册命令（主命令名去重）的别名和描述。
8. ✅ `exit` / `quit` 命令设置退出回调，返回 `False` 触发主循环退出。
9. ✅ 阶段命令（Phase Command）按固定顺序执行，前置阶段未完成时给出提示并拒绝。
10. ✅ `next force` 可强制跳过缺失阶段推进回合。
11. ✅ 多玩家手动模式下，玩家切换时清屏并显示当前玩家派系信息。
12. ✅ 多玩家手动模式下，玩家切换时预留 PIN 码输入校验。
13. ✅ 自动模式下（auto_forum/auto_population/auto_senae），AI 玩家通过决策器自动操作。
14. ✅ 混合模式下（bypass_player_check=false），人类玩家手动交互，AI 玩家自动决策。
15. ✅ 调试命令（如 `build_fleet`/`bf`, `debug_fleet`/`df`, `debug_war`/`dw`, `assign_fleet`/`af`, `show_fleets`/`fl`, `process_fleet_construction`/`pfc`）可正常注册和执行。
16. ✅ 阶段命令内部状态机在竞标、裁员、凯旋投票等步骤间正确流转。
17. ✅ `turn` 命令自动执行所有未执行阶段，或返回异常信息。
18. ✅ `step` 命令逐步执行阶段，每阶段后等待用户确认。
19. ✅ 命令参数解析：`execute` 方法收到的 `args` 已去除命令名本身。
20. ✅ `reload` 命令可在线重载游戏配置。
21. ✅ `terms` 命令可在线切换本地化术语预设。
22. ✅ `load` 命令通过 `ScenarioLoader` 加载场景文件并显示启动信息。
23. ✅ 命令执行过程中产生的异常被捕获并记录日志，不导致整个进程崩溃。
24. ✅ 每个命令文件独立维护，功能内聚（一个文件对应一类相关命令）。
25. ✅ `_is_auto_mode()` 方法返回当前是否处于自动模式。
26. ✅ 欢迎界面/状态摘要/阶段进度在 `_show_current_player_overview()` 中统一展示。

---

## 7. 历史演化与证据

- **历史审计入口：** `git log -- src/ui/commands/`
- **历史名称：** `debug_cli.py`（旧版单文件 CLI，后拆分为命令架构）
- **首次实现版本：** MVP0.3（`src/ui/debug_cli.py`）
- **架构重构：** MVP0.4 — 引入 Command 设计模式，拆分为 `sys_base.py` + `sys_registry.py` + 功能模块
- **多玩家支持：** MVP0.7.11-12 — 加入 `Player` 系统、回合顺序、信息隔离方法
- **阶段命令统一：** 所有 7 个阶段命令均重构为 `Command` 子类，统一执行入口

---

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.4-04-sys_Command命令体系架构.md)

---

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-17 | Document Officer Worker | 初始完整版本，基于源码审计完成 Spec + Technical Mapping |
| v1.1 | 2026-07-17 | Audit Agent | 交叉审计后修正：阶段状态机步骤数、next命令优先级、调试命令列表 |
