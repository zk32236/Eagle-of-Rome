# src/ui/commands/func_status.py
"""
Status命令 - 显示当前游戏状态摘要
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier

if TYPE_CHECKING:
    from src.core.game_state import GameState


class StatusCommand(Command):
    """显示游戏状态摘要命令"""

    name = "status"
    aliases = ["sts"]
    description = "显示当前游戏状态摘要（国库、人物数等）"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if not self.state:
            print("错误: 游戏状态未初始化")
            return False

        treasury = self.state.treasury
        living_count = len(self.state.get_living_members())
        faction_count = len(self.state.factions)
        turn_year = self.state.turn.year if self.state.turn else "未知"
        turn_num = self.state.turn.turn_number if self.state.turn else "未知"

        print("\n" + "=" * 50)
        print("   📊 游戏状态摘要")
        print("=" * 50)
        print(f"   回合: 第 {turn_num} 年 ({abs(turn_year)} BC)")
        print(f"   国库: {treasury} 塔兰特")
        print(f"   存活人物: {living_count} 人")
        print(f"   派系数: {faction_count} 个")
        print("=" * 50)
        return True


class StatusPublicLandCommand(Command):
    name = "status_public_land"
    aliases = ["spl"]
    description = "显示国家公地信息：数量、价值、年收益、国库余额"

    def execute(self, args: List[str]) -> bool:
        terms = TerminologyService.get()
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        tax_rate = self.state.get_economic_rule("national_public_land_tax_rate", 0.02)
        national_land = self.state.get_national_public_land()
        value = national_land * land_price
        annual_income = int(value * tax_rate)
        treasury = self.state.treasury

        print("\n" + "=" * 50)
        print("   🏞️ 国家公地信息")
        print("=" * 50)
        print(f"   公地数量: {national_land} C")
        print(f"   土地单价: {land_price} Talents/C")
        print(f"   公地价值: {value} Talents")
        print(f"   年收益率: {tax_rate * 100:.1f}%")
        print(f"   年收益: {annual_income} Talents")
        print(f"   国库余额: {treasury} Talents")
        print("=" * 50)
        return True


class StatusPrivateLandCommand(Command):
    name = "status_private_land"
    aliases = ["spr"]
    description = "显示所有存活人物的私地信息：数量、价值、年收益、私库余额"

    def execute(self, args: List[str]) -> bool:
        terms = TerminologyService.get()
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        income_rate = self.state.get_economic_rule("private_land_income_rate", 0.05)

        living = self.state.get_living_members()
        if not living:
            print("   无存活人物")
            return True

        # 仅筛选有土地的人物
        landowners = [fig for fig in living if fig.land_private > 0]
        if not landowners:
            print("   无拥有土地的人物")
            return True

        print("\n" + "=" * 80)
        print("   👤 有土地的人物私地信息")
        print("=" * 80)
        print(f"{'ID':<5} {'姓名':<20} {'私地(C)':<8} {'价值(T)':<10} {'年收益(T)':<12} {'私库(T)'}")
        print("-" * 80)

        total_land = 0
        total_value = 0
        total_income = 0.0
        total_wealth = 0

        for fig in landowners:
            name = fig.get_formal_name()
            land = fig.land_private
            value = land * land_price
            annual_income = value * income_rate
            wealth = fig.wealth

            total_land += land
            total_value += value
            total_income += annual_income
            total_wealth += wealth

            print(f"{fig.id:<5} {name:<20} {land:<8} {value:<10} {annual_income:<12.1f} {wealth}")

        print("-" * 80)
        print(f"{'总计':<5} {'':<20} {total_land:<8} {total_value:<10} {total_income:<12.1f} {total_wealth}")
        print("=" * 80)
        return True

class StatusFigureCommand(Command):
        name = "status_figure"
        aliases = ["sf"]
        description = "显示人物详细信息，用法: status_figure [人物ID]（不指定ID则显示所有存活人物）"

        def execute(self, args: List[str]) -> bool:
            terms = TerminologyService.get()

            if args:
                try:
                    figure_id = int(args[0])
                    figure = self.state.get_member(figure_id)
                    if not figure or figure.is_dead:
                        print(f"❌ 人物 ID {figure_id} 不存在或已死亡")
                        return False
                    self._print_figure_detail(figure)
                except ValueError:
                    print("❌ 人物ID必须为整数")
                    return False
            else:
                living = self.state.get_living_members()
                if not living:
                    print("   无存活人物")
                    return True
                print("\n" + "=" * 80)
                print("   👥 存活人物列表")
                print("=" * 80)
                for fig in living:
                    self._print_figure_summary(fig)
            return True

        def _print_figure_summary(self, fig):
            """简要显示一行人物信息"""
            status = "👑" if fig.is_faction_leader else "🟢"
            tier_emoji = {
                ClassTier.NOBILE: "🏛️",
                ClassTier.EQUES: "💰",
                ClassTier.PLEBEIAN: "👤"
            }.get(fig.class_tier, "❓")
            faction = self.state.get_faction(fig.faction_id)
            faction_name = faction.name if faction else "无"
            office_display = fig.office if fig.office else "无"
            print(
                f"{status}{tier_emoji} ID:{fig.id:<3} {fig.get_formal_name():<25} 派系:{faction_name:<12} 影响力:{fig.influence} 财富:{fig.wealth} 人气:{fig.popularity} 私地:{fig.land_private} 老兵:{fig.veterans} 官职:{office_display}")

        def _print_figure_detail(self, fig):
            """详细显示一个人物的所有属性"""
            status = "👑" if fig.is_faction_leader else "🟢"
            tier_emoji = {
                ClassTier.NOBILE: "🏛️",
                ClassTier.EQUES: "💰",
                ClassTier.PLEBEIAN: "👤"
            }.get(fig.class_tier, "❓")
            faction = self.state.get_faction(fig.faction_id)
            faction_name = faction.name if faction else "无"

            # 计算起始年份（用于转换回合数为实际年份）
            current_turn = self.state.turn.turn_number
            current_year = self.state.turn.year
            start_year = current_year - (current_turn - 1)

            # 格式化历史公职，将回合数转换为年份
            history_parts = []
            for term in fig.office_history:
                year = start_year + (term.start_turn - 1)
                bc_ad = "BC" if year < 0 else "AD"
                history_parts.append(f"{term.office_type}({bc_ad}{abs(year)})")

            print("\n" + "=" * 50)
            print(f"   {status}{tier_emoji} 人物详细信息 (ID:{fig.id})")
            print("=" * 50)
            print(f"姓名: {fig.get_formal_name()}")
            print(f"派系: {faction_name}")
            print(f"阶层: {fig.class_tier.value}")
            print(f"家族: {fig.nomen if fig.nomen else '无'} (声望: {fig.family_prestige})")
            print(f"年龄: {fig.age}")
            land_inf = fig.land_private * 10
            vet_inf = fig.veterans * 10
            fam_inf = fig.family_prestige * 10
            off_bonus = fig.get_office_influence_bonus()
            print(
                f"影响力: {fig.influence} = 私地{land_inf} + 老兵{vet_inf} + 人气{fig.popularity} + 家族{fam_inf} + 公职{off_bonus}")
            print(f"官职等级: {fig.rank}")
            print(f"财富: {fig.wealth}")
            print(f"人气: {fig.popularity}")
            print(f"私地: {fig.land_private} C")
            print(f"老兵: {fig.veterans}")
            print(f"担任公职: {fig.office if fig.office else '无'}")
            print(f"公职历史: {', '.join(history_parts) if history_parts else '无'}")
            print(f"持有合同: {fig.contract_ids if fig.contract_ids else '无'}")
            print(f"是否派系领袖: {'是' if fig.is_faction_leader else '否'}")
            print(f"是否死亡: {'是' if fig.is_dead else '否'}")
            print("=" * 50)

def get_progress_bar(state, width=7):
    """生成进度条字符串，格式：[▓░░░░░░] 已执行/总数"""
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"