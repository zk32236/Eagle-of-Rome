"""EOR20261013-02 · Rework-D3D6 — owner-contract RED/GREEN (D3).

RED-first proof for the D3 root-cause domain ("owner-validated explicit empty
veto decision + checked completion receipt"), per the FROZEN design:

  * ``Rework-D3D6-Design-Delta_2026-10-16.md`` (rev3) sec 3 / sec 3.1 / sec 6
    FC-RW-01/03/05
  * ``Rework-D3D6_Implementation_and_Test_Overlay_2026-10-16.md`` sec 3.1 / sec 4
    (R-D3) / sec 8 (RW-AC-01)

Covered:
  * T-D3-01  RW-AC-01  an explicit EMPTY veto by the real current HUMAN tribune is
    a LAWFUL decision (success, ``vetoed == []``) — never the always-failing
    ``record_veto([])`` result.
  * T-D3-02  RW-AC-01  on a registered Hot-seat session the empty decision
    SATISFIES the singleton veto OID through the ONE checked completion writer
    (``_record_veto_step_completion``) so ``phase_ready('senate')`` becomes True.
  * T-D3-03            the empty branch is OWNER-validated: a non-current /
    non-owner player is refused (fail-closed) with NO completion.
  * T-D3-04            the NON-EMPTY veto path is unchanged (existing passed-only
    rules preserved).
  * T-D3-NEG-01        a rejected owner completion is NOT swallowed into success.

Scenarios are constructed in-test (``UNIT-LOCAL-ONLY``); the API/coordinator
business chain stays production. No product/QML/data file is changed.

WATERMARK: DA-Execute owner-contract regression; no commit/push/delete.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import senate_api
from src.api import session_access
from src.api import session_turn_service as turn_service
from src.ui.gui.session_store import GuiSessionStore
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem


def _senate_veto_state():
    """optimates(player1) holds consul; populares(player2) holds the tribune.

    Two passed proposals with every required ballot already in and player2 as the
    current (last-scheduled) player -> the veto obligation is REQUIRED, enforcing a
    real owner-validated explicit empty decision.
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f1.member_ids.append(1)

    tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(3)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.HUMAN))
    state._turn_order = ["player1", "player2"]
    state.set_current_player("player2")

    state.senate_proposal_decision_complete = True
    pids = []
    for _ in range(2):
        pid = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        state.record_senate_vote("player1", pid, True)
        state.record_senate_vote("player2", pid, True)
        pids.append(pid)
    return state, pids


def _veto_oid(state):
    scope = turn_service.mint_scope(state, "senate")
    book = turn_service._book(state)
    return book.oid("senate", "veto", ("singleton", scope.scope_id),
                    scope.scope_id), scope.scope_id


# ===========================================================================
# T-D3-01 — explicit empty veto is a lawful owner decision
# ===========================================================================
def test_d3_01_explicit_empty_veto_is_lawful_no_veto():
    state, _pids = _senate_veto_state()
    res = senate_api.veto(state, "player2", [])
    assert res.get("success") is True, res
    assert res["data"].get("vetoed") == []
    assert res["data"].get("rejected_ids") == []
    # no veto was recorded in the domain state (zero veto mutation).
    assert state.get_senate_vetoes_copy() == set()


# ===========================================================================
# T-D3-02 — registered Hot-seat: the empty decision satisfies the veto OID
# ===========================================================================
def test_d3_02_registered_empty_veto_satisfies_singleton_obligation():
    state, _pids = _senate_veto_state()
    ctx = session_access.register_hotseat_session(state, "player2", epoch=0)
    oid, scope_id = _veto_oid(state)
    book = turn_service._book(state)
    rev = turn_service.current_revision(state)
    assert book.satisfied(oid, scope_id, rev) is False
    assert turn_service.phase_ready(state, "senate") is False

    res = senate_api.veto(state, "player2", [], caller_context=ctx)
    assert res.get("success") is True, res
    # W-12 (TA-06): the owning entry binds the phase and therefore starts a NEW
    # scope generation — the handle minted by a pre-command READ is superseded by
    # design (enter_phase always mints a fresh scope). Re-derive before asserting;
    # the invariant under test (the singleton veto OID is satisfied in the CURRENT
    # generation) is unchanged.
    oid, scope_id = _veto_oid(state)
    assert book.satisfied(oid, scope_id, turn_service.current_revision(state)) is True
    # the ALL-ballots readiness predicate is now satisfied (finalization is not an
    # obligation) — the empty decision closed the frozen veto obligation.
    assert turn_service.phase_ready(state, "senate") is True


