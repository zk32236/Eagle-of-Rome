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
from src.core.entities.figure import Figure

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

        # 获取行省
        province = state.get_province(province_id)
        if not province:
            return api_response(False, "行省不存在")
        if not province.conquered:
            return api_response(False, "行省未征服")

        # 获取候选人
        candidate = state.get_member(candidate_id)
        if not candidate or candidate.is_dead:
            return api_response(False, "候选人不存在或已死亡")

        # 资格校验：使用统一函数
        eligible_candidates = get_eligible_governor_candidates(state, province.governor_type)
        if candidate not in eligible_candidates:
            return api_response(False,
                                f"{candidate.get_formal_name()} 不符合 {province.governor_type} 行省总督的任职资格")

        # 检查是否已被任命
        if is_governor_position_occupied(state, candidate_id):
            return api_response(False, f"{candidate.get_formal_name()} 已被任命为其他行省总督")

        # 原有逻辑
        proposal["province_id"] = province_id
        proposal["candidate_id"] = candidate_id
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

    # ===== 新增：收集保民官否决的停战战争 =====
    ws = state.get_war_system()
    for proposal in proposals:
        pid = proposal["id"]
        if pid in vetoed and proposal["type"] == "peace":
            war = ws.get_war_by_id(proposal["war_id"]) if ws else None
            if war:
                rejected_peace_wars.append(war)

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
                    modified_budget = proposal.get("modified_budget")
                    if modified_budget and modified_budget != contract.base_cost:
                        # 保存原始预算（用于战斗力计算）
                        contract._original_budget = contract.base_cost
                        contract.base_cost = modified_budget
                        state.log_event(
                            f"预算提案通过: 合同 {contract.name} 预算从 {contract._original_budget} 更新为 {modified_budget}",
                            level=logging.INFO,
                            extra={"contract_id": contract.id, "old_budget": contract._original_budget,
                                   "new_budget": modified_budget}
                        )
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


# src/api/senate_api.py

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
    # ===== 新增：召回指挥官 =====
    if war.commander_id:
        commander = state.get_member(war.commander_id)
        if commander:
            commander.is_absent = False
            if commander.office == "proconsul":
                commander.office = "ex-consul"
            elif commander.office == "propraetor":
                commander.office = "ex-praetor"
            commander.update_influence()
            state.log_event(
                f"停战批准，指挥官 {commander.name} 返回罗马",
                level=logging.INFO,
                extra={"war_id": war.id, "commander_id": commander.id}
            )
            print(f"      🔄 停战批准，指挥官 {commander.get_formal_name()} 返回罗马")
            # 清空战争指挥官字段，避免停战期间残留
            war.commander_id = None
    # ==========================
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


# src/api/senate_api.py

# src/api/senate_api.py

