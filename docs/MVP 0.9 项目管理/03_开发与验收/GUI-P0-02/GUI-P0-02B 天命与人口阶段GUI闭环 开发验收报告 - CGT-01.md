# GUI-P0-02B 天命与人口阶段GUI闭环 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件清单

新增：
- `src/core/service/mortality_service.py`
- `src/api/mortality_api.py`
- `src/tests/test_api/test_mortality_api.py`
- `src/ui/gui/qml/stages/MortalityStage.qml`

修改：
- `src/core/game_state.py`
- `src/core/service/__init__.py`
- `src/api/session_api.py`
- `src/ui/commands/phase_mortality.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`

未触碰 / 未纳入本任务：
- `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx` 仍是本任务前已有无关修改。

## 天命服务/API/GUI 实现摘要

- 新增 `MortalityService`，承载事件抽取、死亡、风调雨顺、国泰民安、天降猛男、无妄天灾等旧天命规则，并返回结构化 `events / impacts / logs / next_phase_id`。
- 新增 `mortality_api.execute_mortality_phase()` 和 `get_mortality_view()`，统一返回 `{success, message, data, errors}`。
- `MortalityCommand` 改为 CLI 包装层：调用 `MortalityService` 后格式化打印，保留旧 CLI 输出关键词与回归行为。
- `GameState` 新增 `record_active_event()`，天命服务通过公共接口写入本回合 active event，不再由天命命令层直写 `_active_events`。
- GUI 新增 `MortalityStage.qml`，通过 `GuiSessionStore.doExecuteMortality()` 执行天命，展示事件名称、效果摘要和影响对象。

## 人口阶段整合与回归说明

- 人口阶段继续复用既有 `population_api`、`session_api.get_population_view()` 和 GUI-P0-01 `PopulationStage`。
- `session_api.get_population_view()` 现在只有在 `current_phase_id == "population"` 且 viewer 是当前玩家时才给出 `can_campaign / can_vote / can_complete`。
- 为测试/开发保留显式入口：`create_gui_prototype_session(start_phase="population")` 可直接进入人口阶段；正式默认入口为 `start_phase="mortality"`。

## 阶段顺序与天命后不跳人口

固定 GUI 阶段顺序：

```text
mortality, revenue, forum, population, senate, combat, resolution
天命, 收入, 广场, 人口, 元老院, 战争, 决算
```

`session_api.get_session_snapshot()` 不再固定 `population`，改为按第一个未执行阶段推导 `current_phase_id`。

验证结果：
- 默认 GUI session 当前阶段为 `mortality`。
- 执行天命后 `mortality` 标记已执行。
- 执行天命后 `current_phase_id == "revenue"`。
- 执行天命后不会跳到 `population`。

## 架构边界说明

- GUI/QML 只调用 `GuiSessionStore`。
- `GuiSessionStore` 通过 `GuiApiAdapter` 调用 API。
- `GuiApiAdapter` 调用 `mortality_api` / `session_api` / `population_api`，不导入命令层。
- `mortality_api` 调用 `MortalityService`，不调用 `MortalityCommand`，也不通过 `game_api.execute_phase()`。
- 精确扫描结果：
  - `rg -n "MortalityCommand|execute_phase\(" src\api\mortality_api.py src\api\session_api.py src\ui\gui`：无匹配。
  - `rg -n "_active_events" src\api\mortality_api.py src\api\session_api.py src\core\service\mortality_service.py src\ui\gui src\ui\commands\phase_mortality.py`：无匹配。

## 测试命令与结果

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_mortality_api.py" -q
```

结果：`5 passed in 0.08s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_mortality.py" -q
```

结果：`9 passed in 0.20s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`23 passed in 1.78s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_population_api.py" -q
```

结果：`29 passed in 0.20s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_mortality.py" "src\tests\test_commands\test_phase_population.py" -q
```

结果：`30 passed in 0.35s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_population_disband.py" "src\tests\test_commands\test_phase_population_truce.py" -q
```

结果：`11 passed in 0.26s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_mortality_disaster.py" "src\tests\test_commands\test_phase_mortality_hero.py" "src\tests\test_core\test_phase_mortality_ext.py" -q
```

结果：`7 passed in 0.26s`

## Full src/tests

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`753 passed in 9.35s`

## git diff --check

结果：通过；仅有 Windows 工作区 CRLF 提示，无空白错误。

## 当前 git status --short

当前工作区仍包含本任务前已有无关 Excel 修改，以及本轮 GUI-P0-02B 代码/测试/报告变更。未提交 Git。

## 人工视觉验收待确认项

请 SA 或项目负责人在真实 Windows GUI 窗口确认：
1. 默认进入 GUI 时左侧选中 `天命`，顶部/右侧状态显示当前阶段为天命。
2. 天命页面可见“执行天命”按钮，按钮在当前玩家可操作时可点击。
3. 点击后显示事件名称、摘要和影响对象。
4. 点击后当前阶段进入 `收入`，收入仍为后续任务占位，不跳到人口。
5. 选择人口阶段时仍能看到人口切片，但非当前真实阶段时按钮不可操作。
6. 中文正常显示，布局无明显重叠，天命按钮和结果列表可达。

## 手工测试反馈修正

2026-07-02 项目负责人手工测试反馈：点击“执行天命”后，“完成当前玩家操作”仍不可用，玩家不清楚如何进入收入阶段。

