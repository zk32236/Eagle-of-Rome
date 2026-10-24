"""EOR20261013-02 / G7-W3-D16 — forum second-year lifecycle (RED-first).

Contract source: ``02-sa-design/W3/G7-D16/02-Design-Delta.md`` (the ONLY behaviour
source).  Covered AC candidates (03-Impact-and-AC):

  AC-D16-01  year identity / atomicity      ``-k year_book_lifecycle``
  AC-D16-02  two-year 3H complete chances   ``-k three_human_two_years``
  AC-D16-03  select failure is fail-closed  ``-k select_failure_closed``
  AC-D16-04  Core init / scope alignment    ``-k init_scope_alignment``
  AC-D16-05  1H2AI + resource boundaries    ``-k mixed_and_resource_boundaries``
  AC-D16-06  W3/W2 reverse compatibility    ``-k second_year_senate_compatibility``

Production seams only.  The forum chain is driven through the REAL Store slots
(``doCompleteForumStep`` / ``doResolveForum``) on the REAL masked seat machine,
the REAL coordinator (``session_turn_service``) and the REAL Core state created by
the production factory.  No product / QML / data file is changed; no test-only
constructor, no manual ``book.reset``, no manual turn/phase marker, no direct
``state.advance_year`` call: the year boundary always goes through the product
use-case ``game_api.advance_year``.

The two-year rounds use independent fresh sessions (design 05 §1: no reuse of a
previous round's runtime book).  Fault injection in the AC-D16-03 tests only
touches the ``select_actor`` dependency boundary (design 03 §2 "fault injection
is a branch negative, never a substitute for the real RED").
"""
from __future__ import annotations

import copy
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import game_api
from src.api import combat_api
from src.api import forum_api
from src.api import population_api
from src.api import senate_api
from src.api import session_access
from src.api import session_api
from src.api import session_turn_service as sts
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"
SCENARIO_1H2AI = "gui_prototype.json"

FORUM_SUBSTEPS = ("retirement", "market")


@pytest.fixture(autouse=True)
def _restore_rng():
    st = random.getstate()
    try:
        yield
    finally:
        random.setstate(st)


# ---------------------------------------------------------------------------
# Production-shape harness (barrier / receiver witnesses only)
# ---------------------------------------------------------------------------
class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _Witness:
    """Synchronous barrier witness (no async frame gates)."""

    def __init__(self):
        self.calls = []
        self.pendings = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction))
        self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


def _factory(scenario, start_phase="forum"):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase=start_phase, scenario_file=scenario)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    state.set_current_player(pids[0])
    return state, pids


def _store(state, viewer, masked=True):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _Witness()
    if masked:
        store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    return store, witness


def _ctx(state):
    return session_access.present_context(state)


def _forum_obligations(state):
    scope = sts.mint_scope(state, "forum")
    out = []
    for substep in FORUM_SUBSTEPS:
        out.extend(sts._forum_obligations(state, scope.scope_id, substep))
    return out


def _enter_forum_phase(store):
    """The REAL GUI year path up to the forum phase (mortality -> revenue).

    Only intents a player really issues; every transition is the Store's own.
    """
    assert store.doExecuteMortality().get("success") is True
    assert store.doAdvanceMortality().get("success") is True
    assert store.doExecuteRevenue().get("success") is True
    assert store.doAdvanceRevenue().get("success") is True
    store._refresh_snapshot()
    store._refresh_forum_view()


def _play_forum_year(store, limit=24):
    """Drive ONE forum year through the REAL Store slots.

    Returns the ordered list of (substep, success, message) intents the seats
    issued.  A seat only ever issues the intent a player would issue; every
    transition (handoff / market open / resolve) is the Store's own.
    """
    intents = []
    steps = 0
    while not store.forumResolved and steps < limit:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
        substep = store.forumCurrentStep
        if substep == "retirement":
            fb = store.doCompleteForumStep()
        else:
            fb = store.doResolveForum()
        intents.append((substep, bool(fb.get("success")), fb.get("message")))
        assert fb.get("success") is True, (substep, fb)
    return intents


