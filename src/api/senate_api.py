# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import logging
from typing import List, Optional

from src.api import api_response
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from src.core.systems.political_system import PoliticalSystem


def _political_system(state: GameState) -> PoliticalSystem:
    return PoliticalSystem(state)


def get_senate_initial_info(state: GameState) -> dict:
    """返回元老院阶段初始展示所需的所有信息。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    try:
        result = _political_system(state).build_initial_info()
        return api_response(
            success=result.get("success", False),
            message=result.get("message", ""),
            data=result.get("data", {}),
            errors=result.get("errors", []),
        )
    except Exception as exc:
        return api_response(False, f"获取信息失败: {exc}", errors=[str(exc)])


def propose(state: GameState, player_id: str, proposal_type: str, bypass_turn_check: bool = False, **kwargs) -> dict:
    """记录元老院提案。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).create_proposal(
        player_id,
        proposal_type,
        bypass_turn_check=bypass_turn_check,
        **kwargs,
    )
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def vote(state: GameState, player_id: str, proposal_ids: List[int], votes: List[bool]) -> dict:
    """记录玩家对多个提案的投票。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).record_vote(player_id, proposal_ids, votes)
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def veto(state: GameState, player_id: str, proposal_ids: List[int]) -> dict:
    """记录保民官对已通过提案的否决。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).record_veto(player_id, proposal_ids)
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def resolve_senate(
    state: GameState,
    vote_decider: Optional[SenateVoteDecider] = None,
    takeover_decider: Optional[AutoWarTakeoverDecider] = None,
) -> dict:
    """执行元老院阶段最终结算。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).resolve_senate(vote_decider, takeover_decider)
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


# ==================== 兼容辅助函数 ====================

def execute_war_declaration(state: GameState, war, consul_id: int, legions: int):
    """执行宣战。保留旧公共函数名，内部委托 PoliticalSystem。"""
    return _political_system(state).execute_war_declaration(war, consul_id, legions)


def execute_passed_peace_treaty(state: GameState, war):
    """执行通过的停战草案。保留旧公共函数名，内部委托 PoliticalSystem。"""
    return _political_system(state).execute_passed_peace_treaty(war)


def process_war_takeover(state: GameState, decider: Optional[AutoWarTakeoverDecider] = None):
    """战争接管处理。保留旧公共函数名，内部委托 PoliticalSystem。"""
    return _political_system(state).process_war_takeover(decider)


def get_eligible_governor_candidates(state: GameState, governor_type: str) -> List[Figure]:
    """获取符合行省总督资格的人物列表（按卸任时间倒序排序）。"""
    return _political_system(state).get_eligible_governor_candidates(governor_type)


def is_governor_position_occupied(state: GameState, figure_id: int) -> bool:
    """检查人物是否已被任命为其他行省的总督（候任或现任）。"""
    return _political_system(state).is_governor_position_occupied(figure_id)


def assign_fleets_to_active_wars(state: GameState) -> dict:
    """
    为需要海战且尚无舰队的活跃战争指派可用舰队（补漏函数）。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    ws = state.get_war_system()
    if not ws:
        return api_response(False, "战争系统不可用")

    naval = state.naval_system
    if not naval:
        return api_response(False, "海军系统不可用")

    target_wars = [
        war for war in ws.get_active_wars()
        if war.naval_required and not war.assigned_fleet_ids
    ]
    if not target_wars:
        return api_response(True, "无需指派舰队")

    target_wars.sort(key=lambda war: getattr(war, "enemy_naval_current", 0), reverse=True)

    available_fleets = naval.get_available_fleets()
    if not available_fleets:
        return api_response(True, "无可指派舰队")

    available_fleets.sort(key=lambda fleet: getattr(fleet, "power", 0), reverse=True)

    assigned_details = []
    assigned_any = False

    for war in target_wars:
        if war.assigned_fleet_ids:
            continue

        needed_power = getattr(war, "enemy_naval_current", 0)
        if needed_power <= 0:
            needed_power = 1

        assigned_fleets = []
        total_power = 0
        fleets_to_remove = []

        for fleet in available_fleets:
            if total_power >= needed_power:
                break
            assigned_fleets.append(fleet.number)
            total_power += getattr(fleet, "power", 0)
            fleets_to_remove.append(fleet)

        if not assigned_fleets:
            continue

        for fleet_num in assigned_fleets:
            if naval.assign_fleet_to_war(fleet_num, war.id, "naval"):
                war.assign_fleet(fleet_num)

        for fleet in fleets_to_remove:
            available_fleets.remove(fleet)

        assigned_details.append({
            "war_id": war.id,
            "war_name": war.name,
            "fleets": assigned_fleets,
            "total_power": total_power,
            "needed_power": needed_power,
        })
        assigned_any = True

        if not available_fleets:
            break

    if not assigned_any:
        return api_response(True, "无符合条件的战争需要舰队，或可用舰队不足")

    message = "\n".join(
        f"⚓ 自动指派 {len(detail['fleets'])} 支舰队至 {detail['war_name']} "
        f"（当前海军战力 {detail['total_power']}，需 {detail['needed_power']}）"
        for detail in assigned_details
    )

    state.log_event(
        f"舰队指派补漏：{len(assigned_details)} 个战争获得舰队",
        level=logging.INFO,
        extra={"assigned_wars": [detail["war_id"] for detail in assigned_details]},
    )

    return api_response(True, message, data={"assigned": assigned_details})
