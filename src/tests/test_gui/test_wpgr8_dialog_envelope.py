# src/tests/test_gui/test_wpgr8_dialog_envelope.py
"""WP-G-R8 DA SLICE-R8-02 refit（SA-Design §4.1 **L-D v1.3** / §5.4 / §6 R8-AC-05 / §8.2；FC-UI-05）

弹窗（Dialog）envelope v1.3 + `WIN_MIN`（R8-AC-05；G2-delta-2，Owner 2026-09-21 Q2）：

- 尺寸**内容自适应**：`Wmin=320`、`Wmax=min(round(0.50×W.w), W.w−32)`、
  `Wnat`=最宽单行内容 intrinsic 宽 + 2×padding ⇒ `Dw=clamp(Wnat, Wmin, Wmax)`；
- 高度上限 `Dh ≤ round(0.40×W.h)`（±2px），超限正文内滚（`Hchrome=116`）；
- **唯一位置基准 W = 游戏窗口当前 client rect**（禁最大尺寸/声明父项 rect/上次尺寸/屏幕 rect）；
  每次 open **复位居中**（谓词①中心偏差 ≤1px；谓词②四边落 W 内，容差 0.5px）；
- 可见标题条**可拖动**，拖动中**实时夹取于 W 内**，只改 (x,y)，不改 `Dw/Dh`；
- `Main.qml` `Window` 增 `minimumWidth=1280` / `minimumHeight=720`（`WIN_MIN`）；
- 旧 v1.2 固定框（`min(640,·)` / `min(440,·)`）与极小窗兜底分支**作废**。

> 本文件用**源码 predicate** + **offscreen QML 引擎实测量**取证；真实交互帧族（真指针拖动/重开、
> 背景 panel scene rect 不位移）与两窗渲染 RENDER 归 SO 帧族（`render-index.json` = SO_PENDING）。
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl, Signal, Property, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

_QML_DIR_REL = os.path.join("src", "ui", "gui", "qml")
_SENATE_REL = os.path.join(_QML_DIR_REL, "stages", "SenateStage.qml")
_MAIN_REL = os.path.join(_QML_DIR_REL, "Main.qml")

# L-D v1.3 冻结常量（SA §4.1）
_WMIN = 320
_HCHROME = 116
_WIN_MIN_W = 1280
_WIN_MIN_H = 720


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _wmax(w: float) -> float:
    return min(round(0.50 * w), w - 32)


def _hmax(h: float) -> float:
    return round(0.40 * h)


def _card(i: int, name: str = None) -> dict:
    return {
        "war_id": "w%d" % i,
        "war_name": (name if name is not None else "战争%d" % i),
        "classification": "ongoing",
        "is_real_war": True,
        "war_status": "active",
        "allowed_modes": ["command"],
        "schema_version": 2,
        "authority_by_mode": {"command": "consul_direct"},
        "commander_candidates": [],
        "defaults": {"checked": False, "mode": "command",
                     "target_commander_id": 0, "reinforcement_n": 0},
    }


class _MockStore(QObject):
    """最小 SenateStage 消费面 mock（可注入 errors / war_cards → 驱动弹窗几何 predicate）。"""

    senateViewChanged = Signal()

    def __init__(self, current_step="proposal", war_cards=None, errors=None,
                 errors_by_war=None, parent=None):
        super().__init__(parent)
        self._current_step = current_step
        self._war_cards = war_cards or []
        self._errors = errors or []
        self._by_war = errors_by_war or {}

    @Slot(result=int)
    def _noop(self):
        return 0

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return self._current_step

    @Property(list, notify=senateViewChanged)
    def senateWarCards(self):
        return self._war_cards

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateConsulDirectDecisions(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateVetoCandidateIds(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateVoteResults(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateSubmitErrors(self):
        return self._errors

    @Property(dict, notify=senateViewChanged)
    def senateSubmitErrorsByWar(self):
        return self._by_war

    @Property(bool, notify=senateViewChanged)
    def hasSenateSubmitErrors(self):
        return bool(self._errors)

    @Property(str, notify=senateViewChanged)
    def senateFinalizationWarning(self):
        return ""

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self):
        return False

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self):
        return []

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def governorAppointments(self):
        return {}

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        return {"success": True, "message": "ok"}

    @Slot(result=dict)
    def doSubmitSenateVotes(self):
        return {"success": True, "message": "ok"}

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids):
        return {"success": True, "message": "ok"}


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


# PySide 所有权：engine 被 GC 后窗口即被删除 → 保持存续；mock store 单独持有。
_KEEPALIVE = []
_STORES = []


def tearDownModule():
    app = QGuiApplication.instance()
    for eng in list(_KEEPALIVE):
        for obj in list(eng.rootObjects()):
            try:
                obj.setProperty("visible", False)
                obj.close()
            except Exception:
                pass
    if app is not None:
        for _ in range(3):
            app.processEvents()
    _KEEPALIVE.clear()


def _senate_qml_url_path() -> str:
    return os.path.join(PROJECT_ROOT, _SENATE_REL).replace("\\", "/")


def _load_senate_window(store, width: int, height: int):
    """真实 QML 引擎：Window(W×H) → Loader → SenateStage（anchors fill）。"""
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, _QML_DIR_REL)
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    ctx = engine.rootContext()
    ctx.setContextProperty("theme", theme)
    ctx.setContextProperty("sessionStore", store)

    harness = (
        'import QtQuick 2.15\n'
        'import QtQuick.Window 2.15\n'
        'Window {\n'
        '    id: win\n'
        '    width: %d\n'
        '    height: %d\n'
        '    visible: true\n'
        '    Loader { anchors.fill: parent; source: "%s" }\n'
        '}\n'
    ) % (width, height, _senate_qml_url_path())

    comp = QQmlComponent(engine)
    comp.setData(harness.encode("utf-8"), QUrl.fromLocalFile(os.path.join(qml_dir, "__harness__.qml")))
    assert not comp.isError(), comp.errorString()
    engine.loadData(harness.encode("utf-8"), QUrl.fromLocalFile(os.path.join(qml_dir, "__harness__.qml")))
    for _ in range(3):
        app.processEvents()
    roots = engine.rootObjects()
    assert roots, "harness Window failed to load"
    root = roots[0]
    engine._test_refs = (store, theme, root, comp)
    _STORES.append(store)
    _KEEPALIVE.append(engine)
    return engine, root


def _dialog(root):
    dlg = root.findChild(QObject, "senateValidationDialog")
    assert dlg is not None, "senateValidationDialog not found"
    return dlg


# ===========================================================================
# Part A — 源码 predicate（确定性）
# ===========================================================================

class TestR8DialogEnvelopeSource(unittest.TestCase):
    """R8-AC-05 / L-D v1.3：Dialog envelope 源码面。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE_REL)
        idx = cls.qml.find('objectName: "senateValidationDialog"')
        assert idx >= 0, "senateValidationDialog anchor missing"
        cls.block = cls.qml[idx:idx + 7000]

    def test_old_fixed_dimension_formula_removed(self):
        """v1.2 固定框 Dw=min(640,·)/Dh=min(440,·) 作废。"""
        self.assertNotIn("Math.min(640", self.qml)
        self.assertNotIn("Math.min(440", self.qml)

    def test_window_basis_overlay_anchor(self):
        """唯一基准 W：parent 锚到窗口顶层 Overlay.overlay。"""
        self.assertIn("parent: Overlay.overlay", self.block)

    def test_adaptive_size_and_caps_present(self):
        for marker in ("function ldMaxW()", "function ldMaxH()", "0.50", "0.40",
                       "id: ldWidthMirror", "id: ldHeightMirror",
                       "root.ldWmin", "ldWmin: 320", "ldChrome: 116",
                       "function ldNaturalWidth()", "function ldBodyNaturalHeight("):
            self.assertIn(marker, self.qml, marker)

    def test_centered_reset_on_open(self):
        self.assertIn("function resetDialogPosition()", self.qml)
        self.assertIn("onOpened: resetDialogPosition()", self.qml)

    def test_visible_grip_and_drag_clamp_present(self):
        for marker in ("senateDialogGrip", "DragHandler", "Qt.SizeAllCursor",
                       "onTranslationChanged", "function applyDrag("):
            self.assertIn(marker, self.block, marker)
        # 夹取 helper 在 root 层（Dialog 之前）定义
        self.assertIn("function ldClampX(", self.qml)
        self.assertIn("function ldClampY(", self.qml)

    def test_body_scroll_asneeded_vertical_only(self):
        self.assertIn("ScrollBar.vertical.policy: ScrollBar.AsNeeded", self.block)
        self.assertIn("ScrollBar.horizontal.policy: ScrollBar.AlwaysOff", self.block)

    def test_fixed_header_and_footer_40_and_close_esc(self):
        self.assertIn("Layout.preferredHeight: 40", self.block)
        self.assertIn("战争配置无法提交", self.block)
        self.assertIn("closePolicy: Popup.CloseOnEscape", self.block)
        self.assertIn("senateValidationDialog.close()", self.qml)
        self.assertIn("senateValidationDialog.open()", self.qml)

    def test_no_win_min_literal_inside_dialog_residual(self):
        """WIN_MIN 设置点在 Main.qml（非 Dialog 内硬编码）。"""
        self.assertIn("minimumWidth: %d" % _WIN_MIN_W, _read(_MAIN_REL))
        self.assertIn("minimumHeight: %d" % _WIN_MIN_H, _read(_MAIN_REL))


