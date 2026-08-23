# src/tests/test_gui/test_wpe_resolution_settlement.py
"""
WP-E（GUI-BETA-R1）Resolution 结算 read-model 测试（T-1）。

覆盖（F-E-01 production chain — 真实 advance_year → _commit_settlement → read-model，
禁手工构造 _resolution_settlement 注入，R-16）：
- read-model 形状（settled_turn/year/next_year/treasury_before/after/governor_returns/
  contract_expiries/truce_expiries/decay）
- 四步骤事件：A6 总督返回（命名富化）/ A5 合同到期（身份行）/ A7 和约到期 / A3+A4 年度衰减
- 空态（四步骤全空）→ 空列表
- treasury delta 真实捕获
- execute_resolution 清空（P2-4：幂等 guard 之后）
- _apply_contract_expiration 返回类型兼容（process_contract_expiration int 契约）
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.figure import Figure
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.province import Province
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import resolution_api
from src.api import session_api
from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import GuiSessionStore


@pytest.fixture
def adapter_session():
    """真实 GUI 原型会话（production chain：adapter → session_api → state）。"""
    result = session_api.create_gui_prototype_session(start_phase="combat")
    assert result["success"]
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)
    adapter = GuiApiAdapter(state)
    return adapter, state, player_id


@pytest.fixture
def store_session():
    """真实 GUI Session Store 会话。"""
    result = session_api.create_gui_prototype_session(start_phase="combat")
    assert result["success"]
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)
    store = GuiSessionStore(state)
    store.initialize(player_id)
    return store, state, player_id


def _make_state(year=-260, turn_number=5):
    """最小可用 GameState（对齐 test_game_api_advance_year._make_state 形状）。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=year)
    return state


# ---------------------------------------------------------------------------
# 1. read-model 基本形状
# ---------------------------------------------------------------------------

def test_read_model_shape_after_advance_year():
    """advance_year 后 read-model 存在且形状正确（全部 9 字段）。"""
    state = _make_state()
    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert settlement is not None, "advance_year 后 read-model 必须存在"

    assert set(settlement.keys()) == {
        "settled_turn", "settled_year", "next_year",
        "treasury_before", "treasury_after",
        "governor_returns", "contract_expiries", "truce_expiries", "decay",
    }
    # 结算时回合（滚年前）/ 结算年 / 次年
    assert settlement["settled_turn"] == 5
    assert settlement["settled_year"] == -260
    assert settlement["next_year"] == -259
    # 空态：无事件 → 空列表
    assert settlement["governor_returns"] == []
    assert settlement["contract_expiries"] == []
    assert settlement["truce_expiries"] == []
    assert settlement["decay"] == []


def test_read_model_immune_to_phase_results_clear():
    """read-model 独立于 _phase_results：commit 尾部清空不影响（F1）。"""
    state = _make_state()
    state.advance_year()

    assert state.get_resolution_settlement() is not None
    assert state._phase_results == {}
    assert state._executed_phases == set()


def test_read_model_treasury_before_after():
    """treasury_before/after 真实捕获（A1~A7 通常不触国库 → 常相等，属诚实结果）。"""
    state = _make_state()
    state.add_treasury(1000)
    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert settlement["treasury_before"] == 1000
    assert settlement["treasury_after"] == state.treasury


# ---------------------------------------------------------------------------
# 2. A6 总督返回（命名富化 + 过滤）
# ---------------------------------------------------------------------------

def test_read_model_governor_returns_enriched():
    """A6 真实交接行：命名富化（province_name/old/new governor name）。"""
    state = _make_state()
    old_gov = Figure(id=101, name="Old Governor", is_absent=True, office="proconsul")
    designate = Figure(id=102, name="New Governor", office=None)
    state.add_member(old_gov)
    state.add_member(designate)
    province = Province(
        province_id=1, name="Sicilia", total_land=500,
        governor_id=101, governor_designate_id=102, old_governor_id=101,
        governor_type="proconsul",
    )
    state.add_province(province)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert len(settlement["governor_returns"]) == 1
    row = settlement["governor_returns"][0]
    assert row["province_id"] == 1
    assert row["province_name"] == "Sicilia"
    assert row["old_governor_id"] == 101
    assert row["new_governor_id"] == 102
    assert row["old_governor_name"] == "Old Governor"
    assert row["new_governor_name"] == "New Governor"


def test_read_model_governor_returns_skip_non_events():
    """无旧总督且无候任上任的行省 → 不构成事件，不进 read-model（E-03）。"""
    state = _make_state()
    province = Province(
        province_id=1, name="Sicilia", total_land=500,
        governor_id=None, governor_designate_id=None, old_governor_id=None,
        governor_type="proconsul",
    )
    state.add_province(province)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert settlement["governor_returns"] == []


