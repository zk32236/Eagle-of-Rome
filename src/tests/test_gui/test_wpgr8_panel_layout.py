# src/tests/test_gui/test_wpgr8_panel_layout.py
"""WP-G-R8 DA SLICE-R8-03 refit2（SA-Design v1.6 §4.1 U_S + L-1…L-9 + PF-1/2/3 / §5.4 / §4.6；FC-UI-06/07）

**五框模型**布局 + 真实 scroll ownership + Dialog 几何 envelope（R8-AC-05 / 06 / 07；
TDD_REQUIRED = NO，由**可执行几何 predicate** + RENDER 闭合）。

本片锁定（**源码锚点** + **真实 QML 引擎实测量**；交互帧族 RENDER 归 SO）：
- **#1 进度框**：GameShell Senate step bar（InstructionSlot，单行，保真不改）。
- **#2 公示框**（议事/表决合并单框，`senateAnnouncementBox`）：固定标题「元老院议事」
  + 正文 viewport 恰 **5L**（±1）+ 独立 AsNeeded 滑块；结果内容并入同一 body（禁第二框）。
- **#3–5 三子环节框**：占满余量（rowW × Hrow），各自独立内滚，footer 固定不入滚动。
- **L-1 唯一高度算法**：`Hnotice = 20 + Lt + 6 + 5L`；`rowW = U.w − 28`；
  `Hrow = U.h − 28 − Hnotice − 10`；min = preferred = max（等价显式 anchors）；
  **禁** 360/460 clamp、独立 132/78 结果框、外层兜底滚动、Qt 自动压缩、按内容改高。
- **L-3 真实可读 body**：Panel1 主 body `ScrollView`（`senatePanel1BodyScroll`）统一 scroll
  ownership；footer 固定 body 外；`Hbody = Hrow − 95 ≥ 4L`。
- **L-D Dialog envelope（v1.3）**：内容自适应（`Wmin=320`；`Wmax=min(round(0.50×W.w), W.w−32)`）；
  `Dh≤round(0.40×W.h)`；以 W 居中（重开复位）；可见标题条可拖动夹取；header40 / footer40。
- **U_S（v1.6）**：Senate 相位 shell 容器重组（`GameShell.qml` / `StageDesktop.qml`）—— ① 折叠空
  `StageActionSlot`（46→0）② 移除 Content→Action 槽间隔（10→0）③ 让渡 `StageDesktop` 底内边距（18→0）；
  其余相位不变。`U_S.bottom = Region C 外框底缘`；三框 `row.bottom = U_S.h − 14`（PF-1）；
  scene `Δ = E.top − row.bottom ≤ Δ_frozen = 28`（PF-2，两窗可达）。

> 「看起来对」不算证据——本文件用**源码 predicate** + **offscreen QML 引擎实测量**取证；
> 真实交互（wheel/drag、末项 hit）证据归 SO 帧族（`render-index.json` = SO_PENDING）。
"""
import os
import shiboken6
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem

_QML_DIR_REL = os.path.join("src", "ui", "gui", "qml")
_SENATE_REL = os.path.join(_QML_DIR_REL, "stages", "SenateStage.qml")

# L-1 冻结常量（SA §4.1 v1.4）
_A_MARGIN = 14                       # 公示 x=y=14
_ROW_MARGIN = 28                     # rowW = U.w − 28
_ROW_GAP = 10                        # row.y = 14 + Hnotice + 10
_FOOTER_OFFSET = 95                  # Hbody = Hrow − 95（topMargin44 + footer34 + gap7 + bottom10）
_BODY_MIN_L = 4                      # 最低可读 body = 4L
_VOID_ROW_CLAMP = (360, 460)         # 旧 clamp（禁）


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _hnotce(l_title: float, l_body: float) -> float:
    """L-1：Hnotice = 20 + Lt + 6 + 5L。"""
    return 20 + l_title + 6 + 5 * l_body


