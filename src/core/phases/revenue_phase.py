# src/core/phases/revenue_phase.py

from core.game_state import GameState
from core.localization import TerminologyService
from core.entities.contract import ContractType, ContractStatus


class RevenuePhase:
    """Revenue Phase: Collect taxes and pay expenses - MVP 0.4.3 扩展：合同收益结算"""

    def __init__(self):
        self.phase_name = "revenue"

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_revenue} Phase (Year {abs(state.turn.year)} BC) ---")

        # 1. 基础税收
        base_tax = 100
        state.treasury += base_tax
        print(f"   💰 Base tax: +{base_tax} {terms.currency}")

        # 2. 派系津贴（MVP 0.2）
        stipend = 10
        for faction in state.factions.values():
            faction.treasury += stipend
            print(f"   {faction.name}: +{stipend} {terms.currency}")

        # 3. 军团维护费（MVP 0.3）
        ms = state.get_military_system()
        if ms:
            success, msg = ms.apply_maintenance()
            status = "✅" if success else "⚠️"
            print(f"   {status} {msg}")

        # MVP 0.4.3: 4. 合同收益结算
        self._process_contract_revenues(state, terms)

        print(f"\n   📊 State Treasury: {state.treasury} {terms.currency}")

        # 显示军事摘要
        if ms:
            print(ms.get_military_summary())

        # 显示合同摘要
        self._show_contract_summary(state, terms)

        state.turn.current_phase = self.phase_name
        return True

    def _process_contract_revenues(self, state: GameState, terms):
        """处理合同收益结算 - MVP 0.4.3"""
        active_contracts = [c for c in state.contracts
                            if c.status == ContractStatus.ACTIVE]

        if not active_contracts:
            return

        print(f"\n   📜 Contract Revenues:")

        for contract in active_contracts:
            figure = state.get_member(contract.awarded_to)
            if not figure or figure.is_dead:
                # 承包商死亡，合同终止
                contract.status = ContractStatus.EXPIRED
                print(f"      ⚠️  {contract.name}: Contractor deceased, contract void")
                continue

            if contract.contract_type == ContractType.TAX_FARMING:
                # 包税：骑士获得收益
                profit = contract.execute_tax_collection()
                figure.wealth += profit
                print(f"      📊 {contract.name}: {figure.name} +{profit} {terms.currency}")

                if contract.status == ContractStatus.COMPLETED:
                    print(f"         ✅ Contract completed! Total collected: {contract.total_collected}")

            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                # 工程：国库支付，骑士获得利润
                annual_budget = contract.base_cost // contract.duration_years
                profit = contract.execute_works_payment()

                # 国库支付
                state.treasury -= annual_budget
                # 骑士获得利润（预算的一部分作为利润）
                figure.wealth += profit

                print(f"      🏗️ {contract.name}: Treasury -{annual_budget}, {figure.name} +{profit} profit")

                if contract.status == ContractStatus.COMPLETED:
                    print(f"         ✅ Project completed! Total profit: {contract.total_spent}")

    def _show_contract_summary(self, state: GameState, terms):
        """显示合同摘要 - MVP 0.4.3"""
        active = [c for c in state.contracts if c.status == ContractStatus.ACTIVE]
        pending = [c for c in state.contracts if c.status == ContractStatus.PENDING]
        completed = [c for c in state.contracts if c.status == ContractStatus.COMPLETED]

        if not (active or pending or completed):
            return

        print(f"\n   📋 Contract Status:")
        if active:
            print(f"      ▶️  Active: {len(active)}")
        if pending:
            print(f"      ⏳ Pending: {len(pending)}")
        if completed:
            print(f"      ✅ Completed: {len(completed)}")