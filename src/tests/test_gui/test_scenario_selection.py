# src/tests/test_gui/test_scenario_selection.py
"""
S-A (EOR20261013-02): production scenario-selection chain tests.

These exercise the real production factory (create_gui_prototype_session ->
validated loader), not a test-only ``new GameState``.
GR-F10 (parameterized selection) / GR-F11 (fail-closed, no half-open session).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api
import gui_main


class TestScenarioSelectionChain:
    def test_default_selection_preserves_historical_1h2ai(self):
        result = session_api.create_gui_prototype_session()
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        players = state.get_all_players()
        human = [p for p in players if p.player_type.value == "human"]
        ai = [p for p in players if p.player_type.value != "human"]
        assert len(human) == 1 and len(ai) == 2
        assert result["data"]["scenario"]["scenario_file"] == "gui_prototype.json"

    def test_select_3h(self):
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        assert len(result["data"]["human_players"]) == 3
        assert len(state.get_all_players()) == 3
        assert state.get_current_player().player_type.value == "human"

    def test_select_3h3ai(self):
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h3ai.json")
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        assert len(state.get_all_players()) == 6
        assert len(result["data"]["human_players"]) == 3
        assert result["data"]["scenario"]["ai_count"] == 3

    def test_select_6h(self):
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_6h.json")
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        assert len(result["data"]["human_players"]) == 6
        assert len(state.get_all_players()) == 6

    def test_invalid_missing_scenario_no_half_open(self):
        result = session_api.create_gui_prototype_session(scenario_file="nope_missing.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    def test_traversal_rejected_no_half_open(self):
        result = session_api.create_gui_prototype_session(
            scenario_file="../data/config/game_config.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    # --- R01: explicit empty selection (separate surface) must fail closed ---
    def test_factory_rejects_explicit_empty_scenario(self):
        result = session_api.create_gui_prototype_session(scenario_file="")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    # --- R02: non-canonical (whitespace-wrapped) selection must not publish ---
    def test_whitespace_wrapped_selection_not_silently_substituted(self):
        result = session_api.create_gui_prototype_session(scenario_file=" gr_f_3h.json ")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    # --- R02-r4: the GUI route consumes the validated snapshot via the bounded new
    # entry. The historical filename entry is now FORBIDDEN on GUI requests, so the
    # former "force the historical loader to fail" injection is replaced by a strict
    # SHARED-APPLICATION failure (conserving the fail-closed / no-fallback outcome). ---
    def test_application_failure_after_valid_capture_fails_closed(self, monkeypatch):
        from src.core.scenario_loader import ScenarioLoader

        def boom_apply(state, config):
            raise RuntimeError("simulated shared config-application failure")

        monkeypatch.setattr(ScenarioLoader, "_apply_scenario_config", staticmethod(boom_apply))
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    def test_gui_route_never_touches_historical_fallback_entry(self, monkeypatch):
        # Conserved no-fallback negative: with the historical filename entry and its
        # built-in default instrumented as forbidden raising sentinels, a GUI request
        # still succeeds WITHOUT ever reaching either (the snapshot route has no edge).
        from src.core.scenario_loader import ScenarioLoader

        counters = {"load": 0, "default": 0}

        def forbidden_load(*a, **k):
            counters["load"] += 1
            raise AssertionError("forbidden edge: load_scenario on the GUI route")

        def forbidden_default(*a, **k):
            counters["default"] += 1
            raise AssertionError("forbidden edge: _get_default_config on the GUI route")

        monkeypatch.setattr(ScenarioLoader, "load_scenario", staticmethod(forbidden_load))
        monkeypatch.setattr(ScenarioLoader, "_get_default_config", staticmethod(forbidden_default))
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        assert result["success"], result.get("message")
        assert counters == {"load": 0, "default": 0}

    # --- R02-r2a conserved: a SELECTED canonical file is served by the CAPTURED
    # snapshot, never by the loader's built-in fallback (which differs only in
    # year/treasury). With the forbidden edges instrumented, the published session must
    # carry the SELECTED values (-282 / 142), proving no built-in fallback was used. ---
    def test_selected_canonical_uses_captured_content_not_builtin_fallback(self, monkeypatch):
        from src.core.scenario_loader import ScenarioLoader

        counters = {"load": 0, "default": 0}

        def forbidden_load(*a, **k):
            counters["load"] += 1
            raise AssertionError("forbidden edge: load_scenario on the GUI route")

        def forbidden_default(*a, **k):
            counters["default"] += 1
            raise AssertionError("forbidden edge: _get_default_config on the GUI route")

        monkeypatch.setattr(ScenarioLoader, "load_scenario", staticmethod(forbidden_load))
        monkeypatch.setattr(ScenarioLoader, "_get_default_config", staticmethod(forbidden_default))
        result = session_api.create_gui_prototype_session(scenario_file="gui_prototype.json")
        assert result["success"], result.get("message")
        state = result["data"]["state"]
        # selected gui_prototype.json: year -282 / national treasury 142;
        # a built-in fallback would have published -264 / 100.
        assert state.turn.year == -282
        assert state.treasury == 142
        assert counters == {"load": 0, "default": 0}

    # --- R02-r2b: the ACTUAL player->faction ownership edge must be verified ---
    def test_ownership_swap_keeping_ids_and_types_fails_closed(self, monkeypatch):
        # Swap two players' faction ownership while keeping every player id AND every
        # controller type intact. On gr_f_3h.json all three seats are HUMAN, so a
        # player_type-only check cannot see the corruption; the ownership-edge guard
        # must fail the session closed (no half-open session). Injected at the bounded
        # snapshot entry (the GUI route no longer calls the historical loader).
        from src.core.scenario_loader import ScenarioLoader

        real_init = ScenarioLoader.initialize_validated_scenario

        def swapped(state, snapshot):
            real_init(state, snapshot)
            a = state.get_player("player_optimates")
            b = state.get_player("player_populares")
            a._faction_id, b._faction_id = b._faction_id, a._faction_id

        monkeypatch.setattr(
            ScenarioLoader, "initialize_validated_scenario", staticmethod(swapped))
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])

    # --- NEW PM rule: 0-HUMAN (all-AI) rejected fail-closed at the factory ---
    def test_factory_rejects_zero_human_scenario(self, monkeypatch, tmp_path):
        import json as _json
        from src.core import scenario_validation as sv

        zero_human = {
            "scenario_name": "all-ai unit",
            "start_year": -282,
            "initial_state": {
                "treasury": 100,
                "factions": [
                    {"id": "optimates", "name": "Optimates", "is_player": False},
                    {"id": "populares", "name": "Populares", "is_player": False},
                    {"id": "equites", "name": "Equites", "is_player": False},
                ],
            },
        }
        (tmp_path / "gr_f_0h.json").write_text(_json.dumps(zero_human), encoding="utf-8")
        monkeypatch.setattr(sv, "scenarios_dir", lambda: tmp_path)
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_0h.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])


class TestSelectedSourceProvenance:
    """S-A R02-r4 structural provenance witnesses (real production factory).

    Only acquisition / initializer seams are instrumented; the factory itself and the
    shared config->state body are the real production code.
    """

    EQUAL_VALUE_SCENARIO = {
        "scenario_name": "equal-value counterexample",
        # Matches the built-in default's faction ids / HUMAN-AI flags / year -264 /
        # national treasury 100, but ONE noble per faction (fallback has three).
        "start_year": -264,
        "initial_state": {
            "treasury": 100,
            "factions": [
                {"id": "optimates", "name": "Optimates", "is_player": True},
                {"id": "populares", "name": "Populares", "is_player": False},
                {"id": "equites", "name": "Equites", "is_player": False},
            ],
            "figure_generation": {
                "per_faction": {
                    "nobile": {"count": 1, "age_range": [35, 50]},
                    "eques": {"count": 2, "age_range": [25, 40]},
                    "plebeian": {"count": 1, "age_range": [25, 35]},
                }
            },
        },
    }

    @staticmethod
    def _forbid_legacy_edges(monkeypatch):
        from src.core.scenario_loader import ScenarioLoader

        counters = {"load_scenario": 0, "_get_default_config": 0}

        def forbidden_load(*a, **k):
            counters["load_scenario"] += 1
            raise AssertionError("forbidden edge: load_scenario reached from the GUI route")

        def forbidden_default(*a, **k):
            counters["_get_default_config"] += 1
            raise AssertionError(
                "forbidden edge: _get_default_config reached from the GUI route")

        monkeypatch.setattr(ScenarioLoader, "load_scenario", staticmethod(forbidden_load))
        monkeypatch.setattr(
            ScenarioLoader, "_get_default_config", staticmethod(forbidden_default))
        return counters

    @staticmethod
    def _nobles_per_faction(state):
        from src.core.entities.figure import ClassTier

        counts = {}
        for member in state.get_living_members():
            if member.class_tier == ClassTier.NOBILE:
                counts[member.faction_id] = counts.get(member.faction_id, 0) + 1
        return counts

    def _install_equal_value(self, monkeypatch, tmp_path):
        import json as _json
        from src.core import scenario_validation as sv

        (tmp_path / "equal_value.json").write_text(
            _json.dumps(self.EQUAL_VALUE_SCENARIO), encoding="utf-8")
        monkeypatch.setattr(sv, "scenarios_dir", lambda: tmp_path)

    # ---- Witness 1: equal-value counterexample + forbidden edges ----
    def test_equal_value_counterexample_initializes_captured_content_forbidden_edges_zero(
            self, monkeypatch, tmp_path):
        counters = self._forbid_legacy_edges(monkeypatch)
        self._install_equal_value(monkeypatch, tmp_path)

        result = session_api.create_gui_prototype_session(scenario_file="equal_value.json")
        assert result["success"], result.get("message")
        state = result["data"]["state"]

        # The captured content is consumed: ONE noble per faction. A built-in fallback
        # would have published THREE nobles per faction while matching ids/flags/year
        # (and national treasury 100) -- i.e. every value-heuristic predicate.
        assert self._nobles_per_faction(state) == {
            "optimates": 1, "populares": 1, "equites": 1}

        # Both historical edges are unreachable from the GUI route.
        assert counters == {"load_scenario": 0, "_get_default_config": 0}

    # ---- Witness 2: value-independent fail-closed negative ----
    def test_value_independent_fail_closed_negative(self, monkeypatch, tmp_path):
        from src.core.scenario_loader import ScenarioLoader

        counters = self._forbid_legacy_edges(monkeypatch)
        self._install_equal_value(monkeypatch, tmp_path)

        # Cause the ACTUAL shared config-application seam (a real internal step of the
        # shared body) to raise AFTER capture. This is a genuine application failure,
        # not a fake that manufactures a valid-looking fallback state.
        def boom_load_figures(state, config):
            raise RuntimeError("simulated shared application/resource failure")

        monkeypatch.setattr(ScenarioLoader, "_load_figures", staticmethod(boom_load_figures))

        result = session_api.create_gui_prototype_session(scenario_file="equal_value.json")
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])
        assert counters == {"load_scenario": 0, "_get_default_config": 0}

    # ---- Witness 3: no second read / snapshot integrity ----
    def test_no_second_read_and_snapshot_integrity(self, monkeypatch):
        import hashlib
        from pathlib import Path as _Path
        from src.core import scenario_validation as sv

        real_prepare = sv.prepare_selected_scenario
        captured = {}
        reads = {"count": 0}

        def prepare_then_seal(scenario_file, **kwargs):
            snap = real_prepare(scenario_file, **kwargs)
            captured["bytes"] = snap.raw_bytes
            captured["sha"] = snap.sha256

            # Seal the scenario read seam AFTER capture: any later reread now fails.
            def deny_read_bytes(self):
                reads["count"] += 1
                raise OSError("scenario file reread attempted after capture")

            monkeypatch.setattr(_Path, "read_bytes", deny_read_bytes)
            return snap

        monkeypatch.setattr(sv, "prepare_selected_scenario", prepare_then_seal)

        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        assert result["success"], result.get("message")
        # No second scenario read happened.
        assert reads["count"] == 0
        # Captured-byte SHA matches independently hashed captured bytes (and the report).
        assert captured["sha"] == hashlib.sha256(captured["bytes"]).hexdigest()
        assert result["data"]["scenario"]["sha256"] == captured["sha"]
        # The ORIGINAL captured figure specification is consumed (3 nobles per faction).
        assert self._nobles_per_faction(result["data"]["state"]) == {
            "optimates": 3, "populares": 3, "equites": 3}

    # ---- Witness 3b: recursive immutability / fresh thaw ----
    def test_snapshot_is_recursively_immutable_and_thaw_is_fresh(self):
        import hashlib
        from src.core import scenario_validation as sv

        snap = sv.prepare_selected_scenario("gr_f_3h.json")
        assert isinstance(snap.raw_bytes, bytes)
        assert snap.byte_length == len(snap.raw_bytes)
        assert snap.sha256 == hashlib.sha256(snap.raw_bytes).hexdigest()

        # Nested frozen content rejects mutation.
        with pytest.raises(TypeError):
            snap.frozen_config["initial_state"]["treasury"] = 999
        with pytest.raises((TypeError, AttributeError)):
            snap.frozen_config["initial_state"]["factions"].append({"id": "x"})

        # report_copy / config_copy return fresh detached objects on each call.
        report = snap.report_copy()
        report["factions"].append({"id": "injected"})
        assert all(row["id"] != "injected" for row in snap.report_copy()["factions"])

        config = snap.config_copy()
        config["initial_state"]["treasury"] = 123
        assert snap.config_copy()["initial_state"]["treasury"] == 100  # gr_f_3h treasury


class TestHistoricalFallbackConserved:
    """Historical CLI/direct loader fallback stays unchanged (outside the GUI route)."""

    def test_direct_load_scenario_missing_file_builtin_fallback_unchanged(self):
        from src.core.game_state import GameState
        from src.core.scenario_loader import ScenarioLoader

        state = GameState()
        # Historical public entry, unreachable from the GUI route: a missing file
        # routes to the built-in default (1H/2AI, year -264, treasury 100).
        ScenarioLoader.load_scenario(state, "definitely_missing_scenario.json")
        players = state.get_all_players()
        assert len(players) == 3
        humans = [p for p in players if p.player_type.value == "human"]
        assert len(humans) == 1
        assert state.turn.year == -264
        assert state.treasury == 100


class TestGuiMainScenarioArgParsing:
    """The launch parameter is parsed out of argv and stripped before Qt."""

    def test_absent_scenario_yields_none_and_forwards_all(self):
        scenario, forwarded = gui_main._extract_scenario(["gui_main.py"])
        assert scenario is None
        assert forwarded == ["gui_main.py"]

    def test_separate_form_is_stripped(self):
        scenario, forwarded = gui_main._extract_scenario(
            ["gui_main.py", "--scenario", "gr_f_6h.json"])
        assert scenario == "gr_f_6h.json"
        assert forwarded == ["gui_main.py"]

    def test_equals_form_is_stripped(self):
        scenario, forwarded = gui_main._extract_scenario(
            ["gui_main.py", "--scenario=gr_f_3h.json", "-platform", "offscreen"])
        assert scenario == "gr_f_3h.json"
        assert forwarded == ["gui_main.py", "-platform", "offscreen"]

    def test_missing_value_raises(self):
        with pytest.raises(ValueError):
            gui_main._extract_scenario(["gui_main.py", "--scenario"])

    def test_default_scenario_constant(self):
        assert gui_main.DEFAULT_SCENARIO_FILE == "gui_prototype.json"

    def test_explicit_empty_equals_form_raises(self):
        # R01: `--scenario=` (explicit empty) is NOT absent; it must be rejected,
        # never silently replaced by the historical default.
        with pytest.raises(ValueError):
            gui_main._extract_scenario(["gui_main.py", "--scenario="])

    def test_explicit_empty_separate_form_raises(self):
        with pytest.raises(ValueError):
            gui_main._extract_scenario(["gui_main.py", "--scenario", ""])


class TestProductionEntryExplicitEmpty:
    """R01: explicit empty must fail BEFORE any factory call or GuiApp opening."""

    @staticmethod
    def _deny_factory_and_gui(monkeypatch):
        def deny_factory(*args, **kwargs):
            raise AssertionError(
                "factory must not be called for an explicit empty selection")

        def deny_gui(*args, **kwargs):
            raise AssertionError(
                "GuiApp must not be constructed for an explicit empty selection")

        monkeypatch.setattr(
            gui_main.session_api, "create_gui_prototype_session", deny_factory)
        monkeypatch.setattr(gui_main, "GuiApp", deny_gui)

    def test_equals_form_empty_rejected_no_default_no_gui(self, monkeypatch):
        self._deny_factory_and_gui(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["gui_main.py", "--scenario="])
        assert gui_main.main() == 2

    def test_separate_form_empty_rejected_no_default_no_gui(self, monkeypatch):
        self._deny_factory_and_gui(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["gui_main.py", "--scenario", ""])
        assert gui_main.main() == 2


class TestEnvelopeOriginAndImmutability:
    """S-A r5 P2 witnesses (a)/(b): validator-only ORIGIN + whole-envelope immutability.

    Closes SA-A-R02-r4a (a public/reinitializable envelope was accepted on
    ``isinstance`` alone) and the first half of SA-A-EVID-r4b (no unauthorized-
    construction / whole-envelope-mutation witness). The real production factory is
    used; only acquisition/initializer seams are instrumented.
    """

    def test_public_construction_is_not_a_bypass_api(self):
        from src.core import scenario_validation as sv

        # There is NO public constructor accepting arbitrary bytes/config/report: a
        # bypass call is refused outright, before any state is stored.
        with pytest.raises(TypeError):
            sv.ValidatedScenarioSnapshot(
                "gr_f_3h.json", "unapproved", b"{}",
                {"initial_state": {"factions": []}}, {"arbitrary": "report"})
        # The preparation path still mints a usable, origin-stamped envelope.
        snap = sv.prepare_selected_scenario("gr_f_3h.json")
        assert sv.is_usable_snapshot(snap) is True

    def test_foreign_envelope_rejected_by_bound_initializer(self):
        from src.core import scenario_validation as sv
        from src.core.game_state import GameState
        from src.core.scenario_loader import ScenarioLoader

        # Forge a same-class object OUTSIDE the validator (bypassing the ordinary
        # constructor) carrying mismatched bytes/config/report.
        forged = object.__new__(sv.ValidatedScenarioSnapshot)
        object.__setattr__(forged, "_canonical_name", "gr_f_3h.json")
        object.__setattr__(forged, "_path", "unapproved")
        object.__setattr__(forged, "_raw_bytes", b"{}")
        object.__setattr__(forged, "_byte_length", 2)
        object.__setattr__(forged, "_sha256", "deadbeef")
        object.__setattr__(forged, "_config", {"initial_state": {"factions": []}})
        object.__setattr__(forged, "_report", {})
        object.__setattr__(forged, "_sealed", True)

        assert isinstance(forged, sv.ValidatedScenarioSnapshot)
        assert sv.is_usable_snapshot(forged) is False

        state = GameState()
        factions_before = len(state.factions)
        players_before = len(state.get_all_players())
        with pytest.raises(TypeError):
            ScenarioLoader.initialize_validated_scenario(state, forged)
        # No partial session/state leaked by the rejected envelope.
        assert len(state.factions) == factions_before
        assert len(state.get_all_players()) == players_before

    def test_initializer_rejects_filename_dict_report_none(self):
        from src.core.game_state import GameState
        from src.core.scenario_loader import ScenarioLoader

        state = GameState()
        for bad in ["gr_f_3h.json", {}, {"factions": []}, None, 42, object()]:
            with pytest.raises(TypeError):
                ScenarioLoader.initialize_validated_scenario(state, bad)

    def test_whole_envelope_reassignment_and_reinit_rejected(self):
        from src.core import scenario_validation as sv

        snap = sv.prepare_selected_scenario("gr_f_3h.json")
        original_config = snap.config_copy()
        original_sha = snap.sha256

        # Slot reassignment / deletion is forbidden (no mutable holder).
        with pytest.raises(AttributeError):
            snap._config = {"initial_state": {}}
        with pytest.raises(AttributeError):
            snap._sha256 = "0" * 64
        with pytest.raises(AttributeError):
            del snap._raw_bytes
        # Re-running the ordinary initializer cannot swap config while keeping bytes.
        with pytest.raises(TypeError):
            snap.__init__(
                "gr_f_3h.json", snap.path, snap.raw_bytes,
                {"initial_state": {"factions": []}}, snap.report_copy())

        # The envelope is still the validator-issued one: unchanged and usable.
        assert sv.is_usable_snapshot(snap) is True
        assert snap.config_copy() == original_config
        assert snap.sha256 == original_sha


class TestAcquisitionFailureFailClosed:
    """S-A r5 P2 witness (c): pre-capture acquisition failures fail closed.

    Read / decode / JSON / schema failures at the capture seam must yield
    ``SCENARIO_INVALID`` with no half-open session and zero historical-edge calls.
    Only acquisition seams are instrumented; the production factory is real.
    """

    @staticmethod
    def _forbid_legacy(monkeypatch):
        from src.core.scenario_loader import ScenarioLoader

        counters = {"load_scenario": 0, "_get_default_config": 0}

        def forbidden_load(*a, **k):
            counters["load_scenario"] += 1
            raise AssertionError("forbidden edge: load_scenario reached from the GUI route")

        def forbidden_default(*a, **k):
            counters["_get_default_config"] += 1
            raise AssertionError(
                "forbidden edge: _get_default_config reached from the GUI route")

        monkeypatch.setattr(ScenarioLoader, "load_scenario", staticmethod(forbidden_load))
        monkeypatch.setattr(
            ScenarioLoader, "_get_default_config", staticmethod(forbidden_default))
        return counters

    @staticmethod
    def _assert_fails_closed(result, counters):
        assert result["success"] is False
        assert result["data"] is None
        assert any("SCENARIO_INVALID" in e for e in result["errors"])
        assert counters == {"load_scenario": 0, "_get_default_config": 0}

    def test_read_failure_fails_closed(self, monkeypatch):
        from pathlib import Path as _Path

        counters = self._forbid_legacy(monkeypatch)

        def deny_read_bytes(self):
            raise OSError("simulated unreadable scenario")

        monkeypatch.setattr(_Path, "read_bytes", deny_read_bytes)
        result = session_api.create_gui_prototype_session(scenario_file="gr_f_3h.json")
        self._assert_fails_closed(result, counters)

    def test_decode_failure_fails_closed(self, monkeypatch, tmp_path):
        from src.core import scenario_validation as sv

        counters = self._forbid_legacy(monkeypatch)
        (tmp_path / "bad_utf8.json").write_bytes(b"\xff\xfe\x00\x01\x02")
        monkeypatch.setattr(sv, "scenarios_dir", lambda: tmp_path)
        result = session_api.create_gui_prototype_session(scenario_file="bad_utf8.json")
        self._assert_fails_closed(result, counters)

    def test_invalid_json_fails_closed(self, monkeypatch, tmp_path):
        from src.core import scenario_validation as sv

        counters = self._forbid_legacy(monkeypatch)
        (tmp_path / "bad_json.json").write_text("{ this is not json ", encoding="utf-8")
        monkeypatch.setattr(sv, "scenarios_dir", lambda: tmp_path)
        result = session_api.create_gui_prototype_session(scenario_file="bad_json.json")
        self._assert_fails_closed(result, counters)

    def test_schema_failure_fails_closed(self, monkeypatch, tmp_path):
        import json as _json
        from src.core import scenario_validation as sv

        counters = self._forbid_legacy(monkeypatch)
        illegal = {"scenario_name": "illegal", "initial_state": {"factions": []}}
        (tmp_path / "bad_schema.json").write_text(_json.dumps(illegal), encoding="utf-8")
        monkeypatch.setattr(sv, "scenarios_dir", lambda: tmp_path)
        result = session_api.create_gui_prototype_session(scenario_file="bad_schema.json")
        self._assert_fails_closed(result, counters)
