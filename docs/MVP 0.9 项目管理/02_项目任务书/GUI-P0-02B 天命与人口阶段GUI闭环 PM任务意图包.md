# GUI-P0-02B 天命与人口阶段 GUI 闭环 PM任务意图包

创建日期：2026-07-02

发布对象：系统架构师 SA

任务性质：PM 级任务意图，不是 CGT-01 技术开发任务书

## 一、任务信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | GUI-P0-02B |
| 任务名称 | 天命与人口阶段 GUI 闭环 |
| 任务类型 | GUI 阶段闭环 / P0 核心 GUI Sprint |
| 优先级 | P0.5 / P1 前置 |
| 所属 Sprint | GUI-P0 Sprint：MVP0.7/P0 核心 GUI 闭环 |
| 当前代码基线 | Git HEAD `815a58d` |
| 当前代码提交基线 | `b3d40b5` 已完成 GUI-P0-02A 主壳与阶段导航；`815a58d` 已完成 PM 进度归档 |
| 当前项目根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| 正式文档根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| 前置状态 | GUI-P0-02A 已完成；R1 UI 反馈修正已完成；阶段顺序已固化为 `天命-收入-广场-人口-元老院-战争-决算` |
| 任务输出责任 | SA 先做技术边界审查并定稿技术任务书，再安排实现与验收 |

## 二、背景说明

GUI-P0-02A 已完成 GUI 主壳、阶段导航、全局状态摘要、反馈区和锁定阶段占位能力。当前 GUI 已能承载完整阶段序列，但除 GUI-P0-01 已完成的人口阶段垂直切片外，其他阶段仍主要处于占位或待接入状态。

项目负责人已决定：在进入 P1 功能开发前，先完成 GUI-P0 Sprint，使 MVP0.7/P0 已有核心主干流程可以在 GUI 中连续运行。GUI-P0-02B 是该 Sprint 的第二步，目标是接入第一个真实阶段簇：**天命阶段 + 人口阶段**。

本任务应复用 GUI-P0-01 已完成的人口阶段“庆典 + 公职投票 + 玩家交接 + 选举结果”切片，并将其纳入 GUI-P0-02A 的新主壳、阶段导航和状态刷新机制。同时，补齐天命阶段的最小可玩 GUI 闭环，使玩家能在 GUI 中看到天命结果、理解影响，并继续推进到后续阶段。

注意：R1 已确认阶段顺序为 `天命-收入-广场-人口-元老院-战争-决算`。GUI-P0-02B 虽然同时覆盖天命与人口，但不得擅自改变阶段顺序，也不得要求天命后直接跳到人口。天命与人口可以作为同一开发包处理，但必须尊重真实回合流。

## 三、PM 任务目标

请 SA 基于 GUI-P0-02A 成果，完成 GUI-P0-02B 的技术边界审查和技术任务书定稿，目标是：

1. 将天命阶段接入 GUI 主壳，形成最小可玩闭环。
2. 将 GUI-P0-01 已有的人口阶段切片迁移/整合到 GUI-P0-02A 的阶段容器和导航体系中。
3. 保持阶段顺序 `天命-收入-广场-人口-元老院-战争-决算` 不变。
4. 明确天命阶段与人口阶段所需的 GUI Session/API/Adapter/Store 变化范围。
5. 保持 CLI、自动模式、多玩家权限隔离和已有 GUI 测试不退化。
6. 为后续 GUI-P0-02C 元老院阶段 GUI 闭环保留一致的页面、状态和反馈模式。

## 四、依据文档

请 SA 优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\后续任务池.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\项目进度记录.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A GUI主壳与阶段导航扩展 技术边界审查报告 - SA-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A-R1 UI反馈修正 SA复核回执.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 五、允许修改范围

实际允许范围由 SA 技术任务书最终限定。PM 原则上允许：

