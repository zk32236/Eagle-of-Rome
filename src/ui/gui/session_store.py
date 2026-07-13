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
    mortalityViewChanged = Signal()
    senateViewChanged = Signal()
    revenueViewChanged = Signal()
    queryResultChanged = Signal()
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
        self._mortality_view: Dict[str, Any] = {}
        self._senate_view: Dict[str, Any] = {}
        self._revenue_view: Dict[str, Any] = {}
        self._revenue_result: Dict[str, Any] = {}
        self._mortality_result: Dict[str, Any] = {}
        self._current_player_id: str = ""
        self._viewer_id: str = ""
        self._selected_phase_id: str = ""
        self._selected_phase_summary: Dict[str, Any] = {}
        self._global_query_result: Dict[str, Any] = {}
        self._feedback_queue: List[Dict[str, str]] = []

    # -----------------------------------------------------------------------
    # 初始化
    # -----------------------------------------------------------------------
    def initialize(self, viewer_id: str):
        """初始化，设置 viewer 并加载第一帧快照"""
        self._viewer_id = viewer_id
        self._refresh_snapshot()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()

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
        return self._snapshot.get("current_phase_id", "mortality")

    @Property(str, notify=snapshotChanged)
    def currentPhaseName(self) -> str:
        for phase in self.phaseNavigation:
            if phase.get("id") == self.currentPhaseId:
                return phase.get("name", "")
        return "天命"

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

    @Property(dict, notify=mortalityViewChanged)
    def mortalityResult(self) -> Dict[str, Any]:
        return self._mortality_result

    @Property(list, notify=mortalityViewChanged)
    def mortalityEvents(self) -> List[Dict[str, Any]]:
        return self._mortality_result.get("events", []) or self._mortality_view.get("events", [])

    @Property(bool, notify=mortalityViewChanged)
    def canExecuteMortality(self) -> bool:
        return self._mortality_view.get("can_execute", False)

    @Property(bool, notify=mortalityViewChanged)
    def canAdvanceMortality(self) -> bool:
        return self._mortality_view.get("can_advance", False)

    @Property(dict, notify=senateViewChanged)
    def senateView(self) -> Dict[str, Any]:
        return self._senate_view

    @Property(list, notify=senateViewChanged)
    def senateFactionLeaders(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("faction_leaders", [])

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self) -> Dict[str, Any]:
        return self._senate_view.get("presiding_officer") or {}

    @Property(int, notify=senateViewChanged)
    def warCount(self) -> int:
        return len(self._senate_view.get("active_foreign_wars", []))

    @Property(list, notify=senateViewChanged)
    def senateActiveForeignWars(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("active_foreign_wars", [])

    @Property(list, notify=senateViewChanged)
    def senateWarThreats(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("war_threats", [])

    @Property(list, notify=senateViewChanged)
    def senatePendingPeaceTreaties(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("pending_peace_treaties", [])

    @Property(list, notify=senateViewChanged)
    def senateGovernorVacancies(self) -> List[Dict[str, Any]]:
        vacancies = self._senate_view.get("governor_vacancies", {}) or {}
        flat = []
        type_names = {"proconsul": "行省总督", "propraetor": "副总督"}
        for governor_type, provinces in vacancies.items():
            for province in provinces:
                item = dict(province)
                item["governor_type"] = governor_type
                item["governor_type_name"] = type_names.get(governor_type, governor_type)
                flat.append(item)
        return flat

    @Property(list, notify=senateViewChanged)
    def senatePendingContracts(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("pending_contracts", [])

    # -----------------------------------------------------------------------
    # 收入阶段属性
    # -----------------------------------------------------------------------
    @Property(dict, notify=revenueViewChanged)
    def revenueResult(self) -> Dict[str, Any]:
        return self._revenue_result

    @Property(dict, notify=revenueViewChanged)
    def revenueView(self) -> Dict[str, Any]:
        return self._revenue_view

    @Property(dict, notify=revenueViewChanged)
    def revenueSettledData(self) -> Dict[str, Any]:
        settled = self._revenue_view.get("settled_data")
        if settled:
            return settled
        return self._revenue_result or {}

    @Property(bool, notify=revenueViewChanged)
    def canExecuteRevenue(self) -> bool:
        return self._revenue_view.get("can_execute", False)

    @Property(bool, notify=revenueViewChanged)
    def canAdvanceRevenue(self) -> bool:
        return self._revenue_view.get("can_advance", False)

    @Property(int, notify=revenueViewChanged)
    def treasuryDelta(self) -> int:
        result = self._revenue_result
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if not data:
            data = self._revenue_view.get("settled_data", {}) or {}
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
        return data.get("treasury_delta", 0) if isinstance(data, dict) else 0

    @Property(int, notify=revenueViewChanged)
    def endingTreasury(self) -> int:
        result = self._revenue_result
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if not data:
            data = self._revenue_view.get("settled_data", {}) or {}
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
        return data.get("ending_treasury", self.treasury) if isinstance(data, dict) else self.treasury

    @Property(dict, notify=queryResultChanged)
    def globalQueryResult(self) -> Dict[str, Any]:
        return self._global_query_result

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
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
        return feedback

    @Slot(result=dict)
    def doResolveElection(self) -> dict:
        """结算选举"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.resolve_election()
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        return feedback

    @Slot(result=dict)
    def doExecuteMortality(self) -> dict:
        """执行天命阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.execute_mortality(self._viewer_id)
        if feedback.get("success"):
            self._mortality_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
        self._raise_feedback(feedback)
        self.mortalityViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceMortality(self) -> dict:
        """确认天命结果并进入收入阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_mortality(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
        self._raise_feedback(feedback)
        self.mortalityViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doExecuteRevenue(self) -> dict:
        """执行收入结算。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.settle_revenue(self._viewer_id)
        if feedback.get("success"):
            self._revenue_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
        self._raise_feedback(feedback)
        self.revenueViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceRevenue(self) -> dict:
        """确认收入结算并推进到广场阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_revenue(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
        self._raise_feedback(feedback)
        self.revenueViewChanged.emit()
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
        if phase_id == "population":
            self._refresh_population_view()
        elif phase_id == "mortality":
            self._refresh_mortality_view()
        elif phase_id == "revenue":
            self._refresh_revenue_view()
        elif phase_id == "senate":
            self._refresh_senate_view()
        return feedback

    @Slot(str, result=dict)
    def doGlobalQuery(self, query_id: str) -> dict:
        """Run a safe read-only global query for the OPC bottom bar."""
        if not self._viewer_id:
            feedback = self._feedback(False, gui_text("feedback.query.not_initialized"), "error")
            self._raise_feedback(feedback)
            return feedback

        result = self._adapter.get_global_query_result(self._viewer_id, query_id)
        self._global_query_result = result
        self.queryResultChanged.emit()
        feedback_type = "success" if result.get("status") in {"connected", "readonly"} else "warning"
        feedback = self._feedback(
            True,
            gui_text("feedback.query.selected", title=result.get("title", query_id)),
            feedback_type,
            data=result,
        )
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=dict)
    def refreshSnapshot(self) -> dict:
        """Refresh the shell snapshot from authoritative API DTO."""
        self._refresh_snapshot()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()
        feedback = self._feedback(True, gui_text("feedback.snapshot.refreshed"), "success")
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=bool)
    def switchViewer(self, new_viewer_id: str) -> bool:
        """切换 viewer（用于玩家交接遮罩确认后）"""
        self._viewer_id = new_viewer_id
        self._refresh_snapshot()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()
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
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()

    def _refresh_snapshot(self):
        self._snapshot = self._adapter.get_snapshot(self._viewer_id)
        new_current = self._snapshot.get("current_phase_id", "mortality")
        if not self._selected_phase_id or self._selected_phase_id != new_current:
            self._selected_phase_id = new_current
        self._selected_phase_summary = self._summary_from_phase(
            self._phase_by_id(self._selected_phase_id)
        )
        self.snapshotChanged.emit()
        self.phaseChanged.emit()
        self.currentPlayerChanged.emit()

    def _refresh_population_view(self):
        self._population_view = self._adapter.get_population_view(self._viewer_id)
        self.populationViewChanged.emit()

    def _refresh_mortality_view(self):
        self._mortality_view = self._adapter.get_mortality_view(self._viewer_id)
        self.mortalityViewChanged.emit()

    def _refresh_senate_view(self):
        self._senate_view = self._adapter.get_senate_view(self._viewer_id)
        self.senateViewChanged.emit()

    def _refresh_revenue_view(self):
        self._revenue_view = self._adapter.get_revenue_view(self._viewer_id)
        self.revenueViewChanged.emit()

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
            "interaction_mode": phase.get("interaction_mode", "interactive" if implemented else "placeholder"),
            "actionable": phase.get("actionable", False),
            "handoff_task": phase.get("handoff_task", ""),
            "name_key": phase.get("name_key", ""),
            "subtitle_key": phase.get("subtitle_key", ""),
            "description_key": phase.get("description_key", ""),
            "status_key": phase.get("status_key", ""),
            "status_text": gui_text("phase.status.actionable") if phase.get("actionable", False) else (
                gui_text("phase.status.readonly") if phase.get("interaction_mode") == "readonly" else (
                    gui_text("phase.status.ready") if implemented else gui_text("phase.status.placeholder")
                )
            ),
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
