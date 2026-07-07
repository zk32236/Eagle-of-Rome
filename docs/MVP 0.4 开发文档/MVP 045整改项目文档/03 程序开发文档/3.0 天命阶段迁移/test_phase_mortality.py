# src/tests/test_commands/test_phase_mortality.py
"""
天命阶段命令单元测试
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_mortality import MortalityCommand


class TestMortalityCommand(unittest.TestCase):
    """天命阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        # 使用测试配置创建实例
        test_config = {
            "mortality_rules": {
                "base_draw_count": 1,
                "draw_per_members": 5,
                "max_draws": 3
            }
        }
        self.state = GameState.create_for_testing(test_config)

        # 添加一些测试人物
        self._add_test_figures()

    def _add_test_figures(self):
        """添加测试人物到 GameState"""
        # 创建两个派系
        from src.core.entities.entities import Faction
        from src.core.entities.figure import Figure

        faction1 = Faction(id="senate", name="元老院派")
        faction2 = Faction(id="populares", name="平民派")
        self.state.add_faction(faction1)
        self.state.add_faction(faction2)

        # 创建人物
        fig1 = Figure(id=1, name="Marcus Brutus", faction_id="senate", age=40)
        fig1.is_dead = False
        fig2 = Figure(id=2, name="Gaius Marius", faction_id="populares", age=35)
        fig2.is_dead = False
        fig3 = Figure(id=3, name="Lucius Sulla", faction_id="senate", age=45)
        fig3.is_dead = False

        self.state.add_member(fig1)
        self.state.add_member(fig2)
        self.state.add_member(fig3)

        # 更新派系成员列表
        faction1.member_ids = [1, 3]
        faction2.member_ids = [2]

        # 设置回合
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

    def test_execute_success(self):
        """测试成功执行天命阶段"""
        cmd = MortalityCommand(self.state)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Mortality Phase", output)
        self.assertIn("Drawing", output)

        # 验证阶段被标记为已执行
        self.assertTrue(self.state.is_phase_executed("mortality"))

    @patch('src.core.game_state.GameState.draw_mortality_number')
    def test_draw_logic_death(self, mock_draw):
        """测试抽取逻辑：抽到存活人物应死亡"""
        # 模拟抽取到 ID 2 (Gaius Marius)
        mock_draw.side_effect = [2]  # 第一次抽取返回2

        cmd = MortalityCommand(self.state)

        # 执行命令前人物存活
        self.assertFalse(self.state.get_member(2).is_dead)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        # 验证人物死亡
        self.assertTrue(self.state.get_member(2).is_dead)
        self.assertIn("has died", output)
        # 验证事件记录
        self.assertTrue(any("died" in msg for msg in self.state.event_log))

    @patch('src.core.game_state.GameState.draw_mortality_number')
    def test_draw_logic_safe(self, mock_draw):
        """测试抽取逻辑：抽到未分配号码应安全"""
        # 模拟抽取到 ID 99 (不存在)
        mock_draw.side_effect = [99]

        cmd = MortalityCommand(self.state)

        # 所有人物初始存活
        for mid in [1, 2, 3]:
            self.assertFalse(self.state.get_member(mid).is_dead)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("No member assigned (safe)", output)
        # 验证无人死亡
        for mid in [1, 2, 3]:
            self.assertFalse(self.state.get_member(mid).is_dead)

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = MortalityCommand(self.state)

        # 第一次执行
        result1 = cmd.execute([])
        self.assertTrue(result1)

        # 第二次执行（同一回合）
        f = io.StringIO()
        with redirect_stdout(f):
            result2 = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result2)
        self.assertIn("本回合已执行", output)

    def test_no_members(self):
        """测试没有存活人物时的边界情况"""
        # 清空所有人物的存活状态
        for mid in list(self.state.members.keys()):
            self.state.get_member(mid).is_dead = True

        cmd = MortalityCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)  # 应该仍然成功执行，只是无人死亡
        self.assertIn("Drawing 1 number(s)", output)  # 至少抽取1个
        # 可能抽到号码但无对应存活人物，输出 safe

    def test_multiple_draws(self):
        """测试多次抽取（根据人数计算draw_count）"""
        # 创建新的测试配置，使 draw_per_members = 1，这样存活3人应抽取3次
        test_config = {
            "mortality_rules": {
                "base_draw_count": 1,
                "draw_per_members": 1,  # 每1人抽取1次，3人抽3次
                "max_draws": 3
            }
        }
        # 创建独立的 GameState 实例
        state = GameState.create_for_testing(test_config)

        # 添加测试人物（与 setUp 相同）
        from src.core.entities.entities import Faction
        from src.core.entities.figure import Figure

        faction1 = Faction(id="senate", name="元老院派")
        faction2 = Faction(id="populares", name="平民派")
        state.add_faction(faction1)
        state.add_faction(faction2)

        fig1 = Figure(id=1, name="Marcus Brutus", faction_id="senate", age=40)
        fig1.is_dead = False
        fig2 = Figure(id=2, name="Gaius Marius", faction_id="populares", age=35)
        fig2.is_dead = False
        fig3 = Figure(id=3, name="Lucius Sulla", faction_id="senate", age=45)
        fig3.is_dead = False

        state.add_member(fig1)
        state.add_member(fig2)
        state.add_member(fig3)

        faction1.member_ids = [1, 3]
        faction2.member_ids = [2]

        from src.core.entities.entities import GameTurn
        state.turn = GameTurn(turn_number=1, year=-264)

        # 执行命令
        cmd = MortalityCommand(state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Drawing 3 number(s)", output)

    def test_phase_marking(self):
        """验证阶段标记功能"""
        self.assertFalse(self.state.is_phase_executed("mortality"))

        cmd = MortalityCommand(self.state)
        cmd.execute([])

        self.assertTrue(self.state.is_phase_executed("mortality"))


if __name__ == "__main__":
    unittest.main()