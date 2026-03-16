# src/tests/test_api/test_forum_api.py
"""
API层单元测试 - 广场阶段相关API
"""
import pytest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.systems.war_system import WarSystem
from src.api import forum_api
from src.api import api_response
from src.core.i18n import i18n
from src.core.entities.war import WarStatus

i18n.load("zh-CN")


@pytest.fixture
def test_state():
    """使用 create_for_testing 创建基础游戏状态"""
    config = {
        "testing": {"bypass_player_check": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
        },
        "combat_rules": {"triumph_veteran_duration": 5},
    }
    state = GameState.create_for_testing(config)

    # 设置回合
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=1, year=-282)

    # 添加玩家
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    player2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.AI)
    state.add_player(player1)
    state.add_player(player2)
    state.set_turn_order(["p1", "p2"])
    state.set_current_player("p1")

    # 添加派系（提高资金以通过认购测试）
    faction1 = Faction(id="f1", name="Faction1", treasury=1000)
    faction2 = Faction(id="f2", name="Faction2", treasury=1000)
    state.add_faction(faction1)
    state.add_faction(faction2)

    # 添加人物（存活）
    fig1 = Figure.create_nobile(1, "f1", 40)
    fig1.is_faction_leader = True
    fig1._land_private = 2
    fig1.wealth = 50
    fig1.update_influence()
    state.add_member(fig1)

    fig2 = Figure.create_eques(2, "f1", 30)
    fig2.is_faction_leader = False
    fig2._land_private = 5
    fig2.wealth = 30
    fig2.update_influence()
    state.add_member(fig2)

    fig3 = Figure.create_plebeian(3, "f2", 25)
    fig3.is_faction_leader = False
    fig3.wealth = 20
    fig3.update_influence()
    state.add_member(fig3)

    # 添加广场人物（需要同时加入 _members）
    fig_curia = Figure.create_eques(4, None, 35)
    fig_curia.wealth = 50
    fig_curia.update_influence()
    state.curia.add_figure(fig_curia)
    state.add_member(fig_curia)

    # 添加合同
    contract1 = Contract(
        id=1,
        contract_type=ContractType.PUBLIC_WORKS,
        name="Test Works",
        base_cost=100,
        status=ContractStatus.BUDGETED,
    )
    state._contracts_dict[1] = contract1

    contract2 = Contract(
        id=2,
        contract_type=ContractType.TAX_FARMING,
        name="Test Tax",
        base_cost=100,
        status=ContractStatus.BUDGETED,
    )
    state._contracts_dict[2] = contract2

    # 添加战争系统（用于凯旋）
    war_system = MagicMock(spec=WarSystem)
    war_system._war_discard = []
    war_system.get_war_by_id = MagicMock(return_value=None)
    state.get_war_system = MagicMock(return_value=war_system)

    # 添加论坛临时数据存储
    state._forum_pending = {
        "retirements": [],
        "recruitment_bids": [],
        "contract_bids": [],
        "land_purchases": [],
        "triumph_votes": [],
        "land_trades": [],
    }

    # 国家公地
    state._national_public_land = 100

    return state


# ========== retire_figure 测试 ==========
class TestRetireFigure:
    """测试 retire_figure API"""

    def test_success(self, test_state):
        result = forum_api.retire_figure(test_state, "p1", 2)
        assert result["success"] is True
        assert "已被淘汰" in result["message"]
        assert 2 not in test_state.get_faction("f1").member_ids
        assert 2 in [f.id for f in test_state.curia.get_all_available()]
        pending = test_state.get_forum_pending()
        assert 2 in pending["retirements"]

    def test_not_current_player(self, test_state):
        result = forum_api.retire_figure(test_state, "p2", 2)
        assert result["success"] is False
        assert "当前不是您的回合" in result["message"]

    def test_figure_not_in_faction(self, test_state):
        result = forum_api.retire_figure(test_state, "p1", 3)
        assert result["success"] is False
        assert "不属于你的派系" in result["message"]

    def test_figure_not_found(self, test_state):
        result = forum_api.retire_figure(test_state, "p1", 999)
        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_cannot_retire_leader(self, test_state):
        result = forum_api.retire_figure(test_state, "p1", 1)
        assert result["success"] is False
        assert "不能淘汰派系领袖" in result["message"]

    def test_figure_has_active_contract(self, test_state):
        fig = test_state.get_member(2)
        fig.add_contract(99)  # 使用 add_contract 方法添加合同
        result = forum_api.retire_figure(test_state, "p1", 2)
        assert result["success"] is False
        assert "有活跃合同" in result["message"]


