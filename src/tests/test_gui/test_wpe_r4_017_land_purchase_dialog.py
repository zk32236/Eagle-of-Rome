# src/tests/test_gui/test_wpe_r4_017_land_purchase_dialog.py
"""WP-E-R4 017：公地认购 Dialog 内选人（DATA 证据）。

R4 修正 = 选人移入 Dialog（QML 交互形态），权威提交链不变：
doBuyLand(figure_id, amount) → buy_land → land_purchases (figure_id, amount)。
本测试锁定驱动 Dialog 选择器的 DTO 事实 + 权威提交/结算行为：
- 资格源 = my_figures[].can_buy_land（DTO，QML 不发明规则）
- 提交身份 = (figure_id, quantity) 恰一 pending
- 结算分配同 figure + add_treasury(cost)
- 负向：无资格 / 非法数量 / 财富不足 / 重复 / 刷新重建
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import forum_api
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def state():
    config = {
        "testing": {"bypass_player_check": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "default_bid_profit_rate": 0.2,
            "project_theoretical_construction": 3,
            "project_theoretical_warranty": 10,
        },
    }
    s = GameState.create_for_testing(config)
    s.turn = GameTurn(turn_number=1, year=-282)
    s.add_player(Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN))
    s.set_turn_order(["p1"])
    s.set_current_player("p1")
    s.add_faction(Faction(id="f1", name="Faction1", treasury=1000))

    f1 = Figure.create_nobile(1, "f1", 40)
    f1.wealth = 50
    f1.update_influence()
    s.add_member(f1)
    f2 = Figure.create_eques(2, "f1", 30)
    f2.wealth = 30
    f2.update_influence()
    s.add_member(f2)
    # 财富为 0 的人物 → can_buy_land=False（不可认购）
    f3 = Figure.create_plebeian(3, "f1", 25)
    f3.wealth = 0
    f3.update_influence()
    s.add_member(f3)
    s.get_faction("f1").member_ids = [1, 2, 3]
    s._national_public_land = 100
    return s


def _my_figures(s):
    view = forum_api.get_forum_view(s, "p1")
    assert view["success"]
    return view["data"]["my_figures"]


def _land_actors(s):
    return [f for f in _my_figures(s) if f.get("can_buy_land")]


class TestLandEligibility:
    """资格源 = DTO can_buy_land（wealth>0），QML landActorOptions() 仅过滤。"""

    def test_eligibility_source_can_buy_land(self, state):
        ids = {f["id"] for f in _land_actors(state)}
        assert 1 in ids and 2 in ids
        assert 3 not in ids  # wealth=0 → 不可认购

    def test_no_eligible_figure(self, state):
        for fid in (1, 2, 3):
            state.get_member(fid).wealth = 0
        assert _land_actors(state) == []


class TestLandPurchaseDialog:
    """Dialog 选人 → 提交 → 权威 pending → 结算分配同 figure。"""

    def test_pending_exactly_one_identity(self, state):
        state.set_pending_land_sale_quota(100)
        fig = state.get_member(2)
        fig.wealth = 10 * 10 + 1
        r = forum_api.buy_land(state, "p1", 2, 10)
        assert r["success"] is True
        pending = state.get_forum_pending()
        assert pending["land_purchases"] == [(2, 10)]

    def test_viewer_land_requests_rebuild(self, state):
        """刷新/重入：viewer_land_requests 从 DTO 重建（figure_id + requested_amount）。"""
        state.set_pending_land_sale_quota(100)
        state.get_member(2).wealth = 200
        assert forum_api.buy_land(state, "p1", 2, 5)["success"]
        view = forum_api.get_forum_view(state, "p1")
        reqs = view["data"]["viewer_land_requests"]
        assert reqs == [{"figure_id": 2, "requested_amount": 5}]
        again = forum_api.get_forum_view(state, "p1")["data"]["viewer_land_requests"]
        assert again == reqs

    def test_invalid_amount(self, state):
        state.set_pending_land_sale_quota(100)
        assert forum_api.buy_land(state, "p1", 2, 0)["success"] is False

    def test_insufficient_wealth(self, state):
        state.set_pending_land_sale_quota(100)
        state.get_member(2).wealth = 5  # 买不起 1 单位（10）
        r = forum_api.buy_land(state, "p1", 2, 1)
        assert r["success"] is False
        assert "不足" in r["message"]

    def test_repeat_submit_same_figure(self, state):
        """重复提交同 figure → 拒绝，仍恰一 pending（Dialog 确认守卫 + Core 防重兜底）。"""
        state.set_pending_land_sale_quota(100)
        state.get_member(2).wealth = 500
        assert forum_api.buy_land(state, "p1", 2, 10)["success"]
        r2 = forum_api.buy_land(state, "p1", 2, 5)
        assert r2["success"] is False
        assert len(state.get_forum_pending()["land_purchases"]) == 1

    def test_resolve_allocation_same_figure(self, state):
        """结算分配同 figure + add_treasury(cost)。"""
        state.set_pending_land_sale_quota(50)
        state.add_forum_action("land_purchases", (2, 30))
        fig = state.get_member(2)
        fig.wealth = 500
        initial_land = fig.land_private
        initial_treasury = state.treasury
        r = forum_api.resolve_forum(state)
        assert r["success"] is True
        allocation = r["data"]["land_allocation"]
        assert allocation[0]["figure_id"] == 2
        assert allocation[0]["allocated_amount"] == 30
        assert fig.land_private == initial_land + 30
        assert state.treasury == initial_treasury + 300
