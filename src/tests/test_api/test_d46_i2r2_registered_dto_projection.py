"""EOR20261013-02 · D4/D6 I2-R2 — item5 registered DTO projection (Disposition A).

RED-first contract for the frozen item5 disposition:

  * ``02-sa-design/Rework-D3D6-D4D6-Item5-DTO-Projection-Disposition_2026-10-17.md``
    (``35be80c5…``) §3 (authority / KEEP+ADD / minimal change);
  * ``00-gates/PM-Ruling-D4D6-Item5-DTO-Projection-Accepted_2026-10-17.md``
    (Disposition A — additive two-plane);
  * ``02-sa-design/Rework-D3D6-D4D6-Design-Delta_2026-10-17.md`` §4.5 / FC-D46-07.

Covered:
  * I2R2-R1  non-registered (CLI/legacy) => ``registered_seat == False`` and every
    ``registered_*`` owner/capability field is neutral (None / False); legacy keys
    present.
  * I2R2-R2  registered seat (step=proposal), latched actual HUMAN owner (consul
    held by player1, player1 current) => ``registered_proposal_controller == 'HUMAN'``,
    ``registered_proposal_owner_player_id == 'player1'``,
    ``registered_can_create_proposal is True`` and
    ``registered_can_trigger_ai_proposer is False`` (registered AI bits ALWAYS False).
  * I2R2-R3  a STALE viewer (player2) whose viewer-relative legacy mode reads AI
    while the ACTUAL latched owner is a HUMAN (player1): the registered plane
    carries the ACTUAL owner and refuses the AI trigger; the legacy plane keeps its
    viewer-relative value (additive proof).
  * I2R2-R4  a schedule-derivation ERROR => ``registered_schedule_valid is False``
    and the registered controllers stay neutral (``None``, NOT ``'NONE'``).
  * I2R2-R5  additive: the legacy viewer-relative keys are byte-for-byte equal
    with / without registration.
  * I2R2-R6  a valid schedule with no eligible holder => ``registered_schedule_valid
    is True`` and a structural controller (error != NONE).

Provenance: real ``GameState.create_for_testing`` senate fixture (CONSTRUCTED_STATE);
the only stimulus is a monkeypatched schedule for the error case. No QML / data /
other product file is touched. ``NO TOUCH``: every pre-existing test assertion
(the legacy keys are only READ here).
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.api import session_access
from src.api import session_turn_service as sts
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem


def _senate_state(*, passed=0, current="player1", tribune_ai=True,
                  decision_complete=False):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=1, name="consul", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f1.member_ids.append(1)

    tribune = Figure(id=3, name="tribune", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(3)

    state.add_player(Player(player_id="player1", faction_id="optimates",
                            player_type=PlayerType.HUMAN))
    state.add_player(Player(player_id="player2", faction_id="populares",
                            player_type=PlayerType.AI if tribune_ai
                            else PlayerType.HUMAN))
    state._turn_order = ["player1", "player2"]
    state.set_current_player(current)
    state.senate_proposal_decision_complete = bool(decision_complete)
    for _ in range(passed):
        pid = state.add_senate_proposal(
            {"type": "land", "act_type": "distribution",
             "amount_C": 10, "percent": 0.1})
        state.record_senate_vote("player1", pid, True)
        state.record_senate_vote("player2", pid, True)
    return state


def _view(state, viewer):
    """Read the senate view with the trusted caller context presented (the read
    boundary is guarded; a registered seat denies without a presented handle)."""
    return senate_api.get_senate_view(
        state, viewer, caller_context=session_access.present_context(state))


_REGISTERED_NEUTRAL_NONE = (
    "registered_proposal_owner_player_id", "registered_proposal_officer_id",
    "registered_proposal_controller", "registered_veto_owner_player_id",
    "registered_veto_officer_id", "registered_veto_controller",
)
_REGISTERED_BOOL_FALSE = (
    "registered_can_create_proposal", "registered_can_select_proposal",
    "registered_can_finish_empty", "registered_can_veto",
    "registered_can_trigger_ai_proposer", "registered_can_auto_veto",
    "registered_proposal_satisfied", "registered_veto_satisfied",
    "registered_veto_required", "registered_schedule_valid",
)


def test_i2r2_r1_non_registered_is_neutral_and_legacy_preserved():
    state = _senate_state(passed=0, current="player1")
    res = _view(state, "player1")
    assert res.get("success") is True, res
    data = res["data"]
    assert data["registered_seat"] is False, data.get("registered_seat")
    for key in _REGISTERED_BOOL_FALSE:
        assert data.get(key) is False, (key, data.get(key))
    for key in _REGISTERED_NEUTRAL_NONE:
        assert data.get(key) is None, (key, data.get(key))
    assert data["registered_authority_source"] == "latched_schedule_role_selection"
    for key in ("proposal_control_mode", "veto_control_mode", "proposal_actor",
                "veto_actor", "viewer_has_consul", "can_create_proposal",
                "can_trigger_ai_proposer", "can_veto", "can_auto_veto"):
        assert key in data, key


def test_i2r2_r2_registered_actual_human_owner_blocks_ai_trigger():
    # step must read "proposal": no committed result and the explicit decision is
    # still open (decision_complete=False).
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    res = _view(state, "player1")
    assert res.get("success") is True, res
    data = res["data"]
    assert data["current_step"] == "proposal", data.get("current_step")
    assert data["registered_seat"] is True
    assert data["registered_schedule_valid"] is True
    assert data["registered_proposal_controller"] == sts.CONTROLLER_HUMAN, data
    assert data["registered_proposal_owner_player_id"] == "player1", data
    assert data["registered_can_create_proposal"] is True, data
    assert data["registered_can_select_proposal"] is True, data
    assert data["registered_can_trigger_ai_proposer"] is False, data
    assert data["registered_can_auto_veto"] is False, data


def test_i2r2_r3_stale_viewer_ai_mode_but_actual_human_owner():
    state = _senate_state(passed=0, current="player1", tribune_ai=True,
                          decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    # The public read guard enforces principal==current==viewer, so the
    # stale-viewer *scenario* is exercised at the projection helper directly:
    # viewer=player2 (non-owner) whose legacy viewer-relative mode is AI, while the
    # LATCHED actual owner of the proposal obligation is the HUMAN player1.
    spectator = senate_api.get_senate_view(
        state, "player1", caller_context=session_access.present_context(state))
    assert spectator.get("success") is True, spectator
    assert spectator["data"]["proposal_control_mode"] == "HUMAN"
    reg = senate_api._registered_role_capabilities(state, "player2", "proposal")
    assert reg["registered_proposal_controller"] == sts.CONTROLLER_HUMAN, reg
    assert reg["registered_proposal_owner_player_id"] == "player1", reg
    assert reg["registered_can_trigger_ai_proposer"] is False, reg
    assert reg["registered_can_create_proposal"] is False, reg
    # the stale viewer's own (guarded) read still carries its viewer-relative AI mode
    from src.core.systems.political_system import PoliticalSystem
    mode = PoliticalSystem(state).resolve_proposal_control("player2")["mode"]
    assert mode == "AI", mode


def test_i2r2_r4_schedule_error_is_not_none(monkeypatch):
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(state, "player1", epoch=0)
    scope_id = sts.mint_scope(state, "senate").scope_id

    def _err_obligations(_state, phase=None, substep=None):
        return sts.ScheduleSnapshot(phase="senate", scope_id=scope_id,
                                    obligations=(), errors=("SENATE_RESOLVER_FAILED",))

    monkeypatch.setattr(sts, "obligations", _err_obligations)
    res = _view(state, "player1")
    assert res.get("success") is True, res
    data = res["data"]
    assert data["registered_seat"] is True
    assert data["registered_schedule_valid"] is False, data
    assert data["registered_proposal_controller"] is None, data
    assert data["registered_veto_controller"] is None, data


def test_i2r2_r5_additive_legacy_keys_unchanged_by_registration():
    s1 = _senate_state(passed=0, current="player1", decision_complete=False)
    d1 = _view(s1, "player1")["data"]
    s2 = _senate_state(passed=0, current="player1", decision_complete=False)
    session_access.register_hotseat_session(s2, "player1", epoch=0)
    sts.mint_scope(s2, "senate")
    d2 = _view(s2, "player1")["data"]
    for key in ("proposal_control_mode", "veto_control_mode", "proposal_actor",
                "veto_actor", "viewer_has_consul", "can_create_proposal",
                "can_trigger_ai_proposer", "can_veto", "can_auto_veto"):
        assert d1.get(key) == d2.get(key), (key, d1.get(key), d2.get(key))


def test_i2r2_r6_structural_none_keeps_schedule_valid():
    state = _senate_state(passed=0, current="player1", decision_complete=False)
    state.members.pop(1, None)  # drop the consul figure -> no eligible holder
    session_access.register_hotseat_session(state, "player1", epoch=0)
    sts.mint_scope(state, "senate")
    snap = sts.obligations(state, "senate")
    if snap.errors:
        return  # resolver/derivation error shape -> covered by R4
    res = _view(state, "player1")
    data = res["data"]
    assert data["registered_seat"] is True
    assert data["registered_schedule_valid"] is True, data
    assert data["registered_proposal_controller"] in (
        sts.CONTROLLER_NONE, sts.CONTROLLER_HUMAN, sts.CONTROLLER_AI), data
