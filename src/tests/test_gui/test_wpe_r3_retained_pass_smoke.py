"""WP-E-R3 applicability smoke for six retained PASS identities."""

from src.api import combat_api, forum_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService
from src.core.systems.military_system import MilitarySystem
from src.core.systems.political_system import PoliticalSystem
from src.core.systems.war_system import WarSystem


def _state():
    state = GameState.create_for_testing({"testing": {"bypass_player_check": True}})
    state.turn = GameTurn(turn_number=5, year=-260)
    return state


def test_pass_smoke_01_resolution_revenue_shape_remains_additive():
    state = _state()
    data = EconomicService(state).settle_revenue_phase()["data"]
    assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]
    assert data["accounting_window"]["reconciled"] is True


def test_pass_smoke_02_public_land_four_carriers_remain_stable():
    state = _state()
    state._players["p"] = Player(player_id="p", faction_id="f", player_type=PlayerType.HUMAN)
    state._factions["f"] = Faction(id="f", name="Faction")
    actor = Figure(id=41, name="Actor", faction_id="f", wealth=1000)
    state.add_member(actor)
    state._factions["f"].member_ids = [41]
    state.set_pending_land_sale_quota(20)
    state.set_turn_land_sale_total(20)
    assert forum_api.buy_land(state, "p", 41, 2)["success"]

    first = forum_api.get_forum_view(state, "p")["data"]
    second = forum_api.get_forum_view(state, "p")["data"]
    assert first["land_sale_total"] == first["land_sale_quota"] == 20
    assert first["viewer_land_requests"] == second["viewer_land_requests"]


def test_pass_smoke_03_population_commander_return_identity_preserved():
    state = _state()
    state.treasury = 1000
    state._military_system = MilitarySystem(state)
    state._war_system = WarSystem(state)
    commander = Figure(id=51, name="Commander", office="proconsul", is_absent=True)
    state.add_member(commander)
    war = War(id="office-war", name="Office War")
    war.status = WarStatus.ACTIVE
    war.commander_id = commander.id
    state._war_system._active_wars.append(war)
    state._war_system.mobilize_war_legions(war, 1, commander.id)
    assert state._war_system.enter_truce(war, {"indemnity": 0, "duration": 2})
    war.set_peace_treaty_status("submitted")

    PoliticalSystem(state).execute_passed_peace_treaty(war)

    assert commander.is_absent is False
    assert commander.office == "ex-consul"
    assert war.commander_id is None


def test_pass_smoke_04_rejected_and_expired_treaty_identities_do_not_mix():
    state = _state()
    state._war_system = WarSystem(state)
    rejected = War(id="rejected", name="Rejected")
    rejected.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(rejected)
    assert state._war_system.enter_truce(rejected, {"status": "submitted", "duration": 2, "indemnity": 0})
    assert state._war_system.restore_rejected_peace_treaty(rejected.id)
    assert rejected.status == WarStatus.ACTIVE
    assert rejected.peace_treaty is None
    assert rejected.id == "rejected"


def test_pass_smoke_05_candidate_supply_identity_survives_forum_refresh():
    state = _state()
    state._players["p"] = Player(player_id="p", faction_id="f", player_type=PlayerType.HUMAN)
    state._factions["f"] = Faction(id="f", name="Faction")
    candidate = Figure.create_eques(61, None, 30)
    state.curia.add_figure(candidate)
    state.add_member(candidate)

    first = forum_api.get_forum_view(state, "p")["data"]["available_figures"]
    second = forum_api.get_forum_view(state, "p")["data"]["available_figures"]
    assert [row["id"] for row in first] == [row["id"] for row in second] == [61]


def test_pass_smoke_06_threat_auto_activation_projection_remains_canonical():
    state = _state()
    state._war_system = WarSystem(state)
    war = War(id="threat", name="Threat", start_year=-260, threat_level=0, escalate_rate=1)
    state._war_system._war_deck = [war]
    state._war_system.check_triggers(-260, verbose=False)
    state._war_system.escalate_threats()
    state._war_system.escalate_threats()
    state._war_system.escalate_threats()

    assert war.status == WarStatus.ACTIVE
    card = combat_api._war_card(war, state)
    assert card["legion_count"] == war.mobilized_legion_count == len(war.legion_numbers) == 0
    assert card["status"] == "active"
