"""AC-12 M2-BUG4 T-12/T-13: Revenue and Forum dispatch entry tests.

Verifies _PHASE_ADVANCE_DISPATCH contains revenue and forum entries with valid references.
"""
import pytest

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


class TestPhaseAdvanceDispatch:
    """Verify dispatch table completeness for all implemented phases."""

    def test_dispatch_contains_revenue_entry(self):
        """_PHASE_ADVANCE_DISPATCH has a 'revenue' key with can_attr and slot."""
        store = GuiSessionStore.__new__(GuiSessionStore)
        dispatch = GuiSessionStore._PHASE_ADVANCE_DISPATCH
        assert "revenue" in dispatch
        entry = dispatch["revenue"]
        assert "can_attr" in entry
        assert "slot" in entry
        assert "label" in entry
        assert entry["can_attr"] == "canAdvanceRevenue"
        assert entry["slot"] == "doAdvanceRevenue"

    def test_dispatch_contains_forum_entry(self):
        """_PHASE_ADVANCE_DISPATCH has a 'forum' key with can_attr and slot."""
        dispatch = GuiSessionStore._PHASE_ADVANCE_DISPATCH
        assert "forum" in dispatch
        entry = dispatch["forum"]
        assert "can_attr" in entry
        assert "slot" in entry
        assert "label" in entry
        assert entry["can_attr"] == "canAdvanceForum"
        assert entry["slot"] == "doAdvanceForum"

    def test_dispatch_entries_are_accessible_as_attributes(self):
        """Each dispatch entry's can_attr and slot are real GuiSessionStore attributes."""
        result = session_api.create_gui_prototype_session()
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)

        store = GuiSessionStore(state)
        store.initialize(viewer_id)

        for phase_id, entry in GuiSessionStore._PHASE_ADVANCE_DISPATCH.items():
            assert hasattr(store, entry["can_attr"]), f"Missing can_attr {entry['can_attr']} for {phase_id}"
            assert hasattr(store, entry["slot"]), f"Missing slot {entry['slot']} for {phase_id}"