# ---------------------------------------------------------------------------
# 3. A5 合同到期（身份行）
# ---------------------------------------------------------------------------

def test_read_model_contract_expiries_identity_rows():
    """A5 到期合同 → 身份行（contract_id/name/contract_type/turns_pending）。"""
    state = _make_state()  # turn_number=5
    contract = state.create_contract(ContractType.TAX_FARMING, 1, 90, 2)  # create_turn=2
    assert contract.status == ContractStatus.PENDING

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert len(settlement["contract_expiries"]) == 1
    row = settlement["contract_expiries"][0]
    assert row["contract_id"] == contract.id
    assert row["name"] == contract.name
    assert row["contract_type"] == "TAX_FARMING"
    assert row["turns_pending"] == 3  # 5 - 2
    # 合同确实过期（只承接事实，非编造）
    assert contract.status == ContractStatus.EXPIRED


def test_process_contract_expiration_int_contract():
    """process_contract_expiration 薄包装保持 int 契约（兼容既有调用）。"""
    state = _make_state()
    state.create_contract(ContractType.TAX_FARMING, 1, 90, 2)
    result = state.process_contract_expiration()
    assert isinstance(result, int)
    assert result >= 1

    # 第二次无副作用 → 0
    assert state.process_contract_expiration() == 0


# ---------------------------------------------------------------------------
# 4. A3+A4 年度衰减（per-figure 行）
# ---------------------------------------------------------------------------

def test_read_model_decay_rows():
    """A3/A4 衰减 → per-figure 行：age 恒有（+1），veterans/popularity 仅变化时存在。"""
    state = _make_state()
    fig = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=50)
    state.add_member(fig)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert len(settlement["decay"]) == 1
    row = settlement["decay"][0]
    assert row["figure_id"] == 1
    assert row["name"] == "Marcus"
    assert row["age"] == {"before": 40, "after": 41}
    assert row["veterans"]["before"] == 100
    assert row["veterans"]["after"] < 100
    assert row["popularity"]["before"] == 50
    assert row["popularity"]["after"] < 50


def test_read_model_decay_empty_no_living_members():
    """零存活成员 → decay 空列表（E-04 空态）。"""
    state = _make_state()
    dead = Figure(id=1, name="Dead", age=50, is_dead=True)
    state.add_member(dead)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert settlement["decay"] == []


# ---------------------------------------------------------------------------
# 5. A7 和约到期
# ---------------------------------------------------------------------------

def test_read_model_truce_expiries():
    """A7 到期和约 → truce_expiries 战争名列表（真实事件）。"""
    state = _make_state()  # turn_number=5
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)  # 4 <= 5 → 已到期
    ws._truce_wars.append(war)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert settlement["truce_expiries"] == ["Truce War"]


def test_eg7_05_threat_war_not_mislabeled_as_truce_expiry():
    """E-G7-05：THREAT 战争不再显示为「和约到期」（truce_expired ← read-model A7 事件）。"""
    from src.api import session_api as sa

    result = sa.create_gui_prototype_session(start_phase="combat")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)

    # 制造 THREAT 战争（非和约到期）
    ws = state.get_war_system()
    if ws is not None and not ws.get_threat_wars():
        threat_war = War(id="tw1", name="Threat War", start_year=-270, threat_level=5, strength=5)
        threat_war.status = WarStatus.THREAT
        ws._threats.append(threat_war)

    state.mark_phase_executed("combat")
    from src.api import resolution_api
    resolution_api.execute_resolution(state, player_id)
    state.advance_year()

    view = sa.get_resolution_view(state, player_id)
    assert view["success"] is True
    results = view["data"]["results"]
    # THREAT 战争不得出现在 truce_expired（读 model 只含真实 A7 到期事件）
    assert "Threat War" not in results["truce_expired"], (
        f"THREAT 战争被误标为和约到期: {results['truce_expired']}"
    )
    assert isinstance(results["truce_expired"], list)


# ---------------------------------------------------------------------------
# 6. execute_resolution 清空（P2-4 落点）
# ---------------------------------------------------------------------------

def test_execute_resolution_clears_read_model():
    """新一年 execute_resolution → 清空上年 read-model（幂等 guard 之后）。"""
    state = _make_state()
    state.advance_year()
    assert state.get_resolution_settlement() is not None

    state.mark_phase_executed("combat")
    result = resolution_api.execute_resolution(state)

    assert result["success"] is True
    assert state.get_resolution_settlement() is None, (
        "execute_resolution 必须清空上年 read-model（防跨年残留泄漏）"
    )


