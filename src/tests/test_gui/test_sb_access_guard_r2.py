"""EOR20261013-02 S-B A2 rework — registered production chain + direct boundaries.

These tests exercise the A2 repairs (SA-Verification-Report-S-B / G5 RETURN)
against a REAL registered hot-seat session created by the production factory
(``create_gui_hotseat_session``), NOT an un-registered + fake-provider stand-in:

  * SB-V01 — every public mutation/helper endpoint denies a direct call under a
    revoked/foreign authority, and never mutates source state;
  * SB-V02 — a missing presented context DENIES; a forged / foreign / revoked
    same-epoch context is rejected (issuance identity, not epoch-only);
  * SB-V03 — the SERVICE lifecycle/epoch is authoritative; SUSPENDING/FAILURE
    truly suspends public read/write; the exact-command lease admits only the one
    sanctioned transition;
  * SB-V04 — a registered activation stages privately and fails on a denied read
    (never a false success);
  * SB-V05 — a business rejection with a failed unmask witness stays fail-closed;
  * SB-V06 — the failure surface clears the stale pending faction label;
  * SB-V07 — the structured denial does not export ``_denied_reason``.
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, session_access, gui_query_api
from src.api import player_api, mortality_api, revenue_api, forum_api, senate_api, combat_api, game_api
from src.api import population_api, resolution_api, test_config_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_PENDING, SEAT_MASKED_FAILURE,
)


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _hotseat_session():
    """Production chain: real S-A factory + hot-seat registration."""
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


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _ctx(state):
    """The service-issued handle the trusted routing layer would present (DG-01)."""
    return session_access.current_caller_context(state)


class _Receiver:
    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        self.calls = []
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.calls.append(bool(keep_open))
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _Barrier:
    def __init__(self, arm=True, unmask=True, pending=True):
        self.arm, self.unmask, self.pending = arm, unmask, pending
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return self.arm

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); return self.pending

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return self.unmask

    def show_failure(self, txn, kind):
        self.calls.append(("failure", txn, kind)); return True


# ===========================================================================
# SB-V07 — structured denial never exports the internal reason
# ===========================================================================
def test_denial_envelope_has_no_internal_reason():
    env = session_access.denied_response(session_access.REASON_PRINCIPAL)
    assert env["success"] is False
    assert env["data"] is None
    assert env["errors"][0]["code"] == "DENIED"
    assert env["errors"][0]["scope"] == "session"
    assert "_denied_reason" not in env
    assert "principal" not in str(env["errors"])


# ===========================================================================
# SB-V02 — missing / forged / foreign / revoked context
# ===========================================================================
def test_missing_context_denies_registered_state():
    state, pids = _hotseat_session()
    decision = session_access.authorize_hotseat(state, session_access.OP_MUTATE)
    assert decision.allowed is False
    # R-01 REVERSED (F04-qualified): the boundary itself must DENY an ordinary
    # public request that omits the presented caller context — omission must not
    # silently become CLI mode. (Was: `... is True` — the SB-V02 bypass.)
    denied = session_api.get_session_snapshot(state, pids[0])
    assert denied["success"] is False
    assert denied["data"] is None
    assert denied["errors"][0]["code"] == "DENIED"


def test_forged_context_same_epoch_denies():
    state, pids = _hotseat_session()
    forged = session_access.HotseatContext(
        session_id=f"session-{id(state)}", principal_player_id=pids[0],
        epoch=0, lifecycle="ACTIVE", revoked=False, handle_id="forged-ctx")
    decision = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, request_context=forged)
    assert decision.allowed is False


def test_foreign_session_context_denies():
    s1, p1 = _hotseat_session()
    s2 = session_api.create_gui_hotseat_session(start_phase="population")["data"]["state"]
    foreign = session_access.present_context(s2)
    assert foreign is not None
    decision = session_access.authorize_hotseat(
        s1, session_access.OP_MUTATE, request_context=foreign)
    assert decision.allowed is False


def test_revoked_same_epoch_context_denies():
    state, pids = _hotseat_session()
    ctx = session_access.present_context(state)
    session_access.revoke_hotseat_session(state)
    decision = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, request_context=ctx)
    assert decision.allowed is False
    # A read for the former principal also denies.
    assert session_api.get_session_snapshot(state, pids[0])["success"] is False


# ===========================================================================
# SB-V01 — direct public mutation boundaries deny under a revoked authority
# ===========================================================================
def _all_public_mutations(state, pids):
    # R-05: the FULL frozen-inventory registry (population + D2 module mutations +
    # resolution/game + test-config bypass knob), not merely the slots once visible.
    return [
        (player_api.next_player, (state, pids[0])),
        (player_api.end_turn, (state, pids[0])),  # alias of next_player (58 callable names)
        (session_api.complete_population_player, (state, pids[0])),
        (session_api.submit_population_votes, (state, pids[0], {})),
        (session_api.resolve_population_slice, (state,)),
        (session_api.advance_population_phase, (state, pids[0])),
        (mortality_api.execute_mortality_phase, (state, pids[0])),
        (mortality_api.advance_mortality_phase, (state, pids[0])),
        (revenue_api.execute_revenue_phase, (state, pids[0])),
        (revenue_api.advance_revenue_phase, (state, pids[0])),
        (forum_api.retire_figure, (state, pids[0], 1)),
        (forum_api.open_market, (state, pids[0])),
        (forum_api.recruit_figure, (state, pids[0], 1, 1)),
        (forum_api.place_bid, (state, pids[0], 1, 1, 1)),
        (forum_api.buy_land, (state, pids[0], 1, 1)),
        (forum_api.vote_triumph, (state, pids[0], "w", True)),
        (forum_api.resolve_forum, (state,)),
        (forum_api.advance_forum_phase, (state, pids[0])),
        (senate_api.propose_many, (state, pids[0], [])),
        (senate_api.auto_submit_proposals, (state,)),
        (senate_api.finalize_senate_if_ready, (state,)),
        (senate_api.vote, (state, pids[0], [], [])),
        (senate_api.veto, (state, pids[0], [])),
        (senate_api.resolve_senate, (state,)),
        (senate_api.advance_senate_phase, (state, pids[0])),
        (combat_api.select_war, (state, pids[0], "w")),
        (combat_api.do_combat_action, (state, pids[0], "w", "attack")),
        (combat_api.confirm_battle_result, (state, pids[0])),
        (combat_api.advance_combat, (state, pids[0])),
        (combat_api.auto_resolve_combat, (state, pids[0])),
        (game_api.execute_phase, (state, "mortality", pids[0])),
        (game_api.advance_year, (state, pids[0])),
        # D1 population surface
        (population_api.campaign, (state, pids[0], 1, 10)),
        (population_api.batch_campaign, (state, pids[0], [])),
        (population_api.batch_vote, (state, pids[0], [])),
        (population_api.vote, (state, pids[0], "consul", 1)),
        (population_api.resolve_election, (state,)),
        (population_api.convert_battlefield_commanders, (state,)),
        (population_api.archive_office_holders, (state,)),
        (population_api.begin_population_phase, (state,)),
        (population_api.process_population_disbandments, (state,)),
        # D2 other public core-mutating module functions
        (senate_api.propose, (state, pids[0], "war_declaration")),
        (senate_api.apply_auto_tribune_vetoes, (state,)),
        (senate_api.execute_war_declaration, (state, None, 1, 1)),
        (senate_api.execute_passed_peace_treaty, (state, None)),
        (senate_api.assign_governors, (state,)),
        (senate_api.assign_fleets_to_active_wars, (state,)),
        (senate_api.auto_vote, (state, pids[0])),
        (resolution_api.execute_resolution, (state,)),
        (game_api.execute_turn, (state, pids[0])),
        (forum_api.generate_figures, (state,)),
        (forum_api.generate_contracts, (state,)),
        (forum_api.initialize_forum_turn, (state,)),
        (forum_api.check_province_unrest, (state,)),
        (forum_api.execute_land_acts, (state,)),
        (forum_api.resolve_land_trades, (state,)),
        (forum_api.transact_land, (state, pids[0], 1, 2)),
        (test_config_api.set_test_config, (state, pids[0], "force_battle_result", "victory")),
    ]


def test_every_public_mutation_denies_directly_when_revoked_no_mutation():
    state, pids = _hotseat_session()
    session_access.revoke_hotseat_session(state)
    before = _digest(state)
    rng_before = random.getstate()
    for fn, args in _all_public_mutations(state, pids):
        res = fn(*args)
        assert isinstance(res, dict), fn.__name__
        assert res.get("success") is False, fn.__name__
        errors = res.get("errors") or []
        codes = {e.get("code") for e in errors if isinstance(e, dict)}
        assert "DENIED" in codes, (fn.__name__, res)
    assert _digest(state) == before, "denied mutation reached the source state"
    assert random.getstate() == rng_before, "denied call consumed RNG"


def test_current_seat_positive_mutation_not_denied():
    state, pids = _hotseat_session()
    # Principal == current HUMAN actor; the trusted routing layer presents the
    # service handle -> the guard lets the (business) call through (R-02 revise).
    res = player_api.next_player(state, pids[0], caller_context=_ctx(state))
    errors = res.get("errors") or []
    codes = {e.get("code") for e in errors if isinstance(e, dict)}
    assert "DENIED" not in codes


def test_mutation_claim_foreign_player_denied_no_mutation():
    """F2: the claimed player_id is compared against the presented principal; a
    trusted handle cannot act on a DIFFERENT player's seat."""
    state, pids = _hotseat_session()
    before = _digest(state)
    rng_before = random.getstate()
    res = population_api.campaign(state, pids[1], 1, 10, caller_context=_ctx(state))
    assert res["success"] is False
    assert res["errors"][0]["code"] == "DENIED"
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_public_boundary_cannot_self_exempt_with_bypass():
    """F2: a public mutation cannot self-grant authority with bypass_permission=True
    (nor via the global testing.bypass_player_check toggle)."""
    state, pids = _hotseat_session()
    before = _digest(state)
    res = population_api.campaign(state, pids[0], 1, 10, True, caller_context=_ctx(state))
    assert res["success"] is False
    assert res["errors"][0]["code"] == "DENIED"
    assert _digest(state) == before
    # The predicate agrees for the global toggle too; no authority is derived.
    dec = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, request_context=_ctx(state),
        requested_bypass=True)
    assert dec.allowed is False


