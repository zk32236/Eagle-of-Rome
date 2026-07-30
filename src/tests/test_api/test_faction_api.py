# src/tests/test_api/test_faction_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import faction_api
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    return state


@pytest.fixture
def sample_faction():
    faction = MagicMock(spec=Faction)
    faction.id = "optimates"
    faction.name = "Optimates"
    faction.treasury = 100
    faction.is_player = True
    return faction


@pytest.fixture
def sample_member():
    member = MagicMock(spec=Figure)
    member.influence = 50
    return member


def test_get_factions_status_no_factions(mock_state):
    mock_state.factions = {}
    result = faction_api.get_factions_status(mock_state)
    assert result["success"] is True
    assert "无派系" in result["message"]
    assert result["data"] == []


def test_get_factions_status_with_factions(mock_state, sample_faction, sample_member):
    mock_state.factions = {"optimates": sample_faction}
    sample_faction.get_members.return_value = [sample_member, sample_member]
    result = faction_api.get_factions_status(mock_state)
    assert result["success"] is True
    assert "派系状态一览" in result["message"]
    data = result["data"]
    assert len(data) == 1
    assert data[0]["id"] == "optimates"
    assert data[0]["member_count"] == 2
    assert data[0]["total_influence"] == 100
    assert data[0]["avg_influence"] == 50
    assert data[0]["is_player"] is True


def test_get_factions_status_empty_faction(mock_state, sample_faction):
    mock_state.factions = {"optimates": sample_faction}
    sample_faction.get_members.return_value = []
    result = faction_api.get_factions_status(mock_state)
    assert result["success"] is True
    assert "派系无人" in result["message"]
    data = result["data"]
    assert data[0]["member_count"] == 0
    assert data[0]["total_influence"] == 0
    assert data[0]["avg_influence"] == 0


# ── get_faction_style_map 测试 ──


def test_get_faction_style_map_returns_complete_map():
    """get_faction_style_map() 返回完整 map：包含所有派系及 fallback"""
    state = GameState.create_for_testing({
        "faction_style_map": {
            "opt": {"color": "#8B0000", "name": "Optimates", "id_display": "Opt", "order": 1},
            "pop": {"color": "#006400", "name": "Populares", "id_display": "Pop", "order": 2},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
    })
    opt = Faction(id="opt", name="Optimates")
    pop = Faction(id="pop", name="Populares")
    state.add_faction(opt)
    state.add_faction(pop)

    result = faction_api.get_faction_style_map(state)

    assert result["success"] is True
    data = result["data"]
    assert "map" in data
    assert "fallback" in data
    assert len(data["map"]) == 2
    # opt
    assert data["map"]["opt"]["color"] == "#8B0000"
    assert data["map"]["opt"]["name"] == "Optimates"
    assert data["map"]["opt"]["id_display"] == "Opt"
    assert data["map"]["opt"]["order"] == 1
    # pop
    assert data["map"]["pop"]["color"] == "#006400"
    assert data["map"]["pop"]["name"] == "Populares"
    assert data["map"]["pop"]["id_display"] == "Pop"
    assert data["map"]["pop"]["order"] == 2
    # fallback
    assert data["fallback"]["color"] == "#3A3530"
    assert data["fallback"]["name"] == "未知派系"
    assert data["fallback"]["id_display"] == "?"
    assert data["default_unknown_color"] == "#3A3530"


def test_get_faction_style_map_unknown_faction_fallback():
    """未知 faction_id（不在 style_map 中）→ 使用 fallback 颜色，保留 faction.name"""
    state = GameState.create_for_testing({
        "faction_style_map": {
            "opt": {"color": "#8B0000", "name": "Optimates", "id_display": "Opt", "order": 1},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
    })
    opt = Faction(id="opt", name="Optimates")
    xyz = Faction(id="xyz", name="Rebels")
    state.add_faction(opt)
    state.add_faction(xyz)

    result = faction_api.get_faction_style_map(state)

    data = result["data"]
    assert len(data["map"]) == 2
    # xyz 不在 style_map → fallback color, 保留 name
    assert data["map"]["xyz"]["color"] == "#3A3530"  # fallback color
    assert data["map"]["xyz"]["name"] == "Rebels"    # faction.name
    assert data["map"]["xyz"]["id_display"] == "Rebels"  # faction.name
    assert data["map"]["xyz"]["order"] == 99  # default order