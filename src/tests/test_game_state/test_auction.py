"""
测试 GameState 的 place_bid 和 resolve_auction 方法。
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.entities import Province
from src.core.entities.figure import Figure
from src.core.entities.entities import GameTurn



@pytest.fixture
def state():
    """创建一个干净的 GameState 实例用于测试"""
    state = GameState.create_for_testing({})
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=1, year=-264)
    return state


@pytest.fixture
def province(state):
    """创建一个测试用行省并添加到 state"""
    p = Province(1, "西西里", 1000)
    state.add_province(p)
    return p


@pytest.fixture
def tax_contract(state, province):
    """创建一个包税合同"""
    contract = state.create_contract(
        ContractType.TAX_FARMING,
        province.province_id,
        base_cost=100,
        current_turn=5
    )
    contract.duration_years = 5  # 设置期限
    return contract


@pytest.fixture
def works_contract(state, province):
    """创建一个工程合同，并设置必要字段"""
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province.province_id,
        base_cost=1000,
        current_turn=5
    )
    contract._original_budget = 1000  # 原始预算
    return contract


@pytest.fixture
def knight(state):
    """创建一个骑士人物"""
    fig = Figure(id=101, name="测试骑士", faction_id="faction1")
    fig._wealth = 500
    fig._class_tier = "eques"
    state.add_member(fig)
    return fig


class TestAuction:
    """竞标功能测试"""

    def test_place_bid_success(self, state, tax_contract, knight):
        """测试正常出价"""
        result = state.place_bid(tax_contract.id, knight.id, 150, tax_rate=0.2)
        assert result is True
        contract = state.get_contract(tax_contract.id)
        assert len(contract.bids) == 1
        assert contract.bids[0]["bidder_id"] == knight.id
        assert contract.bids[0]["amount"] == 150
        assert contract.bids[0]["tax_rate"] == 0.2

    def test_place_bid_contract_not_pending(self, state, tax_contract, knight):
        """合同状态不是PENDING时出价失败"""
        tax_contract.status = ContractStatus.ACTIVE
        result = state.place_bid(tax_contract.id, knight.id, 150)
        assert result is False
        assert len(tax_contract.bids) == 0

    def test_place_bid_contract_not_found(self, state, knight):
        """合同不存在时出价失败"""
        result = state.place_bid(999, knight.id, 150)
        assert result is False

    def test_resolve_auction_tax_farming(self, state, tax_contract, knight):
        """包税合同：最高价中标"""
        # 创建第二个骑士
        knight2 = Figure(id=102, name="测试骑士2", faction_id="faction2")
        knight2._wealth = 600
        state.add_member(knight2)

        state.place_bid(tax_contract.id, knight.id, 150, tax_rate=0.1)
        state.place_bid(tax_contract.id, knight2.id, 200, tax_rate=0.2)

        result = state.resolve_auction(tax_contract.id)
        assert result is True

        contract = state.get_contract(tax_contract.id)
        assert contract.status == ContractStatus.ACTIVE
        assert contract.winning_bid["bidder_id"] == knight2.id
        assert contract.winning_bid["amount"] == 200
        # 检查是否正确设置了 _tax_rate 和 _annual_profit（需模拟行省计算，简单验证存在）
        assert hasattr(contract, "_tax_rate")
        assert contract._tax_rate == 0.2

    def test_resolve_auction_tax_farming_no_bids(self, state, tax_contract):
        """包税合同无出价：流拍"""
        result = state.resolve_auction(tax_contract.id)
        assert result is False
        assert tax_contract.status == ContractStatus.EXPIRED

    def test_resolve_auction_public_works(self, state, works_contract, knight):
        """工程合同：最低价中标"""
        knight2 = Figure(id=103, name="测试骑士3", faction_id="faction3")
        knight2._wealth = 600
        state.add_member(knight2)

        # 出价需包含工程合同所需参数
        state.place_bid(works_contract.id, knight.id, 800,
                        r=0.2, original_budget=1000, construction=2, warranty=5,
                        annual_income=400, annual_cost=300)
        state.place_bid(works_contract.id, knight2.id, 700,
                        r=0.3, original_budget=1000, construction=3, warranty=4,
                        annual_income=233, annual_cost=250)

        result = state.resolve_auction(works_contract.id)
        assert result is True

        contract = state.get_contract(works_contract.id)
        assert contract.status == ContractStatus.ACTIVE
        assert contract.winning_bid["bidder_id"] == knight2.id
        assert contract.winning_bid["amount"] == 700
        # 检查工程字段是否正确设置
        assert contract.construction_years == 3
        assert contract.warranty_years == 4
        assert contract.annual_income == 233
        assert contract.annual_cost == 250
        assert contract.warranty_remaining == 4

    def test_resolve_auction_works_no_bids(self, state, works_contract):
        """工程合同无出价：流拍"""
        result = state.resolve_auction(works_contract.id)
        assert result is False
        assert works_contract.status == ContractStatus.EXPIRED

    def test_resolve_auction_contract_not_pending(self, state, tax_contract):
        """合同状态不是PENDING时无法揭标"""
        tax_contract.status = ContractStatus.ACTIVE
        result = state.resolve_auction(tax_contract.id)
        assert result is False