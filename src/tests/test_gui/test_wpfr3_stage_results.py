# src/tests/test_gui/test_wpfr3_stage_results.py
"""WP-F-R3 T-R3-05~07：QML Stage 3 结果态展示（vetoed/failed 分离 + 否决计数 + 混合过滤）。

复用 test_wpfr1_stage_screens.py 的 store/stage stub 模式：
- T-R3-05  Stage 3 结果留存：结果态 Stage 3 含 passed 提案（不再空白），mark=✓
- T-R3-06  否决计数分离：vetoedResultRows 只计 vetoed；rejectedResultRows 计 failed
- T-R3-07  混合场景 Stage 3 过滤：passed+vetoed 呈现，failed 排除；resultMark(vetoed)=✗
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

import shiboken6
import pytest
from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression, QQmlEngine
from PySide6.QtQuick import QQuickItem

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")


def _read_qml(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


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


def _texts(root):
    return [str(i.property("text")) for i in _all_items(root) if isinstance(i.property("text"), str)]


def _to_py(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value


def _call_qml(root, expression):
    ctx = QQmlEngine.contextForObject(root)
    if ctx is None:
        return False, None
    expr = QQmlExpression(ctx, root, expression)
    val = expr.evaluate()
    if expr.hasError():
        return False, None
    if isinstance(val, tuple) and len(val) == 2:
        val = val[0]
    return True, _to_py(val)


def _invoke_list(root, method_name):
    ok, val = _call_qml(root, f"{method_name}()")
    if not ok or val is None:
        return False, []
    return True, list(val)


def _row_id(o):
    d = _to_py(o)
    if isinstance(d, dict):
        return int(d.get("id"))
    if hasattr(o, "property"):
        return int(_to_py(o.property("id")))
    raise AssertionError(f"unexpected row element: {type(o)} {o!r}")


def _row_ids(rows):
    return [_row_id(o) for o in rows]


def _load_qml(qml_file, store):
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(qml_file))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_file} loaded with no root object"
    return engine, roots[0]


class _ResultsSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, submitted=None, parent=None):
        super().__init__(parent)
        self._submitted = submitted or []

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return "results"

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return self._submitted

    @Property(list, notify=senateViewChanged)
    def senateVetoCandidateIds(self):
        return []

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateVoteResults(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateTakeoverOptions(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self):
        return []

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canTakeoverSenateWar(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self):
        return False

    @Property(str, notify=senateViewChanged)
    def senatePresidingOfficer(self):
        return ""

    @Property(list, notify=senateViewChanged)
    def governorAppointments(self):
        return []

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doSubmitSenateVotes(self):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, ids):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", result=dict)
    def doTakeoverWar(self, war_id):
        return {"success": False, "message": "mock"}


def test_tr3_05_stage3_results_retained():
    """T-R3-05（缺陷 A）：结果态 Stage 3 数据源 = passed+vetoed（不再空白），行 mark=✓。"""
    src = _read_qml(SENATE_QML)
    assert "model: root.stageThreeRows()" in src, "Stage 3 Repeater 必须切换到 stageThreeRows()"

    store = _ResultsSenateStore(submitted=[
        {"id": 1, "result": "passed", "title": "宣战", "detail": ""},
        {"id": 2, "result": "passed", "title": "建造", "detail": ""},
    ])
    _engine, root = _load_qml(SENATE_QML, store)

    ok, rows = _invoke_list(root, "vetoResultRows")
    assert ok, "vetoResultRows must be invokable"
    assert len(rows) == 2, "结果态 Stage 3 必须保留 passed 提案（不再空白）"
    assert set(_row_ids(rows)) == {1, 2}

    ok2, s3 = _invoke_list(root, "stageThreeRows")
    assert ok2 and len(s3) == 2, "results 态 stageThreeRows == vetoResultRows"

    ok_m, mark = _call_qml(root, 'resultMark({"result": "passed"})')
    assert ok_m and mark == "\u2713"

    joined = " ".join(_texts(root))
    assert "宣战" in joined and "建造" in joined


def test_tr3_06_veto_count_separation():
    """T-R3-06（缺陷 B）：vetoedResultRows 只计 vetoed；rejectedResultRows 计 failed。"""
    store = _ResultsSenateStore(submitted=[
        {"id": 1, "result": "passed", "title": "宣战", "detail": ""},
        {"id": 2, "result": "vetoed", "title": "建造", "detail": ""},
        {"id": 3, "result": "rejected", "title": "卖地", "detail": ""},
    ])
    _engine, root = _load_qml(SENATE_QML, store)

    ok_v, vetoed = _invoke_list(root, "vetoedResultRows")
    assert ok_v and len(vetoed) == 1, "「保民官否决」只计 vetoed（建造）"
    assert _row_ids(vetoed) == [2]

    ok_r, rejected = _invoke_list(root, "rejectedResultRows")
    assert ok_r and len(rejected) == 1, "「未通过」计 failed（卖地）"
    assert _row_ids(rejected) == [3]
    # vetoed 不含卖地（缺陷 B 回归）
    assert 3 not in _row_ids(vetoed)

    joined = " ".join(_texts(root))
    assert "保民官否决 1 项" in joined
    assert "未通过 1 项" in joined


def test_tr3_07_mixed_stage3_filter():
    """T-R3-07：混合场景 Stage 3 过滤 = passed+vetoed（failed 排除）；resultMark(vetoed)=✗。"""
    store = _ResultsSenateStore(submitted=[
        {"id": 1, "result": "passed", "title": "宣战", "detail": ""},
        {"id": 2, "result": "vetoed", "title": "建造", "detail": ""},
        {"id": 3, "result": "rejected", "title": "卖地", "detail": ""},
    ])
    _engine, root = _load_qml(SENATE_QML, store)

    ok, rows = _invoke_list(root, "vetoResultRows")
    assert ok
    assert _row_ids(rows) == [1, 2], "Stage 3 结果态 = passed+vetoed，failed（卖地）排除"

    ok_m, mark = _call_qml(root, 'resultMark({"result": "vetoed"})')
    assert ok_m and mark == "\u2717"
    ok_c, color = _call_qml(root, 'resultMarkColor({"result": "vetoed"})')
    assert ok_c and color == "#B3261E"

    ok_p, mark_p = _call_qml(root, 'resultMark({"result": "passed"})')
    assert ok_p and mark_p == "\u2713"
