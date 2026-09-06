# src/tests/test_api/test_wpgr3_s4_nominal_effective.py
"""WP-G-R3 S4（R3-G-04 + T-R3-11/12/13/14/15/20/21）— Fleet nominal/effective 分离。

冻结设计：SA-Design-WP-G-R3 v1.2 §4（全节）+ §10 T11~T15/T20/T21 + §4.5 DTO/GUI。

冻结契约（§4.1/§4.2，Owner 2026-09-05 19:41 选项 B 已落位）：
- Fleet 持久 nominal base（award 当次 type config 快照）+ quality q=D/A 精确整数比 +
  package_id=contract.id（完工后保留，与 complete_building 清 _contract_id 不同）；
  _strength_base 保留为 nominal 兼容镜像（n），不可供 replacement/GUI 假称 effective。
- 唯一冻结主线：逐 package raw（精确有理数 Fraction）→ upper-cap min(raw, 2×nominal_package)
  → round 一次（Python ties-to-even）→ 跨 package 求和；无 per-fleet round/clamp；
  lower floor=1 已取消（D28→2、D0→0 均无 floor 保底）；upper cap 保留为 package 级。
- replacement 全 nominal：required=enemy_naval_current；usable=same-war 完成 live nominal；
  committed_building=BUILDING nominal；committed_pending=PENDING/BUDGETED composition 快照；
  deficit<=0 → 0；needed=ceil(deficit/default nominal)；禁 get_combat_strength 作源。
- combat 消费 package aggregator（resolve_naval_battle roman_strength）；exp/martial 为
  每 Fleet modifiers；DTO/读模型（combat_api._war_card / gui_query_api._war_summary）同源
  分层字段（§4.5）；assigned_fleet_count/naval_ready 语义不变。

冻结 oracle：21→18（q6/7）；D28→2（q0.1，无 floor，≠旧 7）；D0→0（q0 不 fallback q=1）；
q1.2（D336）→25（overinvest 不触 cap）；q2.5（D700）→cap 42=2×21；混合舰型（q0.5）→
round 10（3×trireme n3 + 2×quinq n5，nominal19/raw9.5）。

Case A–G（§4.4）：A/C 每例改变 quality/experience/martial（大/小/换人/无）不改变 nominal
deficit；combat 随其变化。F/G：lower floor 取消 + upper cap 仍保留（不因无 floor 误删 cap）；
D=0 → q=0 非 q=1 fallback；effective0 非空舰队 combat 无除零（完整 CRT 优先级：disaster →
胜利阈值 → standoff，P2-G3R3-01 取证注意）。

生产链（真实 producer）：Y1 A280/B350 → Y2 bid C300+D240（或 Case 参数）→ award → 成熟 →
replacement/combat/DTO。混合舰型/触 cap oracle 以 Fleet 持久态 fixture（from_dict 形态）在
aggregator 层验证——生产 generator 单舰型、Senate ceiling ≤1.5A 使 q>1.5 不可达（数学证明
§4.2 已消除 clamp 自由参数；cap/混合仅公式层可达，任务书 §2 Case oracle 允许 task-local）。
"""
import unittest
from unittest import mock

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.entities.contract import ContractStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import (combat_api, forum_api, game_api, gui_query_api, mortality_api,
                     revenue_api, senate_api, session_api, population_api, resolution_api)

_ECON = {
    "fleet_types": {
        "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
        "quinquereme": {"build_cost": 56, "build_time": 2, "maintenance_cost": 6, "strength_base": 5},
    },
    "default_fleet_type": "trireme",
    "legion_maintenance_base": 8,
    "faction_stipend": 0,
    "senate_budget": {
        "public_works_min": 1, "public_works_max_ratio": 1.5,
        "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
    },
    "senate_war_legions": {"default": 4, "min": 1, "cap_mode": "available_pool"},
}

_CONFIG = {
    "testing": {"bypass_player_check": True},
    "political_rules": {
        "min_ages": {"consul": 30, "censor": 30, "praetor": 30, "quaestor": 30, "tribune": 30},
        "candidates_per_election": {"consul": 2},
        "office_cooldowns": {"consul": 0, "censor": 0, "praetor": 0, "quaestor": 0, "tribune": 0},
    },
    "economic_rules": dict(_ECON),
    "mortality_rules": {"event_deck": [], "event_draw_count": 0, "death_count": 0},
}

P1, P2 = "player_opt", "player_pop"
F_TARGET, F_RIVAL = "optimates", "populares"


class DeterministicApproveDecider:
    def decide_vote(self, issue, faction, state):
        return True


