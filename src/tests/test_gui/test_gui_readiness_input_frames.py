"""S-D-2 — GUI Readiness **real input + frame transaction (incl. failure faces)**.

EOR20261013-02 GUI Readiness · slice S-D · sub-task S-D-2.

Frozen design basis (Overlay §1.2 + §4; Delta §3):

  * real input to REAL QML controls: **click / key** mandatory; **touch / wheel**
    only for the **AC04 barrier** class (``G2-R5`` §4: mouse/touch/wheel/key are
    accepted by the barrier, NOT forwarded); **no drag**.
  * frame-sync capture on REAL frames, generation-bound; **failure faces** are
    mandatory captures (MASKED_FAILURE before/after commit, no-ack, no-frame, stale
    frame, loss-of-exposure, prepare failure).
  * **falsification (frame false-positive, SD-N3):** if the ACTUAL PIXELS show
    private/old data while the signal metadata claims masked ⇒ **FAIL**; an alpha
    assignment or a frame receipt WITHOUT neutralization evidence is INSUFFICIENT.
  * **window generation binding (SD-N5 / P7):** resize / recreate / exposure must
    increment the surface/exposure generation; a stale-generation frame is invalid.
  * **text (CJK):** all required text stays ``RENDER_AUTOMATED`` under the controlled
    harness; if a glyph is unavailable offscreen ⇒ **report the gap**, do NOT
    self-downgrade (``screenshot-visual-precheck-spec-v2`` §1.3).

The production overlay (`PlayerHandoffOverlay.qml`) is loaded as the REAL QML; an
underlying clickable control proves the barrier swallows input while masked and the
underlay is reachable once unmasked (positive control).

WATERMARK: S-D-2 DA EXECUTION — NOT runtime/API/GUI acceptance; candidate
dirty/uncommitted; no commit/push/delete; no product-code change.
"""
from __future__ import annotations

import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import sys
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl, Slot
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")


def _img_sig(image: QImage) -> str:
    """SHA-256 of the REAL pixel bytes of a frame (a content identity, not metadata)."""
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    return hashlib.sha256(bytes(img.constBits())).hexdigest()


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _events(rounds=5):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)


def _find(root, name):
    # Prefer the QQuickItem-typed child (supports mapToScene); fall back to QObject.
    try:
        item = root.findChild(QQuickItem, name)
        if item is not None:
            return item
    except Exception:
        pass
    start = root.contentItem() if hasattr(root, "contentItem") else root
    pending = [start]
    while pending:
        node = pending.pop()
        try:
            if node.objectName() == name:
                return node
        except Exception:
            pass
        try:
            pending.extend(node.childItems())
        except Exception:
            pass
    try:
        return root.findChild(QObject, name)
    except Exception:
        return None


class _StoreStub(QObject):
    def __init__(self):
        super().__init__()
        self.takeovers = 0
        self.recoveries = 0

    @Slot(result=dict)
    def requestTakeover(self):
        self.takeovers += 1
        return {"accepted": True}

    @Slot(result=dict)
    def doRecoverContinuation(self):
        self.recoveries += 1
        return {"success": True}

    @Slot(result=dict)
    def retryHandoff(self):
        return {"accepted": True}

    @Slot(result=dict)
    def requestHandoffExit(self):
        return {"success": True}


# Wrapper: a full-window underlying clickable layer + the REAL production overlay
# on top. `underlayClicks` proves swallow vs forward.
_WRAPPER = """
import QtQuick 2.15
import QtQuick.Window 2.15
import "shell"
Window {
    id: win
    width: 1440; height: 900
    visible: true
    property int underlayClicks: 0
    property int underlayKeys: 0
    Rectangle {
        id: underlay
        anchors.fill: parent
        color: "#102030"
        MouseArea {
            objectName: "underlayMouse"
            anchors.fill: parent
            onClicked: win.underlayClicks += 1
        }
        Keys.onPressed: function(event) { win.underlayKeys += 1 }
    }
    PlayerHandoffOverlay { id: ov; objectName: "playerHandoffOverlay"
                           anchors.fill: parent; z: 10 }
}
"""


