# src/tests/test_commands/test_phase_mortality.py
"""
天命阶段命令单元测试
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock
import io
from contextlib import redirect_stdout

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.game_state import GameState
from src.core.entities.contract import ContractStatus
from src.ui.commands.phase_mortality import MortalityCommand


class TestMortalityCommand(unittest.TestCase):
    """天命阶段命令测试类"""

    def setUp(self):
        """每个测试前创建测试用 GameState"""
        test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "死神来了", "effect": "death"}],
                "event_draw_count": 1,
                "death_count": 1
            }
        }
        self.state = GameState.create_for_testing(test_config)

        # 添加一些测试人物
        self._add_test_figures()

    def _add_test_figures(self):
        """添加测试人物到 GameState"""
        from src.core.entities.entities import Faction
        from src.core.entities.figure import Figure

        faction1 = Faction(id="senate", name="元老院派")
        faction2 = Faction(id="populares", name="平民派")
        self.state.add_faction(faction1)
        self.state.add_faction(faction2)

        fig1 = Figure(id=1, name="Marcus Brutus", faction_id="senate", age=40)
        fig1.is_dead = False
        fig2 = Figure(id=2, name="Gaius Marius", faction_id="populares", age=35)
        fig2.is_dead = False
        fig3 = Figure(id=3, name="Lucius Sulla", faction_id="senate", age=45)
        fig3.is_dead = False

        self.state.add_member(fig1)
        self.state.add_member(fig2)
        self.state.add_member(fig3)

        faction1.member_ids = [1, 3]
        faction2.member_ids = [2]

        from src.core.entities.entities import GameTurn
        self.state.turn = GameTurn(turn_number=1, year=-264)

    def test_execute_success(self):
        """测试成功执行天命阶段"""
        cmd = MortalityCommand(self.state)

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("Mortality Phase", output)
        self.assertIn("事件卡:", output)          # 修改点
        self.assertTrue(self.state.is_phase_executed("mortality"))

    def test_death_event(self):
        """测试死亡事件：随机一名人物死亡"""
        cmd = MortalityCommand(self.state)

        # 记录死亡前人物存活状态
        living_before = [mid for mid in [1,2,3] if not self.state.get_member(mid).is_dead]

        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])

        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("死神选中了", output)       # 检查输出

        # 验证有一人死亡
        living_after = [mid for mid in [1,2,3] if not self.state.get_member(mid).is_dead]
        self.assertEqual(len(living_after), len(living_before) - 1)

        # 验证事件日志
        self.assertTrue(any("死亡" in msg for msg in self.state.event_log))

    def test_already_executed(self):
        """测试阶段已执行时再次执行应返回False"""
        cmd = MortalityCommand(self.state)

        result1 = cmd.execute([])
        self.assertTrue(result1)

        f = io.StringIO()
        with redirect_stdout(f):
            result2 = cmd.execute([])
        output = f.getvalue()

        self.assertFalse(result2)
        self.assertIn("本回合已执行", output)

    def test_no_members(self):
        """测试没有存活人物时的边界情况"""
        # 清空所有人物的存活状态
        for mid in list(self.state.members.keys()):
            self.state.get_member(mid).is_dead = True

        cmd = MortalityCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        self.assertIn("无存活人物，死神空手而归", output)   # 修改点

    def test_multiple_deaths(self):
        """测试配置死亡人数大于1的情况"""
        test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "死神来了", "effect": "death"}],
                "event_draw_count": 1,
                "death_count": 2
            }
        }
        state = GameState.create_for_testing(test_config)

        # 添加人物
        from src.core.entities.entities import Faction, GameTurn
        from src.core.entities.figure import Figure
        faction = Faction(id="test", name="测试派")
        state.add_faction(faction)
        for i in range(1, 6):
            fig = Figure(id=i, name=f"人物{i}", faction_id="test", age=30)
            fig.is_dead = False
            state.add_member(fig)
            faction.member_ids.append(i)
        state.turn = GameTurn(turn_number=1, year=-264)

        cmd = MortalityCommand(state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()

        self.assertTrue(result)
        # 检查输出中包含两次死亡（或者检查死亡人数统计）
        self.assertEqual(output.count("死神选中了"), 2)

    def test_phase_marking(self):
        """验证阶段标记功能"""
        self.assertFalse(self.state.is_phase_executed("mortality"))

        cmd = MortalityCommand(self.state)
        cmd.execute([])

        self.assertTrue(self.state.is_phase_executed("mortality"))

    def test_death_event_terminates_contract(self):
        """测试死亡事件终止合同"""
        from src.core.entities.entities import Province, Faction, GameTurn
        from src.core.entities.contract import Contract, ContractType, ContractStatus
        from src.core.entities.figure import Figure, ClassTier
        from src.ui.commands.phase_mortality import MortalityCommand
        from src.core.game_state import GameState

        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)

        # 创建派系和人物
        faction = Faction(id="test", name="测试派")
        state.add_faction(faction)
        knight = Figure(id=101, name="骑士", faction_id="test", age=30)
        knight.wealth = 200
        knight.class_tier = ClassTier.EQUES
        state.add_member(knight)
        faction.member_ids = [101]

        # 创建行省
        province = Province(1, "西西里", 1000)
        state.add_province(province)

        # 创建合同
        contract = state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=100,
            current_turn=state.turn.turn_number - 1
        )
        contract._winning_bid = {"bidder_id": 101, "amount": 100}
        contract.status = ContractStatus.ACTIVE
        contract.awarded_to = 101
        province.bind_tax_contract(contract.id)
        knight.add_contract(contract.id)

        cmd = MortalityCommand(state)
        cmd._handle_death_event()

        self.assertTrue(knight.is_dead)
        self.assertEqual(contract.status, ContractStatus.EXPIRED)
        self.assertIsNone(province.tax_contract_id)


if __name__ == "__main__":
    unittest.main()