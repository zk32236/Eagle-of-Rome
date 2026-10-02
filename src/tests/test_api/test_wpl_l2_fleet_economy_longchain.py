# src/tests/test_api/test_wpl_l2_fleet_economy_longchain.py
"""WP-L L2 — LC-L2-01..06 长链验收（Naval Maintenance / Fleet Economy Rule）。

冻结设计：`02-sa-design/L2/L2-SA-Development-Task.md` **v1.2**
  FC-L2-01..13（§3 冻结契约权威）/ §9 LC-L2-01..06 / §10 L2-AC-05a–e。
轨迹：RED（旧代码短款自动解散 / 无相关战争自动解散 / DISBANDED 短路 THREAT 预算）
  → GREEN（WU-1/2/3 实现后）。

纪律：真实生产路径（GameState/WarSystem/NavalSystem/EconomicService/population_api），
禁 monkeypatch 函数本体；确定性 fixture 经真实 API/实体构造。
"""
import logging

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.contract import ContractStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.service.economic_service import EconomicService
from src.api import population_api


_ECON_CONFIG = {
    "economic_rules": {
        "fleet_types": {
            "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
            "quinquereme": {"build_cost": 60, "build_time": 1, "maintenance_cost": 6, "strength_base": 5},
        },
        "default_fleet_type": "trireme",
        "faction_stipend": 0,
    },
    "testing": {"bypass_player_check": True},
}


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _capture(state):
    state._config._config["logging"] = {
        "enabled": True, "file_path": "/tmp/eor_wpl_l2_lc.log", "log_level": "INFO",
    }
    state._setup_logging()
    handler = _CaptureHandler()
    state._logger.addHandler(handler)
    return handler


def _msgs(handler):
    return [r.getMessage() for r in handler.records]


def _state(treasury=500):
    state = GameState.create_for_testing({k: dict(v) for k, v in _ECON_CONFIG.items()})
    state.turn = GameTurn(turn_number=10, year=-280)
    state._treasury = treasury
    state.pyrrhic_war_won = True
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    return state, faction


def _add_fleet(state, number, fleet_type="trireme", status=FleetStatus.AVAILABLE, target=None):
    fleet = Fleet(number=number, fleet_type=fleet_type)
    fleet._strength_base = state.config.get("economic_rules.fleet_types", {}).get(
        fleet_type, {}).get("strength_base", 3)
    fleet._target_war_id = target
    fleet._status = status
    state._naval_system._fleets[number] = fleet
    return fleet


