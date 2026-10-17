"""EOR20261013-02 · Rework-D1D2 — masked-path integration regression + closure.

RED-first proof for the D1/D2 root-cause domain ("seat authority x coordinator
cursor x Store masked handoff"), per the FROZEN design:

  * ``S-D1D2-Rework-Design-Delta_2026-10-16.md``  (sec 2 authority model / sec 3 D1 /
    sec 4 D2 / sec 5 FC+AC)
  * ``S-D1D2-Rework_Implementation_and_Test_Overlay_2026-10-16.md`` (sec 1 write face /
    sec 3 test overlay)

Covered (W-T1 / W-T2):
  * T-CLOS-01 / AC-CLOS-01  closure-consistency assertion (FC-D1-03): each masked
    owning command's ``_LEASE_HELPERS`` set is EXACTLY its internal guarded-boundary
    closure, and no internal boundary lacking a ``command=`` label may be reachable
    (i.e. the public ``get_candidates`` read boundary is never reached inside the
    transaction-local continuation scope);
  * T-MASK-1H-POP-01/02/03  AC-D1-1H-01/02/03  1H+2AI masked population vote;
  * T-MASK-3H-POP-01        AC-D1-3H-01        3H masked population vote;
  * T-MASK-3H-FORUM-01/02   AC-D2-3H-01/02     3H masked forum retirement / market;
  * T-INV-01                AC-D2-3H-03        seat-sync invariant;
  * T-NEG-01/02/03          AC-NEG-01/02/03    the guard is NOT relaxed.

Scenarios: COMMITTED fixtures only (``gr_f_3h.json``). The 1H+2AI composition is
constructed IN-TEST — there is NO dependency on the Owner-modified working-tree
``data/scenarios/gui_prototype.json``. No product / QML / data file is changed.

WATERMARK: DA-Execute masked-path regression; no commit/push/delete.
"""
from __future__ import annotations

import copy
import functools
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import population_api
from src.api import session_access
from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"
DENIED_TEXT = "Operation unavailable for this seat"

#: The FROZEN expected closure (source of truth for T-CLOS-01). `get_candidates`
#: is deliberately ABSENT (internal reads use the private ``_get_candidates_impl``).
EXPECTED_HELPERS = {
    "submit_population_votes": frozenset({
        "begin_population_phase", "batch_vote", "complete_population_player",
        "resolve_population_slice", "process_population_disbandments",
        "resolve_election", "campaign", "vote",
    }),
    "resolve_population_slice": frozenset({
        "begin_population_phase", "process_population_disbandments",
        "resolve_election", "campaign", "vote",
    }),
    "doCompleteForumStep": frozenset({"retire_figure"}),
    "doResolveForum": frozenset({
        "recruit_figure", "place_bid", "buy_land", "vote_triumph",
    }),
}


@pytest.fixture(autouse=True)
def _restore_rng():
    st = random.getstate()
    try:
        yield
    finally:
        random.setstate(st)


# ---------------------------------------------------------------------------
# Labelled harness witnesses (barrier / receiver only; the business
# Store/Adapter/coordinator chain stays production).
# ---------------------------------------------------------------------------
class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    """Synchronous barrier witness (NO async frame gates), so the masked
    transaction completes inline on an offscreen host."""

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


# ---------------------------------------------------------------------------
# Test-internal construction (never the Owner-modified worktree file)
# ---------------------------------------------------------------------------
def _force_ai(state, pid):
    original = state.get_player(pid)
    state.remove_player(pid)
    state.add_player(Player(player_id=pid, faction_id=original.faction_id,
                            player_type=PlayerType.AI))


def _prepared(start_phase, ai_tail=0):
    """Factory-created session from the COMMITTED fixture; the 1H/2AI composition
    is built in-test (force the trailing controllers to AI)."""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase=start_phase, scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert len(pids) == 3, pids
    if ai_tail:
        for pid in pids[len(pids) - ai_tail:]:
            _force_ai(state, pid)
        state.set_turn_order([pids[0]])
    state.set_current_player(pids[0])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _masked_store(state, viewer):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness()
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE
    return store, witness


def _first_selections(state):
    impl = population_api._get_candidates_impl(state)
    data = impl.get("data", {}) if impl.get("success") else {}
    return {office: rows[0]["id"] for office, rows in data.items() if rows}


# ===========================================================================
# T-CLOS-01 / AC-CLOS-01 — closure-consistency assertion (FC-D1-03)
# ===========================================================================
def test_clos_01_helper_sets_are_exact_and_exclude_public_read():
    helpers = GuiSessionStore._LEASE_HELPERS
    assert set(helpers) == set(EXPECTED_HELPERS)
    for command, expected in EXPECTED_HELPERS.items():
        assert helpers[command] == expected, (command, helpers[command])
        # the owning command is never its own helper; the PUBLIC guarded read
        # boundary is never reachable inside the continuation scope.
        assert command not in helpers[command]
        assert "get_candidates" not in helpers[command]


def test_clos_01_every_effective_mask_label_has_a_declared_closure(monkeypatch):
    """R-01 / AC-CLOS-01: the owning labels are DERIVED from the ACTUAL dispatch
    (the Store's ``_dispatch_owning``), never hand-written. Every effective masked
    owning command must either carry a declared ``_LEASE_HELPERS`` closure or
    prove an EMPTY real internal closure (else its own internal guarded work would
    fall back to an empty helper set and be DENIED)."""
    probe, results, per_driver = _collect_closure(monkeypatch)
    effective = set(probe.dispatched)          # DERIVED from the real dispatch
    assert effective, "the probe must observe real owning dispatches"
    declared = GuiSessionStore._LEASE_HELPERS
    for label in effective:
        helpers = declared.get(label)
        if helpers is None:
            assert probe.observed_helpers().get(label, set()) == {label}, (
                "dispatched masked owning command without a declared closure must "
                "have an empty real closure", label)


