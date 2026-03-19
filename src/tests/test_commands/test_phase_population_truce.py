import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.ui.commands.phase_population import PopulationCommand

class SimpleTurn:
    def __init__(self, num):
        self.turn_number = num

@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.turn.turn_number = 10
    state.log_event = MagicMock()
    return state


@pytest.fixture
def mock_war_system():
    ws = MagicMock()
    ws.get_war_by_commander = MagicMock()
    return ws


def test_convert_consul_to_proconsul(mock_state, mock_war_system):
    figure = Figure(id=101, name='Test Consul')
    figure.is_absent = True
    figure.office = 'consul'
    figure.add_office_history = MagicMock()
    figure.update_influence = MagicMock()
    mock_state.turn = SimpleTurn(10)  # 使用简单对象
    mock_state.get_living_members.return_value = [figure]
    mock_state.get_war_system.return_value = mock_war_system
    # 不需要 mock_state.log_event，因为核心逻辑已测试

    war = War(id='war1', name='Test War')
    war._commander_assigned_turn = 8
    mock_war_system.get_war_by_commander.return_value = war

    cmd = PopulationCommand(mock_state)
    cmd._convert_battlefield_commanders()

    figure.add_office_history.assert_called_once_with('consul', 8, 9)
    assert figure.office == 'proconsul'
    figure.update_influence.assert_called_once()


def test_convert_praetor_to_propraetor(mock_state, mock_war_system):
    """测试大法官转为 propraetor"""
    figure = Figure(id=102, name='Test Praetor')
    figure.is_absent = True
    figure.office = 'praetor'
    figure.add_office_history = MagicMock()
    figure.update_influence = MagicMock()

    mock_state.get_living_members.return_value = [figure]
    mock_state.get_war_system.return_value = mock_war_system

    war = War(id='war2', name='Test War')
    war._commander_assigned_turn = 7
    mock_war_system.get_war_by_commander.return_value = war

    cmd = PopulationCommand(mock_state)
    cmd._convert_battlefield_commanders()

    figure.add_office_history.assert_called_once_with('praetor', 7, 9)
    assert figure.office == 'propraetor'
    figure.update_influence.assert_called_once()


# test_commands/test_phase_population_truce.py

from src.core.entities.figure import Figure

# test_commands/test_phase_population_truce.py

def test_no_war_found_uses_default_turn(mock_state, mock_war_system):
    figure = Figure(id=103, name='Test Commander')
    figure.is_absent = True
    figure.office = 'consul'
    figure.office_history = []  # 清空历史

    mock_state.turn = SimpleTurn(10)
    mock_state.get_living_members.return_value = [figure]
    mock_state.get_war_system.return_value = mock_war_system
    mock_war_system.get_war_by_commander.return_value = None

    cmd = PopulationCommand(mock_state)
    with patch('logging.warning'):
        cmd._convert_battlefield_commanders()

    # 验证历史官职已添加
    assert len(figure.office_history) == 1
    term = figure.office_history[0]
    assert term.office_type == 'consul'
    assert term.start_turn == 9
    assert term.end_turn == 9
    # 验证官职已转换
    assert figure.office == 'proconsul'

def test_ignores_non_absent_or_wrong_office(mock_state, mock_war_system):
    mock_state.turn = SimpleTurn(10)

    figures = [
        Figure(id=1, name='A', is_absent=False, office='consul'),
        Figure(id=2, name='B', is_absent=True, office='quaestor'),
        Figure(id=3, name='C', is_absent=True, office='consul'),
    ]
    for f in figures:
        f.office_history = []  # 清空历史

    mock_state.get_living_members.return_value = figures
    mock_state.get_war_system.return_value = mock_war_system
    mock_war_system.get_war_by_commander.return_value = None

    cmd = PopulationCommand(mock_state)
    cmd._convert_battlefield_commanders()

    assert figures[0].office == 'consul'   # 未变
    assert figures[1].office == 'quaestor' # 未变
    assert figures[2].office == 'proconsul' # 已变
    assert len(figures[2].office_history) == 1
    term = figures[2].office_history[0]
    assert term.office_type == 'consul'
    assert term.start_turn == 9
    assert term.end_turn == 9