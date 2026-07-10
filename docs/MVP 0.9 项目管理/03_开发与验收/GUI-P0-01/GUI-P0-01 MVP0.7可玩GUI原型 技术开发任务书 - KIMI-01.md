# GUI-P0-01 MVP0.7 可玩 GUI 原型技术开发任务书

发布日期：2026-06-25

发布角色：系统架构师 SA-01

开发执行者：KIMI-01（外部非 Codex Agent）

交接方式：由项目负责人人工传递和收回

任务类型：GUI 基础架构 / 可玩垂直切片

优先级：P0.5 / P1 前置

代码基线：Git HEAD `6cc972e`

代码根目录：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## 一、任务目标

基于当前 MVP 0.7 Python 游戏代码，建立 Windows 单机 GUI 的第一套可扩展生产骨架，并交付一个完全不依赖 CLI 的真实可玩垂直切片：

> 人口阶段“庆典 + 公职投票 + 多玩家交接 + 选举结果”。

本任务必须同时完成：

1. PySide6 + Qt Quick/QML GUI 启动入口。
2. 可复用的 GameShell、导航、阶段容器、状态区、反馈区和玩家交接遮罩。
3. GUI 到标准 API 的统一适配机制。
4. 按当前玩家过滤的 GUI 安全状态 DTO。
5. 真实 Population API 庆典和投票闭环。
6. 操作后从权威 `GameState` 重新刷新界面。
7. 多玩家权限和信息隔离。
8. 可复用 GUI 测试骨架、截图和测试报告。

不得只交付静态页面、假数据演示或跳转 CLI 的按钮。

## 二、背景说明

架构收口 Sprint 已完成，当前 Core、System、Service 和主要玩家操作 API 已具备 GUI 接入基础。但现有 `game_api.execute_phase()` 仍反向调用 CLI Command，并通过 `input()`、`print()` 和 `stdout` 捕获组织阶段交互，不能作为 GUI 主入口。

项目采用：

```text
增量 GUI 接入
-> 每个 P1 玩家功能同步交付最小 GUI
-> GUI-P1-02 最终完成完整迁移与产品化收尾
```

GUI-P0-01 的职责是建立后续 P1 功能可复用的骨架并证明真实游戏操作能够沿以下方向闭环：

```text
QML GUI
-> GUI Controller / Adapter
-> API
-> Core / System / Service
-> Entity
```

## 三、已确认界面风格

Style confirmation：方案 A“共和国议事厅”

### 视觉关键词

```text
克制、权力、秩序、战术桌、青铜、暗红、中高信息密度
```

### 色彩令牌

| 用途 | 目标色 |
| --- | --- |
| 应用背景 | `#121512` |
| 一级表面 | `#181B18` |
| 二级表面 | `#20241F` |
| 三级表面 | `#282D27` |
| 边界 | `#3C443C` |
| 强边界 | `#5A6558` |
| 主强调 | `#8F3438` |
| 主强调深色 | `#68272B` |
| 青铜辅助色 | `#B69355` |
| 青铜高亮 | `#D0B170` |
| 正文 | `#EEEAE1` |
| 次级正文 | `#A9AEA5` |
| 弱化正文 | `#757C74` |
| 成功 | `#70A17C` |
| 警告 | `#C4933D` |
| 错误 | `#C45151` |
| 信息 | `#6C8FA1` |

允许为对比度做小幅调整，但不得改变整体暗色、暗红和青铜方向。

### 字体与密度

- 页面标题优先使用项目可合法分发的中文衬线字体；无法打包字体时使用系统 `SimSun`/等价衬线 fallback。
- 正文、按钮、表格和数字使用 `Microsoft YaHei UI`/`Noto Sans SC`/系统无衬线 fallback。
- 不得使用负字距。
- 页面标题约 22–26 px。
- 面板标题约 12–14 px。
- 正文约 11–13 px。
- 表格行高约 40–52 px。
- 中高信息密度，但文本不得拥挤、裁切或重叠。

### 罗马题材表达

- 可使用小型 SPQR 印章、青铜细线、暗红标记、桂冠或鹰徽等身份提示。
- 使用本地、许可清晰的视觉资产。
- 不得从网络运行时加载字体、图标或图片。
- 不得使用大面积羊皮纸、石柱边框、浮雕按钮或地图占据主操作区。
- 不得将地图作为本任务主布局。

### 参考材料

- 风格确认记录：

  `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 界面风格确认记录.md`

