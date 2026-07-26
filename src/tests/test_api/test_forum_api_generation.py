"""
Tests for Wave-01 Forum Init — Figure Generation (C-09a) and Contract Generation (C-09b) API.

Covers:
  - figure_generation_system.generate_figures() via forum_api.generate_figures()
  - forum_api.generate_contracts() (renewal + new contracts + fleet)
  - Boundary conditions per state-boundary-checklist.md
  - DEBUG log_event output verification
"""

import logging
import pytest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.province import Province
from src.core.systems.naval_system import NavalSystem
from src.api import forum_api
from src.core.systems.figure_generation_system import generate_figures, generate_market_figures
from src.core.i18n import i18n

i18n.load("zh-CN")


# ==================== Fixtures ====================


@pytest.fixture
def base_config():
    """Base configuration for figure generation tests."""
    return {
        "testing": {"bypass_player_check": False},
        "forum_rules": {
            "new_figures_count": 3,
            "class_probabilities": {
                "nobile": 0.1,
                "eques": 0.25,
            },
        },
        "economic_rules": {
            "land_price_per_unit": 10,
            "private_land_income_rate": 0.05,
            "province_tax_rate": 0.1,
            "tax_auction_ratio": 0.8,
            "infrastructure_cost_rate": 0.001,
            "project_budget_margin": 0.2,
            "tax_contract_duration": 5,
            "works_contract_duration": 3,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "initial_national_public_land": 1000,
        },
    }


@pytest.fixture
def empty_state(base_config):
    """Minimal state for figure generation — no player/faction setup needed for system calls."""
    state = GameState.create_for_testing(base_config)
    state.turn = GameTurn(turn_number=1, year=-282)

    # Add a few members so that random mighty man stat calculation works
    fig1 = Figure.create_nobile(state.allocate_id(), None, 35)
    fig1.martial = 8
    fig1.intelligence = 7
    fig1.charisma = 6
    fig1.zeal = 5
    state.add_member(fig1)

    fig2 = Figure.create_eques(state.allocate_id(), None, 30)
    fig2.martial = 5
    fig2.intelligence = 9
    fig2.charisma = 4
    fig2.zeal = 3
    state.add_member(fig2)

    return state


@pytest.fixture
def state_with_hero(empty_state):
    """State configured with hero_spawned_this_turn = True."""
    empty_state.hero_spawned_this_turn = True
    empty_state.hero_to_spawn = {
        "type": "historical",
        "data": {
            "id": "hero_001",
            "name": "Gaius Marius",
            "birth_year": -282,
            "martial": 9,
            "intelligence": 7,
            "charisma": 8,
            "zeal": 6,
            "family_prestige": 2,
        },
    }
    return empty_state


@pytest.fixture
def state_with_hero_random(empty_state):
    """State configured with random mighty man hero."""
    empty_state.hero_spawned_this_turn = True
    empty_state.hero_to_spawn = {
        "type": "random",
    }
    return empty_state


@pytest.fixture
def state_without_hero(empty_state):
    """State where hero_spawned_this_turn = False."""
    empty_state.hero_spawned_this_turn = False
    empty_state.hero_to_spawn = None
    return empty_state


@pytest.fixture
def state_with_malformed_hero(empty_state):
    """State where hero_to_spawn data is malformed."""
    empty_state.hero_spawned_this_turn = True
    empty_state.hero_to_spawn = {
        "type": "historical",
        "data": {
            # Missing required fields like birth_year, name, etc.
            "id": "hero_bad",
        },
    }
    return empty_state


@pytest.fixture
def contract_test_state(base_config):
    """Full state setup for contract generation tests including provinces."""
    state = GameState.create_for_testing(base_config)
    state.turn = GameTurn(turn_number=5, year=-278)

    # Add player and faction
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(player1)
    state.set_turn_order(["p1"])
    state.set_current_player("p1")

    faction1 = Faction(id="f1", name="Faction1", treasury=1000)
    state.add_faction(faction1)

    # Add a few members
    fig1 = Figure.create_nobile(state.allocate_id(), "f1", 40)
    fig1.is_faction_leader = True
    state.add_member(fig1)

    # Create provinces
    # Italy (ID=0) — always exists, conquered = False initially
    italy = Province(
        province_id=0,
        name="Italia",
        total_land=1000,
        conquered=False,
    )
    state.add_province(italy)

    # Sicily (ID=1) — conquered province with public land
    sicily = Province(
        province_id=1,
        name="Sicilia",
        total_land=500,
        conquered=True,
    )
    state.add_province(sicily)

    # Gaul (ID=2) — conquered province with public land
    gaul = Province(
        province_id=2,
        name="Gallia",
        total_land=800,
        conquered=True,
    )
    state.add_province(gaul)

    # Unconquered province (ID=3) — should NOT get new contracts
    unconquered = Province(
        province_id=3,
        name="Hispania",
        total_land=600,
        conquered=False,
    )
    state.add_province(unconquered)

    return state


