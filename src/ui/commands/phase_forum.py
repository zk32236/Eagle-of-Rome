# src/ui/commands/phase_forum.py
"""
广场阶段命令 - 优化打印布局，分区块显示信息
"""

import random
import logging
from typing import List, TYPE_CHECKING, Optional
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
from src.core.deciders.impl.auto_land_trade_decider import AutoLandTradeDecider
from src.core.deciders.land_trade_decider import LandTradeDecider
from src.core.service.land_trading_service import LandTradingService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase)"

    def __init__(self, state: "GameState",
                 retirement_decider=None,
                 recruitment_decider=None,
                 triumph_decider=None,
                 land_trade_decider: Optional[LandTradeDecider] = None):
        super().__init__(state)
        self.retirement_decider = retirement_decider or AutoRetirementDecider(state)
        self.recruitment_decider = recruitment_decider or AutoRecruitmentDecider()
        self.triumph_decider = triumph_decider or AutoTriumphDecider()
        self.land_trade_decider = land_trade_decider or AutoLandTradeDecider()

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("revenue"):
            print("⚠️ 必须先执行税收阶段 (revenue)")
            return False

        if self.state.is_phase_executed("forum"):
            print("⚠️ 广场阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_forum} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # ========== 1. 安民告示 ==========
        self._print_notice_board()

        # ========== 2. 人才市场 ==========
        self._print_labor_market()

        # ========== 3. 合同拍卖 ==========
        self._print_contract_auction()

        # ========== 4. 土地交易 ==========
        self._print_land_deals()

        self.state.mark_phase_executed("forum")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ----------------------------------------------------------------------
    # 区块打印方法
    # ----------------------------------------------------------------------

    def _print_notice_board(self):
        """安民告示：战争威胁、活跃战争、民变、凯旋"""
        print("\n\t====================== 安民告示 ====================")

        # 战争威胁
        ws = self.state.get_war_system()
        if ws:
            ws.check_triggers(self.state.turn.year)
            events = ws.escalate_threats()
            for event in events:
                print(f"   {event}")

        # 活跃战争
        active_wars = ws.get_active_wars() if ws else []
        if active_wars:
            print(f"   ⚔️ 活跃战争：{len(active_wars)}场")
            for war in active_wars:
                print(f"\t\t{war.name}")
        else:
            print("   ⚔️ 当前无活跃战争")

        # 行省民变状态
        self._print_civil_unrest()

        # 凯旋审批
        self._print_triumphs()

    def _print_labor_market(self):
        """人才市场：抛弃人物、新人物、招募"""
        print("\n\t====================== 人才市场 ====================")

        # 抛弃人物
        retired_count = self._process_retirements()
        if retired_count > 0:
            print(f"   📢 {retired_count} figure(s) left their factions in Rome:")
            # 具体打印已在 _process_retirements 中完成，此处无需重复
        else:
            print("   📢 无人物被抛弃")

        # 新人物
        new_figures = self._generate_new_figures()
        if new_figures:
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the Senate:")
            for fig in new_figures:
                tier_emoji = {
                    ClassTier.NOBILE: "🏛️",
                    ClassTier.EQUES: "💰",
                    ClassTier.PLEBEIAN: "👤"
                }.get(fig.class_tier, "❓")
                tier_name = fig.class_tier.value
                print(f"      {tier_emoji} {fig.get_formal_name()} ({tier_name})"
                      f"(军略 {fig.martial}, 智略 {fig.intelligence}, 魅力 {fig.charisma}, 热诚 {fig.zeal})")
        else:
            print("   📭 无新人物出现")

        # 广场现有总人数
        total_in_curia = len(self.state.curia.get_all_available())
        print(f"\n   📢 共 {total_in_curia} 名人物在罗马广场可供招募！")

        # 招募过程
        self._process_recruitment()

    def _print_contract_auction(self):
        """合同拍卖：待决合同、预算合同竞标"""
        print("\n\t====================== 合同拍卖 ====================")

        # 生成新合同（但不竞标）
        new_contracts = self._generate_contracts()
        if new_contracts:
            for contract in new_contracts:
                type_emoji = "📊" if contract.contract_type == ContractType.TAX_FARMING else "🏗️"
                print(f"      {type_emoji} 新{contract.name} 生成")

        # 待决合同
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if pending:
            print("\n   📋 Pending Contracts (等待元老院预算表决):")
            tax_contracts = [c for c in pending if c.contract_type == ContractType.TAX_FARMING]
            works_contracts = [c for c in pending if c.contract_type == ContractType.PUBLIC_WORKS]
            if tax_contracts:
                print("\n      📊 Tax Farming:")
                for c in tax_contracts:
                    print(f"         ID:{c.id} {c.name}\t预付:{c.base_cost} 年收益:{c.expected_profit} 期限:{c.duration_years}年")
            if works_contracts:
                print("\n      🏗️ Public Works:")
                for c in works_contracts:
                    print(f"         ID:{c.id} {c.name}\t预算:{c.base_cost} 预期利润:{c.expected_profit}")
        else:
            print("\n   📭 无待决合同")

        # 已预算合同竞标
        budgeted = [c for c in self.state.contracts if c.status == ContractStatus.BUDGETED]
        if budgeted:
            print("\n   📜 对已预算合同进行竞标：")
            for contract in budgeted:
                if contract.contract_type == ContractType.TAX_FARMING:
                    self._auto_bid_for_contract(contract)
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    self._auto_bid_for_works(contract)
        else:
            print("\n   📭 没有待竞标的预算合同。")

    def _print_land_deals(self):
        """土地交易：土地法案执行、自动土地交易"""
        print("\n\t====================== 土地交易 ====================")

        # 执行待决的土地法案
        self._execute_pending_land_acts()

        # 自动土地交易
        self._process_land_trades()

    # ----------------------------------------------------------------------
    # 原有功能方法（修改打印部分以适配新布局）
    # ----------------------------------------------------------------------

    def _print_civil_unrest(self):
        """处理民变触发与自动升级，并打印详细信息（不带DEBUG）"""
        if not self.state.config.get("enable_threats", True):
            return
        base_tax_rate = self.state.get_economic_rule("province_tax_rate", 0.1)
        italy_unrest_trigger = self.state.config.get("economic_rules.italy_unrest_trigger_turns", 3)
        provinces = self.state.get_all_provinces()
        if not provinces:
            return

        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE and c.contract_type == ContractType.TAX_FARMING]
        province_contracts = {}
        for contract in active_contracts:
            pid = contract.province_id
            if pid == 0:
                continue
            province_contracts.setdefault(pid, []).append(contract)

        any_change = False
        print("\n   📊 行省民变状态：")

        # 意大利本土
        italy = self.state.get_province(0)
        if italy:
            old_grievance = italy.grievance
            if old_grievance == 0:
                italy._turns_since_last_land_distribution += 1
                if italy._turns_since_last_land_distribution >= italy_unrest_trigger:
                    italy.set_grievance(1)
                    print(f"      ⚠️ 意大利本土因长期未分地，民怨升至 1 级")
                    any_change = True
            elif 0 < old_grievance < 3:
                italy.set_grievance(old_grievance + 1)
                print(f"      ⚠️ 意大利本土 民怨升级至 {italy.grievance} 级")
                if italy.grievance == 3:
                    print(f"         意大利本土爆发平民起义！政府面临倒台，马上行动！")
                any_change = True

        # 行省
        for province in provinces:
            if province.province_id == 0:
                continue
            if 0 < province.grievance < 3:
                old = province.grievance
                province.set_grievance(old + 1)
                print(f"      ⚠️ 行省 {province.name} 民怨升级至 {province.grievance} 级")
                if province.grievance == 3:
                    print(f"         行省 {province.name} 爆发平民起义！")
                any_change = True

            contracts = province_contracts.get(province.province_id, [])
            if contracts:
                for contract in contracts:
                    tax_rate = getattr(contract, 'tax_rate', 0.0)
                    if tax_rate > base_tax_rate:
                        if province.grievance < 1:
                            province.set_grievance(1)
                            print(f"      🔔 行省 {province.name} 因包税合同税率 {tax_rate * 100:.0f}% > {base_tax_rate * 100:.0f}%，民怨升至 1 级")
                            any_change = True
                        else:
                            print(f"      📌 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}%，当前民怨 {province.grievance} 级")
                    else:
                        print(f"      ✅ 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}% 在允许范围内，民怨 {province.grievance} 级")
            else:
                if province.grievance > 0:
                    print(f"      ℹ️ 行省 {province.name} 当前民怨 {province.grievance} 级")
                    any_change = True

        if not any_change:
            print(f"      所有行省安居乐业，无民变威胁。")

    def _print_triumphs(self):
        """处理所有待凯旋的战争（无调试输出）"""
        ws = self.state.get_war_system()
        if not ws:
            return

        for war in ws._war_discard:
            if war.soldier_share > 0 and war.status == WarStatus.RESOLVED:
                commander_id = war.triumph_commander_id or war.commander_id
                commander = self.state.get_member(commander_id) if commander_id else None
                if not commander or commander.is_dead:
                    war.set_soldier_share(0)
                    continue

                if self.triumph_decider.decide_triumph(war, commander, self.state):
                    duration = self.state.config.get("combat_rules.triumph_veteran_duration", 5)
                    per_turn = war.soldier_share // duration
                    if per_turn > 0:
                        commander.add_temp_influence_task(per_turn, duration)
                        war.set_triumph_approved(True)
                        print(f"   🏆 元老院决定授予 {commander.name} 凯旋！未来几年他将获得士兵的拥戴！")
                        self.state.log_event(f"凯旋批准：{commander.name} 获得 {war.soldier_share} 士兵份额，分 {duration} 回合")
                else:
                    print(f"   ⏳ {commander.name} 的凯旋被元老院否决")
                war.set_soldier_share(0)

    def _process_retirements(self) -> int:
        """处理各派系抛弃人物，打印抛弃信息（带能力值），返回抛弃人数"""
        count = 0
        for faction in self.state.factions.values():
            member_id = self.retirement_decider.decide_whom_to_retire(faction)
            if member_id is None:
                continue
            figure = self.state.get_member(member_id)
            if not figure:
                continue
            faction.remove_member(member_id)
            figure.abandoned_by = faction.id
            figure.faction_id = None
            figure.is_available = True
            self.state.curia.add_figure(figure)
            count += 1
            print(f"      {faction.name} 抛弃了 {figure.get_formal_name()} "
                  f"(军略 {figure.martial}, 智略 {figure.intelligence}, 魅力 {figure.charisma}, 热诚 {figure.zeal})")
        if count > 0:
            print(f"      🗑️ 共 {count} 名人物被抛弃，现已加入广场")
        return count

    def _generate_new_figures(self) -> List[Figure]:
        """生成新人物，返回新人物列表（打印带能力值）"""
        new_figures = []
        forum_rules = self.state.config.get("forum_rules", {})
        count = forum_rules.get("new_figures_count", 3)
        probs = forum_rules.get("class_probabilities", {})
        nobile_prob = probs.get("nobile", 0.1)
        eques_prob = probs.get("eques", 0.25)
        pleb_prob = 1 - nobile_prob - eques_prob
        if pleb_prob < 0:
            pleb_prob = 0.65

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

    def _process_recruitment(self):
        """招募处理（打印出价和结果）"""
        member_limit = self.state.config.get("economic_rules.faction_member_limit", 6)
        factions = list(self.state.factions.values())
        if not factions:
            return
        available_figures = self.state.curia.get_all_available()
        if not available_figures:
            return

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
                if committed[faction.id] + amount > faction.treasury:
                    continue
                if fig_id not in all_bids:
                    all_bids[fig_id] = {}
                all_bids[fig_id][faction.id] = amount
                committed[faction.id] += amount

        if not all_bids:
            print(f"\n   📭 No recruitment bids this year.")
            return

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

    def _process_war_threats(self):
        """处理战争威胁触发和自动升级（已在安民告示中调用，此处保留空方法避免错误）"""
        pass

    def _generate_contracts(self) -> List[Contract]:
        """生成包税权合同和公共工程合同，返回合同列表（不竞标）"""
        contracts = []
        config = self.state.config
        land_price = config.get("economic_rules.land_price_per_unit", 10)
        private_income_rate = config.get("economic_rules.private_land_income_rate", 0.05)
        province_tax_rate = config.get("economic_rules.province_tax_rate", 0.1)
        auction_ratio = config.get("economic_rules.tax_auction_ratio", 0.8)

        # 续约合同
        for contract in self.state.contracts:
            if contract.contract_type == ContractType.TAX_FARMING and contract.status == ContractStatus.ACTIVE:
                if contract.remaining_years == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.TAX_FARMING
                                   and c.status == ContractStatus.PENDING)
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
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

            elif contract.contract_type == ContractType.PUBLIC_WORKS and contract.status == ContractStatus.COMPLETED:
                if contract.warranty_remaining == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.PUBLIC_WORKS
                                   and c.status == ContractStatus.PENDING)
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
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

        # 全新合同
        for province in self.state.get_all_provinces():
            if province.province_id != 0:
                has_tax_active = any(c for c in self.state.contracts
                                     if c.province_id == province.province_id
                                     and c.contract_type == ContractType.TAX_FARMING
                                     and c.status in (ContractStatus.ACTIVE, ContractStatus.PENDING, ContractStatus.BUDGETED))
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
            # ===== 新增日志 =====
            self.state.log_event(
                f"包税合同中标: {contract.name} 中标者 {winner_name} 价格 {contract.winning_bid['amount']}",
                extra={
                    "type": "tax_contract_award",
                    "contract_id": contract.id,
                    "winner_id": contract.winning_bid["bidder_id"],
                    "amount": contract.winning_bid['amount']
                }
            )
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

        if contract.status == ContractStatus.ACTIVE and contract.winning_bid:
            winner = self.state.get_member(contract.winning_bid["bidder_id"])
            winner_name = winner.get_formal_name() if winner else "未知"
            r = contract.winning_bid.get("r", 0)
            discount_pct = r * 100
            print(f"      ✅ 中标者: {winner_name}，中标价 {contract.winning_bid['amount']}，降价 {discount_pct:.0f}%")
            # ===== 新增日志 =====
            self.state.log_event(
                f"工程合同中标: {contract.name} 中标者 {winner_name} 价格 {contract.winning_bid['amount']}",
                extra={
                    "type": "works_contract_award",
                    "contract_id": contract.id,
                    "winner_id": contract.winning_bid["bidder_id"],
                    "amount": contract.winning_bid['amount']
                }
            )
        else:
            print(f"      ❌ 流拍")

    def _execute_pending_land_acts(self):
        """执行已通过的平民分地和贵族买地法案"""
        acts = self.state.get_pending_land_acts()
        if not acts:
            return
        print(f"\n   🏞️ 执行土地法案：")
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        for act in acts:
            if act['type'] == 'distribution':
                self._execute_land_distribution(act, land_price)
            elif act['type'] == 'sale':
                self._execute_land_sale(act, land_price)
        self.state.clear_pending_land_acts()

    def _execute_land_distribution(self, act, land_price):
        national_land = self.state.get_national_public_land()
        amount = int(national_land * act['percent'])
        if amount <= 0:
            print(f"      ⚠️ 国家公地不足，无法分配。")
            return
        self.state.add_national_public_land(-amount)
        italy = self.state.get_province(0)
        if italy:
            italy._land_private += amount
            italy._turns_since_last_land_distribution = 0
            italy.set_grievance(0)
        print(f"      ✅ 平民分地 {amount} C 土地（占国家公地 {act['percent'] * 100:.1f}%），转入意大利私地，民怨重置。")

    def _execute_land_sale(self, act, land_price):
        national_land = self.state.get_national_public_land()
        amount = int(national_land * act['percent'])
        if amount <= 0:
            print(f"      ⚠️ 国家公地不足，无法出售。")
            return
        print(f"      🏛️ 贵族买地：出售 {amount} C 国家公地。")
        nobles = [fig for fig in self.state.get_living_members() if fig.class_tier.value == "nobile"]
        nobles.sort(key=lambda f: f.influence, reverse=True)
        remaining = amount
        sold_count = 0
        for fig in nobles:
            if remaining <= 0:
                break
            max_buy = fig.wealth // land_price
            if max_buy <= 0:
                continue
            buy = random.randint(1, min(remaining, max_buy))
            cost = buy * land_price
            fig.wealth -= cost
            fig._land_private += buy
            fig.update_influence()
            remaining -= buy
            sold_count += 1
            print(f"         {fig.name} 购买 {buy} C，花费 {cost}，剩余土地 {remaining} C")
        sold = amount - remaining
        if sold > 0:
            self.state.add_national_public_land(-sold)
            # === 新增调试输出 ===
            print(f"      [DEBUG] 即将增加国库：{sold * land_price} Talents")
            self.state.add_treasury(sold * land_price)
            print(f"      [DEBUG] 增加后国库：{self.state.treasury} Talents")
            print(
                f"      共售出 {sold} C，国库 +{sold * land_price} Talents，国家公地剩余 {self.state.get_national_public_land()} C")
        else:
            print(f"      无土地售出。")

    def _process_land_trades(self):
        """处理自动土地交易"""
        trade_info = self.land_trade_decider.decide_trade(self.state)
        if not trade_info:
            return

        seller_id, buyer_id, amount = trade_info
        service = LandTradingService(self.state)
        success, msg = service.execute_trade(seller_id, buyer_id, amount)

        if success:
            print(f"\n   💱 自动土地交易执行成功：")
            for line in msg.split('\n'):
                print(f"      {line}")
            # ===== 新增日志 =====
            self.state.log_event(
                f"土地交易成功: 卖家 {seller_id} 买家 {buyer_id} 数量 {amount}",
                extra={"type": "land_trade", "seller_id": seller_id, "buyer_id": buyer_id, "amount": amount}
            )
        else:
            seller = self.state.get_member(seller_id)
            buyer = self.state.get_member(buyer_id)
            seller_name = seller.get_formal_name() if seller else "Unknown"
            buyer_name = buyer.get_formal_name() if buyer else "Unknown"
            print(f"\n   ⚠️ 自动土地交易失败：{seller_name} → {buyer_name} {msg}")
            self.state.log_event(
                f"土地交易失败: 卖家 {seller_id} 买家 {buyer_id} 数量 {amount} - {msg}",
                extra={"type": "land_trade_failure", "seller_id": seller_id, "buyer_id": buyer_id, "amount": amount}
            )