def _hrow(u_height: float, hnotice: float) -> float:
    """L-1 唯一高度算法（predicate 参考实现；用于断言实测值与公式一致）。"""
    return u_height - _ROW_MARGIN - hnotice - _ROW_GAP


def _card(i: int) -> dict:
    return {
        "war_id": "w%d" % i,
        "war_name": "战争%d" % i,
        "classification": "ongoing",
        "is_real_war": True,
        "war_status": "active",
        "allowed_modes": ["command"],
        "schema_version": 2,
        "authority_by_mode": {"command": "consul_direct"},
        "commander_candidates": [
            {"figure_id": i, "label": "指挥官%d" % i, "eligible_role": "consul"}
        ],
        "defaults": {"checked": False, "mode": "command",
                     "target_commander_id": i, "reinforcement_n": 0},
    }


class _MockStore(QObject):
    """最小 SenateStage 消费面 mock（current_step 可注入 → 跨态几何 predicate）。"""

    senateViewChanged = Signal()

    def __init__(self, current_step="proposal", war_cards=None, parent=None):
        super().__init__(parent)
        self._current_step = current_step
        self._war_cards = war_cards or []
        self._submitted = []

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
        return self._submitted

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
        return []

    @Property(dict, notify=senateViewChanged)
    def senateSubmitErrorsByWar(self):
        return {}

    @Property(bool, notify=senateViewChanged)
    def hasSenateSubmitErrors(self):
        return False

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


# 保持各测试中创建的 engine/window 存续（PySide 所有权：engine 被 GC 后窗口即被删除），
# 并单独持有 mock store——使窗口销毁时 sessionStore 仍非 null（避免退出期绑定报错噪声）。
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
    _KEEPALIVE.clear()  # store 仍由 _STORES 持有 → 窗口销毁时不产生 null-context 绑定报错


def _senate_qml_url_path() -> str:
    return os.path.join(PROJECT_ROOT, _SENATE_REL).replace("\\", "/")


def _load_window(store, width: int, height: int):
    """真实 QML 引擎：Window(W×H) → Loader → SenateStage（anchors fill）。

    以 Window 为 root 才能在 offscreen 下真实解析 layout（standalone item 无 window 不 polish）。
    返回 (engine, window_root)。
    """
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


def _qitem(obj):
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


# ===========================================================================
# Part A — 源码 predicate（确定性）
# ===========================================================================

class TestR8FiveFrameRowGeometrySource(unittest.TestCase):
    """R8-AC-06 / L-1：五框模型唯一高度算法（源码面）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE_REL)
        idx = cls.qml.find('objectName: "senateThreePanelRow"')
        assert idx >= 0, "senateThreePanelRow anchor missing"
        start = idx
        end = cls.qml.find("SenateWorkPanel {", start)
        assert end > start
        cls.row_block = cls.qml[start:end]

    def test_unique_hrow_algorithm_present(self):
        """L-1：Hrow = U.h − 28 − Hnotice − 10（唯一算法）。"""
        self.assertIn("hNotice: 20 + lTitle + 6 + 5 * lBody", self.qml)
        self.assertIn("Math.round(root.height) - 28 - hNotice - 10", self.qml)
        self.assertIn("rowW: Math.max(1, Math.round(root.width) - 28)", self.qml)

    def test_row_uses_five_frame_anchors(self):
        """行几何 = 显式 anchors（等价 min=preferred=max）；x=14 / y=14+Hnotice+10 / rowW / Hrow。"""
        self.assertIn("x: 14", self.row_block)
        self.assertIn("y: 14 + root.hNotice + 10", self.row_block)
        self.assertIn("width: root.rowW", self.row_block)
        self.assertIn("height: root.hRow", self.row_block)

    def test_no_legacy_clamp_or_results_height(self):
        """旧 360/460 clamp / 按 step·results 改高 / fillHeight 自由竞争已删（step 无关）。"""
        for marker in ("minPanelRowH: 360", "Math.min(460", "? 200", "? 460"):
            self.assertNotIn(marker, self.qml, marker)
        self.assertNotIn("senateCurrentStep", self.row_block)
        self.assertNotIn("fillHeight", self.row_block)

    def test_no_outer_scroll_and_no_standalone_results_frame(self):
        """五框模型：禁外层兜底滚动 / 禁独立 132（或 78）结果框。"""
        self.assertNotIn('objectName: "senateOuterScroll"', self.qml)
        self.assertNotIn("id: senateOuterScroll", self.qml)
        self.assertNotIn('objectName: "senateResultsArea"', self.qml)
        self.assertNotIn('objectName: "senateResultsTitle"', self.qml)
        self.assertNotIn("Layout.maximumHeight: 132", self.qml)
        self.assertNotIn("Layout.maximumHeight: 78", self.qml)

    def test_announcement_box_and_body_present(self):
        """#2 公示框（议事/表决合并单框）+ 正文 viewport 恰 5L 的独立 AsNeeded 滑块。"""
        self.assertIn('objectName: "senateAnnouncementBox"', self.qml)
        self.assertIn('objectName: "senateAnnouncementBody"', self.qml)
        self.assertIn("noticeBodyH: Math.max(1, 5 * lBody)", self.qml)
        idx = self.qml.find('objectName: "senateAnnouncementBody"')
        block = self.qml[idx:idx + 700]
        self.assertIn("ScrollBar.vertical.policy: ScrollBar.AsNeeded", block)
        self.assertIn("ScrollBar.horizontal.policy: ScrollBar.AlwaysOff", block)


