"""EOR20261013-02 · Rework-D3D6 — masked-path chain RED/GREEN (D5).

RED-first proof for the D5 root-cause domain ("staged population DTO nested
candidate read"), per the FROZEN design:

  * ``Rework-D3D6-Design-Delta_2026-10-16.md`` (rev3) sec 5 / sec 6 FC-RW-01/02/12
  * ``Rework-D3D6_Implementation_and_Test_Overlay_2026-10-16.md`` sec 3.3 / sec 4
    (R-D5) / sec 8 (RW-AC-04/05)

Covered:
  * T-D5-CHAIN-01  RW-AC-04  the FIRST publication under mask of a real masked
    handoff (A -> B) must already carry the AUTHORITATIVE candidate set (the
    service-private ``_get_candidates_impl`` five-office map), never an empty
    placeholder produced by the PUBLIC guarded boundary degrading a denial to
    ``{}`` success.
  * T-D5-NEG-01    RW-AC-05  a candidate RETRIEVAL FAILURE must be an EXPLICIT
    failure envelope, never a "successful" empty vacancy.

Scenarios are constructed in-test from the COMMITTED fixture; the Store/Adapter/
API business chain stays production. ``source_kind=CONSTRUCTED_STATE`` /
``test_chain_quality=UNIT-LOCAL-ONLY`` (per the frozen overlay). The pixel/frame
face is DEFERRED_FOLLOWON and is NOT asserted here.

WATERMARK: DA-Execute masked-path chain regression; no commit/push/delete.
"""
from __future__ import annotations

import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import population_api
from src.api import session_access
from src.api import session_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"


@pytest.fixture(autouse=True)
def _restore_rng():
    st = random.getstate()
    try:
        yield
    finally:
        random.setstate(st)


class _Receiver:
    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    def __init__(self):
        self.calls = []
        self.pendings = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); self.pendings.append(faction)
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route)); return True


def _prepared(start_phase, ai_tail=0):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase=start_phase, scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert len(pids) == 3, pids
    state.set_current_player(pids[0])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _masked_store(state, viewer):
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness()
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE
    return store, witness


def _first_selections(state):
    impl = population_api._get_candidates_impl(state)
    data = impl.get("data", {}) if impl.get("success") else {}
    return {office: rows[0]["id"] for office, rows in data.items() if rows}


def _authoritative(state):
    """Independent raw oracle: the service-private five-office candidate map."""
    impl = population_api._get_candidates_impl(state)
    assert impl.get("success"), impl
    data = impl["data"]
    return {office: [c["id"] for c in rows] for office, rows in data.items()}


# ===========================================================================
# T-D5-CHAIN-01 / RW-AC-04 — first publication under mask carries authority
# ===========================================================================
def test_d5_chain_01_masked_handoff_first_publication_is_authoritative():
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])

    expected = _authoritative(state)
    assert any(expected.values()), "fixture must expose a non-empty candidate set"

    fb = store.submitPopulationVotes(_first_selections(state))
    assert fb["success"] is True, fb
    # A -> B handoff: the seat enters the opaque pending state (no pre-confirm
    # publication of the next seat).
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle
    assert witness.pendings, witness.calls

    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]

    # The FIRST publication under mask (the staged bundle just applied at the
    # real reveal) must already equal the authoritative set — the nested private
    # candidate read must never be degraded to an empty placeholder.
    published = store.populationView
    got = {office: [c["id"] for c in rows]
           for office, rows in (published.get("candidates") or {}).items()}
    assert got == expected, (got, expected)
    assert published.get("office_count") == sum(1 for v in expected.values() if v)


# ===========================================================================
# T-D5-NEG-01 / RW-AC-05 — retrieval failure is EXPLICIT, never empty success
# ===========================================================================
def test_d5_neg_01_candidate_retrieval_failure_is_explicit(monkeypatch):
    # An un-registered CLI state passes the outer read guard (CLI-exempt), so the
    # candidate read seam is reachable directly.
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pid = state.get_all_players()[0].player_id
    state.set_current_player(pid)

    def _boom(_st):
        return {"success": False, "message": "boom", "data": {},
                "errors": [{"code": "SIMULATED_READ_FAILURE"}]}
    monkeypatch.setattr(population_api, "_get_candidates_impl", _boom)

    out = session_api.get_population_view(state, pid)
    assert out.get("success") is False, out
    codes = {e.get("code") for e in (out.get("errors") or []) if isinstance(e, dict)}
    assert "CANDIDATES_UNAVAILABLE" in codes, out


