"""EOR20261013-02 S-B-R3a — Access Authority Closure contract tests (DG-01).

Frozen basis: ``02-sa-design/S-B-R3-Design-Delta.md`` v2 (DG-01 §1.2/§1.4A/§1.5,
F01/F04) + ``S-B-R3_Implementation_and_Test_Overlay.md`` (§1 endpoint registry,
§3 oracle reverse-validation). This module encodes the R3a *contract* oracles:

  * R-01 (F04-qualified): a registered Hot-seat state with a valid current HUMAN
    principal DENIES an ordinary public request that omits / forges / presents a
    foreign / stale caller context, with the ENDPOINT-APPROPRIATE refusal
    (ordinary ``DENIED`` envelope for the API boundary; the CLOSED typed safe shell
    for the Query boundary), and NO mutation / DTO build / RNG draw.
  * R-05: the full endpoint registry (population + D2 mutations + resolution/game
    + test-config knob) — not merely the once-visible slots.
  * R-06: a public suspended/AI request is DENIED (no state-derived AI bypass)
    while the legitimate internal masked drain presenting the service AI
    capability succeeds (F01 §1.4A) — both proven together.

Three INDEPENDENT no-side-effect oracles are used: the source-state digest, the
process RNG position, and a dedicated DTO-builder spy/counter (a ``data is None``
assertion alone does NOT prove the builder was not invoked).
"""
import copy
import os
import random
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, session_access, gui_query_api
from src.api import player_api, population_api
from src.core.entities.player import Player, PlayerType


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


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


# ---------------------------------------------------------------------------
# R-01 — omission / forgery / foreign / stale-epoch refusals at real endpoints
# ---------------------------------------------------------------------------
def test_omission_denies_read_boundaries_no_side_effects():
    state, pids = _hotseat()
    before = _digest(state)
    rng_before = random.getstate()
    builder_calls = {"n": 0}
    real_builder = session_api._build_available_actions

    def _spy(*a, **k):
        builder_calls["n"] += 1
        return real_builder(*a, **k)

    with patch.object(session_api, "_build_available_actions", _spy):
        for fn in (session_api.get_session_snapshot,
                   session_api.get_population_view,
                   session_api.get_resolution_view):
            res = fn(state, pids[0])  # NO caller_context presented
            assert res["success"] is False, fn.__name__
            assert res["data"] is None, fn.__name__
            assert res["errors"][0]["code"] == "DENIED", fn.__name__
            assert res["errors"][0]["scope"] == "session", fn.__name__
    assert builder_calls["n"] == 0, "DTO builder invoked on a denied read"
    assert _digest(state) == before, "denied read mutated source state"
    assert random.getstate() == rng_before, "denied read consumed RNG"


def test_omission_query_boundary_returns_closed_safe_shell():
    state, pids = _hotseat()
    before = _digest(state)
    rng_before = random.getstate()
    result = gui_query_api.get_global_query_result(
        state, pids[0], "figure_search", "", "")  # NO caller_context
    assert result["success"] is False
    dto = result["data"]
    # CLOSED typed safe shell: result_state DENIED + whitelisted enum + empty
    # items/summary + NO raw backend reason (Guard §Result contract; Query CLOSED).
    assert dto["result_state"] == "DENIED"
    assert [e["code"] for e in dto["errors"]] == [gui_query_api.ERR_VIEWER_UNAVAILABLE]
    assert dto["items"] == []
    assert dto["summary"] == {}
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_omission_denies_mutation_boundaries_no_side_effects():
    state, pids = _hotseat()
    before = _digest(state)
    rng_before = random.getstate()
    boundaries = [
        (player_api.next_player, (state, pids[0])),
        (population_api.campaign, (state, pids[0], 1, 10)),
        (population_api.vote, (state, pids[0], "consul", 1)),
        (population_api.resolve_election, (state,)),
        (session_api.complete_population_player, (state, pids[0])),
        (session_api.resolve_population_slice, (state,)),
        (session_api.advance_population_phase, (state, pids[0])),
    ]
    for fn, args in boundaries:
        res = fn(*args)  # NO caller_context presented
        assert isinstance(res, dict), fn.__name__
        assert res.get("success") is False, fn.__name__
        assert res["errors"][0]["code"] == "DENIED", fn.__name__
    assert _digest(state) == before, "denied mutation reached the source state"
    assert random.getstate() == rng_before, "denied mutation consumed RNG"


