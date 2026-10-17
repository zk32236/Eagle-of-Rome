"""EOR20261013-02 · D7–D12 / I1 (+ I1-R1 rework) — S1 delivery protocol + S2 readiness.

RED-first contract (new file; every pre-existing test is untouched):

  * ``02-sa-design/Rework-D7D12-Design-Delta_2026-10-17.md`` §2.1 (FC-712-01..05,
    S1) and §2.3 (FC-712-10..12, S2);
  * ``02-sa-design/Rework-D7D12_Implementation_and_Test_Overlay_2026-10-17.md``
    §2 rows AC-712-01..05 / 11..13 / 22 (prefix B).

Covered here:
  * B-01  a real senate vote package delivers the EXACT next obligation: the
    semantic next actor == ``DeliveryResult.next.actor`` == the actual pending
    receiver == the activation target == the real Core current player;
  * B-02  a real veto package produces the terminal continuation (canonical
    finalization) and a typed delivery envelope;
  * B-03  a missing receiver is a typed ``DELIVERY_MISSING_RECEIVER`` refusal —
    never the legacy ``None -> same-seat`` fallback;
  * B-04  a delivery whose actor disagrees with the real Core current player is a
    typed ``DELIVERY_MISMATCH`` refusal (no guessed activation target);
  * B-05  viewer-local ballot completion is NOT global readiness: the step stays
    ``senate_vote`` and the tally is marked ``PARTIAL`` (is_final=False);
  * B-06  GET remains pure on a partial tally (no finalization, no decider rerun);
  * B-07  all-controller readiness publishes ``settlement_pending`` (not
    ``results``), and the single canonical finalizer is the only terminal writer;
  * B-08  the Store consumes the typed delivery receiver (never a missing-receiver
    same-seat fallback) and keeps the AI-G terminal a masked failure.

I1-R1 additions (SA-I1-01..04):
  * envelope integrity: session_ref / turn / scope_id / core_revision / obligation
    id / disposition-type pairing / legacy contradiction / terminal four facts /
    ``RESOLVED + next=None + terminal=None`` — each an ISOLATED rejection;
  * restored evidence: finalize-before-ready ``PHASE_NOT_READY`` with zero effects,
    explicit ``settlement_pending`` observation, real committed-receipt retention,
    a SAME_HUMAN delivery that must REALLY activate, a REAL ``PlayerType.AI``
    terminal, continuation exactly-once counting, and unregistered CLI bytes;
  * state machine: ``results`` only from canonical four-fact finalization, and a
    readiness error is NEVER represented as ``settlement_pending``.

Provenance: constructed registered Hot-seat states (``register_hotseat_session``)
driven through the REAL Store/Adapter/owner APIs; the barrier provider is the
framework's own synchronous witness (MOCK_AUXILIARY for the frame witnesses).
``source_kind = CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY``.

WATERMARK: DA-Execute I1-R1 (S1+S2 rework); no commit / push / delete; no
pre-existing test edited.
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import senate_api
from src.api import session_access
from src.api import session_turn_service
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)


# ---------------------------------------------------------------------------
# Constructed registered Senate session (3 HUMAN controllers O/P/E)
# ---------------------------------------------------------------------------
def _senate_state(*, votes=None, current="p1", tribune_faction="equites",
                  decision_complete=True, proposal=True, register=True,
                  register_as=None, ai_players=(), enter_senate=True):
    """A registered 3-controller senate state in canonical O/P/E order.

    ``votes`` maps player_id -> bool for the single proposal. Missing entries are
    genuinely uncast ballots (never synthesized on a registered session).
    ``register_as`` allows the seat principal to differ from the Core current
    player (used by the real-AI terminal fixture: the scope is minted with an AI
    G while a HUMAN drives the owning command).
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ("mortality", "revenue", "forum", "population"):
        state.mark_phase_executed(phase)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    for fid, name in (("optimates", "Optimates"),
                      ("populares", "Populares"),
                      ("equites", "Equites")):
        state.add_faction(Faction(id=fid, name=name, treasury=50))

    consul = Figure(id=1, name="consul", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    state.get_faction("optimates").member_ids.append(1)

    tribune = Figure(id=3, name="tribune", faction_id=tribune_faction, age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    tribune.influence = 10
    state.add_member(tribune)
    state.get_faction(tribune_faction).member_ids.append(3)

    for fid, mid in (("optimates", 11), ("populares", 12), ("equites", 13)):
        senator = Figure(id=mid, name=f"senator-{fid}", faction_id=fid, age=50)
        senator.class_tier = ClassTier.NOBILE
        senator.influence = 50
        state.add_member(senator)
        state.get_faction(fid).member_ids.append(mid)

    state.add_player(Player(player_id="p1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="p2", faction_id="populares",
                            player_type=(PlayerType.AI if "p2" in ai_players
                                         else PlayerType.HUMAN)))
    state.add_player(Player(player_id="p3", faction_id="equites",
                            player_type=(PlayerType.AI if "p3" in ai_players
                                         else PlayerType.HUMAN)))
    state._turn_order = ["p1", "p2", "p3"]
    state.set_current_player(current)
    state.senate_proposal_decision_complete = bool(decision_complete)

    proposal_id = None
    if proposal:
        proposal_id = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        for pid, value in (votes or {}).items():
            state.record_senate_vote(pid, proposal_id, bool(value))
    if register:
        session_access.register_hotseat_session(state, register_as or current, epoch=0)
        if enter_senate:
            _enter_senate(state)
    return state, proposal_id


def _enter_senate(state):
    """Enter the senate phase through the REAL committed-receipt route.

    I1a-R3 §A: the trusted phase is P1 (``SessionTurnBook.entries`` last entry),
    so a test fixture that needs a deliverable senate state must enter it the way
    production does (service-issued committed receipt -> ``enter_phase``).
    Idempotent: an already-committed senate route is left untouched.
    """
    book = session_turn_service._book(state)
    scope = book.scopes.get("senate")
    if scope is not None and book.entries \
            and book.entries[-1].get("phase") == "senate" \
            and book.entries[-1].get("scope_id") == scope.scope_id:
        return state
    receipt = session_turn_service.issue_committed_phase_entry_receipt(
        state, command_id="advance_population_phase", phase="senate")
    result = session_turn_service.enter_phase(state, receipt)
    assert result.get("success") is True, result
    return state


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    def __init__(self):
        self.calls = []
        self.pendings = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route)); return True


def _active_store(state, viewer, senate_view=None):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness()
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = viewer
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = dict(senate_view or {})
    return store, witness


def _view(state, viewer):
    """The REAL guarded phase read with the service-presented caller context."""
    return senate_api.get_senate_view(
        state, viewer,
        caller_context=session_access.current_caller_context(state))


def _delivery(feedback):
    data = (feedback or {}).get("data") if isinstance(feedback, dict) else None
    return (data or {}).get("delivery") if isinstance(data, dict) else None


def _genuine_command_ref(state, actor="p1", phase="senate", command="unit"):
    """An ENGINE-issued accepted-command reference (I1-R2 column Q).

    ``issue_owner_receipt`` is the existing owner-receipt facility: the returned
    ``fact_ref`` is registered as a committed fact in the SAME SessionTurnBook, so
    a delivery may name a REAL accepted command instead of an arbitrary string.
    """
    scope = session_turn_service.mint_scope(state, phase)
    receipt = session_turn_service.issue_owner_receipt(
        state, command, actor_player_id=actor,
        fact_ref=f"dispatch:{command}:{scope.scope_id}",
        scope_id=scope.scope_id, kind=session_turn_service.KIND_ACTION)
    return receipt["fact_ref"]


def _live_obligation(state, actor="p1", phase="senate"):
    snap = session_turn_service.obligations(state, phase)
    for obligation in snap.outstanding():
        if obligation.actor_player_id == actor:
            return obligation
    return None


def _base_delivery(state, actor="p1", viewer="p1", phase="senate",
                   outcome="CONTINUE"):
    """A complete envelope built by the REAL producer (positive control).

    I1-R2: carries the ENGINE-issued command reference + the LIVE outstanding
    obligation identity (columns Q/O) instead of the earlier synthetic strings.
    """
    delivery = session_turn_service.delivery_for_actor(
        state, phase, actor, outcome=outcome, viewer_id=viewer,
        command_receipt_ref=_genuine_command_ref(state, actor, phase))
    obligation = _live_obligation(state, actor, phase)
    if obligation is not None and isinstance(delivery.get("next"), dict):
        delivery["next"]["obligation_id"] = list(obligation.obligation_id)
        delivery["next"]["substep"] = obligation.substep
    return delivery


def _terminal_obligation(state, actor, scope_id):
    """The result-owner (terminal) identity used by a RESOLVED delivery."""
    book = session_turn_service._book(state)
    return list(book.oid("senate", "terminal", ("player", actor), scope_id))


def _validation(state, delivery, *, viewer="p1"):
    return session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=viewer)


