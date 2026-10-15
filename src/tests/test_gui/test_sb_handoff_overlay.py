"""EOR20261013-02 S-B Group 3 — handoff UI (reused PlayerHandoffOverlay) + GuiApp
barrier/witness provider wiring.

Group 3 requirements proven against the REAL production overlay QML:
  * pending copy is FACTION NAME ONLY (「下一位：<faction>」) — never a raw player id
    / player name / initials / "PL";
  * the primary activation button copy is 「接管」;
  * a NEUTRAL pluggable avatar/emblem slot exists inside the inherited layout (no
    letter, no asset);
  * the cover is FULLY OPAQUE (alpha == 1) and has a full-window input barrier;
  * clicking 「接管」 dispatches the Store takeover intent (not a raw id/token);
  * the legacy informational handoff (EOR20261011-01) is unchanged (确认交接).

The GuiApp provider methods (arm_barrier/show_pending/request_unmask/show_failure)
are the production barrier producer; a root stub records their dispatch.
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from PySide6.QtCore import QObject, QPointF, Qt, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest
from PySide6.QtQuick import QQuickItem

from src.api import session_api
from src.ui.gui.app import GuiApp
from src.ui.gui.session_store import GuiSessionStore

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")


@pytest.fixture(autouse=True)
def _restore_rng():
    """Keep these session-creating tests transparent to suite ordering."""
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _events(rounds=4):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)


class _StoreStub(QObject):
    def __init__(self):
        super().__init__()
        self.takeovers = 0
        self.retries = 0

    @Slot(result=dict)
    def requestTakeover(self):
        self.takeovers += 1
        return {"accepted": True}

    @Slot(result=dict)
    def retryHandoff(self):
        self.retries += 1
        return {"accepted": True}


class _AppStub(QObject):
    def __init__(self):
        super().__init__()
        self.confirms = []

    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id):
        self.confirms.append(next_player_id)
        return True


def _visual_items(item):
    pending = [item]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(node.childItems())


def _find(root, object_name):
    start = root.contentItem() if hasattr(root, "contentItem") else root
    for node in _visual_items(start):
        if node.objectName() == object_name:
            return node
    if hasattr(root, "findChild"):
        return root.findChild(QObject, object_name)
    return None


_WRAPPER = """
import QtQuick 2.15
import QtQuick.Window 2.15
import "shell"
Window {
    id: win
    width: 1440; height: 900
    visible: true
    PlayerHandoffOverlay { id: ov; anchors.fill: parent }
}
"""


@pytest.fixture
def overlay_runtime():
    _app()
    from PySide6.QtQml import QQmlApplicationEngine
    eng = QQmlApplicationEngine()
    eng.setOutputWarningsToStandardError(False)
    eng.addImportPath(QML_DIR)

    theme_component = QQmlComponent(eng)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()

    store_stub = _StoreStub()
    app_stub = _AppStub()
    eng.rootContext().setContextProperty("theme", theme)
    eng.rootContext().setContextProperty("sessionStore", store_stub)
    eng.rootContext().setContextProperty("guiApp", app_stub)

    comp = QQmlComponent(eng)
    comp.setData(_WRAPPER.encode("utf-8"),
                 QUrl.fromLocalFile(os.path.join(QML_DIR, "_sb_overlay_wrapper.qml")))
    assert not comp.isError(), comp.errorString()
    win = comp.create()
    assert win is not None
    _events()
    overlay = win.findChild(QObject, "playerHandoffOverlay")
    assert overlay is not None
    win._refs = (eng, theme, store_stub, app_stub, comp)
    yield win, overlay, store_stub, app_stub
    win.close()
    _events(1)


def test_pending_is_faction_name_only_and_button_is_takeover(overlay_runtime):
    win, overlay, store_stub, app_stub = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()

    assert overlay.property("visible") is True
    assert overlay.property("maskedMode") is True

    label = _find(win, "handoffPendingLabel")
    assert label is not None
    assert label.property("text") == "下一位：Optimates"
    assert "player_" not in label.property("text")

    button = _find(win, "grHandoffStart")
    assert button is not None
    assert button.property("text") == "接管"

    # primary button click dispatches the Store takeover intent (no raw token).
    point = button.mapToScene(QPointF(float(button.property("width")) / 2.0,
                                      float(button.property("height")) / 2.0))
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     point.toPoint())  # dispatch 接管
    _events()
    assert store_stub.takeovers == 1


def test_cover_is_fully_opaque_and_has_input_barrier(overlay_runtime):
    win, overlay, store_stub, app_stub = overlay_runtime
    overlay.showMaskedPending("Equites")
    _events()

    color = overlay.property("color")
    assert color.alpha() == 255, color.alpha()          # 100% opaque, no #CC hole
    barrier = _find(win, "handoffInputBarrier")
    assert barrier is not None
    assert abs(float(barrier.property("width")) - float(overlay.property("width"))) <= 1.0
    assert abs(float(barrier.property("height")) - float(overlay.property("height"))) <= 1.0


def test_neutral_avatar_slot_has_no_letter(overlay_runtime):
    win, overlay, store_stub, app_stub = overlay_runtime
    overlay.showMaskedPending("Populares")
    _events()
    slot = _find(win, "handoffAvatarSlot")
    assert slot is not None
    # No text (no ID-derived initials / "PL") anywhere inside the slot.
    for node in _visual_items(slot):
        try:
            text = node.property("text")
        except Exception:
            continue
        assert not text, f"avatar slot carries identifying text: {text!r}"


def test_busy_and_failure_states_are_neutral(overlay_runtime):
    win, overlay, store_stub, app_stub = overlay_runtime
    overlay.showMaskedBusy()
    _events()
    assert overlay.property("busy") is True
    # The primary 「接管」 stays in the inherited layout but is DISABLED while busy.
    assert _find(win, "grHandoffStart").property("enabled") is False

    overlay.showMaskedFailure("before_commit", "activation")
    _events()
    assert overlay.property("failureVisible") is True
    assert _find(win, "grHandoffRetry").property("visible") is True
    assert "player_" not in str(_find(win, "handoffFailureLabel").property("text"))


def test_legacy_mode_unchanged(overlay_runtime):
    win, overlay, store_stub, app_stub = overlay_runtime
    overlay.show("player_2")
    _events()
    assert overlay.property("nextPlayerId") == "player_2"
    assert _find(win, "grHandoffStart").property("text") == "确认交接"
    button = _find(win, "grHandoffStart")
    point = button.mapToScene(QPointF(float(button.property("width")) / 2.0,
                                      float(button.property("height")) / 2.0))
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     point.toPoint())
    _events()
    assert app_stub.confirms == ["player_2"]


# ===========================================================================
# GuiApp barrier/witness provider wiring (production producer)
# ===========================================================================
class _RootStub(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    def showHandoffBusy(self):
        self.calls.append("busy")

    def showHandoffPending(self, faction):
        self.calls.append(("pending", faction))

    def showHandoffFailure(self, kind, route):
        self.calls.append(("failure", kind, route))

    def hideHandoff(self):
        self.calls.append("hide")


def _gui_app():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"]
    return GuiApp(result["data"]["state"])


def test_gui_app_provider_methods_drive_root():
    app = _gui_app()
    root = _RootStub()
    app._root = root
    # F4 (R2 §4): arm_barrier / request_unmask can NEVER stand in for a rendered
    # frame, so the legacy synchronous form returns False (no synchronous
    # boolean true). The real gates are the *_async methods below.
    assert app.arm_barrier("t1") is False
    assert app.request_unmask("t1") is False
    assert app.show_pending("t1", "Optimates") is True
    assert app.show_failure("t1", "before_commit", "activation") is True
    assert root.calls == [("pending", "Optimates"), ("failure", "before_commit", "activation")]


def test_gui_app_provider_legacy_form_never_claims_a_frame():
    """The legacy synchronous barrier/unmask methods never claim a frame receipt."""
    app = _gui_app()
    app._root = _RootStub()
    assert app.arm_barrier("t") is False
    assert app.request_unmask("t") is False


def test_gui_app_confirm_handoff_false_while_pending():
    app = _gui_app()
    store = app.get_store()
    # Force the store into a masked pending lifecycle.
    pids = [p.player_id for p in store._state.get_all_players()]
    store.initialize(pids[0])
    store._seat_lifecycle = "MASKED_PENDING_HANDOFF"
    assert app.confirmHandoff(pids[1]) is False       # must not accept while pending


def test_gui_app_confirm_handoff_async_delegates():
    app = _gui_app()
    store = app.get_store()
    # No pending -> refused.
    assert app.confirmHandoffAsync("x") == {"accepted": False, "txn_id": "",
                                            "reason": "not_pending"}
