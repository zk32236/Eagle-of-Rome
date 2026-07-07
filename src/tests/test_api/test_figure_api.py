# src/tests/test_api/test_figure_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import figure_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.turn.turn_number = 5
    state.turn.year = -260
    return state


@pytest.fixture
def sample_figure():
    figure = MagicMock(spec=Figure)
    figure.id = 1
    figure.get_formal_name.return_value = "Gaius Julius"
    figure.is_faction_leader = False
    figure.class_tier = ClassTier.NOBILE
    figure.faction_id = "optimates"
    figure.influence = 50
    figure.wealth = 100
    figure.popularity = 10
    figure.land_private = 5
    figure.veterans = 2
    figure.office = "consul"
    figure.rank = 4
    figure.zeal = 3
    figure.charisma = 4
    figure.martial = 5
    figure.intelligence = 6
    figure.age = 45
    figure.nomen = "Julius"
    figure.family_prestige = 3
    figure.is_dead = False
    figure.is_absent = False
    figure.office_history = []
    figure.contract_ids = []
    figure.get_office_influence_bonus.return_value = 20
    return figure


@pytest.fixture
def sample_faction():
    faction = MagicMock(spec=Faction)
    faction.id = "optimates"
    faction.name = "Optimates"
    return faction


def test_get_figure_info_with_id_success(mock_state, sample_figure, sample_faction):
    mock_state.get_member.return_value = sample_figure
    mock_state.get_faction.return_value = sample_faction
    result = figure_api.get_figure_info(mock_state, figure_id=1)
    assert result["success"] is True
    assert "人物详细信息" in result["message"]
    assert result["data"]["id"] == 1
    assert result["data"]["name"] == "Gaius Julius"


def test_get_figure_info_with_id_not_found(mock_state):
    mock_state.get_member.return_value = None
    result = figure_api.get_figure_info(mock_state, figure_id=999)
    assert result["success"] is False
    assert "不存在或已死亡" in result["message"]


def test_get_figure_info_with_id_dead(mock_state, sample_figure):
    sample_figure.is_dead = True
    mock_state.get_member.return_value = sample_figure
    result = figure_api.get_figure_info(mock_state, figure_id=1)
    assert result["success"] is False


def test_get_figure_info_no_id_no_living(mock_state):
    mock_state.get_living_members.return_value = []
    result = figure_api.get_figure_info(mock_state)
    assert result["success"] is True
    assert "无存活人物" in result["message"]
    assert result["data"] == []


def test_get_figure_info_no_id_with_living(mock_state, sample_figure, sample_faction):
    mock_state.get_living_members.return_value = [sample_figure]
    mock_state.get_faction.return_value = sample_faction
    result = figure_api.get_figure_info(mock_state)
    assert result["success"] is True
    assert "存活人物列表" in result["message"]
    assert len(result["data"]) == 1


def test_get_private_land_info_no_landowners(mock_state):
    mock_state.get_living_members.return_value = []
    result = figure_api.get_private_land_info(mock_state)
    assert result["success"] is True
    assert "无拥有土地的人物" in result["message"]
    assert result["data"]["landowners"] == []


def test_get_private_land_info_with_landowners(mock_state, sample_figure):
    sample_figure.land_private = 5
    sample_figure.wealth = 100
    mock_state.get_living_members.return_value = [sample_figure]
    mock_state.get_economic_rule.side_effect = lambda key, default: {
        "land_price_per_unit": 10,
        "private_land_income_rate": 0.05
    }.get(key, default)
    result = figure_api.get_private_land_info(mock_state)
    assert result["success"] is True
    assert len(result["data"]["landowners"]) == 1
    assert result["data"]["landowners"][0]["land_private"] == 5
    assert result["data"]["totals"]["land"] == 5