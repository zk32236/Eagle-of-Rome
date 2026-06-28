# AS-P0-02 EconomicService 重构开发任务书

创建日期：2026-06-22

发布角色：系统架构师 SA

执行对象：DeepSeek 开发员 DSD-02

任务性质：P0 架构收口任务

当前代码基线：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`，Git HEAD `ea770db`

重要说明：DeepSeek 不具备本地 Agent 能力，不直接修改项目文件、不执行 pytest。请按本任务书输出 Markdown 交付包，由 SA 负责落地代码、运行测试和验收。

## 1. 任务目标

请基于当前代码基线完成 `EconomicService` 重构方案的代码补丁输出。

本任务目标是将收入阶段核心经济结算规则从 UI 命令层 `src/ui/commands/phase_revenue.py` 收束到服务层：

`src/core/service/economic_service.py`

完成后应达到：

1. `RevenueCommand` 只负责阶段守卫、调用服务、打印服务返回结果、标记阶段完成。
2. 私地收益、公地收益、合同结算、合同质保、国家运营费、战争赔款、军团维护费、舰队维护费、派系资金入账等核心结算规则由 `EconomicService` 承担。
3. 旧收入阶段玩家可见核心结果不退化。
4. 服务返回结构可供 CLI 和未来 GUI 复用。
5. 新增直接测试 `EconomicService` 的 pytest 用例。

## 2. 必须参考的代码文件

请以以下代码文件为当前基线，不要基于旧版本或自行想象接口：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_revenue.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\land_trading_service.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\relation_query_service.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\game_state.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\contract.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\province.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\figure.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\military_system.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\naval_system.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\war_system.py
```

请重点参考以下测试：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_revenue.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_revenue_indemnity.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_phase_revenue_ext.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_contract_ext.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_entities\test_entity_contract.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems\test_naval_system.py
C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_contract_api.py
```

## 3. 新增文件要求

必须新增：

```text
src/core/service/economic_service.py
src/tests/test_core/test_economic_service.py
```

可按需要小范围修改：

```text
src/ui/commands/phase_revenue.py
src/core/entities/contract.py
src/core/systems/war_system.py
src/core/game_state.py
src/core/service/__init__.py
```

原则：只改完成本任务必要的文件。不要做无关格式化或跨模块重构。

## 4. EconomicService 职责边界

请实现 `EconomicService`，建议入口：

```python
class EconomicService:
    def __init__(self, state):
        self.state = state

    def settle_revenue_phase(self) -> dict:
        ...
