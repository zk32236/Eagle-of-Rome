# src/api/faction_api.py
from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n

def get_factions_status(state: GameState) -> dict:
    """返回所有派系状态"""
    if not state.factions:
        return api_response(True, i18n.get("factions_no_factions"), data=[])

    lines = [i18n.get("factions_header")]
    data_list = []
    for faction in state.factions.values():
        members = faction.get_members(state)
        member_count = len(members)
        total_influence = sum(m.influence for m in members)
        player_flag = i18n.get("faction_player_flag", default=" [玩家]") if faction.is_player else ""
        avg_influence = total_influence // member_count if member_count > 0 else 0

        # 构建单行文本
        line = i18n.get("faction_line",
                        faction_name=faction.name,
                        faction_id=faction.id,
                        player_flag=player_flag,
                        treasury=faction.treasury,
                        member_count=member_count,
                        total_influence=total_influence,
                        avg_influence=avg_influence)
        lines.append(line)
        if member_count == 0:
            lines.append(i18n.get("faction_warning_empty"))

        data_list.append({
            "id": faction.id,
            "name": faction.name,
            "treasury": faction.treasury,
            "member_count": member_count,
            "total_influence": total_influence,
            "avg_influence": avg_influence,
            "is_player": faction.is_player
        })

    lines.append("=" * 60)
    message = "\n".join(lines)
    return api_response(True, message, data_list)