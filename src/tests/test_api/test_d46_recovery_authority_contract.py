"""EOR20261013-02 · D4/D6 I1 — recovery authority family contract (RED-first).

Frozen source of truth:
  * ``02-sa-design/Rework-D3D6-Recovery-Authority-Design-Delta_2026-10-17.md``
    (``c80531c3…``) — §1.1 canonical five-row admission, §3 issue/bind identity,
    §4 consume protocol, FC-RA-01..12;
  * ``02-sa-design/Rework-D3D6-Recovery-Authority_Implementation_and_Test_Overlay_2026-10-17.md``
    (``91b4449a…``) — §3.2.A RA-A01-P..05-P + RA-PN1..3;
  * ``02-sa-design/Rework-D3D6-D4D6-Design-Delta_2026-10-17.md`` (``f5aeed7d…``)
    §4.1/§5 — item1 registry separation + interface chapter;
  * ``00-gates/Owner-Approval-PC-RA-01-05_2026-10-17.md`` (PC-RA-01/04/05 APPROVED);
  * ``00-gates/G4-DA-Sizing-and-Write-Scope-D4D6-Integration_2026-10-17.md`` (I1 face).

Scope = the I1 authority seam ONLY (no consumer/terminal chain — that is I2):
  * the five-row admission registers a mandate; every other root registers NOTHING;
  * the one-use attempt cap is mintable only from a sealed FAILED_RECOVERABLE
    mandate and only for a kind inside the mandate's permitted closed set;
  * the new ``authorize_hotseat`` recovery branch is inert without an explicit
    service-private possession (cap or live fresh scope) — it is never derived
    from a failure/route/current-AI/None-viewer fact.

Provenance: real factory session (``gr_f_3h.json``) + real service primitives
(``register_hotseat_session`` / ``authorize_and_lease``).  ``source_kind =
CONSTRUCTED_STATE``; ``test_chain_quality = UNIT-LOCAL-ONLY`` (the I1 authority
seam; the full Slot terminal chain is bound in I2).  No QML / data / other
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

from src.api import session_access
from src.api import session_api

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"

#: The FROZEN §1.1 admission table (five rows ONLY). Any other root is EXCLUDE.
EXPECTED_ADMISSION = {
    "advance_forum_phase": ("RA-A01",
                            frozenset({"ENTRY_PENDING", "CONTINUATION_PENDING",
                                       "DELIVERY_PENDING"})),
    "advance_population_phase": ("RA-A02",
                                 frozenset({"ENTRY_PENDING",
                                            "CONTINUATION_PENDING",
                                            "TERMINAL_PENDING",
                                            "DELIVERY_PENDING"})),
    "propose_many": ("RA-A03",
                     frozenset({"CONTINUATION_PENDING", "TERMINAL_PENDING",
                                "DELIVERY_PENDING"})),
    "vote": ("RA-A04",
             frozenset({"CONTINUATION_PENDING", "TERMINAL_PENDING",
                        "DELIVERY_PENDING"})),
    "veto": ("RA-A05", frozenset({"TERMINAL_PENDING", "DELIVERY_PENDING"})),
}

RECOVERY_ROOT = "recover_continuation"


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


def _authorize_original(state, command, actor, payload=None):
    """Drive the REAL service entry: a successful exact ACTIVE authorization that
    records the prior auth and mints the exact lease (§3.2)."""
    return session_access.authorize_and_lease(
        state, command=command, actor=actor,
        payload_digest=session_access.payload_digest_of(payload or {}),
        session_id=session_access._state_identity(state),
        txn_id="txn-orig-1")


def _sealed_mandate(state, command, actor, payload=None):
    """Authorize the original command then seal the mandate as a proven
    post-commit FAILED_RECOVERABLE (the owner-hook seal; the commit proof is a
    service-private argument, never a GUI dict)."""
    _authorize_original(state, command, actor, payload)
    assert session_access.seal_recovery_mandate_for_failure(state) is True


def _business_snapshot(state):
    return (
        session_access.core_business_revision(state),
        getattr(state.get_current_player(), "player_id", None),
        session_api._infer_current_phase_id(state),
    )


# ===========================================================================
# item1 / registry separation + §1.1 admission shape
# ===========================================================================
def test_admission_table_is_exactly_the_five_rows():
    table = session_access._RECOVERY_ADMISSION
    assert set(table) == set(EXPECTED_ADMISSION)
    for command, (policy_id, kinds) in EXPECTED_ADMISSION.items():
        got_id, got_kinds, _transition = table[command]
        assert got_id == policy_id, command
        assert got_kinds == kinds, command
    # the recovery root and the legacy S-C population roots never opt in
    for excluded in ("recover_continuation", "submit_population_votes",
                     "complete_population_player", "resolve_population_slice",
                     "advance_senate_phase", "propose", "advance_forum",
                     "advance_population"):
        assert excluded not in table, excluded


def test_recovery_edge_policies_are_private_and_per_resume_kind():
    policies = session_access._RECOVERY_EDGE_POLICIES
    assert set(policies) == {
        (RECOVERY_ROOT, "ENTRY_PENDING"),
        (RECOVERY_ROOT, "CONTINUATION_PENDING"),
        (RECOVERY_ROOT, "TERMINAL_PENDING"),
        (RECOVERY_ROOT, "DELIVERY_PENDING"),
    }
    # the five normal roots are NEVER in the recovery registry
    normal = {"advance_forum_phase", "advance_population_phase", "propose_many",
              "vote", "veto"}
    for (_root, _kind), _edges in policies.items():
        assert _root == RECOVERY_ROOT
    # registry-LEVEL separation (a normal-root guard LABEL may legitimately appear
    # as an internal recovery edge; that is not a registry key):
    assert {root for (root, _kind) in policies} == {RECOVERY_ROOT}
    assert RECOVERY_ROOT not in session_access._RECOVERY_ADMISSION
    assert set(session_access._RECOVERY_ADMISSION) == normal
    # DELIVERY_PENDING opens NO new business edge (read/verify/re-deliver only)
    assert policies[(RECOVERY_ROOT, "DELIVERY_PENDING")] == frozenset()
    # TERMINAL_PENDING reaches ONLY the unique finalization edge (+ inner assign)
    assert policies[(RECOVERY_ROOT, "TERMINAL_PENDING")] == frozenset(
        {"finalize_senate_if_ready", "assign_governors"})


# ===========================================================================
# §3.2 / FC-RA-01 — registration is opt-in five-row only
# ===========================================================================
def test_mandate_registered_only_for_admitted_root():
    state, pids = _registered("forum")
    lease = _authorize_original(state, "advance_forum_phase", pids[0])
    assert lease is not None, "the original ACTIVE authorization must mint a lease"
    mandate = session_access.recovery_mandate(state)
    assert mandate is not None
    assert mandate.original_command == "advance_forum_phase"
    assert mandate.original_actor == pids[0]
    assert mandate.permitted_resume_kind == frozenset(
        {"ENTRY_PENDING", "CONTINUATION_PENDING", "DELIVERY_PENDING"})
    assert mandate.status == session_access.MANDATE_ARMED
    # a private possession exists at trusted binding time
    assert session_access.current_recovery_invocation(state) is not None


# ===========================================================================
# RA-PN1 — a LEGAL authorization whose root is NOT in the five rows
# ===========================================================================
def test_ra_pn1_non_opt_in_root_registers_nothing():
    state, pids = _registered("population")
    before = _business_snapshot(state)
    # `submit_population_votes` is a LEGAL exact ACTIVE authorization (the old S-C
    # population root) — it must succeed AND register NOTHING.
    lease = _authorize_original(state, "submit_population_votes", pids[0])
    assert lease is not None
    assert session_access.recovery_mandate(state) is None
    assert session_access.current_recovery_invocation(state) is None
    assert session_access.has_failed_recoverable_mandate(state) is False
    # the legal original command is NOT counted as a recovery attempt
    assert session_access.issue_recovery_attempt(
        state, resume_kind="CONTINUATION_PENDING") is None
    assert _business_snapshot(state) == before


# ===========================================================================
# RA-PN2 — a legal root but an ILLEGAL resume-kind / phase chain
# ===========================================================================
def test_ra_pn2_illegal_resume_kind_is_refused():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    before = _business_snapshot(state)
    # RA-A01 permits {ENTRY, CONTINUATION, DELIVERY}; TERMINAL is NOT in the set.
    assert session_access.issue_recovery_attempt(
        state, resume_kind="TERMINAL_PENDING") is None
    # a bogus kind is likewise refused
    assert session_access.issue_recovery_attempt(
        state, resume_kind="NOT_A_KIND") is None
    # ... but a permitted kind IS mintable (positive control after every negative)
    assert session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING") is not None
    assert _business_snapshot(state) == before


def test_ra_pn2_illegal_kind_on_terminal_only_root_is_refused():
    state, pids = _registered("forum")
    _sealed_mandate(state, "veto", pids[0])
    # RA-A05 permits only {TERMINAL, DELIVERY}
    assert session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING") is None
    assert session_access.issue_recovery_attempt(
        state, resume_kind="CONTINUATION_PENDING") is None
    assert session_access.issue_recovery_attempt(
        state, resume_kind="TERMINAL_PENDING") is not None


# ===========================================================================
# RA-PN3 — mandate substitution (another command / payload / actor)
# ===========================================================================
def test_ra_pn3_substituted_mandate_identity_is_refused():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING")
    assert cap is not None
    before = _business_snapshot(state)

    # (a) a cap naming ANOTHER mandate id
    forged_id = session_access.RecoveryAttemptCapability(
        attempt_id=cap.attempt_id, mandate_id="rm-foreign",
        session_id=cap.session_id, resume_kind=cap.resume_kind)
    assert session_access.claim_recovery_attempt(state, forged_id) is None

    # (b) a cap naming ANOTHER session (copied opaque object)
    forged_sess = session_access.RecoveryAttemptCapability(
        attempt_id=cap.attempt_id, mandate_id=cap.mandate_id,
        session_id="session-foreign", resume_kind=cap.resume_kind)
    assert session_access.claim_recovery_attempt(state, forged_sess) is None

    # (c) a wholly free-built cap (unknown attempt id)
    forged_free = session_access.RecoveryAttemptCapability(
        attempt_id="ra-free", mandate_id=cap.mandate_id,
        session_id=cap.session_id, resume_kind=cap.resume_kind)
    assert session_access.claim_recovery_attempt(state, forged_free) is None

    # no substitution consumed the real attempt, and the state is untouched
    real = session_access.claim_recovery_attempt(state, cap)
    assert real is not None
    assert _business_snapshot(state) == before


# ===========================================================================
# Guard branch — precise, additive, possession-gated
# ===========================================================================
def test_guard_denies_recovery_root_without_explicit_possession():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    # sealed mandate exists, but NO cap/scope is presented at the boundary
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT)
    assert decision.allowed is False
    # a cap for the recovery root DOES authorize the recovery dispatch once
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING")
    allowed = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT,
        recovery_capability=cap)
    assert allowed.allowed is True
    assert allowed.exempt == "recovery"
    # a SECOND dispatch of the SAME (now consumed) cap is DENIED
    again = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT,
        recovery_capability=cap)
    assert again.allowed is False


def test_guard_recovery_branch_never_widens_a_non_root_command():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING")
    # a cap presented for a NON-root command cannot open the recovery branch
    decision = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command="submit_population_votes",
        recovery_capability=cap)
    assert decision.allowed is False


def test_fresh_scope_authorizes_only_its_resume_kind_edges():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_population_phase", pids[0])
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="TERMINAL_PENDING")
    scope = session_access.claim_recovery_attempt(state, cap)
    assert scope is not None
    # TERMINAL allows the unique finalization edge
    ok = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE,
        command="finalize_senate_if_ready",
        recovery_dispatch_scope=scope)
    assert ok.allowed is True
    # but NOT an entry edge (different resume kind)
    bad = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command="begin_population_phase",
        recovery_dispatch_scope=scope)
    assert bad.allowed is False
    # and NOT a legacy population root
    bad2 = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command="submit_population_votes",
        recovery_dispatch_scope=scope)
    assert bad2.allowed is False


def test_delivery_scope_opens_no_business_edge():
    state, pids = _registered("forum")
    _sealed_mandate(state, "veto", pids[0])
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="DELIVERY_PENDING")
    scope = session_access.claim_recovery_attempt(state, cap)
    assert scope is not None
    for label in ("finalize_senate_if_ready", "assign_governors",
                  "begin_population_phase", "campaign"):
        decision = session_access.authorize_hotseat(
            state, session_access.OP_MUTATE, command=label,
            recovery_dispatch_scope=scope)
        assert decision.allowed is False, label
    # the recovery root itself is admissible inside the delivery scope
    root = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT,
        recovery_dispatch_scope=scope)
    assert root.allowed is True


# ===========================================================================
# FC-RA-08 / §1.5 — no sign-off for a legacy (mandate-less) failure; revoke kills
# ===========================================================================
def test_legacy_mandate_less_state_gets_no_recovery_authority():
    state, pids = _registered("forum")
    # simulate a legacy post-commit failure: seat suspended, lease cleared, NO
    # mandate was ever registered (deployment-before session).
    session_access.suspend_hotseat_session(state)
    session_access.clear_command_lease(state)
    assert session_access.recovery_mandate(state) is None
    assert session_access.has_failed_recoverable_mandate(state) is False
    assert session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING") is None
    assert session_access.authorize_public(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT).allowed is False


def test_revoke_tears_down_the_recovery_family():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    assert session_access.has_failed_recoverable_mandate(state) is True
    session_access.revoke_hotseat_session(state)
    assert session_access.recovery_mandate(state) is None
    assert session_access.current_recovery_invocation(state) is None
    assert session_access.has_failed_recoverable_mandate(state) is False


def test_one_live_attempt_at_a_time_and_close_is_permanent():
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    first = session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING")
    assert first is not None
    # a second un-consumed attempt is refused (single current attempt)
    assert session_access.issue_recovery_attempt(
        state, resume_kind="CONTINUATION_PENDING") is None
    scope = session_access.claim_recovery_attempt(state, first)
    assert scope is not None
    # a consumed cap is never replayed
    assert session_access.claim_recovery_attempt(state, first) is None
    session_access.close_recovery_scope(state)
    # after close, the stale scope object no longer authorizes anything
    stale = session_access.authorize_hotseat(
        state, session_access.OP_MUTATE, command=RECOVERY_ROOT,
        recovery_dispatch_scope=scope)
    assert stale.allowed is False


def test_adapter_preflight_style_possession_is_non_consuming():
    """The presented cap is validated by the boundary WITHOUT the boundary minting
    or widening authority; only the claim consumes."""
    state, pids = _registered("forum")
    _sealed_mandate(state, "advance_forum_phase", pids[0])
    cap = session_access.issue_recovery_attempt(
        state, resume_kind="ENTRY_PENDING")
    # the boundary does not mint/consume anything until the claim does
    scope = session_access.claim_recovery_attempt(state, cap)
    assert scope is not None
    assert scope.fresh_scope_id
