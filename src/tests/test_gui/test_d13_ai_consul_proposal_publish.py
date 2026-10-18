"""EOR20261013-02 · D13 — AI 执政官提案发布死锁（Option 1 + Option 4）.

Implements the RED-first contract of the FROZEN design:

  * ``00-gates/G3-delta-PM-Freeze-Record-D13_2026-10-18.md`` (design frozen);
  * ``00-gates/G4-DA-Sizing-and-Write-Scope-D13_2026-10-18.md`` (write face);
  * ``02-sa-design/D13_Implementation-and-Test-Overlay.md`` (THE spec, §4 oracle);
  * ``02-sa-design/D13_Design-Delta.md``;
  * ``00-gates/G3-delta-PM-Pro-ReReview-D13_2026-10-18.md`` (B01–B04 CLOSED).

Defect: the Store's AI-controller branch (``session_store.py`` doSubmitSenateProposals)
called ``senate_api.auto_submit_proposals`` OUTSIDE the masked owning flow, so the
AI-child ``propose_many`` (viewer = the AI consul player) was DENIED by the
registered Hot-seat guard (no owning possession) and the API then flattened the
typed ``DENIED`` error into a string + reported "已自动提交 0 项提案" (deadlock).

Covered (matrix ids per Overlay §4.3):
  * D13-T01  non-empty publish stops at the REAL outstanding HUMAN ballot
  * D13-T02  the real one-use owning lease (propose_many, ACTIVE HUMAN actor)
  * D13-T03  Core idempotency (R1a): the Store's post-ballot refusal is NOT the
             Core gate; the real `PACKAGE_ALREADY_SUBMITTED` is proven through a
             legitimate owning dispatch, package identity unchanged
  * D13-T10  independent EMPTY-package terminal (R1a): canonical senate phase
             result == terminal receipt, RESOLVED/HUMAN receiver
  * D13-T04  a non-owner HUMAN viewer is refused verbatim (no package/lease/lock)
  * D13-T05  masked-continuation failure keeps message/data/typed errors and takes
             the bounded CONTINUATION route (never an Option-4 lock)
  * D13-T06  typed seat DENIED -> lock -> real same-seat new-epoch activation ->
             ACTIVE; masked empty projection never unlocks; reason consumed by the
             existing feedback channel
  * D13-T07  a REAL viewer/session/step change clears bool+reason+key (both sync
             entry points); same-seat / masked-empty never clears
  * D13-T08  legacy never-registered AI proposer (no provider) keeps the old path
  * D13-T09  registered + no provider still fails closed (no masked txn)
  * D13-T11  activation-frame failure is captured (handoffFinished(False)/
             MASKED_FAILURE), not judged green from the committed receipt
  * D13-T11a delayed ASYNC gates (R1a): arm / publish / unmask released one by
             one — no submit before arm, exactly one submit after arm, neutral
             DTO + no public handle until the final reveal, real settle result
  * D13-T11b async publish frame False (R1a): a real post-commit failure
  * D13-T12  an ordinary validation rejection does NOT lock and can be retried
  * D13-T13  PACKAGE_ALREADY_SUBMITTED does NOT lock / is not reported as auth
  * D13-T14  the API copies the FULL inner envelope (delivery/status/...) while
             keeping the existing display keys

Provenance: real GameState/Core publication, real ``register_hotseat_session``,
real authorize/lease/consume, real masked activation frame gates. The denial /
rejection envelopes injected in T05/T06/T11/T12/T13 are the SYNTHETIC seams the
Overlay explicitly asks for; every activation/settle path below them is real.
``source_kind = CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY``.
NO TOUCH: this file is new; no pre-existing test byte is modified.
"""
from __future__ import annotations

import os
import sys
from functools import wraps
from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _case_timestamp(request):
    print(f"D13 CASE {request.node.nodeid} START {datetime.now(timezone.utc).isoformat()}")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.api import session_access
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.ui.gui.session_store import GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_FAILURE


# ---------------------------------------------------------------------------
# Fixtures — a REGISTERED hot-seat with an ACTUAL AI consul (T7 shape)
# ---------------------------------------------------------------------------
SESSION_ID = "turn-1"


def _ai_consul_state(*, current="player1", register=True, budget=True,
                     second_player_type=PlayerType.AI):
    """2 factions: consul ∈ populares(player2=AI); tribune ∈ optimates(player1).

    viewer/current = player1 (HUMAN) -> ``resolve_proposal_control("player1")`` is
    ``AI`` (the eligible consul belongs to the other faction), so the Store takes
    the AI-controller branch while the ACTIVE seat is the HUMAN principal.
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=8, name="ai-consul", faction_id="populares", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f2.member_ids.append(8)

    tribune = Figure(id=9, name="tribune", faction_id="optimates", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f1.member_ids.append(9)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=second_player_type))
    state._turn_order = ["player1", "player2"]
    state.set_current_player(current)

    if budget:
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS, province_id=1, base_cost=100,
            current_turn=1)
        contract.status = ContractStatus.PENDING
        # D13-R2: the id of a REAL pending contract (used by the corrected
        # real-dispatch leg of T12b; never a fabricated package identity).
        state._d13_contract_id = contract.id

    if register:
        session_access.register_hotseat_session(state, "player1", epoch=0)
    return state


def _human_owner_state():
    """consul ∈ optimates(player1=HUMAN), viewer = player2 (HUMAN, non-owner)."""
    state = _ai_consul_state(register=False, second_player_type=PlayerType.HUMAN)
    # move the consul to player1's faction so the proposal obligation is HUMAN
    consul = state.get_living_member(8)
    consul.faction_id = "optimates"
    state.get_faction("populares").member_ids.remove(8)
    state.get_faction("optimates").member_ids.append(8)
    state.set_current_player("player2")
    session_access.register_hotseat_session(state, "player1", epoch=0)
    return state


SENATE_VIEW = {
    "phase_id": "senate",
    "current_phase_id": "senate",
    # D13-R2 F01: the REAL get_senate_view DTO does NOT publish
    # ``senate_session_id``; the fixture must not hand-feed an identity the
    # production DTO never carries.
    "viewer_player_id": "player1",
    "current_step": "proposal",
    "viewer_has_consul": False,
    "can_trigger_ai_proposer": True,
    "is_current_player": True,
}


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)
        self.feedback = []
        store.feedbackRaised.connect(self._on_feedback)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)

    def _on_feedback(self, kind, message):
        self.feedback.append((kind, message))


class _SyncWitness:
    """The framework's synchronous witness: every gate returns True inline."""

    def __init__(self, store=None, fail_unmask=False):
        self.calls = []
        self.pendings = []
        self.store = store
        self.fail_unmask = fail_unmask
        self.masked_senate_views = []

    def _snap(self):
        if self.store is not None:
            self.masked_senate_views.append(dict(self.store._senate_view or {}))

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        self._snap()
        return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction))
        self.pendings.append(faction)
        self._snap()
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        self._snap()
        return not self.fail_unmask

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


def _active_store(state, viewer="player1", senate_view=None, witness=None):
    store = GuiSessionStore(state)
    receiver = _Receiver(store)
    witness = witness or _SyncWitness(store)
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = viewer
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = dict(senate_view if senate_view is not None else SENATE_VIEW)
    # D13-R2 F01: no ``_senate_draft_session_id`` seeding — the ONLY identity
    # source under test is the Core turn (``state.turn.turn_number``).
    return store, witness, receiver


def _assert_fixture(state, viewer="player1"):
    """Fixture self-check (Overlay §4.2): never let a false red slip in."""
    assert session_access.is_hotseat_registered(state) is True
    assert state.get_current_player().player_id == viewer
    from src.core.systems.political_system import PoliticalSystem
    ctrl = PoliticalSystem(state).resolve_proposal_control(viewer)
    assert ctrl["mode"] == "AI", ctrl


def _published(state):
    pid = state.get_senate_package_id_for_session(SESSION_ID)
    return pid, (state.get_senate_package_record(pid) if pid else None)


def _reason_msg():
    return "AI 执政官提案未能发布（授权失败），请报告缺陷。"


def _real_senate_dto(state, viewer="player1", **overrides):
    """A REAL ``get_senate_view`` data projection (never a hand-built identity)."""
    env = senate_api.get_senate_view(
        state, viewer, caller_context=session_access.current_caller_context(state))
    assert env.get("success") is True, env
    data = dict(env.get("data") or {})
    data.pop("senate_session_id", None)   # the DTO never publishes it
    data.update(overrides)
    return data