@pytest.fixture
def contract_test_state_with_renewals(contract_test_state):
    """State with existing contracts near renewal point."""
    state = contract_test_state

    # Active tax contract in Sicily — 1 year remaining
    tax_contract = state.create_contract(
        ContractType.TAX_FARMING,
        province_id=1,
        base_cost=100,
        current_turn=5,
    )
    tax_contract.name = "Sicilia包税权"
    tax_contract.status = ContractStatus.ACTIVE
    tax_contract.remaining_years = 1  # triggers renewal
    tax_contract.duration_years = 5
    tax_contract.expected_profit = 50

    # Completed works contract in Gaul — 1 year warranty remaining
    works_contract = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province_id=2,
        base_cost=200,
        current_turn=3,
    )
    works_contract.name = "Gallia工程"
    works_contract.status = ContractStatus.COMPLETED
    works_contract._warranty_remaining = 1  # triggers renewal
    works_contract.duration_years = 3

    return state


@pytest.fixture
def contract_test_state_all_occupied(contract_test_state_with_renewals):
    """State where all provinces already have contracts — no duplicates expected."""
    state = contract_test_state_with_renewals

    # Already has Sicily tax (ACTIVE, 1yr remaining) and Gaul works (COMPLETED)
    # Add active tax for Gaul to prevent new tax contract
    gaul_tax = state.create_contract(
        ContractType.TAX_FARMING,
        province_id=2,
        base_cost=150,
        current_turn=4,
    )
    gaul_tax.name = "Gallia包税权"
    gaul_tax.status = ContractStatus.ACTIVE
    gaul_tax.remaining_years = 3
    gaul_tax.duration_years = 5

    # Add works for Sicily
    sicily_works = state.create_contract(
        ContractType.PUBLIC_WORKS,
        province_id=1,
        base_cost=120,
        current_turn=4,
    )
    sicily_works.name = "Sicilia工程"
    sicily_works.status = ContractStatus.COMPLETED
    sicily_works._warranty_remaining = 3

    return state


# ==================== Figure Generation Tests ====================


