"""WP-E-R3 canonical legion identity and approved-TRUCE lifecycle tests."""

from src.api import combat_api, gui_query_api
from src.core.entities.entities import GameTurn
from src.core.entities.legion import LegionStatus
from src.core.entities.war import War, WarStatus
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.political_system import PoliticalSystem
from src.core.systems.war_system import WarSystem


def _state_with_active_war(requested=3):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=10, year=-260)
    state.treasury = 1000
    ws = WarSystem(state)
    state._war_system = ws
    state._military_system = MilitarySystem(state)
    war = War(id="r3-war", name="R3 War", strength=5)
    war.status = WarStatus.ACTIVE
    war.proposed_legions = requested
    ws._active_wars.append(war)
    return state, ws, war


def _submit_treaty(ws, war, duration=2):
    assert ws.enter_truce(war, {"indemnity": 0, "duration": duration})
    war.set_peace_treaty_status("submitted")


def test_war_identity_count_and_legacy_save_calibration():
    war = War(id="w", name="War")
    war.legions_assigned = 99
    war.add_legion_number(2)
    war.add_legion_number(4)
    war.truce_recruit_target = 3

    restored = War.from_dict(war.to_dict())
    assert restored.legion_numbers == [2, 4]
    assert restored.mobilized_legion_count == restored.legions_assigned == 2
    assert restored.truce_recruit_target == 3

    legacy = war.to_dict()
    legacy["legion_numbers"] = []
    legacy["legions_assigned"] = 7
    restored_legacy = War.from_dict(legacy)
    assert restored_legacy.mobilized_legion_count == restored_legacy.legions_assigned == 0


def test_declaration_mobilization_uses_one_identity_derived_count():
    state, ws, war = _state_with_active_war(3)
    result = ws.mobilize_war_legions(war, 3, None)
    entities = state.get_military_system().get_legions_for_battle(war.id)

    assert result["success"] is True
    assert result["assigned"] == 3
    assert len(war.legion_numbers) == war.mobilized_legion_count == war.legions_assigned == len(entities)


def test_approval_disbands_immediately_and_expiry_rerecruits_target():
    state, ws, war = _state_with_active_war(3)
    ws.mobilize_war_legions(war, 3, None)
    original_numbers = war.legion_numbers
    _submit_treaty(ws, war)

    PoliticalSystem(state).execute_passed_peace_treaty(war)

    assert war.peace_treaty["status"] == "approved"
    assert war.truce_recruit_target == 3
    assert war.legion_numbers == []
    assert war.mobilized_legion_count == war.legions_assigned == 0
    for number in original_numbers:
        legion = state.get_military_system().get_legion_by_number(number)
        assert legion.status == LegionStatus.DISBANDED
        assert legion.war_id is None

    approved_card = combat_api._war_card(war, state)
    assert approved_card["legion_count"] == 0

    state.turn.turn_number = war.truce_end_turn
    assert state.process_truce_expiry() == [war.name]
    assigned = state.get_military_system().get_legions_for_battle(war.id)
    assert war.status == WarStatus.ACTIVE
    assert war.peace_treaty is None
    assert war.truce_recruit_target == 0
    assert len(war.legion_numbers) == war.mobilized_legion_count == len(assigned) == 3
    assert combat_api._war_card(war, state)["legion_count"] == 3
    assert gui_query_api._war_summary(state, war, "active")["legions_assigned"] == 3
    assert state.process_truce_expiry() == []


def test_expiry_projects_actual_partial_recruitment():
    state, ws, war = _state_with_active_war(3)
    ws.mobilize_war_legions(war, 3, None)
    _submit_treaty(ws, war)
    PoliticalSystem(state).execute_passed_peace_treaty(war)

    recruit_cost = state.get_economic_rule("legion_recruit_cost", 10)
    state.treasury = recruit_cost
    state.turn.turn_number = war.truce_end_turn
    result = ws.reactivate_expired_truce(war)

    assert result["requested"] == 3
    assert result["restored"] == 1
    assert result["shortfall"] == 2
    assert war.mobilized_legion_count == len(war.legion_numbers) == 1
    assert combat_api._war_card(war, state)["legion_count"] == 1


def test_approval_bad_identity_is_fail_closed_without_commit():
    state, ws, war = _state_with_active_war(1)
    war.add_legion_number(99)
    _submit_treaty(ws, war)

    PoliticalSystem(state).execute_passed_peace_treaty(war)

    assert war.peace_treaty["status"] == "submitted"
    assert war.truce_recruit_target == 0
    assert war.legion_numbers == [99]
    assert war.truce_end_turn is None
