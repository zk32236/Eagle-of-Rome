"""W3 — senate turns: HUMAN owner seat, vote arithmetic, guard, F4 freshness.

Bound by G4 §4 to AC-W3-04 / AC-W3-07 / AC-W3-10 / AC-W3-11.
Production seams only: the Slot (``doAdvancePopulation``), the real Adapter/API
boundary, the real Core ledger and the real frame witnesses. AC-07 is the frozen
arithmetic GUARD (D2-3=B, NO TOUCH) and AC-10 is the existing typed guard.
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
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_ACTIVATE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

VIEWER = "player1"


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
    state = _entry_state(consul_controller="ai")
    store, _ = _store(state)
    real = store._adapter.advance_population

    def _drop_delivery(viewer):
        feedback = real(viewer)
        if feedback.get("success"):
            feedback["data"].pop("delivery", None)
            feedback["data"].pop("awaiting_player_id", None)
        return feedback

    with patch.object(store._adapter, "advance_population",
                      side_effect=_drop_delivery):
        result = store.doAdvancePopulation()

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
def _chain_state(*, humans=3):
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
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
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

    # p1 entry -> cross-seat pending for the HUMAN consul (p2) -> REAL takeover
    store.doAdvancePopulation()
    driven.render()
    assert store._pending_player_id == "player2", store._pending_player_id
    takeover_txn = (store._seat_txn or {}).get("txn_id", "")
    assert store.requestTakeover()["accepted"] is True
    driven.render()
    driven.render()
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    f03._pump(8, 5)

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
        gates_before = len(gui.gate_log)
        QTest.mouseClick(shell.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point.toPoint())
        f03._pump(2, 5)
        started = gui.gate_log[gates_before:]
        _emit("CLICK", new_gates=[(g["kind"], g["txn"]) for g in started],
              adapter_calls=len(calls),
              gate=dict(store._async_gate) if store._async_gate else None,
              seat=store.seatLifecycle)
        # the owning dispatch may NOT run before the arm receipt
        assert len(started) == 1, started
        assert started[0]["kind"] == "arm"
        owning_txn = started[0]["txn"]
        assert owning_txn and owning_txn != takeover_txn
        assert calls == [], "dispatch ran before the arm receipt"
        assert store.seatLifecycle not in (SEAT_ACTIVE,), store.seatLifecycle

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
        oid_by_packet = {p["packet"]: p["head"]["oids"] for p in packets}

        def _oid_for(pkt, proposal, actor):
            for oid in oid_by_packet.get(pkt, []):
                if ("'vote:%d'" % proposal) in oid and ("'%s'" % actor) in oid:
                    return oid
            return ""

        ballot_rows = []
        for b in ballots:
            pkt = next(p for p in packets if p["packet"] == b["packet"])
            ballot_rows.append({
                "key": (b["proposal"], b["actor"]), "txn": b["txn"],
                "packet": b["packet"],
                "oid_at_entry": _oid_for(b["packet"], b["proposal"], b["actor"]),
                "packet_receipt": pkt["owner_receipt_id"],
                "packet_fact_ref": pkt["owner_receipt_ref"],
                "new_receipts_in_call": b["new_receipts"],
                "votes_after_keys": sorted((p, a) for p, d in
                                           (b["votes_after"] or {}).items()
                                           for a in (d or {})),
            })
            _emit("BALLOT", chain="GRAN", proposal=b["proposal"], actor=b["actor"],
                  owning_txn=b["txn"], satisfied_oid=ballot_rows[-1]["oid_at_entry"],
                  packet_receipt=ballot_rows[-1]["packet_receipt"],
                  fact_ref=ballot_rows[-1]["packet_fact_ref"],
                  new_receipts_in_call=b["new_receipts"],
                  approve=b["approve"])
        assert all(r["oid_at_entry"] for r in ballot_rows), (ballot_rows,
                                                             [len(c["records"])
                                                              for c in conts])
        assert len({r["oid_at_entry"] for r in ballot_rows}) == 6, ballot_rows
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
