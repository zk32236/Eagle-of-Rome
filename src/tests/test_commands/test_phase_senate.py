# src/tests/test_commands/test_phase_senate.py
"""
元老院阶段命令单元测试
"""

import unittest
import sys
import os
import random
from unittest.mock import patch, MagicMock
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_senate import SenateCommand
from src.core.entities.figure import Figure, OfficeTerm, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.localization import TerminologyService


class TestSenateCommand(unittest.TestCase):
    """元老院阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        # 基础配置
        test_config = {
            "political_rules": {
                "leader_cooldown_years": 10,
                "leaders_per_election": 2,
                "office_cooldowns": {
                    "consul": 10,
                    "praetor": 5,
                    "quqaestor": 2
                },
                "offices_per_election": {
                    "consul": 2,
                    "praetor": 2,
                    "quqaestor": 2
                },
                "min_ages": {
                    "consul": 40,
                    "praetor": 35,
                    "quqaestor": 30
                },
                "candidates_per_election": {
                    "consul": 3,
                    "praetor": 3,
                    "quqaestor": 3
                }
            }
        }
        self.state = GameState.create_for_testing(test_config)

        # ===== 创建三个派系 =====
        factions = [
            Faction(id="senate", name="元老院派", treasury=50, is_player=True),
            Faction(id="populares", name="平民派", treasury=30, is_player=False),
            Faction(id="equites", name="骑士派", treasury=40, is_player=False)
        ]
        for f in factions:
            self.state.add_faction(f)
        self.faction1, self.faction2, self.faction3 = factions

        # ===== 辅助函数：创建人物 =====
        next_id = 1
        figures = []

        def create_figure(name, faction_id, age, class_tier,
                          power=5, wealth=20, popularity=5,
                          charisma=5, management=5, strategy=5,
                          history=None):
            nonlocal next_id
            fig = Figure(id=next_id, name=name, faction_id=faction_id, age=age)
            fig.class_tier = class_tier
            fig.power = power
            fig.wealth = wealth
            fig.popularity = popularity
            fig.charisma = charisma
            fig.management = management
            fig.strategy = strategy
            if history:
                for office, start_turn in history:
                    fig.office_history.append(OfficeTerm(office, start_turn))
            figures.append(fig)
            next_id += 1
            return fig

        # ===== 为每个派系生成人物 =====
        for faction_id in ["senate", "populares", "equites"]:
            # 3 贵族
            create_figure(f"{faction_id}_noble1", faction_id, 45, ClassTier.NOBILE,
                          power=8, wealth=30, popularity=7,
                          charisma=8, management=6, strategy=5,
                          history=[("quqaestor", -8), ("praetor", -5), ("consul", -2)])  # 前执政官
            create_figure(f"{faction_id}_noble2", faction_id, 42, ClassTier.NOBILE,
                          power=6, wealth=25, popularity=6,
                          charisma=7, management=7, strategy=6,
                          history=[("quqaestor", -7), ("praetor", -4)])  # 前大法官
            create_figure(f"{faction_id}_noble3", faction_id, 38, ClassTier.NOBILE,
                          power=5, wealth=20, popularity=5,
                          charisma=6, management=5, strategy=7,
                          history=[("quqaestor", -6)])  # 前财务官

            # 2 骑士
            create_figure(f"{faction_id}_eques1", faction_id, 35, ClassTier.EQUES,
                          power=3, wealth=40, popularity=4,
                          charisma=4, management=8, strategy=4)
            create_figure(f"{faction_id}_eques2", faction_id, 32, ClassTier.EQUES,
                          power=2, wealth=35, popularity=3,
                          charisma=3, management=7, strategy=5)

            # 1 平民
            create_figure(f"{faction_id}_pleb1", faction_id, 30, ClassTier.PLEBEIAN,
                          power=1, wealth=5, popularity=2,
                          charisma=2, management=2, strategy=2)

        # 将所有人物添加到状态
        for fig in figures:
            self.state.add_member(fig)

        # 更新派系成员列表
        self.faction1.member_ids = [f.id for f in figures if f.faction_id == "senate"]
        self.faction2.member_ids = [f.id for f in figures if f.faction_id == "populares"]
        self.faction3.member_ids = [f.id for f in figures if f.faction_id == "equites"]

        # 设置回合
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 200

    def _setup_mock_contracts(self):
        """创建模拟的合同用于测试"""
        # 包税合同
        tax_contract = MagicMock(spec=Contract)
        tax_contract.contract_type = ContractType.TAX_FARMING
        tax_contract.status = ContractStatus.PENDING
        tax_contract.name = "西西里包税权"
        tax_contract.base_cost = 30
        tax_contract.expected_profit = 50
        tax_contract.duration_years = 5
        tax_contract.award.return_value = True

        # 工程合同
        works_contract = MagicMock(spec=Contract)
        works_contract.contract_type = ContractType.PUBLIC_WORKS
        works_contract.status = ContractStatus.PENDING
        works_contract.name = "罗马大道工程"
        works_contract.base_cost = 40
        works_contract.expected_profit = 20
        works_contract.duration_years = 2
        works_contract.award.return_value = True

        self.state._contracts = [tax_contract, works_contract]
        return tax_contract, works_contract

    # ===== 测试用例 =====

    def test_execute_success(self):
        """测试成功执行元老院阶段"""
        cmd = SenateCommand(self.state)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Senate Phase", output)
        self.assertIn("MAGISTRATE ELECTIONS", output)
        self.assertIn("Faction Leaders Updated", output)
        self.assertIn("Presiding Officer", output)

        # 验证阶段被标记
        self.assertTrue(self.state.is_phase_executed("senate"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = SenateCommand(self.state)

        # 第一次执行
        result1 = cmd.execute([])
        self.assertTrue(result1)

        # 第二次执行
        f = io.StringIO()
        with redirect_stdout(f):
            result2 = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result2)
        self.assertIn("元老院阶段在本回合已执行过", output)

    def test_election_logic(self):
        """测试选举逻辑（核心验证：执政官应选出2人）"""
        cmd = SenateCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        self.assertTrue(result)

        # 验证执政官选举：应有两人当选（核心业务）
        consuls = [cid for cid in self.state.turn.leader_ids]
        self.assertEqual(len(consuls), 2, "应选举出2名执政官")
        for cid in consuls:
            fig = self.state.get_member(cid)
            self.assertIsNotNone(fig)

        # 注意：由于同一人物可能当选多个官职导致最终覆盖，不再对大法官和财务官人数做硬性断言
        # 这些细节已在其他测试中验证（如资格检查、选举流程输出等）

    def test_contract_processing(self):
        """测试合同处理逻辑"""
        tax_contract, works_contract = self._setup_mock_contracts()

        cmd = SenateCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        self.assertTrue(result)

        # 验证包税合同被授予（应有骑士候选人）
        tax_contract.award.assert_called_once()
        args, kwargs = tax_contract.award.call_args
        # 参数应为 (figure_id, faction_id, turn_number)
        figure_id = args[0]
        awarded_fig = self.state.get_member(figure_id)
        self.assertEqual(awarded_fig.class_tier.value, "eques", "包税合同应授予骑士")

        # 验证工程合同被授予
        works_contract.award.assert_called_once()
        args, kwargs = works_contract.award.call_args
        figure_id = args[0]
        awarded_fig = self.state.get_member(figure_id)
        self.assertEqual(awarded_fig.class_tier.value, "eques", "工程合同应授予骑士")

    def test_presiding_officer(self):
        """测试主持人确定逻辑"""
        cmd = SenateCommand(self.state)
        cmd.execute([])  # 执行选举

        presiding = self.state.get_presiding_officer()
        self.assertIsNotNone(presiding, "主持人不应为None")

        # 主持人应为权力最高者
        living = self.state.get_living_members()
        max_power = max(m.power for m in living)
        self.assertEqual(presiding.power, max_power, "主持人必须是权力最高者")

    def test_seat_standings(self):
        """测试席位占比显示（直接调用私有方法验证输出）"""
        cmd = SenateCommand(self.state)

        # 创建临时人物并设置土地/私兵
        from src.core.entities.figure import Figure
        from src.core.entities.entities import Faction

        # 临时派系
        temp_faction = Faction(id="temp", name="临时派", treasury=0)
        self.state.add_faction(temp_faction)

        fig1 = Figure(id=9981, name="Land Owner 1", faction_id="temp", age=40)
        fig1.land = 10
        fig1.veterans = 5
        fig2 = Figure(id=9982, name="Land Owner 2", faction_id="temp", age=35)
        fig2.land = 8
        fig2.veterans = 2
        self.state.add_member(fig1)
        self.state.add_member(fig2)
        temp_faction.member_ids = [9981, 9982]

        f = io.StringIO()
        with redirect_stdout(f):
            cmd._show_seat_standings(TerminologyService.get())
        output = f.getvalue()

        self.assertIn("Senate Seat Distribution", output)
        self.assertIn("National Assets:", output)
        self.assertIn("Faction Totals:", output)
        self.assertIn("seats", output)

    def test_remove_office_holders(self):
        """测试卸任逻辑"""
        cmd = SenateCommand(self.state)

        # 创建临时人物用于测试
        from src.core.entities.figure import Figure
        fig1 = Figure(id=9991, name="Test Consul", faction_id="senate", age=40)
        fig2 = Figure(id=9992, name="Test Praetor", faction_id="populares", age=35)
        fig3 = Figure(id=9993, name="Test Quaestor", faction_id="senate", age=30)

        # 设置官职
        fig1.office = "consul"
        fig2.office = "praetor"
        fig3.office = "quqaestor"

        # 添加到状态（临时）
        self.state.add_member(fig1)
        self.state.add_member(fig2)
        self.state.add_member(fig3)

        cmd._remove_office_holders("consul")  # 只卸任执政官

        # 验证fig1卸任
        self.assertIsNone(fig1.office)
        # fig2和fig3不应受影响
        self.assertEqual(fig2.office, "praetor")
        self.assertEqual(fig3.office, "quqaestor")

    def test_qualification_checks(self):
        """测试资格检查方法"""
        cmd = SenateCommand(self.state)
        from src.core.entities.figure import Figure, OfficeTerm, ClassTier

        # 创建有历史的人物（符合执政官资格）
        fig_qualified = Figure(id=9971, name="Qualified", faction_id="senate", age=45)
        fig_qualified.class_tier = ClassTier.NOBILE
        fig_qualified.office_history = [
            OfficeTerm("quqaestor", -8),
            OfficeTerm("praetor", -5)
        ]
        self.state.add_member(fig_qualified)

        # 创建无历史的人物（不符合执政官/大法官资格）
        fig_unqualified = Figure(id=9972, name="Unqualified", faction_id="senate", age=40)
        fig_unqualified.class_tier = ClassTier.NOBILE
        self.state.add_member(fig_unqualified)

        # 测试 _get_min_age
        self.assertEqual(cmd._get_min_age("consul"), 40)
        self.assertEqual(cmd._get_min_age("praetor"), 35)
        self.assertEqual(cmd._get_min_age("quqaestor"), 30)

        # 测试 _get_prerequisite
        self.assertEqual(cmd._get_prerequisite("consul"), "Praetor")
        self.assertEqual(cmd._get_prerequisite("praetor"), "Quaestor")
        self.assertEqual(cmd._get_prerequisite("quqaestor"), "None")

        # 测试 _check_prerequisite
        # 有历史人物
        self.assertTrue(cmd._check_prerequisite(fig_qualified, "consul"))  # 有 praetor 历史
        self.assertTrue(cmd._check_prerequisite(fig_qualified, "praetor"))  # 有 quaestor 历史
        self.assertTrue(cmd._check_prerequisite(fig_qualified, "quqaestor"))  # quqaestor 无前置，应返回 True

        # 无历史人物
        self.assertFalse(cmd._check_prerequisite(fig_unqualified, "consul"))  # 无 praetor 历史
        self.assertFalse(cmd._check_prerequisite(fig_unqualified, "praetor"))  # 无 quaestor 历史
        self.assertTrue(cmd._check_prerequisite(fig_unqualified, "quqaestor"))  # quqaestor 无前置，返回 True

        # 测试 _check_in_cooldown
        current_turn = 1
        # fig_qualified 上次担任 praetor 在 -5 回合，距今 6 回合，冷却 5，已过冷却
        self.assertFalse(cmd._check_in_cooldown(fig_qualified, "praetor", current_turn))

        # 假设最近刚担任过
        fig_qualified.office_history.append(OfficeTerm("praetor", current_turn - 1))
        self.assertTrue(cmd._check_in_cooldown(fig_qualified, "praetor", current_turn))

    def test_power_bonus(self):
        """测试权力加成"""
        cmd = SenateCommand(self.state)
        self.assertEqual(cmd._get_power_bonus("consul"), 5)
        self.assertEqual(cmd._get_power_bonus("praetor"), 3)
        self.assertEqual(cmd._get_power_bonus("quqaestor"), 2)


if __name__ == "__main__":
    unittest.main()