"""G7 / D18-D19 — PHASE-1 READ-ONLY probe: second-turn Senate observability.

WHY THIS FILE EXISTS
--------------------
``EOR20261013-02 / G7-W3-SecondTurn-Senate-D18D19`` has NO evidenced branch yet:
T16/T17/T18 show "Turn2 population settled, handoff activated, no Senate
proposal", but no run recorded the authoritative phase/capability facts. This
probe recreates the three REAL registered carriers on the frozen ``b004144``
product and records the SAME session's Turn1 (positive control) and Turn2
(candidate failure) at three observation points:

  P0 = last Population ballot done, immediately BEFORE ``doAdvancePopulation``
  P1 = ``doAdvancePopulation`` returned, seat ACTIVE, Senate submit surface up
  P2 = the real ``doSubmitSenateProposals`` entry and its return value

It does NOT fix anything, does NOT assert a root cause and does NOT touch one
product byte. Every wrapper below is installed on the TEST process only.

EVIDENCE LEVEL
--------------
``REAL_REGISTERED``: the session is created by the production factory
(``session_api.create_gui_prototype_session`` on the shipped scenario + config),
registered through ``session_access.register_hotseat_session``, and driven only
through the REAL Store slots (``doExecuteMortality`` … ``doAdvancePopulation``,
``doSubmitSenateProposals``, ``doAdvanceSenate`` … ``doAdvanceResolution``) on the
REAL masked seat machine with the SAME synchronous barrier witness the W3 chains
use. No ``QQuickWindow`` is constructed, so ``button_enabled`` is the frozen QML
predicate (``(canCreate || canTriggerAI) && !hasZeroValueLandSelection &&
!aiBlocked``, SenateStage.qml:1870-1886) evaluated on the SAME Store properties
the QML binds — never a headless boolean invented by the test.

The only test-side helper that crosses a year is ``game_api.advance_year`` (the
product's own annual use-case). When the full GUI chain cannot reach resolution
(the known headless-seat owner barrier), ``force=True`` — the product's own
documented escape door — is used and recorded in ``03-Run-Log.md``; the Core
commit, the detached new-year book and the scope generation change are real.
"""
from __future__ import annotations

import json
import functools
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import forum_api
from src.api import game_api
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
SCENARIO_1H2AI = "gui_prototype.json"
SCENARIO_3H = "gr_f_3h.json"

EVIDENCE_DIR = os.environ.get(
    "G7_D18D19_EVIDENCE_DIR",
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20261013-02 GUI-Readiness/"
    "03-da-evidence/G7-D18D19-RED",
)
SNAPSHOT_DIR = os.path.join(EVIDENCE_DIR, "02-Snapshots")

POPULATION_OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")


# ---------------------------------------------------------------------------
# Production-shape witnesses (identical shape to the W3 chains / D16 rework)
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


# ---------------------------------------------------------------------------
# Production carriers
# ---------------------------------------------------------------------------
def _factory(scenario):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="mortality", scenario_file=scenario)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    state.set_current_player(pids[0])
    return state, pids


def _store(state, viewer):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _Witness()
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    if store.seatLifecycle == SEAT_MASKED_PENDING:
        store.requestTakeover()
    if store.seatLifecycle == SEAT_ACTIVE:
        store._refresh_senate_view()
        store._refresh_population_view()
        store._refresh_snapshot()
    return store, witness


def _ctx(state):
    return session_access.present_context(state)


def _api_call(fn, *args):
    try:
        return fn(*args, caller_context=_ctx(args[0]))
    except TypeError:
        return fn(*args)


# ---------------------------------------------------------------------------
# Year drivers (REAL Store slots only)
# ---------------------------------------------------------------------------
def _play_forum_year(store, limit=24):
    intents = []
    steps = 0
    while not store.forumResolved and steps < limit:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            continue
        if store.seatLifecycle != SEAT_ACTIVE:
            break
        substep = store.forumCurrentStep
        fb = (store.doCompleteForumStep() if substep == "retirement"
              else store.doResolveForum())
        intents.append((substep, bool(fb.get("success")), fb.get("message")))
        if not fb.get("success"):
            break
    return intents


