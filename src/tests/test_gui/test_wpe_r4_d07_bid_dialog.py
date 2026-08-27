# src/tests/test_gui/test_wpe_r4_d07_bid_dialog.py
"""WP-E-R4 D-07：竞标 Dialog（DATA 证据）。

R4 修正 = 点击竞标 → bidDialog（eques 选择器 + 金额 + 确认/关闭），
权威提交链不变：doPlaceBid(figure_id, contract_id, amount) → place_bid → 7 元组。
本测试锁定驱动 Dialog 的 DTO 事实 + 权威提交/防重/结算：
- 竞标者资格 = my_figures[].can_bid（eques），QML 不发明规则
- 权威 7 元组 (contract_id, figure_id, faction_id, amount, profit_rate, construction, warranty)
- 负向：非 eques / 非法金额 / 重复 / 刷新重建
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.contract import Contract, ContractType, ContractStatus
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
    f2 = Figure.create_eques(2, "f1", 30)  # eques → can_bid
    f2.wealth = 30
    f2.update_influence()
    s.add_member(f2)
    s.get_faction("f1").member_ids = [1, 2]

    c1 = Contract(
        id=1, contract_type=ContractType.TAX_FARMING, name="Tax",
        base_cost=100, status=ContractStatus.BUDGETED,
    )
    c1._original_budget = 100
    s._contracts_dict[1] = c1
    return s


def _bidders(s):
    view = forum_api.get_forum_view(s, "p1")
    assert view["success"]
    return [f for f in view["data"]["my_figures"] if f.get("can_bid")]


def _viewer_bids(s):
    view = forum_api.get_forum_view(s, "p1")
    assert view["success"]
    return view["data"]["viewer_contract_bids"]


class TestBidEligibility:
    """竞标者资格 = DTO can_bid（eques），QML equesBidOptions() 仅过滤。"""

    def test_can_bid_eques_only(self, state):
        ids = {f["id"] for f in _bidders(state)}
        assert ids == {2}  # 仅 eques figure 2；nobile 1 不可竞标

    def test_no_eligible_bidder(self, state):
        state.get_member(2).is_dead = True
        assert _bidders(state) == []


class TestBidDialog:
    """Dialog 选 eques → 出价 → 权威 7 元组 pending → 防重。"""

    def test_authoritative_7tuple_pending(self, state):
        r = forum_api.place_bid(state, "p1", 2, 1, 120)
        assert r["success"] is True
        pending = state.get_forum_pending()
        # (contract_id, figure_id, faction_id, amount, profit_rate, construction, warranty)
        assert (1, 2, "f1", 120, 0.2, 0, 0) in pending["contract_bids"]

    def test_viewer_contract_bids_rebuild(self, state):
        assert forum_api.place_bid(state, "p1", 2, 1, 120)["success"]
        bids = _viewer_bids(state)
        assert len(bids) == 1
        assert bids[0]["contract_id"] == 1
        assert bids[0]["figure_id"] == 2
        assert bids[0]["amount"] == 120
        assert bids[0]["status"] == "pending"
        assert _viewer_bids(state) == bids  # 确定性

    def test_non_eques_rejected(self, state):
        r = forum_api.place_bid(state, "p1", 1, 1, 120)  # nobile → error_not_knight
        assert r["success"] is False
        assert i18n.get("error_not_knight") in r["message"]

    def test_invalid_amount(self, state):
        assert forum_api.place_bid(state, "p1", 2, 1, 0)["success"] is False

    def test_repeat_bid_rejected(self, state):
        assert forum_api.place_bid(state, "p1", 2, 1, 120)["success"]
        r2 = forum_api.place_bid(state, "p1", 2, 1, 130)
        assert r2["success"] is False
        assert "已对本合同出价" in r2["message"]
        assert len(state.get_forum_pending()["contract_bids"]) == 1
