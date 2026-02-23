# src/ui/commands/func_turn_control.py
"""
回合控制命令：next、turn、step
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService

# 导入所有阶段命令类，用于 turn 和 step 命令执行阶段
from src.ui.commands.phase_mortality import MortalityCommand
from src.ui.commands.phase_revenue import RevenueCommand
from src.ui.commands.phase_forum import ForumCommand
from src.ui.commands.phase_population import PopulationCommand
from src.ui.commands.phase_senate import SenateCommand
from src.ui.commands.phase_combat import CombatCommand
from src.ui.commands.phase_resolution import ResolutionCommand

if TYPE_CHECKING:
    from src.core.game_state import GameState


# 阶段顺序（与原 debug_cli.py 保持一致）
PHASE_SEQUENCE = [
    "mortality",
    "revenue",
    "forum",
    "population",
    "senate",
    "combat",
    "resolution"
]

# 阶段命令类映射
PHASE_COMMAND_CLASSES = {
    "mortality": MortalityCommand,
    "revenue": RevenueCommand,
    "forum": ForumCommand,
    "population": PopulationCommand,
    "senate": SenateCommand,
    "combat": CombatCommand,
    "resolution": ResolutionCommand,
}


class NextCommand(Command):
    """推进到下一年"""

    name = "next"
    aliases = ["n"]
    description = "推进到下一年。用法: next [force] (force 可跳过未完成阶段检查)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _get_missing_phases(self) -> List[str]:
        """返回未执行的阶段列表"""
        missing = []
        for phase in PHASE_SEQUENCE:
            if not self.state.is_phase_executed(phase):
                missing.append(phase)
        return missing

    def _show_turn_summary(self):
        """显示回合进度摘要（原 _show_turn_summary 简化版）"""
        terms = TerminologyService.get()
        executed = self.state.executed_phases
        year = abs(self.state.turn.year)

        print(f"\n📅 Year {year} BC:")
        print(f"   Completed: {len(executed)}/7 phases")

        # 简单显示已执行阶段
        for phase in PHASE_SEQUENCE:
            status = "✓" if phase in executed else "○"
            print(f"      {status} {getattr(terms, f'phase_{phase}', phase)}")

        if len(executed) == 7:
            print(f"   ✅ Ready for 'next'")
        else:
            print(f"   ⏳ {7 - len(executed)} remaining")

    def execute(self, args: List[str]) -> bool:
        """
        执行 next 命令
        """
        force = any(arg.lower() == "force" for arg in args)

        # 检查决议阶段是否已执行（除非 force 跳过）
        if not self.state.is_phase_executed("resolution") and not force:
            print("⛔ 必须先执行决议阶段 (resolution) 才能进入下一年")
            print("   使用 'next force' 强制推进，或执行缺失阶段")
            return False

        missing = self._get_missing_phases()
        if missing and not force:
            terms = TerminologyService.get()
            missing_display = [getattr(terms, f"phase_{m}", m) for m in missing]
            print(f"\n⛔ 无法推进，缺失阶段: {', '.join(missing_display)}")
            print("   使用 'next force' 强制推进，或执行缺失阶段")
            return False

        if missing and force:
            missing_names = ', '.join(missing)
            print(f"\n⚠️ 强制推进 - 跳过: {missing_names}")

        self.state.advance_year()
        print(f"已推进至 {abs(self.state.turn.year)} BC")
        self._show_turn_summary()
        return True


class TurnCommand(Command):
    """自动执行完整回合（依次执行所有7个阶段）"""

    name = "turn"
    aliases = []
    description = "自动执行完整回合（依次执行所有7个阶段）"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _execute_phase(self, phase_name: str) -> bool:
        """执行单个阶段，返回是否成功"""
        cmd_class = PHASE_COMMAND_CLASSES.get(phase_name)
        if not cmd_class:
            print(f"❌ 未知阶段: {phase_name}")
            return False
        cmd = cmd_class(self.state)
        return cmd.execute([])

    def execute(self, args: List[str]) -> bool:
        """
        执行 turn 命令
        """
        executed = set(self.state.executed_phases)
        if executed == set(PHASE_SEQUENCE):
            print("⚠️ 所有阶段已执行！使用 'next' 推进回合。")
            return True

        terms = TerminologyService.get()
        print(f"\n{'#' * 60}")
        print(f" 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC)")
        print(f" 术语: {terms.assembly}/{terms.nobles}/{terms.currency}")
        print(f"{'#' * 60}")

        # 按顺序执行未执行阶段
        for i, phase in enumerate(PHASE_SEQUENCE, 1):
            if phase in executed:
                continue

            display_name = getattr(terms, f"phase_{phase}", phase)
            print(f"\n[{i}/7] {display_name}...")

            success = self._execute_phase(phase)
            if not success:
                print(f"❌ 阶段 {phase} 执行失败，中断")
                return False

        print(f"\n{'#' * 60}")
        print(f" ✅ 回合完成 - 所有7个阶段已执行")
        print(f"{'#' * 60}")
        return True


class StepCommand(Command):
    """逐步执行回合，每阶段后暂停等待输入"""

    name = "step"
    aliases = []
    description = "逐步执行回合，每阶段后暂停等待输入"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _execute_phase(self, phase_name: str) -> bool:
        cmd_class = PHASE_COMMAND_CLASSES.get(phase_name)
        if not cmd_class:
            print(f"❌ 未知阶段: {phase_name}")
            return False
        cmd = cmd_class(self.state)
        return cmd.execute([])

    def execute(self, args: List[str]) -> bool:
        """
        执行 step 命令
        """
        executed = set(self.state.executed_phases)
        if executed == set(PHASE_SEQUENCE):
            print("⚠️ 所有阶段已执行！使用 'next' 推进回合。")
            return True

        terms = TerminologyService.get()
        print(f"\n{'#' * 60}")
        print(f" 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC)")
        print(f"{'#' * 60}")

        for i, phase in enumerate(PHASE_SEQUENCE, 1):
            if phase in executed:
                continue

            display_name = getattr(terms, f"phase_{phase}", phase)
            print(f"\n[{i}/7] {display_name}...")

            success = self._execute_phase(phase)
            if not success:
                print(f"❌ 阶段 {phase} 执行失败，中断")
                return False

            # 暂停，等待用户按 Enter
            try:
                input("   按 Enter 继续...")
            except KeyboardInterrupt:
                print("\n⚠️ 用户中断，终止逐步执行")
                return False
            except Exception:
                pass  # 其他异常忽略

        print(f"\n{'#' * 60}")
        print(f" ✅ 回合完成 - 所有7个阶段已执行")
        print(f"{'#' * 60}")
        return True