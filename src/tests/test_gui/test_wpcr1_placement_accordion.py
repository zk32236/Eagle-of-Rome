# src/tests/test_gui/test_wpcr1_placement_accordion.py
"""WP-C-R1 AU-14 NT-6: QML 对象树结构断言（016 placement + 014/015 控件值域 + accordion 时序）。

采用 QGuiApplication offscreen + QQmlComponent 加载 ForumStage.qml / SenateStage.qml，
注入 mock sessionStore，读取 QML 对象树断言（视觉子项遍历 childItems() 可穿透 Repeater 项）：

- T016-1: 顶部公示容器 objectName == "announceArea"
- T016-2: war-threat 渲染位于 announceArea（非 Market）
- T016-3: Market 无「⚔️ 战争威胁」SectionTitle（已移除）
- T016-5: 无 THREAT → 顶部 neutral 空态（不声称战争）
- T016-6: 顶部不残留硬编码「第一次布匿战争进行中」战争状态
- T016-10: 「西西里包税合同待竞标」静态文案保留（归 010/WP-F，R1 不越界）
- T015-3/13: ComboBox model == legion_options（[1..可用池]），default 选中 4
- T015-11: 无个体军团 ID 选择器（仅数量控件）
- T014-3: Slider from/to/stepSize/value == budget_range
- T-ACC-1/2/3 + T014-10: accordion 展开状态与选中集一致、控件可见、onSenateViewChanged 不丢展开
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

from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot, QMetaObject, Q_ARG, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem
import shiboken6


def _qitem(obj):
    """将 QObject 包装重包装为 QQuickItem（childItems/parentItem 遍历 Repeater 项需要）。"""
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _load_qml(qml_file, store):
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    # SenateStage 引用 theme 上下文属性（ForumStage 不用，注入无害）
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "stages", qml_file)))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_file} loaded with no root object"
    engine._test_refs = (store, theme)
    return engine, roots[0]


def _normalize(value):
    """将 QML var 属性值归一化为 Python list。"""
    if value is None:
        return []
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _all_items(root):
    """深度优先遍历 QQuickItem 视觉子项（childItems 可穿透 Repeater 生成的项，findChildren(QObject) 不行）。"""
    pending = [_qitem(root)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


def _texts(root):
    return [str(i.property("text")) for i in _all_items(root) if isinstance(i.property("text"), str)]


def _is_descendant(child, ancestor):
    node = _qitem(child)
    anc = _qitem(ancestor)
    while node is not None:
        if node is anc:
            return True
        node = node.parentItem()
    return False


# ---------------------------------------------------------------------------
# ForumStage mock store
# ---------------------------------------------------------------------------

class _MockForumStore(QObject):
    forumViewChanged = Signal()

    def __init__(self, war_threats=None, parent=None):
        super().__init__(parent)
        self._war_threats = war_threats or []

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self):
        return "market"

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self):
        return False

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
        return []

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self):
        return 0

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self):
        return self._war_threats

    @Property(dict, notify=forumViewChanged)
    def forumResult(self):
        return {}

    @Property(dict, notify=forumViewChanged)
    def forumView(self):
        return {}

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self):
        return False

    @Property(bool, notify=forumViewChanged)
    def canAdvanceForum(self):
        return False

    @Slot("QVariant", result=dict)
    def doRecruitFigure(self, figure_id, amount):
        return {"success": False, "message": "no"}

    @Slot("QVariant", "QVariant", result=dict)
    def doPlaceBid(self, contract_id, amount):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doBuyLand(self, figure_id, amount):
        return {"success": False, "message": "no"}

    @Slot(result=dict)
    def doResolveForum(self):
        return {"success": False, "message": "no"}

    @Slot(result=dict)
    def doCompleteForumStep(self):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doRetireFigure(self, figure_id):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doVoteTriumph(self, war_id, approved):
        return {"success": False, "message": "no"}


_THREATS = [
    {"war_id": "pyrrhic_war", "name": "皮洛士战争", "threat_level": 2, "naval_required": False},
    {"war_id": "first_punic_war", "name": "第一次布匿战争", "threat_level": 3, "naval_required": True},
]


def test_forum_announce_area_object_name():
    """T016-1: 顶部公示容器 objectName == announceArea。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    area = root.findChild(QObject, "announceArea")
    assert area is not None, "announceArea not found"
    assert root.objectName() == "forumStage"


