import pytest
from src.core.entities.entities import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus

class TestProvince:
    """ENT-001 ~ ENT-003: Province实体测试"""

    def test_ent_001_province_creation(self, sample_province):
        """ENT-001: Province创建与属性初始化"""
        assert sample_province.province_id == 1
        assert sample_province.name == "西西里"
        assert sample_province.total_land == 1000
        assert sample_province.land_public == 600
        assert sample_province.land_private == 400
        assert sample_province.grievance == 0
        assert sample_province.tax_contract_id is None
        assert sample_province.project_contract_id is None
        assert sample_province.has_project is False

    def test_ent_002_update_land_type(self, sample_province):
        """ENT-002: 公/私地数量更新"""
        sample_province.update_land_type(50, -30)
        assert sample_province.land_public == 650
        assert sample_province.land_private == 370

        # 测试负值限制
        sample_province.update_land_type(-1000, -1000)
        assert sample_province.land_public == 0
        assert sample_province.land_private == 0

    def test_ent_003_grievance_range(self, sample_province):
        """ENT-003: 民怨值范围限制"""
        sample_province.set_grievance(2)
        assert sample_province.grievance == 2

        with pytest.raises(ValueError, match="Grievance must be between 0 and 3"):
            sample_province.set_grievance(5)

        with pytest.raises(ValueError, match="Grievance must be between 0 and 3"):
            sample_province.set_grievance(-1)


class TestContract:
    """ENT-004 ~ ENT-005: Contract实体测试"""

    def test_ent_004_contract_creation(self):
        """ENT-004: Contract创建与类型枚举（使用工厂方法）"""
        tax_contract = Contract.create_tax_farming(
            id=1,
            province="西西里",
            base_cost=90,
            expected_profit=150
        )
        project_contract = Contract.create_public_works(
            id=2,
            project="道路",
            budget=1000,
            profit_margin=0.2
        )

        assert tax_contract.contract_type == ContractType.TAX_FARMING
        assert project_contract.contract_type == ContractType.PUBLIC_WORKS
        assert tax_contract.id == 1
        assert project_contract.id == 2
        assert tax_contract.status == ContractStatus.PENDING
        # 修正：使用 awarded_to 而非 winner_id
        assert tax_contract.awarded_to is None
        assert tax_contract.is_under_execution is False
        assert tax_contract.profit_base == 0
        # 验证工程合同预期利润计算
        assert project_contract.expected_profit == 200

    def test_ent_005_contract_mark_winner(self):
        """ENT-005: 合同中标状态变更"""
        contract = Contract(
            id=10,
            contract_type=ContractType.TAX_FARMING,
            name="测试合同",
            base_cost=500,
            expected_profit=200,
            duration_years=3,
            target_province="西西里"
        )
        contract.status = ContractStatus.BUDGETED  # 设为 BUDGETED
        assert contract.status == ContractStatus.BUDGETED

        contract.mark_winner(winner_id=1001, current_turn=5, profit_base=20)

        assert contract.status == ContractStatus.ACTIVE
        assert contract.awarded_to == 1001
        assert contract.awarded_turn == 5
        assert contract.profit_base == 20
        assert contract.is_under_execution is True