def _finalization_envelope(state, actor, viewer):
    """A terminal envelope backed by a REAL finalization receipt/four facts."""
    scope_id = session_turn_service.current_scope_id(state, "senate") or ""
    fid = senate_api.senate_finalization_id(state)
    delivery = session_turn_service.delivery_for_actor(
        state, "senate", actor, outcome="RESOLVED", viewer_id=viewer,
        command_receipt_ref=_genuine_command_ref(state, actor),
        terminal={
            "status": "resolved",
            "phase": "senate",
            "scope_id": scope_id,
            "obligation_id": _terminal_obligation(state, actor, scope_id),
            "actor": actor,
            "controller": session_turn_service.controller_of(state, actor),
            "current_player_id": actor,
            "finalization_id": list(fid),
            "cursor_restored": True,
            "awaiting_player_id": actor,
        })
    if isinstance(delivery.get("next"), dict):
        delivery["next"]["obligation_id"] = _terminal_obligation(
            state, actor, scope_id)
        delivery["next"]["substep"] = "terminal"
    return delivery


# ===========================================================================
# AC-712-01 / 02 — a real vote package delivers the EXACT next obligation
# ===========================================================================
def test_d7d12_s1_vote_delivers_exact_next_obligation():
    state, proposal_id = _senate_state(votes={}, current="p1")
    store, witness = _active_store(
        state, "p1", {"submitted_proposals": [{"id": proposal_id}]})

    feedback = store.doSubmitSenateVotes([proposal_id])

    committed = store._committed_receipt or {}
    delivery = _delivery(committed)
    assert feedback.get("success") is True, (feedback, witness.calls)
    assert isinstance(delivery, dict), ("vote must deliver DeliveryResultV1",
                                        committed)
    assert delivery.get("version") == 1, delivery
    assert delivery.get("outcome") == "CONTINUE", delivery
    nxt = delivery.get("next") or {}
    # semantic next obligation == actual receiver == Core current == activation target
    assert nxt.get("actor_player_id") == "p2", delivery
    assert nxt.get("controller") == "HUMAN", delivery
    assert nxt.get("disposition") == "NEXT_HUMAN", delivery
    assert state.get_current_player().player_id == "p2", "Core current receiver"
    assert store._pending_player_id == "p2", (
        "Store activation target must equal the delivered receiver", feedback)
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    # the partial ballot did NOT finalize (single canonical gate untouched)
    assert state.get_phase_result("senate") is None


# ===========================================================================
# AC-712-02 — veto produces the terminal continuation + typed delivery
# ===========================================================================
def test_d7d12_s1_veto_delivers_terminal_continuation():
    state, proposal_id = _senate_state(
        votes={"p1": True, "p2": True, "p3": True}, current="p3")
    store, witness = _active_store(
        state, "p3", {"veto_control_mode": "HUMAN",
                      "submitted_proposals": [{"id": proposal_id}]})

    store.doSubmitSenateVetoes([proposal_id])

    committed = store._committed_receipt or {}
    data = committed.get("data") or {}
    delivery = _delivery(committed)
    assert isinstance(delivery, dict), ("veto must deliver DeliveryResultV1",
                                        committed)
    assert delivery.get("outcome") == "RESOLVED", delivery
    terminal = delivery.get("terminal") or {}
    assert terminal.get("finalization_id"), delivery
    assert data.get("status") == "resolved", data
    # the ONE canonical finalizer really committed the terminal result
    assert state.get_phase_result("senate") is not None
    assert state.get_senate_finalization_receipt(
        state.get_senate_session() or "turn-1") is not None


# ===========================================================================
# AC-712-03 — missing receiver is a TYPED failure, never same-seat
# ===========================================================================
def test_d7d12_s1_missing_receiver_is_typed_failure():
    state, _ = _senate_state(votes={"p1": False, "p2": False, "p3": False},
                             current="p1")
    store, witness = _active_store(state, "p1")

    result = store._settle_after_senate_command(
        "txn-missing", {"success": True, "data": {
            "status": "awaiting_players", "awaiting_player_id": None}})

    assert result.get("success") is False, result
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert err.get("code") == "DELIVERY_MISSING_RECEIVER", result
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert witness.pendings == [], "no guessed handoff target"


# ===========================================================================
# AC-712-04 — delivery actor != real Core current is a typed mismatch
# ===========================================================================
def test_d7d12_s1_delivery_mismatch_fails_closed():
    state, proposal_id = _senate_state(votes={"p1": False}, current="p1")
    store, witness = _active_store(state, "p1")

    mismatched = {
        "version": 1, "outcome": "CONTINUE",
        "phase": "senate", "scope_id": "scope-x", "command_receipt_ref": "r1",
        "next": {"obligation_id": ["oid"], "phase": "senate",
                 "substep": f"vote:{proposal_id}", "actor_player_id": "p2",
                 "controller": "HUMAN", "disposition": "NEXT_HUMAN"},
        "terminal": None, "error": None,
    }
    # Core current is p1 while the delivery claims p2 -> fail closed, no activation.
    result = store._settle_after_senate_command(
        "txn-mismatch", {"success": True, "data": {
            "status": "awaiting_players", "delivery": mismatched}})

    assert result.get("success") is False, result
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert err.get("code") in ("DELIVERY_MISMATCH", "DELIVERY_INVALID"), result
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert witness.pendings == []


# ===========================================================================
# AC-712-11 — viewer-local completion is NOT global results
# ===========================================================================
def test_d7d12_s2_first_voter_complete_is_not_global_results():
    state, proposal_id = _senate_state(votes={}, current="p1")
    state.record_senate_vote("p1", proposal_id, False)
    view = _view(state, "p1")
    assert view.get("success") is True, view
    data = view["data"]

    # p1 covered every proposal ref locally, but p2/p3 ballots are outstanding.
    assert data.get("current_step") == "senate_vote", data.get("current_step")
    assert data.get("senate_settlement_pending") is False, data
    tally = data.get("vote_tally") or {}
    assert tally.get("status") == "PARTIAL", tally
    assert tally.get("is_final") is False, tally
    assert tally.get("covered") == 1 and tally.get("required") == 3, tally
    # no terminal tally row / no veto candidate / no fabricated finalization
    assert data.get("veto_candidate_ids") == [], data.get("veto_candidate_ids")
    assert data.get("vote_results") == [], data.get("vote_results")
    assert state.get_phase_result("senate") is None


