"""EOR20261013-02 S-B-R3b-A2 — rework contract-reject tests (F1/F2/F3/F5/F6).

These encode the CONTRACT-REJECT expectations of the G5 RETURN remediation and are
written FIRST (RED) against the pre-rework tree, then satisfied by the rework:

  * F1 (R3B-V01): the lease binds the REAL current business state —
    * the ACTUAL dispatched payload digest is compared (a correct token + a
      different dispatched payload is DENIED);
    * the authoritative Core actor is compared (not just the registry principal);
    * the authoritative Core business revision is compared (a real business change
      between issue and consume invalidates the lease);
    * `authorize_and_lease` derives the scope/revision from Core (never a GUI label
      or the seat epoch).
  * F2 (R3B-V02): continuation is PRIVATE possession — a public call that merely
    names a command in the live scope (omission / re-entry, no capability) is
    DENIED, and the owning top-level command is not in the helper set.
  * F3 (R3B-V03): the activation reservation requires a PRESENTED private staging
    capability — a public READ naming the reserved target as its viewer is DENIED.
  * F5 (D): a business rejection leaves an independent mutation digest unchanged.
  * F6 (R3B-V05): the production GuiApp path enables neutral startup (no startup
    publish) while the un-registered CLI state keeps the historical publish.
"""
import copy
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, session_access
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_MASKED_PENDING,
)

OP_MUTATE = session_access.OP_MUTATE
OP_READ_SNAPSHOT = session_access.OP_READ_SNAPSHOT


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


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


def _issue(state, pids, command="next_player", payload=None, txn="t-1"):
    pd = session_access.payload_digest_of(payload if payload is not None else {})
    lease = session_access.authorize_and_lease(
        state, command=command, actor=pids[0], payload_digest=pd,
        session_id=_sid(state), txn_id=txn)
    return lease, pd


def _tok(lease, **over):
    base = dict(lease_id=lease.lease_id, command=lease.command,
                operation=lease.operation, payload_digest=lease.payload_digest,
                scope=lease.scope, session_id=lease.session_id, txn_id=lease.txn_id,
                dispatch_epoch=lease.dispatch_epoch)
    base.update(over)
    return session_access.LeaseToken(**base)


# ===========================================================================
# F1 — authoritative business binding
# ===========================================================================
def test_f1_real_payload_mismatch_same_token_denied():
    state, pids = _hotseat()
    lease, pd = _issue(state, pids, payload={"a": 1})
    assert lease is not None
    session_access.suspend_hotseat_session(state, lifecycle_epoch=lease.dispatch_epoch)
    tok = _tok(lease)
    # The token is a faithful copy, but the ACTUAL dispatched payload digest differs.
    wrong = session_access.payload_digest_of({"a": 2})
    assert wrong != pd
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player", lease_token=tok,
        payload_digest=wrong).allowed is False
    # The exact dispatched payload digest passes.
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player", lease_token=tok,
        payload_digest=pd).allowed is True


def test_f1_authoritative_business_revision_change_invalidates_lease():
    state, pids = _hotseat()
    lease, pd = _issue(state, pids)
    assert lease is not None
    session_access.suspend_hotseat_session(state, lifecycle_epoch=lease.dispatch_epoch)
    rev_before = session_access.core_business_revision(state)
    assert int(lease.revision) == rev_before
    # A REAL business change (not a forged record field) — move public land.
    state._national_public_land += 1
    assert session_access.core_business_revision(state) != rev_before
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player", lease_token=_tok(lease),
        payload_digest=pd).allowed is False


def test_f1_authoritative_actor_change_denied():
    state, pids = _hotseat()
    lease, pd = _issue(state, pids)
    session_access.suspend_hotseat_session(state, lifecycle_epoch=lease.dispatch_epoch)
    # The authoritative Core actor moves to a different HUMAN while the registry
    # principal field is untouched.
    state.set_current_player(pids[1])
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player", lease_token=_tok(lease),
        payload_digest=pd).allowed is False


def test_f1_scope_is_authoritative_not_gui_label():
    """The lease scope/revision are derived from Core, not the caller's GUI label."""
    state, pids = _hotseat()
    lease, _pd = _issue(state, pids)
    assert lease.scope == session_access.core_business_scope(state)
    assert int(lease.revision) == session_access.core_business_revision(state)


# ===========================================================================
# F2 — private possession continuation (no ambient borrow)
# ===========================================================================
def _open_continuation(state, pids, command="next_player", helpers=None):
    lease, _pd = _issue(state, pids, command=command)
    assert lease is not None
    session_access.suspend_hotseat_session(state, lifecycle_epoch=lease.dispatch_epoch)
    assert session_access.consume_command_lease(
        state, lease_id=lease.lease_id, helpers=helpers) is None
    return lease


