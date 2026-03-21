# src/tests/test_commands/test_phase_senate.py
"""
元老院阶段命令单元测试
"""

import unittest
import sys
import os
import io
from contextlib import redirect_stdout, redirect_stderr
from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.entities.player import Player
from src.core.entities.war import WarType
from src.core.systems.naval_system import NavalSystem

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.entities.figure import Figure, ClassTier

import unittest
from unittest.mock import MagicMock, patch

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_senate import SenateCommand
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import War, WarStatus
from src.core.game_state import GameState

class TestSenateCommand(unittest.TestCase):
    """元老院阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {}
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

        # 创建一些人物（用于派系领袖和主持人）
        figures = []
        for i, fid in enumerate(["senate", "populares", "equites"]):
            for j in range(3):
                fig = Figure(id=i*10 + j + 1, name=f"{fid}_member_{j}", faction_id=fid, age=40)
                fig.influence = 10 + j
                self.state.add_member(fig)
                figures.append(fig)
                factions[i].member_ids.append(fig.id)

        # 设置领袖（影响力最高者）
        for faction in factions:
            faction.update_faction_leader(self.state)

        # 设置回合
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 200
        self.state.mark_phase_executed("population")

        # 添加合同测试用的行省
        from src.core.entities.province import Province
        province = Province(1, "西西里", 1000)
        self.state.add_province(province)

    def test_execute_success(self):
        """测试成功执行元老院阶段"""
        cmd = SenateCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Senate Phase", output)
        # 新格式使用 "Senate in Meeting" 而非 "Faction Leaders Updated"
        self.assertIn("Senate in Meeting", output)
        # 检查是否有派系领袖信息（可能存在，但不强制）
        # 检查主持人是否存在
        self.assertIn("Presiding Officer", output)
        # 确保阶段正常推进（可检查进度或后续内容）

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

    def test_faction_leaders_updated(self):
        """测试派系领袖更新"""
        cmd = SenateCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        for faction in self.state.factions.values():
            leader = faction.get_leader(self.state)
            self.assertIsNotNone(leader)
            self.assertIn(faction.name, output)
            self.assertIn(leader.name, output)

    def test_presiding_officer(self):
        """测试主持人确定逻辑"""
        cmd = SenateCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        presiding = self.state.get_presiding_officer()
        self.assertIsNotNone(presiding)
        self.assertIn(presiding.name, output)

    def test_governor_appointment_by_type(self):
        """验证总督任命时按 governor_type 正确分类行省"""
        from src.ui.commands.phase_senate import SenateCommand
        from src.core.entities.province import Province
        from src.core.entities.figure import Figure
        from src.core.entities.entities import Faction, GameTurn
        from src.core.game_state import GameState  # 新增导入

        state = GameState.create_for_testing({})
        # 添加测试行省
        province1 = Province(
            province_id=1,
            name="西西里",
            total_land=10000,
            conquered=True,
            governor_type="proconsul"
        )
        province2 = Province(
            province_id=2,
            name="撒丁-科西嘉",
            total_land=16000,
            conquered=True,
            governor_type="propraetor"
        )
        state.add_province(province1)
        state.add_province(province2)

        # 添加候选人（卸任执政官和卸任大法官）
        consul = Figure(id=101, name="Consul Candidate", faction_id="test")
        consul.office_history = [type('Term', (), {'office_type': 'consul', 'end_turn': 5})]
        praetor = Figure(id=102, name="Praetor Candidate", faction_id="test")
        praetor.office_history = [type('Term', (), {'office_type': 'praetor', 'end_turn': 5})]
        state.add_member(consul)
        state.add_member(praetor)

        # 添加派系（不直接设置 leader_id，后续可能需要时再处理）
        faction = Faction(id="test", name="Test Faction", treasury=0)
        # 如果需要 leader，可以后续设置（但当前测试可能不依赖）
        # faction.leader_id = 101  # 假设有可写属性，否则使用 setter
        state.add_faction(faction)

        # 设置回合信息
        state.turn = GameTurn(turn_number=10, year=-270)
        state.turn.leader_ids = [101]

        # 执行总督任命
        cmd = SenateCommand(state)
        cmd._process_governor_appointments(None)

        # 验证提案中的行省类型与候选人对应关系
        self.assertEqual(len(cmd.proposed_governors), 2)
        for prop in cmd.proposed_governors:
            if prop['province_id'] == 1:
                self.assertEqual(prop['new_governor_id'], 101)
            elif prop['province_id'] == 2:
                self.assertEqual(prop['new_governor_id'], 102)

    def test_contract_processing(self):
        """测试合同处理逻辑"""
        # 创建贵族人物（元老）并赋予影响力，确保投票有效
        senator = Figure(id=1000, name="Test Senator", faction_id="senate", age=50)
        senator.class_tier = ClassTier.NOBILE
        senator.influence = 50
        self.state.add_member(senator)
        self.faction1.member_ids.append(1000)

        # 创建待决合同
        tax_contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=30,
            current_turn=self.state.turn.turn_number
        )
        tax_contract.name = "西西里包税权"
        tax_contract.status = ContractStatus.PENDING

        works_contract = self.state.create_contract(
            ContractType.PUBLIC_WORKS,
            province_id=1,
            base_cost=200,
            current_turn=self.state.turn.turn_number
        )
        works_contract.name = "西西里工程"
        works_contract.status = ContractStatus.PENDING

        # 模拟 budget_decider 总是返回所有合同
        mock_budget_decider = MagicMock(spec=AutoBudgetDecider)
        mock_budget_decider.decide_proposals.return_value = [tax_contract, works_contract]

        # 创建 SenateCommand 实例并注入模拟的 budget_decider
        cmd = SenateCommand(self.state, vote_decider=None)  # 使用默认投票决策器
        cmd.budget_decider = mock_budget_decider  # 替换为模拟

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("西西里包税权", output)  # 应出现在输出中
        self.assertIn("西西里工程", output)  # 也应出现

    def test_war_takeover_no_commander(self):
        """测试无指挥官的战争被执政官接管"""
        # 模拟战争系统
        mock_ws = MagicMock()
        # 替换 get_war_system 方法为返回 mock_ws 的模拟方法
        self.state.get_war_system = MagicMock(return_value=mock_ws)

        cmd = SenateCommand(self.state)
        war = MagicMock(spec=War)
        war.id = "test_war"
        war.name = "测试战争"
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        mock_ws.get_active_wars.return_value = [war]

        # 设置执政官
        self.state.turn.leader_ids = [101]
        consul = Figure(id=101, name="执政官", faction_id="senate")
        self.state.add_member(consul)

        # 模拟接管决策器返回 True
        mock_decider = MagicMock()
        mock_decider.decide_takeover.return_value = True
        cmd.takeover_decider = mock_decider

        # 执行
        cmd._process_war_takeover()

        # 验证
        assert war.commander_id == 101
        assert consul.is_absent is True
        mock_decider.decide_takeover.assert_called_once_with(war, consul, None, self.state)

    def test_war_takeover_existing_proconsul(self):
        """测试有 proconsul 指挥官的战争被新执政官接管"""
        # 模拟战争系统
        mock_ws = MagicMock()
        self.state.get_war_system = MagicMock(return_value=mock_ws)

        cmd = SenateCommand(self.state)
        war = MagicMock(spec=War)
        war.id = "test_war"
        war.name = "测试战争"
        war.status = WarStatus.ACTIVE
        war.commander_id = 201
        mock_ws.get_active_wars.return_value = [war]

        self.state.turn.leader_ids = [101]
        consul = Figure(id=101, name="新执政官", faction_id="senate")
        old_cmd = Figure(id=201, name="旧指挥官", faction_id="senate")
        old_cmd.office = "proconsul"
        old_cmd.is_absent = True
        self.state.add_member(consul)
        self.state.add_member(old_cmd)

        mock_decider = MagicMock()
        mock_decider.decide_takeover.return_value = True
        cmd.takeover_decider = mock_decider

        cmd._process_war_takeover()

        assert war.commander_id == 101
        assert consul.is_absent is True
        assert old_cmd.is_absent is False
        assert old_cmd.office == "ex-proconsul"
        mock_decider.decide_takeover.assert_called_once_with(war, consul, old_cmd, self.state)

    """
    测试元老院阶段保民官否决功能
    """

class TestTribuneVeto(unittest.TestCase):
    """测试保民官否决功能"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")

        # 初始化战争系统
        from src.core.systems.war_system import WarSystem
        self.state._war_system = WarSystem(self.state)

        # 添加测试派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=50, is_player=True)
        self.faction2 = Faction(id="populares", name="平民派", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 添加执政官（用于提案）
        self.consul = Figure(id=101, name="执政官", faction_id="senate", age=40)
        self.state.add_member(self.consul)
        self.state.turn.leader_ids = [101]

        # 添加保民官
        self.tribune = Figure(id=102, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.state.add_member(self.tribune)

        # 添加一些元老（用于投票）
        self.senator1 = Figure(id=201, name="元老1", faction_id="senate", age=50)
        self.senator1.influence = 50
        self.state.add_member(self.senator1)
        self.faction1.member_ids.append(201)

        self.senator2 = Figure(id=202, name="元老2", faction_id="populares", age=45)
        self.senator2.influence = 40
        self.state.add_member(self.senator2)
        self.faction2.member_ids.append(202)

        self.senator1.class_tier = ClassTier.NOBILE
        self.senator2.class_tier = ClassTier.NOBILE

        # 模拟投票决策器（始终支持）
        self.mock_vote_decider = MagicMock()
        self.mock_vote_decider.decide_vote.return_value = True

        # 设置土地法案提交概率为100%
        if "political_rules" not in self.state.config._config:
            self.state.config._config["political_rules"] = {}
        if "land_proposal" not in self.state.config._config["political_rules"]:
            self.state.config._config["political_rules"]["land_proposal"] = {}
        self.state.config._config["political_rules"]["land_proposal"]["submit_chance"] = 1.0

        self.state.config._config["testing"] = {
            "propose_war_chance": 1.0,
            "always_declare": True,
            "min_legions": 4,
            "max_legions": 8
        }

    def _create_test_war(self):
        """创建测试用战争，不再通过构造函数传入 status"""
        war = War(id="test_war", name="测试战争")
        war.status = WarStatus.THREAT
        war._threat_level = 2  # 直接设置私有字段（或通过属性，如果有的话）
        return war

    def _create_test_contract(self):
        """创建测试用合同并添加到 state"""
        contract = Contract(
            id=1,
            contract_type=ContractType.TAX_FARMING,
            name="测试合同",
            base_cost=100,
            expected_profit=50,
            status=ContractStatus.PENDING
        )
        self.state._contracts_dict[contract.id] = contract
        return contract

    # ========== 测试用例 ==========

    def test_tribune_veto_war_passed(self):
        """测试宣战提案被保民官否决"""
        war = self._create_test_war()
        ws = self.state.get_war_system()
        ws._threats = [war]

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = True

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],  # 禁用土地法案
            veto_decider=mock_veto_decider
        )
        cmd.execute([])

        self.assertNotIn(war, ws.get_active_wars())
        self.assertEqual(war.status, WarStatus.THREAT)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_tribune_veto_war_rejected(self):
        """测试宣战提案未被保民官否决，正常执行"""
        war = self._create_test_war()
        ws = self.state.get_war_system()
        ws._threats = [war]

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = False

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],  # 禁用土地法案
            veto_decider=mock_veto_decider
        )
        cmd.execute([])

        self.assertIn(war, ws.get_active_wars())
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, 101)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_tribune_veto_contract_passed(self):
        """测试合同被保民官否决"""
        contract = self._create_test_contract()
        ws = self.state.get_war_system()
        ws._threats = []  # 确保没有战争威胁

        mock_budget_decider = MagicMock()
        mock_budget_decider.decide_proposals.return_value = [contract]

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = True

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],  # 禁用土地法案
            veto_decider=mock_veto_decider
        )
        cmd.budget_decider = mock_budget_decider
        cmd.execute([])

        self.assertEqual(contract.status, ContractStatus.PENDING)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_tribune_veto_contract_rejected(self):
        """测试合同未被保民官否决，正常变为 BUDGETED"""
        contract = self._create_test_contract()
        ws = self.state.get_war_system()
        ws._threats = []  # 确保没有战争威胁

        mock_budget_decider = MagicMock()
        mock_budget_decider.decide_proposals.return_value = [contract]

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = False

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],  # 禁用土地法案
            veto_decider=mock_veto_decider
        )
        cmd.budget_decider = mock_budget_decider
        cmd.execute([])

        self.assertEqual(contract.status, ContractStatus.BUDGETED)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_tribune_veto_land_act_passed(self):
        """测试土地法案被保民官否决"""
        mock_land_decider = MagicMock()
        # 只对 populares 派系返回提案
        mock_land_decider.decide_proposal.side_effect = lambda faction_id, state: ('distribution', 0.1) if faction_id == 'populares' else None

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = True

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[mock_land_decider],
            veto_decider=mock_veto_decider
        )
        cmd.execute([])

        acts = self.state.get_pending_land_acts()
        self.assertEqual(len(acts), 0)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_tribune_veto_land_act_rejected(self):
        """测试土地法案未被保民官否决，正常存入待执行列表"""
        mock_land_decider = MagicMock()
        mock_land_decider.decide_proposal.side_effect = lambda faction_id, state: ('distribution', 0.1) if faction_id == 'populares' else None

        mock_veto_decider = MagicMock(spec=TribuneVetoDecider)
        mock_veto_decider.decide_veto.return_value = False

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[mock_land_decider],
            veto_decider=mock_veto_decider
        )
        cmd.execute([])

        acts = self.state.get_pending_land_acts()
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]['type'], 'distribution')
        self.assertAlmostEqual(acts[0]['percent'], 0.1)
        mock_veto_decider.decide_veto.assert_called_once()

    def test_no_tribune_no_veto(self):
        """测试没有保民官时，提案直接执行"""
        self.tribune.is_dead = True

        war = self._create_test_war()
        ws = self.state.get_war_system()
        ws._threats = [war]

        contract = self._create_test_contract()

        mock_budget_decider = MagicMock()
        mock_budget_decider.decide_proposals.return_value = [contract]

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[]  # 禁用土地法案
        )
        cmd.budget_decider = mock_budget_decider
        cmd.execute([])

        self.assertIn(war, ws.get_active_wars())
        self.assertEqual(contract.status, ContractStatus.BUDGETED)

