"""W3 / G7 — S1 regression: cross-year Senate session identity (D18/D19).

WHY THIS MODULE EXISTS
----------------------
``EOR20261013-02 / G7-W3-SecondTurn-Senate-D18D19`` branch C: the Senate session
identity frozen at the Year-1 Submit point (``GameState._senate_session_id``) is
never rolled at the annual boundary. The Year-2 finalization key therefore still
names the Year-1 session, ``canonical_finalization`` classifies the stale key as
``WRONG`` (the annual boundary already cleared ``_phase_results``), ``current_step``
becomes ``readiness_error`` and BOTH ``can_create`` / ``can_trigger_ai`` are false
⇒ the submit button is disabled and the second year can never open a proposal.

This module pins the frozen contract (AC-S1-01..06) with REAL registered carriers
driven only through production seams (factory session, real Store slots, real
``game_api.advance_year``). It is written RED-first: on the unfixed product every
year-2 assertion fails at ``current_step``; after the one-line identity fix the
same module is GREEN.

NO ``force=True`` is used to advance a year in this module; Year-1 must complete
through the real ``doAdvanceSenate → combat → resolution → advance_year`` chain.
The probe module is imported as a read-only harness library (its judgements are
never modified); all observation is done on the SAME Store properties the QML
bindings read — no ``QQuickWindow``, no headless boolean invented by the test.
"""
from __future__ import annotations

import functools
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

from src.api import senate_api
from src.api import session_access
from src.ui.gui.session_store import SEAT_MASKED_PENDING


