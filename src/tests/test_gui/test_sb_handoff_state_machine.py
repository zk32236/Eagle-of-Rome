"""EOR20261013-02 S-B Group 2/4 — handoff authority state machine (Store side).

Drives the production ``GuiSessionStore`` masked handoff machine through its real
public entries (``doCompletePlayer`` / ``submitPopulationVotes`` / ``requestTakeover``
/ ``confirmHandoffAsync`` / ``retryHandoff``). A fake barrier/witness provider
mirrors the production GameShell-backed provider so the protocol is testable
headless; the REAL QML provider wiring is exercised in
``test_sb_handoff_overlay.py``.

Invariants proven:
  * ACTIVE -> MASKED_PENDING_HANDOFF -> ACTIVATE -> (ACTIVE | MASKED_FAILURE);
  * NO pre-confirm publication of the next seat; the pending surface exposes the
    safe FACTION NAME ONLY (never a raw ``player_*`` id / player name / initials);
  * cover/input-swallow provider barrier armed before any dispatch;
  * missing arm / missing unmask witness / missing Query receiver ack -> fail
    closed (cover stays, ``handoffFinished`` False);
  * only an explicit 「接管」 (correct single-use token) activates; wrong/stale/
    duplicate token is refused with no change;
  * the CLOSED Query real receiver-ack contract (EOR20261011-01) is preserved.
"""
import copy
import json
import os
import random
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_PENDING, SEAT_MASKED_FAILURE,
)


@pytest.fixture(autouse=True)
def _restore_rng():
    """Keep these session-creating tests transparent to suite ordering."""
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _session():
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
    return state, pids


def _faction_name(state, pid):
    return state.get_faction(state.get_player(pid).faction_id).name


class _Receiver:
    """Headless stand-in for the production QML query-invalidation receiver."""

    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        self.calls = []
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.calls.append(bool(keep_open))
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _Barrier:
    """Fake barrier/witness provider (GameShell-backed in production)."""

    def __init__(self, arm=True, unmask=True, pending=True):
        self.arm = arm
        self.unmask = unmask
        self.pending = pending
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return self.arm

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction))
        return self.pending

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return self.unmask

    def show_failure(self, txn, kind, route=""):
        # SD-R02 (§1.1.R): the barrier-witness copy call now carries the safe,
        # exclusive failure-origin token; the stub accepts it (copy-only).
        self.calls.append(("failure", txn, kind, route))
        return True


def _setup(with_query=False):
    state, pids = _session()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    recv = _Receiver(store)
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    if with_query:
        store.doGlobalQuery("figure_search", "", "")
    return state, pids, store, recv, barrier


# ===========================================================================
# No pre-confirm publication + faction-name-only pending
# ===========================================================================
def test_masked_handoff_defers_publication_and_shows_faction_only():
    state, pids, store, recv, barrier = _setup()
    pendings = []
    finals = []
    store.handoffMaskPending.connect(lambda f: pendings.append(f))
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))

    fb = store.doCompletePlayer()
    assert fb["success"], fb

    assert store.seatLifecycle == SEAT_MASKED_PENDING
    # No pre-confirm publication of the next seat.
    assert store.viewerPlayerId == ""
    assert store.viewerPlayerId != pids[1]
    assert store.globalQueryResult == {}
    assert store.handoffMaskVisible is True
    assert store.handoffAcceptingTakeover is True

    # Safe faction name ONLY (never a raw player id / player name / initials).
    fname = _faction_name(state, pids[1])
    assert store.handoffPendingFactionName == fname
    assert pids[1] not in store.handoffPendingFactionName
    assert "player_" not in store.handoffPendingFactionName
    assert pendings == [fname]
    # The private token/epoch/player id are NEVER part of the notification copy.
    assert store._pending_token and store._pending_token not in pendings
    assert pids[1] not in pendings

    # Provider armed the opaque cover BEFORE any dispatch, then showed pending.
    assert barrier.calls[0][0] == "arm"
    assert barrier.calls[-1][0] == "pending"
    assert barrier.calls[-1][2] == fname

    # Not finished yet.
    assert finals == []
    # The Query receiver saw a clear-before-publish (real obligation kept).
    assert recv.calls


def test_masked_handoff_no_stale_viewer_residue():
    state, pids, store, recv, barrier = _setup(with_query=True)
    # A's own query DTO is open before the handoff.
    assert store.globalQueryResult.get("id") == "figure_search"
    store.doCompletePlayer()
    # Neutralized: no stale A projection is visible during pending.
    assert store.globalQueryResult == {}
    assert store.senateView == {}
    assert store.mortalityResult == {}
    assert store.populationView == {}


