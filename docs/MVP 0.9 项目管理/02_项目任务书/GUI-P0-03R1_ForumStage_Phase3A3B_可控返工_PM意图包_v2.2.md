# GUI-P0-03R1 ForumStage Phase 3A/3B 可控返工 PM意图包 v2.2

日期：2026-07-15
流程版本：PM→SA→DA v2.2 试跑
任务编号：GUI-P0-03R1
任务名称：ForumStage Phase 3A/3B 可控返工
状态：Ready for Subtask S1

---

## 1. 为什么做

GUI-P0-03 ForumStage 已完成初始 Vertical Slice，并通过自动化测试。但在 Phase 3A 解雇阶段、Phase 3B 市场阶段的视觉校准中，出现人物列表文本、属性与按钮重叠，任务补丁混入步骤条、市场数据、按钮状态、DTO/真实数据语义等多个问题，导致界面越改越差。

本轮目标不是直接继续补 QML，而是按 v2.2 流程重新组织 Phase 3A/3B 可控返工：先拆分 SA 子任务，形成任务书骨架与视觉/布局契约，再合并进入 PM Gate，最后启动 DA 执行第一刀小步修复。

## 2. 期望成果

- 形成符合 v2.2 的 SA 开发任务书骨架。
- 形成 Phase 3A/3B Visual-State Contract、Layout Contract、A-F 差异表。
- PM 合并并核对最终 Development Task。
- DA 只按 Gate 后任务书执行第一刀修复，不越界改 core / shell / 非本轮区域。

## 3. 范围

### 包含

- Phase 3A 解雇阶段：步骤条语义、左侧真实人物列表、锁定状态、完成解雇按钮、右侧市场预览禁用态。
- Phase 3B 市场阶段：市场标题、真实市场数据、待预算合同/可竞标合同、公地/凯旋栏位、提交下注/完成下注按钮。
- Layout Contract：左右双卡片、列表行、列宽、按钮列、滚动区、底部按钮固定。
- Screenshot Gate：每次只修一个区域，必须提交目标图、实测图、差异表。

### 不包含

- 不修改 `src/core/`、entities、systems、service。
- 不重写 Shell，不重排 TopStatusBar、PhaseRail、ContextPanel、BottomQueryBar。
- 不一次性重写 ForumStage 全布局。
- 不伪造真实游戏数据。
- 不进入 Phase 4 及后续阶段。

## 4. 验收条件

1. SA 开发任务书骨架只定义范围、文件、步骤框架、AC 框架，不分析图片。
2. Visual/Layout Contract 单独输出，不与任务书骨架混装。
3. 最终 Development Task 必须明确真实数据与设计示例数据边界。
4. DA 每步修改后必须提交 Runtime Screenshot，Runtime Evidence 优先于自动化测试。
5. 后续 DA 未通过 PM Gate 前不得修改代码。

## 5. 约束

- v2.2 Task Sizing Gate 已触发：输入文件多、图片多、产出物多、跨视觉/布局/数据/测试多域。
- 必须拆分为串行子任务。
- 子任务产出物必须单一。
- 被替换或关闭的子代理后续产物只能作为 reference-only。

## 6. 参考材料

- `E:\OpenClaw\Projects\EOR\workspace\diagnostics\v2.2_review_package_2026-07-15\workflows\pm-sa-da-sequence-workflow_v2.2.md`
- `E:\OpenClaw\Projects\EOR\workspace\diagnostics\v2.2_review_package_2026-07-15\prompts\PM-任务意图包模板_v2.2.md`
- `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_Development_Governance_v1.1.md`
- `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_SA-DA_开发任务书规范模板_v1.4.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-03_ForumStage_PM意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03_开发与验收\GUI-P0-03\GUI-P0-03_ForumStage_DA开发报告.md`

## 7. 优先级与排期

- 优先级：P0
- 建议开发：Codex / SA / DA-Exec 串行试跑

## 8. Subtask Plan / 任务切片与子代理策略

### 是否拆分

- [ ] 单任务
- [x] 串行拆分（后一步依赖前一步产物）
- [ ] 并行拆分

### 拆分原因

- [x] 输入文件 > 5 个
- [x] 输入图片 > 1 张
- [x] 产出物 > 1 类
- [x] 同时涉及视觉、布局、数据、业务流程、测试中的两类以上
- [x] 需跨 API / Store / QML / Test 多层修改
- [x] 需在多份文档与多张图片之间综合推理

### 子任务列表

| Subtask ID | 名称 | 执行角色 | 输入材料 | 输出物 | 前置依赖 |
| --- | --- | --- | --- | --- | --- |
| S1 | SA 任务书骨架 | SA | 本 PM Intent v2.2、v2.2 workflow、SA-DA 模板 v1.4、旧 PM/DA 文档 | Development Task Skeleton | - |
| S2 | Phase 3A/3B 视觉与布局契约 | SA | S1 骨架、Phase 3A/3B 设计图与实测图、GUI Governance v1.1 | Visual-State Contract + Layout Contract + A-F 差异表 | S1 + PM Gate |
| S3 | PM 合并与 Gate | PM | S1 骨架、S2 Contract / 差异表 | 最终 SA 开发任务书 + PM Gate 结论 | S2 |
| S4 | DA 第一刀修复 | DA | S3 最终任务书 | Implementation Report + Runtime Screenshot + Test Results + Watermark | S3 + PM Gate |

### 执行方式

串行顺序：S1 → PM Gate → S2 → PM Gate → S3 → DA Sizing Check → S4

### 写入范围冲突检查

- [x] S1/S2/S3 均为文档产出，不修改代码。
- [x] S4 代码写入范围由 S3 最终任务书定义。
- [x] 未通过 S3 PM Gate 前，不允许 DA 修改任何产品代码。

### 合并责任人

- 合并责任人：PM / Codex 主会话
- 说明：S1 与 S2 产物由 PM 合并为最终 Development Task。

### 迟到产物处理

- 被替换或关闭的子代理后续返回产物标记为 reference-only，不自动进入主流程。

### Gate 设计

- [x] S1 完成后由 PM 核对骨架是否覆盖 Intent 范围。
- [x] S2 完成后由 PM 核对 Contract 是否覆盖 Phase 3A/3B 视觉与布局问题。
- [x] S3 完成后执行 DA Task Sizing Check。
- [x] S4 完成后由 SA 验收，再进入 PM Final Gate。
