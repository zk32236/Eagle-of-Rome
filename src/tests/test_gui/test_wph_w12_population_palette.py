# src/tests/test_gui/test_wph_w12_population_palette.py
"""WP-H W12 focused fix — PopulationStage RadioButton 原生控件定制（机制 O1）。

T-H08（W12）：离屏 **显式** `QT_QUICK_CONTROLS_STYLE`（Fusion / Basic）跑同旅程 → 断言
  ① 无 "contentItem" 定制告警（FC-H-01：由修正达成，非抑制）；
  ② 候选行标签文本色 == factionStyle.factionColor(faction_id)（enabled 与 disabled 两态）；
  ③ checked / enabled / onClick / focus / autoExclusive（键盘·互斥）语义不变。

机制面（SA-Design-WP-H-W12-delta-2026-09-27.md §4）：
  - 移除 `contentItem: Text { ... }` 覆盖（原 627-633）；
  - 新增控件级 `palette.windowText` / `palette.disabled.windowText` /
    `palette.inactive.windowText` = `factionStyle.factionColor(modelData.faction_id)`；
  - 三风格（Windows/Basic/Fusion）RadioButton 标签色同取 `control.palette.windowText`
    ⇒ 受支持路径 + 风格无关。

零抑制：不安装任何 logger/stderr/Qt/regex 抑制；raw 消息只用于计数与归档。
显式风格：未设 `QT_QUICK_CONTROLS_STYLE` 时 **skip**（禁止依赖离屏默认风格，防 W12 同类
false-negative 复发）；设了则断言运行期 `QQuickStyle.name()` 命中该显式值。
真机 Windows 原生风格 V1/V2 属 Owner 侧，本离屏测试 **不** 代替之。
"""
from __future__ import annotations

import contextlib
import gc
import json
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore

STYLE = os.environ.get("QT_QUICK_CONTROLS_STYLE", "").strip()
EVIDENCE_DIR = os.environ.get("WPH_W12_EVIDENCE_DIR")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
POPULATION_QML = os.path.join(QML_DIR, "stages", "PopulationStage.qml")

# FC-H-04 in-scope 告警族（可归因于项目 QML/runtime binding·layout·control）。
IN_SCOPE_PATTERNS = (
    r"Unable to assign",
    r"Cannot read prop",
    r"is not a function",
    r"TypeError",
    r"Detected anchors on an item that is managed by a layout",
    r"Cannot specify contentItem",
)
_IN_SCOPE_RE = re.compile("|".join(IN_SCOPE_PATTERNS))

CANDIDATE_OBJECTNAME = "populationVoteCandidate_consul_7"
CANDIDATE_LABEL = "Marcus"


def _require_explicit_style():
    """T-H08 硬约束：离屏必须显式绑定风格；未设 → skip（不得依赖默认）。"""
    if not STYLE:
        pytest.skip(
            "requires explicit QT_QUICK_CONTROLS_STYLE (Fusion/Basic); "
            "离屏默认风格不得代替显式风格绑定（W12 防 false-negative 复发）"
        )


def _effective_style_name():
    from PySide6.QtQuickControls2 import QQuickStyle
    return QQuickStyle.name()


def in_scope(messages):
    return [m for m in messages if _IN_SCOPE_RE.search(m)]


def _write_evidence(name, content):
    if not EVIDENCE_DIR:
        return
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    with open(os.path.join(EVIDENCE_DIR, name), "w", encoding="utf-8") as fh:
        fh.write(content)


# ───────────────────────────── 基础设施 ─────────────────────────────

def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


@contextlib.contextmanager
def capture_qt_raw():
    """全量 raw Qt 消息捕获（qInstallMessageHandler；不改写/不过滤消息）。"""
    captured = []

    def _h(_t, _c, msg):
        captured.append(str(msg))

    old = qInstallMessageHandler(_h)
    try:
        yield captured
    finally:
        qInstallMessageHandler(old)


_ENGINES = []


def _flush_deferred(app):
    try:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    except Exception:
        pass
    if app is not None:
        for _ in range(3):
            app.processEvents()


