# src/tests/test_gui/test_wpj_groupa_phase_steps.py
"""WP-J Group-A-2 / J-AC-10 — 六阶段子环节步骤条状态保真（TDD）。

层级：
- 单元（DATA）：各阶段 `get_*_view().steps` 权威步骤读模型（键/顺序/词表/谓词/current 基数）。
- 集成：`GuiSessionStore.phaseSteps` 透传（选中相位作用域 + notify）。
- 渲染：`StepBar.qml` 消费 `{key,label,state}` 四态。

契约（冻结设计 §2.2 / §4 FC-01..FC-08）：
- FC-02 shape: steps = [{key:str,label:str,state:enum}]，升序，key 唯一
- FC-03 词表: {todo,current,complete,not_applicable}，每步恰一值，相位内 current <= 1
- FC-04 基数/键: mortality[execute] / revenue[confirm] / forum[retirement,market] /
                population[campaign,vote] / senate[proposal,senate_vote,tribune_veto] /
                combat = max(3,N) 战争派生槽（R1 FC-16；无 advance）
- FC-06 公示区不进步骤条；FC-07 Mortality 无「查看事件结果」伪步骤
- FC-08 QML 零重建：Store 只透传

RED（实现前）：六阶段步骤读模型不存在 → 全部失败。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import shiboken6  # noqa: E402
from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import (  # noqa: E402
    combat_api,
    forum_api,
    mortality_api,
    revenue_api,
    senate_api,
    session_api,
)
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
STEPBAR_QML = os.path.join(QML_DIR, "components", "StepBar.qml")

EXPECTED_KEYS = {
    "mortality": ["execute"],
    "revenue": ["confirm"],
    "forum": ["retirement", "market"],
    "population": ["campaign", "vote"],
    "senate": ["proposal", "senate_vote", "tribune_veto"],
    # R1 FC-16：Combat 槽位由可执行战争数 N 派生（war_k）；原型会话无战争 → N=0 → 3 槽。
    "combat": ["war_1", "war_2", "war_3"],
}
VALID_STATES = {"todo", "current", "complete", "not_applicable"}


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


def _prototype(start_phase):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    return state, viewer_id


def _view(phase_id, state, viewer_id):
    return {
        "mortality": lambda: mortality_api.get_mortality_view(state, viewer_id)["data"],
        "revenue": lambda: revenue_api.get_revenue_view(state, viewer_id)["data"],
        "forum": lambda: forum_api.get_forum_view(state, viewer_id)["data"],
        "population": lambda: session_api.get_population_view(state, viewer_id)["data"],
        "senate": lambda: senate_api.get_senate_view(state, viewer_id)["data"],
        "combat": lambda: combat_api.get_combat_view(state, viewer_id)["data"],
    }[phase_id]()


# ---------------------------------------------------------------------------
# 单元 / DATA —— 各阶段 steps 读模型
# ---------------------------------------------------------------------------

def test_mortality_steps_single_execute_and_pseudo_step_removed():
    """FC-04/FC-07：Mortality 仅 [execute]；无「查看事件结果」伪步骤。"""
    state, viewer_id = _prototype("mortality")
    view = mortality_api.get_mortality_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["execute"]
    labels = " ".join(s["label"] for s in steps)
    assert "执行天命" in labels
    assert "查看事件结果" not in labels, "FC-07：伪步骤必须移除"
    assert steps[0]["state"] == "current"  # can_execute == True
    # 执行后 → complete（result 存在）
    assert state is not None
    assert mortality_api.execute_mortality_phase(state, viewer_id)["success"]
    view2 = mortality_api.get_mortality_view(state, viewer_id)["data"]
    assert view2["steps"][0]["state"] == "complete"


def test_revenue_steps_single_confirm():
    """FC-04：Revenue 仅 [confirm]。"""
    state, viewer_id = _prototype("revenue")
    view = revenue_api.get_revenue_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["confirm"]
    assert view["can_execute"] is True
    assert steps[0]["state"] == "current"
    assert revenue_api.execute_revenue_phase(state, viewer_id)["success"]
    view2 = revenue_api.get_revenue_view(state, viewer_id)["data"]
    assert view2["steps"][0]["state"] == "complete"


def test_forum_steps_progression_retirement_to_market():
    """FC-04/FC-05：Forum [retirement, market]；retirement current → complete，market current。"""
    state, viewer_id = _prototype("forum")
    view = forum_api.get_forum_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["retirement", "market"]
    assert view["current_step"] == "retirement"
    assert steps[0]["state"] == "current"
    assert steps[1]["state"] == "todo"
    # 完成解雇 → market
    assert forum_api.open_market(state, viewer_id)["success"]
    view2 = forum_api.get_forum_view(state, viewer_id)["data"]
    assert view2["current_step"] == "market"
    by_key = {s["key"]: s["state"] for s in view2["steps"]}
    assert by_key["retirement"] == "complete"
    assert by_key["market"] == "current"


def test_population_steps_keys_and_current_invariant():
    """FC-04：Population [campaign, vote]；current 键 == view.current_step。"""
    state, viewer_id = _prototype("population")
    view = session_api.get_population_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["campaign", "vote"]
    currents = [s["key"] for s in steps if s["state"] == "current"]
    if view["current_step"] in ("campaign", "vote"):
        assert currents == [view["current_step"]]


def test_senate_steps_keys_and_current_invariant():
    """FC-04：Senate [proposal, senate_vote, tribune_veto]；current 键 == view.current_step。"""
    state, viewer_id = _prototype("senate")
    view = senate_api.get_senate_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["proposal", "senate_vote", "tribune_veto"]
    currents = [s["key"] for s in steps if s["state"] == "current"]
    if view["current_step"] in ("proposal", "senate_vote", "tribune_veto"):
        assert currents == [view["current_step"]]


def test_combat_steps_r1_war_derived_model():
    """FC-16（R1）：Combat steps = max(3,N) 战争派生（war_k）；无 advance；current_step 保留。

    原型会话无活跃战争 → N=0 → 3 槽全 not_applicable（R-3③）；无 current。
    """
    state, viewer_id = _prototype("combat")
    view = combat_api.get_combat_view(state, viewer_id)["data"]
    steps = view["steps"]
    assert [s["key"] for s in steps] == ["war_1", "war_2", "war_3"]
    assert all(s["state"] == "not_applicable" for s in steps)
    assert "advance" not in [s["key"] for s in steps]
    assert "current_step" in view


def test_six_phase_steps_shape_vocabulary_and_cardinality():
    """FC-02/FC-03：六阶段 shape/词表/唯一键/升序/current<=1。"""
    for phase_id in EXPECTED_KEYS:
        state, viewer_id = _prototype(phase_id)
        view = _view(phase_id, state, viewer_id)
        steps = view["steps"]
        assert isinstance(steps, list) and steps, f"{phase_id}: steps 必须非空"
        keys = [s["key"] for s in steps]
        assert keys == EXPECTED_KEYS[phase_id], f"{phase_id}: 键/顺序不符 {keys}"
        assert len(keys) == len(set(keys)), f"{phase_id}: key 重复"
        for s in steps:
            assert set(s.keys()) >= {"key", "label", "state"}, f"{phase_id}: 缺字段 {s}"
            assert isinstance(s["label"], str) and s["label"], f"{phase_id}: label 空 {s}"
            assert s["state"] in VALID_STATES, f"{phase_id}: 词表外 {s['state']}"
        currents = [s for s in steps if s["state"] == "current"]
        assert len(currents) <= 1, f"{phase_id}: current > 1"
        # FC-06：公示区不得作为步骤节点
        assert not any("公示" in s["label"] for s in steps), f"{phase_id}: 公示区不得进步骤条"


def test_store_phase_steps_scoped_to_selected_phase():
    """FC-01/FC-08：Store.phaseSteps 透传选中相位的权威 steps。"""
    state, viewer_id = _prototype("forum")
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    store.selectPhase("forum")
    steps = store.phaseSteps
    assert [s["key"] for s in steps] == ["retirement", "market"]
    # 切换到非实现相位或无 steps 相位 → 空（不造步骤，FC-03/FC-06）
    store.selectPhase("resolution")
    assert store.phaseSteps == []


# ---------------------------------------------------------------------------
# 渲染 —— StepBar 消费 {key,label,state}
# ---------------------------------------------------------------------------

def test_stepbar_renders_four_states():
    """StepBar.qml 消费步骤模型四态：todo/current/complete/not_applicable。"""
    app = _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("theme", theme)
    engine._test_refs = theme

    comp = QQmlComponent(engine)
    comp.loadUrl(QUrl.fromLocalFile(STEPBAR_QML))
    assert not comp.isError(), comp.errorString()
    steps = [
        {"key": "a", "label": "步骤A", "state": "complete"},
        {"key": "b", "label": "步骤B", "state": "current"},
        {"key": "c", "label": "步骤C", "state": "todo"},
        {"key": "d", "label": "步骤D", "state": "not_applicable"},
    ]
    bar = comp.createWithInitialProperties({"steps": steps})
    assert bar is not None, comp.errorString()
    app.processEvents()
    joined = " ".join(_texts(bar))
    for label in ("步骤A", "步骤B", "步骤C", "步骤D"):
        assert label in joined, f"步骤标签缺失: {label}；实际 {joined}"
    # complete 呈现 ✓；not_applicable 无数字/✓（muted）
    texts = _texts(bar)
    assert "✓" in texts
    assert all(t != "4" for t in texts), "not_applicable 不应显示编号"
