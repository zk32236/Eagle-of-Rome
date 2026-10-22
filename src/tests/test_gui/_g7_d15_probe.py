"""G7 / D15 — instrumented PROBE (test-face only): which fail-closed branch of
``GuiSessionStore._settle_seat_after_success`` is taken after a Population
resolution ("last HUMAN completes -> resolve_slice") stalls the seat handoff.

WHY THIS FILE EXISTS
--------------------
``03-da-evidence/D7D12-W3/G7-D15-AB/02-Gate-Break-Analysis.md`` proved (code +
runtime logs) that the D15 stall is a fail-closed silence inside the SETTLE gate
and narrowed it to four branches (S-a..S-d), but none of them logs anything
(they all end in ``_fail_masked``, which has no ``logger`` call). This probe
therefore OBSERVES the real transaction from the test side only:

* the Store, the Adapter, the API boundary, the Core ledger, the masked
  seat-transition machine and the delivery validator are the PRODUCTION ones;
* every wrapper below is installed by ``monkeypatch`` on the test process and is
  removed at test teardown -- not one product byte is read-modified-written;
* the existing W3 test files (``test_w3_senate_turns.py`` /
  ``test_w3_delivery_authority.py`` / ``test_w3_guards.py`` / ``_w3_real_gate.py``)
  are imported/consulted for their PRODUCTION scaffolding shapes; none of them is
  edited, and no assertion of theirs is touched.

OBSERVED SEAMS (read-only instrumentation)
------------------------------------------
* ``_settle_seat_after_success`` entry: ``delivery`` presence, ``outcome``,
  ``next`` / ``terminal``, viewer, Core current, and an independent
  ``validate_delivery_result`` verdict computed on the SAME envelope;
* ``_delivery_fail``: the typed ``{code, stage, committed, detail}`` that selects
  S-a / S-b / S-c;
* ``_activate_seat``: same-seat success path (proves the gate was NOT failed);
* ``_handoff_failure_feedback`` / ``_masked_business_rejection`` / ``_fail_masked``:
  the remaining terminal routes (incl. the S-d pending-witness half);
* Adapter dispatch: ``resolve_election`` (== ``resolve_slice``) vs ``next_player``;
* ``retryHandoff``: the early-exit reason the overlay's 「重试」 really gets.

EVIDENCE LEVEL
--------------
``REAL_TXN_NO_WINDOW``: real registered hot-seat session, real masked owning
transaction, real Adapter/API/Core, real delivery validator and the real
production barrier WITNESS (``_Witness``: the same synchronous witness the W3
chains use). No application QML shell / ``QQuickWindow`` is constructed -- the
D15 break is at the SETTLE gate (post-dispatch, pre-frame), so a frame tier would
not change which branch is taken. The label is deliberately the weaker one.
"""
import json
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import population_api, session_access, session_api, session_turn_service
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import ClassTier, Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVATE,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

EVIDENCE_LEVEL = "REAL_TXN_NO_WINDOW"

EVIDENCE_DIR = os.environ.get(
    "G7_D15_EVIDENCE_DIR",
    "/mnt/e/OpenClaw/Projects/EOR/workspace/"
    "EOR20261013-02 GUI-Readiness/03-da-evidence/D7D12-W3/G7-D15-Probe",
)

_PLAYER_SPECS = (
    ("player1", "optimates"),
    ("player2", "populares"),
    ("player3", "equites"),
)

_RESULTS = []


