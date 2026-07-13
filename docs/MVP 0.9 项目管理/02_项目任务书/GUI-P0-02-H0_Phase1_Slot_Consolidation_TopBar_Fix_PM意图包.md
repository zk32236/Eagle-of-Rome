# PM 意图包 — Phase H0: 槽位收束 + TopBar 修复

**修正版本：Codex Review v2 → v3 前置任务**
**角色：PM（奥古斯都）**
**日期：2026-07-12**
**代码基准：`main` (post-GUI-P0-02-D Phase 1 合并)**
**来源：Codex v2 Review (2026-07-12) — 有条件通过，3 个未闭合问题**

---

## Objective

解决 Codex GUI-P0-02-F/G v2 Review 中标记的 3 个未闭合问题，为 v3 重新提交扫清障碍：

1. **StageDesktop 槽位未成为唯一承载结构** — `MortalityStage` 自建了平行槽位（header / instruction / action），与 `StageDesktop` 的通用槽位设计冲突
2. **TopStatusBar 栏位稳定性问题** — 稳定度硬编码为 `78`（应为 Store 派生字段），战争栏存在条件隐藏
3. **测试证据不足** — GUI startup / shell layout 无明确测试结果

目标：在 **不引入新功能、不修改后端、不触及其他阶段** 的前提下，完成结构修正，使 v3 审查号通过。

---

## Problem

### 问题 A — StageDesktop 槽位未成为唯一承载结构

`StageDesktop.qml` 定义了 4 个通用槽位（`headerArea`、`contentArea`、`footerArea`、`sidePanelArea`），意图作为**所有阶段内容**的唯一主承载结构。但 `MortalityStage.qml` 在核心内容区（`contentArea`）内部又自建了平行槽位结构：

- `header` 区域（徽章 + 标题 + 步骤条）
- `instruction` 区域（描述文本 + 提示）
- `action` 区域（执行 / 推进按钮 + 事件卡片列表）

导致 `StageDesktop` 的 4 槽位设计被架空，破坏了阶段性组件复用契约。**其他阶段若也照此模式实现，将导致布局结构碎片化，无法统一维护。**

### 问题 B — TopStatusBar 栏位硬编码与条件隐藏

`TopStatusBar.qml` 存在以下问题：

1. **稳定度硬编码**：稳定度显示固定值 `"78"`，未从 Store 或 snapshot 派生
2. **战争栏条件隐藏**：战争数/战争信息栏位带有条件判断，在数据不可用时完全隐藏，导致顶栏栏位数量不稳定、布局抖动

此问题在此前 Codex v1 审查中已标记（Deferred），现需在 H0 中闭环。

### 问题 C — 测试证据不足

GUI-P0-02-D Phase 1 任务未包含：
- GUI startup 初始化测试
- Shell 布局结构性测试
- 像素级验收核对（A-F 验收表）

Codex 审查时只能依赖 DA 声称的"手工检查通过"，缺乏可复现的自动验证证据。

---

## Scope

### A. MortalityStage 槽位归位到 StageDesktop 4 槽位

将 `MortalityStage.qml` 内部的自建平行槽位（header / instruction / action）内容重新分布到 `StageDesktop` 的通用 4 槽位中：

| 原 MortalityStage 区域 | 目标 StageDesktop 槽位 | 内容 |
|------------------------|------------------------|------|
| header 区域（徽章 + 标题 + 步骤条） | `headerArea` | 徽章、阶段标题、2 步骤引导条（StepBar） |
| instruction 区域（描述文本 + 提示） | `contentArea`（顶部子区） | 阶段描述、当前事件说明、操作提示 |
| action 区域（按钮 + 事件卡片列表） | `contentArea`（中部子区） + `footerArea` | 事件卡片列表在 contentArea，执行/推进按钮在 footerArea |
| — | `sidePanelArea` | (预留，保持为空或放置上下阶段指示) |

### B. 删除 / 降级 MortalityStage 内部平行槽位

