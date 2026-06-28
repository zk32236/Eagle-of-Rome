# AS-P0-02 EconomicService 重构 PM任务意图包

创建日期：2026-06-22

发布对象：系统架构师 SA

任务性质：PM 级任务意图，不是 DeepSeek 技术开发任务书

## 一、当前判断

AS-P0-01 `PoliticalSystem` 重构已由 SA 验收通过，结论为 `CONDITIONAL_PASS`。架构收口 Sprint 的下一条主线应推进 AS-P0-02 `EconomicService` 重构。

当前收入阶段仍承载大量核心经济结算规则，包括私地收益、公地收益、合同结算、军团维护、海军维护、国家运营费、战争赔款、派系资金更新等。后续 MVP 1.0 的腐败、忠诚度、人物养成、派系收买、审判罚金等功能都会依赖稳定的经济结算边界，因此 `EconomicService` 是进入 P1 玩法开发前必须收口的 P0 架构任务。

## 二、任务目标

请 SA 基于现有代码和架构文档，完成 AS-P0-02 `EconomicService` 重构的技术边界审查，并在边界明确后定稿技术任务书，由 SA 直接发布给 DeepSeek。

PM 目标不是要求 SA 立即修改代码，而是要求 SA 将以下问题收口到可执行技术任务：

1. 明确是否新增或整理 `src/core/service/economic_service.py`。
2. 明确 `EconomicService` 应承担的收入阶段经济结算职责。
3. 明确哪些逻辑应从 `phase_revenue.py` 迁移到服务层。
4. 明确哪些展示、输入、阶段推进逻辑应保留在 UI 命令层。
5. 明确服务返回结构，保证未来 CLI 和 GUI 都可复用。
6. 明确资金流、合同生命周期、军团/舰队维护费、战争赔款的顺序与原子性要求。
7. 明确 DeepSeek 实现时的允许范围、禁止事项、测试目标和交付格式。

## 三、优先级与阶段位置

| 项目 | 结论 |
| --- | --- |
| 任务编号 | AS-P0-02 |
| 任务名称 | `EconomicService` 重构 |
| 优先级 | P0 |
| 所属阶段 | 架构收口 Sprint |
| 前置条件 | AS-P0-01 `PoliticalSystem` 已验收通过 |
| 后续依赖 | 腐败、忠诚度、人物养成、派系收买、监察官审判、经济平衡 |

PM 判断：AS-P0-02 应优先于大部分 P1 玩法功能启动；在它完成前，不建议 DeepSeek 开始腐败、忠诚度、派系收买等经济/政治强耦合玩法。

## 四、依据文档路径

请 SA 优先参考：

- `E:\Eagle of Rome\MVP 0.9 项目管理\架构收口 Sprint 任务包.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\文档-代码一致性审计清单.md`
- `E:\Eagle of Rome\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `E:\Eagle of Rome\MVP 0.7 架构文档`
- `E:\Eagle of Rome\MVP 0.7 函数索引说明书`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 五、代码审查关注范围

请 SA 重点审查以下代码区域，并据此定稿技术任务书：

| 范围 | PM 关注点 |
| --- | --- |
| `src/ui/commands/phase_revenue.py` | 当前收入阶段是否承担过多核心经济规则，哪些逻辑应迁移 |
| `src/core/service/` | 是否已有可复用服务模式，`EconomicService` 应放置和命名在哪里 |
| `src/core/game_state.py` | 资金、阶段状态、临时状态、日志与公共方法是否足够支撑服务化 |
| `src/core/entities/contract.py` | 合同生命周期、到期、结算、付款语义是否需要公共方法补强 |
| `src/core/systems/military_system.py` | 军团维护费、状态恢复、战争相关经济影响是否存在边界耦合 |
| `src/core/systems/naval_system.py` | 舰队维护费、建造合同、舰队状态是否存在边界耦合 |
| `src/api/` | 是否需要为经济结算预留 API 边界，或本轮仅保持命令层调用服务 |
| `src/tests/` | 当前收入阶段、合同、军团、舰队、战争赔款相关测试覆盖是否足够 |

## 六、PM 级验收目标

AS-P0-02 最终完成后，PM 期望达到以下结果：

| 类别 | 验收目标 |
| --- | --- |
| 架构 | 收入阶段核心经济规则从 UI 命令层迁移到服务层，依赖方向保持 `UI -> API/Core Service -> Entity/System` |
| 行为 | 私地、公地、合同、维护费、国家运营费、战争赔款、派系资金更新等旧行为不退化 |
| 可测试性 | `EconomicService` 可被测试直接调用，收入阶段回归测试能覆盖主要结算路径 |
| 可扩展性 | 后续腐败、忠诚度、派系资金、罚金、经济平衡等 P1 功能不需要继续往 `phase_revenue.py` 堆规则 |
| 可观测性 | 关键经济结算路径保留或增强 DEBUG 日志，便于 SA 和 DeepSeek 追踪资金流 |
| 交付 | SA 验收结论至少为 `CONDITIONAL_PASS`，相关 pytest 通过或失败项有明确非本任务原因 |

## 七、PM 级禁止事项

请 SA 在技术任务书中约束 DeepSeek：

- 不得改变收入阶段对玩家展示的核心结果。
- 不得引入腐败、忠诚度、派系收买、审判罚金等 P1 新玩法。
- 不得将新的经济规则继续堆在 UI 命令层。
- 不得破坏资金流转原子性，避免出现部分扣款/部分结算的半状态。
- 不得改变合同生命周期语义。
- 不得绕过现有玩家、派系、国库等资金归属规则。
- 不得做无关大范围格式化或跨模块重构。
- 不得修改 `E:\Eagle of Rome` 下历史档案作为代码交付。

## 八、建议 SA 输出内容

请 SA 先输出 `EconomicService` 边界审查结果，建议格式如下：

```text
Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER

Reasons:

Files reviewed:

Recommended EconomicService responsibilities:

Logic to migrate from phase_revenue.py:

Logic that should remain in UI command layer:

Logic that should remain in entity/system layer:

Required public methods or interfaces:

Required service return structure:

Required pytest targets:

Architecture risks:

DeepSeek implementation constraints:

Technical task brief publication status:
```

## 九、任务发布机制

本任务后续发布给 DeepSeek 的机制如下：

1. PM 已输出本任务意图包。
2. SA 基于边界审查定稿技术任务书。
3. SA 直接发布技术任务书给 DeepSeek。
4. DeepSeek 输出后，由 SA 先做代码与测试验收。
5. SA 向 PM 返回验收结论。
6. PM 更新架构收口 Sprint 进度、任务池和路线图。

## 十、PM 交付要求

请 SA 完成以下交付：

1. `EconomicService` 边界审查结论。
2. 面向 DeepSeek 的技术任务书。
3. 技术任务书发布确认。
4. 后续 DeepSeek 输出后的 SA 验收报告。

PM 将根据 SA 回执更新：

- `架构收口 Sprint 任务包.md`
- `MVP0.7模块开发优先级表.md`
- `后续任务池.md`
