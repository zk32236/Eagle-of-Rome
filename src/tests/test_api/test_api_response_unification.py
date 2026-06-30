"""Focused tests for AS-P1-01 API response unification."""

from unittest.mock import MagicMock

from src.api import api_response
from src.api import forum_api, senate_api


RESPONSE_KEYS = {"success", "message", "data", "errors"}


def assert_api_response_shape(response):
    assert set(response.keys()) == RESPONSE_KEYS
    assert isinstance(response["success"], bool)
    assert isinstance(response["message"], str)
    assert isinstance(response["errors"], list)


def test_unified_api_response_factory_allows_none_data():
    response = api_response(True, "ok")

    assert_api_response_shape(response)
    assert response["data"] is None


def test_forum_api_permission_error_uses_unified_response_shape():
    state = MagicMock()
    state.config = {"testing.bypass_player_check": False}
    state.is_current_player.return_value = False

    response = forum_api.retire_figure(state, "player_optimates", 1)

    assert_api_response_shape(response)
    assert response["success"] is False


def test_forum_api_invalid_recruit_amount_uses_unified_response_shape():
    state = MagicMock()
    state.config = {"testing.bypass_player_check": False}
    state.is_current_player.return_value = True
    state.get_player.return_value = MagicMock(faction_id="optimates")

    response = forum_api.recruit_figure(state, "player_optimates", 1, 0)

    assert_api_response_shape(response)
    assert response["success"] is False


def test_senate_api_none_state_errors_use_unified_response_shape():
    responses = [
        senate_api.get_senate_initial_info(None),
        senate_api.propose(None, "player_optimates", "war"),
        senate_api.vote(None, "player_optimates", [1], [True]),
        senate_api.veto(None, "player_optimates", [1]),
        senate_api.resolve_senate(None),
    ]

    for response in responses:
        assert_api_response_shape(response)
        assert response["success"] is False
