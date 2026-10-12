"""EOR20261011-01 S4 — contract_status / province_info DTO contracts.

Frozen authority (G3 v1.5 → v1.4 → v1.3 → v1.1):
  * SA v1.1 §5.3 capabilities / selector grammar;
  * SA v1.1 §6.2 per-viewer field allowlist (V public / V OWN-only / U-H absent);
  * SA v1.1 §6.1 ownership (contract owner = awarded_faction; province visibility = conquered).

DATA-class acceptance. Production read seam =
``gui_query_api.get_global_query_result``. No helper/shortcut entry; every case
drives the public seam with a sanctioned prototype session (AC-13/AC-15 style).
"""
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import gui_query_api, session_api
from src.core.entities.contract import ContractStatus, ContractType

# ---------------------------------------------------------------------------
# Frozen §6.2 field sets
# ---------------------------------------------------------------------------
CONTRACT_PUBLIC_LABELS = {
    "query.contract.id", "query.contract.type", "query.contract.name",
    "query.contract.status", "query.contract.awarded_faction",
    "query.contract.awarded_to",
}
CONTRACT_OWN_LABELS = {
    "query.contract.cost", "query.contract.expected_profit",
    "query.contract.progress_collected", "query.contract.progress_spent",
    "query.contract.remaining_years", "query.contract.warranty",
}
# bid / debug / internal mirror keys that must never surface in ANY DTO layer.
CONTRACT_FORBIDDEN_KEYS = {
    "bids", "_bids", "winning_bid", "_winning_bid", "tax_rate", "_tax_rate",
    "profit_base", "_profit_base", "contract_price", "_contract_price",
    "profit_rate", "_profit_rate", "approved_budget", "_approved_budget",
    "actual_cost", "_actual_cost", "base_cost", "_original_budget",
    "original_budget", "annual_profit", "_annual_profit", "create_turn",
    "_create_turn", "is_extended", "_is_extended", "paid", "_paid",
}

PROVINCE_PUBLIC_LABELS = [
    "query.province.id", "query.province.name", "query.province.total_land",
    "query.province.land_public", "query.province.governor",
    "query.province.governor_type", "query.province.controller",
    "query.province.grievance", "query.province.tax_contract",
    "query.province.project_contract",
]
# U / internal-financial that must be absent for EVERY viewer.
PROVINCE_ABSENT_KEYS = {
    "land_private", "_land_private", "tax_base", "_tax_base",
    "development_level", "infrastructure", "garrison", "loyalty",
    "governor_designate_id", "_governor_designate_id",
}

S4_QUERIES = ("contract_status", "province_info")


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


def _make_contract(state, *, ctype=ContractType.TAX_FARMING, province_id=0,
                   status=ContractStatus.ACTIVE, awarded_faction=None,
                   awarded_to=None, cost=100, profit=20, collected=0, spent=0,
                   remaining=3, warranty=0, name=None):
    """Sanctioned initial-state fixture: a real Contract in the canonical registry."""
    contract = state.create_contract(ctype, province_id, cost, state.turn.turn_number)
    contract.status = status
    contract.name = name if name is not None else "合同%s" % contract.id
    contract.awarded_faction = awarded_faction
    contract.awarded_to = awarded_to
    contract.base_cost = cost
    contract.expected_profit = profit
    contract.total_collected = collected
    contract.total_spent = spent
    contract.remaining_years = remaining
    contract._warranty_remaining = warranty
    return contract


def _conquer(state, province_id):
    """Sanctioned initial-state fixture: mark a province conquered."""
    province = state.get_province(province_id)
    province._conquered = True
    return province


# ===========================================================================
# contract_status — AC-07 (§6.2 lifecycle list/detail, ownership)
# ===========================================================================
def test_contract_status_listed_from_canonical_registry():
    state, viewer_id = _setup_state()
    c1 = _make_contract(state, status=ContractStatus.PENDING)
    c2 = _make_contract(state, status=ContractStatus.BUDGETED)

    result, dto = _data(state, viewer_id, "contract_status", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}
    assert dto["filters"]["field"] == "name"
    returned = {item["record_id"] for item in dto["items"]}
    assert returned == {str(c1.id), str(c2.id)}
    assert all(item["label_key"] == "query.item.contract" for item in dto["items"])


