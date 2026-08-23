import pytest
from unittest.mock import MagicMock

from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import ClassTier, Figure, OfficeTerm
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.entities.war import War, WarStatus, WarType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.core.systems.war_system import WarSystem


@pytest.fixture
def state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-264)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    optimates = Faction(id="optimates", name="Optimates", treasury=100)
    populares = Faction(id="populares", name="Populares", treasury=100)
    state.add_faction(optimates)
    state.add_faction(populares)

    consul = Figure(id=1, name="Consul", faction_id="optimates", age=45)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 100
    senator = Figure(id=2, name="Senator", faction_id="populares", age=50)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 80
    tribune = Figure(id=3, name="Tribune", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    candidate = Figure(id=4, name="Ex Consul", faction_id="optimates", age=55)
    candidate.office_history = [OfficeTerm("consul", start_turn=1, end_turn=3)]

    for fig in (consul, senator, tribune, candidate):
        state.add_member(fig)
    optimates.member_ids.extend([1, 4])
    populares.member_ids.extend([2, 3])

    state.add_player(Player("player1", "optimates", PlayerType.HUMAN))
    state.add_player(Player("player2", "populares", PlayerType.HUMAN))
    state.set_turn_order(["player1", "player2"])
    state.set_current_player("player1")
    return state


def add_threat_war(state, war_id="war1"):
    war = War(id=war_id, name="Test War", war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    return war


def add_truce_war(state, war_id="peace1"):
    war = War(id=war_id, name="Truce War", war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"indemnity": 100, "duration": 3, "status": "pending"})
    state.get_war_system()._truce_wars.append(war)
    return war


def test_create_all_supported_proposal_types(state):
    politics = PoliticalSystem(state)
    add_threat_war(state)
    add_truce_war(state)

    province = Province(10, "Sicily", 1000, conquered=True, governor_type="proconsul")
    state.add_province(province)

    contract = state.create_contract(ContractType.TAX_FARMING, province_id=10, base_cost=100, current_turn=5)
    contract.status = ContractStatus.PENDING

    assert politics.create_proposal("player1", "war", war_id="war1", legions=6)["success"]
    assert politics.create_proposal("player1", "peace", war_id="peace1")["success"]
    assert politics.create_proposal("player1", "governor", province_id=10, candidate_id=4)["success"]
    assert politics.create_proposal("player1", "budget", contract_id=contract.id)["success"]
    # AU-7：land 主输入改 amount_C（int）；percent 派生（默认公地 1000 → 50/1000 = 0.05）
    assert politics.create_proposal("player1", "land", act_type="sale", amount_C=50)["success"]

    proposals = state.get_senate_proposals()
    assert [proposal["type"] for proposal in proposals] == ["war", "peace", "governor", "budget", "land"]
    assert proposals[-1]["amount_C"] == 50
    assert proposals[-1]["percent"] == 0.05


def test_calculate_vote_result_passed(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05})
    state.record_senate_vote("player1", proposal_id, True)
    state.record_senate_vote("player2", proposal_id, True)

    result = politics.calculate_vote_result(state.get_senate_proposals()[0])

    assert result["passed"] is True
    assert result["vetoed"] is False


def test_calculate_vote_result_rejected(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05})
    state.record_senate_vote("player1", proposal_id, False)
    state.record_senate_vote("player2", proposal_id, False)

    result = politics.calculate_vote_result(state.get_senate_proposals()[0])

    assert result["passed"] is False
    assert result["support_influence"] == 0


def test_calculate_vote_result_vetoed(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05})
    state.record_senate_vote("player1", proposal_id, True)
    state.record_senate_veto(proposal_id)

    result = politics.calculate_vote_result(state.get_senate_proposals()[0])

    assert result["passed"] is False
    assert result["vetoed"] is True


