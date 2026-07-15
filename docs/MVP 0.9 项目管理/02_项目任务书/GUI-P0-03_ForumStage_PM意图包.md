# GUI-P0-03 ForumStage PM意图包

日期：2026-07-13
状态：Ready for SA Boundary Review
执行对象：Codex
目标版本：EOR GUI v3.25.1 Phase 3 广场阶段

---

## 1. 当前判断

Phase 1 天命、Phase 2 收入已经完成并归档，GUI 主壳、StageDesktop 四槽位、TopStatusBar、PhaseRail、ContextPanel、BottomQueryBar 已形成可复用基线。

Phase 3 的任务不是重建 Shell，而是在既有 Shell / Store / Adapter 连接层上，实现 v3.25.1 HTML 原型中的广场阶段真实切片。

本阶段必须继续执行 GUI 视觉不回退治理：新增 ForumStage 不得破坏 A-F 区域既有布局。

## 2. 任务目标

实现广场阶段 GUI 闭环，包括：

| 模块 | 目标 |
| --- | --- |
| 公示区 | 显示广场阶段说明、当前玩家、当前子环节、可执行状态 |
| 解雇成员 | 展示本派系成员，允许当前玩家解雇非领袖、无活跃合同的人物 |
| 人才市场 | 展示可招募人物、可竞标合同、公地认购、凯旋投票入口 |
| Store/API 连接 | QML 只能通过 GuiSessionStore Slot 访问 GuiApiAdapter，再进入 forum_api |
| 阶段推进 | 广场结算后可推进到人口阶段 |
| 测试与留痕 | GUI startup、forum API/DTO、结构归位、完整回归、开发报告 |

## 3. 产品目标

目标形态以 v3.25.1 HTML 原型 Phase 3 为准：

- 中央象牙白桌面保持 Phase 1/2 已稳定样式。
- 顶部信息层显示 `3 / 7`、`广场阶段`、阶段说明。
- 步骤条表达：公示区 -> 解雇成员 -> 人才市场。
- 内容区采用左右双面板：
  - 左：解雇成员。
  - 右：人才市场 / 招募 / 竞标 / 认购 / 凯旋。
- 主操作按钮仍位于 StageActionSlot 底部居中，不漂移到内容中央。

## 4. 允许范围

| 类型 | 路径 |
| --- | --- |
| 新建 | `src/ui/gui/qml/stages/ForumStage.qml` |
| 修改 | `src/api/forum_api.py` |
| 修改 | `src/api/session_api.py` |
| 修改 | `src/ui/gui/api_adapter.py` |
| 修改 | `src/ui/gui/session_store.py` |
| 修改 | `src/ui/gui/qml/shell/GameShell.qml` |
| 修改 | `src/ui/gui/localization.py` |
| 修改/新增 | `src/tests/test_gui/`、`src/tests/test_api/` |

## 5. 禁止范围

| 禁止项 | 说明 |
| --- | --- |
| 不改 `src/core/` | 不修改内核规则、实体、系统、服务 |
| 不改 `Main.qml` | 不重做应用入口 |
| 不改其他阶段业务 | 不重构 Mortality / Revenue / Population / Senate |
| 不绕过 Store/API | QML 不得直接调用 forum_api、game_api 或 core 对象 |
| 不扩大视觉重构 | 不重排 TopStatusBar、PhaseRail、ContextPanel、BottomQueryBar |

## 6. 验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | `forum` 被标记为已实现交互阶段 |
| AC-02 | ForumStage 正确挂载在 `stageContainer` 内，尺寸匹配 StageContentSlot |
| AC-03 | Forum 主操作层挂载在 `centerPanel` 底部操作槽语义位置 |
| AC-04 | `get_forum_view()` 只读 DTO 能返回 my_figures、available_figures、pending_contracts、land_sale_quota、triumph_wars、can_execute、can_advance、resolved 等字段 |
| AC-05 | Store 暴露 forum 相关只读属性和 Slot |
| AC-06 | QML 启动测试通过 |
| AC-07 | forum API/GUI 专用测试通过 |
| AC-08 | `src/tests` 完整回归通过，或明确记录非本任务导致的失败 |
| AC-09 | 输出 DA 开发报告，包含修改文件、测试结果、A-F 差异表、截图可读性说明 |

## 7. 风险

| 风险 | 控制 |
| --- | --- |
| Phase 3 功能多，容易混入内核改动 | 只新增查询 DTO 和连接层，业务行为调用既有 forum_api |
| QML 页面过重导致布局回退 | 只填充 StageContentSlot，不改 Shell A-F 主结构 |
| 自动截图中文字不可读 | 截图只作为布局粗验；最终视觉仍需人工本机截图确认 |
| 多玩家子环节状态尚未有专用后端状态机 | 本阶段以当前已有玩家切换和 pending forum actions 为基础，先完成 GUI 真实入口与结算闭环 |

## 8. 下一步

进入 SA 边界审计，确认可改文件、禁改文件、接口边界与不回退清单后，再进入 DA 实现。
