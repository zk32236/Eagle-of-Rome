# src/tests/test_commands/test_phase_revenue.py
"""税收阶段命令单元测试 - 适配当前打印格式"""

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
from src.core.entities.entities import GameTurn, Province, Faction
from src.core.entities.figure import Figure
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.ui.commands.phase_revenue import RevenueCommand
from src.core.localization import TerminologyService


class TestRevenueCommand(unittest.TestCase):
    """税收阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {
            "economic_rules": {
                "land_price_per_unit": 10,
                "national_public_land_tax_rate": 0.02,
                "faction_stipend": 10,
                "faction_tax_rate": 0.1,
                "private_land_income_rate": 0.05,
                "base_tax": 100
            }
        }
        self.state = GameState.create_for_testing(test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("mortality")

        # 添加测试派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=50)
        self.faction2 = Faction(id="plebs", name="平民派", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 添加测试人物
        self.figure = Figure(id=1, name="测试人物", faction_id="senate", age=30, wealth=100)
        self.figure._land_private = 10  # 私地10
        self.state.add_member(self.figure)

        # 添加意大利行省（用于国家公地）
        italy = Province(0, "意大利", 0)
        italy._land_public = 1000
        self.state.add_province(italy)

    def test_national_opex_deduction(self):
        """测试国家运营费正常扣除"""
        self._setup_mock_military_system()

        # 创建两个已征服行省
        province1 = Province(1, "西西里", total_land=1000)
        province1._conquered = True
        province2 = Province(2, "撒丁岛", total_land=2000)
        province2._conquered = True
        self.state.add_province(province1)
        self.state.add_province(province2)

        self.state.treasury = 1000  # 手动设置国库，避免其他收入干扰
        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        land_price = 10
        rate = 0.003
        expected_opex = int((1000 + 2000) * land_price * rate)  # 90
        # 国家公地收益：1000 * 10 * 0.02 = 200
        expected_treasury = 1000 + 200 - expected_opex  # 1110
        self.assertEqual(self.state.treasury, expected_treasury)
        self.assertIn("国家运营费计算", output)
        self.assertIn(f"运营费 = {expected_opex}", output)
        self.assertEqual(self.state.treasury_deficit_turns, 0)  # 赤字计数不变

    def test_no_conquered_provinces(self):
        """测试无已征服行省时运营费为0"""
        self._setup_mock_military_system()

        # 创建两个未征服行省
        province1 = Province(1, "未征服1", total_land=1000)
        province1._conquered = False
        province2 = Province(2, "未征服2", total_land=2000)
        province2._conquered = False
        self.state.add_province(province1)
        self.state.add_province(province2)

        self.state.treasury = 1000
        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        # 国家公地初始1000，收益200，因此最终国库应为 1000 + 200 = 1200
        self.assertEqual(self.state.treasury, 1200)
        self.assertIn("无已征服行省，国家运营费为 0", output)

    def _setup_mock_military_system(self):
        """创建并设置模拟的军事系统"""
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (True, "")
        mock_ms.get_military_summary.return_value = "Military summary"
        mock_ms.calculate_maintenance.return_value = (0, {})  # 关键修复
        self.state._military_system = mock_ms
        return mock_ms

    def _create_real_contracts(self):
        """创建真实的包税和工程合同用于测试"""
        # 创建行省
        province = Province(1, "测试行省", 1000)
        self.state.add_province(province)

        # 创建包税合同
        tax_contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=80,
            current_turn=self.state.turn.turn_number - 1
        )
        tax_contract.status = ContractStatus.ACTIVE
        tax_contract._winning_bid = {"bidder_id": 1, "amount": 80, "tax_rate": 0.1}
        tax_contract._annual_profit = 20
        tax_contract.remaining_years = 5
        tax_contract.awarded_to = 1
        tax_contract.awarded_faction = "senate"

        # 创建工程合同
        works_contract = self.state.create_contract(
            ContractType.PUBLIC_WORKS,
            province_id=1,
            base_cost=800,
            current_turn=self.state.turn.turn_number - 1
        )
        works_contract.status = ContractStatus.ACTIVE
        works_contract.awarded_to = 1
        works_contract.awarded_faction = "senate"
        works_contract._original_budget = 800
        works_contract._construction_years = 3
        works_contract._warranty_years = 10
        works_contract._annual_income = 267
        works_contract._annual_cost = 200
        works_contract.remaining_years = 3
        works_contract.total_spent = 0

        return tax_contract, works_contract

    # ========== 测试用例 ==========

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("revenue")
        cmd = RevenueCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

    def test_execute_success(self):
        """测试成功执行税收阶段"""
        self._setup_mock_military_system()
        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Revenue Phase", output)
        self.assertIn("国家公地收益", output)
        self.assertIn("派系金库收益", output)
        self.assertIn("元老院派", output)
        self.assertIn("财政拨款", output)
        self.assertIn("会员贡献", output)
        self.assertIn("现有资金", output)
        self.assertIn("地主私人收益", output)

    def test_contract_revenue(self):
        """测试合同收益处理（逻辑验证）"""
        self._setup_mock_military_system()
        tax_contract, works_contract = self._create_real_contracts()

        figure = self.state.get_member(1)
        initial_wealth = figure.wealth
        initial_treasury = self.state.treasury  # 初始国库为0

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)

        # 私地收入：10*10*0.05=5，抽成0.5，净收入4.5 round(4.5)=4
        # 包税合同利润20，抽成2，净收入18
        # 工程合同利润67，抽成6.7，净收入60.3 round=60
        expected_wealth_increase = 4 + 18 + 60
        self.assertEqual(figure.wealth, initial_wealth + expected_wealth_increase)

        # 国库变化：初始0 + 国家公地200 + 包税国库收入80 - 工程支付267 = 13
        self.assertEqual(self.state.treasury, initial_treasury + 200 + 80 - 267)

        # 验证工程合同的成本设置正确
        self.assertEqual(works_contract._annual_cost, 200)
        self.assertEqual(works_contract._annual_income, 267)

        # 验证输出中包含派系表格
        self.assertIn("派系金库收益", output)

    def test_no_contracts(self):
        """测试无合同时税收阶段仍正常执行"""
        self._setup_mock_military_system()
        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("国家公地收益", output)
        self.assertIn("派系金库收益", output)

    def test_faction_tax_deduction(self):
        """测试派系抽成是否正确计入派系金库"""
        self._setup_mock_military_system()
        initial_faction_treasury = self.faction1.treasury  # 应为50

        cmd = RevenueCommand(self.state)
        cmd.execute([])

        # 私地收入5，抽成0.5 → 派系抽成0（四舍五入后为0）
        # 派系津贴+10
        expected_treasury = initial_faction_treasury + 10
        self.assertEqual(self.faction1.treasury, expected_treasury)

    def test_insufficient_treasury_no_crash(self):
        """测试国库不足时不会崩溃"""
        self.state.treasury = -10
        self._setup_mock_military_system()
        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])  # 不应抛出异常
        self.assertTrue(result)

    def test_military_maintenance_failure(self):
        """测试军事维护失败场景（国库不足导致解散军团）"""
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (False, "")
        mock_ms.get_military_summary.return_value = "Military summary"
        mock_ms.calculate_maintenance.return_value = (0, {})
        self.state._military_system = mock_ms

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        mock_ms.apply_maintenance.assert_called_once_with(verbose=False)
        self.assertNotIn("Treasury shortfall", output)

    def test_military_maintenance_success(self):
        """测试军事维护成功"""
        mock_ms = MagicMock()
        mock_ms.apply_maintenance.return_value = (True, "")
        mock_ms.get_military_summary.return_value = "Military summary"
        mock_ms.calculate_maintenance.return_value = (0, {})
        self.state._military_system = mock_ms

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        mock_ms.apply_maintenance.assert_called_once_with(verbose=False)

    def test_contract_revenue_dead_contractor(self):
        """测试承包商死亡时的合同处理"""
        self._setup_mock_military_system()

        # 创建测试人物并标记死亡
        fig = Figure(id=2, name="Dead Contractor", faction_id="senate", wealth=100)
        fig.is_dead = True
        self.state.add_member(fig)

        # 添加行省
        province = Province(2, "测试行省2", 1000)
        self.state.add_province(province)

        # 创建合同并模拟中标者死亡
        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=2,
            base_cost=80,
            current_turn=self.state.turn.turn_number - 1
        )
        contract.status = ContractStatus.ACTIVE
        contract._winning_bid = {"bidder_id": 2, "amount": 80, "tax_rate": 0.1}
        contract._annual_profit = 20
        contract.awarded_to = 2

        cmd = RevenueCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 验证合同已终止
        self.assertEqual(contract.status, ContractStatus.EXPIRED)
        # 验证行省已解绑
        self.assertIsNone(province.tax_contract_id)


if __name__ == "__main__":
    unittest.main()