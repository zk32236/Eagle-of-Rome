"""EOR20261013-02 S-B-R3a — all-endpoint negative matrix + independent oracles.

F04 / F05 (S-B-R3 Design-Delta v2 §1.5): for EVERY registered read and mutation
endpoint, each of the five negative caller-context classes — **omission / forged /
foreign / revoked / stale** — must produce the *endpoint-appropriate* refusal:

  * ordinary API boundary  -> the structured ordinary DENIED envelope
    (``{success: false, data: null, errors: [{code: "DENIED", scope: "session"}]}``);
  * Query boundary         -> the CLOSED typed safe shell (``result_state=DENIED``,
    whitelisted ``viewer_unavailable``, empty items/summary, no raw backend reason).

Each negative is checked with THREE INDEPENDENT no-side-effect oracles (a
``data is None`` assertion alone does NOT prove the DTO builder was not invoked):

  (1) DTO-builder spy/counter — the endpoint module's response builder
      (``api_response``; ``_build_*`` for Query; ``_ok`` for test-config) is NOT
      invoked on a refusal;
  (2) source-state digest — ``state.to_dict()`` is unchanged;
  (3) process RNG position — ``random.getstate()`` is unchanged.
"""
import copy
import os
import random
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import (session_api, session_access, gui_query_api, player_api,
                     population_api, mortality_api, revenue_api, forum_api,
                     senate_api, combat_api, game_api, resolution_api,
                     test_config_api)
from src.core.entities.player import Player, PlayerType


@pytest.fixture(autouse=True)
def _restore_rng():
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _hotseat():
    """Production chain: real S-A factory + hot-seat registration, all-HUMAN."""
    result = session_api.create_gui_hotseat_session(start_phase="population")
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
    session_access.advance_hotseat_principal(state, pids[0], 0)
    return state, pids


def _ctx(state):
    return session_access.current_caller_context(state)


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _forged(state, pids):
    return session_access.HotseatContext(
        session_id=session_access._state_identity(state),
        principal_player_id=pids[0], epoch=0, lifecycle="ACTIVE",
        revoked=False, handle_id="forged-ctx")


def _stale(state, pids):
    good = _ctx(state)
    return session_access.HotseatContext(
        session_id=good.session_id, principal_player_id=good.principal_player_id,
        epoch=good.epoch + 7, lifecycle=good.lifecycle, revoked=good.revoked,
        handle_id=good.handle_id)


# ---------------------------------------------------------------------------
# Endpoint inventories
# ---------------------------------------------------------------------------
def _read_endpoints(state, pids):
    return [
        ("session_api.get_session_snapshot", session_api.get_session_snapshot,
         (state, pids[0])),
        ("session_api.get_population_view", session_api.get_population_view,
         (state, pids[0])),
        ("session_api.get_resolution_view", session_api.get_resolution_view,
         (state, pids[0])),
        ("mortality_api.get_mortality_view", mortality_api.get_mortality_view,
         (state, pids[0])),
        ("revenue_api.get_revenue_view", revenue_api.get_revenue_view,
         (state, pids[0])),
        ("forum_api.get_forum_view", forum_api.get_forum_view, (state, pids[0])),
        ("senate_api.get_senate_view", senate_api.get_senate_view, (state, pids[0])),
        ("combat_api.get_combat_view", combat_api.get_combat_view, (state, pids[0])),
        ("player_api.get_players", player_api.get_players, (state,)),
        ("player_api.get_current_player", player_api.get_current_player, (state,)),
        ("population_api.get_candidates", population_api.get_candidates, (state,)),
        ("test_config_api.get_test_config", test_config_api.get_test_config,
         (state, pids[0])),
    ]


