# src/tests/test_api/test_wpg_gc_combat_gate.py
"""
WP-G GC 切片测试（T-GC-14/15/18）— combat_api 海军门（GUI+CLI 共享面）

冻结语义来源：任务包 v0.8 §11.8/§11.9、G1-09/R-04/R-05/R-06、
G2 设计 D/K/M 件（G3 DESIGN FROZEN）。
真实生命周期链（真实 NavalSystem CRT + 真实舰队/军团附着），禁手搓 DTO mock（证据红线）。
"""
import random as _random
from pathlib import Path

import pytest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import combat_api

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _build_state(war_id="war1", enemy_naval=18, n_fleets=3, strength=5,
                 legion_count=2, add_second_war=False):
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
            },
            "default_fleet_type": "trireme",
        }
    })
    state.turn = GameTurn(turn_number=10, year=-280)
    for p in ["mortality", "revenue", "forum", "population", "senate"]:
        state.mark_phase_executed(p)
    state.pyrrhic_war_won = True
    state._treasury = 500

    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Marcus", faction_id="senate", age=40)
    commander.martial = 6
    commander.influence = 50
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    war = War(
        id=war_id, name="Naval War", strength=strength, threat_level=3,
        rewards={"treasury": 100},
        naval_required=True,
        enemy_naval_current=enemy_naval,
        disaster_numbers=[2, 3, 4],
        standoff_numbers=[99],
    )
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)

    ns = state.naval_system
    for n in range(1, n_fleets + 1):
        fleet = Fleet(number=n, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._target_war_id = war.id
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[n] = fleet
        ok = ns.assign_fleet_to_war(n, war.id, "naval")
        assert ok, f"assign fleet {n} failed"

    if legion_count > 0:
        ms = state._military_system
        for num in range(1, legion_count + 1):
            ok, _ = ms.recruit_legion(num)
            assert ok, f"recruit legion {num} failed"
        assigned, msg = ms.assign_to_war(list(range(1, legion_count + 1)), war.id, 101)
        assert assigned == legion_count, msg

    if add_second_war:
        war2 = War(
            id="war2", name="Land War", strength=8, threat_level=2,
            rewards={"treasury": 100},
            naval_required=False,
            disaster_numbers=[99],
            standoff_numbers=[99],
        )
        war2.commander_id = 101
        war2.status = WarStatus.ACTIVE
        state._war_system._active_wars.append(war2)
        for num in (11, 12, 13, 14):
            ok, _ = ms.recruit_legion(num)
            assert ok
        assigned, msg = ms.assign_to_war([11, 12, 13, 14], "war2", 101)
        assert assigned == 4, msg

    return state, war, commander


@pytest.fixture
def gate_state():
    return _build_state(enemy_naval=18, n_fleets=3, legion_count=2)


# ════════════════════════════════════════════════════════════════════════
# T-GC-14 — GUI do_combat_action 海军门（§11.8）
# ════════════════════════════════════════════════════════════════════════
def test_tgc14_gui_do_combat_action_naval_gate_blocks(gate_state):
    """naval_required + 未获控 attack → naval 阻断 DTO（land_battle=blocked）+ 陆战零执行
    + resolved_wars 含该 war + 不阻塞 advance + DTO 字段齐备"""
    state, war, commander = gate_state
    # STALEMATE：3 舰队战力 27（martial 6），enemy 30，dice 5 → total 2
    war._enemy_naval_current = 30
    with patch("src.core.systems.naval_system.random.randint", return_value=5):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]

    # 阻断 DTO 字段齐备（向后兼容字段名 + 增量字段）
    for field in ("war_id", "war_name", "result", "result_label", "losses",
                  "triumph", "dice", "total_attack", "enemy_defence", "total_score",
                  "loot", "casualty_numbers"):
        assert field in data, f"naval block DTO missing {field}"
    assert data["war_id"] == "war1"
    assert data["land_battle"] == "blocked"
    assert data["naval"] == {"result": "STALEMATE", "roman_losses": 0,
                             "sea_control_acquired": False}
    assert data["losses"] == 0

    # 陆战零执行：军团保持 ACTIVE + assigned（G1-15 零陆战伤亡）
    ms = state._military_system
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    assert all(l.war_id == war.id for l in attached)

    # resolved_wars 含该 war → advance 不阻塞
    phase_data = state.get_phase_result("combat")
    assert war.id in phase_data["resolved_wars"]
    adv = combat_api.advance_combat(state, "player_opt")
    assert adv["success"]


