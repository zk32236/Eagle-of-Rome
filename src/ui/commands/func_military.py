# src/ui/commands/func_military.py
"""
军事功能命令：战争状态、指派指挥官、军团状态、征召、解散
"""

from typing import List, Optional, TYPE_CHECKING

from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.war import WarStatus

if TYPE_CHECKING:
    from src.core.game_state import GameState


class WarsCommand(Command):
    """显示战争状态"""

    name = "wars"
    aliases = []
    description = "显示战争状态（牌堆、活跃、弃牌）"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        ws = self.state.get_war_system()
        if not ws:
            print("战争系统未就绪")
            return False

        terms = TerminologyService.get()

        print(f"\n{'=' * 55}")
        print(f"   ⚔️  {terms.phase_combat} Status")
        print(f"{'=' * 55}")

        # 牌堆
        deck_count = len(getattr(ws, '_war_deck', []))
        print(f"\n   📚 Deck: {deck_count} war(s) waiting")

        # 预警
        imminent = ws.check_imminent_wars() if hasattr(ws, 'check_imminent_wars') else []
        if imminent:
            print(f"\n   🔮 Imminent:")
            for war in imminent:
                print(f"      ⚠️  {war.name}")

        # 活跃战争
        active = ws.get_active_wars()
        if active:
            # 获取军事准备状态
            is_ready, unassigned, no_legions = self.state.get_military_preparation_status()

            if is_ready:
                print(f"\n   ✅ READY FOR COMBAT")
            else:
                print(f"\n   ❌ NOT READY")

            for war in active:
                print(f"\n   📋 {war.name}")
                print(f"      Strength: {war.get_total_strength()} | Duration: {war.duration}y")

                # 指挥官状态
                if war.commander_id:
                    commander = self.state.get_member(war.commander_id)
                    if commander and not commander.is_dead:
                        print(f"      🎖️  Commander: {commander.name}")
                    else:
                        status_info = {
                            "killed": ("⚰️", "KILLED"),
                            "fled": ("🏃", "FLED"),
                            "captured": ("🔒", "CAPTURED"),
                        }.get(getattr(war, 'commander_status', ''), ("❓", "UNKNOWN"))
                        emoji, text = status_info
                        print(f"      {emoji} Commander {text} - NEED REASSIGNMENT")
                else:
                    print(f"      ❌ NO COMMANDER - NEED ASSIGNMENT")

                # 军团状态
                ms = self.state.get_military_system()
                if ms:
                    legions = ms.get_legions_for_battle(war.id)
                    if legions:
                        vet_count = sum(1 for l in legions if l.is_veteran)
                        vet_text = f" ({vet_count}⭐)" if vet_count else ""
                        print(f"      🛡️  {len(legions)} legion(s){vet_text}")
                    else:
                        print(f"      💀 NO LEGIONS - NEED REINFORCEMENT")

                # 惩罚
                if hasattr(war, 'penalties') and war.penalties:
                    penalty_text = []
                    if 'unrest_per_turn' in war.penalties:
                        penalty_text.append(f"{terms.unrest}+{war.penalties['unrest_per_turn']}/turn")
                    if 'treasury_cost' in war.penalties:
                        penalty_text.append(f"{war.penalties['treasury_cost']}{terms.currency}/turn")
                    if penalty_text:
                        print(f"      💸 {', '.join(penalty_text)}")
        else:
            print(f"\n   ☮️  No active wars")

        # 弃牌堆
        discard_count = len(getattr(ws, '_war_discard', []))
        if discard_count:
            print(f"\n   ♻️  Resolved: {discard_count} war(s)")

        print(f"{'=' * 55}")
        return True


