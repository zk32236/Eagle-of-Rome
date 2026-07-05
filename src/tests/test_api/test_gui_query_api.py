import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import gui_query_api, session_api


def _setup_state():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    return state, viewer_id


def test_game_status_query_returns_public_snapshot():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "game_status")

    assert result["success"]
    data = result["data"]
    assert data["id"] == "game_status"
    assert data["status"] == "connected"
    assert data["title_key"] == "query.game_status.title"
    assert data["summary"]["current_phase_id"] == "mortality"
    assert any(item["label_key"] == "query.item.treasury" for item in data["items"])


def test_faction_query_only_exposes_viewer_treasury():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id

    result = gui_query_api.get_global_query_result(state, viewer_id, "faction_info")

    assert result["success"]
    data = result["data"]
    assert data["status"] == "readonly"
    factions = data["summary"]["factions"]
    assert any(f["id"] == viewer_faction_id and "treasury" in f for f in factions)
    assert all(
        "treasury" not in f
        for f in factions
        if f["id"] != viewer_faction_id
    )
    treasury_items = [item for item in data["items"] if item["label_key"] == "query.item.treasury"]
    assert len(treasury_items) == 1
    assert treasury_items[0]["meta"]["scope"] == "viewer_faction"


def test_war_list_query_uses_public_dto_shape():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "war_list")

    assert result["success"]
    data = result["data"]
    assert data["status"] == "readonly"
    assert "wars" in data["summary"]
    assert "counts" in data["summary"]
    for war in data["summary"]["wars"]:
        assert {"id", "name", "status", "threat_level", "naval_required"}.issubset(war.keys())


def test_legion_status_query_returns_readonly_counts_without_mutation():
    state, viewer_id = _setup_state()
    before = {phase_id: state.is_phase_executed(phase_id) for phase_id in [
        "mortality", "revenue", "forum", "population", "senate", "combat", "resolution"
    ]}

    result = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")

    assert result["success"]
    data = result["data"]
    assert data["status"] == "readonly"
    assert data["summary"]["counts"]["total"] >= 1
    assert "legions" in data["summary"]
    after = {phase_id: state.is_phase_executed(phase_id) for phase_id in before}
    assert after == before


def test_placeholder_query_uses_unified_dto():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "contract_status")

    assert result["success"]
    data = result["data"]
    assert data["id"] == "contract_status"
    assert data["status"] == "placeholder"
    assert data["items"][0]["label_key"] == "query.item.handoff"


def test_query_rejects_invalid_viewer():
    state, _ = _setup_state()

    result = gui_query_api.get_global_query_result(state, "missing_player", "game_status")

    assert not result["success"]
    assert "Viewer player not found" in result["message"]
