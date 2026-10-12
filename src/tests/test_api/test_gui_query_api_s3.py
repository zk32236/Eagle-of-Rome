"""EOR20261011-01 S3 — game_status / public_land / help DTO contracts.

Frozen authority (G3 v1.5 → v1.4 → v1.3 → v1.1):
  * SA v1.1 §5.3 capabilities / selector grammar;
  * SA v1.1 §6.2 per-viewer field allowlist (V public / V OWN-only / U-H absent).

DATA-class acceptance. Production read seam =
``gui_query_api.get_global_query_result``; the canonical public-land read model
is ``game_api.get_public_land_info``. No helper/shortcut entry; every case drives
the public seam with a sanctioned prototype session.
"""
import json
import os
import random
import sys
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import gui_query_api, game_api, session_api

S3_QUERIES = ("game_status", "public_land", "help")

# §6.2 game_status V-public summary field set (exact).
GAME_STATUS_SUMMARY_KEYS = {
    "year", "turn", "current_phase", "current_phase_id", "current_player_id",
    "treasury", "living_count", "faction_count", "players_overview",
}
PLAYERS_OVERVIEW_KEYS = {"player_id", "faction_id", "player_type", "is_current"}

# §6.2 public_land V-public summary field set (exact, ordered).
PUBLIC_LAND_FIELDS = [
    "national_land", "land_price", "value", "tax_rate", "annual_income", "treasury",
]
PUBLIC_LAND_ITEM_LABELS = [
    "query.public_land.national_land",
    "query.public_land.land_price",
    "query.public_land.value",
    "query.public_land.tax_rate",
    "query.public_land.annual_income",
    "query.public_land.treasury",
]

# §6.2 help guidance ids + their i18n keys.
HELP_GUIDE_IDS = ("usage", "filter", "detail", "back", "close", "readonly")

# Forbidden keys anywhere in an S3 DTO (U fields / private / national aggregates).
FORBIDDEN_DTO_KEYS = {
    "is_online", "accounts", "national_totals", "global_totals",
    "own_faction_totals", "landowners", "treasury_delta",
}
# Forbidden copy in the help surface (no executable debug/force/CLI guidance).
FORBIDDEN_HELP_STRINGS = ("debug", "force", "cli", "exec", "sudo", "shell", "debug_cli")


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _data(state, viewer_id, query_id, filter_text="", record_id=""):
    result = gui_query_api.get_global_query_result(
        state, viewer_id, query_id, filter_text, record_id
    )
    return result, result["data"]


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


# ===========================================================================
# game_status — AC-01 (current game public fields / player overview §6)
# ===========================================================================
def test_game_status_scalar_public_field_matrix():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "game_status")

    assert result["success"]
    assert dto["id"] == "game_status"
    assert dto["result_state"] == "OK"
    assert dto["status"] == "connected"
    assert dto["capabilities"] == {"can_filter": False, "can_detail": False}
    # exact §6.2 public summary field set + players_overview element shape
    assert set(dto["summary"].keys()) == GAME_STATUS_SUMMARY_KEYS
    for entry in dto["summary"]["players_overview"]:
        assert set(entry.keys()) == PLAYERS_OVERVIEW_KEYS
    # item label order frozen
    assert [it["label_key"] for it in dto["items"]] == [
        "query.item.year", "query.item.turn", "query.item.current_phase",
        "query.item.current_player", "query.item.treasury",
        "query.item.living_members", "query.item.factions",
    ]
    # U field is_online is ABSENT everywhere (recursive)
    assert "is_online" not in _all_keys(dto)
    assert "is_online" not in " ".join(_all_strings(dto))


def test_game_status_scalar_rejects_filter_and_record():
    state, viewer_id = _setup_state()

    r1, d1 = _data(state, viewer_id, "game_status", "x", "")
    assert not r1["success"]
    assert [e["code"] for e in d1["errors"]] == ["invalid_request"]

    r2, d2 = _data(state, viewer_id, "game_status", "", "1")
    assert not r2["success"]
    assert [e["code"] for e in d2["errors"]] == ["invalid_request"]


# ===========================================================================
# public_land — AC-05 (canonical public-land snapshot incl. existing price)
# ===========================================================================
def test_public_land_snapshot_fields_and_canonical_parity():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "public_land")

    assert result["success"]
    assert dto["id"] == "public_land"
    assert dto["result_state"] == "OK"
    assert dto["capabilities"] == {"can_filter": False, "can_detail": False}
    assert [it["label_key"] for it in dto["items"]] == PUBLIC_LAND_ITEM_LABELS
    assert list(dto["summary"].keys()) == PUBLIC_LAND_FIELDS

    canonical = game_api.get_public_land_info(state)["data"]
    for field in PUBLIC_LAND_FIELDS:
        assert dto["summary"][field] == canonical[field], field

    # values rendered as localized label + value (non-blank)
    for it in dto["items"]:
        assert it["value"].strip() != "", it["label_key"]
    # the existing snapshot price is PRESENT (reading it is not the OUT/DEFER
    # standalone price capability)
    assert dto["summary"]["land_price"] == canonical["land_price"]


