# src/tests/test_commands/test_func_population.py
"""
Population 功能命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_population import FestivalCommand
from src.core.game_state import GameState
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure


@pytest.fixture
def mock_state():
    """模拟 GameState"""
    state = MagicMock(spec=GameState)
    state.factions = {}
    return state


@pytest.fixture
def mock_figure():
    """模拟人物"""
    figure = MagicMock(spec=Figure)
    figure.id = 123
    figure.faction_id = "player"
    figure.wealth = 100
    figure.popularity = 50
    figure.is_dead = False
    figure.get_formal_name.return_value = "Marcus Brutus"
    return figure


@pytest.fixture
def player_faction():
    """模拟玩家派系"""
    faction = MagicMock(spec=Faction)
    faction.is_player = True
    faction.id = "player"
    faction.name = "玩家派系"
    return faction


def test_festival_success(mock_state, mock_figure, player_faction):
    """成功举办庆典"""
    mock_state.get_member.return_value = mock_figure
    mock_state.factions = {"player": player_faction}

    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "50"])

    assert result is True
    mock_state.get_member.assert_called_once_with(123)
    assert mock_figure.wealth == 50  # 100 - 50
    mock_figure.add_popularity.assert_called_once_with(50)


def test_festival_invalid_args_count(mock_state):
    """参数个数错误"""
    cmd = FestivalCommand(mock_state)
    result = cmd.execute([])  # 无参数
    assert result is False
    result = cmd.execute(["123"])  # 少一个参数
    assert result is False
    result = cmd.execute(["123", "50", "extra"])  # 多一个参数
    assert result is False


def test_festival_invalid_arg_type(mock_state):
    """参数类型错误"""
    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["abc", "50"])
    assert result is False
    result = cmd.execute(["123", "xyz"])
    assert result is False


def test_festival_negative_amount(mock_state):
    """金额为负"""
    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "-10"])
    assert result is False


def test_festival_figure_not_found(mock_state):
    """人物不存在"""
    mock_state.get_member.return_value = None
    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["999", "50"])
    assert result is False
    mock_state.get_member.assert_called_once_with(999)


def test_festival_figure_dead(mock_state, mock_figure):
    """人物已死亡"""
    mock_figure.is_dead = True
    mock_state.get_member.return_value = mock_figure

    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "50"])
    assert result is False


def test_festival_no_player_faction(mock_state, mock_figure):
    """没有玩家派系"""
    mock_state.get_member.return_value = mock_figure
    mock_state.factions = {}  # 无派系

    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "50"])
    assert result is False


def test_festival_figure_not_in_player_faction(mock_state, mock_figure, player_faction):
    """人物不属于玩家派系"""
    mock_figure.faction_id = "other"
    mock_state.get_member.return_value = mock_figure
    mock_state.factions = {"player": player_faction}

    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "50"])
    assert result is False


def test_festival_insufficient_wealth(mock_state, mock_figure, player_faction):
    """财富不足"""
    mock_figure.wealth = 30
    mock_state.get_member.return_value = mock_figure
    mock_state.factions = {"player": player_faction}

    cmd = FestivalCommand(mock_state)
    result = cmd.execute(["123", "50"])
    assert result is False
    # 确保没有修改财富和人气
    assert mock_figure.wealth == 30
    mock_figure.add_popularity.assert_not_called()