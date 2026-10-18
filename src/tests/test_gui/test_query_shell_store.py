"""EOR20261011-01 S1 — shared query shell Store-level behaviour.

Covers the viewer/handoff invalidation protocol (v1.2 §2.1): synchronous
clear-before-publish with a REAL receiver-completion witness, retained-OPEN
auto-refresh of the SAME query against the new viewer, CLOSED-on-entry stays
CLOSED, read-during-guard fail-closed, automatic-failure empty+CLOSED routing and
the standalone/public reset paths.

The production handoff chain is driven through the real public slots
``doCompletePlayer`` / ``submitPopulationVotes``; no direct ``switchViewer`` /
private-helper / mock shortcut is used as an acceptance entry.

``_ProductionReceiverShim`` mirrors the production QML receiver
(``GameShell.Connections`` → ``QueryResultOverlay.resetForInvalidation``) which
clears every local/bound model and then calls
``sessionStore.ackQueryInvalidation(epoch)`` (v1.2 §2.1 step 3). The REAL QML
receiver itself is exercised in ``test_query_shell_qt.py``; the shim only makes
the Store protocol testable headless — it is not an app/confirmation substitute.
"""
import copy
import json
import os
import random
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from PySide6.QtCore import QCoreApplication, Qt

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import GuiSessionStore


def _hotseat_population_session():
    """Sanctioned initial-state fixture: real production session, 3 HUMAN seats."""
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


def _own_figure_id(state, viewer_id):
    faction_id = state.get_player(viewer_id).faction_id
    return next(fig.id for fig in state.get_living_members() if fig.faction_id == faction_id)


# A4 (AC14) — unique sensitive sentinel (an A-private value). Set on A's own
# figure, it must be ABSENT across the temporal invalidation chain and in final B.
_SENSITIVE_SENTINEL = 867530925


class _ProductionReceiverShim:
    """Headless stand-in for the production QML receiver.

    On each ``queryInvalidated(keep_open)`` it clears its (empty) local model and
    then acks the CURRENT epoch — exactly what ``resetForInvalidation`` does in
    ``QueryResultOverlay.qml``. Used to make the Store witness testable without a
    QML engine; the real receiver is exercised in ``test_query_shell_qt.py``.
    """

    def __init__(self, store, ack: bool = True, connect: bool = True):
        self._store = store
        self._ack = ack
        self.calls = []
        if connect:
            store.queryInvalidated.connect(self._on_invalidated)

    def _on_invalidated(self, keep_open):
        self.calls.append(bool(keep_open))
        if self._ack:
            self._store.ackQueryInvalidation(self._store.queryInvalidationEpoch)


def test_do_global_query_publishes_typed_dto_and_filter():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    feedback = store.doGlobalQuery("figure_search", "", "")
    assert feedback["success"]
    assert store.globalQueryResult["id"] == "figure_search"
    assert store.globalQueryResult["result_state"] in ("OK", "EMPTY")
    assert store.globalQueryResult["capabilities"]["can_filter"] is True

    filtered = store.doGlobalQuery("figure_search", "zzzz-no-match", "")
    assert filtered["success"]
    assert store.globalQueryResult["result_state"] == "EMPTY"
    assert store.globalQueryResult["filters"]["applied"] == "zzzz-no-match"


def test_close_clears_window_and_invalidates():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    events = []
    store.queryInvalidated.connect(lambda keep_open: events.append(keep_open))

    feedback = store.clearGlobalQuery()

    assert feedback["success"]
    assert store.globalQueryResult == {}
    assert events and events[-1] is False


def test_read_during_invalidation_guard_fails_closed():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    captured = {}

    def _on_invalidated(keep_open):
        captured["nested"] = store.doGlobalQuery("figure_search", "", "")

    store.queryInvalidated.connect(_on_invalidated)
    store.clearGlobalQuery()

    nested = captured.get("nested")
    assert nested is not None
    assert nested["success"] is False
    assert nested["data"]["result_state"] == "ERROR"
    assert [err["code"] for err in nested["data"]["errors"]] == ["query_unavailable"]


