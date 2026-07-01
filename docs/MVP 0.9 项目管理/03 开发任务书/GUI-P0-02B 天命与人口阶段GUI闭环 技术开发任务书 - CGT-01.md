# GUI-P0-02B 天命与人口阶段 GUI 闭环 技术开发任务书 - CGT-01

创建日期：2026-07-02
发布对象：CGT-01
发布角色：SA-01 / 系统架构师
任务类型：GUI 阶段闭环 / 架构边界收束 / P0 GUI Sprint
优先级：P0.5 / P1 前置
代码基线：`2296cb0 Add GUI-P0-02B PM intent package`
项目根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`
正式文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs`

## 一、任务目标

在 GUI-P0-02A 主壳和阶段导航基础上，完成 GUI-P0-02B《天命与人口阶段 GUI 闭环》：

1. 将天命阶段接入 GUI 主壳，形成最小可用 GUI 闭环。
2. 复用并整合 GUI-P0-01 已完成人口阶段切片，使其在 GUI-P0-02A 阶段容器、状态栏、反馈区和导航体系中继续可用。
3. 保持真实阶段顺序：`天命-收入-广场-人口-元老院-战争-决算`。
4. 天命阶段完成后不得直接跳到人口阶段，应按真实阶段顺序进入 `revenue` 或当前系统定义的下一阶段占位/承接状态。
5. 建立天命阶段 GUI 安全 API/Service/Session/Store 边界，不允许 GUI 或 API 直接调用 CLI 命令层。

## 二、背景说明

GUI-P0-02A 已完成主壳、阶段导航、状态栏、右侧上下文、反馈区、placeholder 阶段和 i18n 预留。当前 `PopulationStage` 是唯一真实切片。

但当前代码仍存在以下 GUI-P0-02B 前置缺口：

- `session_api.create_gui_prototype_session()` 当前直接把 `mortality/revenue/forum` 标记为已执行并进入人口阶段。
- `session_api.get_session_snapshot()` 当前固定 `current_phase_id = "population"`。
- 天命核心规则仍在 `src/ui/commands/phase_mortality.py` 命令层。
- 当前无 `mortality_api.py`，无 `MortalityService`，GUI 不具备安全执行天命的 API 入口。

本任务必须先收束天命 API/服务边界，再接 GUI。不要让 QML/Session/Adapter 调用 `MortalityCommand` 或 `game_api.execute_phase()`。

## 三、依据文档

请优先参考：

- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-02B 天命与人口阶段GUI闭环 PM任务意图包.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02B 天命与人口阶段GUI闭环 技术边界审查报告 - SA-01.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A-R1 UI反馈修正 SA复核回执.md`
- `docs/MVP 0.9 项目管理/P1功能最小可用GUI开发与验收标准.md`
- `docs/MVP 0.9 项目管理/AI开发任务模板.md`
- `AGENTS.md`
- `.agents/runtime_profile.md`

关键代码路径：

- `src/api/session_api.py`
- `src/api/population_api.py`
- `src/ui/commands/phase_mortality.py`
- `src/ui/commands/phase_population.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/stages/PopulationStage.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`

## 四、允许修改范围

| 范围 | 说明 |
| --- | --- |
| `src/core/service/mortality_service.py` | 可新增。承载天命阶段核心规则，返回结构化结果。 |
| `src/core/service/__init__.py` | 可导出 `MortalityService`。 |
| `src/api/mortality_api.py` | 可新增。提供 GUI/CLI 可复用的天命 API。 |
| `src/api/session_api.py` | 可修改 session 创建、snapshot、阶段推导、天命/人口 DTO。 |
| `src/ui/commands/phase_mortality.py` | 可修改为服务/API 包装层，保持 CLI 旧行为。 |
| `src/ui/gui/api_adapter.py` | 可新增天命 API 调用包装。 |
| `src/ui/gui/session_store.py` | 可新增天命 view、执行 Slot、阶段刷新逻辑。 |
| `src/ui/gui/qml/stages/MortalityStage.qml` | 可新增天命阶段页面。 |
| `src/ui/gui/qml/shell/*.qml` | 可修改主壳容器、上下文、反馈接入。 |
| `src/ui/gui/qml/i18n/GuiText.qml` 与 `src/ui/gui/localization.py` | 可新增本轮 GUI 文案 key。 |
| `src/core/game_state.py` | 仅当需要公共方法避免私有字段直写时可小范围补充，例如 `record_active_event()`。 |
| `src/tests/test_gui/` | 必须新增/调整 GUI tests。 |
| `src/tests/test_api/` | 必须新增/调整 mortality/session/population API tests。 |
| `src/tests/test_commands/` | 必须保留 mortality/population CLI 回归。 |

## 五、禁止事项

- 不得改变真实阶段顺序：`天命-收入-广场-人口-元老院-战争-决算`。
- 不得让天命阶段完成后直接跳到人口阶段。
- 不得在 GUI 层复制天命、人口、庆典、投票、选举等核心业务规则。
- 不得让 GUI/Adapter/Session 调用 `src.ui.commands.phase_mortality.MortalityCommand`。
- 不得让 `mortality_api` 或 `session_api` 通过 `game_api.execute_phase()` 间接调用命令层。
- 不得新增 GUI/API 对 `GameState`、System、Service、Entity 私有字段的直接写入。
- 不得新增 P1 玩法，例如人物属性、经验、忠诚、腐败、审判、收买等。
- 不得提前实现 GUI-P0-02C 元老院、GUI-P0-02D 收入/广场、GUI-P0-02E 战争、GUI-P0-02F 决算。
- 不得修改或暂存 `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`。
- 不得提交截图、缓存、日志、临时目录或环境文件。
- 不得自行提交 Git。

## 六、实现要求

### 1. 天命服务层

新增或整理 `MortalityService`，要求：

- 从命令层收束天命核心规则，避免 GUI 复制规则。
- 执行事件抽取、死亡、丰收、和平、猛男、灾害等既有 P0 行为。
- 返回结构化结果，不依赖 stdout：

```python
{
    "events": [
        {
            "name": "...",
            "effect": "death|bountiful_harvest|peace|mighty_man|disaster|unknown",
            "summary": "...",
            "impacts": [...],
            "logs": [...]
        }
    ],
    "phase_executed": True,
    "next_phase_id": "revenue"
}
```

- 旧 CLI 输出可以由 `phase_mortality.py` 根据结构化结果格式化打印。
- 如需设置 active event，请优先补充 GameState 公共方法，不要在 API/GUI 层直写 `_active_events`。

### 2. 天命 API

新增 `src/api/mortality_api.py`，至少提供：

- `execute_mortality_phase(state, viewer_player_id)`
- 可选：`get_mortality_view(state, viewer_player_id)`

要求：

- 返回统一 `{success, message, data, errors}`。
- 校验重复执行；重复执行应返回失败或只读已完成状态，不得重复应用事件。
- 校验 viewer 是否存在；如当前项目阶段规则需要当前玩家权限，则必须校验 current player。
- 成功后 mark `mortality` executed。
- 返回 `next_phase_id = "revenue"`，不得返回 `population` 作为天命后的下一阶段。

### 3. Session API 与阶段推导

修改 `session_api`：

- 不得继续固定 `current_phase_id = "population"`。
- 应按阶段顺序推导当前阶段：第一个未执行阶段即 current phase。
- 阶段顺序固定为：`mortality, revenue, forum, population, senate, combat, resolution`。
- `implemented` 至少对 `mortality` 和 `population` 为 true。
- `actionable` 必须同时满足：阶段已实现、该阶段是当前阶段、viewer 是当前玩家。
- 天命完成后 current phase 应变为 `revenue` 占位；收入/广场未实现时保持 placeholder，不得自动跳人口。
- 若需要保留测试辅助入口，可增加显式参数或 helper 让测试/开发创建“直接进入人口阶段”的 session，但正式 GUI 启动默认应从真实当前阶段开始。

### 4. GUI Store / Adapter

修改 `GuiApiAdapter`：

- 新增天命 API 包装。
- 不得导入或调用命令层。

修改 `GuiSessionStore`：

- 新增天命 view/result 属性或 DTO。
- 新增 `doExecuteMortality()` Slot。
- 天命执行成功后刷新 snapshot，并显示结构化 feedback。
- 若当前阶段为 `revenue` placeholder，选中收入时应提示后续任务承接，不执行任何收入业务。
- 人口视图刷新仍走现有 `session_api.get_population_view()`。

### 5. QML

新增 `MortalityStage.qml`：

- 显示当前回合/年份、天命状态、事件名称、效果摘要、影响对象、继续流程提示。
- 提供“执行天命”按钮，仅在 `current_phase_id == mortality`、viewer 是当前玩家、mortality 未执行时可用。
- 执行后展示结果，并通过反馈区提示。
- 不要求截图交付；真实窗口视觉由项目负责人或 SA 人工验证。

修改 `GameShell.qml`：

- `selectedPhaseId == "mortality"` 时显示 `MortalityStage`。
- `selectedPhaseId == "population"` 时显示 `PopulationStage`。
- 其他阶段显示 `LockedStagePlaceholder`。

### 6. 人口阶段整合

- 保持人口阶段原庆典、投票、玩家交接、选举结果能力。
- 只有当前阶段为 `population` 时，人口操作按钮才可执行。
- 非当前玩家应只读或显示权限提示。
- 不要新增第二套人口状态。

### 7. i18n 文案

- 新增 GUI 文案进入 `GuiText.qml` 或 `src/ui/gui/localization.py`。
- 默认 zh-CN 即可，不要求运行时语言切换。
- 不要无序散落新硬编码。

## 七、调试日志要求

- 天命执行、事件抽取、事件应用、死亡对象、active event 写入、阶段标记、下一阶段推导应写入可定位日志。
- 人口阶段操作失败、权限拒绝、状态刷新失败应保留可定位日志。
- 日志不得泄露其他玩家不可见信息。

## 八、测试要求

请 CGT-01 至少执行并在报告中记录：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_population_api.py" -q
```

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_mortality.py" "src\tests\test_commands\test_phase_population.py" -q
```

如新增 `test_mortality_api.py` 或服务测试，请一并执行并列出结果。

请执行 full regression：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

并执行：

```powershell
git diff --check
```

根据当前项目规范：如果 CGT-01 full `src/tests` 报告完整，SA 后续默认不重复跑全量，只复核方案一致性、diff、架构边界和测试覆盖；高风险或证据不足时再补跑。

## 九、验收标准

### 功能

- GUI 可进入天命阶段页面。
- 天命页面能显示执行前状态、执行后事件结果、效果摘要和影响对象。
- 天命执行后标记 `mortality` 已执行。
- 天命执行后 current phase 变为 `revenue` 或真实下一阶段，不跳到 `population`。
- 人口阶段切片仍能完成庆典、投票、玩家交接、选举结果。
- 阶段顺序保持 `天命-收入-广场-人口-元老院-战争-决算`。

### 架构

- GUI 只调用 `GuiSessionStore` / `GuiApiAdapter`。
- Adapter 只调用 API。
- API 调用 Service/Core，不调用 UI command。
- Core/Service 不依赖 GUI/API/QML。
- 无新增 GUI/API 对私有字段直写。

### 测试

- 指定 GUI/API/command/focused tests 通过。
- full `src/tests` 通过或失败项有明确非本任务原因。
- `git diff --check` 无空白错误。

### 视觉

- 不要求 CGT-01 提交截图。
- 请在报告中列出人工视觉验证步骤和待确认项。
- 最终视觉由项目负责人或 SA 在真实 Windows GUI 窗口确认。

## 十、交付物

请归档开发验收报告：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02B 天命与人口阶段GUI闭环 开发验收报告 - CGT-01.md`

报告必须包含：

1. Decision by CGT-01: `READY_FOR_SA_REVIEW` 或明确阻塞原因。
2. 修改文件清单。
3. 天命服务/API/GUI 实现摘要。
4. 人口阶段整合与回归说明。
5. 阶段顺序和“天命后不跳人口”的验证说明。
6. 架构边界说明：确认没有 GUI/API 调用命令层。
7. 测试命令与结果。
8. full `src/tests` 结果。
9. `git diff --check` 结果。
10. 人工视觉验收待确认项。
11. 风险与遗留问题。

完成后请在 CGT-01 线程回执 `READY_FOR_SA_REVIEW`。不要自行提交 Git。