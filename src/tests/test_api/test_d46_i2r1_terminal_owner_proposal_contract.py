"""EOR20261013-02 · D4/D6 I2-R1 — terminal / G + owner_completion + proposal + seal.

RED-first contract for the I2-R1 continuation of the frozen integrated design:

  * ``02-sa-design/Rework-D3D6-D4D6-Design-Delta_2026-10-17.md`` (``f5aeed7d…``)
    §4.3 (terminal / G), §4.4 (owner_completion), §4.6 (AI proposal/veto narrow
    delegation), §6.1 FC-D46-05/06/08;
  * ``02-sa-design/Rework-D3D6-D4D6_Implementation_and_Test_Overlay_2026-10-17.md``
    (``9450e5ed…``) §3.2 D46-REC-TERM / D46-OWN-COMP / D46-AI-DEL / D46-REC-AUTH;
  * ``00-gates/G5-PM-Ruling-D4D6-I2-Disposition-Amendment_2026-10-17.md`` (PM
    Amendment: narrow ``session_store.py`` write face);
  * ``00-gates/G4-DA-Sizing-and-Write-Scope-D4D6-Integration_2026-10-17.md``.

Covered:
  * I2R1-T3-01  item3  a REAL authorized (owning-dispatch) senate-ready recovery runs
    the UNIQUE terminal (finalize -> private G-only selection) and returns the FROZEN
    terminal envelope with the real Core current player == G.
  * I2R1-T3-02  item3  ``_select_senate_result_owner`` ONLY selects ``scope.actor``
    (G), never a public actor; a stale scope is refused; G=AI => ``awaiting=None``.
  * I2R1-T3-03  item3  an UNauthorized senate-ready context keeps the legacy ready
    stop (no false terminal / no masked failure).
  * I2R1-T4-01  item4  the outer jump (``_verify_owner_completion``) SKIPS the generic
    ``complete_actor`` for an ACCEPTED veto whose real owner record already exists.
  * I2R1-T4-02  item4  ``COMMITTED_DECISION_UNPROVEN`` when a marker is presented with
    NO real owner record (masked failure; no fabricated completion).
  * I2R1-T4-03  item4  idempotency: re-deriving after the jump issues NO new
    receipt/decider/completion.
  * I2R1-T6-01  item6  the senate ``proposal`` substep delegates to the EXISTING
    AI-proposal algorithm via its RECURSION-FREE owner exit (no second coordinator).
  * I2R1-T6-02  item6  a non-AI / wrong-owner proposal obligation fails closed BEFORE
    the owner algorithm runs (zero side effects).
  * I2R1-SEAL-01 item4 §2b  ``_fail_masked`` seals the armed mandate
    ``FAILED_RECOVERABLE`` ONLY on a proven POST-commit failure.

Provenance: real factory / real service primitives (``create_gui_prototype_session``
or the frozen ``GameState.create_for_testing`` senate fixture; real
``authorize_and_lease`` / ``consume_command_lease``; the real coordinator
``continue_after_command``; the real owner writers). ``source_kind =
CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY`` (the full Slot terminal
chain is bound by the G5 verifier). The AI deciders are the ONLY MOCK_AUXILIARY
stimulus; no product guard/owner result is replaced. No QML / data / other product
file is touched.

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

from src.api import senate_api
from src.api import session_access
from src.api import session_api
from src.api import session_turn_service as sts
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem


# ---------------------------------------------------------------------------
# Base senate fixture (registered Hot-seat, 2 passed proposals, all ballots in).
#   * optimates: player1 (HUMAN) holds the consul (presiding officer);
#   * populares: player2 (AI)    holds the tribune (=> AI veto obligation).
# ---------------------------------------------------------------------------
def _senate_state(*, passed=2, current="player2", tribune_ai=True,
                  decision_complete=None):
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

    if decision_complete is None:
        decision_complete = passed > 0
    state.senate_proposal_decision_complete = bool(decision_complete)
    for _ in range(passed):
        pid = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        state.record_senate_vote("player1", pid, True)
        state.record_senate_vote("player2", pid, True)
    return state


def _ready_registered_senate():
    """A REGISTERED senate state that is all-required-ready (no proposals, the
    explicit empty decision is complete) with a real presiding consul owned by
    player1 (HUMAN)."""
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope = sts.mint_scope(state, "senate")     # actor = player1 (entry current)
    assert sts.phase_ready(state, "senate") is True
    return state, scope


# ===========================================================================
# I2R1-T6-01 — the proposal substep delegates through the RECURSION-FREE owner exit
# ===========================================================================
def test_i2r1_t6_01_proposal_substep_delegates_recursion_free(monkeypatch):
    state = _senate_state(passed=0, current="player2", tribune_ai=False)
    # make the consul (presiding officer) owned by an AI player so the proposal
    # obligation is a REAL AI stop.
    state.remove_player("player1")
    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.AI))
    state.set_current_player("player1")
    # latch the schedule (persists the proposal role selection for the scope)
    snap = sts.obligations(state, "senate")
    prop = next(o for o in snap.obligations if o.substep == "proposal")
    assert prop.controller == sts.CONTROLLER_AI, prop
    assert prop.is_executable and not prop.satisfied, prop

    calls = {"cont": 0}
    orig = sts.continue_after_command

    def _spy(*a, **k):
        calls["cont"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(sts, "continue_after_command", _spy)

    out = senate_api._senate_ai_executor(state, prop)
    assert out.kind == sts.OUTCOME_ACCEPTED, out
    # the owner publication happened (a real package/decision) but the executor
    # NEVER re-entered the coordinator (recursion-free single outer drive).
    assert calls["cont"] == 0, calls


def test_i2r1_t6_02_proposal_non_ai_owner_fails_closed():
    state = _senate_state(passed=0, current="player1", tribune_ai=True)
    # player1 is HUMAN and owns the consul -> the proposal obligation is HUMAN.
    snap = sts.obligations(state, "senate")
    prop = next(o for o in snap.obligations if o.substep == "proposal")
    assert prop.controller == sts.CONTROLLER_HUMAN, prop
    out = senate_api._senate_ai_executor(state, prop)
    assert out.kind == sts.OUTCOME_FAILURE, out


def test_i2r1_t6_03_propose_many_owner_exit_skips_continuation(monkeypatch):
    calls = {"cont": 0}
    orig = sts.continue_after_command

    def _spy(*a, **k):
        calls["cont"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(sts, "continue_after_command", _spy)

    # the recursion-free owner exit NEVER re-enters the coordinator
    state = _senate_state(passed=0, current="player1", tribune_ai=True)
    res = senate_api.propose_many(state, "player1", [], _run_continuation=False)
    assert res.get("success") is True, res
    assert calls["cont"] == 0, calls

    # the default owning-root path keeps the built-in continuation (ONE drive)
    state2 = _senate_state(passed=0, current="player1", tribune_ai=True)
    senate_api.propose_many(state2, "player1", [])
    assert calls["cont"] == 1, calls


# ===========================================================================
# I2R1-SEAL-01 — _fail_masked seals ONLY on a proven POST-commit failure
# ===========================================================================
def _store_with_armed_mandate():
    from src.ui.gui.session_store import GuiSessionStore
    state = _senate_state(passed=0, current="player1", tribune_ai=True)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    ctx = session_access.present_context(state)
    lease = session_access.authorize_and_lease(
        state, command="advance_population_phase", actor="player1",
        payload_digest="pd", session_id=ctx.session_id, txn_id="txn-seal")
    assert lease is not None
    assert session_access.recovery_mandate(state) is not None
    assert session_access.has_failed_recoverable_mandate(state) is False
    store = GuiSessionStore(state)
    return store, state


def test_i2r1_seal_01_post_commit_failure_seals_mandate():
    store, state = _store_with_armed_mandate()
    store._fail_masked("after_commit", "txn-seal")
    assert session_access.has_failed_recoverable_mandate(state) is True


def test_i2r1_seal_02_pre_commit_failure_does_not_seal():
    store, state = _store_with_armed_mandate()
    store._fail_masked("before_commit", "txn-seal")
    assert session_access.has_failed_recoverable_mandate(state) is False


# ===========================================================================
# I2R1-T4-01/02/03 — outer owner_completion jump
# ===========================================================================
def _veto_marker(state, scope):
    book = sts._book(state)
    veto_oid = book.oid("senate", "veto", ("singleton", scope.scope_id),
                        scope.scope_id)
    rec = next((r for r in book.records
                if r.obligation_id == veto_oid
                and r.command_id == "senate_veto_decision"
                and r.satisfied_kind == sts.KIND_ACTION), None)
    assert rec is not None
    return sts.OwnerCompletion(
        scope_id=scope.scope_id, obligation_id=veto_oid,
        command_id="senate_veto_decision", actor_player_id=None,
        kind=sts.KIND_ACTION, receipt_id=rec.authoritative_fact_ref or "",
        pre_revision=(rec.dispatch_key[-1] if rec.dispatch_key else 0),
        satisfied_at_revision=rec.satisfied_at_revision,
        fact_ref=rec.authoritative_fact_ref or "")


def _veto_ready_state():
    """Registered senate state: 2 passed proposals, all ballots in, an AI tribune
    whose veto is the ONLY outstanding obligation, and the REAL owner veto record
    already written by the owner writer."""
    state = _senate_state(passed=2, current="player2", tribune_ai=True)
    session_access.register_hotseat_session(state, "player2", epoch=0)
    sts.mint_scope(state, "senate")
    snap = sts.obligations(state, "senate")
    veto = next(o for o in snap.obligations if o.substep == "veto")
    assert veto.controller == sts.CONTROLLER_AI and not veto.satisfied, veto
    # the EXISTING owner writer records the singleton veto OID (real production write)
    wrote = senate_api._record_veto_step_completion(state)
    assert wrote.get("success") is True, wrote
    return state, veto


def test_i2r1_t4_01_outer_jump_skips_generic_completion(monkeypatch):
    state, _veto = _veto_ready_state()
    scope = sts._book(state).scopes["senate"]
    marker = _veto_marker(state, scope)

    calls = {"complete": 0}
    orig = sts.complete_actor

    def _spy(*a, **k):
        calls["complete"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(sts, "complete_actor", _spy)

    def executor(_state, _target):
        return sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED,
                                    command_id="senate_veto_decision",
                                    owner_completion=marker)

    res = sts.continue_after_command(state, phase="senate", ai_executor=executor)
    assert res.masked_failure is False, res.reason
    # the generic completion path was NOT taken for the already-owner-completed OID
    assert calls["complete"] == 0, calls


def test_i2r1_t4_02_unproven_owner_completion_is_masked_failure():
    state = _senate_state(passed=2, current="player2", tribune_ai=True)
    session_access.register_hotseat_session(state, "player2", epoch=0)
    scope = sts.mint_scope(state, "senate")
    # NO real owner record was written -> a presented marker is UNPROVEN.
    marker = sts.OwnerCompletion(
        scope_id=scope.scope_id,
        obligation_id=sts._book(state).oid("senate", "veto",
                                          ("singleton", scope.scope_id),
                                          scope.scope_id),
        command_id="senate_veto_decision", actor_player_id=None,
        kind=sts.KIND_ACTION, receipt_id="x", pre_revision=0,
        satisfied_at_revision=0, fact_ref="senate-veto:x")

    def executor(_state, _target):
        return sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED,
                                    command_id="senate_veto_decision",
                                    owner_completion=marker)

    res = sts.continue_after_command(state, phase="senate", ai_executor=executor)
    assert res.masked_failure is True
    assert res.reason == "OWNER_COMPLETION_UNPROVEN", res.reason


def test_i2r1_t4_03_outer_jump_is_idempotent(monkeypatch):
    state, _veto = _veto_ready_state()
    scope = sts._book(state).scopes["senate"]
    marker = _veto_marker(state, scope)
    book = sts._book(state)
    records_before = len(book.records)

    def executor(_state, _target):
        return sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED,
                                    command_id="senate_veto_decision",
                                    owner_completion=marker)

    sts.continue_after_command(state, phase="senate", ai_executor=executor)
    # a second drive issues NO new ledger record (the obligation is satisfied).
    sts.continue_after_command(state, phase="senate", ai_executor=executor)
    assert len(book.records) == records_before


# ===========================================================================
# I2R1-T3-01/02/03 — terminal / G
#
# NOTE (honest RED status): the terminal/envelope + the private selector are NEW
# symbols delivered by this slice. Per Overlay §3.1 a baseline-missing symbol is
# NOT a valid RED, and the end-to-end owning-dispatch flow (which is what legally
# arms the finalize guard) is supplied by the Store's masked machine — not yet
# wired to a senate phase in this slice. The tests below therefore bind the
# terminal ORDER + FROZEN envelope (with a MOCK_AUXILIARY finalize stimulus at the
# owner seam) and the ROUTING/refusal semantics (real code, no stimulus).
# ===========================================================================
_COMPLETION_FACTS = {"phase_result": True, "final_outcome_frozen": True,
                     "pending_cleared": True, "receipt": True}


def _ok_finalize(state):
    return {"success": True, "data": {"completion_facts": dict(_COMPLETION_FACTS),
                                        "finalization_id": ["s", "turn-1", 2]}}


def test_i2r1_t3_00_recover_routes_senate_ready_to_terminal(monkeypatch):
    state, scope = _ready_registered_senate()
    seen = {"called": 0}

    def _fake(state, sc, lease=None):
        seen["called"] += 1
        return sts.ContinuationResult(
            status=sts.STATUS_RESOLVED, actor=sc.actor,
            terminal={"status": "resolved", "phase": "senate",
                      "scope_id": sc.scope_id, "actor": sc.actor})
    monkeypatch.setattr(sts, "_terminal_senate_phase", _fake)
    res = sts.recover_continuation(state, ai_executor=None)
    assert seen["called"] == 1, seen
    assert res.status == sts.STATUS_RESOLVED, (res.status, res.reason)


def test_i2r1_t3_01_terminal_order_and_envelope(monkeypatch):
    state, scope = _ready_registered_senate()
    order = []
    monkeypatch.setattr(senate_api, "finalize_senate_if_ready",
                        lambda s: (order.append("finalize") or _ok_finalize(s)))
    # spy the private selector to prove the fixed order: finalize THEN select G
    orig_sel = sts._select_senate_result_owner
    monkeypatch.setattr(sts, "_select_senate_result_owner",
                        lambda s, sc: (order.append("select") or orig_sel(s, sc)))

    res = sts._terminal_senate_phase(state, scope)
    assert res.status == sts.STATUS_RESOLVED, (res.status, res.reason)
    assert order == ["finalize", "select"], order
    term = res.terminal
    assert term["status"] == "resolved" and term["phase"] == "senate"
    assert term["scope_id"] == scope.scope_id
    assert term["actor"] == "player1" and term["current_player_id"] == "player1"
    assert term["controller"] == sts.CONTROLLER_HUMAN
    assert term["cursor_restored"] is True
    assert term["awaiting_player_id"] == "player1"
    assert term["finalization_id"] == ["s", "turn-1", 2]
    assert state.get_current_player().player_id == "player1"


def test_i2r1_t3_02_select_result_owner_only_scope_actor_and_stale_refused():
    state, scope = _ready_registered_senate()
    sel = sts._select_senate_result_owner(state, scope)
    assert sel.get("success") is True, sel
    assert sel["actor"] == "player1"
    # a stale (non-current) scope is refused
    stale = sts._Scope(scope_id="deadbeef", phase="senate", entry_revision=0,
                       actor="player1")
    bad = sts._select_senate_result_owner(state, stale)
    assert bad.get("success") is False and bad["reason"] == "STALE_SCOPE"


def test_i2r1_t3_02b_g_is_ai_not_awaiting(monkeypatch):
    state, scope = _ready_registered_senate()
    # G is the phase-entry actor; make it the AI player (principal stays HUMAN).
    scope.actor = "player2"
    monkeypatch.setattr(senate_api, "finalize_senate_if_ready", _ok_finalize)
    res = sts._terminal_senate_phase(state, scope)
    assert res.terminal is not None, (res.status, res.reason)
    assert res.terminal["controller"] == sts.CONTROLLER_AI
    # G=AI => no HUMAN awaiting target (never a None->same-seat fallback target)
    assert res.terminal["awaiting_player_id"] is None
    assert state.get_current_player().player_id == "player2"


def test_i2r1_t3_03_unauthorized_ready_keeps_legacy_stop():
    state, scope = _ready_registered_senate()
    # NO owning dispatch/recovery scope established -> the finalize guard denies;
    # the terminal must NOT fabricate a result nor turn it into a masked failure.
    res = sts.recover_continuation(state, ai_executor=None)
    assert res.status == sts.STATUS_PHASE_READY, (res.status, res.reason)
    assert res.terminal is None


def test_i2r1_t3_04_terminal_business_failure_is_masked(monkeypatch):
    state, scope = _ready_registered_senate()
    monkeypatch.setattr(senate_api, "finalize_senate_if_ready",
                        lambda s: {"success": False,
                                   "errors": [{"code": "PHASE_NOT_READY"}]})
    res = sts._terminal_senate_phase(state, scope)
    assert res.status == sts.STATUS_FAILURE and res.masked_failure
    assert res.reason == "TERMINAL_FINALIZE_FAILED"
