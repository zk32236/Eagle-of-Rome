# GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件清单

- `src/api/senate_api.py`
- `src/api/session_api.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/stages/SenateStage.qml`
- `src/tests/test_api/test_senate_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`
- `src/tests/test_gui/test_session_api.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01.md`

未纳入本任务修改：`docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx` 为任务开始前既有未提交变更，本轮未处理。

## 实现摘要

- 新增 `senate_api.get_senate_view(state, viewer_player_id)`，返回 GUI 元老院只读 DTO。
- DTO 明确标记 `interaction_mode: "readonly"`、`actionable: False`，并关闭 `can_create_proposal`、`can_vote`、`can_resolve`。
- 只读数据复用 `PoliticalSystem.build_initial_info()` 汇总派系领袖、主持官、对外战争、战争威胁、停战草案、总督空缺和待处理合同。
- `session_api` 阶段导航新增 `interaction_mode`，将 `senate` 标记为 `implemented=True` 但 `readonly/non-actionable`。
- `GuiApiAdapter` 与 `GuiSessionStore` 增加 Senate 只读刷新路径和只读属性暴露。
- 新增 `SenateStage.qml`，接入 `GameShell.qml`，仅展示公开状态和后续承接提示，不提供政治行动按钮。
- 新增/补充 GUI 文案集中层 key，保持 GUI-P0-02A 建立的 i18n 预留边界。

## 架构边界确认

- 未实现提案创建、投票、否决、结算或阶段推进。
- 未接入宣战、停战、预算、总督任命、战争接管等动作。
- GUI 路径保持 `GUI -> API -> Core/System/Service -> Entity`。
- 扫描 `src/ui/gui` 与 `src/api/session_api.py` 未发现调用 `phase_senate.py`、CLI command、`game_api.execute_phase()`、`execute_turn()`。
- 未新增 `doPropose`、`doVoteSenate`、`doResolveSenate` 等行动槽。

## 测试命令与结果

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_senate_api.py" -q
```

结果：`16 passed in 0.21s`

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`25 passed in 2.49s`

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_systems\test_political_system.py" -q
```

结果：`6 passed in 0.07s`

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_senate.py" -q
```

结果：`35 passed in 0.38s`

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`762 passed in 10.15s`

## git diff --check

结果：通过；仅有工作区 LF 将被 Git 转为 CRLF 的提示，无空白错误。

## 当前 git status --short

```text
 M docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx
 M src/api/senate_api.py
 M src/api/session_api.py
 M src/tests/test_api/test_senate_api.py
 M src/tests/test_gui/test_adapter.py
 M src/tests/test_gui/test_qml_startup.py
 M src/tests/test_gui/test_session_api.py
 M src/ui/gui/api_adapter.py
 M src/ui/gui/localization.py
 M src/ui/gui/qml/i18n/GuiText.qml
 M src/ui/gui/qml/shell/GameShell.qml
 M src/ui/gui/session_store.py
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1 元老院只读状态与导航接入 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01.md
?? src/ui/gui/qml/stages/SenateStage.qml
```

说明：Excel 与技术开发任务书为本任务开始前已存在的工作区状态/任务输入；本轮代码交付未修改 Excel。

## 风险与遗留问题

- `SenateStage.qml` 当前只读展示公开状态；提案、投票、否决、结算、阶段推进需由 GUI-P0-02C 后续任务接入。
- GUI 人工视觉仍需在真实 Windows 窗口确认页面布局、中文显示和滚动区域可读性。
- 本轮未迁移或实现任何元老院业务动作，避免提前扩大 GUI-P0-02C-1 边界。

## SA review request

CGT-01 请求 SA-01 对 GUI-P0-02C-1 元老院只读状态与导航接入进行最终技术验收。
