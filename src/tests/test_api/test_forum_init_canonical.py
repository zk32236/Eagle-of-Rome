"""
src/tests/test_api/test_forum_init_canonical.py

Canonical forum initialization tests (GUI-BETA-R1 WP-C).

Covers AU-1 initialize_forum_turn: the 5 init side effects (war trigger 015,
contracts 014, figures+hero 009, fleet completion ④, province unrest ⑤),
exactly-once guard, ODR-04 hero marker turn-ownership validation, cross-turn
reset (T-C-01..10), and AU-4 resolution land-acts hook (T-R-01/02).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from unittest.mock import patch

from src.api import forum_api
from src.api import session_api
from src.core.entities.contract import ContractType
from src.core.entities.figure import ClassTier
from src.core.entities.war import WarStatus


def _make_state(start_phase="forum"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"]
    return result["data"]["state"]


def _hero_marker(state, spawn_turn):
    state.hero_spawned_this_turn = True
    state.hero_to_spawn = {"type": "random", "spawn_turn": spawn_turn}


# ---------------------------------------------------------------------------
# T-C-01..10 — canonical init (AU-1)
# ---------------------------------------------------------------------------

def test_initialize_forum_turn_war_trigger():
    """015: init runs war check_triggers + escalate_threats (respects enable_threats)."""
    state = _make_state()
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    ws = state.get_war_system()
    assert ws is not None
    pyrrhic = next((w for w in ws.get_threat_wars() if w.id == "pyrrhic_war"), None)
    assert pyrrhic is not None, "pyrrhic_war should be a THREAT after init"
    assert pyrrhic.status == WarStatus.THREAT
    assert pyrrhic.threat_level >= 1


def test_initialize_forum_turn_contract_generation():
    """014: init generates contracts; turn-1 Italy PUBLIC_WORKS (province_id==0)."""
    state = _make_state()
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    italy_works = [
        c for c in state.get_all_contracts()
        if c.contract_type == ContractType.PUBLIC_WORKS and c.province_id == 0
    ]
    assert italy_works, "expected Italy PUBLIC_WORKS contract after init"


def test_initialize_forum_turn_hero_consumption():
    """009: preset hero markers (valid stamp) are consumed; hero enters curia; markers cleared."""
    state = _make_state()
    turn = state.turn.turn_number
    _hero_marker(state, turn)
    before_ids = {f.id for f in state.curia.get_all_available()}
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    assert state.hero_spawned_this_turn is False
    assert state.hero_to_spawn is None
    available = state.curia.get_all_available()
    new_figures = [f for f in available if f.id not in before_ids]
    assert len(new_figures) == 4, "3 normal figures + 1 hero expected"
    hero = next((f for f in new_figures if f.class_tier == ClassTier.NOBILE), None)
    assert hero is not None, "hero should be NOBILE"
    hero_rows = [fd for fd in result["data"]["figures"] if fd.get("is_hero")]
    assert len(hero_rows) == 1, "init result should flag the hero row"


def test_initialize_forum_turn_fleet_completion():
    """④: init delegates fleet construction completion to naval_system (turn_number)."""
    state = _make_state()
    assert state.naval_system is not None
    with patch.object(
        state.naval_system, "process_fleet_construction",
        wraps=state.naval_system.process_fleet_construction,
    ) as spy:
        result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    spy.assert_called_once_with(state.turn.turn_number)


def test_initialize_forum_turn_unrest():
    """⑤: init runs province unrest check; result carries rebellions/province_updates."""
    state = _make_state()
    with patch(
        "src.api.forum_api.check_province_unrest",
        wraps=forum_api.check_province_unrest,
    ) as spy:
        result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    spy.assert_called_once_with(state)
    unrest = result["data"]["unrest"]
    assert "rebellions" in unrest
    assert "province_updates" in unrest


def test_initialize_forum_turn_exactly_once():
    """Second init within the same turn is a no-op (data=={}; no side effects doubled)."""
    state = _make_state()
    r1 = forum_api.initialize_forum_turn(state)
    assert r1["success"]
    threat_ids_1 = sorted(w.id for w in state.get_war_system().get_threat_wars())
    contracts_1 = len(state.get_all_contracts())
    figures_1 = len(state.curia.get_all_available())

    r2 = forum_api.initialize_forum_turn(state)
    assert r2["success"]
    assert r2["data"] == {}
    assert sorted(w.id for w in state.get_war_system().get_threat_wars()) == threat_ids_1
    assert len(state.get_all_contracts()) == contracts_1
    assert len(state.curia.get_all_available()) == figures_1
    assert state.get_forum_pending().get("forum_initialized")


def test_initialize_forum_turn_hero_stale_cleanup():
    """009 defensive cleanup: stale marker (spawn flag False) is cleared, no hero spawned."""
    state = _make_state()
    state.hero_spawned_this_turn = False
    state.hero_to_spawn = {"type": "random"}
    before_count = len(state.curia.get_all_available())
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    assert state.hero_spawned_this_turn is False
    assert state.hero_to_spawn is None
    assert len(state.curia.get_all_available()) == before_count + 3, "no hero expected"


def test_initialize_forum_turn_odr04_stale_marker_discard():
    """ODR-04: marker stamped with an older turn is discarded (not consumed)."""
    state = _make_state()
    _hero_marker(state, state.turn.turn_number - 1)
    before_count = len(state.curia.get_all_available())
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    assert state.hero_spawned_this_turn is False
    assert state.hero_to_spawn is None
    assert len(state.curia.get_all_available()) == before_count + 3, "stale hero must not spawn"


def test_initialize_forum_turn_odr04_unstamped_marker_discard():
    """ODR-04 pre-fix transition: unstamped marker (legacy save) is discarded, not consumed."""
    state = _make_state()
    state.hero_spawned_this_turn = True
    state.hero_to_spawn = {"type": "random"}  # legacy save: no spawn_turn stamp
    before_count = len(state.curia.get_all_available())
    result = forum_api.initialize_forum_turn(state)
    assert result["success"]
    assert state.hero_spawned_this_turn is False
    assert state.hero_to_spawn is None
    assert len(state.curia.get_all_available()) == before_count + 3, "unstamped hero must not spawn"


def test_forum_initialized_reset_cross_turn():
    """Cross-turn reset: resolve_forum clears forum_initialized; next turn re-inits."""
    state = _make_state()
    r1 = forum_api.initialize_forum_turn(state)
    assert r1["success"]
    figures_turn1 = len(state.curia.get_all_available())

    forum_api.resolve_forum(state)
    assert not state.get_forum_pending().get("forum_initialized"), \
        "resolve_forum must reset forum_initialized"

    state.turn.advance_year()
    r2 = forum_api.initialize_forum_turn(state)
    assert r2["success"]
    assert r2["data"] != {}, "second turn init must re-execute side effects"
    assert len(state.curia.get_all_available()) > figures_turn1
    assert state.get_forum_pending().get("forum_initialized")


# ---------------------------------------------------------------------------
# T-R-01/02 — resolution land-acts hook (AU-4)
# ---------------------------------------------------------------------------

def test_resolve_forum_executes_land_acts():
    """AU-4: resolve_forum executes pending land distribution acts (idempotent hook)."""
    state = _make_state()
    state.add_national_public_land(1000)
    national_before = state.get_national_public_land()
    italy = state.get_province(0)
    italy_private_before = italy.land_private
    state.add_pending_land_act({"type": "distribution", "percent": 0.1})

    result = forum_api.resolve_forum(state)
    assert result["success"]
    assert state.get_pending_land_acts() == []
    assert state.get_national_public_land() < national_before
    assert italy.land_private > italy_private_before


def test_resolve_forum_land_acts_idempotent():
    """AU-4: second resolve_forum does not re-execute land acts."""
    state = _make_state()
    state.add_national_public_land(1000)
    state.add_pending_land_act({"type": "distribution", "percent": 0.1})
    r1 = forum_api.resolve_forum(state)
    assert r1["success"]
    land_after_first = state.get_province(0).land_private
    r2 = forum_api.resolve_forum(state)
    assert r2["success"]
    assert state.get_province(0).land_private == land_after_first
