"""W3 G7-C — AI restore interaction (zero-package confirm / skip vote+veto / manual combat).

RED-first carrier for AC-W3-03 (NEW predicate), AC-W3-12 (AMEND_COVERAGE) and
AC-W3-18 (AMEND_CAPABILITY_COVERAGE) per TA-W3-04.

Real production seam only: real registered Hot-seat entry (``doAdvancePopulation``)
-> real continuation/delivery -> real SenateStage footer equivalent
(``doSubmitSenateProposals``) -> D13 masked owning flow -> ``auto_submit_proposals``
-> ``propose_many`` -> owner package/completion -> real projection/frame.
Faults (if any) are injected only at declared data boundaries.

NO existing test byte is modified; this file is new (TA-W3-04 §2).
"""
import contextlib
import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
import PySide6.QtQuick  # noqa: F401,E402  (Window -> QQuickWindow mapping)

from src.api import senate_api, session_api, session_turn_service  # noqa: E402
from src.core.systems.political_system import PoliticalSystem  # noqa: E402
from src.tests.test_gui.test_w3_delivery_authority import (  # noqa: E402
    VIEWER,
    _entry_delivery,
    _entry_state,
    _store,
)
from src.ui.gui.session_store import (  # noqa: E402
    FAIL_AFTER_COMMIT,
    RECOVER_ROUTE_ACTIVATION,
    RECOVER_ROUTE_CONTINUATION,
)

CONSUL_OWNER = "player2"
SECOND_AI_OWNER = "player3"   # 1H2AI: the second AI seat (equites)


def _counting_ai_producer(sink):
    """Real producer, counted; the registration state itself is untouched."""
    real = senate_api.auto_submit_proposals

    def _call(*args, **kwargs):
        sink.append(1)
        return real(*args, **kwargs)

    # The trusted adapter/guard routes on ``api_func.__name__``; the wrapper must
    # keep the REAL command identity (a renamed wrapper would be denied).
    _call.__name__ = real.__name__
    _call.__doc__ = real.__doc__
    return _call


def _retry_spy(store, sink):
    """Delegating retry spy (a bare None return would break the masked machine)."""
    real = store.retryHandoff

    def _call(*args, **kwargs):
        sink.append(1)
        return real(*args, **kwargs)

    return _call


@contextlib.contextmanager
def _ai_makes_no_proposals():
    """The AI's OWN deciders decide "no proposal" (a real empty decision).

    Only the EXISTING decider input is fixed (no test-only product switch): the
    land deciders decline and no pending budget contract exists, so the published
    package is genuinely empty.
    """
    with patch.object(senate_api.AutoLandProposalDecider, "decide_proposal",
                      return_value=None):
        yield


def _click(store, payload=None):
    """Run the real footer Slot; return (seat feedback, owner command feedback)."""
    result = store.doSubmitSenateProposals([] if payload is None else payload)
    return result, dict(store._committed_receipt or {})


def _proposal_obligation(state):
    snap = session_turn_service.obligations(state, "senate")
    assert not snap.errors, snap.errors
    return next(o for o in snap.obligations if o.substep == "proposal")


def _latched_proposal_owner(state):
    book = session_turn_service._book(state)
    scope = book.scopes.get("senate")
    assert scope is not None
    return book.role_selections.get((scope.scope_id, "proposal")) or {}


def _entered_store(*, budget=True, consul="ai", third="ai"):
    """Registered session whose real entry has stopped at the presenter gate.

    R2: the restore fixture is a REAL **1H2AI** session (viewer + AI consul +
    a second AI seat). ``third=None`` only ever built 1H1AI, so the design's
    "registered 1H2AI" scenario was never actually under test.
    """
    state = _entry_state(consul_controller=consul, third=third, budget=budget)
    if third is not None:
        second = state.get_player(SECOND_AI_OWNER)
        assert second is not None, [p.player_id for p in state.get_all_players()]
        assert second.player_type.name == "AI", second.player_type
    sink = []
    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink)):
        store, witness = _store(state)
        feedback, receipt, delivery = _entry_delivery(store)
    return state, store, witness, feedback, delivery, sink


def _dispatch_surface(store):
    """Spy the WHOLE dispatch surface of the ONE call under test (R1).

    The previous scope ended BEFORE the refused call, so a refusal that leaked
    into the AI routing could never be seen. This context manager stays armed
    through the call itself and covers every channel a leak could take:

    * ``senate_api.auto_submit_proposals`` — the AI producer itself;
    * ``store._adapter.call`` — the trusted AI route (counted when the target is
      the producer, i.e. the adapter was asked to run the AI command);
    * ``store._adapter.submit_senate_proposals`` — the HUMAN submit route.

    Returns ``(box, *patchers)``; use every patcher in one ``with``.
    """
    box = {"producer": [], "adapter_ai": [], "human_submit": []}
    real_producer = senate_api.auto_submit_proposals
    real_call = store._adapter.call
    real_human = store._adapter.submit_senate_proposals

    def _producer(*args, **kwargs):
        box["producer"].append(1)
        return real_producer(*args, **kwargs)

    # The trusted adapter/guard routes on ``api_func.__name__``; keep the REAL
    # command identity so the wrapper is not denied by a renamed callable.
    _producer.__name__ = real_producer.__name__
    _producer.__doc__ = real_producer.__doc__

    def _call(api_func, *args, **kwargs):
        if getattr(api_func, "__name__", "") == "auto_submit_proposals":
            box["adapter_ai"].append(1)
        return real_call(api_func, *args, **kwargs)

    def _human(*args, **kwargs):
        box["human_submit"].append(1)
        return real_human(*args, **kwargs)

    return (box,
            patch.object(senate_api, "auto_submit_proposals", new=_producer),
            patch.object(store._adapter, "call", side_effect=_call),
            patch.object(store._adapter, "submit_senate_proposals",
                         side_effect=_human))