class TestR8ScrollOwnershipSource(unittest.TestCase):
    """R8-AC-07 / L-3 / L-7：真实 scroll ownership / clip 链（源码面）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE_REL)

    def test_panel1_main_body_scroll_present(self):
        self.assertIn('objectName: "senatePanel1BodyScroll"', self.qml)
        self.assertIn("id: panel1BodyScroll", self.qml)

    def test_main_body_scroll_owns_explanation_and_war_repeater_and_frozen(self):
        """主 body ScrollView 须在其内容中包住 说明 / War Card Repeater / frozen direct 区 / nonWar。"""
        body = self.qml.find("id: panel1BodyScroll")
        self.assertGreaterEqual(body, 0)
        war_card = self.qml.find("sessionStore.senateWarCards || []) : []", body)
        self.assertGreater(war_card, body)
        frozen = self.qml.find("id: frozenDirectSection", body)
        self.assertGreater(frozen, body)
        nonwar = self.qml.find("root.nonWarProposalOptions()", frozen)
        self.assertGreater(nonwar, frozen)
        footer = self.qml.find("root.selectedProposals()", nonwar)
        self.assertGreater(footer, nonwar)

    def test_old_nonwar_only_inner_scrollview_removed(self):
        """旧只包 nonWar 的局部 ScrollView 已移除——nonWar 列直接作为主 body 内容列。"""
        body = self.qml.find("id: panel1BodyScroll")
        self.assertGreaterEqual(body, 0)
        nonwar = self.qml.find("root.nonWarProposalOptions()", body)
        self.assertGreater(nonwar, 0)
        window = self.qml[max(0, nonwar - 220):nonwar]
        self.assertIn("ColumnLayout {", window)
        self.assertNotIn("ScrollView {", window)

    def test_no_common_scroll_ancestor(self):
        """L-7：无 senateOuterScroll / 无共同滚动祖先（footer 无 Flickable 祖先）。"""
        self.assertNotIn('objectName: "senateOuterScroll"', self.qml)

    def test_results_merged_into_announcement_body(self):
        """L-5：结果内容并入 #2 公示 body（主持/席位之后，三子框之前）——不出现第六框。"""
        body = self.qml.find('objectName: "senateAnnouncementBody"')
        fleet = self.qml.find("root._fleetSummary()")
        row = self.qml.find('objectName: "senateThreePanelRow"')
        self.assertGreater(body, 0)
        self.assertGreater(fleet, body)
        self.assertGreater(row, fleet)

    def test_frozen_and_card_error_subscrolls_retained(self):
        """frozen ≤168 内滚 / 卡错误块 ≤120 内滚保留（产品 R7 §5.7.1）。"""
        self.assertIn("Layout.maximumHeight: 168", self.qml)