def test_public_land_scalar_rejects_filter_and_record():
    state, viewer_id = _setup_state()

    r1, d1 = _data(state, viewer_id, "public_land", "x", "")
    assert not r1["success"]
    assert [e["code"] for e in d1["errors"]] == ["invalid_request"]

    r2, d2 = _data(state, viewer_id, "public_land", "", "1")
    assert not r2["success"]
    assert [e["code"] for e in d2["errors"]] == ["invalid_request"]


def test_public_land_fail_closed_when_source_unavailable():
    state, viewer_id = _setup_state()

    # canonical read model reports failure / data=None -> system_unavailable
    for bad in ({"success": False, "data": None}, {"success": True, "data": None}):
        with patch.object(game_api, "get_public_land_info", return_value=bad):
            result, dto = _data(state, viewer_id, "public_land")
        assert not result["success"]
        assert dto["result_state"] == "ERROR"
        assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
        assert dto["items"] == [] and dto["summary"] == {}

    # missing canonical component -> system_unavailable (never a fabricated zero)
    partial = {"success": True, "data": {
        "national_land": 100, "land_price": 10, "value": 1000,
        "tax_rate": 0.02, "annual_income": 20, "treasury": None,
    }}
    with patch.object(game_api, "get_public_land_info", return_value=partial):
        result, dto = _data(state, viewer_id, "public_land")
    assert not result["success"]
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]


def test_public_land_no_national_private_aggregate():
    state, viewer_id = _setup_state()

    _result, dto = _data(state, viewer_id, "public_land")

    assert not (set(_all_keys(dto)) & {"national_totals", "global_totals",
                                       "own_faction_totals", "landowners"})


# ===========================================================================
# help — AC-12 (categories + read-only guidance; no executable debug/force)
# ===========================================================================
def test_help_categories_and_readonly_guidance():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "help")

    assert result["success"]
    assert dto["id"] == "help"
    assert dto["result_state"] == "OK"
    assert dto["capabilities"] == {"can_filter": False, "can_detail": False}
    # the canonical twelve categories are listed (label = the query title key)
    labels = [it["label_key"] for it in dto["items"]]
    for qid in gui_query_api.CANONICAL_QUERY_IDS:
        assert ("query." + qid + ".title") in labels, qid
    # read-only operation guidance present (topic label + instruction value key)
    for gid in HELP_GUIDE_IDS:
        assert ("query.help.guide." + gid) in labels, gid
    guides = [it for it in dto["items"] if it["label_key"].startswith("query.help.guide.")
              and it.get("value_key")]
    assert len(guides) == len(HELP_GUIDE_IDS)
    for it in guides:
        assert it["value_key"] == it["label_key"] + ".value"
    assert dto["summary"]["categories"] == list(gui_query_api.CANONICAL_QUERY_IDS)
    assert dto["summary"]["guide_count"] == len(HELP_GUIDE_IDS)


def test_help_has_no_debug_or_force_commands():
    state, viewer_id = _setup_state()

    _result, dto = _data(state, viewer_id, "help")

    blob = " ".join(_all_strings(dto)).lower()
    for forbidden in FORBIDDEN_HELP_STRINGS:
        assert forbidden not in blob, forbidden


def test_help_scalar_rejects_filter_and_record():
    state, viewer_id = _setup_state()

    r1, d1 = _data(state, viewer_id, "help", "x", "")
    assert not r1["success"]
    assert [e["code"] for e in d1["errors"]] == ["invalid_request"]

    r2, d2 = _data(state, viewer_id, "help", "", "1")
    assert not r2["success"]
    assert [e["code"] for e in d2["errors"]] == ["invalid_request"]


# ===========================================================================
# Cross-cutting — viewer independence + recursive leak + read-only invariant
# ===========================================================================
def test_s3_public_scalars_are_viewer_independent():
    """game_status / public_land / help are PUBLIC views: every eligible viewer
    receives the identical DTO (no per-viewer variation, no OWN-only block)."""
    state, _ = _setup_state()
    viewers = _eligible_viewers(state)
    assert len(viewers) >= 2

    for query_id in S3_QUERIES:
        dtos = []
        for viewer in viewers:
            result, dto = _data(state, viewer.player_id, query_id)
            assert result["success"], (query_id, viewer.player_id)
            dtos.append(dto)
        assert all(d == dtos[0] for d in dtos), query_id


def test_s3_recursive_dto_leak_probe():
    state, viewer_id = _setup_state()

    for query_id in S3_QUERIES:
        _result, dto = _data(state, viewer_id, query_id)
        assert not (set(_all_keys(dto)) & FORBIDDEN_DTO_KEYS), query_id
        blob = " ".join(_all_strings(dto))
        assert "is_online" not in blob, query_id


