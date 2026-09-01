# src/tests/test_api/test_wpg_gd_population_parity.py
"""
WP-G G4-GD G2（L 件 §6 / §11.5）— GUI/CLI Population 生命周期对等（S28/S29/S30/S33）。

T-GD-17~20：战后态（战争结束 → 军团/舰队 AVAILABLE）经两个生产入口：
- CLI：phase_population._handle_step_0（PopulationCommand，_auto_mode）
- GUI：session_api.resolve_population_slice
同一 canonical population_api.process_population_disbandments → 相同 mutation 集
（军团 DISBANDED / 舰队 DISBANDED 非 DESTROYED / _legions_to_disband 消费 /
resolved war legion_numbers 清空）+ 幂等 marker（重入零重复）。

真实生命周期链（真实 GameState/WarSystem/MilitarySystem/NavalSystem + 真实阶段 API），
禁手搓 DTO mock（证据红线）。
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import session_api, population_api
from src.ui.commands.phase_population import PopulationCommand


def _build_postwar_state():
    """战后态（G1-14 链：战争 RESOLVED → 幸存召回 AVAILABLE）：
    - war1 RESOLVED（discard），legion_numbers=[1,2]（残留镜像，召回后不清）
    - 军团 1/2 召回 → AVAILABLE；军团 3 AVAILABLE 入 _legions_to_disband 队列
    - 舰队 1 AVAILABLE（无需要海战的战争 → decider 命中 → DISBANDED）
    - 人口阶段为当前阶段（mortality/revenue/forum 已执行）
    """
    config = {
        "testing": {"bypass_player_check": True},
        "political_rules": {
            "min_ages": {"consul": 40},
            "office_rank": {"consul": 5},
            "office_influence_bonus": {"consul": 40},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=12, year=-275)
    state._treasury = 500
    state.pyrrhic_war_won = True

    faction = Faction(id="Optimates", name="贵族派")
    state._factions["Optimates"] = faction
    player = Player(player_id="player_1", faction_id="Optimates", player_type=PlayerType.HUMAN)
    state._players["player_1"] = player
    state._current_player_id = "player_1"
    state._turn_order = ["player_1"]

    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    ms = state._military_system
    ws = state._war_system
    ns = state._naval_system

    # 已结束战争（TRIUMPH/VICTORY 结算后形态：RESOLVED + discard + legion_numbers 残留）
    war1 = War(id="war1", name="Ended War", strength=8, threat_level=3)
    war1.status = WarStatus.RESOLVED
    ws._war_discard.append(war1)

    # 军团 1/2：征召 → 指派 → 召回（AVAILABLE，war_id=None；war.legion_numbers 残留 [1,2]）
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok
    assigned, _ = ms.assign_to_war([1, 2], "war1", 101)
    assert assigned == 2
    assert ms.recall_from_war("war1") == 2
    war1.add_legion_number(1)
    war1.add_legion_number(2)

    # 军团 3：AVAILABLE 且入待解散队列（GA 兼容队列路径）
    ok, _ = ms.recruit_legion(3)
    assert ok
    ms.get_legion_by_number(3).recall()  # ACTIVE → AVAILABLE（recall 无参）
    ws.add_legions_to_disband([3])

    # 舰队 1：AVAILABLE（无需要海战的战争 → AutoFleetDisbandDecider 命中 → DISBANDED）
    fleet1 = Fleet(number=1, fleet_type="trireme")
    fleet1._strength_base = 3
    fleet1._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet1
    # 舰队 2：AVAILABLE（同被解散）
    fleet2 = Fleet(number=2, fleet_type="trireme")
    fleet2._strength_base = 3
    fleet2._status = FleetStatus.AVAILABLE
    ns._fleets[2] = fleet2

    # 人口阶段为当前阶段（resolve_population_slice 阶段门）
    for ph in ("mortality", "revenue", "forum"):
        state.mark_phase_executed(ph)
    return state


def _snapshot_mutation(state):
    """解散生命周期 mutation 集快照（军团/舰队/队列/war 镜像残留）。"""
    ms = state._military_system
    ns = state._naval_system
    ws = state._war_system
    return {
        "legion_status": [l.status for l in ms._legions],
        "legion_war_id": [l.war_id for l in ms._legions],
        "fleet_status": {n: f.status for n, f in ns._fleets.items()},
        "fleet_target_war_id": {n: f._target_war_id for n, f in ns._fleets.items()},
        "legions_to_disband": list(ws._legions_to_disband),
        "resolved_war_legion_numbers": {w.id: list(w.legion_numbers) for w in ws._war_discard},
    }


# ---------------------------------------------------------------------------
# T-GD-17 — S30：GUI 与 CLI 对同一战后态产生相同 mutation 集
# ---------------------------------------------------------------------------

def test_tgd17_gui_cli_same_mutation_set():
    cli_state = _build_postwar_state()
    gui_state = _build_postwar_state()

    # CLI 入口：PopulationCommand._handle_step_0（_auto_mode 跳过 input）
    cmd = PopulationCommand(cli_state)
    cmd._auto_mode = True
    cmd._handle_step_0()

    # GUI 入口：resolve_population_slice
    gui_result = session_api.resolve_population_slice(gui_state)
    assert gui_result["success"] is True, gui_result.get("message")

    assert _snapshot_mutation(cli_state) == _snapshot_mutation(gui_state)


# ---------------------------------------------------------------------------
# T-GD-18 — GUI population 现执行军团解散（经 canonical）
# ---------------------------------------------------------------------------

def test_tgd18_gui_executes_legion_disband():
    gui_state = _build_postwar_state()
    gui_result = session_api.resolve_population_slice(gui_state)
    assert gui_result["success"] is True

    data = gui_result["data"]
    assert "disbandment" in data, "phase result data 必须携带 disbandment 业务事实"
    disbandment = data["disbandment"]
    legions = disbandment["legions"]
    # resolved_wars 消费 war1.legion_numbers=[1,2] → 2 个解散；deescalated 消费队列 [3] → 1 个
    assert legions["resolved_wars"]["total"] == 2
    assert legions["deescalated"]["total"] == 1

    ms = gui_state._military_system
    assert ms.get_legion_by_number(1).status == LegionStatus.DISBANDED
    assert ms.get_legion_by_number(2).status == LegionStatus.DISBANDED
    assert ms.get_legion_by_number(3).status == LegionStatus.DISBANDED
    assert gui_state._war_system._legions_to_disband == []


# ---------------------------------------------------------------------------
# T-GD-19 — GUI population 现执行舰队解散（经 canonical → DISBANDED 非 DESTROYED）
# ---------------------------------------------------------------------------

def test_tgd19_gui_executes_fleet_disband():
    gui_state = _build_postwar_state()
    gui_result = session_api.resolve_population_slice(gui_state)
    assert gui_result["success"] is True

    disbandment = gui_result["data"]["disbandment"]
    assert sorted(disbandment["fleets"]) == [1, 2]

    ns = gui_state._naval_system
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED
    assert ns.get_fleet(2).status == FleetStatus.DISBANDED
    # 行政退役非 DESTROYED（G1-13/R-11）
    assert FleetStatus.DESTROYED not in (ns.get_fleet(1).status, ns.get_fleet(2).status)


# ---------------------------------------------------------------------------
# T-GD-20 — canonical 幂等 marker：同 phase 第二次调用 no-op（S33）
# ---------------------------------------------------------------------------

def test_tgd20_canonical_idempotent_no_double_disband():
    state = _build_postwar_state()

    first = population_api.process_population_disbandments(state)
    assert first["legions"]["resolved_wars"]["total"] == 2
    assert first["legions"]["deescalated"]["total"] == 1
    assert sorted(first["fleets"]) == [1, 2]
    snap = _snapshot_mutation(state)

    # 重入（同 phase）：marker 命中 → no-op，零重复 mutation
    second = population_api.process_population_disbandments(state)
    assert second is first or second == first
    assert _snapshot_mutation(state) == snap
    assert state._war_system._legions_to_disband == []

    # 双入口连续调用：GUI 侧再入（resolve_population_slice 已 early-return）+ canonical 直接重入
    gui_state = _build_postwar_state()
    population_api.process_population_disbandments(gui_state)
    before = _snapshot_mutation(gui_state)
    population_api.process_population_disbandments(gui_state)
    assert _snapshot_mutation(gui_state) == before


# ---------------------------------------------------------------------------
# S33 补充：CLI _handle_step_0 双执行（startup_done 守卫 + marker 双重防护）
# ---------------------------------------------------------------------------

def test_tgd20b_cli_step0_reentry_no_duplicate():
    state = _build_postwar_state()
    cmd = PopulationCommand(state)
    cmd._auto_mode = True
    cmd._handle_step_0()
    snap = _snapshot_mutation(state)
    # 再执行（同 command 实例 startup_done 守卫；新实例则 marker 防护）
    cmd._handle_step_0()
    assert _snapshot_mutation(state) == snap

    cmd2 = PopulationCommand(state)
    cmd2._auto_mode = True
    cmd2._handle_step_0()
    assert _snapshot_mutation(state) == snap
