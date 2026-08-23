# src/tests/test_gui/test_senate_r1_gui.py
"""GUI-BETA-R1 WP-D-R1（G7 Focused Correction）QML probe 测试（F-R1-02 + §13.1 targeted 2/4/9）。

- F-R1-02 / targeted 2：非执政官 viewer（canCreateSenateProposal=False）→ 参数控件/三角 disabled
  （AU-R1-03a）；=True → 既有 enabled 断言不回归（与 test_wpcr1_placement_accordion / 
  test_senate_amount_c_controls parity）
- targeted 4：checkbox 驱动展开/折叠（AU-R1-04a，G7 #8 复现——未选提案参数面板折叠）
- targeted 9：R1 触碰 DTO 字段 null-safe（AU-R1-06c）——engine warnings 捕获，断言无新增
  Unable to assign [undefined]（legion_options/budget_range/public_land/expandedBillKeys/门控表达式）

数据形状：真实 producer（senate_api.get_senate_view proposal_options）——非 QML-only mock
绕过真实 DTO 形状（Task Package §12 禁 mock-only 证据）。
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

from src.tests.test_gui.test_wpcr1_placement_accordion import (
    _build_real_senate_state,
    _real_senate_options,
)


def _qitem(obj):
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _all_items(root):
    pending = [_qitem(root)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


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


class FakeSenateStore(QObject):
    """FakeSessionStore：真实 DTO 形状 + 可配置 canCreateSenateProposal（AU-R1-03a 门控 probe）。"""

    senateViewChanged = Signal()

    def __init__(self, options, can_create=True, current_step="proposal", parent=None):
        super().__init__(parent)
        self._options = options
        self._can_create = can_create
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
        return self._can_create

    @Property(bool, notify=senateViewChanged)
    def canSelectSenateProposal(self):
        return self._can_create

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self):
        return not self._can_create

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


def _load_senate_stage(store, collect_warnings=False):
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    captured = []
    if collect_warnings:
        engine.warnings.connect(lambda errors: captured.extend(str(e.toString()) for e in errors))

    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "stages", "SenateStage.qml")))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "SenateStage.qml loaded with no root object"
    return engine, roots[0], captured


def _triangle_mouse_areas(root):
    """billCard 表头三角 MouseArea（width==18，AU-R1-03a 门控对象）。"""
    out = []
    for item in _all_items(root):
        if "MouseArea" not in item.metaObject().className():
            continue
        try:
            if int(item.property("width")) == 18:
                out.append(item)
        except (TypeError, ValueError):
            continue
    return out


def _legion_combos(root):
    return [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.isVisible()]


def _sliders(root):
    return [s for s in _all_items(root)
            if "Slider" in s.metaObject().className()
            and "Groove" not in s.metaObject().className()
            and "Handle" not in s.metaObject().className()]


# ---------------------------------------------------------------------------
# F-R1-02 / targeted 2 — unauthorised viewer authority gating（AU-R1-03a）
# ---------------------------------------------------------------------------

def test_unauthorised_viewer_controls_gated():
    """非执政官 viewer（canCreateSenateProposal=False）→ 三角/军团 ComboBox/预算 Slider/land Slider 全禁用。"""
    options = _real_senate_options()  # 真实 producer 形状（war + budget + land×2）
    store = FakeSenateStore(options, can_create=False)
    _engine, root, _warnings = _load_senate_stage(store)
    app = _get_app()

    # 默认选中 war/budget → 卡片展开 → 控件在树中
    triangles = _triangle_mouse_areas(root)
    assert len(triangles) >= 2, f"预期至少 2 个三角 MouseArea，got {len(triangles)}"
    for tri in triangles:
        assert tri.property("enabled") is False, "非执政官 viewer 三角必须禁用（参数面板不可展开）"

    combos = _legion_combos(root)
    assert len(combos) == 1
    assert combos[0].property("enabled") is False, "非执政官 viewer 军团 ComboBox 必须禁用"

    sliders = [s for s in _sliders(root) if s.isVisible()]
    assert len(sliders) == 1, f"预期 1 个可见 budget Slider，got {len(sliders)}"
    assert sliders[0].property("enabled") is False, "非执政官 viewer 预算 Slider 必须禁用"

    # land Slider 门控：即使经程序展开 land 面板，land Slider 仍禁用（AU-R1-03a 全覆盖）
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    land_sliders = [s for s in _sliders(root) if s.isVisible() and s.property("to") == 1000]
    assert len(land_sliders) == 1, "land:sale 选中后 land Slider 应可见（展开断言）"
    assert land_sliders[0].property("enabled") is False, "非执政官 viewer land Slider 必须禁用"


def test_consul_viewer_controls_enabled_no_regression():
    """执政官 viewer（canCreateSenateProposal=True）→ 既有 enabled 断言不回归（parity）。"""
    options = _real_senate_options()
    store = FakeSenateStore(options, can_create=True)
    _engine, root, _warnings = _load_senate_stage(store)
    app = _get_app()

    for tri in _triangle_mouse_areas(root):
        assert tri.property("enabled") is True

    combos = _legion_combos(root)
    assert len(combos) == 1
    assert combos[0].property("enabled") is True
    assert str(combos[0].property("currentText")) == "4"  # legion_options.default（真实 producer）

    sliders = [s for s in _sliders(root) if s.isVisible()]
    assert len(sliders) == 1
    assert sliders[0].property("enabled") is True

    # land Slider 门控正向：可编辑（test_senate_amount_c_controls:260 parity）
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    land_sliders = [s for s in _sliders(root) if s.isVisible() and s.property("to") == 1000]
    assert len(land_sliders) == 1
    assert land_sliders[0].property("enabled") is True


# ---------------------------------------------------------------------------
# targeted 4 — selected/unselected panel state（AU-R1-04a，G7 #8 复现）
# ---------------------------------------------------------------------------

def test_checkbox_drives_expand_collapse():
    """勾选 → 自动展开；取消勾选 → 折叠（无陈旧参数面板）；刷新复入状态一致。"""
    options = _real_senate_options()
    store = FakeSenateStore(options, can_create=True)
    _engine, root, _warnings = _load_senate_stage(store)
    app = _get_app()

    def keys(prop):
        return set(_normalize(root.property(prop)))

    # 初始：war/budget 选中并展开；land 未选中未展开
    assert "land:sale" not in keys("selectedProposalKeys")
    assert "land:sale" not in keys("expandedBillKeys")

    # 勾选 land:sale → 自动展开（checkbox 为控制交互，R1-04 契约）
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    assert "land:sale" in keys("selectedProposalKeys")
    assert "land:sale" in keys("expandedBillKeys")
    land_sliders = [s for s in _sliders(root) if s.isVisible() and s.property("to") == 1000]
    assert len(land_sliders) == 1, "勾选后 land 参数面板必须展开（G7 #8 反例闭合）"

    # 取消勾选 → 折叠（无陈旧参数面板残留）
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", False))
    app.processEvents()
    assert "land:sale" not in keys("selectedProposalKeys")
    assert "land:sale" not in keys("expandedBillKeys"), "取消勾选必须折叠参数面板（无陈旧面板）"
    land_sliders = [s for s in _sliders(root) if s.isVisible() and s.property("to") == 1000]
    assert len(land_sliders) == 0

    # 刷新复入（expandCheckedBills 与选中集一致）：取消 war 后 expandCheckedBills 不复活
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "war:w1"), Q_ARG("QVariant", False))
    app.processEvents()
    store.senateViewChanged.emit()
    app.processEvents()
    assert "war:w1" not in keys("expandedBillKeys")
    assert keys("expandedBillKeys") == keys("selectedProposalKeys"), "展开状态必须与选中集一致（刷新复入）"


# ---------------------------------------------------------------------------
# targeted 9 — R1-touched DTO null safety（AU-R1-06c）
# ---------------------------------------------------------------------------

def test_r1_touched_bindings_null_safe_real_dto_shape():
    """真实 DTO 形状加载 SenateStage → engine warnings 捕获：R1 触碰字段无新增 undefined。"""
    options = _real_senate_options()
    store = FakeSenateStore(options, can_create=True)
    _engine, root, captured = _load_senate_stage(store, collect_warnings=True)
    app = _get_app()
    # 触发一轮交互（选中 land + 折叠）覆盖 R1 触碰绑定路径
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", False))
    app.processEvents()

    r1_fields = [
        "legion_options", "budget_range", "public_land", "expandedBillKeys",
        "canCreateSenateProposal", "amount_C", "modified_budget", "params",
        "senatePublicAnnouncement", "direct_actions",
    ]
    r1_warnings = [w for w in captured if any(f in w for f in r1_fields)]
    undefined = [w for w in r1_warnings if "Unable to assign" in w or "undefined" in w.lower()]
    assert undefined == [], f"R1 触碰字段出现 undefined 绑定警告: {undefined}"
    # 全量引擎警告中也不得出现 R1 门控表达式相关 undefined
    assert not any("MouseArea" in w and "enabled" in w for w in captured), captured


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
