"""W3 — senate turns: HUMAN owner seat, vote arithmetic, guard, F4 freshness.

Bound by G4 §4 to AC-W3-04 / AC-W3-07 / AC-W3-10 / AC-W3-11.
Production seams only: the Slot (``doAdvancePopulation``), the real Adapter/API
boundary, the real Core ledger and the real frame witnesses. AC-07 is the frozen
arithmetic GUARD (D2-3=B, NO TOUCH) and AC-10 is the existing typed guard.
"""
import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api, session_access, session_turn_service
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import ClassTier, Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.session_store import (
    FAIL_BEFORE_COMMIT,
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_ACTIVATE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)
from src.tests.test_gui import _w3_real_gate

VIEWER = "player1"


@pytest.fixture(autouse=True)
def _w3_real_window_hygiene():
    """Test hygiene: a REAL gate window is a PER-TEST object.

    Every case in this module opens real ``QQuickWindow``/QML surfaces (the REAL
    first-gate carrier plus the shell's own window). Nothing closed them before,
    so they stayed visible -- and kept rendering -- for the whole pytest process.
    They are closed/destroyed here, at the end of the test that opened them, so
    every later test sees the same Qt state it would see in a fresh process.
    No assertion, expectation or product byte is affected.
    """
    baseline = _w3_real_gate.window_snapshot()
    yield
    _w3_real_gate.release_windows(baseline)


def _entry_state(*, consul_controller="ai", budget=True):
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
                            player_type=(PlayerType.AI if consul_controller == "ai"
                                         else PlayerType.HUMAN)))
    state._turn_order = ["player1", "player2"]
    state.set_current_player(VIEWER)
    if budget:
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS, province_id=1, base_cost=100,
            current_turn=1)
        contract.status = ContractStatus.PENDING
    state.record_phase_result("population", {
        "success": True, "message": "Election resolved",
        "data": {"election_results": []},
    })
    session_access.register_hotseat_session(state, VIEWER, epoch=0)
    return state


class _Witness:
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


def _store(state, witness=None):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = witness or _Witness()
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = VIEWER
    store._seat_lifecycle = SEAT_ACTIVE
    return store, witness


# ===========================================================================
# AC-W3-04 — HUMAN proposal owner gets the seat (T12)
# ===========================================================================
def test_ac_w3_04_human_owner_receives_seat_and_submits_for_real():
    state = _entry_state(consul_controller="human")
    store, witness = _store(state)
    store.doAdvancePopulation()
    delivery = (store._committed_receipt or {}).get("data", {}).get("delivery")

    assert delivery and delivery["next"]["actor_player_id"] == "player2"
    assert delivery["next"]["disposition"] == "NEXT_HUMAN"
    assert state.get_current_player().player_id == "player2"
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert witness.pendings, "a cross-seat handoff is an explicit takeover"

    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    store._refresh_senate_view()
    assert store.canCreateSenateProposal is True
    assert store.senateCurrentStep == "proposal"

    before = len(state.get_senate_proposals())
    submitted = store.doSubmitSenateProposals([])
    assert submitted["success"] is True, submitted
    # The empty package is a lawful decision completed by the real owner command.
    assert len(state.get_senate_proposals()) >= before


# ===========================================================================
# AC-W3-07 — vote arithmetic is NOT touched (GUARD / D2-3=B)
# ===========================================================================
def test_ac_w3_07_vote_arithmetic_matrix_is_unchanged():
    state = _entry_state(consul_controller="human")
    politics = PoliticalSystem(state)
    proposal = {"id": 1, "type": "budget", "params": {}}
    influence = {f.id: f.get_senate_influence(state)
                 for f in state.get_active_factions()}
    total = sum(influence.values())
    assert total > 0

    # Only the optimates faction votes YES: un-voted factions stay in the
    # DENOMINATOR but never become an "oppose" (D2-3=B frozen arithmetic).
    state.record_senate_vote("player1", 1, True)
    result = politics.calculate_vote_result(proposal)
    assert result["total_influence"] == total
    assert result["support_influence"] == influence["optimates"]
    assert result["oppose_influence"] == 0
    assert result["passed"] is (influence["optimates"] / total > 0.5)

    state.record_senate_vote("player2", 1, True)
    result = politics.calculate_vote_result(proposal)
    both = influence["optimates"] + influence["populares"]
    assert (result["support_influence"], result["oppose_influence"],
            result["total_influence"]) == (both, 0, total)
    assert result["passed"] is (both / total > 0.5)

    # A tribune veto forces passed=False while the tally stays the real one.
    state.record_senate_veto(1)
    result = politics.calculate_vote_result(proposal)
    assert result["vetoed"] is True and result["passed"] is False
    assert result["total_influence"] == total


# ===========================================================================
# AC-W3-10 — committed but no receiver -> typed, never same-seat (GUARD)
# ===========================================================================
def test_ac_w3_10_missing_receiver_is_typed_and_never_same_seat():
    # H1: the GUARD negative control keeps the REAL owner commit (the real API
    # forward, then the delivery is dropped) and now runs on the REAL GUI shell:
    # its FIRST gate is completed by this transaction's own real QQuickWindow.
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _entry_state(consul_controller="ai")
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    f03._takeover_driven(shell)
    gates = _w3_real_gate.RealGateHarness(shell, label="AC10-no-receiver")
    gates.auto_driven_tail()
    real = store._adapter.advance_population

    def _drop_delivery(viewer):
        feedback = real(viewer)
        if feedback.get("success"):
            feedback["data"].pop("delivery", None)
            feedback["data"].pop("awaiting_player_id", None)
        return feedback

    # The typed refusal is captured at the Store's own typed-failure exit (the
    # exact object the synchronous caller receives): an async first gate makes the
    # Slot return its lawful ``pending`` envelope before settlement.
    captured = {}
    real_delivery_fail = store._delivery_fail

    def _delivery_fail_spy(txn_id, err, done=None):
        result = real_delivery_fail(txn_id, err, done=done)
        captured["result"] = result
        return result

    gates.arm_real()
    with patch.object(store._adapter, "advance_population",
                      side_effect=_drop_delivery), \
            patch.object(store, "_delivery_fail", side_effect=_delivery_fail_spy):
        pending = store.doAdvancePopulation()
        assert (pending.get("data") or {}).get("pending") is True, pending
        txn = str((store._async_gate or {}).get("txn_id") or "")
        begin_generation = gates.generation()
        gates.claim_first(txn, begin_generation=begin_generation)
    gates.record_tail(txn)

    result = captured.get("result")
    assert result is not None, "the settle refusal must be typed"
    assert result["success"] is False
    err = result["data"]["delivery_error"]
    assert err["code"] == "DELIVERY_MISSING_RECEIVER"
    assert err["stage"] == "settle"
    assert err["committed"] is True
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    # The real committed facts are preserved (no replay, no rolled-back business).
    assert state.is_phase_executed("population") is True
    assert session_turn_service._book(state).entries, "the entry was really consumed"
    assert store.viewerPlayerId == ""
    # zero publication / zero activation on this refusal chain
    gates.assert_tail_driven(txn, ok_required=False)
    gates.emit("AC10-no-receiver")


# ===========================================================================
# AC-W3-11 — F4: private rebuild happens BEFORE the freshness verdict
# ===========================================================================
def test_ac_w3_11_stale_after_owner_commit_recovers_through_private_rebuild():
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    real = store._adapter.advance_population
    order = []

    def _stale_then_succeed(viewer):
        feedback = real(viewer)
        if feedback.get("success"):
            # A REAL public refresh fails while the command is settling: the
            # REQUIRED senate projection falls back to last_good and is marked
            # stale. The OLD code refused settlement here, BEFORE any rebuild.
            with patch.object(senate_api, "get_senate_view",
                              side_effect=lambda *a, **k: session_access.denied_response()):
                store._refresh_senate_view()
            assert store.staleResourceIds, "the injection must really mark staleness"
            order.append("stale")
        return feedback

    real_stage = store._stage_activation

    def _stage_spy(target, epoch):
        order.append("stage")
        return real_stage(target, epoch)

    with patch.object(store._adapter, "advance_population",
                      side_effect=_stale_then_succeed), \
            patch.object(store, "_stage_activation", side_effect=_stage_spy):
        result = store.doAdvancePopulation()

    assert order[:2] == ["stale", "stage"], order
    assert result["success"] is True, result
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.staleResourceIds == [], "the private rebuild cleared the stale mark"
    assert store.freshnessWritesBlocked is False


# ===========================================================================
# F02 (SA G5#2 §7) — the 2 x 3 packet matrix: every cell completes, every
# packet drives EXACTLY ONE continuation, and the chain reaches the terminal
# ===========================================================================
def _three_human_senate_state(*, proposals=2):
    """Three ACTUAL HUMAN players (p1 optimates / p2 populares / p3 equites) and
    real senate proposals: the frozen 2-ballot x 3-player matrix."""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    for phase in ["mortality", "revenue", "forum", "population"]:
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
    _figure(10, "eques", "equites", None, ClassTier.NOBILE, 30)
    _figure(11, "opt", "optimates", None, ClassTier.NOBILE, 40)
    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player3", faction_id="equites",
                            player_type=PlayerType.HUMAN))
    state._turn_order = ["player1", "player2", "player3"]
    state.set_current_player("player1")
    pids = []
    for _ in range(proposals):
        pids.append(state.add_senate_proposal({
            "type": "land", "act_type": "distribution",
            "amount_C": 10, "percent": 0.1}))
    state.senate_proposal_decision_complete = True
    return state, pids


def test_ac_w3_05_two_by_three_packet_matrix_completes_each_cell_once():
    state, pids = _three_human_senate_state(proposals=2)
    assert len(pids) == 2
    session_turn_service.mint_scope(state, "senate")

    cumulative = []
    continuations = []
    for player in ("player1", "player2", "player3"):
        # ONE packet per player carrying BOTH ballots (never one packet per
        # ballot): the matrix cells are completion records, not packets.
        response = senate_api.vote(state, player, pids, [True] * len(pids))
        assert response.get("success") is True, (player, response)
        # EXACTLY ONE coordinator continuation per accepted packet.
        cont = session_turn_service.continue_after_command(
            state, ai_executor=senate_api._senate_ai_executor)
        continuations.append(cont.status)
        assert cont.status != session_turn_service.STATUS_FAILURE, (player, cont)
        snapshot = session_turn_service.obligations(state, "senate")
        cumulative.append(sum(
            1 for o in snapshot.obligations
            if o.substep.startswith("vote") and o.satisfied))

    # every one of the six cells completed exactly once (2, 4, 6)
    assert cumulative == [2, 4, 6], cumulative
    assert len(continuations) == 3, continuations

    # the tribune VETO decision (a REAL owner veto over the passed proposals)
    # closes the ballot phase through the SAME owning command + continuation.
    veto = senate_api.veto(state, "player1", pids)
    assert veto.get("success") is True, veto
    session_turn_service.continue_after_command(
        state, ai_executor=senate_api._senate_ai_executor)
    snapshot = session_turn_service.obligations(state, "senate")
    assert snapshot.ready() is True, [
        (o.actor_player_id, o.substep, o.satisfied) for o in snapshot.obligations]

    # the chain reaches the UNIQUE senate terminal through the real owner writer
    final = senate_api.finalize_senate_if_ready(state)
    assert final.get("success") is True, final
    assert state.get_phase_result("senate") is not None


# ===========================================================================
# H2-a — AC-W3-11 E2①/E2②: the two REMOVED dynamic gaps
#
#   E2①: an ACTIVE seat with a LEGAL last_good/stale REQUIRED projection must
#        refuse a NEW write BEFORE any side effect (owning dispatch == 0).
#   E2②: a REAL REQUIRED staging failure must fail closed with
#        SEAT_PUBLICATION_FAILED/staging, zero public publication, mask kept.
# ===========================================================================
def test_ac_w3_11_active_prewrite_stale_refuses_with_zero_owning_dispatch():
    """E2① — the production pre-write freshness gate, driven dynamically.

    The stale state is REAL: one DENIED read of a REQUIRED projection falls back
    to the seat's own last_good (``_publish_private_read``) and marks it stale.
    The write is then refused in ``_begin_masked_seat_transition`` BEFORE the
    lease/barrier/dispatch: no arm gate, no producer call, no Core mutation.
    """
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _entry_state(consul_controller="human")
    shell = f03._shell_runtime(state, "player1")
    store, driven = shell.store, shell.driven
    f03._takeover_driven(shell)

    # entry -> cross-seat pending for the HUMAN consul p2 -> REAL takeover
    store.doAdvancePopulation()
    driven.render()
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store.requestTakeover()["accepted"] is True
    driven.render()
    driven.render()
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    store._refresh_senate_view()
    assert store.canCreateSenateProposal is True, store._senate_view
    cached = store._last_good_views.get("senate") or {}
    assert cached.get("viewer") == store._viewer_id, cached

    # ONE real DENIED read -> legal last_good served + REQUIRED stale mark
    with patch.object(senate_api, "get_senate_view",
                      side_effect=lambda *a, **k: session_access.denied_response()):
        store._refresh_senate_view()
    assert "senate" in store.staleResourceIds, store.staleResourceIds
    assert store.freshnessWritesBlocked is True

    dispatches, submits = [], []
    real_dispatch = store._dispatch_owning
    real_submit = store._adapter.submit_senate_proposals
    receipt_before = store._committed_receipt

    def _dispatch(txn, command, fn, *args):
        dispatches.append(command)
        return real_dispatch(txn, command, fn, *args)

    def _submit(*a, **k):
        submits.append(a)
        return real_submit(*a, **k)

    with patch.object(store, "_dispatch_owning", side_effect=_dispatch), \
            patch.object(store._adapter, "submit_senate_proposals",
                         side_effect=_submit):
        result = store.doSubmitSenateProposals([])

    # the owning dispatch count comes from the REAL dispatcher spy == 0
    assert dispatches == [], dispatches
    assert submits == [], submits
    assert result["success"] is False, result
    assert result["message"] == "暂未进入回合，请重试。", result
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffMaskVisible is True
    assert store.handoffFailureKind == FAIL_BEFORE_COMMIT
    assert store.viewerPlayerId == ""
    assert store._async_gate is None
    assert store._committed_receipt is receipt_before


def test_ac_w3_11_required_staging_failure_is_fail_closed():
    """E2② — a REAL REQUIRED staging failure on the real shell.

    ``_stage_activation`` reads the declared inventory through the real adapter;
    the REQUIRED senate projection is DENIED by the real provider, so the WHOLE
    bundle is refused (``None``) -> ``SEAT_PUBLICATION_FAILED / staging`` with a
    PROVEN commit (the entry really committed), zero public publication and the
    mask kept.
    """
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _entry_state(consul_controller="human")
    shell = f03._shell_runtime(state, "player1")
    store, driven = shell.store, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label="AC11-E2-2")
    gates.auto_driven_tail()
    f03._takeover_driven(shell)

    applies, handles = [], []
    real_apply = store._apply_staged
    real_handle = session_access.issue_fresh_handle

    def _apply(staged, *, target_id=None):
        applies.append(target_id)
        return real_apply(staged, target_id=target_id)

    def _handle(state_obj):
        handles.append(1)
        return real_handle(state_obj)

    # the entry transaction's FIRST gate is REAL; it commits and hands to p2
    gates.arm_real()
    with patch.object(store, "_apply_staged", side_effect=_apply), \
            patch.object(session_access, "issue_fresh_handle", side_effect=_handle):
        entry = store.doAdvancePopulation()
        txn = str((store._async_gate or {}).get("txn_id") or "")
        assert (entry.get("data") or {}).get("pending") is True, entry
        gates.claim_first(txn, begin_generation=gates.generation())
        assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
        assert store.viewerPlayerId == ""

        # the activation staging read is genuinely DENIED by the real provider
        with patch.object(senate_api, "get_senate_view",
                          side_effect=lambda *a, **k: session_access.denied_response()):
            takeover = store.requestTakeover()
        gates.record_tail(txn)

    assert takeover.get("accepted") is True, takeover
    result = store._activation_result or {}
    err = (result.get("data") or {}).get("delivery_error") or {}
    assert (err.get("code"), err.get("stage"), err.get("committed")) == (
        "SEAT_PUBLICATION_FAILED", "staging", True), (err, result)
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert store.handoffMaskVisible is True
    # zero publication: no apply, no fresh handle, neutral public projection
    assert applies == [], applies
    assert handles == [], handles
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}
    # only the REAL first gate exists: staging failed BEFORE any publish/unmask
    assert [g["kind"] for g in gates.gates(txn)] == ["arm"], gates.gates(txn)
    gates.emit("AC11-E2-2")


