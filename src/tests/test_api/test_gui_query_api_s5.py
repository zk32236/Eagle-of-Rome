"""EOR20261011-01 S5 — war_list / legion_status / fleet_status DTO contracts.

Frozen authority (G3 v1.5 → v1.4 → v1.3 → v1.2 → v1.1):
  * SA v1.1 §5.3 capabilities / selector grammar (war_list string ws-id selector;
    legion_status / fleet_status canonical-decimal selector);
  * SA v1.1 §6.2 per-query field allowlist (V public / U-H absent) — military
    DTO authority, as amended for legion_status by ERRATUM LEGION-S5-01;
  * ERRATUM LEGION-S5-01 (SA LEGION_RULING=A): legion_status publishes the frozen
    nine-field current-public projection (number,name,status,is_veteran,war_id,
    assigned,strength,cost,destroyed_turn) present-when-present for eligible
    HUMAN/AI viewers — the five deployment/strength/cost/destroyed fields are
    RESTORED. The fleet strength/commander/assigned_war_id/mission fields remain
    ABSENT for EVERY relation.

DATA-class acceptance. Production read seam =
``gui_query_api.get_global_query_result``. No helper/shortcut entry; every case
drives the public seam with a sanctioned prototype session (AC-13/AC-15 style).

⚠️ war_list field-matrix conflict (EOR20261011-01 S5, DISCLOSED):
  The S5 §6.2 war_list field list (``id,name,status,threat_level,naval_required,
  commander_name,legions_assigned,assigned_fleet_count,fleet_strength_read_model``;
  "raw war/debug/deck/assignment mirror fields absent") is a **DESIGN_REALITY_MISMATCH**
  against the pre-existing FROZEN war read-model contracts (WP-O R03 / WP-G-R1 S3
  SC-04 / WP-G-R3 S4 §4.5 / WP-G-R3 S5 T19), which mandate ``commander_id``,
  ``fleets_assigned``, ``naval_ready``, ``assigned_fleet_ids`` and the layered
  ``fleet_*`` strength fields on the very same GUI war summary. Narrowing war_list
  would break those frozen contracts, so the AUTHORITATIVE war read model is
  preserved unchanged and the conflict is routed to PM/SA (see Implementation
  Report). These cases pin the preserved (authoritative) war shape accordingly.
"""
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import gui_query_api, session_api
from src.core.entities.war import War, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus

# ---------------------------------------------------------------------------
# War summary read model — the authoritative (preserved) shape.
# ---------------------------------------------------------------------------
WAR_READ_MODEL_FIELDS = {
    "id", "name", "status", "threat_level", "naval_required",
    "commander_id", "commander_name", "legions_assigned",
    "assigned_fleet_count", "fleets_assigned", "naval_ready",
    "assigned_fleet_ids", "fleet_nominal_strength", "fleet_quality_adjusted_base",
    "fleet_experience_bonus", "fleet_commander_bonus",
    "fleet_effective_combat_strength", "fleet_strength_packages",
}
# Raw war / debug / deck container keys that must NEVER surface in any DTO layer.
WAR_RAW_DEBUG_KEYS = {
    "_war_deck", "war_deck", "_active_wars", "_threats", "_truce_wars",
    "_resolved_wars", "enemy_naval_current", "_enemy_naval_current",
    "_enemy_naval_max", "_enemy_land_current", "_enemy_land_max",
    "_enemy_budget_initial", "strength", "_strength", "reward_receipt",
    "_reward_receipt", "_activation_origin", "_activation_episode",
}
WAR_DETAIL_LABELS = [
    "query.war.id", "query.war.name", "query.war.status", "query.war.threat_level",
    "query.war.naval_required", "query.war.commander_name",
    "query.war.legions_assigned", "query.war.assigned_fleet_count",
    "query.war.naval_ready", "query.war.fleet_effective_combat_strength",
]

