# GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 PM任务意图包

- 日期：2026-07-05
- 发布方：项目经理 PM
- 接收方：系统架构师 SA-01
- 后续执行方：CGT-01（由 SA 定稿技术任务书后发布）
- 优先级：P0
- 任务类型：GUI 查询能力补齐 / API-Adapter 边界收束 / DTO 与权限过滤
- 代码与文档根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- 当前基线：`e4754b0 Update PM progress for GUI-P0-03A closeout`

## 一、背景说明

`GUI-P0-03A OPC主壳骨架落地` 已完成并归档，OPC 五区主壳、底部查询栏和查询浮窗已经成为后续 GUI 的结构基线。但底部 12 个查询按钮仍处于分批接入状态：游戏状态已接入，派系信息/战争列表只读，军团状态及其余查询占位。

PM 判断：下一步不应直接进入元老院或广场复杂动作，而应先补齐 `GuiApiAdapter` 与 `GuiSessionStore` 的第一批全局只读查询能力，形成安全、统一、可复用的数据入口。这样后续 Senate / Forum / Combat / Revenue 页面都能复用查询 DTO 和权限过滤规则。

## 二、任务目标

请 SA 先进行技术边界审查，并据此向 CGT-01 发布小范围技术任务书。目标是完成 `GUI-P0-03B GuiApiAdapter 第一批增量与全局只读查询`：

1. 补齐底部查询按钮第一批真实/只读数据入口。
2. 统一 `GuiApiAdapter` 的只读查询返回结构，避免 QML 直接理解 Core 对象。
3. 明确哪些查询可以本轮接入，哪些继续占位。
4. 保持多玩家信息隔离，不裸显他派金库、人物私产、隐藏决策信息。
5. 不引入任何阶段复杂业务动作，不推进阶段，不修改 Core 规则。

## 三、依据文档

请 SA 优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03A OPC主壳骨架落地 PM闭环记录.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_UI_API_Mapping.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\GUI_Code_Alignment_Audit.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

建议审查代码：

- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/` 下底部查询栏、查询浮窗、主壳相关 QML
- `src/api/session_api.py`
- `src/api/game_api.py`
- `src/core/game_state.py`
- `src/core/systems/war_system.py`
- `src/core/systems/military_system.py`
- `src/core/systems/naval_system.py`
- `src/core/entities/contract.py`
- 相关 GUI/API 测试

## 四、PM 初步范围建议

### 4.1 本轮优先接入或补强

| 查询按钮 | PM 建议状态 | 说明 |
|---|---|---|
| 游戏状态 | 补强/保留真实接入 | 已有 `get_game_status_summary()`，03B 可统一返回结构和展示 DTO。 |
| 派系信息 | 真实只读接入 | 只展示本派系安全信息与公开派系概览，禁止泄露他派私有资源。 |
| 战争列表 | 真实只读接入 | 展示活跃/已解决战争摘要，不执行战斗，不调用 CombatCommand。 |
| 军团状态 | 真实只读或结构占位升级 | 优先接入可安全读取的军团摘要；如 API 不稳，SA 可要求只读 DTO 边界先行。 |
| 人物查询 | 只读接入或延后 | 仅展示本派系人物或公开字段，禁止暴露隐藏/私有资产。 |
| 派系金库 | 本派系只读 | 仅显示 viewer 所属派系。 |
| 公地信息 | 只读接入或占位 | 可展示公共土地总量/可认购额度，不执行交易。 |
| 私地信息 | 谨慎接入 | 仅本派系/本人可见，若权限边界不清则延后。 |
| 合同状态 | 占位或只读 DTO 边界审查 | 不要求本轮新增完整 contract_api。 |
| 行省信息 | 占位或公开只读 | 不做总督任命动作。 |
| 舰队状态 | 占位或只读摘要 | 不做海战或舰队调度动作。 |
| 帮助 | 静态占位 | 必须走 GuiText/localization。 |

### 4.2 本轮明确不做

- 不做元老院提案、表决、否决、结算。
- 不做广场招募、竞标、买地、凯旋投票或土地交易。
- 不做战争发动进攻、战斗结算或停战草案生成。
- 不做收入结算确认或决算推进。
- 不做完整 i18n 语言包，但新增文案必须集中管理。

## 五、允许修改范围

SA 可在技术任务书中允许 CGT-01 修改以下范围：

- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/` 中底部查询按钮、查询浮窗、主壳相关 QML
- 必要的 `src/api/session_api.py` 或 `src/api/game_api.py` 只读查询接口
- 必要的轻量 DTO 辅助函数，但不得把业务规则写进 GUI 层
- `src/tests/test_gui/`、`src/tests/test_api/` 中相关测试
- 必要的项目文档/开发验收报告

