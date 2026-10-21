"""W3 (D8/D9/BL-D14-01/T11/T12) — delivery authority / phase-entry production chain.

RED-first carrier for AC-W3-01/02/03/05/06/08/09/12/13/16/17/18/19/20/21.
Every case enters through the REAL production Slot (``doAdvancePopulation`` /
``doSubmitSenateProposals``) or the real public API boundary
(``session_api.*`` / ``senate_api.*``); the seat machine, adapter, Core ledger and
frame witnesses are the production ones. Faults are injected only at a declared
data boundary (adapter feedback / provider frame / registry read).

NO existing test byte is modified; this file is new (G4 §4).
"""
import inspect
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
import PySide6.QtQuick  # noqa: F401  (Window -> QQuickWindow mapping)
from PySide6.QtCore import QObject, QPointF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtTest import QTest

from src.ui.gui.app import GuiApp
from src.ui.gui.localization import gui_localization

from src.api import senate_api, session_access, session_turn_service, session_api
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import ClassTier, Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.ui.gui.session_store import (
    FAIL_BEFORE_COMMIT,
    GuiSessionStore,
    SEAT_ACTIVATE,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

VIEWER = "player1"


# ---------------------------------------------------------------------------
# Real registered session at the population -> senate entry boundary
# ---------------------------------------------------------------------------
def _entry_state(*, consul_controller="ai", third=None, budget=True,
                 register=True):
    """Registered hot-seat: p1 optimates (HUMAN, viewer), p2 populares, p3 equites.

    consul figure 8 = populares (p2); tribune figure 9 = optimates (p1).
    ``consul_controller`` is the REAL ``player2`` PlayerType ("ai"|"human").
    """
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
        return fig

    _figure(8, "consul", "populares", "consul", ClassTier.NOBILE, 50)
    _figure(9, "tribune", "optimates", "tribune", ClassTier.PLEBEIAN, 30)
    _figure(10, "eques", "equites", None, ClassTier.EQUES, 30)
    _figure(11, "opt", "optimates", None, ClassTier.NOBILE, 40)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=(PlayerType.AI if consul_controller == "ai"
                                         else PlayerType.HUMAN)))
    if third is not None:
        state.add_player(Player(player_id="player3", faction_id="equites",
                                player_type=(PlayerType.HUMAN if third == "human"
                                             else PlayerType.AI)))
    order = ["player1", "player2"] + (["player3"] if third is not None else [])
    state._turn_order = order
    state.set_current_player(VIEWER)

    if budget:
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS, province_id=1, base_cost=100,
            current_turn=1)
        contract.status = ContractStatus.PENDING

    # The population phase is genuinely RESOLVED (real phase result), the mark is
    # NOT yet executed -> the advance API is at its real commit boundary.
    state.record_phase_result("population", {
        "success": True, "message": "Election resolved",
        "data": {"election_results": []},
    })
    if register:
        session_access.register_hotseat_session(state, VIEWER, epoch=0)
    return state


class _Witness:
    """Synchronous production witness (real Query/publish/unmask seam)."""

    def __init__(self, unmask=True):
        self.calls = []
        self.pendings = []
        self.unmask = unmask

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction))
        self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return self.unmask

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


def _store(state, viewer=VIEWER, witness=None):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = witness or _Witness()
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = viewer
    store._seat_lifecycle = SEAT_ACTIVE
    return store, witness


def _entry_delivery(store):
    """Run the REAL Slot once; return (owner feedback, entry_receipt, delivery).

    The Slot's own return value is the SEAT settlement; the OWNER command feedback
    (with its typed envelope) is the transaction's committed receipt.
    """
    store.doAdvancePopulation()
    owner = store._committed_receipt or {}
    data = owner.get("data") or {}
    return owner, data.get("entry_receipt"), data.get("delivery")


# ===========================================================================
# AC-W3-01 — phase-entry delivery by outcome domain
# ===========================================================================
def test_ac_w3_01_entry_delivers_valid_envelope():
    state = _entry_state()
    store, witness = _store(state)
    feedback, receipt, delivery = _entry_delivery(store)

    assert feedback["success"] is True, feedback
    assert isinstance(delivery, dict) and delivery.get("version") == 1
    assert delivery["outcome"] in ("CONTINUE", "RESOLVED")
    verdict = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)
    assert verdict["ok"] is True, verdict
    assert delivery.get("next"), "the entry must deliver its receiver"
    assert delivery["next"]["actor_player_id"]
    # The delivered receiver == the REAL Core current (K column read-back).
    assert state.get_current_player().player_id == delivery["next"]["actor_player_id"]


def test_ac_w3_01_rejection_is_typed_and_has_no_delivery():
    state = _entry_state()
    state.set_current_player("player2")          # viewer is not the active player
    store, _ = _store(state)
    before = state.is_phase_executed("population")
    feedback = store.doAdvancePopulation()
    assert feedback["success"] is False
    assert "delivery" not in (feedback.get("data") or {})
    assert state.is_phase_executed("population") == before


# ===========================================================================
# AC-W3-02 — entry receipt consumed exactly once -> new senate scope
# ===========================================================================
def test_ac_w3_02_entry_receipt_is_consumed_once_and_mints_new_scope():
    state = _entry_state()
    book = session_turn_service._book(state)
    assert "senate" not in book.scopes
    store, _ = _store(state)
    feedback, receipt, _ = _entry_delivery(store)

    assert feedback["success"] is True
    assert receipt and book.entries, "the entry must append its PhaseEntered record"
    last = book.entries[-1]
    assert last["phase"] == "senate"
    assert last["receipt_id"] == receipt["receipt_id"]
    assert book.scopes["senate"].scope_id == last["scope_id"]

    scopes_before = dict(book.scopes)
    again = session_turn_service.enter_phase(state, receipt)
    assert again["success"] is False
    assert again["reason"] == "DUPLICATE_RECEIPT"
    assert dict(book.scopes) == scopes_before


# ===========================================================================
# AC-W3-03 / AC-W3-12 / AC-W3-20 — AI consul proposal is driven at entry
# ===========================================================================
def test_ac_w3_03_ai_consul_proposal_is_driven_by_the_entry_continuation():
    state = _entry_state(consul_controller="ai")
    store, witness = _store(state)
    feedback, _, delivery = _entry_delivery(store)

    assert feedback["success"] is True, feedback
    assert state.get_senate_proposals(), "the AI proposal must really be published"
    assert state.senate_proposal_decision_complete or state.get_senate_proposals()
    snapshot = session_turn_service.obligations(state, "senate")
    prop = next(o for o in snapshot.obligations if o.substep == "proposal")
    assert prop.satisfied is True
    assert delivery and delivery.get("next")
    # AC-20: the AI target never produced a HUMAN pending/seat.
    assert witness.pendings == []
    assert store._pending_player_id == ""
    assert store.seatLifecycle == SEAT_ACTIVE
    # AC-12: the normal path never enters FAIL_AFTER_COMMIT and never retries.
    assert store.handoffFailureKind == ""


def test_ac_w3_12_normal_entry_has_zero_after_commit_failures():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    kinds = []
    original = store._fail_masked

    def _spy(kind, txn_id="", route="activation"):
        kinds.append(kind)
        return original(kind, txn_id, route)

    retries = []
    with patch.object(store, "_fail_masked", side_effect=_spy), \
            patch.object(store, "retryHandoff", side_effect=lambda: retries.append(1)):
        feedback, _, _ = _entry_delivery(store)

    assert feedback["success"] is True
    assert kinds == [], kinds
    assert retries == []


# ===========================================================================
# AC-W3-05 / AC-W3-06 — coverage layering + no premature results
# ===========================================================================
def test_ac_w3_05_coverage_is_ballot_layer_and_packet_layer_separate():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    feedback, _, _ = _entry_delivery(store)
    assert feedback["success"] is True

    proposals = state.get_senate_proposals()
    readiness = session_turn_service.senate_readiness(state)
    assert readiness["required"] == len(proposals) * 2
    assert readiness["covered"] < readiness["required"]
    assert readiness["all_ballots_ready"] is False

    # ONE accepted HUMAN packet boundary -> ONE continuation -> still partial.
    before_records = len(session_turn_service._book(state).records)
    for proposal in proposals:
        state.record_senate_vote(VIEWER, proposal["id"], True)
    cont = session_turn_service.continue_after_command(
        state, ai_executor=senate_api._senate_ai_executor)
    after = session_turn_service.senate_readiness(state)
    assert after["covered"] == after["required"]
    assert after["all_ballots_ready"] is True
    assert cont.status in ("next_human", "phase_ready", "resolved")
    assert len(session_turn_service._book(state).records) - before_records \
        <= len(proposals) + 1


def test_ac_w3_06_partial_coverage_never_presents_results():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    view = store._adapter.call(
        senate_api.get_senate_view, state, VIEWER)
    assert view["success"] is True
    data = view["data"]
    assert data["current_step"] != "results"
    assert data["vote_results"] == []
    assert data["vote_tally"]["status"] == "PARTIAL"

    fin = store._adapter.call(senate_api.finalize_senate_if_ready, state)
    assert fin["success"] is False
    assert fin["errors"][0]["code"] == "PHASE_NOT_READY"
    assert state.get_phase_result("senate") is None


