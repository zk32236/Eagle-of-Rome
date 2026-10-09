# src/tests/test_gui/test_wpj_groupd_render_evidence.py
"""WP-J Group-D — RENDER_AUTOMATED 截图证据（route=DIRECT_PRODUCTION）。

真实生产链：`session_api.create_gui_prototype_session` → 真实 `GuiSessionStore` →
真实生产动作（`population_api.process_population_disbandments` /
`forum_api.open_market` → `initialize_forum_turn`）→ 真实 `Main.qml` 离屏渲染
（QT_QPA_PLATFORM=offscreen）→ `window.grabWindow()` → PNG。

证据落 `03-da-evidence/GroupD/{Group-D-Aftermath,Group-D-Rebellion}/`：
- Group-D-Aftermath：人口公示框内战后反馈行（凯旋仪式已举行 + 军团解散计数）
  + 空 payload 回落（FC-D07）。
- Group-D-Rebellion：广场公告框内起义警示行（西西里起义）。

No-Test-Assisted-Transition：状态经真实生产动作到达；不直置 store 终态。
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
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupD"
)

from src.api import session_api, population_api, forum_api  # noqa: E402
from src.core.entities.war import War, WarStatus  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

_ENGINES = []


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
    _ENGINES.append(engine)
    return engine, qml_dir


def _capture(engine, out_png, width=1440, height=900):
    """Offscreen capture with a bounded poll/retry loop until the frame is ready."""
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

    def grab():
        if result:
            return
        attempts["n"] += 1
        try:
            if not window.isVisible():
                window.show()
            try:
                window.setWidth(width)
                window.setHeight(height)
            except Exception:
                pass
            QGuiApplication.processEvents()
            QGuiApplication.processEvents()
            try:
                window.requestUpdate()
            except Exception:
                pass
            QGuiApplication.processEvents()

            img = None
            if hasattr(window, "grabWindow") and window.width() > 0 and window.height() > 0:
                img = window.grabWindow()
            if img is None or img.isNull():
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    img = scr.grabWindow(int(window.winId()))

            if img is not None and not img.isNull():
                ok = img.save(out_png)
                finish((out_png, img.width(), img.height()) if ok else None)
                return

            if attempts["n"] >= MAX_ATTEMPTS:
                finish(None)
            else:
                QTimer.singleShot(RETRY_INTERVAL_MS, grab)
        except Exception as exc:  # noqa: BLE001
            finish("exc:" + type(exc).__name__ + ":" + str(exc))

    QTimer.singleShot(0, grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))
    app.exec()
    return result[0] if result else None


def _teardown(engine):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    try:
        for win in list(QGuiApplication.topLevelWindows()):
            try:
                win.close()
                win.deleteLater()
            except Exception:
                pass
        engine.deleteLater()
    except Exception:
        pass
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()


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
        "fixture": "test_wpj_groupd_render_evidence.py",
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


def _session_store(start_phase):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    return state, viewer


def _attach_resolved_war(state, commander_id, legion_numbers=(1, 2)):
    war = War(
        id="wpj-gd-render-war", name="对迦太基战争", strength=5, threat_level=3,
        rewards={"treasury": 100, "land": 0, "family_prestige": 0},
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.RESOLVED
    war.set_soldier_share(20)
    war.set_triumph_commander(commander_id)
    war.set_triumph_approved(True)
    ms = state.get_military_system()
    for n in legion_numbers:
        ok, _msg = ms.recruit_legion(n)
        if ok:
            war.add_legion_number(n)
    state.get_war_system()._war_discard.append(war)
    return war


# ---------------------------------------------------------------------------
# Group-D-Aftermath
# ---------------------------------------------------------------------------

def test_render_population_aftermath_and_empty():
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        state, viewer = _session_store("population")
        commander = next(m for m in state.get_living_members())
        _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))
        population_api.process_population_disbandments(state)   # 真实生产动作
        store = GuiSessionStore(state)
        store.initialize(viewer)
        store.selectPhase("population")
        assert store.populationOutcome.get("triumphs"), "populationOutcome 必须非空"
        engine, _ = _create_engine(store)
        name = f"population-aftermath-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-D-Aftermath", name), w, h)
        rows.append(_emit("Group-D-Aftermath", name, cap,
                          "create_gui_prototype_session(population)+resolved_war(triumph+2 legions)"
                          "+process_population_disbandments", "population", (w, h)))
        _teardown(engine)

    # FC-D07 否证：空 payload → 公示框不追加行
    state, viewer = _session_store("population")
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("population")
    assert store.populationOutcome.get("triumphs") == []
    engine, _ = _create_engine(store)
    name = "population-aftermath-empty-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-D-Aftermath", name), 1440, 900)
    rows.append(_emit("Group-D-Aftermath", name, cap,
                      "create_gui_prototype_session(population)+no_disbandment(empty)",
                      "population", (1440, 900)))
    _teardown(engine)

    manifest = os.path.join(EVIDENCE_BASE, "Group-D-Aftermath", "aftermath-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupd-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# Group-D-Rebellion
# ---------------------------------------------------------------------------

def test_render_forum_rebellion():
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        state, viewer = _session_store("forum")
        province = state.get_province(1)
        province.set_event_flag("rebellion_active", False)
        province.set_grievance(3)
        assert forum_api.open_market(state, viewer)["success"]   # 真实生产动作
        store = GuiSessionStore(state)
        store.initialize(viewer)
        store.selectPhase("forum")
        assert store.forumRebellionEvents, "forumRebellionEvents 必须非空"
        engine, _ = _create_engine(store)
        name = f"forum-rebellion-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-D-Rebellion", name), w, h)
        rows.append(_emit("Group-D-Rebellion", name, cap,
                          "create_gui_prototype_session(forum)+province(1).grievance=3+open_market"
                          "(initialize_forum_turn/check_province_unrest)", "forum", (w, h)))
        _teardown(engine)

    manifest = os.path.join(EVIDENCE_BASE, "Group-D-Rebellion", "rebellion-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupd-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
