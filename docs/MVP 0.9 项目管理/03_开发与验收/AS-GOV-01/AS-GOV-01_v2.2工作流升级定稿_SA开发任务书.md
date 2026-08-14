# AS-GOV-01 v2.2 工作流升级定稿 — SA 开发任务书

> 版本：v1.0
> 日期：2026-07-15
> 编写人：SA Sub-Agent
> 参考：PM Intent Package `02_项目任务书/AS-GOV-01_v2.2工作流升级定稿_PM意图包.md`
> 上位 Workflow：`workflows/pm-sa-da-sequence-workflow.md` v2.2（评审包草案基准）

---

## 一、任务背景

CODEX 已完成 v2.2 评审包的审查，结论为"有条件通过，建议小修后定稿"。评审发现 6 项口径/一致性问题需在定稿前修正。修正后的 v2.2 内容需部署到正式资产文件。

本任务书按 PM Subtask Plan 中的 S1 子任务编制：**将 CODEX 6 项修正应用到 v2.2 草案文件**。

---

## 二、任务目标

1. v2.2 评审包草案文件中 6 项 CODEX 评审问题已修正
2. 修正后文件保持内部一致性（版本引用、术语、路径）
3. 不破坏现有结构的完整性

---

## 三、依据文档

| 文档 | 路径 |
|------|------|
| CODEX 评审报告 | `workspace/diagnostics/CODEX_EOR_v2.2工作流升级评审包_评审报告_2026-07-15.md` |
| v2.2 评审包变更清单 | `workspace/diagnostics/v2.2_review_package_2026-07-15/change-manifest.md` |
| PM Intent Package | `02_项目任务书/AS-GOV-01_v2.2工作流升级定稿_PM意图包.md` |
| v2.2 草案 workflow | `workspace/diagnostics/v2.2_review_package_2026-07-15/workflows/pm-sa-da-sequence-workflow_v2.2.md` |
| v2.2 草案 SA prompt | `workspace/diagnostics/v2.2_review_package_2026-07-15/agents/SA/prompts/sa-task-launch-prompt_v2.2.md` |
| v2.2 草案 DA prompt | `workspace/diagnostics/v2.2_review_package_2026-07-15/agents/DA-Exec/prompts/da-exec-task-launch-prompt_v2.2.md` |
| v2.2 草案 SA soul | `workspace/diagnostics/v2.2_review_package_2026-07-15/agents/SA/soul/sa-soul_v2.2.md` |
| v2.2 草案 SA memo | `workspace/diagnostics/v2.2_review_package_2026-07-15/agents/SA/memo/sa-operating-memory_v2.2.md` |
| v2.2 草案 PM 模板 | `workspace/diagnostics/v2.2_review_package_2026-07-15/prompts/PM-任务意图包模板_v2.2.md` |
| v2.2 草案 role governance | `workspace/diagnostics/v2.2_review_package_2026-07-15/bible/role-and-agent-governance_v2.2.md` |

