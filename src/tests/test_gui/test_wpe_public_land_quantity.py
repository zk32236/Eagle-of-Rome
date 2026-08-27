# src/tests/test_gui/test_wpe_public_land_quantity.py
"""
WP-E（GUI-BETA-R1）Public Land 四载体测试（T-2）。

Slice 3 覆盖（F-E-02 production chain — 真实土地法案（political_system.py:510 权威写入）
→ buy_land → resolve_forum 分配，禁手工构造 land_allocation 注入，R-16）：
- turn_land_sale_total 稳定贯穿 resolve / 次年清除（A3.1）
- 无认购且 quota>0 → 无条件「未售作废」+ 清空（G-14 收敛，A3.3）
- land_allocation 结构化（allocated / partial / insufficient_wealth / skipped_dead）
- 财务变更（treasury + 国家公地）断言（017-07）

Slice 4/5 用例（防重 / DTO / landDialog）在后续切片追加。
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.systems.political_system import PoliticalSystem
from src.api import forum_api


def _make_state(year=-260, turn_number=5):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=year)
    return state


def _execute_sale_act(state, amount_C: int, percent: float = 100.0):
    """经政治系统 sale 分支权威写入 quota + total（真实 producer，非手工设字段）。"""
    ps = PoliticalSystem(state)
    result = ps.execute_passed_proposal({
        "type": "land",
        "act_type": "sale",
        "amount_C": amount_C,
        "percent": percent,
    })
    assert result.get("success") is True
    assert state.pending_land_sale_quota == amount_C
    assert state.turn_land_sale_total == amount_C


def _add_figure(state, fig_id: int, name: str, wealth: int, influence: int = 10, faction_id: str = "f1", class_tier="NOBILE"):
    tier = getattr(ClassTier, class_tier, ClassTier.NOBILE)
    fig = Figure(id=fig_id, name=name, wealth=wealth, faction_id=faction_id, class_tier=tier)
    fig._influence = influence
    state.add_member(fig)
    return fig


# ---------------------------------------------------------------------------
# 1. turn_land_sale_total 载体（A3.1 / A3.2）
# ---------------------------------------------------------------------------

def test_sale_act_writes_total_parallel():
    """sale 法案 → quota + total 双写入（political_system.py:510 并行写）。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    assert state.turn_land_sale_total == 300
    assert state.pending_land_sale_quota == 300


def test_total_stable_through_resolve():
    """total 稳定贯穿 resolve（历史事实载体）；quota 归零。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Marcus", wealth=5000)
    state.add_forum_action("land_purchases", (1, 100))

    result = forum_api.resolve_forum(state)
    assert result["success"] is True
    # total 保留（resolve 后仍可读）
    assert state.turn_land_sale_total == 300
    # quota 已清
    assert state.pending_land_sale_quota == 0


def test_total_cleared_on_year_advance():
    """turn 语义：年度滚轮 → total 作废（_commit_settlement A2 段清除）。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    assert state.turn_land_sale_total == 300

    state.advance_year()
    assert state.turn_land_sale_total == 0


# ---------------------------------------------------------------------------
# 2. 无认购 → 无条件配额处置（G-14 收敛，A3.3）
# ---------------------------------------------------------------------------

def test_no_purchase_clears_quota_with_unsold_message():
    """无认购且 quota>0 → 「未售作废」+ clear（跨年残留收敛）。"""
    state = _make_state()
    _execute_sale_act(state, 200)

    result = forum_api.resolve_forum(state)
    assert result["success"] is True
    assert any("未售" in r for r in result["data"]["results"])
    assert any("200" in r for r in result["data"]["results"])
    assert state.pending_land_sale_quota == 0
    # 结构化 allocation 为空
    assert result["data"]["land_allocation"] == []


def test_no_quota_no_unsold_message():
    """quota=0 且无认购 → 无「未售作废」噪声。"""
    state = _make_state()
    result = forum_api.resolve_forum(state)
    assert result["success"] is True
    assert not any("未售" in r for r in result["data"]["results"])


