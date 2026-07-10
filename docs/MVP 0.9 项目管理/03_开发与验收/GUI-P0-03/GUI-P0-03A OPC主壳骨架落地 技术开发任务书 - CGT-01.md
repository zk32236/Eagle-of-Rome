# GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01

## 一、任务基本信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | GUI-P0-03A |
| 任务名称 | OPC主壳骨架落地 |
| 执行对象 | CGT-01 |
| 任务类型 | GUI 主壳骨架 / 界面结构落地 / 安全只读入口接入 |
| 优先级 | P0 |
| 所属阶段 | GUI-P0-03 OPC-01 GUI重设计实施拆分 |
| 代码基线 | `5488f16 Confirm OPC-01 GUI direction for GUI-P0-03A` |
| 计划归档路径 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01.md` |
| 归档状态 | `ARCHIVED_BY_SA` |

## 二、任务目标

本轮目标是将 OPC-01 v3.23 已确认的 GUI 五区主壳结构落地到现有 PySide6/QML GUI 中，形成后续元老院交互化、广场、战争、收入、决算等阶段 GUI 开发的稳定容器。

本轮只做：

- 顶栏
- 左导航
- 中栏阶段容器
- 公告区
- 右侧状态/日志面板
- 底栏 12 查询按钮占位或安全只读入口
- 阶段容器与未实现阶段 placeholder
- 必要的 SessionStore / GuiApiAdapter 只读数据支持

本轮不是全阶段 GUI 重写，不接入复杂业务动作。

## 三、背景说明

项目负责人已确认 OPC-01 v3.23 作为后续 GUI 目标方向。后续 GUI 开发以 OPC-01 五区布局和 `EOR_GUI设计文档.md` V2.0 范围内迭代为准。

当前 GUI 基线已具备：

- PySide6/QML 主壳
- 阶段导航
- 天命阶段 GUI 闭环
- 人口阶段 GUI 闭环
- 元老院只读页
- `GuiApiAdapter`
- `GuiSessionStore`
- `GuiText.qml` / `localization.py` 的初步 i18n 集中层

本轮应在此基础上改造主壳结构，而不是把 HTML 原型代码直接搬入 QML。

## 四、依据文档

请优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03 OPC-01界面确认记录 - PM.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-03 OPC-01 GUI重设计界面确认与实施拆分 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\PM_Instruction.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_GUI_Prototype_v3.23.html`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_GUI设计文档.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_UI_API_Mapping.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\GUI_Code_Alignment_Audit.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 五、允许修改范围

允许修改以下范围：

| 范围 | 说明 |
| --- | --- |
| `src/ui/gui/qml/shell/` | 主壳、顶栏、阶段导航、右侧状态/日志、底栏按钮容器 |
| `src/ui/gui/qml/stages/` | 阶段容器、未实现阶段 placeholder、现有天命/人口/元老院页面的嵌入适配 |
| `src/ui/gui/qml/components/` | 可复用按钮、面板、状态卡、日志项等 UI 组件 |
| `src/ui/gui/qml/theme/` | 必要的主题尺寸、颜色、间距变量 |
| `src/ui/gui/qml/i18n/GuiText.qml` | 新增 UI 文案 key / getter / 格式化函数 |
| `src/ui/gui/localization.py` | 如需补充 Python 侧 GUI 文案 key |
| `src/ui/gui/session_store.py` | 只读状态、底栏查询状态、日志/反馈状态、阶段选择状态 |
| `src/ui/gui/api_adapter.py` | 安全只读查询入口包装 |
| `src/api/session_api.py` | 如确需补充 shell DTO、全局摘要、导航状态；必须保持 `{success, message, data, errors}` |
| `src/tests/test_gui/` | GUI Store、Adapter、QML 启动、QML 文案扫描测试 |
| `docs/MVP 0.9 项目管理/03 开发任务书/` | CGT-01 开发验收报告 |

可安全复用的现有只读 API 包括但不限于：

- `session_api.get_session_snapshot()`
- `game_api.get_status_summary()`
- `faction_api.get_factions_status()`
- `figure_api.get_figure_info()`
- `contract_api.get_contracts_status()`
- `province_api.get_province_info()`
- `game_api.get_public_land_info()`