class TestR8DialogEnvelopeSource(unittest.TestCase):
    """R8-AC-05 / L-D v1.3：Dialog 几何 envelope（源码面）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _read(_SENATE_REL)
        idx = cls.qml.find('objectName: "senateValidationDialog"')
        cls.block = cls.qml[idx:idx + 2400]

    def test_adaptive_envelope_v13(self):
        self.assertNotIn("Math.min(640", self.qml)
        self.assertNotIn("Math.min(440", self.qml)
        self.assertIn("function ldMaxW()", self.qml)
        self.assertIn("function ldMaxH()", self.qml)
        self.assertIn("ldWmin: 320", self.qml)
        self.assertIn("parent: Overlay.overlay", self.block)

    def test_short_header_present(self):
        self.assertIn("战争配置无法提交", self.block)

    def test_fixed_header_and_footer_40(self):
        self.assertIn("Layout.preferredHeight: 40", self.block)

    def test_close_and_esc_paths_present(self):
        self.assertIn("closePolicy: Popup.CloseOnEscape", self.block)
        self.assertIn("senateValidationDialog.close()", self.qml)
        self.assertIn("senateValidationDialog.open()", self.qml)


# ===========================================================================
# Part B — 可执行几何 predicate（真实 QML 引擎实测量）
# ===========================================================================

class TestR8FiveFrameGeometryPredicates(unittest.TestCase):
    """R8-AC-06：L-1 五框几何不变量（真实引擎测量；容差 ±1px）。"""

    def _measure(self, width, height, step="proposal", cards=None):
        store = _MockStore(current_step=step, war_cards=(cards if cards is not None else [_card(i) for i in range(3)]))
        engine, root = _load_window(store, width, height)
        row = root.findChild(QObject, "senateThreePanelRow")
        box = root.findChild(QObject, "senateAnnouncementBox")
        body = root.findChild(QObject, "senateAnnouncementBody")
        self.assertIsNotNone(row, "senateThreePanelRow not found")
        self.assertIsNotNone(box, "senateAnnouncementBox not found")
        self.assertIsNotNone(body, "senateAnnouncementBody not found")
        stage = box.parent()
        return root, row, box, body, stage

    def test_hrow_matches_formula_at_authorized_test_windows(self):
        """L-1：1440×900 与 1280×720 两测试窗，实测 Hrow == U.h − 28 − Hnotice − 10。"""
        for (w, h) in ((1440, 900), (1280, 720)):
            root, row, box, body, stage = self._measure(w, h)
            u_h = float(root.property("height"))
            hnotice = float(box.property("height"))
            self.assertAlmostEqual(hnotice, _hnotce(float(stage.property("lTitle")),
                                                    float(stage.property("lBody"))), delta=1.0,
                                   msg="Hnotice mismatch at %dx%d" % (w, h))
            self.assertAlmostEqual(float(row.property("height")), _hrow(u_h, hnotice), delta=1.0,
                                   msg="Hrow mismatch at %dx%d" % (w, h))
            # row.bottom = U.h − 14（±1）
            self.assertAlmostEqual(float(row.property("y")) + float(row.property("height")),
                                   u_h - _A_MARGIN, delta=1.0)

    def test_announcement_box_geometry(self):
        """L-1：公示 x=y=14、w=U.w−28、h=Hnotice。"""
        root, row, box, body, stage = self._measure(1440, 900)
        u_w = float(root.property("width"))
        self.assertAlmostEqual(float(box.property("x")), _A_MARGIN, delta=1.0)
        self.assertAlmostEqual(float(box.property("y")), _A_MARGIN, delta=1.0)
        self.assertAlmostEqual(float(box.property("width")), u_w - _ROW_MARGIN, delta=2.0)
        # row y = 14 + Hnotice + 10
        self.assertAlmostEqual(float(row.property("y")),
                               _A_MARGIN + float(box.property("height")) + _ROW_GAP, delta=1.0)

    def test_announcement_body_viewport_exactly_5l(self):
        """L-5：公示正文 viewport 恰 5L（±1）。"""
        root, row, box, body, stage = self._measure(1440, 900)
        lb = float(stage.property("lBody"))
        self.assertAlmostEqual(float(body.property("height")), 5.0 * lb, delta=1.0)

    def test_five_frame_geometry_stable_across_steps(self):
        """L-1：同 U 跨 proposal/vote/veto/results —— Hrow/公示框几何差 ≤1px。"""
        row_h, box_h, box_y = [], [], []
        for step in ("proposal", "senate_vote", "tribune_veto", "results"):
            root, row, box, body, stage = self._measure(1440, 900, step=step)
            row_h.append(float(row.property("height")))
            box_h.append(float(box.property("height")))
            box_y.append(float(box.property("y")))
        self.assertLessEqual(max(row_h) - min(row_h), 1.0, "Hrow varies across steps: %r" % row_h)
        self.assertLessEqual(max(box_h) - min(box_h), 1.0, "Hnotice varies across steps: %r" % box_h)
        self.assertLessEqual(max(box_y) - min(box_y), 1.0, "announcement y varies across steps: %r" % box_y)

    def test_three_panels_equal_geometry(self):
        """L-2：三面板 width=(rowW−24)/3（±2）、height=Hrow（±1）。"""
        root, row, box, body, stage = self._measure(1440, 900)
        panels = [c for c in row.findChildren(QObject)
                  if c.metaObject().className() == "SenateWorkPanel"]
        self.assertEqual(len(panels), 3)
        rw = float(box.property("width"))
        rh = float(row.property("height"))
        for p in panels:
            self.assertAlmostEqual(float(p.property("width")), (rw - 24) / 3.0, delta=2.0)
            self.assertAlmostEqual(float(p.property("height")), rh, delta=1.0)


class TestR8BodyViewportPredicates(unittest.TestCase):
    """R8-AC-06 / L-3：真实可读 body viewport = Hrow − 95 ≥ 4L（真实引擎测量）。"""

    def test_panel1_body_viewport_equals_hrow_minus_95(self):
        store = _MockStore(current_step="proposal", war_cards=[_card(i) for i in range(3)])
        engine, root = _load_window(store, 1440, 900)
        row = root.findChild(QObject, "senateThreePanelRow")
        body = root.findChild(QObject, "senatePanel1BodyScroll")
        box = root.findChild(QObject, "senateAnnouncementBox")
        self.assertIsNotNone(body, "senatePanel1BodyScroll not found")
        hrow = float(row.property("height"))
        bh = float(body.property("height"))
        lb = float(box.parent().property("lBody"))
        self.assertGreaterEqual(bh, float(_BODY_MIN_L) * lb, "Panel1 body below 4L: %r" % bh)
        self.assertAlmostEqual(bh, hrow - _FOOTER_OFFSET, delta=1.0)

    def test_panel1_body_owns_war_cards_under_overflow(self):
        """L-3/L-7：内容溢出时主 body ScrollView 承托 War Card（可滚 extent → 末项可达）。"""
        cards = [_card(i) for i in range(20)]
        store = _MockStore(current_step="proposal", war_cards=cards)
        engine, root = _load_window(store, 1440, 900)
        body = root.findChild(QObject, "senatePanel1BodyScroll")
        self.assertIsNotNone(body)
        content_h = float(body.property("contentHeight"))
        view_h = float(body.property("height"))
        self.assertGreater(content_h, view_h, "expected overflow content to be scrollable")
        repeaters = [c for c in body.findChildren(QObject)
                     if c.metaObject().className().startswith("QQuickRepeater")]
        counts = sorted(int(r.property("count")) for r in repeaters)
        self.assertIn(20, counts, "War Card Repeater(20) must live inside Panel1 main body scroll: %r" % counts)
        war_rep = [r for r in repeaters if int(r.property("count")) == 20][0]
        content_col = war_rep.parent()
        self.assertAlmostEqual(float(content_col.property("height")), content_h, delta=2.0)

    def test_no_outer_scroll_fallback(self):
        """L-7：不存在 senateOuterScroll（外层兜底已删）。"""
        store = _MockStore(current_step="proposal", war_cards=[_card(0)])
        engine, root = _load_window(store, 1440, 900)
        self.assertIsNone(root.findChild(QObject, "senateOuterScroll"))


class TestR8ResultsMergedPredicate(unittest.TestCase):
    """R8-AC-06 / L-5：results 内容并入 #2 且五框几何不变（真实引擎测量）。"""

    def test_no_standalone_results_frame_at_results_step(self):
        store = _MockStore(current_step="results", war_cards=[])
        engine, root = _load_window(store, 1440, 900)
        self.assertIsNone(root.findChild(QObject, "senateResultsArea"),
                          "standalone results frame must be removed")
        self.assertIsNotNone(root.findChild(QObject, "senateAnnouncementBox"))

    def test_results_step_does_not_change_row_geometry(self):
        """L-5：results 态 Hrow/公示框与 proposal 态一致（≤1px）——results 不挤压五框。"""
        def geo(step):
            store = _MockStore(current_step=step, war_cards=[_card(0)])
            engine, root = _load_window(store, 1440, 900)
            return (float(root.findChild(QObject, "senateThreePanelRow").property("height")),
                    float(root.findChild(QObject, "senateAnnouncementBox").property("height")))

        prop = geo("proposal")
        res = geo("results")
        self.assertLessEqual(abs(res[0] - prop[0]), 1.0)
        self.assertLessEqual(abs(res[1] - prop[1]), 1.0)


