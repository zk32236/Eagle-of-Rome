# src/tests/test_gui/test_wpj_groupb_render_evidence.py
"""WP-J Group B — RENDER_AUTOMATED 截图证据（route=DIRECT_PRODUCTION）。

真实生产链：`session_api.create_gui_prototype_session` → 真实 `GuiSessionStore` →
真实生产动作（forum_api.open_market / store.doVoteTriumph；senate 真实 resolver 驱动的
`store.senateVetoControlMode`）→ 真实 `Main.qml` 离屏渲染（QT_QPA_PLATFORM=offscreen）
→ `window.grabWindow()` → PNG。

证据落 `03-da-evidence/GroupB/{Group-B-1,Group-B-2}/`：
- Group-B-1：凯旋行三态（可投「赞成」/ 不可投「不可投」[灰] / 已投「已投」[灰]）
- Group-B-2：保民官否决归属（HUMAN「判定否决 → 公示结果」/ AI「AI判定否决 → 公示结果」/ NONE「无保民官，跳过否决」）

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
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupB"
)

from src.api import session_api, forum_api  # noqa: E402
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
    """Offscreen capture with a bounded poll/retry loop until the frame is ready.

    Determinism fix (WP-J Group B ATTEMPT-3): the previous implementation issued a
    single grab after a fixed `QTimer.singleShot(900, grab)` delay. Under load the
    freshly-shown offscreen window was sometimes not yet renderable at that instant,
    so `grabWindow()` returned a null image and the capture intermittently failed
    (capture_ok False for 2 of 3 states in ATTEMPT-2). Here we (re)grab on a fixed
    cadence until a non-null image is produced, bounded by MAX_ATTEMPTS so a genuinely
    unreachable window still fails closed (never a silent pass). The 3-state
    `capture_ok` assertions in the test bodies are unchanged.
    """
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

    # Bounded poll: 100 ms cadence x 150 attempts = 15 s ceiling (below the 20 s guard).
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
        "fixture": "test_wpj_groupb_render_evidence.py",
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


# ---------------------------------------------------------------------------
# ③ 凯旋行三态（Group-B-1）
# ---------------------------------------------------------------------------

def _forum_store_with_resolved_war():
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    faction_id = state.get_player(viewer).faction_id
    commander = next(m for m in state.get_living_members() if m.faction_id == faction_id)
    war = War(
        id="wpj-gb-render-war", name="渲染测试战争", strength=5, threat_level=3,
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
    return store, state, viewer, war


def test_render_group_b1_triumph_three_states():
    rows = []
    # (1) retirement 子环节 → 不可投
    store, state, viewer, _war = _forum_store_with_resolved_war()
    assert store.forumCurrentStep == "retirement"
    engine, _ = _create_engine(store)
    name = "group-b-1-triumph-readonly-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-B-1", name))
    rows.append(_emit("Group-B-1", name, cap,
                      "create_gui_prototype_session(forum)+resolved_war+retirement",
                      "forum", (1440, 900)))

    # (2) market 子环节 + 未投 → 赞成
    assert forum_api.open_market(state, viewer)["success"]
    store._refresh_forum_view()
    store.selectPhase("forum")
    assert store.forumCurrentStep == "market"
    engine, _ = _create_engine(store)
    name = "group-b-1-triumph-actionable-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-B-1", name))
    rows.append(_emit("Group-B-1", name, cap,
                      "create_gui_prototype_session(forum)+resolved_war+open_market",
                      "forum", (1440, 900)))

    # (3) 点击「赞成」提交 → 已投（灰化）
    assert store.doVoteTriumph("wpj-gb-render-war", True)["success"]
    store.selectPhase("forum")
    engine, _ = _create_engine(store)
    name = "group-b-1-triumph-voted-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-B-1", name))
    rows.append(_emit("Group-B-1", name, cap,
                      "create_gui_prototype_session(forum)+open_market+doVoteTriumph(true)",
                      "forum", (1440, 900)))

    manifest = os.path.join(EVIDENCE_BASE, "Group-B-1", "triumph-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupb-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# ④ 保民官否决归属三模式（Group-B-2）
# ---------------------------------------------------------------------------

def _senate_store_with_mode(mode):
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    viewer_faction = state.get_player(viewer).faction_id
    living = [m for m in state.get_living_members()]
    tribunes = [m for m in living if getattr(m, "office", None) == "tribune"]
    if mode == "NONE":
        for t in tribunes:
            t.office = None
    elif mode == "HUMAN":
        if tribunes and tribunes[0].faction_id == viewer_faction:
            keep = tribunes[0]
        else:
            keep = next((m for m in living if m.faction_id == viewer_faction), None)
            assert keep is not None, "viewer faction has no living member for tribune"
            keep.office = "tribune"
        for t in tribunes:
            if t.id != keep.id:
                t.office = None
    elif mode == "AI":
        other = next((m for m in living if m.faction_id != viewer_faction), None)
        assert other is not None, "no non-viewer living member for AI tribune"
        other.office = "tribune"
        for t in tribunes:
            if t.id != other.id and t.faction_id == viewer_faction:
                t.office = None
    else:
        raise AssertionError(mode)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("senate")
    assert store.senateVetoControlMode == mode, (
        f"expected {mode}, got {store.senateVetoControlMode}"
    )
    return store, state, viewer


def test_render_group_b2_veto_attribution_three_modes():
    from src.tests.test_gui.test_wpj_groupb_senate_attribution_gui import (
        HUMAN_COPY, AI_COPY, NONE_COPY, _find_text,
    )
    rows = []
    for mode, name_tag in (("HUMAN", "human"), ("AI", "ai"), ("NONE", "none")):
        store, _state, _viewer = _senate_store_with_mode(mode)
        engine, _ = _create_engine(store)
        name = f"group-b-2-senate-veto-{name_tag}-1440x900.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-B-2", name))
        rows.append(_emit("Group-B-2", name, cap,
                          f"create_gui_prototype_session(senate)+tribune_setup({mode})",
                          "senate", (1440, 900)))
    manifest = os.path.join(EVIDENCE_BASE, "Group-B-2", "veto-attribution-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupb-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