def test_takeover_activates_and_finishes_true():
    state, pids, store, recv, barrier = _setup()
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    store.doCompletePlayer()

    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]
    assert store.handoffPendingFactionName == ""
    assert store.handoffMaskVisible is False
    assert len(finals) == 1 and finals[0][1] is True


def test_wrong_or_stale_token_denied_no_change():
    state, pids, store, recv, barrier = _setup()
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING

    res = store.confirmHandoffAsync("bogus-token")
    assert res["accepted"] is False
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""
    assert store.viewerPlayerId != pids[1]


def test_duplicate_takeover_single_use():
    state, pids, store, recv, barrier = _setup()
    store.doCompletePlayer()
    first = store.requestTakeover()
    assert first["accepted"] is True
    # Second attempt: lifecycle is ACTIVE → not pending → refused, no republish.
    second = store.requestTakeover()
    assert second["accepted"] is False
    assert store.seatLifecycle == SEAT_ACTIVE


# ===========================================================================
# Fail-closed witnesses
# ===========================================================================
def test_missing_barrier_arm_fails_closed():
    state, pids, store, recv, barrier = _setup()
    barrier.arm = False
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    fb = store.doCompletePlayer()
    assert fb["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffMaskVisible is True
    assert store.viewerPlayerId != pids[1]
    assert any(s is False for _, s in finals)


def test_missing_unmask_witness_fails_closed_cover_stays():
    state, pids, store, recv, barrier = _setup()
    barrier.unmask = False
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    store.doCompletePlayer()
    store.requestTakeover()
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffMaskVisible is True          # cover stays
    assert any(s is False for _, s in finals)


def test_no_receiver_ack_during_handoff_fails_closed_before_commit():
    state, pids = _session()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    store.doGlobalQuery("figure_search", "", "")   # had_content -> needs a real ack
    _zombie = _Receiver(store, ack=False)
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId != pids[1]


def test_business_rejection_releases_barrier_same_seat():
    state, pids, store, recv, barrier = _setup()
    with patch.object(store._adapter, "next_player",
                      return_value={"success": False, "message": "no"}):
        fb = store.doCompletePlayer()
    assert fb["success"] is False
    # No mutation → refresh A and release the barrier safely (same seat).
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]
    assert any(c[0] == "unmask" for c in barrier.calls)


def test_retry_same_seat_recovery():
    state, pids, store, recv, barrier = _setup()
    store.doCompletePlayer()               # pending B; the txn records target B
    # W3 / W-04 / A-W3-03 (SUPERSEDED assertion, TA-02): retry re-validates the
    # RECORDED target. The Core cursor is NEVER a target source (reading it is
    # already a violation), so it is left untouched.
    store._fail_masked("after_commit")
    assert store.seatLifecycle == SEAT_MASKED_FAILURE

    res = store.retryHandoff()
    assert res["accepted"] is True
    # TA-02a (W3-R2): the recorded target (B) is NOT the viewer (A), so the bounded
    # retry re-arms a REAL pending handoff — it is an activation ONLY for the
    # recorded same seat. The same-seat positive control now lives in
    # test_w3_delivery_authority.py::test_ac_w3_08_retry_uses_the_recorded_envelope_target
    # (in-scope envelope) and in test_w2b_projection.py::
    # test_activation_failure_can_be_retried_without_replaying_a_command (legacy
    # checkpoint branch). This nodeid keeps its historical NAME only.
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store._pending_player_id == pids[1]
    assert store._pending_token                      # a FRESH single-use reservation
    assert store.viewerPlayerId == ""                # no pre-confirm publication
    assert barrier.calls[-1][0] == "pending"
    assert barrier.calls[-1][2] == _faction_name(state, pids[1])


# ===========================================================================
# Preserved legacy Query contract (no provider -> unchanged EOR20261011-01 path)
# ===========================================================================
def test_legacy_handoff_unchanged_without_provider():
    state, pids, store, recv = _setup()[0:4]
    store.clearHandoffBarrierProvider()
    store.doGlobalQuery("figure_search", "", "")
    handoffs = []
    store.handoffRequired.connect(lambda i: handoffs.append(i))
    store.doCompletePlayer()
    # Legacy: synchronous Query-ack-gated publication of the next viewer.
    assert store.viewerPlayerId == pids[1]
    assert store.globalQueryResult.get("id") == "figure_search"
    assert handoffs