def test_forum_war_threat_rendered_in_announce_area():
    """T016-2: war-threat 渲染位于 announceArea 内（非 Market）；内容来自 DTO 不重算。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    area = root.findChild(QObject, "announceArea")
    assert area is not None
    block = root.findChild(QObject, "announceWarThreats")
    assert block is not None, "announceWarThreats block not found"
    # 块在 announceArea 子树内
    assert _is_descendant(block, area), "war-threat block must live inside announceArea"
    # 有威胁 → 块可见，空态不可见
    assert block.property("visible") is True
    empty = root.findChild(QObject, "announceWarThreatsEmpty")
    assert empty is not None
    assert empty.property("visible") is False
    # delegate Text 渲染 DTO 字段（name/threat_level/naval_required 直读，不重算）
    joined = " ".join(_texts(root))
    assert "皮洛士战争 · 威胁等级 2 · 陆战" in joined
    assert "第一次布匿战争 · 威胁等级 3 · 需海军" in joined


def test_forum_market_war_threat_section_removed():
    """T016-3: Market 无「⚔️ 战争威胁」SectionTitle（已移除）。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    texts = _texts(root)
    assert not any(t == "⚔️ 战争威胁" for t in texts)
    assert not any("战争威胁" in t and "⚔" in t for t in texts), "Market war-threat SectionTitle must be removed"


def test_forum_war_threat_empty_state():
    """T016-5: 无 THREAT → 顶部 neutral 空态（不声称战争存在）。"""
    store = _MockForumStore([])
    _engine, root = _load_qml("ForumStage.qml", store)
    block = root.findChild(QObject, "announceWarThreats")
    empty = root.findChild(QObject, "announceWarThreatsEmpty")
    assert block is not None and empty is not None
    assert block.property("visible") is False
    assert empty.property("visible") is True
    assert "本回合无战争威胁" in str(empty.property("text"))


def test_forum_no_stale_hardcoded_war_state():
    """T016-6 + T016-10: 顶部不残留「第一次布匿战争进行中」战争状态；「西西里包税合同待竞标」保留。"""
    store = _MockForumStore([])
    _engine, root = _load_qml("ForumStage.qml", store)
    joined = " ".join(_texts(root))
    assert "第一次布匿战争进行中" not in joined, "hard-coded war-state must not remain in top area"
    assert "西西里包税合同待竞标" in joined, "static contract copy belongs to 010/WP-F, must be retained"


# ---------------------------------------------------------------------------
# SenateStage mock store
# ---------------------------------------------------------------------------

class _MockSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, options, current_step="proposal", parent=None):
        super().__init__(parent)
        self._options = options
        self._current_step = current_step
        self._submitted = []
        self.submit_calls = 0

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self):
        return self._options

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return self._current_step

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return self._submitted

    @Property(list, notify=senateViewChanged)
    def senateTakeoverOptions(self):
        return []

    @Property(bool, notify=senateViewChanged)
    def canTakeoverSenateWar(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canAdvanceSenate(self):
        return False

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self):
        return []

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def governorAppointments(self):
        return {}

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        self.submit_calls += 1
        return {"success": True, "message": "ok"}

    @Slot(result=dict)
    def doSubmitSenateVotes(self):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids):
        return {"success": False, "message": "no"}

    @Slot(str, result=dict)
    def doTakeoverWar(self, war_id):
        return {"success": True, "message": "ok"}