# ===========================================================================
# T-MASK-1H-POP — 1H + 2AI masked population vote (AC-D1-1H-01/02)
# ===========================================================================
def _submit_1h(store, state):
    return store.submitPopulationVotes(_first_selections(state))


def test_mask_1h_pop_01_vote_submits_success_no_denied():
    state, pids = _prepared("population", ai_tail=2)
    store, witness = _masked_store(state, pids[0])

    fb = _submit_1h(store, state)
    assert fb["success"] is True, fb
    # same-seat recovery: the viewer/principal is unchanged and the seat is ACTIVE.
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store.viewerPlayerId == pids[0]
    assert store.handoffMaskVisible is False

    # ballots recorded (5 fixed-five entries; abstentions allowed)
    votes = [v for v in state.get_population_votes() if v[0] == pids[0]]
    assert len(votes) == 5, votes

    blob = repr(fb)
    assert DENIED_TEXT not in blob
    assert "CANDIDATES_UNAVAILABLE" not in blob
    assert "masked_failure" not in blob
    # the masked transaction really ran (barrier armed + reveal)
    kinds = [c[0] for c in witness.calls]
    assert "arm" in kinds and "unmask" in kinds


def test_mask_1h_pop_02_election_resolves_and_same_seat_recovers():
    state, pids = _prepared("population", ai_tail=2)
    store, witness = _masked_store(state, pids[0])

    fb = _submit_1h(store, state)
    assert fb["success"] is True, fb
    # the election settled (population phase result landed) ...
    assert state.get_phase_result("population") is not None
    assert store.populationResolved is True
    # ... and the seat recovered same-seat at a fresh epoch (no MASKED_FAILURE).
    assert store.seatLifecycle == SEAT_ACTIVE
    assert witness.pendings == []          # no artificial handoff on a same seat
    assert session_access.current_caller_context(state) is not None
    assert session_access.current_lease_token(state) is None


def test_mask_1h_pop_03_chain_probe_no_internal_deny(monkeypatch):
    """AC-D1-1H-03 (R-02): the chain probe CLASSIFIES each guard decision instead
    of washing away every READ denial. It distinguishes a legitimate MASKED
    EXTERNAL PROJECTION refusal (the Store's post-op projection refresh, made
    while the seat is masked) from an owning INTERNAL BUSINESS read/call. It then
    asserts, per internal read site, that NO ``DENIED`` is returned, and that
    INSIDE the owning dispatch window EVERY internal call (READ *and* MUTATE) is
    authorised — while the external projection refusals are still observed (so the
    pass is not produced by excluding all READ denials)."""
    state, pids = _prepared("population", ai_tail=2)
    store, witness = _masked_store(state, pids[0])
    probe = ClosureProbe()
    probe.install(monkeypatch)

    # observe every INTERNAL business read (the service-private validated-read
    # boundary the owning continuation must use) and its real envelope.
    reads = []
    orig_impl = population_api._get_candidates_impl

    def impl_spy(st):
        r = orig_impl(st)
        reads.append(r)
        return r
    monkeypatch.setattr(population_api, "_get_candidates_impl", impl_spy)

    fb = _submit_1h(store, state)
    assert fb["success"] is True, fb

    # (A) per-SITE assertion: every internal business read returned success and no
    #     DENIED envelope. (If the internal read regressed to the PUBLIC guarded
    #     boundary, no private-impl read would be observed -> `assert reads` fails.)
    assert reads, "the chain must have performed internal candidate reads"
    for r in reads:
        assert r.get("success") is True, r
        codes = {e.get("code") for e in (r.get("errors") or [])
                 if isinstance(e, dict)}
        assert "DENIED" not in codes, r

    # (B) inside the owning dispatch window EVERY internal call is authorised —
    #     READ and MUTATE alike (no DENIED link anywhere in the chain).
    biz = probe.business_calls()
    assert biz, "the owning dispatch window must have exercised internal calls"
    assert [(c["owning"], c["op"], c["command"])
            for c in biz if not c["allowed"]] == []
    # the window really carried the labelled owning/helper boundaries (and the
    # un-labelled internal reads never reach a public guarded boundary).
    assert {c["command"] for c in biz} >= {"submit_population_votes", "batch_vote"}
    assert None not in {c["command"] for c in biz}

    # (C) the legitimate MASKED EXTERNAL PROJECTION refusals ARE observed and
    #     classified as such — we did NOT exclude all READ denials to claim
    #     "no DENIED". These are the Store's masked projection refresh reads.
    proj = probe.projection_calls()
    assert proj, "expected masked external projection reads inside the window"
    proj_denied = [c for c in proj if not c["allowed"]]
    assert proj_denied, "the masked projection refresh must be refused"
    assert all(c["reason"] for c in proj_denied)
    # and the two classes are disjoint: no projection read was counted as business.
    assert all(c not in biz for c in proj)


# ===========================================================================
# T-MASK-3H-POP — 3H masked population vote (AC-D1-3H-01)
# ===========================================================================
def test_mask_3h_pop_01_each_human_submits_with_paired_handoffs():
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])
    takeovers = 0

    for _ in range(3):
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            takeovers += 1
        assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
        fb = _submit_1h(store, state)
        assert fb["success"] is True, fb

    # every human seat recorded its five ballots and the slice resolved.
    for pid in pids:
        assert len([v for v in state.get_population_votes() if v[0] == pid]) == 5, pid
    assert state.get_phase_result("population") is not None
    assert store.seatLifecycle == SEAT_ACTIVE
    assert takeovers == 2, takeovers   # A -> B -> C (two handoffs; C same-seat)