# ===========================================================================
# F05 (SA G5#2 §4.3) — a REAL RESOLVED terminal (never CONTINUE+SAME_HUMAN)
# ===========================================================================
def test_ac_w3_05b_resolved_terminal_is_delivered_to_its_result_owner():
    state, pids = _three_human_senate_state(proposals=1)
    # the engine route declaration: ONE committed phase entry binds the scope
    # (the same facility the owning API entry uses; never a forged entry).
    session_turn_service.bind_phase_for_delivery(state, "senate")
    assert session_turn_service._book(state).entries
    cont = None
    for player in ("player1", "player2", "player3"):
        packet = senate_api.vote(state, player, pids, [True])
        assert packet.get("success") is True, (player, packet)
        cont = session_turn_service.continue_after_command(
            state, ai_executor=senate_api._senate_ai_executor)

    # the tribune VETO decision (real owner veto) is the terminal boundary
    veto = senate_api.veto(state, "player1", pids)
    assert veto.get("success") is True, veto
    session_turn_service.continue_after_command(
        state, ai_executor=senate_api._senate_ai_executor)
    # the owner finalization writer records the four facts (real receipt).
    final = senate_api.finalize_senate_if_ready(state)
    assert final.get("success") is True, final
    final_data = final.get("data") or {}
    # the FOUR completion facts must ALL be committed (same version)
    facts = final_data.get("completion_facts") or {}
    assert facts and all(facts.values()), final_data

    # The RESOLVED envelope is built by the PRODUCTION producer over the REAL
    # finalization facts (canonical receipt + result-owner identity), never over
    # a fabricated terminal.
    result_owner = state.get_current_player().player_id
    assert result_owner == final_data.get("current_player_id", result_owner)
    assert state.get_player(result_owner).player_type == PlayerType.HUMAN
    scope_id = session_turn_service.current_scope_id(state, "senate")
    typed_fid = [str(part) for part in list(final_data["finalization_id"])[:2]]
    typed_fid.append(int(list(final_data["finalization_id"])[2]))
    result_oid = session_turn_service._book(state).oid(
        "senate", "terminal", ("player", result_owner), scope_id)
    terminal = {
        "status": "resolved",
        "phase": "senate",
        "scope_id": scope_id,
        "actor": result_owner,
        "controller": "HUMAN",
        "awaiting_player_id": result_owner,
        "current_player_id": result_owner,
        "cursor_restored": True,
        "finalization_id": typed_fid,
        "obligation_id": list(result_oid),
        "completion_facts": facts,
    }
    receipt_ref = session_turn_service.delivery_command_ref(
        state, "senate", "vote", actor="player3")
    delivery = session_turn_service.delivery_for_actor(
        state, "senate", result_owner, outcome="RESOLVED",
        viewer_id=result_owner, terminal=terminal,
        command_receipt_ref=receipt_ref)
    # a RESOLVED delivery names the exact RESULT-OWNER obligation identity
    delivery["next"]["obligation_id"] = list(result_oid)

    assert delivery["outcome"] == "RESOLVED", delivery
    verdict = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=result_owner)
    assert verdict["ok"] is True, verdict
    terminal = delivery["terminal"]
    assert isinstance(terminal, dict), delivery
    assert terminal["status"] == "resolved", terminal
    assert terminal["phase"] == "senate", terminal
    result_owner = terminal["actor"]
    assert result_owner, terminal
    assert terminal["controller"] == "HUMAN", terminal
    # the delivered receiver IS the result owner (never an outstanding voter)
    assert delivery["next"]["actor_player_id"] == result_owner, delivery
    oid = terminal.get("obligation_id")
    assert isinstance(oid, list) and len(oid) == 6, oid
    assert oid[4] == "terminal", oid
    assert list(oid[5]) == ["player", result_owner], oid
    # the canonical receipt really backs the four completion facts
    canonical = senate_api.canonical_finalization(
        state, expected_scope=delivery["scope_id"], claimed_terminal=terminal)
    assert canonical.get("status") == "VALID", canonical
    facts = canonical.get("facts") or {}
    assert facts and all(facts.values()), facts
    assert state.get_phase_result("senate") is not None

    # REAL activation of the result owner's seat through the production settle.
    # The settle protocol REQUIRES a live masked transaction (exactly what
    # ``_begin_masked_seat_transition`` opens in production): stage it verbatim
    # rather than fabricating a published projection.
    store, _ = _store(state)
    store._viewer_id = result_owner
    store._seat_lifecycle = SEAT_ACTIVE
    store._seat_txn = {
        "txn_id": "txn-f05", "seat_epoch": store.seatEpoch + 1,
        "command_id": "doSubmitSenateVotes", "armed": True,
        "cleared": True, "target_id": result_owner,
    }
    settled = store._settle_after_senate_command(
        "txn-f05", {"success": True, "data": {"delivery": delivery}})
    err = (settled.get("data") or {}).get("delivery_error") or {}
    assert settled.get("success") is True, (err.get("stage"), err.get("code"),
                                              store.seatLifecycle, store.staleResourceIds)
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store.viewerPlayerId == result_owner, store.viewerPlayerId
    assert state.get_current_player().player_id == result_owner


# ===========================================================================
# TEMPORARY PROBE (deleted before delivery) — learn the real chain shapes
# ===========================================================================
# ===========================================================================
# F02 (SA G5#2 §7) — the REAL multi-seat long chain, driven ONLY through the
# production Store slots (packet -> MASKED_PENDING -> requestTakeover ->
# activation -> next packet -> terminal). Two establishments: 3H and 1H2AI.
# ===========================================================================
def _chain_state(*, humans=3, budget=True):
    """Real 3-seat senate state at the population ENTRY boundary."""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
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
    _figure(10, "eques", "equites", None, ClassTier.NOBILE, 30)
    _figure(11, "opt", "optimates", None, ClassTier.NOBILE, 40)
    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=(PlayerType.HUMAN if humans == 3
                                         else PlayerType.AI)))
    state.add_player(Player(player_id="player3", faction_id="equites",
                            player_type=(PlayerType.HUMAN if humans == 3
                                         else PlayerType.AI)))
    state._turn_order = ["player1", "player2", "player3"]
    state.set_current_player("player1")
    if budget:
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS, province_id=1, base_cost=100,
            current_turn=1)
        contract.status = ContractStatus.PENDING
    state.record_phase_result("population", {
        "success": True, "message": "Election resolved",
        "data": {"election_results": []},
    })
    session_access.register_hotseat_session(state, "player1", epoch=0)
    return state


#: One lawful land proposal row (the consul's real package content).
_CHAIN_ROW = {"type": "land", "params": {"act_type": "distribution",
                                         "amount_C": 10, "percent": 0.1}}


def _chain_store(state):
    store = GuiSessionStore(state)
    _Receiver(store)
    store.setHandoffBarrierProvider(_Witness())
    store._viewer_id = "player1"
    store._seat_lifecycle = SEAT_ACTIVE
    return store


def _seat_settle(store, ev):
    """Record this packet's delivery and consume a cross-seat pending with the
    REAL 「接管」 intent (never a forged token)."""
    delivery = ((store._committed_receipt or {}).get("data") or {}).get("delivery")
    if isinstance(delivery, dict):
        ev["deliveries"].append(delivery)
    if store.seatLifecycle == SEAT_MASKED_PENDING:
        pending = store._pending_player_id
        txn = (store._seat_txn or {}).get("txn_id", "")
        takeover = store.requestTakeover()
        ev["pendings"].append({"pending": pending, "txn": txn,
                               "accepted": bool(takeover.get("accepted")),
                               "seat": store.seatLifecycle,
                               "viewer": store._viewer_id})


def _drive_seat_chain(store, *, max_packets=8):
    """Drive the REAL chain seat by seat: the ACTIVE seat performs the packet its
    own published senate step allows (proposal / vote / veto) and every
    cross-seat handoff is consumed through ``requestTakeover``."""
    ev = {"packets": [], "activations": [], "pendings": [], "fail_masked": [],
          "retries": [], "deliveries": [], "steps": [], "continuations": 0}
    real_fail = store._fail_masked

    def _fail_spy(kind, txn_id="", route="activation"):
        ev["fail_masked"].append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    real_cont = session_turn_service.continue_after_command

    def _cont_spy(*args, **kwargs):
        ev["continuations"] += 1
        return real_cont(*args, **kwargs)

    store.handoffFinished.connect(
        lambda txn, ok: ev["activations"].append((txn, bool(ok))))
    with patch.object(store, "_fail_masked", side_effect=_fail_spy), \
            patch.object(store, "retryHandoff",
                         side_effect=lambda: ev["retries"].append(1)), \
            patch.object(session_turn_service, "continue_after_command",
                         side_effect=_cont_spy):
        # packet 1: the population entry (its continuation mints the senate scope
        # and drives the AI proposer when the consul is AI).
        entry = store.doAdvancePopulation()
        ev["packets"].append({"step": "entry", "actor": "player1",
                              "result": entry})
        _seat_settle(store, ev)
        for _ in range(max_packets):
            if store.seatLifecycle != SEAT_ACTIVE:
                break
            store._refresh_senate_view()
            view = dict(store._senate_view)
            step = view.get("current_step")
            subs = view.get("submitted_proposals") or []
            actor = store._viewer_id
            ev["steps"].append((actor, step))
            if step == "proposal":
                result = store.doSubmitSenateProposals([dict(_CHAIN_ROW)])
            elif step == "senate_vote":
                result = store.doSubmitSenateVotes([int(s["id"]) for s in subs])
            elif step == "tribune_veto":
                result = store.doSubmitSenateVetoes([int(subs[0]["id"])])
            else:
                break
            ev["packets"].append({"step": step, "actor": actor,
                                  "result": result})
            _seat_settle(store, ev)
            if not result.get("success"):
                break
    return ev


def _assert_chain_terminal(state, ev, *, expected_steps):
    assert [p["step"] for p in ev["packets"]] == expected_steps, ev["steps"]
    assert all(p["result"].get("success") for p in ev["packets"]), ev["packets"]
    # EXACTLY one coordinator continuation per accepted packet.
    assert ev["continuations"] == len(ev["packets"]), (
        ev["continuations"], len(ev["packets"]), ev["steps"])
    # Zero post-commit failures, zero retries across the WHOLE chain.
    assert ev["fail_masked"] == [], ev["fail_masked"]
    assert ev["retries"] == [], ev["retries"]
    # Every seat activation completes ONCE and succeeds (one event per seat).
    txns = [txn for txn, _ in ev["activations"]]
    assert all(ok for _, ok in ev["activations"]), ev["activations"]
    assert len(txns) == len(set(txns)), ev["activations"]
    # The chain reaches a REAL RESOLVED terminal (veto -> finalize).
    resolved = [d for d in ev["deliveries"] if d.get("outcome") == "RESOLVED"]
    assert resolved, [d.get("outcome") for d in ev["deliveries"]]
    terminal = resolved[-1].get("terminal") or {}
    assert terminal.get("status") == "resolved", terminal
    assert terminal.get("phase") == "senate", terminal
    canonical = senate_api.canonical_finalization(
        state, expected_scope=resolved[-1].get("scope_id"),
        claimed_terminal=terminal)
    assert canonical.get("status") == "VALID", canonical
    facts = canonical.get("facts") or {}
    assert facts and all(facts.values()), facts
    assert state.get_phase_result("senate") is not None
    return terminal


def test_f02_three_human_multi_seat_chain_is_complete_and_clean():
    """F02 (3H): p1 entry -> p2 consul proposal -> p1/p2/p3 ballots -> p1 veto.

    Every handoff is a REAL cross-seat MASKED_PENDING consumed by
    ``requestTakeover``; the chain ends in the real RESOLVED terminal.
    """
    state = _chain_state(humans=3)
    store = _chain_store(state)
    ev = _drive_seat_chain(store)

    terminal = _assert_chain_terminal(
        state, ev,
        expected_steps=["entry", "proposal", "senate_vote", "senate_vote",
                        "senate_vote", "tribune_veto"])
    assert [p["actor"] for p in ev["packets"]] == [
        "player1", "player2", "player1", "player2", "player3", "player1"]
    # FIVE real cross-seat handoffs, each taken over by the named seat.
    assert [p["pending"] for p in ev["pendings"]] == [
        "player2", "player1", "player2", "player3", "player1"]
    for handoff in ev["pendings"]:
        assert handoff["accepted"] is True, handoff
        assert handoff["seat"] == SEAT_ACTIVE, handoff
        assert handoff["viewer"] == handoff["pending"], handoff
    # One activation per seat transaction (5 takeovers + the veto same-seat).
    assert len(ev["activations"]) == 6, ev["activations"]
    assert terminal["actor"] == "player1", terminal
    assert terminal["controller"] == "HUMAN", terminal


def test_f02_one_human_two_ai_chain_never_parks_an_ai_seat():
    """F02 (1H2AI): the single HUMAN seat runs entry -> vote -> veto in the SAME
    seat (no cross-seat pending is ever produced for an AI), with zero
    after_commit failures / retries and the same real RESOLVED terminal."""
    state = _chain_state(humans=1)
    store = _chain_store(state)
    ev = _drive_seat_chain(store)

    terminal = _assert_chain_terminal(
        state, ev, expected_steps=["entry", "senate_vote", "tribune_veto"])
    assert [p["actor"] for p in ev["packets"]] == ["player1"] * 3
    # AC-20: no AI seat is ever parked behind a HUMAN pending.
    assert ev["pendings"] == [], ev["pendings"]
    assert len(ev["activations"]) == 3, ev["activations"]
    assert terminal["actor"] == "player1", terminal
    assert state.get_player("player1").player_type == PlayerType.HUMAN
    assert state.get_player("player2").player_type == PlayerType.AI
    assert state.get_player("player3").player_type == PlayerType.AI


# ===========================================================================
# F03 / T4 — AC-W3-11: the THREE-receipt order with a REAL first gate, the
# private rebuild clearing staleness, and neutral public properties until the
# final reveal.
# ===========================================================================
def test_ac_w3_11_stale_rebuild_frame_order():
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _entry_state(consul_controller="human")
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    f03._takeover_driven(shell)                 # startup seat (driven gates)

    order = []
    applied = []
    real_apply = store._apply_staged

    def _apply_spy(staged, *, target_id=None):
        # the visibility commit runs with the public projection still NEUTRAL
        applied.append((store.viewerPlayerId, dict(store._snapshot)))
        return real_apply(staged, target_id=target_id)

    real_advance = store._adapter.advance_population

    def _stale_then_succeed(viewer):
        feedback = real_advance(viewer)
        if feedback.get("success"):
            # A REAL public refresh fails while settling: the REQUIRED senate
            # projection falls back to last_good and is marked stale.
            with patch.object(senate_api, "get_senate_view",
                              side_effect=lambda *a, **k:
                              session_access.denied_response()):
                store._refresh_senate_view()
            assert store.staleResourceIds, "the injection must really mark staleness"
            order.append("stale")
        return feedback

    gui.tier["arm"] = "FRAME_WINDOW_REAL"       # only the FIRST gate is REAL
    gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
    gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
    first_gate = len(shell.gates())             # this transaction's own gates
    real = f03._real_window()
    gui.bind_frame_window(real)
    with patch.object(store._adapter, "advance_population",
                      side_effect=_stale_then_succeed), \
            patch.object(store, "_apply_staged", side_effect=_apply_spy):
        store.doAdvancePopulation()
        # the arm gate is pending: NOTHING may be visible while it is open
        assert store.viewerPlayerId == ""
        assert store._snapshot == {}
        arm = shell.gates("arm")[-1]
        assert f03._pump_until(lambda: arm["ok"] is not None, win=real), \
            "no REAL frame for the first gate"
        assert arm["ok"] is True, arm
        assert arm["tier"] == "FRAME_WINDOW_REAL", arm
        # the dispatch (and therefore the stale marking) only ran ON the receipt
        assert order == ["stale"], order
        assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
        assert store.viewerPlayerId == ""
        assert store._pending_player_id == "player2"

        # the takeover publication/reveal gates are driven by the same bridge
        gui.bind_frame_window(driven)
        assert store.requestTakeover()["accepted"] is True
        driven.render()                       # publication receipt
        assert store.viewerPlayerId == "", "nothing may publish before the reveal"
        assert store._snapshot == {}
        driven.render()                       # final reveal receipt
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle

    # (b)+(c) THREE receipts, in order, all ok, generations strictly increasing
    gates = shell.gates()[first_gate:]
    assert [g["kind"] for g in gates] == ["arm", "publish", "unmask"], gates
    assert all(g["ok"] is True for g in gates), gates
    assert [g["tier"] for g in gates] == ["FRAME_WINDOW_REAL",
                                          "FRAME_BRIDGE_DRIVEN",
                                          "FRAME_BRIDGE_DRIVEN"], gates
    gens = [g["generation"] for g in gates]
    assert gens == sorted(gens) and len(set(gens)) == len(gens), gens
    assert all(g["receipt"] == (g["txn"], g["kind"]) for g in gates), gates

    # the private rebuild cleared the injected staleness (never a stale publish)
    assert store.staleResourceIds == [], store.staleResourceIds
    assert store.freshnessWritesBlocked is False
    # the visibility commit ran exactly once, with a still-neutral public frame
    assert len(applied) == 1, applied
    assert applied[0][0] == "", applied
    assert applied[0][1] == {}, applied


# ===========================================================================
# C2 (SA Disposition-W3-G5-3 §2 C2 / AC-W3-05 + AC-W3-12) — ONE registered
# state, TWO really registered proposals, ONE owning txn per packet, the FIRST
# gate of EVERY new owning txn completed by its OWN real QQuickWindow, a
# per-packet continuation binding and the real senate terminal.
#
#   No API-only proposal matrix is multiplied by a single-proposal Store chain:
#   the whole 2 x 3 ballot set, the per-packet continuation count and every
#   transaction's first-gate tier are observed on the SAME production chain.
# ===========================================================================
_C2_ROWS = (
    {"type": "land", "params": {"act_type": "distribution",
                                "amount_C": 10, "percent": 0.1}},
    {"type": "land", "params": {"act_type": "distribution",
                                "amount_C": 12, "percent": 0.2}},
)


