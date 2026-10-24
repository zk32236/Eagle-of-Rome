"""W3 / G7 — S2: the AI tribune veto must wait for ONE real human confirmation.

WHY THIS MODULE EXISTS
----------------------
``EOR20261013-02 / G7-W3-AI-Veto-Confirm`` (Slice B). The frozen G3-delta says:
on a REGISTERED senate scope with a NON-EMPTY passed-only candidate set and an
ACTUAL AI tribune, the automatic continuation must NOT run the AI veto decider
before a real human gesture. ``session_turn_service._continue_scheduled_phase``
used to call ``_senate_ai_executor`` -> ``apply_auto_tribune_vetoes`` directly, so
the veto obligation was drained before any click (T16).

The contract pinned here (AC-S2-01..07):

  * before the click: zero AI veto-decider calls, the veto OID is NOT satisfied,
    nothing finalized, the existing ``senateVetoSubmitButton`` is usable, and the
    human presenter has NO veto choice;
  * one click: exactly ONE traversal of the passed candidates through the real AI
    decider, the real decision recorded, exactly one owner receipt;
  * repeat / stale / non-presenter: typed DENIED, ZERO extra AI calls;
  * a real HUMAN tribune keeps the original path (AI executor = 0);
  * a legitimate EMPTY step (no proposal / no passed candidate / lawful NONE)
    still skips automatically — never a permanent WAITING;
  * a new year cannot revive an old gate (coexists with the Slice A fix);
  * the QML button state comes from the SAME DTO the backend derives (real Qt
    object, never an invented boolean).

Everything is driven through REAL production seams: the production GUI session
factory, the registered Hot-seat entry (``doAdvancePopulation``), the real Store
slots the QML buttons call, the real masked owning flow with the real barrier
witness, and the real deciders. Test-side wrappers only COUNT calls (they
delegate unchanged); no product byte is patched.

SETUP NOTE (declared, not hidden): ``gui_prototype.json`` only offers optimates
tribune candidates, so that 1H2AI scenario can never elect an AI tribune. To
exercise the frozen "ACTUAL AI tribune" predicate the ELECTED tribune figure is
moved to the AI faction before the senate work (``_retarget_tribune``); the office
holder, the resolver path and the PlayerType mapping stay the real ones. The senate
ballots are likewise established through the same Core primitive the AI executor
uses, because the ballot step is a PRECONDITION of the veto gate, not its subject.

TEST-R1 (G5 RETURN — coverage only, product untouched):
  * S2-03 denies a NON-presenter at the REAL protected entry while the veto
    obligation is still OUTSTANDING (whole-dispatch counters), instead of
    reading another viewer's projection after the gate was consumed;
  * S2-05b/05c put the lawful NONE BEFORE the vote command, so the PRODUCTION
    continuation itself has to reach the terminal facts (a ``settlement_pending``
    projection is never accepted as a skip);
  * S2-06 drives a REAL Year-2 AI-veto gate (new scope, new turn/OID epoch, new
    tribune) before replaying the Year-1 seat handle and the Year-1 projection.
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.tests._evidence_root import evidence_root
from src.api import senate_api, session_access, session_turn_service as sts
from src.ui.gui.session_store import SEAT_ACTIVE, SEAT_MASKED_PENDING


def _load_probe():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_g7_second_turn_probe.py")
    spec = importlib.util.spec_from_file_location("_g7_veto_probe_lib", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

SCENARIO_1H2AI = probe.SCENARIO_1H2AI


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    """W1b：证据写根由 helper 派生（默认 tmp 派生根；归档区在模块内不可达）。"""
    base = os.environ.get("G7_S2_EVIDENCE_DIR") or tmp_path_factory.mktemp("w3-ai-veto")
    return evidence_root(base, namespace="w3-ai-veto")


def _dump(root, name, obj):
    """Persist one machine-readable observation (test evidence only)."""
    root.ensure_dir()
    path = root.path(name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True,
                  default=str)
    return path


# ---------------------------------------------------------------------------
# Ballot preferences (real candidate ids; only the CHOICE differs)
# ---------------------------------------------------------------------------
def _prefer_own_consul(store, viewer, state=None):
    """The viewer faction's own consul (HUMAN consulate, HUMAN tribune)."""
    faction = state.get_player(viewer).faction_id if state is not None else ""
    picks = probe._abstain_selections(store)
    for candidate in store.populationCandidates:
        if (candidate.get("office") == "consul"
                and candidate.get("faction_id") == faction
                and candidate.get("id")):
            picks["consul"] = candidate.get("id")
            break
    for candidate in store.populationCandidates:
        if (candidate.get("office") == "tribune"
                and candidate.get("faction_id") == faction
                and candidate.get("id")):
            picks["tribune"] = candidate.get("id")
            break
    return picks


# ---------------------------------------------------------------------------
# Instrumentation (counting wrappers only — never a changed decision)
# ---------------------------------------------------------------------------
class _DeciderSpy:
    """Counts REAL AI veto-decider traversals; the decision is unchanged."""

    def __init__(self):
        self.calls = []

    def install(self, monkeypatch):
        real_cls = senate_api.AutoTribuneVetoDecider
        spy = self

        class _Counting(real_cls):  # type: ignore[misc, valid-type]
            def decide_veto(self, issue, tribune_id, state):  # noqa: D102
                decision = super().decide_veto(issue, tribune_id, state)
                spy.calls.append({"tribune_id": tribune_id,
                                  "vetoed": bool(decision)})
                return decision

        monkeypatch.setattr(senate_api, "AutoTribuneVetoDecider", _Counting)
        return spy


