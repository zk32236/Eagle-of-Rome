# src/tests/test_api/test_forum_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import forum_api
from src.core.entities.player import Player, PlayerType
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.entities.curia import Curia
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    """模拟 GameState，包含必要的属性和方法"""
    state = MagicMock(spec=GameState)

    # 玩家相关
    player = Player("p1", "optimates", PlayerType.HUMAN)
    state.get_player.return_value = player
    state.is_current_player.side_effect = lambda pid: pid == "p1"
    state.get_current_player.return_value = player

    # 派系相关 - 使用 MagicMock，便于断言
    faction = MagicMock(spec=Faction)
    faction.id = "optimates"
    faction.name = "Optimates"
    faction.treasury = 100
    faction.member_ids = []
    faction.get_members = MagicMock(return_value=[])
    state.get_faction.return_value = faction

    # 人物相关 - 使用普通 MagicMock（不指定 spec），直接设置属性
    figure = MagicMock()
    figure.id = 1
    figure.name = "Test Figure"
    figure.faction_id = "optimates"
    figure.is_faction_leader = False
    figure.has_active_contract = False
    figure.is_dead = False
    figure.land_private = 5          # 确保是整数
    figure.wealth = 50
    figure.get_formal_name = MagicMock(return_value="Test Figure")
    state.get_member.return_value = figure

    # Curia - 使用 MagicMock
    curia = MagicMock(spec=Curia)
    curia.get_all_available = MagicMock(return_value=[])
    curia.add_figure = MagicMock()
    curia.remove_figure = MagicMock()
    state.curia = curia

    # 合同相关
    contract = Contract(id=10, contract_type=ContractType.TAX_FARMING, name="Test Contract")
    contract.status = ContractStatus.BUDGETED
    state.get_contract.return_value = contract

    # 广场临时数据存储
    state._forum_pending = {
        "retirements": [],
        "recruitment_bids": [],
        "contract_bids": [],
        "land_purchases": [],
        "triumph_votes": [],
        "land_trades": [],
    }
    state.add_forum_action = MagicMock()
    state.get_forum_pending.return_value = state._forum_pending
    state.clear_forum_pending = MagicMock()

    # 经济规则
    state.get_economic_rule.return_value = 10
    state.get_national_public_land.return_value = 100

    # 派系列表
    state.factions = {"optimates": faction}

    return state


# ========== retire_figure 测试 ==========

def test_retire_figure_success(mock_state):
    """成功淘汰人物"""
    result = forum_api.retire_figure(mock_state, "p1", 1)
    assert result["success"] is True
    assert "已被淘汰" in result["message"]

    faction = mock_state.get_faction.return_value
    faction.remove_member.assert_called_once_with(1)          # 现在可以通过
    mock_state.curia.add_figure.assert_called_once()
    mock_state.add_forum_action.assert_called_once_with("retirements", 1)


def test_retire_figure_not_current_player(mock_state):
    mock_state.is_current_player.return_value = False
    result = forum_api.retire_figure(mock_state, "p2", 1)
    assert result["success"] is False
    assert "当前不是您的回合" in result["message"]


def test_retire_figure_not_in_faction(mock_state):
    figure = mock_state.get_member.return_value
    figure.faction_id = "populares"
    result = forum_api.retire_figure(mock_state, "p1", 1)
    assert result["success"] is False
    assert "不属于你的派系" in result["message"]


def test_retire_figure_is_leader(mock_state):
    figure = mock_state.get_member.return_value
    figure.is_faction_leader = True
    result = forum_api.retire_figure(mock_state, "p1", 1)
    assert result["success"] is False
    assert "不能淘汰派系领袖" in result["message"]


def test_retire_figure_has_active_contract(mock_state):
    figure = mock_state.get_member.return_value
    figure.has_active_contract = True
    result = forum_api.retire_figure(mock_state, "p1", 1)
    assert result["success"] is False
    assert "有活跃合同" in result["message"]


# ========== recruit_figure 测试 ==========

def test_recruit_figure_success(mock_state):
    fig = MagicMock()
    fig.id = 2
    fig.name = "Recruit"
    fig.is_dead = False
    fig.get_formal_name = MagicMock(return_value="Recruit")
    mock_state.curia.get_all_available.return_value = [fig]

    result = forum_api.recruit_figure(mock_state, "p1", 2, 10)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_once_with("recruitment_bids", ("optimates", 2, 10))


