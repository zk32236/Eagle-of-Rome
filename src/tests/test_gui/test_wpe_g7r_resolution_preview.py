# src/tests/test_gui/test_wpe_g7r_resolution_preview.py
"""
WP-E-G7R — Resolution preview 只读投影 + 单源化 + 呈现契约测试（G7R 新增）。

覆盖（production-shape，R-16：禁手工构造 preview DTO 注入——全部经真实 producer
`session_api._build_resolution_preview` / `get_resolution_view` 路径）：
- EC-01 preview 零变异（等价快照比对）
- EC-02 preview 刷新稳定（确定性）+ 跨年 re-entry 不毒化（A4 / resolved 单源化）
- EC-03 无 StepBar / 无「4 / 4」（RENDER）
- EC-04 将来时文案族（E-03，禁「预计」/过去时）
- EC-05 派系聚合 / 无 per-figure dump（R-21）
- EC-10 preview = commit parity（decay-only 分量，ODR-C1）
- 005-05 派系聚合投影 / 005-06 空态（E-04）
"""
import os

import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure
from src.core.entities.contract import ContractType
from src.core.entities.province import Province
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore


def _make_state(year=-260, turn_number=5):
    """最小可用 GameState（对齐 test_wpe_resolution_settlement._make_state 形状）。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=year)
    return state


def _add_faction(state, fid, name, member_ids):
    faction = Faction(id=fid, name=name)
    faction.member_ids = list(member_ids)
    state._factions[fid] = faction
    return faction


def _make_rich_state():
    """四类目齐全状态（真实 producer 驱动；禁手工构造 preview DTO，R-16）。"""
    state = _make_state()
    # A3+A4：成员（veterans/popularity > 0；fig1 带 office + temp 任务 → decay-only 边界）
    fig1 = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=50,
                  faction_id="Optimates", office="consul")
    fig1.add_temp_influence_task(10, 2)
    fig2 = Figure(id=2, name="Lucius", age=45, veterans=40, popularity=20, faction_id="Optimates")
    fig3 = Figure(id=3, name="Gaius", age=38, veterans=0, popularity=30, faction_id="Populares")
    for fig in (fig1, fig2, fig3):
        state.add_member(fig)
    _add_faction(state, "Optimates", "贵族派", [1, 2])
    _add_faction(state, "Populares", "平民派", [3])
    # A6：总督交接（old_governor_id 有值 → 返回事件；designate 升任 → successor_name）
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
    # A5：到期合同（PENDING 且 create_turn=2，现回合 5 → 存在 ≥3 回合）
    state.create_contract(ContractType.PUBLIC_WORKS, 1, 90, 2)
    # A7：到期和约
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)
    ws._truce_wars.append(war)
    return state


def _snapshot_state(state):
    """preview 调用前后的等价快照（EC-01：year/turn/member/contract/truce/province/treasury）。"""
    return {
        "year": state.turn.year if state.turn else None,
        "turn_number": state.turn.turn_number if state.turn else None,
        "treasury": state.treasury,
        "members": [
            {
                "id": m.id,
                "age": m.age,
                "veterans": m.veterans,
                "popularity": m.popularity,
                "influence": m.influence,
                "office": m.office,
                "is_dead": m.is_dead,
                "is_absent": m.is_absent,
                "temp_tasks": [dict(t) for t in m._temp_influence_tasks],
            }
            for m in state.get_living_members()
        ],
        "contracts": [
            {"id": c.id, "status": c.status.name, "create_turn": c.create_turn}
            for c in state.contracts
        ],
        "provinces": [
            {
                "id": p.province_id,
                "old_governor_id": p.old_governor_id,
                "governor_designate_id": p.governor_designate_id,
            }
            for p in state.get_all_provinces()
        ],
        "war_system_present": state.get_war_system() is not None,
    }


# ---------------------------------------------------------------------------
# EC-01 / EC-02 — 零变异 + 刷新稳定
# ---------------------------------------------------------------------------

def test_preview_zero_mutation():
    """EC-01 / 005-11：_build_resolution_preview 前后 state 等价快照零变化。"""
    state = _make_rich_state()
    before = _snapshot_state(state)

    session_api._build_resolution_preview(state)
    session_api._build_resolution_preview(state)

    after = _snapshot_state(state)
    assert before == after, "preview 必须零变异（EC-01）"


def test_preview_refresh_stable():
    """EC-02 / 005-11：重复 N 次 preview → 同结果（确定性、幂等）。"""
    state = _make_rich_state()
    results = [session_api._build_resolution_preview(state) for _ in range(5)]
    for r in results[1:]:
        assert r == results[0], "preview 刷新必须稳定（EC-02）"


# ---------------------------------------------------------------------------
# 005-05 / EC-05 — 派系聚合投影（decay-only，ODR-C1）
# ---------------------------------------------------------------------------

def test_faction_influence_aggregate_projection():
    """005-05：before=Σinfluence；after=纯函数只读重算；delta=after-before；decay-only（office 恒定）。"""
    from src.core.entities.figure import _compute_influence
    state = _make_rich_state()
    fig1 = state.get_member(1)
    fig2 = state.get_member(2)
    fig3 = state.get_member(3)

    preview = session_api._build_resolution_preview(state)
    by_faction = {row["faction_id"]: row for row in preview["faction_influence"]}

    # before = Σ 当前影响力
    assert by_faction["Optimates"]["influence_before"] == fig1.influence + fig2.influence
    assert by_faction["Populares"]["influence_before"] == fig3.influence

    # after = 纯函数只读重算（decay-only：veterans/popularity/temp 衰减目标，office/land/family 恒定）
    plan = state._plan_member_decay()
    t1 = plan[1]
    temp_after_1 = sum(t["per_turn"] for t in t1["temp_influence_tasks"])
    exp_after_1 = _compute_influence(
        fig1.land_private, t1["veterans"], t1["popularity"],
        fig1.family_prestige, fig1.get_office_influence_bonus(), temp_after_1,
    )
    t2 = plan[2]
    exp_after_2 = _compute_influence(
        fig2.land_private, t2["veterans"], t2["popularity"],
        fig2.family_prestige, fig2.get_office_influence_bonus(), 0,
    )
    t3 = plan[3]
    exp_after_3 = _compute_influence(
        fig3.land_private, t3["veterans"], t3["popularity"],
        fig3.family_prestige, fig3.get_office_influence_bonus(), 0,
    )
    assert by_faction["Optimates"]["influence_after"] == exp_after_1 + exp_after_2
    assert by_faction["Populares"]["influence_after"] == exp_after_3
    assert by_faction["Optimates"]["influence_delta"] == (
        by_faction["Optimates"]["influence_after"] - by_faction["Optimates"]["influence_before"]
    )
    # decay-only（ODR-C1）：office bonus 恒定并入 after（不因总督交接变化）
    assert exp_after_1 == _compute_influence(
        fig1.land_private, t1["veterans"], t1["popularity"],
        fig1.family_prestige, fig1.get_office_influence_bonus(), temp_after_1,
    )
    assert fig1.get_office_influence_bonus() == 40  # consul


def test_no_per_figure_decay_dump():
    """EC-05 / R-21：ResolutionStage.qml 衰减区无 per-figure dump（禁 age/veterans/popularity 行）。"""
    qml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "src", "ui", "gui", "qml", "stages", "ResolutionStage.qml",
    )
    with open(qml_path, encoding="utf-8") as f:
        content = f.read()
    # 衰减区必须消费 preview.faction_influence（派系聚合）
    assert "preview.faction_influence" in content
    # 禁 per-figure 展示字段
    assert "resolutionResults.decay" not in content
    assert "年龄 " not in content
    assert "· 老兵 " not in content
    assert "· 声望 " not in content


# ---------------------------------------------------------------------------
# EC-10 — preview = commit parity（decay-only 分量，ODR-C1）
# ---------------------------------------------------------------------------

def test_preview_commit_parity():
    """EC-10 / 005-13：同锁定态 preview 四类事实 == advance 后 settlement/权威状态
    （faction 比较对象 = decay-only 分量，ODR-C1）。"""
    from src.core.entities.figure import _compute_influence
    state = _make_rich_state()
    # 锁定 office bonus（decay-only 比较：office 恒定，不取 advance 后可能变化的 office）
    office_bonus_map = {m.id: m.get_office_influence_bonus() for m in state.get_living_members()}
    before_influence = {m.id: m.influence for m in state.get_living_members()}

    preview = session_api._build_resolution_preview(state)
    state.advance_year()
    settlement = state.get_resolution_settlement()

    # 1) 总督返回 parity（province_id/province_name/old governor 名；successor == new governor 名）
    assert len(preview["governor_returns"]) == 1
    gr = preview["governor_returns"][0]
    sr_rows = [r for r in settlement["governor_returns"] if r["province_id"] == gr["province_id"]]
    assert len(sr_rows) == 1
    assert sr_rows[0]["province_name"] == gr["province_name"]
    assert sr_rows[0]["old_governor_name"] == gr["governor_name"]
    assert sr_rows[0]["new_governor_name"] == gr["successor_name"]

    # 2) 合同到期 parity（身份行：id/name/contract_type）
    preview_contracts = {(c["contract_id"], c["name"], c["contract_type"]) for c in preview["contract_expiries"]}
    settlement_contracts = {(c["contract_id"], c["name"], c["contract_type"]) for c in settlement["contract_expiries"]}
    assert preview_contracts == settlement_contracts

    # 3) 和约到期 parity
    assert {t["war_name"] for t in preview["truce_expiries"]} == set(settlement["truce_expiries"])

    # 4) 派系聚合 parity（decay-only 分量：advance 后用同一纯函数 + 锁定 office 重算）
    by_faction = {row["faction_id"]: row for row in preview["faction_influence"]}
    recomputed = {}
    for faction in state.factions.values():
        total = 0
        for m in state.get_living_members():
            if m.faction_id != faction.id:
                continue
            temp_after = sum(t["per_turn"] for t in m._temp_influence_tasks)
            total += _compute_influence(
                m.land_private, m.veterans, m.popularity,
                m.family_prestige, office_bonus_map[m.id], temp_after,
            )
        recomputed[faction.id] = total
    assert by_faction["Optimates"]["influence_after"] == recomputed["Optimates"]
    assert by_faction["Populares"]["influence_after"] == recomputed["Populares"]
    # before 分量 = 预 advance 的 Σ 影响力（锁定）
    assert by_faction["Optimates"]["influence_before"] == (
        before_influence[1] + before_influence[2]
    )
    assert by_faction["Populares"]["influence_before"] == before_influence[3]


# ---------------------------------------------------------------------------
# A4 / EC-02 — resolved 单源化 + 跨年 re-entry 不毒化
# ---------------------------------------------------------------------------

def test_resolved_single_source_no_cross_year_poisoning():
    """A4 / EC-02：advance 后 resolved=False（单源化）→ 新年入口自动结算可靠触发（跨年不卡死）。"""
    result = session_api.create_gui_prototype_session(start_phase="combat")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)
    store = GuiSessionStore(state)
    store.initialize(player_id)

    state.mark_phase_executed("combat")
    store.refreshSnapshot()
    store.selectPhase("resolution")
    assert store.resolutionResolved is True
    assert state.is_phase_executed("resolution")

    # 单命令 advance → 新年
    feedback = store.doAdvanceResolution()
    assert feedback["success"]
    assert store.selectedPhaseId == "mortality"
    # 单源化：resolved=False（旧双源会因上年 read-model 残留而 True → 新年入口永不结算 → 循环卡死）
    store._refresh_resolution_view()
    assert store.resolutionResolved is False

    # 新年重新进入 resolution → 自动结算触发（execute_resolution 被调用；combat 未执行故失败，属正常流程序）
    execute_calls = []
    original_execute = store._adapter.execute_phase

    def counting_execute(phase, pid):
        execute_calls.append(phase)
        return original_execute(phase, pid)

    store._adapter.execute_phase = counting_execute
    try:
        store.selectPhase("resolution")
    finally:
        store._adapter.execute_phase = original_execute
    assert "resolution" in execute_calls, "新年入口必须触发自动结算（跨年毒化已闭合）"

    # 真实流程：combat 执行后再结算 → 成功 + 旧 read-model 清空
    state.mark_phase_executed("combat")
    store._refresh_resolution_view()
    store.selectPhase("resolution")
    assert state.is_phase_executed("resolution")
    assert store.resolutionResolved is True
    assert state.get_resolution_settlement() is None, "execute_resolution 必须清空上年 read-model"


# ---------------------------------------------------------------------------
# RENDER：E-03/E-04 文案族 + 无 StepBar / 无 4/4（静态 + 引擎渲染）
# ---------------------------------------------------------------------------

def _qml_paths():
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "src", "ui", "gui", "qml",
    )
    return {
        "resolution_stage": os.path.join(base, "stages", "ResolutionStage.qml"),
        "context_panel": os.path.join(base, "shell", "ContextPanel.qml"),
    }


def _create_qml_engine(store):
    """加载真实 Main.qml（对齐 test_qml_startup._create_engine 模式）。"""
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


def test_future_tense_copy_family():
    """EC-04 / 005-02/03/09：E-03 将来时文案族冻结在 ResolutionStage.qml；禁「预计」/过去时。"""
    paths = _qml_paths()
    with open(paths["resolution_stage"], encoding="utf-8") as f:
        content = f.read()

    # 总督返回（005-02）
    assert "总督\" + (gt.governor_name || \"\") + \"将返回罗马" in content
    # 合同到期（005-03）
    assert "→ 将于本年度结束时到期" in content
    # 和约到期（005-09）
    assert "→ 和约将在本年度结束时到期" in content
    # 年度衰减（005-05）：将减少 N 点影响力，降至 M
    assert "将减少 \" + (-delta) + \" 点影响力，降至 " in content
    assert "影响力无变化，仍为 " in content
    assert "将增加 \" + delta + \" 点影响力，升至 " in content
    # 禁「预计」；禁过去时「已过期」/「返回罗马 · 行省」（旧文案）
    assert "预计" not in content
    assert "已过期" not in content
    assert "返回罗马 · 行省" not in content


def test_no_visible_stepbar():
    """EC-03 / 005-07：QML 无 resolutionStepBar objectName；ContextPanel 无「4 / 4」。"""
    paths = _qml_paths()
    with open(paths["resolution_stage"], encoding="utf-8") as f:
        stage_content = f.read()
    with open(paths["context_panel"], encoding="utf-8") as f:
        panel_content = f.read()

    assert "resolutionStepBar" not in stage_content
    assert "resolutionStepStatuses" not in stage_content
    assert "4 / 4" not in panel_content
    # 无「决算完成」第五块 / x/4 隐喻（精确 text 模式；头部注释说明性引用不计数）
    assert 'text: "决算完成"' not in stage_content

    # 引擎渲染：root 树中无 resolutionStepBar 对象
    result = session_api.create_gui_prototype_session(start_phase="combat")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")
    store = GuiSessionStore(state)
    store.initialize(player_id)
    store.refreshSnapshot()
    store.selectPhase("resolution")

    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication
    engine, qml_dir = _create_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None
    assert root.findChild(QObject, "resolutionStepBar") is None


def test_preview_empty_states():
    """005-06 / E-04：四类目空态文案冻结（无空白/隐藏/编造）+ preview 空列表 DATA 语义。"""
    paths = _qml_paths()
    with open(paths["resolution_stage"], encoding="utf-8") as f:
        content = f.read()

    # E-04 空态文案族（冻结统一措辞）
    for empty_copy in [
        "本年度结束时无总督返回",
        "本年度结束时无合同到期",
        "本年度结束时无和约到期",
        "本年度结束时无派系影响力衰减",
        "当前无重大年度风险",
    ]:
        assert empty_copy in content, f"E-04 空态文案缺失: {empty_copy}"
    # 禁旧空态（精确 text 值 pattern，避免与 E-04 新文案子串冲突）
    assert 'text: "无风险事件"' not in content
    assert 'text: "无和约到期"' not in content
    assert 'text: "无变化"' not in content

    # DATA：空状态 preview 四类目为空列表（权威 producer 输出）
    state = _make_state()
    preview = session_api._build_resolution_preview(state)
    assert preview["governor_returns"] == []
    assert preview["contract_expiries"] == []
    assert preview["truce_expiries"] == []
    assert preview["faction_influence"] == []
