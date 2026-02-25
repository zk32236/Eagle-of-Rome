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
        self.assertEqual(test_a._config._config, config_a)
        self.assertEqual(test_b._config._config, config_b)

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

    # ==================== MVP 0.5 新增测试 ====================

class TestGameStateMVP05(unittest.TestCase):
    """测试 GameState MVP 0.5 新增的行省/合同管理接口"""

    def setUp(self):
        """每个测试前创建一个新的 GameState 实例"""
        self.state = GameState.create_for_testing({})

    # ---------- 行省管理测试 ----------
    def test_add_province_and_get_province(self):
        """测试添加行省和通过ID获取行省"""
        from src.core.entities.entities import Province

        province = Province(1, "西西里", 1000)
        self.state.add_province(province)

        retrieved = self.state.get_province(1)
        self.assertIs(retrieved, province)
        self.assertEqual(retrieved.name, "西西里")

        # 获取不存在的ID应返回None
        self.assertIsNone(self.state.get_province(999))

    def test_add_province_updates_public_land(self):
        """测试添加行省后全局公地总数更新正确"""
        from src.core.entities.entities import Province

        # 初始为0
        self.assertEqual(self.state._public_land_total, 0)

        province1 = Province(1, "西西里", 1000)  # 公地600
        province2 = Province(2, "撒丁尼亚", 500)  # 公地300
        self.state.add_province(province1)
        self.assertEqual(self.state._public_land_total, 600)
        self.state.add_province(province2)
        self.assertEqual(self.state._public_land_total, 900)

    def test_get_all_provinces_returns_copy(self):
        """测试 get_all_provinces 返回副本，修改副本不影响内部"""
        from src.core.entities.entities import Province

        province1 = Province(1, "西西里", 1000)
        province2 = Province(2, "撒丁尼亚", 500)
        self.state.add_province(province1)
        self.state.add_province(province2)

        provinces = self.state.get_all_provinces()
        self.assertEqual(len(provinces), 2)

        # 修改返回的列表
        provinces.clear()
        # 内部字典应不受影响
        self.assertEqual(len(self.state.get_all_provinces()), 2)

    # ---------- 合同管理测试 ----------
    def test_create_contract_and_get_contract(self):
        """测试创建合同和通过ID获取合同"""
        from src.core.entities.contract import ContractType

        contract = self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        self.assertEqual(contract.id, 1)
        self.assertEqual(contract.contract_type, ContractType.TAX_FARMING)
        self.assertEqual(contract.province_id, 1)
        self.assertEqual(contract.base_cost, 90)
        self.assertEqual(contract.create_turn, 5)

        retrieved = self.state.get_contract(1)
        self.assertIs(retrieved, contract)
        self.assertIsNone(self.state.get_contract(999))

    def test_contract_id_auto_increment(self):
        """测试合同ID自增"""
        from src.core.entities.contract import ContractType

        contract1 = self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        contract2 = self.state.create_contract(ContractType.PUBLIC_WORKS, 2, 200, 5)
        self.assertEqual(contract1.id, 1)
        self.assertEqual(contract2.id, 2)

    def test_get_all_contracts_returns_copy(self):
        """测试 get_all_contracts 返回副本"""
        from src.core.entities.contract import ContractType

        self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        self.state.create_contract(ContractType.PUBLIC_WORKS, 2, 200, 5)

        contracts = self.state.get_all_contracts()
        self.assertEqual(len(contracts), 2)

        contracts.clear()
        self.assertEqual(len(self.state.get_all_contracts()), 2)

    # ---------- 获取行省绑定的合同测试 ----------
    def test_get_province_contract(self):
        """测试通过行省和类型获取绑定的合同"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import ContractType

        province = Province(1, "西西里", 1000)
        self.state.add_province(province)

        contract = self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        province.bind_tax_contract(contract.id)

        retrieved = self.state.get_province_contract(1, ContractType.TAX_FARMING)
        self.assertIs(retrieved, contract)

        self.assertIsNone(self.state.get_province_contract(1, ContractType.PUBLIC_WORKS))
        self.assertIsNone(self.state.get_province_contract(999, ContractType.TAX_FARMING))

    # ---------- reset 测试 ----------
    def test_reset_clears_new_fields(self):
        """测试 reset 方法清空新增字段并重置计数器"""
        from src.core.entities.entities import Province
        from src.core.entities.contract import ContractType

        province = Province(1, "西西里", 1000)
        self.state.add_province(province)
        self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)

        self.assertGreater(len(self.state._provinces), 0)
        self.assertGreater(len(self.state._contracts_dict), 0)
        self.assertGreater(self.state._public_land_total, 0)
        self.assertEqual(self.state._contract_id_counter, 2)

        self.state.reset()

        self.assertEqual(len(self.state._provinces), 0)
        self.assertEqual(len(self.state._contracts_dict), 0)
        self.assertEqual(self.state._public_land_total, 0)
        self.assertEqual(self.state._contract_id_counter, 1)


if __name__ == "__main__":
    unittest.main()