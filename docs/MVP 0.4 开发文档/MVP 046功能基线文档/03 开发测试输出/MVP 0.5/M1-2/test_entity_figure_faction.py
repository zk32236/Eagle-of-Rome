import unittest
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction


class TestFigureMVP05(unittest.TestCase):
    """测试 Figure 类 MVP 0.5 新增功能"""

    def test_add_contract(self):
        fig = Figure(id=1001, name="西塞罗")
        fig._figure_type = "knight"
        fig.add_contract(1)
        self.assertEqual(fig.contract_ids, [1])
        self.assertTrue(fig.has_active_contract)

    def test_remove_contract(self):
        fig = Figure(id=1001, name="西塞罗")
        fig._figure_type = "knight"
        fig.add_contract(1)
        fig.remove_contract(1)
        self.assertEqual(fig.contract_ids, [])
        self.assertFalse(fig.has_active_contract)

    def test_settle_contract_profit(self):
        fig = Figure(id=1001, name="西塞罗")
        fig.wealth = 100
        fig.settle_contract_profit(50)
        self.assertEqual(fig.wealth, 150)


class TestFactionMVP05(unittest.TestCase):
    """测试 Faction 类 MVP 0.5 新增功能"""

    def test_update_total_land(self):
        faction = Faction(id="F1", name="元老派")
        member1 = Figure(id=1, name="甲")
        member1._land_private = 100
        member2 = Figure(id=2, name="乙")
        member2._land_private = 200
        faction.update_total_land([member1, member2])
        self.assertEqual(faction.total_land, 300)

    def test_add_province(self):
        faction = Faction(id="F1", name="元老派")
        faction.add_province(1)
        faction.add_province(1)  # 重复添加不应增加
        self.assertEqual(faction.province_owned, [1])

    def test_update_knight_contract_count(self):
        faction = Faction(id="F1", name="元老派")
        knight1 = Figure(id=3, name="骑士甲")
        knight1._figure_type = "knight"
        knight1._has_active_contract = True
        knight2 = Figure(id=4, name="骑士乙")
        knight2._figure_type = "knight"
        knight2._has_active_contract = False
        faction.update_knight_contract_count([knight1, knight2])
        self.assertEqual(faction.knight_contract_count, 1)


if __name__ == '__main__':
    unittest.main()