# 架构收口 Sprint 任务包

创建日期：2026-06-20

适用阶段：MVP 0.7 功能完成后，MVP 0.9 / MVP 1.0 P1 功能开发前。

项目角色：

- 项目负责人：最终决策与需求确认。
- 项目经理 Agent：负责计划、任务拆分、任务书、文档管理、优先级控制。
- 系统架构师 Agent：负责架构审查、代码验收、本地调试、pytest 验证。
- DeepSeek：模块程序员，负责代码实现、补丁、实现报告和测试说明。

## 一、Sprint 总目标

在不新增 P1 复杂玩法的前提下，完成 MVP 0.7 代码的架构收口，使后续腐败、审判、忠诚度、人物养成、派系收买等 P1 功能可以建立在稳定分层上。

本 Sprint 不以“新增玩法”为目标，而以“降低后续开发风险”为目标。

## 二、工作目录基线

| 类型 | 路径 | 用途 |
| --- | --- | --- |
| 文档根目录 | `E:\Eagle of Rome` | 架构文档、项目管理、历史资料 |
| 代码根目录 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` | 唯一代码根、PyCharm 项目根、测试运行目录 |
| 运行环境说明 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md` | 本地环境基线 |
| Agent 说明 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md` | 代码协作规范 |
| Python | `C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe` | 测试和脚本运行解释器 |
| 测试框架 | `pytest` | 单元测试、回归测试 |

## 三、Sprint 范围

### 当前进度快照（2026-06-24）

| 编号 | 任务 | 当前状态 | 验收/归档 |
| --- | --- | --- | --- |
| AS-P0-01 | `PoliticalSystem` 重构设计与实现 | 已完成，SA 验收结论 `CONDITIONAL_PASS`，明确验收通过 | 代码提交 `ea770db`；验收文档见 `MVP 0.9 项目管理\03 开发任务书` |
| AS-P0-02 | `EconomicService` 重构设计与实现 | 已完成，最终验收结论 `PASS`，项目负责人手动测试确认通过 | 代码提交 `08295df`；SA/CGT 验收文档见 `MVP 0.9 项目管理\03 开发任务书` |
| AS-P0-03 | 私有字段访问收束第一批 | 已完成，SA `CONDITIONAL_PASS`，项目负责人手工测试通过 | 提交 `6cc972e`；指定测试 187 passed；全量测试 721 passed |
| AS-P0-04 | 广场阶段土地交易 API 化收尾 | 已完成，最终验收结论 `PASS`，项目负责人手工测试确认通过 | 代码提交 `24c1933`；SA/CGT 验收文档见 `MVP 0.9 项目管理\03 开发任务书` |

### P0 缺陷关闭记录

| 编号 | 缺陷 | 状态 | 验收/归档 |
| --- | --- | --- | --- |
| BUG-P0-20260623 | Forum current player sync | 已完成，最终验收结论 `PASS`，项目负责人手工测试确认通过 | 代码提交 `6ea1281`；SA/CGT 验收文档见 `MVP 0.9 项目管理\03 开发任务书` |

### 必做 P0

| 编号 | 任务 | 目标 | 责任分工 |
| --- | --- | --- | --- |
| AS-P0-01 | `PoliticalSystem` 重构设计与实现 | 将元老院/政治核心逻辑从 UI/API 分散状态收束到系统层 | 架构师先审查，DeepSeek 实现，架构师验收 |
| AS-P0-02 | `EconomicService` 重构设计与实现 | 将收入阶段经济结算从 UI 命令层迁移到服务层 | 架构师先审查，DeepSeek 实现，架构师验收 |
| AS-P0-03 | 私有字段访问收束第一批 | 为 `_senate_pending`、`_population_pending`、战争私有列表等提供公共访问/操作方法 | 架构师定边界，DeepSeek 实现 |
| AS-P0-04 | 广场阶段土地交易 API 化收尾 | 消除广场阶段步骤4仍绕过 API 的数据流尾巴 | DeepSeek 实现，架构师验收 |

### 应做 P1

| 编号 | 任务 | 目标 |
| --- | --- | --- |
| AS-P1-01 | `api_response` 统一 | 删除 `forum_api.py`、`senate_api.py` 中重复定义，统一从 `src.api` 导入 |
| AS-P1-02 | 旧竞标接口处理 | 明确 `GameState.place_bid()` / `resolve_auction()` 的废弃、兼容或迁移策略 |
| AS-P1-03 | 影子 `Province` 处理 | 明确 `entities.py` 中旧 `Province` 的废弃状态，避免后续 AI 误改 |
| AS-P1-04 | 测试环境确认 | 确认 pytest 可运行，并记录标准测试命令 |

### 暂不纳入

- 腐败机制。
- 监察官起诉与审判。
- 人物忠诚度。
- 人物养成。
- 派系资金收买人物。
- GUI 原型。

这些任务必须等架构收口 Sprint 完成或获得项目负责人明确批准后再启动。

## 四、任务包 1：PoliticalSystem 重构

### 任务编号

AS-P0-01

### PM 状态更新（2026-06-22）

本任务已由 DeepSeek 完成实现，并经系统架构师复核验收通过。

| 项目 | 结果 |
| --- | --- |
| SA 验收结论 | `CONDITIONAL_PASS`，明确验收通过 |
| 代码提交 | `ea770db`，`AS-P0-01 PoliticalSystem refactor` |
| 核心交付 | 新增 `src/core/systems/political_system.py`；`senate_api.py` 瘦身为薄 API 层；`phase_senate.py` 宣布/结算关键路径统一调用 `senate_api.resolve_senate()` |
| 公共接口补强 | 新增/补充 `GameState`、`WarSystem`、`Province` 公共方法，减少关键路径私有字段直改 |
| 新增测试 | `src/tests/test_systems/test_political_system.py` |
| 归档文档 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-01 PoliticalSystem 重构开发验收报告 - CGT-01.md`；`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-01 PoliticalSystem 重构 SA验收回执 - SA-04.md` |

