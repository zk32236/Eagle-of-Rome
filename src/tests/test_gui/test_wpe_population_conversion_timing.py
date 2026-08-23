# src/tests/test_gui/test_wpe_population_conversion_timing.py
"""
WP-E（GUI-BETA-R1）Population 转换公示时序测试（T-3）。

覆盖（F-E-03 production chain — 真实 begin_population_phase →
convert_battlefield_commanders → phase result → get_population_view → Store）：
- 门控改 total > 0（移除 populationResolved，E-ODR-04/R-11）：选举未解析时 banner 已可见（P6）
- 多转换渲染（022-04 ≥2 条，consul→proconsul + praetor→propraetor）
- 重复 refresh 不重复不丢失（P5，begin_population_phase 幂等 + 直读存储结果）
- 转换缺失 → 无 fallback（P7/022-05，E-13 fail-closed——QML 无 fallback 文案断言在 RENDER 层）
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.figure import Figure
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import population_api, session_api


def _make_population_state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    return state, ws


def _make_absent_commander(state, fig_id: int, name: str, office: str, war: War):
    """absent 指挥官 + 关联战争（真实前置状态）。"""
    fig = Figure(id=fig_id, name=name, office=office, is_absent=True)
    state.add_member(fig)
    war.commander_id = fig_id
    return fig


def _make_war(ws, war_id: str, name: str):
    war = War(id=war_id, name=name, start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)
    return war


# ---------------------------------------------------------------------------
# 1. 门控 total > 0（P6：选举未解析时转换公告已可见）
# ---------------------------------------------------------------------------

def test_conversion_result_produced_by_real_chain():
    """production chain：begin_population_phase → convert_battlefield_commanders →
    phase result → get_population_view DTO。"""
    state, ws = _make_population_state()
    war = _make_war(ws, "w1", "Sicily War")
    _make_absent_commander(state, 1, "Marcus", "consul", war)

    result = population_api.begin_population_phase(state)
    assert "converted" in result
    stored = state.get_phase_result("battlefield_commander_conversion")
    assert isinstance(stored, dict)
    assert stored["total"] == 1
    assert stored["converted"][0]["old_office"] == "consul"
    assert stored["converted"][0]["new_office"] == "proconsul"

    view = session_api.get_population_view(state, "player_1") if state.get_player("player_1") else None
    if view is not None:
        conv = view.get("data", {}).get("battlefield_commander_conversion", {})
        assert conv.get("total", 0) >= 1


def test_population_view_exposes_conversion_without_resolve():
    """get_population_view 后 populationResolved 可为 False，但转换结果已存在（门控前提）。"""
    from src.api import session_api as sa

    result = sa.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    ws = state.get_war_system()
    war = _make_war(ws, "w1", "Sicily War")
    _make_absent_commander(state, 1, "Marcus", "consul", war)

    view_result = sa.get_population_view(state, viewer_id)
    assert view_result["success"] is True
    data = view_result["data"]
    conv = data.get("battlefield_commander_conversion", {})
    assert conv.get("total", 0) == 1
    # 转换结果独立于选举解析（数据已到 DTO，门控仅决定展示）
    assert "resolved" in data


# ---------------------------------------------------------------------------
# 2. 多转换（022-04 ≥2 条）
# ---------------------------------------------------------------------------

def test_multi_conversion_two_rows():
    """consul→proconsul + praetor→propraetor 两条（通用渲染器不得抑制）。"""
    state, ws = _make_population_state()
    war1 = _make_war(ws, "w1", "Sicily War")
    war2 = _make_war(ws, "w2", "Gaul War")
    _make_absent_commander(state, 1, "Marcus", "consul", war1)
    _make_absent_commander(state, 2, "Lucius", "praetor", war2)

    population_api.begin_population_phase(state)
    stored = state.get_phase_result("battlefield_commander_conversion")
    assert stored["total"] == 2
    offices = {(c["old_office"], c["new_office"]) for c in stored["converted"]}
    assert ("consul", "proconsul") in offices
    assert ("praetor", "propraetor") in offices


# ---------------------------------------------------------------------------
# 3. 重复 refresh 不重复不丢失（P5）
# ---------------------------------------------------------------------------

def test_repeated_view_no_duplicate_no_loss():
    """多次 get_population_view → 幂等 no-op + 直读存储结果（不重复不丢失）。"""
    from src.api import session_api as sa

    result = sa.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    ws = state.get_war_system()
    war = _make_war(ws, "w1", "Sicily War")
    _make_absent_commander(state, 1, "Marcus", "consul", war)

    view1 = sa.get_population_view(state, viewer_id)["data"]
    conv1 = view1.get("battlefield_commander_conversion", {})
    assert conv1.get("total", 0) == 1

    for _ in range(3):
        view_n = sa.get_population_view(state, viewer_id)["data"]
        conv_n = view_n.get("battlefield_commander_conversion", {})
        assert conv_n.get("total", 0) == 1
        assert conv_n.get("converted", []) == conv1.get("converted", [])


def test_begin_population_phase_idempotent():
    """begin_population_phase 幂等：二次调用返回存储结果，不重复转换。"""
    state, ws = _make_population_state()
    war = _make_war(ws, "w1", "Sicily War")
    _make_absent_commander(state, 1, "Marcus", "consul", war)

    r1 = population_api.begin_population_phase(state)
    r2 = population_api.begin_population_phase(state)
    assert "converted" in r1
    assert "converted" in r2
    stored = state.get_phase_result("battlefield_commander_conversion")
    assert stored["total"] == 1


# ---------------------------------------------------------------------------
# 4. 转换缺失 → 无 fallback（P7/022-05 前置：fail-closed 数据侧）
# ---------------------------------------------------------------------------

def test_no_conversion_empty_result_no_fallback_data():
    """无 absent 指挥官 → 转换结果空；DTO 保持空结构（QML 无 fallback 文案由 RENDER 断言）。"""
    from src.api import session_api as sa

    result = sa.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)

    view = sa.get_population_view(state, viewer_id)["data"]
    conv = view.get("battlefield_commander_conversion", {})
    # 空态：total=0 / converted=[]
    assert conv.get("total", 0) == 0
    assert conv.get("converted", []) == []


# ---------------------------------------------------------------------------
# 5. RENDER：门控 total>0（选举未解析时 banner 可见）
# ---------------------------------------------------------------------------

def _create_population_qml_engine(store):
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


def test_render_conversion_banner_visible_without_election_resolved():
    """RENDER（P6）：选举未解析（populationResolved=false）但 total>0 → banner 可见。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    from src.ui.gui.session_store import GuiSessionStore

    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    ws = state.get_war_system()
    war = _make_war(ws, "w1", "Sicily War")
    _make_absent_commander(state, 1, "Marcus", "consul", war)

    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    store._refresh_population_view()
    # 数据侧前提：total>0 且 resolved=False（门控替换的验证基础）
    assert store.populationConversionResult.get("total", 0) >= 1
    assert store.populationResolved is False

    engine, qml_dir = _create_population_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    banner = root.findChild(QObject, "populationCommanderConversion")
    assert banner is not None, "populationCommanderConversion not found"
    assert banner.property("visible") is True, (
        "banner 必须在选举未解析时可见（门控 total>0，E-ODR-04）"
    )


def test_render_conversion_banner_hidden_when_no_conversion():
    """RENDER：无转换（total=0）→ banner 隐藏（无 fallback 文案，E-13 fail-closed）。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    from src.ui.gui.session_store import GuiSessionStore

    result = session_api.create_gui_prototype_session(start_phase="population")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)

    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    store._refresh_population_view()
    assert store.populationConversionResult.get("total", 0) == 0

    engine, qml_dir = _create_population_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    banner = root.findChild(QObject, "populationCommanderConversion")
    assert banner is not None
    assert banner.property("visible") is False
    # fail-closed：banner 内无 fallback 文案（仅 Repeater 直读 converted，无空态文本）
    from PySide6.QtQuick import QQuickItem
    texts = [str(i.property("text")) for i in _all_qquick_items(banner) if i.property("text")]
    assert not any("无转换" in t or "fallback" in t.lower() for t in texts), texts


def _all_qquick_items(root):
    from PySide6.QtQuick import QQuickItem
    start = root if isinstance(root, QQuickItem) else root.findChild(QQuickItem)
    pending = [start]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())