def test_standalone_refresh_closes_open_query():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    events = []
    store.queryInvalidated.connect(lambda keep_open: events.append(keep_open))
    store.refreshSnapshot()

    assert store.globalQueryResult == {}
    assert events and events[-1] is False


# ===========================================================================
# F2 — REAL receiver-completion witness gates the new-viewer publish
# ===========================================================================
def test_receiver_ack_allows_viewer_publication():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    receiver = _ProductionReceiverShim(store)
    store.handoffRequired.connect(lambda next_id: None)

    completed = store.doCompletePlayer()

    assert completed["success"]
    # The receiver acked the epoch, so the new viewer WAS published.
    assert store.viewerPlayerId == player_ids[1]
    assert receiver.calls, "receiver never invoked"
    # Automatic unfiltered re-read of the SAME query for the new viewer.
    assert store.globalQueryResult.get("id") == "figure_search"


def test_viewer_change_without_receiver_ack_fails_closed():
    """A non-responding receiver (connected but never acks) must NOT satisfy the
    completion witness → no new-viewer publication (v1.2 §2.1 step 3, F2)."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    zombie = _ProductionReceiverShim(store, ack=False)
    store.handoffRequired.connect(lambda next_id: None)

    store.doCompletePlayer()

    assert zombie.calls, "receiver was never invoked"
    # Fail-closed: the new viewer was NOT published and the window is empty/closed.
    assert store.viewerPlayerId == player_ids[0]
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_queued_receiver_does_not_satisfy_completion_witness():
    """A queued (Qt.QueuedConnection) receiver has NOT run when the synchronous
    emit returns → its ack is not observed → fail-closed (F2)."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    shim = _ProductionReceiverShim(store, ack=True, connect=False)
    store.queryInvalidated.connect(shim._on_invalidated, Qt.QueuedConnection)
    store.handoffRequired.connect(lambda next_id: None)

    store.doCompletePlayer()

    assert store.viewerPlayerId == player_ids[0]
    assert store.globalQueryResult == {}

    # Drain the deliberately-queued (never-acked) delivery NOW, while this Store
    # is alive; otherwise it fires in the next module's first event pump and
    # dereferences this finished test's Store -> native SIGSEGV (D13 R2b).
    _app = QCoreApplication.instance()
    if _app is not None:
        _app.processEvents()
    store.queryInvalidated.disconnect(shim._on_invalidated)


# ===========================================================================
# F2 residual (A4) — a PERSISTENT outstanding receiver-clear obligation
# ===========================================================================
def test_close_then_switch_without_receiver_ack_fails_closed():
    """A4 (F2 residual): an unacknowledged clear is a PERSISTENT outstanding
    receiver-clear obligation. After ``clearGlobalQuery`` leaves the Store empty +
    CLOSED, a later switch must NOT be authorised by Store-empty/CLOSED alone —
    the empty state must not masquerade as receiver completion."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    # A zombie receiver: invoked, but never writes the matching epoch ack.
    zombie = _ProductionReceiverShim(store, ack=False)

    store.clearGlobalQuery()
    assert store.globalQueryResult == {}
    assert store._query_open is False
    assert zombie.calls, "receiver invoked without an ack"

    # Store-empty/CLOSED alone must NOT witness receiver completion.
    store.switchViewer(player_ids[1])
    assert store.viewerPlayerId == player_ids[0], "empty Store bypassed the outstanding ack"
    assert store.globalQueryResult == {}
    assert store._query_open is False


def test_failed_switch_then_retry_requires_real_receiver_ack():
    """A4 (F2 residual): a failed (unacknowledged) switch keeps the obligation; the
    retry switches ONLY after a real receiver ack — never via the empty Store."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    zombie = _ProductionReceiverShim(store, ack=False)
    store.handoffRequired.connect(lambda next_id: None)

    store.doCompletePlayer()
    # Fail-closed: the new viewer was NOT published; the obligation is retained.
    assert store.viewerPlayerId == player_ids[0]
    assert store.globalQueryResult == {}

    # Retry with the receiver now acking -> obligation discharged -> publish.
    zombie._ack = True
    store.switchViewer(player_ids[1])
    assert store.viewerPlayerId == player_ids[1]


