import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import gui_query_api, session_api

# Foreign-private figure field label keys (hidden for OTHER/UNOWNED; v1.2 §4).
FIGURE_PRIVATE_LABELS = {
    "query.figure.influence",
    "query.figure.wealth",
    "query.figure.popularity",
    "query.figure.land_private",
    "query.figure.veterans",
    "query.figure.age",
    "query.figure.office_history",
}
FIGURE_PUBLIC_LABELS = {
    "query.figure.name",
    "query.figure.faction",
    "query.figure.class_tier",
    "query.figure.office",
    "query.figure.is_leader",
    "query.figure.is_dead",
}

# Owner-ordered 21-row OWN detail table (SA13 §5 / FC-18).
OWN_DETAIL_ORDER = [
    "query.figure.name",
    "query.figure.faction",
    "query.figure.class_tier",
    "query.figure.family",
    "query.figure.age",
    "query.figure.influence",
    "query.figure.rank",
    "query.figure.zeal",
    "query.figure.charisma",
    "query.figure.martial",
    "query.figure.intelligence",
    "query.figure.wealth",
    "query.figure.popularity",
    "query.figure.land_private",
    "query.figure.veterans",
    "query.figure.office",
    "query.figure.office_history",
    "query.figure.contracts",
    "query.figure.is_leader",
    "query.figure.is_dead",
    "query.figure.is_present",
]

# FOREIGN detail = PUBLIC_IDENTITY rows only, in the same relative order.
FOREIGN_DETAIL_ORDER = [
    "query.figure.name",
    "query.figure.faction",
    "query.figure.class_tier",
    "query.figure.office",
    "query.figure.is_leader",
    "query.figure.is_dead",
]

# CLI ``status_figure`` list column schema (PT-01), ordered.
OWN_LIST_COLUMNS = [
    "col_status", "col_class", "col_id", "col_name", "col_faction",
    "col_influence", "col_wealth", "col_popularity", "col_land",
    "col_veterans", "col_office",
]
FOREIGN_LIST_COLUMNS = [
    "col_status", "col_class", "col_id", "col_name", "col_faction", "col_office",
]


def _setup_state():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    return state, viewer_id


def _eligible_viewers(state):
    return [
        player for player in state.get_all_players()
        if player.player_type.value in ("human", "ai")
    ]


def _other_eligible_viewer(state, faction_id):
    for player in _eligible_viewers(state):
        if player.faction_id and player.faction_id != faction_id:
            return player
    raise AssertionError("no eligible viewer with a different faction")


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
# Existing real queries keep their public DTO shape
# ===========================================================================
def test_game_status_query_returns_public_snapshot():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "game_status")

    assert result["success"]
    data = result["data"]
    assert data["id"] == "game_status"
    assert data["result_state"] == "OK"
    assert data["status"] == "connected"
    assert data["title_key"] == "query.game_status.title"
    assert data["summary"]["current_phase_id"] == "mortality"
    assert any(item["label_key"] == "query.item.treasury" for item in data["items"])
    assert "is_online" not in data["summary"]
    assert all("is_online" not in str(item) for item in data["items"])


def test_faction_query_only_exposes_viewer_treasury():
    state, viewer_id = _setup_state()
    viewer_faction_id = state.get_player(viewer_id).faction_id

    result = gui_query_api.get_global_query_result(state, viewer_id, "faction_info")

    assert result["success"]
    data = result["data"]
    assert data["status"] == "readonly"
    factions = data["summary"]["factions"]
    assert any(f["id"] == viewer_faction_id and "treasury" in f for f in factions)
    assert all(
        "treasury" not in f
        for f in factions
        if f["id"] != viewer_faction_id
    )
    treasury_items = [item for item in data["items"] if item["label_key"] == "query.item.treasury"]
    assert len(treasury_items) == 1
    assert treasury_items[0]["meta"]["scope"] == "viewer_faction"


