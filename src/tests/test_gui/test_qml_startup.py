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
        "phaseRail",
        "populationStage",
        "feedbackPanel",
        "playerHandoffOverlay",
    ]
    for object_name in expected_objects:
        assert root.findChild(QObject, object_name) is not None, object_name
