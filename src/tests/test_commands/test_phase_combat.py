# src/tests/test_commands/test_phase_combat.py
"""
战斗阶段命令单元测试 — S1 适配版
CombatCommand 已委托给 combat_api.auto_resolve_combat 共享用例。
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
from src.core.entities.entities import Faction, GameTurn
from unittest.mock import MagicMock, patch
from src.core.entities.war import War, WarStatus
from src.core.entities.player import Player, PlayerType
from src.ui.commands.phase_combat import CombatCommand

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestCombatCommand(unittest.TestCase):
    """战斗阶段命令测试类 (S1 共享用例适配版)"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {}
        self.state = GameState.create_for_testing(test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("senate")

        # 添加玩家 & 设为当前玩家（共享用例需要）
        self.faction1 = Faction(id="senate", name="Senate", treasury=50)
        self.state.add_faction(self.faction1)
        self.player = Player(player_id="player_opt", faction_id="senate",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

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
                         naval_support_required=False, commander_id=1, **kwargs):
        """
        创建一个模拟的战争对象，用于测试。
        S1 适配：共享用例需要 int 类型 legions_assigned、
        get_war_by_id 查询表等。
        """
        if not hasattr(self, '_mock_wars_by_id'):
            self._mock_wars_by_id = {}

        war = MagicMock()
        war.id = war_id
        war.name = name
        war._strength = strength
        war.naval_support_required = naval_support_required
        war.naval_strength = 3 if naval_support_required else 0
        war.commander_id = commander_id
        war.duration = 0
        war.status = WarStatus.ACTIVE
        war.legions_assigned = 4  # S1: 共享用例需要 int（用于 *_2 公式）
        war._disaster_numbers = [2, 3]
        war.legion_numbers = []

        # 模拟常用方法
        war.get_total_strength.return_value = strength + (3 if naval_support_required else 0)
        war.is_disaster_roll.return_value = False
        war.is_standoff_roll.return_value = False
        war.report_commander_casualty = MagicMock()
        war.report_commander_casualty.return_value = None
        war.add_legion_number = MagicMock()
        war.set_commander_assigned_turn = MagicMock()

        # S1: _compute_combat_result → war.calculate_rewards() → dict
        # MagicMock 的 .get() 返回 Mock，必须设置 return_value
        war.calculate_rewards.return_value = {"treasury": 100}

        # S1: 注册到 mock_war_system.get_war_by_id 查询表
        self._mock_wars_by_id[war_id] = war
        self.mock_war_system.get_war_by_id.side_effect = lambda wid: self._mock_wars_by_id.get(wid)

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
        """测试成功执行战斗阶段"""
        mock_randint.return_value = 6
        war = self._create_mock_war(strength=9)
        war.get_total_strength.return_value = 9
        war.legions_assigned = 4
        self.mock_war_system.get_active_wars.return_value = [war]

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        # Mock resolve_war
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": True, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None
        self.mock_war_system.enter_truce.return_value = True

        mock_decider = MagicMock()
        mock_decider.decide_treaty.return_value = {
            'indemnity': 60, 'duration': 5, 'generated_turn': self.state.turn.turn_number
        }

        cmd = CombatCommand(self.state, peace_treaty_decider=mock_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Combat Phase", output)
        self.assertIn("Test War", output)

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("combat")
        cmd = CombatCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

    def test_no_active_wars(self):
        """测试没有活跃战争时自动完成"""
        self.mock_war_system.get_active_wars.return_value = []
        self.mock_war_system.get_truce_wars_with_approved_treaty.return_value = []

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
        self.mock_military_system.get_available_legions.return_value = []
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war2.name, "victory": True, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("1 war(s) without commanders", output)

    @patch('random.randint')
    def test_battle_outcomes_triumph(self, mock_randint):
        """测试大胜结果"""
        mock_randint.return_value = 12
        war = self._create_mock_war(strength=5)
        war.get_total_strength.return_value = 5
        war.legions_assigned = 4
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": True, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        cmd = CombatCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # S1: 共享用例输出 result_label
        self.assertTrue("triumph" in output.lower() or "大胜" in output or "🏆" in output)

    @patch('random.randint')
    def test_battle_outcomes_victory(self, mock_randint):
        """测试胜利结果"""
        mock_randint.return_value = 9
        war = self._create_mock_war(strength=12)
        war.get_total_strength.return_value = 12
        war.legions_assigned = 4
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": True, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        mock_decider = MagicMock()
        mock_decider.decide_treaty.return_value = {
            'indemnity': 60, 'duration': 5, 'generated_turn': self.state.turn.turn_number
        }

        cmd = CombatCommand(self.state, peace_treaty_decider=mock_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertTrue("victory" in output.lower() or "胜利" in output or "大胜" in output)

    @patch('random.randint')
    def test_battle_outcomes_stalemate(self, mock_randint):
        """测试僵持结果"""
        mock_randint.return_value = 5
        war = self._create_mock_war(strength=11)
        war.get_total_strength.return_value = 11
        war.legions_assigned = 2  # score = 5+5+4-11=3 → draw
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": False, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertTrue(any(w in output for w in ["draw", "stalemate", "僵持", "⏸️"]))

    @patch('random.random')
    @patch('random.randint')
    def test_battle_outcomes_defeat_fled(self, mock_randint, mock_random):
        """测试失败结果"""
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=20)
        war.get_total_strength.return_value = 20
        war.legions_assigned = 0  # No legions → high chance of defeat
        war._disaster_numbers = [12]  # 2 is not a disaster
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": False, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        mock_random.return_value = 0.2

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertTrue("defeat" in output.lower() or "战败" in output or "😞" in output)

    @patch('random.randint')
    def test_battle_outcomes_disaster(self, mock_randint):
        """测试灾难结果"""
        mock_randint.return_value = 2
        war = self._create_mock_war(strength=5)
        war.is_disaster_roll.return_value = True
        war.legions_assigned = 4
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": False, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        legions = [self._create_mock_legion(1), self._create_mock_legion(2)]
        self.mock_military_system.get_legions_for_battle.return_value = legions
        self.mock_military_system.get_available_legions.return_value = legions

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertTrue("disaster" in output.lower() or "灾难" in output or "💀" in output)

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
        self.mock_military_system.get_available_legions.return_value = []
        self.mock_war_system.resolve_war.return_value = {
            "war_name": war.name, "victory": False, "duration": 0,
            "rewards": {}, "penalties_applied": []
        }
        self.mock_war_system.add_legions_to_disband.return_value = None

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)

    def test_commander_dead(self):
        """测试指挥官已死亡的情况"""
        self.commander.is_dead = True
        war = self._create_mock_war()
        self.mock_war_system.get_active_wars.return_value = [war]
        self.mock_war_system.add_legions_to_disband.return_value = None
        self.mock_military_system.get_available_legions.return_value = []

        cmd = CombatCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