def test_governor_execution_uses_public_designate_method(state):
    politics = PoliticalSystem(state)
    province = Province(10, "Sicily", 1000, conquered=True, governor_type="proconsul", governor_id=1)
    state.add_province(province)
    proposal = {
        "id": 1,
        "type": "governor",
        "province_id": 10,
        "candidate_id": 4,
        "old_governor_id": 1,
    }

    result = politics.execute_passed_proposal(proposal)

    assert result["success"] is True
    assert province.governor_designate_id == 4
    assert province.old_governor_id == 1
    assert state.get_member(4).is_absent is True


def test_restore_rejected_peace_uses_war_system_public_method(state):
    politics = PoliticalSystem(state)
    war = add_truce_war(state)
    war.commander_id = 1

    restored = politics.restore_rejected_peace_wars([war])

    ws = state.get_war_system()
    assert restored == [war]
    assert war in ws.get_active_wars()
    assert war not in ws.get_truce_wars()
    assert war.peace_treaty is None
    assert war.commander_id == 1


def test_build_initial_info_presiding_officer_has_faction(state):
    """WP-05V V1 DP-7: 主持 DTO 增补 faction_id / faction_name。"""
    politics = PoliticalSystem(state)
    info = politics.build_initial_info()
    po = info["data"]["presiding_officer"]
    assert po["figure_id"] == 1
    assert po["faction_id"] == "optimates"
    assert po["faction_name"] == "Optimates"


def test_build_initial_info_presiding_no_faction_degrades(state):
    """WP-05V V1 DP-7: 主持无派系时降级 faction_id=None / faction_name=""。"""
    # 添加一个无派系、更高阶的独裁官作为主持（dictator rank 6 > consul rank 4）
    dictator = Figure(id=9, name="Dictator", faction_id=None, age=50)
    dictator.office = "dictator"
    dictator.class_tier = ClassTier.NOBILE
    dictator.influence = 200
    state.add_member(dictator)

    politics = PoliticalSystem(state)
    info = politics.build_initial_info()
    po = info["data"]["presiding_officer"]
    assert po["figure_id"] == 9
    assert po["faction_id"] is None
    assert po["faction_name"] == ""


# ==================== WP-C-R1 AU-14: NT-2 / NT-4（权威谓词正/负向，ED-01/ED-02） ====================

def _with_authoritative_ranges(state):
    """注入 ODR 权威值域 config（ED-01/ED-02 CLOSED 值，与 game_config.json 一致）。"""
    state.config.economic_rules.senate_budget = {
        "public_works_min": 1, "public_works_max_ratio": 1.5,
        "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
    }
    state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}
    return state


# ---- NT-2: T014-5/6/7/8 预算谓词 ----

def test_budget_reject_below_min(state):
    """T014-5：建造 <1T → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=10, base_cost=100, current_turn=5)
    proposal = {"type": "budget"}
    result = politics._populate_proposal(proposal, "budget", contract_id=contract.id, modified_budget=0)
    assert result["success"] is False
    assert "低于允许范围" in result["message"]


def test_budget_reject_above_max(state):
    """T014-6：建造 >base×150% → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=10, base_cost=100, current_turn=5)
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=contract.id, modified_budget=151)
    assert result["success"] is False
    assert "超过允许范围" in result["message"]


def test_budget_reject_non_int(state):
    """T014-7：非 int → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=10, base_cost=100, current_turn=5)
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=contract.id, modified_budget=100.5)
    assert result["success"] is False
    assert "整数" in result["message"]


def test_budget_reject_missing_contract(state):
    """合同不存在 → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=9999, modified_budget=50)
    assert result["success"] is False
    assert "合同不存在" in result["message"]


