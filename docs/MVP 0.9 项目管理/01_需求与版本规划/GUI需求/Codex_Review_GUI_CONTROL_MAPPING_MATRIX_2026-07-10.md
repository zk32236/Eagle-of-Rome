# Codex 审阅意见：GUI_CONTROL_MAPPING_MATRIX

审阅日期：2026-07-10  
审阅对象：`GUI_CONTROL_MAPPING_MATRIX.md`  
审阅角色：EOR GUI 开发顾问 / Codex  
结论：**有条件通过，需小范围修正后再进入 `GUI_DTO_GAP_REPORT` 与 `GUI_PHASE_INTEGRATION_PLAN`。**

## 一、总体判断

OC 本轮 Mapping 已覆盖 Shell、天命、收入、广场、人口、元老院、战争、决算 7/7 区域，并且能区分：

- 已有 Store / Adapter / API 支撑的 GUI 元素。
- 仅需 QML 重建的视觉元素。
- GUI 连接层缺口。
- DTO / API / 后端能力缺口。
- Deferred Placeholder。
- 权限和多玩家信息隔离风险。

这份 Matrix **可以作为后续 Gap Report 和 Phase Plan 的基础**，但目前仍有几处高影响问题需要修正，否则会导致后续工作量判断偏差。

## 二、必须修正项

### 1. 收入阶段不应简单归类为 Backend Gap

当前 Matrix 在 G6-G22 中多处将收入阶段标为 `Backend Gap` 或“无 revenue API”。

审阅发现：

- `src/core/service/economic_service.py` 已存在 `EconomicService`。
- `EconomicService.settle_revenue_phase()` 已包含收入结算相关数据结构，例如：
  - public land income
  - private land rows
  - contract rows
  - military / naval maintenance
  - faction rows
- 当前真正缺口更像是：
  - `revenue_api.py` 缺失。
  - `GuiApiAdapter` 缺收入阶段方法。
  - `GuiSessionStore` 缺 revenue view / execute Slot。
  - QML 阶段页缺失。
  - DTO 需要为 GUI 做权限过滤和结构稳定化。

建议修正分类：

| 原分类 | 建议分类 |
| --- | --- |
| Backend Gap | API Missing / Adapter Gap / DTO Gap |
| 无收入后端 | Core Service Existing, GUI API Missing |
| Deferred | Deferred until Revenue API + DTO wrapper |

收入阶段后续不应被视为“从零做后端规则”，而应视为“已有 Core Service，需要补 GUI 安全 API 和 DTO”。

### 2. Backend Status 枚举需要统一

指令要求分类使用：

- Existing
- Adapter Gap
- DTO Gap
- Backend Gap
- Deferred Placeholder
- Pure Static UI Text

当前 Matrix 中出现了若干扩展写法：

- `API有/Adapter Store QML缺`
- `API有/GUI无`
- `New QML`
- `API→GUI全链路已通`
- `Backend Gap + 权限问题`

这些写法有助于理解，但如果直接进入 DTO Gap Report，会导致汇总不可机器化、不可稳定比较。

建议做法：

1. 保留原描述作为备注。
2. `Backend Status` 字段统一改为标准枚举。
3. 需要更细分类时，在 `Implementation Status` 或备注中说明。

建议映射：

| 当前写法 | Backend Status 建议 | Implementation Status 建议 |
| --- | --- | --- |
| API有/Adapter Store QML缺 | Adapter Gap | Add Adapter + Store + Rebuild QML |
| API有/GUI无 | Adapter Gap 或 DTO Gap | Add GUI exposure |
| New QML | Pure Static UI Text 或 Existing | Rebuild QML |
| API→GUI全链路已通 | Existing | Rebuild QML visual |
| Backend Gap + 权限问题 | Backend Gap 或 DTO Gap | Permission model required |

### 3. 人口与元老院表格字段不完整

区域 I、J 的表格比前文 Shell / 天命 / 收入 / 广场少了字段。

缺少或合并了：

- Empty State
- Error State
- Evidence
- 有些行缺 Phase Rule / Permission Rule / Enabled Rule 的完整表达

这会影响后续 DTO Gap Report 对 empty/error/权限字段的整理。

建议：

