# src/tests/test_api/test_wpfr1_forum_pending_buyer.py
"""WP-F-R1 T-F10 / T-F11：Public Land 防重后端 + 双真实买家不折叠（R1-F-05 后端侧）。

- T-F10  同 figure 重复认购仍被后端拒绝（forum_api.buy_land 既有守卫，AC-F05-4）
- T-F11  两真实不同买家 → resolve 后 land_allocation 两条独立行（canonical 逐条，AC-F05-9/10，
         无模糊名去重）
"""
import pytest

from src.api import forum_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState


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
    f1.wealth = 500
    f1.update_influence()
    s.add_member(f1)
    f2 = Figure.create_eques(2, "f1", 30)
    f2.wealth = 300
    f2.update_influence()
    s.add_member(f2)
    s.get_faction("f1").member_ids = [1, 2]
    s._national_public_land = 100
    return s


def test_tf10_backend_repeat_land_request_rejected(state):
    """T-F10（AC-F05-4）：同 figure 二次认购 → 显式拒绝（非静默替换，守卫不变）。"""
    state.set_pending_land_sale_quota(100)
    first = forum_api.buy_land(state, "p1", 1, 5)
    assert first["success"] is True
    second = forum_api.buy_land(state, "p1", 1, 5)
    assert second["success"] is False
    assert "已提交" in second["message"]
    pending = state.get_forum_pending()["land_purchases"]
    assert pending == [(1, 5)]  # 无替换、无第二条


def test_tf11_two_distinct_buyers_not_collapsed(state):
    """T-F11（AC-F05-9/10）：两真实不同买家 → land_allocation 两条独立行（逐 figure_id，不折叠）。"""
    state.set_pending_land_sale_quota(100)
    assert forum_api.buy_land(state, "p1", 1, 3)["success"] is True
    assert forum_api.buy_land(state, "p1", 2, 2)["success"] is True
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], resolved.get("message")
    rows = resolved["data"]["land_allocation"]
    by_figure = {r["figure_id"]: r for r in rows}
    assert set(by_figure) == {1, 2}  # 两买家各一行，不折叠
    assert by_figure[1]["allocated_amount"] == 3
    assert by_figure[2]["allocated_amount"] == 2
    assert by_figure[1]["cost"] == 30
    assert by_figure[2]["cost"] == 20
    assert {r["status"] for r in rows} == {"allocated"}
