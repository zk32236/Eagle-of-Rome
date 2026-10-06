# src/tests/test_gui/test_wpj_groupa_forum_action_layout.py
"""WP-J Group-A-3 / J-AC-11 — Forum 子环节操作按钮滚动可及性（布局断言）。

FC-13 / UI-P09(c)：阶段内子环节的提交/完成操作按钮必须固定于滚动区之外
（按钮 `parent` 链不含任何 `ScrollView`）。

- 「⚖ 提交下注」：修复前位于 `marketScroll`（ScrollView）之内 → RED。
- 「↪ 完成解雇」：已在 `retireListScroll` 之外（一并冻结）。
- 多视口：1280×720 与 1440×900 均须可及。

TDD_REQUIRED = NO（纯布局）+ 可选布局断言（本文件）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import shiboken6  # noqa: E402
from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
FORUM_QML = os.path.join(QML_DIR, "stages", "ForumStage.qml")


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


def _find_text(root, text):
    for item in _all_items(root):
        if item.property("text") == text:
            return item
    return None


def _ancestor_class_names(item):
    names = []
    cur = item
    while cur is not None:
        try:
            names.append(cur.metaObject().className())
        except Exception:
            pass
        cur = cur.parentItem()
    return names


class _ForumStore(QObject):
    """最小 mock：ForumStage 消费面（真实 DTO 形状，market 子环节、未 resolved）。"""

    forumViewChanged = Signal()

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return [{"id": 1, "name": "图斯库卢姆", "faction_id": "f1", "class_label": "骑士",
                 "influence": 10, "can_retire": True}]

    @Property(list, notify=forumViewChanged)
    def forumViewerLandRequests(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumLandAllocation(self):
        return []

    @Property(dict, notify=forumViewChanged)
    def forumResult(self):
        return {}

    @Property(dict, notify=forumViewChanged)
    def forumView(self):
        return {}

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self):
        return False

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self):
        return "market"

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        rows = []
        for i in range(12):  # 长内容触发滚动
            rows.append({"id": 100 + i, "name": f"人才{i}", "martial": 5, "intellect": 5,
                         "charisma": 5, "zeal": 5, "class_label": "骑士", "cost": 4,
                         "is_hero": False})
        return rows

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarEvents(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumViewerContractBids(self):
        return []

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandSaleTotal(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandPricePerUnit(self):
        return 10

    @Property(bool, notify=forumViewChanged)
    def forumHasActiveWar(self):
        return False

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self):
        return True

    @Slot("QVariant", "QVariant", result=dict)
    def doBuyLand(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", "QVariant", result=dict)
    def doPlaceBid(self, figure_id, contract_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doRecruitFigure(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", result=dict)
    def doRetireFigure(self, figure_id):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doCompleteForumStep(self):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doVoteTriumph(self, war_id, approved):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doResolveForum(self):
        return {"success": False, "message": "mock"}


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
    return engine, root


def _assert_action_button_out_of_scroll(root, label):
    item = _find_text(root, label)
    assert item is not None, f"未找到子环节操作按钮文案 {label!r}"
    names = _ancestor_class_names(item)
    offenders = [n for n in names if "ScrollView" in n or "Flickable" in n]
    assert not offenders, (
        f"FC-13 违规：{label!r} 位于滚动容器内（祖先链含 {offenders}）"
    )
    assert item.isVisible(), f"{label!r} 必须可见（固定于滚动区外）"


def test_market_submit_button_outside_scroll_1440():
    store = _ForumStore()
    _engine, root = _load_forum(store, 1440, 900)
    _assert_action_button_out_of_scroll(root, "⚖ 提交下注")


def test_retire_complete_button_outside_scroll():
    store = _ForumStore()
    _engine, root = _load_forum(store, 1440, 900)
    _assert_action_button_out_of_scroll(root, "✓ 已完成解雇")


def test_market_submit_button_outside_scroll_1280x720():
    store = _ForumStore()
    _engine, root = _load_forum(store, 1280, 720)
    _assert_action_button_out_of_scroll(root, "⚖ 提交下注")
