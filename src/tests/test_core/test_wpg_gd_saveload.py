# src/tests/test_core/test_wpg_gd_saveload.py
"""
WP-G G4-GD G1（O 件 §1 PARITY GAP 修复）— GameState 存档纳入 WarSystem/MilitarySystem。

T-GD-11~16：真实 GameState 存档 round-trip（War 容器全量 / 25 军团状态 /
sea_control_acquired / Fleet._target_war_id / commander 绑定）+ 旧存档退化路径
（缺 _war_system/_military_system 键 → 加载不崩 + reset 空态；Legion 缺省容错；
WarStatus.DEFEATED 旧值加载不崩）。

真实生命周期链（真实 GameState/WarSystem/MilitarySystem/NavalSystem + 真实
to_dict/load_from_dict），禁手搓 DTO mock（证据红线）。
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


_ECON = {
    "economic_rules": {
        "fleet_types": {
            "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
        },
        "default_fleet_type": "trireme",
    }
}


def _build_rich_state():
    """真实生命周期链：ACTIVE（获控+舰队 ON_MISSION+军团指派）+ TRUCE（approved 条约）
    + THREAT + 多状态军团 + 待解散队列。"""
    state = GameState.create_for_testing(_ECON)
    state.turn = GameTurn(turn_number=12, year=-275)
    state._treasury = 500
    state.pyrrhic_war_won = True

    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    ws = state._war_system
    ms = state._military_system
    ns = state._naval_system

    # 战争 1：ACTIVE + 制海权已获控 + 舰队 ON_MISSION（_target_war_id）+ 军团指派
    war1 = War(
        id="war1", name="Active Naval War", strength=8, threat_level=3,
        rewards={"treasury": 100}, naval_required=True,
        enemy_naval_current=12, enemy_land_current=10, disaster_numbers=[2, 3],
        standoff_numbers=[99], unlocked_provinces=[1],
    )
    war1.commander_id = 101
    war1.status = WarStatus.ACTIVE
    war1._sea_control_acquired = True  # True 唯一写入点 = resolve_naval_battle（GC 已测）；此处仅为持久化验证置位
    ws._active_wars.append(war1)

    # 战争 2：TRUCE + approved 条约 + truce_end_turn（字段容错保留，N 件 §4）
    war2 = War(id="war2", name="Truce War", strength=5, threat_level=0)
    war2.status = WarStatus.TRUCE
    war2.commander_id = 101
    war2.set_peace_treaty({"status": "approved", "indemnity": 50, "duration": 3, "generated_turn": 10})
    war2.set_truce_end_turn(15)
    ws._truce_wars.append(war2)

    # 战争 3：THREAT
    war3 = War(id="war3", name="Threat War", strength=6, threat_level=2)
    war3.status = WarStatus.THREAT
    ws._threats.append(war3)

    # 战争 4：牌堆（未激活）
    war4 = War(id="war4", name="Deck War", strength=4, threat_level=0)
    war4.status = WarStatus.INACTIVE
    ws._war_deck.append(war4)

    # 军团：1/2 指派 ACTIVE、3 征召未指派 ACTIVE、4 DISBANDED、5 DESTROYED、6/7 待解散队列
    for num in (1, 2, 3, 4, 5, 6, 7):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit {num} failed"
    assigned, msg = ms.assign_to_war([1, 2], war1.id, 101)
    assert assigned == 2, msg
    ms.get_legion_by_number(1).promote_to_veteran()  # 老兵持久（G1-19）
    ms.get_legion_by_number(4).disband()
    ms.get_legion_by_number(5).mark_destroyed(11)
    ws.add_legions_to_disband([6, 7])
    ms.get_legion_by_number(6).disband()
    ms.get_legion_by_number(7).disband()

    # 舰队：1 号 ON_MISSION（_target_war_id=war1）、2 号 AVAILABLE（无目标）
    fleet1 = Fleet(number=1, fleet_type="trireme")
    fleet1._strength_base = 3
    fleet1._target_war_id = war1.id
    fleet1._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet1
    assert ns.assign_fleet_to_war(1, war1.id, "naval")
    fleet2 = Fleet(number=2, fleet_type="trireme")
    fleet2._strength_base = 3
    fleet2._status = FleetStatus.AVAILABLE
    ns._fleets[2] = fleet2

    return state, ws, ms, ns


# ---------------------------------------------------------------------------
# T-GD-11 — War 容器全量 round-trip（deck/discard/active/threats/truce + legions_to_disband）
# ---------------------------------------------------------------------------

def test_tgd11_war_containers_roundtrip():
    state, ws, ms, ns = _build_rich_state()
    data = state.to_dict()
    assert "_war_system" in data and "_military_system" in data, "PARITY GAP 修复：to_dict 必须含 war/military 键"

    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)
    rws = restored._war_system

    assert [w.id for w in rws._war_deck] == [w.id for w in ws._war_deck]
    assert [w.id for w in rws._war_discard] == [w.id for w in ws._war_discard]
    assert [w.id for w in rws._active_wars] == [w.id for w in ws._active_wars]
    assert [w.id for w in rws._threats] == [w.id for w in ws._threats]
    assert [w.id for w in rws._truce_wars] == [w.id for w in ws._truce_wars]
    assert rws._legions_to_disband == ws._legions_to_disband == [6, 7]

    # 关键 War 字段逐项（status/commander/peace_treaty/truce_end_turn/legion_numbers）
    r1 = rws.get_war_by_id("war1")
    assert r1.status == WarStatus.ACTIVE
    assert r1.commander_id == 101
    assert r1.sea_control_acquired is True
    r2 = rws.get_war_by_id("war2")
    assert r2.status == WarStatus.TRUCE
    assert r2.peace_treaty == {"status": "approved", "indemnity": 50, "duration": 3, "generated_turn": 10}
    assert r2.truce_end_turn == 15
    r3 = rws.get_war_by_id("war3")
    assert r3.status == WarStatus.THREAT
    assert r3.threat_level == 2


# ---------------------------------------------------------------------------
# T-GD-12 — 25 军团状态 round-trip（status/war_id/commander_id/is_veteran/_destroyed_turn/_legion_type）
# ---------------------------------------------------------------------------

def test_tgd12_legions_roundtrip():
    state, ws, ms, ns = _build_rich_state()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rms = restored._military_system

    assert len(rms._legions) == 25
    for num in range(1, 26):
        orig = ms.get_legion_by_number(num)
        new = rms.get_legion_by_number(num)
        assert new.status == orig.status, f"legion {num} status"
        assert new.war_id == orig.war_id, f"legion {num} war_id"
        assert new.commander_id == orig.commander_id, f"legion {num} commander_id"
        assert new.is_veteran == orig.is_veteran, f"legion {num} is_veteran"
        assert new._destroyed_turn == orig._destroyed_turn, f"legion {num} destroyed_turn"
        assert new._legion_type == orig._legion_type, f"legion {num} legion_type"

    # 多状态显式断言
    assert rms.get_legion_by_number(1).status == LegionStatus.ACTIVE
    assert rms.get_legion_by_number(1).is_veteran is True
    assert rms.get_legion_by_number(2).status == LegionStatus.ACTIVE
    assert rms.get_legion_by_number(4).status == LegionStatus.DISBANDED
    assert rms.get_legion_by_number(5).status == LegionStatus.DESTROYED
    assert rms.get_legion_by_number(5)._destroyed_turn == 11
    assert rms.get_legion_by_number(8).status == LegionStatus.UNRAISED


# ---------------------------------------------------------------------------
# T-GD-13 — sea_control_acquired（GC 字段）与 Fleet._target_war_id（S32）
# ---------------------------------------------------------------------------

def test_tgd13_sea_control_and_fleet_provenance_roundtrip():
    state, ws, ms, ns = _build_rich_state()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rws = restored._war_system
    rns = restored._naval_system

    assert rws.get_war_by_id("war1").sea_control_acquired is True
    assert rns.get_fleet(1) is not None
    assert rns.get_fleet(1)._target_war_id == "war1"
    assert rns.get_fleet(1).assigned_war_id == "war1"
    assert rns.get_fleet(1).status == FleetStatus.ON_MISSION
    assert rns.get_fleet(2)._target_war_id is None
    assert rns.get_fleet(2).status == FleetStatus.AVAILABLE


# ---------------------------------------------------------------------------
# T-GD-14 — 旧存档退化：缺 _war_system/_military_system 键 → 加载不崩 + reset 空态
# ---------------------------------------------------------------------------

def test_tgd14_legacy_save_degradation():
    state, ws, ms, ns = _build_rich_state()
    data = state.to_dict()
    data.pop("_war_system")
    data.pop("_military_system")

    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)  # 不崩

    # 退化路径：保留 reset() 重建的 wars.json 空运行态 + 25 UNRAISED 军团
    assert restored._war_system is not None
    assert restored._military_system is not None
    assert len(restored._military_system._legions) == 25
    assert all(l.status == LegionStatus.UNRAISED for l in restored._military_system._legions)
    assert restored._war_system._legions_to_disband == []


# ---------------------------------------------------------------------------
# T-GD-15 — Legion 缺省容错 + WarStatus.DEFEATED 旧值加载不崩
# ---------------------------------------------------------------------------

def test_tgd15_legion_defaults_and_defeated_status():
    state, ws, ms, ns = _build_rich_state()
    data = state.to_dict()
    # 手工构造旧存档形态：Legion 缺 is_veteran/_destroyed_turn；war 含 DEFEATED 旧值
    data["_military_system"]["_legions"][0].pop("is_veteran", None)
    data["_military_system"]["_legions"][0].pop("_destroyed_turn", None)
    data["_war_system"]["_active_wars"][0]["status"] = "defeated"

    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)  # 不崩

    l1 = restored._military_system.get_legion_by_number(1)
    assert l1.is_veteran is False  # 缺省 False
    assert l1._destroyed_turn == 0  # 缺省 0
    r1 = restored._war_system.get_war_by_id("war1")
    assert r1.status == WarStatus.DEFEATED  # 枚举值保留（N 件 §3：禁新写入，旧值加载容错）


# ---------------------------------------------------------------------------
# T-GD-16 — save/load 后 commander 绑定一致（War/Legion/Fleet，Q 件 I 终验）
# ---------------------------------------------------------------------------

def test_tgd16_commander_binding_roundtrip():
    state, ws, ms, ns = _build_rich_state()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rws = restored._war_system
    rms = restored._military_system
    rns = restored._naval_system

    r1 = rws.get_war_by_id("war1")
    assert r1.commander_id == 101
    for num in (1, 2):
        assert rms.get_legion_by_number(num).war_id == "war1"
        assert rms.get_legion_by_number(num).commander_id == 101
    # 舰队战力 martial 权威 = War Commander（G1-20/H 件 §4；GC 收敛后 round-trip 一致）
    assert rns.get_fleet(1).get_combat_strength(restored) == 4 + 3  # martial 4 + trireme base 3


# ---------------------------------------------------------------------------
# 加载后继续下一战（S32 集成：获控战争加载后可直接陆战，无 stale flag 干扰）
# ---------------------------------------------------------------------------

def test_tgd16b_loaded_war_continues_land_battle():
    state, ws, ms, ns = _build_rich_state()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    r1 = restored._war_system.get_war_by_id("war1")
    # 获控状态持久 → 加载后同战可跳过海战直达陆战路径（R-06 判定面）
    assert r1.sea_control_acquired is True
    assert r1.naval_required is True