如果某个底栏查询缺少安全 API，本轮应显示占位状态，不得绕过 API 读取 Core 私有字段。

## 六、禁止事项

CGT-01 必须遵守以下禁止事项：

1. 不得直接迁入或改写 `EOR_GUI_Prototype_v3.23.html` 的 HTML / CSS / JS 代码。
2. 不得把本任务扩大成全阶段 GUI 重写。
3. 不得接入元老院提案、投票、否决、结算、战争接管、停战、预算、总督任命等复杂业务动作。
4. 不得接入广场退休、招募、合同投标、土地交易、凯旋投票、广场结算等复杂业务动作。
5. 不得接入战争/海战执行逻辑。
6. 不得接入收入结算或决算推进逻辑。
7. 不得让 GUI 直接调用 CLI Command。
8. 不得让 GUI 调用 `game_api.execute_phase()` 或 `game_api.execute_turn()`。
9. 不得让 GUI 直接或间接调用 `CombatCommand`。
10. 不得绕过 `GuiApiAdapter` / `SessionStore` 直接调用 Core/System/Service/Entity。
11. 不得绕过 API/SessionStore 权限边界展示私有信息。
12. 不得新增 P1 新玩法或修改 Core 规则。
13. 不得做无关大范围格式化。
14. 不得提交 Git。

## 七、实现要求

### 7.1 五区主壳结构

按 OPC-01 已确认方向，将 GUI 主壳调整为五区：

1. 顶栏：全局年份、阶段、当前玩家、国库、派系金库等摘要。
2. 左导航：七阶段导航，顺序固定为 `天命-收入-广场-人口-元老院-战争-决算`。
3. 中栏：公告区 + 阶段内容容器 + 子阶段面板区域。
4. 右面板：当前阶段状态、当前玩家/权限、结构化反馈、日志摘要。
5. 底栏：12 个全局查询按钮。

现有天命、人口、元老院只读页面必须能继续显示，不得因主壳调整退化。

### 7.2 阶段容器

阶段容器应支持：

- 已实现阶段显示真实页面。
- 未实现阶段显示明确 placeholder。
- placeholder 必须说明该阶段由后续任务承接。
- 不得伪装为已完成业务闭环。
- 点击阶段导航只能改变 GUI selected phase，不得执行 Core 阶段业务。

### 7.3 公告区

中栏顶部应提供公告区，用于承载：

- 当前阶段标题
- 当前阶段简要说明
- 当前阶段状态
- 当前阶段是否可操作
- 未实现阶段的后续任务提示

公告区仅展示 SessionStore / session snapshot / 当前阶段 view 的结构化数据，不得复制业务规则。

### 7.4 右侧状态/日志面板

右侧面板应至少支持：

- 当前选中阶段
- 当前权威阶段
- 当前玩家 / 当前 viewer
- 玩家是否有权限操作
- 最近反馈消息
- 轻量 UI 日志或操作结果摘要

日志/反馈只记录 GUI 层操作结果与 API 返回摘要，不得吞掉 API `errors`。

### 7.5 底部 12 查询按钮策略

底部 12 查询按钮第一轮允许「已接入 / 只读 / 占位」混合。

优先级如下：

1. 游戏状态
2. 派系信息
3. 战争列表
4. 军团状态
5. 其余占位

本轮最低要求：

- 底栏 12 个按钮视觉位置完整。
- `游戏状态` 优先接入 `game_api.get_status_summary()` 或 session snapshot 中已有安全摘要。
- `派系信息` 优先接入 `faction_api.get_factions_status()`，但不得泄露其他玩家私有资金或非公开信息。
- `战争列表` 如无专用 API，可先显示来自现有安全摘要或占位，不得读取 WarSystem 私有字段。
- `军团状态` 如无专用 API，可先显示占位，不得读取 MilitarySystem 私有字段。
- 其余按钮可以是明确标记的 placeholder。

底栏按钮点击后应通过右侧面板、弹窗或中栏轻量面板展示结果。具体展示形式由 CGT-01 在现有 QML 风格内保守实现。

### 7.6 i18n 硬约束

所有新增 UI 文案必须通过 `GuiText.get("key")` 或现有等价集中调用。

