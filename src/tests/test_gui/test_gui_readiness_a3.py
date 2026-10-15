"""A3 supplementary DATA owner-boundary tests; NOT real-QML acceptance.

Fault stimulus is MOCK_AUXILIARY (fault injected at the named population
candidate-retrieval seam); raw Core/domain + RNG is the oracle.
Existing frozen S-C tests are deliberately not edited.

F2 closure (S-C-A3-R6). The coordinator derives population obligations through the
**service-private validated-read boundary** ``population_api._get_candidates_impl``
(the design-designated internal-continuation read; see ``population_api.get_candidates``
docstring). The PUBLIC guarded ``population_api.get_candidates`` boundary is NOT
weakened, and ``DENIED`` is never reclassified as ``EMPTY``. Candidate retrieval
ERROR / ``None`` / ``success=False`` / malformed schema must never be equated with a
structural NONE/EMPTY: readiness stays false, the cursor does not move, and the raw
source digest is unchanged — for BOTH the legacy (never-registered / CLI-exempt) and
the registered Hot-seat path. This mirrors how the frozen owner-barrier / guard tests
exercise a REGISTERED Hot-seat session (``register_hotseat_session``).
"""
import copy
import random

import pytest

from src.api import population_api, session_access, session_api
from src.api import session_turn_service as turns
from src.core.entities.player import Player, PlayerType

OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")


def _mk_controllers(state, humans, ais):
    """Force the exact controller set on an existing session (frozen-test style)."""
    pids = [p.player_id for p in state.get_all_players()]
    want = list(humans) + list(ais)
    while len(want) < len(pids):
        want.append(PlayerType.AI)
    want = want[:len(pids)]
    for pid, kind in zip(pids, want):
        original = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(pid, original.faction_id, kind))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    return pids


@pytest.fixture
def population_state():
    rng = random.getstate()
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    try:
        yield result["data"]["state"]
    finally:
        random.setstate(rng)


def raw_state(state):
    return copy.deepcopy(state.to_dict()), random.getstate()


def _patch_candidates(monkeypatch, fault):
    """Inject a candidate-retrieval fault at the service-private read seam."""

    def broken(_state, *args, **kwargs):
        if fault == "throw":
            raise RuntimeError("candidate retrieval failure")
        if fault == "none":
            return None
        if fault == "failed":
            return {"success": False, "data": {o: [] for o in OFFICES}}
        if fault == "empty":
            return {"success": True, "data": {}}
        if fault == "missing-office":
            return {"success": True, "data": {"consul": []}}
        return {"success": True, "data": {o: None for o in OFFICES}}

    monkeypatch.setattr(population_api, "_get_candidates_impl", broken)


@pytest.mark.parametrize("registered", [False, True], ids=["legacy", "registered"])
@pytest.mark.parametrize("fault", ["throw", "none", "failed", "empty", "missing-office", "bad-rows"])
def test_F2_candidate_errors_never_ready_or_move(population_state, monkeypatch, registered, fault):
    state = population_state
    if registered:
        session_access.register_hotseat_session(state, state.get_current_player().player_id, epoch=0)
    scope = turns.mint_scope(state, "population")
    before = raw_state(state)
    original = population_api._get_candidates_impl

    _patch_candidates(monkeypatch, fault)
    assert not turns.phase_ready(state, "population"), "retrieval ERROR must not be structural NONE"
    schedule = turns.obligations(state, "population")
    assert not schedule.ready()
    selected = turns.select_actor(state, scope.scope_id)
    assert not selected["success"]
    drained = turns.continue_after_command(state, phase="population")
    assert not drained.ok and drained.masked_failure
    assert not turns._book(state).records
    assert raw_state(state) == before
    # Positive control: restoring owner retrieval restores a real executable
    # obligation (both the legacy and the registered path use the same
    # service-private validated-read boundary), never a dead end.
    monkeypatch.setattr(population_api, "_get_candidates_impl", original)
    restored = turns.obligations(state, "population")
    assert restored.obligations
    assert turns.select_actor(state, scope.scope_id)["success"]


def test_F2_full_empty_schema_is_lawful_not_error(population_state, monkeypatch):
    state = population_state
    monkeypatch.setattr(population_api, "_get_candidates_impl", lambda _state: {
        "success": True, "data": {o: [] for o in OFFICES}})
    before = raw_state(state)
    assert turns.phase_ready(state, "population")
    assert turns.obligations(state, "population").ready()
    assert raw_state(state) == before


def test_F2_retrieval_failure_after_prior_ai_commit_no_rollback(population_state, monkeypatch, registered=False):
    """A prior AI obligation commits once; a LATER retrieval failure must neither
    add a new effect nor roll back the committed one (post-commit failure boundary).

    The stimulus is a labelled MOCK_AUXILIARY fault at the retrieval seam; the raw
    Core/domain digest + RNG is the oracle.
    """
    state = population_state
    if registered:
        session_access.register_hotseat_session(state, state.get_current_player().player_id, epoch=0)
    boundary = {}
    calls = {"n": 0}

    def executor(s, target):
        calls["n"] += 1
        # the AI's real business commit: record one ballot for the scheduled AI seat
        cands = population_api.get_candidates(s)
        for office, rows in cands["data"].items():
            if rows:
                population_api.vote(s, target.actor_player_id, office, rows[0]["id"])
                break
        # capture the post-commit failure boundary
        boundary["digest"] = copy.deepcopy(s.to_dict())
        boundary["rng"] = random.getstate()
        # every SUBSEQUENT obligation re-derivation now hits a retrieval ERROR
        monkeypatch.setattr(
            population_api, "_get_candidates_impl",
            lambda _s, *a, **k: (_ for _ in ()).throw(RuntimeError("retrieval failed")))
        return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai-1")

    res = turns.continue_after_command(state, ai_executor=executor)
    assert calls["n"] == 1, "the retrieval fault must stop the continuation after one AI commit"
    assert res.masked_failure and not res.ok
    assert (copy.deepcopy(state.to_dict()), random.getstate()) == (
        boundary["digest"], boundary["rng"]), "no new effect and no rolled-back committed effect"


# ===========================================================================
# F1 — frozen per-substep schedule wired into the COMMON path
# ===========================================================================
def test_F1_forum_all_controller_rounds_not_singleton_collapse():
    """Another (non-current) HUMAN and every controller must hold independent
    retirement + market obligations (no single phase-entry `execute` collapse)."""
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    snap = turns.obligations(state, "forum")
    # retirement + market for each canonical controller (3) -> 6 obligations
    assert len(snap.obligations) == 6
    assert {o.substep for o in snap.obligations} == {"retirement", "market"}
    humans = [o for o in snap.obligations if o.controller == turns.CONTROLLER_HUMAN]
    ais = [o for o in snap.obligations if o.controller == turns.CONTROLLER_AI]
    assert len(humans) == 4 and len(ais) == 2
    assert not snap.ready()
    # the OTHER HUMAN is scheduled as HUMAN, never misclassified as AI
    assert any(o.actor_player_id == pids[1] and o.controller == turns.CONTROLLER_HUMAN
               for o in snap.obligations)
    # every controller/substep finish makes the phase ready (both rounds)
    scope = turns.mint_scope(state, "forum")
    for pid in pids:
        for substep in ("retirement", "market"):
            turns.complete_actor(state, None, scope.scope_id, f"fin-{substep}-{pid}",
                                 actor_player_id=pid, phase="forum", substep=substep,
                                 satisfied_kind=turns.KIND_EXPLICIT_FINISH, core_revision_before=0)
    assert turns.phase_ready(state, "forum")


def test_F1_senate_proposal_owner_is_actual_human_not_viewer_mode():
    """The senate proposal obligation is owned by the ACTUAL office holder mapped
    to its real PlayerType — never the viewer-relative political `mode`."""
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    current = state.get_current_player()
    fig = next(m for m in state.get_living_members()
               if m.faction_id == current.faction_id)
    previous_office = fig.office
    fig.office = "consul"
    try:
        # the mapping is the actual PlayerType, never the political `mode`
        assert turns.resolve_office_controller(state, fig.id) == turns.CONTROLLER_HUMAN
        snapshot = turns.obligations(state, "senate")
        prop = next(o for o in snapshot.obligations if o.substep == "proposal")
        assert prop.officer_id == fig.id
        assert prop.controller == turns.CONTROLLER_HUMAN
    finally:
        fig.office = previous_office


# ===========================================================================
# F3 — senate FIRST-finalization readiness gate (registered Hot-seat)
# ===========================================================================
def test_F3_senate_finalize_gated_until_all_ballots():
    """A registered Hot-seat senate first-finalization must NOT commit tally/
    finalization while any required HUMAN/AI ballot is outstanding."""
    from src.api import senate_api

    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    scope = turns.mint_scope(state, "senate")
    # one pending proposal -> every canonical controller holds a mandatory ballot
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    assert not turns.phase_ready(state, "senate")
    before = copy.deepcopy(state.to_dict())
    denied = senate_api.finalize_senate_if_ready(state, caller_context=ctx)
    assert denied["success"] is False
    assert denied["data"]["settlement_guard"] == "senate_not_ready"
    assert copy.deepcopy(state.to_dict()) == before, "denied finalization must not mutate"
    # cast every required ballot -> the vote barrier is satisfied
    proposal_id = state.get_senate_proposals()[0]["id"]
    for pid in pids:
        state.record_senate_vote(pid, proposal_id, True)
    # S-C F1: the frozen senate schedule ALSO holds the veto-holder obligation
    # (all-voter barrier first, then veto). The veto-holder's LAWFUL decision (incl.
    # an explicit empty choice) is what satisfies it; readiness then flips open.
    _veto_oid = turns._book(state).oid("senate", "veto", ("singleton", scope.scope_id),
                                      scope.scope_id)
    _rc = turns.issue_owner_receipt(state, "senate-veto", scope_id=scope.scope_id,
                                    obligation_id=_veto_oid, fact_ref="veto:test")
    turns.complete_actor(state, None, scope.scope_id, "senate-veto",
                         phase="senate", substep="veto",
                         satisfied_kind=turns.KIND_ACTION,
                         owner_receipt=_rc)
    assert turns.phase_ready(state, "senate")