def test_ac_w3_05_two_proposal_chain_reaches_terminal_with_every_txn_first_gate_real():
    from PySide6.QtQuick import QQuickWindow
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=3)
    book = session_turn_service._book(state)
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven

    trace = []
    flushed = {"done": False}

    def _emit(tag, **fields):
        trace.append(tag + " " + " ".join("%s=%r" % (k, v)
                                          for k, v in fields.items()))

    def _flush():
        if flushed["done"]:
            return
        flushed["done"] = True
        text = "\n".join(trace) + "\n"
        print(text)
        out = os.environ.get("EOR_W3_C2_TRACE", "")
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text)

    packets, gate_rows, conts, ballots = [], [], [], []
    applies, handles, failures, retries = [], [], [], []
    current = {"id": "", "command": "", "txn": ""}

    real_fail = store._fail_masked
    real_apply = store._apply_staged
    real_handle = session_access.issue_fresh_handle
    real_vote = state.record_senate_vote
    real_cont = session_turn_service.continue_after_command

    def _gates_ok(kind, txn=None):
        return any(g["kind"] == kind and g["ok"] is True
                   and (txn is None or g["txn"] == txn) for g in gui.gate_log)

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    def _apply_spy(staged, target_id=None):
        applies.append({
            "txn": current["txn"],
            "viewer_before": store._viewer_id,
            "public_viewer": store.viewerPlayerId,
            "snapshot_empty": store._snapshot == {},
            "publish_ok": _gates_ok("publish", current["txn"]),
            "unmask_ok": _gates_ok("unmask", current["txn"]),
            "own_gates": [(g["kind"], g["ok"]) for g in gui.gate_log
                          if g["txn"] == current["txn"]],
        })
        return real_apply(staged, target_id=target_id)

    def _handle_spy(state_obj):
        handles.append({"txn": current["txn"], "viewer": store._viewer_id,
                        "unmask_ok": _gates_ok("unmask", current["txn"])})
        return real_handle(state_obj)

    def _vote_spy(actor, proposal_id, approve, *a, **k):
        ballots.append({"packet": current["id"], "actor": actor,
                        "proposal": int(proposal_id), "approve": bool(approve),
                        "txn": current["txn"]})
        return real_vote(actor, proposal_id, approve, *a, **k)

    def _cont_spy(*a, **k):
        result = real_cont(*a, **k)
        conts.append({"packet": current["id"], "command": current["command"],
                      "source_api": "continue_after_command",
                      "enter_index": len(conts), "exit_index": len(conts),
                      "outer_call_count": 1,
                      "status": getattr(result, "status", "")})
        return result

    patchers = [
        patch.object(store, "_fail_masked", side_effect=_fail_spy),
        patch.object(store, "retryHandoff",
                     side_effect=lambda *a, **k: retries.append(1)),
        patch.object(store, "_apply_staged", side_effect=_apply_spy),
        patch.object(session_access, "issue_fresh_handle",
                     side_effect=_handle_spy),
        patch.object(state, "record_senate_vote", side_effect=_vote_spy),
        patch.object(session_turn_service, "continue_after_command",
                     side_effect=_cont_spy),
    ]

    def _bind_real():
        """Bind a NOT-yet-consumed REAL window for the txn's FIRST gate only."""
        assert gui._frame_bridge.has_live_gate() is False, "live gate at bind"
        win = f03._real_window()
        assert isinstance(win, QQuickWindow), win
        counts = {"after": 0, "swap": 0}

        def _a():
            counts["after"] += 1

        def _s():
            counts["swap"] += 1

        win.afterRendering.connect(_a)
        win.frameSwapped.connect(_s)
        gui.tier["arm"] = "FRAME_WINDOW_REAL"
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        gui.bind_frame_window(win)
        assert gui._frame_bridge._window is win, "the real window must be bound"
        return win, counts, int(gui._frame_bridge._generation)

    def _rebind_for_activation():
        """The ONLY rebind point: ACTIVATE with NO live gate. A publication gate
        that is already live is never dropped."""
        if store._seat_lifecycle != SEAT_ACTIVATE:
            return
        if gui._frame_bridge.has_live_gate():
            return
        if gui._frame_bridge._window is driven:
            return
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        gui.bind_frame_window(driven)

    store.seatLifecycleChanged.connect(_rebind_for_activation)

    def _settle():
        """Consume the seat transition of ONE packet: a cross-seat handoff goes
        through the REAL 「接管」 intent; every later gate is driven by the same
        signal pair on the unmodified bridge."""
        for _ in range(8):
            if store._seat_lifecycle == SEAT_ACTIVE:
                return
            if store._seat_lifecycle == SEAT_MASKED_PENDING:
                assert gui._frame_bridge.has_live_gate() is False, \
                    "a pending seat must not hold a live gate"
                gui.bind_frame_window(driven)
                takeover = store.requestTakeover()
                assert takeover.get("accepted") is True, takeover
            driven.render()
            f03._pump(2, 3)
        raise AssertionError("seat never became ACTIVE: %r"
                             % (store._seat_lifecycle,))

    def _packet(pkt_id, step, command, invoke):
        actor = store._viewer_id
        scope = book.scopes["senate"].scope_id if "senate" in book.scopes else ""
        ballots_before = len(ballots)
        win, counts, bind_gen = _bind_real()
        current["id"], current["command"] = pkt_id, command
        result = invoke()
        gate = dict(store._async_gate or {})
        txn = str(gate.get("txn_id") or "")
        current["txn"] = txn
        gen_begin = int(gui._frame_bridge._generation)
        assert txn, (pkt_id, gate)
        assert gate.get("kind") == "arm", (pkt_id, gate)
        first = [g for g in gui.gate_log if g["txn"] == txn][0]
        assert f03._pump_until(lambda: first["ok"] is not None, win=win), \
            "%s: no REAL frame for the first gate" % pkt_id
        # the FIRST gate of THIS txn: real window, real double signal, frozen
        # generation, its own receipt -- asserted at begin/complete time.
        assert first["kind"] == "arm", first
        assert first["tier"] == "FRAME_WINDOW_REAL", first
        assert first["ok"] is True, first
        assert first["receipt"] == (txn, "arm"), first
        assert first["generation"] == gen_begin, (first, gen_begin)
        assert counts["after"] >= 1 and counts["swap"] >= 1, counts
        ack = (store._query_invalidation_ack, store.queryInvalidationEpoch)
        _emit("GATE", chain="C2", packet=pkt_id, owning_txn=txn, gate_index=0,
              kind=first["kind"], tier=first["tier"], ok=first["ok"],
              generation_at_begin=gen_begin,
              generation_recorded=first["generation"],
              source_id=id(win), source_qt_type=win.metaObject().className(),
              after_signals=counts["after"], swap_signals=counts["swap"],
              receipt=first["receipt"], qml_ack=ack,
              result_pending=bool((result.get("data") or {}).get("pending")))
        _settle()

        rows = [dict(g) for g in gui.gate_log if g["txn"] == txn]
        for idx, row in enumerate(rows):
            gate_rows.append(row)
            if idx:
                _emit("GATE", chain="C2", packet=pkt_id, owning_txn=txn,
                      gate_index=idx, kind=row["kind"], tier=row["tier"],
                      ok=row["ok"], generation=row["generation"],
                      receipt=row["receipt"])
        receipt = store._committed_receipt or {}
        rdata = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
        delivery = rdata.get("delivery") if isinstance(rdata.get("delivery"), dict) \
            else None
        record = {
            "packet": pkt_id, "step": step, "actor": actor, "owning_txn": txn,
            "scope": scope, "command": command,
            "accepted": bool(receipt.get("success")),
            "delivery": delivery,
            "created": list(rdata.get("created") or []),
            "gates": [(g["kind"], g["tier"], g["ok"]) for g in rows],
            "ballots": ballots[ballots_before:],
            "first_bind_generation": bind_gen,
            "first_generation": gen_begin,
        }
        packets.append(record)
        _emit("PACKET", chain="C2", packet=pkt_id, step=step, actor=actor,
              owning_txn=txn, scope=scope, command=command,
              accepted=record["accepted"], gates=record["gates"],
              ballots=[(b["proposal"], b["actor"]) for b in record["ballots"]])
        current["id"], current["command"], current["txn"] = "", "", ""
        return record

    for _p in patchers:
        _p.start()
    try:
        registered = session_access.is_hotseat_registered(state)
        # the startup takeover is its OWN identity (a CONTROL, never a packet)
        startup_txn = str((store._seat_txn or {}).get("txn_id") or "")
        current["id"], current["txn"] = "CONTROL", startup_txn
        f03._takeover_driven(shell)             # CONTROL: startup takeover (driven)
        current["id"], current["txn"] = "", ""
        _emit("CHAIN", chain="C2", registered=registered,
              control_txn=startup_txn,
              startup_viewer=store._viewer_id, turn=state.turn.turn_number,
              players=[p.player_id for p in state.get_all_players()])

        # P1 — the population ENTRY (p1) -> cross-seat pending for p2 (consul)
        _packet("P1", "entry", "advancePopulation",
                lambda: store.doAdvancePopulation())
        assert "senate" in book.scopes, book.scopes
        entry_receipt = str(book.entries[-1]["receipt_id"]) if book.entries else ""
        scope_id = book.scopes["senate"].scope_id
        assert entry_receipt and scope_id, (entry_receipt, scope_id)

        # P2 — the REAL consul seat (p2) registers TWO real proposals
        store._refresh_senate_view()
        assert store._senate_view.get("current_step") == "proposal", \
            store._senate_view
        assert store.canCreateSenateProposal is True, store._senate_view
        proposals_before = {int(p["id"]) for p in state.get_senate_proposals()}
        p2 = _packet("P2", "proposal", "doSubmitSenateProposals",
                     lambda: store.doSubmitSenateProposals(
                         [dict(r) for r in _C2_ROWS]))
        created = sorted(int(c["proposal_id"]) for c in p2["created"]
                         if c.get("proposal_id") is not None)
        assert len(created) == 2 and len(set(created)) == 2, created
        registered_ids = {int(p["id"]) for p in state.get_senate_proposals()}
        assert set(created) <= registered_ids, (created, registered_ids)
        assert set(created).isdisjoint(proposals_before), (created, proposals_before)
        pids = created

        # P3..P5 — the 2 x 3 ballot matrix: ONE packet per player, BOTH ballots
        for idx in range(3):
            store._refresh_senate_view()
            view = dict(store._senate_view)
            assert view.get("current_step") == "senate_vote", view
            ids = sorted(int(s["id"]) for s in (view.get("submitted_proposals")
                                                or []))
            assert ids == pids, (ids, pids)
            _packet("P%d" % (3 + idx), "senate_vote", "doSubmitSenateVotes",
                    lambda ids=ids: store.doSubmitSenateVotes(ids))

        # the 2 x 3 matrix is COMPLETE before the terminal decision is taken
        readiness = session_turn_service.senate_readiness(state)
        _emit("BALLOTS", chain="C2", readiness=readiness,
              veto_actor=readiness.get("veto_actor"),
              veto_officer=readiness.get("veto_officer_id"))
        assert readiness["required"] == 6, readiness
        assert readiness["covered"] == 6, readiness
        assert readiness["all_ballots_ready"] is True, readiness
        assert readiness["decision_complete"] is True, readiness
        assert readiness["veto_required"] is True, readiness
        assert readiness["veto_satisfied"] is False, readiness

        # P6 — the REAL tribune veto closes the ballot phase
        store._refresh_senate_view()
        assert store._senate_view.get("current_step") == "tribune_veto", \
            store._senate_view
        _packet("P6", "tribune_veto", "doSubmitSenateVetoes",
                lambda: store.doSubmitSenateVetoes([pids[0]]))

        # ---- C2-A: ONE registered state/book/scope, TWO real proposal ids ---
        assert registered is True
        assert book.scopes["senate"].scope_id == scope_id
        assert len({p["owning_txn"] for p in packets}) == len(packets) == 6
        assert [p["step"] for p in packets] == [
            "entry", "proposal", "senate_vote", "senate_vote", "senate_vote",
            "tribune_veto"], [p["step"] for p in packets]
        assert [p["actor"] for p in packets] == [
            "player1", "player2", "player1", "player2", "player3", "player1"], \
            [p["actor"] for p in packets]
        assert all(p["accepted"] for p in packets), packets

        # ---- C2-C: EXACTLY ONE continuation per accepted packet -------------
        for p in packets:
            hits = [c for c in conts if c["packet"] == p["packet"]]
            _emit("CONT", packet=p["packet"], command=p["command"],
                  enter_index=(hits[0]["enter_index"] if hits else None),
                  exit_index=(hits[-1]["exit_index"] if hits else None),
                  outer_call_count=len(hits),
                  result=(hits[0]["status"] if hits else "MISSING"))
            assert len(hits) == 1, (p["packet"], hits)
            assert hits[0]["status"] != session_turn_service.STATUS_FAILURE, hits
        assert len(conts) == len(packets), (len(conts), len(packets))

        # ---- C2-B: 2 proposals x 3 players, exactly ONE real write per key --
        expected_keys = {(pid, actor) for pid in pids
                         for actor in ("player1", "player2", "player3")}
        counts_by_key = {}
        for b in ballots:
            key = (b["proposal"], b["actor"])
            counts_by_key[key] = counts_by_key.get(key, 0) + 1
        assert set(counts_by_key) == expected_keys, (counts_by_key, expected_keys)
        assert all(v == 1 for v in counts_by_key.values()), counts_by_key
        for p in packets:
            if p["step"] != "senate_vote":
                continue
            keys = [(b["proposal"], b["actor"]) for b in p["ballots"]]
            assert sorted(keys) == sorted((pid, p["actor"]) for pid in pids), \
                (p["packet"], keys)
            assert all(b["txn"] == p["owning_txn"] for b in p["ballots"]), \
                p["ballots"]
        _emit("BALLOT_KEYS", chain="C2", keys=sorted(counts_by_key),
              per_key_counts=counts_by_key)

        # ---- C2-E: EVERY new owning txn's FIRST gate is REAL ----------------
        for p in packets:
            kinds = [k for k, _t, _o in p["gates"]]
            assert kinds[0] == "arm", (p["packet"], kinds)
            assert kinds in (["arm"], ["arm", "publish", "unmask"]), \
                (p["packet"], kinds)
            assert p["gates"][0][1] == "FRAME_WINDOW_REAL", p["gates"]
            assert p["gates"][0][2] is True, p["gates"]
            assert all(t == "FRAME_BRIDGE_DRIVEN" and o is True
                       for _k, t, o in p["gates"][1:]), p["gates"]
        for row in gate_rows:
            assert row["ok"] is True, row
            assert row["receipt"] == (row["txn"], row["kind"]), row
        gens = [row["generation"] for row in gate_rows]
        assert gens == sorted(gens) and len(set(gens)) == len(gens), gens

        # ---- C2-F: ordering / isolation of every visibility commit ----------
        _emit("VISIBILITY", applies=len(applies), handles=len(handles),
              applies_neutral=all(a["public_viewer"] == "" and a["snapshot_empty"]
                                  for a in applies),
              publish_before_apply=all(a["publish_ok"] for a in applies),
              unmask_before_handle=all(h["unmask_ok"] for h in handles))
        assert applies and len(applies) == len(handles), (applies, handles)
        assert all(a["publish_ok"] and a["unmask_ok"] for a in applies), applies
        assert all(a["public_viewer"] == "" and a["snapshot_empty"]
                   for a in applies), applies
        assert all(h["unmask_ok"] for h in handles), handles

        # ---- C2-G: the REAL senate terminal (no test-side finalize) ---------
        last = packets[-1]["delivery"] or {}
        assert last.get("outcome") == "RESOLVED", last
        terminal = last.get("terminal") or {}
        result_owner = terminal.get("actor")
        assert terminal.get("status") == "resolved", terminal
        assert terminal.get("phase") == "senate", terminal
        assert result_owner == "player1", terminal
        assert last["next"]["actor_player_id"] == result_owner, last["next"]
        assert last["scope_id"] == scope_id, last
        canonical = senate_api.canonical_finalization(
            state, expected_scope=last["scope_id"], claimed_terminal=terminal)
        facts = canonical.get("facts") or {}
        _emit("TERMINAL", chain="C2",
              same_scope=bool(last.get("scope_id") == scope_id),
              finalization_id=terminal.get("finalization_id"),
              canonical_status=canonical.get("status"),
              completion_facts=facts, result_owner=result_owner,
              next_actor=(last.get("next") or {}).get("actor_player_id"),
              next_controller=(last.get("next") or {}).get("controller"),
              phase_result=bool(state.get_phase_result("senate") is not None))
        assert canonical.get("status") == "VALID", canonical
        assert facts and all(facts.values()), facts
        assert state.get_phase_result("senate") is not None

        # ---- zero after_commit / zero retry across the WHOLE chain ----------
        _emit("FAILURES", failed_masks=failures, retries=retries,
              after_commit=sum(1 for f in failures if f[0] == "after_commit"))
        assert failures == [], failures
        assert retries == [], retries
        _emit("SUMMARY", chain="C2", packets=len(packets),
              txns=len({p["owning_txn"] for p in packets}),
              gates=len(gate_rows), continuations=len(conts),
              ballots=len(ballots), proposals=pids, scope=scope_id,
              entry_receipt=entry_receipt, result_owner=result_owner,
              facts=facts, lifecycle=store._seat_lifecycle)
        _flush()
    finally:
        for _p in patchers:
            _p.stop()
        _flush()


# ===========================================================================
# C3 (SA Disposition-W3-G5-3 §2 C3 / AC-W3-04 + AC-W3-18) — the REAL senate
# submit CONTROL chain
#
#   The submit is NOT a Python Slot call: a REAL mouse event is delivered to the
#   production ``senateProposalSubmitButton`` MouseArea, whose OWN binding
#   (``enabled`` = the original composite expression) is read back together with
#   its four raw inputs; the click starts the owning transaction (arm gate), and
#   only after that receipt does the real Adapter reach ``propose_many`` and
#   return an accepted owner receipt. A paired negative control removes ONLY the
#   capability key at the read boundary: the real card / button lose the
#   capability and the same click dispatches NOTHING.
# ===========================================================================
_UI_ENABLED_EXPR = ("(sessionStore.canCreateSenateProposal"
                    " || sessionStore.canTriggerAIProposer)"
                    " && !root.hasZeroValueLandSelection()"
                    " && !sessionStore.senateAiProposerBlocked")


def _qml_eval(scope, text):
    """Evaluate QML text in the scope object's OWN component context."""
    from PySide6.QtQml import QQmlEngine, QQmlExpression
    expr = QQmlExpression(QQmlEngine.contextForObject(scope), scope, text)
    value = expr.evaluate()
    if isinstance(value, tuple):
        value = value[0]
    assert not expr.hasError(), expr.error().toString()
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value


