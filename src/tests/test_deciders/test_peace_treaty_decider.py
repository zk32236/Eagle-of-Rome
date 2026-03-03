import pytest
from unittest.mock import MagicMock
from src.core.entities.war import War
from src.core.game_state import GameState
from src.core.deciders.impl.auto_peace_treaty_decider import AutoPeaceTreatyDecider

@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.config.get.return_value = {
        "indemnity_base_multiplier": 10,
        "indemnity_duration_multiplier": 5,
        "duration_victory": 5,
        "duration_stalemate": 3
    }
    state.turn.turn_number = 10
    return state

@pytest.fixture
def war():
    war = War(id='test', name='Test War', strength=8)
    war.duration = 2
    return war

def test_victory_treaty(war, mock_state):
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'VICTORY', mock_state)
    assert treaty is not None
    # 预期赔款 = 8*10 + 2*5 = 80 + 10 = 90
    assert treaty['indemnity'] == 90
    assert treaty['duration'] == 5
    assert treaty['generated_turn'] == 10

def test_defeat_treaty(war, mock_state):
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'DEFEAT', mock_state)
    assert treaty is not None
    assert treaty['indemnity'] == -90
    assert treaty['duration'] == 5

def test_stalemate_treaty(war, mock_state):
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'STALEMATE', mock_state)
    assert treaty is not None
    assert treaty['indemnity'] == 0
    assert treaty['duration'] == 3

def test_triumph_no_treaty(war, mock_state):
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'TRIUMPH', mock_state)
    assert treaty is None

def test_disaster_no_treaty(war, mock_state):
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'DISASTER', mock_state)
    assert treaty is None

def test_config_override():
    state = MagicMock(spec=GameState)
    # 模拟自定义配置
    custom_config = {
        "indemnity_base_multiplier": 5,
        "indemnity_duration_multiplier": 2,
        "duration_victory": 3,
        "duration_stalemate": 1
    }
    state.config.get.return_value = custom_config
    state.turn.turn_number = 15
    war = War(id='test', name='Test', strength=10)
    war.duration = 3
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, 'VICTORY', state)
    # 预期赔款 = 10*5 + 3*2 = 50 + 6 = 56
    assert treaty['indemnity'] == 56
    assert treaty['duration'] == 3