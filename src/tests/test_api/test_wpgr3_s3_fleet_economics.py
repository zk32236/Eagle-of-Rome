# src/tests/test_api/test_wpgr3_s3_fleet_economics.py
"""WP-G-R3 S3（R3-G-03 + T-R3-07/08/09/10）— Fleet contract A/B/C/D 四权威 + 双输入 + AI 双 draw。

冻结设计：SA-Design-WP-G-R3 v1.2 §3（全节）+ §10 T07~T10 + §4.3（PENDING nominal 快照，
serializer 侧 SC09）+ §6（受影响回归）。

冻结契约（§3.1）：
- A Baseline = `_original_budget`（generator 冻结；Senate 重复修改不得覆盖为上次 B）
- B Approved = 新 `_approved_budget`（Senate budget PASS 写入，即使金额未修改也写；legacy
  BUDGETED fallback = base_cost）
- C Winning price = `_contract_price`（Forum award 时固化；award 后 base_cost=C 保持旧
  public-works payment 消费兼容——C 独立于 B 持久，B 不丢）
- D Actual cost = `_actual_cost`（Optional[int]，正式字段化；award 固化入队时持久 D，award
  不重算；None≠0）

admission/award 双表分离（§3.3/§3.6）：place_bid 入队守卫（current player / BUDGETED / C 非
bool 正整数且 C≤B / alive owned Eques / D 非 bool 非负整数且 D≤C / 新请求 (contract,figure)
防重 / 显式 D 与显式 rate 冲突拒）与 resolve_forum award 复检（按 pending faction_id 分组、
**不重放 current-player guard**、live owner/Eques 复检、合同 BUDGETED、8-tuple D 只固化一次、
package 已物化 no-op、自身 pending 非 duplicate、失效候选先过滤→最低价→平手、全失效
fail-closed 无 winner 无付款）。

多期金额守恒（§3.6）：Fleet 在 award 以最终 build_time 为唯一 N 同步
_construction_years/duration/remaining_years 与 annual C//N、D//N；末期成本
D-(N-1)*annual_cost（remaining_years==1）；payment 走既有 C-total_spent 末期算法；
总付款 C、总成本 D、gross=C-D 守恒（税率/工期 authority 不变）。

AI（§3.4）：decide_fleet_bid 读 Senate B（approved_budget）、两独立 draw（bid_discount 定 C、
profit_rate 第二次独立 uniform）、返回既有三元 (knight, C, profit_rate)；边际范围/截断/
Eques 选择保持（R3-11 零重平衡）。

R1 s3 superseding authority（§6/§4.2 ledger）：旧「竞标折价⇒true deficit」由 R3 supersede
（quality 降不授权补 hull）；本文件 fixture 全部 valid-commander（消除 commanderless Senate
捷径，R3-G01 合法红灯）；replacement nominal 断言见 S4（test_wpgr3_s4_nominal_effective.py）。

生产链（真实 producer）：Y1 Forum init（PENDING A280）→ Forum resolve/advance → Population
（目标派系 200 > rival 100）→ Senate propose(budget B350)/vote/resolve → BUDGETED → Combat
（真实 naval 门：无舰队 auto-DEFEAT 阻断陆战）→ resolution → advance_year → Y2 … bid →
award → … Revenue 付款。禁手工 BUDGETED/成熟/auto-assign 冒充。
"""
import json
import unittest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.fleet import FleetStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.core.systems.political_system import PoliticalSystem
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.api import (combat_api, forum_api, game_api, gui_query_api, mortality_api,
                     revenue_api, senate_api, session_api, population_api, resolution_api)

# ---------------------------------------------------------------------------
# 确定性 fixture：Population 权重 200>100 + Senate deterministic approve
# ---------------------------------------------------------------------------