def test_contract_status_empty_returns_empty_state():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "contract_status", "", "")

    assert result["success"]
    assert dto["result_state"] == "EMPTY"
    assert dto["items"] == []
    assert dto["summary"] == {"count": 0}


def test_contract_status_own_active_detail_exposes_private_fields():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = _own_figure(state, faction_id)
    contract = _make_contract(
        state, status=ContractStatus.ACTIVE, awarded_faction=faction_id,
        awarded_to=own.id, cost=120, profit=45, collected=30, spent=10,
        remaining=2, warranty=4,
    )

    result, dto = _data(state, viewer_id, "contract_status", "", str(contract.id))

    assert result["success"]
    assert dto["items"] == []
    assert dto["detail"]["record_id"] == str(contract.id)
    labels = set(_detail_labels(dto))
    assert CONTRACT_PUBLIC_LABELS.issubset(labels)
    assert CONTRACT_OWN_LABELS.issubset(labels)
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.contract.cost"]["value"] == "120"
    assert by_label["query.contract.expected_profit"]["value"] == "45"
    assert by_label["query.contract.progress_collected"]["value"] == "30"
    assert by_label["query.contract.progress_spent"]["value"] == "10"
    assert by_label["query.contract.remaining_years"]["value"] == "2"
    assert by_label["query.contract.warranty"]["value"] == "4"


def test_contract_status_other_detail_public_only():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    other = _other_eligible_viewer(state, faction_id)
    other_fig = _own_figure(state, other.faction_id)
    contract = _make_contract(
        state, status=ContractStatus.ACTIVE, awarded_faction=other.faction_id,
        awarded_to=other_fig.id, cost=500, profit=500, collected=500, spent=500,
    )

    result, dto = _data(state, viewer_id, "contract_status", "", str(contract.id))

    assert result["success"]
    labels = set(_detail_labels(dto))
    assert CONTRACT_PUBLIC_LABELS.issubset(labels)
    assert not (CONTRACT_OWN_LABELS & labels)
    # No private sentinel value leaks anywhere.
    blob = " ".join(_all_strings(dto))
    assert "500" not in blob


def test_contract_status_unowned_pending_detail_public_only():
    state, viewer_id = _setup_state()
    contract = _make_contract(
        state, status=ContractStatus.PENDING, awarded_faction=None, awarded_to=None,
        cost=333, profit=333, collected=333, spent=333,
    )

    result, dto = _data(state, viewer_id, "contract_status", "", str(contract.id))

    assert result["success"]
    labels = set(_detail_labels(dto))
    assert CONTRACT_PUBLIC_LABELS.issubset(labels)
    assert not (CONTRACT_OWN_LABELS & labels)
    assert "333" not in " ".join(_all_strings(dto))


def test_contract_status_inconsistent_ownership_hides_private_fields():
    """awarded_to belongs to a different faction than awarded_faction -> private absent."""
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    foreign = _foreign_figure(state, faction_id)
    # awarded_faction == viewer faction, but awarded_to is a FOREIGN figure -> inconsistent
    contract = _make_contract(
        state, status=ContractStatus.ACTIVE, awarded_faction=faction_id,
        awarded_to=foreign.id, cost=654, profit=654, collected=654, spent=654,
    )

    result, dto = _data(state, viewer_id, "contract_status", "", str(contract.id))

    assert result["success"]
    labels = set(_detail_labels(dto))
    assert CONTRACT_PUBLIC_LABELS.issubset(labels)
    assert not (CONTRACT_OWN_LABELS & labels)
    assert "654" not in " ".join(_all_strings(dto))


def test_contract_status_type_and_status_bind_i18n_keys():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = _own_figure(state, faction_id)
    contract = _make_contract(
        state, ctype=ContractType.PUBLIC_WORKS, status=ContractStatus.ACTIVE,
        awarded_faction=faction_id, awarded_to=own.id,
    )

    _result, dto = _data(state, viewer_id, "contract_status", "", str(contract.id))
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.contract.type"]["value_key"] == "query.contract.type.public_works"
    assert by_label["query.contract.type"]["value"] == ""
    assert by_label["query.contract.status"]["value_key"] == "query.contract.status.active"
    assert by_label["query.contract.status"]["value"] == ""