# ===========================================================================
# D13-T00 (F01) — the origin identity comes from Core ``turn-N``, not the DTO
# ===========================================================================
def test_d13_t00_identity_comes_from_core_turn():
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    # the DTO genuinely does not carry the key (the fixture no longer fakes it)
    assert "senate_session_id" not in store._senate_view, store._senate_view
    # the ONLY trusted identity = Core turn -> ``turn-{N}``
    assert store._senate_session_identity() == SESSION_ID, \
        store._senate_session_identity()
    # the strict origin predicate becomes a REAL key
    assert store._senate_ai_proposer_origin() == (SESSION_ID, "proposal", "player1"), \
        store._senate_ai_proposer_origin()

    # a non-positive / bool / missing turn is NOT an identity (fail-closed)
    state.turn.turn_number = 0
    assert store._senate_session_identity() is None
    assert store._senate_ai_proposer_origin() is None
    state.turn.turn_number = True
    assert store._senate_session_identity() is None
    state.turn.turn_number = 1

    # a non-proposal step / missing viewer / missing phase never builds an origin
    store._senate_view = {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "senate_vote"}
    assert store._senate_ai_proposer_origin() is None
    store._senate_view = {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "proposal"}
    store._viewer_id = ""
    assert store._senate_ai_proposer_origin() is None
    store._viewer_id = "player1"
    store._senate_view = {"viewer_player_id": "player1", "current_step": "proposal"}
    assert store._senate_ai_proposer_origin() is None
    # viewer mismatch is never the origin viewer
    store._senate_view = {"phase_id": "senate", "viewer_player_id": "player2",
                          "current_step": "proposal"}
    assert store._senate_ai_proposer_origin() is None


@pytest.mark.parametrize("mismatch", ["viewer", "session", "step", "phase", "key"])
def test_d13_b04_final_identity_mismatch_never_restores_errors(monkeypatch, mismatch):
    state = _ai_consul_state()
    store, witness, receiver = _active_store(state)

    def auto_submit_proposals(state_, *a, **k):
        return session_access.denied_response()

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)
    completed = []

    def final_boundary(txn_id, ok):
        assert ok is True
        completed.append(ok)
        # The real frame/lifecycle has completed. Simulate a new final identity
        # before rejection completion consumes it; old errors must not cross it.
        store._senate_submit_errors = []
        if mismatch == "viewer":
            store._viewer_id = "player2"
        elif mismatch == "session":
            state.turn.turn_number = 2
        elif mismatch == "step":
            store._senate_view["current_step"] = "senate_vote"
        elif mismatch == "phase":
            store._senate_view["phase_id"] = "forum"
        else:
            store._senate_ai_proposer_block_key = ("turn-9", "proposal", "player1")

    store.handoffFinished.connect(final_boundary)
    store.doSubmitSenateProposals([])
    assert completed == [True]
    assert store._senate_submit_errors == []
    assert not any(message == _reason_msg() for _, message in receiver.feedback)


def test_d13_b04_completion_consumes_saved_reason(monkeypatch):
    state = _ai_consul_state()
    store, witness, receiver = _active_store(state)
    saved_reason = "saved origin-specific authorization reason"

    def auto_submit_proposals(state_, *a, **k):
        return session_access.denied_response()

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)

    def final_boundary(txn_id, ok):
        assert ok is True
        store._senate_ai_proposer_blocked_reason = saved_reason
        store._senate_submit_errors = []

    store.handoffFinished.connect(final_boundary)
    store.doSubmitSenateProposals([])
    assert store._senate_ai_proposer_origin() == (SESSION_ID, "proposal", "player1")
    assert any(item.get("code") == "DENIED" for item in store._senate_submit_errors)
    assert any(message == saved_reason for _, message in receiver.feedback)
    assert not any(message == _reason_msg() for _, message in receiver.feedback)


def _wrap_auto(fn):
    """Keep the REAL API name (the Adapter's boundary label is ``__name__``)."""
    return wraps(senate_api.auto_submit_proposals)(fn)


# ===========================================================================
# D13-T01 — a NON-EMPTY AI publication stops at the outstanding HUMAN ballot
# ===========================================================================
def test_d13_t01_non_empty_publish_stops_at_human_ballot():
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    fb = store.doSubmitSenateProposals([])
    receipt = store._committed_receipt

    pid, record = _published(state)
    assert pid and record, (
        "D13-T01: the AI consul publication did not reach Core (RED = AI-child "
        "propose_many denial)", fb, receipt)
    refs = record.get("proposal_refs") or record.get("created") or []
    assert refs, record
    assert len(refs) >= 1, record
    assert state.get_senate_proposals(), state.get_senate_proposals()
    assert state.senate_proposal_decision_complete is True

    data = (receipt or {}).get("data") or {}
    delivery = data.get("delivery") or {}
    assert delivery.get("outcome") == "CONTINUE", (delivery, data, fb)
    nxt = delivery.get("next") or {}
    assert nxt.get("controller") == "HUMAN", nxt
    assert nxt.get("actor_player_id") == "player1", nxt
    # the ballot is genuinely OUTSTANDING: the HUMAN seat is still ACTIVE after
    # the same-seat recovery, and no ballot was cast on the player's behalf.
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    # never a masked continuation failure
    assert store._handoff_failure_kind == "", store._handoff_failure_kind


# ===========================================================================
# D13-T02 — the REAL one-use owning lease
# ===========================================================================
def test_d13_t02_real_owning_lease(monkeypatch):
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    seen = {"lease": [], "consume": []}
    orig_lease = session_access.authorize_and_lease
    orig_consume = session_access.consume_command_lease

    def _lease(*a, **k):
        seen["lease"].append(dict(k))
        return orig_lease(*a, **k)

    def _consume(*a, **k):
        seen["consume"].append(dict(k))
        return orig_consume(*a, **k)

    monkeypatch.setattr(session_access, "authorize_and_lease", _lease)
    monkeypatch.setattr(session_access, "consume_command_lease", _consume)

    store.doSubmitSenateProposals([])

    assert seen["lease"], "no owning lease was requested"
    lease = seen["lease"][0]
    assert lease["command"] == "propose_many", lease
    assert lease["actor"] == "player1", lease
    assert lease["txn_id"], lease
    assert seen["consume"], "the lease was never consumed"
    assert seen["consume"][0]["helpers"] == frozenset({
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
        "finalize_senate_if_ready", "assign_governors",
    }), seen["consume"][0]["helpers"]


# ===========================================================================
# D13-T04 — a non-owner HUMAN viewer is refused verbatim (no lock, no package)
# ===========================================================================
def test_d13_t04_non_owner_human_refused():
    state = _human_owner_state()
    # sanity: the obligation says HUMAN and the owner is player1, viewer is player2
    store, witness, receiver = _active_store(state, viewer="player2")

    fb = store.doSubmitSenateProposals([])

    assert fb.get("success") is False, fb
    assert fb.get("message") == "当前提案权不属于本玩家，不能代替其他玩家/无主持人提案", fb
    pid, record = _published(state)
    assert pid is None and record is None, (pid, record)
    assert witness.calls == [], witness.calls
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None


# ===========================================================================
# D13-T05 — masked continuation failure: fidelity + bounded CONTRIBUTION route
# ===========================================================================
def test_d13_t05_continuation_failure_preserves_typed_envelope(monkeypatch):
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    envelope = {
        "success": False,
        "message": "AI continuation failed",
        "data": {"status": "masked_failure", "resolved": False,
                 "retryable": True, "reason": "ai_drain_timeout"},
        "errors": [{"code": "AI_DRAIN_MASKED_FAILURE",
                    "message": "ai_drain_timeout"}],
    }

    def auto_submit_proposals(state_, *a, **k):
        return dict(envelope)

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)

    fb = store.doSubmitSenateProposals([])

    # the ORIGINAL (unflattened) envelope is preserved on the committed receipt
    receipt = store._committed_receipt or {}
    assert receipt.get("message") == "AI continuation failed", (receipt, fb)
    assert (receipt.get("data") or {}).get("status") == "masked_failure", receipt
    assert any(isinstance(e, dict) and e.get("code") == "AI_DRAIN_MASKED_FAILURE"
               for e in (receipt.get("errors") or [])), receipt
    assert store._handoff_failure_route == "continuation", store._handoff_failure_route
    assert store._handoff_failure_kind == "after_commit", store._handoff_failure_kind
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    # no activation retry was opened (arm happened ONCE, at the owning flow start)
    assert sum(1 for c in witness.calls if c[0] == "arm") == 1, witness.calls


