"""
测试税收阶段中工程合同支付、质保递减及死亡终止逻辑。
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.entities import Province, GameTurn
from src.core.entities.figure import Figure
from src.ui.commands.phase_revenue import RevenueCommand
from src.core.localization import TerminologyService


@pytest.fixture
def state():
    """创建测试用 GameState，并设置必要的经济规则"""
    config = {
        "economic_rules": {
            "land_price_per_unit": 10,
            "national_public_land_tax_rate": 0.02,
            "faction_stipend": 10,
            "private_land_income_rate": 0.05
        }
    }
    state = GameState.create_for_testing(config)
    # 设置回合，避免 mark_complete 时出错
    state.turn = GameTurn(turn_number=1, year=-264)
    return state


@pytest.fixture
def province(state):
    p = Province(1, "测试行省", 1000)
    state.add_province(p)
    return p


@pytest.fixture
def knight(state):
    fig = Figure(id=201, name="骑士甲", faction_id="faction1")
    fig._wealth = 1000
    fig._land_private = 100
    state.add_member(fig)
    return fig


@pytest.fixture
def works_contract(state, province, knight):
    """创建一个已中标的工程合同，处于施工状态"""
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province.province_id,
        base_cost=1000,
        current_turn=5
    )
    # 模拟中标后设置的字段
    contract._winning_bid = {
        "bidder_id": knight.id,
        "amount": 800,
        "r": 0.2,
        "construction": 3,
        "warranty": 5,
        "annual_income": 267,
        "annual_cost": 200
    }
    contract.mark_winner(knight.id, 5, 0)
    contract._construction_years = 3
    contract._warranty_years = 5
    contract._warranty_remaining = 5
    contract._annual_income = 267
    contract._annual_cost = 200
    contract.remaining_years = 3
    contract.base_cost = 800  # 承包价
    # 绑定行省
    province.bind_project_contract(contract.id)
    return contract


class TestRevenuePhaseExt:
    """税收阶段扩展功能测试"""

    def test_works_payment_normal(self, state, works_contract, knight):
        """正常施工年份支付年收入"""
        cmd = RevenueCommand(state)
        terms = TerminologyService.get()
        faction_tax_collected = {}
        tax_rate = state.get_economic_rule("faction_tax_rate", 0.1)
        cmd._process_contract_revenues(terms, faction_tax_collected, tax_rate)

        contract = works_contract
        # 国库减少 payment（annual_income = 267）
        assert state.treasury == -267
        # 骑士财富增加 payment
        assert knight.wealth == 60
        # 施工剩余年限减少
        assert contract.remaining_years == 2
        # 总支出记录
        assert contract.total_spent == 267

    def test_works_final_payment(self, state, works_contract, knight):
        """最后一年支付余数"""
        cmd = RevenueCommand(state)
        # 设置已支付2年，剩余1年
        works_contract.remaining_years = 1
        works_contract.total_spent = 267 * 2  # 已支付534
        initial_treasury = state.treasury
        initial_wealth = knight.wealth

        terms = TerminologyService.get()
        faction_tax_collected = {}
        tax_rate = state.get_economic_rule("faction_tax_rate", 0.1)
        cmd._process_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 最后一年应支付总承包价 - 已支付 = 800 - 534 = 266
        assert state.treasury == initial_treasury - 266
        assert knight.wealth == initial_wealth + 59
        assert works_contract.remaining_years == 0
        assert works_contract.total_spent == 800
        # 合同应变为 COMPLETED
        assert works_contract.status == ContractStatus.COMPLETED
        # 行省应解绑
        province = state.get_province(works_contract.province_id)
        assert province.project_contract_id is None
        assert province.has_project is False

    def test_contractor_death_during_works(self, state, works_contract, knight):
        """中标者死亡，合同终止"""
        # 标记骑士死亡
        state.mark_member_dead(knight.id, transfer_land=True)
        assert knight.is_dead is True

        cmd = RevenueCommand(state)
        terms = TerminologyService.get()
        faction_tax_collected = {}
        tax_rate = state.get_economic_rule("faction_tax_rate", 0.1)
        cmd._process_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 合同应被终止（EXPIRED）
        assert works_contract.status == ContractStatus.EXPIRED
        # 行省解绑
        province = state.get_province(works_contract.province_id)
        assert province.project_contract_id is None
        assert province.has_project is False

    def test_warranty_decay(self, state, works_contract):
        """已完成工程合同的质保年限逐年递减"""
        # 先让合同完成
        works_contract.status = ContractStatus.COMPLETED
        works_contract._warranty_remaining = 5

        cmd = RevenueCommand(state)
        terms = TerminologyService.get()
        cmd._process_warranty_decay(terms)

        assert works_contract.warranty_remaining == 4

        # 再次递减至0
        cmd._process_warranty_decay(terms)
        assert works_contract.warranty_remaining == 3
        # 模拟递减5次到0
        for _ in range(3):
            cmd._process_warranty_decay(terms)
        assert works_contract.warranty_remaining == 0