def test_contract_status_no_bid_debug_internals_recursive():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = _own_figure(state, faction_id)
    contract = _make_contract(
        state, status=ContractStatus.ACTIVE, awarded_faction=faction_id,
        awarded_to=own.id,
    )
    # Distinctive bid/debug internals set on the canonical entity.
    contract._bids = [{"bidder_id": own.id, "amount": 999111}]
    contract._winning_bid = {"bidder_id": own.id, "amount": 999222, "tax_rate": 0.11}
    contract._tax_rate = 0.11
    contract._approved_budget = 999333
    contract._actual_cost = 999444
    contract._profit_base = 999555

    _result, list_dto = _data(state, viewer_id, "contract_status", "", "")
    _result, detail_dto = _data(state, viewer_id, "contract_status", "", str(contract.id))

    for dto in (list_dto, detail_dto):
        keys = set(_all_keys(dto))
        assert not (CONTRACT_FORBIDDEN_KEYS & keys), keys & CONTRACT_FORBIDDEN_KEYS
        blob = " ".join(_all_strings(dto))
        for sentinel in ("999111", "999222", "999333", "999444", "999555"):
            assert sentinel not in blob, sentinel


def test_contract_status_selector_and_filter():
    state, viewer_id = _setup_state()
    c1 = _make_contract(state, name="Sicilia包税权")
    c2 = _make_contract(state, name="Via工程")

    # canonical decimal accept
    ok = gui_query_api.get_global_query_result(state, viewer_id, "contract_status", "", str(c1.id))
    assert ok["success"]
    assert ok["data"]["detail"]["record_id"] == str(c1.id)

    # malformed / absent selector -> identical record_unavailable shell
    for bad in ["0", "01", "-1", "1.5", "abc", " 1", "999999"]:
        result = gui_query_api.get_global_query_result(
            state, viewer_id, "contract_status", "", bad)
        assert not result["success"], bad
        assert result["data"]["result_state"] == "DENIED", bad
        assert [e["code"] for e in result["data"]["errors"]] == ["record_unavailable"], bad
        assert result["data"]["detail"] is None

    # name filter
    _result, filtered = _data(state, viewer_id, "contract_status", "Sicilia", "")
    assert filtered["filters"]["applied"] == "sicilia"
    assert {it["record_id"] for it in filtered["items"]} == {str(c1.id)}

    _result, empty = _data(state, viewer_id, "contract_status", "zzz-no-match", "")
    assert empty["result_state"] == "EMPTY"
    assert empty["filters"]["applied"] == "zzz-no-match"


def test_contract_status_duplicate_or_invalid_canonical_id_fails_query():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    _make_contract(state, status=ContractStatus.PENDING)
    contracts = list(state.get_all_contracts())
    with patch.object(state, "get_all_contracts", return_value=list(contracts) + [contracts[0]]):
        dup = gui_query_api.get_global_query_result(state, viewer_id, "contract_status")
    assert not dup["success"]
    assert [e["code"] for e in dup["data"]["errors"]] == ["query_failed"]

    with patch.object(state, "get_all_contracts",
                      return_value=list(contracts) + [SimpleNamespace(id=0, contract_type=None, status=None, name="x")]):
        inv = gui_query_api.get_global_query_result(state, viewer_id, "contract_status")
    assert not inv["success"]
    assert [e["code"] for e in inv["data"]["errors"]] == ["query_failed"]


def test_contract_status_missing_required_source_fails_closed():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    # A contract-like source missing a required canonical attribute (status=None).
    broken = SimpleNamespace(id=1, contract_type=ContractType.TAX_FARMING,
                             status=None, name="x", awarded_faction=None,
                             awarded_to=None)
    with patch.object(state, "get_all_contracts", return_value=[broken]):
        result = gui_query_api.get_global_query_result(state, viewer_id, "contract_status")
    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]
    assert result["data"]["items"] == [] and result["data"]["summary"] == {}