def _fault_counters(store):
    """Count the masked-machine faults of ONE chain (R2).

    ``after_commit`` / ``recovery`` are read from the SAME ``_fail_masked``
    call (kind + route); ``retry`` counts the real ``retryHandoff`` entry.
    A delegating wrapper is used everywhere — a bare ``None`` return would break
    the masked machine instead of observing it.
    """
    box = {"failures": [], "after_commit": 0, "retry": 0, "recovery": 0}
    real_fail = store._fail_masked
    real_retry = store.retryHandoff

    def _fail(kind, txn_id="", route=RECOVER_ROUTE_ACTIVATION):
        box["failures"].append((kind, route))
        if kind == FAIL_AFTER_COMMIT:
            box["after_commit"] += 1
        if route == RECOVER_ROUTE_CONTINUATION:
            box["recovery"] += 1
        return real_fail(kind, txn_id, route)

    def _retry(*args, **kwargs):
        box["retry"] += 1
        return real_retry(*args, **kwargs)

    return (box,
            patch.object(store, "_fail_masked", side_effect=_fail),
            patch.object(store, "retryHandoff", side_effect=_retry))


@contextlib.contextmanager
def _chain_counters(state, instant=None):
    """Count the ONE publication / receipt / continuation of the chain (R3).

    ``instant`` (a list, optional) receives the publication-instant snapshot:
    the real ``PackageRecord`` and ``decision_complete`` flag taken immediately
    after the real ``submit_proposal_package`` returns success and BEFORE the
    finalizer clears the in-flight scope state.
    """
    box = {"publications": 0, "receipts": 0, "continuations": 0, "instant": []}
    real_submit = PoliticalSystem.submit_proposal_package
    real_receipt = state.record_senate_finalization_receipt
    real_cont = session_turn_service.continue_after_command

    def _submit(system, actor, request, ctx):
        out = real_submit(system, actor, request, ctx)
        if isinstance(out, dict) and out.get("success"):
            box["publications"] += 1
            snap = {
                "senate_session_id": (request or {}).get("senate_session_id"),
                "decision_complete": state.senate_proposal_decision_complete,
                "proposals": list(state.get_senate_proposals()),
            }
            sid = snap["senate_session_id"]
            snap["package_id"] = state.get_senate_package_id_for_session(sid)
            snap["record"] = state.get_senate_package_record(snap["package_id"])
            snap["receipt"] = state.get_senate_finalization_receipt(sid)
            box["instant"].append(snap)
            if instant is not None:
                instant.append(snap)
        return out

    def _receipt(receipt):
        box["receipts"] += 1
        return real_receipt(receipt)

    def _cont(*args, **kwargs):
        box["continuations"] += 1
        return real_cont(*args, **kwargs)

    with patch.object(PoliticalSystem, "submit_proposal_package", new=_submit), \
            patch.object(state, "record_senate_finalization_receipt",
                         side_effect=_receipt), \
            patch.object(session_turn_service, "continue_after_command",
                         side_effect=_cont):
        yield box


def _assert_no_faults(counts, label):
    assert counts["failures"] == [], (label, counts["failures"])
    assert counts["after_commit"] == 0, (label, counts["failures"])
    assert counts["retry"] == 0, (label, counts["retry"])
    assert counts["recovery"] == 0, (label, counts["failures"])


# ===========================================================================
# AC-W3-03 (NEW) — the entry stops at the real presenter, zero generation
# ===========================================================================
def test_ai_entry_stops_at_real_presenter_before_generation():
    state, store, witness, feedback, delivery, sink = _entered_store()

    assert feedback["success"] is True, feedback
    assert sink == [], "the entry continuation must never generate an AI proposal"
    assert state.get_senate_proposals() == []
    assert state.senate_proposal_decision_complete is False

    prop = _proposal_obligation(state)
    assert prop.satisfied is False
    # The obligation actor is the REAL validated HUMAN presenter (scope.actor G).
    assert prop.actor_player_id == VIEWER
    assert prop.controller == session_turn_service.CONTROLLER_HUMAN
    assert prop.officer_id == 8, "the officer identity must stay the real consul"
    # The latched DECISION owner stays the actual AI consul (never rewritten).
    latched = _latched_proposal_owner(state)
    assert latched["actor_player_id"] == CONSUL_OWNER
    assert latched["controller"] == session_turn_service.CONTROLLER_AI

    # The delivery hands the presenter confirmation to G, not to the AI.
    assert delivery and delivery.get("next"), delivery
    assert delivery["outcome"] == "CONTINUE"
    assert delivery["next"]["actor_player_id"] == VIEWER
    assert delivery["next"]["controller"] == "HUMAN"
    verdict = session_turn_service.validate_delivery_result(
        state, delivery, viewer_id=VIEWER)
    assert verdict["ok"] is True, verdict
    assert state.get_current_player().player_id == VIEWER
    # AC-20: the AI owner never sits a HUMAN pending seat.
    assert witness.pendings == []

    view = store._senate_view
    assert view.get("current_step") == "proposal", view.get("current_step")
    # AC-18 (NEW): capability plane splits presenter from decision owner.
    assert view["registered_proposal_owner_player_id"] == CONSUL_OWNER
    assert view["registered_proposal_controller"] == "AI"
    assert view["registered_can_create_proposal"] is False
    assert view["registered_can_select_proposal"] is False
    assert view["registered_can_finish_empty"] is False
    assert view["registered_can_trigger_ai_proposer"] is True
    assert view["can_create_proposal"] is False
    assert view["can_finish_empty"] is False
    assert view["can_trigger_ai_proposer"] is True


