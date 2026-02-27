# src/ui/commands/phase_senate.py
"""
元老院阶段命令 - 处理合同、更新派系领袖、确定主持人
"""
import random
from typing import List, TYPE_CHECKING, Optional
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractType, ContractStatus
from src.ui.commands.func_status import get_progress_bar
from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider
from src.core.entities.war import WarStatus


if TYPE_CHECKING:
    from src.core.game_state import GameState


class SenateCommand(Command):
    """元老院阶段命令"""

    name = "senate"
    aliases = ["s"]
    description = "执行元老院阶段 (Senate Phase) - 处理合同、更新派系领袖、确定主持人"

    def __init__(self, state: "GameState",
                 vote_decider: Optional[SenateVoteDecider] = None):
        super().__init__(state)
        self.vote_decider = vote_decider or AutoSenateVoteDecider()
        # 如果还需要合同选取逻辑（decide_proposals），可保留 BudgetDecider 或将其也通用化
        # 但为简化，我们继续保留原有 budget_decider 用于选取提案
        self.budget_decider = AutoBudgetDecider()

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("population"):
            print("⚠️ 必须先执行人口阶段 (population)")
            return False

        if self.state.is_phase_executed("senate"):
            print("⚠️ 元老院阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_senate} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # ========== 1. 更新派系领袖 ==========
        print(f"\n   👑 Faction Leaders Updated:")
        for faction in self.state.factions.values():
            leader = faction.update_faction_leader(self.state)
            if leader:
                print(f"      {faction.name}: {leader.name} (Influence: {leader.influence})")

        # ========== 2. 主持人确定 ==========
        presiding = self.state.get_presiding_officer()
        if not presiding:
            self.state.log_event("Error: No presiding officer!")
            return False

        office_display = presiding.office if presiding.office else "无"
        print(f"\n   🎤 Presiding Officer: {presiding.name} ({office_display})")

        # 2.1 宣战提案处理（新增）
        self._process_war_proposals()

        # 2.2 任命总督处理（预留）

        # 2.3 审判总督处理（预留）

        # ========== 3.法案处理 ==========

        # 3.1 预算审批（合同授权）
        self._process_budget_proposals(terms)

        self.state.mark_phase_executed("senate")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    import random  # 确保在文件顶部有导入

    def _process_war_proposals(self):
        ws = self.state.get_war_system()
        if not ws:
            return

        threats = [w for w in ws._threats if w.status == WarStatus.THREAT]
        if not threats:
            print(f"\n   ⚔️ 没有战争威胁需要处理。")
            return

        consul_id = self.state.turn.leader_ids[0] if self.state.turn.leader_ids else None
        if not consul_id:
            print(f"\n   ⚠️ 没有执政官，无法处理宣战提案。")
            return
        consul = self.state.get_member(consul_id)
        if not consul:
            return

        print(f"\n   ⚔️ 战争威胁处理（执政官：{consul.name}）：")

        # 读取配置并打印
        propose_chance = self.state.config.get("testing.propose_war_chance", 0.7)
        always_declare = self.state.config.get("testing.always_declare", False)
        min_legions = self.state.config.get("testing.min_legions", 4)
        max_legions = self.state.config.get("testing.max_legions", 8)
        print(f"      DEBUG: propose_chance={propose_chance}, always_declare={always_declare}")

        for war in threats:
            print(f"\n      📋 战争威胁：{war.name}")
            print(f"         威胁等级：{war.threat_level}")

            # 决定是否提议
            if always_declare or random.random() < propose_chance:
                legions = random.randint(min_legions, max_legions)
                print(f"         执政官提议宣战，要求批准 {legions} 个军团。")
            else:
                print(f"         执政官决定暂不宣战。")
                continue

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                if faction.id == consul.faction_id:
                    support = True  # 执政官派系自动支持
                else:
                    support = self.vote_decider.decide_vote(war, faction, self.state)

                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，宣战失败。")
                continue

            support_ratio = votes_for / total_influence
            print(
                f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                success = ws.activate_war(war.id, consul_id, legions)
                if success:
                    consul.is_absent = True
                    self.state.log_event(f"宣战通过：{war.name}，执政官 {consul.name} 出征，批准军团 {legions}")
                    print(f"          ✅ 宣战通过！执政官 {consul.name} 出征，影响力不再计入元老院。")
                    new_presiding = self.state.get_presiding_officer()
                    if new_presiding:
                        print(f"          元老院新主持人：{new_presiding.name}（官职 {new_presiding.office}）")
                else:
                    print(f"          ⚠️ 激活战争失败，请联系管理员。")
            else:
                print(f"          ❌ 宣战被元老院否决。")

    def _process_budget_proposals(self, terms):
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if not pending:
            print(f"\n   📭 No pending contracts for budget.")
            return

        print(f"\n   📋 Budget Proposals:")
        proposals = self.budget_decider.decide_proposals(pending, self.state)
        if not proposals:
            print(f"      No contracts selected for vote.")
            return

        for contract in proposals:
            print(f"\n      📊 {contract.name}")

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                support = self.vote_decider.decide_vote(contract, faction, self.state)
                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，合同无法表决。")
                continue

            support_ratio = votes_for / total_influence
            print(
                f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                contract.status = ContractStatus.BUDGETED
                print(f"          ✅ 预算通过，状态变为 BUDGETED")
                self.state.log_event(f"合同预算通过：{contract.name}")
            else:
                print(f"          ❌ 预算否决，保持 PENDING")

    def _process_pending_contracts(self, terms):
        """处理待决合同"""
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if not pending:
            return

        print(f"\n   📋 Processing {len(pending)} pending contract(s)...")

        for contract in pending:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._vote_tax_contract(contract, terms)
            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                self._assign_works_contract(contract, terms)

    def _vote_tax_contract(self, contract, terms):
        """参议院投票决定包税合同授予"""
        print(f"\n   📊 Voting: {contract.name}")
        print(f"      Cost: {contract.base_cost} | Expected: {contract.expected_profit}")

        # 获取骑士阶层候选人（排除贵族）
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} candidates")
            return

        print(f"\n      Candidates ({terms.cavalry_class}):")
        for idx, (member, faction) in enumerate(candidates[:5], 1):
            print(f"         {idx}. {member.name} ({faction.name}) [Wealth:{member.wealth}]")

        # 简化：自动投票给最富有的骑士（模拟竞标）
        candidates.sort(key=lambda x: x[0].wealth, reverse=True)
        winner, winner_faction = candidates[0]

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            self.state.add_figure_wealth(winner.id, -contract.base_cost)
            self.state.add_treasury(contract.base_cost)
            print(f"\n      ✅ Awarded to {winner.name} ({winner_faction.name})")
            print(f"         {winner.name} paid {contract.base_cost} {terms.currency}")
            print(f"         Treasury +{contract.base_cost} {terms.currency}")

    def _assign_works_contract(self, contract, terms):
        """执政官指派工程合同"""
        print(f"\n   🏗️ Assigning: {contract.name}")
        print(f"      Budget: {contract.base_cost} | Profit: {contract.expected_profit}")

        # 获取执政官
        consuls = [self.state.get_member(cid) for cid in self.state.turn.leader_ids]
        consuls = [c for c in consuls if c]

        if not consuls:
            print(f"      ⏳ Awaiting {terms.leader_title} election...")
            return

        assigning_consul = consuls[0]
        print(f"      👑 Assigned by {terms.leader_title} {assigning_consul.name}")

        # 获取骑士候选人
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} contractors")
            return

        print(f"\n      Available {terms.cavalry_class}:")
        for idx, (member, faction) in enumerate(candidates[:5], 1):
            mgmt = getattr(member, 'management', 5)
            print(f"         {idx}. {member.name} ({faction.name}) [Mgmt:{mgmt}]")

        # 执政官指派给本派系骑士，否则随机
        own_faction_candidates = [(m, f) for m, f in candidates
                                  if m.faction_id == assigning_consul.faction_id]

        if own_faction_candidates:
            winner, winner_faction = random.choice(own_faction_candidates)
        else:
            winner, winner_faction = random.choice(candidates)

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            print(f"\n      ✅ Assigned to {winner.name} ({winner_faction.name})")
            print(f"         Duration: {contract.duration_years} years")