"""EOR20261011-01 S1 — AC14 real Qt production handoff chain (A4).

Drives the REAL production GUI class and the REAL QML shell
(``src.ui.gui.app.GuiApp`` → ``Main.qml`` → ``GameShell`` →
``QueryResultOverlay`` / ``PlayerHandoffOverlay``):

A opens A's OWN sensitive ``figure_search`` result through the real bottom query
button + a real result-row click; then BOTH production viewer-mutation branches
run —
  * ``submitPopulationVotes`` awaiting branch, and
  * ``doCompletePlayer`` next-HUMAN branch —
and the player handoff is confirmed through the REAL QML PlayerHandoffOverlay
button (``guiApp.confirmHandoff`` → production ``GuiApp.confirmHandoff`` →
``store.switchViewer``).

The runtime uses the real ``GuiApp`` object (a thin ``_RecordingGuiApp`` subclass
that only ADDS an observation of ``confirmHandoff``) and replicates the exact
production signal wiring performed by ``GuiApp.run`` (``feedbackRaised`` /
``handoffRequired``), so the handoff overlay is shown by production code and the
confirm button invokes the production ``confirmHandoff``.

A4 evidence hardening (addresses SA-Verify ATTEMPT-3 F5/AC14 evidence gaps):
  * a UNIQUE sensitive sentinel (A's own private ``wealth``) is set and its
    ABSENCE is asserted across the temporal chain — at every
    ``queryResultChanged`` / ``snapshotChanged`` / ``handoffRequired`` /
    ``queryInvalidated`` callback — searching the Store DTO, the overlay's BOUND
    ``dto``/``items`` model, and all feedback payloads (not just ``dto_empty``);
  * the confirm click is OBSERVED to actually dispatch ``GuiApp.confirmHandoff``,
    advance an additional invalidation epoch, and trigger a POST-confirmation
    same-query reread (fixing the "already B before the click" tautology);
  * the final B surface is searched for the sentinel across Store + rendered UI +
    feedback payloads.

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
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from src.api import session_api
from src.core.entities.player import Player, PlayerType
from src.ui.gui.app import GuiApp
from src.ui.gui.localization import gui_localization

# A4 (AC14) — unique sensitive sentinel: A's own figure ``wealth``, a field that is
# foreign-private for every other viewer. It must be ABSENT across the temporal
# invalidation chain and in final B.
SENSITIVE_SENTINEL = 867530925


def _rng_isolated(fn):
    """Test-hygiene guard: restore the process RNG state after the wrapped test.

    These presentation-contract tests create real sessions (which draw from the
    global ``random`` module). Restoring the state keeps them transparent to the
    test-suite ordering — otherwise the extra draws perturb later, unrelated
    order-sensitive tests.
    """
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


class _RecordingGuiApp(GuiApp):
    """The REAL production app, with an observed ``confirmHandoff``.

    The only addition is a spy list: the confirm click's actual dispatch to
    ``GuiApp.confirmHandoff`` becomes machine-proven (not inferred from an
    already-B viewer). All behaviour delegates to the real production method.
    """

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

    # REAL production application object (owns the real GuiSessionStore).
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

    # Replicate the exact production wiring performed by ``GuiApp.run`` so the
    # real app methods drive the real QML (handoff overlay show + confirm).
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
    """All rendered Text/label contents currently in the live visual tree."""
    parts = []
    for item in _visual_items(runtime):
        try:
            txt = item.property("text")
        except Exception:
            continue
        if txt:
            parts.append(str(txt))
    return " ".join(parts)


def _open_query(runtime, query_id="figure_search"):
    _click(runtime, _find(runtime, f"queryButton_{query_id}"))
    overlay = _overlay(runtime)
    assert overlay.property("visible") is True
    assert runtime.store.globalQueryResult.get("id") == query_id


def _inject_sentinel(runtime, sentinel=SENSITIVE_SENTINEL):
    """Set the unique sensitive sentinel on A's OWN figure private wealth."""
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    figure = runtime.state.get_living_member(own_id)
    assert figure is not None
    figure.wealth = sentinel
    return own_id


