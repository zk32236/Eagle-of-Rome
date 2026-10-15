"""S-D-2 — GUI Readiness **R-1 integrated REAL production chain**.

EOR20261013-02 GUI Readiness · slice S-D · sub-task S-D-2.

Frozen design basis (write face = Overlay §1.2 + §2/§2.1 + §4; Delta §2/§3):

  * Delta §2.1 — the exact REAL chain S-D requires (single, non-substitutable)::

        gui_main.main
          -> _extract_scenario(argv)                       # parser (basename)
          -> session_api.create_gui_prototype_session(...) # factory
              -> scenario_validation.prepare_selected_scenario(...)  # single capture
              -> ScenarioLoader.initialize_validated_scenario(state, snapshot)
          -> GuiApp(state)                                 # real Qt app
          -> real QML (GameShell / stage controls)
          -> real Store slot -> api_adapter -> API authority -> real Core state

  * Delta §2.3 prohibitions (enforced here): no test-only constructor; no GameState
    injection (``_mk_state`` / ``Player(...)`` / controller forcing); no mock
    substitution for the real receiver / Store / Adapter; no CLI/API game-action
    substitute; no ``start_phase=`` phase-flow skip; no ``testing.bypass_player_check``.
  * Delta §2.4 R-1 positive-proof elements exercised below: ``--scenario`` selected
    and validated (source SHA recorded, ZERO fallback); ``GuiApp`` realised and a
    REAL QML control hit; the real Store->Adapter->authority read executed; and an
    **independent oracle** that reads the raw Core/domain (``GameState``) — never the
    production DTO as sole oracle.

Evidence class: `PRODUCTION_CHAIN` (the parser/factory/validated-loader/GuiApp/QML
launch is the real production entry). The QML engine is installed by this harness
mirroring the non-blocking portion of ``GuiApp.run`` (the production ``run`` blocks
in ``QGuiApplication.exec``); the session/game chain above is entirely production.

WATERMARK: S-D-2 DA EXECUTION — NOT runtime/API/GUI acceptance; candidate
dirty/uncommitted; no commit/push/delete; no product-code change.
"""
from __future__ import annotations

import hashlib
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

import gui_main
from src.api import session_access, session_api
from src.core.scenario_validation import DEFAULT_SCENARIO_FILE
from src.ui.gui.app import GuiApp
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVATE,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIOS_DIR = os.path.join(PROJECT_ROOT, "data", "scenarios")

# Disconnect falsification (Overlay §4 / R4 §5): when set, the real control->Store
# binding is disconnected so the corresponding integrated test MUST fail. This is
# the RED witness proving the test detects the absence of the real binding.
_FALSIFY = os.environ.get("GR_SD2_FALSIFY") == "1"

# ---------------------------------------------------------------------------
# The three frozen fixtures (G4-S-D-2 §3): byte SHA-256 + expected composition.
# These hashes bind the SOURCE evidenced by the validated-loader capture; they are
# re-derived from the real file bytes in the tests (no placeholder treated as proven).
# ---------------------------------------------------------------------------
FIXTURES = {
    "gr_f_3h.json": {
        "sha256": "68e97ea02ecfd77470423db35a659983c1f33016e00a97541b34b6f1bf24e2c6",
        "factions": 3, "human": 3, "ai": 0,
    },
    "gr_f_3h3ai.json": {
        "sha256": "a631c8e46b7669562490ef7683478c25b4858bd7d4a5f4d56f04127b595b6ecf",
        "factions": 6, "human": 3, "ai": 3,
    },
    "gr_f_6h.json": {
        "sha256": "0b40469c44807dc073b60585f56117dc6d7cb58796f4f82f664a7907fa8d626d",
        "factions": 6, "human": 6, "ai": 0,
    },
}


@pytest.fixture(autouse=True)
def _restore_rng():
    """Session creation consumes RNG deterministically; keep suite ordering inert."""
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


def _fixture_bytes_sha256(name: str) -> str:
    with open(os.path.join(SCENARIOS_DIR, name), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _raw_core_oracle(state):
    """INDEPENDENT oracle: read the raw Core/domain (never the production DTO)."""
    players = list(state.get_all_players())
    return {
        "n_players": len(players),
        "human": sum(1 for p in players if p.player_type.value == "human"),
        "ai": sum(1 for p in players if p.player_type.value == "ai"),
        "factions": len(state.factions),
        "current": getattr(state.get_current_player(), "player_id", None),
        "turn": state.turn.turn_number if state.turn else None,
    }


# ---------------------------------------------------------------------------
# Qt / QML harness (mirrors the non-blocking portion of GuiApp.run)
# ---------------------------------------------------------------------------
def _app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _events(rounds=5):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)