# ===========================================================================
# F1 remainder — senate VETO-holder obligation (another HUMAN tribune)
# ===========================================================================
def test_F1_senate_veto_holder_is_actual_human_and_required():
    """The senate veto obligation is owned by the ACTUAL eligible tribune (mapped
    office -> faction -> real ``PlayerType``), is REQUIRED once a passed candidate
    exists, and blocks readiness until the veto-holder's lawful decision."""
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "senate")
    current = state.get_current_player()
    fam = [m for m in state.get_living_members() if m.faction_id == current.faction_id]
    assert fam, "current faction has no living member"
    saved = {m.id: m.office for m in fam}
    try:
        for m in fam[1:]:
            if m.office == "tribune":
                m.office = "quaestor"
        fam[0].office = "tribune"
        trib = fam[0]
        state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
        proposal_id = state.get_senate_proposals()[0]["id"]
        for pid in pids:
            state.record_senate_vote(pid, proposal_id, True)
        snap = turns.obligations(state, "senate")
        veto = next(o for o in snap.obligations if o.substep == "veto")
        assert veto.officer_id == trib.id
        assert veto.controller == turns.CONTROLLER_HUMAN  # another HUMAN, never AI
        assert not veto.satisfied
        assert not turns.phase_ready(state, "senate")
        # the veto-holder's lawful explicit-empty decision satisfies the obligation
        _veto_oid = turns._book(state).oid("senate", "veto", ("singleton", scope.scope_id),
                                          scope.scope_id)
        _rc = turns.issue_owner_receipt(state, "veto-empty", scope_id=scope.scope_id,
                                        obligation_id=_veto_oid, fact_ref="veto:empty")
        turns.complete_actor(state, None, scope.scope_id, "veto-empty",
                             phase="senate", substep="veto",
                             satisfied_kind=turns.KIND_ACTION,
                             owner_receipt=_rc)
        assert turns.phase_ready(state, "senate")
    finally:
        for m in fam:
            m.office = saved[m.id]


# ===========================================================================
# F4 — forum completion integration in the Store (ledger, not cache flag)
# ===========================================================================
def test_F4_store_forum_finishes_are_ledger_recorded_not_cache_flag(monkeypatch):
    """The Store records each forum substep finish into the ONE session ledger via
    the completion service (owner completion), with a CHECKED structured AI outcome
    and NO authoritative cache flag (a failure is NEVER recorded; no flag success)."""
    import src.ui.gui.session_store as store_mod
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    scope = turns.mint_scope(state, "forum")
    book = turns._book(state)
    ai_oid = book.oid("forum", "retirement", ("player", pids[1]), scope.scope_id)
    # owner-recorded human retirement finish -> real ledger record
    store._record_forum_ledger_finish(pids[0], "retirement", "t:ret")
    assert book.satisfied(book.oid("forum", "retirement", ("player", pids[0]),
                                   scope.scope_id), scope.scope_id,
                          turns.current_revision(state))

    class _FailProcessor:
        def __init__(self, *a, **k):
            pass

        def process_retirement(self, *a, **k):
            return turns.ExecutionOutcome(turns.OUTCOME_FAILURE, detail="boom")

        def process_market(self, *a, **k):
            return turns.ExecutionOutcome(turns.OUTCOME_FAILURE, detail="boom")

    monkeypatch.setattr(store_mod, "AutoPlayerProcessor", _FailProcessor)
    store._process_ai_factions_forum("retirement")
    # a FAILED AI step is NOT recorded and leaves the substep not-ready (no flag success)
    assert not book.satisfied(ai_oid, scope.scope_id, turns.current_revision(state))
    assert not getattr(store, "_forum_ai_processed", False)
    assert not turns.forum_substep_ready(state, "retirement")

    class _OkProcessor:
        def __init__(self, *a, **k):
            pass

        def process_retirement(self, *a, **k):
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ok-ret")

        def process_market(self, *a, **k):
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ok-mkt")

    monkeypatch.setattr(store_mod, "AutoPlayerProcessor", _OkProcessor)
    store._process_ai_factions_forum("retirement")
    # an ACCEPTED AI step is recorded via the completion service
    assert book.satisfied(ai_oid, scope.scope_id, turns.current_revision(state))
    assert turns.forum_substep_ready(state, "retirement")
    # the cache flag is NOT a gate: a pre-set flag must not skip the schedule
    store._forum_ai_processed = True
    # §4.3: the earlier HUMAN market obligation must be recorded first (canonical
    # next-obligation stop); THEN the scheduled AI market runs.
    store._record_forum_ledger_finish(pids[0], "market", "t:mkt")
    store._process_ai_factions_forum("market")
    assert book.satisfied(book.oid("forum", "market", ("player", pids[1]),
                                   scope.scope_id), scope.scope_id,
                          turns.current_revision(state))


# ===========================================================================
# F5 — population resolver: readiness BEFORE denied business work +
#      registered (not book-present) boundary
# ===========================================================================
def test_F5_registered_resolver_readiness_precedes_business_work():
    """A registered Hot-seat population resolver must commit NO business work when
    readiness fails (readiness precedes begin/drain/disband)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    before = raw_state(state)
    denied = session_api.resolve_population_slice(state, caller_context=ctx)
    assert denied["success"] is False
    assert raw_state(state) == before, "denied resolver mutated business state"


# ===========================================================================
# F6 — complete_actor receipt provenance + select_actor sole cursor writer
# ===========================================================================
def test_F6_complete_actor_requires_owner_receipt_provenance():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    # an empty owner command id is rejected
    assert turns.complete_actor(state, None, scope.scope_id, "",
        actor_player_id=pids[0])["reason"] == "MISSING_COMMAND_ID"
    # an invalid satisfaction kind is rejected
    assert turns.complete_actor(state, None, scope.scope_id, "cmd",
        actor_player_id=pids[0],
        satisfied_kind="BOGUS")["reason"] == "INVALID_SATISFACTION_KIND"
    # an INVENTED obligation (not derivable from the owner schedule) is rejected
    bogus = ("session-x", 999, "scope-x", "population", "vote",
             ("player", "no_such_player"))
    assert turns.complete_actor(state, None, scope.scope_id, "cmd",
        obligation_id=bogus,
        actor_player_id=pids[0])["reason"] == "UNKNOWN_OBLIGATION"
    # a lawful owner-declared explicit finish on a REAL obligation is accepted
    ok = turns.complete_actor(state, None, scope.scope_id, "finish",
        actor_player_id=pids[0], satisfied_kind=turns.KIND_EXPLICIT_FINISH)
    assert ok["success"]


def test_F6_continuation_human_stop_routes_through_select_actor(monkeypatch):
    """The continuation's HUMAN-stop must route through ``select_actor`` (the SOLE
    cursor writer) — never a direct ``set_current_player`` write."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    # all-HUMAN fixture: the first outstanding obligation is a HUMAN, so the
    # continuation must take the HUMAN-stop branch (never the AI drain).
    _mk_controllers(state, [PlayerType.HUMAN] * 8, [])
    turns.mint_scope(state, "population")
    calls = []

    def spy(s, *a, **k):
        calls.append(True)
        return {"success": True, "actor": None, "ready": True}

    monkeypatch.setattr(turns, "select_actor", spy)
    turns.continue_after_command(
        state, phase="population",
        ai_executor=lambda s, t: turns.ExecutionOutcome(
            turns.OUTCOME_FAILURE, detail="unused"))
    assert calls, "HUMAN-stop must route through select_actor (sole cursor writer)"


# ===========================================================================
# A3-R8 — G5-RETURN rework (F1/A3-01, F1/A3-02, F3/A3-03, F4/A3-04, F6/A3-05)
#
# TEST DISCIPLINE (§C): the closures below drive the REAL production owner
# commands (senate_api.propose_many / vote / veto / finalize_senate_if_ready,
# session_store.doCompleteForumStep / doResolveForum, session_api/*), NOT
# synthetic records or direct executor stubs, wherever a behavioural claim is
# made. Where a fault must be injected (child-API denial), it is injected at a
# named seam and labelled MOCK_AUXILIARY; the trigger remains a real owner call.
# ===========================================================================
from src.api import senate_api  # noqa: E402


def _senate_state(humans, ais, registered=False):
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, humans, ais)
    if registered:
        session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _set_offices(state, assignment):
    """assignment: {player_id: office}. Save/restore helper returns a restore fn."""
    saved = {}
    for pid, office in assignment.items():
        player = state.get_player(pid)
        members = [m for m in state.get_living_members() if m.faction_id == player.faction_id]
        assert members, f"{pid} faction has no living member"
        for m in members:
            saved.setdefault(m.id, m.office)
        members[0].office = office
    return saved


def _restore_offices(state, saved):
    for mid, office in saved.items():
        m = state.get_member(mid)
        if m is not None:
            m.office = office


