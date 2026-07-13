# EOR GUI QML 重建补充规范 - v3.25.1

生成日期：2026-07-10  
适用项目：Eagle of Rome  
适用范围：MVP 0.9 GUI B 路线重建阶段  
主基线文档：`EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md`  
目标原型：`EOR_GUI_Prototype_v3.25.1.html`  

## 1. 文档定位

本文件是 `EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md` 的工程落地补充，不替代原设计规范。

原 baseline 负责回答：

- EOR GUI 应该呈现什么产品形态。
- 五区布局、视觉层级、材质体系和交互原则是什么。
- 人工验收时应看哪些体验结果。

本补充规范负责回答：

- v3.25.1 HTML 如何映射到 QML 组件。
- B 路线下哪些连接层必须保留，哪些 QML 层可以重建。
- 新 QML 组件的职责边界是什么。
- Theme、状态、权限、错误、空状态如何统一。
- OC 后续实现时如何避免再次形成“边写边改、逻辑混入界面”的技术债。

## 2. B 路线实施边界

后续 GUI 改造采用 B 路线：

> 保留启动入口、Adapter、Store 等连接层，重建 QML 页面与组件。

### 2.1 必须保留

| 层级 | 对象 | 要求 |
| --- | --- | --- |
| 应用入口 | `GuiApp` / `src/ui/gui/app.py` | 保留启动、QML engine、context property 注入方式 |
| 状态容器 | `GuiSessionStore` / `src/ui/gui/session_store.py` | QML 只能通过 Store 读取状态和调用 Slot |
| API 适配 | `GuiApiAdapter` / `src/ui/gui/api_adapter.py` | 保留统一 API 调用、成功/失败/异常映射 |
| API / DTO | `src/api/` | 作为 GUI 唯一后端能力来源 |
| i18n | `localization.py` / `GuiText.qml` | 所有新增 QML 文案必须走集中 key |
| 测试入口 | `src/tests/test_gui/` | 作为重建期最低保护线 |

### 2.2 可以重建或大改

| 层级 | 对象 | 要求 |
| --- | --- | --- |
| Shell | `GameShell.qml` | 保持五区职责，重建视觉和布局细节 |
| 顶栏 | `TopStatusBar.qml` | 重建为深朱红饱满 HUD |
| 阶段导航 | `PhaseRail.qml` | 重建为 44px 阶段导航与 hover 标签 |
| 中央阶段区 | Stage container / stage pages | 重建为象牙白桌面 + 羊皮纸事务卡 |
| 右侧栏 | `ContextPanel.qml` / feedback components | 保留信息职责，重做视觉 |
| 底部查询栏 | `BottomQueryBar.qml` | 保留 12 查询入口，重做 HUD 视觉 |
| 弹窗 | Overlay / Modal | 统一深朱红标题栏、羊皮纸内容区、铜金边框 |
| 基础组件 | Button / Card / Table / EmptyState | 可保留概念，重建样式和状态表现 |

### 2.3 禁止新增路径

新 QML 不得新增以下路径：

```text
QML -> Core
QML -> CLI Command
QML -> game_api.execute_phase()
QML -> game_api.execute_turn()
QML -> Python 私有字段
QML -> 中文文本判断业务逻辑
```

唯一允许的方向：

```text
QML
↓
GuiSessionStore Property / Slot
↓
GuiApiAdapter
↓
API
↓
Core / System / Service
↓
Entity
```

## 3. HTML 到 QML 的映射规范

OC 在实现前必须先完成 `GUI_CONTROL_MAPPING_MATRIX.md`。后续编码时应按下表建立稳定映射：

