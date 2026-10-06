# src/tests/test_gui/test_wpj_groupa_r1_combat_steps.py
"""WP-J Group-A R1 / J-AC-14 (FC-16) — 战斗步骤条 = 可执行战争「占位→实名」进度。

层级：DATA（`get_combat_view().steps` 读模型）+ 集成（GuiSessionStore 透传）。

契约（冻结设计 R1 §4 FC-16 / §5.3；Owner S-2 R-2/R-3）：
- 槽数 = `max(3, N)`（N≤3→3；N>3→N 不封顶）。
- N = `len(resolved_wars) + len(_actionable_wars) + len(无存活指挥官的 active 战争 ∉ resolved_wars)`
  （含无指挥官自动跳过者）。
- 槽 k≤N：处理前 label=「可执行战争k」state=todo；处理后 label=该场战争名 state=complete（k 映射处理序 resolved_wars[k-1]）。
- `current` = 最低序 todo 槽（「下一空槽」）；无 todo → 无 current。
- 槽 N<k≤max(3,N)：not_applicable（灰）。
- N=0 → 全槽 not_applicable；**无 advance（推进决算）步骤**；`current_step` 相位内部机保留。

Transition Owner / No-Test-Assisted：状态一律经真实生产动作（`select_war` / `do_combat_action` /
`auto_resolve_combat`→`_skip_all_unassigned`）到达；禁直置 `steps`。

RED（实现前）：Combat 固定 `[select,action,result,advance]` → 全部失败。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import combat_api  # noqa: E402
from src.core.entities.entities import Faction, GameTurn  # noqa: E402
from src.core.entities.figure import Figure  # noqa: E402
from src.core.entities.player import Player, PlayerType  # noqa: E402
from src.core.entities.war import War, WarType, WarStatus  # noqa: E402
from src.core.game_state import GameState  # noqa: E402
from src.core.systems.military_system import MilitarySystem  # noqa: E402
from src.core.systems.war_system import WarSystem  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

VALID_STATES = {"todo", "current", "complete", "not_applicable"}


def _combat_state(wars_spec):
    """wars_spec: list of (war_id, war_name, commander_id_or_None)。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)

    for cid in sorted({c for (_, _, c) in wars_spec if c is not None}):
        f = Figure(id=cid, name="C%d" % cid, faction_id="optimates", age=40)
        f.martial = 6
        state.add_member(f)
        faction.member_ids.append(cid)

    player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    ms = state._military_system
    for idx, (wid, wname, cid) in enumerate(wars_spec):
        w = War(id=wid, name=wname, war_type=WarType.FOREIGN, strength=8,
                threat_level=3, rewards={"treasury": 100})
        w.commander_id = cid
        w.legions_assigned = 1
        ln = idx + 1
        w.add_legion_number(ln)
        w.status = WarStatus.ACTIVE
        state._war_system._active_wars.append(w)
        ok, _ = ms.recruit_legion(ln)
        assert ok, "recruit legion %d failed" % ln
        ms.assign_to_war([ln], wid, cid)
    return state


def _steps(state):
    return combat_api.get_combat_view(state, "player_opt")["data"]["steps"]


def _states(state):
    return [s["state"] for s in _steps(state)]


def _labels(state):
    return [s["label"] for s in _steps(state)]


# ---------------------------------------------------------------------------
# 基数 = max(3, N)
# ---------------------------------------------------------------------------

def test_n3_three_slots_placeholders_current_first():
    """FC-16：N=3（2 可执行 + 1 无指挥官）→ 3 槽占位；最低序 = current。"""
    state = _combat_state([
        ("war_a", "皮洛士战争", 1),
        ("war_b", "西西里叛乱", 2),
        ("war_c", "伊比利亚威胁", None),
    ])
    steps = _steps(state)
    assert len(steps) == 3, "max(3, N) 槽数应为 3"
    assert _states(state) == ["current", "todo", "todo"]
    assert _labels(state) == ["可执行战争1", "可执行战争2", "可执行战争3"]


def test_n2_third_slot_not_applicable():
    """FC-16：N=2 → 3 槽；槽 3 not_applicable。"""
    state = _combat_state([("w1", "战争A", 1), ("w2", "战争B", 2)])
    assert _states(state) == ["current", "todo", "not_applicable"]


def test_n1_remaining_slots_not_applicable():
    """FC-16：N=1 → 3 槽；槽 2/3 not_applicable（灰、跳过）。"""
    state = _combat_state([("w1", "战争A", 1)])
    assert _states(state) == ["current", "not_applicable", "not_applicable"]


def test_n0_all_not_applicable_no_current():
    """FC-16 R-3③：N=0 → 全槽 not_applicable（仍 3 槽）；无 current。"""
    state = _combat_state([])
    steps = _steps(state)
    assert len(steps) == 3
    assert all(s["state"] == "not_applicable" for s in steps)
    assert not any(s["state"] == "current" for s in steps)


def test_n_gt_3_overflow_no_cap():
    """FC-16 R-3④：N>3 → 槽数 = N（不封顶）。"""
    state = _combat_state([
        ("w1", "战争A", 1), ("w2", "战争B", 2),
        ("w3", "战争C", 3), ("w4", "战争D", 4),
    ])
    steps = _steps(state)
    assert len(steps) == 4, "N>3 应不封顶（槽数 = N）"
    assert _states(state) == ["current", "todo", "todo", "todo"]