# ---------------------------------------------------------------------------
# Production-shaped fixture state (same construction the W3 chains use)
# ---------------------------------------------------------------------------
def _make_state(human_ids, *, viewer, pre_resolved=True, mark_all=True):
    """Registered hot-seat at the population RESOLVED boundary.

    All HUMAN population ballots are complete by construction: with no election
    candidates the frozen predicate ``_all_human_population_votes_complete`` is
    vacuously true, so ``doCompletePlayer`` takes the LAST-HUMAN branch
    (``lease_command == "resolve_population_slice"``). The phase result is
    already recorded, i.e. the resolver's idempotent branch emits the SAME
    viewer-bound ``_resolved_delivery()`` envelope the first (mutating) resolve
    emits -- the envelope producer is the identical helper either way.
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ("mortality", "revenue", "forum"):
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

    for player_id, faction_id in _PLAYER_SPECS:
        state.add_player(Player(
            player_id=player_id, faction_id=faction_id,
            player_type=(PlayerType.HUMAN if player_id in human_ids
                         else PlayerType.AI)))
    state._turn_order = [player_id for player_id, _ in _PLAYER_SPECS]
    state.set_current_player(viewer)

    contract = state.create_contract(
        ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
    contract.status = ContractStatus.PENDING

    # Every HUMAN has really voted for every office that has candidates, so the
    # FROZEN predicate ``_all_human_population_votes_complete`` is TRUE and
    # ``doCompletePlayer`` takes the LAST-HUMAN branch (resolve_slice). The vote
    # rows are recorded on the real Core book (no predicate is monkeypatched).
    candidates = population_api._get_candidates_impl(state)
    rows_by_office = (candidates.get("data") or {}) \
        if candidates.get("success") else {}
    for player_id in human_ids:
        for office, rows in rows_by_office.items():
            if rows:
                state.record_population_vote(
                    player_id, office, rows[0]["id"], replace=True)

    if pre_resolved:
        state.record_phase_result("population", {
            "success": True, "message": "Election resolved",
            "data": {"election_results": []},
        })
    else:
        # The readiness predicate (stricter than the HUMAN-completion one) also
        # looks at each seat's vote-completion mark.
        # PROBE-2: ``mark_all=False`` leaves the AI seats UNMARKED (the only shape
        # in which the population AI drain can still have work to do). The default
        # keeps probe-1's construction byte-for-byte.
        for player_id, _faction in _PLAYER_SPECS:
            if mark_all or player_id in human_ids:
                state.set_vote_completed(player_id, True)
    session_access.register_hotseat_session(state, viewer, epoch=0)
    return state


class _Witness:
    """The production synchronous barrier witness (same shape as the W3 chains)."""

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


class _Receiver:
    """The real Query receiver obligation (acks every invalidation)."""

    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


def _store(state, viewer):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _Witness()
    store.setHandoffBarrierProvider(witness)
    store._viewer_id = viewer
    store._seat_lifecycle = SEAT_ACTIVE
    return store, witness


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------
def _delivery_snapshot(store, delivery):
    """Everything the settle gate decides on -- plus an independent verdict."""
    current = None
    try:
        current = store._state.get_current_player().player_id
    except Exception:                                # pragma: no cover - defensive
        current = None
    verdict = None
    if isinstance(delivery, dict):
        try:
            verdict = session_turn_service.validate_delivery_result(
                store._state, delivery, viewer_id=store._viewer_id)
        except Exception as exc:                     # pragma: no cover - defensive
            verdict = {"ok": None,
                       "error": {"code": "PROBE_VALIDATOR_EXCEPTION",
                                 "stage": "probe", "detail": str(exc)}}
    envelope = delivery if isinstance(delivery, dict) else {}
    return {
        "delivery_present": isinstance(delivery, dict),
        "outcome": envelope.get("outcome"),
        "next": envelope.get("next"),
        "terminal": envelope.get("terminal"),
        "version": envelope.get("version"),
        "scope_id": envelope.get("scope_id"),
        "keys": sorted(envelope.keys()),
        "viewer": store._viewer_id,
        "core_current": current,
        "verdict_ok": (verdict or {}).get("ok"),
        "verdict_error": (verdict or {}).get("error"),
    }


class _Trace:
    def __init__(self, store, label):
        self.store = store
        self.label = label
        self.settle = []
        self.delivery_fail = []
        self.activate = []
        self.failure_feedback = []
        self.business_rejection = []
        self.fail_masked = []
        self.dispatch = []
        self.votes_complete = None
        self.perturb = None
        self.retry = None
        self.feedback = None
        self.lifecycle_after = ""
        self.last_delivery_after = None


def _install(monkeypatch, trace):
    """Install read-only wrappers on the CLASS / the adapter instance."""
    store = trace.store

    original_settle = GuiSessionStore._settle_seat_after_success
    original_delivery_fail = GuiSessionStore._delivery_fail
    original_activate = GuiSessionStore._activate_seat
    original_failure_feedback = GuiSessionStore._handoff_failure_feedback
    original_business = GuiSessionStore._masked_business_rejection
    original_fail_masked = GuiSessionStore._fail_masked
    original_retry = GuiSessionStore.retryHandoff

    def settle(self, txn_id, next_actor_id=None, done=None, delivery=None,
               legacy=None):
        snap = _delivery_snapshot(self, delivery)
        row = {"txn_id": txn_id, "next_actor_id": next_actor_id,
               "legacy_present": isinstance(legacy, dict),
               "legacy_keys": sorted(legacy.keys()) if isinstance(legacy, dict)
               else [], "lifecycle_before": self._seat_lifecycle,
               "delivery_required_command_at_settle":
                   self._delivery_required_command,
               "command_id_at_settle":
                   (self._seat_txn or {}).get("command_id", ""),
               "seat_txn_target_at_settle":
                   (self._seat_txn or {}).get("target_id", "")}
        row.update(snap)
        trace.settle.append(row)
        if trace.perturb is not None:
            trace.perturb(self)
            row["perturbed"] = True
        try:
            result = original_settle(
                self, txn_id, next_actor_id=next_actor_id, done=done,
                delivery=delivery, legacy=legacy)
        finally:
            row["lifecycle_after"] = self._seat_lifecycle
            row["last_delivery_recorded"] = bool(self._last_delivery)
        row["result_success"] = (result or {}).get("success")
        return result

    def delivery_fail(self, txn_id, err, done=None):
        record = err if isinstance(err, dict) else {}
        trace.delivery_fail.append({
            "txn_id": txn_id,
            "code": str(record.get("code") or ""),
            "stage": str(record.get("stage") or ""),
            "committed": record.get("committed", "<omitted>"),
            "detail": record.get("detail", ""),
            "raw_keys": sorted(record.keys()),
        })
        return original_delivery_fail(self, txn_id, err, done=done)

    def activate(self, txn_id, target_id, same_seat=False, done=None,
                 commit_proven=True):
        trace.activate.append({"txn_id": txn_id, "target_id": target_id,
                               "same_seat": bool(same_seat),
                               "commit_proven": commit_proven})
        return original_activate(self, txn_id, target_id, same_seat=same_seat,
                                 done=done, commit_proven=commit_proven)

    def failure_feedback(self, delivery_error=None):
        record = delivery_error if isinstance(delivery_error, dict) else {}
        trace.failure_feedback.append({
            "delivery_error": record or None,
            "code": str(record.get("code") or ""),
            "stage": str(record.get("stage") or ""),
            "pending_player_id": self._pending_player_id,
            "failure_kind": self._handoff_failure_kind,
        })
        return original_failure_feedback(self, delivery_error=delivery_error)

    def business_rejection(self, txn_id, feedback, done=None):
        data = (feedback or {}).get("data") if isinstance(feedback, dict) else None
        errors = (feedback or {}).get("errors") if isinstance(feedback, dict) else None
        trace.business_rejection.append({
            "txn_id": txn_id,
            "success": (feedback or {}).get("success"),
            "message": (feedback or {}).get("message"),
            "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
            "errors": errors if isinstance(errors, list) else errors,
        })
        return original_business(self, txn_id, feedback, done=done)

    def fail_masked(self, kind, txn_id="", route=None):
        entry = {"kind": kind, "txn_id": txn_id,
                 "lifecycle_before": self._seat_lifecycle}
        if route is None:
            result = original_fail_masked(self, kind, txn_id)
        else:
            entry["route"] = route
            result = original_fail_masked(self, kind, txn_id, route=route)
        entry["lifecycle_after"] = self._seat_lifecycle
        entry["failure_kind"] = self._handoff_failure_kind
        entry["failure_route"] = self._handoff_failure_route
        trace.fail_masked.append(entry)
        return result

    def retry(self):
        result = original_retry(self)
        trace.retry = result
        return result

    monkeypatch.setattr(GuiSessionStore, "_settle_seat_after_success", settle)
    monkeypatch.setattr(GuiSessionStore, "_delivery_fail", delivery_fail)
    monkeypatch.setattr(GuiSessionStore, "_activate_seat", activate)
    monkeypatch.setattr(GuiSessionStore, "_handoff_failure_feedback",
                        failure_feedback)
    monkeypatch.setattr(GuiSessionStore, "_masked_business_rejection",
                        business_rejection)
    monkeypatch.setattr(GuiSessionStore, "_fail_masked", fail_masked)
    monkeypatch.setattr(GuiSessionStore, "retryHandoff", retry)

    adapter = store._adapter

    original_resolve = adapter.resolve_election
    original_next = adapter.next_player
    original_advance = adapter.advance_population
    original_votes = adapter.all_human_population_votes_complete

    def resolve_election(*args, **kwargs):
        trace.dispatch.append("resolve_slice")
        return original_resolve(*args, **kwargs)

    def next_player(*args, **kwargs):
        trace.dispatch.append("next_player")
        return original_next(*args, **kwargs)

    def advance_population(*args, **kwargs):
        trace.dispatch.append("advance")
        return original_advance(*args, **kwargs)

    def votes_complete(*args, **kwargs):
        value = original_votes(*args, **kwargs)
        trace.votes_complete = bool(value)
        return value

    monkeypatch.setattr(adapter, "resolve_election", resolve_election)
    monkeypatch.setattr(adapter, "next_player", next_player)
    monkeypatch.setattr(adapter, "advance_population", advance_population)
    monkeypatch.setattr(adapter, "all_human_population_votes_complete",
                        votes_complete)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def _classify(trace):
    """Map the observed seams onto S-a / S-b / S-c / S-d / NONE / MULTIPLE."""
    if trace.business_rejection:
        return "NONE", "business rejection before the settle gate"
    branches = set()
    for row in trace.delivery_fail:
        code, stage = row["code"], row["stage"]
        if code == session_turn_service.DELIVERY_MISSING_RECEIVER \
                and stage == "settle":
            branches.add("S-b")
        elif code == session_turn_service.DELIVERY_INVALID \
                and stage == "terminal":
            branches.add("S-c")
        elif code == session_turn_service.DELIVERY_MISMATCH \
                and stage == "target_faction":
            branches.add("S-d")
        elif code == session_turn_service.DELIVERY_MISSING_RECEIVER:
            # Producer-side typed refusal carried ON the envelope (stage=receiver):
            # the settle gate rejects a delivered-but-receiverless envelope, which
            # is the S-a validation half.
            branches.add("S-a")
        else:
            branches.add("S-a")
    # S-d (second half): pending witness refused AFTER the target was accepted.
    for entry in trace.fail_masked:
        if entry.get("pending_player_id") and not trace.delivery_fail:
            branches.add("S-d")
    if len(branches) > 1:
        return "MULTIPLE", "more than one fail-closed branch observed"
    if branches:
        branch = branches.pop()
        return branch, {
            "S-a": "delivery envelope present but validate_delivery_result refused",
            "S-b": "no usable receiver at settle (delivery missing / no next.actor)",
            "S-c": "RESOLVED envelope whose next controller is AI (not a seat)",
            "S-d": "target has no real faction / pending witness refused",
        }[branch]
    if any(row["same_seat"] for row in trace.activate):
        return "NONE", "same-seat activation path (no _delivery_fail)"
    if trace.lifecycle_after == SEAT_MASKED_FAILURE:
        return "NONE", "masked failure outside the four settle branches"
    if trace.lifecycle_after == SEAT_MASKED_PENDING:
        return "NONE", "cross-seat pending (handoff to another seat)"
    return "NONE", "no fail-closed branch observed"


def _run(monkeypatch, label, human_ids, viewer, *, pre_resolved=True,
         slot="doCompletePlayer", perturb=None, synthetic=False):
    state = _make_state(human_ids, viewer=viewer, pre_resolved=pre_resolved)
    store, witness = _store(state, viewer)
    trace = _Trace(store, label)
    trace.perturb = perturb
    _install(monkeypatch, trace)

    feedback = getattr(store, slot)()
    trace.feedback = feedback
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)

    if store._seat_lifecycle == SEAT_MASKED_FAILURE:
        trace.retry = store.retryHandoff()
        trace.lifecycle_after = store._seat_lifecycle

    branch, trigger = _classify(trace)

    settle = trace.settle[0] if trace.settle else {}
    record = {
        "label": label,
        "scenario": {"human_ids": list(human_ids), "viewer": viewer,
                     "players": len(_PLAYER_SPECS),
                     "phase_pre_resolved": pre_resolved, "slot": slot,
                     "synthetic_perturbation": bool(synthetic)},
        "evidence_level": EVIDENCE_LEVEL,
        "votes_complete": trace.votes_complete,
        "dispatch": trace.dispatch,
        "lease_command": (store._seat_txn or {}).get("command_id", ""),
        "delivery_required_command": store._delivery_required_command,
        "reached_settle": bool(trace.settle),
        "settle_entry": settle,
        "delivery_fail": trace.delivery_fail,
        "activate": trace.activate,
        "failure_feedback": trace.failure_feedback,
        "business_rejection": trace.business_rejection,
        "fail_masked": trace.fail_masked,
        "branch": branch,
        "trigger": trigger,
        "lifecycle_final": store._seat_lifecycle,
        "last_delivery_recorded": trace.last_delivery_after,
        "seat_txn": dict(store._seat_txn) if isinstance(store._seat_txn, dict)
        else None,
        "retry": trace.retry,
        "witness_calls": witness.calls,
        "feedback": feedback,
    }
    _RESULTS.append(record)
    _emit(record)
    return record


def _emit(record):
    settle = record["settle_entry"]
    first_fail = record["delivery_fail"][0] if record["delivery_fail"] else {}
    retry = record["retry"] or {}
    print("G7_D15_PROBE label=%s level=%s reached_settle=%s dispatch=%s "
          "delivery_present=%s outcome=%s next_actor=%s next_controller=%s "
          "branch=%s fail_code=%s fail_stage=%s retry_reason=%s "
          "lifecycle=%s"
          % (record["label"], record["evidence_level"],
             record["reached_settle"], ",".join(record["dispatch"]) or "-",
             settle.get("delivery_present"), settle.get("outcome"),
             ((settle.get("next") or {}) or {}).get("actor_player_id"),
             ((settle.get("next") or {}) or {}).get("controller"),
             record["branch"], first_fail.get("code", "-"),
             first_fail.get("stage", "-"), retry.get("reason", "-"),
             record["lifecycle_final"]))
    try:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        path = os.path.join(EVIDENCE_DIR, "probe-%s.json" % record["label"])
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2,
                      default=str)
        print("G7_D15_PROBE_EVIDENCE path=%s" % path)
    except Exception as exc:                          # pragma: no cover - defensive
        print("G7_D15_PROBE_EVIDENCE_FAILED label=%s error=%s"
              % (record["label"], exc))


@pytest.fixture(scope="module", autouse=True)
def _write_summary():
    yield
    if not _RESULTS:
        return
    summary = {
        "task": "EOR20261013-02 / G7-W3-D15-Handoff-Stall",
        "probe": "_g7_d15_probe.py",
        "evidence_level": EVIDENCE_LEVEL,
        "rows": [{key: row[key] for key in
                  ("label", "branch", "trigger", "reached_settle", "dispatch",
                   "lifecycle_final")} for row in _RESULTS],
    }
    try:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        path = os.path.join(EVIDENCE_DIR, "probe-summary.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2,
                      default=str)
        print("G7_D15_PROBE_SUMMARY path=%s" % path)
    except Exception as exc:                          # pragma: no cover - defensive
        print("G7_D15_PROBE_SUMMARY_FAILED error=%s" % exc)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def test_g7_d15_probe_1h2ai_last_human_resolution(monkeypatch):
    """1 HUMAN + 2 AI: the single HUMAN is the last completer -> resolve_slice."""
    record = _run(monkeypatch, "1h2ai", ("player1",), "player1")
    assert record["reached_settle"] is True, (
        "probe validity: the settle gate must be reached; observed=%r"
        % (record["lifecycle_final"],))
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE", "NONE")


def test_g7_d15_probe_3h_last_human_resolution(monkeypatch):
    """3 HUMAN: player3 is the LAST completer (current + viewer) -> resolve_slice."""
    record = _run(monkeypatch, "3h", ("player1", "player2", "player3"),
                  "player3")
    assert record["reached_settle"] is True, (
        "probe validity: the settle gate must be reached; observed=%r"
        % (record["lifecycle_final"],))
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE", "NONE")


def test_g7_d15_probe_1h2ai_fresh_resolution(monkeypatch):
    """1 HUMAN + 2 AI, FIRST (mutating) resolve -- the production fact pattern."""
    record = _run(monkeypatch, "1h2ai-fresh", ("player1",), "player1",
                  pre_resolved=False)
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE", "NONE")


def test_g7_d15_probe_3h_fresh_resolution(monkeypatch):
    """3 HUMAN, FIRST (mutating) resolve, player3 last -- production fact pattern."""
    record = _run(monkeypatch, "3h-fresh", ("player1", "player2", "player3"),
                  "player3", pre_resolved=False)
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE", "NONE")


def test_g7_d15_probe_advance_population_entry(monkeypatch):
    """The phase-ENTRY slot (``advancePopulation``) -- its own envelope (W-01)."""
    record = _run(monkeypatch, "advance-entry", ("player1",), "player1",
                  pre_resolved=True, slot="doAdvancePopulation")
    assert record["reached_settle"] is True, (
        "probe validity: the settle gate must be reached; observed=%r"
        % (record["lifecycle_final"],))
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE", "NONE")


def _perturb_core_advances_to_ai(store):
    """SYNTHETIC: move the Core current player between the producer (which built
    the viewer-bound RESOLVED envelope) and the settle gate that validates it.

    This is NOT a claim about the production run: it is the controlled condition
    sweep that proves (a) the probe's classifier really fires and (b) exactly
    which fact flips the settle gate into a silent fail-closed branch. Every
    other element of the transaction is the production one.
    """
    store._state.set_current_player("player2")       # an AI seat


def test_g7_d15_probe_synthetic_core_advance(monkeypatch):
    """Condition sweep: Core advances to an AI seat before settle -> which branch?"""
    record = _run(monkeypatch, "synthetic-core-ai", ("player1",), "player1",
                  pre_resolved=True, perturb=_perturb_core_advances_to_ai,
                  synthetic=True)
    assert record["reached_settle"] is True
    assert record["branch"] in ("S-a", "S-b", "S-c", "S-d", "MULTIPLE"), (
        "the synthetic condition must really flip the settle gate: %r"
        % (record["branch"],))


# ===========================================================================
# PROBE 2 (2026-10-23) — PRODUCTION WRITER HUNT (no Core injection)
# ---------------------------------------------------------------------------
# Question: on the REAL production entry points, WITHOUT injecting any Core
# change, can "envelope actor != Core current at settle" be reproduced?
#
# Every scenario below drives the PRODUCTION Store / Adapter / API / Core:
#   * no ``set_current_player`` call is made by THIS file (it is only WATCHED);
#   * no turn / receipt / delivery field is hand-filled;
#   * the only test-side wiring is read-only observation plus, for P-B3, a
#     signal handler that submits a SECOND real owning command (a production-
#     visible action a QML double-click could perform).
#
# The decisive instrument is ordering, not opinion: every Core cursor write is
# stamped with how many delivery envelopes had already been built and how many
# settle gates had already run. A write inside the divergence window is
# ``envelopes_built >= 1 and settles == 0``.
#
# Probe-1 tests / helpers above are untouched; ``_make_state`` gained one
# default-true keyword so probe-1 keeps its exact construction.
# ===========================================================================
PROBE2_EVIDENCE_DIR = os.environ.get(
    "G7_D15_PROBE2_EVIDENCE_DIR",
    "/mnt/e/OpenClaw/Projects/EOR/workspace/"
    "EOR20261013-02 GUI-Readiness/03-da-evidence/D7D12-W3/G7-D15-Probe2",
)

_P2_RESULTS = []
_ORIG_VALIDATE = session_turn_service.validate_delivery_result
_ORIG_DELIVERY_FOR_ACTOR = session_turn_service.delivery_for_actor


def _p2_current(state):
    try:
        return getattr(state.get_current_player(), "player_id", None)
    except Exception:                                # pragma: no cover - defensive
        return None


def _p2_turn(state):
    try:
        return state.turn.turn_number
    except Exception:                                # pragma: no cover - defensive
        return None


class _P2Trace(_Trace):
    """Probe-1 trace + the probe-2 ordering ledger (same attribute surface, so
    ``_install`` and ``_classify`` are reused unchanged)."""

    def __init__(self, store, label):
        _Trace.__init__(self, store, label)
        self.path_id = ""
        self.core_series = []
        self.core_writes = []
        self.envelopes = []
        self.drains = []
        self.elections = []
        self.refreshes = []
        self.payloads = []
        self.stale_delivery = None
        self.stale_at_consumer = []

    def mark(self, store, tag):
        self.core_series.append({
            "tag": tag,
            "core_current": _p2_current(store._state),
            "turn": _p2_turn(store._state),
            "lifecycle": store._seat_lifecycle,
            "dispatches": len(self.dispatch),
            "envelopes_built": len(self.envelopes),
            "settles": len(self.settle),
        })


def _install_p2(monkeypatch, trace):
    """Observe the PRODUCTION seams that could write the Core cursor or build /
    consume a delivery envelope. Nothing here writes product state."""
    store = trace.store
    state = store._state
    adapter = store._adapter

    original_set_current = GameState.set_current_player

    def set_current(self, player_id, *args, **kwargs):
        frames = []
        for frame in traceback.extract_stack()[:-1]:
            if os.path.abspath(frame.filename) == os.path.abspath(__file__):
                continue
            frames.append("%s:%s:%s" % (os.path.basename(frame.filename),
                                        frame.lineno, frame.name))
        trace.core_writes.append({
            "value": str(player_id),
            "stack": frames[-6:],
            "envelopes_built": len(trace.envelopes),
            "dispatches": len(trace.dispatch),
            "settles": len(trace.settle),
            "in_divergence_window": bool(len(trace.envelopes) >= 1
                                         and not trace.settle),
        })
        return original_set_current(self, player_id, *args, **kwargs)

    def delivery_for_actor(*args, **kwargs):
        result = _ORIG_DELIVERY_FOR_ACTOR(*args, **kwargs)
        owner_state = args[0] if args else kwargs.get("state")
        phase = args[1] if len(args) > 1 else kwargs.get("phase")
        actor = args[2] if len(args) > 2 else kwargs.get("actor")
        nxt = (result or {}).get("next") or {}
        trace.envelopes.append({
            "phase": phase,
            "actor": actor,
            "viewer": kwargs.get("viewer_id"),
            "outcome": (result or {}).get("outcome"),
            "controller": nxt.get("controller"),
            "next_actor": nxt.get("actor_player_id"),
            "scope_id": (result or {}).get("scope_id"),
            "core_current_at_build": _p2_current(owner_state),
            "turn_at_build": _p2_turn(owner_state),
        })
        return result

    original_drain = session_api._drain_ai_population_turns

    def drain(drain_state, auto, **kwargs):
        before = _p2_current(drain_state)
        result = original_drain(drain_state, auto, **kwargs)
        data = result.get("data") or {}
        trace.drains.append({
            "before": before,
            "after": _p2_current(drain_state),
            "success": result.get("success"),
            "reason_code": data.get("reason_code", ""),
            "processed": list(data.get("processed_players") or []),
        })
        return result

    original_resolve_election = population_api.resolve_election

    def resolve_election(election_state, **kwargs):
        before = _p2_current(election_state)
        result = original_resolve_election(election_state, **kwargs)
        data = result.get("data") or {}
        trace.elections.append({
            "before": before,
            "after": _p2_current(election_state),
            "success": result.get("success"),
            "elected": list(data.get("elected") or []),
            "offices": [row.get("office")
                        for row in (data.get("election_results") or [])],
        })
        return result

    # The adapter captured the BOUND ``_on_refresh`` at construction, so the
    # callback is wrapped on the instance (it still calls the real method).
    original_refresh = adapter._refresh_callback

    def refresh():
        trace.refreshes.append({
            "lifecycle": store._seat_lifecycle,
            "dispatches": len(trace.dispatch),
            "settles": len(trace.settle),
            "deferred_flag_before": bool(store._deferred_public_refresh),
        })
        return original_refresh()

    # Outer wrapper: keep the raw envelope the settle gate is really handed.
    original_settle = GuiSessionStore._settle_seat_after_success

    def settle(self, txn_id, next_actor_id=None, done=None, delivery=None,
               legacy=None):
        trace.payloads.append(delivery)
        return original_settle(self, txn_id, next_actor_id=next_actor_id,
                               done=done, delivery=delivery, legacy=legacy)

    monkeypatch.setattr(GameState, "set_current_player", set_current)
    monkeypatch.setattr(session_turn_service, "delivery_for_actor",
                        delivery_for_actor)
    monkeypatch.setattr(session_api, "_drain_ai_population_turns", drain)
    monkeypatch.setattr(population_api, "resolve_election", resolve_election)
    monkeypatch.setattr(adapter, "_refresh_callback", refresh)
    monkeypatch.setattr(GuiSessionStore, "_settle_seat_after_success", settle)
    trace._state_ref = state


def _p2_setup(monkeypatch, label, human_ids, viewer, *, pre_resolved=True,
              mark_all=True):
    state = _make_state(human_ids, viewer=viewer, pre_resolved=pre_resolved,
                        mark_all=mark_all)
    store, witness = _store(state, viewer)
    trace = _P2Trace(store, label)
    _install(monkeypatch, trace)
    _install_p2(monkeypatch, trace)
    trace.core_writes.clear()
    return state, store, witness, trace


def _p2_stale_probe(trace):
    """Runs at a NEW transaction's settle entry: validates the PREVIOUS
    transaction's real envelope (read-only) to show WHICH stage refuses it."""

    def _probe(store):
        if trace.stale_delivery is None:
            return
        verdict = _ORIG_VALIDATE(store._state, trace.stale_delivery,
                                 viewer_id=store._viewer_id)
        trace.stale_at_consumer.append({
            "at": "settle_entry",
            "txn_id": (store._seat_txn or {}).get("txn_id", ""),
            "ok": verdict.get("ok"),
            "error": verdict.get("error"),
            "core_current": _p2_current(store._state),
            "envelope_actor": ((trace.stale_delivery.get("next") or {})
                               .get("actor_player_id")),
            "envelope_scope": trace.stale_delivery.get("scope_id"),
        })
        trace.stale_delivery = None

    return _probe


