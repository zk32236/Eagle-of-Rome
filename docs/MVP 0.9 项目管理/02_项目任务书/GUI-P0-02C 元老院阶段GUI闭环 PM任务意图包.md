# GUI-P0-02C 元老院阶段 GUI 闭环 PM任务意图包

创建日期：2026-07-03

发布对象：系统架构师 SA

任务性质：PM 级任务意图，不是 CGT-01 技术开发任务书

## 一、任务信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | GUI-P0-02C |
| 任务名称 | 元老院阶段 GUI 闭环 |
| 任务类型 | GUI 阶段闭环 / P0 核心 GUI Sprint / 高风险政治阶段接入 |
| 优先级 | P0.5 / P1 前置 |
| 所属 Sprint | GUI-P0 Sprint：MVP0.7/P0 核心 GUI 闭环 |
| 当前代码基线 | Git HEAD `4d2fbf8` |
| 已完成前置 | GUI-P0-02A 主壳与阶段导航；GUI-P0-02B 天命与人口阶段 GUI 闭环 |
| 当前项目根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| 正式文档根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| 任务输出责任 | SA 先拆分小 Sprint、完成技术边界审查，再逐个定稿子任务并安排实现与验收 |

## 二、背景说明

GUI-P0 Sprint 当前已完成：

1. GUI-P0-02A：主壳、阶段导航、状态栏、反馈区和占位阶段容器。
2. GUI-P0-02B：天命阶段 GUI 安全入口、人口阶段切片整合、`MortalityService` / `mortality_api` 收束。

按照 GUI-P0 Sprint 顺序，下一阶段应接入元老院阶段。元老院阶段是 MVP0.7/P0 的高风险核心阶段，涉及 `PoliticalSystem`、`senate_api`、提案、投票、宣战、停战、预算、总督任命、战争接管、多玩家权限和自动模式。它也是后续 P1 腐败、审判、收买、人物政治互动等功能的关键承接面。

本任务复杂度较高，项目负责人明确要求：**不得把 GUI-P0-02C 当作一个大而全的单体开发任务。SA 必须使用 Sprint 式拆分方法，将其分割为若干个较小、较简单、可单独验证闭环的子任务，逐步完成元老院阶段 GUI 接入。**

## 三、PM 任务目标

请 SA 接收本 PM 意图包后，先完成 GUI-P0-02C 的拆分规划与技术边界审查，而不是直接给 CGT-01 一个大任务。

PM 对 GUI-P0-02C 的总目标是：

1. 在 GUI 中接入 MVP0.7/P0 元老院阶段主干流程。
2. 让玩家可以查看元老院阶段状态、议题/提案、投票信息、关键结果和下一步流程。
3. 逐步接入 P0 既有政治动作：宣战、停战/停战草案、预算、总督任命、战争接管等。
4. 保持 `GUI -> API -> Core/System/Service -> Entity` 依赖方向。
5. 保持 `senate_api` 薄 API 层与 `PoliticalSystem` 系统层边界，不让 GUI 直接调用 `phase_senate.py`。
6. 保持自动模式、手动模式、多玩家权限隔离和 GUI-P0-02A/02B 成果不退化。
7. 不新增 P1 政治玩法。

## 四、SA 必须执行的 Sprint 拆分要求

SA 应先输出 **GUI-P0-02C Sprint 拆分方案**，再决定每个子任务的技术任务书。

PM 建议拆分方向如下，SA 可调整，但必须保持“小任务、可闭环、可单独验收”：

| 建议子任务 | 目标 | 验收闭环 |
| --- | --- | --- |
| GUI-P0-02C-1 | 元老院阶段只读状态与导航接入 | GUI 可进入元老院页，显示阶段、当前玩家、可见摘要、锁定/可操作状态，不执行政治动作 |
| GUI-P0-02C-2 | 提案/议题列表与详情展示 | GUI 通过 API/Session 展示当前提案、议题类型、发起者、影响对象、表决状态 |
| GUI-P0-02C-3 | 基础投票闭环 | 支持玩家对已存在提案投票、显示成功/失败/权限拒绝、刷新投票结果 |
| GUI-P0-02C-4 | 宣战/战争接管类动作接入 | 只接入 P0 既有动作，保持 `senate_api`/`PoliticalSystem` 边界，补相关测试 |
| GUI-P0-02C-5 | 停战草案/预算/总督任命动作接入 | 分批接入剩余 P0 高风险动作，避免一次性吞并全部复杂逻辑 |
| GUI-P0-02C-6 | 元老院阶段完成与推进闭环 | 完成阶段结果确认、自动/AI 路径、阶段完成标记、进入下一阶段占位或后续阶段 |
| GUI-P0-02C-R | 缺口收束与人工 GUI 验证修正 | 只修复 02C 子任务验收发现的 UI/权限/刷新/文案问题，不新增范围 |

