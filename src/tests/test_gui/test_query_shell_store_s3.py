"""EOR20261011-01 S3 — Store-level integration for the S3 query handlers.

Drives the REAL production ``GuiSessionStore`` and the reused clear-before-publish
invalidation protocol (v1.1 §7). The viewer transition is triggered through the
production public slot ``doCompletePlayer`` with a real receiver-completion
witness — no direct ``switchViewer`` / private-helper / mock entry.
"""
import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import pytest

from unittest.mock import patch

from src.api import game_api, session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import GuiSessionStore

S3_QUERIES = ("game_status", "public_land", "help")


@pytest.fixture(autouse=True)
def _rng_isolated():
    state = random.getstate()
    yield
    random.setstate(state)


def _hotseat_population_session():
    """Sanctioned initial-state fixture: real production session, HUMAN seats."""
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    player_ids = [player.player_id for player in state.get_all_players()]
    for player_id in player_ids[1:]:
        original = state.get_player(player_id)
        state.remove_player(player_id)
        state.add_player(Player(
            player_id=player_id,
            faction_id=original.faction_id,
            player_type=PlayerType.HUMAN,
        ))
    state.set_turn_order(player_ids)
    state.set_current_player(player_ids[0])
    return state, player_ids


class _ReceiverShim:
    """Headless stand-in for the production QML receiver: on every
    ``queryInvalidated(keep_open)`` it clears its (empty) model and acks the
    current epoch — exactly ``QueryResultOverlay.resetForInvalidation``."""

    def __init__(self, store, connect=True):
        self._store = store
        self.calls = []
        if connect:
            store.queryInvalidated.connect(self._on_invalidated)

    def _on_invalidated(self, keep_open):
        self.calls.append(bool(keep_open))
        self._store.ackQueryInvalidation(self._store.queryInvalidationEpoch)


def test_store_publishes_s3_typed_dtos_non_tabular():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    for query_id in S3_QUERIES:
        feedback = store.doGlobalQuery(query_id)
        assert feedback["success"], query_id
        dto = store.globalQueryResult
        assert dto.get("id") == query_id
        assert dto.get("result_state") == "OK"
        assert dto["capabilities"] == {"can_filter": False, "can_detail": False}
        # scalar / help are NON-TABULAR: no column schema -> the overlay renders
        # them via the legacy label+value path (no list header row).
        assert dto.get("columns") == [], query_id
        assert dto.get("items"), query_id
        assert all(it.get("columns", []) == [] for it in dto["items"]), query_id
        store.clearGlobalQuery()


def test_s3_scalar_queries_closed_on_entry_stays_closed_after_handoff():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    handoffs = []
    store.handoffRequired.connect(lambda next_id: handoffs.append(next_id))

    completed = store.doCompletePlayer()

    assert completed["success"]
    assert handoffs
    assert store.viewerPlayerId == player_ids[1]
    assert store.globalQueryResult == {}


def test_s3_nonfilterable_filter_rejected_keeps_window_closed():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    feedback = store.doGlobalQuery("help", "x", "")

    assert feedback["success"] is False
    assert feedback["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in feedback["data"]["errors"]] == ["invalid_request"]
    # a rejected scalar leaves the cache EMPTY and the window CLOSED
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_s3_readonly_invariant_through_store():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    before = copy.deepcopy(state.to_dict())
    rng_before = random.getstate()

    for query_id in S3_QUERIES:
        store.doGlobalQuery(query_id, "", "")
        store.doGlobalQuery(query_id, "zzz", "")

    after = copy.deepcopy(state.to_dict())
    assert after == before
    assert random.getstate() == rng_before


# ===========================================================================
# F1 / N1 (ATTEMPT-2) — Adapter + Store truth propagation + old-content clearance
# ===========================================================================
def test_s3_adapter_propagates_game_status_missing_source_failure():
    """F1: the real Adapter (``GuiApiAdapter``) forwards the typed
    system_unavailable failure unchanged — never a fabricated success — when the
    canonical turn source is absent."""
    from src.core.game_state import GameState
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    with patch.object(GameState, "turn", None):
        dto = store._adapter.get_global_query_result(player_ids[0], "game_status", "", "")

    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
    assert dto["items"] == [] and dto["summary"] == {}


def test_s3_store_missing_source_failure_clears_old_content():
    """F1: after a successful game_status, a missing canonical source must
    propagate the typed failure through the Store AND clear the previously
    published DTO/model (no retained old content, window CLOSED)."""
    from src.core.game_state import GameState
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    ok = store.doGlobalQuery("game_status")
    assert ok["success"]
    assert store.globalQueryResult.get("id") == "game_status"
    assert store.globalQueryResult.get("result_state") == "OK"
    assert store.globalQueryResult.get("items")

    with patch.object(GameState, "turn", None):
        bad = store.doGlobalQuery("game_status")

    assert bad["success"] is False
    assert bad["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in bad["data"]["errors"]] == ["system_unavailable"]
    # Old content cleared; window CLOSED; nothing retained.
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_s3_store_public_land_failed_result_with_data_clears_old_content():
    """N1: a failed canonical producer (success=False) carrying data must fail
    closed through the Store and clear the previously published DTO."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    ok = store.doGlobalQuery("public_land")
    assert ok["success"]
    assert store.globalQueryResult.get("id") == "public_land"

    bad = {"success": False, "data": {
        "national_land": 1, "land_price": 1, "value": 1,
        "tax_rate": 0.02, "annual_income": 0, "treasury": 0,
    }}
    with patch.object(game_api, "get_public_land_info", return_value=bad):
        fb = store.doGlobalQuery("public_land")

    assert fb["success"] is False
    assert [e["code"] for e in fb["data"]["errors"]] == ["system_unavailable"]
    assert store.globalQueryResult == {}
    assert store._query_open is False
