# src/tests/test_commands/test_phase_resolution_truce.py

import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_resolution import ResolutionCommand


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.turn.turn_number = 10
    state.log_event = MagicMock()
    return state


@pytest.fixture
def mock_war_system():
    ws = MagicMock(spec=WarSystem)
    ws.get_truce_wars_with_approved_treaty = MagicMock()
    ws._move_to_threat = MagicMock()
    return ws


def create_mock_war(war_id, name, expired):
    """创建模拟战争，根据expired决定is_truce_expired返回值"""
    war = MagicMock(spec=War)
    war.id = war_id
    war.name = name
    war.is_truce_expired = MagicMock(return_value=expired)
    war.clear_peace_treaty = MagicMock()
    return war


def test_truce_expired_single_war(mock_state, mock_war_system):
    """测试单个战争到期"""
    war = create_mock_war('w1', 'Test War', expired=True)
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [war]
    mock_state.get_war_system.return_value = mock_war_system

    cmd = ResolutionCommand(mock_state)
    cmd._check_truce_expiry()

    # 验证战争被移到威胁列表
    mock_war_system._move_to_threat.assert_called_once_with(war, threat_level=1)
    # 验证清除草案
    war.clear_peace_treaty.assert_called_once()
    # 验证日志
    mock_state.log_event.assert_called_once_with(
        f"{war.name} 和约到期，重启威胁",
        extra={'type': 'truce_expired', 'war_id': war.id}
    )


def test_truce_not_expired_single_war(mock_state, mock_war_system):
    """测试单个战争未到期"""
    war = create_mock_war('w1', 'Test War', expired=False)
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [war]
    mock_state.get_war_system.return_value = mock_war_system

    cmd = ResolutionCommand(mock_state)
    cmd._check_truce_expiry()

    mock_war_system._move_to_threat.assert_not_called()
    war.clear_peace_treaty.assert_not_called()
    mock_state.log_event.assert_not_called()


def test_truce_mixed_expiry(mock_state, mock_war_system):
    """测试多个战争，部分到期部分未到期"""
    war1 = create_mock_war('w1', 'War1', expired=True)
    war2 = create_mock_war('w2', 'War2', expired=False)
    war3 = create_mock_war('w3', 'War3', expired=True)
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [war1, war2, war3]
    mock_state.get_war_system.return_value = mock_war_system

    cmd = ResolutionCommand(mock_state)
    cmd._check_truce_expiry()

    # 只有 war1 和 war3 应被处理
    assert mock_war_system._move_to_threat.call_count == 2
    mock_war_system._move_to_threat.assert_any_call(war1, threat_level=1)
    mock_war_system._move_to_threat.assert_any_call(war3, threat_level=1)
    war1.clear_peace_treaty.assert_called_once()
    war3.clear_peace_treaty.assert_called_once()
    war2.clear_peace_treaty.assert_not_called()

    # 日志应调用两次
    assert mock_state.log_event.call_count == 2


def test_no_truce_wars(mock_state, mock_war_system):
    """测试没有停战战争"""
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = []
    mock_state.get_war_system.return_value = mock_war_system

    cmd = ResolutionCommand(mock_state)
    cmd._check_truce_expiry()

    mock_war_system._move_to_threat.assert_not_called()
    mock_state.log_event.assert_not_called()