class _ProducerSpy:
    """Counts the AI proposal producer and the auto-veto producer calls."""

    def __init__(self):
        self.auto_proposals = 0
        self.auto_vetoes = 0
        # The UNWRAPPED production symbols (a boundary-level negative control must
        # not increment the counting wrapper it is proving stays at zero).
        self.real_proposals = None
        self.real_vetoes = None


def _install_producers(monkeypatch, spy):
    real_proposals = senate_api.auto_submit_proposals
    real_vetoes = senate_api.apply_auto_tribune_vetoes

    def _proposals(*a, **k):
        spy.auto_proposals += 1
        return real_proposals(*a, **k)

    def _vetoes(*a, **k):
        spy.auto_vetoes += 1
        return real_vetoes(*a, **k)

    # The trusted adapter routes on ``api_func.__name__``.
    _proposals.__name__ = real_proposals.__name__
    _proposals.__doc__ = real_proposals.__doc__
    _vetoes.__name__ = real_vetoes.__name__
    _vetoes.__doc__ = real_vetoes.__doc__

    monkeypatch.setattr(senate_api, "auto_submit_proposals", _proposals)
    monkeypatch.setattr(senate_api, "apply_auto_tribune_vetoes", _vetoes)
    spy.real_proposals = real_proposals
    spy.real_vetoes = real_vetoes
    return spy


# ---------------------------------------------------------------------------
# Ledger / DTO facts
# ---------------------------------------------------------------------------
def _book_scope(state):
    book = sts._book(state)
    return book, book.scopes.get("senate")


def _veto_oid(state):
    book, scope = _book_scope(state)
    assert scope is not None
    return book.oid("senate", "veto", ("singleton", scope.scope_id),
                    scope.scope_id)


def _veto_records(state):
    oid = _veto_oid(state)
    book, _ = _book_scope(state)
    return [r for r in book.records if r.obligation_id == oid]


def _all_veto_records(state):
    """Every veto record of the whole book (all scope generations)."""
    book, _ = _book_scope(state)
    return [r for r in book.records
            if len(r.obligation_id) > 4 and r.obligation_id[4] == "veto"]


def _veto_receipts(state):
    book, _ = _book_scope(state)
    return [r for r in book.receipts.values()
            if r.get("command") == "senate_veto_decision"]


def _view(state, viewer):
    """The SAME guarded read the Store performs (registered seat context)."""
    try:
        resp = senate_api.get_senate_view(
            state, viewer, caller_context=session_access.present_context(state))
    except TypeError:  # pragma: no cover - legacy signature
        resp = senate_api.get_senate_view(state, viewer)
    return resp.get("data") if isinstance(resp.get("data"), dict) else resp


def _latch(state, tag="veto"):
    book, scope = _book_scope(state)
    return dict(book.role_selections.get((scope.scope_id, tag)) or {})


def _settle(store):
    for _ in range(8):
        if store.seatLifecycle == SEAT_ACTIVE:
            return True
        takeover = store.requestTakeover()
        if not takeover.get("accepted"):
            return False
    return store.seatLifecycle == SEAT_ACTIVE


def _counters(carrier):
    """The WHOLE-dispatch side-effect counters (never a per-branch guess)."""
    state = carrier.state
    return {
        "decider_calls": len(carrier.deciders.calls),
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "auto_proposal_producer": carrier.producers.auto_proposals,
        "veto_records": len(_veto_records(state)),
        "veto_receipts": len(_veto_receipts(state)),
        "revision": sts.current_revision(state),
    }


def _gate_snapshot(carrier, viewer=None):
    """The outstanding-gate facts of the REAL projection (no cached copy)."""
    state = carrier.state
    book, scope = _book_scope(state)
    oid = _veto_oid(state)
    view = _view(state, carrier.viewer if viewer is None else viewer)
    return {
        "step": view.get("current_step"),
        "can_confirm_ai_veto": view.get("can_confirm_ai_veto"),
        "can_veto": view.get("can_veto"),
        "veto_control_mode": view.get("veto_control_mode"),
        "veto_candidate_ids": list(view.get("veto_candidate_ids") or []),
        "scope_id": scope.scope_id if scope is not None else None,
        "veto_oid": list(oid),
        "veto_oid_satisfied": bool(
            book.satisfied(oid, scope.scope_id, sts.current_revision(state))
            if scope is not None else True),
        "records": len(_veto_records(state)),
        "receipts": len(_veto_receipts(state)),
    }


def _foreign_store(state, viewer):
    """A REAL second Store instance bound to a NON-presenter player.

    The frozen session model is ONE registered seat per session
    (``session_access._SeatRecord``: a single principal + handle per state), so a
    second *principal* is structurally impossible in this carrier. A foreign
    player seat is therefore the strongest realisable non-presenter: it uses the
    production Store entry, not a test-side reimplementation.
    """
    try:
        store, witness = probe._store(state, viewer)
    except Exception as exc:  # pragma: no cover - recorded, never hidden
        return None, None, "ERR:%s: %s" % (type(exc).__name__, exc)
    return store, witness, ""


def _drop_tribune_office(store, state, pids=None):
    """SETUP: no eligible tribune -> resolver-backed lawful NONE."""
    dropped = []
    for figure in state.get_living_members():
        if getattr(figure, "office", None) == "tribune":
            dropped.append(figure.id)
            figure.office = None
    return {"dropped": dropped}


