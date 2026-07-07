# src/tests/test_core/test_scenario_loader.py
import pytest
from src.core.game_state import GameState
from src.core.scenario_loader import ScenarioLoader

def test_faction_initial_treasury():
    state = GameState()
    ScenarioLoader.load_scenario(state, "mvp_test.json")
    for faction in state.factions.values():
        assert faction.treasury == state.get_economic_rule("faction_initial_treasury", 10)