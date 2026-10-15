"""
src/ui/gui/app.py
GUI 应用主类 — 初始化 PySide6、注册 QML 类型、加载主界面。
"""
import os
import sys
import logging

import PySide6
from PySide6.QtCore import QUrl, QObject, Signal, Slot, Qt, QTimer, qVersion
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

from src.core.game_state import GameState
from src.api import session_access
from src.ui.gui.session_store import GuiSessionStore
from src.ui.gui.localization import gui_localization
from src.ui.gui.controllers.population_controller import PopulationController
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel

logger = logging.getLogger("EOR-GUI")


class HandoffFrameBridge(QObject):
    """R2 §4 / F4 real frame-receipt bridge (owned by :class:`GuiApp`).

    The frozen Witness Protocol requires that a QML property assignment / signal
    delivery alone is **never** ``BARRIER_PRESENTED`` / ``PUBLICATION_BOUND_UNDER_MASK`` /
    ``UNMASK_PRESENTED``: the receipts must be confirmed by a REAL ``QQuickWindow``
    frame. This bridge records the immutable armed scene-generation tag on
    ``QQuickWindow.afterRendering`` and confirms that the SAME generation completed
    its window frame on ``QQuickWindow.frameSwapped``. A receipt is emitted only
    when BOTH signal observations were made for that generation AND the window is
    exposed/visible — never a ``QTimer`` or an arbitrary QML binding notify.

    Callbacks carry only immutable IDs (``txn_id`` / ``kind`` / ``generation``);
    they never read/mutate QML or Core. Receipts from an old generation, or after a
    window recreation, are discarded. A gate that does not complete inside the
    approved 5s witness window fails closed (``ok=False``).
    """

    def __init__(self, parent=None, *, timeout_ms: int = 5000):
        super().__init__(parent)
        self._window = None
        self._connected = False
        self._generation = 0
        self._gate = None
        self._timeout_ms = int(timeout_ms)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    # -- window binding -----------------------------------------------------
    def bind_window(self, window) -> None:
        """Bind (or rebind) the production :class:`QQuickWindow`. A window
        recreation discards any live gate (fail closed) and increments the
        surface generation."""
        if window is self._window:
            return
        self._invalidate_gate()
        self._disconnect()
        self._window = window
        self._connect()

    def _connect(self) -> None:
        w = self._window
        if w is not None and not self._connected:
            # AutoConnection: a notice emitted from the RENDER thread is delivered
            # queued to the GUI thread; a GUI-thread notice is direct. Never
            # read/mutate QML/Core from the render thread.
            w.afterRendering.connect(self._on_after_rendering)
            w.frameSwapped.connect(self._on_frame_swapped)
            self._connected = True

    def _disconnect(self) -> None:
        w = self._window
        if w is not None and self._connected:
            try:
                w.afterRendering.disconnect(self._on_after_rendering)
                w.frameSwapped.disconnect(self._on_frame_swapped)
            except (RuntimeError, TypeError):  # pragma: no cover - defensive
                pass
        self._connected = False

    # -- gate API (async; the caller suspends) ------------------------------
    def begin(self, txn_id: str, kind: str, on_receipt) -> int:
        """Request a REAL frame receipt for ``(txn_id, kind)``. Returns the
        immutable generation tag. ``on_receipt(txn_id, kind, ok)`` fires once."""
        self._invalidate_gate()
        self._generation += 1
        gen = self._generation
        self._gate = {"txn_id": txn_id, "kind": kind, "generation": gen,
                      "after": False, "swapped": False, "on_receipt": on_receipt}
        if self._window is not None:
            # Request the scene update on the GUI thread; the receipt arrives via
            # the queued afterRendering + frameSwapped observations below.
            self._window.requestUpdate()
        self._timer.start(self._timeout_ms)
        return gen

    def has_live_gate(self) -> bool:
        return self._gate is not None

    # -- render-thread notices (queued to the GUI thread) -------------------
    def _on_after_rendering(self) -> None:
        g = self._gate
        if g is None or g["after"]:
            return
        g["after"] = True
        self._maybe_complete()

    def _on_frame_swapped(self) -> None:
        g = self._gate
        if g is None or not g.get("after") or g["swapped"]:
            return
        g["swapped"] = True
        self._maybe_complete()

    def _maybe_complete(self) -> None:
        g = self._gate
        if g is None or not (g["after"] and g["swapped"]):
            return
        if self._window is not None and self._window.isExposed():
            self._complete(True)

    def _on_timeout(self) -> None:
        if self._gate is not None:
            self._complete(False)

    def _invalidate_gate(self) -> None:
        g = self._gate
        self._gate = None
        self._timer.stop()
        if g is not None:
            self._fire(g, False)

    def _complete(self, ok: bool) -> None:
        g = self._gate
        self._gate = None
        self._timer.stop()
        if g is not None:
            self._fire(g, bool(ok))

    @staticmethod
    def _fire(g, ok: bool) -> None:
        try:
            g["on_receipt"](g["txn_id"], g["kind"], bool(ok))
        except Exception:  # pragma: no cover - defensive
            logger.exception("handoff frame receipt callback failed")


