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
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.war_takeover_decider import WarTakeoverDecider



if TYPE_CHECKING:
    from src.core.game_state import GameState


class SenateCommand(Command):
    """元老院阶段命令"""

    name = "senate"
    aliases = ["s"]
    description = "执行元老院阶段 (Senate Phase) - 处理合同、更新派系领袖、确定主持人"

    def __init__(self, state: "GameState",
                 vote_decider: Optional[SenateVoteDecider] = None,
                 takeover_decider: Optional[WarTakeoverDecider] = None):  # 新增
        super().__init__(state)
        self.vote_decider = vote_decider or AutoSenateVoteDecider()
        self.budget_decider = AutoBudgetDecider()
        self.takeover_decider = takeover_decider or AutoWarTakeoverDecider()  # 新增

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

        # 2.2 战争接管处理（新增）
        self._process_war_takeover()

        # 2.3 任命总督处理（预留）

        # 2.4 审判总督处理（预留）

        # ========== 3.法案处理 ==========

        # 3.1 预算审批（合同授权）
        self._process_budget_proposals(terms)

        self.state.mark_phase_executed("senate")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True


    def _process_war_takeover(self):
        """处理战争接管：为无指挥官的活跃战争指派指挥官，以及处理 proconsul 机制"""
        ws = self.state.get_war_system()
        if not ws:
            return

        # 获取当前执政官（第一位）
        if not self.state.turn.leader_ids:
            return
        consul_id = self.state.turn.leader_ids[0]
        consul = self.state.get_member(consul_id)
        if not consul:
            return

        # 获取所有活跃战争
        active_wars = ws.get_active_wars()
        for war in active_wars:
            if war.commander_id is None:
                # 无指挥官，由执政官接管（决策器决定）
                if self.takeover_decider.decide_takeover(war, consul, None, self.state):
                    war.commander_id = consul.id
                    consul.is_absent = True
                    print(f"      ✅ 执政官 {consul.name} 接管战争 {war.name}")
                    self.state.log_event(f"执政官 {consul.name} 接管 {war.name}")
                else:
                    print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}")
            else:
                # 已有指挥官，检查是否为前任执政官（proconsul 机制）
                old_cmd = self.state.get_member(war.commander_id)
                if not old_cmd:
                    continue
                # 如果指挥官是 proconsul 或 ex-consul 且不在罗马，新执政官可决定是否接管
                if old_cmd.office in ("proconsul", "ex-consul") and old_cmd.is_absent:
                    if self.takeover_decider.decide_takeover(war, consul, old_cmd, self.state):
                        # 接管：原指挥官返回罗马
                        old_cmd.is_absent = False
                        old_cmd.office = "ex-proconsul"  # 或保留原职，可配置
                        war.commander_id = consul.id
                        consul.is_absent = True
                        print(f"      🔄 执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回罗马")
                        self.state.log_event(f"执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回")
                    else:
                        print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}，由 {old_cmd.name} 继续指挥")

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

        propose_chance = self.state.config.get("testing.propose_war_chance", 0.7)
        always_declare = self.state.config.get("testing.always_declare", False)
        min_legions = self.state.config.get("testing.min_legions", 4)
        max_legions = self.state.config.get("testing.max_legions", 8)

        for war in threats:
            print(f"\n      📋 战争威胁：{war.name}")
            print(f"         威胁等级：{war.threat_level}")

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
                    support = True
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
                    # ========== 自动征召军团并指派指挥官 ==========
                    # 1. 设置战争指挥官为执政官（已在 activate_war 中设置？为确保，再设一次）
                    war.commander_id = consul_id

                    # 2. 获取军事系统
                    # 获取军事系统，如果为 None 则尝试创建（临时修复）
                    ms = self.state.get_military_system()
                    if ms is None:
                        print("      ⚠️ 军事系统未初始化，正在创建临时实例...")
                        from src.core.systems.military_system import MilitarySystem
                        ms = MilitarySystem(self.state)
                        # 临时赋值到 GameState 的私有字段（后续应修正 reset 方法）
                        self.state._military_system = ms

                    if ms:
                        print(
                            f"          军事系统可用，国库 {self.state.treasury}，可用军团数 {len(ms.get_available_legions())}")
                        available_legions = ms.get_available_legions()
                        recruit_count = min(legions, len(available_legions))
                        print(f"          计划征召 {legions} 个军团，实际可征召 {recruit_count} 个")

                        if recruit_count > 0:
                            results = ms.recruit_multiple(recruit_count)
                            recruited_numbers = [r[0] for r in results if r[1]]
                            print(
                                f"          征召结果：成功 {len(recruited_numbers)} 个，失败 {len(results) - len(recruited_numbers)} 个")

                            if recruited_numbers:
                                assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul_id)
                                print(f"          指派结果：{msg}")
                                if hasattr(war, 'add_legion_number'):
                                    for num in recruited_numbers:
                                        war.add_legion_number(num)
                            else:
                                print(f"          军团征召失败（可能国库不足）。")
                        else:
                            print(f"          警告：无可用军团或国库不足，无法征召！")

                        if recruit_count < legions:
                            print(f"          实际征召 {recruit_count}/{legions} 个军团。")
                    else:
                        print(f"          错误：无法获取军事系统，军团未征召！")

                    # 3. 标记执政官出征
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