def test_tgc14_gui_naval_triumph_continues_land_battle(gate_state):
    """TRIUMPH → 获控 → 同场陆战执行（DTO naval 增量 sea_control_acquired=True）"""
    state, war, _ = gate_state
    war._enemy_naval_current = 0
    # 同一全局 random：side_effect 顺序 = 海战骰子 7 → TRIUMPH，陆战骰子 7
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "TRIUMPH"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land_battle"] == "allowed"
    # 陆战真实执行（非阻断）：战斗结算字段齐全
    assert "total_score" in data and "dice" in data


# ════════════════════════════════════════════════════════════════════════
# T-GC-15 — CLI auto_resolve_combat：naval-required 多战混合 → 阻断战不阻塞 advance
# ════════════════════════════════════════════════════════════════════════
def test_tgc15_cli_auto_resolve_mixed_wars_blocked_not_blocking_advance():
    """auto_resolve_combat：naval 阻断战 + 陆战胜利战混合 → 全部结算且 advance 通过"""
    state, war, _ = _build_state(enemy_naval=18, n_fleets=3, legion_count=2,
                                 add_second_war=True)
    war._enemy_naval_current = 30  # 海战 STALEMATE：dice 5 + 27 - 30 = 2
    # 同一全局 random：side_effect 顺序 = war1 海战骰子 5（STALEMATE）→ war2 陆战骰子 10（triumph）
    with patch.object(combat_api.random, "randint", side_effect=[5, 10, 10, 10, 10]):
        result = combat_api.auto_resolve_combat(state, "player_opt")

    assert result["success"]
    data = result["data"]
    assert data["wars_resolved"] == 2
    assert data["active_war_count"] == 2
    assert data["completed"] is True
    assert state.is_phase_executed("combat")

    battles = {b["war_id"]: b for b in data["battles"]}
    assert battles["war1"]["land_battle"] == "blocked"
    assert battles["war1"]["naval"]["result"] == "STALEMATE"
    assert battles["war2"]["result"] == "triumph"
    assert battles["war2"].get("land_battle") != "blocked"

    # 阻断战战争继续（未 resolve/discard）
    assert war.status == WarStatus.ACTIVE
    assert war.sea_control_acquired is False


# ════════════════════════════════════════════════════════════════════════
# T-GC-18 — diff 审计（static，R-11/R-12/R-06/K 件残留扫描）
# ════════════════════════════════════════════════════════════════════════
def _read_source(rel_path: str) -> str:
    return (_REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tgc18_no_sea_control_ratio_as_authority_residual():
    """无 _sea_control_ratio 作获控权威残留：gate 判定用 sea_control_acquired"""
    naval = _read_source("src/core/systems/naval_system.py")
    combat = _read_source("src/api/combat_api.py")
    war_src = _read_source("src/core/entities/war.py")
    # 门判定点仅引用 sea_control_acquired（K 件 §1）
    assert "if war.naval_required and not war.sea_control_acquired" in combat
    # resolve_naval_battle 获控 mutation 写 _sea_control_acquired（True 唯一 owner）
    assert "war._sea_control_acquired = True" in naval
    # from_dict 不把 _sea_control_ratio 映射为 acquired（N 件 §2：dormant 不映射）
    assert "acquired is True" in war_src


def test_tgc18_no_mark_destroyed_for_admin_retirement_residual():
    """行政退役路径（决策器/国库解散）无 mark_destroyed 残留（R-11）"""
    naval = _read_source("src/core/systems/naval_system.py")
    disband_fn = naval.split("def disband_unused_fleets")[1].split("\n    # ---------- 舰队恢复")[0]
    assert "fleet.mark_destroyed" not in disband_fn
    apply_fn = naval.split("def apply_maintenance")[1].split("\n    # ---------- 序列化")[0]
    assert "fleet.mark_destroyed" not in apply_fn
    # 新增原语存在
    fleet_src = _read_source("src/core/entities/fleet.py")
    assert "def disband(self)" in fleet_src


def test_tgc18_no_global_available_fleet_block_residual():
    """补充合同无「任一全局可用舰队即阻断所有战争」残留（§11.11/G1-11）"""
    naval = _read_source("src/core/systems/naval_system.py")
    repl_fn = naval.split("def generate_replacement_contracts")[1].split("\n    # ---------- 序列化")[0]
    assert "if self.get_available_fleets():" not in repl_fn
    # 冻结公式：deficit = target - existing → ceil(deficit/base)（D 件 §6）
    assert "deficit = enemy_strength - existing" in repl_fn
    assert "needed_ships = max(1, (deficit + base_strength - 1) // base_strength)" in repl_fn
