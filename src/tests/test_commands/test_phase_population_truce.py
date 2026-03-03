import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.ui.commands.phase_population import PopulationCommand


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
    """测试执政官转为 proconsul"""
    figure = Figure(id=101, name='Test Consul')
    figure.is_absent = True
    figure.office = 'consul'
    figure.add_office_history = MagicMock()
    figure.update_influence = MagicMock()

    mock_state.get_living_members.return_value = [figure]
    mock_state.get_war_system.return_value = mock_war_system

    war = War(id='war1', name='Test War')
    war._commander_assigned_turn = 8
    mock_war_system.get_war_by_commander.return_value = war

    cmd = PopulationCommand(mock_state)
    cmd._convert_battlefield_commanders()

    # 验证历史记录
    figure.add_office_history.assert_called_once_with('consul', 8, 9)
    # 验证官职变更
    assert figure.office == 'proconsul'
    figure.update_influence.assert_called_once()
    mock_state.log_event.assert_called()


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


def test_no_war_found_uses_default_turn(mock_state, mock_war_system):
    """找不到战争时使用默认上任回合"""
    figure = Figure(id=103, name='Test Commander')
    figure.is_absent = True
    figure.office = 'consul'
    figure.add_office_history = MagicMock()
    figure.update_influence = MagicMock()

    mock_state.get_living_members.return_value = [figure]
    mock_state.get_war_system.return_value = mock_war_system
    mock_war_system.get_war_by_commander.return_value = None  # 找不到战争

    cmd = PopulationCommand(mock_state)
    with patch('logging.warning'):  # 避免日志污染
        cmd._convert_battlefield_commanders()

    # 应使用当前回合-1作为上任回合
    figure.add_office_history.assert_called_once_with('consul', 9, 9)
    assert figure.office == 'proconsul'
    figure.update_influence.assert_called_once()

    # 验证警告日志被记录（至少一次）
    mock_state.log_event.assert_any_call(
        f"警告：战场指挥官 {figure.name} 找不到指挥的战争，使用默认上任回合",
        extra={'type': 'truce_conversion_warning', 'figure_id': figure.id},
        level=30
    )
    # 验证转换成功日志也被记录（至少一次）
    mock_state.log_event.assert_any_call(
        f"战场指挥官 {figure.name} 转为 proconsul",
        extra={
            'type': 'commander_conversion',
            'figure_id': figure.id,
            'old_office': 'consul',
            'new_office': 'proconsul',
            'assigned_turn': 9
        }
    )


def test_ignores_non_absent_or_wrong_office(mock_state, mock_war_system):
    """忽略不在战场或官职不符的人物"""
    figures = [
        Figure(id=1, name='A', is_absent=False, office='consul'),  # 不在战场
        Figure(id=2, name='B', is_absent=True, office='quaestor'),  # 官职不符
        Figure(id=3, name='C', is_absent=True, office='consul'),    # 应转换
    ]
    for f in figures:
        f.add_office_history = MagicMock()
        f.update_influence = MagicMock()

    mock_state.get_living_members.return_value = figures
    mock_state.get_war_system.return_value = mock_war_system
    mock_war_system.get_war_by_commander.return_value = None

    cmd = PopulationCommand(mock_state)
    cmd._convert_battlefield_commanders()

    # 只有 id=3 的被转换
    assert figures[0].office == 'consul'   # 未变
    assert figures[1].office == 'quaestor' # 未变
    assert figures[2].office == 'proconsul' # 已变

    figures[2].add_office_history.assert_called_once()
    figures[2].update_influence.assert_called_once()
    figures[0].add_office_history.assert_not_called()
    figures[1].add_office_history.assert_not_called()