# src/tests/fixtures/wpgr4_fixtures.py
"""WP-G-R4 (SA v1.7 §9.1/§9.2, DA-Plan §1 S0) — FIX-R4-01~09 builders.

纪律（§3.4 config 取证 / §9.1 seam）：
- 所有 state 经 GameState.create_for_testing(task-local 内存 config) 构造——**不读工作树
  game_config.json override**（取证绑定 committed 默认 force_battle_result="" /
  force_naval_result="" / tribune_veto_chance=0.3）；force 键仅在 fixture 需要时显式设置。
- 真实 GameState/Player/Figure/War/Legion/Fleet 实体；Bootstrap 只声明「已到合法
  Senate/Combat 入口」外生前置（mortality~population executed → senate 当前阶段；
  senate executed → combat 当前阶段），**不以手工 phase executed 替代被测进程**。
- joined 链的 Takeover/submit/vote/resolve/advance/attack/confirm 必须全真公开调用
  （senate_api/combat_api）——本模块只提供状态前置，不代跑业务。
- Fleet predecessor = canonical R3 contract→construction→assign 链不在本模块重建：
  S2+ 的 ready 舰队以 naval.assign_fleet_to_war（合法公开 assign）生产；单元负例的
  损坏对象一律 manifest 标注 FAULT_INJECTION，不冒充生命周期来源。
- 复用 R3 helper 结构（create_for_testing + 实体直建），不复用其结论/假默认。
"""

from typing import Any, Dict, List, Optional

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem

# ---------------------------------------------------------------------------
# 固定标识（FIX-R4-01 production-shape 前驱，SA v1.7 §9.2/§9.2b）
# ---------------------------------------------------------------------------
P1 = "player1"
F1 = "optimates"
C1_ID = 1
WAR_A = "pyrrhic_war"       # commanderless ACTIVE，非 naval（-282 历史卡标识）
WAR_B = "first_punic_war"   # TRUCE+pending，naval-required（-279 历史卡标识）


def _base_config(**testing_overrides: Any) -> Dict[str, Any]:
    """task-local 内存 config（committed 默认语义；不依赖工作树 game_config override）。"""
    testing = {
        "force_battle_result": "",          # committed 默认 ""（工作树 "victory" 为 Owner 取证现场，禁读）
        "force_naval_result": "",           # committed 默认 ""（工作树同）
        "tribune_veto_chance": 0.3,         # committed 默认 0.3（工作树 0.0 override 禁读）
        "auto_senate": False,
        "propose_war_chance": 0.0,
        "always_declare": False,
        "bypass_player_check": False,
    }
    testing.update(testing_overrides)
    return {
        "testing": testing,
        "economic_rules": {
            "legion_recruit_cost": 4,
            "legion_maintenance_base": 8,
            "veteran_maintenance_bonus": 1,
            "senate_war_legions": {"default": 4, "min": 1, "cap_mode": "available_pool"},
            "senate_land": {"default_percent": 0.10},
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
                "quadrireme": {"build_cost": 120, "build_time": 2, "maintenance_cost": 6, "strength_base": 4},
            },
            "default_fleet_type": "trireme",
        },
        "political_rules": {
            "land_proposal": {"sale_chance": 0.0, "distribution_chance": 0.0},
        },
    }


def make_base_state(
    turn_number: int = 1,
    year: int = -264,
    phases_to_senate: bool = True,
    config: Optional[Dict[str, Any]] = None,
) -> GameState:
    """Bootstrap：合法 Senate/Combat 入口（mortality/revenue/forum/population 已 executed）。"""
    state = GameState.create_for_testing(config if config is not None else _base_config())
    state.turn = GameTurn(turn_number=turn_number, year=year)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    if phases_to_senate:
        for phase in ["mortality", "revenue", "forum", "population"]:
            state.mark_phase_executed(phase)
    return state


def add_faction(state: GameState, faction_id: str = F1, treasury: int = 500) -> Faction:
    faction = Faction(id=faction_id, name=faction_id.capitalize(), treasury=treasury)
    state.add_faction(faction)
    return faction


def add_player(state: GameState, player_id: str = P1, faction_id: str = F1,
               player_type: str = "human") -> Player:
    player = Player(player_id, faction_id, PlayerType(player_type))
    state.add_player(player)
    state._turn_order = [player_id]
    state.set_current_player(player_id)
    return player


def add_consul(state: GameState, faction: Faction, figure_id: int = C1_ID,
               name: str = "Consul Aemilius", influence: int = 80) -> Figure:
    consul = Figure(id=figure_id, name=name, faction_id=faction.id, age=45)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = influence
    state.add_member(consul)
    faction.member_ids.append(figure_id)
    return consul


