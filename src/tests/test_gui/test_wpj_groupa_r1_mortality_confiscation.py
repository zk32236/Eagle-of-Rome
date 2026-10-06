# src/tests/test_gui/test_wpj_groupa_r1_mortality_confiscation.py
"""WP-J Group-A R1 / J-AC-13 (FC-15 / FC-09) — 天命死亡行「收归国库的土地/财产」明细。

层级：DATA（生产者按人供数 = CLI 转账值）+ RENDER（携带且 ≥1 渲染 / 缺或 0 不渲染）。

契约（冻结设计 R1 §4 FC-15/FC-09 / §5.2；Owner R-4 = Option 1）：
- 生产者 `MortalityService._handle_death_event` 为每名死者在 `figure_death` impact 写入
  `wealth_confiscated:int`（单位 T，源 = `Figure.wealth` 转账值）与
  `land_confiscated:int`（单位 C，源 = `Figure._land_private` 转账值）——与
  `GameState.mark_member_dead` 转账/CLI print **同源**。
- QML 仅渲染：字段存在且 ≥1 → 渲染子行；缺失/0 → 不渲染；**QML 禁重算**。
- **不改** `mark_member_dead` 的 `bool` 返回契约。

RED（实现前）：payload 无归公字段 → DATAs/RENDER 断言失败。
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
from PySide6.QtCore import QObject, QUrl, Signal, Property  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import mortality_api  # noqa: E402
from src.core.entities.entities import Faction, GameTurn  # noqa: E402
from src.core.entities.figure import Figure  # noqa: E402
from src.core.entities.player import Player, PlayerType  # noqa: E402
from src.core.game_state import GameState  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
MORTALITY_QML = os.path.join(QML_DIR, "stages", "MortalityStage.qml")


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
    """仅收集**可见**文本项（隐藏项不参与渲染证据）。"""
    out = []
    for i in _all_items(root):
        if not isinstance(i.property("text"), str):
            continue
        try:
            if not i.isVisible():
                continue
        except Exception:
            pass
        out.append(str(i.property("text")))
    return out


def _death_state(figures):
    """figures: list of (id, name, faction_id, wealth, land_private)。"""
    state = GameState.create_for_testing({
        "mortality_rules": {
            "event_deck": [{"name": "死神来了", "effect": "death", "weight": 1}],
            "event_draw_count": 1,
            "death_count": len(figures),
        }
    })
    state.turn = GameTurn(turn_number=1, year=-264)
    opt = Faction("opt", "Optimates")
    pop = Faction("pop", "Populares")
    state.add_faction(opt)
    state.add_faction(pop)
    members = {}
    for (fid, name, fac, wealth, land) in figures:
        f = Figure(fid, name, faction_id=fac, age=50)
        f.wealth = wealth
        f._land_private = land
        state.add_member(f)
        state.get_faction(fac).member_ids.append(fid)
        members[fid] = f
    state.add_player(Player("p1", "opt", PlayerType.HUMAN))
    state.set_current_player("p1")
    return state


# ---------------------------------------------------------------------------
# DATA —— 生产者按人供数 + 同源
# ---------------------------------------------------------------------------

def test_producer_writes_per_victim_confiscation_fields():
    """FC-15①：`figure_death` impact 携带 per-victim wealth/land 供数字段。"""
    state = _death_state([
        (10, "Caesar", "opt", 100, 3),
        (11, "Pompey", "pop", 0, 5),
    ])
    assert mortality_api.execute_mortality_phase(state, "p1")["success"]
    events = state.get_phase_result("mortality")["events"]
    impacts = [imp for ev in events for imp in (ev.get("impacts") or [])
               if imp.get("type") == "figure_death"]
    by_id = {imp["figure_id"]: imp for imp in impacts}
    assert set(by_id) == {10, 11}
    assert by_id[10]["wealth_confiscated"] == 100
    assert by_id[10]["land_confiscated"] == 3
    assert by_id[11]["wealth_confiscated"] == 0
    assert by_id[11]["land_confiscated"] == 5
    # 既有字段不破坏（additive）
    assert by_id[10]["figure_name"] == "Caesar"
    assert by_id[10]["faction_name"] == "Optimates"


def test_producer_confiscation_matches_state_transfer_same_source():
    """FC-15①：供数值 == `mark_member_dead` 实际转账（国库 / 国家公地增量）。"""
    state = _death_state([
        (10, "Caesar", "opt", 100, 3),
        (11, "Pompey", "pop", 40, 5),
    ])
    treasury_before = state._treasury
    land_before = state._national_public_land
    assert mortality_api.execute_mortality_phase(state, "p1")["success"]
    events = state.get_phase_result("mortality")["events"]
    impacts = [imp for ev in events for imp in (ev.get("impacts") or [])
               if imp.get("type") == "figure_death"]
    sum_wealth = sum(imp["wealth_confiscated"] for imp in impacts)
    sum_land = sum(imp["land_confiscated"] for imp in impacts)
    assert state._treasury - treasury_before == sum_wealth == 140
    assert state._national_public_land - land_before == sum_land == 8


def test_mark_member_dead_return_contract_unchanged():
    """FC-15/§5.2：`mark_member_dead` `bool` 返回契约不变。"""
    state = _death_state([(10, "Caesar", "opt", 10, 1)])
    assert state.mark_member_dead(10, transfer_land=True, transfer_wealth=True) is True
    assert state.mark_member_dead(10) is False  # 已死亡


# ---------------------------------------------------------------------------
# RENDER —— QML 仅渲染（携带且 ≥1）／缺或 0 不渲染
# ---------------------------------------------------------------------------

class _MortalityStore(QObject):
    mortalityViewChanged = Signal()

    def __init__(self, events, parent=None):
        super().__init__(parent)
        self._events = events

    @Property(list, notify=mortalityViewChanged)
    def mortalityEvents(self):
        return self._events


def _load_mortality(store):
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
    engine.load(QUrl.fromLocalFile(MORTALITY_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "MortalityStage loaded with no root object"
    return engine, roots[0]


def _event_with(wealth, land, include=True):
    imp = {"type": "figure_death", "figure_id": 10, "figure_name": "Caesar",
           "faction_id": "opt", "faction_name": "Optimates", "terminated_contracts": []}
    if include:
        imp["wealth_confiscated"] = wealth
        imp["land_confiscated"] = land
    else:
        imp.pop("wealth_confiscated", None)
        imp.pop("land_confiscated", None)
    return [{"name": "死神来了", "effect": "death", "summary": "1 人死亡，财产归公。",
             "impacts": [imp]}]


def test_render_confiscation_rows_when_present_and_ge_1():
    """FC-15②：字段存在且 ≥1 → 渲染「损失财富/土地（收归国库）」子行。"""
    store = _MortalityStore(_event_with(100, 3))
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    assert "损失财富 100 T（收归国库）" in joined, joined
    assert "损失土地 3 C（收归国库）" in joined, joined


def test_render_no_rows_when_zero():
    """FC-15②：字段为 0 → 不渲染子行。"""
    store = _MortalityStore(_event_with(0, 0))
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    assert "Caesar" in joined, "死亡行必须渲染（证明 store 已接）: " + joined
    assert "损失财富" not in joined
    assert "损失土地" not in joined


def test_render_no_rows_when_absent():
    """FC-15②：字段缺失（生产者未供数）→ 不渲染（不占位、不伪造）。"""
    store = _MortalityStore(_event_with(0, 0, include=False))
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    assert "Caesar" in joined, "死亡行必须渲染（证明 store 已接）: " + joined
    assert "损失财富" not in joined
    assert "损失土地" not in joined


def test_render_land_only_when_wealth_zero():
    """FC-15②/checklist #4：无财富有土地 → 仅渲染土地子行。"""
    store = _MortalityStore(_event_with(0, 5))
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    assert "Caesar" in joined, "死亡行必须渲染（证明 store 已接）: " + joined
    assert "损失财富" not in joined
    assert "损失土地 5 C（收归国库）" in joined