def test_d5_neg_02_candidate_bad_shape_is_explicit(monkeypatch):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pid = state.get_all_players()[0].player_id
    state.set_current_player(pid)

    def _bad_shape(_st):
        # missing the tribune key -> NOT the complete five-office map
        return {"success": True, "message": "ok",
                "data": {k: [] for k in
                         ("consul", "censor", "praetor", "quaestor")}}
    monkeypatch.setattr(population_api, "_get_candidates_impl", _bad_shape)

    out = session_api.get_population_view(state, pid)
    assert out.get("success") is False, out
    codes = {e.get("code") for e in (out.get("errors") or []) if isinstance(e, dict)}
    assert "CANDIDATES_SHAPE_INVALID" in codes, out


def test_d5_neg_03_legit_all_empty_is_still_success(monkeypatch):
    """A lawful all-empty five-office mapping is a VALID vacancy — NOT a failure."""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pid = state.get_all_players()[0].player_id
    state.set_current_player(pid)

    empty = {k: [] for k in ("consul", "censor", "praetor", "quaestor", "tribune")}
    monkeypatch.setattr(
        population_api, "_get_candidates_impl",
        lambda _st: {"success": True, "message": "ok", "data": dict(empty)})

    out = session_api.get_population_view(state, pid)
    assert out.get("success") is True, out
    assert out["data"].get("candidates") == empty
    assert out["data"].get("office_count") == 0


# ===========================================================================
# D3/D5 R1 — R02 (stable exception code) + R03 (logical DATA chain / SECC)
# ---------------------------------------------------------------------------
# R02: a candidate retrieval EXCEPTION (or a non-dict envelope) must map to the
# stable ``CANDIDATES_UNAVAILABLE`` code, NOT the outermost generic
# ``errors=[str(e)]``. ``CANDIDATES_SHAPE_INVALID`` still covers bad shape;
# a lawful all-empty five-office map still succeeds.
# R03: a failing STAGING read on the REAL masked receiver must keep the mask and
# publish NO candidates (not just a direct API negative); and the SECC
# C-N/C-B1/C-B2/C-B3 parity uses an INDEPENDENT raw commit-side oracle (never
# ``_get_candidates_impl``/``get_candidates``/``get_population_view``/Store).
# ===========================================================================
def _phase_view_state():
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pid = state.get_all_players()[0].player_id
    state.set_current_player(pid)
    return state, pid


# --- R02 (stable exception -> code) ----------------------------------------
def test_r02_d5_helper_raise_maps_to_candidates_unavailable(monkeypatch):
    state, pid = _phase_view_state()

    def _raise(_st):
        raise RuntimeError("simulated retrieval failure")
    monkeypatch.setattr(population_api, "_get_candidates_impl", _raise)

    out = session_api.get_population_view(state, pid)
    assert out.get("success") is False, out
    codes = {e.get("code") for e in (out.get("errors") or []) if isinstance(e, dict)}
    assert "CANDIDATES_UNAVAILABLE" in codes, out


def test_r02_d5_non_dict_envelope_maps_to_candidates_unavailable(monkeypatch):
    state, pid = _phase_view_state()
    monkeypatch.setattr(population_api, "_get_candidates_impl",
                        lambda _st: ["not", "a", "dict"])
    out = session_api.get_population_view(state, pid)
    assert out.get("success") is False, out
    codes = {e.get("code") for e in (out.get("errors") or []) if isinstance(e, dict)}
    assert "CANDIDATES_UNAVAILABLE" in codes, out


# --- R03 (REAL masked receiver: failing staging keeps mask, no publication) --
def test_r03_d5_failing_staging_keeps_mask_and_no_publication(monkeypatch):
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])

    orig = population_api._get_candidates_impl

    def _gated(st):
        # Fail ONLY the STAGING read (the private activation reservation nesting),
        # never the owning-commit reads -> the failure lands at the real receiver
        # stage seam (last retrieval) on the A -> B handoff.
        if session_access._nesting_staging_capability(st) is not None:
            raise RuntimeError("simulated staging retrieval failure")
        return orig(st)
    monkeypatch.setattr(population_api, "_get_candidates_impl", _gated)

    pubs = []
    store.populationViewChanged.connect(lambda: pubs.append(dict(store.populationView)))
    fb = store.submitPopulationVotes(_first_selections(state))
    assert fb["success"] is True, fb
    # the A -> B handoff reaches the opaque pending state; the STAGING of B's DTOs
    # happens on the real takeover and fails (the retrieval seam is real).
    assert store.seatLifecycle == SEAT_MASKED_PENDING, store.seatLifecycle

    result = store.requestTakeover()

    # the mask is RETAINED (failure), no fresh handle, and NO candidates were ever
    # published to the public model. (``accepted`` is only an intent ack, not
    # success; the lifecycle is the authority.)
    assert store.seatLifecycle == SEAT_MASKED_FAILURE, store.seatLifecycle
    assert not (store.populationView.get("candidates") or {}), store.populationView
    assert all(not (p.get("candidates") or {}) for p in pubs), pubs
    assert any(c[0] == "failure" for c in witness.calls), witness.calls


