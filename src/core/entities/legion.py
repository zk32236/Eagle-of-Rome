# src/core/entities/legion.py
# 修改内容：增加 DESTROYED 状态，添加 destroyed_turn 字段和 mark_destroyed 方法

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum, auto


class LegionStatus(Enum):
    """军团状态"""
    UNRAISED = auto()      # 未征召（在兵营中）
    ACTIVE = auto()         # 活跃（已指派）
    VETERAN = auto()        # 老兵（经历过战斗）
    DISBANDED = auto()      # 已解散
    DESTROYED = auto()      # 新增：被摧毁（等待恢复）


@dataclass
class Legion:
    """
    军团实体 - 罗马军团
    新增：_destroyed_turn 字段，记录被摧毁的回合数
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

    # ========== 新增字段 ==========
    _destroyed_turn: int = 0  # 被摧毁时的回合数（仅在 status == DESTROYED 时有效）

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

    # ========== 原有方法保持不变 ==========

    def get_combat_strength(self) -> int:
        """计算军团战力（用于CRT）"""
        base = 2  # 基础战力
        if self.is_veteran:
            base += 1  # 老兵+1
        return base

    def get_maintenance_cost(self, state):
        base = state.get_economic_rule("legion_maintenance_base", 2)
        if self.is_veteran:
            base += state.get_economic_rule("veteran_maintenance_bonus", 1)
        return base

    def can_be_recruited(self, state: 'GameState') -> bool:
        """检查是否可以征召（允许从 DISBANDED 恢复的军团征召）"""
        return self.status in (LegionStatus.UNRAISED, LegionStatus.DISBANDED)

    def can_be_disbanded(self, state: 'GameState') -> bool:
        """检查是否可以解散"""
        # 不能在战斗中解散
        if self.war_id:
            return False
        return self.status in (LegionStatus.ACTIVE, LegionStatus.VETERAN)

    def recruit(self, state: 'GameState') -> bool:
        """征召军团"""
        if not self.can_be_recruited(state):
            return False
        self.status = LegionStatus.ACTIVE
        return True

    def assign_to_war(self, war_id: str, commander_id: int) -> bool:
        """指派到战争"""
        if self.status not in (LegionStatus.ACTIVE, LegionStatus.VETERAN):
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

    # ========== 新增方法 ==========

    @property
    def destroyed_turn(self) -> int:
        """返回被摧毁时的回合数（仅当状态为 DESTROYED 时有意义）"""
        return self._destroyed_turn

    def mark_destroyed(self, current_turn: int):
        """
        标记军团被摧毁。
        设置状态为 DESTROYED，记录摧毁回合，清空指派信息。
        """
        self.status = LegionStatus.DESTROYED
        self._destroyed_turn = current_turn
        self.war_id = None
        self.commander_id = None
        # 摧毁后不再保留老兵状态（可配置，这里简单重置为 False）
        self.is_veteran = False

    def recover(self):
        """
        恢复军团（由外部调用，将 DESTROYED 转为 DISBANDED）。
        返回 True 表示恢复成功。
        """
        if self.status != LegionStatus.DESTROYED:
            return False
        self.status = LegionStatus.DISBANDED
        self._destroyed_turn = 0
        return True

    def to_display_dict(self) -> Dict[str, Any]:
        """转换为显示字典（已包含 DESTROYED 状态）"""
        from src.core.localization import TerminologyService
        terms = TerminologyService.get()

        status_emoji = {
            LegionStatus.UNRAISED: "⚪",
            LegionStatus.ACTIVE: "🟢",
            LegionStatus.VETERAN: "⭐",
            LegionStatus.DISBANDED: "⚫",
            LegionStatus.DESTROYED: "💀",  # 新增
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
            LegionStatus.DESTROYED: "💀",
        }.get(self.status, "❓")

        vet = "⭐" if self.is_veteran else ""
        assigned = f"→{self.war_id[:10]}..." if self.war_id else ""
        destroyed_info = f" (摧毁于{self._destroyed_turn})" if self.status == LegionStatus.DESTROYED else ""
        return f"{status_emoji} {self.name}{vet}[Str:{self.get_combat_strength()}]{assigned}{destroyed_info}"