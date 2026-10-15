# src/tests/test_core/test_scenario_validation.py
"""
S-A (EOR20261013-02): fail-closed scenario selection/validation tests.

GR-F10 (parameterized scenario selection) / GR-F11 (fail-closed validation).
Valid + invalid paths. Content checks run against detached dicts; file/path checks
run against the approved data/scenarios directory.
"""
import copy

import pytest

from src.core import scenario_validation as sv


VALID_CORE = {
    "scenario_name": "unit",
    "start_year": -282,
    "initial_state": {
        "treasury": 100,
        "random_seed": 42,
        "factions": [
            {"id": "optimates", "name": "Optimates", "is_player": True},
            {"id": "populares", "name": "Populares", "is_player": False},
            {"id": "equites", "name": "Equites", "is_player": False},
        ],
        "figure_generation": {
            "per_faction": {
                "nobile": {"count": 3, "age_range": [35, 50]},
                "eques": {"count": 2, "age_range": [25, 40]},
                "plebeian": {"count": 1, "age_range": [25, 35]},
            }
        },
    },
}


def _mutate(fn):
    data = copy.deepcopy(VALID_CORE)
    fn(data)
    return data


class TestValidScenarioData:
    def test_valid_core_reports_bijection_and_effective_treasury(self):
        report = sv.validate_scenario_data(copy.deepcopy(VALID_CORE))
        assert report["faction_count"] == 3
        assert report["human_count"] == 1
        assert report["ai_count"] == 2
        # per-faction treasury is IGNORED at HEAD; effective value is reported only.
        assert report["effective_faction_treasury"] == 10
        assert report["player_ids"] == [
            "player_equites", "player_optimates", "player_populares"]

    def test_report_exposes_min_human_requirement(self):
        report = sv.validate_scenario_data(copy.deepcopy(VALID_CORE))
        assert report["min_humans"] == 1
        assert report["human_required"] is True

    def test_declared_per_faction_treasury_reported_ignored(self):
        data = _mutate(lambda d: d["initial_state"]["factions"][0].update({"treasury": 999}))
        report = sv.validate_scenario_data(data)
        row = report["factions"][0]
        assert row["declared_treasury_ignored"] == 999
        assert row["effective_treasury"] == 10

    def test_1h_from_default_scenario_is_legal(self):
        report = sv.preflight_scenario(sv.DEFAULT_SCENARIO_FILE)
        assert report["faction_count"] == 3
        assert report["human_count"] == 1 and report["ai_count"] == 2


class TestShippedFixtures:
    @pytest.mark.parametrize("name", ["gr_f_3h.json", "gr_f_3h3ai.json", "gr_f_6h.json"])
    def test_fixtures_preflight_ok(self, name):
        report = sv.preflight_scenario(name)
        assert report["scenario_file"] == name
        assert sv.MIN_FACTIONS <= report["faction_count"] <= sv.MAX_FACTIONS
        assert report["human_count"] + report["ai_count"] == report["faction_count"]
        assert len(report["sha256"]) == 64
        assert report["controller_bijection"] is True

    def test_3h_composition(self):
        r = sv.preflight_scenario("gr_f_3h.json")
        assert (r["faction_count"], r["human_count"], r["ai_count"]) == (3, 3, 0)

    def test_3h3ai_composition(self):
        r = sv.preflight_scenario("gr_f_3h3ai.json")
        assert (r["faction_count"], r["human_count"], r["ai_count"]) == (6, 3, 3)

    def test_6h_composition(self):
        r = sv.preflight_scenario("gr_f_6h.json")
        assert (r["faction_count"], r["human_count"], r["ai_count"]) == (6, 6, 0)


class TestInvalidScenarioData:
    def test_zero_factions(self):
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(
                _mutate(lambda d: d["initial_state"].update({"factions": []})))

    def test_seven_factions(self):
        def add(d):
            d["initial_state"]["factions"] = [
                {"id": f"x{i}", "name": f"X{i}", "is_player": False} for i in range(7)]
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(add))

    def test_duplicate_faction_id(self):
        def dup(d):
            d["initial_state"]["factions"][1]["id"] = "optimates"
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(dup))

    def test_missing_is_player(self):
        def drop(d):
            del d["initial_state"]["factions"][0]["is_player"]
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(drop))

    def test_truthy_string_is_player_rejected(self):
        def bad(d):
            d["initial_state"]["factions"][0]["is_player"] = "true"
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_empty_faction_id(self):
        def bad(d):
            d["initial_state"]["factions"][0]["id"] = ""
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_unsupported_explicit_players(self):
        def bad(d):
            d["initial_state"]["players"] = [{"player_id": "p"}]
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_negative_faction_treasury(self):
        def bad(d):
            d["initial_state"]["factions"][0]["treasury"] = -5
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_bad_age_range(self):
        def bad(d):
            d["initial_state"]["figure_generation"]["per_faction"]["nobile"]["age_range"] = [50, 35]
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_bad_figure_count(self):
        def bad(d):
            d["initial_state"]["figure_generation"]["per_faction"]["nobile"]["count"] = -1
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(bad))

    def test_non_object_root(self):
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(["not", "a", "dict"])

    def test_missing_initial_state(self):
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data({"scenario_name": "x"})

    def test_zero_human_all_ai_rejected(self):
        # 0-HUMAN (all-AI) is rejected fail-closed; spec MVP0.7-12 §2.2 requires
        # at least one HUMAN seat driving the turn order.
        def all_ai(d):
            for fac in d["initial_state"]["factions"]:
                fac["is_player"] = False
        with pytest.raises(sv.ScenarioValidationError):
            sv.validate_scenario_data(_mutate(all_ai))


class TestPathSelectionFailClosed:
    @pytest.mark.parametrize("bad", [
        "does_not_exist.json",
        "..",
        "../gui_prototype.json",
        "sub/gui_prototype.json",
        "gui_prototype.txt",
        "",
        "/etc/hostname",
    ])
    def test_illegal_selection_rejected(self, bad):
        with pytest.raises(sv.ScenarioValidationError):
            sv.preflight_scenario(bad)