# ---------------------------------------------------------------------------
# F1/A3-01 — office holder is mapped to its validated owning PLAYER and can
# become CURRENT and ACT (real owner commands; no AI processing).
# ---------------------------------------------------------------------------
def test_A3R8_F1_proposal_owner_maps_to_owning_player_and_becomes_current():
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    ctx = session_access.present_context(state)
    saved = _set_offices(state, {pids[0]: "consul"})
    try:
        scope = turns.mint_scope(state, "senate")
        snap = turns.obligations(state, "senate")
        prop = next(o for o in snap.obligations if o.substep == "proposal")
        assert prop.controller == turns.CONTROLLER_HUMAN
        # A3-01: the office holder is mapped to its VALIDATED owning player (the
        # bare officer id cannot be handed to ``set_current_player``).
        assert prop.actor_player_id == pids[0], prop
        assert prop.officer_id is not None
        # Force the cursor off the office holder to prove the coordinator moves it.
        state.set_current_player(pids[2])
        res = turns.continue_after_command(
            state, phase="senate",
            ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
        assert res.status == turns.STATUS_NEXT_HUMAN, res
        assert res.actor == pids[0]
        assert state.get_current_player().player_id == pids[0], \
            "the office holder must become CURRENT"
        # ACT via the real production owner command (empty package = lawful).
        acted = senate_api.propose_many(state, pids[0], [], caller_context=ctx)
        assert acted["success"] is True, acted.get("message")
        prop2 = next(o for o in turns.obligations(state, "senate").obligations
                     if o.substep == "proposal")
        assert prop2.satisfied
    finally:
        _restore_offices(state, saved)


def test_A3R8_F1_veto_holder_uses_last_voter_anchor_and_becomes_current():
    """The veto obligation is anchored on the LAST SCHEDULED VOTER (not G) and
    mapped to the ACTUAL eligible tribune's validated owning player — a HUMAN
    distinct from the last voter can become CURRENT and ACT (real veto command)."""
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    ctx = session_access.present_context(state)
    # last scheduled voter = last player in canonical order; its faction must have
    # NO tribune, so the resolver falls to the global eligible tribune (another
    # faction) — a HUMAN distinct from the last voter.
    saved = _set_offices(state, {pids[0]: "consul", pids[1]: "tribune"})
    try:
        # ensure the last voter's faction has no tribune
        last_voter = pids[-1]
        lv_faction = state.get_player(last_voter).faction_id
        for m in state.get_living_members():
            if m.faction_id == lv_faction and m.office == "tribune":
                m.office = "quaestor"
        scope = turns.mint_scope(state, "senate")
        state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
        pid_prop = state.get_senate_proposals()[0]["id"]
        for pid in pids:
            turns.select_scheduled_actor(state, "senate", pid, scope.scope_id)
            v = senate_api.vote(state, pid, [pid_prop], [True], caller_context=ctx)
            assert v["success"] is True, (pid, v.get("message"))
        veto = next(o for o in turns.obligations(state, "senate").obligations
                    if o.substep == "veto")
        assert veto.controller == turns.CONTROLLER_HUMAN, veto
        assert veto.actor_player_id is not None, "veto holder must map to a real player"
        assert veto.actor_player_id != last_voter, \
            "tribune must be a HUMAN distinct from the last scheduled voter"
        assert not veto.satisfied
        # the tribune becomes CURRENT and acts via the real veto command
        turns.select_scheduled_actor(state, "senate", veto.actor_player_id, scope.scope_id)
        acted = senate_api.veto(state, veto.actor_player_id, [pid_prop], caller_context=ctx)
        assert acted["success"] is True, acted.get("message")
        veto2 = next(o for o in turns.obligations(state, "senate").obligations
                     if o.substep == "veto")
        assert veto2.satisfied
    finally:
        _restore_offices(state, saved)


# ---------------------------------------------------------------------------
# F1/A3-02 — non-population continuation: finite outstanding-work invariant;
# stop at the next HUMAN; true readiness only when nothing is outstanding.
# ---------------------------------------------------------------------------
def test_A3R8_F1_forum_continuation_drains_all_ai_then_stops_at_human():
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    # the remaining HUMAN is LAST so the loop must drain the adjacent AI seats first.
    pids = _mk_controllers(
        state, [PlayerType.AI, PlayerType.AI, PlayerType.HUMAN], [])
    h0 = pids[2]
    seen = []

    def ex(s, t):
        seen.append(t.actor_player_id)
        return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai")

    res = turns.continue_after_command(state, phase="forum", ai_executor=ex)
    # NOT a premature READY after one AI step: the loop drains EVERY outstanding AI
    # obligation (retirement + market) and then STOPS at the remaining HUMAN.
    assert res.status == turns.STATUS_NEXT_HUMAN, res
    assert res.actor == h0
    assert set(seen) == {pids[0], pids[1]}
    assert not turns.phase_ready(state, "forum")


def test_A3R8_F1_forum_continuation_true_readiness_when_all_ai():
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.AI, PlayerType.AI, PlayerType.AI], [])
    res = turns.continue_after_command(
        state, phase="forum",
        ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
    assert res.status == turns.STATUS_PHASE_READY, (res.status, res.reason)
    assert turns.phase_ready(state, "forum")


def test_A3R8_F1_senate_continuation_not_premature_ready_with_outstanding_ai():
    """A senate with outstanding AI ballots must NOT be reported ready after one
    drained step; the loop continues and stops at the next HUMAN."""
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.AI, PlayerType.AI], [])
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    # satisfy the proposal obligation so the drain focuses on ballots
    scope = turns.mint_scope(state, "senate")
    turns.complete_actor(state, None, scope.scope_id, "proposal-done",
                         phase="senate", substep="proposal",
                         satisfied_kind=turns.KIND_EXPLICIT_FINISH)
    res = turns.continue_after_command(
        state, phase="senate",
        ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
    assert res.status != turns.STATUS_PHASE_READY, "premature READY with outstanding ballots"
    assert res.status in (turns.STATUS_NEXT_HUMAN, turns.STATUS_FAILURE)


# ---------------------------------------------------------------------------
# F1/A3-02 (Store) — a non-consul viewer must NOT auto-submit on another
# HUMAN's behalf; the AI auto-proposer requires an ACTUAL AI controller.
# ---------------------------------------------------------------------------
def test_A3R8_F1_store_senate_nonconsul_does_not_auto_submit_for_human_owner():
    from src.ui.gui.session_store import GuiSessionStore
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    saved = _set_offices(state, {pids[0]: "consul"})
    try:
        store = GuiSessionStore(state)
        store.initialize(pids[2])  # a non-consul viewer (not the proposal owner)
        store._senate_view = {"viewer_has_consul": False}
        before = copy.deepcopy(state.to_dict())
        feedback = store.doSubmitSenateProposals([])
        assert feedback["success"] is False, "must not auto-submit for another HUMAN"
        assert copy.deepcopy(state.to_dict()) == before, "no mutation on refusal"
    finally:
        _restore_offices(state, saved)


# ---------------------------------------------------------------------------
# F3/A3-03 — partial recovery admission is gated by the frozen readiness
# predicate (registered Hot-seat); a lawful recovery still preserves the
# four-fact receipt replay.
# ---------------------------------------------------------------------------
def test_A3R8_F3_partial_recovery_gated_by_readiness_no_mutation():
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI],
                                registered=True)
    ctx = session_access.present_context(state)
    scope = turns.mint_scope(state, "senate")
    # a PARTIAL finalization state: result present, receipt missing.
    state.record_phase_result("senate", {"success": True,
                                          "data": {"frozen_war_decisions": []}})
    # an outstanding obligation: a pending proposal with no ballots cast.
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    assert not turns.phase_ready(state, "senate")
    before = copy.deepcopy(state.to_dict())
    denied = senate_api.finalize_senate_if_ready(state, caller_context=ctx)
    assert denied["success"] is False
    assert denied["data"]["settlement_guard"] == "senate_not_ready"
    assert copy.deepcopy(state.to_dict()) == before, "denied partial recovery mutated state"


def test_A3R8_F3_partial_recovery_replays_four_facts_when_ready():
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI],
                                registered=True)
    ctx = session_access.present_context(state)
    scope = turns.mint_scope(state, "senate")
    saved = _set_offices(state, {pids[0]: "consul"})
    try:
        # make senate readiness TRUE via the real owner command: explicit empty package.
        acted = senate_api.propose_many(state, pids[0], [], caller_context=ctx)
        assert acted["success"] is True, acted.get("message")
        if not turns.phase_ready(state, "senate"):
            turns.complete_actor(state, None, scope.scope_id, "proposal-done",
                                 phase="senate", substep="proposal",
                                 satisfied_kind=turns.KIND_EXPLICIT_FINISH,
                                 owner_declared=True)
        assert turns.phase_ready(state, "senate"), "readiness must hold for lawful recovery"
        # partial finalization state: result present (frozen outcome), receipt missing.
        state.record_phase_result("senate", {"success": True,
                                              "data": {"frozen_war_decisions": []}})
        recovered = senate_api.finalize_senate_if_ready(state, caller_context=ctx)
        assert recovered["success"] is True, recovered.get("message")
        assert (recovered["data"].get("recovered") is True
                or recovered["data"].get("replayed") is True)
        facts = recovered["data"].get("completion_facts")
        assert facts is None or all(facts.values())
    finally:
        _restore_offices(state, saved)


# ---------------------------------------------------------------------------
# F4/A3-04 — the Store forum path uses the single common schedule: a satisfied
# seat's business work is NEVER replayed, and a denied child API is NOT
# swallowed into a false ACCEPTED.
# ---------------------------------------------------------------------------
def test_A3R8_F4_store_forum_no_replay_of_satisfied_seat(monkeypatch):
    import src.ui.gui.session_store as store_mod
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    # exactly one AI seat.
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    calls = {"n": 0}

    class _Proc:
        def __init__(self, *a, **k):
            pass

        def process_retirement(self, *a, **k):
            calls["n"] += 1
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="r")

        def process_market(self, *a, **k):
            calls["n"] += 1
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="m")

    monkeypatch.setattr(store_mod, "AutoPlayerProcessor", _Proc)
    # §4.3: the two earlier HUMAN retirement obligations must be recorded first
    # (canonical next-obligation stop), so the single AI seat is the next work.
    store._record_forum_ledger_finish(pids[0], "retirement", "t:r0")
    store._record_forum_ledger_finish(pids[1], "retirement", "t:r1")
    store._process_ai_factions_forum("retirement")
    first = calls["n"]
    assert first == 1, "the scheduled AI retirement must run exactly once"
    # a second pass must SKIP the already-satisfied obligation BEFORE any effect.
    store._process_ai_factions_forum("retirement")
    assert calls["n"] == first, "a satisfied seat's business work must not be replayed"