如果 SA 判断上述拆分不合理，应返回调整后的拆分表，并说明每个子任务：

- 子任务编号
- 子任务目标
- 允许修改范围
- 禁止事项
- 测试要求
- 可独立验收的闭环标准
- 是否可并行或必须串行
- 对后续子任务的依赖

## 五、依据文档

请 SA 优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\后续任务池.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\项目进度记录.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-02A GUI主壳与阶段导航扩展 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-02B 天命与人口阶段GUI闭环 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02B 天命与人口阶段GUI闭环 技术边界审查报告 - SA-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

重点代码路径：

- `src/api/senate_api.py`
- `src/core/systems/political_system.py`
- `src/ui/commands/phase_senate.py`
- `src/api/session_api.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/tests/test_api/test_senate_api.py`
- `src/tests/test_commands/test_phase_senate.py`
- `src/tests/test_systems/test_political_system.py`
- `src/tests/test_gui`

## 六、允许修改范围

实际允许范围由 SA 在每个子任务技术任务书中最终限定。PM 原则上允许：

| 范围 | 说明 |
| --- | --- |
| GUI QML 页面/组件 | 新增或扩展 SenateStage 页面、提案列表、投票控件、结果反馈、权限提示 |
| GUI Session/API/Store/Adapter | 仅限支持元老院阶段快照、提案视图、投票动作、阶段结果刷新 |
| `senate_api` 薄接口补强 | 仅限 GUI 安全 DTO、明确错误语义、保持 `{success, message, data, errors}` |
| `PoliticalSystem` 公共接口补强 | 仅限确有必要的系统层方法，不得新增 P1 玩法 |
| GUI 测试 | 新增元老院阶段 GUI smoke、状态、权限、投票闭环测试 |
| API/系统测试 | 相关 `senate_api`、`PoliticalSystem`、阶段命令回归 |
| 文档 | 子任务技术任务书、开发验收报告、SA 回执、必要的 GUI 运行说明 |

## 七、禁止事项

- 不得把 GUI-P0-02C 作为一个大而全的单体任务直接派给 CGT-01。
- 不得在 GUI 层实现或复制元老院政治规则。
- 不得让 GUI 直接调用 `phase_senate.py`、CLI command、stdout/input 或旧命令流。
- 不得绕过 `senate_api` 直接调用 `PoliticalSystem` 执行玩家操作，除非 SA 明确设计为只读 DTO 查询且不执行动作。
- 不得绕过 `PoliticalSystem` 在 API/GUI 层自行处理提案、投票、战争接管、停战、预算或总督任命规则。
- 不得直接修改 `_senate_pending`、`_phase_results`、战争私有列表、总督候任字段或其他私有字段。
- 不得新增 P1 玩法：腐败、审判、人物收买、忠诚、人物属性、经验等。
- 不得破坏 GUI-P0-02A 主壳、GUI-P0-02B 天命/人口闭环、CLI、自动模式和多玩家权限隔离。
- 不得泄漏其他玩家不可见信息。
- 不得提交临时文件、Excel 锁文件、缓存、日志或本地环境文件。

## 八、实现要求

SA 应在拆分方案和各子任务技术任务书中确保：

1. 每个子任务都有可独立运行、可独立验收的 GUI 闭环。
2. 每个子任务范围足够小，失败时可以局部回退或返工，不影响整个 02C Sprint。
3. 只读展示优先于写操作；高风险动作必须在只读信息结构稳定后再接入。
4. 投票闭环应先于复杂动作创建闭环，因为投票是元老院阶段通用基础。
5. 宣战、战争接管、停战草案、预算、总督任命等动作应分批处理。
6. 所有玩家动作通过 `senate_api` 或 SA 定义的 GUI 安全 API/Session/Adapter 入口。
7. 操作完成后必须从权威状态刷新，不建立第二套 GUI 权威状态。
8. 非当前玩家、不可见议题、不可操作状态必须显示明确反馈并禁止越权操作。
9. 自动模式/AI 路径如果本子任务不处理，必须明确保留为占位或后续子任务。
10. 每个子任务完成后，SA 应决定是否可以进入下一个子任务。

