"""AC-12 M2-BUG4 T-10/T-11: Revenue and Forum property binding tests.

Verifies all QML-bound properties exist with correct types.
"""
import pytest

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


class TestRevenuePropertyBindings:
    """Verify revenue session_store properties exist and return correct types."""

    def test_revenue_properties_exist_and_have_correct_types(self):
        """All revenue QML-bound properties exist and return correct Python types."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Boolean properties
        assert isinstance(store.canExecuteRevenue, bool)
        assert isinstance(store.canAdvanceRevenue, bool)

        # Dict properties
        assert isinstance(store.revenueView, dict)
        assert isinstance(store.revenueSettledData, (dict, type(None)))
        assert isinstance(store.revenueResult, dict)

    def test_revenue_property_bindings_respond_to_phase(self):
        """Properties change after executing and advancing to revenue phase."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Before advancing, revenue should not be the current phase
        assert store.currentPhaseId == "mortality"

        # Advance through mortality
        store.doExecuteMortality()
        store.doAdvanceMortality()
        assert store.currentPhaseId == "revenue"

        # After advancing, canExecuteRevenue should be True
        assert store.canExecuteRevenue is True
        assert "phase_id" in store.revenueView


class TestForumPropertyBindings:
    """Verify forum session_store properties exist and return correct types."""

    def test_forum_properties_exist_and_have_correct_types(self):
        """All forum QML-bound properties exist and return correct Python types."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Boolean properties
        assert isinstance(store.canExecuteForum, bool)
        assert isinstance(store.canAdvanceForum, bool)

        # Dict properties
        assert isinstance(store.forumView, dict)
        assert isinstance(store.forumResult, dict)

    def test_forum_property_bindings_respond_to_phase(self):
        """Properties populate after navigating to forum phase."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        # Navigate through mortality→revenue→forum
        store.doExecuteMortality()
        store.doAdvanceMortality()
        store.doExecuteRevenue()
        store.doAdvanceRevenue()
        assert store.currentPhaseId == "forum"

        # Forum view should be populated
        assert "phase_id" in store.forumView
        assert store.canExecuteForum is True