_ECON = {
    "fleet_types": {
        "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
        "quinquereme": {"build_cost": 56, "build_time": 2, "maintenance_cost": 6, "strength_base": 4},
    },
    "default_fleet_type": "trireme",
    "legion_maintenance_base": 8,
    "faction_stipend": 0,
    # ODR-ED：budget range（propose modified_budget 校验消费）
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
    """task-local Senate 补票器（真实 resolve_senate 结算路径，零随机）。"""

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


def _build_fleet_chain_state(enemy_naval=20, default_type="trireme"):
    """S3 entry state（valid-commander 版 —— R1 s3 commanderless 捷径已消除，R3-G01 合法）。

    ACTIVE naval_required war 已有**有效前线 Commander**（id=40，非 Consul、与拟当选预算
    Consul 分开——设计 §8.2 Chain FC 第 1 步）+ 目标派系（living influence 200）/rival（100）
    + 双派系 eques bidder + 可当选 Consul（praetor 履历）。mortality/revenue 已 executed →
    Y1 自 Forum 阶段开始。
    """
    cfg = {k: dict(v) for k, v in _CONFIG.items()}
    cfg["economic_rules"] = {k: dict(v) if isinstance(v, dict) else v for k, v in _CONFIG["economic_rules"].items()}
    cfg["economic_rules"]["default_fleet_type"] = default_type
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

    # 目标派系 living influence 合计 200（target 80 + filler 120）
    target = _add_figure(state, 10, F_TARGET, popularity=80, charisma=90)
    _add_figure(state, 11, F_TARGET, popularity=120, charisma=5)
    # rival 派系 living influence 合计 100
    rival = _add_figure(state, 20, F_RIVAL, popularity=100, charisma=80)
    # eques bidder ×2（influence 0 → 不影响选举权重 fixture）
    eques = _add_figure(state, 30, F_TARGET, popularity=0, charisma=0,
                        praetor_history=False, tier=ClassTier.EQUES, wealth=5000)
    eques2 = _add_figure(state, 31, F_TARGET, popularity=0, charisma=0,
                         praetor_history=False, tier=ClassTier.EQUES, wealth=5000)
    rival_eques = _add_figure(state, 32, F_RIVAL, popularity=0, charisma=0,
                              praetor_history=False, tier=ClassTier.EQUES, wealth=5000)
    # 有效前线 Commander（id=40，NOBILE optimates；非 Consul 候选——独立于 senate 提案人）
    commander = _add_figure(state, 40, F_TARGET, popularity=10, charisma=10,
                            praetor_history=True, martial=4)

    war = War(
        id="naval_war", name="Naval War", strength=8, threat_level=3,
        naval_required=True, enemy_naval_current=enemy_naval, enemy_naval_max=enemy_naval,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = commander.id  # valid commander（非 commanderless；R3-G01 required=False）
    state._war_system._active_wars.append(war)

    # Y1 自 Forum 阶段开始（mortality/revenue 已执行）
    state.mark_phase_executed("mortality")
    state.mark_phase_executed("revenue")
    return state, {"war": war, "target": target, "rival": rival, "eques": eques,
                   "eques2": eques2, "rival_eques": rival_eques, "commander": commander}


# ---------------------------------------------------------------------------
# 年度 / phase 生产链 helper（全部真实 API）
# ---------------------------------------------------------------------------

def _fleet_contract_for(state, war):
    return [
        c for c in state.get_all_contracts()
        if getattr(c, "_target_war_id", None) == war.id
        and getattr(c, "_is_fleet_construction", False)
    ]


def _vote_batch(state, player_id, consul_figure_id, bypass=True):
    """真实 batch_vote：恰 5 条 office entry（consul=指定候选人；其余 ABSTAIN）。"""
    entries = [
        {"office": office, "figure_id": consul_figure_id if office == "consul" else 0}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]
    ]
    res = population_api.batch_vote(state, player_id, entries, bypass_permission=bypass)
    assert res["success"], f"batch_vote {player_id} failed: {res.get('message')} {res.get('errors')}"


def _population_round(state, consul_figure_id, rival_vote_figure_id=0):
    """begin → get_candidates → human batch votes → resolve → advance。"""
    entry = population_api.begin_population_phase(state)
    assert isinstance(entry, dict) and "archived" in entry, f"begin failed: {entry}"
    cand = population_api.get_candidates(state)
    assert cand["success"], cand.get("message")
    _vote_batch(state, P1, consul_figure_id)
    _vote_batch(state, P2, rival_vote_figure_id)
    resolved = session_api.resolve_population_slice(state)
    assert resolved["success"], f"resolve_population_slice failed: {resolved.get('message')} {resolved.get('errors')}"
    adv = session_api.advance_population_phase(state, P1)
    assert adv["success"], f"advance_population_phase failed: {adv.get('message')}"
    return resolved["data"]


def _senate_resolve_advance(state):
    """resolve_senate（确定性 approve）→ advance_senate_phase。
    WP-G-R4（OD-R4-05/06 supersede，SA v1.7 §2.3b）：零提案先显式空选择写 P。"""
    if not state.get_senate_proposals() and not state.senate_proposal_decision_complete:
        fin = senate_api.propose_many(state, P1, [])
        assert fin["success"], fin.get("message")
    resolved = senate_api.resolve_senate(state, vote_decider=DeterministicApproveDecider())
    assert resolved["success"], f"resolve_senate failed: {resolved.get('message')}"
    adv = senate_api.advance_senate_phase(state, P1)
    assert adv["success"], f"advance_senate_phase failed: {adv.get('message')}"
    return resolved


def _combat_naval_gate_year(state, war_id):
    """Combat：真实 do_combat_action attack → canonical naval 门（无成舰/未获控 → auto-DEFEAT
    阻断陆战，war 保持 ACTIVE）→ advance → resolution → advance_year。

    设计 §8.2 Chain FC step 5/7：不得以 commanderless nonactionable 跳过（本 fixture war 有
    valid commander → actionable → 必须真实处理 naval gate）。
    WP-G-R4 supersede（SA v1.7 §8.3）：无 ready 成舰 → NAVAL_NOT_READY（非 R3 自动 DEFEAT）
    ——零副作用 + 显式 advance（年 1 无舰队战斗 = 合法跳过）。
    """
    act = combat_api.do_combat_action(state, P1, war_id, "attack")
    if not act["success"]:
        assert act["data"]["code"] in ("NAVAL_NOT_READY", "NAVAL_SYSTEM_UNAVAILABLE"), act
        w = state.get_war_system().get_war_by_id(war_id)
        assert w.status == WarStatus.ACTIVE
    adv = combat_api.advance_combat(state, P1)
    assert adv["success"], f"advance_combat failed: {adv.get('message')}"
    res = resolution_api.execute_resolution(state)
    assert res["success"], f"execute_resolution failed: {res.get('message')} {res.get('errors')}"
    ay = game_api.advance_year(state, P1)
    assert ay["success"], f"advance_year failed: {ay.get('message')}"
    return ay


def _mortality_revenue_round(state):
    """年度 M/R：mortality execute/advance → revenue execute/advance。"""
    mor = mortality_api.execute_mortality_phase(state, P1)
    assert mor["success"], f"mortality execute failed: {mor.get('message')}"
    assert mortality_api.advance_mortality_phase(state, P1)["success"]
    rev = revenue_api.execute_revenue_phase(state, P1)
    assert rev["success"], f"revenue execute failed: {rev.get('message')}"
    assert revenue_api.advance_revenue_phase(state, P1)["success"]
    return rev


def _forum_init(state):
    """Forum init：process_fleet_construction + 合同生成 + …（真实 producer）。"""
    res = forum_api.initialize_forum_turn(state)
    assert res["success"], f"initialize_forum_turn failed: {res.get('message')}"
    return res


def _forum_resolve_advance(state):
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], f"resolve_forum failed: {resolved.get('message')}"
    adv = forum_api.advance_forum_phase(state, P1)
    assert adv["success"], f"advance_forum_phase failed: {adv.get('message')}"
    return resolved


