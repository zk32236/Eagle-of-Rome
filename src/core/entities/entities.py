# src/core/entities/entities.py

from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from src.core.entities.figure import ClassTier

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.figure import Figure  # 仅类型检查时导入


@dataclass
class Senator:
    """
    元老实体 - 使用抽象属性名，显示通过TerminologyService映射
    """

    id: int
    name: str
    faction_id: str

    # 核心能力（属性名保持英文，显示时映射）
    military: int = 0
    oratory: int = 0
    loyalty: int = 0
    influence: int = 0

    is_faction_leader: bool = False  # 原is_consul，抽象化
    is_dead: bool = False
    is_present: bool = True  # 原is_in_rome

    leader_history: List[int] = field(default_factory=list)  # 原consul_history

    def get_voting_power(self) -> int:
        """投票权 = 演说 + 影响力"""
        return self.oratory + self.influence

    def can_be_candidate(self, current_turn: int, cooldown: int = 10) -> bool:
        """检查参选资格"""
        if self.is_faction_leader:
            return False

        for term_turn in self.leader_history:
            years_ago = current_turn - term_turn
            if 0 < years_ago < cooldown:
                return False
        return True

    def years_since_last_leadership(self, current_turn: int) -> Optional[int]:
        """距上次担任领袖的年数"""
        if not self.leader_history:
            return None
        return current_turn - max(self.leader_history)

    def __repr__(self) -> str:
        if self.is_dead:
            status = "☠️"
        elif self.is_faction_leader:
            status = "👑"
        else:
            status = "🟢"

        history = f"×{len(self.leader_history)}" if self.leader_history else ""
        return (f"{status} {self.name}(ID:{self.id})"
                f"[军{self.military}演{self.oratory}影{self.influence}]{history}")


@dataclass
class Faction:
    """派系实体 - MVP 0.4.5 新增动态领袖"""

    id: str
    name: str
    treasury: int = 0
    is_player: bool = False
    member_ids: List[int] = field(default_factory=list)

    # ==================== MVP 0.5 新增字段 ====================
    _total_land: int = 0                     # 派系成员私地总和
    _province_owned: List[int] = field(default_factory=list)  # 控制的行省ID列表
    _knight_contract_count: int = 0          # 派系内骑士持有的合同总数

    def get_senate_influence(self, state: 'GameState') -> int:
        total = 0
        for mid in self.member_ids:
            member = state.get_member(mid)
            if member and not member.is_dead and member.is_present and not member.is_absent:
                if member.class_tier == ClassTier.NOBILE:
                    total += member.influence
        return total

    def get_vacancies(self, state: 'GameState', member_limit: int) -> int:
        """计算派系空缺数（基于存活成员）"""
        current_members = len(self.get_members(state))
        return max(0, member_limit - current_members)

    def remove_member(self, member_id: int):
        """
        从派系成员列表中移除指定人物ID。
        """
        if member_id in self.member_ids:
            self.member_ids.remove(member_id)

    def get_total_influence(self, state: 'GameState', only_in_rome: bool = False) -> int:
        total = 0
        for mid in self.member_ids:
            member = state.get_member(mid)
            if member and not member.is_dead and member.is_present:
                if only_in_rome and member.is_absent:
                    continue
                total += member.influence
        return total

    def get_members(self, state: 'GameState') -> List['Figure']:
        """获取所有存活成员"""
        result = []
        for mid in self.member_ids:
            member = state.get_member(mid)
            if member and not member.is_dead:
                result.append(member)
        return result

    # ==================== MVP 0.4.5 新增 ====================

    def get_leader(self, state: 'GameState') -> Optional['Figure']:
        members = self.get_members(state)
        living = [m for m in members if not m.is_dead and m.is_present]
        if not living:
            return None
        return max(living, key=lambda m: m.influence)   # 原 m.power

    def update_faction_leader(self, state: 'GameState') -> Optional['Figure']:
        """更新派系领袖标记（应在权力变化后调用）"""
        # 清除旧领袖标记
        for m in self.get_members(state):
            m.is_faction_leader = False

        # 设置新领袖
        new_leader = self.get_leader(state)
        if new_leader:
            new_leader.is_faction_leader = True

        return new_leader

    def __repr__(self) -> str:
        return f"{self.name}({self.id})[💰{self.treasury}]"

    # ==================== MVP 0.5 新增方法 ====================

    def update_total_land(self, members: List['Figure']) -> None:
        """
        根据派系成员列表更新派系总土地（成员私地之和）。

        Args:
            members: 派系存活成员列表（通常由外部通过 GameState 获取）。
        """
        self._total_land = sum(m.land_private for m in members)

    def add_province(self, province_id: int) -> None:
        """
        添加行省 ID 到控制列表，避免重复。

        Args:
            province_id: 行省ID。
        """
        if province_id not in self._province_owned:
            self._province_owned.append(province_id)

    def update_knight_contract_count(self, knights: List['Figure']) -> None:
        """
        统计派系内所有骑士的合同总数。

        Args:
            knights: 派系内的骑士成员列表（通常由外部筛选后传入）。
        """
        self._knight_contract_count = sum(1 for k in knights if k.has_active_contract)

    # ==================== MVP 0.5 新增属性访问器 ====================

    @property
    def total_land(self) -> int:
        """获取派系成员私地总和"""
        return self._total_land

    @property
    def province_owned(self) -> List[int]:
        """获取派系控制的行省ID列表（返回副本，防止外部修改）"""
        return self._province_owned.copy()

    @property
    def knight_contract_count(self) -> int:
        """获取派系内骑士持有的合同总数"""
        return self._knight_contract_count


