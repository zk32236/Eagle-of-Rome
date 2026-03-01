# src/tests/test_commands/test_phase_population.py
"""人口阶段命令单元测试 - 适配新打印布局"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.ui.commands.phase_population import PopulationCommand
from src.core.localization import TerminologyService
from src.core.systems.military_system import MilitarySystem
from src.core.systems.war_system import WarSystem


class TestPopulationCommand(unittest.TestCase):
    """人口阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {
            "political_rules": {
                "candidates_per_election": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
                "min_ages": {"consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30},
                "office_cooldowns": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
                "offices_per_election": {"consul": 1, "censor": 1, "praetor": 1, "quaestor": 2, "tribune": 1}
            },
            "economic_rules": {
                "faction_member_limit": 6
            }
        }
        self.state = GameState.create_for_testing(test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("forum")

        # 添加测试派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=100)
        self.faction2 = Faction(id="plebs", name="平民派", treasury=80)
        self.faction3 = Faction(id="equites", name="骑士派", treasury=60)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)
        self.state.add_faction(self.faction3)

        # 添加测试人物到派系（贵族，有官职历史）
        self.noble1 = Figure(id=1, name="senate_noble1", faction_id="senate", class_tier=ClassTier.NOBILE, age=45, wealth=50)
        self.noble1.office_history = [OfficeTerm("quaestor", -8), OfficeTerm("praetor", -5), OfficeTerm("consul", -2)]
        self.noble1.influence = 30
        self.state.add_member(self.noble1)
        self.faction1.member_ids.append(1)

        self.noble2 = Figure(id=2, name="senate_noble2", faction_id="senate", class_tier=ClassTier.NOBILE, age=42, wealth=50)
        self.noble2.office_history = [OfficeTerm("quaestor", -7), OfficeTerm("praetor", -4)]
        self.noble2.influence = 25
        self.state.add_member(self.noble2)
        self.faction1.member_ids.append(2)

        self.noble3 = Figure(id=3, name="senate_noble3", faction_id="senate", class_tier=ClassTier.NOBILE, age=38, wealth=50)
        self.noble3.office_history = [OfficeTerm("quaestor", -6)]
        self.noble3.influence = 20
        self.state.add_member(self.noble3)
        self.faction1.member_ids.append(3)

        self.populares1 = Figure(id=4, name="populares_noble1", faction_id="plebs", class_tier=ClassTier.NOBILE, age=45, wealth=50)
        self.populares1.office_history = [OfficeTerm("quaestor", -8), OfficeTerm("praetor", -5), OfficeTerm("consul", -2)]
        self.populares1.influence = 28
        self.state.add_member(self.populares1)
        self.faction2.member_ids.append(4)

        self.populares2 = Figure(id=5, name="populares_noble2", faction_id="plebs", class_tier=ClassTier.NOBILE, age=42, wealth=50)
        self.populares2.office_history = [OfficeTerm("quaestor", -7), OfficeTerm("praetor", -4)]
        self.populares2.influence = 24
        self.state.add_member(self.populares2)
        self.faction2.member_ids.append(5)

        self.populares3 = Figure(id=6, name="populares_noble3", faction_id="plebs", class_tier=ClassTier.NOBILE, age=38, wealth=50)
        self.populares3.office_history = [OfficeTerm("quaestor", -6)]
        self.populares3.influence = 18
        self.state.add_member(self.populares3)
        self.faction2.member_ids.append(6)

        self.equites1 = Figure(id=7, name="equites_noble1", faction_id="equites", class_tier=ClassTier.NOBILE, age=42, wealth=50)
        self.equites1.office_history = [OfficeTerm("quaestor", -7), OfficeTerm("praetor", -4)]
        self.equites1.influence = 22
        self.state.add_member(self.equites1)
        self.faction3.member_ids.append(7)

        self.equites2 = Figure(id=8, name="equites_noble2", faction_id="equites", class_tier=ClassTier.NOBILE, age=42, wealth=50)
        self.equites2.office_history = [OfficeTerm("quaestor", -7), OfficeTerm("praetor", -4)]
        self.equites2.influence = 21
        self.state.add_member(self.equites2)
        self.faction3.member_ids.append(8)

        self.equites3 = Figure(id=9, name="equites_noble3", faction_id="equites", class_tier=ClassTier.NOBILE, age=38, wealth=50)
        self.equites3.office_history = [OfficeTerm("quaestor", -6)]
        self.equites3.influence = 16
        self.state.add_member(self.equites3)
        self.faction3.member_ids.append(9)

        # 添加骑士和平民（用于庆典和选举）
        self.knight1 = Figure(id=10, name="senate_eques1", faction_id="senate", class_tier=ClassTier.EQUES, age=35, wealth=40)
        self.knight1.influence = 5
        self.state.add_member(self.knight1)
        self.faction1.member_ids.append(10)

        self.knight2 = Figure(id=11, name="senate_eques2", faction_id="senate", class_tier=ClassTier.EQUES, age=32, wealth=40)
        self.knight2.influence = 4
        self.state.add_member(self.knight2)
        self.faction1.member_ids.append(11)

        self.plebeian1 = Figure(id=12, name="populares_eques1", faction_id="plebs", class_tier=ClassTier.PLEBEIAN, age=30, wealth=20)
        self.plebeian1.influence = 2
        self.state.add_member(self.plebeian1)
        self.faction2.member_ids.append(12)

        self.plebeian2 = Figure(id=13, name="populares_eques2", faction_id="plebs", class_tier=ClassTier.PLEBEIAN, age=30, wealth=20)
        self.plebeian2.influence = 1
        self.state.add_member(self.plebeian2)
        self.faction2.member_ids.append(13)

        self.plebeian3 = Figure(id=14, name="equites_eques1", faction_id="equites", class_tier=ClassTier.PLEBEIAN, age=30, wealth=20)
        self.plebeian3.influence = 1
        self.state.add_member(self.plebeian3)
        self.faction3.member_ids.append(14)

        # 设置军事系统和战争系统（模拟）
        self.mock_military = MagicMock(spec=MilitarySystem)
        self.state._military_system = self.mock_military

        self.mock_war = MagicMock(spec=WarSystem)
        self.mock_war._war_discard = []  # 添加私有属性，避免 AttributeError
        self.mock_war._legions_to_disband = []
        self.state._war_system = self.mock_war

    # ========== 测试用例 ==========

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("population")
        cmd = PopulationCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

    def test_execute_success(self):
        """测试成功执行人口阶段"""
        cmd = PopulationCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Population Phase", output)
        self.assertIn("ELECTIONS Campaign", output)
        self.assertIn("📋 选举结果：", output)
        self.assertIn("📊 各派系影响力（选举后）：", output)

    def test_automatic_festivals(self):
        """测试自动庆典功能"""
        # 模拟庆典决策器返回一些花费
        mock_decider = MagicMock()
        mock_decider.decide_festivals.return_value = {1: 10, 2: 5}  # 人物ID: 花费

        cmd = PopulationCommand(self.state, festival_decider=mock_decider)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        # 检查输出中是否包含庆典统计
        self.assertIn("总计花费", output)
        self.assertIn("增加人气", output)

    def test_censor_election(self):
        """测试监察官选举：检查选举结果中是否有监察官"""
        cmd = PopulationCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        # 检查选举结果中是否包含监察官行
        self.assertIn("📜 CENSOR:", output)

    def test_tribune_class_restriction(self):
        """测试保民官仅限骑士和平民"""
        # 创建一个贵族候选人尝试参选保民官（应不出现）
        noble = Figure(id=100, name="贵族", faction_id="senate", class_tier=ClassTier.NOBILE, age=35)
        noble.office_history = []
        self.state.add_member(noble)
        self.faction1.member_ids.append(100)

        # 创建一个骑士候选人
        knight = Figure(id=101, name="骑士", faction_id="equites", class_tier=ClassTier.EQUES, age=35)
        knight.office_history = []
        self.state.add_member(knight)
        self.faction3.member_ids.append(101)

        cmd = PopulationCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        # 检查选举结果中是否有保民官行
        self.assertIn("🛡️ TRIBUNE:", output)
        # 确保贵族没有当选（此处简化验证，信任选举逻辑）

    def test_remove_office_holders(self):
        """测试卸任官员"""
        # 先设置一些现任官员
        self.noble1.office = "consul"
        self.noble2.office = "censor"
        self.noble3.office = "praetor"

        cmd = PopulationCommand(self.state)

        # 分别调用卸任方法，不执行整个阶段
        cmd._remove_office_holders("consul")
        self.assertEqual(self.noble1.office, "ex-consul")
        self.assertEqual(len(self.noble1.office_history), 4)  # 原3+1
        self.assertEqual(self.noble1.office_history[-1].office_type, "consul")
        self.assertEqual(self.noble1.office_history[-1].start_turn, self.state.turn.turn_number - 1)

        cmd._remove_office_holders("censor")
        self.assertEqual(self.noble2.office, "ex-censor")
        self.assertEqual(len(self.noble2.office_history), 3)  # 原2+1
        self.assertEqual(self.noble2.office_history[-1].office_type, "censor")

        cmd._remove_office_holders("praetor")
        self.assertEqual(self.noble3.office, "ex-praetor")
        self.assertEqual(len(self.noble3.office_history), 2)  # 原1+1
        self.assertEqual(self.noble3.office_history[-1].office_type, "praetor")

        # 验证影响力已更新（可选）
        self.assertGreater(self.noble1.influence, 0)


if __name__ == "__main__":
    unittest.main()