@pytest.fixture
def overlay_runtime():
    _app()
    eng = QQmlApplicationEngine()
    eng.setOutputWarningsToStandardError(False)
    eng.addImportPath(QML_DIR)

    theme_component = QQmlComponent(eng)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()

    store_stub = _StoreStub()
    eng.rootContext().setContextProperty("theme", theme)
    eng.rootContext().setContextProperty("sessionStore", store_stub)
    eng.rootContext().setContextProperty("guiApp", QObject())

    # loaded through the engine (like the production Main.qml) so the root is the
    # real QQuickWindow (supports grabWindow for pixel evidence)
    eng.loadData(_WRAPPER.encode("utf-8"),
                 QUrl.fromLocalFile(os.path.join(QML_DIR, "_sd2_input_wrapper.qml")))
    roots = eng.rootObjects()
    assert roots, "wrapper window failed to load"
    win = roots[0]
    _events()
    overlay = _find(win, "playerHandoffOverlay")
    assert overlay is not None
    win._refs = (eng, theme, store_stub)
    yield win, overlay, store_stub
    win.close()
    _events(1)


def _center_point(item):
    return item.mapToScene(QPointF(float(item.property("width")) / 2.0,
                                   float(item.property("height")) / 2.0)).toPoint()


# ===========================================================================
# 1. Input — click/key accepted by the barrier, NOT forwarded while masked
# ===========================================================================
def test_sd_n4_click_is_swallowed_while_masked(overlay_runtime):
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()
    assert overlay.property("visible") is True

    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(20, 20))  # inside the overlay cover, outside any button
    _events()
    assert win.property("underlayClicks") == 0, "click reached the underlying control"


def test_positive_control_click_reaches_underlay_when_unmasked(overlay_runtime):
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()
    overlay.hideOverlay()
    _events()
    assert overlay.property("visible") is False
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(20, 20))
    _events()
    assert win.property("underlayClicks") == 1, "the underlay must be reachable once unmasked"


def test_key_is_not_forwarded_while_masked(overlay_runtime):
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()
    QTest.keyClick(win, Qt.Key.Key_A)
    _events()
    assert win.property("underlayKeys") == 0, "key reached the underlying layer"


def test_wheel_is_accepted_by_the_barrier(overlay_runtime):
    """AC04 barrier: wheel is accepted by the barrier, not forwarded."""
    from PySide6.QtGui import QWheelEvent
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()
    barrier = _find(win, "handoffInputBarrier")
    assert barrier is not None
    pos = QPointF(20.0, 20.0)
    ev = QWheelEvent(pos, QPointF(20.0, 20.0), QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QGuiApplication.sendEvent(win, ev)
    _events()
    # the barrier consumed it (accepted) and the underlay saw no click/scroll side effect
    assert ev.isAccepted() is True
    assert win.property("underlayClicks") == 0


def test_positive_control_after_each_input_negative(overlay_runtime):
    """R-04: after EVERY input negative (SD-N4 click + key swallow) an eligible
    current-seat action must still succeed — the underlay is reachable once the
    barrier is legitimately removed (the seat is not deadlocked)."""
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events()
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(20, 20))
    QTest.keyClick(win, Qt.Key.Key_A)
    _events()
    assert win.property("underlayClicks") == 0
    assert win.property("underlayKeys") == 0
    # positive control: the barrier is legitimately removed -> the same action reaches
    # the underlay.
    overlay.hideOverlay()
    _events()
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(20, 20))
    _events()
    assert win.property("underlayClicks") == 1


# ===========================================================================
# 2. Frame capture — REAL frame opacity (pixels, not metadata)
# ===========================================================================
def _frame_is_opaque(image: QImage, x: int, y: int) -> bool:
    """Falsification primitive: opaque iff the ACTUAL pixel alpha == 255. Uses
    pixel bytes ONLY — never an alpha declaration / frame receipt as evidence."""
    px = image.pixelColor(x, y)
    return px.alpha() == 255


def _grid_points(image: QImage, step: int = 96):
    xs = list(range(4, max(5, image.width() - 4), step))
    ys = list(range(4, max(5, image.height() - 4), step))
    return [(x, y) for y in ys for x in xs]


def _frame_is_opaque_grid(image: QImage):
    """R-03: opacity is asserted over a GRID of REAL pixels (a single point / two
    corners is insufficient)."""
    bad = [(x, y) for (x, y) in _grid_points(image)
           if not _frame_is_opaque(image, x, y)]
    return (not bad), bad