# ---------------------------------------------------------------------------
# legion_status — §6.2 public observables only (MIL-10 UNVERIFIED absent)
# ---------------------------------------------------------------------------
# legion_status — frozen nine-field current-public projection (LEGION-S5-01).
LEGION_PUBLIC_FIELDS = (
    "number", "name", "status", "is_veteran", "war_id",
    "assigned", "strength", "cost", "destroyed_turn",
)
# DETAIL restores the identity 4 + the deployment/strength observables.
LEGION_DETAIL_LABELS = [
    "query.legion.number", "query.legion.name", "query.legion.status",
    "query.legion.is_veteran", "query.legion.war_id", "query.legion.assigned",
    "query.legion.strength",
]
# Legion fields that REMAIN hidden/private after LEGION-S5-01 (the five
# deployment/strength/cost/destroyed fields are now authorized public).
LEGION_FORBIDDEN_KEYS = {
    "commander_id", "_destroyed_turn", "_legion_type", "battles_fought",
    "battles_won", "experience", "status_emoji", "legion_type",
}

# ---------------------------------------------------------------------------
# fleet_status — §6.2 public identity only (no debug fields)
# ---------------------------------------------------------------------------
FLEET_DETAIL_LABELS = [
    "query.fleet.number", "query.fleet.name", "query.fleet.fleet_type",
    "query.fleet.status", "query.fleet.is_veteran",
]
FLEET_FORBIDDEN_KEYS = {
    "strength", "_strength_base", "commander", "commander_id", "_commander_id",
    "assigned_war_id", "_assigned_war_id", "mission", "_assigned_mission_type",
    "experience", "_experience", "quality_adjusted_base", "_nominal_strength_base",
    "construction_quality_numerator", "_construction_quality_numerator",
    "construction_quality_denominator", "_construction_quality_denominator",
    "construction_package_id", "_construction_package_id",
    "destroyed_turn", "_destroyed_turn", "target_war_id", "_target_war_id",
    "contract_id", "_contract_id", "build_start_turn", "_build_start_turn",
}

S5_QUERIES = ("war_list", "legion_status", "fleet_status")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _rng_isolated():
    state = random.getstate()
    yield
    random.setstate(state)


def _setup_state():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    return state, viewer_id


def _eligible_viewers(state):
    return [p for p in state.get_all_players()
            if p.player_type.value in ("human", "ai")]


def _own_figure(state, faction_id):
    return next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)


def _all_strings(obj):
    out = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.append(str(key))
            out.extend(_all_strings(value))
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            out.extend(_all_strings(value))
    elif isinstance(obj, str):
        out.append(obj)
    elif obj is not None:
        out.append(str(obj))
    return out


def _all_keys(obj):
    out = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.append(str(key))
            out.extend(_all_keys(value))
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            out.extend(_all_keys(value))
    return out


def _data(state, viewer_id, query_id, filter_text="", record_id=""):
    result = gui_query_api.get_global_query_result(
        state, viewer_id, query_id, filter_text, record_id
    )
    return result, result["data"]


def _detail_labels(dto):
    return [field["label_key"] for field in dto["detail"]["fields"]]


def _add_active_war(state, war_id="w1", name="Test War", threat=3, naval=False,
                    commander_id=None):
    """Sanctioned initial-state fixture: a real War in the canonical WarSystem."""
    ws = state.get_war_system()
    war = War(id=war_id, name=name, start_year=-270, threat_level=threat,
              naval_required=naval)
    war.status = WarStatus.ACTIVE
    if commander_id is not None:
        war.commander_id = commander_id
    ws._active_wars.append(war)
    return war


def _add_fleet(state, number=1, name="Fleet One", fleet_type="trireme",
               status=FleetStatus.AVAILABLE, war_id=None, veteran=False):
    """Sanctioned initial-state fixture: a real Fleet in the canonical NavalSystem."""
    naval = gui_query_api._get_naval_system(state)
    fleet = Fleet(number=number, name=name, fleet_type=fleet_type)
    fleet._status = status
    fleet._is_veteran = veteran
    if war_id is not None:
        fleet._assigned_war_id = war_id
    naval._fleets[number] = fleet
    return fleet


def _attach_fleet_to_war(state, war, number=1):
    naval = gui_query_api._get_naval_system(state)
    fleet = Fleet(number=number, name="Fleet %d" % number, fleet_type="trireme")
    fleet._status = FleetStatus.ON_MISSION
    fleet._assigned_war_id = war.id
    naval._fleets[number] = fleet
    war.assign_fleet(number)
    return fleet


