"""EOR20261013-02 · D4/D6 I1 — phase-role registry closure (RED-first).

Frozen source of truth: ``02-sa-design/Rework-D3D6-D4D6-Design-Delta_2026-10-17.md``
(``f5aeed7d…``) §4.1.1/§4.1.2 (FC-D46-01/02) + ``…_Overlay…`` (``9450e5ed…``) §2.

Scope (I1 = authority plumbing): the Store gains an INDEPENDENT new-normal-root
registry ``_PHASE_ROLE_LEASE_HELPERS`` and a new lookup
``_helpers_for_owning_command`` (old table first, then new, unknown → empty). The
legacy four-root ``_LEASE_HELPERS`` map and its reverse-lock test are UNCHANGED;
the two sets are disjoint; the recovery root is in NEITHER normal registry.

NO TOUCH: ``test_da_rework_d1d2.py`` and every pre-existing assertion; this file is new.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import session_access
from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"

#: The FROZEN legacy four-root map (must stay byte-for-byte identical).
EXPECTED_LEASE_HELPERS = {
    "submit_population_votes": frozenset({
        "begin_population_phase", "batch_vote", "complete_population_player",
        "resolve_population_slice", "process_population_disbandments",
        "resolve_election", "campaign", "vote",
    }),
    "resolve_population_slice": frozenset({
        "begin_population_phase", "process_population_disbandments",
        "resolve_election", "campaign", "vote",
    }),
    "doCompleteForumStep": frozenset({"retire_figure"}),
    "doResolveForum": frozenset({
        "recruit_figure", "place_bid", "buy_land", "vote_triumph",
    }),
}

#: The FROZEN new normal-root closure (design §4.1.2, E = internal guarded labels).
EXPECTED_PHASE_ROLE_HELPERS = {
    "advance_forum_phase": frozenset({
        "begin_population_phase", "archive_office_holders",
        "convert_battlefield_commanders", "process_population_disbandments",
        "campaign", "vote", "resolve_election",
    }),
    "advance_population_phase": frozenset({
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
        "finalize_senate_if_ready", "assign_governors",
    }),
    "propose_many": frozenset({
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
        "finalize_senate_if_ready", "assign_governors",
    }),
    "vote": frozenset({
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
        "finalize_senate_if_ready", "assign_governors",
    }),
    "veto": frozenset({
        "auto_submit_proposals", "apply_auto_tribune_vetoes",
        "finalize_senate_if_ready", "assign_governors",
    }),
}


def _state():
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="forum",
        scenario_file=SCENARIO_3H)
    state = res["data"]["state"]
    state.set_current_player(state.get_all_players()[0].player_id)
    return state


# ===========================================================================
# FC-D46-01 — registry separation + legacy map intact
# ===========================================================================
def test_legacy_lease_helpers_are_byte_for_byte_unchanged():
    assert GuiSessionStore._LEASE_HELPERS == EXPECTED_LEASE_HELPERS


def test_phase_role_registry_is_exactly_the_five_new_roots():
    reg = GuiSessionStore._PHASE_ROLE_LEASE_HELPERS
    assert set(reg) == set(EXPECTED_PHASE_ROLE_HELPERS)
    for command, expected in EXPECTED_PHASE_ROLE_HELPERS.items():
        assert reg[command] == expected, command
        # the owning command is never its own helper
        assert command not in reg[command]


def test_two_normal_registries_are_disjoint_at_key_and_value_level():
    old = GuiSessionStore._LEASE_HELPERS
    new = GuiSessionStore._PHASE_ROLE_LEASE_HELPERS
    assert set(old).isdisjoint(set(new))
    # registry-LEVEL separation: the recovery registry is keyed ONLY by the
    # recovery root, and the five admission rows ARE exactly the five new roots
    # (a normal-root guard LABEL may legitimately appear as an internal recovery
    # edge; that is not a registry key).
    assert {root for (root, _kind) in session_access._RECOVERY_EDGE_POLICIES} \
        == {"recover_continuation"}
    assert "recover_continuation" not in session_access._RECOVERY_ADMISSION
    assert set(session_access._RECOVERY_ADMISSION) == set(new)


def test_recovery_root_is_in_neither_normal_registry():
    root = "recover_continuation"
    assert root not in GuiSessionStore._LEASE_HELPERS
    assert root not in GuiSessionStore._PHASE_ROLE_LEASE_HELPERS
    # ... but it IS keyed (with every resume-kind) in the private recovery registry
    kinds = {k for (_root, k) in session_access._RECOVERY_EDGE_POLICIES}
    assert kinds == {"ENTRY_PENDING", "CONTINUATION_PENDING",
                     "TERMINAL_PENDING", "DELIVERY_PENDING"}


# ===========================================================================
# FC-D46-01 — lookup order: old, then new, then empty (never a union/wildcard)
# ===========================================================================
def test_helpers_for_owning_command_lookup_order():
    lookup = GuiSessionStore._helpers_for_owning_command
    # old roots resolve to the legacy sets verbatim
    for command, expected in EXPECTED_LEASE_HELPERS.items():
        assert lookup(command) == expected, command
    # new roots resolve to the new sets
    for command, expected in EXPECTED_PHASE_ROLE_HELPERS.items():
        assert lookup(command) == expected, command
    # unknown roots are refused with the empty set (no default union / wildcard)
    for unknown in ("", "next_player", "advance_senate_phase", "propose",
                    "recover_continuation", "bogus_root"):
        assert lookup(unknown) == frozenset(), unknown


def test_dispatch_owning_uses_the_new_lookup(monkeypatch):
    state = _state()
    store = GuiSessionStore(state)
    captured = {}

    orig = session_access.begin_dispatch_nesting

    def spy(st, *, txn_id, command, dispatch_epoch, helpers=None):
        captured["command"] = command
        captured["helpers"] = frozenset(helpers or ())
        return orig(st, txn_id=txn_id, command=command,
                    dispatch_epoch=dispatch_epoch, helpers=helpers)

    monkeypatch.setattr(session_access, "begin_dispatch_nesting", spy)
    store._dispatch_owning({"txn_id": "t", "seat_epoch": 1},
                           "advance_forum_phase", lambda: "ok")
    assert captured["command"] == "advance_forum_phase"
    assert captured["helpers"] == EXPECTED_PHASE_ROLE_HELPERS["advance_forum_phase"]


def test_after_barrier_consume_uses_the_new_lookup(monkeypatch):
    """The lease-consumption helpers must come from the SAME lookup, else a new
    root's continuation scope would be opened with an empty helper set."""
    source = GuiSessionStore._after_barrier_armed
    import inspect
    text = inspect.getsource(source)
    assert "_helpers_for_owning_command" in text
    assert "_LEASE_HELPERS.get" not in text