def _retarget_tribune(state, to_faction="populares"):
    """SETUP: re-point the ELECTED tribune to an ACTUAL AI faction.

    See the module docstring: the shipped 1H2AI scenario offers only optimates
    tribune candidates, so an AI tribune can never be elected there. The real
    office holder is kept; only its faction ownership (and therefore the real
    PlayerType mapping) changes.
    """
    tribune = None
    for figure in state.get_living_members():
        if getattr(figure, "office", None) == "tribune":
            tribune = figure
            break
    if tribune is None:
        return None
    old = state.get_faction(tribune.faction_id)
    new = state.get_faction(to_faction)
    if old is not None and tribune.id in old.member_ids:
        old.member_ids.remove(tribune.id)
    tribune.faction_id = to_faction
    if new is not None and tribune.id not in new.member_ids:
        new.member_ids.append(tribune.id)
    return tribune.id


class _Carrier:
    def __init__(self, state, store, pids, viewer, deciders, producers,
                 witness, checks):
        self.state = state
        self.store = store
        self.pids = pids
        self.viewer = viewer
        self.deciders = deciders
        self.producers = producers
        self.witness = witness
        self.checks = checks

    @property
    def view(self):
        return _view(self.state, self.viewer)

    def click_veto(self, payload=None):
        return self.store.doSubmitSenateVetoes(
            [] if payload is None else payload)


def _run_chain(carrier, *, retarget=True, publish=True, ai_votes=True,
               human_yes=True, preference=_prefer_own_consul, confirm=False,
               before_vote=None):
    """Drive ONE real year of the registered chain to (through) the veto gate.

    mortality -> revenue -> forum -> population -> senate entry -> proposal
    publication -> ballots -> the REAL vote command whose continuation used to
    auto-drain the AI veto.

    Re-usable on the carrier of an ALREADY advanced year (S2-06): every step is
    the SAME production Store slot / registered entry, so year 2 is a real new
    scope generation, never a fabricated one. ``before_vote`` is a test SETUP
    hook that mutates the fixture (never the product) between the ballots and
    the vote command — used to build the lawful-NONE precondition.
    """
    state, store, pids, viewer = (carrier.state, carrier.store, carrier.pids,
                                  carrier.viewer)
    deciders, producers, witness = (carrier.deciders, carrier.producers,
                                    carrier.witness)
    checks = {"chain": probe._entry_chain(store, state)}
    assert _settle(store), checks
    store._refresh_population_view()
    picks = preference(store, viewer, state)
    # PC02W TD-01 (2026-10-23): 逐席位庆典前置（G1 per-actor gate），断言零变更。
    for _pid in pids:
        state.set_batch_completed(_pid, True)
    checks["population"] = probe._play_population(store, picks)
    store._refresh_population_view()
    store._refresh_snapshot()
    assert _settle(store), checks
    checks["advance"] = store.doAdvancePopulation()
    assert _settle(store), checks
    store._refresh_senate_view()
    checks["picks"] = picks
    checks["step_after_entry"] = store.senateCurrentStep

    if retarget:
        checks["tribune_id"] = _retarget_tribune(state)
        store._refresh_senate_view()
    checks["veto_mode_before_publish"] = _view(state, viewer).get(
        "veto_control_mode")

    options = list(store.senateProposalOptions or [])
    checks["option_count"] = len(options)
    if publish:
        checks["submit"] = store.doSubmitSenateProposals(options)
    else:
        checks["submit"] = store.doSubmitSenateProposals([])
    assert _settle(store), checks
    store._refresh_senate_view()
    ids = [p.get("id") for p in state.get_senate_proposals()]
    checks["proposal_ids"] = ids

    if ai_votes and ids:
        for pid in ids:
            for other in pids[1:]:
                state.record_senate_vote(other, pid, True)
    elif not ai_votes and ids:
        for pid in ids:
            for other in pids[1:]:
                state.record_senate_vote(other, pid, False)
    store._refresh_senate_view()
    store._refresh_snapshot()
    assert _settle(store), checks
    if before_vote is not None:
        checks["before_vote"] = before_vote(store, state, pids)
        store._refresh_senate_view()
    checks["vote"] = (store.doSubmitSenateVotes(ids if human_yes else [])
                      if ids else None)
    assert _settle(store), checks
    store._refresh_senate_view()

    carrier.checks = checks
    if confirm:
        checks["confirm"] = carrier.click_veto()
        assert _settle(store), checks
        store._refresh_senate_view()
    return carrier


def _gate_carrier(monkeypatch, *, hold_rng=False, **kwargs):
    """Fresh 1H2AI carrier + spies, then ONE real year up to the veto gate."""
    rng_state = random.getstate()
    if not hold_rng:
        random.seed(42)
    try:
        state, pids = probe._factory(SCENARIO_1H2AI)
        viewer = pids[0]
        store, witness = probe._store(state, viewer)
        deciders = _DeciderSpy().install(monkeypatch)
        producers = _install_producers(monkeypatch, _ProducerSpy())
        carrier = _Carrier(state, store, pids, viewer, deciders, producers,
                           witness, {})
        return _run_chain(carrier, **kwargs)
    finally:
        if not hold_rng:
            random.setstate(rng_state)


