# src/ui/commands/phase_revenue.py
"""
税收阶段命令 - 处理税收、派系津贴、军团维护费和合同收益
优化打印格式：表格化显示派系资金和私地收益
"""
import logging

from typing import List, Dict, Tuple, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractStatus, ContractType
from src.ui.commands.func_status import get_progress_bar

if TYPE_CHECKING:
    from src.core.game_state import GameState


class RevenueCommand(Command):
    """税收阶段命令"""

    name = "revenue"
    aliases = ["r"]
    description = "执行税收阶段 (Revenue Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("mortality"):
            print("⚠️ 必须先执行天命阶段 (mortality)")
            return False

        if self.state.is_phase_executed("revenue"):
            print("⚠️ 税收阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_revenue} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 初始化派系抽成累计字典和津贴记录
        faction_tax_collected: Dict[str, float] = {}
        faction_stipend: Dict[str, int] = {}

        # 获取配置
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        public_income_rate = self.state.get_economic_rule("public_land_income_rate", 0.01)  # 新增
        national_tax_rate = self.state.get_economic_rule("national_public_land_tax_rate", 0.02)
        stipend = self.state.get_economic_rule("faction_stipend", 10)
        tax_rate = self.state.get_economic_rule("faction_tax_rate", 0.1)

        # 初始化派系抽成累计字典和津贴记录
        faction_tax_collected: Dict[str, float] = {}
        faction_stipend: Dict[str, int] = {}
        for faction in self.state.factions.values():
            faction_tax_collected[faction.id] = 0.0
            faction_stipend[faction.id] = stipend

        # 1. 国家公地收益（只执行一次）
        national_land = self.state.get_national_public_land()
        tax_income = int(round(national_land * land_price* public_income_rate * national_tax_rate))
        self.state.add_treasury(tax_income)
        print(f"💰 国家公地收益: \t+{tax_income} {terms.currency}")
        print(f"📊 国库现有资金: \t{self.state.treasury} {terms.currency}\n")
        self.state.log_event(...)

        # 2. 私地收益（只执行一次）
        private_data = self._collect_private_land_income(terms, faction_tax_collected, tax_rate)
        total_net_private = sum(d[2] for d in private_data)
        if total_net_private > 0:
            self.state.log_event(...)

        # 3. 合同收益结算（只执行一次）
        self._collect_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 4. 军团维护费（只执行一次） + 赔偿金处理
        ms = self.state.get_military_system()
        if ms:
            total_maintenance, _ = ms.calculate_maintenance()
            print(f"📊 军团维护费: \t{total_maintenance} {terms.currency}")
            success, msg = ms.apply_maintenance(verbose=False)

        # 5. 国家运营费扣除
        self._deduct_national_opex()

        self._settle_indemnities()

        # 5. 先更新派系国库（处理抽成和津贴）
        for faction_id, total_tax_float in faction_tax_collected.items():
            tax_int = int(round(total_tax_float))
            faction = self.state.get_faction(faction_id)
            if faction:
                faction.treasury += faction_stipend[faction_id] + tax_int
                if tax_int > 0:
                    self.state.log_event(
                        f"派系抽成: {faction.name} +{tax_int}",
                        extra={"type": "faction_tax", "faction_id": faction_id, "amount": tax_int}
                    )
                if faction_stipend[faction_id] > 0:
                    self.state.log_event(
                        f"派系津贴: {faction.name} +{faction_stipend[faction_id]}",
                        extra={"type": "faction_stipend", "faction_id": faction_id,
                               "amount": faction_stipend[faction_id]}
                    )

        # 6. 重新构建 faction_final（此时国库已更新）
        faction_final = {}
        for faction in self.state.factions.values():
            faction_final[faction.id] = {
                'stipend': faction_stipend.get(faction.id, 0),
                'tax': int(round(faction_tax_collected.get(faction.id, 0.0))),
                'final': faction.treasury
            }

        # 7. 打印派系表格（只执行一次）
        self._print_faction_table(terms, faction_final)

        # 8. 打印私地收益表格（只执行一次）
        self._print_private_land_table(private_data, terms)

        # 9. 记录国库最终余额
        self.state.log_event(...)

        self.state.mark_phase_executed("revenue")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.3 国家运营 =======

    def _deduct_national_opex(self):
        """扣除国家运营费（仅对已征服行省）"""
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("national_opex_rate", 0.003)

        provinces = self.state.get_all_provinces()
        conquered = [p for p in provinces if p.conquered]

        if not conquered:
            print("   🏛️ 无已征服行省，国家运营费为 0")
            return

        total_land = 0
        print("\n   🏛️ 国家运营费计算：")
        for p in conquered:
            total_land += p.total_land
            print(f"      行省 {p.name}: total_land={p.total_land}")

        opex_float = total_land * land_price * rate
        opex = int(opex_float)  # 向下取整

        if opex > 0:
            self.state.treasury -= opex
            print(f"      土地单价: {land_price} Talents/单位, 费率: {rate}")
            print(f"      总土地: {total_land}, 运营费 = {opex} Talents")
            print(f"      国库扣除后余额: {self.state.treasury}")

            self.state.log_event(
                f"国家运营费扣除: {opex} Talents",
                extra={
                    "type": "national_opex",
                    "amount": opex,
                    "treasury_after": self.state.treasury,
                    "total_land": total_land,
                    "land_price": land_price,
                    "rate": rate
                }
            )
        else:
            print(f"      运营费为 0，不扣除")

    # ======== MVP 0.7.1 停战议和 =======

    def _settle_indemnities(self):
        """结算所有战争赔款（正：收入，负：支出）"""
        war_system = self.state.get_war_system()
        if not war_system:
            return

        all_wars = (war_system._war_deck + war_system._war_discard +
                    war_system._active_wars + war_system._threats +
                    war_system._truce_wars)
        for war in all_wars:
            amount = war.indemnity_due
            if amount == 0:
                continue

            if amount > 0:
                # 收入
                self.state.add_treasury(amount)
                print(f"      📦 战争赔款收入: {war.name} +{amount} Talents")
                self.state.log_event(
                    f"战争赔款收入: {war.name} +{amount}",
                    extra={'type': 'indemnity_income', 'war_id': war.id, 'amount': amount}
                )
                war.set_indemnity_due(0)  # 清除赔款
            else:
                # 支出（amount为负）
                if self.state.treasury < -amount:
                    print(f"      💀 国库不足以支付战争赔款 {war.name} {-amount} Talents，共和覆灭！")
                    self.state.log_event(
                        f"国库不足支付赔款，共和覆灭",
                        extra={'type': 'game_over', 'reason': 'indemnity', 'war_id': war.id, 'amount': -amount},
                        level=logging.CRITICAL
                    )
                    # 国库不足，不清除赔款，等待下回合再次尝试
                else:
                    self.state.add_treasury(amount)
                    print(f"      💸 战争赔款支出: {war.name} {-amount} Talents")
                    self.state.log_event(
                        f"战争赔款支出: {war.name} {-amount}",
                        extra={'type': 'indemnity_expense', 'war_id': war.id, 'amount': -amount}
                    )
                    war.set_indemnity_due(0)  # 清除赔款

    # ================================= MVP 0.1-0.5 =======================================

    def _collect_private_land_income(self, terms, faction_tax_collected: Dict[str, float], tax_rate: float) -> List[
        Tuple[int, str, int, int]]:
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("private_land_income_rate", 0.05)

        data = []
        for fig in self.state.get_living_members():
            try:
                if fig.land_private <= 0:
                    continue
                income_float = fig.land_private * land_price * rate
                if income_float <= 0:
                    continue

                tax_float = income_float * tax_rate
                net_income_float = income_float - tax_float
                net_income_int = int(round(net_income_float))
                if net_income_int > 0:
                    fig.add_wealth(net_income_int)
                    if fig.faction_id and fig.faction_id in faction_tax_collected:
                        faction_tax_collected[fig.faction_id] += tax_float
                    data.append((fig.id, fig.get_formal_name(), net_income_int, fig.wealth))
            except Exception as e:
                self.state.log_exception(
                    e,
                    context=f"私地收益处理失败: 人物 {fig.id} {fig.name}",
                    extra={"figure_id": fig.id, "land_private": fig.land_private}
                )
                continue
        return data

    def _collect_contract_revenues(self, terms, faction_tax_collected: Dict[str, float], tax_rate: float):
        """处理合同收益，逐条记录，包含异常处理"""
        from src.core.entities.contract import ContractType, ContractStatus

        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE]

        for contract in active_contracts:
            try:
                if contract.contract_type == ContractType.TAX_FARMING:
                    winning_bid = contract.winning_bid
                    if not winning_bid:
                        continue
                    figure = self.state.get_member(winning_bid["bidder_id"])
                    if not figure or figure.is_dead:
                        contract.terminate()
                        province = self.state.get_province(contract.province_id)
                        if province:
                            province.unbind_tax_contract()
                        continue

                    annual_profit = contract.annual_profit
                    profit_float = float(annual_profit)
                    tax_float = profit_float * tax_rate
                    net_profit_int = int(round(profit_float - tax_float))

                    self.state.add_treasury(winning_bid["amount"])
                    figure.add_wealth(net_profit_int)
                    contract.total_collected += annual_profit

                    if figure.faction_id and figure.faction_id in faction_tax_collected:
                        faction_tax_collected[figure.faction_id] += tax_float

                    if contract.remaining_years > 0:
                        contract.remaining_years -= 1
                        if contract.remaining_years == 0:
                            contract.set_extended(True)

                    # 日志：包税合同收益
                    self.state.log_event(
                        f"包税合同收益: {figure.name} 净得 {net_profit_int}，国库 +{winning_bid['amount']}",
                        extra={
                            "type": "tax_contract_revenue",
                            "contract_id": contract.id,
                            "figure_id": figure.id,
                            "net_profit": net_profit_int,
                            "treasury_gain": winning_bid['amount']
                        }
                    )

                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    figure = self.state.get_member(contract.awarded_to)
                    if not figure or figure.is_dead:
                        contract.terminate()
                        province = self.state.get_province(contract.province_id)
                        if province:
                            province.unbind_project_contract()
                        continue

                    if contract.remaining_years > 0:
                        annual_income = contract.annual_income
                        annual_cost = contract._annual_cost
                        if contract.remaining_years == 1:
                            paid = contract.total_spent
                            total_bid = contract.base_cost
                            payment = total_bid - paid
                            cost = annual_cost
                        else:
                            payment = annual_income
                            cost = annual_cost

                        profit_float = float(payment - cost)
                        if profit_float > 0:
                            tax_float = profit_float * tax_rate
                            tax_int = int(round(tax_float))
                        else:
                            tax_float = 0.0
                            tax_int = 0

                        knight_net_profit = profit_float - tax_float
                        knight_net_gain = int(round(knight_net_profit))
                        self.state.add_treasury(-payment)
                        figure.add_wealth(knight_net_gain)
                        contract.total_spent += payment
                        contract.remaining_years -= 1

                        if figure.faction_id and figure.faction_id in faction_tax_collected:
                            faction_tax_collected[figure.faction_id] += tax_float

                        # 日志：工程合同收益
                        self.state.log_event(
                            f"工程合同收益: {figure.name} 净得 {knight_net_gain}，国库 -{payment}",
                            extra={
                                "type": "works_contract_revenue",
                                "contract_id": contract.id,
                                "figure_id": figure.id,
                                "net_profit": knight_net_gain,
                                "treasury_cost": payment
                            }
                        )

                        if contract.remaining_years <= 0:
                            contract.mark_complete(self.state.turn.turn_number)
                            province = self.state.get_province(contract.province_id)
                            if province:
                                province.unbind_project_contract()
                            self.state.log_event(
                                f"工程合同竣工: {contract.name}",
                                extra={"type": "works_contract_complete", "contract_id": contract.id}
                            )
            except Exception as e:
                self.state.log_exception(
                    e,
                    context=f"合同收益处理失败: 合同 {contract.id}",
                    extra={"contract_id": contract.id, "contract_type": contract.contract_type.value}
                )
                continue

    def _print_faction_table(self, terms, faction_data: Dict[str, dict]):
        factions = list(self.state.factions.values())
        if not factions:
            return
        factions.sort(key=lambda f: f.name)

        print("💰 派系金库收益 (Faction Treasury):")
        # 表头
        header = "        "
        for f in factions:
            header += f"{f.name:<12}"
        print(header)

        # 财政拨款
        row = "财政拨款"
        for f in factions:
            stipend = faction_data[f.id]['stipend']
            row += f"  +{stipend:<10}"
        print(row)

        # 会员贡献
        row = "会员贡献"
        for f in factions:
            tax = faction_data[f.id]['tax']
            row += f"  +{tax:<10}"
        print(row)

        # 现有资金
        row = "现有资金"
        for f in factions:
            final = faction_data[f.id]['final']
            row += f"  {final:<10}"
        print(row)

    def _print_private_land_table(self, data: List[Tuple[int, str, int, int]], terms):
        if not data:
            print("\n   🌾 无地主私人收益")
            return

        print("\n" + "=" * 70)
        print("💰 地主私人收益 (Landowners' Private Income)")
        print("=" * 70)
        print(f"{'ID':<5} {'Name':<40} {'Income':<10} {'Wealth':<10}")
        print("-" * 70)

        total_income = 0
        total_wealth = 0
        for fig_id, name, income, wealth in data:
            print(f"{fig_id:<5} {name:<40} {income:<10} {wealth:<10}")
            total_income += income
            total_wealth += wealth

        print("-" * 70)
        print(f"{'Total':<5} {'':<40} {total_income:<10} {total_wealth:<10}")
        print("=" * 70)