# ===========================================================================
# T-MASK-3H-FORUM — 3H masked forum finish (AC-D2-3H-01/02)
# ===========================================================================
def test_mask_3h_forum_01_retirement_handoff_pairs_cursor_and_authority():
    state, pids = _prepared("forum")
    store, witness = _masked_store(state, pids[0])

    fb = store.doCompleteForumStep()
    # a next HUMAN exists -> the seat enters MASKED_PENDING_HANDOFF (no stale read).
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert store.viewerPlayerId == ""
    assert witness.pendings, witness.calls
    faction_b = state.get_faction(state.get_player(pids[1]).faction_id).name
    assert witness.pendings[-1] == faction_b

    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]

    # INV-SEAT-SYNC: principal == Core current HUMAN.
    rec = session_access._record(state)
    current = state.get_current_player()
    assert rec.principal_player_id == pids[1]
    assert current.player_id == pids[1]

    # the forum view is freshly readable for the new seat (no swallowed {}).
    store._refresh_forum_view()
    assert isinstance(store.forumView, dict) and "current_step" in store.forumView


def test_mask_3h_forum_02_full_retirement_market_resolves():
    state, pids = _prepared("forum")
    store, witness = _masked_store(state, pids[0])

    steps = 0
    while not store.forumResolved and steps < 12:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
        # INV-SEAT-SYNC at every ACTIVE publication point.
        rec = session_access._record(state)
        assert rec.principal_player_id == state.get_current_player().player_id
        if store.forumCurrentStep == "retirement":
            fb = store.doCompleteForumStep()
        else:
            fb = store.doResolveForum()
        assert fb["success"] is True, fb

    assert store.forumResolved is True
    assert state.get_phase_result("forum") is not None
    assert steps < 12, steps


# ===========================================================================
# Negatives — the guard is NOT relaxed (AC-NEG-01/02/03)
# ===========================================================================
def test_neg_01_public_read_denied_without_presented_handle_and_no_mutation():
    state, pids = _prepared("population")
    before = copy.deepcopy(state.to_dict())
    # missing handle
    res = session_api.get_population_view(state, pids[0])
    assert res.get("success") is False
    assert "DENIED" in {e.get("code") for e in (res.get("errors") or [])}
    # forged / freely-constructed handle (no registry issuance identity)
    forged = session_access.HotseatContext(session_id="session-forged",
                                           principal_player_id=pids[0])
    res2 = session_api.get_population_view(state, pids[0], caller_context=forged)
    assert res2.get("success") is False
    # zero mutation on both refusals
    assert copy.deepcopy(state.to_dict()) == before


def test_neg_02_public_mutation_denied_while_masked():
    state, pids = _prepared("forum")
    store, witness = _masked_store(state, pids[0])
    store.doCompleteForumStep()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    # a public mutation during the masked/pending window is DENIED (public handle
    # revoked), and mutates nothing.
    before = copy.deepcopy(state.to_dict())
    res = population_api.begin_population_phase(state)
    assert res.get("success") is False
    assert "DENIED" in {e.get("code") for e in (res.get("errors") or [])}
    assert copy.deepcopy(state.to_dict()) == before


def test_neg_03_helper_label_replay_without_live_scope_denied():
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])
    # open a masked transaction (real lease + continuation scope), then destroy the
    # scope: a helper label can no longer be replayed.
    txn = store._begin_masked_seat_transition(
        "submitPopulationVotes", lease_command="submit_population_votes",
        payload={})
    assert txn is not None
    assert session_access.current_dispatch_capability(state) is not None
    session_access.clear_command_lease(state)
    assert session_access.current_dispatch_capability(state) is None
    for label in ("submit_population_votes", "campaign", "resolve_election"):
        decision = session_access.present_decision(
            state, session_access.OP_MUTATE, command=label)
        assert decision.allowed is False, label


# ===========================================================================
# R-01 / AC-CLOS-01 — REAL closure gate derived from the owning dispatch
# ===========================================================================
class ClosureProbe:
    """Instruments the single guard (``session_access.authorize_hotseat``), the
    Store's owning dispatch (``GuiSessionStore._dispatch_owning``) and the Store's
    projection refresh (``_on_refresh`` / ``_refresh_*``) so the REAL owning
    dispatch windows are observable. This is the "true gate": the closure is read
    from the ACTUAL call graph, not from two hand-copied constant tables."""

    def __init__(self):
        self.calls = []            # one record per guard decision
        self.dispatched = []       # the ACTUAL owning labels, in dispatch order
        self._projection_depth = 0

    def install(self, monkeypatch):
        orig_auth = session_access.authorize_hotseat

        def auth_spy(st, operation, **kw):
            cap = session_access._nesting_dispatch_capability(st)
            dec = orig_auth(st, operation, **kw)
            self.calls.append({
                "op": operation,
                "command": kw.get("command"),
                "allowed": dec.allowed,
                "exempt": dec.exempt,
                "reason": dec.reason,
                "in_window": cap is not None,
                "owning": cap.command if cap else None,
                "projection": self._projection_depth > 0,
            })
            return dec
        monkeypatch.setattr(session_access, "authorize_hotseat", auth_spy)

        for name in ("_on_refresh", "_refresh_snapshot", "_refresh_population_view",
                     "_refresh_mortality_view", "_refresh_senate_view",
                     "_refresh_revenue_view", "_refresh_forum_view",
                     "_refresh_combat_view", "_refresh_resolution_view"):
            orig = getattr(GuiSessionStore, name)
            monkeypatch.setattr(GuiSessionStore, name, self._projection_wrap(orig))

        orig_disp = GuiSessionStore._dispatch_owning

        def disp_spy(store, txn, command, fn, *a, **k):
            self.dispatched.append(command)
            return orig_disp(store, txn, command, fn, *a, **k)
        monkeypatch.setattr(GuiSessionStore, "_dispatch_owning", disp_spy)

    def _projection_wrap(self, orig):
        @functools.wraps(orig)
        def wrapper(store, *a, **k):
            self._projection_depth += 1
            try:
                return orig(store, *a, **k)
            finally:
                self._projection_depth -= 1
        return wrapper

    # -- derived views -------------------------------------------------------
    def business_calls(self):
        """In-window calls on the owning command's business continuation (excludes
        the Store's masked projection-refresh reads)."""
        return [c for c in self.calls if c["in_window"] and not c["projection"]]

    def projection_calls(self):
        """In-window masked external projection reads (the legitimately refused
        public projection refresh)."""
        return [c for c in self.calls if c["in_window"] and c["projection"]]

    def observed_helpers(self):
        """owning label -> set of command labels actually seen in its window."""
        out = {}
        for c in self.business_calls():
            out.setdefault(c["owning"], set()).add(c["command"])
        return out


