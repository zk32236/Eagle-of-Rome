# AS-P0-04 广场阶段土地交易 API化收尾 开发任务书

日期：2026-06-23

发布人：SA-01 / 系统架构师

执行人：CGT-01

任务性质：P0 架构收口开发任务

代码根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

当前代码基线：`08295df AS-P0-02 EconomicService refactor`

## 1. 任务目标

完成广场阶段步骤 4 土地交易 API 化收尾，使手动模式和自动模式的土地交易记录统一通过 `forum_api.transact_land()` 或等价 API 入口进入 pending，结算入口只负责结算，不再保留 UI 层绕过 API 直接写 pending 的生产路径。

本任务不新增玩法，不改变土地交易价格，不改变财务官权限语义，不迁移自动决策归口。

## 2. 必须完成的改动

### 2.1 统一土地交易记录入口

检查并保持手动土地交易路径通过：

```python
forum_api.transact_land(...)
```

自动土地交易路径也必须改为通过同一 API 或等价 API 入口记录交易。

当前重点关注：

- `src/ui/commands/phase_forum.py`

自动路径不得继续直接调用：

```python
state.add_forum_action("land_trades", ...)
```

如自动模式需要绕过玩家权限，必须使用显式边界，例如：

```python
bypass_permission=True
```

该参数只能绕过玩家/派系权限校验，不得绕过人物合法性、死亡状态、土地数量、交易数量等核心规则。

### 2.2 收紧结算函数职责

检查并修改：

- `src/api/forum_api.py`

`resolve_land_trades()` 或等价结算函数应只负责：

- 读取已记录的 pending land trades。
- 调用 `LandTradingService.execute_trade()` 执行结算。
- 汇总成功/失败结果。
- 在结算完成后清理 pending。

结算函数不得承担交易记录入口职责，也不得兼容 UI 绕过 API 的新写入路径。

### 2.3 pending 清理改为公共方法

检查并修改：

- `src/core/game_state.py`
- `src/api/forum_api.py`

生产代码不得直接写：

```python
state._forum_pending["land_trades"] = []
```

请在 `GameState` 中新增或复用公共方法完成指定 forum pending 分类清理。命名可按现有风格选择，例如：

- `clear_forum_action(action_type)`
- `clear_forum_actions(action_type)`
- `clear_forum_land_trades()`

要求：

- 不改变 `clear_forum_pending()` 原有全量清理语义。
- 不破坏已有 pending 分类。
- 结算后只清理本轮 `land_trades`，不得误清其他广场 pending。

### 2.4 避免新增私有字段访问

如修改 `forum_api.transact_land()`，应优先使用 `Figure` 公共属性或公共方法：

- `figure.land_private`
- `figure.can_sell_land(amount)`
- `figure.sell_land(amount)`
- `figure.buy_land(amount)`

不得新增对 `_land_private` 等私有字段的直接写入。

## 3. 允许修改范围

主要允许修改：

- `src/api/forum_api.py`
- `src/ui/commands/phase_forum.py`
- `src/core/game_state.py`
- `src/tests/test_api/test_forum_api.py`
- `src/tests/test_commands/test_phase_forum_cmd_layer.py`

按需允许小范围修改：

- `src/core/entities/figure.py`
- `src/core/service/land_trading_service.py`
- `src/ui/processors/auto_player_processor.py`
- 其他与土地交易 API 收口直接相关的测试文件

如果需要修改 `LandTradingService`，只能是为配合接口收口的最小改动，不得改变价格和结算规则。

`auto_player_processor.py` 只允许在发现真实绕过 API 的土地交易记录路径时做最小收口；不得在本任务中执行“土地交易决策统一迁移到 AutoPlayerProcessor”的 P2 优化。

## 4. 禁止事项

- 不得改变土地交易价格和结算规则。
- 不得改变财务官交易限制与权限校验语义。
- 不得引入新的土地玩法、GUI 功能、腐败/忠诚度/收买等 P1 机制。
- 不得合并处理“土地交易决策迁移到 AutoPlayerProcessor”P2 优化项。
- 不得新增 UI 层直接修改 pending 或私有字段。
- 不得让结算函数继续直接写 `_forum_pending`。
- 不得做无关格式化或大范围重构。
- 不得修改 `E:\Eagle of Rome` 下历史档案作为代码交付。
- 不得自动提交 Git。

## 5. 行为保持要求

必须保持以下旧行为不退化：

- 手动土地交易成功。
- 自动土地交易成功。
- 土地不足时失败。
- 资金不足时失败。
- seller / buyer 非法时失败。
- 死亡人物不可参与交易。
- 非当前玩家或非本派系人物不可越权交易。
- 财务官限制和权限语义保持一致。
- 广场阶段步骤 1-3 不受影响。
- 多玩家信息隔离不退化。

## 6. 测试要求

请至少执行：

```powershell
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_forum_api.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_cmd_layer.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_fleet.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_forum_triumph.py -q
```

建议新增或补强测试：

1. `forum_api.transact_land()` 手动成功记录 pending。
2. 非当前玩家或非本派系人物交易失败。
3. 自动土地交易路径通过 `forum_api.transact_land()` 或等价 API 入口，不直接写 pending。
4. `resolve_land_trades()` 结算后只清理 `land_trades` pending。
5. 土地不足、资金不足、非法人物、死亡人物失败路径不退化。

同时执行：

```powershell
git diff --check
```

## 7. 交付要求

完成后请输出并归档开发验收报告：

`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-04 广场阶段土地交易 API化收尾 开发验收报告 - CGT-01.md`

报告必须包含：

- 修改文件清单。
- 实际改动摘要。
- 是否发现额外绕过 API 的土地交易路径。
- 是否新增 `GameState` 公共 pending 清理方法。
- 是否保留土地价格、权限、财务官限制和多玩家隔离。
- pytest 执行结果。
- `git diff --check` 结果。
- 未解决问题或建议登记为 P1/P2 的事项。

## 8. SA 验收口径

SA 验收时将重点检查：

- 手动/自动土地交易是否统一走 API 或等价封装。
- UI 层是否仍有新增或残留的生产路径 pending 直写。
- `resolve_land_trades()` 是否仍直接写 `_forum_pending`。
- `LandTradingService` 价格和结算规则是否未被无关改动。
- 测试是否覆盖自动路径、结算清理和权限失败路径。

验收结论将为：

```text
PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER
```
