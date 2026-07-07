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


def get_senate_view(state: GameState, viewer_player_id: str) -> dict:
    """返回 GUI 元老院视图。支持 readonly（非当前阶段）和 interactive（当前阶段）两种模式。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        result = _political_system(state).build_initial_info()
        if not result.get("success", False):
            return api_response(
                False,
                result.get("message", "获取元老院视图失败"),
                data={},
                errors=result.get("errors", []),
            )

        info = result.get("data", {}) or {}
        current_phase_id = _infer_current_phase_id(state)
        current_player = state.get_current_player()
        active_foreign_wars = info.get("active_foreign_wars", [])
        war_threats = info.get("war_threats", [])
        pending_peace_treaties = info.get("pending_peace_treaties", [])
        governor_vacancies = info.get("governor_vacancies", {})
        pending_contracts = info.get("pending_contracts", [])

        is_current_phase = (current_phase_id == "senate")
        is_current_player = state.is_current_player(viewer_player_id)

        # ── 交互模式数据 ──
        proposals_raw = state.get_senate_proposals()
        proposals = []
        for p in proposals_raw:
            proposals.append({
                "proposal_id": p.get("id", p.get("proposal_id", 0)),
                "type": p.get("type", "unknown"),
                "proposer_faction": p.get("proposer_faction", ""),
                "consul_name": p.get("consul_name", ""),
                "war_id": p.get("war_id"),
                "war_name": p.get("war_name", ""),
                "legions": p.get("legions", 0),
                "province_id": p.get("province_id"),
                "province_name": p.get("province_name", ""),
                "candidate_id": p.get("candidate_id"),
                "candidate_name": p.get("candidate_name", ""),
                "contract_id": p.get("contract_id"),
                "contract_name": p.get("contract_name", ""),
                "act_type": p.get("act_type", ""),
                "percent": p.get("percent", 0),
                "description": p.get("description", ""),
            })

        # 判断当前子步骤
        votes_copy = state.get_senate_votes_copy()
        all_player_ids = [p.player_id for p in state.get_all_players()]
        all_voted = False
        if is_current_phase and proposals and votes_copy:
            all_voted = all(
                pid in votes_copy for pid in all_player_ids
            )

        sub_step = "proposal"
        if is_current_phase:
            if proposals:
                sub_step = "vote"
                if all_voted:
                    sub_step = "veto"
                    vetoes = state.get_senate_vetoes_copy()
                    if len(vetoes) > 0:
                        sub_step = "completed"

        # 可用提案类型列表（仅当前阶段为元老院时返回）
        available_proposal_types = []
        if is_current_phase:
            available_proposal_types = [
                {"type": "war", "label": "⚔️ 宣战", "description": "征召军团进攻", "needs": ["war_id", "legions"]},
                {"type": "peace", "label": "☮️ 停战", "description": "批准和约条款", "needs": ["war_id"]},
                {"type": "governor", "label": "🏛️ 总督任命", "description": "行省总督提名", "needs": ["province_id", "candidate_id"]},
                {"type": "budget", "label": "💰 建造合同", "description": "公共工程拨款", "needs": ["contract_id"]},
                {"type": "tax", "label": "📜 包税合同", "description": "行省税收承包", "needs": ["contract_id"]},
                {"type": "sell_land", "label": "🏡 卖地法案", "description": "出售公地", "needs": ["percent"]},
                {"type": "grant_land", "label": "🌾 分地法案", "description": "分配公地给平民", "needs": ["percent"]},
                {"type": "takeover_war", "label": "🛡️ 接管战争", "description": "绕过表决·即执行", "needs": ["war_id"], "bypasses_vote": True},
            ]
            # 只有执政官玩家能看到完整配置面板
            if not is_current_player:
                available_proposal_types = []

        # 总督候选人信息
        governor_candidates = []
        for gtype in ["proconsul", "propraetor"]:
            cands = get_eligible_governor_candidates(state, gtype)
            for c in cands:
                governor_candidates.append({
                    "figure_id": c.id,
                    "name": c.get_formal_name(),
                    "governor_type": gtype,
                })

        # 可用合同
        available_contracts = []
        for c in pending_contracts:
            available_contracts.append({
                "contract_id": c.get("contract_id"),
                "name": c.get("name", ""),
                "type": c.get("type", ""),
                "base_cost": c.get("base_cost", 0),
            })

        # 土地信息（通过 state 现有属性获取）
        land_info = {
            "public_land": getattr(state, "public_land", 0),
            "national_land": getattr(state, "national_land", 0),
        }

        interaction_mode = "readonly"
        can_create = False
        can_vote = False
        can_veto = False
        deadlocked = False

        data = {
            "phase_id": "senate",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": is_current_phase,
            "is_current_player": is_current_player,
            "current_phase_id": current_phase_id,
            "interaction_mode": "readonly",
            "actionable": False,
            "can_create_proposal": False,
            "can_vote": False,
            "can_veto": False,
            "can_resolve": False,
            "sub_step": "proposal",
            "all_voted": False,
            "deadlocked": False,
            "summary": {
                "title": "元老院只读状态",
                "status": "readonly",
                "message": "元老院已接入只读状态",
                "faction_leader_count": len(info.get("faction_leaders", [])),
                "active_foreign_war_count": len(active_foreign_wars),
                "war_threat_count": len(war_threats),
                "pending_peace_treaty_count": len(pending_peace_treaties),
                "pending_contract_count": len(pending_contracts),
            },
            "proposals": proposals,
            "available_proposal_types": available_proposal_types,
            "faction_leaders": info.get("faction_leaders", []),
            "presiding_officer": info.get("presiding_officer"),
            "active_foreign_wars": active_foreign_wars,
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace_treaties,
            "governor_vacancies": governor_vacancies,
            "pending_contracts": pending_contracts,
            "governor_candidates": governor_candidates,
            "available_contracts": available_contracts,
            "land_info": land_info,
            "vote_results": {},
            "warnings": ["只读模式：元老院阶段显示为只读视图"],
            "disabled_reason": "当前非元老院阶段",
        }
        return api_response(True, f"Senate {interaction_mode} view refreshed", data)
    except Exception as exc:
        return api_response(False, f"获取元老院视图失败: {exc}", errors=[str(exc)])


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


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


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
