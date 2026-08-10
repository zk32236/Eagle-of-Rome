"""
T-B3-01: turn_order 仅 HUMAN 断言 (B3-AC01)
Test-First — Run on OLD product baseline (6cb2e69).
Expected: PASS — turn_order 本就仅 HUMAN (set_turn_order(human_players) at L48).
Source AC: B3-AC01 | Contract: B3-FC01 | Authority: MVP0.7-12 §2.2
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, player_api
from src.core.entities.player import PlayerType


class TestBug3TurnOrder:
    """T-B3-01: 验证 create session 后 turn_order 仅包含 HUMAN 玩家"""

    def test_session_creates_with_human_as_current_player(self):
        """创建会话后当前玩家是 HUMAN。
        
        旧代码预期：PASS — create_gui_prototype_session 设置第一个 HUMAN 为当前玩家。
        """
        result = session_api.create_gui_prototype_session()
        assert result["success"], f"Session creation failed: {result.get('message')}"
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]

        current = state.get_current_player()
        assert current is not None, "当前玩家不应为 None"
        assert current.player_id in human_players, (
            f"当前玩家 {current.player_id} 不在 HUMAN 列表中 {human_players}"
        )
        assert current.player_type.value == "human", (
            f"当前玩家类型应为 human，实际为 {current.player_type.value}"
        )

    def test_next_player_returns_human_in_1h_scenario(self):
        """单人模式中 next_player 在 HUMAN turn_order 内循环。
        注意：1H 场景中 next_player 会返回同一玩家（turn_order 仅 1 个 HUMAN）。
        
        旧代码预期：PASS — next_player 在 turn_order（仅 HUMAN）中取模循环。
        """
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]

        state.set_current_player(viewer_id)
        new_id = state.next_player()

        assert new_id is not None, "next_player 应返回玩家 ID"
        assert new_id in human_players, (
            f"next_player 返回 {new_id}，不在 HUMAN 列表 {human_players} 中"
        )
        # 1H 场景：turn_order 仅 1 个 HUMAN，next_player 取模返回同一玩家
        assert new_id == viewer_id, (
            f"1H 场景中 next_player 应返回同一玩家（取模循环），实际返回 {new_id}"
        )

    def test_ai_players_exist_but_not_current_after_session_create(self):
        """验证 AI 玩家存在但当前玩家是 HUMAN。
        
        旧代码预期：PASS — AI 玩家存在但不为当前玩家。
        """
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]

        all_players = state.get_all_players()
        ai_players = [
            p for p in all_players
            if p.player_type.value != "human"
        ]
        assert len(ai_players) >= 1, "应有至少 1 个 AI 玩家"

        current = state.get_current_player()
        for ai in ai_players:
            assert current.player_id != ai.player_id, (
                f"AI 玩家 {ai.player_id} 不应为当前玩家"
            )

    def test_scenario_configuration_is_1h_2ai(self):
        """确认场景配置为 1 HUMAN + 2 AI（前置条件）。
        
        旧代码预期：PASS — gui_prototype.json 配置不变。
        """
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]

        all_players = state.get_all_players()
        human_count = sum(1 for p in all_players if p.player_type.value == "human")
        ai_count = sum(1 for p in all_players if p.player_type.value != "human")

        assert human_count == 1, f"预期 1 HUMAN，实际 {human_count}"
        assert ai_count == 2, f"预期 2 AI，实际 {ai_count}"
        assert len(all_players) == 3, f"预期 3 玩家，实际 {len(all_players)}"

    def test_population_start_phase_maintains_turn_order_behavior(self):
        """population start_phase 版本同样验证 turn_order 仅 HUMAN。
        
        旧代码预期：PASS — start_phase 不影响 turn_order。
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]

        current = state.get_current_player()
        assert current.player_type.value == "human"
        assert current.player_id in human_players
