# src/tests/test_gui/test_wpj_groupd_g7q1_anchor_order.py
"""WP-J Group-D G7/Q1 Δ-6 — 战后反馈行「渲染锚点前移」顺序断言（G7Q1 delta）。

冻结设计 v1.2（`02-sa-design/GroupD/` §5.1 / §6.1 L-D1 / Δ-6）：
- 战后反馈行（`populationAftermathRows`）渲染锚点由公示框 `populationAnnouncement` **尾部**
  前移至**框内顶部**——Group A 既有首行「✨ 选举已完成！」/「📢 人口阶段：…」**之前**
  （对齐规格 Step 0 公告位点：凯旋/解散先于庆典/选举）。
- 仅位点/顺序变更；逐字消费 `sessionStore.populationOutcome` 不变；框高 additive 不变；
  空态不造行（FC-D07）不变。

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
AFTERMATH_OBJ = 'objectName: "populationAftermathRows"'
HEADER_LINE = '"✨ 选举已完成！"'
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


def _find_text_by(root, predicate):
    for item in _all_items(root):
        if "Text" in item.metaObject().className():
            t = item.property("text")
            if isinstance(t, str) and predicate(t):
                return item
    return None


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
        id="wpj-gd-g7q1-war", name="对迦太基战争", strength=5, threat_level=3,
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
# 源码级顺序断言：锚点声明在 Group A 既有首行之前
# ---------------------------------------------------------------------------

def test_source_anchor_precedes_group_a_header():
    src = open(POP_QML, encoding="utf-8").read()
    idx_aftermath = src.index(AFTERMATH_OBJ)
    idx_header = src.index(HEADER_LINE)
    assert idx_aftermath < idx_header, (
        "Δ-6：populationAftermathRows 声明须前置于「✨ 选举已完成！」首行（框内顶部锚点）"
    )
    # 唯一锚点：不重复声明、不新增独立兄弟块（S-2 Δ-1 保持）
    assert src.count(AFTERMATH_OBJ) == 1, "populationAftermathRows 只应声明一次（单锚点）"


# ---------------------------------------------------------------------------
# 渲染层顺序断言：反馈行视觉 y 位于 Group A 既有首行之上
# ---------------------------------------------------------------------------

def test_render_aftermath_rows_above_group_a_header():
    store, state, _viewer = _session_store()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))
    population_api.process_population_disbandments(state)   # 真实生产动作
    store._refresh_population_view()

    assert store.populationOutcome.get("triumphs"), "store 必须透传权威 outcome"
    _engine, root = _load_population(store)

    aftermath = _find_obj(root, "populationAftermathRows")
    assert aftermath is not None, "未找到战后反馈行容器 populationAftermathRows"

    header = _find_text_by(
        root,
        lambda t: t.startswith("✨ 选举已完成！") or t.startswith("📢 人口阶段"),
    )
    assert header is not None, "未找到 Group A 既有首行（选举已完成 / 人口阶段）"

    triumph_line = _find_text_by(root, lambda t: "凯旋仪式" in t and "已举行" in t)
    assert triumph_line is not None, "缺凯旋已举行行"

    # 视觉锚点：反馈行（含凯旋行）位于 Group A 既有首行【之上】（y 更小 = 更靠顶部）。
    row_y = triumph_line.mapToItem(root, 0, 0).y()
    header_y = header.mapToItem(root, 0, 0).y()
    assert row_y < header_y, (
        f"Δ-6 锚点前移未生效：反馈行 y={row_y} 须 < 首行 y={header_y}（框内顶部）"
    )
    assert aftermath.mapToItem(root, 0, 0).y() < header_y, "反馈行容器须位于首行之上"


def test_empty_outcome_keeps_anchor_hidden_no_row():
    """空态（FC-D07）：不造行——锚点容器不可见，且无凯旋行。"""
    store, _state, _viewer = _session_store()
    assert store.populationOutcome.get("triumphs") == []
    _engine, root = _load_population(store)
    aftermath = _find_obj(root, "populationAftermathRows")
    assert aftermath is not None
    assert not aftermath.isVisible(), "空 payload 锚点容器不得可见（FC-D07）"
    assert _find_text_by(root, lambda t: "凯旋仪式" in t) is None, "空 payload 不得出现凯旋行"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