@dataclass
class GameTurn:
    """回合状态"""

    turn_number: int = 1
    year: int = -264
    current_phase: str = "init"
    leader_ids: List[int] = field(default_factory=list)  # 原consul_ids

    def advance_year(self):
        """推进到下一年"""
        self.turn_number += 1
        self.year += 1

    def get_year_display(self) -> str:
        return f"{abs(self.year)} BC" if self.year < 0 else f"{self.year} AD"

    def __repr__(self) -> str:
        return f"Turn {self.turn_number} ({self.get_year_display()})"


# ==================== MVP 0.5 新增：Province 类 ====================

class Province:
    """
    行省实体 - MVP 0.5 新增

    管理行省的土地、税收合同和公共工程合同。
    """
    def __init__(self, province_id: int, name: str, total_land: int):
        """
        初始化行省。

        Args:
            province_id: 行省唯一ID。
            name: 行省名称。
            total_land: 行省总土地面积。
        """
        self._province_id = province_id
        self._name = name
        self._total_land = total_land

        # MVP 0.5 新增字段
        self._land_public = int(total_land * 0.6)  # 公地数量，按比例初始化
        self._land_private = int(total_land * 0.4) # 私地数量，按比例初始化
        self._tax_base = 0                         # 包税权基础税金
        self._grievance = 0                         # 民怨值 0-3
        self._tax_contract_id: Optional[int] = None # 包税权合同ID
        self._project_contract_id: Optional[int] = None # 公共工程合同ID
        self._has_project = False                    # 是否有生效公共工程
        self._turns_since_last_land_distribution = 0  # 仅对意大利有效

    # --- 属性访问器（只读）---
    @property
    def province_id(self) -> int:
        return self._province_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def total_land(self) -> int:
        return self._total_land

    @property
    def land_public(self) -> int:
        return self._land_public

    @property
    def land_private(self) -> int:
        return self._land_private

    @property
    def tax_base(self) -> int:
        return self._tax_base

    @property
    def grievance(self) -> int:
        return self._grievance

    @property
    def tax_contract_id(self) -> Optional[int]:
        return self._tax_contract_id

    @property
    def project_contract_id(self) -> Optional[int]:
        return self._project_contract_id

    @property
    def has_project(self) -> bool:
        return self._has_project

    # --- 公共方法 ---
    def update_land_type(self, public_change: int, private_change: int) -> None:
        """
        调整公地/私地数量，保证非负。

        Args:
            public_change: 公地的变化量（可为负）。
            private_change: 私地的变化量（可为负）。
        """
        self._land_public = max(0, self._land_public + public_change)
        self._land_private = max(0, self._land_private + private_change)

    def bind_tax_contract(self, contract_id: int) -> None:
        """
        绑定包税权合同。

        Args:
            contract_id: 要绑定的合同ID。

        Raises:
            ValueError: 如果该行省已绑定包税权合同。
        """
        if self._tax_contract_id is not None:
            raise ValueError(f"Province {self._province_id} already has a tax contract (ID: {self._tax_contract_id})")
        self._tax_contract_id = contract_id

    def bind_project_contract(self, contract_id: int) -> None:
        """
        绑定公共工程合同。

        Args:
            contract_id: 要绑定的合同ID。

        Raises:
            ValueError: 如果该行省已绑定公共工程合同。
        """
        if self._project_contract_id is not None:
            raise ValueError(f"Province {self._province_id} already has a project contract (ID: {self._project_contract_id})")
        self._project_contract_id = contract_id
        self._has_project = True

    def unbind_tax_contract(self) -> None:
        """解绑包税权合同。"""
        self._tax_contract_id = None

    def unbind_project_contract(self) -> None:
        """解绑公共工程合同。"""
        self._project_contract_id = None
        self._has_project = False

    def set_grievance(self, value: int) -> None:
        """
        设置民怨值。

        Args:
            value: 新的民怨值，必须在0到3之间（含）。

        Raises:
            ValueError: 如果提供的值不在有效范围内。
        """
        if not (0 <= value <= 3):
            raise ValueError(f"Grievance must be between 0 and 3, got {value}")
        self._grievance = value