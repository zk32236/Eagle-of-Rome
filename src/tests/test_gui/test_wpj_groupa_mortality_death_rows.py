# src/tests/test_gui/test_wpj_groupa_mortality_death_rows.py
"""WP-J Group-A-1 / J-AC-09 — Mortality 死亡影响行守卫修复（TDD）。

根因（G1 §1.2 / FC-10）：`MortalityStage.deathImpacts()` 以 `Array.isArray(impacts)` 作守卫，
而运行时 `impacts` 为 `QVariantList`（`Array.isArray` 恒 false）⇒ 恒返 [] ⇒ 死亡行不渲染。

层级：
- 单元（DATA）：权威 payload 契约（`events[].impacts[]` 中 `type=="figure_death"`；字段）。
- 渲染（RENDER）：`MortalityStage.qml` 死亡行可见（列表检测谓词）。

RED（实现前）：QVariantList payload 下渲染测试失败（恒返 []）。
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


def _state_with_player(config):
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-264)
    state.add_player(Player("p1", "f1", PlayerType.HUMAN))
    state.set_current_player("p1")
    return state


def _death_state(death_count=2):
    """生产链：mortality_rules 强制「死神来了」死亡事件（≥2 死者）。"""
    state = _state_with_player({
        "mortality_rules": {
            "event_deck": [{"name": "死神来了", "effect": "death", "weight": 1}],
            "event_draw_count": 1,
            "death_count": death_count,
        }
    })
    opt = Faction("opt", "Optimates")
    pop = Faction("pop", "Populares")
    state.add_faction(opt)
    state.add_faction(pop)
    f1 = Figure(10, "Caesar", faction_id="opt", age=50)
    f2 = Figure(11, "Pompey", faction_id="pop", age=55)
    state.add_member(f1)
    state.add_member(f2)
    opt.member_ids = [10]
    pop.member_ids = [11]
    return state


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


class _MortalityStore(QObject):
    """最小 mock：仅暴露 MortalityStage 消费的 mortalityEvents（QVariantList 形状）。"""

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


# ---------------------------------------------------------------------------
# 单元 / DATA —— 权威 payload 契约（生产链）
# ---------------------------------------------------------------------------

def test_death_payload_contract_multi_victim():
    """权威 payload：events[].impacts[] 含 type=figure_death；多死者全遍历。"""
    state = _death_state(death_count=2)
    resp = mortality_api.execute_mortality_phase(state, "p1")
    assert resp["success"], resp.get("message")
    events = state.get_phase_result("mortality")["events"]
    death_rows = [imp for ev in events for imp in (ev.get("impacts") or [])
                  if imp.get("type") == "figure_death"]
    assert len(death_rows) == 2, f"应有两个 figure_death impact，实际 {death_rows}"
    names = {imp["figure_name"] for imp in death_rows}
    assert names == {"Caesar", "Pompey"}
    for imp in death_rows:
        assert imp.get("faction_name")


# ---------------------------------------------------------------------------
# 渲染 / RENDER —— 死亡行可见（列表检测谓词；RED 前恒不渲染）
# ---------------------------------------------------------------------------

def test_death_rows_render_from_qvariantlist_payload():
    """J-AC-09：QVariantList payload（真实运行时形状）→ 死亡行可见。"""
    state = _death_state(death_count=2)
    assert mortality_api.execute_mortality_phase(state, "p1")["success"]
    events = state.get_phase_result("mortality")["events"]
    store = _MortalityStore(events)
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    assert "Caesar" in joined, f"死亡行（Caesar）必须渲染；实际文本 {joined}"
    assert "Pompey" in joined, f"死亡行（Pompey）必须渲染；实际文本 {joined}"
    assert "Optimates" in joined and "Populares" in joined, "派系名应随死亡行渲染"


def test_no_fabrication_when_payload_has_no_death():
    """FC-11：payload 无 figure_death → 不伪造死亡行。"""
    events = [
        {"name": "丰收", "effect": "bountiful_harvest", "summary": "风调雨顺",
         "impacts": [{"type": "active_event", "note": "harvest"}]},
    ]
    store = _MortalityStore(events)
    _engine, root = _load_mortality(store)
    joined = " ".join(_texts(root))
    # 事件摘要可见，但无任何死亡行（无 💀 明细）
    assert "丰收" not in joined or "💀" not in joined
    death_markers = [t for t in _texts(root) if t == "💀"]
    # 事件头 emoji 也为 💀（effect != death 时为 ⚡），此处 effect=bountiful_harvest → ⚡
    assert death_markers == [], "无 figure_death 时不得渲染死亡明细行（💀）"


def test_impacts_null_is_safe():
    """FC-10/FC-11：impacts 缺失/null → 不崩、不渲染行。"""
    events = [{"name": "和平", "effect": "peace", "summary": ""}]  # 无 impacts 键
    store = _MortalityStore(events)
    _engine, root = _load_mortality(store)
    assert root is not None
