# src/tests/test_commands/test_func_land.py
"""
土地交易功能命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_land import TradeCommand, LandCommand
from src.core.game_state import GameState
from src.core.service.land_trading_service import LandTradingService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.get_living_members.return_value = []
    state.factions = {}
    state.get_faction = MagicMock()
    return state


@pytest.fixture
def mock_service(mock_state):
    with patch('src.ui.commands.func_land.LandTradingService') as MockService:
        service = MockService.return_value
        service.execute_trade.return_value = (True, "Trade successful")
        service.get_trade_preview.return_value = {
            'seller_name': 'Seller',
            'buyer_name': 'Buyer',
            'price_per_unit': 10,
            'seller_land_after': 5,
            'buyer_land_after': 3,
            'can_execute': True
        }
        yield service


# ========== TradeCommand ==========

def test_trade_success(mock_state, mock_service):
    cmd = TradeCommand(mock_state)
    result = cmd.execute(["land", "1", "2", "5"])
    assert result is True
    mock_service.execute_trade.assert_called_once_with(1, 2, 5)


def test_trade_invalid_args_count(mock_state):
    cmd = TradeCommand(mock_state)
    result = cmd.execute([])
    assert result is False
    result = cmd.execute(["land", "1", "2"])
    assert result is False
    result = cmd.execute(["land", "1", "2", "5", "extra"])
    assert result is False


def test_trade_wrong_subcommand(mock_state):
    cmd = TradeCommand(mock_state)
    result = cmd.execute(["sell", "1", "2", "5"])
    assert result is False


def test_trade_invalid_ids(mock_state):
    cmd = TradeCommand(mock_state)
    result = cmd.execute(["land", "abc", "2", "5"])
    assert result is False
    result = cmd.execute(["land", "1", "xyz", "5"])
    assert result is False
    result = cmd.execute(["land", "1", "2", "abc"])
    assert result is False


def test_trade_non_positive_amount(mock_state):
    cmd = TradeCommand(mock_state)
    result = cmd.execute(["land", "1", "2", "0"])
    assert result is False
    result = cmd.execute(["land", "1", "2", "-5"])
    assert result is False


def test_trade_failure(mock_state, mock_service):
    mock_service.execute_trade.return_value = (False, "Trade failed")
    cmd = TradeCommand(mock_state)
    result = cmd.execute(["land", "1", "2", "5"])
    assert result is False


# ========== LandCommand ==========

def test_land_price_success(mock_state, mock_service):
    cmd = LandCommand(mock_state)
    result = cmd.execute(["price", "1", "2"])
    assert result is True
    mock_service.get_trade_preview.assert_called_once_with(1, 2, 1)


def test_land_price_invalid_args_count(mock_state):
    cmd = LandCommand(mock_state)
    result = cmd.execute([])
    assert result is False
    result = cmd.execute(["price", "1"])
    assert result is False
    result = cmd.execute(["price", "1", "2", "extra"])
    assert result is False


def test_land_price_wrong_subcommand(mock_state):
    cmd = LandCommand(mock_state)
    result = cmd.execute(["estimate", "1", "2"])
    assert result is False


def test_land_price_invalid_ids(mock_state):
    cmd = LandCommand(mock_state)
    result = cmd.execute(["price", "abc", "2"])
    assert result is False
    result = cmd.execute(["price", "1", "xyz"])
    assert result is False


def test_land_price_preview_none(mock_state, mock_service):
    mock_service.get_trade_preview.return_value = None
    cmd = LandCommand(mock_state)
    result = cmd.execute(["price", "1", "2"])
    assert result is False