# ===========================================================================
# D13-T05 (F03) — a REAL post-commit AI-drain failure: no replay, no lock
# ===========================================================================
def test_d13_t05b_real_post_commit_ai_drain_does_not_replay(monkeypatch):
    """T05b — the REAL publication commits, then the built-in AI-drain fails.

    The synthetic envelope above isolates the recognition seam. THIS case proves
    the production chain: a real ``auto_submit_proposals`` publishes a real
    non-empty package, the post-commit ``continue_after_command`` reports the
    masked AI-drain failure, and the Store takes the bounded CONTINUATION route
    without replaying the already committed package.
    """
    from src.api import session_turn_service

    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    submissions = {"n": 0}
    monkeypatch.setattr(senate_api, "auto_submit_proposals",
                        _counting_auto(submissions))

    class _DrainFailure:
        masked_failure = True
        reason = "ai_drain_timeout"
        terminal = None

    def _continue(state_, ai_executor=None):
        return _DrainFailure()

    original_continue = session_turn_service.continue_after_command
    monkeypatch.setattr(session_turn_service, "continue_after_command", _continue)

    fb = store.doSubmitSenateProposals([])

    # the REAL publication happened exactly once, before the drain failed
    pid, record = _published(state)
    assert pid and record, (fb, pid)
    refs_before = list(record.get("proposal_refs") or [])
    assert refs_before, record
    packages_before = _packages(state)
    proposals_before = _proposal_ids(state)
    assert submissions["n"] == 1, submissions

    # the typed masked-continuation envelope is preserved verbatim
    receipt = store._committed_receipt or {}
    assert (receipt.get("data") or {}).get("status") == "masked_failure", receipt
    assert any(isinstance(e, dict) and e.get("code") == "AI_DRAIN_MASKED_FAILURE"
               for e in (receipt.get("errors") or [])), receipt
    assert fb.get("success") is False, fb
    # bounded CONTINUATION recovery — never an Option-4 lock / activation retry
    assert store._handoff_failure_kind == "after_commit", store._handoff_failure_kind
    assert store._handoff_failure_route == "continuation", store._handoff_failure_route
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    assert sum(1 for c in witness.calls if c[0] == "arm") == 1, witness.calls

    # Remove the real drain fault, then drive the PRODUCTION continuation
    # recovery entry: ``Store.doRecoverContinuation`` -> Adapter -> public guard
    # -> ``session_api.recover_continuation``. ``retryHandoff`` is activation-only
    # and is NOT the S-C continuation route, so it must not stand in for it.
    monkeypatch.setattr(session_turn_service, "continue_after_command", original_continue)

    from src.api import session_api
    original_recover = session_api.recover_continuation
    recoveries = {"n": 0}

    @wraps(original_recover)
    def _recover(state_, *a, **k):
        recoveries["n"] += 1
        return original_recover(state_, *a, **k)

    monkeypatch.setattr(session_api, "recover_continuation", _recover)

    recovered = store.doRecoverContinuation()

    # the recovery entry really ran (once), and it resumed outstanding work
    assert recoveries["n"] == 1, (recoveries, recovered)
    assert isinstance(recovered, dict), recovered
    # the committed HUMAN command / package is NEVER resubmitted
    assert submissions["n"] == 1, submissions
    assert _packages(state) == packages_before, _packages(state)
    assert _proposal_ids(state) == proposals_before
    pid_after, record_after = _published(state)
    assert pid_after == pid, (pid, pid_after)
    assert list(record_after.get("proposal_refs") or []) == refs_before


# ===========================================================================
# D13-T06 — typed seat DENIED -> UI-local lock across a REAL same-seat recovery
# ===========================================================================
def test_d13_t06_seat_denied_lock_survives_same_seat_activation(monkeypatch):
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    def auto_submit_proposals(state_, *a, **k):
        return session_access.denied_response()

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)

    fb = store.doSubmitSenateProposals([])

    # the seat was really re-activated at a NEW epoch (same seat, no takeover)
    assert any(c[0] == "unmask" for c in witness.calls), witness.calls
    assert store._seat_epoch >= 1, store._seat_epoch
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    # masked projection was empty while the transaction ran
    assert any(view == {} for view in witness.masked_senate_views), \
        witness.masked_senate_views
    # the lock is set and keyed on the PRE-CALL origin (never an empty key)
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1"), \
        store._senate_ai_proposer_block_key
    # epoch is NOT part of the identity: same seat/new epoch keeps the lock
    # the original structured rejection is restored through the existing surface
    assert store._senate_submit_errors, store._senate_submit_errors
    assert any((item.get("code") or "") == "DENIED"
               for item in store._senate_submit_errors), store._senate_submit_errors
    # the reason is CONSUMED by the existing feedback channel
    assert any(msg == _reason_msg() for _kind, msg in receiver.feedback), receiver.feedback
    # the API message is not replaced by the reason
    assert fb.get("message") == session_access.DENIED_MESSAGE, fb


# ===========================================================================
# D13-T07 (F02) — the lock survives / clears ONLY on REAL trustworthy facts.
#
# The lock is ALWAYS built through the real T06 chain (real masked owning flow,
# real DENIED, real same-seat activation) — never by seeding the three fields.
# Both sync entry points are covered: ``_apply_staged`` (real final reveal with
# an explicit target) and ``_refresh_senate_view`` (ACTIVE ordinary refresh).
# ===========================================================================
def _real_denied_lock(monkeypatch, *, state=None, viewer="player1", witness=None):
    """Build the Option-4 lock through the REAL T06 chain."""
    state = state or _ai_consul_state()
    _assert_fixture(state, viewer)
    store, witness, receiver = _active_store(state, viewer=viewer, witness=witness)

    def auto_submit_proposals(state_, *a, **k):
        return session_access.denied_response()

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)
    store.doSubmitSenateProposals([])
    assert store.senateAiProposerBlocked is True, store.senateAiProposerBlocked
    # Identity equality is asserted by T06 and each post-sync oracle below;
    # do not short-circuit the negative projection tests at that earlier defect.
    assert store._senate_ai_proposer_block_key is not None
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    return state, store, witness, receiver


def _real_activate(store, target, *, same_seat=False):
    """Drive a REAL activation (private staging + publish/unmask frames)."""
    txn = store._begin_masked_seat_transition(
        "doSubmitSenateProposals", lease_command=None, payload={}, cont=None)
    assert txn is not None, "the masked transaction did not arm"
    store._activate_seat(txn["txn_id"], target, same_seat=same_seat)
    return store._activation_result


def _refresh_with(store, view):
    """ACTIVE ordinary refresh with a controlled projection."""
    store._adapter.get_senate_view = lambda viewer: dict(view)
    store._refresh_senate_view()


def test_d13_t07a_real_viewer_change_clears(monkeypatch):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    # Make the other seat HUMAN only AFTER the real AI-proposer denial.
    state.get_player("player2")._player_type = PlayerType.HUMAN

    seen = []
    store.senateViewChanged.connect(
        lambda: seen.append((store.senateAiProposerBlocked,
                             store._senate_ai_proposer_blocked_reason,
                             store._senate_ai_proposer_block_key)))

    # a REAL handoff to the OTHER HUMAN: Core current player changes, then the
    # real activation stages/publishes/reveals the new seat.
    state.set_current_player("player2")
    result = _real_activate(store, "player2")

    assert result is not None and result.get("success") is True, result
    assert store._viewer_id == "player2"
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_blocked_reason == ""
    assert store._senate_ai_proposer_block_key is None
    assert seen and seen[-1] == (False, "", None), seen

    # ---- V2-T07a: the NEW viewer's ORDINARY real DTO refresh --------------
    # The reveal alone is not the whole gap: the ACTIVE ordinary refresh of the
    # NEW seat is a second sync entry point, after the viewer identity changed.
    before_feedback = list(receiver.feedback)
    real_new = _real_senate_dto(state, "player2")
    assert real_new.get("viewer_player_id") == "player2", real_new
    assert real_new.get("phase_id") == "senate", real_new
    store._refresh_senate_view()

    assert store._viewer_id == "player2"
    assert store._senate_view.get("viewer_player_id") == "player2", store._senate_view
    # three-way clear stays cleared through the ordinary refresh, with notify
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_blocked_reason == ""
    assert store._senate_ai_proposer_block_key is None
    assert seen and seen[-1] == (False, "", None), seen
    # nothing from the OLD seat crosses into the new one
    assert store._senate_submit_errors == [], store._senate_submit_errors
    assert [m for m in receiver.feedback[len(before_feedback):]
            if m[1] == _reason_msg()] == [], receiver.feedback