def test_war_list_query_uses_public_dto_shape():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "war_list")

    assert result["success"]
    data = result["data"]
    assert data["result_state"] in ("OK", "EMPTY")
    assert data["status"] in ("readonly", "empty")
    assert "wars" in data["summary"]
    assert "counts" in data["summary"]
    for war in data["summary"]["wars"]:
        assert {"id", "name", "status", "threat_level", "naval_required"}.issubset(war.keys())


def test_legion_status_query_returns_readonly_counts_without_mutation():
    state, viewer_id = _setup_state()
    before = {phase_id: state.is_phase_executed(phase_id) for phase_id in [
        "mortality", "revenue", "forum", "population", "senate", "combat", "resolution"
    ]}

    result = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")

    assert result["success"]
    data = result["data"]
    assert data["status"] == "readonly"
    assert data["summary"]["counts"]["total"] >= 1
    assert "legions" in data["summary"]
    after = {phase_id: state.is_phase_executed(phase_id) for phase_id in before}
    assert after == before


# ===========================================================================
# Fail-closed: no placeholder-as-success (rewrites the former placeholder test)
# ===========================================================================
def test_unhandled_query_fails_closed_without_placeholder():
    """A query with no canonical handler must fail closed.

    CS03B S4 TA-02: retargeted from ``contract_status`` (now a real S4 handler)
    to a non-canonical id, so the probe remains valid after every later slice.
    Fail-closed: no fake success, no ``query.item.handoff`` row, typed ERROR shell.
    """
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "no_such_query")

    assert not result["success"]
    data = result["data"]
    assert data["id"] == ""
    assert data["result_state"] == "ERROR"
    assert data["status"] == "error"
    assert data["items"] == []
    assert data["summary"] == {}
    assert data["detail"] is None
    assert data["capabilities"] == {"can_filter": False, "can_detail": False}
    assert data["filters"] is None
    assert all(item.get("label_key") != "query.item.handoff" for item in data["items"])
    assert [err["code"] for err in data["errors"]] == ["unknown_query"]


def test_unknown_query_is_typed_error_with_empty_id():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "not_a_query")

    assert not result["success"]
    data = result["data"]
    assert data["id"] == ""
    assert data["result_state"] == "ERROR"
    assert [err["code"] for err in data["errors"]] == ["unknown_query"]


def test_query_rejects_invalid_viewer():
    state, _ = _setup_state()

    result = gui_query_api.get_global_query_result(state, "missing_player", "game_status")

    assert not result["success"]
    assert "Viewer player not found" in result["message"]
    assert result["data"]["result_state"] == "DENIED"


def test_non_detail_query_with_record_id_is_invalid_request():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "game_status", "", "1")

    assert not result["success"]
    assert [err["code"] for err in result["data"]["errors"]] == ["invalid_request"]


# ===========================================================================
# figure_search — S1 target query
# ===========================================================================
def test_figure_search_lists_living_figures_only():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search")

    assert result["success"]
    data = result["data"]
    assert data["result_state"] in ("OK", "EMPTY")
    assert data["capabilities"] == {"can_filter": True, "can_detail": True}
    assert data["filters"]["field"] == "name"
    living_ids = {str(fig.id) for fig in state.get_living_members()}
    returned_ids = {item["record_id"] for item in data["items"]}
    assert returned_ids == living_ids
    for item in data["items"]:
        assert item["record_id"]
        assert item["label_key"] == "query.item.figure"


def test_figure_search_filter_restricts_to_matched_projected_names():
    state, viewer_id = _setup_state()
    figures = state.get_living_members()
    target = figures[0]
    needle = target.get_formal_name()[:4]

    result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", needle, "")

    assert result["success"]
    data = result["data"]
    expected = {
        str(fig.id) for fig in figures
        if needle.casefold() in fig.get_formal_name().casefold()
    }
    assert {item["record_id"] for item in data["items"]} == expected
    assert data["filters"]["applied"] == needle.casefold()


def test_figure_search_empty_filter_returns_full_visible_list():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "   ", "")

    assert result["success"]
    assert len(result["data"]["items"]) == len(state.get_living_members())