def test_A3R8_F4_process_market_propagates_denied_child(monkeypatch):
    """A denied child API (recruit) must turn the aggregate into FAILURE — never a
    false ACCEPTED (F4)."""
    from src.ui.processors import auto_player_processor as app
    from src.api import forum_api
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    ai = state.get_player(pids[2])
    faction = state.get_faction(ai.faction_id)

    class _Fig:
        id = 1

    monkeypatch.setattr(state.curia, "get_all_available", lambda: [_Fig()])

    class _R:
        def decide_bids(self, fac, available, vacancies, st):
            return {_Fig.id: 1}

    proc = app.AutoPlayerProcessor(state, retirement_decider=None,
                                   recruitment_decider=_R(), bid_decider=None,
                                   triumph_decider=None)
    monkeypatch.setattr(forum_api, "recruit_figure",
                        lambda *a, **k: {"success": False, "message": "DENIED"})
    outcome = proc.process_market(ai.player_id, faction)
    assert outcome.is_failure, "a denied child must not be swallowed into ACCEPTED"


# ---------------------------------------------------------------------------
# F6/A3-05 — every completion is bound to a validated owner receipt/fact; an
# arbitrary string / forged receipt is rejected and leaves ledger+business
# unchanged. The real owner command records a receipt-bound ACTION.
# ---------------------------------------------------------------------------
def test_A3R8_F6_action_requires_validated_owner_receipt():
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    before = raw_state(state)
    # an arbitrary fact string is NOT a receipt
    bad = turns.complete_actor(state, None, scope.scope_id, "arbitrary",
                               actor_player_id=pids[0], satisfied_kind=turns.KIND_ACTION,
                               authoritative_fact_ref="garbage-string")
    assert bad["reason"] == "MISSING_OWNER_RECEIPT"
    assert not turns._book(state).records
    assert raw_state(state) == before
    # an engine-issued receipt is accepted (bound to the pre-command revision)
    oid_vote = turns._book(state).oid("population", "vote", ("player", pids[0]),
                                    scope.scope_id)
    rc = turns.issue_owner_receipt(state, "owner_cmd", actor_player_id=pids[0],
                                   fact_ref="owner:owner_cmd", scope_id=scope.scope_id,
                                   obligation_id=oid_vote)
    ok = turns.complete_actor(state, None, scope.scope_id, "owner_cmd",
                              actor_player_id=pids[0], satisfied_kind=turns.KIND_ACTION,
                              owner_receipt=rc)
    assert ok["success"] and ok.get("recorded")
    # a FORGED receipt (not engine-issued) is rejected and changes nothing
    forged = {"receipt_id": "not-engine-issued", "fact_ref": "owner:x",
              "core_revision_before": 0}
    size_before = len(turns._book(state).records)
    bad2 = turns.complete_actor(state, None, scope.scope_id, "forged",
                                actor_player_id=pids[0], satisfied_kind=turns.KIND_ACTION,
                                owner_receipt=forged)
    assert bad2["reason"] == "MISSING_OWNER_RECEIPT"
    assert len(turns._book(state).records) == size_before


def test_A3R8_F6_stale_owner_receipt_revision_rejected():
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    size_before = len(turns._book(state).records)
    bad = turns.complete_actor(state, None, scope.scope_id, "owner_cmd",
                               actor_player_id=pids[0], satisfied_kind=turns.KIND_ACTION,
                               authoritative_fact_ref="owner:owner_cmd",
                               core_revision_before=999999)
    assert bad["reason"] == "STALE_OWNER_RECEIPT_REVISION"
    assert len(turns._book(state).records) == size_before


def test_A3R8_F6_real_owner_veto_records_receipt_bound_action():
    """A real production owner command (senate veto, by the registered principal)
    records a receipt-bound ACTION completion into the ONE ledger."""
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [],
                                registered=True)
    ctx = session_access.present_context(state)
    saved = _set_offices(state, {pids[0]: "consul", pids[0]: "tribune"})
    try:
        # the last scheduled voter's faction must have NO tribune so the resolver
        # falls to the global eligible tribune = pids[0] (the registered principal).
        lv_faction = state.get_player(pids[-1]).faction_id
        principal_faction = state.get_player(pids[0]).faction_id
        assert lv_faction != principal_faction
        for m in state.get_living_members():
            if m.faction_id == lv_faction and m.office == "tribune":
                m.office = "quaestor"
        scope = turns.mint_scope(state, "senate")
        pid_prop = state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
        # prior committed ballots (fixture domain state; the ACT is the veto command)
        for pid in pids:
            state.record_senate_vote(pid, pid_prop, True)
        veto = next(o for o in turns.obligations(state, "senate").obligations
                    if o.substep == "veto")
        assert veto.actor_player_id == pids[0]
        turns.select_scheduled_actor(state, "senate", pids[0], scope.scope_id)
        acted = senate_api.veto(state, pids[0], [pid_prop], caller_context=ctx)
        assert acted["success"] is True, acted.get("message")
        actions = [r for r in turns._book(state).records
                   if r.satisfied_kind == turns.KIND_ACTION]
        assert actions, "the real owner command must record an ACTION receipt"
        assert actions[-1].authoritative_fact_ref.startswith("senate-veto:")
    finally:
        _restore_offices(state, saved)


# ===========================================================================
# A3-R9 — G5 RETURN #4 rework (RED-first).  §4.1 resolver / candidate errors
# must FAIL CLOSED (never become a structural NONE); the scope's authoritative
# role selection is preserved and the resolver's authority reason retained.
# ===========================================================================
def test_A3R9_F1_proposal_resolver_error_fails_closed(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])

    def boom(self, viewer_player_id):
        raise RuntimeError("proposal resolver retrieval failed")

    monkeypatch.setattr(PoliticalSystem, "resolve_proposal_control", boom)
    snap = turns.obligations(state, "senate")
    assert snap.errors, "a resolver retrieval error must be a schedule error, not NONE"
    assert not turns.phase_ready(state, "senate")


def test_A3R9_F1_veto_resolver_error_fails_closed(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    scope = turns.mint_scope(state, "senate")
    pid_prop = state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    for pid in pids:
        state.record_senate_vote(pid, pid_prop, True)
    turns.complete_actor(state, None, scope.scope_id, "prop-done", phase="senate",
                         substep="proposal", satisfied_kind=turns.KIND_EXPLICIT_FINISH)

    def boom(self, viewer_player_id):
        raise RuntimeError("veto resolver failed")

    monkeypatch.setattr(PoliticalSystem, "resolve_veto_control", boom)
    snap = turns.obligations(state, "senate")
    assert snap.errors, "a veto resolver error must fail closed, not drop the obligation"
    assert not turns.phase_ready(state, "senate")


def test_A3R9_F1_veto_candidate_derivation_error_fails_closed(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    saved = _set_offices(state, {pids[-1]: "tribune"})
    try:
        scope = turns.mint_scope(state, "senate")
        pid_prop = state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
        for pid in pids:
            state.record_senate_vote(pid, pid_prop, True)
        turns.complete_actor(state, None, scope.scope_id, "prop-done", phase="senate",
                             substep="proposal", satisfied_kind=turns.KIND_EXPLICIT_FINISH)

        def boom(self):
            raise RuntimeError("candidate derivation failed")

        monkeypatch.setattr(PoliticalSystem, "build_vote_results_and_candidates", boom)
        snap = turns.obligations(state, "senate")
        assert snap.errors, "a candidate-derivation error must fail closed"
        assert not turns.phase_ready(state, "senate")
    finally:
        _restore_offices(state, saved)


def test_A3R9_F1_seat3_consul_at_entry_selection_preserved():
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [])
    saved = _set_offices(state, {pids[2]: "consul"})
    try:
        state.set_current_player(pids[2])  # entry actor = seat 3 = the consul
        scope = turns.mint_scope(state, "senate")
        prop = next(o for o in turns.obligations(state, "senate").obligations
                    if o.substep == "proposal")
        assert prop.actor_player_id == pids[2]
        assert prop.controller == turns.CONTROLLER_HUMAN
        assert prop.officer_id is not None
        sel = turns._book(state).role_selections[(scope.scope_id, "proposal")]
        assert sel["authority_reason"] == "human_eligible_consul", sel
        # a display refresh does not switch the latched office owner
        for _ in range(3):
            p2 = next(o for o in turns.obligations(state, "senate").obligations
                      if o.substep == "proposal")
            assert p2.actor_player_id == pids[2]
    finally:
        _restore_offices(state, saved)


# ===========================================================================
# A3-R9 — §4.2 the continuation must run the REAL scheduled-owner / current-seat
# path (select the scheduled AI CURRENT, CHECK the selection result, fail closed)
# and the Store must not auto-play an unresolved controller on a registered
# Hot-seat session.
# ===========================================================================
def test_A3R9_F1_continuation_selects_scheduled_ai_current(monkeypatch):
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.AI, PlayerType.AI, PlayerType.HUMAN], [])
    real = turns.select_scheduled_actor
    calls = []

    def spy(s, ph, pid, scope_id=None):
        calls.append(pid)
        return real(s, ph, pid, scope_id)

    monkeypatch.setattr(turns, "select_scheduled_actor", spy)
    res = turns.continue_after_command(
        state, phase="forum",
        ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
    assert calls, "the coordinator must select the scheduled AI as CURRENT before it acts"
    assert res.status == turns.STATUS_NEXT_HUMAN, res


def test_A3R9_F1_continuation_fail_closed_when_ai_not_selectable(monkeypatch):
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.AI, PlayerType.HUMAN], [])
    monkeypatch.setattr(turns, "select_scheduled_actor",
                        lambda *a, **k: {"success": False, "reason": "NOT_SCHEDULED", "actor": None})
    res = turns.continue_after_command(
        state, phase="forum",
        ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
    assert res.masked_failure and not res.ok, "an unselectable scheduled AI must fail closed"


def test_A3R9_F1_human_stop_fail_closed_when_select_actor_fails(monkeypatch):
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.HUMAN, PlayerType.AI], [])
    monkeypatch.setattr(turns, "select_actor",
                        lambda *a, **k: {"success": False, "reason": "SET_CURRENT_FAILED", "actor": None})
    res = turns.continue_after_command(
        state, phase="forum",
        ai_executor=lambda s, t: turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="ai"))
    assert res.masked_failure and not res.ok, \
        "a failed human-stop cursor selection must fail closed (never a false handoff)"


