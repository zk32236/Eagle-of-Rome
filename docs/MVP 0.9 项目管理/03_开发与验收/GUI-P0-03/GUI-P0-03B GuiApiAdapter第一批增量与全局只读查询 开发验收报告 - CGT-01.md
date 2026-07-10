# GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 基线

- 项目根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- 任务基线：`d0b615d Add GUI-P0-03B PM intent package`
- 执行对象：CGT-01
- Git：未提交

## 修改文件清单

- `src/api/gui_query_api.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/shell/BottomQueryBar.qml`
- `src/tests/test_api/test_gui_query_api.py`
- `src/tests/test_gui/test_adapter.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 开发验收报告 - CGT-01.md`

## 实现摘要

- 新增薄只读 API：`src/api/gui_query_api.py`。
- `GuiApiAdapter.get_global_query_result(viewer_id, query_id)` 统一委托 `gui_query_api.get_global_query_result()`。
- `GuiSessionStore.doGlobalQuery()` 不再在 Store 内拼装游戏、派系、战争、军团明细，只负责调用 Adapter、保存查询结果并发出 UI 刷新信号。
- 底部 12 查询按钮保留；第一批接入游戏状态、派系信息、战争列表、军团状态，其余保持统一占位。
- 新增 GUI 查询 API focused tests，并补充 Adapter/Store 委托路径测试。

## 查询按钮接入状态表

| 查询 ID | 显示名称 | 状态 | 数据来源与边界 |
| --- | --- | --- | --- |
| `game_status` | 游戏状态 | 已接入 | `session_api.get_session_snapshot()` + GameState 公共属性，展示年份、回合、阶段、当前玩家、国库、存活人物与派系数量 |
| `faction_info` | 派系信息 | 只读 | viewer 派系显示自身金库；其他派系仅显示公开名称、成员数、公开影响力，不裸显他派金库 |
| `war_list` | 战争列表 | 只读 | 使用 `WarSystem` 公共 getter 汇总 active/threat/truce/resolved 战争，展示公开摘要，不暴露未公开细节 |
| `legion_status` | 军团状态 | 只读 | 使用 `MilitarySystem.get_all_legions()` 与军团公开展示字典，展示数量和公开状态 |
| `character_query` | 人物查询 | 占位 | 本轮不接入 |
| `treasury` | 派系金库 | 占位 | 本轮不接入额外金库查询 |
| `public_land` | 公地信息 | 占位 | 本轮不接入 |
| `private_land` | 私地信息 | 占位 | 本轮不接入 |
| `contract_status` | 合同状态 | 占位 | 本轮不接入 |
| `province_info` | 行省信息 | 占位 | 本轮不接入 |
| `fleet_status` | 舰队状态 | 占位 | 本轮不接入 |
| `help` | 帮助 | 占位 | 本轮不接入 |

## DTO / 权限过滤说明

- 查询返回结构统一为 `{id, title, title_key, status, message, message_key, message_params, items, summary}`。
- `items` 使用 `{label, label_key, value, meta}`，保留当前 GUI 可直接显示字段，同时提供稳定 key 供后续 i18n 扩展。
- viewer 校验由 `gui_query_api.get_global_query_result()` 负责；未知 viewer 返回失败响应。
- `faction_info` 中只有 viewer 派系包含 `treasury`；其他派系只返回公开摘要。
- `war_list` 仅通过公共 getter 获取战争集合，不直接读取 WarSystem 私有容器。
- `legion_status` 仅通过公共 getter 获取军团集合，不直接读取 MilitarySystem 私有容器。

## 架构边界确认

- 查询路径保持：`QML -> GuiSessionStore -> GuiApiAdapter -> gui_query_api -> Core/System/Entity`。
- 未新增 CLI Command 调用。
- 未调用 `game_api.execute_phase()`、`game_api.execute_turn()` 或 `CombatCommand`。
- 未接入元老院、广场、战争、收入、决算复杂业务动作。
- Store 已移除本轮查询明细拼装逻辑，仅保留状态保存与信号通知职责。

## i18n 预留

- 新增 GUI 文案 key 已集中到 `src/ui/gui/localization.py`。
- DTO 保留 `title_key`、`message_key`、`label_key`，支持后续 GUI-I18N 统一解析。
- QML 本轮未新增散落中文/英文 UI 文案。

## 测试命令与结果

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_gui_query_api.py" -q
```

结果：`6 passed in 0.08s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui\test_adapter.py" -q
```

结果：`11 passed in 0.17s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui\test_qml_startup.py" -q
```

结果：`7 passed in 2.49s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`30 passed in 3.16s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`773 passed in 11.95s`

## 静态检查

```powershell
git diff --check
```

结果：通过；仅出现工作区 CRLF 换行提示，无空白错误。

```powershell
rg -n "\._active_wars|\._threats|\._truce_wars|\._legions|\['_active_wars'\]|\['_threats'\]|\['_truce_wars'\]|\['_legions'\]" "src\ui\gui" "src\api\gui_query_api.py" "src\api\session_api.py"
```

结果：无匹配。

```powershell
rg -n "game_api\.execute_phase|game_api\.execute_turn|CombatCommand|phase_senate|phase_forum|phase_revenue|phase_combat|_active_wars|_threats|_truce_wars|_legions" "src\ui\gui" "src\api\gui_query_api.py" "src\api\session_api.py"
```

结果：无禁止调用匹配；宽松私有名扫描命中 `get_active_wars()`、`get_truce_wars()`、`get_all_legions()` 与 `war_threats` DTO/key 字段，均为公共方法或数据 key 的子串误报，不属于私有字段访问。

```powershell
rg -n "游戏状态|派系信息|战争列表|军团状态|人物查询|派系金库|公地信息|私地信息|合同状态|行省信息|舰队状态|帮助|查询结果|关闭" "src\ui\gui\qml\shell" "src\ui\gui\qml\components"
```

结果：无匹配。

```powershell
rg -n "[ \t]+$" "src\api\gui_query_api.py" "src\tests\test_api\test_gui_query_api.py"
```

结果：无匹配。

## 当前 git status

```text
 M src/tests/test_gui/test_adapter.py
 M src/ui/gui/api_adapter.py
 M src/ui/gui/localization.py
 M src/ui/gui/qml/shell/BottomQueryBar.qml
 M src/ui/gui/session_store.py
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术边界审查报告 - SA-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 开发验收报告 - CGT-01.md
?? src/api/gui_query_api.py
?? src/tests/test_api/test_gui_query_api.py
```

## 风险与遗留问题

- `gui_query_api` 当前为第一批只读查询薄 API，后续若继续接入合同、行省、舰队等查询，应继续复用同一 DTO 形态并补充对应公共读取接口。
- DTO 中保留中文展示字段以兼容当前 GUI 浮窗；同时提供 key 字段，后续 GUI-I18N 可进一步迁移为统一 key 解析。
- 战争和军团查询仅展示公开摘要，未接入任何行动入口；后续 GUI-P0-03C/03D 如扩展战斗或海军操作，应另行走独立任务边界审查。

## SA review request

CGT-01 请求 SA-01 对 GUI-P0-03B《GuiApiAdapter第一批增量与全局只读查询》进行最终架构验收。
