# src/tests/test_commands/test_phase_forum_fleet.py
"""
舰队建造专项测试 - 广场阶段
"""
import pytest
from unittest.mock import MagicMock, patch, call
from io import StringIO

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.systems.war_system import WarSystem
from src.core.systems.naval_system import NavalSystem
from src.core.entities.war import War, WarStatus
from src.ui.commands.phase_forum import ForumCommand
from src.api import forum_api
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def test_state():
    """创建测试用游戏状态"""
    config = {
        "testing": {
            "auto_forum": False,
            "bypass_player_check": False,
        },
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "initial_national_public_land": 1000,
        },
        "political_rules": {
            "retirement_chance": 0.3,
        },
        "forum_rules": {
            "new_figures_count": 3,
            "class_probabilities": {"nobile": 0.5, "eques": 0.3, "plebeian": 0.2},
        },
        "combat_rules": {"triumph_veteran_duration": 5},
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)

    # 添加玩家
    player1 = Player("p1", "f1", PlayerType.HUMAN)
    player2 = Player("p2", "f2", PlayerType.AI)
    player3 = Player("p3", "f3", PlayerType.AI)
    state.add_player(player1)
    state.add_player(player2)
    state.add_player(player3)
    state.set_turn_order(["p1", "p2", "p3"])
    state.set_current_player("p1")

    # 添加派系
    faction1 = Faction("f1", "Faction1", treasury=100)
    faction2 = Faction("f2", "Faction2", treasury=100)
    faction3 = Faction("f3", "Faction3", treasury=100)
    state.add_faction(faction1)
    state.add_faction(faction2)
    state.add_faction(faction3)

    # 添加人物
    for i in range(1, 7):
        fig = Figure.create_nobile(i, "f1", 30 + i) if i <= 3 else Figure.create_eques(i, "f1", 25 + i)
        fig.is_faction_leader = (i == 1)
        fig._land_private = 2
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction1.member_ids.append(i)

    for i in range(7, 13):
        fig = Figure.create_nobile(i, "f2", 30 + i) if i <= 9 else Figure.create_eques(i, "f2", 25 + i)
        fig.is_faction_leader = (i == 7)
        fig._land_private = 1
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction2.member_ids.append(i)

    for i in range(13, 19):
        fig = Figure.create_nobile(i, "f3", 30 + i) if i <= 15 else Figure.create_eques(i, "f3", 25 + i)
        fig.is_faction_leader = (i == 13)
        fig._land_private = 1
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction3.member_ids.append(i)

    # 添加行省（意大利）
    italy = Province(
        province_id=0,
        name="意大利",
        total_land=1000,
        land_public=500,
        land_private=500,
        conquered=True,
    )
    state.add_province(italy)

    # 添加战争系统
    war_system = WarSystem(state)
    state._war_system = war_system

    # 添加海军系统
    naval_system = NavalSystem(state)
    state._naval_system = naval_system

    # 标记皮洛士战争胜利，解锁海军
    state._pyrrhic_war_won = True

    return state


@pytest.fixture
def mock_deciders():
    """创建 mock 决策器"""
    retirement = MagicMock()
    recruitment = MagicMock()
    bid = MagicMock()
    land_trade = MagicMock()
    triumph = MagicMock()
    return retirement, recruitment, bid, land_trade, triumph


class TestForumFleet:
    """舰队建造专项测试"""

    def setup_threat_war(self, test_state, naval_required=True):
        """设置一个威胁战争"""
        threat_war = War(id="threat1", name="Threat War")
        threat_war._status = WarStatus.THREAT
        threat_war._naval_required = naval_required
        war_system = test_state.get_war_system()
        war_system._threats = [threat_war]
        return threat_war

    def test_fleet_contract_generated_on_threat(self, test_state, mock_deciders):
        """威胁战争触发舰队合同生成"""
        self.setup_threat_war(test_state, naval_required=True)

        # mock 海军系统的方法，返回非空列表
        mock_contract = MagicMock()
        test_state._naval_system.generate_construction_contracts = MagicMock(return_value=[mock_contract])
        test_state._naval_system.generate_replacement_contracts = MagicMock(return_value=[])

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            cmd._generate_contracts()
        output = mock_stdout.getvalue()
        assert "检测到海战威胁，生成 1 个舰队建造合同" in output
        test_state._naval_system.generate_construction_contracts.assert_called_once()

    def test_fleet_contract_bid_recorded(self, test_state, mock_deciders):
        """舰队合同竞标记录包含人物ID，且中标后调用海军系统"""
        fleet_contract = Contract(
            id=100,
            contract_type=ContractType.PUBLIC_WORKS,
            name="舰队建造合同",
            base_cost=80,
            status=ContractStatus.BUDGETED,
        )
        fleet_contract._is_fleet_construction = True
        test_state._contracts_dict[100] = fleet_contract

        test_state.add_forum_action("contract_bids", (100, 2, "f1", 70, 0.2, 1, 0))

        # 替换为 MagicMock
        test_state._naval_system.on_contract_awarded = MagicMock()

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        contract = test_state.get_contract(100)
        assert contract.awarded_to == 2
        test_state._naval_system.on_contract_awarded.assert_called_once_with(contract, 2)

    def test_fleet_contract_awarded_triggers_construction(self, test_state, mock_deciders):
        """舰队合同中标后调用海军系统开始建造"""
        # 创建舰队建造合同
        fleet_contract = Contract(
            id=101,
            contract_type=ContractType.PUBLIC_WORKS,
            name="舰队建造合同",
            base_cost=80,
            status=ContractStatus.BUDGETED,
        )
        fleet_contract._is_fleet_construction = True
        test_state._contracts_dict[101] = fleet_contract

        # 添加出价
        test_state.add_forum_action("contract_bids", (101, 2, "f1", 70, 0.2, 1, 0))

        # mock 海军系统的 on_contract_awarded 方法
        test_state._naval_system.on_contract_awarded = MagicMock()

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        # 直接调用 resolve_forum
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        contract = test_state.get_contract(101)
        test_state._naval_system.on_contract_awarded.assert_called_once_with(contract, 2)