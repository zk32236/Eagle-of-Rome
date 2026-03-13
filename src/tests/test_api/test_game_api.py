# src/tests/test_api/test_game_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import game_api
from src.core.entities.entities import GameTurn

@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.treasury = 1000
    state.get_living_members.return_value = [MagicMock() for _ in range(5)]
    state.factions = {"f1": MagicMock(), "f2": MagicMock()}
    state.turn = MagicMock(spec=GameTurn)
    state.turn.year = -264
    state.turn.turn_number = 10
    state.get_economic_rule.side_effect = lambda key, default: {
        "land_price_per_unit": 10,
        "national_public_land_tax_rate": 0.02
    }.get(key, default)
    state.get_national_public_land.return_value = 1000
    return state

def test_get_status_summary(mock_state):
    result = game_api.get_status_summary(mock_state)
    assert result["success"] is True
    assert "📊 游戏状态摘要" in result["message"]
    assert "国库: 1000 塔兰特" in result["message"]
    assert "存活人物: 5 人" in result["message"]
    assert "派系数: 2 个" in result["message"]
    assert result["data"]["treasury"] == 1000

def test_get_public_land_info(mock_state):
    result = game_api.get_public_land_info(mock_state)
    assert result["success"] is True
    assert "🏞️ 国家公地信息" in result["message"]
    assert "公地数量: 1000 C" in result["message"]
    assert "年收益: 200 Talents" in result["message"]  # 1000*10*0.02 = 200
    assert result["data"]["national_land"] == 1000