def test_execute_resolution_idempotent_guard_does_not_clear():
    """幂等 guard 早退时不清 read-model（P2-4：清空在 guard 之后）。"""
    state = _make_state()
    state.advance_year()
    assert state.get_resolution_settlement() is not None

    state.mark_phase_executed("combat")
    state.mark_phase_executed("resolution")  # 已执行 → 幂等早退
    result = resolution_api.execute_resolution(state)

    assert result["success"] is False
    assert "resolution_already_executed" in result.get("errors", [])
    # guard 早退 → 不清空
    assert state.get_resolution_settlement() is not None


# ---------------------------------------------------------------------------
# 7. 全事件组合用例（F-E-01 用例 A：非空四步）
# ---------------------------------------------------------------------------

def test_read_model_full_four_step_events():
    """组合：总督返回 + 合同到期 + 和约到期 + 年度衰减 同时产出。"""
    state = _make_state()
    # A6：交接行省
    old_gov = Figure(id=101, name="Old Gov", is_absent=True, office="proconsul")
    designate = Figure(id=102, name="New Gov", office=None)
    state.add_member(old_gov)
    state.add_member(designate)
    province = Province(
        province_id=1, name="Sicilia", total_land=500,
        governor_id=101, governor_designate_id=102, old_governor_id=101,
        governor_type="proconsul",
    )
    state.add_province(province)
    # A5：到期合同
    state.create_contract(ContractType.PUBLIC_WORKS, 1, 90, 2)
    # A7：到期和约
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)
    ws._truce_wars.append(war)
    # A3+A4：存活成员（含交接人物，衰减行亦含 designate 等）
    fig = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=50)
    state.add_member(fig)

    state.advance_year()

    settlement = state.get_resolution_settlement()
    assert len(settlement["governor_returns"]) == 1
    assert len(settlement["contract_expiries"]) == 1
    assert settlement["truce_expiries"] == ["Truce War"]
    # 衰减行：3 个存活成员（old_gov / designate / Marcus）
    assert len(settlement["decay"]) == 3
    decay_ids = {row["figure_id"] for row in settlement["decay"]}
    assert {1, 101, 102} == decay_ids


# ---------------------------------------------------------------------------
# 8. Slice 2 — 视图 DTO（get_resolution_view 四步 / 双源 / read-model 驱动）
# ---------------------------------------------------------------------------

def test_resolution_view_four_steps_after_advance(adapter_session):
    """advance_year 后 get_resolution_view：四步全部 completed（read-model 驱动），无第五步。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    view = adapter.get_resolution_view(player_id)
    assert view["resolved"] is True
    steps = view["step_statuses"]
    assert len(steps) == 4
    names = [s["name"] for s in steps]
    assert "next_year" not in names
    assert names == ["governor_return", "contract_expiry", "risk_check", "annual_decay"]
    for s in steps:
        assert s["status"] == "completed"
    # read-model 驱动的结算结果字段
    results = view["results"]
    assert results["settled"] is True
    assert results["settled_year"] is not None
    assert results["next_year"] == results["settled_year"] + 1
    assert "treasury_before" in results and "treasury_after" in results
    assert "contract_expiries" in results
    assert "decay" in results
    assert isinstance(results["governor_transitions"], list)
    assert isinstance(results["truce_expired"], list)


def test_resolution_view_resolved_dual_source(adapter_session):
    """F2 双源：advance_year 后 executed_phases 已清空，但 read-model 维持 resolved=True。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    # advance_year 清空 executed_phases（_commit_settlement 尾部）
    assert not state.is_phase_executed("resolution")
    view = adapter.get_resolution_view(player_id)
    assert view["resolved"] is True  # 由 read-model 维持


def test_resolution_view_summary_next_year_from_readmodel(adapter_session):
    """summary.next_year 由 read-model 驱动（结算年 + 1）。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    view = adapter.get_resolution_view(player_id)
    settlement = state.get_resolution_settlement()
    summary = view["summary"]
    assert summary["next_year"] != ""
    assert "BC" in summary["next_year"] or "AD" in summary["next_year"]
    assert summary["decay_applied"] is True
    assert settlement["next_year"] is not None


def test_resolution_view_warnings_kept_as_current_scan(adapter_session):
    """F4：warnings 保留为现状扫描（不进 read-model），空 → 空列表。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    view = adapter.get_resolution_view(player_id)
    assert isinstance(view["warnings"], list)