def closure_gate(observed, declared):
    """Pure closure gate. ``observed`` = {owning: set(command|None)} derived from a
    REAL run; ``declared`` = {owning: frozenset(helper)}. Returns the violation
    classes that must be empty for a correct closure."""
    violations = {"unlabeled_internal": [], "undeclared_helper": [],
                  "unreachable_declared": []}
    for label, seen in observed.items():
        if None in seen:
            violations["unlabeled_internal"].append(label)
        allowed = {label} | set(declared.get(label, frozenset()))
        for cmd in seen:
            if cmd is not None and cmd not in allowed:
                violations["undeclared_helper"].append((label, cmd))
        for missing in sorted(set(declared.get(label, frozenset())) - (seen - {None})):
            violations["unreachable_declared"].append((label, missing))
    return violations


def _seed_all_population_votes(state, pids):
    """Test-constructed state: every player holds a full ballot, so
    ``phase_ready('population')`` is True while the phase result is still absent —
    this reaches the ``_masked_do_complete_player`` resolve-population-slice owning
    branch with REAL work."""
    sels = _first_selections(state)
    for pid in pids:
        for off, fid in sels.items():
            state.record_population_vote(pid, off, fid)
        state.set_vote_completed(pid, True)


def _ledger_prefinish_ai_population(state, ai_pids):
    """R2-A (R1-V-01 REVERSE lock): make ``phase_ready('population')`` TRUE while
    the scheduled-AI drain STILL has real work, so the ``resolve_population_slice``
    owning window ITSELF exercises ``campaign`` / ``vote``.

    The AI seat is recorded as lawfully finished in the ONE session ledger
    (owner-declared EXPLICIT_FINISH completion) while ``get_vote_completed(ai)``
    stays False and NO AI ballot is recorded: ``_drain_ai_population_turns``
    (invoked INSIDE ``resolve_population_slice``) therefore still drives each AI
    through ``process_festival`` (campaign) and ``process_vote`` (vote) for real."""
    from src.api import session_turn_service as turn_service
    scope = turn_service.mint_scope(state, "population")
    book = turn_service._book(state)
    for pid in ai_pids:
        for substep in ("campaign", "vote"):
            oid = book.oid("population", substep, ("player", pid), scope.scope_id)
            turn_service.complete_actor(
                state, None, scope.scope_id, "ai-pre-finish",
                obligation_id=oid, actor_player_id=pid, phase="population",
                substep=substep, satisfied_kind=turn_service.KIND_EXPLICIT_FINISH,
                owner_declared=True)


def _prepare_forum_1h2ai(monkeypatch):
    """R2-A: a 1H+2AI forum scenario whose AI controllers produce REAL forum
    choices, so the forum owning windows exercise the scheduled-AI sub-boundaries.

    Constructed in-test (committed fixture + test-built state): every AI faction is
    solvent with wealthy eligible members, one BUDGETED tax-farming contract exists
    (place_bid), one RESOLVED war with a live triumph commander exists
    (vote_triumph) and a land-sale quota is open (buy_land). ``random.random`` is
    pinned to 0.0 so the retirement / triumph draws deterministically reach their
    branches (a REPRODUCIBLE FIXTURE — not a guard/assertion relaxation)."""
    from src.core.entities.contract import ContractType, ContractStatus
    from src.core.entities.war import War, WarStatus
    monkeypatch.setattr(random, "random", lambda: 0.0)
    state, pids = _prepared("forum", ai_tail=2)
    for pid in pids[1:]:
        faction = state.get_faction(state.get_player(pid).faction_id)
        faction.treasury = 5000
        for mid in list(faction.member_ids):
            member = state.get_member(mid)
            if member is not None:
                member.wealth = max(getattr(member, "wealth", 0), 5000)
    contract = state.create_contract(ContractType.TAX_FARMING, 0, 90,
                                     state.turn.turn_number)
    contract.status = ContractStatus.BUDGETED
    ai_faction = state.get_faction(state.get_player(pids[1]).faction_id)
    commander = next(state.get_member(mid) for mid in ai_faction.member_ids
                     if state.get_member(mid))
    war = War(id="gr_f_war1", name="Test War", strength=5, threat_level=3,
              rewards={"treasury": 100, "land": 0, "family_prestige": 0},
              naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99])
    war.status = WarStatus.RESOLVED
    war._triumph_commander_id = commander.id
    war._soldier_share = 100
    state.get_war_system()._war_discard.append(war)      # post-victory container
    state.set_pending_land_sale_quota(50)
    return state, pids


def _drive_pop_submit(monkeypatch):
    state, pids = _prepared("population", ai_tail=2)
    store, _ = _masked_store(state, pids[0])

    def run():
        return _submit_1h(store, state)
    return state, store, run


def _drive_pop_complete_next(monkeypatch):
    state, pids = _prepared("population", ai_tail=2)
    store, _ = _masked_store(state, pids[0])
    return state, store, store.doCompletePlayer


