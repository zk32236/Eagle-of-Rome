"""
T-B3-04: WP-02b 同一 drain → 三派计票 (B3-AC04)
Test-First — Run on OLD product baseline (6cb2e69).
Expected: RED — WP-02b submit_population_votes 在 1H 场景中 complete_population_player
          调用 next_player（返回同一 HUMAN），不触发 resolve_population_slice，
          AI 未被 drain，三派计票不完整。
Source AC: B3-AC04 | Contract: B3-FC05, B3-FC08
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api


class TestBug3Wp02bDrain:
    """T-B3-04: 验证 WP-02b 使用统一 resolve_population_slice drain 路径"""

    def setup_population_session(self):
        """创建人口阶段会话，确认候选人和投票条件就绪。"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)
        return state, viewer_id

    def test_wp02b_submit_triggers_drain_via_resolve_population_slice(self):
        """WP-02b submit_population_votes 路径应通过 resolve_population_slice
        触发 AI drain（同一个 helper）。
        
        旧代码预期：RED — submit_population_votes 中 complete_population_player
                        调用 next_player，1H 场景取模返回同一 HUMAN，
                        不触发 resolve，AI 未被 drain。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = {}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                selection_map[office] = rows[0]["id"]

        if len(selection_map) < 5:
            pytest.skip(f"Only {len(selection_map)} offices have candidates, need 5")

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        ai_players = [p for p in state.get_all_players()
                      if p.player_type.value != "human"]
        for ai in ai_players:
            completed = state.get_vote_completed(ai.player_id)
            assert completed, (
                f"BUG3 未修复：WP-02b submit 后 AI {ai.player_id} vote_completed=False。"
                f" submit result: status={result.get('data', {}).get('status')}"
            )

    def test_wp02b_submit_produces_three_faction_votes(self):
        """WP-02b 提交后三派系应均有投票记录。
        
        旧代码预期：RED — AI 未被 drain，投票记录仅 HUMAN。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = {}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                selection_map[office] = rows[0]["id"]

        if len(selection_map) < 5:
            pytest.skip(f"Only {len(selection_map)} offices have candidates, need 5")

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        all_players = state.get_all_players()
        all_votes = state.get_population_votes()
        voted_ids = set(v[0] for v in all_votes)
        for p in all_players:
            assert p.player_id in voted_ids, (
                f"BUG3 未修复：玩家 {p.player_id} (type={p.player_type.value}) "
                f"无投票记录。submit result: status={result.get('data', {}).get('status')}"
            )

    def test_wp02b_and_manual_vote_use_same_drain(self):
        """验证 WP-02b 路径与手动投票路径使用同一 drain（resolve_population_slice）。
        
        旧代码预期：RED — WP-02b 路径中 complete_population_player 仅调用
                        next_player，不调用 resolve_population_slice。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = {}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                selection_map[office] = rows[0]["id"]

        if len(selection_map) < 5:
            pytest.skip(f"Only {len(selection_map)} offices have candidates, need 5")

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        resolved = state.is_phase_executed("population") or (
            state.get_phase_result("population") is not None
        )
        assert resolved, (
            "BUG3 未修复：WP-02b submit 后 population 未 resolve。"
            f" submit result: status={result.get('data', {}).get('status')}"
        )

    def test_wp02b_three_faction_weighted_voting(self):
        """验证三派系投票权重——每派各 1 票，应产生加权计票结果。
        
        旧代码预期：RED — AI 未被 drain，缺少 AI 投票权重。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = {}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                selection_map[office] = rows[0]["id"]

        if len(selection_map) < 5:
            pytest.skip(f"Only {len(selection_map)} offices have candidates, need 5")

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        pop_result = state.get_phase_result("population")
        if pop_result is None:
            assert False, (
                "BUG3 未修复：population phase_result 为 None。"
                f" submit result: status={result.get('data', {}).get('status')}"
            )

        election_results = pop_result.get("data", {}).get("election_results", [])
        assert len(election_results) > 0, (
            "BUG3 未修复：无选举结果记录"
        )