# ===========================================================================
# war_list — AC-09 (authoritative public war read model; no raw debug containers)
# ===========================================================================
def test_war_list_capabilities_and_empty_state():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "war_list", "", "")

    assert result["success"]
    assert dto["result_state"] in ("OK", "EMPTY")
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}
    assert dto["filters"]["field"] == "name"
    assert "wars" in dto["summary"]
    assert "counts" in dto["summary"]


def test_war_list_public_read_model_no_raw_debug_containers():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    commander = _own_figure(state, faction_id)
    _add_active_war(state, "w1", "Punic War", threat=4, naval=True,
                    commander_id=commander.id)

    result, dto = _data(state, viewer_id, "war_list", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert [it["record_id"] for it in dto["items"]] == ["w1"]
    entry = next(w for w in dto["summary"]["wars"] if w["id"] == "w1")
    assert set(entry.keys()) == WAR_READ_MODEL_FIELDS, set(entry.keys())
    assert entry["commander_name"] == commander.get_formal_name()
    keys = set(_all_keys(dto))
    assert not (WAR_RAW_DEBUG_KEYS & keys), keys & WAR_RAW_DEBUG_KEYS


def test_war_list_commander_is_live_only():
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "No Commander War")

    _result, dto = _data(state, viewer_id, "war_list", "", "")
    entry = next(w for w in dto["summary"]["wars"] if w["id"] == "w1")
    assert entry["commander_id"] is None
    assert entry["commander_name"] == ""


def test_war_list_detail_shape():
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "Punic War", threat=4, naval=True)

    result, dto = _data(state, viewer_id, "war_list", "", "w1")

    assert result["success"]
    assert dto["items"] == []
    assert dto["detail"]["record_id"] == "w1"
    assert _detail_labels(dto) == WAR_DETAIL_LABELS


def test_war_list_string_selector_filter_and_duplicate_id():
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "Punic War")

    ok = gui_query_api.get_global_query_result(state, viewer_id, "war_list", "", "w1")
    assert ok["success"]
    assert ok["data"]["detail"]["record_id"] == "w1"

    # exact case-sensitive codepoint equality; no trim; absent id -> record_unavailable
    for bad in ["w", "W1", "w1 ", " w1", "999"]:
        result = gui_query_api.get_global_query_result(
            state, viewer_id, "war_list", "", bad)
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED", bad
        assert [e["code"] for e in result["data"]["errors"]] == ["record_unavailable"], bad

    _result, filtered = _data(state, viewer_id, "war_list", "Punic", "")
    assert filtered["filters"]["applied"] == "punic"
    assert {it["record_id"] for it in filtered["items"]} == {"w1"}

    # duplicate / empty canonical war id -> query_failed (no first-match)
    from unittest.mock import patch
    ws = state.get_war_system()
    war = ws.get_active_wars()[0]
    with patch.object(ws, "get_active_wars", return_value=[war, war]):
        dup = gui_query_api.get_global_query_result(state, viewer_id, "war_list")
    assert not dup["success"]
    assert [e["code"] for e in dup["data"]["errors"]] == ["query_failed"]

    from types import SimpleNamespace
    with patch.object(ws, "get_active_wars", return_value=[SimpleNamespace(id="")]):
        inv = gui_query_api.get_global_query_result(state, viewer_id, "war_list")
    assert not inv["success"]
    assert [e["code"] for e in inv["data"]["errors"]] == ["query_failed"]


def test_war_list_missing_war_system_fails_closed():
    from unittest.mock import patch
    state, viewer_id = _setup_state()

    with patch.object(state, "get_war_system", return_value=None):
        result = gui_query_api.get_global_query_result(state, viewer_id, "war_list")

    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]
    assert result["data"]["items"] == [] and result["data"]["summary"] == {}


