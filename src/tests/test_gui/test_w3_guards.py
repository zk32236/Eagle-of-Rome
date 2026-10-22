"""W3 — executable negative controls N1–N13 (Acceptance §3).

Each control is a REAL assertion (never explanatory text). Envelopes are either
mutated copies of a genuinely produced ``DeliveryResultV1`` or built through the
public ``delivery_for_actor`` + ``delivery_command_ref`` producers; the validator
under test is the public ``validate_delivery_result``. N6 is an INVARIANT local
probe of the W2b publish gate (a late/stale bundle is not reproducible without a
live event loop).
"""
import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import senate_api, session_access, session_turn_service
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import ClassTier, Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.ui.gui.session_store import (
    FAIL_BEFORE_COMMIT,
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

VIEWER = "player1"


def _state(*, consul="ai", third="human"):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum"]:
        state.mark_phase_executed(phase)
    for fid in ("optimates", "populares", "equites"):
        state.add_faction(Faction(id=fid, name=fid.title(), treasury=50))

    def _figure(fig_id, name, faction, office, tier, influence):
        fig = Figure(id=fig_id, name=name, faction_id=faction, age=40)
        fig.office = office
        fig.class_tier = tier
        fig.influence = influence
        state.add_member(fig)
        state.get_faction(faction).member_ids.append(fig_id)

    _figure(8, "consul", "populares", "consul", ClassTier.NOBILE, 50)
    _figure(9, "tribune", "optimates", "tribune", ClassTier.PLEBEIAN, 30)
    _figure(10, "eques", "equites", None, ClassTier.EQUES, 30)
    _figure(11, "opt", "optimates", None, ClassTier.NOBILE, 40)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=(PlayerType.AI if consul == "ai"
                                         else PlayerType.HUMAN)))
    state.add_player(Player(player_id="player3", faction_id="equites",
                            player_type=(PlayerType.HUMAN if third == "human"
                                         else PlayerType.AI)))
    state._turn_order = ["player1", "player2", "player3"]
    state.set_current_player(VIEWER)
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
    contract.status = ContractStatus.PENDING
    state.record_phase_result("population", {
        "success": True, "message": "Election resolved",
        "data": {"election_results": []},
    })
    session_access.register_hotseat_session(state, VIEWER, epoch=0)
    return state


class _Witness:
    def __init__(self):
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction))
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


def _store(state):
    store = GuiSessionStore(state)
    _Receiver(store)
    store.setHandoffBarrierProvider(_Witness())
    store._viewer_id = VIEWER
    store._seat_lifecycle = SEAT_ACTIVE
    return store


def _advance(state):
    store = _store(state)
    store.doAdvancePopulation()
    return store, (store._committed_receipt or {}).get("data", {}).get("delivery")


def _copy(delivery):
    return {
        **delivery,
        "next": dict(delivery["next"]) if delivery.get("next") else None,
        "terminal": dict(delivery["terminal"]) if delivery.get("terminal") else None,
        "error": dict(delivery["error"]) if delivery.get("error") else None,
    }


# N1 — a forged receiver that is not the real obligation actor
def test_n1_forged_receiver_is_delivery_mismatch():
    state = _state()
    _, delivery = _advance(state)
    forged = _copy(delivery)
    forged["next"]["actor_player_id"] = "player3"
    forged["next"]["controller"] = "HUMAN"
    forged["next"]["disposition"] = "NEXT_HUMAN"
    verdict = session_turn_service.validate_delivery_result(
        state, forged, viewer_id=VIEWER)
    assert verdict["ok"] is False
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH"


# N2 — stale core revision
def test_n2_stale_core_revision_is_rejected():
    state = _state()
    _, delivery = _advance(state)
    stale = _copy(delivery)
    stale["core_revision"] = int(stale["core_revision"]) - 1
    verdict = session_turn_service.validate_delivery_result(
        state, stale, viewer_id=VIEWER)
    assert verdict["ok"] is False
    assert verdict["error"]["stage"] == "revision"