def _install_engine(app):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    from src.ui.gui.models.candidate_list_model import CandidateListModel
    from src.ui.gui.models.event_list_model import EventListModel
    from src.ui.gui.models.figure_list_model import FigureListModel

    _app()
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    eng = QQmlApplicationEngine()
    eng.addImportPath(qml_dir)

    theme_component = QQmlComponent(eng)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    eng.rootContext().setContextProperty("theme", theme)
    eng.rootContext().setContextProperty("sessionStore", app.get_store())
    eng.rootContext().setContextProperty("guiApp", app)

    eng.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    roots = eng.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    window = roots[0]

    # production wiring the blocking run() performs after load:
    app._engine = eng
    app._theme = theme
    app._root = window.findChild(QObject, "gameShell") or window
    app.bind_frame_window(window)
    current = app._state.get_current_player()
    session_access.register_hotseat_session(app._state, current.player_id, epoch=0)
    app.get_store().setHandoffBarrierProvider(app)
    app.get_store().initialize(current.player_id)
    _events()
    return eng, window


def _find(root, name):
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem
    try:
        item = root.findChild(QQuickItem, name)
        if item is not None:
            return item
    except Exception:
        pass
    start = root.contentItem() if hasattr(root, "contentItem") else root
    pending = [start]
    while pending:
        node = pending.pop()
        try:
            if node.objectName() == name:
                return node
        except Exception:
            pass
        try:
            pending.extend(node.childItems())
        except Exception:
            pass
    try:
        return root.findChild(QObject, name)
    except Exception:
        return None


def _launch_real_chain(scenario_basename):
    """Real chain: parser -> factory -> validated loader -> GuiApp -> QML."""
    scenario_file, _forwarded = gui_main._extract_scenario(
        ["gui_main.py", "--scenario", scenario_basename])
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, scenario_file=scenario_file)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    app = GuiApp(state)
    eng, window = _install_engine(app)
    return app, eng, window, res


# ===========================================================================
# 1. Parser (production launch argument)
# ===========================================================================
def test_parser_selects_basename_and_strips_it():
    scenario, forwarded = gui_main._extract_scenario(
        ["gui_main.py", "--scenario", "gr_f_3h3ai.json", "-platform", "offscreen"])
    assert scenario == "gr_f_3h3ai.json"
    assert "--scenario" not in forwarded and "gr_f_3h3ai.json" not in forwarded


def test_parser_explicit_empty_rejected():
    with pytest.raises(ValueError):
        gui_main._extract_scenario(["gui_main.py", "--scenario="])
    with pytest.raises(ValueError):
        gui_main._extract_scenario(["gui_main.py", "--scenario", ""])


def test_parser_default_only_when_absent():
    scenario, _ = gui_main._extract_scenario(["gui_main.py"])
    assert scenario is None
    assert DEFAULT_SCENARIO_FILE == "gui_prototype.json"
    assert gui_main.DEFAULT_SCENARIO_FILE == "gui_prototype.json"


def test_main_explicit_empty_exits_2_before_factory(monkeypatch):
    """An explicit empty value must fail BEFORE any factory/GuiApp call."""
    called = {"factory": 0, "gui": 0}

    def _deny_factory(*a, **k):
        called["factory"] += 1
        raise AssertionError("factory must not be called on an explicit-empty arg")

    def _deny_gui(*a, **k):
        called["gui"] += 1
        raise AssertionError("GuiApp must not be constructed on an explicit-empty arg")

    monkeypatch.setattr(gui_main.session_api, "create_gui_prototype_session", _deny_factory)
    monkeypatch.setattr(gui_main, "GuiApp", _deny_gui)
    monkeypatch.setattr(sys, "argv", ["gui_main.py", "--scenario="])
    assert gui_main.main() == 2
    monkeypatch.setattr(sys, "argv", ["gui_main.py", "--scenario", ""])
    assert gui_main.main() == 2
    assert called == {"factory": 0, "gui": 0}


def test_main_absent_scenario_uses_the_default_basename(monkeypatch):
    """Only a MISSING --scenario falls back to the historical default basename."""
    seen = {}

    def _capture(config_path=None, start_phase="mortality", scenario_file=DEFAULT_SCENARIO_FILE):
        seen["scenario_file"] = scenario_file
        return {"success": False, "message": "stop after capture"}

    monkeypatch.setattr(gui_main.session_api, "create_gui_prototype_session", _capture)
    monkeypatch.setattr(sys, "argv", ["gui_main.py"])
    assert gui_main.main() == 1  # captured, then stopped (no GuiApp/run)
    assert seen["scenario_file"] == "gui_prototype.json"