SA 复跑测试结果：

- `test_senate_api.py`: 13 passed
- `test_phase_senate.py`: 35 passed
- `test_phase_senate_governor.py`: 4 passed
- `test_rebellion_command.py`: 5 passed
- `test_political_system.py`: 6 passed

遗留项已进入 MVP 1.0 目标规划与后续任务池：

- `TD-AS-P0-01-01` 自动提案生成规则迁移，P1
- `TD-AS-P0-01-02` `PoliticalSystem` 文档与函数索引同步，P2
- `TD-AS-P0-01-03` 历史私有字段访问清理，P2

### 任务目标

新增或整理 `PoliticalSystem`，将元老院阶段中的核心政治业务规则从 `phase_senate.py` 和 `senate_api.py` 中收束到系统层，降低后续腐败、审判、派系收买、政治提案扩展的耦合风险。

### 背景说明

DeepSeek 项目回顾已将 `PoliticalSystem` 重构列为 P1 开发前的最高优先级技术债务。Codex 文档-代码审计也发现元老院逻辑存在 API/UI 分散、私有字段访问、战争状态直接操作等问题。

### 依据文档路径

- `E:\Eagle of Rome\MVP 0.7 架构文档\EOR MVP 架构设计总览 （同步至 MVP 0.7）.docx`
- `E:\Eagle of Rome\MVP 0.7 架构文档\EOR MVP 模块调用与业务流程架构文档 (同步至 MVP 0.7).docx`
- `E:\Eagle of Rome\MVP 0.7 架构文档\EOR MVP 标准化接口设计文档 (同步至 MVP 0.7).docx`
- `E:\Eagle of Rome\MVP 0.9 项目管理\文档-代码一致性审计清单.md`

### 允许修改范围

- `src/core/systems/`
- `src/api/senate_api.py`
- `src/ui/commands/phase_senate.py`
- `src/core/game_state.py`
- `src/core/systems/war_system.py`
- `src/tests/test_api/`
- `src/tests/test_commands/`
- `src/tests/test_systems/`

### 禁止事项

- 不得改变元老院阶段玩家可见流程。
- 不得绕过 `senate_api` 直接让 UI 调用系统层执行玩家操作。
- 不得新增 UI 层直接修改私有字段。
- 不得删除现有提案类型、战争接管、停战草案、预算、总督任命逻辑。
- 不得引入 P1 新玩法。

