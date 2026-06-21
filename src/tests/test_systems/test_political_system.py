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
