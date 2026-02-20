# src/tests/test_commands/test_func_contracts.py
"""
合同功能命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os
from io import StringIO

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_contracts import ContractsCommand, VoteCommand
from src.core.game_state import GameState
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.contracts = []
    state.factions = {}
    state.turn.turn_number = 1
    state.add_figure_wealth = MagicMock()
    state.add_treasury = MagicMock()
    state.get_member = MagicMock()
    return state


@pytest.fixture
def mock_contract():
    contract = MagicMock(spec=Contract)
    contract.id = 1
    contract.contract_type = ContractType.TAX_FARMING
    contract.status = ContractStatus.PENDING
    contract.name = "Sicily Tax Contract"
    contract.base_cost = 30
    contract.expected_profit = 50
    contract.duration_years = 5
    contract.remaining_years = 5
    contract.total_collected = 0
    contract.total_spent = 0
    contract.awarded_to = None
    contract.awarded_faction = None
    contract.award.return_value = True
    return contract


@pytest.fixture
def mock_figure():
    figure = MagicMock(spec=Figure)
    figure.id = 101
    figure.name = "Eques Test"
    figure.class_tier.value = "eques"
    figure.wealth = 100
    figure.faction_id = "senate"
    return figure


@pytest.fixture
def mock_faction():
    faction = MagicMock(spec=Faction)
    faction.id = "senate"
    faction.name = "Senate"
    faction.get_members.return_value = []
    return faction


# ========== ContractsCommand ==========

def test_contracts_no_contracts(mock_state):
    mock_state.contracts = []
    cmd = ContractsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


def test_contracts_with_pending(mock_state, mock_contract):
    mock_contract.status = ContractStatus.PENDING
    mock_state.contracts = [mock_contract]
    cmd = ContractsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


def test_contracts_with_active(mock_state, mock_contract):
    mock_contract.status = ContractStatus.ACTIVE
    mock_contract.awarded_to = 101
    mock_contract.awarded_faction = "senate"
    mock_state.contracts = [mock_contract]
    mock_state.get_member.return_value = MagicMock(name="Test")
    mock_state.get_faction.return_value = MagicMock(name="Senate")
    cmd = ContractsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


def test_contracts_with_completed(mock_state, mock_contract):
    mock_contract.status = ContractStatus.COMPLETED
    mock_state.contracts = [mock_contract]
    cmd = ContractsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


def test_contracts_with_expired(mock_state, mock_contract):
    mock_contract.status = ContractStatus.EXPIRED
    mock_state.contracts = [mock_contract]
    cmd = ContractsCommand(mock_state)
    result = cmd.execute([])
    assert result is True


# ========== VoteCommand ==========

def test_vote_wrong_args(mock_state):
    cmd = VoteCommand(mock_state)
    result = cmd.execute([])
    assert result is False
    result = cmd.execute(["not_contract"])
    assert result is False


def test_vote_invalid_contract_id(mock_state):
    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "abc"])
    assert result is False


def test_vote_contract_not_found(mock_state):
    mock_state.contracts = []
    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "999"])
    assert result is False


def test_vote_contract_not_pending(mock_state, mock_contract):
    mock_contract.status = ContractStatus.ACTIVE
    mock_state.contracts = [mock_contract]
    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "1"])
    assert result is False


def test_vote_contract_not_tax_farming(mock_state, mock_contract):
    mock_contract.contract_type = ContractType.PUBLIC_WORKS
    mock_state.contracts = [mock_contract]
    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "1"])
    assert result is False


def test_vote_no_candidates(mock_state, mock_contract):
    mock_state.contracts = [mock_contract]
    mock_state.factions = {}  # 无派系，无候选人
    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "1"])
    assert result is False


@patch('builtins.input')
def test_vote_success(mock_input, mock_state, mock_contract, mock_figure, mock_faction):
    mock_state.contracts = [mock_contract]

    # 正确设置 mock_figure
    class_tier_mock = MagicMock()
    class_tier_mock.value = "eques"
    mock_figure.class_tier = class_tier_mock
    mock_figure.id = 101
    mock_figure.name = "Eques Test"
    mock_figure.wealth = 100
    mock_figure.faction_id = "senate"
    mock_figure.is_dead = False  # 关键：设置为 False

    # 设置候选人
    mock_faction.get_members.return_value = [mock_figure]
    mock_state.factions = {"senate": mock_faction}
    mock_state.get_faction.return_value = mock_faction

    # 模拟用户选择第一个候选人
    mock_input.return_value = "1"

    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "1"])

    assert result is True
    mock_contract.award.assert_called_once_with(101, "senate", 1)
    mock_state.add_figure_wealth.assert_called_once_with(101, -30)
    mock_state.add_treasury.assert_called_once_with(30)


@patch('builtins.input')
def test_vote_cannot_afford(mock_input, mock_state, mock_contract, mock_figure, mock_faction):
    mock_state.contracts = [mock_contract]

    class_tier_mock = MagicMock()
    class_tier_mock.value = "eques"
    mock_figure.class_tier = class_tier_mock
    mock_figure.id = 101
    mock_figure.name = "Eques Test"
    mock_figure.wealth = 20  # 小于 base_cost=30
    mock_figure.faction_id = "senate"
    mock_figure.is_dead = False

    mock_faction.get_members.return_value = [mock_figure]
    mock_state.factions = {"senate": mock_faction}

    mock_input.return_value = "1"

    cmd = VoteCommand(mock_state)
    result = cmd.execute(["contract", "1"])

    assert result is False
    mock_contract.award.assert_not_called()