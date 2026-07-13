# PM 意图包 — Phase 1: Shell 外壳 + 天命阶段垂直切片

**Sequence Deliverable #1**
**角色：PM（奥古斯都）**
**日期：2026-07-11**
**代码基准：`main` (65bbf67)**
**来源讨论：克劳狄乌斯批准 Phase 1，要求先审查验收标准**

---

## Objective

将 EOR GUI 的 Shell 外壳区域（顶栏 / 阶段导航 / 右侧栏 / 底部栏 / 弹窗）视觉对齐 v3.25.1 HTML 原型，同时重建天命阶段的视觉呈现，形成一条完整的垂直切片。

目标：玩家在 Phase 1 交付后能看到 v3.25.1 风格的视觉外壳，并能完整走通天命阶段（执行→推进→进入收入阶段）。

---

## Problem

当前 QML GUI 与 v3.25.1 HTML 原型存在以下差距：

1. **Shell 视觉未对齐** — 顶栏字体/间距/颜色、阶段导航（176px 文本 vs 44px 圆形图标）、右侧栏布局、底部栏颜色、弹窗样式均与原型不符
2. **天命阶段视觉落后** — 缺乏步骤条引导、事件展示为普通矩形而非羊皮纸卡片风格、按钮样式未对齐
3. **战争数缺失** — 顶栏缺少活跃战争数量显示
4. **启动阶段硬编码风险** — `session_store.py` 中 `_selected_phase_id` 的 fallback 默认值存在不统一（`"revenue"` vs `"mortality"`），可能从错误阶段启动

---

## Scope

**明确纳入 Phase 1 的工作：**

| 区域 | 条目 | 动作 |
|------|------|------|
| **A 顶栏** | A1-A4, A7-A8 字体/间距/颜色对齐 | 样式更新 (Reuse) |
| **A 顶栏** | A6 新增 `warCount` | Store 新增 Property |
| **B 导航** | B1-B4 PhaseRail → 44px 圆形图标 + hover 名称弹出 | 新建 PhaseRailIcon.qml |
| **B 导航** | B5-B6 刷新/说明按钮保持 | 不动 |
| **C 右栏** | C1, C4-C8 内容区布局/日志终端风格对齐 | 样式更新 |
| **D 底栏** | D1 背景改为深朱红 | 视觉重建 |
| **D 底栏** | D2,D4,D10,D11 现有 4 查询按钮样式更新 | 样式更新 |
| **E 弹窗** | E1-E6 Modal/Overlay 视觉对齐 | 样式更新 |
| **F 天命** | F1-F3 徽章/标题/描述样式更新 | 样式更新 |
| **F 天命** | F4-F6 2 步骤引导条 | 新建 StepBar.qml |
| **F 天命** | F7-F14 事件展示区 → 羊皮纸卡片风格 | 视觉重建 |
| **F 天命** | F16-F19 执行/推进按钮样式更新 | 样式更新 |
| **修复** | SA-01: fallback phase 统一 | 修改 session_store.py |

---

## Out of Scope

以下内容 Phase 1 不做，推迟到后续 Phase：

| 条目 | 原因 |
|------|------|
| A5 稳定度展示 | 待产品规则确认 (Deferred) |
| C2 通用 advancePhase | Phase 2+ |
| C3 子步骤计数 DTO | Phase 2+ |
| F15 war_threat 类型确认 | 待确认 API 返回值 |
| G 收入阶段全区域 | Phase 2b |
| H 广场阶段全区域 | Phase 3 |
| I 人口阶段 | Phase 2a |
| J 元老院交互扩展 | Phase 4 |
| K+L 战争+决算 | Phase 5 |
| D 底部 8 个占位按钮 | Phase 6 |
| 非 QML 后端重构 | 不涉及 |

---

## Related Systems

| 系统 | 关联 | 是否修改 |
|------|------|:--------:|
| `src/ui/gui/qml/shell/GameShell.qml` | 阶段切换逻辑 | ❌ 不改 |
| `src/ui/gui/qml/shell/TopStatusBar.qml` | 顶栏视觉 | ✅ 样式改 |
| `src/ui/gui/qml/shell/PhaseRail.qml` | 阶段导航 | ✅ 组件替换 |
| `src/ui/gui/qml/shell/ContextPanel.qml` | 右侧栏 | ✅ 样式改 |
| `src/ui/gui/qml/shell/BottomQueryBar.qml` | 底部栏 | ✅ 样式改 |
| `src/ui/gui/qml/shell/QueryResultOverlay.qml` | 弹窗 | ✅ 样式改 |
| `src/ui/gui/qml/stages/MortalityStage.qml` | 天命阶段 | ✅ 视觉重建 |
| `src/ui/gui/session_store.py` | Store 层 | ✅ 新增 warCount + fallback 修复 |
| `src/api/mortality_api.py` | 天命 API | ❌ 不改 |
| `src/core/systems/` | 核心系统 | ❌ 不改 |
| `src/api/senate_api.py` | 元老院 API (warCount 来源) | ❌ 不改 |

---

## Relevant Documents