# ===========================================================================
# legion_status — AC-10 public observables only (MIL-10 fields absent)
# ===========================================================================
def test_legion_status_public_projection_and_canonical_counts():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "legion_status", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["status"] == "readonly"
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}

    ms = state.get_military_system()
    legions = ms.get_all_legions()
    assert dto["summary"]["counts"]["total"] == len(legions)

    # counts = the frozen canonical grouping (total/active/available/assigned/
    # destroyed), NOT a generic count-by-status rewrite nor count-from-hidden.
    expected = {"total": 0, "active": 0, "available": 0, "assigned": 0, "destroyed": 0}
    for lg in legions:
        d = lg.to_display_dict(state)
        expected["total"] += 1
        if d["status"] == "active":
            expected["active"] += 1
        if d["status"] in {"available", "unraised", "disbanded"}:
            expected["available"] += 1
        if d["assigned"]:
            expected["assigned"] += 1
        if d["status"] == "destroyed":
            expected["destroyed"] += 1
    assert dto["summary"]["counts"] == expected

    # every record is EXACTLY the nine authorized public keys and equals the
    # same-state canonical Legion display read model (parity).
    for legion in dto["summary"]["legions"]:
        assert set(legion.keys()) == set(LEGION_PUBLIC_FIELDS), legion
        canonical = next(
            l for l in legions if int(l.number) == legion["number"]
        ).to_display_dict(state)
        assert legion == {k: canonical[k] for k in LEGION_PUBLIC_FIELDS if k in canonical}

    keys = set(_all_keys(dto))
    assert not (LEGION_FORBIDDEN_KEYS & keys), keys & LEGION_FORBIDDEN_KEYS
    assert {"war_id", "assigned", "strength", "cost", "destroyed_turn"} <= keys


def test_legion_status_detail_exposes_public_deployment_and_strength():
    state, viewer_id = _setup_state()
    legion = state.get_military_system().get_legion_by_number(1)
    legion.war_id = "war-abc"
    legion.commander_id = 987654

    result, dto = _data(state, viewer_id, "legion_status", "", "1")

    assert result["success"]
    assert dto["items"] == []
    assert dto["detail"]["record_id"] == "1"
    assert _detail_labels(dto) == LEGION_DETAIL_LABELS
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.legion.war_id"]["value"] == "war-abc"
    assert by_label["query.legion.assigned"]["value_key"] == "query.bool.yes"
    canonical = legion.to_display_dict(state)
    assert by_label["query.legion.strength"]["value"] == str(canonical["strength"])
    keys = set(_all_keys(dto))
    assert not (LEGION_FORBIDDEN_KEYS & keys), keys & LEGION_FORBIDDEN_KEYS


def test_legion_status_preserves_typed_null_false_and_zero():
    state, viewer_id = _setup_state()
    legion = state.get_military_system().get_legion_by_number(1)
    legion.war_id = None
    legion.commander_id = None

    _result, dto = _data(state, viewer_id, "legion_status", "", "")
    entry = next(l for l in dto["summary"]["legions"] if l["number"] == 1)
    # present-when-present: a genuinely unset target is a typed None, not dropped.
    assert "war_id" in entry and entry["war_id"] is None
    assert entry["assigned"] is False
    assert isinstance(entry["strength"], int)
    assert isinstance(entry["cost"], int)
    assert "destroyed_turn" in entry and isinstance(entry["destroyed_turn"], int)

    _result, detail = _data(state, viewer_id, "legion_status", "", "1")
    by_label = {f["label_key"]: f for f in detail["detail"]["fields"]}
    assert by_label["query.legion.war_id"]["value_key"] == "query.value.none"
    assert by_label["query.legion.assigned"]["value_key"] == "query.bool.no"


def test_legion_status_selector_and_filter():
    state, viewer_id = _setup_state()

    for bad in ["0", "01", "-1", "1.5", "abc", " 1", "9999"]:
        result = gui_query_api.get_global_query_result(
            state, viewer_id, "legion_status", "", bad)
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED", bad
        assert [e["code"] for e in result["data"]["errors"]] == ["record_unavailable"], bad

    _result, lst = _data(state, viewer_id, "legion_status", "", "")
    name = lst["summary"]["legions"][0]["name"]
    _result, filtered = _data(state, viewer_id, "legion_status", name, "")
    assert filtered["filters"]["applied"] == name.casefold()
    assert all(name.casefold() in l["name"].casefold()
               for l in filtered["summary"]["legions"])


