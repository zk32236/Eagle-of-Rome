# src/ui/commands/phase_revenue.py
"""
税收阶段命令 - 处理税收、派系津贴、军团维护费和合同收益
"""

from typing import List, TYPE_CHECKING
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

        # 1. 国家公地收益
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        national_tax_rate = self.state.get_economic_rule("national_public_land_tax_rate", 0.02)
        national_land = self.state.get_national_public_land()
        tax_income = int(national_land * land_price * national_tax_rate)
        self.state.add_treasury(tax_income)
        print(f"   💰 国家公地收益: +{tax_income} {terms.currency}")

        # 2. 派系津贴
        stipend = self.state.get_economic_rule("faction_stipend", 10)
        for faction in self.state.factions.values():
            self.state.add_faction_treasury(faction.id, stipend)
            print(f"   {faction.name}: +{stipend} {terms.currency}")

        # 3. 私地收益
        self._process_private_land_income(terms)

        # 4. 军团维护费
        ms = self.state.get_military_system()
        if ms:
            success, msg = ms.apply_maintenance()
            status = "✅" if success else "⚠️"
            print(f"   {status} {msg}")

        # 5. 合同收益结算
        self._process_contract_revenues(terms)

        # 6. 输出国库摘要
        print(f"\n   📊 State Treasury: {self.state.treasury} {terms.currency}")

        # 7. 军事摘要
        if ms:
            print(ms.get_military_summary())

        # 8. 合同摘要
        self._show_contract_summary(terms)

        # 9. 显示私地状态
        from src.ui.commands.func_status import StatusPrivateLandCommand
        spr_cmd = StatusPrivateLandCommand(self.state)
        spr_cmd.execute([])

        # 10. 处理已完成工程合同的质保年限递减
        self._process_warranty_decay(terms)

        # 11. 兼容旧逻辑
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "revenue"

        self.state.mark_phase_executed("revenue")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _process_private_land_income(self, terms):
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("private_land_income_rate", 0.05)

        total_int = 0
        for fig in self.state.get_living_members():
            income_float = fig.land_private * land_price * rate
            income_int = round(income_float)
            if income_int > 0:
                fig.add_wealth(income_int)
                total_int += income_int

        if total_int > 0:
            print(f"\n   🌾 私地收益: +{total_int} {terms.currency} 已分配至各人物私库")
        else:
            print(f"\n   🌾 无私地收益")

    def _process_contract_revenues(self, terms):
        from src.core.entities.contract import ContractType, ContractStatus

        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE]

        if not active_contracts:
            return

        print(f"\n   📜 Contract Revenues:")

        for contract in active_contracts:
            if contract.contract_type == ContractType.TAX_FARMING:
                # 包税合同处理
                winning_bid = contract.winning_bid
                if not winning_bid:
                    continue
                figure = self.state.get_member(winning_bid["bidder_id"])
                if not figure or figure.is_dead:
                    contract.terminate()
                    province = self.state.get_province(contract.province_id)
                    if province:
                        province.unbind_tax_contract()
                    print(f"      ⚠️  {contract.name}: 中标者已死亡，合同终止")
                    continue

                # 获取年净收入（已在 resolve_auction 中计算）
                annual_profit = contract.annual_profit  # 关键修复：定义变量
                self.state.add_treasury(winning_bid["amount"])
                self.state.add_figure_wealth(winning_bid["bidder_id"], annual_profit)
                contract.total_collected += annual_profit

                print(f"      📊 {contract.name}: {figure.name} 获得 {annual_profit} {terms.currency} 净收入，国库 +{winning_bid['amount']}")

                contract.remaining_years -= 1
                if contract.remaining_years <= 0:
                    contract.mark_complete(self.state.turn.turn_number)
                    province = self.state.get_province(contract.province_id)
                    if province:
                        province.unbind_tax_contract()
                    print(f"         ✅ 合同到期完成")

            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                # 工程合同处理
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
                    # 最后一年补足余数
                    if contract.remaining_years == 1:
                        paid = contract.total_spent
                        total_bid = contract.base_cost
                        payment = total_bid - paid
                    else:
                        payment = annual_income

                    self.state.add_treasury(-payment)
                    self.state.add_figure_wealth(contract.awarded_to, payment)
                    contract.total_spent += payment
                    contract.remaining_years -= 1
                    print(f"      🏗️ {contract.name}: Treasury -{payment}, {figure.name} +{payment} (成本 {contract.annual_cost})")

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
                    # 质保到期，可触发事件（暂留接口）
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