def _drive_pop_complete_resolve(monkeypatch):
    """The resolve-population-slice owning branch WITH a real AI drain: only the
    HUMAN's ballots are recorded (all-humans-complete True) and the AI seats are
    ledger-pre-finished so ``phase_ready`` holds while the inside-resolve AI drain
    still runs ``campaign`` + ``vote`` for real (R2-A reverse lock)."""
    state, pids = _prepared("population", ai_tail=2)
    sels = _first_selections(state)
    for off, fid in sels.items():
        state.record_population_vote(pids[0], off, fid)
    state.set_vote_completed(pids[0], True)
    _ledger_prefinish_ai_population(state, pids[1:])
    store, _ = _masked_store(state, pids[0])
    return state, store, store.doCompletePlayer


def _drive_forum_3h(monkeypatch):
    state, pids = _prepared("forum")
    store, _ = _masked_store(state, pids[0])

    def run():
        steps = 0
        while not store.forumResolved and steps < 12:
            steps += 1
            if store.seatLifecycle == SEAT_MASKED_PENDING:
                assert store.requestTakeover()["accepted"] is True
                continue
            if store.forumCurrentStep == "retirement":
                store.doCompleteForumStep()
            else:
                store.doResolveForum()
        return store.forumResolved
    return state, store, run


def _drive_forum_1h2ai(monkeypatch):
    """R2-A: 1H+2AI forum driver exercising the scheduled-AI forum sub-boundaries
    in their owning windows — ``retire_figure`` under ``doCompleteForumStep`` and
    ``recruit_figure`` / ``place_bid`` / ``buy_land`` / ``vote_triumph`` under
    ``doResolveForum`` (the AI forum controllers really run through the guarded
    public boundaries inside the masked owning dispatch)."""
    state, pids = _prepare_forum_1h2ai(monkeypatch)
    store, _ = _masked_store(state, pids[0])

    def run():
        steps = 0
        while not store.forumResolved and steps < 12:
            steps += 1
            if store.seatLifecycle == SEAT_MASKED_PENDING:
                assert store.requestTakeover()["accepted"] is True
                continue
            if store.forumCurrentStep == "retirement":
                store.doCompleteForumStep()
            else:
                store.doResolveForum()
        return store.forumResolved
    return state, store, run


_DRIVERS = (
    ("pop_submit", _drive_pop_submit),
    ("pop_complete_next", _drive_pop_complete_next),
    ("pop_complete_resolve", _drive_pop_complete_resolve),
    ("forum_3h", _drive_forum_3h),
    ("forum_1h2ai", _drive_forum_1h2ai),
)


def _collect_closure(monkeypatch):
    probe = ClosureProbe()
    probe.install(monkeypatch)
    results = {}
    per_driver = {}
    for name, driver in _DRIVERS:
        start = len(probe.dispatched)
        _state, _store, run = driver(monkeypatch)
        results[name] = run()
        per_driver[name] = list(probe.dispatched[start:])
    return probe, results, per_driver


# ===========================================================================
# R-01 gate (real) + mutation falsifiability
# ===========================================================================
def test_clos_01_runtime_closure_gate(monkeypatch):
    probe, results, per_driver = _collect_closure(monkeypatch)
    assert results["pop_submit"]["success"] is True
    assert results["pop_complete_next"]["success"] is True
    assert results["pop_complete_resolve"]["success"] is True
    assert results["forum_3h"] is True
    assert results["forum_1h2ai"] is True

    observed = probe.observed_helpers()
    gate = closure_gate(observed, GuiSessionStore._LEASE_HELPERS)

    # (1) FORWARD: no INTERNAL call to a public guarded boundary without a label
    assert gate["unlabeled_internal"] == [], gate
    # (2) FORWARD: observed internal closure ⊆ declared closure
    assert gate["undeclared_helper"] == [], gate
    # (2b) REVERSE LOCK (R2-A / R1-V-01): every DECLARED helper IS actually
    #      observed in its own owning window — no declared-but-unwitnessed
    #      over-authorization surface survives. "Declared, unobserved and without
    #      a source" ⇒ RED.
    assert gate["unreachable_declared"] == [], gate
    # (3) coverage of ALL effective owning commands and the dynamic conditional
    #     branch — derived from the ACTUAL dispatch, never hand-written
    assert per_driver["pop_submit"] == ["submit_population_votes"], per_driver
    assert set(per_driver["pop_complete_next"]) == {"next_player"}, per_driver
    assert set(per_driver["pop_complete_resolve"]) == {"resolve_population_slice"}, per_driver
    assert set(per_driver["forum_3h"]) == {"doCompleteForumStep", "doResolveForum"}, per_driver
    assert set(per_driver["forum_1h2ai"]) == {"doCompleteForumStep", "doResolveForum"}, per_driver
    # (3b) per-owning bidirectional closure witness (reverse lock, explicit):
    for label, declared in GuiSessionStore._LEASE_HELPERS.items():
        missing = set(declared) - observed.get(label, set())
        assert missing == set(), (label, missing, sorted(observed.get(label, set())))
    for label in set(probe.dispatched):
        helpers = GuiSessionStore._LEASE_HELPERS.get(label)
        assert helpers is not None or observed.get(label, set()) == {label}, label


