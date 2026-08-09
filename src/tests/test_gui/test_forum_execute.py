"""AC-12 M2-BUG4 T-08: Forum execute integration test.

Tests: canExecuteForum → doExecuteForum() → forumResult → refresh.
"""
import pytest

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


class TestForumExecute:
    """Verify forum execute slot lifecycle."""

    def test_forum_initial_can_execute_after_advancing_from_revenue(self):
        """After advancing from mortality→revenue→execute→advance, forum is current and executable."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Execute mortality
        mort = store.doExecuteMortality()
        assert mort["success"]
        advance_mort = store.doAdvanceMortality()
        assert advance_mort["success"]
        assert store.currentPhaseId == "revenue"

        # Execute revenue
        rev = store.doExecuteRevenue()
        assert rev["success"]
        advance_rev = store.doAdvanceRevenue()
        assert advance_rev["success"]
        assert store.currentPhaseId == "forum"

        # Forum should now be the current phase
        assert store.canExecuteForum is True
        assert isinstance(store.forumView, dict)
        assert "current_step" in store.forumView

    def test_forum_execute_changes_executable_state(self):
        """doExecuteForum stores result and changes canExecuteForum."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Navigate to forum
        store.doExecuteMortality()
        store.doAdvanceMortality()
        store.doExecuteRevenue()
        store.doAdvanceRevenue()
        assert store.currentPhaseId == "forum"

        forum_result = store.doExecuteForum()
        assert forum_result["success"]
        assert store.forumResult is not None