def _abstain_selections(store):
    picks = {}
    for candidate in store.populationCandidates:
        office = candidate.get("office")
        if office and office not in picks and candidate.get("id"):
            picks[office] = candidate.get("id")
    return picks


def _own_consul_selection(store, viewer_faction):
    """A lawful ballot that prefers the viewer faction's own consul candidate."""
    picks = {}
    for candidate in store.populationCandidates:
        office = candidate.get("office")
        if not office or office in picks or not candidate.get("id"):
            continue
        picks[office] = candidate.get("id")
    for candidate in store.populationCandidates:
        if (candidate.get("office") == "consul"
                and candidate.get("faction_id") == viewer_faction
                and candidate.get("id")):
            picks["consul"] = candidate.get("id")
            break
    return picks


def _play_population(store, selections, limit=12):
    steps = 0
    while not store.populationResolved and steps < limit:
        steps += 1
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
            store._refresh_population_view()
            continue
        if store.seatLifecycle != SEAT_ACTIVE:
            break
        fb = store.submitPopulationVotes(selections)
        if not fb.get("success"):
            return fb
    return None


def _entry_chain(store, state):
    """mortality -> revenue -> forum -> population, all through Store slots."""
    out = []
    store._reset_phase_caches()
    store._refresh_snapshot()
    for name in ("doExecuteMortality", "doAdvanceMortality",
                 "doExecuteRevenue", "doAdvanceRevenue"):
        fb = getattr(store, name)()
        out.append((name, bool(fb.get("success")), fb.get("message")))
        if not fb.get("success"):
            return out
    out.extend(("forum", ok, msg) for _s, ok, msg in _play_forum_year(store))
    if not store.forumResolved:
        return out
    pid = state.get_current_player().player_id
    adv = _api_call(forum_api.advance_forum_phase, state, pid)
    out.append(("advance_forum_phase", bool(adv.get("success")),
                adv.get("message")))
    return out


# ---------------------------------------------------------------------------
# Snapshot (the frozen P0/P1/P2 field set)
# ---------------------------------------------------------------------------
def _safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - observation only
        return default if default is not None else "ERR:%s" % type(exc).__name__


def _counters():
    return {"advance_calls": 0, "advance_ok": None, "advance_error": None,
            "producer_calls": 0, "ai_producer_calls": 0, "clicks": 0,
            "access": [], "lease": [], "advance_api": None}


def _source_ref(obj):
    """(file, first line) of a live symbol — the exact product provenance."""
    import inspect
    try:
        src_file = inspect.getsourcefile(obj)
        lineno = inspect.findsource(obj)[1] + 1
        return {"file": os.path.relpath(src_file, PROJECT_ROOT),
                "line": lineno,
                "symbol": getattr(obj, "__qualname__",
                                  getattr(obj, "__name__", ""))}
    except Exception as exc:  # pragma: no cover - diagnostic only
        return {"error": type(exc).__name__}


def _install_access_trace(counters):
    """Read-only observation of the ONE seat predicate (never re-decides)."""
    original_auth = session_access.authorize_hotseat
    original_lease = session_access.authorize_and_lease
    original_consume = session_access.consume_command_lease

    def _auth(*a, **k):
        decision = original_auth(*a, **k)
        counters["access"].append({
            "operation": a[1] if len(a) > 1 else k.get("operation"),
            "command": k.get("command"),
            "viewer": k.get("viewer"),
            "allowed": bool(getattr(decision, "allowed", None)),
            "reason": getattr(decision, "reason", None),
            "exempt": getattr(decision, "exempt", None),
        })
        return decision

    def _lease(*a, **k):
        lease = original_lease(*a, **k)
        counters["lease"].append({
            "stage": "issue", "command": k.get("command"),
            "issued": lease is not None,
        })
        return lease

    def _consume(*a, **k):
        reason = original_consume(*a, **k)
        counters["lease"].append({"stage": "consume", "reason": reason})
        return reason

    session_access.authorize_hotseat = _auth
    session_access.authorize_and_lease = _lease
    session_access.consume_command_lease = _consume
    return (original_auth, original_lease, original_consume)