def test_d13_t07b_same_seat_new_epoch_and_ordinary_proposal_keep_the_lock(monkeypatch):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)

    # REAL same-seat activation: same viewer, same Core turn, new epoch -> keep
    result = _real_activate(store, "player1", same_seat=True)
    assert result is not None and result.get("success") is True, result
    assert store._seat_epoch >= 2, store._seat_epoch
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1"), \
        store._senate_ai_proposer_block_key

    # ORDINARY ACTIVE refresh with the REAL proposal DTO (no session key) -> keep
    real_view = _real_senate_dto(state, "player1")
    assert real_view.get("current_step") == "proposal", real_view.get("current_step")
    _refresh_with(store, real_view)
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1")


def test_d13_t07c_missing_session_known_step_keeps_the_lock(monkeypatch):
    """F01 counter-example: only a step, no phase/viewer/session -> KEEP."""
    state, store, witness, receiver = _real_denied_lock(monkeypatch)

    _refresh_with(store, {"current_step": "senate_vote"})

    assert store.senateAiProposerBlocked is True, "missing identity MUST NOT clear"
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1"), \
        store._senate_ai_proposer_block_key
    # the same incomplete projection through the staged entry point keeps it too
    store._apply_staged({"senate": {"current_step": "senate_vote"},
                         "snapshot": {"current_phase_id": "senate"}},
                        target_id="player1")
    assert store.senateAiProposerBlocked is True


@pytest.mark.parametrize("overrides", [
    {"current_step": "senate_vote", "denied": True},
    {"current_step": "senate_vote", "masked": True},
    {"current_step": "senate_vote", "placeholder": True},
    {"current_step": "senate_vote", "status": "masked_failure"},
    {"current_step": "senate_vote", "status": "denied"},
    {"current_step": "senate_vote", "status": "masked"},
    {"current_step": "readiness_error"},
    {"current_step": "unknown_step"},
    {"current_step": "senate_vote", "success": False},
    {"current_step": "senate_vote", "viewer_player_id": "player2"},
    {"current_step": "senate_vote", "phase_id": "forum"},
])
def test_d13_t07d_denied_masked_placeholder_keep_the_lock(monkeypatch, overrides):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    key_before = store._senate_ai_proposer_block_key
    view = dict(phase_id="senate", viewer_player_id="player1", **{})
    view.update(overrides)
    _refresh_with(store, view)
    assert store.senateAiProposerBlocked is True, view
    assert store._senate_ai_proposer_block_key == key_before, view


@pytest.mark.parametrize("invalid_turn", [None, 0, -1, True, False, "1", 1.0])
def test_d13_t07h_missing_core_identity_keeps_lock(monkeypatch, invalid_turn):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    key_before = store._senate_ai_proposer_block_key
    state.turn.turn_number = invalid_turn
    _refresh_with(store, {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "senate_vote"})
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == key_before


def test_d13_t07i_new_turn_with_invalid_projection_keeps_lock(monkeypatch):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    key_before = store._senate_ai_proposer_block_key
    state.turn.turn_number = 2
    _refresh_with(store, {"current_step": "senate_vote"})
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == key_before


def test_d13_t07e_valid_leave_proposal_clears(monkeypatch):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)

    seen = []
    store.senateViewChanged.connect(
        lambda: seen.append((store.senateAiProposerBlocked,
                             store._senate_ai_proposer_blocked_reason,
                             store._senate_ai_proposer_block_key)))

    _refresh_with(store, {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "senate_vote"})

    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_blocked_reason == ""
    assert store._senate_ai_proposer_block_key is None
    assert seen and seen[-1] == (False, "", None), seen

    # settlement_pending is a REAL post-vote recovery step -> also clears
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    _refresh_with(store, {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "settlement_pending"})
    assert store.senateAiProposerBlocked is False


def test_d13_t07f_new_core_turn_clears(monkeypatch):
    """A REAL new Core turn (``turn_number`` 1 -> 2) invalidates the lock."""
    state, store, witness, receiver = _real_denied_lock(monkeypatch)

    state.turn.turn_number = 2
    assert store._senate_session_identity() == "turn-2"
    _refresh_with(store, {"phase_id": "senate", "viewer_player_id": "player1",
                          "current_step": "proposal"})

    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None


def test_d13_t07g_failed_reveal_keeps_the_lock_and_no_reason(monkeypatch):
    state, store, witness, receiver = _real_denied_lock(monkeypatch)

    # the NEXT real activation fails its final-reveal frame
    witness.fail_unmask = True
    before = list(receiver.feedback)
    result = _real_activate(store, "player1", same_seat=True)

    assert result is None or result.get("success") is not True, result
    assert store._seat_lifecycle == SEAT_MASKED_FAILURE, store._seat_lifecycle
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1")
    # no reason replay from a failed reveal
    assert [m for m in receiver.feedback[len(before):] if m[1] == _reason_msg()] == [], \
        receiver.feedback


# ===========================================================================
# D13-T08 / T09 — provider gate: legacy (no provider) vs registered fail-closed
# ===========================================================================
def test_d13_t08_legacy_never_registered_no_provider(monkeypatch):
    state = _ai_consul_state(register=False)
    assert session_access.is_hotseat_registered(state) is False
    store = GuiSessionStore(state)
    receiver = _Receiver(store)
    store._viewer_id = "player1"
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = dict(SENATE_VIEW)

    masked = {"n": 0}
    orig = store._masked_senate_owning_flow

    def _spy(*a, **k):
        masked["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(store, "_masked_senate_owning_flow", _spy)
    applied = {"n": 0}
    orig_apply = store._apply_senate_submit_feedback

    def _spy_apply(feedback):
        applied["n"] += 1
        return orig_apply(feedback)

    monkeypatch.setattr(store, "_apply_senate_submit_feedback", _spy_apply)

    fb = store.doSubmitSenateProposals([])

    assert masked["n"] == 0, masked
    assert store._committed_receipt is None
    pid, record = _published(state)
    assert pid and record, (fb, pid)
    assert (fb.get("data") or {}).get("created"), fb
    assert applied["n"] >= 1, applied
    assert store.senateAiProposerBlocked is False


def test_d13_t09_registered_no_provider_fails_closed():
    state = _ai_consul_state()
    _assert_fixture(state)
    store = GuiSessionStore(state)
    receiver = _Receiver(store)
    store._viewer_id = "player1"
    store._seat_lifecycle = SEAT_ACTIVE
    store._senate_view = dict(SENATE_VIEW)
    # no barrier provider -> NO masked transaction may be opened
    fb = store.doSubmitSenateProposals([])
    assert store._committed_receipt is None
    pid, record = _published(state)
    assert pid is None and record is None, (pid, record)
    assert fb.get("success") is False, fb
    assert store._seat_lifecycle == SEAT_ACTIVE
    assert store.senateAiProposerBlocked is False


# ===========================================================================
# D13-T11 — activation frame failure is captured (not a green receipt)
# ===========================================================================
def test_d13_t11_unmask_witness_false_is_a_real_failure(monkeypatch):
    state = _ai_consul_state()
    _assert_fixture(state)
    witness = _SyncWitness(None, fail_unmask=True)
    store, witness, receiver = _active_store(state, witness=witness)
    witness.store = store

    def auto_submit_proposals(state_, *a, **k):
        return session_access.denied_response()

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)

    finished = []
    store.handoffFinished.connect(lambda txn, ok: finished.append(ok))

    store.doSubmitSenateProposals([])

    assert store._seat_lifecycle == SEAT_MASKED_FAILURE, store._seat_lifecycle
    assert finished and finished[-1] is False, finished
    assert store._activation_result is not None
    assert store._activation_result.get("success") is False, store._activation_result
    # the guard is NOT cleared by a failed reveal, and the reason was NOT replayed
    assert store.senateAiProposerBlocked is True
    assert not any(msg == _reason_msg() for _kind, msg in receiver.feedback), \
        receiver.feedback


# ===========================================================================
# D13-T12 / T13 — ordinary rejection / already-submitted never lock
# ===========================================================================
def _run_rejection(monkeypatch, envelope, state=None):
    state = state or _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    def auto_submit_proposals(state_, *a, **k):
        return dict(envelope)

    monkeypatch.setattr(senate_api, "auto_submit_proposals", auto_submit_proposals)
    fb = store.doSubmitSenateProposals([])
    return state, store, fb, receiver


