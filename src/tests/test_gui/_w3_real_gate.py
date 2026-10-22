"""W3 — reusable REAL-gate scaffolding for masked owning transactions (test-only).

Why this module exists
----------------------
W3 was repeatedly RETURNed on EVIDENCE because the tests completed a masked
transaction's FIRST gate with a synchronous receipt (``_Witness`` /
``_GateWitness`` / a bool) or with a driven source. The frozen frame-evidence
contract (``G3-delta-Amendment-W3-02`` = FT) requires, for EVERY new masked
owning transaction, that the FIRST frame gate is completed by THAT transaction's
OWN real ``QQuickWindow`` (``afterRendering`` + ``frameSwapped``), through the
UNMODIFIED ``HandoffFrameBridge``; every later gate may be driven by a source
that implements only the same signal pair, and MUST be labelled
``FRAME_BRIDGE_DRIVEN`` — never ``REAL``.

This module turns the one-off C2 construction into a facility:

* :func:`real_window` — a fresh REAL ``QQuickWindow`` per REAL gate (offscreen
  swaps exactly one frame, so one window can only serve one gate);
* :class:`FrameWatch` — counts that window's OWN two signals;
* :class:`DrivenFrameSource` — the same signal pair only (never REAL);
* :class:`RealGateHarness` — binds the window for the next owning transaction,
  waits for its first gate, asserts ``REAL`` (tier / receipt / frozen
  generation / both signals), asserts later gates are ``DRIVEN``, and records a
  per-gate ``txn/kind/tier/ok/generation`` row for the evidence table.

Nothing here touches product code: the bridge, the Store and the QML tree are
the production ones; only the *provider frame source* and the explicit tier
LABEL are test-side, exactly as FT (b)/(c) permits.
"""
import os

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtTest import QTest

from src.ui.gui.session_store import SEAT_ACTIVATE, SEAT_ACTIVE, SEAT_MASKED_PENDING

TIER_REAL = "FRAME_WINDOW_REAL"
TIER_DRIVEN = "FRAME_BRIDGE_DRIVEN"

