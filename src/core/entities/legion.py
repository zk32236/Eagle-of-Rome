# src/core/entities/legion.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum, auto


class LegionStatus(Enum):
    """军团状态"""
    UNRAISED = auto()  # 未征召（在兵营中）
    ACTIVE = auto()  # 活跃（已指派）
    VETERAN = auto()  # 老兵（经历过战斗）
    DISBANDED = auto()  # 已解散


@dataclass
class Legion:
    """
    军团实体 - 罗马军团

    属性：
    - 编号：1-10号军团
    - 状态：未征召/活跃/老兵/解散
    - 维护费：每回合消耗
    - 战力：基础2点，老兵+1
    """

    # 基础信息
    number: int  # 军团编号（1-10）
    name: str = ""  # 军团名（如"Legio I"）

    # 状态
    status: LegionStatus = LegionStatus.UNRAISED
    is_veteran: bool = False  # 是否为老兵军团

    # 指派信息
    commander_id: Optional[int] = None  # 指派将领
    war_id: Optional[str] = None  # 指派战争

    # 历史
    battles_fought: int = 0
    battles_won: int = 0

    def __post_init__(self):
        if not self.name:
            self.name = f"Legio {self._roman_numeral()}"

    def _roman_numeral(self) -> str:
        """转换为罗马数字"""
        numerals = {
            1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
            6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"
        }
        return numerals.get(self.number, str(self.number))

    def get_combat_strength(self) -> int:
        """计算军团战力（用于CRT）"""
        base = 2  # 基础战力
        if self.is_veteran:
            base += 1  # 老兵+1
        return base

    def get_maintenance_cost(self) -> int:
        """计算维护费"""
        if self.status == LegionStatus.UNRAISED:
            return 0  # 未征召免费
        base = 2  # 基础维护费
        if self.is_veteran:
            base += 1  # 老兵更贵
        return base

    def can_be_recruited(self, state: 'GameState') -> bool:
        """检查是否可以征召"""
        return self.status == LegionStatus.UNRAISED

    def can_be_disbanded(self, state: 'GameState') -> bool:
        """检查是否可以解散"""
        # 不能在战斗中解散
        if self.war_id:
            return False
        return self.status == LegionStatus.ACTIVE

    def recruit(self, state: 'GameState') -> bool:
        """征召军团"""
        if not self.can_be_recruited(state):
            return False

        self.status = LegionStatus.ACTIVE
        return True

    def assign_to_war(self, war_id: str, commander_id: int) -> bool:
        """指派到战争"""
        if self.status != LegionStatus.ACTIVE:
            return False

        self.war_id = war_id
        self.commander_id = commander_id
        return True

    def recall(self) -> bool:
        """从战争召回"""
        self.war_id = None
        self.commander_id = None
        return True

    def disband(self) -> bool:
        """解散军团"""
        if not self.can_be_disbanded(None):
            return False

        self.status = LegionStatus.DISBANDED
        self.recall()
        return True

    def promote_to_veteran(self):
        """晋升为老兵（战斗胜利后）"""
        self.is_veteran = True
        self.battles_won += 1

    def to_display_dict(self) -> Dict[str, Any]:
        """转换为显示字典"""
        from core.localization import TerminologyService
        terms = TerminologyService.get()

        status_emoji = {
            LegionStatus.UNRAISED: "⚪",
            LegionStatus.ACTIVE: "🟢",
            LegionStatus.VETERAN: "⭐",
            LegionStatus.DISBANDED: "⚫",
        }.get(self.status, "❓")

        return {
            'name': self.name,
            'number': self.number,
            'status': self.status.name,
            'emoji': status_emoji,
            'strength': self.get_combat_strength(),
            'cost': self.get_maintenance_cost(),
            'veteran': self.is_veteran,
            'assigned': self.war_id is not None,
        }

    def __repr__(self) -> str:
        status_emoji = {
            LegionStatus.UNRAISED: "⚪",
            LegionStatus.ACTIVE: "🟢",
            LegionStatus.VETERAN: "⭐",
            LegionStatus.DISBANDED: "⚫",
        }.get(self.status, "❓")

        vet = "⭐" if self.is_veteran else ""
        assigned = f"→{self.war_id[:10]}..." if self.war_id else ""
        return f"{status_emoji} {self.name}{vet}[Str:{self.get_combat_strength()}]{assigned}"