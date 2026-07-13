"""
QML startup regression tests.

These tests catch the GUI-P0-01 failure mode where QQmlApplicationEngine.load()
returns no root object because a nested QML import cannot be resolved.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

from src.api import session_api
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.session_store import GuiSessionStore


class _DummyGuiApp(QObject):
    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        return bool(next_player_id)


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine():
    _get_app()
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")

    state = result["data"]["state"]
    store = GuiSessionStore(state)
    store.initialize(result["data"]["human_players"][0])

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

    gui_app = _DummyGuiApp()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", gui_app)
    engine._test_refs = (store, theme, gui_app)
    return engine, qml_dir


def test_main_qml_loads_root_window():
    engine, qml_dir = _create_engine()
    main_qml = os.path.join(qml_dir, "Main.qml")

    engine.load(QUrl.fromLocalFile(main_qml))
    QGuiApplication.processEvents()

    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    root = roots[0]
    assert isinstance(root, QWindow)


def test_main_qml_exposes_core_gui_regions():
    engine, qml_dir = _create_engine()
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()

    root = engine.rootObjects()[0]
    expected_objects = [
        "gameShell",
        "topStatusBar",
        "phaseRail",
        "centerPanel",
        "stageAnnouncement",
        "stageContainer",
        "contextPanel",
        "bottomQueryBar",
        "queryResultOverlay",
        "queryResultDialog",
        "mortalityStage",
        "populationStage",
        "senateStage",
        "lockedStagePlaceholder",
        "feedbackPanel",
        "playerHandoffOverlay",
    ]
    for object_name in expected_objects:
        assert root.findChild(QObject, object_name) is not None, object_name


def test_mortality_stage_hierarchy_is_attached_to_desktop_slots():
    engine, qml_dir = _create_engine()
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()

    root = engine.rootObjects()[0]
    center_panel = root.findChild(QObject, "centerPanel")
    assert center_panel is not None

    stage_header = root.findChild(QObject, "stageHeaderSlot")
    stage_instruction = root.findChild(QObject, "stageInstructionSlot")
    stage_content = root.findChild(QObject, "stageContentSlot")
    stage_action = root.findChild(QObject, "stageActionSlot")

    stage_announcement = root.findChild(QObject, "stageAnnouncement")
    stage_container = root.findChild(QObject, "stageContainer")
    mortality_stage = root.findChild(QObject, "mortalityStage")

    assert stage_header.property("height") >= 70
    assert stage_instruction.property("height") >= 40
    assert stage_content.property("height") > 0
    assert stage_action.property("height") >= 40
    assert stage_announcement.property("height") == stage_header.property("height")
    assert stage_container.property("height") == stage_content.property("height")
    assert stage_announcement.property("width") == stage_header.property("width")
    assert stage_container.property("width") == stage_content.property("width")
    assert stage_announcement.property("height") < center_panel.property("height")
    assert stage_container.property("height") < center_panel.property("height")


def test_opc_shell_exposes_twelve_bottom_query_buttons():
    engine, qml_dir = _create_engine()
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()

    root = engine.rootObjects()[0]
    bottom_bar = root.findChild(QObject, "bottomQueryBar")
    assert bottom_bar is not None
    query_ids = [
        "game_status",
        "faction_info",
        "war_list",
        "legion_status",
        "figure_search",
        "faction_treasury",
        "public_land",
        "private_land",
        "contract_status",
        "province_info",
        "fleet_status",
        "help",
    ]
    assert bottom_bar.property("queryButtonCount") == 12
    assert bottom_bar.property("queryButtonIds").split(",") == query_ids


def test_shell_store_exposes_seven_phase_navigation_items():
    engine, qml_dir = _create_engine()
    store = engine._test_refs[0]

    assert len(store.phaseNavigation) == 7
    assert store.currentPhaseId == "mortality"
    assert store.phaseNavigation[0]["name"] == "天命"
    assert [phase["id"] for phase in store.phaseNavigation] == [
        "mortality",
        "revenue",
        "forum",
        "population",
        "senate",
        "combat",
        "resolution",
    ]
    assert store.phaseNavigation[5]["name"] == "战争"
    assert store.phaseNavigation[-1]["name"] == "决算"
    assert store.phaseNavigation[0]["actionable"] is True
    assert store.phaseNavigation[3]["implemented"] is True
    assert store.phaseNavigation[3]["actionable"] is False
    assert store.phaseNavigation[4]["implemented"] is True
    assert store.phaseNavigation[4]["interaction_mode"] == "readonly"
    assert store.phaseNavigation[4]["actionable"] is False


def test_shell_text_catalog_labels_treasury():
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    gui_text_path = os.path.join(qml_dir, "i18n", "GuiText.qml")

    with open(gui_text_path, "r", encoding="utf-8") as fh:
        gui_text = fh.read()

    assert 'treasuryPrefix: "国库 "' in gui_text
    assert 'factionTreasuryPrefix: "派系金库 "' in gui_text
    assert 'executeMortality: "执行天命"' in gui_text
    assert 'advanceMortality: "进入收入阶段"' in gui_text
    assert 'senateReadonlyBadge: "只读状态"' in gui_text
    assert 'senateActionsDisabled: "政治行动暂未开放"' in gui_text
    assert 'bottomQueryBarTitle: "全局查询"' in gui_text
    assert 'queryGameStatus: "游戏状态"' in gui_text
    assert 'queryLegionStatus: "军团状态"' in gui_text
    assert 'closeQueryResult: "关闭"' in gui_text


def test_senate_stage_detail_copy_uses_gui_text_catalog():
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    senate_stage_path = os.path.join(qml_dir, "stages", "SenateStage.qml")
    gui_text_path = os.path.join(qml_dir, "i18n", "GuiText.qml")

    with open(senate_stage_path, "r", encoding="utf-8") as fh:
        senate_stage = fh.read()
    with open(gui_text_path, "r", encoding="utf-8") as fh:
        gui_text = fh.read()

    scattered_labels = ["影响力", "需要海战", "赔款", "成本", "预期收益", " 位", " 年"]
    for label in scattered_labels:
        assert label not in senate_stage

    assert "senateInfluenceDetail" in senate_stage
    assert "senateThreatDetail" in senate_stage
    assert "senatePeaceDetail" in senate_stage
    assert "senateContractDetail" in senate_stage
    assert "senateLeaderCount" in senate_stage
    assert 'senateInfluenceLabel: "影响力"' in gui_text
    assert 'senateNavalRequiredLabel: "需要海战"' in gui_text
    assert 'senateExpectedProfitLabel: "预期收益"' in gui_text


def test_opc_shell_boundary_and_i18n_scans():
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    gui_paths = [
        os.path.join(PROJECT_ROOT, "src", "ui", "gui", "session_store.py"),
        os.path.join(PROJECT_ROOT, "src", "ui", "gui", "api_adapter.py"),
    ]
    for root_dir, _, files in os.walk(qml_dir):
        for filename in files:
            if filename.endswith(".qml"):
                gui_paths.append(os.path.join(root_dir, filename))

    forbidden_calls = [
        "game_api.execute_phase",
        "game_api.execute_turn",
        "CombatCommand",
        "phase_senate",
        "phase_forum",
        "phase_revenue",
        "phase_combat",
    ]
    for path in gui_paths:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        for forbidden in forbidden_calls:
            assert forbidden not in content, f"{forbidden} found in {path}"

    changed_qml = [
        os.path.join(qml_dir, "shell", "BottomQueryBar.qml"),
        os.path.join(qml_dir, "shell", "GameShell.qml"),
        os.path.join(qml_dir, "shell", "TopStatusBar.qml"),
        os.path.join(qml_dir, "shell", "ContextPanel.qml"),
        os.path.join(qml_dir, "shell", "FeedbackPanel.qml"),
        os.path.join(qml_dir, "shell", "QueryResultOverlay.qml"),
    ]
    scattered_new_copy = [
        "全局查询",
        "游戏状态",
        "派系信息",
        "战争列表",
        "军团状态",
        "查询结果",
        "结构化反馈",
        "阶段公告",
        "关闭",
    ]
    for path in changed_qml:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        for text in scattered_new_copy:
            assert text not in content, f"{text} found outside GuiText in {path}"

    context_panel_path = os.path.join(qml_dir, "shell", "ContextPanel.qml")
    with open(context_panel_path, "r", encoding="utf-8") as fh:
        context_panel = fh.read()
    assert "queryResultTitle" not in context_panel
    assert "globalQueryResult.items" not in context_panel


def test_revenue_stage_structural_placement():
    """验证 RevenueStage 正确挂载到 stageContent 容器。"""
    engine, qml_dir = _create_engine()
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()

    root = engine.rootObjects()[0]

    # SR1: revenueStage exists and parent is stageContainer
    stage = root.findChild(QObject, "revenueStage")
    assert stage is not None, "revenueStage not found in QML tree"
    container = stage.parent()
    assert container.objectName() == "stageContainer", \
        f"RevenueStage parent is '{container.objectName()}', expected 'stageContainer'"

    # SR2: RevenueStage width ≈ container width (error < 5px)
    width_diff = abs(stage.property("width") - container.property("width"))
    assert width_diff < 5, \
        f"RevenueStage width {stage.property('width')} != container width {container.property('width')} (diff={width_diff})"

    # SR3: RevenueStage height ≈ container height (error < 5px)
    height_diff = abs(stage.property("height") - container.property("height"))
    assert height_diff < 5, \
        f"RevenueStage height {stage.property('height')} != container height {container.property('height')} (diff={height_diff})"

    # SR4: revenueActionLayer exists
    action_layer = root.findChild(QObject, "revenueActionLayer")
    assert action_layer is not None, "revenueActionLayer not found"
    center_panel = root.findChild(QObject, "centerPanel")
    assert action_layer.parent().objectName() == "centerPanel", \
        f"revenueActionLayer parent is '{action_layer.parent().objectName()}', expected 'centerPanel'"
