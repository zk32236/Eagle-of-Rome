# GUI-P0-03A OPC主壳骨架落地 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 代码基线

- Git HEAD: `5488f16 Confirm OPC-01 GUI direction for GUI-P0-03A`
- 项目根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- 未提交 Git。

## 修改文件

- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/shell/FeedbackPanel.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/ui/gui/qml/shell/BottomQueryBar.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/session_store.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/localization.py`
- `src/tests/test_gui/test_qml_startup.py`
- `src/tests/test_gui/test_adapter.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A OPC主壳骨架落地 开发验收报告 - CGT-01.md`

## 实现摘要

- 将 GUI 主壳调整为 OPC 五区结构：顶栏、左导航、中栏公告+阶段容器、右侧状态/日志、底栏查询栏。
- 保留并嵌入既有天命、人口、元老院只读页面，未实现阶段继续显示 placeholder。
- 新增 `BottomQueryBar.qml`，提供 12 个全局查询按钮骨架。
- 右侧 `ContextPanel` 增加查询结果区，并将结构化反馈日志嵌入右侧面板。
- `GuiSessionStore` 增加 `globalQueryResult` 与 `doGlobalQuery(query_id)`，只处理安全只读或占位查询。
- `GuiApiAdapter` 增加 `get_game_status_summary()` 只读包装。
- 新增 GUI 测试覆盖五区对象、底栏 12 查询入口、Store 查询行为、边界扫描与 i18n 扫描。

## 五区布局完成情况

- 顶栏：保留年份、阶段、当前玩家、国库、派系金库摘要。
- 左导航：保留七阶段导航，顺序仍为 `mortality, revenue, forum, population, senate, combat, resolution`。
- 中栏：新增 `stageAnnouncement` 公告区，下方为 `stageContainer` 阶段容器。
- 右面板：显示派系资源、选中阶段、权限提示、查询结果、结构化反馈日志、流程控制按钮。
- 底栏：新增 `bottomQueryBar`，包含 12 个全局查询入口。

## 底部 12 查询按钮完成情况

- 游戏状态：已接入。通过 `GuiSessionStore -> GuiApiAdapter -> game_api.get_status_summary()` 读取安全摘要。
- 派系信息：只读。通过现有 session snapshot 的 viewer 派系资源展示，避免暴露其他玩家私有资金。
- 战争列表：只读。复用元老院只读 DTO 中的公开战争/威胁摘要，不读取 WarSystem 私有字段。
- 军团状态：占位。无本轮授权安全 API，显示 `GUI-P0-03B` 承接。
- 人物查询、派系金库、公地信息、私地信息、合同状态、行省信息、舰队状态、帮助：占位。显示 `GUI-P0-03G` 承接。

## i18n 集中化说明

- 新增/触碰的主壳、公告区、右面板、底栏查询、反馈日志文案集中到 `GuiText.qml` 或 `localization.py`。
- `BottomQueryBar.qml`、`GameShell.qml`、`TopStatusBar.qml`、`ContextPanel.qml`、`FeedbackPanel.qml` 未新增目标 UI 文案散落硬编码。
- 保留既有历史 QML 文案不在本轮大范围迁移。

## API/Adapter 边界说明

- GUI 查询路径保持 `QML -> GuiSessionStore -> GuiApiAdapter -> API`。
- 本轮只新增只读 `get_game_status_summary()` wrapper。
- 未新增复杂写操作 wrapper。
- 底栏占位项不绕过 API 读取 Core/System/Entity 私有状态。

## 未接入内容说明

- 未接入元老院提案、投票、否决、结算、战争接管、停战、预算、总督任命。
- 未接入广场退休、招募、合同投标、土地交易、凯旋投票、广场结算。
- 未接入战争/海战执行逻辑。
- 未接入收入结算或决算推进逻辑。
- 未调用 CLI Command、`game_api.execute_phase()`、`game_api.execute_turn()` 或 `CombatCommand`。

## 测试结果

### test_gui

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

结果：`29 passed in 2.81s`

### test_session_api / test_adapter

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_session_api.py" -q
```

结果：`12 passed in 0.21s`

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_adapter.py" -q
```

结果：`10 passed in 0.27s`

### full src/tests

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

结果：`766 passed in 11.19s`

### git diff --check

结果：通过；仅有 LF 将被 Git 转为 CRLF 的工作区提示，无空白错误。

补充：`src/ui/gui/qml/shell/BottomQueryBar.qml` 为未跟踪新文件，另行执行尾随空白扫描：

```powershell
rg -n "[ \t]+$" src\ui\gui\qml\shell\BottomQueryBar.qml
```

结果：无匹配。

### 边界扫描

```powershell
rg -n "game_api\.execute_phase|game_api\.execute_turn|CombatCommand|phase_senate|phase_forum|phase_revenue|phase_combat" src\ui\gui src\api\session_api.py
```

结果：无匹配。

### i18n 硬编码扫描

```powershell
rg -n "全局查询|游戏状态|派系信息|战争列表|军团状态|查询结果|结构化反馈|阶段公告" src\ui\gui\qml\shell\BottomQueryBar.qml src\ui\gui\qml\shell\GameShell.qml src\ui\gui\qml\shell\TopStatusBar.qml src\ui\gui\qml\shell\ContextPanel.qml src\ui\gui\qml\shell\FeedbackPanel.qml
```

结果：无匹配。新增主壳/底栏/右面板 UI 文案集中在 `GuiText.qml` / `localization.py`。

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
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-03A OPC主壳骨架落地 开发验收报告 - CGT-01.md
?? src/ui/gui/qml/shell/BottomQueryBar.qml
```

## 已知风险

- 底栏多数查询入口为占位，后续 GUI-P0-03B/G 需要按安全 API 逐步接入。
- 战争列表当前复用元老院只读摘要，不等同完整战争 GUI 查询。
- QML offscreen 测试验证对象结构与启动，不替代真实 Windows GUI 视觉验收。

## 需要 SA/项目负责人确认的问题

- 请在真实 GUI 中确认 OPC 五区布局尺寸、底栏按钮密度、右侧日志可读性是否符合项目负责人视觉预期。
- 请确认底栏第一轮“已接入 / 只读 / 占位”混合策略是否满足 GUI-P0-03A 归档条件。

## SA review request

CGT-01 请求 SA-01 对 GUI-P0-03A《OPC主壳骨架落地》进行技术验收。
