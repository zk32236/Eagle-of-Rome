# MVP 0.7 模块开发优先级表

本表用于从 MVP 0.7 功能完成状态进入 MVP 0.9 / MVP 1.0 P1 开发前，安排架构收口、技术债务和后续功能开发顺序。

## 当前判断

MVP 0.7 功能层面可以视为已完成，但进入 P1 前仍需要完成架构收口。DeepSeek 回顾报告认为当前项目处于 `MVP 0.7 -> MVP 1.0` 过渡期；Codex 审计认为功能完成与架构合规之间仍有差距，需要先做收束。

截至 2026-06-25，架构收口 Sprint 的 P0 主线均已完成验收。AS-P0-03 获得 SA `CONDITIONAL_PASS`，项目负责人手工测试通过，指定测试 187 passed、全量测试 721 passed，代码提交为 `6cc972e`。SA 建议 Sprint 已满足结束条件，当前等待项目负责人正式批准进入 GUI 原型/下一阶段。

截至 2026-06-28，GUI-P0-01 MVP0.7 可玩 GUI 原型已完成验收并归档。SA 验收 `PASS`，项目负责人手工测试通过，全量测试 734 passed，代码提交为 `2b220bf`。这意味着后续 P1 功能可以按“功能实现 + 最小可用 GUI 同步交付”的方式推进，GUI-P1-02 仍保留为后期完整迁移和产品化收尾任务。

截至 2026-06-30，AS-P1-01 API Response 统一已完成验收、Git 归档并推送 `origin/main`。SA 验收 `PASS`，focused tests 4 passed，API regression 144 passed，全量回归 738 passed，代码提交为 `01ebce2`。后续 P1 API 开发应复用 `src.api.api_response`，不得在 API 模块中新增重复响应工厂。

截至 2026-07-01，GUI-P0-02A GUI 主壳与阶段导航扩展已完成 Git 归档并推送 `origin/main`，代码提交为 `b3d40b5`。CGT-01 报告 `src/tests/test_gui` 20 passed、人口 API 29 passed、人口阶段 21 passed、full `src/tests` 745 passed；SA 结论为 `CONDITIONAL_PASS / READY_FOR_MANUAL_VISUAL_CHECK`。后续进入 GUI-P0-02B「天命 + 人口阶段 GUI 闭环」，P1 功能开发顺延至 GUI-P0 Sprint 完成后启动。

## 优先级定义

| 优先级 | 含义 |
| --- | --- |
| P0 | 阻塞后续开发，必须优先完成 |
| P1 | 下一阶段核心功能或重要重构 |
| P2 | 可延后，但应在 GUI 或大规模扩展前完成 |
| P3 | 低风险优化或历史清理 |

## 阶段 A：架构收口 Sprint

| 优先级 | 任务 | 目标 | 主要文件/模块 | 验收标准 |
| --- | --- | --- | --- | --- |
| P0 | `PoliticalSystem` 重构 | 将元老院政治核心逻辑从 UI/API 收束到系统层 | `src/core/systems/political_system.py`、`senate_api.py`、`phase_senate.py` | UI 不再直接执行核心政治规则，API 调用系统层 |
| P0 | `EconomicService` 重构 | 将收入阶段经济结算从命令层迁移到服务层 | `src/core/service/economic_service.py`、`phase_revenue.py` | 收入阶段命令只负责调用服务和打印 |
| P0 | 私有字段访问收束 | 减少 `_senate_pending`、`_population_pending`、战争私有列表等直改 | `game_state.py`、`war_system.py`、阶段命令 | 新增公共方法，命令/API 不再新增直改 |
| P0 | 广场阶段土地交易 API 化 | 补齐广场阶段步骤4的数据流统一 | `forum_api.py`、`phase_forum.py`、`auto_player_processor.py` | 土地交易不直接写 `_forum_pending` |
| P1 | `api_response` 统一 | 删除重复定义，统一从 `src.api` 导入 | `forum_api.py`、`senate_api.py` | 所有 API 返回格式来源一致 |
| P1 | 旧竞标接口处理 | 清理或标记 `GameState.place_bid/resolve_auction` | `game_state.py`、测试 | 旧接口不误导新开发 |
| P2 | 影子 `Province` 处理 | 明确 `entities.py` 中旧 `Province` 的废弃状态 | `entities.py`、文档 | 不再作为新开发参考 |