如果 SA 判断需要新增 `query_api.py` 或专门的只读 `gui_query_api.py`，请先在边界审查中说明理由、接口形态和风险，再决定是否纳入本轮。

## 六、禁止事项

- 不得让 QML 直接访问 Core 对象、私有字段或系统实例。
- 不得让 GUI 直接调用 CLI Command、`game_api.execute_phase()`、`game_api.execute_turn()` 或 `CombatCommand`。
- 不得在 GUI 层实现或复制核心业务规则。
- 不得执行阶段推进、战斗结算、收入结算、元老院动作、广场交易等任何状态改变型玩法动作。
- 不得为了查询方便暴露他派金库、人物私产、隐藏投票/竞标信息或未公开战争细节。
- 不得把 OPC HTML 原型中的 mock 数据作为真实数据源。
- 不得新增 P1 新玩法或调整 Core 规则。
- 不得做无关格式化或大范围重构。

## 七、实现要求

SA 技术任务书应要求 CGT-01 至少满足：

1. 所有查询从 `GuiSessionStore -> GuiApiAdapter -> API/session snapshot` 获取，不绕过 Adapter。
2. 每个查询结果返回稳定 DTO，QML 不直接依赖实体对象。
3. 查询结果应适配 `QueryResultOverlay.qml` 或 03A 已落地的查询浮窗机制。
4. 查询失败时应显示结构化错误反馈，不污染状态。
5. 权限过滤必须以 `viewer_id` / `viewer_faction_id` 为依据。
6. 新增 UI 文案必须通过 `GuiText.get("key")` 或等价集中调用；不允许行内字符串硬编码。
7. 对仍占位的按钮，应显示明确的集中化文案，例如“暂未接入”，但不得使用散落硬编码。
8. 保留 03A 主壳布局与 R1 浮窗交互方式，不退回右侧常驻查询结果区。

## 八、测试要求

请 SA 要求 CGT-01 至少执行并报告：

- `src\tests\test_gui -q`
- `src\tests\test_gui\test_adapter.py -q`
- `src\tests\test_gui\test_session_api.py -q` 或当前对应 session/query 测试
- 新增或更新针对全局查询 DTO、权限过滤、占位按钮的 GUI/Adapter 测试
- 若新增 API：对应 `src\tests\test_api` 测试
- `git diff --check`
- 必要时 full `src\tests -q`

SA 验收时应额外扫描：

- 是否存在 GUI/QML/Adapter 调用 CLI Command、`execute_phase`、`execute_turn`、`CombatCommand`。
- 是否存在新增 UI 文案硬编码。
- 是否存在跨派系私有信息泄露。

## 九、验收标准

本任务通过标准：

1. 底部查询按钮第一批真实/只读能力可用，至少应明确覆盖游戏状态、派系信息、战争列表、军团状态中的可安全部分。
2. 其余按钮允许继续占位，但占位状态必须一致、可理解、集中化文案。
3. 查询浮窗继续使用 03A/R1 交互方式，不破坏主壳布局。
4. GUI 查询路径保持 `QML -> GuiSessionStore -> GuiApiAdapter -> API/Session snapshot`。
5. 未新增任何状态改变型业务动作。
6. 权限过滤和多玩家信息隔离不退化。
7. 测试通过，SA 验收结论至少为 `CONDITIONAL_PASS` 且无代码返工项。

## 十、交付物

请 SA 后续要求 CGT-01 提交：

- 修改文件清单
- 实现摘要
- 查询按钮接入状态表
- DTO/权限过滤说明
- 测试命令与结果
- 已知限制与后续建议
- 是否需要项目负责人手工 GUI 验证

## 十一、SA 期望回执格式

请 SA 按以下格式回执 PM：

```text
Decision: READY_FOR_TECH_TASK / RETURN_FOR_PM_CLARIFICATION / DEFER

Reasons:

Files reviewed:

Recommended GUI-P0-03B scope:

Query button implementation matrix:

Required API/DTO boundaries:

Information isolation rules:

Forbidden implementation paths:

Required tests:

Risks:

CGT-01 task dispatch status:
```