### 实现要求

1. 系统架构师先输出 `PoliticalSystem` 边界审查意见。
2. DeepSeek 根据审查意见新增或调整政治系统类。
3. 将适合迁移的逻辑从 `phase_senate.py` / `senate_api.py` 迁入系统层。
4. API 层保留标准入口和标准返回格式。
5. UI 层只负责状态机、输入解析、输出展示。
6. 保持自动模式和手动模式行为一致。
7. 保持多玩家信息隔离不退化。

### 测试要求

- 元老院 API 测试。
- 元老院命令层测试。
- 战争宣战、停战、接管相关测试。
- 总督任命测试。
- 预算提案测试。
- 至少一次相关 pytest 回归。

### 验收标准

- 系统架构师验收 `Decision` 至少为 `CONDITIONAL_PASS`。
- 相关 pytest 通过或失败项有明确非本任务原因。
- UI/API/Core 分层更清晰，不新增反向依赖。
- 旧功能行为不退化。

### 交付格式

DeepSeek 必须输出：

- 修改文件清单。
- 迁移前后职责说明。
- 测试命令与结果。
- 未迁移逻辑清单及原因。
- 风险与后续建议。

## 五、任务包 2：EconomicService 重构

### 任务编号

AS-P0-02

### PM 状态更新（2026-06-22）

AS-P0-02 已完成最终闭环，SA 最终验收结论为 `PASS`，项目负责人手动测试确认通过，Git 归档提交已完成。

| 项目 | 结果 |
| --- | --- |
| SA 最终验收结论 | `PASS`，验收通过 |
| 项目负责人手动测试 | 已确认通过 |
| 代码提交 | `08295df`，`AS-P0-02 EconomicService refactor` |
| 复验结果 | 指定测试 + 额外合同回归合并运行：79 passed |
| 代码质量检查 | `git diff --check` 通过，仅 CRLF 工作区换行提示 |
| Git 状态 | 提交后 `git status --short` 无输出，工作区干净 |
| 边界审查归档 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-02 EconomicService 边界审查报告 - SA-01.md` |
| 技术任务书归档 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-02 EconomicService 重构开发任务书.md` |
| SA 验收回执 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-02 EconomicService 重构 SA验收回执 - SA-01.md` |
| CGT 开发验收报告 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-02 EconomicService 重构开发验收报告 - CGT-01.md` |

最终代码提交范围：

- `src/core/service/economic_service.py`
- `src/core/service/__init__.py`
- `src/core/entities/contract.py`
- `src/core/systems/war_system.py`
- `src/ui/commands/phase_revenue.py`
- `src/tests/test_core/test_economic_service.py`
- `src/tests/test_commands/test_phase_revenue_indemnity.py`

架构结果摘要：

- 新增 `EconomicService`，收入阶段核心经济结算已从 `phase_revenue.py` 迁移到服务层。
- `RevenueCommand` 已瘦身为阶段守卫、服务调用、展示和阶段标记。
- `WarSystem` / `Contract` 已补强公共接口。
- `EconomicService` 已移除 `WarSystem` 私有战争列表 fallback，仅通过公共方法读取战争对象。
- 未引入 P1 新玩法。

下一步：AS-P0-02 已关闭。PM 可准备发布 AS-P0-03 或下一个架构收口任务意图包。

### 任务目标

新增或整理 `EconomicService`，将收入阶段中的经济结算规则从 `phase_revenue.py` 迁移到服务层，使 UI 命令层不再承载核心经济规则。

### 背景说明

收入阶段当前承载私地收益、公地收益、合同结算、军团维护、海军维护、国家运营费、战争赔款、派系资金更新等复杂逻辑。后续腐败、忠诚度、人物养成、派系收买都会依赖经济状态，因此必须先服务化。

### 依据文档路径

- `E:\Eagle of Rome\MVP 0.7 架构文档\EOR MVP 模块调用与业务流程架构文档 (同步至 MVP 0.7).docx`
- `E:\Eagle of Rome\MVP 0.7 架构文档\EOR MVP 开发架构约束与注意事项（同步至MVP0.7）.docx`
- `E:\Eagle of Rome\MVP 0.7 函数索引说明书\服务与工具模块函数索引说明书.docx`
- `E:\Eagle of Rome\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`