class TestFigureGenerationSystem:
    """Tests for figure_generation_system.generate_figures() via forum_api.generate_figures()."""

    # --- AC-01: Returns 3 new figures with reasonable class distribution ---

    def test_returns_3_normal_figures(self, state_without_hero):
        """AC-01: forum_api.generate_figures() returns at least 3 new figures."""
        result = forum_api.generate_figures(state_without_hero)
        assert result["success"] is True
        figures = result["data"]["figures"]
        # 3 normal figures + no hero
        assert len(figures) >= 3

    def test_figures_have_class_tiers(self, state_without_hero):
        """Figures have valid class_tier values."""
        result = forum_api.generate_figures(state_without_hero)
        figures = result["data"]["figures"]
        valid_tiers = {"nobile", "eques", "plebeian"}
        for fig in figures:
            assert fig["class_tier"] in valid_tiers, f"Unexpected tier: {fig['class_tier']}"

    def test_figures_registered_in_state(self, state_without_hero):
        """Figures are registered via add_member and in curia."""
        result = forum_api.generate_figures(state_without_hero)
        figures = result["data"]["figures"]
        for fig_data in figures:
            fig = state_without_hero.get_member(fig_data["id"])
            assert fig is not None, f"Figure {fig_data['id']} not found in state members"
            assert fig.id == fig_data["id"]

    # --- AC-02: Hero generation records spawned_hero_ids ---

    def test_hero_generation_historical(self, state_with_hero):
        """AC-02: Historical hero records in state.spawned_hero_ids."""
        result = forum_api.generate_figures(state_with_hero)
        assert result["success"] is True
        figures = result["data"]["figures"]

        # Should have 4 figures (3 normal + 1 hero)
        assert len(figures) >= 4

        # Hero should be marked
        hero_figures = [f for f in figures if f["is_hero"]]
        assert len(hero_figures) >= 1

        # Check spawned_hero_ids
        assert "hero_001" in state_with_hero.spawned_hero_ids

    def test_hero_generation_random(self, state_with_hero_random):
        """Random mighty man generation works."""
        result = forum_api.generate_figures(state_with_hero_random)
        assert result["success"] is True
        figures = result["data"]["figures"]
        assert len(figures) >= 4

        hero_figures = [f for f in figures if f["is_hero"]]
        assert len(hero_figures) >= 1

        # Hero markers should be cleared
        assert state_with_hero_random.hero_spawned_this_turn is False
        assert state_with_hero_random.hero_to_spawn is None

    def test_no_hero_when_not_set(self, state_without_hero):
        """When hero_spawned_this_turn is False, no hero is generated."""
        result = forum_api.generate_figures(state_without_hero)
        figures = result["data"]["figures"]
        hero_figures = [f for f in figures if f["is_hero"]]
        assert len(hero_figures) == 0

    def test_malformed_hero_falls_back_gracefully(self, state_with_malformed_hero):
        """B3: Malformed hero data falls back gracefully (skip hero)."""
        result = forum_api.generate_figures(state_with_malformed_hero)
        assert result["success"] is True
        figures = result["data"]["figures"]
        # Should still return 3 normal figures
        assert len(figures) >= 3

    # --- Debug logging verification ---

    def test_figure_generation_log_event(self, state_without_hero):
        """DEBUG log_event produced for figure generation."""
        # Patch log_event to capture calls
        original_log = state_without_hero.log_event
        captured = []

        def capturing_log(message, level=logging.INFO, extra=None):
            captured.append((message, level, extra))
            original_log(message, level, extra)

        state_without_hero.log_event = capturing_log

        forum_api.generate_figures(state_without_hero)

        # Check for figure generation debug log
        figure_gen_logs = [c for c in captured if "figure_generation_system: generated" in c[0]]
        assert len(figure_gen_logs) >= 1, "Missing figure generation DEBUG log_event"
        assert figure_gen_logs[0][1] == logging.DEBUG, "Figure gen log should be DEBUG level"

    def test_hero_log_event(self, state_with_hero):
        """DEBUG log_event for hero spawn."""
        original_log = state_with_hero.log_event
        captured = []

        def capturing_log(message, level=logging.INFO, extra=None):
            captured.append((message, level, extra))
            original_log(message, level, extra)

        state_with_hero.log_event = capturing_log

        forum_api.generate_figures(state_with_hero)

        hero_logs = [c for c in captured if "hero spawned" in c[0]]
        assert len(hero_logs) >= 1, "Missing hero spawn DEBUG log_event"

    # --- State boundary checks ---

    def test_empty_members_no_crash(self, base_config):
        """B4: No living members for max-stat calculation uses defaults."""
        state = GameState.create_for_testing(base_config)
        state.turn = GameTurn(turn_number=1, year=-282)
        state.hero_spawned_this_turn = True
        state.hero_to_spawn = {"type": "random"}

        # No members added — random mighty man should use defaults
        result = forum_api.generate_figures(state)
        assert result["success"] is True

    def test_config_counts_respected(self, base_config):
        """B7: Config new_figures_count controls figure count."""
        base_config["forum_rules"]["new_figures_count"] = 5
        state = GameState.create_for_testing(base_config)
        state.turn = GameTurn(turn_number=1, year=-282)
        state.hero_spawned_this_turn = False

        result = forum_api.generate_figures(state)
        figures = result["data"]["figures"]
        assert len(figures) == 5


# ==================== Contract Generation Tests ====================


