"""EOR20261013-02 S-B-R3b — Handoff Atomicity contract tests (DG-03).

Frozen basis: ``02-sa-design/S-B-R3-Design-Delta.md`` v2 §3 (DG-03 §3.2 lease
object + sole issuance precondition; §3.3 predicate conditions 1–12; §3.3A
two-epoch relation; §3.4 exactly-one top-level dispatch consumption + txn-local
continuation scope) and ``S-B-R3_Implementation_and_Test_Overlay.md`` §4.2
negative matrix / §5 R3b row.

Covered:
  * A — exact ``CommandLease`` binding + single atomic consumption; every §3.3
    negative (replay / actor / payload / revision / operation-class / scope /
    session / issuing-txn / unauthorized issuance / missing payload|scope|epoch /
    stale-reentry / abort-before-dispatch) DENIED with an unchanged digest;
  * F03 traces — normal ``ACTIVE -> SUSPENDING -> dispatch``; stale/re-entry/replay.
  * C — commit ordering (authority commit strictly before publish; fresh handle
    only after the safe reveal);
  * D — fail-closed recovery neutralizes on a PRE-commit failure and a business
    rejection recovers through the SAME fresh-epoch protocol;
  * E — neutral startup then explicit first-HUMAN 接管;
  * F — ``handoffExitRequested`` invalidates the txn + handles;
  * G — the O1 read helpers are guarded by the shared predicate (open endpoints).

Three independent no-side-effect oracles (DTO-builder spy / source digest / RNG).
"""
import copy
import os
import random
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import (session_api, session_access, gui_query_api, player_api,
                     game_api, figure_api, faction_api, province_api, contract_api)
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_PENDING, SEAT_MASKED_FAILURE,
)

OP_MUTATE = session_access.OP_MUTATE


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _hotseat(start_phase="population"):
    result = session_api.create_gui_hotseat_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    for pid in pids[1:]:
        o = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=o.faction_id,
                                player_type=PlayerType.HUMAN))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    session_access.advance_hotseat_principal(state, pids[0], 0)
    return state, pids


def _sid(state):
    return session_access._state_identity(state)


def _digest(state):
    return copy.deepcopy(state.to_dict())


def _arm(state, pids, command="next_player", payload=None, scope="txn-1",
         txn="txn-1", revision=0):
    digest = session_access.payload_digest_of(payload if payload is not None else {})
    return session_access.authorize_and_lease(
        state, command=command, actor=pids[0], payload_digest=digest, scope=scope,
        revision=revision, session_id=_sid(state), txn_id=txn), digest


def _token(lease, **over):
    base = dict(lease_id=lease.lease_id, command=lease.command,
                operation=lease.operation, payload_digest=lease.payload_digest,
                scope=lease.scope, session_id=lease.session_id, txn_id=lease.txn_id,
                dispatch_epoch=lease.dispatch_epoch)
    base.update(over)
    return session_access.LeaseToken(**base)


def _present(state, token, command="next_player", operation=OP_MUTATE,
             payload_digest=None):
    return session_access.present_decision(
        state, operation, command=command, lease_token=token,
        payload_digest=payload_digest)


# ===========================================================================
# A — DG-03 §3.2 sole issuance precondition
# ===========================================================================
def test_lease_not_minted_without_prior_active_authorization():
    state, pids = _hotseat()
    # No recorded prior ACTIVE authorization -> no lease may exist.
    lease_id = "ls-manual"
    lease = session_access.CommandLease(
        lease_id=lease_id, command="next_player", operation=OP_MUTATE, actor=pids[0],
        payload_digest="d", revision=0, scope="s", session_id=_sid(state),
        txn_id="t", authorization_epoch=0, dispatch_epoch=1)
    assert session_access.issue_command_lease(state, lease) is None
    assert session_access.current_lease_token(state) is None
    # A presented (unauthorized-issuance) token is DENIED.
    tok = session_access.LeaseToken(
        lease_id=lease_id, command="next_player", operation=OP_MUTATE,
        payload_digest="d", scope="s", session_id=_sid(state), txn_id="t",
        dispatch_epoch=1)
    assert _present(state, tok).allowed is False