# N3 — caller-forged committed receipt
def test_n3_forged_entry_receipt_is_not_committed():
    state = _state()
    forged = {"committed": True, "phase": "senate", "receipt_id": "fake-receipt"}
    result = session_turn_service.enter_phase(state, forged)
    assert result["success"] is False
    assert result["reason"] == "NOT_COMMITTED"


# N4 — second consumption of one real receipt
def test_n4_duplicate_entry_receipt_is_rejected():
    state = _state()
    receipt = session_turn_service.issue_committed_phase_entry_receipt(
        state, command_id="advance_population_phase", phase="senate",
        payload_digest=VIEWER)
    assert session_turn_service.enter_phase(state, receipt)["success"] is True
    second = session_turn_service.enter_phase(state, receipt)
    assert second["success"] is False and second["reason"] == "DUPLICATE_RECEIPT"


# N5 — an AI actor presented as HUMAN (raw PlayerType contradicts the envelope)
def test_n5_ai_actor_presented_as_human_is_invalid():
    state = _state()
    ref = session_turn_service.delivery_command_ref(
        state, "population", "probe", actor=VIEWER)
    delivery = session_turn_service.delivery_for_actor(
        state, "population", "player2", outcome="CONTINUE", viewer_id=VIEWER,
        command_receipt_ref=ref)
    delivery["next"]["controller"] = "HUMAN"
    delivery["next"]["disposition"] = "NEXT_HUMAN"
    verdict = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)
    assert verdict["ok"] is False
    assert verdict["error"]["stage"] == "receiver"


# N6 — a last_good / stale bundle is not publishable as fresh (INVARIANT probe)
def test_n6_stale_bundle_is_not_publishable():
    state = _state()
    store = _store(state)
    resources = {r["resource_id"]: (dict(r["neutral_value"])
                                    if isinstance(r["neutral_value"], dict)
                                    else r["neutral_value"])
                 for r in store.activation_inventory()}
    bundle = {"resources": resources, "seat_epoch": 0, "txn_id": "",
              "tags": {"session": session_access._state_identity(state),
                       "scope": "activation", "target": VIEWER, "seat_epoch": 0,
                       "core_revision": -999, "publication_revision": 0}}
    assert store._bundle_publishable(bundle, VIEWER) is False


# N7 — finalize before full coverage
def test_n7_finalize_before_coverage_is_phase_not_ready():
    state = _state()
    store, _ = _advance(state)
    fin = store._adapter.call(senate_api.finalize_senate_if_ready, state)
    assert fin["success"] is False
    assert fin["errors"][0]["code"] == "PHASE_NOT_READY"
    assert state.get_phase_result("senate") is None


# N8 — retry without a recorded envelope
def test_n8_retry_without_record_is_a_typed_stop():
    state = _state()
    store = _store(state)
    store._seat_lifecycle = SEAT_MASKED_FAILURE
    store._last_delivery = None
    store._delivery_required_command = "advancePopulation"
    result = store.retryHandoff()
    assert result["accepted"] is False
    assert result["delivery_error"]["code"] in (
        "DELIVERY_MISSING_RECEIVER", "DELIVERY_MISMATCH")
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# N9 — a previous-generation scope
def test_n9_foreign_scope_is_rejected():
    state = _state()
    _, delivery = _advance(state)
    foreign = _copy(delivery)
    foreign["scope_id"] = "scope-from-a-previous-generation"
    verdict = session_turn_service.validate_delivery_result(
        state, foreign, viewer_id=VIEWER)
    assert verdict["ok"] is False
    assert verdict["error"]["stage"] == "scope"


