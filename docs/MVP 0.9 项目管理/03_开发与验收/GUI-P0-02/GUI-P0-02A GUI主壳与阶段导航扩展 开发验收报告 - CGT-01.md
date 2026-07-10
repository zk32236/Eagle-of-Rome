# GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## Baseline

- Project root: `C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- Git HEAD: `bbd5240 Add GUI-P0-02A PM intent package`
- Python: `C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`
- 注意：任务开始前已存在非本任务修改 `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`，CGT-01 未读取、未修改、未暂存该文件。

## Changed Files

生产代码：

- `src/api/session_api.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/i18n/qmldir`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`

测试：

- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`

文档：

- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01.md`

## Implementation Summary

主壳与阶段导航：

- `session_api.get_session_snapshot()` 现在返回 GUI-P0 Sprint 口径的完整 7 阶段序列：
  - 天命、人口、元老院、收入、广场、战争/海战、革命/决算。
- 每个阶段 DTO 包含 `id/index/name/subtitle/description/status/implemented/enabled/actionable/handoff_task/disabled_reason`。
- 未实现阶段仅为可点击查看的只读占位，不执行任何 Core 阶段业务。
- `GuiSessionStore` 增加 `selectedPhaseId`、`selectedPhaseName`、`selectedPhaseSummary`、`globalWarnings`、`selectPhase()`、`refreshSnapshot()`。
- `GameShell` 根据 `selectedPhaseId` 在 `PopulationStage` 和 `LockedStagePlaceholder` 间切换。

状态区与上下文：

- 顶部状态栏显示回合、年份、当前 GUI 选择阶段、当前玩家、viewer 派系、国库与 viewer 派系金库摘要。
- 右侧上下文显示 viewer 派系资源、当前阶段说明、实现/占位状态、权限提示和 global warnings。
- 阶段导航点击未实现阶段时，Store 发出 warning feedback，并保持只读占位。
- 切回 `population` 后仍加载 GUI-P0-01 人口真实切片。

反馈区：

- 保留原 `FeedbackPanel` 结构。
- 新增 Store 层统一反馈构造，用于阶段选择、未实现阶段、刷新状态。
- 未实现阶段点击不静默失败，反馈类型为 `warning`。

## Session/API/Store/Adapter Changes

- `session_api.py` 仅补强 GUI shell 只读 DTO，没有新增 API -> UI 命令依赖。
- 未修改 `game_api.py`、`src/core/`、`src/ui/commands/`、`src/ui/processors/`。
- `GuiApiAdapter` 未改动；现有快照与人口视图调用保持兼容。
- `GuiSessionStore` 只维护 GUI selected phase 和 DTO 缓存，不维护第二套权威游戏状态。

## i18n Boundary

本轮按 SA 修订要求建立轻量多语言预留边界，但不实现运行时语言切换。

文案集中层：

- Python Store 反馈文案：`src/ui/gui/localization.py`
- QML 主壳文案：`src/ui/gui/qml/i18n/GuiText.qml`
- QML i18n module: `src/ui/gui/qml/i18n/qmldir`

Key 策略：

- Session DTO 新增稳定 key：
  - `name_key`
  - `subtitle_key`
  - `description_key`
  - `status_key`
  - `disabled_reason_key`
- 示例：
  - `phase.population.name`
  - `phase.senate.description`
  - `phase.status.placeholder`
  - `phase.disabled.placeholder`
  - `warning.gui_p0_02a.shell_only`

未覆盖旧硬编码：

- GUI-P0-01 人口阶段旧 QML 文案仍有较多硬编码，本任务未全量迁移，原因是任务书明确只要求本轮新增/大幅改动主壳、导航、占位、反馈和权限提示文案进入集中层。
- `ContextPanel` 里既有资源卡片标签如“派系金库 / 总影响力 / 派系人物”属于 GUI-P0-01 旧壳层文案，未在本轮完整迁移；建议由后续 `GUI-I18N-01` 统一清理。

GUI-I18N-01 建议：

- 将 `GuiText.qml` 扩展为可切换语言资源。
- 将 GUI-P0-01 人口切片、组件库、反馈区、按钮、表格列名迁移到统一 key。
- 增加 `en-US` catalog 与语言切换入口。
- 补充英文布局截图，检查长文本溢出。