def test_d13_t12_ordinary_validation_rejection_does_not_lock(monkeypatch):
    """F04: a non-DENIED rejection never locks AND the corrected retry REALLY
    publishes (a real package / real refs — never a synthetic ``success=True``)."""
    envelope = {
        "success": False,
        "message": "提案校验失败：预算金额不合法",
        "data": {},
        "errors": [{"code": "NON_WAR_PROPOSAL_INVALID", "scope": "package",
                    "message": "提案校验失败：预算金额不合法"}],
    }
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)
    original = senate_api.auto_submit_proposals

    @wraps(original)
    def _rejecting(state_, *a, **k):
        return dict(envelope)

    monkeypatch.setattr(senate_api, "auto_submit_proposals", _rejecting)
    fb = store.doSubmitSenateProposals([])

    assert store._seat_lifecycle == SEAT_ACTIVE
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    assert not any(msg == _reason_msg() for _kind, msg in receiver.feedback), \
        receiver.feedback
    assert fb.get("message") == "提案校验失败：预算金额不合法", fb
    assert "已自动提交" not in (fb.get("message") or "")
    assert any((i.get("code") or "") == "NON_WAR_PROPOSAL_INVALID"
               for i in store._senate_submit_errors), store._senate_submit_errors
    assert _published(state)[0] is None   # the rejection published nothing

    # ---- corrected retry: the REAL AI intent + REAL Core publication --------
    monkeypatch.setattr(senate_api, "auto_submit_proposals", original)
    fb2 = store.doSubmitSenateProposals([])

    pid, record = _published(state)
    assert fb2.get("success") is True, fb2
    assert pid and record, (fb2, pid, record)
    assert record.get("proposal_refs"), record
    created = (store._committed_receipt.get("data") or {}).get("created")
    assert [item["proposal_id"] for item in created] == record["proposal_refs"]
    assert (store._committed_receipt.get("data") or {}).get("package_id") == pid
    assert len(_packages(state)) == 1, _packages(state)
    assert store.senateAiProposerBlocked is False
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle


def test_d13_t12b_real_validation_rejection_then_real_publish():
    """F04: a REAL Core validation rejection (``NON_WAR_PROPOSAL_INVALID``)
    through the real owning flow, then a REAL corrected publication."""
    state = _human_owner_state()
    state.set_current_player("player1")
    store, witness, receiver = _active_store(
        state, viewer="player1",
        senate_view={"phase_id": "senate", "current_phase_id": "senate",
                     "viewer_player_id": "player1", "current_step": "proposal",
                     "viewer_has_consul": True, "is_current_player": True})
    from src.core.systems.political_system import PoliticalSystem
    assert PoliticalSystem(state).resolve_proposal_control("player1")["mode"] == "HUMAN"

    fb = store.doSubmitSenateProposals([{"type": "bogus"}])

    # a REAL Core rejection (typed, non-DENIED) published nothing and locked nothing
    assert fb.get("success") is False, fb
    assert "已自动提交" not in (fb.get("message") or ""), fb
    codes = {i.get("code") for i in store._senate_submit_errors}
    assert "NON_WAR_PROPOSAL_INVALID" in codes, store._senate_submit_errors
    assert "DENIED" not in codes, store._senate_submit_errors
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    assert _published(state)[0] is None
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle

    # ---- corrected proposal: REAL dispatch + REAL package -------------------
    contract_id = getattr(state, "_d13_contract_id")
    fb2 = store.doSubmitSenateProposals([
        {"type": "budget", "params": {"contract_id": contract_id,
                                       "modified_budget": 100}}])

    pid, record = _published(state)
    assert fb2.get("success") is True, fb2
    assert pid and record, (fb2, pid, record)
    assert record.get("proposal_refs"), record
    created = (store._committed_receipt.get("data") or {}).get("created")
    assert [item["proposal_id"] for item in created] == record["proposal_refs"]
    assert (store._committed_receipt.get("data") or {}).get("package_id") == pid
    assert state.get_senate_proposals(), state.get_senate_proposals()
    assert store.senateAiProposerBlocked is False



def test_d13_t13_already_submitted_does_not_lock(monkeypatch):
    state = _ai_consul_state()
    envelope = {
        "success": False,
        "message": "本会期已提交，请查看已提交内容",
        "data": {},
        "errors": [{"code": "PACKAGE_ALREADY_SUBMITTED", "scope": "package",
                    "message": "本会期已提交，请查看已提交内容"}],
    }
    state, store, fb, receiver = _run_rejection(monkeypatch, envelope, state)
    pid_before, record_before = _published(state)
    assert pid_before is None   # the synthetic rejection published nothing

    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    assert fb.get("message") == "本会期已提交，请查看已提交内容", fb
    assert not any("授权失败" in (msg or "") for _kind, msg in receiver.feedback)
    assert any((i.get("code") or "") == "PACKAGE_ALREADY_SUBMITTED"
               for i in store._senate_submit_errors), store._senate_submit_errors


# ===========================================================================
# D13-T14 — the API copies the FULL inner envelope (legacy display keys kept)
# ===========================================================================
def test_d13_t14_api_passes_through_full_envelope():
    state = _ai_consul_state(register=False)
    result = senate_api.auto_submit_proposals(
        state, land_proposal_deciders=[])
    assert result.get("success") is True, result
    data = result.get("data") or {}
    # legacy display keys are preserved
    assert "proposals" in data and "created" in data, data
    assert data["created"], data
    # the inner canonical envelope is copied, not selectively re-derived
    assert "delivery" in data, data
    assert (data.get("delivery") or {}).get("outcome") in ("CONTINUE", "RESOLVED"), data
    assert "awaiting_player_id" in data, data
    assert result.get("errors") == [], result.get("errors")


def test_d13_t14b_failure_message_is_not_a_success_claim():
    """A denied child publish must keep the REAL message and TYPED errors."""
    state = _ai_consul_state(register=False)
    # register AFTER building the (CLI-exempt) state so the child is denied
    session_access.register_hotseat_session(state, "player1", epoch=0)
    result = senate_api.auto_submit_proposals(
        state, land_proposal_deciders=[])
    assert result.get("success") is False, result
    assert result.get("message") != "已自动提交 0 项提案", result
    assert result.get("message") == session_access.DENIED_MESSAGE, result
    assert any(isinstance(e, dict) and e.get("code") == "DENIED"
               for e in (result.get("errors") or [])), result


def test_d13_t14_four_delivery_types(monkeypatch):
    """T14 — the four delivery classifications, each from a REAL fact.

    CONTINUE/HUMAN and RESOLVED/HUMAN come from real publications; the
    RESOLVED/AI case must fail closed (never a same-seat fallback); a typed vs
    legacy contradiction is resolved by the TYPED delivery only.
    """
    # ---- 1) CONTINUE / HUMAN (real non-empty publish) ----------------------
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)
    fb = store.doSubmitSenateProposals([])
    delivery = (store._committed_receipt.get("data") or {}).get("delivery") or {}
    assert delivery.get("outcome") == "CONTINUE", (delivery, fb)
    assert (delivery.get("next") or {}).get("controller") == "HUMAN", delivery
    assert (delivery.get("next") or {}).get("actor_player_id") == "player1", delivery

    # ---- 2) RESOLVED / HUMAN (real lawful empty package) -------------------
    state2 = _ai_consul_state(budget=False)
    state2.config.testing.propose_war_chance = 0.0
    state2.config.testing.always_declare = False
    state2.config.political_rules.land_proposal.sale_chance = 0.0
    state2.config.political_rules.land_proposal.distribution_chance = 0.0
    _assert_fixture(state2)
    store2, witness2, receiver2 = _active_store(state2)
    fb2 = store2.doSubmitSenateProposals([])
    data2 = store2._committed_receipt.get("data") or {}
    delivery2 = data2.get("delivery") or {}
    assert fb2.get("success") is True, fb2
    assert delivery2.get("outcome") == "RESOLVED", (delivery2, fb2)
    assert data2.get("controller") == "HUMAN", data2
    assert (delivery2.get("next") or {}).get("controller") == "HUMAN", delivery2
    assert store2._seat_lifecycle == SEAT_ACTIVE, store2._seat_lifecycle

    # ---- 3) RESOLVED / AI -> fail closed (never an AI ACTIVE seat) ---------
    state3 = _ai_consul_state()
    _assert_fixture(state3)
    store3, witness3, receiver3 = _active_store(state3)
    finished = []
    store3.handoffFinished.connect(lambda txn, ok: finished.append(ok))

    result3 = store3._settle_after_senate_command(
        "txn-ai", {"success": True,
                   "data": {"status": "resolved", "controller": "AI",
                            "awaiting_player_id": "player2"}})

    assert result3.get("success") is False, result3
    assert store3._seat_lifecycle == SEAT_MASKED_FAILURE, store3._seat_lifecycle
    assert finished == [False], finished
    assert store3._handoff_failure_kind == "after_commit", store3._handoff_failure_kind

    # ---- 4) typed / legacy contradiction: REJECTED (never "typed wins") ----
    # A REAL, complete delivery (real publication, real identity / receipt /
    # obligation) with exactly ONE legacy sibling changed. The frozen rule is
    # "contradiction rejected": the REAL validator + the REAL settle run here
    # (no ``_settle_seat_after_success`` stub, no validator stub).
    state4 = _ai_consul_state()
    _assert_fixture(state4)
    store4, witness4, receiver4 = _active_store(state4)
    first4 = store4.doSubmitSenateProposals([])
    assert first4.get("success") is True, first4
    receipt4 = store4._committed_receipt or {}
    data4 = dict(receipt4.get("data") or {})
    delivery4 = dict(data4.get("delivery") or {})
    assert delivery4.get("outcome") == "CONTINUE", (delivery4, first4)
    assert (delivery4.get("next") or {}).get("actor_player_id") == "player1", delivery4
    assert data4.get("awaiting_player_id") == "player1", data4
    pid4, record4 = _published(state4)
    assert pid4 and record4, (first4, pid4)
    refs4 = list(record4.get("proposal_refs") or [])
    packages4 = _packages(state4)
    pendings4 = list(witness4.pendings)

    # only the ONE legacy sibling changes: awaiting_player_id contradicts the
    # typed delivery's next actor (identity / receipt / obligation untouched).
    data4["awaiting_player_id"] = "player2"
    tampered = dict(receipt4)
    tampered["data"] = data4
    finished4 = []
    store4.handoffFinished.connect(lambda txn, ok: finished4.append(ok))

    result4 = store4._settle_after_senate_command("txn-legacy", tampered)

    err4 = (result4.get("data") or {}).get("delivery_error") or {}
    assert result4.get("success") is False, result4
    assert err4.get("code") == "DELIVERY_MISMATCH", err4
    assert err4.get("stage") == "legacy", err4
    # MASKED_FAILURE: no takeover and no new ACTIVE seat
    assert store4._seat_lifecycle == SEAT_MASKED_FAILURE, store4._seat_lifecycle
    assert store4.seatLifecycle != "ACTIVE", store4.seatLifecycle
    assert finished4 and finished4[-1] is False, finished4
    assert witness4.pendings == pendings4, witness4.pendings
    assert store4._pending_player_id == "", store4._pending_player_id
    assert store4._pending_token == "", store4._pending_token
    # the already-committed package is unchanged
    pid4_after, record4_after = _published(state4)
    assert pid4_after == pid4, (pid4, pid4_after)
    assert record4_after == record4
    assert list(record4_after.get("proposal_refs") or []) == refs4
    assert _packages(state4) == packages4


