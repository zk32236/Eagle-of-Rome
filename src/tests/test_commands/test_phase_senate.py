# src/tests/test_commands/test_phase_senate.py
"""
元老院阶段命令单元测试
"""

import unittest
import sys
import os
import io
from contextlib import redirect_stdout
from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.entities.war import War, WarStatus

from unittest.mock import MagicMock

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
        from src.core.entities.entities import Province
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

if __name__ == "__main__":
    unittest.main()