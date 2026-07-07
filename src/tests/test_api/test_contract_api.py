# src/tests/test_api/test_contract_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import contract_api
from src.core.entities.contract import Contract, ContractStatus, ContractType
from src.core.i18n import i18n

# 加载 i18n 以确保消息正确
i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.contracts = []
    return state


@pytest.fixture
def sample_pending_contract():
    contract = MagicMock(spec=Contract)
    contract.id = 1
    contract.contract_type = ContractType.TAX_FARMING
    contract.status = ContractStatus.PENDING
    contract.name = "Test Tax Contract"
    contract.base_cost = 100
    contract.expected_profit = 50
    return contract


@pytest.fixture
def sample_active_contract():
    contract = MagicMock(spec=Contract)
    contract.id = 2
    contract.contract_type = ContractType.PUBLIC_WORKS
    contract.status = ContractStatus.ACTIVE
    contract.name = "Test Works Contract"
    contract.base_cost = 200
    contract.expected_profit = 30
    contract.awarded_to = 101
    contract.awarded_faction = "optimates"
    contract.remaining_years = 3
    contract.total_collected = 0
    contract.total_spent = 50
    contract.is_extended = False
    return contract


def test_get_contracts_status_no_contracts(mock_state):
    result = contract_api.get_contracts_status(mock_state)
    assert result["success"] is True
    assert "No contracts" in result["message"]
    assert result["data"] == []


def test_get_contracts_status_pending(mock_state, sample_pending_contract):
    mock_state.contracts = [sample_pending_contract]
    result = contract_api.get_contracts_status(mock_state)
    assert result["success"] is True
    assert "PENDING" in result["message"]
    assert result["data"]["pending"][0]["id"] == 1


def test_get_contracts_status_active(mock_state, sample_active_contract):
    mock_state.contracts = [sample_active_contract]
    # 模拟 get_member 和 get_faction 返回有效值
    mock_state.get_member.return_value = MagicMock(name="Test Contractor")
    mock_state.get_faction.return_value = MagicMock(name="Optimates")
    result = contract_api.get_contracts_status(mock_state)
    assert result["success"] is True
    assert "ACTIVE" in result["message"]
    assert result["data"]["active"][0]["id"] == 2


def test_get_contracts_status_mixed(mock_state, sample_pending_contract, sample_active_contract):
    mock_state.contracts = [sample_pending_contract, sample_active_contract]
    mock_state.get_member.return_value = MagicMock(name="Test Contractor")
    mock_state.get_faction.return_value = MagicMock(name="Optimates")
    result = contract_api.get_contracts_status(mock_state)
    assert result["success"] is True
    assert len(result["data"]["pending"]) == 1
    assert len(result["data"]["active"]) == 1