def test_A3R9_F1_store_senate_refuses_on_derivation_error(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem
    from src.api import senate_api
    from src.ui.gui.session_store import GuiSessionStore
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [],
                                registered=True)
    saved = _set_offices(state, {pids[0]: "consul"})
    try:
        store = GuiSessionStore(state)
        store.initialize(pids[2])
        store._senate_view = {"viewer_has_consul": False}

        def boom(self, viewer_player_id):
            raise RuntimeError("schedule derivation failed")

        monkeypatch.setattr(PoliticalSystem, "resolve_proposal_control", boom)
        called = {"auto": 0}
        real_auto = senate_api.auto_submit_proposals

        def spy(s, *a, **k):
            called["auto"] += 1
            return real_auto(s, *a, **k)

        monkeypatch.setattr(senate_api, "auto_submit_proposals", spy)
        before = copy.deepcopy(state.to_dict())
        feedback = store.doSubmitSenateProposals([])
        assert called["auto"] == 0, "a derivation error must not be auto-played"
        assert feedback["success"] is False
        assert copy.deepcopy(state.to_dict()) == before, "no mutation on a failed schedule"
    finally:
        _restore_offices(state, saved)


def test_A3R9_F1_store_senate_unresolved_controller_not_autoplayed(monkeypatch):
    from src.core.systems.political_system import PoliticalSystem
    from src.api import senate_api
    from src.ui.gui.session_store import GuiSessionStore
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [],
                                registered=True)
    store = GuiSessionStore(state)
    store.initialize(pids[2])
    store._senate_view = {"viewer_has_consul": False}
    monkeypatch.setattr(PoliticalSystem, "resolve_proposal_control",
                        lambda self, viewer_player_id: {"mode": "NONE", "actor": None,
                                                        "authority_reason": "no_eligible_host"})
    called = {"auto": 0}
    real_auto = senate_api.auto_submit_proposals

    def spy(s, *a, **k):
        called["auto"] += 1
        return real_auto(s, *a, **k)

    monkeypatch.setattr(senate_api, "auto_submit_proposals", spy)
    before = copy.deepcopy(state.to_dict())
    feedback = store.doSubmitSenateProposals([])
    assert called["auto"] == 0, \
        "an unresolved controller on a registered Hot-seat must not be auto-played"
    assert feedback["success"] is False
    assert copy.deepcopy(state.to_dict()) == before, "no mutation on an unresolved controller"


# ===========================================================================
# A3-R9 — §4.3 the Store forum path must CHECK every completion result, bind an
# authenticated owner no-action receipt, and honour the single common schedule's
# next-HUMAN stop before running further AI (real owner path; no synthetic
# executive substitution for the behavioural closure).
# ===========================================================================
def test_A3R9_F4_forum_stops_before_ai_when_a_human_precedes(monkeypatch):
    import src.ui.gui.session_store as store_mod
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.AI], [])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    calls = {"n": 0}

    class _Proc:
        def __init__(self, *a, **k):
            pass

        def process_retirement(self, *a, **k):
            calls["n"] += 1
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="r")

        def process_market(self, *a, **k):
            calls["n"] += 1
            return turns.ExecutionOutcome(turns.OUTCOME_ACCEPTED, command_id="m")

    monkeypatch.setattr(store_mod, "AutoPlayerProcessor", _Proc)
    store._process_ai_factions_forum("retirement")
    assert calls["n"] == 0, \
        "a pending HUMAN earlier in the common schedule must stop further AI work"


def test_A3R9_F4_forum_finish_result_is_checked(monkeypatch):
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    store._forum_step_override = "retirement"
    # the viewer's own retirement is already satisfied -> the AI is next in order.
    scope = turns.mint_scope(state, "forum")
    turns.complete_actor(state, None, scope.scope_id, "viewer-ret",
                         actor_player_id=pids[0], phase="forum", substep="retirement",
                         satisfied_kind=turns.KIND_EXPLICIT_FINISH, owner_declared=True)
    monkeypatch.setattr(store, "_record_forum_ledger_finish",
                        lambda *a, **k: {"success": False, "reason": "RECORD_FAILED"})
    opened = {"n": 0}
    monkeypatch.setattr(store._adapter, "open_forum_market",
                        lambda *a, **k: opened.__setitem__("n", opened["n"] + 1) or {"success": True})
    feedback = store.doCompleteForumStep()
    assert feedback["success"] is False
    assert opened["n"] == 0, "the market must not open when the owner finish was not recorded"


def test_A3R9_F4_forum_finish_uses_owner_receipt():
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    rec = store._record_forum_ledger_finish(pids[0], "retirement", "owner:retirement")
    assert rec.get("success"), rec
    book = turns._book(state)
    recs = [r for r in book.records
            if r.satisfied_kind == turns.KIND_EXPLICIT_FINISH]
    assert recs, "the owner finish must be recorded"
    assert recs[-1].authoritative_fact_ref.startswith("owner:"), \
        "the owner finish must carry an authenticated owner fact, not a bare string"
    assert book.receipts, "the engine must issue a real owner receipt for the finish"


def test_A3R9_F4_forum_real_owner_success_and_partial_retry(monkeypatch):
    import src.ui.gui.session_store as store_mod
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    scope = turns.mint_scope(state, "forum")
    book = turns._book(state)
    ai_ret = book.oid("forum", "retirement", ("player", pids[2]), scope.scope_id)

    real_cls = store_mod.AutoPlayerProcessor
    calls = {"n": 0}

    class _Spy(real_cls):
        def process_retirement(self, *a, **k):
            calls["n"] += 1
            return super().process_retirement(*a, **k)

        def process_market(self, *a, **k):
            calls["n"] += 1
            return super().process_market(*a, **k)

    monkeypatch.setattr(store_mod, "AutoPlayerProcessor", _Spy)
    # while the two earlier HUMAN retirement obligations are outstanding the REAL
    # scheduled AI must not run (canonical next-obligation stop).
    store._process_ai_factions_forum("retirement")
    assert calls["n"] == 0, "AI work must not precede a pending HUMAN in canonical order"
    # the HUMAN owners complete first -> the REAL scheduled AI owner runs once.
    store._record_forum_ledger_finish(pids[0], "retirement", "owner:r0")
    store._record_forum_ledger_finish(pids[1], "retirement", "owner:r1")
    store._process_ai_factions_forum("retirement")
    assert calls["n"] == 1, "the scheduled real AI owner must run exactly once"
    assert book.satisfied(ai_ret, scope.scope_id, turns.current_revision(state))
    # a partial-success retry must NOT re-run the completed seat
    store._process_ai_factions_forum("retirement")
    assert calls["n"] == 1, "a completed seat must never be replayed"
    assert turns.forum_substep_ready(state, "retirement")


# ===========================================================================
# A3-R9 — §4.4 the owner receipt must BIND an immutable owner-issued fact:
# exact session/scope/actor/operation/OID + the STORED pre-command revision;
# altered / reused / stale receipts are rejected with ledger+business unchanged.
# ===========================================================================
def test_A3R9_F6_altered_owner_receipt_rejected():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    rc = turns.issue_owner_receipt(state, "owner_cmd", actor_player_id=pids[0],
                                   fact_ref="owner:owner_cmd")
    altered = dict(rc)
    altered["fact_ref"] = "owner:forged"
    altered["command"] = "different"
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "owner_cmd",
                               actor_player_id=pids[0], satisfied_kind=turns.KIND_ACTION,
                               owner_receipt=altered)
    assert bad["success"] is False, "an altered receipt copy must be rejected"
    assert not turns._book(state).records
    assert raw_state(state) == before


def test_A3R9_F6_reused_owner_receipt_rejected():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    oid_vote = turns._book(state).oid("population", "vote", ("player", pids[0]),
                                    scope.scope_id)
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0], fact_ref="owner:c1",
                                   scope_id=scope.scope_id, obligation_id=oid_vote)
    ok = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[0],
                              satisfied_kind=turns.KIND_ACTION, owner_receipt=rc,
                              substep="vote")
    assert ok["success"], ok
    size = len(turns._book(state).records)
    before = raw_state(state)
    reuse = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[0],
                                 satisfied_kind=turns.KIND_ACTION, owner_receipt=rc,
                                 substep="campaign")
    assert reuse["success"] is False, "a reused receipt must be rejected"
    assert len(turns._book(state).records) == size
    assert raw_state(state) == before


def test_A3R9_F6_stale_owner_receipt_stored_revision_rejected():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0], fact_ref="owner:c1")
    # a LATER commit advances the ledger revision -> the stored pre-command revision
    # no longer matches (stale) even though no separate argument is supplied.
    turns.complete_actor(state, None, scope.scope_id, "other", actor_player_id=pids[1],
                         satisfied_kind=turns.KIND_EXPLICIT_FINISH)
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION, owner_receipt=rc)
    assert bad["success"] is False
    assert bad["reason"] == "STALE_OWNER_RECEIPT_REVISION"
    assert raw_state(state) == before


def test_A3R9_F6_actor_mismatch_receipt_rejected():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0], fact_ref="owner:c1")
    before = raw_state(state)
    # the receipt binds actor pids[0]; presenting it for pids[1] must be rejected
    bad = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[1],
                               satisfied_kind=turns.KIND_ACTION, owner_receipt=rc)
    assert bad["success"] is False, "a receipt must bind its issuing actor"
    assert not turns._book(state).records
    assert raw_state(state) == before