> 基础路径：`E:\OpenClaw\Projects\EOR\workspace\diagnostics\v2.2_review_package_2026-07-15\`

---

## 四、本轮允许修改范围

### 修改文件（S1 — 修正草案文件）

| # | 文件（评审包草案） | 修正内容 |
|---|-------------------|---------|
| F1 | `workflows/pm-sa-da-sequence-workflow_v2.2.md` | 6 项修正中的 4 项（口径统一、交付路径、Phase 2.75、timeout 量化） |
| F2 | `agents/SA/prompts/sa-task-launch-prompt_v2.2.md` | 默认读取负载拆分 + 交付路径说明 |
| F3 | `agents/SA/soul/sa-soul_v2.2.md` | 交付路径说明 + PLAN_ISSUE 认知 |
| F4 | `agents/SA/memo/sa-operating-memory_v2.2.md` | 交付路径说明 |

### 新建文件（无 — S1 仅修改）

### 不修改文件（S1）
- `agents/SA/memo/sa-operating-memory_v2.2.md`（仅在需要时微量修正路径引用）
- `agents/DA-Exec/prompts/da-exec-task-launch-prompt_v2.2.md`（DA prompt 在 S3 部署时更新）
- `bible/role-and-agent-governance_v2.2.md`（在 S3 部署时确认一致性）
- `prompts/PM-任务意图包模板_v2.2.md`（已含 Subtask Plan，不需修正）
- `change-manifest.md`（变更记录，不修改）

---

## 五、实施顺序（Step 1-6）

### Step 1: 修正 v2.2 workflow — Task Sizing Gate 口径统一

**文件：** `workflows/pm-sa-da-sequence-workflow_v2.2.md`

**改动：**
- §Phase 1.5 中冲突表述统一：触发条件后"必须拆分判断，默认应拆分为串行或并行子任务"
- 如 PM 判断仍作为单任务处理，必须在 Subtask Plan 中写明：
  - 不拆分理由
  - 风险
  - 等待/超时策略
  - 为什么不会造成子代理过载

### Step 2: 修正 v2.2 workflow — 新增 Phase 2.75 DA Task Sizing Check

**文件：** `workflows/pm-sa-da-sequence-workflow_v2.2.md`

**改动：**
- 在 §4 流程图中 Phase 2.5 与 Phase 3 之间插入 Phase 2.75 节点
- 新增 §Phase 2.75 说明段落
- 检查条件：DA Development Task 是否涉及修改文件 > 5、跨 API/Adapter/Store/QML/Tests 多层
- 若触发 → PM 应拆分 DA 子任务或要求 SA 修订 Development Task

### Step 3: 修正 v2.2 workflow + SA prompt — 交付路径澄清

**文件：** `workflows/pm-sa-da-sequence-workflow_v2.2.md` + `agents/SA/prompts/sa-task-launch-prompt_v2.2.md`

**改动（workflow）：**
- 在 §6 交付件体系/或 §4 Phase 2 末尾新增"双路径"说明：
  - 正式交付件 → 产品 `docs/MVP 0.9 项目管理/03_开发与验收/<TASK-ID>/`
  - 代理内部报告 → `agents/<ROLE>/reports/`（可选副本）

**改动（SA prompt）：**
- Report to 路径保留为 `agents/SA/reports/` 但增加注释：此为代理内部运行留痕
- 要求优先写入 Development Task 指定的正式产品 docs 路径

### Step 4: 修正 v2.2 workflow — Deadlock Rules timeout 量化

**文件：** `workflows/pm-sa-da-sequence-workflow_v2.2.md`

**改动：**
- §Deadlock Rules 中"多次"改为具体量化：
  - 连续 2 次 wait_agent timeout → Main Session 发送一次状态追问
  - 状态追问后 1 个等待窗口仍无回复 → 标记 SUBAGENT_RUNTIME_FAILURE
  - 通过文档接替

### Step 5: 修正 v2.2 workflow + SA soul — 新增 PLAN_ISSUE

**文件：** `workflows/pm-sa-da-sequence-workflow_v2.2.md` + `agents/SA/soul/sa-soul_v2.2.md`

**改动（workflow）：**
- §Rework Routing 新增第三种问题类型：PLAN_ISSUE
- PLAN_ISSUE 定义：PM Subtask Plan 不可执行或会导致子代理过载
- 路径：SA 返回 PLAN_ISSUE → PM 修订 Intent Package/Subtask Plan → 重新进入 Task Sizing Gate
- 流程图 RETURN 分支补充 PLAN_ISSUE
- SA 验收内容增加 PLAN_ISSUE 判别依据

**改动（SA soul）：**
- SA 职责中补充 RETURN 可附带 PLAN_ISSUE 的说明

### Step 6: 降低 SA prompt 默认读取负载

**文件：** `agents/SA/prompts/sa-task-launch-prompt_v2.2.md`

**改动：**
- 将当前"Read before executing"列表拆分为：
  - **Mandatory minimal**（4 项）：soul、memo、workflow、当前 PM Intent Package
  - **Task-relevant only**（按需）：根据 Subtask Plan 指定，仅读取与当前子任务相关的文件
- 增加说明：若 Subtask Plan 指定本轮无 GUI 任务，不读取 layout-contract-skill 等文件

---

## 六、各文件改动详情

### F1: `workflows/pm-sa-da-sequence-workflow_v2.2.md`

| 区域 | 当前内容（摘要） | 改为 |
|------|----------------|------|
| §Phase 1.5 冲突表述 | "若满足任一条件，PM 必须在 Intent Package 中完成 Subtask Plan 并拆分任务" + "触发 Sizing Gate 不等于必须并行拆分" | 统一为：触发条件后必须完成切片判断。默认应拆分为串行或并行子任务。如仍作为单任务处理，必须在 Subtask Plan 中写明不拆分理由、风险、等待/超时策略、不会造成子代理过载的说明 |
| 流程图 | Phase 1.5 → Phase 2 | Phase 1.5 → Phase 2 → Phase 2.5 → **Phase 2.75** → Phase 3 |
| §4 新增段落 | 无 Phase 2.75 | 插入 Phase 2.75 — DA Task Sizing Check 完整说明段落 |
| §6 交付件 | 仅单路径 | 增加双路径说明段落 |
| §Deadlock Rules | "多次 wait_agent timeout" | 量化：连续2次 timeout → 追问；追问后1窗口无回复 → SUBAGENT_RUNTIME_FAILURE |
| RETURN 分支 | TASK_ISSUE / DA_ISSUE 两种 | 增加 PLAN_ISSUE：PM Subtask Plan 不可执行 |
| §返工路径 | 两种问题类型 | 三种问题类型（+ PLAN_ISSUE） |

### F2: `agents/SA/prompts/sa-task-launch-prompt_v2.2.md`

| 区域 | 当前 | 改为 |
|------|------|------|
| Read before executing | 9 项必读 | 拆为 Mandatory minimal（4 项）+ Task-relevant only（按需引用 + 说明条件） |
| Report to 路径 | `agents/SA/reports/` 单路径 | 保留此路径但注明为"代理内部运行留痕"；增加说明"优先写入 Development Task 指定的正式产品 docs 路径" |

### F3: `agents/SA/soul/sa-soul_v2.2.md`

| 区域 | 当前 | 改为 |
|------|------|------|
| Phase A 职责 | 未提及 PLAN_ISSUE | 增加：SA 在 Task Design 阶段发现 Subtask Plan 不可执行时，可返回 PLAN_ISSUE |
| Phase B 验收 | 仅 APPROVED/RETURN（TASK_ISSUE/DA_ISSUE） | RETURN 增加 PLAN_ISSUE 类型说明 |

### F4: `agents/SA/memo/sa-operating-memory_v2.2.md`

| 区域 | 当前 | 改为 |
|------|------|------|
| 无变动 | — | 仅确认路径引用正确，无需改动 |

---

## 七、Acceptance Criteria

| # | 验收项 | 验证方式 |
|---|--------|---------|
| AC1 | Phase 1.5 口径统一：触发条件后必须完成切片判断，默认拆分；不拆分需写明理由和风险 | 读取 workflow 对应段落 |
| AC2 | 流程图含 Phase 2.75（DA Task Sizing Check）节点 | 读取 workflow 流程图 |
| AC3 | Phase 2.75 有完整说明段落（触发条件、PM 处理动作） | 读取 workflow §4 |
| AC4 | 正式交付路径与 agent report 路径已明确区分 | 读取 workflow §6 + SA prompt |
| AC5 | SA prompt 已拆分为"最小必读 + 按任务读取" | 读取 SA prompt |
| AC6 | Deadlock Rules timeout 已量化（连续2次→追问→1窗口→SUBAGENT_RUNTIME_FAILURE） | 读取 workflow Deadlock 段 |
| AC7 | RETURN 分支含 PLAN_ISSUE 类型及其路径 | 读取 workflow 流程图 + 返工路径段 |
| AC8 | SA soul 补充 PLAN_ISSUE RETURN 说明 | 读取 SA soul |
| AC9 | 所有修正文件内部版本引用一致 | 交叉检查各文件的版本字符串和引用路径 |
| AC10 | 旧内容未被误删 | git diff 确认 |
| AC11 | 前置条件保障：不涉及产品代码修改 | 确认所有改动仅限于文档/治理文件 |

---

## 八、测试策略

- 本任务为文档修改，无需运行测试
- 验证方式：
  - 逐项读取确认（AC1-AC8）
  - 交叉引用一致性检查（AC9）
  - git diff 验证（AC10）
  - 版本号/引用路径扫描（AC9）

---

## 九、回滚计划

| 场景 | 回滚措施 |
|------|---------|
| 修正后发现语义不一致 | git checkout 草案文件原始版本，重新应用修正 |
| 修正过于激进超出了 Intent 范围 | 按 change-manifest 确认修正边界，撤回越界部分 |
| 文件版本引用链断裂 | 逐文件检查版本字符串，修正不一致项 |

回滚基准：评审包中 `v2.2_review_package_2026-07-15/` 下各文件的原始内容。

---

## 十、实施约束

1. 仅修改评审包草案文件（`v2.2_review_package_2026-07-15/`），不修改正式资产文件
2. 不删除旧版本文件
3. 不改动产品代码文件
4. 不改动 v2.2 草案非本任务范围的其他内容
5. 保持各文件间版本引用、术语、路径的一致性

---

## 十一、交付件交付检查清单

| # | 检查项 | 
|---|--------|
| [ ] | workflow_v2.2.md — Phase 1.5 口径统一 |
| [ ] | workflow_v2.2.md — Phase 2.75 新增段落 |
| [ ] | workflow_v2.2.md — 交付路径双路径说明 |
| [ ] | workflow_v2.2.md — Deadlock Rules timeout 量化 |
| [ ] | workflow_v2.2.md — PLAN_ISSUE 返工路径 |
| [ ] | workflow_v2.2.md — 流程图 RETURN 分支含 PLAN_ISSUE |
| [ ] | SA prompt_v2.2.md — 默认读取负载拆分为 Mandatory + Task-relevant |
| [ ] | SA prompt_v2.2.md — 交付路径说明更新 |
| [ ] | SA soul_v2.2.md — PLAN_ISSUE RETURN 补充 |
| [ ] | 各文件版本引用链一致性验证 |
| [ ] | 上下文水位报告 |

---

## 十二、交付路径

### 正式交付件
```
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\
  03_开发与验收\AS-GOV-01\
    AS-GOV-01_v2.2工作流升级定稿_SA开发任务书.md  ← 本文件
```

### 代理内部报告（可选副本）
```
E:\OpenClaw\Projects\EOR\agents\SA\reports\
```

---

## 十三、Revision History

| 版本 | 日期 | 变更说明 | 编写人 |
|------|------|---------|--------|
| v1.0 | 2026-07-15 | 初始版本 | SA Sub-Agent |

---

## 十四、本任务主类型

**主类型：Governance/Process Update**
- 非 GUI 开发任务，不涉及 Visual-State Contract 或 Layout Contract
- 涉及 4 个文档文件的多处修订（F1-F4）
- 需保持跨文件一致性

不违反产出物单一原则：Development Task 是唯一主要产物。