def test_persistent_zombie_receiver_never_satisfies_witness():
    """A4 (F2 residual): a persistently non-acknowledging receiver keeps EVERY
    subsequent switch fail-closed (no empty-Store bypass, no self-assigned flag)."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    _zombie = _ProductionReceiverShim(store, ack=False)
    store.handoffRequired.connect(lambda next_id: None)
    store.doCompletePlayer()  # failed switch -> persistent obligation

    for _ in range(3):
        store.switchViewer(player_ids[1])
        assert store.viewerPlayerId == player_ids[0]
        assert store.globalQueryResult == {}
        assert store._query_open is False


def test_viewer_handoff_from_open_query_retains_and_autoreads():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    own_figure = _own_figure_id(state, player_ids[0])

    # A opens A's OWN distinguishable sensitive detail.
    opened = store.doGlobalQuery("figure_search", "", str(own_figure))
    assert opened["success"]
    assert store.globalQueryResult["detail"] is not None
    assert store.globalQueryResult["detail"]["record_id"] == str(own_figure)
    # The opened detail is A's OWN non-empty private block (wealth etc.).
    own_field_keys = {f["label_key"] for f in store.globalQueryResult["detail"]["fields"]}
    assert "query.figure.wealth" in own_field_keys

    shim = _ProductionReceiverShim(store)
    invalidations = []
    observed_dto_at_invalidate = []
    handoffs = []

    def _on_invalidated(keep_open):
        invalidations.append(keep_open)
        observed_dto_at_invalidate.append(dict(store.globalQueryResult))

    store.queryInvalidated.connect(_on_invalidated)
    store.handoffRequired.connect(lambda next_id: handoffs.append(next_id))

    # Production entry: complete the current player -> next HUMAN handoff.
    completed = store.doCompletePlayer()

    assert completed["success"]
    assert handoffs, "production handoff was not triggered"
    assert store.viewerPlayerId == player_ids[1]

    # Clear-before-publish: every invalidation saw an EMPTY Store DTO.
    assert invalidations, "no invalidation emitted"
    assert all(dto == {} for dto in observed_dto_at_invalidate)
    # OPEN intent preserved across the viewer change.
    assert any(keep_open is True for keep_open in invalidations)

    # Automatic same-query UNFILTERED re-read for the NEW viewer; old detail
    # discarded (never replayed).
    assert store.globalQueryResult.get("id") == "figure_search"
    assert store.globalQueryResult.get("result_state") in ("OK", "EMPTY")
    assert store.globalQueryResult.get("detail") is None


def test_viewer_handoff_from_closed_window_stays_closed():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    handoffs = []
    store.handoffRequired.connect(lambda next_id: handoffs.append(next_id))

    completed = store.doCompletePlayer()

    assert completed["success"]
    assert handoffs
    assert store.viewerPlayerId == player_ids[1]
    # CLOSED-on-entry stays CLOSED: no query window auto-opened.
    assert store.globalQueryResult == {}


def test_same_id_confirmation_invalidates_and_rereads_when_open():
    """Store-level idempotent same-ID re-read (NOT an AC14 production-chain
    claim): a switchViewer to the SAME id still invalidates and, when OPEN,
    re-reads the same query unfiltered."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    shim = _ProductionReceiverShim(store)
    assert store.switchViewer(player_ids[0]) is True

    assert store.viewerPlayerId == player_ids[0]
    assert store.globalQueryResult.get("id") == "figure_search"
    assert store.globalQueryResult.get("result_state") in ("OK", "EMPTY")


def test_same_id_confirmation_keeps_window_closed_when_closed():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    store.switchViewer(player_ids[0])

    assert store.globalQueryResult == {}