def make_war(
    war_id: str,
    name: str,
    status: WarStatus = WarStatus.ACTIVE,
    naval_required: bool = False,
    enemy_naval: int = 0,
    enemy_land: int = 0,
    threat_level: int = 3,
    strength: int = 5,
    commander_id: Optional[int] = None,
    treaty: Optional[Dict[str, Any]] = None,
) -> War:
    war = War(
        id=war_id, name=name, war_type=WarType.FOREIGN,
        strength=strength, threat_level=threat_level,
        rewards={"treasury": 100},
        naval_required=naval_required,
        enemy_naval_current=enemy_naval,
        enemy_land_current=enemy_land,
        disaster_numbers=[2, 3, 4],
        standoff_numbers=[99],
    )
    war.status = status
    war.commander_id = commander_id
    if treaty is not None:
        war.set_peace_treaty(treaty)
    return war


def attach_active(state: GameState, war: War) -> War:
    state._war_system._active_wars.append(war)
    return war


def attach_truce(state: GameState, war: War) -> War:
    state._war_system._truce_wars.append(war)
    return war


def recruit_legions_for_war(state: GameState, war: War, commander_id: int,
                            count: int = 1) -> List[int]:
    """真实 producer 链：recruit_multiple → assign_to_war → war.add_legion_number。"""
    ms = state.get_military_system()
    results = ms.recruit_multiple(count)
    numbers = [number for number, success, *_ in results if success]
    if numbers:
        ms.assign_to_war(numbers, war.id, commander_id)
        for number in numbers:
            war.add_legion_number(number)
    return numbers