def test_legion_status_duplicate_or_invalid_number_fails_query():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    military = state.get_military_system()
    legions = list(military.get_all_legions())
    with patch.object(military, "get_all_legions", return_value=list(legions) + [legions[0]]):
        dup = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")
    assert not dup["success"]
    assert [e["code"] for e in dup["data"]["errors"]] == ["query_failed"]

    with patch.object(military, "get_all_legions",
                      return_value=[SimpleNamespace(number=0, name="x",
                                                    status=None, is_veteran=False)]):
        inv = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")
    assert not inv["success"]
    assert [e["code"] for e in inv["data"]["errors"]] == ["query_failed"]


def test_legion_status_public_present_private_absent_recursive():
    state, viewer_id = _setup_state()
    legion = state.get_military_system().get_legion_by_number(1)
    legion.war_id = "war-999"
    legion.commander_id = 987654
    legion._destroyed_turn = 999888
    legion.is_veteran = True

    _result, list_dto = _data(state, viewer_id, "legion_status", "", "")
    _result, detail_dto = _data(state, viewer_id, "legion_status", "", "1")

    # authorized public values are present-when-present.
    entry = next(l for l in list_dto["summary"]["legions"] if l["number"] == 1)
    assert entry["war_id"] == "war-999"
    assert entry["assigned"] is True
    assert entry["destroyed_turn"] == 999888
    assert entry["is_veteran"] is True
    blob = " ".join(_all_strings(list_dto))
    assert "war-999" in blob and "999888" in blob
    assert any(l["is_veteran"] for l in list_dto["summary"]["legions"])

    # the commander identity stays hidden for EVERY relation; no raw internal key
    # leaks; the private sentinel never surfaces.
    for dto in (list_dto, detail_dto):
        keys = set(_all_keys(dto))
        assert not (LEGION_FORBIDDEN_KEYS & keys), keys & LEGION_FORBIDDEN_KEYS
        assert "987654" not in " ".join(_all_strings(dto))


def test_legion_status_missing_required_source_fails_closed():
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    legion = state.get_military_system().get_legion_by_number(1)
    incomplete = {"number": 1, "name": "Legio I", "status": "available",
                  "is_veteran": False, "war_id": None, "assigned": False}  # no strength
    with patch.object(legion, "to_display_dict", return_value=incomplete):
        result = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")
    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]


def test_legion_status_rejects_ineligible_viewer_type():
    from unittest.mock import patch
    from src.core.entities.player import Player, PlayerType
    state, viewer_id = _setup_state()
    observer = Player("obs", faction_id=state.get_player(viewer_id).faction_id,
                      player_type=PlayerType.OBSERVER)
    with patch.object(state, "get_player", return_value=observer):
        result = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")
    assert not result["success"]
    assert result["data"]["result_state"] == "DENIED"
    assert [e["code"] for e in result["data"]["errors"]] == ["viewer_unavailable"]


# ===========================================================================
# fleet_status — AC-11 player-level public identity only (no debug fields)
# ===========================================================================
def test_fleet_status_empty_state():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "fleet_status", "", "")

    assert result["success"]
    assert dto["result_state"] == "EMPTY"
    assert dto["items"] == []
    assert dto["summary"]["counts"]["total"] == 0
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}


