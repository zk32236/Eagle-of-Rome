"""src/api/session_turn_service.py
EOR20261013-02 GUI Readiness — slice S-C (coordination / seven-phase + AI drain).

ONE authoritative phase-completion coordinator + ONE session/Core completion
ledger, implementing the FROZEN S-C design:

  * ``02-sa-design/S-C-Coordination-Design-Delta.md``            (§1–§4)
  * ``02-sa-design/S-C_Implementation_and_Test_Overlay.md``      (§1.1 write face,
    §2 negative matrix, §2.1/.R/.RR-03A N7-R/N10-R, §3 five-column AC closure)

Design invariants implemented here (do NOT relax):
  * AI criterion = ``PlayerType.AI`` via ``actor -> faction -> PlayerType``
    resolver. NEVER ``player_id != viewer``, NEVER viewer-relative political
    ``mode``, NEVER ``player_type.value != "human"`` (that admits OBSERVER).
  * ONE ledger: stable obligation identity ``OID`` + once-only dispatch key ``DK``
    anchored at the PRE-command revision + revision anchors
    (``entry_revision`` / ``satisfied_at_revision``). No second ledger, no viewer
    cache (delta §2.2).
  * ``select_actor`` is the sole Hot-seat cursor writer; ``complete_actor`` writes
    a completion record ONLY from a phase-owner command receipt or an
    owner-declared explicit no-action completion.
  * ``continue_after_command`` is the sole automatic continuation: bounded
    (R + T, strictly-decreasing progress), skips satisfied ``OID``s, denies
    same-revision ``DK`` replays, and stops with a MASKED safe failure on
    no-progress / missing decider / unresolved mandatory AI vote.
  * ``phase_ready`` is the exact all-controller predicate; public resolver denial
    MUST precede its business mutation.
  * ``enter_phase`` consumes a successfully COMMITTED phase-advance receipt
    EXACTLY ONCE; visual navigation is not phase entry.

Ledger placement: session/Core turn state (attached to the GameState), never the
viewer cache — a viewer cache reset must not erase completion truth.
"""

from __future__ import annotations

import logging
import types
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.core.entities.player import PlayerType

logger = logging.getLogger("EOR-GUI")


# ---------------------------------------------------------------------------
# Structured execution outcome (narrow, per Overlay §1.1 / delta §2.4/§3.3#6).
# ``auto_player_processor`` MUST return one of these; a swallowed ``None`` or
# caught exception is NOT proof of lawful no-action.
# ---------------------------------------------------------------------------
OUTCOME_ACCEPTED = "ACCEPTED"                # a real command receipt was produced
OUTCOME_NO_CHOICE = "NO_CHOICE"              # deliberate eligible-decider no-choice
OUTCOME_STRUCTURAL_EMPTY = "STRUCTURAL_EMPTY"  # owner-validated structural empty
OUTCOME_FAILURE = "FAILURE"                  # retrieval / decider / API error


@dataclass(frozen=True)
class OwnerCompletion:
    """Private typed carrier (D4/D6 §4.4 FC-D46-06) proving a Senate OWNER already
    wrote the completion for a singleton obligation (e.g. ``senate_veto_decision``).

    It is a READ-ONLY oracle for the outer coordinator and authorises NOTHING: it
    never replaces or duplicates the ONE ``SessionTurnBook`` record, and the outer
    MUST re-verify it against the immutable book record before skipping the generic
    completion path. Optional-value (``None``) is NOT optional-protocol — a
    presented marker that does not match the real record is a masked failure.
    """

    scope_id: str
    obligation_id: Tuple
    command_id: str
    actor_player_id: Optional[str]
    kind: str
    receipt_id: str = ""
    pre_revision: int = 0
    satisfied_at_revision: int = 0
    fact_ref: str = ""


@dataclass(frozen=True)
class ExecutionOutcome:
    """Narrow structured result of a scheduled-AI execution step."""

    kind: str
    detail: str = ""
    command_id: str = ""
    receipts: Tuple[str, ...] = ()
    #: D4/D6 §4.4: an optional owner-completion marker (only a real Senate owner
    #: write ever sets it); default ``None`` keeps the ordinary ballot compatible.
    owner_completion: Optional["OwnerCompletion"] = None

    @property
    def is_accepted(self) -> bool:
        return self.kind == OUTCOME_ACCEPTED

    @property
    def is_failure(self) -> bool:
        return self.kind == OUTCOME_FAILURE


#: Recognised owner-fact namespaces for an ACTION ``authoritative_fact_ref`` (F6).
_OWNER_FACT_NAMESPACES: Tuple[str, ...] = (
    "owner:", "receipt:", "domain:", "ai-receipt:", "senate-veto:", "veto:", "forum:",
)


#: Satisfaction kinds recorded in the ledger.
KIND_ACTION = "ACTION"
KIND_EXPLICIT_FINISH = "EXPLICIT_FINISH"
KIND_STRUCTURAL_NONE = "STRUCTURAL_NONE"

#: Controller labels (never a viewer-relative ``mode``).
CONTROLLER_HUMAN = "HUMAN"
CONTROLLER_AI = "AI"
CONTROLLER_NONE = "NONE"

#: Canonical seven-phase order (single canonical order; R4 §1).
PHASE_ORDER: Tuple[str, ...] = (
    "mortality", "revenue", "forum", "population", "senate", "combat", "resolution",
)

#: Continuation result statuses.
STATUS_NEXT_HUMAN = "next_human"
STATUS_SAME_HUMAN = "same_human"
STATUS_PHASE_READY = "phase_ready"
STATUS_RESOLVED = "resolved"
STATUS_FAILURE = "failure"


# ---------------------------------------------------------------------------
# Ledger records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Obligation:
    """One required obligation in canonical order (R1 §3 single derived view)."""

    obligation_id: Tuple            # stable OID (revision-free)
    scope_id: str
    phase: str
    substep: str
    actor_slot: Tuple               # ("singleton", scope) | ("player", actor_id)
    actor_player_id: Optional[str]
    officer_id: Optional[str]
    controller: str                 # HUMAN | AI | NONE
    required_operation: str
    satisfied: bool
    satisfied_kind: Optional[str]
    source_fact: str

    @property
    def is_executable(self) -> bool:
        return self.controller in (CONTROLLER_HUMAN, CONTROLLER_AI)


@dataclass(frozen=True)
class ScheduleSnapshot:
    """Immutable derived obligation view + closure predicate (R1 §2)."""

    phase: str
    scope_id: str
    obligations: Tuple[Obligation, ...]
    errors: Tuple[str, ...] = ()

    def outstanding(self) -> Tuple[Obligation, ...]:
        """Required obligations whose controller is executable and not satisfied."""
        return tuple(o for o in self.obligations if o.is_executable and not o.satisfied)

    def ready(self) -> bool:
        """All-controller readiness: no outstanding required obligation."""
        return not self.errors and all(
            o.satisfied or not o.is_executable for o in self.obligations)


@dataclass
class _Record:
    command_id: str
    dispatch_key: Tuple            # DK (pre-command anchored)
    obligation_id: Tuple           # OID (stable)
    authoritative_fact_ref: str
    satisfied_kind: str
    entry_revision: int
    satisfied_at_revision: int = 0


@dataclass
class _Scope:
    scope_id: str
    phase: str
    entry_revision: int
    actor: Optional[str]           # phase-entry Core current executable actor G


@dataclass
class ContinuationResult:
    status: str
    actor: Optional[str] = None
    masked_failure: bool = False
    reason: str = ""
    outstanding: Tuple[Obligation, ...] = ()
    processed: Tuple[str, ...] = ()
    #: D4/D6 I2-R1 item3 (FC-D46-05 §4.3.4): the FROZEN senate terminal envelope
    #: (only set on a real ``STATUS_RESOLVED`` senate terminal). ``None`` for every
    #: other (legacy) result — the ordinary continuation stays byte-for-byte.
    terminal: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.status != STATUS_FAILURE


# ---------------------------------------------------------------------------
# S1 — DeliveryResult v1 (D7–D12, FC-712-01..05)
#
# ONE typed internal/API data contract describing the semantic NEXT obligation.
# It is a projection of the immutable scope + owner-backed completion records;
# it grants NO authority and creates NO recovery capability. The invariant the
# Store enforces before any activation is:
#
#   semantic next obligation.actor
#       == DeliveryResult.next.actor_player_id
#       == actual pending receiver
#       == activation target
#       == Core current player
#
# A missing / unknown / contradictory receiver is a TYPED failure and MUST NOT
# be healed by the legacy ``None -> same-seat`` fallback.
# ---------------------------------------------------------------------------
DELIVERY_VERSION = 1

DELIVERY_OUTCOME_CONTINUE = "CONTINUE"
DELIVERY_OUTCOME_RESOLVED = "RESOLVED"
DELIVERY_OUTCOME_FAILURE = "FAILURE"

DELIVERY_DISPOSITION_SAME_HUMAN = "SAME_HUMAN"
DELIVERY_DISPOSITION_NEXT_HUMAN = "NEXT_HUMAN"
DELIVERY_DISPOSITION_AI_OWNER = "AI_OWNER"

DELIVERY_MISSING_RECEIVER = "DELIVERY_MISSING_RECEIVER"
DELIVERY_INVALID = "DELIVERY_INVALID"
DELIVERY_MISMATCH = "DELIVERY_MISMATCH"

DELIVERY_RETRY_ACTIVATION = "ACTIVATION_ONLY"
DELIVERY_RETRY_NONE = "NONE"


def delivery_error(code: str, stage: str = "", *,
                   committed: bool = True,
                   retry_class: str = DELIVERY_RETRY_ACTIVATION,
                   detail: str = "") -> Dict[str, Any]:
    """A typed, safe delivery error (no credential / guard reason)."""
    return {
        "code": code,
        "stage": stage or "delivery",
        "committed": bool(committed),
        "retry_class": retry_class,
        "detail": detail,
    }


def _delivery_disposition(actor: Optional[str], controller: str,
                          viewer_id: Optional[str]) -> str:
    if controller == CONTROLLER_AI:
        return DELIVERY_DISPOSITION_AI_OWNER
    if viewer_id and actor == viewer_id:
        return DELIVERY_DISPOSITION_SAME_HUMAN
    return DELIVERY_DISPOSITION_NEXT_HUMAN


def _next_obligation_id(state: Any, phase: str,
                        actor: Optional[str]) -> Optional[List[Any]]:
    """The stable OID of ``actor``'s outstanding obligation (projection only)."""
    if not actor:
        return None
    try:
        snapshot = obligations(state, phase)
    except Exception:  # pragma: no cover - defensive
        return None
    for obligation in snapshot.outstanding():
        if obligation.actor_player_id == actor:
            return list(obligation.obligation_id)
    return None


def delivery_for_actor(state: Any, phase: str, actor: Optional[str], *,
                       outcome: str = DELIVERY_OUTCOME_CONTINUE,
                       viewer_id: Optional[str] = None,
                       terminal: Optional[Dict[str, Any]] = None,
                       command_receipt_ref: str = "",
                       substep: str = "") -> Dict[str, Any]:
    """Build ``DeliveryResultV1`` for an explicitly resolved receiver.

    Used where the owner has already committed the next/terminal obligation
    (e.g. a resolved population slice). The actor is still validated later by
    :func:`validate_delivery_result` against the REAL Core current player.
    """
    delivery: Dict[str, Any] = {
        "version": DELIVERY_VERSION,
        "session_ref": _session_ns(state),
        "turn": _book(state).turn_number,
        "scope_id": current_scope_id(state, phase) or "",
        "core_revision": current_revision(state),
        "command_receipt_ref": str(command_receipt_ref or ""),
        "outcome": outcome,
        "next": None,
        "terminal": dict(terminal) if terminal else None,
        "error": None,
    }
    if actor:
        controller = controller_of(state, actor)
        delivery["next"] = {
            "obligation_id": None,
            "phase": phase,
            "substep": substep,
            "actor_player_id": actor,
            "controller": controller,
            "disposition": _delivery_disposition(actor, controller, viewer_id),
        }
    if outcome == DELIVERY_OUTCOME_CONTINUE and not actor:
        delivery["error"] = delivery_error(
            DELIVERY_MISSING_RECEIVER, stage="continuation",
            committed=True, retry_class=DELIVERY_RETRY_NONE,
            detail="a non-terminal delivery requires a real receiver")
    return delivery


def delivery_from_continuation(
        state: Any, phase: str, cont: ContinuationResult, *,
        viewer_id: Optional[str] = None,
        command_receipt_ref: str = "") -> Dict[str, Any]:
    """Project ONE ``ContinuationResult`` into ``DeliveryResultV1``.

    ``CONTINUE``/``RESOLVED`` require a real next actor; a successful delivery
    without one is ``DELIVERY_MISSING_RECEIVER`` (never a silent same-seat).
    """
    scope_id = current_scope_id(state, phase) or ""
    base: Dict[str, Any] = {
        "version": DELIVERY_VERSION,
        "session_ref": _session_ns(state),
        "turn": _book(state).turn_number,
        "scope_id": scope_id,
        "core_revision": current_revision(state),
        "command_receipt_ref": str(command_receipt_ref or ""),
        "next": None,
        "terminal": None,
        "error": None,
    }
    if cont.status == STATUS_FAILURE or cont.masked_failure:
        base["outcome"] = DELIVERY_OUTCOME_FAILURE
        base["error"] = delivery_error(
            DELIVERY_INVALID, stage="continuation", committed=True,
            retry_class=DELIVERY_RETRY_NONE,
            detail=str(cont.reason or "CONTINUATION_FAILED"))
        return base
    outcome = (DELIVERY_OUTCOME_RESOLVED
               if cont.status in (STATUS_RESOLVED, STATUS_PHASE_READY)
               else DELIVERY_OUTCOME_CONTINUE)
    base["outcome"] = outcome
    actor = cont.actor
    if actor:
        controller = controller_of(state, actor)
        base["next"] = {
            "obligation_id": (list(cont.outstanding[0].obligation_id)
                              if cont.outstanding else None),
            "phase": phase,
            "substep": (cont.outstanding[0].substep if cont.outstanding else ""),
            "actor_player_id": actor,
            "controller": controller,
            "disposition": _delivery_disposition(actor, controller, viewer_id),
        }
    if cont.terminal is not None:
        base["terminal"] = dict(cont.terminal)
        terminal_oid = base["terminal"].get("obligation_id")
        if base.get("next") is not None and terminal_oid is not None \
                and base["next"].get("obligation_id") is None:
            # §1.2 O: a RESOLVED terminal carries the exact RESULT-OWNER
            # obligation identity (never an outstanding voter).
            base["next"]["obligation_id"] = list(terminal_oid)
    if outcome == DELIVERY_OUTCOME_CONTINUE and not actor:
        base["error"] = delivery_error(
            DELIVERY_MISSING_RECEIVER, stage="continuation",
            committed=True, retry_class=DELIVERY_RETRY_NONE,
            detail="a non-terminal continuation requires a real receiver")
    return base


def _delivery_phase(delivery: Dict[str, Any]) -> str:
    """The envelope's phase, read from the primary facts (never a bare default)."""
    for key in ("next", "terminal"):
        part = delivery.get(key)
        if isinstance(part, dict) and part.get("phase"):
            return str(part["phase"])
    return str(delivery.get("phase") or "senate")


def delivery_command_ref(state: Any, phase: str, command: str, *,
                         actor: Optional[str] = None) -> str:
    """Issue the ENGINE-owned accepted-command reference a delivery carries.

    Uses the EXISTING owner-receipt facility (``book.receipts`` /
    ``committed_facts``): no new ledger, schema, protocol version or authority.
    Column Q resolves the returned fact reference back to this real command in
    the SAME session / turn / scope (never an arbitrary string).

    I1a: a delivery produced by the engine for a phase with NO committed phase
    entry first binds the phase through the SAME service-issued committed entry
    receipt used by ``enter_phase`` (never a payload/decorative claim). This is
    the trusted route for a store-driven operation on a mid-phase state; if the
    receipt cannot be consumed (source not committed / unknown phase) the state
    stays unbound and the delivery validator fails closed.
    """
    scope = mint_scope(state, phase)
    book = getattr(state, _BOOK_ATTR, None)
    if book is not None:
        # Reuse a GENUINE reference already issued by the owning command: no
        # second receipt is minted for the same command/scope (one-time
        # consumption accounting stays exact).
        for ref, rec in book.committed_facts.items():
            if rec.get("command") == command \
                    and rec.get("scope_id") == scope.scope_id:
                return ref
        for receipt_id, rec in book.receipts.items():
            if rec.get("command") == command \
                    and rec.get("scope_id") == scope.scope_id:
                return receipt_id
    receipt = issue_owner_receipt(
        state, command, actor_player_id=actor,
        fact_ref=f"dispatch:{command}:{scope.scope_id}",
        scope_id=scope.scope_id, kind=KIND_ACTION)
    return receipt["fact_ref"]


def bind_phase_for_delivery(state: Any, phase: str) -> None:
    """Engine route declaration for a phase with no journal entry (I1a).

    Issues the SAME service-private committed phase-entry receipt that a real
    phase advance issues, then consumes it exactly once. Any failure leaves the
    book unbound (the delivery validator then fails closed); it never forges an
    entry, never weakens a registered session and never writes a payload field.
    """
    try:
        book = getattr(state, _BOOK_ATTR, None)
        if book is not None and book.entries:
            return
        receipt = issue_committed_phase_entry_receipt(
            state, command_id=f"delivery:{phase}", phase=phase)
    except Exception:  # pragma: no cover - defensive
        return
    try:
        enter_phase(state, receipt)
    except Exception:  # pragma: no cover - defensive
        return


def _norm_obligation_id(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_norm_obligation_id(item) for item in value)
    return value