def _restore_access_trace(saved):
    (session_access.authorize_hotseat,
     session_access.authorize_and_lease,
     session_access.consume_command_lease) = saved


def _snapshot(state, store, run_id, turn, point, counters, extra=None):
    view = dict(getattr(store, "_senate_view", {}) or {})
    book = getattr(state, "_session_turn_book", None)
    scope = book.scopes.get("senate") if book is not None else None
    snap = _safe(lambda: sts.obligations(state, "senate"))
    prop = None
    if snap is not None and not isinstance(snap, str):
        prop = next((o for o in snap.obligations if o.substep == "proposal"), None)
    sel = {}
    if book is not None and scope is not None:
        sel = (book.role_selections.get((scope.scope_id, "proposal")) or {})
    can_create = bool(view.get("can_create_proposal", False))
    can_trigger = bool(view.get("can_trigger_ai_proposer", False))
    blocked = bool(store.senateAiProposerBlocked)
    pending_props = _safe(lambda: len(state.get_senate_proposals()), -1)
    pkg_id = _safe(lambda: state.get_senate_package_id_for_session(
        "turn-%s" % state.turn.turn_number), None)
    record = {
        "run": run_id,
        "point": point,
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "turn": _safe(lambda: state.turn.turn_number),
        "core_current": _safe(lambda: state.get_current_player().player_id),
        "viewer": getattr(store, "_viewer_id", None),
        "seat_lifecycle": store.seatLifecycle,
        "selected_phase_id": getattr(store, "_selected_phase_id", ""),
        "authoritative_current_phase": _safe(
            lambda: session_api._infer_current_phase_id(state)),
        "population_result_exists": _safe(
            lambda: bool(state.get_phase_result("population")), False),
        "population_executed": _safe(
            lambda: bool(state.is_phase_executed("population")), False),
        "advance_population_called": counters["advance_calls"],
        "advance_population_success": counters["advance_ok"],
        "advance_population_error_code_stage": counters["advance_error"],
        "senate_entry_receipt_valid": (extra.get("entry_receipt_valid")
                                        if extra else
                                        (counters.get("advance_api") or {}).get(
                                            "entry_receipt_present")),
        "senate_scope_id": (scope.scope_id if scope is not None else None),
        "senate_scope_actor_G": (getattr(scope, "actor", None)
                                 if scope is not None else None),
        "book_turn": (getattr(book, "turn_number", None)
                      if book is not None else None),
        "book_revision": (getattr(book, "revision_counter", None)
                          if book is not None else None),
        "proposed_owner_player": (sel.get("actor_player_id")
                                  if sel else view.get(
                                      "registered_proposal_owner_player_id")),
        "proposed_owner_controller": (sel.get("controller") if sel else
                                      view.get("registered_proposal_controller")),
        "proposal_oid_satisfied": (bool(prop.satisfied) if prop is not None
                                   else None),
        "pending_proposal_count": pending_props,
        "decision_complete": _safe(
            lambda: bool(state.senate_proposal_decision_complete), False),
        "no_host": _safe(lambda: state.get_presiding_officer() is None, None),
        "readiness_proposal_ready": bool(view.get("readiness_ok", False)),
        "readiness_errors": list(view.get("readiness_errors") or []),
        "current_step": view.get("current_step"),
        "registered_seat": bool(view.get("registered_seat", False)),
        "registered_schedule_valid": bool(
            view.get("registered_schedule_valid", False)),
        "dto_viewer_id": view.get("viewer_player_id"),
        "can_create": can_create,
        "can_trigger_ai": can_trigger,
        "ai_proposer_blocked": blocked,
        "button_enabled": bool((can_create or can_trigger) and not blocked),
        "button_click_count": counters["clicks"],
        "producer_dispatch_count": counters["producer_calls"],
        "new_proposal_count": pending_props,
        "owner_package_count": 1 if pkg_id else 0,
        "senate_view_keys": sorted(view.keys()) if extra and extra.get(
            "dump_keys") else None,
        "senate_view_success": view.get("success"),
        "senate_view_message": view.get("message"),
        "senate_view_errors": view.get("errors"),
        "senate_view_denied": view.get("denied") or view.get("masked"),
        "adapter_ai_producer_calls": counters["ai_producer_calls"],
        "advance_api_result": counters.get("advance_api"),
        "book_consumed_receipts": _safe(
            lambda: sorted(book.consumed_receipts) if book is not None else None,
            None),
        "culprit_source_refs": {
            "senate_finalization_id": _source_ref(senate_api.senate_finalization_id),
            "canonical_finalization": _source_ref(senate_api.canonical_finalization),
            "get_senate_view": _source_ref(senate_api.get_senate_view),
            "get_senate_session": _source_ref(type(state).get_senate_session),
        },
        "canonical_finalization": _safe(lambda: {
            k: senate_api.canonical_finalization(state).get(k)
            for k in ("status", "stage", "detail", "key", "fingerprint",
                      "facts")}),
        "canonical_with_current_turn_key": _safe(lambda: (lambda k: {
            "key": list(k),
            "status": senate_api.canonical_finalization(
                state, expected_key=k).get("status"),
            "stage": senate_api.canonical_finalization(
                state, expected_key=k).get("stage"),
        })(("turn-%s" % state.turn.turn_number,
            "turn-%s" % state.turn.turn_number, 2))),
        "senate_finalization_id": _safe(
            lambda: senate_api.senate_finalization_id(state)),
        "senate_session_id": _safe(lambda: state.get_senate_session()),
        "senate_phase_result_present": _safe(
            lambda: state.get_phase_result("senate") is not None, None),
        "finalization_receipt_index_keys": _safe(
            lambda: sorted(getattr(state, "_senate_finalization_receipts",
                                   {}).keys()), None),
        "book_receipt_keys": _safe(
            lambda: sorted(book.receipts.keys()) if book is not None else None,
            None),
    }
    if extra:
        record.update({k: v for k, v in extra.items()
                       if k not in ("dump_keys",)})
    return record


