"""
测试广场阶段合同生成逻辑和自动竞标。
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.province import Province
from src.core.entities.figure import Figure
from src.core.entities.contract import ContractType, ContractStatus
from src.ui.commands.phase_forum import ForumCommand


@pytest.fixture
def state():
    config = {
        "economic_rules": {
            "land_price_per_unit": 10,
            "private_land_income_rate": 0.05,
            "province_tax_rate": 0.1,
            "tax_auction_ratio": 0.8,
            "tax_contract_duration": 5,
            "tax_bid_increment_min": 0.05,
            "tax_bid_increment_max": 0.20,
            "infrastructure_cost_rate": 0.01,
            "project_budget_margin": 0.2,
            "project_theoretical_construction": 5,
            "project_theoretical_warranty": 10,
            "project_bid_discount_min": 0.05,
            "project_bid_discount_max": 0.20
        }
    }
    state = GameState.create_for_testing(config)
    # 初始化回合
    state.turn = GameTurn(turn_number=1, year=-264)
    return state


@pytest.fixture
def provinces(state):
    # 创建测试用行省，包括意大利
    italy = Province(0, "意大利", 0)
    italy._land_public = 1000  # 匹配国家公地初始值
    italy._conquered = True
    p1 = Province(1, "西西里", 1000)
    p1._conquered = True
    p2 = Province(2, "撒丁岛", 800)
    p2._conquered = True
    p3 = Province(3, "科西嘉", 600)
    p3._conquered = True
    state.add_province(italy)
    state.add_province(p1)
    state.add_province(p2)
    state.add_province(p3)
    return [italy, p1, p2, p3]


@pytest.fixture
def factions_and_knights(state):
    """创建两个派系，每个派系有一个骑士"""
    from src.core.entities.entities import Faction
    f1 = Faction(id="f1", name="派系A", treasury=100, is_player=True)
    f2 = Faction(id="f2", name="派系B", treasury=100, is_player=False)
    state.add_faction(f1)
    state.add_faction(f2)

    k1 = Figure.create_eques(101, "f1", age=30)
    k1.wealth = 500
    k2 = Figure.create_eques(102, "f2", age=35)
    k2.wealth = 600
    state.add_member(k1)
    state.add_member(k2)
    f1.member_ids.append(101)
    f2.member_ids.append(102)
    return [(f1, k1), (f2, k2)]


class TestForumPhaseExt:
    """广场阶段合同生成与自动竞标测试"""

    def test_generate_contracts_skips_italy_tax(self, state, provinces):
        """意大利行省不应生成包税合同"""
        cmd = ForumCommand(state)
        contracts = cmd._generate_contracts()
        tax_contracts = [c for c in contracts if c.contract_type == ContractType.TAX_FARMING]
        works_contracts = [c for c in contracts if c.contract_type == ContractType.PUBLIC_WORKS]
        # 意大利不生成包税合同，所以包税合同数量应为总行省数-1（4-1=3）
        assert len(tax_contracts) == 3
        # 所有行省（包括意大利）都应生成工程合同，前提是 land_public > 0
        # 意大利 land_public 为1000，所以生成1个，加上3个行省共4个
        assert len(works_contracts) == 4

    def test_generate_contracts_values(self, state, provinces):
        """验证生成的合同基础数据正确"""
        cmd = ForumCommand(state)
        contracts = cmd._generate_contracts()
        # 检查包税合同（以西西里为例）
        tax = next(c for c in contracts if c.contract_type == ContractType.TAX_FARMING and c.province_id == 1)
        # 预期 base_cost 根据配置计算
        land_price = 10
        private_rate = 0.05
        province_tax_rate = 0.1
        auction_ratio = 0.8
        province = state.get_province(1)
        land_value = province.land_public * land_price
        base_income = int(land_value * private_rate)
        base_tax = int(base_income * province_tax_rate)
        base_cost = int(base_tax * auction_ratio)
        assert tax.base_cost == base_cost
        assert tax.duration_years == 5

        # 检查工程合同（以意大利为例）
        works = next(c for c in contracts if c.contract_type == ContractType.PUBLIC_WORKS and c.province_id == 0)
        # 意大利工程预算
        infra_rate = 0.01
        budget_margin = 0.2
        italy = state.get_province(0)
        land_value = italy.land_public * land_price
        infra_cost = int(land_value * infra_rate)
        budget = int(infra_cost * (1 + budget_margin))
        assert works._original_budget == budget
        assert works.base_cost == budget

    def test_auto_bid_for_tax_contract(self, state, provinces, factions_and_knights):
        """测试包税合同自动竞标流程"""
        cmd = ForumCommand(state)
        contracts = cmd._generate_contracts()
        tax_contract = next(c for c in contracts if c.contract_type == ContractType.TAX_FARMING and c.province_id == 1)

        # 将合同状态设为 BUDGETED（因为只有 BUDGETED 才能竞标）
        tax_contract.status = ContractStatus.BUDGETED

        try:
            cmd._auto_bid_for_contract(tax_contract)
        except Exception as e:
            pytest.fail(f"自动竞标抛出异常: {e}")

        # 竞标后状态应为 ACTIVE（中标）或 BUDGETED（流拍）
        assert tax_contract.status in (ContractStatus.ACTIVE, ContractStatus.BUDGETED)

    def test_auto_bid_for_works_contract(self, state, provinces, factions_and_knights):
        """测试工程合同自动竞标流程"""
        cmd = ForumCommand(state)
        contracts = cmd._generate_contracts()
        works_contract = next(
            c for c in contracts if c.contract_type == ContractType.PUBLIC_WORKS and c.province_id == 0)

        # 将合同状态设为 BUDGETED
        works_contract.status = ContractStatus.BUDGETED

        try:
            cmd._auto_bid_for_works(works_contract)
        except Exception as e:
            pytest.fail(f"工程自动竞标抛出异常: {e}")

        assert works_contract.status in (ContractStatus.ACTIVE, ContractStatus.BUDGETED)
        if works_contract.status == ContractStatus.ACTIVE:
            assert works_contract.winning_bid is not None
            assert works_contract.awarded_to is not None
            assert works_contract.construction_years > 0
            assert works_contract.annual_income > 0