def test_ac_w3_04_senate_submit_control_chain_is_real():
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtTest import QTest
    from src.core.entities.war import War, WarStatus, WarType
    from src.tests.test_gui import test_w3_delivery_authority as f03

    trace = []

    def _emit(tag, **fields):
        line = tag + " " + " ".join("%s=%r" % (k, v)
                                    for k, v in fields.items())
        trace.append(line)
        print(line)
        path = os.environ.get("EOR_W3_C3_TRACE", "")
        if path:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    state = _chain_state(humans=3)

    # a REAL active war -> a REAL WarProposalCard in the consul's proposal step
    war = War(id="war-c3", name="C3 Border War", war_type=WarType.PROVINCIAL,
              strength=5, threat_level=5, naval_required=False)
    war.status = WarStatus.ACTIVE
    _emit("WAR_REGISTER",
          ok=state._war_system.register_rebellion_war(war))

    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    f03._takeover_driven(shell)

    # ---- H1: ONE fresh real QQuickWindow per masked owning transaction ------
    gates = _w3_real_gate.RealGateHarness(shell, label="AC04")
    gates.auto_driven_tail()

    # p1 entry -> cross-seat pending for the HUMAN consul (p2) -> REAL takeover
    gates.arm_real()
    store.doAdvancePopulation()
    entry_txn = str((store._async_gate or {}).get("txn_id") or "")
    entry_generation = gates.generation()
    entry_first = gates.claim_first(entry_txn,
                                    begin_generation=entry_generation)
    _emit("GATE", packet="entry", owning_txn=entry_txn,
          kind=entry_first["kind"], tier=entry_first["tier"],
          ok=entry_first["ok"], generation=entry_first["generation"],
          generation_at_begin=entry_generation,
          receipt=entry_first["receipt"],
          after_signals=entry_first["after_signals"],
          swap_signals=entry_first["swap_signals"],
          source_type=entry_first["source"],
          source_id=entry_first["source_id"])
    assert store._pending_player_id == "player2", store._pending_player_id
    takeover_txn = (store._seat_txn or {}).get("txn_id", "")
    assert store.requestTakeover()["accepted"] is True
    driven.render()
    driven.render()
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    f03._pump(8, 5)
    for tail in gates.assert_tail_driven(entry_txn):
        _emit("GATE", packet="entry", owning_txn=entry_txn,
              kind=tail["kind"], tier=tail["tier"], ok=tail["ok"],
              generation=tail["generation"], receipt=tail["receipt"])
    gates.record_tail(entry_txn)

    # the normal read refresh publishes the consul's card set to the live tree
    store._refresh_senate_view()
    f03._pump(8, 5)

    stage = shell.window.findChild(QObject, "senateStage")
    button = shell.window.findChild(QObject, "senateProposalSubmitButton")
    assert stage is not None and button is not None, (stage, button)
    _emit("CONTROL", object_name=button.objectName(),
          qt_type=button.metaObject().className(),
          parents=[(o.objectName() or o.metaObject().className())
                   for o in (button.parent(), button.parent().parent(),
                             button.parent().parent().parent(), stage)],
          window=(shell.window.width(), shell.window.height()))

    # ---- AC-W3-18: the four RAW inputs, read from the real QML tree ---------
    assert store.senateCurrentStep == "proposal", store.senateCurrentStep
    assert store._senate_view.get("can_create_proposal") is True
    assert store.canCreateSenateProposal is True
    inputs = {
        "canCreate": bool(store.canCreateSenateProposal),
        "canTriggerAI": bool(store.canTriggerAIProposer),
        "zeroLand": bool(_qml_eval(button, "root.hasZeroValueLandSelection()")),
        "aiBlocked": bool(store.senateAiProposerBlocked),
    }
    composite = bool(_qml_eval(button, _UI_ENABLED_EXPR))
    enabled = bool(button.property("enabled"))
    _emit("INPUTS", **dict(inputs, composite=composite, button_enabled=enabled,
                           expr=_UI_ENABLED_EXPR))
    assert inputs == {"canCreate": True, "canTriggerAI": False,
                      "zeroLand": False, "aiBlocked": False}, inputs
    assert composite is True
    assert enabled == composite

    # ---- AC-W3-18: the REAL card instances (walked inside the live QML tree)
    card_walk = ("(function(){"
                 "  var out = [];"
                 "  function walk(it){"
                 "    if (!it) return;"
                 "    if (it.warId !== undefined && it.card !== undefined)"
                 "      out.push({warId: String(it.warId),"
                 "                editable: !!it.editable});"
                 "    var ch = it.children || [];"
                 "    for (var i = 0; i < ch.length; i++) walk(ch[i]);"
                 "  }"
                 "  walk(root);"
                 "  return out;"
                 "})()")
    card_rows = _qml_eval(button, card_walk)
    _emit("CARDS", count=len(card_rows or []), rows=card_rows,
          store_war_cards=len(store.senateWarCards or []),
          dto_war_cards=[c.get("war_id") for c in (
              store._senate_view.get("war_cards") or [])],
          step=_qml_eval(button, "sessionStore.senateCurrentStep"))
    assert card_rows, "no real WarProposalCard instance in the live tree"
    assert all(r["editable"] is True for r in card_rows), card_rows
    assert all(r["editable"] == bool(store.canCreateSenateProposal)
               for r in card_rows), card_rows

    # ---- AC-W3-18 negative: capability key removed at the read boundary -----
    real_view = senate_api.get_senate_view

    def _drop_capability(*a, **k):
        feedback = real_view(*a, **k)
        data = (feedback or {}).get("data")
        if isinstance(data, dict):
            data.pop("can_create_proposal", None)
        return feedback

    calls = []
    real_submit = store._adapter.submit_senate_proposals

    def _submit_spy(*a, **k):
        calls.append((a, k))
        return real_submit(*a, **k)

    point = button.mapToScene(QPointF(float(button.property("width")) / 2.0,
                                      float(button.property("height")) / 2.0))

    with patch.object(senate_api, "get_senate_view", side_effect=_drop_capability):
        store._refresh_senate_view()
        f03._pump(6, 5)
    _emit("NEGATIVE_VIEW", dto_key="can_create_proposal" in store._senate_view,
          store_property=store.canCreateSenateProposal,
          button_enabled=button.property("enabled"),
          card_editable=[r["editable"] for r in (_qml_eval(button, card_walk) or [])])
    assert store.canCreateSenateProposal is False
    assert bool(button.property("enabled")) is False
    assert all(r["editable"] is False
               for r in (_qml_eval(button, card_walk) or []))

    gates_before = len(gui.gate_log)
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=_submit_spy):
        QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point.toPoint())
        f03._pump(3, 5)
        _emit("NEGATIVE_CLICK", adapter_calls=len(calls),
              new_gates=len(gui.gate_log) - gates_before)
        assert calls == [], calls
        assert len(gui.gate_log) == gates_before

        # ---- restore the REAL published capability (same chain) -------------
        store._refresh_senate_view()
        f03._pump(6, 5)
        assert store.canCreateSenateProposal is True
        assert bool(button.property("enabled")) is True
        assert bool(button.property("enabled")) == bool(
            _qml_eval(button, _UI_ENABLED_EXPR))
        assert all(r["editable"] is True
                   for r in (_qml_eval(button, card_walk) or []))

        # ---- AC-W3-04: the REAL control click owns the transaction ----------
        ordering = gates.watch_dispatch_ordering(lambda: len(calls))
        gates.arm_real()              # the submit txn's OWN fresh real window
        gates_before = len(gui.gate_log)
        QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point.toPoint())
        started = gui.gate_log[gates_before:]
        _emit("CLICK", new_gates=[(g["kind"], g["txn"]) for g in started],
              adapter_calls=len(calls),
              gate=dict(store._async_gate) if store._async_gate else None,
              seat=store.seatLifecycle)
        assert len(started) == 1, started
        assert started[0]["kind"] == "arm"
        owning_txn = started[0]["txn"]
        assert owning_txn and owning_txn != takeover_txn
        # the owning dispatch may NOT run before the arm receipt: the count is
        # sampled exactly at the receipt delivery, before the Store resumes.
        assert ordering and ordering[-1]["txn"] == owning_txn, ordering
        assert ordering[-1]["kind"] == "arm", ordering
        assert ordering[-1]["dispatch_before_receipt"] == 0, ordering
        assert store.seatLifecycle not in (SEAT_ACTIVE,), store.seatLifecycle

        submit_generation = gates.generation()
        submit_first = gates.claim_first(owning_txn,
                                         begin_generation=submit_generation)
        _emit("GATE", packet="submit", owning_txn=owning_txn,
              kind=submit_first["kind"], tier=submit_first["tier"],
              ok=submit_first["ok"], generation=submit_first["generation"],
              generation_at_begin=submit_generation,
              receipt=submit_first["receipt"],
              after_signals=submit_first["after_signals"],
              swap_signals=submit_first["swap_signals"],
              source_type=submit_first["source"],
              source_id=submit_first["source_id"])

        driven.render()
        f03._pump(4, 5)

    _emit("COMMIT", adapter_calls=len(calls),
          rows=list(calls[0][0][0]) if calls else None,
          success=(store._committed_receipt or {}).get("success"),
          seat=store.seatLifecycle, viewer=store.viewerPlayerId,
          step=store.senateCurrentStep,
          proposals=[p.get("id") for p in state.get_senate_proposals()])

    # exactly ONE owning dispatch, carrying the payload the CONTROL produced
    assert len(calls) == 1, calls
    rows_arg = calls[0][0][1] if len(calls[0][0]) > 1 else calls[0][1].get("rows")
    _emit("PAYLOAD", arity=len(calls[0][0]), rows=rows_arg)
    receipt = store._committed_receipt or {}
    assert receipt.get("success") is True, receipt
    delivery = (receipt.get("data") or {}).get("delivery") or {}
    assert delivery.get("outcome") == "CONTINUE", delivery
    assert delivery["next"]["actor_player_id"] == "player1", delivery
    # the real propose_many really registered the package the card produced
    assert state.get_senate_proposals(), "propose_many registered nothing"
    for tail in gates.assert_tail_driven(owning_txn):
        _emit("GATE", packet="submit", owning_txn=owning_txn,
              kind=tail["kind"], tier=tail["tier"], ok=tail["ok"],
              generation=tail["generation"], receipt=tail["receipt"])
    gates.record_tail(owning_txn)
    _emit("SUMMARY", UI_CLICK_REACHABLE=True, owning_txn=owning_txn,
          takeover_txn=takeover_txn, outcome=delivery.get("outcome"),
          cards=len(card_rows), expr_matched=True, negative_zero_dispatch=True,
          proposals=[p.get("id") for p in state.get_senate_proposals()])