def test_clos_01_gate_detects_new_unlabeled_internal_boundary(monkeypatch):
    """FALSIFIABILITY (mutation; not shipped): inject a NEW internal call to a
    PUBLIC guarded READ boundary WITHOUT a ``command`` label inside the owning
    dispatch window. The constant-table assertions stay GREEN while the real gate
    turns RED — proving the gate reads the true closure, not just a constant."""
    state, pids = _prepared("population", ai_tail=2)
    store, _ = _masked_store(state, pids[0])
    probe = ClosureProbe()
    probe.install(monkeypatch)

    orig_batch = population_api.batch_vote

    def batch_with_stray_read(st, pid, entries, *a, **k):
        # the injected defect: an internal public guarded read with NO label
        population_api.get_candidates(st)
        return orig_batch(st, pid, entries, *a, **k)
    monkeypatch.setattr(population_api, "batch_vote", batch_with_stray_read)

    fb = _submit_1h(store, state)
    assert fb["success"] is True, fb

    # the OLD constant-table gate is BLIND to this mutation ...
    assert set(GuiSessionStore._LEASE_HELPERS) == set(EXPECTED_HELPERS)
    assert GuiSessionStore._LEASE_HELPERS == EXPECTED_HELPERS
    # ... while the REAL gate turns RED.
    gate = closure_gate(probe.observed_helpers(), GuiSessionStore._LEASE_HELPERS)
    assert gate["unlabeled_internal"] == ["submit_population_votes"], gate


def test_clos_01_gate_detects_undeclared_helper(monkeypatch):
    """FALSIFIABILITY: inject a NEW internal call to a REAL public guarded boundary
    (``session_api.advance_population_phase``) whose command label is NOT in the
    declared closure of the owning command -> reported as an undeclared helper."""
    state, pids = _prepared("population", ai_tail=2)
    store, _ = _masked_store(state, pids[0])
    probe = ClosureProbe()
    probe.install(monkeypatch)

    orig_batch = population_api.batch_vote

    def batch_with_undeclared(st, pid, entries, *a, **k):
        session_api.advance_population_phase(
            st, pid, caller_context=session_access.current_caller_context(st))
        return orig_batch(st, pid, entries, *a, **k)
    monkeypatch.setattr(population_api, "batch_vote", batch_with_undeclared)

    fb = _submit_1h(store, state)
    assert fb["success"] is True, fb
    gate = closure_gate(probe.observed_helpers(), GuiSessionStore._LEASE_HELPERS)
    assert ("submit_population_votes", "advance_population_phase") \
        in gate["undeclared_helper"], gate


def test_clos_01_gate_detects_unreachable_declared_helper(monkeypatch):
    """FALSIFIABILITY: a declared helper NOT part of the real closure is an
    over-authorization surface and MUST be reported. Falsified by doctoring the
    declared set with a spurious extra label -> flagged as unreachable."""
    probe, results, per_driver = _collect_closure(monkeypatch)
    observed = probe.observed_helpers()

    doctored = {label: frozenset(set(helpers) | {"spurious_unreachable_helper"})
                for label, helpers in GuiSessionStore._LEASE_HELPERS.items()}
    gate = closure_gate(observed, doctored)
    assert ("submit_population_votes", "spurious_unreachable_helper") \
        in gate["unreachable_declared"], gate

    # the TRUE declared set has NO unreachable helper for the fully-witnessed
    # submit closure (an exactness witness, not a subset-only pass):
    real = closure_gate(observed, GuiSessionStore._LEASE_HELPERS)
    submit_unreachable = [c for (lbl, c) in real["unreachable_declared"]
                          if lbl == "submit_population_votes"]
    assert submit_unreachable == [], submit_unreachable


# ===========================================================================
# R-02 (2) / AC-D2-3H-03 — INV-SEAT-SYNC at every seat/DTO publication point
# ===========================================================================
#: Every seat/DTO publication signal the Store emits (the publication paths).
_PUBLICATION_SIGNALS = (
    "snapshotChanged", "populationViewChanged", "mortalityViewChanged",
    "senateViewChanged", "revenueViewChanged", "forumViewChanged",
    "combatViewChanged", "resolutionViewChanged", "phaseChanged",
    "phaseStepsChanged", "currentPlayerChanged", "seatLifecycleChanged",
    "handoffMaskChanged", "handoffPendingFactionChanged", "handoffFinished",
)

#: The DTO/model publication signals (the ones ``_neutralize_public_projection``
#: emits directly).
_DTO_SIGNALS = frozenset({
    "snapshotChanged", "populationViewChanged", "mortalityViewChanged",
    "senateViewChanged", "revenueViewChanged", "forumViewChanged",
    "combatViewChanged", "resolutionViewChanged", "phaseChanged",
    "phaseStepsChanged", "currentPlayerChanged",
})


def _install_publication_moment_probe(store, state, monkeypatch):
    """R2-B (R1-V-02): observe the ``ACTIVE => principal == Core current HUMAN``
    invariant AT THE PUBLICATION MOMENT.

    The R1 hooks checked AFTER a wrapped method returned — a snapshot, not the
    moment a DTO/seat signal was actually published. Here every seat/DTO Qt signal
    is SUBSCRIBED to, so the invariant is evaluated synchronously INSIDE each
    ``emit()`` (the publication/sync point), and every emission is classified by
    its publication PATH (which signal) and STAGE (which forum substep, or whether
    it came from ``_neutralize_public_projection`` — which itself emits the DTO
    signals directly and is therefore a first-class publication path). A
    per-path/per-stage coverage map is retained (never a bare ``n > 0``)."""
    violations = []
    counts = {}        # (signal, stage) -> n
    neutralize = {"depth": 0, "n": 0}

    def check(signal):
        rec = session_access._record(state)
        lifecycle = rec.lifecycle if rec is not None else None
        stage = "neutralize" if neutralize["depth"] > 0 else store.forumCurrentStep
        counts[(signal, stage)] = counts.get((signal, stage), 0) + 1
        if lifecycle != session_access.LIFECYCLE_ACTIVE:
            return
        cur = state.get_current_player()
        pid = getattr(cur, "player_id", None)
        ptype = getattr(getattr(cur, "player_type", None), "value", None)
        if pid != rec.principal_player_id or ptype != "human":
            violations.append((signal, stage, rec.principal_player_id, pid, ptype))

    # (1) SUBSCRIBE to every publication signal -> emit-time observation.
    subscriptions = []
    for name in _PUBLICATION_SIGNALS:
        signal = getattr(store, name)

        def slot(*_a, _name=name):
            check(_name)
        signal.connect(slot)
        subscriptions.append(slot)

    # (2) ``_neutralize_public_projection`` is itself a publication path (it emits
    #     the DTO signals directly) -> mark its emissions + count its calls.
    orig_neutralize = GuiSessionStore._neutralize_public_projection

    @functools.wraps(orig_neutralize)
    def neutralize_spy(self, *a, **k):
        neutralize["depth"] += 1
        neutralize["n"] += 1
        try:
            return orig_neutralize(self, *a, **k)
        finally:
            neutralize["depth"] -= 1
    monkeypatch.setattr(GuiSessionStore, "_neutralize_public_projection",
                        neutralize_spy)

    return {"violations": violations, "counts": counts, "neutralize": neutralize,
            "subscriptions": subscriptions}