def _options_with_ranges():
    return [
        {"key": "war:w1", "type": "war", "title": "宣战 — 皮洛士战争", "detail": "征召 4 个军团；威胁 2；…",
         "params": {"war_id": "w1", "legions": 4, "legion_options": [1, 2, 3, 4, 5]}},
        {"key": "peace:p1", "type": "peace", "title": "停战 — 皮洛士战争", "detail": "赔款 100 T",
         "params": {"war_id": "p1"}},
        {"key": "budget:b1", "type": "budget", "title": "建造合同 — 意大利工程", "detail": "预算金额 100 T",
         "params": {"contract_id": 1, "modified_budget": 100,
                    "budget_range": {"min": 1, "max": 150, "step": 1, "default": 100}}},
    ]


def _key_set(root):
    return {str(k) for k in _normalize(root.property("selectedProposalKeys"))}


def test_senate_accordion_expansion_and_controls():
    """T-ACC-1/2/3 + T014-10: 展开状态与选中集一致；war/budget 控件可见可用；onSenateViewChanged 不丢展开。"""
    store = _MockSenateStore(_options_with_ranges())
    _engine, root = _load_qml("SenateStage.qml", store)
    app = _get_app()

    # T-ACC-2: 展开状态 == 选中集（默认 war/peace/budget）
    keys = _key_set(root)
    assert keys == {"war:w1", "peace:p1", "budget:b1"}
    expanded = {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert expanded == keys

    # T-ACC-1/T014-10: 控件展开可见（delegate 中控件在全部 bill card 实例化，仅有权值域者 enabled）
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.property("enabled") is True]
    assert len(combos) == 1, f"expected exactly 1 enabled legion ComboBox, got {len(combos)} (T015-11)"
    combo = combos[0]
    assert combo.isVisible() is True
    assert str(combo.property("currentText")) == "4", "default legion selection must be 4 (T015-13)"
    # T015-3: ComboBox model == legion_options
    assert _normalize(combo.property("model")) == [1, 2, 3, 4, 5]

    sliders = [s for s in _all_items(root)
               if "Slider" in s.metaObject().className()
               and "Groove" not in s.metaObject().className()
               and "Handle" not in s.metaObject().className()
               and s.property("enabled") is True
               and s.isVisible()]
    assert len(sliders) == 1, f"expected exactly 1 enabled budget Slider, got {len(sliders)}"
    slider = sliders[0]
    # T014-3: Slider from/to/stepSize/value == budget_range（authoritative，非硬编码 20-200）
    assert slider.property("from") == 1
    assert slider.property("to") == 150
    assert slider.property("stepSize") == 1
    assert slider.property("value") == 100

    # T-ACC-3: onSenateViewChanged 触发后不丢展开状态（选中集非空 → 仅重跑 expandCheckedBills）
    store.senateViewChanged.emit()
    app.processEvents()
    expanded2 = {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert expanded2 == keys
    assert combo.isVisible() is True

    # 折叠 → 控件不可见；再展开 → 恢复（accordion 交互保持）
    QMetaObject.invokeMethod(root, "toggleBillExpanded", Qt.DirectConnection, Q_ARG("QVariant", "war:w1"))
    app.processEvents()
    assert "war:w1" not in {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert combo.isVisible() is False
    QMetaObject.invokeMethod(root, "toggleBillExpanded", Qt.DirectConnection, Q_ARG("QVariant", "war:w1"))
    app.processEvents()
    assert "war:w1" in {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert combo.isVisible() is True


def test_senate_no_individual_legion_selector():
    """T015-11: 无个体军团 ID 选择器（仅数量 ComboBox；QML 结构断言）。"""
    store = _MockSenateStore(_options_with_ranges())
    _engine, root = _load_qml("SenateStage.qml", store)
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.property("enabled") is True]
    assert len(combos) == 1, "only one enabled legion-count ComboBox is allowed"
    model = _normalize(combos[0].property("model"))
    assert model == [1, 2, 3, 4, 5], "model must be a count range [1..pool], not individual legion IDs"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