| 文档 | 路径（产品仓库 `docs/.../GUI需求/`） | 用途 |
|------|--------------------------------------|------|
| `GUI_CONTROL_MAPPING_MATRIX.md` | 138 元素控制映射 | 逐元素验证 |
| `GUI_DTO_GAP_REPORT.md` | DTO 差距汇总 | 数据层确认 |
| `GUI_PHASE_INTEGRATION_PLAN.md` | 6 Phase 路线图 + Phase 1 详细实施计划 | 实施依据 |
| `EOR_GUI_Prototype_v3.25.1.html` | HTML 原型 | 视觉参考 |
| `EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md` | 设计规范基线 | 一致性检查 |

---

## Architecture Impact

| 维度 | 评估 |
|------|------|
| 模块新增 | 2 个新 QML 组件（PhaseRailIcon.qml, StepBar.qml） |
| 模块修改 | 6 个现有 QML + 1 个 Store Python |
| API 变更 | **零** — 全部使用现有 API |
| 数据流变更 | 仅新增 `Store.warCount`（只读 Property，从 snapshot 读取） |
| 存档兼容 | 无影响 |
| 性能影响 | 无显著影响 |

---

## Data Model Impact

| 字段 | 来源 | 备注 |
|------|------|------|
| `Store.warCount` (新增) | `_snapshot → senate_view.summary.active_foreign_war_count` | 只读，无对应数据时隐藏 |

无 DTO 或数据模型变更。

---

## Balance Impact

**None** — 不涉及公式、参数、概率、经济、政治或战争平衡。

根据 §4.4 规则：Balance Impact = None → QGD 可不参与。

---

## Implementation Constraints

1. **无 API 变更** — Phase 1 所有数据依赖现有 API，不得新增后端接口
2. **无功能逻辑改动** — 所有按钮的 `onClicked` 绑定、Store 方法调用保持原样
3. **样式严格对齐 v3.25.1** — 以 `EOR_GUI_Prototype_v3.25.1.html` 为视觉参考，不得引入原型以外的设计元素
4. **每次只改一个文件，逐文件回归测试** — 避免碎片化修改难以定位问题
5. **fallback phase 必须先统一** — 在 Phase 1 编码前，SA 审查中必须确认 `_selected_phase_id` 的 fallback 行为

---

## Acceptance Criteria

| 编号 | 标准 | 验证方式 |
|------|------|---------|
| **AC1** | 顶栏显示：图标/国库/派系金库/影响力/回合/玩家；战争数从后端数据获取 | 手动检查 |
| **AC2** | 阶段导航为 44px 圆形图标，hover 显示名称，当前阶段高亮 | 手动检查 |
| **AC3** | 右侧面板显示当前阶段摘要/派系名/人物数 | 手动检查 |
| **AC4** | 底部栏深朱红，4 个有效查询按钮可用，占位按钮保持占位 | 手动检查 |
| **AC5** | 弹窗遮罩/标题/内容区视觉对齐 v3.25.1 | 手动检查 |
| **AC6** | 天命阶段显示 2 步骤条、羊皮纸事件卡片、执行/推进按钮 | 手动检查 |
| **AC7** | 天命按钮功能正常（执行→推进→进入收入阶段） | 手动启动游戏 |
| **AC8** | 回归测试 ≥773 passed（新增 0） | pytest |
| **AC9** | 从任意阶段启动游戏（非天命阶段），Shell 外壳正确反映当前阶段 | 手动检查（加载存档验证） |

---

## Test Plan

| 类型 | 内容 | 责任人 |
|------|------|--------|
| 回归测试 | 全量 pytest → ≥773 passed | DA |
| 视觉检查 | 逐区域比对 v3.25.1 HTML | SA 审查 |
| 功能验证 | 天命阶段完整走通（执行→推进→收入） | SA 审查 |
| 启动验证 | 非天命阶段存档启动，Shell 显示正确阶段 | SA 审查 |

无需新增测试（无 API 变更）。

---

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| PhaseRailIcon 44px 圆形图标不够清晰（中文环境） | 中 | 低 | 使用 HTML 字符映射 + hover 完整名称；SA 审查时确认 |
| 羊皮纸卡片 QML 实现性能开销 | 低 | 低 | 简单 Rectangle+Border+DropShadow，不用复杂纹理 |
| 现有 QML 样式改动破坏布局 | 低 | 中 | 每次只改一个文件，逐文件回归；SA 审查覆盖 |
| fallback phase 统一引入新的启动阶段问题 | 低 | 中 | SA 审查必须覆盖从任意阶段启动的验证 |

---

## Documentation Updates

| 文档 | 动作 |
|------|------|
| `SPRINT_BOARD.md` | 任务进入 IN_PROGRESS 后更新 |
| `workspace/handovers/` | DA 完成后的 Handover |
| `memory.md` | 更新项目记忆 |

---

## Decision Log Required

**No** — 本任务不涉及需要独立落盘的产品决策或 AI 治理决策。Phase 1 范围已在此前讨论中确认。

---

**交付状态：PM 意图包（Sequence Deliverable #1）— 完成 ✅**
**下一环节：提交 SA 进行边界审查**
