"""EOR20261011-01 S2 — faction_info / faction_treasury / private_land DTO contracts.

Frozen authority (G3 v1.5 → v1.4 → v1.3 → v1.1):
  * SA v1.1 §5.3 capabilities / selector grammar;
  * SA v1.1 §6.2 per-viewer field allowlist (V public / V OWN-only / U-H absent).

DATA-class acceptance. Production read seam =
``gui_query_api.get_global_query_result``. No helper/shortcut entry; every case
drives the public seam with a sanctioned prototype session.
"""
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import gui_query_api, session_api

# SA v1.2 §4 faction_info matrix (replaces the superseded v1.1 restriction):
# public = id,name,is_viewer_faction,member_count,total_influence (ALL active
# factions); OWN-only = treasury + individual member roster.
FACTION_PUBLIC_LABELS = {
    "query.faction.id", "query.faction.name", "query.faction.is_viewer",
    "query.faction.member_count", "query.faction.total_influence",
}
FACTION_OWN_LABELS = {"query.faction.treasury", "query.faction.member"}

# §6.2 private_land: OWN-only per-record columns (CLI status_private_land order).
PRIVATE_LAND_COLUMNS = ["col_id", "col_name", "col_land", "col_value", "col_income", "col_wealth"]

S2_QUERIES = ("faction_info", "faction_treasury", "private_land")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _rng_isolated():
    """Restore the process RNG state after each test (suite determinism):
    these tests build real sessions which draw from ``random``."""
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


def _other_eligible_viewer(state, faction_id):
    for player in _eligible_viewers(state):
        if player.faction_id and player.faction_id != faction_id:
            return player
    raise AssertionError("no eligible viewer with a different faction")


def _own_figure(state, faction_id):
    return next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)


def _foreign_figure(state, faction_id):
    return next(fig for fig in state.get_living_members()
                if fig.faction_id and fig.faction_id != faction_id)


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


# ===========================================================================
# faction_info — AC-02 (§6.2 public identity / own-only detail)
# ===========================================================================
def test_faction_info_own_detail_public_plus_own_fields():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    faction = state.get_faction(viewer_faction_id)

    result, dto = _data(state, viewer_id, "faction_info", "", viewer_faction_id)

    assert result["success"]
    assert dto["result_state"] == "OK"
    labels = _detail_labels(dto)
    assert FACTION_PUBLIC_LABELS.issubset(labels)
    assert FACTION_OWN_LABELS.issubset(labels)
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    members = faction.get_members(state)
    assert by_label["query.faction.treasury"]["value"] == "%s T" % faction.treasury
    assert by_label["query.faction.member_count"]["value"] == str(len(members))
    assert by_label["query.faction.total_influence"]["value"] == str(
        sum(m.influence for m in members))


def test_faction_info_other_detail_public_identity_only():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    other_faction_id = _other_eligible_viewer(state, viewer_faction_id).faction_id

    result, dto = _data(state, viewer_id, "faction_info", "", other_faction_id)

    assert result["success"]
    labels = set(_detail_labels(dto))
    # v1.2 §4: an OTHER faction exposes the public set (incl. member_count /
    # total_influence) and NONE of the OWN-only rows.
    assert labels == FACTION_PUBLIC_LABELS
    assert not (FACTION_OWN_LABELS & labels)
    assert "query.faction.member" not in labels
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.faction.member_count"]["value"] == str(
        len(state.get_faction(other_faction_id).get_members(state)))


def test_faction_info_member_rows_use_i18n_keys_not_raw_enum():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id

    _result, dto = _data(state, viewer_id, "faction_info", "", viewer_faction_id)

    members = [f for f in dto["detail"]["fields"] if f["label_key"] == "query.faction.member"]
    assert members
    for field in members:
        # no raw office enum / hardcoded Chinese in the rendered value
        assert field["value"] == ""
        if field["value_key"].startswith("query.office."):
            assert field["value_key"] in {
                "query.office.consul", "query.office.censor", "query.office.praetor",
                "query.office.quaestor", "query.office.tribune", "query.office.proconsul",
                "query.office.propraetor", "query.office.dictator",
            } or field["value_key"] == "query.value.faction_member_leader"


def test_faction_info_public_counts_and_influence_parity():
    """SA v1.2 §4/§107: member_count + total_influence are V-public for ALL active
    factions (positive cross-faction parity against the live aggregate source)."""
    state, viewer_id = _setup_state()

    _result, dto = _data(state, viewer_id, "faction_info", "", "")

    expected = {}
    for faction in state.get_active_factions():
        members = faction.get_members(state)
        expected[faction.id] = (faction.name, len(members),
                                sum(m.influence for m in members))

    summary_by_id = {f["id"]: f for f in dto["summary"]["factions"]}
    assert set(summary_by_id) == set(expected)
    for fid, (name, count, influence) in expected.items():
        entry = summary_by_id[fid]
        assert entry["name"] == name
        assert entry["member_count"] == count
        assert entry["total_influence"] == influence

    member_rows = [i for i in dto["items"] if i["label_key"] == "query.item.members"]
    influence_rows = [i for i in dto["items"]
                      if i["label_key"] == "query.item.influence"]
    assert len(member_rows) == len(expected)
    assert len(influence_rows) == len(expected)
    assert sorted(int(i["value"]) for i in influence_rows) == sorted(
        influence for (_n, _c, influence) in expected.values())