def _emit(record):
    print("G7_SNAP %s" % json.dumps(record, ensure_ascii=False, sort_keys=True,
                                    default=str))


def _persist(record, run_id):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(
        SNAPSHOT_DIR, "%s-T%s-%s.json" % (run_id, record.get("turn"),
                                          record.get("point")))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True,
                  default=str)
    _append_runlog(
        "| %s | T%s | %s | %s | %s | %s/%s | %s | %s | %s | %s |" % (
            run_id, record.get("turn"), record.get("point"),
            record.get("authoritative_current_phase"),
            record.get("current_step"),
            record.get("proposed_owner_controller"),
            record.get("proposed_owner_player"),
            record.get("can_create"), record.get("can_trigger_ai"),
            record.get("button_enabled"),
            ",".join(record.get("readiness_errors") or []) or "-"))
    return path


_RUNLOG_STARTED = {"v": False}


def _append_runlog(line):
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, "_machine-rows.md")
    if not _RUNLOG_STARTED["v"]:
        # One fresh machine table per pytest process (the narrative 03-Run-Log.md is
        # a hand-written companion; this file is regenerated, never duplicated).
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# G7 D18/D19 — run log (machine rows)\n\n"
                     "| run | turn | point | phase | step | owner | can_create | "
                     "can_trigger_ai | button | readiness_errors |\n"
                     "|:--|:--|:--|:--|:--|:--|:-:|:-:|:-:|:--|\n")
        _RUNLOG_STARTED["v"] = True
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------------------
# One complete two-year run
# ---------------------------------------------------------------------------
def _run(run_id, scenario, *, consul_preference):
    # Deterministic replay: the scenario declares ``random_seed = 42``; the probe
    # re-seeds the process RNG so the SAME carrier is reproducible run-to-run
    # (no product file is touched, no state is fabricated).
    import random
    rng_state = random.getstate()
    random.seed(42)
    try:
        return _run_seeded(run_id, scenario, consul_preference)
    finally:
        random.setstate(rng_state)


