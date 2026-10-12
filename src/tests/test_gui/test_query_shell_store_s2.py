"""EOR20261011-01 S2 — Store-level integration for the S2 query handlers.

Drives the REAL production ``GuiSessionStore`` and the reused clear-before-publish
invalidation protocol (v1.1 §7). The viewer transition is triggered through the
production public slot ``doCompletePlayer`` with a real receiver-completion
witness — no direct ``switchViewer`` / private-helper / mock entry.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import pytest

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import GuiSessionStore


@pytest.fixture(autouse=True)
def _rng_isolated():
    """Restore the process RNG state after each test (suite determinism)."""
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


def test_store_publishes_s2_typed_dtos():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    for query_id in ("faction_treasury", "private_land", "faction_info"):
        feedback = store.doGlobalQuery(query_id)
        assert feedback["success"], query_id
        dto = store.globalQueryResult
        assert dto.get("id") == query_id
        assert dto.get("result_state") in ("OK", "EMPTY")
        store.clearGlobalQuery()


# A4-S2 — unique A-private sensitive sentinel (own private-land figure wealth).
_S2_SENTINEL = 867530926


def test_s2_query_viewer_handoff_clears_before_publish_and_autoreads():
    state, player_ids = _hotseat_population_session()
    viewer_faction_id = state.get_player(player_ids[0]).faction_id
    own_fig = next(f for f in state.get_living_members()
                   if f.faction_id == viewer_faction_id)
    own_fig._land_private = 7          # sanctioned fixture: gives A a landowner
    own_fig.wealth = _S2_SENTINEL      # unique A-private sensitive value

    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    # A opens A's OWN NONEMPTY sensitive private_land DETAIL (A-private wealth).
    opened = store.doGlobalQuery("private_land", "", str(own_fig.id))
    assert opened["success"]
    assert store.globalQueryResult.get("id") == "private_land"
    assert store.globalQueryResult.get("detail") is not None
    assert store.globalQueryResult["detail"]["record_id"] == str(own_fig.id)
    detail_keys = {f["label_key"]
                   for f in store.globalQueryResult["detail"]["fields"]}
    assert "query.private_land.wealth" in detail_keys
    assert str(_S2_SENTINEL) in json.dumps(store.globalQueryResult, ensure_ascii=False)

    shim = _ReceiverShim(store)
    observed_dto = []
    invalidations = []

    def _on_invalidated(keep_open):
        invalidations.append(bool(keep_open))
        observed_dto.append(dict(store.globalQueryResult))

    store.queryInvalidated.connect(_on_invalidated)
    handoffs = []
    store.handoffRequired.connect(lambda next_id: handoffs.append(next_id))

    completed = store.doCompletePlayer()

    assert completed["success"]
    assert handoffs, "production handoff was not triggered"
    assert store.viewerPlayerId == player_ids[1]
    # Clear-before-publish: every invalidation observed an EMPTY Store DTO, and a
    # real receiver witnessed/acked each invalidation.
    assert observed_dto, "no invalidation emitted"
    assert all(dto == {} for dto in observed_dto)
    assert shim.calls, "receiver never witnessed an invalidation"
    assert any(k is True for k in invalidations), "OPEN intent not preserved"
    # The OPEN S2 query auto-re-reads for the NEW viewer; A's detail is discarded
    # (never replayed) and A's sensitive sentinel is absent from B's surface.
    assert store.globalQueryResult.get("id") == "private_land"
    assert store.globalQueryResult.get("result_state") in ("OK", "EMPTY")
    assert store.globalQueryResult.get("detail") is None
    assert str(_S2_SENTINEL) not in json.dumps(store.globalQueryResult,
                                               ensure_ascii=False)
    # B's view only exposes B-authorised content (its own faction's records).
    b_faction = state.get_player(player_ids[1]).faction_id
    for item in store.globalQueryResult.get("items", []):
        rec = state.get_member(int(item["record_id"]))
        assert rec is not None and rec.faction_id == b_faction


def test_s2_faction_treasury_closed_on_entry_stays_closed_after_handoff():
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
