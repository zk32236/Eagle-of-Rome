# GUI-P0-01-FIX-01 QML启动阻塞修复 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## Code baseline

- Git HEAD: `6cc972e AS-P0-03 Close first-batch private field access`
- Starting state: `6cc972e` + KIMI-01 GUI-P0-01 未提交工作区
- CGT-01 未提交 Git

## Starting working tree

任务开始时 `git status --short` 显示 KIMI-01 GUI 交付为未跟踪文件：

```text
?? data/scenarios/gui_prototype.json
?? gui_delivery/
?? gui_main.py
?? gui_screenshot.py
?? requirements-gui.txt
?? src/api/session_api.py
?? src/tests/test_gui/
?? src/ui/gui/
```

## Root cause

QML 启动阻塞根因是相对导入路径错误，导致 `QQmlApplicationEngine.load(Main.qml)` 后 `rootObjects()` 为空：

- `shell/GameShell.qml` 直接使用 `PopulationStage`、`LockedStagePlaceholder`，但未导入 `../stages`。
- `stages/*.qml` 使用 `import "components"`，实际组件目录为 `qml/components`，相对 `stages` 应为 `../components`。
- `shell/*.qml` 使用 `AppButton`、`StatusTile` 等共享组件，但未导入 `../components`。

组件级诊断曾复现：

```text
Main.qml:14 Type GameShell unavailable
shell/GameShell.qml:57 PopulationStage is not a type
stages/PopulationStage.qml:5 "components": no such directory
```

## Changed files

- `gui_screenshot.py`
- `src/ui/gui/app.py`
- `src/ui/gui/qml/theme/Theme.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/shell/FeedbackPanel.qml`
- `src/ui/gui/qml/shell/PlayerHandoffOverlay.qml`
- `src/ui/gui/qml/stages/PopulationStage.qml`
- `src/ui/gui/qml/stages/FestivalView.qml`
- `src/ui/gui/qml/stages/VoteView.qml`
- `src/ui/gui/qml/stages/ElectionResultView.qml`
- `src/tests/test_gui/test_qml_startup.py`
- `gui_delivery/screenshots/1440_population_default.png`
- `gui_delivery/screenshots/1280_population_default.png`

## Implementation summary

- 修正 QML 相对导入链：
  - `GameShell.qml` 增加 `import "../stages"` 和 `import "../components"`。
  - `shell` 下使用共享组件的文件增加 `import "../components"`。
  - `stages` 下文件统一改为 `import "../components"`。
- 给关键 QML 区域补充 `objectName`，便于启动测试定位：
  - `gameShellRoot`
  - `phaseRail`
  - `populationStage`
  - `feedbackPanel`
  - `playerHandoffOverlay`
- 修正主题字体 token 为 QML 单字体名：
  - `Microsoft YaHei UI`
  - `SimSun`
- 修正截图脚本：
  - 设置 `theme` context property。
  - 使用 `QUrl.fromLocalFile()` 加载 `Main.qml`。
  - 使用屏幕窗口句柄抓图，输出 1440/1280 默认人口阶段截图。

## QML diagnostics added

`src/ui/gui/app.py` 已补充启动诊断：

- Python 解释器路径。
- PySide6 版本。
- Qt 版本。
- QML import paths。
- `Main.qml` 绝对路径。
- `QQmlApplicationEngine.warnings` 信号日志。
- `Theme.qml` 创建结果。
- `Main.qml`、`GameShell.qml`、`PopulationStage.qml`、`FeedbackPanel.qml` 组件级加载状态。
- root object 数量。
- root object className。
- GameShell 查找结果。
- 当前 viewer/player 初始化结果。

## Startup result

- `src/tests/test_gui/test_qml_startup.py` 验证 `Main.qml` 可加载。
- `rootObjects()` 非空。
- 根对象为 `QWindow`。
- 可定位：
  - `gameShell`
  - `phaseRail`
  - `populationStage`
  - `feedbackPanel`
  - `playerHandoffOverlay`

## Screenshots

已生成：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_delivery\screenshots\1440_population_default.png`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_delivery\screenshots\1280_population_default.png`

截图非空，GameShell、七阶段导航、人口阶段容器、反馈区和右侧上下文区均渲染。当前 offscreen 截图环境中文字体仍显示为方块；已设置默认字体和主题字体，但 Qt offscreen 环境未能取得中文字体。建议 SA/项目负责人在真实 Windows GUI 窗口下复验字体显示。

## Test commands

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui' -q
```

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_population_api.py' -q
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population.py' -q
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population_disband.py' -q
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population_truce.py' -q
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_ui\test_command_framework.py' -q
```

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' -m pytest -p no:cacheprovider 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests' -q
```

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe' 'C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_screenshot.py'
```

```powershell
git diff --check
git status --short
```

## Test results

- `src/tests/test_gui`: `13 passed in 1.31s`
- `test_population_api.py`: `29 passed in 0.16s`
- `test_phase_population.py`: `21 passed in 0.21s`
- `test_phase_population_disband.py`: `7 passed in 0.18s`
- `test_phase_population_truce.py`: `4 passed in 0.13s`
- `test_command_framework.py`: `14 passed in 0.27s`
- 全量 `src/tests`: `734 passed in 8.44s`
- `gui_screenshot.py`: 成功输出 2 张默认人口阶段截图

## Static checks

- `git diff --check`: passed，无输出。
- 禁止调用扫描：
  - 未发现 GUI 调用 `game_api.execute_phase()` / `execute_turn()`。
  - 未发现 GUI 实例化或调用 `PopulationCommand`。
  - 未发现 `testing.bypass_player_check`。
  - 未发现运行时 `http://` / `https://` / CDN 资产依赖。
- 已清理 `src` 下 `__pycache__` 与项目 `.pytest_cache`。

## Architecture compliance

- 保持 `QML -> GuiSessionStore / Controller -> GuiApiAdapter -> session_api / population_api -> GameState`。
- 未改 `src/core/`、`src/ui/commands/`、`src/ui/processors/`。
- 未绕过 `population_api.campaign()`、`population_api.vote()`、`population_api.resolve_election()`。
- QML 不直接持有 `GameState`、Faction、Figure 或 System 实例。
- 本次修复只处理 QML 启动链、诊断、启动测试与截图脚本。

## Known risks

- offscreen 截图环境中文字体显示为方块；主窗口结构非空且布局可见。建议 SA 在真实 Windows GUI 窗口复验字体渲染。
- KIMI-01 原交付仍是整批未提交新文件，`git diff --check` 对未跟踪文件不做逐文件 whitespace 校验；本次按任务书要求执行了命令并记录结果。

## Items deferred

- 未补齐 KIMI-01 原任务书要求的 10 张完整流程截图；本修复任务最低要求的 1440/1280 默认人口阶段截图已生成。
- 未处理完整七阶段 GUI 迁移。
- 未引入字体资产或打包字体方案。

## Git status

最终 `git status --short`：

```text
?? data/scenarios/gui_prototype.json
?? gui_delivery/
?? gui_main.py
?? gui_screenshot.py
?? requirements-gui.txt
?? src/api/session_api.py
?? src/tests/test_gui/
?? src/ui/gui/
```

CGT-01 未提交 Git。请 SA-01 进行最终架构验收。
