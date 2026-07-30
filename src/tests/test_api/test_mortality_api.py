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
    # AC-01: 死亡事件 impact 必须包含 faction_name 字段
    assert event["impacts"][0]["faction_name"] == "测试派"
    assert event["impacts"][0]["faction_id"] == "f1"


# === AC-01: 死亡事件派系字段 ===
def test_death_event_impact_contains_faction_name():
    """死亡事件 impact 中 faction_name 必须存在且匹配死者所属派系"""
    state = _state_with_player({
        "mortality_rules": {
            "event_deck": [{"name": "死神来了", "effect": "death", "weight": 1}],
            "event_draw_count": 1,
            "death_count": 2,
        }
    })
    opt = Faction("opt", "Optimates")
    pop = Faction("pop", "Populares")
    state.add_faction(opt)
    state.add_faction(pop)
    f1 = Figure(10, "Caesar", faction_id="opt", age=50)
    f2 = Figure(11, "Pompey", faction_id="pop", age=55)
    state.add_member(f1)
    state.add_member(f2)
    opt.member_ids = [10]
    pop.member_ids = [11]

    response = mortality_api.execute_mortality_phase(state, "p1")

    assert response["success"]
    event = response["data"]["events"][0]
    assert event["effect"] == "death"
    # 每个死者 impact 必须包含 faction_name
    faction_names_found = set()
    for imp in event["impacts"]:
        assert imp["type"] == "figure_death"
        assert "faction_name" in imp, f"Missing faction_name in impact for {imp['figure_name']}"
        assert imp["faction_name"] != "", "faction_name must not be empty"
        faction_names_found.add(imp["faction_name"])
    # 两个死者应各有正确派系名
    assert "Optimates" in faction_names_found
    assert "Populares" in faction_names_found


# === AC-02: 非死亡事件不误显示派系 ===
def test_non_death_event_no_faction_in_impacts():
    """非死亡事件（丰收/和平/猛男/天灾）不应在 impacts 中包含 faction_name"""
    from src.core.service.mortality_service import MortalityService
    from src.core.entities.entities import GameTurn
    from src.core.entities.province import Province

    state = GameState.create_for_testing({
        "mortality_rules": {
            "event_draw_count": 0,
            "death_count": 0,
        }
    })
    state.turn = GameTurn(turn_number=2, year=-263)
    state.add_player(Player("p1", "f1", PlayerType.HUMAN))
    state.set_current_player("p1")
    # 添加行省支持 disaster/peace 事件
    state.add_province(Province(10, "Sicilia", total_land=1000, conquered=True))

    service = MortalityService(state)

    # 丰收事件
    result = service.apply_bountiful_harvest()
    for imp in result["impacts"]:
        assert "faction_name" not in imp, f"Bountiful harvest should not have faction_name: {imp}"

    # 和平事件
    result = service.apply_peace_event()
    for imp in result["impacts"]:
        assert "faction_name" not in imp, f"Peace event should not have faction_name: {imp}"

    # 天降猛男 — 需要 year 设定
    result = service.apply_mighty_man_event()
    for imp in result["impacts"]:
        assert "faction_name" not in imp, f"Mighty man event should not have faction_name: {imp}"

    # 天灾 — 需要已征服行省
    result = service.apply_disaster_event()
    for imp in result["impacts"]:
        assert "faction_name" not in imp, f"Disaster event should not have faction_name: {imp}"


def test_empty_events_no_faction_leakage():
    """无死者/无事件时不应产生误导性派系字段"""
    state = _state_with_player({"mortality_rules": {"event_deck": []}})
    response = mortality_api.execute_mortality_phase(state, "p1")

    assert response["success"]
    assert len(response["data"]["events"]) == 1
    event = response["data"]["events"][0]
    assert event["effect"] == "none"
    # 中性事件不应有 faction 字段
    for imp in event.get("impacts", []):
        assert "faction_name" not in imp
    # 无 impacts 时也安全
    assert len(event.get("impacts", [])) == 0
