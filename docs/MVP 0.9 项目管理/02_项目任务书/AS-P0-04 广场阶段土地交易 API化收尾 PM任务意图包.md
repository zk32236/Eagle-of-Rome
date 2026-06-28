# AS-P0-04 广场阶段土地交易 API化收尾 PM任务意图包

创建日期：2026-06-23

发布对象：系统架构师 SA

任务性质：PM 级任务意图，不是 DeepSeek/CGT-01 技术开发任务书

## 一、当前判断

AS-P0-01 `PoliticalSystem` 重构已完成并验收通过，AS-P0-02 `EconomicService` 重构已完成最终闭环并获得 SA `PASS`。架构收口 Sprint 当前剩余 P0 主线中，AS-P0-04 是范围较清晰、风险可控、适合优先推进的接口边界任务。

本任务只聚焦“广场阶段土地交易 API 化收尾”，不合并《版本规划》中 P2 项“土地交易决策可以统一迁移到 AutoPlayerProcessor 中”。后者属于自动决策归口优化，可在本任务完成后作为独立技术债或 P2 优化项排期。

## 二、任务目标

请 SA 基于当前代码与架构文档，定稿或补充 AS-P0-04 的技术任务边界，并直接向 CGT-01 发布开发任务书。

PM 目标是完成广场阶段步骤 4 土地交易的数据流收口：

1. 手动土地交易应通过 `forum_api` 或等价 API 记录。
2. 自动土地交易也应通过统一 API 记录，不再绕过 API 直接写临时状态。
3. 土地交易结算入口应只负责结算，不再兼容绕过 API 的临时写入。
4. 交易结算后的 pending 清理应通过公共方法或 API 内部封装完成。
5. 保持现有土地交易规则、价格、权限、多玩家信息隔离不退化。

## 三、优先级与阶段位置

| 项目 | 结论 |
| --- | --- |
| 任务编号 | AS-P0-04 |
| 任务名称 | 广场阶段土地交易 API 化收尾 |
| 优先级 | P0 |
| 所属阶段 | 架构收口 Sprint |
| 前置条件 | AS-P0-01、AS-P0-02 已完成 |
| 后续依赖 | GUI 原型、私地交易正常模式完善、骑士/土地/财务官相关 P1 功能 |

PM 判断：AS-P0-04 应先于 GUI 原型和土地相关 P1 扩展完成。它不新增玩法，但能为后续 GUI、自动模式、多玩家权限和土地经济功能提供稳定数据流。

## 四、依据文档

请 SA 优先参考：

- `E:\Eagle of Rome\MVP 0.9 项目管理\架构收口 Sprint 任务包.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\后续任务池.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\文档-代码一致性审计清单.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

代码根目录：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## 五、建议 SA 审查范围

| 范围 | PM 关注点 |
| --- | --- |
| `src/api/forum_api.py` | 是否已有统一土地交易 API；返回结构是否符合 `{success, message, data, errors}` |
| `src/ui/commands/phase_forum.py` | 手动模式是否绕过 API 写 pending 或直接执行结算逻辑 |
| `src/ui/processors/auto_player_processor.py` | 自动模式是否存在直接调用状态写入或绕过 API 的土地交易路径 |
| `src/core/service/land_trading_service.py` | 土地交易结算职责是否清晰；是否混入交易记录入口职责 |
| `src/core/game_state.py` | forum pending / action 记录和清理是否需要公共方法补强 |
| `src/core/entities/figure.py` | 私地数量调整是否有公共方法，是否存在 `_land_private` 直改风险 |
| `src/tests/test_api/` | 是否覆盖手动/自动交易 API 路径 |
| `src/tests/test_commands/` | 是否覆盖广场阶段步骤 4 与多玩家权限不退化 |

## 六、PM 级禁止事项

请 SA 在技术任务书中明确约束 CGT-01：

- 不得改变土地交易价格和结算规则。
- 不得改变财务官交易限制与权限校验语义。
- 不得引入新的土地玩法、GUI 功能或 P1 机制。
- 不得合并处理“土地交易决策迁移到 AutoPlayerProcessor”这个 P2 优化项。
- 不得新增 UI 层直接修改 pending 或私有字段。
- 不得让结算函数继续接收绕过 API 的临时写入路径。
- 不得做无关格式化或大范围重构。
- 不得修改 `E:\Eagle of Rome` 下历史档案作为代码交付。

## 七、PM 级实现期望

SA 可据此细化技术任务书：

1. 明确土地交易记录入口：手动模式和自动模式均应通过 `forum_api.transact_land` 或等价 API。
2. 明确土地交易结算入口：`resolve_land_trades` 或等价结算函数只负责结算，不负责接收绕过 API 的写入。
3. 明确 pending 清理策略：通过 GameState 公共方法或 API 内部封装完成。
4. 明确权限策略：手动模式必须保持玩家/派系权限校验；自动模式如需 bypass，必须由 SA 明确参数边界。
5. 明确返回结构：API 层保持 `{success, message, data, errors}`。
6. 明确保留行为：交易成功、资金不足、土地不足、非法人物、财务官限制、多玩家信息隔离等旧行为不退化。

## 八、测试要求建议

请 SA 在技术任务书中要求 CGT-01 覆盖：

| 测试类型 | 建议目标 |
| --- | --- |
| API 测试 | 手动土地交易成功；资金不足失败；土地不足失败；非法人物失败；权限校验失败 |
| 命令层测试 | 广场阶段步骤 4 手动流程通过 API 记录交易 |
| 自动模式测试 | 自动土地交易路径通过统一 API 或等价 API，不直接写 pending |
| 结算测试 | 交易结算后 pending 清理正确；资金与土地转移正确 |
| 多玩家测试 | 非当前玩家或非本派系人物不可越权交易；信息隔离不退化 |
| 回归测试 | 广场阶段现有步骤 1-3 不退化 |

## 九、PM 验收标准

AS-P0-04 最终完成后，PM 期望看到：

| 类别 | 验收标准 |
| --- | --- |
| 架构 | 手动/自动土地交易数据流统一到 API 或等价封装，不新增 UI 层 pending/私有字段直写 |
| 行为 | 土地交易价格、财务官限制、权限校验、结算结果保持一致 |
| 测试 | SA 指定测试通过；失败项如有必须明确非本任务原因 |
| 风险 | 若发现 AutoPlayerProcessor 决策归口问题，仅登记为 P2 技术债，不阻塞本任务 |
| 交付 | SA 输出验收回执，结论至少为 `CONDITIONAL_PASS` |

## 十、任务发布机制

本任务后续发布机制如下：

1. PM 输出本任务意图包。
2. SA 基于当前代码边界定稿技术任务书。
3. SA 直接发布给 CGT-01。
4. CGT-01 输出实现交付包。
5. SA 执行本地应用、代码审查、pytest 验收。
6. SA 向 PM 返回验收结论。
7. PM 更新架构收口 Sprint 进度、任务池和项目进度记录。

## 十一、SA 输出建议

请 SA 完成或补充：

1. AS-P0-04 技术边界审查结论。
2. 面向 CGT-01 的技术任务书发布确认。
3. 后续 CGT-01 输出后的 SA 验收报告。

PM 将根据 SA 回执更新：

- `架构收口 Sprint 任务包.md`
- `MVP0.7模块开发优先级表.md`
- `后续任务池.md`
- `项目进度记录.md`