- 删除 `MortalityStage.qml` 中自建的 `RowLayout` / `ColumnLayout` 头部分组结构
- 不再在 `MortalityStage` 内部定义 `property alias header` / `property alias instruction` / `property alias action`
- MortalityStage 的主体变为：`StageDesktop` 的纯消费者，内容全部通过槽位注入
- 若某个槽位不适用，保留为空状态（`visible: false`），而不是另起结构

### C. 修复 TopStatusBar 稳定度硬编码

- 将硬编码的 `"78"` 替换为 `Store.stability ?? "--"`
- 若 Store 层无对应 field，则在 `session_store.py` 新增 `stability` Property，从 snapshot 读取（例如 `snapshot.get("stability", "--")`）
- 确保 UI 显示与后端实际值一致，而非固定值

### D. 修复战争栏条件隐藏

- 战争栏位（warCount / warInfo）从条件隐藏改为**始终显示**
- 缺值情况下显示 `"--"`
- 消除布局条件抖动：不在 `visible` 上做数据依赖判断，只在内容显示上做 fallback

### E. 补充 GUI startup / shell 测试

新增测试覆盖：

| 测试 | 文件 | 内容 |
|------|------|------|
| GUI startup 初始化测试 | `test_gui_startup.py` 或 `test_shell_integration.py` | 验证 GameShell 创建成功、各子组件（StageDesktop, TopStatusBar 等）非空 |
| Shell 布局结构性测试 | `test_shell_layout.py` | 验证 StageDesktop 4 槽位均存在、TopStatusBar 所有栏位可见（无条件隐藏）、MortalityStage 无自建平行槽位残留 |
| TopStatusBar 数据绑定测试 | `test_top_status_bar.py` | 验证稳定度绑定 Store、战争栏始终可见、缺值显示 "--" |
| MortalityStage 槽位消费测试 | `test_mortality_stage.py` | 验证 MortalityStage 内容正确分布在 StageDesktop 4 槽位中 |

### F. 提供 1440×900 截图 + A-F 像素验收表

1. **截图 1**: 天命阶段完整截图（1440×900），标注 A-F 区
2. **截图 2**: TopStatusBar 特写（1440×900 顶栏裁剪），标注稳定度与战争栏
3. **像素验收表**（表格形式，按 QML 实际像素值填写）：

| 区域 | 属性 | 预期值 | 实际值 | 状态 |
|------|------|--------|--------|:----:|
| A headerArea | width | 1440 | ... | Pending |
| A headerArea | height | ... | ... | Pending |
| B contentArea (顶部) | width | ... | ... | Pending |
| B contentArea (中部) | ... | ... | ... | Pending |
| C footerArea | width | ... | ... | Pending |
| D sidePanelArea | (预留空) | — | — | Pending |
| E TopStatusBar 稳定度 | text | Store.stability | ... | Pending |
| F TopStatusBar 战争栏 | visible | true | ... | Pending |

---

## Out of Scope

以下内容 **不属于 H0**，推迟到后续 Phase 或独立任务：

| 条目 | 原因 |
|------|------|
| Core / System / Service / Entity 层修改 | 非 GUI 层，H0 不触及 |
| 新阶段业务规则 | H0 仅修正结构，不引入功能 |
| 新增查询功能（底部栏新按钮等） | 属于 Phase 扩展 |
| 新增后端 API | Phase 1 已确认零 API 变更，H0 继承此约束 |
| PopulationStage / SenateStage 等非 Mortality 阶段 | H0 仅处理 MortalityStage |
| 新 StageDesktop 槽位设计（增删槽位） | 不改变 4 槽位契约 |
| 其他阶段（Revenue / Forum / War / Settlement）的迁移 | 分阶段处理，H0 仅验证死亡率阶段 |
| 弹窗 / 底部栏 / 右侧栏的修改 | Phase 1 已完成，本次不动 |

---

## Files Likely to Change

