# GUI-P0-01-FIX-01 QML启动阻塞修复任务书 - CGT-01

发布日期：2026-06-28

发布角色：系统架构师 SA-01

执行对象：CGT-01

任务类型：缺陷修复 / GUI 启动调试 / 测试补齐

优先级：P0.5 阻塞修复

目标版本：GUI-P0-01 MVP0.7 可玩 GUI 原型

## 一、背景说明

KIMI-01 已按 GUI-P0-01 技术任务书完成初步 GUI 编程交付，并将代码落入活动代码目录：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

当前代码状态不是干净 Git HEAD，而是：

```text
Git HEAD: 6cc972e AS-P0-03 Close first-batch private field access
+ KIMI-01 GUI-P0-01 未提交交付文件
```

KIMI-01 报告称 Python 后端骨架、Session API、Adapter、Store、QML 组件、人口阶段垂直切片和测试骨架已完成，但 GUI 启动被阻塞：

```text
QQmlApplicationEngine.load(Main.qml) 后 rootObjects() 为空
窗口无法显示
```

SA 初步审查判断：该问题更像 QML 加载链、相对导入路径、组件类型解析或启动诊断不足，不应推倒重写 GUI 骨架。请 CGT-01 在 KIMI-01 已完成代码基础上进行最小范围接力修复。

## 二、任务目标