# ===========================================================================
# province_info — AC-08 (§6.2 conquered boundary; land_private absent)
# ===========================================================================
def test_province_info_list_only_conquered():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "province_info", "", "")

    assert result["success"]
    assert dto["result_state"] == "OK"
    assert dto["capabilities"] == {"can_filter": True, "can_detail": True}
    conquered_ids = {str(p.province_id) for p in state.get_all_provinces() if p.conquered}
    returned = {item["record_id"] for item in dto["items"]}
    assert returned == conquered_ids
    uncond = {str(p.province_id) for p in state.get_all_provinces() if not p.conquered}
    assert not (returned & uncond)
    assert all(item["label_key"] == "query.item.province" for item in dto["items"])


def test_province_info_detail_public_fields_and_land_private_absent():
    state, viewer_id = _setup_state()
    province = _conquer(state, 1)

    result, dto = _data(state, viewer_id, "province_info", "", str(province.province_id))

    assert result["success"]
    assert dto["items"] == []
    assert dto["detail"]["record_id"] == str(province.province_id)
    labels = _detail_labels(dto)
    assert labels == PROVINCE_PUBLIC_LABELS
    by_label = {f["label_key"]: f for f in dto["detail"]["fields"]}
    assert by_label["query.province.id"]["value"] == str(province.province_id)
    assert by_label["query.province.name"]["value"] == province.name
    # land_private + internal financial fields absent recursively.
    keys = set(_all_keys(dto))
    assert not (PROVINCE_ABSENT_KEYS & keys), keys & PROVINCE_ABSENT_KEYS
    assert "land_private" not in " ".join(_all_strings(dto))
    # the private land amount (province.land_private) never appears
    blob = " ".join(_all_strings(dto))
    assert str(province.land_private) not in blob or province.land_private == 0


def test_province_info_italy_id_zero_selectable():
    state, viewer_id = _setup_state()

    result, dto = _data(state, viewer_id, "province_info", "", "0")

    assert result["success"]
    assert dto["detail"]["record_id"] == "0"
    # Italy is a conquered province and appears in the list with record_id "0".
    _result, lst = _data(state, viewer_id, "province_info", "", "")
    assert "0" in {it["record_id"] for it in lst["items"]}


def test_province_info_every_listed_row_opens_detail():
    state, viewer_id = _setup_state()
    _conquer(state, 1)
    _conquer(state, 2)

    _result, lst = _data(state, viewer_id, "province_info", "", "")
    for item in lst["items"]:
        result, dto = _data(state, viewer_id, "province_info", "", item["record_id"])
        assert result["success"], item["record_id"]
        assert dto["detail"]["record_id"] == item["record_id"]


def test_province_info_unconquered_and_absent_are_record_unavailable():
    state, viewer_id = _setup_state()
    unconquered = next(p for p in state.get_all_provinces() if not p.conquered)

    for bad in [str(unconquered.province_id), "9999"]:
        result, dto = _data(state, viewer_id, "province_info", "", bad)
        assert not result["success"], bad
        assert dto["result_state"] == "DENIED", bad
        assert [e["code"] for e in dto["errors"]] == ["record_unavailable"], bad
        assert dto["detail"] is None


def test_province_info_selector_grammar():
    state, viewer_id = _setup_state()
    _conquer(state, 1)

    for bad in ["00", "01", "-1", "1.5", "abc", " 1", "1 "]:
        result, dto = _data(state, viewer_id, "province_info", "", bad)
        assert not result["success"], bad
        assert dto["result_state"] == "DENIED", bad
        assert [e["code"] for e in dto["errors"]] == ["record_unavailable"], bad


def test_province_info_filter_by_name():
    state, viewer_id = _setup_state()
    province = _conquer(state, 1)

    _result, filtered = _data(state, viewer_id, "province_info", province.name[:2], "")
    assert filtered["filters"]["applied"] == province.name[:2].casefold()
    assert {it["record_id"] for it in filtered["items"]} == {str(province.province_id)}

    _result, empty = _data(state, viewer_id, "province_info", "zzz-no-match", "")
    assert empty["result_state"] == "EMPTY"
    assert empty["filters"]["applied"] == "zzz-no-match"


