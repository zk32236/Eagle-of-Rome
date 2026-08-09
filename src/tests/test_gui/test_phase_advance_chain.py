"""AC-12 M2-BUG4 T-09: Phase advance chain test.

Verifies mortality→revenue→forum→population advance chain completeness.
"""
import pytest

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


class TestPhaseAdvanceChain:
    """Verify full phase advance chain from mortality through forum to population."""

    def test_mortality_to_revenue_advance(self):
        """Execute mortality then advance → currentPhaseId='revenue'."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Step 1: Mortality execution
        feedback = store.doExecuteMortality()
        assert feedback["success"]
        assert store.currentPhaseId == "mortality"

        # Step 2: Advance to revenue
        feedback = store.doAdvanceMortality()
        assert feedback["success"]
        assert store.currentPhaseId == "revenue"
        assert store.canExecuteRevenue is True

    def test_revenue_to_forum_advance(self):
        """Execute revenue then advance → currentPhaseId='forum'."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Navigate through mortality
        store.doExecuteMortality()
        store.doAdvanceMortality()
        assert store.currentPhaseId == "revenue"

        # Execute and advance revenue
        store.doExecuteRevenue()
        feedback = store.doAdvanceRevenue()
        assert feedback["success"]
        assert store.currentPhaseId == "forum"
        assert store.canExecuteForum is True

    def test_forum_to_population_advance(self):
        """Execute forum then advance → currentPhaseId='population'."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Navigate through mortality→revenue
        store.doExecuteMortality()
        store.doAdvanceMortality()
        store.doExecuteRevenue()
        store.doAdvanceRevenue()
        assert store.currentPhaseId == "forum"

        # Execute and advance forum
        store.doExecuteForum()
        feedback = store.doAdvanceForum()
        assert feedback["success"]
        assert store.currentPhaseId == "population"

    def test_full_chain_to_population(self):
        """Traverse the full chain from mortality through forum to population."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Full chain
        assert store.doExecuteMortality()["success"]
        assert store.doAdvanceMortality()["success"]
        assert store.currentPhaseId == "revenue"

        assert store.doExecuteRevenue()["success"]
        assert store.doAdvanceRevenue()["success"]
        assert store.currentPhaseId == "forum"

        assert store.doExecuteForum()["success"]
        assert store.doAdvanceForum()["success"]
        assert store.currentPhaseId == "population"

    def test_can_advance_current_phase_works_in_chain(self):
        """canAdvanceCurrentPhase and doAdvanceCurrentPhase work at each step."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Mortality: execute then advance via dispatch
        store.doExecuteMortality()
        assert store.canAdvanceCurrentPhase is True
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "revenue"

        # Revenue: execute then advance via dispatch
        store.doExecuteRevenue()
        assert store.canAdvanceCurrentPhase is True
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "forum"

        # Forum: execute then advance via dispatch
        store.doExecuteForum()
        assert store.canAdvanceCurrentPhase is True
        assert store.doAdvanceCurrentPhase()["success"]
        assert store.currentPhaseId == "population"