class TestR8DialogEnvelopePredicate(unittest.TestCase):
    """R8-AC-05 / L-D v1.3：Dialog 几何 envelope（真实引擎测量；背景行不位移）。"""

    def _open_dialog(self, store, w, h):
        engine, root = _load_window(store, w, h)
        dlg = root.findChild(QObject, "senateValidationDialog")
        self.assertIsNotNone(dlg, "senateValidationDialog not found")
        return engine, root, dlg

    def test_dialog_dimensions_and_centering(self):
        for (w, h) in ((1440, 900), (1280, 720)):
            store = _MockStore(current_step="proposal", war_cards=[_card(0)])
            engine, root, dlg = self._open_dialog(store, w, h)
            dlg.setProperty("visible", True)
            for _ in range(3):
                _get_app().processEvents()
            dw = float(dlg.property("width"))
            dh = float(dlg.property("height"))
            wmax = min(round(0.50 * w), w - 32)
            self.assertGreaterEqual(dw, 320 - 1.0)
            self.assertLessEqual(dw, wmax + 1.0)
            self.assertGreater(dh, 0)
            self.assertLessEqual(dh, round(0.40 * h) + 2.0)
            # 谓词①：以 W 居中（±1）
            self.assertLessEqual(abs((float(dlg.property("x")) + dw / 2) - w / 2), 1.0)
            self.assertLessEqual(abs((float(dlg.property("y")) + dh / 2) - h / 2), 1.0)

    def test_dialog_open_does_not_displace_panel_row(self):
        """L-D：Dialog 属 Overlay 层，不参与根布局 → 打开前后三面板行 scene rect 差 ≤1px。"""
        store = _MockStore(current_step="proposal", war_cards=[_card(0)])
        engine, root, dlg = self._open_dialog(store, 1440, 900)
        row = root.findChild(QObject, "senateThreePanelRow")
        before = (float(row.property("height")), float(row.property("y")))
        dlg.setProperty("visible", True)
        _get_app().processEvents()
        after = (float(row.property("height")), float(row.property("y")))
        self.assertLessEqual(abs(before[0] - after[0]), 1.0)
        self.assertLessEqual(abs(before[1] - after[1]), 1.0)


