# src/tests/test_gui/test_tvas_triumph_render_evidence.py
"""EOR20261012-01 (Triumph Vote Abstention Semantics) — S3 RENDER_AUTOMATED evidence.

FC-13 ``action x viewer_vote`` six-cell matrix, captured off the REAL production chain
(SA-Narrow-Ruling §3.4 evidence contract, route = DIRECT_PRODUCTION):
    ``session_api.create_gui_prototype_session`` -> real ``GuiSessionStore``
    -> real production actions (``forum_api.open_market`` / ``store.doVoteTriumph``)
    -> real ``Main.qml`` (with real ``ForumStage.qml``) offscreen
    -> ``QQuickWindow.grabWindow()`` -> PNG (1440x900).

Contract compliance (SA §3.4):
    C-1 DIRECT_PRODUCTION: real store + real producer DTO + real QML; **no** self-built
        read-bridge store (the ATTEMPT-1 failure root cause).
    C-2 six exhaustive cells (§6.1) with visible-text + enabled/disabled +
        forbidden-visible assertions; readonly+已投 are forced overlap counter-examples.
    C-3 per-cell PNG (1440x900) + runtime.json + manifest (``capture_ok`` all-true,
        fail-closed).
    C-4 No-Test-Assisted-Transition: states reached via real production actions.
    C-5 deterministic (no scroll dependence: rendered in a tall viewport so the whole
        market panel is laid out, then cropped to the 1440x900 contract frame).
    C-6 read-only boundary: harness is test-write-face only; product/zero-touch untouched.

Six cells (design §6.1):
    1. actionable + viewer_vote=null   -> [赞成][反对] both enabled
    2. actionable + viewer_vote=true   -> disabled 「已投·赞成」
    3. actionable + viewer_vote=false  -> disabled 「已投·反对」
    4. readonly   + viewer_vote=null   -> disabled 「不可投」
    5. readonly   + viewer_vote=true   -> disabled 「已投·赞成」 (已投优先)
    6. readonly   + viewer_vote=false  -> disabled 「已投·反对」 (已投优先)

Boundary / anomaly cases (SA ruling ``SA-Ruling-viewer_vote-boundary-2026-10-12.md``):
    The ``viewer_vote`` bridge boundary is anchored on KEY PRESENCE
    (``"viewer_vote" in modelData``), NOT on the value:
      * key MISSING, or key present with a NON-BOOL value  -> anomaly -> fail-closed
        ("不可投", no action open; never misread as "反对").
      * key present with value ``None`` (QML ``null``/``undefined``) -> LEGAL abstention
        (dual action when actionable) -- six-cell cell-1.
    A Python dict cannot carry JS ``undefined``, so a present-key ``undefined`` can only
    originate from ``None`` bridging => the "present-key undefined anomaly" branch is
    UNREACHABLE (``ForumStage.qml`` has no such branch; QML logic is ZERO-CHANGE).

    Boundary test cases (G5-r3; all inside the approved write-face):
      TC-1  key-presence discriminator (present-None dual vs key-absent fail-closed)
      TC-2  anomaly: ``viewer_vote`` key missing -> fail-closed
      TC-3  anomaly: non-bool value domain (str ``"yes"`` + number ``1``) -> fail-closed
      TC-4  bridge identity pin: measured QML-side form of ``None`` (null/undefined)
      TC-5  legal present-``None`` equivalence + anomaly leg writes NO vote

Evidence root: this task's ``03-da-evidence/RENDER/`` (NOT the WP-J / any other task).
"""
import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TASK_DIR = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace"
    "/EOR20261012-01 Triumph Vote Abstention Semantics"
)
EVIDENCE_BASE = TASK_DIR + "/03-da-evidence/RENDER"

# R-05: seven-file candidate write-set + three-way (candidate/test/design) identity.
_CANDIDATE_FILES = (
    "src/api/forum_api.py",
    "src/ui/gui/qml/stages/ForumStage.qml",
    "src/tests/test_commands/test_phase_forum_triumph.py",
    "src/tests/test_gui/test_wpj_groupb_forum_triumph_row.py",
    "src/tests/test_gui/test_tvas_triumph_render_evidence.py",
    "docs/00_\u4ea7\u54c1\u6587\u6863/specifications/MVP0.5-05_\u51ef\u65cb\u4e0e\u4e34\u65f6\u5f71\u54cd\u529b.md",
    "docs/00_\u4ea7\u54c1\u6587\u6863/technical-mappings/MVP0.5-05_\u51ef\u65cb\u4e0e\u4e34\u65f6\u5f71\u54cd\u529b.md",
)
_DESIGN_FILES = (
    "02-sa-design/SA-Development-Task.md",
    "02-sa-design/SA-Narrow-Ruling-EOR20261012-01-2026-10-12.md",
    "02-sa-design/PM-Erratum-E1-inheritance-item11-2026-10-12.md",
    "00-gates/G4-EOR20261012-01-ReOpen-2026-10-12.md",
    # G5-r2 boundary ruling + PM disposition (this ATTEMPT-4 is sourced from them).
    "02-sa-design/SA-Ruling-viewer_vote-boundary-2026-10-12.md",
    "00-gates/G5-R2-PM-Disposition-and-Erratum-E2-2026-10-12.md",
)

from src.api import session_api, forum_api  # noqa: E402
from src.core.entities.war import War, WarStatus  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402
from PySide6.QtCore import Property, QObject, Signal, Slot  # noqa: E402

_ENGINES = []
_GRAB_STATE = {}

# --- R-01: harness-local CJK font injection ---------------------------------
# The offscreen platform has no CJK font installed (only DejaVu/Ubuntu), so every
# canonical Chinese label renders as a tofu box. Register a CJK-capable font *from the
# host* into THIS process's font database so Qt glyph fallback can draw
# \u8d5e\u6210/\u53cd\u5bf9/\u5df2\u6295\u00b7\u8d5e\u6210/\u5df2\u6295\u00b7\u53cd\u5bf9/\u4e0d\u53ef\u6295. This touches only this test process
# (QFontDatabase.addApplicationFont) -- NOT product fonts, NOT global env config.
_CJK_FONT_CANDIDATES = (
    "/mnt/c/Windows/Fonts/msyh.ttc",     # Microsoft YaHei
    "/mnt/c/Windows/Fonts/msyhbd.ttc",
    "/mnt/c/Windows/Fonts/simhei.ttf",   # SimHei
    "/mnt/c/Windows/Fonts/msjh.ttc",     # Microsoft JhengHei
    "/mnt/c/Windows/Fonts/simsun.ttc",   # SimSun
    "/mnt/c/Windows/Fonts/Deng.ttf",     # DengXian
)
_CJK_FONTS_STATE = {"loaded_families": [], "loaded_paths": []}


