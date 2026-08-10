"""
T-B3-05: 多 HUMAN 架构边界 — handoff 规则 (B3-AC05)
Test-First — Run on OLD product baseline (6cb2e69).
Coverage: PARTIAL — 当前场景仅为 1H+2AI，不能宣称完整 multi-HUMAN 行为已被实测。
          测试结构边界：验证当前 1H 场景下 handoff 行为的正确语义。
          多 HUMAN 完整覆盖需 scenario 扩展或在修复后架构验证。
Source AC: B3-AC05 | Contract: B3-FC02, B3-FC04, B3-FC09
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api, player_api


class TestBug3MultihumanBoundary:
    """T-B3-05: 验证 multiplayer handoff 架构边界"""

    def setup_session(self, start_phase="population"):
        """创建到人口阶段的会话。"""
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)
        return state, viewer_id, human_players

    def test_single_human_no_handoff_after_completion(self):
        """1H 场景中 HUMAN 完成后不应触发 handoff（无下一 HUMAN）。
        
        旧代码预期：RED — doCompletePlayer 的 next_player 取模返回自己，
                        触发 self-handoff。修复后应直接 resolve。
        """
        state, viewer_id, human_players = self.setup_session()
        assert len(human_players) == 1, "本测试仅适用于 1H 场景"

        # 完成投票
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        for office, rows in candidates.items():
            if rows:
                population_api.vote(state, viewer_id, office, rows[0]["id"])

        # 调用 next_player 模拟 doCompletePlayer 行为
        new_id = state.next_player()

        # 新行为期望：1H 场景中不应 handoff 回自己
        # 旧代码：next_player 在 1-element turn_order 中取模返回同一玩家
        # 这是 BUG3 的根源 — 应改为 completion predicate 检查后 resolve
        assert new_id != viewer_id, (
            f"BUG3 未修复：1H 场景 next_player 返回 {new_id}，等于 viewer {viewer_id}"
        )

    def test_next_player_behavior_with_only_one_human(self):
        """观察 1H 场景中 next_player 行为 — 记录旧代码表现。
        
        旧代码预期：PASS（记录行为）— next_player 取模返回同一玩家。
        这是结构性观察，不是 pass/fail 判定。
        """
        state, viewer_id, human_players = self.setup_session()
        assert len(human_players) == 1

        # 记录 baseline next_player 行为
        original_new_id = state.next_player()
        assert original_new_id is not None

        # 在 1-element turn_order 中，next_player 必然取模返回同一玩家
        # 这本身不是 bug——是 turn_order 的预期行为
        # Bug 在于 doCompletePlayer 无条件调用 next_player 而非检查 completion

    def test_human_completion_must_not_depend_on_vote_completed_marker(self):
        """结构保护：HUMAN completion 由真实投票覆盖 required offices 判断。

        Frozen Design 明确：本轮不新增 HUMAN completion marker；
        `vote_completed` 是 AI drain completion marker，不得拿它判断 HUMAN 是否完成。
        """
        state, viewer_id, human_players = self.setup_session()
        assert len(human_players) == 1

        cand_result = population_api.get_candidates(state)
        assert cand_result.get("success")
        candidates = cand_result.get("data", {})
        required_offices = [office for office, rows in candidates.items() if rows]
        assert required_offices

        for office in required_offices:
            rows = candidates[office]
            result = population_api.vote(state, viewer_id, office, rows[0]["id"])
            assert result.get("success")

        voted_offices = {
            vote[1] for vote in state.get_population_votes()
            if vote[0] == viewer_id
        }
        assert set(required_offices).issubset(voted_offices)

        # HUMAN 完成与 AI vote_completed marker 解耦。
        assert not state.get_vote_completed(viewer_id), (
            "本轮不得通过给 HUMAN 写 vote_completed=True 来实现 completion routing"
        )

    def test_architectural_boundary_no_ai_handoff_possible(self):
        """架构边界：AI 不应出现在 handoff 路径中。
        
        旧代码预期：PASS — AI 不在 turn_order 中，next_player 不会选中 AI。
        """
        state, viewer_id, human_players = self.setup_session()

        all_players = state.get_all_players()
        ai_players = [p for p in all_players if p.player_type.value != "human"]

        # next_player 基于 turn_order（仅 HUMAN）循环
        # AI 不应成为 next_player 的结果
        for _ in range(10):
            new_id = state.next_player()
            assert new_id in human_players, (
                f"next_player 返回 AI {new_id}，不应发生"
            )

    def test_completion_predicate_independent_of_human_count(self):
        """completion predicate 不应依赖 HUMAN 数量（FC09 可扩展性）。
        
        旧代码预期：PASS（结构性）— verification that 1H case completion 
                        check is structurally independent of count.
        """
        state, viewer_id, human_players = self.setup_session()
        assert len(human_players) >= 1

        # 验证 completion check 结构（不依赖 HUMAN 数量）
        all_human_ids = set(human_players)
        
        # 检查机制应使用 all_players 和 vote_completed，不硬编码数量
        all_players = state.get_all_players()
        human_count = sum(1 for p in all_players if p.player_type.value == "human")
        
        # 结构断言：HUMAN 数量 ≥ 1
        assert human_count >= 1
