# src/tests/test_gui/test_wp05_default_selection.py
"""WP-05 默认勾选无副作用（DEV-14）QML 层测试。

采用 QGuiApplication offscreen + QQmlComponent 加载 SenateStage.qml，
注入 mock sessionStore 上下文属性，读取根 selectedProposalKeys 断言。
覆盖：AC-07 / AC-08 / AC-09 / AC-10。
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

from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl, QMetaObject, Q_ARG, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent


def _options(*types):
    """按给定 type 序列构造 proposal options（key 由 type 派生）。"""
    result = []
    for t in types:
        result.append({"key": f"{t}:k", "type": t, "title": t, "detail": ""})
    return result


class _MockSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, options, current_step="proposal", can_takeover=False,
                 takeover_options=None, parent=None):
        super().__init__(parent)
        self._options = options
        self._current_step = current_step
        self._can_takeover = can_takeover
        self._takeover_options = takeover_options or []
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
        return self._takeover_options

    @Property(bool, notify=senateViewChanged)
    def canTakeoverSenateWar(self):
        return self._can_takeover

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canSelectSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self):
        return False

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
    def senatePublicAnnouncement(self):
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


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _load_senate_stage(store):
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    ctx = engine.rootContext()
    ctx.setContextProperty("theme", theme)
    ctx.setContextProperty("sessionStore", store)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "stages", "SenateStage.qml")))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "SenateStage.qml loaded with no root object"
    root = roots[0]
    engine._test_refs = (store, theme)
    return engine, root


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


def _key_set(root):
    return {str(k) for k in _normalize(root.property("selectedProposalKeys"))}


def test_wp05_default_selection():
    """R5（Plan §4.2 L9；SA §2.3(1)）：War Card 默认 unchecked；非 War 提案默认仅 budget。
    （旧「war/peace 默认勾选」已 supersede——war/peace 由统一 War Card 承担。）"""
    store = _MockSenateStore(_options("war", "peace", "budget", "governor", "land"))
    _engine, root = _load_senate_stage(store)

    # AC-07（R5）：非 War 提案默认勾选仅 budget；war/peace 不在 bill 选择集
    keys = _key_set(root)
    assert keys == {"budget:k"}

    # AC-08: 用户 toggle 后 selectedProposalKeys 即时变化
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:k"), Q_ARG("QVariant", True))
    keys = _key_set(root)
    assert keys == {"budget:k", "land:k"}

    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:k"), Q_ARG("QVariant", False))
    keys = _key_set(root)
    assert keys == {"budget:k"}


def test_wp05_default_no_side_effect():
    store = _MockSenateStore(_options("war", "peace", "budget", "governor", "land"))
    _engine, root = _load_senate_stage(store)

    # AC-09: 初始化 + 再次 syncDefaultSelection 均不触发后台提交（零写）
    QMetaObject.invokeMethod(root, "syncDefaultSelection", Qt.DirectConnection)
    assert store.submit_calls == 0


def test_wp05_default_reentry():
    # AC-10 未提交重建 → 重新应用默认集合（R5：非 War 提案默认仅 budget）
    store = _MockSenateStore(_options("war", "peace", "budget", "governor", "land"), current_step="proposal")
    _engine, root = _load_senate_stage(store)
    assert _key_set(root) == {"budget:k"}
    assert root.property("proposalStepDone") is False

    # AC-10 已提交（current_step != "proposal"）→ 显示 submitted_proposals
    store2 = _MockSenateStore(_options("war", "peace", "budget"), current_step="senate_vote")
    store2._submitted = [{"key": "war:k", "type": "war", "label": "宣战"}]
    _engine2, root2 = _load_senate_stage(store2)
    assert root2.property("proposalStepDone") is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
