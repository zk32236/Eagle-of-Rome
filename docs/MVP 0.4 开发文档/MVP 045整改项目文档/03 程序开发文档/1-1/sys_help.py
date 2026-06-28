# src/ui/commands/sys_help.py
"""
Help命令 - 显示所有可用命令的帮助信息
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command

if TYPE_CHECKING:
    from core.game_state import GameState


class HelpCommand(Command):
    """显示帮助信息命令"""

    name = "help"
    aliases = ["h"]
    description = "显示所有可用命令的帮助信息"

    def __init__(self, state: "GameState"):
        super().__init__(state)
        # 注意：registry 将在执行时从外部传入，不能在这里依赖
        self._registry = None

    def set_registry(self, registry):
        """设置命令注册器引用（由CLI在调用时设置）"""
        self._registry = registry

    def execute(self, args: List[str]) -> bool:
        """
        执行help命令，显示所有命令的帮助信息

        Args:
            args: 命令参数（help命令忽略参数）

        Returns:
            bool: 始终返回True
        """
        if not self._registry:
            print("错误: 命令注册器未设置")
            return False

        print("\n" + "=" * 60)
        print("   Eagle of Rome - 可用命令列表")
        print("=" * 60)

        # 获取所有命令名，按名称排序
        cmd_names = self._registry.get_command_names()
        # 去重并只显示主命令名（避免显示别名重复）
        main_commands = {}
        for name in cmd_names:
            info = self._registry.get_command_info(name)
            if info and info['name'] not in main_commands:
                main_commands[info['name']] = info

        # 按命令名排序
        sorted_commands = sorted(main_commands.values(), key=lambda x: x['name'])

        # 计算最大命令名长度用于对齐
        max_name_len = max(len(info['name']) for info in sorted_commands) if sorted_commands else 0

        for cmd_info in sorted_commands:
            name = cmd_info['name']
            aliases = cmd_info['aliases']
            description = cmd_info['description']

            # 格式化别名显示
            alias_str = f"(别名: {', '.join(aliases)})" if aliases else " " * 12

            # 对齐输出
            print(f"  {name:<{max_name_len}}  {alias_str:<15}  {description}")

        print("=" * 60)
        print("输入 'exit' 或 'quit' 退出游戏")
        return True