class AssignCommand(Command):
    """交互式指派指挥官和军团到战争"""

    name = "assign"
    aliases = []
    description = "交互式指派指挥官和军团到战争"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _input_int(self, prompt: str, min_val: int = 1, max_val: Optional[int] = None) -> Optional[int]:
        """辅助方法：获取整数输入"""
        try:
            val = int(input(prompt))
            if val < min_val:
                print(f"   ❌ 输入必须大于等于 {min_val}")
                return None
            if max_val is not None and val > max_val:
                print(f"   ❌ 输入必须小于等于 {max_val}")
                return None
            return val
        except ValueError:
            print("   ❌ 请输入有效数字")
            return None
        except KeyboardInterrupt:
            print("\n   操作取消")
            return None

    def _choose_from_list(self, items, display_func=None, prompt="请选择: ") -> Optional[int]:
        """辅助方法：从列表中选择一项，返回索引（从0开始）"""
        if not items:
            print("   ❌ 列表为空")
            return None

        for idx, item in enumerate(items, 1):
            if display_func:
                print(f"  {idx}. {display_func(item)}")
            else:
                print(f"  {idx}. {item}")

        choice = self._input_int(prompt, 1, len(items))
        if choice is None:
            return None
        return choice - 1

    def execute(self, args: List[str]) -> bool:
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if not ws or not ms:
            print("战争系统或军事系统未就绪")
            return False

        terms = TerminologyService.get()

        # 获取活跃战争
        active = ws.get_active_wars()
        if not active:
            print("没有活跃战争")
            return False

        # 选择战争
        print(f"\n选择战争:")
        war_idx = self._choose_from_list(
            active,
            lambda w: f"{w.name} [Str:{w.get_total_strength()}] {'⚓' if w.naval_support_required else ''}"
        )
        if war_idx is None:
            return False
        selected_war = active[war_idx]

        # 如果已有指挥官，提供增援选项
        if selected_war.commander_id is not None:
            commander = self.state.get_member(selected_war.commander_id)
            print(f"\n   ℹ️  {selected_war.name} 已有指挥官 {commander.name if commander else '未知'}")
            print(f"   选项: [a] 增援军团 / [r] 替换指挥官 / [c] 取消")
            option = input("   > ").strip().lower()
            if option == 'c':
                return False
            elif option == 'a':
                # 仅增援军团
                available = ms.get_unassigned_legions()
                if not available:
                    print("   ❌ 没有可用的军团")
                    return False
                print(f"\n   可增援的军团:")
                for idx, leg in enumerate(available, 1):
                    vet = "⭐" if leg.is_veteran else ""
                    print(f"      {idx}. {leg.name}{vet}")
                choices = input("   输入军团编号（逗号分隔，如 1,2,3）: ").strip()
                if not choices:
                    return False
                try:
                    indices = [int(x.strip()) - 1 for x in choices.split(',')]
                    selected = []
                    for i in indices:
                        if 0 <= i < len(available):
                            selected.append(available[i])
                        else:
                            print(f"   ⚠️ 忽略无效编号 {i+1}")
                    if not selected:
                        return False
                    legion_numbers = [l.number for l in selected]
                    assigned, msg = ms.assign_to_war(legion_numbers, selected_war.id, selected_war.commander_id)
                    print(f"   ✅ {msg}")
                    return True
                except ValueError:
                    print("   ❌ 输入格式错误")
                    return False
            elif option != 'r':
                print("   ❌ 无效选项")
                return False
            # 继续替换流程

        # 选择指挥官
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.is_present:
                    candidates.append(member)
        if not candidates:
            print("没有可用的指挥官")
            return False

        print(f"\n选择指挥官:")
        cmd_idx = self._choose_from_list(
            candidates,
            lambda c: f"{c.name} (Mil:{c.military}) [{c.faction_id}]"
        )
        if cmd_idx is None:
            return False
        selected_cmd = candidates[cmd_idx]

        # 选择军团
        available_legions = ms.get_unassigned_legions()
        if available_legions:
            print(f"\n可用军团:")
            for idx, leg in enumerate(available_legions, 1):
                vet = "⭐" if leg.is_veteran else ""
                print(f"  {idx}. {leg.name}{vet}")

            print(f"输入军团编号（逗号分隔，或输入 0 跳过）: ")
            choices = input("   > ").strip()
            if choices and choices != '0':
                try:
                    indices = [int(x.strip()) - 1 for x in choices.split(',')]
                    selected_legions = []
                    for i in indices:
                        if 0 <= i < len(available_legions):
                            selected_legions.append(available_legions[i])
                        else:
                            print(f"   ⚠️ 忽略无效编号 {i+1}")
                except ValueError:
                    print("   ❌ 输入格式错误")
                    return False
            else:
                selected_legions = []
        else:
            print("没有可用军团")
            selected_legions = []

        # 海军
        fleets = 0
        if selected_war.naval_support_required:
            fleet_input = self._input_int("指派舰队数量 (0-5): ", 0, 5)
            if fleet_input is None:
                return False
            fleets = fleet_input

        # 执行指派
        success = ws.assign_commander(
            selected_war.id,
            selected_cmd.id,
            len(selected_legions),
            fleets
        )
        if success:
            print(f"\n✅ {selected_cmd.name} 指派至 {selected_war.name}")
            if selected_legions:
                legion_numbers = [l.number for l in selected_legions]
                assigned, msg = ms.assign_to_war(legion_numbers, selected_war.id, selected_cmd.id)
                print(f"   {msg}")
            return True
        else:
            print(f"❌ 指派失败")
            return False


