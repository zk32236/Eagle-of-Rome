# AS-P0-01 PoliticalSystem 边界审查任务书

## 任务目标

请系统架构师在 DeepSeek 实现前，审查 `PoliticalSystem` 重构边界，明确政治系统职责范围、迁移边界、禁止事项、公共接口建议和验收测试范围。

## 背景说明

当前项目采用以下协作分工：

- 项目负责人：最终决策与需求确认。
- 项目经理 Agent：整体计划、任务拆分、任务书、文档管理、优先级控制。
- 系统架构师 Agent：架构审查、代码验收、本地调试、pytest 验证。
- DeepSeek：模块程序员，负责代码实现、补丁、实现报告和测试说明。

根据项目路线图，当前第一阶段为“架构收口 Sprint”。`PoliticalSystem` 重构是 P0 任务，必须先完成边界审查，再交给 DeepSeek 实现。

## 工作目录基线

文档根目录：

`E:\Eagle of Rome`

代码根目录：

`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

Python 解释器：

`C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`

测试框架：

`pytest`

## 依据文档路径

请优先参考：

- `E:\Eagle of Rome\MVP 0.9 项目管理\架构收口 Sprint 任务包.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\文档-代码一致性审计清单.md`
- `E:\Eagle of Rome\MVP 0.7 架构文档`
- `E:\Eagle of Rome\MVP 0.7 函数索引说明书`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 审查重点

请重点审查：

1. 是否应新增 `src/core/systems/political_system.py`。
2. `PoliticalSystem` 应承担哪些职责。
3. 哪些逻辑应从 `phase_senate.py` 迁移。
4. 哪些逻辑应从 `senate_api.py` 迁移。
5. 哪些逻辑应保留在 UI 命令层。
6. 哪些逻辑应保留在 API 层。
7. 是否需要新增 `GameState`、`WarSystem`、`Province` 等公共方法。
8. 如何减少 `_senate_pending`、战争私有列表、总督候任字段等私有字段直改。
9. 如何保持自动模式、手动模式、多玩家信息隔离不退化。
10. DeepSeek 实现时的禁止事项和验收测试范围。

## 禁止事项

本次任务是架构边界审查，不要求直接修改代码。

审查建议中应明确禁止 DeepSeek：

- 不得改变元老院阶段玩家可见流程。
- 不得绕过 `senate_api` 直接让 UI 调用系统层执行玩家操作。
- 不得新增 UI 层直接修改私有字段。
- 不得删除现有提案类型、战争接管、停战草案、预算、总督任命逻辑。
- 不得引入 P1 新玩法。
- 不得做无关格式化或大范围重构。

## 期望输出格式

请按以下格式输出：

```text
Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER

Reasons:

Files reviewed:

Recommended PoliticalSystem responsibilities:

Logic to migrate from phase_senate.py:

Logic to migrate from senate_api.py:

Logic that should remain in UI/API:

Required public methods or interfaces:

Required pytest targets:

Architecture risks:

DeepSeek implementation constraints:
```

## 验收标准

本任务完成后，项目经理应能够据此生成 DeepSeek 的 `AS-P0-01 PoliticalSystem 重构开发任务书`，且 DeepSeek 不需要自行决定系统边界。