# ===========================================================================
# Part C — Shell 容器重组（U_S 边界归属；SLICE-R8-03 refit2 / design v1.6）
#   SA §4.1 U_S 唯一化：Senate 相位 ① 折叠空 StageActionSlot（46→0）
#   ② Content→Action 槽间隔随不可见项消除（10→0） ③ 让渡 StageDesktop 底内边距 18
#   ⇒ U_S.bottom = Region C 外框底缘；三框 row.bottom = U_S.h − 14（PF-1）
# ===========================================================================

_SHELL_REL = os.path.join(_QML_DIR_REL, "shell", "GameShell.qml")
_STAGE_DESKTOP_REL = os.path.join(_QML_DIR_REL, "shell", "StageDesktop.qml")


def _load_stage_desktop(store, width, height, compact=False, absorb=False):
    """真实 QML 引擎：Window(W×H) → Loader → StageDesktop（anchors fill）。

    compact=compactActionSlot（折叠 StageActionSlot）；absorb=absorbBottomPadding（让渡底 18）。
    """
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

    desktop_url = os.path.join(PROJECT_ROOT, _STAGE_DESKTOP_REL).replace("\\", "/")
    harness = (
        'import QtQuick 2.15\n'
        'import QtQuick.Window 2.15\n'
        'Window {\n'
        '    id: win\n'
        '    width: %d\n'
        '    height: %d\n'
        '    visible: true\n'
        '    Loader {\n'
        '        anchors.fill: parent\n'
        '        source: "%s"\n'
        '        onLoaded: { item.compactActionSlot = %s; item.absorbBottomPadding = %s }\n'
        '    }\n'
        '}\n'
    ) % (width, height, desktop_url, "true" if compact else "false", "true" if absorb else "false")

    comp = QQmlComponent(engine)
    comp.setData(harness.encode("utf-8"),
                 QUrl.fromLocalFile(os.path.join(qml_dir, "__harness_desktop__.qml")))
    assert not comp.isError(), comp.errorString()
    engine.loadData(harness.encode("utf-8"),
                    QUrl.fromLocalFile(os.path.join(qml_dir, "__harness_desktop__.qml")))
    for _ in range(4):
        app.processEvents()
    roots = engine.rootObjects()
    assert roots, "StageDesktop harness failed to load"
    root = roots[0]
    engine._test_refs = (store, theme, root, comp)
    _STORES.append(store)
    _KEEPALIVE.append(engine)
    return engine, root