### 允许修改范围

- `src/core/service/`
- `src/ui/commands/phase_revenue.py`
- `src/core/game_state.py`
- `src/core/entities/contract.py`
- `src/core/systems/military_system.py`
- `src/core/systems/naval_system.py`
- `src/tests/test_core/`
- `src/tests/test_commands/test_phase_revenue.py`
- `src/tests/test_api/`

### 禁止事项

- 不得改变收入阶段对玩家展示的核心结果。
- 不得将经济规则继续留在 UI 命令层新增扩展。
- 不得破坏资金操作原子性。
- 不得改变合同生命周期语义。
- 不得引入 P1 经济新玩法。

### 实现要求

1. 系统架构师先确认 `EconomicService` 的职责边界。
2. DeepSeek 新增或整理经济服务类。
3. `phase_revenue.py` 改为调用服务并打印结果。
4. 服务返回结构化结算结果，便于 CLI 和未来 GUI 使用。
5. 合同、军团、舰队、战争赔款的结算顺序保持文档一致。
6. DEBUG 日志保留或增强。

### 测试要求

- 私地收益测试。
- 公地收益测试。
- 包税合同结算测试。
- 工程/舰队合同结算测试。
- 军团和舰队维护费测试。
- 战争赔款测试。
- 收入阶段回归测试。

### 验收标准

- `phase_revenue.py` 职责明显减轻。
- 经济结算服务可被测试直接调用。
- 资金流转不出现半状态。
- 相关测试通过。

### 交付格式

DeepSeek 必须输出：

- 修改文件清单。
- 结算流程迁移说明。
- 服务返回结构说明。
- 测试命令与结果。
- 风险与遗留问题。

## 六、任务包 3：私有字段访问收束第一批

### 任务编号

AS-P0-03

### PM 最终状态更新（2026-06-25）

SA 已基于 Git HEAD `6ea1281` 完成当前代码私有字段访问只读审计、第一批技术边界定稿，并已直接向 CGT-01 发布开发任务。

第一批范围：

- 人口 pending。
- WarSystem 跨层容器与待解散队列。
- 总督原子交接。
- 公地认购残余 `_land_private` 写入。

延期为 P1/P2 技术债：

- Contract 生命周期。
- 场景加载。
- 死亡资产回收。
- 调试工具与测试夹具清理。

归档文件：

- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-03 私有字段访问收束第一批 边界审查报告 - SA-01.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-03 私有字段访问收束第一批 开发任务书.md`

最终闭环结果：

| 项目 | 结果 |
| --- | --- |
| SA Decision | `CONDITIONAL_PASS` |
| 项目负责人手工测试 | 通过 |
| SA 指定测试 | 187 passed |
| SA 全量测试 | 721 passed |
| 目标私有字段扫描 | 无匹配 |
| 代码质量检查 | `git diff --check` 通过 |
| Git 提交 | `6cc972e`，`AS-P0-03 Close first-batch private field access` |
| Git 状态 | 提交后工作区清洁 |
| SA 验收回执 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-03 私有字段访问收束第一批 SA验收回执 - SA-01.md` |

条件项仅为新增公共接口同步 MVP 0.7 函数索引，已转为 P1 文档一致性任务，不要求代码返工，也不阻塞 Sprint 结束。

### 任务目标

针对当前最容易导致架构漂移的私有字段访问，新增公共方法或系统层封装，逐步减少 UI/API 对内部状态的直接操作。

### 优先收束对象

| 对象 | 当前风险 | 建议方向 |
| --- | --- | --- |
| `_senate_pending` | 元老院投票、否决、提案结算多处直读直写 | `GameState` / `PoliticalSystem` 提供方法 |
| `_population_pending` | 人口阶段庆典、投票临时数据直写 | `GameState` 提供清理和查询方法 |
| `_active_wars` / `_truce_wars` / `_threats` | UI/API 直接移动战争列表 | `WarSystem` 提供状态转移方法 |
| `_governor_designate_id` / `_old_governor_id` | 总督任命和交接直改 | `Province` 或政治系统提供方法 |
| `_land_private` | 土地交易、认购、迁移直改 | `Figure` 或土地服务提供方法 |

