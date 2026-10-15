"""
src/api/mortality_api.py
GUI/CLI 共用的天命阶段 API。
"""
import logging
from typing import Any, Dict

from src.api import api_response
from src.api import session_access
from src.api import session_turn_service as turn_service
from src.core.game_state import GameState
from src.core.service.mortality_service import MortalityService


logger = logging.getLogger("EOR-GUI")


def get_mortality_view(state: GameState, viewer_player_id: str, *,
                       caller_context=None) -> dict:
    """返回天命阶段只读状态。"""
    # S-B Group 1: active-seat read guard before any public/private DTO build.
    denied = session_access.denied_or_none(
        state, session_access.OP_READ_PHASE_VIEW, viewer=viewer_player_id,
        caller_context=caller_context)
    if denied is not None:
        return denied
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    current_phase_id = _current_phase_id(state)
    result = state.get_phase_result("mortality")
    can_execute = (
        current_phase_id == "mortality"
        and state.is_current_player(viewer_player_id)
        and not state.is_phase_executed("mortality")
        and not result
    )
    # WP-J J-AC-10 / FC-01..FC-07: authoritative intra-phase step read model.
    # Single owner = this phase view; QML/Store may only consume (FC-01/FC-08).
    # Mortality has exactly one sub-step [execute]; the passive 「查看事件结果」 is NOT a
    # lifecycle state (FC-07, spec §3.1) and must never be modelled as a step.
    steps = [
        {
            "key": "execute",
            "label": "⚡ 执行天命",
            "state": "current" if can_execute else ("complete" if result else "todo"),
        }
    ]
    data = {
        "phase_id": "mortality",
        "steps": steps,
        "executed": state.is_phase_executed("mortality"),
        "current_phase_id": current_phase_id,
        "is_current_player": state.is_current_player(viewer_player_id),
        "result": result,
        "events": (result or {}).get("events", []),
        "can_execute": can_execute,
        "can_advance": (
            current_phase_id == "mortality"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("mortality")
            and bool(state.get_phase_result("mortality"))
        ),
        "next_phase_id": MortalityService.NEXT_PHASE_ID,
    }
    return api_response(True, "Mortality view", data)


def execute_mortality_phase(state: GameState, viewer_player_id: str, *,
                            caller_context=None) -> dict:
    """执行天命事件与效果，但不推进阶段。"""
    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="execute_mortality_phase",
        viewer=viewer_player_id, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    if state.is_phase_executed("mortality"):
        return api_response(False, "Mortality phase already executed")

    if state.get_phase_result("mortality"):
        return api_response(False, "Mortality phase already resolved")

    current_phase_id = _current_phase_id(state)
    if current_phase_id != "mortality":
        return api_response(False, f"Current phase is {current_phase_id}, not mortality")

    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Current viewer is not the active player")

    service = MortalityService(state)
    result: Dict[str, Any] = service.execute(mark_phase=False)
    state.record_phase_result("mortality", result)
    logger.info(
        "Mortality phase executed",
        extra={
            "viewer_player_id": viewer_player_id,
            "events": [event.get("name") for event in result.get("events", [])],
            "next_phase_id": result.get("next_phase_id"),
        },
    )
    return api_response(True, "Mortality phase resolved", result)


def advance_mortality_phase(state: GameState, viewer_player_id: str, *,
                            caller_context=None) -> dict:
    """确认天命结果并推进到收入阶段。"""
    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="advance_mortality_phase",
        viewer=viewer_player_id, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    if state.is_phase_executed("mortality"):
        return api_response(False, "Mortality phase already executed")

    current_phase_id = _current_phase_id(state)
    if current_phase_id != "mortality":
        return api_response(False, f"Current phase is {current_phase_id}, not mortality")

    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Current viewer is not the active player")

    result = state.get_phase_result("mortality")
    if not result:
        return api_response(False, "Mortality phase has not been resolved")

    # S-C (R1 §4.5 / Overlay §1.1): advance checks the current scope + the genuine
    # existing result/execution predicate on a registered Hot-seat session.
    barrier = turn_service.owner_barrier(state, "mortality")
    if barrier is not None:
        return api_response(False, barrier["message"], errors=[barrier["code"]])

    state.mark_phase_executed("mortality")
    data = {
        "phase_executed": True,
        "next_phase_id": MortalityService.NEXT_PHASE_ID,
        "result": result,
    }
    logger.info(
        "Mortality phase advanced",
        extra={"viewer_player_id": viewer_player_id, "next_phase_id": MortalityService.NEXT_PHASE_ID},
    )
    return api_response(True, "Mortality phase advanced", data)


def _current_phase_id(state: GameState) -> str:
    phase_order = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
    for phase_id in phase_order:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"
