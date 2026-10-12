"""EOR20261011-01 S4 — Store-level integration for the S4 query handlers.

Drives the REAL production ``GuiSessionStore`` + the reused clear-before-publish
invalidation protocol (v1.1 §7). Handlers are reached only through the public
production seam (``doGlobalQuery`` → Adapter → ``gui_query_api``); no
helper/shortcut/mock entry.
"""
import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import pytest

from unittest.mock import patch

from src.api import session_api
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import GuiSessionStore

S4_QUERIES = ("contract_status", "province_info")


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


def test_store_publishes_s4_typed_dtos_non_tabular():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    for query_id in S4_QUERIES:
        feedback = store.doGlobalQuery(query_id)
        assert feedback["success"], query_id
        dto = store.globalQueryResult
        assert dto.get("id") == query_id
        assert dto.get("result_state") in ("OK", "EMPTY")
        assert dto["capabilities"] == {"can_filter": True, "can_detail": True}
        # non-tabular lists: no column schema (rendered via the label+value path)
        assert dto.get("columns") == [], query_id
        assert all(it.get("columns", []) == [] for it in dto["items"]), query_id
        store.clearGlobalQuery()


def test_store_publishes_s4_detail_and_back_clears_selection():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    # province_info detail of Italy (id 0) then back to the unfiltered list
    feedback = store.doGlobalQuery("province_info", "", "0")
    assert feedback["success"]
    assert store.globalQueryResult.get("detail") is not None
    assert store.globalQueryResult["detail"]["record_id"] == "0"

    back = store.doGlobalQuery("province_info", "", "")
    assert back["success"]
    assert store.globalQueryResult.get("detail") is None
    assert store.globalQueryResult.get("items")


def test_s4_province_missing_source_clears_old_content():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    ok = store.doGlobalQuery("province_info")
    assert ok["success"]
    assert store.globalQueryResult.get("id") == "province_info"

    from types import SimpleNamespace
    broken = SimpleNamespace(province_id=3, name="X", conquered=True, total_land=None,
                             land_public=1, land_private=0, governor_id=None,
                             governor_type="propraetor", grievance=0,
                             tax_contract_id=None, project_contract_id=None)
    with patch.object(state, "get_all_provinces", return_value=[broken]):
        bad = store.doGlobalQuery("province_info")

    assert bad["success"] is False
    assert bad["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in bad["data"]["errors"]] == ["system_unavailable"]
    # old content cleared; window CLOSED; nothing retained.
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_s4_contract_missing_source_clears_old_content():
    state, player_ids = _hotseat_population_session()
    # seed a real OWN contract so the first query publishes OK
    viewer_faction = state.get_player(player_ids[0]).faction_id
    own = next(f for f in state.get_living_members() if f.faction_id == viewer_faction)
    c = state.create_contract(ContractType.TAX_FARMING, 0, 100, state.turn.turn_number)
    c.status = ContractStatus.ACTIVE
    c.name = "包税"
    c.awarded_faction = viewer_faction
    c.awarded_to = own.id

    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    ok = store.doGlobalQuery("contract_status")
    assert ok["success"]
    assert store.globalQueryResult.get("id") == "contract_status"
    assert store.globalQueryResult.get("result_state") == "OK"

    from types import SimpleNamespace
    broken = SimpleNamespace(id=7, contract_type=ContractType.TAX_FARMING, status=None,
                             name="x", awarded_faction=None, awarded_to=None)
    with patch.object(state, "get_all_contracts", return_value=[broken]):
        bad = store.doGlobalQuery("contract_status")

    assert bad["success"] is False
    assert [e["code"] for e in bad["data"]["errors"]] == ["system_unavailable"]
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_s4_adapter_forwards_typed_failure_not_success():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    from types import SimpleNamespace
    broken = SimpleNamespace(province_id=3, name="X", conquered=True, total_land=None,
                             land_public=1, land_private=0, governor_id=None,
                             governor_type="propraetor", grievance=0,
                             tax_contract_id=None, project_contract_id=None)
    with patch.object(state, "get_all_provinces", return_value=[broken]):
        dto = store._adapter.get_global_query_result(player_ids[0], "province_info", "", "")

    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
    assert dto["items"] == [] and dto["summary"] == {}


def test_s4_readonly_invariant_through_store():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    _ReceiverShim(store)

    before = copy.deepcopy(state.to_dict())
    rng_before = random.getstate()

    for query_id in S4_QUERIES:
        store.doGlobalQuery(query_id, "", "")
        store.doGlobalQuery(query_id, "zzz", "")
    store.doGlobalQuery("province_info", "", "0")

    after = copy.deepcopy(state.to_dict())
    assert after == before
    assert random.getstate() == rng_before
