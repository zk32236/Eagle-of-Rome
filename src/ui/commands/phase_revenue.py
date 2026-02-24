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

        # 3. 私地收益（浮点计算，加财富四舍五入，仅显示实际值）
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

        # 9. 显示私地状态以便对比
        from src.ui.commands.func_status import StatusPrivateLandCommand
        spr_cmd = StatusPrivateLandCommand(self.state)
        spr_cmd.execute([])

        # 10. 兼容旧逻辑
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "revenue"

        self.state.mark_phase_executed("revenue")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _process_private_land_income(self, terms):
        """计算并发放私地收益（浮点计算，加财富四舍五入，仅显示实际值）"""
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
        """
        处理活跃合同的年度收益

        遍历所有状态为 ACTIVE 的合同：
        - 包税合同：根据中标信息和实际税率结算
        - 工程合同：原有逻辑（国库支付年度预算，骑士获得利润）
        """
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
                tax_rate = contract.tax_rate
                if not winning_bid:
                    # 无中标信息，跳过（可能是旧合同或其他异常）
                    continue

                # 获取中标者
                figure = self.state.get_member(winning_bid["bidder_id"])
                if not figure or figure.is_dead:
                    # 中标者已死亡，合同终止
                    contract.terminate()
                    print(f"      ⚠️  {contract.name}: 中标者已死亡，合同终止")
                    continue

                # 获取行省
                province = self.state.get_province(contract.province_id)
                if not province:
                    continue

                # 从配置读取参数
                land_price = self.state.get_economic_rule("land_price_per_unit", 10)
                base_income_rate = self.state.get_economic_rule("private_land_income_rate", 0.05)

                # 行省基础年收益
                base_income = province.land_public * land_price * base_income_rate
                # 骑士实际征收税收
                actual_tax = int(base_income * tax_rate)

                # 国库获得中标价
                self.state.add_treasury(winning_bid["amount"])
                # 骑士获得实际税收
                self.state.add_figure_wealth(winning_bid["bidder_id"], actual_tax)

                print(f"      📊 {contract.name}: {figure.name} 获得 {actual_tax} {terms.currency} 税收，国库 +{winning_bid['amount']}")

                # 剩余年限递减
                contract.remaining_years -= 1
                if contract.remaining_years <= 0:
                    contract.mark_complete(self.state.turn.turn_number)
                    print(f"         ✅ 合同到期完成")

            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                # 工程合同（原有逻辑）
                figure = self.state.get_member(contract.awarded_to)
                if not figure or figure.is_dead:
                    contract.expire()
                    print(f"      ⚠️  {contract.name}: Contractor deceased, contract void")
                    continue

                annual_budget = contract.base_cost // contract.duration_years
                profit = contract.execute_works_payment()

                self.state.add_treasury(-annual_budget)
                self.state.add_figure_wealth(contract.awarded_to, profit)

                print(f"      🏗️ {contract.name}: Treasury -{annual_budget}, {figure.name} +{profit} profit")

                if contract.status == ContractStatus.COMPLETED:
                    print(f"         ✅ Project completed! Total profit: {contract.total_spent}")

    def _show_contract_summary(self, terms):
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