# ===========================================================================
# S2-01 — before the human gesture: zero AI veto decision, nothing finalized
# ===========================================================================
def test_s2_01_ai_veto_waits_for_human_confirmation(monkeypatch, evidence):
    carrier = _gate_carrier(monkeypatch)
    view = carrier.view
    facts = {
        "checks": {k: v for k, v in carrier.checks.items()
                   if k not in ("chain",)},
        "step": view.get("current_step"),
        "can_confirm_ai_veto": view.get("can_confirm_ai_veto"),
        "can_veto": view.get("can_veto"),
        "can_auto_veto": view.get("can_auto_veto"),
        "veto_control_mode": view.get("veto_control_mode"),
        "registered_veto_controller": view.get("registered_veto_controller"),
        "registered_veto_owner_player_id": view.get(
            "registered_veto_owner_player_id"),
        "veto_candidate_ids": view.get("veto_candidate_ids"),
        "decider_calls": carrier.deciders.calls,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records": len(_veto_records(carrier.state)),
        "senate_result": carrier.state.get_phase_result("senate") is not None,
        "store_can_submit_veto": carrier.store.canSubmitSenateVeto,
        "latch": _latch(carrier.state),
    }
    _dump(evidence, "s2-01.json", facts)

    assert view.get("current_step") == "tribune_veto", facts
    assert carrier.checks["proposal_ids"], facts
    # AC-S2-01 — the decider did NOT run before the human gesture.
    assert carrier.deciders.calls == [], facts
    assert carrier.producers.auto_vetoes == 0, facts
    assert _veto_records(carrier.state) == [], facts
    assert carrier.state.get_phase_result("senate") is None, facts
    # The existing QML control is usable, from the SAME DTO the backend derives.
    assert view.get("can_confirm_ai_veto") is True, facts
    assert carrier.store.canSubmitSenateVeto is True, facts
    # ... but the human has NO decision right: the AI owner keeps it.
    assert view.get("can_veto") is False, facts
    assert _latch(carrier.state)["controller"] == "AI", facts
    assert _latch(carrier.state)["actor_player_id"] == carrier.pids[1], facts


# ===========================================================================
# S2-02 — one click: exactly one AI traversal, one real decision, one receipt
# ===========================================================================
def test_s2_02_single_click_runs_the_ai_decision_once(monkeypatch, evidence):
    carrier = _gate_carrier(monkeypatch)
    candidates = list(carrier.view.get("veto_candidate_ids") or [])
    assert candidates, carrier.view
    before_records = _veto_records(carrier.state)

    confirmed = carrier.click_veto([])
    view = carrier.view
    result = carrier.state.get_phase_result("senate") or {}
    facts = {
        "confirm": {k: confirmed.get(k) for k in ("success", "message")},
        "decider_calls": carrier.deciders.calls,
        "candidate_ids": candidates,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records_before": len(before_records),
        "veto_records_after": len(_veto_records(carrier.state)),
        "veto_receipts": len(_veto_receipts(carrier.state)),
        "step": view.get("current_step"),
        "canonical": senate_api.canonical_finalization(carrier.state),
        "result_keys": sorted(result.keys()),
        "result_data_keys": sorted((result.get("data") or {}).keys()),
        "completion_facts": (result.get("data") or {}).get("completion_facts"),
        "store_can_advance": carrier.store.canAdvanceSenate,
    }
    _dump(evidence, "s2-02.json", facts)

    assert confirmed.get("success") is True, facts
    # Exactly ONE traversal over the passed-only candidate set.
    assert len(carrier.deciders.calls) == len(candidates), facts
    assert [c["tribune_id"] for c in carrier.deciders.calls] == \
        [carrier.deciders.calls[0]["tribune_id"]] * len(candidates), facts
    assert carrier.producers.auto_vetoes == 1, facts
    # The AI decision is really recorded, once, and the owner receipt is once.
    records = _veto_records(carrier.state)
    assert len(records) == 1, facts
    assert records[0].command_id == "senate_veto_decision", facts
    assert len(_veto_receipts(carrier.state)) == 1, facts
    # The existing completion / readiness / finalization converged: the FOUR
    # canonical completion facts of the SAME version are all true.
    assert result.get("success") is True, facts
    canonical = senate_api.canonical_finalization(carrier.state)
    assert canonical.get("status") == "VALID", facts
    assert all((canonical.get("facts") or {}).values()), facts
    assert len(canonical.get("facts") or {}) == 4, facts


