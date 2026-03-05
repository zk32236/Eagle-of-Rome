# src/ui/commands/func_status.py
"""
Status命令 - 显示当前游戏状态摘要
"""

from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import ContractType, ContractStatus
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.game_state import GameState

# src/ui/commands/func_status.py

class ProvinceCommand(Command):
    """显示行省状态命令"""

    name = "province"
    aliases = ["prov"]
    description = "显示行省状态，用法: province [行省ID] (不指定ID则显示所有行省概要)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _get_controlling_faction(self, province_id: int) -> Optional[str]:
        """返回控制该行省的派系名称，若无则返回 None"""
        for faction in self.state.factions.values():
            if province_id in faction.province_owned:
                return faction.name
        return None

    def _format_contract_info(self, contract_id: Optional[int]) -> str:
        """返回合同简要信息"""
        if contract_id is None:
            return "无"
        contract = self.state.get_contract(contract_id)
        if not contract:
            return "无效"
        if contract.contract_type == ContractType.TAX_FARMING:
            tax_rate = getattr(contract, 'tax_rate', 0.0)
            return f"包税(税率 {tax_rate*100:.0f}%)"
        else:
            return f"工程(预算 {contract.base_cost})"

    def _get_governor_name(self, governor_id: Optional[int]) -> str:
        if governor_id is None:
            return "无"
        fig = self.state.get_member(governor_id)
        if fig is None:
            return "缺失(数据异常)"
        return fig.get_formal_name()

    def execute(self, args: List[str]) -> bool:
        if not args:
            # 显示所有已征服行省概要
            provinces = [p for p in self.state.get_all_provinces() if p.conquered]
            if not provinces:
                print("   📭 没有已征服的行省数据")
                return True

            print("\n" + "=" * 80)
            print("   🏛️ 已征服行省状态一览")
            print("=" * 80)
            print(
                f"{'ID':<4} {'名称':<12} {'类型':<10} {'总督':<16} {'民怨':<4} {'包税合同':<16} {'工程合同':<16} {'控制派系':<12}")
            print("-" * 80)

            for p in provinces:
                if p.province_id == 0:
                    name = "意大利(本土)"
                else:
                    name = p.name
                gov_name = self._get_governor_name(p.governor_id)
                gov_type = p.governor_type if hasattr(p, 'governor_type') and p.governor_type else "未知"
                tax_info = self._format_contract_info(p.tax_contract_id)
                proj_info = self._format_contract_info(p.project_contract_id)
                controller = self._get_controlling_faction(p.province_id) or "无"
                print(
                    f"{p.province_id:<4} {name:<12} {gov_type:<10} {gov_name:<16} {p.grievance:<4} {tax_info:<16} {proj_info:<16} {controller:<12}")
            print("=" * 80)
            return True

        # 有参数：显示单个行省详情
        try:
            pid = int(args[0])
        except ValueError:
            print(f"❌ 无效的行省ID: {args[0]}，必须为整数")
            return False

        province = self.state.get_province(pid)
        if not province:
            print(f"❌ 行省ID {pid} 不存在")
            return False
        if not province.conquered:
            print(f"❌ 行省ID {pid} 尚未征服")
            return False

        print("\n" + "=" * 60)
        if pid == 0:
            print(f"   🏛️ 行省详情：意大利 (本土)")
        else:
            print(f"   🏛️ 行省详情：{province.name} (ID:{pid})")
        print("=" * 60)

        print(f"   总土地: {province.total_land} C")
        print(f"   公地: {province.land_public} C")
        print(f"   私地: {province.land_private} C")
        print(f"   行省类型: {province.governor_type if hasattr(province, 'governor_type') else '未设置'}")
        if province.governor_designate_id:
            designate = self.state.get_member(province.governor_designate_id)
            designate_name = designate.get_formal_name() if designate else "?"
            print(f"   候任总督: {designate_name} (将在决算阶段上任)")

        if province.governor_id:
            gov = self.state.get_member(province.governor_id)
            gov_name = gov.get_formal_name() if gov else "?"
            # 计算上任年份
            if hasattr(province, 'governor_since') and province.governor_since and self.state.turn:
                since_year = self.state.turn.year + (province.governor_since - self.state.turn.turn_number)
                since_display = f"{abs(since_year)} BC" if since_year < 0 else f"{since_year} AD"
            else:
                since_display = "未知"
            print(f"   现任总督: {gov_name} (上任于 {since_display})")

        else:
            print(f"   现任总督: 无")

        print(f"   民怨等级: {province.grievance} (0=安居乐业,1=怨声载道,2=民不聊生,3=平民起义)")

        # 包税合同
        if province.tax_contract_id:
            contract = self.state.get_contract(province.tax_contract_id)
            if contract:
                tax_rate = getattr(contract, 'tax_rate', 0.0)
                winner = self.state.get_member(contract.awarded_to)
                winner_name = winner.get_formal_name() if winner else "未知"
                faction = self.state.get_faction(contract.awarded_faction)
                faction_name = faction.name if faction else "无"
                print(f"\n   📊 包税合同:")
                print(f"      ID: {contract.id}")
                print(f"      中标者: {winner_name} ({faction_name})")
                print(f"      实际税率: {tax_rate*100:.1f}%")
                print(f"      剩余年限: {contract.remaining_years} 年")
                print(f"      年净收入: {getattr(contract, '_annual_profit', 0)}")
            else:
                print(f"\n   ⚠️ 包税合同数据异常")
        else:
            print(f"\n   📭 无包税合同")

        # 工程合同
        if province.project_contract_id:
            contract = self.state.get_contract(province.project_contract_id)
            if contract:
                contractor = self.state.get_member(contract.awarded_to)
                contractor_name = contractor.get_formal_name() if contractor else "未知"
                faction = self.state.get_faction(contract.awarded_faction)
                faction_name = faction.name if faction else "无"
                print(f"\n   🏗️ 公共工程合同:")
                print(f"      ID: {contract.id}")
                print(f"      承建者: {contractor_name} ({faction_name})")
                print(f"      预算: {contract.base_cost}")
                print(f"      剩余年限: {contract.remaining_years} 年")
                print(f"      质保剩余: {getattr(contract, 'warranty_remaining', 0)} 年")
            else:
                print(f"\n   ⚠️ 工程合同数据异常")
        else:
            print(f"\n   🏗️ 无公共工程合同")

        # 控制派系
        controller = self._get_controlling_faction(pid)
        if controller:
            print(f"\n   🏛️ 控制派系: {controller}")
        else:
            print(f"\n   🏛️ 无派系控制")

        print("=" * 60)
        return True

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
            # 处理 ex- 前缀的官职：不显示在现任官职列
            office_display = fig.office if fig.office and not fig.office.startswith("ex-") else "无"
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

            # 计算起始年份（用于将回合数转换为实际年份）
            current_turn = self.state.turn.turn_number
            current_year = self.state.turn.year
            start_year = current_year - (current_turn - 1)

            # 格式化历史公职
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
            print(f"热忱: {fig.zeal}")
            print(f"魅力: {fig.charisma}")
            print(f"军略: {fig.martial}")
            print(f"智略: {fig.intelligence}")
            print(f"财富: {fig.wealth}")
            print(f"人气: {fig.popularity}")
            print(f"私地: {fig.land_private} C")
            print(f"老兵: {fig.veterans}")
            # 处理 ex- 前缀的官职：不显示在现任官职列
            office_display = fig.office if fig.office and not fig.office.startswith("ex-") else "无"
            print(f"担任公职: {office_display}")
            print(f"公职历史: {', '.join(history_parts) if history_parts else '无'}")
            print(f"持有合同: {fig.contract_ids if fig.contract_ids else '无'}")
            print(f"是否派系领袖: {'是' if fig.is_faction_leader else '否'}")
            print(f"是否死亡: {'是' if fig.is_dead else '否'}")
            print(f"是否在罗马: {'否' if fig.is_absent else '是'}")  # 新增
            print("=" * 50)