def test_fleet_status_public_fields_only():
    state, viewer_id = _setup_state()
    _add_fleet(state, number=1, name="Fleet One", fleet_type="trireme",
               status=FleetStatus.AVAILABLE, veteran=True)
    _add_fleet(state, number=2, name="Fleet Two", fleet_type="quinquereme",
               status=FleetStatus.BUILDING)

    result, dto = _data(state, viewer_id, "fleet_status", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert [it["record_id"] for it in dto["items"]] == ["1", "2"]
    assert all(it["label_key"] == "query.item.fleet" for it in dto["items"])
    for fleet in dto["summary"]["fleets"]:
        assert set(fleet.keys()) == {"number", "name", "fleet_type", "status", "is_veteran"}
    assert dto["summary"]["counts"]["available"] == 1
    assert dto["summary"]["counts"]["building"] == 1
    keys = set(_all_keys(dto))
    assert not (FLEET_FORBIDDEN_KEYS & keys), keys & FLEET_FORBIDDEN_KEYS


def test_fleet_status_detail_is_public_identity_only():
    state, viewer_id = _setup_state()
    _add_fleet(state, number=1, name="Fleet One", fleet_type="trireme")

    result, dto = _data(state, viewer_id, "fleet_status", "", "1")

    assert result["success"]
    assert dto["detail"]["record_id"] == "1"
    assert _detail_labels(dto) == FLEET_DETAIL_LABELS
    keys = set(_all_keys(dto))
    assert not (FLEET_FORBIDDEN_KEYS & keys), keys & FLEET_FORBIDDEN_KEYS


def test_fleet_status_selector_and_filter():
    state, viewer_id = _setup_state()
    _add_fleet(state, number=1, name="Fleet One")

    for bad in ["0", "01", "-1", "1.5", "abc", " 1", "999"]:
        result = gui_query_api.get_global_query_result(
            state, viewer_id, "fleet_status", "", bad)
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED", bad
        assert [e["code"] for e in result["data"]["errors"]] == ["record_unavailable"], bad

    _result, filtered = _data(state, viewer_id, "fleet_status", "one", "")
    assert filtered["filters"]["applied"] == "one"
    assert {it["record_id"] for it in filtered["items"]} == {"1"}

    _result, empty = _data(state, viewer_id, "fleet_status", "zzz-no-match", "")
    assert empty["result_state"] == "EMPTY"


def test_fleet_status_no_debug_fields_recursive():
    state, viewer_id = _setup_state()
    fleet = _add_fleet(state, number=1, name="Fleet One", war_id="war-777")
    fleet._commander_id = 555111
    fleet._assigned_mission_type = "naval"
    fleet._strength_base = 424242
    fleet._nominal_strength_base = 313131

    _result, list_dto = _data(state, viewer_id, "fleet_status", "", "")
    _result, detail_dto = _data(state, viewer_id, "fleet_status", "", "1")

    for dto in (list_dto, detail_dto):
        keys = set(_all_keys(dto))
        assert not (FLEET_FORBIDDEN_KEYS & keys), keys & FLEET_FORBIDDEN_KEYS
        blob = " ".join(_all_strings(dto))
        for sentinel in ("war-777", "555111", "424242", "313131", "naval"):
            assert sentinel not in blob, sentinel


def test_fleet_status_duplicate_or_invalid_number_fails_query():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    naval = gui_query_api._get_naval_system(state)
    f1 = _add_fleet(state, number=1, name="Fleet One")
    with patch.object(naval, "get_all_fleets", return_value=[f1, f1]):
        dup = gui_query_api.get_global_query_result(state, viewer_id, "fleet_status")
    assert not dup["success"]
    assert [e["code"] for e in dup["data"]["errors"]] == ["query_failed"]

    with patch.object(naval, "get_all_fleets",
                      return_value=[SimpleNamespace(number=0, name="x",
                                                    fleet_type="t", status=None,
                                                    is_veteran=False)]):
        inv = gui_query_api.get_global_query_result(state, viewer_id, "fleet_status")
    assert not inv["success"]
    assert [e["code"] for e in inv["data"]["errors"]] == ["query_failed"]


def test_fleet_status_missing_source_fails_closed():
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    with patch.object(gui_query_api, "_get_naval_system", return_value=None):
        result = gui_query_api.get_global_query_result(state, viewer_id, "fleet_status")
    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]


# ===========================================================================
# Cross-cutting — AC-13 / AC-15 / AC-16 / no-placeholder / no re-break
# ===========================================================================
def test_s5_military_queries_are_viewer_independent_public():
    state, _ = _setup_state()
    _add_active_war(state, "w1", "Punic War")
    _add_fleet(state, number=1, name="Fleet One")
    _add_fleet(state, number=2, name="Fleet Two")

    for query_id in S5_QUERIES:
        seen = None
        for viewer in _eligible_viewers(state):
            dto = _data(state, viewer.player_id, query_id, "", "")[1]
            if seen is None:
                seen = dto
            else:
                assert dto["summary"] == seen["summary"], (query_id, viewer.player_id)