def _p2_emit(record):
    settle = record["settle_entry"] or {}
    print("G7_D15_PROBE2 path=%s label=%s dispatch=%s reached_settle=%s "
          "envelope_actor=%s core_current=%s controller=%s outcome=%s "
          "validate_ok=%s branch=%s core_writes=%s in_window=%s"
          % (record["path"], record["label"],
             ",".join(record["dispatch"]) or "-",
             record["reached_settle"], record["envelope_actor"],
             record["core_current"], record["controller"], record["outcome"],
             record["validate"]["ok"], record["branch"],
             len(record["core_writes"]),
             record["writes_in_divergence_window"]))
    try:
        os.makedirs(PROBE2_EVIDENCE_DIR, exist_ok=True)
        path = os.path.join(PROBE2_EVIDENCE_DIR,
                            "probe2-%s.json" % record["label"])
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2,
                      default=str)
        print("G7_D15_PROBE2_EVIDENCE path=%s" % path)
    except Exception as exc:                          # pragma: no cover - defensive
        print("G7_D15_PROBE2_EVIDENCE_FAILED label=%s error=%s"
              % (record["label"], exc))


def _p2_finish(trace, label, request, extra=None):
    branch, trigger = _classify(trace)
    settle = trace.settle[-1] if trace.settle else {}
    nxt = (settle.get("next") or {}) if isinstance(settle.get("next"), dict) \
        else {}
    in_window = [row for row in trace.core_writes
                 if row.get("in_divergence_window")]
    record = {
        "probe": 2,
        "task": "EOR20261013-02 / G7-W3-D15-Handoff-Stall",
        "path": trace.path_id,
        "label": label,
        "request": request,
        "evidence_level": "REAL_TXN_NO_WINDOW",
        "dispatch": list(trace.dispatch),
        "reached_settle": bool(trace.settle),
        "settle_entry": settle,
        "envelope_actor": nxt.get("actor_player_id"),
        "core_current": settle.get("core_current"),
        "outcome": settle.get("outcome"),
        "controller": nxt.get("controller"),
        "command_id": settle.get("command_id_at_settle"),
        "validate": {"ok": settle.get("verdict_ok"),
                     "error": settle.get("verdict_error")},
        "branch": branch,
        "trigger": trigger,
        "core_series": trace.core_series,
        "core_writes": trace.core_writes,
        "writes_in_divergence_window": in_window,
        "envelopes": trace.envelopes,
        "drains": trace.drains,
        "elections": trace.elections,
        "refreshes": trace.refreshes,
        "delivery_fail": trace.delivery_fail,
        "business_rejection": trace.business_rejection,
        "activate": trace.activate,
        "fail_masked": trace.fail_masked,
        "lifecycle_final": trace.lifecycle_after,
        "last_delivery_recorded": trace.last_delivery_after,
        "retry": trace.retry,
        "feedback": trace.feedback,
        "extra": extra or {},
    }
    _P2_RESULTS.append(record)
    _p2_emit(record)
    return record