def _add_figure(state, figure_id, faction_id, *, popularity, charisma, age=40,
                praetor_history=True, tier=ClassTier.NOBILE, wealth=0, zeal=1, martial=1):
    fig = Figure(
        id=figure_id, name=f"FIG{figure_id}", faction_id=faction_id,
        class_tier=tier, age=age, popularity=popularity, charisma=charisma,
        zeal=zeal, martial=martial, wealth=wealth,
    )
    if praetor_history:
        fig.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
    state.add_member(fig)
    state.get_faction(faction_id).member_ids.append(figure_id)
    return fig


def _build_fleet_chain_state(enemy_naval=20):
    """S4 entry state（同 S3：valid-commander 版，消除 commanderless Senate 捷径）。"""
    cfg = {k: dict(v) for k, v in _CONFIG.items()}
    cfg["economic_rules"] = {k: dict(v) if isinstance(v, dict) else v for k, v in _CONFIG["economic_rules"].items()}
    state = GameState.create_for_testing(cfg)
    state.turn = GameTurn(turn_number=50, year=-240)
    state._treasury = 5000
    state.pyrrhic_war_won = True
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    for fid, fname in ((F_TARGET, "Optimates"), (F_RIVAL, "Populares")):
        state.add_faction(Faction(id=fid, name=fname, treasury=500))
    state._players[P1] = Player(P1, F_TARGET, PlayerType.HUMAN)
    state._players[P2] = Player(P2, F_RIVAL, PlayerType.HUMAN)
    state._turn_order = [P1, P2]
    state.set_current_player(P1)

    target = _add_figure(state, 10, F_TARGET, popularity=80, charisma=90)
    _add_figure(state, 11, F_TARGET, popularity=120, charisma=5)
    rival = _add_figure(state, 20, F_RIVAL, popularity=100, charisma=80)
    eques = _add_figure(state, 30, F_TARGET, popularity=0, charisma=0,
                        praetor_history=False, tier=ClassTier.EQUES, wealth=5000)
    _add_figure(state, 40, F_TARGET, popularity=0, charisma=0, martial=0)  # valid commander（martial 0 → Case-A 干净 18）

    war = War(
        id="naval_war", name="Naval War", strength=8, threat_level=3,
        naval_required=True, enemy_naval_current=enemy_naval, enemy_naval_max=enemy_naval,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = 40
    state._war_system._active_wars.append(war)

    state.mark_phase_executed("mortality")
    state.mark_phase_executed("revenue")
    return state, {"war": war, "target": target, "rival": rival, "eques": eques}


def _fleet_contract_for(state, war):
    return [
        c for c in state.get_all_contracts()
        if getattr(c, "_target_war_id", None) == war.id
        and getattr(c, "_is_fleet_construction", False)
    ]


def _vote_batch(state, player_id, consul_figure_id):
    entries = [
        {"office": office, "figure_id": consul_figure_id if office == "consul" else 0}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]
    ]
    res = population_api.batch_vote(state, player_id, entries, bypass_permission=True)
    assert res["success"], f"batch_vote {player_id} failed: {res.get('message')}"


def _population_round(state, consul_figure_id, rival_vote_figure_id=0):
    entry = population_api.begin_population_phase(state)
    assert isinstance(entry, dict) and "archived" in entry, f"begin failed: {entry}"
    assert population_api.get_candidates(state)["success"]
    _vote_batch(state, P1, consul_figure_id)
    _vote_batch(state, P2, rival_vote_figure_id)
    resolved = session_api.resolve_population_slice(state)
    assert resolved["success"], f"resolve_population_slice failed: {resolved.get('message')}"
    adv = session_api.advance_population_phase(state, P1)
    assert adv["success"], f"advance_population_phase failed: {adv.get('message')}"
    return resolved["data"]


def _senate_resolve_advance(state):
    resolved = senate_api.resolve_senate(state, vote_decider=DeterministicApproveDecider())
    assert resolved["success"], f"resolve_senate failed: {resolved.get('message')}"
    adv = senate_api.advance_senate_phase(state, P1)
    assert adv["success"], f"advance_senate_phase failed: {adv.get('message')}"
    return resolved


def _combat_naval_gate_year(state, war_id):
    act = combat_api.do_combat_action(state, P1, war_id, "attack")
    assert act["success"], f"do_combat_action failed: {act.get('message')}"
    adv = combat_api.advance_combat(state, P1)
    assert adv["success"], f"advance_combat failed: {adv.get('message')}"
    res = resolution_api.execute_resolution(state)
    assert res["success"], f"execute_resolution failed: {res.get('message')}"
    ay = game_api.advance_year(state, P1)
    assert ay["success"], f"advance_year failed: {ay.get('message')}"
    return ay