# ===========================================================================
# AC-712-12 — GET is pure on a partial tally
# ===========================================================================
def test_d7d12_s2_partial_tally_get_has_no_side_effects(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem

    state, proposal_id = _senate_state(votes={}, current="p1")
    state.record_senate_vote("p1", proposal_id, False)
    calls = {"n": 0}
    real = PoliticalSystem.calculate_vote_result

    def counting(self, proposal, vote_decider=None):
        calls["n"] += 1
        return real(self, proposal, vote_decider)

    monkeypatch.setattr(PoliticalSystem, "calculate_vote_result", counting)
    first = _view(state, "p1")
    second = _view(state, "p1")
    assert first.get("success") and second.get("success")
    assert calls["n"] == 0, "partial tally preview must not run the tally producer"
    assert first["data"]["vote_tally"] == second["data"]["vote_tally"]
    assert state.get_phase_result("senate") is None
    assert state.get_senate_finalization_receipt(
        state.get_senate_session() or "turn-1") is None


# ===========================================================================
# AC-712-10 / 13 — all-controller readiness -> settlement_pending -> results
# ===========================================================================
def test_d7d12_s2_all_ballots_ready_is_settlement_pending_then_terminal():
    # p2/p3 already covered their refs; p1 is the LAST outstanding ballot.
    state, proposal_id = _senate_state(
        votes={"p2": False, "p3": False}, current="p1")
    store, witness = _active_store(
        state, "p1", {"submitted_proposals": [{"id": proposal_id}]})

    before = _view(state, "p1")
    data = before["data"]
    assert data.get("current_step") == "senate_vote", data.get("current_step")
    assert data.get("senate_settlement_pending") is False, data
    assert data.get("vote_tally", {}).get("status") == "PARTIAL", data.get("vote_tally")
    assert state.get_phase_result("senate") is None

    # The LAST ballot closes the all-controller gate; the ONE canonical
    # finalization follows from the owner continuation (no second writer).
    feedback = store.doSubmitSenateVotes([proposal_id])
    committed = store._committed_receipt or {}
    delivery = _delivery(committed)
    assert feedback.get("success") is True, (feedback, witness.calls)
    assert delivery.get("outcome") == "RESOLVED", delivery
    terminal = delivery.get("terminal") or {}
    assert terminal.get("finalization_id"), delivery
    assert state.get_phase_result("senate") is not None

    after = _view(state, "p1")
    assert after["data"].get("current_step") == "results", after["data"]
    assert after["data"].get("senate_settlement_pending") is False


# ===========================================================================
# AC-712-05 / 22 — terminal ownership + no-replay failure routing
# (I1-R1: REAL PlayerType.AI result owner, real committed receipt retained)
# ===========================================================================
def test_d7d12_s1_ai_terminal_owner_is_masked_failure_not_same_seat():
    # The phase-entry G (the scope actor) is a REAL AI player while a HUMAN
    # principal drives the owning command: the terminal result owner is AI.
    state, _ = _senate_state(
        proposal=False, decision_complete=False, current="p2", register_as="p1",
        ai_players=("p2",))
    session_turn_service.mint_scope(state, "senate")   # scope.actor = p2 (AI)
    state.set_current_player("p1")
    store, witness = _active_store(state, "p1", {"viewer_has_consul": True})

    feedback = store.doSubmitSenateProposals([])

    committed = store._committed_receipt or {}
    data = committed.get("data") or {}
    delivery = _delivery(committed)
    assert state.get_player("p2").player_type is PlayerType.AI
    assert session_turn_service.controller_of(state, "p2") == "AI"
    assert data.get("status") == "resolved", (data, feedback)
    assert data.get("controller") == "AI", data
    assert data.get("actor") == "p2", data
    assert data.get("awaiting_player_id") is None, data
    assert isinstance(delivery, dict), delivery
    assert (delivery.get("terminal") or {}).get("controller") == "AI", delivery
    # the terminal really committed the canonical facts
    assert state.get_phase_result("senate") is not None
    assert state.get_senate_finalization_receipt(
        state.get_senate_session() or "turn-1") is not None
    # an AI owner is never an ACTIVE H seat / never a guessed same-seat
    assert feedback.get("success") is False, feedback
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert witness.pendings == [], "an AI owner never becomes an ACTIVE H seat"
    assert store._pending_player_id in (None, ""), store._pending_player_id
    assert store.seatEpoch == 0, store.seatEpoch
    # the committed receipt is RETAINED (real, non-None) after the failure
    assert store._committed_receipt is committed
    assert isinstance(store._committed_receipt, dict)


def test_d7d12_s1_same_human_delivery_requires_real_activation():
    state, proposal_id = _senate_state(votes={}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    store, witness = _active_store(state, "p1", {"submitted_proposals": [{"id": proposal_id}]})

    txn = store._begin_masked_seat_transition("unit-same-seat")
    assert txn is not None, "a real masked transaction must exist"
    delivery = _base_delivery(state, actor="p1", viewer="p1")
    assert (delivery.get("next") or {}).get("disposition") == "SAME_HUMAN", delivery
    assert _validation(state, delivery, viewer="p1")["ok"] is True, delivery

    result = store._settle_after_senate_command(
        txn["txn_id"], {"success": True, "data": {
            "status": "awaiting_players", "delivery": delivery}})

    # SAME_HUMAN is an AFFIRMATIVE recovery that must REALLY activate the seat.
    assert result.get("success") is True, result
    assert (result.get("data") or {}).get("activated") is True, result
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store.seatEpoch == txn["seat_epoch"], (store.seatEpoch, txn)
    assert store._seat_txn is None, "the activation transaction was consumed"
    assert store._viewer_id == "p1"
    assert ("unmask", txn["txn_id"]) in witness.calls, witness.calls
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert not err, result


# ===========================================================================
# SA-I1-01 — DeliveryResultV1 envelope integrity (isolated rejections)
# ===========================================================================
def test_d7d12_s1_delivery_rejects_wrong_session_ref():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    wrong = dict(base, session_ref="session-foreign")
    verdict = _validation(state, wrong)
    assert verdict["ok"] is False, wrong
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "identity", verdict

    missing = dict(base)
    missing.pop("session_ref")
    verdict = _validation(state, missing)
    assert verdict["ok"] is False, missing
    assert verdict["error"]["stage"] == "identity", verdict


def test_d7d12_s1_delivery_rejects_wrong_turn():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    wrong = dict(base, turn=int(base.get("turn") or 0) + 1)
    verdict = _validation(state, wrong)
    assert verdict["ok"] is False, wrong
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "identity", verdict


def test_d7d12_s1_delivery_rejects_wrong_scope():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    wrong = dict(base, scope_id="scope-foreign")
    verdict = _validation(state, wrong)
    assert verdict["ok"] is False, wrong
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "scope", verdict


def test_d7d12_s1_delivery_rejects_stale_revision():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    stale = dict(base, core_revision=int(base.get("core_revision") or 0) - 1)
    verdict = _validation(state, stale)
    assert verdict["ok"] is False, stale
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "revision", verdict


def test_d7d12_s1_delivery_rejects_fake_obligation():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    snap = session_turn_service.obligations(state, "senate")
    real = next(o for o in snap.outstanding() if o.actor_player_id == "p1")

    positive = dict(base)
    positive["next"] = dict(base["next"], obligation_id=list(real.obligation_id))
    assert _validation(state, positive)["ok"] is True, positive

    fake = dict(base)
    fake["next"] = dict(
        base["next"],
        obligation_id=["session-foreign", 1, "scope-foreign", "senate",
                       "vote:999", ["player", "p1"]])
    verdict = _validation(state, fake)
    assert verdict["ok"] is False, fake
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "obligation", verdict


def test_d7d12_s1_delivery_rejects_disposition_type_contradiction():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    # HUMAN receiver labelled AI_OWNER: the disposition/type pair contradicts.
    wrong = dict(base)
    wrong["next"] = dict(base["next"], disposition="AI_OWNER")
    verdict = _validation(state, wrong)
    assert verdict["ok"] is False, wrong
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "receiver", verdict


def test_d7d12_s1_delivery_rejects_legacy_contradiction():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    # A legacy receiver/controller field INSIDE the envelope contradicts the
    # primary next/terminal facts.
    embedded = dict(base, actor="p2")
    verdict = _validation(state, embedded)
    assert verdict["ok"] is False, embedded
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "legacy", verdict

    embedded = dict(base, controller="AI")
    verdict = _validation(state, embedded)
    assert verdict["ok"] is False, embedded
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "legacy", verdict

    embedded = dict(base, awaiting_player_id="p3")
    verdict = _validation(state, embedded)
    assert verdict["ok"] is False, embedded
    assert verdict["error"]["stage"] == "legacy", verdict

    # The legacy SIBLING envelope (command ``data``) must agree with the typed
    # delivery too: a contradictory controller is a typed refusal, not a silent
    # accepted seat transition.
    state2, proposal_id = _senate_state(votes={}, current="p1")
    store, witness = _active_store(
        state2, "p1", {"submitted_proposals": [{"id": proposal_id}]})
    ok = store.doSubmitSenateVotes([proposal_id])
    assert ok.get("success") is True, (ok, witness.calls)
    real_delivery = _delivery(store._committed_receipt)
    assert isinstance(real_delivery, dict), real_delivery
    result = store._settle_after_senate_command(
        "txn-legacy", {"success": True, "data": {
            "status": "awaiting_players", "controller": "AI",
            "delivery": real_delivery}})
    assert result.get("success") is False, result
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert err.get("code") == "DELIVERY_MISMATCH", result
    assert err.get("stage") == "legacy", result


def test_d7d12_s1_delivery_rejects_terminal_fact_mismatch():
    state, _ = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    finalized = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert finalized.get("success") is True, finalized

    terminal = _finalization_envelope(state, "p1", "p1")
    assert _validation(state, terminal)["ok"] is True, terminal

    wrong_receipt = json.loads(json.dumps(terminal))
    wrong_receipt["terminal"]["finalization_id"] = ["bad-session", "bad-senate", 2]
    verdict = _validation(state, wrong_receipt)
    assert verdict["ok"] is False, wrong_receipt
    assert verdict["error"]["code"] == "DELIVERY_MISMATCH", verdict
    assert verdict["error"]["stage"] == "finalization_id", verdict

    wrong_actor = json.loads(json.dumps(terminal))
    wrong_actor["terminal"]["actor"] = "p2"
    wrong_actor["terminal"]["current_player_id"] = "p2"
    verdict = _validation(state, wrong_actor)
    assert verdict["ok"] is False, wrong_actor
    assert verdict["error"]["stage"] in ("terminal", "core"), verdict

    no_receipt_id = json.loads(json.dumps(terminal))
    no_receipt_id["terminal"].pop("finalization_id")
    verdict = _validation(state, no_receipt_id)
    assert verdict["ok"] is False, no_receipt_id
    assert verdict["error"]["stage"] == "terminal", verdict


def test_d7d12_s1_delivery_rejects_resolved_without_next_or_terminal():
    state, _ = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state)
    assert _validation(state, base)["ok"] is True, base

    empty = dict(base, outcome="RESOLVED", next=None, terminal=None)
    verdict = _validation(state, empty)
    assert verdict["ok"] is False, empty
    assert verdict["error"]["code"] == "DELIVERY_INVALID", verdict
    assert verdict["error"]["stage"] == "terminal", verdict


# ===========================================================================
# SA-I1-02 — restored evidence assertions
# ===========================================================================
def test_d7d12_s2_finalizer_refuses_before_all_controller_ready():
    # p1 and p3 ballots are genuinely outstanding.
    state, proposal_id = _senate_state(votes={"p2": False}, current="p1")
    session_id = state.get_senate_session() or "turn-1"
    before = {
        "proposals": len(state.get_senate_proposals()),
        "votes": json.dumps(state.get_senate_votes_copy(), sort_keys=True, default=str),
        "decision_complete": bool(state.senate_proposal_decision_complete),
        "phase_result": state.get_phase_result("senate"),
        "receipt": state.get_senate_finalization_receipt(session_id),
    }

    refused = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))

    assert refused.get("success") is False, refused
    codes = [err.get("code") for err in (refused.get("errors") or [])
             if isinstance(err, dict)]
    assert "PHASE_NOT_READY" in codes, refused
    # ZERO side effects: no result, no receipt, no ballot/decision mutation.
    after = {
        "proposals": len(state.get_senate_proposals()),
        "votes": json.dumps(state.get_senate_votes_copy(), sort_keys=True, default=str),
        "decision_complete": bool(state.senate_proposal_decision_complete),
        "phase_result": state.get_phase_result("senate"),
        "receipt": state.get_senate_finalization_receipt(session_id),
    }
    assert after == before, (before, after)
    assert state.get_senate_finalization_receipt(session_id) is None
    assert state.get_phase_result("senate") is None