# ===========================================================================
# S2-03 — non-presenter on an OUTSTANDING gate / stale handle: typed DENIED
# ===========================================================================
def test_s2_03_foreign_and_stale_confirmations_are_denied(monkeypatch, evidence):
    """The protected confirmation entry, exercised while the gate is LIVE.

    SA R1: the previous revision only read ``other_view`` AFTER the gate had been
    consumed, so no foreign MUTATION entry was ever denied. Here the foreign
    attempt happens while the veto obligation is still outstanding, and the WHOLE
    dispatch is counted (deciders / both producers / records / receipts /
    revision), not just one branch.
    """
    carrier = _gate_carrier(monkeypatch)
    state, store = carrier.state, carrier.store
    stale_view = dict(store._senate_view)           # a REAL earlier projection
    assert stale_view.get("can_confirm_ai_veto") is True, stale_view

    before_gate = _gate_snapshot(carrier)
    assert before_gate["step"] == "tribune_veto", before_gate
    assert before_gate["can_confirm_ai_veto"] is True, before_gate
    assert before_gate["veto_oid_satisfied"] is False, before_gate
    assert before_gate["veto_candidate_ids"], before_gate
    candidates = list(before_gate["veto_candidate_ids"])

    # ---- (A) the capability PRODUCER is strictly viewer-bound --------------
    # ``_registered_role_capabilities`` IS the production producer of the DTO
    # bits (a pure read); the foreign seat must not be granted confirmation.
    foreign_pid = carrier.pids[2]
    foreign_caps = senate_api._registered_role_capabilities(
        state, foreign_pid, "tribune_veto")

    # ---- (B) the REAL protected entry, called by a NON-presenter Store -----
    # SETUP (declared): the seat authority is moved to another player of the
    # session by the PRODUCTION handoff primitive ``advance_hotseat_principal``
    # (the same service call the masked seat handoff uses). The frozen session
    # model has ONE principal per session, so this is the only way a second
    # player can hold a VALID projection — which is exactly what makes the
    # confirmation-entry denial (not a denied read) observable.
    foreign_store, foreign_witness, foreign_error = _foreign_store(state,
                                                                   foreign_pid)
    foreign_ctx = (session_access.advance_hotseat_principal(state, foreign_pid)
                   if foreign_store is not None else None)
    foreign_active = (_settle(foreign_store)
                      if foreign_store is not None else False)
    if foreign_store is not None and foreign_active:
        # the taken-over seat's OWN production projection (never a test dict)
        foreign_store._refresh_senate_view()
    before_foreign = _counters(carrier)
    foreign = ({"success": None, "message": foreign_error,
                "errors": [{"code": "NO_STORE"}]}
               if foreign_store is None else foreign_store.doSubmitSenateVetoes([]))
    after_foreign = _counters(carrier)
    foreign_lifecycle = (foreign_store.seatLifecycle
                         if foreign_store is not None else None)
    foreign_view = (dict(getattr(foreign_store, "_senate_view", {}) or {})
                    if foreign_store is not None else {})

    # the gate must survive the foreign attempt
    session_access.advance_hotseat_principal(state, carrier.viewer)
    assert _settle(store), "the presenter seat could not be recovered"
    store._refresh_senate_view()
    after_gate = _gate_snapshot(carrier)

    # ---- (C) the presenter's own single lawful gesture ---------------------
    first = carrier.click_veto([])
    assert _settle(store), first
    store._refresh_senate_view()
    after_first = _counters(carrier)
    calls_after_first = list(carrier.deciders.calls)

    # ---- (D) repeat + the now-consumed stale handle -----------------------
    second = carrier.click_veto([])
    store._senate_view = stale_view
    third = carrier.click_veto([])
    after_stale = _counters(carrier)

    facts = {
        "gate_before": before_gate,
        "foreign_capability": {k: foreign_caps.get(k) for k in (
            "registered_seat", "registered_schedule_valid",
            "registered_veto_controller", "registered_veto_owner_player_id",
            "registered_can_confirm_ai_veto", "registered_can_veto")},
        "foreign_store_error": foreign_error,
        "foreign_context_player": (foreign_ctx.principal_player_id
                                   if foreign_ctx is not None else None),
        "foreign_lifecycle": foreign_lifecycle,
        "foreign_active": foreign_active,
        "foreign_view": {k: foreign_view.get(k) for k in (
            "success", "current_step", "can_confirm_ai_veto", "can_veto",
            "veto_control_mode", "registered_can_confirm_ai_veto",
            "viewer_player_id", "denied", "masked")},
        "foreign_response": {"success": foreign.get("success"),
                             "message": foreign.get("message"),
                             "errors": foreign.get("errors")},
        "counters": {"before_foreign": before_foreign,
                     "after_foreign": after_foreign,
                     "after_first": after_first,
                     "after_stale": after_stale},
        "gate_after_foreign": after_gate,
        "first": {k: first.get(k) for k in ("success", "message")},
        "second": {"success": second.get("success"),
                   "errors": second.get("errors"),
                   "message": second.get("message")},
        "third": {"success": third.get("success"),
                  "errors": third.get("errors"),
                  "message": third.get("message")},
        "decider_calls": carrier.deciders.calls,
        "veto_records": len(_veto_records(carrier.state)),
        "auto_veto_producer": carrier.producers.auto_vetoes,
    }
    _dump(evidence, "s2-03.json", facts)

    # (A) the confirmation capability does not exist for a non-presenter.
    assert foreign_caps.get("registered_can_confirm_ai_veto") is False, facts
    assert foreign_caps.get("registered_can_veto") is False, facts

    # (B) the protected ENTRY denies the foreign seat, typed, with ZERO effect.
    assert foreign.get("success") is False, facts
    codes = [e.get("code") for e in (foreign.get("errors") or [])
             if isinstance(e, dict)]
    assert "DENIED" in codes, facts
    assert after_foreign == before_foreign, facts
    # ... and the gate is STILL outstanding for the real presenter.
    assert after_gate["step"] == "tribune_veto", facts
    assert after_gate["can_confirm_ai_veto"] is True, facts
    assert after_gate["veto_oid_satisfied"] is False, facts
    assert after_gate["records"] == before_gate["records"], facts

    # (C) the lawful gesture still releases it exactly once.
    assert first.get("success") is True, facts
    assert len(carrier.deciders.calls) == len(candidates), facts
    assert after_first["veto_records"] == before_gate["records"] + 1, facts
    assert after_first["veto_receipts"] == before_gate["receipts"] + 1, facts

    # (D) repeat / stale-handle replay: typed DENIED, ZERO extra activity.
    for label, response in (("repeat", second), ("stale", third)):
        assert response.get("success") is False, (label, facts)
        codes = [e.get("code") for e in (response.get("errors") or [])
                 if isinstance(e, dict)]
        assert "DENIED" in codes, (label, facts)
    assert carrier.deciders.calls == calls_after_first, facts
    assert after_stale["veto_records"] == after_first["veto_records"], facts
    assert after_stale["veto_receipts"] == after_first["veto_receipts"], facts
    assert after_stale["auto_veto_producer"] == 1, facts


