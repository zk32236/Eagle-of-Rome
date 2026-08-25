"""WP-E-R3 canonical Revenue accounting-window tests."""

import copy

from src.core.entities.entities import GameTurn
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService
from src.core.systems.military_system import MilitarySystem
from src.tests.test_core.test_revenue_settlement_dto import _make_full_revenue_state


def test_canonical_ledger_strictly_reconciles_all_treasury_sources():
    state = _make_full_revenue_state()
    data = EconomicService(state).settle_revenue_phase()["data"]
    window = data["accounting_window"]
    rows = window["treasury_ledger_rows"]

    assert window["basis"] == "republic_treasury_cash"
    assert window["reconciled"] is True
    assert sum(row["signed_amount"] for row in rows) == data["treasury_delta"]
    assert window["starting_treasury"] + window["displayed_net_total"] == window["ending_treasury"]
    assert window["displayed_income_total"] - window["displayed_expense_total"] == window["displayed_net_total"]
    assert any(row["key"] == "public_works_payment" for row in rows)
    assert any(row["key"] == "faction_stipend" for row in rows)
    assert all("residual" not in row["key"] and "平账" not in row["label"] for row in rows)


def test_reconciliation_mismatch_is_exposed_without_residual_row():
    state = _make_full_revenue_state()
    service = EconomicService(state)
    data = service.settle_revenue_phase()["data"]
    mismatched = copy.deepcopy(data)
    mismatched["treasury_delta"] += 1

    window = service.build_accounting_window(mismatched)

    assert window["reconciled"] is False
    assert window["displayed_net_total"] == data["treasury_delta"]
    assert window["displayed_net_total"] != mismatched["treasury_delta"]
    assert all(row["key"] != "residual" for row in window["treasury_ledger_rows"])


def test_military_maintenance_records_actual_paid_not_planned_total():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    state.treasury = 1
    state._military_system = MilitarySystem(state)
    assert state._military_system.recruit_legion(1)[0] is False  # insufficient recruit cost

    # Recruit with funds, then make the maintenance window insolvent.
    state.treasury = 100
    assert state._military_system.recruit_legion(1)[0] is True
    state.treasury = 1
    row = EconomicService(state).apply_military_maintenance()

    assert row["total"] > 0
    assert row["paid"] == 0
    assert state.treasury == 1


def test_insufficient_indemnity_warning_never_enters_cash_ledger():
    service = EconomicService(GameState.create_for_testing({}))
    data = {
        "starting_treasury": 5,
        "ending_treasury": 5,
        "treasury_delta": 0,
        "indemnities": [{"war_id": "w", "name": "Unpaid", "amount": -10, "kind": "insufficient"}],
        "national_opex": {},
        "public_land_income": {},
        "contract_rows": [],
        "maintenance": {"military": {}, "naval": {}},
        "faction_rows": {},
    }

    window = service.build_accounting_window(data)

    assert window["treasury_ledger_rows"] == []
    assert window["reconciled"] is True
