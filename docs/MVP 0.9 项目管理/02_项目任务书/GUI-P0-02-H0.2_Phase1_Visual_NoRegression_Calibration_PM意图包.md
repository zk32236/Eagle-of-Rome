# PM 意图包 — GUI-P0-02-H0.2

**Date:** 2026-07-12  
**Status:** Ready for DA  
**Reference:** Codex instruction → `03_开发与验收/GUI-P0-02/GUI-P0-02-H0.2_Phase1_Visual_NoRegression_Calibration_OC指令 -- Codex.md`

---

## Objective

修复 Phase 1 天命界面实测截图中的视觉回退，重点是 C 区 (StageDesktop) 四槽位垂直层级和颜色校准。

## Scope

### C 区 — StageDesktop（重点）

1. **StageHeaderSlot** — 徽章 `1 / 7`、标题 `天命阶段`、说明文案清晰显示在桌面顶部，不半透明
2. **StageInstructionSlot** — 步骤条紧跟 header 下方，done/current/todo 三态清晰
3. **StageContentSlot** — 空状态提示位于信息框/卡片内，不漂浮在桌面中部偏左
4. **StageActionSlot** — `执行天命` 按钮位于 action slot 底部居中，不漂浮在桌面视觉中心
5. 中央桌面保持象牙白 (`#F2EEE4`)，不出现深色横区

### B/D 区 — 颜色校准

- B 左栏背景：偏紫 → 深墨/深棕 (`#14110D` / `#15110D`)
- D 右栏背景：偏紫 → 深墨/深棕，EventLog 不压垮上方 section

### A/E 区 — 轻微校准

- A 顶栏、E 底栏：仅做颜色/边框微调，不重排

### Test Baseline

- GUI startup 7/7
- Full regression ≥ 773

## Out of Scope

- ❌ Core/System/Service/Entity
- ❌ Store/API 扩展
- ❌ 非 Mortaliy 阶段功能
- ❌ 重新设计整体 GUI
- ❌ 改变 A-F 主区域尺寸契约 (layout contract)

## Allowed Files

```
src/ui/gui/qml/theme/Theme.qml
src/ui/gui/qml/shell/GameShell.qml
src/ui/gui/qml/shell/StageDesktop.qml
src/ui/gui/qml/shell/PhaseRail.qml
src/ui/gui/qml/components/PhaseRailIcon.qml
src/ui/gui/qml/shell/ContextPanel.qml
src/ui/gui/qml/shell/BottomQueryBar.qml
src/ui/gui/qml/stages/MortalityStage.qml
src/tests/test_gui/
```

## Deliverables

1. 修改文件清单
2. 修复摘要
3. A-F 区域差异表（目标 vs 修复后表现）
4. GUI startup 测试 7/7
5. 回归测试 ≥ 773
6. 保持/允许/禁止合规说明
