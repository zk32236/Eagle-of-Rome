# src/tests/test_deciders/test_auto_deciders.py
"""
决策器单元测试 - 自动决策器
"""
import pytest
import random
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import War, WarStatus
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.core.deciders.impl.auto_land_trade_decider import AutoLandTradeDecider
from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider


@pytest.fixture
def test_state():
    """基础游戏状态"""
    state = MagicMock(spec=GameState)
    state.config.get = MagicMock(return_value=0.3)  # retirement_chance
    state.get_economic_rule = MagicMock(return_value=6)  # faction_member_limit
    state.log_event = MagicMock()
    return state


@pytest.fixture
def faction():
    """派系"""
    faction = MagicMock(spec=Faction)
    faction.id = "f1"
    faction.name = "TestFaction"
    faction.treasury = 100
    return faction


@pytest.fixture
def members():
    """派系成员列表 - 已添加 name 属性"""
    members = []
    for i in range(5):
        fig = MagicMock(spec=Figure)
        fig.id = i
        fig.name = f"Member{i}"          # 添加 name
        fig.is_faction_leader = (i == 0)
        fig.office = None if i < 3 else "consul"
        fig.has_active_contract = False
        fig.class_tier = ClassTier.EQUES if i % 2 else ClassTier.NOBILE
        fig.is_dead = False
        members.append(fig)
    return members


@pytest.fixture
def available_figures():
    """广场可用人物 - 已添加 name"""
    figs = []
    for i in range(10, 15):
        fig = MagicMock(spec=Figure)
        fig.id = i
        fig.name = f"Figure{i}"
        fig.class_tier = ClassTier.EQUES
        fig.is_dead = False
        fig.abandoned_by = None
        figs.append(fig)
    return figs


class TestAutoRetirementDecider:
    """测试自动淘汰决策器"""

    def test_decide_whom_to_retire_success(self, test_state, faction, members):
        """有合格淘汰者时返回一个人物ID"""
        faction.get_members.return_value = members
        members[1].is_faction_leader = False
        members[1].office = None
        members[1].has_active_contract = False

        decider = AutoRetirementDecider(test_state)
        with patch('random.random', return_value=0.2):
            with patch('random.choice', return_value=members[1]):
                result = decider.decide_whom_to_retire(faction)
                assert result == members[1].id
                test_state.log_event.assert_called()

    def test_no_eligible(self, test_state, faction, members):
        """无合格淘汰者时返回None"""
        for m in members:
            m.is_faction_leader = True
        faction.get_members.return_value = members

        decider = AutoRetirementDecider(test_state)
        with patch('random.random', return_value=0.2):
            result = decider.decide_whom_to_retire(faction)
            assert result is None

    def test_random_chance_miss(self, test_state, faction, members):
        """随机概率未触发时返回None"""
        faction.get_members.return_value = members
        decider = AutoRetirementDecider(test_state)
        with patch('random.random', return_value=0.5):
            result = decider.decide_whom_to_retire(faction)
            assert result is None


class TestAutoRecruitmentDecider:
    """测试自动招募决策器"""

    def test_decide_bids_with_vacancies(self, test_state, faction, available_figures):
        """有空缺时返回出价字典"""
        vacancies = 2
        faction.treasury = 100
        faction.get_members.return_value = []
        test_state.config.get.return_value = 6

        decider = AutoRecruitmentDecider()
        with patch('random.randint', return_value=30):
            with patch('random.shuffle', side_effect=lambda x: None):
                result = decider.decide_bids(faction, available_figures, vacancies, test_state)

        assert len(result) == vacancies
        for fig_id, amount in result.items():
            assert fig_id in [10, 11]
            assert amount == 30

    def test_no_vacancies(self, test_state, faction, available_figures):
        """无空缺时返回空字典"""
        vacancies = 0
        result = AutoRecruitmentDecider().decide_bids(faction, available_figures, vacancies, test_state)
        assert result == {}

    def test_treasury_zero(self, test_state, faction, available_figures):
        """国库为0时返回空字典"""
        faction.treasury = 0
        result = AutoRecruitmentDecider().decide_bids(faction, available_figures, 2, test_state)
        assert result == {}


