"""S-D-1 (R2) — SD1-V01 real producer→consumer continuation route + R1-01
explicit-failure discriminant.

EOR20261013-02 GUI Readiness · slice S-D · sub-task S-D-1 · rework round R2.

The producer ``session_api.submit_population_votes`` (N7-R) and the senate AI
vote drain (N10-R) return, on a FAILED continuation, the REAL structured envelope:

    success = False
    data    = {"status": "masked_failure", "resolved": False, "retryable": True,
               "reason": <reason>, "election_results": []}
    errors  = [{"code": "AI_DRAIN_MASKED_FAILURE", "message": <reason>}]

R1-01 (this round) — the Store recognizer must REQUIRE:
  * an EXPLICIT ``feedback["success"] is False`` (reject a missing / ``None`` /
    empty / non-bool ``success`` AND a truthy ``success``); AND
  * BOTH real-envelope markers ``data.status == "masked_failure"`` AND a typed
    ``errors[].code == "AI_DRAIN_MASKED_FAILURE"`` — neither marker alone, and
    never a boolean-only ``masked_failure`` key, is sufficient (NOT relaxed).

A real-envelope failure routes to the **continuation-only** recovery
(``failureRoute == "continuation"``), never an ordinary non-mutating business
refusal (which re-stages the same seat at a new epoch) nor an activation retry.

RED witness: the malformed / single-marker / boolean-only cases below are wrongly
ACCEPTED by the pre-R2 recognizer (``if not isinstance(feedback, dict) or
feedback.get("success")``) and become GREEN once the explicit-failure discriminant
+ both-marker requirement is enforced. Evidence class: MOCK_AUXILIARY at the
adapter seam (a labelled fault/envelope injection); the observable (the Store's
failure route) is the production seam. No product authority is relaxed; the frozen
tests are untouched.
"""
from __future__ import annotations

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui import session_store as store_mod
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_FAILURE,
)

# The REAL producer envelope (session_api.submit_population_votes / senate drain).
REAL_MASKED_ENVELOPE = {
    "success": False,
    "message": "AI continuation failed",
    "data": {"status": "masked_failure", "resolved": False, "retryable": True,
             "reason": "NO_DECISION", "election_results": []},
    "errors": [{"code": "AI_DRAIN_MASKED_FAILURE", "message": "NO_DECISION"}],
    "feedback_type": "error",
    "feedback_message": "AI continuation failed",
    "error_items": [], "errors_by_scope": {},
}

# An ordinary non-mutating business refusal (must NOT be a continuation failure).
BUSINESS_REJECTION = {
    "success": False, "message": "Invalid population vote selection",
    "data": {}, "errors": [{"code": "INVALID_SELECTION_MAP", "message": "bad"}],
    "feedback_type": "error", "feedback_message": "Invalid population vote selection",
    "error_items": [], "errors_by_scope": {},
}

# A plain activation failure feedback (must NOT be a continuation failure).
ACTIVATION_FAILURE = {
    "success": False, "message": "暂未进入回合，请重试。", "data": None,
    "errors": ["暂未进入回合，请重试。"], "feedback_type": "error",
    "feedback_message": "暂未进入回合，请重试。",
}

# ---------------------------------------------------------------------------
# R1-01 malformed / partial / wrong-discriminant shapes (must ALL be rejected)
# ---------------------------------------------------------------------------
# Both masked markers present, but the explicit ``success`` discriminant is
# absent / None / empty -> the outcome cannot affirm post-commit provenance.
MALFORMED_MISSING_SUCCESS = {
    "message": "AI continuation failed",
    "data": {"status": "masked_failure", "resolved": False, "retryable": True,
             "reason": "NO_DECISION", "election_results": []},
    "errors": [{"code": "AI_DRAIN_MASKED_FAILURE", "message": "NO_DECISION"}],
}
MALFORMED_NONE_SUCCESS = dict(MALFORMED_MISSING_SUCCESS, success=None)
MALFORMED_EMPTY_SUCCESS = dict(MALFORMED_MISSING_SUCCESS, success="")

# Single-marker shapes: requires BOTH markers, so neither alone is sufficient.
STATUS_ONLY_ENVELOPE = {
    "success": False, "message": "AI continuation failed",
    "data": {"status": "masked_failure", "resolved": False},
    "errors": [],
}
CODE_ONLY_ENVELOPE = {
    "success": False, "message": "AI continuation failed", "data": {},
    "errors": [{"code": "AI_DRAIN_MASKED_FAILURE", "message": "NO_DECISION"}],
}

# Boolean-only ``masked_failure`` key — NOT the real producer evidence (R1 brief
# "非布尔 masked_failure 键"); must be rejected under the both-marker requirement.
BOOLEAN_ONLY_MASKED = {
    "success": False, "message": "masked",
    "masked_failure": True, "data": {"masked_failure": True}, "errors": [],
}

