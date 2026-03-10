# src/ui/commands/phase_senate.py
"""
元老院阶段命令 - 处理合同、更新派系领袖、确定主持人
集成停战草案审批流程（MVP 0.7.1）
"""
import random
import logging
from typing import List, TYPE_CHECKING, Optional, Tuple, Any
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
from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
from src.core.deciders.land_proposal_decider import LandProposalDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.war import War
    from src.core.entities.contract import Contract


class SenateCommand(Command):
    """元老院阶段命令"""

    name = "senate"
    aliases = ["s"]
    description = "执行元老院阶段 (Senate Phase) - 处理合同、更新派系领袖、确定主持人、审批停战草案"

    def __init__(self, state: "GameState",
                 vote_decider: Optional[SenateVoteDecider] = None,
                 takeover_decider: Optional[WarTakeoverDecider] = None,
                 land_proposal_deciders: Optional[List[LandProposalDecider]] = None,
                 veto_decider: Optional[TribuneVetoDecider] = None):
        super().__init__(state)
        self.vote_decider = vote_decider if vote_decider is not None else AutoSenateVoteDecider()
        self.budget_decider = AutoBudgetDecider()
        self.takeover_decider = takeover_decider if takeover_decider is not None else AutoWarTakeoverDecider()
        self.land_proposal_deciders = land_proposal_deciders if land_proposal_deciders is not None else [
            AutoLandProposalDecider("populares", "distribution"),
            AutoLandProposalDecider("optimates", "sale")
        ]
        self.veto_decider = veto_decider if veto_decider is not None else AutoTribuneVetoDecider()
        self.proposed_governors = []   # 存储总督任命提案
        self.passed_peace_treaties = []  # 存储通过的停战草案
        self.rejected_peace_treaties = []  # 存储被否决的停战草案（待恢复战争）

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

        # ========== 3. 收集所有通过的提案 ==========
        # 宣战提案列表：每个元素为 (war, consul_id, legions)
        passed_wars: List[Tuple["War", int, int]] = []
        # 通过的合同列表（需要状态变为 BUDGETED）
        passed_contracts: List["Contract"] = []
        # 通过的土地法案列表
        passed_land_acts: List[dict] = []
        # 通过的行省总督列表
        self.proposed_governors = []  # 清空之前的提案
        self.passed_peace_treaties = []  # 清空之前的停战草案
        self.rejected_peace_treaties = []

        # 3.1 宣战提案处理
        self._process_war_proposals(passed_wars)

        # 3.2 停战草案处理（收集并自动提交）
        peace_proposals = self._process_peace_proposals(terms)

        # 3.3 行省总督任命提案
        self._process_governor_appointments(terms)

        # 3.4 预算审批（合同授权），收集通过的合同
        self._process_budget_proposals(terms, passed_contracts)

        # 3.5 土地法案，收集通过的提案
        self._process_land_proposals(terms, passed_land_acts)

        # 3.6 对停战草案进行投票（如果存在）
        if peace_proposals:
            self.passed_peace_treaties = self._vote_on_peace_proposals(peace_proposals)

        for war in self.passed_peace_treaties:
            print(f"  - {war.name}")

        # ========== 4. 保民官否决 ==========
        tribune = self._get_tribune()
        if tribune:
            print(f"\n   🛡️ 保民官 {tribune.name} 正在审查通过的提案...")
            # 宣战否决
            for war in self.passed_peace_treaties:
                print(f"  - {war.name}")
            new_wars = []
            for war, consul_id, legions in passed_wars:
                if self.veto_decider.decide_veto(war, tribune.id, self.state):
                    print(f"      ❌ 保民官否决了宣战：{war.name}")
                    self.state.log_event(f"保民官否决宣战: {war.name}")
                else:
                    new_wars.append((war, consul_id, legions))
            passed_wars = new_wars

            # 停战草案否决
            new_peace = []
            for war in self.passed_peace_treaties:
                issue = {'type': 'peace', 'war_id': war.id, 'treaty': war.peace_treaty}
                veto_result = self.veto_decider.decide_veto(issue, tribune.id, self.state)  # 修正这里

                if veto_result:
                    print(f"      ❌ 保民官否决了 {war.name} 的停战草案")
                    self.state.log_event(f"保民官否决停战草案: {war.name}")
                    war.clear_peace_treaty()
                    war_system = self.state.get_war_system()
                    if war_system:
                        war_system._move_to_active(war)
                else:
                    new_peace.append(war)
            self.passed_peace_treaties = new_peace

            # 总督否决
            new_governors = []
            for gov in self.proposed_governors:
                issue = {
                    'type': 'governor_appointment',
                    'province_id': gov['province_id'],
                    'new_governor_id': gov['new_governor_id'],
                    'old_governor_id': gov['old_governor_id']
                }
                if self.veto_decider.decide_veto(issue, tribune.id, self.state):
                    province = self.state.get_province(gov['province_id'])
                    prov_name = province.name if province else f"ID:{gov['province_id']}"
                    print(f"      ❌ 保民官否决了行省 {prov_name} 的总督任命")
                    self.state.log_event(f"保民官否决行省 {prov_name} 总督任命")
                else:
                    new_governors.append(gov)
            self.proposed_governors = new_governors

            # 合同否决
            new_contracts = []
            for contract in passed_contracts:
                if self.veto_decider.decide_veto(contract, tribune.id, self.state):
                    print(f"      ❌ 保民官否决了合同：{contract.name}")
                    self.state.log_event(f"保民官否决合同: {contract.name} (ID:{contract.id})")
                else:
                    new_contracts.append(contract)
            passed_contracts = new_contracts

            # 土地法案否决
            new_acts = []
            for act in passed_land_acts:
                if self.veto_decider.decide_veto(act, tribune.id, self.state):
                    act_type = act['type']
                    percent = act['percent']
                    desc = self._get_land_act_description(act_type, percent)
                    print(f"      ❌ 保民官否决了土地法案：{desc}")
                    self.state.log_event(f"保民官否决土地法案: {desc}")
                else:
                    new_acts.append(act)
            passed_land_acts = new_acts
        else:
            print(f"\n   🛡️ 当前无保民官，不行使否决权")


        # ========== 5. 执行通过的提案 ==========

        # 5.1 执行宣战
        for war, consul_id, legions in passed_wars:
            self._execute_war_declaration(war, consul_id, legions)

        # 5.2.1 执行总督任命
        self._execute_governor_appointments()

        # 5.2.2 镇压起义战争接管
        self._assign_rebellion_commanders()  # 起义战争指派总督

        # 5.3 战争接管处理（与原逻辑一致）
        self._process_war_takeover()

        # 5.4 执行通过的停战草案
        self._execute_passed_peace_treaties()

        # 5.5 标记合同为 BUDGETED
        for contract in passed_contracts:
            contract.status = ContractStatus.BUDGETED
            print(f"      ✅ {contract.name} 预算通过，状态变为 BUDGETED")
            self.state.log_event(f"合同预算通过：{contract.name}")

        # 5.6 存入土地法案
        for act in passed_land_acts:
            self.state.add_pending_land_act(act)
            print(f"      ✅ {act['description']} 通过，等待下回合执行")

        self.state.mark_phase_executed("senate")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # =================================== MVP 0.7 =============================================

    # ==================== 新增：MVP 0.7-4 行省起义镇压 ====================
    def _assign_rebellion_commanders(self):
        """为起义战争指派总督作为指挥官并征召军团"""
        war_system = self.state.get_war_system()
        if not war_system:
            return

        ms = self.state.get_military_system()
        if not ms:
            return

        rebellion_strength = self.state.config.get("combat_rules.rebellion_strength", 5)
        # 计算所需军团数量（假设每个军团基础战力2）
        legion_count = (rebellion_strength + 1) // 2
        if legion_count < 1:
            legion_count = 1

        for war in war_system.get_active_wars():
            if war.rebellion_province_id is None or war.commander_id is not None:
                continue

            province = self.state.get_province(war.rebellion_province_id)
            if not province:
                continue

            # 优先使用候任总督，若无则使用现任总督
            governor_id = province.governor_designate_id or province.governor_id
            if governor_id is None:
                continue

            commander = self.state.get_member(governor_id)
            if not commander or commander.is_dead:
                continue

            # 征召军团
            available = ms.get_available_legions()
            if not available:
                print(f"      ⚠️ 无可用军团镇压 {province.name} 起义")
                continue

            recruit_count = min(legion_count, len(available))
            results = ms.recruit_multiple(recruit_count)
            recruited_numbers = [r[0] for r in results if r[1]]
            if not recruited_numbers:
                print(f"      ⚠️ 军团征召失败，无法镇压 {province.name} 起义")
                continue

            # 指派指挥官和军团
            war_system.assign_commander(war.id, governor_id, len(recruited_numbers))
            ms.assign_to_war(recruited_numbers, war.id, governor_id)
            commander.is_absent = True  # 总督出征

            print(f"      ✅ 任命 {commander.name} 为 {war.name} 指挥官，征召 {len(recruited_numbers)} 个军团")
            self.state.log_event(
                f"指派总督 {commander.name} 镇压起义",
                extra={"war_id": war.id, "commander_id": governor_id}
            )


    # ==================== 新增：停战草案相关方法 ====================

    def _process_peace_proposals(self, terms):
        """收集所有待决停战草案，并自动提交给元老院"""
        war_system = self.state.get_war_system()
        if not war_system:
            return []

        pending_wars = war_system.get_truce_wars_with_pending_treaty()
        if not pending_wars:
            return []

        print(f"\n\t====================== 停战草案审批 ====================")
        proposals = []
        for war in pending_wars:
            treaty = war.peace_treaty
            print(f"      📜 {war.name}：赔款 {treaty['indemnity']} 塔兰特，有效期 {treaty['duration']} 回合")
            proposals.append(war)

        # 标记为已提交
        for war in proposals:
            treaty = war.peace_treaty
            if treaty:
                war.set_peace_treaty_status('submitted')
        return proposals

    def _vote_on_peace_proposals(self, proposals: List["War"]):
        """对提交的停战草案进行元老院投票"""
        if not proposals:
            return []

        passed = []
        for war in proposals:
            print(f"\n      📜 表决停战：{war.name}")
            treaty = war.peace_treaty

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                issue = {'type': 'peace', 'war_id': war.id, 'treaty': treaty}
                support = self.vote_decider.decide_vote(issue, faction, self.state)

                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，草案未通过。")
                continue

            support_ratio = votes_for / total_influence
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                passed.append(war)
                print(f"          ✅ 停战草案通过，等待保民官否决")
            else:
                print(f"          ❌ 停战草案否决")
                war.clear_peace_treaty()
                war_system = self.state.get_war_system()
                if war_system:
                    war_system._move_to_active(war)


        for war in passed:
            print(f"  - {war.name}")

        return passed

    def _execute_passed_peace_treaties(self):
        """执行通过的停战草案：记录赔款、待解散军团、到期回合"""
        war_system = self.state.get_war_system()
        if not war_system or not self.passed_peace_treaties:
            return

        for war in self.passed_peace_treaties:
            print(f"  - {war.name}")
            treaty = war.peace_treaty
            if not treaty or treaty.get('status') != 'submitted':
                continue

            war.set_peace_treaty_status('approved')
            war.set_indemnity_due(treaty['indemnity'])

            # ===== 新增：召回所有军团，解除与战争的关联 =====
            ms = self.state.get_military_system()
            if ms:
                ms.recall_from_war(war.id)

            if war.legion_numbers:
                war_system.add_legions_to_disband(war.legion_numbers)

            end_turn = self.state.turn.turn_number + treaty['duration']
            war.set_truce_end_turn(end_turn)

            print(f"      ✅ {war.name} 停战草案已批准，赔款 {treaty['indemnity']}，有效期 {treaty['duration']} 回合")
            self.state.log_event(
                f"停战草案批准: {war.name} 赔款 {treaty['indemnity']}",
                extra={'type': 'peace_treaty_approved', 'war_id': war.id}
            )