- 方案 A HTML 交互参考：

  `E:\Eagle of Rome\EOR_GUI_Prototype_Scheme_A.html`

- 方案 A 参考截图：

  `E:\Eagle of Rome\EOR_GUI_Prototype_Scheme_A_1440.png`

HTML 仅用于视觉和交互参考，禁止直接把 HTML/JavaScript 作为生产 GUI 嵌入。

## 四、依据文档和代码

### 项目文档

- `E:\Eagle of Rome\MVP 0.9 项目管理\02_项目任务书\GUI-P0-01 MVP0.7可玩GUI原型 PM任务意图包.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 MVP0.7可玩GUI原型 派工前审查及风格方案 - SA-01.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\AI开发任务模板.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

### 重点代码

- `src/core/game_state.py`
- `src/core/scenario_loader.py`
- `src/core/entities/player.py`
- `src/api/__init__.py`
- `src/api/player_api.py`
- `src/api/game_api.py`
- `src/api/figure_api.py`
- `src/api/faction_api.py`
- `src/api/population_api.py`
- `src/ui/processors/auto_player_processor.py`
- `src/ui/commands/phase_population.py`
- `src/tests/test_api/test_population_api.py`
- `src/tests/test_commands/test_phase_population.py`

KIMI-01 必须基于完整代码基线工作，不得根据 HTML 原型自行猜测业务规则。

## 五、运行环境和依赖

### Python 基线

```text
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe
Python 3.10.6
pytest 9.0.2
```

工作目录：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

### 新增 GUI 依赖

经项目负责人批准安装后使用：

```text
PySide6==6.8.3
pytest-qt==4.4.0
```

要求新增：

`requirements-gui.txt`

内容至少包含上述两个固定版本。

本任务不要求安装或引入 PyInstaller，不执行 EXE 打包。

### 安装约束

- KIMI-01 不得默认声称依赖已安装。
- 如 KIMI-01 无法执行本地命令，应提供准确安装命令和完整测试命令，由项目负责人或 SA 执行。
- 不得修改项目现有 Python 解释器路径。
- 不得引入 Electron、Tauri、FastAPI、Flask、Django、Kivy、Flet 或其他 GUI/Web 框架。
- 不得运行时从 CDN 加载图标、字体或图片。

建议安装命令：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pip install -r "C:\Users\Kerl\PycharmProjects\Eagle of Rome\requirements-gui.txt"
```

## 六、允许修改范围

### 允许新增

```text
gui_main.py
requirements-gui.txt
src/api/session_api.py
src/ui/gui/
src/tests/test_gui/
data/scenarios/gui_prototype.json
```

`src/ui/gui/` 建议结构：

```text
src/ui/gui/
  __init__.py
  app.py
  session_store.py
  api_adapter.py
  controllers/
    __init__.py
    population_controller.py
  models/
    __init__.py
    figure_list_model.py
    candidate_list_model.py
    event_list_model.py
  qml/
    Main.qml
    shell/
      GameShell.qml
      TopStatusBar.qml
      PhaseRail.qml
      ContextPanel.qml
      FeedbackPanel.qml
      PlayerHandoffOverlay.qml
    stages/
      PopulationStage.qml
      FestivalView.qml
      VoteView.qml
      ElectionResultView.qml
      LockedStagePlaceholder.qml
    components/
      AppButton.qml
      IconButton.qml
      StatusTile.qml
      DataTable.qml
      FeedbackToast.qml
      ConfirmDialog.qml
      NumberStepper.qml
      EmptyState.qml
    theme/
      Theme.qml
    assets/
      icons/
      images/
      ATTRIBUTION.md
  README.md
```

允许按等价职责调整文件名，但必须保持模块边界清楚。

### 允许修改

仅在必要时：

- `src/api/population_api.py`
- `src/api/player_api.py`
- `src/api/__init__.py`
- 与新增 API 或 GUI 测试直接相关的既有测试文件
- `.gitignore`，仅用于新增 GUI 运行缓存或截图临时目录

### 修改范围升级规则

如果必须修改以下区域，KIMI-01 应停止并在交付报告中提出原因，不得擅自修改：

- `src/core/game_state.py`
- `src/core/systems/`
- `src/core/service/`
- `src/core/entities/`
- 现有 CLI Command
- 现有 AutoPlayerProcessor/decider
- 场景加载器生产逻辑

新增 `data/scenarios/gui_prototype.json` 可以复用现有场景加载器，不允许为 GUI 重写场景加载规则。

