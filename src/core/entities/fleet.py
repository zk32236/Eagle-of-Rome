# src/core/entities/fleet.py
from enum import Enum
from typing import Optional, Dict, Any, List

class FleetStatus(Enum):
    AVAILABLE = "available"
    ON_MISSION = "on_mission"
    IN_COMBAT = "in_combat"
    DESTROYED = "destroyed"

class Fleet:
    """舰队实体（基础版本）"""

    def __init__(self, number: int, name: str = ""):
        self._number = number
        self._name = name or f"Fleet {number}"
        self._status = FleetStatus.AVAILABLE
        self._commander_id: Optional[int] = None
        self._experience: int = 0
        self._strength_base: int = 3      # 默认值，应从配置读取
        self._is_veteran: bool = False
        self._assigned_war_id: Optional[str] = None
        self._assigned_mission_type: Optional[str] = None
        self._location_zone_id: Optional[int] = None   # 所在海区（预留）
        self._destroyed_turn: int = 0

    # 属性访问器
    @property
    def number(self) -> int: return self._number
    @property
    def name(self) -> str: return self._name
    @property
    def status(self) -> FleetStatus: return self._status
    @property
    def commander_id(self) -> Optional[int]: return self._commander_id
    @property
    def experience(self) -> int: return self._experience
    @property
    def is_veteran(self) -> bool: return self._is_veteran
    @property
    def assigned_war_id(self) -> Optional[str]: return self._assigned_war_id
    @property
    def destroyed_turn(self) -> int: return self._destroyed_turn

    def get_combat_strength(self, state) -> int:
        """计算舰队战力（基础版本）"""
        strength = self._strength_base + self._experience
        if self._commander_id:
            commander = state.get_member(self._commander_id)
            if commander:
                strength += commander.martial   # 使用 martial 作为海战加成
        return strength

    def get_maintenance_cost(self, state) -> int:
        """获取维护费（从配置读取）"""
        return state.get_economic_rule("fleet_maintenance_cost", 5)

    def assign_to_war(self, war_id: str, mission_type: str, commander_id: Optional[int] = None):
        self._assigned_war_id = war_id
        self._assigned_mission_type = mission_type
        self._commander_id = commander_id
        self._status = FleetStatus.ON_MISSION

    def recall(self):
        self._assigned_war_id = None
        self._assigned_mission_type = None
        self._commander_id = None
        self._status = FleetStatus.AVAILABLE

    def mark_destroyed(self, current_turn: int):
        self._status = FleetStatus.DESTROYED
        self._destroyed_turn = current_turn
        self._is_veteran = False
        self._experience = 0
        self._commander_id = None
        self._assigned_war_id = None

    def recover(self):
        """恢复被摧毁的舰队（预留）"""
        if self._status == FleetStatus.DESTROYED:
            self._status = FleetStatus.AVAILABLE
            self._destroyed_turn = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_number": self._number,
            "_name": self._name,
            "_status": self._status.value,
            "_commander_id": self._commander_id,
            "_experience": self._experience,
            "_strength_base": self._strength_base,
            "_is_veteran": self._is_veteran,
            "_assigned_war_id": self._assigned_war_id,
            "_assigned_mission_type": self._assigned_mission_type,
            "_location_zone_id": self._location_zone_id,
            "_destroyed_turn": self._destroyed_turn,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Fleet":
        fleet = Fleet(data["_number"], data.get("_name", ""))
        fleet._status = FleetStatus(data["_status"])
        fleet._commander_id = data.get("_commander_id")
        fleet._experience = data.get("_experience", 0)
        fleet._strength_base = data.get("_strength_base", 3)
        fleet._is_veteran = data.get("_is_veteran", False)
        fleet._assigned_war_id = data.get("_assigned_war_id")
        fleet._assigned_mission_type = data.get("_assigned_mission_type")
        fleet._location_zone_id = data.get("_location_zone_id")
        fleet._destroyed_turn = data.get("_destroyed_turn", 0)
        return fleet