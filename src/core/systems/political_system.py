# src/core/systems/political_system.py
"""
PoliticalSystem collects senate and political business rules.
"""

import logging
import random
from typing import Any, Dict, List, Optional

from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.entities.contract import ContractStatus
from src.core.entities.figure import Figure
from src.core.entities.war import WarStatus


class PoliticalSystem:
    """Core senate proposal, voting, and execution rules."""

    def __init__(self, state):
        self.state = state

    def _result(self, success: bool, message: str = "", data: Any = None, errors: Optional[List[str]] = None) -> dict:
        return {
            "success": success,
            "message": message,
            "data": data or {},
            "errors": errors or [],
        }

    def build_initial_info(self) -> dict:
        if not self.state:
            return self._result(False, "无效的游戏状态")

        faction_leaders = []
        for faction in self.state.factions.values():
            leader = faction.get_leader(self.state)
            if leader:
                faction_leaders.append({
                    "faction_id": faction.id,
                    "faction_name": faction.name,
                    "leader_id": leader.id,
                    "leader_name": leader.get_formal_name(),
                    "influence": leader.influence,
                })

        presiding = self.state.get_presiding_officer()
        presiding_info = None
        if presiding:
            presiding_info = {
                "figure_id": presiding.id,
                "name": presiding.get_formal_name(),
                "office": presiding.office or "无",
            }

        ws = self.state.get_war_system()
        active_foreign_wars = []
        war_threats = []
        pending_peace = []
        if ws:
            for war in ws.get_active_wars():
                if war.rebellion_province_id is None:
                    active_foreign_wars.append({
                        "war_id": war.id,
                        "name": war.name,
                        "status": "active",
                    })

            for war in ws.get_threat_wars():
                war_threats.append({
                    "war_id": war.id,
                    "name": war.name,
                    "threat_level": war.threat_level,
                    "naval_required": war.naval_required,
                })

            for war in ws.get_truce_wars_with_pending_treaty():
                treaty = war.peace_treaty
                pending_peace.append({
                    "war_id": war.id,
                    "name": war.name,
                    "indemnity": treaty.get("indemnity", 0),
                    "duration": treaty.get("duration", 0),
                })

        all_provinces = [p for p in self.state.get_all_provinces() if p.conquered and p.province_id != 0]
        proconsul_vacancies = []
        propraetor_vacancies = []
        for province in all_provinces:
            entry = {"province_id": province.province_id, "province_name": province.name}
            if province.governor_type == "proconsul":
                proconsul_vacancies.append(entry)
            elif province.governor_type == "propraetor":
                propraetor_vacancies.append(entry)

        pending_contracts = []
        for contract in self.state.contracts:
            if contract.status == ContractStatus.PENDING:
                pending_contracts.append({
                    "contract_id": contract.id,
                    "name": contract.name,
                    "type": contract.contract_type.value,
                    "base_cost": contract.base_cost,
                    "expected_profit": contract.expected_profit,
                })

        return self._result(True, "", {
            "faction_leaders": faction_leaders,
            "presiding_officer": presiding_info,
            "active_foreign_wars": active_foreign_wars,
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace,
            "governor_vacancies": {
                "proconsul": proconsul_vacancies,
                "propraetor": propraetor_vacancies,
            },
            "pending_contracts": pending_contracts,
            "land_act_proposals": [],
        })

    def create_proposal(self, player_id: str, proposal_type: str, bypass_turn_check: bool = False, **kwargs) -> dict:
        if not self.state:
            return self._result(False, "无效的游戏状态")

        player = self.state.get_player(player_id)
        if not player:
            return self._result(False, "玩家不存在")
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return self._result(False, "派系不存在")

        consul = self._find_consul_for_faction(faction)
        if not consul:
            return self._result(False, "只有执政官可以提出提案")

        proposal = {
            "type": proposal_type,
            "proposer_faction": faction.id,
            "proposer_player": player_id,
            "consul_id": consul.id,
        }

        validation = self._populate_proposal(proposal, proposal_type, **kwargs)
        if not validation["success"]:
            return validation

        proposal_id = self.state.add_senate_proposal(proposal)
        self.state.log_event(
            f"提案记录: {proposal_type} (ID:{proposal_id})",
            level=logging.INFO,
            extra={"proposal_id": proposal_id, "proposal_type": proposal_type, "player_id": player_id},
        )
        return self._result(True, f"提案已记录 (ID: {proposal_id})", {"proposal_id": proposal_id})

    def record_vote(self, player_id: str, proposal_ids: List[int], votes: List[bool]) -> dict:
        if not self.state:
            return self._result(False, "无效的游戏状态")
        if not self.state.is_current_player(player_id):
            return self._result(False, "当前不是您的回合")

        player = self.state.get_player(player_id)
        if not player:
            return self._result(False, "玩家不存在")
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return self._result(False, "派系不存在")

        influence = faction.get_senate_influence(self.state)
        if influence == 0:
            return self._result(False, "您的派系无元老在场，无法投票")

        if len(proposal_ids) != len(votes):
            return self._result(False, "提案ID列表与投票列表长度不一致")

        success_count = 0
        for proposal_id, vote in zip(proposal_ids, votes):
            if self.state.record_senate_vote(player_id, proposal_id, vote):
                success_count += 1
                self.state.log_event(
                    f"玩家 {player_id} 对提案 {proposal_id} 投票: {vote}",
                    level=logging.INFO,
                    extra={"player_id": player_id, "proposal_id": proposal_id, "vote": vote},
                )

        if success_count == 0:
            return self._result(False, "所有提案均已投过票", {"recorded": 0})
        return self._result(True, f"已记录 {success_count} 个提案的投票", {"recorded": success_count})

    def record_veto(self, player_id: str, proposal_ids: List[int]) -> dict:
        if not self.state:
            return self._result(False, "无效的游戏状态")
        if not self.state.is_current_player(player_id):
            return self._result(False, "当前不是您的回合")

        player = self.state.get_player(player_id)
        if not player:
            return self._result(False, "玩家不存在")
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return self._result(False, "派系不存在")

        tribune = None
        for member in faction.get_members(self.state):
            if member.office == "tribune" and not member.is_dead:
                tribune = member
                break
        if not tribune:
            return self._result(False, "只有保民官可以行使否决权")

        vetoed = []
        for proposal_id in proposal_ids:
            if self.state.record_senate_veto(proposal_id):
                vetoed.append(proposal_id)
                self.state.log_event(
                    f"玩家 {player_id} 否决提案 {proposal_id}",
                    level=logging.INFO,
                    extra={"player_id": player_id, "proposal_id": proposal_id},
                )

        return self._result(True, f"已否决 {len(vetoed)} 个提案", {"vetoed": vetoed})

    def resolve_senate(
        self,
        vote_decider: Optional[SenateVoteDecider] = None,
        takeover_decider: Optional[AutoWarTakeoverDecider] = None,
    ) -> dict:
        if not self.state:
            return self._result(False, "无效的游戏状态")

        proposals = self.state.get_senate_proposals()
        vetoed = self.state.get_senate_vetoes_copy()
        vote_decider = vote_decider or AutoSenateVoteDecider()

        self.state.log_event(
            f"元老院结算开始: {len(proposals)} 个提案",
            level=logging.INFO,
            extra={"proposal_count": len(proposals)},
        )

        passed_proposals = []
        rejected_proposals = []
        rejected_peace_wars = []

        for proposal in proposals:
            result = self.calculate_vote_result(proposal, vote_decider)
            if result["vetoed"]:
                rejected_proposals.append(proposal)
                peace_war = self._get_peace_war(proposal)
                if peace_war:
                    rejected_peace_wars.append(peace_war)
            elif result["passed"]:
                passed_proposals.append(proposal)
            else:
                rejected_proposals.append(proposal)
                peace_war = self._get_peace_war(proposal) if result["total_influence"] > 0 else None
                if peace_war:
                    rejected_peace_wars.append(peace_war)

            self.state.log_event(
                f"提案 {proposal.get('id')} 表决完成: {'通过' if result['passed'] and not result['vetoed'] else '未通过'}",
                level=logging.INFO,
                extra={
                    "proposal_id": proposal.get("id"),
                    "proposal_type": proposal.get("type"),
                    "support": result["support_influence"],
                    "oppose": result["oppose_influence"],
                    "total": result["total_influence"],
                    "vetoed": result["vetoed"],
                },
            )

        execution_messages = []
        for proposal in passed_proposals:
            execution = self.execute_passed_proposal(proposal)
            if execution.get("message"):
                execution_messages.append(execution["message"])

        restored_peace_wars = self.restore_rejected_peace_wars(rejected_peace_wars)

        self.process_war_takeover(takeover_decider)
        self.state.clear_senate_pending()

        self.state.log_event(
            f"元老院结算完成: 通过 {len(passed_proposals)} 个提案，否决 {len(rejected_proposals)} 个提案",
            level=logging.INFO,
            extra={"passed": len(passed_proposals), "rejected": len(rejected_proposals)},
        )

        return self._result(True, "\n".join(execution_messages), {
            "passed_proposals": [p["id"] for p in passed_proposals],
            "rejected_proposals": [p["id"] for p in rejected_proposals],
            "vetoed_proposals": list(vetoed),
            "execution_results": execution_messages,
            "rejected_peace_wars": restored_peace_wars,
            "passed_proposals_snapshot": [p.copy() for p in passed_proposals],
            "rejected_proposals_snapshot": [p.copy() for p in rejected_proposals],
        })

    def build_issue_from_proposal(self, proposal: dict):
        ptype = proposal["type"]
        proposer_faction = proposal.get("proposer_faction")
        if ptype == "war":
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(proposal["war_id"]) if ws else None
            return {"type": "war", "war": war, "proposer_faction": proposer_faction}
        if ptype == "peace":
            return {
                "type": "peace",
                "war_id": proposal["war_id"],
                "treaty": proposal.get("treaty"),
                "proposer_faction": proposer_faction,
            }
        if ptype == "governor":
            return {
                "type": "governor",
                "province_id": proposal["province_id"],
                "candidate_id": proposal["candidate_id"],
                "old_governor_id": proposal.get("old_governor_id"),
                "proposer_faction": proposer_faction,
            }
        if ptype == "budget":
            return {
                "type": "contract",
                "contract": self.state.get_contract(proposal["contract_id"]),
                "proposer_faction": proposer_faction,
            }
        if ptype == "land":
            return {
                "type": "land",
                "act_type": proposal["act_type"],
                "percent": proposal["percent"],
                "proposer_faction": proposer_faction,
            }
        return None

    def calculate_vote_result(self, proposal: dict, vote_decider: Optional[SenateVoteDecider] = None) -> dict:
        vote_decider = vote_decider or AutoSenateVoteDecider()
        proposal_id = proposal["id"]
        vetoes = self.state.get_senate_vetoes_copy()
        if proposal_id in vetoes:
            return {
                "proposal": proposal,
                "passed": False,
                "vetoed": True,
                "support_influence": 0,
                "oppose_influence": 0,
                "total_influence": 0,
            }

        votes = self.state.get_senate_votes_copy()
        support_influence = 0
        oppose_influence = 0
        total_influence = 0

        for faction in self.state.get_active_factions():
            influence = faction.get_senate_influence(self.state)
            if influence == 0:
                continue
            total_influence += influence

            player = self.state.get_player_by_faction(faction.id)
            if not player:
                continue
            player_id = player.player_id
            player_votes = votes.get(player_id, {})
            if proposal_id in player_votes:
                support = player_votes[proposal_id]
            else:
                support = vote_decider.decide_vote(self.build_issue_from_proposal(proposal), faction, self.state)

            if support:
                support_influence += influence
            else:
                oppose_influence += influence

        passed = total_influence > 0 and support_influence / total_influence > 0.5
        return {
            "proposal": proposal,
            "passed": passed,
            "vetoed": False,
            "support_influence": support_influence,
            "oppose_influence": oppose_influence,
            "total_influence": total_influence,
        }

    def execute_passed_proposal(self, proposal: dict) -> dict:
        proposal_type = proposal["type"]
        try:
            if proposal_type == "war":
                ws = self.state.get_war_system()
                war = ws.get_war_by_id(proposal["war_id"]) if ws else None
                if war:
                    self.execute_war_declaration(war, proposal["consul_id"], proposal["legions"])
                    return {"success": True, "message": f"宣战通过: {war.name} (军团 {proposal['legions']})"}

            if proposal_type == "peace":
                war = self._get_peace_war(proposal)
                if war:
                    self.execute_passed_peace_treaty(war)
                    return {"success": True, "message": f"停战草案通过: {war.name}"}

            if proposal_type == "governor":
                province = self.state.get_province(proposal["province_id"])
                if province:
                    province.set_governor_designate(proposal["candidate_id"], proposal.get("old_governor_id"))
                    new_governor = self.state.get_member(proposal["candidate_id"])
                    if new_governor:
                        new_governor.is_absent = True
                    return {"success": True, "message": f"任命 {proposal['candidate_id']} 为 {province.name} 候任总督"}

            if proposal_type == "budget":
                contract = self.state.get_contract(proposal["contract_id"])
                if contract:
                    modified_budget = proposal.get("modified_budget")
                    if modified_budget and modified_budget != contract.base_cost:
                        contract._original_budget = contract.base_cost
                        contract.base_cost = modified_budget
                        self.state.log_event(
                            f"预算提案通过: 合同 {contract.name} 预算从 {contract._original_budget} 更新为 {modified_budget}",
                            level=logging.INFO,
                            extra={
                                "contract_id": contract.id,
                                "old_budget": contract._original_budget,
                                "new_budget": modified_budget,
                            },
                        )
                    contract.status = ContractStatus.BUDGETED
                    return {"success": True, "message": f"合同 {contract.name} 预算通过"}

            if proposal_type == "land":
                act_type = proposal["act_type"]
                percent = proposal["percent"]
                national_land = self.state.get_national_public_land()
                amount = int(national_land * percent)
                if act_type == "sale":
                    self.state.set_pending_land_sale_quota(amount)
                    return {"success": True, "message": f"卖地法案通过，出售 {amount} C 公地"}
                self.state.add_pending_land_act({
                    "type": "distribution",
                    "percent": percent,
                    "amount": amount,
                    "description": f"平民分地法案（分配 {percent * 100:.1f}% 国家公地）",
                })
                return {"success": True, "message": f"分地法案通过，分配 {amount} C 公地"}
        except Exception as exc:
            self.state.log_event(
                f"执行提案失败: {exc}",
                level=logging.ERROR,
                extra={"proposal_id": proposal.get("id")},
            )
            return {"success": False, "message": f"执行提案 {proposal.get('id')} 失败: {exc}"}

        return {"success": False, "message": ""}

    def execute_war_declaration(self, war, consul_id: int, legions: int):
        ws = self.state.get_war_system()
        if not ws:
            return
        ws.activate_war(war.id, consul_id, legions)
        war.commander_id = consul_id
        consul = self.state.get_member(consul_id)
        if consul:
            consul.is_absent = True
        self._auto_recruit_and_assign_legions_for_war(war, consul_id)
        self.state.log_event(
            f"宣战提案执行: {war.name}",
            level=logging.INFO,
            extra={"war_id": war.id, "consul_id": consul_id, "legions": legions},
        )

    def execute_passed_peace_treaty(self, war):
        ws = self.state.get_war_system()
        if not ws:
            return
        treaty = war.peace_treaty
        if not treaty or treaty.get("status") != "submitted":
            return
        war.set_peace_treaty_status("approved")
        war.set_indemnity_due(treaty["indemnity"])
        ms = self.state.get_military_system()
        if ms:
            ms.recall_from_war(war.id)
        if war.commander_id:
            commander = self.state.get_member(war.commander_id)
            if commander:
                commander.is_absent = False
                if commander.office == "proconsul":
                    commander.office = "ex-consul"
                elif commander.office == "propraetor":
                    commander.office = "ex-praetor"
                commander.update_influence()
                self.state.log_event(
                    f"停战批准，指挥官 {commander.name} 返回罗马",
                    level=logging.INFO,
                    extra={"war_id": war.id, "commander_id": commander.id},
                )
                print(f"      🔄 停战批准，指挥官 {commander.get_formal_name()} 返回罗马")
            war.commander_id = None
        if war.legion_numbers:
            ws.add_legions_to_disband(war.legion_numbers)
        end_turn = self.state.turn.turn_number + treaty["duration"]
        war.set_truce_end_turn(end_turn)
        war.status = WarStatus.TRUCE
        self.state.log_event(
            f"停战草案执行: {war.name}",
            level=logging.INFO,
            extra={"war_id": war.id, "end_turn": end_turn},
        )

    def restore_rejected_peace_wars(self, wars: List[Any]) -> List[Any]:
        if not wars:
            return []
        ws = self.state.get_war_system()
        if not ws:
            return []
        restored = []
        seen = set()
        for war in wars:
            if not war or war.id in seen:
                continue
            seen.add(war.id)
            if ws.restore_rejected_peace_treaty(war.id, preserve_commander=True):
                restored.append(war)
                self.state.log_event(
                    f"停战草案未通过，战争恢复: {war.name}",
                    level=logging.INFO,
                    extra={"war_id": war.id},
                )
        return restored

    def process_war_takeover(self, decider: Optional[AutoWarTakeoverDecider] = None):
        ws = self.state.get_war_system()
        if not ws:
            return

        active_wars = ws.get_active_wars()
        if not active_wars:
            return

        decider = decider or AutoWarTakeoverDecider()

        available_commanders = []
        for fig in self.state.get_living_members():
            if not fig.is_absent and not fig.is_dead and fig.office in ("consul", "praetor"):
                available_commanders.append(fig)

        self.state.log_event(
            f"[DEBUG] process_war_takeover: available_commanders = {[f.id for f in available_commanders]}",
            level=logging.DEBUG,
            extra={"function": "process_war_takeover", "available_ids": [f.id for f in available_commanders]},
        )

        if not available_commanders:
            for war in active_wars:
                if war.commander_id:
                    old_cmd = self.state.get_member(war.commander_id)
                    if old_cmd:
                        print(f"      ℹ️ 罗马无可用执政官或大法官，{war.name} 由 {old_cmd.name}（{old_cmd.office}）继续指挥。")
                    else:
                        print(f"      ℹ️ 罗马无可用执政官或大法官，{war.name} 继续由原有指挥官指挥。")
            return

        available_commanders.sort(key=lambda fig: 0 if fig.office == "consul" else 1)
        candidate = available_commanders[0]

        for war in active_wars:
            if war.status != WarStatus.ACTIVE:
                continue

            self.state.log_event(
                f"[DEBUG] process_war_takeover 前: war={war.id}, commander={war.commander_id}",
                level=logging.DEBUG,
                extra={"function": "process_war_takeover", "war_id": war.id, "commander_before": war.commander_id},
            )

            if war.commander_id is None:
                if decider.decide_takeover(war, candidate, None, self.state):
                    war.commander_id = candidate.id
                    candidate.is_absent = True
                    self._auto_recruit_and_assign_legions_for_war(war, candidate.id)
                    self.state.log_event(
                        f"{candidate.name} 接管战争 {war.name}",
                        level=logging.INFO,
                        extra={"war_id": war.id, "new_commander": candidate.id},
                    )
                    print(f"      ✅ {candidate.get_formal_name()} 接管 {war.name}")
                else:
                    self.state.log_event(
                        f"[DEBUG] 决策器拒绝接管战争 {war.id}（无指挥官）",
                        level=logging.DEBUG,
                        extra={"war_id": war.id, "candidate": candidate.id},
                    )
                continue

            old_cmd = self.state.get_member(war.commander_id)
            if old_cmd and old_cmd.is_absent:
                if old_cmd.office in ("proconsul", "propraetor"):
                    self.state.log_event(
                        f"[DEBUG] process_war_takeover 接管分支: war={war.id}, old_commander={old_cmd.id}, office={old_cmd.office}, is_absent={old_cmd.is_absent}, candidate={candidate.id}",
                        level=logging.DEBUG,
                        extra={
                            "function": "process_war_takeover",
                            "war_id": war.id,
                            "old_commander": old_cmd.id,
                            "candidate": candidate.id,
                        },
                    )
                    if decider.decide_takeover(war, candidate, old_cmd, self.state):
                        old_cmd.is_absent = False
                        if old_cmd.office == "proconsul":
                            old_cmd.office = "ex-consul"
                        elif old_cmd.office == "propraetor":
                            old_cmd.office = "ex-praetor"
                        old_cmd.update_influence()
                        war.commander_id = candidate.id
                        candidate.is_absent = True
                        self._auto_recruit_and_assign_legions_for_war(war, candidate.id)
                        print(f"      ✅ {candidate.get_formal_name()} 接管 {war.name}，原指挥官 {old_cmd.get_formal_name()} 返回罗马")
                        self.state.log_event(
                            f"{candidate.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回罗马",
                            level=logging.INFO,
                            extra={"war_id": war.id, "new_commander": candidate.id, "old_commander": old_cmd.id},
                        )
                    else:
                        print(f"      ✅ {candidate.get_formal_name()} 拒绝接管 {war.name}，原指挥官 {old_cmd.get_formal_name()} 继续指挥战争")
                        self.state.log_event(
                            f"[DEBUG] 决策器拒绝接管战争 {war.id}（已有指挥官 {old_cmd.id}）",
                            level=logging.DEBUG,
                            extra={"war_id": war.id, "old_commander": old_cmd.id, "candidate": candidate.id},
                        )
                else:
                    self.state.log_event(
                        f"[DEBUG] 战争 {war.id} 已有指挥官 {old_cmd.id}（{old_cmd.office}），且仍在任，不接管",
                        level=logging.DEBUG,
                        extra={"war_id": war.id, "old_commander": old_cmd.id, "office": old_cmd.office},
                    )
            else:
                self.state.log_event(
                    f"[DEBUG] 战争 {war.id} 已有指挥官 {old_cmd.id if old_cmd else None}，但不符合接管条件",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "commander_id": old_cmd.id if old_cmd else None},
                )

    def get_eligible_governor_candidates(self, governor_type: str) -> List[Figure]:
        if not self.state:
            return []

        required_office = "consul" if governor_type == "proconsul" else "praetor"
        candidates = []

        for fig in self.state.get_living_members():
            if fig.is_absent or fig.is_dead:
                continue
            if fig.office is not None and not fig.office.startswith("ex-"):
                continue

            last_end_turn = None
            for term in fig.office_history:
                if term.office_type == required_office and term.end_turn is not None:
                    if last_end_turn is None or term.end_turn > last_end_turn:
                        last_end_turn = term.end_turn

            if last_end_turn is not None:
                candidates.append((fig, last_end_turn))

        candidates.sort(key=lambda item: (-item[1], item[0].id))
        return [fig for fig, _ in candidates]

    def is_governor_position_occupied(self, figure_id: int) -> bool:
        if not self.state:
            return False
        for province in self.state.get_all_provinces():
            if province.governor_id == figure_id or province.governor_designate_id == figure_id:
                return True
        return False

    def _find_consul_for_faction(self, faction):
        for member in faction.get_members(self.state):
            if member.office == "consul" and not member.is_dead:
                return member

        if self.state.turn and self.state.turn.leader_ids:
            first_leader = self.state.get_member(self.state.turn.leader_ids[0])
            if first_leader and not first_leader.is_dead:
                return first_leader
        return None

    def _populate_proposal(self, proposal: dict, proposal_type: str, **kwargs) -> dict:
        if proposal_type == "war":
            war_id = kwargs.get("war_id")
            legions = kwargs.get("legions")
            if not war_id or not legions:
                return self._result(False, "宣战提案需要 war_id 和 legions")
            proposal["war_id"] = war_id
            proposal["legions"] = legions
            return self._result(True)

        if proposal_type == "peace":
            war_id = kwargs.get("war_id")
            if not war_id:
                return self._result(False, "停战提案需要 war_id")
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(war_id) if ws else None
            if not war or not war.peace_treaty:
                return self._result(False, "战争无待决停战草案")
            war.set_peace_treaty_status("submitted")
            proposal["war_id"] = war_id
            proposal["treaty"] = war.peace_treaty
            return self._result(True)

        if proposal_type == "governor":
            province_id = kwargs.get("province_id")
            candidate_id = kwargs.get("candidate_id")
            if not province_id or not candidate_id:
                return self._result(False, "总督任命需要 province_id 和 candidate_id")
            province = self.state.get_province(province_id)
            if not province:
                return self._result(False, "行省不存在")
            if not province.conquered:
                return self._result(False, "行省未征服")
            candidate = self.state.get_member(candidate_id)
            if not candidate or candidate.is_dead:
                return self._result(False, "候选人不存在或已死亡")
            if candidate not in self.get_eligible_governor_candidates(province.governor_type):
                return self._result(False, f"{candidate.get_formal_name()} 不符合 {province.governor_type} 行省总督的任职资格")
            if self.is_governor_position_occupied(candidate_id):
                return self._result(False, f"{candidate.get_formal_name()} 已被任命为其他行省总督")
            proposal["province_id"] = province_id
            proposal["candidate_id"] = candidate_id
            proposal["old_governor_id"] = province.governor_id
            return self._result(True)

        if proposal_type == "budget":
            contract_id = kwargs.get("contract_id")
            modified_budget = kwargs.get("modified_budget")
            if not contract_id:
                return self._result(False, "预算提案需要 contract_id")
            proposal["contract_id"] = contract_id
            if modified_budget:
                proposal["modified_budget"] = modified_budget
            else:
                contract = self.state.get_contract(contract_id)
                if contract:
                    proposal["modified_budget"] = contract.base_cost
            return self._result(True)

        if proposal_type == "land":
            act_type = kwargs.get("act_type")
            percent = kwargs.get("percent")
            if not act_type or percent is None:
                return self._result(False, "土地法案需要 act_type 和 percent")
            if act_type not in ("sale", "distribution"):
                return self._result(False, "无效的土地法案类型")
            proposal["act_type"] = act_type
            proposal["percent"] = percent
            return self._result(True)

        return self._result(False, f"未知的提案类型: {proposal_type}")

    def _get_peace_war(self, proposal: dict):
        if proposal.get("type") != "peace":
            return None
        ws = self.state.get_war_system()
        return ws.get_war_by_id(proposal["war_id"]) if ws else None

    def _auto_recruit_and_assign_legions_for_war(self, war, consul_id: int):
        ms = self.state.get_military_system()
        if not ms:
            return
        existing = ms.get_legions_for_battle(war.id)
        if existing:
            return
        legions = getattr(war, "proposed_legions", 0)
        if legions <= 0:
            min_legions = self.state.config.get("testing.min_legions", 4)
            max_legions = self.state.config.get("testing.max_legions", 8)
            legions = random.randint(min_legions, max_legions)
        available = ms.get_available_legions()
        recruit_count = min(legions, len(available))
        if recruit_count == 0:
            return
        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [number for number, success, *_ in results if success]
        if not recruited_numbers:
            return
        ms.assign_to_war(recruited_numbers, war.id, consul_id)
        for number in recruited_numbers:
            war.add_legion_number(number)