## 七、禁止事项

- 不得自行提交、合并、rebase 或重置 Git。
- 不得修改 `E:\Eagle of Rome` 下的历史档案作为代码交付。
- 不得只交付 HTML、截图、静态 QML 或假数据。
- 不得要求玩家切回 CLI 完成庆典、投票、玩家交接或查看选举结果。
- 不得调用 `game_api.execute_phase()` / `execute_turn()` 驱动 GUI 交互阶段。
- 不得实例化或调用 `PopulationCommand` 完成 GUI 操作。
- 不得在 GUI/QML 中实现庆典、候选资格、投票权重或选举规则。
- 不得让 QML 直接持有 `GameState`、Faction、Figure 或 System 对象。
- 不得直接修改 Core/System/Service/Entity 私有字段。
- 不得绕过 `population_api.campaign()` 和 `population_api.vote()` 执行玩家操作。
- 不得通过 `testing.bypass_player_check` 绕过 GUI 正常权限。
- 不得直接使用未过滤的全局人物/派系查询向当前玩家显示隐藏信息。
- 不得在玩家交接遮罩出现后继续保留上一玩家敏感模型。
- 不得迁移全部七阶段。
- 不得实现完整地图、远程多人、账号、服务器、手机界面或 P1 新玩法。
- 不得删除或破坏 CLI。
- 不得做无关格式化、大范围重命名或顺手重构。
- 不得引入运行时网络依赖。

## 八、应用启动和场景

### GUI 启动入口

新增：

`gui_main.py`