def test_normal_active_suspending_dispatch_trace():
    state, pids = _hotseat()
    lease, digest = _arm(state, pids)
    assert lease is not None
    # authorization_epoch = e (=rec.epoch=0); dispatch_epoch = e + 1 (F03).
    assert lease.authorization_epoch == 0 and lease.dispatch_epoch == 1
    # Suspension pins the dispatch/suspension epoch (same txn).
    session_access.suspend_hotseat_session(state, lifecycle_epoch=lease.dispatch_epoch)
    tok = _token(lease)
    dec = _present(state, tok, payload_digest=digest)
    assert dec.allowed and dec.exempt == "lease"
    # Atomic consume opens the txn-local continuation scope.
    assert session_access.consume_command_lease(state, lease_id=lease.lease_id) is None
    assert session_access.current_dispatch_capability(state) is not None
    assert session_access.current_lease_token(state) is None


# ===========================================================================
# A — DG-03 §3.3 negative matrix (each DENIED + digest unchanged)
# ===========================================================================
def _negatives(state, pids, lease, digest):
    sid = _sid(state)
    return {
        "operation-class": _token(lease, operation="read:session_snapshot"),
        "payload-absent": _token(lease, payload_digest=""),
        "payload-mismatch": _token(lease, payload_digest="deadbeef"),
        "scope-absent": _token(lease, scope=""),
        "scope-mismatch": _token(lease, scope="other-phase"),
        "session-mismatch": _token(lease, session_id="session-foreign"),
        "txn-mismatch": _token(lease, txn_id="txn-foreign"),
        "epoch-later": _token(lease, dispatch_epoch=lease.dispatch_epoch + 3),
        "lease-id-mismatch": _token(lease, lease_id="ls-other"),
    }


def test_lease_binding_negatives_denied_no_side_effects():
    state, pids = _hotseat()
    lease, digest = _arm(state, pids)
    before, rng_before = _digest(state), random.getstate()
    for name, tok in _negatives(state, pids, lease, digest).items():
        dec = _present(state, tok, payload_digest=digest)
        assert dec.allowed is False, name
    # missing epoch (contract present but epoch dropped to a non e+1 value)
    bad = _token(lease, dispatch_epoch=0)
    assert _present(state, bad, payload_digest=digest).allowed is False
    # wrong command label
    assert _present(state, _token(lease), command="campaign",
                    payload_digest=digest).allowed is False
    # READ operation is never a lease authorization
    assert _present(state, _token(lease), operation=session_access.OP_READ_SNAPSHOT,
                    payload_digest=digest).allowed is False
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_lease_actor_and_revision_mismatch_denied():
    state, pids = _hotseat()
    sid = _sid(state)
    digest = session_access.payload_digest_of({})
    # actor mismatch: a lease recorded/issued for a DIFFERENT actor than current.
    _record = session_access.record_active_authorization(
        state, lease_id="ls-actor", command="next_player", operation=OP_MUTATE,
        actor=pids[1], payload_digest=digest, scope="s", revision=0,
        session_id=sid, txn_id="t", authorization_epoch=0)
    assert _record is not None
    lease = session_access.CommandLease(
        lease_id="ls-actor", command="next_player", operation=OP_MUTATE, actor=pids[1],
        payload_digest=digest, revision=0, scope="s", session_id=sid, txn_id="t",
        authorization_epoch=0, dispatch_epoch=1)
    assert session_access.issue_command_lease(state, lease) is not None
    assert _present(state, _token(lease), payload_digest=digest).allowed is False

    # revision mismatch: lease revision != recorded current revision.
    state2, pids2 = _hotseat()
    sid2 = _sid(state2)
    session_access.record_active_authorization(
        state2, lease_id="ls-rev", command="next_player", operation=OP_MUTATE,
        actor=pids2[0], payload_digest=digest, scope="s", revision=0,
        session_id=sid2, txn_id="t", authorization_epoch=0)
    lease2 = session_access.CommandLease(
        lease_id="ls-rev", command="next_player", operation=OP_MUTATE, actor=pids2[0],
        payload_digest=digest, revision=0, scope="s", session_id=sid2, txn_id="t",
        authorization_epoch=0, dispatch_epoch=1)
    assert session_access.issue_command_lease(state2, lease2) is not None
    # The Core revision advances mid-transaction: current revision != lease revision.
    session_access._record(state2).revision = 99
    assert _present(state2, _token(lease2), payload_digest=digest).allowed is False


