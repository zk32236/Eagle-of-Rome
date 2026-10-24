"""EOR20261011-01 S2 — AC-14 real Qt production handoff chain for an S2 query.

F4 (G5 SA-Verify ATTEMPT-1 finding): the S2 AC-14 evidence must exercise the REAL
approved production Qt path for a NONEMPTY own S2 sensitive result — not a
headless acknowledgement shim. This module drives the REAL production GUI class
and the REAL QML shell (``src.ui.gui.app.GuiApp`` -> ``Main.qml`` -> ``GameShell``
-> ``QueryResultOverlay`` / ``PlayerHandoffOverlay``):

A opens A's OWN sensitive ``private_land`` result through the real bottom query
button + a real result-row click; then BOTH production viewer-mutation branches
run —
  * ``submitPopulationVotes`` awaiting branch, and
  * ``doCompletePlayer`` next-HUMAN branch —
and the player handoff is confirmed through the REAL QML PlayerHandoffOverlay
button (``guiApp.confirmHandoff`` -> production ``GuiApp.confirmHandoff`` ->
``store.switchViewer``).

A UNIQUE sensitive sentinel (A's own private-land figure ``wealth``) is set and
its ABSENCE is asserted across the temporal chain — at every
``queryResultChanged`` / ``snapshotChanged`` / ``handoffRequired`` /
``queryInvalidated`` callback — searching the Store DTO, the overlay's BOUND
``dto`` / ``items`` model, and all feedback payloads; the confirm click is
OBSERVED to dispatch ``GuiApp.confirmHandoff``, advance an extra invalidation
epoch and trigger a POST-confirmation same-query reread; the final B surface is
searched for the sentinel and B exposes only B-authorised content.

Unreachable boundary (Owner AC-17 route): the full ``GuiApp.run()`` OS
event-loop/window interaction-wiring judgement is NOT headless-reachable and is
explicitly Owner-G7-scoped; the DATA-clearance guarantees here remain
machine-proven.
"""

import json
import os
import random
import sys
from functools import wraps

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, QSize, Qt, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem  # noqa: F401  (registers QQuickWindow typing)
from PySide6.QtTest import QTest

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.app import GuiApp
from src.ui.gui.localization import gui_localization

# A unique A-private sensitive sentinel: A's own private-land figure ``wealth``,
# a value foreign-private for every other viewer. It must be ABSENT across the
# temporal invalidation chain and in final B.
S2_SENTINEL = 867530926
S2_QUERY = "private_land"


def _rng_isolated(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        state = random.getstate()
        try:
            return fn(*args, **kwargs)
        finally:
            random.setstate(state)
    return _wrapped


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _process_events(rounds=6):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(10)


def _hotseat_population_state():
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


def _own_figure(state, viewer_id):
    faction_id = state.get_player(viewer_id).faction_id
    return next(fig for fig in state.get_living_members()
                if fig.faction_id == faction_id)


class _RecordingGuiApp(GuiApp):
    """The REAL production app, with an observed ``confirmHandoff``."""

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.confirm_calls = []

    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        self.confirm_calls.append(next_player_id)
        return super().confirmHandoff(next_player_id)


class _Runtime:
    def __init__(self, engine, window, state, store, gui_app, viewer_id, player_ids):
        self.engine = engine
        self.window = window
        self.state = state
        self.store = store
        self.gui_app = gui_app
        self.viewer_id = viewer_id
        self.player_ids = player_ids

    def close(self):
        self.window.close()
        _process_events(1)
        self.engine.deleteLater()
        _process_events(1)


def _build_runtime():
    _app()
    state, player_ids = _hotseat_population_state()

    gui_app = _RecordingGuiApp(state)
    store = gui_app.get_store()
    store.initialize(player_ids[0])

    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.setOutputWarningsToStandardError(False)
    engine.addImportPath(qml_dir)

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("localization", gui_localization)
    engine.rootContext().setContextProperty("guiApp", gui_app)
    engine._test_refs = (store, theme, gui_app)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    roots = engine.rootObjects()
    assert len(roots) == 1
    window = roots[0]
    assert isinstance(window, QWindow)
    window.resize(QSize(1440, 900))
    window.show()
    _process_events()
    assert window.isVisible()

    gui_app._engine = engine
    gui_app._root = window.findChild(QObject, "gameShell")
    assert gui_app._root is not None, "real gameShell not found"
    store.feedbackRaised.connect(gui_app._on_feedback)
    store.handoffRequired.connect(gui_app._on_handoff)

    return _Runtime(engine, window, state, store, gui_app, player_ids[0], player_ids)


def _visual_items(runtime):
    pending = [runtime.window.contentItem()]
    while pending:
        item = pending.pop()
        yield item
        pending.extend(item.childItems())


def _find(runtime, object_name):
    item = next(
        (c for c in _visual_items(runtime) if c.objectName() == object_name), None
    )
    if item is None:
        item = runtime.window.findChild(QObject, object_name)
    assert item is not None, f"{object_name} not found"
    return item


def _find_by_text(runtime, text):
    for item in _visual_items(runtime):
        try:
            value = item.property("text")
        except Exception:
            continue
        if value == text:
            return item
    return None


def _scene_center(item):
    width = float(item.property("width"))
    height = float(item.property("height"))
    assert width > 0 and height > 0
    point = item.mapToScene(QPointF(width / 2.0, height / 2.0))
    return QPoint(round(point.x()), round(point.y()))


def _click(runtime, item):
    point = _scene_center(item)
    assert 0 <= point.x() < runtime.window.width()
    assert 0 <= point.y() < runtime.window.height()
    QTest.mouseClick(runtime.window, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, point)
    _process_events()


def _overlay(runtime):
    return _find(runtime, "queryResultOverlay")


def _handoff_overlay(runtime):
    return _find(runtime, "playerHandoffOverlay")


def _qvar(value):
    if hasattr(value, "toVariant"):
        try:
            return value.toVariant()
        except Exception:
            return value
    return value


def _blob(value):
    try:
        return json.dumps(_qvar(value), ensure_ascii=False, default=str)
    except Exception:
        return repr(value)


def _rendered_text_blob(runtime):
    parts = []
    for item in _visual_items(runtime):
        try:
            txt = item.property("text")
        except Exception:
            continue
        if txt:
            parts.append(str(txt))
    return " ".join(parts)


def _click_own_row(runtime, own_id):
    row = None
    for item in _visual_items(runtime):
        if item.objectName() == f"queryRow_{own_id}":
            row = item
            break
    assert row is not None, f"own row queryRow_{own_id} not found"
    scroll = _find(runtime, "queryResultsScroll")
    column = _find(runtime, "queryResultContentColumn")
    y = row.mapToItem(column, QPointF(0.0, 0.0)).y()
    scroll.setProperty("contentY", max(0.0, y - 40.0))
    _process_events()
    _click(runtime, row)
    return row


def _open_own_private_land_detail(runtime):
    """Open A's own NONEMPTY sensitive private_land detail (query button + row
    click). Returns ``(own_fig_id, sentinel_present_in_own_detail)``."""
    state = runtime.state
    own = _own_figure(state, runtime.viewer_id)
    own._land_private = 7          # sanctioned fixture: gives A a landowner row
    own.wealth = S2_SENTINEL       # unique A-private sensitive value

    _click(runtime, _find(runtime, f"queryButton_{S2_QUERY}"))
    overlay = _overlay(runtime)
    assert overlay.property("visible") is True
    assert runtime.store.globalQueryResult.get("id") == S2_QUERY

    _click_own_row(runtime, own.id)
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == S2_QUERY
    assert dto.get("detail") is not None, "own private_land detail did not open"
    assert dto["detail"]["record_id"] == str(own.id)
    field_keys = {f["label_key"] for f in dto["detail"]["fields"]}
    assert "query.private_land.wealth" in field_keys  # OWN private block present
    assert str(S2_SENTINEL) in _blob(dto), "sentinel absent from own detail"
    # The private value is ACTUALLY rendered in the live UI (so the later
    # rendered-tree absence check is meaningful, not vacuous).
    assert str(S2_SENTINEL) in _rendered_text_blob(runtime), \
        "sentinel not rendered while own detail is open"
    return own.id


def _confirm_handoff(runtime):
    button = _find_by_text(runtime, "确认交接")
    assert button is not None, "real handoff confirm button not found"
    _click(runtime, button)


def _trace_new_viewer_reads(store):
    calls = []
    original = store._adapter.get_global_query_result

    def spy(viewer, query, filter_text, record_id):
        calls.append((viewer, query, filter_text, record_id))
        return original(viewer, query, filter_text, record_id)

    store._adapter.get_global_query_result = spy
    return calls


class _UIProbe:
    """Observes the invalidation temporal chain at EVERY relevant callback, from
    the LIVE store AND the bound QML model (overlay ``dto`` / ``items``) AND all
    feedback payloads."""

    def __init__(self, runtime, sentinel):
        self.runtime = runtime
        self.store = runtime.store
        self.overlay = _overlay(runtime)
        self.sentinel = str(sentinel)
        self.observations = []
        self.feedbacks = []
        self.violations = []
        store = self.store
        store.feedbackRaised.connect(self._on_feedback)
        store.queryResultChanged.connect(lambda: self._snap("queryResultChanged"))
        store.snapshotChanged.connect(lambda: self._snap("snapshotChanged"))
        store.handoffRequired.connect(lambda _id: self._snap("handoffRequired"))
        store.queryInvalidated.connect(lambda _k: self._snap("queryInvalidated"))

    def _on_feedback(self, ftype, fmsg):
        self.feedbacks.append([ftype, fmsg])

    def _snap(self, event):
        store_blob = _blob(self.store.globalQueryResult)
        try:
            bound_dto = _blob(self.overlay.property("dto"))
        except Exception:
            bound_dto = ""
        try:
            bound_items = _blob(self.overlay.property("items"))
        except Exception:
            bound_items = ""
        fb_blob = _blob(self.feedbacks)
        combined = " | ".join([store_blob, bound_dto, bound_items, fb_blob])
        self.observations.append({"event": event, "store": store_blob,
                                  "combined": combined})
        if self.sentinel in combined:
            self.violations.append({"event": event, "combined": combined})

    def events(self):
        return [o["event"] for o in self.observations]


@pytest.fixture
def runtime_factory():
    runtimes = []

    def factory():
        runtime = _build_runtime()
        runtimes.append(runtime)
        return runtime

    yield factory
    for runtime in reversed(runtimes):
        runtime.close()


def _run_ac14_branch(runtime, branch):
    store = runtime.store
    app = runtime.gui_app
    overlay = _overlay(runtime)

    own_id = _open_own_private_land_detail(runtime)  # sentinel in A's OWN block

    reads = _trace_new_viewer_reads(store)
    probe = _UIProbe(runtime, S2_SENTINEL)

    feedback = branch(store)
    assert feedback["success"], feedback.get("message")

    # -- temporal chain: every relevant callback observed and sentinel ABSENT ----
    events = probe.events()
    for expected in ("queryResultChanged", "snapshotChanged", "handoffRequired",
                     "queryInvalidated"):
        assert expected in events, f"callback {expected} not observed: {events}"
    assert not probe.violations, probe.violations
    assert all(o["store"] == "{}" for o in probe.observations
               if o["event"] == "queryInvalidated"), \
        "an invalidation saw a non-empty Store DTO"

    # -- B publication: only new-viewer content; old detail discarded; auto read --
    new_viewer = runtime.player_ids[1]
    assert store.viewerPlayerId == new_viewer
    assert overlay.property("visible") is True
    assert store.globalQueryResult.get("id") == S2_QUERY
    assert store.globalQueryResult.get("detail") is None
    assert (new_viewer, S2_QUERY, "", "") in reads, reads

    # -- final B surface: sentinel absent from Store + rendered UI + feedbacks ----
    assert str(S2_SENTINEL) not in _blob(store.globalQueryResult)
    assert str(S2_SENTINEL) not in _rendered_text_blob(runtime)
    assert str(S2_SENTINEL) not in _blob(probe.feedbacks)

    # -- B re-reads ONLY B-authorised content (B's own faction records) ----------
    b_faction = runtime.state.get_player(new_viewer).faction_id
    for item in store.globalQueryResult.get("items", []):
        rec = runtime.state.get_member(int(item["record_id"]))
        assert rec is not None and rec.faction_id == b_faction

    # -- production handoff overlay really shown and bound to B -------------------
    handoff = _handoff_overlay(runtime)
    assert handoff.property("visible") is True
    assert handoff.property("nextPlayerId") == new_viewer
    assert own_id != ""

    # -- confirm click: observed dispatch + extra epoch + POST-click reread -------
    epoch_before = store.queryInvalidationEpoch
    reads_before = len(reads)
    _confirm_handoff(runtime)

    assert app.confirm_calls == [new_viewer], app.confirm_calls
    assert store.queryInvalidationEpoch > epoch_before, "no extra invalidation epoch"
    post_reads = reads[reads_before:]
    assert (new_viewer, S2_QUERY, "", "") in post_reads, post_reads
    assert handoff.property("visible") is False
    assert store.viewerPlayerId == new_viewer
    assert str(S2_SENTINEL) not in _rendered_text_blob(runtime)


@_rng_isolated
def test_ac14_s2_submit_population_votes_awaiting_branch(runtime_factory):
    runtime = runtime_factory()
    # PC02W TD-01 (2026-10-23): 本席位庆典前置（G1 per-actor gate），断言零变更。
    runtime.store._state.set_batch_completed(runtime.store.viewerPlayerId, True)
    _run_ac14_branch(runtime, lambda store: store.submitPopulationVotes({}))


@_rng_isolated
def test_ac14_s2_do_complete_player_next_human_branch(runtime_factory):
    runtime = runtime_factory()
    _run_ac14_branch(runtime, lambda store: store.doCompletePlayer())


@_rng_isolated
def test_ac14_s2_closed_on_entry_stays_closed(runtime_factory):
    runtime = runtime_factory()
    store = runtime.store
    overlay = _overlay(runtime)

    assert overlay.property("visible") is False
    assert store.globalQueryResult == {}

    feedback = store.doCompletePlayer()

    assert feedback["success"], feedback.get("message")
    assert store.viewerPlayerId == runtime.player_ids[1]
    # CLOSED-on-entry stays CLOSED: no query window auto-opened.
    assert store.globalQueryResult == {}
    assert overlay.property("visible") is False