class TestR8WindowMinSizeSource(unittest.TestCase):
    """WIN_MIN=1280×720：产品级设置点（Main.qml）。"""

    @classmethod
    def setUpClass(cls):
        cls.main = _read(_MAIN_REL)

    def test_minimum_width_height_present(self):
        self.assertIn("minimumWidth: 1280", self.main)
        self.assertIn("minimumHeight: 720", self.main)


# ===========================================================================
# Part B — 可执行几何 predicate（真实 QML 引擎实测量）
# ===========================================================================

class TestR8DialogEnvelopePredicate(unittest.TestCase):
    """R8-AC-05 / L-D v1.3：内容自适应 / 40% 上限 / W 居中（真实引擎测量）。"""

    def _load(self, w, h, cards=None, errors=None, by_war=None, open_dialog=False):
        store = _MockStore(current_step="proposal",
                           war_cards=(cards if cards is not None else [_card(0)]),
                           errors=errors, errors_by_war=by_war)
        engine, root = _load_senate_window(store, w, h)
        dlg = _dialog(root)
        if open_dialog:
            dlg.setProperty("visible", True)
            _get_app().processEvents()
        return root, dlg

    def test_width_content_adaptive_within_min_max(self):
        for (w, h) in ((1440, 900), (1280, 720)):
            root, dlg = self._load(w, h)
            dw = float(dlg.property("width"))
            self.assertGreaterEqual(dw, float(_WMIN) - 0.5, "Dw below Wmin at %dx%d" % (w, h))
            self.assertLessEqual(dw, _wmax(w) + 0.5, "Dw above Wmax at %dx%d" % (w, h))
            # 短内容 → 未封顶到 Wmax（内容自适应，非固定大框）
            self.assertLess(dw, _wmax(w) - 0.5, "short content not adaptive at %dx%d" % (w, h))

    def test_width_caps_to_wmax_for_long_content(self):
        long_name = "超长战争名称" * 20
        errs = [{
            "code": "COMMANDER_CLAIM_DUPLICATE", "scope": "package", "field": "",
            "details": {"claims": [{"war_id": "w0", "commander_id": "c0"}]}, "message": "m",
        }]
        root, dlg = self._load(1440, 900, cards=[_card(0, name=long_name)],
                               errors=errs, by_war={"w0": errs})
        dw = float(dlg.property("width"))
        self.assertAlmostEqual(dw, _wmax(1440), delta=0.5)
        self.assertLessEqual(dw, 1440 - 32 + 0.5)

    def test_height_within_40pct_window(self):
        for (w, h) in ((1440, 900), (1280, 720)):
            root, dlg = self._load(w, h)
            dh = float(dlg.property("height"))
            self.assertGreater(dh, 0)
            self.assertLessEqual(dh, _hmax(h) + 2.0, "Dh above 0.40*W.h at %dx%d" % (w, h))
            self.assertGreaterEqual(dh, float(_HCHROME) - 0.5)

    def test_height_caps_and_body_scrolls_for_long_content(self):
        # 大量（40）真实错误条 → 正文自然高 > HbodyCap → Dh 封顶 round(0.40×W.h)，正文内滚。
        errs = [{"code": "REINFORCEMENT_INVALID", "scope": "w0", "field": "reinforcement_n",
                 "details": {}, "message": "m"} for _ in range(40)]
        root, dlg = self._load(1440, 900, cards=[_card(0)], errors=errs, by_war={"w0": errs},
                               open_dialog=True)
        dh = float(dlg.property("height"))
        self.assertAlmostEqual(dh, _hmax(900), delta=2.0)

    def test_position_centered_and_inside_window_predicates(self):
        for (w, h) in ((1440, 900), (1280, 720)):
            root, dlg = self._load(w, h, open_dialog=True)
            dw = float(dlg.property("width"))
            dh = float(dlg.property("height"))
            x = float(dlg.property("x"))
            y = float(dlg.property("y"))
            # 谓词①：中心偏差 ≤1px
            self.assertLessEqual(abs((x + dw / 2.0) - w / 2.0), 1.0, "center-x at %dx%d" % (w, h))
            self.assertLessEqual(abs((y + dh / 2.0) - h / 2.0), 1.0, "center-y at %dx%d" % (w, h))
            # 谓词②：四边落 W 内（容差 0.5px）
            self.assertGreaterEqual(x, -0.5)
            self.assertGreaterEqual(y, -0.5)
            self.assertLessEqual(x + dw, w + 0.5)
            self.assertLessEqual(y + dh, h + 0.5)

    def test_drag_clamps_inside_window_and_does_not_resize(self):
        w, h = 1440, 900
        root, dlg = self._load(w, h, open_dialog=True)
        dw = float(dlg.property("width"))
        dh = float(dlg.property("height"))
        x0 = float(dlg.property("x"))
        y0 = float(dlg.property("y"))
        # 模拟按下 → 大幅拖动
        dlg.setProperty("_dragStartX", x0)
        dlg.setProperty("_dragStartY", y0)
        dlg.setProperty("_dragX", x0)
        dlg.setProperty("_dragY", y0)
        invoked = QMetaObject.invokeMethod(
            dlg, "applyDrag", Qt.DirectConnection,
            Q_ARG("QVariant", 10000.0), Q_ARG("QVariant", 10000.0))
        self.assertTrue(invoked, "applyDrag not invokable")
        _get_app().processEvents()
        x = float(dlg.property("x"))
        y = float(dlg.property("y"))
        self.assertAlmostEqual(x, w - dw, delta=0.5, msg="drag did not clamp to right edge")
        self.assertAlmostEqual(y, h - dh, delta=0.5, msg="drag did not clamp to bottom edge")
        # 四边仍落 W 内（谓词②）
        self.assertGreaterEqual(x, -0.5)
        self.assertLessEqual(x + dw, w + 0.5)
        self.assertGreaterEqual(y, -0.5)
        self.assertLessEqual(y + dh, h + 0.5)
        # 拖动不改 Dw/Dh
        self.assertAlmostEqual(float(dlg.property("width")), dw, delta=0.5)
        self.assertAlmostEqual(float(dlg.property("height")), dh, delta=0.5)

    def test_reopen_recenters_no_position_memory(self):
        w, h = 1440, 900
        root, dlg = self._load(w, h, open_dialog=True)
        dw = float(dlg.property("width"))
        dh = float(dlg.property("height"))
        x0 = float(dlg.property("x"))
        y0 = float(dlg.property("y"))
        dlg.setProperty("_dragStartX", x0)
        dlg.setProperty("_dragStartY", y0)
        QMetaObject.invokeMethod(dlg, "applyDrag", Qt.DirectConnection,
                                 Q_ARG("QVariant", 600.0), Q_ARG("QVariant", 400.0))
        _get_app().processEvents()
        self.assertNotAlmostEqual(float(dlg.property("x")), x0, delta=1.0)
        # 关闭 → 重开（onOpened 复位）→ 居中（不记忆位置）
        dlg.setProperty("visible", False)
        _get_app().processEvents()
        dlg.setProperty("visible", True)
        _get_app().processEvents()
        x = float(dlg.property("x"))
        y = float(dlg.property("y"))
        self.assertAlmostEqual(x, x0, delta=1.0, msg="reopen did not recenter x")
        self.assertAlmostEqual(y, y0, delta=1.0, msg="reopen did not recenter y")
        self.assertLessEqual(abs((x + dw / 2.0) - w / 2.0), 1.0)
        self.assertLessEqual(abs((y + dh / 2.0) - h / 2.0), 1.0)