def process_war_takeover(state: GameState, decider: Optional[AutoWarTakeoverDecider] = None):
    """战争接管处理：为无指挥官战争指派最高优先级指挥官，并在合适时替换已卸任的指挥官"""
    ws = state.get_war_system()
    if not ws:
        return

    active_wars = ws.get_active_wars()
    if not active_wars:
        return

    if decider is None:
        decider = AutoWarTakeoverDecider()

    # 获取可用的指挥官候选人（在罗马、未出征、未死亡，且官职为 consul 或 praetor）
    available_commanders = []
    for fig in state.get_living_members():
        if not fig.is_absent and not fig.is_dead and fig.office in ("consul", "praetor"):
            available_commanders.append(fig)

    state.log_event(
        f"[DEBUG] process_war_takeover: available_commanders = {[f.id for f in available_commanders]}",
        level=logging.DEBUG,
        extra={"function": "process_war_takeover", "available_ids": [f.id for f in available_commanders]}
    )

    if not available_commanders:
        for war in active_wars:
            if war.commander_id:
                old_cmd = state.get_member(war.commander_id)
                if old_cmd:
                    print(f"      ℹ️ 罗马无可用执政官或大法官，{war.name} 由 {old_cmd.name}（{old_cmd.office}）继续指挥。")
                else:
                    print(f"      ℹ️ 罗马无可用执政官或大法官，{war.name} 继续由原有指挥官指挥。")
        return

    # 按优先级排序：consul > praetor
    available_commanders.sort(key=lambda f: 0 if f.office == "consul" else 1)
    candidate = available_commanders[0]

    for war in active_wars:
        if war.status != WarStatus.ACTIVE:
            continue

        state.log_event(
            f"[DEBUG] process_war_takeover 前: war={war.id}, commander={war.commander_id}",
            level=logging.DEBUG,
            extra={"function": "process_war_takeover", "war_id": war.id, "commander_before": war.commander_id}
        )

        # 情况1：战争无指挥官
        if war.commander_id is None:
            if decider.decide_takeover(war, candidate, None, state):
                war.commander_id = candidate.id
                candidate.is_absent = True
                _auto_recruit_and_assign_legions_for_war(state, war, candidate.id)
                state.log_event(
                    f"{candidate.name} 接管战争 {war.name}",
                    level=logging.INFO,
                    extra={"war_id": war.id, "new_commander": candidate.id}
                )
                print(f"      ✅ {candidate.get_formal_name()} 接管 {war.name}")
            else:
                state.log_event(
                    f"[DEBUG] 决策器拒绝接管战争 {war.id}（无指挥官）",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "candidate": candidate.id}
                )
        # 情况2：战争已有指挥官
        else:
            old_cmd = state.get_member(war.commander_id)
            if old_cmd and old_cmd.is_absent:
                # 关键限制：只有旧指挥官是已卸任的总督（proconsul 或 propraetor）时才允许替换
                if old_cmd.office in ("proconsul", "propraetor"):
                    state.log_event(
                        f"[DEBUG] process_war_takeover 接管分支: war={war.id}, old_commander={old_cmd.id}, office={old_cmd.office}, is_absent={old_cmd.is_absent}, candidate={candidate.id}",
                        level=logging.DEBUG,
                        extra={"function": "process_war_takeover", "war_id": war.id, "old_commander": old_cmd.id, "candidate": candidate.id}
                    )
                    if decider.decide_takeover(war, candidate, old_cmd, state):
                        # 旧指挥官返回罗马
                        old_cmd.is_absent = False
                        if old_cmd.office == "proconsul":
                            old_cmd.office = "ex-consul"
                        elif old_cmd.office == "propraetor":
                            old_cmd.office = "ex-praetor"
                        old_cmd.update_influence()
                        # 新指挥官出征
                        war.commander_id = candidate.id
                        candidate.is_absent = True
                        _auto_recruit_and_assign_legions_for_war(state, war, candidate.id)
                        # 控制台输出
                        print(f"      ✅ {candidate.get_formal_name()} 接管 {war.name}，原指挥官 {old_cmd.get_formal_name()} 返回罗马")
                        state.log_event(
                            f"{candidate.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回罗马",
                            level=logging.INFO,
                            extra={"war_id": war.id, "new_commander": candidate.id, "old_commander": old_cmd.id}
                        )
                    else:
                        print(
                            f"      ✅ {candidate.get_formal_name()} 拒绝接管 {war.name}，原指挥官 {old_cmd.get_formal_name()} 继续指挥战争")
                        state.log_event(
                            f"[DEBUG] 决策器拒绝接管战争 {war.id}（已有指挥官 {old_cmd.id}）",
                            level=logging.DEBUG,
                            extra={"war_id": war.id, "old_commander": old_cmd.id, "candidate": candidate.id}
                        )
                else:
                    # 旧指挥官仍为现任官职（consul/praetor等），不允许替换
                    state.log_event(
                        f"[DEBUG] 战争 {war.id} 已有指挥官 {old_cmd.id}（{old_cmd.office}），且仍在任，不接管",
                        level=logging.DEBUG,
                        extra={"war_id": war.id, "old_commander": old_cmd.id, "office": old_cmd.office}
                    )
            else:
                state.log_event(
                    f"[DEBUG] 战争 {war.id} 已有指挥官 {old_cmd.id if old_cmd else None}，但不符合接管条件",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "commander_id": old_cmd.id if old_cmd else None}
                )

