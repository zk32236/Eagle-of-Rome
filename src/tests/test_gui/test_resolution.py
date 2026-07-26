"""
src/tests/test_gui/test_resolution.py
Resolution View/Stage 测试 — B2

Tests:
- Resolution DTO through adapter
- Store resolution properties (read-only)
- Auto-settlement trigger on selectPhase("resolution")
- canAdvanceResolution flag
- Step status (all pending → all completed)
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import GuiSessionStore
from src.api import session_api


def _make_resolution_ready(state, player_id):
    """Execute all phases up to combat so resolution can be executed."""
    # Both combat and resolution are not yet executed when start_phase="combat"
    # We need combat to be executed before resolution can run
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")


class TestResolutionAdapter:
    """Resolution API Adapter 测试"""

    def setup_adapter(self, start_phase="combat"):
        """Set up session at combat phase."""
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
        assert result["success"]
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        adapter = GuiApiAdapter(state)
        return adapter, state, human_players

    def test_get_resolution_view_returns_dto_when_not_resolved(self):
        """未结算时 get_resolution_view 返回 DTO 且不抛异常"""
        adapter, state, players = self.setup_adapter()
        view = adapter.get_resolution_view(players[0])
        assert isinstance(view, dict)
        assert "resolved" in view
        assert view["resolved"] is False
        assert "step_statuses" in view
        assert "results" in view
        assert "warnings" in view
        assert "summary" in view
        assert "is_current_player" in view

    def test_get_resolution_view_has_five_steps(self):
        """步进状态正好五个"""
        adapter, state, players = self.setup_adapter()
        view = adapter.get_resolution_view(players[0])
        assert len(view["step_statuses"]) == 5

    def test_get_resolution_view_steps_all_pending_when_not_resolved(self):
        """未结算时全部 pending"""
        adapter, state, players = self.setup_adapter()
        view = adapter.get_resolution_view(players[0])
        for step in view["step_statuses"]:
            assert step["status"] == "pending"

    def test_get_resolution_view_after_execution(self):
        """结算后步骤全部 completed，且有结果数据"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        _make_resolution_ready(state, player_id)

        # 执行 resolution
        feedback = adapter.execute_phase("resolution", player_id)
        assert feedback["success"], f"Resolution execution failed: {feedback.get('message')}"

        view = adapter.get_resolution_view(player_id)
        assert view["resolved"] is True
        for step in view["step_statuses"]:
            assert step["status"] == "completed"

        # 检查结果结构
        assert isinstance(view["results"], dict)
        assert "governor_transitions" in view["results"]
        assert "contracts_expired" in view["results"]
        assert "treasury" in view["results"]
        assert "legion_status" in view["results"]

        # 检查总结结构
        assert isinstance(view["summary"], dict)
        assert "dominant_faction" in view["summary"]
        assert "treasury" in view["summary"]
        assert "next_year" in view["summary"]
        assert "decay_applied" in view["summary"]

    def test_get_resolution_view_warnings_list(self):
        """结算后 warnings 是列表"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        adapter.execute_phase("resolution", player_id)
        view = adapter.get_resolution_view(player_id)
        assert isinstance(view["warnings"], list)

    def test_get_resolution_view_is_current_player(self):
        """is_current_player 正确反映当前玩家"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        state.set_current_player(player_id)
        view = adapter.get_resolution_view(player_id)
        assert view["is_current_player"] is True

    def test_get_resolution_view_non_current_player(self):
        """非当前玩家 is_current_player=False"""
        adapter, state, players = self.setup_adapter()
        if len(players) < 2:
            pytest.skip("Need at least 2 players")
        state.set_current_player(players[0])
        view = adapter.get_resolution_view(players[1])
        assert view["is_current_player"] is False

    def test_execute_phase_resolution_success(self):
        """execute_phase("resolution", ...) 成功"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        feedback = adapter.execute_phase("resolution", player_id)
        assert feedback["success"], f"Resolution execution failed: {feedback.get('message')}"
        assert state.is_phase_executed("resolution")

    def test_execute_phase_resolution_idempotent(self):
        """二次执行 resolution 幂等"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        feedback1 = adapter.execute_phase("resolution", player_id)
        assert feedback1["success"]
        feedback2 = adapter.execute_phase("resolution", player_id)
        # 第二次可能不成功（幂等），但不应抛异常
        assert isinstance(feedback2, dict)
        # ResolutionCommand should return success even on second call (no-op)
        # or mark_phase_executed is already set

    def test_adapter_execute_phase_returns_feedback_dict(self):
        """execute_phase adapter method returns structured feedback"""
        adapter, state, players = self.setup_adapter()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        feedback = adapter.execute_phase("resolution", player_id)
        assert isinstance(feedback, dict)
        assert "success" in feedback
        assert "message" in feedback
        assert "feedback_type" in feedback