def _mortality_revenue_round(state):
    mor = mortality_api.execute_mortality_phase(state, P1)
    assert mor["success"], f"mortality execute failed: {mor.get('message')}"
    assert mortality_api.advance_mortality_phase(state, P1)["success"]
    rev = revenue_api.execute_revenue_phase(state, P1)
    assert rev["success"], f"revenue execute failed: {rev.get('message')}"
    assert revenue_api.advance_revenue_phase(state, P1)["success"]
    return rev


def _forum_init(state):
    res = forum_api.initialize_forum_turn(state)
    assert res["success"], f"initialize_forum_turn failed: {res.get('message')}"
    return res


def _forum_resolve_advance(state):
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], f"resolve_forum failed: {resolved.get('message')}"
    adv = forum_api.advance_forum_phase(state, P1)
    assert adv["success"], f"advance_forum_phase failed: {adv.get('message')}"
    return resolved


def _finish_year_from_population(state, war_id):
    if not state.is_phase_executed("forum"):
        adv_forum = forum_api.advance_forum_phase(state, P1)
        assert adv_forum["success"], f"advance_forum_phase failed: {adv_forum.get('message')}"
    _population_round(state, consul_figure_id=0)
    _senate_resolve_advance(state)
    _combat_naval_gate_year(state, war_id)


def year1_approved_contract(state, ctx, modified_budget=350):
    """Y1：PENDING 生成（冻结 A）→ Senate PASS（B=modified_budget）→ BUDGETED。"""
    war = ctx["war"]
    _forum_init(state)
    hits = _fleet_contract_for(state, war)
    assert len(hits) == 1, f"expected exactly 1 fleet contract, got {len(hits)}"
    contract = hits[0]
    assert contract.status == ContractStatus.PENDING
    assert contract._original_budget == contract.base_cost == contract.total_budget
    _forum_resolve_advance(state)
    data = _population_round(state, consul_figure_id=ctx["target"].id,
                             rival_vote_figure_id=ctx["rival"].id)
    winner = next(er for er in data.get("election_results", []) if er["office"] == "consul")
    assert winner["figure_id"] == ctx["target"].id
    assert PoliticalSystem(state)._is_eligible_consul(ctx["target"]) is True
    prop = senate_api.propose(state, P1, "budget", contract_id=contract.id,
                              modified_budget=modified_budget)
    assert prop["success"], f"propose budget failed: {prop.get('message')}"
    proposal_id = prop["data"]["proposal_id"]
    assert senate_api.vote(state, P1, [proposal_id], [True])["success"]
    resolved = senate_api.resolve_senate(state, vote_decider=DeterministicApproveDecider())
    assert resolved["success"], resolved.get("message")
    assert contract.status == ContractStatus.BUDGETED
    assert contract.approved_budget == modified_budget
    assert contract._original_budget == contract._total_budget
    _senate_resolve_advance(state)
    _combat_naval_gate_year(state, war.id)
    return contract


def _award_building(state, ctx, contract, amount, construction_cost):
    """Y2：M/R → Forum init → place_bid(C, D) → resolve award → BUILDING fleets。"""
    _mortality_revenue_round(state)
    _forum_init(state)
    bid = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                              amount=amount, construction_cost=construction_cost)
    assert bid["success"], f"place_bid failed: {bid.get('message')}"
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], resolved.get("message")
    assert contract.status == ContractStatus.ACTIVE
    return resolved


def _mature_assign(state, war):
    """Y2 余段完成 + Y3 M/R + Forum init → 成熟 + auto-assign → ON_MISSION。

    返回 (fleets, contract)。"""
    _finish_year_from_population(state, war.id)
    _mortality_revenue_round(state)
    g1 = _forum_init(state)
    fleets = [f for f in state.naval_system.get_all_fleets() if f._target_war_id == war.id]
    assert len(g1["data"].get("completed_fleets", [])) == len(fleets), g1["data"]
    return fleets


def _canonical_mature(state=None, ctx=None, amount=300, construction_cost=240,
                      enemy_naval=20, modified_budget=350):
    """全 producer 链至 7 艘成熟 ON_MISSION（A280/B350/C/D）。"""
    if state is None:
        state, ctx = _build_fleet_chain_state(enemy_naval=enemy_naval)
    war = ctx["war"]
    contract = year1_approved_contract(state, ctx, modified_budget=modified_budget)
    _award_building(state, ctx, contract, amount=amount, construction_cost=construction_cost)
    building = [f for f in state.naval_system.get_all_fleets() if f.is_building]
    assert len(building) == 7, f"7 BUILDING expected, got {len(building)}"
    fleets = _mature_assign(state, war)
    assert all(f.status == FleetStatus.ON_MISSION for f in fleets), [f.status for f in fleets]
    return state, ctx, contract, fleets


# ---------------------------------------------------------------------------
# aggregator/状态级 fixture 工厂（oracle 表 & 混合 package——生产 generator 单舰型、
# Senate ceiling ≤1.5A 使 q>1.5 不可达；公式层可达性见文件 docstring）
# ---------------------------------------------------------------------------

def _install_exact_package_fleets(state, package_id, counts, q_num, q_den,
                                  *, experience=0, status=FleetStatus.ON_MISSION):
    """在 naval_system 直接装载 exact-package Fleet（from_dict 形态等价——持久字段直构，
    task-local oracle fixture）。counts: {fleet_type: n}。返回 fleet 列表。"""
    if getattr(state, "naval_system", None) is None:
        state._naval_system = NavalSystem(state)
    ns = state.naval_system
    fleet_configs = state.config.get("economic_rules.fleet_types", {})
    fleets = []
    for ftype, count in counts.items():
        nominal = fleet_configs[ftype].get("strength_base", 3)
        for i in range(count):
            fleet = Fleet(number=ns._next_fleet_number, fleet_type=ftype,
                          name=f"oracle-{ftype}-{i}")
            fleet._status = status
            fleet._strength_base = nominal            # nominal 兼容镜像（n）
            fleet._nominal_strength_base = nominal
            fleet._construction_quality_numerator = q_num
            fleet._construction_quality_denominator = q_den
            fleet._construction_package_id = package_id
            fleet._target_war_id = "oracle_war"
            if experience:
                fleet._experience = experience
            ns._fleets[fleet.number] = fleet
            ns._next_fleet_number += 1
            fleets.append(fleet)
    return fleets