# =================================== MVP 0.1-0.5 =============================================

    def _execute_governor_appointments(self):
        if not self.proposed_governors:
            return
        print("\n\t====================== 总督任命执行 ====================")
        for gov in self.proposed_governors:
            province = self.state.get_province(gov['province_id'])
            if not province:
                continue
            new_fig = self.state.get_member(gov['new_governor_id'])
            old_fig = self.state.get_member(gov['old_governor_id']) if gov['old_governor_id'] else None

            # 记录旧总督，供决算阶段返回
            province._old_governor_id = gov['old_governor_id']
            # 设置候任总督
            province._governor_designate_id = gov['new_governor_id']

            if new_fig:
                # 新总督离开罗马（在途），但暂不授予官职
                new_fig.is_absent = True
                new_fig_name = new_fig.get_formal_name()
            else:
                new_fig_name = "未知"

            old_name = old_fig.get_formal_name() if old_fig else "无"
            print(f"      ✅ {province.name} 任命新总督: {new_fig_name} (候任)，旧总督 {old_name} 仍在任")
            self.state.log_event(
                f"行省 {province.name} 任命候任总督 {new_fig_name}",
                extra={
                    'type': 'governor_appointed_designate',
                    'province_id': province.province_id,
                    'new_governor': gov['new_governor_id'],
                    'old_governor': gov['old_governor_id']
                }
            )

    def _process_governor_appointments(self, terms):
        print("\n\t====================== 行省总督任命 ====================")

        # 获取所有已征服的行省
        all_provinces = [p for p in self.state.get_all_provinces() if p.conquered and p.province_id != 0]

        # 行省分类（仅基于已征服行省）
        proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
        propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

        # 候选人获取函数（不变）
        def get_candidates(office_type: str):
            cand_list = []
            for fig in self.state.get_living_members():
                if fig.is_absent:
                    continue
                # 排除现任官职（非 ex- 开头）
                if fig.office is not None and not fig.office.startswith("ex-"):
                    continue
                last_end = None
                for term in fig.office_history:
                    if term.office_type == office_type and term.end_turn is not None:
                        if last_end is None or term.end_turn > last_end:
                            last_end = term.end_turn
                if last_end is not None:
                    cand_list.append((fig, last_end))
            cand_list.sort(key=lambda x: -x[1])
            return [c[0] for c in cand_list]

        consuls = get_candidates('consul')
        praetors = get_candidates('praetor')

        # 修改 assign 函数，增加 used_set 参数
        def assign(provinces, candidates, used_set):
            remaining = list(provinces)
            random.shuffle(remaining)
            assignments = []
            for cand in candidates:
                if cand.id in used_set:
                    continue
                if not remaining:
                    break
                chosen = random.choice(remaining)
                remaining.remove(chosen)
                assignments.append((chosen, cand))
                used_set.add(cand.id)
            return assignments

        used = set()
        proconsul_assignments = assign(proconsul_provinces, consuls, used)
        propraetor_assignments = assign(propraetor_provinces, praetors, used)

        # 打印分配结果（不变）
        def print_assignments(title, assignments):
            print(f"\n   {title}:")
            if not assignments:
                print("      无行省需要任命")
                return
            for prov, cand in assignments:
                # 计算卸任年份显示
                last_year = None
                req_office = 'consul' if title == '执政官行省' else 'praetor'
                for term in cand.office_history:
                    if term.office_type == req_office and term.end_turn is not None:
                        last_year = term.end_turn
                        break
                if last_year is not None:
                    year = self.state.turn.year + (last_year - self.state.turn.turn_number)
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                else:
                    year_display = "未知"
                print(f"      → {cand.get_formal_name()} (卸任 {year_display}) 抽中 {prov.name}")

        print_assignments("执政官行省 (Proconsul)", proconsul_assignments)
        print_assignments("大法官行省 (Propraetor)", propraetor_assignments)

        # 提示未被分配的行省（仅针对已征服行省）
        all_provinces_set = set(proconsul_provinces + propraetor_provinces)
        assigned_provinces = set(p for p, _ in proconsul_assignments + propraetor_assignments)
        unassigned = all_provinces_set - assigned_provinces
        if unassigned:
            for p in unassigned:
                print(f"      ⚠️ {p.name} 无合格候选人，现任总督留任一年")

        # 构建提案（仅针对已征服行省）
        self.proposed_governors = []
        for prov, cand in proconsul_assignments + propraetor_assignments:
            self.proposed_governors.append({
                'province_id': prov.province_id,
                'new_governor_id': cand.id,
                'old_governor_id': prov.governor_id,
                'governor_type': prov.governor_type
            })

        self.state.log_event(
            f"总督任命提案收集完成，共 {len(self.proposed_governors)} 项",
            level=logging.DEBUG,
            extra={"proposals": [p['province_id'] for p in self.proposed_governors]}
        )

    def _get_tribune(self) -> Optional['Figure']:
        """获取当前保民官（假设只有一人）"""
        for fig in self.state.get_living_members():
            if fig.office == "tribune":
                return fig
        return None

    def _execute_war_declaration(self, war: "War", consul_id: int, legions: int):
        """实际执行宣战：激活战争、征召军团、指派指挥官"""
        ws = self.state.get_war_system()
        if not ws:
            print(f"      ⚠️ 战争系统不可用，无法执行宣战")
            return
        success = ws.activate_war(war.id, consul_id, legions)
        if not success:
            print(f"      ⚠️ 激活战争失败")
            return

        war.commander_id = consul_id

        consul = self.state.get_member(consul_id)
        if not consul:
            return

        # 征召军团并指派
        ms = self.state.get_military_system()
        if ms:
            # 原有自动征召逻辑（可复用 _auto_recruit_and_assign_legions_for_war）
            self._auto_recruit_and_assign_legions_for_war(war, consul_id)

        consul.is_absent = True
        self.state.log_event(f"宣战通过：{war.name}，执政官 {consul.name} 出征，批准军团 {legions}")
        print(f"      ✅ 宣战通过！执政官 {consul.name} 出征，影响力不再计入元老院。")
        new_presiding = self.state.get_presiding_officer()
        if new_presiding:
            print(f"      元老院新主持人：{new_presiding.name}（官职 {new_presiding.office}）")

    def _process_land_proposals(self, terms, passed_land_acts: List[dict]):
        """处理土地法案提案，通过的放入 passed_land_acts"""
        land_rules = self.state.config.get("political_rules.land_proposal", {})
        submit_chance = land_rules.get("submit_chance", 0.7)

        presiding = self.state.get_presiding_officer()
        if not presiding:
            print(f"\n   ⚠️ 无主持人，无法处理土地法案。")
            return

        proposals = []
        for faction in self.state.factions.values():
            for decider in self.land_proposal_deciders:
                result = decider.decide_proposal(faction.id, self.state)
                if result:
                    act_type, percent = result
                    proposals.append({
                        'type': act_type,
                        'percent': percent,
                        'proposer_faction': faction.id,
                        'description': self._get_land_act_description(act_type, percent)
                    })

        if not proposals:
            print(f"\n   📭 无土地法案提案。")
            return

        for prop in proposals:
            if random.random() < submit_chance:
                print(f"\n   📋 {prop['description']} 由执政官 {presiding.name} 提交元老院表决。")
                votes_for = 0
                votes_against = 0
                total_influence = 0

                for faction in self.state.get_active_factions():
                    influence = faction.get_senate_influence(self.state)
                    if influence == 0:
                        continue
                    total_influence += influence

                    support = self.vote_decider.decide_vote(prop, faction, self.state)
                    if support:
                        votes_for += influence
                        print(f"          {faction.name} 支持，影响力 {influence}")
                    else:
                        votes_against += influence
                        print(f"          {faction.name} 反对，影响力 {influence}")

                if total_influence == 0:
                    print(f"          无元老在场，法案未通过。")
                    continue

                support_ratio = votes_for / total_influence
                print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")
                if support_ratio > 0.5:
                    passed_land_acts.append(prop)
                    print(f"          ✅ 法案通过，等待保民官否决")
                else:
                    print(f"          ❌ 法案否决。")
            else:
                print(f"\n   ⏳ 执政官 {presiding.name} 决定不提交 {prop['description']}。")

    def _get_land_act_description(self, act_type: str, percent: float) -> str:
        if act_type == 'distribution':
            return f"平民分地法案（分配 {percent * 100:.1f}% 国家公地）"
        else:
            return f"贵族买地法案（出售 {percent * 100:.1f}% 国家公地）"

    def _vote_on_land_act(self, act: dict):
        """对土地法案进行元老院投票"""
        votes_for = 0
        votes_against = 0
        total_influence = 0

        for faction in self.state.get_active_factions():
            influence = faction.get_senate_influence(self.state)
            if influence == 0:
                continue
            total_influence += influence

            # 使用通用投票决策器
            support = self.vote_decider.decide_vote(act, faction, self.state)
            if support:
                votes_for += influence
                print(f"          {faction.name} 支持，影响力 {influence}")
            else:
                votes_against += influence
                print(f"          {faction.name} 反对，影响力 {influence}")

        if total_influence == 0:
            print(f"          无元老在场，法案未通过。")
            return

        support_ratio = votes_for / total_influence
        print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")
        if support_ratio > 0.5:
            print(f"          ✅ 法案通过！")
            self.state.add_pending_land_act(act)
            self.state.log_event(
                f"土地法案通过: {act['description']}",
                extra={"type": "land_act", "act": act['type'], "percent": act['percent']}
            )
        else:
            print(f"          ❌ 法案否决。")

    def _process_war_takeover(self):
        """处理战争接管：为无指挥官的活跃战争指派指挥官，以及处理 proconsul 机制"""

        ws = self.state.get_war_system()
        if not ws:
            return

        # 只处理 ACTIVE 战争
        active_wars = ws.get_active_wars()
        if not active_wars:
            return

        # 获取当前执政官（第一位）
        if not self.state.turn.leader_ids:
            return
        consul_id = self.state.turn.leader_ids[0]
        consul = self.state.get_member(consul_id)
        if not consul:
            return

        # ===== 新增调试打印 =====

        for war in active_wars:
            print(f"  - {war.name}, status: {war.status}, commander_id: {war.commander_id}")

        # ========================

        for war in active_wars:
            # 确保战争是 ACTIVE 状态（二次确认）
            if war.status != WarStatus.ACTIVE:
                continue

            if war.commander_id is None:
                # 无指挥官，由执政官接管（决策器决定）
                # ===== 新增调试打印 =====
                takeover_decision = self.takeover_decider.decide_takeover(war, consul, None, self.state)
                # ========================
                if takeover_decision:
                    war.commander_id = consul.id
                    consul.is_absent = True
                    print(f"      ✅ 执政官 {consul.name} 接管战争 {war.name}")
                    self._auto_recruit_and_assign_legions_for_war(war, consul.id)
                    self.state.log_event(f"执政官 {consul.name} 接管 {war.name}")
                else:
                    print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}")
            else:
                # 已有指挥官，检查是否为前任执政官（proconsul 机制）
                # ========================
                old_cmd = self.state.get_member(war.commander_id)
                if not old_cmd:
                    continue
                # 如果指挥官是 proconsul 或 ex-consul 且不在罗马，新执政官可决定是否接管
                if old_cmd.office in ("proconsul", "ex-consul") and old_cmd.is_absent:
                    if self.takeover_decider.decide_takeover(war, consul, old_cmd, self.state):
                        old_cmd.is_absent = False
                        old_cmd.office = "ex-proconsul"
                        war.commander_id = consul.id
                        consul.is_absent = True
                        print(f"      🔄 执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回罗马")
                        self._auto_recruit_and_assign_legions_for_war(war, consul.id)
                        self.state.log_event(f"执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回")
                    else:
                        print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}，由 {old_cmd.name} 继续指挥")

    def _auto_recruit_and_assign_legions_for_war(self, war, consul_id):
        """自动征召军团并指派给战争（用于宣战和接管）"""
        ms = self.state.get_military_system()
        if not ms:
            print("      ⚠️ 军事系统不可用，无法征召军团")
            return

        # 检查战争是否已有军团，如果有则直接使用现有军团，不再征召
        existing_legions = ms.get_legions_for_battle(war.id) if ms else []
        if existing_legions:
            print(f"      ℹ️ 战争已有 {len(existing_legions)} 个军团，无需征召")
            return

        # 获取应征召的军团数量
        legions = getattr(war, 'proposed_legions', 0)
        if legions <= 0:
            min_leg = self.state.config.get("testing.min_legions", 4)
            max_leg = self.state.config.get("testing.max_legions", 8)
            legions = random.randint(min_leg, max_leg)
            print(f"      ℹ️ 战争未指定军团数，自动分配 {legions} 个")

        available = ms.get_available_legions()
        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)

        # 移除国库资金限制，允许负债征召
        recruit_count = min(legions, len(available))  # 只受可用军团数和需求数限制
        if recruit_count == 0:
            print("      ⚠️ 没有可用军团，无法征召")
            return

        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            print("      ⚠️ 军团征召失败")
            return

        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul_id)
        print(f"      {msg}")
        for num in recruited_numbers:
            war.add_legion_number(num)

        self.state.log_event(f"宣战 {war.name}，征召 {len(recruited_numbers)} 军团")

    def _process_war_proposals(self, passed_wars: List[Tuple["War", int, int]]):
        """处理宣战提案，通过的放入 passed_wars"""
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

        # 获取海军系统（用于检查舰队）
        naval_system = self.state.naval_system

        for war in threats:
            # 如果战争需要海战，检查是否有可用舰队
            if war.naval_required:
                if not naval_system or not naval_system.get_available_fleets():
                    print(f"\n      📋 战争威胁：{war.name}（需要海战）")
                    print(f"         当前无可用舰队，无法宣战。")
                    continue

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
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                # 不立即激活，放入 passed_wars
                passed_wars.append((war, consul_id, legions))
                self.state.log_event(
                    f"宣战通过 (待否决): {war.name}，批准军团 {legions}",
                    extra={"type": "war_declaration_passed", "war_id": war.id, "legions": legions}
                )
                print(f"          ✅ 元老院批准宣战，等待保民官否决")
            else:
                print(f"          ❌ 宣战被元老院否决。")

    def _process_budget_proposals(self, terms, passed_contracts: List["Contract"]):
        """处理预算提案，通过的放入 passed_contracts"""
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
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                passed_contracts.append(contract)
                print(f"          ✅ 预算通过，等待保民官否决")
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