def test_s5_readonly_invariant_core_and_rng():
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "Punic War", naval=True)
    _attach_fleet_to_war(state, state.get_war_system()._active_wars[-1], number=1)
    rng_before = random.getstate()

    def snapshot():
        return {"dict": state.to_dict()}

    before = snapshot()
    for query_id in S5_QUERIES:
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "")
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "a", "")
    for qid, rid in (("war_list", "w1"), ("legion_status", "1"), ("fleet_status", "1")):
        gui_query_api.get_global_query_result(state, viewer_id, qid, "", rid)
    after = snapshot()

    assert after == before
    assert random.getstate() == rng_before


def test_s5_queries_reject_invalid_viewer():
    state, _ = _setup_state()
    for query_id in S5_QUERIES:
        result = gui_query_api.get_global_query_result(state, "missing_player", query_id)
        assert not result["success"], query_id
        assert result["data"]["result_state"] == "DENIED", query_id


def test_all_twelve_canonical_queries_are_implemented_no_placeholder():
    state, viewer_id = _setup_state()
    assert len(gui_query_api.CANONICAL_QUERY_IDS) == 12
    for qid in gui_query_api.CANONICAL_QUERY_IDS:
        data = gui_query_api.get_global_query_result(state, viewer_id, qid)["data"]
        codes = [e["code"] for e in data["errors"]]
        assert "not_implemented" not in codes, qid
        assert "unknown_query" not in codes, qid
        assert data["id"] == qid, qid
        assert data["result_state"] in ("OK", "EMPTY"), qid


def test_noncanonical_query_still_unknown_no_rebreak():
    """The pre-existing fail-closed probe targets a non-canonical id (no_such_query)."""
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "no_such_query")

    assert not result["success"]
    assert result["data"]["id"] == ""
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["unknown_query"]


def test_s5_i18n_keys_present_in_both_locales():
    import json as _json
    keys = [
        "query.war_list.filter_label", "query.legion_status.filter_label",
        "query.fleet_status.filter_label",
        "query.fleet_status.message", "query.item.fleet", "query.value.fleet",
        "query.fleet.number", "query.fleet.name", "query.fleet.fleet_type",
        "query.fleet.status", "query.fleet.is_veteran",
        "query.fleet.status.building", "query.fleet.status.available",
        "query.fleet.status.on_mission", "query.fleet.status.in_combat",
        "query.fleet.status.destroyed", "query.fleet.status.disbanded",
        "query.war_list.message", "query.legion_status.message",
        "query.item.war", "query.item.legion", "query.value.war", "query.value.legion",
        "query.war.id", "query.war.name", "query.war.status", "query.war.threat_level",
        "query.war.naval_required", "query.war.commander_name",
        "query.war.legions_assigned", "query.war.assigned_fleet_count",
        "query.legion.number", "query.legion.name", "query.legion.status",
        "query.legion.is_veteran", "query.legion.war_id", "query.legion.assigned",
        "query.legion.strength", "query.legion.cost", "query.legion.destroyed_turn",
        "query.value.none", "query.bool.yes", "query.bool.no",
    ]
    for locale in ("zh-CN", "en-US"):
        path = os.path.join(PROJECT_ROOT, "data", "i18n", "%s.json" % locale)
        with open(path, encoding="utf-8-sig") as fh:
            catalog = _json.load(fh)
        for key in keys:
            assert key in catalog, (locale, key)
            assert str(catalog[key]) != "", (locale, key)


# ===========================================================================
# S5-ATTEMPT-3 — F1 (missing required source cannot fabricate zero success)
# and F2 (war string-id codepoint ascending order). Public read seam only.
# ===========================================================================
def _add_war_to_group(state, war_id, name, group, threat=3, naval=False):
    """Sanctioned initial-state fixture: a real War placed in a canonical group."""
    ws = state.get_war_system()
    war = War(id=war_id, name=name, start_year=-270, threat_level=threat,
              naval_required=naval)
    if group == "active":
        war.status = WarStatus.ACTIVE
        ws._active_wars.append(war)
    elif group == "threat":
        war.status = WarStatus.THREAT
        ws._threats.append(war)
    elif group == "truce":
        war.status = WarStatus.TRUCE
        ws._truce_wars.append(war)
    else:  # pragma: no cover
        raise AssertionError(group)
    return war