class TestS4NominalEffective(unittest.TestCase):
    # ---------------- T-R3-11：Case A main oracle ----------------
    def test_t11_nominal21_base18_no_topup_combat_consumes_aggregate(self):
        """T11：nominal21/effective_base18/enemy20 无 topup；combat 消费 package 聚合 18
        （非旧 per-fleet Σ21）——判别：enemy=19 时 dice12 → total_new=11 VICTORY（旧 Σ21 会给
        TRIUMPH）。零 exp/零 martial modifiers 分列。"""
        state, ctx, contract, fleets = _canonical_mature()  # A280 D240 q=6/7
        war = ctx["war"]
        ns = state.naval_system

        # replacement：nominal 覆盖 → 0 新合同（Case A：deficit -1）
        contracts = ns.generate_replacement_contracts(state.turn.turn_number)
        self.assertEqual(contracts, [])
        # nominal 聚合（replacement 源是 nominal 而非 effective）
        fleet_configs = state.config.get("economic_rules.fleet_types", {})
        self.assertEqual(contract._original_budget, 280)
        # 四要素算术（§4.3）：deficit = 20 - usable(21) - building(0) - pending(0) = -1
        self.assertEqual(war.enemy_naval_current, 20)

        # breakdown 分层：quality_adjusted_base=18（package raw 18 → cap min(18,42) → round 18）
        bd = ns.get_fleet_strength_breakdown(fleets)
        self.assertEqual(bd["nominal_total"], 21)
        self.assertEqual(bd["quality_adjusted_base"], 18)
        self.assertEqual(bd["experience_bonus"], 0)
        self.assertEqual(bd["commander_bonus"], 0)     # fixture commander martial=0 → 干净 base
        self.assertEqual(bd["effective_combat_strength"], 18)

        # 单舰名义镜像与 q 持久字段（§4.1）
        f0 = fleets[0]
        self.assertEqual(f0._strength_base, 3)                      # nominal 兼容镜像
        self.assertEqual(f0._nominal_strength_base, 3)             # type config 快照
        self.assertEqual(f0._construction_quality_numerator, 240)  # D
        self.assertEqual(f0._construction_quality_denominator, 280)  # A（禁 D/B、D/C）
        self.assertEqual(f0._construction_package_id, contract.id)
        # complete_building 清 _contract_id 但 package 身份保留
        self.assertIsNone(f0.contract_id)
        self.assertEqual(f0._construction_package_id, contract.id)

        # combat 判别：enemy 19 → dice 12 → total = 12 + 18 - 19 = 11 → VICTORY
        war._enemy_naval_current = 19
        with mock.patch("src.core.systems.naval_system.random.randint", return_value=12):
            result, losses = ns.resolve_naval_battle(war)
        self.assertEqual(result, "VICTORY")   # 18 消费（旧 Σ21 → total14 → TRIUMPH，判别失败）
        self.assertEqual(losses["roman_losses"], 0)
        self.assertTrue(war.sea_control_acquired)

    def test_t11_modifiers_split_experience_and_commander(self):
        """T11 modifiers：experience & Commander martial 每 Fleet 加一次（不并入 quality）。"""
        state, ctx, contract, fleets = _canonical_mature()
        ns = state.naval_system
        fleets[0]._experience = 1
        fleets[1]._experience = 2
        # war commander（id=40）martial 3 → 每 Fleet 加一次：7×3=21
        state.get_member(40).martial = 3
        bd = ns.get_fleet_strength_breakdown(fleets)
        self.assertEqual(bd["nominal_total"], 21)
        self.assertEqual(bd["quality_adjusted_base"], 18)   # quality 不含 exp/martial
        self.assertEqual(bd["experience_bonus"], 3)
        self.assertEqual(bd["commander_bonus"], 21)
        self.assertEqual(bd["effective_combat_strength"], 42)

    # ---------------- T-R3-12/13/14/15：replacement nominal ----------------
    def test_t12_hull_loss_defines_true_deficit(self):
        """T12：真实 hull casualty 毁 2 艘 → usable nominal 15 → deficit 5 → 补 2 艘 A80。"""
        state, ctx, contract, fleets = _canonical_mature()
        war = ctx["war"]
        ns = state.naval_system
        # 显式两舰 casualty fixture（同 mark_destroyed+remove_fleet producer parity；
        # 实际 DEFEAT ceil(N/2) smoke 另见 T21）
        for fleet in fleets[:2]:
            fleet.mark_destroyed(state.turn.turn_number)
            war.remove_fleet(fleet.number)
        contracts = ns.generate_replacement_contracts(state.turn.turn_number)
        self.assertEqual(len(contracts), 1)
        comp = contracts[0].recommended_fleet_composition
        self.assertEqual(comp, [{"type": "trireme", "count": 2}])
        self.assertEqual(contracts[0]._original_budget, 80)   # 2×40 A
        self.assertEqual(contracts[0].status, ContractStatus.PENDING)
        # deficit 5 = 20 - 15（真实 loss 而非 quality）
        self.assertEqual(war.enemy_naval_current - 15, 5)

    def test_t13_building_and_ACTIVE_no_double_count(self):
        """T13：BUILDING 21 阻重复；ACTIVE 合同不再叠加 composition（partial maturity 去重）。"""
        # 场景 1：award 后 7 BUILDING（未成熟）→ replacement 0
        state, ctx = _build_fleet_chain_state()
        war = ctx["war"]
        contract = year1_approved_contract(state, ctx)
        _award_building(state, ctx, contract, amount=300, construction_cost=240)
        self.assertEqual(len([f for f in state.naval_system.get_all_fleets() if f.is_building]), 7)
        self.assertEqual(state.naval_system.generate_replacement_contracts(state.turn.turn_number), [])

        # 场景 2：partial maturity——3 艘成熟（usable nominal 9）+ 4 艘仍 BUILDING（12）→ 21 仍覆盖
        fleets = [f for f in state.naval_system.get_all_fleets() if f.is_building]
        for fleet in fleets[:3]:
            fleet._build_end_turn = state.turn.turn_number
        state.naval_system.process_fleet_construction(state.turn.turn_number)
        self.assertEqual(len([f for f in fleets if f.status != FleetStatus.BUILDING]), 3)
        self.assertEqual(state.naval_system.generate_replacement_contracts(state.turn.turn_number), [])
        # 物化容量归 BUILDING 侧（同一 Fleet 不同时在 usable/building 集——partial 去重）
        self.assertEqual(len([f for f in state.naval_system.get_all_fleets()
                              if f._target_war_id == war.id and f.status == FleetStatus.BUILDING]), 4)

    def test_t14_pending_budgeted_blocked_and_cross_war_excluded(self):
        """T14：PENDING/BUDGETED nominal 21 各阻重复；跨 war 容量不互抵。"""
        # PENDING：Y1 Forum init 后（Senate PASS 前）→ committed_pending 21 → 0 合同
        state, ctx = _build_fleet_chain_state()
        war = ctx["war"]
        _forum_init(state)
        contract_p = _fleet_contract_for(state, war)[0]
        self.assertEqual(contract_p.status, ContractStatus.PENDING)
        self.assertEqual(
            state.naval_system.generate_replacement_contracts(state.turn.turn_number), [])

        # BUDGETED：已 approve 未 award → committed_pending 21 → 0 合同
        state, ctx = _build_fleet_chain_state()
        contract = year1_approved_contract(state, ctx)
        self.assertEqual(contract.status, ContractStatus.BUDGETED)
        _mortality_revenue_round(state)
        _forum_init(state)
        self.assertEqual(
            state.naval_system.generate_replacement_contracts(state.turn.turn_number), [],
            "BUDGETED 21 覆盖 target 20 → 0 合同")

        # 跨 war：war B（不同 target）无 committed → deficit 存在 → 给 B 生成；A 容量不计入 B
        state, ctx = _build_fleet_chain_state()
        war_a = ctx["war"]
        contract_a = year1_approved_contract(state, ctx)
        _award_building(state, ctx, contract_a, amount=300, construction_cost=240)  # A: 7 BUILDING
        war_b = War(id="naval_war_b", name="Naval War B", strength=8, threat_level=3,
                    naval_required=True, enemy_naval_current=20, enemy_naval_max=20,
                    disaster_numbers=[2, 3, 4], standoff_numbers=[99])
        war_b.status = WarStatus.ACTIVE
        war_b.commander_id = 40
        state._war_system._active_wars.append(war_b)
        contracts = state.naval_system.generate_replacement_contracts(state.turn.turn_number)
        # A 无补充；B 有 deficit 20 → 补 7 艘 A280
        hits = [c for c in contracts if getattr(c, "_target_war_id", None) == war_b.id]
        self.assertEqual(len(hits), 1, contracts)
        self.assertEqual(hits[0]._original_budget, 280)

    def test_t15_enemy_raise_defines_deficit_quality_irrelevant(self):
        """T15：enemy24 − existing21 → deficit 3 → 补 1 艘 A40；experience/martial/q 不改 hull 数。"""
        state, ctx, contract, fleets = _canonical_mature()
        war = ctx["war"]
        war._enemy_naval_current = 24  # test-local enemy requirement 外生 fixture（设计 §4.4 Case E）
        war._enemy_naval_max = 24
        ns = state.naval_system
        # 改变 quality/exp/martial（大/小/无）不改变 nominal deficit
        fleets[0]._experience = 5
        contracts = ns.generate_replacement_contracts(state.turn.turn_number)
        self.assertEqual(len(contracts), 1)
        comp = contracts[0].recommended_fleet_composition
        self.assertEqual(comp, [{"type": "trireme", "count": 1}])
        self.assertEqual(contracts[0]._original_budget, 40)
        # deficit 3 = 24 - 21
        self.assertEqual(war.enemy_naval_current - 21, 3)

    # ---------------- T-R3-20/21：Case F/G（Owner 选项 B）----------------
    def test_t20_d28_q01_effective2_no_floor(self):
        """T20：7 hull A280/D28（q=0.1）→ raw 2.1 → round 2；无 floor 保底（≠旧 7）；
        combat=2+modifiers；upper cap 保留（q<2 不触 cap，非因无 floor 删 cap）。"""
        state, ctx, contract, fleets = _canonical_mature(amount=100, construction_cost=28)
        ns = state.naval_system
        self.assertEqual(contract._actual_cost, 28)
        bd = ns.get_fleet_strength_breakdown(fleets)
        self.assertEqual(bd["nominal_total"], 21)
        # q=0.1：raw=2.1 → min(2.1,42) → round 2（martial 0 → effective = 2）
        self.assertEqual(bd["quality_adjusted_base"], 2)
        self.assertEqual(bd["commander_bonus"], 0)
        self.assertEqual(bd["effective_combat_strength"], 2)
        # 无 floor：effective 可低于舰数 7（旧每舰 floor=1 会给 package 7）——不等号成立即证明
        self.assertLess(bd["quality_adjusted_base"], len(fleets))
        # replacement nominal 不受 quality 影响：usable 21 → deficit -1 → 0 合同
        self.assertEqual(ns.generate_replacement_contracts(state.turn.turn_number), [])

    def test_t20_oracle_upper_cap_still_present(self):
        """§4.2 oracle：q=2.5（D700/A280）触 cap → 42 = 2×21（package 级 min(raw,2n)）——
        证明 upper cap 保留（不因 lower floor 取消而删 cap）。"""
        state = GameState.create_for_testing({k: dict(v) for k, v in _CONFIG.items()})
        fleets = _install_exact_package_fleets(state, 901, {"trireme": 7}, 700, 280)
        ns = state.naval_system
        bd = ns.get_fleet_strength_breakdown(fleets)
        self.assertEqual(bd["nominal_total"], 21)
        self.assertEqual(bd["quality_adjusted_base"], 42)  # min(52.5, 42) → round 42 = 2×21
        pkgs = bd["fleet_strength_packages"]
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0]["package_id"], 901)
        self.assertEqual(pkgs[0]["nominal"], 21)
        self.assertEqual(pkgs[0]["rounded"], 42)

    def test_t20_oracle_q_over_1_and_mixed_types(self):
        """§4.2 oracle：q=1.2（D336/A280）→ 25（overinvest 不触 cap）；混合舰型 q=0.5 →
        nominal19/raw9.5/round10（per-package 一次舍入，无 per-fleet round）。"""
        state = GameState.create_for_testing({k: dict(v) for k, v in _CONFIG.items()})
        # q=1.2：raw=25.2 → min(25.2,42) → round 25
        fleets_a = _install_exact_package_fleets(state, 902, {"trireme": 7}, 336, 280)
        ns = state.naval_system
        bd = ns.get_fleet_strength_breakdown(fleets_a)
        self.assertEqual(bd["quality_adjusted_base"], 25)
        # 混合舰型（task-local 单舰 nominal：trireme 3 / quinquereme 5 → 合同 q=0.5：D=140/A=280）
        fleets_b = _install_exact_package_fleets(
            state, 903, {"trireme": 3, "quinquereme": 2}, 140, 280)
        bd2 = ns.get_fleet_strength_breakdown(fleets_b)
        self.assertEqual(bd2["nominal_total"], 19)         # 3×3 + 2×5
        self.assertEqual(bd2["quality_adjusted_base"], 10)  # raw 9.5 → round 10（无 per-fleet）
        pkgs = bd2["fleet_strength_packages"]
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0]["rounded"], 10)

    def test_t21_d0_q0_no_fallback_and_rejections(self):
        """T21：D=0 → q=0（非 q=1 fallback）→ effective 0；D<0/D 缺失由既有校验拒绝；
        effective0 非空舰队 combat 无除零（完整 CRT 优先级：disaster→胜利阈值→standoff）。"""
        # D<0 先于 award 由 admission 拒绝（BUDGETED 态）
        state0, ctx0 = _build_fleet_chain_state()
        contract0 = year1_approved_contract(state0, ctx0)
        _mortality_revenue_round(state0)
        _forum_init(state0)
        r = forum_api.place_bid(state0, P1, ctx0["eques"].id, contract0.id,
                                amount=100, construction_cost=-5)
        self.assertFalse(r["success"])
        self.assertEqual(contract0.status, ContractStatus.BUDGETED)

        # D=0 经真实 award（admission 合法：D 非负且 ≤C）→ q=0
        state, ctx, contract, fleets = _canonical_mature(amount=100, construction_cost=0)
        ns = state.naval_system
        self.assertEqual(contract._actual_cost, 0)
        bd = ns.get_fleet_strength_breakdown(fleets)
        self.assertEqual(bd["nominal_total"], 21)
        self.assertEqual(bd["quality_adjusted_base"], 0)  # D=0 → q=0 → raw 0（非 q=1 fallback）

        # effective0 非空舰队 combat：无除零/空断言；CRT 完整优先级（martial 0）——
        # dice12 ∉ disaster[2,3,4]；standoff[99] 不中；total = 12+0−20 = −8 < −3 → DEFEAT
        # （losses=ceil(7/2)=4 基于舰数非强度——无除零；P2-G3R3-01 完整 CRT 优先级取证）
        war = ctx["war"]
        with mock.patch("src.core.systems.naval_system.random.randint", return_value=12), \
             mock.patch("src.core.systems.naval_system.random.sample",
                        side_effect=lambda pop, k: pop[:k]):
            result, losses = ns.resolve_naval_battle(war)
        self.assertEqual(result, "DEFEAT")
        self.assertEqual(losses["roman_losses"], 4)
        survivors = [f for f in ns.get_all_fleets() if f.status == FleetStatus.ON_MISSION]
        self.assertEqual(len(survivors), 3)

    # ---------------- DTO / GUI 读模型（§4.5）----------------
    def test_dto_war_card_strength_fields_and_gui_query(self):
        """§4.5：combat_api._war_card / gui_query_api._war_summary 同源分层字段；count/
        readiness 语义不变；CombatStage.qml 独立 naval 显示绑定。"""
        state, ctx, contract, fleets = _canonical_mature()
        war = ctx["war"]
        state.get_member(40).martial = 3  # per-fleet martial modifier（DTO 分层展示）
        view = combat_api.get_combat_view(state, P1)
        self.assertTrue(view["success"])
        card = next(w for w in view["data"]["active_wars"] if w["war_id"] == war.id)
        self.assertEqual(card["assigned_fleet_count"], 7)      # 语义不变
        self.assertIs(card["naval_ready"], True)
        self.assertEqual(len(card["assigned_fleet_ids"]), 7)
        self.assertEqual(card["fleet_nominal_strength"], 21)
        self.assertEqual(card["fleet_quality_adjusted_base"], 18)
        self.assertEqual(card["fleet_experience_bonus"], 0)
        self.assertEqual(card["fleet_commander_bonus"], 21)    # 7 × martial 3
        self.assertEqual(card["fleet_effective_combat_strength"], 39)
        pkgs = card["fleet_strength_packages"]
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0]["package_id"], contract.id)
        self.assertEqual(pkgs[0]["rounded"], 18)

        q = gui_query_api.get_global_query_result(state, P1, "war_list")
        self.assertTrue(q["success"])
        entries = q["data"]["summary"]["wars"]
        qentry = next(e for e in entries if e["id"] == war.id)
        self.assertEqual(qentry["fleet_nominal_strength"], 21)
        self.assertEqual(qentry["fleet_quality_adjusted_base"], 18)
        self.assertEqual(qentry["fleet_effective_combat_strength"], 39)

        import os
        qml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "src", "ui", "gui", "qml", "stages", "CombatStage.qml",
        )
        with open(qml_path, "r", encoding="utf-8") as _f:
            _qml_src = _f.read()
        self.assertIn("fleet_nominal_strength", _qml_src)
        self.assertIn("fleet_effective_combat_strength", _qml_src)