def test_s3_readonly_invariant_core_and_rng():
    state, viewer_id = _setup_state()
    rng_before = random.getstate()

    def snapshot():
        return {
            "turn": state.turn.turn_number,
            "year": state.turn.year,
            "treasury": state.treasury,
            "national_land": state.get_national_public_land(),
            "phases": {p: state.is_phase_executed(p) for p in [
                "mortality", "revenue", "forum", "population", "senate",
                "combat", "resolution",
            ]},
        }

    before = snapshot()
    for query_id in S3_QUERIES:
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "")
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "a", "")
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "1")
    after = snapshot()

    assert after == before
    assert random.getstate() == rng_before


def test_s3_queries_reject_invalid_viewer():
    state, _ = _setup_state()

    for query_id in S3_QUERIES:
        result = gui_query_api.get_global_query_result(state, "missing_player", query_id)
        assert not result["success"], query_id
        assert result["data"]["result_state"] == "DENIED", query_id


# ===========================================================================
# i18n parity — the S3 keys exist (and are non-empty) in BOTH locales
# ===========================================================================
S3_I18N_KEYS = (
    ["query.public_land.message"] + PUBLIC_LAND_ITEM_LABELS
    + ["query.help.message"]
    + ["query.help.guide." + gid for gid in HELP_GUIDE_IDS]
    + ["query.help.guide." + gid + ".value" for gid in HELP_GUIDE_IDS]
)


def test_s3_i18n_keys_present_in_both_locales():
    for locale in ("zh-CN", "en-US"):
        path = os.path.join(PROJECT_ROOT, "data", "i18n", f"{locale}.json")
        with open(path, encoding="utf-8-sig") as fh:
            catalog = json.load(fh)
        for key in S3_I18N_KEYS:
            assert key in catalog, (locale, key)
            assert str(catalog[key]) != "", (locale, key)


# ===========================================================================
# F1 (ATTEMPT-2) — a missing canonical game-status source must fail closed
# (frozen SA v1.1 §6.2): typed ``system_unavailable``, NEVER a fabricated zero.
# ===========================================================================
def test_game_status_missing_turn_source_fails_closed():
    state, viewer_id = _setup_state()
    with patch.object(type(state), "turn", None):
        result, dto = _data(state, viewer_id, "game_status")
    assert not result["success"]
    assert dto["result_state"] == "ERROR"
    assert dto["status"] == "error"
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
    # No fabricated zero and no retained content in the failure shell.
    assert dto["items"] == []
    assert dto["summary"] == {}
    assert dto["detail"] is None


def test_game_status_missing_year_or_turn_number_fails_closed():
    state, viewer_id = _setup_state()

    class _TurnMissingYear:
        year = None
        turn_number = 7

        def get_year_display(self):
            return "?"

    class _TurnMissingNumber:
        year = -100
        turn_number = None

        def get_year_display(self):
            return "100 BC"

    for stub in (_TurnMissingYear(), _TurnMissingNumber()):
        with patch.object(type(state), "turn", stub):
            result, dto = _data(state, viewer_id, "game_status")
        assert not result["success"]
        assert dto["result_state"] == "ERROR"
        assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
        assert dto["items"] == [] and dto["summary"] == {}


def test_game_status_legitimate_numeric_zero_is_not_missing():
    """A legitimate numeric 0 year/turn must stay a SUCCESS (§6.2): a real 0 is
    distinguishable from a missing source."""
    state, viewer_id = _setup_state()

    class _ZeroTurn:
        year = 0
        turn_number = 0

        def get_year_display(self):
            return "0 AD"

    with patch.object(type(state), "turn", _ZeroTurn()):
        result, dto = _data(state, viewer_id, "game_status")
    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["summary"]["year"] == 0
    assert dto["summary"]["turn"] == 0


# ===========================================================================
# N1 (ATTEMPT-2) — a failed canonical producer is never recast as success
# ===========================================================================
def test_public_land_failed_result_with_data_fails_closed():
    state, viewer_id = _setup_state()
    bad = {"success": False, "message": "producer failure", "data": {
        "national_land": 100, "land_price": 10, "value": 1000,
        "tax_rate": 0.02, "annual_income": 20, "treasury": 5,
    }}
    with patch.object(game_api, "get_public_land_info", return_value=bad):
        result, dto = _data(state, viewer_id, "public_land")
    assert not result["success"]
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
    assert dto["items"] == [] and dto["summary"] == {}


def test_public_land_missing_success_flag_fails_closed():
    state, viewer_id = _setup_state()
    no_flag = {"data": {
        "national_land": 100, "land_price": 10, "value": 1000,
        "tax_rate": 0.02, "annual_income": 20, "treasury": 5,
    }}
    with patch.object(game_api, "get_public_land_info", return_value=no_flag):
        result, dto = _data(state, viewer_id, "public_land")
    assert not result["success"]
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["system_unavailable"]