def _mutation_endpoints(state, pids):
    """The full R-05 registry (58 callable names incl. the ``end_turn`` alias)."""
    return [
        ("player_api.next_player", player_api.next_player, (state, pids[0])),
        ("player_api.end_turn", player_api.end_turn, (state, pids[0])),
        ("session_api.complete_population_player",
         session_api.complete_population_player, (state, pids[0])),
        ("session_api.submit_population_votes", session_api.submit_population_votes,
         (state, pids[0], {})),
        ("session_api.resolve_population_slice", session_api.resolve_population_slice,
         (state,)),
        ("session_api.advance_population_phase", session_api.advance_population_phase,
         (state, pids[0])),
        ("mortality_api.execute_mortality_phase", mortality_api.execute_mortality_phase,
         (state, pids[0])),
        ("mortality_api.advance_mortality_phase", mortality_api.advance_mortality_phase,
         (state, pids[0])),
        ("revenue_api.execute_revenue_phase", revenue_api.execute_revenue_phase,
         (state, pids[0])),
        ("revenue_api.advance_revenue_phase", revenue_api.advance_revenue_phase,
         (state, pids[0])),
        ("forum_api.retire_figure", forum_api.retire_figure, (state, pids[0], 1)),
        ("forum_api.open_market", forum_api.open_market, (state, pids[0])),
        ("forum_api.recruit_figure", forum_api.recruit_figure, (state, pids[0], 1, 1)),
        ("forum_api.place_bid", forum_api.place_bid, (state, pids[0], 1, 1, 1)),
        ("forum_api.buy_land", forum_api.buy_land, (state, pids[0], 1, 1)),
        ("forum_api.vote_triumph", forum_api.vote_triumph, (state, pids[0], "w", True)),
        ("forum_api.resolve_forum", forum_api.resolve_forum, (state,)),
        ("forum_api.advance_forum_phase", forum_api.advance_forum_phase, (state, pids[0])),
        ("senate_api.propose_many", senate_api.propose_many, (state, pids[0], [])),
        ("senate_api.auto_submit_proposals", senate_api.auto_submit_proposals, (state,)),
        ("senate_api.finalize_senate_if_ready", senate_api.finalize_senate_if_ready,
         (state,)),
        ("senate_api.vote", senate_api.vote, (state, pids[0], [], [])),
        ("senate_api.veto", senate_api.veto, (state, pids[0], [])),
        ("senate_api.resolve_senate", senate_api.resolve_senate, (state,)),
        ("senate_api.advance_senate_phase", senate_api.advance_senate_phase,
         (state, pids[0])),
        ("combat_api.select_war", combat_api.select_war, (state, pids[0], "w")),
        ("combat_api.do_combat_action", combat_api.do_combat_action,
         (state, pids[0], "w", "attack")),
        ("combat_api.confirm_battle_result", combat_api.confirm_battle_result,
         (state, pids[0])),
        ("combat_api.advance_combat", combat_api.advance_combat, (state, pids[0])),
        ("combat_api.auto_resolve_combat", combat_api.auto_resolve_combat,
         (state, pids[0])),
        ("game_api.execute_phase", game_api.execute_phase,
         (state, "mortality", pids[0])),
        ("game_api.advance_year", game_api.advance_year, (state, pids[0])),
        ("population_api.campaign", population_api.campaign, (state, pids[0], 1, 10)),
        ("population_api.batch_campaign", population_api.batch_campaign,
         (state, pids[0], [])),
        ("population_api.batch_vote", population_api.batch_vote, (state, pids[0], [])),
        ("population_api.vote", population_api.vote, (state, pids[0], "consul", 1)),
        ("population_api.resolve_election", population_api.resolve_election, (state,)),
        ("population_api.convert_battlefield_commanders",
         population_api.convert_battlefield_commanders, (state,)),
        ("population_api.archive_office_holders",
         population_api.archive_office_holders, (state,)),
        ("population_api.begin_population_phase",
         population_api.begin_population_phase, (state,)),
        ("population_api.process_population_disbandments",
         population_api.process_population_disbandments, (state,)),
        ("senate_api.propose", senate_api.propose,
         (state, pids[0], "war_declaration")),
        ("senate_api.apply_auto_tribune_vetoes", senate_api.apply_auto_tribune_vetoes,
         (state,)),
        ("senate_api.execute_war_declaration", senate_api.execute_war_declaration,
         (state, None, 1, 1)),
        ("senate_api.execute_passed_peace_treaty",
         senate_api.execute_passed_peace_treaty, (state, None)),
        ("senate_api.assign_governors", senate_api.assign_governors, (state,)),
        ("senate_api.assign_fleets_to_active_wars",
         senate_api.assign_fleets_to_active_wars, (state,)),
        ("senate_api.auto_vote", senate_api.auto_vote, (state, pids[0], [])),
        ("resolution_api.execute_resolution", resolution_api.execute_resolution,
         (state,)),
        ("game_api.execute_turn", game_api.execute_turn, (state, pids[0])),
        ("forum_api.generate_figures", forum_api.generate_figures, (state,)),
        ("forum_api.generate_contracts", forum_api.generate_contracts, (state,)),
        ("forum_api.initialize_forum_turn", forum_api.initialize_forum_turn, (state,)),
        ("forum_api.check_province_unrest", forum_api.check_province_unrest, (state,)),
        ("forum_api.execute_land_acts", forum_api.execute_land_acts, (state,)),
        ("forum_api.resolve_land_trades", forum_api.resolve_land_trades, (state,)),
        ("forum_api.transact_land", forum_api.transact_land, (state, pids[0], 1, 2)),
        ("test_config_api.set_test_config", test_config_api.set_test_config,
         (state, pids[0], "force_battle_result", "victory")),
    ]