def _ensure_cjk_fonts():
    """Register a CJK-capable font for this process (fail-closed if none load)."""
    if _CJK_FONTS_STATE["loaded_families"]:
        return _CJK_FONTS_STATE
    from PySide6.QtGui import QFontDatabase
    for path in _CJK_FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        fid = QFontDatabase.addApplicationFont(path)
        if fid == -1:
            continue
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            _CJK_FONTS_STATE["loaded_paths"].append(path)
            _CJK_FONTS_STATE["loaded_families"].extend(families)
    assert _CJK_FONTS_STATE["loaded_families"], (
        "R-01: no CJK font could be registered; candidates="
        + ", ".join(_CJK_FONT_CANDIDATES)
    )
    return _CJK_FONTS_STATE


class _AnomalyStore(QObject):
    """ForumStage store exposing contract-BOUNDARY triumph rows (SA ruling 2026-10-12).

    Rows exercise the R2-01 boundary (``SA-Ruling-viewer_vote-boundary-2026-10-12.md``
    §2/§3): ``viewer_vote`` key MISSING, or key present with a NON-BOOL value
    (str/number), while ``action.state == 'actionable'``.

    Boundary (authoritative):
      * key MISSING                        -> anomaly -> fail-closed ("\u4e0d\u53ef\u6295", no action)
      * present NON-BOOL value ("yes"/1)   -> anomaly -> fail-closed ("\u4e0d\u53ef\u6295", no action)
      * present-key ``None``               -> QML ``null``/``undefined`` -> LEGAL abstention
                                              (dual action); NOT an anomaly. A Python dict
                                              cannot carry JS ``undefined``, so present-key
                                              ``undefined`` can only originate from ``None``.
    """

    forumViewChanged = Signal()

    _ROWS = [
        {"war_id": "anomaly-missing", "name": "\u5f02\u5e38\u6218\u4e89",
         "commander_name": "\u7532", "commander_faction_id": "f1", "soldier_share": 5,
         "action": {"state": "actionable", "reason": "ok"}},  # viewer_vote key MISSING
        {"war_id": "anomaly-nonbool", "name": "\u975e\u5e03\u5c14\u6218\u4e89",
         "commander_name": "\u4e59", "commander_faction_id": "f1", "soldier_share": 3,
         "action": {"state": "actionable", "reason": "ok"}, "viewer_vote": "yes"},
        {"war_id": "anomaly-nonbool-num", "name": "\u6570\u503c\u5f02\u5e38\u6218\u4e89",
         "commander_name": "\u4e19", "commander_faction_id": "f1", "soldier_share": 4,
         "action": {"state": "actionable", "reason": "ok"}, "viewer_vote": 1},
    ]

    def __init__(self, rows=None):
        super().__init__()
        self._rows = [dict(r) for r in (rows if rows is not None else self._ROWS)]
        # Records any ``doVoteTriumph`` invocation: a fail-closed (anomaly) leg must
        # NEVER reach this slot (it would be a fail-OPEN write).
        self.vote_calls = []

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return [dict(r) for r in self._rows]

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumViewerLandRequests(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumLandAllocation(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarEvents(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumViewerContractBids(self):
        return []

    @Property(dict, notify=forumViewChanged)
    def forumResult(self):
        return {}

    @Property(dict, notify=forumViewChanged)
    def forumView(self):
        return {}

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self):
        return False

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self):
        return "market"

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandSaleTotal(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandPricePerUnit(self):
        return 10

    @Property(bool, notify=forumViewChanged)
    def forumHasActiveWar(self):
        return False

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self):
        return True

    # Shell page router: GameShell gates the ForumStage container on
    # ``sessionStore.selectedPhaseId === "forum"`` -- without it the whole stage
    # subtree renders INVISIBLE (visible==false), which would make every
    # visibility assertion vacuous.
    @Property(str, notify=forumViewChanged)
    def selectedPhaseId(self):
        return "forum"

    @Property(str, notify=forumViewChanged)
    def selectedPhaseName(self):
        return "\u5e7f\u573a"

    @Property(dict, notify=forumViewChanged)
    def selectedPhaseSummary(self):
        return {}

    @Slot("QVariant", "QVariant", result=dict)
    def doBuyLand(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", "QVariant", result=dict)
    def doPlaceBid(self, figure_id, contract_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doRecruitFigure(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", result=dict)
    def doRetireFigure(self, figure_id):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doCompleteForumStep(self):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doVoteTriumph(self, war_id, approved):
        # Sentinel: reaching this slot from an ANOMALY leg is a fail-open bug -- the QML
        # handler guard (``!rowVoteDefined``) must early-return first.
        self.vote_calls.append((str(war_id), bool(approved)))
        return {"success": False, "message": "anomaly-should-not-be-called"}

    @Slot(result=dict)
    def doResolveForum(self):
        return {"success": False, "message": "mock"}


def _install_qt_warning_filter():
    """Silence the benign QML 'of null' binding-teardown noise emitted when previous
    engines are destroyed; genuine QML messages are still forwarded to stderr."""
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def _handler(_mode, _context, message):
            if "of null" in message:
                return
            sys.stderr.write(message + "\n")

        qInstallMessageHandler(_handler)
    except Exception:
        pass


_install_qt_warning_filter()

OUT_W = 1440
OUT_H = 900
# Candidate tall viewport heights: the forum market panel is laid out fully (so the last
# section — 🏆 凯旋投票 — is rendered in-frame without relying on a programmatic scroll,
# which does not reflect into an offscreen ``grabWindow()``), then the frame is cropped to
# the 1440x900 contract viewport around the triumph row.
_VIEWPORT_HEIGHTS = (900, 1200, 1600, 2200)

LBL_FOR = "\u8d5e\u6210"                                # 赞成
LBL_AGAINST = "\u53cd\u5bf9"                            # 反对
LBL_VOTED_FOR = "\u5df2\u6295\u00b7\u8d5e\u6210"        # 已投·赞成
LBL_VOTED_AGAINST = "\u5df2\u6295\u00b7\u53cd\u5bf9"    # 已投·反对
LBL_BLOCKED = "\u4e0d\u53ef\u6295"                      # 不可投


class _DummyGuiApp:
    """Minimal guiApp context stub (nav/quit hooks unused offscreen)."""


def _get_app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine(store):
    """Build an offscreen QQmlApplicationEngine bound to the real ``GuiSessionStore``.

    Verbatim-adapted from the ratified WP-J DIRECT_PRODUCTION harness
    (``test_wpj_groupb_render_evidence.py::_create_engine``): same product, same
    context wiring (``theme`` / ``sessionStore`` / ``guiApp`` + registered models).
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    _get_app()
    _ensure_cjk_fonts()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", _DummyGuiApp())
    engine._test_refs = theme
    _ENGINES.append(engine)
    return engine, qml_dir


def _as_quick_window(obj):
    """Return ``obj`` typed as QQuickWindow when possible (engine root may be QWindow)."""
    try:
        from PySide6.QtQuick import QQuickWindow
        if isinstance(obj, QQuickWindow):
            return obj
    except Exception:
        pass
    return obj


def _content_root(window):
    """Return the window's root QQuickItem (contentItem) regardless of root wrapper type."""
    try:
        ci = window.contentItem()
        if ci is not None:
            return ci
    except Exception:
        pass
    try:
        from PySide6.QtQuick import QQuickItem
        return window.findChild(QQuickItem)
    except Exception:
        return None


def _quick_window_of(window):
    """Resolve a QQuickWindow for a synchronous scene-graph grab."""
    try:
        ci = _content_root(window)
        if ci is not None:
            qw = ci.window()
            if qw is not None and hasattr(qw, "grabWindow"):
                return qw
    except Exception:
        pass
    return window if hasattr(window, "grabWindow") else None


def _load_window(engine):
    """Load the real ``Main.qml`` offscreen and return the (re-wrapped) root window."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication

    _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    return _as_quick_window(roots[0])


def _resize(window, width, height):
    from PySide6.QtGui import QGuiApplication
    try:
        if not window.isVisible():
            window.show()
    except Exception:
        pass
    try:
        window.setWidth(width)
        window.setHeight(height)
    except Exception:
        pass
    for _ in range(4):
        QGuiApplication.processEvents()


def _grab(window, out_png, width, height):
    """Offscreen ``QQuickWindow.grabWindow()`` with a bounded poll/retry loop (fail-closed)."""
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication

    app = _get_app()
    result = []
    out_dir = os.path.dirname(out_png)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    MAX_ATTEMPTS = 150
    RETRY_INTERVAL_MS = 100
    attempts = {"n": 0}

    def finish(value):
        if not result:
            result.append(value)
        QCoreApplication.quit()

    def do_grab():
        if result:
            return
        attempts["n"] += 1
        try:
            _resize(window, width, height)
            try:
                window.requestUpdate()
            except Exception:
                pass
            QGuiApplication.processEvents()

            img = None
            qw = _quick_window_of(window)
            if qw is not None and qw.width() > 0 and qw.height() > 0:
                _GRAB_STATE["method"] = type(qw).__name__ + ".grabWindow"
                img = qw.grabWindow()
            if img is None or img.isNull():
                _GRAB_STATE["method"] = "screen.grabWindow"
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    img = scr.grabWindow(int(window.winId()))

            if img is not None and not img.isNull():
                _GRAB_STATE["window_type"] = type(window).__name__
                _GRAB_STATE["attempt"] = attempts["n"]
                finish({"img": img, "w": img.width(), "h": img.height()})
                return

            if attempts["n"] >= MAX_ATTEMPTS:
                finish(None)
            else:
                QTimer.singleShot(RETRY_INTERVAL_MS, do_grab)
        except Exception as exc:  # noqa: BLE001
            finish("exc:" + type(exc).__name__ + ":" + str(exc))

    QTimer.singleShot(200, do_grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))
    app.exec()
    return result[0] if result else None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_items(root):
    """BFS over Qt items via shiboken-wrapped childItems (ratified pattern)."""
    try:
        from PySide6.QtQuick import QQuickItem
        import shiboken6
        ptr = shiboken6.Shiboken.getCppPointer(root)[0]
        start = shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        start = root
    pending = [start]
    out = []
    while pending:
        item = pending.pop()
        if item is None:
            continue
        out.append(item)
        try:
            pending.extend(item.childItems())
        except Exception:
            pass
    return out


def _find_object(root, name):
    if root is None:
        return None
    for item in _iter_items(root):
        try:
            if item.property("objectName") == name:
                return item
        except Exception:
            continue
    return None


def _find_text_item(root, text):
    for item in _iter_items(root):
        try:
            if item.property("text") == text:
                return item
        except Exception:
            continue
    return None


def _button_state(text_item):
    """``{"visible": bool, "enabled": bool|None}`` for a row action button.

    The action label Text's parent is the button Rectangle; its MouseArea child is the
    clickable face (mirrors ``_button_mousearea`` in the ratified row test). ``visible`` is
    the button Rectangle's local visibility.
    """
    if text_item is None:
        return None
    try:
        btn = text_item.parentItem()
    except Exception:
        return None
    if btn is None:
        return None
    visible = bool(btn.property("visible"))
    enabled = None
    try:
        for child in btn.childItems():
            if "MouseArea" in child.metaObject().className():
                enabled = bool(child.property("enabled"))
                break
    except Exception:
        enabled = None
    return {"visible": visible, "enabled": enabled}


def _delegate_of(item):
    """Walk up from a rendered item to its ``MarketActionRow`` delegate.

    The delegate is the ancestor that declares ``secondActionVisible`` (a QML property
    only the row component carries). Returns ``None`` when not found.
    """
    cur = item
    guard = 0
    while cur is not None and guard < 16:
        guard += 1
        try:
            if cur.property("secondActionVisible") is not None:
                return cur
        except Exception:
            pass
        try:
            cur = cur.parentItem()
        except Exception:
            return None
    return None


def _qml_eval_str(item, expression):
    """Evaluate a QML ``expression`` in ``item``'s context; return its value (or an
    ``ERR:``/``EXC:`` tag). Used to observe the ACTUAL QML-side bridge form of
    ``modelData.viewer_vote`` (TC-4): Python ``None`` surfaces as ``null`` or
    ``undefined``, which ``property()`` cannot tell apart (both map to ``None``), so a
    string-discriminant expression is required.
    """
    try:
        from PySide6.QtQml import QQmlEngine, QQmlExpression
        ctx = QQmlEngine.contextForObject(item)
        if ctx is None:
            return None
        expr = QQmlExpression(ctx, item, expression)
        val = expr.evaluate()
        if isinstance(val, (tuple, list)) and len(val) == 2:
            # PySide6 may return (value, ok/undefined-flag).
            val = val[0]
        if expr.hasError():
            return "ERR:" + str(expr.error())
        return val
    except Exception as exc:  # noqa: BLE001
        return "EXC:" + type(exc).__name__


def _viewer_vote_bridge(delegate):
    """``(key_present, qml_form)`` for a triumph delegate's ``modelData.viewer_vote``.

    ``key_present`` is read from the row's own QML predicate (``rowVoteKeyPresent``);
    ``qml_form`` is in {"undefined","null","bool:true","bool:false","other:<v>"}.
    """
    if delegate is None:
        return None, None
    key_present = None
    try:
        key_present = delegate.property("rowVoteKeyPresent")
    except Exception:
        key_present = None
    form = _qml_eval_str(
        delegate,
        "(modelData.viewer_vote === undefined) ? 'undefined'"
        " : ((modelData.viewer_vote === null) ? 'null'"
        " : ((modelData.viewer_vote === true) ? 'bool:true'"
        " : ((modelData.viewer_vote === false) ? 'bool:false'"
        " : ('other:' + String(modelData.viewer_vote)))))",
    )
    return key_present, form


def _emit_qml_signal(item, name):
    """Emit a QML-declared signal (``signal triggered()``) on ``item``.

    Returns a short method tag on success, else ``None``. Used as a POSITIVE-CONTROL
    harness capability -- it must be able to drive a delegate's ``onTriggered`` handler
    (proven on a LEGAL row) before an anomaly no-write assertion is meaningful.
    """
    try:
        sig = getattr(item, name, None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit()
            return "bound-signal.emit"
    except Exception:
        pass
    try:
        from PySide6.QtCore import QMetaObject
        if QMetaObject.invokeMethod(item, name):
            return "QMetaObject.invokeMethod"
    except Exception:
        pass
    return None


def _render_scope(store):
    """Create an offscreen engine bound to ``store`` and return the ``forumStage`` scope.

    The window is shown/resized (as ``_capture_cell`` does) so item layout is settled and
    the stage's shell-gated visibility is real.
    """
    engine, _ = _create_engine(store)
    window = _load_window(engine)
    _resize(window, OUT_W, OUT_H)
    scope = _find_object(_content_root(window), "forumStage")
    assert scope is not None, "forumStage not found in rendered tree"
    return scope


def _mock_row(war_id, name, has_key, value=None):
    """A mock actionable triumph row; ``has_key`` controls ``viewer_vote`` key presence."""
    row = {"war_id": war_id, "name": name, "commander_name": "\u7532",
           "commander_faction_id": "f1", "soldier_share": 5,
           "action": {"state": "actionable", "reason": "ok"}}
    if has_key:
        row["viewer_vote"] = value
    return row


def _tc1_base_row():
    """The SINGLE base DTO for TC-1. BOTH TC-1 inputs are derived from THIS dict only.

    TC-1 must isolate the ``viewer_vote`` key-PRESENCE dimension: row A keeps the key,
    row B deletes it, and every OTHER field is byte-identical (proven mechanically).
    """
    return {
        "war_id": "tc1-base",
        "name": "\u5728\u573a\u6218\u4e89",
        "commander_name": "\u7532",
        "commander_faction_id": "f1",
        "soldier_share": 5,
        "action": {"state": "actionable", "reason": "ok"},
        "viewer_vote": None,
    }


def _assert_rows_identical_except(row_a, row_b, key):
    """Mechanically prove two row DTOs are identical EXCEPT for exactly one key.

    Returns ``(only_in_a, only_in_b, changed_shared)`` for the raw identity record and
    raises AssertionError if the two rows differ on ANY other key or on ANY value.
    """
    keys_a, keys_b = set(row_a), set(row_b)
    only_in_a = sorted(keys_a - keys_b)
    only_in_b = sorted(keys_b - keys_a)
    changed_shared = sorted(k for k in (keys_a & keys_b) if row_a[k] != row_b[k])
    assert only_in_a == [key], (
        "TC-1 isolation: A must have exactly one extra key %r" % key, only_in_a)
    assert only_in_b == [], ("TC-1 isolation: B must not add any key", only_in_b)
    assert changed_shared == [], (
        "TC-1 isolation: shared fields must be identical", changed_shared)
    return only_in_a, only_in_b, changed_shared


def _scene_y(item):
    try:
        from PySide6.QtCore import QPointF
        return float(item.mapToScene(QPointF(0, 0)).y())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# State construction (REAL production chain; No-Test-Assisted-Transition)
# ---------------------------------------------------------------------------

def _build(open_market, vote, readonly_mode):
    """Create a real session, real store, and drive the target cell via production actions.

    - ``open_market``: ``forum_api.open_market`` (retirement -> market sub-step).
    - ``vote``: ``store.doVoteTriumph(str(war_id), True|False)`` (real write slot).
    - ``readonly_mode``: hand the turn to another player so the action projection turns
      ``readonly`` while the viewer's settled vote remains (forced overlap counter-example:
      readonly + 已投 are independent dimensions).
    """
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    faction_id = state.get_player(viewer).faction_id
    commander = next(m for m in state.get_living_members() if m.faction_id == faction_id)

    war = War(
        id="tvas-render-war", name="\u51ef\u65cb\u6e32\u67d3\u6218\u4e89",
        strength=5, threat_level=3,
        rewards={"treasury": 100, "land": 0, "family_prestige": 0},
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.RESOLVED
    war.set_soldier_share(12)
    war.set_triumph_commander(commander.id)
    state.get_war_system()._war_discard.append(war)

    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("forum")

    if open_market:
        assert forum_api.open_market(state, viewer)["success"]
        store._refresh_forum_view()
    if vote is not None:
        assert store.doVoteTriumph(str(war.id), vote)["success"]
    if readonly_mode:
        other = next(p.player_id for p in state.get_all_players() if p.player_id != viewer)
        state.set_current_player(other)
        store._refresh_forum_view()
    return store, state, viewer, war


def _assert_cell(tag, proof, expected):
    kind = expected["kind"]

    def present(label):
        st = proof.get(label)
        return st is not None and st["visible"]

    def enabled(label):
        st = proof.get(label)
        return st is not None and st["enabled"]

    if kind == "dual":
        assert present(LBL_FOR) and enabled(LBL_FOR), (tag, proof)
        assert present(LBL_AGAINST) and enabled(LBL_AGAINST), (tag, proof)
        assert not present(LBL_VOTED_FOR) and not present(LBL_VOTED_AGAINST), (tag, proof)
        assert not present(LBL_BLOCKED), (tag, proof)
    elif kind == "voted_for":
        assert present(LBL_VOTED_FOR) and not enabled(LBL_VOTED_FOR), (tag, proof)
        assert not present(LBL_VOTED_AGAINST), (tag, proof)
        assert not present(LBL_FOR) and not present(LBL_AGAINST), (tag, proof)
        assert not present(LBL_BLOCKED), (tag, proof)
    elif kind == "voted_against":
        assert present(LBL_VOTED_AGAINST) and not enabled(LBL_VOTED_AGAINST), (tag, proof)
        assert not present(LBL_VOTED_FOR), (tag, proof)
        assert not present(LBL_FOR) and not present(LBL_AGAINST), (tag, proof)
        assert not present(LBL_BLOCKED), (tag, proof)
    elif kind == "readonly":
        assert present(LBL_BLOCKED) and not enabled(LBL_BLOCKED), (tag, proof)
        assert not present(LBL_FOR) and not present(LBL_AGAINST), (tag, proof)
        assert not present(LBL_VOTED_FOR) and not present(LBL_VOTED_AGAINST), (tag, proof)
    else:  # pragma: no cover
        raise AssertionError(kind)


def _capture_cell(tag, open_market, vote, readonly_mode, expected):
    store, state, viewer, war = _build(open_market, vote, readonly_mode)

    # C-1/C-4: verify the cell was reached via the real producer projection.
    view = forum_api.get_forum_view(state, viewer)
    assert view["success"], view.get("message")
    rows = view["data"]["triumph_wars"]
    assert rows and rows[0]["war_id"] == str(war.id), (tag, rows)
    action_state = rows[0]["action"]["state"]
    viewer_vote = rows[0]["viewer_vote"]
    assert action_state == expected["action"], (tag, action_state, expected)
    assert viewer_vote == expected["viewer_vote"], (tag, viewer_vote, expected)

    engine, _ = _create_engine(store)
    name = f"tvas-triumph-{tag}-{OUT_W}x{OUT_H}.png"
    out_png = os.path.join(EVIDENCE_BASE, "captures", name)

    window = _load_window(engine)
    scope = _find_object(_content_root(window), "forumStage")
    assert scope is not None, f"forumStage not found in rendered tree for {tag}"
    anchor = _find_text_item(scope, expected["anchor"])
    if anchor is None:
        seen_texts = []
        for it in _iter_items(scope):
            try:
                t = it.property("text")
                if isinstance(t, str) and t:
                    seen_texts.append(t)
            except Exception:
                pass
        raise AssertionError(
            (tag, "anchor label %r not found" % expected["anchor"], seen_texts)
        )

    diag = {
        "selected_phase_id": str(store.selectedPhaseId),
        "forum_current_step": str(store.forumCurrentStep),
        "forum_stage_visible_local": bool(scope.property("visible")),
        "forum_stage_isVisible": bool(scope.isVisible()),
        "has_triumph_title": _find_text_item(scope, "\U0001f3c6 \u51ef\u65cb\u6295\u7968") is not None,
    }

    # Find a tall-enough viewport in which the triumph row is fully laid out in-frame.
    used_h = None
    rect = None
    for h in _VIEWPORT_HEIGHTS:
        _resize(window, OUT_W, h)
        rect = _scene_rect(anchor)
        if rect is not None and rect["y"] + rect["h"] <= h - 1 and rect["y"] >= 0:
            used_h = h
            break
    assert used_h is not None, (tag, "triumph row not laid out in any candidate viewport", rect)

    cap = _grab(window, out_png, OUT_W, used_h)
    assert isinstance(cap, dict), (tag, "grab failed", cap)
    img = cap["img"]

    # Crop the 1440x900 contract frame around the anchor (kept in-frame).
    qimg = img.toImage() if hasattr(img, "toImage") else img
    anchor_y = rect["y"]
    y0 = int(round(anchor_y + rect["h"] / 2.0 - OUT_H / 2.0))
    y0 = max(0, min(y0, used_h - OUT_H))
    crop = qimg.copy(0, y0, OUT_W, OUT_H)
    assert not crop.isNull(), (tag, "crop is null")
    assert crop.width() == OUT_W and crop.height() == OUT_H, (tag, crop.width(), crop.height())
    crop.save(out_png)

    # Anchor must be inside the cropped frame.
    anchor_in_frame = {
        "x": round(rect["x"], 1),
        "y": round(anchor_y - y0, 1),
        "w": round(rect["w"], 1),
        "h": round(rect["h"], 1),
    }
    assert 0 <= anchor_in_frame["y"] and anchor_in_frame["y"] + anchor_in_frame["h"] <= OUT_H, (
        tag, "anchor not inside cropped frame", anchor_in_frame
    )

    proof = {
        lbl: _button_state(_find_text_item(scope, lbl))
        for lbl in (LBL_FOR, LBL_AGAINST, LBL_VOTED_FOR, LBL_VOTED_AGAINST, LBL_BLOCKED)
    }
    _assert_cell(tag, proof, expected)

    # TC-4: pin the ACTUAL QML-side bridge form of this row's ``viewer_vote``. This is the
    # value-layer proof that the producer's Python ``None`` reaches QML as ``null`` or
    # ``undefined`` -- i.e. "legal abstention" and "missing key" are value-indistinguishable
    # and only key PRESENCE discriminates.
    delegate = _delegate_of(anchor)
    vote_key_present, vote_qml_form = _viewer_vote_bridge(delegate)

    # Objective visual certification: the anchor button's rendered background pixel must
    # not contradict its asserted enabled/disabled state (fail closed on a wrong palette).
    btn_rgb, btn_palette = None, None
    btn = anchor.parentItem()
    brect = _scene_rect(btn) if btn is not None else None
    if brect is not None:
        cx = int(brect["x"] + 6)
        cy = int(brect["y"] - y0 + 3)
        if 0 <= cx < crop.width() and 0 <= cy < crop.height():
            col = crop.pixelColor(cx, cy)
            btn_rgb = [col.red(), col.green(), col.blue()]
            btn_palette = _nearest_palette(
                tuple(btn_rgb), {"enabled": _ENABLED_BG, "disabled": _DISABLED_BG}
            )
    expected_palette = "enabled" if expected["kind"] == "dual" else "disabled"
    assert btn_palette in (None, expected_palette), (
        tag, "anchor button pixel palette contradicts state", btn_rgb, btn_palette, expected_palette
    )

    png_exists = os.path.exists(out_png)
    row = {
        "fixture": "test_tvas_triumph_render_evidence.py",
        "frame": tag,
        "phase": "forum",
        "viewport": [OUT_W, OUT_H],
        "render_viewport": [OUT_W, used_h],
        "state_prep": {
            "open_market": open_market,
            "vote": vote,
            "readonly_mode": readonly_mode,
        },
        "route": "DIRECT_PRODUCTION",
        "grab_state": dict(_GRAB_STATE),
        "diag": diag,
        "anchor_in_frame": anchor_in_frame,
        "anchor_button_rgb": btn_rgb,
        "anchor_button_palette": btn_palette,
        "dto": {"action": rows[0]["action"], "viewer_vote": viewer_vote},
        "viewer_vote_key_present": vote_key_present,
        "viewer_vote_qml_value": vote_qml_form,
        "proof": proof,
        "png": name if png_exists else None,
        "png_path": out_png if png_exists else None,
        "png_sha256": _sha256(out_png) if png_exists else None,
        "capture_ok": bool(png_exists and crop is not None and not crop.isNull()),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(out_png[:-4] + ".runtime.json", "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return row


_ENABLED_BG = (132, 37, 10)      # "#84250A"
_DISABLED_BG = (214, 185, 133)   # "#D6B985"


def _nearest_palette(rgb, palette, tol=70):
    for name, ref in palette.items():
        if all(abs(a - b) <= tol for a, b in zip(rgb, ref)):
            return name
    return None


def _scene_rect(item):
    """Scene rect {x,y,w,h} for an item (None on failure)."""
    try:
        from PySide6.QtCore import QPointF
        p = item.mapToScene(QPointF(0, 0))
        return {"x": float(p.x()), "y": float(p.y()),
                "w": float(item.width()), "h": float(item.height())}
    except Exception:
        return None


def _sha_or_none(path):
    try:
        return _sha256(path)
    except OSError:
        return None


def _identity_block():
    """R-05: candidate(seven-file write-set) / test / design three-way SHA binding."""
    cand = {rel: _sha_or_none(os.path.join(PROJECT_ROOT, rel)) for rel in _CANDIDATE_FILES}
    design = {rel: _sha_or_none(os.path.join(TASK_DIR, rel)) for rel in _DESIGN_FILES}
    harness_rel = "src/tests/test_gui/test_tvas_triumph_render_evidence.py"
    return {
        "candidate": {
            "branch": "task/gui-beta-r1-tvas",
            "head": "4c1ec8b",
            "product_root": PROJECT_ROOT,
            "files": cand,
        },
        "test": {"harness": harness_rel, "harness_sha256": cand.get(harness_rel)},
        "design": {"task_dir": TASK_DIR, "files": design},
    }


def _visible_against_in(root):
    """Count visible ``\u53cd\u5bf9`` controls inside one item subtree (per-row identity)."""
    n = 0
    for item in _iter_items(root):
        try:
            if item.property("text") == LBL_AGAINST:
                box = item.parentItem()
                if box is not None and box.property("visible"):
                    n += 1
        except Exception:
            pass
    return n


def _visible_against_count(scope):
    return _visible_against_in(scope)


def test_render_fc13_six_cell_matrix():
    _get_app()
    _ensure_cjk_fonts()
    os.makedirs(os.path.join(EVIDENCE_BASE, "captures"), exist_ok=True)

    frames = [
        _capture_cell("1-actionable-null", True, None, False,
                      {"kind": "dual", "action": "actionable", "viewer_vote": None,
                       "anchor": LBL_FOR}),
        _capture_cell("2-actionable-for", True, True, False,
                      {"kind": "voted_for", "action": "actionable", "viewer_vote": True,
                       "anchor": LBL_VOTED_FOR}),
        _capture_cell("3-actionable-against", True, False, False,
                      {"kind": "voted_against", "action": "actionable", "viewer_vote": False,
                       "anchor": LBL_VOTED_AGAINST}),
        _capture_cell("4-readonly-null", False, None, False,
                      {"kind": "readonly", "action": "readonly", "viewer_vote": None,
                       "anchor": LBL_BLOCKED}),
        _capture_cell("5-readonly-for", True, True, True,
                      {"kind": "voted_for", "action": "readonly", "viewer_vote": True,
                       "anchor": LBL_VOTED_FOR}),
        _capture_cell("6-readonly-against", True, False, True,
                      {"kind": "voted_against", "action": "readonly", "viewer_vote": False,
                       "anchor": LBL_VOTED_AGAINST}),
    ]

    # TC-4 (bridge identity pin): the PRODUCER always sends the key (forum_api:"viewer_vote");
    # the two abstention cells bridge None to null OR undefined (BOTH legal); the voted
    # cells bridge to the exact JS bool. Value-layer observable, not source-comment-only.
    for f in frames:
        assert f["viewer_vote_key_present"] is True, ("TC-4 key must be present", f["frame"], f["viewer_vote_key_present"])
    for f in (frames[0], frames[3]):
        assert f["viewer_vote_qml_value"] in ("null", "undefined"), (
            "TC-4 abstention bridge form", f["frame"], f["viewer_vote_qml_value"])
    assert frames[1]["viewer_vote_qml_value"] == "bool:true", frames[1]["viewer_vote_qml_value"]
    assert frames[2]["viewer_vote_qml_value"] == "bool:false", frames[2]["viewer_vote_qml_value"]
    assert frames[4]["viewer_vote_qml_value"] == "bool:true", frames[4]["viewer_vote_qml_value"]
    assert frames[5]["viewer_vote_qml_value"] == "bool:false", frames[5]["viewer_vote_qml_value"]

    manifest = {
        "schema": "tvas-triumph-render-manifest/v1",
        "task": "EOR20261012-01",
        "route": "DIRECT_PRODUCTION",
        "viewport": [OUT_W, OUT_H],
        "surface": "ForumStage \u51ef\u65cb\u6295\u7968\u884c (MarketActionRow)",
        "grid": [
            "actionable+null -> [\u8d5e\u6210][\u53cd\u5bf9]",
            "actionable+true -> \u5df2\u6295\u00b7\u8d5e\u6210 (disabled)",
            "actionable+false -> \u5df2\u6295\u00b7\u53cd\u5bf9 (disabled)",
            "readonly+null -> \u4e0d\u53ef\u6295 (disabled)",
            "readonly+true -> \u5df2\u6295\u00b7\u8d5e\u6210 (disabled; \u5df2\u6295\u4f18\u5148)",
            "readonly+false -> \u5df2\u6295\u00b7\u53cd\u5bf9 (disabled; \u5df2\u6295\u4f18\u5148)",
        ],
        "frames": frames,
        "cjk_fonts": dict(_CJK_FONTS_STATE),
        "identity": _identity_block(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    with open(os.path.join(EVIDENCE_BASE, "render-manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    assert len(frames) == 6, frames
    assert all(f["png_sha256"] for f in frames), frames
    assert all(f["capture_ok"] for f in frames), frames


def test_render_fc13_anomaly_dto_fail_closed():
    """TC-2 + TC-3: FC-13 fail-closed boundary (SA ruling 2026-10-12).

    TC-2 (``viewer_vote`` key missing) + TC-3 (present NON-BOOL value domain, >=2 types:
    str ``"yes"`` and number ``1``) with ``action.state == 'actionable'`` MUST fail closed
    (no dual action opened; never misread as \u53cd\u5bf9).

    Boundary anchor = ``viewer_vote`` key PRESENCE; a present-key ``None``/``undefined`` is
    LEGAL abstention (six-cell cell-1) and is NOT an anomaly. The 'present-key undefined'
    anomalous branch is UNREACHABLE (Python dict cannot carry JS ``undefined``).
    """
    _get_app()
    _ensure_cjk_fonts()
    store = _AnomalyStore()
    engine, _ = _create_engine(store)
    window = _load_window(engine)
    scope = _find_object(_content_root(window), "forumStage")
    assert scope is not None, "forumStage not found"

    # Canonical *open-vote* labels must NOT appear on any anomalous (actionable) row.
    assert _find_text_item(scope, LBL_FOR) is None, "anomaly row must not render \u8d5e\u6210"
    assert _find_text_item(scope, LBL_VOTED_FOR) is None
    assert _find_text_item(scope, LBL_VOTED_AGAINST) is None
    # Fail-closed -> \u4e0d\u53ef\u6295 (disabled); never \u53cd\u5bf9.
    blocked = _find_text_item(scope, LBL_BLOCKED)
    assert blocked is not None, "anomaly row must render \u4e0d\u53ef\u6295 (fail-closed)"
    assert _button_state(blocked)["enabled"] is False
    visible_against = _visible_against_count(scope)
    assert visible_against == 0, "anomaly row must not open a visible \u53cd\u5bf9"

    # Every anomaly delegate (one per row) must be closed on BOTH legs.
    blocked_delegates = []
    for item in _iter_items(scope):
        try:
            if (item.property("secondActionVisible") is not None
                    and item.property("actionText") == LBL_BLOCKED):
                blocked_delegates.append(item)
        except Exception:
            pass
    assert len(blocked_delegates) == len(store._rows), (
        "every anomaly row must render a single disabled \u4e0d\u53ef\u6295",
        len(blocked_delegates), len(store._rows))
    for d in blocked_delegates:
        assert d.property("enabledAction") is False, "anomaly primary action must be disabled"
        assert d.property("secondActionVisible") is False, "anomaly must not open \u53cd\u5bf9"
        assert d.property("enabledSecondAction") is False
        assert d.property("rowVoteKeyPresent") in (True, False)

    # SA ruling \u00a76: per-ROW identity. Correlate each anomaly row's delegate by war_id and
    # record the mandated columns for EVERY row (not just the aggregate): viewer_vote_qml_value,
    # rendered_blocked_enabled, rendered_visible_against, doVoteTriumph_called.
    delegate_by_war = {}
    for d in blocked_delegates:
        wid = _qml_eval_str(d, "modelData.war_id")
        if (isinstance(wid, str) and wid
                and not wid.startswith("ERR:") and not wid.startswith("EXC:")):
            delegate_by_war[wid] = d
    assert sorted(delegate_by_war) == sorted(r["war_id"] for r in store._rows), (
        "every anomaly row must be matched to its delegate by war_id",
        sorted(delegate_by_war), [r["war_id"] for r in store._rows])

    rows_out = []
    for r in store._rows:
        wid = r["war_id"]
        d = delegate_by_war[wid]
        key_row, qml_form_row = _viewer_vote_bridge(d)
        emit_for = _emit_qml_signal(d, "triggered")
        emit_against = _emit_qml_signal(d, "triggeredSecondary")
        wrote = any(c[0] == wid for c in store.vote_calls)
        rows_out.append({
            "war_id": wid,
            "action": r["action"],
            "has_viewer_vote_key": "viewer_vote" in r,
            "viewer_vote": r.get("viewer_vote", "<missing>"),
            "viewer_vote_qml_key_present": key_row,
            "viewer_vote_qml_value": qml_form_row,
            "rendered_blocked_enabled": bool(d.property("enabledAction")),
            "rendered_visible_against": _visible_against_in(d),
            "doVoteTriumph_called": bool(wrote),
            "signal_emission": {"triggered": emit_for, "triggeredSecondary": emit_against},
        })

    # No-write: firing the anomaly rows' signals must NEVER reach doVoteTriumph
    # (\u5f02\u5e38\u817f\u672a\u5199\u7968). Emission capability is proven separately in TC-5.
    assert store.vote_calls == [], (
        "anomaly legs must NOT write a vote", store.vote_calls)

    anomaly = {
        "schema": "tvas-fc13-anomaly-dto/v1",
        "tag": "fc13-boundary-fail-closed",
        "check": (
            "SA boundary (2026-10-12): viewer_vote key MISSING OR present NON-BOOL value, "
            "with action.state==actionable -> fail-closed (blocked, no action open). "
            "Present-key None/undefined = LEGAL abstention (six-cell cell-1); the "
            "'present-key undefined anomalous' branch is UNREACHABLE "
            "(Python dict cannot carry JS undefined). NOT 'value === undefined'."
        ),
        "boundary": {
            "discriminator": "viewer_vote key PRESENCE ('viewer_vote' in modelData)",
            "legal_abstention": "key present AND value in {null, undefined}",
            "fail_closed": "key missing OR key present with non-bool value",
        },
        "rows": rows_out,
        "rendered_blocked_present": blocked is not None,
        "rendered_blocked_enabled": _button_state(blocked)["enabled"],
        "rendered_for_present": _find_text_item(scope, LBL_FOR) is not None,
        "rendered_visible_against": visible_against,
        "rendered_blocked_delegate_count": len(blocked_delegates),
        "doVoteTriumph_called": bool(store.vote_calls),
        "route": "MOCK_DTO_ANOMALY (QML fail-closed only; real chain never omits viewer_vote)",
        "cjk_fonts": dict(_CJK_FONTS_STATE),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    with open(os.path.join(EVIDENCE_BASE, "fc13-anomaly-dto.identity.json"),
              "w", encoding="utf-8") as fh:
        json.dump(anomaly, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def test_render_fc13_tc1_key_presence_discriminator():
    """TC-1 (decisive): two rows differing ONLY in the ``viewer_vote`` key PRESENCE.

    present-key ``None`` -> LEGAL abstention -> [\u8d5e\u6210][\u53cd\u5bf9] both visible+enabled.
    key ABSENT           -> anomaly          -> disabled \u4e0d\u53ef\u6295, no \u53cd\u5bf9.
    Both rows carry the same value-layer ``None``; only key presence discriminates.
    """
    _get_app()
    _ensure_cjk_fonts()

    # TC-1 isolation: derive BOTH inputs from ONE base DTO; the two rows differ ONLY in the
    # ``viewer_vote`` key PRESENCE. Mechanically assert every other field/value is identical
    # (no side differences in war_id / name / ... are permitted).
    base = _tc1_base_row()
    row_a = copy.deepcopy(base)
    row_b = copy.deepcopy(base)
    del row_b["viewer_vote"]
    only_in_a, only_in_b, changed_shared = _assert_rows_identical_except(
        row_a, row_b, "viewer_vote")
    shared_fields = sorted(set(row_a) & set(row_b))
    shared_fields_sha256 = hashlib.sha256(
        json.dumps({k: row_a[k] for k in shared_fields},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    store_a = _AnomalyStore([copy.deepcopy(row_a)])
    scope_a = _render_scope(store_a)
    proof_a = {lbl: _button_state(_find_text_item(scope_a, lbl))
               for lbl in (LBL_FOR, LBL_AGAINST, LBL_VOTED_FOR, LBL_VOTED_AGAINST, LBL_BLOCKED)}
    _assert_cell("tc1-present-none", proof_a,
                 {"kind": "dual", "action": "actionable", "viewer_vote": None, "anchor": LBL_FOR})
    d_a = _delegate_of(_find_text_item(scope_a, LBL_FOR))
    key_a, form_a = _viewer_vote_bridge(d_a)
    assert key_a is True, ("TC-1 row A: viewer_vote key must be PRESENT", key_a)
    assert form_a in ("null", "undefined"), ("TC-1 row A: bridge form", form_a)
    against_a = _visible_against_count(scope_a)
    assert against_a >= 1, "TC-1 row A must expose \u53cd\u5bf9"

    store_b = _AnomalyStore([copy.deepcopy(row_b)])
    scope_b = _render_scope(store_b)
    proof_b = {lbl: _button_state(_find_text_item(scope_b, lbl))
               for lbl in (LBL_FOR, LBL_AGAINST, LBL_VOTED_FOR, LBL_VOTED_AGAINST, LBL_BLOCKED)}
    _assert_cell("tc1-key-absent", proof_b,
                 {"kind": "readonly", "action": "actionable", "viewer_vote": None,
                  "anchor": LBL_BLOCKED})
    d_b = _delegate_of(_find_text_item(scope_b, LBL_BLOCKED))
    key_b, _form_b = _viewer_vote_bridge(d_b)
    assert key_b is False, ("TC-1 row B: viewer_vote key must be ABSENT", key_b)
    against_b = _visible_against_count(scope_b)
    assert against_b == 0, "TC-1 row B must not open \u53cd\u5bf9"
    assert store_b.vote_calls == [], "TC-1 row B must not write a vote"

    tc1 = {
        "schema": "tvas-fc13-boundary-tc/v1",
        "tc": "TC-1",
        "check": ("key PRESENCE discriminates legal-abstention (present None) from "
                  "anomaly (key absent); both share value-layer None"),
        "isolation": {
            "method": ("single base DTO; each input is an independent deep-copy; row B "
                       "deletes ONLY the viewer_vote key"),
            "base_row": base,
            "input_a": row_a,
            "input_b": row_b,
            "unique_diff": {
                "only_in_a": only_in_a,
                "only_in_b": only_in_b,
                "changed_shared": changed_shared,
            },
            "shared_fields": shared_fields,
            "shared_fields_sha256": shared_fields_sha256,
        },
        "row_a_present_none": {
            "viewer_vote_key_present": key_a,
            "viewer_vote_qml_value": form_a,
            "rendered": proof_a,
            "opened_against": against_a,
        },
        "row_b_key_absent": {
            "viewer_vote_key_present": key_b,
            "rendered": proof_b,
            "opened_against": against_b,
            "doVoteTriumph_called": bool(store_b.vote_calls),
        },
        "route": "MOCK_DTO_BOUNDARY (QML fail-closed only; real chain always sends the key)",
        "cjk_fonts": dict(_CJK_FONTS_STATE),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    with open(os.path.join(EVIDENCE_BASE, "fc13-boundary-tc1.identity.json"),
              "w", encoding="utf-8") as fh:
        json.dump(tc1, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def test_render_fc13_tc5_legal_present_null_equivalence_and_no_write():
    """TC-5: present-key ``None`` is LEGAL (dual action == TC-1 row A) and the anomaly
    (key-absent) leg writes NO vote.

    Positive control: the SAME signal emission on the LEGAL row DOES reach
    ``doVoteTriumph`` -- so the anomaly no-write result is meaningful, not a silent
    emission failure.
    """
    _get_app()
    _ensure_cjk_fonts()

    store = _AnomalyStore([
        _mock_row("tc5-present", "\u5408\u6cd5\u672a\u6295\u6218\u4e89", True, None),
        _mock_row("tc5-absent", "\u5f02\u5e38\u7f3a\u5931\u6218\u4e89", False),
    ])
    scope = _render_scope(store)

    d_legal = _delegate_of(_find_text_item(scope, LBL_FOR))
    assert d_legal is not None and d_legal.property("actionText") == LBL_FOR, "TC-5 legal row not found"
    assert d_legal.property("enabledAction") is True, "legal present-None must be actionable"
    assert d_legal.property("secondActionVisible") is True, "legal present-None must open \u53cd\u5bf9"
    assert d_legal.property("enabledSecondAction") is True
    key_legal, form_legal = _viewer_vote_bridge(d_legal)
    assert key_legal is True, "TC-5 legal row key must be PRESENT"
    assert form_legal in ("null", "undefined"), ("TC-5 legal bridge form", form_legal)

    d_anom = _delegate_of(_find_text_item(scope, LBL_BLOCKED))
    assert d_anom is not None and d_anom.property("actionText") == LBL_BLOCKED, "TC-5 anomaly row not found"
    assert d_anom.property("enabledAction") is False
    assert d_anom.property("secondActionVisible") is False
    assert d_anom.property("enabledSecondAction") is False

    # No-write (anomaly leg): fire BOTH signals first; nothing may be written.
    emit_anom_for = _emit_qml_signal(d_anom, "triggered")
    emit_anom_against = _emit_qml_signal(d_anom, "triggeredSecondary")
    assert store.vote_calls == [], (
        "TC-5: key-absent/anomaly leg must NOT write a vote", store.vote_calls)

    # Positive control (legal leg): the same emission MUST reach the write slot.
    emit_legal_for = _emit_qml_signal(d_legal, "triggered")
    emit_legal_against = _emit_qml_signal(d_legal, "triggeredSecondary")
    assert emit_legal_for or emit_legal_against, (
        "TC-5: harness could not drive a QML delegate handler (emission capability)")
    assert store.vote_calls == [("tc5-present", True), ("tc5-present", False)], (
        "TC-5 positive control: legal row must write both votes", store.vote_calls)

    tc5 = {
        "schema": "tvas-fc13-boundary-tc/v1",
        "tc": "TC-5",
        "check": ("present-key None is LEGAL (dual action == TC-1 row A) and the anomaly "
                  "(key-absent) leg writes NO vote (doVoteTriumph not reached)"),
        "legal_present_none": {
            "viewer_vote_key_present": key_legal,
            "viewer_vote_qml_value": form_legal,
            "actionText": d_legal.property("actionText"),
            "enabledAction": d_legal.property("enabledAction"),
            "secondActionVisible": d_legal.property("secondActionVisible"),
            "enabledSecondAction": d_legal.property("enabledSecondAction"),
        },
        "anomaly_key_absent": {
            "actionText": d_anom.property("actionText"),
            "enabledAction": d_anom.property("enabledAction"),
            "secondActionVisible": d_anom.property("secondActionVisible"),
        },
        "trigger_emission": {
            "anomaly_triggered": emit_anom_for,
            "anomaly_triggeredSecondary": emit_anom_against,
            "legal_triggered": emit_legal_for,
            "legal_triggeredSecondary": emit_legal_against,
        },
        "writes_recorded": [list(c) for c in store.vote_calls],
        "route": "MOCK_DTO_BOUNDARY (QML fail-closed only; real chain always sends the key)",
        "cjk_fonts": dict(_CJK_FONTS_STATE),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    os.makedirs(EVIDENCE_BASE, exist_ok=True)
    with open(os.path.join(EVIDENCE_BASE, "fc13-boundary-tc5.identity.json"),
              "w", encoding="utf-8") as fh:
        json.dump(tc5, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
