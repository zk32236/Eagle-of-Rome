# src/tests/test_gui/test_wpfr1_stage_screens.py
"""WP-F-R1 T-F07 / T-F09 / T-F12：QML 展示面（R1-F-04 GovOps 卡删除 / R1-F-05 Dialog 过滤 + 去重）。

- T-F07  SenateStage：GovOps 卡（border #2E9D4D / 政府\n运作）缺席 + render 无空占位 + ✅ 最终通过保留
- T-F09  ForumStage：pending 买家 A 从 landActorOptions 排除、未提交买家 B 保留
         （真实 forum_api DTO 形状 + QML 函数调用，AC-F05-2/3/5）
- T-F12  ForumStage：canonical announceArea 保留 + market 区重复 Repeater 已删
         （landAllocationRows 函数保留 + WP-F-R1 KEEP 标注，AC-F05-7/8）
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
from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem

from src.api import forum_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
FORUM_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "ForumStage.qml")


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
    """经 QQmlExpression 调用 QML root 函数并取回返回值（PySide6 下 Q_RETURN_ARG 不可用）。

    PySide6 的 evaluate() 返回 (value, isUndefined) 二元组；value 为 QJSValue，toVariant 转换。
    """
    from PySide6.QtQml import QQmlExpression, QQmlEngine
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


def _invoke_list(root, method_name, *args):
    arg_src = ", ".join(repr(a) for a in args)
    ok, val = _call_qml(root, f"{method_name}({arg_src})")
    if not ok or val is None:
        return False, []
    return True, list(val)


def _invoke_bool(root, method_name, *args):
    arg_src = ", ".join(repr(a) for a in args)
    ok, val = _call_qml(root, f"{method_name}({arg_src})")
    if not ok:
        return False, None
    return True, bool(val)


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
    # 与 test_wpcr1 同款：engine 持有 mock store / theme 引用，防 Python GC 导致 QML 读到 null
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(qml_file))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_file} loaded with no root object"
    return engine, roots[0]


# ---------------------------------------------------------------------------
# SenateStage mock（results step，最小面）
# ---------------------------------------------------------------------------

class _ResultsSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, submitted=None, announcement=None, vote_results=None, parent=None):
        super().__init__(parent)
        self._submitted = submitted or []
        self._announcement = announcement or {}
        self._vote_results = vote_results or []

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return "results"

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return self._submitted

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self):
        return self._announcement

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateVoteResults(self):
        return self._vote_results

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


def test_tf07_government_operations_card_absent():
    """T-F07（AC-F04-1/2）：GovOps 卡缺席 + render 无空占位 + ✅ 最终通过保留。"""
    src = _read_qml(SENATE_QML)
    assert "#2E9D4D" not in src, "GovOps 卡唯一锚点 border #2E9D4D 必须删除"
    assert "\\u653f\\u5e9c\\n\\u8fd0\\u4f5c" not in src, "竖排「政府\\n运作」Text 必须删除"
    assert "通过法案纳入执行" not in src, "GovOps 卡内静态文案必须删除"

    store = _ResultsSenateStore(
        submitted=[
            {"id": 1, "result": "passed", "title": "公地出售", "detail": "出售 50C 公地"},
            {"id": 2, "result": "rejected", "title": "税制改革", "detail": "调整税率"},
        ],
        announcement={"enacted_proposals": [{"proposal_id": 1, "type": "land", "title": "公地出售"}]},
        vote_results=[
            {"proposal_id": 1, "support_influence": 130, "oppose_influence": 0,
             "total_influence": 130, "passed": True, "vetoed": False},
            {"proposal_id": 2, "support_influence": 0, "oppose_influence": 130,
             "total_influence": 130, "passed": False, "vetoed": False},
        ],
    )
    _engine, root = _load_qml(SENATE_QML, store)
    joined = " ".join(_texts(root))
    assert "✅ 最终通过：" in joined, "✅ 最终通过 公示必须保留（R1-F-04 不删）"
    assert "政府\n运作" not in joined
    assert "通过法案纳入执行" not in joined
    # R1-F-03 支持率展示（results 态 per-proposal 行）
    assert "通过 · 支持率 100%" in joined
    assert "未通过 · 支持率 0%" in joined


def test_tf07b_senate_support_rate_real_store_render_visible():
    """R1-F-03 真链 render 探针：真实 store 驱动至 results → SenateStage 渲染。

    断言：支持率 Text 在对象树中且可见（isVisible + height>0，防 ColumnLayout 挤压隐藏）；
    GovOps 卡缺席。DATA 侧（vote_results 透传）由证据测试断言。
    """
    from src.api import session_api
    from src.ui.gui.session_store import GuiSessionStore

    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)

    selection_map = {}
    for office in ("consul", "censor", "praetor", "quaestor", "tribune"):
        for c in store.populationCandidates:
            if c.get("office") == office:
                selection_map[office] = int(c.get("id"))
                break
    store.submitPopulationVotes(selection_map)
    store.selectPhase("senate")
    # 确定性种入 2 条公地提案（绕开 prototype 随机 consul/AI proposer 路由；
    # 投票/否决/resolve 链保持真实，propose 环节非 R1-F-03 测试面）
    state.add_senate_proposal({
        "type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05,
        "proposer_faction": "optimates", "proposer_player": "player_optimates",
        "consul_id": 1, "description": "公地出售法案 50 C", "label": "卖地法案 — 出售 50 C",
    })
    state.add_senate_proposal({
        "type": "land", "act_type": "distribution", "amount_C": 50, "percent": 0.05,
        "proposer_faction": "optimates", "proposer_player": "player_optimates",
        "consul_id": 1, "description": "公地分配法案 50 C", "label": "分地法案 — 分配 50 C",
    })
    store._refresh_senate_view()
    fb = store.doSubmitSenateVotes()
    assert fb.get("success"), fb.get("message")
    submitted = store.senateSubmittedProposals or []
    # 否决最后一个提案（仅当 ≥2 提案）——保证至少一个通过提案展示「通过 · 支持率 X%」；
    # tribune 归属随机 → 否决失败时降级空否决（resolve 仍执行）
    if len(submitted) >= 2:
        try:
            store.doSubmitSenateVetoes([int(submitted[-1]["id"])])
        except Exception:
            store.doSubmitSenateVetoes([])
    else:
        store.doSubmitSenateVetoes([])
    assert store.senateCurrentStep == "results"
    assert store.senateVoteResults, "vote_results must flow through GUI store chain"

    _engine, root = _load_qml(SENATE_QML, store)
    support_items = [
        i for i in _all_items(root)
        if isinstance(i.property("text"), str) and "支持率" in str(i.property("text"))
    ]
    assert support_items, "支持率 Text 必须在对象树中（R1-F-03 展示）"
    visible = [i for i in support_items if i.isVisible() and (i.property("height") or 0) > 0]
    assert visible, "支持率 Text 必须可见（height>0，防 ColumnLayout 挤压）"
    joined = " ".join(str(i.property("text")) for i in visible)
    assert "通过 · 支持率" in joined, f"可见支持率文案缺失: {joined}"
    joined_all = " ".join(_texts(root))
    assert "政府\n运作" not in joined_all
    assert "通过法案纳入执行" not in joined_all


# ---------------------------------------------------------------------------
# ForumStage mock（真实 DTO 形状注入 + 配置化）
# ---------------------------------------------------------------------------

class _ForumStageStore(QObject):
    forumViewChanged = Signal()

    def __init__(self, my_figures=None, requests=None, resolved=False, allocation=None,
                 result=None, parent=None):
        super().__init__(parent)
        self._my_figures = my_figures or []
        self._requests = requests or []
        self._resolved = resolved
        self._allocation = allocation or []
        self._result = result or {}

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return self._my_figures

    @Property(list, notify=forumViewChanged)
    def forumViewerLandRequests(self):
        return self._requests

    @Property(list, notify=forumViewChanged)
    def forumLandAllocation(self):
        return self._allocation

    @Property(dict, notify=forumViewChanged)
    def forumResult(self):
        return self._result

    @Property(dict, notify=forumViewChanged)
    def forumView(self):
        return {}

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self):
        return self._resolved

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self):
        return "market"

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarEvents(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumViewerContractBids(self):
        return []

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandSaleTotal(self):
        return 0

    @Property(int, notify=forumViewChanged)
    def forumLandPricePerUnit(self):
        return 10

    @Property(bool, notify=forumViewChanged)
    def forumHasActiveWar(self):
        return False

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self):
        return False

    @Slot("QVariant", "QVariant", result=dict)
    def doBuyLand(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", "QVariant", result=dict)
    def doPlaceBid(self, figure_id, contract_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doRecruitFigure(self, figure_id, amount):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", result=dict)
    def doRetireFigure(self, figure_id):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doCompleteForumStep(self):
        return {"success": False, "message": "mock"}

    @Slot("QVariant", "QVariant", result=dict)
    def doVoteTriumph(self, war_id, approved):
        return {"success": False, "message": "mock"}

    @Slot(result=dict)
    def doResolveForum(self):
        return {"success": False, "message": "mock"}


def _build_forum_state():
    config = {
        "testing": {"bypass_player_check": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "default_bid_profit_rate": 0.2,
            "project_theoretical_construction": 3,
            "project_theoretical_warranty": 10,
        },
    }
    s = GameState.create_for_testing(config)
    s.turn = GameTurn(turn_number=1, year=-282)
    s.add_player(Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN))
    s.set_turn_order(["p1"])
    s.set_current_player("p1")
    s.add_faction(Faction(id="f1", name="Faction1", treasury=1000))
    f1 = Figure.create_nobile(1, "f1", 40)
    f1.wealth = 500
    f1.update_influence()
    s.add_member(f1)
    f2 = Figure.create_eques(2, "f1", 30)
    f2.wealth = 300
    f2.update_influence()
    s.add_member(f2)
    s.get_faction("f1").member_ids = [1, 2]
    s._national_public_land = 100
    s.set_pending_land_sale_quota(100)
    return s


def test_tf09_pending_buyer_excluded_from_dialog_options():
    """T-F09（AC-F05-2/3/5）：pending 买家 A 从 landActorOptions 排除，未提交 B 保留。"""
    state = _build_forum_state()
    view = forum_api.get_forum_view(state, "p1")
    assert view["success"], view.get("message")
    my_figures = view["data"]["my_figures"]
    assert {f["id"] for f in my_figures if f["can_buy_land"]} == {1, 2}  # 首购前 A/B 均可选

    assert forum_api.buy_land(state, "p1", 1, 3)["success"] is True
    view2 = forum_api.get_forum_view(state, "p1")
    assert [r["figure_id"] for r in view2["data"]["viewer_land_requests"]] == [1]

    # 真实 DTO 形状注入 QML（my_figures + viewer_land_requests 均来自真实 get_forum_view）
    store = _ForumStageStore(
        my_figures=view2["data"]["my_figures"],
        requests=view2["data"]["viewer_land_requests"],
    )
    _engine, root = _load_qml(FORUM_QML, store)

    ok, opts = _invoke_list(root, "landActorOptions")
    assert ok, "landActorOptions must be invokable"
    ids = []
    for o in opts:
        d = _to_py(o)
        if isinstance(d, dict):
            ids.append(int(_to_py(d.get("id"))))
        elif hasattr(o, "property"):  # QJSValue 元素
            ids.append(int(_to_py(o.property("id"))))
        else:
            raise AssertionError(f"unexpected landActorOptions element: {type(o)} {o!r}")
    assert 1 not in ids, "已提交买家 A 必须从 Dialog options 排除（R1-F-05 ①）"
    assert 2 in ids, "未提交买家 B 保留可用"

    ok_a, a_pending = _invoke_bool(root, "viewerHasLandPending", 1)
    ok_b, b_pending = _invoke_bool(root, "viewerHasLandPending", 2)
    assert ok_a and a_pending is True
    assert ok_b and b_pending is False


def test_tf12_canonical_result_remains_after_duplicate_region_removal():
    """T-F12（AC-F05-7/8）：market 重复 Repeater 已删；canonical announceArea 保留并渲染。"""
    src = _read_qml(FORUM_QML)
    assert 'objectName: "announceArea"' in src, "canonical announceArea 必须保留"
    assert "function forumPublicResultText" in src, "canonical 结果文案 helper 必须保留"
    assert "model: root.landAllocationRows()" not in src, "market 区重复结果 Repeater 必须删除"
    assert "function landAllocationRows" in src, "landAllocationRows 函数保留（KEEP 标注）"
    assert "KEEP" in src, "WP-F-R1 KEEP 标注应存在"

    store = _ForumStageStore(
        resolved=True,
        allocation=[
            {"figure_id": 1, "name": "图斯库卢姆·马库斯", "requested_amount": 3,
             "allocated_amount": 3, "cost": 30, "status": "allocated"},
        ],
        result={"data": {"results": ["✅ 图斯库卢姆·马库斯 认购 3 C 公地，花费 30 塔兰特"]}},
    )
    _engine, root = _load_qml(FORUM_QML, store)
    area = root.findChild(QObject, "announceArea")
    assert area is not None
    joined = " ".join(_texts(area))
    assert "图斯库卢姆·马库斯 认购 3 C 公地" in joined, "canonical 结果必须呈现"
    # market 区无紧凑 "T" 重复措辞（🏞️ 行已删）
    all_joined = " ".join(_texts(root))
    assert "🏞️ 图斯库卢姆·马库斯 认购" not in all_joined
