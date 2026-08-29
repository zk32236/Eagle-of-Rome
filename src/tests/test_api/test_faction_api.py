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
    """get_faction_style_map() 返回完整 map：六阵营全名键 + G2-B hex + fallback（F-F-01）"""
    state = GameState.create_for_testing({
        "faction_style_map": {
            "optimates": {"color": "#C62828", "name": "Optimates", "id_display": "Opt", "order": 1},
            "populares": {"color": "#1565C0", "name": "Populares", "id_display": "Pop", "order": 2},
            "equites": {"color": "#E65100", "name": "Equites", "id_display": "Equ", "order": 3},
            "f4": {"color": "#6A1B9A", "name": "第四派系", "id_display": "F4", "order": 4},
            "f5": {"color": "#00695C", "name": "第五派系", "id_display": "F5", "order": 5},
            "f6": {"color": "#AD1457", "name": "第六派系", "id_display": "F6", "order": 6},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
    })
    for fid, fname in [
        ("optimates", "Optimates"),
        ("populares", "Populares"),
        ("equites", "Equites"),
        ("f4", "第四派系"),
        ("f5", "第五派系"),
        ("f6", "第六派系"),
    ]:
        state.add_faction(Faction(id=fid, name=fname))

    result = faction_api.get_faction_style_map(state)

    assert result["success"] is True
    data = result["data"]
    assert "map" in data
    assert "fallback" in data
    assert len(data["map"]) == 6
    expected = {
        "optimates": ("#C62828", "Optimates", "Opt", 1),
        "populares": ("#1565C0", "Populares", "Pop", 2),
        "equites": ("#E65100", "Equites", "Equ", 3),
        "f4": ("#6A1B9A", "第四派系", "F4", 4),
        "f5": ("#00695C", "第五派系", "F5", 5),
        "f6": ("#AD1457", "第六派系", "F6", 6),
    }
    for fid, (color, name, id_display, order) in expected.items():
        assert data["map"][fid]["color"] == color
        assert data["map"][fid]["name"] == name
        assert data["map"][fid]["id_display"] == id_display
        assert data["map"][fid]["order"] == order
    # fallback
    assert data["fallback"]["color"] == "#3A3530"
    assert data["fallback"]["name"] == "未知派系"
    assert data["fallback"]["id_display"] == "?"
    assert data["default_unknown_color"] == "#3A3530"


def test_get_faction_style_map_unknown_faction_fallback():
    """未知 faction_id（第 7 id，不在 style_map 中）→ 使用 fallback 颜色 #3A3530（R-02）"""
    state = GameState.create_for_testing({
        "faction_style_map": {
            "optimates": {"color": "#C62828", "name": "Optimates", "id_display": "Opt", "order": 1},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
    })
    opt = Faction(id="optimates", name="Optimates")
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