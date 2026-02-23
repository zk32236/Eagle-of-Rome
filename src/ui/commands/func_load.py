# src/ui/commands/func_load.py
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
            if any(term.office_type == "quqaestor" for term in m.office_history) and m not in (ex_consul, ex_praetor):
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
                print(f"   👑 {faction.name} leader: {leader.name} (Power: {leader.power})")

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

            total_power = sum(m.power for m in members)
            print(f"  Total Power: {total_power}")
            print()

        print("=" * 50)
        print("\n   Progress: [░░░░░░░] 0/7")

    def execute(self, args: List[str]) -> bool:
        """执行 load 命令"""
        scenario_file = args[0] if args else "mvp_test.json"

        # 显示术语信息
        print(self._get_term_info())

        try:
            # 加载场景
            ScenarioLoader.load_scenario(self.state, scenario_file)

            # 获取存活人数
            living_count = len(self.state.get_living_members())

            # 显示场景加载成功信息
            print(f"\n✅ Scenario loaded: {scenario_file}")
            print(f"   Year: {abs(self.state.turn.year)} BC")
            print(f"   Active figures: {living_count}/300")

            # 显示派系详情
            self._display_faction_details()

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