def test_budget_tax_farming_boundaries(state):
    """T014-5/6 包税：min=base×75% / max=base×200%。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    contract = state.create_contract(ContractType.TAX_FARMING, province_id=10, base_cost=80, current_turn=5)
    # 59 < 60（base×75%）→ 拒绝
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=contract.id, modified_budget=59)
    assert result["success"] is False
    # 60 == min → 接受
    proposal = {"type": "budget"}
    result = politics._populate_proposal(proposal, "budget", contract_id=contract.id, modified_budget=60)
    assert result["success"] is True
    assert proposal["modified_budget"] == 60
    # 161 > 160（base×200%）→ 拒绝
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=contract.id, modified_budget=161)
    assert result["success"] is False


def test_budget_no_treasury_interception(state):
    """T014-8：提交期无国库承受力拦截（ODR：不禁止提交，决算期判破产）。"""
    _with_authoritative_ranges(state)
    state._treasury = 10  # 国库极小，仍应可提交
    politics = PoliticalSystem(state)
    contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=10, base_cost=100, current_turn=5)
    result = politics._populate_proposal({"type": "budget"}, "budget", contract_id=contract.id, modified_budget=150)
    assert result["success"] is True


# ---- NT-4: T015-5/6/7/12 军团谓词 ----

def test_war_reject_below_min(state):
    """T015-5：legions < 1（0 不可宣战）→ 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_min")
    result = politics._populate_proposal({"type": "war"}, "war", war_id="war_min", legions=0)
    assert result["success"] is False


def test_war_reject_over_pool(state):
    """T015-6：legions > 可用池 → 权威拒绝「可用军团不足」。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_pool")
    pool = len(state.get_military_system().get_available_legions())
    result = politics._populate_proposal({"type": "war"}, "war", war_id="war_pool", legions=pool + 1)
    assert result["success"] is False
    assert "可用军团不足" in result["message"]


def test_war_reject_non_int(state):
    """T015-5：非 int → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_nonint")
    result = politics._populate_proposal({"type": "war"}, "war", war_id="war_nonint", legions=4.0)
    assert result["success"] is False
    assert "整数" in result["message"]


def test_war_reject_missing_war(state):
    """war 不存在 → 权威拒绝。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "war"}, "war", war_id="missing_war", legions=4)
    assert result["success"] is False
    assert "战争不存在" in result["message"]


def test_war_multi_war_sum_reject(state):
    """T015-12：多战争总和 sum(所有 war legions) > 可用池 → 拒绝「可用军团不足」。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_sum1")
    add_threat_war(state, "war_sum2")
    pool = len(state.get_military_system().get_available_legions())
    # 先提交 war_sum1 占满可用池（单 war 合法）
    proposal1 = {"type": "war"}
    result1 = politics._populate_proposal(proposal1, "war", war_id="war_sum1", legions=pool)
    assert result1["success"] is True
    state.add_senate_proposal(proposal1)
    # 再提交 war_sum2（即使仅 1 个）→ 总和超池 → 拒绝
    result2 = politics._populate_proposal({"type": "war"}, "war", war_id="war_sum2", legions=1)
    assert result2["success"] is False
    assert "可用军团不足" in result2["message"]