def test_recruit_figure_not_in_curia(mock_state):
    mock_state.curia.get_all_available.return_value = []
    result = forum_api.recruit_figure(mock_state, "p1", 99, 10)
    assert result["success"] is False
    assert "不在广场中" in result["message"]


def test_recruit_figure_invalid_amount(mock_state):
    fig = MagicMock()
    fig.id = 2
    mock_state.curia.get_all_available.return_value = [fig]
    result = forum_api.recruit_figure(mock_state, "p1", 2, 0)
    assert result["success"] is False
    assert "金额必须为正整数" in result["message"]


# ========== place_bid 测试 ==========

def test_place_bid_success(mock_state):
    result = forum_api.place_bid(mock_state, "p1", 10, 50)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_once_with("contract_bids", (10, "optimates", 50))


def test_place_bid_contract_not_budgeted(mock_state):
    contract = mock_state.get_contract.return_value
    contract.status = ContractStatus.PENDING
    result = forum_api.place_bid(mock_state, "p1", 10, 50)
    assert result["success"] is False
    assert "不可竞标" in result["message"]


def test_place_bid_invalid_amount(mock_state):
    result = forum_api.place_bid(mock_state, "p1", 10, 0)
    assert result["success"] is False
    assert "金额必须为正整数" in result["message"]


# ========== buy_land 测试 ==========

def test_buy_land_success(mock_state):
    result = forum_api.buy_land(mock_state, "p1", 5)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_once_with("land_purchases", ("optimates", 5))


def test_buy_land_invalid_amount(mock_state):
    result = forum_api.buy_land(mock_state, "p1", 0)
    assert result["success"] is False
    assert "金额必须为正整数" in result["message"]


# ========== vote_triumph 测试 ==========

def test_vote_triumph_success(mock_state):
    result = forum_api.vote_triumph(mock_state, "p1", True)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_once_with("triumph_votes", ("optimates", True))

    result = forum_api.vote_triumph(mock_state, "p1", False)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_with("triumph_votes", ("optimates", False))


# ========== transact_land 测试 ==========

def test_transact_land_success(mock_state):
    seller = MagicMock()
    seller.id = 1
    seller.name = "Seller"
    seller.is_dead = False
    seller.get_formal_name = MagicMock(return_value="Seller")
    buyer = MagicMock()
    buyer.id = 2
    buyer.name = "Buyer"
    buyer.is_dead = False
    buyer.get_formal_name = MagicMock(return_value="Buyer")
    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer

    result = forum_api.transact_land(mock_state, "p1", 1, 2, 3, 50)
    assert result["success"] is True
    mock_state.add_forum_action.assert_called_once_with("land_trades", (1, 2, 3, 50))


def test_transact_land_figure_not_found(mock_state):
    mock_state.get_member.side_effect = lambda fid: None if fid == 1 else MagicMock()
    result = forum_api.transact_land(mock_state, "p1", 1, 2, 3, 50)
    assert result["success"] is False
    assert "不存在" in result["message"]


def test_transact_land_figure_dead(mock_state):
    seller = MagicMock()
    seller.is_dead = True
    buyer = MagicMock()
    buyer.is_dead = False
    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer
    result = forum_api.transact_land(mock_state, "p1", 1, 2, 3, 50)
    assert result["success"] is False
    assert "人物已死亡" in result["message"]


def test_transact_land_invalid_amount(mock_state):
    seller = MagicMock()
    seller.is_dead = False               # 关键：设置 is_dead 为 False
    buyer = MagicMock()
    buyer.is_dead = False                # 关键：设置 is_dead 为 False
    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer

    result = forum_api.transact_land(mock_state, "p1", 1, 2, 0, 50)
    assert result["success"] is False
    assert "金额必须为正整数" in result["message"]


# ========== resolve_forum 测试 ==========

def test_resolve_forum_no_actions(mock_state):
    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "无操作" in result["message"]
    mock_state.clear_forum_pending.assert_called_once()