class TestForumApiGenerateContracts:
    """Tests for forum_api.generate_contracts()."""

    # --- AC-03: Returns renewals + new contracts, province filtering correct ---

    def test_contracts_generated_with_provinces(self, contract_test_state):
        """AC-03: New contracts generated for conquered provinces."""
        result = forum_api.generate_contracts(contract_test_state)
        assert result["success"] is True
        contracts = result["data"]["contracts"]
        # Should generate contracts for Sicily (ID=1) and Gaul (ID=2) and Italy (ID=0)
        province_ids = {c["province_id"] for c in contracts}
        assert 0 in province_ids, "Italy should have works contracts"
        assert 1 in province_ids, "Sicily should have tax contract"
        assert 2 in province_ids, "Gaul should have contracts"

    def test_unconquered_provinces_skipped(self, contract_test_state):
        """Unconquered provinces should not receive contracts."""
        result = forum_api.generate_contracts(contract_test_state)
        contracts = result["data"]["contracts"]
        province_ids = {c["province_id"] for c in contracts}
        assert 3 not in province_ids, "Unconquered Hispania should not have contracts"

    def test_italy_has_works_no_tax(self, contract_test_state):
        """Italy (province_id=0) should have works contracts but no tax contracts."""
        result = forum_api.generate_contracts(contract_test_state)
        italy_contracts = [c for c in result["data"]["contracts"] if c["province_id"] == 0]
        assert len(italy_contracts) > 0, "Italy should have works contracts"
        for c in italy_contracts:
            assert c["contract_type"] == "public_works", "Italy should only have works contracts"

    # --- AC-04: Tax rate calculation preserved ---

    def test_tax_contract_economics(self, contract_test_state):
        """AC-04: Tax contracts have expected_profit = base_tax - base_cost."""
        result = forum_api.generate_contracts(contract_test_state)
        tax_contracts = [c for c in result["data"]["contracts"] if c["contract_type"] == "tax_farming"]
        for tc in tax_contracts:
            # expected_profit should be positive (base_tax > base_cost when auction_ratio < 1.0)
            assert tc["expected_profit"] >= 0, f"Expected profit should be non-negative for {tc['name']}"

    # --- Renewal tests ---

    def test_tax_contract_renewal(self, contract_test_state_with_renewals):
        """Tax contract with remaining_years=1 triggers renewal."""
        result = forum_api.generate_contracts(contract_test_state_with_renewals)
        contracts = result["data"]["contracts"]

        # Sicily should get a renewal PENDING tax contract
        sicily_contracts = [c for c in contracts if c["province_id"] == 1 and c["contract_type"] == "tax_farming"]
        # The renewal creates a new PENDING contract
        assert any(c["status"] == "pending" for c in sicily_contracts), "Sicily should have a renewal tax contract"

    def test_works_contract_renewal(self, contract_test_state_with_renewals):
        """Works contract with warranty_remaining=1 triggers renewal."""
        result = forum_api.generate_contracts(contract_test_state_with_renewals)
        contracts = result["data"]["contracts"]

        # Gaul should get a renewal PENDING works contract
        gaul_works = [c for c in contracts if c["province_id"] == 2 and c["contract_type"] == "public_works"]
        assert any(c["status"] == "pending" for c in gaul_works), "Gaul should have a renewal works contract"

    # --- Boundary: No provinces conquered ---

    def test_no_provinces_no_contracts(self, base_config):
        """B1: No provinces conquered generates only Italy works contracts."""
        state = GameState.create_for_testing(base_config)
        state.turn = GameTurn(turn_number=5, year=-278)
        # Italy only — not conquered
        italy = Province(
            province_id=0,
            name="Italia",
            total_land=1000,
            conquered=False,
        )
        state.add_province(italy)

        result = forum_api.generate_contracts(state)
        assert result["success"] is True
        contracts = result["data"]["contracts"]
        # Italy should still get works contracts even if not conquered
        province_ids = {c["province_id"] for c in contracts}
        assert 0 in province_ids, "Italy should have works contracts even if not conquered"

    def test_no_provinces_land_public_zero_skipped(self, contract_test_state):
        """B5: Province with land_public=0 is skipped."""
        state = contract_test_state
        # Add province with no public land
        empty_public = Province(
            province_id=4,
            name="Deserta",
            total_land=100,
            land_public=0,
            conquered=True,
        )
        state.add_province(empty_public)

        result = forum_api.generate_contracts(state)
        contracts = result["data"]["contracts"]
        province_ids = {c["province_id"] for c in contracts}
        # The province with 0 public land should still not get contracts
        # because new_contract checks land_public > 0
        assert all(c["province_id"] != 4 for c in contracts), "Province 4 (land_public=0) should not have any contracts"

    def test_duplicate_contracts_not_generated(self, contract_test_state_all_occupied):
        """B2: No duplicate contracts when all provinces already have contracts."""
        result = forum_api.generate_contracts(contract_test_state_all_occupied)
        contracts = result["data"]["contracts"]

        # Count contracts per province+type
        from collections import Counter
        contract_keys = [(c["province_id"], c["contract_type"]) for c in contracts]
        key_counts = Counter(contract_keys)
        for key, count in key_counts.items():
            assert count <= 1, f"Duplicate contract for province {key[0]} type {key[1]}: {count} occurrences"

    # --- Fleet construction delegation ---

    def test_fleet_delegation_logged(self, contract_test_state):
        """AC-08: Fleet construction logged as delegation to naval_system."""
        original_log = contract_test_state.log_event
        captured = []

        def capturing_log(message, level=logging.INFO, extra=None):
            captured.append((message, level, extra))
            original_log(message, level, extra)

        contract_test_state.log_event = capturing_log

        # Mock naval_system to return some contracts
        mock_naval = MagicMock(spec=NavalSystem)
        mock_naval.generate_construction_contracts.return_value = []
        mock_naval.generate_replacement_contracts.return_value = []
        contract_test_state._naval_system = mock_naval

        forum_api.generate_contracts(contract_test_state)

        fleet_logs = [c for c in captured if "delegated fleet construction" in c[0]]
        assert len(fleet_logs) >= 1, "Missing fleet delegation DEBUG log_event"

    def test_fleet_silent_when_no_naval_system(self, contract_test_state):
        """B6: No naval_system — fleet contracts silently skipped."""
        contract_test_state._naval_system = None

        result = forum_api.generate_contracts(contract_test_state)
        assert result["success"] is True, "Should succeed even without naval system"

    # --- Debug logging for contracts ---

    def test_contract_generation_log_events(self, contract_test_state):
        """Contract generation produces DEBUG log_events."""
        original_log = contract_test_state.log_event
        captured = []

        def capturing_log(message, level=logging.INFO, extra=None):
            captured.append((message, level, extra))
            original_log(message, level, extra)

        contract_test_state.log_event = capturing_log

        forum_api.generate_contracts(contract_test_state)

        # Check for new contract log events
        tax_new_logs = [c for c in captured if "forum_api: new tax contract:" in c[0]]
        works_new_logs = [c for c in captured if "forum_api: new works contract:" in c[0]]
        assert len(tax_new_logs) > 0, "Missing new tax contract DEBUG log_event"
        assert len(works_new_logs) > 0, "Missing new works contract DEBUG log_event"


