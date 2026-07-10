# AS-P0-02 EconomicService 重构开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## Changed files

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\economic_service.py`（新增）
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\commands\phase_revenue.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\entities\contract.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\systems\war_system.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\core\service\__init__.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_economic_service.py`（新增）
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_revenue_indemnity.py`

## Implementation summary

- 新增 `EconomicService`，承接收入阶段核心经济结算。
- `RevenueCommand` 已瘦身为阶段守卫、调用服务、打印结算结果、记录阶段完成。
- 保留 `RevenueCommand` 旧私有方法入口作为兼容包装，避免旧测试和旧调用断裂。
- 结算顺序按 AS-P0-02 任务书收口为：战争赔款、国家运营费、公地收益、私地收益、合同结算、质保递减、军团维护、海军维护、派系津贴与抽成。
- `Contract` 增加质保递减、舰队合同付款标记、合同收支记录公共方法。
- `WarSystem` 增加全部战争与待赔款战争公共查询方法，收入服务只使用公共查询方法结算战争赔款。

## Architecture notes

- `EconomicService.settle_revenue_phase()` 返回结构化结算单，包含起止国库、国库变化、赔款、国家运营费、公地收益、私地收益、合同行、维护费、派系入账与调试事件。
- UI 层不再执行经济公式、合同生命周期推进或赔款清算，只负责展示服务返回的数据。
- 服务层不调用 API 层，避免 UI/API/Service 方向倒挂。
- 战争赔款结算通过 `WarSystem.get_wars_with_indemnity_due()` / `get_all_wars()` 读取，不再依赖战争系统私有列表。
- 未引入腐败、忠诚度、派系收买、审判罚金等 P1 新玩法。
- 合同语义保持：普通工程付款完成后竣工；舰队建造合同付款完成后只标记已付款，仍等待海军建造完成流程。

## Tests executed

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

Additional regression:

```text
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe -m pytest -p no:cacheprovider src/tests/test_commands/test_func_contracts.py -q
git diff --check
```

## Test results

- `test_economic_service.py`: 6 passed
- `test_phase_revenue.py`: 11 passed
- `test_phase_revenue_indemnity.py`: 3 passed
- `test_phase_revenue_ext.py`: 4 passed
- `test_contract_ext.py`: 5 passed
- `test_entity_contract.py`: 12 passed
- `test_naval_system.py`: 14 passed
- `test_contract_api.py`: 4 passed
- Additional `test_func_contracts.py`: 20 passed
- `git diff --check`: passed；仅有 CRLF 工作区换行提示，无空白错误。

## Known risks

- `RevenueCommand` 为兼容历史测试仍保留若干私有包装方法；后续可在测试迁移完成后再清理。
- 收入阶段自动/手动玩家可见输出已保留核心标题、表格与关键行，但服务结算顺序已按 AS-P0-02 任务书调整。
- 旧模块和旧测试中仍存在部分直接访问实体私有字段的历史用法，本任务仅收口收入阶段关键路径。

## SA review request

CGT-01 请求 SA-01 对 AS-P0-02 EconomicService 重构进行最终架构验收。当前建议：代码可进入 SA review；不建议 CGT-01 自动提交 git，等待 SA/项目负责人归档指令。
