"""
T-B3-02: 1H 主闭环 — no self-handoff → resolve (B3-AC02/05)
Test-First — Run on OLD product baseline (6cb2e69).
Expected: RED — 旧代码 doCompletePlayer → next_player 返回同一 HUMAN（self-handoff），
             不触发 AI drain，不进入 resolve。
             BUG3 未修复，新行为测试应在旧代码上 RED。
Source AC: B3-AC02, B3-AC05 | Contract: B3-FC02, B3-FC03, B3-FC05
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api
from src.ui.gui.session_store import GuiSessionStore
from src.ui.gui.api_adapter import GuiApiAdapter


class TestBug3CompletePlayer:
    """T-B3-02: 验证 1H 主闭环 — HUMAN 完成 → no self-handoff → resolve"""

    def setup_session(self, start_phase="population"):
        """创建到人口阶段的会话并返回 state/store/adapter/players。"""
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
        assert result["success"], f"Session creation failed: {result.get('message')}"
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        assert len(human_players) == 1, f"预期 1 HUMAN，实际 {len(human_players)}"
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)

        # 确保有候选人
        cand_result = population_api.get_candidates(state)
        if not cand_result.get("success"):
            pytest.skip("No candidates available for population phase")

        store = GuiSessionStore(state)
        store.initialize(viewer_id)
        return state, store, viewer_id

    def test_complete_player_no_self_handoff(self):
        """HUMAN 完成投票后不应 handoff 回自己（no self-handoff）。
        
        旧代码预期：RED — doCompletePlayer 调用 next_player，1H 取模返回同一玩家，
                        形成 self-handoff。BUG3 修复后应无 self-handoff 且触发 resolve。
        """
        state, store, viewer_id = self.setup_session()

        # 先完成投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                fig_id = rows[0]["id"]
                population_api.vote(state, viewer_id, office, fig_id)

        # 验证投票已完成
        my_votes = [v for v in state.get_population_votes() if v[0] == viewer_id]
        assert len(my_votes) > 0, "投票未记录"

        # 调用 doCompletePlayer
        feedback = store.doCompletePlayer()

        # BUG3 修复后的期望：success，不应 handoff 回自己
        # 旧代码预期 RED：feedback 中 new_player_id == viewer_id（self-handoff）
        if feedback.get("success"):
            new_id = feedback.get("data", {}).get("new_player_id")
            # 新行为断言：new_player_id 不应等于 viewer_id（no self-handoff）
            # 在旧代码上 expected RED
            assert new_id != viewer_id, (
                f"BUG3 未修复：self-handoff 检测到 {new_id} == {viewer_id}"
            )

    def test_1h_completion_triggers_resolution(self):
        """最后 HUMAN 完成后应触发 population resolution。
        
        旧代码预期：RED — 旧代码 doCompletePlayer 不检查 completion predicate，
                        不调用 resolve_population_slice。
        """
        state, store, viewer_id = self.setup_session()

        # 完成投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        voted_offices = []
        for office, rows in candidates.items():
            if rows:
                fig_id = rows[0]["id"]
                population_api.vote(state, viewer_id, office, fig_id)
                voted_offices.append(office)

        assert len(voted_offices) > 0, "没有可投票的官职"

        # doCompletePlayer
        feedback = store.doCompletePlayer()

        # 新行为期望：population 已 resolved
        # 旧代码预期 RED：population 未 resolve
        resolved = state.is_phase_executed("population") or (
            state.get_phase_result("population") is not None
        )
        assert resolved, (
            "BUG3 未修复：1H 完成后 population 未 resolve。"
            f" feedback={feedback.get('message', 'N/A')}"
        )

    def test_ai_players_completed_after_1h_resolution(self):
        """1H 完成后 AI 应被 drain 并标记 vote_completed=True。
        
        旧代码预期：RED — 旧代码 doCompletePlayer 不触发 AI drain，
                        AI vote_completed 保持 False。
        """
        state, store, viewer_id = self.setup_session()

        # 完成投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        # doCompletePlayer
        feedback = store.doCompletePlayer()

        # 检查 AI 的 vote_completed 状态
        all_players = state.get_all_players()
        ai_players = [p for p in all_players if p.player_type.value != "human"]

        for ai in ai_players:
            completed = state.get_vote_completed(ai.player_id)
            assert completed, (
                f"BUG3 未修复：AI {ai.player_id} vote_completed=False。"
                f" feedback={feedback.get('message', 'N/A')}"
            )

    def test_three_faction_votes_exist_after_resolution(self):
        """三派系投票记录应在 resolution 后存在。
        
        旧代码预期：RED — doCompletePlayer 不触发 resolve，三派投票不完整。
        """
        state, store, viewer_id = self.setup_session()

        # 完成投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        # doCompletePlayer
        store.doCompletePlayer()

        # 检查投票记录涵盖所有玩家（新行为期望）
        all_players = state.get_all_players()
        all_votes = state.get_population_votes()
        voted_player_ids = set(v[0] for v in all_votes)

        for p in all_players:
            assert p.player_id in voted_player_ids, (
                f"BUG3 未修复：玩家 {p.player_id} (type={p.player_type.value}) "
                f"没有投票记录"
            )