# ===========================================================================
# AC-W3-03 + AC-W3-12 — a real zero package finalizes, combat stays manual
# ===========================================================================
def test_ai_zero_package_confirm_finalizes_then_manual_combat():
    state, store, witness, feedback, delivery, sink = _entered_store(budget=False)
    assert feedback["success"] is True, feedback
    assert state.get_senate_proposals() == []

    advance_calls = []
    real_advance = senate_api.advance_senate_phase

    def _advance(*args, **kwargs):
        advance_calls.append(1)
        return real_advance(*args, **kwargs)

    with patch.object(senate_api, "advance_senate_phase", side_effect=_advance):
        # ---- the real footer click: ONE independent AI decision -------------
        with _ai_makes_no_proposals(), \
                patch.object(senate_api, "auto_submit_proposals",
                             new=_counting_ai_producer(sink)):
            click, owner = _click(store)
        assert owner.get("success") is True, (click, owner,
                                            store.senateFinalizationWarning)
        assert sink == [1], "the click must trigger exactly one AI producer run"
        assert state.get_senate_proposals() == []
        # AC-03: the empty package is a REAL owner decision: the continuation
        # produces the canonical terminal (never a click-claimed completion).
        created = (owner.get("data") or {}).get("created")
        assert created == []
        terminal = owner.get("data") or {}
        assert terminal.get("status") == "resolved", (owner, terminal)
        assert terminal.get("finalization_id"), terminal
        canonical = senate_api.canonical_finalization(state)
        assert canonical["status"] == "VALID", canonical
        assert all(canonical["facts"].values()), canonical["facts"]

        readiness = session_turn_service.senate_readiness(state)
        assert readiness["required"] == 0, readiness
        assert readiness["veto_required"] is False

        # AC-12 extension: no automatic combat; only the player's key advances.
        assert advance_calls == [], "the terminal must not auto-advance combat"
        assert store.canAdvanceSenate is True
        assert state.is_phase_executed("combat") is False

        advanced = store.doAdvanceSenate()
        assert advance_calls == [1], "exactly one real Senate->Combat entry call"
        if not advanced.get("success"):
            # This fixture has no Army/Navy universe: the real boundary transaction
            # fail-closes atomically (committed=False) instead of forging a phase.
            assert (advanced.get("data") or {}).get("committed") is False, advanced
            assert state.is_phase_executed("combat") is False

    # N1: a second click (direct Slot) must not re-dispatch or re-publish.
    # R1: the spy is armed for the SECOND (refused) call itself — the previous
    # scope had already ended, so a leak through it was invisible.
    book = session_turn_service._book(state)
    records_before = len(book.records)
    packages_before = dict(state.get_senate_package_registry()["packages"])
    sid = state.get_senate_session()
    receipt_before = state.get_senate_finalization_receipt(sid)
    box, p_producer, p_call, p_human = _dispatch_surface(store)
    with p_producer, p_call, p_human:
        again = store.doSubmitSenateProposals([])
    assert again.get("success") is False, again
    assert sink == [1]
    assert box["producer"] == [], box["producer"]
    assert box["adapter_ai"] == [], box["adapter_ai"]
    assert box["human_submit"] == [], box["human_submit"]
    assert len(session_turn_service._book(state).records) == records_before
    assert dict(state.get_senate_package_registry()["packages"]) == packages_before
    assert state.get_senate_finalization_receipt(sid) == receipt_before
    assert witness.pendings == []


# ===========================================================================
# AC-W3-03 (NEW) — a non-empty AI package keeps its independent decision
# ===========================================================================
def test_ai_nonempty_package_keeps_independent_decision_and_ballot_chain():
    state, store, witness, feedback, delivery, sink = _entered_store(budget=True)
    assert feedback["success"] is True, feedback
    assert state.get_senate_proposals() == []

    human_submit = []
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=lambda *a, **k: human_submit.append(a)), \
            patch.object(senate_api, "auto_submit_proposals",
                         new=_counting_ai_producer(sink)):
        # N8: the player supplies a competing payload; the AI ignores it.
        click, owner = _click(store, [
            {"type": "land", "params": {"act_type": "sale", "amount_C": 1}},
        ])

    assert owner.get("success") is True, (click, owner)
    assert sink == [1]
    assert human_submit == [], "a presenter click must never run the HUMAN submit"
    proposals = state.get_senate_proposals()
    assert proposals, "the AI's own (non-empty) package must really be published"
    # The player's supplied payload left NO trace: a land act of 1 C is never the
    # AI's independent amount here (its own land decision differs).
    assert not any(p.get("type") == "land" and p.get("amount_C") == 1
                   for p in proposals), proposals
    created = (owner.get("data") or {}).get("created") or []
    assert len(created) == len(proposals)
    # The original ballot/veto chain (never a forged empty decision): publishing a
    # package closes the SELECTION, and the real ballots stay required.
    assert state.senate_proposal_decision_complete is True
    readiness = session_turn_service.senate_readiness(state)
    assert readiness["required"] > 0
    assert witness.pendings == []


