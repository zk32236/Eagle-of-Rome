"""
src/tests/test_gui/test_session_api.py
Session API 测试
"""
import pytest
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
from src.core.game_state import GameState


class TestSessionApi:
    """GUI 原型会话 API 测试"""

    def test_create_gui_prototype_session(self):
        """创建 GUI 原型会话"""
        result = session_api.create_gui_prototype_session()
        assert result["success"], f"Session creation failed: {result.get('message')}"
        assert "state" in result["data"]
        assert "human_players" in result["data"]
        state = result["data"]["state"]
        assert hasattr(state, "is_phase_executed")
        assert result["data"]["start_phase"] == "mortality"
        # 默认 GUI 流程从真实天命阶段开始
        assert not state.is_phase_executed("mortality")
        assert not state.is_phase_executed("revenue")
        assert not state.is_phase_executed("forum")
        assert not state.is_phase_executed("population")

    def test_get_session_snapshot(self):
        """获取当前玩家快照"""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        assert len(human_players) > 0
        viewer_id = human_players[0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]
        data = snapshot["data"]
        assert "current_player_id" in data
        assert "viewer_player_id" in data
        assert "viewer_faction_id" in data
        assert "is_current_player" in data
        assert "public_resources" in data
        assert "faction_resources" in data
        assert "my_figures" in data
        assert "phase_navigation" in data
        assert "selected_phase_summary" in data
        assert "global_warnings" in data
        assert data["current_phase_id"] == "mortality"
        assert data["selected_phase_id"] == "mortality"
        assert len(data["phase_navigation"]) == 7

    def test_shell_phase_navigation_matches_gui_p0_sprint_order(self):
        """GUI shell exposes the complete GUI-P0 sprint phase sequence."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]
        phases = snapshot["data"]["phase_navigation"]

        assert [phase["name"] for phase in phases] == [
            "天命",
            "收入",
            "广场",
            "人口",
            "元老院",
            "战争",
            "决算",
        ]
        assert [phase["id"] for phase in phases] == [
            "mortality",
            "revenue",
            "forum",
            "population",
            "senate",
            "combat",
            "resolution",
        ]

    def test_shell_phase_navigation_marks_current_implemented_slice_actionable(self):
        """Only current implemented phase for current player is actionable."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        phases = {phase["id"]: phase for phase in snapshot["data"]["phase_navigation"]}

        assert phases["mortality"]["implemented"] is True
        assert phases["mortality"]["actionable"] is True
        assert phases["mortality"]["name_key"] == "phase.mortality.name"
        assert phases["population"]["implemented"] is True
        assert phases["population"]["actionable"] is False
        assert phases["population"]["disabled_reason_key"] == "phase.disabled.not_current"
        assert phases["senate"]["implemented"] is True
        assert phases["senate"]["interaction_mode"] == "interactive"
        assert phases["senate"]["actionable"] is False
        assert phases["senate"]["disabled_reason_key"] == "phase.disabled.not_current"
        assert phases["revenue"]["implemented"] is True
        assert phases["revenue"]["actionable"] is False
        assert phases["revenue"]["disabled_reason_key"] == "phase.disabled.not_current"
        assert phases["revenue"]["handoff_task"] == "GUI-P0-03"
        assert phases["forum"]["implemented"] is True
        assert phases["forum"]["interaction_mode"] == "interactive"
        assert phases["forum"]["actionable"] is False
        assert phases["forum"]["disabled_reason_key"] == "phase.disabled.not_current"
        assert phases["forum"]["handoff_task"] == "GUI-P0-03"
        # combat and resolution are implemented but not current (actionable=False)
        for phase_id in ["combat", "resolution"]:
            phase = phases[phase_id]
            assert phase["implemented"] is True
            assert phase["interaction_mode"] == "interactive"
            assert phase["actionable"] is False
            assert phase["disabled_reason_key"] == "phase.disabled.not_current"
            assert phase["name_key"].startswith("phase.")
            assert phase["description_key"].startswith("phase.")
            assert phase["status_key"]

    def test_shell_snapshot_exposes_i18n_keys_for_new_gui_copy(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        data = snapshot["data"]

        summary = data["selected_phase_summary"]
        assert summary["name_key"] == "phase.mortality.name"
        assert summary["status_key"] == "phase.status.actionable"
        assert data["global_warnings"][0]["key"] == "warning.gui_p0_05.senate_phase5a"

    def test_senate_phase_navigation_is_interactive_when_current(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]
        data = snapshot["data"]
        phases = {phase["id"]: phase for phase in data["phase_navigation"]}

        assert data["current_phase_id"] == "senate"
        assert phases["senate"]["implemented"] is True
        assert phases["senate"]["interaction_mode"] == "interactive"
        assert phases["senate"]["actionable"] is True
        assert phases["senate"]["current"] is True
        assert phases["senate"]["disabled_reason_key"] == ""
        assert phases["senate"]["disabled_reason"] == ""
        assert data["selected_phase_summary"]["interaction_mode"] == "interactive"
        assert data["selected_phase_summary"]["actionable"] is True
        assert data["selected_phase_summary"]["status_key"] == "phase.status.actionable"

    def test_can_create_population_fixture_explicitly(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["data"]["current_phase_id"] == "population"
        phases = {phase["id"]: phase for phase in snapshot["data"]["phase_navigation"]}
        assert phases["mortality"]["executed"] is True
        assert phases["revenue"]["executed"] is True
        assert phases["forum"]["executed"] is True
        assert phases["population"]["actionable"] is True

    def test_snapshot_no_other_faction_treasury(self):
        """快照不包含其他派系金库"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        snapshot = session_api.get_session_snapshot(state, viewer_id)
        data = snapshot["data"]
        # 只应包含 viewer 的派系资源
        fr = data["faction_resources"]
        assert fr is not None
        # my_figures 只应包含本派系人物
        my_figs = data["my_figures"]
        viewer_faction = data["viewer_faction_id"]
        for fig in my_figs:
            assert fig["faction_id"] == viewer_faction

    def test_get_population_view(self):
        """获取人口阶段视图"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        pop_view = session_api.get_population_view(state, viewer_id)
        assert pop_view["success"]
        data = pop_view["data"]
        assert "my_figures" in data
        assert "candidates" in data
        assert "my_votes" in data
        assert "can_campaign" in data
        assert "can_vote" in data
        assert "can_complete" in data
        assert "can_advance" in data
        assert data["current_step"] in {"campaign", "vote", "results"}
        assert "resolved" in data
        assert "election_results" in data
        assert "faction_influence_before" in data
        assert "faction_influence_after" in data

    def test_get_forum_view(self):
        result = session_api.create_gui_prototype_session(start_phase="forum")
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        from src.api import forum_api
        forum_view = forum_api.get_forum_view(state, viewer_id)

        assert forum_view["success"]
        data = forum_view["data"]
        assert data["phase_id"] == "forum"
        assert data["current_phase_id"] == "forum"
        assert data["current_step"] in {"retirement", "market", "resolution"}
        assert isinstance(data["my_figures"], list)
        assert isinstance(data["available_figures"], list)
        assert isinstance(data["pending_contracts"], list)
        assert isinstance(data["triumph_wars"], list)
        assert "can_execute" in data
        assert "can_advance" in data

    def test_complete_population_player(self):
        """完成当前玩家操作并切换"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        current = human_players[0]
        next_p = human_players[1] if len(human_players) > 1 else current

        # 切换到第一个玩家
        state.set_current_player(current)
        result = session_api.complete_population_player(state, current)
        assert result["success"]
        assert result["data"]["new_player_id"] in human_players

    def test_non_current_player_rejected(self):
        """非当前玩家请求被拒绝"""
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        if len(human_players) < 2:
            pytest.skip("Need at least 2 players")
        state.set_current_player(human_players[0])
        # 第二个玩家试图操作
        result = session_api.complete_population_player(state, human_players[1])
        assert not result["success"]

    def test_resolve_population_slice_two_step_contract(self):
        """Two-step contract: resolve records result, does NOT mark phase executed.

        Covers acceptance cases P-A01, P-A02, P-A07.
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        player_id = human_players[0]
        state.set_current_player(player_id)

        # Step 1: resolve (was done for all AI players via set_current_player above,
        # but the resolution only works after all human players completed too)
        # Re-run resolution to exercise the two-step path
        resolve_result = session_api.resolve_population_slice(state)
        assert resolve_result["success"]
        data = resolve_result["data"]
        assert "election_results" in data
        assert "faction_influence_before" in data
        assert "faction_influence_after" in data

        # Two-step contract: phase NOT executed after resolve
        assert not state.is_phase_executed("population")
        assert session_api._infer_current_phase_id(state) == "population"

        # View still shows population phase, can_advance should match standard pattern
        view = session_api.get_population_view(state, player_id)
        assert view["success"]
        assert view["data"]["resolved"] is True
        assert view["data"]["current_step"] == "results"
        # can_advance should now evaluate using the 4-condition pattern;
        # current phase is population, is_current_player, not executed, has result = True
        assert view["data"]["can_advance"] is True

        snapshot = session_api.get_session_snapshot(state, player_id)
        assert snapshot["success"]
        # current_phase_id should STILL be "population" because phase is not executed
        assert snapshot["data"]["current_phase_id"] == "population"

        # Step 2: advance
        adv_result = session_api.advance_population_phase(state, player_id)
        assert adv_result["success"] is True
        assert state.is_phase_executed("population")
        assert session_api._infer_current_phase_id(state) == "senate"

        # Post-advance snapshot
        snapshot2 = session_api.get_session_snapshot(state, player_id)
        assert snapshot2["success"]
        assert snapshot2["data"]["current_phase_id"] == "senate"

    def test_advance_population_before_resolve_returns_failure(self):
        """Advance before resolve returns failure; phase state unchanged.

        Covers acceptance case P-A04.
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        player_id = human_players[0]
        state.set_current_player(player_id)

        # Attempt advance without resolving first
        adv_result = session_api.advance_population_phase(state, player_id)
        assert not adv_result["success"]
        assert not state.is_phase_executed("population")
        assert session_api._infer_current_phase_id(state) == "population"

    def test_advance_population_non_current_player_returns_failure(self):
        """Non-current-player advance returns failure; phase state unchanged.

        Covers acceptance case P-A05.
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        if len(human_players) < 2:
            pytest.skip("Need at least 2 players")

        player1 = human_players[0]
        player2 = human_players[1]
        state.set_current_player(player1)

        # Resolve (player1 is current — resolution works)
        session_api.resolve_population_slice(state)

        # Player2 (non-current) tries to advance
        adv_result = session_api.advance_population_phase(state, player2)
        assert not adv_result["success"]
        # Phase state unchanged
        assert not state.is_phase_executed("population")

    def test_advance_population_double_advance_returns_failure(self):
        """Double advance returns failure; no duplicate side effects.

        Covers acceptance case P-A06.
        """
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        player_id = human_players[0]
        state.set_current_player(player_id)

        # Resolve
        session_api.resolve_population_slice(state)

        # First advance: should succeed
        adv1 = session_api.advance_population_phase(state, player_id)
        assert adv1["success"]
        assert state.is_phase_executed("population")

        # Second advance: should fail (already executed)
        adv2 = session_api.advance_population_phase(state, player_id)
        assert not adv2["success"]

    # ══════════════════════════════════════════════════════════════════
    # Combat phase session API tests
    # ══════════════════════════════════════════════════════════════════

    def test_implemented_phase_includes_combat(self):
        """_implemented_phase_ids() contains 'combat'."""
        assert "combat" in session_api._implemented_phase_ids()

    def test_phase_interaction_mode_combat(self):
        """_phase_interaction_mode('combat') returns 'interactive'."""
        assert session_api._phase_interaction_mode("combat") == "interactive"

    def test_phase_order_includes_combat(self):
        """_phase_order() contains 'combat' at index 5."""
        order = session_api._phase_order()
        assert "combat" in order
        assert order.index("combat") >= 4  # After senate

    def test_combat_phase_navigation_is_interactive_when_current(self):
        """When combat is the current phase, navigation shows it as interactive."""
        result = session_api.create_gui_prototype_session(start_phase="combat")
        assert result["success"]
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]
        data = snapshot["data"]
        phases = {phase["id"]: phase for phase in data["phase_navigation"]}

        assert data["current_phase_id"] == "combat"
        assert phases["combat"]["implemented"] is True
        assert phases["combat"]["interaction_mode"] == "interactive"
        assert phases["combat"]["actionable"] is True
        assert phases["combat"]["handoff_task"] == "GUI-P0-02E"

    def test_combat_snapshot_includes_expected_phase_data(self):
        """Snapshot includes combat phase with correct metadata."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]

        phases = {phase["id"]: phase for phase in snapshot["data"]["phase_navigation"]}
        combat = phases["combat"]

        assert combat["name"] == "战争"
        assert combat["subtitle"] == "陆战、海战与战役结果"
        assert "战争" in combat["description"]
        assert combat["index"] == 6  # 6th phase (1-indexed)
