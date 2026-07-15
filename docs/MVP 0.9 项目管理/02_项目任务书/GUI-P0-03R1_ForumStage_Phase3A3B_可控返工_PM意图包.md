# GUI-P0-03R1 ForumStage Phase 3A/3B 可控返工 PM意图包

日期：2026-07-14
流程版本：PM→SA→DA v2.1 试跑
任务编号：GUI-P0-03R1
任务名称：ForumStage Phase 3A/3B 可控返工
状态：Ready for SA Task Design

---

## 1. 背景

GUI-P0-03 ForumStage 已完成初始 Vertical Slice，并通过自动化测试。但在 Phase 3A 解雇阶段、Phase 3B 市场阶段的视觉校准过程中，出现了明显回归：人物列表文本、属性与按钮重叠，左侧卡片可读性下降，后续补丁同时混入步骤条、市场数据、按钮状态、DTO/真实数据语义等多个问题，导致越改越差。

因此，本轮不继续直接修改 QML，而按 v2.1 流程重建返工闭环：先由 PM 明确意图，再由 SA 输出开发任务书与 GUI Contract，经过 PM Gate 后，再由 DA 小步执行。

## 2. Problem

当前问题不是单一 QML bug，而是开发流程失控造成的综合问题：

- 缺少 Phase Visual-State Contract，导致公示区、解雇环节、市场环节的编号与状态语义反复摇摆。
- 缺少 Layout Contract，导致人物行、按钮、属性文本在真实数据较长时重叠。
- 设计图示例数据与真实游戏数据边界不清，导致市场新人是否可见、合同是否可竞标等语义被混淆。
- 自动测试通过，但运行截图明显不可接受。
- 单轮修改范围过大，未执行 Small-Step Screenshot Gate。

## 3. Scope

本轮只处理 ForumStage Phase 3A/3B 的可控返工任务设计与后续小步修复，不处理 Phase 4 及后续阶段。

允许 SA 设计任务覆盖以下问题域：

| 问题域 | 说明 |
| --- | --- |
| Phase 3A 解雇阶段 | 步骤条语义、左侧真实人物列表、锁定状态、完成解雇按钮、右侧市场预览禁用态 |
| Phase 3B 市场阶段 | 市场标题、真实市场数据、待预算合同/可竞标合同、公地/凯旋栏位、提交下注/完成下注按钮 |
| Layout Contract | 左右双卡片、列表行、列宽、按钮列、滚动区、底部按钮固定 |
| Screenshot Gate | 每次只修一个区域，必须提交目标图、实测图、差异表 |

## 4. Out of Scope

| 禁止项 | 说明 |
| --- | --- |
| 不修改 `src/core/` | 不改游戏内核、实体、系统、服务 |
| 不重写 Shell | 不重排 TopStatusBar、PhaseRail、ContextPanel、BottomQueryBar |
| 不一次性重写 ForumStage 全布局 | 必须拆为小步返工 |
| 不伪造真实游戏数据 | 设计图中的人物、数值、合同只是示意 |
| 不用测试通过替代视觉验收 | 截图/人工视觉证据优先 |
| 不进入 Phase 4 | 本轮仅 Phase 3A/3B |

## 5. 已确认产品语义

### 5.1 步骤条

正确语义为：

```text
✅ 公示区 → 1 解雇成员 → 2 市场（招募·竞标·认购·凯旋）
```

`公示区` 是前置公示/说明区，不作为编号步骤。编号步骤只有：

1. 解雇成员
2. 市场（招募·竞标·认购·凯旋）

### 5.2 Phase 3A 解雇阶段

- 左侧列表必须显示真实派系成员，不按设计图裁剪为 2 人。
- 派系领袖、仍有活跃合同的人物可以显示为锁定/禁用。
- 市场新人不应提前公开；这属于游戏博弈设计。
- 右侧市场区可以可见但禁用，用于说明“等待子环节完成”。
- “完成解雇”按钮应放在左侧卡片底部，靠近设计图满宽风格；长列表时列表区域滚动，按钮固定。

### 5.3 Phase 3B 市场阶段

- 市场阶段展示真实公开市场数据。
- 第一回合可能没有可竞标合同、公地认购或凯旋投票，但对应栏位应保留并显示空状态。
- `PENDING` 合同代表等待元老院预算表决，不可竞标。
- `BUDGETED` 合同代表已预算、可在广场竞标。
- 市场底部按钮语义为提交/完成下注，而不是直接推进阶段。
- 所有玩家完成市场操作后，右侧 ContextPanel 的“推进到下一阶段”才可用。

## 6. 验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | SA 开发任务书必须包含 Phase Visual-State Contract |
| AC-02 | SA 开发任务书必须包含 Layout Contract |
| AC-03 | SA 必须将任务拆成 Small-Step Screenshot Gate，不允许一次性大改 |
| AC-04 | 任务书必须明确真实数据与设计示例数据边界 |
| AC-05 | 任务书必须明确允许/禁止修改文件 |
| AC-06 | 任务书必须规定截图、差异表、测试和水位报告交付件 |
| AC-07 | 后续 DA 不得在未通过 PM Gate 前修改代码 |
| AC-08 | 后续 DA 每步修改后必须提交运行截图，Runtime Evidence 优先于测试结果 |

## 7. 参考材料

| 材料 | 路径/说明 |
| --- | --- |
| v2.1 工作流 | `E:\OpenClaw\Projects\EOR\workflows\pm-sa-da-sequence-workflow.md` |
| GUI 治理规范 | `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_Development_Governance_v1.1.md` |
| GUI 任务书模板 | `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_SA-DA_开发任务书规范模板_v1.4.md` |
| 原 Phase 3 PM 意图包 | `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03_ForumStage_PM意图包.md` |
| 原 Phase 3 DA 报告 | `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03/GUI-P0-03_ForumStage_DA开发报告.md` |
| 设计图 | `C:/Users/Kerl/Downloads/GUI design - Phase 3A.PNG`, `GUI design - Phase 3B.PNG` |
| 实测问题图 | `C:/Users/Kerl/Downloads/GUI acutal phase 3A - 3.PNG`, `GUI acutal phase 3B - 2.PNG` |

## 8. 下一步

进入 SA Task Design。SA 只输出开发任务书，不修改代码。PM Gate 核对通过后，才能启动 DA 执行第一刀修复。