# ===========================================================================
# GRANULARITY — the SAME registered two-proposal chain, ONE run, collecting the
# three fields C2 left UNPROVEN (Disposition-W3-G5-3 §2.C2.3 / task brief §1):
#   1. PACKET.head_oid_before = the REAL queue head read at packet entry;
#   2. the owner completion identity of all six (proposal, actor) ballots;
#   3. VISIBILITY.epoch + authority at every activation / publication.
# The chain construction is C2's (real QQuickWindow first gate per owning txn),
# so the collected fields belong to the same execution that proved C2.
# ===========================================================================
def test_ac_w3_05_packet_granularity_same_chain():
    from PySide6.QtQuick import QQuickWindow
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=3)
    book = session_turn_service._book(state)
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven

    trace = []
    flushed = {"done": False}

    def _emit(tag, **fields):
        trace.append(tag + " " + " ".join("%s=%r" % (k, v)
                                          for k, v in fields.items()))

    def _flush():
        if flushed["done"]:
            return
        flushed["done"] = True
        text = "\n".join(trace) + "\n"
        print(text)
        out = os.environ.get("EOR_W3_GRAN_TRACE", "")
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text)

    packets, ballots, applies, conts = [], [], [], []
    failures, retries = [], []
    current = {"id": "", "command": "", "txn": ""}

    real_fail = store._fail_masked
    real_apply = store._apply_staged
    real_vote = state.record_senate_vote
    real_cont = session_turn_service.continue_after_command

    def _gates_ok(kind, txn=None):
        return any(g["kind"] == kind and g["ok"] is True
                   and (txn is None or g["txn"] == txn) for g in gui.gate_log)

    def _head(phase):
        """REAL read: the first outstanding obligation of the phase schedule."""
        snap = session_turn_service.obligations(state, phase)
        out = snap.outstanding()
        return {"phase": phase, "count": len(out),
                "head_oid": str(out[0].obligation_id) if out else "",
                "head_actor": (out[0].actor_player_id if out else None),
                "head_substep": (out[0].substep if out else ""),
                "head_slot": (str(out[0].actor_slot) if out else ""),
                "oids": [str(o.obligation_id) for o in out],
                "errors": list(snap.errors)}

    def _receipt_for(command):
        alias = {"advancePopulation": "advance_population_phase",
                 "doSubmitSenateProposals": "propose_many",
                 "doSubmitSenateVotes": "senate_vote",
                 "doSubmitSenateVetoes": "senate_veto_decision"}
        want = alias.get(command, command)
        for ref, rec in book.committed_facts.items():
            if rec.get("command") == want:
                return str(ref), str(rec.get("receipt_id") or "")
        return "", ""

    def _completion_snapshot():
        """H1-5: the REAL post-packet completion state.

        Read AFTER the packet: the phase schedule's own obligation rows (with
        their own ``satisfied`` flag) plus the book's completion RECORDS. This is
        the authority a ballot's completion may be read from; the pre-packet
        queue head is never a completion source.
        """
        snap = session_turn_service.obligations(state, "senate")
        obligations = [{"oid": str(o.obligation_id),
                        "substep": o.substep,
                        "actor": o.actor_player_id,
                        "satisfied": bool(o.satisfied)}
                       for o in snap.obligations]
        records = [{"command_id": str(rec.command_id),
                    "oid": str(rec.obligation_id),
                    "kind": str(rec.satisfied_kind),
                    "fact_ref": str(rec.authoritative_fact_ref),
                    "entry_revision": int(rec.entry_revision),
                    "satisfied_at_revision": int(rec.satisfied_at_revision)}
                   for rec in book.records]
        return {"obligations": obligations, "records": records}

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    def _apply_spy(staged, target_id=None):
        applies.append({
            "txn": current["txn"], "packet": current["id"],
            "seat_epoch": int(store.seatEpoch),
            "core_principal": (state.get_current_player().player_id
                               if state.get_current_player() else None),
            "lease_id": str((store._seat_txn or {}).get("lease_id") or ""),
            "txn_seat_epoch": int((store._seat_txn or {}).get("seat_epoch") or 0),
            "viewer_private": store._viewer_id,
            "public_viewer": store.viewerPlayerId,
            "snapshot_empty": store._snapshot == {},
            "publish_ok": _gates_ok("publish", current["txn"]),
            "unmask_ok": _gates_ok("unmask", current["txn"]),
        })
        return real_apply(staged, target_id=target_id)

    def _vote_spy(actor, proposal_id, approve, *a, **k):
        before = len(book.receipts)
        result = real_vote(actor, proposal_id, approve, *a, **k)
        ballots.append({"packet": current["id"], "actor": actor,
                        "proposal": int(proposal_id),
                        "approve": bool(approve), "txn": current["txn"],
                        "new_receipts": len(book.receipts) - before,
                        "votes_after": dict(state.get_senate_votes_copy() or {})})
        return result

    def _cont_spy(*a, **k):
        result = real_cont(*a, **k)
        rows = []
        for rec in list(book.records):
            rows.append({"command_id": rec.command_id,
                         "obligation_id": str(rec.obligation_id),
                         "fact_ref": rec.authoritative_fact_ref,
                         "kind": rec.satisfied_kind,
                         "entry_revision": int(rec.entry_revision),
                         "satisfied_at_revision": int(rec.satisfied_at_revision)})
        conts.append({"packet": current["id"], "status": getattr(result, "status", ""),
                      "records": rows,
                      "seat_epoch": int(store.seatEpoch),
                      "core_principal": (state.get_current_player().player_id
                                         if state.get_current_player() else None)})
        return result

    patchers = [
        patch.object(store, "_fail_masked", side_effect=_fail_spy),
        patch.object(store, "retryHandoff",
                     side_effect=lambda *a, **k: retries.append(1)),
        patch.object(store, "_apply_staged", side_effect=_apply_spy),
        patch.object(state, "record_senate_vote", side_effect=_vote_spy),
        patch.object(session_turn_service, "continue_after_command",
                     side_effect=_cont_spy),
    ]

    def _bind_real():
        """Bind a NOT-yet-consumed REAL window for the txn's FIRST gate only."""
        assert gui._frame_bridge.has_live_gate() is False, "live gate at bind"
        win = f03._real_window()
        assert isinstance(win, QQuickWindow), win
        counts = {"after": 0, "swap": 0}
        win.afterRendering.connect(lambda: counts.__setitem__("after", counts["after"] + 1))
        win.frameSwapped.connect(lambda: counts.__setitem__("swap", counts["swap"] + 1))
        gui.tier["arm"] = "FRAME_WINDOW_REAL"
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        gui.bind_frame_window(win)
        assert gui._frame_bridge._window is win, "the real window must be bound"
        return win, counts, int(gui._frame_bridge._generation)

    def _rebind_for_activation():
        if store._seat_lifecycle != SEAT_ACTIVATE:
            return
        if gui._frame_bridge.has_live_gate():
            return
        if gui._frame_bridge._window is driven:
            return
        gui.tier["publish"] = "FRAME_BRIDGE_DRIVEN"
        gui.tier["unmask"] = "FRAME_BRIDGE_DRIVEN"
        gui.bind_frame_window(driven)

    store.seatLifecycleChanged.connect(_rebind_for_activation)

    def _settle():
        for _ in range(8):
            if store._seat_lifecycle == SEAT_ACTIVE:
                return
            if store._seat_lifecycle == SEAT_MASKED_PENDING:
                assert gui._frame_bridge.has_live_gate() is False, \
                    "a pending seat must not hold a live gate"
                gui.bind_frame_window(driven)
                takeover = store.requestTakeover()
                assert takeover.get("accepted") is True, takeover
            driven.render()
            f03._pump(2, 3)
        raise AssertionError("seat never became ACTIVE: %r"
                             % (store._seat_lifecycle,))

    def _packet(pkt_id, step, command, invoke, head_phase):
        actor = store._viewer_id
        scope = book.scopes["senate"].scope_id if "senate" in book.scopes else ""
        head = _head(head_phase)
        assert head["head_oid"], (pkt_id, head)
        ballots_before = len(ballots)
        win, counts, bind_gen = _bind_real()
        current["id"], current["command"] = pkt_id, command
        result = invoke()
        gate = dict(store._async_gate or {})
        txn = str(gate.get("txn_id") or "")
        current["txn"] = txn
        assert txn, (pkt_id, gate)
        assert gate.get("kind") == "arm", (pkt_id, gate)
        first = [g for g in gui.gate_log if g["txn"] == txn][0]
        assert f03._pump_until(lambda: first["ok"] is not None, win=win), \
            "%s: no REAL frame for the first gate" % pkt_id
        assert first["tier"] == "FRAME_WINDOW_REAL" and first["ok"] is True, first
        assert first["receipt"] == (txn, "arm"), first
        _settle()
        completion = _completion_snapshot()
        receipt = store._committed_receipt or {}
        rdata = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
        delivery = rdata.get("delivery") if isinstance(rdata.get("delivery"), dict) else None
        ref, rid = _receipt_for(command)
        record = {
            "packet": pkt_id, "step": step, "actor": actor, "owning_txn": txn,
            "scope": scope, "command": command,
            "accepted": bool(receipt.get("success")),
            "delivery": delivery, "created": list(rdata.get("created") or []),
            "head": head, "owner_receipt_ref": ref, "owner_receipt_id": rid,
            "completion": completion,
            "ballots": ballots[ballots_before:],
            "gates": [(g["kind"], g["tier"], g["ok"])
                      for g in gui.gate_log if g["txn"] == txn],
        }
        packets.append(record)
        _emit("PACKET", chain="GRAN", packet=pkt_id, source_slot=command,
              actor=actor, owning_txn=txn, scope=scope,
              head_phase=head["phase"], head_oid_before=head["head_oid"],
              head_actor=head["head_actor"], head_substep=head["head_substep"],
              head_count=head["count"], head_errors=head["errors"],
              accepted=record["accepted"], owner_receipt=rid,
              owner_receipt_ref=ref,
              created=[c.get("proposal_id") for c in record["created"]],
              ballot_keys=[(b["proposal"], b["actor"]) for b in record["ballots"]],
              gates=record["gates"])
        current["id"], current["command"], current["txn"] = "", "", ""
        return record

    for _p in patchers:
        _p.start()
    try:
        registered = session_access.is_hotseat_registered(state)
        startup_txn = str((store._seat_txn or {}).get("txn_id") or "")
        current["id"], current["txn"] = "CONTROL", startup_txn
        f03._takeover_driven(shell)
        current["id"], current["txn"] = "", ""
        _emit("CHAIN", chain="GRAN", registered=registered,
              control_txn=startup_txn, turn=state.turn.turn_number,
              players=[p.player_id for p in state.get_all_players()])

        _packet("P1", "entry", "advancePopulation",
                lambda: store.doAdvancePopulation(), "population")
        assert "senate" in book.scopes, book.scopes
        entry_receipt = str(book.entries[-1]["receipt_id"]) if book.entries else ""
        scope_id = book.scopes["senate"].scope_id
        assert entry_receipt and scope_id, (entry_receipt, scope_id)

        store._refresh_senate_view()
        assert store._senate_view.get("current_step") == "proposal", store._senate_view
        assert store.canCreateSenateProposal is True, store._senate_view
        proposals_before = {int(p["id"]) for p in state.get_senate_proposals()}
        p2 = _packet("P2", "proposal", "doSubmitSenateProposals",
                     lambda: store.doSubmitSenateProposals(
                         [dict(r) for r in _C2_ROWS]), "senate")
        created = sorted(int(c["proposal_id"]) for c in p2["created"]
                         if c.get("proposal_id") is not None)
        assert len(created) == 2 and len(set(created)) == 2, created
        pids = created
        registered_ids = {int(p["id"]) for p in state.get_senate_proposals()}
        assert set(created) <= registered_ids, (created, registered_ids)
        assert set(created).isdisjoint(proposals_before), (created, proposals_before)

        for idx in range(3):
            store._refresh_senate_view()
            view = dict(store._senate_view)
            assert view.get("current_step") == "senate_vote", view
            ids = sorted(int(s["id"]) for s in (view.get("submitted_proposals") or []))
            assert ids == pids, (ids, pids)
            _packet("P%d" % (3 + idx), "senate_vote", "doSubmitSenateVotes",
                    lambda ids=ids: store.doSubmitSenateVotes(ids), "senate")

        readiness = session_turn_service.senate_readiness(state)
        assert readiness["required"] == 6 and readiness["covered"] == 6, readiness
        assert readiness["all_ballots_ready"] is True, readiness
        assert readiness["veto_required"] is True, readiness
        assert readiness["veto_satisfied"] is False, readiness

        store._refresh_senate_view()
        assert store._senate_view.get("current_step") == "tribune_veto", store._senate_view
        _packet("P6", "tribune_veto", "doSubmitSenateVetoes",
                lambda: store.doSubmitSenateVetoes([pids[0]]), "senate")

        # ---- (1) per-packet real queue head + one owning txn per packet ------
        assert registered is True
        assert len({p["owning_txn"] for p in packets}) == len(packets) == 6
        for p in packets:
            assert p["accepted"], p
            assert p["head"]["head_oid"], p
        assert [p["step"] for p in packets] == [
            "entry", "proposal", "senate_vote", "senate_vote", "senate_vote",
            "tribune_veto"]
        assert [p["actor"] for p in packets] == [
            "player1", "player2", "player1", "player2", "player3", "player1"]

        # ---- (2) the six (proposal, actor) completions ------------------------
        pairs = [(b["proposal"], b["actor"]) for b in ballots]
        expected = {(pid, actor) for pid in pids
                    for actor in ("player1", "player2", "player3")}
        assert len(pairs) == 6 and set(pairs) == expected, pairs
        assert len(set(pairs)) == len(pairs), pairs
        assert all(b["txn"] == next(p["owning_txn"] for p in packets
                                     if p["packet"] == b["packet"])
                   for b in ballots), ballots

        last_records = conts[-1]["records"] if conts else []

        def _scheduled_vote(oid, proposal, actor):
            return (("'vote:%d'" % proposal) in oid) and (("'%s'" % actor) in oid)

        def _completion_for(pkt, proposal, actor):
            """H1-5: read the ballot's completion from the REAL post-packet state.

            Returns ``(obligation, completion_record)`` read AFTER the owning
            packet: the schedule's own obligation row and the book's completion
            record (if the product wrote one). The pre-packet queue head is never
            used as a completion source.
            """
            packet = next(p for p in packets if p["packet"] == pkt)
            snap = packet["completion"]
            obligation = next((o for o in snap["obligations"]
                               if _scheduled_vote(o["oid"], proposal, actor)), None)
            record_row = next((r for r in snap["records"]
                               if _scheduled_vote(r["oid"], proposal, actor)), None)
            return obligation, record_row

        ballot_rows = []
        for b in ballots:
            pkt = next(p for p in packets if p["packet"] == b["packet"])
            obligation, record_row = _completion_for(b["packet"], b["proposal"],
                                                     b["actor"])
            satisfied = bool(obligation and obligation["satisfied"])
            backed = bool(satisfied and record_row)
            ballot_rows.append({
                "key": (b["proposal"], b["actor"]), "txn": b["txn"],
                "packet": b["packet"],
                "satisfied": satisfied,
                "scheduled_oid": (obligation["oid"] if obligation else ""),
                # a COMPLETION oid is claimed only when the real schedule says
                # satisfied AND a real completion record backs it
                "satisfied_oid": (record_row["oid"] if backed else ""),
                "completion_annotation": (
                    "REAL_COMPLETION" if backed
                    else ("SCHEDULE_SATISFIED_NO_COMPLETION_RECORD" if satisfied
                          else "NOT_SATISFIED")),
                "completion_fact_ref": (record_row["fact_ref"] if record_row
                                        else ""),
                "completion_kind": (record_row["kind"] if record_row else ""),
                "packet_receipt": pkt["owner_receipt_id"],
                "packet_fact_ref": pkt["owner_receipt_ref"],
                "new_receipts_in_call": b["new_receipts"],
                "votes_after_keys": sorted((p, a) for p, d in
                                           (b["votes_after"] or {}).items()
                                           for a in (d or {})),
            })
            _emit("BALLOT", chain="GRAN", proposal=b["proposal"], actor=b["actor"],
                  owning_txn=b["txn"], satisfied=satisfied,
                  scheduled_oid=ballot_rows[-1]["scheduled_oid"],
                  satisfied_oid=ballot_rows[-1]["satisfied_oid"],
                  completion=ballot_rows[-1]["completion_annotation"],
                  completion_fact_ref=ballot_rows[-1]["completion_fact_ref"],
                  packet_receipt=ballot_rows[-1]["packet_receipt"],
                  fact_ref=ballot_rows[-1]["packet_fact_ref"],
                  new_receipts_in_call=b["new_receipts"],
                  approve=b["approve"])
        # every ballot identifies its OWN scheduled vote obligation and is really
        # satisfied in the post-packet schedule
        assert all(r["scheduled_oid"] for r in ballot_rows), ballot_rows
        assert len({r["scheduled_oid"] for r in ballot_rows}) == 6, ballot_rows
        assert all(r["satisfied"] for r in ballot_rows), ballot_rows
        # the per-ballot owner COMPLETION receipt is reported honestly
        not_collectible = [r["key"] for r in ballot_rows
                           if not r["satisfied_oid"]]
        _emit("BALLOT_COMPLETION", chain="GRAN",
              real_completion=sum(1 for r in ballot_rows
                                  if r["satisfied_oid"]),
              not_collectible=not_collectible,
              annotations=sorted(r["completion_annotation"]
                                 for r in ballot_rows),
              reason=("per-ballot owner completion receipt NOT_COLLECTIBLE: the "
                      "product records ONE receipt per vote packet (shared by its "
                      "ballots); the schedule row is the real completion "
                      "authority available for each ballot"))
        vote_receipts = {p["owner_receipt_id"] for p in packets
                         if p["step"] == "senate_vote"}
        _emit("BALLOT_RECEIPTS", chain="GRAN",
              distinct_senate_vote_receipts=sorted(vote_receipts),
              ballot_count=len(ballot_rows),
              per_ballot_new_receipts=[r["new_receipts_in_call"] for r in ballot_rows],
              ledger_records_per_continuation=[len(c["records"]) for c in conts],
              last_records=last_records)
        assert len(vote_receipts) == 1, vote_receipts

        # ---- (3) epoch + Core principal per activation/publication -----------
        assert applies and len(applies) == 7, applies
        for a in applies:
            _emit("VISIBILITY", chain="GRAN", packet=a["packet"],
                  owning_txn=a["txn"], seat_epoch=a["seat_epoch"],
                  txn_seat_epoch=a["txn_seat_epoch"],
                  authority=a["core_principal"], lease_id=a["lease_id"],
                  viewer_private=a["viewer_private"],
                  public_viewer=a["public_viewer"],
                  snapshot_empty=a["snapshot_empty"],
                  publish_ok=a["publish_ok"], unmask_ok=a["unmask_ok"])
        epochs = [a["seat_epoch"] for a in applies]
        assert epochs == sorted(epochs) and len(set(epochs)) == len(epochs), epochs
        assert all(a["publish_ok"] and a["unmask_ok"] for a in applies), applies
        assert all(a["public_viewer"] == "" and a["snapshot_empty"]
                   for a in applies), applies
        assert all(a["core_principal"] for a in applies), applies
        assert all(a["txn_seat_epoch"] == a["seat_epoch"] for a in applies
                   if a["packet"] != "CONTROL"), applies
        for c in conts:
            _emit("EPOCH", chain="GRAN", packet=c["packet"],
                  continuation_status=c["status"], seat_epoch=c["seat_epoch"],
                  authority=c["core_principal"])

        # ---- terminal + zero-error (unchanged C2 semantics) ------------------
        last = packets[-1]["delivery"] or {}
        assert last.get("outcome") == "RESOLVED", last
        terminal = last.get("terminal") or {}
        assert terminal.get("status") == "resolved", terminal
        assert last.get("scope_id") == scope_id, last
        canonical = senate_api.canonical_finalization(
            state, expected_scope=last["scope_id"], claimed_terminal=terminal)
        facts = canonical.get("facts") or {}
        assert canonical.get("status") == "VALID", canonical
        assert facts and all(facts.values()), facts
        assert state.get_phase_result("senate") is not None
        assert failures == [], failures
        assert retries == [], retries
        _emit("SUMMARY", chain="GRAN", packets=len(packets),
              txns=len({p["owning_txn"] for p in packets}),
              ballots=len(ballots), proposals=pids, scope=scope_id,
              entry_receipt=entry_receipt, terminal_status=terminal.get("status"),
              canonical=canonical.get("status"), facts=facts,
              result_owner=terminal.get("actor"),
              record_counts=[len(c["records"]) for c in conts],
              record_cmds=[[r["command_id"] for r in c["records"]] for c in conts],
              epochs=epochs, after_commit=sum(1 for f in failures
                                              if f[0] == "after_commit"))
        _flush()
    finally:
        for _p in patchers:
            _p.stop()
        _flush()


