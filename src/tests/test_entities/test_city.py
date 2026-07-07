# tests/test_entities/test_city.py
import unittest
from src.core.game_state import GameState
from src.core.entities.city import City
from src.core.entities.province import Province
from src.core.entities.war import War
from src.core.entities.contract import Contract, ContractType


class TestCityEntity(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})

    def test_city_creation(self):
        """测试城市创建和属性"""
        city = City(1, "Roma", {"roads": 3, "aqueducts": 2})
        self.assertEqual(city.city_id, 1)
        self.assertEqual(city.name, "Roma")
        self.assertEqual(city.infrastructure["roads"], 3)
        self.assertEqual(city.infrastructure["aqueducts"], 2)
        # 默认基础设施键应存在
        self.assertIn("forum", city.infrastructure)
        self.assertEqual(city.infrastructure["forum"], 0)

    def test_city_to_dict_from_dict(self):
        """测试城市序列化"""
        city = City(2, "Capua", {"roads": 1, "baths": 1})
        data = city.to_dict()
        new_city = City.from_dict(data)
        self.assertEqual(new_city.city_id, 2)
        self.assertEqual(new_city.name, "Capua")
        self.assertEqual(new_city.infrastructure["roads"], 1)
        self.assertEqual(new_city.infrastructure["baths"], 1)

    def test_game_state_city_management(self):
        """测试 GameState 中的城市管理"""
        city1 = self.state.create_city("Roma", {"roads": 3})
        city2 = self.state.create_city("Capua")
        self.assertEqual(city1.city_id, 1)
        self.assertEqual(city2.city_id, 2)
        self.assertEqual(len(self.state.get_all_cities()), 2)
        self.assertIs(self.state.get_city(1), city1)
        self.assertIs(self.state.get_city(2), city2)

    def test_province_city_ids(self):
        """测试 Province 中的城市ID列表"""
        province = Province(1, "Italia", 1000)
        self.assertEqual(province.city_ids, [])
        province.add_city_id(101)
        province.add_city_id(102)
        self.assertEqual(province.city_ids, [101, 102])
        province.remove_city_id(101)
        self.assertEqual(province.city_ids, [102])

    def test_war_battle_stats(self):
        """测试 War 中的战斗统计字段"""
        war = War(id="test", name="Test War")
        self.assertEqual(war.battles_fought, 0)
        self.assertEqual(war.battles_won, 0)
        # 仅测试字段存在，不测试逻辑

    def test_contract_standard_warranty(self):
        """测试 Contract 中的标准质保期字段"""
        contract = Contract(id=1, contract_type=ContractType.PUBLIC_WORKS)
        self.assertEqual(contract.standard_warranty, 0)
        contract.standard_warranty = 5
        self.assertEqual(contract.standard_warranty, 5)

    def test_serialization_roundtrip(self):
        """测试整个 GameState 序列化包含新字段"""
        # 添加一些数据
        city = self.state.create_city("Roma")
        province = Province(1, "Italia", 1000)
        province.add_city_id(city.city_id)
        self.state.add_province(province)
        war = War(id="war1", name="Test War", battles_fought=3, battles_won=2)
        # 需要将 war 添加到 state？war 通常由 war_system 管理，但为了测试序列化，我们可以在 state 中临时存储，但 war 不在 state 的顶层字段中，而是在 war_system 中。不过 war 有自己的序列化，我们只需测试 war 自身的 to_dict/from_dict。
        # 这里我们只测试 war 自身的序列化
        war_data = war.to_dict()
        new_war = War.from_dict(war_data)
        self.assertEqual(new_war.battles_fought, 3)
        self.assertEqual(new_war.battles_won, 2)

        # 测试 GameState 序列化包含城市
        state_dict = self.state.to_dict()
        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(state_dict)
        self.assertEqual(len(new_state.get_all_cities()), 1)
        self.assertEqual(new_state.get_city(1).name, "Roma")