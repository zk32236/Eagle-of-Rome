# src/ui/commands/phase_revenue.py
"""
税收阶段命令 - 负责阶段守卫、调用经济服务和展示收入结算结果。
"""
from typing import Dict, List, Tuple, TYPE_CHECKING

from src.core.localization import TerminologyService
from src.core.service.economic_service import EconomicService
from src.ui.commands.sys_base import Command

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

        result = EconomicService(self.state).settle_revenue_phase()
        if not result["success"]:
            print("⚠️ 税收阶段结算失败")
            for error in result.get("errors", []):
                print(f"   - {error}")
            return False

        data = result["data"]
        self._print_revenue_result(terms, data)
        self.state.log_event(
            f"税收阶段完成: 国库 {data['ending_treasury']}",
            extra={
                "type": "revenue_phase_complete",
                "starting_treasury": data["starting_treasury"],
                "ending_treasury": data["ending_treasury"],
                "treasury_delta": data["treasury_delta"],
            }
        )
        self.state.mark_phase_executed("revenue")
        return True

    # ================================= MVP 0.7 ===========================================

    def _deduct_national_opex(self):
        """兼容旧测试入口：扣除国家运营费并打印。"""
        data = EconomicService(self.state).deduct_national_opex()
        self._print_national_opex(data)
        return data

    def _settle_indemnities(self):
        """兼容旧测试入口：结算战争赔款并打印。"""
        rows = EconomicService(self.state).settle_indemnities()
        self._print_indemnities(rows)
        return rows

    # ================================= MVP 0.1-0.5 =======================================

    def _process_contract_warranty(self):
        """兼容旧入口：处理已竣工合同的质保期递减。"""
        return EconomicService(self.state).process_contract_warranty()

    def _process_warranty_decay(self, terms=None):
        """兼容扩展测试入口：递减质保并在到期时提示。"""
        rows = self._process_contract_warranty()
        for row in rows:
            if row["expired"]:
                print(f"工程合同质保期结束: {row['name']}")
        return rows

    def _collect_private_land_income(
            self,
            terms,
            faction_tax_collected: Dict[str, float],
            tax_rate: float
    ) -> List[Tuple[int, str, int, int]]:
        return EconomicService(self.state).collect_private_land_income(faction_tax_collected, tax_rate)

    def _collect_contract_revenues(self, terms, faction_tax_collected: Dict[str, float], tax_rate: float):
        return EconomicService(self.state).collect_contract_revenues(faction_tax_collected, tax_rate)

    def _print_revenue_result(self, terms, data: Dict):
        self._print_indemnities(data["indemnities"])
        self._print_national_opex(data["national_opex"])
        self._print_public_land_income(terms, data["public_land_income"])

        military = data["maintenance"]["military"]
        if military.get("available"):
            print(f"📊 军团维护费: \t{military.get('total', 0)} {terms.currency}")

        naval = data["maintenance"]["naval"]
        print(f"      ⚓ {naval.get('message', '')}")

        self._print_faction_table(terms, data["faction_rows"])
        self._print_private_land_table(data["private_land_rows"], terms)

    def _print_indemnities(self, rows: List[Dict]):
        for row in rows:
            amount = row["amount"]
            if row["kind"] == "income":
                print(f"      📦 战争赔款收入: {row['name']} +{amount} Talents")
            elif row["kind"] == "expense":
                print(f"      💸 战争赔款支出: {row['name']} {-amount} Talents")
            elif row["kind"] == "insufficient":
                print(f"      💀 国库不足以支付战争赔款 {row['name']} {-amount} Talents，共和覆灭！")

    def _print_national_opex(self, data: Dict):
        provinces = data.get("provinces", [])
        if not provinces:
            print("   🏛️ 无已征服行省，国家运营费为 0")
            return

        print("\n   🏛️ 国家运营费计算：")
        for province in provinces:
            print(f"      行省 {province['name']}: total_land={province['total_land']}")

        amount = data.get("amount", 0)
        if amount > 0:
            print(f"      土地单价: {data['land_price']} Talents/单位, 费率: {data['rate']}")
            print(f"      总土地: {data['total_land']}, 运营费 = {amount} Talents")
            print(f"      国库扣除后余额: {data['treasury_after']}")
        else:
            print("      运营费为 0，不扣除")

    def _print_public_land_income(self, terms, data: Dict):
        for modifier in data.get("modifiers", []):
            if modifier["type"] == "bumper_harvest":
                print(f"      🌾 风调雨顺加成: 国家公地收益 ×{modifier['multiplier']}")
            elif modifier["type"] == "disaster":
                print(f"      🌪️ 天灾影响: 国家公地收益减少 {modifier['loss_ratio'] * 100:.0f}%")

        print(f"💰 国家公地收益: \t+{data.get('amount', 0)} {terms.currency}")
        print(f"📊 国库现有资金: \t{data.get('treasury_after', self.state.treasury)} {terms.currency}\n")

    def _print_faction_table(self, terms, faction_data: Dict[str, dict]):
        factions = list(self.state.factions.values())
        if not factions:
            return
        factions.sort(key=lambda f: f.name)

        print("💰 派系金库收益 (Faction Treasury):")
        header = "        "
        for f in factions:
            header += f"{f.name:<12}"
        print(header)

        row = "财政拨款"
        for f in factions:
            stipend = faction_data.get(f.id, {}).get("stipend", 0)
            row += f"  +{stipend:<10}"
        print(row)

        row = "会员贡献"
        for f in factions:
            tax = faction_data.get(f.id, {}).get("tax", 0)
            row += f"  +{tax:<10}"
        print(row)

        row = "现有资金"
        for f in factions:
            final = faction_data.get(f.id, {}).get("final", f.treasury)
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