# ---------------------------------------------------------------------------
# 3. land_allocation 结构化（L12 partial / L8 insufficient / 竞争排序 L13）
# ---------------------------------------------------------------------------

def test_allocation_allocated_status():
    """全量认购 → status=allocated + 财务变更（017-07）。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Marcus", wealth=5000)
    state.add_forum_action("land_purchases", (1, 100))

    treasury_before = state.treasury
    land_before = state.get_national_public_land()
    result = forum_api.resolve_forum(state)

    allocs = result["data"]["land_allocation"]
    assert len(allocs) == 1
    row = allocs[0]
    assert row["figure_id"] == 1
    assert row["name"] == "Marcus"
    assert row["requested_amount"] == 100
    assert row["allocated_amount"] == 100
    assert row["cost"] == 100 * state.get_economic_rule("land_price_per_unit", 10)
    assert row["status"] == "allocated"
    # 财务变更：国库 + cost；国家公地 -allocated
    assert state.treasury == treasury_before + row["cost"]
    assert state.get_national_public_land() == land_before - 100


def test_allocation_partial_truncation():
    """L12：请求 > 剩余配额 → status=partial（权威分配截断）。"""
    state = _make_state()
    _execute_sale_act(state, 50)
    fig = _add_figure(state, 1, "Marcus", wealth=5000)
    state.add_forum_action("land_purchases", (1, 100))  # 请求 100 > 配额 50

    result = forum_api.resolve_forum(state)

    row = result["data"]["land_allocation"][0]
    assert row["requested_amount"] == 100
    assert row["allocated_amount"] == 50
    assert row["status"] == "partial"


def test_allocation_insufficient_wealth():
    """L8：财富不足 → status=insufficient_wealth + 显式拒绝文案。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    # 财富不足一单位价格（单价 10）→ max_buy_by_wealth=0 → insufficient_wealth
    fig = _add_figure(state, 1, "Poor Marcus", wealth=5)
    state.add_forum_action("land_purchases", (1, 100))

    result = forum_api.resolve_forum(state)

    row = result["data"]["land_allocation"][0]
    assert row["status"] == "insufficient_wealth"
    assert row["allocated_amount"] == 0
    assert any("资金不足" in r for r in result["data"]["results"])


def test_allocation_skipped_dead():
    """已死亡人物请求 → status=skipped_dead。"""
    state = _make_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Dead Marcus", wealth=5000)
    fig.is_dead = True
    state.add_forum_action("land_purchases", (1, 100))

    result = forum_api.resolve_forum(state)

    row = result["data"]["land_allocation"][0]
    assert row["status"] == "skipped_dead"
    assert row["allocated_amount"] == 0


def test_allocation_competition_influence_order():
    """L13：多请求竞争 → 影响力高者优先分配（quota 截断时）。"""
    state = _make_state()
    _execute_sale_act(state, 100)
    high = _add_figure(state, 1, "High Influence", wealth=5000, influence=80)
    low = _add_figure(state, 2, "Low Influence", wealth=5000, influence=10)
    state.add_forum_action("land_purchases", (1, 100))
    state.add_forum_action("land_purchases", (2, 100))

    result = forum_api.resolve_forum(state)

    allocs = {a["figure_id"]: a for a in result["data"]["land_allocation"]}
    # 高影响力拿满剩余 100；低影响力请求在配额耗尽后被循环跳过（无 allocation 行，
    # 与既有 break 语义一致——冻结 status 词表无「no_quota」类别，不发明新状态）
    assert allocs[1]["allocated_amount"] == 100
    assert allocs[1]["status"] == "allocated"
    assert 2 not in allocs


# ---------------------------------------------------------------------------
# 4. Slice 4 — buy_land 防重 + DTO 四字段 + place_bid 防重（A4.1/A4.2/A4.3）
# ---------------------------------------------------------------------------