def _make_war(state, war_id, naval_required=True, status=WarStatus.ACTIVE, enemy_naval=10,
              peace_treaty=None, commander_id=None):
    war = War(
        id=war_id, name=f"War {war_id}", strength=8, threat_level=3,
        rewards={"treasury": 100}, naval_required=naval_required,
        enemy_naval_current=enemy_naval, enemy_naval_max=enemy_naval,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = status
    war.commander_id = commander_id
    if peace_treaty is not None:
        war.set_peace_treaty(peace_treaty)
    if status == WarStatus.ACTIVE:
        state._war_system._active_wars.append(war)
    elif status == WarStatus.TRUCE:
        state._war_system._truce_wars.append(war)
    elif status == WarStatus.RESOLVED:
        state._war_system._war_discard.append(war)
    elif status == WarStatus.THREAT:
        state._war_system._threats.append(war)
    return war


# ════════════════════════════════════════════════════════════════════════
# LC-L2-01 — Shortfall：全额扣费、国库可为负、零解散（FC-L2-02/03/11）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_01_shortfall_full_charge_treasury_negative_no_disband():
    state, _ = _state(treasury=5)
    ns = state.naval_system
    _add_fleet(state, 1)
    _add_fleet(state, 2)
    handler = _capture(state)
    try:
        dto = EconomicService(state).apply_naval_maintenance()
        assert dto["available"] is True
        assert dto["total"] == 8                       # 2 × trireme 4
        assert dto["charged"] == 8                     # 全额扣费（旧行为：短款解散）
        assert dto["charged"] == dto["treasury_before"] - dto["treasury_after"]
        assert dto["treasury_after"] == -3             # 国库可为负（FC-L2-03）
        assert state.treasury == -3
        assert dto["disbanded"] == 0
        assert dto["disbanded_fleet_ids"] == []
        assert dto["fleet_costs"] == []
        assert dto["unpaid"] == 0
        assert dto["success"] is True
        assert dto["required_after_disband"] == 8
        assert dto["shortfall"] == 3                   # max(0, charged - before)
        assert dto["initial_shortfall"] == 3
        for n in (1, 2):
            assert ns.get_fleet(n).status == FleetStatus.AVAILABLE   # 不解散任何舰队
        assert not [m for m in _msgs(handler) if "type=naval_fleet_disbanded" in m]
        assert [m for m in _msgs(handler) if "type=naval_maintenance" in m]
    finally:
        handler.close()
        state.close_logging()


# ════════════════════════════════════════════════════════════════════════
# LC-L2-02 — Bankruptcy takeover（既有失败条件接管，FC-L2-04）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_02_bankruptcy_takeover_counter_and_game_over():
    state, _ = _state(treasury=-5)
    assert state.get_economic_rule("national_opex_deficit_limit", 3) == 3
    assert state.treasury_deficit_turns == 0
    r1 = state.check_victory_conditions()
    assert state.treasury_deficit_turns == 1
    assert r1["game_over"] is False
    r2 = state.check_victory_conditions()
    assert state.treasury_deficit_turns == 2
    assert r2["game_over"] is False
    r3 = state.check_victory_conditions()
    assert state.treasury_deficit_turns == 3
    assert r3["game_over"] is True
    conds = {c["type"]: c for c in r3["conditions"]}
    assert conds["bankruptcy"]["triggered"] is True
    assert conds["bankruptcy"]["critical"] is True


# ════════════════════════════════════════════════════════════════════════
# LC-L2-03 — Unused retained + war-end / approved-TRUCE retired（FC-L2-05/06/08）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_03_i_no_relevant_naval_war_fleet_retained():
    state, _ = _state()
    ns = state.naval_system
    _add_fleet(state, 1)  # AVAILABLE, no target war, no wars at all
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == []                       # 无相关海战战争 → 保留（FC-L2-05）
    assert ns.get_fleet(1).status == FleetStatus.AVAILABLE
    assert ns.calculate_maintenance() == 4              # 仍维护-bearing（FC-L2-01）


def test_lc_l2_03_ii_resolved_target_fleet_retired():
    state, _ = _state()
    ns = state.naval_system
    war = _make_war(state, "war_a", status=WarStatus.RESOLVED)
    _add_fleet(state, 1, target=war.id)                 # AVAILABLE + RESOLVED target
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == [1]                      # 战争结束退役（FC-L2-06）
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED
    assert ns.get_fleet(1).destroyed_turn == 0          # 行政退役非 DESTROYED（FC-L2-07）


def test_lc_l2_03_iii_approved_truce_fleet_retired():
    state, _ = _state()
    ns = state.naval_system
    _make_war(state, "war_p", status=WarStatus.TRUCE,
              peace_treaty={"status": "approved", "indemnity": 50, "duration": 3, "generated_turn": 1})
    _add_fleet(state, 1)                                # AVAILABLE (released)
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == [1]                      # approved-TRUCE（未 RESOLVED）→ 退役（ODR-L-08）
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED


def test_lc_l2_03_approved_truce_fleet_retains_target_provenance():
    state, _ = _state()
    ns = state.naval_system
    war = _make_war(state, "war_p", status=WarStatus.TRUCE,
                    peace_treaty={"status": "approved", "indemnity": 0, "duration": 3, "generated_turn": 1})
    _add_fleet(state, 1, target=war.id)
    population_api.process_population_disbandments(state)
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED
    assert ns.get_fleet(1)._target_war_id == war.id     # provenance 保留（G1-12）


# ════════════════════════════════════════════════════════════════════════
# LC-L2-04 — Multi-war narrow fix preserved（FC-L2-06 / D2.5 决策序）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_04_resolved_a_retired_active_b_fleet_retained():
    state, _ = _state()
    ns = state.naval_system
    war_a = _make_war(state, "war_a", status=WarStatus.RESOLVED)
    war_b = _make_war(state, "war_b", status=WarStatus.ACTIVE)
    _add_fleet(state, 1, fleet_type="trireme", target=war_a.id)   # A 的 released AVAILABLE
    fb = _add_fleet(state, 2, fleet_type="quinquereme", target=war_b.id)
    assert ns.assign_fleet_to_war(2, war_b.id, "naval") is True    # B 的 live Fleet ON_MISSION
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == [1]                       # A(resolved) 退役，B(live) 不连坐
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED
    assert ns.get_fleet(2).status == FleetStatus.ON_MISSION
    assert ns.calculate_maintenance() == 6               # 仅 B quinquereme 6


def test_lc_l2_04_variant_approved_truce_a_with_active_naval_b_keeps_all():
    """D2.5 决策序：(ii) ACTIVE naval war 先于 (iii) approved-TRUCE → 全部保留。"""
    state, _ = _state()
    ns = state.naval_system
    _make_war(state, "war_a", status=WarStatus.TRUCE,
              peace_treaty={"status": "approved", "indemnity": 0, "duration": 3, "generated_turn": 1})
    war_b = _make_war(state, "war_b", status=WarStatus.ACTIVE)
    _add_fleet(state, 1, target="war_a")
    _add_fleet(state, 2, target=war_b.id)
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == []                        # ACTIVE naval 阻止退役（FC-L2-05）
    assert ns.get_fleet(1).status == FleetStatus.AVAILABLE
    assert ns.get_fleet(2).status == FleetStatus.AVAILABLE


# ════════════════════════════════════════════════════════════════════════
# LC-L2-05 — Maintenance caliber（FC-L2-01 / FC-L2-11）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_05_maintenance_caliber_excludes_terminal_states():
    state, _ = _state(treasury=500)
    ns = state.naval_system
    war = _make_war(state, "war_a", status=WarStatus.ACTIVE)
    _add_fleet(state, 1, "trireme", FleetStatus.AVAILABLE, target=war.id)
    f2 = _add_fleet(state, 2, "trireme", FleetStatus.AVAILABLE, target=war.id)
    assert ns.assign_fleet_to_war(2, war.id, "naval") is True    # ON_MISSION
    _add_fleet(state, 3, "trireme", FleetStatus.BUILDING, target=war.id)
    f4 = _add_fleet(state, 4, "trireme", FleetStatus.AVAILABLE, target=war.id)
    f4.mark_destroyed(10)
    f5 = _add_fleet(state, 5, "trireme", FleetStatus.AVAILABLE, target=war.id)
    f5.disband()
    assert ns.calculate_maintenance() == 8               # 仅 AVAILABLE + ON_MISSION 计入
    dto = EconomicService(state).apply_naval_maintenance()
    assert dto["total"] == 8
    assert dto["charged"] == 8
    assert state.treasury == 492
    assert dto["disbanded"] == 0


# ════════════════════════════════════════════════════════════════════════
# LC-L2-06 — THREAT budget after truce expiry（L2-T3 / FC-L2-13）
# ════════════════════════════════════════════════════════════════════════
def test_lc_l2_06_disbanded_fleet_does_not_short_circuit_threat_budget():
    state, _ = _state()
    ns = state.naval_system
    war = _make_war(state, "war_truce", status=WarStatus.TRUCE,
                    peace_treaty={"status": "approved", "indemnity": 0, "duration": 3, "generated_turn": 9})
    war.set_truce_end_turn(4)                            # current turn 10 → expired
    _add_fleet(state, 1, target=war.id)                  # AVAILABLE bound to the truce war

    # approved-TRUCE（未 RESOLVED）→ Population 退役（DISBANDED，保留 _target_war_id）
    result = population_api.process_population_disbandments(state)
    assert result["fleets"] == [1]
    assert ns.get_fleet(1).status == FleetStatus.DISBANDED
    assert ns.get_fleet(1)._target_war_id == war.id

    # 停战到期 → TRUCE → THREAT
    expired = state.process_truce_expiry()
    assert expired == [war.name]
    assert war.status == WarStatus.THREAT

    # THREAT 阶段建造预算：DISBANDED 舰队不得短路（FC-L2-13）
    contracts = ns.generate_construction_contracts(current_turn=10)
    assert len(contracts) == 1
    assert contracts[0]._target_war_id == war.id
    assert contracts[0].status == ContractStatus.PENDING
    assert contracts[0]._is_fleet_construction is True


def test_lc_l2_06_live_fleet_still_short_circuits_threat_budget():
    """对照（FC-L2-13 边界）：存活（非 DISBANDED）同战舰队仍短路 THREAT 建造预算。"""
    state, _ = _state()
    ns = state.naval_system
    war = _make_war(state, "war_t", status=WarStatus.THREAT)
    _add_fleet(state, 1, target=war.id)                  # AVAILABLE, status ∉ {DESTROYED, DISBANDED}
    contracts = ns.generate_construction_contracts(current_turn=10)
    assert contracts == []                               # 有存活舰队 → 不生成新预算


if __name__ == "__main__":
    import unittest
    unittest.main()
