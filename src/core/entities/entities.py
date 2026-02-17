# src/core/entities/entities.py

from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

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

    def get_total_influence(self, state: 'GameState') -> int:
        """计算在场成员总影响力"""
        total = 0
        for mid in self.member_ids:
            member = state.get_member(mid)
            if member and not member.is_dead and member.is_present:
                total += member.power
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
        """获取当前派系领袖（权力最高者）"""
        members = self.get_members(state)
        living = [m for m in members if not m.is_dead and m.is_present]
        if not living:
            return None
        return max(living, key=lambda m: m.power)

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