启动命令：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_main.py"
```

### 原型场景

新增：

`data/scenarios/gui_prototype.json`

要求：

- 基于现有场景格式，不发明第二套场景模型。
- 至少包含三个本地 HUMAN 玩家派系，确保本轮 GUI 不依赖 AI 自动编排。
- 每个派系有合法人口阶段候选人和足够测试庆典的财富。
- 固定或可控随机种子，保证 GUI 测试稳定。
- GUI 启动后通过 `ScenarioLoader.load_scenario(state, "gui_prototype.json")` 加载真实状态。
- 允许将 `forum` 标记为已完成，使 GUI 直接进入人口阶段切片。
- 不得在场景文件中写入虚假的 GUI 专用结果。

GUI-P0-01 不要求从天命阶段开始完整玩到人口阶段。

## 九、架构实现要求

### 9.1 Session API

新增 `src/api/session_api.py`，保持统一返回：

```text
{success, message, data, errors}
```

至少提供等价接口：

```python
create_gui_prototype_session(config_path=None) -> dict
get_session_snapshot(state, viewer_player_id: str) -> dict
get_population_view(state, viewer_player_id: str) -> dict
complete_population_player(state, player_id: str) -> dict
resolve_population_slice(state) -> dict
```

允许调整命名，但职责必须完整。

#### 快照要求

`get_session_snapshot()` 只返回 GUI 需要的普通字典/列表：

- 回合、年份、当前阶段。
- 当前玩家 ID、类型和派系。
- 公开国家资源摘要。
- 当前玩家自己的派系资源。
- 当前玩家自己的派系人物。
- 七阶段导航状态。
- 当前可执行动作。
- 人口阶段进度。

不得返回：

- 其他玩家派系金库。
- 其他玩家非公开人物详情。
- 可修改的内部容器。
- `GameState` 或 Entity 实例。

#### 人口视图要求

`get_population_view()` 至少返回：

- 当前玩家可操作人物及财富、人气、影响力、资格。
- 所有合法公开候选人的结构化数据。
- 当前玩家已投票的官职和候选人。
- 是否允许庆典、投票、完成当前玩家操作。
- 字段级错误或禁用原因。

### 9.2 GuiApiAdapter

`GuiApiAdapter` 统一负责：

- 调用 API。
- 验证 `success/message/data/errors`。
- 将成功、警告、错误和异常映射为结构化反馈。
- 成功操作后重新请求权威快照。
- 失败操作后保持旧状态，并可验证 Core 未被污染。
- 记录必要日志。

不得把业务规则复制到 adapter。

### 9.3 GuiSessionStore

建立唯一 GUI 会话存储：

- 内部引用唯一 `GameState`。
- QML 只能访问只读属性、列表模型和 Slot。
- 不在 QML/Store 维护第二套财富、人气、影响力、投票或当前玩家权威值。
- 每次 API 操作后从 `session_api` 重新刷新。
- 至少提供：

```text
snapshotChanged
populationViewChanged
currentPlayerChanged
phaseChanged
feedbackRaised
handoffRequired
```

等价信号。

### 9.4 玩家交接

完成当前玩家操作后：

1. 调用标准 API/Session API 完成玩家切换。
2. 立即清空上一玩家敏感模型。
3. 显示全屏玩家交接遮罩。
4. 遮罩只显示下一玩家标识，不显示其派系敏感数据。
5. 下一玩家确认后重新请求其 viewer-scoped 快照。
6. 新快照加载完成前不得显示旧数据。

### 9.5 阶段容器

七阶段导航必须存在：

```text
天命 / 收入 / 广场 / 人口 / 元老院 / 战斗 / 决算
```

本轮：

- 人口阶段为可操作真实切片。
- 其他阶段显示明确的“尚未迁移”占位状态。
- 点击其他阶段不得伪造业务结果。
- 阶段容器必须支持后续注册新的 QML 面板和 Controller。

## 十、可玩垂直切片

### 10.1 庆典

玩家能够：

1. 查看本派系可操作人物。
2. 查看财富、人气、影响力和公职资格。
3. 选择人物。
4. 输入或步进调整投入金额。
5. 取消操作。
6. 确认高影响资源操作。
7. 通过 `population_api.campaign()` 提交。
8. 成功后刷新人物财富、人气、影响力和派系总影响力。
9. 资金不足、金额非法、非当前玩家等失败时显示可修正信息，状态不改变。

### 10.2 公职投票

玩家能够：

1. 按官职切换候选人列表。
2. 查看候选人姓名、派系和资格属性。
3. 选择候选人。
4. 取消选择。
5. 确认投票。
6. 通过 `population_api.vote()` 提交。
7. 成功后显示该官职已投和已选候选人。
8. 重复投票、非法候选人和权限不足时显示错误且状态不改变。

### 10.3 完成玩家操作

- 玩家可完成当前派系操作。
- 支持三名本地 HUMAN 玩家依次交接。
- 每次交接都必须经过隐私遮罩。
- 每个玩家只能看到自己的派系资源和人物详情。

### 10.4 选举结果

- 所有 HUMAN 玩家完成后调用真实 `population_api.resolve_election()` 或受控 Session API。
- API 的 `data` 应补强为 GUI 可消费的结构化结果：

```text
office
figure_id
figure_name
faction_id
```

- GUI 显示每个官职的当选人和派系。
- 结算后从权威状态刷新人物官职和相关影响力。
- 不解析 API 的中文 `message` 来构建结果列表。

## 十一、视觉和组件规范

### GameShell 布局

设计视口：`1440 x 900`

最低视口：`1280 x 720`

| 区域 | 参考尺寸 |
| --- | --- |
| 顶部状态栏 | 64 px |
| 左侧阶段导航 | 160–184 px |
| 右侧上下文 | 296–328 px |
| 底部反馈区 | 96–112 px，可折叠 |
| 中央阶段容器 | 占剩余空间，不小于约 640 px |

### 必须组件化

- 顶部全局状态栏。
- 七阶段导航。
- 当前阶段容器。
- 当前玩家/派系状态。
- 数据表格。
- 人物/候选人列表模型。
- 数值步进器。
- 主按钮、次按钮、图标按钮。
- 成功、错误、警告反馈。
- 确认/取消弹窗。
- 空状态。
- 玩家交接遮罩。
- 结构化事件/反馈区。

不得把整个界面写入单一超大 QML 文件。

### 控件规则

- 工具操作优先使用图标按钮并提供 tooltip。
- 明确命令使用图标 + 文字按钮。
- 数字使用步进器或数值输入，不用自由文本模拟。
- 官职选择使用 tabs/segmented control。
- 高影响资源操作必须确认。
- 卡片圆角不超过 6 px。
- 不允许卡片嵌套卡片。
- 不允许装饰性渐变球、光斑或大面积渐变背景。
- 不允许控件因动态文字改变尺寸导致布局跳动。
- 长姓名和错误信息必须换行或省略并可查看完整内容。

### 图标和资产

- 使用本地打包的 Lucide 图标或 Qt 官方可分发图标。
- 不手绘重复图标。
- 如果使用 Lucide SVG，需在 `assets/ATTRIBUTION.md` 写明来源和许可。
- 可包含一个低对比度、非地图主导的罗马元老院背景图。
- 所有图片必须有明确来源、许可和本地路径。

## 十二、日志要求

沿用项目日志机制，关键事件至少记录：

- GUI 会话创建。
- API 调用失败或异常。
- 当前玩家和阶段。
- 庆典人物 ID 与金额。
- 投票官职与候选人 ID。
- 玩家交接开始和完成。
- 快照刷新失败。
- 选举结算。

日志不得记录其他玩家隐藏金库或人物私密详情。

正常渲染、鼠标移动和频繁属性绑定不得产生噪声日志。

## 十三、测试要求

KIMI-01 必须新增 `src/tests/test_gui/`。

### 环境变量

无头 GUI 测试：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
```