@pytest.fixture(scope="module", autouse=True)
def _write_summary_p2():
    yield
    if not _P2_RESULTS:
        return
    summary = {
        "task": "EOR20261013-02 / G7-W3-D15-Handoff-Stall",
        "probe": "_g7_d15_probe.py (probe 2)",
        "evidence_level": "REAL_TXN_NO_WINDOW",
        "core_injection": "NONE (set_current_player is only WATCHED)",
        "rows": [{key: row[key] for key in
                  ("path", "label", "dispatch", "reached_settle",
                   "envelope_actor", "core_current", "controller", "outcome",
                   "branch", "writes_in_divergence_window")}
                 for row in _P2_RESULTS],
        "divergence_writes_total": sum(
            len(row["writes_in_divergence_window"]) for row in _P2_RESULTS),
    }
    try:
        os.makedirs(PROBE2_EVIDENCE_DIR, exist_ok=True)
        path = os.path.join(PROBE2_EVIDENCE_DIR, "probe2-summary.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2,
                      default=str)
        print("G7_D15_PROBE2_SUMMARY path=%s" % path)
    except Exception as exc:                          # pragma: no cover - defensive
        print("G7_D15_PROBE2_SUMMARY_FAILED error=%s" % exc)


# ---------------------------------------------------------------------------
# P-A1 — the AI drain that runs BEFORE ``_resolved_delivery``
# ---------------------------------------------------------------------------
def test_g7_d15_probe2_a1_drain_unmarked(monkeypatch):
    """1H2AI with the AI seats genuinely UNMARKED / unvoted.

    This is the ONLY shape in which ``_drain_ai_population_turns`` could still
    have work to do inside ``resolve_population_slice``. The production
    readiness gate decides whether the drain is even reachable.
    """
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-a1-drain-unmarked", ("player1",), "player1",
        pre_resolved=False, mark_all=False)
    trace.path_id = "P-A1"
    trace.mark(store, "before_command")
    trace.feedback = store.doCompletePlayer()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "after_command")

    record = _p2_finish(trace, "p2-a1-drain-unmarked", "doCompletePlayer", {
        "ai_seats_marked": False,
        "drain_calls": len(trace.drains),
        "drains": trace.drains,
        "business_rejection": trace.business_rejection,
    })
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["extra"]["drain_calls"] == 0, trace.drains