# ===========================================================================
# F3 — explicit Close cancels retained intent; never auto-reopens
# ===========================================================================
def test_explicit_close_during_viewer_transaction_cancels_and_never_reopens():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    shim = _ProductionReceiverShim(store)
    closed = {"called": False}

    def _on_handoff(_next_id):
        # The user hits Close while the viewer/handoff transaction is active.
        store.clearGlobalQuery()
        closed["called"] = True

    store.handoffRequired.connect(_on_handoff)
    store.doCompletePlayer()

    assert closed["called"]
    # Cancelled: empty and CLOSED, no auto-reopen and no old-data restore.
    assert store.globalQueryResult == {}
    assert store._query_open is False


# ===========================================================================
# F4 — automatic failure leaves an EMPTY CLOSED window + routes safe feedback
# ===========================================================================
def test_auto_refresh_failure_leaves_window_empty_and_closed():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    failure = gui_query_api.build_failure_dto(
        "figure_search", "ERROR", gui_query_api.ERR_QUERY_FAILED
    )
    events = []
    feedbacks = []
    store.queryInvalidated.connect(lambda keep_open: events.append(keep_open))
    store.feedbackRaised.connect(lambda ftype, fmsg: feedbacks.append((ftype, fmsg)))
    shim = _ProductionReceiverShim(store)

    with patch.object(store._adapter, "get_global_query_result", return_value=failure):
        store.doCompletePlayer()

    # EMPTY cache (no retained ERROR/DENIED DTO) + CLOSED window (F4).
    assert store.globalQueryResult == {}
    assert store._query_open is False
    assert store._query_active_id == ""
    assert events and events[-1] is False
    # Safe query-error feedback routed to the shell (never silent).
    assert any(ftype == "error" for ftype, _ in feedbacks), feedbacks


def test_do_global_query_failure_leaves_empty_cache_and_closed_window():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    failure = gui_query_api.build_failure_dto(
        "figure_search", "ERROR", gui_query_api.ERR_QUERY_FAILED
    )
    with patch.object(store._adapter, "get_global_query_result", return_value=failure):
        feedback = store.doGlobalQuery("figure_search", "", "")

    assert feedback["success"] is False
    # The safe failure DTO is surfaced as feedback data, but the Store cache is
    # EMPTY and the window CLOSED (no retained ERROR DTO).
    assert store.globalQueryResult == {}
    assert store._query_open is False
    assert feedback["data"]["result_state"] == "ERROR"


# ===========================================================================
# F2 — stale viewer/epoch result is discarded before publication
# ===========================================================================
def test_stale_result_discarded_when_epoch_changes_mid_read():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    real = store._adapter.get_global_query_result

    def stale(viewer, query, filt, rec):
        # A newer transaction advances the epoch during the synchronous read.
        store._query_epoch += 1
        return real(viewer, query, filt, rec)

    with patch.object(store._adapter, "get_global_query_result", side_effect=stale):
        store.doGlobalQuery("figure_search", "", "")

    assert store.globalQueryResult == {}


def test_invalid_new_viewer_auto_refresh_fails_closed():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")

    shim = _ProductionReceiverShim(store)
    feedbacks = []
    store.feedbackRaised.connect(lambda ftype, fmsg: feedbacks.append((ftype, fmsg)))
    store.switchViewer("ghost-player")

    # Invalid viewer -> empty + CLOSED + safe feedback; no retained DENIED DTO.
    assert store._query_open is False
    assert store.queryGuarded is False
    assert store.globalQueryResult == {}
    assert any(ftype == "error" for ftype, _ in feedbacks), feedbacks


