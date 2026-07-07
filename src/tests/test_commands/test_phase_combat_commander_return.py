# src/tests/test_commands/test_phase_combat_commander_return.py

import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.entities.figure import Figure
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_combat import CombatCommand


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.turn.turn_number = 10
    state.log_event = MagicMock()
    state.get_member = MagicMock()
    return state


@pytest.fixture
def mock_war_system():
    ws = MagicMock(spec=WarSystem)
    ws.get_truce_wars_with_approved_treaty = MagicMock()
    return ws


@pytest.fixture
def mock_war():
    war = MagicMock(spec=War)
    war.id = "test_war"
    war.name = "Test War"
    war.original_commander_id = 101
    war.commander_id = 101
    war.commander_assigned_turn = 8
    war.status = WarStatus.TRUCE
    return war


@pytest.fixture
def mock_commander():
    fig = MagicMock(spec=Figure)
    fig.id = 101
    fig.name = "Test Commander"
    fig.office = "proconsul"
    fig.is_absent = True
    fig.is_dead = False
    fig.add_office_history = MagicMock()
    fig.update_influence = MagicMock()
    return fig


def test_process_commanders_returning_normal(mock_state, mock_war_system, mock_war, mock_commander):
    """测试正常返回：指挥官存活，状态正确"""
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [mock_war]
    mock_state.get_member.return_value = mock_commander

    cmd = CombatCommand(mock_state)
    cmd._process_commanders_returning(mock_war_system)

    # 验证 add_office_history 被调用
    mock_commander.add_office_history.assert_called_once_with("proconsul", 8, 9)  # 上任回合8，结束于9
    assert mock_commander.office is None
    assert mock_commander.is_absent is False
    mock_commander.update_influence.assert_called_once()

    # 验证日志记录
    mock_state.log_event.assert_called_once_with(
        f"指挥官 {mock_commander.name} 返回罗马",
        extra={'type': 'commander_return', 'figure_id': mock_commander.id, 'war_id': mock_war.id}
    )


def test_process_commanders_returning_no_commander(mock_state, mock_war_system, mock_war):
    """测试战争没有指挥官（original_commander_id 和 commander_id 均为 None）"""
    mock_war.original_commander_id = None
    mock_war.commander_id = None
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [mock_war]

    cmd = CombatCommand(mock_state)
    cmd._process_commanders_returning(mock_war_system)

    # 不应调用 get_member
    mock_state.get_member.assert_not_called()
    mock_state.log_event.assert_not_called()


def test_process_commanders_returning_commander_dead(mock_state, mock_war_system, mock_war, mock_commander):
    """测试指挥官已死亡"""
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [mock_war]
    mock_commander.is_dead = True
    mock_state.get_member.return_value = mock_commander

    cmd = CombatCommand(mock_state)
    cmd._process_commanders_returning(mock_war_system)

    # 不应调用 add_office_history
    mock_commander.add_office_history.assert_not_called()
    mock_state.log_event.assert_not_called()


def test_process_commanders_returning_not_proconsul(mock_state, mock_war_system, mock_war, mock_commander):
    """测试指挥官官职不是 proconsul/propraetor（不应处理）"""
    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [mock_war]
    mock_commander.office = "consul"  # 不应该处理
    mock_state.get_member.return_value = mock_commander

    cmd = CombatCommand(mock_state)
    cmd._process_commanders_returning(mock_war_system)

    mock_commander.add_office_history.assert_not_called()
    mock_state.log_event.assert_not_called()


def test_process_commanders_returning_multiple_wars(mock_state, mock_war_system):
    """测试多个停战战争同时处理"""
    # 创建两个战争和对应的指挥官
    war1 = MagicMock(spec=War)
    war1.id = "war1"
    war1.name = "War1"
    war1.original_commander_id = 101
    war1.commander_assigned_turn = 8

    war2 = MagicMock(spec=War)
    war2.id = "war2"
    war2.name = "War2"
    war2.original_commander_id = 102
    war2.commander_assigned_turn = 9

    mock_war_system.get_truce_wars_with_approved_treaty.return_value = [war1, war2]

    fig1 = MagicMock(spec=Figure)
    fig1.id = 101
    fig1.name = "Cmd1"
    fig1.office = "proconsul"
    fig1.is_absent = True
    fig1.is_dead = False
    fig1.add_office_history = MagicMock()
    fig1.update_influence = MagicMock()

    fig2 = MagicMock(spec=Figure)
    fig2.id = 102
    fig2.name = "Cmd2"
    fig2.office = "propraetor"
    fig2.is_absent = True
    fig2.is_dead = False
    fig2.add_office_history = MagicMock()
    fig2.update_influence = MagicMock()

    def get_member_side_effect(fid):
        if fid == 101:
            return fig1
        elif fid == 102:
            return fig2
        return None
    mock_state.get_member.side_effect = get_member_side_effect

    cmd = CombatCommand(mock_state)
    cmd._process_commanders_returning(mock_war_system)

    # 验证两个指挥官都被处理
    fig1.add_office_history.assert_called_once_with("proconsul", 8, 9)
    fig2.add_office_history.assert_called_once_with("propraetor", 9, 9)  # 结束回合9

    assert fig1.office is None
    assert fig2.office is None
    assert fig1.is_absent is False
    assert fig2.is_absent is False

    # 验证日志调用两次
    assert mock_state.log_event.call_count == 2