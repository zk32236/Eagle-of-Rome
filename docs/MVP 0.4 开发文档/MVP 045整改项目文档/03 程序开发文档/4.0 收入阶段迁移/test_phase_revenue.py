# src/tests/test_commands/test_phase_revenue.py
"""
税收阶段命令单元测试
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, call
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_revenue import RevenueCommand
from src.core.entities.contract import Contract, ContractType, ContractStatus


class TestRevenueCommand(unittest.TestCase):
    """税收阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {
            "economic_rules": {
                "base_tax": 100,
                "faction_stipend": 10,
                "legion_recruit_cost": 10,
                "legion_maintenance_base": 2,
                "veteran_maintenance_bonus": 1
            }
        }
        self.state = GameState.create_for_testing(test_config)

        # 添加测试派系
        from src.core.entities.entities import Faction
        self.faction1 = Faction(id="senate", name="元老院派", treasury=50)
        self.faction2 = Faction(id="populares", name="平民派", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 设置回合
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

        # 设置国库初始值
        self.state._treasury = 100

    # ===== 辅助方法 =====
    def _setup_mock_military_system(self):
        """创建并设置模拟的军事系统"""
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (True, "Paid 10 Talents for legion maintenance")
        mock_ms.get_military_summary.return_value = "Military summary"
        self.state._military_system = mock_ms
        return mock_ms

    def _setup_mock_contracts(self):
        """创建并设置模拟的合同"""
        from src.core.entities.figure import Figure
        fig = Figure(id=1, name="Test Contractor", faction_id="senate", wealth=100)
        self.state.add_member(fig)

        # 创建模拟的包税合同
        tax_contract = MagicMock(spec=Contract)
        tax_contract.contract_type = ContractType.TAX_FARMING
        tax_contract.status = ContractStatus.ACTIVE
        tax_contract.awarded_to = 1
        tax_contract.name = "西西里包税权"
        tax_contract.execute_tax_collection.return_value = 20
        tax_contract.total_collected = 20

        # 创建模拟的工程合同
        works_contract = MagicMock(spec=Contract)
        works_contract.contract_type = ContractType.PUBLIC_WORKS
        works_contract.status = ContractStatus.ACTIVE
        works_contract.awarded_to = 1
        works_contract.name = "罗马大道工程"
        works_contract.base_cost = 100
        works_contract.duration_years = 2
        works_contract.execute_works_payment.return_value = 10
        works_contract.total_spent = 50

        self.state._contracts = [tax_contract, works_contract]
        return [tax_contract, works_contract]

    # ===== 测试用例 =====

    def test_execute_success(self):
        """测试成功执行税收阶段"""
        # 设置模拟的军事系统
        mock_ms = self._setup_mock_military_system()

        cmd = RevenueCommand(self.state)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Revenue Phase", output)
        self.assertIn("Base tax: +100", output)
        self.assertIn("元老院派: +10", output)
        self.assertIn("平民派: +10", output)
        # 国库应为初始100 + 税收100 = 200（维护费未模拟扣除）
        self.assertIn("State Treasury: 200", output)
        # 验证国库属性
        self.assertEqual(self.state.treasury, 200)

        # 验证派系资金更新
        self.assertEqual(self.faction1.treasury, 60)   # 50 + 10
        self.assertEqual(self.faction2.treasury, 40)   # 30 + 10

        # 验证军事系统被调用
        mock_ms.apply_maintenance.assert_called_once()

        # 验证阶段被标记
        self.assertTrue(self.state.is_phase_executed("revenue"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = RevenueCommand(self.state)

        # 第一次执行
        result1 = cmd.execute([])
        self.assertTrue(result1)

        # 第二次执行
        f = io.StringIO()
        with redirect_stdout(f):
            result2 = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result2)
        self.assertIn("税收阶段在本回合已执行过", output)

    def test_military_maintenance_success(self):
        """测试军事维护成功场景"""
        mock_ms = self._setup_mock_military_system()

        cmd = RevenueCommand(self.state)
        cmd.execute([])

        mock_ms.apply_maintenance.assert_called_once()

    def test_military_maintenance_failure(self):
        """测试军事维护失败场景（国库不足导致解散军团）"""
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (False, "Treasury shortfall! 2 legion(s) disbanded")
        mock_ms.get_military_summary.return_value = "Military summary"
        self.state._military_system = mock_ms

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)  # 命令仍应成功，只是维护失败
        self.assertIn("⚠️ Treasury shortfall! 2 legion(s) disbanded", output)
        mock_ms.apply_maintenance.assert_called_once()

    def test_contract_revenue(self):
        """测试合同收益处理"""
        # 设置模拟的军事系统（避免干扰）
        self._setup_mock_military_system()

        # 设置模拟的合同
        tax_contract, works_contract = self._setup_mock_contracts()

        # 获取测试人物
        figure = self.state.get_member(1)
        initial_wealth = figure.wealth

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)

        # 验证包税合同调用
        tax_contract.execute_tax_collection.assert_called_once()
        # 验证工程合同调用
        works_contract.execute_works_payment.assert_called_once()

        # 验证人物财富增加（包税20 + 工程10 = 30）
        self.assertEqual(figure.wealth, initial_wealth + 30)

        # 验证国库支付了工程预算（100//2 = 50）
        # 国库初始100 + 税收100 = 200，再减去50 = 150
        self.assertEqual(self.state.treasury, 150)

        # 验证输出包含合同信息
        self.assertIn("Contract Revenues", output)
        self.assertIn("西西里包税权", output)
        self.assertIn("罗马大道工程", output)

    def test_contract_revenue_dead_contractor(self):
        """测试承包商死亡时的合同处理"""
        self._setup_mock_military_system()

        # 创建测试人物并标记死亡
        from src.core.entities.figure import Figure
        fig = Figure(id=2, name="Dead Contractor", faction_id="senate", wealth=100)
        fig.is_dead = True
        self.state.add_member(fig)

        # 创建模拟合同
        contract = MagicMock(spec=Contract)
        contract.contract_type = ContractType.TAX_FARMING
        contract.status = ContractStatus.ACTIVE
        contract.awarded_to = 2
        contract.name = "死亡合同"
        contract.execute_tax_collection.return_value = 20

        self.state._contracts = [contract]

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Contractor deceased, contract void", output)

        # 验证合同状态被置为EXPIRED
        contract.status = ContractStatus.EXPIRED

    def test_no_contracts(self):
        """测试没有合同时不输出合同部分"""
        self._setup_mock_military_system()
        self.state._contracts = []  # 清空合同

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertNotIn("Contract Revenues", output)

    def test_insufficient_treasury_no_crash(self):
        """测试国库不足时命令不崩溃（只测试边界）"""
        self.state._treasury = 0  # 国库为空

        # 设置军事系统（可能返回失败）
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (False, "Treasury shortfall! 2 legion(s) disbanded")
        mock_ms.get_military_summary.return_value = "Military summary"
        self.state._military_system = mock_ms

        cmd = RevenueCommand(self.state)

        try:
            result = cmd.execute([])
            self.assertTrue(result)  # 命令本身应成功
        except Exception as e:
            self.fail(f"国库不足时命令抛出异常: {e}")

    def test_get_economic_rule_uses_config(self):
        """验证经济规则从配置获取"""
        # 修改配置
        test_config = {
            "economic_rules": {
                "base_tax": 999,
                "faction_stipend": 99
            }
        }
        state = GameState.create_for_testing(test_config)
        from src.core.entities.entities import Faction
        faction = Faction(id="test", name="测试", treasury=0)
        state.add_faction(faction)
        state._treasury = 0
        from src.core.entities.entities import GameTurn
        state.turn = GameTurn(turn_number=1, year=-264)

        cmd = RevenueCommand(state)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])

        # 验证使用了配置中的值
        self.assertEqual(state.treasury, 999)  # 只有税收，没有派系津贴支出
        self.assertEqual(faction.treasury, 99)


if __name__ == "__main__":
    unittest.main()