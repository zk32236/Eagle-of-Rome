# GUI-P0-03R1 S1 ForumStage 任务书骨架 SA开发任务书

> 流程版本：PM→SA→DA v2.2-C1
> 任务编号：GUI-P0-03R1
> Subtask：S1 — SA 任务书骨架
> 日期：2026-07-15
> 产出方式：SA 子代理 runtime failure 后，由 Main Session 按文档接替
> 状态：Draft for PM Gate

---

## 1. 任务背景

GUI-P0-03 ForumStage 已完成初始 Vertical Slice，但 Phase 3A 解雇阶段、Phase 3B 市场阶段的视觉校准出现明显回归：人物列表文本、属性与按钮重叠，且后续补丁混入步骤条、市场数据、按钮状态、DTO/真实数据语义等多个问题，导致界面越改越差。

本任务不直接修代码，而是按 v2.2-C1 workflow 将 GUI-P0-03R1 拆分为串行子任务。S1 仅输出 Development Task Skeleton，为后续 S2 视觉/布局契约、S3 PM 合并 Gate、S4 DA 第一刀修复提供骨架。

## 2. 本轮主类型

```text
Task Skeleton / Planning only
```

本轮不属于：

- Visual Calibration
- Layout Contract
- Data DTO Fix
- Store/API Binding
- Code Implementation

## 3. 任务目标

S1 的目标是形成轻量任务书骨架，明确后续子任务的边界、顺序、交付物和 Gate。

S1 不输出最终 DA 可执行任务书。最终 DA 任务书必须在 S2 补齐 Visual-State Contract、Layout Contract、A-F 差异表后，由 S3 合并并通过 PM Gate。

## 4. 依据文档

| 文档 | 路径 |
| --- | --- |
| PM Intent v2.2 | `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03R1_ForumStage_Phase3A3B_可控返工_PM意图包_v2.2.md` |
| v2.2-C1 workflow | `E:\OpenClaw\Projects\EOR\workflows\pm-sa-da-sequence-workflow.md` |
| GUI SA-DA 任务书模板 | `E:\OpenClaw\Projects\EOR\agents\SA\skills\GUI\EOR_GUI_SA-DA_开发任务书规范模板_v1.4.md` |
| 原 Phase 3 PM 意图包 | `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03_ForumStage_PM意图包.md` |
| 原 Phase 3 DA 报告 | `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03/GUI-P0-03_ForumStage_DA开发报告.md` |

## 5. 允许范围

S1 仅允许产出文档骨架：

- `GUI-P0-03R1_S1_ForumStage_任务书骨架_SA开发任务书.md`

后续 S2 可产出：

- `GUI-P0-03R1_S2_ForumStage_VisualLayoutContract.md`
- `GUI-P0-03R1_S2_ForumStage_A-F差异表.md`

后续 S3 可产出：

- `GUI-P0-03R1_ForumStage_Phase3A3B_最终SA开发任务书.md`
- `GUI-P0-03R1_PM_Gate_Report.md`

## 6. 禁止范围

S1 禁止：

- 修改任何产品代码。
- 读取或分析 PNG 截图。
- 输出 Visual-State Contract。
- 输出 Layout Contract。
- 输出 A-F 差异表。
- 将本骨架作为 DA 可执行任务书。
- 要求 DA 启动。

## 7. 后续小步执行框架

| Subtask | 名称 | 角色 | 主要输入 | 主要输出 | Gate |
| --- | --- | --- | --- | --- | --- |
| S1 | 任务书骨架 | SA / Main Session fallback | PM Intent v2.2、workflow、模板、旧 PM/DA 文档 | Development Task Skeleton | PM Gate |
| S2 | 视觉与布局契约 | SA | S1、设计图、实测图、GUI Governance | Visual-State Contract、Layout Contract、A-F 差异表 | PM Gate |
| S3 | 合并与最终 Gate | PM | S1、S2 | 最终 SA 开发任务书、PM Gate Report | DA Sizing Check |
| S4 | DA 第一刀修复 | DA | S3 最终任务书 | Implementation Report、Runtime Screenshot、Test Results、Watermark | SA Verification |