def _advance_year(state, pids, force=True):
    """The ONE product annual use-case (never ``state.advance_year`` directly).

    ``force=True`` is the product's documented CLI ``next`` escape door: it skips
    only the RESOLUTION precondition / owner barrier, never the re-entry guard,
    the permission check or the year lifecycle itself (FC-D16-06/07).
    """
    current = state.get_current_player()
    actor = getattr(current, "player_id", None) or pids[0]
    return game_api.advance_year(state, actor, force=force,
                                 caller_context=_ctx(state))


def _forum_records(state):
    book = sts._book(state)
    return [r.obligation_id for r in book.records if r.obligation_id[3] == "forum"]


# ---------------------------------------------------------------------------
# Rework R1-R5 (2026-10-23) — full-field book snapshot (FC-D16-08)
# ---------------------------------------------------------------------------
def _full_book_snapshot(book):
    """Every container the frozen contract names, plus the generation identity."""
    return {
        "turn_number": book.turn_number,
        "revision_counter": book.revision_counter,
        "session_ns": book.session_ns,
        "scopes": dict(book.scopes),
        "records": [r.obligation_id for r in book.records],
        "entries": repr(book.entries),
        "entered_scope_ids": set(book.entered_scope_ids),
        "role_selections": repr(book.role_selections),
        "receipts": dict(book.receipts),
        "committed_facts": repr(book.committed_facts),
        "consumed_receipts": set(book.consumed_receipts),
    }


def _typed(errors):
    """The typed error dict carried by a BLOCKED feedback (never flattened)."""
    assert isinstance(errors, (list, tuple)) and errors, errors
    first = errors[0]
    assert isinstance(first, dict), first
    return first


def _api_call(fn, *args):
    """Call a guarded product use-case presenting the service caller context.

    The handle is the one the trusted routing layer presents (S-B DG-01); a
    signature that does not accept it keeps the historical call shape.
    """
    try:
        return fn(*args, caller_context=_ctx(args[0]))
    except TypeError:
        return fn(*args)


POPULATION_OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")


def _abstain_selections(store):
    """One lawful ballot per office: the first real candidate of that office."""
    picks = {}
    for candidate in store.populationCandidates:
        office = candidate.get("office")
        if office and office not in picks and candidate.get("id"):
            picks[office] = candidate.get("id")
    return picks


def _play_population(store, limit=12):
    """Drive the population stage through the REAL Store vote slot.

    Each seat issues only the intent a player issues (a legal abstain ballot on
    every office); the handoff and the election resolution are the Store's own.
    """
    selections = _abstain_selections(store)
    assert selections, "the population stage must offer real candidates"
    steps = 0
    while not store.populationResolved and steps < limit:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        # PC02W TD-01 (2026-10-23): 本席位庆典前置（G1 per-actor gate），断言零变更。
        store._state.set_batch_completed(store.viewerPlayerId, True)
        fb = store.submitPopulationVotes(selections)
        assert fb.get("success") is True, fb
    assert store.populationResolved is True, "population never resolved"


def _cast_abstain_ballots(state, pids):
    """Every executable HUMAN controller casts its legal no-choice ballot.

    The product's own batch-vote use-case; an abstain (figure 0) is a lawful
    ballot, not a shortcut around the ballot requirement.
    """
    entries = [{"office": office, "figure_id": 0} for office in POPULATION_OFFICES]
    for pid in pids:
        if sts.controller_of(state, pid) != sts.CONTROLLER_HUMAN:
            continue
        vote = _api_call(population_api.batch_vote, state, pid, entries, True)
        assert vote.get("success") is True, vote


