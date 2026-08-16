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
        "enemy_name": war.name,  # FC-3: DTO 别名（复用 War.name，非新实体字段）
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

    # Result classification — thresholds read from Config combat_rules (FC-2 / DEV-04).
    # Aligned with CLI phase_combat._simplified_crt: TRIUMPH(>=12) / VICTORY(>=6) /
    # STALEMATE(standoff_roll or -3<=score<6) / DEFEAT(<-3). GUI "draw" == CLI "STALEMATE".
    triumph_threshold = state.config.get("combat_rules.triumph_threshold", 12)
    victory_threshold = state.config.get("combat_rules.victory_threshold", 6)
    defeat_threshold = state.config.get("combat_rules.defeat_threshold", -3)

    if war.is_disaster_roll(dice):
        result = "disaster"
    elif score >= triumph_threshold:
        result = "triumph"
    elif score >= victory_threshold:
        result = "victory"
    elif war.is_standoff_roll(dice) or defeat_threshold <= score < victory_threshold:
        result = "draw"
    elif score < defeat_threshold:
        result = "defeat"
    else:
        result = "draw"

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
            war_results = phase_data.get("war_results", {})
        else:
            selected_war_id = ""
            resolved_wars = []
            pending_result = {}
            war_results = {}

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
        resolved_war_cards = []
        for w in relevant_resolved:
            card = _war_card(w, state)
            # AC-4.3: 逐场结果留卡片内 — 每张结算卡附本场 result 对象
            if isinstance(war_results, dict) and w.id in war_results:
                card["result"] = war_results[w.id]
            resolved_war_cards.append(card)

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

        # Idempotency guard (FC-1 AC-1.3): a war already resolved must not be
        # re-resolved on double-click / repeated attack signals.
        if action == "attack":
            phase_data = state.get_phase_result("combat") or {}
            resolved = phase_data.get("resolved_wars", []) if isinstance(phase_data, dict) else []
            if war_id in resolved:
                return api_response(False, f"该战争已结算: {war_id}")

        # Scout is preview-only (DEPRECATED — FUNC-03 attack-only). Retained for
        # API compatibility (B-19); the GUI no longer exposes this action.
        if action == "scout":
            preview_dice = 7  # Average dice for preview
            preview_result = _compute_combat_result(war, state, preview_dice, "scout")
            data = _build_battle_result(
                war, state,
                dice=preview_result["dice"],
                total_attack=preview_result["total_attack"],
                enemy_defence=preview_result["enemy_defence"],
                result=preview_result["result"],
                loot=preview_result["loot"],
                losses=preview_result["losses"],
                triumph=preview_result["triumph"],
            )
            data["deprecated"] = True
            return api_response(
                True,
                f"侦查预览（已弃用）— {war.name}",
                data=data,
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

        # Defence is DEPRECATED (FUNC-03 attack-only). Retained for API
        # compatibility (B-19); the GUI no longer exposes this action.
        if action == "defence":
            battle_result["deprecated"] = True

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
        # AC-4.3: per-war result 持久化 — 按 war_id 累积，不被下一场覆盖 / 确认后不清空
        war_results = phase_data.get("war_results", {})
        if not isinstance(war_results, dict):
            war_results = {}
        war_results[war_id] = battle_result
        phase_data["war_results"] = war_results
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


# ════════════════════════════════════════════════════════════════════════
# S1 Combat 共享用例：auto_resolve_combat
# ════════════════════════════════════════════════════════════════════════
# 整合 CLI CombatCommand 与 GUI auto_resolve 的公共战斗结算逻辑
# CLI + GUI 均委托给此唯一实现
# ════════════════════════════════════════════════════════════════════════

def _generate_peace_treaty(
    war: War,
    battle_result: str,
    state: GameState,
) -> Optional[Dict]:
    """
    根据战斗结果尝试生成停战条约。
    适配自 CLI _maybe_generate_treaty 逻辑。
    仅对非决定性结果（非 triumph/disaster）生成条约。
    """
    # 决定性结果不生成条约（与 CLI 一致）
    if battle_result in ("triumph", "disaster"):
        return None

    from src.core.deciders.impl.auto_peace_treaty_decider import (
        AutoPeaceTreatyDecider
    )
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(war, battle_result.upper(), state)
    if treaty is None:
        return None

    required = {"indemnity", "duration", "generated_turn"}
    if required - treaty.keys():
        logger.warning(
            f"Peace treaty missing required keys for war {war.id}: "
            f"{required - treaty.keys()}"
        )
        return None

    war_system = _war_system(state)
    if war_system and war_system.enter_truce(war, treaty):
        state.log_event(
            f"战争 {war.name} 达成停战草案，赔款 {treaty['indemnity']}，"
            f"有效期 {treaty['duration']} 回合",
            extra={
                "type": "peace_treaty_generated",
                "war_id": war.id,
                "result": battle_result,
                "indemnity": treaty["indemnity"],
                "duration": treaty["duration"],
                "generated_turn": treaty["generated_turn"],
            },
        )
        return treaty
    return None


def _process_commanders_returning(state: GameState) -> List[Dict]:
    """
    处理已批准停战的指挥官返回罗马。
    适配自 CLI _process_commanders_returning 逻辑。
    """
    ws = _war_system(state)
    if not ws:
        return []
    returned = []
    current_turn = state.turn.turn_number if state.turn else 0
    for war in ws.get_truce_wars_with_approved_treaty():
        commander_id = getattr(war, "original_commander_id", None) or war.commander_id
        if not commander_id:
            continue
        commander = state.get_member(commander_id)
        if not commander or commander.is_dead:
            continue

        old_office = getattr(commander, "office", None)
        if old_office in ("proconsul", "propraetor"):
            assigned_turn = getattr(war, "commander_assigned_turn", None) or (
                current_turn - 1
            )
            commander.add_office_history(old_office, assigned_turn, current_turn - 1)
            commander.office = None
            commander.is_absent = False
            commander.update_influence()
            state.log_event(
                f"指挥官 {commander.name} 返回罗马",
                extra={
                    "type": "commander_return",
                    "figure_id": commander.id,
                    "war_id": war.id,
                },
            )
            returned.append({
                "commander_id": commander.id,
                "commander_name": commander.name,
                "war_id": war.id,
                "war_name": war.name,
                "former_office": old_office,
            })
    return returned


def _skip_all_unassigned(state: GameState, wars: List) -> None:
    """
    将无指挥官战争记录到 phase_data resolved_wars，使其不阻塞 advance。
    """
    phase_data = state.get_phase_result("combat") or {}
    if not isinstance(phase_data, dict):
        phase_data = {}
    resolved = list(phase_data.get("resolved_wars", []))
    for war in wars:
        if war.id not in resolved:
            resolved.append(war.id)
    phase_data["resolved_wars"] = resolved
    state.record_phase_result("combat", phase_data)


def auto_resolve_combat(state: GameState, player_id: str) -> dict:
    """
    阶段级公共用例：自动结算所有活跃战争。
    
    CLI CombatCommand 与 GUI adapter.auto_resolve_combat 均委托给此函数。
    Adapter 不再保留 for-loop / 子步骤编排。
    
    返回含以下结构的 dict:
    {
        "success": bool,
        "message": str,
        "data": {
            "wars_resolved": int,        # 已结算战争数
            "active_war_count": int,      # 总活跃战争数
            "skipped_no_commander": int,  # 无指挥官跳过数
            "battles": [                  # 每场战斗结算详情
                {
                    "war_id": str,
                    "war_name": str,
                    "result": str,        # GUI 命名 (triumph/victory/...)
                    "dice": int,
                    "total_attack": int,
                    "enemy_defence": int,
                    "total_score": int,
                    "losses": int,
                    "triumph": bool,
                    "loot": int,
                    ...
                }
            ],
            "treaties": [Dict],          # 生成的停战条约
            "commanders_returned": [Dict], # 返回罗马的指挥官
            "completed": bool,            # combat 阶段是否已完成
            "next_phase": str,            # 下一阶段 ID
        }
    }
    """
    try:
        ws = _war_system(state)
        if not ws:
            return api_response(False, "War system not available")

        active_wars = ws.get_active_wars()
        total_active = len(active_wars)

        if total_active == 0:
            # 无活跃战争也推进阶段（与 CLI 原始行为一致）
            adv_result = advance_combat(state, player_id)
            completed = adv_result.get("success", False)
            adv_data = adv_result.get("data") or {}
            next_phase = adv_data.get("next_phase_id", "resolution")
            return api_response(True, "没有活跃的战争", data={
                "wars_resolved": 0,
                "active_war_count": 0,
                "skipped_no_commander": 0,
                "battles": [],
                "treaties": [],
                "commanders_returned": [],
                "completed": completed,
                "next_phase": next_phase,
            })

        # 分类：有指挥官 vs 无指挥官
        assigned_wars = [w for w in active_wars if w.commander_id is not None]
        skipped = total_active - len(assigned_wars)

        if not assigned_wars:
            # 无指挥官战争：全部标记为已处理，然后推进（与 CLI 一致）
            _skip_all_unassigned(state, active_wars)
            adv_result = advance_combat(state, player_id)
            completed = adv_result.get("success", False)
            adv_data = adv_result.get("data") or {}
            next_phase = adv_data.get("next_phase_id", "resolution")
            return api_response(True, "所有战争均无指挥官，跳过战斗结算", data={
                "wars_resolved": 0,
                "active_war_count": total_active,
                "skipped_no_commander": skipped,
                "battles": [],
                "treaties": [],
                "commanders_returned": [],
                "completed": completed,
                "next_phase": next_phase,
            })

        # 先处理无指挥官战争：标记为已跳过
        _skip_all_unassigned(state, [w for w in active_wars if w.commander_id is None])

        # 逐场结算
        battles = []
        treaties = []
        for war in assigned_wars:
            # Select war
            select_war(state, player_id, war.id)

            # Execute battle (auto 模式跳过玩家校验)
            action_result = do_combat_action(
                state, player_id, war.id, "attack", auto=True
            )
            if not action_result.get("success"):
                continue

            battle_data = action_result.get("data", {})
            battles.append(battle_data)

            # 生成停战条约（CLI 独有逻辑 → 现在属于共享用例）
            result_str = battle_data.get("result", "")
            treaty = _generate_peace_treaty(war, result_str, state)
            if treaty:
                treaties.append(treaty)

            # Confirm result
            confirm_battle_result(state, player_id)

        # 处理指挥官返回
        commanders_returned = _process_commanders_returning(state)

        # 推进战斗阶段
        advance_result = advance_combat(state, player_id)
        completed = advance_result.get("success", False)
        adv_data = advance_result.get("data") or {}
        next_phase = adv_data.get("next_phase_id", "resolution")

        return api_response(True, f"战斗结算完成，共 {len(battles)} 场战斗", data={
            "wars_resolved": len(battles),
            "active_war_count": total_active,
            "skipped_no_commander": skipped,
            "battles": battles,
            "treaties": treaties,
            "commanders_returned": commanders_returned,
            "completed": completed,
            "next_phase": next_phase,
        })

    except Exception as exc:
        logger.exception("auto_resolve_combat failed")
        return api_response(
            False, f"自动战斗结算失败: {exc}", errors=[str(exc)]
        )
