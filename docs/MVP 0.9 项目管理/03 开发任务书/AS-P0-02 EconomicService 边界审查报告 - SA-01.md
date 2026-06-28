# AS-P0-02 EconomicService 边界审查报告 - SA-01

创建日期：2026-06-22

审查对象：`EconomicService` 重构边界

代码基线：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`，Git HEAD `ea770db`

文档根目录：`E:\Eagle of Rome`

## Decision

CONDITIONAL_PASS

## Reasons

1. 当前 `phase_revenue.py` 同时承担 UI 展示、阶段守卫、阶段推进、私地收益、公地收益、合同结算、维护费、国家运营费、战争赔款、派系资金入账，已经超过 UI 命令层职责。
2. 代码中已存在 `src/core/service/` 服务目录和 `LandTradingService` 等服务模式，因此本轮应新增 `src/core/service/economic_service.py`，不应放入 `systems` 或 `api`。
3. 收入阶段已有回归测试，但核心结算测试目前多绑定 `RevenueCommand` 私有方法。重构后必须新增直接测试 `EconomicService` 的用例，并保留收入命令层回归测试。
4. 本轮可以推进实现，但必须先补足少量公共接口，避免服务层继续直接读写 `WarSystem` 私有战争列表、`Contract` 质保私有字段和舰队合同私有字段。
5. 本轮边界应限定为架构收口，不得引入腐败、忠诚度、派系收买、审判罚金等 P1 新玩法。

## Files Reviewed

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_revenue.py`
  - `RevenueCommand.execute()`：收入阶段主流程。
  - `_deduct_national_opex()`：国家运营费。
  - `_settle_indemnities()`：战争赔款。
  - `_process_contract_warranty()`：合同质保递减。
  - `_collect_private_land_income()`：私地收益。
  - `_collect_contract_revenues()`：包税与公共工程合同结算。
  - `_print_faction_table()` / `_print_private_land_table()`：UI 展示。
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\land_trading_service.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\relation_query_service.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\game_state.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\contract.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\military_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\naval_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\war_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_revenue.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_revenue_indemnity.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_phase_revenue_ext.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_contract_ext.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_entities\test_entity_contract.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems\test_naval_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_contract_api.py`

## Recommended EconomicService Responsibilities

`EconomicService` 应新增在：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\economic_service.py`

建议职责：

1. 作为收入阶段核心经济结算服务，接收 `GameState`，执行一轮收入结算。
2. 统一收入阶段资金流顺序：
   - 战争赔款结算。
   - 国家运营费扣除。
   - 国家公地收益。
   - 私地收益与派系抽成累计。
   - 合同收益与合同生命周期推进。
   - 合同质保递减。
   - 军团维护费。
   - 舰队维护费。
   - 派系津贴与派系抽成入账。
3. 返回结构化结算结果，供 CLI 打印和未来 GUI 复用。
4. 保留或增强关键资金流 DEBUG 日志，便于 SA 验收时追踪每一类资金变化。
5. 不承担 UI 输入、玩家展示排版、阶段守卫、阶段完成标记。

## Logic To Migrate From phase_revenue.py

应迁移到 `EconomicService`：

1. `_settle_indemnities()` 的战争赔款收支规则。
2. `_deduct_national_opex()` 的国家运营费计算与扣款规则。
3. `execute()` 中国家公地收益计算，包括丰收、自然灾害事件修正。
4. `_collect_private_land_income()` 的私地收益、个人财富增加、派系抽成累计。
5. `_collect_contract_revenues()` 的包税合同、公建合同、死亡承包商终止、合同完成、行省解绑、舰队建造合同付款完成语义。
6. `_process_contract_warranty()` 的质保递减和到期逻辑，但应通过 `Contract` 公共方法完成。
7. `execute()` 中军团维护费、舰队维护费调用与结果汇总。
8. `execute()` 中派系津贴和派系抽成最终入账。
9. 收入阶段结算所需的可观测日志。

## Logic That Should Remain In UI Command Layer

应保留在 `RevenueCommand`：

1. 阶段前置守卫：死亡阶段是否已执行、收入阶段是否已执行。
2. 阶段标题、分隔线、表格、玩家可见文字输出。
3. 调用 `EconomicService.settle_revenue_phase()` 并按返回数据打印。
4. `_print_faction_table()` 与 `_print_private_land_table()` 等展示函数。
5. 成功结算后的 `state.mark_phase_executed("revenue")`。
6. 命令返回布尔值和 CLI 层异常兜底。

## Logic That Should Remain In Entity/System Layer

应保留在实体或系统层：

1. `Contract` 自身生命周期状态转换，如 `mark_complete()`、`terminate()`、`expire()`。
2. `MilitarySystem.calculate_maintenance()` 与 `MilitarySystem.apply_maintenance()`。
3. `NavalSystem.calculate_maintenance()` 与 `NavalSystem.apply_maintenance()`。
4. `WarSystem` 的战争集合管理、战争查询、战争状态转换。
5. `Province` 的包税合同、公建合同绑定与解绑。
6. `Figure` 的财富增加逻辑。
7. `GameState` 的国库、人物财富、派系金库、合同集合、系统实例查询。

## Required Public Methods Or Interfaces