def test_figure_search_malformed_selector_is_denied_not_bypassed():
    state, viewer_id = _setup_state()

    for bad in ["", "0", "01", "-1", "1.5", "abc", " 1"]:
        result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", bad)
        # empty string means "no detail" -> list; skip that one
        if bad == "":
            continue
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED"
        assert [err["code"] for err in result["data"]["errors"]] == ["record_unavailable"]
        assert result["data"]["detail"] is None
        assert result["data"]["items"] == []


def test_figure_search_absent_id_is_denied():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "999999")

    assert not result["success"]
    assert result["data"]["result_state"] == "DENIED"
    assert [err["code"] for err in result["data"]["errors"]] == ["record_unavailable"]


def test_figure_search_detail_own_exposes_private_fields():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)

    result = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(own.id)
    )

    assert result["success"]
    data = result["data"]
    assert data["items"] == []
    assert data["detail"]["record_id"] == str(own.id)
    labels = {field["label_key"] for field in data["detail"]["fields"]}
    assert FIGURE_PUBLIC_LABELS.issubset(labels)
    assert FIGURE_PRIVATE_LABELS.issubset(labels)


def test_figure_search_detail_other_hides_private_fields():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, faction_id)
    foreign = next(fig for fig in state.get_living_members() if fig.faction_id == other.faction_id)

    result = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(foreign.id)
    )

    assert result["success"]
    labels = {field["label_key"] for field in result["data"]["detail"]["fields"]}
    assert FIGURE_PUBLIC_LABELS.issubset(labels)
    assert not (FIGURE_PRIVATE_LABELS & labels)


def test_figure_search_field_level_viewer_matrix():
    """For every living figure, private labels appear iff the figure is OWN."""
    state, _ = _setup_state()
    figures = state.get_living_members()

    for viewer in _eligible_viewers(state):
        for figure in figures:
            dto = gui_query_api.get_global_query_result(
                state, viewer.player_id, "figure_search", "", str(figure.id)
            )["data"]
            assert dto["result_state"] == "OK"
            labels = {field["label_key"] for field in dto["detail"]["fields"]}
            is_own = figure.faction_id == viewer.faction_id
            if is_own:
                assert FIGURE_PRIVATE_LABELS.issubset(labels), (viewer.player_id, figure.id)
            else:
                assert not (FIGURE_PRIVATE_LABELS & labels), (viewer.player_id, figure.id)


def test_figure_search_recursive_dto_foreign_private_leak_probe():
    """Distinctive sentinel values must not leak into ANY DTO layer."""
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, faction_id)

    own_fig = next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)
    foreign_fig = next(fig for fig in state.get_living_members() if fig.faction_id == other.faction_id)
    own_fig.wealth = 123456
    own_fig.influence = 654321
    foreign_fig.wealth = 987654
    foreign_fig.influence = 111222

    # foreign detail as viewer: no foreign sentinel anywhere
    foreign_dto = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(foreign_fig.id)
    )["data"]
    foreign_strings = _all_strings(foreign_dto)
    assert "987654" not in foreign_strings
    assert "111222" not in foreign_strings
    assert not (FIGURE_PRIVATE_LABELS & {f["label_key"] for f in foreign_dto["detail"]["fields"]})

    # full list as viewer: no foreign sentinel anywhere either
    list_dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]
    list_strings = _all_strings(list_dto)
    assert "987654" not in list_strings
    assert "111222" not in list_strings

    # own detail DOES carry the own sentinel
    own_dto = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(own_fig.id)
    )["data"]
    own_strings = _all_strings(own_dto)
    assert "123456" in own_strings
    assert "654321" in own_strings


def test_figure_search_no_raw_entity_keys_leak():
    state, viewer_id = _setup_state()

    result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search")
    keys = set(_all_keys(result["data"]))

    forbidden_keys = {
        "wealth", "influence", "popularity", "land_private", "_land_private",
        "_influence", "veterans", "office_history", "loyalty", "corruption",
        "_contract_ids", "_has_active_contract", "to_dict",
    }
    assert not (forbidden_keys & keys)


