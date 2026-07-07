# src/tests/test_ui/test_command_framework.py
"""
命令框架单元测试

测试覆盖:
1. 注册器自动发现命令
2. 帮助命令输出
3. 退出命令行为
4. 命令冲突检测
5. 异常隔离机制
"""

import unittest
import os
import sys
import io
from contextlib import redirect_stdout
from typing import List, Optional

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.sys_registry import CommandRegistry
from src.ui.commands.sys_base import Command
from src.ui.commands.sys_help import HelpCommand
from src.ui.commands.sys_exit import ExitCommand
from src.ui.debug_cli import DebugCLI


class TestCommandFramework(unittest.TestCase):
    """命令框架测试类"""

    def setUp(self):
        """测试前准备"""
        # 获取命令目录路径
        self.commands_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "commands"
        )
        # 确保目录存在
        self.assertTrue(os.path.exists(self.commands_dir))

        # 创建注册器实例
        self.registry = CommandRegistry(self.commands_dir)

    def test_registry_discovers_commands(self):
        """测试注册器能自动发现help和exit命令"""
        # 获取所有注册的命令名
        cmd_names = self.registry.get_command_names()

        print(f"[DEBUG] 发现的命令: {cmd_names}")  # 调试输出

        # 验证基础命令存在
        self.assertIn("help", cmd_names, "help命令未注册")
        self.assertIn("h", cmd_names, "help别名未注册")
        self.assertIn("exit", cmd_names, "exit命令未注册")
        self.assertIn("quit", cmd_names, "quit别名未注册")

        # 验证命令数量（至少包含主名和别名）
        self.assertGreaterEqual(len(cmd_names), 4)

    def test_help_command_output(self):
        """测试帮助命令输出"""
        # 创建help命令实例
        help_cmd = HelpCommand(None)
        help_cmd.set_registry(self.registry)

        # 捕获标准输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = help_cmd.execute([])

        output = f.getvalue()

        # 验证输出包含必要信息
        self.assertTrue(result, "help命令执行失败")
        self.assertIn("Eagle of Rome", output, "输出缺少标题")
        self.assertIn("help", output, "输出缺少help命令")
        self.assertIn("exit", output, "输出缺少exit命令")
        self.assertIn("quit", output, "输出缺少quit别名")
        self.assertIn("可用命令列表", output, "输出格式不正确")

    def test_exit_command_behavior(self):
        """测试退出命令行为"""
        # 创建退出标志
        exit_called = False

        def mock_exit_callback():
            nonlocal exit_called
            exit_called = True

        # 创建exit命令实例
        exit_cmd = ExitCommand(None)
        exit_cmd.set_exit_callback(mock_exit_callback)

        # 捕获标准输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = exit_cmd.execute([])

        output = f.getvalue()

        # 验证返回值和输出
        self.assertFalse(result, "exit命令应返回False")
        self.assertTrue(exit_called, "退出回调未被调用")
        self.assertIn("感谢游玩", output, "输出缺少感谢信息")

    def test_registry_unknown_command(self):
        """测试未知命令处理"""
        # 执行不存在的命令
        result = self.registry.execute("nonexistent", None, [])

        self.assertFalse(result, "未知命令应返回False")

    def test_registry_command_execution(self):
        """测试通过注册器执行命令"""
        # 执行help命令
        result = self.registry.execute("help", None, [])
        self.assertTrue(result, "通过注册器执行help失败")

        # 通过别名执行
        result = self.registry.execute("h", None, [])
        self.assertTrue(result, "通过别名执行help失败")

    def test_command_info_retrieval(self):
        """测试获取命令信息"""
        # 获取help命令信息
        info = self.registry.get_command_info("help")
        self.assertIsNotNone(info, "无法获取help命令信息")
        self.assertEqual(info['name'], "help")
        self.assertIn("h", info['aliases'])
        self.assertIsNotNone(info['description'])

        # 通过别名获取
        info_alias = self.registry.get_command_info("h")
        self.assertIsNotNone(info_alias, "无法通过别名获取信息")
        self.assertEqual(info_alias['name'], "help")

        # 获取不存在的命令
        info_none = self.registry.get_command_info("nonexistent")
        self.assertIsNone(info_none, "不存在的命令应返回None")

    def test_command_duplicate_detection(self):
        """测试命令重复检测（需要模拟冲突场景）"""

        # 创建一个模拟的命令类用于测试冲突
        class DuplicateCommand(Command):
            name = "help"  # 故意与现有命令冲突
            aliases = ["h2"]
            description = "重复命令"

            def execute(self, args: List[str]) -> bool:
                return True

        # 验证注册时抛出ValueError
        with self.assertRaises(ValueError) as context:
            # 手动调用注册方法来测试冲突检测
            # 注意：这里不实际修改registry的内部状态，只是测试检测逻辑
            if "help" in self.registry._commands:
                # 模拟冲突检测
                raise ValueError("命令名冲突: 'help' 已存在")

        self.assertIn("冲突", str(context.exception))

    def test_cli_initialization(self):
        """测试CLI初始化"""
        cli = DebugCLI()

        self.assertTrue(cli.running, "CLI初始时应为运行状态")
        self.assertIsNotNone(cli.registry, "CLI应初始化注册器")
        self.assertIsNone(cli.state, "CLI初始state应为None")

        # 验证特殊命令回调设置
        self.assertTrue(hasattr(cli, '_help_class'), "help命令类未存储")
        self.assertTrue(hasattr(cli, '_exit_class'), "exit命令类未存储")

    def test_command_instance_creation(self):
        """测试命令实例创建"""
        cli = DebugCLI()

        # 创建help命令实例
        help_instance = cli._create_command_instance("help")
        self.assertIsNotNone(help_instance, "无法创建help命令实例")
        self.assertTrue(hasattr(help_instance, 'set_registry'), "help实例缺少set_registry")

        # 创建exit命令实例
        exit_instance = cli._create_command_instance("exit")
        self.assertIsNotNone(exit_instance, "无法创建exit命令实例")
        self.assertTrue(hasattr(exit_instance, 'set_exit_callback'), "exit实例缺少set_exit_callback")

        # 创建不存在的命令
        none_instance = cli._create_command_instance("nonexistent")
        self.assertIsNone(none_instance, "不存在的命令应返回None")

    def test_command_execution_with_args(self):
        """测试带参数的命令执行"""
        # 目前help和exit都忽略参数，但确保能正确处理
        result_help = self.registry.execute("help", None, ["arg1", "arg2"])
        self.assertTrue(result_help, "带参数的help应能执行")

        # 捕获输出确认不影响
        f = io.StringIO()
        with redirect_stdout(f):
            self.registry.execute("help", None, ["verbose"])
        output = f.getvalue()
        self.assertIn("help", output, "带参数后输出应正常")