# ===========================================================================
# S2-04 — a real HUMAN tribune keeps the original path (AI executor = 0)
# ===========================================================================
def test_s2_04_human_tribune_path_is_unchanged(monkeypatch, evidence):
    carrier = _gate_carrier(monkeypatch, retarget=False)
    view = carrier.view
    assert view.get("current_step") == "tribune_veto", view
    assert view.get("registered_veto_controller") == "HUMAN", view
    assert view.get("can_confirm_ai_veto") in (False, None), view
    assert view.get("can_veto") is True, view
    assert carrier.store.canSubmitSenateVeto is True

    before = len(carrier.deciders.calls)
    done = carrier.click_veto([])
    facts = {
        "confirm": {k: done.get(k) for k in ("success", "message")},
        "decider_calls": carrier.deciders.calls,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records": len(_veto_records(carrier.state)),
        "step": carrier.view.get("current_step"),
        "latch": _latch(carrier.state),
    }
    _dump(evidence, "s2-04.json", facts)

    assert done.get("success") is True, facts
    assert carrier.deciders.calls[before:] == [], facts
    assert carrier.producers.auto_vetoes == 0, facts
    assert len(_veto_records(carrier.state)) == 1, facts


# ===========================================================================
# S2-05 — a legitimate EMPTY step still skips (never a permanent WAITING)
# ===========================================================================
def test_s2_05a_no_proposal_still_skips(monkeypatch, evidence):
    carrier = _gate_carrier(monkeypatch, publish=False)
    facts = {
        "step": carrier.view.get("current_step"),
        "decider_calls": carrier.deciders.calls,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records": len(_veto_records(carrier.state)),
        "senate_result": carrier.state.get_phase_result("senate") is not None,
        "can_advance": carrier.store.canAdvanceSenate,
    }
    _dump(evidence, "s2-05a.json", facts)
    assert carrier.deciders.calls == [], facts
    assert carrier.producers.auto_vetoes == 0, facts
    assert carrier.view.get("current_step") == "results", facts
    assert carrier.state.get_phase_result("senate") is not None, facts


def test_s2_05b_zero_passed_candidates_converge_to_terminal(monkeypatch, evidence):
    """Lawful NONE (no passed candidate) through the REAL continuation.

    SA R2: the previous revision accepted ``settlement_pending`` here, i.e. it
    could not tell a converged skip from a permanent wait. The production vote
    continuation must reach the terminal facts: step ``results``, a real senate
    result, and an advanceable senate — with ZERO AI veto activity.
    """
    carrier = _gate_carrier(monkeypatch, ai_votes=False, human_yes=False)
    view = carrier.view
    result = carrier.state.get_phase_result("senate") or {}
    facts = {
        "vote": {k: (carrier.checks.get("vote") or {}).get(k)
                 for k in ("success", "message")},
        "step": view.get("current_step"),
        "candidates": view.get("veto_candidate_ids"),
        "veto_mode": view.get("veto_control_mode"),
        "decider_calls": carrier.deciders.calls,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records": len(_veto_records(carrier.state)),
        "senate_result": carrier.state.get_phase_result("senate") is not None,
        "result_success": result.get("success"),
        "can_advance": carrier.store.canAdvanceSenate,
        "canonical": senate_api.canonical_finalization(carrier.state).get(
            "status"),
    }
    _dump(evidence, "s2-05b.json", facts)
    assert view.get("veto_candidate_ids") == [], facts
    assert carrier.deciders.calls == [], facts
    assert carrier.producers.auto_vetoes == 0, facts
    assert len(_veto_records(carrier.state)) == 0, facts
    # PRODUCTION CONTINUATION converged: never a permanent settlement wait.
    assert view.get("current_step") == "results", facts
    assert facts["senate_result"] is True, facts
    assert result.get("success") is True, facts
    assert carrier.store.canAdvanceSenate is True, facts
    assert facts["canonical"] == "VALID", facts


def test_s2_05c_resolver_backed_none_converges_through_production(monkeypatch, evidence):
    """Lawful NONE built BEFORE the vote, so the PRODUCTION path must converge.

    SA R2: removing the office after the gate had already opened and then calling
    ``_refresh_senate_view()`` only produced a pending projection. Here the
    resolver-backed NONE exists at vote time, so the real vote continuation (the
    masked owning flow + ``_converge_senate_settlement``) has to skip the veto
    substep and reach the terminal facts on its own.
    """
    carrier = _gate_carrier(monkeypatch, retarget=False, ai_votes=True,
                            before_vote=_drop_tribune_office)
    view = carrier.view
    result = carrier.state.get_phase_result("senate") or {}
    facts = {
        "before_vote": carrier.checks.get("before_vote"),
        "vote": {k: (carrier.checks.get("vote") or {}).get(k)
                 for k in ("success", "message")},
        "step": view.get("current_step"),
        "veto_mode": view.get("veto_control_mode"),
        "candidates": view.get("veto_candidate_ids"),
        "decider_calls": carrier.deciders.calls,
        "auto_veto_producer": carrier.producers.auto_vetoes,
        "veto_records": len(_veto_records(carrier.state)),
        "senate_result": carrier.state.get_phase_result("senate") is not None,
        "result_success": result.get("success"),
        "can_advance": carrier.store.canAdvanceSenate,
        "canonical": senate_api.canonical_finalization(carrier.state).get(
            "status"),
    }
    _dump(evidence, "s2-05c.json", facts)
    assert carrier.deciders.calls == [], facts
    assert carrier.producers.auto_vetoes == 0, facts
    assert len(_veto_records(carrier.state)) == 0, facts
    assert facts["canonical"] in ("VALID", "ABSENT"), facts
    # PRODUCTION CONTINUATION converged: never a permanent settlement wait.
    assert view.get("current_step") == "results", facts
    assert facts["senate_result"] is True, facts
    assert result.get("success") is True, facts
    assert carrier.store.canAdvanceSenate is True, facts


