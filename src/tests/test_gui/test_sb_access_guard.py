"""EOR20261013-02 S-B Group 1 — active-seat read/write guard (production chain).

Covers the single access policy ``src.api.session_access`` invoked at the minimal
shared boundaries: ``get_session_snapshot``, the phase views, the global query and
the state-mutating Adapter dispatch.

Production entries only: ``session_api.create_gui_prototype_session`` + an explicit
``register_hotseat_session`` binding (the service-issued opaque handle). A
never-registered state keeps the historical CLI exemption; a registered Hot-seat
state denies a non-current/unauthorized read/write with a structured DENIED and
NO source-state mutation.
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
from src.api import session_access
from src.api import gui_query_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.api_adapter import GuiApiAdapter


@pytest.fixture(autouse=True)
def _restore_rng():
    """Keep these session-creating tests transparent to suite ordering (the
    established GUI-harness convention: restore the process RNG after each test)."""
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _hotseat_session(register=True, principal_index=0):
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    player_ids = [p.player_id for p in state.get_all_players()]
    # Make all seats HUMAN so any of them could be the authoritative actor.
    for pid in player_ids[1:]:
        original = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(
            player_id=pid, faction_id=original.faction_id, player_type=PlayerType.HUMAN))
    state.set_turn_order(player_ids)
    state.set_current_player(player_ids[principal_index])
    if register:
        session_access.register_hotseat_session(state, player_ids[principal_index], epoch=0)
    return state, player_ids


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _ctx(state):
    """The service-issued handle the trusted routing layer would present (DG-01)."""
    return session_access.current_caller_context(state)


# ===========================================================================
# Read guard — snapshot / phase view / query
# ===========================================================================
def test_snapshot_non_current_viewer_denied_and_no_mutation():
    state, pids = _hotseat_session(register=True, principal_index=0)
    before = _digest(state)
    # Current actor is the principal; ask for ANOTHER seat's projection.
    denied = session_api.get_session_snapshot(state, pids[1])
    assert denied["success"] is False
    assert denied["data"] is None
    assert denied["errors"][0]["code"] == "DENIED"
    assert denied["errors"][0]["scope"] == "session"
    assert _digest(state) == before, "denied read mutated source state"


def test_snapshot_current_principal_allowed():
    state, pids = _hotseat_session(register=True, principal_index=0)
    # S-B-R4: a legitimate current-seat read presents the service handle (DG-01).
    ok = session_api.get_session_snapshot(state, pids[0], caller_context=_ctx(state))
    assert ok["success"] is True
    assert ok["data"]["viewer_player_id"] == pids[0]


def test_phase_view_non_current_viewer_denied():
    state, pids = _hotseat_session(register=True, principal_index=0)
    before = _digest(state)
    for fn in (session_api.get_population_view, session_api.get_resolution_view):
        denied = fn(state, pids[2])
        assert denied["success"] is False
        assert denied["errors"][0]["code"] == "DENIED"
    assert _digest(state) == before


def test_phase_view_current_principal_allowed():
    state, pids = _hotseat_session(register=True, principal_index=0)
    ok = session_api.get_population_view(state, pids[0], caller_context=_ctx(state))
    assert ok["success"] is True


def test_query_non_current_viewer_denied_safe_shell():
    state, pids = _hotseat_session(register=True, principal_index=0)
    before = _digest(state)
    result = gui_query_api.get_global_query_result(state, pids[1], "figure_search", "", "")
    assert result["success"] is False
    dto = result["data"]
    assert dto["result_state"] == "DENIED"
    assert [e["code"] for e in dto["errors"]] == [gui_query_api.ERR_VIEWER_UNAVAILABLE]
    # CLOSED typed safe shell: no raw backend reason, no items.
    assert dto["items"] == []
    assert "SECRET" not in str(dto)
    assert _digest(state) == before


def test_query_current_principal_allowed():
    state, pids = _hotseat_session(register=True, principal_index=0)
    result = gui_query_api.get_global_query_result(
        state, pids[0], "figure_search", "", "", caller_context=_ctx(state))
    assert result["success"] is True
    assert result["data"]["result_state"] in ("OK", "EMPTY")


# ===========================================================================
# State-mutating boundary (Adapter.call) — non-current command DENIED, no mutation
# ===========================================================================
def test_mutation_non_current_actor_denied_no_mutation():
    state, pids = _hotseat_session(register=True, principal_index=0)
    adapter = GuiApiAdapter(state)
    # Current authoritative actor is pids[0]; a command through the adapter while
    # a DIFFERENT actor is not current must be refused.
    state.set_current_player(pids[1])  # actor != registered principal
    before = _digest(state)
    feedback = adapter.campaign(pids[0], 1, 10)
    assert feedback["success"] is False
    assert feedback["feedback_type"] == "error"
    assert any((e.get("code") == "DENIED") for e in feedback["error_items"])
    assert _digest(state) == before, "denied mutation reached the API"


def test_mutation_current_principal_allowed():
    state, pids = _hotseat_session(register=True, principal_index=0)
    adapter = GuiApiAdapter(state)
    # Principal == current HUMAN actor -> the guard lets the command reach the API
    # (the API's own business rules decide the outcome; the guard is not a bypass).
    feedback = adapter.campaign(pids[0], 1, 10)
    assert not any((e.get("code") == "DENIED") for e in feedback.get("error_items", [])), \
        "guard blocked an authorized current-seat command"
    # Direct predicate agrees only when the same service handle is presented.
    assert session_access.denied_or_none(
        state, session_access.OP_MUTATE, caller_context=_ctx(state)) is None


# ===========================================================================
# Narrow preserved exemptions
# ===========================================================================
def test_unregistered_state_keeps_cli_exemption():
    state, pids = _hotseat_session(register=False)
    # Not a Hot-seat session → historical behaviour (any viewer read works).
    assert session_access.is_hotseat_registered(state) is False
    ok = session_api.get_session_snapshot(state, pids[1])
    assert ok["success"] is True
    result = gui_query_api.get_global_query_result(state, pids[1], "figure_search", "", "")
    assert result["success"] is True


def test_ai_internal_capability_exemption():
    state, pids = _hotseat_session(register=True, principal_index=0)
    # Make the current actor an AI seat.
    original = state.get_player(pids[1])
    state.remove_player(pids[1])
    state.add_player(Player(
        player_id=pids[1], faction_id=original.faction_id, player_type=PlayerType.AI))
    state.set_current_player(pids[1])
    # F01 (§1.4A): the mere state fact "current actor is AI" grants NOTHING.
    assert session_access.authorize_hotseat(state, session_access.OP_MUTATE).allowed is False
    assert session_access.authorize_ai(state, pids[1], session_access.OP_MUTATE).allowed is False
    # Only the explicitly presented service-private scheduled-AI capability is admitted.
    # Only the explicitly presented service-private scheduled-AI capability is
    # admitted, and only inside the owning masked execution window (F01 §1.4A/F03).
    session_access.begin_masked_execution(
        state, txn_id="t1", authorization_epoch=0,
        phase="combat", substep="drain", revision=0)
    cap = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[1], txn_id="t1", authorization_epoch=0)
    ai_ok = session_access.authorize_ai(
        state, pids[1], session_access.OP_MUTATE, ai_capability=cap)
    assert ai_ok.allowed and ai_ok.exempt == "ai"
    # A HUMAN principal cannot obtain the AI capability.
    human_ai = session_access.authorize_ai(
        state, pids[0], session_access.OP_MUTATE, ai_capability=cap)
    assert human_ai.allowed is False
    # A forged capability (wrong id) is rejected.
    forged = session_access.AICapability(
        capability_id="forged", session_id=session_access._state_identity(state),
        txn_id="t1", operation="next_player", actor="ai", phase="combat",
        substep="drain", revision=0, authorization_epoch=0)
    assert session_access.authorize_ai(
        state, pids[1], session_access.OP_MUTATE, ai_capability=forged).allowed is False


def test_revoked_session_denies_even_for_former_principal():
    state, pids = _hotseat_session(register=True, principal_index=0)
    session_access.revoke_hotseat_session(state)
    denied = session_api.get_session_snapshot(state, pids[0])
    assert denied["success"] is False
    assert denied["errors"][0]["code"] == "DENIED"


def test_missing_handle_registered_state_denies():
    """Omission must not silently become CLI mode: a registered slot bound to
    ``None`` denies (it does not fall back to the CLI exemption)."""
    state, pids = _hotseat_session(register=True, principal_index=0)
    setattr(state, session_access._CONTEXT_ATTR, None)
    denied = session_api.get_session_snapshot(state, pids[0])
    assert denied["success"] is False


def test_create_gui_hotseat_session_registers_and_guards():
    """Additive production factory: the real S-A chain + hot-seat registration,
    so the guard is enforced fail-closed on a production-created session."""
    result = session_api.create_gui_hotseat_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert session_access.is_hotseat_registered(state) is True
    assert result["data"]["hotseat_context"].principal_player_id == pids[0]
    # Current principal read OK; a foreign seat denied; no mutation on denial.
    before = _digest(state)
    assert session_api.get_session_snapshot(state, pids[0], caller_context=_ctx(state))["success"] is True
    assert session_api.get_session_snapshot(state, pids[1], caller_context=_ctx(state))["success"] is False
    assert _digest(state) == before