# ===========================================================================
# AC-W3-12 (AMEND_COVERAGE) — normal chains: zero failures / recovery
# ===========================================================================
def test_normal_restore_chains_have_zero_failures_or_recovery():
    # ---- chain 1: 1H + 2AI, AI presenter, zero package ----------------------
    # ---- chain 1: 1H2AI (real second AI seat), AI presenter, zero package ---
    state = _entry_state(consul_controller="ai", third="ai", budget=False)
    assert [p.player_id for p in state.get_all_players()] == [
        VIEWER, CONSUL_OWNER, SECOND_AI_OWNER]
    assert state.get_player(SECOND_AI_OWNER).player_type.name == "AI"
    sink = []
    instant = []
    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink)):
        store, witness = _store(state)
        counts, p_fail, p_retry = _fault_counters(store)
        with p_fail, p_retry:
            feedback, _, _ = _entry_delivery(store)
            assert feedback["success"] is True, feedback
            # The entry does NOT cross the presenter gate.
            assert sink == []
            assert state.get_senate_proposals() == []
            assert state.senate_proposal_decision_complete is False
            with _ai_makes_no_proposals(), \
                    patch.object(senate_api, "auto_submit_proposals",
                                 new=_counting_ai_producer(sink)), \
                    _chain_counters(state, instant) as chain:
                click, owner = _click(store)
            assert owner.get("success") is True, (click, owner)
            assert senate_api.canonical_finalization(state)["status"] == "VALID", (
                owner, store.senateFinalizationWarning)

    _assert_no_faults(counts, "1H2AI/empty")
    assert chain["publications"] == 1, chain["publications"]
    assert chain["continuations"] == 1, chain["continuations"]
    assert len(instant) == 1, instant

    # ---- chain 2: 3H, the real HUMAN consul owner ---------------------------
    state3 = _entry_state(consul_controller="human", third="human")
    assert [p.player_id for p in state3.get_all_players()] == [
        VIEWER, CONSUL_OWNER, SECOND_AI_OWNER]
    assert all(p.player_type.name == "HUMAN" for p in state3.get_all_players())
    sink3 = []
    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink3)):
        store3, _ = _store(state3)
        counts3, p_fail3, p_retry3 = _fault_counters(store3)
        with p_fail3, p_retry3:
            feedback3, _, delivery3 = _entry_delivery(store3)

    assert feedback3["success"] is True, feedback3
    assert sink3 == [], "a HUMAN owner must never trigger the AI producer"
    # AC04: the HUMAN owner H (not G) receives the proposal obligation.
    assert delivery3["next"]["actor_player_id"] == CONSUL_OWNER
    assert delivery3["next"]["controller"] == "HUMAN"
    prop3 = _proposal_obligation(state3)
    assert prop3.actor_player_id == CONSUL_OWNER
    assert prop3.controller == session_turn_service.CONTROLLER_HUMAN
    assert state3.get_senate_proposals() == []
    # R2: the 3H chain carries its OWN counts in this run (no inherited Gate
    # conclusion): after_commit=0 / failure=0 / retry=0 / recovery=0.
    _assert_no_faults(counts3, "3H/entry")


# ===========================================================================
# AC-W3-18 (AMEND_CAPABILITY_COVERAGE) — presenter never gains decision rights
# ===========================================================================
def test_presenter_capability_never_grants_human_ai_decision_rights():
    state, store, witness, feedback, delivery, sink = _entered_store()
    assert feedback["success"] is True, feedback
    view = store._senate_view

    # Store properties are pure pass-through of the viewer-bound DTO.
    assert store.canCreateSenateProposal is False
    assert store.canSelectSenateProposal is False
    assert store.senateCanFinishEmpty is False
    assert store.canTriggerAIProposer is True
    assert store.senateAiProposerBlocked is False
    for key in ("can_create_proposal", "can_select_proposal",
                "can_finish_proposal_selection", "can_finish_empty"):
        assert view[key] is False, (key, view.get(key))
    # The button's original enabled inputs are unchanged in shape.
    assert view.get("current_step") == "proposal"
    assert view.get("senate_no_host") is False

    human_submit = []
    with patch.object(store._adapter, "submit_senate_proposals",
                      side_effect=lambda *a, **k: human_submit.append(a)):
        click, owner = _click(store, [{"type": "budget", "params": {}}])
    assert owner.get("success") is True, (click, owner)
    assert human_submit == []
    # The actual decision owner metadata is still the AI.
    assert store._senate_view["registered_proposal_owner_player_id"] == CONSUL_OWNER
    assert store._senate_view["registered_proposal_controller"] == "AI"


# ===========================================================================
# AC-W3-18 (NEW negative) — invalid/absent AI capability: zero dispatch
# ===========================================================================
def test_invalid_ai_capability_is_rejected_before_dispatch():
    state, store, witness, feedback, delivery, sink = _entered_store()
    assert feedback["success"] is True, feedback
    assert sink == []

    def _view_without_trigger():
        view = dict(store._senate_view)
        view.pop("can_trigger_ai_proposer", None)
        view["registered_can_trigger_ai_proposer"] = False
        return view

    pristine = store._senate_view
    store._senate_view = _view_without_trigger()
    # R1: each refusal is observed by a spy armed for THAT call. A refused call
    # is exactly where a hidden dispatch would live.
    box, p_producer, p_call, p_human = _dispatch_surface(store)
    with p_producer, p_call, p_human:
        refused = store.doSubmitSenateProposals([])
    assert refused.get("success") is False, refused
    assert box["producer"] == [], "an invalid capability must never dispatch"
    assert box["adapter_ai"] == [], box["adapter_ai"]
    assert box["human_submit"] == [], box["human_submit"]
    assert sink == []
    assert state.get_senate_proposals() == []
    assert state.senate_proposal_decision_complete is False

    # A conflicting double authorisation is refused the same way (fail-closed).
    conflicting = dict(pristine)
    conflicting["can_trigger_ai_proposer"] = True
    conflicting["can_create_proposal"] = True
    store._senate_view = conflicting
    box2, q_producer, q_call, q_human = _dispatch_surface(store)
    with q_producer, q_call, q_human:
        refused2 = store.doSubmitSenateProposals([])
    assert refused2.get("success") is False, refused2
    assert box2["producer"] == [], box2["producer"]
    assert box2["adapter_ai"] == [], box2["adapter_ai"]
    assert box2["human_submit"] == [], box2["human_submit"]
    assert state.get_senate_proposals() == []

    # A wrong-viewer projection is refused before any dispatch.
    other = dict(pristine)
    other["viewer_player_id"] = SECOND_AI_OWNER
    store._senate_view = other
    box3, r_producer, r_call, r_human = _dispatch_surface(store)
    with r_producer, r_call, r_human:
        refused3 = store.doSubmitSenateProposals([])
    assert refused3.get("success") is False, refused3
    assert box3["producer"] == [], box3["producer"]
    assert box3["adapter_ai"] == [], box3["adapter_ai"]
    assert box3["human_submit"] == [], box3["human_submit"]


