# GUI-P0-02C-1-R1 元老院只读页 i18n 硬编码收束 开发验收报告 - CGT-01

Decision by CGT-01: READY_FOR_SA_REVIEW

## 修改文件

- `src/ui/gui/qml/stages/SenateStage.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/tests/test_gui/test_qml_startup.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1-R1 元老院只读页i18n硬编码收束 开发验收报告 - CGT-01.md`

## 修复摘要

- 将 `SenateStage.qml` 中元老院只读页细节文案组合迁移到 `GuiText.qml`。
- 新增 `GuiText.senateInfluenceDetail()`、`senateThreatDetail()`、`senatePeaceDetail()`、`senateContractDetail()`、`senateLeaderCount()`。
- `SenateStage.qml` 保持原字段读取和显示结构，仅改为调用 `GuiText` 函数。
- 补充 GUI 启动测试中的轻量扫描断言，防止指定中文标签再次散落回 `SenateStage.qml`。

## 已移出的硬编码文案

- `影响力`
- `威胁`
- `需要海战`
- `赔款`
- `年`
- `成本`
- `预期收益`
- `位`

上述文案已集中到 `src/ui/gui/qml/i18n/GuiText.qml`。

## 未修改范围确认

- 未修改 `senate_api.get_senate_view()` DTO 结构。
- 未修改 `session_api` 阶段导航语义。
- 未新增任何元老院政治动作 Slot 或按钮。
- 未实现提案、投票、否决、结算、阶段推进。
- 未调整页面布局、颜色、字号、阶段导航顺序或 UX 流程。
- 未修改 `src/core/`、`src/ui/commands/`、`src/ui/processors/`。
- 未触碰项目负责人既有版本规划 Excel 改动。

## 测试命令与结果

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONUNBUFFERED='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

结果：`26 passed in 2.41s`

补充扫描：

```powershell
rg -n "影响力|需要海战|赔款|成本|预期收益| 位| 年" src\ui\gui\qml\stages\SenateStage.qml
```

结果：无匹配。

## git diff --check 结果

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
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1 元老院只读状态与导航接入 技术开发任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1-R1 元老院只读页i18n硬编码收束 修复任务书 - CGT-01.md
?? docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02C-1-R1 元老院只读页i18n硬编码收束 开发验收报告 - CGT-01.md
?? src/ui/gui/qml/stages/SenateStage.qml
```

说明：上述状态包含 GUI-P0-02C-1 未提交工作区及项目负责人既有 Excel 改动。R1 本轮实际新增/修改限定在允许范围内。

## 风险与遗留问题

- R1 仅收束 `SenateStage.qml` 指定硬编码标签，不处理 C-1 以外的历史 GUI 文案。
- 真实 Windows GUI 视觉仍由项目负责人/SA 手工确认。

## SA review request

CGT-01 请求 SA-01 对 GUI-P0-02C-1-R1 元老院只读页 i18n 硬编码收束进行复核。
