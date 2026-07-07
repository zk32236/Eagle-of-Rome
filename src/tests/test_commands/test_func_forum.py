# src/tests/test_commands/test_func_forum.py
"""
Forum 功能命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_forum import PersuadeCommand
from src.core.game_state import GameState
from src.core.entities.curia import Curia
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure


@pytest.fixture
def mock_state():
    """模拟 GameState，包含 curia 和 factions"""
    state = MagicMock(spec=GameState)
    state.curia = MagicMock(spec=Curia)
    state.factions = {}
    return state


@pytest.fixture
def mock_figure():
    """模拟人物"""
    figure = MagicMock(spec=Figure)
    figure.id = 123
    figure.get_formal_name.return_value = "Marcus Brutus"
    return figure


def test_persuade_success(mock_state, mock_figure):
    """成功说服人物加入玩家派系"""
    # 设置 Curia 返回人物
    mock_state.curia.remove_figure.return_value = mock_figure

    # 设置玩家派系
    player_faction = MagicMock(spec=Faction)
    player_faction.is_player = True
    player_faction.id = "player"
    player_faction.name = "玩家派系"
    player_faction.member_ids = []
    mock_state.factions = {"player": player_faction}

    cmd = PersuadeCommand(mock_state)
    result = cmd.execute(["123"])

    assert result is True
    mock_state.curia.remove_figure.assert_called_once_with(123)
    assert mock_figure.faction_id == "player"
    assert 123 in player_faction.member_ids


def test_persuade_invalid_id(mock_state):
    """传入非数字参数应返回 False"""
    cmd = PersuadeCommand(mock_state)
    result = cmd.execute(["abc"])
    assert result is False
    mock_state.curia.remove_figure.assert_not_called()


def test_persuade_figure_not_in_curia(mock_state):
    """人物不在 Curia 中"""
    mock_state.curia.remove_figure.return_value = None

    cmd = PersuadeCommand(mock_state)
    result = cmd.execute(["123"])

    assert result is False
    mock_state.curia.remove_figure.assert_called_once_with(123)


def test_persuade_no_player_faction(mock_state, mock_figure):
    """没有玩家派系"""
    mock_state.curia.remove_figure.return_value = mock_figure
    mock_state.factions = {}  # 无玩家派系

    cmd = PersuadeCommand(mock_state)
    result = cmd.execute(["123"])

    assert result is False
    mock_state.curia.remove_figure.assert_called_once_with(123)
    # 验证人物被放回 Curia
    mock_state.curia.add_figure.assert_called_once_with(mock_figure)


def test_persuade_wrong_args_count(mock_state):
    """参数个数错误"""
    cmd = PersuadeCommand(mock_state)
    result = cmd.execute([])  # 无参数
    assert result is False

    result = cmd.execute(["123", "extra"])  # 多余参数
    assert result is False
    mock_state.curia.remove_figure.assert_not_called()