# GUI-P0-03R1 S4D ForumStage Public Results PM Intent

Date: 2026-07-16
Role: PM
Reference prototype: GUI design - Phase 3B-3.PNG

## 1. Current Judgment

After S4B/S4C, Phase 3B can display the market panel and open recruit-bid dialogs. The remaining Phase 3B product gap is the final public-results state after market betting/resolution is completed.

The v3.25.1 prototype shows that after market bets are submitted and resolved, the Forum stage should display a public announcement area with the resolved market outcomes before advancing to the Population phase.

## 2. Product Goal

Show the final Forum public result summary in the central public announcement area after `forumResolved` becomes true.

Expected public result categories include:

- Recruitment result
- Contract-bid result
- Public-land purchase result
- Triumph-vote result

This is a display task, not a rules task.

## 3. Scope Decision

Allowed by default:

- `src/ui/gui/qml/stages/ForumStage.qml`

Forbidden unless a GAP is explicitly reported and approved:

- `src/core/`
- `src/api/`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/qml/shell/`

## 4. Product Constraints

- Use real resolved Forum data only.
- Do not fabricate visual calibration data.
- Do not change Forum resolution rules.
- Do not use the public-results card as the phase-advance control.
- Keep ContextPanel advancement behavior unchanged.
- Preserve S4A/S4B/S4C fixes.

## 5. Acceptance Criteria

- Before Forum resolution, the public announcement area keeps the existing stage-start explanation.
- After Forum resolution, the public announcement area shows a `[Public Results]` style summary.
- Multiple result lines display without overlap.
- Empty/no-action results show a stable empty state.
- Market card remains scrollable and functional.
- GUI startup and full GUI tests pass.

## 6. Next Decision Point

If existing DTO result strings are semantically too detailed or not public-safe, create a separate API/DTO copy-normalization task. Do not expand S4D silently.
