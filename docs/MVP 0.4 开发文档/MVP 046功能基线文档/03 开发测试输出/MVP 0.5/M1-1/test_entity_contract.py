# src/tests/test_entities/test_contract.py
"""
Contract 实体单元测试
测试 MVP 0.4.6 原有功能 + MVP 0.5 新增功能
"""

import unittest
import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.entities.contract import Contract, ContractType, ContractStatus


class TestContract(unittest.TestCase):
    """Contract 类测试"""

    def test_create_tax_farming(self):
        """测试创建包税合同"""
        contract = Contract.create_tax_farming(1, "西西里", 90, 150)

        self.assertEqual(contract.id, 1)
        self.assertEqual(contract.contract_type, ContractType.TAX_FARMING)
        self.assertEqual(contract.status, ContractStatus.PENDING)
        self.assertEqual(contract.name, "西西里包税权")
        self.assertEqual(contract.base_cost, 90)
        self.assertEqual(contract.expected_profit, 150)
        self.assertEqual(contract.duration_years, 5)
        self.assertEqual(contract.target_province, "西西里")
        self.assertIsNone(contract.awarded_to)

    def test_create_public_works(self):
        """测试创建工程合同"""
        contract = Contract.create_public_works(2, "罗马大道", 200)

        self.assertEqual(contract.id, 2)
        self.assertEqual(contract.contract_type, ContractType.PUBLIC_WORKS)
        self.assertEqual(contract.status, ContractStatus.PENDING)
        self.assertEqual(contract.name, "罗马大道工程")
        self.assertEqual(contract.base_cost, 200)
        self.assertEqual(contract.expected_profit, 40)  # 200 * 0.2
        self.assertEqual(contract.duration_years, 2)
        self.assertEqual(contract.project_type, "罗马大道")

    # === MVP 0.4.6 原有功能测试 ===

    def test_award(self):
        """测试授予合同（原有功能）"""
        contract = Contract.create_tax_farming(3, "撒丁尼亚", 80, 120)

        result = contract.award(1001, "senate", 5)

        self.assertTrue(result)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)
        self.assertEqual(contract.awarded_to, 1001)
        self.assertEqual(contract.awarded_faction, "senate")
        self.assertEqual(contract.awarded_turn, 5)
        self.assertEqual(contract.remaining_years, 5)

        # 不能重复授予
        result = contract.award(1002, "populares", 6)
        self.assertFalse(result)

    def test_execute_tax_collection(self):
        """测试包税收益结算"""
        contract = Contract.create_tax_farming(4, "科西嘉", 100, 200)
        contract.award(1001, "senate", 1)

        # 第一年
        profit = contract.execute_tax_collection()
        self.assertEqual(profit, 40)  # 200 // 5
        self.assertEqual(contract.total_collected, 40)
        self.assertEqual(contract.remaining_years, 4)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)

        # 执行4次直到完成
        for _ in range(4):
            contract.execute_tax_collection()

        self.assertEqual(contract.status, ContractStatus.COMPLETED)
        self.assertEqual(contract.total_collected, 200)

    def test_execute_works_payment(self):
        """测试工程付款结算"""
        contract = Contract.create_public_works(5, "水道桥", 300)
        contract.award(1002, "equites", 1)

        # 第一年
        profit = contract.execute_works_payment()
        self.assertEqual(profit, 30)  # 60 // 2 (expected_profit=60)
        self.assertEqual(contract.total_spent, 150)  # 300 // 2
        self.assertEqual(contract.remaining_years, 1)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)

        # 第二年
        profit = contract.execute_works_payment()
        self.assertEqual(profit, 30)
        self.assertEqual(contract.total_spent, 300)
        self.assertEqual(contract.status, ContractStatus.COMPLETED)

    def test_expire(self):
        """测试合同过期"""
        contract = Contract.create_tax_farming(6, "山南高卢", 70, 100)
        self.assertEqual(contract.status, ContractStatus.PENDING)

        contract.expire()
        self.assertEqual(contract.status, ContractStatus.EXPIRED)

        # 已激活的合同不能过期
        contract2 = Contract.create_public_works(7, "港口", 150)
        contract2.award(1003, "senate", 1)
        contract2.expire()
        self.assertEqual(contract2.status, ContractStatus.ACTIVE)  # 不应改变

    def test_get_annual_revenue(self):
        """测试获取年度收益"""
        contract = Contract.create_tax_farming(8, "伊利里亚", 60, 150)
        self.assertEqual(contract.get_annual_revenue(), 0)  # 未激活

        contract.award(1004, "senate", 1)
        self.assertEqual(contract.get_annual_revenue(), 30)  # 150 // 5

    # === MVP 0.5 新增功能测试 ===

    def test_mvp05_new_fields(self):
        """测试 MVP 0.5 新增字段的初始值"""
        contract = Contract.create_tax_farming(9, "希腊", 100, 200)

        # 验证新增字段默认值
        self.assertEqual(contract.profit_base, 0)
        self.assertFalse(contract.is_under_execution)
        self.assertIsNone(contract.complete_turn)

    def test_mark_winner(self):
        """测试 mark_winner 方法"""
        contract = Contract.create_tax_farming(10, "阿非利加", 120, 180)

        contract.mark_winner(2001, 10, 90)

        self.assertEqual(contract.status, ContractStatus.ACTIVE)
        self.assertEqual(contract.awarded_to, 2001)
        self.assertEqual(contract.awarded_turn, 10)
        self.assertEqual(contract.remaining_years, 5)
        self.assertTrue(contract.is_under_execution)
        self.assertEqual(contract.profit_base, 90)

        # 已激活的合同不能再次标记
        with self.assertRaises(ValueError) as context:
            contract.mark_winner(2002, 11, 95)
        self.assertIn("cannot be awarded", str(context.exception))

    def test_mark_complete(self):
        """测试 mark_complete 方法"""
        contract = Contract.create_public_works(11, "神殿修缮", 400)
        contract.mark_winner(2003, 15, 80)

        self.assertTrue(contract.is_under_execution)

        contract.mark_complete(17)

        self.assertFalse(contract.is_under_execution)
        self.assertEqual(contract.status, ContractStatus.COMPLETED)
        self.assertEqual(contract.complete_turn, 17)

    def test_terminate(self):
        """测试 terminate 方法"""
        contract = Contract.create_tax_farming(12, "西班牙", 150, 250)
        contract.mark_winner(2004, 20, 120)

        self.assertTrue(contract.is_under_execution)
        self.assertEqual(contract.status, ContractStatus.ACTIVE)

        contract.terminate()

        self.assertFalse(contract.is_under_execution)
        self.assertEqual(contract.status, ContractStatus.EXPIRED)
        self.assertIsNone(contract.complete_turn)  # 非正常结束

    def test_mark_winner_vs_award_coexistence(self):
        """验证 mark_winner 和 award 可以共存且互不影响"""
        contract = Contract.create_tax_farming(13, "高卢", 200, 300)

        # 使用原有 award 方法
        result1 = contract.award(3001, "senate", 25)
        self.assertTrue(result1)
        self.assertEqual(contract.awarded_to, 3001)

        # 重置合同（测试用，实际业务中不会这样）
        contract2 = Contract.create_tax_farming(14, "不列颠", 180, 270)

        # 使用新的 mark_winner 方法
        contract2.mark_winner(3002, 30, 135)
        self.assertEqual(contract2.awarded_to, 3002)
        self.assertEqual(contract2.profit_base, 135)

        # 两个方法都能正确设置 awarded_to
        self.assertNotEqual(contract.awarded_to, contract2.awarded_to)


if __name__ == "__main__":
    unittest.main()