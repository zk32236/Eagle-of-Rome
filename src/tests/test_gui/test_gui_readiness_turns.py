"""EOR20261013-02 S-C — canonical turn order + AI drain (GR-T03 / GR-T11).

Production entry: ``session_api.create_gui_prototype_session`` + the S-C single
completion coordinator ``session_turn_service``. Controller classification is the
ACTUAL ``PlayerType`` (never ``player_id != viewer``, never viewer-relative
``mode``), and the single ledger keys on a stable ``OID`` + once-only ``DK``.
"""
import copy
import os
import random
import sys, pathlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
from src.api import session_turn_service as sts
from src.core.entities.player import Player, PlayerType


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _mk_state(*, humans, ais):
    """Create a population-phase session then force the exact controller set."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    want = list(humans) + list(ais)
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


def _accepted(state, target):
    return sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED, command_id="cmd")


# ===========================================================================
# GR-T03/a — AI criterion is PlayerType ONLY
# ===========================================================================
def test_controller_of_is_actual_playertype_not_viewer():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    h0, h1, ai = pids
    assert sts.controller_of(state, h0) == sts.CONTROLLER_HUMAN
    assert sts.controller_of(state, h1) == sts.CONTROLLER_HUMAN
    assert sts.controller_of(state, ai) == sts.CONTROLLER_AI
    # OBSERVER is never an executable controller (non-human filter is forbidden).
    state.remove_player(h1)
    state.add_player(Player(player_id=h1,
                            faction_id=state.get_faction("populares").id,
                            player_type=PlayerType.OBSERVER))
    assert sts.controller_of(state, h1) == sts.CONTROLLER_NONE


def test_drain_processes_only_ai_not_other_humans():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    h0, h1, ai = pids
    processed = []

    def executor(s, target):
        processed.append(target.actor_player_id)
        return _accepted(s, target)

    res = sts.continue_after_command(state, ai_executor=executor)
    assert res.status == sts.STATUS_NEXT_HUMAN
    # Only the actual AI seat was drained; the other HUMAN was never auto-played.
    assert processed == [ai]
    assert h1 not in processed


def test_no_autoplay_of_non_current_human():
    state, pids = _mk_state(humans=[PlayerType.HUMAN, PlayerType.HUMAN],
                            ais=[PlayerType.AI])
    _, h1, _ = pids
    # h0 is current; h1 must NOT have any completion recorded.
    sts.continue_after_command(state, ai_executor=lambda s, t: _accepted(s, t))
    book = sts._book(state)
    assert all(rec.obligation_id[5] != ("player", h1) for rec in book.records)


# ===========================================================================
# Ledger identity / replay — the four mandated traces (delta §2.2)
# ===========================================================================
def test_trace_A_completes_B_commits_A_still_complete():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, ai, _ = pids
    scope = sts.mint_scope(state, "population")
    sts.complete_actor(state, None, scope.scope_id, "cmd-A",
                       actor_player_id=h0, phase="population", substep="vote")
    oid_a = sts._book(state).oid("population", "vote", ("player", h0),
                                 scope.scope_id)
    # B commits later at a higher revision.
    sts.complete_actor(state, None, scope.scope_id, "cmd-B",
                       actor_player_id=ai, phase="population", substep="vote")
    assert sts._book(state).satisfied(oid_a, scope.scope_id, sts.current_revision(state))


def test_trace_singleton_vs_faction_round_do_not_collide():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, _ai1, _ai2 = pids
    scope = sts.mint_scope(state, "population")
    book = sts._book(state)
    oid_singleton = book.oid("population", "vote", ("singleton", scope.scope_id),
                             scope.scope_id)
    oid_player = book.oid("population", "vote", ("player", h0), scope.scope_id)
    assert oid_singleton != oid_player
    sts.complete_actor(state, None, scope.scope_id, "s", actor_player_id=h0,
                       obligation_id=oid_singleton, phase="population", substep="vote")
    # The player obligation is NOT masked by the singleton completion.
    assert not book.satisfied(oid_player, scope.scope_id, sts.current_revision(state))


def test_trace_post_commit_retry_skips_satisfied_and_denies_replay():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, _ai1, _ai2 = pids
    scope = sts.mint_scope(state, "population")
    book = sts._book(state)
    r = sts.complete_actor(state, None, scope.scope_id, "cmd-X", actor_player_id=h0,
                           phase="population", substep="vote",
                           core_revision_before=12345)
    assert r["success"] and r.get("recorded")
    # Same-revision replay is denied (once-only DK).
    r2 = sts.complete_actor(state, None, scope.scope_id, "cmd-X", actor_player_id=h0,
                            phase="population", substep="vote",
                            core_revision_before=12345)
    assert r2["success"] is False and r2["reason"] == "DUPLICATE_DISPATCH"


def test_trace_year_reset_clears_only_new_year_keys():
    state, pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    h0, _ai1, _ai2 = pids
    scope = sts.mint_scope(state, "population")
    book = sts._book(state)
    oid_old = book.oid("population", "vote", ("player", h0), scope.scope_id)
    sts.complete_actor(state, None, scope.scope_id, "cmd-Y", actor_player_id=h0,
                       phase="population", substep="vote")
    assert book.satisfied(oid_old, scope.scope_id, sts.current_revision(state))
    book.reset_for_new_year()
    # old-year record (different turn/scope) never matches; reuse is impossible.
    assert not book.satisfied(oid_old, scope.scope_id, sts.current_revision(state))


# ===========================================================================
# enter_phase — committed receipt exactly once; navigation is not entry
# ===========================================================================
def test_enter_phase_requires_committed_receipt_and_is_once_only():
    state, _pids = _mk_state(humans=[PlayerType.HUMAN], ais=[PlayerType.AI])
    # Visual navigation / non-committed receipt is NOT entry.
    assert sts.enter_phase(state, {"phase": "senate"})["success"] is False
    receipt = {"committed": True, "receipt_id": "r1", "phase": "senate"}
    first = sts.enter_phase(state, receipt)
    assert first["success"] is True
    assert first["phase_entered"]["phase"] == "senate"
    # consuming the same committed receipt twice is refused.
    second = sts.enter_phase(state, receipt)
    assert second["success"] is False and second["reason"] == "DUPLICATE_RECEIPT"


# ===========================================================================
# GR-T11 — authority parity: no shared testing bypass, one AI criterion
# ===========================================================================
def test_store_forum_scheduler_has_no_testing_bypass_and_uses_playertype():
    root = pathlib.Path(__file__).resolve().parents[3]
    text = (root / "src" / "ui" / "gui" / "session_store.py").read_text(
        encoding="utf-8")
    # the AI Forum Processing block must not flip the global testing toggle.
    assert "testing.bypass_player_check = True" not in text
    # and must not select "AI" by "not the viewer".
    assert "p.player_id != self._viewer_id" not in text
