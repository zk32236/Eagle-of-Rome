# src/tests/test_gui/test_wp05_governor_ia.py
"""WP-05V G6 Narrow — Governor 信息架构（FC-14 / AC-22~24）QML 层测试。

采用 QGuiApplication offscreen + QQmlComponent 加载 SenateStage.qml，
注入 mock sessionStore 上下文属性，验证：
- AC-22：无 vacancy 场景零 Governor UI（无独立 GovernorAppointmentPanel 实例，
  无「暂无行省信息」占位文本）。
- AC-23：有 vacancy 场景 governor 作为统一提案列表条目，checkbox 默认不勾选
  （FUNC-05 只读候选人展示逻辑由后端 DTO 断言 test_governor_appointments_candidate_has_4_attrs
  + 四态截图 RENDER_AUTOMATED 覆盖，见 §7 证据分类）；只读的 QML 层直接覆盖由
  test_ac23_vacancy_governor_entry_readonly_qml_source（SenateStage.qml 源码结构断言：
  governor 只读展示区仅 Text、无 ComboBox/TextField/TextInput/Slider/SpinBox）。
- AC-24：governor checkbox 勾选/取消 → 提交选择集合的增删（统一提交/表决路径）。
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

from PySide6.QtCore import (
    QObject, Signal, Property, Slot, QUrl, QMetaObject, Q_ARG, Qt,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent


def _options(*types):
    result = []
    for t in types:
        result.append({"key": f"{t}:k", "type": t, "title": t, "detail": ""})
    return result


GOVERNOR_OPTION = {
    "key": "governor:10",
    "type": "governor",
    "title": "总督任命 — 西西里",
    "detail": "候选人：Sextus",
    "params": {"province_id": 10, "candidate_id": 1},
}

GOVERNOR_APPOINTMENTS = {
    "pending_provinces": [{
        "province_id": 10,
        "name": "西西里",
        "candidates": [{
            "id": 1,
            "name": "Sextus",
            "faction_id": "optimates",
            "faction_name": "Optimates",
            "influence": 33,
            "class_tier": "NOBILE",
            "martial": 3,
            "intelligence": 8,
            "charisma": 5,
        }],
    }],
    "completed_provinces": [],
    "can_submit": False,
    "submitted": False,
}


class _MockSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, options, appointments=None, current_step="proposal"):
        super().__init__()
        self._options = options
        self._appointments = appointments or {}
        self._current_step = current_step
        self._submitted = []

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
        return self._appointments

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
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


def _all_texts(root):
    """收集 QML 树中所有 QQuickText 的 text 属性值（含 RichText 源码）。"""
    texts = []
    for obj in root.findChildren(QObject):
        v = obj.property("text")
        if isinstance(v, str) and v:
            texts.append(v)
    return texts


def _gov_panel_count(root):
    return sum(
        1 for c in root.findChildren(QObject)
        if c.metaObject().className().startswith("GovernorAppointmentPanel")
    )


_INPUT_CONTROL_MARKERS = ("ComboBox", "TextField", "TextInput", "Slider", "SpinBox")


def test_ac22_no_vacancy_zero_governor_ui():
    store = _MockSenateStore(_options("war", "peace", "budget"), appointments={})
    engine, root = _load_senate_stage(store)

    # 默认勾选 {war,peace,budget}，无 governor 条目
    assert _key_set(root) == {"war:k", "peace:k", "budget:k"}

    # 无独立 GovernorAppointmentPanel 实例（FC-14 ⑤）
    assert _gov_panel_count(root) == 0, "standalone GovernorAppointmentPanel must be removed"

    # 无「暂无行省信息」占位残留（FC-14 ⑤ + AC-22）
    assert not any("暂无行省信息" in t for t in _all_texts(root)), \
        "no-vacancy state must not render '暂无行省信息' placeholder"


def test_ac23_vacancy_governor_entry_default_unchecked():
    store = _MockSenateStore(
        _options("war", "peace", "budget") + [GOVERNOR_OPTION],
        appointments=GOVERNOR_APPOINTMENTS,
    )
    engine, root = _load_senate_stage(store)

    # governor 默认不勾选（仅 {war,peace,budget}）
    assert _key_set(root) == {"war:k", "peace:k", "budget:k"}

    # 无独立 GovernorAppointmentPanel 实例（governor 统一提案列表内渲染）
    assert _gov_panel_count(root) == 0


def test_ac24_governor_checkbox_selection_flow():
    store = _MockSenateStore(
        _options("war", "peace", "budget") + [GOVERNOR_OPTION],
        appointments=GOVERNOR_APPOINTMENTS,
    )
    engine, root = _load_senate_stage(store)

    # 默认未勾选 → 不提交
    assert "governor:10" not in _key_set(root)

    # 勾选 → 进入提交选择集合
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "governor:10"), Q_ARG("QVariant", True))
    assert "governor:10" in _key_set(root)

    # 取消勾选 → 退出提交选择集合
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "governor:10"), Q_ARG("QVariant", False))
    assert "governor:10" not in _key_set(root)


def test_ac23_vacancy_governor_entry_readonly_qml_source():
    """AC-23 只读（QML 层源码断言）：governor 展开区为纯 Text 展示，无输入/编辑控件。

    FUNC-05 只读候选人展示——直接解析 SenateStage.qml，定位 governor 只读展示区
    （visible 绑定为 ``modelData.type === "governor"`` 的 ColumnLayout），断言其仅含
    Text 组件，不含 ComboBox/TextField/TextInput/Slider/SpinBox 等可编辑输入控件
    （对比 war 条目含 ComboBox、budget/land 条目含 Slider 的可编辑控件）。

    说明：offscreen 环境下 Repeater delegate 因 sessionStore 上下文传播问题无法
    渲染展开区子控件（既存 mock 测试仅校验根对象状态，不校验 delegate 渲染文本），
    故以 QML 源码结构断言作为 AC-23「只读」的直接自动化覆盖。
    """
    qml_path = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
    with open(qml_path, encoding="utf-8") as f:
        source = f.read()

    marker = 'visible: modelData.type === "governor"'
    idx = source.index(marker)
    assert idx != -1, "governor readonly block marker not found in SenateStage.qml"

    block_start = source.rfind("ColumnLayout {", 0, idx)
    assert block_start != -1, "governor ColumnLayout start not found"

    # 花括号配平提取 governor 只读展示区完整块
    depth = 0
    block_end = None
    i = block_start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                block_end = i + 1
                break
        i += 1
    assert block_end is not None, "governor ColumnLayout block unbalanced"

    block = source[block_start:block_end]

    # 只读断言 1：governor 只读展示区内无任何输入/编辑控件
    for control in _INPUT_CONTROL_MARKERS:
        assert control not in block, f"governor readonly area must not contain {control}"

    # 只读断言 2：候选人只读信息以 Text 组件呈现
    assert "Text {" in block, "governor readonly area must render Text components"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