def _make_player_state(player_id="player_1", faction_id="f1"):
    """含 HUMAN 玩家 + 派系 + 角色的 forum 前置状态。"""
    from src.core.entities.player import Player, PlayerType
    from src.core.entities.entities import Faction

    state = _make_state()
    state.config._config["testing"] = {"bypass_player_check": True}
    state._players[player_id] = Player(player_id=player_id, faction_id=faction_id, player_type=PlayerType.HUMAN)
    state._factions[faction_id] = Faction(id=faction_id, name="F1")
    return state


def test_buy_land_duplicate_rejected():
    """L10：同人物重复认购 → 第二条被显式拒绝（pending 恰一条）。"""
    state = _make_player_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Marcus", wealth=5000, faction_id="f1")
    state._factions["f1"].member_ids.append(1)

    ok1 = forum_api.buy_land(state, "player_1", 1, 100)
    assert ok1["success"] is True
    dup = forum_api.buy_land(state, "player_1", 1, 50)
    assert dup["success"] is False
    assert "已提交公地认购请求" in dup["message"]
    pending = state.get_forum_pending()
    assert len(pending["land_purchases"]) == 1


def test_buy_land_duplicate_allows_different_figure():
    """不同人物可各自提交（防重按 figure 粒度）。"""
    state = _make_player_state()
    _execute_sale_act(state, 300)
    fig1 = _add_figure(state, 1, "Marcus", wealth=5000, faction_id="f1")
    fig2 = _add_figure(state, 2, "Brutus", wealth=5000, faction_id="f1")
    state._factions["f1"].member_ids = [1, 2]

    assert forum_api.buy_land(state, "player_1", 1, 100)["success"] is True
    assert forum_api.buy_land(state, "player_1", 2, 100)["success"] is True
    pending = state.get_forum_pending()
    assert len(pending["land_purchases"]) == 2


def test_buy_land_validation_chain_preserved():
    """L7/L8/L9：非法 quantity / 财富不足 / 错误 actor-figure 显式拒绝（校验链保持）。"""
    state = _make_player_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Marcus", wealth=100, faction_id="f1")
    state._factions["f1"].member_ids.append(1)

    # L7 非法 quantity（0 / 负）
    assert forum_api.buy_land(state, "player_1", 1, 0)["success"] is False
    assert forum_api.buy_land(state, "player_1", 1, -5)["success"] is False
    # L8 财富不足（100 T < 100*10）
    assert forum_api.buy_land(state, "player_1", 1, 100)["success"] is False
    # L9 错误 actor/figure（figure 不属于玩家派系）
    other = _add_figure(state, 2, "Enemy", wealth=9999, faction_id="f2")
    state._factions["f2"] = type(state._factions["f1"])(id="f2", name="F2")
    assert forum_api.buy_land(state, "player_1", 2, 10)["success"] is False


def test_forum_view_dto_new_fields():
    """A4.2：DTO 新增 land_sale_total / land_price_per_unit / viewer_land_requests / land_allocation。"""
    state = _make_player_state()
    _execute_sale_act(state, 300)
    fig = _add_figure(state, 1, "Marcus", wealth=5000, faction_id="f1")
    state._factions["f1"].member_ids.append(1)
    forum_api.buy_land(state, "player_1", 1, 80)

    result = forum_api.get_forum_view(state, "player_1")
    assert result["success"] is True
    data = result["data"]
    assert data["land_sale_total"] == 300
    assert data["land_sale_quota"] == 300
    assert data["land_price_per_unit"] == state.get_economic_rule("land_price_per_unit", 10)
    # viewer 作用域 pending（figure.faction_id == viewer.faction_id）
    assert data["viewer_land_requests"] == [{"figure_id": 1, "requested_amount": 80}]
    # resolve 后结构化回读
    forum_api.resolve_forum(state)
    view2 = forum_api.get_forum_view(state, "player_1")
    allocs = view2["data"]["land_allocation"]
    assert len(allocs) == 1
    assert allocs[0]["figure_id"] == 1
    assert allocs[0]["status"] == "allocated"


