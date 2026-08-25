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


def _tribune_absent_guard(figure) -> bool:
    """ODR-WP-D-01 防线 2 共享 guard（外部模块用）：在职保民官不得置位 absent。

    返回 True=允许置位；False=拒绝（fail-closed：office==tribune 且未死亡）。
    政治系统内部置位统一走 PoliticalSystem._set_absent（含日志）；本函数供
    senate_api / war_system / scenario_loader 等外部置位点内联防御。
    """
    return not (figure.office == "tribune" and not figure.is_dead)


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
            presiding_faction = self.state.get_faction(presiding.faction_id)
            presiding_info = {
                "figure_id": presiding.id,
                "name": presiding.get_formal_name(),
                "office": presiding.office or "无",
                "faction_id": presiding.faction_id,
                "faction_name": presiding_faction.name if presiding_faction else "",
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
        # 总督AI自动提名额外日志
        if proposal_type == "governor":
            province_id = kwargs.get("province_id")
            candidate_id = kwargs.get("candidate_id")
            province = self.state.get_province(province_id) if province_id else None
            candidate = self.state.get_member(candidate_id) if candidate_id else None
            self.state.log_event(
                f"总督AI自动提名: {candidate.get_formal_name() if candidate else str(candidate_id)} -> {province.name if province else str(province_id)}",
                extra={
                    "type": "governor_ai_auto_nominate",
                    "province_id": province_id,
                    "candidate_id": candidate_id,
                    "governor_type": province.governor_type if province else None,
                }
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

        # AU-R2-1（T3 收敛）：faction 内 eligible Tribune 查找统一委托
        # _find_tribune_for_faction（单一迭代范围 + 单一谓词，P2-05 分歧消除）
        tribune = self._find_tribune_for_faction(faction)
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
                    "type": "senate_vote_proposal_passed",
                },
            )

        execution_messages = []
        for proposal in passed_proposals:
            execution = self.execute_passed_proposal(proposal)
            if execution.get("message"):
                execution_messages.append(execution["message"])

        restored_peace_wars = self.restore_rejected_peace_wars(rejected_peace_wars)

        # P-7（AU-5）：结算循环完成、clear_senate_pending 之前快照 direct_actions，
        # 供 senate_api.resolve_senate 组装 public_announcement（公示持久化）。
        direct_actions = self.state.get_senate_direct_actions()

        # AU-R1-05a（C1，D-1 采纳）：resolve_senate 零 takeover mutation——隐藏的
        # process_war_takeover 调用已移除；AI 自动接管唯一触发点 = senate_api
        # auto_submit_proposals 尾部（Direct Action 语义，见 execute_ai_takeover_direct_action）。
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
            "direct_actions": direct_actions,
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
                # AU-R1-02b/c：reused 路径 provenance——从注册表读 vote_source（human 票默认 "human"；
                # AI 票经 AU-R1-02a 写回后为 "ai"）；旧存档缺注册表键 → 回退 "human"
                vote_source = self.state.get_senate_vote_source(player_id, proposal_id) or "human"
                decision_state = "reused"
            else:
                support = vote_decider.decide_vote(self.build_issue_from_proposal(proposal), faction, self.state)
                # AU-R1-02a（C3 幂等契约，frozen）：AI 票首次决策即持久化（created once →
                # persisted → Veto/resolve 复用同一存储）；record_senate_vote 重复返回 False
                # （理论不可达，因 :396 已判不存在）→ 不失败，按 reused 语义记日志继续。
                recorded = self.state.record_senate_vote(player_id, proposal_id, support, source="ai")
                vote_source = "ai"
                decision_state = "created" if recorded else "reused"
                if not recorded:
                    self.state.log_event(
                        f"[R1-C3] 幂等 guard: AI 票 {player_id}/{proposal_id} 已存在，按 reused 语义处理（不重掷）",
                        level=logging.INFO,
                        extra={"type": "senate_vote_idempotent", "player_id": player_id, "proposal_id": proposal_id},
                    )
            # AU-R1-02c/06a：决策级结构化日志（proposal_id/faction_id/vote/vote_source/decision_state 可溯源）
            self.state.log_event(
                f"元老院表决决策: proposal={proposal_id} faction={faction.id} vote={support}",
                level=logging.INFO,
                extra={
                    "type": "senate_vote_decision",
                    "proposal_id": proposal_id,
                    "faction_id": faction.id,
                    "vote": support,
                    "vote_source": vote_source,
                    "decision_state": decision_state,
                },
            )

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
                        self._set_absent(new_governor)
                    self.state.log_event(
                        f"候任总督设定: {new_governor.get_formal_name() if new_governor else proposal['candidate_id']} -> {province.name}",
                        extra={
                            "type": "governor_set_designate",
                            "province_id": proposal["province_id"],
                            "province_name": province.name,
                            "candidate_id": proposal["candidate_id"],
                            "candidate_name": new_governor.get_formal_name() if new_governor else None,
                        }
                    )
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
                # P-6（AU-7）：amount_C 为唯一权威消费值（不再 int(national_land * percent) 二次重推，
                # 消除双事实源漂移）；percent 为 _populate_proposal 派生存入的展示/连续性字段。
                act_type = proposal["act_type"]
                amount_C = proposal["amount_C"]
                percent = proposal.get("percent")
                if act_type == "sale":
                    self.state.set_pending_land_sale_quota(amount_C)
                    # WP-E F5：并行写入本年度出售总量（amount_C = P-6/AU-7 唯一权威值，零换算）
                    self.state.set_turn_land_sale_total(amount_C)
                    return {"success": True, "message": f"卖地法案通过，出售 {amount_C} C 公地"}
                self.state.add_pending_land_act({
                    "type": "distribution",
                    "percent": percent,
                    "amount": amount_C,
                    "description": f"平民分地法案（分配 {amount_C} C 国家公地）",
                })
                return {"success": True, "message": f"分地法案通过，分配 {amount_C} C 公地"}
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
            self._set_absent(consul)
        self._auto_recruit_and_assign_legions_for_war(war, consul_id)
        self.state.log_event(
            f"宣战提案执行: {war.name}",
            level=logging.INFO,
            extra={
                "type": "war_declaration_passed",
                "war_id": war.id,
                "war_name": war.name,
                "consul_id": consul_id,
                "legions": legions,
            },
        )

    def execute_passed_peace_treaty(self, war):
        ws = self.state.get_war_system()
        if not ws:
            return
        treaty = war.peace_treaty
        if not treaty or treaty.get("status") != "submitted":
            return
        release = ws.release_war_legions(
            war,
            remember_for_truce=True,
            disband_now=True,
        )
        if not release["success"]:
            self.state.log_event(
                f"停战批准失败，军团释放未完成: {war.name}",
                level=logging.ERROR,
                extra={
                    "type": "treaty_approval_lifecycle_failed",
                    "war_id": war.id,
                    "errors": release["errors"],
                },
            )
            return

        war.set_peace_treaty_status("approved")
        war.set_indemnity_due(treaty["indemnity"])
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
        end_turn = self.state.turn.turn_number + treaty["duration"]
        war.set_truce_end_turn(end_turn)
        war.status = WarStatus.TRUCE
        self.state.log_event(
            f"停战草案执行: {war.name}",
            level=logging.INFO,
            extra={
                "type": "treaty_approved",
                "war_id": war.id,
                "war_name": war.name,
                "indemnity": treaty.get("indemnity", 0),
                "duration": treaty.get("duration", 0),
                "end_turn": end_turn,
                "truce_recruit_target": release["target"],
                "disbanded_legions": release["disbanded"],
                "mobilized_count_after": war.mobilized_legion_count,
            },
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
                    extra={
                        "type": "treaty_rejected",
                        "war_id": war.id,
                        "war_name": war.name,
                        "faction_id": getattr(war, "declared_by", None),
                    },
                )
        return restored

    def execute_ai_takeover_direct_action(self, decider: Optional[AutoWarTakeoverDecider] = None) -> list:
        """AU-R1-05b：AI 自动接管走 Direct Action 语义（与 human takeover_war 同 mutation 路径）。

        - 判定需要接管的活跃外战（ACTIVE + 非起义 + 指挥官缺失 / 已死 / absent proconsul-propraetor）；
        - 候选 Consul 选择（living + office consul/praetor + 未 absent/未死 + consul 优先）；
        - 决策走 decider.decide_takeover（AI 自动化决策保留）；
        - mutation 统一走 execute_war_takeover_direct（FC-05 原子性：招募成功才回写 commander）；
        - 每条成功接管 record_senate_direct_action 写 provenance（trigger_source="ai_auto"，AU-R1-05c）；
        - 返回成功接管记录列表（供测试/日志断言）。

        **C1（G3，D-1 采纳）：严禁在 resolve_senate 内调用——唯一 AI 接管调用点 =
        senate_api.auto_submit_proposals 尾部（GUI session_store:1265 / CLI phase_senate:1025
        双入口共享同一活跃函数）。**
        """
        ws = self.state.get_war_system()
        if not ws:
            return []

        active_wars = ws.get_active_wars()
        if not active_wars:
            return []

        decider = decider or AutoWarTakeoverDecider()
        takeover_records = []

        for war in active_wars:
            if war.status != WarStatus.ACTIVE:
                continue
            if war.rebellion_province_id is not None:
                continue  # 起义战争由总督接管（与 human takeover_war 语义一致）

            old_cmd = self.state.get_member(war.commander_id) if war.commander_id else None
            needs_takeover = war.commander_id is None
            if old_cmd and not needs_takeover:
                if old_cmd.is_dead:
                    needs_takeover = True
                elif old_cmd.is_absent and old_cmd.office in ("proconsul", "propraetor"):
                    needs_takeover = True
            if not needs_takeover:
                self.state.log_event(
                    f"[R1] AI 接管跳过: war={war.id}（已有有效指挥官 {war.commander_id}）",
                    level=logging.DEBUG,
                    extra={"function": "execute_ai_takeover_direct_action", "war_id": war.id,
                           "commander_id": war.commander_id, "trigger_source": "ai_auto"},
                )
                continue

            # 候选 Consul：living + office consul/praetor + 未 absent/未死 + consul 优先
            candidates = [
                fig for fig in self.state.get_living_members()
                if not fig.is_absent and not fig.is_dead and fig.office in ("consul", "praetor")
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda fig: 0 if fig.office == "consul" else 1)
            candidate = candidates[0]

            if not decider.decide_takeover(war, candidate, old_cmd, self.state):
                self.state.log_event(
                    f"[R1] AI 决策器拒绝接管战争 {war.id}（candidate={candidate.id}）",
                    level=logging.DEBUG,
                    extra={"function": "execute_ai_takeover_direct_action", "war_id": war.id,
                           "candidate": candidate.id, "trigger_source": "ai_auto"},
                )
                continue

            previous_status = war.status.value if hasattr(war.status, "value") else str(war.status)
            if not self.execute_war_takeover_direct(war, candidate):
                self.state.log_event(
                    f"[R1] AI 接管失败（军团招募失败）: war={war.id}",
                    level=logging.DEBUG,
                    extra={"function": "execute_ai_takeover_direct_action", "war_id": war.id,
                           "candidate": candidate.id, "trigger_source": "ai_auto"},
                )
                continue
            resulting_status = war.status.value if hasattr(war.status, "value") else str(war.status)

            record = {
                "action_type": "takeover",
                "action": "takeover",
                "war_id": war.id,
                "war_name": war.name,
                "commander_id": candidate.id,
                "commander_name": candidate.get_formal_name(),
                "legions": list(getattr(war, "legion_numbers", []) or []),
                "trigger_source": "ai_auto",
                "previous_status": previous_status,
                "resulting_status": resulting_status,
            }
            self.state.record_senate_direct_action(record)
            self.state.log_event(
                f"AI 自动接管战争 {war.name}: {candidate.get_formal_name()}",
                level=logging.INFO,
                extra={
                    "type": "senate_takeover_direct_action",
                    "war_id": war.id,
                    "new_commander": candidate.id,
                    "trigger_source": "ai_auto",
                },
            )
            takeover_records.append(record)

        return takeover_records


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

    def _is_eligible_consul(self, member) -> bool:
        """Consul 单一资格谓词（AU-1）：在职 + 未死亡 + 未 absent。

        消费方（R2 收敛后）：_find_consul_for_faction 主循环 / fallback / _find_any_eligible_consul
        / resolve_proposal_control（senate_api._viewer_eligible_consul 已退役）——消除双事实源。
        """
        return member.office == "consul" and not member.is_dead and not member.is_absent

    def _is_eligible_tribune(self, member) -> bool:
        """Tribune 单一资格谓词（AU-4，按 ODR-WP-D-01 方案 B 语义——裁决 CLOSED 2026-08-23）。

        方案 B：在职 + 未死亡（is_absent 不参与判定）。
        法律语义（Owner 裁决）：保民官在职期间不能缺席（离开罗马城）——法律上 absent 对在职
        tribune 不存在；防线 1（派遣/任命路径排除在职 tribune）+ 防线 2（_set_absent guard）
        兜底，正常路径下在职 tribune 永不为 absent。
        消费方（R2 收敛后）：_find_tribune_for_faction / _find_any_eligible_tribune /
        resolve_veto_control（senate_api._current_tribune 薄委托 / _viewer_has_tribune 已退役）。
        """
        return member.office == "tribune" and not member.is_dead

    def _set_absent(self, figure) -> bool:
        """防线 2（ODR-WP-D-01）：在职保民官置位 absent → fail-closed 拒绝。

        法律语义：保民官在职期间不能离开罗马城，absent 对在职 tribune 不存在。
        政治系统内所有 absent 置位路径统一经此方法（置位统一管理点）；被拒时保持原状态
        并记日志（fail-closed：不产生非法状态）。返回 True=已置位；False=被 guard 拒绝。
        """
        if figure.office == "tribune" and not figure.is_dead:
            if self.state:
                self.state.log_event(
                    f"[ODR-WP-D-01] 防线2 guard: 在职保民官 {figure.name} 不得置位 absent（拒绝）",
                    level=logging.WARNING,
                    extra={"type": "tribune_absent_guard", "figure_id": figure.id},
                )
            return False
        figure.is_absent = True
        return True

    def _find_consul_for_faction(self, faction):
        for member in faction.get_members(self.state):
            if self._is_eligible_consul(member):
                return member

        if self.state.turn and self.state.turn.leader_ids:
            first_leader = self.state.get_member(self.state.turn.leader_ids[0])
            # fallback（AU-R2-1 收敛）：保留 leader 存在性 + faction 归属检查，资格判定
            # 统一委托 _is_eligible_consul 单一谓词（原四条件内联退役——任一不满足即
            # fail-closed return None，非执政官派系不再误判通过；行为等价）。
            if (
                first_leader
                and first_leader.faction_id == faction.id
                and self._is_eligible_consul(first_leader)
            ):
                return first_leader
        return None

    def _find_any_eligible_consul(self):
        """全局首个 eligible Consul（AI proposer 语义，AU-R2-1）。

        替代 C3（senate_api.auto_submit_proposals 内联主循环 + leader fallback）/
        C4（phase_senate._handle_step_1 内联）——单一迭代范围（全局 living members）+
        单一谓词 _is_eligible_consul；无命中 → None。
        """
        for member in self.state.get_living_members():
            if self._is_eligible_consul(member):
                return member
        return None

    def _find_tribune_for_faction(self, faction):
        """faction 内首个 eligible Tribune（人类 veto 语义，AU-R2-1）。

        替代 T3（record_veto faction 内迭代）——faction.get_members（仅活成员）+
        单一谓词 _is_eligible_tribune；无命中 → None（fail-closed「只有保民官可以行使否决权」）。
        """
        for member in faction.get_members(self.state):
            if self._is_eligible_tribune(member):
                return member
        return None

    def _find_any_eligible_tribune(self):
        """全局首个 eligible Tribune（AI 否决语义，AU-R2-1）。

        替代 T2（senate_api._current_tribune 全局迭代）/ T5（phase_senate._get_tribune
        内联）——单一迭代范围（全局 living members）+ 单一谓词 _is_eligible_tribune。
        """
        for member in self.state.get_living_members():
            if self._is_eligible_tribune(member):
                return member
        return None

    def resolve_proposal_control(self, viewer_player_id: str) -> dict:
        """单一权威提案控制解析（R2 冻结符号，SA §1.2）。

        输出 {mode: HUMAN|AI|NONE, actor, authority_reason}：
        - viewer 缺失 → NONE(missing_viewer)；faction 缺失 → NONE(missing_faction)；
        - faction 内 eligible Consul → HUMAN(human_eligible_consul)；
        - 全局 eligible Consul（AI proposer 独立路径）→ AI(ai_eligible_consul)；
        - 否则 NONE(no_eligible_consul)——fail-closed，不 fallback 猜测。
        消费方（senate_api.get_senate_view / store / 测试）只读结果，禁独立重算。
        """
        viewer = self.state.get_player(viewer_player_id)
        if not viewer:
            return {"mode": "NONE", "actor": None, "authority_reason": "missing_viewer"}
        faction = self.state.get_faction(viewer.faction_id)
        if not faction:
            return {"mode": "NONE", "actor": None, "authority_reason": "missing_faction"}
        consul = self._find_consul_for_faction(faction)
        if consul:
            return {"mode": "HUMAN", "actor": consul.id, "authority_reason": "human_eligible_consul"}
        ai_consul = self._find_any_eligible_consul()
        if ai_consul:
            return {"mode": "AI", "actor": ai_consul.id, "authority_reason": "ai_eligible_consul"}
        return {"mode": "NONE", "actor": None, "authority_reason": "no_eligible_consul"}

    def resolve_veto_control(self, viewer_player_id: str) -> dict:
        """单一权威否决控制解析（R2 冻结符号，SA §1.2）。

        输出 {mode: HUMAN|AI|NONE, actor, authority_reason}：
        - viewer 缺失 → NONE(missing_viewer)；faction 缺失 → NONE(missing_faction)；
        - faction 内 eligible Tribune → HUMAN(human_eligible_tribune)；
        - 全局 eligible Tribune（AI 否决语义）→ AI(ai_eligible_tribune)；
        - 否则 NONE(no_eligible_tribune)——fail-closed（D-R2-05）。
        """
        viewer = self.state.get_player(viewer_player_id)
        if not viewer:
            return {"mode": "NONE", "actor": None, "authority_reason": "missing_viewer"}
        faction = self.state.get_faction(viewer.faction_id)
        if not faction:
            return {"mode": "NONE", "actor": None, "authority_reason": "missing_faction"}
        tribune = self._find_tribune_for_faction(faction)
        if tribune:
            return {"mode": "HUMAN", "actor": tribune.id, "authority_reason": "human_eligible_tribune"}
        ai_tribune = self._find_any_eligible_tribune()
        if ai_tribune:
            return {"mode": "AI", "actor": ai_tribune.id, "authority_reason": "ai_eligible_tribune"}
        return {"mode": "NONE", "actor": None, "authority_reason": "no_eligible_tribune"}

    def _populate_proposal(self, proposal: dict, proposal_type: str, **kwargs) -> dict:
        if proposal_type == "war":
            war_id = kwargs.get("war_id")
            legions = kwargs.get("legions")
            if not war_id or not legions:
                return self._result(False, "宣战提案需要 war_id 和 legions")
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(war_id) if ws else None
            if not war:
                return self._result(False, "战争不存在")
            # 共享 helper（D-1：lazy import 避免跨模块循环导入；值域单一来源 §6.3）
            from src.api.senate_api import _legion_options_for_war
            options = _legion_options_for_war(self.state, war)
            if options is not None:
                if not isinstance(legions, int):
                    return self._result(False, "legions 必须为整数")
                if legions < options["min"]:
                    return self._result(False, "宣战至少需要 1 个军团")
                if legions > options["max"]:
                    return self._result(False, "可用军团不足")
                existing_reserved = sum(
                    p["legions"] for p in self.state.get_senate_proposals()
                    if p.get("type") == "war" and p.get("legions")
                )
                if existing_reserved + legions > options["max"]:
                    return self._result(False, "可用军团不足")
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
            contract = self.state.get_contract(contract_id)
            if not contract:
                return self._result(False, "合同不存在")
            # 共享 helper（D-1：lazy import 避免跨模块循环导入；值域单一来源 §6.3）
            from src.api.senate_api import _budget_range_for_contract
            range_info = _budget_range_for_contract(self.state, contract)
            if range_info is not None and modified_budget is not None:
                if not (isinstance(modified_budget, int)
                        or (isinstance(modified_budget, float) and modified_budget.is_integer())):
                    return self._result(False, "预算金额必须为整数")
                if modified_budget < range_info["min"]:
                    return self._result(False, "预算金额低于允许范围")
                if modified_budget > range_info["max"]:
                    return self._result(False, "预算金额超过允许范围")
                if (modified_budget - range_info["min"]) % range_info["step"] != 0:
                    return self._result(False, "预算金额不符合步进要求")
            proposal["contract_id"] = contract_id
            if modified_budget is not None:
                proposal["modified_budget"] = modified_budget
            else:
                proposal["modified_budget"] = contract.base_cost
            return self._result(True)

        if proposal_type == "land":
            # P-5（AU-7）：amount_C 为唯一权威输入（int），percent 仅派生存入；
            # percent 不再作为独立输入参数接受（冻结 D-01 canonical conversion）。
            act_type = kwargs.get("act_type")
            amount_C = kwargs.get("amount_C")
            if not act_type or amount_C is None:
                return self._result(False, "土地法案需要 act_type 和 amount_C")
            if act_type not in ("sale", "distribution"):
                return self._result(False, "无效的土地法案类型")
            if not (isinstance(amount_C, int) or (isinstance(amount_C, float) and amount_C.is_integer())):
                return self._result(False, "土地数量必须为整数")
            amount_C = int(amount_C)
            national_land = self.state.get_national_public_land()
            if amount_C < 1:
                return self._result(False, "土地数量必须至少为 1 C")
            if amount_C > national_land:
                return self._result(False, "土地数量超过国家公地总量")
            proposal["act_type"] = act_type
            proposal["amount_C"] = amount_C
            proposal["percent"] = amount_C / national_land if national_land else 0.0
            return self._result(True)

        return self._result(False, f"未知的提案类型: {proposal_type}")

    def _get_peace_war(self, proposal: dict):
        if proposal.get("type") != "peace":
            return None
        ws = self.state.get_war_system()
        return ws.get_war_by_id(proposal["war_id"]) if ws else None

    def _auto_recruit_and_assign_legions_for_war(self, war, consul_id: int):
        ws = self.state.get_war_system()
        if not ws:
            return
        if war.mobilized_legion_count:
            return
        legions = getattr(war, "proposed_legions", 0)
        if legions <= 0:
            min_legions = self.state.config.get("testing.min_legions", 4)
            max_legions = self.state.config.get("testing.max_legions", 8)
            legions = random.randint(min_legions, max_legions)
        return ws.mobilize_war_legions(war, legions, consul_id)

    def execute_war_takeover_direct(self, war, consul_figure) -> bool:
        """DEV-13 玩家直接接管：先招募/分配军团，成功后回写 commander（FC-05 原子性）。

        复用 _auto_recruit_and_assign_legions_for_war 招募军团；军团就位后才回写
        commander/office/is_absent。招募失败 → False，commander 不回写。
        human takeover_war（senate_api）与 AI execute_ai_takeover_direct_action 共用此路径。
        """
        if not war or not consul_figure:
            return False
        ms = self.state.get_military_system()
        if ms is None:
            return False

        self._auto_recruit_and_assign_legions_for_war(war, consul_figure.id)

        # 军团招募成功判定：战争已有（或本次新分配）军团
        if not getattr(war, "legion_numbers", None):
            self.state.log_event(
                f"execute_war_takeover_direct: war={war.id} 军团招募失败",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "legion_recruit_failed"},
            )
            return False

        # 旧指挥官 office 转换（仅当其存活且可被替换：is_absent proconsul/propraetor）
        old_cmd_id = war.commander_id
        old_cmd = self.state.get_member(old_cmd_id) if old_cmd_id else None
        if old_cmd and old_cmd.id != consul_figure.id and not old_cmd.is_dead:
            old_cmd.is_absent = False
            if old_cmd.office == "proconsul":
                old_cmd.office = "ex-consul"
            elif old_cmd.office == "propraetor":
                old_cmd.office = "ex-praetor"
            old_cmd.update_influence()

        war.commander_id = consul_figure.id
        self._set_absent(consul_figure)
        self.state.log_event(
            f"战争接管直接执行: war={war.id}, commander={consul_figure.id}",
            level=logging.INFO,
            extra={"war_id": war.id, "commander_id": consul_figure.id, "method": "execute_war_takeover_direct"},
        )
        return True
