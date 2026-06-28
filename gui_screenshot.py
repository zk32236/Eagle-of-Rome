#!/usr/bin/env python
"""
截图脚本：生成 GUI-P0-01 要求的 10 张截图
"""
import sys
import os

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel


def take_screenshot():
    app = QGuiApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI"))
    
    # 创建会话
    result = session_api.create_gui_prototype_session()
    if not result["success"]:
        print(f"Failed: {result['message']}", file=sys.stderr)
        return 1
    
    state = result["data"]["state"]
    human_players = result["data"]["human_players"]
    
    # 注册 QML 类型
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")
    
    store = GuiSessionStore(state)
    if human_players:
        store.initialize(human_players[0])
    
    engine = QQmlApplicationEngine()
    qml_dir = os.path.join(os.path.dirname(__file__), "src", "ui", "gui", "qml")
    engine.addImportPath(qml_dir)
    
    # 连接 QML 错误信号
    def on_object_created(obj, url):
        if obj is None:
            print(f"Failed to load QML: {url.toString()}", file=sys.stderr)
    engine.objectCreated.connect(on_object_created)
    
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", None)  # QML 中引用但不使用
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    if theme_component.isError():
        print(theme_component.errorString(), file=sys.stderr)
        return 1
    theme = theme_component.create()
    engine.rootContext().setContextProperty("theme", theme)
    
    main_qml = os.path.join(qml_dir, "Main.qml")
    engine.load(QUrl.fromLocalFile(main_qml))
    
    if not engine.rootObjects():
        print("Failed to load Main.qml", file=sys.stderr)
        return 1
    
    root = engine.rootObjects()[0]
    
    output_dir = os.path.join(os.path.dirname(__file__), "gui_delivery", "screenshots")
    os.makedirs(output_dir, exist_ok=True)

    # 等待 QML 渲染完成
    from PySide6.QtCore import QTimer
    QTimer.singleShot(500, lambda: _do_screenshots(root, output_dir))
    QTimer.singleShot(1200, app.quit)
    return app.exec()


def _do_screenshots(root, output_dir):
    for width, height, name in [
        (1440, 900, "1440_population_default.png"),
        (1280, 720, "1280_population_default.png"),
    ]:
        root.setWidth(width)
        root.setHeight(height)
        QGuiApplication.processEvents()
        screen = root.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("No screen available for GUI screenshot")
        pixmap = screen.grabWindow(int(root.winId()))
        if pixmap.isNull():
            raise RuntimeError(f"Screenshot is empty for {width}x{height}")
        path = os.path.join(output_dir, name)
        pixmap.save(path)
        print(f"Screenshot saved: {path}")


if __name__ == "__main__":
    sys.exit(take_screenshot())