#: A real QML scene: a real QQuickWindow really renders (and swaps) a frame.
_REAL_WIN_QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    width: 240; height: 160
    visible: true
    color: "black"
    Rectangle { anchors.fill: parent; color: "red" }
}
"""

#: Qt objects must outlive the function that created them, but NOT the test.
_KEEPALIVE = []


# ---------------------------------------------------------------------------
# Test hygiene — a REAL window is a PER-TEST object, not a process-lifetime one
# ---------------------------------------------------------------------------
def window_snapshot():
    """The top-level windows alive right now (baseline for per-test hygiene)."""
    instance = QGuiApplication.instance()
    if instance is None:
        return []
    return list(instance.topLevelWindows())


def _drain_events(rounds=4):
    """Flush postponed deletions and the posted-event queue."""
    from PySide6.QtCore import QCoreApplication, QEvent

    try:
        deferred = int(QEvent.Type.DeferredDelete)
    except AttributeError:  # pragma: no cover - older enum spelling
        deferred = 52
    for _ in range(rounds):
        try:
            QCoreApplication.sendPostedEvents(None, deferred)
        except Exception:  # pragma: no cover - defensive
            pass
        QCoreApplication.processEvents()


def release_windows(baseline=()):
    """Close (and destroy) the REAL windows the current test opened.

    Test hygiene only: no product, Store, bridge or QML byte is touched.

    On the offscreen platform every REAL gate window is a *visible* top-level
    ``QQuickWindow`` that owns a live render surface. W3 opens one (or more) per
    test and, before this helper existed, nothing ever closed them: they stayed
    alive -- together with their surfaces and pending frame work -- for the
    whole pytest process, so a long suite accumulated them across tests and
    later, unrelated offscreen captures ran under a continuously growing set of
    live surfaces. Closing them at test end restores exactly the process state a
    fresh process would show the next test.

    ``baseline`` is the snapshot taken when the test started, so windows that
    belong to somebody else are never touched. Windows created by this module
    are fully destroyed (their engine/component are ours); foreign shell windows
    are only closed, never deleted, because their QML engine owns them.
    """
    keep = {id(win) for win in baseline}
    tracked = list(_KEEPALIVE)
    tracked_ids = {id(obj) for obj in tracked}
    destroyed = closed = 0

    for obj in tracked:
        if isinstance(obj, QWindow):
            try:
                obj.setVisible(False)
            except Exception:  # pragma: no cover - defensive
                pass
            try:
                obj.close()
            except Exception:  # pragma: no cover - defensive
                pass
            try:
                obj.deleteLater()
                destroyed += 1
            except Exception:  # pragma: no cover - defensive
                pass
        else:
            try:
                obj.deleteLater()
            except Exception:  # pragma: no cover - defensive
                pass
    _KEEPALIVE.clear()

    for win in window_snapshot():
        if id(win) in keep or id(win) in tracked_ids:
            continue
        try:
            win.setVisible(False)
            win.close()
            closed += 1
        except Exception:  # pragma: no cover - defensive
            pass

    _drain_events()
    remaining = window_snapshot()
    visible_after = sum(1 for win in remaining if win.isVisible())
    print("W3_RELEASE windows_baseline=%d destroyed_own=%d closed_foreign=%d "
          "visible_after=%d top_level_after=%d"
          % (len(baseline), destroyed, closed, visible_after, len(remaining)))
    return {"baseline": len(baseline), "destroyed": destroyed,
            "closed": closed, "visible_after": visible_after,
            "top_level_after": len(remaining)}


# ---------------------------------------------------------------------------
# Qt plumbing
# ---------------------------------------------------------------------------
def app():
    """The one QGuiApplication of this process."""
    return QGuiApplication.instance() or QGuiApplication([])


def pump(rounds=6, wait=5):
    for _ in range(rounds):
        QGuiApplication.processEvents()
        if wait:
            QTest.qWait(wait)


def pump_until(predicate, *, rounds=120, wait=10, win=None):
    """Spin the REAL event loop until ``predicate()`` is true (or give up)."""
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(wait)
        if win is not None:
            try:
                win.requestUpdate()
            except Exception:  # pragma: no cover - defensive
                pass
        if predicate():
            return True
    return bool(predicate())


def real_window():
    """A FRESH real :class:`QQuickWindow` (its own QML scene).

    On the offscreen platform a window swaps ONE frame, so the REAL tier is
    bound to a freshly created window for exactly the one gate that must be
    real -- the next transaction gets its own new window.
    """
    app()
    engine = QQmlApplicationEngine()
    engine.setOutputWarningsToStandardError(False)
    component = QQmlComponent(engine)
    component.setData(_REAL_WIN_QML.encode("utf-8"),
                      QUrl.fromLocalFile("/tmp/_w3_real_gate_window.qml"))
    assert not component.isError(), component.errorString()
    window = component.create()
    assert window is not None
    assert isinstance(window, QWindow), window
    _KEEPALIVE.extend([engine, component, window])
    return window


class FrameWatch(QObject):
    """Counts the REAL window's OWN ``afterRendering`` / ``frameSwapped``."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.after = 0
        self.swap = 0
        win.afterRendering.connect(self._on_after)
        win.frameSwapped.connect(self._on_swap)

    def _on_after(self):
        self.after += 1

    def _on_swap(self):
        self.swap += 1

    @property
    def counts(self):
        return {"after": self.after, "swap": self.swap}

    def both(self):
        """The dual-signal predicate FT (b) requires for a REAL first gate."""
        return self.after >= 1 and self.swap >= 1


class DrivenFrameSource(QObject):
    """A frame source that implements ONLY the SAME pair of signals the
    production bridge consumes.

    The bridge itself stays byte-unchanged; this source can never complete a
    REAL tier gate and is always recorded as ``FRAME_BRIDGE_DRIVEN``.
    """

    afterRendering = Signal()
    frameSwapped = Signal()

    def __init__(self, exposed=True):
        super().__init__()
        self.updates = 0
        self.exposed = bool(exposed)

    def requestUpdate(self):
        self.updates += 1

    def isExposed(self):
        return self.exposed

    def render(self):
        self.afterRendering.emit()
        self.frameSwapped.emit()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
