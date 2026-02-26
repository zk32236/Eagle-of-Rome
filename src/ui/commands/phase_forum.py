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
from src.core.deciders.retirement_decider import RetirementDecider

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase)"

    def __init__(self, state: "GameState", retirement_decider=None):
        super().__init__(state)
        self.retirement_decider = retirement_decider or AutoRetirementDecider(state)

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

        # 2. 显示 Curia 状态
        self._display_curia(terms)

        # 3. 生成合同（仅生成，不竞标）
        new_contracts = self._generate_contracts()

        # 4. 公告新合同
        if new_contracts:
            print(f"\n   📜 {len(new_contracts)} new contract(s) announced:")
            for c in new_contracts:
                type_name = "包税" if c.contract_type == ContractType.TAX_FARMING else "工程"
                print(f"      {type_name}: {c.name}")
        else:
            print(f"\n   📭 No new contracts.")

        # 5. 对包税合同竞标
        for contract in new_contracts:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._auto_bid_for_contract(contract)

        # 6. 对工程合同竞标
        for contract in new_contracts:
            if contract.contract_type == ContractType.PUBLIC_WORKS:
                self._auto_bid_for_works(contract)

        # 7. 显示待授予合同
        self._display_contracts(terms)

        # 8. 提示可用命令
        print(f"\n   💡 Use 'persuade <id>' to recruit figures into your faction.")
        print(f"   💡 Use 'contracts' to view pending contracts.")

        self.state.mark_phase_executed("forum")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

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
            figure.faction_id = None
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
        from src.core.entities.contract import ContractType

        contracts = []
        config = self.state.config
        land_price = config.get("economic_rules.land_price_per_unit", 10)
        private_income_rate = config.get("economic_rules.private_land_income_rate", 0.05)
        province_tax_rate = config.get("economic_rules.province_tax_rate", 0.1)
        auction_ratio = config.get("economic_rules.tax_auction_ratio", 0.8)

        # 包税合同
        for province in self.state.get_all_provinces():
            if province.province_id == 0:  # 跳过意大利
                continue
            if province.tax_contract_id is not None:
                continue
            public_land = province.land_public
            if public_land == 0:
                continue

            land_value = public_land * land_price
            base_income = int(land_value * private_income_rate)
            base_tax = int(base_income * province_tax_rate)
            base_cost = int(base_tax * auction_ratio)

            contract = self.state.create_contract(
                ContractType.TAX_FARMING,
                province.province_id,
                base_cost,
                self.state.turn.turn_number
            )
            contract.name = f"{province.name}包税权"
            contract.description = f"{province.name}行省税收承包权"
            contract.expected_profit = base_tax - base_cost
            # 从配置读取包税合同期限
            contract.duration_years = config.get("economic_rules.tax_contract_duration", 5)
            contracts.append(contract)
            print(f"      📊 包税权合同生成：{province.name} 底价 {base_cost}")

        # 公共工程合同
        infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)
        budget_margin = config.get("economic_rules.project_budget_margin", 0.2)
        for province in self.state.get_all_provinces():
            if province.project_contract_id is not None or province.has_project:
                continue
            if province.land_public == 0:
                continue
            land_value = province.land_public * land_price
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
            print(f"      🏗️ 公共工程合同生成：{province.name} 预算 {budget}")

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
                print(f"         {faction.name} 的 {knight.get_formal_name()} 财富不足 {knight.wealth} < {amount}，无法出价")
                continue
            self.state.place_bid(contract.id, knight.id, amount, tax_rate=r)
            print(f"         {faction.name} 的 {knight.get_formal_name()} 出价 {amount} (加价 {r*100:.0f}%)")

        self.state.resolve_auction(contract.id)

        if contract.status == ContractStatus.ACTIVE and contract.winning_bid:
            winner = self.state.get_member(contract.winning_bid["bidder_id"])
            winner_name = winner.get_formal_name() if winner else "未知"
            print(f"      ✅ 中标者: {winner_name}，中标价 {contract.winning_bid['amount']}，税率 {contract.tax_rate*100:.0f}%")
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
            print(f"         {faction.name} 的 {knight.get_formal_name()} 出价 {bid_amount} (降价 {r*100:.0f}%)")

        self.state.resolve_auction(contract.id)

    def _display_contracts(self, terms):
        """显示待授予合同"""
        pending = [c for c in self.state.contracts if c.status.value == "pending"]
        if not pending:
            print(f"\n   📭 No pending contracts.")
            return

        print(f"\n   📋 Pending Contracts:")
        tax_contracts = [c for c in pending if c.contract_type == ContractType.TAX_FARMING]
        works_contracts = [c for c in pending if c.contract_type == ContractType.PUBLIC_WORKS]

        if tax_contracts:
            print(f"\n      📊 Tax Farming (Senate Vote Required):")
            for c in tax_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预付:{c.base_cost} 年收益:{c.expected_profit} 期限:{c.duration_years}年")
                print(f"            💡 Senate Phase: use 'vote contract {c.id}'")

        if works_contracts:
            print(f"\n      🏗️ Public Works (Consul Assigns):")
            for c in works_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预算:{c.base_cost} 预期利润:{c.expected_profit}")
                print(f"            💡 Senate Phase: Consul uses 'assign works {c.id} <figure_id>'")