def test_viewer_land_requests_faction_scoped():
    """viewer_land_requests 按 viewer 派系过滤（Q-L7 缺口）。"""
    from src.core.entities.player import Player, PlayerType
    from src.core.entities.entities import Faction

    state = _make_state()
    state.config._config["testing"] = {"bypass_player_check": True}
    state._players["p1"] = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state._players["p2"] = Player(player_id="p2", faction_id="f2", player_type=PlayerType.HUMAN)
    state._factions["f1"] = Faction(id="f1", name="F1")
    state._factions["f2"] = Faction(id="f2", name="F2")
    _execute_sale_act(state, 300)
    fig_a = _add_figure(state, 1, "A", wealth=5000, faction_id="f1")
    fig_b = _add_figure(state, 2, "B", wealth=5000, faction_id="f2")
    state._factions["f1"].member_ids = [1]
    state._factions["f2"].member_ids = [2]
    forum_api.buy_land(state, "p1", 1, 30)
    forum_api.buy_land(state, "p2", 2, 40)

    view_p1 = forum_api.get_forum_view(state, "p1")["data"]
    view_p2 = forum_api.get_forum_view(state, "p2")["data"]
    assert view_p1["viewer_land_requests"] == [{"figure_id": 1, "requested_amount": 30}]
    assert view_p2["viewer_land_requests"] == [{"figure_id": 2, "requested_amount": 40}]


def test_place_bid_duplicate_rejected():
    """E-G7-07：同 (contract_id, figure_id) 重复出价 → 显式拒绝。"""
    from src.core.entities.contract import ContractType, ContractStatus

    state = _make_player_state()
    contract = state.create_contract(ContractType.TAX_FARMING, 1, 100, 1)
    contract.status = ContractStatus.BUDGETED
    fig = _add_figure(state, 1, "Eques Marcus", wealth=5000, faction_id="f1", class_tier="EQUES")
    state._factions["f1"].member_ids.append(1)

    ok = forum_api.place_bid(state, "player_1", 1, contract.id, 120, 0.2)
    assert ok["success"] is True
    dup = forum_api.place_bid(state, "player_1", 1, contract.id, 130, 0.2)
    assert dup["success"] is False
    assert "已对本合同出价" in dup["message"]
    pending = state.get_forum_pending()
    assert len(pending["contract_bids"]) == 1


# ---------------------------------------------------------------------------
# 5. Slice 5 — Store 只读属性 + landDialog 数量交互（A5.1/A5.2）
# ---------------------------------------------------------------------------


def _make_forum_store():
    """真实 GUI Store 会话：mortality→revenue→forum 全链推进（production chain）。"""
    from src.api import session_api
    from src.ui.gui.session_store import GuiSessionStore

    result = session_api.create_gui_prototype_session()
    assert result["success"]
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)

    assert store.doExecuteMortality()["success"]
    assert store.doAdvanceMortality()["success"]
    assert store.doExecuteRevenue()["success"]
    assert store.doAdvanceRevenue()["success"]
    assert store.currentPhaseId == "forum"
    return store, state, viewer_id


def test_store_land_properties_read_dto():
    """A5.1：四个新只读属性均从 _forum_view 读取（E-11 无 QML 本地状态）。"""
    store, state, viewer_id = _make_forum_store()
    store._refresh_forum_view()

    assert store.forumLandSaleTotal == 0
    assert store.forumLandPricePerUnit == state.get_economic_rule("land_price_per_unit", 10)
    assert store.forumViewerLandRequests == []
    assert store.forumLandAllocation == []

    # 写入 sale 法案 → 刷新 → 属性随 DTO 更新
    from src.core.systems.political_system import PoliticalSystem
    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 300, "percent": 100.0,
    })["success"]
    store._refresh_forum_view()
    assert store.forumLandSaleTotal == 300
    assert store.forumLandQuota == 300


