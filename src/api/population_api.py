# src/api/population_api.py
"""
人口阶段 API 函数 - 完整实现
"""
import logging
import random
from typing import List, Dict, Any, Optional

from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n
from src.core.entities.figure import Figure, ClassTier, OfficeTerm


def campaign(
    state: GameState,
    player_id: str,
    figure_id: int,
    amount: int,
    bypass_permission: bool = False
) -> dict:
    """
    举办庆典，消耗人物财富，增加人气。
    权限：当前玩家，且人物属于当前玩家派系（除非 bypass_player_check=True）。
    """
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)

    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    if not bypass:
        if figure.faction_id != player.faction_id:
            return api_response(False, i18n.get("error_figure_not_in_your_faction"))

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    if figure.wealth < amount:
        return api_response(False, i18n.get("error_insufficient_wealth", wealth=figure.wealth))

    # 执行庆典：扣财富，加人气，更新影响力
    figure.wealth -= amount
    figure.popularity += amount
    figure.update_influence()

    state.record_population_campaign(player_id, figure_id, amount)

    message = i18n.get("info_campaign_success", name=figure.get_formal_name(), amount=amount)
    state.log_event(
        f"庆典: {figure.name} 花费 {amount}，人气 +{amount}",
        extra={"figure_id": figure_id, "amount": amount}
    )
    return api_response(True, message, data={"figure_id": figure_id, "amount": amount})