class TestR8ShellContainerReassemblySource(unittest.TestCase):
    """R8-AC-06 / SA §4.1 U_S（v1.6）：Senate 相位 shell 容器重组三项（源码面）。"""

    @classmethod
    def setUpClass(cls):
        cls.shell = _read(_SHELL_REL)
        cls.desktop = _read(_STAGE_DESKTOP_REL)

    def test_shell_collapses_action_slot_for_senate(self):
        """① 折叠空 StageActionSlot：senate 纳入既有 compactActionSlot 机制。"""
        self.assertIn('compactActionSlot: sessionStore.selectedPhaseId === "population"', self.shell)
        self.assertIn('|| sessionStore.selectedPhaseId === "forum"', self.shell)
        self.assertIn('|| sessionStore.selectedPhaseId === "senate"', self.shell)

    def test_shell_transfers_bottom_padding_for_senate(self):
        """③ 让渡底内边距 18：仅 Senate 相位 absorbBottomPadding=true。"""
        self.assertIn('absorbBottomPadding: sessionStore.selectedPhaseId === "senate"', self.shell)
        self.assertIn("property bool absorbBottomPadding: false", self.desktop)
        self.assertIn("anchors.bottomMargin: root.absorbBottomPadding ? 0 : 18", self.desktop)
        self.assertNotIn("anchors.bottomMargin: 18", self.desktop)

    def test_stage_desktop_slot_mechanism_present(self):
        """① 既有 compactActionSlot 机制（46→0 + 不可见）+ ② 槽间隔随不可见项消除。"""
        self.assertIn("Layout.preferredHeight: root.compactActionSlot ? 0 : 46", self.desktop)
        self.assertIn("visible: !root.compactActionSlot", self.desktop)
        self.assertIn("spacing: 10", self.desktop)

    def test_population_forum_unchanged_by_senate_transfer(self):
        """population/forum 仅折叠 ActionSlot，不让渡底内边距（既有行为不变）。"""
        for phase in ("population", "forum"):
            self.assertNotIn('absorbBottomPadding: sessionStore.selectedPhaseId === "%s"' % phase,
                             self.shell)


