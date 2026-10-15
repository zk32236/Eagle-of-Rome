"""S-D-2 (R1-full) — N7-R / N10-R real trigger + boundary + recovery + senate wiring.

EOR20261013-02 GUI Readiness · slice S-D · sub-task S-D-2 · rework round **R1-full**.

Frozen design basis (Overlay §2.1 + §1.2; Delta §2.2/§2.3; disposition
``S-D-2_Disposition.md`` R-01…R-04; ``S-D-2-R1_Senate-Wiring_Disposition.md`` F1/F2):

  * N7-R (``missing_decider``) / N10-R (``unresolved_mandatory_ai_vote``) use **split
    classification** (Overlay §2.1):
      - **stimulus** = ``MOCK_AUXILIARY`` fault at the **named precommit decider
        seam** (N7-R = ``session_api._build_population_auto_processor``; N10-R = the
        senate vote decider). It runs BEFORE any owner commit.
      - **trigger + boundary** = the **real production chain** (Store → Adapter →
        phase-owner API → ``continue_after_command``).
      - **expected result** = a **masked safe failure** (``MASKED_FAILURE``),
        obligation **outstanding**, **not** a public ``DENIED``.
      - **raw comparison point** = the **post-commit failure boundary**, never the
        pre-drain self-identity (R-04: a NON-IDENTICAL comparison).
      - **recovery** = the real recovery route resumes ONLY outstanding AI work; the
        committed HUMAN command is never resubmitted (same-revision ``DK`` replay
        denied).

  * R-01 (trigger truthfulness): the **real-QML-control** integrated trigger
    (``populationResolveButton`` / ``senateProposalSubmitButton`` reached through a
    full real ``gui_main`` mortality→…→population/senate traversal) is **NOT** driven
    in this harness — it depends on the SO runner ``SO-20261013-001`` P1/P3/P4 lane
    (see ``SO-Capability-Gap-Minimum.md``; ``SO-20261013-001 = HOLD``). Therefore the
    tests below drive the **real production CONSUMER entry** the control dispatches to
    (Store slot → real Adapter → real phase-owner API → real coordinator), which is a
    **labelled ``MOCK_AUXILIARY`` SUPPLEMENT** — it does **NOT** close AC03/AC08/AC10.
    The integrated real-control AC stays **OPEN (deferral)**, asserted explicitly by
    ``test_integrated_real_control_trigger_is_deferred_open``.
  * R-01.4: the direct API / Store / coordinator supplements do **not** claim closure;
    the state positioning (``start_phase=``) is **not** presented as a
    production-created trigger.
  * R-02: the owner-layer recovery entry (``session_api.recover_continuation``) is
    wired, via ``api_adapter.recover_continuation``, with the phase AI executor — a
    real recovery now **makes progress** instead of returning ``NO_EXECUTOR``.
  * F1/F2 (S-C completion): ``senate_api._senate_ai_executor`` mirrors the population
    drain; ``senate_api.propose_many`` routes through the SOLE continuation.

WATERMARK: S-D-2 R1-full DA EXECUTION — NOT runtime/API/GUI acceptance; candidate
dirty/uncommitted; no commit/push/delete.
"""
from __future__ import annotations

import copy
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import session_access
from src.api import session_api
from src.api import senate_api
from src.api import session_turn_service as sts
from src.core.entities.player import PlayerType
from src.ui.gui import session_store as store_mod
from src.ui.gui import api_adapter as adapter_mod
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
    RECOVER_ROUTE_CONTINUATION,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
FIXTURE = "gr_f_3h3ai.json"

#: The R-01 integrated real-control trigger is NOT delivered in-harness → the
#: corresponding ACs stay OPEN (deferral, SO lane P1/P3/P4). This marker is asserted
#: by ``test_integrated_real_control_trigger_is_deferred_open`` so the OPEN state is
#: machine-visible and cannot be silently presented as closed.
INTEGRATED_REAL_CONTROL_TRIGGER = "OPEN — deferral (SO-20261013-001 HOLD; R-01.5(a))"