def test_resolve_forum_recruitment(mock_state):
    mock_state._forum_pending["recruitment_bids"] = [
        ("optimates", 101, 10),
        ("populares", 101, 15),
        ("equites", 101, 10),
    ]
    fig101 = MagicMock()
    fig101.id = 101
    fig101.name = "Target"
    fig101.faction_id = None
    fig101.is_dead = False
    fig101.get_formal_name = MagicMock(return_value="Target")
    mock_state.curia.get_all_available.return_value = [fig101]

    faction_opt = MagicMock(spec=Faction)
    faction_opt.id = "optimates"
    faction_opt.name = "Optimates"
    faction_opt.treasury = 100
    faction_opt.member_ids = []
    faction_pop = MagicMock(spec=Faction)
    faction_pop.id = "populares"
    faction_pop.name = "Populares"
    faction_pop.treasury = 100
    faction_pop.member_ids = []
    faction_eq = MagicMock(spec=Faction)
    faction_eq.id = "equites"
    faction_eq.name = "Equites"
    faction_eq.treasury = 100
    faction_eq.member_ids = []

    def get_faction_side_effect(fid):
        return {"optimates": faction_opt, "populares": faction_pop, "equites": faction_eq}.get(fid)
    mock_state.get_faction.side_effect = get_faction_side_effect
    mock_state.factions = {"optimates": faction_opt, "populares": faction_pop, "equites": faction_eq}

    with patch('random.choice', side_effect=lambda x: x[0]):
        result = forum_api.resolve_forum(mock_state)

    assert result["success"] is True
    assert "Target 加入 Populares，成交价 15" in result["message"]
    assert faction_pop.treasury == 85
    assert fig101.faction_id == "populares"
    mock_state.curia.remove_figure.assert_called_once_with(101)


def test_resolve_forum_contract_bid_tax(mock_state):
    contract = Contract(id=20, contract_type=ContractType.TAX_FARMING, name="Tax Contract")
    contract.status = ContractStatus.BUDGETED
    mock_state.get_contract.return_value = contract
    mock_state._forum_pending["contract_bids"] = [
        (20, "optimates", 100),
        (20, "populares", 120),
    ]
    faction_opt = MagicMock(spec=Faction)
    faction_opt.name = "Optimates"
    faction_pop = MagicMock(spec=Faction)
    faction_pop.name = "Populares"
    mock_state.get_faction.side_effect = lambda fid: {"optimates": faction_opt, "populares": faction_pop}.get(fid)

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "中标者: Populares，出价 120" in result["message"]
    assert contract.status == ContractStatus.ACTIVE


def test_resolve_forum_contract_bid_works(mock_state):
    contract = Contract(id=21, contract_type=ContractType.PUBLIC_WORKS, name="Works Contract")
    contract.status = ContractStatus.BUDGETED
    mock_state.get_contract.return_value = contract
    mock_state._forum_pending["contract_bids"] = [
        (21, "optimates", 80),
        (21, "populares", 70),
        (21, "equites", 75),
    ]
    faction_opt = MagicMock(spec=Faction)
    faction_opt.name = "Optimates"
    faction_pop = MagicMock(spec=Faction)
    faction_pop.name = "Populares"
    faction_eq = MagicMock(spec=Faction)
    faction_eq.name = "Equites"
    mock_state.get_faction.side_effect = lambda fid: {"optimates": faction_opt, "populares": faction_pop, "equites": faction_eq}.get(fid)

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "中标者: Populares，出价 70" in result["message"]
    assert contract.status == ContractStatus.ACTIVE


def test_resolve_forum_land_purchase(mock_state):
    mock_state._forum_pending["land_purchases"] = [
        ("optimates", 5),
        ("populares", 3),
    ]
    mock_state.get_economic_rule.return_value = 10
    mock_state.get_national_public_land.return_value = 100

    faction_opt = MagicMock(spec=Faction)
    faction_opt.id = "optimates"
    faction_opt.name = "Optimates"
    faction_opt.treasury = 100
    faction_opt.get_members = MagicMock(return_value=[MagicMock(influence=50)])

    faction_pop = MagicMock(spec=Faction)
    faction_pop.id = "populares"
    faction_pop.name = "Populares"
    faction_pop.treasury = 50
    faction_pop.get_members = MagicMock(return_value=[MagicMock(influence=30)])

    mock_state.get_faction.side_effect = lambda fid: {"optimates": faction_opt, "populares": faction_pop}.get(fid)
    mock_state.factions = {"optimates": faction_opt, "populares": faction_pop}

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Optimates 认购 5 C 公地，花费 50" in result["message"]
    assert "Populares 认购 3 C 公地，花费 30" in result["message"]
    assert faction_opt.treasury == 50
    assert faction_pop.treasury == 20
    mock_state.add_national_public_land.assert_any_call(-5)
    mock_state.add_national_public_land.assert_any_call(-3)


