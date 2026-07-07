# src/tests/test_integration/test_cli_basic.py
"""
集成测试：CLI 基本命令交互
验证 load 和 status 命令的正确性
使用动态导入绕过包导入问题
"""

import unittest
import sys
import os
import io
from contextlib import redirect_stdout
import importlib.util
from src.core.i18n import i18n

# 在测试执行前加载 i18n 中文文本
i18n.load("zh-CN")

# 获取项目根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))

# ===== 动态导入 game_state =====
game_state_path = os.path.join(project_root, 'src', 'core', 'game_state.py')
game_state_spec = importlib.util.spec_from_file_location("game_state", game_state_path)
game_state_module = importlib.util.module_from_spec(game_state_spec)
game_state_spec.loader.exec_module(game_state_module)
GameState = game_state_module.GameState

# ===== 动态导入 func_load =====
func_load_path = os.path.join(project_root, 'src', 'ui', 'commands', 'func_load.py')
func_load_spec = importlib.util.spec_from_file_location("func_load", func_load_path)
func_load_module = importlib.util.module_from_spec(func_load_spec)
func_load_spec.loader.exec_module(func_load_module)
LoadCommand = func_load_module.LoadCommand

# ===== 动态导入 func_status =====
func_status_path = os.path.join(project_root, 'src', 'ui', 'commands', 'func_status.py')
func_status_spec = importlib.util.spec_from_file_location("func_status", func_status_path)
func_status_module = importlib.util.module_from_spec(func_status_spec)
func_status_spec.loader.exec_module(func_status_module)
StatusCommand = func_status_module.StatusCommand


class TestCLIIntegration(unittest.TestCase):
    """CLI 集成测试"""

    def setUp(self):
        """每个测试前创建新的游戏状态"""
        self.state = GameState()

    def test_load_and_status(self):
        """测试 load 后 status 能正确显示加载的数据"""
        from src.core.i18n import i18n
        i18n.load("zh-CN", force=True)  # 强制重新加载

        # 执行 load 命令（使用默认场景名）
        load_cmd = LoadCommand(self.state)
        result = load_cmd.execute([])
        self.assertTrue(result, "load 命令应返回 True")

        # 验证状态已被填充
        self.assertEqual(len(self.state._members), 18, "应加载 18 个人物")
        self.assertEqual(len(self.state._factions), 3, "应加载 3 个派系")
        self.assertEqual(self.state._treasury, 100, "国库应为 100")

        # 执行 status 命令并捕获输出
        status_cmd = StatusCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = status_cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result, "status 命令应返回 True")
        self.assertIn("国库: 100", output, "status 输出应包含国库信息")
        self.assertIn("存活人物: 18", output, "status 输出应包含人物数量")

    def test_load_twice(self):
        """测试两次加载，第二次应覆盖第一次的状态"""
        # 第一次加载
        load_cmd = LoadCommand(self.state)
        load_cmd.execute([])

        # 修改国库以模拟第一次加载后的变化（但不应影响第二次加载）
        self.state._treasury = 200
        self.assertEqual(self.state._treasury, 200, "国库应被修改为 200")

        # 第二次加载（应重置为 100）
        result = load_cmd.execute([])
        self.assertTrue(result, "第二次 load 应成功")
        self.assertEqual(self.state._treasury, 100, "第二次加载后国库应重置为 100")
        self.assertEqual(len(self.state._members), 18, "第二次加载后人物数应为 18")

    def test_load_with_nonexistent_file(self):
        """测试加载不存在的文件应使用默认配置并返回 True"""
        # 先加载一次正常数据
        load_cmd = LoadCommand(self.state)
        load_cmd.execute([])
        original_treasury = self.state._treasury

        # 尝试加载不存在的文件
        result = load_cmd.execute(["nonexistent.json"])
        self.assertTrue(result, "加载不存在文件应返回 True")  # 改为 True

        # 状态应变为默认配置（国库重置为100，人物18）
        self.assertEqual(self.state._treasury, 100, "失败后国库应重置为 100")
        self.assertEqual(len(self.state._members), 18, "人物数应变为 18")


if __name__ == "__main__":
    unittest.main()