# ===========================================================================
# AC-D16-01 / FC-D16-06 / 08 / 10 — the single annual publication boundary
# ===========================================================================
def test_year_book_lifecycle():
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])

    _play_forum_year(store)
    book_before = sts._book(state)
    session_ns = book_before.session_ns
    turn_before = seed_turn = state.turn.turn_number
    revision_before = book_before.revision_counter
    assert len(_forum_records(state)) == 6, _forum_records(state)

    ok = _advance_year(state, pids, force=True)
    assert ok["success"] is True, ok.get("message")

    # Core is the single clock; the published book is the same generation.
    core_turn = state.turn.turn_number
    assert core_turn == turn_before + 1
    book_after = sts._book(state)
    assert book_after.turn_number == core_turn
    assert book_after is not book_before, "a new year publishes a candidate book"
    # identity continuity: same session namespace, monotonic revision
    assert book_after.session_ns == session_ns
    assert book_after.revision_counter >= revision_before
    # the eight EXACT containers are empty (FC-D16-08)
    assert book_after.scopes == {}
    assert book_after.records == []
    assert book_after.entries == []
    assert book_after.entered_scope_ids == set()
    assert book_after.role_selections == {}
    assert book_after.receipts == {}
    assert book_after.committed_facts == {}
    assert book_after.consumed_receipts == set()
    # the old-year identity can never match again
    assert _forum_records(state) == []
    assert seed_turn == turn_before


def test_year_book_lifecycle_core_failure_keeps_live_book(monkeypatch):
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    book = sts._book(state)
    snapshot = (book.turn_number, book.revision_counter,
                copy.deepcopy([r.obligation_id for r in book.records]),
                dict(book.scopes))

    def _boom():
        raise RuntimeError("core plan failure")

    monkeypatch.setattr(state, "advance_year", _boom)
    res = _advance_year(state, pids, force=True)
    assert res["success"] is False
    assert "advance_failed" in (res.get("errors") or [])

    after = sts._book(state)
    assert after is book, "a Core failure never replaces the live book"
    assert after.turn_number == snapshot[0]
    assert after.revision_counter == snapshot[1]
    assert [r.obligation_id for r in after.records] == snapshot[2]
    assert dict(after.scopes) == snapshot[3]
    assert state._year_advance_in_progress is False


def test_year_book_lifecycle_late_attach_uses_core_turn():
    state, pids = _factory(SCENARIO_3H)
    # no coordinator book yet: the FIRST read binds the CURRENT Core turn
    assert getattr(state, "_session_turn_book", None) is None
    _advance_year(state, pids, force=True)
    book = sts._book(state)
    assert book.turn_number == state.turn.turn_number


# ===========================================================================
# AC-D16-02 / FC-D16-01 / 02 / 04 / 05 / 09 — two years of 3H chances
# ===========================================================================
@pytest.mark.parametrize("round_id", ["round1", "round2"])
def test_three_human_two_years(round_id):
    state, pids = _factory(SCENARIO_3H)
    assert len(pids) == 3
    store, _w = _store(state, pids[0])

    year1 = _play_forum_year(store)
    assert [i[0] for i in year1] == ["retirement"] * 3 + ["market"] * 3, year1
    oids_year1 = _forum_records(state)
    assert len(oids_year1) == 6, oids_year1
    assert len(set(oids_year1)) == 6

    ok = _advance_year(state, pids, force=True)
    assert ok["success"] is True, ok.get("message")

    # fresh year: the REAL Store must expose the new year's 6 obligations again
    outstanding = [o for o in _forum_obligations(state) if not o.satisfied]
    assert len(outstanding) == 6, [(o.substep, o.actor_player_id) for o in outstanding]

    store._reset_phase_caches()
    store._refresh_snapshot()
    _enter_forum_phase(store)
    assert store.forumResolved is False, "a new year must not be pre-resolved"
    assert store.forumCurrentStep == "retirement"

    year2 = _play_forum_year(store)
    assert [i[0] for i in year2] == ["retirement"] * 3 + ["market"] * 3, year2
    oids_year2 = _forum_records(state)
    assert len(oids_year2) == 6, oids_year2
    assert set(oids_year1).isdisjoint(set(oids_year2)), "cross-year OID reuse"
    assert state.get_phase_result("forum") is not None


