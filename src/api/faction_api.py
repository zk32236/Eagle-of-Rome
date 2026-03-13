# src/api/faction_api.py
from src.core.game_state import GameState
from src.api import api_response
from typing import List, Dict, Any

def get_factions_status(state: GameState) -> dict:
    """返回所有派系状态"""
    if not state.factions:
        return api_response(True, "   无派系", data=[])

    lines = ["\n" + "=" * 60, "   🏛️ 派系状态一览", "=" * 60]
    data_list = []
    for faction in state.factions.values():
        members = faction.get_members(state)
        member_count = len(members)
        total_influence = sum(m.influence for m in members)
        player_flag = " [玩家]" if faction.is_player else ""
        avg_influence = total_influence // member_count if member_count > 0 else 0

        lines.append(f"\n{faction.name} ({faction.id}){player_flag}")
        lines.append(f"   💰 金库: {faction.treasury} Talents")
        lines.append(f"   👥 成员: {member_count} 人")
        lines.append(f"   📊 总影响力: {total_influence}")
        lines.append(f"   📈 平均影响力: {avg_influence}")
        if member_count == 0:
            lines.append("   ⚠️  派系无人！")

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