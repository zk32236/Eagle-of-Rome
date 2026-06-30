# GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包

创建日期：2026-06-30

发布对象：系统架构师 SA

任务性质：PM 级任务意图，不是 CGT-01/KIMI-01 技术开发任务书

## 一、任务信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | GUI-P0-02A |
| 任务名称 | GUI 主壳与阶段导航扩展 |
| 任务类型 | GUI 基础架构 / 阶段容器 / P0 核心 GUI 闭环前置 |
| 优先级 | P0.5 / P1 前置 |
| 所属 Sprint | GUI-P0 Sprint：MVP0.7/P0 核心 GUI 闭环 |
| 当前代码基线 | Git HEAD `51e0c07` |
| 当前项目根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| 正式文档根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| 前置状态 | P0 架构收口已完成；GUI-P0-01 可玩 GUI 原型已完成；AS-P1-01 API Response 统一已完成 |
| 任务输出责任 | SA 先做技术边界审查并定稿技术任务书，再安排实现与验收 |

## 二、背景说明

项目已经完成 P0 架构收口的大部分关键任务，并完成 GUI-P0-01 MVP0.7 可玩 GUI 原型。当前 GUI 已验证 PySide6/QML 路线可行，并完成人口阶段“庆典 + 公职投票 + 玩家交接 + 选举结果”的真实垂直切片。

在进入 P1 功能开发前，项目负责人确认应先补齐一个 **P0 核心 GUI 闭环 Sprint**，目标不是立即完成全部 CLI 到 GUI 产品化迁移，而是让 MVP0.7/P0 已有核心主干流程可以在 GUI 中连续运行，为后续 P1 功能的最小可用 GUI 交付提供稳定承接面。

GUI-P0 Sprint 暂定拆为 7 个任务：

| 顺序 | 任务编号 | 任务名称 | 覆盖范围 |
| --- | --- | --- | --- |
| 1 | GUI-P0-02A | GUI 主壳与阶段导航扩展 | 全局框架 |
| 2 | GUI-P0-02B | 天命 + 人口阶段 GUI 闭环 | 天命、人口 |
| 3 | GUI-P0-02C | 元老院阶段 GUI 闭环 | 元老院 |
| 4 | GUI-P0-02D | 收入 + 广场阶段 GUI 闭环 | 收入、广场 |
| 5 | GUI-P0-02E | 战争 + 海战阶段 GUI 闭环 | 战争、海战 |
| 6 | GUI-P0-02F | 革命/决算 + 回合推进 + 多玩家交接 | 革命、决算、回合切换 |
| 7 | GUI-P0-02G | MVP0.7/P0 GUI 一局验收与缺口收束 | 全流程验收 |

本任务是第一步，只负责扩展 GUI 主壳、阶段导航和通用状态/反馈框架。它不要求实现所有阶段业务操作，也不应提前吞并后续 B-F 阶段闭环任务。

## 三、PM 任务目标

请 SA 基于当前 GUI-P0-01 成果，完成 GUI-P0-02A 的技术边界审查和技术任务书定稿，目标是建立后续 6 个 GUI 子任务可复用的主框架：

1. 明确 GUI 主壳应如何承载完整回合阶段。
2. 明确阶段导航、阶段容器、全局状态栏、当前玩家区、反馈区、加载/错误状态的边界。
3. 明确 GUI Session/API/Store/Adapter 是否需要补强，以及补强范围。
4. 明确 GUI-P0-02A 与后续 GUI-P0-02B 到 GUI-P0-02G 的接口边界。
5. 定稿面向实现 Agent 的技术开发任务书。
6. 要求实现完成后能在 GUI 中看到完整阶段框架，但阶段内部复杂业务可以以占位/只读摘要/禁用入口方式承接后续任务。

## 四、依据文档

请 SA 优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\后续任务池.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\项目进度记录.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-01 MVP0.7可玩GUI原型 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-01 MVP0.7可玩GUI原型 技术开发任务书 - KIMI-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 五、允许修改范围

实际允许范围由 SA 技术任务书最终限定。PM 原则上允许：

| 范围 | 说明 |
| --- | --- |
| GUI 启动与主壳 | `gui_main.py`、GUI 应用壳层、GameShell、主窗口布局 |
| GUI QML/组件 | 导航、阶段容器、全局状态栏、反馈区、通用按钮/面板组件 |
| GUI Session/API/Store/Adapter | 仅限支持阶段导航、状态快照、当前玩家、错误反馈、刷新机制的薄接口 |
| GUI 测试 | `src/tests/test_gui` 下新增或调整主壳、导航、状态刷新、权限 smoke tests |
| 场景数据 | 如需补充 GUI 主壳测试场景，应保持最小且不影响现有场景 |
| 文档 | 本任务相关技术任务书、验收报告、GUI 运行说明 |

SA 不应开放无边界 Core 重构。若确需新增公开接口，必须说明原因、调用方、测试覆盖和函数索引同步要求。

## 六、禁止事项