def _click_own_row(runtime, own_id):
    """A real result-row click opens A's own detail (production entry)."""
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


def _open_own_detail(runtime):
    """Open A's own sensitive detail (query button + row click). Returns own_id."""
    _open_query(runtime, "figure_search")
    own_id = _inject_sentinel(runtime)
    _click_own_row(runtime, own_id)
    overlay = _overlay(runtime)
    assert overlay.property("visible") is True
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == "figure_search"
    assert dto.get("detail") is not None, "own detail did not open"
    assert dto["detail"]["record_id"] == str(own_id)
    field_keys = {f["label_key"] for f in dto["detail"]["fields"]}
    assert "query.figure.wealth" in field_keys  # OWN private block present
    assert str(SENSITIVE_SENTINEL) in _blob(dto), "sentinel absent from own detail"
    # The private value is ACTUALLY rendered in the live UI (so the later
    # rendered-tree absence check is meaningful, not vacuous).
    assert str(SENSITIVE_SENTINEL) in _rendered_text_blob(runtime), \
        "sentinel not rendered while own detail is open"
    return own_id


def _confirm_handoff(runtime):
    button = _find_by_text(runtime, "确认交接")
    assert button is not None, "real handoff confirm button not found"
    _click(runtime, button)


def _trace_new_viewer_reads(store):
    """Record every ``(viewer, query, filter, record)`` read-chain argument."""
    calls = []
    original = store._adapter.get_global_query_result

    def spy(viewer, query, filter_text, record_id):
        calls.append((viewer, query, filter_text, record_id))
        return original(viewer, query, filter_text, record_id)

    store._adapter.get_global_query_result = spy
    return calls


class _UIProbe:
    """Observes the invalidation temporal chain at EVERY relevant callback.

    At each ``queryResultChanged`` / ``snapshotChanged`` / ``handoffRequired`` /
    ``queryInvalidated`` it captures, from the LIVE store AND the bound QML model
    (the overlay's ``dto`` / ``items``) AND all feedback payloads, so a unique
    sensitive sentinel is proven ABSENT across the chain — not merely via a
    ``dto_empty`` shortcut. Also records whether every ``queryInvalidated`` saw an
    EMPTY Store (clear-before-publish).
    """

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
    """Shared AC14 body: open A's own sentinel detail, run ``branch``, assert the
    full temporal + confirmation evidence."""
    store = runtime.store
    app = runtime.gui_app
    overlay = _overlay(runtime)

    own_id = _open_own_detail(runtime)  # sentinel present in A's own private block

    reads = _trace_new_viewer_reads(store)
    probe = _UIProbe(runtime, SENSITIVE_SENTINEL)

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
    assert store.globalQueryResult.get("id") == "figure_search"
    assert store.globalQueryResult.get("detail") is None
    assert (new_viewer, "figure_search", "", "") in reads, reads

    # -- final B surface: sentinel absent from Store + rendered UI + feedbacks ----
    assert str(SENSITIVE_SENTINEL) not in _blob(store.globalQueryResult)
    assert str(SENSITIVE_SENTINEL) not in _rendered_text_blob(runtime)
    assert str(SENSITIVE_SENTINEL) not in _blob(probe.feedbacks)

    # -- production handoff overlay really shown and bound to B -------------------
    handoff = _handoff_overlay(runtime)
    assert handoff.property("visible") is True
    assert handoff.property("nextPlayerId") == new_viewer
    assert own_id != ""  # own detail was opened

    # -- confirm click: observed dispatch + extra epoch + POST-click reread -------
    epoch_before = store.queryInvalidationEpoch
    reads_before = len(reads)
    _confirm_handoff(runtime)

    assert app.confirm_calls == [new_viewer], app.confirm_calls
    assert store.queryInvalidationEpoch > epoch_before, "no extra invalidation epoch"
    post_reads = reads[reads_before:]
    assert (new_viewer, "figure_search", "", "") in post_reads, post_reads
    assert handoff.property("visible") is False
    assert store.viewerPlayerId == new_viewer
    assert str(SENSITIVE_SENTINEL) not in _rendered_text_blob(runtime)