# N10 — same-revision duplicate dispatch
def test_n10_same_revision_dispatch_is_denied():
    state = _state()
    scope = session_turn_service.mint_scope(state, "population")
    oid = session_turn_service._book(state).oid(
        "population", "vote", ("player", VIEWER), scope.scope_id)
    first = session_turn_service.issue_owner_receipt(
        state, "probe", actor_player_id=VIEWER, fact_ref="owner:probe1",
        scope_id=scope.scope_id, obligation_id=oid,
        kind=session_turn_service.KIND_ACTION)
    ok = session_turn_service.complete_actor(
        state, None, scope.scope_id, "probe", obligation_id=oid,
        actor_player_id=VIEWER, phase="population", substep="vote",
        satisfied_kind=session_turn_service.KIND_ACTION, owner_receipt=first)
    assert ok["success"] is True
    second = session_turn_service.issue_owner_receipt(
        state, "probe", actor_player_id=VIEWER, fact_ref="owner:probe2",
        scope_id=scope.scope_id, obligation_id=oid,
        kind=session_turn_service.KIND_ACTION)
    records = len(session_turn_service._book(state).records)
    dup = session_turn_service.complete_actor(
        state, None, scope.scope_id, "probe", obligation_id=oid,
        actor_player_id=VIEWER, phase="population", substep="vote",
        satisfied_kind=session_turn_service.KIND_ACTION, owner_receipt=second)
    # An idempotent replay is allowed ONLY as a no-second-effect answer.
    assert dup.get("reason") in ("DUPLICATE_DISPATCH", "ALREADY_SATISFIED")
    assert bool(dup.get("success")) is (dup.get("reason") == "ALREADY_SATISFIED")
    assert len(session_turn_service._book(state).records) == records


# N11 — CONTINUE must name the GLOBAL queue head (A-W3-11 / W-08)
#
# H2-b (AC05 ③): the fixture is now the EXACT three-HUMAN chain that reaches the
# REAL vote queue head — three ACTUAL HUMAN players (the consul is never the AI
# default), ``B`` = the product's own queue head, ``C`` = a REAL later ballot
# obligation of the same scope, and ONLY the O column of the envelope changes.
def _three_human_vote_head(*, proposal_rows=None):
    """Drive the production Slots to the REAL vote-head delivery (3H).

        entry (p1) -> cross-seat MASKED_PENDING (p2, the HUMAN consul)
        -> real 「接管」 -> real proposal packet (p2) -> vote-head delivery

    The seat machine, the schedule and the validator are the production ones;
    ``B``/``C`` are read back from the product's own envelope/obligation ids.
    """
    state = _state(consul="human", third="human")
    players = [state.get_player(pid) for pid in ("player1", "player2", "player3")]
    assert len(players) == 3 and all(p is not None for p in players), players
    assert [p.player_type for p in players] == [PlayerType.HUMAN] * 3, \
        [p.player_type for p in players]
    assert state.get_player("player2").faction_id == "populares"  # consul seat

    store = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store._pending_player_id == "player2", store._pending_player_id
    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store._viewer_id == "player2", store._viewer_id
    store._refresh_senate_view()
    assert store.canCreateSenateProposal is True, store._senate_view

    rows = proposal_rows or [{"type": "land",
                              "params": {"act_type": "distribution",
                                         "amount_C": 10, "percent": 0.1}}]
    submitted = store.doSubmitSenateProposals([dict(r) for r in rows])
    assert submitted.get("success") is True, submitted
    delivery = (store._committed_receipt or {}).get("data", {}).get("delivery")
    assert isinstance(delivery, dict) and delivery.get("next"), \
        store._committed_receipt
    return state, store, delivery


def _later_ballot_oid(state, delivery, actor):
    """The REAL obligation id of ``actor``'s ballot in the delivery's scope."""
    scope_id = delivery["scope_id"]
    proposals = state.get_senate_proposals()
    assert proposals, "the fixture must have a ballot obligation"
    return session_turn_service._book(state).oid(
        "senate", "vote:%s" % proposals[0]["id"], ("player", actor), scope_id)


def _forged_later(delivery, actor, later_oid):
    """The head envelope with ONLY the O (actor/obligation) column changed."""
    forged = _copy(delivery)
    forged["next"].update({
        "actor_player_id": actor, "controller": "HUMAN",
        "disposition": "NEXT_HUMAN", "obligation_id": list(later_oid),
    })
    return forged