- 不得实现或改写 P1 新玩法。
- 不得把 GUI-P0-02B 到 GUI-P0-02G 的阶段业务全部提前塞入本任务。
- 不得为了界面方便绕过 API 或直接调用 Core 私有字段。
- 不得在 GUI 层复制人口、元老院、收入、广场、战争等核心业务规则。
- 不得破坏 GUI-P0-01 已完成的人口阶段可玩切片。
- 不得破坏 CLI、自动模式、多玩家权限隔离和现有测试。
- 不得泄漏其他玩家不可见信息。
- 不得引入大范围视觉重做；继续沿用方案 A“共和国议事厅”的视觉方向。
- 不得提交临时文件、Excel 锁文件、缓存、日志或本地环境文件。

## 七、实现要求

SA 技术任务书应要求实现 Agent 至少完成：

1. 在现有 GUI-P0-01 基础上扩展主壳，使其能显示完整 MVP0.7/P0 阶段序列。
2. 提供稳定阶段导航结构，至少覆盖：天命、人口、元老院、收入、广场、战争/海战、革命/决算。
3. 提供统一阶段容器，后续阶段页面可在该容器内替换或挂载。
4. 提供全局状态摘要：回合、阶段、当前玩家、当前派系、国库/派系资金摘要、关键警告。
5. 提供统一操作反馈区，能展示成功、失败、权限拒绝、未实现/后续任务承接、加载中等状态。
6. 提供当前玩家与多玩家切换的只读展示基础，不要求本任务完成完整交接闭环。
7. 对尚未实现的阶段业务入口使用明确的“后续任务承接/暂不可操作”状态，不伪装为已完成。
8. 保持 GUI 状态来自权威 GameState/API 快照，不建立第二套权威状态。
9. 保留 GUI-P0-01 人口阶段已完成切片的入口和可用性。
10. 为后续 GUI-P0-02B 到 GUI-P0-02G 留出清晰扩展点。

## 八、调试日志要求

- GUI 启动、场景加载、阶段切换、状态刷新失败、API 调用失败应有可定位日志。
- 日志应包含阶段、当前玩家、操作类型、结果和错误摘要。
- 不应在正常渲染或高频刷新中输出大量低价值日志。
- 不得记录其他玩家隐藏信息。

## 九、测试要求

SA 技术任务书至少应要求：

| 测试类型 | 最低要求 |
| --- | --- |
| GUI 启动测试 | GUI 可启动并加载主壳，不出现空白主视图 |
| 阶段导航测试 | 阶段列表完整，切换到各阶段容器不崩溃 |
| 状态快照测试 | 回合、阶段、当前玩家、派系摘要可从权威状态刷新 |
| 反馈区测试 | 成功、失败、未实现、权限拒绝状态可显示 |
| 回归测试 | GUI-P0-01 人口阶段切片仍可用 |
| 权限 smoke test | 非当前玩家或不可操作状态不会暴露越权入口 |
| CLI/API 回归 | 相关 CLI/API 测试不退化 |
| 全量回归 | 由 SA 根据改动范围决定是否复跑 full regression，并记录结果 |

## 十、PM 验收标准

| 类别 | 验收标准 |
| --- | --- |
| 范围 | 只完成主壳、导航、通用状态、反馈和扩展点，不提前吞并后续阶段业务 |
| 可见阶段 | GUI 中可见完整 MVP0.7/P0 阶段序列 |
| 可扩展性 | 后续 GUI-P0-02B 到 GUI-P0-02G 能在同一阶段容器中增量接入 |
| 状态 | 全局状态摘要来自权威状态/API，不维护第二套权威状态 |
| 兼容 | GUI-P0-01 人口阶段切片、CLI、自动模式、多玩家隔离不退化 |
| 架构 | 保持 `GUI -> API -> Core/System/Service -> Entity` 方向 |
| 测试 | SA 指定 GUI 测试和相关回归通过 |
| 文档 | 技术任务书、实现报告和验收回执归档到正式 `docs` 路径 |

## 十一、交付物要求

### SA 派工前交付

1. GUI-P0-02A 技术边界审查报告。
2. GUI-P0-02A 技术开发任务书。
3. 对 GUI-P0-02B 到 GUI-P0-02G 的接口/扩展点说明。
4. 实现 Agent、允许修改范围、测试命令和验收口径。

### 实现 Agent 交付

1. 修改文件清单。
2. 主壳、阶段导航、状态区、反馈区实现摘要。
3. API/Session/Store/Adapter 变更说明。
4. 测试命令与结果。
5. 截图或可视验收材料。
6. 风险、遗留问题和后续 GUI-P0-02B 承接建议。

### SA 最终交付

1. `Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER`
2. `Reasons`
3. `Files reviewed`
4. `GUI architecture review`
5. `Test status`
6. `Regression risks`
7. `Required follow-up before GUI-P0-02B`

## 十二、PM 发布给 SA 的请求

请 SA 接收本 PM 任务意图包后，先完成 GUI-P0-02A 的技术边界审查。若确认范围合理，请定稿技术开发任务书并安排实现；若认为 GUI-P0-02A 范围过大或与 GUI-P0-02B 边界重叠，请先返回拆分建议，不要直接扩大实现范围。

本任务完成后，PM 将根据 SA 验收结果更新 GUI-P0 Sprint 进度，并准备 GUI-P0-02B「天命 + 人口阶段 GUI 闭环」任务意图。
