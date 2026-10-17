"""EOR20261013-02 · D4/D6 I2-R3-R1 — the ***provider-bound*** vote/veto
convergence (the production GUI path).

Root cause of G5's S3/S4 blockers: the masked owning flow used to return before
the legacy ``resolve_senate`` convergence blocks, so with a barrier provider
bound (the real GUI path, ``app.py:286``) a zero-passed vote, a NONE-veto vote
or a HUMAN veto left the senate UNRESOLVED (deadlock: ``canAdvanceSenate`` false
forever). Every pre-existing test ran WITHOUT a provider, so the gap was
invisible.

RED-first contract for ``01-pm/DA-Brief-D4D6-I2-R3-R1_2026-10-17.md`` §1:

  * S3  ``doSubmitSenateVotes`` masked flow: zero-passed and NONE-veto are
        settlement-converged INSIDE the owning transaction;
  * S4  ``doSubmitSenateVetoes`` (HUMAN) masked flow: the unconditional
        settlement convergence is preserved;
  * the convergence never fires when the phase is not really ready (no
        premature finalization), and is called at most once per command;
  * with NO provider the legacy synchronous path keeps its byte-for-byte
        behaviour.

Provenance: real Store + real owner APIs + the framework's synchronous barrier
witness (``MOCK_AUXILIARY`` frame witnesses only). ``source_kind =
CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY``.
NO TOUCH: every pre-existing test assertion; this file is new.
"""
from __future__ import annotations

import os
import sys
import functools

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import senate_api, session_access
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.session_store import GuiSessionStore, SEAT_ACTIVE