# ===========================================================================
# TA-W3-05 §2 (a) — FULL non-empty chain: publish -> ballots -> veto ->
# canonical terminal -> the player's OWN key enters combat exactly once
# ===========================================================================
def test_ai_nonempty_chain_reaches_terminal_and_combat():
    # R2: a REAL 1H2AI session (viewer + AI consul + second AI seat).
    state = _entry_state(consul_controller="ai", third="ai", budget=True)
    assert [p.player_id for p in state.get_all_players()] == [
        VIEWER, CONSUL_OWNER, SECOND_AI_OWNER]
    sink = []
    store, witness = _store(state)

    # TA-W3-05 §2(a) positive control: a REAL War/Military universe so the
    # Senate->Combat boundary can actually COMMIT (the shared entry fixture is
    # deliberately built without one; nothing here is faked - the production
    # systems are the real ones).
    from src.core.systems.military_system import MilitarySystem
    from src.core.systems.war_system import WarSystem
    if state.get_war_system() is None:
        state._war_system = WarSystem(state)
    if getattr(state, "_military_system", None) is None:
        state._military_system = MilitarySystem(state)

    counts, p_fail, p_retry = _fault_counters(store)
    advance_calls = []
    real_advance = senate_api.advance_senate_phase

    def _advance(*args, **kwargs):
        advance_calls.append(1)
        return real_advance(*args, **kwargs)

    with p_fail, p_retry, \
            patch.object(senate_api, "auto_submit_proposals",
                         new=_counting_ai_producer(sink)), \
            _chain_counters(state) as chain:
        feedback, _, _ = _entry_delivery(store)
        assert feedback["success"] is True, feedback
        assert sink == [], "the entry still prepares the presentation only"

        # ---- the presenter click: ONE real AI decision, non-empty package ---
        click, owner = _click(store)
        assert owner.get("success") is True, (click, owner,
                                             store.senateFinalizationWarning)
        assert sink == [1], "the click must run the AI producer exactly once"
        proposals = state.get_senate_proposals()
        assert proposals, "the AI's own non-empty package must really be published"
        assert state.senate_proposal_decision_complete is True
        assert witness.pendings == [], "the AI owner never sits a HUMAN seat"

        # ---- ballots: the REAL vote Slot (owner package + AI continuation) --
        ids = [int(p["id"]) for p in proposals]
        vote_fb = store.doSubmitSenateVotes(ids)
        assert vote_fb.get("success") is True, (vote_fb, store._senate_view)
        readiness = session_turn_service.senate_readiness(state)
        assert readiness["covered"] == readiness["required"], readiness
        assert readiness["all_ballots_ready"] is True, readiness

        # ---- veto: the REAL tribune Slot (explicit "no veto" decision) ------
        if store._senate_view.get("current_step") == "tribune_veto":
            veto_fb = store.doSubmitSenateVetoes([])
            assert veto_fb.get("success") is True, (veto_fb, store._senate_view)

        store._refresh_senate_view()
        canonical = senate_api.canonical_finalization(state)
        assert canonical["status"] == "VALID", (canonical,
                                                store.senateFinalizationWarning)
        assert all(canonical["facts"].values()), canonical["facts"]
        assert store._senate_view.get("current_step") in (
            "results", "settlement_pending"), store._senate_view.get("current_step")

        # ---- nothing auto-advanced: the terminal waits for the player ------
        assert store.canAdvanceSenate is True, store._senate_view
        assert state.is_phase_executed("combat") is False

        with patch.object(senate_api, "advance_senate_phase",
                          side_effect=_advance):
            assert advance_calls == [], "a canonical terminal must not auto-advance"
            advanced = store.doAdvanceSenate()

        assert advance_calls == [1], "the player's key advances Senate->Combat once"
        assert advanced.get("success") is True, (advanced.get("message"),
                                                  advanced.get("data"))
        # The boundary commits exactly once: Senate is executed and the shell is
        # now IN the combat phase (combat itself is not executed yet - that is
        # the player's next manual step).
        assert state.is_phase_executed("senate") is True
        assert state.is_phase_executed("combat") is False
        assert store.selectedPhaseId == "combat", store.selectedPhaseId

        # a second key press is guard-denied and never re-executes the boundary
        with patch.object(senate_api, "advance_senate_phase",
                          side_effect=_advance):
            again = store.doAdvanceSenate()
        assert again.get("success") is False, again
        assert advance_calls == [1], advance_calls

    # R2: the non-empty full chain reports its OWN counts.
    _assert_no_faults(counts, "1H2AI/non-empty")
    assert chain["publications"] == 1, chain["publications"]


