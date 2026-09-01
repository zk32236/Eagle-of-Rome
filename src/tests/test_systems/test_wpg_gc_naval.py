# src/tests/test_systems/test_wpg_gc_naval.py
"""
WP-G GC 切片测试（T-GC-01~13/16/17）— Naval / Fleet / Sea Control（System + Entity 层）

冻结语义来源：任务包 v0.8 §5/§8/§9、G1-09/10/11/12/13/14/16/20、
G2 设计 D/J/K/H/O 件（G3 DESIGN FROZEN）。
真实生命周期链（真实 NavalSystem/WarSystem/MilitarySystem + 真实 CRT），禁手搓 DTO mock（证据红线）。
"""
import random as _random

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


# ════════════════════════════════════════════════════════════════════════
# 共享 fixture：真实 GameState + NavalSystem + 海军战争 + 真实舰队指派
# ════════════════════════════════════════════════════════════════════════
def _build_state(war_id="war1", enemy_naval=18, n_fleets=3, strength=5,
                 martial=4, legion_count=0, enemy_land=0):
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
                "quadrireme": {"build_cost": 120, "build_time": 2, "maintenance_cost": 6, "strength_base": 4},
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

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = martial
    commander.influence = 10
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    war = War(
        id=war_id, name="Naval War", strength=strength, threat_level=3,
        rewards={"treasury": 100},
        naval_required=True,
        enemy_naval_current=enemy_naval,
        enemy_land_current=enemy_land,
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

    return state, war, commander


@pytest.fixture
def naval_state():
    """3 舰队 + 2 军团 + martial 4 的海军战争（真实链）"""
    return _build_state(enemy_naval=18, n_fleets=3, legion_count=2)


# ════════════════════════════════════════════════════════════════════════
# T-GC-01 — naval_required + 未获控 → 触发 resolve_naval_battle（S03）
# ════════════════════════════════════════════════════════════════════════
def test_tgc01_naval_gate_triggers_resolve_naval_battle(naval_state):
    """attack 路径对 naval_required + 未获控 war 必须先海战（spy 观察，真实链）"""
    state, war, _ = naval_state
    assert war.sea_control_acquired is False
    ns = state.naval_system
    calls = []
    original = ns.resolve_naval_battle

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    with patch.object(ns, "resolve_naval_battle", side_effect=spy):
        combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert len(calls) == 1
    assert calls[0][0] is war


# ════════════════════════════════════════════════════════════════════════
# T-GC-02 — Naval TRIUMPH → sea_control_acquired=True + 同场陆战执行（S04）
# ════════════════════════════════════════════════════════════════════════
def test_tgc02_naval_triumph_acquires_sea_control_and_land_battle_continues(naval_state):
    """TRIUMPH → 制海权获控 + 陆战继续（naval 增量标注 land_battle=allowed）

    WP-G G4-GD G3（K 件 §3 / D-1）：战争正式结束（同场陆战 TRIUMPH → RESOLVED）→
    clear_sea_control 清理——战斗事实（DTO sea_control_acquired=True）保留，
    实体 flag 随战争结束置回未获控（禁 stale True 残留/重洗入 deck 再战）。
    """
    state, war, _ = naval_state
    war._enemy_naval_current = 0  # TRIUMPH：dice + 21 - 0 ≥ 12
    with patch("src.core.systems.naval_system.random.randint", return_value=7):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "TRIUMPH"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land_battle"] == "allowed"
    # 同场陆战 TRIUMPH → 战争结束（RESOLVED）；制海权随战争正式结束清理（GD 接线）
    assert war.status == WarStatus.RESOLVED
    assert war.sea_control_acquired is False


# ════════════════════════════════════════════════════════════════════════
# T-GC-03 — Naval VICTORY → 同 S04（S05）
# ════════════════════════════════════════════════════════════════════════
def test_tgc03_naval_victory_acquires_sea_control_and_land_battle_continues(naval_state):
    """VICTORY → 同 S04（S05）；同场陆战 VICTORY → 战争结束 → 制海权随战争正式结束清理（GD 接线）"""
    state, war, _ = naval_state
    # N=3 舰队战力 21（含 martial 4）：dice 5 + 21 - 15 = 11 → VICTORY（dice 5 ∉ disaster[2,3,4]）
    war._enemy_naval_current = 15
    # 注意：naval_system.random 与 combat_api.random 是同一全局 random 模块——
    # 用 side_effect 顺序控制（第 1 次 = 海战骰子 5，第 2 次 = 陆战骰子 7）
    with patch.object(combat_api.random, "randint", side_effect=[5, 7]):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "VICTORY"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land_battle"] == "allowed"
    # 同场陆战 VICTORY → 战争结束（RESOLVED）；制海权清理（K 件 §3 / D-1）
    assert war.status == WarStatus.RESOLVED
    assert war.sea_control_acquired is False


# ════════════════════════════════════════════════════════════════════════
# T-GC-04 — Naval STALEMATE → 0 舰队损失 + 陆战不执行 + 军团保持 ACTIVE+assigned + war 继续
# ════════════════════════════════════════════════════════════════════════
def test_tgc04_naval_stalemate_blocks_land_battle_zero_losses(naval_state):
    """STALEMATE → 0 损失 + 阻断陆战（land_battle=blocked）+ 军团保持 + 战争继续"""
    state, war, commander = naval_state
    # 3 舰队战力 21，enemy 21，dice 5 → total 5 → STALEMATE（dice 5 ∉ disaster[2,3,4]/standoff[99]）
    war._enemy_naval_current = 21
    with patch("src.core.systems.naval_system.random.randint", return_value=5):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "STALEMATE"
    assert data["land_battle"] == "blocked"
    assert data["losses"] == 0  # STALEMATE 0 舰队损失（G1-10）

    # 舰队零损失：全部 ON_MISSION
    ns = state.naval_system
    assert all(f.status == FleetStatus.ON_MISSION for f in ns.get_all_fleets())
    assert sorted(war.assigned_fleet_ids) == [1, 2, 3]

    # 军团保持 ACTIVE + assigned（G1-15 零陆战伤亡）
    ms = state._military_system
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    assert all(l.war_id == war.id for l in attached)

    # 战争继续：ACTIVE + duration+1 + 未获控
    assert war.status == WarStatus.ACTIVE
    assert war.duration == 1
    assert war.sea_control_acquired is False

    # 不阻塞 advance（resolved_wars 含该 war）
    adv = combat_api.advance_combat(state, "player_opt")
    assert adv["success"]


# ════════════════════════════════════════════════════════════════════════
# T-GC-05 — Naval DEFEAT → random.sample ceil(N/2) DESTROYED（N=1..6 全表）+ 陆战不执行
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("n,expected_losses,expected_survivors", [
    (1, 1, 0),
    (2, 1, 1),
    (3, 2, 1),
    (4, 2, 2),
    (5, 3, 2),
    (6, 3, 3),
])
def test_tgc05_naval_defeat_ceil_half_destroyed_table(n, expected_losses, expected_survivors):
    """DEFEAT：随机无放回 ceil(N/2) → DESTROYED（集合性质断言，G1-10/G1-06 全表）"""
    state, war, _ = _build_state(enemy_naval=60, n_fleets=n)
    _random.seed(20260831)
    with patch("src.core.systems.naval_system.random.randint", return_value=5):
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "DEFEAT"
    assert data["land_battle"] == "blocked"

    fleets = state.naval_system.get_all_fleets()
    destroyed = [f for f in fleets if f.status == FleetStatus.DESTROYED]
    survivors = [f for f in fleets if f.status == FleetStatus.ON_MISSION]
    assert len(destroyed) == expected_losses
    assert len(survivors) == expected_survivors
    # 伤亡集 ⊆ 参战集（无放回、无前缀序假设——集合性质）
    assert {f.number for f in destroyed} <= set(range(1, n + 1))
    # DESTROYED 同步 war.assigned_fleet_ids（存活舰队仍在册）
    assert sorted(war.assigned_fleet_ids) == sorted(f.number for f in survivors)
    # 伤亡舰队状态：destroyed_turn 记录
    assert all(f.destroyed_turn == 10 for f in destroyed)


# ════════════════════════════════════════════════════════════════════════
# T-GC-06 — Naval DISASTER → 全部参战舰队 DESTROYED + 陆战不执行（S08）
# ════════════════════════════════════════════════════════════════════════
def test_tgc06_naval_disaster_destroys_all_fleets(naval_state):
    """DISASTER：全部参战舰队 DESTROYED + 阻断陆战"""
    state, war, _ = naval_state
    with patch("src.core.systems.naval_system.random.randint", return_value=2):  # dice ∈ disaster_numbers
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "DISASTER"
    assert data["land_battle"] == "blocked"
    assert data["losses"] == 3

    fleets = state.naval_system.get_all_fleets()
    assert all(f.status == FleetStatus.DESTROYED for f in fleets)
    assert war.assigned_fleet_ids == []
    assert war.sea_control_acquired is False


# ════════════════════════════════════════════════════════════════════════
# T-GC-07 — 获控后同战未来 attack 跳过海战直达陆战（S09 / R-06）
# ════════════════════════════════════════════════════════════════════════
def test_tgc07_sea_control_skips_future_naval_battle(naval_state):
    """获控后（同战陆战 DEFEAT 继续）未来 attack 跳过海战直达陆战（R-06）"""
    state, war, commander = naval_state
    war._enemy_naval_current = 0  # 海战 TRIUMPH
    # 陆战高敌力 → DEFEAT（战争继续 ACTIVE，制海权保持，commander 清）
    war._strength = 40
    with patch("src.core.systems.naval_system.random.randint", return_value=7):
        r1 = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert r1["success"]
    assert war.sea_control_acquired is True
    assert war.status == WarStatus.ACTIVE

    # 下回合新 Combat 阶段（phase_data 重建）；Takeover/T15 后重新绑定指挥官（GA 域）
    state.record_phase_result("combat", {})
    war.commander_id = commander.id

    ns = state.naval_system
    calls = []
    original = ns.resolve_naval_battle

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    with patch.object(ns, "resolve_naval_battle", side_effect=spy):
        with patch("src.core.systems.naval_system.random.randint", return_value=7):
            with patch.object(combat_api.random, "randint", return_value=7):
                r2 = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert r2["success"]
    # 关键断言：不再触发海战（R-06）——直达陆战
    assert calls == []
    assert "naval" not in r2["data"]
    assert war.sea_control_acquired is True  # 制海权保持（G1-16）


# ════════════════════════════════════════════════════════════════════════
# T-GC-08 — 同战 deficit：存活 1 艘战力 4、target 10、base 3 → 补 ceil(6/3)=2（S10 / G1-11）
# ════════════════════════════════════════════════════════════════════════
def test_tgc08_replacement_by_same_war_deficit():
    """补充合同 = ceil(deficit/base)；AVAILABLE 存活舰队不再全局阻断（§11.11 修复）"""
    state, war, _ = _build_state(enemy_naval=10, n_fleets=0)
    ns = state.naval_system
    # 存活 1 艘：战力 4（base 3 + 经验 1），专属 war（_target_war_id），AVAILABLE staging
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._experience = 1
    fleet._target_war_id = war.id
    fleet._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet

    contracts = ns.generate_replacement_contracts(current_turn=10)
    # 旧偏差：get_available_fleets() 非空 → 返回 []；冻结语义：deficit 10-4=6 → ceil(6/3)=2
    assert len(contracts) == 1
    comp = contracts[0].recommended_fleet_composition
    assert comp == [{"type": "trireme", "count": 2}]


# ════════════════════════════════════════════════════════════════════════
# T-GC-09 — War A 存活舰队不满足 War B deficit（R-12）；跨战 assign 被拒
# ════════════════════════════════════════════════════════════════════════
def test_tgc09_cross_war_fleet_not_counted_and_assign_rejected():
    """跨战舰队不计入他战 deficit；跨战指派被拒（R-12 / G1-12）"""
    state, war_a, _ = _build_state(war_id="warA", enemy_naval=10, n_fleets=0)
    # War B（同状态，enemy 10）
    war_b = War(
        id="warB", name="War B", strength=5, naval_required=True,
        enemy_naval_current=10, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war_b.commander_id = 101
    war_b.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war_b)

    ns = state.naval_system
    # War A 专属存活舰队（战力 4）
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._experience = 1
    fleet._target_war_id = "warA"
    fleet._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet

    # War B deficit 不受 War A 舰队影响：existing(B)=0 → deficit 10 → ceil(10/3)=4
    contracts = ns.generate_replacement_contracts(current_turn=10)
    by_war = {}
    for c in contracts:
        by_war.setdefault(c._target_war_id, []).append(c)
    assert "warB" in by_war
    assert sum(sum(item["count"] for item in c.recommended_fleet_composition) for c in by_war["warB"]) == 4

    # 跨战指派被拒：fleet 专属 warA，尝试指派 warB → False（R-12 守卫）
    assert ns.assign_fleet_to_war(1, "warB", "naval") is False
    assert fleet.status == FleetStatus.AVAILABLE


# ════════════════════════════════════════════════════════════════════════
# T-GC-10 — 行政退役 → DISBANDED 非 DESTROYED；海战伤亡 → DESTROYED（G1-13 / R-11）
# ════════════════════════════════════════════════════════════════════════
def _minimal_naval_state():
    """无战争的最小 NavalSystem 状态（决策器无存活海战战争 → 可退役）"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {"trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3}},
            "default_fleet_type": "trireme",
        }
    })
    state.turn = GameTurn(turn_number=10, year=-280)
    state._war_system = WarSystem(state)
    state._naval_system = NavalSystem(state)
    return state


def test_tgc10_disband_unused_fleets_uses_disband_not_destroyed():
    """决策器行政退役 → DISBANDED（非 DESTROYED），is_veteran 保留（G1-13 / R-11）"""
    from src.core.deciders.impl.auto_fleet_disband_decider import AutoFleetDisbandDecider
    state = _minimal_naval_state()
    ns = state.naval_system
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._target_war_id = "war1"
    fleet._status = FleetStatus.AVAILABLE
    fleet._is_veteran = True  # 行政退役不清 Veteran（与 legion.disband 对齐，J 件 §4）
    ns._fleets[1] = fleet

    disbanded = ns.disband_unused_fleets(current_turn=10, decider=AutoFleetDisbandDecider())
    assert disbanded == [1]
    assert fleet.status == FleetStatus.DISBANDED
    assert fleet.is_veteran is True
    assert fleet.destroyed_turn == 0  # 非 DESTROYED 路径


def test_tgc10_apply_maintenance_treasury_shortfall_disbands():
    """国库不足 → 行政解散 → DISBANDED（非 DESTROYED，R-11）"""
    state = _minimal_naval_state()
    ns = state.naval_system
    for num in (1, 2):
        fleet = Fleet(number=num, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._target_war_id = "war1"
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[num] = fleet

    state._treasury = 0
    ok, msg = ns.apply_maintenance()
    # 两艘均无法单独补足总维护（0+4 < 8）→ 全部行政解散 → 维护归零
    assert ok is True
    assert all(f.status == FleetStatus.DISBANDED for f in ns.get_all_fleets())
    assert all(f.destroyed_turn == 0 for f in ns.get_all_fleets())


def test_tgc10_naval_casualty_is_destroyed_not_disbanded(naval_state):
    """海战伤亡（DEFEAT/DISASTER）→ DESTROYED（战斗伤亡专用，G1-13）"""
    state, war, _ = naval_state
    war._enemy_naval_current = 60  # total = 5+21-60 < -3 → DEFEAT
    with patch("src.core.systems.naval_system.random.randint", return_value=5):
        combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    fleets = state.naval_system.get_all_fleets()
    assert any(f.status == FleetStatus.DESTROYED for f in fleets)
    assert all(f.status != FleetStatus.DISBANDED for f in fleets)


# ════════════════════════════════════════════════════════════════════════
# T-GC-11 — Fleet._target_war_id to_dict/from_dict round-trip 无损（缺省 None）（S32）
# ════════════════════════════════════════════════════════════════════════
def test_tgc11_fleet_target_war_id_roundtrip():
    """_target_war_id 序列化 round-trip；旧存档缺键 → None（O 件 §3）"""
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._target_war_id = "war1"
    reconstructed = Fleet.from_dict(fleet.to_dict())
    assert reconstructed._target_war_id == "war1"

    fresh = Fleet(number=2, fleet_type="trireme")
    assert fresh._target_war_id is None
    reconstructed_fresh = Fleet.from_dict(fresh.to_dict())
    assert reconstructed_fresh._target_war_id is None

    # 旧存档缺键（无 "_target_war_id"）→ None 不崩
    legacy_data = fresh.to_dict()
    legacy_data.pop("_target_war_id", None)
    legacy = Fleet.from_dict(legacy_data)
    assert legacy._target_war_id is None


# ════════════════════════════════════════════════════════════════════════
# T-GC-12 — War.sea_control_acquired to_dict/from_dict round-trip；旧存档缺键 → False
# ════════════════════════════════════════════════════════════════════════
def test_tgc12_war_sea_control_acquired_roundtrip():
    """sea_control_acquired 序列化 round-trip；旧存档缺键/None → False（O 件 §3 退化路径）"""
    war = War(id="w1", name="W", naval_required=True)
    war._sea_control_acquired = True
    reconstructed = War.from_dict(war.to_dict())
    assert reconstructed.sea_control_acquired is True

    # 缺键 → False（旧存档）
    data = war.to_dict()
    data.pop("_sea_control_acquired", None)
    legacy = War.from_dict(data)
    assert legacy.sea_control_acquired is False

    # 显式 None → False（is not None 容错）
    data["_sea_control_acquired"] = None
    assert War.from_dict(data).sea_control_acquired is False

    # 默认构造 → False
    assert War(id="w2", name="W2").sea_control_acquired is False


# ════════════════════════════════════════════════════════════════════════
# T-GC-13 — 指派后 fleet.commander_id == war.commander_id；战力 martial 取自 War Commander
# ════════════════════════════════════════════════════════════════════════
def test_tgc13_fleet_commander_binding_and_martial_source():
    """Fleet 绑定 = War Commander（G1-20）；战力 martial 权威取 war.commander_id（H 件）"""
    state = GameState.create_for_testing({})
    state._war_system = WarSystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    commander = Figure(id=101, name="War Commander", faction_id="senate", age=40)
    commander.martial = 4
    state.add_member(commander)
    faction.member_ids.append(101)
    old_cmd = Figure(id=102, name="Old Commander", faction_id="senate", age=45)
    old_cmd.martial = 2
    state.add_member(old_cmd)
    faction.member_ids.append(102)

    war = War(id="w1", name="W", naval_required=True, enemy_naval_current=5,
              disaster_numbers=[99], standoff_numbers=[99])
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)

    ns = state.naval_system
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._target_war_id = "w1"
    fleet._status = FleetStatus.AVAILABLE
    fleet._commander_id = 102  # 旧绑定镜像（模拟 GA rebind 前残留）
    ns._fleets[1] = fleet

    # 指派（不传 commander）→ 绑定 = war.commander_id（G1-20）
    assert ns.assign_fleet_to_war(1, "w1", "naval") is True
    assert fleet.commander_id == 101

    # 战力 martial 取自 War Commander（martial 4），非旧绑定（martial 2）
    fleet._experience = 0
    strength = fleet.get_combat_strength(state)
    assert strength == 3 + 4  # base + War Commander martial


# ════════════════════════════════════════════════════════════════════════
# T-GC-16 — 战争结束幸存舰队 recall → AVAILABLE → calculate_maintenance 仍计维护；DISBANDED 后不计
# ════════════════════════════════════════════════════════════════════════
def test_tgc16_recalled_available_fleet_still_maintained_until_disbanded():
    """G1-14：召回 AVAILABLE 幸存者仍计维护（最后维护）；DISBANDED 后不计（GC 原语层）"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {"trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3}},
            "default_fleet_type": "trireme",
        }
    })
    state._naval_system = NavalSystem(state)
    ns = state.naval_system

    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._target_war_id = "war1"
    fleet._status = FleetStatus.ON_MISSION
    ns._fleets[1] = fleet

    # 战争结束 → recall → AVAILABLE（下个 Revenue 付最后维护）
    fleet.recall()
    assert fleet.status == FleetStatus.AVAILABLE
    assert ns.calculate_maintenance() == 4  # AVAILABLE 幸存者仍计维护

    # 下个 Population → DISBANDED → 不计维护
    fleet.disband()
    assert fleet.status == FleetStatus.DISBANDED
    assert ns.calculate_maintenance() == 0


