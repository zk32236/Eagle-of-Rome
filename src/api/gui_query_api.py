"""Read-only GUI global query API.

This module is intentionally thin and read-only. It builds DTOs for the GUI
bottom query bar without importing CLI commands or mutating game state.
"""

from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.game_state import GameState


_QUERY_TITLE_KEYS = {
    "game_status": "query.game_status.title",
    "faction_info": "query.faction_info.title",
    "war_list": "query.war_list.title",
    "legion_status": "query.legion_status.title",
    "figure_search": "query.figure_search.title",
    "faction_treasury": "query.faction_treasury.title",
    "public_land": "query.public_land.title",
    "private_land": "query.private_land.title",
    "contract_status": "query.contract_status.title",
    "province_info": "query.province_info.title",
    "fleet_status": "query.fleet_status.title",
    "help": "query.help.title",
}

_QUERY_TITLES = {
    "game_status": "游戏状态",
    "faction_info": "派系信息",
    "war_list": "战争列表",
    "legion_status": "军团状态",
    "figure_search": "人物查询",
    "faction_treasury": "派系金库",
    "public_land": "公地信息",
    "private_land": "私地信息",
    "contract_status": "合同状态",
    "province_info": "行省信息",
    "fleet_status": "舰队状态",
    "help": "帮助",
}


def get_global_query_result(state: GameState, viewer_player_id: str, query_id: str) -> dict:
    """Return one safe read-only DTO for the GUI global query bar."""
    if not state:
        return api_response(False, "无效的游戏状态")
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    handlers = {
        "game_status": _build_game_status,
        "faction_info": _build_faction_info,
        "war_list": _build_war_list,
        "legion_status": _build_legion_status,
    }
    handler = handlers.get(query_id)
    if handler:
        data = handler(state, viewer_player_id)
    else:
        data = _placeholder_query(query_id, "GUI-P0-03G")
    return api_response(True, data["message"], data)


def _build_game_status(state: GameState, viewer_player_id: str) -> Dict[str, Any]:
    current_player = state.get_current_player()
    current_phase_id = _infer_current_phase_id(state)
    turn = state.turn
    year_display = turn.get_year_display() if turn and hasattr(turn, "get_year_display") else _format_year(turn.year if turn else 0)
    data = _base_query("game_status", "connected", "query.game_status.message")
    data["message"] = "共和国公开状态摘要。"
    data["items"] = [
        _item("query.item.year", "年份", year_display),
        _item("query.item.turn", "回合", str(turn.turn_number if turn else 0)),
        _item("query.item.current_phase", "当前阶段", current_phase_id),
        _item("query.item.current_player", "当前玩家", current_player.player_id if current_player else ""),
        _item("query.item.treasury", "国库", f"{state.treasury} T"),
        _item("query.item.living_members", "在世人物", str(len(state.get_living_members()))),
        _item("query.item.factions", "派系数", str(len(state.get_active_factions()))),
    ]
    data["summary"] = {
        "current_phase_id": current_phase_id,
        "current_player_id": current_player.player_id if current_player else None,
        "treasury": state.treasury,
        "living_count": len(state.get_living_members()),
        "faction_count": len(state.get_active_factions()),
    }
    return data


def _build_faction_info(state: GameState, viewer_player_id: str) -> Dict[str, Any]:
    viewer = state.get_player(viewer_player_id)
    viewer_faction_id = viewer.faction_id if viewer else ""
    data = _base_query("faction_info", "readonly", "query.faction_info.message")
    data["message"] = "当前派系显示金库；其他派系仅显示公开概览。"
    items = []
    public_factions = []
    for faction in state.get_active_factions():
        members = faction.get_members(state)
        total_influence = sum(member.influence for member in members)
        public_entry = {
            "id": faction.id,
            "name": faction.name,
            "member_count": len(members),
            "total_influence": total_influence,
            "is_viewer_faction": faction.id == viewer_faction_id,
        }
        if faction.id == viewer_faction_id:
            public_entry["treasury"] = faction.treasury
            items.extend([
                _item("query.item.faction", "派系", faction.name, {"faction_id": faction.id}),
                _item("query.item.treasury", "派系金库", f"{faction.treasury} T", {"scope": "viewer_faction"}),
                _item("query.item.members", "人物数", str(len(members))),
                _item("query.item.influence", "影响力", str(total_influence)),
            ])
        else:
            items.append(_item(
                "query.item.public_faction",
                "公开派系",
                f"{faction.name} / {len(members)} / {total_influence}",
                {"faction_id": faction.id, "treasury_visible": False},
            ))
        public_factions.append(public_entry)
    data["items"] = items or [_item("query.item.status", "状态", "暂无记录")]
    data["summary"] = {
        "viewer_faction_id": viewer_faction_id,
        "factions": public_factions,
    }
    return data