## Tests Executed

GUI tests:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

Result:

```text
19 passed in 1.56s
```

Population API regression:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_population_api.py" -q
```

Result:

```text
29 passed in 0.20s
```

Population command regression:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_population.py" -q
```

Result:

```text
21 passed in 0.34s
```

Full regression:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

Result:

```text
744 passed in 9.83s
```

## Screenshot Result

Command:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "gui_screenshot.py"
```

Script output:

```text
Screenshot saved: C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_delivery\screenshots\1440_population_default.png
Screenshot saved: C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_delivery\screenshots\1280_population_default.png
```

Because these screenshot files are tracked and task guidance says screenshots should not be submitted by default, CGT-01 copied the generated GUI-P0-02A screenshots to:

- `C:\Users\Kerl\AppData\Local\Temp\eor_gui_p0_02a_screenshots\1440_main_shell.png`
- `C:\Users\Kerl\AppData\Local\Temp\eor_gui_p0_02a_screenshots\1280_main_shell.png`

Then CGT-01 restored the tracked screenshot files to avoid including screenshot changes in the working tree. Visual check confirmed the main shell renders nonblank with full left phase navigation, top status, right context, bottom feedback, and population stage container. Offscreen screenshots still show Chinese glyph boxes due headless Qt font limitations already known from GUI-P0-01; real Windows GUI had previously displayed Chinese correctly.

## Static Checks

`git diff --check`:

```text
warning: in the working copy of 'src/api/session_api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/tests/test_gui/test_adapter.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/tests/test_gui/test_qml_startup.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/tests/test_gui/test_session_api.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/qml/shell/ContextPanel.qml', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/qml/shell/GameShell.qml', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/qml/shell/PhaseRail.qml', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/qml/shell/TopStatusBar.qml', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/qml/stages/LockedStagePlaceholder.qml', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'src/ui/gui/session_store.py', LF will be replaced by CRLF the next time Git touches it
```

No whitespace errors were reported; only CRLF warnings.

Forbidden dependency scan:

```text
src/api/session_api.py:250: from src.ui.processors.auto_player_processor import AutoPlayerProcessor
```

This is the existing excluded historical debt in `resolve_population_slice()` documented by SA, not newly introduced by GUI-P0-02A. No new `game_api.execute_phase()` / `execute_turn()` / CLI Command dependency was added to GUI code.

## Current git status --short

```text
 M docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx
 M src/api/session_api.py
 M src/tests/test_gui/test_adapter.py
 M src/tests/test_gui/test_qml_startup.py
 M src/tests/test_gui/test_session_api.py
 M src/ui/gui/qml/shell/ContextPanel.qml
 M src/ui/gui/qml/shell/GameShell.qml
 M src/ui/gui/qml/shell/PhaseRail.qml
 M src/ui/gui/qml/shell/TopStatusBar.qml
 M src/ui/gui/qml/stages/LockedStagePlaceholder.qml
 M src/ui/gui/session_store.py
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 技术边界审查报告 - SA-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01.md
?? src/ui/gui/localization.py
?? src/ui/gui/qml/i18n/
```

The XLSX modification is pre-existing and not part of this task.

## Risks and Remaining Issues

- GUI-P0-02A still uses a fixed GUI prototype session that enters population phase directly. This matches task scope; full year-flow orchestration belongs to GUI-P0-02B-F.
- Existing `session_api.resolve_population_slice()` API -> UI processor import remains as documented historical debt and was not touched.
- Offscreen screenshots retain font glyph-box limitation; real Windows GUI should be used for final visual font validation.
- QML `PhaseRail` delegates use objectName expressions, but Qt object discovery for repeated delegate items is not the primary test mechanism; Store/QML startup tests validate phase count and shell objects.

## GUI-P0-02B Handoff Suggestions

- Reuse `phase_navigation` DTO and `selectedPhaseId` shell mechanism.
- Implement天命 + 人口闭环 inside the existing `PopulationStage`/stage container without changing navigation contract.
- Keep phase operation buttons disabled unless backed by real API.
- Start `GUI-I18N-01` soon after main shell stabilizes, before broad GUI-P0-02C-F text surfaces multiply.