class TestR8WindowMinSizeRuntime(unittest.TestCase):
    """WIN_MIN=1280×720：Main.qml 装载后 Window 属性实测。"""

    def test_main_window_minimum_size(self):
        from src.ui.gui.models.candidate_list_model import CandidateListModel
        from src.ui.gui.models.event_list_model import EventListModel
        from src.ui.gui.models.figure_list_model import FigureListModel
        from src.ui.gui.session_store import GuiSessionStore
        from src.api import session_api
        from PySide6.QtQml import qmlRegisterType

        app = _get_app()
        result = session_api.create_gui_prototype_session()
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        store = GuiSessionStore(state)
        store.initialize(result["data"]["human_players"][0])

        qml_dir = os.path.join(PROJECT_ROOT, _QML_DIR_REL)
        engine = QQmlApplicationEngine()
        engine.addImportPath(qml_dir)
        qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
        qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
        qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

        theme_component = QQmlComponent(engine)
        theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
        assert not theme_component.isError(), theme_component.errorString()
        theme = theme_component.create()
        engine.rootContext().setContextProperty("theme", theme)
        engine.rootContext().setContextProperty("sessionStore", store)
        engine.rootContext().setContextProperty("guiApp", _DummyGuiApp())

        engine.load(QUrl.fromLocalFile(os.path.join(PROJECT_ROOT, _MAIN_REL)))
        app.processEvents()
        roots = engine.rootObjects()
        assert roots, "Main.qml loaded with no root object"
        root = roots[0]
        _KEEPALIVE.append(engine)
        _STORES.append(store)
        self.assertEqual(int(root.property("minimumWidth")), _WIN_MIN_W)
        self.assertEqual(int(root.property("minimumHeight")), _WIN_MIN_H)


class _DummyGuiApp(QObject):
    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        return bool(next_player_id)


if __name__ == "__main__":
    unittest.main()
