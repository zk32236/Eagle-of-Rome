# src/tests/test_gui/test_wpj_groupd_rebellion_announce.py
"""WP-J Group-D-Rebellion (J-AC-04b) — ForumStage 公告框内起义警示行（RENDER + 静态绑定）。

冻结设计 v1.1（`02-sa-design/GroupD/` §5.4/§6.1 L-D4）：
- 内容并入既有公告框 `announceArea`（框内追加行，非新容器）。
- 逐字渲染 `sessionStore.forumRebellionEvents`：`⚠️ 起义爆发：<province_name>（<name>）`。
- 空态三条件 additive 纳入 rebellion；无起义 → 不追加行。
No-Test-Assisted-Transition：目标态经真实生产动作 `forum_api.open_market`（→ `initialize_forum_turn`）到达。
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
import shiboken6  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import session_api, forum_api  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
FORUM_QML = os.path.join(QML_DIR, "stages", "ForumStage.qml")
REBELLION_MARK = "起义爆发"
EMPTY_STATE_TEXT = "本回合无战争威胁"
_ENGINES = []


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _qitem(obj):
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _all_items(root):
    pending = [_qitem(root)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


def _find_obj(root, object_name):
    for item in _all_items(root):
        if item.objectName() == object_name:
            return item
    return None


def _find_text(root, text):
    for item in _all_items(root):
        if item.property("text") == text:
            return item
    return None


def _texts_under(item):
    return [it.property("text") for it in _all_items(item)
            if "Text" in it.metaObject().className() and it.property("text")]


def _load_forum(store, width=1440, height=900):
    app = _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("theme", theme)
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(FORUM_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "ForumStage loaded with no root object"
    root = roots[0]
    root.setWidth(width)
    root.setHeight(height)
    app.processEvents()
    _ENGINES.append(engine)
    return engine, root


def _session_store_with_rebellion(trigger=True):
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    if trigger:
        province = state.get_province(1)
        province.set_event_flag("rebellion_active", False)
        province.set_grievance(3)
    assert forum_api.open_market(state, viewer)["success"]   # 真实生产动作（→ initialize_forum_turn）
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("forum")
    return store, state, viewer


# ---------------------------------------------------------------------------
# 静态绑定断言（源码级）
# ---------------------------------------------------------------------------

def test_source_consumes_authoritative_rebellion_and_adds_empty_condition():
    src = open(FORUM_QML, encoding="utf-8").read()
    assert "sessionStore.forumRebellionEvents" in src, "公告框须消费权威 forumRebellionEvents（FC-D08）"
    assert REBELLION_MARK in src, "缺起义警示行文案"
    assert "announceRebellionEvents" not in src, "不得新建独立容器 announceRebellionEvents（S-2 Δ-4）"
    # 空态条件纳入 rebellion
    assert "root.rebellionEventCount() === 0" in src, "空态三条件须 additive 纳入 rebellion（L-D4）"


# ---------------------------------------------------------------------------
# 渲染层：有/无起义
# ---------------------------------------------------------------------------

def test_rebellion_row_renders_and_empty_state_hidden():
    store, _state, _viewer = _session_store_with_rebellion(trigger=True)
    rows = store.forumRebellionEvents
    assert rows, "store 必须透传权威 forumRebellionEvents（FC-D09）"
    assert rows[0]["province_name"] == "西西里"
    _engine, root = _load_forum(store)
    box = _find_obj(root, "announceArea")
    assert box is not None, "未找到公告框 announceArea"
    texts = _texts_under(box)
    assert any((REBELLION_MARK in t and "西西里" in t) for t in texts), f"缺起义警示行：{texts}"
    empty_item = _find_text(root, EMPTY_STATE_TEXT)
    assert empty_item is None or not empty_item.isVisible(), "有起义时空态不得显示（L-D4）"


def test_no_rebellion_no_row_and_empty_state_shown():
    store, _state, _viewer = _session_store_with_rebellion(trigger=False)
    assert store.forumRebellionEvents == []
    _engine, root = _load_forum(store)
    box = _find_obj(root, "announceArea")
    assert box is not None
    texts = _texts_under(box)
    assert not any(REBELLION_MARK in t for t in texts), f"无起义不得追加行（FC-D07）：{texts}"
    # 空态可见性由权威标志决定（战争威胁/事件/起义均空且无活跃战争）
    expect_empty = (len(store.forumWarThreats) == 0 and len(store.forumWarEvents) == 0
                    and len(store.forumRebellionEvents) == 0 and not store.forumHasActiveWar)
    empty_item = _find_text(root, EMPTY_STATE_TEXT)
    assert empty_item is not None, "空态文案元素必须存在（由标志门控）"
    assert empty_item.isVisible() == expect_empty, "空态可见性与权威标志一致（L-D4）"
