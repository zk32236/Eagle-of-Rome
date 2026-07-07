# src/ui/commands/func_load.py
import datetime
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.scenario_loader import ScenarioLoader
from src.core.localization import TerminologyService
from src.core.entities.figure import ClassTier

if TYPE_CHECKING:
    from src.core.game_state import GameState


class LoadCommand(Command):
    """加载游戏场景命令"""

    name = "load"
    aliases = ["l"]
    description = "加载场景 (默认: mvp_test.json)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        scenario_file = args[0] if args else "mvp_test.json"

        try:
            # 加载场景
            ScenarioLoader.load_scenario(self.state, scenario_file)

            # 获取关键信息
            year_display = f"{abs(self.state.turn.year)} BC" if self.state.turn.year < 0 else f"{self.state.turn.year} AD"
            treasury = self.state.treasury

            # 获取所有行省名称（意大利特殊处理）
            provinces = self.state.get_all_provinces()
            province_names = []
            for p in provinces:
                if p.conquered:
                    if p.province_id == 0:
                        province_names.append("意大利(本土)")
                    else:
                        province_names.append(p.name)
            territory = ", ".join(province_names)

            # 打印启动时间戳
            start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n📅 游戏启动时间：{start_time}")

            # 打印精简加载页面
            print("\n" + "=" * 60)
            print("               Eagle of Rome - MVP 0.5".center(60))
            print("=" * 60)
            print("游戏简介：基于罗马共和国历史背景的政治策略游戏")
            print(f"开始年份：{year_display}")
            print(f"国库资金：{treasury} Talents")
            print(f"罗马领土：{territory}")
            print("=" * 60)

            return True

        except FileNotFoundError as e:
            print(f"\n❌ 场景文件不存在: {scenario_file}")
            print(f"   错误信息: {e}")
            return False
        except Exception as e:
            print(f"\n❌ 场景加载失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _get_term_info(self) -> str:
        """获取术语信息字符串"""
        terms = TerminologyService.get()
        # 获取当前预设名称（需要从 TerminologyService 获取）
        # 简单方法：遍历 PRESETS 找到匹配的实例
        current_name = "original"
        for name, preset in TerminologyService.PRESETS.items():
            if preset is TerminologyService._current:
                current_name = name
                break
        return (f"   📝 Terminology: {current_name}\n"
                f"   Active terms: {terms.assembly}/{terms.nobles}/{terms.currency}")

    # 在 LoadCommand 类中，替换 _get_ex_office_info 方法

    def _get_ex_office_info(self, faction):
        """获取派系的前任公职信息（确保三人不同）"""
        members = faction.get_members(self.state)
        ex_consul = None
        ex_praetor = None
        ex_quaestor = None

        # 先找执政官（有 consul 历史的人）
        for m in members:
            if any(term.office_type == "consul" for term in m.office_history):
                ex_consul = m
                break

        # 再找大法官（有 praetor 历史，且不是执政官）
        for m in members:
            if any(term.office_type == "praetor" for term in m.office_history) and m is not ex_consul:
                ex_praetor = m
                break

        # 最后找财务官（有 quaestor 历史，且不是前两者）
        for m in members:
            if any(term.office_type == "quaestor" for term in m.office_history) and m not in (ex_consul, ex_praetor):
                ex_quaestor = m
                break

        return {
            "consul": ex_consul.name if ex_consul else "None",
            "praetor": ex_praetor.name if ex_praetor else "None",
            "quaestor": ex_quaestor.name if ex_quaestor else "None"
        }

    def _display_faction_details(self):
        """显示派系详细信息（保留图标和ID，移除属性）"""
        terms = TerminologyService.get()

        print("\n" + "=" * 50)
        print(f"Year: {abs(self.state.turn.year)} BC (Turn {self.state.turn.turn_number})")
        print(f"Phase: {self.state.turn.current_phase}")
        print(f"Treasury: {self.state.treasury} {terms.currency}")
        print("-" * 50)
        print("FACTIONS & MEMBERS:")
        print()

        # 显示前公职信息
        for faction in self.state.factions.values():
            ex = self._get_ex_office_info(faction)
            print(
                f"   {faction.name}: Ex-Consul({ex['consul']}), Ex-Praetor({ex['praetor']}), Ex-Quaestor({ex['quaestor']})")

        # 显示领袖信息
        print()
        for faction in self.state.factions.values():
            leader = faction.get_leader(self.state)
            if leader:
                print(f"   👑 {faction.name} leader: {leader.name} (Influence: {leader.influence})")  # 修改点

        print(f"\n✅ Game loaded!")
        print("=" * 50)

        # 显示每个派系的成员列表（保留图标和ID，移除属性）
        for faction in self.state.factions.values():
            player_flag = " [PLAYER CONTROLLED]" if faction.is_player else ""
            print(f"\n{faction.name} ({faction.id}) - Treasury: {faction.treasury}{terms.currency}{player_flag}")

            members = faction.get_members(self.state)
            for member in members:
                # 构建显示字符串：状态图标 阶层图标 ID:数字 姓名
                status_emoji = "☠️" if member.is_dead else ("👑" if member.is_faction_leader else "🟢")
                tier_emoji = {
                    ClassTier.NOBILE: "🏛️",
                    ClassTier.EQUES: "💰",
                    ClassTier.PLEBEIAN: "👤"
                }.get(member.class_tier, "❓")
                display_name = member.get_formal_name()
                print(f"  {status_emoji}{tier_emoji} ID:{member.id} {display_name}")

            total_influence = sum(m.influence for m in members)  # 修改点
            print(f"  Total Influence: {total_influence}")       # 修改点
            print()

        print("=" * 50)
        print("\n   Progress: [░░░░░░░] 0/7")