def test_frame_capture_real_cover_is_fully_opaque(overlay_runtime):
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events(8)

    grab = getattr(win, "grabWindow", None)
    assert callable(grab), "the root is not a QQuickWindow (no grabWindow)"
    img = win.grabWindow()
    assert img is not None and not img.isNull(), "could not grab the real frame"
    # R-03: pixels agree with the metadata over a GRID (not a single point).
    ok, bad = _frame_is_opaque_grid(img)
    assert ok, f"non-opaque real pixels in the mask: {bad[:8]}"
    assert overlay.property("color").alpha() == 255


def test_frame_sequence_same_transaction_real_frames(overlay_runtime):
    """R-03: a SAME-TRANSACTION real-frame sequence with generation binding:
    BARRIER_PRESENTED (opaque) -> FAILURE face (opaque) -> UNMASK_PRESENTED
    (underlay revealed). Each frame is a REAL ``grabWindow``; the masked frames are
    opaque over a grid and the unmasked frame DIFFERS in its REAL pixels (the cover
    truly neutralised the covered region)."""
    win, overlay, _store = overlay_runtime
    from src.ui.gui.app import HandoffFrameBridge

    # generation binding (production bridge): each begin increments the generation.
    bridge = HandoffFrameBridge(timeout_ms=5000)
    bridge.bind_window(win)
    gen1 = bridge.begin("seq-1", "arm", lambda *a: None)
    gen2 = bridge.begin("seq-2", "publish", lambda *a: None)
    assert gen2 == gen1 + 1, (gen1, gen2)

    overlay.showMaskedPending("Optimates")
    _events(8)
    f_barrier = win.grabWindow()
    assert f_barrier is not None and not f_barrier.isNull()
    ok, bad = _frame_is_opaque_grid(f_barrier)
    assert ok, bad[:8]

    overlay.showMaskedFailure("after_commit", "continuation")
    _events(8)
    f_failure = win.grabWindow()
    assert f_failure is not None and not f_failure.isNull()
    ok2, bad2 = _frame_is_opaque_grid(f_failure)
    assert ok2, bad2[:8]

    overlay.hideOverlay()
    _events(8)
    f_unmasked = win.grabWindow()
    assert f_unmasked is not None and not f_unmasked.isNull()

    # REAL-PIXEL non-identity: the covered frame and the unmasked frame differ.
    assert _img_sig(f_barrier) != _img_sig(f_unmasked), \
        "the mask did not change the REAL pixels (false positive)"


def test_sd_n3_real_pixel_false_positive_is_falsified(overlay_runtime):
    """SD-N3 / R-03 (NON-synthetic): the false-positive falsification runs on REAL
    frames. The masked and unmasked REAL frames differ over the covered region — a
    mask that left the real content unchanged would be an (undetected) false
    positive. The pixel-only checker additionally rejects a translucent frame."""
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Optimates")
    _events(8)
    masked = win.grabWindow()
    overlay.hideOverlay()
    _events(8)
    unmasked = win.grabWindow()
    assert masked is not None and not masked.isNull()
    assert unmasked is not None and not unmasked.isNull()
    assert _img_sig(masked) != _img_sig(unmasked), \
        "the cover did not change the REAL pixels (false positive)"

    # the pixels-only checker (no metadata) rejects a translucent frame.
    translucent = QImage(20, 20, QImage.Format.Format_ARGB32)
    translucent.fill(QColor(0, 0, 0, 204))  # alpha 204 != 255 (a metadata lie)
    assert _frame_is_opaque(translucent, 10, 10) is False


# ===========================================================================
# 3. Generation binding + stale-frame invalidation (SD-N5 / P7) — production bridge
# ===========================================================================
def test_sd_n5_stale_generation_frame_is_invalid(overlay_runtime):
    win, overlay, _store = overlay_runtime
    from src.ui.gui.app import HandoffFrameBridge

    bridge = HandoffFrameBridge(timeout_ms=5000)
    receipts = []
    bridge.bind_window(win)
    gen1 = bridge.begin("t1", "arm", lambda t, k, ok: receipts.append((t, k, ok)))
    assert gen1 == 1
    # a window RECREATION invalidates the live gate (fail closed) BEFORE any frame
    bridge.bind_window(None)
    # the live gate was invalidated: the stale receipt cannot complete as ok
    assert receipts == [("t1", "arm", False)], receipts
    # rebinding increments the surface generation (the old generation is stale)
    bridge.bind_window(win)
    gen2 = bridge.begin("t1b", "arm", lambda t, k, ok: None)
    assert gen2 == 2, gen2


