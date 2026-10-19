# src/api/faction_api.py
from typing import Any, Dict, Optional

from src.core.game_state import GameState
from src.api import api_response
from src.api import session_access
from src.core.i18n import i18n


@session_access.guarded(session_access.OP_READ_PHASE_VIEW,
                        viewer_param="viewer_player_id")
def get_faction_style_map(state: GameState, *,
                          viewer_player_id: Optional[str] = None,
                          caller_context=None) -> dict:
    """
    返回全局派系样式映射。
    权威来源：state.config.get("faction_style_map", {})

    FC-712-20 (W2b) — TARGET-AWARE GUARDED READ. The guard is now bound to the
    ``viewer_player_id`` keyword (``viewer_param``), so this read is adjudicated
    for the SAME seat that will consume it:

      * during the private activation staging the internal neutral reservation
        presents its staging capability and ``viewer_player_id`` must equal the
        reserved target; naming any other player DENIES;
      * on an ACTIVE refresh ``viewer_player_id`` must equal the registered
        principal; an omitted value keeps the historical un-scoped CLI/historical
        behaviour (additive keyword-only parameter — no caller breaks).

    The payload stays display-only config; the *scope* is the session display
    scope, never a cross-seat public surface.
    返回值格式：
    {
        "map": {
            faction_id: {
                "id": faction_id,
                "name": str,         # 展示名
                "color": str,        # 16进制色值
                "id_display": str,   # 短标识
                "order": int,        # 显示顺序
            },
            ...
        },
        "fallback": {
            "color": "#3A3530",
            "name": "未知派系",
            "id_display": "?",
        },
        "default_unknown_color": "#3A3530",
    }
    """
    style_map = state.config.get("faction_style_map", {}) or {}
    fallback = state.config.get("faction_style_fallback", {}) or {
        "color": "#3A3530",
        "name": "未知派系",
        "id_display": "?",
    }

    result_map: Dict[str, Any] = {}
    for faction_id, faction in state.factions.items():
        style = style_map.get(faction_id, {})
        result_map[faction_id] = {
            "id": faction_id,
            "name": style.get("name", faction.name),
            "color": style.get("color", fallback.get("color", "#3A3530")),
            "id_display": style.get("id_display", faction.name),
            "order": style.get("order", 99),
        }

    return api_response(True, "Faction style map", data={
        "map": result_map,
        "fallback": {
            "color": fallback.get("color", "#3A3530"),
            "name": fallback.get("name", "未知派系"),
            "id_display": fallback.get("id_display", "?"),
        },
        "default_unknown_color": "#3A3530",
    })

@session_access.guarded(session_access.OP_READ_PHASE_VIEW)
def get_factions_status(state: GameState, *, caller_context=None) -> dict:
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
