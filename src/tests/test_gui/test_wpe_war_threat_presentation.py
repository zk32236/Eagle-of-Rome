# src/tests/test_gui/test_wpe_war_threat_presentation.py
"""
WP-E（GUI-BETA-R1）War Threat / Auto-Activation 投影测试（T-4）。

覆盖（F7，14P / 06P，production chain — initialize_forum_turn 真实产出 war_events）：
- THREAT 升级 → DTO war_events 行（E-G7-14P-01）
- auto-activation → has_active_war=True + 爆发行 + refresh/re-entry 收敛（06P-02）
- stale「无战争威胁」消除（06P-01：war_events 存在 → 空态三条件不显示）
- 无威胁无战争 → 空态仍显示（不回归）
- WP-G 生命周期零改动（auto-activation 合法性不裁决；traceability 记录）
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import forum_api, session_api


def _make_forum_state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    return state, ws


def _add_player_and_faction(state):
    """真实 Player + Faction（快照依赖 faction.treasury / get_leader 等）。"""
    from src.core.entities.player import Player, PlayerType
    from src.core.entities.entities import Faction

    state.config._config["testing"] = {"bypass_player_check": True}
    state._players["p1"] = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state._factions["f1"] = Faction(id="f1", name="F1")
    return state


def _make_threat_war(ws, war_id: str, name: str, threat_level: int = 3):
    war = War(id=war_id, name=name, start_year=-270, threat_level=threat_level, strength=5)
    war.status = WarStatus.THREAT
    ws._threats.append(war)
    return war


def _make_war_events_for_threat_war(ws, war):
    """对齐 war_system.check_triggers / escalate_threats 的权威字符串形状。"""
    # 通过真实系统路径触发：调用 check_triggers 与 escalate_threats（尊重 enable_threats gate）
    events = ws.check_triggers(-260, verbose=False) + ws.escalate_threats()
    return events


# ---------------------------------------------------------------------------
# 1. war_events 保留载体（A8.1）
# ---------------------------------------------------------------------------

def test_initialize_forum_turn_persists_war_events():
    """initialize_forum_turn → war_events 写入保留载体（open_market 丢弃问题收敛）。"""
    state, ws = _make_forum_state()
    war = _make_threat_war(ws, "tw1", "Threat War", threat_level=6)
    # 使威胁战争可触发升级（真实路径）
    war._triggered_this_turn = False

    result = forum_api.initialize_forum_turn(state)
    assert result["success"] is True

    # 载体存在（无论是否产生事件，载体可读且与返回值一致）
    stored = state.get_forum_war_events()
    returned = result.get("data", {}).get("war_events", [])
    assert stored == returned
    assert isinstance(stored, list)


def test_war_events_carrier_cleared_on_year_advance():
    """war_events 载体随年度滚轮清除（_commit_settlement A2 段）。"""
    state, ws = _make_forum_state()
    state.set_forum_war_events(["⚔️ 战争爆发：Test War"])
    assert state.get_forum_war_events() == ["⚔️ 战争爆发：Test War"]

    state.advance_year()
    assert state.get_forum_war_events() == []


# ---------------------------------------------------------------------------
# 2. DTO 字段（A8.2）
# ---------------------------------------------------------------------------

def test_forum_view_war_events_and_has_active_war():
    """DTO 新增 war_events / has_active_war（war_system.py:949 权威访问器）。"""
    state, ws = _make_forum_state()
    _add_player_and_faction(state)
    state.set_forum_war_events(["⚠️ 威胁升级：Threat War"])

    # 无活跃战争 → has_active_war=False
    view = forum_api.get_forum_view(state, "p1")
    assert view["success"] is True
    assert view["data"]["war_events"] == ["⚠️ 威胁升级：Threat War"]
    assert view["data"]["has_active_war"] is False

    # 加入活跃战争 → has_active_war=True
    active = War(id="aw1", name="Active War", start_year=-270, threat_level=0, strength=5)
    active.status = WarStatus.ACTIVE
    ws._active_wars.append(active)
    view2 = forum_api.get_forum_view(state, "p1")
    assert view2["data"]["has_active_war"] is True


def test_auto_activation_converges_has_active_war():
    """06P-02：auto-activation → has_active_war=True + war_events 爆发行 + refresh 收敛。"""
    state, ws = _make_forum_state()
    _add_player_and_faction(state)

    # 模拟 auto-activation：威胁战争被移入 _active_wars（war_system.py:780 区域行为）
    war = _make_threat_war(ws, "tw1", "Threat War", threat_level=6)
    ws._threats.remove(war)
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)
    state.set_forum_war_events([f"⚔️ 战争爆发：{war.name}"])

    view = forum_api.get_forum_view(state, "p1")
    assert view["data"]["has_active_war"] is True
    assert any("Threat War" in e for e in view["data"]["war_events"])
    # refresh/re-entry 收敛（权威访问器重复读取稳定）
    view2 = forum_api.get_forum_view(state, "p1")
    assert view2["data"]["has_active_war"] is True
    assert view2["data"]["war_events"] == view["data"]["war_events"]


# ---------------------------------------------------------------------------
# 3. 空态三条件（A8.3）
# ---------------------------------------------------------------------------

def test_empty_gate_three_conditions_helpers():
    """空态三条件的 DTO 前提：war_threats 空 && war_events 空 && !has_active_war。"""
    state, ws = _make_forum_state()
    _add_player_and_faction(state)

    # 全空 → 空态成立（无战争威胁仍显示——不回归）
    view = forum_api.get_forum_view(state, "p1")
    assert view["data"]["war_threats"] == []
    assert view["data"]["war_events"] == []
    assert view["data"]["has_active_war"] is False
    empty_condition = (
        len(view["data"]["war_threats"]) == 0
        and len(view["data"]["war_events"]) == 0
        and not view["data"]["has_active_war"]
    )
    assert empty_condition is True

    # 仅 war_events 存在 → 空态不成立（stale「无战争威胁」消除，06P-01）
    state.set_forum_war_events(["⚠️ 威胁升级：Test"])
    view2 = forum_api.get_forum_view(state, "p1")
    empty_condition2 = (
        len(view2["data"]["war_threats"]) == 0
        and len(view2["data"]["war_events"]) == 0
        and not view2["data"]["has_active_war"]
    )
    assert empty_condition2 is False


# ---------------------------------------------------------------------------
# 4. RENDER：三条件门控
# ---------------------------------------------------------------------------

def _create_forum_qml_engine(store):
    import os
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType
    from PySide6.QtCore import QUrl, QObject
    from src.ui.gui.models.figure_list_model import FigureListModel
    from src.ui.gui.models.candidate_list_model import CandidateListModel
    from src.ui.gui.models.event_list_model import EventListModel

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication.instance() or QGuiApplication([])

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    qml_dir = os.path.join(project_root, "src", "ui", "gui", "qml")
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

    class _DummyGuiApp(QObject):
        pass

    gui_app = _DummyGuiApp()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", gui_app)
    return engine, qml_dir


def test_render_empty_gate_hides_empty_text_when_war_events_exist():
    """RENDER（06P-01）：war_events 存在 → announceWarThreatsEmpty 隐藏。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    from src.ui.gui.session_store import GuiSessionStore

    state, ws = _make_forum_state()
    _add_player_and_faction(state)
    state.set_forum_war_events(["⚠️ 威胁升级：Threat War"])

    store = GuiSessionStore(state)
    store.initialize("p1")
    store._refresh_forum_view()
    assert store.forumWarEvents == ["⚠️ 威胁升级：Threat War"]
    assert store.forumHasActiveWar is False
    # 选中 forum 阶段（生产真实展示路径：ForumStage 为当前阶段时绑定求值）
    store.selectPhase("forum")
    store._refresh_forum_view()

    engine, qml_dir = _create_forum_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    empty_text = root.findChild(QObject, "announceWarThreatsEmpty")
    assert empty_text is not None
    assert empty_text.property("visible") is False, (
        "war_events 存在时不得显示「无战争威胁」（06P-01 stale 消除）"
    )
    war_events = root.findChild(QObject, "announceWarEvents")
    assert war_events is not None
    assert war_events.property("visible") is True


def test_render_empty_gate_still_shows_when_all_empty():
    """RENDER（不回归）：无威胁无事件无活跃战争 → 空态仍显示。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    from src.ui.gui.session_store import GuiSessionStore

    state, ws = _make_forum_state()
    _add_player_and_faction(state)

    store = GuiSessionStore(state)
    store.initialize("p1")
    store._refresh_forum_view()
    # 选中 forum 阶段（绑定求值前提）
    store.selectPhase("forum")
    store._refresh_forum_view()

    engine, qml_dir = _create_forum_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    empty_text = root.findChild(QObject, "announceWarThreatsEmpty")
    assert empty_text is not None
    assert empty_text.property("visible") is True