# ===========================================================================
# CLI / AI narrow preserved exemptions
# ===========================================================================
def test_cli_unregistered_exemption_regression():
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert session_access.is_hotseat_registered(state) is False
    res = player_api.next_player(state, state.get_current_player().player_id)
    codes = {e.get("code") for e in (res.get("errors") or []) if isinstance(e, dict)}
    assert "DENIED" not in codes


def test_ai_exemption_regression_registered():
    state, pids = _hotseat_session()
    # Make the current actor an AI seat.
    o = state.get_player(pids[0])
    state.remove_player(pids[0])
    state.add_player(Player(player_id=pids[0], faction_id=o.faction_id,
                            player_type=PlayerType.AI))
    state.set_current_player(pids[0])
    # (i) R-06: a PUBLIC request relying only on "current actor is AI" is DENIED
    # (no state-derived AI bypass) — on ACTIVE and while suspended/masked.
    public = session_access.authorize_public(state, session_access.OP_MUTATE,
                                             command="next_player")
    assert public.allowed is False
    session_access.suspend_hotseat_session(state)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player").allowed is False
    # (ii) The legitimate internal drain presenting the service AI capability
    # succeeds, but ONLY inside the owning masked execution window (F01 §1.4A/F03).
    session_access.begin_masked_execution(
        state, txn_id="t1", authorization_epoch=0,
        phase="combat", substep="drain", revision=0)
    cap = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="t1", authorization_epoch=0)
    dec = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player", ai_capability=cap)
    assert dec.allowed and dec.exempt == "ai"


