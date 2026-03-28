# src/tests/test_commands/test_func_contracts.py
"""
合同功能命令单元测试
"""

import pytest
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_contracts import ContractsCommand, VoteCommand
from src.api import forum_api, senate_api
from src.core.game_state import GameState
from src.core.entities.province import Province
from src.core.entities.player import Player, PlayerType
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.figure import Figure
from src.core.entities.entities import GameTurn, Faction
from unittest.mock import MagicMock, patch
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem




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

"""
合同系统功能升级单元测试（DS030）
测试舰队合同资金流、公共工程预算加成、手动模式出价限制
"""

@pytest.fixture
def basic_state():
    """创建基础测试状态（修复版）"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "land_price_per_unit": 10,
            "private_land_income_rate": 0.05,
            "province_tax_rate": 0.1,
            "tax_auction_ratio": 0.8,
            "tax_contract_duration": 5,
            "infrastructure_cost_rate": 0.001,
            "project_budget_margin": 0.2,
            "project_theoretical_construction": 3,
            "project_theoretical_warranty": 10,
            "default_bid_profit_rate": 0.2,
            "public_work_budget_margin_range": [0.05, 0.20],
            "fleet_types": {
                "trireme": {
                    "build_cost": 40,
                    "build_time": 1,
                    "maintenance_cost": 5,
                    "strength_base": 3
                }
            },
            "default_fleet_type": "trireme"
        },
        "testing": {
            "bypass_player_check": True,
            "auto_forum": False
        }
    })

    # ===== 初始化必要的系统 =====
    state._war_system = WarSystem(state)
    state._war_system.load_wars_from_json("wars.json")  # 可加载空数据，或直接创建空列表
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    # ===== 添加行省 =====
    italy = Province(0, "Italia", total_land=1000)
    italy._conquered = True
    italy._land_public = 1000
    state.add_province(italy)

    province = Province(1, "Sicilia", total_land=500)
    province._conquered = True
    province._land_public = 300
    state.add_province(province)

    # ===== 添加派系和玩家 =====
    faction = Faction("populares", "Populares", 1)  # 注意：构造函数签名为 (faction_id, name, leader_id)
    faction.treasury = 1000
    state.add_faction(faction)


    player = Player("player1", "populares", PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player1")

    # ===== 添加骑士人物 =====
    knight = Figure.create_eques(state.allocate_id(), None, age=30)
    knight.faction_id = "populares"
    knight.wealth = 500
    state.add_member(knight)

    # ===== 添加执政官（用于提案） =====
    consul = Figure.create_nobile(state.allocate_id(), None, age=45)
    consul.faction_id = "populares"
    consul.office = "consul"
    consul.is_absent = False
    state.add_member(consul)

    # 添加骑士和执政官后，立即将它们加入派系成员列表
    faction.member_ids.append(knight.id)
    faction.member_ids.append(consul.id)

    # ===== 初始化回合对象 =====
    state.turn = GameTurn(turn_number=1, year=-275)
    state.turn.leader_ids = [consul.id]

    return state, knight, consul, province


def create_fleet_contract(state, province_id, target_war_id="war1"):
    """创建舰队建造合同"""
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province_id,
        base_cost=100,
        current_turn=state.turn.turn_number
    )
    contract._is_fleet_construction = True
    contract._target_war_id = target_war_id
    contract._fleet_type = "trireme"
    contract._build_time = 1
    contract.name = "Test Fleet Contract"
    contract.status = ContractStatus.BUDGETED  # 直接设为可竞标状态
    return contract


def create_public_works_contract(state, province_id):
    """创建普通公共工程合同"""
    contract = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province_id,
        base_cost=100,
        current_turn=state.turn.turn_number
    )
    contract.name = "Test Works Contract"
    contract.status = ContractStatus.BUDGETED
    return contract


def create_tax_contract(state, province_id):
    """创建包税合同"""
    contract = state.create_contract(
        ContractType.TAX_FARMING,
        province_id,
        base_cost=80,
        current_turn=state.turn.turn_number
    )
    contract.name = "Test Tax Contract"
    contract.status = ContractStatus.BUDGETED
    return contract


class TestContractFixes:
    """合同系统功能升级测试"""

    def test_fleet_contract_financial_flow(self, basic_state):
        """测试舰队合同资金流：中标后设置财务参数，收入阶段完成资金转移，战斗力调整"""
        state, knight, consul, province = basic_state

        # 创建舰队合同并设为可竞标
        contract = create_fleet_contract(state, province.province_id)
        contract._original_budget = 100  # 原始预算

        # 玩家出价
        profit_rate = 0.15  # 折扣15%
        amount = int(contract.base_cost * (1 - profit_rate))  # 85
        result = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, profit_rate)
        assert result["success"]

        # 结算竞标（公示环节）
        forum_result = forum_api.resolve_forum(state)
        assert forum_result["success"]

        # 验证合同中标后财务参数
        contract = state.get_contract(contract.id)
        assert contract.status == ContractStatus.ACTIVE
        assert contract._annual_income == amount  # 一年工期，年收入=中标价
        assert contract._annual_cost == int(amount * (1 - profit_rate))  # 实际成本=中标价*(1-r)
        assert contract.remaining_years == 1

        # 模拟收入阶段结算
        from src.ui.commands.phase_revenue import RevenueCommand
        from src.core.localization import TerminologyService
        rev_cmd = RevenueCommand(state)
        faction_tax_collected = {}
        terms = TerminologyService.get()
        # 设置国库初始值，避免影响验证
        state.treasury = 200
        # 正确调用：传入 terms, faction_tax_collected, tax_rate
        rev_cmd._collect_contract_revenues(terms, faction_tax_collected, 0.1)

        # 验证国库和骑士财富变化
        actual_cost = int(amount * (1 - profit_rate))
        # 骑士净收入 = 收入(amount) - 成本(actual_cost) - 抽成(profit的10%)
        profit = amount - actual_cost  # 16
        tax = int(round(profit * 0.1))  # 2
        knight_net = profit - tax  # 14
        expected_knight_wealth = 500 + knight_net  # 514
        knight = state.get_member(knight.id)
        assert knight.wealth == expected_knight_wealth

        # 国库应减少 amount
        expected_treasury = 200 - amount  # 200 - 85 = 115
        assert state.treasury == expected_treasury

        # 验证战斗力调整
        # 舰队建造合同在 resolve_forum 中调用 naval_system.on_contract_awarded
        naval = state.naval_system
        fleets = naval.get_all_fleets()
        assert len(fleets) == 1
        fleet = fleets[0]
        # 实际成本比例 = actual_cost / original_budget = 72.25 / 100 = 0.7225
        expected_strength = int(round(3 * (actual_cost / contract._original_budget)))
        expected_strength = max(1, min(expected_strength, 6))  # base_strength=3, 上限6
        assert fleet._strength_base == expected_strength

    def test_public_work_budget_bonus(self, basic_state):
        """测试公共工程预算加成：元老院提案时随机加成，通过后合同 base_cost 更新"""
        state, knight, consul, province = basic_state

        # 创建普通工程合同，状态 PENDING
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS,
            province.province_id,
            base_cost=100,
            current_turn=state.turn.turn_number
        )
        contract.name = "Test Works"
        contract.status = ContractStatus.PENDING

        # 模拟执政官提案，传入 modified_budget（模拟加成）
        modified_budget = 120  # 加成20%
        result = senate_api.propose(
            state, "player1", "budget",
            contract_id=contract.id,
            modified_budget=modified_budget
        )
        assert result["success"]

        # 模拟元老院投票通过
        # 获取提案
        proposals = state.get_senate_proposals()
        assert len(proposals) == 1
        proposal = proposals[0]
        # 为所有派系记录赞成票
        for faction in state.get_active_factions():
            player = state.get_player_by_faction(faction.id)
            if player:
                state.record_senate_vote(player.player_id, proposal["id"], True)

        # 执行元老院结算
        result = senate_api.resolve_senate(state)
        print("Senate resolve result message:", result["message"])
        print("Contract base_cost after:", contract.base_cost)
        assert result["success"]

        # 验证合同 base_cost 更新为修改后的预算
        contract = state.get_contract(contract.id)
        assert contract.base_cost == modified_budget
        # 验证原始预算已保存
        assert contract._original_budget == 100

        # 验证合同状态变为 BUDGETED
        assert contract.status == ContractStatus.BUDGETED

    def test_manual_bid_invalid_amount(self, basic_state):
        """测试手动出价限制：金额必须为正数，包税不能低于底价，工程不能高于预算"""
        state, knight, consul, province = basic_state

        # 创建包税合同
        tax_contract = create_tax_contract(state, province.province_id)
        # 创建工程合同
        works_contract = create_public_works_contract(state, province.province_id)

        # 测试出价金额为0或负数
        result = forum_api.place_bid(state, "player1", knight.id, tax_contract.id, 0, 0.2)
        assert not result["success"]
        assert "正整" in result["message"]

        result = forum_api.place_bid(state, "player1", knight.id, tax_contract.id, -10, 0.2)
        assert not result["success"]

        # 测试包税合同出价低于底价
        result = forum_api.place_bid(state, "player1", knight.id, tax_contract.id, 70, 0.2)
        assert not result["success"]
        assert any(phrase in result["message"] for phrase in ["error_bid_too_low", "低于", "底价"])

        # 包税合同出价合法（高于底价），应成功
        result = forum_api.place_bid(state, "player1", knight.id, tax_contract.id, 96, 0.2)
        assert result["success"]

        # 测试工程合同出价高于预算
        works_contract.base_cost = 100
        result = forum_api.place_bid(state, "player1", knight.id, works_contract.id, 120, 0.2)
        assert not result["success"]
        assert any(phrase in result["message"] for phrase in ["error_bid_too_high", "高于", "预算"])

        # 工程合同出价合法（≤预算），应成功
        result = forum_api.place_bid(state, "player1", knight.id, works_contract.id, 80, 0.2)
        assert result["success"]

    def test_manual_bid_default_profit_rate(self, basic_state):
        """测试手动出价默认利润率生效"""
        state, knight, consul, province = basic_state
        contract = create_public_works_contract(state, province.province_id)
        contract.base_cost = 100

        # 不提供利润率，应使用默认0.2
        result = forum_api.place_bid(state, "player1", knight.id, contract.id, 80)  # 不传 profit_rate
        assert result["success"]
        # 检查存储的出价是否包含了默认利润率
        pending = state.get_forum_pending()
        assert len(pending["contract_bids"]) == 1
        _, _, _, _, profit_rate, _, _ = pending["contract_bids"][0]
        assert profit_rate == 0.2

    def test_fleet_contract_multiple_ships(self, basic_state):
        """测试多舰队建造合同的战斗力调整（按总成本比例统一调整）"""
        state, knight, consul, province = basic_state

        # 创建舰队合同，设置推荐组成为2艘 trireme
        contract = create_fleet_contract(state, province.province_id)
        contract._original_budget = 200  # 总预算
        contract._is_fleet_construction = True
        contract._target_war_id = "war1"
        contract._fleet_type = "trireme"
        contract._build_time = 1
        composition = [{"type": "trireme", "count": 2}]
        contract.set_fleet_composition(composition, enemy_strength=10, total_budget=200)

        # 玩家出价，折扣15%
        profit_rate = 0.15
        amount = int(contract.base_cost * (1 - profit_rate))  # 170
        result = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, profit_rate)
        assert result["success"]

        # 结算竞标
        forum_result = forum_api.resolve_forum(state)
        assert forum_result["success"]

        # 验证生成2艘舰队，且每艘强度相同（整体成本比例）
        naval = state.naval_system
        fleets = naval.get_all_fleets()
        assert len(fleets) == 2
        actual_cost = int(amount * (1 - profit_rate))  # 170 * 0.85 = 144
        cost_ratio = actual_cost / contract._original_budget  # 144/200=0.72
        expected_strength = int(round(3 * cost_ratio))  # 2.16 -> 2
        expected_strength = max(1, min(expected_strength, 6))
        for fleet in fleets:
            assert fleet._strength_base == expected_strength

    def test_budget_bonus_random_range(self, basic_state):
        """测试预算加成随机范围配置生效"""
        state, knight, consul, province = basic_state

        # 创建多个合同，测试多次随机
        contracts = []
        for i in range(5):
            contract = state.create_contract(
                ContractType.PUBLIC_WORKS,
                province.province_id,
                base_cost=100,
                current_turn=state.turn.turn_number
            )
            contract.status = ContractStatus.PENDING
            contracts.append(contract)

        # 模拟自动提案生成（需要 budget_decider 和调用 _auto_generate_proposals）
        # 我们手动调用 senate_api.propose 并传入 modified_budget 来模拟随机加成
        margins = []
        for contract in contracts:
            # 模拟随机加成
            r = 0.05 + 0.15 * (contract.id % 10) / 10  # 简单模拟随机
            modified_budget = int(contract.base_cost * (1 + r))
            margins.append(modified_budget)
            result = senate_api.propose(state, "player1", "budget", contract_id=contract.id, modified_budget=modified_budget)
            assert result["success"]

        # 验证所有提案的 modified_budget 都在合理范围内（100~120）
        proposals = state.get_senate_proposals()
        for i, prop in enumerate(proposals):
            assert 100 <= prop["modified_budget"] <= 120

        # 为所有提案投赞成票
        for proposal in proposals:
            for faction in state.get_active_factions():
                player = state.get_player_by_faction(faction.id)
                if player:
                    state.record_senate_vote(player.player_id, proposal["id"], True)

        # 结算元老院
        result = senate_api.resolve_senate(state)
        assert result["success"]

        # 验证每个合同的 base_cost 已更新为修改后的预算
        for i, contract in enumerate(contracts):
            contract = state.get_contract(contract.id)
            assert contract.base_cost == margins[i]

    def test_fleet_contract_payment_in_revenue_phase(self, basic_state):
        """验证舰队合同在收入阶段的资金转移：国库支付中标价，骑士支出实际成本"""
        state, knight, consul, province = basic_state
        state.treasury = 200  # 国库初始资金

        # 创建舰队合同并中标
        contract = create_fleet_contract(state, province.province_id)
        contract._original_budget = 100
        profit_rate = 0.2
        amount = int(contract.base_cost * (1 - profit_rate))  # 80
        result = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, profit_rate)
        assert result["success"]
        forum_result = forum_api.resolve_forum(state)
        assert forum_result["success"]

        # 记录中标前财富
        knight_wealth_before = knight.wealth
        treasury_before = state.treasury

        # 模拟收入阶段结算
        from src.ui.commands.phase_revenue import RevenueCommand
        from src.core.localization import TerminologyService
        rev_cmd = RevenueCommand(state)
        faction_tax_collected = {}
        terms = TerminologyService.get()
        rev_cmd._collect_contract_revenues(terms, faction_tax_collected, 0.1)

        # 验证资金转移
        actual_cost = int(amount * (1 - profit_rate))  # 80 * 0.8 = 64
        profit = amount - actual_cost  # 16
        tax = int(round(profit * 0.1))  # 1.6 → 2
        knight_net = profit - tax  # 14
        expected_knight_wealth = knight_wealth_before + knight_net  # 514
        assert knight.wealth == expected_knight_wealth

        # 国库减少 amount
        expected_treasury = treasury_before - amount
        assert state.treasury == expected_treasury

        # 合同状态：收入阶段仅支付，不标记完成，保持 ACTIVE（舰队建造完成时才变为 COMPLETED）
        contract = state.get_contract(contract.id)
        assert contract.status == ContractStatus.ACTIVE  # 修改：原为 COMPLETED