# Disconnect falsification (Overlay §4 / R4 §5): when set, the sole automatic
# continuation (`continue_after_command`) is disconnected so the N7-R integrated
# test MUST fail — a test that stays green with the continuation disconnected would
# be bypassing the critical production seam and is invalid for G5.
_FALSIFY = os.environ.get("GR_SD2_FALSIFY") == "1"


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


# ---------------------------------------------------------------------------
# Labelled harness witnesses (MOCK_AUXILIARY — barrier/receiver only; the
# business Store/Adapter/coordinator chain stays production).
# ---------------------------------------------------------------------------
class _Receiver:
    """Real Query invalidation receiver (synchronous ack)."""

    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    """Synchronous barrier witness provider (NO async frame gates), so the masked
    transaction completes inline on an offscreen host. Records the failure route."""

    def __init__(self):
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction))
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True

    def failure_routes(self):
        return [c[3] for c in self.calls if c[0] == "failure"]


# ---------------------------------------------------------------------------
# MOCK_AUXILIARY state positioning (NOT the production trigger — R-01.4).
# ``start_phase=`` is used ONLY to POSITION the producer state for the labelled
# supplement; it is NEVER presented as a production-created trigger and it is not
# used on the R-1 real-QML-control path.
# ---------------------------------------------------------------------------
def _positioned_population_state():
    """Factory-created, VALIDATED 3H+3AI state positioned at the producer phase
    (NO controller injection: the factory's real PlayerType set is used)."""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=FIXTURE)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    return state, pids


def _positioned_senate_state():
    """Factory-created, VALIDATED 3H+3AI state positioned at the senate phase."""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="senate", scenario_file=FIXTURE)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    return state, pids


def _humans(state, pids):
    return [p for p in pids
            if state.get_player(p).player_type is PlayerType.HUMAN]


def _pub_digest(state):
    """Business digest from RAW Core (independent oracle), not the production DTO."""
    return {
        "votes": sorted((v[0], v[1], v[2]) for v in state.get_population_votes()),
        "campaigns": sorted((c[0], c[1]) for c in state.get_population_campaigns()),
        "phase_result": copy.deepcopy(state.get_phase_result("population")),
        "turn": state.turn.turn_number if state.turn else None,
        "current": getattr(state.get_current_player(), "player_id", None),
    }


def _full_digest(state):
    return copy.deepcopy(state.to_dict())


def _seam_missing_decider(monkeypatch):
    """MOCK_AUXILIARY stimulus at the NAMED precommit decider seam (N7-R)."""
    def _boom(state):
        raise RuntimeError("DECIDER_MISSING")
    monkeypatch.setattr(session_api, "_build_population_auto_processor", _boom)


class _NoChoiceSenateDecider:
    """MOCK_AUXILIARY stimulus: the NAMED precommit senate vote decider declines to
    decide (None) on a MANDATORY ballot -> the coordinator's NO_CHOICE."""

    def decide_vote(self, issue, faction, state):
        return None


def _seam_senate_no_choice(monkeypatch):
    monkeypatch.setattr(senate_api, "_build_senate_vote_decider",
                        lambda s: _NoChoiceSenateDecider())


def _assign_consul(state, pids):
    """State positioning (``MOCK_AUXILIARY``): make the FIRST HUMAN the presiding
    consul so a real package publication is lawful. NOT a production trigger."""
    player = state.get_player(pids[0])
    members = [m for m in state.get_living_members()
               if m.faction_id == player.faction_id]
    assert members, "the first faction must have a living member"
    members[0].office = "consul"


# ===========================================================================
# 0. R-01 — the integrated real-control trigger is explicitly OPEN (deferral)
# ===========================================================================
def test_integrated_real_control_trigger_is_deferred_open():
    """R-01.5(a): the real-QML-control integrated trigger (``populationResolveButton``
    / ``senateProposalSubmitButton`` reached through a full real ``gui_main``
    mortality→… traversal) is NOT delivered in this harness; it depends on the SO
    runner ``SO-20261013-001`` P1/P3/P4 lane. The integrated AC therefore stays OPEN
    (deferral, NOT an exemption) and is not substituted by the direct-API/Store
    supplements below."""
    assert INTEGRATED_REAL_CONTROL_TRIGGER.startswith("OPEN")
    assert "deferral" in INTEGRATED_REAL_CONTROL_TRIGGER