# ===========================================================================
# TA-W3-05 §2 (b) — combat entry is MANUAL: zero advance before the key,
# exactly one after it (never an automatic phase jump)
# ===========================================================================
def test_manual_combat_entry_requires_player_action():
    state, store, witness, feedback, delivery, sink = _entered_store(budget=False)
    assert feedback["success"] is True, feedback

    advance_calls = []
    real_advance = senate_api.advance_senate_phase

    def _advance(*args, **kwargs):
        advance_calls.append(1)
        return real_advance(*args, **kwargs)

    with patch.object(senate_api, "advance_senate_phase", side_effect=_advance):
        # the real zero-package confirm (a REAL empty AI decision)
        with _ai_makes_no_proposals(), \
                patch.object(senate_api, "auto_submit_proposals",
                             new=_counting_ai_producer(sink)):
            click, owner = _click(store)
        assert owner.get("success") is True, (click, owner,
                                             store.senateFinalizationWarning)
        assert senate_api.canonical_finalization(state)["status"] == "VALID", (
            owner, store.senateFinalizationWarning)
        store._refresh_senate_view()
        assert store.canAdvanceSenate is True, store._senate_view

        # BEFORE the key: zero combat-entry calls, combat not executed, and the
        # senate really sits at its terminal step (no automatic jump).
        assert advance_calls == [], "the terminal must never auto-advance"
        assert state.is_phase_executed("combat") is False
        assert store._senate_view.get("current_step") in (
            "results", "settlement_pending"), store._senate_view.get("current_step")

        # AFTER the key: exactly ONE real Senate->Combat entry call.
        advanced = store.doAdvanceSenate()
        assert advance_calls == [1], "exactly one real Senate->Combat entry call"
        if advanced.get("success"):
            assert state.is_phase_executed("senate") is True, advanced
            assert store.selectedPhaseId == "combat", store.selectedPhaseId
        else:
            # This fixture has no Army/Navy universe: the real boundary
            # transaction fail-closes atomically instead of forging a phase.
            assert (advanced.get("data") or {}).get("committed") is False, advanced
            assert state.is_phase_executed("combat") is False

        # a repeat key press never re-executes the boundary: it is refused and
        # the committed state stays exactly as the ONE key press left it.
        combat_after_first = state.is_phase_executed("combat")
        senate_after_first = state.is_phase_executed("senate")
        again = store.doAdvanceSenate()
        assert again.get("success") is False, again
        assert state.is_phase_executed("combat") is combat_after_first
        assert state.is_phase_executed("senate") is senate_after_first


# ===========================================================================
# TA-W3-05 §2 (c) — C4 negative control: a NON-proposal step is never a
# trigger surface (zero dispatch / zero completion / zero receipt)
# ===========================================================================
def test_non_proposal_step_trigger_true_zero_dispatch():
    """R1 — C4 with a REAL stimulus (design 05 §2 N6 "完成 step" facet).

    STATUS (2026-10-23, REWORK R1): **FAILING ON PURPOSE — STOP finding**.
    With a valid, unlocked, viewer-bound projection that sits on a NON-proposal
    step AND affirmatively advertises ``can_trigger_ai_proposer``, the Store
    dispatches the AI producer (``adapter.call`` + ``auto_submit_proposals``),
    and only the CORE then refuses ("本会期选择已经成功完成"). No package / receipt /
    record is written, so this is a DISPATCH leak, not a publish leak.

    The Store routes on the two DTO capability bits alone and never cross-checks
    the step, so the only thing that keeps production safe is the DTO producer
    always emitting ``can_trigger_ai_proposer=False`` off-proposal (fail-open at
    the Store, fail-closed only in Core). Per the rework brief this is reported
    to PM — the product is NOT patched from a test.
    """
    state, store, witness, feedback, delivery, sink = _entered_store(budget=True)
    assert feedback["success"] is True, feedback

    # One real click publishes the AI's own package and closes SELECTION: the
    # senate has left the proposal step on the REAL projection.
    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink)):
        click, owner = _click(store)
    assert owner.get("success") is True, (click, owner)
    assert sink == [1]
    assert state.get_senate_proposals(), "a real (non-empty) package is published"

    store._refresh_senate_view()
    view = store._senate_view
    assert view.get("current_step") != "proposal", view.get("current_step")
    # The REAL projection is off-proposal and (correctly) advertises no trigger.
    assert view.get("can_create_proposal") is False, view
    assert view.get("can_trigger_ai_proposer") is False, view
    assert view.get("registered_can_trigger_ai_proposer") is False, view

    # R1 — a NEGATIVE control only proves something when the stimulus is real.
    # Off-proposal must be refused because the STEP is wrong, not because the
    # capability bit happened to be dead. So take the real viewer-bound DTO and
    # declare the trigger AFFIRMATIVELY (only the step stays off-proposal):
    # unlocked (no D13 DENIED lock), non-proposal step, can_trigger=True.
    forced = dict(view)
    forced["can_trigger_ai_proposer"] = True
    forced["registered_can_trigger_ai_proposer"] = True
    forced["can_create_proposal"] = False
    store._senate_view = forced
    assert store._is_valid_senate_projection(forced, VIEWER) is True, forced
    assert store.canTriggerAIProposer is True, forced
    assert store.canCreateSenateProposal is False, forced
    assert store.senateAiProposerBlocked is False, "the control must be UNLOCKED"

    book = session_turn_service._book(state)
    records_before = len(book.records)
    packages_before = dict(state.get_senate_package_registry()["packages"])
    sid = state.get_senate_session()
    receipt_before = state.get_senate_finalization_receipt(sid)
    proposals_before = list(state.get_senate_proposals())
    store._committed_receipt = None

    # The spy must cover the REFUSED CALL ITSELF (the old scope ended before
    # it, so a dispatch on this path could never be seen).
    box, p_producer, p_call, p_human = _dispatch_surface(store)
    with p_producer, p_call, p_human:
        refused = store.doSubmitSenateProposals([])

    assert refused.get("success") is False, refused
    # FINDING (R1): the Store refused the command BUT only after dispatching the
    # AI producer — a NON-proposal step with an affirmative trigger bit reaches
    # the AI route. The Core package write itself is refused (no new
    # package/receipt/record below), so this is a DISPATCH leak, not a publish.
    assert box["producer"] == [], (box, refused.get("message"))
    assert box["adapter_ai"] == [], (box["adapter_ai"], refused.get("message"))
    assert box["human_submit"] == [], box["human_submit"]
    assert len(session_turn_service._book(state).records) == records_before
    assert dict(state.get_senate_package_registry()["packages"]) == packages_before
    assert state.get_senate_finalization_receipt(sid) == receipt_before
    assert list(state.get_senate_proposals()) == proposals_before
    assert store._committed_receipt is None, "a refusal commits no receipt"
    assert state.senate_proposal_decision_complete is True  # unchanged, no new run
    assert witness.pendings == []


