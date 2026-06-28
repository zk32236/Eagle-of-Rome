# src/tests/test_entities/test_province.py
"""
Province 实体单元测试
"""

import unittest
import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.entities.entities import Province


class TestProvince(unittest.TestCase):
    """Province 类测试"""

    def test_initialization(self):
        """测试初始化，验证土地按 60/40 分配"""
        province = Province(1, "西西里", 1000)

        self.assertEqual(province.province_id, 1)
        self.assertEqual(province.name, "西西里")
        self.assertEqual(province.total_land, 1000)
        self.assertEqual(province.land_public, 600)   # 1000 * 0.6
        self.assertEqual(province.land_private, 400)  # 1000 * 0.4
        self.assertEqual(province.tax_base, 0)
        self.assertEqual(province.grievance, 0)
        self.assertIsNone(province.tax_contract_id)
        self.assertIsNone(province.project_contract_id)
        self.assertFalse(province.has_project)

    def test_initialization_with_odd_number(self):
        """测试奇数总土地时的取整行为"""
        province = Province(2, "撒丁尼亚", 999)

        self.assertEqual(province.total_land, 999)
        self.assertEqual(province.land_public, 599)   # int(999*0.6)=599
        self.assertEqual(province.land_private, 399)  # int(999*0.4)=399
        self.assertEqual(province.land_public + province.land_private, 998)  # 取整损失1

    def test_update_land_type(self):
        """测试调整公/私地数量"""
        province = Province(3, "科西嘉", 500)
        self.assertEqual(province.land_public, 300)
        self.assertEqual(province.land_private, 200)

        # 正常调整
        province.update_land_type(50, -30)
        self.assertEqual(province.land_public, 350)
        self.assertEqual(province.land_private, 170)

        # 调整为负值，应被限制为0
        province.update_land_type(-400, -200)
        self.assertEqual(province.land_public, 0)
        self.assertEqual(province.land_private, 0)

    def test_bind_tax_contract(self):
        """测试绑定包税权合同"""
        province = Province(4, "山南高卢", 800)

        # 首次绑定
        province.bind_tax_contract(101)
        self.assertEqual(province.tax_contract_id, 101)

        # 重复绑定应抛出异常
        with self.assertRaises(ValueError) as context:
            province.bind_tax_contract(102)
        self.assertIn("already has a tax contract", str(context.exception))

    def test_bind_project_contract(self):
        """测试绑定公共工程合同"""
        province = Province(5, "伊利里亚", 1200)

        # 首次绑定
        province.bind_project_contract(201)
        self.assertEqual(province.project_contract_id, 201)
        self.assertTrue(province.has_project)

        # 重复绑定应抛出异常
        with self.assertRaises(ValueError) as context:
            province.bind_project_contract(202)
        self.assertIn("already has a project contract", str(context.exception))

    def test_unbind_contracts(self):
        """测试解绑合同"""
        province = Province(6, "阿非利加", 1500)

        # 绑定后解绑
        province.bind_tax_contract(301)
        province.bind_project_contract(401)

        self.assertEqual(province.tax_contract_id, 301)
        self.assertEqual(province.project_contract_id, 401)
        self.assertTrue(province.has_project)

        # 解绑
        province.unbind_tax_contract()
        province.unbind_project_contract()

        self.assertIsNone(province.tax_contract_id)
        self.assertIsNone(province.project_contract_id)
        self.assertFalse(province.has_project)

    def test_set_grievance(self):
        """测试设置民怨值"""
        province = Province(7, "希腊", 2000)

        # 正常范围
        province.set_grievance(2)
        self.assertEqual(province.grievance, 2)

        province.set_grievance(0)
        self.assertEqual(province.grievance, 0)

        province.set_grievance(3)
        self.assertEqual(province.grievance, 3)

        # 超出范围
        with self.assertRaises(ValueError) as context:
            province.set_grievance(4)
        self.assertIn("must be between 0 and 3", str(context.exception))

        with self.assertRaises(ValueError) as context:
            province.set_grievance(-1)
        self.assertIn("must be between 0 and 3", str(context.exception))


if __name__ == "__main__":
    unittest.main()