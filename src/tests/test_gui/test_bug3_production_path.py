"""
T-B3-06: 生产初始化路径 — 真实 create_gui_prototype_session() (B3-AC02/08)
Test-First — Run on OLD product baseline (6cb2e69).
Expected: RED — 完整 production 路径中 doCompletePlayer 不触发 AI drain，
           1H 完成无法进入 resolve。
Source AC: B3-AC02, B3-AC08 | Contract: all
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api
from src.ui.gui.session_store import GuiSessionStore


class TestBug3ProductionPath:
    """T-B3-06: 生产初始化路径全流程集成测试"""

    def test_full_production_session_creation(self):
        """验证真实 create_gui_prototype_session() 创建的生产会话状态正确。
        
        旧代码预期：PASS — 会话创建是稳定的前置条件。
        注：默认 start_phase="mortality" 不执行任何前置阶段（符合既有行为）。
        """
        result = session_api.create_gui_prototype_session()
        assert result["success"], f"Session creation failed: {result.get('message')}"
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]

        assert len(human_players) >= 1
        assert state.get_current_player() is not None
        assert state.get_all_players() is not None
        assert len(state.get_all_players()) == 3

        # 默认 start_phase="mortality" → 无前置阶段执行（符合既有测试行为）
        assert not state.is_phase_executed("mortality")
        assert not state.is_phase_executed("population")

        viewer_id = human_players[0]
        state.set_current_player(viewer_id)
        new_id = state.next_player()
        assert new_id in human_players

    def test_production_population_full_flow(self):
        """生产路径人口阶段全流程测试（start_phase="population"）。
        
        旧代码预期：RED — 1H 场景 doCompletePlayer 无法正确完成闭环。
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)

        pop_view = session_api.get_population_view(state, viewer_id)
        assert pop_view.get("success"), "population view 应成功"

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})

        voted_count = 0
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])
                voted_count += 1

        assert voted_count > 0, "没有可投票的官职"

        my_votes = [v for v in state.get_population_votes() if v[0] == viewer_id]
        assert len(my_votes) == voted_count

        store = GuiSessionStore(state)
        store.initialize(viewer_id)
        feedback = store.doCompletePlayer()

        resolved = state.is_phase_executed("population") or (
            state.get_phase_result("population") is not None
        )

        if resolved:
            all_votes = state.get_population_votes()
            voted_ids = set(v[0] for v in all_votes)
            assert len(voted_ids) == 3, (
                f"预期 3 派系投票，实际 {len(voted_ids)}: {voted_ids}"
            )
        else:
            assert False, (
                f"BUG3 未修复：1H production 路径 population 未 resolve。"
                f" feedback: {feedback.get('message')}"
            )

    def test_production_store_initialization(self):
        """验证 GuiSessionStore 初始化在 production 路径中正确运行。
        
        旧代码预期：PASS — Store 初始化是稳定的前置条件。
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        assert store.currentPhaseId == "population"
        assert store.viewerPlayerId == viewer_id
        assert store.isCurrentPlayer is True

    def test_regression_baseline_collection_stable(self):
        """确认生产路径未破坏既有收集基数。
        
        旧代码预期：PASS — 既有测试收集不受新测试影响。
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]

        assert state.get_all_players() is not None
        assert state.get_current_player() is not None
        assert state.get_faction(state.get_current_player().faction_id) is not None

        # start_phase="population" → mortality/revenue/forum 已执行
        for phase in ["mortality", "revenue", "forum"]:
            assert state.is_phase_executed(phase)
        assert not state.is_phase_executed("population")

        from src.api import population_api as pop
        cand_result = pop.get_candidates(state)
        assert cand_result.get("success")
        assert len(cand_result.get("data", {})) >= 1