# ===========================================================================
# R3 / TA-W3-05 §1 — the zero package is PROVEN AT THE PUBLICATION INSTANT,
# and a repeated click on the SAME scope adds nothing
# ===========================================================================
def test_zero_package_publication_instant_snapshot_and_repeat_is_inert():
    """TA-W3-05 §1 retained invariants bound to this module's nodeids.

    §1 captures, per case: (1) session/turn/scope_id/OID, (2) latched actual
    owner, (3) presenter G, (4) viewer/principal/Core/pending/activation,
    (5) DTO top-level/registered capability, (6) raw feedback/delivery/validator,
    (7) publication/receipt/decision_complete, (8) finalization four facts,
    (9) AI and HUMAN Adapter/continuation/advance call counts.

    Coverage table (no invariant is claimed by file existence alone):
    ----------------------------------------------------------------
    | §1 | bound nodeid                                                        |
    |---|---------------------------------------------------------------------|
    | 1 | test_ai_entry_stops_at_real_presenter_before_generation              |
    | 1,4 | test_normal_restore_chains_have_zero_failures_or_recovery          |
    | 1,7 | test_zero_package_publication_instant_snapshot_and_repeat_is_inert |
    | 2,3,5,6 | test_ai_entry_stops_at_real_presenter_before_generation        |
    | 4,6,7,8,9 | test_ai_zero_package_confirm_finalizes_then_manual_combat      |
    | 1,2,6,7,8,9 | test_ai_nonempty_chain_reaches_terminal_and_combat            |
    | 5,9 | test_presenter_capability_never_grants_human_ai_decision_rights    |
    | 5,9 | test_invalid_ai_capability_is_rejected_before_dispatch             |
    | 5,9 | test_non_proposal_step_trigger_true_zero_dispatch                  |
    | 9 | test_manual_combat_entry_requires_player_action                      |
    |---|---------------------------------------------------------------------|
    """
    # R2: 1H2AI — the design's registered restore session.
    state = _entry_state(consul_controller="ai", third="ai", budget=False)
    assert [p.player_id for p in state.get_all_players()] == [
        VIEWER, CONSUL_OWNER, SECOND_AI_OWNER]
    sink = []
    instant = []
    store, witness = _store(state)

    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink)):
        feedback, _, _ = _entry_delivery(store)
        assert feedback["success"] is True, feedback
        # (1) the live scope identity is read BEFORE the click and must not move.
        scope = session_turn_service._book(state).scopes.get("senate")
        assert scope is not None
        scope_id = scope.scope_id
        assert state.get_senate_session() is None, "nothing is published yet"

        # ---- the click: ONE publication, one receipt, one continuation -----
        with _ai_makes_no_proposals(), _chain_counters(state, instant) as chain:
            click, owner = _click(store)

    assert owner.get("success") is True, (click, owner,
                                         store.senateFinalizationWarning)
    assert sink == [1], "the click must run the AI producer exactly once"

    # (7) publication / receipt / continuation, each EXACTLY once.
    assert chain["publications"] == 1, chain["publications"]
    assert chain["receipts"] == 1, chain["receipts"]
    assert chain["continuations"] == 1, chain["continuations"]

    # ---- the PUBLICATION INSTANT (before the finalizer cleared anything) ---
    assert len(instant) == 1, instant
    snap = instant[0]
    session_id = snap["senate_session_id"]
    assert session_id == f"turn-{state.turn.turn_number}", session_id
    # decision_complete is a REAL publication fact, not a click claim.
    assert snap["decision_complete"] is True, snap
    # the package is the EMPTY one: a legal owner decision with zero proposals.
    assert snap["proposals"] == [], snap
    assert snap["package_id"], snap
    record = snap["record"]
    assert record is not None, snap
    assert record["package_id"] == snap["package_id"], record
    assert record["senate_session_id"] == session_id, record
    assert record["proposal_refs"] == [], record
    assert record["direct_decision_refs"] == [], record
    assert record["publication_state"] == "COMMITTED", record
    # (2) the actor of the package is the REAL AI decision owner (never G).
    assert record["actor_id"] == CONSUL_OWNER, record
    assert record["actor_id"] != VIEWER, record

    # the same facts hold afterwards, and the scope identity did not move.
    # NOTE (R3): the finalizer clears the in-flight decision flag when it publishes
    # the terminal, so ``decision_complete`` is only authoritative AT THE INSTANT
    # above — afterwards the canonical terminal is the governing fact.
    assert state.get_senate_package_id_for_session(session_id) == snap["package_id"]
    assert session_turn_service._book(state).scopes["senate"].scope_id == scope_id
    canonical = senate_api.canonical_finalization(state)
    assert canonical["status"] == "VALID", canonical
    assert all(canonical["facts"].values()), canonical["facts"]

    # ---- a repeated click on the SAME scope adds NOTHING -------------------
    packages_before = dict(state.get_senate_package_registry()["packages"])
    receipt_before = state.get_senate_finalization_receipt(session_id)
    records_before = len(session_turn_service._book(state).records)
    box, p_producer, p_call, p_human = _dispatch_surface(store)
    with p_producer, p_call, p_human, _chain_counters(state) as chain2:
        again = store.doSubmitSenateProposals([])

    assert again.get("success") is False, again
    assert box["producer"] == [], box["producer"]
    assert box["adapter_ai"] == [], box["adapter_ai"]
    assert box["human_submit"] == [], box["human_submit"]
    assert chain2["publications"] == 0, chain2["publications"]
    assert chain2["receipts"] == 0, chain2["receipts"]
    assert chain2["continuations"] == 0, chain2["continuations"]
    assert dict(state.get_senate_package_registry()["packages"]) == packages_before
    assert state.get_senate_finalization_receipt(session_id) == receipt_before
    assert len(session_turn_service._book(state).records) == records_before
    assert state.get_senate_package_id_for_session(session_id) == snap["package_id"]
    assert witness.pendings == []
    # nothing was republished or re-finalized by the second click
    assert senate_api.canonical_finalization(state)["status"] == "VALID"


