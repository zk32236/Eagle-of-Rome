# src/tests/test_gui/test_wpj_groupa_r1_render_evidence.py
"""WP-J Group-A R1 — RENDER_AUTOMATED 截图证据（route = DIRECT_PRODUCTION）。

真实生产链：`session_api.create_gui_prototype_session`（或真实战斗状态）→ 真实
`GuiSessionStore` → 真实生产动作（selectPhase / doExecuteMortality / 战斗写路径）→
真实 `Main.qml` 离屏渲染（QT_QPA_PLATFORM=offscreen）→ `window.grabWindow()` → PNG。

证据落 `03-da-evidence/Group-A/R1/`：
- A-4-stepbar/：步骤条间距（forum 2 节点；1280×720 与 1440×900）。
- A-6-combat/：多战争步骤条（N≥2）+ N=0（全灰）。
- A-5-mortality/：死亡行归公明细（生产者按人供数）。

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

from src.api import combat_api, session_api  # noqa: E402
from src.core.entities.entities import Faction, GameTurn  # noqa: E402
from src.core.entities.figure import Figure  # noqa: E402
from src.core.entities.player import Player, PlayerType  # noqa: E402
from src.core.entities.war import War, WarType, WarStatus  # noqa: E402
from src.core.game_state import GameState  # noqa: E402
from src.core.systems.military_system import MilitarySystem  # noqa: E402
from src.core.systems.war_system import WarSystem  # noqa: E402
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
            if img is None or img.isNull():
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
    return result[0] if result else None


def _teardown(engine):
    """释放离屏窗口与引擎（降低全量套件下的 offscreen 资源累积）。"""
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


def _emit(slice_dir, name, capture, state_prep, phase, viewport, extra=None):
    out_dir = os.path.join(EVIDENCE_BASE, "R1", slice_dir)
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, name)
    meta = os.path.join(out_dir, name[:-4] + ".runtime.json")
    row = {
        "fixture": "test_wpj_groupa_r1_render_evidence.py",
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
    if extra:
        row.update(extra)
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return row


# ---------------------------------------------------------------------------
# states
# ---------------------------------------------------------------------------

def _prototype_store(start_phase="mortality"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _combat_state(wars_spec):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for ph in ("mortality", "revenue", "forum", "population", "senate"):
        state.mark_phase_executed(ph)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    for cid in sorted({c for (_, _, c) in wars_spec if c is not None}):
        f = Figure(id=cid, name="C%d" % cid, faction_id="optimates", age=40)
        f.martial = 6
        state.add_member(f)
        faction.member_ids.append(cid)
    player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    ms = state._military_system
    for idx, (wid, wname, cid) in enumerate(wars_spec):
        w = War(id=wid, name=wname, war_type=WarType.FOREIGN, strength=8,
                threat_level=3, rewards={"treasury": 100})
        w.commander_id = cid
        w.legions_assigned = 1
        ln = idx + 1
        w.add_legion_number(ln)
        w.status = WarStatus.ACTIVE
        state._war_system._active_wars.append(w)
        ok, _ = ms.recruit_legion(ln)
        assert ok, "recruit legion %d failed" % ln
        ms.assign_to_war([ln], wid, cid)
    store = GuiSessionStore(state)
    store.initialize("player_opt")
    return store, state, "player_opt"


# ---------------------------------------------------------------------------
# A-4 step bar spacing (1280×720 & 1440×900)
# ---------------------------------------------------------------------------

def test_render_r1_a4_stepbar_two_viewports():
    from src.api import forum_api
    rows = []
    for (w, h, tag) in ((1280, 720, "1280x720"), (1440, 900, "1440x900")):
        store, state, viewer = _prototype_store("forum")
        store.selectPhase("forum")
        steps = store.phaseSteps
        assert steps and len(steps) >= 2, steps
        engine, _ = _create_engine(store)
        name = "stepbar-forum-%s.png" % tag
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "R1", "A-4-stepbar", name), w, h)
        rows.append(_emit("A-4-stepbar", name, cap,
                          "create_gui_prototype_session(forum)+selectPhase(forum)",
                          "forum", (w, h)))
        _teardown(engine)
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# A-6 combat steps (multi-war + N=0)
# ---------------------------------------------------------------------------

def test_render_r1_a6_combat_multi_war():
    store, state, viewer = _combat_state([
        ("war_a", "皮洛士战争", 1),
        ("war_b", "西西里叛乱", 2),
        ("war_c", "伊比利亚威胁", None),
    ])
    store.selectPhase("combat")
    steps = store.phaseSteps
    assert len(steps) == 3, steps
    engine, _ = _create_engine(store)
    name = "combat-multi-war-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "R1", "A-6-combat", name), 1440, 900)
    row = _emit("A-6-combat", name, cap,
                "combat_state(3 wars: 2 commanded + 1 no-commander)+selectPhase(combat)",
                "combat", (1440, 900), extra={"n_wars": 3, "slot_count": len(steps)})
    _teardown(engine)
    assert row["capture_ok"], row


def test_render_r1_a6_combat_n0():
    store, state, viewer = _prototype_store("combat")
    store.selectPhase("combat")
    steps = store.phaseSteps
    assert len(steps) == 3 and all(s["state"] == "not_applicable" for s in steps), steps
    engine, _ = _create_engine(store)
    name = "combat-n0-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "R1", "A-6-combat", name), 1440, 900)
    row = _emit("A-6-combat", name, cap,
                "create_gui_prototype_session(combat)+selectPhase(combat) [N=0]",
                "combat", (1440, 900), extra={"n_wars": 0, "slot_count": len(steps)})
    _teardown(engine)
    assert row["capture_ok"], row


# ---------------------------------------------------------------------------
# A-5 mortality confiscation rows (producer-supplied)
# ---------------------------------------------------------------------------

def _force_death_with_assets(state, count=2):
    try:
        cfg = state._config._config
        mort = cfg.setdefault("mortality_rules", {})
        mort["event_deck"] = [{"name": "死神来了", "effect": "death", "weight": 1}]
        mort["event_draw_count"] = 1
        mort["death_count"] = count
        state._initialize_mortality_pool()
    except Exception:  # noqa: BLE001
        pass
    living = state.get_living_members()
    for idx, m in enumerate(living[:count]):
        m.wealth = (idx + 1) * 100
        m._land_private = (idx + 1) * 3


def test_render_r1_a5_mortality_confiscation_rows():
    store, state, _ = _prototype_store("mortality")
    _force_death_with_assets(state, 2)
    fb = store.doExecuteMortality()
    assert fb.get("success"), fb.get("message")
    store.selectPhase("mortality")
    deaths = [
        imp for ev in (store.mortalityEvents or [])
        for imp in (ev.get("impacts") or []) if imp.get("type") == "figure_death"
    ]
    assert deaths, "强制死亡牌组必须产出 figure_death impacts"
    assert any(imp.get("wealth_confiscated", 0) >= 1 for imp in deaths), deaths
    engine, _ = _create_engine(store)
    name = "mortality-confiscation-rows-1440x900.png"
    cap = _capture(engine, os.path.join(EVIDENCE_BASE, "R1", "A-5-mortality", name), 1440, 900)
    row = _emit("A-5-mortality", name, cap,
                "create_gui_prototype_session(mortality)+force_death_deck+set_assets+doExecuteMortality+selectPhase",
                "mortality", (1440, 900), extra={"death_count": len(deaths)})
    _teardown(engine)
    assert row["capture_ok"], row