# ===========================================================================
# A3-R10 — §4.4 owner-authorization binding (R10-1..R10-6). RED-first.
#
# R10-1: an ACTION record MUST carry an engine-issued (registered) command
#        receipt or a COMMITTED owner fact, BOUND to the immutable owner-issued
#        fact — exact actor / scope / OID / command + the receipt's STORED
#        pre-command revision == the current pre-command revision (even when the
#        separate ``core_revision_before`` argument is omitted). A bare / merely
#        namespaced string is NOT an owner fact.
# R10-2: no-action (EXPLICIT_FINISH / STRUCTURAL_NONE) is an OWNER-DECLARED
#        completion; on a REGISTERED Hot-seat session the record must be
#        attributable to the owner boundary (an owner-origin credential or the
#        explicit owner-declared marker). A never-registered CLI/legacy state
#        keeps the historical low-level semantics (a direct primitive call IS
#        the owner declaration — internal/test use; NOT a public API).
# R10-3: the default kind stays EXPLICIT_FINISH so the frozen trace test stays
#        byte-identical and GREEN (no frozen-test edit).
# R10-4: no laundering — a real owner command receipt must NOT be recorded as
#        EXPLICIT_FINISH; no-action must NOT be recorded as ACTION without a
#        bound receipt (MISSING_OWNER_RECEIPT).
# ===========================================================================
def test_A3R10_R1_action_bare_namespaced_string_not_sufficient():
    """A bare namespaced ``authoritative_fact_ref`` is NOT an owner fact (R10-1)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "arbitrary",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION,
                               authoritative_fact_ref="owner:invented")
    assert bad["success"] is False, "a namespaced string must not authorise an ACTION"
    assert bad["reason"] == "MISSING_OWNER_RECEIPT"
    assert not turns._book(state).records
    assert raw_state(state) == before


def test_A3R10_R1_action_receipt_binds_obligation_oid():
    """The engine receipt must BIND the obligation OID (R10-1)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    book = turns._book(state)
    oid_campaign = book.oid("population", "campaign", ("player", pids[0]), scope.scope_id)
    oid_vote = book.oid("population", "vote", ("player", pids[0]), scope.scope_id)
    # R11: the receipt is bound to the CAMPAIGN obligation at ISSUE time (the
    # registered immutable fact is never mutated by a caller).
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0],
                                   fact_ref="owner:c1", scope_id=scope.scope_id,
                                   obligation_id=oid_campaign)
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "c1",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION,
                               owner_receipt=rc, obligation_id=oid_vote)
    assert bad["success"] is False, "a receipt must bind its obligation OID"
    assert raw_state(state) == before


def test_A3R10_R1_action_committed_fact_accepted_but_unregistered_rejected():
    """A registered COMMITTED fact authorises an ACTION; an unregistered string
    does not (R10-1)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    # an engine-issued receipt COMMITS its fact reference (bound to the OID)
    oid_vote = turns._book(state).oid("population", "vote", ("player", pids[0]),
                                    scope.scope_id)
    turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0],
                              fact_ref="owner:c1", scope_id=scope.scope_id,
                              obligation_id=oid_vote)
    # the committed fact (via its fact_ref string) authorises the ACTION
    ok = turns.complete_actor(state, None, scope.scope_id, "c1",
                              actor_player_id=pids[0],
                              satisfied_kind=turns.KIND_ACTION,
                              authoritative_fact_ref="owner:c1")
    assert ok["success"] and ok.get("recorded"), ok
    # a DIFFERENT unregistered namespaced string does not
    bad = turns.complete_actor(state, None, scope.scope_id, "c2",
                               actor_player_id=pids[1],
                               satisfied_kind=turns.KIND_ACTION,
                               authoritative_fact_ref="owner:not-registered")
    assert bad["success"] is False
    assert bad["reason"] == "MISSING_OWNER_RECEIPT"


def test_A3R10_R4_no_laundering_command_receipt_as_no_action():
    """(R10-4a) A real owner COMMAND receipt must NOT be recorded as EXPLICIT_FINISH."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.AI], [])
    scope = turns.mint_scope(state, "population")
    rc = turns.issue_owner_receipt(state, "real-command", actor_player_id=pids[0],
                                   fact_ref="owner:real-command", scope_id=scope.scope_id)
    before = raw_state(state)
    launder = turns.complete_actor(state, None, scope.scope_id, "real-command",
                                   actor_player_id=pids[0],
                                   satisfied_kind=turns.KIND_EXPLICIT_FINISH,
                                   owner_receipt=rc)
    assert launder["success"] is False, \
        "a real command receipt must not be laundered as a no-action"
    assert raw_state(state) == before


def test_A3R10_R4_no_action_as_action_without_receipt_rejected():
    """(R10-4b) A no-action recorded as ACTION without a bound receipt is rejected."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    bad = turns.complete_actor(state, None, scope.scope_id, "noop",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION)
    assert bad["success"] is False
    assert bad["reason"] == "MISSING_OWNER_RECEIPT"


def test_A3R10_R2_no_action_on_registered_requires_owner_declaration():
    """On a REGISTERED Hot-seat session a no-action record needs an owner-origin
    credential or the explicit owner-declared marker (R10-2)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    scope = turns.mint_scope(state, "population")
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "fin",
                               actor_player_id=pids[0], phase="population",
                               substep="vote",
                               satisfied_kind=turns.KIND_EXPLICIT_FINISH)
    assert bad["success"] is False, "a registered no-action needs an owner declaration"
    assert bad["reason"] == "MISSING_OWNER_DECLARATION"
    assert not turns._book(state).records
    assert raw_state(state) == before


def test_A3R10_R2_owner_declared_marker_accepted_on_registered():
    """The explicit owner-declared marker authorises a registered no-action (R10-2)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    scope = turns.mint_scope(state, "population")
    ok = turns.complete_actor(state, None, scope.scope_id, "fin",
                              actor_player_id=pids[0], phase="population",
                              substep="vote",
                              satisfied_kind=turns.KIND_EXPLICIT_FINISH,
                              owner_declared=True)
    assert ok["success"] and ok.get("recorded"), ok


def test_A3R10_R2_swallowed_none_or_exception_not_lawful_no_action():
    """A swallowed None / exception is NOT a lawful no-action (R10-2, Turn-Order §3)."""
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    _mk_controllers(state, [PlayerType.AI, PlayerType.AI], [])
    res = turns.continue_after_command(
        state, phase="forum",
        ai_executor=lambda s, t: (_ for _ in ()).throw(RuntimeError("swallowed")))
    assert res.masked_failure and not res.ok
    assert not turns._book(state).records
    res2 = turns.continue_after_command(state, phase="forum",
                                        ai_executor=lambda s, t: None)
    assert res2.masked_failure and not res2.ok
    assert not turns._book(state).records


def test_A3R10_R3_default_kind_preserved_for_frozen_test():
    """The primitive default kind is EXPLICIT_FINISH (no-action) so the frozen
    trace test stays byte-identical and GREEN (R10-3)."""
    import inspect
    sig = inspect.signature(turns.complete_actor)
    assert sig.parameters["satisfied_kind"].default == turns.KIND_EXPLICIT_FINISH
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    r = turns.complete_actor(state, None, scope.scope_id, "bare",
                             actor_player_id=pids[0], phase="population", substep="vote")
    assert r["success"] and r.get("recorded")


# ===========================================================================
# A3-R11 — G5 RETURN #5 rework (V10-F01..F04). §4.4 owner-authorization binding.
#   F01: exact command/operation binding; missing binding fields never wildcard.
#   F02: issued fact is an immutable private snapshot; both routes consume it.
#   F03: public Store finish is authorized before any ledger/receipt mutation.
#   F04: ACTION-fact/no-action rejected consistently on BOTH routes (real command).
# ===========================================================================
def test_A3R11_F01_command_mismatch_rejected():
    """A registered receipt issued for command c1 must NOT satisfy command c2."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    oid_vote = turns._book(state).oid("population", "vote", ("player", pids[0]),
                                    scope.scope_id)
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0],
                                   fact_ref="owner:c1", scope_id=scope.scope_id,
                                   obligation_id=oid_vote)
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "c2",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION, owner_receipt=rc)
    assert bad["success"] is False, "a receipt for c1 must not satisfy command c2"
    assert not turns._book(state).records
    assert raw_state(state) == before


def test_A3R11_F01_missing_binding_field_is_not_a_wildcard():
    """A receipt missing the bound scope/OID/actor is rejected — never wildcarded."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    book = turns._book(state)
    before = raw_state(state)
    # (a) issued WITHOUT scope/OID -> a bound completion must be rejected
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0], fact_ref="owner:c1")
    bad = turns.complete_actor(state, None, scope.scope_id, "c1",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION, owner_receipt=rc)
    assert bad["success"] is False, "a receipt missing the bound scope/OID must be rejected"
    assert not book.records
    assert raw_state(state) == before
    # (b) issued WITHOUT actor -> a player-bound completion must be rejected (no None
    # wildcard over the player seat)
    oid_vote = book.oid("population", "vote", ("player", pids[0]), scope.scope_id)
    rc2 = turns.issue_owner_receipt(state, "c1", actor_player_id=None, fact_ref="owner:c1b",
                                    scope_id=scope.scope_id, obligation_id=oid_vote)
    bad2 = turns.complete_actor(state, None, scope.scope_id, "c1",
                                actor_player_id=pids[0],
                                satisfied_kind=turns.KIND_ACTION, owner_receipt=rc2)
    assert bad2["success"] is False, "a None actor must not wildcard a player completion"
    assert not book.records
    assert raw_state(state) == before


def test_A3R11_F02_mutating_returned_object_does_not_alter_registered_fact():
    """The returned receipt is a SEPARATE copy; mutating it cannot alter the
    authoritative registered fact, and the altered presentation is rejected (F02)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    book = turns._book(state)
    oid_vote = book.oid("population", "vote", ("player", pids[0]), scope.scope_id)
    rc = turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0],
                                   fact_ref="owner:c1", scope_id=scope.scope_id,
                                   obligation_id=oid_vote)
    # mutate the returned object
    rc["command"] = "forged"
    rc["obligation_id"] = ("forged",)
    registered = book.receipts[rc["receipt_id"]]
    assert registered["command"] == "c1", "the registered immutable fact was mutated"
    assert registered["obligation_id"] == oid_vote
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "c1",
                               actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION, owner_receipt=rc)
    assert bad["success"] is False
    assert not book.records
    assert raw_state(state) == before