# ════════════════════════════════════════════════════════════════════════
# T-GC-17 — calculate_maintenance 排除 DISBANDED/BUILDING/DESTROYED，含 AVAILABLE 幸存者
# ════════════════════════════════════════════════════════════════════════
def test_tgc17_calculate_maintenance_excludes_terminal_states():
    """排除集 = DESTROYED/BUILDING/DISBANDED（J 件 §5）；AVAILABLE 计入"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {"trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3}},
            "default_fleet_type": "trireme",
        }
    })
    state._naval_system = NavalSystem(state)
    ns = state.naval_system

    available = Fleet(number=1, fleet_type="trireme")
    available._strength_base = 3
    available._target_war_id = "war1"
    available._status = FleetStatus.AVAILABLE
    ns._fleets[1] = available

    building = Fleet(number=2, fleet_type="trireme")
    building._strength_base = 3
    building._target_war_id = "war1"
    building._status = FleetStatus.BUILDING
    ns._fleets[2] = building

    destroyed = Fleet(number=3, fleet_type="trireme")
    destroyed._strength_base = 3
    destroyed._target_war_id = "war1"
    destroyed.mark_destroyed(10)
    ns._fleets[3] = destroyed

    disbanded = Fleet(number=4, fleet_type="trireme")
    disbanded._strength_base = 3
    disbanded._target_war_id = "war1"
    disbanded._status = FleetStatus.DISBANDED
    ns._fleets[4] = disbanded

    assert ns.calculate_maintenance() == 4  # 仅 AVAILABLE