def _dispose_all_engines():
    """确定性销毁本进程创建的 QML roots/engines（先删 root 再删 window）。

    防止 interpreter-teardown 阶段 sessionStore 失效后 QML binding 重求值产生
    `... of null` 噪声（机制性消除，非抑制）。
    """
    app = QGuiApplication.instance()
    engines = list(_ENGINES)
    qml_engines = [e for e in engines if isinstance(e, QQmlApplicationEngine)]
    windows = [e for e in engines if isinstance(e, QQuickWindow)]
    for eng in qml_engines:
        try:
            for root in list(eng.rootObjects()):
                try:
                    root.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
    for win in windows:
        try:
            win.hide()
        except Exception:
            pass
        try:
            win.deleteLater()
        except Exception:
            pass
    _flush_deferred(app)
    for eng in qml_engines:
        try:
            eng.clearComponentCache()
        except Exception:
            pass
    _ENGINES.clear()
    gc.collect()
    _flush_deferred(app)


@pytest.fixture(autouse=True)
def _w12_lifecycle_disposal():
    """每个测试后确定性销毁其 QML roots/engines（消除 teardown 噪声）。"""
    yield
    _dispose_all_engines()


def _load_stage(qml_name, store):
    app = _get_app()
    engine = QQmlApplicationEngine()
    _ENGINES.append(engine)
    engine.addImportPath(QML_DIR)
    qml_warnings = []
    engine.warnings.connect(lambda errs: qml_warnings.extend(str(e.toString()) for e in errs))
    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    engine._w12_refs = (store,)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "stages", qml_name)))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_name} loaded with no root object"
    root = roots[0]
    # 挂入离屏 QQuickWindow（Repeater/Layout delegate 孵化所需）。
    try:
        win = QQuickWindow()
        win.setWidth(1440)
        win.setHeight(900)
        root.setParentItem(win.contentItem())
        win.show()
        _ENGINES.append(win)
    except Exception:
        pass
    for _ in range(3):
        app.processEvents()
    return engine, root, qml_warnings


def _run_stage(qml_name, store, pumps=10):
    app = _get_app()
    with capture_qt_raw() as raw:
        _, root, qml_warnings = _load_stage(qml_name, store)
        for _ in range(pumps):
            app.processEvents()
    return root, raw, qml_warnings


def _walk(obj):
    yield obj
    seen = set()
    kids = []
    if hasattr(obj, "childItems"):
        try:
            kids.extend(obj.childItems())
        except Exception:
            pass
    try:
        kids.extend(obj.children())
    except Exception:
        pass
    for child in kids:
        cid = id(child)
        if cid in seen:
            continue
        seen.add(cid)
        yield from _walk(child)


def _find_by_objectname(root, objectname):
    for item in _walk(root):
        try:
            if item.objectName() == objectname:
                return item
        except Exception:
            continue
    return None


def _expected_faction_color(store, faction_id):
    """复现 FactionStyle.factionColor（直接 key 命中）→ 权威期望色。"""
    data = store.factionStyleMap or {}
    entry = (data.get("map") or {}).get(faction_id)
    if entry and entry.get("color"):
        return entry["color"]
    return (data.get("fallback") or {}).get("color", "#3A3530")


def _population_store(can_vote=True, voted=False):
    """真实 prototype 会话 + producer-shaped `_population_view`（1 候选，consul）。"""
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    store = GuiSessionStore(state)
    store.initialize(viewer)
    style_map = (store.factionStyleMap or {}).get("map", {})
    assert style_map, "prototype session must expose faction style map"
    fid = sorted(style_map.keys())[0]
    fname = style_map[fid].get("name", fid)
    store._population_view = {
        "candidates": {"consul": [
            {"id": 7, "name": CANDIDATE_LABEL, "faction_id": fid, "faction_name": fname},
        ]},
        "current_step": "vote",
        "can_vote": can_vote,
        "my_votes": ({"consul": 7} if voted else {}),
    }
    return store, fid, fname


def _contentitem_color(button):
    ci = button.property("contentItem")
    assert ci is not None, "RadioButton has no contentItem"
    col = ci.property("color")
    assert col is not None, "contentItem has no color property"
    return col


# ───────────────────────────── 源码身份（无 Qt，恒跑） ─────────────────────────────

