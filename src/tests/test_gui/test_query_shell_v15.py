"""EOR20261011-01 S1 v1.5 — Q6 single status + wording; Q7 loop-free track widths.

Drives the REAL production GUI class and the REAL QML shell
(``src.ui.gui.app.GuiApp`` -> ``Main.qml`` -> ``GameShell`` ->
``QueryResultOverlay``) headlessly (offscreen).

Q6 (single status + wording, FC-23 / G16):
  * the DTO status sentence is rendered EXACTLY ONCE — in the fixed h36
    ``queryStatusText`` frame OUTSIDE ``resultsScroll``; the former in-scroll
    duplicate (``queryStatusFull``) is GONE, and the empty/denied body line never
    repeats the status sentence (record-DENIED body suppressed);
  * the figure_search status copy equals the localized value of
    ``query.figure_search.message`` in the active locale (zh / en).

Q7 (loop-free shared tracks, FC-17 / G17):
  * the running app emits ZERO ``Binding loop detected for property
    "trackWidths"`` warnings across open / filter / detail / back / close /
    locale-switch / window-resize;
  * the header row and every data row share identical column tracks (±1px).
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
from PySide6.QtCore import (
    QObject, QPoint, QPointF, QSize, Qt, QUrl, Slot, qInstallMessageHandler,
)
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem  # noqa: F401  (registers QQuickWindow typing)
from PySide6.QtTest import QTest

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.app import GuiApp
from src.ui.gui.localization import gui_localization

# The Owner-frozen wording for the single status key ``query.figure_search.message``.
FIGURE_SEARCH_MSG_ZH = "仅显示当前玩家派系的人物详细信息"
FIGURE_SEARCH_MSG_EN = (
    "Only detailed information for the current player's faction characters is shown."
)
# ``query.error.record_unavailable`` / ``query.record.denied`` share this copy.
DENIED_SENTENCE_ZH = "该记录不可用"


def _rng_isolated(fn):
    """Restore the process RNG state after the wrapped test (suite determinism):
    these presentation tests build real sessions which draw from ``random``."""
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


def _own_figure_id(state, viewer_id):
    faction_id = state.get_player(viewer_id).faction_id
    return next(fig.id for fig in state.get_living_members()
                if fig.faction_id == faction_id)


def _widen_own_name(runtime):
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    figure = runtime.state.get_living_member(own_id)
    assert figure is not None
    figure.praenomen = "X" * 40
    figure.nomen = "Y" * 40
    figure.cognomen = "Z" * 40
    return own_id


# ===========================================================================
# Qt warning capture (QML binding-loop detection) — non-vacuous (see control)
# ===========================================================================
class _QmlWarningCapture:
    """Collect EVERY Qt log message emitted while active (QML binding-loop
    detection is reported through the Qt message handler) plus the engine's own
    ``warnings`` signal, so a capture is not vacuously empty."""

    def __init__(self):
        self.messages = []
        self._prev = None

    def __enter__(self):
        self._prev = qInstallMessageHandler(self._on_message)
        return self

    def __exit__(self, *exc):
        try:
            qInstallMessageHandler(self._prev)
        except Exception:
            pass
        return False

    def _on_message(self, mode, context, message):
        try:
            self.messages.append(str(message))
        except Exception:
            pass

    def add_engine_warnings(self, warnings):
        for warning in warnings:
            try:
                self.messages.append(warning.toString())
            except Exception:
                pass

    def binding_loops(self):
        return [m for m in self.messages if "Binding loop" in m]

    def trackwidths_loops(self):
        return [m for m in self.messages
                if "Binding loop" in m and "trackWidths" in m]


# A deliberate, self-contained cyclic binding (control): the engine MUST report a
# binding loop for it, proving the capture is live (not vacuously empty).
_CONTROL_LOOP_QML = b"""
import QtQuick 2.15
Item {
    property int a: b + 1
    property int b: a + 1
    Component.onCompleted: { var _x = a }
}
"""


class _Runtime:
    def __init__(self, engine, window, state, store, viewer_id, player_ids):
        self.engine = engine
        self.window = window
        self.state = state
        self.store = store
        self.viewer_id = viewer_id
        self.player_ids = player_ids

    def close(self):
        self.window.close()
        _process_events(1)
        self.engine.deleteLater()
        _process_events(1)


def _build_runtime(capture=None):
    _app()
    state, player_ids = _hotseat_population_state()

    gui_app = GuiApp(state)               # REAL production application object
    store = gui_app.get_store()
    store.initialize(player_ids[0])

    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    if capture is not None:
        engine.warnings.connect(capture.add_engine_warnings)

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

    return _Runtime(engine, window, state, store, player_ids[0], player_ids)


@pytest.fixture
def runtime_factory():
    runtimes = []

    def factory(capture=None):
        runtime = _build_runtime(capture)
        runtimes.append(runtime)
        return runtime

    yield factory
    for runtime in reversed(runtimes):
        runtime.close()


# -- tiny visual-tree helpers ------------------------------------------------
def _visual_items(runtime):
    pending = [runtime.window.contentItem()]
    while pending:
        item = pending.pop()
        yield item
        pending.extend(item.childItems())


def _find(runtime, object_name):
    item = next((c for c in _visual_items(runtime) if c.objectName() == object_name), None)
    if item is None:
        item = runtime.window.findChild(QObject, object_name)
    assert item is not None, f"{object_name} not found"
    return item


def _find_optional(runtime, object_name):
    for item in _visual_items(runtime):
        if item.objectName() == object_name:
            return item
    return runtime.window.findChild(QObject, object_name)


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


def _subtree_text_blob(root_item):
    parts = []
    pending = [root_item]
    while pending:
        item = pending.pop()
        try:
            txt = item.property("text")
        except Exception:
            txt = None
        if txt:
            parts.append(str(txt))
        pending.extend(item.childItems())
    return " ".join(parts)


def _overlay_blob(runtime):
    return _subtree_text_blob(_find(runtime, "queryResultOverlay"))


def _drag_hbar(runtime, fraction=1.0, steps=10):
    """REAL horizontal drag of the resultsScroll horizontal slider handle
    (press/move/release — NEVER assigns contentX/position)."""
    hbar = _find(runtime, "queryResultsScrollBarH")
    top_left = hbar.mapToScene(QPointF(0.0, 0.0))
    track_w = float(hbar.property("width"))
    handle_w = float(hbar.property("size")) * track_w
    handle_left = top_left.x() + float(hbar.property("position")) * track_w
    y = top_left.y() + float(hbar.property("height")) / 2.0
    start = QPointF(handle_left + handle_w / 2.0, y)
    target_left = top_left.x() + fraction * (track_w - handle_w)
    end = QPointF(target_left + handle_w / 2.0, y)
    QTest.mousePress(runtime.window, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, start.toPoint())
    for step in range(1, steps + 1):
        f = step / float(steps)
        point = QPointF(start.x() + (end.x() - start.x()) * f, y)
        QTest.mouseMove(runtime.window, point.toPoint())
        _process_events(1)
    QTest.mouseRelease(runtime.window, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, end.toPoint())
    _process_events()
    return start, end


def _open_query(runtime, query_id="figure_search"):
    _click(runtime, _find(runtime, "queryButton_" + query_id))
    overlay = _overlay(runtime)
    assert overlay.property("visible") is True
    assert runtime.store.globalQueryResult.get("id") == query_id
    return overlay


def _click_own_row(runtime, own_id):
    row = None
    for item in _visual_items(runtime):
        if item.objectName() == f"queryRow_{own_id}":
            row = item
            break
    assert row is not None, f"own figure row queryRow_{own_id} not found"
    scroll = _find(runtime, "queryResultsScroll")
    column = _find(runtime, "queryResultContentColumn")
    y = row.mapToItem(column, QPointF(0.0, 0.0)).y()
    scroll.setProperty("contentY", max(0.0, y - 40.0))
    _process_events()
    _click(runtime, row)
    return row


def _child_texts(item):
    out = []
    pending = list(item.childItems())
    while pending:
        it = pending.pop()
        try:
            txt = it.property("text")
        except Exception:
            txt = None
        if txt is not None and str(txt) != "":
            out.append(str(txt))
        pending.extend(it.childItems())
    return out


def _map_x(item, ancestor, dx=0.0):
    return float(item.mapToItem(ancestor, QPointF(dx, 0.0)).x())


def _header_cell(runtime, col_key):
    return _find_optional(runtime, "queryListHeaderCell_" + col_key)


def _row_cell(runtime, rec_id, col_key):
    return _find_optional(runtime, "queryListCell_%s_%s" % (rec_id, col_key))


def _legacy_row_values(runtime):
    rows = []
    prefix = "queryRowValue_"
    for item in _visual_items(runtime):
        name = item.objectName()
        if name.startswith(prefix):
            rows.append((int(name[len(prefix):]), str(item.property("text") or "")))
    rows.sort(key=lambda entry: entry[0])
    return [value for _index, value in rows]


OWN_LIST_COLUMNS = [
    "col_status", "col_class", "col_id", "col_name", "col_faction",
    "col_influence", "col_wealth", "col_popularity", "col_land",
    "col_veterans", "col_office",
]


# ===========================================================================
# Control — the capture actually observes a binding loop (non-vacuous)
# ===========================================================================
def test_warning_capture_control_detects_a_binding_loop():
    """Prove the Qt warning capture is LIVE: a deliberately cyclic QML component
    MUST yield a 'Binding loop detected' message through the installed handler.
    Without this, '0 trackWidths loops' could be a vacuous green."""
    _app()
    capture = _QmlWarningCapture()
    with capture:
        engine = QQmlApplicationEngine()
        engine.addImportPath(os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml"))
        component = QQmlComponent(engine)
        component.setData(_CONTROL_LOOP_QML, QUrl("control_loop.qml"))
        obj = component.create()
        _process_events(2)
        if obj is not None:
            obj.deleteLater()
        engine.deleteLater()
        _process_events(1)
    assert capture.binding_loops(), (
        "the warning capture did not observe a known binding loop: %r"
        % (capture.messages[:20],)
    )


# ===========================================================================
# Q7 — ZERO ``trackWidths`` binding-loop warnings across the full flow
# ===========================================================================
@_rng_isolated
def test_q7_zero_trackwidths_binding_loop_across_flows(runtime_factory):
    capture = _QmlWarningCapture()
    with capture:
        runtime = runtime_factory(capture)
        store = runtime.store

        # -- open (real bottom-bar click) -----------------------------------
        _open_query(runtime, "figure_search")

        # -- detail (real own-row click) + back (real Back click) -----------
        own_id = _own_figure_id(runtime.state, runtime.viewer_id)
        _click_own_row(runtime, own_id)
        assert store.globalQueryResult.get("detail") is not None
        back = _find(runtime, "queryBackButton")
        assert back.property("visible") is True
        _click(runtime, back)
        assert store.globalQueryResult.get("detail") is None

        # -- filter (production Store re-query -> DTO change) ---------------
        store.doGlobalQuery("figure_search", "zzz-no-match", "")
        _process_events()
        assert store.globalQueryResult.get("result_state") == "EMPTY"
        store.doGlobalQuery("figure_search", "", "")
        _process_events()

        # -- locale switch (zh -> en -> zh) ---------------------------------
        try:
            gui_localization.setLocale("en-US")
            _process_events()
            gui_localization.setLocale("zh-CN")
            _process_events()
        finally:
            gui_localization.setLocale("zh-CN")
            _process_events()

        # -- horizontal-overflow stress: widen a name + real slider drag ----
        _widen_own_name(runtime)
        store.doGlobalQuery("figure_search", "", "")
        _process_events()
        _drag_hbar(runtime, fraction=1.0)

        # -- window resize (dialog geometry changes with the viewport) ------
        runtime.window.resize(QSize(1280, 720))
        _process_events()
        runtime.window.resize(QSize(1440, 900))
        _process_events()

        # -- close (real Close click) ---------------------------------------
        _click(runtime, _find(runtime, "queryCloseButton"))
        assert _overlay(runtime).property("visible") is False

        # -- reopen + close via the real bottom bar again -------------------
        _open_query(runtime, "figure_search")
        _click(runtime, _find(runtime, "queryCloseButton"))

    assert capture.trackwidths_loops() == [], capture.trackwidths_loops()[:10]


@_rng_isolated
def test_q7_zero_trackwidths_loop_when_no_query_open_on_resize(runtime_factory):
    capture = _QmlWarningCapture()
    with capture:
        runtime = runtime_factory(capture)
        for size in (QSize(1280, 720), QSize(1600, 950), QSize(1440, 900)):
            runtime.window.resize(size)
            _process_events()
    assert capture.trackwidths_loops() == [], capture.trackwidths_loops()[:10]


# ===========================================================================
# Q6 — single status surface + wording
# ===========================================================================
@_rng_isolated
def test_q6_status_sentence_rendered_exactly_once(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")

    # the in-scroll duplicate no longer exists anywhere
    assert _find_optional(runtime, "queryStatusFull") is None
    # the fixed h36 status frame is the ONE status surface
    status = _find(runtime, "queryStatusText")
    assert status.property("text") == FIGURE_SEARCH_MSG_ZH
    frame = status.parentItem()
    assert abs(float(frame.property("height")) - 36.0) <= 1.0

    blob = _rendered_text_blob(runtime)
    assert blob.count(FIGURE_SEARCH_MSG_ZH) == 1, blob
    # no second render of root.messageText anywhere
    full = sum(1 for it in _visual_items(runtime)
               if it.property("text") == FIGURE_SEARCH_MSG_ZH)
    assert full == 1, full


@_rng_isolated
def test_q6_record_denied_body_does_not_repeat_status(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")

    # absent selector -> generic record-DENIED shell, window stays open
    runtime.store.doGlobalQuery("figure_search", "", "999999")
    _process_events()
    assert runtime.store.globalQueryResult.get("result_state") == "DENIED"

    status = _find(runtime, "queryStatusText")
    assert status.property("text") == DENIED_SENTENCE_ZH
    body = _find(runtime, "queryResultBodyText")
    assert body.property("visible") is False

    # count INSIDE the dialog only (the feedback panel is a separate surface)
    overlay_blob = _overlay_blob(runtime)
    assert overlay_blob.count(DENIED_SENTENCE_ZH) == 1, overlay_blob


@_rng_isolated
def test_q6_empty_body_keeps_its_own_copy(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")
    runtime.store.doGlobalQuery("figure_search", "zzz-no-match", "")
    _process_events()
    assert runtime.store.globalQueryResult.get("result_state") == "EMPTY"

    status = _find(runtime, "queryStatusText")
    assert status.property("text") == FIGURE_SEARCH_MSG_ZH
    # the empty body is a DISTINCT body copy, never a second status sentence
    body = _find(runtime, "queryResultBodyText")
    assert body.property("text") != FIGURE_SEARCH_MSG_ZH
    overlay_blob = _overlay_blob(runtime)
    assert overlay_blob.count(FIGURE_SEARCH_MSG_ZH) == 1, overlay_blob


@_rng_isolated
def test_q6_wording_localized_zh_and_en(runtime_factory):
    runtime = runtime_factory()
    try:
        gui_localization.setLocale("zh-CN")
        _process_events()
        _open_query(runtime, "figure_search")
        status = _find(runtime, "queryStatusText")
        assert status.property("text") == FIGURE_SEARCH_MSG_ZH

        # locale switch re-resolves the SAME key in place (no restart)
        gui_localization.setLocale("en-US")
        _process_events()
        assert status.property("text") == FIGURE_SEARCH_MSG_EN
        overlay_blob = _overlay_blob(runtime)
        assert overlay_blob.count(FIGURE_SEARCH_MSG_EN) == 1, overlay_blob

        gui_localization.setLocale("zh-CN")
        _process_events()
        assert status.property("text") == FIGURE_SEARCH_MSG_ZH
    finally:
        gui_localization.setLocale("zh-CN")
        _process_events()


@_rng_isolated
def test_q6_catalog_value_is_the_frozen_sentence():
    """The catalog is the display authority: both locales carry the frozen value."""
    for locale, expected in (("zh-CN", FIGURE_SEARCH_MSG_ZH),
                             ("en-US", FIGURE_SEARCH_MSG_EN)):
        path = os.path.join(PROJECT_ROOT, "data", "i18n", f"{locale}.json")
        with open(path, encoding="utf-8-sig") as fh:
            catalog = json.load(fh)
        assert catalog["query.figure_search.message"] == expected, locale


# ===========================================================================
# Q7/G15 — header + every data row share identical column tracks (±1px)
# ===========================================================================
@_rng_isolated
def test_q7_header_and_rows_share_identical_tracks(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")
    column = _find(runtime, "queryResultContentColumn")
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)

    tracks = {}
    for ck in OWN_LIST_COLUMNS:
        header = _header_cell(runtime, ck)
        data = _row_cell(runtime, own_id, ck)
        assert header is not None and data is not None, ck
        hw = float(header.property("width"))
        dw = float(data.property("width"))
        # non-vacuous: the shared tracks are really sized (>= the schema floor)
        assert hw >= 24.0 and dw >= 24.0, (ck, hw, dw)
        assert abs(hw - dw) <= 1.0, (ck, hw, dw)
        assert abs(_map_x(header, column) - _map_x(data, column)) <= 1.0, ck
        tracks[ck] = hw

    # non-vacuous: the whole table is at least the sum of its track floors
    assert sum(tracks.values()) >= 24 * len(OWN_LIST_COLUMNS)

    # the SAME tracks are consumed read-only across a locale switch (tracks are
    # recomputed once from the localized header captions -> still self-consistent)
    try:
        gui_localization.setLocale("en-US")
        _process_events()
        for ck in OWN_LIST_COLUMNS:
            header = _header_cell(runtime, ck)
            data = _row_cell(runtime, own_id, ck)
            assert header is not None and data is not None, ck
            assert abs(float(header.property("width"))
                       - float(data.property("width"))) <= 1.0, ck
            assert abs(_map_x(header, column) - _map_x(data, column)) <= 1.0, ck
    finally:
        gui_localization.setLocale("zh-CN")
        _process_events()


# ===========================================================================
# Q7 — overflow: widened content drives a shared track, slider reachable
# ===========================================================================
@_rng_isolated
def test_q7_widened_name_exposes_horizontal_scroll(runtime_factory):
    """A widened OWN name must widen the shared col_name track so the table
    overflows and the horizontal slider becomes reachable (real drag)."""
    runtime = runtime_factory()
    _widen_own_name(runtime)
    _open_query(runtime, "figure_search")
    scroll = _find(runtime, "queryResultsScroll")
    hbar = _find(runtime, "queryResultsScrollBarH")
    content_w = float(scroll.property("contentWidth"))
    view_w = float(scroll.property("width"))
    assert content_w > view_w, (content_w, view_w)
    assert hbar.property("visible") is True
    assert float(scroll.property("contentX")) == 0.0
    _drag_hbar(runtime, fraction=1.0)
    assert float(scroll.property("contentX")) > 0.0


# ===========================================================================
# Regression — the other real queries still render their content
# ===========================================================================
@_rng_isolated
def test_regression_other_queries_still_render_content(runtime_factory):
    runtime = runtime_factory()
    store = runtime.store

    for qid in ("game_status", "faction_info", "legion_status", "war_list"):
        _open_query(runtime, qid)
        dto = store.globalQueryResult
        assert dto.get("id") == qid
        # non-tabular queries never render the table header row
        assert _find(runtime, "queryListHeaderRow").property("visible") is False
        if dto.get("result_state") == "OK" and dto.get("items"):
            rendered = _legacy_row_values(runtime)
            assert len(rendered) == len(dto["items"]), qid
            assert all(value.strip() for value in rendered), qid
        else:
            # EMPTY: the body line renders (no blank rows, no header)
            assert _legacy_row_values(runtime) == [], qid
        # the dialog itself is meaningfully rendered (title present)
        blob = _rendered_text_blob(runtime)
        assert blob.strip() != "", qid
        store.clearGlobalQuery()
        _process_events()
