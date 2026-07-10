# GUI-P0-02A-R1 UI反馈修正 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件

R1 直接修改：
- `src/api/session_api.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_qml_startup.py`

仍属于 GUI-P0-02A 未提交工作区的既有文件：
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/i18n/qmldir`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/tests/test_gui/test_adapter.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01.md`

未触碰：
- `src/core/`
- `src/ui/commands/`
- `src/ui/processors/`
- `src/api/game_api.py`
- `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`，该文件仍为本任务前已有的无关未提交变更。

## 实现摘要

1. GUI 阶段导航顺序已按项目负责人反馈修正为：
   `天命 - 收入 - 广场 - 人口 - 元老院 - 战争 - 决算`

2. 对应 `phase_id` 顺序为：
   `mortality, revenue, forum, population, senate, combat, resolution`

3. `combat` 主显示名从 `战争/海战` 改为 `战争`；海战信息保留在 subtitle/description。

4. `resolution` 主显示名从 `革命/决算` 改为 `决算`；革命检查保留在 subtitle/description。

5. 顶部状态栏资金显示从裸金额 `(sessionStore.treasury || 0) + " T"` 改为：
   `GuiText.treasuryPrefix + (sessionStore.treasury || 0) + " T"`

6. `GuiText.qml` 新增集中字段：
   - `treasuryPrefix: "国库 "`
   - `factionTreasuryPrefix: "派系金库 "`

7. 未改变 CLI/Core 阶段推进规则。人口阶段仍是当前唯一真实可操作 GUI 切片，其余阶段仍为只读 placeholder。

## i18n 边界

R1 未新增散落硬编码资金标签。玩家可见的“国库”“派系金库”进入 `src/ui/gui/qml/i18n/GuiText.qml`。阶段主显示名仍由 `session_api.get_session_snapshot()` 的稳定 DTO 与 `name_key` 同步提供，后续 GUI-I18N-01 可将这些 `phase.*` key 接入完整语言包。

GUI-P0-01 人口切片旧硬编码文案未在本轮迁移，原因是 R1 范围限定为 UI 反馈修正，不扩大到人口阶段内部文案清理。

## 测试命令与结果

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

结果：`20 passed in 1.68s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_population_api.py" -q
```

结果：`29 passed in 0.25s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_population.py" -q
```

结果：`21 passed in 0.34s`

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

结果：`745 passed in 9.74s`

## 截图验证

已运行：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "gui_screenshot.py"
```

生成后复制到临时验收目录，并恢复仓库内既有截图文件，避免默认提交截图：
- `C:\Users\Kerl\AppData\Local\Temp\eor_gui_p0_02a_r1_screenshots\1440_main_shell_r1.png`
- `C:\Users\Kerl\AppData\Local\Temp\eor_gui_p0_02a_r1_screenshots\1280_main_shell_r1.png`

视觉确认：
- 左侧 7 阶段位置从上到下稳定显示，DTO/测试确认文字顺序为 `天命-收入-广场-人口-元老院-战争-决算`。
- 顶部资金区不再使用裸金额，QML 文案集中层和测试确认存在 `国库 ` 标签。
- offscreen 截图中中文仍显示为方块，这是 GUI-P0-01 已确认的无头 Qt 字体限制；不影响真实 Windows GUI 中文显示判断。

## git diff --check

结果：通过；仅有 Windows 工作区 CRLF 提示，无空白错误。

## 当前 git status --short

已知状态：
- 仍存在本任务前已有的无关 Excel 修改：`docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- GUI-P0-02A 主体未提交文件仍在工作区。
- R1 新增报告文件：本报告。
- 截图文件已恢复，不在工作区改动范围内。

## 风险与遗留问题

- 阶段顺序仅修正 GUI 主壳展示 DTO，不改变 CLI/Core 实际阶段推进规则，符合 R1 边界。
- 中文在 offscreen 截图中仍为方块，属于无头字体环境限制；真实窗口中文显示此前已由项目负责人确认正常。
- GUI-P0-02A 仍处于未提交工作区，等待 SA 最终验收与项目负责人授权归档。

SA review request: 请 SA-01 对 GUI-P0-02A-R1 UI反馈修正进行最终复核。