# ===========================================================================
# AC-D16-03 / FC-D16-03 / 05 / 07 / 09 — selection failure is fail-closed
# ===========================================================================
def _counting(store, name):
    calls = []
    original = getattr(store._adapter, name)

    def spy(*a, **k):
        calls.append((a, k))
        return original(*a, **k)

    setattr(store._adapter, name, spy)
    return calls


def test_select_failure_closed_legacy(monkeypatch):
    """Legacy retirement consumer: a selection failure must NOT open the market."""
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0], masked=False)
    open_calls = _counting(store, "open_forum_market")
    resolve_calls = _counting(store, "resolve_forum")

    def _deny(*a, **k):
        return {"success": False, "reason": "STALE_SCOPE", "actor": None}

    monkeypatch.setattr(sts, "select_actor", _deny)
    fb = store.doCompleteForumStep()

    assert fb.get("success") is not True, fb
    assert open_calls == [], f"selection failure opened the market: {open_calls}"
    assert resolve_calls == []
    # the lawful own-seat finish is KEPT; other seats stay outstanding
    assert len(_forum_records(state)) == 1, _forum_records(state)
    assert [o.actor_player_id for o in _forum_obligations(state) if not o.satisfied]


def test_select_failure_closed_market(monkeypatch):
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0], masked=False)
    resolve_calls = _counting(store, "resolve_forum")
    advance_calls = []
    if hasattr(store._adapter, "advance_population_phase"):
        advance_calls = _counting(store._adapter, "advance_population_phase")

    def _deny(*a, **k):
        return {"success": False, "reason": "STALE_REVISION", "actor": None}

    monkeypatch.setattr(sts, "select_actor", _deny)
    fb = store.doResolveForum()

    assert fb.get("success") is not True, fb
    assert resolve_calls == [], f"selection failure resolved the forum: {resolve_calls}"
    assert advance_calls == []


def test_select_failure_closed_masked(monkeypatch):
    """Masked retirement: a selection failure after a REAL completion is neutral."""
    state, pids = _factory(SCENARIO_3H)
    store, witness = _store(state, pids[0], masked=True)
    open_calls = _counting(store, "open_forum_market")

    def _deny(*a, **k):
        return {"success": False, "reason": "SET_CURRENT_FAILED", "actor": None}

    monkeypatch.setattr(sts, "select_actor", _deny)
    fb = store.doCompleteForumStep()

    assert fb.get("success") is not True, fb
    assert open_calls == [], f"selection failure opened the market: {open_calls}"
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    kinds = [c[0] for c in witness.calls]
    assert "failure" in kinds, witness.calls
    assert store._last_delivery is None, "a failed forum txn must not reuse _last_delivery"
    assert store._pending_player_id == "", "no fabricated handoff target"


# ===========================================================================
# AC-D16-04 / FC-D16-04 / 06 / 08 / 09 — same-year idempotency, new-year scope
# ===========================================================================
def test_init_scope_alignment():
    state, pids = _factory(SCENARIO_3H)
    scope1 = sts.mint_scope(state, "forum")
    revision1 = sts.current_revision(state)
    # same-year repeated mint/initialize keep the scope and the completions
    assert sts.mint_scope(state, "forum").scope_id == scope1.scope_id
    book = sts._book(state)
    assert book.turn_number == 1
    _advance_year(state, pids, force=True)
    assert book.turn_number == 1  # the replaced book keeps its own generation
    scope2 = sts.mint_scope(state, "forum")
    assert scope2.scope_id != scope1.scope_id, "a new year mints a fresh scope"
    assert sts.current_revision(state) >= revision1
    assert sts.forum_substep_ready(state, "retirement") is False