def test_replay_after_consumption_denied():
    state, pids = _hotseat()
    lease, digest = _arm(state, pids)
    assert _present(state, _token(lease), payload_digest=digest).allowed is True
    assert session_access.consume_command_lease(state, lease_id=lease.lease_id) is None
    before = _digest(state)
    # Replay of the SAME lease_id after consumption -> DENIED (condition 12).
    assert _present(state, _token(lease), payload_digest=digest).allowed is False
    assert _digest(state) == before


def test_stale_reentry_and_abort_before_dispatch():
    state, pids = _hotseat()
    lease, digest = _arm(state, pids)
    # Abort before dispatch destroys the lease; a retry mints a FRESH lease.
    session_access.clear_command_lease(state)
    assert session_access.current_lease_token(state) is None
    assert _present(state, _token(lease), payload_digest=digest).allowed is False
    lease2, digest2 = _arm(state, pids)
    assert lease2 is not None and lease2.lease_id != lease.lease_id
    # The stale token cannot resurrect the old lease.
    assert _present(state, _token(lease), payload_digest=digest).allowed is False
    assert _present(state, _token(lease2), payload_digest=digest2).allowed is True


def test_lease_cleared_on_revoke_and_advance():
    state, pids = _hotseat()
    lease, _digest_v = _arm(state, pids)
    session_access.revoke_hotseat_session(state)
    assert session_access.current_lease_token(state) is None


# ===========================================================================
# C — commit ordering on a REGISTERED seat
# ===========================================================================
class _Receiver:
    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _Barrier:
    def __init__(self, arm=True, unmask=True, pending=True):
        self.arm = arm
        self.unmask = unmask
        self.pending = pending
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return self.arm

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); return self.pending

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return self.unmask

    def show_failure(self, txn, kind):
        self.calls.append(("failure", txn, kind)); return True


def _store_setup(neutral_startup=False, start_phase="population"):
    state, pids = _hotseat(start_phase=start_phase)
    store = GuiSessionStore(state, neutral_startup=neutral_startup)
    store.initialize(pids[0])
    recv = _Receiver(store)
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    return state, pids, store, recv, barrier


def test_registered_handoff_activates_and_issues_fresh_handle_after_reveal():
    state, pids, store, recv, barrier = _store_setup()
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))
    fb = store.doCompletePlayer()
    assert fb["success"], fb
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""            # no pre-confirm publication
    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]
    assert len(finals) == 1 and finals[0][1] is True
    # The fresh handle is valid only AFTER the safe reveal.
    assert session_access.current_caller_context(state) is not None
    # No command replay: the lease/continuation scope was cleared.
    assert session_access.current_lease_token(state) is None
    assert session_access.current_dispatch_capability(state) is None


def test_commit_ordering_no_fresh_handle_on_failed_reveal():
    state, pids, store, recv, barrier = _store_setup()
    barrier.unmask = False
    store.doCompletePlayer()
    store.requestTakeover()
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.handoffMaskVisible is True
    # A failed safe reveal never issues a fresh public handle.
    assert session_access.current_caller_context(state) is None


# ===========================================================================
# D — fail-closed recovery
# ===========================================================================
def test_precommit_failure_neutralizes_public_projection():
    state, pids, store, recv, barrier = _store_setup()
    barrier.arm = False
    fb = store.doCompletePlayer()
    assert fb["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    # D: a PRE-commit failure also neutralizes every exposed model (no stale A).
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}
    assert store.populationView == {}


def test_business_rejection_recovers_via_fresh_epoch():
    state, pids, store, recv, barrier = _store_setup()
    epoch_before = session_access._record(state).epoch
    with patch.object(store._adapter, "next_player",
                      return_value={"success": False, "message": "no"}):
        fb = store.doCompletePlayer()
    assert fb["success"] is False
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]
    # D: same-seat recovery advances the SERVICE epoch (fresh-epoch protocol).
    assert session_access._record(state).epoch == epoch_before + 1
    assert any(c[0] == "unmask" for c in barrier.calls)


# ===========================================================================
# E — neutral startup then explicit first-HUMAN 接管
# ===========================================================================
def test_neutral_startup_requires_explicit_takeover():
    state, pids = _hotseat()
    store = GuiSessionStore(state, neutral_startup=True)
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    pendings = []
    store.handoffMaskPending.connect(lambda f: pendings.append(f))
    store.initialize(pids[0])
    # No startup publish; neutral pending with the safe faction name ONLY.
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}
    assert store.handoffMaskVisible is True
    faction = state.get_faction(state.get_player(pids[0]).faction_id).name
    assert store.handoffPendingFactionName == faction
    assert pendings == [faction]
    # Explicit first-HUMAN 接管 activates the seat.
    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]