### 阶段 A 状态跟踪（2026-06-22）

| 任务编号 | 任务 | 状态 | PM 备注 |
| --- | --- | --- | --- |
| AS-P0-01 | `PoliticalSystem` 重构 | 已完成/已验收 | SA 结论 `CONDITIONAL_PASS`；代码提交 `ea770db`；相关测试共 63 项通过 |
| AS-P0-02 | `EconomicService` 重构 | 已完成/已验收 | SA 最终结论 `PASS`；代码提交 `08295df`；指定测试 + 额外合同回归 79 passed；项目负责人手动测试通过 |
| AS-P0-03 | 私有字段访问收束 | 已完成/已验收 | SA `CONDITIONAL_PASS`；手工测试通过；187 项指定测试与 721 项全量测试通过；提交 `6cc972e`；条件项仅为函数索引同步 |
| AS-P0-04 | 广场阶段土地交易 API 化 | 已完成/已验收 | SA 最终结论 `PASS`；代码提交 `24c1933`；论坛阶段相关测试 87 passed；项目负责人手工测试通过 |
| AS-P1-01 | `api_response` 统一 | 已完成/已验收 | SA `PASS`；提交 `01ebce2`；focused 4 passed、API regression 144 passed、full regression 738 passed；`forum_api.py` 与 `senate_api.py` 已改用统一 `src.api.api_response` |
| AS-P1-04 | 测试环境确认 | 部分完成 | SA 已复跑 AS-P0-01 相关 pytest；Sprint 总体验收时仍需复核标准命令 |

## 阶段 B：P1 功能开发前置修复

| 优先级 | 任务 | 目标 | 验收标准 |
| --- | --- | --- | --- |
| P1 | 执政官官职丢失修复 | 定位官职被清空根因 | 不再需要测试绕过逻辑 |
| P1 | i18n 硬编码整改 | 为 GUI 和多语言输出做准备 | 新增/改动 UI 文本走 i18n |
| P1 | 测试环境修复 | 确保项目测试可直接运行 | `pytest` 等依赖可用，全量或相关测试可执行 |
| P2 | 调试命令补齐 | 对新增系统/服务提供可观测性 | debug 命令可查看关键实体状态 |

## 阶段 B0：GUI-P0 Sprint

目标：在 P1 功能开发前，让 MVP0.7/P0 已有核心主干流程可以在 GUI 中连续运行。GUI-P0 Sprint 不负责 GUI-P1-02 的完整产品化收尾，也不新增 P1 玩法。

| 顺序 | 优先级 | 任务 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | P0.5 | GUI-P0-02A GUI 主壳与阶段导航扩展 | 已完成/已归档 | 提交 `b3d40b5`；主壳、阶段导航、状态区、反馈区和 R1 UI 反馈修正已完成 |
| 2 | P0.5 | GUI-P0-02B 天命 + 人口阶段 GUI 闭环 | 已完成/已验收/已归档 | `PASS`；提交 `7426b38`；项目负责人真实 GUI 手工验证通过；full `src\tests` 757 passed |
| 3 | P0.5 | GUI-P0-02C 元老院阶段 GUI 闭环 | 已发布给 SA | PM 要求 SA 使用 Sprint 方法拆成多个可单独验证闭环的小子任务；承接 PoliticalSystem/senate_api，保护投票、提案、任命等边界 |
| 4 | P0.5 | GUI-P0-02D 收入 + 广场阶段 GUI 闭环 | 待排期 | 承接 EconomicService/forum_api，覆盖资金、合同、市场和土地相关主干 |
| 5 | P0.5 | GUI-P0-02E 战争 + 海战阶段 GUI 闭环 | 待排期 | 展示战争、军团、舰队、指挥官和 P0 战争决策入口 |
| 6 | P0.5 | GUI-P0-02F 革命/决算 + 回合推进 + 多玩家交接 | 待排期 | 串起连续回合、玩家交接、AI 路径和权限隔离 |
| 7 | P0.5 | GUI-P0-02G MVP0.7/P0 GUI 一局验收与缺口收束 | 待排期 | 用 GUI 跑通一局主干，只修缺口，不扩玩法 |