# ---------------------------------------------------------------------------
# Independent DTO-builder spy oracle
# ---------------------------------------------------------------------------
_BUILDER_MODULES = [session_api, player_api, population_api, mortality_api,
                    revenue_api, forum_api, senate_api, combat_api, game_api,
                    resolution_api]


def _builder_spy(attr="api_response"):
    """Patch every endpoint module's response builder; return (counter, stops)."""
    counter = {"n": 0}
    stops = []
    for module in _BUILDER_MODULES:
        if not hasattr(module, attr):
            continue
        real = getattr(module, attr)

        def _make(real=real):
            def _spy(*a, **k):
                counter["n"] += 1
                return real(*a, **k)
            return _spy

        patcher = patch.object(module, attr, _make())
        patcher.start()
        stops.append(patcher)
    return counter, stops


def _run_negatives(endpoint_calls, present, builder_counter):
    """Run one negative class across all endpoints; assert refusal + oracles."""
    stops = builder_counter[1]
    try:
        for label, fn, args in endpoint_calls:
            kwargs = present()
            res = fn(*args, **kwargs)
            assert isinstance(res, dict), label
            assert res.get("success") is False, (label, res)
            errors = res.get("errors") or []
            codes = {e.get("code") for e in errors if isinstance(e, dict)}
            assert "DENIED" in codes, (label, res)
            assert res.get("data") is None, (label, res)
    finally:
        for patcher in stops:
            patcher.stop()
    assert builder_counter[0]["n"] == 0, "a DTO/response builder ran on a denial"


# ---------------------------------------------------------------------------
# Ordinary read boundaries
# ---------------------------------------------------------------------------
def test_read_endpoints_omission_denied_no_side_effects():
    state, pids = _hotseat()
    before, rng_before = _digest(state), random.getstate()
    counter = _builder_spy()
    _run_negatives(_read_endpoints(state, pids), lambda: {}, counter)
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_read_endpoints_forged_foreign_revoked_stale_denied():
    for kind in ("forged", "foreign", "stale"):
        state, pids = _hotseat()
        other = session_api.create_gui_hotseat_session(start_phase="population")
        foreign = _ctx(other["data"]["state"])
        before, rng_before = _digest(state), random.getstate()

        def present(kind=kind, state=state, pids=pids, foreign=foreign):
            if kind == "forged":
                return {"caller_context": _forged(state, pids)}
            if kind == "foreign":
                return {"caller_context": foreign}
            return {"caller_context": _stale(state, pids)}

        counter = _builder_spy()
        _run_negatives(_read_endpoints(state, pids), present, counter)
        assert _digest(state) == before
        assert random.getstate() == rng_before


