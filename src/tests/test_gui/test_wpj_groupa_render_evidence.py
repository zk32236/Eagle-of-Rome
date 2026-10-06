# src/tests/test_gui/test_wpj_groupa_render_evidence.py
"""WP-J Group-A — RENDER_AUTOMATED 截图证据（route=DIRECT_PRODUCTION）。

真实生产链：`session_api.create_gui_prototype_session` → 真实 `GuiSessionStore` →
真实生产动作（doExecuteMortality / open_market / selectPhase）→ 真实 `Main.qml`
离屏渲染（QT_QPA_PLATFORM=offscreen）→ `window.grabWindow()` → PNG。

证据落 `03-da-evidence/Group-A/{Group-A-1,Group-A-2,Group-A-3}/`：
- Group-A-1：mortality 死亡影响行（强制死亡事件牌组 → 死亡行可见）
- Group-A-2：六阶段权威步骤条（StepBar 唯一渲染 owner）
- Group-A-3：Forum 市场子环节操作按钮（1280×720 与 1440×900）

No-Test-Assisted-Transition：状态一律经真实生产动作到达；不直置 store 终态。
"""
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

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/Group-A"
)

from src.api import session_api  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402


class _DummyGuiApp:
    pass


def _get_app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine(store):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    _get_app()
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
    return engine, qml_dir


def _make_store(start_phase="mortality"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _force_death(state, count=2):
    try:
        cfg = state._config._config
        mort = cfg.setdefault("mortality_rules", {})
        mort["event_deck"] = [{"name": "死神来了", "effect": "death", "weight": 1}]
        mort["event_draw_count"] = 1
        mort["death_count"] = count
        state._initialize_mortality_pool()
    except Exception:  # noqa: BLE001
        pass


def _capture(engine, out_png, width=1440, height=900):
    from PySide6.QtCore import QCoreApplication, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication

    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    window = roots[0]
    result = []

    def finish(value):
        if not result:
            result.append(value)
        QCoreApplication.quit()

    def grab():
        try:
            window.show()
            try:
                window.setWidth(width)
                window.setHeight(height)
            except Exception:
                pass
            QGuiApplication.processEvents()
            QGuiApplication.processEvents()
            img = None
            if hasattr(window, "grabWindow"):
                img = window.grabWindow()
            if (img is None or img.isNull()):
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    img = scr.grabWindow(int(window.winId()))
            if img is None or img.isNull():
                finish(None)
                return
            ok = img.save(out_png)
            finish((out_png, img.width(), img.height()) if ok else None)
        except Exception as exc:  # noqa: BLE001
            finish("exc:" + type(exc).__name__ + ":" + str(exc))

    QTimer.singleShot(900, grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))
    app.exec()
    value = result[0] if result else None
    return value


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _emit(slice_dir, name, capture, state_prep, phase, viewport):
    out_dir = os.path.join(EVIDENCE_BASE, slice_dir)
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, name)
    meta = os.path.join(out_dir, name[:-4] + ".runtime.json")
    row = {
        "fixture": "test_wpj_groupa_render_evidence.py",
        "phase": phase,
        "viewport": list(viewport),
        "state_prep": state_prep,
        "route": "DIRECT_PRODUCTION",
        "png_path": png if os.path.exists(png) else None,
        "png_sha256": _sha256(png) if os.path.exists(png) else None,
        "capture_ok": bool(capture) and capture not in ("timeout",) and not (
            isinstance(capture, str) and capture.startswith("exc:")),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return row


def test_render_group_a1_mortality_death_rows():
    store, state, _ = _make_store("mortality")
    _force_death(state, 2)
    fb = store.doExecuteMortality()
    assert fb.get("success"), fb.get("message")
    store.selectPhase("mortality")
    deaths = [
        imp for ev in (store.mortalityEvents or [])
        for imp in (ev.get("impacts") or []) if imp.get("type") == "figure_death"
    ]
    assert deaths, "强制死亡牌组必须产出 figure_death impacts"
    engine, _ = _create_engine(store)
    cap = _capture(engine, os.path.join(
        EVIDENCE_BASE, "Group-A-1", "group-a-1-mortality-death-rows-1440x900.png"))
    row = _emit("Group-A-1", "group-a-1-mortality-death-rows-1440x900.png", cap,
                "create_gui_prototype_session(mortality)+force_death_deck+doExecuteMortality+selectPhase",
                "mortality", (1440, 900))
    assert row["capture_ok"], f"capture failed: {cap!r}"


def test_render_group_a2_six_phase_steps():
    rows = []
    for phase in ("mortality", "revenue", "forum", "population", "senate", "combat"):
        store, state, _ = _make_store(phase)
        store.selectPhase(phase)
        steps = store.phaseSteps
        assert steps, f"{phase}: phaseSteps 必须非空"
        engine, _ = _create_engine(store)
        name = f"group-a-2-steps-{phase}-1440x900.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-A-2", name))
        rows.append(_emit("Group-A-2", name, cap,
                          f"create_gui_prototype_session({phase})+selectPhase({phase})",
                          phase, (1440, 900)))
    manifest = os.path.join(EVIDENCE_BASE, "Group-A-2", "steps-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupa-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_a3_forum_market_buttons():
    from src.api import forum_api
    rows = []
    for (w, h, tag) in ((1280, 720, "1280x720"), (1440, 900, "1440x900")):
        store, state, viewer = _make_store("forum")
        # 真实生产动作：解雇→市场（子环节操作按钮在 market 子环节出现）
        assert forum_api.open_market(state, viewer)["success"]
        store._refresh_forum_view()
        store.selectPhase("forum")
        assert store.forumCurrentStep == "market"
        engine, _ = _create_engine(store)
        name = f"group-a-3-forum-market-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-A-3", name), w, h)
        rows.append(_emit("Group-A-3", name, cap,
                          "create_gui_prototype_session(forum)+forum_api.open_market+selectPhase(forum)",
                          "forum", (w, h)))
    manifest = os.path.join(EVIDENCE_BASE, "Group-A-3", "forum-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupa-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows
