# src/tests/test_api/test_escg7q1_g1_14_notouch.py
"""ESC-WPJ-G7Q1-01 / ESC-S1 — T-ESC-02 G1-14 实质规则 no-touch（AC-02）。

冻结设计（`02-sa-design/`）：
- FC-ESC-04：G1-14 实质规则逐字不变 —— 解散**实际发生在 Population 阶段**；
  下一 Revenue 收最后维护；**不在**停战批准的元老院阶段执行。
- FC-ESC-02：canonical `process_population_disbandments` exactly-once。

守护链（复用 `test_wpg_g3c_treaty_lifecycle` 的停战/和约链构造）：
停战批准点 → 军团仅释放 AVAILABLE（不即时解散）、无 disbandment marker；
Population 入口处理（= M1 触发的同一 canonical）→ 恰一次解散（deescalated 面）。
"""
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import population_api


def _treaty_state():
    """构造「TRUCE + 权威 pending 条约 + 军团/舰队/指挥官绑定」的最小时序状态。"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 1,
                            "maintenance_cost": 4, "strength_base": 3},
            },
            "default_fleet_type": "trireme",
            "legion_recruit_cost": 10,
            "legion_maintenance_base": 2,
            "veteran_maintenance_bonus": 1,
        },
    })
    state.turn = GameTurn(turn_number=1, year=-264)
    state._treasury = 1000
    state.pyrrhic_war_won = True
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    commander = Figure(id=1, name="指挥官", faction_id="optimates", age=50)
    commander.office = "proconsul"
    commander.is_absent = True
    commander.class_tier = ClassTier.NOBILE
    state.add_member(commander)
    faction.member_ids.append(1)

    war = War(id="escg7q1-treaty-war", name="Treaty War", war_type=WarType.FOREIGN, strength=5,
              naval_required=True, enemy_naval_current=5, enemy_land_current=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"indemnity": 100, "duration": 3, "status": "pending",
                          "generated_turn": 1})
    war.commander_id = 1
    state._war_system._truce_wars.append(war)

    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok
    assigned, _ = ms.assign_to_war([1, 2], war.id, 1)
    assert assigned == 2

    ns = state._naval_system
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._status = FleetStatus.AVAILABLE
    ns._fleets[1] = fleet
    assert ns.assign_fleet_to_war(1, war.id, "naval")

    return state, war, ms, ns


def test_treaty_point_no_disband_no_marker():
    """停战批准点：军团仅释放 AVAILABLE（不即时解散）；无 disbandment marker（FC-ESC-04）。"""
    state, war, ms, ns = _treaty_state()
    PoliticalSystem(state).execute_passed_peace_treaty(war)

    assert war.status == WarStatus.TRUCE, "approved treaty 仍是 TRUCE（G1-14 不变）"
    for num in (1, 2):
        assert ms.get_legion_by_number(num).status == LegionStatus.AVAILABLE, \
            "停战点军团 AVAILABLE，不即时解散（G1-14）"
    assert state.get_phase_result("population_disbandment") is None, \
        "停战/元老院阶段不产 disbandment marker（G1-14）"


def test_population_entry_processing_disbands_exactly_once():
    """Population 阶段处理（= 入口 M1 触发的 canonical）：恰一次解散（FC-ESC-04/FC-ESC-02）。"""
    state, war, ms, ns = _treaty_state()
    PoliticalSystem(state).execute_passed_peace_treaty(war)

    disband = population_api.process_population_disbandments(state)
    assert disband["legions"]["deescalated"]["total"] == 2, \
        "Population 入口解散（G1-14：解散发生在 Population 阶段）"
    for num in (1, 2):
        assert ms.get_legion_by_number(num).status == LegionStatus.DISBANDED
    assert state._war_system._legions_to_disband == [], "队列消费完毕（exactly-once）"

    # marker exactly-once：重复处理零二次 mutation
    again = population_api.process_population_disbandments(state)
    assert again == disband, "marker 幂等（FC-ESC-02）"