def test_land_quantity_production_dto():
    """landDialog quantity>1 → 生产 DTO requested_amount（L5/L6，经真实 doBuyLand 链）。"""
    from src.core.systems.political_system import PoliticalSystem

    store, state, viewer_id = _make_forum_store()
    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 500, "percent": 100.0,
    })["success"]

    # viewer 派系首个可用人物（需富足）
    viewer_faction = state.get_player(viewer_id).faction_id
    fig = next((m for m in state.get_living_members() if m.faction_id == viewer_faction and m.wealth >= 5000), None)
    if fig is None:
        from src.core.entities.figure import Figure
        fig = Figure(id=9001, name="Rich Marcus", wealth=50000, faction_id=viewer_faction)
        state.add_member(fig)
        state.get_faction(viewer_faction).member_ids.append(9001)
        fig_id = 9001
    else:
        fig_id = fig.id

    store._refresh_forum_view()
    feedback = store.doBuyLand(fig_id, 25)  # quantity=25（对话框确认路径）
    assert feedback["success"], feedback.get("message")

    # 生产 DTO：viewer_land_requests 反映 quantity
    requests = store.forumViewerLandRequests
    assert any(r["figure_id"] == fig_id and r["requested_amount"] == 25 for r in requests)
    # pending 可追踪（017-04）
    assert any(r["figure_id"] == fig_id for r in store.forumViewerLandRequests)


def test_land_submit_disables_action_via_pending():
    """提交后 pending 可追踪 → QML enabledAction 依赖 viewer pending 禁用（017-04）。"""
    from src.core.systems.political_system import PoliticalSystem

    store, state, viewer_id = _make_forum_store()
    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 300, "percent": 100.0,
    })["success"]

    viewer_faction = state.get_player(viewer_id).faction_id
    fig = next((m for m in state.get_living_members() if m.faction_id == viewer_faction and m.wealth >= 5000), None)
    fig_id = fig.id if fig else None
    if fig_id is None:
        from src.core.entities.figure import Figure
        fig = Figure(id=9002, name="Rich Brutus", wealth=50000, faction_id=viewer_faction)
        state.add_member(fig)
        state.get_faction(viewer_faction).member_ids.append(9002)
        fig_id = 9002

    store._refresh_forum_view()
    assert store.doBuyLand(fig_id, 10)["success"]

    # viewer pending 存在 → enabledAction 条件（!viewerHasLandPending）为 False
    pending = store.forumViewerLandRequests
    assert any(r["figure_id"] == fig_id for r in pending)


def test_resolve_then_allocation_stable_after_refresh():
    """resolve 后 allocation 行稳定 + 刷新/重入收敛（L16；无 QML 本地残留）。"""
    from src.core.systems.political_system import PoliticalSystem
    from src.api import forum_api

    store, state, viewer_id = _make_forum_store()
    ps = PoliticalSystem(state)
    assert ps.execute_passed_proposal({
        "type": "land", "act_type": "sale", "amount_C": 300, "percent": 100.0,
    })["success"]

    viewer_faction = state.get_player(viewer_id).faction_id
    fig = next((m for m in state.get_living_members() if m.faction_id == viewer_faction and m.wealth >= 5000), None)
    fig_id = fig.id if fig else None
    if fig_id is None:
        from src.core.entities.figure import Figure
        fig = Figure(id=9003, name="Rich Cato", wealth=50000, faction_id=viewer_faction)
        state.add_member(fig)
        state.get_faction(viewer_faction).member_ids.append(9003)
        fig_id = 9003

    store._refresh_forum_view()
    assert store.doBuyLand(fig_id, 50)["success"]
    result = forum_api.resolve_forum(state)
    assert result["success"]

    # 刷新后 allocation 从 DTO 回读（E-11）
    store._refresh_forum_view()
    allocs = store.forumLandAllocation
    assert len(allocs) >= 1
    row = next(a for a in allocs if a["figure_id"] == fig_id)
    assert row["allocated_amount"] == 50
    assert row["status"] == "allocated"
    # 重入刷新 → 稳定（无 QML 本地残留）
    store._refresh_forum_view()
    assert store.forumLandAllocation == allocs
    # total 事实保留
    assert store.forumLandSaleTotal == 300