def test_province_info_missing_required_source_fails_closed():
    from unittest.mock import patch
    from types import SimpleNamespace
    state, viewer_id = _setup_state()
    broken = SimpleNamespace(province_id=3, name="X", conquered=True, total_land=None,
                             land_public=1, land_private=0, governor_id=None,
                             governor_type="propraetor", grievance=0,
                             tax_contract_id=None, project_contract_id=None)
    with patch.object(state, "get_all_provinces", return_value=[broken]):
        result = gui_query_api.get_global_query_result(state, viewer_id, "province_info")
    assert not result["success"]
    assert result["data"]["result_state"] == "ERROR"
    assert [e["code"] for e in result["data"]["errors"]] == ["system_unavailable"]


# ===========================================================================
# Cross-cutting — AC-13 / AC-15 / AC-16
# ===========================================================================
def test_s4_viewer_matrix_contracts_and_provinces():
    state, _ = _setup_state()
    _conquer(state, 1)
    for viewer in _eligible_viewers(state):
        # contract_status detail for every contract: private labels iff OWN & awarded & consistent
        _result, lst = _data(state, viewer.player_id, "province_info", "", "")
        for item in lst["items"]:
            dto = _data(state, viewer.player_id, "province_info", "", item["record_id"])[1]
            assert dto["result_state"] == "OK"
            assert not (PROVINCE_ABSENT_KEYS & set(_all_keys(dto)))


def test_s4_readonly_invariant_core_and_rng():
    state, viewer_id = _setup_state()
    faction_id = state.get_player(viewer_id).faction_id
    own = _own_figure(state, faction_id)
    _make_contract(state, status=ContractStatus.ACTIVE, awarded_faction=faction_id,
                   awarded_to=own.id)
    _conquer(state, 2)
    rng_before = random.getstate()

    def snapshot():
        return {
            "dict": state.to_dict(),
            "rng_contracts": {(c.id, c.status.value, c.awarded_faction, c.remaining_years)
                              for c in state.get_all_contracts()},
            "provinces": {(p.province_id, p.conquered) for p in state.get_all_provinces()},
        }

    before = snapshot()
    for query_id in S4_QUERIES:
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "", "")
        gui_query_api.get_global_query_result(state, viewer_id, query_id, "a", "")
    gui_query_api.get_global_query_result(state, viewer_id, "contract_status", "", "1")
    gui_query_api.get_global_query_result(state, viewer_id, "province_info", "", "0")
    after = snapshot()

    assert after == before
    assert random.getstate() == rng_before


def test_s4_queries_reject_invalid_viewer():
    state, _ = _setup_state()
    for query_id in S4_QUERIES:
        result = gui_query_api.get_global_query_result(state, "missing_player", query_id)
        assert not result["success"], query_id
        assert result["data"]["result_state"] == "DENIED", query_id


def test_s4_i18n_keys_present_in_both_locales():
    import json as _json
    keys = [
        "query.item.contract", "query.contract.id", "query.contract.type",
        "query.contract.name", "query.contract.status",
        "query.contract.awarded_faction", "query.contract.awarded_to",
        "query.contract.cost", "query.contract.expected_profit",
        "query.contract.progress_collected", "query.contract.progress_spent",
        "query.contract.remaining_years", "query.contract.warranty",
        "query.contract.type.tax_farming", "query.contract.type.public_works",
        "query.contract.status.pending", "query.contract.status.budgeted",
        "query.contract.status.active", "query.contract.status.completed",
        "query.contract.status.expired", "query.contract_status.message",
        "query.contract_status.filter_label",
        "query.item.province", "query.province.id", "query.province.name",
        "query.province.total_land", "query.province.land_public",
        "query.province.governor", "query.province.governor_type",
        "query.province.controller", "query.province.grievance",
        "query.province.tax_contract", "query.province.project_contract",
        "query.province_info.message", "query.province_info.filter_label",
    ]
    for locale in ("zh-CN", "en-US"):
        path = os.path.join(PROJECT_ROOT, "data", "i18n", "%s.json" % locale)
        with open(path, encoding="utf-8-sig") as fh:
            catalog = _json.load(fh)
        for key in keys:
            assert key in catalog, (locale, key)
            assert str(catalog[key]) != "", (locale, key)
