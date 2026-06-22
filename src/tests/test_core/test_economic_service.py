from src.core.entities.contract import Contract, ContractStatus, ContractType
from src.core.entities.entities import GameTurn
from src.core.entities.figure import Figure
from src.core.entities.province import Province
from src.core.entities.war import War
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService
from src.core.systems.war_system import WarSystem


def make_state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    return state


def test_settle_indemnities_collects_income_and_clears_due():
    state = make_state()
    state.treasury = 100
    state._war_system = WarSystem(state)
    war = War(id="w1", name="赔款战争")
    war.set_indemnity_due(50)
    state.get_war_system()._active_wars.append(war)

    rows = EconomicService(state).settle_indemnities()

    assert state.treasury == 150
    assert rows[0]["kind"] == "income"
    assert war.indemnity_due == 0


def test_deduct_national_opex_uses_conquered_provinces_only():
    state = make_state()
    state.treasury = 1000
    conquered = Province(1, "Sicilia", total_land=1000, conquered=True)
    unconquered = Province(2, "Africa", total_land=2000, conquered=False)
    state.add_province(conquered)
    state.add_province(unconquered)

    data = EconomicService(state).deduct_national_opex()

    assert data["amount"] == 30
    assert data["total_land"] == 1000
    assert state.treasury == 970


def test_collect_private_land_income_records_faction_tax_float():
    state = make_state()
    figure = Figure(id=101, name="地主", faction_id="senate", age=40)
    figure._land_private = 10
    state.add_member(figure)
    faction_tax_collected = {"senate": 0.0}

    rows = EconomicService(state).collect_private_land_income(faction_tax_collected, 0.1)

    assert rows == [(101, figure.get_formal_name(), 4, figure.wealth)]
    assert faction_tax_collected["senate"] == 0.5


def test_collect_public_works_final_payment_completes_non_fleet_contract():
    state = make_state()
    state.treasury = 1000
    province = Province(1, "Roma", total_land=1000)
    state.add_province(province)
    knight = Figure(id=201, name="骑士甲", faction_id="senate", age=35)
    state.add_member(knight)
    contract = Contract(
        id=301,
        contract_type=ContractType.PUBLIC_WORKS,
        name="道路工程",
        base_cost=800,
        status=ContractStatus.ACTIVE,
        awarded_to=knight.id,
        remaining_years=1,
        total_spent=534,
    )
    contract._province_id = province.province_id
    contract._annual_income = 267
    contract._annual_cost = 200
    state._contracts_dict[contract.id] = contract

    rows = EconomicService(state).collect_contract_revenues({"senate": 0.0}, 0.1)

    assert rows[0]["payment"] == 266
    assert state.treasury == 734
    assert contract.status == ContractStatus.COMPLETED
    assert contract.remaining_years == 0


def test_fleet_contract_payment_marks_paid_without_completing_contract():
    state = make_state()
    state.treasury = 1000
    knight = Figure(id=202, name="造船骑士", faction_id="senate", age=35)
    state.add_member(knight)
    contract = Contract(
        id=302,
        contract_type=ContractType.PUBLIC_WORKS,
        name="舰队建造",
        base_cost=100,
        status=ContractStatus.ACTIVE,
        awarded_to=knight.id,
        remaining_years=1,
    )
    contract.is_fleet_construction = True
    contract._annual_income = 100
    contract._annual_cost = 80
    state._contracts_dict[contract.id] = contract

    EconomicService(state).collect_contract_revenues({"senate": 0.0}, 0.1)

    assert contract.status == ContractStatus.ACTIVE
    assert contract.remaining_years == 0
    assert contract.is_fleet_construction_paid is True


def test_process_contract_warranty_expires_completed_contract():
    state = make_state()
    contract = Contract(
        id=401,
        contract_type=ContractType.PUBLIC_WORKS,
        name="质保工程",
        status=ContractStatus.COMPLETED,
    )
    contract._warranty_remaining = 1
    state._contracts_dict[contract.id] = contract

    rows = EconomicService(state).process_contract_warranty()

    assert rows == [{"contract_id": 401, "name": "质保工程", "before": 1, "after": 0, "expired": True}]
    assert contract.status == ContractStatus.EXPIRED