## 阶段 C：MVP 0.9 / MVP 1.0 P1 功能序列

参考 DeepSeek 回顾报告中的开发序列。

阶段 C 采用“功能实现 + 最小可用 GUI 同步交付”模式。每个 P1 功能按 `P1功能最小可用GUI开发与验收标准.md` 完成 A/B/C/D 分级；A、B 类功能不得仅交付 CLI。GUI-P1-02 在主要 P1 功能稳定后负责完整迁移与产品化收尾，不作为首次补做全部 P1 GUI 的任务。

| 顺序 | 优先级 | 任务 | 说明 |
| --- | --- | --- | --- |
| 4.0 | P1 | 人物属性系统 | MVP0.9-14，作为人物成长和政治机制基础 |
| 5.0 | P1 | 经验值系统 | 支撑人物成长 |
| 6.0 | P1 | 人物养成 | MVP0.9-15 |
| 7.0 | P1 | 忠诚度机制 | 为腐败、收买、叛变等机制铺底 |
| 8.0 | P1 | 腐败机制 | MVP0.9-01 |
| 9.0 | P1 | 监察官起诉与审判 | MVP0.9-02 |
| 10.0 | P1 | 派系资金收买人物 | MVP0.9-03 |
| 11.0+ | P1/P2 | 其余 P1 功能 | 按目标版本规划继续推进 |
| 22.0 | P1 | 数值平衡 | MVP0.9-17，放在 P1 功能基本完成后 |

## 模块风险排序

| 风险级别 | 模块 | 原因 | 管理动作 |
| --- | --- | --- | --- |
| 高 | 元老院 / 政治系统 | 逻辑分散，后续腐败、审判、收买都会依赖 | 先重构再开发 P1 |
| 高 | 收入 / 经济系统 | 资金、合同、维护费、赔款耦合密集 | 先服务化再扩展 |
| 中高 | 广场阶段 | 已基本 API 化，但土地交易步骤仍有尾巴 | 补齐步骤4 |
| 中 | 战争 / 舰队 | 状态列表和合同生命周期复杂 | 保持一致性校验 |
| 中 | 人口阶段 | UI 优化完成，但仍有临时数据直改 | 后续逐步收束 |
| 中 | 多玩家 | 信息隔离已完成，但新功能容易破坏 | 每个任务都加多玩家验收 |
| 低中 | UI 输出 | 硬编码与 i18n 不统一 | GUI 前集中处理 |

## 项目经理派工建议

1. 不要直接让 DeepSeek 开始腐败、审判、收买等 P1 功能。
2. 先派发 `PoliticalSystem` 和 `EconomicService` 两个重构任务。
3. 每个任务必须附带文档、测试、验收口径。
4. 每次 DeepSeek 输出后，使用 `DeepSeek输出验收清单.md` 做验收。
5. 每轮任务结束后更新本表状态。

## 状态栏