# ===========================================================================
# TA-W3-05 §1 #7 (TA-W3-05-A1) — CORE IDEMPOTENCY through a LEGAL owning
# dispatch: the second submission of the SAME package is typed and inert
# ===========================================================================
def test_core_duplicate_after_legal_owning_dispatch_is_typed_and_inert():
    """TA-W3-05 §1 #7 「Core 幂等」 — the independent successor oracle (R3-RW-01).

    The Slot repeat-click oracle (``test_zero_package_publication_instant_
    snapshot_and_repeat_is_inert``) is NOT this oracle: a repeated click can be
    answered by a Store-local refusal before Core is ever asked, so it cannot
    prove the Core defence. Here the second submission is driven through the
    REAL one-use owning lease + real dispatch nesting + the real AI child API
    (``senate_api.auto_submit_proposals``), i.e. a LEGITIMATE OWNING DISPATCH
    independent of the Store's routing (never a Slot re-dispatch, never a
    hand-built package dictionary).

    Core must answer with its typed ``PACKAGE_ALREADY_SUBMITTED`` and publish
    nothing: ``package_id`` / ``PackageRecord`` / refs / proposal set are
    byte-for-byte identical before and after, with zero new publication,
    receipt or continuation. The Slot repeat-click invariant is retained
    separately at the end (zero dispatch).
    """
    state, store, witness, feedback, delivery, sink = _entered_store(budget=True)
    assert feedback["success"] is True, feedback
    assert sink == [], "the entry still prepares the presentation only"

    # ---- 1) the REAL registered chain publishes ONE non-empty package ------
    with patch.object(senate_api, "auto_submit_proposals",
                      new=_counting_ai_producer(sink)):
        click, owner = _click(store)
    assert owner.get("success") is True, (click, owner,
                                         store.senateFinalizationWarning)
    assert sink == [1], "the click must run the AI producer exactly once"
    assert state.senate_proposal_decision_complete is True
    proposals = list(state.get_senate_proposals())
    assert proposals, "the AI's own non-empty package must really be published"

    # ---- 2) the canonical identity snapshot (the four compared fields) -----
    session_id = state.get_senate_session()
    assert session_id, session_id
    package_id = state.get_senate_package_id_for_session(session_id)
    assert package_id, (session_id, package_id)
    record = state.get_senate_package_record(package_id)
    assert record is not None, (package_id, record)
    refs = list(record.get("proposal_refs") or [])
    assert refs, record
    proposal_ids = sorted(int(p["id"]) for p in proposals if p.get("id") is not None)
    assert proposal_ids, proposals
    packages_before = dict(state.get_senate_package_registry()["packages"])
    receipt_before = state.get_senate_finalization_receipt(session_id)

    # ---- 3) the SAME package through a LEGAL owning dispatch ---------------
    attempts = {"n": 0}

    def _dispatch():
        attempts["n"] += 1
        return senate_api.auto_submit_proposals(state)

    with _chain_counters(state) as chain:
        dup = store._masked_senate_owning_flow(
            "doSubmitSenateProposals", "propose_many", _dispatch)

    assert attempts["n"] == 1, attempts
    assert isinstance(dup, dict), dup
    assert dup.get("success") is False, dup
    codes = {e.get("code") for e in (dup.get("errors") or [])
             if isinstance(e, dict)}
    # typed Core refusal — never an authorization denial, never a success claim
    assert "PACKAGE_ALREADY_SUBMITTED" in codes, (codes, dup)
    assert "DENIED" not in codes, (codes, dup)
    assert "已自动提交" not in (dup.get("message") or ""), dup

    # ---- 4) zero new publication / receipt / continuation ------------------
    assert chain["publications"] == 0, chain["publications"]
    assert chain["receipts"] == 0, chain["receipts"]
    assert chain["continuations"] == 0, chain["continuations"]

    # ---- 5) the four canonical fields are unchanged ------------------------
    assert state.get_senate_package_id_for_session(session_id) == package_id
    assert state.get_senate_package_record(package_id) == record
    assert list(state.get_senate_package_record(package_id).get("proposal_refs")
                or []) == refs
    assert dict(state.get_senate_package_registry()["packages"]) == packages_before
    assert sorted(int(p["id"]) for p in state.get_senate_proposals()
                  if p.get("id") is not None) == proposal_ids
    assert state.get_senate_finalization_receipt(session_id) == receipt_before
    # the refusal is a business answer, not a seat/authorization failure
    assert store.senateAiProposerBlocked is False
    assert store._handoff_failure_kind == "", store._handoff_failure_kind
    assert witness.pendings == []

    # ---- 6) the retained Slot invariant: a repeat click dispatches nothing --
    box, p_producer, p_call, p_human = _dispatch_surface(store)
    with p_producer, p_call, p_human:
        again = store.doSubmitSenateProposals([])
    assert again.get("success") is False, again
    assert box["producer"] == [], box["producer"]
    assert box["adapter_ai"] == [], box["adapter_ai"]
    assert box["human_submit"] == [], box["human_submit"]
    assert state.get_senate_package_id_for_session(session_id) == package_id
    assert dict(state.get_senate_package_registry()["packages"]) == packages_before
    assert state.get_senate_finalization_receipt(session_id) == receipt_before
