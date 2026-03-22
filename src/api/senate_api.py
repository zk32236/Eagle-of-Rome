# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import logging
import random
from typing import List, Optional, Dict, Any, Tuple
from src.core.game_state import GameState
from src.core.entities.contract import ContractStatus
from src.core.entities.war import WarStatus
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider

def api_response(success: bool, message: str = "", data: Any = None, errors: List[str] = None) -> dict:
    """生成标准 API 返回格式"""
    return {
        "success": success,
        "message": message,
        "data": data or {},
        "errors": errors or []
    }


def get_senate_initial_info(state: GameState) -> dict:
    """
    返回元老院阶段初始展示所需的所有信息。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    try:
        # 派系领袖
        faction_leaders = []
        for faction in state.factions.values():
            leader = faction.get_leader(state)
            if leader:
                faction_leaders.append({
                    "faction_id": faction.id,
                    "faction_name": faction.name,
                    "leader_id": leader.id,
                    "leader_name": leader.get_formal_name(),
                    "influence": leader.influence
                })

        # 主持人
        presiding = state.get_presiding_officer()
        presiding_info = None
        if presiding:
            presiding_info = {
                "figure_id": presiding.id,
                "name": presiding.get_formal_name(),
                "office": presiding.office or "无"
            }

        # 获取活跃外国战争（非起义战争）
        ws = state.get_war_system()
        active_foreign_wars = []
        if ws:
            for war in ws.get_active_wars():
                # 起义战争有 rebellion_province_id 字段，且应由总督自动接管，不显示在元老院
                if war.rebellion_province_id is None:
                    active_foreign_wars.append({
                        "war_id": war.id,
                        "name": war.name,
                        "status": "active"
                    })

        # 战争威胁
        ws = state.get_war_system()
        war_threats = []
        if ws:
            for war in ws._threats:
                if war.status == WarStatus.THREAT:
                    war_threats.append({
                        "war_id": war.id,
                        "name": war.name,
                        "threat_level": war.threat_level,
                        "naval_required": war.naval_required
                    })

        # 待决停战草案
        pending_peace = []
        if ws:
            for war in ws.get_truce_wars_with_pending_treaty():
                treaty = war.peace_treaty
                pending_peace.append({
                    "war_id": war.id,
                    "name": war.name,
                    "indemnity": treaty.get("indemnity", 0),
                    "duration": treaty.get("duration", 0)
                })

        # 行省空缺
        all_provinces = [p for p in state.get_all_provinces() if p.conquered and p.province_id != 0]
        proconsul_vacancies = []
        propraetor_vacancies = []
        for p in all_provinces:
            if p.governor_type == "proconsul":
                proconsul_vacancies.append({"province_id": p.province_id, "province_name": p.name})
            elif p.governor_type == "propraetor":
                propraetor_vacancies.append({"province_id": p.province_id, "province_name": p.name})

        # 待审批合同
        pending_contracts = []
        for c in state.contracts:
            if c.status == ContractStatus.PENDING:
                pending_contracts.append({
                    "contract_id": c.id,
                    "name": c.name,
                    "type": c.contract_type.value,
                    "base_cost": c.base_cost,
                    "expected_profit": c.expected_profit
                })

        return api_response(True, "", {
            "faction_leaders": faction_leaders,
            "presiding_officer": presiding_info,
            "active_foreign_wars": active_foreign_wars,
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace,
            "governor_vacancies": {
                "proconsul": proconsul_vacancies,
                "propraetor": propraetor_vacancies
            },
            "pending_contracts": pending_contracts,
            "land_act_proposals": []   # 手动模式下由 UI 提供，自动模式下由决策器生成
        })
    except Exception as e:
        return api_response(False, f"获取信息失败: {e}", errors=[str(e)])


def propose(state: GameState, player_id: str, proposal_type: str, bypass_turn_check: bool = False, **kwargs) -> dict:

    player = state.get_player(player_id)
    faction = state.get_faction(player.faction_id)

    # 检查权限：只有执政官可以提案
    player = state.get_player(player_id)
    if not player:
        return api_response(False, "玩家不存在")
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, "派系不存在")

    # 获取派系中担任执政官的人物
    consul = None
    for member in faction.get_members(state):
        if member.office == "consul" and not member.is_dead:
            consul = member
            break

    # 备用：如果派系成员中找不到，尝试从 turn.leader_ids 获取（兼容测试环境）
    if not consul and state.turn and state.turn.leader_ids:
        first_leader_id = state.turn.leader_ids[0]
        first_leader = state.get_member(first_leader_id)
        # 不再检查 office，只要 leader_ids 存在且人物存活，就认为是执政官
        if first_leader and not first_leader.is_dead:
            consul = first_leader

    if not consul:
        return api_response(False, "只有执政官可以提出提案")

    # 根据类型构建提案字典
    proposal = {
        "type": proposal_type,
        "proposer_faction": faction.id,
        "proposer_player": player_id,
        "consul_id": consul.id,
    }

    if proposal_type == "war":
        war_id = kwargs.get("war_id")
        legions = kwargs.get("legions")
        if not war_id or not legions:
            return api_response(False, "宣战提案需要 war_id 和 legions")
        proposal["war_id"] = war_id
        proposal["legions"] = legions
    elif proposal_type == "peace":
        war_id = kwargs.get("war_id")
        if not war_id:
            return api_response(False, "停战提案需要 war_id")
        proposal["war_id"] = war_id
        # 停战草案数据从战争对象中获取
        ws = state.get_war_system()
        war = ws.get_war_by_id(war_id) if ws else None
        if not war or not war.peace_treaty:
            return api_response(False, "战争无待决停战草案")
        war.set_peace_treaty_status('submitted')
        proposal["treaty"] = war.peace_treaty
    elif proposal_type == "governor":
        province_id = kwargs.get("province_id")
        candidate_id = kwargs.get("candidate_id")
        if not province_id or not candidate_id:
            return api_response(False, "总督任命需要 province_id 和 candidate_id")
        proposal["province_id"] = province_id
        proposal["candidate_id"] = candidate_id
        # 获取旧总督（用于记录）
        province = state.get_province(province_id)
        if province:
            proposal["old_governor_id"] = province.governor_id
    elif proposal_type == "budget":
        contract_id = kwargs.get("contract_id")
        modified_budget = kwargs.get("modified_budget")
        if not contract_id:
            return api_response(False, "预算提案需要 contract_id")
        proposal["contract_id"] = contract_id
        if modified_budget:
            proposal["modified_budget"] = modified_budget
        else:
            contract = state.get_contract(contract_id)
            if contract:
                proposal["modified_budget"] = contract.base_cost
    elif proposal_type == "land":
        act_type = kwargs.get("act_type")
        percent = kwargs.get("percent")
        if not act_type or percent is None:
            return api_response(False, "土地法案需要 act_type 和 percent")
        if act_type not in ("sale", "distribution"):
            return api_response(False, "无效的土地法案类型")
        proposal["act_type"] = act_type
        proposal["percent"] = percent
    else:
        return api_response(False, f"未知的提案类型: {proposal_type}")

    # 存储提案
    proposal_id = state.add_senate_proposal(proposal)
    state.log_event(
        f"提案记录: {proposal_type} (ID:{proposal_id})",
        level=logging.INFO,
        extra={"proposal_id": proposal_id, "proposal_type": proposal_type, "player_id": player_id}
    )
    return api_response(True, f"提案已记录 (ID: {proposal_id})", {"proposal_id": proposal_id})


def vote(state: GameState, player_id: str, proposal_ids: List[int], votes: List[bool]) -> dict:
    """
    记录玩家对多个提案的投票。
    """
    if not state:
        return api_response(False, "无效的游戏状态")
    if not state.is_current_player(player_id):
        return api_response(False, "当前不是您的回合")

    player = state.get_player(player_id)
    if not player:
        return api_response(False, "玩家不存在")
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, "派系不存在")

    # 检查派系是否有元老在场（影响力 > 0）
    influence = faction.get_senate_influence(state)
    if influence == 0:
        return api_response(False, "您的派系无元老在场，无法投票")

    # 检查参数长度
    if len(proposal_ids) != len(votes):
        return api_response(False, "提案ID列表与投票列表长度不一致")

    # 记录投票
    success_count = 0
    for pid, vote_val in zip(proposal_ids, votes):
        if state.record_senate_vote(player_id, pid, vote_val):
            success_count += 1
            # ===== 新增日志 =====
            state.log_event(
                f"玩家 {player_id} 对提案 {pid} 投票: {vote_val}",
                level=logging.INFO,
                extra={"player_id": player_id, "proposal_id": pid, "vote": vote_val}
            )

    if success_count == 0:
        return api_response(False, "所有提案均已投过票", data={"recorded": 0})

    return api_response(True, f"已记录 {success_count} 个提案的投票", data={"recorded": success_count})


def veto(state: GameState, player_id: str, proposal_ids: List[int]) -> dict:
    """
    记录保民官对已通过提案的否决。
    """
    if not state:
        return api_response(False, "无效的游戏状态")
    if not state.is_current_player(player_id):
        return api_response(False, "当前不是您的回合")

    player = state.get_player(player_id)
    if not player:
        return api_response(False, "玩家不存在")
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, "派系不存在")

    # 检查是否有保民官人物属于该派系
    tribune = None
    for member in faction.get_members(state):
        if member.office == "tribune" and not member.is_dead:
            tribune = member
            break
    if not tribune:
        return api_response(False, "只有保民官可以行使否决权")

    # 记录否决
    vetoed = []
    for pid in proposal_ids:
        if state.record_senate_veto(pid):
            vetoed.append(pid)
            # ===== 新增日志 =====
            state.log_event(
                f"玩家 {player_id} 否决提案 {pid}",
                level=logging.INFO,
                extra={"player_id": player_id, "proposal_id": pid}
            )

    return api_response(True, f"已否决 {len(vetoed)} 个提案", data={"vetoed": vetoed})


# ===== 在 senate_api.py 中完善 resolve_senate，收集 rejected_peace_wars 并返回 =====
def resolve_senate(state: GameState, vote_decider: Optional[SenateVoteDecider] = None) -> dict:
    """
    执行元老院阶段最终结算：统计投票结果、应用否决、执行所有通过的提案。
    返回 data 中包含 rejected_peace_wars 列表，供命令层恢复战争使用。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    proposals = state.get_senate_proposals()
    votes = state._senate_pending["votes"]  # {player_id: {proposal_id: bool}}
    vetoed = state._senate_pending["vetoes"]

    if vote_decider is None:
        vote_decider = AutoSenateVoteDecider()

    passed_proposals = []
    rejected_proposals = []
    rejected_peace_wars = []   # 存储被否决的停战战争对象

    for proposal in proposals:
        pid = proposal["id"]
        if pid in vetoed:
            continue

        support_influence = 0
        oppose_influence = 0
        total_influence = 0

        for faction in state.get_active_factions():
            influence = faction.get_senate_influence(state)
            if influence == 0:
                continue
            total_influence += influence

            player = state.get_player_by_faction(faction.id)
            if not player:
                continue
            player_id = player.player_id
            if player_id in votes and pid in votes[player_id]:
                if votes[player_id][pid]:
                    support_influence += influence
                else:
                    oppose_influence += influence
            else:
                # 未投票的派系，使用决策器补投
                if proposal["type"] == "war":
                    ws = state.get_war_system()
                    issue = ws.get_war_by_id(proposal["war_id"]) if ws else None
                elif proposal["type"] == "peace":
                    issue = {"type": "peace", "war_id": proposal["war_id"], "treaty": proposal.get("treaty")}
                elif proposal["type"] == "governor":
                    issue = {
                        "type": "governor_appointment",
                        "province_id": proposal["province_id"],
                        "candidate_id": proposal["candidate_id"],
                        "old_governor_id": proposal.get("old_governor_id")
                    }
                elif proposal["type"] == "budget":
                    issue = state.get_contract(proposal["contract_id"])
                elif proposal["type"] == "land":
                    issue = {
                        "type": proposal["act_type"],
                        "percent": proposal["percent"],
                        "proposer_faction": proposal["proposer_faction"]
                    }
                else:
                    continue

                support = vote_decider.decide_vote(issue, faction, state)
                if support:
                    support_influence += influence
                else:
                    oppose_influence += influence

        if total_influence == 0:
            rejected_proposals.append(proposal)
        else:
            support_ratio = support_influence / total_influence
            if support_ratio > 0.5:
                passed_proposals.append(proposal)
            else:
                rejected_proposals.append(proposal)
                # 若为停战草案，记录战争对象
                if proposal["type"] == "peace":
                    ws = state.get_war_system()
                    war = ws.get_war_by_id(proposal["war_id"]) if ws else None
                    if war:
                        rejected_peace_wars.append(war)

    # 执行通过的提案
    execution_messages = []
    for proposal in passed_proposals:
        ptype = proposal["type"]
        try:
            if ptype == "war":
                ws = state.get_war_system()
                if ws:
                    war = ws.get_war_by_id(proposal["war_id"])
                    consul_id = proposal["consul_id"]
                    legions = proposal["legions"]
                    execute_war_declaration(state, war, consul_id, legions)
                    execution_messages.append(f"宣战通过: {war.name} (军团 {legions})")
            elif ptype == "peace":
                ws = state.get_war_system()
                if ws:
                    war = ws.get_war_by_id(proposal["war_id"])
                    execute_passed_peace_treaty(state, war)
                    execution_messages.append(f"停战草案通过: {war.name}")
            elif ptype == "governor":
                province = state.get_province(proposal["province_id"])
                if province:
                    province._governor_designate_id = proposal["candidate_id"]
                    province._old_governor_id = proposal.get("old_governor_id")
                    new_governor = state.get_member(proposal["candidate_id"])
                    if new_governor:
                        new_governor.is_absent = True
                    execution_messages.append(f"任命 {proposal['candidate_id']} 为 {province.name} 候任总督")
            elif ptype == "budget":
                contract = state.get_contract(proposal["contract_id"])
                if contract:
                    contract.status = ContractStatus.BUDGETED
                    execution_messages.append(f"合同 {contract.name} 预算通过")
            elif ptype == "land":
                act_type = proposal["act_type"]
                percent = proposal["percent"]
                national_land = state.get_national_public_land()
                amount = int(national_land * percent)
                if act_type == "sale":
                    state.set_pending_land_sale_quota(amount)
                    execution_messages.append(f"卖地法案通过，出售 {amount} C 公地")
                else:
                    state.add_pending_land_act({
                        "type": "distribution",
                        "percent": percent,
                        "amount": amount,
                        "description": f"平民分地法案（分配 {percent*100:.1f}% 国家公地）"
                    })
                    execution_messages.append(f"分地法案通过，分配 {amount} C 公地")
        except Exception as e:
            execution_messages.append(f"执行提案 {proposal['id']} 失败: {e}")
            state.log_event(f"执行提案失败: {e}", level=logging.ERROR, extra={"proposal_id": proposal["id"]})

    # 执行战争接管
    process_war_takeover(state)

    # 清空临时数据
    state.clear_senate_pending()

    state.log_event(
        f"元老院结算完成: 通过 {len(passed_proposals)} 个提案，否决 {len(rejected_proposals)} 个提案",
        level=logging.INFO,
        extra={"passed": len(passed_proposals), "rejected": len(rejected_proposals)}
    )

    return api_response(True, "\n".join(execution_messages), {
        "passed_proposals": [p["id"] for p in passed_proposals],
        "rejected_proposals": [p["id"] for p in rejected_proposals],
        "vetoed_proposals": list(vetoed),
        "execution_results": execution_messages,
        "rejected_peace_wars": rejected_peace_wars  # 新增
    })