def test_ac14_submit_population_votes_awaiting_branch(runtime_factory):
    runtime = runtime_factory()
    # PC02W TD-01 (2026-10-23): 本席位庆典前置（G1 per-actor gate），断言零变更。
    runtime.store._state.set_batch_completed(runtime.store.viewerPlayerId, True)
    _run_ac14_branch(runtime, lambda store: store.submitPopulationVotes({}))


def test_ac14_do_complete_player_next_human_branch(runtime_factory):
    runtime = runtime_factory()
    _run_ac14_branch(runtime, lambda store: store.doCompletePlayer())


def test_ac14_closed_on_entry_stays_closed(runtime_factory):
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


# ===========================================================================
# v1.3 presentation contract (AC-23/AC-24) — real QML, real gestures
# ===========================================================================
def _find_optional(runtime, object_name):
    for item in _visual_items(runtime):
        if item.objectName() == object_name:
            return item
    return runtime.window.findChild(QObject, object_name)


def _widen_own_name(runtime):
    """Make one OWN figure name long enough to guarantee a horizontally
    over-wide list row (no truncation -> the horizontal slider must appear)."""
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    figure = runtime.state.get_living_member(own_id)
    assert figure is not None
    figure.praenomen = "X" * 40
    figure.nomen = "Y" * 40
    figure.cognomen = "Z" * 40
    return own_id


@_rng_isolated
def test_ac23_dialog_geometry_and_two_axis_results_scroll(runtime_factory):
    runtime = runtime_factory()
    _widen_own_name(runtime)

    _open_query(runtime, "figure_search")
    dialog = _find(runtime, "queryResultDialog")
    # min(W-160, 720) x min(H-140, 560) at 1440x900 -> 720 x 560.
    assert abs(float(dialog.property("width")) - 720.0) <= 1.0
    assert abs(float(dialog.property("height")) - 560.0) <= 1.0

    # Exactly one results surface owns BOTH axes (vertical + horizontal AsNeeded).
    scroll = _find(runtime, "queryResultsScroll")
    vbar = _find(runtime, "queryResultsScrollBarV")
    hbar = _find(runtime, "queryResultsScrollBarH")
    assert vbar.property("asNeeded") is True
    assert hbar.property("asNeeded") is True

    content_w = float(scroll.property("contentWidth"))
    view_w = float(scroll.property("width"))
    assert content_w > view_w, (content_w, view_w)
    max_x = content_w - view_w
    assert float(scroll.property("contentX")) == 0.0
    # the horizontal extreme is reached by a REAL slider drag (no assignment)
    _drag_hbar(runtime, fraction=1.0)
    reachable = float(scroll.property("contentX"))
    assert reachable > 0.0
    assert abs(reachable - max_x) <= 1.0

    # Vertical growth is owned by the SAME surface.
    assert float(scroll.property("contentHeight")) >= float(scroll.property("height"))


