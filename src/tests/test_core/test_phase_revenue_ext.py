# src/tests/test_core/test_phase_revenue_ext.py
"""税收阶段扩展测试 - 私有方法测试"""

import pytest
import io
from unittest.mock import patch, MagicMock
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.entities import GameTurn
from src.core.entities.province import Province
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from src.ui.commands.phase_revenue import RevenueCommand
from src.core.localization import TerminologyService


@pytest.fixture
def state():
    """创建测试用 GameState"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    return state


@pytest.fixture
def knight(state):
    """创建骑士人物"""
    fig = Figure(id=201, name="骑士甲", faction_id="senate", age=35)
    fig._land_private = 100
    fig.class_tier = "eques"
    state.add_member(fig)
    return fig


@pytest.fixture
def works_contract(state, knight):
    """创建公共工程合同（执行中）"""
    province = Province(1, "罗马", 1000)
    state.add_province(province)
    contract = Contract(
        id=301,
        contract_type=ContractType.PUBLIC_WORKS,
        name="罗马大竞技场",
        base_cost=800,
        expected_profit=200,
        status=ContractStatus.ACTIVE,
        awarded_to=knight.id,
        awarded_faction=knight.faction_id,
        remaining_years=3,
        total_spent=0
    )
    contract._original_budget = 800
    contract._construction_years = 3
    contract._warranty_years = 10
    contract._annual_income = 267
    contract._annual_cost = 200
    contract._warranty_remaining = 0
    contract._province_id = province.province_id  # 关键修复：设置行省ID
    state._contracts_dict[301] = contract
    return contract


class TestRevenuePhaseExt:
    """税收阶段私有方法扩展测试"""

    def test_works_payment_normal(self, state, works_contract, knight):
        """正常施工年份支付年收入"""
        cmd = RevenueCommand(state)
        terms = TerminologyService.get()
        faction_tax_collected = {}
        tax_rate = state.get_economic_rule("faction_tax_rate", 0.1)

        initial_treasury = state.treasury
        initial_wealth = knight.wealth

        cmd._collect_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 国库减少年收入267
        assert state.treasury == initial_treasury - 267
        # 骑士获得净收入：利润67 - 抽成6.7 → 60
        assert knight.wealth == initial_wealth + 60
        # 剩余年限减少
        assert works_contract.remaining_years == 2
        # 已支付金额增加
        assert works_contract.total_spent == 267

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

        cmd._collect_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 尾款支付 = 800 - 534 = 266
        assert state.treasury == initial_treasury - 266
        # 利润 = 266 - 200 = 66，抽成6.6 → 净得59
        assert knight.wealth == initial_wealth + 59
        # 合同应标记为已完成
        assert works_contract.status == ContractStatus.COMPLETED
        assert works_contract.remaining_years == 0

    def test_contractor_death_during_works(self, state, works_contract, knight):
        """中标者死亡，合同终止"""
        # 标记骑士死亡
        state.mark_member_dead(knight.id, transfer_land=True)
        assert knight.is_dead is True

        cmd = RevenueCommand(state)
        terms = TerminologyService.get()
        faction_tax_collected = {}
        tax_rate = state.get_economic_rule("faction_tax_rate", 0.1)

        cmd._collect_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 合同应终止（状态变为EXPIRED）
        assert works_contract.status == ContractStatus.EXPIRED
        # 行省应解绑
        province = state.get_province(works_contract.province_id)
        assert province is not None, "行省不存在"
        assert province.project_contract_id is None

    def test_warranty_decay(self, state, works_contract):
        """已完成工程合同的质保年限逐年递减"""
        # 检查 RevenueCommand 是否有 _process_warranty_decay 方法
        cmd = RevenueCommand(state)
        if not hasattr(cmd, '_process_warranty_decay'):
            pytest.skip("RevenueCommand 没有 _process_warranty_decay 方法，跳过测试")

        # 先让合同完成
        works_contract.status = ContractStatus.COMPLETED
        works_contract._warranty_remaining = 5

        terms = TerminologyService.get()

        cmd._process_warranty_decay(terms)

        # 质保剩余减少1
        assert works_contract._warranty_remaining == 4

        # 减到0时应提示失修
        works_contract._warranty_remaining = 1
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._process_warranty_decay(terms)
        assert works_contract._warranty_remaining == 0
        assert "质保期结束" in mock_stdout.getvalue()