def _assert_only_the_o_column_changed(head, forged):
    """Every non-O column stays byte-identical (the isolation proof)."""
    changed_top = {k for k in set(head) | set(forged)
                   if head.get(k) != forged.get(k)}
    assert changed_top == {"next"}, changed_top
    changed_next = {k for k in set(head["next"]) | set(forged["next"])
                    if head["next"].get(k) != forged["next"].get(k)}
    assert changed_next <= {"actor_player_id", "controller", "disposition",
                            "obligation_id"}, changed_next
    assert head["next"]["obligation_id"] != forged["next"]["obligation_id"]


def test_n11_continue_cannot_skip_the_queue_head():
    state, store, delivery = _three_human_vote_head()
    # The REAL vote-head envelope (B = player1) passes.
    head = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)
    assert head["ok"] is True, head
    assert delivery["next"]["actor_player_id"] == VIEWER, delivery["next"]
    assert delivery["next"]["controller"] == "HUMAN", delivery["next"]

    # C = a REAL later ballot actor of the SAME scope; only the O column changes
    later_oid = _later_ballot_oid(state, delivery, "player3")
    later = _forged_later(delivery, "player3", later_oid)
    _assert_only_the_o_column_changed(delivery, later)

    verdict = session_turn_service.validate_delivery_result(
        state, later, viewer_id="player3")
    assert verdict["ok"] is False
    assert verdict["error"]["stage"] == "obligation"
    # B is unaffected by the rejected C envelope, and C was never consumed
    assert session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)["ok"] is True
    snap = session_turn_service.obligations(state, "senate")
    row = next(o for o in snap.obligations
               if str(o.obligation_id) == str(later_oid))
    assert row.satisfied is False, row


# N12 — registration read exception on the public view
def test_n12_registration_read_failure_is_typed():
    state = _state()
    store = _store(state)
    with patch.object(session_access, "is_hotseat_registered",
                      side_effect=RuntimeError("boom")):
        view = store._adapter.call(senate_api.get_senate_view, state, VIEWER)
    assert view["success"] is False
    assert view["errors"][0]["code"] == "REGISTRATION_UNAVAILABLE"


# N13 — a real downstream AI-executor failure is a CONTINUATION failure
def test_n13_ai_executor_failure_is_committed_continuation_failed():
    state = _state()
    store = _store(state)
    with patch.object(senate_api, "auto_submit_proposals",
                      side_effect=lambda *a, **k: {
                          "success": False, "message": "ai down",
                          "data": {}, "errors": ["ai down"]}):
        result = store.doAdvancePopulation()
    data = result.get("data") or {}
    assert result["success"] is False
    assert data["delivery_error"]["code"] == "COMMITTED_CONTINUATION_FAILED"
    assert data["delivery_error"]["stage"] == "continuation"
    assert data["delivery_error"]["committed"] is True
    assert state.is_phase_executed("population") is True
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# ===========================================================================
# F01 / AC-W3-19 (G3-delta §7.1 / §9.1) — the THIRD commit state
# ===========================================================================
class _NoUnmaskWitness:
    """The SAME production seam as ``_Witness`` above, but the final-reveal gate
    never receipts (a real gate miss — never a fabricated boolean witness)."""

    def __init__(self):
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction))
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return False

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


def _typed_activation_error(store):
    return ((store._activation_result or {}).get("data") or {}).get(
        "delivery_error")


