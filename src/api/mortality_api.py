"""
src/api/mortality_api.py
GUI/CLI 共用的天命阶段 API。
"""
import logging
from typing import Any, Dict

from src.api import api_response
from src.core.game_state import GameState
from src.core.service.mortality_service import MortalityService


logger = logging.getLogger("EOR-GUI")


def get_mortality_view(state: GameState, viewer_player_id: str) -> dict:
    """返回天命阶段只读状态。"""
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    current_phase_id = _current_phase_id(state)
    data = {
        "phase_id": "mortality",
        "executed": state.is_phase_executed("mortality"),
        "current_phase_id": current_phase_id,
        "is_current_player": state.is_current_player(viewer_player_id),
        "result": state.get_phase_result("mortality"),
        "events": (state.get_phase_result("mortality") or {}).get("events", []),
        "can_execute": (
            current_phase_id == "mortality"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("mortality")
            and not state.get_phase_result("mortality")
        ),
        "can_advance": (
            current_phase_id == "mortality"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("mortality")
            and bool(state.get_phase_result("mortality"))
        ),
        "next_phase_id": MortalityService.NEXT_PHASE_ID,
    }
    return api_response(True, "Mortality view", data)


def execute_mortality_phase(state: GameState, viewer_player_id: str) -> dict:
    """执行天命事件与效果，但不推进阶段。"""
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


def advance_mortality_phase(state: GameState, viewer_player_id: str) -> dict:
    """确认天命结果并推进到收入阶段。"""
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