# ===========================================================================
# 2. Factory + validated loader (real capture; source SHA; ZERO fallback)
# ===========================================================================
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_real_factory_validated_loader_source_sha_zero_fallback(name):
    expected = FIXTURES[name]
    # the fixture bytes are byte-identical to the frozen G4 identity
    assert _fixture_bytes_sha256(name) == expected["sha256"]

    scenario_file, _ = gui_main._extract_scenario(["gui_main.py", "--scenario", name])
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, scenario_file=scenario_file)
    assert res.get("success"), res.get("message")

    report = res["data"]["scenario"]
    # source SHA recorded from the single validated capture == frozen bytes hash
    assert report["sha256"] == expected["sha256"]
    assert report["scenario_file"] == name
    # ZERO fallback: the selected canonical scenario is NOT the built-in default
    assert report["scenario_file"] != DEFAULT_SCENARIO_FILE
    assert report["faction_count"] == expected["factions"]
    assert report["human_count"] == expected["human"]
    assert report["ai_count"] == expected["ai"]

    # INDEPENDENT oracle: raw Core/domain (not the production DTO)
    core = _raw_core_oracle(res["data"]["state"])
    assert core["n_players"] == expected["factions"]
    assert core["human"] == expected["human"]
    assert core["ai"] == expected["ai"]
    assert core["factions"] == expected["factions"]


def test_real_factory_rejects_missing_scenario_without_fallback():
    """A non-existent selection must fail closed — NEVER fall back to the default."""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, scenario_file="gr_f_does_not_exist.json")
    assert res.get("success") is False
    assert "SCENARIO_INVALID" in (res.get("message") or "")
    assert "state" not in (res.get("data") or {})


# ===========================================================================
# 3. GuiApp + REAL QML control hit -> real Store
# ===========================================================================
def test_real_qml_tree_exposes_shell_and_controls():
    _app, _eng, window, _res = _launch_real_chain("gr_f_3h3ai.json")
    for name in ("gameShell", "playerHandoffOverlay", "bottomQueryBar",
                 "contextPanel", "phaseRail", "topStatusBar", "centerPanel"):
        assert _find(window, name) is not None, name
    # the bounded continuation recovery control is present (S-D-1 binding)
    overlay = _find(window, "playerHandoffOverlay")
    assert overlay is not None
    assert _find(overlay, "grHandoffStart") is not None
    assert _find(overlay, "grContinuationRecover") is not None


def test_real_control_click_reaches_the_real_store(monkeypatch):
    """R-1 (ii): the GuiApp is realised and a REAL QML control is hit; the real
    production Store receives the dispatch (neutral startup -> pending token
    consumed on requestTakeover)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    if _FALSIFY:
        # disconnect the real control binding: the QML 接管 dispatch no longer
        # reaches the Store -> the assertions below MUST fail (RED witness).
        monkeypatch.setattr(GuiSessionStore, "requestTakeover",
                            lambda self: {"accepted": False})

    app, _eng, window, res = _launch_real_chain("gr_f_3h3ai.json")
    store = app.get_store()

    overlay = _find(window, "playerHandoffOverlay")
    assert overlay is not None
    assert overlay.property("visible") is True
    assert overlay.property("maskedMode") is True

    # neutral startup: a bounded takeover is pending with a private token
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    token_before = store._pending_token
    assert token_before, "neutral startup must hold a private pending token"

    button = _find(overlay, "grHandoffStart")
    assert button is not None
    point = button.mapToScene(QPointF(float(button.property("width")) / 2.0,
                                      float(button.property("height")) / 2.0))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, point.toPoint())
    _events()

    # the real control reached the real Store: the single-use token was consumed
    # and the seat left MASKED_PENDING (ACTIVATE is entered synchronously; the
    # async frame-gated commit may fail-closed on the offscreen platform).
    assert store._pending_token == "", "the real control did not reach the Store"
    assert store.seatLifecycle in (SEAT_ACTIVATE, SEAT_MASKED_FAILURE, SEAT_ACTIVE), \
        store.seatLifecycle


def test_real_chain_gui_app_store_binds_the_factory_state():
    """The GuiApp Store owns the SAME GameState produced by the validated loader
    (no injected/duplicated state)."""
    app, _eng, _window, res = _launch_real_chain("gr_f_3h.json")
    state = res["data"]["state"]
    assert app.get_store()._state is state
    assert app._state is state
    core = _raw_core_oracle(state)
    assert core["n_players"] == 3 and core["human"] == 3


# ===========================================================================
# 4. Real Store -> Adapter -> API authority -> real Core (independent oracle)
# ===========================================================================
def test_real_adapter_authority_read_matches_raw_core():
    """A real adapter read through the API authority returns DTO data that the
    INDEPENDENT raw-Core oracle confirms (turn_number / phase)."""
    scenario_file, _ = gui_main._extract_scenario(
        ["gui_main.py", "--scenario", "gr_f_3h.json"])
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, scenario_file=scenario_file)
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    store = GuiSessionStore(state)

    envelope = store._adapter.read_envelope(session_api.get_session_snapshot,
                                            state, pids[0])
    assert envelope.get("success") is True, envelope.get("message")

    # independent oracle: the raw Core turn number (never the DTO as sole oracle)
    raw_turn = state.turn.turn_number if state.turn else 0
    assert envelope["data"]["public_resources"]["turn_number"] == raw_turn


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
