# src/tests/test_gui/test_senate_amount_c_controls.py
"""WP-D AU-7 RENDER: SenateStage.qml land amount_C 控件形状（FC-05/06 改造）。

- 控件：Slider from=1 / to=public_land（root）/ stepSize=1 / value=params.amount_C（nested）
- 交互：改值 → setBillParam("amount_C") → payload params.amount_C 更新
- 守卫：hasZeroValueLandSelection 以 amount_C 为主判定（≤0 → 阻止提交）
- parity-proof：mock option shape 与真实 get_senate_view land option 逐字段一致（由 DATA 侧
  test_senate_land_amount_c.py 背书）；提交 payload 走真实链 round-trip。
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
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression
from PySide6.QtQuick import QQuickItem
import shiboken6
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


def _land_option(amount_C=100, public_land=1000):
    """land option 形状 = 真实 producer 输出（test_senate_land_amount_c.py DATA 侧背书）。"""
    return {
        "key": "land:sale",
        "type": "land",
        "title": "卖地法案 — 出售国家公地",
        "detail": "出售 100 C（约 10%）国家公地；当前公地 1000 C",
        "params": {"act_type": "sale", "amount_C": amount_C, "percent": amount_C / public_land},
        "public_land": public_land,
        "selected": False,
        "enabled": True,
    }


class _MockSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, options, current_step="proposal", parent=None):
        super().__init__(parent)
        self._options = options
        self._current_step = current_step
        self._submitted = []
        self.submit_calls = 0
        self.last_proposals = None

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

    @staticmethod
    def _variant_to_python(value):
        if hasattr(value, "toVariant"):
            return value.toVariant()
        if hasattr(value, "toPython"):
            return value.toPython()
        return value

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        self.submit_calls += 1
        self.last_proposals = self._variant_to_python(proposals)
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
    engine._test_refs = (store, theme)
    return engine, roots[0]


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


def _visible_sliders(root):
    return [s for s in _all_items(root)
            if "Slider" in s.metaObject().className()
            and "Groove" not in s.metaObject().className()
            and "Handle" not in s.metaObject().className()
            and s.isVisible()]


def _select_and_expand_land(root, app):
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    QMetaObject.invokeMethod(root, "expandCheckedBills", Qt.DirectConnection)
    app.processEvents()


def _call_bool(engine, root, name):
    """通过 QQmlExpression 调用 root 的返回 bool 的 JS 函数。"""
    return bool(_call_expr(engine, root, "_r2root.%s()" % name))


def _call_expr(engine, root, expr_text):
    """在 engine rootContext 内求值 JS 表达式（_r2root 已绑定 root）。

    注：PySide6 QQmlExpression.evaluate() 返回 (value, isUndefined) 二元组，需解包取 value。
    """
    ctx = engine.rootContext()
    ctx.setContextProperty("_r2root", root)
    expr = QQmlExpression(ctx, None, expr_text)
    result = expr.evaluate()
    assert not expr.hasError(), expr.error()
    if isinstance(result, tuple) and len(result) == 2:
        result = result[0]
    return result


def _click_submit(engine, root):
    ctx = engine.rootContext()
    ctx.setContextProperty("_r2root", root)
    expr = QQmlExpression(ctx, None, "sessionStore.doSubmitSenateProposals(_r2root.selectedProposals())")
    result = expr.evaluate()
    assert not expr.hasError(), expr.error()
    return result


def test_land_amount_c_slider_shape():
    """AU-7 RENDER：land Slider from=1 / to=public_land(root) / stepSize=1 / value=params.amount_C(nested)。"""
    store = _MockSenateStore([_land_option(amount_C=300, public_land=1000)])
    engine, root = _load_senate_stage(store)
    app = _get_app()
    _select_and_expand_land(root, app)

    sliders = _visible_sliders(root)
    assert len(sliders) == 1, f"expected exactly 1 visible land Slider, got {len(sliders)}"
    slider = sliders[0]
    assert slider.property("visible") is True
    assert slider.property("enabled") is True
    assert slider.property("from") == 1
    assert slider.property("to") == 1000
    assert slider.property("stepSize") == 1
    assert slider.property("value") == 300


def test_land_amount_c_change_writes_bill_param():
    """AU-7 RENDER：Slider 改值 → setBillParam(amount_C) → 提交 payload params.amount_C == 新值。"""
    store = _MockSenateStore([_land_option(amount_C=100, public_land=1000)])
    engine, root = _load_senate_stage(store)
    app = _get_app()
    _select_and_expand_land(root, app)

    sliders = _visible_sliders(root)
    assert len(sliders) == 1
    sliders[0].setProperty("value", 500)
    app.processEvents()

    _click_submit(engine, root)
    captured = store.last_proposals
    assert captured is not None, "mock store must capture submitted payload"
    land_row = [r for r in captured if r.get("type") == "land"][0]
    assert land_row["params"]["amount_C"] == 500
    # root public_land 不被重排进 params（R2-NEW-01 F2 / RC-R2-01 教训）
    assert "public_land" not in land_row["params"]


def test_has_zero_value_land_selection_amount_c():
    """AU-7 RENDER：hasZeroValueLandSelection 以 amount_C 为主判定（≤0 → true 阻止提交）。

    注：真实 producer 默认 amount_C = max(1, int(public_land*default_percent)) 恒 ≥1，且 Slider
    from=1 会将越界值 clamp 到 1 —— 故零值仅能经显式 setBillParam 覆盖注入（守卫的防御对象）。
    """
    store = _MockSenateStore([_land_option(amount_C=300, public_land=1000)])
    engine, root = _load_senate_stage(store)
    app = _get_app()
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    # 正常值 → 不阻止提交
    assert _call_bool(engine, root, "hasZeroValueLandSelection") is False
    # 显式零值覆盖 → 阻止提交
    QMetaObject.invokeMethod(root, "setBillParam", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", "amount_C"), Q_ARG("QVariant", 0))
    app.processEvents()
    assert _call_bool(engine, root, "hasZeroValueLandSelection") is True

    # 未选中 land → 不阻止（守卫只检查已选 land）
    store2 = _MockSenateStore([_land_option(amount_C=0, public_land=1000)])
    engine2, root2 = _load_senate_stage(store2)
    app.processEvents()
    assert _call_bool(engine2, root2, "hasZeroValueLandSelection") is False


def test_land_amount_c_round_trip_real_chain():
    """parity-proof（真实链配对）：QML 捕获 payload（amount_C=500）→ GuiApiAdapter → 真实链存储 500。"""
    from src.ui.gui.api_adapter import GuiApiAdapter
    store = _MockSenateStore([_land_option(amount_C=100, public_land=1000)])
    engine, root = _load_senate_stage(store)
    app = _get_app()
    _select_and_expand_land(root, app)
    sliders = _visible_sliders(root)
    sliders[0].setProperty("value", 500)
    app.processEvents()
    _click_submit(engine, root)
    captured = store.last_proposals

    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    state.add_member(consul)
    faction.member_ids.append(1)
    state._players = {"player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human")}
    state._current_player_id = "player1"
    state._national_public_land = 1000
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    adapter = GuiApiAdapter(state)
    feedback = adapter.submit_senate_proposals("player1", captured)
    assert feedback["success"], feedback
    proposals = state.get_senate_proposals()
    by_type = {p["type"]: p for p in proposals}
    assert by_type["land"]["amount_C"] == 500
    assert by_type["land"]["act_type"] == "sale"
    assert abs(by_type["land"]["percent"] - 0.5) < 1e-9


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
