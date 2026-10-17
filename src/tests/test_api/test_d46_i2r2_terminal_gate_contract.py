"""EOR20261013-02 · D4/D6 I2-R2 — item3 terminal gate + propose_many passthrough
+ owner-checkpoint resume-kind resolver.

RED-first contract for the item3-residual Errata/Overlay (E1–E5) + Disposition §3/§5:

  * ``00-gates/PM-Ruling-D4D6-Item3-Residual-Accepted-Errata-Overlay_2026-10-17.md`` (E1–E5);
  * ``02-sa-design/Rework-D3D6-D4D6-Item3-Residual-Disposition_2026-10-17.md``
    (``648c47fb…``) §3 (S7/S8) / §4 (owning-possession gate) / §5 (resume-kind).

Covered:
  * I2R2-G1  an AUTHORIZED owning-possession context (live owning continuation
    scope) whose senate phase is ready routes the FORWARD continuation's ready
    branch to the UNIQUE terminal (``_terminal_senate_phase``) — NOT the legacy stop.
  * I2R2-G2  a REGISTERED but possession-less context keeps the legacy
    ``STATUS_PHASE_READY`` (byte-for-byte) with no terminal.
  * I2R2-G3  an UNregistered (CLI/legacy) context keeps the legacy ready stop.
  * I2R2-G4  the NEGATIVE control (E4①/E5): NO owning possession => the terminal
    finalize boundary is NEVER touched (finalize call count == 0, zero side effect).
  * I2R2-G5  ``senate_api.propose_many`` success branch passes ``cont.terminal``
    through ADDITIVELY.
  * I2R2-RK1..RK3  ``resolve_recovery_resume_kind`` picks a SINGLE kind by the real
    owner checkpoint and refuses a kind outside the mandate's permitted set, with no
    side effects.

Provenance: real factory / real service primitives (``register_hotseat_session`` /
``authorize_and_lease`` / ``consume_command_lease`` / ``begin_dispatch_nesting``;
the real coordinator). Only the terminal / finalize seam is a MOCK_AUXILIARY
stimulus. ``source_kind = CONSTRUCTED_STATE``; ``test_chain_quality =
UNIT-LOCAL-ONLY`` (the end-to-end Slot terminal chain is bound by the G5 verifier).
NO TOUCH: every pre-existing test assertion; this file is new.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import senate_api
from src.api import session_access
from src.api import session_turn_service as sts
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem


def _senate_state(*, passed=0, current="player1", tribune_ai=True,
                  decision_complete=True):
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


_ADV_HELPERS = frozenset({"auto_submit_proposals", "apply_auto_tribune_vetoes",
                          "finalize_senate_if_ready", "assign_governors"})


def _drop_nesting_residue(state):
    """Test hygiene: the per-thread nesting store is keyed by
    ``session-{id(state)}`` (``session_access._state_identity``).

    ``end_dispatch_nesting`` pops the capability but leaves the (now empty) entry
    behind, so a later state that happens to reuse the same ``id(state)`` could
    observe a stale possession. Dropping the entry eliminates that coupling."""
    store = getattr(session_access._NESTING_LOCAL, "by_state", None)
    if isinstance(store, dict):
        store.pop(f"session-{id(state)}", None)


@contextmanager
def _owning_ready_senate():
    """Registered senate-ready state with a LIVE owning continuation scope (the
    real masked dispatch possession: authorize -> consume -> nesting).

    G5 I2-R3 R1: the scope is ALWAYS closed (the previous helper leaked the
    dispatch nesting, which made ``has_owning_possession`` order-dependent)."""
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope = sts.mint_scope(state, "senate")
    assert sts.phase_ready(state, "senate") is True
    ctx = session_access.present_context(state)
    lease = session_access.authorize_and_lease(
        state, command="advance_population_phase", actor="player1",
        payload_digest="pd", session_id=ctx.session_id, txn_id="txn-r2")
    assert lease is not None
    reason = session_access.consume_command_lease(
        state, lease_id=lease.lease_id, helpers=_ADV_HELPERS)
    assert reason is None, reason
    session_access.begin_dispatch_nesting(
        state, txn_id="txn-r2", command="advance_population_phase",
        dispatch_epoch=lease.dispatch_epoch, helpers=_ADV_HELPERS)
    try:
        yield state, scope, lease
    finally:
        session_access.end_dispatch_nesting(state)
        _drop_nesting_residue(state)


# ===========================================================================
# I2R2-G1 — owning possession routes the ready branch to the UNIQUE terminal
# ===========================================================================
def test_i2r2_g1_owning_possession_routes_ready_branch_to_terminal(monkeypatch):
    seen = {"n": 0}

    def _fake(state, sc, lease=None):
        seen["n"] += 1
        return sts.ContinuationResult(status=sts.STATUS_RESOLVED, actor=sc.actor,
                                      terminal={"status": "resolved",
                                                "phase": "senate",
                                                "scope_id": sc.scope_id})
    monkeypatch.setattr(sts, "_terminal_senate_phase", _fake)
    with _owning_ready_senate() as (state, scope, lease):
        res = sts._continue_scheduled_phase(state, "senate", scope, lease, None)
    assert seen["n"] == 1, (seen["n"], res.status, res.reason)
    assert res.status == sts.STATUS_RESOLVED, (res.status, res.reason)
    assert res.terminal is not None


# ===========================================================================
# I2R2-G2 — registered but NO owning possession keeps the legacy ready stop
# ===========================================================================
def test_i2r2_g2_no_owning_possession_keeps_legacy_ready():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope = sts.mint_scope(state, "senate")
    assert sts.phase_ready(state, "senate") is True
    res = sts._continue_scheduled_phase(state, "senate", scope, None, None)
    assert res.status == sts.STATUS_PHASE_READY, (res.status, res.reason)
    assert res.terminal is None


# ===========================================================================
# I2R2-G3 — unregistered (CLI/legacy) keeps the legacy ready stop
# ===========================================================================
def test_i2r2_g3_unregistered_keeps_legacy_ready():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    scope = sts.mint_scope(state, "senate")
    res = sts._continue_scheduled_phase(state, "senate", scope, None, None)
    assert res.status == sts.STATUS_PHASE_READY, (res.status, res.reason)
    assert res.terminal is None


# ===========================================================================
# I2R2-G4 — NEGATIVE control: no owning possession => finalize NEVER touched
# ===========================================================================
def test_i2r2_g4_no_finalize_without_owning_possession(monkeypatch):
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope = sts.mint_scope(state, "senate")
    calls = {"n": 0}

    def _spy(_state):
        calls["n"] += 1
        return {"success": True, "data": {}}

    monkeypatch.setattr(senate_api, "finalize_senate_if_ready", _spy)
    res = sts._continue_scheduled_phase(state, "senate", scope, None, None)
    assert res.status == sts.STATUS_PHASE_READY, (res.status, res.reason)
    assert calls["n"] == 0, calls


# ===========================================================================
# I2R2-G5 — propose_many passes cont.terminal through ADDITIVELY
# ===========================================================================
def test_i2r2_g5_propose_many_passes_through_terminal(monkeypatch):
    # decision must still be OPEN so the package submit is accepted (a completed
    # selection rejects re-submission).
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=False)
    term = {"status": "resolved", "phase": "senate", "actor": "player1",
            "cursor_restored": True, "finalization_id": ["s", "turn-1", 2]}

    def _fake_cont(*a, **k):
        return sts.ContinuationResult(status=sts.STATUS_RESOLVED, actor="player1",
                                      terminal=dict(term))
    monkeypatch.setattr(sts, "continue_after_command", _fake_cont)
    res = senate_api.propose_many(state, "player1", [])
    assert res.get("success") is True, res
    data = res["data"]
    assert data.get("cursor_restored") is True, data
    assert data.get("finalization_id") == ["s", "turn-1", 2], data
    assert data.get("status") == "resolved", data


# ===========================================================================
# I2R2-RK — resume-kind resolver picks ONE kind by the real checkpoint
# ===========================================================================
def _mandate(permitted, command="propose_many"):
    return session_access.RecoveryMandate(
        mandate_id="rm-test", session_id="s", original_authorization_id="ls",
        original_actor="player1", original_command=command,
        original_payload_digest="pd", original_auth_epoch=0,
        original_dispatch_txn="txn", permitted_resume_kind=frozenset(permitted),
        permitted_phase_transition="senate-stop", policy_id="RA-A03",
        status=session_access.MANDATE_FAILED_RECOVERABLE)


def test_i2r2_rk1_senate_ready_chooses_terminal_pending():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    m = _mandate({"CONTINUATION_PENDING", "TERMINAL_PENDING", "DELIVERY_PENDING"})
    kind = sts.resolve_recovery_resume_kind(state, m)
    assert kind == "TERMINAL_PENDING", kind


def test_i2r2_rk2_non_permitted_kind_is_refused():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    # checkpoint derives TERMINAL_PENDING, which is NOT permitted for this mandate
    m = _mandate({"ENTRY_PENDING", "CONTINUATION_PENDING", "DELIVERY_PENDING"},
                 command="advance_forum_phase")
    assert sts.resolve_recovery_resume_kind(state, m) is None


def test_i2r2_rk3_resolver_is_read_only():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    book = sts._book(state)
    recs = len(book.records)
    m = _mandate({"TERMINAL_PENDING"})
    sts.resolve_recovery_resume_kind(state, m)
    assert len(sts._book(state).records) == recs