# ===========================================================================
# R1a closure — D13-T03 (Core idempotency) / T10 (independent terminal) /
#                T11a-T11b (delayed async gates).  NO product file is touched.
# ===========================================================================
def _packages(state):
    """Read-only view of the canonical PackageRecord ledger (no mutation)."""
    return dict(state._senate_package_ledger["packages"])


def _proposal_ids(state):
    return sorted(int(p.get("id")) for p in state.get_senate_proposals()
                  if p.get("id") is not None)


def _error_codes(feedback):
    return {e.get("code") for e in (feedback or {}).get("errors") or []
            if isinstance(e, dict)}


def _handle_neutral(state):
    """True when no USABLE public handle is presented (absent or revoked).

    The masked transaction either revoked the current issuance
    (``suspend_hotseat_session``) or cleared it under the authority commit
    (``commit_hotseat_principal`` -> ``handle_id = ""``), so no public read/write
    can observe the seat until the final reveal issues a fresh handle.
    """
    ctx = session_access.present_context(state)
    return ctx is None or ctx.revoked is True


def _counting_auto(counter):
    """Count REAL child submissions without changing the boundary identity.

    ``ApiAdapter.call`` passes ``api_func.__name__`` as the owning-scope helper
    label, so the wrapper MUST keep the original name (``functools.wraps``) or the
    internal guarded boundary denies the call (a test artefact, not a product
    behaviour).
    """
    original = senate_api.auto_submit_proposals

    @wraps(original)
    def _auto(*a, **k):
        counter["n"] += 1
        return original(*a, **k)

    return _auto


# ---------------------------------------------------------------------------
# D13-T03 — Core idempotency (the Store refusal is NOT the Core gate)
# ---------------------------------------------------------------------------
def test_d13_t03_core_idempotency_after_full_completion(monkeypatch):
    """T03 — a SECOND submit never publishes again.

    Two independent facts, asserted separately (never conflated):

    1. the REAL Store route after the first full completion: the AI owning branch
       re-runs the whole masked transaction and Core itself refuses with the typed
       ``PACKAGE_ALREADY_SUBMITTED``. The Store never presents this as a success and
       never re-publishes. (If the Store HAD stopped earlier with a Store-local
       refusal, that refusal could not be claimed as Core idempotency — hence the
       separate check below.)
    2. the SAME Core protection reached through a legitimate owning dispatch (real
       lease, real dispatch nesting, real ``auto_submit_proposals``), independent
       of the Store's routing: the second submission is refused with the typed
       code and the package identity/refs/proposal set are unchanged.

    The witness here is the synchronous one, so every gate completes inline: the
    assertion is made on the COMPLETED business feedback, never on a pending
    return value.
    """
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    # ---- first submission: a real, complete Core publication -----------------
    first = store.doSubmitSenateProposals([])
    assert first.get("success") is True, first
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    pid, record = _published(state)
    assert pid and record, (first, pid)
    assert record.get("proposal_refs"), record
    packages_before = _packages(state)
    proposal_ids_before = _proposal_ids(state)
    assert len(packages_before) == 1, packages_before
    assert proposal_ids_before, proposal_ids_before

    submissions = {"n": 0}
    monkeypatch.setattr(senate_api, "auto_submit_proposals", _counting_auto(submissions))

    # ---- (1) the REAL Store re-submit route ---------------------------------
    second = store.doSubmitSenateProposals([])
    assert second.get("success") is False, second
    # the Store really re-driven the owning command (and Core really answered):
    # this rejection is the CORE gate, not a Store-local refusal that could be
    # mistaken for Core idempotency.
    assert submissions["n"] == 1, (submissions, second)
    assert "PACKAGE_ALREADY_SUBMITTED" in _error_codes(second), second
    # the failure copy is preserved (never a "已自动提交 N 项提案" success claim)
    assert "已自动提交" not in (second.get("message") or ""), second
    # the SAME typed error is visible again through the existing error surface
    assert "PACKAGE_ALREADY_SUBMITTED" in {
        i.get("code") for i in store._senate_submit_errors}, store._senate_submit_errors
    # an already-submitted business refusal is NOT an authorization failure
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_block_key is None
    assert not any("授权失败" in (msg or "") for _kind, msg in receiver.feedback)
    # the seat recovered to ACTIVE (same seat, new epoch) with no masked failure
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert store._handoff_failure_kind == "", store._handoff_failure_kind
    # nothing was published again
    assert _packages(state) == packages_before, _packages(state)
    assert _proposal_ids(state) == proposal_ids_before
    assert _published(state)[0] == pid

    # ---- (2) the SAME protection through a legitimate owning dispatch -------
    # Independent of the Store's routing: real one-use lease -> real dispatch
    # nesting -> the real AI child API. Core must refuse again with the typed
    # code and keep every canonical identity unchanged.
    attempts = {"n": 0}

    def _dispatch():
        attempts["n"] += 1
        return senate_api.auto_submit_proposals(state)

    dup = store._masked_senate_owning_flow(
        "doSubmitSenateProposals", "propose_many", _dispatch)

    assert attempts["n"] == 1, attempts
    assert submissions["n"] == 2, submissions
    receipt = store._committed_receipt
    # a non-mutating business refusal returns the SAME committed feedback
    assert receipt is not None and receipt is dup, (receipt, dup)
    assert receipt.get("success") is False, receipt
    assert "PACKAGE_ALREADY_SUBMITTED" in _error_codes(receipt), receipt
    assert "已自动提交" not in (receipt.get("message") or ""), receipt
    assert store.senateAiProposerBlocked is False
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert store._handoff_failure_kind == "", store._handoff_failure_kind

    # ---- no second publication: every canonical identity is unchanged -------
    pid2, record2 = _published(state)
    assert pid2 == pid, (pid, pid2)
    assert record2 == record, (record, record2)
    assert (record2.get("proposal_refs") or []) == (record.get("proposal_refs") or [])
    assert len(_packages(state)) == 1, _packages(state)
    assert _packages(state) == packages_before
    assert _proposal_ids(state) == proposal_ids_before