def test_ac_w3_19_commit_states_proven_unproven_not_committed():
    """AC-W3-19 (§9.1): the three commit states must be pairwise distinguishable.

    * PROVEN        -> ``committed is True``
    * NOT_COMMITTED -> ``committed is False``
    * UNPROVEN      -> the ``committed`` key is OMITTED (never a default value)

    UNPROVEN is the dispatch-exception branch: neither ``True`` (the old default
    that leaked a post-commit copy into an unproven failure) nor ``False`` may be
    fabricated.
    """
    # (1) PROVEN: the command really committed; only the final-reveal gate misses.
    state = _state(consul="ai", third="ai")
    store = _store(state)
    store.setHandoffBarrierProvider(_NoUnmaskWitness())
    store.doAdvancePopulation()
    proven = _typed_activation_error(store)
    assert proven is not None, "the committed activation must leave a typed record"
    assert proven["code"] == "SEAT_PUBLICATION_FAILED", proven
    assert proven["stage"] == "unmask_frame", proven
    assert proven["committed"] is True, proven

    # (2) NOT_COMMITTED: a non-mutating business refusal whose same-seat recovery
    #     also fails at the final-reveal gate.
    state2 = _state(consul="ai", third="ai")
    state2._phase_results.pop("population", None)
    store2 = _store(state2)
    store2.setHandoffBarrierProvider(_NoUnmaskWitness())
    refused = store2.doAdvancePopulation()
    not_committed = store2._w3_recovery_diagnostic or {}
    assert "delivery_error" not in (refused.get("data") or {}), refused
    assert refused["message"] == "Population phase has not been resolved"
    assert refused["errors"] == []
    assert not_committed.get("committed") is False, refused

    # (3) UNPROVEN: the dispatch itself raised -> nothing proves the commit state.
    state3 = _state(consul="ai", third="ai")
    store3 = _store(state3)
    with patch.object(store3, "_dispatch_owning",
                      side_effect=RuntimeError("dispatch exploded")):
        exploded = store3.doAdvancePopulation()
    unproven = (exploded.get("data") or {}).get("delivery_error") or {}
    assert unproven.get("code") == "COMMIT_STATUS_UNPROVEN", exploded
    assert unproven.get("stage") == "dispatch", exploded
    assert "committed" not in unproven, unproven
    # The unproven route is the GENERIC one: no after_commit copy, no sealed
    # recovery mandate, neutral public projection.
    assert store3.handoffFailureKind == FAIL_BEFORE_COMMIT, store3.handoffFailureKind
    assert store3.seatLifecycle == SEAT_MASKED_FAILURE
    assert store3.viewerPlayerId == ""

    # THREE-WAY distinguishability (no state collapsed into a default).
    states = (proven.get("committed"), not_committed.get("committed"),
              "__ABSENT__" if "committed" not in unproven
              else unproven.get("committed"))
    assert states[0] is True and states[1] is False and states[2] == "__ABSENT__"
    assert len({repr(value) for value in states}) == 3, states


def test_ac_w3_19_precommit_recovery_failure_is_typed_and_keeps_the_refusal():
    """AC-W3-19: when ``commit_proven=False`` and the (same-seat) recovery stage
    fails, the caller must get BOTH the ORIGINAL refusal (message/errors kept
    byte-faithful, never a generalized copy) AND the typed record
    ``{code, stage, committed:false}``."""
    state = _state(consul="ai", third="ai")
    state._phase_results.pop("population", None)
    store = _store(state)
    store.setHandoffBarrierProvider(_NoUnmaskWitness())

    result = store.doAdvancePopulation()

    assert result["success"] is False
    # the original business refusal is preserved verbatim
    assert result["message"] == "Population phase has not been resolved", result
    assert result["errors"] == [], result
    typed = store._w3_recovery_diagnostic or {}
    assert typed.get("code") == "SEAT_PUBLICATION_FAILED", result
    assert typed.get("stage") == "unmask_frame", typed
    assert typed.get("committed") is False, typed
    # the SAME typed record is the Store-private activation result
    assert _typed_activation_error(store) == typed["delivery_error"]
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# ===========================================================================
# F04 / N11 — frozen ISOLATION control for the O (queue-head) column
# ===========================================================================
def test_n11_obligation_rejects_the_later_actor_even_with_the_core_head_matched():
    """F04: the N11 control must ISOLATE column O.

    (A) with the Core still at the ORIGINAL head, a delivery naming a LATER actor is
        rejected by the O column (stage == ``obligation``), not by the K/Core
        column — so the rejection is not merely the old Core check;
    (B) the isolation control: move the Core cursor to that same later actor so the
        K column is SATISFIED, and the SAME envelope is STILL rejected by the SAME
        O column.

    No product mutation and no consumer fake is involved: only the real state and
    the real public validator.
    """
    state, store, delivery = _three_human_vote_head()
    head = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)
    assert head["ok"] is True, head

    later_oid = _later_ballot_oid(state, delivery, "player3")
    later = _forged_later(delivery, "player3", later_oid)
    _assert_only_the_o_column_changed(delivery, later)

    # (A) Core at the ORIGINAL head: O fires first (never "core").
    at_head = session_turn_service.validate_delivery_result(
        state, later, viewer_id="player3")
    assert at_head["ok"] is False, at_head
    assert at_head["error"]["stage"] == "obligation", at_head

    # (B) ISOLATION: the K column is now satisfied, O still rejects.
    state.set_current_player("player3")
    assert state.get_current_player().player_id == "player3"
    isolated = session_turn_service.validate_delivery_result(
        state, later, viewer_id="player3")
    assert isolated["ok"] is False, isolated
    assert isolated["error"]["stage"] == "obligation", isolated
    assert isolated["error"]["code"] == "DELIVERY_MISMATCH", isolated
    # the C ballot obligation is still outstanding: nothing was consumed
    snap = session_turn_service.obligations(state, "senate")
    row = next(o for o in snap.obligations
               if str(o.obligation_id) == str(later_oid))
    assert row.satisfied is False, row