class FactionStatusCommand(Command):
    """显示所有派系状态命令"""

    name = "factions"
    aliases = ["fs"]
    description = "显示所有派系状态（金库、成员数、总影响力）"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """执行 factions 命令"""
        if not self.state:
            print("错误: 游戏状态未初始化")
            return False

        print("\n" + "=" * 60)
        print("   🏛️ 派系状态一览")
        print("=" * 60)

        for faction in self.state.factions.values():
            members = faction.get_members(self.state)
            member_count = len(members)
            total_influence = sum(m.influence for m in members)
            player_flag = " [玩家]" if faction.is_player else ""

            # 计算平均影响力
            avg_influence = total_influence // member_count if member_count > 0 else 0

            print(f"\n{faction.name} ({faction.id}){player_flag}")
            print(f"   💰 金库: {faction.treasury} Talents")
            print(f"   👥 成员: {member_count} 人")
            print(f"   📊 总影响力: {total_influence}")
            print(f"   📈 平均影响力: {avg_influence}")

            # 如果成员数为0，显示警告
            if member_count == 0:
                print(f"   ⚠️  派系无人！")

        print("=" * 60)
        return True

def get_progress_bar(state, width=7):
    """生成进度条字符串，格式：[▓░░░░░░] 已执行/总数"""
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"