def _run_seeded(run_id, scenario, consul_preference):
    state, pids = _factory(scenario)
    viewer = pids[0]
    store, witness = _store(state, viewer)
    assert session_access.is_hotseat_registered(state) is True

    counters = _counters()
    original_advance = store._adapter.advance_population

    def _advance(viewer_id):
        counters["advance_calls"] += 1
        res = original_advance(viewer_id)
        counters["advance_ok"] = bool(res.get("success"))
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        delivery = data.get("delivery") if isinstance(data.get("delivery"),
                                                      dict) else {}
        counters["advance_api"] = {
            "success": res.get("success"),
            "message": res.get("message"),
            "data_keys": sorted(data.keys()),
            "entry_receipt_present": bool(data.get("entry_receipt")),
            "delivery_present": bool(delivery),
            "delivery_outcome": delivery.get("outcome"),
            "delivery_next_controller": (delivery.get("next") or {}).get(
                "controller"),
            "delivery_next_actor": (delivery.get("next") or {}).get(
                "actor_player_id"),
            "delivery_next_disposition": (delivery.get("next") or {}).get(
                "disposition"),
            "delivery_error": data.get("delivery_error"),
        }
        if not res.get("success"):
            err = data.get("delivery_error")
            counters["advance_error"] = {
                "message": res.get("message"),
                "errors": res.get("errors"),
                "delivery_error": err,
            }
        return res

    store._adapter.advance_population = _advance

    original_propose = senate_api.propose_many
    original_auto = senate_api.auto_submit_proposals

    def _propose(*a, **k):
        counters["producer_calls"] += 1
        return original_propose(*a, **k)

    def _auto(*a, **k):
        counters["ai_producer_calls"] += 1
        return original_auto(*a, **k)

    # The Adapter routes by ``api_func.__name__`` (the one-seat continuation
    # scope is keyed by the owning COMMAND name), so a counting wrapper MUST keep
    # the original name; otherwise the spy itself would be denied.
    functools.update_wrapper(_propose, original_propose)
    functools.update_wrapper(_auto, original_auto)

    senate_api.propose_many = _propose
    senate_api.auto_submit_proposals = _auto
    saved_trace = _install_access_trace(counters)
    try:
        records = []
        closes = []
        for turn in (1, 2):
            chain = _entry_chain(store, state)
            if store.seatLifecycle == SEAT_MASKED_PENDING:
                store.requestTakeover()
            store._refresh_population_view()
            selections = (consul_preference(store, viewer)
                          if callable(consul_preference) else {})
            pop_fail = _play_population(store, selections)
            store._refresh_population_view()
            store._refresh_snapshot()

            p0 = _snapshot(state, store, run_id, turn, "P0", counters)
            _persist(p0, run_id)
            records.append(p0)
            _emit(p0)

            fb = store.doAdvancePopulation()
            entry_receipt = ((fb.get("data") or {}).get("entry_receipt")
                             if isinstance(fb.get("data"), dict) else None)
            if store.seatLifecycle == SEAT_MASKED_PENDING:
                store.requestTakeover()
            store._refresh_senate_view()
            extra = {
                "advance_return_success": bool(fb.get("success")),
                "advance_return_message": fb.get("message"),
                "advance_return_errors": fb.get("errors"),
                "advance_return_delivery_error": (
                    (fb.get("data") or {}).get("delivery_error")
                    if isinstance(fb.get("data"), dict) else None),
                "entry_receipt_valid": bool(
                    (counters.get("advance_api") or {}).get("entry_receipt_present")),
                "population_play_failure": (pop_fail.get("message")
                                            if isinstance(pop_fail, dict) else None),
                "entry_chain": chain,
                "witness_calls": [list(c)[0] for c in witness.calls],
                "access_trace_tail": counters["access"][-8:],
                "lease_trace_tail": counters["lease"][-6:],
            }
            p1 = _snapshot(state, store, run_id, turn, "P1", counters, extra)
            _persist(p1, run_id)
            records.append(p1)
            _emit(p1)

            before_props = len(state.get_senate_proposals())
            before_pkg = state.get_senate_package_id_for_session(
                "turn-%s" % state.turn.turn_number)
            submit_fb = None
            if p1["button_enabled"]:
                store._refresh_senate_view()
                submit_fb = store.doSubmitSenateProposals([])
                counters["clicks"] += 1
                if store.seatLifecycle == SEAT_MASKED_PENDING:
                    store.requestTakeover()
                store._refresh_senate_view()
            if submit_fb is None:
                # The button is NOT clickable: record why, never fake a click.
                submit_fb = {
                    "success": None,
                    "message": "BUTTON_DISABLED: no real click dispatched",
                    "data": {"can_create": p1["can_create"],
                             "can_trigger_ai": p1["can_trigger_ai"],
                             "ai_proposer_blocked": p1["ai_proposer_blocked"],
                             "current_step": p1["current_step"]},
                }
            after_props = len(state.get_senate_proposals())
            after_pkg = state.get_senate_package_id_for_session(
                "turn-%s" % state.turn.turn_number)
            extra2 = {
                "submit_return": {
                    "success": submit_fb.get("success"),
                    "message": submit_fb.get("message"),
                    "errors": submit_fb.get("errors"),
                    "feedback_message": submit_fb.get("feedback_message"),
                    "data_keys": sorted((submit_fb.get("data") or {}).keys())
                    if isinstance(submit_fb.get("data"), dict) else None,
                },
                "new_proposal_delta": after_props - before_props,
                "owner_package_delta": (1 if (after_pkg and not before_pkg)
                                        else 0),
                "senate_package_id": after_pkg,
                "access_trace_tail": counters["access"][-10:],
                "lease_trace_tail": counters["lease"][-8:],
            }
            p2 = _snapshot(state, store, run_id, turn, "P2", counters, extra2)
            _persist(p2, run_id)
            records.append(p2)
            _emit(p2)

            # ---- close the year through the REAL product chain ----
            senate_steps = _finish_senate(store, state)
            print("G7_SENATE_FINISH %s turn=%s %s" % (run_id, turn, json.dumps(
                senate_steps, ensure_ascii=False, default=str)))
            closed = _close_year(store, state, pids)
            closes.append({"turn": turn, **closed})
            print("G7_YEAR_CLOSE %s turn=%s %s" % (run_id, turn, json.dumps(
                closed, ensure_ascii=False, default=str)))
            if turn == 1 and not closed.get("advanced"):
                raise AssertionError("year 1 could not advance: %s" % (closed,))
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        with open(os.path.join(SNAPSHOT_DIR, "%s-year-close.json" % run_id),
                  "w", encoding="utf-8") as fh:
            json.dump(closes, fh, ensure_ascii=False, indent=2, sort_keys=True,
                      default=str)
        return records
    finally:
        _restore_access_trace(saved_trace)
        senate_api.propose_many = original_propose
        senate_api.auto_submit_proposals = original_auto
        store._adapter.advance_population = original_advance


