# src/ui/commands/sys_exit.py
"""
Exit命令 - 退出游戏
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ExitCommand(Command):
    """退出游戏命令"""

    name = "exit"
    aliases = ["quit"]
    description = "退出游戏"

    def __init__(self, state: "GameState"):
        super().__init__(state)
        self._exit_callback = None

    def set_exit_callback(self, callback):
        """
        设置退出回调函数

        Args:
            callback: 无参数的回调函数，调用后应设置主循环退出标志
        """
        self._exit_callback = callback

    def execute(self, args: List[str]) -> bool:
        """
        执行退出命令

        Args:
            args: 命令参数（exit命令忽略参数）

        Returns:
            bool: 返回False表示请求退出主循环
        """
        print("感谢游玩 Eagle of Rome！再见！")

        # 如果设置了回调，调用回调设置退出标志
        if self._exit_callback:
            self._exit_callback()

        # 返回False表示请求退出
        return False