def test_war_list_missing_military_source_fails_closed():
    """F1: a genuinely missing canonical military source must fail closed with a
    typed ``system_unavailable`` shell for every route (list/filter/detail) —
    NEVER a fabricated-zero success summary, and no retained content."""
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "Punic War")

    for filter_text, record_id in (("", ""), ("punic", ""), ("", "w1")):
        with patch.object(state, "get_military_system", return_value=None):
            result = gui_query_api.get_global_query_result(
                state, viewer_id, "war_list", filter_text, record_id)
        assert not result["success"], (filter_text, record_id)
        assert result["data"]["result_state"] == "ERROR"
        assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]
        assert result["data"]["items"] == []
        assert result["data"]["summary"] == {}
        assert result["data"]["detail"] is None


def test_war_list_missing_naval_source_fails_closed():
    """F1: a genuinely missing canonical naval source must fail closed with a
    typed ``system_unavailable`` shell for every route (list/filter/detail) —
    never a fabricated-zero fleet-strength success summary."""
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "Punic War", naval=True)

    for filter_text, record_id in (("", ""), ("punic", ""), ("", "w1")):
        with patch.object(gui_query_api, "_get_naval_system", return_value=None):
            result = gui_query_api.get_global_query_result(
                state, viewer_id, "war_list", filter_text, record_id)
        assert not result["success"], (filter_text, record_id)
        assert result["data"]["result_state"] == "ERROR"
        assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]
        assert result["data"]["items"] == []
        assert result["data"]["summary"] == {}
        assert result["data"]["detail"] is None


def test_war_list_present_source_legitimate_zero_is_not_missing():
    """A real, present canonical source that legitimately reports ZERO assigned
    legions/fleets stays a SUCCESS with numeric 0 values (§6.2: a real 0 is
    distinguishable from a missing source)."""
    state, viewer_id = _setup_state()
    _add_active_war(state, "w1", "No Fleet War")  # real present sources, zero assigned

    result, dto = _data(state, viewer_id, "war_list", "", "")
    assert result["success"]
    assert dto["result_state"] == "OK"
    entry = next(w for w in dto["summary"]["wars"] if w["id"] == "w1")
    assert entry["legions_assigned"] == 0
    assert entry["assigned_fleet_count"] == 0
    assert entry["fleets_assigned"] == 0
    assert entry["naval_ready"] is False
    assert entry["fleet_nominal_strength"] == 0
    assert entry["assigned_fleet_ids"] == []


def test_war_list_items_sorted_by_string_id_ascending():
    """F2 (§5.3): war ``id`` is a string selector — items and summary.wars are
    published in exact codepoint id ascending order, across groups AND within a
    group, independent of the (grouped/source) build order and of search."""
    state, viewer_id = _setup_state()
    ws = state.get_war_system()
    # deliberately nonascending ids ACROSS groups and WITHIN the active group
    _add_war_to_group(state, "zulu", "Zulu", "active")
    _add_war_to_group(state, "mike", "Mike", "active")
    _add_war_to_group(state, "alpha", "Alpha", "threat")
    _add_war_to_group(state, "Bravo", "Bravo", "truce")

    source_order = [
        w.id for w in (
            ws.get_active_wars() + ws.get_threat_wars() + ws.get_truce_wars()
        )
    ]
    expected = sorted(source_order)  # exact codepoint ascending
    assert source_order != expected, "fixture must be non-vacuous (source order unsorted)"

    result, dto = _data(state, viewer_id, "war_list", "", "")
    assert result["success"]
    assert [it["record_id"] for it in dto["items"]] == expected
    assert [w["id"] for w in dto["summary"]["wars"]] == expected

    # a filtered list preserves the same ascending order (independent of search)
    _result, filtered = _data(state, viewer_id, "war_list", "a", "")
    f_ids = [it["record_id"] for it in filtered["items"]]
    assert f_ids == ["Bravo", "alpha"], f_ids
    assert f_ids == sorted(f_ids)
