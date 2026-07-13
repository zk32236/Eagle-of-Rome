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
        assert phases["senate"]["interaction_mode"] == "readonly"
        assert phases["senate"]["actionable"] is False
        assert phases["senate"]["disabled_reason_key"] == "phase.disabled.readonly"
        assert phases["revenue"]["implemented"] is True
        assert phases["revenue"]["actionable"] is False
        assert phases["revenue"]["disabled_reason_key"] == "phase.disabled.not_current"
        assert phases["revenue"]["handoff_task"] == "GUI-P0-03"
        for phase_id, phase in phases.items():
            if phase_id in {"mortality", "revenue", "population", "senate"}:
                continue
            assert phase["implemented"] is False
            assert phase["interaction_mode"] == "placeholder"
            assert phase["actionable"] is False
            assert phase["handoff_task"].startswith("GUI-P0-02")
            assert phase["name_key"].startswith("phase.")
            assert phase["description_key"].startswith("phase.")
            assert phase["status_key"]
            assert phase["disabled_reason_key"] == "phase.disabled.placeholder"
            assert "暂不可操作" in phase["disabled_reason"]

    def test_shell_snapshot_exposes_i18n_keys_for_new_gui_copy(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        data = snapshot["data"]

        summary = data["selected_phase_summary"]
        assert summary["name_key"] == "phase.mortality.name"
        assert summary["status_key"] == "phase.status.actionable"
        assert data["global_warnings"][0]["key"] == "warning.gui_p0_02c_1.readonly_senate"

    def test_senate_phase_navigation_is_readonly_when_current(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]

        snapshot = session_api.get_session_snapshot(state, viewer_id)
        assert snapshot["success"]
        data = snapshot["data"]
        phases = {phase["id"]: phase for phase in data["phase_navigation"]}

        assert data["current_phase_id"] == "senate"
        assert phases["senate"]["implemented"] is True
        assert phases["senate"]["interaction_mode"] == "readonly"
        assert phases["senate"]["actionable"] is False
        assert phases["senate"]["current"] is True
        assert phases["senate"]["disabled_reason_key"] == "phase.disabled.readonly"
        assert "只读" in phases["senate"]["disabled_reason"]
        assert data["selected_phase_summary"]["interaction_mode"] == "readonly"
        assert data["selected_phase_summary"]["actionable"] is False
        assert "只读" in data["selected_phase_summary"]["status_text"]

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

    def test_resolve_population_slice(self):
        """结算人口阶段"""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        for pid in human_players:
            state.set_current_player(pid)
        # 结算
        result = session_api.resolve_population_slice(state)
        assert result["success"]
        assert state.is_phase_executed("population")
