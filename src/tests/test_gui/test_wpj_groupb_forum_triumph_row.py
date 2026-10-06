# src/tests/test_gui/test_wpj_groupb_forum_triumph_row.py
"""WP-J Group B-1 (J-AC-03) — ForumStage 凯旋行三态（赞成/已投/不可投）QML 消费。

RENDER + 静态绑定断言（FC-B04/B06/B18）：
- 行 delegate 逐字消费 producer `modelData.action.state` + `modelData.viewer_vote`
- 可用性**不再**由 `marketUnlocked`/`canExecuteForum`/`forumResolved` 重算（J-D02/FC-B06）
- 三态渲染：actionable+未投 → enabled「赞成」；viewer_vote!=null → disabled「已投」；
  readonly → disabled 统一「不可投」
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


def _button_mousearea(text_item):
    """actionText Text 的父 = 按钮 Rectangle；其子 MouseArea == 可点击面。"""
    btn = text_item.parentItem()
    for child in btn.childItems():
        if "MouseArea" in child.metaObject().className():
            return child
    return None


class _TriumphForumStore(QObject):
    """最小 mock：ForumStage 凯旋消费面（真实 additive DTO 形状）。"""

    forumViewChanged = Signal()

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return [
            {"war_id": "w1", "name": "战争一", "commander_name": "甲",
             "commander_faction_id": "f1", "soldier_share": 5,
             "action": {"state": "actionable", "reason": "ok"}, "viewer_vote": None},
            {"war_id": "w2", "name": "战争二", "commander_name": "乙",
             "commander_faction_id": "f1", "soldier_share": 3,
             "action": {"state": "actionable", "reason": "ok"}, "viewer_vote": True},
            {"war_id": "w3", "name": "战争三", "commander_name": "丙",
             "commander_faction_id": "f1", "soldier_share": 2,
             "action": {"state": "readonly", "reason": "vote_window_closed"}, "viewer_vote": None},
        ]

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumViewerLandRequests(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumLandAllocation(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
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


# ---------------------------------------------------------------------------
# 静态绑定断言（源码级：逐字消费 producer；禁 QML 重建）
# ---------------------------------------------------------------------------

def test_source_binds_authoritative_action_projection():
    src = open(FORUM_QML, encoding="utf-8").read()
    assert "modelData.action.state === \"actionable\"" in src, \
        "凯旋行必须消费 producer action.state（FC-B01/B03）"
    assert "modelData.viewer_vote" in src, "凯旋行必须消费 producer viewer_vote（FC-B18）"
    assert "enabledAction: rowActionable && !rowVoted" in src, \
        "enabledAction 必须由 action+viewer_vote 派生（FC-B04）"


def test_source_triumph_delegate_no_market_unlocked_rebuild():
    """凯旋行 delegate 不得再以 marketUnlocked/canExecuteForum/forumResolved 重算可用性。"""
    src = open(FORUM_QML, encoding="utf-8").read()
    anchor = src.index("model: sessionStore.forumTriumphWars")
    start = src.index("delegate: MarketActionRow {", anchor)
    end = src.index("MarketActionRow {", start + len("delegate: MarketActionRow {"))
    block = src[start:end]
    code = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("//"))
    assert "root.marketUnlocked" not in code, "凯旋行不得重建 marketUnlocked（FC-B06）"
    assert "sessionStore.canExecuteForum" not in code, "凯旋行不得重建 canExecuteForum（FC-B06）"
    assert "sessionStore.forumResolved" not in code, "凯旋行不得重建 forumResolved（FC-B06）"
    assert "doVoteTriumph(modelData.war_id, true)" in code, "onTriggered 复用既有写槽"


# ---------------------------------------------------------------------------
# 三态渲染（离线帧）
# ---------------------------------------------------------------------------

def test_three_states_render_text_and_enabled():
    store = _TriumphForumStore()
    _engine, root = _load_forum(store)

    approve = _find_text(root, "赞成")
    voted = _find_text(root, "已投")
    blocked = _find_text(root, "不可投")
    assert approve is not None, "actionable+未投 应渲染「赞成」"
    assert voted is not None, "viewer_vote!=null 应渲染「已投」"
    assert blocked is not None, "readonly 应渲染「不可投」"

    assert _button_mousearea(approve).property("enabled") is True, "「赞成」应 enabled（可点）"
    assert _button_mousearea(voted).property("enabled") is False, "「已投」应 disabled"
    assert _button_mousearea(blocked).property("enabled") is False, "「不可投」应 disabled"


def test_no_dead_actionable_appearance_for_readonly():
    """readonly 行不得出现 enabled 外观（死控件）。"""
    store = _TriumphForumStore()
    _engine, root = _load_forum(store)
    blocked = _find_text(root, "不可投")
    assert _button_mousearea(blocked).property("enabled") is False


def test_no_reason_text_rendered():
    """reason 词表值不得作为界面文案呈现（FC-B02/B04）。"""
    store = _TriumphForumStore()
    _engine, root = _load_forum(store)
    for reason in ("vote_window_closed", "not_current_player", "not_phase", "resolved", "ok"):
        assert _find_text(root, reason) is None, f"reason {reason!r} 不得呈现"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
