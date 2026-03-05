# src/core/entities/war.py

from typing import List, Optional, Dict, Any
from enum import Enum

class WarStatus(Enum):
    INACTIVE = "inactive"
    THREAT = "threat"
    ACTIVE = "active"
    TRUCE = "truce"
    RESOLVED = "resolved"
    DEFEATED = "defeated"

class WarType(Enum):
    BARBARIAN = "barbarian"
    FOREIGN = "foreign"
    PROVINCIAL = "provincial"
    CIVIL = "civil"

class War:
    """战争实体"""

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        war_type: WarType = WarType.FOREIGN,
        start_year: int = 0,
        threat_level: int = 0,
        auto_escalate: bool = True,
        escalate_rate: int = 1,
        strength: int = 5,
        naval_support_required: bool = False,
        naval_strength: int = 0,
        land_battle: bool = True,
        disaster_numbers: List[int] = None,
        standoff_numbers: List[int] = None,
        rewards: Dict[str, int] = None,
        penalties: Dict[str, int] = None,
        is_imminent: bool = False,
        matched_war_id: Optional[str] = None,
        # ---------- MVP 0.7-2 新增 ----------
        unlocked_provinces: List[int] = None,
    ):
        self._id = id
        self._name = name
        self._description = description
        self._war_type = war_type
        self._start_year = start_year
        self._threat_level = threat_level
        self._auto_escalate = auto_escalate
        self._escalate_rate = escalate_rate
        self._strength = strength
        self._naval_support_required = naval_support_required
        self._naval_strength = naval_strength
        self._land_battle = land_battle
        self._disaster_numbers = disaster_numbers or [2, 3, 4]
        self._standoff_numbers = standoff_numbers or [5, 6, 7, 8, 9]
        self._rewards = rewards or {}
        self._penalties = penalties or {}
        self._is_imminent = is_imminent
        self._matched_war_id = matched_war_id

        # 运行时字段
        self._status = WarStatus.INACTIVE
        self._commander_id: Optional[int] = None
        self._legions_assigned: int = 0
        self._fleets_assigned: int = 0
        self._activation_turn: Optional[int] = None
        self._duration: int = 0
        self._commander_status: str = "active"
        self._soldier_share: int = 0
        self._triumph_commander_id: Optional[int] = None
        self._triumph_approved: bool = False
        self._original_commander_id: Optional[int] = None
        self._commander_assigned_turn: Optional[int] = None
        self._peace_treaty: Optional[Dict] = None
        self._indemnity_due: int = 0
        self._truce_end_turn: Optional[int] = None
        self._legion_numbers: List[int] = []

        # ---------- MVP 0.7-2 新增 ----------
        self._unlocked_provinces = unlocked_provinces or []

    # ---------- 属性访问器 ----------
    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def war_type(self) -> WarType:
        return self._war_type

    @property
    def start_year(self) -> int:
        return self._start_year

    @property
    def threat_level(self) -> int:
        return self._threat_level

    @threat_level.setter
    def threat_level(self, value: int):
        self._threat_level = value

    @property
    def auto_escalate(self) -> bool:
        return self._auto_escalate

    @property
    def escalate_rate(self) -> int:
        return self._escalate_rate

    @property
    def strength(self) -> int:
        return self._strength

    @property
    def naval_support_required(self) -> bool:
        return self._naval_support_required

    @property
    def naval_strength(self) -> int:
        return self._naval_strength

    @property
    def land_battle(self) -> bool:
        return self._land_battle

    @property
    def disaster_numbers(self) -> List[int]:
        return self._disaster_numbers

    @property
    def standoff_numbers(self) -> List[int]:
        return self._standoff_numbers

    @property
    def rewards(self) -> Dict[str, int]:
        return self._rewards.copy()

    @property
    def penalties(self) -> Dict[str, int]:
        return self._penalties.copy()

    @property
    def is_imminent(self) -> bool:
        return self._is_imminent

    @property
    def matched_war_id(self) -> Optional[str]:
        return self._matched_war_id

    @property
    def status(self) -> WarStatus:
        return self._status

    @status.setter
    def status(self, value: WarStatus):
        self._status = value

    @property
    def commander_id(self) -> Optional[int]:
        return self._commander_id

    @commander_id.setter
    def commander_id(self, value: Optional[int]):
        self._commander_id = value

    @property
    def legions_assigned(self) -> int:
        return self._legions_assigned

    @legions_assigned.setter
    def legions_assigned(self, value: int):
        self._legions_assigned = value

    @property
    def fleets_assigned(self) -> int:
        return self._fleets_assigned

    @fleets_assigned.setter
    def fleets_assigned(self, value: int):
        self._fleets_assigned = value

    @property
    def activation_turn(self) -> Optional[int]:
        return self._activation_turn

    @activation_turn.setter
    def activation_turn(self, value: Optional[int]):
        self._activation_turn = value

    @property
    def duration(self) -> int:
        return self._duration

    @duration.setter
    def duration(self, value: int):
        self._duration = value

    @property
    def commander_status(self) -> str:
        return self._commander_status

    @property
    def soldier_share(self) -> int:
        return self._soldier_share

    @property
    def triumph_commander_id(self) -> Optional[int]:
        return self._triumph_commander_id

    @property
    def triumph_approved(self) -> bool:
        return self._triumph_approved

    @property
    def original_commander_id(self) -> Optional[int]:
        return self._original_commander_id

    @property
    def commander_assigned_turn(self) -> Optional[int]:
        return self._commander_assigned_turn

    @property
    def peace_treaty(self) -> Optional[Dict]:
        return self._peace_treaty

    @property
    def indemnity_due(self) -> int:
        return self._indemnity_due

    @property
    def truce_end_turn(self) -> Optional[int]:
        return self._truce_end_turn

    @property
    def legion_numbers(self) -> List[int]:
        return self._legion_numbers.copy()

    # ---------- MVP 0.7-2 新增属性 ----------
    @property
    def unlocked_provinces(self) -> List[int]:
        """返回战争胜利后解锁的行省ID列表（只读副本）。"""
        return self._unlocked_provinces.copy()

    # ---------- 公共方法 ----------
    def get_total_strength(self) -> int:
        """获取敌国总战力（含海军）。"""
        total = self._strength
        if self._naval_support_required:
            total += self._naval_strength
        return total

    def is_disaster_roll(self, dice: int) -> bool:
        return dice in self._disaster_numbers

    def is_standoff_roll(self, dice: int) -> bool:
        return dice in self._standoff_numbers

    def calculate_rewards(self) -> Dict[str, int]:
        return self._rewards.copy()

    def apply_penalties(self, state) -> List[str]:
        # 简化实现，实际应引用 GameState
        return []

    def set_soldier_share(self, amount: int):
        self._soldier_share = amount

    def set_triumph_commander(self, commander_id: int):
        self._triumph_commander_id = commander_id

    def set_triumph_approved(self, approved: bool):
        self._triumph_approved = approved

    def set_original_commander(self, commander_id: int, assigned_turn: int):
        self._original_commander_id = commander_id
        self._commander_assigned_turn = assigned_turn

    def set_peace_treaty(self, treaty: Dict):
        """设置和约，若未指定 status 则默认为 'pending'"""
        if 'status' not in treaty:
            treaty['status'] = 'pending'
        self._peace_treaty = treaty

    def set_peace_treaty_status(self, status: str):
        if self._peace_treaty:
            self._peace_treaty["status"] = status

    def set_indemnity_due(self, amount: int):
        self._indemnity_due = amount

    def set_truce_end_turn(self, turn: int):
        self._truce_end_turn = turn

    def clear_peace_treaty(self):
        self._peace_treaty = None

    def add_legion_number(self, legion_num: int):
        if legion_num not in self._legion_numbers:
            self._legion_numbers.append(legion_num)

    def clear_legion_numbers(self):
        self._legion_numbers.clear()

    def report_commander_casualty(self, status: str, turn: int):
        self._commander_status = status
        # 记录阵亡回合等（可扩展）

    def set_commander_assigned_turn(self, turn: int):
        """设置指挥官指派回合（用于人口阶段官职转换）"""
        self._commander_assigned_turn = turn

    def assign_commander(self, commander_id: int, legions: int = 0):
        """指派指挥官（供测试使用，实际指派通过 WarSystem）"""
        self._commander_id = commander_id
        self._legions_assigned = legions
        # 可选：记录指派回合
        # self._commander_assigned_turn = current_turn

    def is_truce_expired(self, current_turn: int) -> bool:
        """判断停战是否到期（当前回合 >= 停战结束回合）"""
        return self._truce_end_turn is not None and current_turn >= self._truce_end_turn

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        """将战争对象转换为字典，用于存档。"""
        return {
            "id": self._id,
            "name": self._name,
            "description": self._description,
            "war_type": self._war_type.value,
            "start_year": self._start_year,
            "threat_level": self._threat_level,
            "auto_escalate": self._auto_escalate,
            "escalate_rate": self._escalate_rate,
            "strength": self._strength,
            "naval_support_required": self._naval_support_required,
            "naval_strength": self._naval_strength,
            "land_battle": self._land_battle,
            "disaster_numbers": self._disaster_numbers.copy(),
            "standoff_numbers": self._standoff_numbers.copy(),
            "rewards": self._rewards.copy(),
            "penalties": self._penalties.copy(),
            "is_imminent": self._is_imminent,
            "matched_war_id": self._matched_war_id,
            "status": self._status.value,
            "commander_id": self._commander_id,
            "legions_assigned": self._legions_assigned,
            "fleets_assigned": self._fleets_assigned,
            "activation_turn": self._activation_turn,
            "duration": self._duration,
            "commander_status": self._commander_status,
            "soldier_share": self._soldier_share,
            "triumph_commander_id": self._triumph_commander_id,
            "triumph_approved": self._triumph_approved,
            "original_commander_id": self._original_commander_id,
            "commander_assigned_turn": self._commander_assigned_turn,
            "peace_treaty": self._peace_treaty.copy() if self._peace_treaty else None,
            "indemnity_due": self._indemnity_due,
            "truce_end_turn": self._truce_end_turn,
            "legion_numbers": self._legion_numbers.copy(),
            # MVP 0.7-2 新增
            "unlocked_provinces": self._unlocked_provinces.copy(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "War":
        """从字典重建战争对象。"""
        # 处理枚举
        war_type = WarType(data.get("war_type", "foreign"))
        status = WarStatus(data.get("status", "inactive"))

        war = War(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            war_type=war_type,
            start_year=data.get("start_year", 0),
            threat_level=data.get("threat_level", 0),
            auto_escalate=data.get("auto_escalate", True),
            escalate_rate=data.get("escalate_rate", 1),
            strength=data.get("strength", 5),
            naval_support_required=data.get("naval_support_required", False),
            naval_strength=data.get("naval_strength", 0),
            land_battle=data.get("land_battle", True),
            disaster_numbers=data.get("disaster_numbers"),
            standoff_numbers=data.get("standoff_numbers"),
            rewards=data.get("rewards"),
            penalties=data.get("penalties"),
            is_imminent=data.get("is_imminent", False),
            matched_war_id=data.get("matched_war_id"),
            unlocked_provinces=data.get("unlocked_provinces", []),
        )

        # 设置运行时字段
        war._status = status
        war._commander_id = data.get("commander_id")
        war._legions_assigned = data.get("legions_assigned", 0)
        war._fleets_assigned = data.get("fleets_assigned", 0)
        war._activation_turn = data.get("activation_turn")
        war._duration = data.get("duration", 0)
        war._commander_status = data.get("commander_status", "active")
        war._soldier_share = data.get("soldier_share", 0)
        war._triumph_commander_id = data.get("triumph_commander_id")
        war._triumph_approved = data.get("triumph_approved", False)
        war._original_commander_id = data.get("original_commander_id")
        war._commander_assigned_turn = data.get("commander_assigned_turn")
        war._peace_treaty = data.get("peace_treaty")
        war._indemnity_due = data.get("indemnity_due", 0)
        war._truce_end_turn = data.get("truce_end_turn")
        war._legion_numbers = data.get("legion_numbers", [])

        return war