def _finish_senate(store, state, limit=8):
    """Drive the senate sub-steps a player really issues (vote / veto).

    The proposal click already happened at P2. This finishes the SAME year's
    senate so Turn1 is a REAL completed control (the Owner's T16/T17/T18 runs all
    submitted proposals in Turn1); Turn2 then starts from a canonically finalized
    prior senate, exactly like the field reports.
    """
    steps = []
    for _ in range(limit):
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            store.requestTakeover()
        store._refresh_senate_view()
        if store.seatLifecycle != SEAT_ACTIVE:
            steps.append(("seat", store.seatLifecycle))
            break
        step = store.senateCurrentStep
        ids = [p.get("id") for p in store.senateSubmittedProposals
               if p.get("id") is not None]
        if step == "senate_vote" and store.canSubmitSenateVote and ids:
            # Store signature: doSubmitSenateVotes(agree_ids=None) — approve the
            # listed ids (one positional argument). Driver arity only; the
            # probe's snapshots/assertions are untouched.
            fb = store.doSubmitSenateVotes(ids)
            steps.append(("vote", bool(fb.get("success")), fb.get("message")))
            continue
        if step == "tribune_veto" and store.canSubmitSenateVeto and ids:
            fb = store.doSubmitSenateVetoes(ids)
            steps.append(("veto", bool(fb.get("success")), fb.get("message")))
            continue
        if store.canAdvanceSenate:
            steps.append(("results", True, "can_advance"))
            break
        steps.append(("stop", False, step))
        break
    return steps