# --- R03 (SECC independent raw commit-side oracle) -------------------------
def _raw_candidate_oracle(state):
    """INDEPENDENT raw commit-side oracle (Delta sec 9.1 C_raw): derive the
    five-office candidate list from the raw living members + frozen config, using
    only the domain primitive ``Figure.can_hold_office`` — NEVER the candidate
    projection helper / Store / ``get_population_view``."""
    offices = ["consul", "censor", "praetor", "quaestor", "tribune"]
    turn = state.turn.turn_number
    cfg = state.config.get("political_rules", {}).get("candidates_per_election", {})
    out = {o: [] for o in offices}
    used = set()
    for office in offices:
        elig = []
        for fig in state.get_living_members():
            if fig.is_absent or fig.faction_id is None or fig.id in used:
                continue
            ok, _ = fig.can_hold_office(office, turn, state.config)
            if ok:
                elig.append(fig)
        elig.sort(key=lambda f: f.get_qualification_attribute(office), reverse=True)
        top = elig[: cfg.get(office, 2)]
        for f in top:
            used.add(f.id)
        out[office] = [f.id for f in top]
    return out


def test_r03_d5_secc_c_n_first_publication_matches_raw_oracle():
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])
    oracle = _raw_candidate_oracle(state)
    assert any(oracle.values())

    fb = store.submitPopulationVotes(_first_selections(state))
    assert fb["success"] is True, fb
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.requestTakeover()["accepted"] is True

    published = store.populationView
    got = {o: [c["id"] for c in rows]
           for o, rows in (published.get("candidates") or {}).items()}
    assert got == oracle, (got, oracle)


def test_r03_d5_secc_c_b1_all_empty_is_lawful_success():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.add_faction(Faction(id="f1", name="F1", treasury=10))
    state.add_player(Player(player_id="p1", faction_id="f1",
                            player_type=PlayerType.HUMAN))
    state.set_current_player("p1")
    assert all(not v for v in _raw_candidate_oracle(state).values())

    out = session_api.get_population_view(state, "p1")
    assert out.get("success") is True, out
    cands = out["data"].get("candidates") or {}
    assert cands == {k: [] for k in
                     ("consul", "censor", "praetor", "quaestor", "tribune")}, cands
    assert out["data"].get("office_count") == 0


def test_r03_d5_secc_c_b2_retrieval_failure_no_publication(monkeypatch):
    state, pid = _phase_view_state()

    def _raise(_st):
        raise RuntimeError("retrieval failure")
    monkeypatch.setattr(population_api, "_get_candidates_impl", _raise)

    out = session_api.get_population_view(state, pid)
    assert out.get("success") is False, out
    # no successful candidate publication payload is produced.
    assert not (out.get("data") or {}).get("candidates"), out
    codes = {e.get("code") for e in (out.get("errors") or []) if isinstance(e, dict)}
    assert "CANDIDATES_UNAVAILABLE" in codes, out


def test_r03_d5_secc_c_b3_resolved_historical_projection():
    state, pids = _prepared("population")
    store, witness = _masked_store(state, pids[0])
    for _ in range(3):
        if store.seatLifecycle == SEAT_MASKED_PENDING:
            assert store.requestTakeover()["accepted"] is True
        fb = store.submitPopulationVotes(_first_selections(state))
        assert fb["success"] is True, fb

    res = state.get_phase_result("population")
    assert res is not None, "the population election must have resolved"
    raw = (res.get("data") or {}).get("candidates") or {}
    assert raw, "the committed historical candidate projection must exist"

    viewer = store.viewerPlayerId
    state.set_current_player(viewer)
    out = session_api.get_population_view(
        state, viewer,
        caller_context=session_access.current_caller_context(state))
    assert out.get("success") is True, out
    got = {o: [c["id"] for c in rows]
           for o, rows in (out["data"].get("candidates") or {}).items()}
    oracle = {o: [c["id"] for c in rows] for o, rows in raw.items()}
    assert got == oracle, (got, oracle)