def test_my_figures_dto_carries_can_buy_land():
    """017：actor 选择行数据源 = DTO can_buy_land 权威布尔（QML 不重算资格）。

    冻结设计 §B.2：选择面只读消费 my_figures.can_buy_land（forum_api 权威），
    禁 QML 从 class/wealth 重建资格；无 eligible 时公地行禁用（enabledAction 依赖）。
    """
    from src.core.entities.player import Player, PlayerType
    from src.core.entities.entities import Faction
    from src.api import forum_api

    state = _make_state()
    state.add_player(Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN))
    state.add_faction(Faction(id="f1", name="F1"))
    _add_figure(state, 1, "Marcus", wealth=5000, faction_id="f1")
    _add_figure(state, 2, "Poor Lucius", wealth=0, faction_id="f1")

    view = forum_api.get_forum_view(state, "p1")
    assert view["success"]
    rows = {f["id"]: f for f in view["data"]["my_figures"]}
    assert rows[1]["can_buy_land"] is True
    assert rows[2]["can_buy_land"] is False


def test_land_quantity_invalid_rejected():
    """L7：非法 quantity 经 API 拒绝 → 显式反馈（L11）。"""
    store, state, viewer_id = _make_forum_store()
    viewer_faction = state.get_player(viewer_id).faction_id
    fig = next((m for m in state.get_living_members() if m.faction_id == viewer_faction), None)
    if fig is None:
        return  # 无可用人物，跳过（负向由 API 层用例覆盖）

    feedback = store.doBuyLand(fig.id, 0)
    assert feedback["success"] is False
    feedback2 = store.doBuyLand(fig.id, -3)
    assert feedback2["success"] is False


# ---------------------------------------------------------------------------
# 6. Slice 5 — RENDER（ForumStage objectName 断言）
# ---------------------------------------------------------------------------


def _create_forum_qml_engine(store):
    """加载真实 Main.qml 并选择 forum 阶段（对齐 test_qml_startup 模式）。"""
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


def test_render_public_land_row_and_dialog_exist():
    """RENDER：公地认购行 + landDialog 存在（ForumStage）。"""
    import os
    from PySide6.QtCore import QUrl, QObject
    from PySide6.QtGui import QGuiApplication

    store, state, viewer_id = _make_forum_store()
    engine, qml_dir = _create_forum_qml_engine(store)
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]
    assert root is not None

    assert root.findChild(QObject, "forumStage") is not None
    # 公地认购行（新状态机 objectName）
    assert root.findChild(QObject, "publicLandPurchaseRow") is not None
    # landDialog 本体存在（Dialog 组件）
    land_dialog = root.findChild(QObject, "landDialog")
    assert land_dialog is not None, "landDialog not found"
    # 打开对话框 → contentItem 创建 → 数量输入框存在（IntValidator 1..999 由 QML 声明）
    from PySide6.QtCore import QMetaObject, Qt
    forum_stage = root.findChild(QObject, "forumStage")
    # WP-E R4（017）：openLandDialog 0 参化（选人移入 Dialog，入口无需传 figure）
    invoked = QMetaObject.invokeMethod(
        forum_stage,
        "openLandDialog",
        Qt.DirectConnection,
    )
    assert invoked is True, "openLandDialog not invokable"
    QGuiApplication.processEvents()
    assert land_dialog.property("opened") is True, "landDialog did not open"
    land_field = root.findChild(QObject, "landAmountField")
    assert land_field is not None, "landAmountField not found after opening landDialog"