def _load_probe():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_g7_second_turn_probe.py")
    spec = importlib.util.spec_from_file_location(
        "_g7_second_turn_probe_lib", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()


# ---------------------------------------------------------------------------
# Instrumentation (read-only spies that call the original symbol unchanged)
# ---------------------------------------------------------------------------
def _store_props(store):
    """The exact Store properties the Senate QML button binds (same source)."""
    return {
        # SenateStage.qml:1877 binds exactly these three Store properties.
        "store_can_create": bool(getattr(
            store, "canCreateSenateProposal", False)),
        "store_can_trigger": bool(getattr(
            store, "canTriggerAIProposer", False)),
        "store_blocked": bool(getattr(store, "senateAiProposerBlocked", False)),
        "store_step": getattr(store, "senateCurrentStep", None),
    }


def _instrument(store):
    counters = probe._counters()
    original_advance = store._adapter.advance_population

    def _advance(viewer_id):
        counters["advance_calls"] += 1
        res = original_advance(viewer_id)
        counters["advance_ok"] = bool(res.get("success"))
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        delivery = data.get("delivery") if isinstance(
            data.get("delivery"), dict) else {}
        counters["advance_api"] = {
            "success": res.get("success"),
            "message": res.get("message"),
            "entry_receipt_present": bool(data.get("entry_receipt")),
            "delivery_outcome": delivery.get("outcome"),
            "delivery_next_controller": (delivery.get("next") or {}).get(
                "controller"),
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

    # The adapter routes by ``api_func.__name__``; a spy must keep the original
    # name or the one-seat continuation scope would deny it.
    functools.update_wrapper(_propose, original_propose)
    functools.update_wrapper(_auto, original_auto)

    senate_api.propose_many = _propose
    senate_api.auto_submit_proposals = _auto
    saved_trace = probe._install_access_trace(counters)

    def restore():
        probe._restore_access_trace(saved_trace)
        senate_api.propose_many = original_propose
        senate_api.auto_submit_proposals = original_auto
        store._adapter.advance_population = original_advance

    return counters, restore


def _core_fingerprint(state):
    """The Core facts ``selectPhase`` must NOT touch (S1-04)."""
    book = getattr(state, "_session_turn_book", None)
    scope = book.scopes.get("senate") if book is not None else None
    executed = getattr(state, "_executed_phases", None)
    results = getattr(state, "_phase_results", None)
    ledger = getattr(state, "_senate_finalization_ledger", None)
    receipts = ledger.get("by_session") if isinstance(ledger, dict) else None
    return {
        "authoritative_phase": probe._safe(
            lambda: probe.session_api._infer_current_phase_id(state)),
        "executed_phases": sorted(executed) if isinstance(executed, (set, list))
        else None,
        "phase_results": sorted(results.keys()) if isinstance(results, dict)
        else None,
        "finalization_receipts": sorted(receipts.keys())
        if isinstance(receipts, dict) else None,
        "book_revision": getattr(book, "revision_counter", None),
        "scope_id": getattr(scope, "scope_id", None),
        "pending_proposals": probe._safe(
            lambda: len(state.get_senate_proposals()), -1),
        "decision_complete": probe._safe(
            lambda: bool(state.senate_proposal_decision_complete), None),
        "package_id": probe._safe(
            lambda: state.get_senate_package_id_for_session(
                "turn-%s" % state.turn.turn_number), None),
    }


def _row(tag, turn, point, rec):
    print("S1_ROW %s" % json.dumps({
        "tag": tag, "turn": turn, "point": point,
        "step": rec.get("current_step"),
        "owner": "%s/%s" % (rec.get("proposed_owner_controller"),
                            rec.get("proposed_owner_player")),
        "can_create": rec.get("can_create"),
        "can_trigger_ai": rec.get("can_trigger_ai"),
        "button": rec.get("button_enabled"),
        "errors": rec.get("readiness_errors"),
        "session_id": rec.get("senate_session_id"),
        "finalization_key": rec.get("senate_finalization_id"),
        "canonical": (rec.get("canonical_finalization") or {}).get("status"),
        "dispatch": rec.get("producer_dispatch_count"),
        "ai_dispatch": rec.get("adapter_ai_producer_calls"),
    }, ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------------------
# The two-year REAL driver
# ---------------------------------------------------------------------------
def _run(tag, scenario, preference, *, stop_after_senate=False):
    """Drive Year 1 (complete) and Year 2 (up to the submit surface).

    ``stop_after_senate=True`` returns right after the Year-1 senate finalization
    (used by the same-year receipt negative control).
    """
    rng_state = random.getstate()
    random.seed(42)
    state = None
    try:
        state, pids = probe._factory(scenario)
        viewer = pids[0]
        store, _witness = probe._store(state, viewer)
        assert session_access.is_hotseat_registered(state) is True
        counters, restore = _instrument(store)
        out = {"tag": tag, "state": state, "store": store, "pids": pids,
               "viewer": viewer, "counters": counters, "turns": {},
               "closes": [], "navigation": None}
        try:
            for turn in (1, 2):
                base_prop = counters["producer_calls"]
                base_ai = counters["ai_producer_calls"]
                chain = probe._entry_chain(store, state)
                if store.seatLifecycle == SEAT_MASKED_PENDING:
                    store.requestTakeover()
                store._refresh_population_view()
                selections = (preference(store, viewer)
                              if callable(preference) else {})
                # PC02W TD-01 (2026-10-23): 逐席位庆典前置（G1 per-actor gate），断言零变更。
                for _pid in pids:
                    state.set_batch_completed(_pid, True)
                pop_fail = probe._play_population(store, selections)
                store._refresh_population_view()
                store._refresh_snapshot()

                p0 = probe._snapshot(state, store, tag, turn, "P0", counters)
                _row(tag, turn, "P0", p0)

                # S1-04 negative control: navigation is not business progress.
                if turn == 1:
                    before = _core_fingerprint(state)
                    store.selectPhase("senate")
                    store._refresh_senate_view()
                    after = _core_fingerprint(state)
                    out["navigation"] = {
                        "before": before, "after": after,
                        "view": dict(getattr(store, "_senate_view", {}) or {}),
                        "selected_phase": getattr(store, "_selected_phase_id", ""),
                    }

                fb = store.doAdvancePopulation()
                if store.seatLifecycle == SEAT_MASKED_PENDING:
                    store.requestTakeover()
                store._refresh_senate_view()
                extra = dict(_store_props(store))
                extra.update({
                    "advance_return_success": bool(fb.get("success")),
                    "advance_return_message": fb.get("message"),
                    "entry_receipt_valid": bool(
                        (counters.get("advance_api") or {}).get(
                            "entry_receipt_present")),
                    "dispatch_since_entry": (counters["producer_calls"]
                                             - base_prop),
                    "ai_dispatch_since_entry": (counters["ai_producer_calls"]
                                                - base_ai),
                    "population_play_failure": (pop_fail.get("message")
                                                if isinstance(pop_fail, dict)
                                                else None),
                })
                p1 = probe._snapshot(state, store, tag, turn, "P1", counters, extra)
                _row(tag, turn, "P1", p1)

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
                extra2 = dict(_store_props(store))
                extra2.update({
                    "submit_return": {
                        "success": submit_fb.get("success"),
                        "message": submit_fb.get("message"),
                        "errors": submit_fb.get("errors"),
                    },
                    "dispatch_since_entry": (counters["producer_calls"]
                                             - base_prop),
                    "ai_dispatch_since_entry": (counters["ai_producer_calls"]
                                                - base_ai),
                    "new_proposal_delta": after_props - before_props,
                    "owner_package_delta": (1 if (after_pkg and not before_pkg)
                                            else 0),
                    "senate_package_id": after_pkg,
                })
                p2 = probe._snapshot(state, store, tag, turn, "P2", counters, extra2)
                _row(tag, turn, "P2", p2)

                out["turns"][turn] = {"P0": p0, "P1": p1, "P2": p2,
                                      "entry_chain": chain,
                                      "submit": submit_fb}

                if stop_after_senate and turn == 1:
                    # The submit continuation already finalized the senate
                    # (P2 canonical=VALID); nothing else is driven here.
                    return out

                if turn == 2:
                    break

                # Year 1 must close through the REAL chain (no force).
                steps = probe._finish_senate(store, state)
                closed = probe._close_year(store, state, pids)
                out["closes"].append(closed)
                print("S1_YEAR_CLOSE %s %s" % (tag, json.dumps(
                    closed, ensure_ascii=False, default=str)))
                assert closed.get("advanced") is True, closed
                assert not closed.get("force_advance_year"), closed
                out["year1_receipts"] = probe._safe(
                    lambda: sorted(state._senate_finalization_ledger[
                        "by_session"].keys()), [])
            return out
        finally:
            restore()
    finally:
        random.setstate(rng_state)


# Module-level cache: each carrier is expensive (real two-year chain) and every
# assertion below is read-only on the produced records/state.
_CACHE = {}


def _carrier(tag, scenario, preference):
    if tag not in _CACHE:
        _CACHE[tag] = _run(tag, scenario, preference)
    return _CACHE[tag]


# ===========================================================================
# S1-01 — 1H2AI / HUMAN consul: Turn2 proposal is submittable (incl. empty batch)
# ===========================================================================
def test_s1_01_human_consul_two_year_chain_submits_turn2():
    run = _carrier("S1-01", probe.SCENARIO_1H2AI, probe._prefer_own_consul)
    t1, t2 = run["turns"][1], run["turns"][2]

    # Turn 1 positive control (unchanged behaviour).
    assert t1["P1"]["current_step"] == "proposal", t1["P1"]["readiness_errors"]
    assert t1["P2"]["submit_return"]["success"] is True
    assert t1["P2"]["owner_package_delta"] == 1
    assert t1["P2"]["canonical_finalization"]["status"] == "VALID"

    # AC-S1-01/02/05 — Year 2 opens a lawful proposal surface for the HUMAN owner.
    assert t2["P1"]["authoritative_current_phase"] == "senate"
    assert t2["P1"]["current_step"] == "proposal", (
        t2["P1"]["current_step"], t2["P1"]["readiness_errors"])
    assert t2["P1"]["readiness_errors"] == []
    assert t2["P1"]["can_create"] is True
    assert t2["P1"]["can_trigger_ai"] is False
    assert t2["P1"]["button_enabled"] is True

    # The derived key must be the CURRENT year, never the frozen one.
    assert t2["P1"]["senate_finalization_id"][1] == "turn-2", \
        t2["P1"]["senate_finalization_id"]
    assert t2["P1"]["canonical_finalization"]["status"] == "ABSENT", \
        t2["P1"]["canonical_finalization"]

    # AC-S1-05 — the real click publishes exactly one owner package (empty batch).
    assert t2["P2"]["submit_return"]["success"] is True, \
        t2["P2"]["submit_return"]
    assert t2["P2"]["owner_package_delta"] == 1
    assert t2["P2"]["new_proposal_delta"] == 0
    assert t2["P2"]["canonical_finalization"]["status"] == "VALID"


# ===========================================================================
# S1-02 — 1H2AI / AI consul: verified HUMAN presenter triggers exactly once
# ===========================================================================
def test_s1_02_ai_consul_presenter_triggers_exactly_once():
    run = _carrier("S1-02", probe.SCENARIO_1H2AI, probe._prefer_foreign_consul)
    t2 = run["turns"][2]
    p1, p2 = t2["P1"], t2["P2"]

    assert p1["proposed_owner_controller"] == "AI", p1["proposed_owner_player"]
    assert p1["current_step"] == "proposal", (
        p1["current_step"], p1["readiness_errors"])
    # The presenter is the verified HUMAN seat (DTO bound to the same viewer).
    assert p1["registered_seat"] is True
    assert p1["dto_viewer_id"] == run["viewer"]
    assert p1["can_create"] is False
    assert p1["can_trigger_ai"] is True

    # AC-S1-02 — zero dispatch in Year 2 before the human gesture.
    assert p1["dispatch_since_entry"] == 0
    assert p1["ai_dispatch_since_entry"] == 0

    # AC-S1-02 — exactly one AI owner dispatch after the single real click.
    assert p2["submit_return"]["success"] is True, p2["submit_return"]
    assert p2["ai_dispatch_since_entry"] == 1
    assert p2["owner_package_delta"] == 1
    # The AI owner published its package and the year moved on to the vote
    # (publication alone is not a finalization; no WRONG receipt may appear).
    assert p2["current_step"] == "senate_vote", p2["current_step"]
    assert p2["canonical_finalization"]["status"] != "WRONG"


# ===========================================================================
# S1-03 — 3H: Year-2 owner follows the REAL seat mapping; others cannot propose
# ===========================================================================
def test_s1_03_three_human_owner_mapping_and_no_proxy():
    run = _carrier("S1-03", probe.SCENARIO_3H, probe._abstain)
    t2 = run["turns"][2]
    p1 = t2["P1"]

    assert p1["proposed_owner_controller"] == "HUMAN"
    assert p1["proposed_owner_player"] == run["pids"][0]
    assert p1["current_step"] == "proposal", (
        p1["current_step"], p1["readiness_errors"])
    assert p1["can_create"] is True

    # Another real human may not inherit the proposal right (typed fail-closed).
    state = run["state"]
    other = run["pids"][1]
    before_props = len(state.get_senate_proposals())
    before_pkg = state.get_senate_package_id_for_session("turn-2")
    resp = probe._api_call(senate_api.get_senate_view, state, other)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    assert data.get("can_create_proposal", False) is False
    assert data.get("can_trigger_ai_proposer", False) is False

    # The negative read did not mutate any proposal/package fact.
    assert len(state.get_senate_proposals()) == before_props
    assert state.get_senate_package_id_for_session("turn-2") == before_pkg


# ===========================================================================
# S1-04 — selectPhase('senate') is navigation only (negative control)
# ===========================================================================
def test_s1_04_selectphase_is_navigation_only():
    run = _carrier("S1-01", probe.SCENARIO_1H2AI, probe._prefer_own_consul)
    nav = run["navigation"]
    assert nav is not None
    assert nav["selected_phase"] == "senate"
    # Zero Core / receipt / ledger mutation.
    assert nav["before"] == nav["after"], {
        "before": nav["before"], "after": nav["after"]}
    assert nav["before"]["authoritative_phase"] == "population"
    # Not actionable: the business phase was never advanced by navigation.
    assert bool(nav["view"].get("actionable", False)) is False
    assert nav["view"].get("current_step") != "results"


# ===========================================================================
# S1-05 — fail-closed: corrupted same-year receipt / old-year receipt / stale viewer
# ===========================================================================
def test_s1_05_same_year_receipt_corruption_is_fail_closed():
    run = _run("S1-05", probe.SCENARIO_1H2AI, probe._prefer_own_consul,
               stop_after_senate=True)
    state = run["state"]
    counters = run["counters"]

    key = senate_api.senate_finalization_id(state)
    assert key[1] == "turn-1", key
    assert state.has_senate_finalization_receipt("turn-1") is True
    assert senate_api.canonical_finalization(state)["status"] == "VALID"

    # Same-year idempotent replay (AC-S1-04) before corruption.
    replay = probe._api_call(senate_api.finalize_senate_if_ready, state)
    assert replay.get("success") is True
    assert (replay.get("data") or {}).get("replayed") is True

    ledger = state._senate_finalization_ledger
    stored = dict(ledger["receipts"][ledger["by_session"]["turn-1"]])
    before_dispatch = (counters["producer_calls"] +
                       counters["ai_producer_calls"])
    before_result = json.dumps(state.get_phase_result("senate"),
                               sort_keys=True, default=str)
    ledger["receipts"][ledger["by_session"]["turn-1"]][
        "content_fingerprint"] = "0" * 64
    try:
        # AC-S1-03 — a same-year mismatch stays WRONG (fail-closed).
        canon = senate_api.canonical_finalization(state)
        assert canon["status"] == "WRONG", canon
        assert canon["stage"] == "content_fingerprint", canon

        first = probe._api_call(senate_api.finalize_senate_if_ready, state)
        second = probe._api_call(senate_api.finalize_senate_if_ready, state)
        assert first.get("success") is not True
        assert second.get("success") is not True
        assert first.get("data", {}).get("receipt_mismatch", {}).get(
            "status") == "WRONG"
        # Zero dispatch and zero replay/re-mint.
        assert (counters["producer_calls"] +
                counters["ai_producer_calls"]) == before_dispatch
        assert ledger["receipts"][ledger["by_session"]["turn-1"]][
            "content_fingerprint"] == "0" * 64
        assert json.dumps(state.get_phase_result("senate"), sort_keys=True,
                          default=str) == before_result
    finally:
        ledger["receipts"][ledger["by_session"]["turn-1"]] = stored


def test_s1_05b_old_year_receipt_does_not_leak_into_new_year():
    run = _carrier("S1-01", probe.SCENARIO_1H2AI, probe._prefer_own_consul)
    state = run["state"]
    t2 = run["turns"][2]

    # The old-year receipt survives (its own-year idempotency is not deleted)...
    assert "turn-1" in (run.get("year1_receipts") or [])
    # ...but it neither backs nor blocks the NEW year's capability.
    assert t2["P1"]["senate_finalization_id"][1] == "turn-2"
    assert t2["P1"]["canonical_finalization"]["status"] == "ABSENT"
    assert t2["P1"]["canonical_with_current_turn_key"]["status"] == "ABSENT"
    assert t2["P1"]["current_step"] == "proposal"

    # Stale (non-owning) viewer read: no capability, no dispatch.
    before = (run["counters"]["producer_calls"],
              run["counters"]["ai_producer_calls"])
    other = run["pids"][1]
    resp = probe._api_call(senate_api.get_senate_view, state, other)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    assert data.get("can_create_proposal", False) is False
    assert data.get("can_trigger_ai_proposer", False) is False
    assert (run["counters"]["producer_calls"],
            run["counters"]["ai_producer_calls"]) == before


# ===========================================================================
# S1-06 — button state is the DTO/Store predicate (never hard-enabled)
# ===========================================================================
def test_s1_06_button_state_is_same_source_as_dto():
    for tag, scenario, preference in (
            ("S1-01", probe.SCENARIO_1H2AI, probe._prefer_own_consul),
            ("S1-02", probe.SCENARIO_1H2AI, probe._prefer_foreign_consul),
            ("S1-03", probe.SCENARIO_3H, probe._abstain)):
        run = _carrier(tag, scenario, preference)
        for turn, points in run["turns"].items():
            for point in ("P1", "P2"):
                rec = points[point]
                store_predicate = (
                    (rec["store_can_create"] or rec["store_can_trigger"])
                    and not rec["store_blocked"])
                assert store_predicate == rec["button_enabled"], (
                    tag, turn, point, rec["store_can_create"],
                    rec["store_can_trigger"], rec["store_blocked"],
                    rec["button_enabled"])
                # Capability and DTO agree one-to-one.
                assert rec["store_can_create"] == rec["can_create"]
                assert rec["store_can_trigger"] == rec["can_trigger_ai"]
                # Outside the proposal step no capability may exist (no hard-open).
                if rec["current_step"] != "proposal":
                    assert rec["can_create"] is False
                    assert rec["can_trigger_ai"] is False
                    assert rec["button_enabled"] is False
