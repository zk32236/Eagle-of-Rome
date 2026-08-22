import pytest

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
    assert politics.create_proposal("player1", "land", act_type="sale", percent=0.05)["success"]

    proposals = state.get_senate_proposals()
    assert [proposal["type"] for proposal in proposals] == ["war", "peace", "governor", "budget", "land"]


def test_calculate_vote_result_passed(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "percent": 0.05})
    state.record_senate_vote("player1", proposal_id, True)
    state.record_senate_vote("player2", proposal_id, True)

    result = politics.calculate_vote_result(state.get_senate_proposals()[0])

    assert result["passed"] is True
    assert result["vetoed"] is False


def test_calculate_vote_result_rejected(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "percent": 0.05})
    state.record_senate_vote("player1", proposal_id, False)
    state.record_senate_vote("player2", proposal_id, False)

    result = politics.calculate_vote_result(state.get_senate_proposals()[0])

    assert result["passed"] is False
    assert result["support_influence"] == 0


def test_calculate_vote_result_vetoed(state):
    politics = PoliticalSystem(state)
    proposal_id = state.add_senate_proposal({"type": "land", "act_type": "sale", "percent": 0.05})
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