# ===========================================================================
# T-D3-03 — fail-closed owner validation (non-owner / non-current refused)
# ===========================================================================
def test_d3_03_non_owner_empty_veto_refused_no_completion():
    state, _pids = _senate_veto_state()          # current = player2
    # player1 is NOT the eligible tribune owner and NOT current.
    res = senate_api.veto(state, "player1", [])
    assert res.get("success") is False, res
    codes = {e.get("code") for e in (res.get("errors") or []) if isinstance(e, dict)}
    assert codes, res


def test_d3_03b_no_eligible_tribune_refused():
    state, _pids = _senate_veto_state()
    state.get_member(3).is_dead = True           # remove the only eligible tribune
    res = senate_api.veto(state, "player2", [])
    assert res.get("success") is False, res


# ===========================================================================
# T-D3-04 — the NON-EMPTY veto path is unchanged
# ===========================================================================
def test_d3_04_nonempty_veto_still_records_the_veto():
    state, pids = _senate_veto_state()
    res = senate_api.veto(state, "player2", [pids[0]])
    assert res.get("success") is True, res
    assert res["data"].get("vetoed") == [pids[0]]
    assert state.get_senate_vetoes_copy() == {pids[0]}


# ===========================================================================
# D3/D5 R1 — R01 (input contract) + R03 (REAL Store logical DATA chain)
# ---------------------------------------------------------------------------
# R01: the OWNER boundary must preserve the difference between an EXPLICIT ``[]``
# decision and a MISSING / MALFORMED payload (None / bad shape). A malformed
# payload must NOT be normalized into a lawful "explicit no-veto"; it is a real
# failure with ZERO new receipt / completion and ZERO veto mutation.
# R03: the D3 obligation is only closed by a REAL Store ``doSubmitSenateVetoes([])``
# -> real owner completion -> ``phase_ready`` -> real result/advance chain (not an
# API-only / ``phase_ready``-only test), with one-time-completion counting evidence.
# ===========================================================================
class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


def _senate_store():
    """Build the REAL registered GuiSessionStore over the senate-veto state."""
    state, pids = _senate_veto_state()
    session_access.register_hotseat_session(state, "player2", epoch=0)
    store = GuiSessionStore(state)
    _Receiver(store)
    store.initialize("player2")
    return store, state, pids


# --- R01 (API owner boundary) ----------------------------------------------
def test_r01_api_veto_none_payload_is_not_an_empty_decision():
    state, _pids = _senate_veto_state()
    oid, scope_id = _veto_oid(state)
    book = turn_service._book(state)
    res = senate_api.veto(state, "player2", None)
    assert res.get("success") is False, res
    assert book.satisfied(oid, scope_id, turn_service.current_revision(state)) is False
    assert state.get_senate_vetoes_copy() == set()


def test_r01_api_veto_bad_shape_payload_is_not_an_empty_decision():
    for bad in ({"x": 1}, "12", 0, False, "consul"):
        state, _pids = _senate_veto_state()
        oid, scope_id = _veto_oid(state)
        book = turn_service._book(state)
        res = senate_api.veto(state, "player2", bad)
        assert res.get("success") is False, (bad, res)
        assert book.satisfied(oid, scope_id,
                              turn_service.current_revision(state)) is False, bad
        assert state.get_senate_vetoes_copy() == set(), bad


# --- R01 (REAL Store payload boundary) -------------------------------------
def test_r01_store_malformed_payload_not_silently_no_veto():
    store, state, _pids = _senate_store()
    oid, scope_id = _veto_oid(state)
    book = turn_service._book(state)
    for bad in (None, ["x", "y"], [None], {}, "3"):
        fb = store.doSubmitSenateVetoes(bad)
        assert fb.get("success") is False, (bad, fb)
        assert book.satisfied(oid, scope_id,
                              turn_service.current_revision(state)) is False, bad
        assert state.get_senate_vetoes_copy() == set(), bad


