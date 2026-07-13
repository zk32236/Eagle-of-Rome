# SA Phase 1 Layout Report — GUI-P0-02-F & GUI-P0-02-G

**Date:** 2026-07-11  
**Agent:** SA Sub-Agent (disposable)  
**Tasks:** F (Layout Contract Extraction) → G (Static QML Shell Skeleton)

---

## 1. Report Path

```
E:\OpenClaw\Projects\EOR\agents\SA\reports\2026-07-11-sa-f-g-report.md
```

---

## 2. Deliverables Produced

### Task F — Layout Contract

| File | Status |
|------|--------|
| `E:\OpenClaw\Projects\EOR\agents\SA\reports\GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` | **NEW** — 12 sections covering A-F regions |

### Task G — QML Shell Skeleton

| File | Status | Change Summary |
|------|--------|---------------|
| `src/ui/gui/qml/shell/StageDesktop.qml` | **NEW** | Ivory #FAF5EE panel with 4 named slots (StageHeaderSlot / StageInstructionSlot / StageContentSlot / StageActionSlot) |
| `src/ui/gui/qml/shell/GameShell.qml` | **MODIFIED** | Main-wrapper 8px padding via anchor margins; TopStatusBar→48px, PhaseRail→44px, ContextPanel→240px, BottomQueryBar→48px; replaced inline centerPanel with StageDesktop component; preserved "stageAnnouncement" + "stageContainer" objectNames for DA slot content |
| `src/ui/gui/qml/shell/ContextPanel.qml` | **MODIFIED** | Added section-named objectNames: currentPhaseSection, operationSection, progressSection, playerSection, eventLogSection |
| `src/ui/gui/qml/shell/BottomQueryBar.qml` | **MODIFIED** | Height corrected to 48px (was 42px) |
| `src/ui/gui/qml/stages/MortalityStage.qml` | **MODIFIED** | Restructured with slot-aware objectNames: mortalityHeaderSlot, mortalityInstructionSlot, mortalityContentSlot, mortalityActionSlot. Layout uses ColumnLayout with stacked sections matching slot architecture. Execute button now in dedicated bottom slot with anchor-centered positioning |
| `src/ui/gui/qml/shell/PhaseRail.qml` | **unmodified** | Already 44px rail, 34px circles ✓ |
| `src/ui/gui/qml/shell/TopStatusBar.qml` | **unmodified** | Already 48px height, #8B2500 bg, 5 stat blocks ✓ |
| `src/ui/gui/qml/components/PhaseRailIcon.qml` | **unmodified** | Already 34px circles, 3 states ✓ |
| `src/ui/gui/qml/components/StepBar.qml` | **unmodified** | Keep as-is ✓ |

---

## 3. Key Findings

1. **HTML prototype has NO BottomQueryBar DOM**. The `.op-bar` CSS class exists but no `<div class="op-bar">` element is instantiated in the body. The BottomQueryBar exists only in the existing QML implementation and CSS spec.

2. **Layout contract dimensions conflict with visual polish overrides**. The original CSS (48px header, 44px rail, 240px panel) differs from Codex override values (62px header, 92px rail, 286px panel). This contract uses the **original CSS values** as specified in the task parameters.

3. **StageDesktop as component required backward-compat aliases**. The test `test_main_qml_exposes_core_gui_regions` expects objectNames "centerPanel", "stageAnnouncement", and "stageContainer". StageDesktop.qml uses objectName "centerPanel" and GameShell.qml places the stageAnnouncement/stageContainer Rectangles inside the corresponding slots with parent reassignment, preserving test compatibility.

4. **MortalityStage action button remains inside MortalityStage itself** (action slot at bottom) rather than being lifted into StageDesktop.StageActionSlot. This is because each phase has different action buttons and GameShell currently delegates phase content to stage components. Full slot extraction would require a separate DA task.

---

## 4. Test Results

```
src/tests/test_gui/test_qml_startup.py::test_main_qml_loads_root_window             PASSED
src/tests/test_gui/test_qml_startup.py::test_main_qml_exposes_core_gui_regions       PASSED
src/tests/test_gui/test_qml_startup.py::test_opc_shell_exposes_twelve_bottom_query_buttons PASSED
src/tests/test_gui/test_qml_startup.py::test_shell_store_exposes_seven_phase_navigation_items PASSED
src/tests/test_gui/test_qml_startup.py::test_shell_text_catalog_labels_treasury      PASSED
src/tests/test_gui/test_qml_startup.py::test_senate_stage_detail_copy_uses_gui_text_catalog PASSED
src/tests/test_gui/test_qml_startup.py::test_opc_shell_boundary_and_i18n_scans       PASSED
All 7 GUI tests + 766 other tests = 773 passed in 25.87s
```

No regressions. All boundary checks (no hardcoded Chinese text, no forbidden API calls, no scattered copy) pass.

---

## 5. Unresolved Issues

| # | Issue | Severity | Recommendation |
|---|-------|----------|---------------|
| 1 | **BottomQueryBar placement undefined in layout contract**. The HTML prototype has no `<div class="op-bar">` DOM element — it exists only as CSS. The layout contract treats E as a sibling of main-wrapper. Existing QML anchors it to parent.bottom with 8px margins. | Low | Accept current implementation. If DA needs different positioning, update contract after visual confirmation. |
| 2 | **Stage action buttons are phase-specific, not generic**. Each phase (mortality, revenue, forum, etc.) has its own action button label and handler. StageDesktop.StageActionSlot is empty by default. MortalityStage.qml contains its own action slot internally. | Medium | Future task (GUI-P0-02-H) should lift action buttons into StageDesktop.StageActionSlot with DA binding. |
| 3 | **StepBar.qml exists but is unused by MortalityStage**. MortalityStage has its own inline steps bar rather than using the StepBar component. | Low | Can be refactored in a later visual-consolidation task. |
| 4 | **Layout contract uses original CSS values, not v3.25.1 visual refit overrides**. The v3.25 HUD density CSS increases header to 62px, rail to 92px, and panel to 286px. The task specified 48/44/240, so the contract follows those. If Codex v4.0 values are intended, a follow-up calibration is needed. | Medium | Confirm with PM whether Phase 1 should use original CSS values or v3.25.1 visual-refit values. |

---

## 6. Recommended Next Action

**GUI-P0-02-H — Phase 1 天命内容填充与 Store/API 绑定** (as specified in SA-DA spec v1.1 §九):

1. Place mortality phase content inside StageDesktop.StageContentSlot (currently MortalityStage fills it via stageContainer).
2. Bind `GuiSessionStore.doExecuteMortality()` to the action button in StageDesktop.StageActionSlot (lift from MortalityStage's internal slot).
3. Move phase header/badge/description into StageDesktop.StageHeaderSlot.
4. Move step indicator into StageDesktop.StageInstructionSlot using StepBar.qml component.
5. Verify 1440×900 layout contract dimensions with a real screenshot.
6. Produce pixel-level acceptance table (§四.4 of SA-DA spec v1.1).

**Immediate prerequisite:** Resolve unresolved issue #4 (original vs. v3.25.1 refit dimensions) before proceeding with DA content filling.