class TestW12SourceIdentity:
    """P-W12.4：逐字不变 + 无 contentItem 覆盖 + 无抑制 / 无风格分支 / 无 token 扩张。"""

    def _src(self):
        with open(POPULATION_QML, encoding="utf-8") as fh:
            return fh.read()

    def test_palette_path_present_contentitem_removed(self):
        src = self._src()
        assert "contentItem: Text {" not in src, "contentItem 覆盖必须移除"
        assert "palette.windowText: factionStyle.factionColor(modelData.faction_id)" in src
        assert "palette.disabled.windowText: factionStyle.factionColor(modelData.faction_id)" in src
        assert "palette.inactive.windowText: factionStyle.factionColor(modelData.faction_id)" in src

    def test_untouched_properties_verbatim(self):
        src = self._src()
        assert 'objectName: "populationVoteCandidate_" + modelData.office + "_" + modelData.id' in src
        assert 'text: modelData.name + " (" + root.factionShort(modelData.faction_name) + ")"' in src
        assert "checked: root.votedFigureId(modelData.office) === modelData.id" in src
        assert ("enabled: sessionStore.canVote && campaignSubmitted() && "
                "!sessionStore.populationResolved && !sessionStore.myVotes[modelData.office]") in src
        assert "font.pixelSize: 12" in src
        assert "onClicked: root.selectCandidate(modelData.office, modelData.id)" in src
        # 行为属性未被覆盖（键盘/互斥语义 = 控件默认）
        for banned in ("focusPolicy:", "autoExclusive:", "checkable:", "indicator:", "background:"):
            assert banned not in src, banned

    def test_no_suppression_no_style_branch_no_global_style(self):
        src = self._src()
        for token in ("QT_QUICK_CONTROLS_IGNORE_CUSTOMIZATION_WARNINGS",
                      "QT_QUICK_CONTROLS_STYLE", "QQuickStyle", "import QtQuick.Controls.",
                      "console.log", "Qt.logging"):
            assert token not in src, token
        assert "#008000" not in src


# ───────────────────────────── 运行面（显式风格） ─────────────────────────────

