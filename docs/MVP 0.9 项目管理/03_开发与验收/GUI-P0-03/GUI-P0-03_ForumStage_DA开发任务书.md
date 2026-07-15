# GUI-P0-03 ForumStage DA开发任务书

日期：2026-07-13
任务编号：GUI-P0-03
任务名称：Phase 3 广场阶段 ForumStage GUI 真实切片
任务类型：Store/API Binding + Stage Content Implementation
优先级：P0
目标版本：EOR GUI v3.25.1

---

## 一、任务背景

Phase 1 天命、Phase 2 收入已经完成。当前 GUI Shell 与 StageDesktop 四槽位已稳定，Phase 3 需要在同一套结构中实现广场阶段。

本阶段不得推翻已稳定 Shell，不得复制业务规则到 QML。目标是在 v3.25.1 HTML 原型形态下，完成可运行、可测试、可验收的 ForumStage。

## 二、任务目标

1. 新增 `ForumStage.qml`。
2. 新增 `forum_api.get_forum_view()` 查询 DTO。
3. 在 GuiApiAdapter / GuiSessionStore 中接入 forum 查询和操作。
4. 在 GameShell 中注册 forum header、step bar、content、action。
5. 将 session_api 中 `forum` 标记为已实现交互阶段。
6. 补齐测试和开发报告。

## 三、依据文档

| 文档 | 用途 |
| --- | --- |
| `EOR_GUI_Development_Governance_v1.0.md` | GUI 不回退、截图、A-F 验收治理 |
| `EOR_GUI_SA-DA_开发任务书规范模板_v1.3.md` | GUI 任务书字段、结构归位测试要求 |
| `EOR_GUI_Prototype_v3.25.1.html` | Phase 3 视觉目标 |
| `GUI-P0-03_ForumStage_PM意图包.md` | 产品目标 |
| `GUI-P0-03_ForumStage_SA边界审查报告.md` | 允许/禁止范围 |

## 四、目标截图与当前实测截图

| 类型 | 路径/说明 |
| --- | --- |
| 目标 | v3.25.1 HTML Prototype Phase 3 |
| 当前 | Phase 2 后，Forum 仍为 placeholder/未实现状态 |
| 截图要求 | DA 报告需记录自动截图是否可读；若中文方块，只能作为布局粗验 |

## 五、允许修改范围

| 类型 | 文件 |
| --- | --- |
| 新建 | `src/ui/gui/qml/stages/ForumStage.qml` |
| 修改 | `src/api/forum_api.py` |
| 修改 | `src/api/session_api.py` |
| 修改 | `src/ui/gui/api_adapter.py` |
| 修改 | `src/ui/gui/session_store.py` |
| 修改 | `src/ui/gui/qml/shell/GameShell.qml` |
| 修改 | `src/ui/gui/localization.py` |
| 修改/新增 | `src/tests/test_gui/`、`src/tests/test_api/` |

## 六、禁止修改范围

- 禁止修改 `src/core/`。
- 禁止修改 `src/core/entities/`。
- 禁止修改 `src/core/systems/`。
- 禁止修改 `src/core/service/`。
- 禁止修改 `src/ui/gui/qml/Main.qml`。
- 禁止重排 TopStatusBar、PhaseRail、ContextPanel、BottomQueryBar。
- 禁止 QML 直接调用 `forum_api`、`game_api`、`core`。

## 七、保持项 / 允许改项 / 禁止改项 / 风险项

| 类型 | 区域 | 要求 |
| --- | --- | --- |
| 保持项 | A TopStatusBar | 保持 Phase2 后稳定布局 |
| 保持项 | B PhaseRail | 保持 7 阶段顺序；广场变为已实现但不改变样式体系 |
| 允许改项 | C StageDesktop | 添加 forum header、step、content |
| 保持项 | D ContextPanel | 使用现有阶段摘要，不重排右栏 |
| 保持项 | E BottomQueryBar | 保持 12 查询入口 |
| 允许改项 | F MainAction | 新增 forum 底部主操作按钮 |
| 风险项 | C/F | 防止内容卡片或主按钮漂移到错误容器 |

## 八、A-F 区域要求

| 区域 | 目标要求 | 验收 |
| --- | --- | --- |
| A | 顶栏不动，forum 只影响阶段数据 | 截图/结构检查 |
| B | 广场按钮可显示当前/可选状态 | 截图 |
| C | v3.25.1 广场双面板内容位于象牙桌面内 | 截图/结构测试 |
| D | 右栏显示广场当前阶段、操作、进度、玩家、日志 | 截图/人工验收 |
| E | 底部查询栏不变 | 截图/既有测试 |
| F | 主按钮底部居中，执行/完成/推进状态清晰 | 截图/结构测试 |

## 九、布局契约与槽位要求

ForumStage 只填充 StageContentSlot。不得自建平行 Shell。

GameShell 中 forum 相关内容应遵守：

| 内容 | 槽位 |
| --- | --- |
| `3 / 7` badge、标题、说明 | StageHeaderSlot |
| 公示区 -> 解雇成员 -> 人才市场步骤条 | StageInstructionSlot |
| 双面板内容 | StageContentSlot |
| 完成解雇 / 完成市场 / 推进人口主按钮 | StageActionSlot 语义位置 |

## 十、Store/API 绑定要求

新增或暴露：

| 层 | 要求 |
| --- | --- |
| `forum_api.py` | `get_forum_view(state, viewer_player_id)` |
| `api_adapter.py` | `get_forum_view`、`retire_figure`、`recruit_figure`、`place_bid`、`buy_land`、`vote_triumph`、`resolve_forum` |
| `session_store.py` | `forumView`、`forumResult`、`forumCurrentStep`、`forumMyFigures`、`forumAvailableFigures`、`forumPendingContracts`、`forumLandQuota`、`forumTriumphWars`、`canExecuteForum`、`canAdvanceForum` |
| `session_store.py` Slot | `doRetireFigure`、`doRecruitFigure`、`doPlaceBid`、`doBuyLand`、`doVoteTriumph`、`doResolveForum`、`doAdvanceForum` |

## 十一、视觉不回退要求

测试通过不等于视觉通过。DA 报告必须包含 A-F 差异表。若截图中文字不可读，必须说明“仅供布局粗验，最终文字可读性需人工本机验收”。

## 十二、测试要求

必须执行：

```text
py -3.10 -m pytest -p no:cacheprovider src\tests\test_api\test_forum_api.py -q
py -3.10 -m pytest -p no:cacheprovider src\tests\test_gui -q
py -3.10 -m pytest -p no:cacheprovider src\tests -q
```

## 十三、截图与验收证据要求

DA 报告需包含：

- 目标原型来源。
- 实测截图路径或无法生成的说明。
- A-F 差异表。
- 截图可读性说明。
- 未解决问题清单。

## 十四、验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | GUI 可启动，ForumStage 对象存在 |
| AC-02 | ForumStage 正确挂载于 `stageContainer` |
| AC-03 | forum 已在 `session_api` 标记为 implemented + interactive |
| AC-04 | Store/API 连接完整 |
| AC-05 | QML 无直接 core/API 越界调用 |
| AC-06 | forum DTO 字段完整且不泄露非 viewer 私密数据 |
| AC-07 | 完整回归通过 |

## 十五、交付物

1. 代码变更。
2. 测试结果。
3. `GUI-P0-03_ForumStage_DA开发报告.md`。