### 允许修改范围

- `src/core/game_state.py`
- `src/core/systems/war_system.py`
- `src/core/entities/province.py`
- `src/core/entities/figure.py`
- `src/api/*.py`
- `src/ui/commands/*.py`
- 相关测试

### 禁止事项

- 不得一次性大范围重构所有私有字段。
- 不得只改调用点而不补测试。
- 不得破坏现有存档/序列化兼容。

### 实现要求

1. 系统架构师先确认第一批收束范围。
2. DeepSeek 分批新增公共方法。
3. 每次只迁移高风险调用点。
4. 保留行为一致。
5. 对无法迁移的调用点记录技术债务。

### 验收标准

- 至少完成元老院、人口、战争状态三类中的一类高风险收束。
- 不新增 UI 层私有字段直改。
- 相关测试通过。

## 七、任务包 4：广场阶段土地交易 API 化收尾

### 任务编号

AS-P0-04

### PM 状态更新（2026-06-23）

AS-P0-04 已完成最终闭环，SA 最终验收结论为 `PASS`，项目负责人手工测试确认通过，Git 归档提交已完成。

| 项目 | 结果 |
| --- | --- |
| SA 最终验收结论 | `PASS`，验收通过 |
| 项目负责人手工测试 | 已确认通过 |
| 代码提交 | `24c1933`，`AS-P0-04 Forum land trade API closeout` |
| SA 本地复跑 | `test_forum_api.py` 57 passed；`test_phase_forum_cmd_layer.py` 18 passed；`test_phase_forum_fleet.py` 3 passed；`test_phase_forum_triumph.py` 4 passed；`test_func_forum.py` 5 passed |
| 代码质量检查 | `git diff --check` 通过，仅 CRLF 工作区换行提示 |
| Git 状态 | 提交后 `git status --short` 无输出，工作区干净 |
| SA 验收回执 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-04 广场阶段土地交易 API化收尾 SA验收回执 - SA-01.md` |
| CGT 开发验收报告 | `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-04 广场阶段土地交易 API化收尾 开发验收报告 - CGT-01.md` |

最终代码提交范围：

- `src/api/forum_api.py`
- `src/core/game_state.py`
- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_commands/test_phase_forum_cmd_layer.py`
- `src/ui/commands/phase_forum.py`

架构结果摘要：

- 手动/自动土地交易已统一经 `forum_api.transact_land()` 或等价 API 入口记录。
- 自动路径不再由 UI 层直接写 `land_trades` pending。
- `resolve_land_trades()` 已改用 `GameState.clear_forum_action("land_trades")`，不再直接写 `_forum_pending["land_trades"]`。
- `transact_land()` 使用 `seller.can_sell_land(land)`，未新增 `_land_private` 私有字段访问。
- `LandTradingService` 土地价格和结算规则未被修改。

下一步：AS-P0-04 已关闭。架构收口 Sprint 剩余 P0 主线为 AS-P0-03 私有字段访问收束第一批。

### 任务目标

完成广场阶段步骤4土地交易的数据流统一，使自动模式和手动模式均通过 `forum_api` 记录与结算土地交易，不再绕过 API 直接写临时状态。

### 背景说明

DeepSeek 回顾报告指出：广场阶段步骤1-3 已完成 API 化，但交易环节自动模式仍存在直接调用 `state.add_forum_action` 或直接写 pending 的尾巴。

### 允许修改范围