def test_war_multi_war_sum_ok_within_pool(state):
    """T015-12 正向：多战争总和 ≤ 池 → 接受。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_ok1")
    add_threat_war(state, "war_ok2")
    proposal1 = {"type": "war"}
    result1 = politics._populate_proposal(proposal1, "war", war_id="war_ok1", legions=2)
    assert result1["success"] is True
    state.add_senate_proposal(proposal1)
    proposal2 = {"type": "war"}
    result2 = politics._populate_proposal(proposal2, "war", war_id="war_ok2", legions=2)
    assert result2["success"] is True


def test_war_no_treasury_interception(state):
    """T015-7：提交期无国库承受力拦截（ODR：不禁止提交）。"""
    _with_authoritative_ranges(state)
    state._treasury = 1
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_treasury")
    result = politics._populate_proposal({"type": "war"}, "war", war_id="war_treasury", legions=4)
    assert result["success"] is True


def test_war_default_4_within_pool(state):
    """T015-13 正向：default=4 ∈ [1..池] → 接受并写入。"""
    _with_authoritative_ranges(state)
    politics = PoliticalSystem(state)
    add_threat_war(state, "war_def")
    proposal = {"type": "war"}
    result = politics._populate_proposal(proposal, "war", war_id="war_def", legions=4)
    assert result["success"] is True
    assert proposal["legions"] == 4


# ==================== WP-D AU-1: Consul 单一谓词 + fallback 四条件（004 + Consul Discovery） ====================

def test_is_eligible_consul_predicate(state):
    """AU-1：在职 + 未死亡 + 未 absent。"""
    politics = PoliticalSystem(state)
    consul = state.get_member(1)
    assert politics._is_eligible_consul(consul) is True
    consul.is_absent = True
    assert politics._is_eligible_consul(consul) is False
    consul.is_absent = False
    consul.is_dead = True
    assert politics._is_eligible_consul(consul) is False
    consul.is_dead = False
    consul.office = None
    assert politics._is_eligible_consul(consul) is False


def test_find_consul_fallback_rejects_foreign_leader(state):
    """AU-1 P1 修正：fallback leader_ids[0] 为异派系领袖 → 不返回（fail-closed）。"""
    politics = PoliticalSystem(state)
    faction_opt = state.get_faction("optimates")
    # 主循环不命中（移除 consul 成员）→ fallback leader_ids[0]=2 为 populares 非 consul 元老
    faction_opt.member_ids.remove(1)
    state.turn.leader_ids = [2]
    assert politics._find_consul_for_faction(faction_opt) is None


def test_find_consul_fallback_requires_consul_office(state):
    """AU-1 P1 修正：fallback 领袖 office != consul → 不返回。"""
    politics = PoliticalSystem(state)
    faction_opt = state.get_faction("optimates")
    faction_opt.member_ids.remove(1)
    state.get_member(1).office = None  # 同派系但 office != consul
    state.turn.leader_ids = [1]
    assert politics._find_consul_for_faction(faction_opt) is None


def test_find_consul_fallback_absent_consul_rejected(state):
    """AU-1 P1 修正：fallback 领袖 is_absent → 不返回（对齐 _viewer_eligible_consul）。"""
    politics = PoliticalSystem(state)
    faction_opt = state.get_faction("optimates")
    faction_opt.member_ids.remove(1)
    state.get_member(1).is_absent = True  # 同派系 consul 但 absent
    state.turn.leader_ids = [1]
    assert politics._find_consul_for_faction(faction_opt) is None


def test_find_consul_fallback_valid_consul_returned(state):
    """AU-1 P1 修正 正向：fallback 四条件全满足（同派系 consul 未 absent 未死亡）→ 返回。"""
    politics = PoliticalSystem(state)
    faction_opt = state.get_faction("optimates")
    faction_opt.member_ids.remove(1)  # 主循环不命中 → 走 fallback
    state.turn.leader_ids = [1]
    assert politics._find_consul_for_faction(faction_opt) is state.get_member(1)


def test_create_proposal_non_consul_faction_fail_closed(state):
    """AU-1 负向（场景 P）：非执政官派系 propose → 权威拒绝（fallback 修正后不再误判）。"""
    politics = PoliticalSystem(state)
    state.get_faction("optimates").member_ids.remove(1)
    state.turn.leader_ids = [2]  # populares 非 consul 元老
    result = politics.create_proposal("player1", "land", act_type="sale", amount_C=50)
    assert result["success"] is False
    assert "只有执政官" in result["message"]


# ==================== WP-D AU-4: Tribune 单一谓词（ODR-WP-D-01 方案 B，CLOSED 2026-08-23） ====================

def test_is_eligible_tribune_predicate_scheme_b(state):
    """AU-4 方案 B（ODR-WP-D-01 裁决）：eligible = 在职 + 未死亡（is_absent 不参与判定）。"""
    politics = PoliticalSystem(state)
    tribune = state.get_member(3)
    assert politics._is_eligible_tribune(tribune) is True
    tribune.is_absent = True
    assert politics._is_eligible_tribune(tribune) is True  # 方案 B：absent 不影响资格（防线 2 保证正常路径不可达此态）
    tribune.is_absent = False
    tribune.is_dead = True
    assert politics._is_eligible_tribune(tribune) is False
    tribune.is_dead = False
    tribune.office = None
    assert politics._is_eligible_tribune(tribune) is False


def test_set_absent_guard_refuses_live_tribune(state):
    """防线 2（ODR-WP-D-01）：在职保民官置位 absent → fail-closed 拒绝（统一管理点 _set_absent）。"""
    politics = PoliticalSystem(state)
    tribune = state.get_member(3)
    assert politics._set_absent(tribune) is False
    assert tribune.is_absent is False  # 拒绝后未置位
    # 控制组：执政官正常置位；guard 范围 = office==tribune 且未死亡（死亡 tribune 不在拒绝范围）
    consul = state.get_member(1)
    assert politics._set_absent(consul) is True
    assert consul.is_absent is True
    tribune.is_dead = True
    assert politics._set_absent(tribune) is True


def test_tribune_absent_guard_module_level(state):
    """防线 2（ODR-WP-D-01）：模块级共享 guard 供外部置位点（senate_api/war_system/scenario_loader）内联防御。"""
    from src.core.systems.political_system import _tribune_absent_guard
    assert _tribune_absent_guard(state.get_member(3)) is False  # 在职 tribune → 拒绝
    assert _tribune_absent_guard(state.get_member(1)) is True   # consul → 允许
    assert _tribune_absent_guard(state.get_member(2)) is True   # 无 office → 允许


def test_execute_ai_takeover_direct_action_excludes_live_tribune(state):
    """防线 1（ODR-WP-D-01）：出征指挥官选择天然排除在职 tribune（office in consul/praetor 筛选）。

    正向：consul 被选为指挥官并置位 absent；负向：tribune 在 living 池中但永不入选、不被置位 absent。
    AU-R1-05b（G3 C1，D-1 采纳）：process_war_takeover 重构为 execute_ai_takeover_direct_action
    （Direct Action 语义）；Scheme B 防线 1 断言完整保留（迁移至新方法名）。
    """
    from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider

    war = War(id="war_active", name="Active War", war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.ACTIVE
    state.get_war_system()._active_wars.append(war)

    decider = MagicMock(spec=AutoWarTakeoverDecider)
    decider.decide_takeover.return_value = True

    politics = PoliticalSystem(state)
    records = politics.execute_ai_takeover_direct_action(decider=decider)

    assert war.commander_id == 1  # consul 入选（tribune 被 office 筛选排除）
    assert state.get_member(1).is_absent is True
    assert state.get_member(3).is_absent is False  # tribune 未被置位 absent
    assert state.get_member(3) not in [
        m for m in state.get_living_members() if m.office in ("consul", "praetor")
    ]
    # AU-R1-05b：返回成功接管记录列表 + provenance（trigger_source=ai_auto）
    assert len(records) == 1
    assert records[0]["war_id"] == war.id
    assert records[0]["trigger_source"] == "ai_auto"
    assert records[0]["action"] == "takeover"
    assert records[0]["commander_id"] == 1


def test_governor_candidates_exclude_tribune(state):
    """防线 1（ODR-WP-D-01）：总督候选人排除在职 tribune（即便具备执政官历史资历）。"""
    politics = PoliticalSystem(state)
    tribune = state.get_member(3)
    tribune.office_history = [OfficeTerm("consul", start_turn=1, end_turn=3)]  # 造资历，但 office=tribune 仍在职
    assert tribune not in politics.get_eligible_governor_candidates("proconsul")
    assert state.get_member(4) in politics.get_eligible_governor_candidates("proconsul")  # 正向对照：ex-consul 可任总督


def test_governor_proposal_rejects_tribune_candidate(state):
    """防线 1（ODR-WP-D-01）：总督任命提案拒绝在职 tribune 候选人（fail-closed）。"""
    politics = PoliticalSystem(state)
    province = Province(10, "Sicily", 1000, conquered=True, governor_type="proconsul")
    state.add_province(province)
    result = politics.create_proposal("player1", "governor", province_id=10, candidate_id=3)
    assert result["success"] is False
    assert "任职资格" in result["message"]


def test_record_veto_eligible_tribune_succeeds(state):
    """AU-4 正向：faction 内 eligible Tribune → 可否决。"""
    state.set_current_player("player2")
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "war"})
    result = politics.record_veto("player2", [proposal_id])
    assert result["success"] is True
    assert proposal_id in state.get_senate_vetoes_copy()


# ==================== WP-D AU-7: Land amount_C 值域谓词 ====================

def test_land_reject_missing_amount_c(state):
    """AU-7：percent-only 输入（无 amount_C）→ 权威拒绝（D-01 canonical conversion）。"""
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "land"}, "land", act_type="sale", percent=0.05)
    assert result["success"] is False
    assert "amount_C" in result["message"]


def test_land_reject_zero_amount_c(state):
    """AU-7：amount_C=0 → 权威拒绝（1 ≤ amount_C）。"""
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "land"}, "land", act_type="sale", amount_C=0)
    assert result["success"] is False


def test_land_reject_above_national(state):
    """AU-7：amount_C > national_public_land → 权威拒绝。"""
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "land"}, "land", act_type="distribution", amount_C=1001)
    assert result["success"] is False
    assert "超过" in result["message"]


def test_land_reject_non_int(state):
    """AU-7：非整数 amount_C → 权威拒绝。"""
    politics = PoliticalSystem(state)
    result = politics._populate_proposal({"type": "land"}, "land", act_type="sale", amount_C=50.5)
    assert result["success"] is False


def test_land_accept_float_integer(state):
    """AU-7：整数值 float（如 QML JS 跨槽边界 300.0）→ 接受并 int 归一（D-6 同源容忍）。"""
    politics = PoliticalSystem(state)
    proposal = {"type": "land"}
    result = politics._populate_proposal(proposal, "land", act_type="sale", amount_C=300.0)
    assert result["success"] is True
    assert proposal["amount_C"] == 300
    assert proposal["percent"] == 0.3


def test_land_derived_percent_stored(state):
    """AU-7 P2-06：proposal 同时存 amount_C + 派生 percent（build_issue_from_proposal 继续读 percent）。"""
    politics = PoliticalSystem(state)
    proposal = {"type": "land"}
    result = politics._populate_proposal(proposal, "land", act_type="sale", amount_C=50)
    assert result["success"] is True
    assert proposal["amount_C"] == 50
    assert proposal["percent"] == 0.05
    issue = politics.build_issue_from_proposal(proposal)
    assert issue["percent"] == 0.05


def test_execute_land_sale_consumes_amount_c(state):
    """AU-7 K：execute 消费 proposal[amount_C]（不再 int(land*percent) 二次重推）。"""
    state._national_public_land = 1000
    politics = PoliticalSystem(state)
    result = politics.execute_passed_proposal({
        "id": 1, "type": "land", "act_type": "sale", "amount_C": 300, "percent": 0.3,
    })
    assert result["success"] is True
    assert state.pending_land_sale_quota == 300


def test_execute_land_distribution_consumes_amount_c(state):
    """AU-7 L：execute 消费 amount_C → add_pending_land_act amount == amount_C。"""
    state._national_public_land = 1000
    politics = PoliticalSystem(state)
    result = politics.execute_passed_proposal({
        "id": 1, "type": "land", "act_type": "distribution", "amount_C": 200, "percent": 0.2,
    })
    assert result["success"] is True
    acts = state.get_pending_land_acts()
    assert len(acts) == 1
    assert acts[0]["type"] == "distribution"
    assert acts[0]["amount"] == 200
    assert acts[0]["percent"] == 0.2
