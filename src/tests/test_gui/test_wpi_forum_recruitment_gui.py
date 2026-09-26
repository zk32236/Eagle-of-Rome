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