### 必须测试

#### Session API

- 创建真实 GUI 原型会话。
- 当前玩家快照只包含其有权查看的信息。
- 其他派系敏感数据不泄漏。
- 人口视图返回普通 DTO。
- 玩家切换前后 viewer 数据正确变化。
- 非当前玩家请求操作被拒绝。

#### API Adapter / Store

- 正确处理成功响应。
- 正确处理失败和 `errors`。
- 正确处理异常。
- 成功后刷新权威快照。
- 失败后不污染界面或 Core 状态。
- 交接时旧敏感模型先清空。

#### GUI 启动和组件

- `QQmlApplicationEngine` 成功加载 `Main.qml`。
- 根对象非空。
- GameShell、阶段导航、人口面板和反馈区存在。
- 七阶段导航顺序正确。
- 非人口阶段只显示未迁移占位。

#### 可玩闭环

- 庆典成功：财富下降，人气和影响力刷新。
- 庆典失败：资金不足，状态不变。
- 庆典取消：不调用 API。
- 投票成功：官职显示已投。
- 重复投票失败：状态不变。
- 非法候选失败。
- 玩家完成操作后显示交接遮罩。
- 交接前清除旧派系敏感信息。
- 三名 HUMAN 玩家完成后真实结算选举。
- 结果来自结构化 API data。

#### CLI 和自动模式回归

至少执行：

```text
src/tests/test_api/test_population_api.py
src/tests/test_commands/test_phase_population.py
src/tests/test_commands/test_phase_population_disband.py
src/tests/test_commands/test_phase_population_truce.py
src/tests/test_ui/test_command_framework.py
```

GUI 代码不得导致这些测试退化。

#### 全量测试

执行：

```powershell
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

### 静态检查

执行：

```powershell
git diff --check
```

并静态确认：

- QML 不直接引用或修改 Core 私有字段。
- GUI 不导入 CLI Command。
- GUI 不调用 `game_api.execute_phase()`。
- GUI 玩家操作只经 API。
- 不存在运行时 CDN 或 HTTP 资产依赖。

## 十四、截图与视觉验收材料

KIMI-01 必须提交 PNG 截图，不接受只写“界面正常”。

### 必须截图

在 `1440 x 900`：

1. GameShell + 人口阶段庆典默认页。
2. 已选择人物并填写庆典金额。
3. 庆典成功后状态刷新和反馈。
4. 公职投票候选列表和投票单。
5. 非法/重复操作错误反馈。
6. 玩家交接全屏遮罩。
7. 选举结果页。

在 `1280 x 720`：

8. GameShell + 人口阶段庆典页。
9. 公职投票页。
10. 玩家交接遮罩。

截图要求：

- 主视图非空。
- 无文字重叠、溢出或关键控件不可达。
- 无横向页面滚动。
- 当前玩家、阶段和关键资源清楚可见。
- 表格和弹窗符合已批准风格。
- 不显示调试边框或假数据标签。

建议交付目录：

`gui_delivery/screenshots/`

## 十五、验收标准

| 类别 | 验收标准 |
| --- | --- |
| 启动 | 使用指定 Python 命令启动 GUI，无 CLI 交互要求 |
| 风格 | 符合方案 A，并吸收方案 B 的表格/弹窗可读性 |
| 可玩性 | 三名本地 HUMAN 玩家可完成庆典、投票、交接和选举结果闭环 |
| 真实性 | 使用真实 GameState、ScenarioLoader 和 Population API |
| 架构 | GUI -> API -> Core；无 GUI 业务规则、无私有字段直改 |
| 状态 | 成功后从权威状态刷新；失败和取消不污染状态 |
| 权限 | 当前玩家权限正确，交接时无上一玩家敏感信息残留 |
| 可扩展性 | GameShell、阶段容器、Adapter、Store 和组件可供后续 P1 复用 |
| 测试 | GUI 测试、人口相关回归和全量 pytest 通过 |
| 视觉 | 10 张规定截图符合双视口要求 |
| CLI | 原 CLI 入口和自动模式测试不退化 |
| Git | KIMI-01 未自行提交 Git |

以下情况 SA 将建议 `RETURN_FOR_REWORK`：

- 仍需切回 CLI 完成核心操作。
- 只使用假数据或 HTML 演示。
- GUI 绕过 API。
- GUI 直接修改 Core 私有状态。
- 非当前玩家可越权或看到其他派系敏感信息。
- 状态刷新、失败回滚或交接清理错误。
- 核心 GUI 无自动测试或缺少截图。

## 十六、明确不在本轮

- 完整七阶段迁移。
- 元老院完整提案和投票 GUI。
- 广场完整 GUI。
- 完整交互式罗马地图。
- AI 玩家在 GUI 中的可视化行动编排。
- 远程多人、服务器、账号和网络同步。
- 手机和平板适配。
- 全量存档管理和存档版本迁移。
- EXE、安装器、Steam、自动更新和正式发行。
- 最终动画、音效、过场和完整视觉主题。
- GUI-P1-02 产品化收尾。
- MVP 0.9 / MVP 1.0 P1 新玩法。

## 十七、KIMI-01 交付格式

KIMI-01 是外部非 Codex Agent，交付必须完整、自包含。

### 交付方式

若不能直接修改项目目录，提交一个完整文件包：

```text
GUI-P0-01_KIMI-01_delivery/
  DELIVERY_REPORT.md
  files/
    gui_main.py
    requirements-gui.txt
    src/...
    data/...
  screenshots/
  test_output/