# ===========================================================================
# AC-W3-08 — retry never reads the Core cursor as a target
# ===========================================================================
def test_ac_w3_08_retry_without_recorded_envelope_is_typed_stop():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    assert store.doAdvancePopulation()["success"] is True

    store._seat_lifecycle = SEAT_MASKED_FAILURE
    store._last_delivery = None
    store._delivery_required_command = "advancePopulation"
    current_before = state.get_current_player().player_id
    calls = []
    real_getter = state.get_current_player

    def _spy_getter():
        calls.append(1)
        return real_getter()

    with patch.object(state, "get_current_player", side_effect=_spy_getter):
        result = store.retryHandoff()

    assert result["accepted"] is False
    assert result["delivery_error"]["code"] in (
        "DELIVERY_MISSING_RECEIVER", "DELIVERY_MISMATCH")
    assert calls == [], "the retry must not read the Core cursor as a target"
    assert state.get_current_player().player_id == current_before
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


def test_ac_w3_08_retry_uses_the_recorded_envelope_target():
    state = _entry_state(consul_controller="ai")
    store, witness = _store(state, witness=_Witness(unmask=False))
    feedback = store.doAdvancePopulation()
    assert feedback["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store._last_delivery is not None
    recorded = store._last_delivery["delivery"]["next"]["actor_player_id"]

    witness.unmask = True
    retry = store.retryHandoff()
    assert retry["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    # the target came from the recorded envelope (SAME_HUMAN viewer), not Core order
    assert recorded == VIEWER


# ===========================================================================
# AC-W3-09 — legacy fields cannot change the seat
# ===========================================================================
def test_ac_w3_09_contradictory_legacy_is_rejected_by_the_validator():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    real = store._adapter.advance_population

    def _corrupt(viewer):
        feedback = real(viewer)
        if feedback.get("success"):
            feedback["data"]["awaiting_player_id"] = "player9"
        return feedback

    with patch.object(store._adapter, "advance_population", side_effect=_corrupt):
        feedback = store.doAdvancePopulation()

    assert feedback["success"] is False
    err = feedback["data"]["delivery_error"]
    assert err["code"] in ("DELIVERY_MISMATCH", "DELIVERY_INVALID")
    assert err["stage"] in ("legacy", "receiver")
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# ===========================================================================
# AC-W3-13 — repeated entry / replay idempotency
# ===========================================================================
def test_ac_w3_13_repeated_advance_is_guard_denied_without_second_effect():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    book = session_turn_service._book(state)
    scopes = len(book.scopes)
    proposals = len(state.get_senate_proposals())
    entries = len(book.entries)

    again = store.doAdvancePopulation()
    assert again["success"] is False
    assert "already executed" in (again.get("message") or "").lower()
    assert len(book.scopes) == scopes
    assert len(state.get_senate_proposals()) == proposals
    assert len(book.entries) == entries


# ===========================================================================
# AC-W3-16 — single issuer (static proof + deleted Store issuer)
# ===========================================================================
def test_ac_w3_16_store_no_longer_issues_or_binds_a_receiver():
    store = GuiSessionStore(_entry_state(register=False))
    assert not hasattr(store, "_receiver_delivery")
    retry_src = inspect.getsource(GuiSessionStore.retryHandoff)
    assert "get_current_player" not in retry_src
    flow_src = inspect.getsource(GuiSessionStore._masked_senate_owning_flow)
    # W-12 (GA-02) / A-W3-07 / INV-W3-05: the Store NEVER signs a phase binding.
    # The mid-session binding moved to the owning API entry (senate_api), so the
    # whole Store source must be free of the service binding facility.
    assert "bind_phase_for_delivery" not in flow_src
    store_src = inspect.getsource(GuiSessionStore)
    assert "bind_phase_for_delivery" not in store_src
    settle_src = inspect.getsource(GuiSessionStore._settle_after_senate_command)
    assert 'get("awaiting_player_id")' not in settle_src
    assert 'get("actor")' not in settle_src
    assert 'get("status")' not in settle_src
    assert 'get("controller")' not in settle_src


# ===========================================================================
# AC-W3-17 — registration read failure is typed (GUARD + PLANNED extension)
# ===========================================================================
def test_ac_w3_17_registration_read_failure_is_typed_and_writes_nothing():
    state = _entry_state()
    store, _ = _store(state)
    before = state.is_phase_executed("population")

    with patch.object(session_access, "is_hotseat_registered",
                      side_effect=RuntimeError("registry read failed")):
        view = store._adapter.call(senate_api.get_senate_view, state, VIEWER)
        fin = store._adapter.call(senate_api.finalize_senate_if_ready, state)
        adv = store._adapter.advance_population(VIEWER)

    for response in (view, fin, adv):
        assert response["success"] is False
        assert response["errors"][0]["code"] == "REGISTRATION_UNAVAILABLE"
    assert state.get_phase_result("senate") is None
    assert state.is_phase_executed("population") is False
    assert before is False


# ===========================================================================
# AC-W3-18 — capability key consumption (U5)
# ===========================================================================
def test_ac_w3_18_capability_is_the_dto_key_and_gates_human_submit():
    state = _entry_state(consul_controller="human")
    store, _ = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    assert store.requestTakeover()["accepted"] is True
    store._refresh_senate_view()
    assert store.canCreateSenateProposal == bool(
        store._senate_view.get("can_create_proposal"))

    # false capability on a REGISTERED seat -> refused, zero owning dispatch
    store._senate_view = dict(store._senate_view, can_create_proposal=False)
    calls = []
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=lambda *a, **k: calls.append(1) or {"success": False}):
        refused = store.doSubmitSenateProposals([])
    assert refused["success"] is False
    assert calls == [], "the capability gate must precede the HUMAN submit route"

    # true capability -> the REAL owning HUMAN submit route runs
    store._senate_view = dict(store._senate_view, can_create_proposal=True)
    accepted = store.doSubmitSenateProposals([])
    assert accepted["success"] is True, accepted


def test_ac_w3_18_missing_capability_key_is_refused():
    """B1 / AC-W3-18: a MISSING capability key is a refusal, never a fallback to
    the local ``viewer_has_consul`` obligation (A-W3-04: no local re-derivation)."""
    state = _entry_state(consul_controller="human")
    store, _ = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    assert store.requestTakeover()["accepted"] is True
    store._refresh_senate_view()
    view = dict(store._senate_view)
    assert view.get("viewer_has_consul") is True, view
    view.pop("can_create_proposal", None)
    store._senate_view = view

    calls = []
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=lambda *a, **k: calls.append(1) or {"success": True}):
        refused = store.doSubmitSenateProposals([])

    assert refused["success"] is False, refused
    assert refused.get("feedback_type") == "warning", refused
    assert calls == [], "a missing capability key must not reach the submit route"