def test_faction_info_other_faction_has_public_counts_but_no_treasury():
    """SA v1.2 §4: other/unowned factions DO expose the public aggregates
    (member_count + total_influence) but never treasury / member roster."""
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id

    _result, dto = _data(state, viewer_id, "faction_info", "", "")

    for entry in dto["summary"]["factions"]:
        if entry["id"] == viewer_faction_id:
            continue
        assert "member_count" in entry
        assert "total_influence" in entry
        assert "treasury" not in entry
        assert "members" not in entry

    id_rows = [i for i in dto["items"]
               if i["label_key"] in ("query.item.faction", "query.item.public_faction")
               and i["meta"].get("faction_id") != viewer_faction_id]
    assert id_rows
    for item in id_rows:
        assert item["value"] == state.get_faction(item["meta"]["faction_id"]).name


def test_faction_info_recursive_foreign_private_leak_probe():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, viewer_faction_id)
    foreign_fig = _foreign_figure(state, viewer_faction_id)

    other_faction = state.get_faction(other.faction_id)
    other_faction.treasury = 555001
    foreign_fig.wealth = 888003
    foreign_fig.popularity = 999004

    # Full list as the viewer: no foreign treasury / individual private values.
    _result, list_dto = _data(state, viewer_id, "faction_info", "", "")
    blob = " ".join(_all_strings(list_dto))
    assert "555001" not in blob
    assert "888003" not in blob
    assert "999004" not in blob

    # Foreign faction detail as the viewer: public set + public aggregates only;
    # no individual private sentinel, no treasury and no member roster.
    _result, foreign_dto = _data(state, viewer_id, "faction_info", "", other.faction_id)
    foreign_blob = " ".join(_all_strings(foreign_dto))
    for sentinel in ("555001", "888003", "999004"):
        assert sentinel not in foreign_blob, sentinel
    foreign_labels = set(_detail_labels(foreign_dto))
    assert "query.faction.treasury" not in foreign_labels
    assert "query.faction.member" not in foreign_labels
    # The foreign faction's PUBLIC total_influence aggregate IS present (v1.2 §4
    # V-public) and equals the canonical live aggregate.
    by_label = {f["label_key"]: f for f in foreign_dto["detail"]["fields"]}
    assert by_label["query.faction.total_influence"]["value"] == str(
        sum(m.influence for m in other_faction.get_members(state)))


def test_faction_info_filter_restricts_and_selector_returns_detail():
    state, viewer_id = _setup_state()
    factions = state.get_active_factions()
    target = factions[0]

    _result, filtered = _data(state, viewer_id, "faction_info", target.name[:3], "")
    assert filtered["filters"]["applied"] == target.name[:3].casefold()
    for item in filtered["items"]:
        fid = item["meta"].get("faction_id")
        if fid:
            assert target.name[:3].casefold() in state.get_faction(fid).name.casefold()

    # F2: the selectable faction IDENTITY row publishes a nonempty record_id;
    # driving the frozen (id, "", record_id) chain opens that faction's detail.
    id_rows = [i for i in filtered["items"]
               if i["label_key"] in ("query.item.faction", "query.item.public_faction")]
    assert id_rows
    for row in id_rows:
        assert row["record_id"] != ""
        assert row["record_id"] == row["meta"]["faction_id"]
        detail_result, detail_dto = _data(
            state, viewer_id, "faction_info", "", row["record_id"])
        assert detail_result["success"]
        assert detail_dto["detail"]["record_id"] == row["record_id"]

    _result, empty = _data(state, viewer_id, "faction_info", "zzz-no-match", "")
    assert empty["result_state"] == "EMPTY"
    assert empty["items"] == []
    assert empty["filters"]["applied"] == "zzz-no-match".casefold()


def test_faction_info_absent_selector_is_record_denied():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "faction_info", "", "no-such-faction")

    assert not result["success"]
    assert dto["result_state"] == "DENIED"
    assert [e["code"] for e in dto["errors"]] == ["record_unavailable"]
    assert dto["detail"] is None
    assert dto["items"] == []