```

`EconomicService` 应负责：

1. 战争赔款结算。
2. 国家运营费扣除。
3. 国家公地收益结算。
4. 私地收益结算，包含个人财富增加和派系抽成累计。
5. 包税合同结算。
6. 公共工程合同付款、利润、派系抽成、完成和解绑。
7. 合同质保递减和到期。
8. 调用 `MilitarySystem` 维护费公共方法。
9. 调用 `NavalSystem` 维护费公共方法。
10. 派系津贴和派系抽成最终入账。
11. 返回结构化结算数据和调试信息。

`EconomicService` 不负责：

1. 玩家输入。
2. 命令行表格打印。
3. 收入阶段是否可执行的前置判断。
4. `state.mark_phase_executed("revenue")`。
5. 任何 P1 新玩法。

## 5. RevenueCommand 修改要求

请将 `RevenueCommand.execute()` 改为薄命令层：

1. 保留死亡阶段已执行检查。
2. 保留收入阶段重复执行检查。
3. 保留原玩家可见标题、表格、摘要输出。
4. 调用 `EconomicService(self.state).settle_revenue_phase()`。
5. 使用服务返回的 `data` 打印私地收益表、派系收益表、合同/维护费/赔款摘要。
6. 服务成功后再调用 `state.mark_phase_executed("revenue")`。
7. 不再在 UI 命令层直接执行私地、公地、合同、赔款、维护费、派系入账等核心规则。

允许保留或调整以下 UI 展示函数：

```text
_print_faction_table()
_print_private_land_table()
```

如果保留旧私有结算函数，只能作为兼容薄包装，不能继续承载真实规则。更推荐删除或改为调用服务的内部结果。

## 6. 结算顺序要求

请保持旧收入阶段的资金流顺序：

1. 战争赔款。
2. 国家运营费。
3. 国家公地收益。
4. 私地收益。
5. 合同结算。
6. 合同质保。
7. 军团维护费。
8. 舰队维护费。
9. 派系津贴与派系抽成入账。

不得随意改变顺序。若你认为必须调整顺序，交付包中必须单独说明原因，并标记为需要 SA 决策。

## 7. 服务返回结构要求

`EconomicService.settle_revenue_phase()` 必须返回普通 dict，不要导入 API 层工具。

建议结构：

```python
{
    "success": True,
    "message": "Revenue phase settled",
    "data": {
        "starting_treasury": 100,
        "ending_treasury": 120,
        "treasury_delta": 20,
        "indemnities": [],
        "national_opex": {},
        "public_land_income": {},
        "private_land_rows": [],
        "contract_rows": [],
        "maintenance": {
            "military": {},
            "naval": {},
        },
        "faction_rows": {},
        "debug_events": [],
    },
    "errors": [],
}
```

字段要求：

1. `private_land_rows` 必须能支撑原私地收益表打印。
2. `faction_rows` 必须能支撑原派系金库收益表打印。
3. `contract_rows` 必须表达包税、公建付款、合同完成、承包商死亡终止、舰队合同付款完成等事件。
4. `maintenance.military` 和 `maintenance.naval` 必须表达维护费金额、成功状态和消息。
5. `indemnities` 必须表达战争名、金额、收入或支出、是否结清。
6. `errors` 只用于真正失败或异常；旧逻辑中可继续执行的情况应作为 warning/debug event 记录。

## 8. 公共接口补强要求

为减少私有字段直改，请补强以下接口。

### 8.1 WarSystem

新增下列方法之一：

```python
def get_all_wars(self) -> list:
    ...
```

或：

```python
def get_wars_with_indemnity_due(self) -> list:
    ...
```

用途：替代收入阶段当前直接拼接 `_war_deck`、`_war_discard`、`_active_wars`、`_threats`、`_truce_wars`。

### 8.2 Contract

请新增必要公共方法，避免服务层直接修改质保和舰队合同付款私有字段。

建议：

```python
def advance_warranty(self) -> int:
    ...

def mark_fleet_construction_paid(self) -> None:
    ...
```

可选：

```python
def record_tax_collection(self, amount: int) -> None:
    ...

def record_works_payment(self, amount: int) -> None:
    ...