def _finish_year_from_population(state, war_id, consul_figure_id=0):
    """自 Forum 结算后推进至下一年：Forum advance（若未执行）→ Population → Senate（0/N）→
    Combat（真实 naval 门，无成舰 auto-DEFEAT 确定性）→ resolution → advance_year。"""
    if not state.is_phase_executed("forum"):
        adv_forum = forum_api.advance_forum_phase(state, P1)
        assert adv_forum["success"], f"advance_forum_phase failed: {adv_forum.get('message')}"
    _population_round(state, consul_figure_id=consul_figure_id)
    _senate_resolve_advance(state)
    _combat_naval_gate_year(state, war_id)


def year1_approved_contract(state, ctx, modified_budget=350):
    """Y1：PENDING 生成（冻结 A）→ Senate PASS（B=modified_budget）→ BUDGETED。

    返回 fleet 合同对象（BUDGETED，A=_original_budget、B=_approved_budget、base_cost=B）。
    """
    war = ctx["war"]
    _forum_init(state)
    hits = _fleet_contract_for(state, war)
    assert len(hits) == 1, f"expected exactly 1 fleet contract, got {len(hits)}"
    contract = hits[0]
    assert contract.status == ContractStatus.PENDING
    comp = contract.recommended_fleet_composition
    assert comp, comp
    # A 冻结不变量（设计 §3.1：_original_budget == base_cost == total_budget > 0）
    assert contract._original_budget > 0, contract._original_budget
    assert contract._original_budget == contract.base_cost == contract.total_budget

    _forum_resolve_advance(state)
    data = _population_round(state, consul_figure_id=ctx["target"].id,
                             rival_vote_figure_id=ctx["rival"].id)
    winner = None
    for er in data.get("election_results", []):
        if er["office"] == "consul":
            winner = er
    assert winner is not None and winner["figure_id"] == ctx["target"].id, winner
    assert PoliticalSystem(state)._is_eligible_consul(ctx["target"]) is True

    prop = senate_api.propose(state, P1, "budget", contract_id=contract.id,
                              modified_budget=modified_budget)
    assert prop["success"], f"propose budget failed: {prop.get('message')}"
    proposal_id = prop["data"]["proposal_id"]
    voted = senate_api.vote(state, P1, [proposal_id], [True])
    assert voted["success"], voted.get("message")
    resolved = senate_api.resolve_senate(state, vote_decider=DeterministicApproveDecider())
    assert resolved["success"], resolved.get("message")
    assert contract.status == ContractStatus.BUDGETED
    # B 独立落点（§3.1）：PASS 即使未改金额也写 approved_budget
    assert contract.approved_budget == modified_budget, contract.approved_budget
    assert contract._original_budget == contract._total_budget  # A 不被 Senate 改写
    _senate_resolve_advance(state)
    _combat_naval_gate_year(state, war.id)
    return contract


def _award_block(state, ctx, contract, amount, construction_cost=None, profit_rate=None):
    """Y2 段：Forum init → place_bid → resolve_forum award（真实 producer 物化 BUILDING）。"""
    _mortality_revenue_round(state)
    _forum_init(state)
    bid = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                              amount=amount, construction_cost=construction_cost,
                              profit_rate=profit_rate)
    assert bid["success"], f"place_bid failed: {bid.get('message')}"
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], resolved.get("message")
    assert contract.status == ContractStatus.ACTIVE
    return resolved


# ===========================================================================
# T-R3-07：A280/B350/C300/D240 四权威全链 + roundtrip + 多期守恒 + 双派系 award
# ===========================================================================