允许的等价集中调用包括：

- `GuiText.qml` 中的集中属性
- `GuiText.qml` 中的集中函数
- `localization.py` 中稳定 key
- 后续可迁移到 JSON 语言包的稳定 key 机制

禁止：

- 在 QML 新增行内中文字符串。
- 在 QML 新增行内英文 UI 文案。
- 在 Python GUI 层新增散落 UI 文案。
- 在按钮、标题、提示、placeholder、日志文本中硬编码字符串。

如果 CGT-01 修改了已有包含行内字符串的区域，应优先迁移到集中层。

### 7.7 API/Adapter 边界

必须保持：

```text
GUI/QML -> GuiSessionStore -> GuiApiAdapter -> API -> Core/System/Service -> Entity
```

本轮允许 `GuiApiAdapter` 新增只读 wrapper。

本轮不允许新增复杂写操作 wrapper。

如某个信息当前没有安全 API，必须先占位，不得从 GUI 层绕过。

## 八、测试要求

CGT-01 至少执行并报告以下测试：

### 8.1 GUI 重点测试

```powershell
cd "C:\Users\Kerl\PycharmProjects\Eagle of Rome"
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
```

必须覆盖：

- QML root 能启动。
- 五区主壳关键对象可定位。
- 阶段导航顺序不变。
- 天命/人口/元老院页面仍可显示。
- 未实现阶段显示 placeholder。
- 底部查询按钮存在且不会执行复杂业务动作。
- 新增文案集中到 GuiText/localization。

### 8.2 API/Session 相关测试

如修改 `session_api.py` 或 `api_adapter.py`，必须执行相关测试，例如：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_session_api.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_adapter.py" -q
```

### 8.3 回归测试

必须执行全量测试并报告结果：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

### 8.4 静态扫描

必须执行并报告：

```powershell
git diff --check
```

并执行边界扫描，确认 GUI 未新增以下调用：

```text
game_api.execute_phase
game_api.execute_turn
CombatCommand
phase_senate
phase_forum
phase_revenue
phase_combat
```

必须执行 i18n 硬编码扫描，确认新增/修改 QML 中除 `qml/i18n/GuiText.qml` 外，没有新增 UI 文案硬编码。若存在历史遗留硬编码，应在报告中区分“本轮新增”与“历史遗留”。

## 九、验收标准

SA 将按以下标准验收：

| 类别 | 验收标准 |
| --- | --- |
| 主壳结构 | 顶栏、左导航、中栏、右面板、底栏五区可见且结构稳定 |
| 阶段顺序 | 仍为 `天命-收入-广场-人口-元老院-战争-决算` |
| 现有功能 | 天命、人口、元老院只读页面不退化 |
| 底部按钮 | 12 查询按钮存在，优先级入口按要求处理，未接入项明确占位 |
| 架构边界 | GUI 不调用 CLI Command，不调用 `execute_phase()` / `execute_turn()`，不绕过 API |
| 权限隔离 | 不展示未经 API/SessionStore 过滤的私有信息 |
| i18n | 新增 UI 文案集中到 `GuiText.get("key")` 或等价集中调用 |
| 测试 | CGT-01 报告中 GUI 测试、相关 API/Session 测试、全量测试通过 |
| 交付 | 开发验收报告完整，未提交 Git |

## 十、CGT-01 交付格式

CGT-01 完成后，请输出开发验收报告并归档到：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03A OPC主壳骨架落地 开发验收报告 - CGT-01.md
```

报告必须包含：

```text
Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED / RETURN_FOR_SCOPE_CONFIRMATION

代码基线:

修改文件:

实现摘要:

五区布局完成情况:

底部 12 查询按钮完成情况:
- 游戏状态:
- 派系信息:
- 战争列表:
- 军团状态:
- 其余占位:

i18n 集中化说明:

API/Adapter 边界说明:

未接入内容说明:

测试结果:
- test_gui:
- test_session_api / test_adapter:
- full src/tests:
- git diff --check:
- 边界扫描:
- i18n 硬编码扫描:

已知风险:

需要 SA/项目负责人确认的问题:
```

CGT-01 不得提交 Git。Git 归档由 SA 在项目负责人手工验证通过后执行。
