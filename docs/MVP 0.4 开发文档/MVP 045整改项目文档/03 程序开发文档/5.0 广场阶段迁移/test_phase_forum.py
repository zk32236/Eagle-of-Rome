# src/tests/test_commands/test_phase_forum.py
"""
广场阶段命令单元测试
"""

import unittest
import sys
import os
from unittest.mock import patch
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_forum import ForumCommand
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure
from src.core.entities.contract import Contract


class TestForumCommand(unittest.TestCase):
    """广场阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        self.state = GameState.create_for_testing({})
        # 设置回合
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

    def test_execute_success(self):
        """测试成功执行广场阶段"""
        cmd = ForumCommand(self.state)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Forum Phase", output)

        # 验证 Curia 中增加了人物
        self.assertGreater(len(self.state.curia.get_all_available()), 0)

        # 验证合同列表增加了
        self.assertGreater(len(self.state.contracts), 0)

        # 验证阶段标记
        self.assertTrue(self.state.is_phase_executed("forum"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = ForumCommand(self.state)
        cmd.execute([])  # 第一次执行

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result)
        self.assertIn("广场阶段在本回合已执行过", output)

    @patch('random.randint')
    def test_generate_figures(self, mock_randint):
        """测试新人物生成逻辑"""
        # 第一个 randint 用于决定生成人数（返回2）
        # 后续所有 randint 返回固定值 30，避免 StopIteration
        mock_randint.side_effect = [2] + [30] * 100

        cmd = ForumCommand(self.state)
        new_figures = cmd._generate_new_figures()

        self.assertEqual(len(new_figures), 2)

        # 验证人物已添加到 members 和 curia
        self.assertIn(new_figures[0].id, self.state.members)
        self.assertIn(new_figures[1].id, self.state.members)
        self.assertEqual(len(self.state.curia.get_all_available()), 2)

    @patch('random.randint')
    def test_generate_contracts(self, mock_randint):
        """测试合同生成逻辑"""
        # 控制随机数以生成特定的成本和利润
        mock_randint.side_effect = [30, 15, 40]  # tax_cost, tax_profit, budget

        cmd = ForumCommand(self.state)
        new_contracts = cmd._generate_contracts()

        self.assertEqual(len(new_contracts), 2)
        self.assertEqual(new_contracts[0].contract_type.value, "tax_farming")
        self.assertEqual(new_contracts[0].base_cost, 30)
        self.assertEqual(new_contracts[0].expected_profit, 15)

        self.assertEqual(new_contracts[1].contract_type.value, "public_works")
        self.assertEqual(new_contracts[1].base_cost, 40)

        # 验证合同已添加到 state.contracts
        self.assertEqual(len(self.state.contracts), 2)

    def test_curia_display(self):
        """验证 Curia 显示输出包含人物信息"""
        # 先手动添加一个人物到 Curia
        fig = Figure(id=999, name="Test Figure", faction_id=None)
        self.state.curia.add_figure(fig)

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._display_curia(TerminologyService.get())

        output = f.getvalue()
        self.assertIn("Test Figure", output)
        self.assertIn("ID:999", output)

    def test_contract_display(self):
        """验证合同显示输出包含合同信息"""
        # 先手动添加一个待决合同
        contract = Contract.create_tax_farming(1, "测试行省", 50, 20)
        contract._created_turn = 1
        self.state.contracts.append(contract)

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._display_contracts(TerminologyService.get())

        output = f.getvalue()
        self.assertIn("测试行省", output)
        self.assertIn("ID:1", output)


if __name__ == "__main__":
    unittest.main()