# ===========================================================================
# F04 / AC-W3-18 — the capability key is consumed through the REAL read envelope
# ===========================================================================
def test_ac_w3_18_capability_key_comes_from_the_real_read_envelope():
    """F04: the missing-capability control must remove the key at the REAL
    read-envelope boundary (the API source), never by hand-assigning
    ``store._senate_view``."""
    state = _state(consul="human", third="human")
    store = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    assert store.requestTakeover()["accepted"] is True
    store._refresh_senate_view()
    assert store.canCreateSenateProposal is True

    real = senate_api.get_senate_view

    def _without_capability(*args, **kwargs):
        response = real(*args, **kwargs)
        if isinstance(response, dict) and isinstance(response.get("data"), dict):
            response["data"].pop("can_create_proposal", None)
        return response

    calls = []
    with patch.object(senate_api, "get_senate_view",
                      side_effect=_without_capability), \
            patch.object(store._adapter, "submit_senate_proposals",
                         side_effect=lambda *a, **k: calls.append(1) or {
                             "success": True}):
        # the key really disappears at the boundary, through the REAL pipeline
        store._refresh_senate_view()
        assert "can_create_proposal" not in store._senate_view
        assert store.canCreateSenateProposal is False
        refused = store.doSubmitSenateProposals([])

    assert refused["success"] is False, refused
    assert refused.get("feedback_type") == "warning", refused
    assert calls == [], "the capability gate must precede the HUMAN submit route"


# ===========================================================================
# GAP-1 — submitPopulationVotes is an IN-SCOPE owning command
# ===========================================================================
def test_gap1_population_vote_is_an_in_scope_owning_command():
    """G4-Amendment-W3-03 GAP-1: the in-scope selector must contain
    ``submitPopulationVotes`` (same shape as the other owning ids) — never a
    dynamic inference or a wildcard."""
    def _recorded_for(command_id, lease_command):
        state = _state(consul="ai", third="ai")
        store = _store(state)
        seen = {}

        def _cont(txn, ok, failure):
            seen["command"] = store._delivery_required_command

        txn = store._begin_masked_seat_transition(
            command_id, lease_command=lease_command, payload={}, cont=_cont)
        assert txn is not None, (command_id, store.handoffFailureKind)
        return seen.get("command")

    assert _recorded_for("submitPopulationVotes",
                         "submit_population_votes") == "submitPopulationVotes"
    # two controls: an already in-scope id stays, an out-of-scope one stays ""
    assert _recorded_for("doSubmitSenateProposals",
                         "propose_many") == "doSubmitSenateProposals"
    assert _recorded_for("doCompletePlayer", "next_player") == ""