def test_resolve_forum_land_purchase_insufficient_land(mock_state):
    mock_state._forum_pending["land_purchases"] = [
        ("optimates", 80),
        ("populares", 30),
    ]
    mock_state.get_national_public_land.return_value = 100
    mock_state.get_economic_rule.return_value = 10

    faction_opt = MagicMock(spec=Faction)
    faction_opt.id = "optimates"
    faction_opt.name = "Optimates"
    faction_opt.treasury = 1000
    faction_opt.get_members = MagicMock(return_value=[MagicMock(influence=50)])

    faction_pop = MagicMock(spec=Faction)
    faction_pop.id = "populares"
    faction_pop.name = "Populares"
    faction_pop.treasury = 1000
    faction_pop.get_members = MagicMock(return_value=[MagicMock(influence=30)])

    mock_state.get_faction.side_effect = lambda fid: {"optimates": faction_opt, "populares": faction_pop}.get(fid)
    mock_state.factions = {"optimates": faction_opt, "populares": faction_pop}

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Optimates 认购 80 C 公地，花费 800" in result["message"]
    assert "Populares 认购 20 C 公地，花费 200" in result["message"]


def test_resolve_forum_triumph_vote_pass(mock_state):
    mock_state._forum_pending["triumph_votes"] = [
        ("optimates", True),
        ("populares", False),
        ("equites", True),
    ]
    faction_opt = MagicMock(spec=Faction)
    faction_opt.get_members = MagicMock(return_value=[MagicMock(influence=50)])
    faction_pop = MagicMock(spec=Faction)
    faction_pop.get_members = MagicMock(return_value=[MagicMock(influence=30)])
    faction_eq = MagicMock(spec=Faction)
    faction_eq.get_members = MagicMock(return_value=[MagicMock(influence=20)])

    mock_state.get_faction.side_effect = lambda fid: {
        "optimates": faction_opt,
        "populares": faction_pop,
        "equites": faction_eq
    }.get(fid)
    mock_state.factions = {"optimates": faction_opt, "populares": faction_pop, "equites": faction_eq}

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "凯旋仪式获得批准（支持率 70.0%" in result["message"]


def test_resolve_forum_triumph_vote_fail(mock_state):
    mock_state._forum_pending["triumph_votes"] = [
        ("optimates", True),
        ("populares", False),
        ("equites", False),
    ]
    faction_opt = MagicMock(spec=Faction)
    faction_opt.get_members = MagicMock(return_value=[MagicMock(influence=50)])
    faction_pop = MagicMock(spec=Faction)
    faction_pop.get_members = MagicMock(return_value=[MagicMock(influence=30)])
    faction_eq = MagicMock(spec=Faction)
    faction_eq.get_members = MagicMock(return_value=[MagicMock(influence=20)])

    mock_state.get_faction.side_effect = lambda fid: {
        "optimates": faction_opt,
        "populares": faction_pop,
        "equites": faction_eq
    }.get(fid)
    mock_state.factions = {"optimates": faction_opt, "populares": faction_pop, "equites": faction_eq}

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "凯旋仪式被否决（支持率 50.0%" in result["message"]


def test_resolve_forum_land_trade_insufficient_land(mock_state):
    seller = MagicMock()
    seller.id = 1
    seller.name = "Seller"
    seller.get_formal_name = MagicMock(return_value="Seller")
    seller.land_private = 2
    seller.wealth = 50
    seller.is_dead = False

    buyer = MagicMock()
    buyer.id = 2
    buyer.name = "Buyer"
    buyer.get_formal_name = MagicMock(return_value="Buyer")
    buyer.land_private = 0
    buyer.wealth = 100
    buyer.is_dead = False

    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer
    mock_state._forum_pending["land_trades"] = [(1, 2, 3, 30)]

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Seller 土地不足" in result["message"]
    assert seller.land_private == 2
    assert buyer.land_private == 0
    assert seller.wealth == 50
    assert buyer.wealth == 100


