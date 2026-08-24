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
    """A3/A4 衰减 → preview.faction_influence 派系聚合（decay-only，ODR-C1；无 per-figure 行）。"""
    from src.core.entities.entities import Faction
    state = _make_state()
    fig = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=50, faction_id="Optimates")
    state.add_member(fig)
    faction = Faction(id="Optimates", name="贵族派")
    faction.member_ids = [1]
    state._factions["Optimates"] = faction

    preview = session_api._build_resolution_preview(state)
    assert len(preview["faction_influence"]) == 1
    row = preview["faction_influence"][0]
    assert row["faction_id"] == "Optimates"
    assert row["faction_name"] == "贵族派"
    # before = 当前影响力（只读）；after = 纯函数衰减重算（decay-only）
    assert row["influence_before"] == fig.influence
    assert row["influence_after"] < row["influence_before"]
    assert row["influence_delta"] == row["influence_after"] - row["influence_before"]
    # 读 model 仍为内部 parity 源（decay 行保留，非展示）
    state.advance_year()
    settlement = state.get_resolution_settlement()
    assert len(settlement["decay"]) == 1


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
    """组合：总督返回 + 合同到期 + 和约到期 + 年度衰减（派系聚合）→ preview 四类目事实。"""
    from src.core.entities.entities import Faction
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
    # A3+A4：存活成员（归属派系，供派系聚合）
    fig = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=50, faction_id="Optimates")
    state.add_member(fig)
    faction = Faction(id="Optimates", name="贵族派")
    faction.member_ids = [1]
    state._factions["Optimates"] = faction

    preview = session_api._build_resolution_preview(state)
    # 总督返回（guard：old_fig 存在且未死；designate 升任 → successor_name）
    assert len(preview["governor_returns"]) == 1
    gr = preview["governor_returns"][0]
    assert gr["province_id"] == 1
    assert gr["province_name"] == "Sicilia"
    assert gr["governor_name"] == "Old Gov"
    assert gr["successor_name"] == "New Gov"
    # 合同到期（身份行）
    assert len(preview["contract_expiries"]) == 1
    assert preview["contract_expiries"][0]["contract_type"] == "PUBLIC_WORKS"
    # 和约到期
    assert preview["truce_expiries"] == [{"war_name": "Truce War"}]
    # 年度衰减（派系聚合，无 per-figure 行）
    assert len(preview["faction_influence"]) == 1
    assert preview["faction_influence"][0]["faction_name"] == "贵族派"
    assert preview["faction_influence"][0]["influence_delta"] < 0

    # read-model（内部 parity 源）仍按既有形状产出
    state.advance_year()
    settlement = state.get_resolution_settlement()
    assert len(settlement["governor_returns"]) == 1
    assert len(settlement["contract_expiries"]) == 1
    assert settlement["truce_expiries"] == ["Truce War"]
    assert len(settlement["decay"]) == 3


# ---------------------------------------------------------------------------
# 8. Slice 2 — 视图 DTO（get_resolution_view 四步 / 双源 / read-model 驱动）
# ---------------------------------------------------------------------------

def test_resolution_view_preview_categories_after_advance(adapter_session):
    """advance_year 后 get_resolution_view：preview 四类目存在、无 step_statuses 键（E-02）；
    resolved 单源化 → False（settlement 不再参与门控）。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    view = adapter.get_resolution_view(player_id)
    assert "step_statuses" not in view, "step_statuses 键必须移除（E-02）"
    preview = view["preview"]
    for key in ["governor_returns", "contract_expiries", "truce_expiries", "faction_influence"]:
        assert key in preview, key
    assert isinstance(preview["faction_influence"], list)
    # resolved 单源化：advance 后 False → results 为空；read-model 事实经 settlement 访问器（parity 源）
    assert view["resolved"] is False
    results = view["results"]
    assert "settled" not in results, "results.settled 必须移除（D10 §3）"
    assert results["settled_year"] is None
    settlement = state.get_resolution_settlement()
    assert settlement is not None
    assert settlement["next_year"] == settlement["settled_year"] + 1
    assert "treasury_before" in settlement and "treasury_after" in settlement
    assert isinstance(settlement["contract_expiries"], list)
    assert isinstance(settlement["decay"], list)
    assert isinstance(settlement["governor_returns"], list)
    assert isinstance(settlement["truce_expiries"], list)


def test_resolution_view_resolved_single_source(adapter_session):
    """resolved 单源化（D2 §4.2）：仅 is_phase_executed；advance 后 read-model 仍在但 resolved=False。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    assert state.is_phase_executed("resolution")
    view = adapter.get_resolution_view(player_id)
    assert view["resolved"] is True

    adapter.advance_year(player_id)
    # advance 后 executed_phases 已清空，但 read-model 仍存在 → 单源化下 resolved=False（旧双源会 True）
    assert not state.is_phase_executed("resolution")
    assert state.get_resolution_settlement() is not None
    view2 = adapter.get_resolution_view(player_id)
    assert view2["resolved"] is False
    assert view2["preview"]["faction_influence"] is not None


