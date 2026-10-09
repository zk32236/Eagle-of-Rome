# src/tests/test_gui/test_wpj_groupd_population_aftermath.py
"""WP-J Group-D-Aftermath (J-AC-04a) — PopulationStage 公示框内战后反馈行（RENDER + 静态绑定）。

冻结设计 v1.1（`02-sa-design/GroupD/` §5.1/§5.3/§6.1 L-D1/L-D2）：
- 内容并入既有公示框 `populationAnnouncement`（框内追加，非新框）。
- 逐字渲染 `sessionStore.populationOutcome`（凯旋仪式已举行 / 战后军团·停战降级军团·闲置舰队计数）。
- 框高 additive：空 → 回落基值 88；非空 → 88 + 行数*16 + spacing。
- D-2：修正混淆静态行（庆典 vs 凯旋仪式归属分离）。
No-Test-Assisted-Transition：目标态经真实生产动作 `process_population_disbandments` 到达。
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
import shiboken6  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import session_api, population_api  # noqa: E402
from src.core.entities.war import War, WarStatus  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
POP_QML = os.path.join(QML_DIR, "stages", "PopulationStage.qml")
OLD_CONFUSING_LINE = "今年举行庆典？→ 广场阶段已投票决定：是"
NEW_D2_LINE = "📢 人口阶段：🎉 庆典赞助（候选人竞选）→ 🗳️ 投票选举"
_ENGINES = []


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


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


def _find_obj(root, object_name):
    for item in _all_items(root):
        if item.objectName() == object_name:
            return item
    return None


def _texts_under(item):
    return [it.property("text") for it in _all_items(item)
            if "Text" in it.metaObject().className() and it.property("text")]


def _load_population(store, width=1440, height=900):
    app = _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("theme", theme)
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(POP_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "PopulationStage loaded with no root object"
    root = roots[0]
    root.setWidth(width)
    root.setHeight(height)
    app.processEvents()
    _ENGINES.append(engine)
    return engine, root


def _session_store(start_phase="population"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("population")
    return store, state, viewer


def _attach_resolved_war(state, commander_id, legion_numbers=()):
    war = War(
        id="wpj-gd-render-war", name="对迦太基战争", strength=5, threat_level=3,
        rewards={"treasury": 100, "land": 0, "family_prestige": 0},
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.RESOLVED
    war.set_soldier_share(20)
    war.set_triumph_commander(commander_id)
    war.set_triumph_approved(True)
    ms = state.get_military_system()
    for n in legion_numbers:
        ok, _msg = ms.recruit_legion(n)
        if ok:
            war.add_legion_number(n)
    state.get_war_system()._war_discard.append(war)
    return war


# ---------------------------------------------------------------------------
# 静态绑定断言（源码级）
# ---------------------------------------------------------------------------

def test_source_consumes_authoritative_outcome_and_fixes_d2_line():
    src = open(POP_QML, encoding="utf-8").read()
    assert "sessionStore.populationOutcome" in src, "公示框须消费权威 populationOutcome（FC-D08）"
    for needle in ("凯旋仪式", "战后军团", "停战降级军团", "闲置舰队"):
        assert needle in src, f"缺战后反馈行文案：{needle}"
    assert OLD_CONFUSING_LINE not in src, "混淆静态行必须移除（D-2）"
    assert NEW_D2_LINE in src, "D-2 修正静态行（庆典 vs 凯旋归属分离）"
    # 不新增独立兄弟块（内容并入既有框；S-2 Δ-1）
    assert '"populationAftermath"' not in src, \
        "不得新增独立兄弟块 objectName populationAftermath（S-2 Δ-1）"


# ---------------------------------------------------------------------------
# 渲染层：空态回落 88 / 非空 additive 行
# ---------------------------------------------------------------------------

def test_empty_outcome_falls_back_to_base_height():
    store, _state, _viewer = _session_store()
    assert store.populationOutcome.get("triumphs") == []
    _engine, root = _load_population(store)
    box = _find_obj(root, "populationAnnouncement")
    assert box is not None, "未找到公示框 populationAnnouncement"
    assert abs(box.height() - 88) <= 1, f"空 payload → 框高回落 88（FC-D07），实际 {box.height()}"
    texts = _texts_under(box)
    assert not any("凯旋仪式" in t for t in texts), "空 payload 不得出现凯旋行"


def test_aftermath_rows_render_and_raise_box_height():
    store, state, _viewer = _session_store()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))
    population_api.process_population_disbandments(state)   # 真实生产动作
    store._refresh_population_view()

    outcome = store.populationOutcome
    assert outcome["triumphs"], "store 必须透传权威 outcome"
    _engine, root = _load_population(store)
    box = _find_obj(root, "populationAnnouncement")
    assert box is not None
    texts = _texts_under(box)
    assert any(("凯旋仪式" in t and "已举行" in t) for t in texts), f"缺凯旋已举行行：{texts}"
    assert any(commander.name in t for t in texts), "凯旋行须含权威 commander_name"
    assert any("战后军团" in t for t in texts), f"缺战后军团计数行：{texts}"
    # additive 框高（≥ 88 + 1 行）
    assert box.height() >= 88 + 16, f"非空必须撑高（L-D1），实际 {box.height()}"
