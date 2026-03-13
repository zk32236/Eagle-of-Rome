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