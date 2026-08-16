"""
src/tests/test_gui/test_resolution_advance.py
Resolution Advance (B3) — doAdvanceResolution / GameShell Registration 测试

Tests:
- doAdvanceResolution() success path (advance year -> mortality)
- doAdvanceResolution() failure path (stay in phase 7, preserve results)
- doAdvanceResolution() idempotence (cannot call while advancing)
- isResolutionAdvancing loading flag
- Permission guards (not current player, not resolved)
- doAdvanceCurrentPhase dispatches to doAdvanceResolution
- _PHASE_ADVANCE_DISPATCH has resolution entry
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.ui.gui.session_store import GuiSessionStore
from src.api import session_api


def _make_resolution_ready(state, player_id):
    """Execute combat so resolution can be auto-settled, then select resolution."""
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")


class TestResolutionAdvance:
    """GUI Session Store doAdvanceResolution 集成测试"""

    def setup_store(self, start_phase="combat"):
        """Set up session at combat phase, ready for resolution."""
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
        assert result["success"]
        state = result["data"]["state"]
        players = result["data"]["human_players"]
        store = GuiSessionStore(state)
        store.initialize(players[0])
        return store, state, players

    # ------------------------------------------------------------------
    # 1. Dispatcher existence
    # ------------------------------------------------------------------
    def test_phase_advance_dispatch_has_resolution_entry(self):
        """_PHASE_ADVANCE_DISPATCH 包含 resolution 条目"""
        store, state, players = self.setup_store()
        dispatch = store._PHASE_ADVANCE_DISPATCH
        assert "resolution" in dispatch
        entry = dispatch["resolution"]
        assert entry["can_attr"] == "canAdvanceResolution"
        assert entry["slot"] == "doAdvanceResolution"
        assert "进入下一年度" in entry["label"]

    def test_resolution_advance_label_semantics(self):
        """按钮文案「⏭️ 进入下一年度」精确映射 advance_year 跨年语义（非通用阶段推进）"""
        store, state, players = self.setup_store()
        label = store._PHASE_ADVANCE_DISPATCH["resolution"]["label"]
        assert label == "\u23ed\ufe0f 进入下一年度"
        assert "下一年度" in label
        assert "下一回合" not in label  # 不再是通用阶段推进

    def test_advance_current_phase_dispatches_resolution(self):
        """doAdvanceCurrentPhase 将 resolution 分派到 doAdvanceResolution"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()

        # 进入 resolution 阶段（触发自动结算）
        store.selectPhase("resolution")
        assert store.resolutionResolved is True
        assert store.canAdvanceResolution is True

        # 通过统一分派调用
        result = store.doAdvanceCurrentPhase()
        # 应执行 advance_year，返回 success
        assert result["success"], f"advance failed: {result.get('message')}"
        assert store.selectedPhaseId == "mortality"

    # ------------------------------------------------------------------
    # 2. doAdvanceResolution success path
    # ------------------------------------------------------------------
    def test_do_advance_resolution_success(self):
        """结算完成 + 当前玩家时 doAdvanceResolution 成功，回到天命阶段"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()

        store.selectPhase("resolution")
        assert store.resolutionResolved is True

        result = store.doAdvanceResolution()
        assert result["success"], f"Advance failed: {result.get('message')}"

        # 回到天命阶段
        assert store.selectedPhaseId == "mortality"
        # phaseChanged 信号应发射（可以通过副作用验证——selectedPhaseId 已更新）

    def test_do_advance_resolution_updates_snapshot(self):
        """成功后 snapshot 被刷新"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()

        store.selectPhase("resolution")
        before_turn = store.turnNumber

        result = store.doAdvanceResolution()
        assert result["success"]

        # 快照已刷新
        assert store.currentPhaseId == "mortality"
        # 回合数（yearDisplay）在 advance_year 后应更新
        # 注：实际 advance_year 是否增加 turn 视实现而定，此处仅检查不抛异常

    def test_do_advance_resolution_phase_changed_emitted(self):
        """成功后 phaseChanged 信号发射"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        signals = []
        store.phaseChanged.connect(lambda: signals.append(1))

        result = store.doAdvanceResolution()
        assert result["success"]
        assert len(signals) >= 1

    def test_do_advance_resolution_resets_resolving_flag(self):
        """doAdvanceResolution 完成后 _resolution_advancing 重置为 False"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # 确认初始状态
        assert store.isResolutionAdvancing is False

        # 执行推进
        store.doAdvanceResolution()

        # flag 已重置
        assert store.isResolutionAdvancing is False

    # ------------------------------------------------------------------
    # 3. doAdvanceResolution failure/stay path
    # ------------------------------------------------------------------
    def test_do_advance_resolution_fails_if_not_resolved(self):
        """未结算时拒绝推进"""
        store, state, players = self.setup_store()
        player_id = players[0]
        state.set_current_player(player_id)
        store.refreshSnapshot()

        # 直接进入 resolution 阶段（尚未结算）
        store.selectPhase("resolution")
        # 此时可能自动结算已经开始或已完成
        # 测试另一种情况：强制设置 store._resolution_view 为未结算
        store._resolution_view = {
            "resolved": False,
            "is_current_player": True,
            "step_statuses": [],
            "results": {},
            "warnings": [],
            "summary": {},
        }
        store.resolutionViewChanged.emit()

        result = store.doAdvanceResolution()
        assert not result["success"]
        assert store.selectedPhaseId == "resolution"  # 未切换

    def test_do_advance_resolution_stays_in_phase_7_after_failure(self):
        """失败后停留在 Phase 7，保留结算结果"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # 模拟 advance_year 失败：注入一个假的 advance_year 到 adapter
        original_advance = store._adapter.advance_year
        def failing_advance(pid):
            return {"success": False, "message": "Simulated failure", "feedback_type": "error"}
        store._adapter.advance_year = failing_advance

        try:
            result = store.doAdvanceResolution()
            assert not result["success"]
            assert store.selectedPhaseId == "resolution"  # 未切换
            # 结算结果应保留
            assert store.resolutionResolved is True
        finally:
            store._adapter.advance_year = original_advance

    # ------------------------------------------------------------------
    # 4. Loading flag / idempotence
    # ------------------------------------------------------------------
    def test_is_resolution_advancing_false_by_default(self):
        """初始状态 isResolutionAdvancing 为 False"""
        store, state, players = self.setup_store()
        assert store.isResolutionAdvancing is False

    def test_is_resolution_advancing_true_during_execution(self):
        """doAdvanceResolution 执行中 isResolutionAdvancing 为 True"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # 拦截 advance_year 来检测 flag 状态
        original_advance = store._adapter.advance_year
        captured_flag = []

        def test_advance(pid):
            captured_flag.append(store.isResolutionAdvancing)
            return original_advance(pid)

        store._adapter.advance_year = test_advance

        try:
            store.doAdvanceResolution()
            assert len(captured_flag) >= 1
            assert captured_flag[0] is True, "advancing flag was not True during execution"
        finally:
            store._adapter.advance_year = original_advance

    def test_do_advance_resolution_rejects_while_advancing(self):
        """正在推进时第二次调用被拒绝（幂等）"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # 手动设置 advancing flag
        store._resolution_advancing = True
        store.resolutionAdvancingChanged.emit()

        result = store.doAdvanceResolution()
        assert not result["success"]
        assert "正在推进" in result.get("message", "") or "wait" in result.get("message", "").lower()

    def test_is_resolution_advancing_emits_signal(self):
        """isResolutionAdvancing 的变化发射 resolutionAdvancingChanged 信号"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        signals = []
        store.resolutionAdvancingChanged.connect(lambda: signals.append(1))

        store.doAdvanceResolution()
        # 至少发射 2 次：True → False
        assert len(signals) >= 2

    # ------------------------------------------------------------------
    # 5. Permission guards
    # ------------------------------------------------------------------
    def test_do_advance_resolution_fails_for_non_current_player(self):
        """非当前玩家时拒绝推进"""
        store, state, players = self.setup_store()
        if len(players) < 2:
            pytest.skip("Need at least 2 players")

        player_id = players[0]
        other_player = players[1]
        state.set_current_player(player_id)
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        # 切换到其他玩家
        store.switchViewer(other_player)
        store._refresh_resolution_view()

        result = store.doAdvanceResolution()
        assert not result["success"]

    def test_do_advance_resolution_fails_if_not_initialized(self):
        """未初始化时拒绝"""
        store, state, players = self.setup_store()
        store._viewer_id = ""  # 清空 viewer_id

        result = store.doAdvanceResolution()
        assert not result["success"]

    def test_can_advance_resolution_tied_to_advancing_flag(self):
        """_resolution_advancing 会影响 canAdvanceResolution"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        assert store.canAdvanceResolution is True

        # 设置 advancing flag
        store._resolution_advancing = True
        store.resolutionAdvancingChanged.emit()
        store.resolutionViewChanged.emit()

        assert store.canAdvanceResolution is False

        # 重置
        store._resolution_advancing = False
        store.resolutionAdvancingChanged.emit()
        store.resolutionViewChanged.emit()

        assert store.canAdvanceResolution is True

    # ------------------------------------------------------------------
    # 6. Loader / progress indicator 绑定
    # ------------------------------------------------------------------
    def test_is_resolution_advancing_resets_on_failure(self):
        """推进失败后 isResolutionAdvancing 重置为 False"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        original_advance = store._adapter.advance_year
        def failing_advance(pid):
            return {"success": False, "message": "Simulated error", "feedback_type": "error"}
        store._adapter.advance_year = failing_advance

        try:
            store.doAdvanceResolution()
            assert store.isResolutionAdvancing is False
        finally:
            store._adapter.advance_year = original_advance

    # ------------------------------------------------------------------
    # 7. doAdvanceResolution signal behavior
    # ------------------------------------------------------------------
    def test_resolution_view_changed_emitted_on_advance(self):
        """推进期间 resolutionViewChanged 发射（通知 QML 绑定更新）"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        signals = []
        store.resolutionViewChanged.connect(lambda: signals.append(1))

        store.doAdvanceResolution()
        # 至少发射 2 次（进入/退出 advancing 时的 emit）
        assert len(signals) >= 2

    def test_do_advance_resolution_returns_structured_dict(self):
        """doAdvanceResolution 返回结构化反馈 dict"""
        store, state, players = self.setup_store()
        player_id = players[0]
        _make_resolution_ready(state, player_id)
        store.refreshSnapshot()
        store.selectPhase("resolution")

        result = store.doAdvanceResolution()
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result
        assert "feedback_type" in result
