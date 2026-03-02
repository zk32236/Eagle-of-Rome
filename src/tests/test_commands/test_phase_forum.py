# src/tests/test_commands/test_phase_forum.py
"""广场阶段命令单元测试 - 适配新打印布局"""

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
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.ui.commands.phase_forum import ForumCommand
from src.core.deciders.impl.auto_land_trade_decider import AutoLandTradeDecider
from src.core.localization import TerminologyService


class TestForumCommand(unittest.TestCase):
    """广场阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {
            "forum_rules": {
                "new_figures_count": 2,
                "class_probabilities": {"nobile": 0.5, "eques": 0.3, "plebeian": 0.2}
            },
            "economic_rules": {
                "faction_member_limit": 6,
                "land_price_per_unit": 10,
                "province_tax_rate": 0.1
            },
            "enable_threats": True
        }
        self.state = GameState.create_for_testing(test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("revenue")

        # 添加测试派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=100, is_player=True)
        self.faction2 = Faction(id="plebs", name="平民派", treasury=80)
        self.faction3 = Faction(id="equites", name="骑士派", treasury=60)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)
        self.state.add_faction(self.faction3)

        # 添加测试人物到派系
        self.fig1 = Figure(id=1, name="元老A", faction_id="senate", class_tier=ClassTier.NOBILE, age=40, wealth=50)
        self.fig1._land_private = 5
        self.fig1.martial = 5
        self.fig1.intelligence = 6
        self.fig1.charisma = 7
        self.fig1.zeal = 4
        self.state.add_member(self.fig1)
        self.faction1.member_ids.append(1)

        self.fig2 = Figure(id=2, name="平民B", faction_id="plebs", class_tier=ClassTier.PLEBEIAN, age=30, wealth=20)
        self.fig2.martial = 3
        self.fig2.intelligence = 4
        self.fig2.charisma = 5
        self.fig2.zeal = 6
        self.state.add_member(self.fig2)
        self.faction2.member_ids.append(2)

        # 添加意大利行省
        italy = Province(0, "意大利", 0)
        italy._land_public = 1000
        self.state.add_province(italy)

    # ========== 测试用例 ==========

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        self.state.mark_phase_executed("forum")
        cmd = ForumCommand(self.state)
        result = cmd.execute([])
        self.assertFalse(result)

    def test_execute_success(self):
        """测试成功执行广场阶段"""
        cmd = ForumCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 检查区块标题
        self.assertIn("安民告示", output)
        self.assertIn("人才市场", output)
        self.assertIn("合同拍卖", output)
        self.assertIn("土地交易", output)

    @unittest.skip("新布局不再显示所有Curia人物列表，此测试暂时跳过")
    def test_curia_display(self):
        """验证广场人物显示（已跳过）"""
        pass

    def test_contract_display(self):
        """验证合同显示包含在输出中"""
        # 创建一个待决合同
        province = Province(1, "西西里", 1000)
        self.state.add_province(province)
        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=30,
            current_turn=1
        )
        contract.status = ContractStatus.PENDING
        contract.name = "西西里包税权"

        cmd = ForumCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("合同拍卖", output)
        self.assertIn("西西里包税权", output)

    def test_generate_contracts(self):
        """测试合同生成功能"""
        # 添加行省
        for pid, name in [(1, "西西里"), (2, "撒丁尼亚")]:
            province = Province(pid, name, 1000)
            self.state.add_province(province)

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        # 检查是否有新合同生成提示
        self.assertIn("新", output)
        self.assertGreater(len(self.state.get_all_contracts()), 0)

    def test_generate_figures(self):
        """测试新人物生成"""
        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("new figure(s) arrive", output)

    def test_process_retirements(self):
        """测试人物淘汰"""
        # 确保派系中有可淘汰人物
        eligible = Figure(id=3, name="可抛弃", faction_id="senate", class_tier=ClassTier.EQUES, age=35)
        eligible.office = None
        eligible._has_active_contract = False
        eligible.martial = 2
        eligible.intelligence = 3
        eligible.charisma = 4
        eligible.zeal = 5
        self.state.add_member(eligible)
        self.faction1.member_ids.append(3)

        # 创建模拟退休决策器，始终返回该人物ID
        mock_retirement_decider = MagicMock()
        mock_retirement_decider.decide_whom_to_retire.return_value = 3

        cmd = ForumCommand(self.state, retirement_decider=mock_retirement_decider)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("抛弃了", output)

    def test_process_retirements_no_candidate(self):
        """测试无合格候选人时跳过"""
        # 所有成员都不符合条件（如都是领袖）
        for fig in self.state.get_living_members():
            fig.is_faction_leader = True

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("无人物被抛弃", output)

    def test_recruitment_process(self):
        """测试招募流程"""
        # 添加人物到Curia
        recruit = Figure(id=100, name="自由人", faction_id=None, class_tier=ClassTier.EQUES, age=30, wealth=0)
        recruit.martial = 4
        recruit.intelligence = 5
        recruit.charisma = 6
        recruit.zeal = 7
        self.state.curia.add_figure(recruit)

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("招募出价情况", output)

    def test_italy_unrest_trigger(self):
        """测试意大利本土民怨触发"""
        italy = self.state.get_province(0)
        italy._grievance = 0
        italy._turns_since_last_land_distribution = 2
        self.state.config._config["economic_rules"] = {"italy_unrest_trigger_turns": 3}

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()

        # 2+1=3，达到阈值，应升级
        self.assertIn("意大利本土因长期未分地，民怨升至 1 级", output)
        self.assertEqual(italy.grievance, 1)

    def test_civil_unrest_tax_trigger(self):
        """测试包税合同超税率触发民怨"""
        province = Province(1, "西西里", 1000)
        province._grievance = 0
        self.state.add_province(province)

        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=24,
            current_turn=1
        )
        contract.status = ContractStatus.ACTIVE
        contract._winning_bid = {"bidder_id": 1, "amount": 28, "tax_rate": 0.15}
        contract._tax_rate = 0.15  # 直接设置属性
        contract._annual_profit = 5
        contract.awarded_to = 1

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()

        self.assertIn("因包税合同税率 15% > 10%，民怨升至 1 级", output)
        self.assertEqual(province.grievance, 1)

    def test_civil_unrest_already_revolted(self):
        """测试已起义的行省不再触发和升级"""
        province = Province(1, "西西里", 1000)
        province._grievance = 3
        self.state.add_province(province)

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()

        # 不应有升级提示
        self.assertNotIn("行省 西西里 民怨升级", output)
        self.assertEqual(province.grievance, 3)

    def test_civil_unrest_auto_escalation(self):
        """测试行省民怨自动升级"""
        province = Province(1, "西西里", 1000)
        province._grievance = 1
        self.state.add_province(province)

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()
        self.assertIn("行省 西西里 民怨升级至 2 级", output)
        self.assertEqual(province.grievance, 2)

    def test_civil_unrest_italy_ignored(self):
        """测试意大利行省不参与合同触发，但未分地自动升级仍然进行"""
        italy = self.state.get_province(0)
        italy._grievance = 1
        italy._turns_since_last_land_distribution = 0  # 默认0

        # 创建一个意大利的包税合同（实际不应存在，但测试逻辑）
        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=0,
            base_cost=24,
            current_turn=1
        )
        contract.status = ContractStatus.ACTIVE
        contract._winning_bid = {"bidder_id": 1, "amount": 28, "tax_rate": 0.15}
        contract._tax_rate = 0.15
        contract._annual_profit = 5
        contract.awarded_to = 1

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()

        # 不应因合同而触发意大利民怨提示
        self.assertNotIn("因包税合同税率", output)
        # 但意大利民怨会自动升级（从1升到2）
        self.assertEqual(italy.grievance, 2)
        self.assertIn("意大利本土 民怨升级至 2 级", output)

    def test_civil_unrest_multiple_contracts(self):
        """测试多个合同作用于同一行省"""
        province = Province(1, "西西里", 1000)
        province._grievance = 0
        self.state.add_province(province)

        contract1 = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=24,
            current_turn=1
        )
        contract1.status = ContractStatus.ACTIVE
        contract1._winning_bid = {"bidder_id": 1, "amount": 28, "tax_rate": 0.15}
        contract1._tax_rate = 0.15
        contract1._annual_profit = 5
        contract1.awarded_to = 1

        contract2 = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=20,
            current_turn=1
        )
        contract2.status = ContractStatus.ACTIVE
        contract2._winning_bid = {"bidder_id": 2, "amount": 21, "tax_rate": 0.05}
        contract2._tax_rate = 0.05
        contract2._annual_profit = 4
        contract2.awarded_to = 2

        cmd = ForumCommand(self.state)
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            cmd._print_civil_unrest()
        output = mock_stdout.getvalue()

        # 应看到税率超限的提示，且民怨设为1
        self.assertIn("因包税合同税率 15% > 10%，民怨升至 1 级", output)
        self.assertEqual(province.grievance, 1)

    def test_auto_land_trade_success(self):
        """测试自动土地交易成功"""
        seller = Figure(id=10, name="卖家", faction_id="senate", class_tier=ClassTier.NOBILE, wealth=100)
        seller._land_private = 5
        buyer = Figure(id=11, name="买家", faction_id="equites", class_tier=ClassTier.EQUES, wealth=100)
        buyer._land_private = 0
        self.state.add_member(seller)
        self.state.add_member(buyer)

        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = (10, 11, 3)

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("自动土地交易执行成功", output)
        # 验证土地转移
        self.assertEqual(seller.land_private, 2)
        self.assertEqual(buyer.land_private, 3)

    def test_auto_land_trade_failure(self):
        """测试自动土地交易失败（如财富不足）"""
        seller = Figure(id=10, name="卖家", faction_id="senate", class_tier=ClassTier.NOBILE, wealth=100)
        seller._land_private = 5
        buyer = Figure(id=11, name="买家", faction_id="equites", class_tier=ClassTier.EQUES, wealth=10)  # 财富不足
        buyer._land_private = 0
        self.state.add_member(seller)
        self.state.add_member(buyer)

        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = (10, 11, 3)

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("自动土地交易失败", output)
        self.assertEqual(seller.land_private, 5)  # 未变化
        self.assertEqual(buyer.wealth, 10)

    def test_auto_land_trade_no_opportunity(self):
        """测试没有交易机会时跳过（不打印任何交易信息）"""
        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = None

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertNotIn("自动土地交易", output)


if __name__ == "__main__":
    unittest.main()