class GuiApp(QObject):
    """Eagle of Rome GUI 应用主类。"""

    engineLoaded = Signal(bool)
    errorOccurred = Signal(str)

    def __init__(self, state: GameState, parent=None):
        super().__init__(parent)
        self._state = state
        # R3b F6 (SB-V05): the PRODUCTION GuiApp path enables neutral startup — the
        # Store never publishes the factory-chosen actor; it enters a neutral
        # MASKED_PENDING and exposes only the safe faction name until an explicit
        # first-HUMAN 「接管」. Un-registered CLI/historical states keep the
        # historical publish (the CLI exemption is preserved and separated in the
        # Store's initialize()).
        self._store = GuiSessionStore(state, neutral_startup=True)
        self._engine = None
        self._root = None
        self._theme = None
        self._app = None
        # F4: the production frame-receipt bridge. Bound to the real QQuickWindow
        # once it exists (``run`` / ``bind_frame_window``); the Store's masked
        # barrier / publication / unmask gates await its receipts.
        self._frame_bridge = HandoffFrameBridge(self)

    def bind_frame_window(self, window) -> None:
        """Bind the real window used for frame receipts (production + tests)."""
        self._frame_bridge.bind_window(window)

    def run(self, argv=None):
        """启动 GUI 应用。"""
        app = QGuiApplication(argv or sys.argv)
        self._app = app
        app.setApplicationName("Eagle of Rome")
        app.setOrganizationName("EOR")
        app.setFont(QFont("Microsoft YaHei UI"))
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"PySide6 version: {PySide6.__version__}")
        logger.info(f"Qt version: {qVersion()}")

        # 注册 QML 类型
        qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
        qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
        qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

        self._engine = QQmlApplicationEngine()
        self._engine.warnings.connect(self._on_qml_warnings)

        # 设置 QML 导入路径
        qml_dir = os.path.join(os.path.dirname(__file__), "qml")
        self._engine.addImportPath(qml_dir)
        logger.info(f"QML directory: {qml_dir}")

        # 获取 QML 根目录
        logger.info(f"QML import paths: {self._engine.importPathList()}")

        # 加载 Theme 组件并设置为上下文属性
        theme_component = QQmlComponent(self._engine)
        theme_qml = os.path.join(qml_dir, "theme", "Theme.qml")
        theme_component.loadUrl(QUrl.fromLocalFile(os.path.normpath(theme_qml)))
        if theme_component.isError():
            logger.error(f"Theme.qml errors: {theme_component.errorString()}")
        else:
            theme_obj = theme_component.create()
            if theme_obj:
                self._theme = theme_obj
                self._engine.rootContext().setContextProperty("theme", self._theme)
                logger.info("Theme object created and exposed as 'theme'")
            else:
                logger.error("Failed to create Theme object")

        # 设置上下文属性（QML 可直接访问）
        self._engine.rootContext().setContextProperty("sessionStore", self._store)
        self._engine.rootContext().setContextProperty("localization", gui_localization)
        self._engine.rootContext().setContextProperty("guiApp", self)

        # 加载主 QML
        main_qml = os.path.join(qml_dir, "Main.qml")
        url = QUrl.fromLocalFile(os.path.normpath(main_qml))
        logger.info(f"Loading QML: {url.toString()}")
        self._log_qml_component_status(qml_dir, [
            "Main.qml",
            os.path.join("shell", "GameShell.qml"),
            os.path.join("stages", "PopulationStage.qml"),
            os.path.join("shell", "FeedbackPanel.qml"),
        ])
        self._engine.load(url)

        # 检查 QML 加载结果（rootObjects 为空即加载失败）
        root_objects = self._engine.rootObjects()
        logger.info(f"Root objects count: {len(root_objects)}")

        if not root_objects:
            logger.error("Failed to load Main.qml: rootObjects() is empty")
            self._log_qml_component_status(qml_dir, [
                "Main.qml",
                os.path.join("shell", "GameShell.qml"),
                os.path.join("stages", "PopulationStage.qml"),
                os.path.join("stages", "FestivalView.qml"),
                os.path.join("stages", "VoteView.qml"),
                os.path.join("stages", "ElectionResultView.qml"),
            ])
            self.errorOccurred.emit("Failed to load Main.qml")
            self.engineLoaded.emit(False)
            return 1

        # 根对象应该是 Window
        window = root_objects[0]
        logger.info(f"Root object type: {type(window).__name__}")
        logger.info(f"Root object className: {window.metaObject().className()}")

        # 查找 GameShell 子组件
        self._root = window.findChild(QObject, "gameShell")
        if not self._root:
            logger.warning("GameShell not found as child of Window, using window as root")
            self._root = window
        else:
            logger.info("GameShell found via findChild")
        logger.info(f"GameShell lookup result: {bool(self._root)}")
        # F4: bind the REAL window used for the handoff frame receipts.
        self._frame_bridge.bind_window(window)
        self.engineLoaded.emit(True)

        # S-B Group 2/3 (startup safety, R2/R5): register the single active-seat
        # access policy and bind the production barrier/witness provider BEFORE the
        # first viewer is published, so the very first projection is already
        # guarded — a registered seat can never publish before its authority exists.
        try:
            current = self._state.get_current_player()
            if current is not None:
                session_access.register_hotseat_session(
                    self._state, current.player_id, epoch=0)
            self._store.setHandoffBarrierProvider(self)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"S-B hot-seat wiring failed: {e}")

        # initialize store（中性启动：已注册的 Hot-seat 永不在启动时发布；未注册的
        # CLI/历史状态保留历史的首个 viewer 发布）—— authority was registered above.
        current = self._state.get_current_player()
        if current:
            self._store.initialize(current.player_id)
            logger.info(f"GUI initialized for viewer: {current.player_id}")

        # 连接 store 信号到 QML
        self._store.feedbackRaised.connect(self._on_feedback)
        self._store.handoffRequired.connect(self._on_handoff)
        # SB-V06: wire the masked safe-exit request to the existing safe exit path.
        self._store.handoffExitRequested.connect(self._on_handoff_exit)

        # 启动事件循环
        logger.info("Starting event loop...")
        exit_code = app.exec()
        logger.info(f"Event loop exited with code: {exit_code}")
        return exit_code

    @Slot(list)
    def _on_qml_warnings(self, warnings):
        for warning in warnings:
            logger.error(f"QML warning: {warning.toString()}")

    def _log_qml_component_status(self, qml_dir: str, relative_paths):
        for rel_path in relative_paths:
            path = os.path.normpath(os.path.join(qml_dir, rel_path))
            component = QQmlComponent(self._engine)
            component.loadUrl(QUrl.fromLocalFile(path))
            if component.isError():
                logger.error(f"QML component error [{rel_path}]: {component.errorString()}")
            else:
                logger.info(f"QML component ready [{rel_path}]: {path}")

    @Slot(str, str)
    def _on_feedback(self, ftype: str, fmsg: str):
        """反馈信号转发到 QML"""
        try:
            if self._root is not None:
                self._root.showFeedback(ftype, fmsg)
        except Exception as e:
            logger.warning(f"showFeedback failed: {e}")

    @Slot(str)
    def _on_handoff(self, next_player_id: str):
        """玩家交接信号转发到 QML"""
        try:
            if self._root is not None:
                self._root.showHandoff(next_player_id)
        except Exception as e:
            logger.warning(f"showHandoff failed: {e}")

    @Slot()
    def _on_handoff_exit(self):
        """SB-V06: the Store already invalidated the txn + handles; now quit."""
        try:
            if self._app is not None:
                self._app.quit()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"safe exit failed: {e}")

    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        """QML 调用：确认交接后切换 viewer。

        R2: while a masked handoff transaction is pending/activating the legacy
        boolean form returns False (it must not mean "accepted") and never starts
        a new transaction. The masked path uses ``confirmHandoffAsync``/
        ``requestTakeover`` instead.
        """
        if self._store.seatLifecycle != "ACTIVE":
            return False
        return self._store.switchViewer(next_player_id)

    @Slot(str, result=dict)
    def confirmHandoffAsync(self, pending_token: str) -> dict:
        """S-B Group 2: event-driven activation. Returns {accepted, txn_id};
        accepted is NOT success — completion arrives via ``handoffFinished``."""
        return self._store.confirmHandoffAsync(pending_token)

    # -----------------------------------------------------------------------
    # S-B Group 2/3 — barrier/witness provider.
    #
    # F4 (R2 §1/§4): the barrier / publication / unmask gates must await a REAL
    # QQuickWindow frame receipt — a synchronous ``True`` return can never mean
    # "presented". The legacy same-name methods therefore NEVER claim a frame
    # (they return ``False``); the Store uses the ``*_async`` gate methods which
    # raise the QML surface and then suspend on
    # :class:`HandoffFrameBridge`'s afterRendering + frameSwapped receipt.
    # ``show_pending`` / ``show_failure`` are copy updates (not frame gates) and
    # keep their synchronous boolean.
    # -----------------------------------------------------------------------
    def _raise_cover_busy(self) -> bool:
        if self._root is None:
            return False
        try:
            self._root.showHandoffBusy()
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"showHandoffBusy failed: {e}")
            return False

    def _hide_cover(self) -> bool:
        if self._root is None:
            return False
        try:
            self._root.hideHandoff()
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"hideHandoff failed: {e}")
            return False

    @Slot(str, object)
    def arm_barrier_async(self, txn_id: str, on_receipt) -> None:
        """Present the opaque cover (BARRIER) then await a REAL frame receipt."""
        if not self._raise_cover_busy():
            on_receipt(txn_id, "arm", False)
            return
        self._frame_bridge.begin(txn_id, "arm", on_receipt)

    @Slot(str, object)
    def publish_under_mask_async(self, txn_id: str, on_receipt) -> None:
        """Bind the staged bundle UNDER the still-opaque cover, then await the
        matching afterRendering + frameSwapped receipt (the publication gate)."""
        if not self._raise_cover_busy():
            on_receipt(txn_id, "publish", False)
            return
        self._frame_bridge.begin(txn_id, "publish", on_receipt)

    @Slot(str, object)
    def request_unmask_async(self, txn_id: str, on_receipt) -> None:
        """Request cover removal, then await the final-reveal frame receipt."""
        if not self._hide_cover():
            on_receipt(txn_id, "unmask", False)
            return
        self._frame_bridge.begin(txn_id, "unmask", on_receipt)

    # -- legacy same-name gates: never a synchronous frame claim (F4) -------
    @Slot(str, result=bool)
    def arm_barrier(self, txn_id: str) -> bool:
        # No synchronous boolean may stand in for a rendered frame.
        return False

    @Slot(str, result=bool)
    def request_unmask(self, txn_id: str) -> bool:
        return False

    @Slot(str, str, result=bool)
    def show_pending(self, txn_id: str, faction_name: str) -> bool:
        if self._root is None:
            return False
        try:
            self._root.showHandoffPending(faction_name)
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"show_pending failed: {e}")
            return False

    @Slot(str, str, str, result=bool)
    def show_failure(self, txn_id: str, kind: str, route: str) -> bool:
        # SD-R02 (§1.1.R): copy-only token pass-through. The widened route
        # argument is forwarded to the reused overlay verbatim; this method is
        # NOT an authorization predicate and does NOT touch the frame gate
        # (HandoffFrameBridge is unchanged).
        if self._root is None:
            return False
        try:
            self._root.showHandoffFailure(kind, route)
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"show_failure failed: {e}")
            return False

    def get_store(self) -> GuiSessionStore:
        return self._store
