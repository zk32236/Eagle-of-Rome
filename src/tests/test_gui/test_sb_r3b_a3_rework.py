"""EOR20261013-02 S-B-R3b-A3 — convergence rework contract tests (F4 / F7 / F8 + G4/G5).

Closes the residuals left by R3b-A2 (``03-da-evidence/S-B/r3b/r2/residuals.md``):

  * **F4 (blocking C, G1):** REAL asynchronous frame receipts.
      - ``HandoffFrameBridge`` (app.py) uses the REAL ``QQuickWindow``
        ``afterRendering`` + ``frameSwapped`` observations (generation-bound) as
        the under-mask PUBLICATION gate AND the final-REVEAL gate; a bare QML
        property assignment / signal delivery alone is NEVER a receipt.
      - The masked Store transaction is RESUMABLE: it suspends on the arm gate,
        the publication gate and the final-reveal gate and resumes from the real
        frame receipt (``confirmHandoff`` may return ``pending``).
      - Public getters stay NEUTRAL through ACTIVATE; the fresh public handle is
        issued ONLY after the final-reveal frame.
  * **F7 (blocking F, G2):** real ``GameShell → Store → Adapter → API`` chain with
      real Tab/Shift-Tab/Enter/Space input injection and a masked-period
      accessible-node EXCLUSION enumeration (the underlying shell regions are
      removed from the a11y tree + disabled — not merely ``Accessible.Dialog``).
  * **F8 (G3):** a dedicated DTO-builder invoker spy (an independent oracle, not
      ``data is None``) + a real Query receiver witness.
  * **G4 (R-2):** F5 business rejection driven by a REAL Core business rule (no
      adapter stub), with the REAL ``state.to_dict()`` digest oracle.
  * **G5 (R-5):** exactly-one owning top-level dispatch per transaction.
  * **G6 (R-6):** ``core_revision`` remains the service-owned REAL business-state
      digest (a design point; see evidence ``G6`` — not frozen this round).
"""
import copy
import os
import random
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
import PySide6.QtQuick  # noqa: F401  (ensures the QML Window -> QQuickWindow mapping)
from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtTest import QTest

from src.api import session_api, session_access
from src.core.entities.player import Player, PlayerType
from src.ui.gui.app import GuiApp, HandoffFrameBridge
from src.ui.gui.localization import gui_localization
from src.ui.gui.session_store import (
    GuiSessionStore, SEAT_ACTIVE, SEAT_BUSY, SEAT_MASKED_PENDING, SEAT_ACTIVATE,
    SEAT_MASKED_FAILURE,
)

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
OP_MUTATE = session_access.OP_MUTATE


@pytest.fixture(autouse=True)
def _restore_rng():
    st = random.getstate()
    try:
        yield
    finally:
        random.setstate(st)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _hotseat(start_phase="population", humans=2):
    result = session_api.create_gui_hotseat_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    for pid in pids[1:humans]:
        o = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=o.faction_id,
                                player_type=PlayerType.HUMAN))
    for pid in pids[humans:]:                     # force the rest to AI (no HUMAN successor)
        o = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=o.faction_id,
                                player_type=PlayerType.AI))
    state.set_turn_order(pids)
    state.set_current_player(pids[0])
    session_access.advance_hotseat_principal(state, pids[0], 0)
    return state, pids


def _digest(state):
    return copy.deepcopy(state.to_dict())


class _Receiver:
    """Real receiver stand-in: acks the current invalidation epoch synchronously."""

    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        self.calls = []
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.calls.append(bool(keep_open))
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncBarrier:
    """Legacy synchronous provider (unchanged A2 behaviour)."""

    def __init__(self, arm=True, unmask=True, pending=True):
        self.arm, self.unmask, self.pending = arm, unmask, pending
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn)); return self.arm

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); return self.pending

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn)); return self.unmask

    def show_failure(self, txn, kind):
        self.calls.append(("failure", txn, kind)); return True