@_rng_isolated
def test_ac24_action_row_close_right_no_clear_and_localized_label(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")
    dialog = _find(runtime, "queryResultDialog")

    # No Clear control exists anywhere.
    assert _find_optional(runtime, "queryClearButton") is None

    close_btn = _find(runtime, "queryCloseButton")
    back_btn = _find(runtime, "queryBackButton")
    assert close_btn.property("visible") is True    # available in every outcome
    assert back_btn.property("visible") is False    # list state -> Back hidden

    dlg_w = float(dialog.property("width"))
    dlg_h = float(dialog.property("height"))
    close_origin = close_btn.mapToItem(dialog, QPointF(0.0, 0.0))
    close_w = float(close_btn.property("width"))
    # Close sits in the bottom action row (not the header), on the RIGHT side.
    assert close_origin.y() > dlg_h * 0.5
    assert close_origin.x() + close_w > dlg_w * 0.5

    # The header contains no Close control.
    header = _find_optional(runtime, "queryResultHeader")
    assert header is not None
    pending = [header]
    close_in_header = False
    while pending:
        item = pending.pop()
        for child in item.childItems():
            if child.objectName() == "queryCloseButton":
                close_in_header = True
            pending.append(child)
    assert not close_in_header

    # Filter-row label localized; relabels live on locale switch.
    label = _find(runtime, "queryFilterLabel")
    assert label.property("text") == "按姓名查询"
    try:
        gui_localization.setLocale("en-US")
        _process_events()
        assert label.property("text") == "Search by name"
    finally:
        gui_localization.setLocale("zh-CN")
        _process_events()
    assert label.property("text") == "按姓名查询"


@_rng_isolated
def test_two_axis_reset_clears_both_content_axes(runtime_factory):
    runtime = runtime_factory()
    _widen_own_name(runtime)
    _open_query(runtime, "figure_search")
    scroll = _find(runtime, "queryResultsScroll")

    scroll.setProperty("contentX", 30.0)
    scroll.setProperty("contentY", 30.0)
    _process_events()
    assert float(scroll.property("contentX")) > 0.0
    assert float(scroll.property("contentY")) > 0.0

    # Public Close -> GameShell receiver resetForInvalidation resets BOTH axes.
    runtime.store.clearGlobalQuery()
    _process_events()
    assert float(scroll.property("contentX")) == 0.0
    assert float(scroll.property("contentY")) == 0.0


# ===========================================================================
# v1.4 — LIST = TABLE: one header row + value-only, column-aligned data rows
# =========================================================================
OWN_LIST_COLUMNS = [
    "col_status", "col_class", "col_id", "col_name", "col_faction",
    "col_influence", "col_wealth", "col_popularity", "col_land",
    "col_veterans", "col_office",
]
FOREIGN_LIST_COLUMNS = [
    "col_status", "col_class", "col_id", "col_name", "col_faction", "col_office",
]
FOREIGN_PRIVATE_COLUMNS = ["col_influence", "col_wealth", "col_popularity",
                           "col_land", "col_veterans"]


def _foreign_figure_id(state, viewer_id):
    faction_id = state.get_player(viewer_id).faction_id
    return next(fig.id for fig in state.get_living_members()
                if fig.faction_id and fig.faction_id != faction_id)


def _map_x(item, ancestor, dx=0.0):
    return float(item.mapToItem(ancestor, QPointF(dx, 0.0)).x())


def _header_cell(runtime, col_key):
    return _find_optional(runtime, "queryListHeaderCell_" + col_key)


def _row_cell(runtime, rec_id, col_key):
    return _find_optional(runtime, "queryListCell_%s_%s" % (rec_id, col_key))


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


@_rng_isolated
def test_list_header_row_present_and_absent_in_detail_empty_denied(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")

    headers = [it for it in _visual_items(runtime)
               if it.objectName() == "queryListHeaderRow"]
    assert len(headers) == 1, "exactly one header row"
    assert headers[0].property("visible") is True
    # header cells are the LOCALIZED captions (zh-CN default) in CLI order
    assert _find(runtime, "queryListHeaderLabel_col_status").property("text") == "状态"
    assert _find(runtime, "queryListHeaderLabel_col_name").property("text") == "姓名"
    assert _find(runtime, "queryListHeaderLabel_col_office").property("text") == "官职"

    # DETAIL (real own-row click) -> header hidden
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    _click_own_row(runtime, own_id)
    assert runtime.store.globalQueryResult.get("detail") is not None
    assert _find(runtime, "queryListHeaderRow").property("visible") is False

    # EMPTY (no-match filter) -> header hidden
    empty = runtime.store.doGlobalQuery("figure_search", "zzzz-no-match", "")
    assert empty["success"] is True
    _process_events()
    assert runtime.store.globalQueryResult.get("result_state") == "EMPTY"
    assert _find(runtime, "queryListHeaderRow").property("visible") is False

    # DENIED (absent selector) -> header hidden
    runtime.store.doGlobalQuery("figure_search", "", "999999")
    _process_events()
    assert runtime.store.globalQueryResult.get("result_state") == "DENIED"
    assert _find(runtime, "queryListHeaderRow").property("visible") is False


@_rng_isolated
def test_list_data_rows_are_value_only(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    figure = runtime.state.get_living_member(own_id)

    header_text = _find(runtime, "queryListHeaderLabel_col_name").property("text")
    assert header_text == "姓名"

    cell = _row_cell(runtime, own_id, "col_name")
    assert cell is not None
    value_text = _find(runtime, "queryListValue_%s_col_name" % own_id).property("text")
    assert value_text == figure.get_formal_name()
    # the data cell renders the VALUE only (one text) - never a repeated label
    assert _child_texts(cell) == [figure.get_formal_name()]
    assert header_text not in _child_texts(cell)


@_rng_isolated
def test_list_column_tracks_aligned_header_and_rows(runtime_factory):
    runtime = runtime_factory()
    _open_query(runtime, "figure_search")
    column = _find(runtime, "queryResultContentColumn")
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    foreign_id = _foreign_figure_id(runtime.state, runtime.viewer_id)

    # column j begins at the identical x (and has the identical track width) in
    # the header row and in every OWN data row
    for ck in OWN_LIST_COLUMNS:
        header = _header_cell(runtime, ck)
        data = _row_cell(runtime, own_id, ck)
        assert header is not None and data is not None, ck
        assert abs(_map_x(header, column) - _map_x(data, column)) <= 1.0, ck
        assert abs(float(header.property("width"))
                   - float(data.property("width"))) <= 1.0, ck

    # a FOREIGN row keeps the public columns aligned under their header
    for ck in FOREIGN_LIST_COLUMNS:
        header = _header_cell(runtime, ck)
        data = _row_cell(runtime, foreign_id, ck)
        assert header is not None and data is not None, ck
        assert abs(_map_x(header, column) - _map_x(data, column)) <= 1.0, ck


@_rng_isolated
def test_list_header_and_rows_co_scroll_together(runtime_factory):
    runtime = runtime_factory()
    _widen_own_name(runtime)
    _open_query(runtime, "figure_search")
    scroll = _find(runtime, "queryResultsScroll")
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    header = _header_cell(runtime, "col_name")
    data = _row_cell(runtime, own_id, "col_name")
    assert header is not None and data is not None

    hx0 = _map_x(header, scroll)
    dx0 = _map_x(data, scroll)
    x0 = float(scroll.property("contentX"))
    assert x0 == 0.0
    # REAL horizontal drag on the resultsScroll slider handle (never assigns
    # contentX): press / move / release part-way along the track.
    _drag_hbar(runtime, fraction=0.5)
    assert float(scroll.property("contentX")) > x0 + 1.0, \
        "the real drag did not change contentX"
    hx1 = _map_x(header, scroll)
    dx1 = _map_x(data, scroll)

    # the header and the data rows translate by the IDENTICAL contentX (no shift)
    assert abs((hx0 - hx1) - (dx0 - dx1)) <= 1.0
    assert abs(hx1 - dx1) <= 1.0
    assert hx1 < hx0, "the horizontal drag did not move the content"


@_rng_isolated
def test_list_last_column_reachable_by_horizontal_drag(runtime_factory):
    runtime = runtime_factory()
    _widen_own_name(runtime)
    _open_query(runtime, "figure_search")
    own_id = _own_figure_id(runtime.state, runtime.viewer_id)
    scroll = _find(runtime, "queryResultsScroll")
    hbar = _find(runtime, "queryResultsScrollBarH")
    content_w = float(scroll.property("contentWidth"))
    view_w = float(scroll.property("width"))
    assert content_w > view_w
    # overflow slider is VISIBLE (AsNeeded + overflow) and fixed controls are
    # stationary across contentX
    assert hbar.property("visible") is True
    close_btn = _find(runtime, "queryCloseButton")
    dialog = _find(runtime, "queryResultDialog")
    label = _find(runtime, "queryFilterLabel")
    fixed_before = [_scene_xy(close_btn), _scene_xy(dialog), _scene_xy(label)]

    assert float(scroll.property("contentX")) == 0.0
    # REAL drag to the far right (no contentX assignment)
    _drag_hbar(runtime, fraction=1.0)

    reachable = float(scroll.property("contentX"))
    assert reachable > 0.0
    assert abs(reachable - (content_w - view_w)) <= 1.0, (reachable, content_w - view_w)

    for cell in (_header_cell(runtime, "col_office"),
                 _row_cell(runtime, own_id, "col_office")):
        assert cell is not None
        left = _map_x(cell, scroll)
        right = _map_x(cell, scroll, float(cell.property("width")))
        assert left >= -1.0, left
        assert right <= view_w + 1.0, right      # fully reachable, no truncation

    # fixed controls (Close / dialog / filter label) did not move
    fixed_after = [_scene_xy(close_btn), _scene_xy(dialog), _scene_xy(label)]
    for (bx, by), (ax, ay) in zip(fixed_before, fixed_after):
        assert abs(bx - ax) <= 1.0 and abs(by - ay) <= 1.0, (fixed_before, fixed_after)


@_rng_isolated
def test_list_leader_badge_marked_own_and_foreign(runtime_factory):
    runtime = runtime_factory()
    state = runtime.state
    faction_id = state.get_player(runtime.viewer_id).faction_id
    figures = list(state.get_living_members())
    own = next(f for f in figures if f.faction_id == faction_id)
    foreign = next(f for f in figures if f.faction_id and f.faction_id != faction_id)
    non_leader = next(f for f in figures if f is not own and f is not foreign)
    own.is_faction_leader = True
    foreign.is_faction_leader = True
    non_leader.is_faction_leader = False

    _open_query(runtime, "figure_search")
    # EACH faction's leader is marked (own AND foreign); non-leaders are unmarked.
    assert _find(runtime, "queryListValue_%s_col_status" % own.id).property("text") == "领袖"
    assert _find(runtime, "queryListValue_%s_col_status" % foreign.id).property("text") == "领袖"
    assert _find(runtime, "queryListValue_%s_col_status" % non_leader.id).property("text") == ""


@_rng_isolated
def test_list_foreign_private_cells_absent(runtime_factory):
    runtime = runtime_factory()
    state = runtime.state
    foreign_id = _foreign_figure_id(state, runtime.viewer_id)
    foreign = state.get_living_member(foreign_id)
    foreign.wealth = 246810
    foreign.influence = 135791

    _open_query(runtime, "figure_search")

    # OWN_PRIVATE columns are ABSENT for a FOREIGN row (no cell, no value, no
    # placeholder) - placement is by track index so the public columns stay aligned
    for ck in FOREIGN_PRIVATE_COLUMNS:
        assert _row_cell(runtime, foreign_id, ck) is None, ck
        assert _find_optional(
            runtime, "queryListValue_%s_%s" % (foreign_id, ck)) is None, ck
    for ck in FOREIGN_LIST_COLUMNS:
        assert _row_cell(runtime, foreign_id, ck) is not None, ck

    blob = _rendered_text_blob(runtime)
    assert "246810" not in blob
    assert "135791" not in blob


# ===========================================================================
# A6-V01 (ATTEMPT-7) — legacy NON-TABULAR row rendering (production entry)
# + A6-V02 (ATTEMPT-7) — REAL horizontal slider drag (no contentX assignment)
# ===========================================================================
def _scene_xy(item):
    point = item.mapToScene(QPointF(0.0, 0.0))
    return (round(point.x(), 2), round(point.y(), 2))


def _resolve_param(value):
    """Python mirror of GuiText.queryValueParam (keyed refs / lists / scalars)."""
    if value is None:
        return ""
    if isinstance(value, list):
        return gui_localization.text("query.list.separator").join(
            _resolve_param(v) for v in value)
    if isinstance(value, dict) and "key" in value:
        params = {k: _resolve_param(v) for k, v in value.items() if k != "key"}
        return gui_localization.textParams(value["key"], params)
    return value


def _resolve_query_value(item):
    """Python mirror of GuiText.queryValue for a list/detail item."""
    if item.get("value_key"):
        params = {k: _resolve_param(v)
                  for k, v in (item.get("value_params") or {}).items()}
        resolved = gui_localization.textParams(item["value_key"], params)
        if resolved != item["value_key"]:
            return resolved
        return gui_localization.text("query.value.unknown")
    return item.get("value", "")


def _legacy_row_values(runtime):
    """(label_key, rendered value text) for every NON-TABULAR legacy row.

    Returned in DOCUMENT (list) order via the delegate index in the objectName.
    """
    rows = []
    prefix = "queryRowValue_"
    for item in _visual_items(runtime):
        name = item.objectName()
        if name.startswith(prefix):
            rows.append((int(name[len(prefix):]),
                         str(item.property("labelKey") or ""),
                         str(item.property("text") or "")))
    rows.sort(key=lambda entry: entry[0])
    return [(label_key, text) for _index, label_key, text in rows]


def _drag_hbar(runtime, fraction=1.0, steps=10):
    """REAL horizontal drag of the resultsScroll horizontal slider handle.

    Press/move/release the ScrollBar handle along the track; NEVER assigns
    ``contentX`` (or ``position``) directly. ``fraction`` 0..1 is the target
    handle offset across the draggable track (1.0 = far right = max contentX).
    """
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


@_rng_isolated
def test_game_status_non_tabular_values_rendered(runtime_factory):
    """A6-V01: opening the already-real game_status through the production
    bottom-bar entry renders the CURRENT-STATE values (label + value) as visible
    text, NOT blank rows. API-only DTO assertions cannot catch this regression."""
    runtime = runtime_factory()
    _open_query(runtime, "game_status")          # real bottom-bar button click
    overlay = _overlay(runtime)
    assert overlay.property("visible") is True
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == "game_status"
    assert dto.get("result_state") == "OK"
    # a non-tabular list never renders the table header row
    assert _find(runtime, "queryListHeaderRow").property("visible") is False

    expected = {it["label_key"]: _resolve_query_value(it) for it in dto["items"]}
    rendered = dict(_legacy_row_values(runtime))
    assert rendered == expected, (rendered, expected)
    assert len(rendered) == 7
    for key, value in rendered.items():
        assert value.strip() != "", (key, "blank value")

    # the seven values are the REAL current-state values (not placeholders)
    state = runtime.state
    turn = state.turn
    assert expected["query.item.turn"] == str(turn.turn_number)
    assert expected["query.item.treasury"] == "%s T" % state.treasury
    assert expected["query.item.living_members"] == str(len(state.get_living_members()))
    assert expected["query.item.factions"] == str(len(state.get_active_factions()))
    assert expected["query.item.current_phase"] == gui_localization.text(
        "query.phase." + dto["summary"]["current_phase_id"])

    # the values are actually PAINTED (present in the live rendered text tree)
    blob = _rendered_text_blob(runtime)
    for value in expected.values():
        assert value in blob, (value, "not rendered")


@_rng_isolated
def test_original_lists_non_tabular_values_rendered(runtime_factory):
    """A6-V01: the other original non-tabular lists (faction_info /
    legion_status) render every row's value; an EMPTY list renders the empty
    body with NO blank rows and no table header."""
    runtime = runtime_factory()

    _open_query(runtime, "faction_info")
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == "faction_info"
    assert dto.get("result_state") == "OK"
    assert _find(runtime, "queryListHeaderRow").property("visible") is False
    expected = [_resolve_query_value(it) for it in dto["items"]]
    rendered = [value for _lk, value in _legacy_row_values(runtime)]
    assert rendered == expected, (rendered, expected)
    assert rendered and all(value.strip() for value in rendered)
    treasury = runtime.state.get_faction(
        runtime.state.get_player(runtime.viewer_id).faction_id).treasury
    assert "%s T" % treasury in rendered

    # close (production Close path) so the next real bottom-bar click is not
    # intercepted by the open overlay scrim, then open the next list.
    runtime.store.clearGlobalQuery()
    _process_events()
    _open_query(runtime, "legion_status")
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == "legion_status"
    assert dto.get("result_state") == "OK"
    assert _find(runtime, "queryListHeaderRow").property("visible") is False
    expected = [_resolve_query_value(it) for it in dto["items"]]
    rendered = [value for _lk, value in _legacy_row_values(runtime)]
    assert rendered == expected, (rendered[:5], expected[:5])
    assert len(rendered) == len(dto["items"]) > 0
    assert all(value.strip() for value in rendered)

    # war_list is EMPTY in this fixture: empty body, no legacy rows, no header
    runtime.store.clearGlobalQuery()
    _process_events()
    _open_query(runtime, "war_list")
    dto = runtime.store.globalQueryResult
    assert dto.get("id") == "war_list"
    assert dto.get("result_state") == "EMPTY"
    assert _legacy_row_values(runtime) == []
    assert _find(runtime, "queryListHeaderRow").property("visible") is False


@_rng_isolated
def test_list_real_horizontal_drag_localized_long_header_value(runtime_factory):
    """A6-V02: a REAL slider drag reaches the last column under a localized
    long-header/value case (en-US captions are longer than zh-CN), with the
    header + data translating by the identical contentX."""
    runtime = runtime_factory()
    _widen_own_name(runtime)
    try:
        gui_localization.setLocale("en-US")
        _process_events()
        _open_query(runtime, "figure_search")
        scroll = _find(runtime, "queryResultsScroll")
        hbar = _find(runtime, "queryResultsScrollBarH")
        own_id = _own_figure_id(runtime.state, runtime.viewer_id)
        # localized (English) header caption for the last column
        assert _find(runtime,
                     "queryListHeaderLabel_col_office").property("text") == "Office"
        content_w = float(scroll.property("contentWidth"))
        view_w = float(scroll.property("width"))
        assert content_w > view_w, (content_w, view_w)
        assert hbar.property("visible") is True

        header = _header_cell(runtime, "col_office")
        data = _row_cell(runtime, own_id, "col_office")
        hx0 = _map_x(header, scroll)
        dx0 = _map_x(data, scroll)
        assert float(scroll.property("contentX")) == 0.0
        _drag_hbar(runtime, fraction=1.0)          # real drag, no assignment
        assert float(scroll.property("contentX")) > 0.0
        hx1 = _map_x(header, scroll)
        dx1 = _map_x(data, scroll)
        assert abs((hx0 - hx1) - (dx0 - dx1)) <= 1.0
        assert abs(hx1 - dx1) <= 1.0
        for cell in (header, data):
            left = _map_x(cell, scroll)
            right = _map_x(cell, scroll, float(cell.property("width")))
            assert left >= -1.0, left
            assert right <= view_w + 1.0, right
    finally:
        gui_localization.setLocale("zh-CN")
        _process_events()