def add_ready_fleets(state: GameState, war: War, count: int = 1,
                     start_number: int = 1) -> List[Fleet]:
    """真实公开 assign 生产 ON_MISSION 舰队（canonical naval.assign_fleet_to_war）。"""
    ns = state.naval_system
    fleets = []
    for i in range(count):
        number = start_number + i
        fleet = Fleet(number=number, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._target_war_id = war.id
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[number] = fleet
        ok = ns.assign_fleet_to_war(number, war.id, "naval")
        assert ok, f"assign fleet {number} failed"
        fleets.append(fleet)
    return fleets


def exhaust_legion_pool(state: GameState) -> None:
    """N0 零池附例：征召全部可用军团（真实链）→ available pool == 0。"""
    ms = state.get_military_system()
    numbers = [legion.number for legion in ms.get_available_legions()]
    if numbers:
        ms.recruit_multiple(len(numbers))


# ---------------------------------------------------------------------------
# FIX-R4-01 — 非空主样本（SA v1.7 §9.2 FIX-R4-01 / §9.2b，O5 恢复可构造）
#   P1/F1 + eligible Consul C1 留城 + War A=pyrrhic_war commanderless ACTIVE 非 naval
#   + War B=first_punic_war TRUCE+pending naval-required + public_land>0（land:sale 另
#   一合法非 Takeover 提案可构造）+ 真实 reinforcement 池/国库。
# ---------------------------------------------------------------------------
def build_fix01(
    treasury: int = 500,
    public_land: int = 500,
    zero_pool: bool = False,
    with_war_b: bool = True,
) -> Dict[str, Any]:
    state = make_base_state(turn_number=1, year=-282)
    faction = add_faction(state, treasury=treasury)
    add_player(state)
    consul = add_consul(state, faction)
    state.add_national_public_land(public_land)

    war_a = make_war(WAR_A, "Pyrrhic War", status=WarStatus.ACTIVE,
                     naval_required=False, enemy_land=6, threat_level=4)
    attach_active(state, war_a)
    wars = [war_a]
    if with_war_b:
        war_b = make_war(
            WAR_B, "First Punic War", status=WarStatus.TRUCE,
            naval_required=True, enemy_naval=20, enemy_land=4,
            treaty={"indemnity": 80, "duration": 3, "status": "pending", "generated_turn": 1},
        )
        attach_truce(state, war_b)
        wars.append(war_b)
    if zero_pool:
        exhaust_legion_pool(state)

    return {
        "state": state,
        "faction": faction,
        "player_id": P1,
        "consul": consul,
        "war_a": war_a,
        "war_b": war_b if with_war_b else None,
        "wars": wars,
        "manifest": {
            "fixture": "FIX-R4-01",
            "fixed_ids": {"player": P1, "faction": F1, "consul": C1_ID,
                          "war_a": WAR_A, "war_b": WAR_B},
            "entry": "senate-current (mortality~population executed)",
            "note": "C1 留城（is_absent=False）→ proposal_control HUMAN → 另一合法非空提案可提交（O5）",
        },
    }


# ---------------------------------------------------------------------------
# FIX-R4-02 — naval-required ACTIVE + Commander/live legions + sea=false + 零 ready
# ---------------------------------------------------------------------------
def build_fix02(naval_force: str = "", land_force: str = "",
                ready_override: Optional[str] = None) -> Dict[str, Any]:
    """ready_override ∈ {None, 'building','destroyed','disbanded','available','missing'}
    供参数化负例；FAULT_INJECTION 状态直接置位（manifest 标注，不冒充生命周期来源）。"""
    config = _base_config()
    cfg = config["testing"]
    cfg["force_naval_result"] = naval_force
    cfg["force_battle_result"] = land_force
    state = make_base_state(turn_number=10, year=-280, config=config)
    state.pyrrhic_war_won = True
    state._treasury = 500
    faction = add_faction(state)
    add_player(state, player_id=P1, faction_id=F1)
    consul = add_consul(state, faction, figure_id=101, name="Test Commander")
    consul.influence = 10

    war = make_war("naval_gate_war", "Naval Gate War", status=WarStatus.ACTIVE,
                   naval_required=True, enemy_naval=18, enemy_land=6,
                   commander_id=consul.id, threat_level=4)
    attach_active(state, war)
    ms = state.get_military_system()
    recruit_legions_for_war(state, war, consul.id, count=2)
    legions = ms.get_legions_for_battle(war.id)

    ns = state.naval_system
    fleets = []
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._target_war_id = war.id
    fleet._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet
    if ready_override is None:
        # 零 ready：保持 AVAILABLE（未指派）→ assigned_fleet_ids 空 → NOT_READY
        pass
    elif ready_override == "assigned-ok":
        assert ns.assign_fleet_to_war(1, war.id, "naval")
        fleets.append(fleet)
    elif ready_override == "missing":
        # FAULT_INJECTION：war 侧指派引用缺实体（assigned_fleet_ids=[1] 但 _fleets 无 1）
        assert ns.assign_fleet_to_war(1, war.id, "naval")
        del ns._fleets[1]
    else:
        # FAULT_INJECTION 负例：指派后直接改状态（损坏/建造中/已毁/已解散/错战绑定）
        assert ns.assign_fleet_to_war(1, war.id, "naval")
        if ready_override == "building":
            fleet._status = FleetStatus.BUILDING
        elif ready_override == "destroyed":
            fleet._status = FleetStatus.DESTROYED
        elif ready_override == "disbanded":
            fleet._status = FleetStatus.DISBANDED
        elif ready_override == "available":
            fleet._status = FleetStatus.AVAILABLE
        elif ready_override == "wrong-war":
            war.assigned_fleet_ids = []  # 损坏绑定：清 war 侧，留 fleet._target_war_id 错位
        fleets.append(fleet)

    return {
        "state": state, "faction": faction, "player_id": P1,
        "commander": consul, "war": war, "fleets": fleets,
        "legions": legions,
        "manifest": {
            "fixture": "FIX-R4-02",
            "config_delta": {"force_naval_result": naval_force, "force_battle_result": land_force},
            "ready_override": ready_override,
            "fault_injection": ready_override in ("building", "destroyed", "disbanded",
                                                  "available", "wrong-war"),
        },
    }


# ---------------------------------------------------------------------------
# FIX-R4-03..07 — ready fleets + live Legions/Commander（combat dual-stage 前置）
# ---------------------------------------------------------------------------
def _combat_war_state(war_id: str = "naval_war", naval_force: str = "",
                      land_force: str = "", n_fleets: int = 1,
                      legions: int = 2, with_treaty: bool = False,
                      consul_absent: bool = True, turn_number: int = 10) -> Dict[str, Any]:
    config = _base_config()
    cfg = config["testing"]
    cfg["force_naval_result"] = naval_force
    cfg["force_battle_result"] = land_force
    state = make_base_state(turn_number=turn_number, year=-280, config=config)
    for phase in ["senate"]:
        state.mark_phase_executed(phase)          # combat 当前阶段（外生前置）
    state.pyrrhic_war_won = True
    state._treasury = 500
    faction = add_faction(state)
    add_player(state)
    commander = Figure(id=101, name="Test Commander", faction_id=F1, age=40)
    commander.martial = 4
    commander.influence = 10
    commander.class_tier = ClassTier.NOBILE
    commander.office = "proconsul"
    commander.is_absent = consul_absent
    state.add_member(commander)
    faction.member_ids.append(101)

    war = make_war(war_id, "Naval War", status=WarStatus.ACTIVE,
                   naval_required=True, enemy_naval=18, enemy_land=6,
                   commander_id=101, threat_level=4)
    attach_active(state, war)
    if with_treaty:
        war.set_peace_treaty({"indemnity": 60, "duration": 3, "status": "pending",
                              "generated_turn": 1})
    recruited = recruit_legions_for_war(state, war, 101, count=legions)
    fleets = add_ready_fleets(state, war, count=n_fleets) if n_fleets else []
    return {
        "state": state, "faction": faction, "player_id": P1,
        "commander": commander, "war": war, "fleets": fleets,
        "legion_numbers": recruited,
        "manifest": {
            "fixture": "combat-ready-base",
            "config_delta": {"force_naval_result": naval_force, "force_battle_result": land_force},
            "n_fleets": n_fleets, "legions": legions,
            "fleet_producer": "naval.assign_fleet_to_war (canonical ON_MISSION)",
        },
    }


def build_fix03(naval_force: str = "STALEMATE", land_force: str = "TRIUMPH") -> Dict[str, Any]:
    """ready fleet + sea=false → Naval STALEMATE → Land NOT_EXECUTED（land 可设 TRIUMPH 证明没被消费）。"""
    ctx = _combat_war_state(naval_force=naval_force, land_force=land_force, n_fleets=1, legions=2)
    ctx["manifest"]["fixture"] = "FIX-R4-03"
    return ctx


def build_fix04(n_fleets: int = 5, naval_force: str = "DEFEAT",
                land_force: str = "TRIUMPH") -> Dict[str, Any]:
    """N 艘 ready 舰 + live Legions/Commander：真实损失采样（DEFEAT ceil(N/2)/DISASTER N）。"""
    ctx = _combat_war_state(naval_force=naval_force, land_force=land_force,
                            n_fleets=n_fleets, legions=2)
    ctx["manifest"]["fixture"] = "FIX-R4-04"
    return ctx


def build_fix05(naval_force: str = "VICTORY", land_force: str = "DEFEAT") -> Dict[str, Any]:
    ctx = _combat_war_state(naval_force=naval_force, land_force=land_force, n_fleets=1, legions=2)
    ctx["manifest"]["fixture"] = "FIX-R4-05"
    return ctx


def build_fix06(naval_force: str = "TRIUMPH", land_force: str = "STALEMATE") -> Dict[str, Any]:
    """Naval TRIUMPH + Land draw → 合法 treaty decider → TRUCE pending（land 值经 canonical CRT）。"""
    ctx = _combat_war_state(naval_force=naval_force, land_force=land_force, n_fleets=1, legions=2)
    ctx["manifest"]["fixture"] = "FIX-R4-06"
    return ctx


def build_fix07(naval_force: str = "VICTORY", land_force: str = "TRIUMPH") -> Dict[str, Any]:
    """Naval VICTORY + Land TRIUMPH → War RESOLVED / recall / sea clear（stage 快照 vs final 海权不同）。"""
    ctx = _combat_war_state(naval_force=naval_force, land_force=land_force, n_fleets=1, legions=2)
    ctx["manifest"]["fixture"] = "FIX-R4-07"
    return ctx


# ---------------------------------------------------------------------------
# FIX-R4-08/09 — 非海军合法 war（真实 Commander/Legions）+ Forum 资格链
# ---------------------------------------------------------------------------
def build_fix08(land_force: str = "VICTORY", war_id: str = WAR_A) -> Dict[str, Any]:
    config = _base_config()
    config["testing"]["force_battle_result"] = land_force
    state = make_base_state(turn_number=10, year=-280, config=config)
    for phase in ["senate"]:
        state.mark_phase_executed(phase)
    state.pyrrhic_war_won = True
    state._treasury = 500
    faction = add_faction(state)
    add_player(state)
    commander = Figure(id=101, name="Victory Commander", faction_id=F1, age=40)
    commander.martial = 4
    commander.influence = 30
    commander.class_tier = ClassTier.NOBILE
    commander.office = "proconsul"
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    war = make_war(war_id, "Pyrrhic War", status=WarStatus.ACTIVE,
                   naval_required=False, enemy_land=6, commander_id=101, threat_level=4)
    attach_active(state, war)
    recruited = recruit_legions_for_war(state, war, 101, count=2)
    return {
        "state": state, "faction": faction, "player_id": P1,
        "commander": commander, "war": war, "legion_numbers": recruited,
        "manifest": {
            "fixture": "FIX-R4-08",
            "config_delta": {"force_battle_result": land_force, "force_naval_result": ""},
        },
    }


def build_fix09(land_force: str = "VICTORY", war_id: str = WAR_A) -> Dict[str, Any]:
    """FIX08 真实 ordinary VICTORY 产 RESOLVED + share>0 + alive 候选（Forum 资格 DATA 前置）。"""
    ctx = build_fix08(land_force=land_force, war_id=war_id)
    ctx["manifest"]["fixture"] = "FIX-R4-09"
    return ctx