# ===========================================================================
# S2-06 — Year-2 REAL AI-veto gate: new scope, old handle cannot release it
# ===========================================================================
def test_s2_06_year_two_gate_and_year_one_handle_isolation(monkeypatch, evidence):
    """SA R3: a genuine Year-2 AI-veto gate, then a Year-1 handle replay.

    Year 1 is driven through the real chain and confirmed once. The year is then
    closed by the product's own annual use-case, and the SAME Store is driven
    through the real Year-2 chain until a NEW AI-veto gate is genuinely
    outstanding (new scope, new OID, new epoch). Only then is the captured
    Year-1 affirmative handle replayed.
    """
    rng_state = random.getstate()
    random.seed(42)
    try:
        carrier = _gate_carrier(monkeypatch, hold_rng=True)
        state, store = carrier.state, carrier.store
        year1 = {
            "scope_id": _book_scope(state)[1].scope_id,
            "veto_oid": list(_veto_oid(state)),
            "session_id": carrier.view.get("senate_session_id"),
            "revision": sts.current_revision(state),
            "records": len(_veto_records(state)),
            "total_records": len(_all_veto_records(state)),
            "handle": dict(store._senate_view),
            "proposal_ids": [p.get("id") for p in state.get_senate_proposals()],
        }
        assert year1["handle"].get("can_confirm_ai_veto") is True, year1
        assert year1["records"] == 0, year1

        confirmed = carrier.click_veto([])
        assert confirmed.get("success") is True, confirmed
        assert _settle(store), confirmed
        store._refresh_senate_view()
        assert senate_api.canonical_finalization(state).get("status") == "VALID"
        assert len(_veto_records(state)) == 1
        year1_record = _veto_records(state)[0]
        year1["record_command"] = year1_record.command_id
        year1["record_revision"] = year1_record.satisfied_at_revision
        year1["context"] = session_access.get_context(state)

        closed = probe._close_year(store, state, carrier.pids)
        facts = {
            "year1": {k: v for k, v in year1.items()
                      if k not in ("handle", "context")},
            "year1_context": {
                "principal": (year1["context"].principal_player_id
                              if year1["context"] is not None else None),
                "epoch": (year1["context"].epoch
                          if year1["context"] is not None else None),
            },
            "year1_handle": {k: year1["handle"].get(k) for k in (
                "current_step", "can_confirm_ai_veto", "viewer_player_id",
                "senate_session_id", "veto_candidate_ids")},
            "close": closed,
        }
        assert closed.get("advanced") is True, facts
        store._refresh_senate_view()
        assert state.turn.turn_number == 2, facts

        # ---------------- Year 2: drive the REAL chain to a NEW gate --------
        deciders_at_year2_entry = len(carrier.deciders.calls)
        _run_chain(carrier, retarget=True)
        gate2 = _gate_snapshot(carrier)
        facts["gate_year2"] = gate2
        facts["year2_checks"] = {k: v for k, v in carrier.checks.items()
                                 if k in ("tribune_id", "proposal_ids",
                                          "step_after_entry", "vote")}
        facts["deciders_at_year2_entry"] = deciders_at_year2_entry
        facts["year2_scope_is_new"] = gate2["scope_id"] != year1["scope_id"]
        facts["year2_oid_is_new"] = gate2["veto_oid"] != year1["veto_oid"]

        assert facts["year2_scope_is_new"] is True, facts
        assert facts["year2_oid_is_new"] is True, facts
        assert gate2["step"] == "tribune_veto", facts
        assert gate2["can_confirm_ai_veto"] is True, facts
        assert gate2["veto_oid_satisfied"] is False, facts
        assert gate2["veto_candidate_ids"], facts
        # NOTHING ran for the new gate before the human gesture.
        assert len(carrier.deciders.calls) == deciders_at_year2_entry, facts
        # The NEW scope has no veto record yet (the gate is unconsumed), and the
        # detached Year-1 book is not the current one.
        assert gate2["records"] == 0, facts
        assert len(_all_veto_records(state)) == 0, facts
        assert year1_record.satisfied_at_revision == year1["record_revision"], facts

        # ------- (1) the Year-1 seat HANDLE (epoch-bound) replayed ---------
        before_ctx = _counters(carrier)
        old_context_response = carrier.producers.real_vetoes(
            state, None, carrier.viewer, caller_context=year1["context"])
        after_ctx = _counters(carrier)
        facts["old_handle_replay"] = {
            "response": {k: old_context_response.get(k)
                         for k in ("success", "message", "errors")},
            "before": before_ctx, "after": after_ctx,
        }
        assert old_context_response.get("success") is False, facts
        ctx_codes = [e.get("code") for e in
                     (old_context_response.get("errors") or [])
                     if isinstance(e, dict)]
        assert "DENIED" in ctx_codes, facts
        assert after_ctx == before_ctx, facts
        store._refresh_senate_view()
        gate_after_ctx = _gate_snapshot(carrier)
        facts["gate_after_old_handle"] = gate_after_ctx
        assert gate_after_ctx["step"] == "tribune_veto", facts
        assert gate_after_ctx["veto_oid_satisfied"] is False, facts

        # ------- (2) the Year-1 affirmative PROJECTION replayed -------------
        # PRODUCT FACT (discriminated, not assumed): the confirmation gesture
        # carries NO scope/epoch identity — ``doSubmitSenateVetoes`` reads only
        # the live ``veto_control_mode`` and a FRESH projection. A stale client
        # projection is therefore inert: it is discarded, and the gesture is
        # applied to the LIVE Year-2 gate exactly once. The cross-year security
        # property is carried by the handle/epoch denial above plus the scope/OID
        # separation asserted below, NOT by rejecting the click.
        before_replay = _counters(carrier)
        store._senate_view = dict(year1["handle"])
        replay = store.doSubmitSenateVetoes(year1["proposal_ids"])
        after_replay = _counters(carrier)
        recovered = _settle(store)
        store._refresh_senate_view()
        gate_after_replay = _gate_snapshot(carrier)
        facts["old_projection_replay"] = {
            "response": {k: replay.get(k) for k in ("success", "message",
                                                    "errors")},
            "before": before_replay, "after": after_replay,
            "seat_recovered": recovered,
            "gate_after": gate_after_replay,
        }
        _dump(evidence, "s2-06.json", facts)

        assert replay.get("success") is True, facts
        # Exactly ONE traversal of the YEAR-2 candidates (the stale view is gone).
        assert (after_replay["decider_calls"] - before_replay["decider_calls"]
                == len(gate2["veto_candidate_ids"])), facts
        # The released obligation is the YEAR-2 one, and only it.
        assert after_replay["veto_records"] == before_replay["veto_records"] + 1
        assert after_replay["veto_receipts"] == before_replay["veto_receipts"] + 1
        assert gate_after_replay["veto_oid_satisfied"] is True, facts
        # The Year-1 record/scope was NOT revived or rewritten.
        assert year1_record.satisfied_at_revision == year1["record_revision"], facts
        assert gate_after_replay["scope_id"] == gate2["scope_id"], facts

        # ---- (3) then a further normal gesture on the consumed gate ---------
        extra = carrier.click_veto([])
        store._refresh_senate_view()
        facts["year2_confirm_after"] = {
            "response": {k: extra.get(k) for k in ("success", "message",
                                                   "errors")},
            "records": len(_veto_records(state)),
            "receipts": len(_veto_receipts(state)),
            "decider_calls": len(carrier.deciders.calls),
            "canonical": senate_api.canonical_finalization(state).get("status"),
            "step": carrier.view.get("current_step"),
        }
        _dump(evidence, "s2-06.json", facts)
        assert extra.get("success") is False, facts
        assert len(carrier.deciders.calls) == after_replay["decider_calls"], facts
        assert len(_veto_records(state)) == 1, facts
        assert len(_veto_receipts(state)) == 1, facts
        assert facts["year2_confirm_after"]["canonical"] == "VALID", facts
    finally:
        random.setstate(rng_state)