# ---------------------------------------------------------------------------
# 9. Slice 2 — 两段式推进（F3）
# ---------------------------------------------------------------------------

def test_two_stage_advance_first_stage_no_navigation(store_session):
    """第一段：advance_year 成功 → 不跳转，resolutionSettled=True，仍停留 resolution。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.resolutionResolved is True

    feedback = store.doAdvanceResolution()
    assert feedback["success"]
    assert store.selectedPhaseId == "resolution"  # 不跳转
    assert store.resolutionSettled is True
    # 标签动态化
    assert "进入下一年度" in store.advanceCurrentPhaseText


def test_two_stage_advance_second_stage_navigates(store_session):
    """第二段：已结算 → 导航 mortality + 状态复位。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    store.doAdvanceResolution()  # 第一段
    assert store.selectedPhaseId == "resolution"

    feedback = store.doAdvanceResolution()  # 第二段
    assert feedback["success"]
    assert store.selectedPhaseId == "mortality"
    # 瞬态标记复位（read-model 仍保 settled=True 直到新年 execute_resolution 清空——F3 设计）
    assert store._resolution_settled is False


def test_two_stage_advance_failure_stays(store_session):
    """第一段失败：停留 + 刷新 + 反馈（FC-06 失败不变式）。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")

    original_advance = store._adapter.advance_year
    def failing_advance(pid):
        return {"success": False, "message": "Simulated failure", "feedback_type": "error"}
    store._adapter.advance_year = failing_advance
    try:
        feedback = store.doAdvanceResolution()
        assert not feedback["success"]
        assert store.selectedPhaseId == "resolution"
        assert store.resolutionSettled is False
        assert store.resolutionResolved is True
    finally:
        store._adapter.advance_year = original_advance


def test_on_refresh_does_not_retrigger_execute_after_settlement(store_session):
    """F3 关键正确性：结算后 resolved 双源阻止 _on_refresh 重执行 execute_resolution。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    store.doAdvanceResolution()  # 第一段：结算完成
    assert store.resolutionSettled is True

    # 模拟 _on_refresh（结算后 _executed_phases 已清空，read-model 维持 resolved）
    store._on_refresh()
    # 不应重触发（_executeResolution 会再执行 execute_resolution——combat 未执行则失败；
    # 双源 resolved=True 使触发条件不成立）
    assert store.resolutionSettled is True
    view = store.resolutionView
    assert view.get("resolved", False) is True


# ---------------------------------------------------------------------------
# 10. Slice 2 — RENDER（QML objectName 断言，F-E-01）
# ---------------------------------------------------------------------------


def _create_qml_engine(store):
    """加载真实 Main.qml（对齐 test_qml_startup._create_engine 模式）。"""
    import os
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


def _all_qquick_items(root):
    """深度优先遍历 QQuickItem 视觉子项（childItems 可穿透 Repeater 生成的项）。"""
    from PySide6.QtQuick import QQuickItem
    pending = [root if isinstance(root, QQuickItem) else root.findChild(QQuickItem)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


def test_render_step_bar_has_four_children(store_session):
    """RENDER：resolutionStepBar 子项 == 4（无第五块「决算完成」）。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickItem

    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")

    engine, qml_dir = _create_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    step_bar = root.findChild(QObject, "resolutionStepBar")
    assert step_bar is not None, "resolutionStepBar not found"
    # Repeater 生成的 step 块为 QQuickRectangle 视觉子项（childItems 穿透 Repeater）
    step_blocks = [
        i for i in _all_qquick_items(step_bar)
        if isinstance(i, QQuickItem) and i.property("color") is not None and i.parentItem() is not None
    ]
    # 精确过滤：delegate Rectangle 具有 color 属性且直接属于 stepBar 的视觉子树（Repeater 容器内）
    delegate_rects = [i for i in _all_qquick_items(step_bar) if str(i.metaObject().className()).startswith("QQuickRectangle")]
    assert len(delegate_rects) == 4, f"expected 4 step blocks, got {len(delegate_rects)}"


def test_render_four_step_sections_present(store_session):
    """RENDER：结算后四步分节 objectName 全部存在 + summaryPanel 保留。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication

    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    store.doAdvanceResolution()  # 第一段结算（面板可见前提）

    engine, qml_dir = _create_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    for object_name in [
        "resolutionResultsPanel",
        "resolutionGovernorReturnSection",
        "resolutionContractExpirySection",
        "resolutionRiskCheckSection",
        "resolutionAnnualDecaySection",
        "resolutionTruceExpirySection",
        "resolutionSummaryPanel",
    ]:
        assert root.findChild(QObject, object_name) is not None, object_name