def test_resolution_view_summary_next_year(adapter_session):
    """summary.next_year 展示（结算后 = 结算年 + 1；resolved=False 时为空态——单源化）。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)

    # 结算后（未 advance）：resolved=True → summary 可见
    view = adapter.get_resolution_view(player_id)
    assert view["resolved"] is True
    summary = view["summary"]
    assert summary["next_year"] != ""
    assert "BC" in summary["next_year"] or "AD" in summary["next_year"]
    # 结算后但未 advance → read-model 未写 → decay_applied 诚实为 False
    assert summary["decay_applied"] is False

    # advance 后：resolved=False → summary 空态（面板隐藏，非展示陈旧数据）
    adapter.advance_year(player_id)
    view2 = adapter.get_resolution_view(player_id)
    assert view2["resolved"] is False
    assert view2["summary"]["next_year"] == ""


def test_resolution_view_warnings_kept_as_current_scan(adapter_session):
    """F4：warnings 保留为现状扫描（不进 read-model），空 → 空列表。"""
    adapter, state, player_id = adapter_session
    state.mark_phase_executed("combat")
    adapter.execute_phase("resolution", player_id)
    adapter.advance_year(player_id)

    view = adapter.get_resolution_view(player_id)
    assert isinstance(view["warnings"], list)


# ---------------------------------------------------------------------------
# 9. 单命令推进（E-05，两段式语义废除）
# ---------------------------------------------------------------------------

def test_advance_failure_stays_and_retryable(store_session):
    """单命令失败：停留 resolution + advancing 复位 + 可重试（EC-09）。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.resolutionResolved is True

    original_advance = store._adapter.advance_year
    def failing_advance(pid):
        return {"success": False, "message": "Simulated failure", "feedback_type": "error"}
    store._adapter.advance_year = failing_advance
    try:
        feedback = store.doAdvanceResolution()
        assert not feedback["success"]
        assert store.selectedPhaseId == "resolution"
        assert store.isResolutionAdvancing is False
        assert store.resolutionResolved is True
    finally:
        store._adapter.advance_year = original_advance

    # 可重试：恢复后再次调用 → 直入 mortality
    feedback2 = store.doAdvanceResolution()
    assert feedback2["success"]
    assert store.selectedPhaseId == "mortality"


def test_on_refresh_resolved_single_source_prevents_reexecute(store_session):
    """resolved 单源化：自动结算后 resolved=True（is_phase_executed）→ _on_refresh 不重执行；
    advance 后 resolved=False → 跨年不毒化（EC-02/A4）。"""
    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.resolutionResolved is True
    assert state.is_phase_executed("resolution")

    # 结算后 _on_refresh：resolved=True → 不重触发 execute_resolution
    execute_calls = []
    original_execute = store._adapter.execute_phase
    def counting_execute(phase, pid):
        execute_calls.append(phase)
        return original_execute(phase, pid)
    store._adapter.execute_phase = counting_execute
    try:
        store._on_refresh()
    finally:
        store._adapter.execute_phase = original_execute
    assert "resolution" not in execute_calls, "resolved=True 时 _on_refresh 不得重触发 execute_resolution"
    assert store.resolutionResolved is True

    # 单命令 advance → 新年 resolved=False（单源）→ 跨年不毒化
    feedback = store.doAdvanceResolution()
    assert feedback["success"]
    assert store.selectedPhaseId == "mortality"
    assert store.resolutionResolved is False


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


def test_render_four_categories_and_risk_zone_present(store_session):
    """RENDER：四类目 + 独立风险区 + summaryPanel objectName 全部存在；无 resolutionStepBar（E-02）。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication

    store, state, player_id = store_session
    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    # 门控 resolutionResolved（G7R：预结算即可见）——无需 advance
    assert store.resolutionResolved is True

    engine, qml_dir = _create_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    for object_name in [
        "resolutionResultsPanel",
        "resolutionGovernorReturnSection",
        "resolutionContractExpirySection",
        "resolutionTruceExpirySection",
        "resolutionAnnualDecaySection",
        "resolutionRiskCheckSection",
        "resolutionSummaryPanel",
    ]:
        assert root.findChild(QObject, object_name) is not None, object_name
    # E-02：无可见顺序 StepBar
    assert root.findChild(QObject, "resolutionStepBar") is None, "resolutionStepBar 必须移除（E-02）"