def test_figure_search_readonly_invariant_core_and_rng():
    state, viewer_id = _setup_state()
    rng_before = random.getstate()

    def snapshot():
        return {
            "turn": state.turn.turn_number,
            "year": state.turn.year,
            "treasury": state.treasury,
            "phases": {p: state.is_phase_executed(p) for p in [
                "mortality", "revenue", "forum", "population", "senate", "combat", "resolution"
            ]},
            "figures": {
                fig.id: (fig.influence, fig.wealth, fig.popularity)
                for fig in state.get_living_members()
            },
        }

    before = snapshot()
    gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")
    gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "a", "")
    figures = state.get_living_members()
    gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", str(figures[0].id))
    for query_id in gui_query_api.CANONICAL_QUERY_IDS:
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "")
    after = snapshot()

    assert after == before
    assert random.getstate() == rng_before


# ===========================================================================
# F1 — full-string selector grammar + canonical source ID integrity
# ===========================================================================
def test_figure_search_selector_requires_exact_canonical_wire_form():
    state, viewer_id = _setup_state()
    own = next(fig for fig in state.get_living_members())

    ok = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", str(own.id))
    assert ok["success"]
    assert ok["data"]["detail"]["record_id"] == str(own.id)

    # Trailing newline (Python ``$`` would otherwise accept it), leading/trailing
    # space, sign and fractional forms must all fail closed identically.
    for bad in [f"{own.id}\n", f" {own.id}", f"{own.id} ", f"+{own.id}", f"{own.id}.0"]:
        result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", bad)
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED", bad
        assert [e["code"] for e in result["data"]["errors"]] == ["record_unavailable"], bad


def test_figure_search_duplicate_canonical_id_source_fails_query():
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    figures = list(state.get_living_members())
    duplicate = figures[0]
    with patch.object(state, "get_living_members", return_value=list(figures) + [duplicate]):
        result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search")
    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["query_failed"]


def test_figure_search_invalid_canonical_id_source_fails_query():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    figures = list(state.get_living_members())
    with patch.object(state, "get_living_members",
                      return_value=list(figures) + [SimpleNamespace(id=0)]):
        result = gui_query_api.get_global_query_result(state, viewer_id, "figure_search")
    assert not result["success"]
    assert [e["code"] for e in result["data"]["errors"]] == ["query_failed"]


def test_legion_duplicate_number_source_fails_query():
    from unittest.mock import patch
    state, viewer_id = _setup_state()
    military = state.get_military_system()
    legions = list(military.get_all_legions())
    if not legions:
        return
    with patch.object(military, "get_all_legions", return_value=list(legions) + [legions[0]]):
        result = gui_query_api.get_global_query_result(state, viewer_id, "legion_status")
    assert not result["success"]
    assert [e["code"] for e in result["data"]["errors"]] == ["query_failed"]


# ===========================================================================
# F7 — enum/bool display binds i18n keys (no hardcoded Chinese / raw enum)
# ===========================================================================
def test_enum_and_bool_display_values_bind_i18n_keys():
    state, viewer_id = _setup_state()
    gs = gui_query_api.get_global_query_result(state, viewer_id, "game_status")["data"]
    phase = next(i for i in gs["items"] if i["label_key"] == "query.item.current_phase")
    assert phase["value_key"] == "query.phase.mortality"

    faction_id = state.get_player(viewer_id).faction_id
    own = next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)
    dto = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(own.id)
    )["data"]
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.figure.is_leader"]["value_key"] in ("query.bool.yes", "query.bool.no")
    assert by_label["query.figure.is_dead"]["value_key"] in ("query.bool.yes", "query.bool.no")
    assert by_label["query.figure.class_tier"]["value_key"].startswith("query.figure.class_tier.")


def test_figure_rows_carry_localised_value_template():
    state, viewer_id = _setup_state()
    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search")["data"]
    for item in dto["items"]:
        assert item["value_key"] == "query.value.figure"
        assert item["value_params"]["class_tier"]["key"].startswith("query.figure.class_tier.")


