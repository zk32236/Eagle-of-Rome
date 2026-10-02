# src/tests/test_api/test_wpl_l1_contract_bidding.py
"""WP-L · L1 — Acceptance Test Set (LC-01..LC-05).

Contract Bidding & Economic Presentation. Authoritative contract source =
`02-sa-design/SA-Development-Task.md` v1.1 §3 (FC-L1-01..FC-L1-14).
Frozen design sha256 = a74489cb… (`baseline-checksums.sha256`).
Regression baseline = 7737db7b2e7f19962616a1bee696e6fff3da25f2.

Production paths only: generate → Senate budget → place_bid → resolve_forum →
Revenue settle; no monkeypatch of function bodies; no hand-mutated state.

- LC-01 Fleet four-authority (A/B/C/D) + settlement conservation (L-AC-01).
- LC-02 Infrastructure unification to Fleet-style (L1-T1 / L-AC-02/07): explicit D,
  A always-set, quality = D/A caliber, 8-tuple enqueue, award freezes C/D.
- LC-03 No-eligible-Knight non-blocking bid (L1-T2 / L-AC-03): row actionable,
  DTO truth, QML not gated on knight availability.
- LC-04 Strength display single source (L1-T3 / L-AC-04): post-build war card only.
- LC-05 Single bid authority + explicit branch, no silent normalization (L1-T4).
"""
import os
import unittest

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.province import Province
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.contract import ContractType, ContractStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem
from src.core.service.economic_service import EconomicService
from src.api import forum_api, senate_api, combat_api

