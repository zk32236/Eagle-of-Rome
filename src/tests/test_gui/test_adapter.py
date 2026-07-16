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

    def setup_adapter(self, start_phase="population"):
        result = session_api.create_gui_prototype_session(start_phase=start_phase)
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

    def test_session_store_selects_senate_phase_without_business_execution(self):
        result = session_api.create_gui_prototype_session()
        assert result["success"]
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])
        proposals_before = list(state.get_senate_proposals())

        messages = []
        store.feedbackRaised.connect(lambda ftype, message: messages.append((ftype, message)))
        feedback = store.selectPhase("senate")

        assert feedback["success"]
        assert store.selectedPhaseId == "senate"
        assert store.selectedPhaseSummary["implemented"] is True
        assert store.selectedPhaseSummary["interaction_mode"] == "interactive"
        assert store.selectedPhaseSummary["handoff_task"] == "GUI-P0-02C"
        assert store.senateView["interaction_mode"] == "readonly"
        assert store.senateView["current_step"] == "proposal"
        assert "proposal_options" in store.senateView
        assert "submitted_proposals" in store.senateView
        assert store.senateView["can_resolve"] is False
        assert state.get_senate_proposals() == proposals_before
        assert state.is_phase_executed("senate") is False
        assert messages[-1][0] == "info"

    def test_session_store_can_return_to_population_after_placeholder_phase(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        store.selectPhase("combat")
        feedback = store.selectPhase("population")

        assert feedback["success"]
        assert store.selectedPhaseId == "population"
        assert store.selectedPhaseSummary["implemented"] is True
        assert isinstance(store.myFigures, list)

    def test_adapter_executes_mortality_and_keeps_current_phase_until_advance(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        adapter = GuiApiAdapter(state)

        feedback = adapter.execute_mortality(player_id)

        assert feedback["success"]
        assert feedback["data"]["phase_executed"] is False
        assert feedback["data"]["next_phase_id"] == "revenue"
        snapshot = adapter.get_snapshot(player_id)
        assert snapshot["current_phase_id"] == "mortality"
        assert snapshot["current_phase_id"] != "population"

    def test_session_store_executes_mortality_and_keeps_result_visible(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        assert store.selectedPhaseId == "mortality"
        assert store.canExecuteMortality is True
        feedback = store.doExecuteMortality()

        assert feedback["success"]
        assert store.currentPhaseId == "mortality"
        assert store.currentPhaseId != "population"
        assert store.selectedPhaseId == "mortality"
        assert store.canExecuteMortality is False
        assert store.canAdvanceMortality is True
        assert len(store.mortalityEvents) >= 1

        advance = store.doAdvanceMortality()

        assert advance["success"]
        assert store.currentPhaseId == "revenue"
        assert store.selectedPhaseId == "revenue"
        assert store.selectedPhaseSummary["implemented"] is True
        assert store.selectedPhaseSummary["handoff_task"] == "GUI-P0-03"
        assert store.canAdvanceMortality is False

    def test_adapter_get_senate_view_exposes_phase5a_dto(self):
        adapter, state, players = self.setup_adapter(start_phase="senate")
        state.set_current_player(players[0])

        view = adapter.get_senate_view(players[0])

        assert view["phase_id"] == "senate"
        assert view["interaction_mode"] == "interactive"
        assert view["current_step"] == "proposal"
        assert view["actionable"] is True
        assert "proposal_options" in view
        assert "submitted_proposals" in view
        assert view["can_resolve"] is False
        assert "faction_leaders" in view

    def test_session_store_submits_senate_proposals_and_moves_to_vote_step(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        viewer = state.get_player(player_id)
        consul = next(fig for fig in state.get_living_members() if fig.faction_id == viewer.faction_id)
        consul.office = "consul"
        store = GuiSessionStore(state)
        store.initialize(player_id)
        option = {"type": "land", "params": {"act_type": "sale", "percent": 0.1}}

        feedback = store.doSubmitSenateProposals([option])

        assert feedback["success"]
        assert len(state.get_senate_proposals()) == 1
        assert store.senateCurrentStep == "senate_vote"
        assert len(store.senateSubmittedProposals) == 1

    def test_session_store_submits_senate_votes_and_moves_to_veto_step(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        viewer = state.get_player(player_id)
        consul = next(fig for fig in state.get_living_members() if fig.faction_id == viewer.faction_id)
        consul.office = "consul"
        store = GuiSessionStore(state)
        store.initialize(player_id)
        store.doSubmitSenateProposals([{"type": "land", "params": {"act_type": "sale", "percent": 0.1}}])

        submitted_before_vote = list(store.senateSubmittedProposals)

        feedback = store.doSubmitSenateVotes()

        assert feedback["success"]
        assert store.senateCurrentStep == "tribune_veto"
        assert store.senateSubmittedProposals == submitted_before_vote
        assert len(store.senateSubmittedProposals) == 1

    def test_session_store_submits_senate_veto_confirmation_and_records_result(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        viewer = state.get_player(player_id)
        consul = next(fig for fig in state.get_living_members() if fig.faction_id == viewer.faction_id)
        consul.office = "consul"
        tribune = next(fig for fig in state.get_living_members() if fig.faction_id == viewer.faction_id and fig is not consul)
        tribune.office = "tribune"
        store = GuiSessionStore(state)
        store.initialize(player_id)
        store.doSubmitSenateProposals([{"type": "land", "params": {"act_type": "sale", "percent": 0.1}}])
        store.doSubmitSenateVotes()

        feedback = store.doSubmitSenateVetoes([])

        assert feedback["success"]
        result_data = state.get_phase_result("senate")
        assert result_data is not None
        assert (
            result_data["data"]["passed_proposals_snapshot"]
            or result_data["data"]["rejected_proposals_snapshot"]
        )
        assert store.senateCurrentStep == "results"
        assert store.senateSubmittedProposals

        advance = store.doAdvanceSenate()

        assert advance["success"]
        assert store.currentPhaseId == "combat"
        assert store.selectedPhaseId == "combat"

    def test_session_store_auto_resolves_tribune_veto_when_viewer_has_no_tribune(self):
        result = session_api.create_gui_prototype_session(start_phase="senate")
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        viewer = state.get_player(player_id)
        consul = next(fig for fig in state.get_living_members() if fig.faction_id == viewer.faction_id)
        consul.office = "consul"
        other = next(p for p in state.get_all_players() if p.player_id != player_id)
        other_member = next(fig for fig in state.get_living_members() if fig.faction_id == other.faction_id)
        other_member.office = "tribune"
        store = GuiSessionStore(state)
        store.initialize(player_id)
        store.doSubmitSenateProposals([{"type": "land", "params": {"act_type": "sale", "percent": 0.1}}])
        store.doSubmitSenateVotes()

        assert store.senateCurrentStep == "tribune_veto"
        assert store.canSubmitSenateVeto is True
        assert store.canManuallySelectSenateVeto is False
        feedback = store.doSubmitSenateVetoes([])

        assert feedback["success"]
        result_data = state.get_phase_result("senate")
        assert result_data is not None
        assert store.senateCurrentStep == "results"

    def test_adapter_get_forum_view_exposes_interactive_dto(self):
        adapter, state, players = self.setup_adapter(start_phase="forum")
        state.set_current_player(players[0])

        view = adapter.get_forum_view(players[0])

        assert view["phase_id"] == "forum"
        assert view["current_phase_id"] == "forum"
        assert view["can_execute"] is True
        assert isinstance(view["my_figures"], list)
        assert isinstance(view["available_figures"], list)
        assert isinstance(view["pending_contracts"], list)

    def test_session_store_forum_step_and_resolution_flow(self):
        result = session_api.create_gui_prototype_session(start_phase="forum")
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        assert store.selectedPhaseId == "forum"
        assert store.forumCurrentStep == "retirement"
        step_feedback = store.doCompleteForumStep()
        assert step_feedback["success"]
        assert store.forumCurrentStep == "market"
        assert len(store.forumAvailableFigures) >= 3

        resolve_feedback = store.doResolveForum()
        assert resolve_feedback["success"]
        assert store.forumResolved is True
        assert store.canAdvanceForum is True

        advance_feedback = store.doAdvanceForum()
        assert advance_feedback["success"]
        assert store.currentPhaseId == "population"

    def test_session_store_forum_market_includes_retired_and_new_figures(self):
        result = session_api.create_gui_prototype_session(start_phase="forum")
        state = result["data"]["state"]
        player_id = result["data"]["human_players"][0]
        store = GuiSessionStore(state)
        store.initialize(player_id)
        retiree = next(row for row in store.forumMyFigures if not row.get("is_leader"))

        retire_feedback = store.doRetireFigure(retiree["id"])
        assert retire_feedback["success"]
        before_market_ids = {row["id"] for row in store.forumAvailableFigures}
        assert retiree["id"] in before_market_ids

        step_feedback = store.doCompleteForumStep()

        assert step_feedback["success"]
        after_market_ids = {row["id"] for row in store.forumAvailableFigures}
        assert retiree["id"] in after_market_ids
        assert len(after_market_ids - before_market_ids) == 3

    def test_session_store_population_resolution_keeps_results_visible(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        assert store.selectedPhaseId == "population"
        assert store.populationCurrentStep in {"campaign", "vote"}
        feedback = store.doResolveElection()

        assert feedback["success"]
        assert store.populationResolved is True
        assert store.populationCurrentStep == "results"
        assert store.selectedPhaseId == "population"
        assert isinstance(store.populationElectionResults, list)
        assert store.canAdvancePopulation is True

        advance_feedback = store.doAdvancePopulation()
        assert advance_feedback["success"]
        assert store.currentPhaseId == "senate"
        assert store.selectedPhaseId == "senate"

    def test_opc_global_queries_are_readonly_or_placeholder(self):
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])
        executed_before = {phase["id"]: state.is_phase_executed(phase["id"]) for phase in store.phaseNavigation}

        game_status = store.doGlobalQuery("game_status")
        assert game_status["success"]
        assert store.globalQueryResult["id"] == "game_status"
        assert store.globalQueryResult["status"] == "connected"
        assert any(item["label"] for item in store.globalQueryResult["items"])

        faction_info = store.doGlobalQuery("faction_info")
        assert faction_info["success"]
        assert store.globalQueryResult["status"] == "readonly"
        assert store.globalQueryResult["items"][0]["value"] == store.viewerFactionName

        war_list = store.doGlobalQuery("war_list")
        assert war_list["success"]
        assert store.globalQueryResult["status"] == "readonly"

        legion_status = store.doGlobalQuery("legion_status")
        assert legion_status["success"]
        assert store.globalQueryResult["status"] == "readonly"
        assert "counts" in store.globalQueryResult["summary"]

        executed_after = {phase["id"]: state.is_phase_executed(phase["id"]) for phase in store.phaseNavigation}
        assert executed_after == executed_before

    def test_adapter_global_query_delegates_to_gui_query_api(self):
        adapter, state, players = self.setup_adapter()

        result = adapter.get_global_query_result(players[0], "game_status")

        assert result["id"] == "game_status"
        assert result["title_key"] == "query.game_status.title"
        assert result["status"] == "connected"
        assert "items" in result