# ---------------------------------------------------------------------------
# D13-T10 — independent EMPTY-package terminal (canonical result == receipt)
# ---------------------------------------------------------------------------
def test_d13_t10_independent_empty_package_terminal():
    """T10 — a LAWKUL empty package reaches its own terminal.

    The package is genuinely empty (zero proposal refs, zero proposals) and the
    terminal is written by the canonical finalizer inside the owning dispatch, so
    the terminal receipt and the canonical senate phase result MUST agree:

      * outcome RESOLVED with a HUMAN result owner (the ACTIVE receiver);
      * the terminal's ``finalization_id`` IS ``senate_api.senate_finalization_id``;
      * the canonical ``phase_result('senate')`` carries the empty decision.

    The terminal is NOT back-propagated into the non-empty publication moment:
    T01 (non-empty) stays CONTINUE/HUMAN-ballot; THIS fixture is the only place a
    RESOLVED/HUMAN delivery is asserted.
    """
    state = _ai_consul_state(budget=False)
    # zero every AI proposal source -> a deterministic LAWFUL empty package
    state.config.testing.propose_war_chance = 0.0
    state.config.testing.always_declare = False
    state.config.political_rules.land_proposal.sale_chance = 0.0
    state.config.political_rules.land_proposal.distribution_chance = 0.0
    _assert_fixture(state)
    store, witness, receiver = _active_store(state)

    fb = store.doSubmitSenateProposals([])
    receipt = store._committed_receipt
    assert fb.get("success") is True, (fb, receipt)
    assert receipt is not None and receipt.get("success") is True, receipt

    pid, record = _published(state)
    assert pid and record, (pid, record)
    assert (record.get("proposal_refs") or []) == [], record
    assert state.get_senate_proposals() == [], state.get_senate_proposals()

    # ---- canonical phase result -------------------------------------------
    phase_result = state.get_phase_result("senate")
    assert phase_result is not None, "the canonical senate phase result was not written"
    assert phase_result.get("success") is True, phase_result
    result_data = phase_result.get("data") or {}
    assert result_data.get("passed_proposals") == [], result_data
    assert result_data.get("rejected_proposals") == [], result_data
    assert result_data.get("vetoed_proposals") == [], result_data
    announcement = result_data.get("public_announcement") or {}
    assert announcement.get("enacted_proposals") == [], announcement
    assert "frozen_war_decisions" in result_data, result_data
    session_id = state.get_senate_session() or SESSION_ID
    assert state.has_senate_finalization_receipt(session_id) is True

    # ---- terminal receipt == canonical result ------------------------------
    data = receipt.get("data") or {}
    delivery = data.get("delivery") or {}
    terminal = delivery.get("terminal") or {}
    assert delivery.get("outcome") == "RESOLVED", (delivery, data)
    assert data.get("created") == [], data
    assert data.get("status") == "resolved", data
    assert data.get("controller") == "HUMAN", data
    assert terminal.get("status") == "resolved", terminal
    assert terminal.get("phase") == "senate", terminal
    assert terminal.get("controller") == "HUMAN", terminal
    assert terminal.get("actor") == "player1", terminal
    assert terminal.get("awaiting_player_id") == "player1", terminal
    assert list(terminal.get("finalization_id")) == list(
        senate_api.senate_finalization_id(state)), terminal
    # the delivered receiver IS the ACTIVE HUMAN seat
    nxt = delivery.get("next") or {}
    assert nxt.get("actor_player_id") == "player1", nxt
    assert nxt.get("controller") == "HUMAN", nxt
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert store._viewer_id == "player1"
    assert store._handoff_failure_kind == "", store._handoff_failure_kind
    assert store._activation_result.get("success") is True, store._activation_result


# ---------------------------------------------------------------------------
# D13-T11a / T11b — delayed ASYNC gates, production shape
# ---------------------------------------------------------------------------
class _AsyncWitness:
    """Production-shape barrier provider: frames arrive asynchronously.

    Mirrors ``src/ui/gui/app.py``: the legacy synchronous gates NEVER claim a
    frame (they return False); only the ``*_async`` methods begin a real gate and
    the receipt is delivered later through the callback.
    """

    def __init__(self, store=None):
        self.store = store
        self.calls = []
        self.gates = []          # [(kind, txn, receipt_cb)]
        self.pendings = []
        self.failures = []
        self.masked_senate_views = []

    # -- legacy synchronous gates: no frame is ever claimed ------------------
    def arm_barrier(self, txn):
        self.calls.append(("arm_sync", txn))
        return False

    def request_unmask(self, txn):
        self.calls.append(("unmask_sync", txn))
        return False

    def _snap(self):
        if self.store is not None:
            self.masked_senate_views.append(dict(self.store._senate_view or {}))

    # -- real async frame gates ---------------------------------------------
    def arm_barrier_async(self, txn, cb):
        self.calls.append(("arm", txn))
        self._snap()
        self.gates.append(("arm", txn, cb))

    def publish_under_mask_async(self, txn, cb):
        self.calls.append(("publish", txn))
        self._snap()
        self.gates.append(("publish", txn, cb))

    def request_unmask_async(self, txn, cb):
        self.calls.append(("unmask", txn))
        self._snap()
        self.gates.append(("unmask", txn, cb))

    # -- copy updates (not frame gates) --------------------------------------
    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction))
        self.pendings.append(faction)
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        self.failures.append((kind, route))
        return True

    def pending_kind(self):
        return self.gates[0][0] if self.gates else None

    def fire(self, kind, ok=True):
        """Deliver ONE real frame receipt (exactly once, in order)."""
        for idx, (gate_kind, txn, cb) in enumerate(self.gates):
            if gate_kind == kind:
                self.gates.pop(idx)
                cb(txn, gate_kind, ok)
                return True
        return False


def _async_store(state):
    witness = _AsyncWitness()
    store, witness, receiver = _active_store(state, witness=witness)
    witness.store = store
    return store, witness, receiver


def test_d13_t11a_async_arm_publish_unmask_are_ordered(monkeypatch):
    """T11a — the three real frames are released one by one.

    Facts asserted at each suspension point (never inferred from the receipt):

      * before the ARM frame: nothing submitted; DTO neutral; no ACTIVE seat;
        no public handle;
      * after the ARM frame: exactly ONE owning dispatch / ONE publication;
        the publish gate is pending; DTO still neutral; still no handle;
      * after the PUBLISH frame: authority committed, reveal pending, DTO still
        neutral, still no public handle;
      * after the UNMASK frame: ACTIVE with the correct receiver/lifecycle.

    The REAL ``_settle_after_senate_command`` return value is captured through a
    wrapper that calls the original; the synchronous return of a suspended
    activation is a PENDING envelope, so ``handoffFinished`` — not that return and
    not the committed receipt — is the completion proof.
    """
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _async_store(state)

    submissions = {"n": 0}
    monkeypatch.setattr(senate_api, "auto_submit_proposals", _counting_auto(submissions))

    settled = []
    orig_settle = store._settle_after_senate_command

    def _settle(txn_id, feedback, done=None):
        result = orig_settle(txn_id, feedback, done=done)
        settled.append((txn_id, dict(feedback), result))
        return result

    monkeypatch.setattr(store, "_settle_after_senate_command", _settle)

    finished = []
    store.handoffFinished.connect(lambda txn, ok: finished.append(ok))

    # ---- the call SUSPENDS on the arm frame -----------------------------
    first = store.doSubmitSenateProposals([])
    assert first.get("success") is True, first
    assert (first.get("data") or {}).get("pending") is True, first
    assert witness.pending_kind() == "arm", witness.gates

    # BEFORE arm: nothing reached Core, nothing published
    assert submissions["n"] == 0, submissions
    pid, record = _published(state)
    assert pid is None and record is None, (pid, record)
    assert state.get_senate_proposals() == []
    assert _packages(state) == {}
    # DTO neutral + no ACTIVE seat + no public handle
    assert store._senate_view == {}, store._senate_view
    assert store.senateSubmittedProposals == []
    assert store.seatLifecycle != "ACTIVE", store.seatLifecycle
    assert store.handoffMaskVisible is True
    assert _handle_neutral(state) is True
    assert finished == [], finished

    # ---- ARM frame receipt -> the owning dispatch runs ------------------
    assert witness.fire("arm") is True
    assert submissions["n"] == 1, submissions
    pid, record = _published(state)
    assert pid and record, (pid, record)
    assert len(_packages(state)) == 1, _packages(state)
    assert witness.pending_kind() == "publish", witness.gates

    # after arm / before publish: still masked & neutral
    assert store._senate_view == {}, store._senate_view
    assert store.senateSubmittedProposals == []
    assert store.seatLifecycle != "ACTIVE", store.seatLifecycle
    assert _handle_neutral(state) is True
    assert finished == [], finished
    assert submissions["n"] == 1

    # ---- PUBLISH frame receipt -----------------------------------------
    assert witness.fire("publish") is True
    assert witness.pending_kind() == "unmask", witness.gates
    assert store._reveal_pending is True
    assert store.seatLifecycle != "ACTIVE", store.seatLifecycle
    assert store.handoffMaskVisible is True
    assert store._senate_view == {}, store._senate_view
    assert _handle_neutral(state) is True
    assert finished == [], finished

    # ---- UNMASK frame receipt: completion ------------------------------
    assert witness.fire("unmask") is True
    assert witness.gates == [], witness.gates
    assert finished == [True], finished
    assert store._seat_lifecycle == SEAT_ACTIVE, store._seat_lifecycle
    assert store._viewer_id == "player1"
    assert store._handoff_failure_kind == ""
    assert store.seatEpoch >= 1
    assert _handle_neutral(state) is False
    assert session_access.present_context(state).revoked is False
    assert submissions["n"] == 1, "the package must be submitted exactly once"

    # ---- the REAL settle result + the delivered receiver -------------------
    assert settled, "the real _settle_after_senate_command never ran"
    _txn, fb, settle_result = settled[-1]
    data = fb.get("data") or {}
    delivery = data.get("delivery") or {}
    assert delivery.get("outcome") == "CONTINUE", delivery
    nxt = delivery.get("next") or {}
    assert nxt.get("actor_player_id") == "player1", nxt
    assert nxt.get("controller") == "HUMAN", nxt
    # the settle's SYNCHRONOUS return was a pending envelope (activation suspended)
    assert isinstance(settle_result, dict), settle_result
    assert (settle_result.get("data") or {}).get("pending") is True, settle_result
    # the real activation result is the post-reveal success
    assert store._activation_result.get("success") is True, store._activation_result
    assert (store._activation_result.get("data") or {}).get("activated") is True
    # the ACTIVE projection is the real receiver DTO again
    assert store.senateSubmittedProposals, store.senateSubmittedProposals
    assert state.get_senate_proposals()


