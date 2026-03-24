# src/core/entities/contract.py

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


class ContractType(Enum):
    """合同类型"""
    TAX_FARMING = "tax_farming"  # 包税：行省税收权
    PUBLIC_WORKS = "public_works"  # 工程：公共建设


class ContractStatus(Enum):
    PENDING = "pending"
    BUDGETED = "budgeted"   # 新增
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass
class Contract:
    id: int
    contract_type: ContractType

    # === MVP 0.5 新增必需字段（放在前面，无默认值）===
    _province_id: int = 0  # 行省ID
    _create_turn: int = 0  # 创建回合
    _annual_profit: int = 0  # 年净收入（中标后设置）

    # === MVP 0.5 公共工程新增字段 ===
    _original_budget: int = 0  # 原始预算
    _construction_years: int = 0  # 实际施工周期
    _warranty_years: int = 0  # 实际质保周期
    _annual_income: int = 0  # 骑士年收入
    _warranty_remaining: int = 0  # 剩余质保年限
    _annual_cost: int = 0  # 骑士年支出
    _is_extended: bool = False
    _standard_warranty: int = 0

    status: ContractStatus = ContractStatus.PENDING

    # === MVP 0.7-4 舰队合同 ===
    _is_fleet_construction: bool = False  # 是否为舰队建造合同
    _recommended_fleet_composition: List[Dict[str, Any]] = field(default_factory=list)
    _enemy_strength: int = 0  # 敌方海军强度（用于参考）
    _total_budget: int = 0  # 总预算（所有舰队建造成本之和）

    # 基本信息
    name: str = ""
    description: str = ""

    # 财务参数
    base_cost: int = 0
    expected_profit: int = 0
    duration_years: int = 1

    # 关联信息
    target_province: Optional[str] = None
    project_type: Optional[str] = None

    # 授予信息
    awarded_to: Optional[int] = None
    awarded_faction: Optional[str] = None
    awarded_turn: Optional[int] = None

    # 执行状态
    remaining_years: int = 0
    total_collected: int = 0
    total_spent: int = 0

    # === MVP 0.5 新增字段（私有）===
    _profit_base: int = 0
    _is_under_execution: bool = False
    _complete_turn: Optional[int] = None

    # === 竞标功能新增字段 ===
    _bids: List[Dict] = field(default_factory=list)      # 存储所有出价记录
    _winning_bid: Optional[Dict] = None                   # 中标记录（含 bidder_id, amount, tax_rate）
    _tax_rate: Optional[float] = None                     # 实际税率（中标者承诺的加价比例）

    # === 包税权竞标功能新增字段 ===
    _contract_price: int = 0  # 年合同价
    _profit_rate: float = 0.0  # 利润率 p


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

    @property
    def contract_price(self) -> int:
        return self._contract_price

    @property
    def profit_rate(self) -> float:
        return self._profit_rate

    @property
    def standard_warranty(self) -> int:
        return self._standard_warranty

    @standard_warranty.setter
    def standard_warranty(self, value: int):
        self._standard_warranty = value

    @property
    def recommended_fleet_composition(self) -> List[Dict[str, Any]]:
        return self._recommended_fleet_composition.copy()

    @property
    def enemy_strength(self) -> int:
        return self._enemy_strength

    @property
    def total_budget(self) -> int:
        return self._total_budget

    def set_fleet_composition(self, composition: List[Dict[str, Any]], enemy_strength: int, total_budget: int):
        """设置舰队组成建议"""
        self._recommended_fleet_composition = composition
        self._enemy_strength = enemy_strength
        self._total_budget = total_budget

    @property
    def is_fleet_construction(self) -> bool:
        return self._is_fleet_construction

    @is_fleet_construction.setter
    def is_fleet_construction(self, value: bool):
        self._is_fleet_construction = value

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
        expected_profit = int(budget * profit_margin)
        return cls(
            id=id,
            contract_type=ContractType.PUBLIC_WORKS,
            name=f"{project}工程",
            description=f"{project}建设项目，国库出资{budget}塔兰特",
            base_cost=budget,
            expected_profit=expected_profit,
            duration_years=2,
            project_type=project
        )

    # ==================== MVP 0.4.3 原有方法 ====================

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

    # === MVP 0.5 新增属性访问器 ===
    @property
    def province_id(self) -> int:
        return self._province_id

    @property
    def create_turn(self) -> int:
        return self._create_turn

    @property
    def profit_base(self) -> int:
        return self._profit_base

    @property
    def is_under_execution(self) -> bool:
        return self._is_under_execution

    @property
    def complete_turn(self) -> Optional[int]:
        return self._complete_turn

    # === 竞标功能新增属性 ===
    @property
    def bids(self) -> List[Dict]:
        """返回所有出价记录的副本"""
        return self._bids.copy()

    @property
    def winning_bid(self) -> Optional[Dict]:
        """返回中标记录，包含 bidder_id, amount, tax_rate"""
        return self._winning_bid

    @property
    def tax_rate(self) -> Optional[float]:
        """返回实际税率（中标者的加价比例）"""
        return self._tax_rate

    @property
    def original_budget(self) -> int:
        return self._original_budget

    @property
    def construction_years(self) -> int:
        return self._construction_years

    @property
    def warranty_years(self) -> int:
        return self._warranty_years

    @property
    def annual_income(self) -> int:
        return self._annual_income

    @property
    def annual_profit(self) -> int:
        return self._annual_profit

    @property
    def warranty_remaining(self) -> int:
        return self._warranty_remaining

    @property
    def annual_cost(self) -> int:
        return self._annual_cost

    @property
    def is_extended(self) -> bool:
        return self._is_extended


    # === MVP 0.5 新增方法 ===
    def set_extended(self, extended: bool = True):
        self._is_extended = extended

    def mark_winner(self, winner_id: int, current_turn: int, profit_base: int) -> None:
        """
        标记中标，激活合同。
        只允许 BUDGETED 状态的合同中标。
        """
        if self.status != ContractStatus.BUDGETED:
            raise ValueError(f"Contract {self.id} cannot be awarded: status is {self.status.value} (must be BUDGETED)")
        self.awarded_to = winner_id
        self.awarded_turn = current_turn
        self.status = ContractStatus.ACTIVE
        self.remaining_years = self.duration_years
        self._is_under_execution = True
        self._profit_base = profit_base

    def mark_complete(self, current_turn: int) -> None:
        self._is_under_execution = False
        self.status = ContractStatus.COMPLETED
        self._complete_turn = current_turn

    def terminate(self) -> None:
        self._is_under_execution = False
        self.status = ContractStatus.EXPIRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "contract_type": self.contract_type.value,
            "_province_id": self._province_id,
            "_create_turn": self._create_turn,
            "_contract_price": self._contract_price,
            "_profit_rate": self._profit_rate,
            "_original_budget": self._original_budget,
            "_construction_years": self._construction_years,
            "_warranty_years": self._warranty_years,
            "_annual_income": self._annual_income,
            "_warranty_remaining": self._warranty_remaining,
            "_annual_cost": self._annual_cost,
            "_is_extended": self._is_extended,
            "_standard_warranty": self._standard_warranty,
            "status": self.status.value,
            "name": self.name,
            "description": self.description,
            "base_cost": self.base_cost,
            "expected_profit": self.expected_profit,
            "duration_years": self.duration_years,
            "target_province": self.target_province,
            "project_type": self.project_type,
            "awarded_to": self.awarded_to,
            "awarded_faction": self.awarded_faction,
            "awarded_turn": self.awarded_turn,
            "remaining_years": self.remaining_years,
            "total_collected": self.total_collected,
            "total_spent": self.total_spent,
            "_profit_base": self._profit_base,
            "_is_under_execution": self._is_under_execution,
            "_complete_turn": self._complete_turn,
            "_bids": self._bids,
            "_winning_bid": self._winning_bid,
            "_tax_rate": self._tax_rate,
            "_is_fleet_construction": self._is_fleet_construction,
            "_recommended_fleet_composition": self._recommended_fleet_composition,
            "_enemy_strength": self._enemy_strength,
            "_total_budget": self._total_budget,
            "_annual_profit": self._annual_profit,  # 兼容
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Contract":
        contract = Contract(
            id=data["id"],
            contract_type=ContractType(data["contract_type"]),
            _province_id=data.get("_province_id", 0),
            _create_turn=data.get("_create_turn", 0),
            _contract_price=data.get("_contract_price", 0),
            _profit_rate=data.get("_profit_rate", 0.0),
            _original_budget=data.get("_original_budget", 0),
            _construction_years=data.get("_construction_years", 0),
            _warranty_years=data.get("_warranty_years", 0),
            _annual_income=data.get("_annual_income", 0),
            _warranty_remaining=data.get("_warranty_remaining", 0),
            _annual_cost=data.get("_annual_cost", 0),
            _is_extended=data.get("_is_extended", False),
            _standard_warranty=data.get("_standard_warranty", 0),
            status=ContractStatus(data.get("status", "pending")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            base_cost=data.get("base_cost", 0),
            expected_profit=data.get("expected_profit", 0),
            duration_years=data.get("duration_years", 1),
            target_province=data.get("target_province"),
            project_type=data.get("project_type"),
            awarded_to=data.get("awarded_to"),
            awarded_faction=data.get("awarded_faction"),
            awarded_turn=data.get("awarded_turn"),
            remaining_years=data.get("remaining_years", 0),
            total_collected=data.get("total_collected", 0),
            total_spent=data.get("total_spent", 0),
            _profit_base=data.get("_profit_base", 0),
            _is_under_execution=data.get("_is_under_execution", False),
            _complete_turn=data.get("_complete_turn"),
            _bids=data.get("_bids", []),
            _winning_bid=data.get("_winning_bid"),
            _tax_rate=data.get("_tax_rate"),
            _is_fleet_construction=data.get("_is_fleet_construction", False),
            _recommended_fleet_composition=data.get("_recommended_fleet_composition", []),
            _enemy_strength=data.get("_enemy_strength", 0),
            _total_budget=data.get("_total_budget", 0),
            _annual_profit=data.get("_annual_profit", 0),
        )
        return contract