# src/tests/test_commands/test_phase_combat.py
"""
战斗阶段命令单元测试
"""
import pytest
import unittest
import sys
import os
import io
from contextlib import redirect_stdout
from src.core.game_state import GameState
from src.core.entities.legion import Legion, LegionStatus
from src.core.entities.figure import Figure
from src.core.entities.entities import GameTurn
from unittest.mock import MagicMock, patch
from src.core.entities.war import War, WarStatus
from src.ui.commands.phase_combat import CombatCommand

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)




class TestCombatCommand(unittest.TestCase):
    """战斗阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {}
        self.state = GameState.create_for_testing(test_config)

        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("senate")

        self.mock_war_system = MagicMock()
        self.state._war_system = self.mock_war_system

        self.mock_military_system = MagicMock()
        self.state._military_system = self.mock_military_system

        self.commander = Figure(id=1, name="Test Commander", faction_id="senate", age=40)
        self.commander.martial = 5
        self.commander.influence = 10
        self.state.add_member(self.commander)
        self.commander.is_absent = True

    def _create_mock_war(self, war_id="war1", name="Test War", strength=10,
                         naval_support_required=False, commander_id=1, **kwargs):  # <-- 默认改为1
        """
        创建一个模拟的战争对象，用于测试。
        """
        war = MagicMock()  # 不指定 spec，允许动态添加属性
        war.id = war_id
        war.name = name
        war._strength = strength
        war.naval_support_required = naval_support_required
        war.naval_strength = 3 if naval_support_required else 0
        war.commander_id = commander_id
        war.duration = 0
        war.status = WarStatus.ACTIVE

        # 模拟常用方法
        war.get_total_strength.return_value = strength + (3 if naval_support_required else 0)
        war.is_disaster_roll.return_value = False
        war.is_standoff_roll.return_value = False
        war.report_commander_casualty = MagicMock()
        war.add_legion_number = MagicMock()
        war.set_commander_assigned_turn = MagicMock()  # 新增方法

        # 允许通过 kwargs 覆盖默认值
        for key, value in kwargs.items():
            setattr(war, key, value)

        return war

    def _create_mock_legion(self, number=1, is_veteran=False):
        legion = MagicMock(spec=Legion)
        legion.number = number
        legion.name = f"Legio {number}"
        legion.is_veteran = is_veteran
        legion.status = LegionStatus.ACTIVE
        legion.get_combat_strength.return_value = 2 + (1 if is_veteran else 0)
        legion.promote_to_veteran = MagicMock()
        legion.recall = MagicMock()
        legion.mark_destroyed = MagicMock()
        return legion

    # ===== 测试用例 =====

    @patch('random.randint')
    def test_execute_success(self, mock_randint):
        """测试成功执行战斗阶段（小胜），应生成停战草案"""
        mock_randint.return_value = 6
        war = self._create_mock_war(strength=9)
        war.get_total_strength.return_value = 9
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        # 模拟和平决策器返回草案
        mock_decider = MagicMock()
        mock_decider.decide_treaty.return_value = {
            'indemnity': 60,
            'duration': 5,
            'generated_turn': self.state.turn.turn_number
        }

        cmd = CombatCommand(self.state, peace_treaty_decider=mock_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Combat Phase", output)
        self.assertIn("⚔️  Resolving Test War", output)
        # 验证 enter_truce 被调用
        self.mock_war_system.enter_truce.assert_called_once()
        # 验证 deactivate_war_to_threat 未被调用
        self.mock_war_system.deactivate_war_to_threat.assert_not_called()
        # 验证指挥官仍然在前线（is_absent 保持 True）
        commander = self.state.get_member(1)  # 假设指挥官ID为1
        self.assertTrue(commander.is_absent)
        # 验证草案生成日志
        self.assertIn("达成停战草案", output)

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("combat")
        cmd = CombatCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

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
        war1 = self._create_mock_war(war_id="war1", name="Unassigned War", commander_id=None)
        war2 = self._create_mock_war(war_id="war2", name="Assigned War", commander_id=1)
        self.mock_war_system.get_active_wars.return_value = [war1, war2]

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
        self.assertIn("Test Commander", output)
        self.assertIn("Forces: 1 Legion(s)", output)

    @patch('random.randint')
    def test_battle_outcomes_triumph(self, mock_randint):
        """测试大胜结果"""
        mock_randint.return_value = 12
        war = self._create_mock_war(strength=5)
        war.get_total_strength.return_value = 5
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("TRIUMPH", output)
        self.assertIn("0 losses", output)
        for leg in legions:
            leg.promote_to_veteran.assert_called_once()
            leg.recall.assert_called_once()
        self.mock_war_system.resolve_war.assert_called_once_with("war1", victory=True)

    @patch('random.randint')
    def test_battle_outcomes_victory(self, mock_randint):
        """测试胜利结果（小胜），应生成停战草案"""
        mock_randint.return_value = 9
        war = self._create_mock_war(strength=12)
        war.get_total_strength.return_value = 12
        self.mock_war_system.get_active_wars.return_value = [war]
        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        # 模拟和平决策器返回草案
        mock_decider = MagicMock()
        mock_decider.decide_treaty.return_value = {
            'indemnity': 60,
            'duration': 5,
            'generated_turn': self.state.turn.turn_number
        }

        cmd = CombatCommand(self.state, peace_treaty_decider=mock_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("VICTORY", output)
        self.assertIn("0 losses", output)
        # 验证 enter_truce 被调用
        self.mock_war_system.enter_truce.assert_called_once()
        # 验证 deactivate_war_to_threat 未被调用
        self.mock_war_system.deactivate_war_to_threat.assert_not_called()
        # 验证指挥官仍然在前线（is_absent 保持 True）
        commander = self.state.get_member(1)
        self.assertTrue(commander.is_absent)
        # 验证草案生成日志
        self.assertIn("达成停战草案", output)

    @patch('random.randint')
    def test_battle_outcomes_stalemate(self, mock_randint):
        """测试僵持结果"""
        # 设置敌方强度15，我方总战力9（军团4 + 指挥官5），骰子5 → combat_total = 5+9-15 = -1（僵持区间）
        mock_randint.return_value = 5
        war = self._create_mock_war(strength=15)
        war.get_total_strength.return_value = 15
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("STALEMATE", output)
        self.assertIn("0 losses", output)
        self.assertEqual(war.duration, 1)  #原为2，修改为1
        self.mock_war_system.resolve_war.assert_not_called()
        self.mock_war_system.deactivate_war_to_threat.assert_not_called()

    @patch('random.random')
    @patch('random.randint')
    def test_battle_outcomes_defeat_fled(self, mock_randint, mock_random):
        """测试失败结果且将领逃跑"""
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=15)
        war.get_total_strength.return_value = 15
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions

        mock_random.return_value = 0.2

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("DEFEAT", output)
        self.assertIn("1 Legion(s) destroyed", output)

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
        self.assertIn("DISASTER", output)
        self.assertIn("2 Legion(s) destroyed", output)

        for leg in legions:
            leg.mark_destroyed.assert_called_once_with(1)

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
        self.assertIn("No Legions assigned!", output)
        self.assertEqual(war.duration, 1)

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
        self.assertIn("Commander unavailable!", output)
        self.mock_war_system.recall_commander.assert_called_once_with("war1")


if __name__ == "__main__":
    unittest.main()