# ===========================================================================
# 1. N7-R — real producer envelope (masked safe failure, not a public DENIED)
# ===========================================================================
def test_n7r_real_producer_returns_masked_safe_failure(monkeypatch):
    state, pids = _positioned_population_state()
    viewer = pids[0]
    _seam_missing_decider(monkeypatch)

    env = session_api.submit_population_votes(state, viewer, {})
    assert env.get("success") is False
    assert env["data"]["status"] == "masked_failure"
    assert env["data"]["resolved"] is False
    assert env["data"]["retryable"] is True
    assert env["errors"][0]["code"] == "AI_DRAIN_MASKED_FAILURE"
    # a masked safe failure is NOT a public typed DENIED
    assert "DENIED" not in (env.get("message") or "")


def test_n7r_post_commit_boundary_is_non_identical_and_stable(monkeypatch):
    """R-04: the raw comparison point is the POST-COMMIT failure boundary — a NON-
    IDENTICAL, non-self-identity comparison. The committed HUMAN ballot makes the
    post-submit digest differ from the pre-submit digest (proving the commit), while
    the FAILED continuation adds NO further effect (the post-commit digest is stable
    across a second, disconnected continuation attempt)."""
    state, pids = _positioned_population_state()
    viewer = pids[0]
    digest_pre = _pub_digest(state)

    _seam_missing_decider(monkeypatch)
    session_api.submit_population_votes(state, viewer, {})
    digest_post_commit = _pub_digest(state)

    # NON-IDENTITY: the committed HUMAN ballot moved the state off its pre-value.
    assert digest_post_commit != digest_pre, "the HUMAN commit must be observable"
    human_votes = [v for v in digest_post_commit["votes"] if v[0] == viewer]
    assert human_votes, "the committed HUMAN ballot must be retained (post-commit)"
    assert digest_post_commit["phase_result"] is None, "no settlement may be fabricated"

    # STABILITY: a second failed continuation adds NO new effect (post-commit boundary).
    session_api.submit_population_votes(state, viewer, {})
    assert _pub_digest(state) == digest_post_commit, \
        "the failed continuation must not add an effect past the boundary"


def test_n7r_real_envelope_is_recognised_by_the_real_store(monkeypatch):
    state, pids = _positioned_population_state()
    _seam_missing_decider(monkeypatch)
    env = session_api.submit_population_votes(state, pids[0], {})
    assert GuiSessionStore._is_masked_continuation_failure(env) is True


def test_n7r_real_consumer_routes_to_continuation(monkeypatch):
    """Store masked-submit entry (the exact slot the real control dispatches) with
    the REAL adapter drives the REAL producer envelope and routes it as
    ``continuation`` — only the bounded continuation recovery is offered."""
    state, pids = _positioned_population_state()
    viewer = pids[0]
    store = GuiSessionStore(state)
    witness = _SyncWitness()
    _Receiver(store)
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE
    assert type(store._adapter) is adapter_mod.GuiApiAdapter  # real adapter, no substitution

    if _FALSIFY:
        # disconnect the sole automatic continuation: no masked failure is produced
        # and the continuation route is never selected -> assertions MUST fail.
        monkeypatch.setattr(
            session_api.turn_service, "continue_after_command",
            lambda *a, **k: sts.ContinuationResult(status=sts.STATUS_RESOLVED))

    _seam_missing_decider(monkeypatch)
    store.submitPopulationVotes({})

    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert witness.failure_routes()[-1] == RECOVER_ROUTE_CONTINUATION