class TestS3FourAuthorities(unittest.TestCase):
    def _awarded_canonical(self, enemy_naval=20):
        """真实 producer 链：Y1 A280/B350 → Y2 bid C300+D240 → award → 7 BUILDING →
        完成 Y2（Forum advance → Pop/Senate/Combat → year）→ 返回时已至 Y3 起点。"""
        state, ctx = _build_fleet_chain_state(enemy_naval=enemy_naval)
        war = ctx["war"]
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        assert contract._original_budget == 280, contract._original_budget  # 7×trireme40
        resolved = _award_block(state, ctx, contract, amount=300, construction_cost=240)
        _finish_year_from_population(state, war.id)
        return state, ctx, contract, resolved

    def test_t07_four_authorities_chain_and_roundtrip(self):
        """280/350/300/240 四权威全链与 roundtrip；gross=60；B award 后不丢。"""
        state, ctx, contract, resolved = self._awarded_canonical()
        war = ctx["war"]

        # 四权威（§3.1）：A/B/C/D 独立持久
        self.assertEqual(contract._original_budget, 280)     # A baseline
        self.assertEqual(contract.approved_budget, 350)      # B approved（Senate PASS）
        self.assertEqual(contract.contract_price, 300)       # C winning price
        self.assertEqual(contract._actual_cost, 240)         # D actual cost（入队持久，非 award 重算）
        # award 后兼容投影：base_cost=C（public-works payment 消费），B 仍 350 不丢
        self.assertEqual(contract.base_cost, 300)
        self.assertEqual(contract.approved_budget, 350)
        self.assertEqual(contract._total_budget, 280)        # A 历史别名不变

        # 7 艘 BUILDING 物化（真实 award producer）
        building = [f for f in state.naval_system.get_all_fleets() if f.is_building]
        self.assertEqual(len(building), 7)
        self.assertTrue(all(f._target_war_id == war.id for f in building))
        self.assertFalse(contract.is_fleet_construction_paid)  # 付款事实未提前

        # roundtrip：新数据无损（SC09 contract serializer 侧）
        from src.core.entities.contract import Contract as ContractEntity
        d = contract.to_dict()
        rt = ContractEntity.from_dict(d)
        self.assertEqual(rt._original_budget, 280)
        self.assertEqual(rt.approved_budget, 350)
        self.assertEqual(rt.contract_price, 300)
        self.assertEqual(rt._actual_cost, 240)
        self.assertEqual(rt.base_cost, 300)
        self.assertEqual(rt.status, ContractStatus.ACTIVE)
        self.assertEqual(rt._target_war_id, war.id)
        self.assertEqual(rt._fleet_type, "trireme")
        self.assertEqual(rt._build_time, 1)
        # 8-tuple enqueue 的 JSON 可序列化性由 t08 的 pending 断言覆盖（award 后 pending 已
        # 被 resolve_forum 清空——此处不断言空载体）

    def test_t07_revenue_gross60_and_paid(self):
        """Y3 Revenue：真实 public-works payment C300/costD240/gross60/tax/wealth；_paid 与
        maturation 分立（付款完成先于 COMPLETED）。"""
        state, ctx, contract, _resolved = self._awarded_canonical()
        war = ctx["war"]
        # Y3 M/R：Revenue 先于 Forum maturity（设计 §8.2 step 8 phase 顺序）
        rev = _mortality_revenue_round(state)
        rows = rev["data"]["data"]["contract_rows"]
        row = next(r for r in rows if r["contract_id"] == contract.id)
        self.assertEqual(row["type"], "public_works")
        self.assertEqual(row["payment"], 300)
        self.assertEqual(row["cost"], 240)
        # gross（税前）恒 = C−D = 60（tax/rounding authority 不因本窄修改变）
        self.assertEqual(row["payment"] - row["cost"], 60)
        self.assertTrue(contract.is_fleet_construction_paid)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)  # maturation 前不 COMPLETED

        g1 = _forum_init(state)
        completed = g1["data"].get("completed_fleets", [])
        self.assertEqual(len(completed), 7)
        self.assertEqual(contract.status, ContractStatus.COMPLETED)
        fleets = [f for f in state.naval_system.get_all_fleets() if f._target_war_id == war.id]
        self.assertTrue(all(f.status in (FleetStatus.AVAILABLE, FleetStatus.ON_MISSION)
                            for f in fleets), [f.status for f in fleets])

    def test_t07_multi_period_conservation(self):
        """Fleet build_time=2（quinquereme 5 艘 A280/B350/C300/D240）：总付款 C、总成本 D、
        gross60 跨两期守恒；annual C//N、D//N；末期成本 D-(N-1)*annual。"""
        state, ctx = _build_fleet_chain_state(enemy_naval=20, default_type="quinquereme")
        war = ctx["war"]
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        # 5 × quinquereme build_cost 56 = A280；build_time=2
        self.assertEqual(contract._original_budget, 280, contract._original_budget)
        self.assertEqual(contract._build_time, 2)

        _award_block(state, ctx, contract, amount=300, construction_cost=240)
        # award N 同步（§3.6）：唯一 N = build_time=2
        self.assertEqual(contract.remaining_years, 2)
        self.assertEqual(contract.duration_years, 2)
        self.assertEqual(contract.construction_years, 2)
        self.assertEqual(contract.annual_income, 150)  # C//N
        self.assertEqual(contract.annual_cost, 120)    # D//N

        # Y2 余段（award 后）：Population（ABSTAIN）→ Senate（0 提案）→ Combat（无成舰
        # auto-DEFEAT 确定性）→ advance_year → Y3
        _finish_year_from_population(state, war.id)

        # Y3 Revenue（remaining=2 → 常规年付 C//N、D//N）
        rev1 = _mortality_revenue_round(state)
        rows1 = rev1["data"]["data"]["contract_rows"]
        row1 = next(r for r in rows1 if r["contract_id"] == contract.id)
        self.assertEqual(row1["payment"], 150)
        self.assertEqual(row1["cost"], 120)
        self.assertEqual(contract.remaining_years, 1)
        # Y3 余段：Forum init + resolve → advance → Population/Senate/Combat → advance_year
        _forum_init(state)
        _forum_resolve_advance(state)
        _finish_year_from_population(state, war.id)

        # Y4 Revenue（remaining=1 → 末期 payment=C-total_spent；cost=D-(N-1)*annual）
        rev2 = _mortality_revenue_round(state)
        rows2 = rev2["data"]["data"]["contract_rows"]
        row2 = next(r for r in rows2 if r["contract_id"] == contract.id)
        self.assertEqual(row2["payment"], 150)   # 300 - 150
        self.assertEqual(row2["cost"], 120)      # 240 - 1×120
        self.assertTrue(contract.is_fleet_construction_paid)
        self.assertEqual(contract.total_spent, 300)
        self.assertEqual(contract.remaining_years, 0)
        # Y4 Forum init → 成熟（build_end = award_turn + build_time = Y2+2）
        g4 = _forum_init(state)
        self.assertEqual(len(g4["data"].get("completed_fleets", [])), 5)
        self.assertEqual(contract.status, ContractStatus.COMPLETED)

    def test_t07_award_multi_faction_not_current_player(self):
        """§3.6 反例：双派系合法 bid（低价 = 非当前派系）award 不被 current-player guard 拒。"""
        state, ctx = _build_fleet_chain_state()
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        _mortality_revenue_round(state)
        _forum_init(state)
        # P1（当前）→ 出 310；P2（另一派系）→ 出 300（更低价）
        bid1 = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                   amount=310, construction_cost=240)
        self.assertTrue(bid1["success"], bid1.get("message"))
        bid2 = forum_api.place_bid(state, P2, ctx["rival_eques"].id, contract.id,
                                   amount=300, construction_cost=240)
        self.assertTrue(bid2["success"], bid2.get("message"))

        # 公示时 current player = P1；P2 的合法 bid 必须仍可 award（不重放 current-player guard）
        state.set_current_player(P1)
        resolved = forum_api.resolve_forum(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertEqual(contract.status, ContractStatus.ACTIVE)
        self.assertEqual(contract.contract_price, 300)
        self.assertEqual(contract.awarded_faction, F_RIVAL)  # 低价 300 胜（P2 派系）
        self.assertEqual(contract.awarded_to, ctx["rival_eques"].id)
        self.assertEqual(contract._actual_cost, 240)

    def test_t07_award_invalid_candidates_filtered(self):
        """§3.6：失效候选先过滤（figure 死亡/非 EQUES/离派系）→ 最低价；全失效 fail-closed。"""
        # 场景 1：最低价 bidder 死亡 → 过滤后次低价胜
        state, ctx = _build_fleet_chain_state()
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        _mortality_revenue_round(state)
        _forum_init(state)
        forum_api.place_bid(state, P1, ctx["eques"].id, contract.id, amount=300, construction_cost=240)
        forum_api.place_bid(state, P1, ctx["eques2"].id, contract.id, amount=310, construction_cost=250)
        # eques（低价 300）在公示前死亡 → 候选失效
        ctx["eques"].is_dead = True
        resolved = forum_api.resolve_forum(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertEqual(contract.status, ContractStatus.ACTIVE)
        self.assertEqual(contract.awarded_to, ctx["eques2"].id)
        self.assertEqual(contract.contract_price, 310)

        # 场景 2：全部候选失效 → fail-closed：无 winner、合同保持 BUDGETED、零 Fleet/付款
        state2, ctx2 = _build_fleet_chain_state()
        contract2 = year1_approved_contract(state2, ctx2, modified_budget=350)
        _mortality_revenue_round(state2)
        _forum_init(state2)
        forum_api.place_bid(state2, P1, ctx2["eques"].id, contract2.id,
                            amount=300, construction_cost=240)
        ctx2["eques"].is_dead = True
        state2.clear_forum_pending()  # 防误伤：先清空 recruitment 等；重新只放 bid
        forum_api.place_bid(state2, P1, ctx2["eques2"].id, contract2.id,
                            amount=310, construction_cost=250)
        ctx2["eques2"].is_dead = True
        resolved2 = forum_api.resolve_forum(state2)
        self.assertTrue(resolved2["success"], resolved2.get("message"))
        self.assertEqual(contract2.status, ContractStatus.BUDGETED)  # 无 winner
        self.assertEqual(state2.naval_system.get_all_fleets(), [])   # 零第二批 Fleet
        self.assertFalse(contract2.is_fleet_construction_paid)


# ===========================================================================
# T-R3-08：human 双输入（C+D）+ 入队守卫全矩阵 + pending 回显 + 自身 pending 非 duplicate
# ===========================================================================

class TestS3HumanDualInput(unittest.TestCase):
    def _budgeted(self):
        state, ctx = _build_fleet_chain_state()
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        _mortality_revenue_round(state)
        _forum_init(state)
        return state, ctx, contract

    def test_t08_dual_input_capture_and_echo(self):
        """GUI/API 双输入透传：place_bid(C, construction_cost=D) → 8 元组 pending → response
        echo construction_cost/gross_profit/profit_rate；viewer 只暴露本派系。"""
        state, ctx, contract = self._budgeted()
        res = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                  amount=300, construction_cost=240)
        self.assertTrue(res["success"], res.get("message"))
        data = res["data"]
        self.assertEqual(data["construction_cost"], 240)
        self.assertEqual(data["gross_profit"], 60)
        self.assertAlmostEqual(data["profit_rate"], 0.2, places=9)

        pending = state.get_forum_pending()["contract_bids"]
        self.assertEqual(len(pending), 1)
        bid = pending[0]
        self.assertEqual(len(bid), 8)                       # 8 元组
        self.assertEqual(bid[0], contract.id)
        self.assertEqual(bid[3], 300)                       # C（前 7 索引不变）
        self.assertEqual(bid[7], 240)                       # D 尾部追加
        # viewer DTO 回显
        view = forum_api.get_forum_view(state, P1)["data"]
        mine = [b for b in view["viewer_contract_bids"] if b["contract_id"] == contract.id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["construction_cost"], 240)
        self.assertEqual(mine[0]["gross_profit"], 60)
        self.assertAlmostEqual(mine[0]["profit_rate"], 0.2, places=9)
        # 不泄漏他派系 bid（P2 无 bid 记录）
        view2 = forum_api.get_forum_view(state, P2)["data"]
        self.assertEqual(view2["viewer_contract_bids"], [])

        # _pending_contract_rows 增四字段（§3.3：is_fleet/baseline(A)/approved(B)/bid_ceiling）
        row = next(r for r in view["pending_contracts"] if r["id"] == contract.id)
        self.assertTrue(row["is_fleet_construction"])
        self.assertEqual(row["baseline_construction_cost"], 280)
        self.assertEqual(row["approved_budget"], 350)
        self.assertEqual(row["bid_ceiling"], 350)

    def test_t08_admission_guard_matrix(self):
        """入队守卫：C>B、D>C、D<0、D invalid（NaN/Inf/str/float-frac/bool）、C invalid、
        missing/dead eques、新请求重复拒。"""
        def _place(**kw):
            state, ctx, contract = self._budgeted()
            base = {"amount": 300, "construction_cost": 240}
            base.update(kw)
            return forum_api.place_bid(state, P1, base.pop("figure_id", ctx["eques"].id),
                                       contract.id, **base), state, ctx, contract

        r, _, _, contract = _place(amount=400)                      # C > B(350) → 拒
        self.assertFalse(r["success"]); self.assertEqual(contract.status, ContractStatus.BUDGETED)
        r, _, _, _ = _place(construction_cost=360)                  # D > C → 拒
        self.assertFalse(r["success"])
        r, _, _, _ = _place(construction_cost=-1)                   # D < 0 → 拒
        self.assertFalse(r["success"])
        r, _, _, _ = _place(construction_cost=0)                    # D = 0 合法入队（q=0 语义归 S4）
        self.assertTrue(r["success"], r.get("message"))
        r, _, _, _ = _place(construction_cost=240.5)                # float fractional → 拒
        self.assertFalse(r["success"])
        r, _, _, _ = _place(construction_cost=True)                 # bool → 拒
        self.assertFalse(r["success"])
        r, _, _, _ = _place(construction_cost=float("nan"))         # NaN → 拒
        self.assertFalse(r["success"])
        r, _, _, _ = _place(amount=True)                            # C bool → 拒
        self.assertFalse(r["success"])
        # missing Eques（NOBILE consul 候选）→ 拒
        state, ctx, contract = self._budgeted()
        r = forum_api.place_bid(state, P1, ctx["target"].id, contract.id,
                                amount=300, construction_cost=240)
        self.assertFalse(r["success"])

        # dead eques → 拒
        state, ctx, contract = self._budgeted()
        ctx["eques"].is_dead = True
        r = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                amount=300, construction_cost=240)
        self.assertFalse(r["success"])

        # 新请求重复 (contract, figure) → 拒；不同 figure 同合同 → 允（自身 pending 非 duplicate 前置）
        state, ctx, contract = self._budgeted()
        r1 = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                 amount=300, construction_cost=240)
        self.assertTrue(r1["success"])
        r2 = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                 amount=290, construction_cost=230)
        self.assertFalse(r2["success"])
        r3 = forum_api.place_bid(state, P1, ctx["eques2"].id, contract.id,
                                 amount=290, construction_cost=230)
        self.assertTrue(r3["success"], r3.get("message"))

        # 显式 D 与显式 rate 冲突 → 拒；一致 → 允
        state, ctx, contract = self._budgeted()
        rc = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                 amount=300, construction_cost=240, profit_rate=0.5)
        self.assertFalse(rc["success"], "D 与 rate 冲突应拒绝")
        rok = forum_api.place_bid(state, P1, ctx["eques2"].id, contract.id,
                                  amount=300, construction_cost=240, profit_rate=0.2)
        self.assertTrue(rok["success"], rok.get("message"))

    def test_t08_legacy_rate_path_persists_D_at_enqueue(self):
        """Legacy/AI explicit rate 路径（无 construction_cost）：入队时按 int(C*(1-rate)) 确定 D，
        一旦入队即持久；award 不再算一遍。"""
        state, ctx, contract = self._budgeted()
        res = forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                                  amount=300, profit_rate=0.2)
        self.assertTrue(res["success"], res.get("message"))
        pending = state.get_forum_pending()["contract_bids"]
        bid = pending[0]
        self.assertEqual(len(bid), 8)
        self.assertEqual(bid[7], 240)  # int(300×0.8) 入队持久
        resolved = forum_api.resolve_forum(state)
        self.assertTrue(resolved["success"])
        self.assertEqual(contract._actual_cost, 240)  # award 零重算（同值但走持久 D）
        self.assertEqual(contract.contract_price, 300)

    def test_t08_own_pending_not_duplicate_at_award(self):
        """§3.6：自身 pending 在 award 时非「新请求防重」；重复 settlement（合同已 ACTIVE/
        已物化）no-op 不二次付款、不造第二批 Fleet。"""
        state, ctx, contract = self._budgeted()
        forum_api.place_bid(state, P1, ctx["eques"].id, contract.id,
                            amount=300, construction_cost=240)
        resolved = forum_api.resolve_forum(state)
        self.assertTrue(resolved["success"])
        fleets_after_first = len(state.naval_system.get_all_fleets())
        self.assertEqual(fleets_after_first, 7)
        # 二次 resolve（同会期已 clear pending；合同 ACTIVE）→ no-op，零新增
        resolved2 = forum_api.resolve_forum(state)
        self.assertTrue(resolved2["success"], resolved2.get("message"))
        self.assertEqual(len(state.naval_system.get_all_fleets()), 7)