# A truthy success that (wrongly) carries the masked markers -> rejected.
SUCCESS_TRUE_WITH_MARKERS = dict(REAL_MASKED_ENVELOPE, success=True)


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _population_store():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    for pid in pids[1:]:
        o = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=o.faction_id,
                                player_type=PlayerType.HUMAN))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    return state, pids, store


class _Receiver:
    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _Barrier:
    def __init__(self):
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route)); return True

    def failure_routes(self):
        return [c[3] for c in self.calls if c[0] == "failure"]


# ===========================================================================
# 1. Recognizer binds the REAL envelope + enforces the R1-01 discriminant
# ===========================================================================
def test_real_structured_envelope_is_recognised():
    assert GuiSessionStore._is_masked_continuation_failure(REAL_MASKED_ENVELOPE) is True


def test_missing_success_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(MALFORMED_MISSING_SUCCESS) is False


def test_none_success_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(MALFORMED_NONE_SUCCESS) is False


def test_empty_success_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(MALFORMED_EMPTY_SUCCESS) is False


def test_status_only_is_not_a_continuation_failure():
    # Both markers are REQUIRED (R1-01 / PM "齐"); status alone is insufficient.
    assert GuiSessionStore._is_masked_continuation_failure(STATUS_ONLY_ENVELOPE) is False


def test_error_code_only_is_not_a_continuation_failure():
    # Both markers are REQUIRED (R1-01 / PM "齐"); the typed code alone is insufficient.
    assert GuiSessionStore._is_masked_continuation_failure(CODE_ONLY_ENVELOPE) is False


def test_boolean_only_masked_flag_is_not_a_continuation_failure():
    # The boolean ``masked_failure`` key is not the real producer evidence.
    assert GuiSessionStore._is_masked_continuation_failure(BOOLEAN_ONLY_MASKED) is False


def test_business_rejection_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(BUSINESS_REJECTION) is False


def test_activation_failure_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(ACTIVATION_FAILURE) is False


def test_success_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(SUCCESS_TRUE_WITH_MARKERS) is False


def test_non_dict_is_not_a_continuation_failure():
    assert GuiSessionStore._is_masked_continuation_failure(None) is False
    assert GuiSessionStore._is_masked_continuation_failure("masked_failure") is False
    assert GuiSessionStore._is_masked_continuation_failure(REAL_MASKED_ENVELOPE["data"]) is False


# ===========================================================================
# 2. N7-R — the real envelope selects the continuation-only UI (integration)
# ===========================================================================
def test_real_envelope_routes_population_submit_to_continuation(monkeypatch):
    state, pids, store = _population_store()
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    _Receiver(store)
    monkeypatch.setattr(store._adapter, "submit_population_votes",
                        lambda *a, **k: dict(REAL_MASKED_ENVELOPE))
    store.submitPopulationVotes({})
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert barrier.failure_routes()[-1] == "continuation", barrier.calls


def test_business_rejection_does_not_route_to_continuation(monkeypatch):
    state, pids, store = _population_store()
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    _Receiver(store)
    monkeypatch.setattr(store._adapter, "submit_population_votes",
                        lambda *a, **k: dict(BUSINESS_REJECTION))
    store.submitPopulationVotes({})
    assert "continuation" not in barrier.failure_routes(), barrier.calls


def test_malformed_masked_marker_does_not_route_to_continuation(monkeypatch):
    # Masked markers present but the explicit ``success`` discriminant is missing
    # -> NOT a continuation failure, so it must never take the continuation route.
    state, pids, store = _population_store()
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    _Receiver(store)
    monkeypatch.setattr(store._adapter, "submit_population_votes",
                        lambda *a, **k: dict(MALFORMED_MISSING_SUCCESS))
    store.submitPopulationVotes({})
    assert "continuation" not in barrier.failure_routes(), barrier.calls


# ===========================================================================
# 3. N10-R — the real envelope selects the continuation-only UI (integration)
# ===========================================================================
def test_real_envelope_routes_senate_submit_to_continuation(monkeypatch):
    state, pids, store = _population_store()
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    store._senate_view = {"viewer_has_consul": True}
    monkeypatch.setattr(store._adapter, "submit_senate_proposals",
                        lambda *a, **k: dict(REAL_MASKED_ENVELOPE))
    store.doSubmitSenateProposals([])
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert barrier.failure_routes()[-1] == "continuation", barrier.calls


def test_senate_business_rejection_does_not_route_to_continuation(monkeypatch):
    state, pids, store = _population_store()
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    store._senate_view = {"viewer_has_consul": True}
    monkeypatch.setattr(store._adapter, "submit_senate_proposals",
                        lambda *a, **k: dict(BUSINESS_REJECTION))
    store.doSubmitSenateProposals([])
    assert "continuation" not in barrier.failure_routes(), barrier.calls


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