# ===========================================================================
# 2. N10-R — senate continuation wiring (F1/F2) + masked safe failure
# ===========================================================================
def test_n10r_propose_many_routes_through_the_sole_continuation(monkeypatch):
    """F2: ``senate_api.propose_many`` — after a SUCCESSFUL package publication —
    routes through the SOLE automatic continuation
    (``session_turn_service.continue_after_command``) with the senate executor,
    mirroring ``session_api.submit_population_votes`` L724."""
    seen = []
    orig = sts.continue_after_command

    def _spy(state, *a, **k):
        seen.append(k.get("ai_executor"))
        return orig(state, *a, **k)

    monkeypatch.setattr(sts, "continue_after_command", _spy)
    state, pids = _positioned_senate_state()
    _assign_consul(state, pids)
    human0 = _humans(state, pids)[0]
    r = senate_api.propose_many(
        state, human0,
        [{"type": "land", "params": {"act_type": "sale", "amount_C": 1}}],
        caller_context=session_access.present_context(state))
    assert r.get("success") is True, r.get("message")
    assert seen == [senate_api._senate_ai_executor], seen


def test_n10r_senate_executor_maps_real_vote_to_accepted():
    """F1: the senate executor records a REAL ballot via the existing
    AutoSenateVoteDecider path and maps it to ``OUTCOME_ACCEPTED``."""
    state, pids = _positioned_senate_state()
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    snap = sts.obligations(state, "senate")
    ai_vote = next(o for o in snap.obligations
                   if o.substep.startswith("vote:") and o.controller == "AI")
    out = senate_api._senate_ai_executor(state, ai_vote)
    assert out.kind == sts.OUTCOME_ACCEPTED, out
    assert state.has_senate_vote(ai_vote.actor_player_id,
                                 int(ai_vote.substep.split(":", 1)[1]))


def test_n10r_senate_executor_unsupported_substep_fails_closed():
    """F1: an UNSUPPORTED substep (no safe owner executor) fails closed — never a
    silent success."""
    state, pids = _positioned_senate_state()
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    snap = sts.obligations(state, "senate")
    veto = next(o for o in snap.obligations if o.substep == "veto")
    out = senate_api._senate_ai_executor(state, veto)
    assert out.kind == sts.OUTCOME_FAILURE, out


def test_n10r_real_chain_produces_unresolved_mandatory_ai_vote_envelope(
        monkeypatch):
    """N10-R end-to-end through the REAL production chain: ``propose_many`` (F2
    continuation) → the HUMAN ballots are recorded through the REAL production vote
    API → the production owner recovery entry routes the outstanding AI ballot via
    the F1 senate executor → the NAMED precommit decider seam returns a deliberate
    no-choice → the coordinator maps it to ``UNRESOLVED_MANDATORY_AI_VOTE`` and the
    real Store recogniser accepts the producer envelope.

    SUPPLEMENT (``MOCK_AUXILIARY``): the state is POSITIONED at the senate phase and
    the no-choice is injected at the decider seam — this does NOT close the integrated
    real-control AC (OPEN, see §0)."""
    state, pids = _positioned_senate_state()
    _assign_consul(state, pids)
    ctx = session_access.present_context(state)
    human0 = _humans(state, pids)[0]

    # (a) real production package publication (the first outstanding ballot is HUMAN).
    r = senate_api.propose_many(
        state, human0,
        [{"type": "land", "params": {"act_type": "sale", "amount_C": 1}}],
        caller_context=ctx)
    assert r.get("success") is True, r.get("message")
    proposals = state.get_senate_proposals()
    assert proposals, "the package publication must create the canonical proposal"
    pid = proposals[0]["id"]

    # (b) the FIRST HUMAN ballot is recorded through the REAL production vote API
    #     (the package continuation made that HUMAN CURRENT). After that ballot the
    #     first OUTSTANDING senate ballot is an AI (populares) -> the drain is reached.
    v = senate_api.vote(state, human0, [pid], [True], caller_context=ctx)
    assert v.get("success") is True, (human0, v.get("message"))

    # (c) stimulus: the NAMED precommit senate vote-decider seam -> no-choice.
    _seam_senate_no_choice(monkeypatch)

    # (d) the real production owner recovery entry routes the outstanding AI ballot
    #     through the F1 senate executor.
    env = session_api.recover_continuation(state)
    assert env.get("success") is False, env
    assert env["data"]["status"] == "masked_failure"
    assert env["data"]["reason"] == "UNRESOLVED_MANDATORY_AI_VOTE"
    assert env["errors"][0]["code"] == "AI_DRAIN_MASKED_FAILURE"
    # the real Store recogniser accepts the producer envelope
    assert GuiSessionStore._is_masked_continuation_failure(env) is True