# ==================== 任务1：补充测试用例 ====================
class TestSenateEdgeCases(unittest.TestCase):
    """元老院阶段边界情况及未覆盖场景测试"""

    def setUp(self):
        """每个测试前创建干净状态，并初始化所有必要系统"""
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")

        # 初始化战争系统
        from src.core.systems.war_system import WarSystem
        self.state._war_system = WarSystem(self.state)
        self.state._war_system._threats = []
        self.state._war_system._active_wars = []
        self.state._war_system._truce_wars = []
        self.state._war_system._war_deck = []
        self.state._war_system._war_discard = []
        self.state._war_system._legions_to_disband = []

        # 初始化军事系统
        from src.core.systems.military_system import MilitarySystem
        self.state._military_system = MilitarySystem(self.state)

        # 初始化海军系统（避免后续扩展出错）
        from src.core.systems.naval_system import NavalSystem
        self.state._naval_system = NavalSystem(self.state)

        # 确保国库充足（避免自动否决）
        self.state._treasury = 500

        # 创建派系
        self.faction1 = Faction(id="senate", name="元老院派", treasury=50)
        self.faction2 = Faction(id="populares", name="平民派", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 创建元老（有影响力）
        self.senator1 = Figure(id=101, name="元老1", faction_id="senate", age=50)
        self.senator1.influence = 100
        self.senator1.class_tier = ClassTier.NOBILE
        self.state.add_member(self.senator1)
        self.faction1.member_ids.append(101)

        self.senator2 = Figure(id=102, name="元老2", faction_id="populares", age=45)
        self.senator2.influence = 80
        self.senator2.class_tier = ClassTier.NOBILE
        self.state.add_member(self.senator2)
        self.faction2.member_ids.append(102)

        # 执政官
        self.consul = Figure(id=201, name="执政官", faction_id="senate", age=42)
        self.consul.office = "consul"
        self.state.add_member(self.consul)
        self.state.turn.leader_ids = [201]

        # 模拟投票决策器（默认支持）
        self.mock_vote_decider = MagicMock()
        self.mock_vote_decider.decide_vote.return_value = True

        # 模拟土地法案决策器（默认不生成提案）
        self.mock_land_decider = MagicMock()
        self.mock_land_decider.decide_proposal.return_value = None

        # 模拟预算决策器（默认不生成合同）
        self.mock_budget_decider = MagicMock()
        self.mock_budget_decider.decide_proposals.return_value = []

        # 模拟保民官否决器（默认不否决）
        self.mock_veto_decider = MagicMock()
        self.mock_veto_decider.decide_veto.return_value = False

        # 测试配置：确保宣战提案总是提出
        self.state.config._config["testing"] = {
            "propose_war_chance": 1.0,
            "always_declare": True,
            "min_legions": 4,
            "max_legions": 8
        }

    # ==================== 辅助方法 ====================
    def _create_threat_war(self, war_id="test_war", name="测试战争", naval_required=False):
        """创建威胁状态的战争"""
        # 使用正确的构造函数（根据 war_system.py 中的用法）
        from src.core.entities.war import War, WarType
        war = War(
            id=war_id,
            name=name,
            war_type=WarType.FOREIGN,
            strength=5,
            naval_required=naval_required
        )
        war.status = WarStatus.THREAT
        war._threat_level = 2
        ws = self.state.get_war_system()
        ws._threats.append(war)
        return war

    def _create_truce_war_with_pending_treaty(self, war_id="truce_war", name="停战战争"):
        """创建停战状态且含有待决草案的战争"""
        from src.core.entities.war import War, WarType
        war = War(
            id=war_id,
            name=name,
            war_type=WarType.FOREIGN,
            strength=5
        )
        war.status = WarStatus.TRUCE
        # 使用 set_peace_treaty 方法设置草案
        treaty = {
            "indemnity": 100,
            "duration": 3,
            "status": "pending",
            "generated_turn": 1
        }
        war.set_peace_treaty(treaty)
        ws = self.state.get_war_system()
        ws._truce_wars.append(war)
        return war

    def _create_pending_contract(self, contract_id=1, name="测试合同"):
        """创建待决合同"""
        contract = Contract(
            id=contract_id,
            contract_type=ContractType.PUBLIC_WORKS,
            name=name,
            base_cost=50,
            expected_profit=20,
            status=ContractStatus.PENDING
        )
        self.state._contracts_dict[contract.id] = contract
        return contract

    # ==================== 宣战被否决 ====================
    def test_war_proposal_rejected(self):
        """测试宣战提案被元老院否决，战争保持威胁状态"""
        # 让执政官出征，使其影响力不计入
        self.consul.is_absent = True
        # 将执政官派系的其他成员移出，避免自动支持
        # 将 senator1 从 senate 派系移除，添加到 populares
        self.faction1.member_ids.remove(101)
        self.senator1.faction_id = "populares"
        self.faction2.member_ids.append(101)
        # 确保所有派系投票反对
        self.mock_vote_decider.decide_vote.return_value = False

        war = self._create_threat_war()

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        ws = self.state.get_war_system()
        # 战争仍为威胁状态
        self.assertIn(war, ws._threats)
        self.assertNotIn(war, ws._active_wars)
        self.assertEqual(war.status, WarStatus.THREAT)

    # ==================== 停战草案通过 ====================
    def test_peace_treaty_passed(self):
        """测试停战草案通过：赔款、停战回合、军团待解散标记"""
        war = self._create_truce_war_with_pending_treaty()

        # 模拟投票支持
        self.mock_vote_decider.decide_vote.return_value = True

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        ws = self.state.get_war_system()
        # 检查草案状态变为 approved
        self.assertEqual(war.peace_treaty["status"], "approved")
        # 检查赔款设置
        self.assertEqual(war.indemnity_due, 100)
        # 检查停战结束回合（当前回合1 + 3 = 4）
        self.assertEqual(war.truce_end_turn, 4)
        # 检查军团待解散标记（由于没有实际军团，列表为空）
        self.assertEqual(ws._legions_to_disband, [])

    # ==================== 停战草案被否决 ====================
    def test_peace_treaty_rejected(self):
        """测试停战草案被元老院否决：战争恢复活跃，草案清除"""
        war = self._create_truce_war_with_pending_treaty()

        # 修改投票决策器：所有派系反对
        self.mock_vote_decider.decide_vote.return_value = False

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        ws = self.state.get_war_system()
        # 战争应被移回活跃列表
        self.assertIn(war, ws._active_wars)
        self.assertNotIn(war, ws._truce_wars)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        # 草案应被清除
        self.assertIsNone(war.peace_treaty)

    # ==================== 预算合同被否决 ====================
    def test_budget_contract_rejected(self):
        """测试预算合同被元老院否决，状态保持 PENDING"""
        contract = self._create_pending_contract()

        # 预算决策器返回该合同
        self.mock_budget_decider.decide_proposals.return_value = [contract]
        # 投票决策器反对
        self.mock_vote_decider.decide_vote.return_value = False

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        self.assertEqual(contract.status, ContractStatus.PENDING)

    # ==================== 卖地法案通过 ====================
    def test_land_sale_act_passed(self):
        """测试卖地法案通过后，pending_land_sale_quota 设置正确"""
        # 配置土地法案决策器：只在 populares 派系返回提案
        self.mock_land_decider.decide_proposal.side_effect = (
            lambda faction_id, state: ("sale", 0.05) if faction_id == "populares" else None
        )
        self.state._national_public_land = 1000
        self.state.config._config["political_rules"] = {
            "land_proposal": {"submit_chance": 1.0}
        }

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[self.mock_land_decider],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        self.assertEqual(self.state.pending_land_sale_quota, 50)  # 1000 * 0.05 = 50

    # ==================== 分地法案通过 ====================
    def test_land_distribution_act_passed(self):
        """测试分地法案通过后，法案存入 _pending_land_acts"""
        # 配置土地法案决策器：只在 populares 派系返回提案
        self.mock_land_decider.decide_proposal.side_effect = (
            lambda faction_id, state: ("distribution", 0.05) if faction_id == "populares" else None
        )
        self.state._national_public_land = 1000
        self.state.config._config["political_rules"] = {
            "land_proposal": {"submit_chance": 1.0}
        }

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[self.mock_land_decider],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        acts = self.state.get_pending_land_acts()
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["type"], "distribution")
        self.assertEqual(acts[0]["amount"], 50)  # 1000 * 0.05 = 50

    # ==================== 无提案 ====================
    def test_no_proposals(self):
        """测试没有任何提案时，阶段正常执行"""
        self.mock_land_decider.decide_proposal.return_value = None
        self.mock_budget_decider.decide_proposals.return_value = []

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[self.mock_land_decider],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider

        result = cmd.execute([])
        self.assertTrue(result)

    # ==================== 无元老在场 ====================
    def test_no_senators_present(self):
        """测试所有元老缺席（影响力为0）时，所有提案不通过"""
        # 将所有元老设置为缺席
        self.senator1.is_absent = True
        self.senator2.is_absent = True
        # 执政官出征，不计影响力
        self.consul.is_absent = True

        # 创建宣战提案
        war = self._create_threat_war()
        # 创建停战提案
        truce_war = self._create_truce_war_with_pending_treaty()
        # 创建合同提案
        contract = self._create_pending_contract()
        self.mock_budget_decider.decide_proposals.return_value = [contract]
        # 土地法案决策器返回提案（只在 populares 派系返回）
        self.mock_land_decider.decide_proposal.side_effect = (
            lambda faction_id, state: ("sale", 0.05) if faction_id == "populares" else None
        )
        self.state._national_public_land = 1000
        self.state.config._config["political_rules"] = {
            "land_proposal": {"submit_chance": 1.0}
        }

        # 投票决策器即使返回支持，但由于总影响力为0，算法会跳过投票
        self.mock_vote_decider.decide_vote.return_value = True

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[self.mock_land_decider],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        ws = self.state.get_war_system()
        # 宣战提案未通过：战争仍在威胁列表
        self.assertIn(war, ws._threats)
        self.assertNotIn(war, ws._active_wars)

        # 停战草案未通过：战争仍在停战列表（草案未执行）
        self.assertIn(truce_war, ws._truce_wars)

        # 合同未通过：状态保持 PENDING
        self.assertEqual(contract.status, ContractStatus.PENDING)

        # 土地法案未通过：无待执行法案
        self.assertEqual(self.state.pending_land_sale_quota, 0)
        self.assertEqual(len(self.state.get_pending_land_acts()), 0)

    # ==================== 投票平局 ====================
    def test_tie_vote(self):
        """测试支持率 = 50% 时，提案不通过（边界条件）"""
        war = self._create_threat_war()

        # 控制投票：让两个派系影响力相等，一个支持一个反对
        self.senator1.influence = 100
        self.senator2.influence = 100

        # 定义投票决策器：senate 支持，populares 反对
        def vote_side(issue, faction, state):
            if faction.id == "senate":
                return True
            else:
                return False
        self.mock_vote_decider.decide_vote.side_effect = vote_side

        cmd = SenateCommand(
            self.state,
            vote_decider=self.mock_vote_decider,
            land_proposal_deciders=[],
            veto_decider=self.mock_veto_decider
        )
        cmd.budget_decider = self.mock_budget_decider
        cmd.execute([])

        ws = self.state.get_war_system()
        # 支持率 50% 应不通过，战争仍为威胁
        self.assertIn(war, ws._threats)
        self.assertNotIn(war, ws._active_wars)

