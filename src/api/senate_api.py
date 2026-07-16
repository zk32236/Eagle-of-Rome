# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
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



def _safe_name(item: Any, *attrs: str) -> str:
    for attr in attrs:
        value = getattr(item, attr, None)
        if value:
            return str(value)
    if isinstance(item, dict):
        for attr in attrs:
            value = item.get(attr)
            if value:
                return str(value)
    return ""


def _proposal_label(state: GameState, proposal: Dict[str, Any]) -> str:
    ptype = proposal.get("type", "")
    if ptype == "war":
        ws = state.get_war_system()
        war = ws.get_war_by_id(proposal.get("war_id")) if ws else None
        return f"宣战 — {_safe_name(war, 'name') or proposal.get('war_id')}（征召 {proposal.get('legions', 0)} 个军团）"
    if ptype == "peace":
        ws = state.get_war_system()
        war = ws.get_war_by_id(proposal.get("war_id")) if ws else None
        return f"停战 — {_safe_name(war, 'name') or proposal.get('war_id')}"
    if ptype == "governor":
        province = state.get_province(proposal.get("province_id"))
        candidate = state.get_member(proposal.get("candidate_id"))
        candidate_name = candidate.get_formal_name() if candidate else proposal.get("candidate_id")
        return f"总督任命 — {_safe_name(province, 'name') or proposal.get('province_id')}：{candidate_name}"
    if ptype == "budget":
        contract = state.get_contract(proposal.get("contract_id"))
        amount = proposal.get("modified_budget")
        return f"建造合同 — {_safe_name(contract, 'name') or proposal.get('contract_id')}（预算 {amount} T）"
    if ptype == "land":
        if proposal.get("act_type") == "sale":
            return "卖地法案 — 出售国家公地"
        return "分地法案 — 分配公地给平民"
    return ptype


def _proposal_option(key: str, proposal_type: str, title: str, detail: str, params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": key,
        "type": proposal_type,
        "title": title,
        "detail": detail,
        "params": params,
        "selected": False,
        "enabled": True,
    }


def _build_proposal_options(state: GameState, info: Dict[str, Any]) -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    for war in info.get("war_threats", []):
        options.append(_proposal_option(
            f"war:{war.get('war_id')}", "war",
            f"宣战 — {war.get('name', war.get('war_id'))}",
            f"征召 6 个军团；威胁 {war.get('threat_level', 0)}",
            {"war_id": war.get("war_id"), "legions": 6},
        ))
    for peace in info.get("pending_peace_treaties", []):
        options.append(_proposal_option(
            f"peace:{peace.get('war_id')}", "peace",
            f"停战 — {peace.get('name', peace.get('war_id'))}",
            f"赔款 {peace.get('indemnity', 0)} T；期限 {peace.get('duration', 0)} 年",
            {"war_id": peace.get("war_id")},
        ))
    politics = _political_system(state)
    vacancies = info.get("governor_vacancies", {}) or {}
    for governor_type, provinces in vacancies.items():
        candidates = politics.get_eligible_governor_candidates(governor_type)
        available = [candidate for candidate in candidates if not politics.is_governor_position_occupied(candidate.id)]
        candidate = available[0] if available else None
        for province in provinces:
            if not candidate:
                continue
            options.append(_proposal_option(
                f"governor:{province.get('province_id')}", "governor",
                f"总督任命 — {province.get('province_name', province.get('province_id'))}",
                f"候选人：{candidate.get_formal_name()}",
                {"province_id": province.get("province_id"), "candidate_id": candidate.id},
            ))
    for contract in info.get("pending_contracts", []):
        base_cost = contract.get("base_cost", 0)
        options.append(_proposal_option(
            f"budget:{contract.get('contract_id')}", "budget",
            f"建造合同 — {contract.get('name', contract.get('contract_id'))}",
            f"预算金额 {base_cost} T；预期收益 {contract.get('expected_profit', 0)} T",
            {"contract_id": contract.get("contract_id"), "modified_budget": base_cost},
        ))
    public_land = state.get_national_public_land()
    if public_land > 0:
        options.append(_proposal_option(
            "land:sale", "land", "卖地法案 — 出售国家公地",
            f"出售 10% 国家公地；当前公地 {public_land} C",
            {"act_type": "sale", "percent": 0.10},
        ))
        options.append(_proposal_option(
            "land:distribution", "land", "分地法案 — 分配公地给平民",
            f"分配 10% 国家公地；当前公地 {public_land} C",
            {"act_type": "distribution", "percent": 0.10},
        ))
    return options