class TestTH08PopulationPalette:

    def test_style_is_explicit_and_effectively_bound(self):
        _require_explicit_style()
        _get_app()
        effective = _effective_style_name()
        _write_evidence(f"style-binding-{STYLE}.json", json.dumps({
            "requested_via_env": STYLE,
            "effective_QQuickStyle_name": effective,
            "matches": effective.lower() == STYLE.lower(),
        }, ensure_ascii=False, indent=2) + "\n")
        assert effective.lower() == STYLE.lower(), (effective, STYLE)

    def test_enabled_label_color_and_no_contentitem_warning(self):
        _require_explicit_style()
        store, fid, _ = _population_store(can_vote=True)
        expected = _expected_faction_color(store, fid)
        root, raw, qml_warnings = _run_stage("PopulationStage.qml", store)
        _write_evidence(f"raw-w12-{STYLE}-enabled.json", json.dumps(
            {"style": STYLE, "raw": raw, "engine_warnings": qml_warnings},
            ensure_ascii=False, indent=2) + "\n")

        hits = [m for m in raw if "contentItem" in m or "Cannot specify" in m]
        assert hits == [], hits
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        assert qml_warnings == [], qml_warnings

        button = _find_by_objectname(root, CANDIDATE_OBJECTNAME)
        assert button is not None, "candidate RadioButton not instantiated"
        assert button.property("enabled") is True
        assert button.property("text") == f"{CANDIDATE_LABEL} ({_short(store, fid)})"

        ci = button.property("contentItem")
        assert ci.property("text") == button.property("text")
        observed = _contentitem_color(button).name()
        _write_evidence(f"faction-color-{STYLE}-enabled.json", json.dumps({
            "style": STYLE, "state": "enabled", "faction_id": fid,
            "expected": expected, "observed_contentItem_color": observed,
            "match": observed.lower() == expected.lower(),
        }, ensure_ascii=False, indent=2) + "\n")
        assert observed.lower() == expected.lower(), (observed, expected)

    def test_disabled_label_keeps_faction_color(self):
        _require_explicit_style()
        store, fid, _ = _population_store(can_vote=False)
        expected = _expected_faction_color(store, fid)
        root, raw, _ = _run_stage("PopulationStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

        button = _find_by_objectname(root, CANDIDATE_OBJECTNAME)
        assert button is not None
        assert button.property("enabled") is False, "can_vote=False ⇒ enabled 必须为 False"
        observed = _contentitem_color(button).name()
        _write_evidence(f"faction-color-{STYLE}-disabled.json", json.dumps({
            "style": STYLE, "state": "disabled", "faction_id": fid,
            "expected": expected, "observed_contentItem_color": observed,
            "match": observed.lower() == expected.lower(),
        }, ensure_ascii=False, indent=2) + "\n")
        assert observed.lower() == expected.lower(), (observed, expected)

    def test_checked_binding_semantics(self):
        _require_explicit_style()
        store_off, _, _ = _population_store(can_vote=True, voted=False)
        root_off, _, _ = _run_stage("PopulationStage.qml", store_off)
        b_off = _find_by_objectname(root_off, CANDIDATE_OBJECTNAME)
        assert b_off is not None and b_off.property("checked") is False

        store_on, _, _ = _population_store(can_vote=True, voted=True)
        root_on, _, _ = _run_stage("PopulationStage.qml", store_on)
        b_on = _find_by_objectname(root_on, CANDIDATE_OBJECTNAME)
        assert b_on is not None and b_on.property("checked") is True

    def test_onclick_wiring_and_keyboard_defaults_unchanged(self):
        _require_explicit_style()
        app = _get_app()
        store, _, _ = _population_store(can_vote=True)
        root, _, _ = _run_stage("PopulationStage.qml", store)
        button = _find_by_objectname(root, CANDIDATE_OBJECTNAME)
        assert button is not None

        # onClicked: root.selectCandidate(office,id)（信号发射 → selectedVotes 写入）
        emit_ok = False
        try:
            button.clicked.emit()
            emit_ok = True
        except Exception:
            emit_ok = False
        for _ in range(5):
            app.processEvents()
        raw_sel = root.property("selectedVotes")
        if hasattr(raw_sel, "toVariant"):
            raw_sel = raw_sel.toVariant()
        selected = raw_sel if isinstance(raw_sel, dict) else {}
        _write_evidence(f"interaction-{STYLE}.json", json.dumps({
            "style": STYLE,
            "clicked_emit_supported": emit_ok,
            "selectedVotes": dict(selected),
            "focusPolicy": int(button.property("focusPolicy")),
            "autoExclusive": bool(button.property("autoExclusive")),
            "checkable": bool(button.property("checkable")),
        }, ensure_ascii=False, indent=2) + "\n")
        if emit_ok:
            assert selected.get("consul") == 7, selected

        # 键盘/互斥 = 控件默认（与新建参照 RadioButton 逐项一致）
        ref_engine, ref = _reference_radio_button()
        try:
            assert button.property("focusPolicy") == ref.property("focusPolicy")
            assert bool(button.property("autoExclusive")) is True
            assert bool(button.property("checkable")) is True
        finally:
            ref_engine.deleteLater()


_REF_QML = b"""
import QtQuick 2.15
import QtQuick.Controls 2.15
RadioButton { text: "ref" }
"""


_REFS = []


def _reference_radio_button():
    """新建一个 *未修改* 的默认 RadioButton（用于键盘/互斥默认值对照）。

    QML 创建的对象归 JS 引擎所有 → 必须保持 Python 强引用 + QObject 父级，
    否则可能在读取前被 GC 销毁。
    """
    engine = QQmlEngine()
    comp = QQmlComponent(engine)
    comp.setData(_REF_QML, QUrl())
    obj = comp.create()
    assert obj is not None, comp.errorString()
    try:
        obj.setParent(engine)
    except Exception:
        pass
    _REFS.extend([engine, comp, obj])
    return engine, obj


def _short(store, fid):
    """复现 FactionStyle.factionShort（直接 key 命中 → id_display）。"""
    entry = ((store.factionStyleMap or {}).get("map") or {}).get(fid) or {}
    disp = entry.get("id_display")
    if disp:
        return disp
    return fid[:3] if len(fid) > 3 else fid