# ==================== 任务3：补充测试用例 ====================
class TestManualTakeover(unittest.TestCase):
    """手动模式下战争接管功能测试"""

    def setUp(self):
        # 创建测试状态
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")
        self.state._treasury = 1000

        # 初始化战争和军事系统
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        # 创建派系和人物
        self.faction = Faction(id="optimates", name="Optimates", treasury=100)
        self.state.add_faction(self.faction)

        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 100
        self.state.add_member(self.consul)
        self.faction.member_ids.append(1)

        self.senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
        self.senator.class_tier = ClassTier.NOBILE
        self.senator.influence = 50
        self.state.add_member(self.senator)
        self.faction.member_ids.append(2)

        # 设置玩家
        self.player = Player("player1", "optimates", "human")
        self.state.add_player(self.player)
        self.state.set_current_player("player1")
        self.state.set_turn_order(["player1"])

        # 创建一个活跃的外国战争（非起义）
        from src.core.entities.war import WarType
        self.war = War(
            id="foreign_war",
            name="外国战争",
            war_type=WarType.FOREIGN,
            strength=10,
            naval_required=False,
            rebellion_province_id=None
        )
        self.war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war)
        # 初始化海军系统


    @patch('builtins.input')
    def test_manual_takeover_war(self, mock_input):
        """测试手动模式下接管外国战争并增派军团"""
        mock_input.side_effect = ["next", "propose B01 3", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as buf, redirect_stdout(buf):
            result = cmd.execute([])
            output = buf.getvalue()  # 在块内获取

        self.assertTrue(result)

        ws = self.state.get_war_system()
        war = ws.get_war_by_id("foreign_war")
        self.assertEqual(war.commander_id, 1)
        consul = self.state.get_member(1)
        self.assertTrue(consul.is_absent)

        ms = self.state.get_military_system()
        legions = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(legions), 3)
        self.assertIn("已接管战争，增援 3 个军团", output)

    @patch('builtins.input')
    def test_manual_takeover_war_with_existing_commander(self, mock_input):
        """测试接管已有指挥官的战争（如前任执政官指挥）"""
        old_commander = Figure(id=3, name="前执政官", faction_id="optimates", age=45)
        old_commander.office = "proconsul"
        old_commander.is_absent = True
        old_commander.class_tier = ClassTier.NOBILE
        self.state.add_member(old_commander)
        self.faction.member_ids.append(3)
        self.war.commander_id = 3
        self.war.set_commander_assigned_turn(1)  # 使用 setter

        mock_input.side_effect = ["next", "propose B01 2", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as buf, redirect_stdout(buf):
            result = cmd.execute([])
            output = buf.getvalue()

        self.assertTrue(result)

        war = self.state.get_war_system().get_war_by_id("foreign_war")
        self.assertEqual(war.commander_id, 1)
        self.assertTrue(self.consul.is_absent)
        self.assertFalse(old_commander.is_absent)
        self.assertEqual(old_commander.office, "ex-proconsul")

        ms = self.state.get_military_system()
        legions = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(legions), 2)
        self.assertIn("已接管战争，增援 2 个军团", output)

    @patch('builtins.input')
    def test_manual_takeover_insufficient_legions(self, mock_input):
        """测试征召军团时可用军团不足（实际可用25个，征召30个）"""
        mock_input.side_effect = ["next", "propose B01 30", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as buf, redirect_stdout(buf):
            result = cmd.execute([])
            output = buf.getvalue()

        self.assertTrue(result)
        war = self.state.get_war_system().get_war_by_id("foreign_war")
        ms = self.state.get_military_system()
        legions = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(legions), 25)
        # 修正：实际征召25个，消息应为25
        self.assertIn("已接管战争，增援 25 个军团", output)

    @patch('builtins.input')
    def test_manual_takeover_invalid_war_id(self, mock_input):
        """测试接管不存在的战争"""
        mock_input.side_effect = ["next", "propose B99 3", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        # 同时捕获 stdout 和 stderr
        with io.StringIO() as out, io.StringIO() as err, redirect_stdout(out), redirect_stderr(err):
            result = cmd.execute([])
            output = out.getvalue()
            error = err.getvalue()
        self.assertTrue(result)
        self.assertIn("❌ 无效的法案ID: B99", output + error)

    @patch('builtins.input')
    def test_manual_takeover_no_consul(self, mock_input):
        """测试当前玩家没有执政官人物"""
        self.consul.is_dead = True
        for member in self.state.get_living_members():
            if member.office == "consul":
                member.office = None

        mock_input.side_effect = ["next", "propose B01 3", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as out, io.StringIO() as err, redirect_stdout(out), redirect_stderr(err):
            result = cmd.execute([])
            output = out.getvalue()
            error = err.getvalue()
        self.assertTrue(result)
        self.assertIn("❌ 您没有在罗马的执政官可以出征", output + error)
        war = self.state.get_war_system().get_war_by_id("foreign_war")
        self.assertIsNone(war.commander_id)

    @patch('builtins.input')
    def test_manual_takeover_rebellion_war_not_shown(self, mock_input):
        """测试起义战争不在接管列表中（通过 API 过滤）"""
        # 创建起义战争
        from src.core.entities.war import WarType
        rebellion_war = War(
            id="rebellion",
            name="起义战争",
            war_type=WarType.PROVINCIAL,
            strength=5,
            naval_required=False,
            rebellion_province_id=1
        )
        rebellion_war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(rebellion_war)

        mock_input.side_effect = ["next", "propose B01 3", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as buf, redirect_stdout(buf):
            result = cmd.execute([])
            output = buf.getvalue()

        self.assertTrue(result)
        war = self.state.get_war_system().get_war_by_id("foreign_war")
        self.assertEqual(war.commander_id, 1)
        rebellion = self.state.get_war_system().get_war_by_id("rebellion")
        self.assertIsNone(rebellion.commander_id)
        # 确保接管命令是针对外国战争的，没有尝试接管起义战争
        self.assertIn("已接管战争，增援 3 个军团", output)

    @patch('builtins.input')
    def test_manual_war_declaration_with_naval_no_fleet(self, mock_input):
        """测试需要海战但无舰队时，宣战失败"""
        # 创建需要海战的战争，并加入威胁列表
        war = War(
            id="naval_war",
            name="海战战争",
            war_type=WarType.FOREIGN,
            strength=10,
            naval_required=True
        )
        war.status = WarStatus.THREAT
        self.state._war_system._threats.append(war)

        # 模拟无可用舰队
        self.state.naval_system.get_available_fleets = MagicMock(return_value=[])

        # 模拟用户输入：步骤0 next，步骤1 propose B01 6
        mock_input.side_effect = ["next", "propose B01 6", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False

        with io.StringIO() as out, io.StringIO() as err, redirect_stdout(out), redirect_stderr(err):
            result = cmd.execute([])
            output = out.getvalue()
            error = err.getvalue()

        self.assertTrue(result)  # 阶段仍正常完成
        self.assertIn("战争需要海战，但当前无可用舰队，无法宣战。请先建造舰队。", output + error)

        # 验证战争未被激活（仍然在威胁列表）
        self.assertIn(war, self.state._war_system._threats)
        self.assertNotIn(war, self.state._war_system._active_wars)

    @patch('builtins.input')
    def test_manual_war_declaration_with_naval_has_fleet(self, mock_input):
        """测试需要海战且有舰队时，宣战成功"""
        war = War(
            id="naval_war",
            name="海战战争",
            war_type=WarType.FOREIGN,
            strength=10,
            naval_required=True
        )
        war.status = WarStatus.THREAT
        self.state._war_system._threats.append(war)

        # 模拟有可用舰队
        mock_fleet = MagicMock()
        self.state.naval_system.get_available_fleets = MagicMock(return_value=[mock_fleet])

        mock_input.side_effect = ["next", "propose B01 6", "next"]

        cmd = SenateCommand(self.state)
        cmd._auto_mode = False
        # 确保投票决策器总是返回支持
        cmd.vote_decider = MagicMock()
        cmd.vote_decider.decide_vote.return_value = True

        with io.StringIO() as buf, redirect_stdout(buf):
            result = cmd.execute([])
            output = buf.getvalue()

        self.assertTrue(result)
        self.assertIn("✅ 对 海战战争 宣战，申请征召 6 个军团", output)
        self.assertNotIn(war, self.state._war_system._threats)
        self.assertIn(war, self.state._war_system._active_wars)

if __name__ == "__main__":
    unittest.main()