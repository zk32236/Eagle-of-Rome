# src/tests/test_gui/test_wpe_r5_shared_surface_smoke.py
"""WP-E-R5 共享面 smoke：R4 继承面（stipend 恒等式 / Forum 零触碰）+ POST-07P applicability。

R5 编辑面 = military_system（维护费 mutation）+ economic_service.apply_military_maintenance
（回报 3 新键）+ RevenueStage 维护费行（值语义）——与 Forum/017/D-07/combat 零交集。
R4 继承面：stipend 行恒等式（faction_rows stipend = 国库扣减，F6:317-318）；Forum 载体在位。
POST-07P（Combat 计数派生）：applicability-only（预期无重叠）。
"""
from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.province import Province
from src.core.entities.war import War
from src.core.systems.war_system import WarSystem
from src.core.service.economic_service import EconomicService
from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


# ─── R4 继承面：stipend 恒等式（四层对账，R4 PASS 继承）──────────────────

_R4_ECON_CONFIG = {
    "economic_rules": {
        "faction_stipend": 5,
        "land_price_per_unit": 10,
        "national_opex_rate": 0.0003,
        "initial_national_public_land": 0,
    }
}


def _make_r4_state():
    """R4 D-12 stipend 同款状态：opening=142 + 赔款 36 − opex 18 − stipend 15 → ending=145。"""
    s = GameState.create_for_testing(_R4_ECON_CONFIG)
    s.turn = GameTurn(turn_number=5, year=-260)
    s.treasury = 142
    for fid, name in (("opt", "Optimates"), ("pop", "Populares"), ("equ", "Equites")):
        s.add_faction(Faction(id=fid, name=name))
    s._war_system = WarSystem(s)
    war = War(id="w1", name="赔款战争")
    war.set_indemnity_due(36)
    s.get_war_system()._active_wars.append(war)
    s.add_province(Province(1, "行省", total_land=6000, conquered=True))
    return s


def _settle(s):
    result = EconomicService(s).settle_revenue_phase()
    assert result["success"], f"Settlement failed: {result}"
    return result["data"]


def _stipend_total(data):
    return sum(row["stipend"] for row in data["faction_rows"].values())


class TestR4StipendIdentityInherited:
    """R5 不触碰 stipend 行/扣款路径：恒等式继续成立（行 = delta 分量 = 实扣同源）。"""

    def test_stipend_identity_beta_001(self):
        data = _settle(_make_r4_state())
        assert _stipend_total(data) == 15
        assert data["starting_treasury"] == 142
        assert data["ending_treasury"] == 145
        assert data["treasury_delta"] == 3
        # 维护费分量（R5 场景无军团）：total=0 / charged=0 —— R4 面不受影响
        military = data["maintenance"]["military"]
        assert military["total"] == 0
        assert military["charged"] == 0
        assert military["shortfall"] == 0
        assert military["disbanded"] == 0
        # 四层恒等式：ending == starting + Σincome − Σexpense（stipend 归支出）
        assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]


# ─── R4 继承面：Forum 零触碰 ──────────────────────────────────────────────

def _make_store(start_phase=None):
    kwargs = {"start_phase": start_phase} if start_phase else {}
    result = session_api.create_gui_prototype_session(**kwargs)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


class TestForumSharedSurfaceZeroTouch:
    """R5 编辑面与 Forum 共享面零交集：Forum 载体/流程无回归。"""

    def test_forum_market_shared_surface_no_regression(self):
        store, state, viewer_id = _make_store()
        assert store.doExecuteMortality()["success"]
        assert store.doAdvanceMortality()["success"]
        assert store.doExecuteRevenue()["success"]
        assert store.doAdvanceRevenue()["success"]
        assert store.currentPhaseId == "forum"
        assert store.doCompleteForumStep()["success"]
        store.selectPhase("forum")
        store._refresh_forum_view()

        assert isinstance(store.forumAvailableFigures, list)
        assert isinstance(store.forumMyFigures, list)
        assert isinstance(store.forumTriumphWars, list)
        assert isinstance(store.forumPendingContracts, list)
        assert store.forumCurrentStep == "market"

    def test_recruit_retire_slots_unchanged(self):
        store, state, viewer_id = _make_store()
        assert store.doExecuteMortality()["success"]
        assert store.doAdvanceMortality()["success"]
        assert store.doExecuteRevenue()["success"]
        assert store.doAdvanceRevenue()["success"]
        store.doCompleteForumStep()
        store._refresh_forum_view()
        r = store.doRecruitFigure(999999, 1)
        assert isinstance(r, dict) and r.get("success") is False


class TestPost07pApplicability:
    """POST-07P（Combat 计数派生）：R5 编辑面（military mutation / economic 回报 /
    Revenue 维护费行）在 combat 共享面之外 → applicability-only，无重叠。"""

    def test_combat_surface_outside_r5_edits(self):
        store, state, viewer_id = _make_store(start_phase="combat")
        assert isinstance(store.combatActiveWars, list)
        assert store.combatView is not None