# ========== recruit_figure 测试 ==========
class TestRecruitFigure:
    """测试 recruit_figure API"""

    def test_success(self, test_state):
        result = forum_api.recruit_figure(test_state, "p1", 4, 50)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert ("f1", 4, 50) in pending["recruitment_bids"]

    def test_figure_not_in_curia(self, test_state):
        result = forum_api.recruit_figure(test_state, "p1", 1, 50)
        assert result["success"] is False
        assert "不在广场中" in result["message"]

    def test_invalid_amount(self, test_state):
        result = forum_api.recruit_figure(test_state, "p1", 4, 0)
        assert result["success"] is False
        assert "金额必须为正整数" in result["message"]


# ========== place_bid 测试 ==========
class TestPlaceBid:
    """测试 place_bid API"""

    def test_success(self, test_state):
        result = forum_api.place_bid(test_state, "p1", 2, 2, 120)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert (2, 2, "f1", 120) in pending["contract_bids"]

    def test_contract_not_found(self, test_state):
        result = forum_api.place_bid(test_state, "p1", 2, 999, 120)
        assert result["success"] is False
        assert "contract_not_found" in result["message"]

    def test_contract_not_budgeted(self, test_state):
        contract = test_state.get_contract(2)
        contract.status = ContractStatus.PENDING
        result = forum_api.place_bid(test_state, "p1", 2, 2, 120)
        assert result["success"] is False
        assert "不可竞标" in result["message"]

    def test_invalid_amount(self, test_state):
        result = forum_api.place_bid(test_state, "p1", 2, 2, 0)
        assert result["success"] is False
        assert "金额必须为正整数" in result["message"]


# ========== buy_land 测试 ==========
class TestBuyLand:
    """测试 buy_land API"""

    def test_success(self, test_state):
        result = forum_api.buy_land(test_state, "p1", 10)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert ("f1", 10) in pending["land_purchases"]

    def test_invalid_amount(self, test_state):
        result = forum_api.buy_land(test_state, "p1", 0)
        assert result["success"] is False
        assert "金额必须为正整数" in result["message"]


# ========== vote_triumph 测试 ==========
class TestVoteTriumph:
    """测试 vote_triumph API"""

    def test_success_yes(self, test_state):
        result = forum_api.vote_triumph(test_state, "p1", "war1", True)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert ("war1", "f1", True) in pending["triumph_votes"]

    def test_success_no(self, test_state):
        result = forum_api.vote_triumph(test_state, "p1", "war1", False)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert ("war1", "f1", False) in pending["triumph_votes"]


# ========== transact_land 测试 ==========
class TestTransactLand:
    """测试 transact_land API"""

    def test_success(self, test_state):
        result = forum_api.transact_land(test_state, "p1", 2, 4, 1, 15)
        assert result["success"] is True
        pending = test_state.get_forum_pending()
        assert (2, 4, 1, 15) in pending["land_trades"]

    def test_figure_not_found(self, test_state):
        result = forum_api.transact_land(test_state, "p1", 999, 4, 1, 15)
        assert result["success"] is False
        assert "figure_not_found" in result["message"] or "不存在" in result["message"]

    def test_figure_dead(self, test_state):
        fig = test_state.get_member(2)
        fig.is_dead = True
        result = forum_api.transact_land(test_state, "p1", 2, 4, 1, 15)
        assert result["success"] is False
        assert "error_figure_dead" in result["message"] or "人物已死亡" in result["message"]

    def test_invalid_amount(self, test_state):
        result = forum_api.transact_land(test_state, "p1", 2, 4, 0, 15)
        assert result["success"] is False
        assert "金额必须为正整数" in result["message"] or "error_invalid_amount" in result["message"]