def _build_war_list(state: GameState, viewer_player_id: str) -> Dict[str, Any]:
    data = _base_query("war_list", "readonly", "query.war_list.message")
    data["message"] = "战争列表展示公开状态摘要，不执行战斗。"
    ws = state.get_war_system()
    if not ws:
        data["items"] = [_item("query.item.status", "状态", "战争系统不可用")]
        data["summary"] = {"wars": []}
        return data

    wars = []
    for group_name, group in (
        ("active", ws.get_active_wars()),
        ("threat", ws.get_threat_wars()),
        ("truce", ws.get_truce_wars()),
        ("resolved", ws.get_resolved_wars()),
    ):
        for war in group:
            entry = _war_summary(state, war, group_name)
            wars.append(entry)

    data["items"] = [
        _item("query.item.war", "战争", _war_item_value(war), {"war_id": war["id"], "status": war["status"]})
        for war in wars
    ] or [_item("query.item.status", "状态", "暂无记录")]
    data["summary"] = {
        "wars": wars,
        "counts": {
            "active": len([war for war in wars if war["status"] == "active"]),
            "threat": len([war for war in wars if war["status"] == "threat"]),
            "truce": len([war for war in wars if war["status"] == "truce"]),
            "resolved": len([war for war in wars if war["status"] == "resolved"]),
        },
    }
    return data


def _build_legion_status(state: GameState, viewer_player_id: str) -> Dict[str, Any]:
    data = _base_query("legion_status", "readonly", "query.legion_status.message")
    data["message"] = "军团状态为只读摘要，不征召、不解散、不分配。"
    ms = state.get_military_system()
    if not ms:
        data["items"] = [_item("query.item.status", "状态", "军事系统不可用")]
        data["summary"] = {"legions": [], "counts": {}}
        return data

    legions = []
    counts = {"total": 0, "active": 0, "available": 0, "assigned": 0, "destroyed": 0}
    for legion in ms.get_all_legions():
        info = legion.to_display_dict(state)
        status = info.get("status", "")
        counts["total"] += 1
        if status == "active":
            counts["active"] += 1
        if status in {"available", "unraised", "disbanded"}:
            counts["available"] += 1
        if info.get("assigned"):
            counts["assigned"] += 1
        if status == "destroyed":
            counts["destroyed"] += 1
        legions.append({
            "number": info.get("number"),
            "name": info.get("name"),
            "status": status,
            "is_veteran": info.get("is_veteran", False),
            "war_id": info.get("war_id"),
            "assigned": info.get("assigned", False),
            "strength": info.get("strength", 0),
            "cost": info.get("cost", 0),
            "destroyed_turn": info.get("destroyed_turn", 0),
        })

    data["items"] = [
        _item("query.item.legion", "军团", _legion_item_value(legion), {"legion_number": legion["number"]})
        for legion in legions
    ] or [_item("query.item.status", "状态", "暂无记录")]
    data["summary"] = {"counts": counts, "legions": legions}
    return data


def _placeholder_query(query_id: str, handoff_task: str) -> Dict[str, Any]:
    data = _base_query(query_id, "placeholder", "query.placeholder.message")
    data["message"] = f"{handoff_task} 后续任务承接；当前仅显示入口占位。"
    data["message_params"] = {"handoff_task": handoff_task}
    data["items"] = [_item("query.item.handoff", "承接任务", handoff_task)]
    data["summary"] = {"handoff_task": handoff_task}
    return data


def _base_query(query_id: str, status: str, message_key: str) -> Dict[str, Any]:
    return {
        "id": query_id,
        "title": _QUERY_TITLES.get(query_id, query_id),
        "title_key": _QUERY_TITLE_KEYS.get(query_id, query_id),
        "status": status,
        "message": "",
        "message_key": message_key,
        "message_params": {},
        "items": [],
        "summary": {},
    }


def _item(label_key: str, label: str, value: Any, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "label": label,
        "label_key": label_key,
        "value": "" if value is None else str(value),
        "meta": meta or {},
    }


def _war_summary(state: GameState, war, status: str) -> Dict[str, Any]:
    commander_name = ""
    if getattr(war, "commander_id", None):
        commander = state.get_member(war.commander_id)
        commander_name = commander.get_formal_name() if commander else str(war.commander_id)
    return {
        "id": war.id,
        "name": war.name,
        "status": status,
        "threat_level": getattr(war, "threat_level", 0),
        "naval_required": getattr(war, "naval_required", False),
        "commander_id": getattr(war, "commander_id", None),
        "commander_name": commander_name,
        "legions_assigned": getattr(war, "legions_assigned", 0),
        "fleets_assigned": getattr(war, "fleets_assigned", 0),
    }


def _war_item_value(war: Dict[str, Any]) -> str:
    parts = [war["name"], war["status"]]
    if war.get("threat_level"):
        parts.append(f"threat {war['threat_level']}")
    if war.get("naval_required"):
        parts.append("naval")
    if war.get("commander_name"):
        parts.append(war["commander_name"])
    return " / ".join(parts)


def _legion_item_value(legion: Dict[str, Any]) -> str:
    parts = [legion["name"], legion["status"], f"str {legion['strength']}"]
    if legion.get("assigned"):
        parts.append(f"war {legion.get('war_id', '')}")
    if legion.get("is_veteran"):
        parts.append("veteran")
    return " / ".join(parts)


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    return f"{year} AD"