def _typed_finalization_parts(value: Any) -> Optional[List[Any]]:
    """B.4.1: (str, str, int) positional identity — never a coercion.

    ``bool`` is an ``int`` subclass and a numeric string/float is not the
    canonical protocol version: both are rejected instead of normalised.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    first, second, third = value
    if type(first) is not str or type(second) is not str:
        return None
    if type(third) is not int or isinstance(third, bool):
        return None
    return [first, second, third]


def _absent(value: Any) -> bool:
    """Column helper: null/absent is 0 for every mandatory delivery field."""
    return value is None or value == ""


def _schema_denial(delivery: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Column H (§1.2): mapping / version=1 / known outcome / typed containers.

    An ill-typed or unknown state is OUTSIDE the 16 normalised rows and is
    ``DELIVERY_INVALID`` / ``schema`` (never a seventeenth enum).
    """
    version = delivery.get("version")
    if isinstance(version, bool) or not isinstance(version, int) \
            or version != DELIVERY_VERSION:
        return delivery_error(DELIVERY_INVALID, stage="schema",
                              detail="unsupported or untyped version")
    outcome = delivery.get("outcome")
    if not isinstance(outcome, str) or outcome not in (
            DELIVERY_OUTCOME_CONTINUE, DELIVERY_OUTCOME_RESOLVED,
            DELIVERY_OUTCOME_FAILURE):
        return delivery_error(DELIVERY_INVALID, stage="schema",
                              detail="unknown outcome")
    for key in ("next", "terminal", "error"):
        value = delivery.get(key)
        if value is not None and not isinstance(value, dict):
            return delivery_error(DELIVERY_INVALID, stage="schema",
                                  detail=f"{key} must be a mapping or null")
    if outcome != DELIVERY_OUTCOME_FAILURE and delivery.get("error") is not None:
        return delivery_error(DELIVERY_INVALID, stage="schema",
                              detail="a successful delivery must not carry an error")
    return None


def _shape_of(delivery: Dict[str, Any]) -> Tuple[str, int, int]:
    """Normalise to (class, N, T) — C/S/R/F and typed next/terminal presence."""
    outcome = delivery.get("outcome")
    nxt = delivery.get("next") if isinstance(delivery.get("next"), dict) else None
    terminal = (delivery.get("terminal")
                if isinstance(delivery.get("terminal"), dict) else None)
    if outcome == DELIVERY_OUTCOME_FAILURE:
        cls = "F"
    elif outcome == DELIVERY_OUTCOME_RESOLVED:
        cls = "R"
    else:
        disposition = ((nxt or {}).get("disposition")
                       or delivery.get("disposition"))
        cls = "S" if disposition == DELIVERY_DISPOSITION_SAME_HUMAN else "C"
    return cls, (1 if nxt is not None else 0), (1 if terminal is not None else 0)


def _shape_denial(cls: str, n_present: int, t_present: int,
                  phase: str = "senate") -> Optional[Dict[str, Any]]:
    """The finite shape rows (§1.3) evaluated BEFORE the shared columns.

    Rows 03/07/12/13 (the ACCEPT rows) return ``None`` and still require every
    applicable column below. ``ALL`` is a conjunction, never an early success.
    """
    if cls in ("C", "S"):
        if n_present == 0 and t_present == 0:
            return delivery_error(DELIVERY_MISSING_RECEIVER, stage="receiver",
                                  detail="a non-terminal delivery requires a real receiver")
        if t_present == 1:
            return delivery_error(DELIVERY_INVALID, stage="outcome_terminal",
                                  detail="a non-terminal outcome cannot carry a terminal")
    if cls == "R" and t_present == 0:
        if phase != "senate":
            # Out of the D7–D12 Senate protocol: a resolved non-Senate SLICE with a
            # real next keeps its existing phase-boundary meaning (no terminal
            # species is invented for it).
            if n_present == 0:
                return delivery_error(DELIVERY_MISSING_RECEIVER, stage="receiver",
                                      detail="a resolved slice requires its next receiver")
            return None
        # Rows 09 and 11: RESOLVED requires the canonical terminal, even when a
        # genuine next exists (a real next never substitutes for finalization).
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="RESOLVED requires the canonical terminal")
    if cls == "F" and (n_present == 1 or t_present == 1):
        return delivery_error(DELIVERY_INVALID, stage="failure",
                              detail="a failure cannot deliver a receiver or terminal")
    return None


def _claimed_phases(delivery: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """Every phase CLAIM the envelope makes (A.2) — never a source of authority."""
    claims: List[Tuple[str, Any]] = []
    for key in ("next", "terminal"):
        part = delivery.get(key)
        if isinstance(part, dict) and not _absent(part.get("phase")):
            claims.append((key, part.get("phase")))
    if not _absent(delivery.get("phase")):
        claims.append(("phase", delivery.get("phase")))
    return claims


def _senate_semantics(delivery: Dict[str, Any]) -> bool:
    """True when the envelope asserts ANY Senate protocol meaning (I1a)."""
    for _key, value in _claimed_phases(delivery):
        if value == "senate":
            return True
    terminal = delivery.get("terminal")
    if isinstance(terminal, dict):
        fid = terminal.get("finalization_id")
        if fid not in (None, "", []):
            return True
        oid = terminal.get("obligation_id")
        if isinstance(oid, (list, tuple)) and len(oid) > 3 and oid[3] == "senate":
            return True
    return False


def _envelope_denial(state: Any, delivery: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Columns I / S / V / Q (§1.2): identity, scope, revision, command receipt.

    A.1–A.4 (I1a): the trusted phase comes ONLY from ``trusted_phase`` (P1
    ``SessionTurnBook.entries`` -> P2 live scope -> P3 committed receipt). The
    envelope phase is a CLAIM used only for comparison; an unknown/forged claim
    can never grant the non-Senate exemption (route, never payload).

    A missing mandatory field is ``DELIVERY_INVALID``; a foreign/stale/unknown
    value is ``DELIVERY_MISMATCH``. Read-only (the book is probed, never minted;
    an unknown oracle fails closed).
    """
    book = getattr(state, _BOOK_ATTR, None)

    # -- I: session_ref / turn must identify THIS session and CURRENT turn -----
    session_ref = delivery.get("session_ref")
    if _absent(session_ref):
        return delivery_error(DELIVERY_INVALID, stage="identity",
                              detail="session_ref is required")
    if str(session_ref) != str(_session_ns(state)):
        return delivery_error(DELIVERY_MISMATCH, stage="identity",
                              detail="session_ref does not identify this session")

    turn = delivery.get("turn")
    if turn is None:
        return delivery_error(DELIVERY_INVALID, stage="identity",
                              detail="turn is required")
    expected_turn = book.turn_number if book is not None else 1
    try:
        turn_ok = int(turn) == int(expected_turn)
    except (TypeError, ValueError):
        return delivery_error(DELIVERY_INVALID, stage="identity",
                              detail="turn must be an integer")
    if not turn_ok:
        return delivery_error(DELIVERY_MISMATCH, stage="identity",
                              detail="turn does not identify the current turn")

    # -- A.1/A.2: trusted phase is the ONLY authority; claims only compare -------
    trusted = trusted_phase(state)
    phase = trusted.get("phase")
    scope_id = delivery.get("scope_id")
    if phase is None:
        if _senate_semantics(delivery):
            if _absent(scope_id):
                return delivery_error(DELIVERY_INVALID, stage="scope",
                                      detail="scope_id is required for the trusted scope")
            if delivery.get("outcome") == DELIVERY_OUTCOME_RESOLVED:
                return delivery_error(DELIVERY_MISMATCH, stage="receipt_wrong",
                                      detail=trusted.get("detail")
                                      or "the phase is not bound")
            return delivery_error(trusted.get("code") or DELIVERY_INVALID,
                                  stage=trusted.get("stage") or "phase",
                                  detail=trusted.get("detail")
                                  or "the phase is not bound")
        # I1b (out of scope this round): a genuine NON-Senate slice on a state
        # with no committed phase entry keeps its historical envelope semantics.
        # It can never carry Senate semantics (checked above), so the Senate
        # protocol is not weakened by this fallback.
        phase = _delivery_phase(delivery)
        current_scope = None
        if book is not None:
            scope = book.scopes.get(phase)
            current_scope = scope.scope_id if scope is not None else None
        if _absent(scope_id):
            if current_scope:
                return delivery_error(DELIVERY_INVALID, stage="scope",
                                      detail="scope_id is required for a minted scope")
        elif str(scope_id) != str(current_scope or ""):
            return delivery_error(DELIVERY_MISMATCH, stage="scope",
                                  detail="scope_id is foreign or stale")
        terminal = delivery.get("terminal")
        if isinstance(terminal, dict):
            terminal_scope = terminal.get("scope_id")
            if _absent(terminal_scope):
                return delivery_error(DELIVERY_INVALID, stage="scope",
                                      detail="terminal.scope_id is required")
            if str(terminal_scope) != str(current_scope or ""):
                return delivery_error(DELIVERY_MISMATCH, stage="scope",
                                      detail="terminal scope is foreign or stale")
        revision = delivery.get("core_revision")
        if revision is None:
            return delivery_error(DELIVERY_INVALID, stage="revision",
                                  detail="core_revision is required")
        try:
            revision_ok = int(revision) == int(current_revision(state))
        except (TypeError, ValueError):
            return delivery_error(DELIVERY_INVALID, stage="revision",
                                  detail="core_revision must be an integer")
        if not revision_ok:
            return delivery_error(DELIVERY_MISMATCH, stage="revision",
                                  detail="core_revision is stale")
        return _command_receipt_denial(state, book, delivery, scope_id)
    current_scope = trusted["scope_id"]
    claims = _claimed_phases(delivery)
    declared: List[Any] = []
    for _key, value in claims:
        if value not in declared:
            declared.append(value)
    if len(declared) > 1:
        return delivery_error(DELIVERY_MISMATCH, stage="phase",
                              detail="the declared phases disagree")
    for key, value in claims:
        if value != phase:
            return delivery_error(DELIVERY_MISMATCH, stage="phase",
                                  detail=f"{key} phase disagrees with the trusted route")

    # -- S: the envelope scope AND the terminal scope must be the TRUSTED scope --
    if _absent(scope_id):
        return delivery_error(DELIVERY_INVALID, stage="scope",
                              detail="scope_id is required for the trusted scope")
    if str(scope_id) != str(current_scope):
        return delivery_error(DELIVERY_MISMATCH, stage="scope",
                              detail="scope_id is foreign or stale")
    terminal = delivery.get("terminal")
    if isinstance(terminal, dict):
        terminal_scope = terminal.get("scope_id")
        if _absent(terminal_scope):
            return delivery_error(DELIVERY_INVALID, stage="scope",
                                  detail="terminal.scope_id is required")
        if str(terminal_scope) != str(current_scope):
            return delivery_error(DELIVERY_MISMATCH, stage="scope",
                                  detail="terminal scope is foreign or stale")

    # -- A.4.4: a non-Senate route cannot carry Senate-specific declarations ---
    if phase != "senate":
        senate_decl = False
        if isinstance(terminal, dict):
            fid = terminal.get("finalization_id")
            if fid not in (None, "", []):
                senate_decl = True
            oid = terminal.get("obligation_id")
            if isinstance(oid, (list, tuple)) and len(oid) > 3 \
                    and oid[3] == "senate":
                senate_decl = True
        if senate_decl:
            return delivery_error(
                DELIVERY_MISMATCH, stage="phase",
                detail="a Senate declaration cannot use a non-Senate route")

    # -- V: a fresh (never the earlier commit) revision ------------------------
    revision = delivery.get("core_revision")
    if revision is None:
        return delivery_error(DELIVERY_INVALID, stage="revision",
                              detail="core_revision is required")
    try:
        revision_ok = int(revision) == int(current_revision(state))
    except (TypeError, ValueError):
        return delivery_error(DELIVERY_INVALID, stage="revision",
                              detail="core_revision must be an integer")
    if not revision_ok:
        return delivery_error(DELIVERY_MISMATCH, stage="revision",
                              detail="core_revision is stale")

    # -- Q: the reference must resolve to a genuine accepted command -----------
    return _command_receipt_denial(state, book, delivery, scope_id)


def _command_receipt_denial(state: Any, book: Any,
                            delivery: Dict[str, Any],
                            scope_id: Any) -> Optional[Dict[str, Any]]:
    ref = delivery.get("command_receipt_ref")
    if not isinstance(ref, str) or not ref.strip():
        return delivery_error(DELIVERY_INVALID, stage="command_receipt",
                              detail="a committed command reference is required")
    ref = ref.strip()
    if book is None:
        return delivery_error(DELIVERY_MISMATCH, stage="command_receipt",
                              detail="the command reference cannot be verified")
    if ref in book.receipts or ref in book.committed_facts:
        return None
    for rec in book.records:
        oid = rec.obligation_id or ()
        rec_scope = oid[2] if len(oid) > 2 else ""
        rec_turn = oid[1] if len(oid) > 1 else None
        if rec_scope == str(scope_id or "") and rec_turn == book.turn_number \
                and (rec.command_id == ref or rec.authoritative_fact_ref == ref):
            return None
    return delivery_error(DELIVERY_MISMATCH, stage="command_receipt",
                          detail="the reference is not an accepted command")


def _obligation_denial(state: Any, phase: str,
                       nxt: Dict[str, Any],
                       terminal: Optional[Dict[str, Any]] = None,
                       outcome: str = DELIVERY_OUTCOME_CONTINUE,
                       scope_id: str = "") -> Optional[Dict[str, Any]]:
    """Column O (§1.2): the exact authoritative immediate obligation identity.

    A missing id is ``DELIVERY_INVALID/obligation``; a fake/stale/wrong-actor or
    previous-generation id is ``DELIVERY_MISMATCH/obligation``. For a RESOLVED
    terminal the identity is the RESULT-OWNER obligation (never an outstanding
    voter), so no outstanding obligation is fabricated for a finalised scope.
    """
    presented = nxt.get("obligation_id")
    if _absent(presented):
        if phase != "senate":
            return None
        return delivery_error(DELIVERY_INVALID, stage="obligation",
                              detail="the exact obligation identity is required")
    actor = nxt.get("actor_player_id")
    if _absent(actor):
        # Column A owns the missing-receiver diagnostic; O never masks it as a
        # fake obligation comparison against an empty actor.
        return None
    if terminal is not None and outcome == DELIVERY_OUTCOME_RESOLVED:
        if not isinstance(presented, (list, tuple)) or len(presented) != 6:
            return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                                  detail="the result-owner obligation is malformed")
        book = getattr(state, _BOOK_ATTR, None)
        turn = book.turn_number if book is not None else None
        expected = (str(_session_ns(state)), turn, str(scope_id or ""), phase,
                    "terminal", ("player", actor))
        if _norm_obligation_id(presented) != _norm_obligation_id(expected):
            return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                                  detail="not the exact result-owner obligation")
        return None
    try:
        snapshot = obligations(state, phase)
    except Exception:  # pragma: no cover - defensive
        snapshot = None
    if snapshot is None or snapshot.errors:
        return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                              detail="the obligation cannot be verified")
    outstanding = snapshot.outstanding()
    if outcome == DELIVERY_OUTCOME_CONTINUE:
        # A-W3-11 / F-01: a CONTINUE delivery MUST name the GLOBAL queue-head
        # obligation. Accepting "any unsatisfied obligation of this actor" would
        # let a delivery skip an earlier faction (the D9 "never got a turn"
        # defect). RESOLVED / non-CONTINUE keeps its exact result-owner meaning.
        if not outstanding:
            return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                                  detail="a CONTINUE delivery requires an "
                                         "outstanding obligation")
        head = outstanding[0]
        if head.actor_player_id != actor:
            return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                                  detail="the receiver is not the queue-head "
                                         "obligation")
        expected = head.obligation_id
    else:
        expected = None
        for obligation in outstanding:
            if obligation.actor_player_id == actor:
                expected = obligation.obligation_id
                break
        if expected is None:
            return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                                  detail="no such outstanding obligation for the actor")
    if _norm_obligation_id(presented) != _norm_obligation_id(expected):
        return delivery_error(DELIVERY_MISMATCH, stage="obligation",
                              detail="obligation id is foreign or stale")
    return None


def _legacy_denial(delivery: Dict[str, Any], legacy: Any,
                   nxt: Optional[Dict[str, Any]],
                   terminal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Column L (§1.2): every PRESENT legacy sibling/embedded field must agree.

    A NON-EMPTY legacy awaiting against an AI primary ALWAYS rejects — absent
    optional fields never create a receiver, and a present field is never
    skipped (the earlier AI-awaiting hole).
    """
    if nxt is not None:
        primary_actor = nxt.get("actor_player_id")
        primary_controller = nxt.get("controller")
        primary_awaiting = (primary_actor
                            if primary_controller == CONTROLLER_HUMAN else None)
    elif isinstance(terminal, dict):
        primary_actor = terminal.get("actor")
        primary_controller = terminal.get("controller")
        primary_awaiting = terminal.get("awaiting_player_id")
    else:
        return None
    sources = [delivery]
    if isinstance(legacy, dict):
        sources.append(legacy)
    for source in sources:
        controller = source.get("controller")
        if not _absent(controller) and primary_controller \
                and controller != primary_controller:
            return delivery_error(DELIVERY_MISMATCH, stage="legacy",
                                  detail="legacy controller contradicts the delivery")
        actor = source.get("actor")
        if not _absent(actor) and primary_actor and actor != primary_actor:
            return delivery_error(DELIVERY_MISMATCH, stage="legacy",
                                  detail="legacy actor contradicts the delivery")
        awaiting = source.get("awaiting_player_id")
        if not _absent(awaiting):
            if primary_awaiting is None or awaiting != primary_awaiting:
                return delivery_error(
                    DELIVERY_MISMATCH, stage="legacy",
                    detail="legacy awaiting receiver contradicts the delivery")
    return None


def _terminal_denial(state: Any, phase: str,
                     nxt: Optional[Dict[str, Any]],
                     terminal: Any,
                     scope_id: str = "") -> Optional[Dict[str, Any]]:
    """Column T (§1.2) + §2 canonical terminal identity.

    A RESOLVED Senate terminal must dereference the GENUINE receipt body and
    satisfy the same-version canonical predicate (identity + content); four
    booleans alone are insufficient. A non-Senate terminal uses its genuine
    owner receipt.
    """
    if not isinstance(terminal, dict):
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="terminal must be a mapping")
    actor = terminal.get("actor")
    if not actor:
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="terminal requires the real result owner")
    status = terminal.get("status")
    if _absent(status):
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="terminal requires a typed status")
    if status != "resolved":
        return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                              detail="terminal status is not resolved")
    claimed_phase = terminal.get("phase")
    if _absent(claimed_phase):
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="terminal requires its phase identity")
    if claimed_phase != phase:
        return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                              detail="terminal phase disagrees with the delivery")
    actual_controller = controller_of(state, actor)
    if terminal.get("controller") != actual_controller:
        return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                              detail="terminal controller disagrees with PlayerType")
    if nxt is not None and nxt.get("actor_player_id") \
            and nxt.get("actor_player_id") != actor:
        return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                              detail="terminal owner differs from the delivered next")
    awaiting = terminal.get("awaiting_player_id")
    if actual_controller == CONTROLLER_HUMAN:
        if awaiting != actor:
            return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                                  detail="a HUMAN terminal must await its owner")
    elif not _absent(awaiting):
        return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                              detail="an AI owner is never an awaiting HUMAN seat")

    if phase != "senate":
        owner_receipt = terminal.get("owner_receipt")
        receipt_id = (owner_receipt.get("receipt_id")
                      if isinstance(owner_receipt, dict) else None)
        book = getattr(state, _BOOK_ATTR, None)
        if not receipt_id or book is None or receipt_id not in book.receipts:
            return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                                  detail="a non-Senate terminal needs its owner receipt")
        return None

    from src.api import senate_api
    try:
        finalization_id = senate_api.senate_finalization_id(state)
    except Exception:  # pragma: no cover - defensive
        finalization_id = None
    expected = _typed_finalization_parts(finalization_id)
    if expected is None:
        return delivery_error(DELIVERY_MISMATCH, stage="finalization_id",
                              detail="the canonical finalization id is not typed")
    claimed = terminal.get("finalization_id")
    if _absent(claimed) or claimed == []:
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="terminal requires the canonical finalization id")
    if not isinstance(claimed, (list, tuple)) or len(claimed) != 3:
        return delivery_error(DELIVERY_INVALID, stage="terminal",
                              detail="the finalization id is malformed")
    observed = _typed_finalization_parts(claimed)
    if observed is None:
        return delivery_error(DELIVERY_MISMATCH, stage="finalization_id",
                              detail="the finalization id components are not typed")
    if observed != expected:
        return delivery_error(DELIVERY_MISMATCH, stage="finalization_id",
                              detail="terminal names a foreign finalization")
    claimed_list = terminal.get("finalization_id_list")
    if claimed_list is not None:
        if not isinstance(claimed_list, (list, tuple)) or len(claimed_list) != 3:
            return delivery_error(DELIVERY_MISMATCH, stage="receipt_wrong",
                                  detail="the finalization id list is malformed")
        if list(claimed_list) != [str(part) for part in expected]:
            return delivery_error(DELIVERY_MISMATCH, stage="finalization_id",
                                  detail="the finalization id list is not positionally equal")

    canonical = senate_api.canonical_finalization(
        state, expected_scope=scope_id or None,
        expected_key=tuple(finalization_id) if finalization_id else None,
        claimed_terminal=terminal)
    if canonical.get("status") == "ABSENT":
        return delivery_error(DELIVERY_MISMATCH, stage="receipt_missing",
                              detail="no canonical receipt backs this terminal")
    if canonical.get("status") != "VALID":
        stage = canonical.get("stage") or "receipt_wrong"
        return delivery_error(DELIVERY_MISMATCH, stage=stage,
                              detail="the canonical receipt is inconsistent")
    facts_claim = terminal.get("completion_facts")
    if facts_claim is not None:
        verified = canonical.get("facts") or {}
        if not isinstance(facts_claim, dict) or facts_claim != verified:
            return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                                  detail="the claimed completion facts are false")
    revision_claim = terminal.get("core_revision")
    if revision_claim is not None:
        try:
            revision_ok = int(revision_claim) == int(current_revision(state))
        except (TypeError, ValueError):
            revision_ok = False
        if not revision_ok:
            return delivery_error(DELIVERY_MISMATCH, stage="terminal",
                                  detail="the claimed terminal revision is stale")
    return None