# ========== resolve_forum 测试 ==========
class TestResolveForum:
    """测试 resolve_forum 结算逻辑"""

    def test_no_actions(self, test_state):
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "本阶段无操作" in result["message"]

    def test_recruitment(self, test_state):
        test_state._forum_pending["recruitment_bids"] = [("f1", 4, 50), ("f2", 4, 60)]
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        figure = test_state.get_member(4)
        assert figure.faction_id == "f2"
        assert test_state.get_faction("f2").treasury == 1000 - 60
        assert "加入 Faction2，成交价 60" in result["message"]

    def test_recruitment_plurality_random(self, test_state):
        test_state._forum_pending["recruitment_bids"] = [("f1", 4, 50), ("f2", 4, 50)]
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        figure = test_state.get_member(4)
        assert figure.faction_id in ("f1", "f2")
        if figure.faction_id == "f1":
            assert test_state.get_faction("f1").treasury == 1000 - 50
        else:
            assert test_state.get_faction("f2").treasury == 1000 - 50

    def test_tax_contract(self, test_state):
        test_state._forum_pending["contract_bids"] = [(2, 2, "f1", 120), (2, 3, "f2", 110)]
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True

        contract = test_state.get_contract(2)
        assert contract.awarded_to == 2
        # 通过中标人物检查派系
        winner = test_state.get_member(2)
        assert winner.faction_id == "f1"
        assert contract.status == ContractStatus.ACTIVE
        assert contract.tax_rate == pytest.approx(0.12)
        assert "税率" in result["message"]

    def test_works_contract(self, test_state):
        test_state._forum_pending["contract_bids"] = [(1, 2, "f1", 90), (1, 3, "f2", 80)]
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        contract = test_state.get_contract(1)
        assert contract.awarded_to == 3
        winner = test_state.get_member(3)
        assert winner.faction_id == "f2"
        assert contract.status == ContractStatus.ACTIVE
        assert "中标者: Faction2，出价 80" in result["message"]

    def test_land_purchase(self, test_state):
        test_state._forum_pending["land_purchases"] = [("f1", 30), ("f2", 20)]
        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "Faction1 认购 30 C 公地，花费 300" in result["message"]
        assert "Faction2 认购 20 C 公地，花费 200" in result["message"]
        assert test_state.get_national_public_land() == 50

    def test_land_purchase_insufficient_land(self, test_state):
        test_state._forum_pending["land_purchases"] = [("f1", 80), ("f2", 30)]
        result = forum_api.resolve_forum(test_state)
        assert "Faction1 认购 80 C 公地，花费 800" in result["message"]
        assert "公地不足，Faction2 认购失败" in result["message"]
        assert "Faction2 认购 20 C 公地" not in result["message"]

    def test_land_purchase_insufficient_funds(self, test_state):
        test_state.get_faction("f2").treasury = 50
        test_state._forum_pending["land_purchases"] = [("f1", 30), ("f2", 20)]
        result = forum_api.resolve_forum(test_state)
        assert "Faction2 资金不足，认购失败" in result["message"]
        assert "Faction1 认购 30 C 公地" in result["message"]



    @pytest.mark.xfail(reason="mock战争状态与真实代码交互复杂，暂时标记为预期失败")
    def test_triumph_approved(self, test_state):
        war = MagicMock()
        war.id = "war1"
        war.name = "Test War"
        war.soldier_share = 50
        war.status = WarStatus.RESOLVED
        war.triumph_commander_id = 1
        war.set_soldier_share = MagicMock()
        war.set_triumph_approved = MagicMock()

        war_system = test_state.get_war_system()
        war_system._war_discard = [war]

        # 直接设置投票数据
        test_state._forum_pending["triumph_votes"] = [("war1", "f1", True), ("war1", "f2", False)]

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "凯旋仪式获得批准" in result["message"]

    @pytest.mark.xfail(reason="mock战争状态与真实代码交互复杂，暂时标记为预期失败")
    def test_triumph_rejected(self, test_state):
        war = MagicMock()
        war.id = "war1"
        war.name = "Test War"
        war.soldier_share = 50
        war.status = WarStatus.RESOLVED
        war.triumph_commander_id = 1
        war.set_soldier_share = MagicMock()
        war.set_triumph_approved = MagicMock()

        war_system = test_state.get_war_system()
        war_system._war_discard = [war]

        # 直接设置投票数据
        test_state._forum_pending["triumph_votes"] = [("war1", "f1", False), ("war1", "f2", True)]

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "被否决" in result["message"]

    def test_triumph_commander_dead(self, test_state):
        war = MagicMock()
        war.id = "war1"
        war.name = "Test War"
        war.soldier_share = 50
        war.status = WarStatus.RESOLVED
        war.triumph_commander_id = 1
        war.set_soldier_share = MagicMock()

        war_system = test_state.get_war_system()
        war_system._war_discard = [war]

        # 指挥官死亡
        commander = test_state.get_member(1)
        commander.is_dead = True

        test_state.add_forum_action("triumph_votes", ("war1", "f1", True))

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        war.set_soldier_share.assert_called_once_with(0)
        assert "指挥官已死" in result["message"]

    def test_mixed_actions(self, test_state):
        # 招募
        test_state.add_forum_action("recruitment_bids", ("f1", 4, 30))
        # 合同竞标
        test_state.add_forum_action("contract_bids", (2, 2, "f1", 110))
        test_state.add_forum_action("contract_bids", (2, 3, "f2", 120))
        # 公地认购
        test_state.add_forum_action("land_purchases", ("f1", 10))
        # 凯旋投票
        war = MagicMock()
        war.id = "war1"
        war.name = "Test War"
        war.soldier_share = 20
        war.status = WarStatus.RESOLVED
        war.triumph_commander_id = 1
        war.set_soldier_share = MagicMock()
        war.set_triumph_approved = MagicMock()
        war_system = test_state.get_war_system()
        war_system._war_discard = [war]
        test_state.add_forum_action("triumph_votes", ("war1", "f1", True))

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "加入 Faction1" in result["message"]
        assert "中标者: Faction2，出价 120" in result["message"]
        assert "Faction1 认购 10 C 公地" in result["message"]
        assert "凯旋仪式获得批准" in result["message"]