def vote(
    state: GameState,
    player_id: str,
    office: str,
    figure_id: int,
    bypass_permission: bool = False
) -> dict:
    """
    为指定公职的候选人投票。
    权限：当前玩家（除非 bypass_player_check=True）。
    规则：每个玩家在每个官职只能投一次，重复投票将报错。
    """
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)

    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 验证公职名称
    valid_offices = ["consul", "censor", "praetor", "quaestor", "tribune"]
    if office not in valid_offices:
        return api_response(False, i18n.get("error_invalid_office"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    # 检查候选人资格
    cand_result = get_candidates(state)
    if cand_result["success"]:
        candidates = cand_result["data"].get(office, [])
        if not any(c["id"] == figure_id for c in candidates):
            return api_response(False, i18n.get("error_figure_not_candidate"))

    if not state.record_population_vote(
        player_id,
        office,
        figure_id,
        replace=bypass_permission
    ):
        return api_response(False, i18n.get("error_already_voted", office=office.upper()))

    message = i18n.get("info_vote_recorded", office=office.upper(), name=figure.get_formal_name())
    state.log_event(
        f"投票: 玩家 {player_id} 为 {office} 投给 {figure.name}",
        extra={"player_id": player_id, "office": office, "figure_id": figure_id}
    )
    return api_response(True, message, data={"office": office, "figure_id": figure_id})


def get_candidates(state: GameState) -> dict:
    """
    获取所有公职的候选人列表（结构化数据）。
    按官职优先级从高到低处理，每个官职从所有符合资格且未被更高官职录用的人选中选出前N名。
    """
    office_priority = ["consul", "censor", "praetor", "quaestor", "tribune"]  # 从高到低
    final_data = {office: [] for office in office_priority}
    used_figure_ids = set()  # 已入选更高官职的人物ID

    current_turn = state.turn.turn_number

    for office in office_priority:
        # 收集所有存活且未占用且符合该官职资格的人物
        candidates = []
        for fig in state.get_living_members():
            if fig.is_absent:
                continue
            if fig.id in used_figure_ids:
                continue
            can_hold, _ = fig.can_hold_office(office, current_turn, state.config)
            if can_hold:
                candidates.append(fig)

        # 按资格属性排序
        sorted_candidates = sorted(
            candidates,
            key=lambda fig: fig.get_qualification_attribute(office),
            reverse=True
        )

        # 取前N名
        num_candidates = state.config.get("political_rules", {}).get("candidates_per_election", {}).get(office, 2)
        top_candidates = sorted_candidates[:num_candidates]

        # 记录录用者
        for fig in top_candidates:
            used_figure_ids.add(fig.id)

        # 构建输出列表
        cand_list = []
        for fig in top_candidates:
            cand_list.append({
                "id": fig.id,
                "name": fig.get_formal_name(),
                "faction_id": fig.faction_id,
                "faction_name": state.get_faction(fig.faction_id).name if fig.faction_id else "无",
                "martial": fig.martial,
                "intelligence": fig.intelligence,
                "charisma": fig.charisma,
                "zeal": fig.zeal,
            })
        final_data[office] = cand_list

    message = _format_candidates_message(final_data)
    return api_response(True, message, data=final_data)


def _get_eligible_for_office(state: GameState, office_type: str) -> List[Figure]:
    """获取指定公职的合格候选人（复用原逻辑）"""
    current_turn = state.turn.turn_number
    eligible = []
    for fig in state.get_living_members():
        if fig.is_absent:  # 不在罗马不能参选
            continue
        can_hold, _ = fig.can_hold_office(office_type, current_turn, state.config)
        if can_hold:
            eligible.append(fig)
    return eligible


def _format_candidates_message(data: Dict[str, List[Dict]]) -> str:
    """格式化候选人消息，与设计文档一致（包括图标、缩进、属性）"""
    lines = []
    office_names = {
        "consul": "🏛️ CONSUL",
        "censor": "📜 CENSOR",
        "praetor": "⚖ PRAETOR",
        "quaestor": "💰 QUAESTOR",
        "tribune": "🛡️ TRIBUNE"
    }
    for office, cands in data.items():
        # 每个官职标题一行
        lines.append(f"\n   {office_names.get(office, office.upper())}: ")
        if not cands:
            # 若无候选人，可选择不显示或显示占位，当前可能不显示该官职，但设计文档要求显示标题？我们保持现状。
            continue
        for c in cands:
            faction_disp = f"({c['faction_name']})" if c['faction_name'] != "无" else ""
            # 缩进6空格，格式：ID:1 姓名 (派系) 军略X 智略X 魅力X 热忱X
            lines.append(
                f"      ID:{c['id']} {c['name']} {faction_disp} "
                f"军略{c['martial']} 智略{c['intelligence']} 魅力{c['charisma']} 热忱{c['zeal']}"
            )
    if not lines:
        return "\n   📋 当前无候选人"
    return "\n".join(lines)

def resolve_election(state: GameState) -> dict:
    """
    统计投票结果，确定当选者，授予官职。
    根据人口阶段投票记录进行加权计票。
    """
    votes = state.get_population_votes()
    if not votes:
        return api_response(True, "无投票记录", data={})

    # 按公职分组投票
    votes_by_office = {}
    for player_id, office, fig_id in votes:
        votes_by_office.setdefault(office, []).append((player_id, fig_id))

    # 获取所有存活人物
    living_members = {m.id: m for m in state.get_living_members()}

    # 计算每个派系的总影响力（直接遍历所有存活人物）
    faction_influence = {}
    for member in state.get_living_members():
        if member.faction_id:
            faction_influence[member.faction_id] = faction_influence.get(member.faction_id, 0) + member.influence

    results = []
    elected_figures = []

    election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
    for office in election_order:
        office_votes = votes_by_office.get(office, [])
        if not office_votes:
            continue

        # 计算每位候选人获得的加权票数
        score = {}
        for player_id, fig_id in office_votes:
            player = state.get_player(player_id)
            if not player:
                continue
            faction_id = player.faction_id
            if not faction_id:
                continue
            influence = faction_influence.get(faction_id, 0)
            if influence > 0:
                score[fig_id] = score.get(fig_id, 0) + influence

        if not score:
            continue

        max_score = max(score.values())
        top_candidates = [fig_id for fig_id, s in score.items() if s == max_score]
        if len(top_candidates) > 1:
            winner_id = random.choice(top_candidates)
        else:
            winner_id = top_candidates[0]

        winner = living_members.get(winner_id)
        if winner:
            winner.office = office
            winner.update_influence()
            if office == "consul":
                # 将执政官加入 leader_ids（如果不在的话）
                if winner.id not in state.turn.leader_ids:
                    state.turn.leader_ids.append(winner.id)
            elected_figures.append(winner)

            faction = state.get_faction(winner.faction_id)
            faction_name = faction.name if faction else "无"
            results.append(f"      {office.upper()}: {winner.get_formal_name()} ({faction_name})")
            state.log_event(
                f"选举结果: {office} 当选者 {winner.name}",
                extra={"type": "election", "office": office, "figure_id": winner.id}
            )

    # 更新派系领袖
    for faction in state.factions.values():
        faction.update_faction_leader(state)

    if results:
        message = "\n   📋 选举结果：\n" + "\n".join(results)
    else:
        message = "   📋 无有效选举结果"

    return api_response(True, message, data={"elected": [f.id for f in elected_figures]})
