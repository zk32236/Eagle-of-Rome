# CODEX Work Instruction — GUI-P0-02-CX1

## Task Title
Phase 1 Central Page Hierarchy Rendering Failure — Independent Diagnosis and Repair

## Task Type
Specialist Code Diagnosis / Targeted GUI Repair

## Priority
P1 — Blocking Visual Defect

## Background

OpenClaw / DA has already attempted to repair the missing central page information hierarchy by modifying:

- `src/ui/gui/qml/shell/StageDesktop.qml`
  - `stageHeaderSlot` preferred height: `implicitHeight` → `80`
  - `stageInstructionSlot` preferred height: `32` → `50`

The DA report states that this should restore:

- Stage badge
- Stage title
- Stage description
- Workflow / progress strip
- Instruction card

The report also states:

- GUI startup tests: `7 passed`
- Full regression: `773 passed`
- Only two lines in one QML file were changed

However, the latest runtime screenshot still shows the same central failure:

- stage badge remains effectively invisible
- stage title remains effectively invisible
- stage description remains effectively invisible
- workflow strip remains effectively invisible
- instruction card is not rendered as the approved design
- only faint, partially collapsed text is visible near the top-left of the parchment area

Therefore, the previous root-cause conclusion is incomplete or incorrect.

Reference implementation report:

- `GUI-P0-02-H0-5_Phase1_Hierarchy_Fix_DA开发报告.md`

Reference screenshot:

- `GUI acutal phase 1 - 7.PNG`

---

# Objective

Independently diagnose and repair the actual runtime cause of the Phase 1 central information hierarchy rendering failure.

The task is not to perform another cosmetic adjustment.

The task is to determine why the hierarchy remains visually collapsed or invisible despite explicit slot heights and passing tests, then implement the smallest safe repair.

---

# Required Investigation

Codex shall trace the full runtime rendering chain for the Phase 1 centre workspace, including at minimum:

1. `StageDesktop.qml`
2. the component loaded into `stageHeaderSlot`
3. the component loaded into `stageInstructionSlot`
4. the Phase 1 content component
5. any `Loader`, `Component`, `StackLayout`, `ColumnLayout`, `anchors.fill`, `visible`, `opacity`, `enabled`, `z`, `clip`, `Layout.*`, or implicit-size dependency involved
6. any state/model binding that controls which hierarchy elements are instantiated or shown
7. colour/opacity combinations that could make valid items render nearly invisible against the parchment background
8. whether child components are anchored into parents that still resolve to zero width/height
9. whether slot children are created but rendered behind another layer
10. whether a parent `opacity`, `visible`, `clip`, or state transition is suppressing the content

Do not assume the prior diagnosis is correct.

---

# Mandatory Diagnostic Questions

The implementation report must explicitly answer:

1. Are the missing hierarchy components instantiated at runtime?
2. What are their actual runtime `x`, `y`, `width`, `height`, `visible`, `opacity`, and `z` values?
3. Which exact property or binding causes the content to remain collapsed, clipped, hidden, transparent, or visually indistinguishable?
4. Why did the previous `preferredHeight` repair fail to restore the approved appearance?
5. Why did all automated tests pass despite the visible defect?
6. What minimum test should be added or improved so this defect is caught in future?

---

# Repair Requirements

The repaired Phase 1 centre page must visibly restore:

- Stage badge: `1 / 7`
- Stage title
- Stage description
- workflow/progress strip
- instruction card
- primary action button

The restored page shall match the approved design hierarchy and remain within the existing five-region GUI structure.

The fix should be minimal and evidence-based.

---

# Constraints

## Must Preserve

- existing five-region layout
- top HUD
- left phase rail
- right context panel
- bottom query bar
- current colour palette
- approved parchment workspace
- existing functional behaviour
- existing core/service/domain boundaries

## Must Not

- redesign the GUI
- move business logic into QML
- change core systems, services, entities, or gameplay logic
- replace the Phase 1 page with a static mock-up
- hide the defect with hard-coded screenshots or image overlays
- perform broad refactoring unrelated to the failure
- change unrelated GUI files without clear justification

---

# Verification

Codex shall perform:

1. runtime visual verification using a fresh screenshot
2. GUI startup tests
3. full regression tests
4. direct inspection of runtime geometry/visibility values for the previously missing elements

The screenshot must clearly show the restored hierarchy.

Passing tests alone are not sufficient.

---

# Required Deliverables

Codex shall save the following files into the designated EOR working directory:

1. `GUI-P0-02-CX1_Codex_Implementation_Report.md`
2. `GUI-P0-02-CX1_After_Fix.png`
3. updated or new GUI test file(s), if required

The implementation report must include:

- confirmed root cause
- runtime evidence
- files changed
- exact changes made
- why the prior repair failed
- tests added or modified
- test results
- regression result
- screenshot path
- confirmation that unrelated systems were not changed

Do not provide the report only in chat. Save it as a file in the working directory.

---

# Completion Gate

This task is complete only when:

- all hierarchy elements are clearly visible
- the page matches the approved structural hierarchy
- the defect is reproduced and explained
- the real root cause is documented
- regression tests pass
- a screenshot confirms the repair
- the final report is saved in the designated working directory
