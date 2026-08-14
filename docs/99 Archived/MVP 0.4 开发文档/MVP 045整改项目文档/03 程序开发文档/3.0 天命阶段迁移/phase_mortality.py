# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - 处理人物死亡
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MortalityCommand(Command):
    """天命阶段命令"""

    name = "mortality"
    aliases = ["m"]
    description = "执行天命阶段 (Mortality Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行天命阶段

        Args:
            args: 命令参数（无意义，忽略）

        Returns:
            bool: 执行成功返回 True，失败返回 False
        """
        # 检查阶段是否已执行
        if self.state.is_phase_executed("mortality"):
            print("⚠️ 天命阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(self.state.turn.year)} BC) ---")

        deaths_this_turn = []
        living_count = len(self.state.get_living_members())

        # 计算抽取数量
        mortality_rules = self.state.config.get("mortality_rules", {})
        base = mortality_rules.get("base_draw_count", 1)
        per = mortality_rules.get("draw_per_members", 5)
        max_draws = mortality_rules.get("max_draws", 3)
        draw_count = max(1, min(max_draws, living_count // per))

        print(f"Drawing {draw_count} number(s) from pool (1-300)...")
        print(f"Current living: {living_count}")

        for i in range(draw_count):
            drawn_number = self.state.draw_mortality_number()
            print(f"  [Draw {i + 1}] Number {drawn_number}...")

            member = self.state.get_living_member(drawn_number)

            if member:
                self._process_death(member)
                deaths_this_turn.append(member)
            else:
                print(f"     -> No member assigned (safe)")

        # 记录事件
        if deaths_this_turn:
            names = ", ".join([m.name for m in deaths_this_turn])
            self.state.log_event(f"💀 {terms.nobles} died: {names}")
        else:
            self.state.log_event(f"✅ No deaths this year")

        # 设置当前阶段（兼容旧逻辑）
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "mortality"

        # 标记阶段已执行
        self.state.mark_phase_executed("mortality")

        return True

    def _process_death(self, member):
        """处理单个死亡人物"""
        # 通过 GameState 的方法标记死亡
        self.state.mark_member_dead(member.id)

        # 获取派系信息并打印
        faction = self.state.get_faction(member.faction_id)
        fname = faction.name if faction else "Unknown"
        print(f"     -> 💀 {member.name} of {fname} has died!")

        if faction:
            remaining = len(faction.get_members(self.state))
            terms = TerminologyService.get()
            print(f"        {fname} has {remaining} {terms.nobles.lower()} remaining")