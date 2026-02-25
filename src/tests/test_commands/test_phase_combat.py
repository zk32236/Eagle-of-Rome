# src/tests/test_commands/test_phase_combat.py
"""
战斗阶段命令单元测试
"""

import unittest
import sys
import os
import random
from unittest.mock import MagicMock, patch, call
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_combat import CombatCommand
from src.core.entities.war import War, WarStatus
from src.core.entities.legion import Legion, LegionStatus
from src.core.entities.figure import Figure




class TestCombatCommand(unittest.TestCase):
    """战斗阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {}
        self.state = GameState.create_for_testing(test_config)

        # ===== 新增：设置回合 =====
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

        # ===== 新增：标记 senate 阶段已执行 =====
        self.state.mark_phase_executed("senate")

        # 创建模拟的战争系统
        self.mock_war_system = MagicMock()
        self.state._war_system = self.mock_war_system

        # 创建模拟的军事系统
        self.mock_military_system = MagicMock()
        self.state._military_system = self.mock_military_system

        # 设置回合
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

        # 创建测试人物（用作指挥官）
        self.commander = Figure(id=1, name="Test Commander", faction_id="senate", age=40)
        self.commander.military = 5
        self.commander.influence = 10
        self.state.add_member(self.commander)

    def _create_mock_war(self, war_id="war1", name="Test War", strength=5,
                         commander_id=1, legions_assigned=2, fleets_assigned=0,
                         naval_support_required=False):
        """创建模拟的战争对象"""
        war = MagicMock(spec=War)
        war.id = war_id
        war.name = name
        war.strength = strength
        war.commander_id = commander_id
        war.legions_assigned = legions_assigned
        war.fleets_assigned = fleets_assigned
        war.naval_support_required = naval_support_required
        war.status = WarStatus.ACTIVE
        war.duration = 1

        # 方法模拟
        war.get_total_strength.return_value = strength
        war.get_naval_strength_required.return_value = 3 if naval_support_required else 0
        war.is_disaster_roll.return_value = False
        war.is_standoff_roll.return_value = False
        war.report_commander_casualty = MagicMock()
        return war

    def _create_mock_legion(self, number=1, is_veteran=False):
        """创建模拟的军团对象"""
        legion = MagicMock(spec=Legion)
        legion.number = number
        legion.name = f"Legio {number}"
        legion.is_veteran = is_veteran
        legion.status = LegionStatus.ACTIVE
        legion.get_combat_strength.return_value = 2 + (1 if is_veteran else 0)
        legion.promote_to_veteran = MagicMock()
        legion.recall = MagicMock()
        return legion

    # ===== 测试用例 =====

    def test_execute_success(self):
        """测试成功执行战斗阶段"""
        # 设置模拟：有活跃战争，已指派指挥官，有军团
        war = self._create_mock_war()
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Combat Phase", output)
        self.assertIn("Battle: Test War", output)
        self.assertIn("Total Force:", output)

        # 验证战争系统和军事系统被调用
        self.mock_war_system.get_active_wars.assert_called_once()
        self.mock_military_system.get_legions_for_battle.assert_called_once_with("war1")

        # 验证阶段被标记
        self.assertTrue(self.state.is_phase_executed("combat"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = CombatCommand(self.state)

        # 第一次执行（设置无战争，快速完成）
        self.mock_war_system.get_active_wars.return_value = []
        result1 = cmd.execute([])
        self.assertTrue(result1)

        # 第二次执行
        f = io.StringIO()
        with redirect_stdout(f):
            result2 = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result2)
        self.assertIn("战斗阶段在本回合已执行过", output)

    def test_no_active_wars(self):
        """测试没有活跃战争时自动完成"""
        self.mock_war_system.get_active_wars.return_value = []

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("No active conflicts", output)
        self.assertTrue(self.state.is_phase_executed("combat"))

    def test_unassigned_wars(self):
        """测试有战争但未指派指挥官时跳过"""
        # 两个战争：一个无指挥官，一个有指挥官
        war1 = self._create_mock_war(war_id="war1", name="Unassigned War", commander_id=None)
        war2 = self._create_mock_war(war_id="war2", name="Assigned War", commander_id=1)
        self.mock_war_system.get_active_wars.return_value = [war1, war2]

        # 有指挥官的那个战争设置军团
        self.mock_military_system.get_legions_for_battle.side_effect = lambda war_id: (
            [self._create_mock_legion()] if war_id == "war2" else []
        )

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("1 war(s) without commanders!", output)
        self.assertIn("Unassigned War", output)
        self.assertIn("Assigned War", output)  # 有指派的战争会战斗
        self.assertIn("Battle: Assigned War", output)

    @patch('random.randint')
    def test_battle_outcomes_triumph(self, mock_randint):
        """测试大胜结果"""
        mock_randint.return_value = 10  # 骰子10

        war = self._create_mock_war(strength=5)
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("RESULT: TRIUMPH", output)
        self.assertIn("returns in triumph", output)

        for leg in legions:
            leg.promote_to_veteran.assert_called_once()
            leg.recall.assert_called_once()
        self.mock_war_system.resolve_war.assert_called_once_with("war1", victory=True)

    @patch('random.randint')
    def test_battle_outcomes_victory(self, mock_randint):
        """测试胜利结果"""
        mock_randint.return_value = 6
        war = self._create_mock_war(strength=5)
        self.mock_war_system.get_active_wars.return_value = [war]
        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("RESULT: VICTORY", output)
        self.mock_war_system.resolve_war.assert_called_once_with("war1", victory=True)

    @patch('random.randint')
    def test_battle_outcomes_stalemate(self, mock_randint):
        """测试僵持结果"""
        # 设置骰子为2，敌方强度为12，使 combat_total = 2+9-12 = -1 (在僵持区间)
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=12)
        war.get_total_strength.return_value = 12
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("RESULT: STALEMATE", output)
        self.assertEqual(war.duration, 2)  # 原1，僵持+1
        self.mock_war_system.resolve_war.assert_not_called()

    @patch('random.randint')
    @patch('random.random')
    def test_battle_outcomes_defeat_fled(self, mock_random, mock_randint):
        """测试失败结果且将领逃跑"""
        # 设置骰子为2，敌方强度为15，使 combat_total = 2+9-15 = -4 (< -3 触发失败)
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=15)
        war.get_total_strength.return_value = 15
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        # 设置随机使得将领逃跑 (roll<0.3)
        mock_random.return_value = 0.2

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("RESULT: DEFEAT", output)

        # 验证军团损失一半（2个军团损失1个）
        self.assertEqual(legions[0].status, LegionStatus.DISBANDED)
        legions[0].recall.assert_called_once()
        self.assertFalse(legions[1].status == LegionStatus.DISBANDED)

        war.report_commander_casualty.assert_called_once_with("fled", 1)

    @patch('random.randint')
    def test_battle_outcomes_disaster(self, mock_randint):
        """测试灾难结果"""
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=5)
        war.is_disaster_roll.return_value = True
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("RESULT: DISASTER", output)

        for leg in legions:
            leg.recall.assert_called_once()
            self.assertEqual(leg.status, LegionStatus.DISBANDED)

        self.assertTrue(self.commander.is_dead)
        war.report_commander_casualty.assert_called_once_with("killed", 1)

    def test_commander_casualty_record(self):
        """测试指挥官伤亡记录功能"""
        war = self._create_mock_war()
        war.report_commander_casualty("killed", 1)
        war.report_commander_casualty.assert_called_once_with("killed", 1)

    def test_no_legions_assigned(self):
        """测试指派了指挥官但无军团的情况"""
        war = self._create_mock_war()
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_military_system.get_legions_for_battle.return_value = []

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("No Legions assigned!", output)  # 注意大小写
        self.assertEqual(war.duration, 2)

    def test_commander_dead(self):
        """测试指挥官已死亡的情况"""
        self.commander.is_dead = True
        war = self._create_mock_war()
        self.mock_war_system.get_active_wars.return_value = [war]

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Commander unavailable!", output)  # 注意大小写
        self.mock_war_system.recall_commander.assert_called_once_with("war1")


if __name__ == "__main__":
    unittest.main()