def test_d7d12_s2_settlement_pending_then_single_canonical_receipt():
    # All ballots in, zero passed candidates -> ready but NOT finalized.
    state, proposal_id = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_id = state.get_senate_session() or "turn-1"

    pending = _view(state, "p1")
    assert pending.get("success") is True, pending
    assert pending["data"].get("current_step") == "settlement_pending", pending["data"]
    assert pending["data"].get("senate_settlement_pending") is True, pending["data"]
    assert pending["data"].get("senate_finalization_error") is False, pending["data"]
    assert state.get_phase_result("senate") is None
    assert state.get_senate_finalization_receipt(session_id) is None

    first = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert first.get("success") is True, first
    receipt = state.get_senate_finalization_receipt(session_id)
    assert isinstance(receipt, dict), first
    assert first["data"].get("replayed") is not True, first["data"]

    results = _view(state, "p1")
    assert results["data"].get("current_step") == "results", results["data"]
    assert results["data"].get("senate_settlement_pending") is False, results["data"]

    second = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert second.get("success") is True, second
    assert second["data"].get("replayed") is True, second["data"]
    assert state.get_senate_finalization_receipt(session_id) == receipt


def test_d7d12_s1_delivery_failure_retains_committed_receipt():
    state, proposal_id = _senate_state(votes={}, current="p1")
    store, witness = _active_store(
        state, "p1", {"submitted_proposals": [{"id": proposal_id}]})

    ok = store.doSubmitSenateVotes([proposal_id])
    assert ok.get("success") is True, (ok, witness.calls)
    committed = store._committed_receipt
    real_delivery = _delivery(committed)
    assert isinstance(real_delivery, dict), committed

    bad = json.loads(json.dumps(real_delivery))
    bad["scope_id"] = "scope-foreign"
    result = store._settle_after_senate_command(
        "txn-retain", {"success": True, "data": {
            "status": "awaiting_players", "delivery": bad}})

    assert result.get("success") is False, result
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert err.get("code") == "DELIVERY_MISMATCH", result
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert store._committed_receipt is committed, "the committed receipt is retained"
    assert state.get_current_player().player_id == "p2", "no cursor rollback"


def test_d7d12_s1_continuation_runs_exactly_once(monkeypatch):
    real = session_turn_service.continue_after_command
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(session_turn_service, "continue_after_command", counting)

    # 1) vote batch
    state, proposal_id = _senate_state(votes={}, current="p1")
    store, _ = _active_store(
        state, "p1", {"submitted_proposals": [{"id": proposal_id}]})
    calls.clear()
    vote_fb = store.doSubmitSenateVotes([proposal_id])
    assert vote_fb.get("success") is True, vote_fb
    assert len(calls) == 1, ("vote batch continuation", len(calls))

    # 2) explicit EMPTY veto
    state, proposal_id = _senate_state(
        votes={"p1": True, "p2": True, "p3": True}, current="p3")
    store, _ = _active_store(
        state, "p3", {"veto_control_mode": "HUMAN",
                      "submitted_proposals": [{"id": proposal_id}]})
    calls.clear()
    empty_fb = store.doSubmitSenateVetoes([])
    assert (store._committed_receipt or {}).get("success") is True, empty_fb
    assert len(calls) == 1, ("empty veto continuation", len(calls))

    # 3) NON-EMPTY veto
    state, proposal_id = _senate_state(
        votes={"p1": True, "p2": True, "p3": True}, current="p3")
    store, _ = _active_store(
        state, "p3", {"veto_control_mode": "HUMAN",
                      "submitted_proposals": [{"id": proposal_id}]})
    calls.clear()
    veto_fb = store.doSubmitSenateVetoes([proposal_id])
    assert (store._committed_receipt or {}).get("success") is True, veto_fb
    assert len(calls) == 1, ("non-empty veto continuation", len(calls))

    # 4) proposal package (explicit empty decision)
    state, _ = _senate_state(
        proposal=False, decision_complete=False, current="p1")
    store, _ = _active_store(state, "p1", {"viewer_has_consul": True})
    calls.clear()
    prop_fb = store.doSubmitSenateProposals([])
    assert prop_fb.get("success") is True, prop_fb
    assert len(calls) == 1, ("proposal continuation", len(calls))


def test_d7d12_s1_unregistered_cli_bytes_unchanged(monkeypatch):
    """A never-registered CLI/legacy state keeps the historical response exactly.

    Independent comparison: the same call is repeated on an identical fresh state
    with the continuation BOOBY-TRAPPED, and the two serialized responses must be
    byte-identical (no new key, no extra continuation).
    """
    # vote
    state_a, pid_a = _senate_state(votes={}, current="p1", register=False)
    baseline_vote = senate_api.vote(state_a, "p1", [pid_a], [True])
    assert "delivery" not in (baseline_vote.get("data") or {}), baseline_vote
    assert "awaiting_player_id" not in (baseline_vote.get("data") or {}), baseline_vote

    def boom(*args, **kwargs):
        raise AssertionError("continuation must NOT run on a CLI/legacy state")

    monkeypatch.setattr(session_turn_service, "continue_after_command", boom)
    state_b, pid_b = _senate_state(votes={}, current="p1", register=False)
    trapped_vote = senate_api.vote(state_b, "p1", [pid_b], [True])
    assert json.dumps(baseline_vote, sort_keys=True, default=str) == \
        json.dumps(trapped_vote, sort_keys=True, default=str), (baseline_vote, trapped_vote)

    # veto (non-empty)
    state_c, pid_c = _senate_state(
        votes={"p1": True, "p2": True, "p3": True}, current="p3", register=False)
    baseline_veto = senate_api.veto(state_c, "p3", [pid_c])
    state_d, pid_d = _senate_state(
        votes={"p1": True, "p2": True, "p3": True}, current="p3", register=False)
    trapped_veto = senate_api.veto(state_d, "p3", [pid_d])
    assert json.dumps(baseline_veto, sort_keys=True, default=str) == \
        json.dumps(trapped_veto, sort_keys=True, default=str), (baseline_veto, trapped_veto)
    assert "delivery" not in (baseline_veto.get("data") or {}), baseline_veto


# ===========================================================================
# SA-I1-04 — the state machine only reports canonical results
# ===========================================================================
def test_d7d12_s2_results_require_canonical_finalization_receipt():
    # A success phase_result WITHOUT the canonical receipt/four facts is a
    # partial finalization: it must NEVER be projected as ``results``.
    state, proposal_id = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    state.record_phase_result("senate", {
        "success": True, "message": "partial", "data": {"frozen_war_decisions": []}})
    session_id = state.get_senate_session() or "turn-1"
    assert state.get_senate_finalization_receipt(session_id) is None

    view = _view(state, "p1")
    assert view.get("success") is True, view
    data = view["data"]
    assert data.get("current_step") != "results", data.get("current_step")
    assert data.get("current_step") == "settlement_pending", data.get("current_step")
    assert data.get("senate_finalization_error") is True, data
    assert data.get("vote_tally", {}).get("is_final") is False, data.get("vote_tally")

    # The canonical finalizer completes the missing facts -> real results.
    repaired = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert repaired.get("success") is True, repaired
    assert state.get_senate_finalization_receipt(session_id) is not None
    repaired_view = _view(state, "p1")
    assert repaired_view["data"].get("current_step") == "results", repaired_view["data"]
    assert repaired_view["data"].get("vote_tally", {}).get("is_final") is True


def test_d7d12_s2_readiness_error_is_not_settlement_pending(monkeypatch):
    state, proposal_id = _senate_state(
        votes={"p1": False, "p2": True, "p3": True}, current="p1")
    real = session_turn_service.senate_readiness

    def broken_readiness(state_arg):
        snapshot = dict(real(state_arg))
        snapshot.update({
            "ready": False,
            "errors": ("SENATE_VETO_RESOLVER_FAILED",),
        })
        return snapshot

    monkeypatch.setattr(session_turn_service, "senate_readiness", broken_readiness)
    view = _view(state, "p1")
    assert view.get("success") is True, view
    data = view["data"]

    assert data.get("current_step") == "readiness_error", data.get("current_step")
    assert data.get("senate_settlement_pending") is False, data
    assert data.get("readiness_errors"), data
    assert "SENATE_VETO_RESOLVER_FAILED" in data.get("readiness_errors"), data
    assert data.get("senate_finalization_error") is True, data
    assert data.get("vote_tally", {}).get("is_final") is False, data.get("vote_tally")
    assert state.get_phase_result("senate") is None