def _install_publication_hooks(state, monkeypatch, check):
    """Wrap every seat/DTO publication point (Store ``_emit_seat`` /
    ``_apply_staged`` / each ``_refresh_*``), every service authority-commit point
    and the Core cursor writer so the ``ACTIVE => principal == current HUMAN``
    invariant is checked at each of them (not just at a loop-head snapshot)."""
    def wrap_store(name):
        orig = getattr(GuiSessionStore, name)

        @functools.wraps(orig)
        def w(self, *a, **k):
            r = orig(self, *a, **k)
            check(name)
            return r
        monkeypatch.setattr(GuiSessionStore, name, w)

    for name in ("_emit_seat", "_apply_staged",
                 "_refresh_snapshot", "_refresh_population_view",
                 "_refresh_mortality_view", "_refresh_senate_view",
                 "_refresh_revenue_view", "_refresh_forum_view",
                 "_refresh_combat_view", "_refresh_resolution_view"):
        wrap_store(name)

    def wrap_sa(name):
        orig = getattr(session_access, name)

        @functools.wraps(orig)
        def w(*a, **k):
            r = orig(*a, **k)
            check(name)
            return r
        monkeypatch.setattr(session_access, name, w)

    for name in ("commit_hotseat_principal", "issue_fresh_handle",
                 "advance_hotseat_principal", "end_masked_execution"):
        wrap_sa(name)

    orig_scp = state.set_current_player

    def scp_spy(pid):
        r = orig_scp(pid)
        check("set_current_player")
        return r
    monkeypatch.setattr(state, "set_current_player", scp_spy)


def test_mask_3h_forum_03_seat_sync_invariant_at_every_publication(monkeypatch):
    """AC-D2-3H-03 / R2-B (R1-V-02): across the full 3H retirement -> market flow,
    assert ``lifecycle == ACTIVE  =>  principal == Core current HUMAN`` AT EVERY
    DTO/seat PUBLICATION MOMENT. Unlike a post-return snapshot, the invariant is
    evaluated synchronously INSIDE each Qt signal ``emit()`` (the publication/sync
    point) for EVERY publication path — including ``_neutralize_public_projection``,
    which directly emits the DTO signals. A per-path / per-stage coverage map is
    kept (never a bare ``n > 0``). A bare cursor move under an ACTIVE seat (the D2
    defect) would surface here as a moment-of-publication violation."""
    state, pids = _prepared("forum")
    violations = []
    checks = {"n": 0}

    def check(tag):
        rec = session_access._record(state)
        if rec is None or rec.lifecycle != session_access.LIFECYCLE_ACTIVE:
            return
        checks["n"] += 1
        cur = state.get_current_player()
        pid = getattr(cur, "player_id", None)
        ptype = getattr(getattr(cur, "player_type", None), "value", None)
        if pid != rec.principal_player_id or ptype != "human":
            violations.append((tag, rec.principal_player_id, pid, ptype))

    _install_publication_hooks(state, monkeypatch, check)
    store, witness = _masked_store(state, pids[0])
    moment = _install_publication_moment_probe(store, state, monkeypatch)

    steps = 0
    while not store.forumResolved and steps < 12:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        if store.forumCurrentStep == "retirement":
            store.doCompleteForumStep()
        else:
            store.doResolveForum()

    assert store.forumResolved is True
    assert checks["n"] > 0, "the publication hooks must have fired"
    assert violations == [], violations

    # ---- R2-B: publication-MOMENT observation --------------------------------
    # nothing was ever published exposing an ACTIVE seat whose principal differs
    # from the Core current HUMAN (checked inside ``emit()``, not after return).
    assert moment["violations"] == [], moment["violations"]
    # ``_neutralize_public_projection`` (which emits the DTO signals itself) is
    # exercised as a REAL publication path.
    assert moment["neutralize"]["n"] > 0, moment
    counts = moment["counts"]
    # per-PUBLICATION-PATH coverage: every DTO signal was published at least once.
    for sig in sorted(_DTO_SIGNALS):
        assert any(k[0] == sig for k in counts), (sig, sorted(counts))
    # the neutralize path emitted the DTO signals DIRECTLY (moment-level witness).
    assert any(k[0] == "snapshotChanged" and k[1] == "neutralize" for k in counts), \
        sorted(counts)
    # per-STAGE coverage (NOT n>0): publications observed in BOTH substeps.
    stages = {k[1] for k in counts}
    assert "retirement" in stages and "market" in stages, sorted(stages)