def test_resolve_forum_land_trade_insufficient_wealth(mock_state):
    seller = MagicMock()
    seller.id = 1
    seller.name = "Seller"
    seller.get_formal_name = MagicMock(return_value="Seller")
    seller.land_private = 10
    seller.wealth = 50
    seller.is_dead = False

    buyer = MagicMock()
    buyer.id = 2
    buyer.name = "Buyer"
    buyer.get_formal_name = MagicMock(return_value="Buyer")
    buyer.land_private = 0
    buyer.wealth = 20
    buyer.is_dead = False

    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer
    mock_state._forum_pending["land_trades"] = [(1, 2, 3, 30)]

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Buyer 财富不足" in result["message"]
    assert seller.land_private == 10
    assert buyer.land_private == 0
    assert seller.wealth == 50
    assert buyer.wealth == 20

def test_resolve_forum_land_trade_success(mock_state):
    class MockFigure:
        def __init__(self, id, name, land_private, wealth, is_dead):
            self.id = id
            self.name = name
            self._land_private = land_private
            self.wealth = wealth
            self.is_dead = is_dead
        @property
        def land_private(self):
            return self._land_private
        @land_private.setter
        def land_private(self, value):
            self._land_private = value
        def get_formal_name(self):
            return self.name

    seller = MockFigure(1, "Seller", 10, 50, False)
    buyer = MockFigure(2, "Buyer", 0, 100, False)

    mock_state.get_member.side_effect = lambda fid: seller if fid == 1 else buyer
    mock_state._forum_pending["land_trades"] = [(1, 2, 3, 30)]

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Seller 出售 3 C 土地给 Buyer，价格 30" in result["message"]
    assert seller.land_private == 7
    assert buyer.land_private == 3
    assert seller.wealth == 80
    assert buyer.wealth == 70


def test_resolve_forum_mixed_actions(mock_state):
    class MockFigure:
        def __init__(self, id, name, land_private, wealth, is_dead):
            self.id = id
            self.name = name
            self._land_private = land_private
            self.wealth = wealth
            self.is_dead = is_dead
        @property
        def land_private(self):
            return self._land_private
        @land_private.setter
        def land_private(self, value):
            self._land_private = value
        def get_formal_name(self):
            return self.name

    # 招募人物
    fig101 = MockFigure(101, "Target", 0, 0, False)
    fig101.faction_id = None
    mock_state.curia.get_all_available.return_value = [fig101]

    # 土地交易人物
    seller = MockFigure(1, "Seller", 10, 50, False)
    buyer = MockFigure(2, "Buyer", 0, 100, False)

    # 其他数据设置保持不变...
    mock_state._forum_pending["recruitment_bids"] = [("optimates", 101, 10)]
    mock_state._forum_pending["contract_bids"] = [(20, "optimates", 100)]
    mock_state._forum_pending["land_purchases"] = [("optimates", 5)]
    mock_state._forum_pending["triumph_votes"] = [("optimates", True)]
    mock_state._forum_pending["land_trades"] = [(1, 2, 3, 30)]

    mock_state.get_member.side_effect = lambda fid: {
        1: seller,
        2: buyer,
        101: fig101
    }.get(fid)

    faction_opt = MagicMock(spec=Faction)
    faction_opt.id = "optimates"
    faction_opt.name = "Optimates"
    faction_opt.treasury = 200
    faction_opt.member_ids = []
    faction_opt.get_members = MagicMock(return_value=[MagicMock(influence=50)])

    mock_state.get_faction.return_value = faction_opt
    mock_state.factions = {"optimates": faction_opt}
    mock_state.get_economic_rule.return_value = 10
    mock_state.get_national_public_land.return_value = 100

    result = forum_api.resolve_forum(mock_state)
    assert result["success"] is True
    assert "Target 加入 Optimates，成交价 10" in result["message"]
    assert "中标者: Optimates，出价 100" in result["message"]
    assert "Optimates 认购 5 C 公地，花费 50" in result["message"]
    assert "凯旋仪式获得批准（支持率 100.0%" in result["message"]
    assert "Seller 出售 3 C 土地给 Buyer，价格 30" in result["message"]
    assert faction_opt.treasury == 200 - 10 - 50
    assert seller.land_private == 7
    assert buyer.land_private == 3
    assert seller.wealth == 80
    assert buyer.wealth == 70