| 范围 | 说明 |
| --- | --- |
| GUI QML 页面/组件 | 天命阶段页面、人口阶段页面整合、阶段容器内的真实阶段内容、结果摘要和操作反馈 |
| GUI Session/API/Store/Adapter | 仅限支持天命阶段结果读取/推进、人口阶段现有切片接入、状态刷新、错误反馈的薄接口 |
| GUI 测试 | `src/tests/test_gui` 下新增或调整天命、人口阶段、阶段导航、状态刷新和 QML startup 测试 |
| API 测试 | 如补强天命/人口 API 或 session DTO，需补对应 API/adapter 测试 |
| 场景数据 | 如需补充 GUI-P0-02B 测试场景，应保持最小且不影响现有场景 |
| 文档 | 技术任务书、开发验收报告、SA 回执、必要的 GUI 运行说明 |

SA 不应开放无边界 Core 重构。若当前天命阶段缺少 GUI 安全 API/DTO，SA 应先判断是补薄 API，还是在本任务中仅做只读结果展示与继续推进；不得让 GUI 直接调用命令层输入输出流。

## 六、禁止事项

- 不得改变真实阶段顺序：`天命-收入-广场-人口-元老院-战争-决算`。
- 不得为了快速闭环让天命阶段直接跳到人口阶段。
- 不得新增 P1 新玩法、人物属性、经验、忠诚、腐败、审判或收买机制。
- 不得在 GUI 层复制天命、人口、公职投票、庆典、选举等核心业务规则。
- 不得绕过 API 或直接修改 `GameState`、System、Service、Entity 私有字段。
- 不得破坏 GUI-P0-02A 主壳、阶段导航、状态栏、反馈区和锁定阶段占位能力。
- 不得破坏 GUI-P0-01 已完成人口阶段垂直切片。
- 不得破坏 CLI、自动模式、多玩家信息隔离和现有测试。
- 不得泄漏其他玩家不可见信息。
- 不得把 GUI-P0-02C 元老院、GUI-P0-02D 收入/广场、GUI-P0-02F 回合推进等后续任务提前吞并。
- 不得提交临时文件、Excel 锁文件、缓存、日志或本地环境文件。

## 七、实现要求

SA 技术任务书应要求实现 Agent 至少完成：

1. 在 GUI-P0-02A 主壳中，将天命阶段从锁定/占位状态升级为真实可进入阶段页面。
2. 天命阶段页面应展示当前回合、当前阶段、天命结果/事件名称、效果摘要、影响对象和继续流程入口。
3. 天命阶段操作必须调用 GUI 安全 API/Session/Adapter，不得读取 CLI stdout 或模拟命令输入。
4. 天命阶段完成后，应按真实阶段顺序继续到收入阶段或当前系统定义的下一阶段，不得私自跳转到人口阶段。
5. 将 GUI-P0-01 的人口阶段切片接入 GUI-P0-02A 阶段容器，保持庆典、公职投票、玩家交接、选举结果流程可用。
6. 人口阶段页面应沿用统一状态栏、反馈区、错误提示和刷新机制，不维护第二套权威状态。
7. 人口阶段应正确处理当前玩家、AI 玩家、HUMAN 玩家交接和权限隔离。
8. 对本任务未覆盖的收入、广场、元老院、战争、决算阶段，继续使用明确的锁定/后续任务承接状态。
9. GUI 文案应接入 GUI-P0-02A 已建立的 i18n 预留机制，新增文本不得无序散落。
10. 若新增公共接口、DTO 或 adapter 方法，应在开发报告中说明调用方、返回结构、错误语义和后续文档同步需要。

## 八、调试日志要求

- 天命阶段进入、结果读取、效果应用、继续推进失败应有可定位日志。
- 人口阶段关键操作失败、权限拒绝、状态刷新失败应有可定位日志。
- 日志应包含阶段、当前玩家、操作类型、对象标识和结果摘要。
- 不得记录其他玩家隐藏信息。
- 正常渲染和高频状态刷新不得产生大量无价值日志。

