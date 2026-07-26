"""
战斗阶段 API
提供战斗阶段的只读视图、战斗操作和推进接口。
"""

import random
import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus


logger = logging.getLogger("EOR-CombatAPI")


# ════════════════════════════════════════════════════════════════════════
# 内部辅助
# ════════════════════════════════════════════════════════════════════════

def _war_system(state: GameState):
    return state.get_war_system()


def _military_system(state: GameState):
    return state.get_military_system()


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _war_card(war: War, state: GameState) -> Dict[str, Any]:
    """Build a single war_card dict for the CombatView DTO."""
    commander_name = ""
    commander_martial = 0
    commander_id = -1
    if war.commander_id is not None:
        commander = state.get_member(war.commander_id)
        if commander:
            commander_name = commander.get_formal_name() if hasattr(commander, 'get_formal_name') else commander.name or ""
            commander_martial = getattr(commander, 'martial', 0) or 0
            commander_id = war.commander_id

    legions = war.legions_assigned
    legion_power = legions * 2
    total_power = commander_martial + legion_power
    enemy_power = war.get_total_strength()

    return {
        "war_id": war.id,
        "name": war.name,
        "war_type": war.war_type.value,
        "commander_name": commander_name,
        "commander_martial": commander_martial,
        "commander_id": commander_id,
        "legion_count": legions,
        "legion_numbers": war.legion_numbers,
        "total_power": total_power,
        "enemy_power": enemy_power,
        "threat_level": war.threat_level,
        "status": war.status.value if hasattr(war.status, 'value') else str(war.status),
        "has_commander": commander_id >= 0,
    }


def _build_battle_result(
    war: War,
    state: GameState,
    dice: int,
    total_attack: int,
    enemy_defence: int,
    result: str,
    loot: int,
    losses: int,
    triumph: bool,
) -> Dict[str, Any]:
    """Build a battle_result DTO."""
    label_map = {
        "triumph": "🏆 大胜！",
        "victory": "⚔️ 胜利",
        "draw": "🤝 僵持",
        "defeat": "😞 战败",
        "disaster": "💀 灾难",
    }
    result_label = label_map.get(result, result)

    # Compute loot shares using standard formula
    treasury_share = int(loot * 0.50)
    faction_share = int(loot * 0.25)
    commander_share_value = int(loot * 0.15)
    soldier_share = loot - treasury_share - faction_share - commander_share_value

    return {
        "war_id": war.id,
        "war_name": war.name,
        "result": result,
        "result_label": result_label,
        "dice": dice,
        "total_attack": total_attack,
        "enemy_defence": enemy_defence,
        "total_score": total_attack - enemy_defence,
        "losses": losses,
        "triumph": triumph,
        "loot": loot,
        "treasury_share": treasury_share,
        "commander_share": commander_share_value,
        "faction_share": faction_share,
        "soldier_share": soldier_share,
    }