def test_A3R11_F02_fact_ref_route_consumes_receipt_once():
    """A successful fact-ref ACTION consumes the resolved immutable receipt, so a
    repeated presentation is rejected (F02)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    scope = turns.mint_scope(state, "population")
    book = turns._book(state)
    oid_vote = book.oid("population", "vote", ("player", pids[0]), scope.scope_id)
    turns.issue_owner_receipt(state, "c1", actor_player_id=pids[0],
                              fact_ref="owner:c1", scope_id=scope.scope_id,
                              obligation_id=oid_vote)
    ok = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[0],
                              satisfied_kind=turns.KIND_ACTION,
                              authoritative_fact_ref="owner:c1")
    assert ok["success"] and ok.get("recorded"), ok
    rid = next(iter(book.receipts))
    assert rid in book.consumed_receipts, "the fact-ref credential must be consumed"
    before = raw_state(state)
    bad = turns.complete_actor(state, None, scope.scope_id, "c1", actor_player_id=pids[0],
                               satisfied_kind=turns.KIND_ACTION,
                               authoritative_fact_ref="owner:c1", substep="campaign")
    assert bad["success"] is False, "a reused fact-ref credential must be rejected"
    assert raw_state(state) == before


def test_A3R11_F04_action_receipt_and_fact_ref_not_relabelled_no_action():
    """An ACTION credential presented as a no-action must be rejected on BOTH the
    presented-receipt route AND the registered fact-ref route (F04)."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    scope = turns.mint_scope(state, "population")
    book = turns._book(state)
    oid_vote = book.oid("population", "vote", ("player", pids[0]), scope.scope_id)
    rc = turns.issue_owner_receipt(state, "cmd", actor_player_id=pids[0],
                                   fact_ref="owner:cmd", scope_id=scope.scope_id,
                                   obligation_id=oid_vote, kind=turns.KIND_ACTION)
    before = raw_state(state)
    # (a) presented-receipt route
    bad1 = turns.complete_actor(state, None, scope.scope_id, "cmd",
                                actor_player_id=pids[0],
                                satisfied_kind=turns.KIND_EXPLICIT_FINISH,
                                owner_receipt=rc, owner_declared=True)
    assert bad1["success"] is False, "an ACTION receipt must not be relabelled no-action"
    # (b) registered fact-ref route (the previously UNCHECKED route)
    bad2 = turns.complete_actor(state, None, scope.scope_id, "cmd",
                                actor_player_id=pids[0],
                                satisfied_kind=turns.KIND_EXPLICIT_FINISH,
                                authoritative_fact_ref="owner:cmd", owner_declared=True)
    assert bad2["success"] is False, "an ACTION fact-ref must not authorise a no-action"
    assert not book.records
    assert raw_state(state) == before


def test_A3R11_F04_real_command_fact_cannot_be_relabelled_no_action():
    """A REAL senate veto command's ACTION fact cannot be relabelled as a no-action
    (both routes); a genuine optional-duty no-action finish stays lawful (F04)."""
    state, pids = _senate_state([PlayerType.HUMAN, PlayerType.HUMAN, PlayerType.HUMAN], [],
                                registered=True)
    ctx = session_access.present_context(state)
    saved = _set_offices(state, {pids[0]: "consul", pids[0]: "tribune"})
    try:
        lv_faction = state.get_player(pids[-1]).faction_id
        principal_faction = state.get_player(pids[0]).faction_id
        assert lv_faction != principal_faction
        for m in state.get_living_members():
            if m.faction_id == lv_faction and m.office == "tribune":
                m.office = "quaestor"
        scope = turns.mint_scope(state, "senate")
        pid_prop = state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
        for pid in pids:
            state.record_senate_vote(pid, pid_prop, True)
        veto = next(o for o in turns.obligations(state, "senate").obligations
                    if o.substep == "veto")
        assert veto.actor_player_id == pids[0]
        turns.select_scheduled_actor(state, "senate", pids[0], scope.scope_id)
        acted = senate_api.veto(state, pids[0], [pid_prop], caller_context=ctx)
        assert acted["success"] is True, acted.get("message")
        book = turns._book(state)
        actions = [r for r in book.records if r.satisfied_kind == turns.KIND_ACTION]
        assert actions, "the real owner command must record an ACTION receipt"
        fact_ref = actions[-1].authoritative_fact_ref
        assert fact_ref.startswith("senate-veto:")
        before = raw_state(state)
        records_before = len(book.records)
        # (a) fact-ref route — the real command fact must not relabel as no-action
        launder_fact = turns.complete_actor(
            state, None, scope.scope_id, "senate_veto_decision",
            phase="senate", substep="veto",
            satisfied_kind=turns.KIND_EXPLICIT_FINISH,
            authoritative_fact_ref=fact_ref, owner_declared=True)
        assert launder_fact["success"] is False, \
            "a real command ACTION fact must not be relabelled as a no-action"
        # (b) presented-receipt route
        rc = dict(book.committed_facts[fact_ref])
        launder_receipt = turns.complete_actor(
            state, None, scope.scope_id, "senate_veto_decision",
            phase="senate", substep="veto",
            satisfied_kind=turns.KIND_EXPLICIT_FINISH,
            owner_receipt=rc, owner_declared=True)
        assert launder_receipt["success"] is False, \
            "a real command receipt must not be relabelled as a no-action"
        assert len(book.records) == records_before, "no relabelled record was written"
        assert raw_state(state) == before
        # control: a genuine optional-duty no-action finish is still lawful
        forum_scope = turns.mint_scope(state, "forum")
        ok_noaction = turns.complete_actor(
            state, None, forum_scope.scope_id, "optional-finish",
            actor_player_id=pids[0], phase="forum", substep="retirement",
            satisfied_kind=turns.KIND_EXPLICIT_FINISH, owner_declared=True)
        assert ok_noaction["success"] and ok_noaction.get("recorded")
    finally:
        _restore_offices(state, saved)


def test_A3R11_F03_registered_masked_store_finish_denied():
    """A masked (suspended) registered seat's public Store finish must be DENIED
    before any ledger/receipt/business mutation (F03)."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    store._forum_step_override = "retirement"
    session_access.suspend_hotseat_session(state)
    book = turns._book(state)
    records_before = len(book.records)
    receipts_before = len(book.receipts)
    before = raw_state(state)
    feedback = store.doCompleteForumStep()
    assert feedback["success"] is False, "a masked seat must not record a finish"
    assert len(book.records) == records_before
    assert len(book.receipts) == receipts_before
    assert raw_state(state) == before


def test_A3R11_F03_registered_wrong_human_store_finish_denied():
    """A registered Store finish invoked for the WRONG HUMAN (not the seat's
    current actor/principal) must be DENIED before any mutation (F03)."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    store._forum_step_override = "retirement"
    store._viewer_id = pids[1]  # a different HUMAN than the current actor/principal
    book = turns._book(state)
    records_before = len(book.records)
    receipts_before = len(book.receipts)
    before = raw_state(state)
    feedback = store.doCompleteForumStep()
    assert feedback["success"] is False, "a wrong-HUMAN finish must be denied"
    assert len(book.records) == records_before
    assert len(book.receipts) == receipts_before
    assert raw_state(state) == before