def _receiver_denial(state: Any, nxt: Optional[Dict[str, Any]],
                     terminal: Optional[Dict[str, Any]],
                     viewer_id: Optional[str], phase: str = "") -> Optional[Dict[str, Any]]:
    """Column A (§1.2): real actor, raw PlayerType, disposition/scheduling."""
    part = nxt if nxt is not None else terminal
    if not isinstance(part, dict):
        return None
    actor = (nxt.get("actor_player_id") if nxt is not None
             else terminal.get("actor"))
    if _absent(actor):
        return delivery_error(DELIVERY_MISSING_RECEIVER, stage="receiver",
                              detail="a real receiver is required")
    if getattr(state, "get_player", lambda _x: None)(actor) is None:
        return delivery_error(DELIVERY_INVALID, stage="receiver",
                              detail="the receiver is not a real player")
    controller = (nxt.get("controller") if nxt is not None
                  else terminal.get("controller"))
    if controller not in (CONTROLLER_HUMAN, CONTROLLER_AI):
        return delivery_error(DELIVERY_INVALID, stage="receiver",
                              detail="the controller enum is unknown")
    actual = controller_of(state, actor)
    if actual == CONTROLLER_NONE:
        return delivery_error(DELIVERY_INVALID, stage="receiver",
                              detail="the raw PlayerType is not executable")
    if actual != controller:
        return delivery_error(DELIVERY_MISMATCH, stage="receiver",
                              detail="the controller contradicts the raw PlayerType")
    if nxt is None:
        return None
    disposition = nxt.get("disposition")
    if disposition not in (DELIVERY_DISPOSITION_SAME_HUMAN,
                           DELIVERY_DISPOSITION_NEXT_HUMAN,
                           DELIVERY_DISPOSITION_AI_OWNER):
        return delivery_error(DELIVERY_INVALID, stage="receiver",
                              detail="the disposition enum is unknown")
    if actual == CONTROLLER_HUMAN \
            and disposition == DELIVERY_DISPOSITION_AI_OWNER:
        return delivery_error(DELIVERY_MISMATCH, stage="receiver",
                              detail="a HUMAN receiver cannot carry AI_OWNER")
    if actual == CONTROLLER_AI \
            and disposition != DELIVERY_DISPOSITION_AI_OWNER:
        return delivery_error(DELIVERY_MISMATCH, stage="receiver",
                              detail="an AI receiver requires AI_OWNER")
    if disposition == DELIVERY_DISPOSITION_SAME_HUMAN:
        if viewer_id and actor != viewer_id:
            return delivery_error(DELIVERY_MISMATCH, stage="receiver",
                                  detail="SAME_HUMAN must target the current viewer")
        if _earlier_obligation(state, phase, actor):
            return delivery_error(DELIVERY_MISMATCH, stage="receiver",
                                  detail="SAME_HUMAN cannot skip an earlier obligation")
    return None


def _earlier_obligation(state: Any, phase: str, actor: str) -> bool:
    """True when another actor holds an EARLIER outstanding obligation."""
    try:
        snapshot = obligations(state, phase)
    except Exception:  # pragma: no cover - defensive
        return True
    if snapshot.errors:
        return True
    outstanding = snapshot.outstanding()
    for index, obligation in enumerate(outstanding):
        if obligation.actor_player_id == actor:
            return any(o.actor_player_id != actor for o in outstanding[:index])
    return False