def _compute_combat_result(
    war: War,
    state: GameState,
    dice: int,
    action: str,
) -> Dict[str, Any]:
    """
    Core combat formula.
    Returns a dict with result, total_attack, enemy_defence, loot, losses, triumph.
    """
    # Commander bonus
    commander_martial = 0
    if war.commander_id is not None:
        commander = state.get_member(war.commander_id)
        if commander:
            commander_martial = getattr(commander, 'martial', 0) or 0

    # Legion power
    legion_power = war.legions_assigned * 2

    # Apply action modifiers
    action_bias = 0
    if action == "defence":
        action_bias = 2  # Defensive stance gives +2
    elif action == "scout":
        action_bias = -1  # Scout is preview-only, slight penalty

    total_attack = dice + commander_martial + legion_power + action_bias
    enemy_defence = war.get_total_strength()
    score = total_attack - enemy_defence

    # Result classification
    if war.is_disaster_roll(dice):
        result = "disaster"
    elif score >= 10:
        result = "triumph"
    elif score >= 5:
        result = "victory"
    elif score >= 0:
        result = "draw"
    else:
        result = "defeat"

    # Losses
    losses = 0
    if result == "disaster":
        losses = max(1, war.legions_assigned // 2)  # Disaster loses half the legions
    elif result == "defeat":
        losses = max(1, war.legions_assigned // 3)  # Defeat loses a third

    # Loot (only for non-disaster)
    loot = 0
    triumph = False
    if result != "disaster" and result != "defeat":
        rewards = war.calculate_rewards()
        loot = rewards.get("treasury", 0)
        if result == "triumph":
            triumph = True
            # Triumph gives bonus loot
            loot = int(loot * 1.5)

    return {
        "result": result,
        "total_attack": total_attack,
        "enemy_defence": enemy_defence,
        "loot": loot,
        "losses": losses,
        "triumph": triumph,
        "dice": dice,
        "commander_martial": commander_martial,
        "legion_power": legion_power,
    }


# ════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════

def get_combat_view(state: GameState, viewer_player_id: str) -> dict:
    """Return read-only combat stage DTO."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        ws = _war_system(state)
        ms = _military_system(state)
        ns = state.naval_system

        active_wars = ws.get_active_wars() if ws else []
        fleet_count = len(ns.get_available_fleets()) if ns else 0
        available_legion_count = len(ms.get_available_legions()) if ms else 0
        treasury = getattr(state, '_treasury', 0)

        current_phase_id = _infer_current_phase_id(state)
        current_player = state.get_current_player()

        # Determine current step and phase data
        phase_data = state.get_phase_result("combat") or {}
        if isinstance(phase_data, dict):
            selected_war_id = phase_data.get("selected_war_id", "")
            resolved_wars = phase_data.get("resolved_wars", [])
            pending_result = phase_data.get("pending_result", {})
        else:
            selected_war_id = ""
            resolved_wars = []
            pending_result = {}

        # active_wars naturally shrinks as wars are resolved (status changes to RESOLVED)
        # So all_resolved = True when active_wars is empty
        # Check pending_result first: show result view before transitioning to advance
        if pending_result:
            current_step = "result"
        elif len(active_wars) == 0:
            current_step = "advance"
        elif selected_war_id:
            current_step = "action"
        else:
            current_step = "select"
        all_resolved = len(active_wars) == 0

        actionable = (
            current_phase_id == "combat"
            and state.is_current_player(viewer_player_id)
        )
        interaction_mode = "interactive" if current_phase_id == "combat" else "readonly"

        # Build war cards for active wars
        war_cards = [_war_card(w, state) for w in active_wars]

        # Build resolved war cards from war_system discard pile, filtered by phase_data
        resolved_war_ids = resolved_wars  # list of war_ids from phase_data
        resolved_wars_full = ws.get_resolved_wars() if ws else []
        relevant_resolved = [w for w in resolved_wars_full if w.id in resolved_war_ids]
        resolved_war_cards = [_war_card(w, state) for w in relevant_resolved]

        # Battle results
        battle_results = []
        if pending_result:
            battle_results = [pending_result]

        # Summary
        active_war_count = len(active_wars)
        resolved_war_count = len(resolved_wars)

        data = {
            "phase_id": "combat",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": current_phase_id == "combat",
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "interaction_mode": interaction_mode,
            "current_step": current_step,
            "actionable": actionable,
            "selected_war_id": selected_war_id,
            "can_advance": all_resolved,
            "all_resolved": all_resolved,
            "fleet_count": fleet_count,
            "available_legion_count": available_legion_count,
            "treasury": treasury,
            "active_wars": war_cards,
            "resolved_war_cards": resolved_war_cards,
            "resolved_war_ids": resolved_war_ids,
            "battle_results": battle_results,
            "summary": {
                "title": "战斗阶段",
                "status": current_step,
                "message": "选择战争 → 进攻/防御/侦查 → 查看战果 → 推进决算",
                "active_war_count": active_war_count,
                "resolved_war_count": resolved_war_count,
            },
        }
        return api_response(True, "Combat phase view refreshed", data)
    except Exception as exc:
        logger.exception("get_combat_view failed")
        return api_response(False, f"获取战斗视图失败: {exc}", errors=[str(exc)])


def select_war(state: GameState, viewer_player_id: str, war_id: str) -> dict:
    """Mark a war as selected for combat action."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        ws = _war_system(state)
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            return api_response(False, f"War not found: {war_id}")

        # Store selected war in phase data
        phase_data = state.get_phase_result("combat") or {}
        if isinstance(phase_data, dict):
            phase_data["selected_war_id"] = war_id
        else:
            phase_data = {"selected_war_id": war_id}
        state.record_phase_result("combat", phase_data)

        return api_response(
            True,
            f"Selected war: {war.name}",
            data={"selected_war_id": war_id, "war_name": war.name},
        )
    except Exception as exc:
        logger.exception("select_war failed")
        return api_response(False, f"选择战争失败: {exc}", errors=[str(exc)])


def do_combat_action(
    state: GameState,
    viewer_player_id: str,
    war_id: str,
    action: str,  # "scout", "defence", "attack"
    auto: bool = False,
) -> dict:
    """Execute a combat action on a war."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not auto and not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        ws = _war_system(state)
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            return api_response(False, f"War not found: {war_id}")

        if action not in ("scout", "defence", "attack"):
            return api_response(False, f"Unknown action: {action}")

        # Scout is preview only
        if action == "scout":
            preview_dice = 7  # Average dice for preview
            preview_result = _compute_combat_result(war, state, preview_dice, "scout")
            return api_response(
                True,
                f"侦查预览 — {war.name}",
                data=_build_battle_result(
                    war, state,
                    dice=preview_result["dice"],
                    total_attack=preview_result["total_attack"],
                    enemy_defence=preview_result["enemy_defence"],
                    result=preview_result["result"],
                    loot=preview_result["loot"],
                    losses=preview_result["losses"],
                    triumph=preview_result["triumph"],
                ),
            )

        # Roll dice
        dice = random.randint(2, 12)
        result_data = _compute_combat_result(war, state, dice, action)
        result = result_data["result"]

        # Resolve war with core system
        victory = result in ("triumph", "victory")
        if ws:
            ws.resolve_war(war_id, victory)
            if result == "disaster":
                # For disaster, also resolve war as non-victory but mark as losing war
                war.status = WarStatus.RESOLVED
                state.log_event(
                    f"战斗灾难: {war.name}",
                    extra={
                        "type": "combat_disaster",
                        "war_id": war_id,
                        "war_name": war.name,
                        "losses": result_data["losses"],
                        "result": result,
                    }
                )

        # Apply legion losses via military system
        ms = _military_system(state)
        if ms and result_data["losses"] > 0:
            # Mark legions as needing to be disbanded
            ws.add_legions_to_disband(war.legion_numbers[:result_data["losses"]])

        # Build battle result
        battle_result = _build_battle_result(
            war, state,
            dice=result_data["dice"],
            total_attack=result_data["total_attack"],
            enemy_defence=result_data["enemy_defence"],
            result=result,
            loot=result_data["loot"],
            losses=result_data["losses"],
            triumph=result_data["triumph"],
        )

        # Store in phase data
        phase_data = state.get_phase_result("combat") or {}
        if not isinstance(phase_data, dict):
            phase_data = {}
        phase_data["pending_result"] = battle_result
        resolved = phase_data.get("resolved_wars", [])
        if war_id not in resolved:
            resolved.append(war_id)
        phase_data["resolved_wars"] = resolved
        phase_data["selected_war_id"] = war_id  # Keep selected for result display
        state.record_phase_result("combat", phase_data)

        return api_response(
            True,
            f"战斗结算完成: {result}",
            data=battle_result,
        )
    except Exception as exc:
        logger.exception("do_combat_action failed")
        return api_response(False, f"执行战斗操作失败: {exc}", errors=[str(exc)])


def confirm_battle_result(state: GameState, viewer_player_id: str) -> dict:
    """Acknowledge the battle result and return to SELECT or ADVANCE."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        phase_data = state.get_phase_result("combat") or {}
        if not isinstance(phase_data, dict):
            phase_data = {}

        # Clear pending result
        phase_data["pending_result"] = {}
        phase_data["selected_war_id"] = ""

        # Check if all wars resolved
        ws = _war_system(state)
        active_wars = ws.get_active_wars() if ws else []
        resolved = phase_data.get("resolved_wars", [])
        if len(active_wars) == 0:
            next_step = "advance"
        else:
            next_step = "select"
        all_resolved = len(active_wars) == 0

        state.record_phase_result("combat", phase_data)

        return api_response(
            True,
            "战果已确认",
            data={"next_step": next_step, "all_resolved": all_resolved},
        )
    except Exception as exc:
        logger.exception("confirm_battle_result failed")
        return api_response(False, f"确认战果失败: {exc}", errors=[str(exc)])


def advance_combat(state: GameState, viewer_player_id: str) -> dict:
    """Confirm all combat is done, advance to Phase 7 (Resolution)."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        # Check that all wars are resolved
        phase_data = state.get_phase_result("combat") or {}
        if not isinstance(phase_data, dict):
            phase_data = {}
        resolved = phase_data.get("resolved_wars", [])
        ws = _war_system(state)
        active_wars = ws.get_active_wars() if ws else []

        # Fast-path: no active wars → nothing to resolve → ready to advance
        if len(active_wars) == 0:
            pass
        elif len(active_wars) > len(resolved):
            remaining = len(active_wars) - len(resolved)
            return api_response(False, f"尚有 {remaining} 场战争未结算")

        # Record combat result and mark phase executed
        state.record_phase_result("combat", phase_data)
        state.mark_phase_executed("combat")

        return api_response(
            True,
            "战斗阶段完成，推进到决算阶段",
            data={"next_phase_id": "resolution"},
        )
    except Exception as exc:
        logger.exception("advance_combat failed")
        return api_response(False, f"推进战斗阶段失败: {exc}", errors=[str(exc)])
