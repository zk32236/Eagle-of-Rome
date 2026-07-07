# src/tests/test_core/test_game_state.py
"""
GameState 单元测试 - 使用动态导入绕过包导入，仅测试多实例基础功能
"""

import unittest
import sys
import os
import importlib.util

# 获取项目根目录和 game_state.py 的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
game_state_path = os.path.join(project_root, 'src', 'core', 'game_state.py')

# 动态导入 game_state 模块，避免触发 __init__.py 中的其他导入
spec = importlib.util.spec_from_file_location("game_state", game_state_path)
game_state_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game_state_module)
GameState = game_state_module.GameState


class TestGameStateMultiInstance(unittest.TestCase):
    """测试多实例创建与状态隔离"""

    def test_multi_instance_creation(self):
        """验证可以创建多个独立实例"""
        state_a = GameState()
        state_b = GameState()

        # 必须是不同对象
        self.assertIsNot(state_a, state_b)
        # 内部容器也必须是独立对象
        self.assertIsNot(state_a._members, state_b._members)
        self.assertIsNot(state_a._factions, state_b._factions)

    def test_state_isolation(self):
        """验证修改一个实例不影响另一个实例"""
        state_a = GameState()
        state_b = GameState()

        # 修改实例A的国库
        state_a._treasury = 100
        # 修改实例A的成员字典（模拟添加成员）
        state_a._members[1] = None

        self.assertEqual(state_a._treasury, 100)
        self.assertEqual(state_b._treasury, 0)          # B 不受影响
        self.assertIn(1, state_a._members)
        self.assertNotIn(1, state_b._members)           # B 不受影响

    def test_reset(self):
        """验证 reset 方法仅重置当前实例"""
        state = GameState()
        # 修改一些状态
        state._treasury = 100
        state._members[1] = None
        state._event_log.append("test")

        state.reset()

        # 状态应恢复初始
        self.assertEqual(state._treasury, 0)
        self.assertEqual(len(state._members), 0)
        self.assertEqual(len(state._event_log), 0)
        # 确保天命池重新初始化
        self.assertEqual(len(state._mortality_pool), GameState.MAX_MEMBER_ID)

    def test_reset_does_not_affect_other_instances(self):
        """验证重置一个实例不影响其他实例"""
        state_a = GameState()
        state_b = GameState()

        state_a._treasury = 100
        state_b._treasury = 200

        state_a.reset()

        self.assertEqual(state_a._treasury, 0)
        self.assertEqual(state_b._treasury, 200)   # B 保持不变

    def test_create_for_testing(self):
        """验证测试工厂方法正确注入配置并创建独立实例"""
        test_config = {"test_key": "test_value", "foo": 42}
        test_state = GameState.create_for_testing(test_config)

        # 验证配置被注入
        self.assertEqual(test_state._config._config, test_config)

        # 验证状态已初始化（非空）
        self.assertEqual(len(test_state._mortality_pool), GameState.MAX_MEMBER_ID)
        self.assertEqual(test_state._treasury, 0)

        # 验证与正常实例隔离
        normal_state = GameState()
        self.assertIsNot(test_state, normal_state)
        self.assertIsNot(test_state._members, normal_state._members)

    def test_create_for_testing_independent(self):
        """验证多个测试实例彼此独立"""
        config_a = {"id": "A"}
        config_b = {"id": "B"}

        test_a = GameState.create_for_testing(config_a)
        test_b = GameState.create_for_testing(config_b)

        self.assertIsNot(test_a, test_b)
        self.assertEqual(test_a._config._config, config_a)  # 修改点
        self.assertEqual(test_b._config._config, config_b)  # 修改点

        # 修改其中一个的国库，验证隔离
        test_a._treasury = 500
        self.assertEqual(test_b._treasury, 0)

    def test_initial_state_after_creation(self):
        """验证普通构造后状态正确初始化"""
        state = GameState()
        self.assertEqual(state._treasury, 0)
        self.assertEqual(len(state._members), 0)
        self.assertEqual(len(state._factions), 0)
        self.assertEqual(len(state._event_log), 0)
        self.assertEqual(len(state._used_ids), 0)
        self.assertEqual(len(state._mortality_pool), GameState.MAX_MEMBER_ID)

    def test_public_methods_exist(self):
        """验证所有公共方法均保留（仅检查存在性，不测试逻辑）"""
        state = GameState()
        # 实体管理
        self.assertTrue(hasattr(state, 'add_member'))
        self.assertTrue(hasattr(state, 'get_member'))
        self.assertTrue(hasattr(state, 'get_living_members'))
        self.assertTrue(hasattr(state, 'get_living_member'))
        # 派系管理
        self.assertTrue(hasattr(state, 'add_faction'))
        self.assertTrue(hasattr(state, 'get_faction'))
        self.assertTrue(hasattr(state, 'get_active_factions'))
        # 配置获取
        self.assertTrue(hasattr(state, 'get_cooldown_years'))
        self.assertTrue(hasattr(state, 'get_leaders_per_election'))
        self.assertTrue(hasattr(state, 'get_office_cooldown'))
        self.assertTrue(hasattr(state, 'get_offices_per_election'))
        # 天命机制
        self.assertTrue(hasattr(state, 'draw_mortality_number'))
        # 回合管理
        self.assertTrue(hasattr(state, 'advance_year'))
        self.assertTrue(hasattr(state, 'is_phase_executed'))
        self.assertTrue(hasattr(state, 'mark_phase_executed'))
        # 战争/军事
        self.assertTrue(hasattr(state, 'get_war_system'))
        self.assertTrue(hasattr(state, 'get_active_wars'))
        self.assertTrue(hasattr(state, 'get_military_system'))
        self.assertTrue(hasattr(state, 'is_military_prepared'))
        self.assertTrue(hasattr(state, 'get_military_preparation_status'))
        # 主持人
        self.assertTrue(hasattr(state, 'get_presiding_officer'))
        # 日志
        self.assertTrue(hasattr(state, 'log_event'))
        self.assertTrue(hasattr(state, 'get_status_summary'))
        # ID分配
        self.assertTrue(hasattr(state, 'allocate_id'))

    # ===== 新增的经济相关方法测试 =====

    def test_add_treasury(self):
        """测试国库增减"""
        state = GameState()
        self.assertEqual(state.treasury, 0)

        # 增加
        new_value = state.add_treasury(100)
        self.assertEqual(state.treasury, 100)
        self.assertEqual(new_value, 100)

        # 减少
        new_value = state.add_treasury(-50)
        self.assertEqual(state.treasury, 50)
        self.assertEqual(new_value, 50)

    def test_add_faction_treasury(self):
        """测试派系资金增减"""
        state = GameState()
        from src.core.entities.entities import Faction
        faction = Faction(id="test", name="测试派系", treasury=50)
        state.add_faction(faction)

        # 增加
        result = state.add_faction_treasury("test", 30)
        self.assertTrue(result)
        self.assertEqual(faction.treasury, 80)

        # 减少
        result = state.add_faction_treasury("test", -20)
        self.assertTrue(result)
        self.assertEqual(faction.treasury, 60)

        # 派系不存在
        result = state.add_faction_treasury("nonexistent", 10)
        self.assertFalse(result)

    def test_add_figure_wealth(self):
        """测试人物财富增减"""
        state = GameState()
        from src.core.entities.figure import Figure
        figure = Figure(id=1, name="测试人物", faction_id="test", wealth=100)
        state.add_member(figure)

        # 增加
        result = state.add_figure_wealth(1, 50)
        self.assertTrue(result)
        self.assertEqual(figure.wealth, 150)

        # 减少
        result = state.add_figure_wealth(1, -30)
        self.assertTrue(result)
        self.assertEqual(figure.wealth, 120)

        # 人物不存在
        result = state.add_figure_wealth(999, 10)
        self.assertFalse(result)

        # 人物已死亡
        figure.is_dead = True
        result = state.add_figure_wealth(1, 10)
        self.assertFalse(result)

    def test_get_economic_rule(self):
        """测试获取经济规则配置"""
        test_config = {
            "economic_rules": {
                "base_tax": 200,
                "faction_stipend": 20
            }
        }
        state = GameState.create_for_testing(test_config)

        self.assertEqual(state.get_economic_rule("base_tax"), 200)
        self.assertEqual(state.get_economic_rule("faction_stipend"), 20)
        # 不存在的键返回默认值
        self.assertEqual(state.get_economic_rule("nonexistent", 99), 99)
        self.assertIsNone(state.get_economic_rule("nonexistent"))

    def test_contracts_property(self):
        """测试合同属性"""
        state = GameState()
        self.assertEqual(state.contracts, [])

        test_contracts = ["合同1", "合同2"]
        state.contracts = test_contracts
        self.assertEqual(state.contracts, test_contracts)


if __name__ == "__main__":
    unittest.main()