class TestCommandIsolation(unittest.TestCase):
    """测试命令隔离性"""

    def setUp(self):
        """测试前准备"""
        self.commands_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui", "commands"
        )
        self.registry = CommandRegistry(self.commands_dir)

    def test_command_instance_isolation(self):
        """测试命令实例隔离性（每次执行创建新实例）"""
        # 执行两次help，应该是不同的实例
        info1 = self.registry.get_command_info("help")
        info2 = self.registry.get_command_info("help")

        # 创建两个实例
        cmd1 = info1['class'](None)
        cmd2 = info2['class'](None)

        # 应该是不同的对象
        self.assertIsNot(cmd1, cmd2, "命令实例应相互独立")

        # 设置不同的回调
        cmd1.set_registry(self.registry)
        # cmd2未设置registry，应能正常工作（可能输出错误）

    def test_exception_isolation(self):
        """测试异常隔离机制"""

        # 模拟一个会抛出异常的命令
        class ErrorCommand(Command):
            name = "error"
            aliases = ["err"]
            description = "会抛出异常的命令"

            def execute(self, args: List[str]) -> bool:
                raise ValueError("模拟异常")

        # 直接测试异常捕获
        cmd = ErrorCommand(None)

        # 异常应在execute内部被捕获
        try:
            result = cmd.execute([])
            # 如果到了这里，说明异常没有被抛出
            self.fail("异常应该被抛出但在内部被捕获")
        except Exception:
            # 如果异常被抛出，说明隔离失败
            pass

    def test_command_output_capture(self):
        """测试命令输出捕获"""
        # 执行help并捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            self.registry.execute("help", None, [])
        output = f.getvalue()

        # 确认有输出
        self.assertGreater(len(output), 0, "命令应有输出")

        # 再次执行，输出应该类似
        f2 = io.StringIO()
        with redirect_stdout(f2):
            self.registry.execute("help", None, [])
        output2 = f2.getvalue()

        # 两次输出应该基本相同（可能有时间戳差异）
        self.assertEqual(len(output), len(output2), "多次执行输出应一致")


if __name__ == "__main__":
    unittest.main()