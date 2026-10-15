"""EOR20261013-02 S-C-A2 convergence — R-5 owner-side ledger barrier + R-3
``player_api`` full delegation.

Covers:
  * R-5 forum owner-side barrier wiring (``open_market`` before retirement;
    ``resolve_forum`` before market settlement; ``advance_forum_phase`` scope +
    genuine result predicate) on a REGISTERED Hot-seat session, plus the
    never-registered legacy exemption;
  * R-5 mortality/revenue/game singleton advance barrier (current scope + genuine
    result/execution predicate);
  * R-3 ``player_api.next_player`` delegates to the coordinator ``select_actor`` on
    a COORDINATED pass (canonical seat order) while an un-coordinated legacy state
    keeps the historical rotation (route by session mode; delta §6).

Classification: the API trigger is the real production entry (guarded boundary +
owner API). Raw-state comparison = the pre-commit boundary; a denied operation must
leave the business digest unchanged.

RED/falsification knob: when ``SC_R2_FALSIFY=1`` the coordinator barrier is
disconnected (``owner_barrier`` -> None). The barrier-dependent assertions then
fail, proving the test detects the absence of the wiring (falsification, R4 §5).
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import game_api
from src.api import mortality_api
from src.api import player_api
from src.api import revenue_api
from src.api import session_api
from src.api import session_access
from src.api import session_turn_service as sts
from src.core.entities.player import Player, PlayerType


_FALSIFY = os.environ.get("SC_R2_FALSIFY") == "1"


@pytest.fixture(autouse=True)
def _restore_rng():
    st = random.getstate()
    try:
        yield
    finally:
        random.setstate(st)


@pytest.fixture(autouse=True)
def _maybe_falsify(monkeypatch):
    """Disconnect the coordinator barrier to produce a genuine RED (falsification)."""
    if _FALSIFY:
        monkeypatch.setattr(sts, "owner_barrier", lambda *a, **k: None)


def _registered_state(start_phase, humans, ais):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    want = list(humans) + list(ais)
    while len(want) < len(pids):
        want.append(PlayerType.AI)
    want = want[:len(pids)]
    for pid, kind in zip(pids, want):
        original = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=original.faction_id,
                                player_type=kind))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _ctx(state):
    return session_access.present_context(state)


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _finish_forum(state, pids, substep):
    scope = sts.mint_scope(state, "forum")
    for pid in pids:
        sts.complete_actor(
            state, None, scope.scope_id, f"fin-{substep}-{pid}",
            actor_player_id=pid, phase="forum", substep=substep,
            satisfied_kind=sts.KIND_EXPLICIT_FINISH, core_revision_before=0,
            owner_declared=True)


# ===========================================================================
# R-5 — coordinator barrier: exemption, wrong phase, forum substeps
# ===========================================================================
def test_owner_barrier_exempts_never_registered_state():
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    # un-registered (CLI/legacy) -> barrier is a no-op
    assert sts.owner_barrier(state, "forum", "retirement") is None


def test_owner_barrier_wrong_phase():
    state, pids = _registered_state("population", [PlayerType.HUMAN, PlayerType.HUMAN],
                                    [PlayerType.AI])
    # current phase is population; a forum/mortality barrier must refuse the scope
    assert sts.owner_barrier(state, "mortality")["reason"] == "WRONG_PHASE"
    assert sts.owner_barrier(state, "forum")["reason"] == "WRONG_PHASE"


# ===========================================================================
# R-5 — forum: open_market needs retirement finish; resolve_forum needs market
# ===========================================================================
def test_forum_open_market_blocked_until_retirement_finished():
    state, pids = _registered_state("forum", [PlayerType.HUMAN, PlayerType.HUMAN],
                                    [PlayerType.AI])
    sts.mint_scope(state, "forum")
    before = _digest(state)
    denied = public_open_market(state, pids[0])
    assert denied["success"] is False
    assert denied["errors"][0] == "PHASE_NOT_READY"
    assert _digest(state) == before, "denied open_market mutated source state"
    # the barrier's allow-condition: an owner-recorded explicit retirement finish
    # lifts the barrier (DATA supplementary; no forced retirement duty).
    assert sts.owner_barrier(state, "forum", "retirement") is not None
    _finish_forum(state, pids, "retirement")
    assert sts.owner_barrier(state, "forum", "retirement") is None
    assert sts.forum_substep_ready(state, "retirement") is True


def public_open_market(state, viewer):
    from src.api import forum_api
    return forum_api.open_market(state, viewer, caller_context=_ctx(state))


def public_resolve_forum(state):
    from src.api import forum_api
    return forum_api.resolve_forum(state, caller_context=_ctx(state))


def public_advance_forum(state, viewer):
    from src.api import forum_api
    return forum_api.advance_forum_phase(state, viewer, caller_context=_ctx(state))


def test_forum_resolve_blocked_until_market_finished_then_advances():
    state, pids = _registered_state("forum", [PlayerType.HUMAN, PlayerType.HUMAN],
                                    [PlayerType.AI])
    _finish_forum(state, pids, "retirement")
    before = _digest(state)
    denied = public_resolve_forum(state)
    assert denied["success"] is False
    assert denied["errors"][0] == "PHASE_NOT_READY"
    assert _digest(state) == before, "denied resolve_forum mutated source state"

    _finish_forum(state, pids, "market")
    resolved = public_resolve_forum(state)
    assert resolved["success"] is True, resolved.get("message")

    advanced = public_advance_forum(state, pids[0])
    assert advanced["success"] is True, advanced.get("message")
    assert state.is_phase_executed("forum") is True


# ===========================================================================
# R-5 — mortality / revenue / game singleton advance barrier
# ===========================================================================
def test_mortality_advance_checks_genuine_result_predicate():
    state, pids = _registered_state("mortality", [PlayerType.HUMAN, PlayerType.AI],
                                    [PlayerType.AI])
    before = _digest(state)
    denied = mortality_api.advance_mortality_phase(state, pids[0], caller_context=_ctx(state))
    assert denied["success"] is False
    assert _digest(state) == before

    ex = mortality_api.execute_mortality_phase(state, pids[0], caller_context=_ctx(state))
    assert ex["success"] is True, ex.get("message")
    adv = mortality_api.advance_mortality_phase(state, pids[0], caller_context=_ctx(state))
    assert adv["success"] is True, adv.get("message")
    assert state.is_phase_executed("mortality") is True


def test_revenue_advance_checks_genuine_result_predicate():
    state, pids = _registered_state("revenue", [PlayerType.HUMAN, PlayerType.AI],
                                    [PlayerType.AI])
    ex = revenue_api.execute_revenue_phase(state, pids[0], caller_context=_ctx(state))
    assert ex["success"] is True, ex.get("message")
    adv = revenue_api.advance_revenue_phase(state, pids[0], caller_context=_ctx(state))
    assert adv["success"] is True, adv.get("message")
    assert state.is_phase_executed("revenue") is True


def test_advance_year_resolution_scope_gate():
    state, pids = _registered_state("resolution", [PlayerType.HUMAN, PlayerType.AI],
                                    [PlayerType.AI])
    # resolution not executed yet -> the fail-closed precondition refuses (no forced escape)
    denied = game_api.advance_year(state, pids[0], force=False, caller_context=_ctx(state))
    assert denied["success"] is False
    state.mark_phase_executed("resolution")
    ok = game_api.advance_year(state, pids[0], force=False, caller_context=_ctx(state))
    assert ok["success"] is True, ok.get("message")


# ===========================================================================
# R-3 — player_api.next_player delegates to the coordinator on a coordinated pass
# ===========================================================================
def _population_state(humans, ais):
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    want = list(humans) + list(ais)
    while len(want) < len(pids):
        want.append(PlayerType.AI)
    want = want[:len(pids)]
    for pid, kind in zip(pids, want):
        original = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=original.faction_id,
                                player_type=kind))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    return state, pids


def test_R3_coordinated_next_player_delegates_to_coordinator(monkeypatch):
    state, pids = _population_state([PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    h0, h1, _ai = pids
    session_access.register_hotseat_session(state, h0, epoch=0)
    # A DIFFERENT legacy rotation order (h0 -> ai) proves the delegation is not a
    # blind turn_order rotation on a coordinated Hot-seat session: the coordinator
    # (select_actor) is the sole cursor writer and its pick is honoured.
    state.set_turn_order([h0, pids[2], h1])
    sts.mint_scope(state, "population")  # the coordinator ledger exists (coordinated)
    calls = []

    def spy(state_arg, *a, **k):
        calls.append(True)
        state_arg.set_current_player(h1)
        return {"success": True, "actor": h1, "controller": "HUMAN"}

    monkeypatch.setattr(sts, "select_actor", spy)
    resp = player_api.next_player(state, h0, caller_context=_ctx(state))
    assert calls == [True], "coordinated next_player must delegate to select_actor"
    assert resp["success"] is True, resp.get("message")
    assert resp["data"]["new_player_id"] == h1, resp["data"]
    assert state.get_current_player().player_id == h1


def test_R3_legacy_uncoordinated_rotation_unchanged():
    state, pids = _population_state([PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    h0, h1, ai = pids
    assert getattr(state, "_session_turn_book", None) is None  # no coordinator ledger
    state.set_turn_order([h0, ai, h1])
    resp = player_api.next_player(state, h0)
    assert resp["success"] is True, resp.get("message")
    # historical blind rotation (session mode routing; CLI semantics unchanged)
    assert resp["data"]["new_player_id"] == ai