| v3.25.1 HTML 区域 | QML 组件建议 | 数据来源 | 交互入口 | 验收重点 |
| --- | --- | --- | --- | --- |
| 顶栏 Logo / 年份 / 回合 | `TopStatusBar.qml` | `sessionStore` 全局属性 | 无或只读 | 信息短句化、HUD 饱满、不承载复杂操作 |
| 顶栏国库 / 当前玩家 / 阶段 | `TopStatusBar.qml` | `sessionStore.snapshot` 或派生属性 | 无 | 数值清楚、权限不泄露 |
| 左侧 7 阶段导航 | `PhaseRail.qml` | `sessionStore.phaseItems` / selected phase | `sessionStore.selectPhase()` | 当前、已完成、锁定、只读状态明确 |
| 中央阶段标题 | `StageHeader.qml` 或阶段页内 header | 当前阶段 DTO / Store | 无 | 阶段名、说明、状态短句化 |
| 中央阶段对象卡 | `ParchmentCard.qml` / 阶段专用组件 | 阶段 DTO | 阶段 Slot | 羊皮纸卡片，信息可扫描 |
| 中央阶段主操作 | `ActionButton.qml` | Store enabled/disabled/action result | Store Slot | 动作与推进分离 |
| 右侧派系状态 | `ContextPanel.qml` | viewer 过滤后的 DTO | 无 | 不暴露隐藏玩家信息 |
| 右侧日志 | `FeedbackPanel.qml` | Store feedback / event list | 无 | 解释最近事件，不替代主结果展示 |
| 底部 12 查询 | `BottomQueryBar.qml` | query config + Store | `sessionStore.doGlobalQuery()` | 只读，不改变游戏状态 |
| 查询浮窗 | `QueryResultOverlay.qml` | query result DTO | close only | 可读、可关闭、不遮挡永久状态 |
| 玩家交接 | `PlayerHandoffOverlay.qml` | Store handoff state | confirm Slot | 多玩家手动模式不退化 |

## 4. QML 组件职责边界

### 4.1 Shell 组件

`GameShell.qml` 只负责五区布局和全局结构，不写阶段业务逻辑。

允许：

- 布局顶栏、左栏、中央区、右栏、底栏。
- 根据 selected phase 装载对应阶段组件。
- 传递 Store 状态给子组件。

禁止：

- 判断具体阶段规则。
- 判断按钮权限。
- 直接调用 API。
- 根据中文阶段名选择业务逻辑。

### 4.2 TopStatusBar

`TopStatusBar.qml` 只展示全局只读状态。

必须展示或预留：

- 当前年份 / 回合。
- 当前玩家。
- 当前阶段。
- 国库或全局财政摘要。
- 其他经 Mapping 确认为 Existing 的全局状态。

禁止：

- 放置阶段核心操作。
- 展示未经 viewer 过滤的其他玩家隐藏资产。
- 用长段说明占据顶栏。

### 4.3 PhaseRail

`PhaseRail.qml` 负责阶段导航和阶段状态显示。

必须支持：

- 7 阶段固定顺序。
- 当前阶段。
- 已完成阶段。
- 未解锁阶段。
- 可查看但不可操作阶段。
- hover 标签或等价名称提示。

允许调用：

- `sessionStore.selectPhase(phaseId)`。

禁止：

- 直接推进阶段。
- 根据阶段中文名判断是否可操作。
- 自行推断阶段完成状态。

### 4.4 ContextPanel

`ContextPanel.qml` 负责右侧辅助判断。

可包含：

- 当前派系状态。
- 权限提示。
- 当前阶段提示。
- 事件日志。
- 流程控制入口，如果该入口已经由 Store 明确暴露。

禁止：

- 承载大型阶段主表格。
- 承载查询结果常驻内容。
- 替代中央阶段区完成主要操作。

### 4.5 BottomQueryBar

`BottomQueryBar.qml` 负责 12 个全局只读查询入口。

必须：

- 固定位置。
- 只读。
- 不改变游戏状态。
- 对未实现查询显示 disabled 或 placeholder reason。
- 调用统一查询 Slot，不直接访问 API。

### 4.6 Stage 页面

每个阶段页面只负责本阶段展示和本阶段操作。

阶段页面必须遵守：

- 从 Store 或阶段 DTO 读取数据。
- 通过 Store Slot 发起动作。
- 不复制 Core 规则。
- 不自行判断权限。
- 不直接修改状态。
- 动作执行后先展示结果，再允许进入下一阶段。

建议阶段页面分层：