def _submitted_proposal_rows(state: GameState) -> List[Dict[str, Any]]:
    rows = []
    for proposal in state.get_senate_proposals():
        row = proposal.copy()
        row["label"] = _proposal_label(state, proposal)
        rows.append(row)
    return rows


def _seat_share_rows(state: GameState) -> List[Dict[str, Any]]:
    total = sum(faction.get_senate_influence(state) for faction in state.get_active_factions())
    rows = []
    for faction in state.get_active_factions():
        influence = faction.get_senate_influence(state)
        rows.append({
            "faction_id": faction.id,
            "faction_name": faction.name,
            "influence": influence,
            "percent": int(round(influence * 100 / total)) if total else 0,
        })
    return rows


def _current_tribune(state: GameState) -> Optional[Figure]:
    for member in state.get_living_members():
        if member.office == "tribune" and not member.is_dead:
            return member
    return None


def _viewer_has_tribune(state: GameState, viewer_player_id: str) -> bool:
    viewer = state.get_player(viewer_player_id)
    tribune = _current_tribune(state)
    return bool(viewer and tribune and tribune.faction_id == viewer.faction_id)


def _passed_proposals_for_veto(state: GameState) -> List[Dict[str, Any]]:
    politics = _political_system(state)
    passed = []
    for proposal in state.get_senate_proposals():
        result = politics.calculate_vote_result(proposal)
        if result.get("passed") and not result.get("vetoed"):
            passed.append(proposal)
    return passed


def apply_auto_tribune_vetoes(
    state: GameState,
    veto_decider: Optional[TribuneVetoDecider] = None,
) -> dict:
    """Apply AI tribune veto decisions for GUI when current viewer does not own the tribune."""
    if not state:
        return api_response(False, "Invalid game state")
    tribune = _current_tribune(state)
    if not tribune:
        return api_response(True, "No tribune is available; veto step skipped", data={"vetoed": [], "decisions": []})
    decider = veto_decider or AutoTribuneVetoDecider()
    politics = _political_system(state)
    vetoed = []
    decisions = []
    for proposal in _passed_proposals_for_veto(state):
        issue = politics.build_issue_from_proposal(proposal)
        should_veto = decider.decide_veto(issue, tribune.id, state)
        if should_veto:
            state.record_senate_veto(proposal["id"])
            vetoed.append(proposal["id"])
        decisions.append({
            "proposal_id": proposal["id"],
            "proposal_type": proposal.get("type"),
            "vetoed": should_veto,
            "tribune_id": tribune.id,
            "tribune_faction_id": tribune.faction_id,
        })
    return api_response(
        True,
        f"AI tribune veto decisions completed; vetoed {len(vetoed)} proposal(s)",
        data={"vetoed": vetoed, "decisions": decisions},
    )

