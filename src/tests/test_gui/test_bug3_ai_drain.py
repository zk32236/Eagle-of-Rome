"""
T-B3-03: AI vote_completed marker (B3-AC03)
Test-First — Run on OLD product baseline (6cb2e69).
Expected: RED — AI drain 不在 1H 完成路径上，
           AI vote_completed 保持 False（BUG3 未修复）。
Source AC: B3-AC03 | Contract: B3-FC03
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api
from src.core.entities.player import PlayerType


class TestBug3AiDrain:
    """T-B3-03: 验证 AI drain 后 AI 的 vote_completed 标记"""

    def setup_session(self):
        """创建到人口阶段的会话。"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)
        return state, viewer_id

    def get_ai_players(self, state):
        """获取所有 AI 玩家。"""
        return [p for p in state.get_all_players()
                if p.player_type.value != "human"]

    def test_ai_vote_completed_initial_state(self):
        """验证初始状态下 AI vote_completed 为 False（前置条件）。
        
        旧代码预期：PASS — 初始状态 AI 未完成。
        """
        state, viewer_id = self.setup_session()
        ai_players = self.get_ai_players(state)

        for ai in ai_players:
            assert not state.get_vote_completed(ai.player_id), (
                f"初始状态 AI {ai.player_id} vote_completed 应为 False"
            )

    def test_ai_vote_completed_after_human_completion(self):
        """HUMAN 完成后 AI 应被 drain 并标记 vote_completed=True。
        
        旧代码预期：RED — 旧 doCompletePlayer 不触发 AI drain，
                        AI vote_completed 保持 False。
        """
        state, viewer_id = self.setup_session()

        # 完成 HUMAN 投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        # 调用 resolve_population_slice 模拟最终完成后的 drain
        resolved = session_api.resolve_population_slice(state)

        # 新行为期望：AI vote_completed=True
        # 旧代码预期 RED：AI 未被 drain，vote_completed=False
        ai_players = self.get_ai_players(state)
        for ai in ai_players:
            completed = state.get_vote_completed(ai.player_id)
            assert completed, (
                f"BUG3 未修复：AI {ai.player_id} vote_completed=False "
                f"(resolve_population_slice result: {resolved.get('message')})"
            )

    def test_ai_vote_completed_persists_after_resolution_recorded(self):
        """AI drain 后 resolution result 已记录，AI vote_completed 应保持 True。

        Frozen AC 只要求 AI completion marker + population resolution。
        `resolve_population_slice()` 负责 record_phase_result；
        `mark_phase_executed("population")` 属于后续 advance_population_phase，
        本测试不得要求 resolve 阶段提前改变 phase_executed 语义。

        旧代码预期：RED — phase_result 可以被记录，但 AI 未被 drain，
                        因此 AI vote_completed 仍为 False。
        """
        state, viewer_id = self.setup_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        resolved = session_api.resolve_population_slice(state)
        assert resolved.get("success"), (
            f"population resolution 应成功，实际: {resolved.get('message')}"
        )

        phase_result = state.get_phase_result("population")
        assert phase_result is not None, (
            "resolve_population_slice 成功后必须记录 population phase_result"
        )

        # 两阶段语义保护：resolve 不等于 advance。
        assert not state.is_phase_executed("population"), (
            "resolve 阶段不应提前 mark phase_executed；该动作属于 advance_population_phase"
        )

        ai_players = self.get_ai_players(state)
        for ai in ai_players:
            assert state.get_vote_completed(ai.player_id), (
                f"BUG3 未修复：AI {ai.player_id} vote_completed=False "
                "在 resolution result 已记录后"
            )

    def test_resolve_population_slice_drains_all_ai(self):
        """resolve_population_slice 应 drain 所有 AI 玩家（不仅是 turn_order 中的）。
        
        旧代码预期：PASS/RED — resolve_population_slice 中 while 循环会 drain 非 HUMAN 玩家，
                        但该 drain 只在 resolve_population_slice 被调用时触发。
                        如果 doCompletePlayer 没调用 resolve_population_slice 则 AI 未 drain。
        """
        state, viewer_id = self.setup_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        resolved = session_api.resolve_population_slice(state)

        ai_players = self.get_ai_players(state)
        assert len(ai_players) == 2, f"预期 2 AI，实际 {len(ai_players)}"

        for ai in ai_players:
            assert state.get_vote_completed(ai.player_id), (
                f"AI {ai.player_id} (type={ai.player_type.value}) 未被 drain"
            )