```text
StageHeader
DecisionSummary
PrimaryObjects / Cards / Tables
ActionArea
ResultPanel
NextStepArea
```

## 5. Theme Token 规范

后续 QML 不应散落硬编码颜色。应在 `Theme.qml` 或等价主题对象中定义稳定 token。

建议 token：

| Token | 用途 | 参考色 |
| --- | --- | --- |
| `shellBackground` | 应用深墨外壳 | `#15120E` |
| `shellPanel` | 侧栏、右栏深色面板 | `#1F1812` |
| `hudRed` | 顶栏、底栏、主 HUD | `#6B1C00` |
| `hudRedHover` | HUD hover | `#7B220E` |
| `stageDesktop` | 中央象牙白桌面 | `#F1EDE3` |
| `stageDesktopAlt` | 中央区弱分层 | `#F3EEE4` |
| `parchmentCard` | 羊皮纸卡片 | `#FBF3DF` |
| `parchmentCardAlt` | 次级卡片 | `#FFF7E8` |
| `goldBorder` | 铜金边框 | `#B99145` |
| `goldHighlight` | 当前状态、高亮 | `#D9AF63` |
| `goldText` | 强调文字 | `#F2D590` |
| `dangerRed` | 危险操作 | `#8B1A12` |
| `successGreen` | 成功反馈 | `#3F6B3A` |
| `warningOchre` | 警告反馈 | `#A86D24` |
| `disabledBg` | 禁用背景 | `#5C554B` |
| `disabledText` | 禁用文字 | `#A9A196` |
| `bodyTextDark` | 浅底正文 | `#2A241B` |
| `bodyTextLight` | 深底正文 | `#F7EBD2` |
| `mutedText` | 次要说明 | `#8C7D68` |

规则：

1. QML 中新增颜色优先引用 Theme token。
2. 若确需新增颜色，先补充 Theme token，再使用。
3. 禁止在阶段页面内散落大量 `#RRGGBB`。
4. 状态颜色必须跨组件一致。

## 6. 状态展示统一矩阵

所有 Action 控件必须支持以下状态，不得只实现 enabled / disabled 两态。

| 状态 | UI 表现 | 数据来源 | 必须说明 |
| --- | --- | --- | --- |
| Ready | 主按钮可点击，铜金或朱红强调 | Store enabled rule | 当前动作名称 |
| Disabled | 降低对比度，不可点击 | Store / DTO disabled reason | 禁用原因 |
| Loading / Executing | 按钮锁定，显示执行中 | Store action state 或本地瞬态 | 不允许重复点击 |
| Success | 结果摘要显示在阶段主区 | action result DTO | 主要影响 |
| Error | 错误提示可见 | API errors / message | 失败原因 |
| Empty | 空状态组件 | DTO empty data | 为什么为空、下一步是什么 |
| Deferred | 占位但不可操作 | Mapping 标记 | 后续任务接入 |

阶段页面验收时必须检查：

- 禁用按钮是否有 reason。
- 空表格是否有 empty state。
- API 失败是否有 error state。
- 成功结果是否在中央主区可见，而不是只进日志。
- 操作中是否避免重复提交。

## 7. i18n 与文案 key 规范

新增 QML 文案必须走集中 key。

建议 key 命名：

| 类型 | 格式 | 示例 |
| --- | --- | --- |
| 阶段名 | `phase.<id>.name` | `phase.mortality.name` |
| 阶段说明 | `phase.<id>.description` | `phase.mortality.description` |
| 操作按钮 | `action.<domain>.<name>` | `action.mortality.execute` |
| 禁用原因 | `disabled.<domain>.<reason>` | `disabled.turn.notCurrentPlayer` |
| 空状态 | `empty.<domain>.<case>` | `empty.senate.noProposals` |
| 错误标题 | `error.<domain>.<case>` | `error.api.callFailed` |
| 查询入口 | `query.<id>.title` | `query.wars.title` |
| 状态标签 | `status.<name>` | `status.currentPlayer` |

禁止：