# ===========================================================================
# A4 (AC14 reachable) — REAL year-advance / _on_refresh temporal traces:
# at every callback the old sensitive detail is already cleared (Store empty),
# and the window ends CLOSED (standalone reset is close-before-refresh).
# ===========================================================================
def test_year_advance_temporal_trace_closes_and_clears_old_query():
    """A4 (AC14 reachable): a REAL year advance (``doAdvanceResolution`` ->
    ``_reset_phase_caches``) performs the close-before-refresh temporal chain. At
    every queryResultChanged/snapshotChanged/queryInvalidated callback the Store
    DTO is already EMPTY (old sensitive detail cleared); the window ends CLOSED."""
    from src.api import session_api
    result = session_api.create_gui_prototype_session(start_phase="combat")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    players = result["data"]["human_players"]
    player_id = players[0]
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")

    store = GuiSessionStore(state)
    store.initialize(player_id)
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.canAdvanceResolution is True

    # A opens A's OWN sensitive detail with a unique sentinel private value.
    own_id = _own_figure_id(state, player_id)
    state.get_living_member(own_id).wealth = _SENSITIVE_SENTINEL
    opened = store.doGlobalQuery("figure_search", "", str(own_id))
    assert opened["success"]
    assert str(_SENSITIVE_SENTINEL) in json.dumps(store.globalQueryResult,
                                                  ensure_ascii=False)

    blobs = []

    def _cap():
        blobs.append(json.dumps(store.globalQueryResult, ensure_ascii=False))

    store.queryResultChanged.connect(_cap)
    store.snapshotChanged.connect(_cap)
    store.queryInvalidated.connect(lambda keep_open: _cap())

    before_epoch = store.queryInvalidationEpoch
    advanced = store.doAdvanceResolution()

    assert advanced["success"], advanced.get("message")
    assert store.queryInvalidationEpoch > before_epoch
    assert blobs, "no temporal callback observed"
    assert all(b == "{}" for b in blobs), blobs
    assert store.globalQueryResult == {}
    assert store._query_open is False
    assert str(_SENSITIVE_SENTINEL) not in json.dumps(store.globalQueryResult)


def test_on_refresh_temporal_trace_closes_and_clears_old_query():
    """A4 (AC14 reachable): the REAL production refresh callback ``_on_refresh``
    (wired by the Adapter after a successful mutation) performs the standalone
    close-before-refresh chain: every callback sees an EMPTY Store and the old
    sensitive detail is gone (window ends CLOSED)."""
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    own_id = _own_figure_id(state, player_ids[0])
    state.get_living_member(own_id).wealth = _SENSITIVE_SENTINEL
    opened = store.doGlobalQuery("figure_search", "", str(own_id))
    assert opened["success"]
    assert str(_SENSITIVE_SENTINEL) in json.dumps(store.globalQueryResult,
                                                  ensure_ascii=False)

    blobs = []

    def _cap():
        blobs.append(json.dumps(store.globalQueryResult, ensure_ascii=False))

    store.queryResultChanged.connect(_cap)
    store.snapshotChanged.connect(_cap)
    store.queryInvalidated.connect(lambda keep_open: _cap())

    store._on_refresh()

    assert blobs and all(b == "{}" for b in blobs), blobs
    assert store.globalQueryResult == {}
    assert store._query_open is False


# ===========================================================================
# Standalone reset / _on_refresh close an open query (not auto-reopen)
# ===========================================================================
def test_standalone_reset_closes_open_query():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}

    store._reset_phase_caches()

    assert store.globalQueryResult == {}


def test_on_refresh_both_branches_close_open_query():
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    # branch 1: mortality phase result absent -> reset path closes
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}
    store._on_refresh()
    assert store.globalQueryResult == {}

    # branch 2: phase result present + turn advanced -> still closes
    store.doGlobalQuery("figure_search", "", "")
    assert store.globalQueryResult != {}
    state.record_phase_result("mortality", {"success": True, "message": "", "data": {}})
    store._on_refresh()
    assert store.globalQueryResult == {}


# ===========================================================================
# F6 — the Adapter never forwards raw/malformed failure text
# ===========================================================================
def test_adapter_sanitizes_malformed_failure_dict_with_raw_message():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    poison = {
        "success": False,
        "message": "SECRET backend text",
        "data": {"result_state": "ERROR", "message": "SECRET backend text", "errors": []},
    }
    with patch.object(gui_query_api, "get_global_query_result", return_value=poison):
        dto = store._adapter.get_global_query_result(player_ids[0], "figure_search", "", "")

    blob = json.dumps(dto, ensure_ascii=False)
    assert "SECRET" not in blob
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["query_failed"]


