"""
src/tests/test_gui/test_adapter.py
GuiApiAdapter 测试
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import GuiSessionStore
from src.api import session_api


class TestGuiApiAdapter:
    """GUI API Adapter 测试"""

    def setup_adapter(self):
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        adapter = GuiApiAdapter(state)
        return adapter, state, human_players

    def test_call_success(self):
        """正确映射成功响应"""
        adapter, state, players = self.setup_adapter()
        state.set_current_player(players[0])
        # 获取快照
        snapshot = adapter.get_snapshot(players[0])
        assert isinstance(snapshot, dict)
        assert "my_figures" in snapshot

    def test_campaign_failure_insufficient_wealth(self):
        """资金不足时失败且不改变状态"""
        adapter, state, players = self.setup_adapter()
        state.set_current_player(players[0])
        my_figs = adapter.get_snapshot(players[0]).get("my_figures", [])
        if not my_figs:
            pytest.skip("No figures available")
        fig = my_figs[0]
        before_wealth = fig["wealth"]
        # 尝试投入超过财富的金额
        feedback = adapter.campaign(players[0], fig["id"], before_wealth + 1000)
        assert not feedback["success"]
        assert feedback["feedback_type"] == "error"
        # 验证状态未改变
        snapshot = adapter.get_snapshot(players[0])
        fig_after = next((f for f in snapshot.get("my_figures", []) if f["id"] == fig["id"]), None)
        assert fig_after is not None
        assert fig_after["wealth"] == before_wealth

    def test_next_player_success(self):
        """切换玩家成功"""
        adapter, state, players = self.setup_adapter()
        state.set_current_player(players[0])
        feedback = adapter.next_player(players[0])
        assert feedback["success"]
        assert "new_player_id" in feedback.get("data", {})

    def test_next_player_wrong_player(self):
        """非当前玩家切换失败"""
        adapter, state, players = self.setup_adapter()
        if len(players) < 2:
            pytest.skip("Need at least 2 players")
        state.set_current_player(players[0])
        feedback = adapter.next_player(players[1])
        assert not feedback["success"]
        assert feedback["feedback_type"] == "error"

    def test_session_store_selects_placeholder_phase_without_business_execution(self):
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        messages = []
        store.feedbackRaised.connect(lambda ftype, message: messages.append((ftype, message)))
        feedback = store.selectPhase("senate")

        assert feedback["success"]
        assert store.selectedPhaseId == "senate"
        assert store.selectedPhaseSummary["implemented"] is False
        assert store.selectedPhaseSummary["handoff_task"] == "GUI-P0-02C"
        assert messages[-1][0] == "warning"

    def test_session_store_can_return_to_population_after_placeholder_phase(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        store.selectPhase("combat")
        feedback = store.selectPhase("population")

        assert feedback["success"]
        assert store.selectedPhaseId == "population"
        assert store.selectedPhaseSummary["implemented"] is True
        assert isinstance(store.myFigures, list)
