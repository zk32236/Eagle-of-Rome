# src/tests/test_commands/test_phase_combat_peace.py

import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.entities.figure import Figure
from src.ui.commands.phase_combat import CombatCommand
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.deciders.peace_treaty_decider import PeaceTreatyDecider
from src.core.localization import TerminologyService


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.turn.turn_number = 10
    state.log_event = MagicMock()
    return state


@pytest.fixture
def mock_war_system():
    ws = MagicMock(spec=WarSystem)
    ws.enter_truce = MagicMock(return_value=True)
    return ws


@pytest.fixture
def war():
    war = War(id='test_war', name='测试战争', strength=5)
    war.duration = 2
    war.commander_id = 101
    war._commander_assigned_turn = 8
    return war


def test_victory_generates_treaty(mock_state, mock_war_system, war):
    """测试 VICTORY 结果生成草案"""
    mock_decider = MagicMock(spec=PeaceTreatyDecider)
    expected_treaty = {
        'indemnity': 60,
        'duration': 5,
        'generated_turn': 10
    }
    mock_decider.decide_treaty.return_value = expected_treaty

    cmd = CombatCommand(mock_state, peace_treaty_decider=mock_decider)
    result = 'VICTORY'
    terms = TerminologyService.get()

    # 直接调用草案生成方法
    cmd._maybe_generate_treaty(mock_war_system, war, result, terms)

    # 验证 enter_truce 被正确调用
    mock_war_system.enter_truce.assert_called_once_with(war, expected_treaty)

    # 验证日志记录
    mock_state.log_event.assert_called_once_with(
        f"战争 {war.name} 生成停战草案，赔款 {expected_treaty['indemnity']}，有效期 {expected_treaty['duration']} 回合",
        extra={
            'type': 'peace_treaty_generated',
            'war_id': war.id,
            'result': result,
            'indemnity': expected_treaty['indemnity'],
            'duration': expected_treaty['duration'],
            'generated_turn': expected_treaty['generated_turn']
        }
    )


def test_triumph_no_treaty(mock_state, mock_war_system, war):
    """测试 TRIUMPH 不生成草案"""
    mock_decider = MagicMock(spec=PeaceTreatyDecider)
    cmd = CombatCommand(mock_state, peace_treaty_decider=mock_decider)
    result = 'TRIUMPH'
    terms = TerminologyService.get()

    cmd._maybe_generate_treaty(mock_war_system, war, result, terms)

    mock_decider.decide_treaty.assert_not_called()
    mock_war_system.enter_truce.assert_not_called()
    mock_state.log_event.assert_not_called()


def test_stalemate_generates_treaty(mock_state, mock_war_system, war):
    """测试 STALEMATE 生成草案"""
    mock_decider = MagicMock(spec=PeaceTreatyDecider)
    expected_treaty = {
        'indemnity': 0,
        'duration': 3,
        'generated_turn': 10
    }
    mock_decider.decide_treaty.return_value = expected_treaty

    cmd = CombatCommand(mock_state, peace_treaty_decider=mock_decider)
    result = 'STALEMATE'
    terms = TerminologyService.get()

    cmd._maybe_generate_treaty(mock_war_system, war, result, terms)

    mock_war_system.enter_truce.assert_called_once_with(war, expected_treaty)


def test_enter_truce_failure_logs_warning(mock_state, mock_war_system, war):
    """测试 enter_truce 失败时记录警告"""
    mock_war_system.enter_truce.return_value = False

    mock_decider = MagicMock(spec=PeaceTreatyDecider)
    expected_treaty = {
        'indemnity': 60,
        'duration': 5,
        'generated_turn': 10
    }
    mock_decider.decide_treaty.return_value = expected_treaty

    cmd = CombatCommand(mock_state, peace_treaty_decider=mock_decider)
    result = 'VICTORY'
    terms = TerminologyService.get()

    cmd._maybe_generate_treaty(mock_war_system, war, result, terms)

    # 验证警告日志被记录
    mock_state.log_event.assert_called_once_with(
        f"战争 {war.name} 草案生成失败：无法进入停战",
        extra={'type': 'peace_treaty_failed', 'war_id': war.id},
        level=30  # logging.WARNING
    )