- 不需要重写内容。
- 但请补齐 I、J 区域表格字段，与主模板保持一致。
- 尤其人口阶段要补：
  - 庆典赞助空状态。
  - 候选人为空状态。
  - 投票失败错误状态。
  - 非当前玩家 disabled reason。
- 元老院阶段要补：
  - 提案列表为空。
  - 战争/停战/总督/合同列表为空。
  - 只读原因。
  - 未来交互缺口证据。

### 4. 战争与决算阶段的 Backend Gap 表述需更精确

当前 K/L 区域将战争、决算多处标为 Backend Gap，并指出 `combat_api.py` / `resolution_api.py` 不存在。

这个判断在“GUI API 缺失”层面成立，但需要避免误读为 Core 完全不存在。

从代码检索看：

- `game_api.py` 仍引用 `CombatCommand`，但 GUI 禁止直接使用 CLI Command 路径。
- `core.systems.war_system`、`military_system`、`naval_system` 等已有部分战争相关能力。
- `game_api.advance_year()` 存在，但它不是合格 GUI 安全封装。

建议修正为：

| 区域 | 建议分类 |
| --- | --- |
| 战争阶段 K5-K8 | API Missing / Backend Capability Partial / GUI Deferred |
| 决算阶段 L5-L7 | API Missing / GUI Safe Wrapper Missing / DTO Gap |

如果 OC 无法确认 Core 能力是否足够，应写 `Unknown / Requires Architecture Audit`，不要直接写“后端完全缺失”。

### 5. 通用 `advancePhase` 不应默认作为 Phase 1 必做

Matrix 在 C2、H15 等位置提出新增通用 `advancePhase` Slot。

该方向可以作为长期统一设计，但不应阻塞第一阶段 New Shell 或天命 Vertical Slice。

理由：

- 天命阶段已有 `doAdvanceMortality()` 完整链路。
- 当前目标是先验证新 Shell + 天命阶段闭环。
- 过早设计通用推进 Slot 可能扩大范围，牵涉所有阶段状态机。

建议：

- C2 分类改为 `Decision Needed / Later Adapter Gap`。
- `GUI_PHASE_INTEGRATION_PLAN` 中将通用 `advancePhase` 放到 Phase 2+ 或“阶段统一推进治理”任务。
- 天命 Vertical Slice 继续使用现有 `doAdvanceMortality()`。

## 三、建议保留的优点

以下内容建议保留，作为后续两份文档的基础：

1. 顶栏 A5/A6 的判断很好：
   - 稳定度应先 Deferred，不要为了 HTML 占位强行加后端。
   - 战争数可以从现有 senate view 摘要暴露，属于轻量 DTO/Store Gap。

2. 底部 12 查询按钮分类清楚：
   - 已实现查询与 Deferred Placeholder 区分明确。
   - 权限不确定项有标注。

3. 天命阶段 Mapping 可作为第一个 Vertical Slice 依据：
   - execute / result / disabled reason / advance 链路完整。
   - 适合作为新 QML 视觉体系验证点。

4. 广场阶段第二轮修正有价值：
   - 正确认识到 `forum_api.py` 已有大量能力。
   - 将“后端缺口”改成“API 有，GUI 连接缺”是正确方向。

5. 元老院阶段判断准确：
   - API 有交互能力。
   - Adapter / Store / QML 当前只读。
   - 后续应单独规划元老院交互化任务。

## 四、是否允许继续下一步

建议流程：

1. OC 先小修 `GUI_CONTROL_MAPPING_MATRIX.md`：
   - 修正收入阶段分类。
   - 统一 Backend Status 枚举。
   - 补齐人口和元老院表格字段。
   - 精确化战争/决算 Backend Gap 表述。
   - 将通用 `advancePhase` 调整为后续决策项，不阻塞天命 Vertical Slice。

2. 修正后无需重新提交大报告，只需在文档末尾追加：
   - “Codex 审阅修正说明”
   - 修改点列表
   - 未处理原因

3. 修正完成后，可以继续输出：
   - `GUI_DTO_GAP_REPORT.md`
   - `GUI_PHASE_INTEGRATION_PLAN.md`

## 五、最终结论

结论：**有条件通过。**

这份 Matrix 的覆盖度和方向是合格的，足以作为后续工作的地基；但必须先做上述小范围修正，尤其是收入阶段分类和 Backend Status 标准化。修正后，可以继续推进 DTO Gap Report 和 Phase Integration Plan。