def test_A3R11_F03_registered_authorized_store_finish_records(monkeypatch):
    """Positive control: an AUTHORIZED registered Store finish IS recorded in the
    ONE session ledger (F03)."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    store._forum_step_override = "retirement"
    # MOCK_AUXILIARY: the downstream market-open seal (forum_api.initialize_forum_turn
    # nesting under a registered seat) is NOT the F03 subject; stub it so the
    # assertion isolates whether the AUTHORIZED finish was admitted + recorded.
    monkeypatch.setattr(store._adapter, "open_forum_market",
                        lambda *a, **k: {"success": True, "data": {}})
    book = turns._book(state)
    scope = turns.mint_scope(state, "forum")
    feedback = store.doCompleteForumStep()
    assert feedback["success"] is True, feedback.get("message")
    oid = book.oid("forum", "retirement", ("player", pids[0]), scope.scope_id)
    assert book.satisfied(oid, scope.scope_id, turns.current_revision(state)), \
        "an authorized finish must be recorded in the ledger"


def test_A3R11_F03_population_completion_result_is_checked(monkeypatch):
    """The population public writer must CHECK the owner completion result and NOT
    rotate the cursor when the completion was rejected (F03)."""
    from src.api import player_api
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.HUMAN, PlayerType.HUMAN], [PlayerType.AI])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    ctx = session_access.present_context(state)
    monkeypatch.setattr(turns, "complete_actor",
                        lambda *a, **k: {"success": False, "reason": "COMPLETION_REJECTED"})
    calls = {"n": 0}
    real_next = player_api.next_player

    def spy(*a, **k):
        calls["n"] += 1
        return real_next(*a, **k)

    monkeypatch.setattr(player_api, "next_player", spy)
    resp = session_api.complete_population_player(state, pids[0], caller_context=ctx)
    assert resp["success"] is False
    assert calls["n"] == 0, "a rejected completion must not proceed to the cursor rotation"


# ===========================================================================
# A3-R12 — G5 RETURN #6 rework (V11-F01 / V11-F02).  RED-first.
#
# V11-F01: a registered Forum owner-chain must NOT publish a false market-open
#   success.  The positive control drives the REAL Store->Adapter->forum owner->
#   canonical initializer chain (NO stub of that transition) and asserts the
#   authoritative init/business facts exactly once; a refused/failed initializer
#   must not publish market success.
# V11-F02: an ACCEPTED committed AI Forum command must be recorded as a receipt-
#   bound ACTION (never an EXPLICIT_FINISH relabel); a genuine no-choice finish
#   stays a lawful owner no-action declaration; the AI command fact cannot be
#   relabelled on either route.
# ===========================================================================
def _registered_forum_store(humans, ais):
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, humans, ais)
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    return state, pids, store


def _force_retireable_member(state, faction):
    """Make the faction deterministically retireable (a non-leader, office-less,
    contract-free member) and return the eligible list."""
    members = list(faction.get_members(state))
    for m in members:
        if not m.is_faction_leader and m.office:
            m.office = None
    return [m for m in members
            if not m.is_faction_leader
            and not (m.office and not str(m.office).startswith("ex-"))
            and not m.has_active_contract]


def test_A3R12_F01_registered_store_real_owner_chain_opens_market_once():
    """V11-F01 positive control: a registered current-HUMAN public finish travels
    the REAL Store->Adapter->forum owner->canonical initializer chain (the
    transition is NOT stubbed) and publishes the canonical init/business facts
    exactly once."""
    from src.core.entities.contract import ContractType
    state, pids, store = _registered_forum_store([PlayerType.HUMAN], [PlayerType.AI])
    # every non-viewer seat's retirement is already finished -> the AI drain has no
    # outstanding work, so the route reaches the REAL market open.
    for pid in pids[1:]:
        rec = store._record_forum_ledger_finish(pid, "retirement", f"prep:{pid}")
        assert rec.get("success"), rec
    figures_before = len(state.curia.get_all_available())
    feedback = store.doCompleteForumStep()
    assert feedback["success"] is True, feedback.get("message")
    # authoritative canonical-initialization facts (the REAL initializer ran once)
    assert state.get_forum_pending().get("forum_initialized")
    assert state.get_forum_pending().get("market_opened")
    ws = state.get_war_system()
    assert ws is not None and any(w.id == "pyrrhic_war" for w in ws.get_threat_wars())
    italy = [c for c in state.get_all_contracts()
             if c.contract_type == ContractType.PUBLIC_WORKS and c.province_id == 0]
    assert italy, "the canonical initializer must generate the Italy PUBLIC_WORKS contract"
    assert len(state.curia.get_all_available()) > figures_before, \
        "the canonical initializer must generate the turn's market figures"
    # exactly-once: a re-open is a no-op (no re-initialization, no duplicate facts)
    n_contracts = len(state.get_all_contracts())
    n_figures = len(state.curia.get_all_available())
    again = store._adapter.open_forum_market(pids[0])
    assert again["success"] is True
    assert again["data"]["generated_figures"] == []
    assert len(state.get_all_contracts()) == n_contracts
    assert len(state.curia.get_all_available()) == n_figures


def test_A3R12_F01_refused_initializer_cannot_publish_market_success(monkeypatch):
    """V11-F01 negative: a refused/failed canonical initializer must NOT publish a
    false market-open success.  MOCK_AUXILIARY: the initializer is forced to
    refuse at the open_market->initialize_forum_turn seam (the fault stimulus);
    the raw pre-commit boundary is the oracle."""
    from src.api import forum_api
    state, pids, store = _registered_forum_store([PlayerType.HUMAN], [PlayerType.AI])
    for pid in pids[1:]:
        store._record_forum_ledger_finish(pid, "retirement", f"prep:{pid}")
    scope = turns.mint_scope(state, "forum")
    turns.complete_actor(state, None, scope.scope_id, "viewer-ret",
                         actor_player_id=pids[0], phase="forum", substep="retirement",
                         satisfied_kind=turns.KIND_EXPLICIT_FINISH, owner_declared=True)
    assert turns.forum_substep_ready(state, "retirement")

    def _refuse(*a, **k):
        return {"success": False, "message": "init refused",
                "data": {}, "errors": ["INIT_REFUSED"]}

    monkeypatch.setattr(forum_api, "initialize_forum_turn", _refuse)
    before = raw_state(state)
    feedback = store._adapter.open_forum_market(pids[0])
    assert feedback["success"] is False, \
        "a refused initializer must not publish a false market success"
    assert not state.get_forum_pending().get("market_opened")
    assert raw_state(state) == before


def test_A3R12_F02_real_ai_command_records_action_receipt_once():
    """V11-F02: a deterministic REAL mutating Forum owner command driven through the
    Store writer records a receipt-bound ACTION (never an EXPLICIT_FINISH relabel),
    with the raw domain effect; a post-commit retry does not replay the effect."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    # first seat AI (processed), a later HUMAN stops further AI work.
    pids = _mk_controllers(state, [PlayerType.AI, PlayerType.HUMAN], [])
    state.config.political_rules.retirement_chance = 1.0
    ai_pid = pids[0]
    ai_player = state.get_player(ai_pid)
    faction = state.get_faction(ai_player.faction_id)
    eligible = _force_retireable_member(state, faction)
    assert eligible, "deterministic retire requires an eligible faction member"
    faction_ids_before = {m.id for m in faction.get_members(state)}
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    scope = turns.mint_scope(state, "forum")
    book = turns._book(state)
    oid = book.oid("forum", "retirement", ("player", ai_pid), scope.scope_id)
    store._process_ai_factions_forum("retirement")
    recs = [r for r in book.records if r.obligation_id == oid]
    assert recs, "the real AI retirement must be recorded"
    rec = recs[-1]
    assert rec.satisfied_kind == turns.KIND_ACTION, \
        "a real accepted AI command must be recorded as ACTION, not EXPLICIT_FINISH"
    assert rec.authoritative_fact_ref.startswith("ai-receipt:"), rec.authoritative_fact_ref
    assert book.satisfied(oid, scope.scope_id, turns.current_revision(state))
    # raw domain effect: a real member left the faction into the curia (retired)
    curia_ids = {f.id for f in state.curia.get_all_available()}
    assert faction_ids_before & curia_ids, \
        "the real retire_figure must move a member into the curia"
    # post-commit retry: no replay, no duplicate effect
    n_records = len(book.records)
    curia_after = {f.id for f in state.curia.get_all_available()}
    store._process_ai_factions_forum("retirement")
    assert len(book.records) == n_records, "a completed seat must never be replayed"
    assert {f.id for f in state.curia.get_all_available()} == curia_after


def test_A3R12_F02_real_no_choice_is_lawful_owner_no_action():
    """V11-F02 retention: a genuine no-choice finish (the eligible decider declines)
    is a LAWFUL owner no-action declaration (EXPLICIT_FINISH), not an ACTION."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.AI, PlayerType.HUMAN], [])
    state.config.political_rules.retirement_chance = 0.0  # decider declines
    ai_pid = pids[0]
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    scope = turns.mint_scope(state, "forum")
    book = turns._book(state)
    oid = book.oid("forum", "retirement", ("player", ai_pid), scope.scope_id)
    store._process_ai_factions_forum("retirement")
    recs = [r for r in book.records if r.obligation_id == oid]
    assert recs, "the no-choice finish must still be recorded (lawful no-action)"
    assert recs[-1].satisfied_kind == turns.KIND_EXPLICIT_FINISH
    assert book.satisfied(oid, scope.scope_id, turns.current_revision(state))


def test_A3R12_F02_ai_command_fact_not_relabelled_no_action_both_routes():
    """V11-F02: the AI command's committed ACTION fact cannot be relabelled as a
    no-action on EITHER the fact-ref route or the presented-receipt route."""
    from src.ui.gui.session_store import GuiSessionStore
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result
    state = result["data"]["state"]
    pids = _mk_controllers(state, [PlayerType.AI, PlayerType.HUMAN], [])
    state.config.political_rules.retirement_chance = 1.0
    ai_pid = pids[0]
    ai_player = state.get_player(ai_pid)
    faction = state.get_faction(ai_player.faction_id)
    assert _force_retireable_member(state, faction)
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    scope = turns.mint_scope(state, "forum")
    book = turns._book(state)
    oid = book.oid("forum", "retirement", ("player", ai_pid), scope.scope_id)
    store._process_ai_factions_forum("retirement")
    recs = [r for r in book.records if r.obligation_id == oid]
    assert recs and recs[-1].satisfied_kind == turns.KIND_ACTION, recs
    fact_ref = recs[-1].authoritative_fact_ref
    before = raw_state(state)
    n_records = len(book.records)
    # (a) fact-ref route
    launder_ref = turns.complete_actor(
        state, None, scope.scope_id, "process_retirement",
        obligation_id=oid, actor_player_id=ai_pid, phase="forum", substep="retirement",
        satisfied_kind=turns.KIND_EXPLICIT_FINISH,
        authoritative_fact_ref=fact_ref, owner_declared=True)
    assert launder_ref["success"] is False, \
        "an AI command ACTION fact must not be relabelled no-action (fact-ref route)"
    # (b) presented-receipt route
    rc = dict(book.committed_facts[fact_ref])
    launder_rc = turns.complete_actor(
        state, None, scope.scope_id, "process_retirement",
        obligation_id=oid, actor_player_id=ai_pid, phase="forum", substep="retirement",
        satisfied_kind=turns.KIND_EXPLICIT_FINISH,
        owner_receipt=rc, owner_declared=True)
    assert launder_rc["success"] is False, \
        "an AI command receipt must not be relabelled no-action (receipt route)"
    assert len(book.records) == n_records, "no relabelled record was written"
    assert raw_state(state) == before