- `src/api/forum_api.py`
- `src/ui/commands/phase_forum.py`
- `src/ui/processors/auto_player_processor.py`
- `src/core/service/land_trading_service.py`
- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_commands/test_phase_forum*.py`

### 禁止事项

- 不得改变土地交易价格和结算规则。
- 不得破坏财务官交易限制。
- 不得绕过玩家权限校验，除非自动模式明确传入 bypass 参数。

### 实现要求

1. 手动土地交易通过 `forum_api.transact_land`。
2. 自动土地交易也通过 `forum_api.transact_land` 或等价 API。
3. `resolve_land_trades` 只负责结算，不负责接受绕过 API 的临时写入。
4. 结算后清理临时交易数据必须通过公共方法或 API 内部封装。

### 测试要求

- 手动交易成功。
- 手动交易失败：资金不足、土地不足、非法人物。
- 自动模式交易成功。
- 交易结算后 pending 清理。
- 多玩家权限不退化。

### 验收标准

- 广场阶段步骤4数据流与步骤1-3 一致。
- 无新增 `_forum_pending` 直接写入。
- 测试通过。

## 八、Sprint 统一禁止事项

本 Sprint 所有任务均禁止：

- 启动 P1 新玩法。
- 绕过系统架构师审查处理核心分层问题。
- 把业务规则继续堆到 UI 命令层。
- 为了测试通过而删除功能。
- 直接大范围格式化无关文件。
- 修改 `E:\Eagle of Rome` 下历史档案作为代码交付。

## 九、系统架构师审查要求

涉及以下内容时，系统架构师必须审查：

- `PoliticalSystem`
- `EconomicService`
- API 边界调整
- 私有字段访问替代方案
- 多玩家信息隔离
- UI/API/Core 分层
- 战争状态转移
- 合同生命周期
- 资金原子性

系统架构师输出格式：

```text
Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER
Reasons:
Files reviewed:
Test status:
Architecture risks:
Required DeepSeek changes:
```

## 十、Sprint 完成定义

满足以下条件，方可认为架构收口 Sprint 完成：

1. `PoliticalSystem` 重构至少获得 `CONDITIONAL_PASS`。
2. `EconomicService` 重构至少获得 `CONDITIONAL_PASS`。
3. 广场阶段土地交易 API 化完成。
4. 私有字段访问第一批收束完成，并记录剩余债务。
5. pytest 可在代码根目录执行，且关键相关测试通过。
6. 相关文档或函数索引已同步或生成待同步清单。
7. 项目负责人确认可以进入 P1 功能开发。

### 完成定义状态（2026-06-25）

| 条件 | 状态 | 说明 |
| --- | --- | --- |
| `PoliticalSystem` 重构至少获得 `CONDITIONAL_PASS` | 已满足 | SA 验收结论为 `CONDITIONAL_PASS`，明确验收通过 |
| `EconomicService` 重构至少获得 `CONDITIONAL_PASS` | 已满足 | SA 最终验收 `PASS`，项目负责人手动测试确认通过 |
| 广场阶段土地交易 API 化完成 | 已满足 | SA 最终验收 `PASS`，项目负责人手工测试确认通过 |
| 私有字段访问第一批收束完成，并记录剩余债务 | 已满足 | SA `CONDITIONAL_PASS`；目标扫描无匹配；剩余 P1/P2 技术债已登记 |
| pytest 可执行且关键相关测试通过 | 已满足 | AS-P0-03 指定测试 187 passed；全量测试 721 passed |
| 相关文档或函数索引已同步或生成待同步清单 | 已满足 | 函数索引条件项已生成 P1 文档一致性任务，不阻塞收口 |
| 项目负责人确认可以进入 P1 功能开发 | 待正式批准 | 手工测试已通过；SA 建议结束 Sprint，等待项目负责人阶段批准 |

## 十一、建议执行顺序

1. 系统架构师审查 `PoliticalSystem` 边界。（已完成）
2. DeepSeek 执行 AS-P0-01。（已完成）
3. 系统架构师验收 AS-P0-01。（已完成，`CONDITIONAL_PASS`）
4. 系统架构师审查 `EconomicService` 边界。（已完成，`CONDITIONAL_PASS`）
5. DeepSeek 执行 AS-P0-02。（已完成）
6. 系统架构师验收 AS-P0-02。（已完成，`PASS`）
7. DeepSeek 执行 AS-P0-04。（已完成）
8. 系统架构师验收 AS-P0-04。（已完成，`PASS`）
9. CGT-01 执行 AS-P0-03 第一批。（已完成）
10. 系统架构师完成 AS-P0-03 与 Sprint 技术验收。（已完成，`CONDITIONAL_PASS`）
11. 项目负责人正式批准架构收口 Sprint 结束并选择下一阶段入口。（待批准）