def test_g7_d15_probe2_a1_drain_marked(monkeypatch):
    """1H2AI where every seat is already marked complete (probe-1 fresh shape):
    the drain IS reached inside the resolve, and can only skip."""
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-a1-drain-marked", ("player1",), "player1",
        pre_resolved=False, mark_all=True)
    trace.path_id = "P-A1"
    trace.mark(store, "before_command")
    trace.feedback = store.doCompletePlayer()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "after_command")

    record = _p2_finish(trace, "p2-a1-drain-marked", "doCompletePlayer", {
        "ai_seats_marked": True,
        "drain_calls": len(trace.drains),
        "drains": trace.drains,
    })
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["extra"]["drain_calls"] == 1, trace.drains
    assert trace.drains[0]["processed"] == [], trace.drains
    assert record["writes_in_divergence_window"] == []


# ---------------------------------------------------------------------------
# P-A2 — election settlement changes the Core current?
# ---------------------------------------------------------------------------
def test_g7_d15_probe2_a2_election_settlement(monkeypatch):
    """First (mutating) resolve: offices / faction leaders / influence really
    change inside ``population_api.resolve_election``. Watch the Core cursor."""
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-a2-election", ("player1",), "player1",
        pre_resolved=False, mark_all=True)
    trace.path_id = "P-A2"
    trace.mark(store, "before_command")
    trace.feedback = store.doCompletePlayer()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "after_command")

    record = _p2_finish(trace, "p2-a2-election", "doCompletePlayer", {
        "elections": trace.elections,
        "election_current_unchanged": all(
            row["before"] == row["after"] for row in trace.elections),
    })
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert len(trace.elections) == 1, trace.elections
    assert record["extra"]["election_current_unchanged"] is True, trace.elections
    assert record["writes_in_divergence_window"] == []