def test_r06_capability_bound_to_actual_txn_scope_command():
    """F03: the capability is bound to the ACTUAL operation/command/txn and the
    authoritative masked scope — not merely to its own mint-time copy."""
    state, pids = _hotseat_session()
    o = state.get_player(pids[0])
    state.remove_player(pids[0])
    state.add_player(Player(player_id=pids[0], faction_id=o.faction_id,
                            player_type=PlayerType.AI))
    state.set_current_player(pids[0])
    session_access.begin_masked_execution(
        state, txn_id="txn-1", authorization_epoch=0,
        phase="combat", substep="drain", revision=0)
    cap = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-1", authorization_epoch=0)
    # exact match -> allowed
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=cap).allowed is True
    # a DIFFERENT requested command is rejected (no operation widening)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="campaign",
        ai_capability=cap).allowed is False
    # a READ operation is never authorized by an AI capability
    assert session_access.authorize_public(
        state, session_access.OP_READ_SNAPSHOT, ai_capability=cap).allowed is False
    # changed owning txn -> rejected
    other_txn = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-2", authorization_epoch=0)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=other_txn).allowed is False
    # the authoritative scope changes under the same txn -> the stale cap is rejected
    session_access.begin_masked_execution(
        state, txn_id="txn-1", authorization_epoch=0,
        phase="forum", substep="drain", revision=0)
    stale = session_access.issue_ai_capability(
        state, operation="next_player", phase="combat", substep="drain",
        revision=0, expected_actor=pids[0], txn_id="txn-1", authorization_epoch=0)
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command="next_player",
        ai_capability=stale).allowed is False