# ===========================================================================
# T-R3-09/10：AI decider —— 读 B、两 draw 独立、零重平衡
# ===========================================================================

class TestS3AiBidDecider(unittest.TestCase):
    def _bid_state(self):
        state, ctx, contract = self._budgeted_contract_only()
        knights = [ctx["eques"], ctx["eques2"]]
        return state, contract, knights

    def _budgeted_contract_only(self):
        state, ctx = _build_fleet_chain_state()
        contract = year1_approved_contract(state, ctx, modified_budget=350)
        _mortality_revenue_round(state)
        _forum_init(state)
        return state, ctx, contract

    def test_t09_ai_reads_senate_b(self):
        """T-R3-09：AI Senate B=350 报价可表达 C=300（固定合法 discount 1-300/350）；
        A=280 不被读作 ceiling（stale total_budget 读取会产生 240）。"""
        state, contract, knights = self._bid_state()
        self.assertEqual(contract.approved_budget, 350)
        self.assertEqual(contract._original_budget, 280)
        discount = 1 - 300 / 350  # 0.14285714285714285
        decider = AutoBidDecider()
        with patch("src.core.deciders.impl.auto_bid_decider.random.choice", return_value=knights[0]), \
             patch("src.core.deciders.impl.auto_bid_decider.random.uniform", side_effect=[discount, 0.2]):
            knight, amount, profit_rate = decider.decide_fleet_bid(contract, knights, state)
        self.assertEqual(knight.id, knights[0].id)
        self.assertEqual(amount, 300)
        self.assertNotEqual(amount, 240)  # A-ceiling 旧读法（280×0.857…）会产出 240
        self.assertEqual(amount, 300)
        self.assertAlmostEqual(profit_rate, 0.2)
        # 边际范围保持（R3-11：uniform 0.05-0.20、int 截断）
        self.assertTrue(0.05 <= discount <= 0.20)

    def test_t10_two_draws_independent(self):
        """T-R3-10：序列 mock——固定 draw1 改 draw2 → C 恒定、D 变；固定 draw2 改 draw1 →
        bid 折扣变、profit-rate 恒定。禁只 seed 跑一次。"""
        state, contract, knights = self._bid_state()
        d_fixed = 1 - 300 / 350
        decider = AutoBidDecider()

        with patch("src.core.deciders.impl.auto_bid_decider.random.choice", return_value=knights[0]), \
             patch("src.core.deciders.impl.auto_bid_decider.random.uniform",
                   side_effect=[d_fixed, 0.10]) as m1:
            k1, c1, p1 = decider.decide_fleet_bid(contract, knights, state)
        with patch("src.core.deciders.impl.auto_bid_decider.random.choice", return_value=knights[0]), \
             patch("src.core.deciders.impl.auto_bid_decider.random.uniform",
                   side_effect=[d_fixed, 0.20]) as m2:
            k2, c2, p2 = decider.decide_fleet_bid(contract, knights, state)
        # draw1 固定 → C 恒定
        self.assertEqual(c1, 300)
        self.assertEqual(c2, 300)
        # draw2 改变 → profit_rate 改变（D=int(C×(1-rate)) 随之改变：270 vs 240）
        self.assertAlmostEqual(p1, 0.10)
        self.assertAlmostEqual(p2, 0.20)
        self.assertEqual(int(c1 * (1 - p1)), 270)
        self.assertEqual(int(c2 * (1 - p2)), 240)
        # 两次独立调用各恰两 draw（顺序：discount → profit）
        self.assertEqual(m1.call_count, 2)
        self.assertEqual(m2.call_count, 2)

        # 反方向：draw2 固定 → profit 恒定；draw1 改变 → C 变
        with patch("src.core.deciders.impl.auto_bid_decider.random.choice", return_value=knights[0]), \
             patch("src.core.deciders.impl.auto_bid_decider.random.uniform",
                   side_effect=[0.10, 0.20]) as m3:
            k3, c3, p3 = decider.decide_fleet_bid(contract, knights, state)
        with patch("src.core.deciders.impl.auto_bid_decider.random.choice", return_value=knights[0]), \
             patch("src.core.deciders.impl.auto_bid_decider.random.uniform",
                   side_effect=[d_fixed, 0.20]) as m4:
            k4, c4, p4 = decider.decide_fleet_bid(contract, knights, state)
        self.assertEqual(c3, int(350 * 0.9))
        self.assertEqual(c4, 300)
        self.assertAlmostEqual(p3, 0.20)
        self.assertAlmostEqual(p4, 0.20)
        self.assertEqual(m3.call_count, 2)
        self.assertEqual(m4.call_count, 2)

    def test_t10_interface_stable_3tuple_and_no_rebalance(self):
        """3-tuple (knight, amount, profit_rate) 接口稳定（auto_player_processor 消费不变）；
        边际范围/截断保持：amount ∈ [int(350×0.80), int(350×0.95)]。"""
        state, contract, knights = self._bid_state()
        decider = AutoBidDecider()
        for _ in range(30):
            with patch("src.core.deciders.impl.auto_bid_decider.random.choice",
                       return_value=knights[0]):
                result = decider.decide_fleet_bid(contract, knights, state)
            self.assertEqual(len(result), 3)
            knight, amount, profit_rate = result
            self.assertEqual(knight.id, knights[0].id)
            self.assertGreaterEqual(amount, int(350 * 0.80))
            self.assertLessEqual(amount, int(350 * 0.95))
            self.assertTrue(0.05 <= profit_rate <= 0.20)