def _close_year(store, state, pids):
    """senate -> combat -> resolution -> advance_year (real, no force first)."""
    out = {}
    if store.seatLifecycle == SEAT_MASKED_PENDING:
        store.requestTakeover()
    if store.seatLifecycle != SEAT_ACTIVE:
        out["seat"] = store.seatLifecycle
    out["can_advance_senate"] = bool(store.canAdvanceSenate)
    if store.canAdvanceSenate:
        fb = store.doAdvanceSenate()
        out["advance_senate"] = bool(fb.get("success"))
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            store.requestTakeover()
    store.selectPhase("combat")
    if store.seatLifecycle == SEAT_MASKED_PENDING:
        store.requestTakeover()
    if store.canAdvanceCombat:
        fb = store.doAdvanceCombat()
        out["advance_combat"] = bool(fb.get("success"))
    store.selectPhase("resolution")
    if store.seatLifecycle == SEAT_MASKED_PENDING:
        store.requestTakeover()
    if not store.resolutionResolved:
        store._executeResolution()
    out["resolution_resolved"] = bool(store.resolutionResolved)
    fb = store.doAdvanceResolution()
    out["advance_resolution"] = bool(fb.get("success"))
    out["advance_resolution_message"] = fb.get("message")
    out["senate_session_id_before_year"] = _safe(
        lambda: state.get_senate_session())
    if not out["advance_resolution"]:
        actor = state.get_current_player().player_id
        force = _api_call(game_api.advance_year, state, actor, True)
        out["force_advance_year"] = bool(force.get("success"))
        out["force_message"] = force.get("message")
        out["advanced"] = bool(force.get("success"))
    else:
        out["advanced"] = True
    out["turn_after"] = state.turn.turn_number
    out["senate_session_id_after_year"] = _safe(
        lambda: state.get_senate_session())
    return out


# ---------------------------------------------------------------------------
# Carrier selection helpers
# ---------------------------------------------------------------------------
def _prefer_own_consul(store, viewer):
    faction = store.viewerFactionId
    return _own_consul_selection(store, faction)


def _prefer_foreign_consul(store, viewer):
    """A lawful ballot for ANOTHER faction's consul candidate.

    The consulate then goes to that (AI) faction, producing the 1H2AI / AI-consul
    carrier (T18 shape). Every office still receives one real candidate id, so the
    ballot is complete; nothing about the state is fabricated.
    """
    picks = _abstain_selections(store)
    faction = store.viewerFactionId
    for candidate in store.populationCandidates:
        if (candidate.get("office") == "consul"
                and candidate.get("faction_id") != faction
                and candidate.get("id")):
            picks["consul"] = candidate.get("id")
            break
    return picks


def _abstain(store, viewer):
    return _abstain_selections(store)


# ===========================================================================
# R1 — 1H2AI, HUMAN-held consulate
# ===========================================================================
def test_r1_1h2ai_human_consul_two_years():
    records = _run("R1", SCENARIO_1H2AI, consul_preference=_prefer_own_consul)
    assert records, "no snapshot produced"
    owners = {r["proposed_owner_controller"] for r in records if r["point"] == "P1"}
    print("G7_RUN R1 owners=%s" % owners)


# ===========================================================================
# R2 — 1H2AI, AI-held consulate
# ===========================================================================
def test_r2_1h2ai_ai_consul_two_years():
    records = _run("R2", SCENARIO_1H2AI, consul_preference=_prefer_foreign_consul)
    assert records, "no snapshot produced"
    owners = {r["proposed_owner_controller"] for r in records if r["point"] == "P1"}
    print("G7_RUN R2 owners=%s" % owners)


# ===========================================================================
# R3 — 3H (three real HUMAN seats)
# ===========================================================================
def test_r3_3h_two_years():
    records = _run("R3", SCENARIO_3H, consul_preference=_abstain)
    assert records, "no snapshot produced"
    owners = {r["proposed_owner_controller"] for r in records if r["point"] == "P1"}
    print("G7_RUN R3 owners=%s" % owners)