```

注意：不得改变现有 `mark_complete()`、`terminate()`、`expire()` 的语义。

### 8.3 GameState

优先复用：

```text
add_treasury()
add_faction_treasury()
add_figure_wealth()
get_all_contracts()
get_war_system()
get_military_system()
naval_system
```

如果现有接口足够，不强制新增 `GameState` 方法。

## 9. 必须迁移的旧逻辑

请从 `phase_revenue.py` 迁移以下规则：

1. `_settle_indemnities()`。
2. `_deduct_national_opex()`。
3. 国家公地收益计算，包括 `bumper_harvest` 和 `natural_disaster` 修正。
4. `_collect_private_land_income()`。
5. `_collect_contract_revenues()`。
6. `_process_contract_warranty()`。
7. 军团维护费调用与结果汇总。
8. 舰队维护费调用与结果汇总。
9. 派系津贴和派系抽成最终入账。

## 10. 必须保留的旧行为

不得退化：

1. 私地收益会增加人物财富。
2. 私地收益派系抽成会进入派系金库。
3. 国家公地收益会进入国库。
4. 国家运营费会扣除国库。
5. 包税合同每年向国库缴纳合同价，并给承包者利润。
6. 公共工程合同每年从国库付款，并给承包者净利润。
7. 公共工程最后一年按剩余金额付款。
8. 承包者死亡时合同终止，并解绑对应行省合同。
9. 公共工程完成时解绑项目合同。
10. 舰队建造合同付款完成后不得错误标记为普通公共工程竣工；舰队系统仍负责舰队竣工。
11. 质保年限逐年递减，到期后合同进入旧逻辑预期状态。
12. 战争赔款为正数时收入国库并清零；为负数时若国库不足，不得错误清零。
13. 军团维护费仍由 `MilitarySystem.apply_maintenance()` 处理。
14. 舰队维护费仍由 `NavalSystem.apply_maintenance()` 处理。
15. 收入阶段成功后仍标记为已执行。

## 11. 禁止事项

1. 不得改变收入阶段玩家可见核心结果。
2. 不得引入腐败、忠诚度、派系收买、审判罚金等 P1 新玩法。
3. 不得将新的经济规则继续堆在 UI 命令层。
4. 不得破坏资金流转顺序。
5. 不得让合同状态、国库、人物财富、派系金库出现部分更新后异常退出的半状态。
6. 不得改变合同生命周期语义。
7. 不得绕过现有玩家、派系、国库资金归属规则。
8. 不得让 UI 层继续直接修改私有字段。
9. 不得让服务层调用 API 层。
10. 不得做无关大范围格式化或跨模块重构。
11. 不得修改 `E:\Eagle of Rome` 下历史档案作为代码交付。
12. 不得声称本地 pytest 已通过；DeepSeek 不执行本地测试。

## 12. 测试要求

请新增：

```text
src/tests/test_core/test_economic_service.py
```

至少覆盖：

1. 公地收益和私地收益结算。
2. 包税合同结算。
3. 公共工程合同正常付款。
4. 公共工程最后一年付款和完成。
5. 承包商死亡导致合同终止和行省解绑。
6. 战争赔款收入和支出。
7. 合同质保递减。
8. `RevenueCommand` 调用服务后仍能标记收入阶段完成。

SA 验收时将运行：

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

## 13. 交付格式

请输出一个 Markdown 交付包，文件名建议：

```text
AS-P0-02 EconomicService 重构 - 完整交付包 - DSD-02.md
```

交付包必须包含：

```text
Decision by DSD: READY_FOR_SA_REVIEW

Baseline:

Changed files:

Implementation summary:

Patch or full replacement code:

Tests for SA to run:

Known risks:

Self-check checklist:
```

代码交付要求：

1. 优先提供统一 diff，必须能相对 Git HEAD `ea770db` 应用。
2. 如果无法提供可靠 diff，请按文件提供完整替换代码块，并明确每个文件路径。
3. 不要只描述思路，必须给出可落地代码。
4. 不要把多个版本混在一起。
5. 不要省略 imports。
6. 不要输出伪代码。

## 14. SA 验收标准

SA 将按以下标准验收：

1. 新增 `EconomicService`，并且收入阶段核心经济结算已迁移到服务层。
2. `RevenueCommand` 不再承载核心经济规则。
3. 服务返回结构能支撑当前 CLI 展示和未来 GUI 复用。
4. 私有字段直改明显减少，尤其是战争列表、合同质保、舰队合同付款字段。
5. 旧收入阶段行为不退化。
6. 任务指定 pytest 通过，或失败项有明确非本任务原因。
7. 未引入 P1 新玩法。
8. 未做无关大范围重构。

验收结论将为：

```text
PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER
```

## 15. 发布确认

本技术任务书由 SA 基于 PM 意图包和边界审查定稿。

DeepSeek 请按本任务书输出 Markdown 交付包；SA 收到后负责本地应用、调试、测试与验收。