class TestS4FleetSerializer(unittest.TestCase):
    def test_serializer_new_fleet_roundtrip_exact(self):
        """SC09 fleet 侧：新字段（nominal/q num-den/package_id）round-trip 完全相等。"""
        fleet = Fleet(number=1, fleet_type="trireme", name="F1")
        fleet._status = FleetStatus.ON_MISSION
        fleet._strength_base = 3
        fleet._nominal_strength_base = 3
        fleet._construction_quality_numerator = 240
        fleet._construction_quality_denominator = 280
        fleet._construction_package_id = 77
        fleet._target_war_id = "naval_war"
        d = fleet.to_dict()
        rt = Fleet.from_dict(d)
        self.assertEqual(rt._nominal_strength_base, 3)
        self.assertEqual(rt._construction_quality_numerator, 240)
        self.assertEqual(rt._construction_quality_denominator, 280)
        self.assertEqual(rt._construction_package_id, 77)
        self.assertEqual(rt._strength_base, 3)
        self.assertEqual(rt._target_war_id, "naval_war")

    def test_serializer_legacy_fleet_honest_baked(self):
        """legacy-shaped fleet dict（无新字段，_strength_base=2 已烘焙 effective）→
        nominal 由同版 type config 派生；旧 effective 值保留为 legacy snapshot；诚实标注
        legacy_baked（不声称还原精确 q）。"""
        legacy = {
            "_number": 5, "_name": "Legacy F", "_fleet_type": "trireme",
            "_status": "available", "_commander_id": None, "_experience": 0,
            "_strength_base": 2, "_is_veteran": False, "_assigned_war_id": None,
            "_assigned_mission_type": None, "_location_zone_id": None, "_destroyed_turn": 0,
            "_build_start_turn": None, "_build_end_turn": None, "_contract_id": 77,
            "_target_war_id": "naval_war",
        }
        fleet_configs = {"trireme": {"strength_base": 3}}
        fleet = Fleet.from_dict(legacy, fleet_configs=fleet_configs)
        # nominal = 同版 config 快照（§4.1：缺新字段时旧 _strength_base 是已舍入 effective）
        self.assertEqual(fleet._nominal_strength_base, 3)
        self.assertEqual(fleet._construction_quality_numerator, None)
        self.assertEqual(fleet._construction_quality_denominator, None)
        self.assertEqual(fleet._construction_package_id, None)
        self.assertEqual(fleet._quality_source, "legacy_baked")
        # 旧 effective 值保留为 legacy snapshot（_strength_base 不被改写为 nominal）
        self.assertEqual(fleet._strength_base, 2)
        # roundtrip 保持标注
        rt = Fleet.from_dict(fleet.to_dict(), fleet_configs=fleet_configs)
        self.assertEqual(rt._quality_source, "legacy_baked")
        self.assertEqual(rt._strength_base, 2)

    def test_serializer_legacy_unknown_type_no_guess(self):
        """未知舰型 legacy：不猜 nominal（None）；_strength_base 保留 baked 值；兼容标注。"""
        legacy = {
            "_number": 6, "_name": "Unknown F", "_fleet_type": "liburna",
            "_status": "available", "_commander_id": None, "_experience": 0,
            "_strength_base": 4, "_is_veteran": False, "_assigned_war_id": None,
            "_assigned_mission_type": None, "_location_zone_id": None, "_destroyed_turn": 0,
            "_build_start_turn": None, "_build_end_turn": None, "_contract_id": None,
            "_target_war_id": None,
        }
        fleet = Fleet.from_dict(legacy, fleet_configs={"trireme": {"strength_base": 3}})
        self.assertIsNone(fleet._nominal_strength_base)
        self.assertEqual(fleet._strength_base, 4)
        self.assertEqual(fleet._quality_source, "legacy_baked")


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
