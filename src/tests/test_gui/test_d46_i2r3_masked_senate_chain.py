"""EOR20261013-02 · D4/D6 I2-R3 (末段) — Store §2a masked senate owning flow
end-to-end (round-trip) + terminal-aware settle.

RED-first contract for the item3-final Store side:

  * ``01-pm/DA-Brief-D4D6-I2-R3_2026-10-17.md`` §1 task 1 (Store §2a S1–S6) /
    task 4 (端到端可驱动);
  * ``02-sa-design/Rework-D3D6-D4D6-Item3-Residual-Disposition_2026-10-17.md``
    §3.1–§3.4 (masked owning flow + owning-possession gate + settle);
  * ``00-gates/PM-Ruling-D4D6-Item3-Residual-Accepted-Errata-Overlay_2026-10-17.md``
    (E1–E5).

Covered:
  * I2R3-E2E  a registered seat, with a barrier provider bound, submits the
    explicit EMPTY senate decision through ``doSubmitSenateProposals``: the Store
    runs the masked owning flow, the owning dispatch makes the item3
    owning-possession gate TRUE, the command's built-in continuation reaches the
    UNIQUE senate terminal (``finalize_senate_if_ready`` + private G-only
    selection), and the frozen terminal envelope rides back on the committed
    receipt — the end-to-end round-trip is DRIVABLE from the Store.
  * I2R3-S5   the terminal-aware settle: a resolved terminal with an AI G is a
    masked failure (never the ``None -> same-seat`` fallback); a resolved HUMAN G
    settles to that G.
  * I2R3-NEG  with NO barrier provider the legacy synchronous path is untouched
    (no masked transaction is opened).

Provenance: real service primitives (``register_hotseat_session``), the real
coordinator continuation, the real owner finalize writer. The barrier provider is
the framework's own synchronous witness (``MOCK_AUXILIARY`` stimulus only for the
frame witnesses). ``source_kind = CONSTRUCTED_STATE``; ``test_chain_quality =
UNIT-LOCAL-ONLY`` (the full Slot/pixel terminal chain is bound by the G5 verifier).
NO TOUCH: every pre-existing test assertion; this file is new.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import session_access
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.session_store import GuiSessionStore, SEAT_ACTIVE


def _senate_state(*, passed=0, current="player1", tribune_ai=True,
                  decision_complete=False):
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

    tribune = Figure(id=3, name="tribune", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(3)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.AI if tribune_ai
                            else PlayerType.HUMAN))
    state._turn_order = ["player1", "player2"]
    state.set_current_player(current)
    state.senate_proposal_decision_complete = bool(decision_complete)
    for _ in range(passed):
        pid = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        state.record_senate_vote("player1", pid, True)
        state.record_senate_vote("player2", pid, True)
    return state


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    def __init__(self):
        self.calls = []
        self.pendings = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route)); return True


def _active_store(state, viewer, senate_view):
    """A store with a bound barrier provider and an ACTIVE seat (the masked
    machine's precondition), WITHOUT the full ``initialize`` DTO load (the
    constructed fixture has no session snapshot)."""
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness()
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = viewer
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = dict(senate_view)
    return store, witness


# ===========================================================================
# I2R3-E2E — the masked senate owning flow reaches the UNIQUE terminal
# ===========================================================================
def test_i2r3_e2e_masked_senate_proposal_reaches_terminal():
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, "player1", {"viewer_has_consul": True})

    fb = store.doSubmitSenateProposals([])

    # The owning command's committed receipt carries the FROZEN terminal envelope
    # (the end-to-end round-trip reached the terminal under the masked owning flow).
    committed = store._committed_receipt
    assert committed is not None, (fb, witness.calls)
    data = committed.get("data") or {}
    assert data.get("status") == "resolved", (data, fb)
    assert data.get("phase") == "senate", data
    assert data.get("actor") == "player1", data
    assert data.get("current_player_id") == "player1", data
    assert data.get("cursor_restored") is True, data
    # the UNIQUE finalize really ran (the real owner writer committed the result)
    assert state.get_phase_result("senate") is not None
    # the private G-only selection made the real Core current == G (read-back)
    assert state.get_current_player().player_id == "player1"


def test_i2r3_e2e_masked_transaction_was_opened_with_owning_lease():
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, "player1", {"viewer_has_consul": True})

    store.doSubmitSenateProposals([])
    # the masked machine really armed the barrier (the owning transaction ran)
    assert any(c[0] == "arm" for c in witness.calls), witness.calls


# ===========================================================================
# I2R3-S5 — terminal-aware settle (AI G is NOT a None -> same-seat fallback)
# ===========================================================================
def test_i2r3_s5_ai_terminal_is_masked_failure():
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, "player1", {"viewer_has_consul": True})

    result = store._settle_after_senate_command(
        "txn-s5", {"success": True, "data": {
            "status": "resolved", "phase": "senate", "actor": "player2",
            "controller": "AI", "current_player_id": "player2",
            "awaiting_player_id": None}})
    assert result.get("success") is False, result
    # a masked failure was recorded (no same-seat recovery attempted)
    assert any(c[0] == "failure" for c in witness.calls), witness.calls


def test_i2r3_s5_human_terminal_settles_to_g():
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store, witness = _active_store(state, "player1", {"viewer_has_consul": True})

    # a DIFFERENT human G -> handoff pending (explicit takeover for the other H)
    state.set_current_player("player2")
    result = store._settle_after_senate_command(
        "txn-s5b", {"success": True, "data": {
            "status": "resolved", "phase": "senate", "actor": "player2",
            "controller": "HUMAN", "current_player_id": "player2",
            "awaiting_player_id": "player2"}})
    assert store._pending_player_id == "player2", (result, store._pending_player_id)


# ===========================================================================
# I2R3-NEG — no provider => the legacy synchronous path is untouched
# ===========================================================================
def test_i2r3_neg_no_provider_keeps_legacy_path(monkeypatch):
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    store = GuiSessionStore(state)
    store._viewer_id = "player1"
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = {"viewer_has_consul": True}
    # no barrier provider -> the masked flow must NOT be entered
    called = {"masked": 0}
    orig = store._masked_senate_owning_flow

    def _spy(*a, **k):
        called["masked"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(store, "_masked_senate_owning_flow", _spy)
    store.doSubmitSenateProposals([])
    assert called["masked"] == 0, called