def get_senate_view(state: GameState, viewer_player_id: str) -> dict:
    """返回 GUI 元老院只读视图，不执行提案、投票或结算业务。"""
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

        senate_result = state.get_phase_result("senate")
        result_data = senate_result.get("data", {}) if isinstance(senate_result, dict) else {}
        proposals = _submitted_proposal_rows(state)
        proposal_options = _build_proposal_options(state, info)
        if not proposals and result_data:
            proposals = []
            for proposal in result_data.get("passed_proposals_snapshot", []) or []:
                row = proposal.copy()
                row["label"] = _proposal_label(state, proposal)
                row["result"] = "passed"
                proposals.append(row)
            for proposal in result_data.get("rejected_proposals_snapshot", []) or []:
                row = proposal.copy()
                row["label"] = _proposal_label(state, proposal)
                row["result"] = "rejected"
                proposals.append(row)
        player_votes = state.get_senate_votes_copy().get(viewer_player_id, {})
        voted_all = bool(proposals) and all(proposal.get("id") in player_votes for proposal in proposals)
        if result_data:
            current_step = "results"
        elif not proposals:
            current_step = "proposal"
        elif voted_all:
            current_step = "tribune_veto"
        else:
            current_step = "senate_vote"
        actionable = current_phase_id == "senate" and state.is_current_player(viewer_player_id)
        can_create = actionable and current_step == "proposal" and len(proposal_options) > 0
        viewer_has_tribune = _viewer_has_tribune(state, viewer_player_id)

        data = {
            "phase_id": "senate",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": current_phase_id == "senate",
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "interaction_mode": "interactive" if current_phase_id == "senate" else "readonly",
            "current_step": current_step,
            "actionable": actionable,
            "can_create_proposal": can_create,
            "can_vote": actionable and current_step == "senate_vote" and len(proposals) > 0,
            "can_veto": actionable and current_step == "tribune_veto" and viewer_has_tribune,
            "can_auto_veto": actionable and current_step == "tribune_veto" and not viewer_has_tribune,
            "viewer_has_tribune": viewer_has_tribune,
            "can_resolve": actionable and current_step == "tribune_veto",
            "can_advance": current_step == "results",
            "summary": {
                "title": "元老院议事",
                "status": current_step,
                "message": "执政官提案 → 元老院表决 → 保民官否决 → 法案公示与政府运作",
                "faction_leader_count": len(info.get("faction_leaders", [])),
                "active_foreign_war_count": len(active_foreign_wars),
                "war_threat_count": len(war_threats),
                "pending_peace_treaty_count": len(pending_peace_treaties),
                "pending_contract_count": len(pending_contracts),
                "proposal_option_count": len(proposal_options),
                "submitted_proposal_count": len(proposals),
            },
            "faction_leaders": info.get("faction_leaders", []),
            "presiding_officer": info.get("presiding_officer"),
            "active_foreign_wars": active_foreign_wars,
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace_treaties,
            "governor_vacancies": governor_vacancies,
            "pending_contracts": pending_contracts,
            "proposal_options": proposal_options,
            "submitted_proposals": proposals,
            "senate_result": senate_result or {},
            "seat_shares": _seat_share_rows(state),
            "warnings": [{
                "type": "info",
                "key": "senate.phase5a",
                "message": "当前开放 Phase 5A 执政官提案；表决、否决与结算由后续子环节接入。",
            }],
            "disabled_reason": "" if actionable else "当前不是元老院阶段或当前行动玩家，暂不可操作。",
        }
        return api_response(True, "Senate phase view refreshed", data)
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



def propose_many(state: GameState, player_id: str, proposals: List[Dict[str, Any]]) -> dict:
    """Record a batch of GUI-selected senate proposals."""
    if not state:
        return api_response(False, "无效的游戏状态")
    if not proposals:
        return api_response(False, "未选择任何法案")
    created = []
    errors = []
    for spec in proposals:
        proposal_type = spec.get("type")
        params = spec.get("params", {}) or {}
        result = propose(state, player_id, proposal_type, **params)
        if result.get("success"):
            created.append({
                "proposal_id": result.get("data", {}).get("proposal_id"),
                "type": proposal_type,
            })
        else:
            errors.append(result.get("message", "提案失败"))
    if errors and not created:
        return api_response(False, "提交法案失败", data={"created": created}, errors=errors)
    return api_response(
        True,
        f"已提交 {len(created)} 项法案",
        data={"created": created, "errors": errors},
        errors=errors,
    )


def advance_senate_phase(state: GameState, player_id: str) -> dict:
    """Mark senate complete and advance the GUI shell to combat."""
    if not state:
        return api_response(False, "Invalid game state")
    if not state.is_current_player(player_id):
        return api_response(False, "Current player mismatch")
    if not state.get_phase_result("senate"):
        return api_response(False, "Senate result is not ready")
    state.mark_phase_executed("senate")
    return api_response(True, "Advanced to combat phase", data={"next_phase_id": "combat"})

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
