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
from unittest.mock import MagicMock

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.ui.commands.phase_senate import SenateCommand
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import WarStatus, War






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

if __name__ == "__main__":
    unittest.main()