# --- R03 (REAL Store logical DATA chain) -----------------------------------
def test_r03_d3_store_none_payload_keeps_zero_completion_chain():
    """R03: a MISSING payload through the REAL Store must NOT become a lawful
    no-veto - the chain yields a failure with ZERO new receipt / completion."""
    store, state, _pids = _senate_store()
    oid, scope_id = _veto_oid(state)
    book = turn_service._book(state)
    rev = turn_service.current_revision(state)
    fb = store.doSubmitSenateVetoes(None)
    assert fb.get("success") is False, fb
    assert book.satisfied(oid, scope_id, rev) is False
    assert turn_service.phase_ready(state, "senate") is False
    assert state.get_senate_vetoes_copy() == set()
    assert state.get_phase_result("senate") is None


# --- R03 (REAL Store logical DATA chain) -----------------------------------
def test_r03_d3_store_explicit_empty_veto_full_chain_ready_result():
    store, state, _pids = _senate_store()
    oid, scope_id = _veto_oid(state)
    book = turn_service._book(state)
    assert book.satisfied(oid, scope_id,
                          turn_service.current_revision(state)) is False
    assert turn_service.phase_ready(state, "senate") is False

    fb = store.doSubmitSenateVetoes([])
    assert fb.get("success") is True, fb
    # real owner completion satisfied the singleton veto OID; the REAL result
    # landed (no veto recorded) and the real advance capability is available.
    # TA-06: re-derive the CURRENT generation (W-12 binds the owning entry first).
    oid, scope_id = _veto_oid(state)
    assert book.satisfied(oid, scope_id,
                          turn_service.current_revision(state)) is True
    assert state.get_senate_vetoes_copy() == set()
    assert state.get_phase_result("senate") is not None
    assert store.canAdvanceSenate is True
    adv = store.doAdvanceSenate()
    assert adv.get("success") is True, adv


def test_r03_d3_completion_rejection_is_not_success(monkeypatch):
    state, _pids = _senate_veto_state()
    ctx = session_access.register_hotseat_session(state, "player2", epoch=0)
    monkeypatch.setattr(turn_service, "complete_actor",
                        lambda *a, **k: {"success": False, "reason": "FORCED_REJECT"})
    res = senate_api.veto(state, "player2", [], caller_context=ctx)
    assert res.get("success") is False, res


def test_r03_d3_completion_exception_is_not_success(monkeypatch):
    state, _pids = _senate_veto_state()
    ctx = session_access.register_hotseat_session(state, "player2", epoch=0)
    # silence the expected exception log (evidence hygiene: the runner's captured
    # -rA logs would otherwise echo a ``<line> failed`` token).
    import logging
    monkeypatch.setattr(logging.getLogger("EOR-GUI"), "exception",
                        lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(turn_service, "complete_actor", _boom)
    res = senate_api.veto(state, "player2", [], caller_context=ctx)
    assert res.get("success") is False, res
    codes = {e.get("code") for e in (res.get("errors") or []) if isinstance(e, dict)}
    assert "VETO_COMPLETION_EXCEPTION" in codes, res


def test_r03_d3_reentry_consumes_completion_once(monkeypatch):
    state, _pids = _senate_veto_state()
    ctx = session_access.register_hotseat_session(state, "player2", epoch=0)
    counts = {"issue": 0, "complete": 0}
    orig_issue = turn_service.issue_owner_receipt
    orig_complete = turn_service.complete_actor

    def _issue_spy(*a, **k):
        counts["issue"] += 1
        return orig_issue(*a, **k)

    def _complete_spy(*a, **k):
        counts["complete"] += 1
        return orig_complete(*a, **k)
    monkeypatch.setattr(turn_service, "issue_owner_receipt", _issue_spy)
    monkeypatch.setattr(turn_service, "complete_actor", _complete_spy)

    r1 = senate_api.veto(state, "player2", [], caller_context=ctx)
    assert r1.get("success") is True, r1
    r2 = senate_api.veto(state, "player2", [], caller_context=ctx)
    assert r2.get("success") is False, r2   # re-entry refused (obligation satisfied)
    # exactly one receipt issued / one completion consumed (one-time consumption).
    assert counts == {"issue": 1, "complete": 1}, counts