# ===========================================================================
# SC09 serializer 侧：新数据无损 + legacy 诚实
# ===========================================================================

class TestS3Serializer(unittest.TestCase):
    def test_serializer_legacy_unknown_b_honest(self):
        """legacy-shaped dict（旧 serializer 无 _approved_budget/_actual_cost 键）→
        from_dict：B=legacy_unknown 不伪造、D=None；ACTIVE public works 诚实标注。"""
        from src.core.entities.contract import Contract as ContractEntity
        legacy = {
            "id": 7, "contract_type": "public_works", "_province_id": 0, "_create_turn": 1,
            "_contract_price": 300, "_profit_rate": 0.2, "_original_budget": 280,
            "_construction_years": 1, "_warranty_years": 0, "_annual_income": 300,
            "_warranty_remaining": 0, "_annual_cost": 300, "_is_extended": False,
            "_standard_warranty": 0, "status": "active", "name": "旧舰队合同",
            "description": "", "base_cost": 300, "expected_profit": 60,
            "duration_years": 1, "target_province": None, "project_type": None,
            "awarded_to": 30, "awarded_faction": "optimates", "awarded_turn": 51,
            "remaining_years": 1, "total_collected": 0, "total_spent": 0,
            "_profit_base": 0, "_is_under_execution": True, "_complete_turn": None,
            "_bids": [], "_winning_bid": None, "_tax_rate": None,
            "_is_fleet_construction": True,
            "_recommended_fleet_composition": [{"type": "trireme", "count": 7}],
            "_enemy_strength": 20, "_total_budget": 280, "_paid": False, "_annual_profit": 0,
        }
        c = ContractEntity.from_dict(legacy)
        # 过去的 Senate B 已被 base_cost 覆盖 → 不可重建，诚实 unknown（不伪造 350/280）
        self.assertIsNone(c.approved_budget)
        self.assertEqual(c._authority_source, "legacy_unknown")
        # C 从已保存 contract_price 恢复；D 无明确 _actual_cost → None（≠0）
        self.assertEqual(c.contract_price, 300)
        self.assertIsNone(c._actual_cost)
        self.assertEqual(c._original_budget, 280)  # A 可恢复（generator 冻结）
        # roundtrip 保持标注不漂移
        rt = ContractEntity.from_dict(c.to_dict())
        self.assertIsNone(rt.approved_budget)
        self.assertEqual(rt._authority_source, "legacy_unknown")

    def test_serializer_legacy_pending_A_from_total_budget(self):
        """旧 PENDING fleet：A 可从 _total_budget>0 恢复（_original_budget 缺键 fallback）。"""
        from src.core.entities.contract import Contract as ContractEntity
        legacy = {
            "id": 8, "contract_type": "public_works", "_province_id": 0, "_create_turn": 1,
            "_contract_price": 0, "_profit_rate": 0.0, "_construction_years": 0,
            "_warranty_years": 0, "_annual_income": 0, "_warranty_remaining": 0,
            "_annual_cost": 0, "_is_extended": False, "_standard_warranty": 0,
            "status": "pending", "name": "旧待批舰队合同", "description": "",
            "base_cost": 280, "expected_profit": 0, "duration_years": 1,
            "target_province": None, "project_type": None, "awarded_to": None,
            "awarded_faction": None, "awarded_turn": None, "remaining_years": 0,
            "total_collected": 0, "total_spent": 0, "_profit_base": 0,
            "_is_under_execution": False, "_complete_turn": None, "_bids": [],
            "_winning_bid": None, "_tax_rate": None, "_is_fleet_construction": True,
            "_recommended_fleet_composition": [{"type": "trireme", "count": 7}],
            "_enemy_strength": 20, "_total_budget": 280, "_paid": False, "_annual_profit": 0,
        }
        c = ContractEntity.from_dict(legacy)
        self.assertEqual(c._original_budget, 280)
        self.assertIsNone(c.approved_budget)
        self.assertEqual(c.status, ContractStatus.PENDING)


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
