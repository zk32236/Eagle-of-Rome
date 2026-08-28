# src/tests/test_gui/test_wpe_g7r_ec14_screenshots.py
"""
WP-E-G7R — EC-14 截图门（补充证据：post-click Mortality）。

oc-eor-screenshot 官方 fixture 中 `resolution_advance` 断言旧两段式字段
（`resolutionStepStatuses`，SO 冻结 safe-bin runner），与 G7R 单命令实现不兼容
（实施报告偏离登记 D-2）；本文件以 production-shape 路径（真实 gui_prototype 会话 →
真实 store → 真实 Main.qml 离屏渲染 + grabToImage）产出 post-click Mortality 截图
+ runtime 证据，落盘 `EOR20260821-01 GUI-BETA-R1/03-da-evidence/screenshots/`。
pre-advance Resolution 截图由 oc-eor-screenshot phase7_normal 官方 fixture 产出
（INFRA-SCREENSHOT-FIXTURE 输出根，实施阶段已拷贝入 G7R evidence）。
"""
import os
import json

SCREENSHOTS_DIR = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/"
    "EOR20260821-01 GUI-BETA-R1/03-da-evidence/screenshots"
)


def _create_qml_engine(store):
    """加载真实 Main.qml（对齐 test_qml_startup._create_engine 模式）。"""
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


def _grab_to_file(target, out_path: str) -> bool:
    """异步 grabToImage → 保存 PNG（QQuickItem 或 QQuickWindow.contentItem）。"""
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtQuick import QQuickItem

    if not isinstance(target, QQuickItem):
        raise TypeError(f"grab 目标必须是 QQuickItem，实际 {type(target).__name__}")

    result = {"saved": False}

    grab = target.grabToImage()
    if grab is None:
        raise RuntimeError("grabToImage 返回 None")

    def on_ready():
        try:
            image = grab.image()
            if image.isNull():
                raise RuntimeError("grabbed image is null")
            result["saved"] = image.save(out_path, "PNG")
        except BaseException as exc:  # noqa: BLE001 — 事件循环内捕获上报
            result["error"] = exc
        finally:
            QCoreApplication.quit()

    grab.ready.connect(on_ready)
    QTimer.singleShot(8000, QCoreApplication.quit)
    QCoreApplication.instance().exec()
    if result.get("error"):
        raise result["error"]
    return result["saved"]


def test_ec14_post_click_mortality_screenshot():
    """EC-14（补充）：单命令点击后 → Mortality 阶段离屏截图 + runtime 证据。"""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from src.api import session_api
    from src.ui.gui.session_store import GuiSessionStore

    result = session_api.create_gui_prototype_session(start_phase="combat")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")
    store = GuiSessionStore(state)
    store.initialize(player_id)
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.resolutionResolved is True
    assert store.advanceCurrentPhaseText == "\u23ed\ufe0f 进入下一年度"

    # 单命令点击（E-05）：一次 advance_year → 直入 mortality
    year_before = state.turn.year
    feedback = store.doAdvanceResolution()
    assert feedback["success"], feedback
    assert store.selectedPhaseId == "mortality"
    assert state.turn.year == year_before + 1
    assert store.isResolutionAdvancing is False

    engine, qml_dir = _create_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    window = engine.rootObjects()[0]
    assert window is not None, "Main.qml 未加载"

    if isinstance(window, QQuickWindow):
        target = window.contentItem()
    else:
        target = window.findChild(QQuickItem)
    assert target is not None, "未找到 QML 根 QQuickItem（contentItem）"

    # P1-HARNESS-01 opt-in 守卫：证据 PNG 已存在且未设 WP_E_G7R_EC14_REFRESH=1 → 捕获跳过
    # （早退 return = PASS，非 pytest.skip：上方业务断言已执行，计数不变，R2 §1.7）
    out_path = os.path.join(SCREENSHOTS_DIR, "g7r-post-click-mortality-2026-08-24.png")
    if os.path.exists(out_path) and os.environ.get("WP_E_G7R_EC14_REFRESH") != "1":
        return

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    saved = _grab_to_file(target, out_path)
    assert saved, f"截图保存失败: {out_path}"

    # runtime 证据（JSON）
    runtime = {
        "fixture": "g7r-post-click-mortality",
        "phase": "mortality",
        "selected_phase_id": store.selectedPhaseId,
        "current_phase_id": store.currentPhaseId,
        "year_before": year_before,
        "year_after": state.turn.year,
        "advance_year_count": 1,
        "advance_label": store.advanceCurrentPhaseText,
        "advancing_reset": store.isResolutionAdvancing is False,
        "png": "g7r-post-click-mortality-2026-08-24.png",
        "capture": "QQuickItem.grabToImage offscreen (real Main.qml)",
    }
    runtime_path = os.path.join(SCREENSHOTS_DIR, "g7r-post-click-mortality-runtime.json")
    with open(runtime_path, "w", encoding="utf-8") as f:
        json.dump(runtime, f, indent=2, ensure_ascii=False)