## 8. S2 必须补充的内容

S2 必须独立输出以下内容，不能混入 S1：

### 8.1 Phase Visual-State Contract

至少覆盖：

- Phase 3A 解雇阶段
- Phase 3B 市场阶段

必须明确：

- 当前步骤条
- 真实游戏数据
- 设计图示例数据
- 必须显示区域
- 可见但禁用区域
- 当前可操作按钮
- 禁用按钮
- 状态推进条件
- 不得提前公开的信息
- 不得伪造的信息

### 8.2 Layout Contract

至少覆盖：

- 左侧解雇成员卡片
- 右侧市场卡片
- 人物列表行
- 属性列、文本列、按钮列
- 滚动区
- 底部按钮固定策略
- 禁止重叠项

### 8.3 A-F 差异表

至少覆盖：

- A TopStatusBar
- B PhaseRail
- C StageDesktop / ForumStage
- D ContextPanel
- E BottomQueryBar
- F StageAction / 卡片内按钮

## 9. S3 最终任务书必须包含

S3 合并后的最终 SA 开发任务书必须包含：

- 本轮任务主类型。
- Phase Visual-State Contract。
- Layout Contract。
- 真实数据与设计示例数据边界。
- 小步执行顺序。
- 截图与验收门禁。
- 允许/禁止修改文件。
- Acceptance Criteria。
- 测试策略。
- 回滚计划。
- DA 交付要求。
- 直接退回条件。

## 10. S4 DA 第一刀原则

S4 不得一次性修全部 Phase 3A/3B 问题。

第一刀建议由 S3 决定，只能选择一个主要区域，例如：

- 只修左侧人物列表防重叠；
- 或只修步骤条语义；
- 或只修右侧市场卡片空状态；
- 或只修卡片内底部按钮固定。

每刀完成后必须提交：

- 修改文件列表。
- Runtime Screenshot。
- 本刀影响区域。
- 不回退区域说明。
- 测试结果。
- Context Watermark。

## 11. AC 框架

| 编号 | 验收项 |
| --- | --- |
| AC-S1-01 | S1 仅输出任务书骨架，不包含图片分析和视觉契约 |
| AC-S1-02 | S1 明确 S2/S3/S4 的输入、输出、Gate |
| AC-S1-03 | S1 明确后续 DA 不得在 S3 PM Gate 前启动 |
| AC-S1-04 | S1 明确 S2 必须补齐 Visual-State Contract、Layout Contract、A-F 差异表 |
| AC-S1-05 | S1 不修改任何产品代码 |

## 12. 测试策略框架

S1 为文档任务，无需运行产品测试。

后续 S4 至少需要：

- GUI startup 测试。
- 与本刀修改相关的 GUI/API 聚焦测试。
- 必要时完整回归。
- Runtime Screenshot 人工视觉核查。

## 13. 交付件框架

| 阶段 | 交付件 |
| --- | --- |
| S1 | `GUI-P0-03R1_S1_ForumStage_任务书骨架_SA开发任务书.md` |
| S2 | Visual-State Contract、Layout Contract、A-F 差异表 |
| S3 | 最终 SA 开发任务书、PM Gate Report |
| S4 | DA Implementation Report、Runtime Screenshot、Test Results、Watermark |

## 14. Runtime Failure 记录

S1 原计划由 SA 子代理执行。

子代理 `019f653c-948b-71d2-b12a-d2d23682a954` 连续两个 `wait_agent` 窗口未返回，经状态追问后一个等待窗口仍无回复，触发 v2.2-C1 `SUBAGENT_RUNTIME_FAILURE`。目标目录未发现写入文件。

因此本文件由 Main Session 按文档接替方式产出。若该子代理后续返回产物，只能作为 reference-only，不自动进入主流程。

## 15. Context Watermark

```text
---CONTEXT WATERMARK---
Estimated load: ~24%
Key assets written:
- GUI-P0-03R1_S1_ForumStage_任务书骨架_SA开发任务书.md
Steps completed: S1 task skeleton
---
```