def test_adapter_sanitizes_denied_failure_with_unknown_code():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    poison = {
        "success": False,
        "data": {
            "result_state": "DENIED",
            "message": "SECRET",
            "errors": [{"code": "RAW_BACKEND_CODE", "message": "SECRET"}],
        },
    }
    with patch.object(gui_query_api, "get_global_query_result", return_value=poison):
        dto = store._adapter.get_global_query_result(player_ids[0], "figure_search", "", "")

    blob = json.dumps(dto, ensure_ascii=False)
    assert "SECRET" not in blob
    assert "RAW_BACKEND_CODE" not in blob
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["query_failed"]


def test_adapter_preserves_legit_safe_failure_enum():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    legit = gui_query_api.build_failure_dto(
        "figure_search", "DENIED", gui_query_api.ERR_RECORD_UNAVAILABLE
    )
    with patch.object(
        gui_query_api, "get_global_query_result",
        return_value={"success": False, "data": legit},
    ):
        dto = store._adapter.get_global_query_result(player_ids[0], "figure_search", "", "")

    assert dto["result_state"] == "DENIED"
    assert [e["code"] for e in dto["errors"]] == ["record_unavailable"]


def test_adapter_rejects_malformed_success_envelope():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    malformed = {
        "success": True,
        "data": {"id": "figure_search", "result_state": "OK",
                 "message": "SECRET", "items": []},  # missing summary/capabilities
    }
    with patch.object(gui_query_api, "get_global_query_result", return_value=malformed):
        dto = store._adapter.get_global_query_result(player_ids[0], "figure_search", "", "")

    blob = json.dumps(dto, ensure_ascii=False)
    assert "SECRET" not in blob
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["query_failed"]


def test_adapter_nonstr_failure_code_never_raises():
    """A4 (F6 residual): a non-str / unhashable failure ``code`` (list/dict/int)
    must NEVER raise; the malformed envelope is normalised to the fixed safe
    ``query_failed`` shell with redacted copy (type validated before enum lookup)."""
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    for bad_code in ([], {}, 123, None, ["x"], {"code": 1}):
        poison = {
            "success": False,
            "message": "SECRET backend text",
            "data": {
                "result_state": "ERROR",
                "message": "SECRET backend text",
                "errors": [{"code": bad_code, "message": "SECRET backend text"}],
            },
        }
        with patch.object(gui_query_api, "get_global_query_result", return_value=poison):
            dto = store._adapter.get_global_query_result(
                player_ids[0], "figure_search", "", ""
            )
        blob = json.dumps(dto, ensure_ascii=False)
        assert "SECRET" not in blob, bad_code
        assert dto["result_state"] == "ERROR", bad_code
        assert [e["code"] for e in dto["errors"]] == ["query_failed"], bad_code


def test_store_chain_nonstr_failure_code_yields_safe_shell():
    """A4 (F6 residual) negative through the PUBLIC Store chain: ``code:[]`` /
    ``code:{}`` / ``code:123`` -> no exception, ``query_failed`` safe shell,
    Store empty + CLOSED."""
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    feedbacks = []
    store.feedbackRaised.connect(lambda ftype, fmsg: feedbacks.append((ftype, fmsg)))

    for bad_code in ([], {}, 123):
        poison = {
            "success": False,
            "data": {
                "result_state": "ERROR",
                "message": "SECRET",
                "errors": [{"code": bad_code, "message": "SECRET"}],
            },
        }
        with patch.object(gui_query_api, "get_global_query_result", return_value=poison):
            feedback = store.doGlobalQuery("figure_search", "", "")

        assert feedback["success"] is False, bad_code
        assert feedback["data"]["result_state"] == "ERROR", bad_code
        assert [e["code"] for e in feedback["data"]["errors"]] == ["query_failed"], bad_code
        blob = json.dumps(feedback, ensure_ascii=False)
        assert "SECRET" not in blob, bad_code
        # Empty cache + CLOSED (no retained malformed ERROR DTO).
        assert store.globalQueryResult == {}
        assert store._query_open is False

    assert any(ftype == "error" for ftype, _ in feedbacks), feedbacks