## 九、调试日志要求

- 元老院阶段进入、状态快照失败、提案读取失败、投票失败、权限拒绝、阶段推进失败应有可定位日志。
- 日志应包含阶段、当前玩家、操作类型、提案/战争/人物标识和结果摘要。
- 不得记录其他玩家隐藏信息。
- 正常渲染和高频刷新不得产生大量低价值日志。

## 十、测试要求

SA 应为每个子任务指定最小测试集，并在整个 02C Sprint 末尾要求完整回归。

| 测试类型 | 最低要求 |
| --- | --- |
| GUI 启动测试 | GUI 主壳、阶段导航和元老院页面可加载 |
| 元老院只读测试 | 阶段状态、当前玩家、提案摘要、权限状态可展示 |
| 投票/API 测试 | 投票成功、失败、重复投票、权限拒绝、错误结构 |
| 高风险动作测试 | 宣战、停战、预算、总督任命等按子任务范围分别覆盖 |
| 状态刷新测试 | 操作后从权威状态刷新，不出现局部假状态 |
| 多玩家测试 | 当前玩家可操作，其他玩家不可越权或看到隐藏信息 |
| CLI 回归 | `phase_senate.py` 相关关键路径不退化 |
| 系统/API 回归 | `test_senate_api.py`、`test_political_system.py`、相关阶段测试 |
| GUI 回归 | `src/tests/test_gui` 相关测试通过 |
| full regression | Sprint 收束时执行 full `src/tests` 或由 SA 基于风险明确说明采信依据 |
| 质量检查 | `git diff --check` passed，仅 CRLF 提示可接受 |

## 十一、PM 验收标准

| 类别 | 验收标准 |
| --- | --- |
| 拆分 | SA 已输出可执行的 GUI-P0-02C Sprint 子任务拆分方案 |
| 小闭环 | 每个子任务可以单独验收，不依赖一次性完成整个元老院阶段 |
| 架构 | 保持 `GUI -> API -> Core/System/Service -> Entity`，不出现 GUI/API -> UI command 反向依赖 |
| 政治边界 | 玩家动作经 `senate_api` / `PoliticalSystem` 正确边界执行 |
| 功能 | 元老院阶段 P0 主干最终可在 GUI 中完成 |
| 兼容 | CLI、自动模式、多玩家权限、GUI-P0-02A/02B 不退化 |
| 测试 | 每个子任务测试通过，Sprint 收束有完整回归或充分采信依据 |
| 文档 | 拆分方案、子任务书、开发验收报告、SA 回执均归档到正式 `docs` 路径 |

## 十二、交付物要求

### SA 首轮交付

1. GUI-P0-02C 技术边界审查报告。
2. GUI-P0-02C Sprint 子任务拆分方案。
3. 第一批子任务技术开发任务书，建议从只读状态/导航接入开始。
4. 子任务执行顺序、依赖关系和是否可并行说明。
5. 每个子任务的验收测试要求。

### 实现 Agent 子任务交付

1. 修改文件清单。
2. 子任务实现摘要。
3. API/Session/Store/Adapter 变更说明。
4. 测试命令与结果。
5. 风险、遗留问题和下一子任务承接建议。

### SA 每轮验收交付

1. `Decision: PASS / CONDITIONAL_PASS / RETURN_FOR_REWORK / DEFER`
2. `Reasons`
3. `Files reviewed`
4. `GUI architecture review`
5. `Senate API / PoliticalSystem boundary review`
6. `Test status`
7. `Regression risks`
8. `Next subtask recommendation`

## 十三、PM 发布给 SA 的请求

请 SA 接收本 PM 任务意图包后，先完成 GUI-P0-02C 的技术边界审查和 Sprint 子任务拆分方案。

PM 明确要求：

1. 不要直接把 GUI-P0-02C 作为一个大任务派给 CGT-01。
2. 先拆成若干个小的、较简单的、可单独验证闭环的子任务。
3. 每个子任务完成后由 SA 独立验收，再进入下一个子任务。
4. 如果 SA 判断第一个子任务应仅为“元老院只读状态与导航接入”，PM 支持该收束。
5. 后续 PM 将根据 SA 的拆分方案，把 GUI-P0-02C Sprint 纳入进度跟踪。
