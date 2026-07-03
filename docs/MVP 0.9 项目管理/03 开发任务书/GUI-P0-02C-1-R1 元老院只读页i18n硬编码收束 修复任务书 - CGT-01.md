# GUI-P0-02C-1-R1 元老院只读页 i18n 硬编码收束 修复任务书 - CGT-01

创建日期：2026-07-04

发布对象：CGT-01

发布角色：SA-01 / 系统架构师

任务状态：正式派发

前置任务：GUI-P0-02C-1《元老院只读状态与导航接入》

当前状态：C-1 已获 SA `CONDITIONAL_PASS / READY_FOR_MANUAL_GUI_CHECK`，但存在一个需收束的 i18n 条件项。

项目根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

正式文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs`

Python 解释器：`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

---

## 一、任务编号

`GUI-P0-02C-1-R1`

## 二、任务名称

元老院只读页 i18n 硬编码收束

## 三、任务类型

缺陷修复 / GUI 文案规范收束 / C-1 条件项修复

## 四、任务目标

修复 SA 验收发现的 C-1 条件项：`SenateStage.qml` 中仍有少量新增中文细节标签硬编码，未完全符合“GUI 文案集中到 i18n 层”的规范。

本任务只处理这些文案集中问题，不改变元老院只读 DTO、Session 语义、Store 行为、页面布局和任何政治业务边界。

## 五、背景说明

GUI-P0-02C-1 已完成元老院只读状态与导航接入，核心架构边界正确：

- `senate_api.get_senate_view()` 返回只读 DTO。
- `session_api` 将 `senate` 标记为 `implemented=True`、`interaction_mode="readonly"`、`actionable=False`。
- GUI 新增 `SenateStage.qml`，未接入提案、投票、否决、结算或阶段推进。
- CGT-01 已报告 full `src/tests`: `762 passed`。

SA 复核发现仅有以下新增 QML 文案仍散落在 `SenateStage.qml` 内：

- `影响力`
- `威胁 / 需要海战`
- `赔款 / 年`
- `成本 / 预期收益`
- `位`

这些不阻塞功能，但会造成后续多语言迁移返工，因此需要在 C-1 Git 归档前收束。

## 六、依据文档

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02C-1 元老院只读状态与导航接入 技术开发任务书 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 七、允许修改范围

| 文件 | 允许内容 |
| --- | --- |
| `src/ui/gui/qml/stages/SenateStage.qml` | 移除新增散落中文标签，改为引用 `GuiText` 集中层。 |
| `src/ui/gui/qml/i18n/GuiText.qml` | 新增元老院细节标签、格式化函数或属性。 |
| `src/ui/gui/localization.py` | 如需要，可补充对应 key，保持 Python/QML 文案边界一致。 |
| `src/tests/test_gui/test_qml_startup.py` 或相关 GUI 测试 | 补一个轻量断言，确保新增文案集中在 `GuiText.qml`，并避免 `SenateStage.qml` 继续出现上述散落中文标签。 |
| 开发验收报告 | 更新 R1 执行摘要和测试结果。 |

## 八、禁止事项

本 R1 严格禁止：

1. 不得修改 `senate_api.get_senate_view()` 的 DTO 结构。
2. 不得修改 `session_api` 的阶段导航语义。
3. 不得新增或修改任何元老院政治动作 Slot。
4. 不得实现提案、投票、否决、结算、阶段推进。
5. 不得接入宣战、停战、预算、总督任命、战争接管。
6. 不得调整页面布局、颜色、字号、阶段导航顺序或 UX 流程。
7. 不得修改 `src/core/`、`src/ui/commands/`、`src/ui/processors/`。
8. 不得触碰项目负责人已有改动的版本规划 Excel。
9. 不得提交 Git。

## 九、实现要求

1. 将 `SenateStage.qml` 中以下文案移入 `GuiText.qml` 或等价集中层：
   - `影响力`
   - `威胁`
   - `需要海战`
   - `赔款`
   - `年`
   - `成本`
   - `预期收益`
   - `位`
2. `SenateStage.qml` 应通过 `GuiText` 属性或函数组合这些文本。
3. 保持显示结果与 C-1 当前界面一致，不改变数据字段读取逻辑。
4. 可在 `GuiText.qml` 中新增函数，例如：
   - `senateInfluenceDetail(factionName, influence)`
   - `senateThreatDetail(threatLevel, navalRequired)`
   - `senatePeaceDetail(indemnity, duration)`
   - `senateContractDetail(baseCost, expectedProfit)`
   - `senateLeaderCount(count)`
   具体命名由 CGT-01 自定，但需清晰。
5. 不要求提交 GUI 截图；真实 GUI 视觉由项目负责人/SA 人工验证。

## 十、测试要求

至少执行：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

并执行：

```powershell
git diff --check
```

如 CGT-01 顺手执行 full regression，可报告结果；但本 R1 不强制 full regression，除非实际修改超出允许范围。

## 十一、验收标准

- `SenateStage.qml` 不再包含上述新增散落中文标签。
- 新增元老院细节标签集中到 `GuiText.qml` 或等价 i18n 层。
- 元老院只读页面行为不变。
- 元老院仍无任何政治动作入口。
- `src/tests/test_gui` 通过。
- `git diff --check` 通过。
- 工作区仍不触碰版本规划 Excel。

## 十二、交付物

请 CGT-01 在完成后更新或新增 R1 开发验收报告，建议归档到：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02C-1-R1 元老院只读页i18n硬编码收束 开发验收报告 - CGT-01.md`

报告需包含：

```text
Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED / RETURNED

修改文件：
修复摘要：
已移出的硬编码文案：
未修改范围确认：
测试命令与结果：
git diff --check 结果：
风险与遗留问题：
```

完成后请回执 SA-01 复核。不得自行提交 Git。
