# src/core/systems/political_system.py
"""
PoliticalSystem collects senate and political business rules.
"""

import copy
import logging
import uuid
from typing import Any, Dict, List, Optional

from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider
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

        # WP-F R2-01（D-3）：record_veto fail-closed 四条件——not submitted / vote not complete /
        # Senate failed / outside candidate set（passed-and-not-vetoed 判定合一）→ 拒绝该 id 且
        # 零否决状态变更（game_state.record_senate_veto 原语零改）；返回结构增加 rejected_ids 明细；
        # 全拒 → success=False（镜像 record_vote「全部未记录返 False」既有契约，见上）。
        # 否决候选唯一权威 = build_vote_results_and_candidates 的 veto_candidate_ids（单一 producer，
        # 与 AI veto / DTO 路径同源同果）。
        vetoed = []
        rejected_ids = []
        proposals = self.state.get_senate_proposals()
        votes = self.state.get_senate_votes_copy().get(player_id, {})
        vote_complete = bool(proposals) and all(p["id"] in votes for p in proposals)
        # WP-F R2-01（单一 producer）：否决候选集唯一来源 = build_vote_results_and_candidates
        # 的 veto_candidate_ids（与 AI/DTO 路径同源）；禁内联 calculate_vote_result 重算
        # passed-only（零平行判定）。
        candidate_ids = set(self.build_vote_results_and_candidates()["veto_candidate_ids"])
        for proposal_id in proposal_ids:
            proposal = next((p for p in proposals if p["id"] == proposal_id), None)
            if proposal is None:
                rejected_ids.append({"proposal_id": proposal_id, "reason": "not_submitted"})
                continue
            if not vote_complete:
                rejected_ids.append({"proposal_id": proposal_id, "reason": "vote_not_complete"})
                continue
            if proposal_id not in candidate_ids:
                rejected_ids.append({"proposal_id": proposal_id, "reason": "not_passed"})
                continue
            if self.state.record_senate_veto(proposal_id):
                vetoed.append(proposal_id)
                self.state.log_event(
                    f"玩家 {player_id} 否决提案 {proposal_id}",
                    level=logging.INFO,
                    extra={"player_id": player_id, "proposal_id": proposal_id},
                )

        if not vetoed:
            return self._result(
                False,
                "否决被拒绝：提案未通过元老院表决",
                {"vetoed": vetoed, "rejected_ids": rejected_ids},
            )
        return self._result(
            True,
            f"已否决 {len(vetoed)} 个提案",
            {"vetoed": vetoed, "rejected_ids": rejected_ids},
        )

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
        vetoed_proposals = []      # 新增：被保民官否决（vetoed=True）
        failed_proposals = []      # 新增：元老院表决未通过（failed）
        rejected_peace_wars = []
        # WP-F R1-F-03：本轮每提案已算 vote result 载体（透出权威已算值，禁重算/重跑投票）
        vote_results = []

        for proposal in proposals:
            result = self.calculate_vote_result(proposal, vote_decider)
            if result["vetoed"]:
                vetoed_proposals.append(proposal)
                peace_war = self._get_peace_war(proposal)
                if peace_war:
                    rejected_peace_wars.append(peace_war)
            elif result["passed"]:
                passed_proposals.append(proposal)
            else:
                failed_proposals.append(proposal)
                peace_war = self._get_peace_war(proposal) if result["total_influence"] > 0 else None
                if peace_war:
                    rejected_peace_wars.append(peace_war)

            # WP-F R1-F-03：收集本轮每提案已算 vote result（proposal_id + support/oppose/total/passed/vetoed）
            vote_results.append({
                "proposal_id": proposal.get("id"),
                "support_influence": result["support_influence"],
                "oppose_influence": result["oppose_influence"],
                "total_influence": result["total_influence"],
                "passed": result["passed"],
                "vetoed": result["vetoed"],
            })

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

        # WP-F R3：rejected 聚合（vetoed + failed）逐字保留既有语义（test_senate_r1.py:180-190 兼容）
        rejected_proposals = vetoed_proposals + failed_proposals

        execution_messages = []
        for proposal in passed_proposals:
            if self._is_war_proposal(proposal):
                # R5（SA §4.1 / §4.10 C-M01，DA-3）：War/Peace 军事/条约效果延迟到
                # Senate→Combat 边界整包事务；政治链零军事早写（不调 execute_*）。
                continue
            execution = self.execute_passed_proposal(proposal)
            if execution.get("message"):
                execution_messages.append(execution["message"])

        # R5（SA §4.1，DA-3）：为每个 War Proposal 冻结 final Decision（ENACTED/REJECTED/
        # VETOED）到执行账本；供边界事务读取 immutable 结果（Results 清理不销毁）。
        session_id = self.state.get_senate_session() or (
            f"turn-{self.state.turn.turn_number if self.state.turn else 0}")
        for proposal in proposals:
            if not self._is_war_proposal(proposal):
                continue
            outcome = ("VETOED" if proposal in vetoed_proposals
                       else "ENACTED" if proposal in passed_proposals else "REJECTED")
            decision_input = self._war_decision_input(proposal)
            self.state.record_war_decision(session_id, proposal.get("id"), {
                "proposal_id": proposal.get("id"),
                "war_id": decision_input["war_id"],
                "outcome": outcome,
                "mode": decision_input["mode"],
                "source": decision_input["source"],
                "payload": decision_input["payload"],
                "snapshot_ref": decision_input["snapshot_ref"],
            })

        # R5（SA §4.4 / C-M05）：被拒/Veto Peace 的 ACTIVE 恢复不再在 Results 早写；
        # 全部 PF（含 unchecked/空包）在边界统一处理。
        restored_peace_wars = []

        # P-7（AU-5）：结算循环完成、clear_senate_pending 之前快照 direct_actions，
        # 供 senate_api.resolve_senate 组装 public_announcement（公示持久化）。
        direct_actions = self.state.get_senate_direct_actions()

        # AU-R1-05a（C1，D-1 采纳）：resolve_senate 零 takeover mutation。
        # R5（SA §5.2 C-M08/C-M09，DA-4）：旧 process_war_takeover / AI 接管直连均已退役——
        # 唯一 mutation 入口 = Senate→Combat 整包事务（senate_api.advance_senate_phase）。
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
            "failed_proposals": [p["id"] for p in failed_proposals],
            "execution_results": execution_messages,
            "rejected_peace_wars": restored_peace_wars,
            "passed_proposals_snapshot": [p.copy() for p in passed_proposals],
            "rejected_proposals_snapshot": [p.copy() for p in rejected_proposals],
            "vetoed_proposals_snapshot": [p.copy() for p in vetoed_proposals],
            "failed_proposals_snapshot": [p.copy() for p in failed_proposals],
            "direct_actions": direct_actions,
            "vote_results": vote_results,
        })

    def build_issue_from_proposal(self, proposal: dict):
        ptype = proposal["type"]
        proposer_faction = proposal.get("proposer_faction")
        if ptype == "war_proposal":
            # R5（DA-3）：投票决策器需要看到 war_id/mode（不重算内容，只读快照身份）
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(proposal["war_id"]) if ws else None
            return {"type": "war_proposal", "war_id": proposal.get("war_id"), "war": war,
                    "mode": proposal.get("mode"), "payload": proposal.get("payload"),
                    "proposer_faction": proposer_faction}
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

    def build_vote_results_and_candidates(self) -> Dict[str, Any]:
        """WP-F R2-01：单一权威中间投影 producer（唯一 passed-only 候选集生产点）。

        对每个已提交提案调 calculate_vote_result（复用唯一投票计算，零重算/零重掷）产出：
        - vote_results：字段复用 resolve_senate 既有 schema（proposal_id / support_influence /
          oppose_influence / total_influence / passed / vetoed）；
        - veto_candidate_ids：passed 且未否决的提案 id（权威 passed-only 候选集）。

        全消费者（AI veto / Human-direct record_veto / DTO / Store / QML）同源此 producer，
        禁平行 passed-only 判定。首次调用可触发未投票 AI 派系首次决策并幂等持久化
        （source="ai"，与 resolve_senate 最终计算同源同果）；此后纯读零重掷。
        """
        vote_results: List[Dict[str, Any]] = []
        veto_candidate_ids: List[int] = []
        for proposal in self.state.get_senate_proposals():
            result = self.calculate_vote_result(proposal)
            vote_results.append({
                "proposal_id": proposal.get("id"),
                "support_influence": result["support_influence"],
                "oppose_influence": result["oppose_influence"],
                "total_influence": result["total_influence"],
                "passed": result["passed"],
                "vetoed": result["vetoed"],
            })
            if result.get("passed") and not result.get("vetoed"):
                veto_candidate_ids.append(proposal.get("id"))
        return {"vote_results": vote_results, "veto_candidate_ids": veto_candidate_ids}

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
                    # R3-G-03（设计 §3.1，FROZEN）：Fleet budget PASS 分支——冻结 A（
                    # `_original_budget` 绝不被覆盖为上一次 B）、写 B（`_approved_budget`，即使
                    # 金额未修改也写入）、保持 legacy base_cost=B 投影。普通工程旧逻辑保留。
                    if getattr(contract, "_is_fleet_construction", False):
                        if modified_budget is None:
                            modified_budget = contract.base_cost
                        # A 冻结：重复修改不得把 _original_budget 覆盖成上一次 B（旧代码缺陷）
                        # （generator 已冻结 _original_budget；此处仅防御性断言语义，不覆盖）
                        contract._approved_budget = int(modified_budget)
                        contract.base_cost = int(modified_budget)
                        self.state.log_event(
                            f"预算提案通过（Fleet）: 合同 {contract.name} 批准预算 B="
                            f"{contract._approved_budget}，基线 A={contract._original_budget}",
                            level=logging.INFO,
                            extra={
                                "contract_id": contract.id,
                                "baseline_a": contract._original_budget,
                                "approved_b": contract._approved_budget,
                            },
                        )
                    elif modified_budget and modified_budget != contract.base_cost:
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
        # M6（G 件 §5）：宣战征召改用显式值（proposal 的 legions），禁 random；
        # 值域仍由 _legion_options_for_war（宣战语义）约束，与 Takeover/Continue 的
        # Reinforcement N 契约区分。
        self._recruit_and_assign_exact(war, consul_id, legions)
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
        """和约批准（G3C 冻结九步，Owner Correction 2026-09-01）。

        approved = TEMPORARY TRUCE（非战争结束）：War 保持 TRUCE + 驻留 _truce_wars，
        treaty.status=approved + truce_end_turn=当前回合+duration；当前 Commander 返回罗马
        （commander_id=None）、Legion/Fleet 召回 → AVAILABLE（下个 Revenue 最后维护、下个
        Population DISBANDED）；legion_numbers 入 _legions_to_disband 后**立即清空**
        （ODR-CAND-01 方向① enqueue-then-clear，防双入残留）；到期由 A7
        process_truce_expiry → _move_to_threat 恢复（truce 到期机制，见 G3C 冻结语义）。
        TRIUMPH/VICTORY → RESOLVED 为独立生命周期（resolve_war，禁混同）。
        """
        ws = self.state.get_war_system()
        if not ws:
            return
        treaty = war.peace_treaty
        # R5（DA-3 / SA §4.10 C-M04）：前提由「Submit 早写 submitted」重构为权威 pending
        # 草案（冻结 treaty_ref + live pending 复核）；不再依赖已拆除的 Submit 早写。
        if not treaty or treaty.get("status") not in ("pending", "submitted"):
            return
        # 1. 条约 → approved
        war.set_peace_treaty_status("approved")
        # 2. 记赔
        war.set_indemnity_due(treaty["indemnity"])
        # 3. 当前军团召回 → AVAILABLE（G1-14：下个 Revenue 付最后维护）
        ms = self.state.get_military_system()
        if ms:
            ms.recall_from_war(war.id)
        # 4. 当前舰队召回 → AVAILABLE（如适用，G1-14/E 件 §5）
        if self.state.naval_system:
            self.state.naval_system.recall_fleets_from_war(war.id)
        # 5. Commander 返回罗马（is_absent=False / office 回退 / update_influence）；
        #    war.commander_id = None（释放绑定）
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
        # 6. enqueue：war.legion_numbers → _legions_to_disband（ODR-CAND-01 方向①）
        if war.legion_numbers:
            ws.add_legions_to_disband(war.legion_numbers)
        # 7. 立即 clear（防双入残留：war.legion_numbers 不再保留重复解散引用）
        war.clear_legion_numbers()
        # 8. set truce_end_turn（到期恢复机制载体）
        end_turn = self.state.turn.turn_number + treaty.get("duration", 0)
        war.set_truce_end_turn(end_turn)
        # 9. War 保持 TRUCE（驻留 _truce_wars；禁 move_truce_war_to_resolved / resolve_war /
        #    入 _war_discard——approved = temporary truce，非战争结束，G3C 冻结）
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

    # R5（SA §5.2 C-M08，DA-4）：旧 AI 接管链（`_ai_takeover_candidate_wars` /
    # `plan_ai_takeovers` / `execute_ai_takeover_direct_action`）已退役——AI 接管不再存在
    # 独立直连路径；AI 意图统一经 `submit_proposal_package`（Package Submit），执行经
    # 唯一 `advance_senate_phase` 边界事务。

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

    # =====================================================================
    # R5（SA §2.1/§2.2/§2.4/§2.5/§3，DA-1 + DA-2）
    # =====================================================================

    _COMMANDER_ROLE_POOL = ("consul", "praetor", "ex-consul", "ex-praetor")

    # SA §3.9 冻结 21 个 Submit code（20 规则/上下文 + 1 技术）
    _SUBMIT_ERROR_CODES = (
        "SUBMIT_REQUEST_INVALID", "SUBMIT_NOT_AUTHORIZED", "SUBMIT_PHASE_INVALID",
        "PACKAGE_ALREADY_SUBMITTED", "SUBMIT_REQUEST_REUSED", "WAR_PROPOSAL_DUPLICATE",
        "WAR_TARGET_INVALID", "WAR_NOT_PROPOSABLE", "WAR_MODE_INVALID", "COMMANDER_REQUIRED",
        "COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE", "REINFORCEMENT_INVALID",
        "PEACE_DRAFT_INVALID", "COMMANDER_CLAIM_DUPLICATE", "GOVERNOR_COMMANDER_CONFLICT",
        "GOVERNOR_NOMINATION_DUPLICATE", "NON_WAR_PROPOSAL_INVALID", "LEGION_POOL_EXCEEDED",
        "SUBMIT_CONTEXT_CHANGED", "SUBMIT_PUBLISH_FAILED",
    )

    def _error(self, code: str, scope: str = "package", field: Optional[str] = None,
               details: Optional[dict] = None, message: str = "") -> Dict[str, Any]:
        return {"code": code, "scope": scope, "field": field,
                "details": details or {}, "message": message or code}

    def _senate_view_revision(self) -> int:
        sp = getattr(self.state, "_senate_pending", {}) or {}
        turn = getattr(self.state.turn, "turn_number", 0) if self.state.turn else 0
        return int(turn or 0) * 1000 + int(sp.get("proposal_id_counter", 0) or 0)

    # ---------- War universe / Commander candidates（§2.4）----------

    def _real_wars(self) -> List[Any]:
        ws = self.state.get_war_system()
        if not ws:
            return []
        out, seen = [], set()
        for war in list(ws.get_active_wars()) + list(ws.get_truce_wars()):
            if war.id in seen:
                continue
            seen.add(war.id)
            if war.status in (WarStatus.ACTIVE, WarStatus.TRUCE):
                out.append(war)
        return out

    def _senate_card_wars(self, ws) -> List[Any]:
        out, seen = [], set()
        for war in list(ws.get_threat_wars()) + list(ws.get_active_wars()) + list(ws.get_truce_wars()):
            if war.id in seen:
                continue
            seen.add(war.id)
            # approved temporary TRUCE 不可用新 Peace/Command 提案绕过有效停战 → 不出作战卡
            if (war.status == WarStatus.TRUCE and war.peace_treaty
                    and war.peace_treaty.get("status") == "approved"):
                continue
            out.append(war)
        return out

    def _current_command_war_ids(self, figure_id: int) -> List[str]:
        return sorted(war.id for war in self._real_wars() if war.commander_id == figure_id)

    def _war_commander_role(self, fig) -> Optional[str]:
        """§2.4 单一候选资格谓词（输出一个 role；current office > Former Consul > Former Praetor）。"""
        office = fig.office
        if office == "tribune":
            return None  # 现任 Tribune 不可为 War Commander（含历史任期的离城禁令）
        if office == "consul":
            return "consul"
        if office == "praetor":
            return "praetor"
        if office == "ex-consul":
            return "ex-consul"
        if office == "ex-praetor":
            return "ex-praetor"
        # 战争延任身份：proconsul/propraetor 按相应 Former 家族归类
        if office == "proconsul":
            return "ex-consul"
        if office == "propraetor":
            return "ex-praetor"
        # 已结束 consul/praetor 任期 → Former 依据（不得靠 office 字符串猜总督）
        for term in getattr(fig, "office_history", []) or []:
            if term.office_type == "consul" and term.end_turn is not None:
                return "ex-consul"
        for term in getattr(fig, "office_history", []) or []:
            if term.office_type == "praetor" and term.end_turn is not None:
                return "ex-praetor"
        return None

    def build_war_commander_candidates(self, context: Optional[dict] = None) -> List[Dict[str, Any]]:
        """§2.4 唯一 Commander 候选 producer（全部 Card 共用；按 FigureId 升序）。"""
        if not self.state:
            return []
        governor_ids = set()
        for province in self.state.get_all_provinces():
            gid = getattr(province, "governor_id", None)
            if gid is not None:
                governor_ids.add(gid)
        rows = []
        for fig in self.state.get_living_members():
            if fig.is_dead:
                continue
            role = self._war_commander_role(fig)
            if not role:
                continue
            if fig.id in governor_ids:
                continue  # 现任 Province Governor 排除（不靠 office 字符串推测）
            rows.append({
                "figure_id": fig.id,
                "label": fig.get_formal_name(),
                "eligible_role": role,
                "office": fig.office,
                "martial": getattr(fig, "martial", 0),
                "current_command_war_ids": self._current_command_war_ids(fig.id),
            })
        rows.sort(key=lambda r: r["figure_id"])
        return rows

    # ---------- Card defaults / views（§2.1/§2.2）----------

    def _war_card_defaults(self, facts: Dict[str, Any], consul_id: Optional[int]) -> Dict[str, Any]:
        classification = facts["classification"]
        current = facts["current_commander_id"]
        if classification in ("active_declaration", "passive_declaration"):
            return {"checked": False, "mode": "command",
                    "target_commander_id": consul_id, "reinforcement_n": 4}
        target = current if current is not None else consul_id
        return {"checked": False, "mode": "command",
                "target_commander_id": target, "reinforcement_n": 0}

    def build_war_card_views(self, context: Optional[dict] = None) -> List[Dict[str, Any]]:
        """§2.1/§2.2/§5.1：组合 WarSystem lifecycle facts + 共享候选池 + defaults。"""
        if not self.state:
            return []
        ws = self.state.get_war_system()
        if not ws:
            return []
        ctx = dict(context or {})
        candidates = self.build_war_commander_candidates(ctx)
        consul_id = ctx.get("consul_id")
        if consul_id is None:
            consul = self._find_any_eligible_consul()
            consul_id = consul.id if consul else None
        current_turn = ctx.get("current_turn")
        if current_turn is None and self.state.turn:
            current_turn = self.state.turn.turn_number
        facts_ctx = {"current_turn": current_turn, "consul_id": consul_id}
        revision = self._senate_view_revision()
        cards = []
        for war in self._senate_card_wars(ws):
            facts = ws.describe_senate_war(war.id, facts_ctx)
            if not facts:
                continue
            label = ""
            if war.commander_id is not None:
                cmd = self.state.get_member(war.commander_id)
                label = cmd.get_formal_name() if cmd else ""
            card = dict(facts)
            card["current_commander_label"] = label
            card["commander_candidates"] = candidates
            card["defaults"] = self._war_card_defaults(facts, consul_id)
            card["view_revision"] = revision
            cards.append(card)
        cards.sort(key=lambda c: c["war_id"])
        return cards

    # ---------- Commander Claim（§2.5/§3.3）----------

    def normalize_war_drafts(self, war_drafts: Optional[List[dict]]) -> List[Dict[str, Any]]:
        out = []
        for row in war_drafts or []:
            if not isinstance(row, dict):
                continue
            out.append({
                "war_id": row.get("war_id"),
                "checked": bool(row.get("checked")),
                "mode": row.get("mode", "command"),
                "target_commander_id": row.get("target_commander_id"),
                "reinforcement_n": row.get("reinforcement_n"),
            })
        return out

    def _war_claim_source(self, war) -> str:
        if (war.status == WarStatus.TRUCE and war.peace_treaty
                and war.peace_treaty.get("status") == "pending"):
            return "pending_peace"
        turn = getattr(self.state.turn, "turn_number", None) if self.state.turn else None
        if (war.activation_origin == "passive_declaration" and war.activation_turn is not None
                and turn is not None and war.activation_turn == turn):
            return "passive_declaration"
        return "ongoing"

    def build_commander_claims(self, real_wars: List[Any], canonical_drafts: List[dict],
                               declaration_candidates: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """§2.5 完整 Commander Claim（非 null 集合；null 不入集合）。"""
        drafts_by_war = {}
        for d in canonical_drafts or []:
            if isinstance(d, dict) and d.get("war_id"):
                drafts_by_war[d["war_id"]] = d
        claims = []
        for war in real_wars or []:
            draft = drafts_by_war.get(war.id)
            checked = bool(draft and draft.get("checked"))
            mode = (draft or {}).get("mode", "command")
            if not checked:
                commander_id, basis, proposed_mode = war.commander_id, "retained_unchecked", "command"
            elif mode == "peace":
                commander_id, basis, proposed_mode = war.commander_id, "retained_peace", "peace"
            else:
                commander_id, basis, proposed_mode = (draft.get("target_commander_id"),
                                                      "selected_command", "command")
            if commander_id is None:
                continue
            claims.append({"war_id": war.id, "commander_id": commander_id, "basis": basis,
                           "proposed_mode": proposed_mode, "source": self._war_claim_source(war)})
        for cand in declaration_candidates or []:
            war_id = cand.get("war_id") if isinstance(cand, dict) else getattr(cand, "id", None)
            draft = drafts_by_war.get(war_id)
            if not draft or not draft.get("checked") or draft.get("mode") == "peace":
                continue
            commander_id = draft.get("target_commander_id")
            if commander_id is None:
                continue
            claims.append({"war_id": war_id, "commander_id": commander_id,
                           "basis": "selected_declaration", "proposed_mode": "command",
                           "source": "active_declaration"})
        return claims

    # ---------- Submit package（§3.1–§3.9）----------

    def _submit_failure(self, errors: List[dict], request_id: Optional[str] = None,
                        checks_skipped: Optional[list] = None) -> dict:
        errors = sorted(errors, key=lambda e: (e.get("code", ""), str(e.get("scope", ""))))
        return {"success": False,
                "message": errors[0]["message"] if errors else "提交失败",
                "data": {"created": [], "submit_request_id": request_id, "submitted": False,
                         "draft_preserved": True, "checks_skipped": checks_skipped or []},
                "errors": errors}

    def _package_fingerprint(self, war_drafts, proposals) -> str:
        parts = []
        for row in war_drafts or []:
            if isinstance(row, dict):
                parts.append(("w", row.get("war_id"), bool(row.get("checked")), row.get("mode"),
                              row.get("target_commander_id"), row.get("reinforcement_n")))
            else:
                parts.append(("?", repr(row)))
        for spec in proposals or []:
            if isinstance(spec, dict):
                params = spec.get("params") or {}
                try:
                    items = tuple(sorted((str(k), str(v)) for k, v in params.items()))
                except Exception:
                    items = (repr(params),)
                parts.append(("p", spec.get("type"), items))
            else:
                parts.append(("?", repr(spec)))
        return repr(parts)

    def submit_proposal_package(self, actor: str, request: dict,
                                context: Optional[dict] = None) -> dict:
        """§3.1–§3.9 唯一整包 Submit（validate → stage → 原子发布；all-or-nothing）。"""
        ctx = dict(context or {})

        # ---------------- V0 请求 / 身份 / 会期门 ----------------
        if not isinstance(request, dict):
            return self._submit_failure([self._error("SUBMIT_REQUEST_INVALID", field="request",
                                                     message="请求格式非法")])
        war_drafts_raw = request.get("war_drafts") or []
        proposals_raw = request.get("proposals") or []
        if not isinstance(war_drafts_raw, list) or not isinstance(proposals_raw, list):
            return self._submit_failure([self._error("SUBMIT_REQUEST_INVALID", field="request",
                                                     message="war_drafts/proposals 必须为列表")])
        session_id = request.get("senate_session_id") or ctx.get("senate_session_id") or "default"
        request_id = request.get("submit_request_id")

        player = self.state.get_player(actor)
        if not player:
            return self._submit_failure([self._error("SUBMIT_NOT_AUTHORIZED", field="actor",
                                                     details={"actor_id": actor},
                                                     message="调用身份无效")], request_id)
        faction = self.state.get_faction(player.faction_id)
        consul = self._find_consul_for_faction(faction) if faction else None
        if consul is None:
            return self._submit_failure([self._error("SUBMIT_NOT_AUTHORIZED",
                                                     details={"actor_id": actor, "reason": "no_eligible_consul"},
                                                     message="只有执政官可以提出提案")], request_id)
        step = ctx.get("current_step")
        if step is not None and step != "proposal" and not ctx.get("allow_any_phase"):
            return self._submit_failure([self._error("SUBMIT_PHASE_INVALID",
                                                     details={"current_step": step},
                                                     message="当前不在提案阶段")], request_id)

        fingerprint = self._package_fingerprint(war_drafts_raw, proposals_raw)
        registry = self.state.get_senate_package_registry()
        if request_id:
            existing = registry["requests"].get(request_id)
            if existing is not None:
                if existing.get("fingerprint") == fingerprint:
                    return {"success": True, "message": "提交已重放",
                            "data": {"created": [dict(c) for c in existing.get("created", [])],
                                     "submit_request_id": request_id, "submitted": True,
                                     "draft_preserved": False, "replayed": True},
                            "errors": []}
                return self._submit_failure([self._error(
                    "SUBMIT_REQUEST_REUSED",
                    details={"submit_request_id": request_id,
                             "existing_package_id": existing.get("package_id")},
                    message="已成功请求身份被用于不同意图")], request_id)
            if self.state.senate_proposal_decision_complete:
                return self._submit_failure([self._error(
                    "PACKAGE_ALREADY_SUBMITTED",
                    details={"senate_session_id": session_id},
                    message="本会期选择已经成功完成")], request_id)

        # ---------------- V1/V2 行归一 + 身份/字段/资格 ----------------
        errors: List[dict] = []
        checks_skipped: List[dict] = []
        ws = self.state.get_war_system()
        card_wars = {w.id: w for w in self._senate_card_wars(ws)} if ws else {}
        real_wars = self._real_wars()
        real_ids = {w.id for w in real_wars}
        candidate_ids = [c["figure_id"] for c in self.build_war_commander_candidates(ctx)]

        canonical: List[dict] = []
        seen_war = set()
        war_inputs_complete = True
        for row in war_drafts_raw:
            if not isinstance(row, dict):
                errors.append(self._error("SUBMIT_REQUEST_INVALID", field="war_drafts",
                                          message="war_draft 必须为 dict"))
                war_inputs_complete = False
                continue
            war_id = row.get("war_id")
            if not war_id or not isinstance(war_id, str):
                errors.append(self._error("SUBMIT_REQUEST_INVALID", scope="war", field="war_id",
                                          message="war_id 非法"))
                war_inputs_complete = False
                continue
            if war_id in seen_war:
                errors.append(self._error("WAR_PROPOSAL_DUPLICATE", scope=war_id,
                                          details={"war_id": war_id, "reason": "input_duplicate"},
                                          message="同一 War 重复输入"))
                war_inputs_complete = False
                continue
            seen_war.add(war_id)
            checked = row.get("checked", False)
            if not isinstance(checked, bool):
                errors.append(self._error("SUBMIT_REQUEST_INVALID", scope=war_id, field="checked",
                                          message="checked 必须为布尔"))
                war_inputs_complete = False
                continue
            draft = {"war_id": war_id, "checked": checked, "mode": row.get("mode", "command"),
                     "target_commander_id": row.get("target_commander_id"),
                     "reinforcement_n": row.get("reinforcement_n")}
            canonical.append(draft)
            if not checked:
                continue  # unchecked：只读身份与 checked（不校验 mode/Commander/N 缓存值）
            if war_id not in card_wars:
                code = "WAR_NOT_PROPOSABLE" if war_id in real_ids else "WAR_TARGET_INVALID"
                errors.append(self._error(code, scope=war_id, details={"war_id": war_id},
                                          message="War 不可提案" if code == "WAR_NOT_PROPOSABLE"
                                          else "War 不存在"))
                war_inputs_complete = False
                continue
            war = card_wars[war_id]
            facts = ws.describe_senate_war(war_id, {"current_turn": ctx.get("current_turn")})
            mode = draft["mode"]
            allowed_modes = (facts or {}).get("allowed_modes") or []
            if mode not in ("command", "peace"):
                errors.append(self._error("WAR_MODE_INVALID", scope=war_id,
                                          details={"war_id": war_id, "mode": mode,
                                                   "allowed_modes": allowed_modes},
                                          message="mode 不是 command/peace"))
                war_inputs_complete = False
                continue
            if mode == "peace":
                if not (facts or {}).get("is_real_war"):
                    errors.append(self._error("WAR_MODE_INVALID", scope=war_id,
                                              details={"war_id": war_id, "mode": mode,
                                                       "allowed_modes": allowed_modes},
                                              message="该 candidate 不允许 peace 模式"))
                    war_inputs_complete = False
                    continue
                if not (war.peace_treaty and war.peace_treaty.get("status") == "pending"):
                    errors.append(self._error("PEACE_DRAFT_INVALID", scope=war_id,
                                              details={"war_id": war_id, "reason": "no_pending_draft",
                                                       "observed_treaty_ref": None},
                                              message="无有效 pending 停战草案"))
                    war_inputs_complete = False
                    continue
                continue
            if "command" not in allowed_modes:
                errors.append(self._error("WAR_MODE_INVALID", scope=war_id,
                                          details={"war_id": war_id, "mode": mode,
                                                   "allowed_modes": allowed_modes},
                                          message="该 War 不允许此 mode"))
                war_inputs_complete = False
                continue
            target = draft["target_commander_id"]
            if target is None:
                errors.append(self._error("COMMANDER_REQUIRED", scope=war_id,
                                          field="target_commander_id", details={"war_id": war_id},
                                          message="checked command 缺少 target Commander"))
                war_inputs_complete = False
            elif (not isinstance(target, int)) or isinstance(target, bool) or target < 0:
                errors.append(self._error("COMMANDER_TARGET_INVALID", scope=war_id,
                                          field="target_commander_id",
                                          details={"war_id": war_id, "supplied_target": target},
                                          message="target 身份类型非法"))
                war_inputs_complete = False
            else:
                fig = self.state.get_member(target)
                if fig is None or fig.is_dead:
                    errors.append(self._error("COMMANDER_TARGET_INVALID", scope=war_id,
                                              field="target_commander_id",
                                              details={"war_id": war_id, "supplied_target": target},
                                              message="target 实体不存在"))
                    war_inputs_complete = False
                elif target not in candidate_ids:
                    errors.append(self._error("COMMANDER_INELIGIBLE", scope=war_id,
                                              field="target_commander_id",
                                              details={"war_id": war_id, "figure_id": target},
                                              message="target 不符合 Commander 资格"))
                    war_inputs_complete = False
            n = draft["reinforcement_n"]
            if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0):
                errors.append(self._error("REINFORCEMENT_INVALID", scope=war_id,
                                          field="reinforcement_n",
                                          details={"war_id": war_id, "supplied_n": n},
                                          message="Reinforcement N 非法"))
                war_inputs_complete = False

        # 非 War 提案纯校验（staging，不落库）
        staged_props: List[dict] = []
        gov_nominations: List[tuple] = []
        for spec in proposals_raw:
            if not isinstance(spec, dict):
                errors.append(self._error("SUBMIT_REQUEST_INVALID", field="proposals",
                                          message="提案必须为 dict"))
                continue
            ptype = spec.get("type")
            params = spec.get("params", {}) or {}
            staging: Dict[str, Any] = {"type": ptype}
            result = self._populate_proposal(staging, ptype, **params)
            if not result.get("success"):
                errors.append(self._error("NON_WAR_PROPOSAL_INVALID", scope=str(ptype), field=ptype,
                                          details={"type": ptype},
                                          message=result.get("message", "普通提案校验失败")))
                continue
            staging["proposer_faction"] = faction.id
            staging["proposer_player"] = actor
            staging["consul_id"] = consul.id
            staged_props.append(staging)
            if ptype == "governor":
                gov_nominations.append((staging.get("candidate_id"), staging.get("province_id")))

        seen_fig, seen_prov = {}, {}
        for fig_id, prov_id in gov_nominations:
            if fig_id in seen_fig and seen_fig[fig_id] != prov_id:
                errors.append(self._error("GOVERNOR_NOMINATION_DUPLICATE",
                                          details={"figure_ids": [fig_id],
                                                   "province_ids": [seen_fig[fig_id], prov_id]},
                                          message="同一人物被提名到两个 Province"))
            seen_fig.setdefault(fig_id, prov_id)
            if prov_id in seen_prov and seen_prov[prov_id] != fig_id:
                errors.append(self._error("GOVERNOR_NOMINATION_DUPLICATE",
                                          details={"reason": "DUPLICATE_PROVINCE", "province_ids": [prov_id],
                                                   "figure_ids": [seen_prov[prov_id], fig_id]},
                                          message="同一 Province 被提名两个人物"))
            seen_prov.setdefault(prov_id, fig_id)

        # ---------------- V3 包级约束 ----------------
        n_valid = not any(e["code"] == "REINFORCEMENT_INVALID" for e in errors)
        if war_inputs_complete:
            declarations = [{"war_id": w.id} for w in (ws.get_threat_wars() if ws else [])]
            claims = self.build_commander_claims(real_wars, canonical, declarations)
            by_cmd: Dict[int, list] = {}
            for c in claims:
                by_cmd.setdefault(c["commander_id"], []).append(c)
            dup = False
            for cmd_id, group in by_cmd.items():
                if len({g["war_id"] for g in group}) > 1:
                    errors.append(self._error("COMMANDER_CLAIM_DUPLICATE",
                                              details={"commander_id": cmd_id, "claims": group},
                                              message="同一非 null Commander 被不同 War claim"))
                    dup = True
            if not dup:
                claim_cmds = {c["commander_id"] for c in claims}
                for fig_id, prov_id in gov_nominations:
                    if fig_id in claim_cmds:
                        errors.append(self._error("GOVERNOR_COMMANDER_CONFLICT",
                                                  details={"figure_id": fig_id, "province_id": prov_id,
                                                           "roles": ["war_commander", "province_governor"]},
                                                  message="同人不可同时为 Province Governor 与 War Commander"))
        else:
            checks_skipped.append({"check": "commander_claim_uniqueness",
                                   "prerequisite_codes": ["WAR_TARGET_INVALID", "WAR_MODE_INVALID",
                                                          "PEACE_DRAFT_INVALID", "COMMANDER_REQUIRED",
                                                          "COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE",
                                                          "REINFORCEMENT_INVALID"]})
            checks_skipped.append({"check": "governor_cross_role",
                                   "prerequisite_codes": ["COMMANDER_CLAIM"]})

        if n_valid and not any(e["code"] == "LEGION_POOL_EXCEEDED" for e in errors):
            requested = 0
            requests = []
            for draft in canonical:
                if not draft["checked"] or draft["mode"] != "command":
                    continue
                war = card_wars.get(draft["war_id"])
                if war is None or not isinstance(draft["reinforcement_n"], int) or isinstance(draft["reinforcement_n"], bool):
                    continue
                requested += int(draft["reinforcement_n"])
                requests.append({"war_id": draft["war_id"],
                                 "source": "active_declaration" if war.status == WarStatus.THREAT else "ongoing",
                                 "reinforcement_n": int(draft["reinforcement_n"])})
            ms = self.state.get_military_system()
            available = len(ms.get_available_legions()) if ms else 0
            if requested > available:
                errors.append(self._error("LEGION_POOL_EXCEEDED",
                                          details={"requested_total": requested, "available_total": available,
                                                   "reduce_by": requested - available,
                                                   "requests": sorted(requests, key=lambda r: r["war_id"])},
                                          message="全部合法 checked command 新兵总请求超过实际池"))
        elif not n_valid:
            checks_skipped.append({"check": "legion_pool", "prerequisite_codes": ["REINFORCEMENT_INVALID"]})

        # ---------------- V4 发布准备 + 原子发布 ----------------
        if errors:
            return self._submit_failure(errors, request_id, checks_skipped)

        turn = self.state.turn.turn_number if self.state.turn else 0
        revision = self._senate_view_revision()
        package_id = uuid.uuid4().hex
        context_id = uuid.uuid4().hex
        snapshots: List[dict] = []
        try:
            for draft in canonical:
                if not draft["checked"]:
                    continue
                war = card_wars.get(draft["war_id"])
                facts = ws.describe_senate_war(draft["war_id"], {"current_turn": turn}) or {}
                if draft["mode"] == "peace":
                    treaty = copy.deepcopy(war.peace_treaty or {})
                    treaty["treaty_ref"] = {"war_id": war.id,
                                            "version": treaty.get("generated_turn")}
                    payload = {"treaty_snapshot": treaty}
                else:
                    fig = self.state.get_member(draft["target_commander_id"])
                    payload = {"target_commander_id": draft["target_commander_id"],
                               "target_commander_label": fig.get_formal_name() if fig else "",
                               "reinforcement_n": int(draft["reinforcement_n"])}
                snapshots.append({
                    "type": "war_proposal", "schema_version": 1, "war_id": war.id,
                    "war_label": war.name, "source": facts.get("classification"),
                    "mode": draft["mode"], "package_id": package_id,
                    "senate_session_id": session_id, "submission_context_id": context_id,
                    "submitted_at": {"turn": turn, "senate_session_id": session_id,
                                     "revision": revision},
                    "payload": payload,
                })
            created = []
            for snap in snapshots:
                pid = self.state.add_senate_proposal(dict(snap))
                created.append({"proposal_id": pid, "type": "war_proposal", "war_id": snap["war_id"]})
            for staging in staged_props:
                pid = self.state.add_senate_proposal(dict(staging))
                created.append({"proposal_id": pid, "type": staging.get("type")})
            self.state.senate_proposal_decision_complete = True
            # R5（DA-3）：冻结会期身份（execution receipt / boundary 事务共用）
            self.state.set_senate_session(session_id)
            for snap in snapshots:
                self.state.register_submitted_war_snapshot(session_id, snap["war_id"], snap)
            if request_id:
                self.state.register_senate_package(request_id, {
                    "fingerprint": fingerprint, "package_id": package_id, "created": created,
                    "snapshots": snapshots, "senate_session_id": session_id,
                    "submission_context_id": context_id})
        except Exception as exc:  # pragma: no cover - defensive
            self.state.log_event(f"Submit 发布失败: {exc}", level=logging.ERROR,
                                 extra={"type": "submit_publish_failed"})
            return self._submit_failure([self._error("SUBMIT_PUBLISH_FAILED",
                                                     details={"stage": "publish", "retryable": True},
                                                     message="提交发布失败")], request_id)

        return {"success": True, "message": "已提交整包",
                "data": {"created": created, "submit_request_id": request_id,
                         "submitted": True, "draft_preserved": False, "replayed": False,
                         "package_id": package_id, "checks_skipped": checks_skipped},
                "errors": []}

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
            # R5 DA-2（DD-01 / C-M03，SA §3.7）：拆除 peace submit 早写与 live alias——
            # War.peace_treaty.status 保持权威 pending，submitted 身份只在政治账本表达；
            # proposal 只携带深冻结副本（客户端改原 dict 不影响快照）。
            proposal["war_id"] = war_id
            proposal["treaty"] = copy.deepcopy(war.peace_treaty)
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

    # ---------- R5（SA §4）：Resolution Engine（plan / commit）----------

    def _is_war_proposal(self, proposal) -> bool:
        """War Proposal 识别（R5 snapshot `war_proposal` + legacy `war`/`peace`）。"""
        return isinstance(proposal, dict) and proposal.get("type") in ("war_proposal", "war", "peace")

    def _war_decision_input(self, proposal: dict) -> Dict[str, Any]:
        """归一 War Proposal 为边界消费输入（mode/source/payload/snapshot_ref）。"""
        ptype = proposal.get("type")
        if ptype == "war_proposal":
            payload = copy.deepcopy(proposal.get("payload") or {})
            return {
                "war_id": proposal.get("war_id"),
                "mode": proposal.get("mode"),
                "source": proposal.get("source"),
                "payload": payload,
                "snapshot_ref": {
                    "proposal_id": proposal.get("proposal_id") or proposal.get("id"),
                    "package_id": proposal.get("package_id"),
                    "senate_session_id": proposal.get("senate_session_id"),
                    "schema_version": proposal.get("schema_version", 1),
                },
            }
        if ptype == "peace":
            treaty = copy.deepcopy(proposal.get("treaty") or {})
            return {
                "war_id": proposal.get("war_id"),
                "mode": "peace",
                "source": "pending_peace",
                "payload": {"treaty_snapshot": treaty},
                "snapshot_ref": {"proposal_id": proposal.get("id"), "schema_version": 0},
            }
        # legacy declaration proposal（`type == "war"`）
        n = proposal.get("legions")
        return {
            "war_id": proposal.get("war_id"),
            "mode": "command",
            "source": "active_declaration",
            "payload": {"target_commander_id": proposal.get("consul_id"),
                        "target_commander_label": "",
                        "reinforcement_n": int(n) if isinstance(n, int) else 0},
            "snapshot_ref": {"proposal_id": proposal.get("id"), "schema_version": 0},
        }

    def build_war_resolution_plan(self, inputs: dict) -> Dict[str, Any]:
        """SA §4.2 规范化整包计划（纯函数）：同时姓 Commander 解析（F 公式）+ 确定性征召分配。

        输入：current_turn / session_id / decisions / real_wars / available_legion_ids /
        pending_war_ids。输出 immutable WarResolutionPlan（不以 card 遍历顺序为真值）。
        """
        decisions = list(inputs.get("decisions") or [])
        real_wars = list(inputs.get("real_wars") or [])
        u0 = sorted(int(x) for x in (inputs.get("available_legion_ids") or []))
        pending_ids = set(inputs.get("pending_war_ids") or [])
        session_id = inputs.get("session_id") or f"turn-{inputs.get('current_turn', 0)}"
        current_turn = inputs.get("current_turn", 0)

        e = [d for d in decisions if d.get("outcome") == "ENACTED"]
        ad_ids = {d["war_id"] for d in e
                  if d.get("mode") == "command" and d.get("source") == "active_declaration"}
        pe_ids = {d["war_id"] for d in e if d.get("mode") == "peace"}
        ec: Dict[str, Any] = {}
        duplicate_targets: List[Any] = []
        target_to_war: Dict[Any, str] = {}
        for d in e:
            if d.get("mode") != "command":
                continue
            wid = d["war_id"]
            target = (d.get("payload") or {}).get("target_commander_id")
            ec[wid] = target
            if target is None:
                continue
            if target in target_to_war and target_to_war[target] != wid:
                duplicate_targets.append(target)
            else:
                target_to_war[target] = wid

        r_ids = {w.id for w in real_wars}
        c0 = {w.id: w.commander_id for w in real_wars}
        pf_ids = pending_ids - pe_ids
        w_final = r_ids | ad_ids
        final_commander: Dict[str, Any] = {}
        for wid in sorted(w_final):
            if wid in pe_ids:
                final_commander[wid] = None
            elif wid in ec:
                final_commander[wid] = ec[wid]
            else:
                old = c0.get(wid)
                moved_to = target_to_war.get(old) if old is not None else None
                if old is not None and moved_to is not None and moved_to != wid:
                    final_commander[wid] = None
                else:
                    final_commander[wid] = old

        new_n: Dict[str, int] = {}
        for wid in sorted(ec):
            payload = next((d.get("payload") or {} for d in e
                            if d.get("war_id") == wid and d.get("mode") == "command"), {})
            n = payload.get("reinforcement_n", 0)
            new_n[wid] = int(n) if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else 0

        allocations: Dict[str, List[int]] = {}
        idx = 0
        for wid in sorted(ec):
            need = new_n.get(wid, 0)
            allocations[wid] = u0[idx:idx + need]
            idx += need
        shortfall = idx - len(u0)

        treaty_effects = []
        for wid in sorted(pe_ids):
            payload = next((d.get("payload") or {} for d in e
                            if d.get("war_id") == wid and d.get("mode") == "peace"), {})
            treaty_effects.append({"war_id": wid,
                                   "treaty_snapshot": copy.deepcopy(payload.get("treaty_snapshot") or {})})

        execution_id = f"{session_id}:senate_to_combat:v1"
        fingerprint = repr((session_id, current_turn,
                            sorted((d.get("war_id"), d.get("outcome"), d.get("mode"),
                                    repr((d.get("payload") or {}).get("target_commander_id")),
                                    repr((d.get("payload") or {}).get("reinforcement_n")))
                                   for d in decisions)))
        return {
            "execution_id": execution_id,
            "session_id": session_id,
            "current_turn": current_turn,
            "input_fingerprint": fingerprint,
            "all_decisions": decisions,
            "enacted": e,
            "activation_set": sorted(ad_ids),
            "peace_set": sorted(pe_ids),
            "pending_fallback_set": sorted(pf_ids),
            "command_set": sorted(ec),
            "new_reinforcement": dict(new_n),
            "final_commander_by_war": dict(final_commander),
            "reinforcement_allocations": allocations,
            "treaty_effects": treaty_effects,
            "available_pool": list(u0),
            "duplicate_targets": sorted(duplicate_targets, key=lambda x: (x is None, x)),
            "legion_shortfall": max(0, shortfall),
        }

    def _apply_peace_effects(self, war, treaty_snapshot: dict) -> None:
        """SA §4.4 PE：条约 approved/赔款/期限/TRUCE 保留 + 召回 + enqueue-then-clear。"""
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        treaty = treaty_snapshot or {}
        war.set_peace_treaty_status("approved")
        war.set_indemnity_due(treaty.get("indemnity", 0))
        if ms:
            ms.recall_from_war(war.id)
        if self.state.naval_system:
            self.state.naval_system.recall_fleets_from_war(war.id)
        # Commander 释放（F=null）+ 返回罗马
        if war.commander_id:
            commander = self.state.get_member(war.commander_id)
            if commander:
                commander.is_absent = False
                if commander.office == "proconsul":
                    commander.office = "ex-consul"
                elif commander.office == "propraetor":
                    commander.office = "ex-praetor"
                commander.update_influence()
            war.commander_id = None
        # enqueue-then-clear（ODR-CAND-01）：先入待解散，再清 legion_numbers
        if war.legion_numbers:
            ws.add_legions_to_disband(list(war.legion_numbers))
        war.clear_legion_numbers()
        duration = treaty.get("duration", 0)
        war.set_truce_end_turn((self.state.turn.turn_number if self.state.turn else 0) + duration)

    def _strict_recruit_and_bind(self, war, commander_id, planned_ids: List[int]) -> List[int]:
        """SA §4.5 严格征召：逐 planned ID 征召并核对恰好 N（禁 min 截断/少募即成功）。"""
        ms = self.state.get_military_system()
        if not ms or not planned_ids:
            if planned_ids:
                raise RuntimeError("military_system_unavailable")
            return []
        recruited: List[int] = []
        for number in planned_ids:
            ok, _msg = ms.recruit_legion(number)
            if not ok:
                raise RuntimeError(f"recruit_failed:{number}")
            recruited.append(number)
        assigned, _msg = ms.assign_to_war(recruited, war.id, commander_id)
        if assigned != len(planned_ids):
            raise RuntimeError(f"assign_count_mismatch:{assigned}!={len(planned_ids)}")
        for number in recruited:
            war.add_legion_number(number)
        return recruited

    def commit_war_resolution(self, plan: dict, transaction=None) -> Dict[str, Any]:
        """SA §4.6 C-T07~C-T10：在受锁事务应用已完成的 Plan（失败 → 抛异常 → 回滚 S0）。

        不在写入过程中再决定下一 War 的 Commander（F 已一次求完）。
        """
        state = self.state
        ws = state.get_war_system()
        ms = state.get_military_system()
        ns = state.naval_system
        if ws is None:
            raise RuntimeError("war_system_unavailable")
        if plan.get("duplicate_targets"):
            raise RuntimeError("duplicate_command_targets")
        if plan.get("legion_shortfall", 0) > 0:
            raise RuntimeError("reinforcement_pool_shortfall")

        effect = {"peace": [], "fallback": [], "activated": [], "bound": [],
                  "recruited": [], "pending_fallback_war_ids": list(plan["pending_fallback_set"])}

        # C-T07：PE 条款/释放/召回/入队/clear
        for pe in plan["treaty_effects"]:
            war = ws.get_war_by_id(pe["war_id"])
            if war is None:
                raise RuntimeError(f"peace_war_missing:{pe['war_id']}")
            self._apply_peace_effects(war, pe["treaty_snapshot"])
            effect["peace"].append(pe["war_id"])

        # C-T08：AD 激活（本边界才迁为真实 ACTIVE）
        submitted_snapshots = {}
        for d in plan["enacted"]:
            ref = (d.get("snapshot_ref") or {})
            if ref.get("senate_session_id"):
                snap = state.get_submitted_war_snapshot(ref["senate_session_id"], d["war_id"])
                if snap:
                    submitted_snapshots[d["war_id"]] = snap
        for wid in plan["activation_set"]:
            war = ws.get_war_by_id(wid)
            if war is None:
                continue
            if war.status != WarStatus.THREAT:
                raise RuntimeError(f"activation_not_threat:{wid}")
            snapshot = submitted_snapshots.get(wid) or {}
            proposer = snapshot.get("proposer_id")
            existing = war.commander_id
            ws.activate_war(wid, proposer if proposer is not None else (existing if existing is not None else -1),
                            plan["new_reinforcement"].get(wid, 0))
            effect["activated"].append(wid)

        # C-T08：PF 终止草案 + TRUCE→ACTIVE
        for wid in plan["pending_fallback_set"]:
            war = ws.get_war_by_id(wid)
            if war is None:
                continue
            if war.status != WarStatus.TRUCE:
                raise RuntimeError(f"fallback_not_truce:{wid}")
            war.clear_peace_treaty()
            if not ws.move_truce_war_to_active(war):
                raise RuntimeError(f"fallback_move_failed:{wid}")
            effect["fallback"].append(wid)

        # C-T07/T09：Commander 绑定 + 幸存 rebind + 严格征召
        for wid in sorted(plan["final_commander_by_war"]):
            war = ws.get_war_by_id(wid)
            if war is None:
                continue
            target = plan["final_commander_by_war"][wid]
            if wid in plan["peace_set"]:
                continue  # PE 已经释放
            if wid in plan["command_set"] and ms:
                for legion in ms.get_legions_for_battle(wid):
                    legion.commander_id = target
                if ns:
                    for fleet in ns.get_fleets_by_war(wid):
                        fleet.commander_id = target
                war.commander_id = target
                recruited = self._strict_recruit_and_bind(war, target, plan["reinforcement_allocations"].get(wid, []))
                if recruited:
                    effect["recruited"].extend(recruited)
                effect["bound"].append(wid)
            else:
                # 非 EC：保留/回退 F（不新增兵，幸存不缩编）
                war.commander_id = target

        # C-T10：按最终岗位求解 office/absent/deployed（新任命→deployed；非任命不被二次 release）
        appointed = {plan["final_commander_by_war"].get(w)
                     for w in (list(plan["command_set"]) + list(plan["activation_set"]))}
        appointed.discard(None)
        for fid in sorted(appointed):
            fig = state.get_member(fid)
            if fig is not None and not getattr(fig, "is_dead", False):
                fig.is_absent = True
        return effect

    def _recruit_and_assign_exact(self, war, commander_id: int, count: int) -> List[int]:
        """显式 Reinforcement N 征召 + 指派（G1-23/G1-24，Q 件 F；禁 random）。

        从 get_available_legions()（UNRAISED ∪ DISBANDED）池按 N 征召，assign 到 war
        并记录 legion_number（兼容读/provenance，N 件 §1；战斗权威 = live 实体，GB）。
        返回实际征召编号列表。
        """
        ms = self.state.get_military_system()
        if not ms or count <= 0:
            return []
        available = ms.get_available_legions()
        recruit_count = min(count, len(available))
        if recruit_count == 0:
            return []
        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [number for number, success, *_ in results if success]
        if not recruited_numbers:
            return []
        ms.assign_to_war(recruited_numbers, war.id, commander_id)
        for number in recruited_numbers:
            war.add_legion_number(number)
        return recruited_numbers

    def is_war_commander_valid(self, war) -> bool:
        """P2 前置判定：war 是否存在有效指挥官（F 件 §2.1 / H 件 §3）。

        有效 = commander_id 非 None 且 commander 实体存活且非（absent proconsul/propraetor）。
        供 Takeover P2 / Continue 前置 / AI 路径 / DTO 单一判定（R-01）。
        """
        if war is None or war.commander_id is None:
            return False
        old_cmd = self.state.get_member(war.commander_id)
        if old_cmd is None or old_cmd.is_dead:
            return False
        if old_cmd.is_absent and old_cmd.office in ("proconsul", "propraetor"):
            return False
        return True

    def _default_reinforcement_n(self) -> int:
        """Reinforcement N 冻结默认（G 件 §4）：pool==0 → 0（G1-24）；pool>0 → min=1。"""
        ms = self.state.get_military_system()
        pool = len(ms.get_available_legions()) if ms else 0
        return 0 if pool == 0 else 1

    def _validate_reinforcement_n(self, n) -> Optional[int]:
        """Reinforcement N fail-closed 重校验（G 件 §4）。返回规范化 N 或 None（拒绝）。

        N<0 → 拒绝；pool>0 且 N==0 → 拒绝；N>pool → 拒绝；pool==0 且 N==0 → 接受。
        N 缺省 → 冻结默认（min）。国库不参与上限（G1-17/R-10）。
        """
        if n is None:
            n = self._default_reinforcement_n()
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            return None
        ms = self.state.get_military_system()
        pool = len(ms.get_available_legions()) if ms else 0
        if pool == 0:
            return n if n == 0 else None
        return n if 1 <= n <= pool else None

    def execute_war_takeover_deploy(self, war, consul_figure, reinforcement_n: Optional[int] = None) -> bool:
        """统一 Takeover 部署 mutation（WP-G-R4，SA v1.7 §2.4b：原 execute_war_takeover_direct
        部署十步，业务语义/R3 六闭包 KEEP，owner 边界移动到 advance_senate_phase 部署单元）。

        P1（TRUCE + pending treaty，T7）：terminate treaty（clear）→ TRUCE→ACTIVE；
        P2（ACTIVE + no valid commander，T15）：无状态转换、无条约 mutation；
        异常态（ACTIVE+pending / TRUCE+无 pending / 其他状态）→ fail closed False。
        Shared Core：保留幸存 → Legion 全量 rebind → Fleet 全量 rebind → 设 commander →
        显式 Reinforcement N → 新军团 bind 新 Commander → 一致结果（R-14 反 split-brain）。
        FC-05 原子性：显式 N>0 但征召 0 成功 → commander 回滚不回写。

        调用约束（R4-10）：仅 senate_api.advance_senate_phase 的部署单元可调用（takeover_war
        Submit 零部署、execute_ai_takeover_direct_action 废弃直连——均不得直接调用）。
        """
        if not war or not consul_figure:
            return False
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if ws is None or ms is None:
            return False

        # --- 0. Reinforcement N 校验先行（G 件 §4 fail-closed：拒绝时零 mutation）---
        n = self._validate_reinforcement_n(reinforcement_n)
        if n is None:
            self.state.log_event(
                f"execute_war_takeover_direct: war={war.id} Reinforcement N 非法（fail closed）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "invalid_reinforcement_n"},
            )
            return False

        # --- 双前置校验（fail closed）---
        treaty = war.peace_treaty
        treaty_pending = bool(treaty and treaty.get("status") == "pending")
        if war.status == WarStatus.TRUCE:
            if not treaty_pending:
                self.state.log_event(
                    f"execute_war_takeover_direct: war={war.id} TRUCE 但无 pending treaty（fail closed）",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "reason": "truce_without_pending_treaty"},
                )
                return False
            # P1 前置处理（分支专属）：terminate treaty + TRUCE→ACTIVE
            war.clear_peace_treaty()
            if not ws.move_truce_war_to_active(war):
                return False
        elif war.status == WarStatus.ACTIVE:
            if treaty_pending:
                # 异常态：ACTIVE + pending → fail closed（禁无条件幂等 cleanup，F 件 §2.1）
                self.state.log_event(
                    f"execute_war_takeover_direct: war={war.id} ACTIVE+pending 异常态（fail closed）",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "reason": "active_with_pending_treaty"},
                )
                return False
            if self.is_war_commander_valid(war):
                # 禁 ACTIVE + valid commander 任意接管（F 件 §5.1；幂等/重入拒绝）
                self.state.log_event(
                    f"execute_war_takeover_direct: war={war.id} 已有有效指挥官（幂等拒绝）",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "reason": "already_taken_over"},
                )
                return False
            # P2：无状态转换、无条约 mutation
        else:
            self.state.log_event(
                f"execute_war_takeover_direct: war={war.id} 状态 {war.status} 不可接管（fail closed）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "war_not_takeoverable"},
            )
            return False

        # --- Shared Core 十步 ---
        # 1. Validate eligible Consul（调用方已校验执政官资格；此处防御）
        if consul_figure.is_dead:
            return False
        new_commander_id = consul_figure.id

        # 2/3/4. 读取实际幸存 attached Legion/Fleet 实体并保留（G1-04/R-08：禁自愿裁员）
        surviving_legions = ms.get_legions_for_battle(war.id)
        naval_system = self.state.naval_system
        surviving_fleets = naval_system.get_fleets_by_war(war.id) if naval_system else []

        # 5. 幸存 Legion rebind → 新 Consul（R-14 反 split-brain）
        for legion in surviving_legions:
            legion.commander_id = new_commander_id

        # 6. 幸存 Fleet rebind → 新 Consul（E3 setter；_target_war_id 归 GC 不动）
        for fleet in surviving_fleets:
            fleet.commander_id = new_commander_id

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

        # 7. 设 War.commander_id → 新 Consul
        war.commander_id = new_commander_id

        # 8. 显式 Reinforcement N（Q 件 F；FC-05：N>0 征召失败 → commander 回滚不回写）
        recruited = self._recruit_and_assign_exact(war, new_commander_id, n)
        if n > 0 and not recruited:
            war.commander_id = old_cmd_id
            self.state.log_event(
                f"execute_war_takeover_direct: war={war.id} 军团招募失败",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "legion_recruit_failed"},
            )
            return False
        # 9. 新征召军团 bind → 新 Commander（_recruit_and_assign_exact 内 assign_to_war 完成）

        # 10. 持久一致结果
        self._set_absent(consul_figure)
        self.state.log_event(
            f"战争接管部署执行: war={war.id}, commander={consul_figure.id}, reinforcement_n={n}",
            level=logging.INFO,
            extra={"war_id": war.id, "commander_id": consul_figure.id, "reinforcement_n": n,
                   "method": "execute_war_takeover_deploy", "owner": "advance_senate_phase"},
        )
        return True

    # WP-G-R4（SA v1.7 §2.4b）：legacy 名称别名——部署十步仍居本方法体，但唯一调用 owner
    # = advance_senate_phase 部署单元（R4-10 不双写）。旧直连调用语义被 R4 废弃：
    # takeover_war 不再经此部署；execute_ai_takeover_direct_action 不再直接 mutation。
    def execute_war_takeover_direct(self, war, consul_figure, reinforcement_n: Optional[int] = None) -> bool:
        return self.execute_war_takeover_deploy(war, consul_figure, reinforcement_n=reinforcement_n)

    def execute_war_continue_direct(self, war, consul_figure, reinforcement_n: Optional[int] = None) -> bool:
        """Continue Existing Command 唯一 mutation（G1-21 / F 件 §2.2 / T8）。

        前置：TRUCE + pending + 现有 commander 有效。
        语义：清条约 → TRUCE→ACTIVE → 保留 commander（禁静默替换）→ 保留幸存 →
        征召 N（显式）→ 新军团 bind 现有 commander。
        """
        if not war or not consul_figure:
            return False
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if ws is None or ms is None:
            return False
        treaty = war.peace_treaty
        treaty_pending = bool(treaty and treaty.get("status") == "pending")
        if war.status != WarStatus.TRUCE or not treaty_pending:
            self.state.log_event(
                f"execute_war_continue_direct: war={war.id} 前置不满足（fail closed）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "not_truce_pending"},
            )
            return False
        if not self.is_war_commander_valid(war):
            self.state.log_event(
                f"execute_war_continue_direct: war={war.id} 现有 commander 无效（fail closed）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "no_valid_commander"},
            )
            return False

        # 0. Reinforcement N 校验先行（G 件 §4 fail-closed：拒绝时零 mutation）
        n = self._validate_reinforcement_n(reinforcement_n)
        if n is None:
            self.state.log_event(
                f"execute_war_continue_direct: war={war.id} Reinforcement N 非法（fail closed）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "reason": "invalid_reinforcement_n"},
            )
            return False

        # 1. 清 pending treaty（non-submitted/cleared，显式终止）
        war.clear_peace_treaty()
        # 2. TRUCE → ACTIVE（容器迁移原语，禁复制容器操作）
        if not ws.move_truce_war_to_active(war):
            return False
        # 3. 现有 commander 保留（war.commander_id 不变，禁静默替换）
        existing_commander_id = war.commander_id
        # 4. 保留现有幸存军团（禁裁员，无操作）
        # 5. 征召 Reinforcement N（新 Consul 执行征召决策，G1-21）
        recruited = self._recruit_and_assign_exact(war, existing_commander_id, n)
        if n > 0 and not recruited:
            return False
        # 6. 新征召军团 bind → 现有 commander（_recruit_and_assign_exact 内完成）
        self.state.log_event(
            f"战争继续指挥直接执行: war={war.id}, commander={existing_commander_id}, reinforcement_n={n}",
            level=logging.INFO,
            extra={"war_id": war.id, "commander_id": existing_commander_id, "reinforcement_n": n,
                   "method": "execute_war_continue_direct"},
        )
        return True