def test_faction_info_viewer_matrix_own_vs_other():
    state, _ = _setup_state()
    for viewer in _eligible_viewers(state):
        viewer_faction_id = viewer.faction_id
        _result, dto = _data(state, viewer.player_id, "faction_info", "", "")
        for entry in dto["summary"]["factions"]:
            # v1.2 §4: public aggregates for every faction; treasury is OWN-only.
            assert "member_count" in entry and "total_influence" in entry, viewer.player_id
            if entry["id"] == viewer_faction_id:
                assert "treasury" in entry, viewer.player_id
            else:
                assert "treasury" not in entry, viewer.player_id


def test_faction_info_list_order_is_exact_id_ascending():
    """SA11 §5.3 / SA v1.2: the faction list order is exact faction.id ascending
    (codepoint) for EVERY viewer — no owner-first bias (F3)."""
    state, _ = _setup_state()
    for viewer in _eligible_viewers(state):
        _result, dto = _data(state, viewer.player_id, "faction_info", "", "")
        ids = [f["id"] for f in dto["summary"]["factions"]]
        assert ids == sorted(ids), (viewer.player_id, ids)
        row_ids = [i["record_id"] for i in dto["items"]
                   if i["label_key"] in ("query.item.faction", "query.item.public_faction")]
        assert row_ids == sorted(row_ids), (viewer.player_id, row_ids)


# ===========================================================================
# faction_treasury — AC-04 (own amount only, no accounts)
# ===========================================================================
def test_faction_treasury_own_amount_only():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    faction = state.get_faction(viewer_faction_id)

    result, dto = _data(state, viewer_id, "faction_treasury", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["status"] == "readonly"
    assert dto["capabilities"] == {"can_filter": False, "can_detail": False}
    assert dto["summary"]["viewer_faction_id"] == viewer_faction_id
    assert dto["summary"]["viewer_faction_name"] == faction.name
    assert dto["summary"]["treasury"] == faction.treasury
    values = [item["value"] for item in dto["items"]]
    assert "%s T" % faction.treasury in values
    assert faction.name in values


def test_faction_treasury_no_accounts_recursive():
    state, viewer_id = _setup_state()

    _result, dto = _data(state, viewer_id, "faction_treasury", "", "")

    assert "accounts" not in _all_keys(dto)
    assert "accounts" not in " ".join(_all_strings(dto))


def test_faction_treasury_scalar_rejects_filter_and_record():
    state, viewer_id = _setup_state()

    r1, d1 = _data(state, viewer_id, "faction_treasury", "x", "")
    assert not r1["success"]
    assert [e["code"] for e in d1["errors"]] == ["invalid_request"]

    r2, d2 = _data(state, viewer_id, "faction_treasury", "", "1")
    assert not r2["success"]
    assert [e["code"] for e in d2["errors"]] == ["invalid_request"]


# ===========================================================================
# private_land — AC-06 (own records + own totals; national totals absent)
# ===========================================================================
def _set_land(fig, land):
    """Sanctioned initial-state fixture: give a figure private land.

    ``Figure.land_private`` is a read-only property over ``_land_private``;
    setting the backing field is fixture setup only (never an acceptance entry).
    """
    fig._land_private = int(land)
    return fig


def _make_own_landowner(state, faction_id, land=7, wealth=1234):
    fig = _own_figure(state, faction_id)
    _set_land(fig, land)
    fig.wealth = wealth
    return fig


def test_private_land_own_records_only():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    own = _make_own_landowner(state, viewer_faction_id, land=7)
    foreign = _foreign_figure(state, viewer_faction_id)
    _set_land(foreign, 9)

    result, dto = _data(state, viewer_id, "private_land", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}
    own_ids = {str(fig.id) for fig in state.get_living_members()
               if fig.faction_id == viewer_faction_id and fig.land_private > 0}
    returned = {item["record_id"] for item in dto["items"]}
    assert returned == own_ids
    assert str(own.id) in returned
    assert str(foreign.id) not in returned


def test_private_land_totals_are_viewer_faction_scope():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7, wealth=1234)
    land_price = state.get_economic_rule("land_price_per_unit", 10)

    _result, dto = _data(state, viewer_id, "private_land", "", "")

    totals = dto["summary"]["own_faction_totals"]
    assert totals["scope"] == "viewer_faction"
    assert totals["faction_id"] == viewer_faction_id
    assert totals["land"] == sum(f.land_private for f in state.get_living_members()
                                 if f.faction_id == viewer_faction_id and f.land_private > 0)
    assert totals["value"] == totals["land"] * land_price


def test_private_land_national_totals_absent_recursive():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7)
    _set_land(_foreign_figure(state, viewer_faction_id), 9)

    _result, dto = _data(state, viewer_id, "private_land", "", "")

    # only the viewer-scoped totals block; no national/global totals key.
    assert set(dto["summary"].keys()) == {"viewer_faction_id", "own_faction_totals"}
    assert "totals" not in dto["summary"]
    assert not (set(_all_keys(dto)) & {"national_totals", "global_totals"})


