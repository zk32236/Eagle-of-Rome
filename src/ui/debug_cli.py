# src/ui/debug_cli.py
"""
调试命令行界面 - 整改后版本（整合 GameState）
"""

import sys
import os
import traceback
import logging
import datetime


# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.sys_registry import CommandRegistry
from src.core.game_state import GameState


class Tee:
    """将输出同时写入文件和原始 stdout"""
    def __init__(self, filename, mode='a', encoding='utf-8'):
        self.file = open(filename, mode, encoding=encoding)
        self.stdout = sys.stdout

    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def close(self):
        self.file.close()
        sys.stdout = self.stdout


class DebugCLI:
    """调试命令行界面"""

    def __init__(self):
        """初始化CLI"""
        self.running = True
        self.state = GameState("data/config/game_config.json")

        # 初始化命令注册器
        commands_dir = os.path.join(os.path.dirname(__file__), "commands")
        self.registry = CommandRegistry(commands_dir)

        # 为特殊命令设置回调
        self._setup_special_commands()

    def _setup_special_commands(self):
        """
        设置特殊命令的回调
        帮助命令需要注册器引用，退出命令需要退出回调
        """
        help_info = self.registry.get_command_info("help")
        if help_info:
            self._help_class = help_info['class']

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
        """运行CLI主循环，同时将输出保存到日志文件"""
        # ---------- 设置 CLI 输出日志 ----------
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        cli_log_path = os.path.join(log_dir, f"cli_{timestamp}.log")
        tee = Tee(cli_log_path)
        sys.stdout = tee
        # ---------------------------------------

        try:
            # 自动加载默认场景
            print("\n🔄 自动加载默认场景...")
            self.registry.execute("load", self.state, [])

            print("输入 'help' 查看可用命令，'exit' 退出游戏")
            print()

            while self.running:
                try:
                    cmd_input = input("> ").strip()
                    if not cmd_input:
                        continue

                    parts = cmd_input.split()
                    cmd_name = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []

                    cmd_instance = self._create_command_instance(cmd_name)
                    if cmd_instance:
                        result = cmd_instance.execute(args)
                        if cmd_name in ["exit", "quit"] and not result:
                            self._stop()
                    else:
                        print(f"未知命令: {cmd_name}")
                        print("输入 'help' 查看可用命令")

                except EOFError:
                    print("\n输入流已关闭，退出。")
                    break
                except KeyboardInterrupt:
                    print("\n使用 'exit' 命令退出游戏")
                    continue
                except Exception as e:
                    # 获取当前状态信息
                    state_info = ""
                    if self.state and hasattr(self.state, 'turn') and self.state.turn:
                        turn_info = f"回合 {self.state.turn.turn_number}"
                        year_info = f"年份 {abs(self.state.turn.year)} BC"
                        state_info = f"{turn_info} {year_info}"
                    # 记录错误日志
                    if self.state and hasattr(self.state, 'log_event'):
                        tb_str = traceback.format_exc()
                        self.state.log_event(
                            f"未捕获异常: 命令 '{cmd_input}' - {str(e)}",
                            level=logging.ERROR,
                            extra={
                                "context": state_info,
                                "cmd": cmd_input,
                                "exception": str(e),
                                "traceback": tb_str
                            }
                        )
                    print(f"发生未预期错误: {e}")
                    traceback.print_exc()
        finally:
            # 恢复原始 stdout 并关闭文件
            sys.stdout = tee.stdout
            tee.close()
            print("CLI 输出日志已保存至:", cli_log_path)

    def shutdown(self):
        """关闭CLI"""
        self.running = False
        print("CLI已关闭")


def main():
    cli = DebugCLI()
    try:
        cli.run()
    finally:
        cli.shutdown()


if __name__ == "__main__":
    main()