# ===========================================================================
# I1-R2 — Addendum §1.2/§1.3: 11 mandatory columns + 16-row shape table
# ===========================================================================
def _r2_state():
    """A registered senate state with a minted scope (p1/p3 outstanding)."""
    state, proposal_id = _senate_state(votes={"p2": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    return state, proposal_id


def _terminal_map(state, actor, *, controller=None, current_player_id="__actor__",
                  **overrides):
    scope_id = session_turn_service.current_scope_id(state, "senate") or ""
    fid = senate_api.senate_finalization_id(state)
    ctrl = controller or session_turn_service.controller_of(state, actor)
    terminal = {
        "status": "resolved",
        "phase": "senate",
        "scope_id": scope_id,
        "actor": actor,
        "controller": ctrl,
        "current_player_id": (actor if current_player_id == "__actor__"
                              else current_player_id),
        "finalization_id": list(fid),
        "obligation_id": _terminal_obligation(state, actor, scope_id),
        "cursor_restored": True,
        "awaiting_player_id": actor if ctrl == "HUMAN" else None,
    }
    terminal.update(overrides)
    return terminal


def _deny(verdict, code, stage):
    assert verdict["ok"] is False, verdict
    assert verdict["error"]["code"] == code, verdict
    assert verdict["error"]["stage"] == stage, verdict


# ---------------------------------------------------------------------------
# Rows 01–08: CONTINUE (C) / CONTINUE+SAME_HUMAN (S)
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_shape_rows_01_08_continue_and_same_human():
    state, _ = _r2_state()
    c = _base_delivery(state, actor="p1", viewer="p2")     # NEXT_HUMAN
    s = _base_delivery(state, actor="p1", viewer="p1")     # SAME_HUMAN
    terminal = _terminal_map(state, "p1")

    # Row 03 / 07 — the only ACCEPT rows here.
    assert _validation(state, c, viewer="p2")["ok"] is True, c
    assert _validation(state, s, viewer="p1")["ok"] is True, s

    # Row 01: C 0 0 -> MR/receiver
    _deny(_validation(state, dict(c, next=None), viewer="p2"),
          "DELIVERY_MISSING_RECEIVER", "receiver")
    # Row 02: C 0 1 -> DI/outcome_terminal
    _deny(_validation(state, dict(c, next=None, terminal=terminal), viewer="p2"),
          "DELIVERY_INVALID", "outcome_terminal")
    # Row 04: C 1 1 -> DI/outcome_terminal
    _deny(_validation(state, dict(c, terminal=terminal), viewer="p2"),
          "DELIVERY_INVALID", "outcome_terminal")
    # Row 05: bare SAME_HUMAN claim cannot supply next -> MR/receiver
    _deny(_validation(state, dict(s, next=None, disposition="SAME_HUMAN"),
                      viewer="p1"),
          "DELIVERY_MISSING_RECEIVER", "receiver")
    # Row 06: S 0 1 -> DI/outcome_terminal
    _deny(_validation(state, dict(s, next=None, terminal=terminal,
                                  disposition="SAME_HUMAN"), viewer="p1"),
          "DELIVERY_INVALID", "outcome_terminal")
    # Row 08: S 1 1 -> DI/outcome_terminal
    _deny(_validation(state, dict(s, terminal=terminal), viewer="p1"),
          "DELIVERY_INVALID", "outcome_terminal")


# ---------------------------------------------------------------------------
# Rows 09–12: RESOLVED (R) — terminal-only and terminal+next
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_shape_rows_09_12_resolved():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p1")

    # Row 09: R 0 0 -> DI/terminal (no interactive receiver)
    _deny(_validation(state, dict(base, outcome="RESOLVED", next=None,
                                  terminal=None)),
          "DELIVERY_INVALID", "terminal")
    # Row 11: R 1 0 -> DI/terminal EVEN IF a genuine next exists
    _deny(_validation(state, dict(base, outcome="RESOLVED", terminal=None)),
          "DELIVERY_INVALID", "terminal")

    # Row 10 without the canonical four facts -> DM/terminal or §2 receipt stage.
    terminal = _terminal_map(state, "p1")
    _deny(_validation(state, dict(base, outcome="RESOLVED", next=None,
                                  terminal=terminal)),
          "DELIVERY_MISMATCH", "receipt_missing")

    # Row 12: canonical terminal + exact result-owner obligation -> ACCEPT.
    finalized, _ = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_turn_service.mint_scope(finalized, "senate")
    assert senate_api.finalize_senate_if_ready(
        finalized, caller_context=session_access.current_caller_context(finalized)
    ).get("success") is True
    envelope = _finalization_envelope(finalized, "p1", "p1")
    assert _validation(finalized, envelope, viewer="p1")["ok"] is True, envelope

    # Row 10 HUMAN interactive terminal-only -> MR/receiver (frozen S1 needs next)
    _deny(_validation(finalized, dict(envelope, next=None), viewer="p1"),
          "DELIVERY_MISSING_RECEIVER", "receiver")


# ---------------------------------------------------------------------------
# Rows 13–16: FAILURE (F)
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_shape_rows_13_16_failure():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    failure = dict(base, outcome="FAILURE", next=None, terminal=None,
                   error={"code": "DELIVERY_INVALID", "stage": "continuation",
                          "committed": True, "retry_class": "NONE",
                          "detail": "typed"})
    terminal = _terminal_map(state, "p1")

    # Row 13: typed failure only, never activation.
    assert _validation(state, failure)["ok"] is True, failure
    # Row 14: F + success terminal -> DI/failure
    _deny(_validation(state, dict(failure, terminal=terminal)),
          "DELIVERY_INVALID", "failure")
    # Row 15: F + activation receiver -> DI/failure
    _deny(_validation(state, dict(failure, next=base["next"])),
          "DELIVERY_INVALID", "failure")
    # Row 16: F + both -> DI/failure
    _deny(_validation(state, dict(failure, next=base["next"],
                                  terminal=terminal)),
          "DELIVERY_INVALID", "failure")
    # E column: a FAILURE without a typed error is DI/failure.
    no_error = dict(failure, error=None)
    _deny(_validation(state, no_error), "DELIVERY_INVALID", "failure")


# ---------------------------------------------------------------------------
# Columns H (schema), I (identity), S (scope), V (revision)
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_schema_identity_scope_revision_columns():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    # H — malformed / unknown state is outside the 16 rows.
    _deny(_validation(state, dict(base, version=2)), "DELIVERY_INVALID", "schema")
    _deny(_validation(state, dict(base, outcome="MAYBE")), "DELIVERY_INVALID", "schema")
    _deny(_validation(state, dict(base, next=["not", "a", "mapping"])),
          "DELIVERY_INVALID", "schema")
    _deny(_validation(state, dict(base, terminal="no")), "DELIVERY_INVALID", "schema")
    _deny(_validation(state, dict(base, error={"code": "X"})),
          "DELIVERY_INVALID", "schema")

    # I — missing -> DI/identity, foreign -> DM/identity.
    missing = dict(base)
    missing.pop("session_ref")
    _deny(_validation(state, missing, viewer="p2"), "DELIVERY_INVALID", "identity")
    _deny(_validation(state, dict(base, session_ref="session-foreign"), viewer="p2"),
          "DELIVERY_MISMATCH", "identity")
    missing = dict(base)
    missing.pop("turn")
    _deny(_validation(state, missing, viewer="p2"), "DELIVERY_INVALID", "identity")
    _deny(_validation(state, dict(base, turn=99), viewer="p2"),
          "DELIVERY_MISMATCH", "identity")

    # S — envelope scope missing/foreign, and terminal scope foreign.
    missing = dict(base)
    missing.pop("scope_id")
    _deny(_validation(state, missing, viewer="p2"), "DELIVERY_INVALID", "scope")
    _deny(_validation(state, dict(base, scope_id="scope-foreign"), viewer="p2"),
          "DELIVERY_MISMATCH", "scope")

    # V — revision missing/stale.
    missing = dict(base)
    missing.pop("core_revision")
    _deny(_validation(state, missing, viewer="p2"), "DELIVERY_INVALID", "revision")
    _deny(_validation(state, dict(base, core_revision=int(base["core_revision"]) + 7),
                      viewer="p2"),
          "DELIVERY_MISMATCH", "revision")


def test_d7d12_i1r2_terminal_scope_column():
    finalized, _ = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_turn_service.mint_scope(finalized, "senate")
    assert senate_api.finalize_senate_if_ready(
        finalized, caller_context=session_access.current_caller_context(finalized)
    ).get("success") is True
    envelope = _finalization_envelope(finalized, "p1", "p1")
    assert _validation(finalized, envelope, viewer="p1")["ok"] is True, envelope

    foreign = json.loads(json.dumps(envelope))
    foreign["terminal"]["scope_id"] = "scope-foreign"
    _deny(_validation(finalized, foreign, viewer="p1"),
          "DELIVERY_MISMATCH", "scope")

    missing = json.loads(json.dumps(envelope))
    missing["terminal"].pop("scope_id")
    _deny(_validation(finalized, missing, viewer="p1"),
          "DELIVERY_INVALID", "scope")


# ---------------------------------------------------------------------------
# Column Q — command_receipt_ref must resolve to a genuine accepted command
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_command_receipt_column():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    missing = dict(base)
    missing.pop("command_receipt_ref")
    _deny(_validation(state, missing, viewer="p2"),
          "DELIVERY_INVALID", "command_receipt")
    _deny(_validation(state, dict(base, command_receipt_ref="arbitrary-string"),
                      viewer="p2"),
          "DELIVERY_MISMATCH", "command_receipt")
    # A real finalization receipt must NOT double as a command reference for an
    # unrelated command: only the issued command identity resolves.
    _deny(_validation(state, dict(base, command_receipt_ref="vote"), viewer="p2"),
          "DELIVERY_MISMATCH", "command_receipt")


# ---------------------------------------------------------------------------
# Column O — exact live obligation identity (incl. generation)
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_obligation_column():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    missing = json.loads(json.dumps(base))
    missing["next"].pop("obligation_id")
    _deny(_validation(state, missing, viewer="p2"),
          "DELIVERY_INVALID", "obligation")

    fake = json.loads(json.dumps(base))
    fake["next"]["obligation_id"] = ["session-foreign", 1, "scope-foreign",
                                      "senate", "vote:999", ["player", "p1"]]
    _deny(_validation(state, fake, viewer="p2"),
          "DELIVERY_MISMATCH", "obligation")

    old_generation = json.loads(json.dumps(base))
    old_generation["next"]["obligation_id"] = list(base["next"]["obligation_id"])
    old_generation["next"]["obligation_id"][1] = 0    # previous turn generation
    _deny(_validation(state, old_generation, viewer="p2"),
          "DELIVERY_MISMATCH", "obligation")


# ---------------------------------------------------------------------------
# Column A — real actor / raw PlayerType / disposition
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_receiver_column():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    empty = json.loads(json.dumps(base))
    empty["next"]["actor_player_id"] = ""
    _deny(_validation(state, empty, viewer="p2"),
          "DELIVERY_MISSING_RECEIVER", "receiver")

    unknown = json.loads(json.dumps(base))
    unknown["next"]["controller"] = "OBSERVER"
    _deny(_validation(state, unknown, viewer="p2"),
          "DELIVERY_INVALID", "receiver")

    wrong_type = json.loads(json.dumps(base))
    wrong_type["next"]["controller"] = "AI"
    wrong_type["next"]["disposition"] = "AI_OWNER"
    _deny(_validation(state, wrong_type, viewer="p2"),
          "DELIVERY_MISMATCH", "receiver")

    wrong_disposition = json.loads(json.dumps(base))
    wrong_disposition["next"]["disposition"] = "AI_OWNER"
    _deny(_validation(state, wrong_disposition, viewer="p2"),
          "DELIVERY_MISMATCH", "receiver")

    # SAME_HUMAN must target the current viewer.
    same = _base_delivery(state, actor="p1", viewer="p1")
    assert _validation(state, same, viewer="p1")["ok"] is True, same
    _deny(_validation(state, same, viewer="p2"),
          "DELIVERY_MISMATCH", "receiver")


# ---------------------------------------------------------------------------
# Column K — actual Core current / real G
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_core_column():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    # The REAL Core current player is p1; p3 holds a genuine outstanding
    # obligation while the delivery claims p3 as the receiver -> Core mismatch.
    obligation_p3 = _live_obligation(state, "p3")
    assert obligation_p3 is not None
    moved = json.loads(json.dumps(base))
    moved["next"]["actor_player_id"] = "p3"
    moved["next"]["disposition"] = "NEXT_HUMAN"
    moved["next"]["obligation_id"] = list(obligation_p3.obligation_id)
    _deny(_validation(state, moved, viewer="p2"), "DELIVERY_MISMATCH", "core")

    finalized, _ = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_turn_service.mint_scope(finalized, "senate")
    assert senate_api.finalize_senate_if_ready(
        finalized, caller_context=session_access.current_caller_context(finalized)
    ).get("success") is True
    envelope = _finalization_envelope(finalized, "p1", "p1")

    no_current = json.loads(json.dumps(envelope))
    no_current["terminal"].pop("current_player_id")
    _deny(_validation(finalized, no_current, viewer="p1"),
          "DELIVERY_INVALID", "core")

    wrong_current = json.loads(json.dumps(envelope))
    wrong_current["terminal"]["current_player_id"] = "p2"
    _deny(_validation(finalized, wrong_current, viewer="p1"),
          "DELIVERY_MISMATCH", "core")

    # A terminal-only envelope still runs the real Core/G comparison.
    g_wrong = json.loads(json.dumps(envelope))
    g_wrong["next"] = None
    g_wrong["terminal"]["actor"] = "p2"
    g_wrong["terminal"]["current_player_id"] = "p2"
    g_wrong["terminal"]["awaiting_player_id"] = "p2"
    canary = _validation(finalized, g_wrong, viewer="p1")
    assert canary["ok"] is False, canary
    assert canary["error"]["stage"] in ("core", "terminal", "receiver"), canary


# ---------------------------------------------------------------------------
# Column T — canonical terminal identity/facts (§2)
# ---------------------------------------------------------------------------
def _finalized_state():
    state, _ = _senate_state(
        votes={"p1": False, "p2": False, "p3": False}, current="p1")
    session_turn_service.mint_scope(state, "senate")
    assert senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state)
    ).get("success") is True
    return state