- 在 QML 中新增散落中文硬编码。
- 根据中文文案判断业务逻辑。
- 让 DTO 返回长中文文本后由 QML 再解析含义。

## 8. Layout 与响应式约束

后续 QML 重建至少以以下窗口尺寸验收：

| 尺寸 | 目标 |
| --- | --- |
| 1280x720 | 不遮挡核心操作，底部 12 查询不溢出 |
| 1366x768 | 默认可玩尺寸，五区布局稳定 |
| 1920x1080 | 不过度空旷，中央区信息仍聚焦 |

约束：

1. 顶栏、左栏、右栏、底栏尺寸应稳定，不随内容大幅跳动。
2. 中央阶段区应优先获得可用空间。
3. 长文本必须换行或截断，不得压坏按钮和卡片。
4. 查询浮窗不得遮挡顶栏关键状态和底部查询栏关闭路径。
5. 阶段导航不得因 hover 改变主布局宽度。

## 9. Mapping 先于实现

任何 QML 组件开始编码前，必须能在 `GUI_CONTROL_MAPPING_MATRIX.md` 中找到对应条目。

实现前置检查：

| 检查项 | 要求 |
| --- | --- |
| GUI Element | 已登记 |
| Type | 已分类 |
| Data Source | 已确认 |
| API / Adapter | 已确认或标记 Gap |
| Phase Rule | 已确认 |
| Permission Rule | 已确认 |
| Enabled Rule | 已确认 |
| Disabled Reason | 已确认 |
| Empty/Error State | 已确认 |
| Backend Status | 已分类 |

如果某控件没有 Mapping 条目，不得实现为可操作控件。

## 10. 第一个 Vertical Slice：天命阶段

除非 `GUI_PHASE_INTEGRATION_PLAN.md` 提出更强理由，第一阶段 Vertical Slice 默认选择天命阶段。

天命阶段适合作为第一片的原因：

- API 和 Adapter 已相对完整。
- 业务流程短。
- 可验证动作与推进分离。
- 可验证结果展示、日志反馈、disabled reason。
- 可验证新视觉体系在阶段页内的落地。

天命 Vertical Slice 最低闭环：

1. 玩家进入天命阶段。
2. 顶栏、阶段导航、右侧栏显示当前阶段和当前玩家。
3. 中央区显示天命说明、可执行动作、结果区域。
4. 点击执行天命后停留本页。
5. 天命结果以羊皮纸事务卡或结果摘要展示在中央区。
6. 日志同步记录事件。
7. 执行后出现进入下一阶段入口。
8. 非当前玩家或错误阶段时按钮禁用并说明原因。
9. API 失败时显示错误状态。
10. CLI、自动模式、多玩家权限不退化。

## 11. 验收补充

新 QML 组件验收除原 baseline 的视觉标准外，还必须检查：

| 类别 | 验收问题 |
| --- | --- |
| 架构 | 组件是否只通过 `sessionStore` 读写？ |
| 状态 | enabled / disabled / loading / success / error / empty 是否完整？ |
| 权限 | 是否显示当前玩家和不可操作原因？ |
| 信息隔离 | 是否只展示 viewer 可见信息？ |
| i18n | 是否无新增散落中文硬编码？ |
| Theme | 是否引用 Theme token，而不是散落颜色？ |
| 可回归 | 是否保留或更新了 QML 启动测试 objectName？ |
| 体验 | 1280x720、1366x768、1920x1080 是否可用？ |

## 12. 决策记录

1. 原设计 baseline 保持稳定，不直接改写为工程规范。
2. 本补充文档专门服务 B 路线 QML 重建。
3. OC 后续实现必须先完成 Mapping / Gap / Plan。
4. 新 Shell 与天命 Vertical Slice 的编码必须在顾问审阅三份对齐文件后开始。
5. 若 Mapping 发现 DTO/API 缺口，不得在 QML 中用假数据或硬编码绕过。

## 13. 一句话原则

QML 重建不是把 HTML 逐像素搬进项目，而是用稳定组件、明确状态和正确 API 边界，把 v3.25.1 的产品体验落成可维护的游戏界面。