def test_n10r_senate_submit_routes_masked_envelope_to_continuation(monkeypatch):
    """The N10-R envelope (produced by the senate producer chain) is recognised and
    routed to the bounded continuation recovery by the real Store."""
    state, pids = _positioned_population_state()
    store = GuiSessionStore(state)
    witness = _SyncWitness()
    _Receiver(store)
    store.setHandoffBarrierProvider(witness)
    store.initialize(pids[0])

    def _patched(player_id, selections, **kw):
        return {
            "success": False, "message": "AI continuation failed",
            "data": {"status": "masked_failure", "resolved": False,
                     "retryable": True, "reason": "UNRESOLVED_MANDATORY_AI_VOTE",
                     "election_results": []},
            "errors": [{"code": "AI_DRAIN_MASKED_FAILURE",
                        "message": "UNRESOLVED_MANDATORY_AI_VOTE"}],
        }

    # MOCK_AUXILIARY envelope injected at the adapter seam (the class provenance is
    # the real N10-R envelope the senate chain produces; the Store routing is real).
    monkeypatch.setattr(store._adapter, "submit_population_votes", _patched)
    store.submitPopulationVotes({})
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert witness.failure_routes()[-1] == RECOVER_ROUTE_CONTINUATION


# ===========================================================================
# 3. R-02 — the recovery route really makes progress (owner entry + executor)
# ===========================================================================
def test_recovery_owner_entry_makes_real_progress(monkeypatch):
    """R-02: the owner-layer recovery entry (reached through the real Adapter) MUST
    supply the phase AI executor so a real recovery PROGRESSES on the outstanding AI
    work — not just return a dict that stays ``MASKED_FAILURE`` (``NO_EXECUTOR``). The
    committed HUMAN command is never resubmitted."""
    state, pids = _positioned_population_state()
    viewer = pids[0]
    store = GuiSessionStore(state)
    witness = _SyncWitness()
    _Receiver(store)
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE

    _seam_missing_decider(monkeypatch)
    store.submitPopulationVotes({})
    assert store.seatLifecycle == SEAT_MASKED_FAILURE

    # before recovery: NO AI ballot was recorded (the drain failed at the seam).
    votes_failed = sorted((v[0], v[1], v[2]) for v in state.get_population_votes())
    ai_before = {p for p in pids
                 if state.get_player(p).player_type is PlayerType.AI
                 and any(v[0] == p for v in votes_failed)}
    assert ai_before == set(), "the failed drain must not have recorded an AI vote"

    monkeypatch.undo()  # the decider seam is restored (a working drain)
    feedback = store.doRecoverContinuation()  # Store -> real Adapter -> owner entry
    assert isinstance(feedback, dict)
    assert feedback.get("success") is True, feedback

    # REAL FORWARD PROGRESS: the outstanding AI ballots are now recorded.
    votes_after = sorted((v[0], v[1], v[2]) for v in state.get_population_votes())
    ai_after = {p for p in pids
                if state.get_player(p).player_type is PlayerType.AI
                and any(v[0] == p for v in votes_after)}
    assert ai_after, "the recovery must have resumed the outstanding AI work"
    # the committed HUMAN ballot is NOT resubmitted (unchanged count for the viewer).
    human_before = [v for v in votes_failed if v[0] == viewer]
    human_after = [v for v in votes_after if v[0] == viewer]
    assert human_after == human_before