```

`files/` 必须保留相对于代码根目录的完整路径。

不得只交付：

- 局部代码片段。
- 省略内容的伪代码。
- 无法直接落盘的聊天描述。
- 只有 patch 而没有新增完整文件。
- 只有截图而没有代码。

### DELIVERY_REPORT.md 必须包含

```text
Decision by KIMI-01: READY_FOR_SA_REVIEW / BLOCKED

Code baseline:

Changed files:

New files:

Architecture summary:

Session/API interfaces:

GUI components:

Playable flow:

Permission and information-isolation handling:

State refresh and rollback handling:

Dependencies and exact installed versions:

Test commands:

Test results:

Screenshot inventory:

Static checks:

Known risks:

Items deferred to GUI-P1-02:

Git status:
```

### 测试输出

提交：

- GUI 聚焦测试完整输出。
- 人口回归测试完整输出。
- 全量 pytest 最终摘要。
- `git diff --check` 结果。
- 若有失败，提供完整 traceback，不得只写失败数量。

### Git 约束

- 不得执行 `git commit`。
- 不得修改已有 Git 历史。
- 不得清理或回滚非本任务修改。
- 交付报告应声明未提交 Git。

## 十八、项目负责人向 KIMI-01 的人工交接材料

项目负责人应提供：

1. 本技术任务书。
2. Git HEAD `6cc972e` 的完整代码快照。
3. 方案 A HTML 原型和 1440×900 截图。
4. PM 任务意图包。
5. P1 最小可用 GUI 标准。

建议代码快照包含：

```text
main.py
src/
data/
AGENTS.md
.agents/runtime_profile.md
```

建议排除：

```text
.git/
.idea/
Lib/
Scripts/
pyvenv.cfg
logs/
.pytest_cache/
__pycache__/
```

KIMI-01 必须确认其工作基线是 `6cc972e`。如果收到的代码与任务书不一致，应停止并报告，不得自行猜测。

## 十九、SA 验收和后续流程

1. 项目负责人将任务书和代码快照人工传递给 KIMI-01。
2. KIMI-01 按本任务书交付完整文件包和报告。
3. 项目负责人将完整交付转交 SA。
4. SA 将检查实际代码、依赖、架构、权限、视觉、截图和测试。
5. SA 独立运行 GUI 测试、相关回归和全量 pytest。
6. SA 使用桌面浏览/截图工具验证 `1440 x 900` 和 `1280 x 720`。
7. 项目负责人执行手工试玩。
8. 只有 SA 验收和项目负责人手工测试均通过后，才允许 Git 归档。

KIMI-01 不负责最终验收结论，也不得宣布任务正式完成。