def assign_fleets_to_active_wars(state: GameState) -> dict:
    """
    为需要海战且尚无舰队的活跃战争指派可用舰队（补漏函数）。
    策略：按敌方海军力量降序排序，为每个战争分配尽可能多的可用舰队，
          直到舰队用尽或战争需求满足。不会重复指派已有舰队的战争。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    ws = state.get_war_system()
    if not ws:
        return api_response(False, "战争系统不可用")

    naval = state.naval_system
    if not naval:
        return api_response(False, "海军系统不可用")

    # 获取需要海战且当前没有舰队指派的活跃战争
    target_wars = [
        w for w in ws.get_active_wars()
        if w.naval_required and not w.assigned_fleet_ids
    ]
    if not target_wars:
        return api_response(True, "无需指派舰队")

    # 按敌方海军力量降序排列（强度高的优先）
    target_wars.sort(key=lambda w: getattr(w, 'enemy_naval_current', 0), reverse=True)

    # 获取所有可用舰队，并按战力降序排列
    available_fleets = naval.get_available_fleets()
    if not available_fleets:
        return api_response(True, "无可指派舰队")

    available_fleets.sort(key=lambda f: getattr(f, 'power', 0), reverse=True)

    assigned_details = []
    assigned_any = False

    for war in target_wars:
        # 再次检查，防止在循环中因其他原因已指派
        if war.assigned_fleet_ids:
            continue

        needed_power = getattr(war, 'enemy_naval_current', 0)
        if needed_power <= 0:
            needed_power = 1   # 若无敌方海军数据，默认至少需要1艘

        assigned_fleets = []
        total_power = 0
        fleets_to_remove = []

        for fleet in available_fleets:
            if total_power >= needed_power:
                break
            assigned_fleets.append(fleet.number)
            total_power += getattr(fleet, 'power', 0)
            fleets_to_remove.append(fleet)

        if not assigned_fleets:
            continue

        # 执行指派
        for fleet_num in assigned_fleets:
            if naval.assign_fleet_to_war(fleet_num, war.id, "naval"):
                war.assign_fleet(fleet_num)

        # 从可用列表中移除已指派的舰队
        for fleet in fleets_to_remove:
            available_fleets.remove(fleet)

        assigned_details.append({
            "war_id": war.id,
            "war_name": war.name,
            "fleets": assigned_fleets,
            "total_power": total_power,
            "needed_power": needed_power
        })
        assigned_any = True

        if not available_fleets:
            break

    if not assigned_any:
        return api_response(True, "无符合条件的战争需要舰队，或可用舰队不足")

    # 构建返回消息
    message_lines = []
    for detail in assigned_details:
        message_lines.append(
            f"⚓ 自动指派 {len(detail['fleets'])} 支舰队至 {detail['war_name']} "
            f"（当前海军战力 {detail['total_power']}，需 {detail['needed_power']}）"
        )
    message = "\n".join(message_lines)

    state.log_event(
        f"舰队指派补漏：{len(assigned_details)} 个战争获得舰队",
        level=logging.INFO,
        extra={"assigned_wars": [d["war_id"] for d in assigned_details]}
    )

    return api_response(True, message, data={"assigned": assigned_details})

def get_eligible_governor_candidates(state: GameState, governor_type: str) -> List[Figure]:
    """
    获取符合行省总督资格的人物列表（按卸任时间倒序排序）。
    仅用于手动模式校验。
    """
    if not state:
        return []

    required_office = "consul" if governor_type == "proconsul" else "praetor"
    candidates = []

    for fig in state.get_living_members():
        # 1. 必须存活且未出征（在罗马）
        if fig.is_absent or fig.is_dead:
            continue

        # 2. 当前不能有现任官职（允许以 "ex-" 开头的卸任官职）
        if fig.office is not None and not fig.office.startswith("ex-"):
            continue

        # 3. 必须在历史中担任过 required_office 且有卸任记录
        last_end_turn = None
        for term in fig.office_history:
            if term.office_type == required_office and term.end_turn is not None:
                if last_end_turn is None or term.end_turn > last_end_turn:
                    last_end_turn = term.end_turn

        if last_end_turn is None:
            continue

        candidates.append((fig, last_end_turn))

    # 按卸任回合倒序排序，若相同则按人物ID排序（保持稳定）
    candidates.sort(key=lambda x: (-x[1], x[0].id))
    return [fig for fig, _ in candidates]


def is_governor_position_occupied(state: GameState, figure_id: int) -> bool:
    """检查人物是否已被任命为其他行省的总督（候任或现任）。"""
    if not state:
        return False
    for province in state.get_all_provinces():
        if province.governor_id == figure_id or province.governor_designate_id == figure_id:
            return True
    return False