为减少私有字段直改，建议本轮补足以下公共接口：

1. `WarSystem`
   - 新增 `get_all_wars()` 或 `get_wars_with_indemnity_due()`。
   - 用于替代 `phase_revenue.py` 当前直接拼接 `_war_deck`、`_war_discard`、`_active_wars`、`_threats`、`_truce_wars`。
2. `Contract`
   - 新增 `advance_warranty()` 或 `decrement_warranty()`，内部处理 `_warranty_remaining` 递减和到期状态。
   - 新增 `mark_fleet_construction_paid()` 或等价公共方法，避免收入结算直接写 `_paid`。
   - 如需要，可新增 `record_tax_collection(amount)`、`record_works_payment(amount)`，避免服务层直接散落修改 `total_collected`、`total_spent` 和 `remaining_years`。
3. `GameState`
   - 优先复用 `add_treasury()`、`add_faction_treasury()`、`add_figure_wealth()`、`get_all_contracts()`、`get_war_system()`、`get_military_system()`、`naval_system`。
   - 若现有方法足够，不强制新增。
4. `Province`
   - 优先复用现有合同解绑方法。
   - 不允许服务层直接写行省私有字段。

## Required Service Return Structure

`EconomicService` 不应导入 API 层工具，但应返回 GUI/CLI 友好的普通字典：

```python
{
    "success": bool,
    "message": str,
    "data": {
        "starting_treasury": int,
        "ending_treasury": int,
        "treasury_delta": int,
        "indemnities": list,
        "national_opex": dict,
        "public_land_income": dict,
        "private_land_rows": list,
        "contract_rows": list,
        "maintenance": {
            "military": dict,
            "naval": dict,
        },
        "faction_rows": dict,
        "debug_events": list,
    },
    "errors": list,
}
```

说明：

- `private_land_rows` 应保留 `RevenueCommand` 打印私地表所需字段。
- `faction_rows` 应保留派系名称、原金库、津贴、抽成、最终金库。
- `contract_rows` 应能表达包税收入、公建付款、承包商死亡终止、合同完成、舰队建造合同已付款等事件。
- `errors` 仅记录结算失败或异常；旧行为中允许继续的警告应放在 `data` 或日志中。

## Required Pytest Targets

DeepSeek 实现后，SA 至少应运行：

```text
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_core/test_economic_service.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_commands/test_phase_revenue.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_commands/test_phase_revenue_indemnity.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_core/test_phase_revenue_ext.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_core/test_contract_ext.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_entities/test_entity_contract.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_systems/test_naval_system.py -q
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_api/test_contract_api.py -q
```

新增测试建议：

1. `test_economic_service_public_and_private_land_income`
2. `test_economic_service_tax_farming_contract_settlement`
3. `test_economic_service_public_works_payment_and_completion`
4. `test_economic_service_dead_contractor_terminates_and_unbinds`
5. `test_economic_service_indemnity_income_and_expense`
6. `test_economic_service_warranty_decay`
7. `test_revenue_command_calls_service_and_marks_phase`

## Architecture Risks

1. 当前收入结算并非严格事务系统。服务化时必须保持每个结算项目内部的更新顺序一致，不能先改合同状态再失败于资金或人物更新。
2. 战争赔款当前依赖 `WarSystem` 私有列表，若不补公共查询方法，重构会把私有字段访问从 UI 层搬到服务层，架构收益不足。
3. 合同结算混合包税、公建、舰队建造合同语义，容易误删舰队建造合同“付款完成但等待舰队系统竣工”的旧行为。
4. `RevenueCommand` 现有测试会检查输出文字和私有方法行为，重构时需要同步调整测试目标，不能只新增服务测试而放弃命令层回归。
5. `MilitarySystem` 与 `NavalSystem` 维护费仍会直接修改国库，这是现有系统边界。本轮只允许服务层调用这些公共方法，不建议把维护费内部规则再迁入 `EconomicService`。

## DeepSeek Implementation Constraints

1. 必须以 Git HEAD `ea770db` 为当前代码基线。
2. 必须新增 `src/core/service/economic_service.py`。
3. 必须将收入阶段核心经济规则从 `phase_revenue.py` 迁移到服务层。
4. 不得改变收入阶段玩家可见核心结果。
5. 不得引入腐败、忠诚度、派系收买、审判罚金等 P1 新玩法。
6. 不得新增 UI 层直接修改私有字段。
7. 不得绕过现有国库、人物财富、派系金库归属规则。
8. 不得改变合同生命周期语义。
9. 不得让 UI 绕过服务层继续堆经济规则。
10. 不得修改 `E:\Eagle of Rome` 历史档案作为代码交付。
11. 不得做无关格式化、跨模块大重构或清理无关历史问题。
12. DeepSeek 不具备本地测试执行权，交付时不得声称 pytest 已在本机通过；只能列出建议 SA 运行的测试命令。

## Technical Task Brief Publication Status

已基于本边界审查定稿 DeepSeek 技术开发任务书：

`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\AS-P0-02 EconomicService 重构开发任务书.md`

发布状态：SA 技术任务书已归档为可直接发送给 DeepSeek 的版本。DeepSeek 交付后，由 SA 执行本地代码修改、测试和验收。