# ---------------------------------------------------------------------------
# P-B1 — the synchronous success refresh inside the SUSPENDING window
# ---------------------------------------------------------------------------
def test_g7_d15_probe2_b1_refresh_window(monkeypatch):
    """Every production ``success`` API call runs the adapter's synchronous
    refresh callback. Observe it while the seat is suspended."""
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-b1-refresh", ("player1",), "player1",
        pre_resolved=True)
    trace.path_id = "P-B1"
    trace.mark(store, "before_command")
    trace.feedback = store.doCompletePlayer()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "after_command")

    record = _p2_finish(trace, "p2-b1-refresh", "doCompletePlayer", {
        "refresh_calls": trace.refreshes,
        "refresh_outside_active": [
            row for row in trace.refreshes
            if row["lifecycle"] != SEAT_ACTIVE],
        "dispatch_count": len(trace.dispatch),
        "deferred_after": bool(store._deferred_public_refresh),
    })
    assert len(trace.refreshes) >= 1, trace.refreshes
    assert all(row["lifecycle"] != SEAT_ACTIVE for row in trace.refreshes), \
        trace.refreshes
    assert record["dispatch"] == ["resolve_slice"], record["dispatch"]
    assert record["writes_in_divergence_window"] == []


# ---------------------------------------------------------------------------
# P-B3 — a second owning command inside the masked window (and right after it)
# ---------------------------------------------------------------------------
def test_g7_d15_probe2_b3_second_owning_command(monkeypatch):
    """A QML double-submit is a real signal-handler re-entry. Fire
    ``doAdvancePopulation`` + ``doCompletePlayer`` from the FIRST lifecycle
    signal inside the masked window, then submit ``doAdvancePopulation``
    immediately after the first command returns."""
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-b3-reentry", ("player1",), "player1",
        pre_resolved=True)
    trace.path_id = "P-B3"
    fired = []

    def _reenter():
        if fired:
            return
        fired.append(True)
        try:
            store.phaseChanged.disconnect(_reenter)
        except Exception:                            # pragma: no cover - defensive
            pass
        trace.mark(store, "reentry_seam")
        attempts = []
        for name in ("doAdvancePopulation", "doCompletePlayer"):
            before = {"dispatches": len(trace.dispatch),
                      "settles": len(trace.settle),
                      "lifecycle": store._seat_lifecycle}
            feedback = getattr(store, name)()
            attempts.append({
                "call": name,
                "before": before,
                "after": {"dispatches": len(trace.dispatch),
                          "settles": len(trace.settle),
                          "lifecycle": store._seat_lifecycle},
                "feedback": feedback,
            })
        trace.reentry = attempts

    store.phaseChanged.connect(_reenter)
    trace.mark(store, "before_command")
    trace.feedback = store.doCompletePlayer()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "after_first_command")
    adjacent = store.doAdvancePopulation()
    trace.mark(store, "after_adjacent_command")

    record = _p2_finish(trace, "p2-b3-reentry", "doCompletePlayer", {
        "reentry_fired": bool(fired),
        "reentry": getattr(trace, "reentry", []),
        "adjacent_feedback": adjacent,
        "dispatch_order": list(trace.dispatch),
        "settles_at_each_dispatch": [row["settles"] for row in
                                     trace.core_series if "tag" in row],
    })
    assert record["dispatch"][0] == "resolve_slice", record["dispatch"]
    assert record["writes_in_divergence_window"] == []
    assert fired, "the masked window must have emitted a real lifecycle phase signal"
    for attempt in getattr(trace, "reentry", []):
        assert attempt["feedback"].get("success") is False, attempt
        assert attempt["after"]["dispatches"] == attempt["before"]["dispatches"], attempt
        assert attempt["after"]["settles"] == attempt["before"]["settles"], attempt


