# src/tests/test_commands/test_phase_population.py
"""
人口阶段命令单元测试
"""

import unittest
import sys
import os
import io
import random
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_population import PopulationCommand
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, OfficeTerm, ClassTier
from src.core.entities.entities import Faction, GameTurn


class TestPopulationCommand(unittest.TestCase):
    """人口阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        # 基础配置（含选举规则）
        test_config = {
            "political_rules": {
                "leader_cooldown_years": 10,
                "leaders_per_election": 2,
                "office_cooldowns": {
                    "consul": 10,
                    "praetor": 5,
                    "quaestor": 2
                },
                "offices_per_election": {
                    "consul": 2,
                    "praetor": 2,
                    "quaestor": 2
                },
                "min_ages": {
                    "consul": 40,
                    "praetor": 35,
                    "quaestor": 30
                },
                "candidates_per_election": {
                    "consul": 3,
                    "praetor": 3,
                    "quaestor": 3
                }
            }
        }
        self.state = GameState.create_for_testing(test_config)

        # 创建三个派系
        factions = [
            Faction(id="senate", name="元老院派", treasury=50, is_player=True),
            Faction(id="populares", name="平民派", treasury=30, is_player=False),
            Faction(id="equites", name="骑士派", treasury=40, is_player=False)
        ]
        for f in factions:
            self.state.add_faction(f)
        self.faction1, self.faction2, self.faction3 = factions

        # ===== 创建人物用于选举测试 =====
        next_id = 1
        figures = []

        def create_figure(name, faction_id, age, class_tier,
                          influence=5, wealth=20, popularity=5,
                          charisma=5, intelligence=5, martial=5,
                          history=None):
            nonlocal next_id
            fig = Figure(id=next_id, name=name, faction_id=faction_id, age=age)
            fig.class_tier = class_tier
            fig.influence = influence
            fig.wealth = wealth
            fig.popularity = popularity
            fig.charisma = charisma
            fig.intelligence = intelligence
            fig.martial = martial
            if history:
                for office, start_turn in history:
                    fig.office_history.append(OfficeTerm(office, start_turn))
            figures.append(fig)
            next_id += 1
            return fig

        for faction_id in ["senate", "populares", "equites"]:
            # 3 贵族
            create_figure(f"{faction_id}_noble1", faction_id, 45, ClassTier.NOBILE,
                          influence=8, wealth=30, popularity=7,
                          charisma=8, intelligence=6, martial=5,
                          history=[("quaestor", -8), ("praetor", -5), ("consul", -2)])
            create_figure(f"{faction_id}_noble2", faction_id, 42, ClassTier.NOBILE,
                          influence=6, wealth=25, popularity=6,
                          charisma=7, intelligence=7, martial=6,
                          history=[("quaestor", -7), ("praetor", -4)])
            create_figure(f"{faction_id}_noble3", faction_id, 38, ClassTier.NOBILE,
                          influence=5, wealth=20, popularity=5,
                          charisma=6, intelligence=5, martial=7,
                          history=[("quaestor", -6)])

            # 2 骑士
            create_figure(f"{faction_id}_eques1", faction_id, 35, ClassTier.EQUES,
                          influence=3, wealth=40, popularity=4,
                          charisma=4, intelligence=8, martial=4)
            create_figure(f"{faction_id}_eques2", faction_id, 32, ClassTier.EQUES,
                          influence=2, wealth=35, popularity=3,
                          charisma=3, intelligence=7, martial=5)

            # 1 平民
            create_figure(f"{faction_id}_pleb1", faction_id, 30, ClassTier.PLEBEIAN,
                          influence=1, wealth=5, popularity=2,
                          charisma=2, intelligence=2, martial=2)

        for fig in figures:
            self.state.add_member(fig)

        self.faction1.member_ids = [f.id for f in figures if f.faction_id == "senate"]
        self.faction2.member_ids = [f.id for f in figures if f.faction_id == "populares"]
        self.faction3.member_ids = [f.id for f in figures if f.faction_id == "equites"]

        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 200
        self.state.mark_phase_executed("forum")  # 人口阶段前需执行广场

        # 设置模拟军事系统（可选，原有测试需要）
        self._setup_mock_military_system()

    def _setup_mock_military_system(self, active_legions=5, unassigned_legions=2, available_legions=3):
        mock_ms = MagicMock()
        mock_legion = MagicMock()
        mock_legion.number = 1
        mock_legion.name = "Legio I"
        mock_ms.get_active_legions.return_value = [mock_legion] * active_legions
        mock_ms.get_unassigned_legions.return_value = [mock_legion] * unassigned_legions
        mock_ms.get_available_legions.return_value = [mock_legion] * available_legions
        mock_ms.disband_legion.return_value = (True, "Disbanded")
        self.state._military_system = mock_ms
        return mock_ms

    # ===== 选举相关测试（从原 test_phase_senate.py 移植）=====

    def test_election_logic(self):
        """测试选举逻辑：执政官应选出2人"""
        cmd = PopulationCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        consuls = [cid for cid in self.state.turn.leader_ids]
        self.assertEqual(len(consuls), 2, "应选举出2名执政官")
        for cid in consuls:
            fig = self.state.get_member(cid)
            self.assertIsNotNone(fig)

    def test_remove_office_holders(self):
        """测试卸任逻辑"""
        cmd = PopulationCommand(self.state)

        # 创建临时人物并设置官职
        fig1 = Figure(id=9991, name="Test Consul", faction_id="senate", age=40)
        fig1.office = "consul"
        fig2 = Figure(id=9992, name="Test Praetor", faction_id="populares", age=35)
        fig2.office = "praetor"
        fig3 = Figure(id=9993, name="Test Quaestor", faction_id="senate", age=30)
        fig3.office = "quaestor"
        self.state.add_member(fig1)
        self.state.add_member(fig2)
        self.state.add_member(fig3)

        cmd._remove_office_holders("consul")
        self.assertEqual(fig1.office, "ex-consul")
        self.assertEqual(fig2.office, "praetor")
        self.assertEqual(fig3.office, "quaestor")

    def test_qualification_checks(self):
        """测试资格检查方法"""
        cmd = PopulationCommand(self.state)

        fig_qualified = Figure(id=9971, name="Qualified", faction_id="senate", age=45)
        fig_qualified.class_tier = ClassTier.NOBILE
        fig_qualified.office_history = [
            OfficeTerm("quaestor", -8),
            OfficeTerm("praetor", -5)
        ]
        self.state.add_member(fig_qualified)

        fig_unqualified = Figure(id=9972, name="Unqualified", faction_id="senate", age=40)
        fig_unqualified.class_tier = ClassTier.NOBILE
        self.state.add_member(fig_unqualified)

        self.assertEqual(cmd._get_min_age("consul"), 40)
        self.assertEqual(cmd._get_prerequisite("consul"), "Praetor")
        self.assertTrue(cmd._check_prerequisite(fig_qualified, "consul"))
        self.assertFalse(cmd._check_prerequisite(fig_unqualified, "consul"))

        current_turn = 1
        self.assertFalse(cmd._check_in_cooldown(fig_qualified, "praetor", current_turn))
        fig_qualified.office_history.append(OfficeTerm("praetor", current_turn - 1))
        self.assertTrue(cmd._check_in_cooldown(fig_qualified, "praetor", current_turn))

    # ===== 原有人口阶段功能测试（保持不变）=====

    def test_execute_success(self):
        """测试成功执行人口阶段（包含选举和其他功能）"""
        cmd = PopulationCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Population Phase", output)
        self.assertIn("MAGISTRATE ELECTIONS", output)
        self.assertIn("State of the Republic", output)
        self.assertTrue(self.state.is_phase_executed("population"))

    def test_already_executed(self):
        cmd = PopulationCommand(self.state)
        cmd.execute([])
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()
        self.assertFalse(result)
        self.assertIn("人口阶段在本回合已执行过", output)

    def test_republic_state_calculation_calm(self):
        self.state._treasury = 200
        with patch.object(self.state, 'get_active_wars', return_value=[]):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)
        self.assertEqual(state_name, terms.state_calm)

    def test_republic_state_calculation_uneasy(self):
        self.state._treasury = 80
        with patch.object(self.state, 'get_active_wars', return_value=[]):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)
        self.assertEqual(state_name, terms.state_uneasy)

    def test_republic_state_calculation_tense(self):
        self.state._treasury = 40
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)
        self.assertEqual(state_name, terms.state_tense)

    def test_republic_state_calculation_bad(self):
        self.state._treasury = -10
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            state_name = cmd._calculate_republic_state(terms)
        self.assertEqual(state_name, terms.state_bad)

    def test_legion_disbandment_bad_state(self):
        mock_ms = self._setup_mock_military_system(active_legions=6, unassigned_legions=3)
        self.state._treasury = -10
        with patch.object(self.state, 'get_active_wars', return_value=['war1']):
            cmd = PopulationCommand(self.state)
            terms = TerminologyService.get()
            cmd._process_legion_disbandment(terms, terms.state_bad)
        self.assertEqual(mock_ms.disband_legion.call_count, 3)

    def test_legion_disbandment_tense_state(self):
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
        mock_ms.disband_legion.assert_not_called()

    def test_legion_disbandment_calm_state(self):
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
        mock_random.return_value = 0.1
        cmd = PopulationCommand(self.state)
        terms = TerminologyService.get()
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_population_events(terms)
        output = f.getvalue()
        self.assertIn("📢", output)

    @patch('random.random')
    def test_population_events_not_triggered(self, mock_random):
        mock_random.return_value = 0.3
        cmd = PopulationCommand(self.state)
        terms = TerminologyService.get()
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_population_events(terms)
        output = f.getvalue()
        self.assertIn("No significant events", output)


if __name__ == "__main__":
    unittest.main()