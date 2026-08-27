# src/tests/test_gui/test_wpe_r4_shared_surface_smoke.py
"""WP-E-R4 共享面 smoke：D-11（Forum Market 共享面）targeted + POST-07P applicability。

R4 编辑面 = ForumStage（公地认购 + Pending Contract 竞标）+ RevenueStage（国家支出增行）。
D-11 = Forum Market 共享面（招募/解雇/凯旋）→ 017/D-07 触碰同区 → targeted smoke。
POST-07P = Combat 计数派生 → R4 编辑面之外 → applicability-only（无重叠，不重测）。
"""
from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


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


class TestD11ForumMarketSmoke:
    """D-11 targeted：Forum Market 共享面（招募/解雇/凯旋）无回归。"""

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

        # D-11 共享面载体在位（招募/解雇/凯旋/竞标/认购）
        assert isinstance(store.forumAvailableFigures, list)
        assert isinstance(store.forumMyFigures, list)
        assert isinstance(store.forumTriumphWars, list)
        assert isinstance(store.forumPendingContracts, list)
        # R4 新增 DTO 载体在位（竞标骑士 / 认购人物选择器数据源）
        assert isinstance(store.forumViewerContractBids, list)
        assert isinstance(store.forumViewerLandRequests, list)
        assert store.forumCurrentStep == "market"

    def test_recruit_retire_triumph_slots_unchanged(self):
        """招募/解雇/凯旋 Store Slot 语义不变（017/D-07 未触碰这些路径）。"""
        store, state, viewer_id = _make_store()
        assert store.doExecuteMortality()["success"]
        assert store.doAdvanceMortality()["success"]
        assert store.doExecuteRevenue()["success"]
        assert store.doAdvanceRevenue()["success"]
        store.doCompleteForumStep()
        store._refresh_forum_view()
        # 招募 Slot 存在且对无效 figure 显式失败（非静默 no-op）
        r = store.doRecruitFigure(999999, 1)
        assert isinstance(r, dict) and r.get("success") is False


class TestPost07pApplicability:
    """POST-07P applicability：Combat 落点在 R4 编辑面之外 → 无重叠。"""

    def test_combat_surface_outside_r4_edits(self):
        store, state, viewer_id = _make_store(start_phase="combat")
        # R4 仅改 ForumStage/RevenueStage；combat 共享面（POST-07P）不重叠
        assert isinstance(store.combatActiveWars, list)
        # 仅 applicability 判定：确认 R4 未触碰 combat 数据源
        assert store.combatView is not None