def test_d7d12_i1r2_terminal_column_receipt_stages():
    state = _finalized_state()
    envelope = _finalization_envelope(state, "p1", "p1")
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope
    session_id = senate_api.senate_finalization_id(state)[1]
    valid_body = state.get_senate_finalization_receipt(session_id)
    assert isinstance(valid_body, dict), valid_body

    missing_status = json.loads(json.dumps(envelope))
    missing_status["terminal"].pop("status")
    _deny(_validation(state, missing_status, viewer="p1"),
          "DELIVERY_INVALID", "terminal")

    wrong_fid = json.loads(json.dumps(envelope))
    wrong_fid["terminal"]["finalization_id"] = ["bad", "bad", 2]
    _deny(_validation(state, wrong_fid, viewer="p1"),
          "DELIVERY_MISMATCH", "finalization_id")

    false_facts = json.loads(json.dumps(envelope))
    false_facts["terminal"]["completion_facts"] = {
        "phase_result": True, "final_outcome_frozen": False,
        "pending_cleared": True, "receipt": True}
    _deny(_validation(state, false_facts, viewer="p1"),
          "DELIVERY_MISMATCH", "terminal")

    wrong_revision = json.loads(json.dumps(envelope))
    wrong_revision["terminal"]["core_revision"] = 999999
    _deny(_validation(state, wrong_revision, viewer="p1"),
          "DELIVERY_MISMATCH", "terminal")

    # WRONG receipt: a foreign body behind the genuine key is never "results".
    foreign = state.get_senate_finalization_receipt(session_id)
    original_senate_id = foreign["senate_session_id"]
    try:
        foreign["senate_session_id"] = "foreign-senate"
        _deny(_validation(state, envelope, viewer="p1"),
              "DELIVERY_MISMATCH", "receipt_wrong")
    finally:
        foreign["senate_session_id"] = original_senate_id
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope


def test_d7d12_i1r2_receipt_absent_claimed_terminal_is_denied():
    state, _ = _r2_state()
    # A genuine success phase_result WITHOUT any canonical receipt (ABSENT).
    state.record_phase_result("senate", {
        "success": True, "message": "partial",
        "data": {"frozen_war_decisions": []}})
    session_id = senate_api.senate_finalization_id(state)[1]
    assert state.get_senate_finalization_receipt(session_id) is None

    envelope = _base_delivery(state, actor="p1", viewer="p1")
    envelope["outcome"] = "RESOLVED"
    envelope["terminal"] = _terminal_map(state, "p1")
    envelope["next"]["obligation_id"] = _terminal_obligation(
        state, "p1", envelope["scope_id"])
    envelope["next"]["substep"] = "terminal"
    _deny(_validation(state, envelope, viewer="p1"),
          "DELIVERY_MISMATCH", "receipt_missing")
    # The ordinary GET is settlement_pending, never results.
    view = _view(state, "p1")
    assert view["data"].get("current_step") == "settlement_pending", view["data"]


def test_d7d12_i1r2_dangling_receipt_is_readiness_error():
    state = _finalized_state()
    session_id = senate_api.senate_finalization_id(state)[1]
    ledger = state._senate_finalization_ledger
    real_key = ledger["by_session"][session_id]
    ledger["by_session"][session_id] = ("ghost", session_id, 2)
    try:
        envelope = _finalization_envelope(state, "p1", "p1")
        _deny(_validation(state, envelope, viewer="p1"),
              "DELIVERY_MISMATCH", "receipt_wrong")
        view = _view(state, "p1")
        data = view["data"]
        assert data.get("current_step") == "readiness_error", data.get("current_step")
        assert data.get("senate_settlement_pending") is False, data
        assert data.get("readiness_errors"), data
        # A dangling claimed receipt is NOT treated as absence to rerun effects.
        replay = senate_api.finalize_senate_if_ready(
            state, caller_context=session_access.current_caller_context(state))
        assert replay.get("success") is False, replay
        codes = [(e or {}).get("code") for e in (replay.get("errors") or [])]
        assert "DELIVERY_MISMATCH" in codes, replay
        assert ledger["by_session"][session_id] == ("ghost", session_id, 2), \
            "the dangling claim must not be silently rewritten"
    finally:
        ledger["by_session"][session_id] = real_key


def test_d7d12_i1r2_content_fingerprint_mismatch_is_denied():
    state = _finalized_state()
    envelope = _finalization_envelope(state, "p1", "p1")
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    # Same revision/key/receipt hash, one changed frozen value -> content mismatch.
    stored = state._phase_results["senate"]
    original = stored["data"].get("senate_content_marker")
    stored["data"]["senate_content_marker"] = "changed-after-commit"
    try:
        _deny(_validation(state, envelope, viewer="p1"),
              "DELIVERY_MISMATCH", "content_fingerprint")
        view = _view(state, "p1")
        assert view["data"].get("current_step") == "readiness_error", view["data"]
    finally:
        if original is None:
            stored["data"].pop("senate_content_marker", None)
        else:
            stored["data"]["senate_content_marker"] = original