| 日期 | 变更 |
| --- | --- |
| 2026-06-20 | 初版，基于 DeepSeek 项目回顾和 Codex 文档-代码一致性审计生成 |
| 2026-06-22 | AS-P0-01 `PoliticalSystem` 重构标记为已完成/已验收；补充阶段 A 状态跟踪与遗留技术债 |
| 2026-06-22 | AS-P0-02 `EconomicService` 重构完成 SA 边界审查与技术任务书定稿，进入 DeepSeek/DSD-02 实现交付环节 |
| 2026-06-22 | AS-P0-02 `EconomicService` 重构完成最终闭环，SA 验收 `PASS`，代码提交 `08295df`，79 项相关测试通过 |
| 2026-06-23 | AS-P0-04 广场阶段土地交易 API 化收尾完成最终闭环，SA 验收 `PASS`，代码提交 `24c1933`，87 项相关测试通过 |
| 2026-06-24 | AS-P0-03 完成 SA 当前基线只读审计与第一批技术边界定稿，技术任务已直接发布给 CGT-01，进入实现与验收阶段 |
| 2026-06-25 | AS-P0-03 完成最终闭环，SA `CONDITIONAL_PASS`，手工测试通过，全量测试 721 passed，提交 `6cc972e`；架构收口 Sprint 技术条件满足，等待项目负责人批准结束 |
| 2026-06-25 | 发布《P1功能最小可用GUI开发与验收标准》V1.0；后续 P1 功能同步交付最小 GUI，GUI-P1-02 负责最终完整迁移与产品化收尾 |
| 2026-06-28 | GUI-P0-01 MVP0.7 可玩 GUI 原型完成最终闭环，SA 验收 `PASS`，项目负责人手工测试通过，全量测试 734 passed，提交 `2b220bf`；后续进入 P1 功能增量开发与最小 GUI 同步交付阶段 |
| 2026-06-30 | AS-P1-01 API Response 统一完成最终闭环，SA 验收 `PASS`，focused 4 passed，API regression 144 passed，全量回归 738 passed，提交并推送 `01ebce2`；P1 API 返回结构进入统一基线 |
| 2026-07-01 | GUI-P0-02A GUI 主壳与阶段导航扩展及 R1 UI 反馈修正完成 Git 归档，提交 `b3d40b5`，CGT 全量测试 745 passed；GUI-P0 Sprint 下一步进入 GUI-P0-02B 天命 + 人口阶段 GUI 闭环 |
| 2026-07-02 | 发布 GUI-P0-02B 天命与人口阶段 GUI 闭环 PM 任务意图包给 SA，等待技术边界审查与开发任务书定稿 |
| 2026-07-02 | GUI-P0-02B 完成 SA 派工前技术边界审查，结论 `READY_FOR_TECH_TASK`；技术开发任务书已定稿并发布给 CGT-01，进入实现环节 |
| 2026-07-02 | GUI-P0-02B 完成主实现、R2 UX 修正、R3 生命周期修正；SA 技术复核 `CONDITIONAL_PASS / READY_FOR_MANUAL_GUI_CHECK`，技术线不再要求返工，等待项目负责人手工 GUI 验证与 Git 归档 |
| 2026-07-02 | GUI-P0-02B 完成最终闭环，项目负责人真实 GUI 手工验证通过，最终状态 `PASS`；提交并推送 `7426b38`，full `src\tests` 757 passed；GUI-P0 Sprint 下一步进入 GUI-P0-02C 元老院阶段 GUI 闭环 |
| 2026-07-03 | 发布 GUI-P0-02C 元老院阶段 GUI 闭环 PM 任务意图包给 SA；要求 SA 先拆分 Sprint 子任务，再逐个派工和验收 |

## 2026-07-05 GUI-P0-03 OPC-01 GUI重设计基线

| 任务 | 优先级 | 状态 | 说明 |
|---|---|---|---|
| GUI-P0-03 OPC-01 GUI重设计界面确认与实施拆分 | P0 | PM 意图包已生成，待 SA 界面确认 | 先确认界面与 Sprint 拆分，再向 CGT-01 派发开发任务。 |
