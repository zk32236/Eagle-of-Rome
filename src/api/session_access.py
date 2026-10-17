"""src/api/session_access.py
EOR20261013-02 GUI Readiness — slice S-B (access / handoff), Group 1 (A2 rework).

ONE authoritative local seat access policy ("active-seat read/write guard").

Design source (frozen): ``02-sa-design/G2-Active-Seat-Read-Write-Guard.md`` +
``G2-Handoff-Authority-State-Machine.md`` + ``G2-R2-Handoff-Witness-Protocol.md``.

Placement (minimal, single):
  * this module owns the ONE predicate :func:`authorize_hotseat` / :func:`authorize_ai`;
  * it is invoked at every *public API boundary* BEFORE any DTO construction or
    mutation (session snapshot, seven phase views, the global query, the
    state-mutating Adapter dispatch and the direct public mutation endpoints);
  * lightweight wrappers call the predicate exactly once and never replicate its
    logic. The Store mirrors lifecycle to drop stale callbacks/UI input but is
    **not** the sole authorization authority; the Adapter routes context and
    preserves typed failure, it is not security truth.

A2 rework (SA-Verification-Report-S-B / G5 RETURN) repairs:
  * SB-V01 — the predicate is reachable at every public mutation/helper endpoint,
    including direct calls that do not go through the Adapter;
  * SB-V02 — a registered session REQUIRES a service-issued opaque *presented*
    context; a missing context DENIES (omission is never CLI), and a forged /
    foreign / stale / revoked context is rejected by validating the issuance
    identity, session, principal, revoked flag, lifecycle and epoch — not epoch
    alone. ``HotseatContext`` is freely constructible; only the registry-issued
    ``handle_id`` predicates acceptance;
  * SB-V03 — the service (this module) owns the authoritative lifecycle/epoch;
    SUSPENDING/FAILURE truly suspends public reads/writes, and a single-use,
    exact-command *lease* authorizes only the one prior-authorized transition;
  * SB-V07 — :func:`denied_response` no longer exports the internal
    ``_denied_reason`` audit category to the caller.

Authoritative tuple (see G2 handoff state machine):
    ``session_id, lifecycle, principal_player_id, pending_player_id, epoch,
    phase, core_revision, completion_command_id``
belongs to the session access service. Core owns the current actor/phase; the
Store owns only the projected DTO / render transaction.

Narrow preserved exemptions (must NOT be relabeled by a request):
  * a state that was never registered as a Hot-seat session keeps the historical
    CLI permissions (the historical 1H/2AI ``gui_prototype`` + CLI suite);
  * unexported AI-internal capability: actor type must be AI and it must be the
    scheduled current eligible actor.

Result contract (ordinary denial):
    ``{success: false, data: null, errors: [{code: "DENIED", scope: "session",
    field: null, details: {}, message: "Operation unavailable for this seat"}]}``
Internal reason categories are recorded on the decision object for authorized
audit but are **not** placed in the public envelope (see :func:`denied_response`);
the Query engine keeps its own CLOSED typed safe shell.

This is LOCAL seat authority, not remote login / security against an in-process
debugger (explicitly out of scope in the frozen design).
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
import threading
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Set

logger = logging.getLogger("EOR-GUI")


# ---------------------------------------------------------------------------
# Operation names — typed aliases used by the single predicate.
# ---------------------------------------------------------------------------
OP_READ_SNAPSHOT = "read:session_snapshot"
OP_READ_PHASE_VIEW = "read:phase_view"
OP_READ_QUERY = "read:global_query"
OP_MUTATE = "mutate:command"

#: Operations that never mutate source state (side-effect free reads).
READ_OPERATIONS = frozenset({OP_READ_SNAPSHOT, OP_READ_PHASE_VIEW, OP_READ_QUERY})

#: Internal reason categories (audit only; never surfaced raw to a player).
REASON_SESSION = "session"
REASON_LIFECYCLE = "lifecycle"
REASON_PRINCIPAL = "principal"
REASON_EPOCH = "epoch"
REASON_PHASE = "phase"
REASON_DUPLICATE = "duplicate"

DENIED_CODE = "DENIED"
DENIED_SCOPE = "session"
DENIED_MESSAGE = "Operation unavailable for this seat"

# Lifecycle labels shared with the Store handoff machine (mirrored constants; the
# Store remains its own publication owner, this guard only consumes the label).
LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_SUSPENDING = "SUSPENDING"
LIFECYCLE_FAILURE = "MASKED_FAILURE"
LIFECYCLE_REVOKED = "REVOKED"
#: Masked scheduled-AI execution window of the owning handoff transaction (F01
#: §1.4A / F03). No public projection/handle exists inside this window; only the
#: service-private AI capability is admitted.
LIFECYCLE_EXECUTING_MASKED = "EXECUTING_MASKED"


def denied_response(reason: str = REASON_SESSION,
                    message: str = DENIED_MESSAGE) -> Dict[str, Any]:
    """The single structured ordinary-denial envelope (see module docstring).

    ``reason`` is an internal audit category; it is deliberately **NOT** placed in
    the public ``errors`` entry nor exported as a ``_denied_reason`` key (SB-V07),
    so a caller cannot probe record existence or the denial cause.
    """
    return {
        "success": False,
        "message": message,
        "data": None,
        "errors": [{
            "code": DENIED_CODE,
            "scope": DENIED_SCOPE,
            "field": None,
            "details": {},
            "message": message,
        }],
    }


# ---------------------------------------------------------------------------
# Opaque service-issued in-process handle.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HotseatContext:
    """Service-issued opaque handle bound to session + principal + epoch.

    Mutable request fields (a viewer id, a ``mode``, a ``player_id``) are only
    *claims*; they are compared against this handle. Callers cannot manufacture a
    principal by passing a viewer/player id, nor set ``mode=CLI``. ``handle_id`` is
    the service-issued *issuance identity*: a freely-constructed ``HotseatContext``
    (without the registry's current ``handle_id``) is always rejected.
    """

    session_id: str
    principal_player_id: str
    epoch: int = 0
    lifecycle: str = LIFECYCLE_ACTIVE
    revoked: bool = False
    handle_id: str = ""


#: Lifecycle scope label for the masked scheduled-AI execution window (F01 §1.4A).
LIFECYCLE_SCOPE_EXECUTING_MASKED = "EXECUTING_MASKED"


@dataclass(frozen=True)
class AICapability:
    """Unexported service-private scheduled-AI capability (F01 §1.4A).

    Minted ONLY by the session service when it drains scheduled AI under mask and
    passed through a DISTINCT keyword-only parameter (``ai_capability``); it is
    **never** inferred from ``state`` (an AI current actor alone grants nothing).
    Like :class:`HotseatContext`, it is freely constructible as a value object; only
    the registry-issued ``capability_id`` and the exact field match predicate accept
    it, so a forged/free capability is always rejected.
    """

    capability_id: str
    session_id: str
    txn_id: str
    operation: str
    actor: str
    phase: str
    substep: str
    revision: int
    authorization_epoch: int
    lifecycle_scope: str = LIFECYCLE_SCOPE_EXECUTING_MASKED


# ---------------------------------------------------------------------------
# Exact one-use command lease + transaction-local continuation (DG-03).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommandLease:
    """Service-issued exact, single-command, transaction-bound lease (DG-03 §3.2).

    Freely constructible as a value object; only the registry-issued
    ``lease_id`` matched against the recorded prior authorization and the owning
    transaction admits it. It is never publicly requestable/exportable and
    cannot be minted by a caller (no label sets).
    """

    lease_id: str
    command: str
    operation: str
    actor: str
    payload_digest: str
    revision: int
    scope: str
    session_id: str
    txn_id: str
    authorization_epoch: int
    dispatch_epoch: int


@dataclass(frozen=True)
class LeaseToken:
    """The structured lease presentation a caller passes to the predicate (§3.3).

    A bare label is never sufficient; every bound field is carried explicitly so
    a missing ``payload_digest`` / ``scope`` / ``dispatch_epoch`` is a hard reject.
    """

    lease_id: str
    command: str
    operation: str
    payload_digest: str
    scope: str
    session_id: str
    txn_id: str
    dispatch_epoch: int


@dataclass(frozen=True)
class DispatchCapability:
    """Non-exported transaction-local continuation capability (DG-03 §3.4).

    Opened by the owning transaction's single top-level dispatch; authorizes the
    internal helper chain of that one dispatch. It never satisfies a public
    boundary's caller-context requirement and cannot be widened into a reusable
    token.
    """

    txn_id: str
    dispatch_epoch: int
    command: str
    session_id: str


@dataclass(frozen=True)
class StagingCapability:
    """Unexported service-private activation-reservation capability (R3b F3).

    Minted ONLY by :func:`issue_activation_reservation`; presented through a
    distinct keyword-only parameter (``staging_capability``) so a public READ can
    never borrow the private staging reservation merely by naming the reserved
    ``viewer``. Freely constructible as a value object; only the registry-issued
    ``capability_id`` plus the exact target/revision/txn match predicate accept it.
    """

    capability_id: str
    session_id: str
    target: str
    txn_id: str
    revision: int
    epoch: int


#: Private attribute name under which the service binds the handle to a state.
_CONTEXT_ATTR = "_session_access_context"


def _state_identity(state: Any) -> str:
    return f"session-{id(state)}"


def _key(state: Any) -> str:
    return _state_identity(state)


# ---------------------------------------------------------------------------
# Service-owned authoritative registry (independent of the bound handle).
# ---------------------------------------------------------------------------
@dataclass
class _SeatRecord:
    session_id: str
    principal_player_id: str
    epoch: int = 0
    lifecycle: str = LIFECYCLE_ACTIVE
    revoked: bool = False
    handle_id: str = ""
    #: Exact prior-authorized one-use command lease (R2 step 3).
    command_lease: Optional[Dict[str, Any]] = None
    #: Internal neutral activation reservation (R2 step 7 staging).
    reservation: Optional[Dict[str, Any]] = None
    #: Service-private masked scheduled-AI capability record (F01 §1.4A).
    ai_capability: Optional[Dict[str, Any]] = None
    #: Authoritative masked-execution scope of the OWNING transaction (F03):
    #: ``{txn_id, authorization_epoch, phase, substep, revision}``. Set only by
    #: :func:`begin_masked_execution` (service) and compared by the predicate, so a
    #: capability is validated against the service's *current* scope rather than
    #: against a mint-time copy that trivially equals itself.
    masked_scope: Optional[Dict[str, Any]] = None
    #: DG-03 §3.2–§3.4: the exact prior ACTIVE current-seat authorization tuple
    #: recorded at lease-issue time (the sole issuance precondition).
    prior_auth: Optional[Dict[str, Any]] = None
    #: The owning transaction's non-exported transaction-local continuation scope,
    #: opened by the single top-level dispatch and cleared on settle (DG-03 §3.4).
    continuation_scope: Optional[Dict[str, Any]] = None
    #: The one service transaction that owns authorization + suspension + dispatch.
    active_txn_id: str = ""
    #: The lifecycle/dispatch epoch the owning transaction is permitted to dispatch
    #: under (``authorization_epoch + 1`` for a normal handoff; F03 §3.3A).
    lifecycle_epoch: int = 0
    #: Current service-tracked core revision (re-checked at commit, DG-03 §3.3 #10).
    revision: int = 0
    #: D4/D6 I1 recovery authority family (PC-RA-01..05). Independent of the
    #: business ledger and of every other capability slot; registered ONLY on a
    #: successful original ACTIVE exact authorization of a §1.1 admission row.
    recovery_mandate: Optional[Dict[str, Any]] = None
    recovery_invocation: Optional[Dict[str, Any]] = None
    recovery_attempt: Optional[Dict[str, Any]] = None
    recovery_scope: Optional[Dict[str, Any]] = None


#: Per-state authoritative registration record. It lives on the state under a
#: name independent of the bound handle (``_CONTEXT_ATTR``), so deleting the
#: handle cannot silently downgrade a registered Hot-seat session to the CLI
#: exemption, while the record still dies with the state (no global id-reuse
#: collisions across a long process).
_REGISTRY_ATTR = "_session_access_registry"
_ISSUE_COUNTER = 0


def _record(state: Any) -> Optional["_SeatRecord"]:
    return getattr(state, _REGISTRY_ATTR, None)


def _new_handle_id() -> str:
    global _ISSUE_COUNTER
    _ISSUE_COUNTER += 1
    return f"ctx-{_ISSUE_COUNTER}-{uuid.uuid4().hex[:10]}"


def _bind_handle(state: Any, rec: _SeatRecord) -> HotseatContext:
    ctx = HotseatContext(
        session_id=rec.session_id,
        principal_player_id=rec.principal_player_id,
        epoch=rec.epoch,
        lifecycle=rec.lifecycle,
        revoked=rec.revoked,
        handle_id=rec.handle_id,
    )
    try:
        setattr(state, _CONTEXT_ATTR, ctx)
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to bind hot-seat context")
    return ctx


def register_hotseat_session(state: Any, principal_player_id: str,
                             epoch: int = 0) -> HotseatContext:
    """Register ``state`` as a Hot-seat session and issue an opaque handle.

    Only the session service / production factory calls this. Once registered, the
    state is guarded fail-closed; an un-registered state keeps the CLI exemption.
    """
    rec = _SeatRecord(
        session_id=_state_identity(state),
        principal_player_id=str(principal_player_id),
        epoch=int(epoch),
        lifecycle=LIFECYCLE_ACTIVE,
        revoked=False,
        handle_id=_new_handle_id(),
    )
    setattr(state, _REGISTRY_ATTR, rec)
    return _bind_handle(state, rec)


def is_hotseat_registered(state: Any) -> bool:
    """Independent registration record (SB-V02): True even if the bound handle was
    deleted, so a registered session can never silently fall back to CLI."""
    return _record(state) is not None


def get_context(state: Any) -> Optional[HotseatContext]:
    """Return the bound handle attribute (informational fast path only).

    Security decisions must use :func:`authorize_hotseat` /
    :func:`present_context`; this helper is never the authority.
    """
    return getattr(state, _CONTEXT_ATTR, None)


def present_context(state: Any) -> Optional[HotseatContext]:
    """Return the service-issued handle a boundary may *present* to the predicate.

    ``None`` when the state is un-registered, the handle is absent, or a forged /
    stale handle does not carry the registry's current issuance ``handle_id``.
    """
    rec = _record(state)
    if rec is None:
        return None
    ctx = getattr(state, _CONTEXT_ATTR, None)
    if ctx is None or not rec.handle_id or ctx.handle_id != rec.handle_id:
        return None
    return ctx


def current_caller_context(state: Any) -> Optional[HotseatContext]:
    """Service-owned accessor the TRUSTED routing layer (Adapter/Store/App) uses
    to obtain the current handle it must explicitly PRESENT at a boundary (DG-01
    §1.2d). The API boundaries themselves never call this — they only pass through
    what they were given, so an omitted/forged context is denied by the predicate.
    """
    return present_context(state)


def revoke_hotseat_session(state: Any) -> None:
    """Revoke the current handle's authority (used on exit / failure-closed).

    The registration (and its independent record) is retained so a revoked session
    can never silently fall back to the CLI exemption; it now denies until a fresh
    registration.
    """
    rec = _record(state)
    if rec is None:
        return
    rec.revoked = True
    rec.lifecycle = LIFECYCLE_REVOKED
    rec.command_lease = None
    rec.continuation_scope = None
    rec.prior_auth = None
    rec.active_txn_id = ""
    rec.reservation = None
    rec.ai_capability = None
    rec.masked_scope = None
    _revoke_recovery_family(rec)
    _bind_handle(state, rec)


def suspend_hotseat_session(state: Any,
                            lifecycle: str = LIFECYCLE_SUSPENDING,
                            lifecycle_epoch: Optional[int] = None) -> Optional[_SeatRecord]:
    """SB-V03: truly suspend public read/write authority (R2 SUSPENDING/FAILURE).

    The service epoch/principal are retained for the transaction record, but every
    public read/write now DENIES (A's handle is revoked) until a fresh handle is
    issued by :func:`advance_hotseat_principal` after a safe reveal. The already
    issued exact-command lease is retained (it is consumed at dispatch, not here);
    ``lifecycle_epoch`` pins the dispatch epoch of the owning transaction (F03).
    """
    rec = _record(state)
    if rec is None:
        return None
    rec.lifecycle = lifecycle
    rec.revoked = True
    if lifecycle_epoch is not None:
        rec.lifecycle_epoch = int(lifecycle_epoch)
    rec.ai_capability = None
    rec.masked_scope = None
    _bind_handle(state, rec)
    return rec


def fail_hotseat_session(state: Any) -> Optional[_SeatRecord]:
    """Enter the fail-closed MASKED_FAILURE service state (handle revoked, deny)."""
    return suspend_hotseat_session(state, lifecycle=LIFECYCLE_FAILURE)


def advance_hotseat_principal(state: Any, principal_player_id: str,
                              epoch: Optional[int] = None) -> Optional[HotseatContext]:
    """Move the seat authority to a new principal by issuing a FRESH handle.

    No-op (returns ``None``) for a never-registered state, so an un-registered
    CLI/historical session is never silently promoted to a guarded one. The fresh
    handle is bound only AFTER the Store has safely published/revealed the seat (the
    caller orders this), so a failed activation never grants reads.
    """
    rec = _record(state)
    if rec is None:
        return None
    rec.principal_player_id = str(principal_player_id)
    rec.epoch = rec.epoch if epoch is None else int(epoch)
    rec.lifecycle = LIFECYCLE_ACTIVE
    rec.revoked = False
    rec.handle_id = _new_handle_id()
    rec.command_lease = None
    rec.continuation_scope = None
    rec.prior_auth = None
    rec.active_txn_id = ""
    rec.reservation = None
    rec.ai_capability = None
    rec.masked_scope = None
    _revoke_recovery_family(rec)
    return _bind_handle(state, rec)


def commit_hotseat_principal(state: Any, principal_player_id: str,
                             epoch: Optional[int] = None) -> Optional[_SeatRecord]:
    """Authority commit UNDER the mask (R2 step 8 / DG-03 §3.3A).

    Records the new principal + ACTIVE lifecycle but, unlike
    :func:`advance_hotseat_principal`, does NOT issue a fresh public handle: the
    fresh handle is issued only AFTER the safe reveal (:func:`issue_fresh_handle`).
    The current handle id is cleared and the record stays ``revoked`` so no public
    read/write can observe the new identity before the reveal completes.
    """
    rec = _record(state)
    if rec is None:
        return None
    rec.principal_player_id = str(principal_player_id)
    rec.epoch = rec.epoch if epoch is None else int(epoch)
    rec.lifecycle = LIFECYCLE_ACTIVE
    rec.revoked = True
    rec.handle_id = ""
    rec.command_lease = None
    rec.continuation_scope = None
    rec.prior_auth = None
    rec.active_txn_id = ""
    rec.reservation = None
    rec.ai_capability = None
    rec.masked_scope = None
    _revoke_recovery_family(rec)
    _bind_handle(state, rec)
    return rec


def issue_fresh_handle(state: Any) -> Optional[HotseatContext]:
    """Issue the fresh service handle AFTER the safe reveal (R2 step 8)."""
    rec = _record(state)
    if rec is None:
        return None
    rec.handle_id = _new_handle_id()
    rec.revoked = False
    return _bind_handle(state, rec)


def unregister_hotseat_session(state: Any) -> None:
    """Drop the hot-seat registration (test/teardown only; not a request path)."""
    try:
        delattr(state, _REGISTRY_ATTR)
    except AttributeError:
        pass
    try:
        delattr(state, _CONTEXT_ATTR)
    except AttributeError:
        pass


# ---------------------------------------------------------------------------
# Exact prior-authorized one-use command lease (R2 step 3).
# ---------------------------------------------------------------------------
def payload_digest_of(payload: Any) -> str:
    """Canonical payload digest for the lease binding (never caller-supplied)."""
    try:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # pragma: no cover - defensive
        blob = repr(payload)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Authoritative Core business binding (R3b F1 / DG-03 §3.3 conditions 4/5/9/10).
# The lease must bind the REAL current business state — never a GUI method label
# and never the seat lifecycle/epoch (R3B-V01).
# ---------------------------------------------------------------------------
def _business_blob(state: Any) -> str:
    """Canonical, stable encoding of the authoritative Core business state."""
    try:
        return json.dumps(state.to_dict(), sort_keys=True, ensure_ascii=False,
                          default=str)
    except Exception:  # pragma: no cover - defensive
        return repr(getattr(state, "__dict__", {}))


def core_business_revision(state: Any) -> int:
    """Service-owned business revision: a stable digest of the REAL Core business
    state (NOT the seat lifecycle/epoch). Any business mutation changes it, so a
    lease bound at issue no longer matches after a real business change (F1)."""
    return zlib.crc32(_business_blob(state).encode("utf-8"))


def core_business_scope(state: Any) -> str:
    """Service-owned authoritative business-scope token (phase/substep proxy),
    derived from the REAL Core business state — never a GUI method label (F1)."""
    return "core-" + hashlib.sha256(_business_blob(state).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-thread continuation nesting (R3b F2 — PRIVATE possession, not ambient).
# The service opens a nesting entry ONLY while the owning transaction is inside
# its dispatch; a public call outside that window possesses no capability and is
# therefore adjudicated by the ordinary (deny-under-mask) branches.
# ---------------------------------------------------------------------------
_NESTING_LOCAL = threading.local()


def _nesting_entry(state: Any) -> dict:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    if store is None:
        store = {}
        _NESTING_LOCAL.by_state = store
    return store.setdefault(_key(state), {})


def begin_dispatch_nesting(state: Any, *, txn_id: str, command: str,
                           dispatch_epoch: int,
                           helpers: Optional[Iterable[str]] = None) -> Optional[DispatchCapability]:
    """Open the private continuation nesting around the single owning dispatch.
    Returns the possessed capability; must be closed by :func:`end_dispatch_nesting`."""
    rec = _record(state)
    if rec is None:
        return None
    cap = DispatchCapability(txn_id=str(txn_id), dispatch_epoch=int(dispatch_epoch),
                             command=str(command), session_id=rec.session_id)
    _nesting_entry(state)["dispatch_cap"] = cap
    return cap


def end_dispatch_nesting(state: Any) -> None:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    if store is not None and _key(state) in store:
        store[_key(state)].pop("dispatch_cap", None)


def begin_staging_nesting(state: Any, capability: "StagingCapability") -> None:
    """Open the private staging nesting around the internal activation reads."""
    if capability is not None:
        _nesting_entry(state)["staging_cap"] = capability


def end_staging_nesting(state: Any) -> None:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    if store is not None and _key(state) in store:
        store[_key(state)].pop("staging_cap", None)


def _nesting_dispatch_capability(state: Any) -> Optional[DispatchCapability]:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    entry = store.get(_key(state)) if store else None
    return entry.get("dispatch_cap") if entry else None


def _nesting_staging_capability(state: Any) -> Optional[StagingCapability]:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    entry = store.get(_key(state)) if store else None
    return entry.get("staging_cap") if entry else None


def _cap_matches_scope(cap: DispatchCapability, scope: Dict[str, Any],
                       rec: "_SeatRecord") -> bool:
    if not isinstance(scope, dict):
        return False
    return (cap.txn_id == scope.get("txn_id")
            and cap.session_id == rec.session_id
            and int(cap.dispatch_epoch) == int(scope.get("dispatch_epoch", -1))
            and int(scope.get("dispatch_epoch", -1)) == int(rec.lifecycle_epoch))


def _staging_capability_ok(rec: "_SeatRecord", cap: Optional[StagingCapability],
                           operation: str, viewer: Optional[str]) -> bool:
    """R3b F3: a private staging READ requires the PRESENTED staging capability,
    validated against the reservation's target / revision / txn. Naming the target
    as ``viewer`` alone is NEVER sufficient."""
    if cap is None or operation not in READ_OPERATIONS:
        return False
    res = rec.reservation
    if not isinstance(res, dict) or not res.get("active"):
        return False
    return (cap.capability_id == res.get("capability_id")
            and cap.session_id == rec.session_id
            and cap.target == res.get("target")
            and cap.txn_id == res.get("txn_id")
            and int(cap.revision) == int(res.get("revision", -2))
            and viewer == res.get("target"))


def _continuation_decision(state: Any, rec: "_SeatRecord", operation: str,
                           command: Optional[str],
                           dispatch_capability: Optional[DispatchCapability]) -> Optional["AccessDecision"]:
    """R3b F2: authorize ONLY a *possessed* transaction-local continuation call.

    Continuation authority is PRIVATE possession: the caller must present the
    non-exported dispatch capability, or be dynamically nested inside the owning
    dispatch (opened by the service around it). A bare public call that merely
    names a command in the scope is DENIED (no ambient borrow). The owning
    top-level command is granted at most ONCE while the scope lives (no second
    owning dispatch). Returns an ``AccessDecision``, or ``None`` when there is no
    live continuation, so the ordinary public branches adjudicate the call.
    """
    scope = rec.continuation_scope
    cap = dispatch_capability or _nesting_dispatch_capability(state)
    if not isinstance(scope, dict):
        if cap is not None:
            return _deny(REASON_DUPLICATE, operation)  # stray capability
        return None
    if cap is None:
        # Live scope but NO possession -> not a continuation call; fall through so
        # the ordinary branches deny a public re-entry under the masked seat.
        return None
    if not _cap_matches_scope(cap, scope, rec):
        return _deny(REASON_DUPLICATE, operation)
    if command is None:
        return _deny(REASON_DUPLICATE, operation)
    if command == scope.get("command"):
        # The owning top-level command, granted only while the caller POSSESSES the
        # continuation (explicit capability or dynamic nesting opened by the service
        # around the one dispatch). A public call without possession never reaches
        # here (it falls through and is denied by the masked-seat branches).
        return _allow(operation, exempt="lease", command=command)
    if command in (scope.get("helpers") or frozenset()):
        return _allow(operation, exempt="lease", command=command)
    return _deny(REASON_DUPLICATE, operation)


def _prior_auth_matches(prior: Dict[str, Any], lease: Dict[str, Any]) -> bool:
    keys = ("lease_id", "command", "operation", "actor", "payload_digest",
            "revision", "scope", "session_id", "txn_id", "authorization_epoch")
    return all(prior.get(k) == lease.get(k) for k in keys)


def record_active_authorization(state: Any, *, lease_id: str, command: str,
                                operation: str, actor: str, payload_digest: str,
                                scope: str, revision: int, session_id: str,
                                txn_id: str,
                                authorization_epoch: int) -> Optional[Dict[str, Any]]:
    """Record the successful prior ACTIVE current-seat business authorization for
    the EXACT tuple (DG-03 §3.2 sole issuance precondition). A lease may only be
    minted from a matching recorded authorization."""
    rec = _record(state)
    if rec is None or rec.lifecycle != LIFECYCLE_ACTIVE:
        return None
    rec.prior_auth = {
        "lease_id": str(lease_id), "command": str(command),
        "operation": str(operation), "actor": str(actor),
        "payload_digest": str(payload_digest), "revision": int(revision),
        "scope": str(scope), "session_id": str(session_id),
        "txn_id": str(txn_id), "authorization_epoch": int(authorization_epoch),
    }
    return dict(rec.prior_auth)


def issue_command_lease(state: Any, lease: CommandLease) -> Optional[CommandLease]:
    """Mint the exact single-use lease (DG-03 §3.2) — ONLY after a matching
    recorded prior ACTIVE current-seat authorization. Returns ``None`` (never a
    lease) when the sole issuance precondition is not met, so a lease presented
    without a matching prior authorization is DENIED (§3.3 #8)."""
    rec = _record(state)
    if rec is None:
        return None
    fields = {f: getattr(lease, f) for f in (
        "lease_id", "command", "operation", "actor", "payload_digest", "revision",
        "scope", "session_id", "txn_id", "authorization_epoch", "dispatch_epoch")}
    if not isinstance(rec.prior_auth, dict) or not _prior_auth_matches(rec.prior_auth, fields):
        return None
    if int(lease.dispatch_epoch) != int(lease.authorization_epoch) + 1:
        return None
    rec.command_lease = {**fields, "consumed": False}
    rec.active_txn_id = str(lease.txn_id)
    rec.lifecycle_epoch = int(lease.dispatch_epoch)
    rec.revision = int(lease.revision)
    return lease


def authorize_and_lease(state: Any, *, command: str, actor: str,
                        payload_digest: str, session_id: str, txn_id: str,
                        operation: str = OP_MUTATE, scope: Optional[str] = None,
                        revision: Optional[int] = None) -> Optional[CommandLease]:
    """Service entry used by the owning transaction: run the single ACTIVE
    current-seat business authorization for the EXACT command, record it, then
    issue the exact one-use lease (dispatch epoch = authorization epoch + 1).

    R3b F1: the recorded/leased ``scope`` and ``revision`` are derived from the
    REAL current Core business state (never the caller's GUI ``command`` label or
    the seat lifecycle epoch). Optional ``scope``/``revision`` arguments are
    accepted for signature compatibility but are ignored.

    Returns ``None`` when the state is not a registered ACTIVE current-seat
    session, so the lease is only ever a continuation of an authorized command.
    """
    rec = _record(state)
    if rec is None:
        return None
    decision = authorize_hotseat(
        state, operation, viewer=actor, command=command,
        request_context=present_context(state), payload_digest=payload_digest)
    if not decision.allowed:
        return None
    auth_epoch = rec.epoch
    auth_scope = core_business_scope(state)
    auth_revision = core_business_revision(state)
    lease_id = "ls-" + uuid.uuid4().hex
    prior = record_active_authorization(
        state, lease_id=lease_id, command=command, operation=operation,
        actor=actor, payload_digest=payload_digest, scope=auth_scope,
        revision=auth_revision, session_id=session_id, txn_id=txn_id,
        authorization_epoch=auth_epoch)
    if prior is None:
        return None
    lease = CommandLease(
        lease_id=lease_id, command=str(command), operation=str(operation),
        actor=str(actor), payload_digest=str(payload_digest),
        revision=int(auth_revision), scope=str(auth_scope),
        session_id=str(session_id), txn_id=str(txn_id),
        authorization_epoch=int(auth_epoch), dispatch_epoch=int(auth_epoch) + 1)
    issued = issue_command_lease(state, lease)
    if issued is None:
        return None
    # D4/D6 I1: register the §1.1 narrow recovery mandate in the SAME serialized
    # authorization boundary — ONLY for the five admission rows. Every other root
    # (incl. the legacy S-C population roots) registers NOTHING (default deny).
    _register_recovery_mandate_locked(
        state, rec, lease_id=issued.lease_id, command=command, actor=actor,
        payload_digest=payload_digest, auth_epoch=auth_epoch, txn_id=txn_id,
        session_id=session_id)
    return issued


def current_lease_token(state: Any) -> Optional[LeaseToken]:
    """Trusted service accessor: the live (unconsumed) lease presentation, or
    ``None``. The public boundary never fetches this; only the trusted routing
    layer presents it."""
    rec = _record(state)
    if rec is None or not isinstance(rec.command_lease, dict):
        return None
    lease = rec.command_lease
    if lease.get("consumed"):
        return None
    try:
        return LeaseToken(
            lease_id=lease["lease_id"], command=lease["command"],
            operation=lease["operation"], payload_digest=lease["payload_digest"],
            scope=lease["scope"], session_id=lease["session_id"],
            txn_id=lease["txn_id"], dispatch_epoch=lease["dispatch_epoch"])
    except KeyError:
        return None


def current_dispatch_capability(state: Any) -> Optional[DispatchCapability]:
    """Trusted service accessor: the owning transaction's live continuation scope."""
    rec = _record(state)
    if rec is None or not isinstance(rec.continuation_scope, dict):
        return None
    scope = rec.continuation_scope
    try:
        return DispatchCapability(
            txn_id=scope["txn_id"], dispatch_epoch=scope["dispatch_epoch"],
            command=scope["command"], session_id=scope["session_id"])
    except KeyError:
        return None


def _lease_match(state: Any, rec: "_SeatRecord", lease: Dict[str, Any], token: LeaseToken,
                 requested_operation: Optional[str],
                 requested_command: Optional[str],
                 requested_payload_digest: Optional[str] = None) -> Optional[str]:
    """All DG-03 §3.3 conditions 1–12 checked against the CURRENT authoritative
    Core state; returns a denial reason or ``None``."""
    if lease.get("consumed"):
        return REASON_DUPLICATE                                    # 12
    if token.lease_id != lease.get("lease_id"):
        return REASON_DUPLICATE                                    # 1
    if token.command != lease.get("command") or (
            requested_command is not None and requested_command != lease.get("command")):
        return REASON_PHASE                                       # 2
    if requested_operation is not None and requested_operation != lease.get("operation"):
        return REASON_PHASE                                       # 3
    if token.operation != lease.get("operation"):
        return REASON_PHASE                                       # 3
    # 4 — payload binding: token digest, stored digest AND the ACTUAL dispatched
    # payload digest must all agree; a missing value is a hard reject (F1).
    if not token.payload_digest or not lease.get("payload_digest") \
            or token.payload_digest != lease.get("payload_digest"):
        return REASON_PHASE
    if requested_payload_digest is not None \
            and requested_payload_digest != lease.get("payload_digest"):
        return REASON_PHASE
    # 5 — scope binding to the CURRENT authoritative Core business scope (F1).
    if not token.scope or not lease.get("scope") \
            or token.scope != lease.get("scope") \
            or token.scope != core_business_scope(state):
        return REASON_PHASE
    if token.session_id != lease.get("session_id") \
            or rec.session_id != lease.get("session_id"):
        return REASON_SESSION                                     # 6
    if token.txn_id != lease.get("txn_id") or rec.active_txn_id != lease.get("txn_id"):
        return REASON_SESSION                                     # 7
    if not isinstance(rec.prior_auth, dict) or not _prior_auth_matches(rec.prior_auth, lease):
        return REASON_PRINCIPAL                                   # 8
    # 9 — actor binding to the CURRENT authoritative Core actor (not merely the
    # registry principal copy; F1). A changed Core actor is caught here.
    actor_id, _actor_type = _authoritative_actor(state)
    if actor_id is None or actor_id != lease.get("actor"):
        return REASON_PRINCIPAL
    # 10 — business-revision binding to the CURRENT real Core business state (F1).
    if int(lease.get("revision", -1)) != core_business_revision(state):
        return REASON_EPOCH
    if int(lease.get("authorization_epoch", -1)) != int(rec.prior_auth.get(
            "authorization_epoch", -2)):
        return REASON_EPOCH
    if int(lease.get("dispatch_epoch", -1)) != int(lease.get("authorization_epoch", -2)) + 1:
        return REASON_EPOCH                                       # 11 two-epoch relation
    if int(token.dispatch_epoch) != int(lease.get("dispatch_epoch")) \
            or int(rec.lifecycle_epoch) != int(lease.get("dispatch_epoch")):
        return REASON_EPOCH                                       # 11 dispatch epoch
    return None


def consume_command_lease(state: Any, *, lease_id: Optional[str] = None,
                          helpers: Optional[Iterable[str]] = None) -> Optional[str]:
    """Atomically validate (conditions 1–12) and consume the owning transaction's
    single top-level dispatch lease, opening the non-exported transaction-local
    continuation scope (DG-03 §3.4). Returns a denial reason, or ``None`` on
    success. A consumed/cleared lease is never resurrected."""
    rec = _record(state)
    if rec is None or not isinstance(rec.command_lease, dict):
        return REASON_DUPLICATE
    lease = rec.command_lease
    if lease_id is not None and lease_id != lease.get("lease_id"):
        return REASON_DUPLICATE
    token = LeaseToken(
        lease_id=lease.get("lease_id", ""), command=lease.get("command", ""),
        operation=lease.get("operation", ""), payload_digest=lease.get("payload_digest", ""),
        scope=lease.get("scope", ""), session_id=lease.get("session_id", ""),
        txn_id=lease.get("txn_id", ""), dispatch_epoch=int(lease.get("dispatch_epoch", -1)))
    reason = _lease_match(state, rec, lease, token, lease.get("operation"),
                          lease.get("command"))
    if reason is not None:
        return reason
    lease["consumed"] = True
    # R3b F2: the continuation scope authorizes the internal HELPER chain only; the
    # owning top-level command is granted at most once via ownership, never by
    # membership in the helper set (no ambient borrow, no second owning dispatch).
    helpers_only = frozenset(str(h) for h in (helpers or ())) - {lease.get("command")}
    rec.continuation_scope = {
        "txn_id": lease.get("txn_id"), "dispatch_epoch": lease.get("dispatch_epoch"),
        "command": lease.get("command"), "session_id": lease.get("session_id"),
        "helpers": helpers_only, "owning_consumed": False,
    }
    return None


def clear_command_lease(state: Any) -> None:
    """Destroy the lease and its continuation scope (never resurrected)."""
    rec = _record(state)
    if rec is not None:
        rec.command_lease = None
        rec.continuation_scope = None


# ---------------------------------------------------------------------------
# Internal neutral activation reservation (R2 step 7 private staging).
# ---------------------------------------------------------------------------
def issue_activation_reservation(state: Any, target_player_id: str,
                                 epoch: Optional[int] = None,
                                 txn_id: str = "") -> Optional[StagingCapability]:
    """Reserve the target/revision/txn-bound internal neutral activation capability.

    R3b F3: the reservation stores the reserved ``target``, the current Core
    business ``revision`` and the owning ``txn_id``, and returns a PRIVATE
    :class:`StagingCapability`. ONLY a caller presenting that capability (validated
    against target/revision/txn) may perform the private staging READ for the
    reserved target; a bare public read that merely names the target is DENIED.
    """
    rec = _record(state)
    if rec is None:
        return None
    capability_id = _new_handle_id().replace("ctx-", "stg-")
    rec.reservation = {
        "target": str(target_player_id),
        "epoch": rec.epoch if epoch is None else int(epoch),
        "revision": core_business_revision(state),
        "txn_id": str(txn_id or ""),
        "capability_id": capability_id,
        "active": True,
    }
    return StagingCapability(
        capability_id=capability_id, session_id=rec.session_id,
        target=str(target_player_id), txn_id=str(txn_id or ""),
        revision=int(rec.reservation["revision"]), epoch=int(rec.reservation["epoch"]))


def end_activation_reservation(state: Any) -> None:
    rec = _record(state)
    if rec is not None:
        rec.reservation = None


# ---------------------------------------------------------------------------
# Masked scheduled-AI execution window (F03 / F01 §1.4A).
# ---------------------------------------------------------------------------
def begin_masked_execution(state: Any, *, txn_id: str, authorization_epoch: int,
                          phase: str, substep: str,
                          revision: int) -> Optional[Dict[str, Any]]:
    """Enter the masked execution window of the OWNING handoff transaction (F03).

    The service records the authoritative scope (txn / authorization epoch /
    phase / substep / revision) here; the AI capability predicate validates the
    presented capability against THIS scope, never against a mint-time copy. The
    public handle is revoked for the whole window (no public projection).
    """
    rec = _record(state)
    if rec is None:
        return None
    rec.lifecycle = LIFECYCLE_EXECUTING_MASKED
    rec.revoked = True
    rec.command_lease = None
    rec.reservation = None
    rec.ai_capability = None
    rec.masked_scope = {
        "txn_id": str(txn_id),
        "authorization_epoch": int(authorization_epoch),
        "phase": str(phase),
        "substep": str(substep),
        "revision": int(revision),
    }
    _bind_handle(state, rec)
    return dict(rec.masked_scope)


def end_masked_execution(state: Any,
                         lifecycle: str = LIFECYCLE_ACTIVE) -> Optional[_SeatRecord]:
    """Leave the masked execution window (commit / abort / failure / exit).

    The capability and the authoritative scope are destroyed and never
    resurrected; a retry mints a fresh capability under a fresh txn.
    """
    rec = _record(state)
    if rec is None:
        return None
    rec.masked_scope = None
    rec.ai_capability = None
    rec.lifecycle = lifecycle
    _bind_handle(state, rec)
    return rec


# ---------------------------------------------------------------------------
# Unexported service-private masked scheduled-AI capability (F01 §1.4A).
# ---------------------------------------------------------------------------
def issue_ai_capability(state: Any, *, operation: str, phase: str, substep: str,
                       revision: int, expected_actor: str, txn_id: str,
                       authorization_epoch: int) -> Optional[AICapability]:
    """Mint the masked scheduled-AI capability for ONE drain step of the owning
    transaction. Only the session service calls this at dispatch; it is never
    derived from ``state`` and never publicly requestable/exportable. Minting is
    valid ONLY inside :func:`begin_masked_execution` (EXECUTING_MASKED); the
    predicate still validates every field against the authoritative scope so a
    capability minted for a different txn/phase is rejected (F03)."""
    rec = _record(state)
    if rec is None:
        return None
    if rec.lifecycle != LIFECYCLE_EXECUTING_MASKED \
            or not isinstance(rec.masked_scope, dict):
        return None
    capability_id = _new_handle_id().replace("ctx-", "ai-")
    rec.ai_capability = {
        "capability_id": capability_id,
        "operation": str(operation),
        "phase": str(phase),
        "substep": str(substep),
        "revision": int(revision),
        "expected_actor": str(expected_actor),
        "txn_id": str(txn_id),
        "authorization_epoch": int(authorization_epoch),
        "consumed": False,
    }
    return AICapability(
        capability_id=capability_id,
        session_id=rec.session_id,
        txn_id=str(txn_id),
        operation=str(operation),
        actor="ai",
        phase=str(phase),
        substep=str(substep),
        revision=int(revision),
        authorization_epoch=int(authorization_epoch),
        lifecycle_scope=LIFECYCLE_SCOPE_EXECUTING_MASKED,
    )


def consume_ai_capability(state: Any) -> None:
    """Mark the masked AI capability consumed (once-only; a replay is denied)."""
    rec = _record(state)
    if rec is not None and rec.ai_capability is not None:
        rec.ai_capability["consumed"] = True


def revoke_ai_capability(state: Any) -> None:
    """Destroy the masked AI capability (MASKED_FAILURE / abort / exit). It is
    never resurrected; a retry mints a fresh capability under a fresh txn."""
    rec = _record(state)
    if rec is not None:
        rec.ai_capability = None


def _ai_capability_denied(rec: "_SeatRecord", state: Any, cap: AICapability,
                          *, requested_operation: Optional[str] = None,
                          requested_command: Optional[str] = None) -> Optional[str]:
    """Return a denial reason when the presented AI capability does not EXACTLY
    match the registry record AND the authoritative masked scope (F01 §1.4A / F03);
    ``None`` when every field matches.

    F03: the check is against the service's CURRENT masked scope
    (``rec.masked_scope``) plus the actual request (operation/command), NOT merely
    against the mint-time copy in ``rec.ai_capability`` — so a capability for a
    different txn/phase/revision/epoch, a different command, or a READ operation is
    rejected even if its own stored fields agree with one another.
    """
    stored = rec.ai_capability
    if not isinstance(stored, dict) or stored.get("consumed"):
        return REASON_PRINCIPAL
    # The owning transaction must currently be inside its masked execution window.
    if rec.lifecycle != LIFECYCLE_EXECUTING_MASKED:
        return REASON_LIFECYCLE
    scope = rec.masked_scope
    if not isinstance(scope, dict):
        return REASON_LIFECYCLE
    if cap.capability_id != stored.get("capability_id"):
        return REASON_PRINCIPAL  # forged / free capability
    if cap.session_id != rec.session_id:
        return REASON_SESSION
    # F03: bind to the OWNING transaction (authoritative scope, not the mint copy).
    if cap.txn_id != scope.get("txn_id") or cap.txn_id != stored.get("txn_id"):
        return REASON_SESSION
    if cap.operation != stored.get("operation"):
        return REASON_PHASE  # operation widening inside the record
    if cap.actor != "ai":
        return REASON_PRINCIPAL
    # F03: the ACTUAL request must be the exact operation/command (a capability for
    # 'next_player' cannot satisfy a different command, and never a READ op).
    if requested_operation in READ_OPERATIONS:
        return REASON_PHASE
    if requested_command is not None and requested_command != cap.operation:
        return REASON_PHASE
    actor, actor_type = _authoritative_actor(state)
    if actor_type != "ai" or actor is None or actor != stored.get("expected_actor"):
        return REASON_PRINCIPAL  # not the scheduled current AI actor
    # F03: authoritative service scope (phase/substep/revision/epoch).
    if cap.phase != scope.get("phase") or cap.phase != stored.get("phase"):
        return REASON_PHASE
    if cap.substep != scope.get("substep") or cap.substep != stored.get("substep"):
        return REASON_PHASE
    if cap.revision != scope.get("revision") or cap.revision != stored.get("revision"):
        return REASON_EPOCH
    if cap.authorization_epoch != scope.get("authorization_epoch") \
            or cap.authorization_epoch != stored.get("authorization_epoch"):
        return REASON_EPOCH
    if cap.lifecycle_scope != LIFECYCLE_SCOPE_EXECUTING_MASKED:
        return REASON_LIFECYCLE
    return None


# ---------------------------------------------------------------------------
# Recovery authority family (D4/D6 I1 — PC-RA-01/02/03/04/05, Owner-approved).
#
# Additive and service-private. A ``RecoveryMandate`` is registered ONLY on a
# successful original ACTIVE exact authorization of one of the five RA Delta
# §1.1 admission rows. It is NOT a receipt, NOT a business ledger and NOT
# derivable from a failure / ``failureRoute`` / "the current actor is AI" fact.
# After a PROVEN post-commit failure the mandate may be sealed
# ``FAILED_RECOVERABLE``; a single-use ``RecoveryAttemptCapability`` then opens a
# FRESH ``RecoveryDispatchScope`` (never the destroyed lease / continuation
# scope). Every entry still passes the single public guard: the new recovery
# branch is inert unless a service-private possession (an explicit cap or a live
# fresh scope) is presented, and it is never derived from ``state``/DTO/viewer.
# ---------------------------------------------------------------------------
RECOVERY_ROOT = "recover_continuation"

RESUME_ENTRY_PENDING = "ENTRY_PENDING"
RESUME_CONTINUATION_PENDING = "CONTINUATION_PENDING"
RESUME_TERMINAL_PENDING = "TERMINAL_PENDING"
RESUME_DELIVERY_PENDING = "DELIVERY_PENDING"

RECOVERY_RESUME_KINDS = frozenset({
    RESUME_ENTRY_PENDING, RESUME_CONTINUATION_PENDING,
    RESUME_TERMINAL_PENDING, RESUME_DELIVERY_PENDING,
})

MANDATE_ARMED = "ARMED"
MANDATE_FAILED_RECOVERABLE = "FAILED_RECOVERABLE"
MANDATE_CLOSED = "CLOSED"
MANDATE_REVOKED = "REVOKED"

RECOVERY_POLICY_VERSION = "RA-rev2"

#: RA Delta §1.1 canonical finite opt-in admission (the ONLY original-auth roots
#: that register a mandate). Value = (policy_id, permitted resume-kind closed set,
#: permitted source->target phase transition). Every other root is EXCLUDE — the
#: legacy S-C population roots and all ordinary commands register NOTHING.
_RECOVERY_ADMISSION: Dict[str, Any] = {
    "advance_forum_phase": (
        "RA-A01",
        frozenset({RESUME_ENTRY_PENDING, RESUME_CONTINUATION_PENDING,
                   RESUME_DELIVERY_PENDING}),
        "forum->population",
    ),
    "advance_population_phase": (
        "RA-A02",
        frozenset({RESUME_ENTRY_PENDING, RESUME_CONTINUATION_PENDING,
                   RESUME_TERMINAL_PENDING, RESUME_DELIVERY_PENDING}),
        "population->senate",
    ),
    "propose_many": (
        "RA-A03",
        frozenset({RESUME_CONTINUATION_PENDING, RESUME_TERMINAL_PENDING,
                   RESUME_DELIVERY_PENDING}),
        "senate-stop",
    ),
    "vote": (
        "RA-A04",
        frozenset({RESUME_CONTINUATION_PENDING, RESUME_TERMINAL_PENDING,
                   RESUME_DELIVERY_PENDING}),
        "senate-stop",
    ),
    "veto": (
        "RA-A05",
        frozenset({RESUME_TERMINAL_PENDING, RESUME_DELIVERY_PENDING}),
        "senate-stop",
    ),
}

#: recovery root x resume-kind -> the ONLY internal guarded edges reachable
#: inside that recovery dispatch (design §4.1.3, expanded per resume-kind). The
#: recovery root itself is always admissible and is NOT listed here; the five
#: normal roots are NEVER in this registry (strict separation).
_RECOVERY_EDGE_POLICIES: Dict[Any, frozenset] = {
    (RECOVERY_ROOT, RESUME_ENTRY_PENDING): frozenset({
        "begin_population_phase", "archive_office_holders",
        "convert_battlefield_commanders", "process_population_disbandments",
    }),
    (RECOVERY_ROOT, RESUME_CONTINUATION_PENDING): frozenset({
        "campaign", "vote", "resolve_election",
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
    }),
    (RECOVERY_ROOT, RESUME_TERMINAL_PENDING): frozenset({
        "finalize_senate_if_ready", "assign_governors",
    }),
    (RECOVERY_ROOT, RESUME_DELIVERY_PENDING): frozenset(),
}


@dataclass(frozen=True)
class RecoveryMandate:
    """Service-private registration object (RA Delta §3.1); never exported."""

    mandate_id: str
    session_id: str
    original_authorization_id: str
    original_actor: str
    original_command: str
    original_payload_digest: str
    original_auth_epoch: int
    original_dispatch_txn: str
    permitted_resume_kind: frozenset
    permitted_phase_transition: str
    policy_id: str = ""
    policy_version: str = RECOVERY_POLICY_VERSION
    status: str = MANDATE_ARMED


@dataclass(frozen=True)
class RecoveryInvocationHandle:
    """Private possession (possession, not a public handle / not a live scope)."""

    handle_id: str
    mandate_id: str
    session_id: str


@dataclass(frozen=True)
class RecoveryAttemptCapability:
    """One-use opaque attempt capability (registry identity, not a dict)."""

    attempt_id: str
    mandate_id: str
    session_id: str
    resume_kind: str = ""
    root: str = RECOVERY_ROOT
    failure_generation: int = 0


@dataclass(frozen=True)
class RecoveryDispatchScope:
    """The FRESH recovery dispatch scope (never the old lease/continuation)."""

    fresh_scope_id: str
    attempt_id: str
    mandate_id: str
    session_id: str
    resume_kind: str
    root: str = RECOVERY_ROOT
    active: bool = True


def recovery_admission_for(command: Optional[str]):
    """The §1.1 admission row for ``command`` (or ``None``). Never derived from
    a helper union / an OP label / a business success."""
    if command is None:
        return None
    return _RECOVERY_ADMISSION.get(str(command))


def recovery_edge_allowed(resume_kind: str, label: Optional[str]) -> bool:
    """True iff ``label`` is an admissible internal edge for the recovery root
    under ``resume_kind`` (the recovery root itself is always admissible)."""
    if label is None:
        return False
    if label == RECOVERY_ROOT:
        return True
    return label in _RECOVERY_EDGE_POLICIES.get(
        (RECOVERY_ROOT, resume_kind), frozenset())


def _revoke_recovery_family(rec: "_SeatRecord") -> None:
    """Tear down the whole recovery family (exit/revoke/unregister/principal
    change). The old scope/attempt are permanently destroyed — never resurrected."""
    rec.recovery_scope = None
    rec.recovery_attempt = None
    rec.recovery_invocation = None
    rec.recovery_mandate = None


def _register_recovery_mandate_locked(state: Any, rec: "_SeatRecord", *,
                                      lease_id: str, command: str, actor: str,
                                      payload_digest: str, auth_epoch: int,
                                      txn_id: str, session_id: str
                                      ) -> Optional[Dict[str, Any]]:
    """Register the §1.1 narrow mandate inside the serialized authorization
    boundary. Unknown / non-opt-in root -> NO mandate (default deny)."""
    row = recovery_admission_for(command)
    if row is None:
        return None
    policy_id, resume_kinds, transition = row
    mandate_id = "rm-" + uuid.uuid4().hex
    rec.recovery_mandate = {
        "mandate_id": mandate_id,
        "policy_id": policy_id,
        "session_id": str(session_id),
        "original_authorization_id": str(lease_id),
        "original_actor": str(actor),
        "original_command": str(command),
        "original_payload_digest": str(payload_digest),
        "original_auth_epoch": int(auth_epoch),
        "original_dispatch_txn": str(txn_id),
        "permitted_resume_kind": frozenset(resume_kinds),
        "permitted_phase_transition": transition,
        "policy_version": RECOVERY_POLICY_VERSION,
        "status": MANDATE_ARMED,
        "failure_generation": 0,
    }
    # THE private possession, placed at trusted binding time (never read off a DTO
    # or a caller-supplied state argument).
    rec.recovery_invocation = {
        "handle_id": _new_handle_id().replace("ctx-", "rmi-"),
        "mandate_id": mandate_id,
        "session_id": str(session_id),
    }
    # a fresh authorization supersedes any prior attempt/scope (no resurrection)
    rec.recovery_attempt = None
    rec.recovery_scope = None
    return dict(rec.recovery_mandate)


def recovery_mandate(state: Any) -> Optional[RecoveryMandate]:
    """Read-only audit view of the current mandate (never an authorization)."""
    rec = _record(state)
    if rec is None or not isinstance(rec.recovery_mandate, dict):
        return None
    m = rec.recovery_mandate
    return RecoveryMandate(
        mandate_id=m.get("mandate_id", ""),
        session_id=m.get("session_id", ""),
        original_authorization_id=m.get("original_authorization_id", ""),
        original_actor=m.get("original_actor", ""),
        original_command=m.get("original_command", ""),
        original_payload_digest=m.get("original_payload_digest", ""),
        original_auth_epoch=int(m.get("original_auth_epoch", -1)),
        original_dispatch_txn=m.get("original_dispatch_txn", ""),
        permitted_resume_kind=m.get("permitted_resume_kind") or frozenset(),
        permitted_phase_transition=m.get("permitted_phase_transition", ""),
        policy_id=m.get("policy_id", ""),
        policy_version=m.get("policy_version", RECOVERY_POLICY_VERSION),
        status=m.get("status", ""),
    )


def current_recovery_invocation(state: Any) -> Optional[RecoveryInvocationHandle]:
    """Trusted service accessor: the private possession the trusted routing layer
    may present. NEVER auto-fetched by a boundary and never read off a DTO."""
    rec = _record(state)
    if rec is None or not isinstance(rec.recovery_invocation, dict):
        return None
    inv = rec.recovery_invocation
    return RecoveryInvocationHandle(
        handle_id=inv.get("handle_id", ""),
        mandate_id=inv.get("mandate_id", ""),
        session_id=inv.get("session_id", ""))


def has_failed_recoverable_mandate(state: Any) -> bool:
    """True iff a mandate is sealed FAILED_RECOVERABLE (the only state from which
    an attempt may be minted). A mandate-less (legacy) session is always False."""
    rec = _record(state)
    return bool(rec is not None and isinstance(rec.recovery_mandate, dict)
                and rec.recovery_mandate.get("status") == MANDATE_FAILED_RECOVERABLE)


def determinate_recovery_resume_kind(state: Any) -> Optional[str]:
    """The resume-kind ONLY when the sealed mandate's permitted set is a
    singleton. A multi-kind mandate requires the real owner checkpoint (I2) to
    choose; in I1 the Store intent therefore fails closed (never a caller pick)."""
    rec = _record(state)
    if rec is None or not isinstance(rec.recovery_mandate, dict):
        return None
    if rec.recovery_mandate.get("status") != MANDATE_FAILED_RECOVERABLE:
        return None
    kinds = rec.recovery_mandate.get("permitted_resume_kind") or frozenset()
    if len(kinds) == 1:
        return next(iter(kinds))
    return None


def seal_recovery_mandate_for_failure(state: Any, *,
                                      failure_generation: int = 1) -> bool:
    """Owner-commit hook: mark the CURRENT armed mandate FAILED_RECOVERABLE.

    Called ONLY by the real owner/coordinator commit path (wired in I2) after a
    PROVEN, uncompleted post-commit failure. Without an armed mandate (a legacy
    deployment-before session) nothing is sealed — the seat simply stays masked.
    """
    rec = _record(state)
    if rec is None or not isinstance(rec.recovery_mandate, dict):
        return False
    if rec.recovery_mandate.get("status") != MANDATE_ARMED:
        return False
    rec.recovery_mandate["status"] = MANDATE_FAILED_RECOVERABLE
    rec.recovery_mandate["failure_generation"] = int(failure_generation)
    return True


def issue_recovery_attempt(state: Any, *, resume_kind: str
                           ) -> Optional[RecoveryAttemptCapability]:
    """Mint the ONE single-use attempt cap. Requires a sealed FAILED_RECOVERABLE
    mandate, no live attempt, and ``resume_kind`` inside the mandate's permitted
    closed set (an illegal kind / phase chain is refused without side effects)."""
    rec = _record(state)
    if rec is None or not isinstance(rec.recovery_mandate, dict):
        return None
    m = rec.recovery_mandate
    if m.get("status") != MANDATE_FAILED_RECOVERABLE:
        return None
    if resume_kind not in (m.get("permitted_resume_kind") or frozenset()):
        return None
    prior = rec.recovery_attempt
    if isinstance(prior, dict) and not prior.get("consumed"):
        return None  # one current attempt only
    attempt_id = "ra-" + uuid.uuid4().hex
    rec.recovery_attempt = {
        "attempt_id": attempt_id,
        "mandate_id": m.get("mandate_id"),
        "session_id": rec.session_id,
        "root": RECOVERY_ROOT,
        "resume_kind": str(resume_kind),
        "failure_generation": int(m.get("failure_generation", 0)),
        "consumed": False,
    }
    return RecoveryAttemptCapability(
        attempt_id=attempt_id, mandate_id=m.get("mandate_id", ""),
        session_id=rec.session_id, resume_kind=str(resume_kind),
        failure_generation=int(m.get("failure_generation", 0)))


def claim_recovery_attempt(state: Any, capability: RecoveryAttemptCapability
                          ) -> Optional[RecoveryDispatchScope]:
    """Atomic claim/consume (the API guard's role, before any owner action):
    validate the presented cap against the registry identity + mandate + session
    + root, consume it EXACTLY once, and open a FRESH RecoveryDispatchScope.
    A second claim, any mismatch, or a non-FAILED_RECOVERABLE mandate denies."""
    rec = _record(state)
    if rec is None or capability is None:
        return None
    attempt = rec.recovery_attempt
    if not isinstance(attempt, dict) or attempt.get("consumed"):
        return None
    if capability.attempt_id != attempt.get("attempt_id"):
        return None
    if capability.mandate_id != attempt.get("mandate_id"):
        return None
    if capability.session_id != rec.session_id:
        return None
    if capability.root != RECOVERY_ROOT:
        return None
    m = rec.recovery_mandate
    if not isinstance(m, dict) or m.get("status") != MANDATE_FAILED_RECOVERABLE:
        return None
    attempt["consumed"] = True
    scope_id = "rsc-" + uuid.uuid4().hex
    rec.recovery_scope = {
        "fresh_scope_id": scope_id,
        "attempt_id": attempt.get("attempt_id"),
        "mandate_id": attempt.get("mandate_id"),
        "session_id": rec.session_id,
        "resume_kind": attempt.get("resume_kind"),
        "root": RECOVERY_ROOT,
        "active": True,
    }
    opened = RecoveryDispatchScope(
        fresh_scope_id=scope_id, attempt_id=attempt.get("attempt_id", ""),
        mandate_id=attempt.get("mandate_id", ""), session_id=rec.session_id,
        resume_kind=attempt.get("resume_kind", ""))
    return opened


def close_recovery_scope(state: Any) -> None:
    """Close the fresh dispatch scope (FINISH/finally). Never resurrected."""
    rec = _record(state)
    if rec is not None:
        rec.recovery_scope = None


# -- private recovery possession (thread-local, never derived from state) -----
def begin_recovery_nesting(state: Any,
                           capability: Optional[RecoveryAttemptCapability]) -> None:
    """Arm the private recovery possession around the single intent dispatch.
    Only the trusted routing layer calls this; a public call outside the window
    possesses nothing and is adjudicated by the ordinary branches."""
    if capability is not None:
        _nesting_entry(state)["recovery_cap"] = capability


def end_recovery_nesting(state: Any) -> None:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    if store is not None and _key(state) in store:
        store[_key(state)].pop("recovery_cap", None)
        store[_key(state)].pop("recovery_scope", None)


def _arm_recovery_scope_nesting(state: Any, scope: RecoveryDispatchScope) -> None:
    _nesting_entry(state)["recovery_scope"] = scope


def _nesting_recovery_capability(state: Any) -> Optional[RecoveryAttemptCapability]:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    entry = store.get(_key(state)) if store else None
    return entry.get("recovery_cap") if entry else None


def _nesting_recovery_scope(state: Any) -> Optional[RecoveryDispatchScope]:
    store = getattr(_NESTING_LOCAL, "by_state", None)
    entry = store.get(_key(state)) if store else None
    return entry.get("recovery_scope") if entry else None


def _recovery_decision(state: Any, rec: "_SeatRecord", operation: str,
                       command: Optional[str],
                       capability: Optional[RecoveryAttemptCapability],
                       scope: Optional[RecoveryDispatchScope],
                       arm_scope: bool = False) -> "AccessDecision":
    """The precise, additive recovery branch. Two shapes:

    (a) a LIVE fresh scope possession authorizes the recovery root plus ONLY the
        internal guarded edges allowed for that scope's resume-kind (a different
        resume-kind's edge, an unrelated root, or a scope outside its txn is
        DENIED);
    (b) otherwise a presented (unconsumed) cap on the recovery root consumes and
        opens the fresh scope (the owner-action consuming boundary), then allows.

    No cap and no live scope -> DENY (never a None-viewer / route / current-AI /
    failure default)."""
    rs = rec.recovery_scope
    if isinstance(rs, dict) and rs.get("active") and scope is not None \
            and scope.fresh_scope_id == rs.get("fresh_scope_id") \
            and scope.session_id == rec.session_id \
            and scope.root == RECOVERY_ROOT:
        if recovery_edge_allowed(rs.get("resume_kind"), command):
            return _allow(operation, exempt="recovery",
                          scope_id=rs.get("fresh_scope_id"),
                          resume_kind=rs.get("resume_kind"))
        return _deny(REASON_PHASE, operation)
    if command != RECOVERY_ROOT or capability is None:
        return _deny(REASON_PRINCIPAL, operation)
    m = rec.recovery_mandate
    if not isinstance(m, dict) or m.get("status") != MANDATE_FAILED_RECOVERABLE:
        return _deny(REASON_LIFECYCLE, operation)
    opened = claim_recovery_attempt(state, capability)
    if opened is None:
        return _deny(REASON_DUPLICATE, operation)
    if arm_scope:
        # Armed by the trusted routing layer's window: the fresh scope becomes the
        # possession that authorizes the root + its allowed internal edges for the
        # remainder of the ONE dispatch (cleared by end_recovery_nesting).
        _arm_recovery_scope_nesting(state, opened)
    return _allow(operation, exempt="recovery",
                  scope_id=opened.fresh_scope_id, resume_kind=opened.resume_kind)


# ---------------------------------------------------------------------------
# Decision object.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str = ""
    operation: str = ""
    exempt: str = ""  # "" | "cli" | "ai" | "lease" | "reservation"
    details: Dict[str, Any] = field(default_factory=dict)

    def denial(self, message: str = DENIED_MESSAGE) -> Dict[str, Any]:
        return denied_response(self.reason or REASON_SESSION, message)


def _allow(operation: str, exempt: str = "", **details: Any) -> AccessDecision:
    return AccessDecision(True, "", operation, exempt, dict(details))


def _deny(reason: str, operation: str, **details: Any) -> AccessDecision:
    return AccessDecision(False, reason, operation, "", dict(details))


def _authoritative_actor(state: Any):
    """(player_id, actor_type_value) for the Core-authoritative current actor."""
    current = None
    getter = getattr(state, "get_current_player", None)
    if callable(getter):
        current = getter()
    if current is None:
        return None, None
    actor_type = getattr(getattr(current, "player_type", None), "value", None)
    return getattr(current, "player_id", None), actor_type


def _is_human(actor_type: Optional[str]) -> bool:
    return actor_type == "human"


def _config_bypass(state: Any) -> bool:
    """True when the global ``testing.bypass_player_check`` toggle is on (F2).

    The toggle is a Core/test config knob; on a registered Hot-seat PUBLIC request
    it must NOT grant seat authority (a HUMAN cannot flip a global switch to obtain
    the authority of another seat).
    """
    try:
        return bool(state.config.get("testing.bypass_player_check", False))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The single predicate.
# ---------------------------------------------------------------------------
def authorize_hotseat(
    state: Any,
    operation: str,
    *,
    viewer: Optional[str] = None,
    target_player_id: Optional[str] = None,
    request_context: Optional[HotseatContext] = None,
    ai_capability: Optional[AICapability] = None,
    authoritative_phase: Optional[str] = None,
    claim_phase: Optional[str] = None,
    phase_revision_current: Optional[bool] = None,
    command: Optional[str] = None,
    payload_digest: Optional[str] = None,
    lease_token: Optional[LeaseToken] = None,
    dispatch_capability: Optional[DispatchCapability] = None,
    staging_capability: Optional[StagingCapability] = None,
    recovery_capability: Optional[RecoveryAttemptCapability] = None,
    recovery_dispatch_scope: Optional[RecoveryDispatchScope] = None,
    requested_bypass: bool = False,
) -> AccessDecision:
    """Authorize one public API operation against a registered Hot-seat session.

    A never-registered state is CLI-exempt (allow). A *registered* state:

      1. may use the internal neutral activation reservation for a private read of
         the reserved target only (no public exposure);
      2. may execute the exact prior-authorized one-use command lease once;
      3. allows the scheduled current AI actor a mutation (unexported AI capability);
      4. otherwise REQUIRES a presented, service-issued opaque context
         (:func:`present_context`): a missing context DENIES, and the presented
         context's issuance identity / session / principal / revoked flag /
         lifecycle / epoch must match the authoritative registry record.
    """
    rec = _record(state)

    # -- CLI exemption: never registered → historical permissions -------------
    if rec is None:
        return _allow(operation, exempt="cli")

    # -- 1. internal neutral activation reservation (private staging reads) ----
    # R3b F3: the reservation is a PRIVATE capability. A public READ can no longer
    # borrow staging authority merely by naming the reserved ``viewer`` target; the
    # caller must PRESENT the service-private staging capability (``staging_capability``)
    # validated against the reservation's target / revision / txn.
    if rec.reservation is not None and rec.reservation.get("active"):
        cap = staging_capability or _nesting_staging_capability(state)
        if _staging_capability_ok(rec, cap, operation, viewer):
            return _allow(operation, exempt="reservation",
                          target=rec.reservation.get("target"))
        return _deny(REASON_LIFECYCLE, operation)

    # -- 2. exact prior-authorized one-use command lease / txn-local scope ----
    # DG-03 §3.3/§3.4: a STRUCTURED lease token is matched conditions 1–12 (no
    # label-set membership; a missing payload_digest/scope/epoch is a hard
    # reject). Once consumed, the owning transaction's single top-level dispatch
    # and its internal helper chain are authorized by the non-exported
    # transaction-local continuation scope, never by a re-presentable lease.
    if lease_token is not None:
        if not isinstance(rec.command_lease, dict):
            return _deny(REASON_DUPLICATE, operation)
        reason = _lease_match(state, rec, rec.command_lease, lease_token, operation,
                              command, payload_digest)
        if reason is None:
            return _allow(operation, exempt="lease", command=command,
                          lease_id=lease_token.lease_id)
        return _deny(reason, operation)
    cont = _continuation_decision(state, rec, operation, command, dispatch_capability)
    if cont is not None:
        return cont

    # -- 3. unexported AI-internal capability (F01 §1.4A — capability-gated) ---
    # NEVER satisfied by the state fact that the current actor happens to be AI.
    # Admitted ONLY when the trusted internal masked drain EXPLICITLY presents the
    # service-private scheduled-AI capability and every field matches the registry.
    # An ordinary public request (ai_capability is None) gains nothing here and
    # falls through to branch 4 (presented HUMAN context) — a public mutation while
    # the seat is SUSPENDING/masked/failure is DENIED even if Core's actor is AI.
    if ai_capability is not None:
        ai_reason = _ai_capability_denied(
            rec, state, ai_capability,
            requested_operation=operation, requested_command=command)
        if ai_reason is None:
            return _allow(operation, exempt="ai", principal=ai_capability.actor)
        return _deny(ai_reason, operation)

    # -- 3.5 exact recovery authority branch (D4/D6 I1 — PC-RA-01/04/05) -------
    # Additive. INERT unless a service-private possession is explicitly PRESENTED
    # (an attempt cap or a live fresh recovery scope, possibly via the private
    # thread-local possession the trusted routing layer armed). It is NEVER
    # derived from the seat's failure state, a failureRoute string, a None
    # viewer, or the fact that the current actor happens to be AI.
    rec_cap = recovery_capability or _nesting_recovery_capability(state)
    rec_scope = recovery_dispatch_scope or _nesting_recovery_scope(state)
    if rec_cap is not None or rec_scope is not None:
        # The fresh scope is armed into the private possession ONLY when the cap
        # came from the trusted routing layer's window (never for a bare explicit
        # cap presentation, so a second direct dispatch of the same cap still
        # fails closed once the cap is consumed).
        arm_scope = (recovery_capability is None
                     and recovery_dispatch_scope is None
                     and rec_cap is not None)
        return _recovery_decision(state, rec, operation, command, rec_cap,
                                  rec_scope, arm_scope=arm_scope)

    # -- 4. presented service-issued opaque context (mandatory) ---------------
    # F2: a public request must NEVER self-grant authority with a bypass flag or a
    # global ``testing.bypass_player_check`` toggle — the public boundary cannot be
    # exempted by the request. (CLI-unregistered states keep the historical path
    # via branch 0; the AI/lease/reservation exemptions are their own branches.)
    if requested_bypass or _config_bypass(state):
        return _deny(REASON_PRINCIPAL, operation)
    if request_context is None:
        # Omission must not silently become CLI mode (SB-V02).
        return _deny(REASON_SESSION, operation)

    # 4a. issuance identity + session + revoked (authenticity of the handle)
    if request_context.handle_id != rec.handle_id:
        return _deny(REASON_SESSION, operation)
    if request_context.session_id != rec.session_id:
        return _deny(REASON_SESSION, operation)
    if rec.revoked or request_context.revoked:
        return _deny(REASON_SESSION, operation)

    # 4b. lifecycle + epoch
    if rec.lifecycle != LIFECYCLE_ACTIVE:
        return _deny(REASON_LIFECYCLE, operation)
    if request_context.lifecycle != rec.lifecycle:
        return _deny(REASON_LIFECYCLE, operation)
    if request_context.epoch != rec.epoch:
        return _deny(REASON_EPOCH, operation)

    # 4c. principal claim matches the registry
    if request_context.principal_player_id != rec.principal_player_id:
        return _deny(REASON_PRINCIPAL, operation)

    # -- 5. principal == authoritative current HUMAN actor --------------------
    actor_id, actor_type = _authoritative_actor(state)
    if actor_id is None:
        return _deny(REASON_LIFECYCLE, operation)
    if actor_id != rec.principal_player_id:
        return _deny(REASON_PRINCIPAL, operation)
    if not _is_human(actor_type):
        return _deny(REASON_PRINCIPAL, operation)

    # -- 6. claimed viewer/target equals principal ----------------------------
    if viewer is not None and viewer != rec.principal_player_id:
        return _deny(REASON_PRINCIPAL, operation)
    if target_player_id is not None and target_player_id != rec.principal_player_id:
        return _deny(REASON_PRINCIPAL, operation)

    # -- 7. owner-supplied phase claim ----------------------------------------
    if phase_revision_current is False:
        return _deny(REASON_PHASE, operation)
    if claim_phase is not None and authoritative_phase is not None \
            and claim_phase != authoritative_phase:
        return _deny(REASON_PHASE, operation)

    return _allow(operation, principal=rec.principal_player_id, epoch=rec.epoch)


def authorize_ai(
    state: Any,
    actor_id: str,
    operation: str,
    *,
    ai_capability: Optional[AICapability] = None,
) -> AccessDecision:
    """Unexported AI-internal capability (narrow preserved exemption, F01 §1.4A).

    Allowed only when the caller EXPLICITLY presents the service-private masked
    scheduled-AI capability (``ai_capability``) and every field exactly matches the
    owning masked transaction, AND the actor is the scheduled current AI actor. A
    HUMAN cannot obtain it by passing ``bypass_permission`` or a global config
    toggle; the mere state fact "current actor is AI" is NOT sufficient.
    """
    # A never-registered state keeps the historical CLI behaviour (no AI gate).
    if _record(state) is None:
        return _allow(operation, exempt="cli")
    if ai_capability is None:
        return _deny(REASON_PRINCIPAL, operation, capability="ai")
    rec = _record(state)
    reason = _ai_capability_denied(rec, state, ai_capability,
                                   requested_operation=operation)
    if reason is not None:
        return _deny(reason, operation, capability="ai")
    actor, _actor_type = _authoritative_actor(state)
    if actor is None or actor != actor_id:
        return _deny(REASON_PRINCIPAL, operation, capability="ai")
    return _allow(operation, exempt="ai", principal=actor)


# ---------------------------------------------------------------------------
# Boundary helpers — one call at each public edge.
# ---------------------------------------------------------------------------
def present_decision(state: Any, operation: str, *, caller_context=None,
                     ai_capability=None, lease_token=None, dispatch_capability=None,
                     recovery_capability=None, recovery_dispatch_scope=None,
                     **kwargs: Any) -> AccessDecision:
    """Predicate form that passes through the EXPLICITLY presented capability.

    DG-01 §1.2: the boundary passes whatever it was given and MUST NOT fetch the
    handle off ``state`` (the old ``present_context(state)`` auto-fill is removed).
    A registered Hot-seat state therefore DENIES when ``caller_context`` is omitted;
    the trusted routing layer (Adapter/Store/App) is the only presenter.
    """
    return authorize_hotseat(state, operation, request_context=caller_context,
                             ai_capability=ai_capability, lease_token=lease_token,
                             dispatch_capability=dispatch_capability,
                             recovery_capability=recovery_capability,
                             recovery_dispatch_scope=recovery_dispatch_scope,
                             **kwargs)


def denied_or_none(state: Any, operation: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Return the structured DENIED envelope, or ``None`` when authorized.

    Thin wrapper so each API boundary reads::

        denied = session_access.denied_or_none(state, session_access.OP_READ_SNAPSHOT,
                                               viewer=viewer_player_id)
        if denied is not None:
            return denied
    """
    decision = present_decision(state, operation, **kwargs)
    if decision.allowed:
        return None
    return decision.denial()


def authorize_or_deny(state: Any, operation: str, **kwargs: Any) -> AccessDecision:
    """Predicate form for callers that need the decision object (audit/logs)."""
    return present_decision(state, operation, **kwargs)


def authorize_public(state: Any, operation: str, *,
                     command: Optional[str] = None,
                     payload_digest: Optional[str] = None,
                     viewer: Optional[str] = None,
                     target_player_id: Optional[str] = None,
                     caller_context: Optional[HotseatContext] = None,
                     ai_capability: Optional[AICapability] = None,
                     lease_token: Optional[LeaseToken] = None,
                     dispatch_capability: Optional[DispatchCapability] = None,
                     staging_capability: Optional[StagingCapability] = None,
                     recovery_capability: Optional[RecoveryAttemptCapability] = None,
                     recovery_dispatch_scope: Optional[RecoveryDispatchScope] = None,
                     requested_bypass: bool = False) -> AccessDecision:
    """Convenience predicate for a *direct* public mutation/helper endpoint.

    Same single policy; explicitly names the endpoint ``command`` label so the
    exact-command lease can authorize the one prior-authorized transition, and
    passes through the explicitly presented ``caller_context`` / ``ai_capability``
    (no boundary-side auto-fill, DG-01).
    """
    return present_decision(
        state, operation, viewer=viewer, target_player_id=target_player_id,
        command=command, payload_digest=payload_digest,
        caller_context=caller_context, ai_capability=ai_capability,
        lease_token=lease_token, dispatch_capability=dispatch_capability,
        staging_capability=staging_capability,
        recovery_capability=recovery_capability,
        recovery_dispatch_scope=recovery_dispatch_scope,
        requested_bypass=requested_bypass)


# ---------------------------------------------------------------------------
# Boundary decorator (DG-01 §1.2b) — ONE keyword-only presentation per endpoint.
# ---------------------------------------------------------------------------
def _bound_arg(fn: Callable, args: tuple, kwargs: dict, name: Optional[str]):
    if name is None:
        return None
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return None
    return bound.arguments.get(name)


def guarded(operation: str, *, command: Optional[str] = None,
            viewer_param: Optional[str] = None,
            target_param: Optional[str] = None,
            bypass_param: Optional[str] = "bypass_permission") -> Callable:
    """Decorate a public API boundary with the single access predicate.

    Adds ONE trailing keyword-only presentation (``caller_context`` and, for the
    masked drain, ``ai_capability``); runs :func:`authorize_hotseat` BEFORE any DTO
    build / mutation and returns the ordinary DENIED envelope on refusal. The
    boundary forwards the presented context to inner continuations when it declares
    a ``caller_context`` parameter (threaded-down internal continuation, DG-01
    §1.3). It never fetches the handle off ``state``.
    """
    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)
        forward_cc = "caller_context" in sig.parameters
        forward_ai = "ai_capability" in sig.parameters

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            caller_context = kwargs.pop("caller_context", None)
            ai_capability = kwargs.pop("ai_capability", None)
            lease_token = kwargs.pop("lease_token", None)
            dispatch_capability = kwargs.pop("dispatch_capability", None)
            staging_capability = kwargs.pop("staging_capability", None)
            state = args[0] if args else kwargs.get("state")
            viewer = _bound_arg(fn, args, kwargs, viewer_param)
            target = _bound_arg(fn, args, kwargs, target_param)
            requested_bypass = bool(_bound_arg(fn, args, kwargs, bypass_param))
            decision = authorize_hotseat(
                state, operation, viewer=viewer, target_player_id=target,
                request_context=caller_context, command=command,
                ai_capability=ai_capability, lease_token=lease_token,
                dispatch_capability=dispatch_capability,
                staging_capability=staging_capability,
                requested_bypass=requested_bypass)
            if not decision.allowed:
                return decision.denial()
            if forward_cc:
                kwargs["caller_context"] = caller_context
            if ai_capability is not None and forward_ai:
                kwargs["ai_capability"] = ai_capability
            return fn(*args, **kwargs)

        return wrapper

    return decorator