def test_office_office_history_and_leader_use_i18n_keys():
    """F7: office enum, office-history list and faction member leader copy all
    bind i18n keys (no raw enum / hardcoded Chinese in any DTO layer)."""
    from src.core.entities.figure import OfficeTerm
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = next(fig for fig in state.get_living_members() if fig.faction_id == faction_id)
    own.office = "consul"
    own.is_faction_leader = True
    own.office_history = [OfficeTerm(office_type="quaestor", start_turn=1, end_turn=2)]

    dto = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(own.id)
    )["data"]
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}

    # office enum -> query.office.<enum>, rendered value blank (no raw enum)
    office_field = by_label["query.figure.office"]
    assert office_field["value_key"] == "query.office.consul"
    assert office_field["value"] == ""

    # office history -> explicit list of office key refs, never a joined enum
    hist = by_label["query.figure.office_history"]
    assert hist["value_key"] == "query.figure.office_history_value"
    offices = hist["value_params"]["offices"]
    assert offices and all(o["key"] == "query.value.office_term" for o in offices)
    assert all(o["office"]["key"].startswith("query.office.") for o in offices)
    assert all(o["year"] for o in offices)
    assert hist["value"] == ""

    # faction detail member copy: office + leader tag both keyed
    faction_dto = gui_query_api.get_global_query_result(
        state, viewer_id, "faction_info", "", faction_id
    )["data"]
    member_fields = [f for f in faction_dto["detail"]["fields"]
                     if f["label_key"] == "query.faction.member"]
    assert member_fields
    leader_field = next(f for f in member_fields if f["label"] == own.get_formal_name())
    assert leader_field["value_key"] == "query.value.faction_member_leader"
    params = leader_field["value_params"]
    assert params["office"]["key"] == "query.office.consul"
    assert params["leader"]["key"] == "query.value.leader"
    # No hardcoded player copy and no raw enum in the rendered value.
    assert leader_field["value"] == ""
    assert "领袖" not in leader_field["value"]


# ===========================================================================
# v1.3 — LIST = CLI status_figure column schema (PT-01), viewer-projected
# ===========================================================================
def _figure_by_id(state, record_id):
    return state.get_member(int(record_id))


def test_figure_list_columns_owner_schema_own_vs_foreign():
    """OWN rows carry the full 11-column CLI schema; FOREIGN rows carry only the
    public-identity columns (1,2,3,4,5,11); private columns are ABSENT."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]

    seen_own = False
    seen_foreign = False
    for item in dto["items"]:
        figure = _figure_by_id(state, item["record_id"])
        cols = [c["col_key"] for c in item["columns"]]
        if figure.faction_id == faction_id:
            seen_own = True
            assert cols == OWN_LIST_COLUMNS
        else:
            seen_foreign = True
            assert cols == FOREIGN_LIST_COLUMNS
            # No OWN_PRIVATE column key may appear anywhere for a foreign record.
            assert not (set(cols) & set(OWN_LIST_COLUMNS[5:10]))
    assert seen_own and seen_foreign, "expected both an OWN and a FOREIGN living record"


def test_figure_list_columns_not_truncated_full_values():
    """No cell is truncated: every cell carries the full source value and the
    schema declares a positive minimum width (no ellipsis marker)."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]

    for item in dto["items"]:
        figure = _figure_by_id(state, item["record_id"])
        for col in item["columns"]:
            assert col["min_width_px"] >= 24
            assert "elide" not in col and "truncated" not in col
            assert "…" not in col["value"] and "..." not in col["value"]
        name_cell = next(c for c in item["columns"] if c["col_key"] == "col_name")
        assert name_cell["value"] == figure.get_formal_name()
        id_cell = next(c for c in item["columns"] if c["col_key"] == "col_id")
        assert id_cell["value"] == str(figure.id)


def test_figure_list_foreign_has_no_private_values_recursively():
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, faction_id)
    foreign = next(f for f in state.get_living_members() if f.faction_id == other.faction_id)
    foreign.wealth = 246810
    foreign.influence = 135791
    foreign.age = 424242

    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]
    blob = " ".join(_all_strings(dto))
    assert "246810" not in blob
    assert "135791" not in blob
    assert "424242" not in blob