处理结论：
- “完成当前玩家操作”是人口阶段玩家交接按钮，不应承担从天命进入收入阶段的职责。
- GUI 正确流程应为：点击“执行天命”后，权威状态将 `current_phase_id` 推进到 `revenue`，界面自动选中左侧“收入”阶段并显示收入 placeholder。
- 已补充 `GuiSessionStore.doExecuteMortality()`：天命执行成功并刷新 snapshot 后，自动将 `selectedPhaseId` 同步为新的 `current_phase_id`。
- 收入阶段仍不执行经济业务，保持 GUI-P0-02D 后续任务承接边界。

补充复跑：
- `src\tests\test_gui`: `23 passed in 1.82s`
- `src\tests\test_api\test_mortality_api.py`: `5 passed in 0.06s`

## R2 UX 修正

2026-07-02 SA-01 R2 反馈确认：上一版执行天命后直接跳到“收入”页，玩家要手动点回“天命”才能看结果，不符合阶段 UX。阶段应采用两步模型：

1. 执行/结算本阶段并停留结果页。
2. 玩家点击单独按钮进入下一阶段。

已完成修正：
- `execute_mortality_phase(state, viewer_player_id)` 现在只执行天命事件与效果，不调用 `state.mark_phase_executed("mortality")`。
- 新增 `GameState.record_phase_result()` / `get_phase_result()` / `clear_phase_result()`，由 Core 封装阶段结果状态。
- `execute_mortality_phase()` 成功后把结构化天命结果记录到权威阶段结果，重复执行会被拒绝，避免重复死亡、丰收或天灾。
- 新增 `advance_mortality_phase(state, viewer_player_id)`，校验 viewer、当前阶段、当前玩家和天命结果存在后，才标记 `mortality` 已完成并推进到 `revenue`。
- `get_mortality_view()` 返回 `result / events / can_execute / can_advance / executed / current_phase_id / next_phase_id`。
- `GuiApiAdapter` 新增 `advance_mortality()`。
- `GuiSessionStore` 新增 `canAdvanceMortality` 和 `doAdvanceMortality()`。
- `doExecuteMortality()` 成功后保持 `selectedPhaseId == "mortality"`，结果页继续可见。
- `doAdvanceMortality()` 成功后才将 `selectedPhaseId` 同步到 `revenue`。
- `MortalityStage.qml` 新增 `进入收入阶段` 按钮，绑定 `sessionStore.canAdvanceMortality`。

R2 UX 行为确认：
- 初始天命页：`can_execute=True`，`can_advance=False`。
- 点击“执行天命”：权威 `current_phase_id` 仍为 `mortality`，界面仍停留天命页，事件结果可见，`can_execute=False`，`can_advance=True`。
- 点击“进入收入阶段”：`mortality` 才标记完成，权威 `current_phase_id` 进入 `revenue`，界面自动选中收入 placeholder。
- “完成当前玩家操作”仍只属于人口阶段。
- 不执行收入阶段经济结算，收入仍为 GUI-P0-02D 占位。

R2 补充测试：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_mortality_api.py" -q
```

结果：`7 passed in 0.09s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`23 passed in 2.19s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_mortality.py" -q
```

结果：`9 passed in 0.23s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui\test_session_api.py" -q
```

结果：`11 passed in 0.13s`

R2 full regression：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`755 passed in 9.92s`

R2 架构边界扫描：
- `rg -n "MortalityCommand|execute_phase\(" src\api\mortality_api.py src\api\session_api.py src\ui\gui`：无匹配。
- `rg -n "_active_events|_phase_results" src\api\mortality_api.py src\api\session_api.py src\core\service\mortality_service.py src\ui\gui src\ui\commands\phase_mortality.py`：无匹配。

R2 `git diff --check`：通过；仅 CRLF 提示，无空白错误。

## R3 生命周期修正

2026-07-02 SA-01 R3 复核指出：`GameState._phase_results` 在 `reset()` 和 `advance_year()` 中未随 `_executed_phases` 一起清理，可能导致下一年回到 `mortality` 后仍保留上一年天命结果，从而阻止新一年执行天命。

已完成修正：
- `GameState.reset()` 中新增 `_phase_results.clear()`。
- `GameState.advance_year()` 中新增 `_phase_results.clear()`。
- `record_phase_result()` 使用 `copy.deepcopy()` 保存结果，避免外部对象引用污染内部权威结果。
- `get_phase_result()` 使用 `copy.deepcopy()` 返回结果副本，避免调用方修改返回 dict 后污染内部状态。
- 未在 `advance_mortality_phase()` 成功后清理 mortality result，玩家进入 revenue 后仍可回看天命结果；清理仅发生在 reset / next year 级别。

R3 补充测试：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_mortality_api.py" -q
```

结果：`8 passed in 0.08s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_core\test_game_state.py" -q
```

结果：`28 passed in 0.18s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`23 passed in 1.91s`

R3 full regression：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`757 passed in 10.47s`

R3 架构边界扫描：
- `rg -n "_phase_results" src\api\mortality_api.py src\api\session_api.py src\core\service\mortality_service.py src\ui\gui src\ui\commands\phase_mortality.py`：无匹配。

R3 `git diff --check`：通过；仅 CRLF 提示，无空白错误。

## 风险与遗留问题

- `session_api.resolve_population_slice()` 仍存在既有 API -> UI processor 历史依赖，本任务未扩大处理。
- `GameState.mark_member_dead()` 内部仍有历史私有字段处理与 stdout 输出；本任务没有扩大死亡资产回收重构。
- `game_api.py` 仍作为历史 CLI/API 调试入口映射 `MortalityCommand`，本任务未修改；新增 GUI/API 路径不依赖它。
- 后续 GUI-P0-02C 可沿用本轮 `Service + API + Adapter + Store + Stage` 模式接入元老院阶段。

SA review request: 请 SA-01 对 GUI-P0-02B 天命与人口阶段 GUI 闭环进行最终技术复核。
