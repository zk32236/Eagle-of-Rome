# PM 意图包 — GUI-P0-02-H

**Date:** 2026-07-12  
**Status:** Draft → Ready for SA Review  
**Next:** SA Boundary Review → DA Execution

---

## Objective

完成 Phase 1 天命阶段内容填充与 Store/API 绑定，使 MortalityStage 在游戏运行中可交互。

## Prerequisites (已通过)

| 前置 | 状态 |
| --- | --- |
| GUI-P0-02-F/G v2 (布局契约 + Shell骨架) | ✅ 有条件通过 |
| GUI-P0-02-H0 (Slot Consolidation + TopBar Fix) | ✅ 通过 |
| GUI-P0-02-H0.1 (PhaseRailIcon Startup Fix) | ✅ 773 passed |
| StageDesktop 四槽位 | ✅ 已启用 |
| MortalityStage (精简为内容区) | ✅ 已就绪 |

## Scope

1. **StageDesktop 槽位绑定** — 确保四槽位正确引用 Mortality 数据
   - `stageHeaderSlot`: 天命 badge + title + description (从 sessionStore 读取)
   - `stageInstructionSlot`: 步骤条 (基于阶段状态)
   - `stageContentSlot`: MortalityStage 内容区 (事件列表)
   - `stageActionSlot`: 执行天命按钮 (绑定 doExecuteMortality)

2. **MortalityStage 内容绑定**
   - 事件列表: `sessionStore.mortalityEvents` → UI 事件卡片
   - 空状态提示: 无事件时的指导文案
   - `showFeedback()` 回调

3. **状态绑定表** — 输出 QML 属性 ↔ Store 字段的完整映射

4. **测试与验收证据**
   - GUI startup 测试 (7/7)
   - 完整回归 (≥773 passed)
   - 1440×900 运行截图
   - A-F 像素级验收表
   - 状态绑定表

## Out of Scope

- ❌ Core/System/Service/Entity 修改
- ❌ 其他阶段 (Population, Senate, Forum 等)
- ❌ 新阶段业务规则
- ❌ 新查询功能
- ❌ 新后端 API
- ❌ 存档兼容
- ❌ AI 参数调整

## Related Files

```
src/ui/gui/qml/shell/GameShell.qml
src/ui/gui/qml/shell/StageDesktop.qml
src/ui/gui/qml/stages/MortalityStage.qml
src/ui/gui/qml/shell/TopStatusBar.qml
src/ui/gui/qml/components/PhaseRailIcon.qml
src/ui/gui/qml/theme/Theme.qml (reference only)
src/ui/gui/session_store.py (reference only — Store API contract)
```

## Architecture Impact

- 仅限 QML + Store 层绑定
- 不修改 Core 数据模型
- 不修改后端 API
- 不新增 Store 字段（使用现有）

## Acceptance Criteria

| # | Criteria | Verification |
| --- | --- | --- |
| AC-H-01 | Mortality 阶段能正确加载 | 截图 |
| AC-H-02 | 顶部栏显示天命 header (badge/title/desc) | 截图 |
| AC-H-03 | 步骤条显示正确状态 | 截图 |
| AC-H-04 | 事件区域正常显示/提示 | 截图 |
| AC-H-05 | 执行天命按钮可点击 | 截图 |
| AC-H-06 | 按钮返回结果正常显示 | 截图或测试 |
| AC-H-07 | 状态绑定表交付 | 文档 |
| AC-H-08 | A-F 像素验收表 | 文档 |
| AC-H-09 | 回归测试 ≥ 773 passed | 测试报告 |
| AC-H-10 | GUI startup 测试 7/7 passed | 测试报告 |

## Test Plan

```text
python3 -m pytest src/tests/test_gui/test_qml_startup.py -v  (7 passed)
python3 -m pytest src/tests/ -q  (≥773 passed)
```

## Risks

- `sessionStore.mortalityEvents` 为 `null` 或空时的边界处理
- `sessionStore.doExecuteMortality()` 的返回值处理
- 无头测试环境无法生成实际截图 → 需截图环境可用时手动补充

## Decision Log Required

No new product-level decisions expected.
