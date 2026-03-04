import pytest
from unittest.mock import MagicMock
from src.core.game_state import GameState
from src.core.entities.war import War
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_revenue import RevenueCommand

@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.treasury = 100
    state.add_treasury = MagicMock(side_effect=lambda x: setattr(state, 'treasury', state.treasury + x))
    state.log_event = MagicMock()
    return state

@pytest.fixture
def mock_war_system():
    ws = MagicMock(spec=WarSystem)
    ws._war_deck = []
    ws._war_discard = []
    ws._active_wars = []
    ws._threats = []
    ws._truce_wars = []
    return ws

def test_indemnity_income(mock_state, mock_war_system):
    war = War(id='w1', name='Test War')
    war.set_indemnity_due(50)
    mock_war_system._active_wars = [war]  # 放在任一列表
    mock_state.get_war_system.return_value = mock_war_system

    cmd = RevenueCommand(mock_state)
    cmd._settle_indemnities()

    assert mock_state.treasury == 150
    mock_state.log_event.assert_called_with(
        f"战争赔款收入: Test War +50",
        extra={'type': 'indemnity_income', 'war_id': 'w1', 'amount': 50}
    )
    assert war.indemnity_due == 0

def test_indemnity_expense_sufficient(mock_state, mock_war_system):
    war = War(id='w2', name='Expense War')
    war.set_indemnity_due(-30)
    mock_war_system._truce_wars = [war]
    mock_state.get_war_system.return_value = mock_war_system

    cmd = RevenueCommand(mock_state)
    cmd._settle_indemnities()

    assert mock_state.treasury == 70
    mock_state.log_event.assert_called_with(
        f"战争赔款支出: Expense War 30",
        extra={'type': 'indemnity_expense', 'war_id': 'w2', 'amount': 30}
    )
    assert war.indemnity_due == 0

def test_indemnity_expense_insufficient(mock_state, mock_war_system, capsys):
    war = War(id='w3', name='Bankrupt War')
    war.set_indemnity_due(-200)  # 国库只有100
    mock_war_system._active_wars = [war]
    mock_state.get_war_system.return_value = mock_war_system

    cmd = RevenueCommand(mock_state)
    cmd._settle_indemnities()

    captured = capsys.readouterr()
    assert "共和覆灭" in captured.out
    # 注意：当前未调用 add_treasury，国库不变
    assert mock_state.treasury == 100
    mock_state.log_event.assert_called_with(
        f"国库不足支付赔款，共和覆灭",
        extra={'type': 'game_over', 'reason': 'indemnity', 'war_id': 'w3', 'amount': 200},
        level=50  # logging.CRITICAL
    )
    # 赔款标记是否应清除？按设计，即使国库不足也应清除？建议不清除，否则下次会再次尝试。但简化起见，可暂时不清除，等待后续处理。
    # 此处我们按设计：不清除，但为了测试方便，可断言 war.indemnity_due == -200
    assert war.indemnity_due == -200