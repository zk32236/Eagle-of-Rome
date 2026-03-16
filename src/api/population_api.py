# src/api/population_api.py
"""
人口阶段 API 函数骨架
"""
import logging
from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n


def campaign(state: GameState, player_id: str, figure_id: int, amount: int) -> dict:
    """
    举办庆典，消耗人物财富，增加人气。
    权限：当前玩家，且人物属于当前玩家派系。
    """
    # 基础权限检查
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 暂时返回未实现
    return api_response(False, "未实现")


def vote(state: GameState, player_id: str, office: str, figure_id: int) -> dict:
    """
    为指定公职的候选人投票。
    权限：当前玩家，且只能投一次（临时记录）。
    """
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 暂时返回未实现
    return api_response(False, "未实现")


def get_candidates(state: GameState) -> dict:
    """
    获取所有公职的候选人列表（用于展示）。
    不包含权限检查，所有玩家可查看。
    """
    # 暂时返回空数据
    data = {
        "consul": [],
        "censor": [],
        "praetor": [],
        "quaestor": [],
        "tribune": [],
    }
    message = "候选人列表功能未实现"
    return api_response(True, message, data=data)