import test_wpgr3_s3_fleet_economics as s3
import test_wpgr3_s4_nominal_effective as s4

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _read_qml(name):
    p = os.path.join(_PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", name)
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


class _ApproveDecider:
    """Real resolve_senate settlement path, zero random (task-local)."""

    def decide_vote(self, issue, faction, state):
        return True


_INFRA_CONFIG = {
    "testing": {"bypass_player_check": True},
    "economic_rules": {
        "land_price_per_unit": 10,
        "private_land_income_rate": 0.05,
        "province_tax_rate": 0.1,
        "tax_auction_ratio": 0.8,
        "infrastructure_cost_rate": 0.001,
        "project_budget_margin": 0.2,
        "tax_contract_duration": 5,
        "works_contract_duration": 3,
        "project_theoretical_construction": 3,
        "project_theoretical_warranty": 10,
        "default_bid_profit_rate": 0.2,
        "senate_budget": {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        },
    },
    "political_rules": {
        "min_ages": {"consul": 30, "censor": 30, "praetor": 30, "quaestor": 30, "tribune": 30},
        "candidates_per_election": {"consul": 2},
        "office_cooldowns": {"consul": 0, "censor": 0, "praetor": 0, "quaestor": 0, "tribune": 0},
    },
    "mortality_rules": {"event_deck": [], "event_draw_count": 0, "death_count": 0},
}


def _build_infra_state(*, with_knight=True, with_tax=False):
    """Deterministic production state: Italy (id 0) with public land → infra contract
    generator; one eligible Eques bidder; one Consul for the Senate budget round."""
    state = GameState.create_for_testing(_INFRA_CONFIG)
    state.turn = GameTurn(turn_number=5, year=-270)
    state._treasury = 5000
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    state.add_faction(Faction(id="f1", name="F1", treasury=1000))
    state.add_player(Player("p1", "f1", PlayerType.HUMAN))
    state.set_turn_order(["p1"])
    state.set_current_player("p1")

    italy = Province(province_id=0, name="Italia", total_land=100000, conquered=False)
    state.add_province(italy)
    if with_tax:
        sicily = Province(province_id=1, name="Sicilia", total_land=5000, conquered=True)
        state.add_province(sicily)

    consul = Figure.create_nobile(state.allocate_id(), "f1", 45)
    consul.office = "consul"
    consul.is_absent = False
    state.add_member(consul)
    state.get_faction("f1").member_ids.append(consul.id)
    state.turn.leader_ids = [consul.id]

    knight = None
    if with_knight:
        knight = Figure.create_eques(state.allocate_id(), "f1", 30)
        knight.wealth = 5000
        state.add_member(knight)
        state.get_faction("f1").member_ids.append(knight.id)

    return state, consul, knight


def _gen_infra(state):
    res = forum_api.generate_contracts(state)
    assert res["success"], res
    infra = [c for c in state.get_all_contracts()
             if c.contract_type == ContractType.PUBLIC_WORKS
             and not getattr(c, "_is_fleet_construction", False)]
    assert len(infra) == 1, [c.name for c in state.get_all_contracts()]
    return infra[0]


def _budget_pass(state, contract, modified_budget):
    prop = senate_api.propose(state, "p1", "budget", contract_id=contract.id,
                              modified_budget=modified_budget)
    assert prop["success"], prop
    resolved = senate_api.resolve_senate(state, vote_decider=_ApproveDecider())
    assert resolved["success"], resolved
    assert contract.status == ContractStatus.BUDGETED


# ---------------------------------------------------------------------------
# LC-01 — Fleet four-authority + settlement conservation (L-AC-01 / FC-L1-05/14)
# ---------------------------------------------------------------------------

class TestLC01FleetFourAuthority(unittest.TestCase):
    def test_fleet_chain_A_B_C_D_gross_and_settlement(self):
        state, ctx = s3._build_fleet_chain_state(enemy_naval=20)
        contract = s3.year1_approved_contract(state, ctx, modified_budget=350)
        self.assertEqual(contract._original_budget, 280)     # A
        self.assertEqual(contract.approved_budget, 350)      # B
        s3._award_block(state, ctx, contract, amount=300, construction_cost=240)
        self.assertEqual(contract.contract_price, 300)       # C
        self.assertEqual(contract._actual_cost, 240)         # D
        self.assertEqual(contract.base_cost, 300)            # projection = C after award
        s3._finish_year_from_population(state, ctx["war"].id,
                                        consul_figure_id=ctx["target"].id)
        rev = s3._mortality_revenue_round(state)
        row = next(r for r in rev["data"]["data"]["contract_rows"]
                   if r["contract_id"] == contract.id)
        self.assertEqual(row["payment"], 300)
        self.assertEqual(row["cost"], 240)
        self.assertEqual(row["payment"] - row["cost"], 60)   # gross = C − D conserved


# ---------------------------------------------------------------------------
# LC-02 — Infrastructure unification (L1-T1 / FC-L1-02/04/05/06/07/14)
# ---------------------------------------------------------------------------

class TestLC02InfraUnification(unittest.TestCase):
    def test_generation_A_always_set(self):
        state, _, _ = _build_infra_state()
        c = _gen_infra(state)
        self.assertEqual(c.status, ContractStatus.PENDING)
        self.assertGreater(c._original_budget, 0)            # FC-L1-06
        self.assertEqual(c._original_budget, c.base_cost)

    def test_senate_budget_writes_B_keeps_A(self):
        state, _, _ = _build_infra_state()
        c = _gen_infra(state)
        A = c._original_budget
        B = int(A * 1.2)
        _budget_pass(state, c, B)
        self.assertEqual(c.approved_budget, B)               # FC-L1-05 B written
        self.assertEqual(c._original_budget, A)              # A frozen
        self.assertEqual(c.base_cost, B)
        self.assertEqual(c.bid_ceiling(), B)                 # ceiling = B

    def test_bid_explicit_D_persisted_as_8tuple(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        A = c._original_budget
        B = int(A * 1.2)
        _budget_pass(state, c, B)
        C, D = B - 40, B - 200
        r = forum_api.place_bid(state, "p1", knight.id, c.id, C, construction_cost=D)
        self.assertTrue(r["success"], r)
        bids = state.get_forum_pending()["contract_bids"]
        self.assertEqual(len(bids), 1)
        self.assertEqual(len(bids[0]), 8)                    # FC-L1-02 8-tuple
        self.assertEqual(bids[0][7], D)                      # index 7 = D
        self.assertEqual(r["data"]["gross_profit"], C - D)   # FC-L1-04 profit=C−D

    def test_bid_rejects_D_greater_than_C(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        B = c.base_cost
        r = forum_api.place_bid(state, "p1", knight.id, c.id, B - 40, construction_cost=B)
        self.assertFalse(r["success"])
        self.assertEqual(len(state.get_forum_pending()["contract_bids"]), 0)

    def test_bid_rejects_negative_D(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        r = forum_api.place_bid(state, "p1", knight.id, c.id, c.base_cost, construction_cost=-5)
        self.assertFalse(r["success"])

    def test_bid_rejects_explicit_D_rate_conflict(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        B = c.base_cost
        C, D = B - 40, B - 200
        # rate that derives a different D than the explicit one → no silent pick
        r = forum_api.place_bid(state, "p1", knight.id, c.id, C,
                                profit_rate=0.9, construction_cost=D)
        self.assertFalse(r["success"])

    def test_award_freezes_C_D_and_quality_ratio(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        A = c._original_budget
        B = int(A * 1.2)
        _budget_pass(state, c, B)
        C, D = B - 40, B - 200
        forum_api.place_bid(state, "p1", knight.id, c.id, C, construction_cost=D)
        res = forum_api.resolve_forum(state)
        self.assertTrue(res["success"], res)
        c = state.get_contract(c.id)
        self.assertEqual(c.status, ContractStatus.ACTIVE)
        self.assertEqual(c.contract_price, C)                # C frozen at award
        self.assertEqual(c._actual_cost, D)                  # D frozen (not recomputed)
        self.assertEqual(c.base_cost, C)                     # projection = C
        self.assertEqual(c._original_budget, A)              # A intact
        # quality caliber = D/A drives infra duration/warranty (retained formulas)
        self.assertEqual(c.construction_years, max(1, int(3 * A / D)))
        self.assertEqual(c.warranty_years, int(10 * D / A))
        # settlement uses D (production settle seam)
        rows = EconomicService(state).collect_contract_revenues({}, 0.1)
        row = next(r for r in rows if r["contract_id"] == c.id)
        self.assertEqual(row["payment"], c.annual_income)
        self.assertEqual(row["cost"], c.annual_cost)


# ---------------------------------------------------------------------------
# LC-03 — No eligible Knight non-blocking (L1-T2 / FC-L1-08/09/10)
# ---------------------------------------------------------------------------

class TestLC03NoKnightNonBlocking(unittest.TestCase):
    def test_dto_row_actionable_with_zero_knights(self):
        state, _, _ = _build_infra_state(with_knight=False)
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        view = forum_api.get_forum_view(state, "p1")
        self.assertTrue(view["success"])
        self.assertTrue(all(not f["can_bid"] for f in view["data"]["my_figures"]))
        row = next(r for r in view["data"]["pending_contracts"] if r["id"] == c.id)
        self.assertTrue(row["can_bid"])                      # row actionable

    def test_backend_truth_rejects_non_knight(self):
        state, consul, _ = _build_infra_state()
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        r = forum_api.place_bid(state, "p1", consul.id, c.id, c.base_cost)
        self.assertFalse(r["success"])                       # FC-L1-08

    def test_qml_bid_button_not_gated_on_knight_availability(self):
        src = _read_qml("ForumStage.qml")
        self.assertNotIn("equesBidOptions().length > 0", src)  # FC-L1-09


# ---------------------------------------------------------------------------
# LC-04 — Strength display single source (L1-T3 / FC-L1-11; G2 ③ withdrawn)
# ---------------------------------------------------------------------------

class TestLC04StrengthSingleSource(unittest.TestCase):
    def test_post_build_war_card_authoritative(self):
        state, ctx, contract, fleets = s4._canonical_mature()
        war = ctx["war"]
        state.set_current_player(s4.P1)
        view = combat_api.get_combat_view(state, s4.P1)
        card = next(w for w in view["data"]["active_wars"] if w["war_id"] == war.id)
        self.assertEqual(card["fleet_nominal_strength"], 21)
        self.assertEqual(card["fleet_quality_adjusted_base"], 18)   # 21 × 6/7
        self.assertEqual(card["fleet_effective_combat_strength"], 18)

    def test_combatstage_binds_readmodel_fields(self):
        src = _read_qml("CombatStage.qml")
        for key in ("fleet_nominal_strength", "fleet_quality_adjusted_base",
                    "fleet_effective_combat_strength"):
            self.assertIn(key, src)

    def test_bid_dialog_strength_projection_withdrawn(self):
        src = _read_qml("ForumStage.qml")
        self.assertNotIn("fleet_effective_combat_strength", src)
        self.assertNotIn("fleet_quality_adjusted_base", src)


# ---------------------------------------------------------------------------
# LC-05 — Single bid authority + explicit branch, no silent normalization (L1-T4)
# ---------------------------------------------------------------------------

class TestLC05SingleAuthorityNoNormalization(unittest.TestCase):
    def test_gui_adapter_same_single_authority(self):
        from src.ui.gui.api_adapter import GuiApiAdapter
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        A = c._original_budget
        B = int(A * 1.2)
        _budget_pass(state, c, B)
        C, D = B - 40, B - 200
        adapter = GuiApiAdapter(state)
        r = adapter.place_bid("p1", knight.id, c.id, C, construction_cost=D)
        self.assertTrue(r["success"], r)
        bids = state.get_forum_pending()["contract_bids"]
        self.assertEqual(len(bids), 1)
        self.assertEqual(bids[0][7], D)                      # one enqueue point, exact D

    def test_family_explicit_branch_tax_vs_infra(self):
        state, _, knight = _build_infra_state(with_tax=True)
        res = forum_api.generate_contracts(state)
        self.assertTrue(res["success"])
        infra = [c for c in state.get_all_contracts()
                 if c.contract_type == ContractType.PUBLIC_WORKS
                 and not getattr(c, "_is_fleet_construction", False)]
        tax = [c for c in state.get_all_contracts()
               if c.contract_type == ContractType.TAX_FARMING]
        self.assertTrue(infra and tax)
        _budget_pass(state, infra[0], int(infra[0]._original_budget * 1.2))
        tax[0].status = ContractStatus.BUDGETED   # fixture: tax branch under test
        B = infra[0].base_cost
        # infra: PUBLIC_WORKS accepts explicit D (8-tuple)
        r1 = forum_api.place_bid(state, "p1", knight.id, infra[0].id, B - 40,
                                 construction_cost=B - 200)
        self.assertTrue(r1["success"], r1)
        # tax: rate path only, 7-tuple, no D field
        r2 = forum_api.place_bid(state, "p1", knight.id, tax[0].id,
                                 tax[0].base_cost, profit_rate=0.2)
        self.assertTrue(r2["success"], r2)
        bids = state.get_forum_pending()["contract_bids"]
        by_contract = {b[0]: b for b in bids}
        self.assertEqual(len(by_contract[infra[0].id]), 8)   # explicit branch
        self.assertEqual(len(by_contract[tax[0].id]), 7)

    def test_no_silent_normalization_of_explicit_D(self):
        state, _, knight = _build_infra_state()
        c = _gen_infra(state)
        _budget_pass(state, c, int(c._original_budget * 1.2))
        C, D = c.base_cost - 40, c.base_cost - 211   # awkward D (not renormalized)
        r = forum_api.place_bid(state, "p1", knight.id, c.id, C, construction_cost=D)
        self.assertTrue(r["success"], r)
        bid = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(bid[7], D)                          # exact, no silent renormalization


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