class TestAutoBidDecider:
    """测试自动竞标决策器"""

    def test_decide_tax_bid(self, test_state):
        """包税合同出价"""
        contract = MagicMock(spec=Contract)
        contract.id = 1
        contract.base_cost = 100
        knights = [MagicMock(spec=Figure) for _ in range(3)]
        for i, k in enumerate(knights):
            k.id = 10 + i
            k.name = f"Knight{k.id}"          # 添加 name

        decider = AutoBidDecider()
        with patch('random.choice', return_value=knights[0]):
            with patch('random.uniform', return_value=0.1):
                result = decider.decide_tax_bid(contract, knights, test_state)

        assert result is not None
        knight, amount, r = result
        assert knight == knights[0]
        assert amount == 110
        assert r == 0.1

    def test_decide_works_bid(self, test_state):
        """工程合同出价"""
        contract = MagicMock(spec=Contract)
        contract.id = 2
        contract.base_cost = 200
        knights = [MagicMock(spec=Figure) for _ in range(3)]
        for i, k in enumerate(knights):
            k.id = 10 + i
            k.name = f"Knight{k.id}"          # 添加 name

        decider = AutoBidDecider()
        with patch('random.choice', return_value=knights[0]):
            with patch('random.uniform', return_value=0.15):
                result = decider.decide_works_bid(contract, knights, test_state)

        assert result is not None
        knight, amount, r, construction, warranty = result
        assert knight == knights[0]
        assert amount == 170
        assert r == 0.15

    def test_decide_fleet_bid(self, test_state):
        """舰队建造合同出价"""
        contract = MagicMock(spec=Contract)
        contract.id = 3
        contract.base_cost = 80
        contract.total_budget = 80
        knights = [MagicMock(spec=Figure)]
        knights[0].id = 100
        knights[0].name = "Knight100"         # 添加 name

        decider = AutoBidDecider()
        with patch('random.choice', return_value=knights[0]):
            with patch('random.uniform', return_value=0.12):
                result = decider.decide_fleet_bid(contract, knights, test_state)

        assert result is not None
        knight, amount, r = result
        assert knight == knights[0]
        assert amount == 70
        assert r == 0.12


class TestAutoLandTradeDecider:
    """测试自动土地交易决策器"""

    def test_decide_trade_success(self, test_state):
        """成功选择一对贵族和骑士进行交易"""
        nobles = []
        equites = []
        for i in range(3):
            noble = MagicMock(spec=Figure)
            noble.id = i
            noble.name = f"Noble{i}"          # 添加 name
            noble.class_tier = ClassTier.NOBILE
            noble.land_private = 5
            nobles.append(noble)

            equite = MagicMock(spec=Figure)
            equite.id = i + 10
            equite.name = f"Equite{i}"        # 添加 name
            equite.class_tier = ClassTier.EQUES
            equite.land_private = 0
            equites.append(equite)

        test_state.get_living_members.return_value = nobles + equites

        decider = AutoLandTradeDecider()
        with patch('random.choice', side_effect=[nobles[0], equites[1]]):
            with patch('random.randint', return_value=3):
                result = decider.decide_trade(test_state)

        assert result == (0, 11, 3)

    def test_no_nobles_or_equites(self, test_state):
        """缺少贵族或骑士时返回None"""
        # 只有贵族
        noble = MagicMock(spec=Figure, class_tier=ClassTier.NOBILE)
        noble.name = "NobleOnly"               # 添加 name
        test_state.get_living_members.return_value = [noble]
        decider = AutoLandTradeDecider()
        assert decider.decide_trade(test_state) is None

        # 只有骑士
        equite = MagicMock(spec=Figure, class_tier=ClassTier.EQUES)
        equite.name = "EquiteOnly"             # 添加 name
        test_state.get_living_members.return_value = [equite]
        assert decider.decide_trade(test_state) is None

    def test_seller_no_land(self, test_state):
        """卖家无私地时返回None"""
        nobles = [MagicMock(spec=Figure)]
        nobles[0].id = 1                     # 添加 id
        nobles[0].class_tier = ClassTier.NOBILE
        nobles[0].land_private = 0
        nobles[0].name = "Noble0"
        equites = [MagicMock(spec=Figure)]
        equites[0].id = 2                     # 添加 id
        equites[0].class_tier = ClassTier.EQUES
        equites[0].name = "Equite0"

        test_state.get_living_members.return_value = nobles + equites

        decider = AutoLandTradeDecider()
        with patch('random.choice', side_effect=[nobles[0], equites[0]]):
            result = decider.decide_trade(test_state)
        assert result is None


class TestAutoTriumphDecider:
    """测试自动凯旋决策器"""

    def test_decide_triumph(self, test_state):
        """根据概率返回 True/False"""
        war = MagicMock(spec=War)
        war.id = "war1"
        war.name = "TestWar"
        commander = MagicMock(spec=Figure)
        commander.id = 1
        commander.name = "Commander"

        test_state.config.get.return_value = 0.5

        decider = AutoTriumphDecider()
        with patch('random.random', return_value=0.3):
            assert decider.decide_triumph(war, commander, test_state) is True
        with patch('random.random', return_value=0.7):
            assert decider.decide_triumph(war, commander, test_state) is False