# ===========================================================================
# H2-b (AC-W3-05 ①② / AC-W3-18) — the REAL control interaction helpers
#
#   The card checkbox and the ``senateProposalSubmitButton`` MouseArea are the
#   PRODUCTION ones; nothing here writes a Store property to imitate a click.
# ===========================================================================
def _h2b_emit(tag, **fields):
    line = tag + " " + " ".join("%s=%r" % (k, v) for k, v in fields.items())
    print(line)
    path = os.environ.get("EOR_W3_H2B_TRACE", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _h2b_items(root):
    """Every live QQuickItem of a QML subtree (the real tree, never a copy)."""
    import shiboken6
    from PySide6.QtQuick import QQuickItem
    try:
        item = shiboken6.Shiboken.wrapInstance(
            shiboken6.Shiboken.getCppPointer(root)[0], QQuickItem)
    except Exception:
        return []
    pending, out = [item], []
    while pending:
        node = pending.pop()
        out.append(node)
        pending.extend(node.childItems())
    return out


def _h2b_bill_card(window, key):
    """The live bill card whose OWN ``billKey`` property is ``key``."""
    from PySide6.QtCore import QObject
    for obj in window.findChildren(QObject):
        try:
            value = obj.property("billKey")
        except Exception:
            continue
        if value is not None and str(value) == str(key):
            return obj
    return None


#: JS over the REAL stage tree: find the card by its OWN ``billKey`` and its OWN
#: CheckBox control (``toggle`` invokable + ``checked``) — the production items.
_H2B_WALK = ("(function(){var card=null,box=null;"
             "function fc(it){if(!it||card)return;"
             "if(it.billKey!==undefined&&String(it.billKey)===KEY){card=it;return;}"
             "var ch=it.children||[];for(var i=0;i<ch.length;i++)fc(ch[i]);}"
             "function fb(it){if(!it||box)return;"
             "if(typeof it.toggle==='function'&&it.checked!==undefined){box=it;return;}"
             "var ch=it.children||[];for(var i=0;i<ch.length;i++)fb(ch[i]);}"
             "fc(root);if(card)fb(card);")


def _h2b_card_probe(scope, key):
    """Read the live card/control truth of ``key`` from the REAL QML tree."""
    body = (_H2B_WALK + "return {card:!!card,box:!!box,"
            "checked:box?(box.checked===true):null,"
            "enabled:box?(box.enabled!==false):null,"
            "editable:card?(card.editable!==false):null};})()")
    value = _qml_eval(scope, body.replace("KEY", repr(str(key))))
    return dict(value or {})


def _h2b_card_box(scope, key):
    """The live CheckBox CONTROL object of the card ``key`` (or None)."""
    body = _H2B_WALK + "return box;})()"
    return _qml_eval(scope, body.replace("KEY", repr(str(key))))


def _h2b_card_toggle(scope, key):
    """Toggle the card's OWN control (its ``toggle()`` invokable)."""
    body = (_H2B_WALK + "if(!box)return 'NO_BOX';box.toggle();"
            "return (box.checked===true)?'CHECKED':'UNCHECKED';})()")
    return _qml_eval(scope, body.replace("KEY", repr(str(key))))


def _h2b_click(shell, item, *, pump=True):
    """A REAL mouse click at the item's own centre (never a property write)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    point = item.mapToScene(QPointF(float(item.property("width")) / 2.0,
                                    float(item.property("height")) / 2.0))
    QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, point.toPoint())
    if pump:
        QGuiApplication.processEvents()
        QTest.qWait(10)
        QGuiApplication.processEvents()
    return point


def _h2b_set_card(shell, scope, key, selected):
    """Select/deselect ONE bill card through its OWN CheckBox control.

    A REAL mouse click on the card's CheckBox is attempted first; when the
    offscreen viewport clips the card, the SAME control's own ``toggle()``
    invokable performs the interaction instead. The mechanism is returned so the
    evidence never claims a click it did not deliver.
    """
    from PySide6.QtGui import QGuiApplication
    probe = _h2b_card_probe(scope, key)
    assert probe.get("card") is True, "no live bill card for %r" % (key,)
    assert probe.get("box") is True, "no CheckBox control inside %r" % (key,)
    want = bool(selected)
    if bool(probe.get("checked")) == want:
        return "ALREADY"
    assert bool(probe.get("enabled")) is True, (key, probe)
    box = _h2b_card_box(scope, key)
    items = _h2b_items(box)
    assert items, "the control object is not a live item: %r" % (key,)
    _h2b_click(shell, items[0])
    mechanism = "MOUSE_CLICK"
    if bool(_h2b_card_probe(scope, key).get("checked")) != want:
        _h2b_card_toggle(scope, key)
        QGuiApplication.processEvents()
        mechanism = "CONTROL_TOGGLE"
    assert bool(_h2b_card_probe(scope, key).get("checked")) is want, \
        (key, _h2b_card_probe(scope, key))
    return mechanism


def _h2b_settle(shell, gates, driven, *, rounds=10):
    """Consume ONE seat transition through the production 「接管」 intent.

    A gate that is still live is drained on the driven pair FIRST (later gates
    are always driven); only a clean seat is taken over.
    """
    from src.tests.test_gui import test_w3_delivery_authority as f03
    store = shell.store
    for _ in range(rounds):
        if store._seat_lifecycle == SEAT_ACTIVE and gates.live_gate() is False:
            return True
        if gates.live_gate():
            driven.render()
            f03._pump(2, 3)
            continue
        if store._seat_lifecycle == SEAT_MASKED_PENDING:
            gates.bind_driven()
            takeover = store.requestTakeover()
            assert takeover.get("accepted") is True, takeover
        else:
            driven.render()
        f03._pump(2, 3)
    raise AssertionError("seat never became ACTIVE: %r" % (store._seat_lifecycle,))


def _h2b_click_owning(shell, gates, item):
    """A REAL control click that starts an owning txn; ``(txn, first_gate_row)``.

    ``QTest`` pumps the event loop inside the click, so the arm gate can already
    have been completed by the time the click returns: the transaction is read
    from the gate the click REALLY started (never assumed from ``_async_gate``).
    """
    gui = shell.gui
    before = len(gui.gate_log)
    gates.arm_real()
    _h2b_click(shell, item, pump=False)
    new_rows = gui.gate_log[before:]
    live = str((shell.store._async_gate or {}).get("txn_id") or "")
    txn = live or (str(new_rows[0]["txn"]) if new_rows else "")
    assert txn, ("the click started no owning transaction", new_rows)
    assert all(r["txn"] == txn for r in new_rows), new_rows
    assert new_rows[0]["kind"] == "arm", new_rows
    # the gate's OWN generation is read while IT is the live gate; when the click
    # already drove the chain past it, the receipt's frozen generation is used.
    live_kind = str((shell.store._async_gate or {}).get("kind") or "")
    gen_begin = gates.generation() if live_kind == "arm" else None
    row = gates.claim_first(txn, begin_generation=gen_begin)
    return txn, row


# ===========================================================================
# B-1 / B-2 (AC-W3-05 ①②) — TWO proposals registered by the REAL controls
# (card checkbox + ``senateProposalSubmitButton``) and carried through ONE
# chain; every cell's owner completion read from the REAL product facts.
# ===========================================================================
def test_ac_w3_05_two_proposals_from_the_real_controls_share_one_chain():
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=3)
    state._national_public_land = 1000          # real public land -> real drafts
    book = session_turn_service._book(state)
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label="AC05-controls")
    gates.auto_driven_tail()

    failures, retries, conts, packets, ballots = [], [], [], [], []
    mechanisms = []
    current = {"id": "", "command": "", "txn": ""}

    real_fail = store._fail_masked
    real_vote = state.record_senate_vote
    real_cont = session_turn_service.continue_after_command

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    def _cont_spy(*a, **k):
        result = real_cont(*a, **k)
        conts.append({"packet": current["id"], "command": current["command"],
                      "status": getattr(result, "status", "")})
        return result

    def _vote_spy(actor, proposal_id, approve, *a, **k):
        before = len(book.receipts)
        result = real_vote(actor, proposal_id, approve, *a, **k)
        ballots.append({"packet": current["id"], "actor": actor,
                        "proposal": int(proposal_id), "approve": bool(approve),
                        "txn": current["txn"],
                        "new_receipts": len(book.receipts) - before,
                        "votes_after": dict(state.get_senate_votes_copy() or {}),
                        "proposals_after": [dict(p) for p in
                                            state.get_senate_proposals()]})
        return result

    def _completion_snapshot():
        """The REAL post-packet completion state (schedule rows + records)."""
        snap = session_turn_service.obligations(state, "senate")
        obligations = [{"oid": str(o.obligation_id), "substep": o.substep,
                        "actor": o.actor_player_id,
                        "satisfied": bool(o.satisfied)}
                       for o in snap.obligations]
        records = [{"oid": str(rec.obligation_id),
                    "command_id": str(rec.command_id),
                    "kind": str(rec.satisfied_kind),
                    "fact_ref": str(rec.authoritative_fact_ref),
                    "entry_revision": int(rec.entry_revision),
                    "satisfied_at_revision": int(rec.satisfied_at_revision)}
                   for rec in book.records]
        return {"obligations": obligations, "records": records}

    _ALIAS = {"advancePopulation": "advance_population_phase",
              "doSubmitSenateProposals": "propose_many",
              "doSubmitSenateVotes": "senate_vote",
              "doSubmitSenateVetoes": "senate_veto_decision"}

    def _new_fact(command, before):
        want = _ALIAS.get(command, command)
        for ref, rec in book.committed_facts.items():
            if ref in before:
                continue
            if str(rec.get("command") or "") == want:
                return str(ref), str(rec.get("receipt_id") or "")
        return "", ""

    def _receipt_for(command):
        """The command's committed receipt (shared when the product signs ONE)."""
        want = _ALIAS.get(command, command)
        for ref, rec in book.committed_facts.items():
            if str(rec.get("command") or "") == want:
                return str(ref), str(rec.get("receipt_id") or "")
        return "", ""

    def _packet(pkt_id, step, command, invoke=None, click=None):
        actor = store._viewer_id
        scope = book.scopes["senate"].scope_id if "senate" in book.scopes else ""
        ballots_before = len(ballots)
        facts_before = set(book.committed_facts)
        current["id"], current["command"] = pkt_id, command
        gates_before = len(gui.gate_log)
        gates.arm_real()               # THIS packet's own fresh real window
        if click is not None:
            _h2b_click(shell, click, pump=False)
            result = None
        else:
            result = invoke()
        new_rows = gui.gate_log[gates_before:]
        gate = dict(store._async_gate or {})
        txn = str(gate.get("txn_id") or "")
        if not txn and new_rows:
            txn = str(new_rows[0]["txn"])
        current["txn"] = txn
        if not txn:
            _h2b_emit("PACKET_NO_TXN", chain="AC05-controls", packet=pkt_id,
                      gate=gate, seat=store.seatLifecycle,
                      step=store.senateCurrentStep,
                      can_create=store.canCreateSenateProposal,
                      viewer=store._viewer_id,
                      submit_errors=store._senate_submit_errors,
                      receipt=store._committed_receipt, result=result)
        assert txn and new_rows, (pkt_id, gate, new_rows)
        assert new_rows[0]["kind"] == "arm", new_rows
        assert all(r["txn"] == txn for r in new_rows), new_rows
        # the gate's OWN generation, read while IT is still the live gate
        gen_begin = gates.generation() if str(gate.get("kind") or "") == "arm" \
            else None
        first = gates.claim_first(txn, begin_generation=gen_begin)
        _h2b_settle(shell, gates, driven)
        gates.record_tail(txn)
        ref, rid = _new_fact(command, facts_before)
        shared = False
        if not rid:
            # the product signs ONE receipt per vote package: the packet that did
            # not append a new fact is linked to that SAME committed receipt.
            ref, rid = _receipt_for(command)
            shared = bool(rid)
        receipt = store._committed_receipt or {}
        rdata = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
        record = {
            "packet": pkt_id, "step": step, "actor": actor,
            "owning_txn": txn, "scope": scope, "command": command,
            "accepted": bool(receipt.get("success")),
            "delivery": (rdata.get("delivery")
                         if isinstance(rdata.get("delivery"), dict) else None),
            "created": list(rdata.get("created") or []),
            "owner_receipt_ref": ref, "owner_receipt_id": rid,
            "receipt_shared": shared,
            "gates": [(g["kind"], g["tier"], g["ok"])
                      for g in gui.gate_log if g["txn"] == txn],
            "ballots": ballots[ballots_before:],
            "completion": _completion_snapshot(),
            "pending": bool(((result or {}).get("data") or {}).get("pending")),
        }
        packets.append(record)
        _h2b_emit("PACKET", chain="AC05-controls", packet=pkt_id, step=step,
                  actor=actor, owning_txn=txn, command=command,
                  accepted=record["accepted"], owner_receipt=rid,
                  created=[c.get("proposal_id") for c in record["created"]],
                  first_gate=(first["kind"], first["tier"], first["ok"],
                              first["generation"],
                              first["generation_at_begin"],
                              first["after_signals"], first["swap_signals"],
                              first["source"]),
                  gates=record["gates"],
                  ballot_keys=[(b["proposal"], b["actor"])
                               for b in record["ballots"]])
        current["id"], current["command"], current["txn"] = "", "", ""
        return record

    patchers = [
        patch.object(store, "_fail_masked", side_effect=_fail_spy),
        patch.object(store, "retryHandoff",
                     side_effect=lambda *a, **k: retries.append(1)),
        patch.object(state, "record_senate_vote", side_effect=_vote_spy),
        patch.object(session_turn_service, "continue_after_command",
                     side_effect=_cont_spy),
    ]
    for _p in patchers:
        _p.start()
    try:
        # the startup takeover is a CONTROL (driven), never a packet
        f03._takeover_driven(shell)

        # ---- P1: the population ENTRY (p1) -> cross-seat pending for p2 -----
        _packet("P1", "entry", "advancePopulation",
                lambda: store.doAdvancePopulation())
        assert "senate" in book.scopes, book.scopes
        scope_id = book.scopes["senate"].scope_id
        assert scope_id

        # ---- P2: the TWO proposals are created by the REAL CONTROLS ---------
        store._refresh_senate_view()
        f03._pump(10, 5)                      # the Repeater builds the live cards
        assert store.senateCurrentStep == "proposal", store.senateCurrentStep
        assert store.canCreateSenateProposal is True, store._senate_view
        from PySide6.QtCore import QObject
        stage = shell.window.findChild(QObject, "senateStage")
        button = shell.window.findChild(QObject, "senateProposalSubmitButton")
        assert stage is not None and button is not None, (stage, button)
        options = list(store.senateProposalOptions or [])
        land_keys = [o["key"] for o in options if o.get("type") == "land"]
        assert len(land_keys) == 2, [o.get("key") for o in options]
        js_walk = ("(function(){var out=[];"
                   "function walk(it){if(!it)return;"
                   "if(it.billKey!==undefined)out.push(String(it.billKey));"
                   "var ch=it.children||[];"
                   "for(var i=0;i<ch.length;i++)walk(ch[i]);}"
                   "walk(root);return out;})()")
        _h2b_emit("CARDS", chain="AC05-controls",
                  live_cards=list(_qml_eval(button, js_walk) or []),
                  options=[(o.get("key"), o.get("type"), o.get("public_land"))
                           for o in options],
                  non_war=[(o.get("key"), o.get("type"))
                           for o in _qml_eval(button,
                                              "root.nonWarProposalOptions()") or []])
        # every other selectable card is cleared THROUGH ITS OWN CONTROL, and
        # the two land cards are checked THROUGH THEIR OWN CHECKBOXES.
        for opt in options:
            key = opt.get("key")
            if key in land_keys:
                continue
            if opt.get("type") in ("war", "peace"):
                continue
            if _h2b_card_probe(button, key).get("card") is not True:
                continue
            mechanisms.append((key, _h2b_set_card(shell, button, key, False)))
        for key in land_keys:
            mechanisms.append((key, _h2b_set_card(shell, button, key, True)))
        f03._pump(4, 5)
        package = list(_qml_eval(button, "root.selectedProposals()") or [])
        _h2b_emit("CONTROL", chain="AC05-controls",
                  mechanisms=mechanisms,
                  package=[(r.get("type"), (r.get("params") or {}).get("act_type"),
                            (r.get("params") or {}).get("amount_C"))
                           for r in package],
                  button_enabled=button.property("enabled"),
                  zero_land=_qml_eval(button, "root.hasZeroValueLandSelection()"))
        assert len(package) == 2, package
        assert all(r.get("type") == "land" for r in package), package
        assert sorted((r.get("params") or {}).get("act_type")
                      for r in package) == ["distribution", "sale"], package
        # the click mechanism is disclosed, never assumed
        assert all(m in ("MOUSE_CLICK", "CONTROL_TOGGLE", "ALREADY")
                   for _k, m in mechanisms), mechanisms

        proposals_before = {int(p["id"]) for p in state.get_senate_proposals()}
        p2 = _packet("P2", "proposal", "doSubmitSenateProposals",
                     click=button)
        created = sorted(int(c["proposal_id"]) for c in p2["created"]
                         if c.get("proposal_id") is not None)
        assert len(created) == 2 and len(set(created)) == 2, created
        assert set(created).isdisjoint(proposals_before), (created, proposals_before)
        assert set(created) <= {int(p["id"])
                                for p in state.get_senate_proposals()}, created
        pids = created
        _h2b_emit("PROPOSALS", chain="AC05-controls", ids=pids,
                  source="senateProposalSubmitButton -> doSubmitSenateProposals",
                  owner_receipt=p2["owner_receipt_id"], scope=scope_id,
                  accepted=p2["accepted"])

        # ---- P3..P5: the 2 x 3 ballot matrix, ONE packet per HUMAN --------
        for idx in range(3):
            store._refresh_senate_view()
            view = dict(store._senate_view)
            assert view.get("current_step") == "senate_vote", view
            ids = sorted(int(s["id"]) for s in
                         (view.get("submitted_proposals") or []))
            assert ids == pids, (ids, pids)
            _packet("P%d" % (3 + idx), "senate_vote", "doSubmitSenateVotes",
                    lambda ids=ids: store.doSubmitSenateVotes(ids))

        readiness = session_turn_service.senate_readiness(state)
        _h2b_emit("READINESS", chain="AC05-controls", readiness=readiness)
        assert readiness["required"] == 6, readiness
        assert readiness["covered"] == 6, readiness
        assert readiness["all_ballots_ready"] is True, readiness
        assert readiness["veto_required"] is True, readiness
        assert readiness["veto_satisfied"] is False, readiness

        # ---- P6: the REAL tribune veto closes the ballot phase -------------
        store._refresh_senate_view()
        assert store.senateCurrentStep == "tribune_veto", store.senateCurrentStep
        _packet("P6", "tribune_veto", "doSubmitSenateVetoes",
                lambda: store.doSubmitSenateVetoes([pids[0]]))

        # ---- B-1: ONE chain, TWO real proposals, SIX REAL first gates ------
        assert [p["step"] for p in packets] == [
            "entry", "proposal", "senate_vote", "senate_vote", "senate_vote",
            "tribune_veto"], [p["step"] for p in packets]
        assert [p["actor"] for p in packets] == [
            "player1", "player2", "player1", "player2", "player3",
            "player1"], [p["actor"] for p in packets]
        assert all(p["accepted"] for p in packets), packets
        assert len({p["owning_txn"] for p in packets}) == 6, packets
        for p in packets:
            kinds = [k for k, _t, _o in p["gates"]]
            assert kinds[0] == "arm", (p["packet"], kinds)
            assert p["gates"][0][1] == "FRAME_WINDOW_REAL", p["gates"]
            assert p["gates"][0][2] is True, p["gates"]
            assert all(t == "FRAME_BRIDGE_DRIVEN" and o is True
                       for _k, t, o in p["gates"][1:]), p["gates"]
        real_rows = [r for r in gates.rows if r["tier"] == _w3_real_gate.TIER_REAL]
        assert len(real_rows) == 6, real_rows
        # exactly ONE continuation per accepted packet
        for p in packets:
            hits = [c for c in conts if c["packet"] == p["packet"]]
            assert len(hits) == 1, (p["packet"], hits)
            assert hits[0]["status"] != session_turn_service.STATUS_FAILURE, hits

        # ---- B-2: per-cell (proposal_id x player_id) completion linkage ----
        players = ("player1", "player2", "player3")
        core_votes = state.get_senate_votes_copy() or {}
        _h2b_emit("CORE_VOTES", chain="AC05-controls",
                  final_votes=core_votes,
                  per_packet=[(b["packet"], b["proposal"], b["actor"],
                               b["votes_after"]) for b in ballots])

        def _core_vote(pid, actor, snapshot=None):
            """The REAL Core ballot record of this cell (``{player: {pid: bool}}``)."""
            row = (snapshot or {}).get(actor)
            if isinstance(row, dict):
                for key in (pid, str(pid)):
                    if key in row:
                        return bool(row[key])
            return None

        def _is_ballot(oid, pid, actor):
            return (("'vote:%d'" % pid) in oid) and (("'%s'" % actor) in oid)

        grid = []
        for b in ballots:
            pkt = next(p for p in packets if p["packet"] == b["packet"])
            snap = pkt["completion"]
            obligation = next((o for o in snap["obligations"]
                               if _is_ballot(o["oid"], b["proposal"],
                                             b["actor"])), None)
            record_row = next((r for r in snap["records"]
                               if _is_ballot(r["oid"], b["proposal"],
                                             b["actor"])), None)
            satisfied = bool(obligation and obligation["satisfied"])
            row = {
                "key": (b["proposal"], b["actor"]), "packet": b["packet"],
                "owning_txn": b["txn"],
                "ballot_written": b["txn"] == pkt["owning_txn"],
                "core_vote": _core_vote(b["proposal"], b["actor"],
                                        b["votes_after"]),
                "scheduled_oid": (obligation["oid"] if obligation else ""),
                "satisfied": satisfied,
                "completion_fact_ref": (record_row["fact_ref"]
                                         if record_row else ""),
                "completion_kind": (record_row["kind"] if record_row else ""),
                "packet_receipt": pkt["owner_receipt_id"],
                "packet_fact_ref": pkt["owner_receipt_ref"],
                "annotation": ("REAL_COMPLETION" if record_row else
                               ("SCHEDULE_SATISFIED_NO_PER_BALLOT_RECEIPT"
                                if satisfied else "NOT_SATISFIED")),
                "new_receipts_in_call": b["new_receipts"],
            }
            grid.append(row)
            _h2b_emit("GRID", chain="AC05-controls", proposal=b["proposal"],
                      actor=b["actor"], owning_txn=row["owning_txn"],
                      ballot_written=row["ballot_written"],
                      core_vote=row["core_vote"],
                      scheduled_oid=row["scheduled_oid"],
                      satisfied=row["satisfied"],
                      completion=row["annotation"],
                      completion_fact_ref=row["completion_fact_ref"],
                      packet_receipt=row["packet_receipt"],
                      packet_fact_ref=row["packet_fact_ref"],
                      new_receipts_in_call=row["new_receipts_in_call"])

        expected_keys = {(pid, actor) for pid in pids for actor in players}
        assert len(grid) == 6 and {g["key"] for g in grid} == expected_keys, grid
        assert all(g["ballot_written"] for g in grid), grid
        # the REAL Core vote record exists for EVERY cell (never an OID rename)
        assert all(g["core_vote"] is True for g in grid), grid
        # the REAL post-packet schedule row of EVERY cell is satisfied
        assert all(g["satisfied"] for g in grid), grid
        assert len({g["scheduled_oid"] for g in grid}) == 6, grid
        # every cell points at ITS packet's owner receipt; the three vote packets
        # share the ONE receipt the product signs per package (never invented).
        assert all(g["packet_receipt"] for g in grid), grid
        vote_receipts = {g["packet_receipt"] for g in grid}
        assert len(vote_receipts) == 1, vote_receipts
        assert len({g["owning_txn"] for g in grid}) == 3, grid
        not_collectible = [g["key"] for g in grid
                           if not g["completion_fact_ref"]]
        _h2b_emit("GRID_COMPLETION", chain="AC05-controls",
                  linked=sum(1 for g in grid if g["core_vote"] is True
                             and g["satisfied"] and g["packet_receipt"]),
                  real_completion=sum(1 for g in grid
                                      if g["completion_fact_ref"]),
                  not_collectible=not_collectible,
                  reason=("per-ballot DEDICATED owner receipt NOT_COLLECTIBLE: the "
                          "product signs ONE receipt per vote packet (shared by "
                          "its ballots); the cell is linked through its REAL Core "
                          "vote record + its own satisfied schedule row + its "
                          "packet's owner receipt"))

        # ---- the REAL senate terminal survives the whole chain -------------
        last = packets[-1]["delivery"] or {}
        assert last.get("outcome") == "RESOLVED", last
        terminal = last.get("terminal") or {}
        assert terminal.get("status") == "resolved", terminal
        assert last.get("scope_id") == scope_id, last
        canonical = senate_api.canonical_finalization(
            state, expected_scope=last["scope_id"], claimed_terminal=terminal)
        facts = canonical.get("facts") or {}
        assert canonical.get("status") == "VALID", canonical
        assert facts and all(facts.values()), facts
        assert state.get_phase_result("senate") is not None
        assert failures == [], failures
        assert retries == [], retries
        _h2b_emit("SUMMARY", chain="AC05-controls", packets=len(packets),
                  proposals=pids, scope=scope_id,
                  real_first_gates=len(real_rows),
                  continuations=len(conts), ballots=len(ballots),
                  grid_linked=sum(1 for g in grid if g["core_vote"] is True),
                  grid_receipts=sum(1 for g in grid if g["completion_fact_ref"]),
                  terminal=terminal.get("status"),
                  canonical=canonical.get("status"))
        gates.emit("AC05-controls")
    finally:
        for _p in patchers:
            _p.stop()


# ===========================================================================
# B-4 (AC-W3-18) — the ZERO-LAND isolation control built from a REAL land
# selection draft (never from removing a capability key)
# ===========================================================================
def test_ac_w3_18_zero_land_draft_isolation_control():
    from PySide6.QtCore import QObject
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=3)
    state._national_public_land = 1000
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label="AC18-zeroLand")
    gates.auto_driven_tail()

    # ---- setup leg (CONTROL, driven): startup -> entry -> consul seat ------
    f03._takeover_driven(shell)
    store.doAdvancePopulation()
    driven.render()
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store.requestTakeover()["accepted"] is True
    driven.render()
    driven.render()
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    store._refresh_senate_view()
    f03._pump(10, 5)                          # the Repeater builds the live cards
    assert store.senateCurrentStep == "proposal", store.senateCurrentStep
    assert store.canCreateSenateProposal is True, store._senate_view

    stage = shell.window.findChild(QObject, "senateStage")
    button = shell.window.findChild(QObject, "senateProposalSubmitButton")
    assert stage is not None and button is not None, (stage, button)

    options = list(store.senateProposalOptions or [])
    land = [o for o in options if o.get("type") == "land"]
    assert len(land) == 2, [o.get("key") for o in options]
    key = land[0]["key"]
    acts = sorted(o["params"]["act_type"] for o in land)

    def _inputs():
        return {
            "canCreate": bool(store.canCreateSenateProposal),
            "canTriggerAI": bool(store.canTriggerAIProposer),
            "zeroLand": bool(_qml_eval(button,
                                       "root.hasZeroValueLandSelection()")),
            "aiBlocked": bool(store.senateAiProposerBlocked),
        }

    def _composite():
        return bool(_qml_eval(button, _UI_ENABLED_EXPR))

    # ---- select the land card (and clear every other card) via its control -
    mechanisms = []
    for opt in options:
        other = opt.get("key")
        if other == key or opt.get("type") in ("war", "peace"):
            continue
        if _h2b_card_probe(button, other).get("card") is not True:
            continue
        mechanisms.append((other, _h2b_set_card(shell, button, other, False)))
    mechanisms.append((key, _h2b_set_card(shell, button, key, True)))
    f03._pump(4, 5)

    # ---- state P: the real NON-zero land draft -----------------------------
    positive = _inputs()
    assert positive == {"canCreate": True, "canTriggerAI": False,
                        "zeroLand": False, "aiBlocked": False}, positive
    assert bool(button.property("enabled")) is True
    assert bool(button.property("enabled")) is _composite()
    package = list(_qml_eval(button, "root.selectedProposals()") or [])
    assert [r.get("type") for r in package] == ["land"], package
    assert int(package[0]["params"]["amount_C"]) == int(
        land[0]["params"]["amount_C"]), package
    _h2b_emit("LAND_POSITIVE", chain="AC18-zeroLand", key=key, acts=acts,
              public_land=land[0].get("public_land"),
              amount_C=package[0]["params"]["amount_C"], inputs=positive,
              enabled=button.property("enabled"),
              composite=_composite(), mechanisms=mechanisms)

    # ---- state Z: a REAL ZERO-LAND draft through the SAME draft setter -----
    # The production slider is ``from: 1`` (it can never express 0); the zero
    # value is therefore written through ``setBillParam`` — the EXACT function
    # the slider's own ``onValueChanged`` calls. No capability key is touched.
    _qml_eval(button, "root.setBillParam('%s', 'amount_C', 0)" % key)
    f03._pump(4, 5)
    zero = _inputs()
    assert zero == {"canCreate": True, "canTriggerAI": False,
                    "zeroLand": True, "aiBlocked": False}, zero
    assert bool(button.property("enabled")) is False
    assert bool(button.property("enabled")) is _composite()
    # the CAPABILITY is unchanged: the card/checkbox is still editable/usable
    landed = _h2b_card_probe(button, key)
    assert landed.get("card") is True and landed.get("box") is True, landed
    assert landed.get("enabled") is True, landed
    assert landed.get("checked") is True, landed
    assert store.canCreateSenateProposal is True
    _h2b_emit("LAND_ZERO", chain="AC18-zeroLand", key=key, inputs=zero,
              enabled=button.property("enabled"), composite=_composite(),
              card_editable=landed.get("editable"),
              card_checked=landed.get("checked"),
              store_can_create=store.canCreateSenateProposal)

    # a REAL click on the disabled control dispatches NOTHING
    calls = []
    gate_count = len(gui.gate_log)
    proposals_before = {int(p["id"]) for p in state.get_senate_proposals()}
    real_submit = store._adapter.submit_senate_proposals

    def _submit_spy(*a, **k):
        calls.append(a)
        return real_submit(*a, **k)

    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=_submit_spy):
        _h2b_click(shell, button)
        f03._pump(4, 5)
    assert calls == [], calls
    assert len(gui.gate_log) == gate_count
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert {int(p["id"]) for p in state.get_senate_proposals()} == \
        proposals_before

    # ---- restore a legal draft -> the SAME control really submits ----------
    _qml_eval(button, "root.setBillParam('%s', 'amount_C', 10)" % key)
    f03._pump(4, 5)
    assert _inputs()["zeroLand"] is False
    assert bool(button.property("enabled")) is True == _composite()

    txn, row = _h2b_click_owning(shell, gates, button)
    _h2b_settle(shell, gates, driven)

    receipt = store._committed_receipt or {}
    assert receipt.get("success") is True, receipt
    created = list((receipt.get("data") or {}).get("created") or [])
    assert len(created) == 1, created
    new_ids = {int(p["id"]) for p in state.get_senate_proposals()} - proposals_before
    assert {int(c["proposal_id"]) for c in created} == new_ids, (created, new_ids)
    assert row["tier"] == _w3_real_gate.TIER_REAL and row["ok"] is True, row
    assert row["receipt"] == (txn, "arm"), row
    gates.assert_tail_driven(txn)
    gates.record_tail(txn)
    _h2b_emit("LAND_SUBMIT", chain="AC18-zeroLand", owning_txn=txn,
              tier=row["tier"], ok=row["ok"], generation=row["generation"],
              gen_begin=row["generation_at_begin"],
              after=row["after_signals"], swap=row["swap_signals"],
              created=[c.get("proposal_id") for c in created])
    gates.emit("AC18-zeroLand")