# ===========================================================================
# SB-V03/V04 — registered masked flow: suspension + private staging + activation
# ===========================================================================
def _registered_masked_store(barrier=None, ack=True):
    state, pids = _hotseat_session()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    recv = _Receiver(store, ack=ack)
    barrier = barrier or _Barrier()
    store.setHandoffBarrierProvider(barrier)
    return state, pids, store, recv, barrier


def test_registered_masked_flow_suspends_service_then_activates():
    state, pids, store, recv, barrier = _registered_masked_store()
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))

    fb = store.doCompletePlayer()
    assert fb["success"], fb
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    # SB-V03: the service is truly suspended while masked — A reads deny.
    assert session_access.present_decision(
        state, session_access.OP_READ_SNAPSHOT, viewer=pids[0]).allowed is False
    assert session_api.get_session_snapshot(state, pids[0])["success"] is False

    res = store.requestTakeover()
    assert res["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]
    assert len(finals) == 1 and finals[0][1] is True
    # Fresh handle: B reads OK, A (foreign seat) denied.
    assert session_api.get_session_snapshot(state, pids[1], caller_context=_ctx(state))["success"] is True
    assert session_api.get_session_snapshot(state, pids[0], caller_context=_ctx(state))["success"] is False


def test_registered_business_rejection_missing_unmask_fails_closed():
    state, pids, store, recv, barrier = _registered_masked_store()
    barrier.unmask = False
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    from unittest.mock import patch
    with patch.object(store._adapter, "next_player",
                      return_value={"success": False, "message": "no"}):
        fb = store.doCompletePlayer()
    assert fb["success"] is False
    # Fail-closed: the cover stays, no next-seat publication (SB-V05).
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffMaskVisible is True
    assert store.viewerPlayerId != pids[1]
    assert any(s is False for _, s in finals)
    assert session_api.get_session_snapshot(state, pids[1])["success"] is False


def test_registered_activation_preparation_read_failure_no_commit():
    state, pids, store, recv, barrier = _registered_masked_store()
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    # A denied/empty preparation read must NOT commit (SB-V04).
    from unittest.mock import patch
    with patch.object(store._adapter, "read_envelope",
                      return_value={"success": False, "data": None, "errors": []}):
        store.requestTakeover()
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId != pids[1]
    assert not any(s is True for _, s in finals)
    assert session_api.get_session_snapshot(state, pids[1])["success"] is False


def test_failure_surface_clears_pending_faction_label():
    state, pids, store, recv, barrier = _registered_masked_store()
    store.doCompletePlayer()
    assert store.handoffPendingFactionName != ""
    store._fail_masked("after_commit")
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffPendingFactionName == ""