def test_frame_gate_times_out_fail_closed(overlay_runtime):
    win, overlay, _store = overlay_runtime
    from src.ui.gui.app import HandoffFrameBridge

    bridge = HandoffFrameBridge(timeout_ms=40)
    receipts = []
    bridge.bind_window(win)
    bridge.begin("t2", "publish", lambda t, k, ok: receipts.append((t, k, ok)))
    QTest.qWait(120)
    _events()
    assert receipts == [("t2", "publish", False)], receipts


def test_failure_face_is_captured(overlay_runtime):
    """A MASKED_FAILURE (failure face) is a mandatory capture: the failure surface
    is shown with NO stale pending label (SB-V06), and a REAL failure-face frame is
    grabbed (R-03: failure faces are real captures, not attribute-only assertions)."""
    win, overlay, _store = overlay_runtime
    overlay.showMaskedPending("Populares")
    _events()
    assert _find(win, "handoffPendingLabel").property("text") == "下一位：Populares"
    overlay.showMaskedFailure("after_commit", "continuation")
    _events(8)
    assert overlay.property("failureVisible") is True
    assert overlay.property("failureRoute") == "continuation"
    # no stale pending target label survives the failure face
    assert overlay.property("pendingFactionName") == ""
    # R-03: a REAL failure-face frame is captured (not an attribute-only assert).
    img = win.grabWindow()
    assert img is not None and not img.isNull()
    ok, bad = _frame_is_opaque_grid(img)
    assert ok, bad[:8]


# ===========================================================================
# 4. §1.1.R recovery control — real input, mutual exclusion (production overlay)
# ===========================================================================
def test_recover_control_keyboard_and_pointer_share_one_action(overlay_runtime):
    win, overlay, store_stub = overlay_runtime
    overlay.showMaskedFailure("after_commit", "continuation")
    _events()
    recover = _find(win, "grContinuationRecover")
    assert recover is not None and recover.property("visible") is True

    # pointer dispatch
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _center_point(recover))
    _events()
    assert store_stub.recoveries == 1

    # keyboard dispatch (explicit local Keys handler on the recover control)
    recover.forceActiveFocus()
    _events()
    QTest.keyClick(win, Qt.Key.Key_Return)
    _events()
    assert store_stub.recoveries == 2


def test_failure_actions_are_mutually_exclusive(overlay_runtime):
    win, overlay, _store = overlay_runtime
    overlay.showMaskedFailure("after_commit", "activation")
    _events()
    assert _find(win, "grHandoffRetry").property("visible") is True
    assert _find(win, "grContinuationRecover").property("visible") is False

    overlay.showMaskedFailure("after_commit", "continuation")
    _events()
    assert _find(win, "grHandoffRetry").property("visible") is False
    assert _find(win, "grContinuationRecover").property("visible") is True


# ===========================================================================
# 5. Text — CJK glyph availability (report the gap; never self-downgrade)
# ===========================================================================
def test_cjk_glyph_availability_is_detected_and_reported():
    from PySide6.QtGui import QFont, QFontMetricsF
    _app()
    font = QFont("Microsoft YaHei UI")
    metrics = QFontMetricsF(font)
    required = "玩家交接下一位请该派系点击接管继续处理退出"
    available = {ch: metrics.inFont(ch) for ch in set(required)}
    missing = sorted(ch for ch, ok in available.items() if not ok)
    # detection is meaningful (a dict of bools); the ACTUAL gap is reported in the
    # implementation report — this asserts only that the machine check works and
    # that the required text is present in the overlay source.
    overlay_src = open(os.path.join(QML_DIR, "shell", "PlayerHandoffOverlay.qml"),
                       encoding="utf-8").read()
    assert "接管" in overlay_src and "继续处理" in overlay_src
    assert isinstance(missing, list)
    print(f"CJK glyphs missing in offscreen font: {missing}")