# ===========================================================================
# AC-W3-08 (A3 supplement) — the Core cursor is never a retry target source
# ===========================================================================
def test_ac_w3_08_retry_never_uses_core_cursor_when_record_disagrees():
    """The recorded envelope names B; the Core cursor says A. The retry must
    re-validate the RECORD and refuse — it must never adopt the Core cursor."""
    state = _entry_state(consul_controller="ai")
    store, witness = _store(state, witness=_Witness(unmask=False))
    assert store.doAdvancePopulation()["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    recorded = store._last_delivery["delivery"]["next"]["actor_player_id"]
    assert recorded == VIEWER
    viewer_before = store.viewerPlayerId

    # The Core cursor now disagrees with the recorded receiver.
    state.set_current_player("player2")
    core_before = state.get_current_player().player_id

    retry = store.retryHandoff()

    assert retry["accepted"] is False, retry
    assert retry["delivery_error"]["code"] == "DELIVERY_MISMATCH", retry
    assert store.viewerPlayerId == viewer_before
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert state.get_current_player().player_id == core_before


# ===========================================================================
# AC-W3-19 — uncommitted rejection never masquerades as after_commit
# ===========================================================================
def test_ac_w3_19_precommit_rejection_with_frame_failure_stays_generic():
    state = _entry_state(consul_controller="ai")
    state._phase_results.pop("population", None)
    store, witness = _store(state, witness=_Witness(unmask=False))
    feedback = store.doAdvancePopulation()

    assert feedback["success"] is False
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT
    # The original pre-commit refusal stays byte-faithful ...
    assert feedback["message"] == "Population phase has not been resolved"
    # ... and the Store-private diagnostic is explicitly uncommitted.
    activation = store._activation_result or {}
    assert activation["data"]["delivery_error"]["committed"] is False
    assert witness.calls[-1][0] == "failure"
    assert witness.calls[-1][2] == FAIL_BEFORE_COMMIT
    assert state.is_phase_executed("population") is False


# ===========================================================================
# AC-W3-21 — never-registered CLI/legacy byte-for-byte
# ===========================================================================
def test_ac_w3_21_never_registered_response_is_byte_identical():
    state = _entry_state(register=False)
    response = session_api.advance_population_phase(state, VIEWER)
    assert response["success"] is True
    assert set(response["data"]) == {
        "phase_executed", "next_phase_id", "result", "entry_receipt"}
    assert "delivery" not in response["data"]
    assert "awaiting_player_id" not in response["data"]


# ===========================================================================
# F08 (SA G5#2 §4.2) — recorded-target retry POSITIVE control: the FOUR-way
# equality (activated target == public viewer == authority == recorded target)
# ===========================================================================
def test_ac_w3_08_retry_positive_control_lands_on_the_recorded_target():
    """F08: the W3 recorded-envelope retry positive control must assert the WHOLE
    equality, not only ``recorded == VIEWER`` + ACTIVE:

        actual activated target == public viewer == seat authority
                               == recorded envelope target

    The recorded target is the ONLY target source (the Core cursor is never read
    to guess it — AC-W3-08), and the TA-02a cross-seat pending assertion stays
    intact (it is exercised by the AC-W3-04 takeover case in this same suite).
    """
    state = _entry_state(consul_controller="ai")
    store, witness = _store(state, witness=_Witness(unmask=False))
    assert store.doAdvancePopulation()["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    recorded = store._last_delivery["delivery"]["next"]["actor_player_id"]
    epoch_before = store.seatEpoch

    witness.unmask = True
    retry = store.retryHandoff()
    assert retry["accepted"] is True, retry
    assert store.seatLifecycle == SEAT_ACTIVE

    activated = state.get_current_player().player_id
    public_viewer = store.viewerPlayerId
    record = session_access._record(state)
    authority = getattr(record, "principal_player_id", "")
    assert recorded == VIEWER
    assert activated == recorded, (activated, recorded)
    assert public_viewer == recorded, (public_viewer, recorded)
    assert authority == recorded, (authority, recorded)
    assert store.seatEpoch == epoch_before + 1


# ===========================================================================
# W-12 (GA-02) — the MID-SESSION phase binding is signed by the owning API
# entry, never by the Store (A-W3-07 / INV-W3-05)
# ===========================================================================
def _bind_call_sites(monkeypatch):
    """Record the IMMEDIATE caller of the service binding facility."""
    import traceback
    calls = []
    real = session_turn_service.bind_phase_for_delivery

    def _spy(state, phase):
        calls.append(traceback.extract_stack()[-2].filename)
        return real(state, phase)

    monkeypatch.setattr(session_turn_service, "bind_phase_for_delivery", _spy)
    return calls


def test_w12_store_never_binds_the_phase(monkeypatch):
    """A mid-session senate command (no journal yet) still gets its binding, but
    it is issued from ``senate_api`` — the Store contributes ZERO calls."""
    state = _entry_state(consul_controller="ai")
    state.mark_phase_executed("population")
    assert not session_turn_service._book(state).entries
    store, _ = _store(state)
    store._senate_view = {
        "phase_id": "senate", "viewer_player_id": VIEWER,
        "current_step": "proposal", "viewer_has_consul": True,
        "can_create_proposal": True,
    }
    calls = _bind_call_sites(monkeypatch)

    store.doSubmitSenateProposals([])

    store_calls = [c for c in calls if c.endswith("session_store.py")]
    api_calls = [c for c in calls if c.endswith("src/api/senate_api.py")]
    assert store_calls == [], calls
    assert len(api_calls) == 1, calls
    assert session_turn_service._book(state).scopes.get("senate") is not None


# ===========================================================================
# F03 — REAL frame evidence (G3-delta Amendment W3-02: three tiers)
#
#   (a) QUERY_ACK_REAL      : the ack is written back by the REAL QML overlay
#   (b) FRAME_WINDOW_REAL   : the transaction's FIRST gate is completed by a REAL
#                             QQuickWindow afterRendering + frameSwapped
#   (c) FRAME_BRIDGE_DRIVEN : the remaining gates are driven by a source that
#                             implements ONLY the same signal pair, feeding the
#                             UNMODIFIED HandoffFrameBridge
#
# Every gate is recorded as (txn_id, kind, ok, generation, tier); the tier is
# written by the test (never inferred) and FRAME_BRIDGE_DRIVEN is never labelled
# REAL. A synchronous True / QTimer / property-notify receipt is never used.
# ===========================================================================
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")

_REAL_WIN_QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    width: 240; height: 160
    visible: true
    color: "black"
    Rectangle { anchors.fill: parent; color: "red" }
}
"""

_KEEPALIVE = []


class _DrivenFrameSource(QObject):
    """A frame source that implements ONLY the SAME pair of signals the
    production handoff bridge consumes. It never touches the bridge (which stays
    byte-unchanged) and is never used for the REAL tier."""

    afterRendering = Signal()
    frameSwapped = Signal()

    def __init__(self):
        super().__init__()
        self.updates = 0
        self._exposed = True

    def requestUpdate(self):
        self.updates += 1

    def isExposed(self):
        return self._exposed

    def render(self):
        self.afterRendering.emit()
        self.frameSwapped.emit()


class _RootStub(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    def showHandoffBusy(self):
        self.calls.append("busy")

    def hideHandoff(self):
        self.calls.append("hide")

    def showHandoffPending(self, faction):
        self.calls.append(("pending", faction))

    def showHandoffFailure(self, kind, route=""):
        self.calls.append(("failure", kind, route))


class _RecordingGuiApp(GuiApp):
    """The REAL production provider, recording every gate it is asked for.

    It adds ONLY observation: the tier assignment is explicit test data (it is
    never derived from the callback), and every callback is forwarded verbatim to
    the production :class:`HandoffFrameBridge` receipt."""

    def __init__(self, state):
        super().__init__(state)
        self.gate_log = []
        self.tier = {"arm": "FRAME_BRIDGE_DRIVEN",
                     "publish": "FRAME_BRIDGE_DRIVEN",
                     "unmask": "FRAME_BRIDGE_DRIVEN"}

    def _begin_recorded(self, kind, txn_id, on_receipt):
        entry = {"txn": txn_id, "kind": kind, "tier": self.tier[kind],
                 "ok": None, "generation": None, "receipt": None}
        self.gate_log.append(entry)

        def _cb(t, k, ok):
            entry["ok"] = bool(ok)
            entry["receipt"] = (t, k)
            entry["generation"] = int(self._frame_bridge._generation)
            on_receipt(t, k, ok)

        return entry, _cb

    def arm_barrier_async(self, txn_id, on_receipt):
        entry, cb = self._begin_recorded("arm", txn_id, on_receipt)
        super().arm_barrier_async(txn_id, cb)
        entry["generation"] = entry["generation"] or int(
            self._frame_bridge._generation)

    def publish_under_mask_async(self, txn_id, on_receipt):
        entry, cb = self._begin_recorded("publish", txn_id, on_receipt)
        super().publish_under_mask_async(txn_id, cb)
        entry["generation"] = entry["generation"] or int(
            self._frame_bridge._generation)

    def request_unmask_async(self, txn_id, on_receipt):
        entry, cb = self._begin_recorded("unmask", txn_id, on_receipt)
        super().request_unmask_async(txn_id, cb)
        entry["generation"] = entry["generation"] or int(
            self._frame_bridge._generation)


class _Shell:
    def __init__(self, gui, store, engine, window, driven):
        self.gui = gui
        self.store = store
        self.engine = engine
        self.window = window
        self.driven = driven

    def gates(self, kind=None):
        return [g for g in self.gui.gate_log if kind is None or g["kind"] == kind]

    def complete_driven(self, count=1):
        for _ in range(count):
            self.driven.render()



def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _pump(rounds=6, wait=5):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        if wait:
            QTest.qWait(wait)


def _pump_until(predicate, *, rounds=120, win=None):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(10)
        if win is not None:
            try:
                win.requestUpdate()
            except Exception:  # pragma: no cover - defensive
                pass
        if predicate():
            return True
    return bool(predicate())


def _real_window():
    """A REAL QQuickWindow (a real QML scene). On the offscreen platform a
    window swaps ONE frame, so the REAL tier is bound to a freshly created
    window for exactly the one gate that must be real."""
    engine = QQmlApplicationEngine()
    engine.setOutputWarningsToStandardError(False)
    component = QQmlComponent(engine)
    component.setData(_REAL_WIN_QML.encode("utf-8"),
                      QUrl.fromLocalFile("/tmp/_w3_r5b_frame_window.qml"))
    assert not component.isError(), component.errorString()
    window = component.create()
    assert window is not None
    assert isinstance(window, QWindow)
    _KEEPALIVE.extend([engine, component, window])
    return window


def _shell_runtime(state, viewer=None):
    """The REAL production application + the REAL QML shell (GameShell / overlays).

    Exactly the wiring ``GuiApp.run`` performs, minus the blocking event loop:
    the real Store, the real GuiApp provider and the real QML receiver tree.
    """
    _app()
    gui = _RecordingGuiApp(state)
    store = gui.get_store()
    engine = QQmlApplicationEngine()
    engine.setOutputWarningsToStandardError(False)
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(
        os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("localization", gui_localization)
    engine.rootContext().setContextProperty("guiApp", gui)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    roots = engine.rootObjects()
    assert len(roots) == 1, roots
    window = roots[0]
    window.resize(QSize(1200, 800))
    window.show()
    _pump(6, 5)
    gui._engine = engine
    gui._root = window.findChild(QObject, "gameShell")
    assert gui._root is not None, "the real GameShell was not found"
    driven = _DrivenFrameSource()
    gui.bind_frame_window(driven)
    store.setHandoffBarrierProvider(gui)
    store.initialize(viewer or state.get_current_player().player_id)
    _pump(2, 2)
    _KEEPALIVE.extend([engine, theme, gui, store])
    return _Shell(gui, store, engine, window, driven)


def _takeover_driven(shell):
    assert shell.store.requestTakeover()["accepted"] is True
    shell.complete_driven(2)
    assert shell.store.seatLifecycle == SEAT_ACTIVE, shell.store.seatLifecycle


def _disable_query_ack(window):
    """Remove the REAL QML invalidation receiver by disabling the QML
    ``Connections`` elements that carry it (the ack write-back lives in QML, so a
    Python-side disconnect cannot reach it)."""
    found = []
    for obj in window.findChildren(QObject):
        if "Connections" in obj.metaObject().className():
            found.append(obj)
            obj.setProperty("enabled", False)
    return found


# ===========================================================================
# T1 — AC-W3-01 / AC-W3-11 shared seam: the cross-seat ENTRY transaction
# ===========================================================================
def test_ac_w3_01_real_frame_cross_seat_entry():
    """(a) the real QML overlay acks the invalidation; (b) the entry transaction's
    FIRST gate is completed by a REAL QQuickWindow; (c) nothing else claims REAL.
    """
    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui = shell.store, shell.gui
    _takeover_driven(shell)                     # startup takeover (driven gates)
    assert store._viewer_id == "player1"

    shell.gui.tier["arm"] = "FRAME_WINDOW_REAL"
    real = _real_window()
    gui.bind_frame_window(real)
    ack_before = store.queryInvalidationEpoch

    # --- the transaction under test (cross-seat entry) -------------------
    store.doAdvancePopulation()
    assert store._async_gate is not None, "the arm gate must suspend the txn"
    assert store._async_gate["kind"] == "arm"
    # no public projection may be visible while the FIRST gate is pending
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}

    arm = shell.gates("arm")[-1]
    assert _pump_until(lambda: arm["ok"] is not None, win=real), "no REAL frame"
    assert arm["ok"] is True, arm
    assert arm["tier"] == "FRAME_WINDOW_REAL", arm

    # (a) the REAL QML receiver wrote back the CURRENT invalidation epoch.
    assert store.queryInvalidationEpoch > ack_before
    assert store._query_invalidation_ack == store.queryInvalidationEpoch

    # cross-seat handoff: p2 is pending; NOTHING of p2 is published.
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store._pending_player_id == "player2", store._pending_player_id
    assert store.viewerPlayerId == ""
    delivery = (store._committed_receipt or {}).get("data", {}).get("delivery")
    assert delivery and delivery["next"]["actor_player_id"] == "player2", delivery
    assert delivery["outcome"] == "CONTINUE", delivery
    assert delivery["next"]["disposition"] == "NEXT_HUMAN", delivery


# ===========================================================================
def test_ac_w3_01_no_ack_never_publishes_the_cross_seat_entry():
    """(a) NEGATIVE control: the very same entry with the REAL QML ack receiver
    disabled must publish NOTHING — the frame alone is never a receipt."""
    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui = shell.store, shell.gui
    _takeover_driven(shell)

    # A REAL read with content: the clear obligation now exists.
    store.doGlobalQuery("figure_search")
    assert store._query_open or store._global_query_result, "the query must open"
    connections = _disable_query_ack(shell.window)
    assert connections, "the real QML ack receiver must be present"

    # the arm frame also comes from a real window, so the ONLY missing witness is
    # the receiver completion (the ack) — never the frame.
    shell.gui.tier["arm"] = "FRAME_WINDOW_REAL"
    real = _real_window()
    gui.bind_frame_window(real)
    store.doAdvancePopulation()
    arm = shell.gates("arm")[-1]
    assert _pump_until(lambda: arm["ok"] is not None, win=real), "no REAL frame"
    assert arm["ok"] is True, arm            # the frame DID arrive ...

    # ... and yet nothing may be published without the receiver completion.
    assert store._query_invalidation_ack != store.queryInvalidationEpoch
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT, store.handoffFailureKind
    assert store.viewerPlayerId == ""
    assert store._pending_player_id == ""
    assert store._committed_receipt is None
    assert state.is_phase_executed("population") is False


# ===========================================================================
# T2 — AC-W3-04 / AC-W3-18: the REAL overlay click and the submit gate
# ===========================================================================
def test_ac_w3_04_real_qml_takeover_and_submit():
    """A REAL QML 「接管」 click drives the production takeover; the FIRST gate of
    that transaction (publish-under-mask) is a REAL window receipt and the final
    reveal is driven by the unmodified bridge. The submit packet then passes the
    composite capability gate through the REAL owning route."""
    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    _takeover_driven(shell)                     # startup seat (driven gates)

    # entry -> cross-seat pending for the HUMAN consul (driven gates only)
    store.doAdvancePopulation()
    driven.render()
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store._pending_player_id == "player2"

    # REAL window for the FIRST gate of the takeover transaction; the final
    # reveal is rebound to the driven source INSIDE the seat transition (after the
    # publication receipt, before the unmask gate begins).
    shell.gui.tier["publish"] = "FRAME_WINDOW_REAL"
    real = _real_window()
    gui.bind_frame_window(real)
    rebound = {"done": False}

    def _rebind_for_reveal():
        if rebound["done"] or not store._reveal_pending:
            return
        if store.seatLifecycle != SEAT_ACTIVATE:
            return
        rebound["done"] = True
        gui.bind_frame_window(driven)

    store.seatLifecycleChanged.connect(_rebind_for_reveal)

    overlay = shell.window.findChild(QObject, "playerHandoffOverlay")
    assert overlay is not None, "the real handoff overlay must exist"
    button = overlay.findChild(QObject, "grHandoffStart")
    assert button is not None
    assert button.property("text") == "接管", button.property("text")
    point = button.mapToScene(QPointF(float(button.property("width")) / 2.0,
                                      float(button.property("height")) / 2.0))
    QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, point.toPoint())

    publish = shell.gates("publish")[-1]
    assert _pump_until(lambda: publish["ok"] is not None, win=real), "no REAL frame"
    assert publish["ok"] is True, publish
    assert publish["tier"] == "FRAME_WINDOW_REAL", publish
    # the public viewer stays neutral until the FINAL reveal receipt
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}

    unmask = shell.gates("unmask")[-1]
    assert unmask["tier"] == "FRAME_BRIDGE_DRIVEN", unmask
    driven.render()
    assert unmask["ok"] is True, unmask
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store._viewer_id == "player2"
    assert store.viewerPlayerId == "player2"

    # --- the submit packet: the composite capability gate, then the REAL route.
    store._refresh_senate_view()
    assert store.canCreateSenateProposal is True, store._senate_view
    calls = []
    real_submit = store._adapter.submit_senate_proposals
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=lambda *a, **k: calls.append((a, k))
                      or real_submit(*a, **k)):
        submitted = store.doSubmitSenateProposals([])
        # the owning dispatch runs ONLY after the arm receipt
        assert store._async_gate is not None, "the submit must suspend on its arm gate"
        assert store._async_gate["kind"] == "arm"
        driven.render()
    assert submitted.get("success") is True, submitted
    assert len(calls) == 1, calls
    # the submit transaction's gates are ALL driven (never REAL)
    shell.gui.tier["arm"] = "FRAME_BRIDGE_DRIVEN"
    for gate in shell.gates():
        if gate["tier"] == "FRAME_WINDOW_REAL":
            assert gate["kind"] == "publish", gate


# ===========================================================================
# T3 — AC-W3-12: the whole chain with frame events and ZERO failure counters
# ===========================================================================
def test_ac_w3_12_full_chain_zero_after_commit():
    """Every gate is a real/driven frame receipt; the failure counters stay at
    zero for the WHOLE chain (no after_commit, no retry), and every gate belongs
    to the live transaction (stale txn receipts are discarded)."""
    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    _takeover_driven(shell)

    failures, retries = [], []
    real_fail = store._fail_masked

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, route))
        return real_fail(kind, txn_id, route)

    with patch.object(store, "_fail_masked", side_effect=_fail_spy), \
            patch.object(store, "retryHandoff",
                         side_effect=lambda: retries.append(1)):
        # (1) the entry transaction: REAL window arm gate
        gui.tier["arm"] = "FRAME_WINDOW_REAL"
        real = _real_window()
        gui.bind_frame_window(real)
        store.doAdvancePopulation()
        arm = shell.gates("arm")[-1]
        assert _pump_until(lambda: arm["ok"] is not None, win=real)
        assert arm["ok"] is True and arm["tier"] == "FRAME_WINDOW_REAL", arm
        assert store.seatLifecycle == SEAT_MASKED_PENDING
        gui.tier["arm"] = "FRAME_BRIDGE_DRIVEN"   # every later gate is driven

        # a stale/foreign transaction receipt is DISCARDED by the Store
        before = store.seatLifecycle
        store._on_frame_receipt("txn-from-a-previous-generation", "publish", True)
        store._on_frame_receipt(arm["txn"], "unmask", True)
        assert store.seatLifecycle == before

        # (2) the takeover: driven publication + reveal
        gui.bind_frame_window(driven)
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        assert store.requestTakeover()["accepted"] is True
        driven.render()
        assert store.viewerPlayerId == ""     # still neutral before the reveal
        driven.render()
        assert store.seatLifecycle == SEAT_ACTIVE

        # (3) the consul's real proposal packet (arm gate driven)
        store._refresh_senate_view()
        assert store.canCreateSenateProposal is True
        submitted = store.doSubmitSenateProposals([
            {"type": "land",
             "params": {"act_type": "distribution", "amount_C": 10,
                        "percent": 0.1}}])
        if store._async_gate is not None:
            driven.render()
        assert submitted.get("success") is True, submitted

    assert failures == [], failures
    assert retries == [], retries

    gates = shell.gates()
    kinds = [g["kind"] for g in gates]
    assert kinds.count("arm") >= 2, kinds
    assert kinds.count("publish") >= 2, kinds
    assert all(g["ok"] is True for g in gates), gates
    # every receipt names its OWN (txn, kind) and the generation is monotonic
    assert all(g["receipt"] == (g["txn"], g["kind"]) for g in gates), gates
    gens = [g["generation"] for g in gates]
    assert gens == sorted(gens) and len(set(gens)) == len(gens), gens
    # exactly the FIRST gate of each transaction is allowed to be REAL
    real_gates = [g for g in gates if g["tier"] == "FRAME_WINDOW_REAL"]
    assert len(real_gates) == 1, real_gates
    assert real_gates[0]["kind"] == "arm", real_gates


# ===========================================================================
# F03 — W3 DOUBLE-TRANSACTION SKELETON PROBE (SA Disposition-W3-G5-3 §3)
#
#   ONE registered state / ONE book / ONE live Store: two DIFFERENT owning
#   transactions (T1 = population -> senate entry, T2 = senate proposal submit),
#   each getting its FIRST gate (arm) completed by ITS OWN freshly created REAL
#   QQuickWindow through the UNMODIFIED production HandoffFrameBridge; every
#   later gate is FRAME_BRIDGE_DRIVEN. While T2's arm gate is suspended the Store
#   is fed the previous transaction's receipt, a wrong kind, an old-generation id
#   and a refresh of the retired window: the live gate must hold and nothing may
#   be dispatched or published. No real-source signal is ever hand-emitted.
# ===========================================================================
def test_ac_w3_05_two_owning_txn_first_gate_probe():
    from PySide6.QtQuick import QQuickWindow

    trace = []
    flushed = {"done": False}

    def _emit(tag, **fields):
        trace.append(tag + " " + " ".join("%s=%r" % (k, v) for k, v in fields.items()))

    def _flush():
        if flushed["done"]:
            return
        flushed["done"] = True
        text = "\n".join(trace) + "\n"
        print(text)
        out = os.environ.get("EOR_W3_PROBE_TRACE", "")
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text)

    def _watch(win):
        counts = {"after": 0, "swap": 0}

        def _a():
            counts["after"] += 1

        def _s():
            counts["swap"] += 1

        win.afterRendering.connect(_a)
        win.frameSwapped.connect(_s)
        return counts

    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    book = session_turn_service._book(state)

    def _txn_gates(txn):
        return [g for g in gui.gate_log if g["txn"] == txn]

    applies, handles, failures, dispatches, submits = [], [], [], [], []
    real_apply = store._apply_staged
    real_handle = session_access.issue_fresh_handle
    real_dispatch = store._dispatch_owning
    real_submit = store._adapter.submit_senate_proposals

    def _gates_ok(kind):
        return any(g["kind"] == kind and g["ok"] is True for g in gui.gate_log)

    def _apply_spy(staged, target_id=None):
        applies.append({"viewer_before": store._viewer_id,
                        "public_viewer": store.viewerPlayerId,
                        "snapshot_empty": store._snapshot == {},
                        "publish_ok": _gates_ok("publish"),
                        "unmask_ok": _gates_ok("unmask")})
        return real_apply(staged, target_id=target_id)

    def _handle_spy(state_obj):
        handles.append({"viewer": store._viewer_id,
                        "unmask_ok": _gates_ok("unmask")})
        return real_handle(state_obj)

    def _fail_spy(*a, **k):
        failures.append((a, tuple(sorted(k.items()))))
        return GuiSessionStore._fail_masked(store, *a, **k)

    def _dispatch_spy(txn, command, fn, *args):
        dispatches.append({"txn": txn.get("txn_id"), "command": command})
        return real_dispatch(txn, command, fn, *args)

    def _submit_spy(*a, **k):
        submits.append(a)
        return real_submit(*a, **k)

    patchers = [
        patch.object(store, "_apply_staged", side_effect=_apply_spy),
        patch.object(session_access, "issue_fresh_handle", side_effect=_handle_spy),
        patch.object(store, "_fail_masked", side_effect=_fail_spy),
        patch.object(store, "_dispatch_owning", side_effect=_dispatch_spy),
        patch.object(store._adapter, "submit_senate_proposals",
                     side_effect=_submit_spy),
    ]
    for _p in patchers:
        _p.start()
    try:
        registered = session_access.is_hotseat_registered(state)
        _takeover_driven(shell)                 # CONTROL: startup takeover (driven)
        _emit("CONTROL startup_takeover", lifecycle=store.seatLifecycle,
              viewer=store._viewer_id, gate_count=len(gui.gate_log))

        # ---------------- T1: population -> senate entry (owning txn) --------
        w1 = _real_window()
        w1_sig = _watch(w1)
        assert isinstance(w1, QQuickWindow), w1
        assert gui._frame_bridge.has_live_gate() is False
        gui.tier["arm"] = "FRAME_WINDOW_REAL"
        gui.bind_frame_window(w1)
        w1_bind_gen = int(gui._frame_bridge._generation)
        dispatch_before_t1 = len(dispatches)

        entry = store.doAdvancePopulation()
        gate1 = dict(store._async_gate or {})
        t1 = str(gate1.get("txn_id") or "")
        g1_begin = int(gui._frame_bridge._generation)
        _emit("TXN1_BEGIN", txn=t1, command="advancePopulation",
              gate_kind=gate1.get("kind"), bind_generation=w1_bind_gen,
              generation_at_begin=g1_begin,
              source_id=id(w1), source_type=w1.metaObject().className(),
              dispatch_delta=len(dispatches) - dispatch_before_t1,
              return_pending=bool((entry.get("data") or {}).get("pending")))
        assert t1 and gate1.get("kind") == "arm", (t1, gate1)

        arm1 = _txn_gates(t1)[0]
        neutral_at_begin = (store.viewerPlayerId == "", store._snapshot == {},
                            store.seatLifecycle)
        assert _pump_until(lambda: arm1["ok"] is not None, win=w1), "T1 arm: no frame"
        ack1 = (store._query_invalidation_ack, store.queryInvalidationEpoch)
        _emit("GATE1_FIRST", txn=t1, kind=arm1["kind"], tier=arm1["tier"],
              ok=arm1["ok"], generation_recorded=arm1["generation"],
              generation_at_begin=g1_begin,
              after_signals=w1_sig["after"], swap_signals=w1_sig["swap"],
              receipt=arm1["receipt"], neutral_at_begin=neutral_at_begin,
              qml_ack=ack1)
        assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
        assert store._pending_player_id == "player2", store._pending_player_id

        # ---- T1 continuation: takeover (reuses the SAME owning txn id) -------
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        gui.bind_frame_window(driven)
        takeover = store.requestTakeover()
        t1b = str((store._seat_txn or {}).get("txn_id") or "")
        _emit("TXN1_TAKEOVER", accepted=takeover.get("accepted"), txn=t1b,
              reuses_owning_txn=bool(t1b == t1), lifecycle=store.seatLifecycle)
        assert takeover.get("accepted") is True, takeover
        driven.render()                          # publish-under-mask receipt
        assert store.viewerPlayerId == "", "public viewer before the reveal"
        # (c) an OLD gate receipt (previous kind of the SAME txn) while the
        #     final-reveal gate is live: it must be dropped, never resume it.
        live = dict(store._async_gate or {})
        old_kind_held = bool(live.get("txn_id") == t1 and live.get("kind") == "unmask")
        store._on_frame_receipt(t1, "publish", True)
        held_after_old_kind = bool((store._async_gate or {}).get("txn_id") == t1
                                   and (store._async_gate or {}).get("kind") == "unmask")
        _emit("NEGATIVE_CONTROL old_kind_receipt", live_gate=live.get("kind"),
              held_before=old_kind_held, held_after=held_after_old_kind)
        driven.render()                          # final-reveal receipt -> apply
        assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
        assert store._viewer_id == "player2", store._viewer_id

        # ---------------- T2: senate proposal submit (owning txn) ------------
        rebind = {"done": False}

        def _rebind_for_t2():
            if rebind["done"] or store._seat_lifecycle != SEAT_ACTIVATE:
                return
            if gui._frame_bridge.has_live_gate():
                return
            rebind["done"] = True
            gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
            gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
            gui.bind_frame_window(driven)

        store.seatLifecycleChanged.connect(_rebind_for_t2)
        store._refresh_senate_view()
        assert store.canCreateSenateProposal is True, store._senate_view
        proposals_before = sorted(int(p["id"]) for p in state.get_senate_proposals())
        scope_before_t2 = book.scopes["senate"].scope_id

        w2 = _real_window()
        w2_sig = _watch(w2)
        assert isinstance(w2, QQuickWindow), w2
        assert gui._frame_bridge.has_live_gate() is False
        gui.tier["arm"] = "FRAME_WINDOW_REAL"
        gui.bind_frame_window(w2)
        w2_bind_gen = int(gui._frame_bridge._generation)

        submitted = store.doSubmitSenateProposals([
            {"type": "land", "params": {"act_type": "distribution",
                                        "amount_C": 10, "percent": 0.1}},
            {"type": "land", "params": {"act_type": "distribution",
                                        "amount_C": 12, "percent": 0.2}},
        ])
        gate2 = dict(store._async_gate or {})
        t2 = str(gate2.get("txn_id") or "")
        g2_begin = int(gui._frame_bridge._generation)
        _emit("TXN2_BEGIN", txn=t2, command="doSubmitSenateProposals",
              gate_kind=gate2.get("kind"), bind_generation=w2_bind_gen,
              generation_at_begin=g2_begin, distinct_from_t1=bool(t2 and t2 != t1),
              source_id=id(w2), source_type=w2.metaObject().className(),
              return_pending=bool((submitted.get("data") or {}).get("pending")),
              scope=scope_before_t2)
        assert t2 and t2 != t1 and gate2.get("kind") == "arm", (t2, gate2)

        # ---------------- activity-gate negative control ---------------------
        nc_before = (store.seatLifecycle, store._viewer_id, store.viewerPlayerId,
                     store._snapshot == {}, len(dispatches), len(submits),
                     len(applies), len(handles))
        store._on_frame_receipt(t1, "arm", True)          # previous owning txn
        store._on_frame_receipt(t2, "publish", True)      # wrong kind
        store._on_frame_receipt(t2, "unmask", True)       # wrong kind
        store._on_frame_receipt("txn-from-an-old-generation", "arm", True)
        nc_gate = dict(store._async_gate or {})
        nc_held = bool(nc_gate.get("txn_id") == t2 and nc_gate.get("kind") == "arm")
        nc_after = (store.seatLifecycle, store._viewer_id, store.viewerPlayerId,
                    store._snapshot == {}, len(dispatches), len(submits),
                    len(applies), len(handles))
        nc_unchanged = bool(nc_after == nc_before)
        _emit("NEGATIVE_CONTROL injected_receipts", txn_mismatch_injected=t1,
              wrong_kind_injected=["publish", "unmask"], gate_held=nc_held,
              state_unchanged=nc_unchanged, state=nc_before)

        # The RETIRED real window (W1) is refreshed after T2's gate began. W1 and
        # W2 are served by the SAME event-loop turns offscreen, so the isolation
        # is evidenced by (i) the retired source really emitted, (ii) the bridge
        # is bound to exactly ONE window (W2) after the rebind, (iii) the live
        # gate was still T2/arm at every turn in which it was live, and (iv) the
        # ONLY receipts produced are the live (txn, kind) pairs.
        w2_before_old = (w2_sig["after"], w2_sig["swap"])
        old_before = (w1_sig["after"], w1_sig["swap"])
        gate_live_iters = 0
        completion = None
        for _i in range(12):
            try:
                w1.setProperty("color", "#1%02d1%02d1%02d" % (_i, _i, _i))
                w1.requestUpdate()
            except Exception:  # pragma: no cover - defensive
                pass
            _pump(2, 5)
            _g = store._async_gate
            if _g is not None and _g.get("txn_id") == t2 and _g.get("kind") == "arm":
                gate_live_iters += 1
            elif _g is None and completion is None:
                completion = {"iteration": _i,
                              "w1": (w1_sig["after"], w1_sig["swap"]),
                              "w2": (w2_sig["after"], w2_sig["swap"])}
        old_after = (w1_sig["after"], w1_sig["swap"])
        old_source_exercised = bool(old_after != old_before)
        bridge_bound_to_w2 = bool(gui._frame_bridge._window is w2)
        completed_from_w2 = bool(completion is None
                                 or completion["w2"] != w2_before_old)
        t1_arm_entries = [g for g in gui.gate_log
                          if g["txn"] == t1 and g["kind"] == "arm"]
        oldgen_entries = [g for g in gui.gate_log
                          if g["txn"] == "txn-from-an-old-generation"]
        no_foreign_receipt = bool(len(t1_arm_entries) == 1 and not oldgen_entries)
        isolation_ok = bool(old_source_exercised and bridge_bound_to_w2
                            and completed_from_w2 and no_foreign_receipt)
        _emit("NEGATIVE_CONTROL retired_window_refresh", signals_before=old_before,
              signals_after=old_after,
              verdict=("EXERCISED" if old_source_exercised
                       else "NEGATIVE_NOT_EXERCISED"),
              gate_live_iterations=gate_live_iters, completion=completion,
              bridge_bound_to_w2=bridge_bound_to_w2,
              completed_from_w2=completed_from_w2,
              no_foreign_receipt=no_foreign_receipt)

        # ---------------- T2 first gate: REAL window ------------------------
        arm2 = _txn_gates(t2)[0]
        assert arm2["kind"] == "arm", arm2
        assert _pump_until(lambda: arm2["ok"] is not None, win=w2), "T2 arm: no frame"
        ack2 = (store._query_invalidation_ack, store.queryInvalidationEpoch)
        _emit("GATE2_FIRST", txn=t2, kind=arm2["kind"], tier=arm2["tier"],
              ok=arm2["ok"], generation_recorded=arm2["generation"],
              generation_at_begin=g2_begin,
              after_signals=w2_sig["after"], swap_signals=w2_sig["swap"],
              receipt=arm2["receipt"], qml_ack=ack2)

        # ---------------- T2 settlement (same-seat publish/reveal if any) ----
        if store.seatLifecycle == SEAT_ACTIVATE:
            driven.render()                      # publication-under-mask
            driven.render()                      # final reveal -> apply
        _emit("TXN2_SETTLE", lifecycle=store.seatLifecycle,
              pending=store._pending_player_id, viewer=store._viewer_id,
              rebind=rebind["done"])

        created = ((store._committed_receipt or {}).get("data") or {}).get("created") or []
        created_ids = sorted(int(c["proposal_id"]) for c in created
                             if c.get("proposal_id") is not None)
        proposals_after = sorted(int(p["id"]) for p in state.get_senate_proposals())
        new_ids = [pid for pid in proposals_after if pid not in proposals_before]
        scope_after_t2 = book.scopes["senate"].scope_id

        t1_first, t2_first = _txn_gates(t1)[0], _txn_gates(t2)[0]
        real1 = bool(t1_first["kind"] == "arm"
                     and t1_first["tier"] == "FRAME_WINDOW_REAL"
                     and t1_first["ok"] is True
                     and t1_first["receipt"] == (t1, "arm")
                     and w1_sig["after"] >= 1 and w1_sig["swap"] >= 1
                     and t1_first["generation"] == g1_begin)
        real2 = bool(t2_first["kind"] == "arm"
                     and t2_first["tier"] == "FRAME_WINDOW_REAL"
                     and t2_first["ok"] is True
                     and t2_first["receipt"] == (t2, "arm")
                     and w2_sig["after"] >= 1 and w2_sig["swap"] >= 1
                     and t2_first["generation"] == g2_begin)
        ordering_ok = bool(applies and len(applies) == len(handles)
                           and all(a["publish_ok"] and a["unmask_ok"]
                                   and a["public_viewer"] == "" for a in applies)
                           and all(h["unmask_ok"] for h in handles))

        for g in gui.gate_log:
            _emit("GATE", txn=g["txn"], kind=g["kind"], tier=g["tier"],
                  ok=g["ok"], generation=g["generation"], receipt=g["receipt"])
        for a in applies:
            _emit("APPLY", **a)
        for h in handles:
            _emit("FRESH_HANDLE", **h)
        _emit("DISPATCH", calls=dispatches)
        _emit("FAILURES", failed_masks=failures)

        verdict = {
            "C1_same_registered_state": bool(registered is True
                                             and scope_before_t2
                                             and scope_before_t2 == scope_after_t2),
            "C2_two_distinct_owning_txn": bool(
                t1 and t2 and t1 != t2
                and [d["command"] for d in dispatches].count("advance_population_phase") == 1
                and [d["command"] for d in dispatches].count("propose_many") == 1),
            "C3_first_gate_real_T1": real1,
            "C4_first_gate_real_T2": real2,
            "C5_t2_accepted_two_proposals": bool(created_ids and len(created_ids) == 2
                                                 and new_ids == created_ids),
            "C6_activity_gate_negative_control": bool(nc_held and nc_unchanged
                                                      and old_kind_held
                                                      and held_after_old_kind),
            "C6b_retired_window_events": old_source_exercised,
            "C6c_retired_source_isolation": isolation_ok,
            "C7_ordering_single_apply": ordering_ok,
            "C8_qml_ack_real": bool(ack1[0] == ack1[1] and ack2[0] == ack2[1]),
            "C9_zero_failed_masks": bool(failures == []),
            "C10_takeover_reuses_t1_txn": bool(t1b == t1),
        }
        for key, value in verdict.items():
            _emit("PREDICATE", id=key, value=value)
        _emit("SUMMARY", t1=t1, t2=t2, t1_gates=len(_txn_gates(t1)),
              t2_gates=len(_txn_gates(t2)), created=created_ids,
              proposals=proposals_after, new_proposals=new_ids,
              applies=len(applies), handles=len(handles),
              lifecycle=store.seatLifecycle)
        _flush()

        assert all(verdict.values()), verdict
    finally:
        for _p in patchers:
            _p.stop()
        _flush()


# ===========================================================================
# C1 (SA Disposition-W3-G5-3 §2 C1 / AC-W3-19 §9.1) — F01
#
# (i)  the commit context (``commit_proven`` x ``stage`` x the ORIGINAL
#      feedback) is JOINT at EVERY ``_activate_seat`` exit -- early (core /
#      staging / freshness / activation_txn) and late (publish / unmask /
#      apply) -- never only patched in at the tail;
# (ii) a rejected command's public ``success/message/data/errors`` stay
#      byte-faithful (value, key presence, type); the recovery diagnostic is
#      carried PRIVATELY and never written into the rejected object.
#
# Every case runs the REAL Slot -> REAL masked owning flow -> REAL
# ``_masked_business_rejection`` -> REAL ``_activate_seat``. Faults exist ONLY
# at the declared data boundaries (adapter feedback / adapter read envelope /
# provider frame receipt); ``_activate_seat``, the settle path and the owner
# functions are never patched.
# ===========================================================================
_C1_FIELDS = ("success", "message", "data", "errors")


class _GateWitness:
    """Provider that BEGINS the real async gates and delivers a chosen receipt.

    It is a declared PROVIDER FRAME boundary: the Store's own gate machine
    (``_begin_frame_gate`` / ``_on_frame_receipt``) is unmodified; only the
    receipt value of the named gate is controlled.
    """

    def __init__(self, arm=True, publish=True, unmask=True):
        self.results = {"arm": arm, "publish": publish, "unmask": unmask}
        self.calls = []
        self.pendings = []

    def arm_barrier(self, txn):
        self.calls.append(("arm_sync", txn))
        return True

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction))
        self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask_sync", txn))
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True

    def _gate(self, kind, txn_id, on_receipt):
        self.calls.append((kind, txn_id))
        on_receipt(txn_id, kind, self.results[kind])

    def arm_barrier_async(self, txn_id, on_receipt):
        self._gate("arm", txn_id, on_receipt)

    def publish_under_mask_async(self, txn_id, on_receipt):
        self._gate("publish", txn_id, on_receipt)

    def request_unmask_async(self, txn_id, on_receipt):
        self._gate("unmask", txn_id, on_receipt)


def _c1_snapshot(feedback):
    """Deep snapshot of the FOUR public fields (value / key presence / type)."""
    import copy
    import json
    values = {k: feedback.get(k) for k in _C1_FIELDS}
    return {
        "present": {k: (k in feedback) for k in _C1_FIELDS},
        "types": {k: type(feedback[k]).__name__
                  for k in _C1_FIELDS if k in feedback},
        "json": json.dumps(values, sort_keys=True, default=str),
        "values": copy.deepcopy(values),
    }


def _c1_refusal(shape):
    """The three CONSTRUCTIBLE producer refusal shapes named by C1-C."""
    if shape == "data_none":
        return {"success": False, "message": "提案包校验未通过",
                "errors": [{"code": "PACKAGE_REJECTED",
                             "message": "提案包校验未通过"}],
                "data": None}
    if shape == "data_missing_key":
        return {"success": False, "message": "提案字段缺失",
                "errors": [{"code": "MISSING_FIELD", "field": "war_id"}],
                "data": {"hint": "check the war selection"}}
    if shape == "data_with_producer_diagnostic":
        return {"success": False, "message": "提案包已拒绝",
                "errors": [{"code": "PACKAGE_REJECTED"}],
                "data": {"status": "rejected",
                         "delivery_error": {"code": "PACKAGE_REJECTED",
                                            "stage": "validation",
                                            "committed": False}}}
    raise AssertionError("unknown refusal shape: %r" % (shape,))


def _c1_active_consul():
    """REAL registered ACTIVE seat whose viewer owns the consul proposal right
    (entry -> cross-seat pending p2 -> explicit takeover -> p2 ACTIVE)."""
    state = _entry_state(consul_controller="human")
    store, witness = _store(state)
    assert store.doAdvancePopulation()["success"] is True
    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    store._refresh_senate_view()
    assert store._senate_view.get("viewer_has_consul") is True, store._senate_view
    assert store.canCreateSenateProposal is True, store._senate_view
    return state, store


def _c1_submit(store, refusal=None, *, before_return=None, read_fault=False):
    """The REAL Slot with ONE declared boundary fault; records the refusal object
    EXACTLY as it was handed to the Store plus the fresh-handle / call counts."""
    captured = {"calls": 0, "handles": 0}
    real_submit = store._adapter.submit_senate_proposals
    real_handle = session_access.issue_fresh_handle

    def _submit_spy(*a, **k):
        captured["calls"] += 1
        obj = refusal if refusal is not None else real_submit(*a, **k)
        captured["refusal"] = _c1_snapshot(obj)
        if before_return is not None:
            before_return()
        return obj

    def _handle_spy(state_obj):
        captured["handles"] += 1
        return real_handle(state_obj)

    patchers = [
        patch.object(store._adapter, "submit_senate_proposals",
                     side_effect=_submit_spy),
        patch.object(session_access, "issue_fresh_handle",
                     side_effect=_handle_spy),
    ]
    if read_fault:
        patchers.append(patch.object(
            store._adapter, "read_envelope",
            side_effect=lambda *a, **k: {
                "success": False, "message": "DENIED", "data": None,
                "errors": [{"code": "DENIED"}]}))
    for _p in patchers:
        _p.start()
    try:
        result = store.doSubmitSenateProposals([
            {"type": "land", "params": {"act_type": "distribution",
                                        "amount_C": 10, "percent": 0.1}}])
    finally:
        for _p in patchers:
            _p.stop()
    captured.setdefault("refusal", None)
    return result, captured


def _c1_assert_false_exit(store, state, code, stage):
    """The one joint FALSE-branch contract, asserted identically per exit."""
    diag = store._w3_recovery_diagnostic
    assert isinstance(diag, dict), diag
    assert (diag.get("code"), diag.get("stage")) == (code, stage), diag
    assert diag.get("committed") is False, diag
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT, store.handoffFailureKind
    # zero recovery seal for a PROVEN non-commit
    assert session_access.has_failed_recoverable_mandate(state) is False
    # public projection stays neutral
    assert store.viewerPlayerId == "", store.viewerPlayerId
    assert store._snapshot == {}, store._snapshot


@pytest.mark.parametrize("shape", ["data_none", "data_missing_key",
                                   "data_with_producer_diagnostic"])
def test_ac_w3_19_refusal_four_fields_survive_a_failed_recovery(shape):
    """C1-C: the rejected object's four public fields are preserved byte for
    byte across a FAILED same-seat recovery, and the diagnostic is private."""
    state, store = _c1_active_consul()
    rev_before = session_access.core_business_revision(state)
    refusal = _c1_refusal(shape)

    result, captured = _c1_submit(store, refusal, read_fault=True)

    # C1-A provenance: the owning command is a PROVEN non-commit (zero Core
    # business revision advance) -> the whole recovery is commit_proven=False.
    assert session_access.core_business_revision(state) == rev_before
    assert captured["calls"] == 1, captured

    after = _c1_snapshot(result)
    before = captured["refusal"]
    assert after["present"] == before["present"], (after, before)
    assert after["types"] == before["types"], (after, before)
    assert after["json"] == before["json"], (after, before)
    # the producer's OWN diagnostic is never overwritten either
    assert after["values"]["data"] == before["values"]["data"], (after, before)

    _c1_assert_false_exit(store, state, "SEAT_PUBLICATION_FAILED", "staging")
    assert captured["handles"] == 0, captured


def test_ac_w3_19_core_mismatch_exit_is_jointly_classified():
    """C1-B early exit ``core``: a FALSE recovery branch is never after_commit."""
    state, store = _c1_active_consul()

    def _core_moves():
        # REAL Core read-back now disagrees with the recovery target (negative
        # witness only -- the Core is never a target source).
        state.set_current_player(VIEWER)

    result, captured = _c1_submit(store, _c1_refusal("data_missing_key"),
                                  before_return=_core_moves)
    assert result["success"] is False, result
    assert captured["calls"] == 1, captured
    _c1_assert_false_exit(store, state, "DELIVERY_MISMATCH", "core")
    assert captured["handles"] == 0, captured


def test_ac_w3_19_publish_frame_exit_is_jointly_classified():
    """C1-B late exit ``publish_frame`` under a REAL async gate receipt = False."""
    state, store = _c1_active_consul()
    witness = _GateWitness(publish=False)
    store.setHandoffBarrierProvider(witness)

    result, captured = _c1_submit(store, _c1_refusal("data_none"))
    assert result["success"] is False, result
    assert ("publish",) == tuple(c[0] for c in witness.calls if c[0] == "publish")
    _c1_assert_false_exit(store, state, "SEAT_PUBLICATION_FAILED", "publish_frame")
    assert captured["handles"] == 0, captured


def test_ac_w3_19_unmask_frame_exit_is_jointly_classified():
    """C1-B late exit ``unmask_frame`` under a REAL async gate receipt = False."""
    state, store = _c1_active_consul()
    witness = _GateWitness(unmask=False)
    store.setHandoffBarrierProvider(witness)

    result, captured = _c1_submit(store, _c1_refusal("data_none"))
    assert result["success"] is False, result
    _c1_assert_false_exit(store, state, "SEAT_PUBLICATION_FAILED", "unmask_frame")
    assert captured["handles"] == 0, captured


def test_ac_w3_19_activation_txn_guard_never_defaults_to_true():
    """C1-B: the ``activation_txn`` guard must not reuse the ``committed=True``
    default, and must not emit the post-commit copy for a FALSE context.

    GUARD_WITNESS: the guard is exercised directly (no-record transaction) --
    this is NOT claimed as an integrated reachability proof.
    """
    state, store = _c1_active_consul()
    store._seat_txn = None

    result = store._activate_seat("txn-guard-witness", VIEWER,
                                  commit_proven=False)
    assert result["success"] is False, result
    typed = (result.get("data") or {}).get("delivery_error") or {}
    assert typed.get("code") == "SEAT_PUBLICATION_FAILED", typed
    assert typed.get("stage") == "activation_txn", typed
    assert typed.get("committed") is False, typed
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT, store.handoffFailureKind
    assert session_access.has_failed_recoverable_mandate(state) is False


def test_ac_w3_19_unproven_dispatch_omits_the_committed_key():
    """C1-D negative guard: an UNPROVEN dispatch is neither true nor false."""
    state, store = _c1_active_consul()

    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=RuntimeError("provider exploded")):
        result = store.doSubmitSenateProposals([
            {"type": "land", "params": {"act_type": "distribution",
                                        "amount_C": 10, "percent": 0.1}}])
    typed = (result.get("data") or {}).get("delivery_error") or {}
    assert typed.get("code") == "COMMIT_STATUS_UNPROVEN", typed
    assert typed.get("stage") == "dispatch", typed
    assert "committed" not in typed, typed
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT
    assert session_access.has_failed_recoverable_mandate(state) is False


def test_ac_w3_19_every_activation_exit_shares_one_commit_classification():
    """Structural proof for the exits that cannot be driven without patching the
    product (``freshness`` is AC11-owned; ``apply`` needs a publish-time schema
    failure): ONE classifier owns the ONLY fail call, so no exit can carry its
    own commit kind."""
    src = inspect.getsource(GuiSessionStore._activate_seat)
    # no exit may carry its own post-commit classification: the ONLY occurrence
    # of the post-commit label sits inside the one joint classifier
    assert src.count("FAIL_AFTER_COMMIT") == 1, src
    # exactly one joint classifier -> exactly one fail call and one typed record
    assert src.count("_fail_masked(") == 1, src
    assert src.count("_typed_delivery_error(") == 1, src
    assert src.count("committed=commit_proven") == 1, src
    for stage in ("activation_txn", "core", "staging", "freshness",
                  "publish_frame", "unmask_frame", "apply"):
        assert '"%s"' % stage in src, (stage, src)
    # classifier definition + one call per exit (7 exits + settlement default)
    assert src.count("_fail_activation(") >= 8, src

    rejection = inspect.getsource(GuiSessionStore._masked_business_rejection)
    # the diagnostic is PRIVATE and never written into the rejected object
    assert "_w3_recovery_diagnostic" in rejection, rejection
    assert "preserved" not in rejection, rejection
    assert 'data["delivery_error"] = ' not in rejection, rejection
    assert 'preserved["data"]' not in rejection, rejection


# ===========================================================================
# C3 — PHASE A PROBE: is the REAL senate submit control actually clickable?
#
#   Question (DA-Task-Brief-W3-C3 §阶段A): in the offscreen environment, can a
#   REAL mouse event land on the production ``senateProposalSubmitButton``
#   MouseArea and start the REAL owning transaction (real txn + accepted
#   receipt)? Nothing is asserted about the chain here: the probe only reports
#   WHERE it breaks. No Slot is called as a fallback.
# ===========================================================================
def test_ac_w3_04_senate_submit_control_click_probe():
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (Real Qt type check)

    def _say(tag, **fields):
        line = (tag + " " + " ".join("%s=%r" % (k, v)
                                    for k, v in fields.items()))
        print(line)
        path = os.environ.get("EOR_W3_C3_PROBE", "")
        if path:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    state = _entry_state(consul_controller="human")
    shell = _shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    _takeover_driven(shell)

    # p1 entry -> cross-seat pending for the HUMAN consul (p2) -> REAL takeover
    store.doAdvancePopulation()
    driven.render()
    assert store._pending_player_id == "player2", store._pending_player_id
    assert store.requestTakeover()["accepted"] is True
    driven.render()
    driven.render()
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    _pump(4, 5)

    stage = shell.window.findChild(QObject, "senateStage")
    button = shell.window.findChild(QObject, "senateProposalSubmitButton")
    _say("PROBE_A_OBJECTS", stage=stage, button=button,
         button_type=(button.metaObject().className() if button else None))

    parents = []
    node = button
    while node is not None and len(parents) < 8:
        parents.append(node.objectName() or node.metaObject().className())
        node = node.parent()
    _say("PROBE_A_PARENT_CHAIN", chain=parents)

    _say("PROBE_A_STORE", selectedPhaseId=store.selectedPhaseId,
         senateCurrentStep=store.senateCurrentStep,
         canCreateSenateProposal=store.canCreateSenateProposal,
         canTriggerAIProposer=store.canTriggerAIProposer,
         senateAiProposerBlocked=store.senateAiProposerBlocked,
         viewer=store.viewerPlayerId, seat=store.seatLifecycle)

    if stage is not None:
        _say("PROBE_A_STAGE", visible=stage.property("visible"),
             enabled=stage.property("enabled"),
             width=stage.property("width"), height=stage.property("height"))

    assert button is not None, "senateProposalSubmitButton not in the QML tree"
    width = float(button.property("width"))
    height = float(button.property("height"))
    point = button.mapToScene(QPointF(width / 2.0, height / 2.0))
    _say("PROBE_A_GEOMETRY", enabled=button.property("enabled"),
         visible=button.property("visible"), width=width, height=height,
         scene=(point.x(), point.y()),
         window=(shell.window.width(), shell.window.height()),
         inside_window=(0 <= point.x() < shell.window.width()
                        and 0 <= point.y() < shell.window.height()))

    # --- C3-UI2 inputs: read the ORIGINAL QML expression, never a rewrite ----
    from PySide6.QtQml import QQmlEngine, QQmlExpression

    expr_text = ("(sessionStore.canCreateSenateProposal"
                 " || sessionStore.canTriggerAIProposer)"
                 " && !root.hasZeroValueLandSelection()"
                 " && !sessionStore.senateAiProposerBlocked")

    def _eval(text, scope=None):
        scope = scope if scope is not None else button
        expr = QQmlExpression(QQmlEngine.contextForObject(scope), scope, text)
        value = expr.evaluate()
        if isinstance(value, tuple):
            value = value[0]
        return value, (expr.error().toString() if expr.hasError() else "")

    composite, composite_err = _eval(expr_text)
    zero_land, zero_err = _eval("root.hasZeroValueLandSelection()")
    _say("PROBE_A_EXPR", composite=composite, error=composite_err,
         zero_land=zero_land, zero_error=zero_err,
         button_enabled=button.property("enabled"),
         H=store.canCreateSenateProposal,
         AI=store.canTriggerAIProposer,
         blocked=store.senateAiProposerBlocked)

    cards = [o for o in shell.window.findChildren(QObject)
             if str(o.metaObject().className()).startswith("WarProposalCard")]
    _say("PROBE_A_CARDS", count=len(cards),
         editable=[c.property("editable") for c in cards],
         war_ids=[c.property("warId") for c in cards])
    war_cards = store.senateWarCards or []
    _say("PROBE_A_DTO", war_cards=len(war_cards),
         keys=sorted(war_cards[0].keys()) if war_cards else [],
         dto_can_create=(store._senate_view or {}).get("can_create_proposal"),
         store_can_create=store.canCreateSenateProposal)

    calls = []
    real_submit = store._adapter.submit_senate_proposals

    def _spy(*a, **k):
        calls.append((a, k))
        return real_submit(*a, **k)

    gates_before = len(gui.gate_log)
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=_spy):
        QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point.toPoint())
        QTest.qWait(30)
        QGuiApplication.processEvents()
        new_gates = gui.gate_log[gates_before:]
        _say("PROBE_A_AFTER_CLICK", adapter_calls=len(calls),
             new_gates=[(g["kind"], g["tier"], g["txn"]) for g in new_gates],
             gate=dict(store._async_gate) if store._async_gate else None,
             seat=store.seatLifecycle)
        if new_gates:
            driven.render()
            QTest.qWait(20)
            QGuiApplication.processEvents()
            receipt = (store._committed_receipt or {}).get("data", {}).get(
                "delivery")
            _say("PROBE_A_COMMIT", accepted=bool(
                (store._committed_receipt or {}).get("success")),
                outcome=(receipt or {}).get("outcome"),
                adapter_calls=len(calls), seat=store.seatLifecycle,
                viewer=store.viewerPlayerId)

    reachable = bool(calls) and bool(new_gates)
    _say("PROBE_A_CONCLUSION", UI_CLICK_REACHABLE=reachable,
         adapter_calls=len(calls), gate_started=bool(new_gates))
    assert reachable, ("PROBE_A_NOT_REACHABLE"
                       " adapter_calls=%d gate_started=%s enabled=%r"
                       " visible=%r scene=%r"
                       % (len(calls), bool(new_gates),
                          button.property("enabled"),
                          button.property("visible"),
                          (point.x(), point.y())))
