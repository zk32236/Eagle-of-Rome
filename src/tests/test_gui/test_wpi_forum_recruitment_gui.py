# src/tests/test_gui/test_wpi_forum_recruitment_gui.py
"""WP-I — Forum 招募容量 GUI 平价（Attempt-3：S4）

覆盖（SA-Design §3.G / §3.M M6 / I-06 / R-I06；Task Package §16.1 T-I10）：
- T-I10a Store 只读透传：viewer_recruitment DTO 字段 → GUI Store 属性（零本地缓存）。
- T-I10b Store/action 在 remaining==0 不可提交（new distinct 经真实 API 生产链拒绝）。
- T-I10c QML 门控逻辑：recruitActionAllowed = 权威剩余槽位 或 本目标已 pending
         （同目标重提仍可用；槽位耗尽 + 未 pending → 不可用）。
- T-I10d 静态守卫（R-I06）：ForumStage.qml 只消费权威布尔/槽位，无 QML-only 容量计算。

性质：GUI 消费权威 remaining slots（不自行计算容量）；不新增玩法规则。
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

from src.api import session_api
from src.core.entities.figure import Figure
from src.ui.gui.session_store import GuiSessionStore

FORUM_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "ForumStage.qml")
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")


# ---------------------------------------------------------------------------
# 真实 GUI Store 会话（forum market 环节）
# ---------------------------------------------------------------------------

def _make_forum_store():
    """真实 GUI Store 会话：forum 阶段 market 环节（production chain）。"""
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    assert store.selectedPhaseId == "forum"
    assert store.doCompleteForumStep()["success"]
    store._refresh_forum_view()
    return store, state, viewer_id


def _force_remaining(state, faction_id, slots):
    """把 viewer 派系塑造为「权威剩余槽位 == slots」的确定性前置（test-local）。

    - 清空 viewer 派系 pending（viewer 尚未行动）；
    - 存活成员调整为 capacity − slots（按需补/标死；不破坏其他派系）。
    """
    state._forum_pending["recruitment_bids"] = [
        r for r in state._forum_pending.get("recruitment_bids", []) if r[0] != faction_id
    ]
    capacity = state.get_faction_capacity()
    _set_living(state, faction_id, capacity - slots)
    assert state.get_remaining_recruitment_slots(faction_id) == slots
    return capacity


def _set_living(state, faction_id, target):
    faction = state.get_faction(faction_id)
    guard = 0
    while faction.get_living_member_count(state) > target and guard < 200:
        guard += 1
        killed = False
        for mid in list(faction.member_ids):
            m = state.get_member(mid)
            if m is not None and not getattr(m, "is_dead", False):
                m.is_dead = True
                killed = True
                break
        if not killed:
            break
    nxt = 95000
    while faction.get_living_member_count(state) < target:
        fig = Figure.create_plebeian(nxt, faction_id, 30)
        fig.wealth = 100
        state.add_member(fig)
        if fig.id not in faction.member_ids:
            faction.member_ids.append(fig.id)
        nxt += 1
    assert faction.get_living_member_count(state) == target


# ---------------------------------------------------------------------------
# T-I10a — Store 只读透传（viewer_recruitment → 属性）
# ---------------------------------------------------------------------------

def test_ti10a_store_viewer_recruitment_passthrough():
    store, state, viewer_id = _make_forum_store()
    faction_id = state.get_player(viewer_id).faction_id

    r = store.forumRecruitment
    assert isinstance(r, dict) and r, "forumRecruitment 必须透出 DTO 字典"
    # 与权威 resolver 逐字段一致（GUI 只消费，不自算）
    assert r["capacity"] == state.get_faction_capacity()
    assert r["current_member_count"] == state.get_faction(faction_id).get_living_member_count(state)
    assert r["physical_vacancies"] == state.get_faction_physical_vacancies(faction_id)
    assert r["pending_recruitment_target_count"] == state.get_pending_recruitment_target_count(faction_id)
    assert r["remaining_recruitment_slots"] == state.get_remaining_recruitment_slots(faction_id)
    assert r["can_submit_recruitment_bid"] is (r["remaining_recruitment_slots"] > 0)

    # 逐属性回读一致
    assert store.forumRecruitmentCapacity == r["capacity"]
    assert store.forumRecruitmentCurrentMemberCount == r["current_member_count"]
    assert store.forumRecruitmentPhysicalVacancies == r["physical_vacancies"]
    assert store.forumRecruitmentPendingTargetCount == r["pending_recruitment_target_count"]
    assert store.forumRecruitmentRemainingSlots == r["remaining_recruitment_slots"]
    assert store.forumRecruitmentCanSubmit == r["can_submit_recruitment_bid"]
    assert store.forumViewerPendingRecruitmentTargetIds == state.get_pending_recruitment_target_ids(faction_id)


# ---------------------------------------------------------------------------
# T-I10b — Store/action 在 remaining==0 不可提交（生产链）
# ---------------------------------------------------------------------------

def test_ti10b_store_action_blocked_when_slots_exhausted():
    store, state, viewer_id = _make_forum_store()
    faction_id = state.get_player(viewer_id).faction_id
    _force_remaining(state, faction_id, 1)
    store._refresh_forum_view()
    assert store.forumRecruitmentRemainingSlots == 1
    assert store.forumRecruitmentCanSubmit is True

    available = store.forumAvailableFigures
    assert len(available) >= 2, "market 环节应生成多个可招募目标"
    target_x = available[0]["id"]
    target_y = available[1]["id"]

    # 占用最后槽（new distinct 经真实 API 生产链接受）
    ok = store.doRecruitFigure(target_x, 50)
    assert ok["success"] is True, ok.get("message")
    assert store.forumRecruitmentRemainingSlots == 0
    assert store.forumRecruitmentCanSubmit is False
    assert target_x in store.forumViewerPendingRecruitmentTargetIds

    # remaining==0 → 新 distinct 目标不可提交（GUI action 经 API 拒绝，非静默）
    blocked = store.doRecruitFigure(target_y, 50)
    assert blocked["success"] is False
    assert target_y not in store.forumViewerPendingRecruitmentTargetIds
    assert store.forumRecruitmentPendingTargetCount == 1  # 零新增 pending


# ---------------------------------------------------------------------------
# T-I10c — QML 门控逻辑（真实 Store + 真实 Main.qml → ForumStage）
# ---------------------------------------------------------------------------

# QGuiApplication 必须保活（否则引擎/QML 对象被 GC 失效 → sessionStore 变 null）
_QT_APP = None


def _ensure_app():
    global _QT_APP
    from PySide6.QtGui import QGuiApplication
    _QT_APP = QGuiApplication.instance() or QGuiApplication([])
    return _QT_APP


def _load_forum_stage(store):
    """加载真实 ForumStage.qml（轻量直载；对齐 test_wpfr1_stage_screens 模式）。"""
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtCore import QUrl

    app = _ensure_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(FORUM_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "ForumStage.qml loaded with no root object"
    assert roots[0].objectName() == "forumStage"
    return engine, roots[0]


def _call_qml(obj, expr_str):
    from PySide6.QtQml import QQmlExpression, QQmlEngine
    ctx = QQmlEngine.contextForObject(obj)
    if ctx is None:
        return False, None
    expr = QQmlExpression(ctx, obj, expr_str)
    val = expr.evaluate()
    if expr.hasError():
        return False, None
    if isinstance(val, tuple) and len(val) == 2:
        val = val[0]
    if hasattr(val, "toVariant"):
        val = val.toVariant()
    return True, val


def _recruit_allowed(forum_stage, figure_id):
    ok, val = _call_qml(forum_stage, f"recruitActionAllowed({int(figure_id)})")
    assert ok, "recruitActionAllowed 必须可调用（QML 未抛错）"
    return bool(val)


def test_ti10c_qml_recruit_gating_follows_authoritative_slots():
    store, state, viewer_id = _make_forum_store()
    faction_id = state.get_player(viewer_id).faction_id
    _force_remaining(state, faction_id, 1)
    store._refresh_forum_view()
    available = store.forumAvailableFigures
    assert len(available) >= 2
    target_x = available[0]["id"]
    target_y = available[1]["id"]

    _engine, forum_stage = _load_forum_stage(store)

    # (1) remaining>0 → 任意未 pending 目标可用（消费 can_submit_recruitment_bid）
    assert store.forumRecruitmentCanSubmit is True
    assert _recruit_allowed(forum_stage, target_x) is True
    assert _recruit_allowed(forum_stage, target_y) is True

    # (2) 占用最后槽 → remaining==0：已 pending 目标仍可用（同目标重提语义不变）；
    #     未 pending 的 new distinct 目标不可用。
    assert store.doRecruitFigure(target_x, 50)["success"] is True
    assert store.forumRecruitmentCanSubmit is False
    assert _recruit_allowed(forum_stage, target_x) is True      # 已 pending → 保持可用
    assert _recruit_allowed(forum_stage, target_y) is False     # 未 pending + 无槽 → 不可用
    assert _recruit_allowed(forum_stage, 999999) is False


# ---------------------------------------------------------------------------
# T-I10d — 静态守卫（R-I06）：QML 只消费权威布尔/槽位，无 QML-only 容量计算
# ---------------------------------------------------------------------------

def test_ti10d_qml_consumes_authority_no_local_capacity():
    with open(FORUM_QML, encoding="utf-8") as fh:
        src = fh.read()
    # 消费权威布尔/槽位 + 门控 helper 在位
    assert "sessionStore.forumRecruitmentCanSubmit" in src
    assert "sessionStore.forumViewerPendingRecruitmentTargetIds" in src
    assert "function recruitActionAllowed(" in src
    # 无 QML-only 容量计算（不得在 QML 复制容量表 / 调用核心 resolver / 自算槽位）
    assert "get_faction_capacity" not in src
    assert "remaining_recruitment_slots" not in src
    assert "physical_vacancies" not in src


# ---------------------------------------------------------------------------
# T-I21 — GUI 时窗门控（招募 / 竞标 / 凯旋）— WP-I-R2 §D2/D3 / I-06b
# 权威 = 单一 sessionStore.forumResolved（禁用 marketUnlocked / forumCurrentStep 作窗口判据）
# ---------------------------------------------------------------------------

def _flat(text):
    return "".join(text.split())


def _read_forum_qml():
    with open(FORUM_QML, encoding="utf-8") as fh:
        return fh.read()


def _cpp_ptr(obj):
    try:
        import shiboken6
        return shiboken6.Shiboken.getCppPointer(obj)[0]
    except Exception:
        return None


def _all_items(root_obj):
    """枚举 QQuickItem 视觉树：findChildren(QQuickItem) 拿到 Repeater 宿主项
    （含 ScrollView/ColumnLayout 等），再逐个 childItems() 穿透 Repeater 生成的项。"""
    from PySide6.QtQuick import QQuickItem
    if root_obj is None:
        return []
    seen = set()
    out = []
    pending = []
    if isinstance(root_obj, QQuickItem):
        pending.append(root_obj)
    pending.extend(root_obj.findChildren(QQuickItem))
    while pending:
        it = pending.pop()
        key = _cpp_ptr(it)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        out.append(it)
        pending.extend(it.childItems())
    return out


def _objs_with_property(root_obj, prop_name):
    """返回子树中具有指定属性的项（属性存在 → property() 非 None）。"""
    return [i for i in _all_items(root_obj) if i.property(prop_name) is not None]


def _label_text(obj):
    """取子树首个非空 text 属性（按钮标签文案）。"""
    for i in _all_items(obj):
        t = i.property("text")
        if isinstance(t, str) and t:
            return t
    return None


def test_ti21a_static_time_window_gating_present():
    """T-I21①：ForumStage.qml 招募/竞标行级门控含 !sessionStore.forumResolved；
    凯旋行改由 producer 单一权威投影门控（WP-J Group B ③ FC-B04/B06）+ 纵深守卫 + 结束态文案。"""
    src = _read_forum_qml()
    flat = _flat(src)
    # 招募行级门控（保留：同源单一窗口权威 = !sessionStore.forumResolved）
    assert _flat(
        "recruitTimeReady: root.marketUnlocked && sessionStore.canExecuteForum"
        " && !sessionStore.forumResolved"
    ) in flat
    # 竞标行级门控（保留）
    assert _flat(
        "&& !root.viewerBidForContract(modelData.id) && !sessionStore.forumResolved"
    ) in flat
    # 凯旋行级门控（WP-J Group B ③ / J-AC-03 / FC-B04/B06 取代 WP-I 旧 forumResolved 复合式）：
    # 可用性改由 producer 投影（action.state + viewer_vote）驱动，QML 零业务重建。
    assert _flat("enabledAction: rowActionable && !rowVoted") in flat
    assert _flat(
        "readonly property bool rowActionable: modelData.action !== undefined"
        " && modelData.action !== null && modelData.action.state === \"actionable\""
    ) in flat
    assert _flat(
        "readonly property bool rowVoted: modelData.viewer_vote !== null"
        " && modelData.viewer_vote !== undefined"
    ) in flat
    # 纵深守卫：招募 open/confirm、竞标 open/confirm 的 forumResolved early-return
    # （原 ≥5 的凯旋项已由 producer 投影守卫取代 ⇒ 阈值 = 4）
    assert flat.count(_flat("if (sessionStore.forumResolved) { return }")) >= 4
    # 凯旋行 inline 纵深守卫（FC-B04：已投/不可投即早返回；取代原 forumResolved 守卫）
    assert _flat("if (rowVoted) { return }") in flat
    assert _flat("if (!rowActionable) { return }") in flat
    # 结束态玩家可读文案（不变）
    assert "已结束" in src
    assert "无空位" in src
    # 无内部诊断 / raw 串（不变）
    for bad in ("INVARIANT_VIOLATION", "forumResolved="):
        assert bad not in src


def test_ti21b_runtime_time_window_gating_and_guards():
    """T-I21②③④⑤ + M5：窗口开/闭三动作可用性 + 纵深守卫 early-return + 零状态变更。"""
    store, state, viewer_id = _make_forum_store()
    faction_id = state.get_player(viewer_id).faction_id
    _force_remaining(state, faction_id, 2)
    store._refresh_forum_view()
    assert store.forumResolved is False
    available = store.forumAvailableFigures
    assert available, "market 环节应有可招募目标"
    target_x = available[0]["id"]

    app = _ensure_app()
    _engine, forum_stage = _load_forum_stage(store)

    # ② 窗口开：招募可用性与现状一致（can_submit → 未 pending 目标可用）
    assert store.forumRecruitmentCanSubmit is True
    assert _recruit_allowed(forum_stage, target_x) is True
    # ③ 窗口开：三动作共用窗口因子为真（单一权威：marketUnlocked && canExecuteForum && !forumResolved）
    _, open_factor = _call_qml(
        forum_stage,
        "marketUnlocked && sessionStore.canExecuteForum && !sessionStore.forumResolved",
    )
    assert bool(open_factor) is True, "窗口开三动作窗口因子应为真（行为与现状一致）"
    # ② 窗口开：招募行可用性与现状一致（招募按钮存在且至少一个可点）
    btns = _objs_with_property(forum_stage, "recruitEnabled")
    assert btns, "窗口开时招募按钮应存在（Repeater 项可穿透）"
    assert all(b.property("recruitTimeReady") is True for b in btns)
    assert any(b.property("recruitEnabled") is True for b in btns), "窗口开招募应可点"

    # 窗口开：纵深守卫为 no-op（不阻断正常打开）
    assert _call_qml(forum_stage, "recruitDialogFigureId = 424242")[0]
    assert _call_qml(forum_stage, "openRecruitDialog(424243, 'X', 10)")[0]
    _, v = _call_qml(forum_stage, "recruitDialogFigureId")
    assert int(v) == 424243, "窗口开 openRecruitDialog 不应被守卫阻断"

    # --- 结算：关闭时窗 ---
    r = store.doResolveForum()
    assert r["success"] is True, r.get("message")
    store._refresh_forum_view()
    app.processEvents()
    assert store.forumResolved is True
    # 前提：canExecuteForum 仍为 true（否则 3 动作早已被 canExecuteForum 禁用，非本 delta 面）
    assert store.canExecuteForum is True, "结算后 canExecute 应仍为 true（G1-lite R2-Q1/Q2 前提）"
    _, mu = _call_qml(forum_stage, "marketUnlocked")
    assert bool(mu) is True

    # ③ 窗闭：三动作窗口因子翻转为 false（canExecuteForum 仍真 ⇒ 由 !forumResolved 关闭窗口）
    _, closed_factor = _call_qml(
        forum_stage,
        "marketUnlocked && sessionStore.canExecuteForum && !sessionStore.forumResolved",
    )
    assert bool(closed_factor) is False, "窗闭三动作窗口因子应为 false"
    _, resolved_factor = _call_qml(forum_stage, "!sessionStore.forumResolved")
    assert bool(resolved_factor) is False

    # ③ 窗闭：招募行禁用（recruitTimeReady / recruitEnabled 均 false）
    btns = _objs_with_property(forum_stage, "recruitEnabled")
    assert btns, "结算后招募按钮应仍存在（available_figures 未清空）"
    for b in btns:
        assert b.property("recruitTimeReady") is False
        assert b.property("recruitEnabled") is False
    # ④ 结束态文案：玩家可读「已结束」（非「无空位」/「招募」）
    assert _label_text(btns[0]) == "已结束", "结束态文案应为玩家可读「已结束」"

    # ③ 窗闭：所有 MarketActionRow（竞标 / 凯旋 / 土地）enabledAction 均为 false
    rows = _objs_with_property(forum_stage, "enabledAction")
    assert rows, "窗口行应存在"
    for row in rows:
        assert row.property("enabledAction") is False

    # M5 纵深守卫：openRecruitDialog / openBidDialog 结算后 early-return（零状态变更）
    assert _call_qml(forum_stage, "recruitDialogFigureId = 424242")[0]
    assert _call_qml(forum_stage, "openRecruitDialog(424243, 'X', 10)")[0]
    _, v = _call_qml(forum_stage, "recruitDialogFigureId")
    assert int(v) == 424242, "结算后 openRecruitDialog 必须 early-return"

    assert _call_qml(forum_stage, "bidDialogContractId = 424242")[0]
    assert _call_qml(forum_stage, "openBidDialog(424243, 'X', 10, false, 0, 0)")[0]
    _, v = _call_qml(forum_stage, "bidDialogContractId")
    assert int(v) == 424242, "结算后 openBidDialog 必须 early-return"

    # confirmRecruitDialog 结算后不得提交（零状态变更：pending 目标数不变）
    before_pending = store.forumRecruitmentPendingTargetCount
    assert _call_qml(forum_stage, "recruitDialogFigureId = %d" % int(target_x))[0]
    assert _call_qml(forum_stage, "recruitDialogAmount = '5'")[0]
    assert _call_qml(forum_stage, "confirmRecruitDialog()")[0]
    assert store.forumRecruitmentPendingTargetCount == before_pending, (
        "结算后 confirmRecruitDialog 必须零状态变更"
    )

    # confirmBidDialog 结算后不得提交（零状态变更：viewer contract bids 不变）
    before_bids = len(store.forumViewerContractBids)
    assert _call_qml(forum_stage, "bidDialogFigureId = 1")[0]
    assert _call_qml(forum_stage, "bidDialogContractId = 1")[0]
    assert _call_qml(forum_stage, "bidDialogAmount = '5'")[0]
    assert _call_qml(forum_stage, "confirmBidDialog()")[0]
    assert len(store.forumViewerContractBids) == before_bids, (
        "结算后 confirmBidDialog 必须零状态变更"
    )
