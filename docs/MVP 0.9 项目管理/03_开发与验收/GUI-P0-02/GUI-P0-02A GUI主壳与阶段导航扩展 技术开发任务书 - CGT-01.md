# GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01

发布日期：2026-06-30

发布角色：SA-01 / 系统架构师

执行 Agent：CGT-01

任务编号：GUI-P0-02A

任务名称：GUI 主壳与阶段导航扩展

任务类型：GUI 基础架构 / 阶段容器 / P0 核心 GUI 闭环前置

优先级：P0.5 / P1 前置

目标 Sprint：GUI-P0 Sprint：MVP0.7/P0 核心 GUI 闭环

代码基线：Git HEAD `bbd5240 Add GUI-P0-02A PM intent package`

项目根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

正式文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs`

Python 解释器：`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

## 一、背景说明

GUI-P0-01 已完成 PySide6/QML 可玩 GUI 原型，并验证人口阶段“庆典 + 公职投票 + 玩家交接 + 选举结果”的真实垂直切片。当前 GUI 已具备：

- `gui_main.py` 启动入口。
- `src/ui/gui/app.py` QML 加载与诊断。
- `GameShell` 三栏布局。
- `PhaseRail`、`TopStatusBar`、`ContextPanel`、`FeedbackPanel`、`PlayerHandoffOverlay`。
- `GuiSessionStore` 与 `GuiApiAdapter`。
- `session_api` 安全 viewer DTO。
- GUI 启动和 Session/API 测试骨架。

但当前 GUI 仍主要围绕人口阶段切片：阶段导航、顶部状态、右侧上下文和占位页面还没有形成完整 MVP0.7/P0 阶段主壳。GUI-P0-02A 的职责是建立后续 GUI-P0-02B 到 GUI-P0-02G 可以复用的主框架，不负责提前实现各阶段业务闭环。

## 二、任务目标

在现有 GUI-P0-01 基础上扩展 GUI 主壳，使 GUI 中可见完整 MVP0.7/P0 阶段序列，并建立通用阶段容器、全局状态摘要、当前玩家/派系摘要、反馈区、未实现阶段占位和后续扩展点。

本任务完成后，玩家应能在 GUI 中看到：

1. 顶部全局状态栏：年份/回合、当前阶段、当前玩家、当前派系、国库、派系金库或摘要。
2. 左侧阶段导航：天命、人口、元老院、收入、广场、战争/海战、革命/决算。
3. 中央阶段容器：人口阶段仍显示 GUI-P0-01 真实切片；未迁移阶段显示明确占位/只读摘要/后续任务承接。
4. 右侧上下文区：当前 viewer 派系资源、当前阶段说明、可执行/不可执行原因、关键警告。
5. 底部反馈区：成功、失败、警告、信息、未实现、权限拒绝等结构化反馈。

## 三、依据文档

请优先阅读：

- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 技术边界审查报告 - SA-01.md`
- `docs/MVP 0.9 项目管理/P1功能最小可用GUI开发与验收标准.md`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-01 MVP0.7可玩GUI原型 技术开发任务书 - KIMI-01.md`
- `AGENTS.md`
- `.agents/runtime_profile.md`

重点代码：

- `gui_main.py`
- `gui_screenshot.py`
- `src/api/session_api.py`
- `src/ui/gui/app.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/qml/Main.qml`
- `src/ui/gui/qml/shell/*.qml`
- `src/ui/gui/qml/components/*.qml`
- `src/ui/gui/qml/stages/*.qml`
- `src/tests/test_gui/*.py`

## 四、允许修改范围

| 范围 | 允许内容 |
| --- | --- |
| `src/api/session_api.py` | 仅限 GUI shell 所需只读 DTO、阶段导航、全局摘要、权限/未实现提示 |
| `src/ui/gui/session_store.py` | 增加 selected phase、shell snapshot、global warnings、反馈/刷新 Slot |
| `src/ui/gui/api_adapter.py` | 增加薄查询包装；继续验证 `{success, message, data, errors}` |
| `src/ui/gui/app.py` | QML 诊断、对象查找、信号连接、启动日志等主壳支持 |
| `src/ui/gui/qml/shell/*.qml` | 主壳、阶段导航、顶部状态、右侧上下文、反馈区扩展 |
| `src/ui/gui/qml/components/*.qml` | 可复用展示组件、按钮、状态徽章、占位组件 |
| `src/ui/gui/localization.py` 或 `src/ui/gui/qml/i18n/*.qml` | 可新增 GUI 文案集中层；仅限本任务新增/改动文案的 key/fallback 管理 |
| `src/ui/gui/qml/stages/*.qml` | 人口阶段保留；新增/调整未实现阶段占位页面 |
| `src/tests/test_gui/*.py` | GUI shell、导航、Session DTO、QML 启动、权限 smoke tests |
| `gui_screenshot.py` | 截图脚本补充 GUI-P0-02A 主壳截图 |
| `src/ui/gui/README.md` | 如需更新 GUI 运行或验收说明 |

