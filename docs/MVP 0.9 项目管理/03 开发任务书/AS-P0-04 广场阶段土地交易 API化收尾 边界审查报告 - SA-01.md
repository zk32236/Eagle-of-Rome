# AS-P0-04 广场阶段土地交易 API化收尾 边界审查报告 - SA-01

日期：2026-06-23

角色：系统架构师 SA-01

Decision: CONDITIONAL_PASS

## Reasons

AS-P0-04 可以进入 CGT-01 开发执行，但必须严格限定为“广场阶段土地交易数据流 API 化收尾”，不得扩大为土地交易规则重做、GUI 原型、自动决策归口迁移或 P1 土地玩法。

当前代码已经具备较好的收口基础：手动土地交易路径已经通过 `forum_api.transact_land()` 记录；土地价格与资金/土地转移主要由 `LandTradingService` 承担；`Figure` 已有 `sell_land()`、`buy_land()` 等公共方法。剩余主要风险集中在两个点：

1. 自动土地交易路径仍在 `phase_forum.py` 中直接调用 `GameState.add_forum_action("land_trades", ...)`，没有经过统一 API 入口。
2. `forum_api.resolve_land_trades()` 结算后仍直接写 `state._forum_pending["land_trades"] = []`，需要改为公共方法或 API 内部封装。

因此本任务适合作为 P0 架构收口任务推进。

## Files Reviewed

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\api\forum_api.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_forum.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\processors\auto_player_processor.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\land_trading_service.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\game_state.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\figure.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_forum_api.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_cmd_layer.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_fleet.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_triumph.py`

## Recommended Boundary

### API Layer

`forum_api.transact_land()` 应成为土地交易记录的唯一公共入口，覆盖手动模式和自动模式。

API 层应负责：

- 权限校验入口。
- seller / buyer 合法性校验。
- 死亡人物、土地数量、交易数量基础校验。
- 将合法交易写入 forum pending。
- 返回统一 `{success, message, data, errors}` 结构。

自动模式如需绕过玩家权限，应只通过显式参数 `bypass_permission=True` 绕过玩家/派系权限校验；不得绕过人物合法性、土地数量、交易数量等核心规则。

### UI Command Layer

`phase_forum.py` 应保留：

- 广场阶段步骤推进。
- 输入解析和玩家提示。
- 自动模式是否触发土地交易的流程编排。
- 调用 `forum_api.transact_land()` 记录交易。
- 调用 `forum_api.resolve_land_trades()` 执行结算。

`phase_forum.py` 不应继续直接写 forum pending，也不应直接修改 `_forum_pending`、`_land_private` 等私有字段。

### Service Layer

`LandTradingService` 应继续只承担土地交易结算规则：

- 价格计算。
- seller / buyer 资金土地校验。
- 调用 `Figure.sell_land()` / `Figure.buy_land()`。
- 派系土地统计更新。
- 交易历史记录。

本任务不应重写价格、结算、财务官权限或土地经济规则。

### GameState

`GameState` 应补充或使用公共方法完成 pending 清理，例如：

- `clear_forum_action("land_trades")`
- 或 `clear_forum_land_trades()`

具体命名可由 CGT-01 按现有代码风格选择，但生产代码不得再直接写 `state._forum_pending["land_trades"] = []`。

## Logic To Change

1. 将 `phase_forum.py` 自动土地交易路径中的直接 pending 写入改为调用 `forum_api.transact_land()`。
2. 将 `forum_api.resolve_land_trades()` 结算后的 pending 清理改为公共方法或 API 内部封装。
3. 如触及 `forum_api.transact_land()`，应优先使用 `Figure.land_private` 或 `Figure.can_sell_land()` 等公共接口，避免新增私有字段读取。

## Logic To Preserve

- 土地交易价格。
- 财务官交易限制与权限校验语义。
- 私地数量和资金转移规则。
- seller / buyer 死亡、非法人物、土地不足、资金不足等失败行为。
- 广场阶段步骤 1-3 现有行为。
- 手动模式玩家可见流程。
- 多玩家信息隔离。
- 自动模式现有触发时机。

## Out Of Scope

- 不处理“土地交易决策统一迁移到 AutoPlayerProcessor”P2 优化项。
- 不引入 GUI。
- 不新增土地玩法。
- 不重构整个广场阶段。
- 不重写 `LandTradingService` 经济规则。
- 不修改 `E:\Eagle of Rome` 下历史档案作为代码交付。

## Required Public Methods Or Interfaces

最低建议：

- 保留并统一使用 `forum_api.transact_land(state, player_id, seller_id, buyer_id, land, price, bypass_permission=False)`。
- 新增或复用 `GameState` 公共 pending 清理方法，避免生产代码直接写 `_forum_pending`。

可选建议：

- 在 `forum_api.transact_land()` 中使用 `seller.land_private` 或 `seller.can_sell_land(land)` 替代 `_land_private` 读取。

## Required Pytest Targets

CGT-01 至少应执行：

- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_commands/test_phase_forum_cmd_layer.py`
- `src/tests/test_commands/test_phase_forum_fleet.py`
- `src/tests/test_commands/test_phase_forum_triumph.py`

建议新增或补强覆盖：

- 手动土地交易成功记录 pending。
- 非当前玩家或非本派系人物交易失败。
- 自动土地交易路径调用统一 API。
- 结算后 `land_trades` pending 被正确清理。
- 土地不足、资金不足、非法人物、死亡人物失败路径不退化。

## Architecture Risks

- 若自动模式直接改为 bypass 所有校验，会破坏土地交易规则。
- 若结算函数继续兼容绕过 API 的写入路径，会保留当前架构债。
- 若把决策归口迁移到 AutoPlayerProcessor，会扩大本任务范围并干扰 P2 排期。
- 若重写 LandTradingService，容易引入经济规则回归。

## CGT-01 Implementation Constraints

- 不得改变土地交易价格和结算规则。
- 不得改变财务官交易限制与权限校验语义。
- 不得引入新土地玩法、GUI 功能或 P1 机制。
- 不得合并处理“土地交易决策迁移到 AutoPlayerProcessor”P2 优化项。
- 不得新增 UI 层直接修改 pending 或私有字段。
- 不得让结算函数继续直接写 `_forum_pending`。
- 不得做无关格式化或大范围重构。
- 不得自动提交 Git；实现完成后由 SA/项目负责人确认归档。

## Technical Task Brief Publication Status

已基于本审查结论生成面向 CGT-01 的 AS-P0-04 技术开发任务书，待发送给 CGT-01 执行。
