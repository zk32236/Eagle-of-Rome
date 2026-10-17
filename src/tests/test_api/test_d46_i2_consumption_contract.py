"""EOR20261013-02 · D4/D6 I2 — consumption / terminal contract (RED-first).

Frozen source of truth:
  * ``02-sa-design/Rework-D3D6-D4D6-Design-Delta_2026-10-17.md`` (``f5aeed7d…``)
    §4.2 (committed-entry receipt), §4.3 (terminal / G), §4.4 (owner_completion),
    §4.6 (AI narrow delegation), §6.1 FC-D46-01..10;
  * ``02-sa-design/Rework-D3D6-D4D6_Implementation_and_Test_Overlay_2026-10-17.md``
    (``9450e5ed…``) §3.2 (D46-REC-ENTRY / D46-OWN-COMP / D46-AI-DEL), §4, §5;
  * ``02-sa-design/Rework-D3D6-Recovery-Authority-Design-Delta_2026-10-17.md``
    (``c80531c3…``);
  * ``00-gates/G4-DA-Sizing-and-Write-Scope-D4D6-Integration_2026-10-17.md`` (I2 face).

Scope = the I2 consumption / terminal seam built ON the I1 authority family:
  * item2 — ``enter_phase`` consumes a SERVICE-ISSUED committed entry receipt
    exactly once (a GUI plain dict with ``committed=True`` is refused on a
    registered Hot-seat session); the phase-advance owning command's commit hook
    ISSUES the receipt; failure enum NOT_COMMITTED / MISSING_PHASE /
    DUPLICATE_RECEIPT / BINDING_MISMATCH / SOURCE_NOT_COMMITTED;
  * item4 — ``ExecutionOutcome.owner_completion`` typed carrier (default None);
  * item6 — ``_senate_ai_executor`` narrow delegation of the ``veto`` substep.

Provenance: real factory session (``gr_f_3h.json``) + real service primitives
(``create_gui_prototype_session`` / ``register_hotseat_session`` /
``record_phase_result`` / the real ``advance_forum_phase`` boundary).
``source_kind = CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY``
(the full Slot terminal chain is bound by the G5 verifier). No QML / data / other
product file is touched.

NO TOUCH: every pre-existing test assertion; this file is new.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import forum_api
from src.api import session_access
from src.api import session_api
from src.api import session_turn_service as sts

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"


# ---------------------------------------------------------------------------
# Real-primitive construction (committed fixture only)
# ---------------------------------------------------------------------------
def _registered(start_phase):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase=start_phase,
        scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    state.set_current_player(pids[0])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _unregistered(start_phase):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase=start_phase,
        scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    state.set_current_player(pids[0])
    return state, pids


def _issue(state, *, command_id="advance_forum_phase", phase="population",
           actor=None):
    return sts.issue_committed_phase_entry_receipt(
        state, command_id=command_id, phase=phase, actor=actor,
        txn_id="txn-1", domain_scope_id="ds-1", payload_digest="pd-1")


# ===========================================================================
# item2 / FC-D46-04 — a GUI plain dict cannot forge ``committed=True``
# ===========================================================================
def test_gui_plain_dict_is_not_a_committed_receipt_on_registered_session():
    state, pids = _registered("forum")
    # exactly the shape a GUI could build: committed=True + a made-up receipt_id.
    forged = {"committed": True, "receipt_id": "gui-forged-1", "phase": "population"}
    out = sts.enter_phase(state, forged)
    assert out.get("success") is False, out
    assert out.get("reason") == "NOT_COMMITTED", out
    # no scope was minted for the target phase by the refused entry
    book = sts._book(state)
    assert "population" not in book.scopes or book.scopes["population"] is None


# ===========================================================================
# item2 — a service-issued receipt is consumed EXACTLY once
# ===========================================================================
def test_service_issued_receipt_consumed_exactly_once():
    state, pids = _registered("forum")
    # the source phase (forum) is a real committed advance
    state.mark_phase_executed("forum")
    receipt = _issue(state, phase="population")
    assert receipt.get("committed") is True, receipt
    assert receipt.get("issued_by") == "advance_forum_phase", receipt

    first = sts.enter_phase(state, receipt)
    assert first.get("success") is True, first
    assert first["phase_entered"]["phase"] == "population"

    second = sts.enter_phase(state, receipt)
    assert second.get("success") is False, second
    assert second.get("reason") == "DUPLICATE_RECEIPT", second


# ===========================================================================
# item2 — a tampered presented copy is a BINDING_MISMATCH
# ===========================================================================
def test_tampered_receipt_binding_is_refused():
    state, pids = _registered("forum")
    state.mark_phase_executed("forum")
    receipt = _issue(state, phase="population")
    tampered = dict(receipt)
    tampered["actor"] = "someone-else"
    out = sts.enter_phase(state, tampered)
    assert out.get("success") is False, out
    assert out.get("reason") == "BINDING_MISMATCH", out
    # the un-tampered issued receipt is still consumable (no side effect from the
    # refused presentation)
    ok = sts.enter_phase(state, receipt)
    assert ok.get("success") is True, ok


# ===========================================================================
# item2 — SOURCE_NOT_COMMITTED when the source phase never advanced
# ===========================================================================
def test_source_not_committed_is_refused():
    state, pids = _registered("forum")
    # forum is NOT executed -> the population entry has no committed source
    receipt = _issue(state, phase="population")
    out = sts.enter_phase(state, receipt)
    assert out.get("success") is False, out
    assert out.get("reason") == "SOURCE_NOT_COMMITTED", out


# ===========================================================================
# item2 — MISSING_PHASE
# ===========================================================================
def test_missing_phase_is_refused():
    state, pids = _registered("forum")
    state.mark_phase_executed("forum")
    receipt = _issue(state, phase="")
    out = sts.enter_phase(state, receipt)
    assert out.get("success") is False, out
    assert out.get("reason") == "MISSING_PHASE", out


# ===========================================================================
# item2 — a never-registered (CLI/legacy) state keeps the historical semantics
# ===========================================================================
def test_unregistered_state_keeps_historical_enter_phase():
    state, pids = _unregistered("forum")
    # visual navigation / non-committed receipt is NOT entry
    assert sts.enter_phase(state, {"phase": "population"})["success"] is False
    receipt = {"committed": True, "receipt_id": "r1", "phase": "population"}
    first = sts.enter_phase(state, receipt)
    assert first["success"] is True, first
    assert first["phase_entered"]["phase"] == "population"
    second = sts.enter_phase(state, receipt)
    assert second["success"] is False
    assert second["reason"] == "DUPLICATE_RECEIPT", second


# ===========================================================================
# item2 — the phase-advance owning command commit hook ISSUES the receipt
# ===========================================================================
def test_advance_forum_phase_commit_hook_issues_receipt():
    state, pids = _unregistered("forum")
    pid = pids[0]
    state.set_current_player(pid)
    state.record_phase_result("forum", {"success": True, "data": {}})
    out = forum_api.advance_forum_phase(state, pid)
    assert out.get("success") is True, out
    data = out.get("data") or {}
    receipt = data.get("entry_receipt")
    assert isinstance(receipt, dict), out
    assert receipt.get("committed") is True, receipt
    assert receipt.get("command_id") == "advance_forum_phase", receipt
    assert receipt.get("phase") == "population", receipt
    # it is registered in the SERVICE-PRIVATE book registry (not a caller object)
    book = sts._book(state)
    reg = getattr(book, "_committed_phase_receipts", {})
    assert receipt.get("receipt_id") in reg, (receipt, list(reg))


# ===========================================================================
# item4 — ExecutionOutcome carries an optional owner_completion (default None)
# ===========================================================================
def test_execution_outcome_owner_completion_defaults_none():
    out = sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED, command_id="c")
    assert out.owner_completion is None
    marker = sts.OwnerCompletion(
        scope_id="s", obligation_id=("o",), command_id="senate_veto_decision",
        actor_player_id=None, kind=sts.KIND_ACTION, receipt_id="r",
        pre_revision=1, satisfied_at_revision=2, fact_ref="senate-veto:s")
    out2 = sts.ExecutionOutcome(sts.OUTCOME_ACCEPTED, command_id="senate_veto_decision",
                                owner_completion=marker)
    assert out2.owner_completion is marker
    assert out2.owner_completion.actor_player_id is None


# ===========================================================================
# item6 — the senate executor fails closed for a non-AI-owner veto obligation
# ===========================================================================
def test_senate_executor_veto_without_ai_owner_fails_closed():
    """A veto obligation that is NOT a real scheduled-AI stop must stay a masked
    failure (never a silent success / never an AI takeover of a HUMAN tribune)."""
    state, pids = _unregistered("senate")
    state.set_current_player(pids[0])
    state.add_senate_proposal({"type": "law", "title": "t", "payload": {}})
    snap = sts.obligations(state, "senate")
    veto = next(o for o in snap.obligations if o.substep == "veto")
    out = senate_executor(state, veto)
    assert out.kind == sts.OUTCOME_FAILURE, out


def senate_executor(state, target):
    from src.api import senate_api
    return senate_api._senate_ai_executor(state, target)