# ===========================================================================
# v1.3 — DETAIL = Owner-ordered field→value table (PT-02), viewer-projected
# ===========================================================================
def test_figure_detail_owner_order_21_rows_own():
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = next(f for f in state.get_living_members() if f.faction_id == faction_id)

    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", str(own.id))["data"]
    keys = [f["label_key"] for f in dto["detail"]["fields"]]
    assert keys == OWN_DETAIL_ORDER
    assert len(keys) == 21


def test_figure_detail_value_forms_match_cli():
    from src.api import gui_query_api
    from src.core.entities.figure import OfficeTerm
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = next(f for f in state.get_living_members() if f.faction_id == faction_id)
    own.office = "consul"
    own.family_prestige = 1
    own.office_history = [OfficeTerm(office_type="quaestor", start_turn=1, end_turn=2)]

    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", str(own.id))["data"]
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}

    # family(prestige) template
    fam = by_label["query.figure.family"]
    assert fam["value_key"] == "query.figure.family_value"
    assert fam["value_params"]["prestige"] == "1"
    # influence breakdown template + verbatim components
    inf = by_label["query.figure.influence"]
    assert inf["value_key"] == "query.figure.influence_value"
    p = inf["value_params"]
    assert p["total"] == str(own.influence)
    assert p["land"] == str(own.land_private * 10)
    assert p["vet"] == str(own.veterans * 10)
    assert p["pop"] == str(own.popularity)
    assert p["fam"] == str(own.family_prestige * 10)
    assert p["office"] == str(own.get_office_influence_bonus())
    # office history: office(year) per term
    hist = by_label["query.figure.office_history"]
    assert hist["value_params"]["offices"][0]["office"]["key"] == "query.office.quaestor"
    assert hist["value_params"]["offices"][0]["year"]
    # is-in-Rome uses the present flag (is_absent reversed)
    assert by_label["query.figure.is_present"]["value_key"] in ("query.bool.yes", "query.bool.no")


def test_figure_detail_foreign_public_rows_recursive_absence():
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, faction_id)
    foreign = next(f for f in state.get_living_members() if f.faction_id == other.faction_id)
    foreign.age = 777777
    foreign.zeal = 424242
    foreign.wealth = 888888
    foreign.add_contract(5150)

    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", str(foreign.id))["data"]
    keys = [f["label_key"] for f in dto["detail"]["fields"]]
    assert keys == FOREIGN_DETAIL_ORDER
    for private_key in set(OWN_DETAIL_ORDER) - set(FOREIGN_DETAIL_ORDER):
        assert private_key not in keys
    blob = " ".join(_all_strings(dto))
    for sentinel in ("777777", "424242", "888888", "5150"):
        assert sentinel not in blob, sentinel


# ===========================================================================
# v1.4 — LIST = TABLE: one header row (labels only) + value-only aligned rows
# ===========================================================================
# CLI ``status_figure`` header caption order (col 11 uses the short Office key).
V1_4_HEADER_LABEL_ORDER = [
    "query.figure.status",
    "query.figure.class_tier",
    "query.figure.id",
    "query.figure.name",
    "query.figure.faction",
    "query.figure.influence",
    "query.figure.wealth",
    "query.figure.popularity",
    "query.figure.land_private",
    "query.figure.veterans",
    "query.figure.office_short",
]