class RealGateHarness:
    """The REAL-gate facility for ONE live GUI shell (one Store / one bridge).

    Usage (one owning transaction)::

        real = RealGateHarness(shell)
        real.arm_real()                 # fresh real window bound BEFORE the txn
        result = store.doAdvancePopulation()
        txn = (store._async_gate or {}).get("txn_id", "")
        begin_generation = real.generation()
        row = real.claim_first(txn, begin_generation=begin_generation)
        real.bind_driven()              # later gates: driven pair only
        ...
        real.assert_tail_driven(txn)
    """

    def __init__(self, shell, *, label=""):
        self.shell = shell
        self.store = shell.store
        self.gui = shell.gui
        self.driven = shell.driven
        self.label = label
        self.bindings = []      # one per owning txn (window / watch / txn)
        self.rows = []          # recorded per-gate evidence rows
        self._current = None

    # -- bridge / window ----------------------------------------------------
    def generation(self):
        return int(self.gui._frame_bridge._generation)

    def live_gate(self):
        return bool(self.gui._frame_bridge.has_live_gate())

    def arm_real(self):
        """Bind a FRESH real window for the NEXT owning txn's FIRST gate."""
        assert self.live_gate() is False, "a live gate must never be dropped at bind"
        win = real_window()
        watch = FrameWatch(win)
        self.gui.tier["arm"] = TIER_REAL
        self.gui.tier["publish"] = TIER_DRIVEN
        self.gui.tier["unmask"] = TIER_DRIVEN
        self.gui.bind_frame_window(win)
        assert self.gui._frame_bridge._window is win, "the real window must be bound"
        binding = {"win": win, "watch": watch, "bound_generation": self.generation(),
                   "txn": "", "row": None}
        self.bindings.append(binding)
        self._current = binding
        return binding

    def bind_driven(self):
        """Rebind the UNMODIFIED bridge to the driven pair (later gates only).

        A live gate is never dropped: dropping it is the production fail-close
        path and would be a false failure, not a rebind.
        """
        if self.live_gate():
            return False
        self.gui.tier["publish"] = TIER_DRIVEN
        self.gui.tier["unmask"] = TIER_DRIVEN
        self.gui.bind_frame_window(self.driven)
        return True

    def auto_driven_tail(self):
        """Every gate AFTER a txn's first one uses the driven signal pair.

        The provider's async gate entry points are wrapped so the rebind happens
        BEFORE the bridge begins the gate: a live gate is never dropped, and the
        recorded tier always names the source that really completes it.
        """
        gui = self.gui
        if getattr(gui, "_w3_auto_driven", False):
            return
        for name in ("publish_under_mask_async", "request_unmask_async"):
            original = getattr(gui, name)

            def _gate(txn_id, on_receipt, _original=original):
                if not self.live_gate():
                    self.bind_driven()
                return _original(txn_id, on_receipt)

            setattr(gui, name, _gate)
        gui._w3_auto_driven = True

    def watch_dispatch_ordering(self, dispatched):
        """Record the owning-dispatch count AT THE MOMENT the arm receipt is
        delivered (i.e. immediately before the Store resumes the gate).

        ``dispatched`` returns the current dispatch count. A row with
        ``dispatch_before_receipt == 0`` is the exact ordering predicate: the
        owning dispatch provably did not run before the real frame receipt.
        """
        gui = self.gui
        rows = []
        original = getattr(gui, "arm_barrier_async")

        def _arm(txn_id, on_receipt):
            def _receipt(txn, kind, ok):
                rows.append({"txn": txn, "kind": kind, "ok": bool(ok),
                             "dispatch_before_receipt": int(dispatched())})
                return on_receipt(txn, kind, ok)

            return original(txn_id, _receipt)

        setattr(gui, "arm_barrier_async", _arm)
        return rows

    def fail_live_gate_by_rebind(self):
        """The PRODUCTION bridge's own fail-close: recreating the surface while a
        gate is live discards that gate with ``ok=False``.

        No boolean is fabricated: ``HandoffFrameBridge.bind_window`` invalidates
        the live gate itself (the same rule a real window recreation triggers).
        """
        assert self.live_gate(), "no live gate to fail closed"
        surface = real_window()
        self.gui.bind_frame_window(surface)
        assert self.live_gate() is False
        return surface

    def rebind_on_activation(self):
        """Rebind to the driven pair when the seat enters ACTIVATE with no live
        gate (the same-seat reveal path). Returns the connected slot."""
        def _on_change():
            if self.store._seat_lifecycle != SEAT_ACTIVATE:
                return
            if self.live_gate():
                return
            if self.gui._frame_bridge._window is self.driven:
                return
            self.bind_driven()

        self.store.seatLifecycleChanged.connect(_on_change)
        return _on_change

    # -- per-gate observation ----------------------------------------------
    def gates(self, txn=None):
        return [g for g in self.gui.gate_log
                if txn is None or g["txn"] == txn]

    def first(self, txn):
        rows = self.gates(txn)
        assert rows, "no gate recorded for txn %r" % (txn,)
        return rows[0]

    def claim_first(self, txn, *, begin_generation=None):
        """Wait for THIS txn's own first gate and prove it is REAL."""
        assert txn, "no owning txn"
        binding = self._current
        assert binding is not None, "arm_real() must bind the window first"
        assert binding["txn"] in ("", txn), (binding["txn"], txn)
        binding["txn"] = txn
        first = self.first(txn)
        assert first["kind"] == "arm", first
        assert pump_until(lambda: first["ok"] is not None, win=binding["win"]), \
            "no REAL frame for the first gate of %r" % (txn,)
        assert first["tier"] == TIER_REAL, first
        assert first["ok"] is True, first
        assert first["receipt"] == (txn, "arm"), first
        if begin_generation is not None:
            assert first["generation"] == begin_generation, (first, begin_generation)
        assert binding["bound_generation"] <= first["generation"], (first, binding)
        assert binding["watch"].both(), binding["watch"].counts
        row = {
            "txn": txn,
            "kind": first["kind"],
            "tier": first["tier"],
            "ok": first["ok"],
            "generation": first["generation"],
            "generation_at_begin": (begin_generation if begin_generation is not None
                                    else first["generation"]),
            "bound_generation": binding["bound_generation"],
            "receipt": first["receipt"],
            "after_signals": binding["watch"].counts["after"],
            "swap_signals": binding["watch"].counts["swap"],
            "source": binding["win"].metaObject().className(),
            "source_id": id(binding["win"]),
        }
        binding["row"] = row
        self.rows.append(row)
        return row

    def assert_tail_driven(self, txn, *, ok_required=True):
        """Every gate AFTER the first of this txn is DRIVEN (never REAL)."""
        tail = self.gates(txn)[1:]
        for row in tail:
            assert row["tier"] == TIER_DRIVEN, row
            if ok_required:
                assert row["ok"] is True, row
            assert row["receipt"] == (txn, row["kind"]), row
        return tail

    def record_tail(self, txn):
        """Record the non-first gates of this txn into the evidence table."""
        for row in self.gates(txn)[1:]:
            self.rows.append({
                "txn": txn, "kind": row["kind"], "tier": row["tier"],
                "ok": row["ok"], "generation": row["generation"],
                "generation_at_begin": None,
                "bound_generation": None,
                "receipt": row["receipt"],
                "after_signals": None, "swap_signals": None,
                "source": "driven-signal-pair", "source_id": None,
            })
        return self.rows

    # -- evidence ----------------------------------------------------------
    def table(self):
        """Markdown rows: one per recorded gate (the G5 cross-check table)."""
        out = ["| txn | kind | tier | ok | generation | receipt | signals | source |",
               "|:--|:--|:--|:-:|:-:|:--|:--|:--|"]
        for row in self.rows:
            signals = ""
            if row["after_signals"] is not None:
                signals = "after=%d swap=%d" % (row["after_signals"],
                                                row["swap_signals"])
            out.append("| `%s` | %s | %s | %s | %s | `%s` | %s | %s |" % (
                row["txn"], row["kind"], row["tier"], row["ok"],
                row["generation"], row["receipt"], signals or "-",
                row["source"]))
        return "\n".join(out)

    def summary(self):
        """(real, driven) counts over the recorded rows."""
        real = sum(1 for r in self.rows if r["tier"] == TIER_REAL)
        driven = sum(1 for r in self.rows if r["tier"] == TIER_DRIVEN)
        return {"real": real, "driven": driven,
                "txns": len({r["txn"] for r in self.rows})}

    def emit(self, label):
        """Print one machine-readable line per recorded gate (evidence table)."""
        for row in self.rows:
            signals = ("-" if row["after_signals"] is None
                       else "after=%d/swap=%d" % (row["after_signals"],
                                                  row["swap_signals"]))
            print("GATE_ROW label=%s txn=%s kind=%s tier=%s ok=%s gen=%s "
                  "gen_begin=%s receipt=%s signals=%s source=%s"
                  % (label, row["txn"], row["kind"], row["tier"], row["ok"],
                     row["generation"], row["generation_at_begin"],
                     row["receipt"], signals, row["source"]))
        print("GATE_SUMMARY label=%s real=%d driven=%d txns=%d"
              % ((label,) + (self.summary()["real"],
                             self.summary()["driven"],
                             self.summary()["txns"])))


