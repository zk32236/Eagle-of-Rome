# src/api/player_api.py
from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n
import logging


def get_players(state: GameState) -> dict:
    """
    返回所有玩家信息，包括当前玩家标记。
    """
    players = state.get_all_players()
    data = []
    current_id = state._current_player_id
    for p in players:
        data.append({
            "player_id": p.player_id,
            "faction_id": p.faction_id,
            "player_type": p.player_type.value,
            "is_current": (p.player_id == current_id),
            "is_online": p.is_online,
        })
    # 格式化消息（可选）
    lines = ["\n👥 玩家列表:"]
    for p in data:
        current_flag = " (当前)" if p["is_current"] else ""
        faction_name = state.get_faction(p["faction_id"]).name if p["faction_id"] else "无派系"
        lines.append(f"  {p['player_id']}{current_flag} - 派系: {faction_name} ({p['player_type']})")
    message = "\n".join(lines)
    return api_response(True, message, data)


def get_current_player(state: GameState) -> dict:
    """
    返回当前玩家信息。
    """
    player = state.get_current_player()
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))
    data = {
        "player_id": player.player_id,
        "faction_id": player.faction_id,
        "player_type": player.player_type.value,
        "is_online": player.is_online,
    }
    faction_name = state.get_faction(player.faction_id).name if player.faction_id else "无派系"
    message = i18n.get("info_current_player", player_id=player.player_id, faction=faction_name)
    return api_response(True, message, data)


def next_player(state: GameState, player_id: str) -> dict:
    """
    结束当前玩家回合，切换到下一个玩家。
    需要检查 player_id 是否为当前玩家。
    """
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    new_id = state.next_player()
    if new_id is None:
        return api_response(False, i18n.get("error_no_next_player"))

    new_player = state.get_player(new_id)
    faction_name = state.get_faction(new_player.faction_id).name if new_player.faction_id else "无派系"
    message = i18n.get("info_player_switched", player_id=new_id, faction=faction_name)
    # 记录日志
    state.log_event(f"玩家切换: {player_id} -> {new_id}", level=logging.INFO,
                    extra={"from": player_id, "to": new_id})
    return api_response(True, message, {"new_player_id": new_id})


# 别名
end_turn = next_player