# GUI-P0-02C-1 元老院只读状态与导航接入 技术开发任务书 - CGT-01

创建日期：2026-07-03

发布对象：CGT-01

发布角色：SA-01 / 系统架构师

任务状态：正式派发

当前代码基线：Git HEAD `df16200 Add GUI-P0-02C PM intent package`

项目根目录：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

正式文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs`

Python 解释器：`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

---

## 一、任务编号

`GUI-P0-02C-1`

## 二、任务名称

元老院阶段只读状态与导航接入

## 三、任务类型

GUI 阶段闭环子任务 / 只读视图接入 / 架构安全铺垫

## 四、优先级

P0.5 / GUI-P0 Sprint 子任务

## 五、背景说明

GUI-P0-02C 是元老院阶段 GUI 闭环任务，涉及 `PoliticalSystem`、`senate_api`、提案、投票、否决、宣战、停战、预算、总督任命、战争接管、多玩家权限和自动模式，整体复杂度高，禁止作为一个大任务一次性实现。

本任务是 GUI-P0-02C 的第一个子任务，只做“元老院只读状态与导航接入”。目标是在不执行任何政治动作的前提下，让 GUI 主壳可以进入元老院页面，并展示由 API/Core 提供的安全只读摘要。

本任务完成后，后续子任务才能继续接入提案详情、投票、战争类动作、停战/预算/总督任命以及阶段推进。

## 六、任务目标

1. 让 GUI 左侧阶段导航中的“元老院”从纯占位状态升级为“已接入只读页”。
2. 新增或接入 `SenateStage.qml`，展示元老院阶段只读信息。
3. 提供 GUI 可用的元老院只读 DTO/API/Adapter/Store 数据流。
4. 明确区分“已接入只读”与“可操作真实切片”，避免元老院被误判为可执行政治动作。
5. 保持 `GUI -> API -> Core/System/Service -> Entity` 依赖方向。
6. 不改变任何元老院核心规则、CLI 行为、自动模式、多玩家权限隔离。

## 七、依据文档

请优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-02C 元老院阶段GUI闭环 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02B 天命与人口阶段GUI闭环 开发验收报告 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

重点代码路径：

- `src/api/senate_api.py`
- `src/core/systems/political_system.py`
- `src/api/session_api.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/tests/test_api/test_senate_api.py`
- `src/tests/test_systems/test_political_system.py`
- `src/tests/test_commands/test_phase_senate.py`
- `src/tests/test_gui`

## 八、允许修改范围

| 范围 | 允许内容 |
| --- | --- |
| `src/api/senate_api.py` | 可新增安全只读 view API，例如 `get_senate_view(state, viewer_player_id)`；必须返回统一 `{success, message, data, errors}` 结构。 |
| `src/api/session_api.py` | 可补充阶段导航/阶段摘要中的只读语义，例如 `interaction_mode: "readonly"` 或等价字段；不得破坏天命/人口已有语义。 |
| `src/ui/gui/api_adapter.py` | 可新增获取元老院只读视图的方法。 |
| `src/ui/gui/session_store.py` | 可新增 `senateView`、刷新方法、只读状态属性；不得新增政治动作 Slot。 |
| `src/ui/gui/qml/stages/` | 可新增 `SenateStage.qml`，只展示只读数据与不可操作提示。 |
| `src/ui/gui/qml/shell/GameShell.qml` | 可接入 `SenateStage.qml` 页面切换。 |
| `src/ui/gui/qml/i18n/GuiText.qml` / `localization.py` | 可新增元老院只读页面所需文案，保持 i18n 预留。 |
| `src/tests/test_gui` | 可新增/补强 GUI 启动、Store、Session 测试。 |
| `src/tests/test_api/test_senate_api.py` | 可新增元老院只读 API 测试。 |

如确有必要，可在 `PoliticalSystem` 增加只读辅助方法，但优先复用现有 `build_initial_info()`。不得改变现有政治规则。

## 九、禁止事项

本任务严格禁止：

1. 不得实现提案创建、提案编辑、投票、否决、元老院结算、阶段推进。
2. 不得接入宣战、停战草案、预算、总督任命、战争接管等玩家动作。
3. 不得让 GUI 直接调用 `phase_senate.py`、CLI Command、stdout/input 或旧命令流。
4. 不得让 GUI 直接调用 `PoliticalSystem` 执行动作；玩家动作后续必须经 `senate_api`。
5. 不得在 GUI 层复制元老院政治规则。
6. 不得绕过 `PoliticalSystem` 在 API/GUI 层自行处理提案、投票、战争接管、停战、预算或总督任命规则。
7. 不得直接修改 `_senate_pending`、`_phase_results`、战争私有列表、总督候任字段或其他私有字段。
8. 不得新增 P1 政治玩法：腐败、审判、人物收买、忠诚、人物属性、经验等。
9. 不得破坏 GUI-P0-02A 主壳、GUI-P0-02B 天命/人口闭环、CLI、自动模式和多玩家权限隔离。
10. 不得提交截图、缓存、日志、Excel 临时文件、本地环境文件。
11. 不得读取、修改、暂存项目负责人已有改动的版本规划 Excel：`docs\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`。
12. 不得自行提交 Git。

## 十、实现要求

### 10.1 元老院只读 API/DTO

请提供 GUI 可用的元老院只读视图。建议位置为 `senate_api.get_senate_view(state, viewer_player_id)`，也可提出等价实现，但必须满足：

