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
from src.ui.processors.auto_player_processor import AutoPlayerProcessor
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider

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
    forumViewChanged = Signal()
    combatViewChanged = Signal()
    resolutionViewChanged = Signal()
    resolutionAdvancingChanged = Signal()
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
        self._forum_view: Dict[str, Any] = {}
        self._forum_result: Dict[str, Any] = {}
        self._forum_step_override: str = ""
        self._combat_view: Dict[str, Any] = {}
        self._combat_result: Dict[str, Any] = {}
        self._resolution_view: Dict[str, Any] = {}
        self._resolution_resolving: bool = False
        self._resolution_advancing: bool = False
        self._revenue_result: Dict[str, Any] = {}
        self._mortality_result: Dict[str, Any] = {}
        self._current_player_id: str = ""
        self._viewer_id: str = ""
        self._selected_phase_id: str = ""
        self._selected_phase_summary: Dict[str, Any] = {}
        self._global_query_result: Dict[str, Any] = {}
        self._feedback_queue: List[Dict[str, str]] = []
        self._forum_ai_processed = False

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
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()

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

    @Property(int, notify=snapshotChanged)
    def currentPhaseIndex(self) -> int:
        nav = self.phaseNavigation
        for i, phase in enumerate(nav):
            if phase.get("id") == self.currentPhaseId:
                return i
        return 0

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
    def populationView(self) -> Dict[str, Any]:
        return self._population_view

    @Property(list, notify=populationViewChanged)
    def populationCampaigns(self) -> List[Dict[str, Any]]:
        return self._population_view.get("my_campaigns", [])

    @Property(str, notify=populationViewChanged)
    def populationCurrentStep(self) -> str:
        return self._population_view.get("current_step", "campaign")

    @Property(bool, notify=populationViewChanged)
    def populationResolved(self) -> bool:
        return self._population_view.get("resolved", False)

    @Property(list, notify=populationViewChanged)
    def populationElectionResults(self) -> List[Dict[str, Any]]:
        return self._population_view.get("election_results", [])

    @Property(list, notify=populationViewChanged)
    def populationInfluenceBefore(self) -> List[Dict[str, Any]]:
        return self._population_view.get("faction_influence_before", [])

    @Property(list, notify=populationViewChanged)
    def populationInfluenceAfter(self) -> List[Dict[str, Any]]:
        return self._population_view.get("faction_influence_after", [])

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

    @Property(bool, notify=populationViewChanged)
    def canAdvancePopulation(self) -> bool:
        return self._population_view.get("can_advance", False)

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

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self) -> str:
        return self._senate_view.get("current_step", "proposal")

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("proposal_options", [])

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("submitted_proposals", [])

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("seat_shares", [])

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self) -> bool:
        return self._senate_view.get("can_create_proposal", False)

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self) -> bool:
        return self._senate_view.get("can_vote", False)

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self) -> bool:
        return self._senate_view.get("can_veto", False) or self._senate_view.get("can_auto_veto", False)

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self) -> bool:
        return self._senate_view.get("can_veto", False)

    @Property(bool, notify=senateViewChanged)
    def canAdvanceSenate(self) -> bool:
        return self._senate_view.get("can_advance", False)

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

    @Property(dict, notify=forumViewChanged)
    def forumView(self) -> Dict[str, Any]:
        return self._forum_view

    @Property(dict, notify=forumViewChanged)
    def forumResult(self) -> Dict[str, Any]:
        return self._forum_result or self._forum_view.get("result", {})

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self) -> str:
        if self._forum_step_override:
            return self._forum_step_override
        return self._forum_view.get("current_step", "retirement")

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("my_figures", [])

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("available_figures", [])

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("pending_contracts", [])

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self) -> int:
        return self._forum_view.get("land_sale_quota", 0)

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("triumph_wars", [])

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self) -> bool:
        return self._forum_view.get("can_execute", False)

    @Property(bool, notify=forumViewChanged)
    def canAdvanceForum(self) -> bool:
        return self._forum_view.get("can_advance", False)

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self) -> bool:
        return self._forum_view.get("resolved", False) or bool(self._forum_result)

    # -----------------------------------------------------------------------
    # Combat stage properties
    # -----------------------------------------------------------------------
    @Property(dict, notify=combatViewChanged)
    def combatView(self) -> Dict[str, Any]:
        return self._combat_view

    @Property(list, notify=combatViewChanged)
    def combatActiveWars(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("active_wars", [])

    @Property(list, notify=combatViewChanged)
    def combatBattleResults(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("battle_results", [])

    @Property(str, notify=combatViewChanged)
    def combatCurrentStep(self) -> str:
        return self._combat_view.get("current_step", "select")

    @Property(bool, notify=combatViewChanged)
    def canAdvanceCombat(self) -> bool:
        return self._combat_view.get("can_advance", False)

    @Property(bool, notify=combatViewChanged)
    def allCombatResolved(self) -> bool:
        return self._combat_view.get("all_resolved", False)

    @Property(str, notify=combatViewChanged)
    def combatSelectedWarId(self) -> str:
        return self._combat_view.get("selected_war_id", "")

    @Property(bool, notify=combatViewChanged)
    def hasActiveWars(self) -> bool:
        wars = self._combat_view.get("active_wars", [])
        return len(wars) > 0

    @Property(list, notify=combatViewChanged)
    def combatResolvedWarCards(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("resolved_war_cards", [])

    @Property(list, notify=combatViewChanged)
    def combatResolvedWarIds(self) -> List[str]:
        return self._combat_view.get("resolved_war_ids", [])

    @Property(list, notify=combatViewChanged)
    def combatAllWarCards(self) -> List[Dict[str, Any]]:
        """Combined list of active + resolved war cards for QML Repeater."""
        active = self._combat_view.get("active_wars", [])
        resolved = self._combat_view.get("resolved_war_cards", [])
        return active + resolved

    @Property(dict, notify=combatViewChanged)
    def combatResult(self) -> Dict[str, Any]:
        return self._combat_result

    @Property(dict, notify=combatViewChanged)
    def combatBattleResultDetail(self) -> Dict[str, Any]:
        results = self._combat_view.get("battle_results", [])
        return results[0] if results else {}

    @Property(int, notify=combatViewChanged)
    def combatFleetCount(self) -> int:
        return self._combat_view.get("fleet_count", 0)

    @Property(int, notify=combatViewChanged)
    def combatAvailableLegions(self) -> int:
        return self._combat_view.get("available_legion_count", 0)

    @Property(dict, notify=queryResultChanged)
    def globalQueryResult(self) -> Dict[str, Any]:
        return self._global_query_result

    # -----------------------------------------------------------------------
    # Resolution stage properties
    # -----------------------------------------------------------------------
    @Property(dict, notify=resolutionViewChanged)
    def resolutionView(self) -> Dict[str, Any]:
        return self._resolution_view

    @Property(list, notify=resolutionViewChanged)
    def resolutionStepStatuses(self) -> list:
        return self._resolution_view.get("step_statuses", [])

    @Property(dict, notify=resolutionViewChanged)
    def resolutionResults(self) -> dict:
        return self._resolution_view.get("results", {})

    @Property(list, notify=resolutionViewChanged)
    def resolutionWarnings(self) -> list:
        return self._resolution_view.get("warnings", [])

    @Property(dict, notify=resolutionViewChanged)
    def resolutionSummary(self) -> dict:
        return self._resolution_view.get("summary", {})

    @Property(bool, notify=resolutionViewChanged)
    def resolutionResolved(self) -> bool:
        return self._resolution_view.get("resolved", False)

    @Property(bool, notify=resolutionViewChanged)
    def isResolutionResolving(self) -> bool:
        return self._resolution_resolving

    @Property(bool, notify=resolutionViewChanged)
    def canAdvanceResolution(self) -> bool:
        """是否可以推进下一年度（结算完成 + 当前玩家 + 非推进中 + 非分派中）"""
        if not self._resolution_view:
            return False
        resolved = self._resolution_view.get("resolved", False)
        is_current = self._resolution_view.get("is_current_player", False)
        return resolved and is_current and not self._resolution_resolving and not self._resolution_advancing

    @Property(bool, notify=resolutionAdvancingChanged)
    def isResolutionAdvancing(self) -> bool:
        """是否正在执行 advance_year（loading 状态）"""
        return self._resolution_advancing

    # -----------------------------------------------------------------------
    # 阶段推进统一分派
    # -----------------------------------------------------------------------
    _PHASE_ADVANCE_DISPATCH = {
        "mortality": {
            "can_attr": "canAdvanceMortality",
            "slot": "doAdvanceMortality",
            "label": "\u23ed\ufe0f 推进到收入阶段",
        },
        "revenue": {
            "can_attr": "canAdvanceRevenue",
            "slot": "doAdvanceRevenue",
            "label": "\u23ed\ufe0f 推进到广场",
        },
        "forum": {
            "can_attr": "canAdvanceForum",
            "slot": "doAdvanceForum",
            "label": "\u23ed\ufe0f 推进到人口阶段",
        },
        "population": {
            "can_attr": "canAdvancePopulation",
            "slot": "doAdvancePopulation",
            "label": "\u23ed\ufe0f 进入元老院阶段",
        },
        "senate": {
            "can_attr": "canAdvanceSenate",
            "slot": "doAdvanceSenate",
            "label": "\u23ed\ufe0f 推进到战斗阶段",
        },
        "combat": {
            "can_attr": "canAdvanceCombat",
            "slot": "doAdvanceCombat",
            "label": "\u23ed\ufe0f 推进到决断阶段",
        },
        "resolution": {
            "can_attr": "canAdvanceResolution",
            "slot": "doAdvanceResolution",
            "label": "\u23ed\ufe0f 推进到下一回合",
        },
    }

    @Property(bool, notify=phaseChanged)
    def canAdvanceCurrentPhase(self) -> bool:
        dispatch = self._PHASE_ADVANCE_DISPATCH.get(self.currentPhaseId)
        if not dispatch:
            return False
        return getattr(self, dispatch["can_attr"], False)

    @Property(str, notify=phaseChanged)
    def advanceCurrentPhaseText(self) -> str:
        dispatch = self._PHASE_ADVANCE_DISPATCH.get(self.currentPhaseId)
        if not dispatch:
            return "\u23ed\ufe0f 推进到下一阶段"
        return dispatch["label"]

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
        if feedback.get("success"):
            self._selected_phase_id = "population"
            self._selected_phase_summary = self._summary_from_phase(
                self._phase_by_id("population")
            )
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self.phaseChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvancePopulation(self) -> dict:
        """确认人口阶段结果并切换到元老院阶段视图。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self.canAdvancePopulation:
            feedback = self._feedback(False, "人口阶段尚未完成，无法推进", "error")
            self._raise_feedback(feedback)
            return feedback

        # Call adapter -> session_api.advance_population_phase()
        feedback = self._adapter.advance_population(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._selected_phase_id = "senate"
            self._selected_phase_summary = self._summary_from_phase(self._phase_by_id("senate"))
            self._refresh_senate_view()
            self.phaseChanged.emit()
        self._raise_feedback(feedback)
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
            self._refresh_forum_view()
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
            self._refresh_forum_view()
        self._raise_feedback(feedback)
        self.revenueViewChanged.emit()
        return feedback

    @Slot(int, result=dict)
    def doRetireFigure(self, figure_id: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.retire_figure(self._viewer_id, figure_id)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, result=dict)
    def doRecruitFigure(self, figure_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.recruit_figure(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, int, result=dict)
    def doPlaceBid(self, figure_id: int, contract_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.place_bid(self._viewer_id, figure_id, contract_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, result=dict)
    def doBuyLand(self, figure_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.buy_land(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(str, bool, result=dict)
    def doVoteTriumph(self, war_id: str, vote: bool) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.vote_triumph(self._viewer_id, war_id, vote)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(result=dict)
    def doCompleteForumStep(self) -> dict:
        if self.forumCurrentStep == "retirement":
            feedback = self._adapter.open_forum_market(self._viewer_id)
            if feedback.get("success"):
                self._forum_step_override = "market"
                self._process_ai_factions_forum()
            self._refresh_forum_view()
            self._raise_feedback(feedback)
            return feedback
        return self.doResolveForum()

    @Slot(result=dict)
    def doResolveForum(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}

        # Safety net: process AI forum actions if not already done
        # (covers the case where doCompleteForumStep was bypassed)
        self._process_ai_factions_forum()

        feedback = self._adapter.resolve_forum()
        if feedback.get("success"):
            self._forum_result = feedback
            self._forum_step_override = "resolution"
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_forum_view()
        return feedback

    # -----------------------------------------------------------------------
    # AI Forum Processing
    # -----------------------------------------------------------------------
    def _process_ai_factions_forum(self) -> None:
        """
        Execute forum actions for all non-human (AI) factions.
        Called after the human completes retirement step, before market
        transition. Also called as a safety net in doResolveForum().
        Double-processing is prevented by a guard flag.
        """
        if getattr(self, '_forum_ai_processed', False):
            logger.debug("AI forum already processed, skipping")
            return

        all_players = self._state.get_all_players()
        ai_players = [p for p in all_players if p.player_id != self._viewer_id]
        if not ai_players:
            logger.info("No AI players to process for forum")
            self._forum_ai_processed = True
            return

        # Instantiate deciders and processor
        processor = AutoPlayerProcessor(
            self._state,
            retirement_decider=AutoRetirementDecider(self._state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider(),
        )

        # Bypass player permission checks for AI operations
        saved_bypass = self._state.config.get("testing.bypass_player_check", False)
        self._state.config.testing.bypass_player_check = True

        try:
            for ai_player in ai_players:
                ai_faction = self._state.get_faction(ai_player.faction_id)
                if not ai_faction:
                    logger.warning(
                        "AI player has no faction, skipping forum processing",
                        extra={"player_id": ai_player.player_id},
                    )
                    continue

                logger.info(
                    "Processing AI forum actions",
                    extra={
                        "player_id": ai_player.player_id,
                        "faction_id": ai_faction.id,
                        "faction_name": ai_faction.name,
                    },
                )

                try:
                    # Step 1: Open market (generate new figures) — idempotent
                    open_result = self._adapter.open_forum_market(ai_player.player_id)
                    if not open_result.get("success"):
                        logger.warning(
                            f"AI market open failed for {ai_faction.name}: "
                            f"{open_result.get('message')}"
                        )

                    # Step 2: Retirement
                    processor.process_retirement(ai_player.player_id, ai_faction)

                    # Step 3: Market decisions (recruit, bid, land, triumph)
                    processor.process_market(ai_player.player_id, ai_faction)

                    logger.info(
                        f"AI forum actions completed for {ai_faction.name}",
                        extra={
                            "player_id": ai_player.player_id,
                            "faction_id": ai_faction.id,
                        },
                    )
                except Exception as e:
                    logger.exception(
                        f"AI forum processing failed for faction {ai_faction.name}: {e}"
                    )
                    # Continue processing other AI factions

        except Exception as e:
            logger.exception(f"Unexpected error in AI forum processing: {e}")
        finally:
            self._state.config.testing.bypass_player_check = saved_bypass
            self._forum_ai_processed = True
            logger.info("AI forum processing completed")

    # -----------------------------------------------------------------------
    # Forum stage Slot — Advance
    # -----------------------------------------------------------------------
    @Slot(result=dict)
    def doAdvanceForum(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_forum(self._viewer_id)
        if feedback.get("success"):
            self._forum_step_override = ""
            self._refresh_snapshot()
            self._refresh_forum_view()
            self._refresh_population_view()
        self._raise_feedback(feedback)
        self.forumViewChanged.emit()
        return feedback

    # -----------------------------------------------------------------------
    # Combat stage Slot
    # -----------------------------------------------------------------------
    @Slot(str, result=dict)
    def doSelectWar(self, war_id: str) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        from src.api import combat_api
        feedback = self._adapter.call(combat_api.select_war, self._state, self._viewer_id, war_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(str, str, result=dict)
    def doCombatAction(self, war_id: str, action: str) -> dict:
        """Execute a combat action: 'scout', 'defence', 'attack'."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.do_combat_action(self._viewer_id, war_id, action)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._combat_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doConfirmBattleResult(self) -> dict:
        """Acknowledge battle result, return to SELECT or go to ADVANCE."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.confirm_battle_result(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceCombat(self) -> dict:
        """Advance to Resolution phase."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self.canAdvanceCombat:
            feedback = self._feedback(False, "尚有未结算的战争", "error")
            self._raise_feedback(feedback)
            return feedback
        feedback = self._adapter.advance_combat(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._selected_phase_id = "resolution"
            self._selected_phase_summary = self._summary_from_phase(
                self._phase_by_id("resolution")
            )
            self.phaseChanged.emit()
        self.combatViewChanged.emit()
        return feedback

    # -----------------------------------------------------------------------
    # Resolution stage Slot
    # -----------------------------------------------------------------------
    @Slot(result=dict)
    def doAdvanceResolution(self) -> dict:
        """推进到下一年度（决算完成确认，返回天命阶段）。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if self._resolution_advancing:
            feedback = self._feedback(False, "正在推进中，请稍候", "warning")
            self._raise_feedback(feedback)
            return feedback
        if not self.canAdvanceResolution:
            feedback = self._feedback(False, "决算尚未完成，无法推进", "error")
            self._raise_feedback(feedback)
            return feedback

        self._resolution_advancing = True
        self.resolutionAdvancingChanged.emit()
        self.resolutionViewChanged.emit()

        try:
            feedback = self._adapter.advance_year(self._viewer_id)
            if feedback.get("success"):
                self._refresh_snapshot()
                self._selected_phase_id = "mortality"
                self._selected_phase_summary = self._summary_from_phase(
                    self._phase_by_id("mortality")
                )
                self.phaseChanged.emit()
            else:
                # 失败：停留在 Phase 7，保留结算结果
                logger.warning(f"Year advance failed: {feedback.get('message')}")
                self._refresh_resolution_view()
            self._raise_feedback(feedback)
            return feedback
        finally:
            self._resolution_advancing = False
            self.resolutionAdvancingChanged.emit()
            self.resolutionViewChanged.emit()

    @Slot(result=dict)
    def doAdvanceCurrentPhase(self) -> dict:
        """Unified dispatch: advance button based on currentPhaseId."""
        phase_id = self.currentPhaseId
        if phase_id == "mortality":
            return self.doAdvanceMortality()
        elif phase_id == "revenue":
            return self.doAdvanceRevenue()
        elif phase_id == "forum":
            return self.doAdvanceForum()
        elif phase_id == "population":
            return self.doAdvancePopulation()
        elif phase_id == "senate":
            return self.doAdvanceSenate()
        elif phase_id == "combat":
            return self.doAdvanceCombat()
        elif phase_id == "resolution":
            return self.doAdvanceResolution()
        else:
            return {"success": False, "message": f"\u672a\u77e5\u9636\u6bb5: {phase_id}", "errors": [f"unknown phase: {phase_id}"]}

    def _variant_to_python(self, value):
        if hasattr(value, "toVariant"):
            return value.toVariant()
        if hasattr(value, "toPython"):
            return value.toPython()
        return value

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        payload = self._variant_to_python(proposals)
        selected = []
        for item in payload or []:
            item = self._variant_to_python(item)
            if isinstance(item, dict):
                selected.append(item)
        feedback = self._adapter.submit_senate_proposals(self._viewer_id, selected)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doSubmitSenateVotes(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        proposals = self._senate_view.get("submitted_proposals", []) or []
        proposal_ids = [int(item.get("id")) for item in proposals if item.get("id") is not None]
        if not proposal_ids:
            feedback = self._feedback(False, "没有可表决的法案", "error")
            self._raise_feedback(feedback)
            return feedback
        votes = [True for _ in proposal_ids]
        feedback = self._adapter.submit_senate_votes(self._viewer_id, proposal_ids, votes)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        payload = self._variant_to_python(proposal_ids)
        veto_ids = []
        for item in payload or []:
            item = self._variant_to_python(item)
            try:
                veto_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        if self._senate_view.get("can_auto_veto", False):
            auto_feedback = self._adapter.apply_auto_senate_vetoes()
            self._raise_feedback(auto_feedback)
            if not auto_feedback.get("success"):
                self._refresh_senate_view()
                self.senateViewChanged.emit()
                return auto_feedback
        elif veto_ids:
            veto_feedback = self._adapter.submit_senate_vetoes(self._viewer_id, veto_ids)
            self._raise_feedback(veto_feedback)
            if not veto_feedback.get("success"):
                self._refresh_senate_view()
                self.senateViewChanged.emit()
                return veto_feedback

        feedback = self._adapter.resolve_senate()
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceSenate(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self.canAdvanceSenate:
            feedback = self._feedback(False, "Senate result is not ready", "error")
            self._raise_feedback(feedback)
            return feedback
        feedback = self._adapter.advance_senate(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
            self._selected_phase_id = "combat"
            self._selected_phase_summary = self._summary_from_phase(self._phase_by_id("combat"))
            self.phaseChanged.emit()

            # Auto-resolve combat for AI players
            if self.currentPlayerId != self._viewer_id:
                self._adapter.auto_resolve_combat(self._viewer_id)
            # Refresh combat view for all players entering combat phase
            self._refresh_combat_view()
        self.senateViewChanged.emit()
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
        elif phase_id == "forum":
            self._refresh_forum_view()
        elif phase_id == "combat":
            self._refresh_combat_view()
        elif phase_id == "resolution":
            self._refresh_resolution_view()
            # 自动结算触发：首次进入且尚未结算
            if not self._resolution_view.get("resolved", False) and not self._resolution_resolving:
                self._executeResolution()
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
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()
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
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()
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
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()
        # Auto-settlement trigger: resolution phase, not yet resolved, not currently resolving
        if (self._selected_phase_id == "resolution"
                and not self._resolution_view.get("resolved", False)
                and not self._resolution_resolving):
            self._executeResolution()

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

    def _refresh_forum_view(self):
        self._forum_view = self._adapter.get_forum_view(self._viewer_id)
        if self._forum_step_override and self._forum_view.get("resolved"):
            self._forum_step_override = "resolution"
        self.forumViewChanged.emit()

    def _refresh_combat_view(self):
        self._combat_view = self._adapter.get_combat_view(self._viewer_id)
        self.combatViewChanged.emit()

    def _refresh_resolution_view(self):
        self._resolution_view = self._adapter.get_resolution_view(self._viewer_id)
        self.resolutionViewChanged.emit()

    def _executeResolution(self):
        """自动结算：进入 resolution 阶段时触发，防重复。"""
        if self._resolution_resolving:
            logger.info("Resolution already resolving, skipping")
            return
        if not self._viewer_id:
            logger.warning("Cannot execute resolution: no viewer_id")
            return

        self._resolution_resolving = True
        self.resolutionViewChanged.emit()
        self.phaseChanged.emit()  # 同步通知 advance 按钮绑定
        try:
            feedback = self._adapter.execute_phase("resolution", self._viewer_id)
            if feedback.get("success"):
                # 结算成功：刷新快照和 resolution view
                self._refresh_snapshot()
                self._refresh_resolution_view()
                self.phaseChanged.emit()
            else:
                logger.warning(f"Resolution execution failed: {feedback.get('message')}")
                self._refresh_resolution_view()
            self._raise_feedback(feedback)
        finally:
            self._resolution_resolving = False
            self.resolutionViewChanged.emit()
            self.phaseChanged.emit()  # 同步通知 advance 按钮绑定

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