谨慎允许：

- `gui_main.py`：仅限启动日志或初始化参数，不得改为 CLI 阶段执行入口。
- `data/scenarios/gui_prototype.json`：仅限最小测试场景补强，不得破坏 GUI-P0-01 人口切片。

## 五、禁止事项

1. 不得实现或改写 P1 新玩法。
2. 不得提前实现 GUI-P0-02B 到 GUI-P0-02F 的阶段业务闭环。
3. 不得让 GUI/QML 直接调用 Core/System/Service/Entity。
4. 不得直接修改 Core 私有字段。
5. 不得在 GUI 层复制人口、元老院、收入、广场、战争/海战、决算阶段核心业务规则。
5a. 不得把本任务新增的大量 GUI 文案继续散落硬编码在 QML/Session 中；新增主壳、导航、占位、反馈、权限提示文案必须进入 GUI 文案集中层或使用稳定 i18n key。
6. 不得通过 `game_api.execute_phase()` 或 `game_api.execute_turn()` 驱动 GUI 阶段流程。
7. 不得新增 API -> UI 命令依赖；不要扩大处理 `game_api.py` 和 `session_api.resolve_population_slice()` 的历史债务。
8. 不得修改 `src/core/`、`src/ui/commands/`、`src/ui/processors/`，除非先停止并向 SA 回报。
9. 不得修改 `docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`。
10. 不得破坏 CLI、自动模式、多玩家权限隔离和 GUI-P0-01 人口阶段切片。
11. 不得提交 Git。
12. 不得提交缓存、日志、截图临时产物、Excel 锁文件或本地环境文件。

## 六、实现要求

### 6.1 阶段导航

必须在 GUI 中展示完整阶段序列：

| id | 显示名 | 本轮状态 |
| --- | --- | --- |
| `mortality` | 天命 | 占位/后续 GUI-P0-02B 承接 |
| `population` | 人口 | 保留 GUI-P0-01 真实切片 |
| `senate` | 元老院 | 占位/后续 GUI-P0-02C 承接 |
| `revenue` | 收入 | 占位/后续 GUI-P0-02D 承接 |
| `forum` | 广场 | 占位/后续 GUI-P0-02D 承接 |
| `combat` | 战争/海战 | 占位/后续 GUI-P0-02E 承接 |
| `resolution` | 革命/决算 | 占位/后续 GUI-P0-02F 承接 |

说明：本表是 GUI-P0 Sprint 的展示/承接顺序，不要求本任务修改 CLI 或 Core 的历史阶段执行顺序。

每个阶段导航项至少包含：

- `id`
- `index`
- `name`
- `subtitle` 或 `description`
- `status`
- `implemented`
- `enabled`
- `actionable`
- `handoff_task`
- `locked_reason` 或 `disabled_reason`

### 6.2 阶段容器

- `population` 仍加载现有 `PopulationStage`。
- 未实现阶段应加载统一占位页面，例如 `StagePlaceholder` 或增强现有 `LockedStagePlaceholder`。
- 占位页必须明确显示：阶段名称、当前不可操作原因、后续任务编号、不会影响当前游戏状态。
- 切换阶段只改变 GUI selected phase，不应执行 Core 阶段结算。

### 6.3 全局状态摘要

顶部状态栏至少显示：

- 回合编号。
- 年份显示。
- 当前权威阶段或 GUI 当前阶段。
- 当前玩家 ID。
- viewer 派系名称/ID。
- 国库。
- 当前 viewer 派系金库摘要。

右侧上下文面板至少显示：

- viewer 派系资源。
- 当前阶段说明。
- 当前阶段是否已实现/是否可操作。
- 权限提示。
- 关键警告或后续任务承接信息。

### 6.4 Session/API DTO

可以选择以下方案之一：

方案 A：扩展 `session_api.get_session_snapshot()`。

方案 B：新增 `session_api.get_gui_shell_snapshot(state, viewer_player_id)`，并让 Store 调用该接口。