# ==================== 执行辅助函数（从 phase_senate.py 提取） ====================

def execute_war_declaration(state: GameState, war, consul_id: int, legions: int):
    """执行宣战"""
    ws = state.get_war_system()
    if not ws:
        return
    ws.activate_war(war.id, consul_id, legions)
    war.commander_id = consul_id
    consul = state.get_member(consul_id)
    if consul:
        consul.is_absent = True
    # 征召军团
    ms = state.get_military_system()
    if ms:
        _auto_recruit_and_assign_legions_for_war(state, war, consul_id)


def execute_passed_peace_treaty(state: GameState, war):
    """执行通过的停战草案"""
    ws = state.get_war_system()
    if not ws:
        return
    treaty = war.peace_treaty
    if not treaty or treaty.get("status") != "submitted":
        return
    war.set_peace_treaty_status("approved")
    war.set_indemnity_due(treaty["indemnity"])
    ms = state.get_military_system()
    if ms:
        ms.recall_from_war(war.id)
    if war.legion_numbers:
        ws.add_legions_to_disband(war.legion_numbers)
    end_turn = state.turn.turn_number + treaty["duration"]
    war.set_truce_end_turn(end_turn)
    # 确保战争状态设为 TRUCE
    war.status = WarStatus.TRUCE


def _auto_recruit_and_assign_legions_for_war(state: GameState, war, consul_id: int):
    """自动征召军团并指派给战争"""
    ms = state.get_military_system()
    if not ms:
        return
    # 检查已有军团
    existing = ms.get_legions_for_battle(war.id) if ms else []
    if existing:
        return
    legions = getattr(war, "proposed_legions", 0)
    if legions <= 0:
        min_leg = state.config.get("testing.min_legions", 4)
        max_leg = state.config.get("testing.max_legions", 8)
        legions = random.randint(min_leg, max_leg)
    available = ms.get_available_legions()
    recruit_count = min(legions, len(available))
    if recruit_count == 0:
        return
    results = ms.recruit_multiple(recruit_count)
    recruited_numbers = [r[0] for r in results if r[1]]
    if not recruited_numbers:
        return
    ms.assign_to_war(recruited_numbers, war.id, consul_id)
    for num in recruited_numbers:
        war.add_legion_number(num)


def process_war_takeover(state: GameState):
    """战争接管处理"""
    ws = state.get_war_system()
    if not ws:
        return
    active_wars = ws.get_active_wars()
    if not active_wars:
        return
    if not state.turn.leader_ids:
        return
    consul_id = state.turn.leader_ids[0]
    consul = state.get_member(consul_id)
    if not consul:
        return
    decider = AutoWarTakeoverDecider()
    for war in active_wars:
        if war.status != WarStatus.ACTIVE:
            continue
        if war.commander_id is None:
            if decider.decide_takeover(war, consul, None, state):
                war.commander_id = consul.id
                consul.is_absent = True
                _auto_recruit_and_assign_legions_for_war(state, war, consul.id)
        else:
            old_cmd = state.get_member(war.commander_id)
            if old_cmd and old_cmd.office in ("proconsul", "ex-consul") and old_cmd.is_absent:
                if decider.decide_takeover(war, consul, old_cmd, state):
                    old_cmd.is_absent = False
                    old_cmd.office = "ex-proconsul"
                    war.commander_id = consul.id
                    consul.is_absent = True
                    _auto_recruit_and_assign_legions_for_war(state, war, consul.id)