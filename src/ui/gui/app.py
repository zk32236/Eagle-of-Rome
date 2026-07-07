"""
src/ui/gui/app.py
GUI 应用主类 — 初始化 PySide6、注册 QML 类型、加载主界面。
"""
import os
import sys
import logging

import PySide6
from PySide6.QtCore import QUrl, QObject, Signal, Slot, qVersion
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

from src.core.game_state import GameState
from src.ui.gui.session_store import GuiSessionStore
from src.ui.gui.controllers.population_controller import PopulationController
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel

logger = logging.getLogger("EOR-GUI")


class GuiApp(QObject):
    """Eagle of Rome GUI 应用主类。"""

    engineLoaded = Signal(bool)
    errorOccurred = Signal(str)

    def __init__(self, state: GameState, parent=None):
        super().__init__(parent)
        self._state = state
        self._store = GuiSessionStore(state)
        self._engine = None
        self._root = None
        self._theme = None

    def run(self, argv=None):
        """启动 GUI 应用。"""
        app = QGuiApplication(argv or sys.argv)
        app.setApplicationName("Eagle of Rome")
        app.setOrganizationName("EOR")
        app.setFont(QFont("Microsoft YaHei UI"))
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"PySide6 version: {PySide6.__version__}")
        logger.info(f"Qt version: {qVersion()}")

        # 注册 QML 类型
        qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
        qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
        qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

        self._engine = QQmlApplicationEngine()
        self._engine.warnings.connect(self._on_qml_warnings)

        # 设置 QML 导入路径
        qml_dir = os.path.join(os.path.dirname(__file__), "qml")
        self._engine.addImportPath(qml_dir)
        logger.info(f"QML directory: {qml_dir}")

        # 获取 QML 根目录
        logger.info(f"QML import paths: {self._engine.importPathList()}")

        # 加载 Theme 组件并设置为上下文属性
        theme_component = QQmlComponent(self._engine)
        theme_qml = os.path.join(qml_dir, "theme", "Theme.qml")
        theme_component.loadUrl(QUrl.fromLocalFile(os.path.normpath(theme_qml)))
        if theme_component.isError():
            logger.error(f"Theme.qml errors: {theme_component.errorString()}")
        else:
            theme_obj = theme_component.create()
            if theme_obj:
                self._theme = theme_obj
                self._engine.rootContext().setContextProperty("theme", self._theme)
                logger.info("Theme object created and exposed as 'theme'")
            else:
                logger.error("Failed to create Theme object")

        # 设置上下文属性（QML 可直接访问）
        self._engine.rootContext().setContextProperty("sessionStore", self._store)
        self._engine.rootContext().setContextProperty("guiApp", self)

        # 加载主 QML
        main_qml = os.path.join(qml_dir, "Main.qml")
        url = QUrl.fromLocalFile(os.path.normpath(main_qml))
        logger.info(f"Loading QML: {url.toString()}")
        self._log_qml_component_status(qml_dir, [
            "Main.qml",
            os.path.join("shell", "GameShell.qml"),
            os.path.join("stages", "PopulationStage.qml"),
            os.path.join("shell", "FeedbackPanel.qml"),
        ])
        self._engine.load(url)

        # 检查 QML 加载结果（rootObjects 为空即加载失败）
        root_objects = self._engine.rootObjects()
        logger.info(f"Root objects count: {len(root_objects)}")

        if not root_objects:
            logger.error("Failed to load Main.qml: rootObjects() is empty")
            self._log_qml_component_status(qml_dir, [
                "Main.qml",
                os.path.join("shell", "GameShell.qml"),
                os.path.join("stages", "PopulationStage.qml"),
                os.path.join("stages", "FestivalView.qml"),
                os.path.join("stages", "VoteView.qml"),
                os.path.join("stages", "ElectionResultView.qml"),
            ])
            self.errorOccurred.emit("Failed to load Main.qml")
            self.engineLoaded.emit(False)
            return 1

        # 根对象应该是 Window
        window = root_objects[0]
        logger.info(f"Root object type: {type(window).__name__}")
        logger.info(f"Root object className: {window.metaObject().className()}")

        # 查找 GameShell 子组件
        self._root = window.findChild(QObject, "gameShell")
        if not self._root:
            logger.warning("GameShell not found as child of Window, using window as root")
            self._root = window
        else:
            logger.info("GameShell found via findChild")
        logger.info(f"GameShell lookup result: {bool(self._root)}")
        self.engineLoaded.emit(True)

        # 初始化 store（设置第一个 viewer）
        current = self._state.get_current_player()
        if current:
            self._store.initialize(current.player_id)
            logger.info(f"GUI initialized for viewer: {current.player_id}")

        # 连接 store 信号到 QML
        self._store.feedbackRaised.connect(self._on_feedback)
        self._store.handoffRequired.connect(self._on_handoff)

        # 启动事件循环
        logger.info("Starting event loop...")
        exit_code = app.exec()
        logger.info(f"Event loop exited with code: {exit_code}")
        return exit_code

    @Slot(list)
    def _on_qml_warnings(self, warnings):
        for warning in warnings:
            logger.error(f"QML warning: {warning.toString()}")

    def _log_qml_component_status(self, qml_dir: str, relative_paths):
        for rel_path in relative_paths:
            path = os.path.normpath(os.path.join(qml_dir, rel_path))
            component = QQmlComponent(self._engine)
            component.loadUrl(QUrl.fromLocalFile(path))
            if component.isError():
                logger.error(f"QML component error [{rel_path}]: {component.errorString()}")
            else:
                logger.info(f"QML component ready [{rel_path}]: {path}")

    @Slot(str, str)
    def _on_feedback(self, ftype: str, fmsg: str):
        """反馈信号转发到 QML"""
        try:
            if self._root is not None:
                self._root.showFeedback(ftype, fmsg)
        except Exception as e:
            logger.warning(f"showFeedback failed: {e}")

    @Slot(str)
    def _on_handoff(self, next_player_id: str):
        """玩家交接信号转发到 QML"""
        try:
            if self._root is not None:
                self._root.showHandoff(next_player_id)
        except Exception as e:
            logger.warning(f"showHandoff failed: {e}")

    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        """QML 调用：确认交接后切换 viewer"""
        return self._store.switchViewer(next_player_id)

    def get_store(self) -> GuiSessionStore:
        return self._store