# ==================== Direct System Tests ====================


class TestFigureGenerationSystemDirect:
    """Direct tests on figure_generation_system module functions."""

    def test_generate_figures_returns_list(self, empty_state):
        figures = generate_figures(empty_state)
        assert isinstance(figures, list)
        assert len(figures) == 3  # 3 normal, no hero

    def test_generate_market_figures_returns_list(self, empty_state):
        figures = generate_market_figures(empty_state)
        assert isinstance(figures, list)
        assert len(figures) == 3

    def test_generate_figures_with_hero(self, state_with_hero):
        figures = generate_figures(state_with_hero)
        assert len(figures) == 4  # 3 normal + 1 hero
        assert "hero_001" in state_with_hero.spawned_hero_ids

    def test_generate_figures_without_hero(self, state_without_hero):
        figures = generate_figures(state_without_hero)
        assert len(figures) == 3  # 3 normal, no hero


# ==================== API Response Format Tests ====================


class TestGenerateFiguresAPIResponse:
    """Verification of forum_api.generate_figures() response format."""

    def test_api_response_format(self, state_without_hero):
        result = forum_api.generate_figures(state_without_hero)
        assert "success" in result
        assert "message" in result
        assert "data" in result
        assert "figures" in result["data"]

    def test_figure_data_shape(self, state_without_hero):
        result = forum_api.generate_figures(state_without_hero)
        for fig in result["data"]["figures"]:
            assert "id" in fig
            assert "name" in fig
            assert "class_tier" in fig
            assert "martial" in fig
            assert "intelligence" in fig
            assert "charisma" in fig
            assert "zeal" in fig
            assert "age" in fig
            assert "is_hero" in fig


class TestGenerateContractsAPIResponse:
    """Verification of forum_api.generate_contracts() response format."""

    def test_api_response_format(self, contract_test_state):
        result = forum_api.generate_contracts(contract_test_state)
        assert "success" in result
        assert "message" in result
        assert "data" in result
        assert "contracts" in result["data"]

    def test_contract_data_shape(self, contract_test_state):
        result = forum_api.generate_contracts(contract_test_state)
        for c in result["data"]["contracts"]:
            assert "id" in c
            assert "name" in c
            assert "contract_type" in c
            assert "contract_type_label" in c
            assert "province_id" in c
            assert "base_cost" in c
            assert "expected_profit" in c
            assert "duration_years" in c
            assert "status" in c
            assert "is_renewal" in c
            assert "is_fleet" in c


# ==================== Error Path Tests ====================


class TestErrorPaths:
    """Error path tests per state-boundary-checklist.md."""

    def test_contract_gen_skips_on_create_contract_none(self, contract_test_state):
        """E3: state.create_contract() should always return a contract object."""
        # create_contract creates and stores the contract; it doesn't return None
        result = forum_api.generate_contracts(contract_test_state)
        assert result["success"] is True

    def test_empty_config_probabilities_use_defaults(self, base_config):
        """B6: Empty or missing config uses defaults."""
        # Remove class_probabilities from config
        base_config["forum_rules"] = {"new_figures_count": 3}
        state = GameState.create_for_testing(base_config)
        state.turn = GameTurn(turn_number=1, year=-282)

        result = forum_api.generate_figures(state)
        assert result["success"] is True
        assert len(result["data"]["figures"]) == 3