## 九、测试要求

SA 技术任务书至少应要求：

| 测试类型 | 最低要求 |
| --- | --- |
| GUI 启动测试 | GUI 可启动并显示 GUI-P0-02A 主壳、阶段导航和状态栏 |
| 天命阶段测试 | 可进入天命页面，显示天命结果/效果摘要，并通过 API/Session 推进 |
| 阶段顺序测试 | 天命完成后不跳过真实阶段顺序；阶段导航顺序保持 `天命-收入-广场-人口-元老院-战争-决算` |
| 人口阶段回归 | GUI-P0-01 人口阶段庆典、投票、玩家交接、选举结果仍可用 |
| 状态刷新测试 | 天命和人口操作后，GUI 从权威状态刷新，不出现局部假状态 |
| 权限测试 | 当前玩家可操作，非当前玩家或不可见信息不泄漏 |
| Adapter/API 测试 | 新增或调整的 session/API/adapter 方法覆盖成功、失败和错误结构 |
| CLI 回归 | 人口阶段、天命相关 CLI/API 关键路径不退化 |
| 自动模式回归 | AI 行动和自动路径不退化 |
| 全量回归 | CGT-01 如按任务书完整跑 full `src/tests` 并报告充分，SA 可按当前规范选择复核而非重复全量；高风险或证据不足时 SA 应补跑 |

## 十、PM 验收标准

| 类别 | 验收标准 |
| --- | --- |
| 范围 | 只完成天命与人口阶段 GUI 闭环，不提前吞并后续阶段 |
| 天命阶段 | 玩家可在 GUI 中看到天命结果、理解影响，并按真实阶段顺序继续 |
| 人口阶段 | GUI-P0-01 人口切片在新主壳中仍可完成庆典、投票、玩家交接和选举结果 |
| 阶段顺序 | 保持 `天命-收入-广场-人口-元老院-战争-决算` |
| 状态 | 全局状态、阶段内容和操作反馈来自权威状态/API |
| 架构 | 保持 `GUI -> API -> Core/System/Service -> Entity`，GUI 不承载核心业务规则 |
| 兼容 | CLI、自动模式、多玩家隔离和 GUI-P0-02A 主壳不退化 |
| 测试 | SA 指定 GUI/API/adapter/人口回归测试通过，必要时 full regression 通过 |
| 文档 | 技术任务书、开发验收报告、SA 回执归档到正式 `docs` 路径 |

## 十一、交付物要求

### SA 派工前交付

1. GUI-P0-02B 技术边界审查报告。
2. GUI-P0-02B 技术开发任务书。
3. 天命阶段 GUI/API/Session 接入边界说明。
4. 人口阶段现有切片迁移/整合方案。
5. 实现 Agent、允许修改范围、测试命令和验收口径。

### 实现 Agent 交付

1. 修改文件清单。
2. 天命阶段 GUI 闭环实现摘要。
3. 人口阶段 GUI 整合与回归说明。
4. API/Session/Store/Adapter 变更说明。
5. 测试命令与结果。
6. 风险、遗留问题和后续 GUI-P0-02C 承接建议。

### SA 最终交付

1. `Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER`
2. `Reasons`
3. `Files reviewed`
4. `GUI architecture review`
5. `Stage flow review`
6. `Test status`
7. `Regression risks`
8. `Required follow-up before GUI-P0-02C`

## 十二、PM 发布给 SA 的请求

请 SA 接收本 PM 任务意图包后，先完成 GUI-P0-02B 的技术边界审查。若确认范围合理，请定稿技术开发任务书并安排实现；若发现天命阶段 API/Session 基础不足，或人口阶段旧切片与新主壳整合存在边界风险，请先返回技术收束建议，不要让实现 Agent 自行决定阶段边界。

本任务完成后，PM 将根据 SA 验收结果更新 GUI-P0 Sprint 进度，并准备 GUI-P0-02C「元老院阶段 GUI 闭环」任务意图。
