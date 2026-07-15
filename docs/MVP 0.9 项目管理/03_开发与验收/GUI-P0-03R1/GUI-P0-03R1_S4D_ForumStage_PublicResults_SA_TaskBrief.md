# GUI-P0-03R1 S4D ForumStage Public Results SA Task Brief

Date: 2026-07-16
Role: SA
Task type: GUI display bug fix / visual-state completion
Priority: P1 within GUI-P0-03R1 Phase 3B closeout

## 1. Task ID

GUI-P0-03R1_S4D_ForumStage_PublicResults

## 2. Goal

Implement the Forum Phase 3B final public-results display state in `ForumStage.qml`, using existing resolved Forum data.

## 3. Background

The v3.25.1 Phase 3B-3 prototype shows a public-results box after market bets are resolved. Current ForumStage still focuses on the market panel and does not prominently render the resolved result list in the public announcement area.

## 4. References

Documents / assets:

- `C:/Users/Kerl/Downloads/GUI design - Phase 3B-3.PNG`
- `GUI-P0-03R1_S4B_ForumStage_MarketPanel_DA????.md`
- `GUI-P0-03R1_S4C_ForumStage_MarketRecruit_DA_Report.md`

Code:

- `src/ui/gui/qml/stages/ForumStage.qml`
- `src/ui/gui/session_store.py`
- `src/api/forum_api.py`

## 5. Existing Binding Check

Existing data paths:

- `sessionStore.forumResolved`
- `sessionStore.forumResult`
- `sessionStore.forumView.resolution_results`

Existing behavior:

- `forum_api.resolve_forum()` records `data.results`.
- `forum_api.get_forum_view()` exposes `resolution_results`.
- `GuiSessionStore.doResolveForum()` stores the API feedback in `_forum_result` and refreshes the Forum view.

SA decision: no API/Store/Core change is required for S4D.

## 6. Allowed Changes

- Modify `src/ui/gui/qml/stages/ForumStage.qml` only.
- Add helper JS functions inside ForumStage if needed.
- Add/adjust QML text layout for public results.

## 7. Forbidden Changes

- Do not edit Core/API/Store/Adapter/Shell.
- Do not change Forum resolution logic.
- Do not fabricate resolved results.
- Do not alter ContextPanel advance semantics.
- Do not regress S4A/S4B/S4C layout fixes.

## 8. Implementation Requirements

1. Add a safe QML helper to retrieve resolved result lines from `forumResult.data.results` or `forumView.resolution_results`.
2. Before resolution, keep existing public announcement copy.
3. After resolution, display `[Public Results]` plus bullet-style result lines.
4. If no result lines are available, display a stable empty result message.
5. Ensure the announcement card grows enough to show multiple lines without overlap.
6. Keep market content scroll behavior unchanged.

## 9. Test Requirements

Run:

```text
py -3.10 -m pytest -p no:cacheprovider src/tests/test_gui/test_qml_startup.py -q
py -3.10 -m pytest -p no:cacheprovider src/tests/test_gui -q
```

Also run:

```text
git diff --check -- src/ui/gui/qml/stages/ForumStage.qml
```

## 10. Acceptance Criteria

- `forumResolved == false`: existing Forum public explanation remains visible.
- `forumResolved == true`: public results summary is visible in the central public area.
- Result lines are readable and do not overlap following cards.
- No forbidden file is modified by S4D.
- GUI tests pass.

## 11. Deliverables

- Updated `ForumStage.qml`.
- PM intent document.
- SA task brief.
- DA implementation report.
- Test result summary.
- SA/PM acceptance decision.