| 文件 | 动作 | 说明 |
|------|:----:|------|
| `src/ui/gui/qml/stages/MortalityStage.qml` | ✅ 重构 | 删除自建平行槽位，内容通过 StageDesktop 槽位注入 |
| `src/ui/gui/qml/shell/StageDesktop.qml` | ✅ 修改 | 确保 4 槽位均可用，slot 绑定正确 |
| `src/ui/gui/qml/shell/GameShell.qml` | ✅ 修改 | 若需要在阶段加载时对槽位做额外初始化绑定 |
| `src/ui/gui/qml/shell/TopStatusBar.qml` | ✅ 修改 | 替换稳定度硬编码；战争栏改为始终显示 |
| `src/ui/gui/session_store.py` | ✅ 修改 | 新增 stability Property（从 snapshot 读取，只读） |
| `src/ui/gui/stages/`（tests） | ✅ 新增 | GUI startup / shell 测试文件 |
| `docs/.../验收/` | ✅ 新增 | 像素验收表 + 截图标注 |

### 不受影响文件

| 文件 | 说明 |
|------|:----:|:------|
| `src/core/systems/*` | 不改 |
| `src/api/*` | 不改 |
| `src/domain/*` | 不改 |
| `src/infrastructure/*` | 不改 |
| `src/ui/gui/qml/stages/PopulationStage.qml` | 不改 |
| `src/ui/gui/qml/stages/SenateStage.qml` | 不改 |
| 其他阶段 QML | 不改 |

---

## Architecture Impact

| 维度 | 评估 |
|------|------|
| 模块新增 | 0 个新 QML 组件；新增 3-4 个测试文件（Python） |
| 模块修改 | 4 QML + 1 Store Python 文件 |
| API 变更 | **零** |
| 数据流变更 | 仅新增 `Store.stability`（只读 Property，从 snapshot 读取） |
| 存档兼容 | 无影响 |
| 性能影响 | 无显著影响 |
| 组件契约变更 | StageDesktop 4 槽位从"可选建议"升级为"唯一主承载结构" |

---

## Data Model Impact

| 字段 | 来源 | 备注 |
|------|------|------|
| `Store.stability` (新增) | `_snapshot → mortality_view.stability` (或等价路径) | 只读，缺省时显示 "--" |

无 DTO 或数据模型变更。`Store.warCount` 已在 Phase 1 中新增，本次不再重复。

---

## Balance Impact

**None** — 不涉及公式、参数、概率、经济、政治或战争平衡。

---

## Implementation Constraints

1. **零 API 变更** — 任何数据必须从现有 `_snapshot` 读取，不得新增后端接口
2. **不触及其他阶段** — H0 只处理 `MortalityStage`，`PopulationStage`、`SenateStage` 等其他阶段保留原样
3. **不引入新功能** — H0 是修正任务，不是功能扩展。所有变更只为解决 v2 review 中标记的 3 个问题
4. **每次只改一个文件，逐文件回归测试** — 避免碎片化修改难以定位
5. **像素验收表作为检查清单** — 验收表中的每一项在提交前必须填写实际值并确认

---

## Acceptance Criteria

| 编号 | 标准 | 验证方式 |
|------|------|:--------:|
| **AC-H0-01** | StageDesktop 的 4 槽位（headerArea / contentArea / footerArea / sidePanelArea）全部启用，MortalityStage 不自行创建平行槽位结构 | QML 源码审查 |
| **AC-H0-02** | MortalityStage 的徽章、标题、步骤条位于 `headerArea` | 源码审查 + 截图标注 |
| **AC-H0-03** | MortalityStage 的当前事件描述、操作提示位于 `contentArea` | 源码审查 + 截图标注 |
| **AC-H0-04** | MortalityStage 的执行/推进按钮位于 `footerArea` | 源码审查 + 截图标注 |
| **AC-H0-05** | MortalityStage 中不存在 `property alias header` / `property alias instruction` / `property alias action` | grep 确认 |
| **AC-H0-06** | TopStatusBar 中稳定度显示从 `Store.stability` 派生，无硬编码数值 | 源码审查 |
| **AC-H0-07** | TopStatusBar 战争栏始终可见（`visible: true`），缺值时显示 `"--"` | 源码审查 + 测试 |
| **AC-H0-08** | 所有新增测试运行通过（GUI startup test / shell layout test / TopStatusBar binding test / MortalityStage slot test） | pytest |
| **AC-H0-09** | 回归测试 ≥ 773 passed（与 Phase 1 基线一致） | pytest |
| **AC-H0-10** | A-F 像素验收表全部填写并核对一致 | 截图 + 表格 |
| **AC-H0-11** | 从任意阶段启动游戏，Shell 正确渲染，无布局错乱 | 手动验证 |