def test_f2_public_omission_cannot_borrow_live_scope():
    state, pids = _hotseat()
    _open_continuation(state, pids, command="submit_population_votes",
                       helpers={"begin_population_phase", "batch_vote"})
    # A PUBLIC call naming the owning command with NO capability is DENIED.
    assert session_access.present_decision(
        state, OP_MUTATE, command="submit_population_votes").allowed is False
    # A PUBLIC call naming a helper command with NO capability is DENIED.
    assert session_access.present_decision(
        state, OP_MUTATE, command="begin_population_phase").allowed is False
    # With the POSSESSED capability, the owning dispatch + declared helper pass.
    cap = session_access.current_dispatch_capability(state)
    assert cap is not None
    assert session_access.present_decision(
        state, OP_MUTATE, command="submit_population_votes",
        dispatch_capability=cap).allowed is True
    assert session_access.present_decision(
        state, OP_MUTATE, command="begin_population_phase",
        dispatch_capability=cap).allowed is True
    # An out-of-scope command is DENIED even with the capability.
    assert session_access.present_decision(
        state, OP_MUTATE, command="advance_year",
        dispatch_capability=cap).allowed is False


def test_f2_second_owning_dispatch_while_live_denied():
    state, pids = _hotseat()
    _open_continuation(state, pids, command="next_player")
    cap = session_access.current_dispatch_capability(state)
    # First (owning) dispatch under possession is allowed.
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player", dispatch_capability=cap).allowed is True
    # A SECOND owning dispatch that holds NO possession (a public re-entry while the
    # scope is still live) is DENIED — the live scope is not a reusable token.
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player").allowed is False


def test_f2_owning_command_excluded_from_helpers():
    state, pids = _hotseat()
    _open_continuation(state, pids, command="submit_population_votes",
                       helpers={"submit_population_votes", "batch_vote"})
    scope = session_access._record(state).continuation_scope
    assert "submit_population_votes" not in scope["helpers"]
    assert "batch_vote" in scope["helpers"]


# ===========================================================================
# F3 — private staging reservation requires a presented capability
# ===========================================================================
def test_f3_public_read_cannot_borrow_staging_reservation():
    state, pids = _hotseat()
    cap = session_access.issue_activation_reservation(
        state, pids[1], epoch=1, txn_id="stg-txn")
    assert cap is not None
    before = _digest(state)
    # A public READ naming the reserved target as its viewer, WITHOUT the private
    # staging capability, is DENIED (no staging-authority borrow).
    res = session_api.get_session_snapshot(state, pids[1])
    assert res.get("success") is False
    assert _digest(state) == before
    # With the presented staging capability the reserved-target read succeeds.
    session_access.begin_staging_nesting(state, cap)
    try:
        ok = session_api.get_session_snapshot(state, pids[1])
    finally:
        session_access.end_staging_nesting(state)
    assert ok.get("success") is True


# ===========================================================================
# F5 — business rejection leaves an independent mutation digest unchanged
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


def test_f5_business_rejection_digest_unchanged_and_recovers():
    from unittest.mock import patch
    state, pids = _hotseat()
    store = GuiSessionStore(state, neutral_startup=False)
    store.initialize(pids[0])
    recv = _Receiver(store)
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    digest_before = _digest(state)
    rev_before = session_access.core_business_revision(state)
    with patch.object(store._adapter, "next_player",
                      return_value={"success": False, "message": "refused"}):
        fb = store.doCompletePlayer()
    assert fb["success"] is False
    # F5: the independent business-state digest is UNCHANGED by a refusal, and the
    # seat recovers through the same fresh-epoch protocol (not a re-stage at the
    # old epoch).
    assert _digest(state) == digest_before
    assert store.seatLifecycle == SEAT_ACTIVE
    assert session_access._record(state).epoch == 1


# ===========================================================================
# F6 — production GuiApp neutral startup (no startup publish)
# ===========================================================================
def test_f6_gui_app_production_path_neutral_startup_no_publish():
    from src.ui.gui.app import GuiApp
    result = session_api.create_gui_hotseat_session(start_phase="population")
    assert result["success"]
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    app = GuiApp(state)
    store = app.get_store()
    assert store._neutral_startup is True
    store.setHandoffBarrierProvider(_Barrier())
    _Receiver(store)
    store.initialize(pids[0])
    # No startup publish: neutral MASKED_PENDING, empty viewer.
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""
    # Explicit first-HUMAN 接管 publishes.
    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]


def test_f6_cli_unregistered_state_keeps_historical_publish():
    from src.ui.gui.app import GuiApp
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"]
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert not session_access.is_hotseat_registered(state)
    store = GuiApp(state).get_store()
    store.setHandoffBarrierProvider(_Barrier())
    _Receiver(store)
    store.initialize(pids[0])
    # The un-registered CLI state keeps the historical first-viewer publish.
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]