class TestR8ShellContainerReassemblyPredicate(unittest.TestCase):
    """R8-AC-06：shell 容器重组 → U_S.bottom = Region C 外框底缘（真实引擎实测量）。

    以 `StageContentSlot`（=U_S 区域）底到 StageDesktop 外框底缘的残留量衡量：
      baseline（mortality 等，无折叠无让渡）= 46 + 10 + 18 = 74（设计 §17.1 实测 74–102）
      population（折叠 ActionSlot）= 18
      senate（折叠 + 让渡 18）= 0  ⇒ U_S.bottom = C.bottom（PF-2 可达前提）
    """

    def _shell_residual(self, compact, absorb, w=1440, h=900):
        store = _MockStore(current_step="senate")
        engine, root = _load_stage_desktop(store, w, h, compact=compact, absorb=absorb)
        content = root.findChild(QObject, "stageContentSlot")
        action = root.findChild(QObject, "stageActionSlot")
        self.assertIsNotNone(content, "stageContentSlot not found")
        self.assertIsNotNone(action, "stageActionSlot not found")
        cy = float(content.property("y"))
        ch = float(content.property("height"))
        root_h = float(root.property("height"))
        scene_top = 10.0 + cy          # ColumnLayout topMargin=10；StageDesktop 顶在 scene (0,0)
        scene_bottom = 10.0 + cy + ch
        return {
            "root_h": root_h,
            "scene_top": scene_top,
            "scene_bottom": scene_bottom,
            "residual": root_h - scene_bottom,
            "content_h": ch,
            "action_h": float(action.property("height")),
            "action_visible": bool(action.property("visible")),
        }

    def test_baseline_residual_is_74(self):
        m = self._shell_residual(compact=False, absorb=False)
        self.assertAlmostEqual(m["residual"], 74.0, delta=1.0)
        self.assertAlmostEqual(m["action_h"], 46.0, delta=1.0)
        self.assertTrue(m["action_visible"])
        self.assertAlmostEqual(m["scene_top"], 160.0, delta=1.0)

    def test_population_collapses_action_slot_residual_18(self):
        m = self._shell_residual(compact=True, absorb=False)
        self.assertAlmostEqual(m["residual"], 18.0, delta=1.0)
        self.assertAlmostEqual(m["action_h"], 0.0, delta=1.0)
        self.assertFalse(m["action_visible"])
        self.assertAlmostEqual(m["scene_top"], 160.0, delta=1.0)

    def test_senate_absorbs_bottom_padding_residual_0(self):
        for (w, h) in ((1440, 900), (1280, 720)):
            m = self._shell_residual(compact=True, absorb=True, w=w, h=h)
            self.assertAlmostEqual(m["residual"], 0.0, delta=1.0,
                                   msg="senate residual at %dx%d" % (w, h))
            self.assertAlmostEqual(m["action_h"], 0.0, delta=1.0)
            self.assertFalse(m["action_visible"])
            self.assertAlmostEqual(m["scene_top"], 160.0, delta=1.0)
            # U_S.h = C.h − 160 ⇒ content(=U_S) 高 = root.h − 160
            self.assertAlmostEqual(m["content_h"], float(h) - 160.0, delta=1.0)

    def test_senate_uS_bottom_equals_region_c_bottom(self):
        """PF-1/PF-2 前提：U_S.bottom == C.bottom（残留 0）⇒ row.bottom = U_S.h − 14。"""
        m = self._shell_residual(compact=True, absorb=True)
        self.assertAlmostEqual(m["scene_bottom"], m["root_h"], delta=1.0)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
