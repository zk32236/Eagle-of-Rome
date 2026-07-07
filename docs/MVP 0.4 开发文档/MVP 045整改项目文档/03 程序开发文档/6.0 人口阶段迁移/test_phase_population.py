# src/tests/test_commands/test_phase_population.py
"""
人口阶段命令单元测试
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
import io
from contextlib import redirect_stdout
import random

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_population import PopulationCommand
from src.core.localization import TerminologyService


class TestPopulationCommand(unittest.TestCase):
    """人口阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        self.state = GameState.create_for_testing({})
        # 设置回合
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

    def _setup_mock_military_system(self, active_legions=5, unassigned_legions=2, available_legions=3):
        """创建并设置模拟的军事系统"""
        mock_ms = MagicMock()
        # 模拟军团列表（使用简单的 MagicMock 对象）
        mock_legion = MagicMock()
        mock_legion.number = 1
        mock_legion.name = "Legio I"

        mock_ms.get_active_legions.return_value = [mock_legion] * active_legions
        mock_ms.get_unassigned_legions.return_value = [mock_legion] * unassigned_legions
        mock_ms.get_available_legions.return_value = [mock_legion] * available_legions
        mock_ms.disband_legion.return_value = (True, "Disbanded")

        self.state._military_system = mock_ms
        return mock_ms

    def test_execute_success(self):
        """测试成功执行人口阶段"""
        self._setup_mock_military_system()
        self.state._treasury = 100

        cmd = PopulationCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Population Phase", output)
        self.assertIn("State of the Republic", output)

        # 验证阶段标记
        self.assertTrue(self.state.is_phase_executed("population"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = PopulationCommand(self.state)
        cmd.execute([])  # 第一次执行

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result)
        self.assertIn("人口阶段在本回合已执行过", output)

    def test_republic_state_calculation_calm(self):
        """测试国库充足且无战争时状态为 Calm"""
        self.state._treasury = 200
        # 模拟无战争
        with patch.object(self.state, 'get_active_wars', return_value=[]):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)

        self.assertEqual(state_name, terms.state_calm)

    def test_republic_state_calculation_uneasy(self):
        """测试国库低于100但无战争时状态为 Uneasy"""
        self.state._treasury = 80
        with patch.object(self.state, 'get_active_wars', return_value=[]):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)

        self.assertEqual(state_name, terms.state_uneasy)

    def test_republic_state_calculation_tense(self):
        """测试国库低于50且有战争时状态为 Tense"""
        self.state._treasury = 40
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)

        self.assertEqual(state_name, terms.state_tense)

    def test_republic_state_calculation_bad(self):
        """测试国库为负且有战争时状态为 Bad"""
        self.state._treasury = -10
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)

        self.assertEqual(state_name, terms.state_bad)

    def test_legion_disbandment_bad_state(self):
        """测试 Bad 状态时强制解散一半军团"""
        # 设置活跃军团 6 个，未指派军团 3 个（确保足够解散）
        mock_ms = self._setup_mock_military_system(active_legions=6, unassigned_legions=3)
        self.state._treasury = -10
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            cmd._process_legion_disbandment(terms, terms.state_bad)

        # 验证解散了 3 个军团（6//2）
        self.assertEqual(mock_ms.disband_legion.call_count, 3)

    def test_legion_disbandment_tense_state(self):
        """测试 Tense 状态时建议解散"""
        mock_ms = self._setup_mock_military_system(active_legions=6, unassigned_legions=2)
        self.state._treasury = 40
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()

            f = io.StringIO()
            with redirect_stdout(f):
                cmd._process_legion_disbandment(terms, terms.state_tense)

            output = f.getvalue()
            self.assertIn("Consider disbanding unassigned", output)

        # 验证未调用解散
        mock_ms.disband_legion.assert_not_called()

    def test_legion_disbandment_calm_state(self):
        """测试 Calm 状态时显示可征召军团"""
        mock_ms = self._setup_mock_military_system(active_legions=4, available_legions=3)
        self.state._treasury = 200
        with patch.object(self.state, 'get_active_wars', return_value=[]):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()

            f = io.StringIO()
            with redirect_stdout(f):
                cmd._process_legion_disbandment(terms, terms.state_calm)

            output = f.getvalue()
            self.assertIn("available for recruitment", output)

        mock_ms.disband_legion.assert_not_called()

    @patch('random.random')
    def test_population_events_triggered(self, mock_random):
        """测试人口事件触发（20%概率）"""
        mock_random.return_value = 0.1  # <0.2，触发事件

        cmd = PopulationCommand(self.state)
        terms = TerminologyService.get()

        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_population_events(terms)

        output = f.getvalue()
        self.assertIn("📢", output)

    @patch('random.random')
    def test_population_events_not_triggered(self, mock_random):
        """测试人口事件未触发"""
        mock_random.return_value = 0.3  # >0.2，不触发事件

        cmd = PopulationCommand(self.state)
        terms = TerminologyService.get()

        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_population_events(terms)

        output = f.getvalue()
        self.assertIn("No significant events", output)


if __name__ == "__main__":
    unittest.main()