class LegionsCommand(Command):
    """显示军团状态"""

    name = "legions"
    aliases = []
    description = "显示军团状态"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        ms = self.state.get_military_system()
        if not ms:
            print("军事系统未就绪")
            return False

        print(ms.get_military_summary())
        ms.display_legion_status()
        return True


class RecruitCommand(Command):
    """交互式征召军团"""

    name = "recruit"
    aliases = []
    description = "交互式征召军团"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _input_int(self, prompt: str, min_val: int = 1, max_val: Optional[int] = None) -> Optional[int]:
        try:
            val = int(input(prompt))
            if val < min_val:
                print(f"   ❌ 必须大于等于 {min_val}")
                return None
            if max_val is not None and val > max_val:
                print(f"   ❌ 必须小于等于 {max_val}")
                return None
            return val
        except ValueError:
            print("   ❌ 请输入有效数字")
            return None
        except KeyboardInterrupt:
            print("\n   操作取消")
            return None

    def execute(self, args: List[str]) -> bool:
        ms = self.state.get_military_system()
        if not ms:
            print("军事系统未就绪")
            return False

        terms = TerminologyService.get()
        available = ms.get_available_legions()

        if not available:
            print(f"没有可征召的军团")
            return False

        print(f"\n国库: {self.state.treasury} {terms.currency}")
        print(f"可征召军团: {len(available)}")
        print(f"征召费用: 10 {terms.currency} 每军团")

        print(f"\n模式: [1] 单军团  [2] 批量征召")
        mode = input("选择 (1-2): ").strip()

        if mode == "2":
            # 批量模式
            count = self._input_int(f"征召数量 (1-{len(available)}): ", 1, len(available))
            if count is None:
                return False
            total_cost = count * 10
            if self.state.treasury < total_cost:
                print(f"❌ 需要 {total_cost} {terms.currency}，当前 {self.state.treasury}")
                return False
            results = ms.recruit_multiple(count)
            success = sum(1 for _, s, _ in results if s)
            print(f"\n✅ 成功征召 {success}/{count} 军团")
            return True

        else:  # 默认单军团
            print(f"\n可征召军团:")
            for legion in available:
                print(f"  {legion.number}. {legion.name}")
            choice = self._input_int(f"选择军团编号 (1-10): ", 1, 10)
            if choice is None:
                return False
            success, msg = ms.recruit_legion(choice)
            status = "✅" if success else "❌"
            print(f"   {status} {msg}")
            return success


class DisbandCommand(Command):
    """交互式解散军团"""

    name = "disband"
    aliases = []
    description = "交互式解散军团"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _parse_indices(self, input_str: str, max_len: int) -> List[int]:
        """解析用户输入的索引，支持逗号分隔和 all"""
        if input_str.lower() == 'all':
            return list(range(max_len))
        try:
            indices = [int(x.strip()) - 1 for x in input_str.split(',')]
            return [i for i in indices if 0 <= i < max_len]
        except ValueError:
            return []

    def execute(self, args: List[str]) -> bool:
        ms = self.state.get_military_system()
        if not ms:
            print("军事系统未就绪")
            return False

        terms = TerminologyService.get()
        unassigned = [l for l in ms.get_active_legions() if l.war_id is None]

        if not unassigned:
            print(f"没有未指派的军团可解散")
            return False

        print(f"\n未指派军团:")
        for idx, legion in enumerate(unassigned, 1):
            vet = "⭐" if legion.is_veteran else ""
            print(f"  {idx}. {legion.name}{vet}")

        input_str = input(f"\n选择要解散的军团编号（逗号分隔，或输入 'all'）: ").strip()
        indices = self._parse_indices(input_str, len(unassigned))
        if not indices:
            print("❌ 无效选择")
            return False

        success_count = 0
        for i in indices:
            legion = unassigned[i]
            success, msg = ms.disband_legion(legion.number)
            if success:
                success_count += 1
                print(f"   ✅ {msg}")
            else:
                print(f"   ❌ {msg}")

        print(f"\n解散 {success_count}/{len(indices)} 军团")
        return success_count > 0