# ---------------------------------------------------------------------------
# Column L — legacy sibling/embedded agreement
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_legacy_column_including_terminal_only():
    state = _finalized_state()
    envelope = _finalization_envelope(state, "p1", "p1")
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    embedded_actor = dict(envelope, actor="p2")
    _deny(_validation(state, embedded_actor, viewer="p1"),
          "DELIVERY_MISMATCH", "legacy")
    embedded_controller = dict(envelope, controller="AI")
    _deny(_validation(state, embedded_controller, viewer="p1"),
          "DELIVERY_MISMATCH", "legacy")
    embedded_awaiting = dict(envelope, awaiting_player_id="p2")
    _deny(_validation(state, embedded_awaiting, viewer="p1"),
          "DELIVERY_MISMATCH", "legacy")

    # Terminal-only: legacy is STILL checked (no next-is-None shortcut).
    terminal_only = json.loads(json.dumps(envelope))
    terminal_only["next"] = None
    terminal_only["actor"] = "p2"
    _deny(_validation(state, terminal_only, viewer="p1"),
          "DELIVERY_MISMATCH", "legacy")


def test_d7d12_i1r2_ai_awaiting_nonempty_always_rejects():
    state, _ = _senate_state(proposal=False, decision_complete=False,
                             current="p2", register_as="p1",
                             ai_players=("p2",))
    session_turn_service.mint_scope(state, "senate")
    state.set_current_player("p1")
    store, witness = _active_store(state, "p1", {"viewer_has_consul": True})
    feedback = store.doSubmitSenateProposals([])
    committed = store._committed_receipt or {}
    delivery = _delivery(committed)
    assert isinstance(delivery, dict), (feedback, committed)
    assert state.get_player("p2").player_type is PlayerType.AI
    assert (delivery.get("terminal") or {}).get("controller") == "AI", delivery
    assert _validation(state, delivery, viewer="p1")["ok"] is True, delivery

    # A non-empty awaiting on a REAL AI owner must always reject (never skipped).
    bad = json.loads(json.dumps(delivery))
    bad["next"] = None
    bad["terminal"]["awaiting_player_id"] = "p1"
    verdict = _validation(state, bad, viewer="p1")
    assert verdict["ok"] is False, verdict
    assert verdict["error"]["stage"] in ("legacy", "terminal", "receiver"), verdict

    # Terminal-only AI transport ACCEPTS at the integrity layer (no activation).
    terminal_only = json.loads(json.dumps(delivery))
    terminal_only["next"] = None
    assert _validation(state, terminal_only, viewer="p1")["ok"] is True, terminal_only
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert witness.pendings == []


# ---------------------------------------------------------------------------
# §2.3 replay equality + GET purity
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_replay_equality_and_no_effects():
    state = _finalized_state()
    session_id = senate_api.senate_finalization_id(state)[1]
    receipt = json.loads(json.dumps(state.get_senate_finalization_receipt(session_id)))
    result_before = json.dumps(state.get_phase_result("senate"), sort_keys=True,
                               default=str)

    replay = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert replay.get("success") is True, replay
    assert replay["data"].get("replayed") is True, replay["data"]
    assert json.dumps(state.get_senate_finalization_receipt(session_id),
                      sort_keys=True, default=str) == json.dumps(
        receipt, sort_keys=True, default=str), "receipt identity must not change"
    assert json.dumps(state.get_phase_result("senate"), sort_keys=True,
                      default=str) == result_before, "business result delta=0"

    # Wrong receipt -> typed mismatch, NO effects, receipt body unchanged.
    stored = state.get_senate_finalization_receipt(session_id)
    original_fp = stored["content_fingerprint"]
    stored["content_fingerprint"] = "0" * 64
    try:
        bad = senate_api.finalize_senate_if_ready(
            state, caller_context=session_access.current_caller_context(state))
        assert bad.get("success") is False, bad
        codes = [(e or {}).get("code") for e in (bad.get("errors") or [])]
        assert "DELIVERY_MISMATCH" in codes, bad
        assert stored["content_fingerprint"] == "0" * 64, "no receipt overwrite"
        assert json.dumps(state.get_phase_result("senate"), sort_keys=True,
                          default=str) == result_before
    finally:
        stored["content_fingerprint"] = original_fp
    assert senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state)
    ).get("success") is True


def test_d7d12_i1r2_get_purity_in_pending_and_corrupt_states():
    state, _ = _r2_state()
    session_id = senate_api.senate_finalization_id(state)[1]
    before = {
        "receipts": json.dumps(state._senate_finalization_ledger, sort_keys=True,
                               default=str),
        "results": json.dumps(state._phase_results, sort_keys=True, default=str),
        "proposals": json.dumps(state.get_senate_proposals(), sort_keys=True,
                                default=str),
        "votes": json.dumps(state.get_senate_votes_copy(), sort_keys=True,
                            default=str),
    }
    for _ in range(3):
        assert _view(state, "p1").get("success") is True
    after = {
        "receipts": json.dumps(state._senate_finalization_ledger, sort_keys=True,
                               default=str),
        "results": json.dumps(state._phase_results, sort_keys=True, default=str),
        "proposals": json.dumps(state.get_senate_proposals(), sort_keys=True,
                                default=str),
        "votes": json.dumps(state.get_senate_votes_copy(), sort_keys=True,
                            default=str),
    }
    assert after == before, "GET must not mint/write/backfill"
    assert state.get_senate_finalization_receipt(session_id) is None


# ---------------------------------------------------------------------------
# §3 Priority C — unregistered CLI four routes (structure equality)
# ---------------------------------------------------------------------------
def test_d7d12_i1r2_unregistered_cli_four_routes_unchanged(monkeypatch):
    """No pre-I1 byte snapshot is available -> Priority C compensation.

    ``HISTORICAL_CLI_BYTES_UNVERIFIABLE``: this proves the unregistered route's
    response STRUCTURE is unchanged in-process (and that no continuation runs),
    never that the bytes equal a historical build.
    """
    def snapshot(response):
        """A STRUCTURE-only view: same keys/containers/types, no volatile values.

        Values (session/scope ids, package uuids) legitimately differ between two
        fresh states; Priority C compares response STRUCTURE, never history bytes.
        """
        def shape(value):
            if isinstance(value, dict):
                return {key: shape(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [shape(item) for item in value]
            return type(value).__name__
        return json.dumps(shape(response), sort_keys=True), shape(response)

    def boom(*args, **kwargs):
        raise AssertionError("continuation must NOT run on a CLI/legacy state")

    # 1) proposal (explicit empty package) — the legacy path runs its historical
    #    continuation, so structural equality is compared across two fresh states.
    state_a, _ = _senate_state(proposal=False, decision_complete=False,
                               current="p1", register=False)
    baseline = senate_api.propose_many(state_a, "p1", [])
    state_b, _ = _senate_state(proposal=False, decision_complete=False,
                               current="p1", register=False)
    repeat = senate_api.propose_many(state_b, "p1", [])
    assert snapshot(baseline) == snapshot(repeat), (baseline, repeat)
    # The legacy proposal route ALREADY carries the continuation envelope (N10-R
    # chain); it is a PRE-EXISTING shape, recorded rather than denied here. The
    # three guard-early-return routes below must NOT grow a delivery key.
    assert ("delivery" in (baseline.get("data") or {})) == \
        ("delivery" in (repeat.get("data") or {})), (baseline, repeat)

    # 2) vote
    state_c, pid_c = _senate_state(votes={}, current="p1", register=False)
    vote_base = senate_api.vote(state_c, "p1", [pid_c], [True])
    monkeypatch.setattr(session_turn_service, "continue_after_command", boom)
    state_d, pid_d = _senate_state(votes={}, current="p1", register=False)
    vote_trapped = senate_api.vote(state_d, "p1", [pid_d], [True])
    assert snapshot(vote_base) == snapshot(vote_trapped)
    assert "delivery" not in (vote_base.get("data") or {}), vote_base
    monkeypatch.undo()

    # 3) explicit EMPTY veto
    state_e, _ = _senate_state(votes={"p1": True, "p2": True, "p3": True},
                               current="p3", register=False)
    empty_base = senate_api.veto(state_e, "p3", [])
    monkeypatch.setattr(session_turn_service, "continue_after_command", boom)
    state_f, _ = _senate_state(votes={"p1": True, "p2": True, "p3": True},
                               current="p3", register=False)
    empty_trapped = senate_api.veto(state_f, "p3", [])
    assert snapshot(empty_base) == snapshot(empty_trapped)
    assert "delivery" not in (empty_base.get("data") or {}), empty_base
    monkeypatch.undo()

    # 4) NON-EMPTY veto
    state_g, pid_g = _senate_state(votes={"p1": True, "p2": True, "p3": True},
                                   current="p3", register=False)
    veto_base = senate_api.veto(state_g, "p3", [pid_g])
    monkeypatch.setattr(session_turn_service, "continue_after_command", boom)
    state_h, pid_h = _senate_state(votes={"p1": True, "p2": True, "p3": True},
                                   current="p3", register=False)
    veto_trapped = senate_api.veto(state_h, "p3", [pid_h])
    assert snapshot(veto_base) == snapshot(veto_trapped)
    assert "delivery" not in (veto_base.get("data") or {}), veto_base
    monkeypatch.undo()


# ===========================================================================
# I1a-R3 §A — trusted phase (P1 entries / P2 live scope / P3 committed receipt)
# ===========================================================================
def test_d7d12_i1r3_forged_unknown_phase_cannot_expand_the_non_senate_exemption():
    """The old payload-controlled exemption: an unknown ``next.phase`` + no
    ``scope_id`` + no obligation reached a non-Senate success. The trusted route
    is the ONLY exemption source, so this must be a typed phase denial."""
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    forged = json.loads(json.dumps(base))
    forged["outcome"] = "RESOLVED"
    forged["terminal"] = None
    forged.pop("scope_id")
    forged["next"]["phase"] = "principal_assembly"
    forged["next"].pop("obligation_id")
    forged["next"].pop("substep")
    verdict = _validation(state, forged, viewer="p2")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "phase"), verdict


def test_d7d12_i1r3_declared_phases_must_agree_with_the_trusted_route():
    state = _finalized_state()
    envelope = _finalization_envelope(state, "p1", "p1")
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    forged["terminal"]["phase"] = "population"
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "phase"), verdict