# ---------------------------------------------------------------------------
# 占位 → 实名（真实生产动作：玩家自选顺序）
# ---------------------------------------------------------------------------

def test_placeholder_then_realname_on_real_action():
    """FC-16：真实 `do_combat_action` 后槽 k 占位 → 该场战争名 + complete；current 后移。"""
    state = _combat_state([
        ("war_a", "皮洛士战争", 1),
        ("war_b", "西西里叛乱", 2),
        ("war_c", "伊比利亚威胁", None),
    ])
    # 处理前占位
    assert _labels(state)[0] == "可执行战争1"
    # 真实生产动作：选择 + 进攻
    assert combat_api.select_war(state, "player_opt", "war_a")["success"]
    res = combat_api.do_combat_action(state, "player_opt", "war_a", "attack")
    assert res["success"], res.get("message")
    steps = _steps(state)
    assert steps[0]["label"] == "皮洛士战争", "槽 1 应替换为该场战争名"
    assert steps[0]["state"] == "complete"
    assert steps[1]["state"] == "current"  # 最低序 todo（下一空槽）
    assert steps[2]["state"] == "todo"


def test_player_self_selected_order_maps_to_slot_order():
    """FC-16：玩家自选顺序 —— 先打第 2 场 → 槽 2 变实名（不是槽 1）。"""
    state = _combat_state([
        ("war_a", "皮洛士战争", 1),
        ("war_b", "西西里叛乱", 2),
    ])
    assert combat_api.select_war(state, "player_opt", "war_b")["success"]
    assert combat_api.do_combat_action(state, "player_opt", "war_b", "attack")["success"]
    steps = _steps(state)
    assert steps[0]["label"] == "西西里叛乱" and steps[0]["state"] == "complete"
    assert steps[1]["state"] == "current"
    assert steps[2]["state"] == "not_applicable"


def test_single_war_processed_remaining_slots_na():
    """FC-16 J-AC-14-2：N=1 结算 → 槽 1 complete；槽 2/3 not_applicable。"""
    state = _combat_state([("w1", "战争A", 1)])
    assert combat_api.select_war(state, "player_opt", "w1")["success"]
    assert combat_api.do_combat_action(state, "player_opt", "w1", "attack")["success"]
    steps = _steps(state)
    assert steps[0]["label"] == "战争A" and steps[0]["state"] == "complete"
    assert steps[1]["state"] == "not_applicable"
    assert steps[2]["state"] == "not_applicable"


def test_no_commander_auto_skip_counts_in_n_and_becomes_complete():
    """FC-16 R-3②：无指挥官 auto-skip（`_skip_all_unassigned`）计入 N，处理后 complete。"""
    state = _combat_state([("war_c", "伊比利亚威胁", None)])
    steps = _steps(state)
    assert len(steps) == 3
    assert steps[0]["state"] == "current" and steps[0]["label"] == "可执行战争1"
    assert steps[1]["state"] == "not_applicable"
    # 真实生产 owner：auto_resolve → _skip_all_unassigned → resolved_wars
    res = combat_api.auto_resolve_combat(state, "player_opt")
    assert res["success"], res.get("message")
    steps2 = _steps(state)
    assert steps2[0]["label"] == "伊比利亚威胁"
    assert steps2[0]["state"] == "complete"


# ---------------------------------------------------------------------------
# 无 advance；shape/键/current_step 保留
# ---------------------------------------------------------------------------

def test_no_advance_step_and_current_step_preserved():
    """FC-16⑦⑨：无「推进决算」步骤；`current_step` 相位内部机保留。"""
    state = _combat_state([("w1", "战争A", 1), ("w2", "战争B", 2)])
    view = combat_api.get_combat_view(state, "player_opt")["data"]
    keys = [s["key"] for s in view["steps"]]
    assert "advance" not in keys
    assert not any("决算" in s["label"] for s in view["steps"])
    assert "current_step" in view
    assert view["current_step"] in ("select", "action", "result", "advance")


def test_steps_shape_unique_keys_and_vocabulary():
    """FC-02/FC-03/FC-16：shape/唯一键/词表/current<=1。"""
    state = _combat_state([
        ("w1", "战争A", 1), ("w2", "战争B", 2),
        ("w3", "战争C", 3), ("w4", "战争D", 4),
    ])
    steps = _steps(state)
    keys = [s["key"] for s in steps]
    assert len(keys) == len(set(keys)), f"key 重复 {keys}"
    for s in steps:
        assert set(s.keys()) >= {"key", "label", "state"}
        assert isinstance(s["label"], str) and s["label"]
        assert s["state"] in VALID_STATES
    assert sum(1 for s in steps if s["state"] == "current") <= 1


def test_store_phase_steps_passes_through_combat():
    """FC-01/FC-08：GuiSessionStore.phaseSteps 透传 combat 权威 steps。"""
    state = _combat_state([("w1", "战争A", 1), ("w2", "战争B", 2)])
    store = GuiSessionStore(state)
    store.initialize("player_opt")
    store.selectPhase("combat")
    steps = store.phaseSteps
    assert len(steps) == 3
    assert [s["state"] for s in steps] == ["current", "todo", "not_applicable"]