# ---------------------------------------------------------------------------
# P-D1 / P-D2 — an OLD envelope reaching a NEW consumer / a closed scope
# ---------------------------------------------------------------------------
def test_g7_d15_probe2_d1d2_stale_envelope(monkeypatch):
    """txn1 = resolve (population scope). txn2 = advance (senate scope).
    Present txn1's REAL envelope to the validator at txn2's settle moment and
    after txn2 completes: record the stage that refuses it."""
    _state, store, _witness, trace = _p2_setup(
        monkeypatch, "p2-d1d2-stale", ("player1",), "player1",
        pre_resolved=True)
    trace.path_id = "P-D1/P-D2"
    trace.mark(store, "txn1_before")
    trace.feedback = store.doCompletePlayer()
    trace.mark(store, "txn1_after")
    assert trace.payloads and isinstance(trace.payloads[-1], dict), \
        "txn1 must deliver a real envelope"

    stale = trace.payloads[-1]
    txn1_last_delivery = bool(store._last_delivery)
    trace.stale_delivery = stale
    trace.perturb = _p2_stale_probe(trace)
    trace.feedback2 = store.doAdvancePopulation()
    trace.lifecycle_after = store._seat_lifecycle
    trace.last_delivery_after = bool(store._last_delivery)
    trace.mark(store, "txn2_after")

    post = _ORIG_VALIDATE(store._state, stale, viewer_id=store._viewer_id)
    record = _p2_finish(trace, "p2-d1d2-stale", "doCompletePlayer+doAdvancePopulation", {
        "txn1_envelope": {
            "scope_id": stale.get("scope_id"),
            "actor": (stale.get("next") or {}).get("actor_player_id"),
            "outcome": stale.get("outcome"),
            "controller": (stale.get("next") or {}).get("controller"),
        },
        "txn1_last_delivery_recorded_after_activation": txn1_last_delivery,
        "stale_at_consumer": trace.stale_at_consumer,
        "stale_post_command": {"ok": post.get("ok"), "error": post.get("error")},
        "envelope_scopes": [row.get("scope_id") for row in trace.envelopes],
        "txn2_feedback": trace.feedback2,
    })
    assert record["dispatch"][0] == "resolve_slice", record["dispatch"]
    assert record["writes_in_divergence_window"] == []
    assert txn1_last_delivery is False or txn1_last_delivery is None, \
        "a validated envelope must not survive a successful activation"
    assert post.get("ok") is False, post
    assert record["extra"]["stale_at_consumer"] or record["extra"]["stale_post_command"], \
        record["extra"]