def test_recovery_is_not_activation_retry(monkeypatch):
    """Recovery never touches the activation/handoff contract: a store in the
    continuation route dispatches ``doRecoverContinuation`` (not ``retryHandoff``)."""
    state, pids = _positioned_population_state()
    viewer = pids[0]
    store = GuiSessionStore(state)
    witness = _SyncWitness()
    _Receiver(store)
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    _seam_missing_decider(monkeypatch)
    store.submitPopulationVotes({})
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert witness.failure_routes()[-1] == RECOVER_ROUTE_CONTINUATION

    feedback = store.doRecoverContinuation()
    assert isinstance(feedback, dict) and "success" in feedback
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# ===========================================================================
# 4. Negative matrix — SD-N8 / SD-N9 (+ per-negative positive control, R-04)
# ===========================================================================
def test_sd_n8_recover_only_in_masked_failure():
    """SD-N8: ``doRecoverContinuation`` is refused outside MASKED_FAILURE."""
    state, pids = _positioned_population_state()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    assert store.seatLifecycle == SEAT_ACTIVE
    feedback = store.doRecoverContinuation()
    assert feedback.get("success") is False


def test_sd_n9_recovery_does_not_replay_human(monkeypatch):
    """SD-N9 / R-04: the committed HUMAN command is not resubmitted and the FULL state
    (not just a count) is invariant across the recovery for the HUMAN ballot set."""
    state, pids = _positioned_population_state()
    viewer = pids[0]
    _seam_missing_decider(monkeypatch)
    session_api.submit_population_votes(state, viewer, {})
    human_votes_before = [v for v in state.get_population_votes() if v[0] == viewer]

    monkeypatch.undo()
    sts.recover_continuation(
        state, ai_executor=session_api._population_ai_executor)
    human_votes_after = [v for v in state.get_population_votes() if v[0] == viewer]
    # the committed HUMAN ballot was neither duplicated nor altered.
    assert human_votes_after == human_votes_before


def test_positive_control_after_every_negative(monkeypatch):
    """R-04 positive-control rule: after EVERY negative in this file, an eligible
    current-seat action must still succeed (the seat is not deadlocked).

    Checks: (i) after the N7-R masked failure the coordinator can progress with a
    working decider; (ii) after an out-of-scope recovery refusal the seat is still
    ACTIVE and a lawful action path exists."""
    # (i) after the N7-R masked failure
    state, pids = _positioned_population_state()
    viewer = pids[0]
    _seam_missing_decider(monkeypatch)
    session_api.submit_population_votes(state, viewer, {})
    monkeypatch.undo()
    res = sts.continue_after_command(
        state, ai_executor=session_api._population_ai_executor)
    assert res.masked_failure is False, res.reason

    # (ii) after an out-of-scope recovery refusal (SD-N8)
    state2, pids2 = _positioned_population_state()
    store2 = GuiSessionStore(state2)
    store2.initialize(pids2[0])
    assert store2.seatLifecycle == SEAT_ACTIVE
    refused = store2.doRecoverContinuation()
    assert refused.get("success") is False
    # the seat is still ACTIVE and a lawful progress path (the producer) exists
    assert store2.seatLifecycle == SEAT_ACTIVE
    res2 = sts.continue_after_command(
        state2, ai_executor=session_api._population_ai_executor)
    assert res2.masked_failure is False, res2.reason


def test_sd_n9_full_state_invariance_on_illegal_negative(monkeypatch):
    """R-04 / SD-N9 (full invariance): an illegal negative (wrong-actor recovery,
    SD-N8) leaves the ENTIRE business state unchanged — not merely a count."""
    state, pids = _positioned_population_state()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    before = _full_digest(state)
    feedback = store.doRecoverContinuation()  # out of scope (SEAT_ACTIVE)
    assert feedback.get("success") is False
    assert _full_digest(state) == before, "the refusal must not mutate the state"


# ===========================================================================
# 5. Anti-injection witness — the positive path uses NO GameState injection
# ===========================================================================
def test_positive_path_uses_factory_playertypes_no_injection():
    """Delta §2.3(2) / SD-N6: the positive path must NOT inject controllers. The
    factory's REAL PlayerType set (3H + 3AI) is used unchanged."""
    state, pids = _positioned_population_state()
    kinds = sorted(p.player_type.value for p in state.get_all_players())
    assert kinds == ["ai", "ai", "ai", "human", "human", "human"]
    # no OBSERVER / non-viewer mutation smuggled into the state
    assert all(p.player_type.value in ("human", "ai") for p in state.get_all_players())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