def test_private_land_recursive_foreign_leak_probe():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7)
    foreign = _foreign_figure(state, viewer_faction_id)
    _set_land(foreign, 424242)
    foreign.wealth = 313131

    _result, dto = _data(state, viewer_id, "private_land", "", "")
    blob = " ".join(_all_strings(dto))
    assert "424242" not in blob
    assert "313131" not in blob


def test_private_land_detail_own_and_selector():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    own = _make_own_landowner(state, viewer_faction_id, land=7, wealth=1234)

    result, dto = _data(state, viewer_id, "private_land", "", str(own.id))

    assert result["success"]
    assert dto["items"] == []
    assert dto["detail"]["record_id"] == str(own.id)
    labels = _detail_labels(dto)
    assert labels == ["query.private_land.id", "query.private_land.name",
                      "query.private_land.land", "query.private_land.value",
                      "query.private_land.annual_income", "query.private_land.wealth"]


def test_private_land_malformed_or_absent_selector_denied():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7)
    foreign = _foreign_figure(state, viewer_faction_id)
    _set_land(foreign, 9)

    for bad in ["0", "01", "-1", "1.5", "abc", " 1", "999999", str(foreign.id)]:
        result, dto = _data(state, viewer_id, "private_land", "", bad)
        assert not result["success"], bad
        assert dto["result_state"] == "DENIED", bad
        assert [e["code"] for e in dto["errors"]] == ["record_unavailable"], bad
        assert dto["detail"] is None


def test_private_land_filter_by_own_name():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    own = _make_own_landowner(state, viewer_faction_id, land=7)
    needle = own.get_formal_name()[:4]

    result, dto = _data(state, viewer_id, "private_land", needle, "")

    assert result["success"]
    assert dto["filters"]["field"] == "name"
    assert dto["filters"]["applied"] == needle.casefold()
    for item in dto["items"]:
        fid = int(item["record_id"])
        assert needle.casefold() in state.get_member(fid).get_formal_name().casefold()


def test_private_land_list_columns_schema():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7)

    _result, dto = _data(state, viewer_id, "private_land", "", "")

    assert [c["col_key"] for c in dto["columns"]] == PRIVATE_LAND_COLUMNS
    for col in dto["columns"]:
        assert "value" not in col and "value_key" not in col   # header = caption only
        assert col["align"] == "left"
        assert col["min_width_px"] >= 24
    for item in dto["items"]:
        assert [c["col_key"] for c in item["columns"]] == PRIVATE_LAND_COLUMNS


def test_private_land_viewer_matrix_own_faction_only():
    state, _ = _setup_state()
    for viewer in _eligible_viewers(state):
        fig = _own_figure(state, viewer.faction_id)
        _set_land(fig, 3)
        _result, dto = _data(state, viewer.player_id, "private_land", "", "")
        for item in dto["items"]:
            fid = int(item["record_id"])
            assert state.get_member(fid).faction_id == viewer.faction_id, viewer.player_id
        assert dto["summary"]["own_faction_totals"]["faction_id"] == viewer.faction_id


# ===========================================================================
# Cross-cutting — AC-15 / AC-19
# ===========================================================================
def test_s2_queries_fail_closed_no_placeholder():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "no_such_query", "", "")
    assert not result["success"]
    assert dto["result_state"] == "ERROR"
    assert [e["code"] for e in dto["errors"]] == ["unknown_query"]
    assert all(item.get("label_key") != "query.item.handoff" for item in dto["items"])


def test_s2_readonly_invariant_core_and_rng():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id
    _make_own_landowner(state, viewer_faction_id, land=7)
    rng_before = random.getstate()

    def snapshot():
        return {
            "turn": state.turn.turn_number,
            "year": state.turn.year,
            "treasury": state.treasury,
            "faction_treasuries": {f.id: f.treasury for f in state.get_active_factions()},
            "figures": {f.id: (f.influence, f.wealth, f.land_private)
                        for f in state.get_living_members()},
        }

    before = snapshot()
    for query_id in S2_QUERIES:
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "")
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "a", "")
    own = _own_figure(state, viewer_faction_id)
    gui_query_api.get_global_query_result(state, viewer_id, "faction_info", "", viewer_faction_id)
    gui_query_api.get_global_query_result(state, viewer_id, "private_land", "", str(own.id))
    after = snapshot()

    assert after == before
    assert random.getstate() == rng_before


def test_s2_queries_reject_invalid_viewer():
    state, _ = _setup_state()

    for query_id in S2_QUERIES:
        result = gui_query_api.get_global_query_result(state, "missing_player", query_id)
        assert not result["success"], query_id
        assert result["data"]["result_state"] == "DENIED", query_id
