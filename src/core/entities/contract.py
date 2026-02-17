# src/core/entities/contract.py

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto


class ContractType(Enum):
    """合同类型"""
    TAX_FARMING = "tax_farming"  # 包税：行省税收权
    PUBLIC_WORKS = "public_works"  # 工程：公共建设


class ContractStatus(Enum):
    """合同状态"""
    PENDING = "pending"  # 等待授予
    ACTIVE = "active"  # 执行中
    COMPLETED = "completed"  # 已完成
    EXPIRED = "expired"  # 过期（未授予）


@dataclass
class Contract:
    """
    合同实体

    包税合同（Tax Farming）：
    - 骑士预付资金购买税收权
    - 执行期：5年（MVP简化：一次性或分年）
    - 收益：实际税收 - 预付成本

    工程合同（Public Works）：
    - 国库出资，骑士执行
    - 成本：建设费用
    - 利润：承包价 - 实际成本（智略影响成本）
    """

    id: int
    contract_type: ContractType
    status: ContractStatus = ContractStatus.PENDING

    # 基本信息
    name: str = ""  # 合同名称（如"西西里包税权"）
    description: str = ""  # 描述

    # 财务参数
    base_cost: int = 0  # 基础成本/投资额
    expected_profit: int = 0  # 预期收益/利润
    duration_years: int = 1  # 执行年限（MVP简化）

    # 关联信息
    target_province: Optional[str] = None  # 目标行省（包税）
    project_type: Optional[str] = None  # 项目类型（工程）

    # 授予信息
    awarded_to: Optional[int] = None  # 授予的人物ID
    awarded_faction: Optional[str] = None  # 授予的派系ID
    awarded_turn: Optional[int] = None  # 授予回合

    # 执行状态
    remaining_years: int = 0  # 剩余年限
    total_collected: int = 0  # 已收收益（包税）
    total_spent: int = 0  # 已支成本（工程）

    def __repr__(self) -> str:
        type_emoji = {
            ContractType.TAX_FARMING: "📊",
            ContractType.PUBLIC_WORKS: "🏗️"
        }.get(self.contract_type, "📋")

        status_icon = {
            ContractStatus.PENDING: "⏳",
            ContractStatus.ACTIVE: "▶️",
            ContractStatus.COMPLETED: "✅",
            ContractStatus.EXPIRED: "❌"
        }.get(self.status, "❓")

        return (f"{type_emoji}{status_icon} {self.name} "
                f"[成本:{self.base_cost} 收益:{self.expected_profit}]")

    @classmethod
    def create_tax_farming(cls, id: int, province: str, base_cost: int, expected_profit: int) -> "Contract":
        """创建包税合同"""
        return cls(
            id=id,
            contract_type=ContractType.TAX_FARMING,
            name=f"{province}包税权",
            description=f"{province}行省税收承包权，预付{base_cost}塔兰特",
            base_cost=base_cost,
            expected_profit=expected_profit,
            duration_years=5,  # 历史5年，MVP可简化
            target_province=province
        )

    @classmethod
    def create_public_works(cls, id: int, project: str, budget: int, profit_margin: float = 0.2) -> "Contract":
        """创建工程合同"""
        # 利润 = 预算 × 利润率（智略可提升利润率）
        expected_profit = int(budget * profit_margin)

        return cls(
            id=id,
            contract_type=ContractType.PUBLIC_WORKS,
            name=f"{project}工程",
            description=f"{project}建设项目，国库出资{budget}塔兰特",
            base_cost=budget,  # 国库出资
            expected_profit=expected_profit,
            duration_years=2,  # 工程通常2年完成
            project_type=project
        )

    # ==================== MVP 0.4.3 新增方法 ====================

    def award(self, figure_id: int, faction_id: str, turn: int) -> bool:
        """授予合同给指定人物"""
        if self.status != ContractStatus.PENDING:
            return False

        self.awarded_to = figure_id
        self.awarded_faction = faction_id
        self.awarded_turn = turn
        self.status = ContractStatus.ACTIVE
        self.remaining_years = self.duration_years
        return True

    def execute_tax_collection(self) -> int:
        """执行包税收益结算（每年调用）"""
        if self.status != ContractStatus.ACTIVE:
            return 0
        if self.contract_type != ContractType.TAX_FARMING:
            return 0

        # MVP简化：每年固定收益
        annual_profit = self.expected_profit // self.duration_years
        self.total_collected += annual_profit
        self.remaining_years -= 1

        if self.remaining_years <= 0:
            self.status = ContractStatus.COMPLETED

        return annual_profit

    def execute_works_payment(self) -> int:
        """执行工程付款结算（每年调用）"""
        if self.status != ContractStatus.ACTIVE:
            return 0
        if self.contract_type != ContractType.PUBLIC_WORKS:
            return 0

        # MVP简化：每年支付部分预算
        annual_payment = self.base_cost // self.duration_years
        annual_profit = self.expected_profit // self.duration_years
        self.total_spent += annual_payment
        self.remaining_years -= 1

        if self.remaining_years <= 0:
            self.status = ContractStatus.COMPLETED

        return annual_profit

    def expire(self):
        """合同过期（未在有效期内授予）"""
        if self.status == ContractStatus.PENDING:
            self.status = ContractStatus.EXPIRED

    def get_annual_revenue(self) -> int:
        """获取年度收益"""
        if self.status != ContractStatus.ACTIVE:
            return 0
        if self.contract_type == ContractType.TAX_FARMING:
            return self.expected_profit // self.duration_years
        elif self.contract_type == ContractType.PUBLIC_WORKS:
            return self.expected_profit // self.duration_years
        return 0