def test_d13_t11b_async_publish_frame_false_is_a_real_failure():
    """T11b — a FALSE frame receipt must be captured as a real failure.

    The Core publication already committed when the publish gate fails, so the
    committed receipt is NOT delivery proof. The test asserts
    ``handoffFinished(False)``, ``SEAT_MASKED_FAILURE`` and the failed activation
    result — a green-but-not-delivered state would turn this test red.
    """
    state = _ai_consul_state()
    _assert_fixture(state)
    store, witness, receiver = _async_store(state)

    finished = []
    store.handoffFinished.connect(lambda txn, ok: finished.append(ok))

    first = store.doSubmitSenateProposals([])
    assert (first.get("data") or {}).get("pending") is True, first
    assert witness.pending_kind() == "arm", witness.gates

    assert witness.fire("arm") is True
    pid, record = _published(state)
    assert pid and record, (pid, record)
    # the publication is committed BEFORE the failing gate
    assert store._committed_receipt is not None
    assert store._committed_receipt.get("success") is True
    assert witness.pending_kind() == "publish", witness.gates

    assert witness.fire("publish", ok=False) is True

    assert store._seat_lifecycle == SEAT_MASKED_FAILURE, store._seat_lifecycle
    assert finished == [False], finished
    assert store._activation_result is not None
    assert store._activation_result.get("success") is False, store._activation_result
    assert store._handoff_failure_kind == "after_commit", store._handoff_failure_kind
    assert witness.failures, witness.failures
    # fail closed: no usable public handle, neutral DTO, no unmask gate opened
    assert _handle_neutral(state) is True
    assert store._senate_view == {}, store._senate_view
    assert witness.pending_kind() is None, witness.gates
    assert not any(c[0] == "unmask" for c in witness.calls), witness.calls
    # the subscription to the committed receipt is NOT a success claim
    assert store._committed_receipt.get("success") is True


# ===========================================================================
# Errata E-D13-4.4 — success-clear OWNERSHIP (same owner clears / other keeps)
#
# The lock exists to stop ONE AI proposer from retrying. A business success may
# clear it only when it is attributable to the SAME owner (origin == lock key);
# a foreign or unprovable origin keeps it (fail-closed, E-D13-4.2).
# ===========================================================================
def _e4_lock(monkeypatch):
    """Build the Option-4 lock through the REAL T06 chain (never seeded)."""
    original = senate_api.auto_submit_proposals
    state, store, witness, receiver = _real_denied_lock(monkeypatch)
    assert store._senate_ai_proposer_block_key == (SESSION_ID, "proposal", "player1"), \
        store._senate_ai_proposer_block_key
    return original, state, store, witness, receiver


def test_d13_e4_success_clear_same_owner_clears(monkeypatch):
    """E-D13-4.4(1): same-owner success dispatch -> three-way clear + notify.

    The final reveal is failed on purpose (``fail_unmask``) so the projection
    sync can NEVER be the source of the clear: the only possible source is the
    real dispatch success, and the seat ends MASKED_FAILURE while the lock is
    already cleared.
    """
    original, state, store, witness, receiver = _e4_lock(monkeypatch)
    monkeypatch.setattr(senate_api, "auto_submit_proposals", original)
    witness.fail_unmask = True

    seen = []
    store.senateViewChanged.connect(
        lambda: seen.append((store.senateAiProposerBlocked,
                             store._senate_ai_proposer_blocked_reason,
                             store._senate_ai_proposer_block_key)))

    fb = store.doSubmitSenateProposals([])

    # the dispatch really succeeded (a real package exists)
    pid, record = _published(state)
    assert pid and record, (fb, pid)
    # the clear happened at the success point, not via any projection
    assert store.senateAiProposerBlocked is False
    assert store._senate_ai_proposer_blocked_reason == ""
    assert store._senate_ai_proposer_block_key is None
    assert (False, "", None) in seen, seen
    # no projection was ever re-staged (the reveal failed)
    assert store._seat_lifecycle == SEAT_MASKED_FAILURE, store._seat_lifecycle


def test_d13_e4_success_clear_cross_owner_keeps(monkeypatch):
    """E-D13-4.4(2): a DIFFERENT owner's successful dispatch keeps the lock.

    The lock belongs to ``(turn-1, proposal, player1)``; the owning flow is
    driven with the real dispatch but the production ``ai_proposer_origin``
    value a different viewer would carry. The async witness suspends the
    transaction at the publish gate, i.e. BEFORE any projection is staged, so
    the asserted guard state is exactly the success-clear decision.
    """
    original, state, store, witness, receiver = _e4_lock(monkeypatch)
    key_before = store._senate_ai_proposer_block_key

    async_witness = _AsyncWitness(store)
    store.setHandoffBarrierProvider(async_witness)
    monkeypatch.setattr(senate_api, "auto_submit_proposals", original)

    store._masked_senate_owning_flow(
        "doSubmitSenateProposals", "propose_many",
        lambda: senate_api.auto_submit_proposals(state),
        ai_proposer_origin=(SESSION_ID, "proposal", "player2"))
    assert async_witness.pending_kind() == "arm", async_witness.gates

    async_witness.fire("arm")

    # the OTHER owner's real publication happened...
    pid, record = _published(state)
    assert pid and record, (pid, record)
    assert async_witness.pending_kind() == "publish", async_witness.gates
    # ...and it did NOT clear this seat's lock
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_blocked_reason == store.AI_PROPOSER_BLOCK_REASON
    assert store._senate_ai_proposer_block_key == key_before, \
        store._senate_ai_proposer_block_key


def test_d13_e4_success_clear_missing_identity_keeps(monkeypatch):
    """E-D13-4.4(3): a success with NO provable origin keeps the lock.

    Production entry: with the cached step off ``proposal`` the Store cannot
    build an origin, so it passes ``ai_proposer_origin=None`` into the real
    owning flow. An unprovable owner must fail closed (keep), never "any
    success clears".
    """
    original, state, store, witness, receiver = _e4_lock(monkeypatch)
    key_before = store._senate_ai_proposer_block_key

    async_witness = _AsyncWitness(store)
    store.setHandoffBarrierProvider(async_witness)
    monkeypatch.setattr(senate_api, "auto_submit_proposals", original)

    # the identity source is genuinely unavailable at the call site
    store._senate_view["current_step"] = "senate_vote"
    assert store._senate_ai_proposer_origin() is None

    store.doSubmitSenateProposals([])
    assert async_witness.pending_kind() == "arm", async_witness.gates
    async_witness.fire("arm")

    pid, record = _published(state)
    assert pid and record, (pid, record)
    assert async_witness.pending_kind() == "publish", async_witness.gates
    assert store.senateAiProposerBlocked is True
    assert store._senate_ai_proposer_block_key == key_before, \
        store._senate_ai_proposer_block_key
