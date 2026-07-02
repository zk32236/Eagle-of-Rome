"""
Mortality API tests.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import mortality_api, session_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState


def _state_with_player(config=None):
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.add_player(Player("p1", "f1", PlayerType.HUMAN))
    state.set_current_player("p1")
    return state


def test_execute_mortality_success_from_gui_session_keeps_current_phase_mortality():
    result = session_api.create_gui_prototype_session()
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]

    response = mortality_api.execute_mortality_phase(state, player_id)

    assert response["success"]
    assert response["data"]["phase_executed"] is False
    assert response["data"]["next_phase_id"] == "revenue"
    assert not state.is_phase_executed("mortality")
    snapshot = session_api.get_session_snapshot(state, player_id)
    assert snapshot["data"]["current_phase_id"] == "mortality"
    assert snapshot["data"]["current_phase_id"] != "population"

    view = mortality_api.get_mortality_view(state, player_id)
    assert view["data"]["result"]["next_phase_id"] == "revenue"
    assert len(view["data"]["events"]) >= 1
    assert view["data"]["can_execute"] is False
    assert view["data"]["can_advance"] is True


def test_execute_mortality_rejects_repeat_execution():
    state = _state_with_player({"mortality_rules": {"event_deck": []}})

    first = mortality_api.execute_mortality_phase(state, "p1")
    second = mortality_api.execute_mortality_phase(state, "p1")

    assert first["success"]
    assert not second["success"]
    assert "already resolved" in second["message"]


def test_execute_mortality_rejects_non_current_viewer():
    state = GameState.create_for_testing({"mortality_rules": {"event_deck": []}})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.add_player(Player("p1", "f1", PlayerType.HUMAN))
    state.add_player(Player("p2", "f2", PlayerType.HUMAN))
    state.set_current_player("p1")

    response = mortality_api.execute_mortality_phase(state, "p2")

    assert not response["success"]
    assert "not the active player" in response["message"]


def test_execute_mortality_no_event_deck_records_result_without_marking_phase():
    state = _state_with_player({"mortality_rules": {"event_deck": []}})

    response = mortality_api.execute_mortality_phase(state, "p1")

    assert response["success"]
    assert not state.is_phase_executed("mortality")
    assert response["data"]["next_phase_id"] == "revenue"
    assert response["data"]["events"][0]["effect"] == "none"


def test_advance_mortality_phase_requires_existing_result():
    state = _state_with_player({"mortality_rules": {"event_deck": []}})

    response = mortality_api.advance_mortality_phase(state, "p1")

    assert not response["success"]
    assert "has not been resolved" in response["message"]


def test_advance_mortality_phase_marks_executed_and_enters_revenue():
    state = _state_with_player({"mortality_rules": {"event_deck": []}})
    execute = mortality_api.execute_mortality_phase(state, "p1")

    response = mortality_api.advance_mortality_phase(state, "p1")

    assert execute["success"]
    assert response["success"]
    assert response["data"]["phase_executed"] is True
    assert response["data"]["next_phase_id"] == "revenue"
    assert state.is_phase_executed("mortality")
    assert mortality_api.get_mortality_view(state, "p1")["data"]["current_phase_id"] == "revenue"


def test_advance_year_clears_mortality_result_and_allows_next_year_execution():
    state = _state_with_player({"mortality_rules": {"event_deck": []}})
    first = mortality_api.execute_mortality_phase(state, "p1")
    advance = mortality_api.advance_mortality_phase(state, "p1")

    state.advance_year()
    assert state.get_phase_result("mortality") is None
    second = mortality_api.execute_mortality_phase(state, "p1")

    assert first["success"]
    assert advance["success"]
    assert second["success"]
    assert not state.is_phase_executed("mortality")


def test_execute_mortality_death_event_returns_structured_summary():
    state = _state_with_player({
        "mortality_rules": {
            "event_deck": [{"name": "死神来了", "effect": "death", "weight": 1}],
            "event_draw_count": 1,
            "death_count": 1,
        }
    })
    faction = Faction("f1", "测试派")
    state.add_faction(faction)
    figure = Figure(1, "测试人物", faction_id="f1", age=40)
    state.add_member(figure)
    faction.member_ids = [1]

    response = mortality_api.execute_mortality_phase(state, "p1")

    assert response["success"]
    event = response["data"]["events"][0]
    assert event["effect"] == "death"
    assert event["impacts"][0]["type"] == "figure_death"
    assert event["impacts"][0]["figure_id"] == 1
    assert state.get_member(1).is_dead is True