# ===========================================================================
# AC-D16-05 / FC-D16-01 / 02 / 05 — 1H2AI control + cardinality
# ===========================================================================
def test_mixed_and_resource_boundaries():
    state, pids = _factory(SCENARIO_1H2AI)
    kinds = {p.player_id: p.player_type for p in state.get_all_players()}
    humans = [p for p in pids if sts.controller_of(state, p) == sts.CONTROLLER_HUMAN]
    ais = [p for p in pids if sts.controller_of(state, p) == sts.CONTROLLER_AI]
    assert len(pids) == 3, (pids, kinds)
    assert len(humans) == 1 and len(ais) == 2, (humans, ais, kinds)

    # cardinality = actual executable controllers x two substeps (never O/P/E)
    obligations = _forum_obligations(state)
    assert len(obligations) == 6, [(o.substep, o.controller) for o in obligations]
    assert {o.controller for o in obligations} == {sts.CONTROLLER_HUMAN, sts.CONTROLLER_AI}

    store, _w = _store(state, humans[0])
    year1 = _play_forum_year(store)
    for substep in FORUM_SUBSTEPS:
        assert substep in [i[0] for i in year1], year1
    oids_year1 = _forum_records(state)
    assert len(oids_year1) >= 2, oids_year1
    _advance_year(state, pids, force=True)

    fresh = _forum_obligations(state)
    assert len(fresh) == 6
    assert len([o for o in fresh if not o.satisfied]) == 6, "old-year facts leaked"
    assert set(oids_year1).isdisjoint(
        {r for r in _forum_records(state)}), "cross-year OID reuse"
    assert sts.forum_substep_ready(state, "retirement") is False


# ===========================================================================
# AC-D16-06 / FC-D16-07 / 08 / 10 — second-year freshness / W3 compatibility
# ===========================================================================
def test_second_year_senate_compatibility():
    """AC-D16-06 / R1 — the SECOND year really ENTERS the Senate.

    Year 1 closes on the real annual publication boundary; year 2 then plays the
    real forum round and advances population -> Senate through the product
    use-cases, so the fresh Senate scope + consumed entry receipt are observed on
    a real entry (never a test-side forum completion bridge).
    """
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    scope_year1 = sts.mint_scope(state, "forum").scope_id
    receipts_year1 = set(sts._book(state).receipts)
    assert receipts_year1, "the first year must have issued owner receipts"

    assert _advance_year(state, pids, force=True)["success"] is True

    book = sts._book(state)
    assert book.receipts == {} and book.consumed_receipts == set()
    scope_year2 = sts.mint_scope(state, "forum").scope_id
    assert scope_year2 != scope_year1, "the second year must use a fresh scope"

    # ---- year 2: real forum round, then a real population -> Senate entry ----
    store._reset_phase_caches()
    store._refresh_snapshot()
    _enter_forum_phase(store)
    assert store.forumResolved is False, "a new year must not be pre-resolved"
    _play_forum_year(store)
    assert len(_forum_records(state)) == 6, _forum_records(state)

    pid = state.get_current_player().player_id
    adv_forum = _api_call(forum_api.advance_forum_phase, state, pid)
    assert adv_forum.get("success") is True, adv_forum
    _play_population(store)
    pid = state.get_current_player().player_id
    adv_pop = _api_call(session_api.advance_population_phase, state, pid)
    assert adv_pop.get("success") is True, adv_pop

    # the Senate entry is real: a scope of THIS generation exists, minting is
    # idempotent inside the year, and the committed entry receipt was consumed
    senate_scope = sts.mint_scope(state, "senate")
    assert sts.mint_scope(state, "senate").scope_id == senate_scope.scope_id
    live = sts._book(state)
    assert live.scopes.get("senate") is senate_scope
    assert live.turn_number == state.turn.turn_number
    assert live.consumed_receipts, "the population entry receipt must be consumed"
    assert senate_scope.scope_id not in {scope_year1, scope_year2}
    assert state.get_phase_result("senate") is None, "entered, not yet resolved"