修复 GUI-P0-01 当前 QML 启动阻塞，使以下命令能够正常启动 PySide6/QML 主窗口：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_main.py"
```

最低目标：

1. `Main.qml` 可被 QML 引擎成功加载。
2. `rootObjects()` 非空。
3. 主窗口非空显示。
4. `GameShell`、七阶段导航、人口阶段容器、反馈区、玩家交接遮罩可以被创建。
5. 人口阶段“庆典 + 投票 + 玩家交接 + 选举结果”仍通过真实 API 和权威状态运行，不退化为假数据演示。
6. 增加或修复 GUI 启动测试，避免再次出现 `rootObjects() == 0` 但测试未捕获的问题。

## 三、依据文档

请优先阅读：

- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 MVP0.7可玩GUI原型 技术开发任务书 - KIMI-01.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 EOR_GUI_Prototype_Scheme_A_开发验收报告 - KIMI-01.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 界面风格确认记录.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

重点代码：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_main.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_screenshot.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\requirements-gui.txt`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\api\session_api.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\app.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\session_store.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\api_adapter.py`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\ui\gui\qml\`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\`

## 四、允许修改范围

允许修改：

```text
gui_main.py
gui_screenshot.py
requirements-gui.txt
src/api/session_api.py
src/ui/gui/
src/tests/test_gui/
data/scenarios/gui_prototype.json
```

允许新增：

```text
src/tests/test_gui/test_qml_startup.py
src/ui/gui/qml/qmldir
src/ui/gui/qml/*/qmldir
src/ui/gui/qml/diagnostics 或等价诊断辅助文件
```

仅当证明必要时，才允许修改：

```text
src/api/population_api.py
src/api/player_api.py
src/api/__init__.py
```

如需修改以下区域，必须停止并在回执中说明原因，不得擅自修改：

```text
src/core/
src/ui/commands/
src/ui/processors/
现有 CLI 入口
现有 AutoPlayerProcessor / decider
```

## 五、禁止事项

- 不得推倒重写 KIMI-01 的 GUI 骨架。
- 不得把 GUI 改成 HTML、WebView、Electron、Tauri、FastAPI 或其他技术栈。
- 不得绕过 `population_api.campaign()`、`population_api.vote()`、`population_api.resolve_election()` 执行玩家操作。
- 不得调用 `game_api.execute_phase()` / `execute_turn()` 驱动 GUI。
- 不得实例化或调用 `PopulationCommand` 完成 GUI 操作。
- 不得在 QML 中复制核心业务规则。
- 不得让 QML 直接持有 `GameState`、Faction、Figure 或 System 实例。
- 不得直接修改 Core/System/Service/Entity 私有字段。
- 不得通过 `testing.bypass_player_check` 作为 GUI 正常权限绕过。
- 不得泄漏其他玩家派系金库或非公开人物详情。
- 不得引入 P1 新玩法。
- 不得修改 `E:\Eagle of Rome` 下历史档案作为代码交付。
- 不得自行提交 Git。
- 不得做无关格式化、大范围重命名或跨模块重构。
- 不得优先用降级 PySide6 解决问题；除非已证明代码路径无误且存在明确版本兼容证据，否则保持 `PySide6==6.8.3`。

## 六、实现要求

### 6.1 必须先补足 QML 错误诊断

请在 `src/ui/gui/app.py` 或等价位置增加可靠诊断，使启动失败时能输出真实 QML 错误。

建议至少做到：

1. 连接 `QQmlApplicationEngine.warnings` 信号或等价机制，记录 `QQmlError.toString()`。
2. 使用 `QQmlComponent` 对 `Main.qml` 做可选诊断加载，失败时输出 `errorString()`。
3. 对 Theme、Main、GameShell 关键组件分别记录加载路径和结果。
4. 启动失败时错误信息必须写入日志，而不是只写 `rootObjects() is empty`。

### 6.2 优先检查并修复 QML 相对导入路径

SA 初步发现以下高概率问题：

1. `Main.qml` 只 `import "shell"`。
2. `GameShell.qml` 位于 `qml/shell/`，但直接使用 `PopulationStage`、`LockedStagePlaceholder`。
3. `PopulationStage.qml`、`FestivalView.qml`、`VoteView.qml`、`ElectionResultView.qml` 位于 `qml/stages/`，但使用 `import "components"`，实际组件目录为 `qml/components/`。

请重点检查是否需要改为：

```qml
// shell/GameShell.qml
import "../stages"

// stages/*.qml
import "../components"
```

或通过 `qmldir` 和规范模块导入方式统一解决。

要求：选择一种清晰、可维护、后续 P1 GUI 可复用的方式，不要靠复制 QML 文件到多个目录来规避路径问题。

### 6.3 保持主题与组件边界

当前 `Theme.qml` 已被 Python 创建后作为 context property `theme` 暴露。允许保留该方式，也允许改回 QML singleton，但必须满足：

1. 所有 QML 文件都能稳定访问主题令牌。
2. 不再出现因为 theme 导入导致 `Main.qml` 创建失败。
3. 不引入运行时网络字体或图片依赖。

### 6.4 保持真实 API 闭环

修复启动问题时，不得把真实 API 操作替换为 QML 假状态。

必须保留：

```text
QML -> GuiSessionStore / Controller -> GuiApiAdapter -> session_api / population_api -> GameState
```

成功操作后仍需从权威状态刷新；失败操作不得污染状态。

### 6.5 清理生成物

不得提交或保留不必要运行产物：

```text
__pycache__/
.pytest_cache/
临时截图缓存
Qt 临时缓存
```

如果 KIMI-01 交付中已有 `__pycache__`，请从工作区清理，但不得删除源代码或交付报告。

## 七、调试日志要求

GUI 启动与 QML 诊断日志至少包含：

- Python 解释器路径。
- PySide6 版本。
- Qt import paths。
- `Main.qml` 绝对路径。
- QML warnings/errors。
- root object 数量。
- GameShell 查找结果。
- 当前 viewer/player 初始化结果。

日志不得记录其他玩家隐藏金库或非公开人物详情。

## 八、测试要求

### 8.1 GUI 启动测试

新增或修复 `src/tests/test_gui/test_qml_startup.py`，至少覆盖：

1. `Main.qml` 加载成功。
2. `rootObjects()` 非空。
3. 根对象是窗口或等价 QML root。
4. 可找到 `gameShell`。
5. 阶段导航、人口阶段、反馈区至少能被创建或通过 objectName 定位。

无头测试环境：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

### 8.2 KIMI-01 原 GUI 测试回归

执行：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

### 8.3 人口阶段与 CLI 回归

至少执行：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_population_api.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population_disband.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_population_truce.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_ui\test_command_framework.py" -q
```

### 8.4 全量回归

执行：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

### 8.5 静态检查

执行：

```powershell
git diff --check
git status --short
```

并静态确认：

- GUI 不导入 CLI Command。
- GUI 不调用 `game_api.execute_phase()` / `execute_turn()`。
- QML 不直接引用 Core 私有字段。
- 没有运行时 CDN、HTTP 字体或图片依赖。

### 8.6 截图验证

若本地 GUI 可启动，请生成或更新至少以下截图：

```text
gui_delivery/screenshots/1440_population_default.png
gui_delivery/screenshots/1280_population_default.png
```

如时间允许，补充 KIMI-01 原任务书要求的 10 张截图。若截图脚本仍有问题，但主程序可手动启动，请在回执中明确区分“启动已修复”和“截图自动化待补”。

## 九、验收标准

| 类别 | 验收标准 |
| --- | --- |
| 启动 | `gui_main.py` 可启动，`rootObjects()` 非空，主窗口可显示 |
| 诊断 | QML 加载失败时能输出真实 QML error/warning |
| 架构 | 仍保持 `GUI -> API -> Core/System/Service -> Entity` |
| 数据 | 庆典、投票、完成玩家、选举结果仍通过真实 API 和权威状态刷新 |
| 权限 | 当前玩家权限与多玩家信息隔离不退化 |
| 测试 | `test_gui`、人口相关回归、全量 pytest 通过，或失败项明确为非本任务原因 |
| 视觉 | 主窗口非空；至少默认人口阶段截图无明显空白、重叠或控件不可达 |
| Git | CGT-01 不提交 Git，只提交验收报告 |

SA 将在以下情况建议 `RETURN_FOR_REWORK`：

- 仍然 `rootObjects() == 0`。
- 只能通过删除主要 QML 组件或改成假数据页面启动。
- GUI 绕过 API 或复制业务规则。
- 启动测试不能捕获 QML 加载失败。
- 多玩家信息隔离被破坏。

## 十、交付物

请 CGT-01 完成后提交开发验收报告，归档到：

`E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01-FIX-01 QML启动阻塞修复 开发验收报告 - CGT-01.md`

报告必须包含：

```text
Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED

Code baseline:

Starting working tree:

Root cause:

Changed files:

Implementation summary:

QML diagnostics added:

Startup result:

Screenshots:

Test commands:

Test results:

Static checks:

Architecture compliance:

Known risks:

Items deferred:

Git status:
```

CGT-01 不得自行提交 Git。SA 将在代码审查、GUI 验证、pytest 复跑和项目负责人手工测试通过后，再按授权归档提交。
