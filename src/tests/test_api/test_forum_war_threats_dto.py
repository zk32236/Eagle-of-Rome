"""
src/tests/test_api/test_forum_war_threats_dto.py

016 war_threats DTO tests (GUI-BETA-R1 WP-C).

Covers AU-3: get_forum_view exposes war_threats with the same war identity as
the Senate view (war_system.get_threat_wars), the minimal field set
{war_id/name/threat_level/naval_required}, and the empty-array contract.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import forum_api
from src.api import senate_api
from src.api import session_api

MINIMAL_FIELDS = ("war_id", "name", "threat_level", "naval_required")


def _make_state(start_phase="forum"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"]
    return result["data"]["state"]


def _viewer(state):
    return state.get_all_players()[0].player_id


def _forum_data(state, viewer):
    result = forum_api.get_forum_view(state, viewer)
    assert result["success"]
    return result["data"]


def test_forum_view_has_war_threats():
    """T-D-01: get_forum_view returns a war_threats list (修复前 FAIL：字段缺失)."""
    state = _make_state()
    viewer = _viewer(state)
    forum_api.initialize_forum_turn(state)
    data = _forum_data(state, viewer)
    assert "war_threats" in data
    assert isinstance(data["war_threats"], list)


def test_war_threats_fields():
    """T-D-02: minimal fields present; naval_required matches wars.json
    (pyrrhic_war False L48 / first_punic_war True L85)."""
    state = _make_state()
    viewer = _viewer(state)
    # advance to the first_punic_war trigger year (-279) so both wars are threats
    while state.turn.year < -279:
        state.turn.advance_year()
    forum_api.initialize_forum_turn(state)
    data = _forum_data(state, viewer)
    rows = {row["war_id"]: row for row in data["war_threats"]}
    for row in rows.values():
        for key in MINIMAL_FIELDS:
            assert key in row, f"missing DTO field {key} in {row}"
    pyrrhic = rows.get("pyrrhic_war")
    assert pyrrhic is not None, "pyrrhic_war expected among threats"
    assert pyrrhic["naval_required"] is False
    assert pyrrhic["threat_level"] >= 1
    first_punic = rows.get("first_punic_war")
    assert first_punic is not None, "first_punic_war expected among threats at -279"
    assert first_punic["naval_required"] is True


def test_war_threats_same_identity_as_senate():
    """T-D-03: forum war_threats share war_id identity with the Senate view."""
    state = _make_state()
    viewer = _viewer(state)
    forum_api.initialize_forum_turn(state)
    forum_rows = _forum_data(state, viewer)["war_threats"]
    assert forum_rows, "forum war_threats must be non-empty after init"
    senate_result = senate_api.get_senate_view(state, viewer)
    assert senate_result["success"]
    senate_rows = senate_result["data"]["war_threats"]
    assert senate_rows, "senate war_threats must be non-empty after init"
    assert sorted(row["war_id"] for row in forum_rows) == sorted(row["war_id"] for row in senate_rows)
    for row in forum_rows:
        assert set(MINIMAL_FIELDS).issubset(row.keys())


def test_war_threats_empty_array():
    """T-D-04: no THREAT wars -> empty list (no None / no error)."""
    state = _make_state()
    viewer = _viewer(state)
    state.config._config["enable_threats"] = False  # init triggers nothing
    forum_api.initialize_forum_turn(state)
    data = _forum_data(state, viewer)
    assert data["war_threats"] == []