# ===========================================================================
# B-5 (AC-W3-18) — the INDEPENDENT blocked isolation control: the AI proposer
# is refused (never zero-land, never a removed capability key), and the block
# is CONSUMED BY IDENTITY (a real new Core turn clears it).
# ===========================================================================
def _h2b_ai_consul_state():
    """A registered hot-seat whose CONSUL is the AI player: the HUMAN viewer may
    only TRIGGER the AI proposer (``canTriggerAIProposer``), never propose."""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    for fid in ("optimates", "populares"):
        state.add_faction(Faction(id=fid, name=fid.title(), treasury=50))
    consul = Figure(id=8, name="ai-consul", faction_id="populares", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    state.get_faction("populares").member_ids.append(8)
    tribune = Figure(id=9, name="tribune", faction_id="optimates", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    state.get_faction("optimates").member_ids.append(9)
    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.AI))
    state._turn_order = ["player1", "player2"]
    state.set_current_player("player1")
    session_access.register_hotseat_session(state, "player1", epoch=0)
    return state


def test_ac_w3_18_ai_proposer_blocked_isolation_control():
    from PySide6.QtCore import QObject
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _h2b_ai_consul_state()
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label="AC18-aiBlocked")
    gates.auto_driven_tail()
    f03._takeover_driven(shell)
    store._refresh_senate_view()
    assert store.senateCurrentStep == "proposal", store.senateCurrentStep

    button = shell.window.findChild(QObject, "senateProposalSubmitButton")
    assert button is not None, "senateProposalSubmitButton not in the live tree"

    def _inputs():
        return {
            "canCreate": bool(store.canCreateSenateProposal),
            "canTriggerAI": bool(store.canTriggerAIProposer),
            "zeroLand": bool(_qml_eval(button,
                                       "root.hasZeroValueLandSelection()")),
            "aiBlocked": bool(store.senateAiProposerBlocked),
        }

    def _composite():
        return bool(_qml_eval(button, _UI_ENABLED_EXPR))

    # ---- the UNBLOCKED truth table: the AI trigger is a legal control ------
    before = _inputs()
    assert before == {"canCreate": False, "canTriggerAI": True,
                      "zeroLand": False, "aiBlocked": False}, before
    assert bool(button.property("enabled")) is True
    assert bool(button.property("enabled")) is _composite()
    _h2b_emit("AI_INPUTS", chain="AC18-aiBlocked", phase="before",
              inputs=before, enabled=button.property("enabled"),
              composite=_composite())

    # ---- the REAL control click -> the AI owning chain (REAL first gate) ---
    # The refusal is the PRODUCTION guard's own typed DENIED (the same envelope
    # ``session_access.denied_response()`` builds); nothing is monkeypatched and
    # the AI producer is only OBSERVED (no fake return value).
    ai_calls = []
    real_auto = senate_api.auto_submit_proposals

    def _observe_auto(state_, *a, **k):
        ai_calls.append(1)
        return real_auto(state_, *a, **k)

    with patch.object(senate_api, "auto_submit_proposals",
                      side_effect=_observe_auto):
        txn, row = _h2b_click_owning(shell, gates, button)
        _h2b_settle(shell, gates, driven)
    _h2b_emit("AI_PUBLISH", chain="AC18-aiBlocked", ai_producer_calls=len(ai_calls),
              seat=store.seatLifecycle, blocked=store.senateAiProposerBlocked,
              origin=store._senate_ai_proposer_origin(),
              step=store.senateCurrentStep,
              submit_errors=store._senate_submit_errors,
              receipt_success=(store._committed_receipt or {}).get("success"),
              receipt_message=(store._committed_receipt or {}).get("message"))

    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == (
        "turn-1", "proposal", "player1"), store._senate_ai_proposer_block_key
    assert any((item.get("code") or "") == "DENIED"
               for item in (store._senate_submit_errors or [])), \
        store._senate_submit_errors
    assert row["tier"] == _w3_real_gate.TIER_REAL and row["ok"] is True, row
    assert row["receipt"] == (txn, "arm"), row
    gates.assert_tail_driven(txn)
    gates.record_tail(txn)

    # ---- the BLOCKED truth table (not zero-land, not a missing key) ------
    blocked = _inputs()
    assert blocked == {"canCreate": False, "canTriggerAI": True,
                       "zeroLand": False, "aiBlocked": True}, blocked
    assert bool(button.property("enabled")) is False
    assert bool(button.property("enabled")) is _composite()
    _h2b_emit("AI_INPUTS", chain="AC18-aiBlocked", phase="blocked",
              inputs=blocked, enabled=button.property("enabled"),
              composite=_composite(), block_key=store._senate_ai_proposer_block_key,
              owning_txn=txn, tier=row["tier"], ok=row["ok"],
              generation=row["generation"],
              gen_begin=row["generation_at_begin"],
              after=row["after_signals"], swap=row["swap_signals"])
    gates.emit("AC18-aiBlocked")

    # a second REAL click dispatches NOTHING (no second AI publish attempt)
    gate_count = len(gui.gate_log)
    ai_calls_before_second = len(ai_calls)
    with patch.object(senate_api, "auto_submit_proposals",
                      side_effect=_observe_auto):
        _h2b_click(shell, button)
        f03._pump(4, 5)
    assert len(ai_calls) == ai_calls_before_second, ai_calls
    assert len(gui.gate_log) == gate_count

    # ---- the block is CONSUMED BY IDENTITY: a REAL new Core turn clears it -
    state.turn.turn_number = 2
    store._refresh_senate_view()
    assert store.senateAiProposerBlocked is False, store.senateAiProposerBlocked
    assert store._senate_ai_proposer_block_key is None
    _h2b_emit("AI_IDENTITY_CONSUMED", chain="AC18-aiBlocked",
              turn=state.turn.turn_number, inputs=_inputs(),
              enabled=button.property("enabled"))


# ===========================================================================
# H2-c (AC-W3-01 / AC-W3-03 / AC-W3-12) — the 1H2AI long chain.
#
#   ONE HUMAN (player1) + TWO AI (player2 / player3), entered at the population
#   boundary on the REAL GUI shell. EVERY AI decision (the consul proposal and
#   both AI vote ballots) is produced by the REAL coordinator executor
#   (``continue_after_command(ai_executor=...)``), never by this file and never
#   by a synchronous witness. Every packet's FIRST gate is its own fresh real
#   ``QQuickWindow`` (FRAME_WINDOW_REAL); every later gate is
#   FRAME_BRIDGE_DRIVEN. The chain must finish with FAIL_AFTER_COMMIT == 0,
#   retryHandoff == 0 and every handoff completed.
# ===========================================================================
def _h2c_wrap_executor(real_exec, *, current, calls, depth):
    """Observe the REAL coordinator AI executor; its return is kept verbatim.

    Nothing is substituted: the wrapped object is the production callable the
    continuation really carries (``_senate_ai_executor(state, target)``), and its
    OWN ``ExecutionOutcome`` is recorded.
    """
    from src.api import session_turn_service as _turn

    def _run(*a, **k):
        if len(a) >= 2:
            target = a[1]
        else:
            target = k.get("target") or k.get("obligation")
        depth["inside"] += 1
        try:
            result = real_exec(*a, **k)
        finally:
            depth["inside"] -= 1
        status = getattr(result, "kind", None)
        receipts = [str(x) for x in (getattr(result, "receipts", ()) or ())]
        calls.append({
            "packet": current["id"],
            "target_type": type(target).__name__,
            "actor": getattr(target, "actor_player_id", None),
            "substep": getattr(target, "substep", ""),
            "status": status,
            "kind": status,
            "accepted": status == _turn.OUTCOME_ACCEPTED,
            "command_id": getattr(result, "command_id", ""),
            "receipts": receipts,
            "created": receipts,
            "created_count": len(receipts),
            "owner_completion": bool(getattr(result, "owner_completion", None)),
            "detail": getattr(result, "detail", ""),
        })
        return result
    return _run


