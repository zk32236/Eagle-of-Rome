# GUI-P0-03A-R1 底部查询结果浮窗化修正 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件

- `src/ui/gui/qml/shell/BottomQueryBar.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/QueryResultOverlay.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/tests/test_gui/test_qml_startup.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A-R1 底部查询结果浮窗化修正 开发验收报告 - CGT-01.md`

说明：本轮未改查询业务接入范围；`session_store.py`、`api_adapter.py` 等仍为 GUI-P0-03A 工作区既有改动。

## 实现摘要

- 保留底部 12 个查询按钮。
- 移除 `ContextPanel.qml` 中常驻查询结果区。
- 新增 `QueryResultOverlay.qml`，点击底部查询按钮后以轻量浮窗展示查询结果。
- 浮窗展示标题、状态、message、items 明细列表和关闭按钮。
- `BottomQueryBar.qml` 改为发出 `queryRequested(queryId)`，由 `GameShell.qml` 调用 `sessionStore.doGlobalQuery()` 并打开 overlay。
- 右侧面板恢复为派系资源、选中/权威阶段、权限提示、事件日志/结构化反馈、流程控制。

## 边界确认

- 未新增元老院、广场、战争、收入、决算复杂业务动作。
- 未新增新的底部查询业务接入范围。
- 未调用 CLI Command、`game_api.execute_phase()`、`game_api.execute_turn()` 或 `CombatCommand`。
- 未绕过 Adapter/API 读取 Core 私有字段。
- 未提交 Git。

## i18n 集中化说明

- 新增浮窗文案 `关闭` 已集中到 `GuiText.closeQueryResult`。
- 浮窗标题、状态、空状态、底栏查询按钮文案继续从 `GuiText.qml` / Store DTO 获取。
- `QueryResultOverlay.qml` 未新增目标中文/英文 UI 文案硬编码。

## 测试结果

### test_gui

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

结果：`29 passed in 3.28s`

### test_adapter

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_adapter.py" -q
```

结果：`10 passed in 0.24s`

### git diff --check

结果：通过；仅有 LF 将被 Git 转为 CRLF 的工作区提示，无空白错误。

补充未跟踪新文件尾随空白扫描：

```powershell
rg -n "[ \t]+$" src\ui\gui\qml\shell\QueryResultOverlay.qml src\ui\gui\qml\shell\BottomQueryBar.qml
```

结果：无匹配。

### 边界扫描

```powershell
rg -n "game_api\.execute_phase|game_api\.execute_turn|CombatCommand|phase_senate|phase_forum|phase_revenue|phase_combat" src\ui\gui src\api\session_api.py
```

结果：无匹配。

### i18n 硬编码扫描

```powershell
rg -n "查询结果|关闭|已接入|只读|占位|点击底部|全局查询|游戏状态|派系信息|战争列表|军团状态" src\ui\gui\qml\shell\BottomQueryBar.qml src\ui\gui\qml\shell\ContextPanel.qml src\ui\gui\qml\shell\GameShell.qml src\ui\gui\qml\shell\QueryResultOverlay.qml
```

结果：无匹配。

### 右侧常驻查询区扫描

```powershell
rg -n "queryResultTitle|globalQueryResult\.items|queryResultEmpty" src\ui\gui\qml\shell\ContextPanel.qml
```

结果：无匹配。

## 当前 git status --short

```text
 M src/tests/test_gui/test_adapter.py
 M src/tests/test_gui/test_qml_startup.py
 M src/ui/gui/api_adapter.py
 M src/ui/gui/localization.py
 M src/ui/gui/qml/i18n/GuiText.qml
 M src/ui/gui/qml/shell/ContextPanel.qml
 M src/ui/gui/qml/shell/FeedbackPanel.qml
 M src/ui/gui/qml/shell/GameShell.qml
 M src/ui/gui/qml/shell/TopStatusBar.qml
 M src/ui/gui/session_store.py
?? docs/MVP 0.9 项目管理/01_需求与版本规划/~$EOR MVP 1.0 目标版本规划 V1.1.xlsx
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A OPC主壳骨架落地 开发验收报告 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A-R1 底部查询结果浮窗化修正 开发验收报告 - CGT-01.md
?? src/ui/gui/qml/shell/BottomQueryBar.qml
?? src/ui/gui/qml/shell/QueryResultOverlay.qml
```

说明：Excel 临时锁文件为项目负责人/Office 产生的无关未跟踪文件，本轮未处理。

## 已知风险

- 浮窗视觉尺寸和交互细节仍需项目负责人在真实 Windows GUI 中确认。
- 查询内容仍沿用 GUI-P0-03A 的只读/占位策略，本轮未扩展业务接入范围。

## SA review request

CGT-01 请求 SA-01 对 GUI-P0-03A-R1《底部查询结果浮窗化修正》进行技术复核。