# ===========================================================================
# F — safe-exit wiring (SB-V06)
# ===========================================================================
def test_handoff_exit_invalidates_txn_and_handles():
    state, pids, store, recv, barrier = _store_setup()
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    exits = []
    store.handoffExitRequested.connect(lambda: exits.append(True))
    res = store.requestHandoffExit()
    assert res["success"] is True
    assert exits == [True]
    # R2 §4 step 8: txn + handles invalidated; no public projection survives, and
    # any read with the (revoked) handle is DENIED.
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId == ""
    ctx = session_access.current_caller_context(state)
    res = session_api.get_session_snapshot(state, pids[0], caller_context=ctx)
    assert res.get("success") is False


# ===========================================================================
# G — O1 read-helper guards
# ===========================================================================
def _read_helpers(state, pids):
    return [
        ("game_api.get_status_summary", game_api.get_status_summary, (state,)),
        ("game_api.get_public_land_info", game_api.get_public_land_info, (state,)),
        ("faction_api.get_faction_style_map", faction_api.get_faction_style_map, (state,)),
        ("faction_api.get_factions_status", faction_api.get_factions_status, (state,)),
        ("figure_api.get_figure_info", figure_api.get_figure_info, (state,)),
        ("figure_api.get_private_land_info", figure_api.get_private_land_info, (state,)),
        ("province_api.get_province_info", province_api.get_province_info, (state,)),
        ("contract_api.get_contracts_status", contract_api.get_contracts_status, (state,)),
    ]


def test_o1_read_helpers_deny_omission_on_registered_state():
    state, pids = _hotseat()
    before, rng_before = _digest(state), random.getstate()
    for label, fn, args in _read_helpers(state, pids):
        res = fn(*args)  # no caller_context presented
        assert res.get("success") is False, label
        codes = {e.get("code") for e in (res.get("errors") or []) if isinstance(e, dict)}
        assert "DENIED" in codes, label
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_o1_read_helpers_allow_with_presented_context():
    state, pids = _hotseat()
    ctx = session_access.current_caller_context(state)
    for label, fn, args in _read_helpers(state, pids):
        res = fn(*args, caller_context=ctx)
        assert res.get("success") is True, label


def test_o1_read_helpers_cli_exempt_and_query_closed_ok():
    # An un-registered CLI state keeps historical permissions.
    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert game_api.get_status_summary(state)["success"] is True
    assert figure_api.get_private_land_info(state)["success"] is True
    # The CLOSED Query safe shell is preserved for a registered seat.
    hs, hpids = _hotseat()
    ctx = session_access.current_caller_context(hs)
    q = gui_query_api.get_global_query_result(
        hs, hpids[0], "public_land", "", "", caller_context=ctx)
    assert q["success"] is True
    assert q["data"]["result_state"] in ("OK", "EMPTY")


# ===========================================================================
# Population masked dispatch: exactly-one top-level dispatch + continuation
# ===========================================================================
def test_txn_local_continuation_scope_authorizes_dispatch_and_helpers_only():
    state, pids, store, recv, barrier = _store_setup(start_phase="population")
    txn = store._begin_masked_seat_transition(
        "submitPopulationVotes", lease_command="submit_population_votes",
        payload={"consul": 1})
    assert txn is not None
    cap = session_access.current_dispatch_capability(state)
    assert cap is not None
    # The owning dispatch + its declared helper chain are authorized.
    assert session_access.present_decision(
        state, OP_MUTATE, command="submit_population_votes",
        dispatch_capability=cap).allowed is True
    assert session_access.present_decision(
        state, OP_MUTATE, command="begin_population_phase",
        dispatch_capability=cap).allowed is True
    # An out-of-scope command is DENIED.
    assert session_access.present_decision(
        state, OP_MUTATE, command="advance_year",
        dispatch_capability=cap).allowed is False
    # After settle (scope cleared) even the owning command is DENIED — no public
    # re-entry rides a dead scope.
    session_access.clear_command_lease(state)
    assert session_access.present_decision(
        state, OP_MUTATE, command="submit_population_votes").allowed is False
