"""
Try QML offscreen rendering for Revenue Stage screenshot.
Sets QT_QPA_PLATFORM=offscreen, loads a minimal QML with RevenueStage,
and captures the rendered output.

NOTE: Evidence-only test — uses Qt event loop (app.exec()).
Excluded from full regression.
"""
import os
import sys
import json

import pytest

pytestmark = pytest.mark.skip(reason="Evidence-only, excluded from full regression")

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SCREENSHOTS_DIR = "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260729-01_GUI-Alignment/WP-01/03-da-evidence/screenshots"


def test_qml_render_check():
    """
    Test if QML offscreen rendering is available.
    Creates a minimal Window and attempts to grab a screenshot.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtCore import QUrl, QCoreApplication, QTimer
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQuick import QQuickWindow
    except ImportError as e:
        print(f"PySide6 import error: {e}")
        print("QML offscreen rendering not available for screenshots.")
        return

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv)

    engine = QQmlApplicationEngine()
    qml_dir = os.path.normpath(os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml"))
    engine.addImportPath(qml_dir)

    # Create a minimal test QML
    test_qml_content = '''
import QtQuick 2.15
import QtQuick.Window 2.15

Window {
    visible: false
    width: 400
    height: 100
    title: "QML Render Test"
    color: "#FFF9EC"

    Text {
        anchors.centerIn: parent
        text: "QML Offscreen Render Test"
        font.pixelSize: 14
        color: "#2E251B"
    }
}
'''

    test_qml_path = os.path.join(os.path.dirname(__file__), "_qml_render_test.qml")
    with open(test_qml_path, "w", encoding="utf-8") as f:
        f.write(test_qml_content)

    engine.load(QUrl.fromLocalFile(test_qml_path))
    root_objects = engine.rootObjects()

    if not root_objects:
        print("QML engine loaded no root objects")
        if os.path.exists(test_qml_path):
            os.unlink(test_qml_path)
        return

    window = root_objects[0]
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    out = os.path.join(SCREENSHOTS_DIR, "_qml_render_test_check.png")

    # Use QTimer to let the event loop process rendering
    captured = []

    def capture():
        image = window.grabWindow()
        image.save(out)
        print(f"Test screenshot saved to: {out}")
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.quit()
        captured.append(True)

    QTimer.singleShot(1000, capture)
    app.exec()

    if os.path.exists(test_qml_path):
        os.unlink(test_qml_path)

    if captured:
        print(f"QML offscreen rendering WORKS. File: {out}")
        print(f"Size: {os.path.getsize(out)} bytes")
    else:
        print("QML offscreen rendering FAILED to produce screenshot")
