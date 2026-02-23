# src/ui/commands/func_status.py
"""
Status命令 - 显示当前游戏状态摘要
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command

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
        """
        执行status命令

        Args:
            args: 命令参数（无意义，忽略）

        Returns:
            bool: 始终返回 True
        """
        if not self.state:
            print("错误: 游戏状态未初始化")
            return False

        # 获取状态信息
        treasury = self.state.treasury
        living_count = len(self.state.get_living_members())
        faction_count = len(self.state.factions)
        turn_year = self.state.turn.year if self.state.turn else "未知"
        turn_num = self.state.turn.turn_number if self.state.turn else "未知"

        # 格式化输出
        print("\n" + "=" * 50)
        print("   📊 游戏状态摘要")
        print("=" * 50)
        print(f"   回合: 第 {turn_num} 年 ({abs(turn_year)} BC)")
        print(f"   国库: {treasury} 塔兰特")
        print(f"   存活人物: {living_count} 人")
        print(f"   派系数: {faction_count} 个")
        print("=" * 50)

        return True

def get_progress_bar(state, width=7):
    """生成进度条字符串，格式：[▓░░░░░░] 已执行/总数"""
    executed = len(state.executed_phases)
    total = 7  # 总阶段数
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"