def test_d7d12_i1r3_missing_envelope_scope_is_denied():
    state, _ = _r2_state()
    base = _base_delivery(state, actor="p1", viewer="p2")
    assert _validation(state, base, viewer="p2")["ok"] is True, base

    missing = dict(base)
    missing.pop("scope_id")
    verdict = _validation(state, missing, viewer="p2")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_INVALID", "scope"), verdict


def test_d7d12_i1r3_minted_scope_without_committed_entry_is_denied():
    """A scope minted by a lazy producer is NOT a trusted phase entry."""
    state, _ = _senate_state(votes={"p2": False}, current="p1",
                             enter_senate=False)
    session_turn_service.mint_scope(state, "senate")
    base = _base_delivery(state, actor="p1", viewer="p2")
    verdict = _validation(state, base, viewer="p2")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_INVALID", "phase"), verdict


def test_d7d12_i1r3_resolved_claim_without_committed_entry_is_receipt_wrong():
    state, _ = _senate_state(votes={"p2": False}, current="p1",
                             proposal=False, decision_complete=True,
                             enter_senate=False)
    session_turn_service.mint_scope(state, "senate")
    envelope = _base_delivery(state, actor="p1", viewer="p1")
    envelope["outcome"] = "RESOLVED"
    envelope["next"]["substep"] = "terminal"
    envelope["terminal"] = _terminal_map(state, "p1")
    verdict = _validation(state, envelope, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "receipt_wrong"), verdict


def test_d7d12_i1r3_legacy_entry_on_a_registered_session_is_denied():
    state, _ = _senate_state(votes={"p2": False}, current="p1",
                             enter_senate=False)
    result = session_turn_service._enter_phase_legacy(
        state, {"committed": True, "receipt_id": "legacy-entry",
                "phase": "senate"})
    assert result.get("success") is True, result
    base = _base_delivery(state, actor="p1", viewer="p2")
    verdict = _validation(state, base, viewer="p2")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_INVALID", "phase"), verdict


# ===========================================================================
# I1a-R3 §B — original commit binding (turn / substep / scope generation /
# revision) and typed finalization identity / counts
# ===========================================================================
def _terminal_oid_envelope(state, actor="p1"):
    return _finalization_envelope(state, actor, actor)


def test_d7d12_i1r3_terminal_turn_binding_is_enforced():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    forged["terminal"]["obligation_id"][1] = int(forged["turn"]) + 1
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "obligation"), verdict


def test_d7d12_i1r3_terminal_substep_binding_is_enforced():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    forged["terminal"]["obligation_id"][4] = "vote:1"
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "obligation"), verdict


def test_d7d12_i1r3_terminal_scope_generation_binding_is_enforced():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    forged["terminal"]["obligation_id"][2] = "scope-old-generation"
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "scope"), verdict


def test_d7d12_i1r3_terminal_phase_slot_binding_is_enforced():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    forged["terminal"]["obligation_id"][3] = "population"
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "obligation"), verdict


def test_d7d12_i1r3_commit_revision_upper_bound_is_enforced():
    state = _finalized_state()
    book = session_turn_service._book(state)
    scope = book.scopes["senate"]
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = session_turn_service._Record(
        command_id="forged-commit",
        dispatch_key=("forged",),
        obligation_id=book.oid("senate", "vote:forged", ("player", "p1"),
                               scope.scope_id),
        authoritative_fact_ref="forged-commit",
        satisfied_kind="action",
        entry_revision=scope.entry_revision,
        satisfied_at_revision=book.revision_counter + 5)
    book.records.append(forged)
    try:
        verdict = _validation(state, envelope, viewer="p1")
    finally:
        book.records.remove(forged)
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "receipt_wrong"), verdict


def test_d7d12_i1r3_derived_commit_revision_matches_the_real_finalize_commit():
    """G4 obligation proof: at the REAL finalize entry the derived revision (the
    spec formula over the only write path, ``SessionTurnBook.write``) equals the
    ledger revision at commit, and finalize itself advances/writes nothing."""
    state, _ = _senate_state(votes={"p1": False, "p2": False, "p3": False},
                             current="p1")
    book = session_turn_service._book(state)
    scope = book.scopes["senate"]
    book.write(session_turn_service._Record(
        command_id="unit-owner-commit",
        dispatch_key=book.dk("senate", "vote:unit", "p1", 0),
        obligation_id=book.oid("senate", "vote:unit", ("player", "p1"),
                               scope.scope_id),
        authoritative_fact_ref="unit-owner-commit",
        satisfied_kind="action",
        entry_revision=scope.entry_revision))
    commit_revision = book.revision_counter
    records_before = [(rec.obligation_id, rec.satisfied_at_revision)
                      for rec in book.records]
    revision_before = book.revision_counter

    finalized = senate_api.finalize_senate_if_ready(
        state, caller_context=session_access.current_caller_context(state))
    assert finalized.get("success") is True, finalized
    assert book.revision_counter == revision_before, "finalize advances no ledger"
    assert [(rec.obligation_id, rec.satisfied_at_revision)
            for rec in book.records] == records_before, "finalize writes no record"

    derived = [rec.satisfied_at_revision for rec in book.records
               if len(rec.obligation_id) > 3
               and rec.obligation_id[2] == scope.scope_id
               and rec.obligation_id[3] == "senate"]
    derived_revision = max(derived) if derived else scope.entry_revision
    assert derived_revision == commit_revision == book.revision_counter, (
        derived_revision, commit_revision, book.revision_counter)


def test_d7d12_i1r3_finalization_id_component_types_are_enforced():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    fid = forged["terminal"]["finalization_id"]
    forged["terminal"]["finalization_id"] = [fid[0], fid[1], str(fid[2])]
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "finalization_id"), verdict


def test_d7d12_i1r3_finalization_id_boolean_protocol_is_denied():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    fid = forged["terminal"]["finalization_id"]
    forged["terminal"]["finalization_id"] = [fid[0], fid[1], True]
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "finalization_id"), verdict


def test_d7d12_i1r3_finalization_id_list_is_position_sensitive():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    forged = json.loads(json.dumps(envelope))
    parts = [str(part) for part in forged["terminal"]["finalization_id"]]
    forged["terminal"]["finalization_id_list"] = [
        parts[0], parts[1] + "-foreign", parts[2]]
    verdict = _validation(state, forged, viewer="p1")
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "finalization_id"), verdict


def test_d7d12_i1r3_receipt_body_list_must_match_the_key():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    session_id = senate_api.senate_finalization_id(state)[1]
    body = state.get_senate_finalization_receipt(session_id)
    original = list(body["finalization_id_list"])
    body["finalization_id_list"] = [
        original[0], original[1] + "-foreign", original[2]]
    try:
        verdict = _validation(state, envelope, viewer="p1")
    finally:
        body["finalization_id_list"] = original
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "finalization_id"), verdict


def test_d7d12_i1r3_receipt_counts_are_recomputed_from_the_frozen_data():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    session_id = senate_api.senate_finalization_id(state)[1]
    body = state.get_senate_finalization_receipt(session_id)
    original = body["governor_assignment_count"]
    body["governor_assignment_count"] = original + 1
    try:
        verdict = _validation(state, envelope, viewer="p1")
    finally:
        body["governor_assignment_count"] = original
    error = verdict.get("error") or {}
    assert (verdict.get("ok"), error.get("code"), error.get("stage")) == (
        False, "DELIVERY_MISMATCH", "counts"), verdict


def test_d7d12_i1r3_missing_count_claim_is_not_defaulted_to_zero():
    state = _finalized_state()
    envelope = _terminal_oid_envelope(state)
    assert _validation(state, envelope, viewer="p1")["ok"] is True, envelope

    session_id = senate_api.senate_finalization_id(state)[1]
    body = state.get_senate_finalization_receipt(session_id)
    original = body.pop("retained_effect_intent_count")
    try:
        verdict = _validation(state, envelope, viewer="p1")
    finally:
        body["retained_effect_intent_count"] = original
    assert verdict.get("ok") is True, verdict