---

## Test Plan

| 类型 | 内容 | 责任人 |
|------|------|:------:|
| 回归测试 | 全量 pytest → ≥ 773 passed | DA |
| 新增单元测试 | GUI startup 初始化测试 | DA |
| 新增单元测试 | Shell layout 结构性测试（4 槽位/栏位可见性） | DA |
| 新增单元测试 | TopStatusBar 数据绑定测试（稳定度/战争栏） | DA |
| 新增单元测试 | MortalityStage 槽位消费测试 | DA |
| 视觉检查 | 1440×900 截图标注验收 | SA 审查 |
| 像素验收表 | A-F 各区实际像素核对 | SA 审查 |
| 功能验证 | 天命阶段完整走通（执行→推进→收入） | SA 审查 |
| 启动验证 | 非天命阶段存档启动，Shell 布局正确 | SA 审查 |

---

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| 其他阶段（PopulationStage, SenateStage）后续也使用了类似 MortalityStage 的平行槽位模式，H0 修正后这些阶段会与 StageDesktop 契约不一致 | 高 | 中 | CI 执行 — H0 声明本次仅处理 MortalityStage。后续各阶段重构时，PR 模板需检查槽位契约合规。**已建立清单，作为 H 阶段准入条件** |
| 槽位归位后布局偏移（例如 headerArea 内元素过多导致高度变化） | 中 | 中 | 像素验收表涵盖 A-F 各区实际像素值，SA 审查时逐项确认 |
| Store.stability 对应 snapshot 路径不确定 | 中 | 低 | 需与 DA 确认 backend snapshot 结构中是否已有稳定性值；若无则使用 store-safe 占位 `"--"`，不新增后端字段 |
| pytest 新增测试需要 qmltestrunner 或 PyQt 环境可用 | 低 | 高 | 若 QML 测试环境不可用，改为 shell 脚本 + QML scene graph dump 验证，或 DA 手工截图验收替代 |

---

## Documentation Updates

| 文档 | 动作 |
|------|------|
| `SPRINT_BOARD.md` | 任务进入 IN_PROGRESS 后更新 |
| `workspace/handovers/` | DA 完成后的 Handover |
| `memory.md` | 更新项目记忆 |

---

## Decision Log Required

**No** — 本任务是 Codex v2 review 提出的修正要求，不涉及需要独立落盘的产品决策。

---

## Reference Documents

| 文档 | 路径 | 用途 |
|------|------|------|
| GUI-P0-02-D Phase 1 任务书 | `02_项目任务书/GUI-P0-02-D_Phase1_Shell_Mortality_PM意图包.md` | Phase 1 上下文、Architecture Impact、约束继承 |
| Codex v2 Review 结论 | Codex 审查日志 (2026-07-12) | 3 个未闭合问题的详细描述 |
| StageDesktop.qml (当前版本) | `src/ui/gui/qml/shell/StageDesktop.qml` | 4 槽位定义确认 |
| MortalityStage.qml (当前版本) | `src/ui/gui/qml/stages/MortalityStage.qml` | 需重构的平行槽位结构 |
| TopStatusBar.qml (当前版本) | `src/ui/gui/qml/shell/TopStatusBar.qml` | 需修复的硬编码 + 条件隐藏 |

---

**交付状态：PM 意图包（H0 修正任务）— 完成 ✅**
**下一环节：提交 SA/Codex 确认范围后，分配给 DA 实施**
