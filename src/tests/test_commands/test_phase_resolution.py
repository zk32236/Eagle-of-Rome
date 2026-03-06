# src/tests/test_commands/test_phase_resolution.py
"""决议阶段命令单元测试 - 适配精简打印"""

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
from src.core.entities.figure import Figure
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.ui.commands.phase_resolution import ResolutionCommand
from src.core.localization import TerminologyService


class TestResolutionCommand(unittest.TestCase):
    """决议阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {}
        self.state = GameState.create_for_testing(test_config)
        self.state.turn = GameTurn(turn_number=5, year=-260)
        self.state.mark_phase_executed("combat")

        # 添加测试派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=50)
        self.faction2 = Faction(id="plebs", name="平民派", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 添加测试人物
        self.fig1 = Figure(id=1, name="Marcus", faction_id="senate", age=40)
        self.fig1.loyalty = 8
        self.fig1.wealth = 100
        self.fig1.popularity = 10
        self.fig1.veterans = 4
        self.state.add_member(self.fig1)
        self.faction1.member_ids.append(1)

        self.fig2 = Figure(id=2, name="Gaius", faction_id="plebs", age=35)
        self.fig2.loyalty = 3
        self.fig2.wealth = 50
        self.fig2.popularity = 8
        self.fig2.veterans = 2
        self.state.add_member(self.fig2)
        self.faction2.member_ids.append(2)

    # ========== 测试用例 ==========
    def test_deficit_increment(self):
        """国库为负时赤字计数增加"""
        self.state.treasury = -10
        self.state._treasury_deficit_turns = 1
        cmd = ResolutionCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertEqual(self.state.treasury_deficit_turns, 2)
        self.assertIn("国库赤字（第2回合）", output)

    def test_deficit_reset(self):
        """国库非负时赤字计数重置"""
        self.state.treasury = 100
        self.state._treasury_deficit_turns = 2
        cmd = ResolutionCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertEqual(self.state.treasury_deficit_turns, 0)
        self.assertNotIn("国库赤字", output)

    def test_bankruptcy_threshold(self):
        """赤字达到阈值时触发破产提示"""
        self.state.treasury = -10
        self.state._treasury_deficit_turns = 2  # 假设阈值为3
        cmd = ResolutionCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertEqual(self.state.treasury_deficit_turns, 3)
        self.assertIn("国库连续3回合赤字", output)

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("resolution")
        cmd = ResolutionCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

    def test_execute_success(self):
        """测试成功执行决议阶段"""
        cmd = ResolutionCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Revolution Phase", output)
        self.assertIn("胜利/失败条件检查", output)

    def test_victory_conditions(self):
        """测试胜利条件检查"""
        # 设置人物为贵族，使其影响力计入元老院
        from src.core.entities.figure import ClassTier
        self.fig1.class_tier = ClassTier.NOBILE
        self.fig2.class_tier = ClassTier.NOBILE
        self.fig1.faction_id = "senate"
        self.fig2.faction_id = "senate"
        self.fig1.influence = 10
        self.fig2.influence = 5

        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("元老院主导派系: 元老院派", output)

    def test_revolution_risk(self):
        """测试革命风险评估（已移除，仅保留胜利条件）"""
        # 此功能已移除，测试仅验证胜利条件输出存在
        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("胜利/失败条件检查", output)
        # 不再包含风险提示
        self.assertNotIn("Revolution Risk Assessment", output)

    def test_contract_expiration(self):
        """测试合同过期逻辑（无输出）"""
        from src.core.entities.entities import Province

        province1 = Province(1, "Province1", 1000)
        province2 = Province(2, "Province2", 1000)
        self.state.add_province(province1)
        self.state.add_province(province2)

        # 创建过期合同（4回合前创建）
        contract_expired = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=100,
            current_turn=self.state.turn.turn_number - 4
        )
        contract_expired.status = ContractStatus.PENDING
        contract_expired._created_turn = self.state.turn.turn_number - 4

        # 创建未过期合同（1回合前创建）
        contract_pending = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=2,
            base_cost=100,
            current_turn=self.state.turn.turn_number - 1
        )
        contract_pending.status = ContractStatus.PENDING
        contract_pending._created_turn = self.state.turn.turn_number - 1

        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 验证合同状态已改变（后台逻辑）
        self.assertEqual(contract_expired.status, ContractStatus.EXPIRED)
        self.assertEqual(contract_pending.status, ContractStatus.PENDING)
        # 输出中不应包含过期信息
        self.assertNotIn("expired", output.lower())

    def test_contract_summary(self):
        """测试合同摘要（已移除）"""
        from src.core.entities.entities import Province

        province = Province(1, "Province1", 1000)
        self.state.add_province(province)

        active_contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=100,
            current_turn=self.state.turn.turn_number - 2
        )
        active_contract.status = ContractStatus.ACTIVE
        active_contract.remaining_years = 2
        active_contract.expected_profit = 20
        active_contract.duration_years = 2

        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 输出中不应包含合同摘要
        self.assertNotIn("Active Contracts", output)

    def test_annual_decay(self):
        """测试年度衰减（后台执行，无输出）"""
        # 记录初始值
        pop1 = self.fig1.popularity
        vet1 = self.fig1.veterans
        age1 = self.fig1.age

        pop2 = self.fig2.popularity
        vet2 = self.fig2.veterans
        age2 = self.fig2.age

        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 验证衰减已发生（人气降50%，老兵降20%，年龄+1）
        # 注意：由于取整，可能会有1的误差，我们使用近似检查
        self.assertLess(self.fig1.popularity, pop1)
        self.assertLess(self.fig1.veterans, vet1)
        self.assertEqual(self.fig1.age, age1 + 1)

        self.assertLess(self.fig2.popularity, pop2)
        self.assertLess(self.fig2.veterans, vet2)
        self.assertEqual(self.fig2.age, age2 + 1)

        # 输出中不应包含衰减信息
        self.assertNotIn("Annual Decay", output)

    def test_prepare_next_year(self):
        """测试准备下一年（方法无输出，仅验证可调用）"""
        cmd = ResolutionCommand(self.state)
        # 直接调用私有方法，确保不抛出异常
        try:
            cmd._prepare_next_year(verbose=False)
        except Exception as e:
            self.fail(f"_prepare_next_year raised exception: {e}")

    def test_active_wars_in_report(self):
        """测试年度报告中显示活跃战争（已移除）"""
        mock_war = MagicMock()
        mock_war.name = "Gallic War"
        self.state.get_active_wars = MagicMock(return_value=[mock_war])

        cmd = ResolutionCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 输出中不应包含战争信息
        self.assertNotIn("Ongoing Conflicts", output)
        self.assertNotIn("Gallic War", output)


if __name__ == "__main__":
    unittest.main()