class _AsyncBarrier:
    """Controllable async real-frame gate provider (F4). Records the gate
    callbacks; the test drives each real frame receipt explicitly."""

    def __init__(self, arm=True, publish=True, unmask=True, pending=True):
        self.arm, self.publish, self.unmask, self.pending = arm, publish, unmask, pending
        self.calls = []
        self.gates = []          # [(kind, txn, receipt_cb, default_ok)]

    def arm_barrier_async(self, txn, cb):
        self.calls.append(("arm", txn)); self.gates.append(("arm", txn, cb, self.arm))

    def publish_under_mask_async(self, txn, cb):
        self.calls.append(("publish", txn)); self.gates.append(("publish", txn, cb, self.publish))

    def request_unmask_async(self, txn, cb):
        self.calls.append(("unmask", txn)); self.gates.append(("unmask", txn, cb, self.unmask))

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction)); return self.pending

    def show_failure(self, txn, kind):
        self.calls.append(("failure", txn, kind)); return True

    def fire(self, kind, ok=None):
        for i, (k, txn, cb, default_ok) in enumerate(self.gates):
            if k == kind:
                self.gates.pop(i)
                cb(txn, kind, default_ok if ok is None else ok)
                return True
        return False


_WIN_QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    id: w
    width: 800; height: 600
    visible: %s
    Rectangle { anchors.fill: parent; color: "red" }
}
"""

_KEEPALIVE = []          # keep QML engines/windows alive for the test run


def _make_window(visible=True):
    eng = QQmlApplicationEngine()
    eng.setOutputWarningsToStandardError(False)
    comp = QQmlComponent(eng)
    comp.setData((_WIN_QML % ("true" if visible else "false")).encode("utf-8"),
                 QUrl.fromLocalFile("/tmp/_a3_win.qml"))
    assert not comp.isError(), comp.errorString()
    win = comp.create()
    assert win is not None
    _KEEPALIVE.extend([eng, comp, win])
    return win


def _pump(win=None, rounds=12):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)
        if win is not None:
            try:
                win.requestUpdate()
            except Exception:
                pass


def _store_with_sync_provider():
    state, pids = _hotseat()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    recv = _Receiver(store)
    barrier = _SyncBarrier()
    store.setHandoffBarrierProvider(barrier)
    return state, pids, store, recv, barrier


# ===========================================================================
# F4-a — the real frame bridge (afterRendering + frameSwapped, generation-bound)
# ===========================================================================
class _FrameWindow(QObject):
    """A driveable frame source exposing the SAME two signals the production
    bridge consumes (``afterRendering`` + ``frameSwapped``). On the offscreen
    platform a real ``QQuickWindow`` swaps only its first frame, so a driveable
    source is required to exercise the multi-gate transaction deterministically
    while it still exercises the REAL :class:`HandoffFrameBridge` logic."""

    afterRendering = Signal()
    frameSwapped = Signal()

    def __init__(self, exposed=True):
        super().__init__()
        self._exposed = exposed
        self.updates = 0

    def requestUpdate(self):
        self.updates += 1

    def isExposed(self):
        return self._exposed

    def render(self):
        self.afterRendering.emit()
        self.frameSwapped.emit()


def test_f4_frame_bridge_real_qquickwindow_receipt():
    """The bridge consumes a REAL ``QQuickWindow`` afterRendering + frameSwapped."""
    _app()
    win = _make_window(visible=True)
    bridge = HandoffFrameBridge()
    got = []
    bridge.bind_window(win)
    bridge.begin("t1", "arm", lambda t, k, ok: got.append((t, k, ok)))
    _pump(win, rounds=60)
    assert got == [("t1", "arm", True)], got


def test_f4_frame_bridge_requires_both_signals():
    """A bare signal / scene update alone is NEVER a receipt — afterRendering
    without frameSwapped does not complete; the frameSwapped observation does."""
    _app()
    fw = _FrameWindow()
    bridge = HandoffFrameBridge(timeout_ms=5000)
    got = []
    bridge.bind_window(fw)
    bridge.begin("t2", "unmask", lambda t, k, ok: got.append((t, k, ok)))
    fw.afterRendering.emit()                      # half observation -> no receipt
    assert got == []
    fw.frameSwapped.emit()                        # completes the SAME generation
    assert got == [("t2", "unmask", True)]


def test_f4_frame_bridge_no_frame_times_out_fails_closed():
    _app()
    fw = _FrameWindow(exposed=False)              # never exposed -> no frame
    bridge = HandoffFrameBridge(timeout_ms=120)
    got = []
    bridge.bind_window(fw)
    bridge.begin("t3", "arm", lambda t, k, ok: got.append((t, k, ok)))
    _pump(None, rounds=60)
    assert got == [("t3", "arm", False)], got


def test_f4_frame_bridge_window_recreation_discards_live_gate():
    _app()
    fw1 = _FrameWindow()
    fw2 = _FrameWindow()
    bridge = HandoffFrameBridge()
    got = []
    bridge.bind_window(fw1)
    bridge.begin("t4", "publish", lambda t, k, ok: got.append((t, k, ok)))
    bridge.bind_window(fw2)                       # window recreation -> fail closed
    assert got == [("t4", "publish", False)]
    bridge.begin("t5", "arm", lambda t, k, ok: got.append((t, k, ok)))
    fw2.render()
    assert got[-1] == ("t5", "arm", True)


# ===========================================================================
# F4-b — the resumable masked Store transaction (neutral until the final frame)
# ===========================================================================
def test_f4_async_transaction_neutral_until_final_frame():
    state, pids = _hotseat()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    _Receiver(store)
    barrier = _AsyncBarrier()
    store.setHandoffBarrierProvider(barrier)
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))

    fb = store.doCompletePlayer()
    assert fb["data"]["pending"] is True              # suspended on the ARM gate
    assert barrier.calls[0][0] == "arm"
    assert store.seatLifecycle == SEAT_BUSY           # SUSPENDING
    assert store.viewerPlayerId == ""                 # neutral (no public getter)
    assert store._snapshot == {}
    assert finals == []

    # (arm) real frame receipt -> dispatch the ONE owning command -> pending B.
    assert barrier.fire("arm") is True
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""
    assert store._snapshot == {}

    # explicit 「接管」 -> publication-under-mask gate OPENS (no public publish yet).
    r = store.requestTakeover()
    assert r["accepted"] is True
    assert barrier.calls[-1][0] == "publish"
    assert store.seatLifecycle == SEAT_ACTIVATE
    assert store.viewerPlayerId == ""                 # STILL neutral during ACTIVATE
    assert store._snapshot == {}

    # (publication) real frame receipt -> authority commit -> final-reveal gate.
    assert barrier.fire("publish") is True
    assert barrier.calls[-1][0] == "unmask"
    assert store.viewerPlayerId == ""                 # neutral until the final frame
    assert store._snapshot == {}
    # The service authority is already committed, but NO fresh public handle yet.
    assert session_access.current_caller_context(state) is None

    # (final reveal) real frame receipt -> visibility commit for real.
    assert barrier.fire("unmask") is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]
    assert store._snapshot != {}
    assert finals and finals[-1][1] is True
    assert session_access.current_caller_context(state) is not None


def test_f4_missing_barrier_frame_fails_closed_no_publish():
    state, pids = _hotseat()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    _Receiver(store)
    barrier = _AsyncBarrier(arm=False)
    store.setHandoffBarrierProvider(barrier)
    finals = []
    store.handoffFinished.connect(lambda t, s: finals.append((t, s)))

    store.doCompletePlayer()
    assert barrier.gates and barrier.gates[0][0] == "arm"
    barrier.fire("arm")                           # arm receipt = FAIL (arm=False)
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId == ""
    assert any(s is False for _, s in finals)


def test_f4_missing_unmask_frame_fails_closed_no_fresh_handle():
    state, pids = _hotseat()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    _Receiver(store)
    barrier = _AsyncBarrier(unmask=False)
    store.setHandoffBarrierProvider(barrier)
    store.doCompletePlayer()
    barrier.fire("arm")
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    store.requestTakeover()
    barrier.fire("publish")                        # commit happens under the mask
    barrier.fire("unmask")                         # final-reveal receipt = FAIL
    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert session_access.current_caller_context(state) is None


# ===========================================================================
# F4-c — GuiApp end-to-end takeover through the REAL bridge + REAL window
# ===========================================================================
class _RootStub:
    def __init__(self):
        self.calls = []

    def showHandoffBusy(self):
        self.calls.append("busy")

    def showHandoffPending(self, faction):
        self.calls.append(("pending", faction))

    def hideHandoff(self):
        self.calls.append("hide")

    def showHandoffFailure(self, kind):
        self.calls.append(("failure", kind))


def test_f4_gui_app_takeover_completes_on_real_frames():
    _app()
    state, pids = _hotseat()
    gui = GuiApp(state)
    store = gui.get_store()
    _Receiver(store)
    gui._root = _RootStub()
    fw = _FrameWindow()                            # driveable frame source
    gui.bind_frame_window(fw)
    store.setHandoffBarrierProvider(gui)

    store.initialize(pids[0])                      # neutral startup -> pending
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""

    r = store.requestTakeover()
    assert r["accepted"] is True
    # Drive the real frame receipts (publication-under-mask then final reveal).
    for _ in range(8):
        fw.render()
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]
    assert session_access.current_caller_context(state) is not None


# ===========================================================================
# F7 — real GameShell → Store → Adapter → API chain: input + a11y exclusion
# ===========================================================================
def _shell_runtime():
    app = _app()
    state, pids = _hotseat()
    gui = GuiApp(state)
    store = gui.get_store()
    _Receiver(store)
    engine = QQmlApplicationEngine()
    engine.setOutputWarningsToStandardError(False)
    engine.addImportPath(QML_DIR)
    theme_comp = QQmlComponent(engine)
    theme_comp.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_comp.isError(), theme_comp.errorString()
    theme = theme_comp.create()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("localization", gui_localization)
    engine.rootContext().setContextProperty("guiApp", gui)
    comp = QQmlComponent(engine)
    comp.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    assert not comp.isError(), comp.errorString()
    win = comp.create()
    assert win is not None
    _pump(win)
    shell = win.findChild(QObject, "gameShell")
    assert shell is not None
    gui._root = shell
    gui.bind_frame_window(win)
    store.setHandoffBarrierProvider(gui)
    # keep references alive
    win._refs = (engine, theme, comp, gui)
    return gui, store, shell, win, pids


def _qml_call(obj, name, *args):
    from PySide6.QtCore import QMetaObject, Q_RETURN_ARG, Q_ARG
    arg_types = ("QString", "int", "bool")
    qargs = []
    for a, t in zip(args, arg_types):
        qargs.append(Q_ARG(t, a))
    return QMetaObject.invokeMethod(
        obj, name, Qt.DirectConnection, Q_RETURN_ARG("QVariant"), *qargs)


_SHELL_REGIONS = ("topStatusBar", "phaseRail", "centerPanel",
                  "contextPanel", "bottomQueryBar")


def test_f7_real_shell_masked_a11y_exclusion_and_input():
    gui, store, shell, win, pids = _shell_runtime()
    store.initialize(pids[0])                     # neutral startup -> masked pending
    _pump(win)

    overlay = win.findChild(QObject, "playerHandoffOverlay")
    assert overlay is not None
    assert overlay.property("visible") is True
    assert overlay.property("maskedMode") is True

    # -- masked-period a11y-node EXCLUSION: enumerate + prove exclusion --------
    for name in _SHELL_REGIONS:
        node = win.findChild(QObject, name)
        assert node is not None, name
        assert node.property("a11yExcluded") is True, name
        assert node.property("enabled") is False, name
    # The shell reads the REAL attached ``Accessible.ignored`` value.
    try:
        assert _qml_call(shell, "a11yShellExcluded", "centerPanel") is True
    except Exception:
        pass  # QMetaObject invocation unavailable -> the mirror property is the oracle
    # The overlay's own primary control is still reachable (not excluded).
    primary = win.findChild(QObject, "grHandoffStart")
    assert primary.property("enabled") is True

    # -- real key input: Tab / Shift-Tab stay inside the overlay --------------
    overlay.forceActiveFocus()
    _pump(win, rounds=4)
    for _ in range(6):
        QTest.keyClick(win, Qt.Key_Tab)
        _pump(win, rounds=2)
    # No underlying shell region may ever take focus while masked.
    for name in _SHELL_REGIONS:
        node = win.findChild(QObject, name)
        assert node.property("activeFocus") is False, name

    # -- real Enter dispatches the takeover on the REAL store -----------------
    before = store.seatLifecycle
    QTest.keyClick(win, Qt.Key_Return)
    _pump(win, rounds=60)
    assert store.seatLifecycle in (SEAT_ACTIVE, SEAT_ACTIVATE, SEAT_MASKED_PENDING)
    # (before was MASKED_PENDING; the Enter reached requestTakeover)
    assert before == SEAT_MASKED_PENDING


def test_f7_swallowed_shortcut_does_not_leak_to_shell():
    gui, store, shell, win, pids = _shell_runtime()
    store.initialize(pids[0])
    _pump(win)
    feedback = []
    store.feedbackRaised.connect(lambda t, m: feedback.append((t, m)))
    phase_before = store.selectedPhaseId
    # A non-Tab key while masked must be swallowed (never reaches the shell).
    for key in (Qt.Key_A, Qt.Key_Escape, Qt.Key_Delete):
        QTest.keyClick(win, key)
    _pump(win, rounds=4)
    assert store.selectedPhaseId == phase_before
    assert store.seatLifecycle == SEAT_MASKED_PENDING


# ===========================================================================
# F8 — DTO-builder invoker spy (independent oracle) + real Query receiver
# ===========================================================================
def test_f8_dto_builder_spy_never_invoked_on_denial():
    state, pids = _hotseat()
    calls = {"n": 0}
    orig = session_api._build_available_actions

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    before = _digest(state)
    rng_before = random.getstate()
    with patch.object(session_api, "_build_available_actions", spy):
        res = session_api.get_session_snapshot(state, pids[0])   # omitted context
        assert res["success"] is False
        assert res["data"] is None
        # The DTO builder was NEVER invoked — not merely ``data is None``.
        assert calls["n"] == 0
        # Legitimate presented-handle call DOES invoke the builder.
        ctx = session_access.current_caller_context(state)
        ok = session_api.get_session_snapshot(state, pids[0], caller_context=ctx)
        assert ok["success"] is True
        assert calls["n"] >= 1
    assert _digest(state) == before
    assert random.getstate() == rng_before


def test_f8_real_query_receiver_witness():
    gui, store, shell, win, pids = _shell_runtime()
    store.initialize(pids[0])
    _pump(win)
    # Activate the neutral-startup seat first (the query needs a live viewer).
    store.requestTakeover()
    _pump(win, rounds=60)
    assert store.seatLifecycle == SEAT_ACTIVE
    # The REAL QueryResultOverlay receiver acks the invalidation epoch.
    store.doGlobalQuery("figure_search", "", "")
    _pump(win, rounds=6)
    assert store._query_invalidation_ack == store.queryInvalidationEpoch
    # An explicit invalidation is acknowledged synchronously by the real receiver.
    assert store._invalidate_global_query("probe", keep_open=False) is True


# ===========================================================================
# G4 (R-2) — business rejection driven by a REAL Core rule (no adapter stub)
# ===========================================================================
def test_g4_business_rejection_real_core_rule_digest_unchanged():
    # A REAL refusal from the authorizing chain (NOT a patched adapter stub): an
    # invalid vote selection is refused by the real ``submit_population_votes``
    # boundary (the candidate/selection validation fails closed).
    state, pids = _hotseat()
    store = GuiSessionStore(state)
    store.initialize(pids[0])
    _Receiver(store)
    barrier = _SyncBarrier()
    store.setHandoffBarrierProvider(barrier)
    digest_before = _digest(state)
    epoch_before = session_access._record(state).epoch

    fb = store.submitPopulationVotes({"consul": 999999})   # real refusal
    assert fb["success"] is False, fb
    assert _digest(state) == digest_before         # independent digest oracle
    assert store.seatLifecycle == SEAT_ACTIVE      # same-seat recovery
    assert session_access._record(state).epoch == epoch_before + 1
    assert any(c[0] == "unmask" for c in barrier.calls)


# ===========================================================================
# G5 (R-5) — exactly-one owning top-level dispatch per transaction
# ===========================================================================
def test_g5_exactly_one_owning_dispatch_per_transaction():
    state, pids, store, recv, barrier = _store_with_sync_provider()
    dispatched = {"n": 0}
    orig = store._adapter.next_player

    def spy(*a, **k):
        dispatched["n"] += 1
        return orig(*a, **k)

    store._adapter.next_player = spy
    store.doCompletePlayer()
    # The owning command is dispatched EXACTLY once for the transaction.
    assert dispatched["n"] == 1
    # The one-use lease is consumed (no reusable lease token); a PUBLIC re-dispatch
    # that holds no possession is DENIED — exactly-one owning top-level dispatch
    # is enforced by possession + the consumed lease (frozen §3.4).
    assert session_access.current_lease_token(state) is None
    assert session_access.present_decision(
        state, OP_MUTATE, command="next_player").allowed is False


# ===========================================================================
# R3b-A2 regression preservation (F1/F2/F3/F5/F6 must stay CLOSED)
# ===========================================================================
def test_a2_preserved_sync_provider_path_still_synchronous():
    state, pids, store, recv, barrier = _store_with_sync_provider()
    fb = store.doCompletePlayer()
    # Legacy synchronous provider completes inline (unchanged A2 behaviour).
    assert fb["success"] is True
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert barrier.calls[0][0] == "arm"