def _h2c_drive_1h2ai(chain_label):
    """Drive the REAL 1H2AI chain on the live shell; return every observation."""
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=1)
    state._national_public_land = 1000
    book = session_turn_service._book(state)
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label=chain_label)
    gates.auto_driven_tail()

    packets, conts, ballots, exec_calls = [], [], [], []
    failures, retries, handoffs, feedbacks = [], [], [], []
    lifecycles = []
    current = {"id": "", "txn": ""}
    depth = {"inside": 0}
    exec_wrappers = {}

    real_fail = store._fail_masked
    real_cont = session_turn_service.continue_after_command
    real_vote = state.record_senate_vote

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    def _retry_spy(*a, **k):
        retries.append(1)
        return {"accepted": False}

    def _wrap_exec(real_exec):
        key = id(real_exec)
        wrapper = exec_wrappers.get(key)
        if wrapper is None:
            wrapper = _h2c_wrap_executor(real_exec, current=current,
                                         calls=exec_calls, depth=depth)
            exec_wrappers[key] = wrapper
        return wrapper

    def _cont_spy(*a, **k):
        carried = k.get("ai_executor")
        if carried is not None:
            k["ai_executor"] = _wrap_exec(carried)
        elif len(a) >= 2 and callable(a[1]):
            carried = a[1]
            a = (a[0], _wrap_exec(carried)) + tuple(a[2:])
        result = real_cont(*a, **k)
        conts.append({"packet": current["id"],
                      "carried_executor": carried is not None,
                      "status": getattr(result, "status", "")})
        return result

    def _vote_spy(actor, proposal_id, approve, *a, **k):
        result = real_vote(actor, proposal_id, approve, *a, **k)
        ballots.append({"packet": current["id"], "actor": actor,
                        "proposal": int(proposal_id),
                        "approve": bool(approve),
                        "from_executor": depth["inside"] > 0,
                        "txn": current["txn"]})
        return result

    def _packet(pkt_id, step, invoke):
        current["id"] = pkt_id
        gates_before = len(gui.gate_log)
        ballots_before = len(ballots)
        exec_before = len(exec_calls)
        gates.arm_real()
        result = invoke()
        new_rows = gui.gate_log[gates_before:]
        gate = dict(store._async_gate or {})
        txn = str(gate.get("txn_id") or "")
        if not txn and new_rows:
            txn = str(new_rows[0]["txn"])
        assert txn and new_rows, (pkt_id, gate, new_rows)
        assert new_rows[0]["kind"] == "arm", (pkt_id, new_rows)
        assert all(r["txn"] == txn for r in new_rows), (pkt_id, new_rows)
        current["txn"] = txn
        gen_begin = gates.generation() if str(gate.get("kind") or "") == "arm" \
            else None
        first = gates.claim_first(txn, begin_generation=gen_begin)
        _h2b_settle(shell, gates, driven)
        gates.assert_tail_driven(txn)
        gates.record_tail(txn)
        receipt = store._committed_receipt or {}
        data = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
        delivery = data.get("delivery") if isinstance(data.get("delivery"), dict) \
            else None
        record = {
            "packet": pkt_id, "step": step, "txn": txn,
            "accepted": bool(receipt.get("success")),
            "delivery": delivery,
            "created": list(data.get("created") or []),
            "gates": [(g["kind"], g["tier"], g["ok"])
                      for g in gui.gate_log if g["txn"] == txn],
            "first": first,
            "seat": store.seatLifecycle,
            "ballots": ballots[ballots_before:],
            "exec": exec_calls[exec_before:],
            "conts": [c for c in conts if c["packet"] == pkt_id],
            "result": result,
        }
        packets.append(record)
        _h2b_emit("H2C_PACKET", chain=chain_label, packet=pkt_id, step=step,
                  owning_txn=txn, accepted=record["accepted"],
                  outcome=(delivery or {}).get("outcome"),
                  next_actor=((delivery or {}).get("next") or {}).get(
                      "actor_player_id"),
                  created=[c.get("proposal_id") for c in record["created"]],
                  first_gate=(first["kind"], first["tier"], first["ok"],
                              first["generation"],
                              first["generation_at_begin"],
                              first["after_signals"], first["swap_signals"]),
                  gates=record["gates"],
                  continuations=len(record["conts"]),
                  executor_calls=[(c["substep"], c["actor"], c["accepted"])
                                  for c in record["exec"]],
                  ballots=[(b["proposal"], b["actor"], b["from_executor"])
                           for b in record["ballots"]])
        current["id"], current["txn"] = "", ""
        return record

    store.handoffFinished.connect(
        lambda txn, ok: handoffs.append({"txn": txn, "ok": bool(ok)}))
    store.feedbackRaised.connect(
        lambda kind, message: feedbacks.append((str(kind), str(message))))
    store.seatLifecycleChanged.connect(
        lambda: lifecycles.append(store.seatLifecycle))

    patchers = [
        patch.object(store, "_fail_masked", side_effect=_fail_spy),
        patch.object(store, "retryHandoff", side_effect=_retry_spy),
        patch.object(state, "record_senate_vote", side_effect=_vote_spy),
        patch.object(session_turn_service, "continue_after_command",
                     side_effect=_cont_spy),
    ]
    for _p in patchers:
        _p.start()
    try:
        f03._takeover_driven(shell)          # startup seat: CONTROL (driven)
        handoffs.clear()                     # count only the chain's handoffs
        feedbacks.clear()
        lifecycles.clear()

        # ---- the population ENTRY: its continuation drives the AI consul ----
        entry = _packet("P1", "entry", lambda: store.doAdvancePopulation())
        assert entry["accepted"], entry
        assert state.get_senate_proposals(), "the AI consul proposed nothing"
        assert "senate" in book.scopes, book.scopes
        snap = session_turn_service.obligations(state, "senate")
        after_entry = {
            "proposals": [dict(p) for p in state.get_senate_proposals()],
            "decision_complete": bool(state.senate_proposal_decision_complete),
            "propose_facts": [(str(ref), str(rec.get("command") or ""),
                               str(rec.get("receipt_id") or ""))
                              for ref, rec in book.committed_facts.items()
                              if str(rec.get("command") or "") in
                              ("propose_many", "auto_submit_proposals")],
            "obligations": [{"oid": str(o.obligation_id),
                             "substep": o.substep,
                             "actor": o.actor_player_id,
                             "controller": o.controller,
                             "satisfied": bool(o.satisfied)}
                            for o in snap.obligations],
        }

        store._refresh_senate_view()
        assert store.senateCurrentStep == "senate_vote", store.senateCurrentStep
        view = dict(store._senate_view)
        pids = sorted(int(s["id"]) for s in (view.get("submitted_proposals") or []))
        assert pids, view

        # ---- the HUMAN ballot packet: the continuation drains both AI seats --
        _packet("P2", "senate_vote",
                lambda: store.doSubmitSenateVotes(pids))

        store._refresh_senate_view()
        assert store.senateCurrentStep == "tribune_veto", store.senateCurrentStep
        _packet("P3", "tribune_veto",
                lambda: store.doSubmitSenateVetoes([pids[0]]))
    finally:
        for _p in patchers:
            _p.stop()

    return {
        "state": state, "book": book, "shell": shell, "store": store,
        "gui": gui, "gates": gates, "packets": packets, "conts": conts,
        "ballots": ballots, "exec_calls": exec_calls, "failures": failures,
        "retries": retries, "handoffs": handoffs, "feedbacks": feedbacks,
        "lifecycles": lifecycles, "after_entry": after_entry,
    }


def test_ac_w3_12_one_human_two_ai_chain_runs_every_ai_decision_through_the_real_executor():
    """C-1 / C-2 / C-4: the 1H2AI REAL chain with executor provenance."""
    run = _h2c_drive_1h2ai("AC12-1H2AI")
    state, store = run["state"], run["store"]
    packets = run["packets"]

    # ---- C-1: the three packets, each its OWN owning txn + REAL first gate --
    assert [p["step"] for p in packets] == ["entry", "senate_vote",
                                            "tribune_veto"], packets
    assert len({p["txn"] for p in packets}) == 3, packets
    for p in packets:
        kinds = [k for k, _t, _o in p["gates"]]
        assert kinds[0] == "arm", (p["packet"], kinds)
        assert p["gates"][0] == ("arm", _w3_real_gate.TIER_REAL, True), p["gates"]
        assert all(t == _w3_real_gate.TIER_DRIVEN and o is True
                   for _k, t, o in p["gates"][1:]), p["gates"]
        # exactly ONE coordinator continuation per accepted packet
        assert len(p["conts"]) == 1, (p["packet"], p["conts"])
        assert p["conts"][0]["carried_executor"] is True, p["conts"]
        assert p["conts"][0]["status"] != session_turn_service.STATUS_FAILURE
        assert p["accepted"], p
    real_rows = [r for r in run["gates"].rows
                 if r["tier"] == _w3_real_gate.TIER_REAL]
    assert len(real_rows) == 3, real_rows
    # no AI seat is ever parked behind a HUMAN pending
    assert store._pending_player_id == "", store._pending_player_id
    assert SEAT_MASKED_PENDING not in run["lifecycles"], run["lifecycles"]

    # ---- C-2: the NON-EMPTY AI proposal comes from the REAL executor --------
    proposal_calls = [c for c in run["exec_calls"] if c["substep"] == "proposal"]
    assert proposal_calls, run["exec_calls"]
    assert all(c["actor"] == "player2" for c in proposal_calls), proposal_calls
    assert all(c["accepted"] for c in proposal_calls), proposal_calls
    created = [pid for c in proposal_calls for pid in c["created"]]
    assert created, proposal_calls
    registered = sorted(int(p["id"]) for p in run["after_entry"]["proposals"])
    assert sorted(int(pid) for pid in created) == registered, (created, registered)
    assert all(c["command_id"] == "auto_submit_proposals" for c in proposal_calls), \
        proposal_calls
    # the proposal obligation is REALLY completed (owner completion, not a guess)
    prop = [o for o in run["after_entry"]["obligations"]
            if o["substep"] == "proposal"]
    assert prop and all(o["satisfied"] for o in prop), prop
    assert run["after_entry"]["decision_complete"] is True
    # the receipt is the product's OWN committed fact for its proposal writer
    assert run["after_entry"]["propose_facts"], run["after_entry"]
    assert all(rid for _ref, _cmd, rid in run["after_entry"]["propose_facts"]), \
        run["after_entry"]
    # a HUMAN prefix is NOT in the evidence: the proposal packet was the ENTRY
    assert packets[0]["step"] == "entry"
    assert not [p for p in packets if p["step"] == "proposal"], packets

    # ---- every AI ballot is cast INSIDE the real executor -------------------
    ai_ballots = [b for b in run["ballots"] if b["actor"] in ("player2", "player3")]
    assert ai_ballots, run["ballots"]
    assert all(b["from_executor"] for b in ai_ballots), ai_ballots
    assert {b["actor"] for b in ai_ballots} == {"player2", "player3"}, ai_ballots
    assert all(b["proposal"] in registered for b in run["ballots"]), run["ballots"]
    vote_calls = [c for c in run["exec_calls"]
                  if str(c["substep"]).startswith("vote:")]
    assert {c["actor"] for c in vote_calls} >= {"player2", "player3"}, vote_calls
    assert all(c["accepted"] for c in vote_calls), vote_calls
    # the HUMAN ballot(s) are the same-seat packet, never an AI executor call
    human_ballots = [b for b in run["ballots"] if b["actor"] == "player1"]
    assert human_ballots and not any(b["from_executor"] for b in human_ballots), \
        human_ballots

    # ---- the REAL senate terminal survives the whole chain -----------------
    last = packets[-1]["delivery"] or {}
    assert last.get("outcome") == "RESOLVED", last
    terminal = last.get("terminal") or {}
    assert terminal.get("status") == "resolved", terminal
    canonical = senate_api.canonical_finalization(
        state, expected_scope=last.get("scope_id"), claimed_terminal=terminal)
    facts4 = canonical.get("facts") or {}
    assert canonical.get("status") == "VALID", canonical
    assert facts4 and all(facts4.values()), facts4
    assert state.get_phase_result("senate") is not None
    assert store.handoffMaskVisible is False

    # ---- C-4: runtime COUNTS (never constants) -----------------------------
    after_commit = [f for f in run["failures"] if f[0] == "after_commit"]
    assert after_commit == [], run["failures"]
    assert run["failures"] == [], run["failures"]
    assert run["retries"] == [], run["retries"]
    ok_handoffs = [h for h in run["handoffs"] if h["ok"]]
    assert ok_handoffs and len(ok_handoffs) == len(run["handoffs"]), run["handoffs"]
    assert {h["txn"] for h in run["handoffs"]} == {p["txn"] for p in packets}, \
        run["handoffs"]
    error_events = [f for f in run["feedbacks"] if f[0] == "error"]
    assert error_events == [], run["feedbacks"]
    _h2b_emit("H2C_COUNTS", chain="AC12-1H2AI",
              packets=len(packets),
              after_commit=len(after_commit),
              failures=len(run["failures"]),
              retry_handoff_calls=len(run["retries"]),
              handoffs=len(run["handoffs"]),
              handoff_ok=len(ok_handoffs),
              handoff_txns=[h["txn"] for h in run["handoffs"]],
              failure_copy_events=len(error_events),
              feedback_events=len(run["feedbacks"]),
              executor_calls=len(run["exec_calls"]),
              ai_ballots=len(ai_ballots),
              continuations=len(run["conts"]),
              terminal=terminal.get("status"),
              canonical=canonical.get("status"))
    run["gates"].emit("AC12-1H2AI")


def test_ac_w3_03_successful_explicit_empty_batch_is_a_positive_control():
    """C-3: an EXPLICIT successful empty batch (decision_complete, 0 proposals).

    This is the positive carrier AC03 was missing: the AI consul really submits
    an EMPTY package through the real executor, the product records
    ``senate_proposal_decision_complete`` with ZERO proposals, and the chain
    reaches the REAL terminal. It is NOT the N13 failure negative control.
    """
    from src.tests.test_gui import test_w3_delivery_authority as f03

    state = _chain_state(humans=1, budget=False)
    state.config.testing.propose_war_chance = 0.0
    state.config.testing.always_declare = False
    state.config.political_rules.land_proposal.sale_chance = 0.0
    state.config.political_rules.land_proposal.distribution_chance = 0.0
    shell = f03._shell_runtime(state, "player1")
    store, gui, driven = shell.store, shell.gui, shell.driven
    gates = _w3_real_gate.RealGateHarness(shell, label="AC03-empty-batch")
    gates.auto_driven_tail()

    calls, failures, retries, handoffs, feedbacks = [], [], [], [], []
    current = {"id": "", "txn": ""}
    depth = {"inside": 0}
    wrappers = {}
    real_fail = store._fail_masked
    real_cont = session_turn_service.continue_after_command

    def _fail_spy(kind, txn_id="", route="activation"):
        failures.append((kind, txn_id, route))
        return real_fail(kind, txn_id, route)

    def _wrap(real_exec):
        key = id(real_exec)
        if key not in wrappers:
            wrappers[key] = _h2c_wrap_executor(real_exec, current=current,
                                              calls=calls, depth=depth)
        return wrappers[key]

    def _cont_spy(*a, **k):
        carried = k.get("ai_executor")
        if carried is not None:
            k["ai_executor"] = _wrap(carried)
        elif len(a) >= 2 and callable(a[1]):
            carried = a[1]
            a = (a[0], _wrap(carried)) + tuple(a[2:])
        assert carried is not None, "the entry continuation carries no executor"
        return real_cont(*a, **k)

    pm_calls = []
    real_pm = senate_api.propose_many

    def _pm_spy(state_, *a, **k):
        package = a[1] if len(a) > 1 else k.get("package")
        if not isinstance(package, dict):
            package = {}
        result = real_pm(state_, *a, **k)
        pm_calls.append({
            "success": bool((result or {}).get("success")),
            "war_drafts": len(package.get("war_drafts") or []),
            "proposals": len(package.get("proposals") or []),
            "created": len(((result or {}).get("data") or {}).get("created") or []),
            "decision_complete_now": bool(
                getattr(state_, "senate_proposal_decision_complete", False)),
            "all_ballots_ready_now": bool(
                session_turn_service.senate_readiness(state_).get(
                    "all_ballots_ready")),
        })
        return result

    store.handoffFinished.connect(
        lambda txn, ok: handoffs.append({"txn": txn, "ok": bool(ok)}))
    store.feedbackRaised.connect(
        lambda kind, message: feedbacks.append((str(kind), str(message))))

    with patch.object(store, "_fail_masked", side_effect=_fail_spy), \
            patch.object(store, "retryHandoff",
                         side_effect=lambda *a, **k: retries.append(1)), \
            patch.object(session_turn_service, "continue_after_command",
                         side_effect=_cont_spy), \
            patch.object(senate_api, "propose_many", side_effect=_pm_spy):
        f03._takeover_driven(shell)
        handoffs.clear()
        feedbacks.clear()
        current["id"] = "P1"
        gates.arm_real()
        before = len(gui.gate_log)
        entry = store.doAdvancePopulation()
        new_rows = gui.gate_log[before:]
        gate = dict(store._async_gate or {})
        txn = str(gate.get("txn_id") or "") or str(new_rows[0]["txn"])
        current["txn"] = txn
        assert new_rows and new_rows[0]["kind"] == "arm", (gate, new_rows)
        gen_begin = gates.generation() if str(gate.get("kind") or "") == "arm" \
            else None
        first = gates.claim_first(txn, begin_generation=gen_begin)
        _h2b_settle(shell, gates, driven)
        gates.assert_tail_driven(txn)
        gates.record_tail(txn)

    receipt = store._committed_receipt or {}
    data = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
    delivery = data.get("delivery") if isinstance(data.get("delivery"), dict) else {}
    _h2b_emit("H2C_EMPTY_PROBE", chain="AC03-empty-batch",
              step=store.senateCurrentStep,
              can_create=store.canCreateSenateProposal,
              can_trigger=store.canTriggerAIProposer,
              decision_complete=state.senate_proposal_decision_complete,
              proposals=len(state.get_senate_proposals()),
              outcome=(delivery or {}).get("outcome"),
              next_actor=((delivery or {}).get("next") or {}).get("actor_player_id"),
              seat=store.seatLifecycle, viewer=store._viewer_id,
              submit_errors=store._senate_submit_errors,
              calls=[(c["substep"], c["actor"], c["status"], c["created_count"])
                     for c in calls],
              propose_many=pm_calls)

    # ---- the empty decision is REAL and EXPLICIT (not a failure) ------------
    assert receipt.get("success") is True, receipt
    assert state.get_senate_proposals() == [], state.get_senate_proposals()
    assert calls, "the AI executor was never invoked"
    assert all(c["substep"] == "proposal" for c in calls), calls
    assert all(c["accepted"] for c in calls), calls
    assert all(c["created_count"] == 0 for c in calls), calls
    # the product ITSELF wrote the EXPLICIT empty decision at that submit
    # (``decision_complete_now``); the terminal finalization clears the flag
    # again, so the END-of-chain read is False — both are real product facts.
    assert pm_calls, "the AI proposal writer was never called"
    assert all(c["proposals"] == 0 and c["war_drafts"] == 0 for c in pm_calls), \
        pm_calls
    assert all(c["created"] == 0 for c in pm_calls), pm_calls
    assert [c for c in pm_calls if c["decision_complete_now"] is True], pm_calls
    assert state.senate_proposal_decision_complete is False
    # zero ballots exist, so readiness is trivially complete AT the decision
    readiness = session_turn_service.senate_readiness(state)
    assert readiness["required"] == 0 and readiness["covered"] == 0, readiness

    # ---- the outcome is the REAL RESOLVED terminal (positive control) -------
    assert delivery.get("outcome") == "RESOLVED", (delivery, entry)
    terminal = delivery.get("terminal") or {}
    assert terminal.get("status") == "resolved", terminal
    canonical = senate_api.canonical_finalization(
        state, expected_scope=delivery.get("scope_id"), claimed_terminal=terminal)
    assert canonical.get("status") == "VALID", canonical
    facts4 = canonical.get("facts") or {}
    assert facts4 and all(facts4.values()), facts4
    assert state.get_phase_result("senate") is not None

    # ---- strictly distinguished from the N13 failure negative control ------
    assert "delivery_error" not in data, data
    assert store.handoffFailureKind == "", store.handoffFailureKind
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert failures == [], failures
    assert retries == [], retries
    assert all(h["ok"] for h in handoffs), handoffs
    assert [f for f in feedbacks if f[0] == "error"] == [], feedbacks
    assert first["tier"] == _w3_real_gate.TIER_REAL and first["ok"] is True, first
    _h2b_emit("H2C_EMPTY_BATCH", chain="AC03-empty-batch",
              owning_txn=txn, accepted=receipt.get("success"),
              proposals=len(state.get_senate_proposals()),
              decision_complete=state.senate_proposal_decision_complete,
              decision_complete_at_submit=[c["decision_complete_now"]
                                           for c in pm_calls],
              executor_calls=[(c["substep"], c["actor"], c["accepted"],
                               c["created_count"], c["status"])
                              for c in calls],
              outcome=delivery.get("outcome"),
              terminal=terminal.get("status"),
              canonical=canonical.get("status"),
              after_commit=len([f for f in failures if f[0] == "after_commit"]),
              retry_calls=len(retries),
              handoffs=len(handoffs),
              first_gate=(first["kind"], first["tier"], first["ok"],
                          first["generation"], first["after_signals"],
                          first["swap_signals"]))
    gates.emit("AC03-empty-batch")
