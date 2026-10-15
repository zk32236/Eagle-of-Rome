"""EOR20261013-02 S-C — negative-case matrix (GR-AC10, Overlay §2).

Rows: N1 (non-current write), N2 (duplicate submit), N3 (empty candidate),
N6 (forced AI/HUMAN autoplay), N8 (stale epoch),
N7-R (missing_decider) / N10-R (unresolved mandatory AI vote) — the executable
seam rows of Overlay §2.1.RR-03A.

Classification: N7-R/N10-R stimulus = ``MOCK_AUXILIARY`` fault at the named
precommit decider seam; the trigger + observable = the production coordinator
``session_turn_service.continue_after_command`` and the RAW Core digest. The raw
comparison point is the POST-COMMIT failure boundary (no new effect, no rollback).
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import mortality_api
from src.api import session_api
from src.api import session_access
from src.api import session_turn_service as sts
from src.core.entities.player import Player, PlayerType


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _mk_state(*, humans, ais, observers=()):
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    want = list(humans) + list(ais) + list(observers)
    while len(want) < len(pids):
        want.append(PlayerType.AI)
    assert len(pids) == len(want), (pids, want)
    for pid, kind in zip(pids, want):
        original = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=original.faction_id,
                                player_type=kind))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    return state, pids


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _accepted(state, target):
    return sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED, command_id="cmd")


# ===========================================================================
# N1 — non-current write denied before dispatch; digest equal
# ===========================================================================
def test_N1_non_current_write_denied_before_dispatch():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    before = _digest(state)
    # a non-current HUMAN seat dispatches a mutation family
    denied = session_api.complete_population_player(state, pids[1])
    assert denied["success"] is False
    assert denied["errors"][0]["code"] == "DENIED"
    assert _digest(state) == before, "denied write mutated source state"


# ===========================================================================
# N2 — duplicate / replayed completion denied by the once-only DK
# ===========================================================================
def test_N2_duplicate_submit_replay_denied():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, _ai1, _ai2 = pids
    scope = sts.mint_scope(state, "population")
    r1 = sts.complete_actor(state, None, scope.scope_id, "cmd-1", actor_player_id=h0,
                            phase="population", substep="vote", core_revision_before=7)
    assert r1["success"] and r1.get("recorded")
    r2 = sts.complete_actor(state, None, scope.scope_id, "cmd-1", actor_player_id=h0,
                            phase="population", substep="vote", core_revision_before=7)
    assert r2["success"] is False and r2["reason"] == "DUPLICATE_DISPATCH"


# ===========================================================================
# N3 — empty lawful state: EMPTY allowed, but never a fictitious success
# ===========================================================================
def test_N3_empty_is_not_fictitious_success():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, _ai1, _ai2 = pids
    scope = sts.mint_scope(state, "population")
    # an owner-declared structural empty removes ONLY that obligation
    r = sts.complete_actor(state, None, scope.scope_id, "empty",
                           actor_player_id=h0, phase="population", substep="vote",
                           satisfied_kind=sts.KIND_STRUCTURAL_NONE)
    assert r["success"]
    book = sts._book(state)
    oid = book.oid("population", "vote", ("player", h0), scope.scope_id)
    assert book.satisfies_kind(oid) == sts.KIND_STRUCTURAL_NONE
    # no fabricated controller/action fact was created
    assert sts.controller_of(state, None) == sts.CONTROLLER_NONE


# ===========================================================================
# N6 — forced AI/HUMAN autoplay denied (observer + other HUMAN never auto-played)
# ===========================================================================
def test_N6_observer_and_other_human_are_not_ai():
    state, pids = _mk_state(humans=[PlayerType.HUMAN],
                            ais=[PlayerType.AI], observers=[PlayerType.OBSERVER])
    h0, ai, obs = pids
    assert sts.is_ai_actor(state, ai) is True
    assert sts.is_ai_actor(state, h0) is False   # HUMAN not treated as AI
    assert sts.is_ai_actor(state, obs) is False  # OBSERVER excluded


def test_N6_forced_ai_handle_does_not_autoplay_human():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    _, h1, ai = pids
    processed = []
    sts.continue_after_command(
        state, ai_executor=lambda s, t: (processed.append(t.actor_player_id)
                                         or _accepted(s, t)))
    assert processed == [ai]
    assert h1 not in processed


# ===========================================================================
# N8 — stale epoch / revision: prior token reuse denied, no mutation
# ===========================================================================
def test_N8_stale_revision_and_scope_denied():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    scope = sts.mint_scope(state, "population")
    before = _digest(state)
    stale = sts.select_actor(state, scope_id=scope.scope_id,
                             expected_revision=sts.current_revision(state) + 1)
    assert stale["success"] is False and stale["reason"] == "STALE_REVISION"
    wrong_scope = sts.select_actor(state, scope_id="deadbeef")
    assert wrong_scope["success"] is False and wrong_scope["reason"] == "STALE_SCOPE"
    assert _digest(state) == before


# ===========================================================================
# N7-R — missing_decider: masked safe failure, obligation outstanding
# ===========================================================================
def test_N7_R_missing_decider_masked_failure():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    _h0, _h1, ai = pids
    scope = sts.mint_scope(state, "population")
    boundary = _digest(state)  # post-commit failure boundary (no prior commit here)

    def bad_decider(s, target):
        raise RuntimeError("decider retrieval unavailable")  # ERROR at precommit seam

    res = sts.continue_after_command(state, ai_executor=bad_decider)
    assert res.status == sts.STATUS_FAILURE
    assert res.masked_failure is True
    # obligation stays outstanding (no ledger satisfied, no structural NONE)
    book = sts._book(state)
    outstanding_ids = {o.obligation_id for o in res.outstanding}
    assert any(oid[5] == ("player", ai) for oid in outstanding_ids)
    oid = book.oid("population", res.outstanding[0].substep, ("player", ai),
                   scope.scope_id)
    assert not book.satisfied(oid, scope.scope_id, sts.current_revision(state))
    # POST-COMMIT FAILURE BOUNDARY: no new effect, no rollback
    assert _digest(state) == boundary


# ===========================================================================
# N10-R — unresolved mandatory AI vote: deliberate no-choice -> masked failure
# ===========================================================================
def test_N10_R_unresolved_mandatory_ai_vote_masked_failure():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    _h0, _h1, _ai = pids
    boundary = _digest(state)

    def no_choice(s, target):
        return sts.ExecutionOutcome(sts.OUTCOME_NO_CHOICE, detail="NO_DECISION")

    res = sts.continue_after_command(state, ai_executor=no_choice)
    assert res.status == sts.STATUS_FAILURE
    assert res.masked_failure is True
    assert res.reason == "UNRESOLVED_MANDATORY_AI_VOTE"
    assert _digest(state) == boundary


# ===========================================================================
# Recovery — grContinuationRecover resumes ONLY outstanding; no HUMAN replay
# ===========================================================================
def test_recover_resumes_only_outstanding_and_does_not_replay_human():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    h0, _h1, ai = pids
    scope = sts.mint_scope(state, "population")
    # a committed HUMAN command with a fixed pre-command revision
    sts.complete_actor(state, None, scope.scope_id, "human-cmd", actor_player_id=h0,
                       phase="population", substep="campaign", core_revision_before=1)
    book = sts._book(state)
    human_oid = book.oid("population", "campaign", ("player", h0), scope.scope_id)
    human_records_before = sum(1 for r in book.records if r.obligation_id == human_oid)

    # a failing drain first (masked), then recovery with the decider available
    sts.continue_after_command(
        state, ai_executor=lambda s, t: (_ for _ in ()).throw(RuntimeError("boom")))
    res = sts.recover_continuation(state, ai_executor=lambda s, t: _accepted(s, t))
    assert res.status in (sts.STATUS_NEXT_HUMAN, sts.STATUS_PHASE_READY), (
        f"status={res.status} processed={res.processed} "
        f"nrecords={len(book.records)} reason={res.reason}")
    # the committed HUMAN command was NOT resubmitted (record count unchanged)
    human_records_after = sum(1 for r in book.records if r.obligation_id == human_oid)
    assert human_records_after == human_records_before == 1
    # the outstanding AI obligation is now satisfied (resumed, not lost)
    ai_oid = book.oid("population", "campaign", ("player", ai), scope.scope_id)
    assert book.satisfied(ai_oid, scope.scope_id, sts.current_revision(state)), (
        f"processed={res.processed} nrecords={len(book.records)}")


# ===========================================================================
# N4 - forced_advance: pending obligations / no settlement -> DENIED, no auto-skip
# ===========================================================================
def test_N4_forced_advance_denied_no_autoskip():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    before = _digest(state)
    resp = session_api.advance_population_phase(state, pids[0], caller_context=ctx)
    assert resp["success"] is False
    # no auto-skip: the phase is neither resolved nor executed; business digest equal
    assert state.is_phase_executed("population") is False
    assert state.get_phase_result("population") is None
    assert _digest(state) == before


# ===========================================================================
# N5 - wrong_phase: invoke another phase's mutation -> DENIED, digest equal
# ===========================================================================
def test_N5_wrong_phase_mutation_denied():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    before = _digest(state)
    # current phase is population; a mortality mutation must be refused pre-dispatch
    resp = mortality_api.advance_mortality_phase(state, pids[0], caller_context=ctx)
    assert resp["success"] is False
    assert _digest(state) == before
    # a stale phase-scope selection is also refused (navigation is not authority)
    stale = sts.select_actor(state, scope_id="stale-phase-scope")
    assert stale["success"] is False and stale["reason"] == "STALE_SCOPE"
    assert _digest(state) == before


# ===========================================================================
# N9 - illegal_payload_or_resource: malformed batch denied before partial writes
# ===========================================================================
def test_N9_illegal_payload_denied_before_writes():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    before = _digest(state)
    # negative id + unknown office -> INVALID_SELECTION_MAP, no partial write
    resp = session_api.submit_population_votes(
        state, pids[0], {"consul": -1}, caller_context=ctx)
    assert resp["success"] is False
    assert resp["errors"][0]["code"] == "INVALID_SELECTION_MAP"
    assert _digest(state) == before
    # a non-dict payload is likewise refused without mutation
    resp2 = session_api.submit_population_votes(state, pids[0], ["x"], caller_context=ctx)
    assert resp2["success"] is False
    assert _digest(state) == before


# ===========================================================================
# N11 - role_vs_faction_round: a singleton step never drops a faction round
# ===========================================================================
def test_N11_role_round_does_not_drop_faction_round():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    h0, _h1, ai = pids
    scope = sts.mint_scope(state, "population")
    book = sts._book(state)
    oid_singleton = book.oid("population", "vote", ("singleton", scope.scope_id),
                             scope.scope_id)
    # take the singleton (role) step for the population scope
    r = sts.complete_actor(state, None, scope.scope_id, "role-step",
                           obligation_id=oid_singleton, phase="population", substep="vote",
                           satisfied_kind=sts.KIND_EXPLICIT_FINISH)
    assert r["success"]
    # the per-controller faction-round obligations are NOT dropped
    snap = sts.obligations(state, "population", "vote")
    outstanding_players = [o for o in snap.obligations
                           if o.actor_slot[0] == "player" and not o.satisfied]
    assert outstanding_players, "role round must not satisfy faction-round seats"
    assert sts.phase_ready(state, "population") is False
    # readiness stays false until every controller is done
    for pid in (h0, ai):
        sts.complete_actor(state, None, scope.scope_id, f"vote-{pid}",
                           actor_player_id=pid, phase="population", substep="vote",
                           satisfied_kind=sts.KIND_EXPLICIT_FINISH)
    # h1 still outstanding -> not ready
    assert sts.phase_ready(state, "population") is False
