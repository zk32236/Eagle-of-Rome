"""
src/ui/gui/session_store.py
GuiSessionStore — 唯一 GUI 会话存储。
QML 只能访问只读属性、列表模型和 Slot。
每次 API 操作后从 session_api 重新刷新。
"""
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Property, Slot, QAbstractListModel, Qt, QModelIndex

from src.core.game_state import GameState
from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.localization import gui_text

logger = logging.getLogger("EOR-GUI")


class GuiSessionStore(QObject):
    """
    GUI 会话存储。
    内部持有 GameState 引用，对 QML 暴露只读属性和信号。
    """

    # 信号
    snapshotChanged = Signal()
    populationViewChanged = Signal()
    currentPlayerChanged = Signal()
    phaseChanged = Signal()
    feedbackRaised = Signal(str, str)  # type, message
    handoffRequired = Signal(str)  # next_player_id

    def __init__(self, state: GameState, parent=None):
        super().__init__(parent)
        self._state = state
        self._adapter = GuiApiAdapter(state, refresh_callback=self._on_refresh)

        # 缓存的快照数据（只含 DTO）
        self._snapshot: Dict[str, Any] = {}
        self._population_view: Dict[str, Any] = {}
        self._current_player_id: str = ""
        self._viewer_id: str = ""
        self._selected_phase_id: str = "population"
        self._selected_phase_summary: Dict[str, Any] = {}
        self._feedback_queue: List[Dict[str, str]] = []

    # -----------------------------------------------------------------------
    # 初始化
    # -----------------------------------------------------------------------
    def initialize(self, viewer_id: str):
        """初始化，设置 viewer 并加载第一帧快照"""
        self._viewer_id = viewer_id
        self._refresh_snapshot()
        self._refresh_population_view()

    # -----------------------------------------------------------------------
    # QML 可访问属性
    # -----------------------------------------------------------------------
    @Property(str, notify=snapshotChanged)
    def currentPlayerId(self) -> str:
        return self._snapshot.get("current_player_id", "")

    @Property(str, notify=snapshotChanged)
    def viewerPlayerId(self) -> str:
        return self._snapshot.get("viewer_player_id", "")

    @Property(str, notify=snapshotChanged)
    def viewerFactionId(self) -> str:
        return self._snapshot.get("viewer_faction_id", "")

    @Property(bool, notify=snapshotChanged)
    def isCurrentPlayer(self) -> bool:
        return self._snapshot.get("is_current_player", False)

    @Property(str, notify=snapshotChanged)
    def yearDisplay(self) -> str:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("year_display", "")

    @Property(int, notify=snapshotChanged)
    def turnNumber(self) -> int:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("turn_number", 0)

    @Property(int, notify=snapshotChanged)
    def treasury(self) -> int:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("treasury", 0)

    @Property(int, notify=snapshotChanged)
    def factionTreasury(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("treasury", 0) if fr else 0

    @Property(int, notify=snapshotChanged)
    def factionInfluence(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("total_influence", 0) if fr else 0

    @Property(int, notify=snapshotChanged)
    def factionMemberCount(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("member_count", 0) if fr else 0

    @Property(list, notify=snapshotChanged)
    def phaseNavigation(self) -> List[Dict[str, Any]]:
        return self._snapshot.get("phase_navigation", [])

    @Property(str, notify=phaseChanged)
    def selectedPhaseId(self) -> str:
        return self._selected_phase_id

    @Property(str, notify=phaseChanged)
    def selectedPhaseName(self) -> str:
        return self._selected_phase_summary.get("name", "")

    @Property(dict, notify=phaseChanged)
    def selectedPhaseSummary(self) -> Dict[str, Any]:
        return self._selected_phase_summary

    @Property(str, notify=snapshotChanged)
    def currentPhaseId(self) -> str:
        return self._snapshot.get("current_phase_id", "population")

    @Property(str, notify=snapshotChanged)
    def currentPhaseName(self) -> str:
        for phase in self.phaseNavigation:
            if phase.get("id") == self.currentPhaseId:
                return phase.get("name", "")
        return "人口"

    @Property(str, notify=snapshotChanged)
    def viewerFactionName(self) -> str:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("name", "") if fr else self.viewerFactionId

    @Property(list, notify=snapshotChanged)
    def globalWarnings(self) -> List[Dict[str, str]]:
        return self._snapshot.get("global_warnings", [])

    @Property(list, notify=snapshotChanged)
    def myFigures(self) -> List[Dict[str, Any]]:
        return self._snapshot.get("my_figures", [])

    @Property(list, notify=populationViewChanged)
    def populationCandidates(self) -> List[Dict[str, Any]]:
        """返回按官职分组的候选人，转为扁平列表供 QML 消费"""
        candidates = self._population_view.get("candidates", {})
        flat = []
        office_names = {
            "consul": "执政官", "censor": "监察官", "praetor": "大法官",
            "quaestor": "财务官", "tribune": "保民官"
        }
        for office, cands in candidates.items():
            for c in cands:
                c_copy = dict(c)
                c_copy["office"] = office
                c_copy["office_name"] = office_names.get(office, office)
                flat.append(c_copy)
        return flat

    @Property(dict, notify=populationViewChanged)
    def myVotes(self) -> Dict[str, int]:
        return self._population_view.get("my_votes", {})

    @Property(bool, notify=populationViewChanged)
    def canCampaign(self) -> bool:
        return self._population_view.get("can_campaign", False)

    @Property(bool, notify=populationViewChanged)
    def canVote(self) -> bool:
        return self._population_view.get("can_vote", False)

    @Property(bool, notify=populationViewChanged)
    def canComplete(self) -> bool:
        return self._population_view.get("can_complete", False)

    # -----------------------------------------------------------------------
    # QML Slot — 操作入口
    # -----------------------------------------------------------------------
    @Slot(int, int, result=dict)
    def doCampaign(self, figure_id: int, amount: int) -> dict:
        """举办庆典"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.campaign(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_population_view()
        return feedback

    @Slot(str, int, result=dict)
    def doVote(self, office: str, figure_id: int) -> dict:
        """投票"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.vote(self._viewer_id, office, figure_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_population_view()
        return feedback

    @Slot(result=dict)
    def doCompletePlayer(self) -> dict:
        """完成当前玩家操作，切换下一个玩家"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.next_player(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            # 检查是否所有人类玩家都已完成
            new_id = feedback.get("data", {}).get("new_player_id")
            if new_id:
                self._viewer_id = new_id
                self.handoffRequired.emit(new_id)
            self._refresh_snapshot()
            self._refresh_population_view()
        return feedback

    @Slot(result=dict)
    def doResolveElection(self) -> dict:
        """结算选举"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.resolve_election()
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_population_view()
        return feedback

    @Slot(str, result=dict)
    def selectPhase(self, phase_id: str) -> dict:
        """Select a shell phase without executing phase business."""
        phase = self._phase_by_id(phase_id)
        if not phase:
            feedback = self._feedback(False, gui_text("feedback.phase.unknown", phase_id=phase_id), "error")
            self._raise_feedback(feedback)
            return feedback

        self._selected_phase_id = phase_id
        self._selected_phase_summary = self._summary_from_phase(phase)
        self.phaseChanged.emit()
        logger.info(
            "GUI phase selected",
            extra={
                "phase_id": phase_id,
                "viewer_player_id": self._viewer_id,
                "current_player_id": self.currentPlayerId,
                "implemented": phase.get("implemented", False),
            },
        )

        if not phase.get("implemented", False):
            feedback = self._feedback(
                True,
                gui_text(
                    "feedback.phase.placeholder",
                    name=phase.get("name", phase_id),
                    handoff_task=phase.get("handoff_task", "后续任务"),
                ),
                "warning",
                data={"phase_id": phase_id},
            )
            self._raise_feedback(feedback)
            return feedback

        feedback = self._feedback(
            True,
            gui_text("feedback.phase.selected", name=phase.get("name", phase_id)),
            "info",
            data={"phase_id": phase_id},
        )
        self._raise_feedback(feedback)
        self._refresh_population_view()
        return feedback

    @Slot(result=dict)
    def refreshSnapshot(self) -> dict:
        """Refresh the shell snapshot from authoritative API DTO."""
        self._refresh_snapshot()
        self._refresh_population_view()
        feedback = self._feedback(True, gui_text("feedback.snapshot.refreshed"), "success")
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=bool)
    def switchViewer(self, new_viewer_id: str) -> bool:
        """切换 viewer（用于玩家交接遮罩确认后）"""
        self._viewer_id = new_viewer_id
        self._refresh_snapshot()
        self._refresh_population_view()
        self.currentPlayerChanged.emit()
        return True

    @Slot(str)
    def logUiEvent(self, message: str):
        """QML 记录 UI 事件"""
        logger.info(f"[UI] {message}")

    # -----------------------------------------------------------------------
    # 内部刷新
    # -----------------------------------------------------------------------
    def _on_refresh(self):
        """API 操作成功后自动刷新"""
        self._refresh_snapshot()
        self._refresh_population_view()

    def _refresh_snapshot(self):
        self._snapshot = self._adapter.get_snapshot(self._viewer_id)
        if not self._selected_phase_id:
            self._selected_phase_id = self._snapshot.get("selected_phase_id", "population")
        self._selected_phase_summary = self._summary_from_phase(
            self._phase_by_id(self._selected_phase_id)
        )
        self.snapshotChanged.emit()
        self.phaseChanged.emit()
        self.currentPlayerChanged.emit()

    def _refresh_population_view(self):
        self._population_view = self._adapter.get_population_view(self._viewer_id)
        self.populationViewChanged.emit()

    def _raise_feedback(self, feedback: dict):
        ftype = feedback.get("feedback_type", "info")
        fmsg = feedback.get("feedback_message", "")
        if fmsg:
            self.feedbackRaised.emit(ftype, fmsg)

    def _phase_by_id(self, phase_id: str) -> Dict[str, Any]:
        for phase in self.phaseNavigation:
            if phase.get("id") == phase_id:
                return phase
        return {}

    def _summary_from_phase(self, phase: Dict[str, Any]) -> Dict[str, Any]:
        if not phase:
            return self._snapshot.get("selected_phase_summary", {})
        implemented = phase.get("implemented", False)
        return {
            "id": phase.get("id", ""),
            "name": phase.get("name", ""),
            "subtitle": phase.get("subtitle", ""),
            "description": phase.get("description", ""),
            "implemented": implemented,
            "actionable": phase.get("actionable", False),
            "handoff_task": phase.get("handoff_task", ""),
            "name_key": phase.get("name_key", ""),
            "subtitle_key": phase.get("subtitle_key", ""),
            "description_key": phase.get("description_key", ""),
            "status_key": phase.get("status_key", ""),
            "status_text": gui_text("phase.status.actionable") if implemented else gui_text("phase.status.placeholder"),
            "disabled_reason": phase.get("disabled_reason") or gui_text(
                "phase.disabled.placeholder",
                handoff_task=phase.get("handoff_task", "后续任务"),
            ),
        }

    def _feedback(
        self,
        success: bool,
        message: str,
        feedback_type: str,
        data: Any = None,
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "data": data,
            "errors": [] if success else [message],
            "feedback_type": feedback_type,
            "feedback_message": message,
        }