无论选哪种，返回值必须保持 `{success, message, data, errors}`。DTO 必须只包含 GUI 可安全展示的信息，不得泄漏其他玩家隐藏金库或人物私有详情。

建议 DTO：

```python
{
    "current_player_id": "player_optimates",
    "viewer_player_id": "player_optimates",
    "viewer_faction_id": "optimates",
    "is_current_player": True,
    "current_phase_id": "population",
    "selected_phase_id": "population",
    "public_resources": {...},
    "faction_resources": {...},
    "phase_navigation": [...],
    "selected_phase_summary": {...},
    "global_warnings": [...],
}
```

### 6.5 Store / Adapter

`GuiSessionStore` 应提供或补强：

- `selectedPhaseId`
- `selectedPhaseName`
- `selectedPhaseSummary`
- `globalWarnings`
- `phaseNavigation`
- `selectPhase(phase_id)` Slot
- `refreshSnapshot()` 或等价 Slot
- 统一反馈触发方法

`GuiApiAdapter` 应继续负责：

- 调用 API。
- 验证 `{success, message, data, errors}`。
- 统一映射成功、失败、异常反馈。
- 成功操作后刷新权威快照。

### 6.6 反馈区

反馈区必须能显示以下类型：

- `success`
- `error`
- `warning`
- `info`
- 未实现/后续任务承接提示
- 权限拒绝提示

如果 QML 内部点击未实现阶段，应通过 Store/反馈区提示，不得静默失败。

### 6.7 视觉与布局

沿用方案 A“共和国议事厅”：

- 暗色应用背景。
- 暗红与青铜作为小面积强调。
- 中高信息密度。
- 表格/列表清晰，弹窗/反馈可读。
- 罗马元素仅作身份提示。
- 不做大范围视觉重做。
- 不采用地图主导布局。


### 6.8 多语言 / i18n 预留要求

当前项目已有 Core 层 `i18n` / terminology 基础，但 GUI-P0-01 仍包含较多 QML 硬编码中文。GUI-P0-02A 不要求完成完整多语言切换，但必须从主壳开始建立可迁移边界。

本轮最低要求：

1. 对本任务新增或大幅改动的主壳、阶段导航、占位页、反馈区、权限提示、状态标签文案，建立集中管理方式。
2. 可以选择以下任一实现方式：
   - Python 侧 GUI 文案服务，例如 `src/ui/gui/localization.py` / `gui_text.py`；
   - QML 侧文案 Singleton，例如 `src/ui/gui/qml/i18n/GuiText.qml`；
   - 复用项目现有 `i18n`，由 `session_api` / Store 提供 resolved text 与稳定 key。
3. Session/API DTO 应保留稳定 key 或 ID，例如：
   - `phase_id`
   - `name_key`
   - `description_key`
   - `status_key`
   - `handoff_task`
4. 默认显示语言可继续为 `zh-CN`，但 key 命名和文案集中方式必须支持后续扩展 `en-US`。
5. 未实现阶段占位文案不得只写死在单个 QML 文件里；至少应从集中层或 DTO fallback 获取。
6. 既有 GUI-P0-01 人口阶段旧硬编码文案不要求本轮全量迁移；但如果本任务修改这些区域，应避免继续扩大硬编码债务。
7. 若实现 Agent 认为完整接入现有 `src.core.i18n` 会导致范围扩大，应选择轻量 GUI 文案 catalog，并在报告中建议后续 `GUI-I18N-01` 独立任务统一迁移。
## 七、调试日志要求

必须记录：

- GUI 启动和 QML 加载失败。
- Session snapshot 刷新失败。
- 阶段选择变化。
- 未实现阶段点击。
- API 调用失败。

日志要求：

- 包含 phase_id、viewer_player_id、current_player_id、操作类型、结果摘要。
- 不得记录其他玩家隐藏信息。
- 不得在正常渲染或高频刷新中刷大量低价值日志。

## 八、测试要求

执行 Agent 必须至少新增或补强以下测试：

### 8.1 GUI Session/API 测试

- 快照包含 7 个阶段导航项。
- 阶段显示顺序为：天命、人口、元老院、收入、广场、战争/海战、革命/决算。
- 新增/改动 GUI 文案存在集中定义或稳定 key，不继续散落硬编码。
- 人口阶段标记为已实现/可操作。
- 未实现阶段标记为不可业务操作，并包含后续任务编号。
- viewer 只能看到本派系资源和本派系人物。

### 8.2 Store / Adapter 测试