- 返回统一 `{success, message, data, errors}`。
- `data` 至少包含：
  - `phase_id`: `senate`
  - `viewer_player_id`
  - `current_player_id`
  - `is_current_phase`
  - `is_current_player`
  - `interaction_mode`: `readonly`
  - `actionable`: `False`
  - `can_create_proposal`: `False`
  - `can_vote`: `False`
  - `can_resolve`: `False`
  - `summary`
  - `faction_leaders`
  - `presiding_officer`
  - `active_foreign_wars`
  - `war_threats`
  - `pending_peace_treaties`
  - `governor_vacancies`
  - `pending_contracts`
  - `warnings` 或 `disabled_reason`
- 只读 DTO 可复用 `PoliticalSystem.build_initial_info()`，但不得执行任何会改变状态的方法。
- 如存在多玩家信息隔离风险，优先收束为摘要/count 或公共信息，不泄漏隐藏信息。

### 10.2 阶段导航语义

当前 GUI 的 `implemented/actionable` 容易把“已接入页面”和“可执行阶段动作”混在一起。本任务必须补强语义：

- 元老院在 C-1 中可以是 `implemented=True`，但必须 `actionable=False`。
- 建议新增 `interaction_mode: "readonly"` 或等价字段。
- PhaseRail / ContextPanel / selected summary 应能显示“已接入只读 / 后续子任务接入操作”。
- 不得影响天命和人口阶段既有可操作逻辑。

### 10.3 GUI 页面

新增 `SenateStage.qml` 或等价页面，要求：

- 采用既有方案 A “共和国议事厅”风格，不做大范围视觉重做。
- 中高信息密度，布局清晰，罗马元素只作身份提示。
- 显示元老院只读摘要，包括当前阶段、当前玩家、主持官、派系领袖、战争/停战/总督/合同摘要。
- 所有政治动作按钮不得出现；如保留未来入口，只能禁用并标注“后续任务承接”。
- 页面刷新必须从权威 API/Store 数据读取，不建立 GUI 本地权威状态。
- 不要求 CGT-01 提交 GUI 截图；真实 GUI 视觉由项目负责人/SA 人工验证。

### 10.4 Store / Adapter

- `GuiApiAdapter` 可新增 `get_senate_view(viewer_id)`。
- `GuiSessionStore` 可新增 `senateView`、`senateViewChanged`、`_refresh_senate_view()`。
- 选择元老院页面或刷新 snapshot 时，应刷新元老院只读数据。
- 不得新增 `doVote`、`doPropose`、`doResolveSenate` 等动作 Slot。

### 10.5 i18n

- 新增 GUI 文案必须集中到 `GuiText.qml` 和/或 `localization.py`。
- 不要求本轮完成完整多语言切换，但不得把后续难以迁移的大量硬编码散落在 QML 内。

## 十一、调试日志要求

- 只读视图获取失败时，可记录 DEBUG 日志，包含 phase、viewer、current_player、错误摘要。
- 正常高频刷新不得产生大量低价值日志。
- 不得记录其他玩家隐藏信息。

## 十二、测试要求

CGT-01 至少执行并报告以下测试：

### 12.1 新增/补强测试

1. `test_senate_api.py`
   - 元老院只读 API 返回统一响应结构。
   - `interaction_mode == "readonly"`。
   - `actionable/can_vote/can_create_proposal/can_resolve` 均为 `False`。
   - 无效 state / 无效 viewer 有明确失败响应。

2. `test_gui/test_session_api.py`
   - 元老院阶段在导航中可显示为已接入只读。
   - 当前阶段为元老院时，`implemented=True` 但 `actionable=False`。
   - 天命/人口已有导航语义不退化。

3. `test_gui/test_adapter.py`
   - Store 可选择 `senate`。
   - Store 能刷新并暴露 `senateView`。
   - 选择元老院不会执行任何政治业务。

4. `test_gui/test_qml_startup.py`
   - QML 能加载 `SenateStage`。
   - 根对象和既有 `mortalityStage`、`populationStage` 不退化。

### 12.2 回归测试

请至少执行：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_senate_api.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems\test_political_system.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_commands\test_phase_senate.py" -q
```

如修改范围触及 `session_api`、GUI Store 或全局阶段导航，建议执行 full regression：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

并执行：

```powershell
git diff --check
```

如果 full regression 因非本任务原因失败，必须列出失败测试、失败原因判断和是否阻塞本任务。

## 十三、验收标准

### 功能验收

- GUI 可以选择元老院阶段并显示 `SenateStage`。
- 元老院页面能显示权威只读摘要。
- 元老院页面不执行任何政治动作。
- 当前阶段为元老院时，界面仍明确显示“只读接入 / 操作由后续任务承接”。

### 架构验收

- 保持 `GUI -> API -> Core/System/Service -> Entity`。
- GUI 不调用 `phase_senate.py`。
- GUI 不直接调用 `PoliticalSystem` 执行动作。
- API/GUI 不复制元老院政治规则。
- 无新增私有字段直改。
- `senate_api` 返回结构保持 `{success, message, data, errors}`。

### 回归验收

- GUI-P0-02A 主壳不退化。
- GUI-P0-02B 天命/人口阶段不退化。
- `senate_api`、`PoliticalSystem`、`phase_senate` 现有测试不退化。
- CLI、自动模式、多玩家权限不退化。

## 十四、交付物

请 CGT-01 完成后提交开发验收报告，归档到：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02C-1 元老院只读状态与导航接入 开发验收报告 - CGT-01.md`

报告必须包含：

```text
Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED / RETURNED

代码基线：
修改文件：
实现摘要：
API / Session / Store / QML 变更说明：
架构边界自检：
测试命令与结果：
git diff --check 结果：
未修改/未触碰范围确认：
风险与遗留问题：
下一子任务建议：
```

CGT-01 不得自行提交 Git。完成后请回执 SA-01 进行最终验收。