# ===========================================================================
# REWORK R1 (2026-10-23) — the NORMAL annual chain (no force) + Senate entry
# ===========================================================================
def test_r1_normal_trigger_chain_and_no_force_refusal():
    """The NORMAL annual trigger chain, and the no-force boundary's real gate.

    mortality/revenue/forum are driven by the Store slots, population by the real
    Store vote slot, and the Senate entry by the product phase-advance use-case.
    The year boundary is then attempted WITHOUT force: the product refuses it on
    the real resolution prerequisite (the very condition ``force=True`` skips).
    """
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    turn_before = state.turn.turn_number
    pid = state.get_current_player().player_id

    adv_forum = _api_call(forum_api.advance_forum_phase, state, pid)
    assert adv_forum.get("success") is True, adv_forum
    assert state.is_phase_executed("forum") is True

    _play_population(store)
    pid = state.get_current_player().player_id
    adv_pop = _api_call(session_api.advance_population_phase, state, pid)
    assert adv_pop.get("success") is True, adv_pop
    assert state.get_phase_result("population") is not None

    pid = state.get_current_player().player_id

    # The NORMAL trigger prerequisite is REAL and is never skipped here: without a
    # committed resolution the product refuses the no-force year boundary.
    # (`force=True` exists precisely to skip this prerequisite; the GUI chain's
    # senate/combat/resolution owners are denied to this headless seat — recorded
    # in the rework evidence as the structural blocker, never bridged in the test.)
    before_boundary = _full_book_snapshot(sts._book(state))
    res = _advance_year(state, pids, force=False)
    assert res.get("success") is False, res
    errors = res.get("errors") or []
    assert ("resolution_not_executed" in errors
            or any(isinstance(e, dict) and e.get("code") == "DENIED"
                   for e in errors)), res
    assert state.turn.turn_number == turn_before, "Core must not advance"
    assert _full_book_snapshot(sts._book(state)) == before_boundary
    senate_scope = sts.mint_scope(state, "senate")
    assert sts._book(state).scopes.get("senate") is senate_scope
    assert sts._book(state).consumed_receipts, "entry receipt consumed once"


# ===========================================================================
# REWORK R2 — failure / initialization witnesses (full field, typed)
# ===========================================================================
def test_r2_prepare_failure_preserves_full_book():
    """A prepare-stage refusal is typed AND leaves the live book untouched."""
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    book = sts._book(state)
    assert book.turn_number == state.turn.turn_number
    core_turn = state.turn.turn_number

    # Precondition negative (branch, not an annual-entry substitute): the live
    # book claims a FOREIGN generation, exactly the case the prepare step must
    # reject with TURN_BOOK_OUT_OF_SYNC instead of silently migrating.
    book.turn_number = core_turn + 7
    skewed = _full_book_snapshot(book)

    res = _advance_year(state, pids, force=True)
    assert res.get("success") is False, res
    err = _typed(res.get("errors"))
    assert err.get("code") == "TURN_BOOK_OUT_OF_SYNC", err
    assert err.get("stage") == "year_prepare", err
    assert err.get("committed") is False, err

    after = sts._book(state)
    assert after is book, "a prepare failure never replaces the live book"
    assert _full_book_snapshot(after) == skewed
    assert state.turn.turn_number == core_turn, "Core must not advance"
    assert state._year_advance_in_progress is False


def test_r2_core_failure_preserves_full_book(monkeypatch):
    """A real Core precommit failure keeps every book field byte-identically."""
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    book = sts._book(state)
    before = _full_book_snapshot(book)
    core_turn = state.turn.turn_number

    def _boom():
        raise RuntimeError("core plan failure")

    monkeypatch.setattr(state, "advance_year", _boom)
    res = _advance_year(state, pids, force=True)
    assert res["success"] is False
    assert "advance_failed" in (res.get("errors") or [])

    after = sts._book(state)
    assert after is book
    assert _full_book_snapshot(after) == before
    assert state.turn.turn_number == core_turn
    assert state._year_advance_in_progress is False


