"""
src/api/revenue_api.py
GUI/CLI 共用的收入阶段 API。
"""
import logging
from typing import Any, Dict

from src.api import api_response
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService

logger = logging.getLogger("EOR-GUI")

NEXT_PHASE_ID = "forum"


def get_revenue_view(state: GameState, viewer_player_id: str) -> dict:
    """返回收入阶段只读状态。"""
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    current_phase_id = _current_phase_id(state)
    result = state.get_phase_result("revenue")
    data = {
        "phase_id": "revenue",
        "executed": state.is_phase_executed("revenue"),
        "current_phase_id": current_phase_id,
        "is_current_player": state.is_current_player(viewer_player_id),
        "result": result,
        "settled_data": result.get("data") if result else None,
        "can_execute": (
            current_phase_id == "revenue"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("revenue")
            and not result
        ),
        "can_advance": (
            current_phase_id == "revenue"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("revenue")
            and bool(result)
        ),
        "next_phase_id": NEXT_PHASE_ID,
    }
    return api_response(True, "Revenue view", data)


def execute_revenue_phase(state: GameState, viewer_player_id: str) -> dict:
    """执行收入结算。"""
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    if state.is_phase_executed("revenue"):
        return api_response(False, "Revenue phase already executed")

    if state.get_phase_result("revenue"):
        return api_response(False, "Revenue phase already resolved")

    current_phase_id = _current_phase_id(state)
    if current_phase_id != "revenue":
        return api_response(False, f"Current phase is {current_phase_id}, not revenue")

    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Current viewer is not the active player")

    service = EconomicService(state)
    result = service.settle_revenue_phase()
    state.record_phase_result("revenue", result)
    logger.info(
        "Revenue phase executed",
        extra={
            "viewer_player_id": viewer_player_id,
            "treasury_delta": (result.get("data") or {}).get("treasury_delta", 0),
            "next_phase_id": NEXT_PHASE_ID,
        },
    )
    return api_response(True, "Revenue phase settled", result)


def advance_revenue_phase(state: GameState, viewer_player_id: str) -> dict:
    """确认收入结算并推进到广场阶段。"""
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    if state.is_phase_executed("revenue"):
        return api_response(False, "Revenue phase already executed")

    current_phase_id = _current_phase_id(state)
    if current_phase_id != "revenue":
        return api_response(False, f"Current phase is {current_phase_id}, not revenue")

    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Current viewer is not the active player")

    result = state.get_phase_result("revenue")
    if not result:
        return api_response(False, "Revenue phase has not been resolved")

    state.mark_phase_executed("revenue")
    data = {
        "phase_executed": True,
        "next_phase_id": NEXT_PHASE_ID,
        "result": result,
    }
    logger.info(
        "Revenue phase advanced",
        extra={"viewer_player_id": viewer_player_id, "next_phase_id": NEXT_PHASE_ID},
    )
    return api_response(True, "Revenue phase advanced", data)


def _current_phase_id(state: GameState) -> str:
    phase_order = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
    for phase_id in phase_order:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"
