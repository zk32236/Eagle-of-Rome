# src/ui/debug_cli.py
"""
调试命令行界面 - 整改后版本

核心功能:
1. 初始化命令注册器
2. 主循环读取用户输入
3. 分发命令到注册器执行
4. 异常隔离，单条命令失败不影响CLI
"""

import sys
import os
from typing import List, Optional

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.sys_registry import CommandRegistry
from src.ui.commands.sys_help import HelpCommand
from src.ui.commands.sys_exit import ExitCommand


class DebugCLI:
    """调试命令行界面"""

    def __init__(self):
        """初始化CLI"""
        self.running = True
        self.state = None  # 暂不创建GameState，后续指令会添加

        # 初始化命令注册器
        commands_dir = os.path.join(os.path.dirname(__file__), "commands")
        print(f"[DEBUG] 命令目录: {commands_dir}")
        self.registry = CommandRegistry(commands_dir)

        # 打印发现的命令
        cmd_names = self.registry.get_command_names()
        print(f"[DEBUG] 发现的命令: {cmd_names}")

        # 为特殊命令设置回调
        self._setup_special_commands()

    def _setup_special_commands(self):
        """
        设置特殊命令的回调
        帮助命令需要注册器引用，退出命令需要退出回调
        """
        # 获取HelpCommand类并设置注册器
        help_info = self.registry.get_command_info("help")
        if help_info:
            # 注意：这里只是存储类引用，实际实例化时设置
            self._help_class = help_info['class']

        # 获取ExitCommand类并设置退出回调
        exit_info = self.registry.get_command_info("exit")
        if exit_info:
            self._exit_class = exit_info['class']

    def _create_command_instance(self, cmd_name: str):
        """
        创建命令实例并设置必要的回调

        Args:
            cmd_name: 命令名

        Returns:
            命令实例，如果命令不存在返回None
        """
        cmd_info = self.registry.get_command_info(cmd_name)
        if not cmd_info:
            return None

        cmd_class = cmd_info['class']
        instance = cmd_class(self.state)

        # 为特定命令设置回调
        if cmd_class.name == "help":
            instance.set_registry(self.registry)
        elif cmd_class.name == "exit":
            instance.set_exit_callback(self._stop)

        return instance

    def _stop(self):
        """设置退出标志"""
        self.running = False

    def run(self):
        """运行CLI主循环"""
        print("\n" + "=" * 60)
        print("   Eagle of Rome - Debug CLI (整改后版本)")
        print("=" * 60)
        print("输入 'help' 查看可用命令，'exit' 退出游戏")
        print()

        while self.running:
            try:
                # 读取用户输入
                cmd_input = input("> ").strip()

                # 跳过空输入
                if not cmd_input:
                    continue

                # 分割命令名和参数
                parts = cmd_input.split()
                cmd_name = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # 创建命令实例并执行
                cmd_instance = self._create_command_instance(cmd_name)

                if cmd_instance:
                    # 执行命令，根据返回值决定是否退出
                    result = cmd_instance.execute(args)
                    # 如果命令返回False且是退出命令，设置running=False
                    # 注意：ExitCommand已经通过回调设置了running=False
                    # 这里保留作为双重保障
                    if cmd_name in ["exit", "quit"] and not result:
                        self._stop()
                else:
                    print(f"未知命令: {cmd_name}")
                    print("输入 'help' 查看可用命令")

            except KeyboardInterrupt:
                print("\n使用 'exit' 命令退出游戏")
            except Exception as e:
                # 捕获所有异常，防止单条命令崩溃导致整个CLI退出
                print(f"发生未预期错误: {e}")
                import traceback
                traceback.print_exc()

    def shutdown(self):
        """关闭CLI（清理资源）"""
        self.running = False
        print("CLI已关闭")


def main():
    """CLI入口函数"""
    cli = DebugCLI()
    try:
        cli.run()
    finally:
        cli.shutdown()


if __name__ == "__main__":
    main()