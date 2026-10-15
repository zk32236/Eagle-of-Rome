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
class ExecutionOutcome:
    """Narrow structured result of a scheduled-AI execution step."""

    kind: str
    detail: str = ""
    command_id: str = ""
    receipts: Tuple[str, ...] = ()

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

    @property
    def ok(self) -> bool:
        return self.status != STATUS_FAILURE


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


def _session_ns(state: Any) -> str:
    return f"session-{id(state)}"


def _book(state: Any) -> SessionTurnBook:
    book = getattr(state, _BOOK_ATTR, None)
    if book is None:
        book = SessionTurnBook(_session_ns(state))
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


def enter_phase(state: Any, transition_receipt: Optional[dict]) -> dict:
    """Consume a successfully COMMITTED phase-advance receipt EXACTLY ONCE.

    Emits an immutable ``PhaseEntered`` record and mints a FRESH scope for the new
    phase (leaving the old phase invalidates old handles/commands, R1 §5). Visual
    navigation is NOT phase entry — only a committed advance receipt entry event
    reaches here.
    """
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
    # Fresh scope minted at entry (new immutable identity).
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
    out.append(Obligation(
        obligation_id=prop_oid, scope_id=scope_id, phase="senate",
        substep="proposal", actor_slot=("singleton", scope_id),
        actor_player_id=prop_role["actor_player_id"],
        officer_id=prop_role["officer_id"],
        controller=prop_role["controller"],
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
        outstanding = list(snapshot.outstanding())
        if not outstanding:
            if snapshot.ready():
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
# continuance recovery (grContinuationRecover, Overlay §2.1.R)
# ---------------------------------------------------------------------------
def recover_continuation(state: Any, lease: Any = None,
                         fresh_receipt: Any = None, **kwargs: Any) -> ContinuationResult:
    """Bounded S-C continuation recovery: recompute ``obligations()`` and resume
    ONLY outstanding AI work. Satisfied ``OID``s are skipped and same-revision
    ``DK`` replays are denied => a committed HUMAN command is never resubmitted and
    no committed AI/global settlement is repeated. Mutually exclusive with
    activation retry (S-B) and resolution-entry settlement retry (R4).
    """
    if not phase_ready(state, _current_phase(state)):
        # Outstanding work remains -> resume the continuation.
        return continue_after_command(state, lease, fresh_receipt, **kwargs)
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