# ===========================================================================
# AC15 — DETACHED canonical Core snapshot + non-serialized history carriers +
#        bounded relevant-RNG inventory + full Store read chain (12 routes,
#        filter, own detail and failure boundaries), before/after equal
# ===========================================================================
# Mutable Core carriers that ``GameState.to_dict`` does NOT serialize (history /
# RNG-derived pools). A detached deep copy of each is compared so an in-place
# mutation of a non-serialized carrier cannot alias the "before" snapshot.
_NON_SERIALIZED_CARRIERS = (
    "_event_log",               # Core event history (log_event appends here)
    "_forum_war_events",        # forum war-event history carrier
    "_forum_rebellion_events",  # forum rebellion-event history carrier
    "_mortality_pool",          # RNG-shuffled mortality draw pool
)


def _carrier_snapshot(state):
    """Detached deep copy of the non-serialized Core carriers."""
    return {name: copy.deepcopy(getattr(state, name, None))
            for name in _NON_SERIALIZED_CARRIERS}


def _rng_inventory():
    """Bounded, executable relevant-RNG inventory.

    Binds the process-wide ``random`` module state AND the state of every
    ``random.Random`` instance exposed as a module-level attribute of an already
    imported ``src.*`` product module. This is a bounded inventory (the ``src.*``
    modules loaded at call time) paired with the global generator — not an
    unbounded repository-wide claim.
    """
    inventory = {"random": random.getstate()}
    for mod_name, module in sorted(sys.modules.items()):
        if module is None or not mod_name.startswith("src"):
            continue
        for attr, value in vars(module).items():
            if isinstance(value, random.Random):
                try:
                    inventory[f"{mod_name}.{attr}"] = value.getstate()
                except Exception:
                    continue
    return inventory


def test_read_invariant_full_core_and_rng_unchanged():
    from src.api import gui_query_api
    state, player_ids = _hotseat_population_session()
    store = GuiSessionStore(state)
    store.initialize(player_ids[0])

    # Detached canonical snapshot (deep copy) — immune to the shallow-copy
    # aliasing inside GameState.to_dict (``_phase_results.copy()`` etc.).
    before = copy.deepcopy(state.to_dict())
    carriers_before = _carrier_snapshot(state)
    rng_inventory_before = _rng_inventory()

    # -- full Store read chain: 12 routes + filters + own detail --------------
    for query_id in gui_query_api.CANONICAL_QUERY_IDS:
        store.doGlobalQuery(query_id, "", "")
        store.doGlobalQuery(query_id, "zzz-no-match", "")
    figures = state.get_living_members()
    if figures:
        store.doGlobalQuery("figure_search", "", str(figures[0].id))

    # -- direct API routes + a foreign selector probe -------------------------
    for query_id in gui_query_api.CANONICAL_QUERY_IDS:
        gui_query_api.get_global_query_result(state, player_ids[0], query_id, "", "")
    if figures:
        gui_query_api.get_global_query_result(state, player_ids[0], "figure_search", "",
                                              str(figures[0].id))
        gui_query_api.get_global_query_result(state, player_ids[0], "figure_search", "",
                                              str(figures[-1].id))

    # -- failure / boundary routes (must not mutate Core either) ----------------
    store.doGlobalQuery("figure_search", "", "999999")   # record DENIED
    store.doGlobalQuery("not_a_query", "", "")            # unknown query
    gui_query_api.get_global_query_result(state, player_ids[0], "figure_search", "", "999999")
    gui_query_api.get_global_query_result(state, "ghost-player", "figure_search", "", "")

    after = copy.deepcopy(state.to_dict())
    carriers_after = _carrier_snapshot(state)
    rng_inventory_after = _rng_inventory()

    assert after == before
    assert carriers_after == carriers_before
    assert rng_inventory_after == rng_inventory_before