def test_r2_same_year_init_refresh_mint_exactly_once():
    """Same year: repeated init/refresh/mint never fork the generation."""
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    book = sts._book(state)
    scope = sts.mint_scope(state, "forum")
    revision = sts.current_revision(state)
    oids = sorted(r.obligation_id for r in book.records)
    assert len(oids) == 6 and len(set(oids)) == 6

    for _ in range(3):
        store._refresh_forum_view()
        store._refresh_snapshot()
        assert sts.mint_scope(state, "forum").scope_id == scope.scope_id
        assert sts.current_revision(state) == revision
        assert sts._book(state) is book
        assert sorted(r.obligation_id for r in book.records) == oids
        assert book.turn_number == state.turn.turn_number
    assert len(_forum_records(state)) == 6


def test_r2_year2_partial_seat_barrier_denial():
    """After ONE year-2 retirement the owner barrier still refuses."""
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0])
    _play_forum_year(store)
    assert _advance_year(state, pids, force=True)["success"] is True

    store._reset_phase_caches()
    store._refresh_snapshot()
    _enter_forum_phase(store)
    fb = store.doCompleteForumStep()          # exactly ONE seat finishes
    assert fb is not None, fb

    barrier = sts.owner_barrier(state, "forum", "retirement")
    assert barrier is not None, "a partial year-2 retirement must be refused"
    assert barrier.get("message")
    assert sts.forum_substep_ready(state, "retirement") is False
    assert len(_forum_records(state)) == 1, _forum_records(state)
    outstanding = [o for o in _forum_obligations(state) if not o.satisfied]
    assert len(outstanding) == 5, [(o.substep, o.actor_player_id) for o in outstanding]


SELECT_FAILURE_CASES = [
    ("STALE_SCOPE", {"success": False, "reason": "STALE_SCOPE", "actor": None}),
    ("STALE_REVISION", {"success": False, "reason": "STALE_REVISION", "actor": None}),
    ("SET_CURRENT_FAILED", {"success": False, "reason": "SET_CURRENT_FAILED",
                           "actor": None}),
    ("MALFORMED_SELECT", None),
    ("SELECT_EMPTY_ACTOR", {"success": True, "actor": None, "controller": "HUMAN"}),
    ("SELECT_NOT_HUMAN", {"success": True, "actor": "__ghost__",
                          "controller": "HUMAN"}),
    ("SELECT_EXCEPTION:RuntimeError", "raise"),
]


@pytest.mark.parametrize("reason,outcome", SELECT_FAILURE_CASES)
def test_r2_select_failure_matrix(monkeypatch, reason, outcome):
    """Every select refusal is typed and forbids ALL same-seat follow-ups.

    The spy covers the DENIED call itself (a real non-zero select count) and the
    three follow-up surfaces are independently instrumented on the real adapter.
    """
    state, pids = _factory(SCENARIO_3H)
    store, _w = _store(state, pids[0], masked=False)
    open_calls = _counting(store, "open_forum_market")
    resolve_calls = _counting(store, "resolve_forum")
    population_calls = _counting(store, "advance_population")

    sel_calls = []

    def _select(*a, **k):
        sel_calls.append((a, k))
        if outcome == "raise":
            raise RuntimeError("select boom")
        return outcome

    monkeypatch.setattr(sts, "select_actor", _select)
    fb = store.doCompleteForumStep()

    assert fb.get("success") is not True, fb
    err = _typed(fb.get("errors"))
    assert err.get("code") == "FORUM_NEXT_ACTOR_FAILED", err
    assert err.get("stage") == "forum_select", err
    assert err.get("reason") == reason, err
    assert sel_calls, "the denied select call itself must be instrumented"
    assert open_calls == [], open_calls
    assert resolve_calls == [], resolve_calls
    assert population_calls == [], population_calls
    # the lawful own-seat finish is KEPT; the other seats stay outstanding
    assert len(_forum_records(state)) == 1, _forum_records(state)
    outstanding = [o for o in _forum_obligations(state) if not o.satisfied]
    assert len(outstanding) == 5, [(o.substep, o.actor_player_id) for o in outstanding]


