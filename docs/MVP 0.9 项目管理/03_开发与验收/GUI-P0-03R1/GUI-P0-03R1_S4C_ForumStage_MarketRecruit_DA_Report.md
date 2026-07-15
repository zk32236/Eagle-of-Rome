# GUI-P0-03R1 S4C ForumStage Market Recruit DA Report

Date: 2026-07-16
Role flow: PM -> SA -> DA -> CGT -> SA/PM, all inside the Codex main session
Sub-agents: not used

## 1. PM Scope Confirmation

S4C addresses two Phase 3B issues found after S4B visual acceptance against the v3.25.1 design prototype:

1. Talent-market character names were not displayed as full names.
2. Talent-market recruit buttons did not follow the prototype interaction.

The v3.25.1 design shows full names such as `Gnaeus Junius`, `Claudius Magnus`, and `Servius Antonius`, plus a recruit confirmation dialog with a bid amount input before submitting the recruitment action.

## 2. SA Boundary Check

Allowed scope:

- `src/ui/gui/qml/stages/ForumStage.qml`

Forbidden scope kept unchanged:

- `src/core/`
- `src/api/`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/shell/`

SA finding: existing GUI binding already exposes `sessionStore.doRecruitFigure(figure_id, amount)`, so no API/Store/Core expansion was required.

## 3. DA Implementation

Changed file:

- `src/ui/gui/qml/stages/ForumStage.qml`

Implementation points:

- Increased the talent-name column width and disabled name elision for the expected v3.25.1 market names.
- Slightly compressed numeric/class/cost columns to keep the row stable within the market card.
- Changed recruit button behavior from immediate API submission to opening a modal recruit dialog.
- Added recruit dialog state fields on `ForumStage` for selected figure id, figure name, base cost, and input amount.
- Added a modal dialog with base cost display, amount input, confirm button, close button, Enter-key submit, and basic positive-integer validation.
- Confirming the dialog calls the existing `sessionStore.doRecruitFigure(root.recruitDialogFigureId, amount)` method.

## 4. CGT Test Result

Executed by Codex on 2026-07-16:

```text
py -3.10 -m pytest -p no:cacheprovider src/tests/test_gui/test_qml_startup.py -q
10 passed in 5.10s
```

```text
py -3.10 -m pytest -p no:cacheprovider src/tests/test_gui -q
36 passed in 5.19s
```

Additional check:

```text
git diff --check -- src/ui/gui/qml/stages/ForumStage.qml
passed
```

## 5. Manual Visual Acceptance Pending

PM should verify locally:

- Phase 3B talent names display as full names in the market list.
- Clicking a recruit button opens a centered recruit dialog.
- The dialog title includes the selected figure name.
- The dialog amount field defaults to the figure base cost.
- Confirm submits the entered amount through the existing GUI action.
- Closing the dialog leaves the market state unchanged.

## 6. SA/PM Acceptance

Decision: CONDITIONAL_PASS

Reason: QML startup and GUI regression tests pass, and the implementation stays inside the approved ForumStage-only scope. Final acceptance still requires local visual confirmation of the dialog interaction against the v3.25.1 prototype.

## 7. Archive Recommendation

Do not archive yet until PM confirms the manual visual acceptance screenshots. If accepted, archive S4B/S4C as a bounded ForumStage Phase 3B market-panel correction, without including unrelated pre-existing changes in forbidden files.