- `GuiSessionStore.selectPhase("senate")` 或等价操作不崩溃。
- 未实现阶段选择后可产生 `warning/info` 反馈或更新 selected phase summary。
- 切回 `population` 后人口阶段数据仍可刷新。
- Adapter 对 API 失败响应仍映射为 error feedback。

### 8.3 QML 启动与主壳测试

- `Main.qml` root 非空。
- 可定位：
  - `gameShell`
  - `topStatusBar`
  - `phaseRail`
  - `contextPanel`
  - `feedbackPanel`
  - `populationStage`
  - `lockedStagePlaceholder` 或新的阶段占位对象
  - `playerHandoffOverlay`
- 阶段导航数据可渲染 7 项，或通过 Store/QML 对象验证 7 项。

### 8.4 回归测试命令

请执行：

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
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_population.py" -q
```

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

若全量测试失败，必须说明失败是否来自环境权限、既有技术债或本任务代码。

### 8.5 截图 / 可视验收

请运行或更新 `gui_screenshot.py`，至少生成：

- 1440x900 主壳截图。
- 1280x720 主壳截图。

截图中必须可见：

- 完整 7 阶段导航。
- 顶部状态栏。
- 右侧上下文区。
- 底部反馈区。
- 人口阶段真实切片或未实现阶段占位提示。

截图文件可作为本地验收材料；默认不要提交截图，除非 SA/项目负责人另行要求。

## 九、验收标准

| 类别 | 标准 |
| --- | --- |
| 范围 | 只完成主壳、导航、状态摘要、反馈区和扩展点，不实现后续阶段业务闭环 |
| 可见阶段 | GUI 可见完整 7 阶段序列 |
| 人口切片 | GUI-P0-01 人口阶段仍可用，测试不退化 |
| 状态来源 | 状态摘要来自 `session_api` / 权威 `GameState` DTO，不维护第二套权威状态 |
| API 边界 | GUI 通过 Store/Adapter/API 读取或操作，不绕过 API |
| 权限隔离 | viewer 只看到本派系资源和人物，不泄漏其他玩家隐藏信息 |
| 未实现提示 | 未迁移阶段明确显示后续任务承接和不可操作状态 |
| 视觉 | 延续方案 A，不做大范围视觉重做，不引入地图主导布局 |
| 测试 | 指定 GUI、API、人口命令和全量回归通过或失败原因明确 |
| 文档 | 开发验收报告归档到正式 docs 路径 |
| 多语言预留 | 本任务新增/改动主壳文案有集中 catalog 或稳定 i18n key，默认 zh-CN 可用，后续可扩展 en-US |

SA 建议判定：

- 满足以上要求：`PASS`。
- 仅存在轻微展示/文档问题且不影响后续任务：`CONDITIONAL_PASS`。
- GUI 绕过 API、泄漏信息、破坏人口切片、提前吞并阶段业务、全量测试失败且原因不明：`RETURN_FOR_REWORK`。

## 十、交付物

CGT-01 完成后请归档开发验收报告：

`docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01.md`

报告必须包含：

1. `Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED / NEEDS_CLARIFICATION`
2. 修改文件清单。
3. 主壳、阶段导航、状态区、反馈区实现摘要。
4. Session/API/Store/Adapter 变更说明。
5. 新增/修改测试说明。
5a. 多语言/i18n 预留实现说明：文案集中层路径、key 策略、未覆盖的旧硬编码范围。
6. 测试命令与完整结果。
7. 截图生成结果和截图路径。
8. `git diff --check` 结果。
9. 当前 `git status --short`。
10. 未完成事项、风险和 GUI-P0-02B 承接建议。

## 十一、执行前检查

CGT-01 开始前请确认：

```powershell
git status --short --branch
```

注意：本地可能存在项目负责人/PM 正在编辑的版本规划 xlsx。不得修改或暂存该文件。

请勿自行提交 Git。完成后等待 SA/项目负责人授权归档。
## 附录：2026-07-01 GUI截图交付规则修订

根据项目负责人最新决策，CGT-01 后续不再被强制要求提交 GUI 截图文件。本任务书中所有“截图”“截图路径”“截图材料”要求统一解释为：

- 自动截图可作为辅助材料，但不是 CGT-01 必交付物。
- 若无头 Qt / 自动截图环境导致中文方块、截图失败或截图不可用于视觉判断，不作为返工阻塞。
- CGT-01 必须继续交付自动化测试、QML 启动验证、GUI 状态/DTO 测试和手工验证步骤。
- GUI 最终视觉验收由项目负责人或 SA 在真实 Windows GUI 窗口人工完成。
