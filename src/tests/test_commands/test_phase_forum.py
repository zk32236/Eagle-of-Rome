# src/tests/test_commands/test_phase_forum.py
"""
广场阶段命令单元测试
"""
# src/tests/test_commands/test_phase_forum.py
"""
广场阶段命令单元测试
"""

import unittest
import sys
import os
import io
import random  # 可能需要的，虽然当前测试未直接使用
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from src.core.deciders.retirement_decider import RetirementDecider
from src.core.deciders.recruitment_decider import RecruitmentDecider  # 新增
from src.core.entities.curia import Curia

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_forum import ForumCommand
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn, Province  # 确保 Faction 在这里导入
from src.core.entities.contract import ContractType, Contract



class TestForumCommand(unittest.TestCase):
    """广场阶段命令测试类"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.get_pending_land_acts = MagicMock(return_value=[])

        # 添加行省
        from src.core.entities.entities import Province
        italy = Province(0, "意大利", 0)
        italy._land_public = 1000
        self.state.add_province(italy)
        province = Province(1, "西西里", 1000)
        self.state.add_province(province)

        # 标记 revenue 已执行
        self.state.mark_phase_executed("revenue")

    def test_execute_success(self):
        """测试成功执行广场阶段"""
        self.state.get_pending_land_acts = MagicMock(return_value=[])
        cmd = ForumCommand(self.state)

        # 捕获输出
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Forum Phase", output)
        self.assertIn("new figure(s) arrive", output)   # 新增检查

        # 验证合同列表增加了
        self.assertGreater(len(self.state.contracts), 0)

        # 验证阶段标记
        self.assertTrue(self.state.is_phase_executed("forum"))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        # 确保 state 模拟了 get_pending_land_acts
        self.state.get_pending_land_acts = MagicMock(return_value=[])
        cmd = ForumCommand(self.state)
        cmd.execute([])  # 第一次执行

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result)
        self.assertIn("广场阶段在本回合已执行过", output)

    @patch('random.randint')
    def test_generate_figures(self, mock_randint):
        """测试新人物生成逻辑"""
        # 模拟配置，使生成人物数量为2
        with patch.object(self.state.config, 'get', return_value={"new_figures_count": 2}) as mock_get:
            # 原有的随机数模拟（用于阶层概率等）
            mock_randint.side_effect = [2] + [30] * 100

            cmd = ForumCommand(self.state)
            new_figures = cmd._generate_new_figures()

            # 验证生成数量为2
            self.assertEqual(len(new_figures), 2)
            # 验证配置被正确读取
            mock_get.assert_called_with("forum_rules", {})

    @patch('random.randint')
    def test_generate_contracts(self, mock_randint):
        """测试合同生成逻辑"""
        # 控制随机数以生成特定的成本和利润（实际生成中不使用随机，但保留模拟）
        mock_randint.side_effect = [30, 15, 40]

        cmd = ForumCommand(self.state)
        new_contracts = cmd._generate_contracts()

        self.assertEqual(len(new_contracts), 3)
        # 根据当前生成顺序：
        # 0: 意大利工程 (public_works, base_cost=12)
        # 1: 西西里包税 (tax_farming, base_cost=24)
        # 2: 西西里工程 (public_works, base_cost=7)
        self.assertEqual(new_contracts[0].contract_type.value, "public_works")
        self.assertEqual(new_contracts[0].base_cost, 12)
        self.assertEqual(new_contracts[1].contract_type.value, "tax_farming")
        self.assertEqual(new_contracts[1].base_cost, 24)
        self.assertEqual(new_contracts[2].contract_type.value, "public_works")
        self.assertEqual(new_contracts[2].base_cost, 7)

    def test_curia_display(self):
        """验证 Curia 显示输出包含人物信息"""
        # 先手动添加一个人物到 Curia
        fig = Figure(id=999, name="Test Figure", faction_id=None)
        self.state.curia.add_figure(fig)

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._display_curia(TerminologyService.get())

        output = f.getvalue()
        self.assertIn("Test Figure", output)
        self.assertIn("ID:999", output)

    def test_contract_display(self):
        """验证合同显示输出包含合同信息"""
        # 使用 create_contract 创建合同（自动注册）
        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=50,
            current_turn=1
        )
        contract.name = "测试行省包税权"

        cmd = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._display_contracts(TerminologyService.get())

        output = f.getvalue()
        self.assertIn("测试行省包税权", output)

    def test_process_retirements(self):
        """测试广场阶段淘汰人物功能"""
        from src.core.entities.entities import Faction
        from src.core.entities.figure import Figure
        from src.core.entities.entities import GameTurn

        # 创建测试状态
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        # 创建派系
        faction = Faction(id="test", name="测试派", treasury=10)
        state.add_faction(faction)  # 注意：这里应该用 state，不是 self.state

        # 创建两个人物：一个可抛弃，一个不可抛弃（领袖）
        fig1 = Figure(id=101, name="可抛弃", faction_id="test")
        fig1.is_faction_leader = False
        fig1.office = None
        fig1._has_active_contract = False  # 使用私有字段

        fig2 = Figure(id=102, name="不可抛弃", faction_id="test")
        fig2.is_faction_leader = True
        fig2.office = None
        fig2._has_active_contract = False  # 使用私有字段

        state.add_member(fig1)
        state.add_member(fig2)

        faction.member_ids = [101, 102]

        # 创建模拟的退休决策器，固定返回 fig1.id
        mock_decider = MagicMock(spec=RetirementDecider)
        mock_decider.decide_whom_to_retire.return_value = 101

        cmd = ForumCommand(state, retirement_decider=mock_decider)

        # 执行内部方法
        cmd._process_retirements()

        # 验证：fig1 被移出派系，加入 Curia
        self.assertNotIn(101, faction.member_ids)
        self.assertIsNone(fig1.faction_id)
        self.assertTrue(fig1.is_available)
        # 验证 Curia 中包含 fig1
        curia_figures = state.curia.get_all_available()
        self.assertTrue(any(f.id == 101 for f in curia_figures))
        # 验证 fig2 仍在派系中
        self.assertIn(102, faction.member_ids)

        # 验证决策器被调用
        mock_decider.decide_whom_to_retire.assert_called_once_with(faction)

    def test_process_retirements_no_candidate(self):
        """测试无可抛弃人物时，不进行任何操作"""
        from src.core.entities.entities import Faction
        from src.core.entities.figure import Figure
        from src.core.entities.entities import GameTurn

        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        faction = Faction(id="test", name="测试派", treasury=10)
        state.add_faction(faction)

        fig = Figure(id=101, name="唯一人物", faction_id="test")
        fig.is_faction_leader = True  # 领袖，不可抛弃
        fig.office = None
        fig._has_active_contract = False  # 使用私有字段

        state.add_member(fig)
        faction.member_ids = [101]

        mock_decider = MagicMock(spec=RetirementDecider)
        mock_decider.decide_whom_to_retire.return_value = None

        cmd = ForumCommand(state, retirement_decider=mock_decider)
        cmd._process_retirements()

        # 验证没有任何变化
        self.assertIn(101, faction.member_ids)
        self.assertEqual(fig.faction_id, "test")
        self.assertTrue(fig.is_available)  # is_available 默认 True
        self.assertTrue(state.curia.is_empty())

        mock_decider.decide_whom_to_retire.assert_called_once_with(faction)

    def test_recruitment_process(self):
        """测试招募流程：模拟出价并验证派系资金变化"""

        # 创建测试状态
        state = GameState.create_for_testing({})
        from src.core.entities.entities import GameTurn
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        # 创建两个派系
        faction_opt = Faction(id="optimates", name="Optimates", treasury=100)
        faction_pop = Faction(id="populares", name="Populares", treasury=100)
        state.add_faction(faction_opt)
        state.add_faction(faction_pop)

        # 创建两个人人物
        fig1 = Figure(id=101, name="被抛弃者", faction_id=None)
        fig1.abandoned_by = "optimates"  # 被 Optimates 抛弃
        fig1.wealth = 0
        fig2 = Figure(id=102, name="自由人", faction_id=None)
        fig2.wealth = 0
        state.add_member(fig1)
        state.add_member(fig2)

        # 将两人加入 Curia
        state.curia.add_figure(fig1)
        state.curia.add_figure(fig2)

        # 设置派系成员（初始为空，有空缺）
        faction_opt.member_ids = []
        faction_pop.member_ids = []

        # 模拟决策器，返回固定出价
        mock_decider = MagicMock(spec=RecruitmentDecider)

        def decide_bids_side_effect(faction, available, vacancies, state):
            # 只有 Populares 出价 fig2，Optimates 不出价
            if faction.id == "populares":
                return {102: 15}
            return {}

        mock_decider.decide_bids.side_effect = decide_bids_side_effect

        # 创建命令实例，传入模拟的 recruitment_decider
        cmd = ForumCommand(state, recruitment_decider=mock_decider)

        # 执行招募流程
        cmd._process_recruitment()

        # 验证结果
        # fig2 应加入 Populares
        self.assertEqual(fig2.faction_id, "populares")
        self.assertIn(102, faction_pop.member_ids)
        # fig2 财富增加 15
        self.assertEqual(fig2.wealth, 15)
        # Populares 国库减少 15
        self.assertEqual(faction_pop.treasury, 85)

        # fig1 应仍在 Curia，未被招募
        self.assertIsNone(fig1.faction_id)
        self.assertIn(fig1, state.curia.get_all_available())
        # Optimates 国库未变
        self.assertEqual(faction_opt.treasury, 100)

        # 验证 Curia 中只剩下 fig1
        curia_figures = state.curia.get_all_available()
        self.assertEqual(len(curia_figures), 1)
        self.assertEqual(curia_figures[0].id, 101)

        # 验证决策器被正确调用
        self.assertEqual(mock_decider.decide_bids.call_count, 2)

    def test_civil_unrest_tax_trigger(self):
        """测试当包税合同税率超过基础税率时，行省民怨被设为1"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import Contract, ContractType, ContractStatus

        # 创建测试状态
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        # 添加测试行省（非意大利）
        province = Province(1, "西西里", 1000)
        province._grievance = 0
        state.add_province(province)

        # 创建一个已中标的包税合同，税率设为15%（超过基础税率10%）
        contract = Contract(
            id=1,
            contract_type=ContractType.TAX_FARMING,
            name="西西里包税权",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.ACTIVE,
            awarded_to=101
        )
        contract._tax_rate = 0.15  # 设置实际税率
        contract._province_id = 1
        state._contracts_dict[1] = contract

        # 执行民变处理
        cmd = ForumCommand(state)
        cmd._process_civil_unrest()

        # 验证行省民怨变为1
        self.assertEqual(province.grievance, 1)

    def test_civil_unrest_auto_escalation(self):
        """测试行省民怨从1自动升级到2，再到3并输出起义提示"""
        from src.core.entities.entities import Province
        import io
        from contextlib import redirect_stdout

        # 创建测试状态
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        # 添加测试行省，初始民怨=1
        province = Province(1, "西西里", 1000)
        province._grievance = 1
        state.add_province(province)

        cmd = ForumCommand(state)

        # 第一次升级：1→2
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        output = f.getvalue()
        self.assertEqual(province.grievance, 2)
        self.assertNotIn("起义", output)

        # 第二次升级：2→3
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        output = f.getvalue()
        self.assertEqual(province.grievance, 3)
        self.assertIn("爆发平民起义", output)

        # 第三次升级：已起义，不再变化
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        self.assertEqual(province.grievance, 3)

    def test_civil_unrest_italy_ignored(self):
        """测试意大利行省不参与触发和升级"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import Contract, ContractType, ContractStatus

        # 创建测试状态
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        # 添加意大利行省，初始民怨=0
        italy = Province(0, "意大利", 0)
        italy._grievance = 0
        state.add_province(italy)

        # 创建包税合同（税率高于基础）
        contract = Contract(
            id=1,
            contract_type=ContractType.TAX_FARMING,
            name="意大利包税权（不应存在）",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.ACTIVE,
            awarded_to=101
        )
        contract._tax_rate = 0.15
        contract._province_id = 0
        state._contracts_dict[1] = contract

        cmd = ForumCommand(state)
        cmd._process_civil_unrest()

        # 意大利民怨仍为0
        self.assertEqual(italy.grievance, 0)

    def test_civil_unrest_already_revolted(self):
        """测试已起义的行省不再触发和升级"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import Contract, ContractType, ContractStatus

        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        province = Province(1, "西西里", 1000)
        province._grievance = 3  # 已起义
        state.add_province(province)

        contract = Contract(
            id=1,
            contract_type=ContractType.TAX_FARMING,
            name="西西里包税权",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.ACTIVE,
            awarded_to=101
        )
        contract._tax_rate = 0.15
        contract._province_id = 1
        state._contracts_dict[1] = contract

        cmd = ForumCommand(state)
        cmd._process_civil_unrest()

        # 民怨保持3
        self.assertEqual(province.grievance, 3)

    def test_civil_unrest_multiple_contracts(self):
        """测试多个合同作用于同一行省，民怨应设为至少1"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import Contract, ContractType, ContractStatus

        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")

        province = Province(1, "西西里", 1000)
        province._grievance = 0
        state.add_province(province)

        # 创建两个合同，一个税率超限，一个不超限
        contract1 = Contract(
            id=1,
            contract_type=ContractType.TAX_FARMING,
            name="合同1",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.ACTIVE,
            awarded_to=101
        )
        contract1._tax_rate = 0.15
        contract1._province_id = 1
        state._contracts_dict[1] = contract1

        contract2 = Contract(
            id=2,
            contract_type=ContractType.TAX_FARMING,
            name="合同2",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.ACTIVE,
            awarded_to=102
        )
        contract2._tax_rate = 0.05  # 低于基础
        contract2._province_id = 1
        state._contracts_dict[2] = contract2

        cmd = ForumCommand(state)
        cmd._process_civil_unrest()

        # 民怨应设为1（至少1）
        self.assertEqual(province.grievance, 1)

    def test_italy_unrest_trigger(self):
        """测试意大利本土连续未分地达到阈值时触发民怨升级"""
        from src.core.entities.entities import Province
        import io
        from contextlib import redirect_stdout

        # 创建测试状态，设置配置阈值
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")
        # 注入配置
        state.config._config = {
            "economic_rules": {
                "italy_unrest_trigger_turns": 2
            }
        }

        # 获取意大利行省（手动创建）
        italy = Province(0, "意大利", 0)
        italy._grievance = 0
        italy._turns_since_last_land_distribution = 0
        state.add_province(italy)

        cmd = ForumCommand(state)

        # 第一回合：未达阈值，不应升级
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        self.assertEqual(italy.grievance, 0)

        # 第二回合：计数器变为1，仍未达阈值
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        self.assertEqual(italy.grievance, 0)

        # 第三回合：计数器变为2，达到阈值，触发升级至1
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        output = f.getvalue()
        self.assertEqual(italy.grievance, 1)
        self.assertIn("意大利本土因长期未分地，民怨升至 1 级", output)

    def test_italy_unrest_trigger(self):
        """测试意大利本土连续未分地达到阈值时触发民怨升级"""
        from src.core.entities.entities import Province
        import io
        from contextlib import redirect_stdout

        # 创建测试状态，设置配置阈值
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        state.mark_phase_executed("revenue")
        # 注入配置
        state.config._config = {
            "economic_rules": {
                "italy_unrest_trigger_turns": 2
            }
        }

        # 获取意大利行省（手动创建）
        italy = Province(0, "意大利", 0)
        italy._grievance = 0
        italy._turns_since_last_land_distribution = 0
        state.add_province(italy)

        cmd = ForumCommand(state)

        # 第一回合：未达阈值，不应升级
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        self.assertEqual(italy.grievance, 0)

        # 第二回合：计数器变为1，再加1后达到阈值，触发升级至1
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        output = f.getvalue()
        self.assertEqual(italy.grievance, 1)  # 修正：应为1
        self.assertIn("意大利本土因长期未分地，民怨升至 1 级", output)

        # 第三回合：自动升级到2
        f = io.StringIO()
        with redirect_stdout(f):
            cmd._process_civil_unrest()
        output = f.getvalue()
        self.assertEqual(italy.grievance, 2)  # 修正：应为2
        self.assertIn("意大利本土 民怨升级至 2 级", output)

    def test_auto_land_trade_success(self):
        """测试自动土地交易成功执行"""
        # 准备模拟数据
        seller = Figure(id=1, name="Seller", faction_id="senate", class_tier=ClassTier.NOBILE, wealth=100)
        seller._land_private = 5
        buyer = Figure(id=2, name="Buyer", faction_id="senate", class_tier=ClassTier.EQUES, wealth=100)
        buyer._land_private = 0
        self.state.add_member(seller)
        self.state.add_member(buyer)

        # 模拟决策器返回交易
        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = (1, 2, 3)

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("自动土地交易执行成功", output)
        self.assertEqual(seller.land_private, 2)  # 5-3
        self.assertEqual(buyer.land_private, 3)

    def test_auto_land_trade_failure(self):
        """测试自动土地交易失败（如财富不足）"""
        seller = Figure(id=1, name="Seller", faction_id="senate", class_tier=ClassTier.NOBILE, wealth=100)
        seller._land_private = 5
        buyer = Figure(id=2, name="Buyer", faction_id="senate", class_tier=ClassTier.EQUES, wealth=10)  # 财富不足
        buyer._land_private = 0
        self.state.add_member(seller)
        self.state.add_member(buyer)

        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = (1, 2, 3)

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("自动土地交易失败", output)
        self.assertEqual(seller.land_private, 5)  # 未变化
        self.assertEqual(buyer.wealth, 10)

    def test_auto_land_trade_no_opportunity(self):
        """测试没有交易机会时跳过"""
        mock_trade_decider = MagicMock()
        mock_trade_decider.decide_trade.return_value = None

        cmd = ForumCommand(self.state, land_trade_decider=mock_trade_decider)

        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        self.assertIn("没有合适的土地交易机会", output)

if __name__ == "__main__":
    unittest.main()