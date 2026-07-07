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
from src.ui.commands.phase_mortality import MortalityCommand
from src.core.entities.war import War, WarStatus


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
        from src.core.entities.entities import Faction, GameTurn
        from src.core.entities.province import Province
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

    def test_bountiful_harvest_event(self):
        """测试风调雨顺事件：写入 active_events 并检查税收阶段加成"""
        # 修改配置确保抽取到风调雨顺
        test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "风调雨顺", "effect": "bountiful_harvest", "weight": 1}],
                "event_draw_count": 1,
                "bumper_harvest_multiplier": 1.5
            },
            "economic_rules": {
                "land_price_per_unit": 10,
                "public_land_income_rate": 0.01,
                "national_public_land_tax_rate": 0.1,
                "private_land_income_rate": 0.05,
                "faction_tax_rate": 0.1
            }
        }
        state = GameState.create_for_testing(test_config)
        # 设置必要的实体
        from src.core.entities.entities import GameTurn, Faction
        from src.core.entities.figure import Figure, ClassTier
        state.turn = GameTurn(turn_number=1, year=-264)
        # 添加派系和人物
        faction = Faction("test", "测试派")
        state.add_faction(faction)
        fig = Figure(1, "测试人物", faction_id="test", age=30)
        # 设置私地数量（通过私有字段，因为 land_private 是只读属性）
        fig._land_private = 100
        fig.class_tier = ClassTier.EQUES
        state.add_member(fig)
        faction.member_ids = [1]
        # 设置国家公地
        state._national_public_land = 1000

        # 执行天命阶段
        from src.ui.commands.phase_mortality import MortalityCommand
        cmd_m = MortalityCommand(state)
        cmd_m.execute([])

        # 验证事件已写入
        self.assertIn("bumper_harvest", state.active_events)
        self.assertEqual(state.active_events["bumper_harvest"]["multiplier"], 1.5)

        # 执行税收阶段
        from src.ui.commands.phase_revenue import RevenueCommand
        cmd_r = RevenueCommand(state)
        # 模拟前置阶段已执行
        state._executed_phases.add("mortality")
        initial_treasury = state.treasury
        initial_wealth = fig.wealth

        f = io.StringIO()
        with redirect_stdout(f):
            cmd_r.execute([])
        output = f.getvalue()

        # 验证加成效果
        # 国家公地收益：1000*10*0.01*0.1 = 10，乘1.5得15
        self.assertEqual(state.treasury - initial_treasury, 15)
        # 私地收入：100*10*0.05 = 50，乘1.5得75，扣除派系抽成10%得67.5，四舍五入68
        self.assertEqual(fig.wealth - initial_wealth, 68)
        # 日志中应有提示
        self.assertIn("风调雨顺加成", output)

    def test_peace_event(self):
        """测试国泰民安事件：民怨和战争威胁等级置零"""
        # 修改配置确保抽取到国泰民安
        test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "国泰民安", "effect": "peace", "weight": 1}],
                "event_draw_count": 1
            }
        }
        state = GameState.create_for_testing(test_config)
        from src.core.entities.entities import GameTurn, Faction
        from src.core.entities.figure import Figure
        from src.core.entities.province import Province
        from src.core.systems.war_system import WarSystem
        from src.core.entities.war import War, WarStatus  # 确保导入

        state.turn = GameTurn(turn_number=1, year=-264)

        # 添加一个已征服行省，民怨设为2
        province = Province(1, "Test Province", 1000, conquered=True)
        province.set_grievance(2)
        state.add_province(province)

        # 添加一个未征服行省，民怨设为3（不应受影响）
        province2 = Province(2, "Unconquered", 1000, conquered=False)
        province2.set_grievance(3)
        state.add_province(province2)

        # 初始化战争系统（真实对象）
        war_system = WarSystem(state)
        # 创建一个威胁战争
        war = War(id="test_war", name="Test War")
        war.threat_level = 3
        war.status = WarStatus.THREAT
        war_system._threats.append(war)
        state._war_system = war_system

        # 执行天命阶段
        from src.ui.commands.phase_mortality import MortalityCommand
        cmd = MortalityCommand(state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd.execute([])
        output = f.getvalue()

        # 验证行省民怨
        self.assertEqual(province.grievance, 0)
        self.assertEqual(province2.grievance, 3)  # 未征服的不变
        # 验证战争威胁
        self.assertEqual(war.threat_level, 0)
        # 检查输出
        self.assertIn("国泰民安", output)
        self.assertIn("Test Province 民怨从 2 降至 0", output)
        self.assertIn("Test War 威胁等级从 3 降至 0", output)

        # 验证日志
        self.assertTrue(any("国泰民安触发" in msg for msg in state.event_log))


if __name__ == "__main__":
    unittest.main()