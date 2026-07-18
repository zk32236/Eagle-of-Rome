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
        """Population resolution via two-step contract via unified dispatch.

        Covers acceptance cases P-A01, P-A02, P-A03.
        """
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

        # P-A01/P-A02: After resolution, population NOT executed, still on population
        assert store.currentPhaseId == "population"
        assert store.canAdvancePopulation is True

        # P-A03: Advance via unified dispatch -> should route to Population advance
        assert store.canAdvanceCurrentPhase is True
        advance_feedback = store.doAdvanceCurrentPhase()
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

    # ══════════════════════════════════════════════════════════════════
    # Combat adapter tests
    # ══════════════════════════════════════════════════════════════════

    def setup_combat_state(self, adapter, state, players, with_wars=True):
        """Helper to set up a state with combat-phase wars for testing."""
        from src.core.entities.war import War, WarType, WarStatus
        from src.core.entities.figure import Figure
        from src.core.entities.entities import Faction

        # Ensure war system exists
        if not state.get_war_system():
            from src.core.systems.war_system import WarSystem
            state._war_system = WarSystem(state)
        if not state.get_military_system():
            from src.core.systems.military_system import MilitarySystem
            state._military_system = MilitarySystem(state)

        state.mark_phase_executed("mortality")
        state.mark_phase_executed("revenue")
        state.mark_phase_executed("forum")
        state.mark_phase_executed("population")
        state.mark_phase_executed("senate")
        state.set_current_player(players[0])

        if with_wars:
            # Find or create a commander
            faction = next(iter(state.factions.values()))
            viewer = state.get_player(players[0])

            commander = None
            for fig in state.get_living_members():
                if fig.faction_id == viewer.faction_id:
                    commander = fig
                    commander.martial = 5
                    break
            if not commander:
                commander = Figure(id=999, name="TestCommander", faction_id=viewer.faction_id, age=40)
                commander.martial = 5
                state.add_member(commander)

            war = War(
                id="test_adapter_war",
                name="Test Adapter War",
                war_type=WarType.FOREIGN,
                strength=6,
                threat_level=2,
                rewards={"treasury": 80},
                disaster_numbers=[2, 3],
            )
            war.commander_id = commander.id
            war.legions_assigned = 3
            war.status = WarStatus.ACTIVE
            state._war_system._active_wars.append(war)

        return adapter, state, players

    def test_get_combat_view_success(self):
        """Combat adapter returns data dict on success."""
        adapter, state, players = self.setup_adapter()
        adapter, state, players = self.setup_combat_state(adapter, state, players, with_wars=True)

        view = adapter.get_combat_view(players[0])

        assert isinstance(view, dict)
        assert view.get("phase_id") == "combat"
        assert len(view.get("active_wars", [])) > 0
        assert view.get("current_step") == "select"

    def test_get_combat_view_failure(self):
        """Combat adapter returns empty dict on API failure (None state)."""
        adapter, state, players = self.setup_adapter()
        # Corrupt state to cause failure
        adapter._state = None

        view = adapter.get_combat_view(players[0])

        assert isinstance(view, dict)
        assert view == {}

    def test_do_combat_action_success(self):
        """Combat adapter.call wrapping works for do_combat_action."""
        adapter, state, players = self.setup_adapter()
        adapter, state, players = self.setup_combat_state(adapter, state, players, with_wars=True)

        # First select the war
        from src.api import combat_api
        select_feedback = adapter.call(combat_api.select_war, state, players[0], "test_adapter_war")
        assert select_feedback["success"]

        # Then execute attack
        feedback = adapter.do_combat_action(players[0], "test_adapter_war", "attack")

        assert feedback["success"]
        data = feedback.get("data", {})
        assert "result" in data
        assert "dice" in data
        assert "total_attack" in data
        assert "enemy_defence" in data

    def test_advance_combat_success(self):
        """Combat adapter advance_combat returns success after all wars resolved."""
        adapter, state, players = self.setup_adapter()
        adapter, state, players = self.setup_combat_state(adapter, state, players, with_wars=True)

        from src.api import combat_api

        # Resolve the single war
        select_feedback = adapter.call(combat_api.select_war, state, players[0], "test_adapter_war")
        assert select_feedback["success"]

        action_feedback = adapter.call(combat_api.do_combat_action, state, players[0], "test_adapter_war", "attack")
        assert action_feedback["success"]

        confirm_feedback = adapter.call(combat_api.confirm_battle_result, state, players[0])
        assert confirm_feedback["success"]

        # Now advance
        feedback = adapter.advance_combat(players[0])
        assert feedback["success"]
        assert feedback["data"]["next_phase_id"] == "resolution"
