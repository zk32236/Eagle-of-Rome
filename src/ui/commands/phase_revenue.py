# src/ui/commands/phase_revenue.py
"""
税收阶段命令 - 处理税收、派系津贴、军团维护费和合同收益
"""

from typing import List, Dict, TYPE_CHECKING
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

        # 获取配置
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        national_tax_rate = self.state.get_economic_rule("national_public_land_tax_rate", 0.02)
        stipend = self.state.get_economic_rule("faction_stipend", 10)
        tax_rate = self.state.get_economic_rule("faction_tax_rate", 0.1)  # 派系抽成比例

        # 初始化派系抽成累计字典
        faction_tax_collected: Dict[str, float] = {}
        for faction in self.state.factions.values():
            faction_tax_collected[faction.id] = 0.0

        # 1. 国家公地收益
        national_land = self.state.get_national_public_land()
        tax_income = int(round(national_land * land_price * national_tax_rate))
        self.state.add_treasury(tax_income)
        print(f"   💰 国家公地收益: +{tax_income} {terms.currency}")

        # 2. 派系津贴
        for faction in self.state.factions.values():
            self.state.add_faction_treasury(faction.id, stipend)
            print(f"   {faction.name}: +{stipend} {terms.currency}")

        # 3. 私地收益（同时计算抽成）
        self._process_private_land_income(terms, faction_tax_collected, tax_rate)

        # 4. 军团维护费
        ms = self.state.get_military_system()
        if ms:
            success, msg = ms.apply_maintenance()
            status = "✅" if success else "⚠️"
            print(f"   {status} {msg}")

        # 5. 合同收益结算（同时计算抽成）
        self._process_contract_revenues(terms, faction_tax_collected, tax_rate)

        # 6. 将累计抽成取整后加入派系金库
        for faction_id, total_tax_float in faction_tax_collected.items():
            tax_int = int(round(total_tax_float))  # 四舍五入取整
            if tax_int > 0:
                faction = self.state.get_faction(faction_id)
                if faction:
                    faction.treasury += tax_int
                    print(f"   {faction.name} 派系金库 +{tax_int} {terms.currency}（成员贡献）")
                    self.state.log_event(f"派系抽成: {faction.name} +{tax_int}")

        # 7. 输出国库摘要
        print(f"\n   📊 State Treasury: {self.state.treasury} {terms.currency}")

        # 8. 军事摘要
        if ms:
            print(ms.get_military_summary())

        # 9. 合同摘要
        self._show_contract_summary(terms)

        # 10. 显示私地状态
        from src.ui.commands.func_status import StatusPrivateLandCommand
        spr_cmd = StatusPrivateLandCommand(self.state)
        spr_cmd.execute([])

        # 11. 处理已完成工程合同的质保年限递减
        self._process_warranty_decay(terms)

        # 12. 兼容旧逻辑
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "revenue"

        self.state.mark_phase_executed("revenue")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _process_private_land_income(self, terms, faction_tax_collected: Dict[str, float], tax_rate: float):
        """处理私地收入，同时计算派系抽成"""
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("private_land_income_rate", 0.05)

        total_net = 0.0
        for fig in self.state.get_living_members():
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
                total_net += net_income_float
                if fig.faction_id and fig.faction_id in faction_tax_collected:
                    faction_tax_collected[fig.faction_id] += tax_float

        if total_net > 0:
            print(f"\n   🌾 私地收益分配完成，总净收入约 {total_net:.1f} {terms.currency}")
        else:
            print(f"\n   🌾 无私地收益")

    def _process_contract_revenues(self, terms, faction_tax_collected: Dict[str, float], tax_rate: float):
        """处理合同收益，同时计算派系抽成"""
        from src.core.entities.contract import ContractType, ContractStatus

        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE]

        if not active_contracts:
            return

        print(f"\n   📜 Contract Revenues:")

        for contract in active_contracts:
            if contract.contract_type == ContractType.TAX_FARMING:
                winning_bid = contract.winning_bid
                if not winning_bid:
                    continue
                figure = self.state.get_member(winning_bid["bidder_id"])
                if not figure or figure.is_dead:
                    # 中标者已死亡，终止合同
                    contract.terminate()
                    province = self.state.get_province(contract.province_id)
                    if province:
                        province.unbind_tax_contract()
                    print(f"      ⚠️  {contract.name}: 中标者已死亡，合同终止")
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

                print(
                    f"      📊 {contract.name}: {figure.name} 获得 {net_profit_int} {terms.currency} 净收入，国库 +{winning_bid['amount']}")

                if contract.remaining_years > 0:
                    contract.remaining_years -= 1
                    if contract.remaining_years == 0:
                        contract.set_extended(True)
                        print(f"         📌 合同已延期，继续生效")


            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                figure = self.state.get_member(contract.awarded_to)
                if not figure or figure.is_dead:
                    contract.terminate()
                    province = self.state.get_province(contract.province_id)
                    if province:
                        province.unbind_project_contract()
                    print(f"      ⚠️  {contract.name}: 中标者已死亡，合同终止")
                    continue

                if contract.remaining_years > 0:
                    annual_income = contract.annual_income
                    annual_cost = contract._annual_cost  # 直接访问私有字段
                    if contract.remaining_years == 1:
                        paid = contract.total_spent
                        total_bid = contract.base_cost
                        payment = total_bid - paid
                        cost = annual_cost
                    else:
                        payment = annual_income
                        cost = annual_cost

                    # 计算利润（工程款 - 当年成本）
                    profit_float = float(payment - cost)

                    if profit_float > 0:
                        tax_float = profit_float * tax_rate
                        tax_int = int(round(tax_float))
                    else:
                        tax_float = 0.0
                        tax_int = 0

                    # 骑士净收益 = 利润 - 抽成

                    knight_net_profit = profit_float - tax_float
                    knight_net_gain = int(round(knight_net_profit))
                    self.state.add_treasury(-payment)
                    figure.add_wealth(knight_net_gain)
                    contract.total_spent += payment
                    contract.remaining_years -= 1

                    if figure.faction_id and figure.faction_id in faction_tax_collected:
                        faction_tax_collected[figure.faction_id] += tax_float
                    print(
                        f"      🏗️ {contract.name}: Treasury -{payment}, {figure.name} +{knight_net_gain} (利润 {profit_float:.1f}, 税 {tax_float:.1f})")
                    if contract.remaining_years <= 0:
                        contract.mark_complete(self.state.turn.turn_number)
                        province = self.state.get_province(contract.province_id)
                        if province:
                            province.unbind_project_contract()
                        print(f"         ✅ 工程竣工")
                else:
                    continue

    def _process_warranty_decay(self, terms):
        """遍历所有已完成的工程合同，减少其剩余质保年限"""
        from src.core.entities.contract import ContractType, ContractStatus

        for contract in self.state.contracts:
            if (contract.contract_type == ContractType.PUBLIC_WORKS
                    and contract.status == ContractStatus.COMPLETED
                    and hasattr(contract, 'warranty_remaining') and contract.warranty_remaining > 0):
                contract._warranty_remaining -= 1
                if contract.warranty_remaining == 0:
                    print(f"      ⚠️ {contract.name} 质保期结束，进入失修状态")

    def _show_contract_summary(self, terms):
        from src.core.entities.contract import ContractStatus

        active = [c for c in self.state.contracts if c.status == ContractStatus.ACTIVE]
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        completed = [c for c in self.state.contracts if c.status == ContractStatus.COMPLETED]
        if not (active or pending or completed):
            return
        print(f"\n   📋 Contract Status:")
        if active:
            print(f"      ▶️  Active: {len(active)}")
        if pending:
            print(f"      ⏳ Pending: {len(pending)}")
        if completed:
            print(f"      ✅ Completed: {len(completed)}")