def _senate_state(*, tribune_faction="populares", tribune_ai=True,
                  passed_votes_for_others=False, extra_proposal=False):
    """A registered-ready senate fixture with a configurable tribune slot.

    ``tribune_faction`` = ``None`` (no eligible tribune -> veto mode NONE),
    ``"optimates"`` (viewer's faction -> HUMAN veto), or ``"populares"``.
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=1, name="consul", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f1.member_ids.append(1)

    if tribune_faction is not None:
        tribune = Figure(id=3, name="tribune", faction_id=tribune_faction, age=35)
        tribune.office = "tribune"
        tribune.class_tier = ClassTier.PLEBEIAN
        state.add_member(tribune)
        state.get_faction(tribune_faction).member_ids.append(3)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.AI if tribune_ai
                            else PlayerType.HUMAN))
    state._turn_order = ["player1", "player2"]
    state.set_current_player("player1")
    state.senate_proposal_decision_complete = True

    pid = state.add_senate_proposal(
        {"type": "land", "act_type": "distribution", "amount_C": 10, "percent": 0.1})
    # pre-record the NON-viewer ballots so the viewer's command completes the
    # all-ballots barrier (deterministic; no AI drain needed).
    state.record_senate_vote("player2", pid, bool(passed_votes_for_others))
    ids = [pid]
    if extra_proposal:
        pid2 = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution", "amount_C": 12, "percent": 0.1})
        state.record_senate_vote("player2", pid2, bool(passed_votes_for_others))
        ids.append(pid2)
    return state, ids


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
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


def _active_store(state, proposal_ids, *, with_provider=True,
                  veto_mode=None):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness() if with_provider else None
    if with_provider:
        store.setHandoffBarrierProvider(witness)
    store._viewer_id = "player1"
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = {
        "viewer_has_consul": True,
        "submitted_proposals": [{"id": pid} for pid in proposal_ids],
        "current_step": "senate_vote",
        "senate_result": None,
        "veto_control_mode": veto_mode or "NONE",
    }
    return store, witness


def _count_finalize(monkeypatch):
    calls = {"n": 0, "ok": 0}
    orig = senate_api.finalize_senate_if_ready

    @functools.wraps(orig)
    def _spy(*a, **k):
        calls["n"] += 1
        result = orig(*a, **k)
        if result.get("success"):
            calls["ok"] += 1
        return result

    monkeypatch.setattr(senate_api, "finalize_senate_if_ready", _spy)
    return calls


# ===========================================================================
# S3 — zero-passed vote converges while the provider (production path) is bound
# ===========================================================================
def test_i2r3r1_provider_vote_zero_passed_converges(monkeypatch):
    state, ids = _senate_state(tribune_faction="populares", tribune_ai=True,
                               passed_votes_for_others=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, ids)
    calls = _count_finalize(monkeypatch)

    feedback = store.doSubmitSenateVotes([])      # viewer votes NO on every row

    assert feedback.get("success") is True, feedback
    assert state.get_phase_result("senate") is not None, (feedback, witness.calls)
    assert calls["n"] == 1, calls
    assert calls["ok"] == 1, calls
    # the masked activation re-read the REAL view: the senate is settled/advanceable
    assert store.senateCurrentStep == "results", store._senate_view
    assert store.canAdvanceSenate is True, store._senate_view
    # the seat stayed ACTIVE (same-seat settlement, no failed mask)
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert not any(c[0] == "failure" for c in witness.calls), witness.calls


# ===========================================================================
# S3 — NONE-veto convergence (no eligible tribune) under the provider
# ===========================================================================
def test_i2r3r1_provider_vote_none_veto_converges(monkeypatch):
    state, ids = _senate_state(tribune_faction=None, passed_votes_for_others=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, ids, veto_mode="NONE")
    calls = _count_finalize(monkeypatch)

    feedback = store.doSubmitSenateVotes(ids)     # viewer agrees -> proposals pass

    assert feedback.get("success") is True, feedback
    assert state.get_phase_result("senate") is not None, (feedback, witness.calls)
    assert calls["n"] == 1, calls
    assert calls["ok"] == 1, calls
    assert store.senateCurrentStep == "results", store._senate_view
    assert store.canAdvanceSenate is True, store._senate_view
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle


# ===========================================================================
# S4 — HUMAN veto convergence under the provider (the deadlock blocker)
# ===========================================================================
def test_i2r3r1_provider_human_veto_converges(monkeypatch):
    state, ids = _senate_state(tribune_faction="optimates", tribune_ai=True,
                               passed_votes_for_others=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, ids, veto_mode="HUMAN")
    calls = _count_finalize(monkeypatch)

    # votes pass -> the HUMAN tribune step is the outstanding obligation
    vote_feedback = store.doSubmitSenateVotes(ids)
    assert vote_feedback.get("success") is True, vote_feedback
    assert state.get_phase_result("senate") is None
    assert calls["n"] == 0, calls          # not ready: NO premature finalization
    assert store.senateCurrentStep == "tribune_veto", store._senate_view

    veto_feedback = store.doSubmitSenateVetoes([])

    assert veto_feedback.get("success") is True, veto_feedback
    assert state.get_phase_result("senate") is not None, (veto_feedback, witness.calls)
    assert calls["n"] == 1, calls
    assert calls["ok"] == 1, calls
    assert store.senateCurrentStep == "results", store._senate_view
    assert store.canAdvanceSenate is True, store._senate_view
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert not any(c[0] == "failure" for c in witness.calls), witness.calls


# ===========================================================================
# Negative control — a NOT-ready vote must NOT finalize early
# ===========================================================================
def test_i2r3r1_provider_vote_not_ready_does_not_finalize(monkeypatch):
    state, ids = _senate_state(tribune_faction=None, passed_votes_for_others=True,
                               extra_proposal=True)
    # drop the other player's ballot on ONE proposal -> the barrier is not met
    # (deterministic, no reliance on AI drain)
    state._senate_pending["votes"]["player2"].pop(ids[0], None)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, [ids[1]])   # viewer only votes on ids[1]
    calls = _count_finalize(monkeypatch)

    feedback = store.doSubmitSenateVotes([ids[1]])

    assert feedback.get("success") is True, feedback
    assert state.get_phase_result("senate") is None, feedback
    assert calls["n"] == 0, calls
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle


# ===========================================================================
# Legacy control — NO provider => untouched synchronous path (still resolves)
# ===========================================================================
def test_i2r3r1_no_provider_vote_zero_passed_keeps_legacy(monkeypatch):
    state, ids = _senate_state(tribune_faction="populares", tribune_ai=True,
                               passed_votes_for_others=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, _ = _active_store(state, ids, with_provider=False)
    entered = {"n": 0}
    orig = store._masked_senate_owning_flow

    def _spy(*a, **k):
        entered["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(store, "_masked_senate_owning_flow", _spy)

    feedback = store.doSubmitSenateVotes([])

    assert feedback.get("success") is True, feedback
    assert entered["n"] == 0, entered
    assert state.get_phase_result("senate") is not None, feedback
    assert store.senateCurrentStep == "results", store._senate_view
