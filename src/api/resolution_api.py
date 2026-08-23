# src/api/resolution_api.py
"""
S2 共享用例：决算阶段决议结算 (Resolution Settlement)

单一执行入口 `execute_resolution()` — CLI 与 GUI 共用。

边界规则（与 execution-plan.md §3.2 一致）：
- execute_resolution() 负责本年度决算、胜利条件检查、军团恢复
- execute_resolution() 不推进到下一年度（不调用 advance_year()）
- advance_year() 是独立的 Player Command
"""
import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.game_state import GameState

logger = logging.getLogger("EOR-RESOLUTION")


def execute_resolution(
    state: GameState,
    player_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    决算阶段共享用例。

    执行顺序：
    1. 前置检查（combat 已执行、resolution 未执行）
    2. 胜利条件检查 (check_victory_conditions)
    3. 军团恢复 (process_legion_recovery)
    4. 清除本回合事件 (clear_active_events)
    5. 标记阶段已执行 (mark_phase_executed)
    6. 记录决算结果 DTO (record_phase_result)

    参数:
        state: 游戏状态
        player_id: 可选的玩家 ID（跳过检查时可为 None）

    返回:
        api_response 格式的 dict:
        {
            "success": bool,
            "message": str,
            "data": ResolutionResultDTO dict,
            "errors": [...]
        }
    """
    try:
        # 1. 前置检查：combat 必须已执行
        if not state.is_phase_executed("combat"):
            return api_response(
                False, "必须先执行战斗阶段 (combat)",
                errors=["combat_not_executed"],
            )

        # 1b. 前置检查：resolution 尚未执行（幂等保护）
        if state.is_phase_executed("resolution"):
            return api_response(
                False, "决议阶段在本回合已执行过",
                errors=["resolution_already_executed"],
            )

        # 1c. 清除上年决算 read-model（WP-E R-1 P2-4 收口：置于幂等 guard 之后——
        #     语义 = 「新 resolution 开始时清」，非函数最顶端；防跨年残留泄漏到新年预结算视图）
        state.clear_resolution_settlement()

        # 2. 胜利条件检查
        victory_conditions = state.check_victory_conditions()

        # 3. 军团恢复
        turn_number = state.turn.turn_number if state.turn else 0
        ms = state.get_military_system()
        recovered_legions: List[int] = []
        if ms:
            recovered_legions = ms.process_legion_recovery(turn_number)

        # 4. 清除本回合生效的事件（天命）
        state.clear_active_events()

        # 5. 标记阶段已执行
        state.mark_phase_executed("resolution")

        # 6. 构建并记录决算结果 DTO
        current_year = state.turn.year if state.turn else 0
        dto = _build_resolution_dto(
            state=state,
            victory_conditions=victory_conditions,
            recovered_legions=recovered_legions,
            current_year=current_year,
        )
        state.record_phase_result("resolution", dto)

        return api_response(True, "决算阶段执行完成", data=dto)

    except Exception as e:
        logger.exception("execute_resolution failed")
        return api_response(False, f"决算阶段执行异常: {e}", errors=[str(e)])


def _build_resolution_dto(
    state: GameState,
    victory_conditions: Dict[str, Any],
    recovered_legions: List[int],
    current_year: int,
) -> Dict[str, Any]:
    """
    构建决算结果 DTO。

    返回的 dict 结构（ResolutionResultDTO）：
        {
            "year": int,                     # 当前年份
            "year_display": str,             # 格式化年份（如 "260 BC"）
            "victory": {
                "game_over": bool,
                "conditions": [...],
                "summary": dict,
            },
            "legion_recovery": {
                "recovered": int,            # 恢复的军团数量
                "recovered_ids": List[int],  # 恢复的军团 ID 列表
                "full_recovery": bool,       # 是否全军已恢复
            },
            "key_events": List[str],         # 关键事件列表
            "events_cleared": bool,          # 本回合事件是否已清除
        }
    """
    year_display = _format_year(current_year)

    recovered_count = len(recovered_legions)

    # 军团恢复状态
    legion_summary = {
        "recovered": recovered_count,
        "recovered_ids": recovered_legions,
        "details": f"已恢复 {recovered_count} 支军团" if recovered_count > 0 else "无军团需要恢复",
    }

    # 关键事件
    key_events = []
    vc = victory_conditions
    for cond in vc.get("conditions", []):
        if cond.get("triggered"):
            key_events.append(cond["details"])

    if recovered_count > 0:
        key_events.append(f"恢复 {recovered_count} 支军团")

    return {
        "year": current_year,
        "year_display": year_display,
        "victory": vc,
        "legion_recovery": legion_summary,
        "key_events": key_events,
        "events_cleared": True,
    }


def _format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    return f"{year} AD"