class TestResolutionStore:
    """GUI Session Store Resolution 属性测试"""

    def setup_store(self, start_phase="combat"):
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
        assert result["success"]
        state = result["data"]["state"]
        players = result["data"]["human_players"]
        state.set_current_player(players[0])
        store = GuiSessionStore(state)
        store.initialize(players[0])
        return store, state, players

    def test_resolution_properties_exist(self):
        """Resolution 只读属性均存在"""
        store, state, players = self.setup_store()
        # 初始未结算
        assert hasattr(store, "resolutionView")
        assert hasattr(store, "resolutionStepStatuses")
        assert hasattr(store, "resolutionResults")
        assert hasattr(store, "resolutionWarnings")
        assert hasattr(store, "resolutionSummary")
        assert hasattr(store, "resolutionResolved")
        assert hasattr(store, "canAdvanceResolution")
        assert hasattr(store, "isResolutionResolving")

    def test_resolution_initial_not_resolved(self):
        """初始状态未结算"""
        store, state, players = self.setup_store()
        assert store.resolutionResolved is False
        assert store.canAdvanceResolution is False

    def test_resolution_initial_steps_all_pending(self):
        """初始步骤全部 pending"""
        store, state, players = self.setup_store()
        steps = store.resolutionStepStatuses
        assert len(steps) == 5
        for step in steps:
            assert step["status"] == "pending"

    def test_select_phase_resolution_triggers_auto_settlement(self):
        """selectPhase('resolution') 自动触发结算"""
        store, state, players = self.setup_store()
        player_id = players[0]

        # 准备 combat 已执行
        _make_resolution_ready(state, player_id)
        # 刷新 store 状态（refresh_snapshot 读取执行标记）
        store.refreshSnapshot()

        # 尚未执行 resolution
        assert not state.is_phase_executed("resolution")

        # 选择 resolution 阶段 → 自动结算
        feedback = store.selectPhase("resolution")
        assert feedback["success"]
        assert store.selectedPhaseId == "resolution"

        # 结算应已自动触发
        assert state.is_phase_executed("resolution")

        # Store resolution 状态更新
        assert store.resolutionResolved is True
        assert store.resolutionStepStatuses[0]["status"] == "completed"

    def test_auto_settlement_idempotent(self):
        """二次进入 resolution 不重复结算"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()

        # 第一次进入 → 自动结算
        store.selectPhase("resolution")
        assert state.is_phase_executed("resolution")

        # 切换到其他阶段再切回来
        store.selectPhase("mortality")
        store.selectPhase("resolution")

        # 不应重复结算（is_phase_executed 已经在 B1 的 execute_phase 中检查）
        # 但 resolution view 应仍然显示已结算
        store._refresh_resolution_view()
        assert store.resolutionResolved is True

    def test_can_advance_resolution_after_settlement(self):
        """结算完成后 canAdvanceResolution 为 True"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")
        assert store.resolutionResolved is True
        assert store.canAdvanceResolution is True

    def test_resolution_warnings_present_after_settlement(self):
        """结算后 warnings 存在（可能是空列表）"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")
        assert isinstance(store.resolutionWarnings, list)

    def test_resolution_summary_populated_after_settlement(self):
        """结算后 summary 有数据"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")
        summary = store.resolutionSummary
        assert isinstance(summary, dict)
        # should have treasury data or at least structure
        assert "treasury" in summary or "next_year" in summary

    def test_resolution_view_signal_emitted(self):
        """resolutionViewChanged 信号在刷新时发射"""
        store, state, players = self.setup_store()
        signals = []
        store.resolutionViewChanged.connect(lambda: signals.append(1))
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")
        # selectPhase triggers _refresh_resolution_view which emits signal
        assert len(signals) >= 1

    def test_resolution_results_summary_all_properties_from_dto(self):
        """所有 DTO 字段通过 store 属性可访问"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        view = store.resolutionView
        assert isinstance(view, dict)
        assert "resolved" in view
        assert "step_statuses" in view
        assert "results" in view
        assert "warnings" in view
        assert "summary" in view
        assert "is_current_player" in view