def test_figure_list_header_schema_cli_order_with_office_short():
    """The LIST exposes exactly one header schema: localized column captions in
    CLI order (col 11 = query.figure.office_short), labels ONLY (no values)."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]

    assert dto["result_state"] in ("OK", "EMPTY")
    cols = dto["columns"]
    assert [c["col_key"] for c in cols] == OWN_LIST_COLUMNS
    assert [c["label_key"] for c in cols] == V1_4_HEADER_LABEL_ORDER
    for col in cols:
        # Header cells carry a localized caption only - never a value payload.
        assert "value" not in col
        assert "value_key" not in col
        assert col["align"] == "left"          # CLI tabular parity
        assert col["min_width_px"] >= 24


def test_figure_list_header_absent_in_detail_empty_and_denied():
    """The header row exists iff list rows exist: absent in DETAIL/EMPTY/DENIED."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = next(f for f in state.get_living_members() if f.faction_id == faction_id)

    detail = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", str(own.id))["data"]
    assert detail["detail"] is not None
    assert detail["columns"] == []

    empty = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "zzz-no-match", "")["data"]
    assert empty["result_state"] == "EMPTY"
    assert empty["items"] == []
    assert empty["columns"] == []

    denied = gui_query_api.get_global_query_result(
        state, viewer_id, "figure_search", "", "999999")["data"]
    assert denied["result_state"] == "DENIED"
    assert denied["items"] == []
    assert denied["columns"] == []


def test_figure_list_header_union_public_only_for_all_foreign():
    """For an all-FOREIGN set the header shows only the columns a visible row can
    populate (public identity) - no phantom private column captions."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    foreign = next(f for f in state.get_living_members()
                   if f.faction_id and f.faction_id != faction_id)

    record = gui_query_api._project_figure(state, foreign, faction_id)
    header = gui_query_api._figure_list_columns([record])

    assert [c["col_key"] for c in header] == FOREIGN_LIST_COLUMNS
    assert [c["label_key"] for c in header][-1] == "query.figure.office_short"
    assert not (set(c["col_key"] for c in header) & set(OWN_LIST_COLUMNS[5:10]))


def test_figure_list_leader_marking_own_and_foreign():
    """EACH faction's leader is clearly marked (col-1 status/leader badge from
    is_faction_leader) - own AND foreign factions' leaders; non-leaders unmarked.

    ``is_faction_leader`` is PUBLIC_IDENTITY, so a FOREIGN leader carries the very
    same badge as an OWN leader."""
    from src.api import gui_query_api
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    figures = list(state.get_living_members())
    assert len(figures) >= 3
    own = next(f for f in figures if f.faction_id == faction_id)
    foreign = next(f for f in figures if f.faction_id and f.faction_id != faction_id)
    non_leader = next(f for f in figures if f is not own and f is not foreign)

    own.is_faction_leader = True
    foreign.is_faction_leader = True
    non_leader.is_faction_leader = False

    dto = gui_query_api.get_global_query_result(state, viewer_id, "figure_search", "", "")["data"]
    by_id = {item["record_id"]: item for item in dto["items"]}

    def status_cell(record_id):
        item = by_id[str(record_id)]
        return next(c for c in item["columns"] if c["col_key"] == "col_status")

    assert status_cell(own.id)["value_key"] == "query.value.leader"
    assert status_cell(foreign.id)["value_key"] == "query.value.leader"
    assert status_cell(non_leader.id)["value_key"] == ""
    assert status_cell(non_leader.id)["value"] == ""


# ===========================================================================
# v1.3 — i18n parity for the new keys (zh-CN + en-US)
# ===========================================================================
NEW_FIGURE_I18N_KEYS = [
    "query.figure_search.filter_label",
    "query.figure.office_short",
    "query.figure.status",
    "query.figure.family",
    "query.figure.family_value",
    "query.figure.rank",
    "query.figure.zeal",
    "query.figure.charisma",
    "query.figure.martial",
    "query.figure.intelligence",
    "query.figure.contracts",
    "query.figure.is_present",
    "query.figure.influence_value",
    "query.figure.office_history_value",
    "query.value.none",
    "query.value.office_term",
]


def test_new_figure_i18n_keys_present_in_both_locales():
    import json as _json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    for locale in ("zh-CN", "en-US"):
        path = os.path.join(root, "data", "i18n", f"{locale}.json")
        with open(path, encoding="utf-8-sig") as fh:
            catalog = _json.load(fh)
        for key in NEW_FIGURE_I18N_KEYS:
            assert key in catalog, (locale, key)
            assert str(catalog[key]) != ""
