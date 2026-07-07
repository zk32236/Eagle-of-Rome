"""
测试 Contract 类新增的工程合同字段及方法。
"""

import pytest
from src.core.entities.contract import Contract, ContractType, ContractStatus


class TestContractExt:
    """Contract 类新增工程合同字段测试"""

    def test_contract_works_fields_defaults(self):
        """测试工程合同新增字段的默认值"""
        contract = Contract(
            id=1,
            contract_type=ContractType.PUBLIC_WORKS,
            _province_id=10,
            _create_turn=5
        )
        # 工程合同特有字段默认值应为0
        assert contract.construction_years == 0
        assert contract.warranty_years == 0
        assert contract.annual_income == 0
        assert contract.annual_cost == 0
        assert contract.warranty_remaining == 0
        assert contract.original_budget == 0

    def test_contract_works_fields_set(self):
        """测试设置工程合同字段值（通过私有属性赋值）"""
        contract = Contract(
            id=2,
            contract_type=ContractType.PUBLIC_WORKS,
            _province_id=20,
            _create_turn=6
        )
        contract._construction_years = 3
        contract._warranty_years = 5
        contract._annual_income = 100
        contract._annual_cost = 80
        contract._warranty_remaining = 5
        contract._original_budget = 500

        assert contract.construction_years == 3
        assert contract.warranty_years == 5
        assert contract.annual_income == 100
        assert contract.annual_cost == 80
        assert contract.warranty_remaining == 5
        assert contract.original_budget == 500

    def test_mark_winner_sets_fields_correctly(self):
        """测试 mark_winner 方法设置中标者及相关字段"""
        contract = Contract(
            id=3,
            contract_type=ContractType.TAX_FARMING,
            _province_id=30,
            _create_turn=7
        )
        # 必须先设为 BUDGETED
        contract.status = ContractStatus.BUDGETED
        assert contract.status == ContractStatus.BUDGETED

        contract.mark_winner(winner_id=101, current_turn=8, profit_base=50)

        assert contract.status == ContractStatus.ACTIVE
        assert contract.awarded_to == 101
        assert contract.awarded_turn == 8
        assert contract.profit_base == 50
        assert contract.is_under_execution is True
        assert contract.remaining_years == contract.duration_years

    def test_mark_complete_works(self):
        """测试 mark_complete 方法标记合同完成"""
        contract = Contract(
            id=4,
            contract_type=ContractType.PUBLIC_WORKS,
            _province_id=40,
            _create_turn=9
        )
        contract.status = ContractStatus.BUDGETED  # 先设为 BUDGETED
        contract.mark_winner(winner_id=201, current_turn=10, profit_base=0)
        contract._is_under_execution = True
        contract.status = ContractStatus.ACTIVE

        contract.mark_complete(current_turn=10)

        assert contract.status == ContractStatus.COMPLETED
        assert contract.is_under_execution is False
        assert contract.complete_turn == 10

    def test_terminate_works(self):
        """测试 terminate 方法强制终止合同"""
        contract = Contract(
            id=5,
            contract_type=ContractType.PUBLIC_WORKS,
            _province_id=50,
            _create_turn=11
        )
        contract.status = ContractStatus.BUDGETED
        contract.mark_winner(winner_id=202, current_turn=12, profit_base=0)
        contract._is_under_execution = True
        contract.status = ContractStatus.ACTIVE

        contract.terminate()

        assert contract.status == ContractStatus.EXPIRED
        assert contract.is_under_execution is False
        assert contract.complete_turn is None