# ===========================================================================
# S2-07 — real Qt first frame: button / mask / activation / last_good source
# ===========================================================================
def test_s2_07_real_qml_button_mask_and_activation(monkeypatch, evidence):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    from src.ui.gui.models.candidate_list_model import CandidateListModel
    from src.ui.gui.models.event_list_model import EventListModel
    from src.ui.gui.models.figure_list_model import FigureListModel

    carrier = _gate_carrier(monkeypatch)
    store = carrier.store
    assert store.senateCurrentStep == "tribune_veto"

    app = QGuiApplication.instance() or QGuiApplication([])
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(
        QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    theme = theme_component.create()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", None)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    app.processEvents()
    assert engine.rootObjects(), "the production QML tree did not load"
    root = engine.rootObjects()[0]

    store.selectPhase("senate")
    for _ in range(6):
        app.processEvents()
    button = root.findChild(QObject, "senateVetoSubmitButton")
    assert button is not None, "senateVetoSubmitButton not found in the real QML"
    frame_facts = {
        "button_enabled": bool(button.property("enabled")),
        "store_can_submit": bool(store.canSubmitSenateVeto),
        "dto_can_confirm": bool(store._senate_view.get("can_confirm_ai_veto")),
        "dto_can_veto": bool(store._senate_view.get("can_veto")),
        "mask_before": bool(store.handoffMaskVisible),
        "lifecycle_before": store.seatLifecycle,
        "last_good_viewer_before": (
            (store._last_good_views.get("senate") or {}).get("viewer")),
    }
    # The REAL control is enabled from the SAME DTO predicate (no local guess).
    assert frame_facts["button_enabled"] is True, frame_facts
    assert frame_facts["dto_can_confirm"] is True, frame_facts
    assert frame_facts["dto_can_veto"] is False, frame_facts

    # The QML handler's own call (the same Slot, the same payload binding).
    clicked = store.doSubmitSenateVetoes([])
    frame_facts["click"] = {k: clicked.get(k) for k in ("success", "message")}
    frame_facts["decider_calls"] = carrier.deciders.calls
    frame_facts["lifecycle_after"] = store.seatLifecycle
    frame_facts["mask_after"] = bool(store.handoffMaskVisible)
    frame_facts["witness_calls"] = [list(c)[0] for c in carrier.witness.calls]
    frame_facts["last_good"] = {
        "viewer": (store._last_good_views.get("senate") or {}).get("viewer"),
        "stale": bool(store._stale_resources.get("senate")),
        "projection_stale": bool(store.projectionStale),
    }
    frame_facts["step_after"] = store.senateCurrentStep
    for _ in range(6):
        app.processEvents()
    button_after = root.findChild(QObject, "senateVetoSubmitButton")
    frame_facts["button_enabled_after"] = bool(
        button_after.property("enabled") if button_after is not None else False)
    _dump(evidence, "s2-07.json", frame_facts)

    assert clicked.get("success") is True, frame_facts
    assert len(carrier.deciders.calls) > 0, frame_facts
    # The seat really went through the masked transaction and came back ACTIVE.
    assert "arm" in frame_facts["witness_calls"], frame_facts
    assert store.seatLifecycle == SEAT_ACTIVE, frame_facts
    assert frame_facts["last_good"]["viewer"] == carrier.viewer, frame_facts
    # The real control follows the DTO again after the decision.
    assert frame_facts["button_enabled_after"] is False, frame_facts
