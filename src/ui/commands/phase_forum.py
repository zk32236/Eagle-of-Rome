# src/ui/commands/phase_forum.py
"""
广场阶段命令 - 生成新人物和合同，并展示 Curia 状态
"""

import random
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.ui.commands.func_status import get_progress_bar
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.entities.war import WarStatus
from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
from src.core.deciders.triumph_decider import TriumphDecider

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase)"

    def __init__(self, state: "GameState", retirement_decider=None, recruitment_decider=None, triumph_decider=None):
        super().__init__(state)
        self.retirement_decider = retirement_decider or AutoRetirementDecider(state)
        self.recruitment_decider = recruitment_decider or AutoRecruitmentDecider()
        self.triumph_decider = triumph_decider or AutoTriumphDecider()  # 新增

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("revenue"):
            print("⚠️ 必须先执行税收阶段 (revenue)")
            return False

        if self.state.is_phase_executed("forum"):
            print("⚠️ 广场阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()

        print(f"\n--- {terms.phase_forum} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 淘汰派系成员
        self._process_retirements()

        # 1. 生成新人物
        new_figures = self._generate_new_figures()
        if new_figures:
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the {terms.assembly}:")
            for fig in new_figures:
                tier_emoji = {
                    ClassTier.NOBILE: "🏛️",
                    ClassTier.EQUES: "💰",
                    ClassTier.PLEBEIAN: "👤"
                }.get(fig.class_tier, "❓")
                print(f"      {tier_emoji} {fig.get_formal_name()} ({fig.class_tier.value})")
        else:
            print(f"\n   📭 No new figures this year.")

        # 2. 显示 Curia 状态,处理招募,处理战争威胁
        self._display_curia(terms)
        self._process_recruitment()
        self._process_war_threats()



        # 3. 生成合同（仅生成，不竞标）
        new_contracts = self._generate_contracts()

        # 4. 公告已预算的合同（即将竞标）
        budgeted_contracts = [c for c in self.state.contracts if c.status == ContractStatus.BUDGETED]
        if budgeted_contracts:
            print(f"\n   📜 有预算的合同 ({len(budgeted_contracts)} 份) 将进行竞标：")
            for c in budgeted_contracts:
                type_name = "包税" if c.contract_type == ContractType.TAX_FARMING else "工程"
                print(f"      {type_name}: {c.name}")
        else:
            print(f"\n   📭 没有待竞标的预算合同。")

        # 在 _auto_bid_for_works 循环之前，这样新合同就会触发民变。
        # 因为新合同还没有开始收税，要到下个回合的r阶段才实际收税引起民变。
        self._process_civil_unrest()
        self._process_triumphs()
        self._process_budgeted_auctions()

        """

        # 5. 对包税合同竞标
        for contract in new_contracts:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._auto_bid_for_contract(contract)

        # 6. 对工程合同竞标
        for contract in new_contracts:
            if contract.contract_type == ContractType.PUBLIC_WORKS:
                self._auto_bid_for_works(contract)
        """

        # 7. 显示待授予合同
        self._display_contracts(terms)

        # 8. 显示激活的战争威胁
        active_wars = self.state.get_war_system().get_active_wars() if self.state.get_war_system() else []
        if active_wars:
            print(f"\n   ⚔️ 活跃战争：{len(active_wars)}场（使用 'wars' 查看详情）")

        # 8. 提示可用命令
        print(f"\n   💡 Use 'persuade <id>' to recruit figures into your faction.")
        print(f"   💡 Use 'contracts' to view pending contracts.")

        self.state.mark_phase_executed("forum")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _process_triumphs(self):
        """处理所有待凯旋的战争"""
        ws = self.state.get_war_system()
        if not ws:
            return

        # 获取所有已解决且有士兵份额的战争（可从 _war_discard 或单独列表获取）
        # 这里假设 ws._war_discard 中存放已解决的战争，且可能有士兵份额
        # 更稳妥的方式：遍历所有战争（包括活跃和已解决），但需避免重复处理
        # 我们可以在 War 中增加一个标记 _triumph_processed，但简化起见，我们只处理刚解决的战争，
        # 但需要持久化。由于战争解决后即移入弃牌堆，我们可以遍历弃牌堆中士兵份额 >0 的战争。
        # 但弃牌堆可能累积，为避免重复处理，应在处理后将 soldier_share 清零。
        for war in ws._war_discard:
            if war.soldier_share > 0 and war.status == WarStatus.RESOLVED:
                commander = self.state.get_member(war.commander_id)
                if not commander or commander.is_dead:
                    war.set_soldier_share(0)
                    continue

                if self.triumph_decider.decide_triumph(war, commander, self.state):
                    duration = self.state.config.get("combat_rules.triumph_veteran_duration", 5)
                    per_turn = war.soldier_share // duration
                    if per_turn > 0:
                        commander.add_temp_influence_task(per_turn, duration)
                        war.set_triumph_approved(True)  # <-- 新增：标记凯旋已批准
                        print(f"      🏆 {commander.name} 凯旋！获得 {per_turn}×{duration} 临时影响力")
                        self.state.log_event(
                            f"凯旋批准：{commander.name} 获得 {war.soldier_share} 士兵份额，分 {duration} 回合")
                    else:
                        print(f"      ⚠️ {commander.name} 凯旋：士兵份额 {war.soldier_share} 过少，无法分配")
                else:
                    print(f"      ⏳ {commander.name} 的凯旋被元老院否决")
                # 无论批准与否，清零士兵份额，避免重复处理
                war.set_soldier_share(0)

    def _process_budgeted_auctions(self):
        """对已预算的合同进行竞标"""
        budgeted = [c for c in self.state.contracts if c.status == ContractStatus.BUDGETED]
        if not budgeted:
            return

        print(f"\n   🔔 对已预算合同进行竞标：")
        for contract in budgeted:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._auto_bid_for_contract(contract)
            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                self._auto_bid_for_works(contract)

    def _process_civil_unrest(self):
        """处理民变触发与自动升级，并打印详细信息"""
        if not self.state.config.get("enable_threats", True):
            return
        print(f"\n   📊 行省民变状态：")
        base_tax_rate = self.state.get_economic_rule("province_tax_rate", 0.1)
        # 从配置读取意大利触发阈值，键名应与配置文件一致
        italy_unrest_trigger = self.state.config.get("economic_rules.italy_unrest_trigger_turns", 3)
        provinces = self.state.get_all_provinces()
        if not provinces:
            return

        # 收集活跃的包税合同（按行省分组）
        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE and c.contract_type == ContractType.TAX_FARMING]
        province_contracts = {}
        for contract in active_contracts:
            pid = contract.province_id
            if pid == 0:  # 意大利无包税合同
                continue
            province_contracts.setdefault(pid, []).append(contract)

        any_change = False

        # 处理意大利本土的民变（ID=0）
        italy = self.state.get_province(0)
        if italy:
            old_grievance = italy.grievance
            if old_grievance == 0:
                # 增加未分地回合计数
                italy._turns_since_last_land_distribution += 1
                # 使用 italy_unrest_trigger 变量，而不是未定义的 italy_unrest_threshold
                if italy._turns_since_last_land_distribution >= italy_unrest_trigger:
                    italy.set_grievance(1)
                    print(f"      ⚠️ 意大利本土因长期未分地，民怨升至 1 级")
                    any_change = True
            elif 0 < old_grievance < 3:
                # 自动升级
                italy.set_grievance(old_grievance + 1)
                print(f"      ⚠️ 意大利本土 民怨升级至 {italy.grievance} 级")
                if italy.grievance == 3:
                    print(f"         意大利本土爆发平民起义！政府倒台，游戏结束。")
                    # 触发游戏结束（简单退出）
                    import sys
                    sys.exit(0)
                any_change = True
            # 如果已经是3，不再处理

        # 处理行省的自动升级和合同触发
        for province in provinces:
            if province.province_id == 0:
                continue
            # 自动升级
            if 0 < province.grievance < 3:
                old = province.grievance
                province.set_grievance(old + 1)
                print(f"      ⚠️ 行省 {province.name} 民怨升级至 {province.grievance} 级")
                if province.grievance == 3:
                    print(f"         行省 {province.name} 爆发平民起义！")
                any_change = True

            # 合同触发的民怨
            contracts = province_contracts.get(province.province_id, [])
            if contracts:
                for contract in contracts:
                    tax_rate = getattr(contract, 'tax_rate', 0.0)
                    if tax_rate > base_tax_rate:
                        if province.grievance < 1:
                            province.set_grievance(1)
                            print(
                                f"      🔔 行省 {province.name} 因包税合同税率 {tax_rate * 100:.0f}% > {base_tax_rate * 100:.0f}%，民怨升至 1 级")
                            any_change = True
                        else:
                            print(
                                f"      📌 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}%，当前民怨 {province.grievance} 级")
                    else:
                        print(
                            f"      ✅ 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}% 在允许范围内，民怨 {province.grievance} 级")
            else:
                if province.grievance > 0:
                    print(f"      ℹ️ 行省 {province.name} 当前民怨 {province.grievance} 级")
                    any_change = True

        if not any_change:
            # 检查是否有任何行省有合同或民怨
            has_info = False
            for province in provinces:
                if province.province_id == 0:
                    continue
                if province.grievance > 0 or province_contracts.get(province.province_id):
                    has_info = True
                    break
            if not has_info:
                print(f"      所有行省安居乐业，无民变威胁。")

    def _process_war_threats(self):
        """处理战争威胁触发和自动升级"""
        ws = self.state.get_war_system()
        if not ws:
            return

        # 检查新威胁触发
        ws.check_triggers(self.state.turn.year)

        # 自动升级
        events = ws.escalate_threats()
        for event in events:
            print(f"   {event}")

    def _process_recruitment(self):
        member_limit = self.state.config.get("economic_rules.faction_member_limit", 6)
        factions = list(self.state.factions.values())
        if not factions:
            return
        available_figures = self.state.curia.get_all_available()
        if not available_figures:
            return

        # 记录每个派系已承诺的总出价
        committed = {faction.id: 0 for faction in factions}

        all_bids = {}
        for faction in factions:
            vacancies = faction.get_vacancies(self.state, member_limit)
            if vacancies <= 0:
                continue
            bids = self.recruitment_decider.decide_bids(faction, available_figures, vacancies, self.state)
            if not bids:
                continue
            for fig_id, amount in bids.items():
                # 检查该派系当前已承诺总额 + 本次出价是否超过金库
                if committed[faction.id] + amount > faction.treasury:
                    continue
                if fig_id not in all_bids:
                    all_bids[fig_id] = {}
                all_bids[fig_id][faction.id] = amount
                committed[faction.id] += amount  # 累加承诺

        if not all_bids:
            print(f"\n   📭 No recruitment bids this year.")
            return

        # 打印出价情况
        print(f"\n   📢 招募出价情况：")
        for fig_id, faction_bids in all_bids.items():
            figure = self.state.get_member(fig_id)
            if not figure:
                continue
            bid_str = ", ".join([f"{self.state.get_faction(fid).name}:{amt}" for fid, amt in faction_bids.items()])
            print(f"      {figure.get_formal_name()} 收到出价：{bid_str}")

        recruited_count = 0
        for fig_id, faction_bids in all_bids.items():
            figure = self.state.get_member(fig_id)
            if not figure or figure not in self.state.curia.get_all_available():
                continue

            max_amount = max(faction_bids.values())
            top_factions = [fid for fid, amt in faction_bids.items() if amt == max_amount]

            if len(top_factions) > 1:
                winner_fid = random.choice(top_factions)
            else:
                winner_fid = top_factions[0]

            winner_faction = self.state.get_faction(winner_fid)

            # 扣款前检查：确保当前金库仍足够（理论上因为承诺控制，应该足够，但以防万一）
            if winner_faction.treasury < max_amount:
                print(f"      ⚠️ {winner_faction.name} 金库不足 {max_amount}，无法招募 {figure.get_formal_name()}")
                continue

            winner_faction.treasury -= max_amount
            figure.wealth += max_amount

            self.state.curia.remove_figure(fig_id)
            figure.faction_id = winner_fid
            winner_faction.member_ids.append(fig_id)
            figure.abandoned_by = None

            recruited_count += 1
            print(f"      ✅ {figure.get_formal_name()} 加入 {winner_faction.name}，成交价 {max_amount}")

        if recruited_count > 0:
            print(f"   🎉 {recruited_count} 名人物被招募")
        else:
            print(f"   📭 No successful recruitments.")

    def _process_retirements(self):
        """处理各派系抛弃人物"""
        # 从配置读取是否启用淘汰（可先硬编码启用，后续配置化）
        count = 0
        for faction in self.state.factions.values():
            member_id = self.retirement_decider.decide_whom_to_retire(faction)
            if member_id is None:
                continue
            figure = self.state.get_member(member_id)
            if not figure:
                continue
            # 从派系移除
            faction.remove_member(member_id)
            figure.abandoned_by = faction.id    # 先保存faction.id
            figure.faction_id = None            #再清空faction.id
            figure.is_available = True  # 标记为可招募
            # 放入 Curia
            self.state.curia.add_figure(figure)
            count += 1
            print(f"      {faction.name} 抛弃了 {figure.get_formal_name()}")
        if count > 0:
            print(f"      🗑️ 共 {count} 名人物被抛弃，现已加入广场")

    def _generate_new_figures(self) -> List[Figure]:
        """生成新人物"""
        new_figures = []
        # 从 forum_rules 读取配置
        forum_rules = self.state.config.get("forum_rules", {})
        count = forum_rules.get("new_figures_count", 3)
        probs = forum_rules.get("class_probabilities", {})
        nobile_prob = probs.get("nobile", 0.1)
        eques_prob = probs.get("eques", 0.25)
        # 平民概率自动补足，确保总和为1
        pleb_prob = 1 - nobile_prob - eques_prob
        if pleb_prob < 0:
            pleb_prob = 0.65  # 容错处理，但最好确保配置总和为1

        next_id = max((mid for mid in self.state.members.keys()), default=0) + 1

        for i in range(count):
            figure_id = next_id + i
            tier_roll = random.random()
            if tier_roll < nobile_prob:
                figure = Figure.create_nobile(figure_id, None, age=random.randint(30, 50))
            elif tier_roll < nobile_prob + eques_prob:
                figure = Figure.create_eques(figure_id, None, age=random.randint(25, 40))
            else:
                figure = Figure.create_plebeian(figure_id, None, age=random.randint(20, 35))

            self.state.add_member(figure)
            self.state.curia.add_figure(figure)
            new_figures.append(figure)

        return new_figures

    def _display_curia(self, terms):
        curia = self.state.curia
        if curia.is_empty():
            print(f"\n   📭 The {terms.assembly} is empty.")
            return

        print(f"\n   🏛️  Figures in {terms.assembly}:")
        for tier in ["nobile", "eques", "plebeian"]:
            figures = curia.get_available_by_tier(tier)
            if not figures:
                continue
            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(tier, "❓")
            print(f"\n      {tier_emoji} {tier.upper()} ({len(figures)}):")
            for fig in figures:
                influence_str = f"影响力 {fig.influence} " if fig.influence > 0 else ""
                wealth_str = f"财富 {fig.wealth} " if fig.wealth > 0 else ""
                pop_str = f"人气 {fig.popularity} " if fig.popularity > 0 else ""
                family_info = f" 家族:{fig.family}" if fig.family else ""
                print(f"         ID:{fig.id} {fig.get_formal_name()}")
                print(f"            [{influence_str}{wealth_str}{pop_str}]{family_info}")

    def _generate_contracts(self):
        """生成包税权合同和公共工程合同，返回合同列表（不竞标）"""
        from src.core.entities.contract import ContractType, ContractStatus

        contracts = []
        config = self.state.config
        land_price = config.get("economic_rules.land_price_per_unit", 10)
        private_income_rate = config.get("economic_rules.private_land_income_rate", 0.05)
        province_tax_rate = config.get("economic_rules.province_tax_rate", 0.1)
        auction_ratio = config.get("economic_rules.tax_auction_ratio", 0.8)

        # ========== 1. 处理续约合同 ==========
        for contract in self.state.contracts:
            # 包税合同：剩余1年时生成新待决合同
            if contract.contract_type == ContractType.TAX_FARMING and contract.status == ContractStatus.ACTIVE:
                if contract.remaining_years == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.TAX_FARMING
                                   and c.status == ContractStatus.PENDING)
                    if not existing:
                        public_land = province.land_public
                        if public_land == 0:
                            continue
                        land_value = public_land * land_price
                        base_income = int(land_value * private_income_rate)
                        base_tax = int(base_income * province_tax_rate)
                        base_cost = int(base_tax * auction_ratio)

                        new_contract = self.state.create_contract(
                            ContractType.TAX_FARMING,
                            province.province_id,
                            base_cost,
                            self.state.turn.turn_number
                        )
                        year = self.state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract.name = f"{province.name}包税权 ({year_display})"
                        new_contract.description = f"{province.name}行省税收承包权（续约）"
                        new_contract.expected_profit = base_tax - base_cost
                        new_contract.duration_years = config.get("economic_rules.tax_contract_duration", 5)
                        contracts.append(new_contract)
                        print(f"      📊 续约包税权合同生成：{province.name} 底价 {base_cost}")

            # 工程合同：竣工后质保剩余1年时生成新待决合同
            elif contract.contract_type == ContractType.PUBLIC_WORKS and contract.status == ContractStatus.COMPLETED:
                if contract.warranty_remaining == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.PUBLIC_WORKS
                                   and c.status == ContractStatus.PENDING)
                    if not existing:
                        public_land = province.land_public
                        if public_land == 0:
                            continue
                        land_value = public_land * land_price
                        infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)
                        budget_margin = config.get("economic_rules.project_budget_margin", 0.2)
                        infra_cost = int(land_value * infra_rate)
                        budget = int(infra_cost * (1 + budget_margin))

                        year = self.state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract = self.state.create_contract(
                            ContractType.PUBLIC_WORKS,
                            province.province_id,
                            budget,
                            self.state.turn.turn_number
                        )
                        new_contract.name = f"{province.name}工程 ({year_display})"
                        new_contract.description = f"{province.name}公共建设项目（续约）"
                        new_contract._original_budget = budget
                        contracts.append(new_contract)
                        print(f"      🏗️ 续约工程合同生成：{province.name} 预算 {budget}")

        # ========== 2. 处理全新合同 ==========
        for province in self.state.get_all_provinces():
            # 包税合同（意大利不生成）
            if province.province_id != 0:
                has_tax_active = any(c for c in self.state.contracts
                                     if c.province_id == province.province_id
                                     and c.contract_type == ContractType.TAX_FARMING
                                     and c.status in (
                                     ContractStatus.ACTIVE, ContractStatus.PENDING, ContractStatus.BUDGETED))
                if not has_tax_active and province.land_public > 0:
                    land_value = province.land_public * land_price
                    base_income = int(land_value * private_income_rate)
                    base_tax = int(base_income * province_tax_rate)
                    base_cost = int(base_tax * auction_ratio)

                    contract = self.state.create_contract(
                        ContractType.TAX_FARMING,
                        province.province_id,
                        base_cost,
                        self.state.turn.turn_number
                    )
                    year = self.state.turn.year
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                    contract.name = f"{province.name}包税权 ({year_display})"
                    contract.description = f"{province.name}行省税收承包权"
                    contract.expected_profit = base_tax - base_cost
                    contract.duration_years = config.get("economic_rules.tax_contract_duration", 5)
                    contracts.append(contract)
                    print(f"      📊 新包税权合同生成：{province.name} 底价 {base_cost}")

            # 工程合同（所有行省包括意大利）
            has_works = any(c for c in self.state.contracts
                            if c.province_id == province.province_id
                            and c.contract_type == ContractType.PUBLIC_WORKS
                            and c.status not in (ContractStatus.EXPIRED, ContractStatus.COMPLETED))
            if not has_works and province.land_public > 0:
                land_value = province.land_public * land_price
                infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)
                budget_margin = config.get("economic_rules.project_budget_margin", 0.2)
                infra_cost = int(land_value * infra_rate)
                budget = int(infra_cost * (1 + budget_margin))

                year = self.state.turn.year
                year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                contract = self.state.create_contract(
                    ContractType.PUBLIC_WORKS,
                    province.province_id,
                    budget,
                    self.state.turn.turn_number
                )
                contract.name = f"{province.name}工程 ({year_display})"
                contract.description = f"{province.name}公共建设项目"
                contract._original_budget = budget
                contracts.append(contract)
                print(f"      🏗️ 新公共工程合同生成：{province.name} 预算 {budget}")

        return contracts

    def _auto_bid_for_contract(self, contract):
        """为单个包税合同自动竞标并揭标"""
        if contract.contract_type != ContractType.TAX_FARMING:
            return

        config = self.state.config
        min_inc = config.get("economic_rules.tax_bid_increment_min", 0.05)
        max_inc = config.get("economic_rules.tax_bid_increment_max", 0.20)

        factions = list(self.state.factions.values())
        if not factions:
            return

        print(f"\n      🔔 开始竞标 {contract.name} 底价 {contract.base_cost}")
        for faction in factions:
            equites = [m for m in faction.get_members(self.state)
                       if m.class_tier == ClassTier.EQUES and not m.is_dead]
            if not equites:
                continue
            knight = max(equites, key=lambda k: k.wealth)

            r = random.uniform(min_inc, max_inc)
            amount = int(contract.base_cost * (1 + r))

            if knight.wealth < amount:
                print(
                    f"         {faction.name} 的 {knight.get_formal_name()} 财富不足 {knight.wealth} < {amount}，无法出价")
                continue
            self.state.place_bid(contract.id, knight.id, amount, tax_rate=r)
            print(f"         {faction.name} 的 {knight.get_formal_name()} 出价 {amount} (加价 {r * 100:.0f}%)")

        self.state.resolve_auction(contract.id)

        if contract.status == ContractStatus.ACTIVE and contract.winning_bid:
            winner = self.state.get_member(contract.winning_bid["bidder_id"])
            winner_name = winner.get_formal_name() if winner else "未知"
            actual_inc = (contract.winning_bid['amount'] - contract.base_cost) / contract.base_cost * 100
            print(f"      ✅ 中标者: {winner_name}，中标价 {contract.winning_bid['amount']}，加价 {actual_inc:.0f}%")

            # ===== 清理该行省所有已过期的包税权合同 =====
            province_id = contract.province_id
            extended_contracts = [c for c in self.state.contracts
                                  if c.province_id == province_id
                                  and c.contract_type == ContractType.TAX_FARMING
                                  and c.id != contract.id
                                  and c.status == ContractStatus.ACTIVE
                                  and c.is_extended]
            for ec in extended_contracts:
                if ec.id in self.state._contracts_dict:
                    del self.state._contracts_dict[ec.id]
                    province = self.state.get_province(province_id)
                    if province and province.tax_contract_id == ec.id:
                        province.unbind_tax_contract()
                    print(f"         🗑️ 清理延期包税合同: {ec.name}")
        else:
            print(f"      ❌ 流拍")

    def _auto_bid_for_works(self, contract):
        """为单个工程合同自动竞标并揭标"""
        if contract.contract_type != ContractType.PUBLIC_WORKS:
            return

        config = self.state.config
        X = config.get("economic_rules.project_theoretical_construction", 5)
        N = config.get("economic_rules.project_theoretical_warranty", 10)
        min_discount = config.get("economic_rules.project_bid_discount_min", 0.05)
        max_discount = config.get("economic_rules.project_bid_discount_max", 0.20)
        land_price = config.get("economic_rules.land_price_per_unit", 10)
        infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)

        # 获取行省信息，用于计算实际成本
        province = self.state.get_province(contract.province_id)
        if not province:
            return
        land_value = province.land_public * land_price
        infra_cost = int(land_value * infra_rate)

        factions = list(self.state.factions.values())
        if not factions:
            return

        print(f"\n      🔔 开始竞标 {contract.name} 预算 {contract._original_budget}")
        original_budget = contract._original_budget

        for faction in factions:
            knights = [m for m in faction.get_members(self.state)
                       if m.class_tier == ClassTier.EQUES and not m.is_dead]
            if not knights:
                continue
            knight = max(knights, key=lambda k: k.wealth)

            r = random.uniform(min_discount, max_discount)
            bid_amount = int(original_budget * (1 - r))
            construction = int(X * (1 + r) + 0.5)
            if construction < 1:
                construction = 1
            warranty = int(N * (1 - r) + 0.5)
            if warranty < 0:
                warranty = 0
            annual_income = bid_amount // construction

            # 计算年支出
            actual_cost = int(infra_cost * (1 - r))
            annual_cost = actual_cost // construction

            self.state.place_bid(
                contract.id,
                knight.id,
                bid_amount,
                r=r,
                original_budget=original_budget,
                construction=construction,
                warranty=warranty,
                annual_income=annual_income,
                annual_cost=annual_cost
            )
            print(f"         {faction.name} 的 {knight.get_formal_name()} 出价 {bid_amount} (降价 {r * 100:.0f}%)")

        self.state.resolve_auction(contract.id)

        # 打印中标结果
        if contract.status == ContractStatus.ACTIVE and contract.winning_bid:
            winner = self.state.get_member(contract.winning_bid["bidder_id"])
            winner_name = winner.get_formal_name() if winner else "未知"
            r = contract.winning_bid.get("r", 0)
            discount_pct = r * 100
            print(f"      ✅ 中标者: {winner_name}，中标价 {contract.winning_bid['amount']}，降价 {discount_pct:.0f}%")
        else:
            print(f"      ❌ 流拍")

    def _display_contracts(self, terms):
        """显示待授予合同"""
        pending = [c for c in self.state.contracts if c.status.value == "pending"]
        if not pending:
            print(f"\n   📭 No pending contracts.")
            return

        print(f"\n   📋 Pending Contracts (等待元老院预算表决):")
        tax_contracts = [c for c in pending if c.contract_type == ContractType.TAX_FARMING]
        works_contracts = [c for c in pending if c.contract_type == ContractType.PUBLIC_WORKS]

        if tax_contracts:
            print(f"\n      📊 Tax Farming:")
            for c in tax_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预付:{c.base_cost} 年收益:{c.expected_profit} 期限:{c.duration_years}年")


        if works_contracts:
            print(f"\n      🏗️ Public Works:")
            for c in works_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预算:{c.base_cost} 预期利润:{c.expected_profit}")