def test_read_endpoints_revoked_context_denied():
    state, pids = _hotseat()
    good = _ctx(state)
    session_access.revoke_hotseat_session(state)
    before, rng_before = _digest(state), random.getstate()
    counter = _builder_spy()
    _run_negatives(_read_endpoints(state, pids),
                   lambda: {"caller_context": good}, counter)
    assert _digest(state) == before
    assert random.getstate() == rng_before


# ---------------------------------------------------------------------------
# Query boundary — CLOSED typed safe shell (its own DTO oracle)
# ---------------------------------------------------------------------------
def _assert_query_shell(state, pids, kwargs):
    calls = {"n": 0}
    real = gui_query_api._build_figure_search

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    before, rng_before = _digest(state), random.getstate()
    with patch.object(gui_query_api, "_build_figure_search", _spy):
        res = gui_query_api.get_global_query_result(
            state, pids[0], "figure_search", "", "", **kwargs)
    assert res["success"] is False
    dto = res["data"]
    assert dto["result_state"] == "DENIED"
    assert [e["code"] for e in dto["errors"]] == [gui_query_api.ERR_VIEWER_UNAVAILABLE]
    assert dto["items"] == [] and dto["summary"] == {}
    assert calls["n"] == 0, "the query engine ran on a denied request"
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_query_boundary_negative_matrix_closed_shell():
    state, pids = _hotseat()
    _assert_query_shell(state, pids, {})  # omission
    _assert_query_shell(state, pids, {"caller_context": _forged(state, pids)})
    other = session_api.create_gui_hotseat_session(start_phase="population")
    _assert_query_shell(state, pids, {"caller_context": _ctx(other["data"]["state"])})
    _assert_query_shell(state, pids, {"caller_context": _stale(state, pids)})
    good = _ctx(state)
    session_access.revoke_hotseat_session(state)
    _assert_query_shell(state, pids, {"caller_context": good})


# ---------------------------------------------------------------------------
# Mutation boundaries (full R-05 registry)
# ---------------------------------------------------------------------------
def test_mutation_endpoints_omission_denied_no_side_effects():
    state, pids = _hotseat()
    before, rng_before = _digest(state), random.getstate()
    counter = _builder_spy()
    _run_negatives(_mutation_endpoints(state, pids), lambda: {}, counter)
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_mutation_endpoints_forged_foreign_stale_denied():
    for kind in ("forged", "foreign", "stale"):
        state, pids = _hotseat()
        other = session_api.create_gui_hotseat_session(start_phase="population")
        foreign = _ctx(other["data"]["state"])
        before, rng_before = _digest(state), random.getstate()

        def present(kind=kind, state=state, pids=pids, foreign=foreign):
            if kind == "forged":
                return {"caller_context": _forged(state, pids)}
            if kind == "foreign":
                return {"caller_context": foreign}
            return {"caller_context": _stale(state, pids)}

        counter = _builder_spy()
        _run_negatives(_mutation_endpoints(state, pids), present, counter)
        assert _digest(state) == before
        assert random.getstate() == rng_before


def test_mutation_endpoints_revoked_context_denied():
    state, pids = _hotseat()
    good = _ctx(state)
    session_access.revoke_hotseat_session(state)
    before, rng_before = _digest(state), random.getstate()
    counter = _builder_spy()
    _run_negatives(_mutation_endpoints(state, pids),
                   lambda: {"caller_context": good}, counter)
    assert _digest(state) == before
    assert random.getstate() == rng_before