# ===========================================================================
# NEGATIVE CONTROLS — DIRECTLY RUNNABLE (R3 / G5-R2 sec 4.1 = R2-E-01)
# ---------------------------------------------------------------------------
# In R2 the A/B mutations were DA-temporary: run, observed RED, reverted. They
# were therefore NOT independently reproducible by a read-only verifier (no
# runnable artifact could be selected). These two NEGATIVE CONTROLS ship the SAME
# falsifications as FIRST-CLASS, directly selectable tests: running them injects
# the violation INSIDE the real flow and asserts that the main closure gate /
# the publication-moment probe DETECT it. Both are monkeypatch-scoped, so every
# injection is auto-reverted (no cross-test pollution). NEGATIVE-CONTROL SEMANTICS:
# each test PASSES iff its detector correctly catches the injected defect.
# Run them alone with:  -k negcontrol
# ===========================================================================
def test_negcontrol_A_closure_gate_detects_injected_internal_boundary(monkeypatch):
    """NEGATIVE CONTROL A (closure gate) — directly runnable, `-k negcontrol`.

    Inject, INSIDE the real masked owning dispatch, an INTERNAL PUBLIC guarded
    boundary call that carries NO ``command`` label (``population_api.get_candidates``
    — the public read boundary the masked internal continuation must never reach),
    and route the helper boundary ``batch_vote`` through its un-labelled inner
    implementation so its declared label is never observed (a real label-loss
    defect). The MAIN closure gate must turn RED on the injected over-authorization
    surface:
      * ``unlabeled_internal`` — the unlabelled boundary call is caught, and
      * ``unreachable_declared`` — the declared helper ``batch_vote`` is now
        declared-but-unobserved (the R2-A over-authorization signature).
    ``monkeypatch`` auto-reverts the injection (asserted at the end)."""
    inner_batch = getattr(population_api.batch_vote, "__wrapped__", None)
    assert inner_batch is not None, \
        "the guarded batch_vote boundary must expose its wrapped implementation"
    original_boundary = population_api.batch_vote

    def injected_batch(st, pid, entries, *a, **k):
        # (1) injected defect: an internal PUBLIC boundary with NO `command` label
        population_api.get_candidates(st)
        # (2) injected defect: the labelled helper path is bypassed, so the
        #     declared label ``batch_vote`` is never observed (unreachable_declared)
        return inner_batch(st, pid, entries, *a, **k)

    monkeypatch.setattr(population_api, "batch_vote", injected_batch)

    probe, _results, _per_driver = _collect_closure(monkeypatch)
    gate = closure_gate(probe.observed_helpers(), GuiSessionStore._LEASE_HELPERS)

    # the injected unlabelled internal boundary IS detected ...
    assert "submit_population_votes" in gate["unlabeled_internal"], gate
    # ... and the injected label loss leaves a REAL declared-but-unobserved helper
    assert ("submit_population_votes", "batch_vote") in gate["unreachable_declared"], gate
    # the main gate (as asserted by test_clos_01_runtime_closure_gate) is RED:
    assert (gate["unlabeled_internal"] != []
            or gate["unreachable_declared"] != []), gate

    # NEGATIVE-CONTROL hygiene: the injection is monkeypatch-scoped and reverts.
    monkeypatch.undo()
    assert population_api.batch_vote is original_boundary


def test_negcontrol_B_publication_moment_probe_detects_transient_mismatch(monkeypatch):
    """NEGATIVE CONTROL B (publication-moment probe) — directly runnable, `-k negcontrol`.

    Inject, AT the ``_neutralize_public_projection`` publication point, a
    TRANSIENT seat-authority mismatch — an ACTIVE seat whose principal is a bogus
    player — that is restored IMMEDIATELY after ``snapshotChanged.emit()`` (the
    real flow is unchanged once the original neutralize runs). The publication
    MOMENT probe (subscribed to every seat/DTO signal, evaluated synchronously
    INSIDE ``emit()``) MUST detect it, while the OLD after-return hooks — which
    only sample AFTER the wrapped method returns, when the record is restored —
    MUST see NOTHING. This fixes the discriminating power of "publication moment
    vs after-return". ``monkeypatch`` auto-reverts the injection."""
    state, pids = _prepared("forum")
    violations = []
    checks = {"n": 0}

    def check(tag):
        rec = session_access._record(state)
        if rec is None or rec.lifecycle != session_access.LIFECYCLE_ACTIVE:
            return
        checks["n"] += 1
        cur = state.get_current_player()
        pid = getattr(cur, "player_id", None)
        ptype = getattr(getattr(cur, "player_type", None), "value", None)
        if pid != rec.principal_player_id or ptype != "human":
            violations.append((tag, rec.principal_player_id, pid, ptype))

    _install_publication_hooks(state, monkeypatch, check)
    store, witness = _masked_store(state, pids[0])
    moment = _install_publication_moment_probe(store, state, monkeypatch)

    # ---- the injected defect (monkeypatch-scoped; auto-reverted) -------------
    _orig_neut = GuiSessionStore._neutralize_public_projection

    @functools.wraps(_orig_neut)
    def _neut_transient(self, *a, **k):
        rec = session_access._record(self._state)
        if rec is None:
            return _orig_neut(self, *a, **k)
        saved = (rec.lifecycle, rec.principal_player_id)
        rec.lifecycle = session_access.LIFECYCLE_ACTIVE
        rec.principal_player_id = "player-bogus"
        try:
            # published ONLY for the emission instant, then restored
            self.snapshotChanged.emit()
        finally:
            rec.lifecycle, rec.principal_player_id = saved
        return _orig_neut(self, *a, **k)
    monkeypatch.setattr(GuiSessionStore, "_neutralize_public_projection",
                        _neut_transient)

    steps = 0
    while not store.forumResolved and steps < 12:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        if store.forumCurrentStep == "retirement":
            store.doCompleteForumStep()
        else:
            store.doResolveForum()

    assert store.forumResolved is True
    assert checks["n"] > 0, "the publication hooks must have fired"
    # the OLD after-return hook is BLIND to the transient (restored) mismatch ...
    assert violations == [], violations
    # ... while the publication-MOMENT probe DETECTS it (stage + bogus principal).
    assert moment["violations"] != [], moment
    assert all(v[2] == "player-bogus" for v in moment["violations"]), \
        moment["violations"]