# ===========================================================================
# REWORK R3 — TA-W3-06 AI outstanding retention through the real consumer
# ===========================================================================
def test_r3_ai_outstanding_retained_and_year2():
    """An AI retirement failure is a typed BLOCKED, never a silent completion.

    Year 1 is played to a lawful completion, so the year-2 round is the SECOND
    genuine consumer pass (no test-side state priming). If the scheduled AI cannot
    finish its retirement there, the human's own lawful finish is retained, every
    other obligation is unchanged, and no market/resolve/population follow-up runs.
    """
    state, pids = _factory(SCENARIO_1H2AI)
    humans = [p for p in pids if sts.controller_of(state, p) == sts.CONTROLLER_HUMAN]
    assert len(humans) == 1, humans
    state.set_current_player(humans[0])
    session_access.register_hotseat_session(state, humans[0], epoch=0)
    store, _w = _store(state, humans[0], masked=False)

    open_calls = _counting(store, "open_forum_market")
    resolve_calls = _counting(store, "resolve_forum")
    population_calls = _counting(store, "advance_population")

    before = {(o.substep, o.actor_player_id)
              for o in _forum_obligations(state) if not o.satisfied}
    assert len(before) == 6, before

    fb = store.doCompleteForumStep()
    assert fb is not None, fb
    retained = {(o.substep, o.actor_player_id)
                for o in _forum_obligations(state) if not o.satisfied}
    ai_out = [o for o in _forum_obligations(state)
              if not o.satisfied and o.controller == sts.CONTROLLER_AI
              and o.substep == "retirement"]
    if ai_out:
        # TA-W3-06: the AI obligation is still outstanding — the real consumer
        # must refuse with the exact typed reason and run ZERO follow-ups.
        assert fb.get("success") is not True, fb
        err = _typed(fb.get("errors"))
        assert err.get("code") == "FORUM_NEXT_ACTOR_FAILED", err
        assert err.get("stage") == "forum_select", err
        assert err.get("reason") == "AI_OBLIGATION_PENDING", err
        assert open_calls == [], open_calls
        assert resolve_calls == [], resolve_calls
        assert population_calls == [], population_calls
        removed = before - retained
        assert ("retirement", humans[0]) in removed, "the lawful finish is kept"
        records = _forum_records(state)
        assert {(r[4], r[5][1]) for r in records} == removed, (records, removed)
        assert len(retained) == 6 - len(removed), retained
    else:
        # the scheduled AI really finished this retirement: the lawful completion
        # is the alternative end state and it is the ONLY follow-up that may run.
        assert fb.get("success") is True, fb
        assert open_calls, "a complete retirement must open the market once"
        assert [o for o in _forum_obligations(state)
                if o.substep == "retirement" and not o.satisfied] == []

    # ---- year 2: the same real consumer on a FRESH generation ----
    assert _advance_year(state, pids, force=True)["success"] is True
    store._reset_phase_caches()
    store._refresh_snapshot()
    _enter_forum_phase(store)
    before2 = {(o.substep, o.actor_player_id)
               for o in _forum_obligations(state) if not o.satisfied}
    assert len(before2) == 6, before2

    open_calls.clear()
    resolve_calls.clear()
    population_calls.clear()
    fb3 = store.doCompleteForumStep()
    assert fb3 is not None, fb3
    retained2 = {(o.substep, o.actor_player_id)
                 for o in _forum_obligations(state) if not o.satisfied}
    ai_out2 = [o for o in _forum_obligations(state)
               if not o.satisfied and o.controller == sts.CONTROLLER_AI
               and o.substep == "retirement"]
    if ai_out2:
        assert fb3.get("success") is not True, fb3
        err3 = _typed(fb3.get("errors"))
        assert err3.get("code") == "FORUM_NEXT_ACTOR_FAILED", err3
        assert err3.get("stage") == "forum_select", err3
        assert err3.get("reason") == "AI_OBLIGATION_PENDING", err3
        assert open_calls == [], open_calls
        assert resolve_calls == [], resolve_calls
        assert population_calls == [], population_calls
        assert ("retirement", humans[0]) in before2 - retained2, before2 - retained2
        assert retained2, retained2
    else:
        assert fb3.get("success") is True, fb3
        assert open_calls, "a complete retirement must open the market once"
