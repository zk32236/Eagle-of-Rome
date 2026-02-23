# src/ui/commands/phase_revenue.py
"""
税收阶段命令 - 处理税收、派系津贴、军团维护费和合同收益

该命令负责：
- 向国库征收基础税收
- 向每个派系发放年度津贴
- 扣除军团维护费（通过军事系统）
- 结算活跃合同（包税和工程）的收益
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
        """
        执行税收阶段

        步骤：
        1. 检查阶段是否已执行（防重复）
        2. 增加基础税收至国库
        3. 为每个派系发放年度津贴
        4. 处理军团维护费（通过军事系统）
        5. 结算活跃合同的收益
        6. 输出状态摘要
        7. 标记阶段为已执行

        Args:
            args: 命令参数（忽略）

        Returns:
            bool: 执行成功返回 True，失败返回 False
        """
        # 检查阶段是否已执行
        if self.state.is_phase_executed("revenue"):
            print("⚠️ 税收阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_revenue} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 1. 基础税收
        base_tax = self.state.get_economic_rule("base_tax", 100)
        self.state.add_treasury(base_tax)
        print(f"   💰 Base tax: +{base_tax} {terms.currency}")

        # 2. 派系津贴
        stipend = self.state.get_economic_rule("faction_stipend", 10)
        for faction in self.state.factions.values():
            self.state.add_faction_treasury(faction.id, stipend)
            print(f"   {faction.name}: +{stipend} {terms.currency}")

        # 3. 军团维护费
        ms = self.state.get_military_system()
        if ms:
            success, msg = ms.apply_maintenance()
            status = "✅" if success else "⚠️"
            print(f"   {status} {msg}")

        # 4. 合同收益结算
        self._process_contract_revenues(terms)

        # 5. 输出国库摘要
        print(f"\n   📊 State Treasury: {self.state.treasury} {terms.currency}")

        # 6. 军事摘要
        if ms:
            print(ms.get_military_summary())

        # 7. 合同摘要
        self._show_contract_summary(terms)

        # 8. 兼容旧逻辑：设置当前阶段（如果turn有该属性）
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "revenue"

        # 9. 标记阶段已执行
        self.state.mark_phase_executed("revenue")
        print(f"\n   Progress: {get_progress_bar(self.state)}")

        return True

    def _process_contract_revenues(self, terms):
        """
        处理活跃合同的年度收益

        遍历所有状态为 ACTIVE 的合同：
        - 若承包商死亡，合同作废（expire）
        - 包税合同：执行收益结算，收益归承包商个人财富
        - 工程合同：国库支付年度预算，承包商获得利润
        """
        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE]

        if not active_contracts:
            return

        print(f"\n   📜 Contract Revenues:")

        for contract in active_contracts:
            figure = self.state.get_member(contract.awarded_to)
            if not figure or figure.is_dead:
                # 承包商死亡，合同终止
                contract.expire()  # 使用封装方法，而非直接修改status
                print(f"      ⚠️  {contract.name}: Contractor deceased, contract void")
                continue

            if contract.contract_type == ContractType.TAX_FARMING:
                # 包税：骑士获得收益
                profit = contract.execute_tax_collection()
                self.state.add_figure_wealth(contract.awarded_to, profit)
                print(f"      📊 {contract.name}: {figure.name} +{profit} {terms.currency}")

                if contract.status == ContractStatus.COMPLETED:
                    print(f"         ✅ Contract completed! Total collected: {contract.total_collected}")

            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                # 工程：国库支付，骑士获得利润
                annual_budget = contract.base_cost // contract.duration_years
                profit = contract.execute_works_payment()

                # 国库支付
                self.state.add_treasury(-annual_budget)
                # 骑士获得利润
                self.state.add_figure_wealth(contract.awarded_to, profit)

                print(f"      🏗️ {contract.name}: Treasury -{annual_budget}, {figure.name} +{profit} profit")

                if contract.status == ContractStatus.COMPLETED:
                    print(f"         ✅ Project completed! Total profit: {contract.total_spent}")

    def _show_contract_summary(self, terms):
        """
        打印当前合同状态摘要
        """
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