# ---------------------------------------------------------------------------
# Seat-transition helper shared by the chains
# ---------------------------------------------------------------------------
def settle_seat(harness, *, rounds=8):
    """Consume ONE seat transition of the current packet.

    A cross-seat handoff is consumed through the REAL 「接管」 intent
    (``requestTakeover``); the publication/reveal gates of the SAME owning txn
    are then completed by the driven signal pair on the unmodified bridge.
    """
    store = harness.store
    for _ in range(rounds):
        if store._seat_lifecycle == SEAT_ACTIVE:
            return True
        if store._seat_lifecycle == SEAT_MASKED_PENDING:
            assert harness.live_gate() is False, \
                "a pending seat must not hold a live gate"
            harness.bind_driven()
            takeover = store.requestTakeover()
            assert takeover.get("accepted") is True, takeover
        harness.driven.render()
        pump(2, 3)
    raise AssertionError("seat never became ACTIVE: %r" % (store._seat_lifecycle,))


# ---------------------------------------------------------------------------
# Minimum self-check of the facility itself (run by the W3 test files)
# ---------------------------------------------------------------------------
def self_check_bridge_pair():
    """Prove the facility's two claims without a QML shell.

    (a) a fresh REAL window completes a bridge gate through its OWN dual signal;
    (b) a driven source (same signal pair only) completes a gate as DRIVEN and
        is never recorded as REAL.
    """
    from src.ui.gui.app import HandoffFrameBridge

    app()
    win = real_window()
    watch = FrameWatch(win)
    bridge = HandoffFrameBridge(timeout_ms=5000)
    real_got = []
    bridge.bind_window(win)
    gen = bridge.begin("txn-selfcheck-real", "arm",
                       lambda t, k, ok: real_got.append((t, k, ok,
                                                         bridge._generation)))
    assert gen == bridge._generation, (gen, bridge._generation)
    assert pump_until(lambda: real_got, win=win), "no REAL dual-signal receipt"
    assert real_got == [("txn-selfcheck-real", "arm", True, gen)], real_got
    assert watch.both(), watch.counts

    driven = DrivenFrameSource()
    bridge.bind_window(driven)
    driven_got = []
    driven_gen = bridge.begin("txn-selfcheck-driven", "publish",
                              lambda t, k, ok: driven_got.append((t, k, ok)))
    driven.render()
    assert driven_got == [("txn-selfcheck-driven", "publish", True)], driven_got
    assert driven_gen == gen + 1, (driven_gen, gen)
    return {"real": real_got[0], "driven": driven_got[0],
            "real_signals": watch.counts,
            "tiers": (TIER_REAL, TIER_DRIVEN)}
