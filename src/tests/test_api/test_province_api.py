# src/tests/test_api/test_province_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import province_api
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType
from src.core.entities.entities import Faction
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    return state


@pytest.fixture
def sample_province():
    province = MagicMock(spec=Province)
    province.province_id = 1
    province.name = "Sicilia"
    province.conquered = True
    province.total_land = 1000
    province.land_public = 600
    province.land_private = 400
    province.governor_type = "proconsul"
    province.governor_id = 101
    province.governor_designate_id = None
    province.grievance = 1
    province.tax_contract_id = 10
    province.project_contract_id = None
    province._old_governor_id = None
    province.governor_since = 1
    return province


@pytest.fixture
def sample_italy():
    province = MagicMock(spec=Province)
    province.province_id = 0
    province.name = "Italy"
    province.conquered = True
    province.total_land = 6000
    province.land_public = 6000
    province.land_private = 0
    province.governor_type = "proconsul"
    province.governor_id = None
    province.governor_designate_id = None
    province.grievance = 0
    province.tax_contract_id = None
    province.project_contract_id = None
    return province


@pytest.fixture
def sample_tax_contract():
    contract = MagicMock(spec=Contract)
    contract.id = 10
    contract.contract_type = ContractType.TAX_FARMING
    contract.base_cost = 100
    contract.tax_rate = 0.15
    contract.awarded_to = 101
    contract.awarded_faction = "optimates"
    contract.remaining_years = 3
    contract._annual_profit = 20
    return contract


@pytest.fixture
def sample_faction():
    faction = MagicMock(spec=Faction)
    faction.id = "optimates"
    faction.name = "Optimates"
    faction.province_owned = [1]
    return faction


def test_get_province_info_no_id_no_provinces(mock_state):
    mock_state.get_all_provinces.return_value = []
    result = province_api.get_province_info(mock_state)
    assert result["success"] is True
    assert "没有已征服的行省数据" in result["message"]
    assert result["data"] == []


def test_get_province_info_no_id_with_provinces(mock_state, sample_province, sample_italy, sample_tax_contract, sample_faction):
    # 配置一个 mock 成员，使其 get_formal_name 返回字符串
    mock_member = MagicMock()
    mock_member.get_formal_name.return_value = "Test Governor"
    mock_state.get_member.return_value = mock_member  # 正确配置

    mock_state.get_all_provinces.return_value = [sample_province, sample_italy]
    mock_state.get_contract.return_value = sample_tax_contract

    mock_state.factions = {"optimates": sample_faction}
    result = province_api.get_province_info(mock_state)
    assert result["success"] is True
    assert "已征服行省状态一览" in result["message"]
    assert len(result["data"]) == 2


def test_get_province_info_with_id_found(mock_state, sample_province, sample_tax_contract, sample_faction):
    # 设置数值属性
    sample_province.governor_since = 5
    mock_state.turn.turn_number = 10
    mock_state.turn.year = -260
    # 确保 governor 的 get_formal_name 返回字符串
    mock_governor = MagicMock()
    mock_governor.get_formal_name.return_value = "Test Governor"
    mock_state.get_member.return_value = mock_governor

    mock_state.get_province.return_value = sample_province
    mock_state.get_contract.return_value = sample_tax_contract
    mock_state.get_member.return_value = MagicMock(name="Governor")
    mock_state.get_faction.return_value = sample_faction
    result = province_api.get_province_info(mock_state, province_id=1)
    assert result["success"] is True
    assert "行省详情" in result["message"]
    assert result["data"]["province_id"] == 1


def test_get_province_info_with_id_not_found(mock_state):
    mock_state.get_province.return_value = None
    result = province_api.get_province_info(mock_state, province_id=999)
    assert result["success"] is False
    assert "不存在" in result["message"]


def test_get_province_info_with_id_not_conquered(mock_state, sample_province):
    sample_province.conquered = False
    mock_state.get_province.return_value = sample_province
    result = province_api.get_province_info(mock_state, province_id=1)
    assert result["success"] is False
    assert "尚未征服" in result["message"]