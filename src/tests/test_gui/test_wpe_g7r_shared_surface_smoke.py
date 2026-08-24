# src/tests/test_gui/test_wpe_g7r_shared_surface_smoke.py
"""
WP-E-G7R — EC-12 共享面 smoke：全阶段按钮推进链 + Forum/Population 刷新不回归。

覆盖：
- 全阶段按钮 label/enabled 推进链（doAdvanceCurrentPhase 统一分派）
- resolution 单命令 → mortality 后 Forum/Population 刷新链（_on_refresh）不回归
- _PHASE_ADVANCE_DISPATCH 七阶段条目完整性（共享面零触碰）
"""
import pytest

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


class TestG7RSharedSurfaceSmoke:
    """WP-E-G7R 共享面 smoke（EC-12）。"""

    def test_phase_advance_chain_with_dispatch(self):
        """全阶段统一分派推进链：mortality→revenue→forum→population；每步 label/enabled 正确。"""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # mortality
        store.doExecuteMortality()
        assert store.canAdvanceCurrentPhase is True
        assert "收入阶段" in store.advanceCurrentPhaseText
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "revenue"

        # revenue
        store.doExecuteRevenue()
        assert store.canAdvanceCurrentPhase is True
        assert "广场" in store.advanceCurrentPhaseText
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "forum"

        # forum（Forum 共享面：推进后 view 刷新）
        store.doExecuteForum()
        assert store.canAdvanceCurrentPhase is True
        assert "人口阶段" in store.advanceCurrentPhaseText
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "population"
        # Forum/Population 刷新链不回归
        assert isinstance(store.forumView, dict)
        assert isinstance(store.populationView, dict)
        assert hasattr(store, "populationResolved")

    def test_resolution_single_command_shared_refresh(self):
        """resolution 单命令 → mortality；_on_refresh 链（Forum/Population/Combat/Senate）不回归。"""
        result = session_api.create_gui_prototype_session(start_phase="combat")
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)
        state.mark_phase_executed("combat")
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # resolution 按钮：唯一「⏭️ 进入下一年度」+ enabled
        assert store.resolutionResolved is True
        assert store.canAdvanceResolution is True
        assert store.advanceCurrentPhaseText == "\u23ed\ufe0f 进入下一年度"

        # 单命令 → mortality
        feedback = store.doAdvanceResolution()
        assert feedback["success"]
        assert store.selectedPhaseId == "mortality"
        assert store.currentPhaseId == "mortality"

        # 共享面 view 全部刷新（_on_refresh → _refresh_*_view）
        assert isinstance(store.forumView, dict)
        assert isinstance(store.populationView, dict)
        assert isinstance(store.senateView, dict)
        assert isinstance(store.combatView, dict)
        assert isinstance(store.resolutionView, dict)

    def test_dispatch_table_complete(self):
        """_PHASE_ADVANCE_DISPATCH 七阶段条目完整（共享面零触碰，E-05 唯一 resolution 标签）。"""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        dispatch = store._PHASE_ADVANCE_DISPATCH
        assert set(dispatch.keys()) == {
            "mortality", "revenue", "forum", "population", "senate", "combat", "resolution",
        }
        # 其他阶段标签保持（零改动）
        assert dispatch["mortality"]["label"] == "\u23ed\ufe0f 推进到收入阶段"
        assert dispatch["revenue"]["label"] == "\u23ed\ufe0f 推进到广场"
        assert dispatch["forum"]["label"] == "\u23ed\ufe0f 推进到人口阶段"
        assert dispatch["population"]["label"] == "\u23ed\ufe0f 进入元老院阶段"
        assert dispatch["senate"]["label"] == "\u23ed\ufe0f 推进到战斗阶段"
        assert dispatch["combat"]["label"] == "\u23ed\ufe0f 推进到决断阶段"
        # resolution 唯一「⏭️ 进入下一年度」（E-05）
        assert dispatch["resolution"]["label"] == "\u23ed\ufe0f 进入下一年度"