def _core_denial(state: Any, phase: str, nxt: Optional[Dict[str, Any]],
                 terminal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Column K (§1.2): the ACTUAL Core current / result-owner G read-back.

    Missing fields are never a wildcard; a terminal-only envelope is checked
    against the real Core current player and the scope's true G.
    """
    current = _entry_actor(state)
    if terminal is not None:
        actor = terminal.get("actor")
        if _absent(actor):
            return delivery_error(DELIVERY_INVALID, stage="core",
                                  detail="terminal actor is required")
        current_player_id = terminal.get("current_player_id")
        if _absent(current_player_id):
            return delivery_error(DELIVERY_INVALID, stage="core",
                                  detail="terminal.current_player_id is mandatory")
        if str(current_player_id) != str(actor):
            return delivery_error(DELIVERY_MISMATCH, stage="core",
                                  detail="terminal current player is not the owner")
        if str(current) != str(actor):
            return delivery_error(DELIVERY_MISMATCH, stage="core",
                                  detail="terminal owner is not the actual Core current")
        cursor = terminal.get("cursor_restored")
        if cursor is None:
            return delivery_error(DELIVERY_INVALID, stage="core",
                                  detail="cursor_restored is mandatory")
        if cursor is not True:
            return delivery_error(DELIVERY_MISMATCH, stage="core",
                                  detail="the terminal must restore the real cursor")
        book = getattr(state, _BOOK_ATTR, None)
        scope = book.scopes.get(phase) if book is not None else None
        if scope is not None and scope.actor \
                and str(scope.actor) != str(actor):
            return delivery_error(DELIVERY_MISMATCH, stage="core",
                                  detail="the terminal owner is not the scope G")
    if nxt is not None:
        actor = nxt.get("actor_player_id")
        if actor and str(current) != str(actor):
            return delivery_error(DELIVERY_MISMATCH, stage="core",
                                  detail="delivery actor is not the actual Core current")
    return None


def _failure_denial(delivery: Dict[str, Any],
                    nxt: Optional[Dict[str, Any]],
                    terminal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Column E (§1.2): F requires a typed error and no activation/success."""
    error = delivery.get("error")
    if not isinstance(error, dict) or not isinstance(error.get("code"), str) \
            or not error.get("code", "").strip():
        return delivery_error(DELIVERY_INVALID, stage="failure",
                              detail="a failure requires a typed error")
    if nxt is not None or terminal is not None:
        return delivery_error(DELIVERY_INVALID, stage="failure",
                              detail="a failure cannot carry a receiver or terminal")
    return None


def validate_delivery_result(state: Any, delivery: Any, *,
                             viewer_id: Optional[str] = None,
                             legacy: Any = None) -> Dict[str, Any]:
    """Validate ``DeliveryResultV1`` against the REAL Core/PlayerType facts.

    Deterministic order (§1.2): H→I→S→V→Q→shape→O→A→K→T→L→E. Every applicable
    column runs before ANY success return; a terminal-only envelope is NOT a
    success shortcut (legacy / actual Core / G / canonical terminal still run).
    It never mutates authority or the ledger.
    """
    if not isinstance(delivery, dict):
        return {"ok": False, "error": delivery_error(
            DELIVERY_INVALID, stage="schema", detail="delivery must be a mapping")}
    denial = _schema_denial(delivery)
    if denial is not None:
        return {"ok": False, "error": denial}
    outcome = delivery.get("outcome")
    cls, n_present, t_present = _shape_of(delivery)
    trusted = trusted_phase(state)
    phase = trusted.get("phase") or _delivery_phase(delivery)

    # I / S / V / Q (incl. A.1–A.4 trusted-phase resolution)
    denial = _envelope_denial(state, delivery)
    if denial is not None:
        return {"ok": False, "error": denial}

    # Shape rows (§1.3) — the phase is the TRUSTED phase, never the claim.
    denial = _shape_denial(cls, n_present, t_present, phase)
    if denial is not None:
        return {"ok": False, "error": denial}

    nxt = delivery.get("next") if isinstance(delivery.get("next"), dict) else None
    terminal = (delivery.get("terminal")
                if isinstance(delivery.get("terminal"), dict) else None)
    scope_id = str(delivery.get("scope_id") or "")

    # E — a typed failure is accepted as an error envelope only (row 13).
    if cls == "F":
        denial = _failure_denial(delivery, nxt, terminal)
        if denial is not None:
            return {"ok": False, "error": denial}
        return {"ok": True, "error": None}

    # O — exact immediate obligation / result-owner obligation.
    if nxt is not None:
        denial = _obligation_denial(state, phase, nxt, terminal, outcome, scope_id)
        if denial is not None:
            return {"ok": False, "error": denial}

    # A — real actor / raw PlayerType / disposition.
    denial = _receiver_denial(state, nxt, terminal, viewer_id, phase)
    if denial is not None:
        return {"ok": False, "error": denial}

    # K — actual Core current + scope G read-back (terminal-only included).
    denial = _core_denial(state, phase, nxt, terminal)
    if denial is not None:
        return {"ok": False, "error": denial}

    # T — canonical terminal identity/content (§2).
    if terminal is not None:
        denial = _terminal_denial(state, phase, nxt, terminal, scope_id)
        if denial is not None:
            return {"ok": False, "error": denial}

    # L — every PRESENT legacy sibling/embedded field.
    denial = _legacy_denial(delivery, legacy, nxt, terminal)
    if denial is not None:
        return {"ok": False, "error": denial}

    # Row 10 — a HUMAN interactive terminal-only delivery still needs a next.
    if cls == "R" and nxt is None and terminal is not None \
            and terminal.get("controller") != CONTROLLER_AI:
        return {"ok": False, "error": delivery_error(
            DELIVERY_MISSING_RECEIVER, stage="receiver",
            detail="a HUMAN interactive result still requires its next receiver")}
    return {"ok": True, "error": None}


# ---------------------------------------------------------------------------
# Per-state book (session/Core turn state; NOT the viewer cache)
# ---------------------------------------------------------------------------
_BOOK_ATTR = "_session_turn_book"


class SessionTurnBook:
    """The ONE session/Core completion ledger + scope registry."""

    def __init__(self, session_ns: str):
        self.session_ns = session_ns
        self.turn_number = 1
        self.scopes: Dict[str, _Scope] = {}
        self.records: List[_Record] = []
        self.entries: List[Dict[str, Any]] = []
        self.entered_scope_ids: set = set()
        #: Persisted role selection latched at scope entry (delta §1.2 re-
        #: evaluation rule): the office owner/authority reason is resolved ONCE
        #: per (scope_id, role tag) and NOT switched on each display refresh.
        self.role_selections: Dict[Tuple[str, str], Dict[str, Any]] = {}
        #: Owner receipts issued by the engine for a real production command
        #: (F6): a completion recorded as an ACTION must present one of these.
        self.receipts: Dict[str, Dict[str, Any]] = {}
        #: COMMITTED owner facts (fact_ref -> receipt) the engine has issued
        #: (R10-1): an ACTION may authorise via a committed fact reference. A bare
        #: or unregistered string is NOT a committed fact.
        self.committed_facts: Dict[str, Dict[str, Any]] = {}
        #: Receipt IDs already CONSUMED by a committed completion (once-only, §4.4).
        self.consumed_receipts: set = set()
        #: Monotonic ledger revision (a witness value, NOT the crc32 business
        #: digest): the `satisfied_at_revision <= core_revision_now` ceiling rule
        #: requires a non-decreasing revision, which a digest is not.
        self.revision_counter = 0

    # -- OID / DK factories (delta §2.2, lossless to R1's tuple) --------------
    def oid(self, phase: str, substep: str, actor_slot: Tuple,
            scope_id: str) -> Tuple:
        return (self.session_ns, self.turn_number, scope_id, phase, substep,
                actor_slot)

    def dk(self, phase: str, substep: str, actor: Optional[str],
           core_revision_before: int) -> Tuple:
        return (self.session_ns, self.turn_number, phase, substep, actor,
                core_revision_before)

    # -- satisfaction / replay lookup (stable OID; revision ceiling) ----------
    def satisfied(self, oid: Tuple, scope_id: str, revision_now: int) -> bool:
        for rec in self.records:
            if rec.obligation_id == oid and self._scope_of(rec) == scope_id \
                    and rec.satisfied_at_revision <= revision_now:
                return True
        return False

    def satisfies_kind(self, oid: Tuple) -> Optional[str]:
        for rec in self.records:
            if rec.obligation_id == oid:
                return rec.satisfied_kind
        return None

    def _scope_of(self, rec: _Record) -> str:
        # OID index 2 is the scope_id (stable identity, delta §2.2).
        return rec.obligation_id[2] if len(rec.obligation_id) > 2 else ""

    def replay_denied(self, dk: Tuple) -> bool:
        return any(rec.dispatch_key == dk for rec in self.records)

    def write(self, rec: _Record) -> None:
        # assign the monotonic post-commit revision, then advance the counter.
        self.revision_counter += 1
        rec.satisfied_at_revision = self.revision_counter
        self.records.append(rec)

    def reset_for_new_year(self) -> None:
        """On successful atomic year advance: reset ONLY the new-year obligation
        keys + scopes. Characters/economy/wars are NOT touched (R1 §5)."""
        self.turn_number += 1
        self.scopes.clear()
        self.records.clear()
        self.entries.clear()
        self.entered_scope_ids.clear()
        self.role_selections.clear()
        self.receipts.clear()
        self.committed_facts.clear()
        self.consumed_receipts.clear()


# ---------------------------------------------------------------------------
# D16 — the ONE annual ledger publication boundary (FC-D16-06/08/09)
# ---------------------------------------------------------------------------
class YearPrepareError(RuntimeError):
    """Typed pre-commit preparation failure (never a Core/advance failure)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def prepare_new_year_book(state: Any, target_turn: int) -> Optional[SessionTurnBook]:
    """Build the DETACHED candidate ledger for the next year (no side effect).

    Consumed ONLY by the annual use-case (``game_api.advance_year``) inside the
    existing re-entry guard and BEFORE the Core commit. It never writes the state,
    never mints a scope, never writes a cursor / receipt / completion: it returns
    a detached ``SessionTurnBook`` whose single pointer publication happens AFTER
    the Core commit succeeded (failure atomicity, FC-06).

    * no live book -> ``None`` (a never-registered CLI state is not given a ledger);
    * live book out of sync with the Core turn -> ``TURN_BOOK_OUT_OF_SYNC``;
    * any other preparation problem -> ``YEAR_LEDGER_PREPARE_FAILED``.

    The candidate inherits ``session_ns`` + the monotonic ``revision_counter`` then
    reuses the EXISTING ``reset_for_new_year`` on the CANDIDATE only.
    """
    book = getattr(state, _BOOK_ATTR, None)
    if book is None:
        return None
    turn = getattr(state, "turn", None)
    core_turn = getattr(turn, "turn_number", None)
    if not isinstance(core_turn, int):
        raise YearPrepareError("YEAR_LEDGER_PREPARE_FAILED")
    if int(book.turn_number) != int(core_turn):
        raise YearPrepareError("TURN_BOOK_OUT_OF_SYNC")
    if int(target_turn) != int(core_turn) + 1:
        raise YearPrepareError("YEAR_LEDGER_PREPARE_FAILED")
    try:
        candidate = SessionTurnBook(book.session_ns)
        candidate.turn_number = int(core_turn)
        candidate.revision_counter = int(book.revision_counter)
        candidate.reset_for_new_year()  # candidate only; the live book is untouched
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("failed to prepare the new-year candidate book")
        raise YearPrepareError("YEAR_LEDGER_PREPARE_FAILED") from exc
    return candidate


def _session_ns(state: Any) -> str:
    return f"session-{id(state)}"


def _book(state: Any) -> SessionTurnBook:
    book = getattr(state, _BOOK_ATTR, None)
    if book is None:
        book = SessionTurnBook(_session_ns(state))
        # D16 (FC-D16-06/10): a LATE attach (mid-year / new-year cold start) binds
        # the CURRENT Core turn. Core ``state.turn.turn_number`` is the single
        # authority; an existing book is never re-bound on a read path.
        turn = getattr(state, "turn", None)
        core_turn = getattr(turn, "turn_number", None)
        if isinstance(core_turn, int) and core_turn > 0:
            book.turn_number = core_turn
        try:
            setattr(state, _BOOK_ATTR, book)
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to attach session turn book")
    return book


def current_revision(state: Any) -> int:
    """Authoritative ledger revision: the session book's monotonic counter when a
    book exists (the frozen ceiling rule needs a non-decreasing revision), else the
    Core business digest as a bootstrap witness."""
    book = getattr(state, _BOOK_ATTR, None)
    if book is not None:
        return book.revision_counter
    from src.api import session_access
    try:
        return int(session_access.core_business_revision(state))
    except Exception:  # pragma: no cover - defensive
        return 0


# ---------------------------------------------------------------------------
# PlayerType resolution — the FROZEN AI criterion (delta §1.2).
# ---------------------------------------------------------------------------
def player_of_faction(state: Any, faction_id: Optional[str]) -> Optional[Any]:
    if not faction_id:
        return None
    getter = getattr(state, "get_player_by_faction", None)
    if callable(getter):
        return getter(faction_id)
    return None


def controller_of(state: Any, actor_player_id: Optional[str]) -> str:
    """Resolve ``controller`` for the player-owned actor: HUMAN | AI | OBSERVER.

    The value is the ACTUAL ``PlayerType`` of the owning player, NEVER the
    viewer-relative political ``mode`` and NEVER ``player_id != viewer``.
    """
    if not actor_player_id:
        return CONTROLLER_NONE
    player = state.get_player(actor_player_id) if hasattr(state, "get_player") else None
    if player is None:
        return CONTROLLER_NONE
    ptype = getattr(player, "player_type", None)
    if ptype is PlayerType.AI:
        return CONTROLLER_AI
    if ptype is PlayerType.HUMAN:
        return CONTROLLER_HUMAN
    return CONTROLLER_NONE  # OBSERVER (or unknown) is never an executable turn


def is_ai_actor(state: Any, actor_player_id: Optional[str]) -> bool:
    """The one AI predicate used by the drain / Store scheduler."""
    return controller_of(state, actor_player_id) == CONTROLLER_AI


def _office_owning_player(state: Any, officer_id: Optional[int]) -> Optional[Any]:
    """office -> faction -> validated owning player (ScenarioLoader bijection)."""
    if officer_id is None:
        return None
    figure = state.get_member(officer_id) if hasattr(state, "get_member") else None
    if figure is None:
        return None
    return player_of_faction(state, getattr(figure, "faction_id", None))


def resolve_office_controller(state: Any, officer_id: Optional[int]) -> str:
    """office -> faction -> player -> PlayerType (fail-closed, never AI fallback).

    Returns HUMAN | AI | NONE. A missing/invalid mapping is NONE (structural),
    never an AI fallback (delta §1.2 step 6).
    """
    player = _office_owning_player(state, officer_id)
    if player is None:
        return CONTROLLER_NONE  # invalid faction-controller mapping -> fail-closed
    return controller_of(state, player.player_id)


def resolve_role_selection(state: Any, scope_id: str, tag: str,
                          officer_id: Optional[int], anchor_player_id: Optional[str],
                          authority_reason: Optional[str] = None) -> Dict[str, Any]:
    """Resolve and PERSIST the office-holder -> validated owning player mapping
    for a role obligation (F1/A3-01).

    The office holder is mapped to its owning player (office -> faction -> player)
    so the seat can be made CURRENT by ``select_actor`` (a bare officer id cannot
    be handed to ``set_current_player``). An office holder whose faction has NO
    owning player is a ``ScheduleDerivationError`` — fail-closed, never a silent
    structural NONE (delta §1.2 step 6). ``officer_id is None`` is a genuine
    structural absence (CONTROLLER_NONE).

    The selection is latched once per ``(scope_id, tag)`` and re-used for the
    scope lifetime (delta §1.2 re-evaluation rule: the office owner must NOT be
    switched on each display refresh).
    """
    book = _book(state)
    key = (scope_id, tag)
    cached = book.role_selections.get(key)
    if cached is not None:
        return cached
    if officer_id is None:
        selection = {"officer_id": None, "actor_player_id": None,
                     "controller": CONTROLLER_NONE, "anchor_player_id": anchor_player_id,
                     "authority_reason": authority_reason or "no_office_holder"}
    else:
        player = _office_owning_player(state, officer_id)
        if player is None:
            raise ScheduleDerivationError(f"{tag.upper()}_CONTROLLER_MAPPING_INVALID")
        selection = {"officer_id": officer_id,
                     "actor_player_id": player.player_id,
                     "controller": controller_of(state, player.player_id),
                     "anchor_player_id": anchor_player_id,
                     # §4.1: preserve the AUTHORITATIVE resolver reason (never a
                     # generic mapping label) while mapping office -> owning player.
                     "authority_reason": authority_reason or "validated_owning_player"}
    book.role_selections[key] = selection
    return selection


# ---------------------------------------------------------------------------
# Scope entry / phase entry
# ---------------------------------------------------------------------------
def _entry_actor(state: Any) -> Optional[str]:
    getter = getattr(state, "get_current_player", None)
    current = getter() if callable(getter) else None
    return getattr(current, "player_id", None)


def mint_scope(state: Any, phase: str) -> _Scope:
    """Idempotent scope mint (same scope_id for a phase until re-entry)."""
    book = _book(state)
    scope = book.scopes.get(phase)
    if scope is None:
        scope = _Scope(scope_id=uuid.uuid4().hex, phase=phase,
                       entry_revision=current_revision(state),
                       actor=_entry_actor(state))
        book.scopes[phase] = scope
    return scope


def current_scope_id(state: Any, phase: str) -> Optional[str]:
    scope = _book(state).scopes.get(phase)
    return scope.scope_id if scope else None


def trusted_phase(state: Any) -> Dict[str, Any]:
    """A.1/A.3 (I1a): the ONE authoritative phase binding.

    * **P1** — ``SessionTurnBook.entries`` is append-only; the LAST entry is the
      only authority for the current phase (and its scope generation). An empty
      journal or an entry without a typed ``phase``/``scope_id`` is NOT inferred.
    * **P2** — the phase must still be live: ``book.scopes[phase].scope_id`` must
      equal the entry's scope (a cleaned/cross-turn scope is dead).
    * **P3** — a service-issued committed entry receipt (``receipt_id``) must
      still match this session/turn/phase and its source phase must be committed;
      a legacy entry is only legitimate on a never-registered CLI/legacy state
      (``TURN_BINDING_SCOPE_LIVE_ONLY`` diagnostic — no new field, no forgery).

    Returns a plain mapping: ``phase``/``scope_id`` are ``None`` on any failure,
    with ``code``/``stage``/``detail`` carrying the typed fail-closed denial.
    Pure read: never mints, never writes, never defaults to ``"senate"``.
    """
    result: Dict[str, Any] = {
        "phase": None, "scope_id": None, "receipt_id": None,
        "diagnostic": "", "code": None, "stage": None, "detail": "",
    }
    book = getattr(state, _BOOK_ATTR, None)
    if book is None or not book.entries:
        result.update(code=DELIVERY_INVALID, stage="phase",
                      detail="no committed phase entry binds this delivery")
        return result
    last = book.entries[-1]
    phase = last.get("phase")
    scope_id = last.get("scope_id")
    if not isinstance(phase, str) or not phase \
            or not isinstance(scope_id, str) or not scope_id:
        result.update(code=DELIVERY_INVALID, stage="phase",
                      detail="the last phase entry is not bound to a phase/scope")
        return result
    # Contradictory data: two entries pointing at ONE scope with a phase conflict.
    for entry in book.entries:
        if entry.get("scope_id") == scope_id and entry.get("phase") != phase:
            result.update(code=DELIVERY_MISMATCH, stage="phase",
                          detail="conflicting phase entries for one scope")
            return result
    scope = book.scopes.get(phase)
    if scope is None or str(scope.scope_id) != scope_id:
        result.update(code=DELIVERY_MISMATCH, stage="scope",
                      detail="the trusted phase scope is no longer live")
        return result
    receipt_id = last.get("receipt_id")
    if receipt_id:
        snap = _phase_receipt_registry(book).get(receipt_id)
        if snap is None:
            result.update(code=DELIVERY_MISMATCH, stage="phase",
                          detail="the phase entry receipt is not service-issued")
            return result
        if snap.get("session_id") != _session_ns(state) \
                or snap.get("turn") != book.turn_number \
                or snap.get("phase") != phase \
                or snap.get("committed") is not True:
            result.update(code=DELIVERY_MISMATCH, stage="phase",
                          detail="the phase entry binding is forged")
            return result
        source = _PHASE_SOURCE.get(phase)
        if source:
            try:
                src_executed = bool(state.is_phase_executed(source))
            except Exception:  # pragma: no cover - defensive
                src_executed = False
            try:
                src_result = state.get_phase_result(source) is not None
            except Exception:  # pragma: no cover - defensive
                src_result = False
            if not (src_executed or src_result):
                result.update(code=DELIVERY_MISMATCH, stage="phase",
                              detail="the phase source is not committed")
                return result
        result.update(phase=phase, scope_id=scope_id, receipt_id=receipt_id,
                      diagnostic="COMMITTED_ROUTE")
        return result
    from src.api import session_access
    try:
        registered = bool(session_access.is_hotseat_registered(state))
    except Exception:  # pragma: no cover - defensive
        registered = True  # fail closed
    if registered:
        result.update(code=DELIVERY_INVALID, stage="phase",
                      detail="a registered session requires a committed phase entry")
        return result
    result.update(phase=phase, scope_id=scope_id,
                  diagnostic="TURN_BINDING_SCOPE_LIVE_ONLY")
    return result


#: Service-private registry attr for COMMITTED phase-entry receipts (item2,
#: FC-D46-04). Never a caller-held object; the receipt is a frozen snapshot so a
#: GUI cannot forge ``committed=True``.
_PHASE_RECEIPTS_ATTR = "_committed_phase_receipts"

#: The committed advance source phase for each target phase (FC-D46-04 binding).
_PHASE_SOURCE: Dict[str, str] = {
    "population": "forum",
    "senate": "population",
}


def _phase_receipt_registry(book: "SessionTurnBook") -> Dict[str, Any]:
    reg = getattr(book, _PHASE_RECEIPTS_ATTR, None)
    if reg is None:
        reg = {}
        try:
            setattr(book, _PHASE_RECEIPTS_ATTR, reg)
        except Exception:  # pragma: no cover - defensive
            pass
    return reg


def issue_committed_phase_entry_receipt(
        state: Any, *, command_id: str, phase: str, actor: Optional[str] = None,
        txn_id: str = "", domain_scope_id: str = "", payload_digest: str = "",
        core_revision_before: Optional[int] = None,
        core_revision_after: Optional[int] = None) -> dict:
    """item2/FC-D46-04 ISSUER: the phase-advance OWING command's commit hook.

    Called by the advance API (``session_api.advance_population_phase`` /
    ``forum_api.advance_forum_phase``) AFTER the real ``mark_phase_executed``
    commit and BEFORE returning to the adapter. The receipt is a SERVICE-private
    immutable snapshot (``committed=True`` set HERE, never by the caller) bound to
    session/turn/source->target phase/actor/txn/revision/commit fact, and
    registered in the book registry keyed by ``receipt_id``. ``enter_phase``
    consumes it EXACTLY ONCE.
    """
    book = _book(state)
    reg = _phase_receipt_registry(book)
    rev = current_revision(state)
    snap = types.MappingProxyType({
        "receipt_id": uuid.uuid4().hex,
        "issued_by": str(command_id),
        "committed": True,
        "command_id": str(command_id),
        "phase": phase,
        "source_phase": _PHASE_SOURCE.get(phase, ""),
        "session_id": _session_ns(state),
        "turn": book.turn_number,
        "txn_id": str(txn_id),
        "domain_scope_id": str(domain_scope_id),
        "actor": actor if actor is not None else _entry_actor(state),
        "core_revision_before": (int(core_revision_before)
                                 if core_revision_before is not None else rev),
        "core_revision_after": (int(core_revision_after)
                                if core_revision_after is not None else rev),
        "payload_digest": str(payload_digest),
    })
    reg[snap["receipt_id"]] = snap
    return dict(snap)


def enter_phase(state: Any, transition_receipt: Optional[dict]) -> dict:
    """Consume a successfully COMMITTED phase-advance receipt EXACTLY ONCE.

    Emits an immutable ``PhaseEntered`` record and mints a FRESH scope for the new
    phase (leaving the old phase invalidates old handles/commands, R1 §5). Visual
    navigation is NOT phase entry — only a committed advance receipt entry event
    reaches here.

    D4/D6 item2 (FC-D46-04): on a REGISTERED Hot-seat session the receipt MUST be
    a service-issued committed receipt (a GUI plain dict with ``committed=True``
    is refused: ``NOT_COMMITTED``). A never-registered CLI/legacy state keeps the
    historical low-level semantics (a direct primitive call with a committed dict).
    """
    from src.api import session_access
    if session_access.is_hotseat_registered(state):
        return _enter_phase_from_committed_receipt(state, transition_receipt)
    return _enter_phase_legacy(state, transition_receipt)


def _enter_phase_legacy(state: Any, transition_receipt: Optional[dict]) -> dict:
    """Never-registered CLI/legacy low-level semantics (historical, unchanged)."""
    if not isinstance(transition_receipt, dict) or not transition_receipt.get(
            "committed", False):
        return {"success": False, "reason": "NOT_COMMITTED",
                "message": "phase entry requires a committed advance receipt"}
    receipt_id = transition_receipt.get("receipt_id") or transition_receipt.get(
        "command_id") or ""
    phase = transition_receipt.get("phase")
    if not phase:
        return {"success": False, "reason": "MISSING_PHASE"}
    book = _book(state)
    dedup = (book.turn_number, receipt_id, phase)
    if dedup in getattr(book, "entered_scope_ids", set()):
        return {"success": False, "reason": "DUPLICATE_RECEIPT"}
    scope = _Scope(scope_id=uuid.uuid4().hex, phase=phase,
                   entry_revision=current_revision(state), actor=_entry_actor(state))
    book.scopes[phase] = scope
    book.entered_scope_ids.add(dedup)
    event = {
        "scope_id": scope.scope_id,
        "phase": phase,
        "core_revision": scope.entry_revision,
        "actor": scope.actor,
    }
    book.entries.append(event)
    return {"success": True, "phase_entered": event}


def _enter_phase_from_committed_receipt(state: Any,
                                        transition_receipt: Optional[dict]) -> dict:
    """REGISTERED Hot-seat item2 consumption (service-private receipt, once-only).

    Failure enum (FC-D46-04): NOT_COMMITTED / MISSING_PHASE / DUPLICATE_RECEIPT /
    BINDING_MISMATCH / SOURCE_NOT_COMMITTED. Never mints a scope on failure.
    """
    if not isinstance(transition_receipt, dict):
        return {"success": False, "reason": "NOT_COMMITTED",
                "message": "entry requires a service-issued committed receipt"}
    book = _book(state)
    reg = _phase_receipt_registry(book)
    rid = transition_receipt.get("receipt_id")
    snap = reg.get(rid) if rid else None
    if snap is None:
        return {"success": False, "reason": "NOT_COMMITTED",
                "message": "receipt is not a service-issued committed receipt"}
    if not snap.get("committed"):
        return {"success": False, "reason": "NOT_COMMITTED"}
    # The presented copy must MATCH the issued immutable snapshot field-for-field.
    for field in ("committed", "command_id", "phase", "session_id", "turn",
                  "txn_id", "domain_scope_id", "actor",
                  "core_revision_before", "core_revision_after", "payload_digest"):
        if transition_receipt.get(field) != snap.get(field):
            return {"success": False, "reason": "BINDING_MISMATCH",
                    "message": f"receipt field {field} does not match the issued receipt"}
    phase = snap.get("phase")
    if not phase:
        return {"success": False, "reason": "MISSING_PHASE"}
    if snap.get("session_id") != _session_ns(state) \
            or snap.get("turn") != book.turn_number:
        return {"success": False, "reason": "BINDING_MISMATCH",
                "message": "receipt is bound to a different session/turn"}
    source = snap.get("source_phase")
    if source:
        try:
            src_executed = bool(state.is_phase_executed(source))
        except Exception:  # pragma: no cover - defensive
            src_executed = False
        try:
            src_result = state.get_phase_result(source) is not None
        except Exception:  # pragma: no cover - defensive
            src_result = False
        if not (src_executed or src_result):
            return {"success": False, "reason": "SOURCE_NOT_COMMITTED",
                    "message": f"source phase {source} is not committed"}
    dedup = (book.turn_number, snap.get("receipt_id"), phase)
    if dedup in getattr(book, "entered_scope_ids", set()):
        return {"success": False, "reason": "DUPLICATE_RECEIPT"}
    scope = _Scope(scope_id=uuid.uuid4().hex, phase=phase,
                   entry_revision=current_revision(state), actor=_entry_actor(state))
    book.scopes[phase] = scope
    book.entered_scope_ids.add(dedup)
    event = {
        "scope_id": scope.scope_id,
        "phase": phase,
        "core_revision": scope.entry_revision,
        "actor": scope.actor,
        "receipt_id": snap.get("receipt_id"),
    }
    book.entries.append(event)
    return {"success": True, "phase_entered": event}


# ---------------------------------------------------------------------------
# Obligation derivation (R1 §3 table -> implementable single derived view)
# ---------------------------------------------------------------------------
class ScheduleDerivationError(RuntimeError):
    """Owner facts unavailable/invalid; never structural inapplicability."""


def _population_required_offices(state: Any) -> set:
    """Required offices with non-empty candidate lists (an ERROR, never a
    structural empty, on retrieval failure — delta §4.1).

    Read through the **service-private validated-read boundary**
    ``population_api._get_candidates_impl``: the design-designated internal
    continuation read (see the ``population_api.get_candidates`` docstring — "the
    internal ``_get_candidates_impl`` is used by already-authorized internal
    continuations"). The coordinator is an INTERNAL continuation, not a public
    caller; the PUBLIC guarded ``population_api.get_candidates`` boundary is NOT
    weakened, bypassed or re-exposed, and ``DENIED`` is never reclassified as
    ``EMPTY``. A retrieval failure / throw / shape violation is a
    ``ScheduleDerivationError`` (ERROR), NEVER a structural NONE/EMPTY."""
    from src.api import population_api
    try:
        cand = population_api._get_candidates_impl(state)
    except Exception as exc:
        raise ScheduleDerivationError("POPULATION_CANDIDATE_RETRIEVAL_FAILED") from exc
    if not isinstance(cand, dict) or not cand.get("success"):
        raise ScheduleDerivationError("POPULATION_CANDIDATE_RETRIEVAL_FAILED")
    data = cand.get("data")
    offices = {"consul", "censor", "praetor", "quaestor", "tribune"}
    if not isinstance(data, dict) or set(data) != offices or any(
            not isinstance(rows, list) for rows in data.values()):
        raise ScheduleDerivationError("POPULATION_CANDIDATE_SCHEMA_INVALID")
    return {office for office, rows in data.items() if rows}


def _population_obligations(state: Any, scope_id: str, substep: str) -> List[Obligation]:
    book = _book(state)
    required = _population_required_offices(state)
    votes_by_player: Dict[str, set] = {}
    try:
        for pid, office, _fid in state.get_population_votes():
            votes_by_player.setdefault(pid, set()).add(office)
    except Exception:  # pragma: no cover - defensive
        votes_by_player = {}

    out: List[Obligation] = []
    for player in state.get_all_players():
        pid = player.player_id
        controller = controller_of(state, pid)
        slot = ("player", pid)
        oid = book.oid("population", substep, slot, scope_id)
        covered = (not required) or required.issubset(votes_by_player.get(pid, set()))
        try:
            done = bool(state.get_vote_completed(pid))
        except Exception:  # pragma: no cover - defensive
            done = False
        if substep == "campaign":
            try:
                own = bool(state.get_batch_completed(pid))
            except Exception:  # pragma: no cover - defensive
                own = False
            # A completed vote (or full ballot coverage) implies the seat's
            # campaign/entry work closed (the fixed-five submission is the
            # campaign+vote trigger).
            satisfied = bool(own) or done or covered
            source = "batch_completed"
        else:  # "vote"
            satisfied = done or covered
            source = "vote_covered"
        if book.satisfied(oid, scope_id, current_revision(state)):
            satisfied = True
        out.append(Obligation(
            obligation_id=oid, scope_id=scope_id, phase="population",
            substep=substep, actor_slot=slot, actor_player_id=pid,
            officer_id=None, controller=controller,
            required_operation=substep, satisfied=satisfied,
            satisfied_kind=(book.satisfies_kind(oid) if satisfied else None),
            source_fact=source))
    return out


def _singleton_obligations(state: Any, phase: str, scope_id: str) -> List[Obligation]:
    """Singleton / all-controller obligations for the non-population phases.

    Global owner G = the phase-entry Core current executable actor latched at
    scope entry (R1 §3). Readiness is the genuine existing result/execution
    predicate (``is_phase_executed`` / recorded phase result) — a swallowed
    exception is NOT completion.
    """
    book = _book(state)
    scope = book.scopes.get(phase)
    actor = scope.actor if scope else _entry_actor(state)
    controller = controller_of(state, actor)
    slot = ("singleton", scope_id)
    oid = book.oid(phase, "execute", slot, scope_id)
    try:
        executed = bool(state.is_phase_executed(phase))
    except Exception:  # pragma: no cover - defensive
        executed = False
    try:
        has_result = state.get_phase_result(phase) is not None
    except Exception:  # pragma: no cover - defensive
        has_result = False
    satisfied = executed or has_result
    if book.satisfied(oid, scope_id, current_revision(state)):
        satisfied = True
    return [Obligation(
        obligation_id=oid, scope_id=scope_id, phase=phase, substep="execute",
        actor_slot=slot, actor_player_id=actor, officer_id=None,
        controller=controller, required_operation="execute", satisfied=satisfied,
        satisfied_kind=(book.satisfies_kind(oid) if satisfied else None),
        source_fact="phase_executed_or_result")]


def obligations(state: Any, phase: Optional[str] = None,
                substep: Optional[str] = None) -> ScheduleSnapshot:
    """The single derived obligation view (R1 §2/§3).

    F1: the FROZEN per-substep schedule is wired into the COMMON path — forum
    (retirement then market, per canonical controller) and senate (actual
    proposal-holder, per-controller ballots, finalization) are no longer collapsed
    to a single phase-entry ``execute`` singleton.
    """
    phase = phase or _current_phase(state)
    scope = mint_scope(state, phase)
    try:
        if phase == "population":
            substep = substep or _population_substep(state)
            items = _population_obligations(state, scope.scope_id, substep)
        elif phase == "forum":
            # F1: all-controller retirement round THEN market round (R1 §3).
            items = (_forum_obligations(state, scope.scope_id, "retirement")
                     + _forum_obligations(state, scope.scope_id, "market"))
        elif phase == "senate":
            items = _senate_schedule(state, scope.scope_id)
        else:
            items = _singleton_obligations(state, phase, scope.scope_id)
    except ScheduleDerivationError as exc:
        return ScheduleSnapshot(phase=phase, scope_id=scope.scope_id,
                                obligations=(), errors=(str(exc),))
    return ScheduleSnapshot(phase=phase, scope_id=scope.scope_id,
                            obligations=tuple(items))


def _political_system(state: Any) -> Any:
    from src.core.systems.political_system import PoliticalSystem
    return PoliticalSystem(state)


def _senate_schedule(state: Any, scope_id: str) -> List[Obligation]:
    """Frozen senate role schedule (R1 §3): proposal-holder -> per-controller
    ballots -> finalization. The office owner is resolved through the existing
    political resolver and mapped to the ACTUAL ``PlayerType`` (never the
    viewer-relative ``mode``).
    """
    book = _book(state)
    scope = book.scopes.get("senate")
    G = scope.actor if scope else _entry_actor(state)
    rev_now = current_revision(state)
    out: List[Obligation] = []

    # --- proposal obligation: the actual office owner (never the viewer) ------
    # §4.1: a RESOLVER RETRIEVAL/MAPPING ERROR must fail closed (a schedule
    # error), NEVER be laundered into a structural NONE. Only a resolver-backed
    # ``actor is None`` (no eligible host) is a genuine structural absence.
    prop_reason = "no_office_holder"
    officer_id = None
    if G:
        try:
            pc = _political_system(state).resolve_proposal_control(G)
        except Exception as exc:
            raise ScheduleDerivationError("SENATE_PROPOSAL_RESOLVER_FAILED") from exc
        officer_id = pc.get("actor")
        prop_reason = pc.get("authority_reason") or "no_office_holder"
    proposals = state.get_senate_proposals()
    prop_oid = book.oid("senate", "proposal", ("singleton", scope_id), scope_id)
    # F1/A3-01: map the office holder to its VALIDATED owning player so the seat
    # can be made CURRENT by ``select_actor`` (a bare officer id cannot be handed
    # to ``set_current_player``); fail-closed on an invalid mapping; persist the
    # selection for the scope lifetime (never switched on a display refresh).
    prop_role = resolve_role_selection(state, scope_id, "proposal", officer_id, G,
                                       authority_reason=prop_reason)
    try:
        decision_complete = bool(state.senate_proposal_decision_complete)
    except Exception:  # pragma: no cover - defensive
        decision_complete = False
    try:
        no_host = state.get_presiding_officer() is None
    except Exception:  # pragma: no cover - defensive
        no_host = False
    prop_sat = (bool(proposals) or decision_complete or no_host
                or book.satisfied(prop_oid, scope_id, rev_now))
    # G7-W3 restore (C1 / 02-INV-Exception): on a REGISTERED senate scope a still
    # UNSATISFIED proposal owned by the ACTUAL AI consul is the HUMAN presenter's
    # CONFIRMATION obligation, carried by the existing validated phase-entry actor
    # G. The latched DECISION owner (``book.role_selections``) stays the AI: no
    # owner record is rewritten, no other player is chosen, and a missing /
    # non-HUMAN G keeps the ORIGINAL owner semantics (the continuation gate then
    # fails closed instead of draining an AI package).
    prop_actor = prop_role["actor_player_id"]
    prop_ctrl = prop_role["controller"]
    if (_is_registered(state) and not prop_sat
            and prop_role["controller"] == CONTROLLER_AI
            and G is not None and G != prop_role["actor_player_id"]
            and controller_of(state, G) == CONTROLLER_HUMAN):
        prop_actor = G
        prop_ctrl = CONTROLLER_HUMAN
    out.append(Obligation(
        obligation_id=prop_oid, scope_id=scope_id, phase="senate",
        substep="proposal", actor_slot=("singleton", scope_id),
        actor_player_id=prop_actor,
        officer_id=prop_role["officer_id"],
        controller=prop_ctrl,
        required_operation="proposal", satisfied=prop_sat,
        satisfied_kind=(book.satisfies_kind(prop_oid) if prop_sat else None),
        source_fact="senate_proposals"))

    # --- per-proposal ballot obligation for each canonical controller --------
    votes = state.get_senate_votes_copy()
    for proposal in proposals:
        pid_prop = proposal.get("id") if isinstance(proposal, dict) else None
        for player in state.get_all_players():
            ctrl = controller_of(state, player.player_id)
            if ctrl == CONTROLLER_NONE:
                continue
            slot = ("player", player.player_id)
            substep = f"vote:{pid_prop}"
            oid = book.oid("senate", substep, slot, scope_id)
            voted = (pid_prop is not None
                     and pid_prop in votes.get(player.player_id, {}))
            if book.satisfied(oid, scope_id, rev_now):
                voted = True
            out.append(Obligation(
                obligation_id=oid, scope_id=scope_id, phase="senate",
                substep=substep, actor_slot=slot, actor_player_id=player.player_id,
                officer_id=None, controller=ctrl, required_operation="vote",
                satisfied=voted,
                satisfied_kind=(book.satisfies_kind(oid) if voted else None),
                source_fact="senate_ballot"))

    # --- veto obligation (R1 §3 senate veto row): the ACTUAL eligible tribune
    #     (office -> faction -> actual PlayerType), never a viewer-relative mode.
    #     F1/A3-01: the resolver ANCHOR is the LAST SCHEDULED VOTER (the frozen
    #     delta §1.2 anchor), NOT the phase-entry actor G. "all voter barrier
    #     first": it becomes a REQUIRED stop only once every required ballot is in;
    #     then it applies iff a passed candidate exists ("zero passed candidates OR
    #     resolver-backed no eligible tribune" = the structural-absence condition).
    #     Satisfied by a real veto decision receipt recorded in the ledger. ------
    vote_obs = [o for o in out if o.required_operation == "vote"]
    last_voter_id = vote_obs[-1].actor_player_id if vote_obs else G
    veto_anchor = last_voter_id or G
    veto_oid = book.oid("senate", "veto", ("singleton", scope_id), scope_id)
    # §4.1: resolver / candidate RETRIEVAL errors on the veto path FAIL CLOSED
    # (a schedule error), never silently dropped. Whether the veto is actually
    # REQUIRED is re-derived from real business eligibility (a passed candidate),
    # so a legitimate eligibility change is honoured; the latched OWNER mapping is
    # preserved by ``resolve_role_selection`` (never switched on a display refresh).
    veto_holder = None
    veto_reason = "no_office_holder"
    if veto_anchor:
        try:
            vc = _political_system(state).resolve_veto_control(veto_anchor)
        except Exception as exc:
            raise ScheduleDerivationError("SENATE_VETO_RESOLVER_FAILED") from exc
        veto_holder = vc.get("actor")
        veto_reason = vc.get("authority_reason") or "no_office_holder"
    all_ballots = bool(proposals) and all(o.satisfied for o in vote_obs)
    veto_required = False
    if veto_holder is not None and all_ballots:
        try:
            passed = _political_system(state).build_vote_results_and_candidates().get(
                "veto_candidate_ids") or []
        except Exception as exc:
            raise ScheduleDerivationError(
                "SENATE_VETO_CANDIDATE_DERIVATION_FAILED") from exc
        veto_required = bool(passed)
    if veto_required:
        # F1/A3-01: map the ACTUAL eligible tribune to its VALIDATED owning player
        # and persist the role selection for the scope lifetime.
        veto_role = resolve_role_selection(state, scope_id, "veto", veto_holder,
                                           veto_anchor, authority_reason=veto_reason)
    else:
        latched = book.role_selections.get((scope_id, "veto"))
        veto_role = {"officer_id": (latched or {}).get("officer_id", veto_holder),
                     "actor_player_id": None, "controller": CONTROLLER_NONE,
                     "anchor_player_id": veto_anchor,
                     "authority_reason": veto_reason}
    veto_actor = veto_role["actor_player_id"]
    veto_ctrl = veto_role["controller"]
    veto_off = veto_role["officer_id"]
    veto_sat = (not veto_required) or book.satisfied(veto_oid, scope_id, rev_now)
    # G7 (AC-S2-01/02): on a REGISTERED senate scope a REQUIRED but UNSATISFIED
    # veto owned by the ACTUAL AI tribune is the verified HUMAN presenter G's
    # CONFIRMATION obligation — the SAME single-authority projection the proposal
    # presenter already uses. The latched DECISION owner (``book.role_selections``)
    # stays the AI: no owner record is rewritten, no other player is chosen, and a
    # missing / non-HUMAN G keeps the original AI row so the continuation gate
    # fails closed instead of auto-draining the decider.
    if (_is_registered(state) and veto_required and not veto_sat
            and veto_role["controller"] == CONTROLLER_AI
            and G is not None and G != veto_role["actor_player_id"]
            and controller_of(state, G) == CONTROLLER_HUMAN):
        veto_actor = G
        veto_ctrl = CONTROLLER_HUMAN
    out.append(Obligation(
        obligation_id=veto_oid, scope_id=scope_id, phase="senate",
        substep="veto", actor_slot=("singleton", scope_id),
        actor_player_id=veto_actor, officer_id=veto_off,
        controller=veto_ctrl,
        required_operation="veto", satisfied=veto_sat,
        satisfied_kind=(book.satisfies_kind(veto_oid) if veto_sat else None),
        source_fact="senate_veto"))

    # --- finalization is the ACTION performed when every required ballot is in,
    #     not a precondition of readiness: it is intentionally NOT an obligation
    #     here (so ``phase_ready('senate')`` is the pre-finalization all-ballots
    #     predicate the F3 gate needs). ------------------------------------------
    return out


def _current_phase(state: Any) -> str:
    try:
        from src.api.session_api import _infer_current_phase_id
        pid = _infer_current_phase_id(state)
        if pid:
            return pid
    except Exception:  # pragma: no cover - defensive
        pass
    return "population"


def _population_substep(state: Any) -> str:
    """vote unless the campaign round is still outstanding for some controller."""
    snap_phase = "population"
    scope = mint_scope(state, snap_phase)
    camp = _population_obligations(state, scope.scope_id, "campaign")
    if any(o.is_executable and not o.satisfied for o in camp):
        return "campaign"
    return "vote"


# ---------------------------------------------------------------------------
# phase_ready (exact all-controller predicate)
# ---------------------------------------------------------------------------
def phase_ready(state: Any, phase: Optional[str] = None,
                scope_id: Optional[str] = None) -> bool:
    """True iff every REQUIRED obligation in the phase scope is authoritatively
    satisfied (structural inapplicability removes only that obligation)."""
    phase = phase or _current_phase(state)
    scope = mint_scope(state, phase)
    if scope_id is not None and scope_id != scope.scope_id:
        return False
    return obligations(state, phase).ready()


def senate_readiness(state: Any) -> Dict[str, Any]:
    """GET-PURE all-controller readiness for the senate phase (S2/FC-712-10..12).

    Derived from the REAL ballots / proposal decision / actual office owner; it
    never mints a scope, never backfills a ballot and never writes the ledger.
    ``covered``/``required`` are the aggregate tally facts (partial vs complete),
    NOT a terminal result: only the canonical finalizer writes results.
    """
    book = getattr(state, _BOOK_ATTR, None)
    scope = book.scopes.get("senate") if book is not None else None
    scope_id = scope.scope_id if scope else ""
    rev = current_revision(state)
    proposals = list(state.get_senate_proposals() or [])
    votes = state.get_senate_votes_copy() or {}
    players = [p.player_id for p in state.get_all_players()
               if controller_of(state, p.player_id)
               in (CONTROLLER_HUMAN, CONTROLLER_AI)]
    required = len(proposals) * len(players)
    covered = 0
    for proposal in proposals:
        pid_prop = proposal.get("id") if isinstance(proposal, dict) else None
        if pid_prop is None:
            continue
        for player_id in players:
            if pid_prop in votes.get(player_id, {}):
                covered += 1
    all_ballots = bool(proposals) and covered == required
    try:
        decision_complete = bool(state.senate_proposal_decision_complete)
    except Exception:  # pragma: no cover - defensive
        decision_complete = False
    try:
        no_host = state.get_presiding_officer() is None
    except Exception:  # pragma: no cover - defensive
        no_host = False
    proposal_ready = bool(proposals) or decision_complete or no_host
    errors: List[str] = []
    veto_required = False
    veto_satisfied = True
    veto_actor = None
    veto_officer = None
    if all_ballots:
        anchor = players[-1] if players else None
        try:
            control = _political_system(state).resolve_veto_control(anchor)
        except Exception as exc:
            errors.append("SENATE_VETO_RESOLVER_FAILED")
            control = {}
        veto_officer = (control or {}).get("actor")
        if veto_officer is not None and not errors:
            try:
                candidates = _political_system(
                    state).build_vote_results_and_candidates().get(
                        "veto_candidate_ids") or []
            except Exception:  # pragma: no cover - defensive
                errors.append("SENATE_VETO_CANDIDATE_DERIVATION_FAILED")
                candidates = []
            veto_required = bool(candidates)
            if veto_required:
                owner = _office_owning_player(state, veto_officer)
                if owner is None:
                    errors.append("SENATE_VETO_CONTROLLER_MAPPING_INVALID")
                    veto_satisfied = False
                else:
                    veto_actor = owner.player_id
                    veto_oid = (book.oid("senate", "veto",
                                         ("singleton", scope_id), scope_id)
                                if book is not None and scope_id else None)
                    veto_satisfied = bool(
                        veto_oid is not None
                        and book.satisfied(veto_oid, scope_id, rev))
    ready = (not errors and proposal_ready
             and (not proposals or all_ballots)
             and (not veto_required or veto_satisfied))
    return {
        "scope_id": scope_id,
        "covered": covered,
        "required": required,
        "all_ballots_ready": all_ballots,
        "proposal_ready": proposal_ready,
        "decision_complete": decision_complete,
        "no_host": no_host,
        "veto_required": veto_required,
        "veto_satisfied": veto_satisfied,
        "veto_actor": veto_actor,
        "veto_officer_id": veto_officer,
        "ready": ready,
        "errors": tuple(errors),
    }


# ---------------------------------------------------------------------------
# select_actor — sole Hot-seat cursor writer (R1 §2 / Turn-Order §1)
# ---------------------------------------------------------------------------
def select_actor(state: Any, scope_id: Optional[str] = None,
                 expected_revision: Optional[int] = None) -> dict:
    """Select the next required actor and set the Core cursor.

    Verifies the PRECEDING obligation is satisfied (stable OID) / structurally
    inapplicable, then calls the existing ``GameState.set_current_player``. No
    Store ``next_player`` shortcut. Never marks skipped seats as having acted.
    """
    phase = _current_phase(state)
    scope = mint_scope(state, phase)
    if scope_id is not None and scope_id != scope.scope_id:
        return {"success": False, "reason": "STALE_SCOPE", "actor": None}
    rev = current_revision(state)
    if expected_revision is not None and int(expected_revision) != rev:
        return {"success": False, "reason": "STALE_REVISION", "actor": None}

    snapshot = obligations(state, phase)
    if snapshot.errors:
        return {"success": False, "reason": snapshot.errors[0], "actor": None}
    outstanding = list(snapshot.outstanding())
    if not outstanding:
        return {"success": True, "actor": None, "ready": True}
    target = outstanding[0]
    if target.controller == CONTROLLER_HUMAN:
        if not state.set_current_player(target.actor_player_id):
            return {"success": False, "reason": "SET_CURRENT_FAILED", "actor": None}
        return {"success": True, "actor": target.actor_player_id,
                "controller": CONTROLLER_HUMAN, "ready": False}
    # AI actor: the cursor is set to the scheduled AI actor; the caller drains it.
    if target.actor_player_id and state.set_current_player(target.actor_player_id):
        return {"success": True, "actor": target.actor_player_id,
                "controller": CONTROLLER_AI, "ready": False}
    return {"success": True, "actor": target.actor_player_id,
            "controller": target.controller, "ready": False}


# ---------------------------------------------------------------------------
# complete_actor — write a session/Core completion record (R1 §2)
# ---------------------------------------------------------------------------
def _lease_is_valid(state: Any, lease: Any) -> bool:
    """F6: a presented command lease must be the live service-issued lease.

    ``None`` is the owner-declared / internal path (no lease presented); any other
    value must match the currently live, unconsumed lease identity — an arbitrary
    object is rejected (fail-closed).
    """
    try:
        from src.api import session_access
        live = session_access.current_lease_token(state)
    except Exception:  # pragma: no cover - defensive
        return False
    if live is None:
        return False
    lid = getattr(lease, "lease_id", None)
    if lid is None and isinstance(lease, dict):
        lid = lease.get("lease_id")
    return bool(lid) and getattr(live, "lease_id", None) == lid


def _receipt_rejection_reason(state: Any, owner_receipt: Any,
                             authoritative_fact_ref: str, expected_revision: int) -> str:
    """STALE_OWNER_RECEIPT_REVISION when the registered receipt/fact exists but its
    STORED pre-command revision is stale; MISSING_OWNER_RECEIPT otherwise (R10-1)."""
    book = getattr(state, _BOOK_ATTR, None)
    rec = None
    if isinstance(owner_receipt, dict):
        rid = owner_receipt.get("receipt_id")
        rec = getattr(book, "receipts", {}).get(rid) if rid else None
    elif isinstance(authoritative_fact_ref, str) and authoritative_fact_ref.strip():
        rec = getattr(book, "committed_facts", {}).get(authoritative_fact_ref)
    if rec is not None and rec.get("core_revision_before") != expected_revision:
        return "STALE_OWNER_RECEIPT_REVISION"
    return "MISSING_OWNER_RECEIPT"


def _resolve_owner_receipt(state: Any, owner_receipt: Any,
                           authoritative_fact_ref: str) -> Optional[Any]:
    """Resolve a presented credential to its registered IMMUTABLE snapshot (R11/F02).

    Both accepted routes — a supplied ``owner_receipt`` dict and a committed
    ``authoritative_fact_ref`` — resolve to the SAME private immutable issued
    snapshot held in the book (never to a caller-held mutable object). A ``None``
    result means the credential is absent / unregistered / altered and MUST be
    rejected. A supplied dict must MATCH the registered snapshot field-for-field.
    """
    book = getattr(state, _BOOK_ATTR, None)
    registered = getattr(book, "receipts", {}) if book is not None else {}
    if isinstance(owner_receipt, dict):
        rid = owner_receipt.get("receipt_id")
        rec = registered.get(rid) if rid else None
        if rec is None:
            return None
        # the SUPPLIED dict must MATCH the registered snapshot (reject altered copies)
        for field in ("command", "fact_ref", "core_revision_before", "actor_player_id",
                      "scope_id", "obligation_id", "kind"):
            if owner_receipt.get(field) != rec.get(field):
                return None
        return rec
    ref = authoritative_fact_ref or ""
    if not isinstance(ref, str) or not ref.strip():
        return None
    if not ref.startswith(_OWNER_FACT_NAMESPACES):
        return None
    if book is None:
        return None
    return book.committed_facts.get(ref)


def _validate_owner_receipt(state: Any, owner_receipt: Any, authoritative_fact_ref: str,
                           actor_player_id: Optional[str], scope_id: str,
                           command_id: Optional[str], *,
                           expected_revision: Optional[int] = None,
                           obligation_id: Optional[Tuple] = None,
                           satisfied_kind: Optional[str] = None) -> bool:
    """F6/§4.4/R10-1/R11-F01: a completion must name a real, BOUND owner command
    receipt or COMMITTED fact — never an arbitrary string and never an altered /
    reused / stale / mismatched copy.

    The authorisation resolves to an ENGINE-ISSUED registered receipt (via
    :func:`_resolve_owner_receipt`): either a supplied ``owner_receipt`` dict or a
    non-empty ``authoritative_fact_ref`` matching a COMMITTED owner fact. A bare /
    merely-namespaced / unregistered string is NOT an owner fact and is rejected.

    R11-F01 EXACT BINDING: every bound field must be PRESENT and EQUAL — a missing
    (``None``) issued field is NEVER a wildcard. The command (``rec['command']``)
    must equal the completion ``command_id``; the ACTOR, the SCOPE, the OBLIGATION
    (OID), the KIND and the STORED pre-command revision (== ``expected_revision``)
    must all match exactly. A registered receipt for command c1 can therefore never
    satisfy a completion for command c2, and a receipt issued without a binding
    field can never authorise a bound completion.
    """
    rec = _resolve_owner_receipt(state, owner_receipt, authoritative_fact_ref)
    if rec is None:
        return False
    book = getattr(state, _BOOK_ATTR, None)
    # once-only consumption (R10-1 / F02)
    if rec.get("receipt_id") in getattr(book, "consumed_receipts", set()):
        return False
    # EXACT, COMPLETE command/operation binding (F01): no None-as-wildcard.
    if not isinstance(command_id, str) or not command_id.strip():
        return False
    if rec.get("command") != command_id:
        return False
    # ACTOR binding — exact, including a legitimate ``None`` (singleton role) which
    # must still EQUAL the completion actor (never a wildcard over a player seat).
    if rec.get("actor_player_id") != actor_player_id:
        return False
    # SCOPE binding — exact.
    if rec.get("scope_id") != scope_id:
        return False
    # OBLIGATION (OID) binding — exact.
    if rec.get("obligation_id") != obligation_id:
        return False
    # KIND binding (R10-4a / F04: a command receipt cannot launder a no-action, and
    # a no-action credential cannot authorise a command) — exact.
    if satisfied_kind is not None and rec.get("kind") != satisfied_kind:
        return False
    # STORED pre-command revision binding (stale receipt rejected) — exact.
    if expected_revision is not None \
            and rec.get("core_revision_before") != expected_revision:
        return False
    return True


def issue_owner_receipt(state: Any, command: str, *,
                        actor_player_id: Optional[str] = None,
                        fact_ref: str = "",
                        scope_id: Optional[str] = None,
                        obligation_id: Optional[Tuple] = None,
                        kind: str = KIND_ACTION) -> dict:
    """Engine-issued owner receipt for a real production command (F6/§4.4/R10-1).

    Bound to the CURRENT (pre-command) engine revision — the caller cannot invent
    the revision. Production owners issue one AFTER their real domain commit and
    present it to ``complete_actor``; the receipt is bound to the issuing ACTOR,
    the SCOPE, the OBLIGATION (OID) and the satisfaction KIND so an altered /
    reused / stale / mis-scoped / kind-mismatched copy is rejected. Issuing the
    receipt also registers its ``fact_ref`` as a COMMITTED owner fact (the
    ``authoritative_fact_ref`` string path authorises an ACTION only when it
    matches such a committed fact).
    """
    book = _book(state)
    # R11-F02: the registered "committed fact" is a PRIVATE IMMUTABLE SNAPSHOT
    # (a frozen mapping), decoupled from any caller-held object; the returned value
    # is a SEPARATE mutable copy. Mutating the returned object can therefore never
    # alter the authoritative registered fact, and an altered presentation is
    # rejected by the field-for-field match in ``_resolve_owner_receipt``.
    snapshot = types.MappingProxyType({
        "receipt_id": uuid.uuid4().hex,
        "command": command,
        "actor_player_id": actor_player_id,
        "fact_ref": fact_ref or f"owner:{command}",
        "core_revision_before": current_revision(state),
        "scope_id": scope_id,
        "obligation_id": obligation_id,
        "kind": kind,
    })
    book.receipts[snapshot["receipt_id"]] = snapshot
    if snapshot["fact_ref"]:
        book.committed_facts[snapshot["fact_ref"]] = snapshot
    return dict(snapshot)


def complete_actor(state: Any, lease: Any, scope_id: str, command_id: str, *,
                   obligation_id: Optional[Tuple] = None,
                   actor_player_id: Optional[str] = None,
                   substep: str = "vote", phase: str = "population",
                   satisfied_kind: str = KIND_EXPLICIT_FINISH,
                   authoritative_fact_ref: str = "",
                   core_revision_before: Optional[int] = None,
                   owner_receipt: Optional[dict] = None,
                   owner_declared: bool = False) -> dict:
    """Write ONE completion record — from a phase-owner command receipt or an
    owner-declared explicit no-action completion. NEVER from a cached DTO boolean.

    F6/§4.4/R10 receipt-provenance contract (never an arbitrary string):
      * ``command_id`` must be a non-empty owner command identity;
      * ``satisfied_kind`` must be ACTION / EXPLICIT_FINISH / STRUCTURAL_NONE;
      * an **ACTION** record (a real command happened) MUST present a validated
        engine-issued ``owner_receipt`` or a COMMITTED owner
        ``authoritative_fact_ref`` — BOUND to the actor / scope / OID / command and
        whose STORED ``core_revision_before`` equals the current pre-command
        revision; a bare / merely-namespaced string is NOT a receipt
        (``MISSING_OWNER_RECEIPT`` / ``STALE_OWNER_RECEIPT_REVISION``);
      * a no-action record (EXPLICIT_FINISH / STRUCTURAL_NONE) carries no command
        receipt; on a REGISTERED Hot-seat session it must be attributable to the
        owner boundary via an engine-issued no-action credential or the explicit
        ``owner_declared`` marker (``MISSING_OWNER_DECLARATION``); a
        never-registered CLI/legacy state keeps the historical low-level
        semantics — a DIRECT primitive call IS the owner declaration (internal /
        test use; this primitive is NOT a public API);
      * a presented ``lease`` must be the live service-issued lease;
      * a completed PER-ACTOR obligation must be derivable from the owner schedule.
    The default kind is ``EXPLICIT_FINISH``: a low-level caller that declares no
    kind is recording an owner-declared no-action, NOT an owner ACTION.
    """
    book = _book(state)
    if scope_id is None:
        return {"success": False, "reason": "MISSING_SCOPE"}
    if not isinstance(command_id, str) or not command_id.strip():
        return {"success": False, "reason": "MISSING_COMMAND_ID",
                "message": "a completion requires a non-empty owner command id"}
    if satisfied_kind not in (KIND_ACTION, KIND_EXPLICIT_FINISH, KIND_STRUCTURAL_NONE):
        return {"success": False, "reason": "INVALID_SATISFACTION_KIND"}
    if lease is not None and not _lease_is_valid(state, lease):
        return {"success": False, "reason": "INVALID_LEASE"}
    rev_now = current_revision(state)
    # Resolve the obligation identity BEFORE receipt validation so the receipt /
    # committed fact is BOUND to the exact obligation (R10-1 OID binding).
    if obligation_id is None:
        slot = ("player", actor_player_id) if actor_player_id else ("singleton", scope_id)
        obligation_id = book.oid(phase, substep, slot, scope_id)
    # A supplied pre-command revision that does not match the CURRENT pre-command
    # revision is stale for a COMMAND (ACTION); it is checked BEFORE the receipt
    # resolution so a stale command is rejected as STALE_OWNER_RECEIPT_REVISION.
    # (no-action kinds carry no command, so their revision argument is not bound.)
    if satisfied_kind == KIND_ACTION and core_revision_before is not None \
            and int(core_revision_before) != rev_now:
        return {"success": False, "reason": "STALE_OWNER_RECEIPT_REVISION",
                "message": "core_revision_before must match the pre-command "
                           "owner revision"}
    # A credential is PRESENTED when a non-empty one is supplied on EITHER accepted
    # route: the ``owner_receipt`` dict, or a committed ``authoritative_fact_ref``.
    _presented = owner_receipt is not None or (
        isinstance(authoritative_fact_ref, str)
        and authoritative_fact_ref.strip() != "")
    # §4.3/§4.4/R10/R11: a PRESENTED credential must be engine-issued AND exactly
    # bound (command / actor / scope / OID / kind + STORED pre-command revision).
    # The SAME validation runs for the receipt route and the fact-ref route, and for
    # BOTH the ACTION and the no-action kinds — an ACTION fact/receipt can never be
    # relabelled as a no-action on EITHER route (no laundering, F04).
    if _presented and not _validate_owner_receipt(
            state, owner_receipt, authoritative_fact_ref, actor_player_id, scope_id,
            command_id, expected_revision=rev_now, obligation_id=obligation_id,
            satisfied_kind=satisfied_kind):
        return {"success": False,
                "reason": _receipt_rejection_reason(
                    state, owner_receipt, authoritative_fact_ref, rev_now),
                "message": "a presented owner credential must be an engine-issued, "
                           "unconsumed, exactly-bound, in-revision credential"}
    if satisfied_kind == KIND_ACTION:
        # R10-1: an ACTION record (a real command happened) REQUIRES a validated
        # engine-issued command receipt or a COMMITTED owner fact; a bare / merely
        # namespaced string is NOT an owner fact.
        if not _validate_owner_receipt(state, owner_receipt, authoritative_fact_ref,
                                       actor_player_id, scope_id, command_id,
                                       expected_revision=rev_now,
                                       obligation_id=obligation_id,
                                       satisfied_kind=KIND_ACTION):
            return {"success": False,
                    "reason": _receipt_rejection_reason(
                        state, owner_receipt, authoritative_fact_ref, rev_now),
                    "message": "an ACTION completion requires a validated owner "
                               "command receipt/fact (not a bare string)"}
    else:
        # R10-2: no-action (owner-declared completion; no command => no receipt).
        # On a REGISTERED Hot-seat session the record must be attributable to the
        # owner boundary — an owner-origin credential (the engine-issued no-action
        # receipt) or the explicit owner-declared marker. A never-registered
        # CLI/legacy state keeps the historical low-level semantics: a DIRECT
        # primitive call IS the owner declaration (internal/test use — this
        # primitive is NOT a public API). A PRESENTED credential on this route has
        # ALREADY been exactly validated above for the no-action kind, so an ACTION
        # fact/receipt presented here is rejected (no laundering).
        from src.api import session_access
        if session_access.is_hotseat_registered(state) \
                and not (owner_declared or _presented):
            return {"success": False, "reason": "MISSING_OWNER_DECLARATION",
                    "message": "a no-action completion on a registered Hot-seat "
                               "session requires an owner-origin credential or an "
                               "explicit owner-declared marker"}
    # R11-F02: resolve the credential to the ONE registered immutable identity so
    # BOTH routes CONSUME the SAME identity after a successful write.
    _resolved_credential = _resolve_owner_receipt(
        state, owner_receipt, authoritative_fact_ref)
    if isinstance(owner_receipt, dict) and owner_receipt.get("fact_ref"):
        authoritative_fact_ref = owner_receipt["fact_ref"]
    rev_before = int(core_revision_before) if core_revision_before is not None \
        else rev_now
    # F6 receipt-provenance: a completed PER-ACTOR obligation MUST be derivable
    # from the phase owner's authoritative schedule. An invented/arbitrary per-
    # actor ID (and any stringly "receipt" that names no real obligation) is
    # rejected fail-closed. A singleton/role obligation (structural, no actor) is
    # accepted as the phase schedule's role step.
    _slot = obligation_id[5] if len(obligation_id) > 5 else None
    if isinstance(_slot, tuple) and _slot and _slot[0] == "player":
        _cand = {"population": ("campaign", "vote"),
                 "forum": ("retirement", "market")}.get(phase, (None,))
        _derivable = False
        for _st in _cand:
            try:
                _snap = obligations(state, phase, _st)
            except Exception:  # pragma: no cover - defensive
                continue
            if any(o.obligation_id == obligation_id for o in _snap.obligations):
                _derivable = True
                break
        if not _derivable:
            return {"success": False, "reason": "UNKNOWN_OBLIGATION",
                    "message": "completion must name a real owner obligation"}
    dk = book.dk(phase, substep, actor_player_id, rev_before)
    if book.replay_denied(dk):
        return {"success": False, "reason": "DUPLICATE_DISPATCH"}
    if book.satisfied(obligation_id, scope_id, current_revision(state)):
        return {"success": True, "reason": "ALREADY_SATISFIED"}
    rec = _Record(
        command_id=command_id, dispatch_key=dk, obligation_id=obligation_id,
        authoritative_fact_ref=authoritative_fact_ref, satisfied_kind=satisfied_kind,
        entry_revision=(book.scopes.get(phase).entry_revision
                        if book.scopes.get(phase) else rev_before),
        satisfied_at_revision=book.revision_counter + 1)
    book.write(rec)
    # §4.4/F02: an engine-issued receipt is ONCE-ONLY — consume the RESOLVED
    # immutable identity on the committed write, for BOTH the receipt and the
    # fact-ref routes (a fact-ref-only ACTION previously left it unconsumed).
    if _resolved_credential is not None and _resolved_credential.get("receipt_id"):
        book.consumed_receipts.add(_resolved_credential["receipt_id"])
    return {"success": True, "recorded": True,
            "obligation_id": obligation_id, "dispatch_key": dk}


# ---------------------------------------------------------------------------
# continue_after_command — the SOLE automatic continuation (R4 §1 / delta §2.3)
# ---------------------------------------------------------------------------
def _continue_scheduled_phase(state: Any, phase: str, scope: _Scope, lease: Any,
                              ai_executor: Optional[Callable[..., ExecutionOutcome]],
                              max_iterations: Optional[int] = None) -> ContinuationResult:
    """F1/A3-02 bounded continuation over the frozen per-substep schedule.

    Finite outstanding-work invariant with strictly-decreasing progress: each
    iteration re-derives the schedule, consumes >=1 outstanding obligation, and
    re-derives. A HUMAN obligation makes that HUMAN CURRENT via ``select_actor``
    and STOPS; an AI obligation runs once through the phase owner and its
    ``complete_actor`` result is CHECKED; a failure / deliberate no-choice is a
    MASKED safe failure; when no outstanding obligation remains the TRUE readiness
    answer (``snapshot.ready()``) is returned — never a premature READY. Iterating
    past the finite bound is an immediate no-progress safe stop.
    """
    book = _book(state)
    processed: List[str] = []
    _initial = obligations(state, phase)
    if _initial.errors:
        return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                  reason=_initial.errors[0], processed=())
    # finite drain bound = (initial outstanding work) + 1 (R + T, delta §2.3): the
    # strictly-decreasing invariant means a legitimate drain cannot exceed it; a
    # no-progress iteration is an immediate safe stop.
    budget = len(_initial.outstanding()) + 1
    if max_iterations is not None:
        budget = min(budget, int(max_iterations))
    iterations = 0
    while True:
        snapshot = obligations(state, phase)
        if snapshot.errors:
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason=snapshot.errors[0], processed=tuple(processed))
        # G7-W3 restore (C2): on a REGISTERED senate scope an UNSATISFIED proposal
        # obligation MUST belong to a real, validated HUMAN presenter. The RAW
        # obligation is inspected BEFORE ``outstanding()`` filters NONE and before
        # ``ready()`` treats a non-executable row as unnecessary; otherwise a
        # missing / non-HUMAN presenter would be auto-drained into an AI package
        # or laundered into a structural completion. This gate also covers
        # T-RECOVER. It never widens a validator and never returns NEXT_HUMAN.
        if phase == "senate" and _is_registered(state):
            _prop = next((o for o in snapshot.obligations
                          if o.substep == "proposal"), None)
            if _prop is not None and not _prop.satisfied and (
                    _prop.controller != CONTROLLER_HUMAN
                    or controller_of(state, _prop.actor_player_id)
                    != CONTROLLER_HUMAN):
                return ContinuationResult(
                    status=STATUS_FAILURE, masked_failure=True,
                    reason="SENATE_PRESENTER_CONFIRMATION_REQUIRED",
                    outstanding=tuple(snapshot.outstanding()),
                    processed=tuple(processed))
        outstanding = list(snapshot.outstanding())
        if not outstanding:
            if snapshot.ready():
                # item3 (S8 / Errata E1-E2): under a REAL owning possession the
                # senate ready branch returns the UNIQUE terminal (finalize ->
                # private G-only selection) instead of the legacy stop. The gate
                # reads ONLY an already-tracked possession, so every
                # unauthorized/no-possession context (unregistered CLI/legacy or a
                # registered seat with no owning/recovery scope) keeps the frozen
                # direct-API senate-ready contract byte-for-byte (no finalize
                # side effect) — see ``has_owning_possession``.
                if phase == "senate" and has_owning_possession(state):
                    return _terminal_senate_phase(state, scope, lease)
                return ContinuationResult(status=STATUS_PHASE_READY, actor=scope.actor,
                                          processed=tuple(processed))
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="NOT_READY_NO_OUTSTANDING",
                                      processed=tuple(processed))
        iterations += 1
        if iterations > budget:
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="BOUND_EXHAUSTED_NO_PROGRESS",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        target = outstanding[0]
        if target.controller == CONTROLLER_HUMAN:
            # F6: ``select_actor`` is the SOLE cursor writer (no bypass). §4.2:
            # its RESULT is CHECKED — a failed cursor write is a masked safe
            # failure, never a false handoff.
            sel = select_actor(state, scope.scope_id)
            if not sel.get("success"):
                return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                          reason=sel.get("reason", "HUMAN_SELECT_FAILED"),
                                          outstanding=tuple(outstanding),
                                          processed=tuple(processed))
            return ContinuationResult(status=STATUS_NEXT_HUMAN,
                                      actor=target.actor_player_id,
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        rev_before = current_revision(state)
        if book.replay_denied(book.dk(phase, target.substep,
                                      target.actor_player_id, rev_before)):
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="DUPLICATE_DISPATCH",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        # §4.2: the scheduled AI must be made CURRENT by the coordinator BEFORE it
        # acts (R1 §2/§3). The selection result is CHECKED; an unselectable
        # scheduled AI fails closed (never runs the executor off-authority).
        _sel = select_scheduled_actor(state, phase, target.actor_player_id,
                                      scope.scope_id)
        if not _sel.get("success"):
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason=_sel.get("reason", "SCHEDULED_ACTOR_NOT_CURRENT"),
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        outcome = _run_ai_step(ai_executor, state, target)
        if outcome is None or outcome.is_failure:
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason=(outcome.detail if outcome else "NO_EXECUTOR"),
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        if outcome.kind == OUTCOME_NO_CHOICE:
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="UNRESOLVED_MANDATORY_AI_VOTE",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        # item4/FC-D46-06: a Senate OWNER may have ALREADY written the completion
        # (e.g. the veto singleton via ``_record_veto_step_completion``). The
        # outcome then carries a read-only owner_completion marker: verify it
        # against the immutable book record and SKIP the generic issue/complete
        # (never call ``complete_actor`` — incl. its ALREADY_SATISFIED path).
        if outcome.owner_completion is not None:
            if _verify_owner_completion(state, phase, scope, target,
                                        outcome.owner_completion):
                processed.append(target.actor_player_id or "singleton")
                continue
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="OWNER_COMPLETION_UNPROVEN",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        kind = (KIND_STRUCTURAL_NONE if outcome.kind == OUTCOME_STRUCTURAL_EMPTY
                else KIND_ACTION)
        # R10: a real scheduled-AI command is recorded as a receipt-bound ACTION
        # (engine-issued; bound to the schedule OID + pre-command revision); a
        # structural-empty is an owner-declared no-action (explicit marker).
        _rc = None
        if kind == KIND_ACTION:
            _rc = issue_owner_receipt(
                state, outcome.command_id or "ai-step",
                actor_player_id=target.actor_player_id,
                fact_ref=f"ai-receipt:{outcome.command_id or 'ai-step'}",
                scope_id=scope.scope_id, obligation_id=target.obligation_id,
                kind=KIND_ACTION)
        rec = complete_actor(
            state, lease, scope.scope_id,
            command_id=outcome.command_id or "ai-step",
            obligation_id=target.obligation_id,
            actor_player_id=target.actor_player_id,
            phase=phase, substep=target.substep,
            satisfied_kind=kind,
            authoritative_fact_ref=(f"ai-receipt:{outcome.command_id or 'ai-step'}"
                                    if kind == KIND_ACTION else ""),
            core_revision_before=rev_before,
            owner_receipt=_rc,
            owner_declared=(kind == KIND_STRUCTURAL_NONE))
        if not rec.get("success"):
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason=rec.get("reason", "COMPLETION_REJECTED"),
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        processed.append(target.actor_player_id or "singleton")


def select_scheduled_actor(state: Any, phase: str, actor_player_id: str,
                           scope_id: Optional[str] = None) -> dict:
    """Select the SPECIFIC scheduled actor as CURRENT (coordinator-owned cursor
    write). The actor must hold a real outstanding obligation in the phase; this
    never marks a skipped seat as having acted."""
    scope = mint_scope(state, phase)
    if scope_id is not None and scope_id != scope.scope_id:
        return {"success": False, "reason": "STALE_SCOPE", "actor": None}
    snapshot = obligations(state, phase)
    if snapshot.errors:
        return {"success": False, "reason": snapshot.errors[0], "actor": None}
    for o in snapshot.outstanding():
        if o.actor_player_id == actor_player_id:
            if not state.set_current_player(actor_player_id):
                return {"success": False, "reason": "SET_CURRENT_FAILED", "actor": None}
            return {"success": True, "actor": actor_player_id}
    return {"success": False, "reason": "NOT_SCHEDULED", "actor": None}


def run_scheduled_actor(state: Any, phase: str, actor_player_id: str,
                        operation: Callable[..., Any], *args: Any,
                        scope_id: Optional[str] = None, **kwargs: Any) -> Any:
    """F4: run a scheduled actor's phase-owner operation with that actor CURRENT.

    The cursor write AND the restore live HERE (the coordinator is the sole cursor
    writer); the caller never touches the cursor. The previous CURRENT actor is
    restored afterwards so the GUI viewer's session is not left on an AI seat.
    Returns ``None`` when the actor no longer holds an outstanding obligation.
    """
    prev = _entry_actor(state)
    sel = select_scheduled_actor(state, phase, actor_player_id, scope_id)
    if not sel.get("success"):
        return None
    try:
        return operation(*args, **kwargs)
    finally:
        # restore the actor that was CURRENT before this scheduled step, if any and
        # still present; otherwise leave the scheduled actor (caller re-selects).
        if prev and prev != actor_player_id and hasattr(state, "get_player") \
                and state.get_player(prev) is not None:
            state.set_current_player(prev)


def continue_after_command(state: Any, lease: Any = None,
                           receipt: Any = None, *, phase: Optional[str] = None,
                           ai_executor: Optional[Callable[..., ExecutionOutcome]] = None,
                           max_iterations: Optional[int] = None) -> ContinuationResult:
    """Bounded AI drain -> role cursor selection -> automatic finalization.

    Bounded by ``budget = R + T`` with a strictly-decreasing-progress invariant:
    each iteration must consume >=1 obligation or emit one committed transition;
    otherwise it STOPS with a masked safe failure (never spins). Satisfied ``OID``s
    are skipped; a same-revision ``DK`` replay is denied. Missing decider /
    unresolved mandatory AI vote / failed action -> MASKED safe failure, obligation
    stays outstanding, mask retained, no phase advance.
    """
    phase = phase or _current_phase(state)
    scope = mint_scope(state, phase)
    book = _book(state)
    snapshot = obligations(state, phase)
    if snapshot.errors:
        return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                  reason=snapshot.errors[0])

    if phase != "population":
        # F1/A3-02: bounded continuation over the frozen per-substep schedule —
        # NEVER a premature READY after a single AI step.
        return _continue_scheduled_phase(state, phase, scope, lease, ai_executor,
                                         max_iterations=max_iterations)

    # ---- population: campaign then vote, all controllers ------------------
    processed: List[str] = []
    try:
        budget = _population_budget(state, scope.scope_id, max_iterations)
    except ScheduleDerivationError as exc:
        # candidate-retrieval ERROR (incl. a failure raised on a re-derivation) is
        # a masked safe failure; it never crashes and never fabricates progress.
        return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                  reason=str(exc))
    iterations = 0
    while iterations < budget:
        iterations += 1
        try:
            substep = _population_substep(state)
            items = _population_obligations(state, scope.scope_id, substep)
        except ScheduleDerivationError as exc:
            # Retrieval failed on a LATER iteration (after earlier AI/global commits)
            # -> masked safe failure: the post-commit boundary is left intact (no new
            # effect, no rollback of the committed obligation).
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason=str(exc), processed=tuple(processed))
        outstanding = [o for o in items if o.is_executable and not o.satisfied]
        if not outstanding:
            # substep complete; if campaign done and vote outstanding, next loop
            if substep == "campaign":
                continue
            break
        ai_targets = [o for o in outstanding if o.controller == CONTROLLER_AI]
        human_targets = [o for o in outstanding if o.controller == CONTROLLER_HUMAN]
        if not ai_targets:
            # Stop at the next HUMAN; the SOLE cursor writer (``select_actor``)
            # makes that HUMAN CURRENT — the continuation never writes the cursor
            # directly (F6: no ``set_current_player`` bypass).
            actor = human_targets[0].actor_player_id if human_targets else None
            if actor:
                select_actor(state, scope.scope_id)
            return ContinuationResult(status=STATUS_NEXT_HUMAN, actor=actor,
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        target = ai_targets[0]
        rev_before = current_revision(state)
        dk = book.dk("population", substep, target.actor_player_id, rev_before)
        if book.replay_denied(dk):
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="DUPLICATE_DISPATCH",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        outcome = _run_ai_step(ai_executor, state, target)
        if outcome is None or outcome.is_failure:
            return ContinuationResult(
                status=STATUS_FAILURE, masked_failure=True,
                reason=(outcome.detail if outcome else "NO_EXECUTOR"),
                outstanding=tuple(outstanding), processed=tuple(processed))
        if outcome.kind in (OUTCOME_NO_CHOICE,):
            # Deliberate no-choice on a MANDATORY obligation -> unresolved
            # mandatory AI vote: safe failure, mask retained (N10-R).
            return ContinuationResult(
                status=STATUS_FAILURE, masked_failure=True,
                reason="UNRESOLVED_MANDATORY_AI_VOTE",
                outstanding=tuple(outstanding), processed=tuple(processed))
        if outcome.kind == OUTCOME_STRUCTURAL_EMPTY:
            # Owner-validated structural empty removes only this obligation.
            complete_actor(state, lease, scope.scope_id,
                           command_id=outcome.command_id or "ai-empty",
                           obligation_id=target.obligation_id,
                           actor_player_id=target.actor_player_id,
                           phase="population", substep=substep,
                           satisfied_kind=KIND_STRUCTURAL_NONE,
                           core_revision_before=rev_before,
                           owner_declared=True)
            processed.append(target.actor_player_id or "ai")
            continue
        if not outcome.is_accepted:
            return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                      reason="NON_ACCEPTED_OUTCOME",
                                      outstanding=tuple(outstanding),
                                      processed=tuple(processed))
        _rc = issue_owner_receipt(
            state, outcome.command_id or "ai-vote",
            actor_player_id=target.actor_player_id,
            fact_ref=f"ai-receipt:{outcome.command_id or 'ai-vote'}",
            scope_id=scope.scope_id, obligation_id=target.obligation_id,
            kind=KIND_ACTION)
        complete_actor(state, lease, scope.scope_id,
                       command_id=outcome.command_id or "ai-vote",
                       obligation_id=target.obligation_id,
                       actor_player_id=target.actor_player_id,
                       phase="population", substep=substep,
                       satisfied_kind=KIND_ACTION,
                       authoritative_fact_ref=f"ai-receipt:{outcome.command_id or 'ai-vote'}",
                       core_revision_before=rev_before,
                       owner_receipt=_rc)
        processed.append(target.actor_player_id or "ai")

    # Loop ended: ready -> resolve / advance, else a masked safe failure.
    if phase_ready(state, "population", scope.scope_id):
        return ContinuationResult(status=STATUS_RESOLVED, actor=scope.actor,
                                  processed=tuple(processed))
    return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                              reason="BOUND_EXHAUSTED_NO_PROGRESS",
                              processed=tuple(processed),
                              outstanding=tuple(
                                  o for o in _population_obligations(
                                      state, scope.scope_id, _population_substep(state))
                                  if o.is_executable and not o.satisfied))


def _population_budget(state: Any, scope_id: str, max_iterations: Optional[int]) -> int:
    """budget = R + T (finite). R = remaining outstanding executable obligations;
    T = finite explicit transition budget for boundaries crossed in THIS
    continuation (0 or 1)."""
    items = _population_obligations(state, scope_id, "vote")
    r = sum(1 for o in items if o.is_executable and not o.satisfied)
    camp = _population_obligations(state, scope_id, "campaign")
    r += sum(1 for o in camp if o.is_executable and not o.satisfied)
    budget = max(1, r) + 1
    if max_iterations is not None:
        budget = min(budget, int(max_iterations))
    return budget


def _verify_owner_completion(state: Any, phase: str, scope: "_Scope",
                             target: "Obligation",
                             oc: Optional["OwnerCompletion"]) -> bool:
    """item4/FC-D46-06: re-verify a presented owner-completion MARKER against the
    IMMUTABLE book record (the ONE ledger). It authorises NOTHING; a mismatch is a
    masked failure at the caller. Only the singleton ``senate_veto_decision``
    ACTION record is accepted, with the exact scope/OID/actor/revision identity.
    """
    if oc is None or phase != "senate":
        return False
    book = _book(state)
    if oc.scope_id != scope.scope_id:
        return False
    veto_oid = book.oid("senate", "veto", ("singleton", scope.scope_id),
                        scope.scope_id)
    if oc.obligation_id != veto_oid or oc.obligation_id != target.obligation_id:
        return False
    rec = None
    for r in book.records:
        if (r.obligation_id == veto_oid and r.command_id == "senate_veto_decision"
                and r.satisfied_kind == KIND_ACTION):
            rec = r
            break
    if rec is None:
        return False
    if oc.actor_player_id is not None:
        return False
    if oc.pre_revision != (rec.dispatch_key[-1] if rec.dispatch_key else -1):
        return False
    if oc.satisfied_at_revision != rec.satisfied_at_revision:
        return False
    if oc.fact_ref and oc.fact_ref != rec.authoritative_fact_ref:
        return False
    return book.satisfied(veto_oid, scope.scope_id, current_revision(state))


def _run_ai_step(ai_executor: Optional[Callable[..., ExecutionOutcome]],
                 state: Any, target: Obligation) -> Optional[ExecutionOutcome]:
    """Invoke the narrow scheduled-AI capability through the phase owner.

    The executor is the phase-specific drain (population: session_api
    ``_drain_ai_population_turns`` bridged). A missing executor is a masked failure
    (never a silent success).
    """
    if ai_executor is None:
        return ExecutionOutcome(OUTCOME_FAILURE, detail="NO_EXECUTOR")
    try:
        outcome = ai_executor(state, target)
    except Exception as exc:  # decider-retrieval throw at the precommit seam
        return ExecutionOutcome(OUTCOME_FAILURE, detail=f"AI_STEP_EXCEPTION: {exc}")
    if outcome is None:
        return ExecutionOutcome(OUTCOME_FAILURE, detail="AI_STEP_NONE")
    return outcome


# ---------------------------------------------------------------------------
# Terminal / G — item3 / FC-D46-05 (§4.3)
#
# The senate phase's UNIQUE terminal: once this scope's all-required-ready and a
# canonical finalization is committed, the result owner G is selected privately
# (``scope.actor``) and made the real Core current player; only then is the
# terminal envelope returned. This is NOT a generic coordinator duty — it is the
# senate phase owner's terminal, invoked by the coordinator ONLY from the ready
# branch (or the recovery ready branch). A never-authorized context (e.g. a direct
# CLI/legacy call, or a registered seat with no owning dispatch/recovery scope)
# falls back to the legacy ready stop, so no existing assertion changes.
# ---------------------------------------------------------------------------
def _is_registered(state: Any) -> bool:
    """True iff ``state`` is a registered Hot-seat session. A never-registered
    (CLI/legacy) state keeps the historical semantics."""
    try:
        from src.api import session_access as _access
        return bool(_access.is_hotseat_registered(state))
    except Exception:  # pragma: no cover - defensive
        return False


def has_owning_possession(state: Any) -> bool:
    """item3 §3.4 / E1-E2: the FORWARD-continuation owning-possession gate.

    ``True`` iff ``state`` is a registered Hot-seat session AND a live owning
    continuation scope (``current_dispatch_capability``) OR a live recovery scope
    is present. It ONLY re-reads authority facts the service ALREADY tracks — it
    never widens a guard, never derives possession from a viewer / route /
    default, and never mints a scope or a capability.
    """
    if not _is_registered(state):
        return False
    try:
        from src.api import session_access as _access
    except Exception:  # pragma: no cover - defensive
        return False
    try:
        if _access.current_dispatch_capability(state) is not None:
            return True
        return _access._nesting_recovery_scope(state) is not None
    except Exception:  # pragma: no cover - defensive
        return False


def _is_guard_denial(response: Any) -> bool:
    """True iff ``response`` is the ordinary public-guard DENIED envelope (an
    UNAUTHORIZED boundary call) rather than a business refusal. The guard denial
    carries the single ``DENIED`` error code; it is NOT a terminal business
    failure (so the terminal branch must NOT turn it into a masked failure)."""
    if not isinstance(response, dict) or response.get("success") is not False:
        return False
    for err in (response.get("errors") or []):
        if isinstance(err, dict) and err.get("code") == "DENIED":
            return True
    return False


def _select_senate_result_owner(state: Any, scope: "_Scope") -> dict:
    """item3/FC-D46-05 §4.3.2: the PRIVATE G-only result-owner selection.

    Reads G from the existing ``scope.actor`` (the phase-entry Core current
    executable actor); it does NOT accept a public actor parameter, does NOT write
    the ledger, does NOT fabricate an outstanding obligation, and does NOT change
    ``select_scheduled_actor``'s "only-outstanding" condition. It only makes G the
    real Core current player (the SOLE controlled cursor write) and reads back.
    """
    if scope is None:
        return {"success": False, "reason": "NO_SCOPE"}
    if _book(state).scopes.get("senate") is not scope:
        return {"success": False, "reason": "STALE_SCOPE"}
    G = scope.actor
    if not G:
        return {"success": False, "reason": "NO_RESULT_OWNER"}
    ctrl = controller_of(state, G)
    if ctrl not in (CONTROLLER_HUMAN, CONTROLLER_AI):
        return {"success": False, "reason": "RESULT_OWNER_NOT_EXECUTABLE"}
    if not phase_ready(state, "senate", scope.scope_id):
        # D4/D6 I2-R3 (item3 端到端可驱动): a REAL finalization that committed the
        # senate phase result (four facts same version) authoritatively closes
        # every required obligation. The finalize's ``clear_senate_pending`` then
        # resets ``senate_proposal_decision_complete``, which can make the DERIVED
        # ``phase_ready`` predicate read False AFTER the commit (the readiness that
        # was true at the ready-branch entry is the same-version fact). The
        # committed success phase_result is therefore the stronger same-version
        # oracle; with NO committed result the historical guard is unchanged.
        committed = state.get_phase_result("senate")
        if not (isinstance(committed, dict) and committed.get("success")):
            return {"success": False, "reason": "PHASE_NOT_READY"}
    player = state.get_player(G) if hasattr(state, "get_player") else None
    if player is None:
        return {"success": False, "reason": "RESULT_OWNER_MISSING"}
    if not state.set_current_player(G):
        return {"success": False, "reason": "SET_CURRENT_FAILED"}
    if _entry_actor(state) != G:
        return {"success": False, "reason": "READBACK_MISMATCH"}
    return {"success": True, "actor": G, "controller": ctrl}


def _terminal_senate_phase(state: Any, scope: "_Scope",
                           lease: Any = None, processed: Tuple[str, ...] = ()) -> "ContinuationResult":
    """item3/FC-D46-05 §4.3.1 fixed order: (1) the UNIQUE internal finalize, then
    (2) the private result-owner selection, then (3) the frozen terminal envelope.

    An UNAUTHORIZED guard denial at the finalize boundary is NOT a terminal failure
    — it means this context holds no owning dispatch/recovery scope, so the legacy
    ready stop is returned. A real business/finalization failure IS a masked
    terminal failure ``{status:'failure', masked_failure:true, reason:<stage>}``.
    """
    from src.api import senate_api
    try:
        fin = senate_api.finalize_senate_if_ready(state)
    except Exception as exc:  # pragma: no cover - defensive
        return ContinuationResult(
            status=STATUS_FAILURE, masked_failure=True,
            reason=f"TERMINAL_FINALIZE_EXCEPTION:{exc}")
    if not fin.get("success"):
        if _is_guard_denial(fin):
            # no owning continuation/recovery authority in this context -> the
            # historical ready stop (byte-for-byte) instead of a false terminal.
            # I2-R3 observation ②: carry the (empty) ``processed`` tuple explicitly
            # so the fallback envelope shape matches the ready branch verbatim.
            return ContinuationResult(status=STATUS_PHASE_READY, actor=scope.actor,
                                      processed=tuple(processed))
        return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                  reason="TERMINAL_FINALIZE_FAILED")
    data = fin.get("data") or {}
    facts = data.get("completion_facts")
    if not (isinstance(facts, dict) and all(facts.values())):
        return ContinuationResult(status=STATUS_FAILURE, masked_failure=True,
                                  reason="TERMINAL_FACTS_INCOMPLETE")
    sel = _select_senate_result_owner(state, scope)
    if not sel.get("success"):
        return ContinuationResult(
            status=STATUS_FAILURE, masked_failure=True,
            reason=sel.get("reason", "RESULT_OWNER_SELECTION_FAILED"))
    G = sel["actor"]
    ctrl = sel["controller"]
    # §4.3.4: G=AI never enters the Store's ``None -> same-seat`` fallback — the
    # envelope carries the real G + its controller (awaiting only for a HUMAN), and
    # returns the ORIGINAL controlled phase owner without an AI takeover / ACTIVE AI.
    awaiting = G if ctrl == CONTROLLER_HUMAN else None
    # B.4.1: the terminal CLAIMS the typed positional identity. The owner's
    # produced data may still carry the historical all-string form; in that case
    # derive the typed identity from the SAME canonical key (never coerce it).
    fid_claim = data.get("finalization_id")
    typed_claim = (isinstance(fid_claim, (list, tuple)) and len(fid_claim) == 3
                   and type(fid_claim[0]) is str and type(fid_claim[1]) is str
                   and type(fid_claim[2]) is int
                   and not isinstance(fid_claim[2], bool))
    if not typed_claim:
        fid_claim = list(senate_api.senate_finalization_id(state))
    else:
        fid_claim = list(fid_claim)
    terminal = {
        "status": "resolved",
        "phase": "senate",
        "scope_id": scope.scope_id,
        "actor": G,
        "controller": ctrl,
        "current_player_id": G,
        "finalization_id": fid_claim,
        "cursor_restored": True,
        "awaiting_player_id": awaiting,
        # §1.2 O: the exact RESULT-OWNER obligation identity (an identity tuple
        # only — no obligation is fabricated in the ledger for the finalised scope).
        "obligation_id": list(_book(state).oid(
            "senate", "terminal", ("player", G), scope.scope_id)),
    }
    return ContinuationResult(status=STATUS_RESOLVED, actor=G, terminal=terminal)


# ---------------------------------------------------------------------------
# owner checkpoint resume-kind resolver (item3 §5 / Errata E5)
#
# The Store's recovery intent must NOT pick a resume-kind itself and must NOT use
# the I1 cardinality proxy (``determinate_recovery_resume_kind`` only returns a
# value for a singleton permitted set — every admission row is multi-kind, so it
# is permanently ``None``). The coordinator owns the REAL checkpoint: it chooses
# the SINGLE kind from the Core facts + the ``SessionTurnBook``, then
# MEMBERSHIP-validates it against the mandate's permitted closed set.
# ---------------------------------------------------------------------------
RESUME_ENTRY_PENDING = "ENTRY_PENDING"
RESUME_CONTINUATION_PENDING = "CONTINUATION_PENDING"
RESUME_TERMINAL_PENDING = "TERMINAL_PENDING"
RESUME_DELIVERY_PENDING = "DELIVERY_PENDING"


def _derive_recovery_resume_kind(state: Any) -> Optional[str]:
    """The REAL owner checkpoint (read-only Core facts + the SessionTurnBook).

    * senate phase already READY -> the terminal is the unfinished step
      (``TERMINAL_PENDING``); otherwise outstanding work remains
      (``CONTINUATION_PENDING``);
    * any other phase already committed (ready) -> entry into the next phase is
      the unfinished step (``ENTRY_PENDING``); otherwise ``CONTINUATION_PENDING``.
    """
    try:
        phase = _current_phase(state)
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        ready = bool(phase_ready(state, phase))
    except Exception:  # pragma: no cover - defensive
        ready = False
    if phase == "senate":
        return RESUME_TERMINAL_PENDING if ready else RESUME_CONTINUATION_PENDING
    return RESUME_ENTRY_PENDING if ready else RESUME_CONTINUATION_PENDING


def resolve_recovery_resume_kind(state: Any, mandate: Any) -> Optional[str]:
    """item3 §5.2.1: coordinator-owned owner-checkpoint resolver.

    Chooses the SINGLE resume-kind from the real checkpoint facts, then
    MEMBERSHIP-validates it against ``mandate.permitted_resume_kind``. A derived
    kind OUTSIDE the permitted closed set is REFUSED (``None``) with NO side
    effects — never a caller pick, never a cardinality proxy, never a registry
    expansion. Strictly read-only (it never writes a record / cursor / business).
    """
    if mandate is None:
        return None
    permitted = getattr(mandate, "permitted_resume_kind", None) or frozenset()
    kind = _derive_recovery_resume_kind(state)
    if kind is None or kind not in permitted:
        return None
    return kind


# ---------------------------------------------------------------------------
# continuance recovery (grContinuationRecover, Overlay §2.1.R)
# ---------------------------------------------------------------------------
def recover_continuation(state: Any, lease: Any = None,
                         fresh_receipt: Any = None, **kwargs: Any) -> ContinuationResult:
    """Bounded S-C continuation recovery: recompute ``obligations()`` and resume
    ONLY outstanding AI work. Satisfied ``OID``s are skipped and same-revision
    ``DK`` replays are denied => a committed HUMAN command is never resubmitted and
    no committed AI/global settlement is repeated. Mutually exclusive with
    activation retry (S-B) and resolution-entry settlement retry (R4).

    D4/D6 I2-R1 item3 (FC-D46-05 §4.3.1): when the senate phase is READY (no
    outstanding required obligation) the recovery MUST return the UNIQUE terminal
    branch (finalize -> private G-only selection), NOT a bare ``STATUS_PHASE_READY``.
    """
    phase = _current_phase(state)
    if not phase_ready(state, phase):
        # Outstanding work remains -> resume the continuation.
        return continue_after_command(state, lease, fresh_receipt, **kwargs)
    if phase == "senate" and _is_registered(state):
        # D4/D6 I2-R1 item3 (FC-D46-05 §4.3.1): a REGISTERED senate-ready recovery
        # returns the UNIQUE terminal branch, NOT a bare ``STATUS_PHASE_READY``.
        scope = mint_scope(state, "senate")
        return _terminal_senate_phase(state, scope, lease)
    return ContinuationResult(status=STATUS_PHASE_READY, actor=_entry_actor(state))


# ---------------------------------------------------------------------------
# R-5 owner-side ledger barrier (Overlay §1.1 / R1 §4.4)
#
# The phase-owner APIs (forum / mortality / revenue / game / combat advance
# triggers) consult this bounded barrier BEFORE their business mutation. It
# enforces the CURRENT phase scope plus the relevant ledger barrier on a
# REGISTERED Hot-seat session only; a never-registered (CLI/legacy) state is
# exempt and keeps the historical semantics. It NEVER forces a retirement/bid
# duty (R1 §4.4): an owner-recorded explicit legal finish (or structural
# inapplicability) removes the obligation.
# ---------------------------------------------------------------------------
FORUM_SUBSTEPS: Tuple[str, ...] = ("retirement", "market")


def _forum_obligations(state: Any, scope_id: str, substep: str) -> List[Obligation]:
    """Per-controller forum substep obligations (retirement | market).

    Satisfied ONLY by an owner-recorded explicit finish in the ONE session ledger
    (``complete_actor`` with an explicit-finish/structural kind) — never a cached
    DTO boolean. A seat finishes; it does not have to retire or bid.
    """
    book = _book(state)
    out: List[Obligation] = []
    for player in state.get_all_players():
        pid = player.player_id
        controller = controller_of(state, pid)
        if controller == CONTROLLER_NONE:
            continue
        slot = ("player", pid)
        oid = book.oid("forum", substep, slot, scope_id)
        satisfied = book.satisfied(oid, scope_id, current_revision(state))
        out.append(Obligation(
            obligation_id=oid, scope_id=scope_id, phase="forum", substep=substep,
            actor_slot=slot, actor_player_id=pid, officer_id=None,
            controller=controller, required_operation=substep, satisfied=satisfied,
            satisfied_kind=(book.satisfies_kind(oid) if satisfied else None),
            source_fact="forum_ledger_finish"))
    return out


def forum_substep_ready(state: Any, substep: str) -> bool:
    """Exact all-controller readiness for ONE forum substep (retirement|market)."""
    scope = mint_scope(state, "forum")
    return all(o.satisfied for o in _forum_obligations(state, scope.scope_id, substep))


def owner_barrier(state: Any, phase: Optional[str] = None,
                  substep: Optional[str] = None) -> Optional[dict]:
    """Owner-side ledger barrier for a phase-owner API boundary (R-5).

    Returns ``None`` when the operation is ADMITTED, or a structured denial dict
    ``{"code", "reason", "message"}`` when a REGISTERED Hot-seat session is out of
    scope / still has an unmet required ledger obligation. A never-registered
    (CLI/legacy) state is exempt (returns ``None``).

    * forum (with a substep): all-controller readiness of that forum substep
      (retirement before ``open_market``; market before ``resolve_forum``).
    * every other phase: the genuine existing result/execution predicate
      (``phase_ready`` -- ``is_phase_executed`` / recorded phase result).
    """
    from src.api import session_access
    if not session_access.is_hotseat_registered(state):
        return None
    phase = phase or _current_phase(state)
    if _current_phase(state) != phase:
        return {"code": "PHASE_NOT_READY", "reason": "WRONG_PHASE",
                "message": f"Current phase is not {phase}"}
    scope = mint_scope(state, phase)
    if phase == "forum" and substep:
        if forum_substep_ready(state, substep):
            return None
        return {"code": "PHASE_NOT_READY", "reason": "FORUM_SUBSTEP_NOT_READY",
                "message": f"Forum {substep} obligations are outstanding"}
    if phase == "combat":
        # The genuine CLOSED combat readiness predicate (no outstanding actionable
        # wars) is owned by combat_api and checked there; the barrier ADDS NO
        # commander-faction rule (R1 §3 combat clarification) and only pins the
        # current phase scope (verified above).
        return None
    if phase_ready(state, phase, scope.scope_id):
        return None
    return {"code": "PHASE_NOT_READY", "reason": "PHASE_NOT_READY",
            "message": f"{phase} phase is not ready"}