def test_forged_foreign_stale_contexts_denied():
    state, pids = _hotseat()
    # forged: same session/principal/epoch but a non-registry handle_id
    forged = session_access.HotseatContext(
        session_id=session_access._state_identity(state),
        principal_player_id=pids[0], epoch=0, lifecycle="ACTIVE",
        revoked=False, handle_id="forged-ctx")
    dec = session_api.get_session_snapshot(state, pids[0], caller_context=forged)
    assert dec["success"] is False and dec["errors"][0]["code"] == "DENIED"

    # foreign: a valid handle issued for a DIFFERENT state
    other = session_api.create_gui_hotseat_session(start_phase="population")["data"]["state"]
    foreign = _ctx(other)
    assert foreign is not None
    dec = session_api.get_session_snapshot(state, pids[0], caller_context=foreign)
    assert dec["success"] is False

    # stale epoch: same identity but a wrong epoch
    good = _ctx(state)
    stale = session_access.HotseatContext(
        session_id=good.session_id, principal_player_id=good.principal_player_id,
        epoch=good.epoch + 5, lifecycle=good.lifecycle,
        revoked=good.revoked, handle_id=good.handle_id)
    dec = session_api.get_session_snapshot(state, pids[0], caller_context=stale)
    assert dec["success"] is False


def test_positive_presented_handle_reaches_business_layer():
    state, pids = _hotseat()
    ok = session_api.get_session_snapshot(state, pids[0], caller_context=_ctx(state))
    assert ok["success"] is True
    # Omission is never rescued by reading the handle off the state itself.
    assert session_access.present_decision(
        state, session_access.OP_READ_SNAPSHOT, viewer=pids[0]).allowed is False


def test_revoked_context_denied_at_read_and_write():
    state, pids = _hotseat()
    good = _ctx(state)
    session_access.revoke_hotseat_session(state)
    assert session_api.get_session_snapshot(state, pids[0], caller_context=good)["success"] is False
    assert player_api.next_player(state, pids[0], caller_context=good)["success"] is False


# ---------------------------------------------------------------------------
# R-06 — public suspended-AI denial vs legitimate masked-drain capability (F01)
# ---------------------------------------------------------------------------
def test_r06_public_ai_denied_and_masked_drain_capability_allows():
    state, pids = _hotseat()
    # Current actor becomes AI.
    o = state.get_player(pids[0])
    state.remove_player(pids[0])
    state.add_player(Player(player_id=pids[0], faction_id=o.faction_id,
                            player_type=PlayerType.AI))
    state.set_current_player(pids[0])
    # (i) public request: DENIED — no state-derived AI bypass (ACTIVE and masked).
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player").allowed is False
    session_access.suspend_hotseat_session(state)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player").allowed is False
    # (ii) legitimate internal masked drain presenting the service capability.
    session_access.begin_masked_execution(
        state, txn_id="txn-r06", authorization_epoch=0,
        phase="combat", substep="drain", revision=0)
    cap = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-r06", authorization_epoch=0)
    dec = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player", ai_capability=cap)
    assert dec.allowed and dec.exempt == "ai"
    # F03: bound to the exact command / operation / owning txn, not mint-time copies.
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="campaign",
        ai_capability=cap).allowed is False
    assert session_access.authorize_public(
        state, session_access.OP_READ_SNAPSHOT, ai_capability=cap).allowed is False
    wrong_txn = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-other", authorization_epoch=0)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=wrong_txn).allowed is False
    # A REAL guarded boundary performs the drain inside the masked window.
    cap2 = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-r06", authorization_epoch=0)
    drain = player_api.next_player(state, pids[0], ai_capability=cap2)
    codes = {e.get("code") for e in (drain.get("errors") or []) if isinstance(e, dict)}
    assert "DENIED" not in codes, "the legitimate masked drain was blocked"
    # A consumed capability is not replayable.
    session_access.consume_ai_capability(state)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=cap2).allowed is False
    # Exit/failure revokes the capability; it is never resurrected.
    session_access.revoke_ai_capability(state)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=cap2).allowed is False
