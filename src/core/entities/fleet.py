# src/core/entities/fleet.py
from enum import Enum
from typing import Optional, Dict, Any, List


class FleetStatus(Enum):
    BUILDING = "building"       # 建造中（合同已签，未完工）
    AVAILABLE = "available"      # 可用
    ON_MISSION = "on_mission"    # 执行任务中
    IN_COMBAT = "in_combat"      # 战斗中
    DESTROYED = "destroyed"      # 被摧毁（仅战斗伤亡，G1-13）
    DISBANDED = "disbanded"      # 行政退役（正常退役/国库解散，G1-13 / J 件 §1）


class Fleet:
    """舰队实体"""

    def __init__(
        self,
        number: int,
        name: str = "",
        fleet_type: str = "trireme",   # 舰队类型，如 trireme, quinquereme
    ):
        self._number = number
        self._name = name or f"Fleet {number}"
        self._fleet_type = fleet_type
        self._status = FleetStatus.BUILDING  # 默认为建造中
        self._commander_id: Optional[int] = None
        self._experience: int = 0
        self._strength_base: int = 3          # 从配置读取，初始化后根据类型设置
        self._is_veteran: bool = False
        self._assigned_war_id: Optional[str] = None
        self._assigned_mission_type: Optional[str] = None
        self._location_zone_id: Optional[int] = None
        self._destroyed_turn: int = 0
        # 建造相关
        self._build_start_turn: Optional[int] = None
        self._build_end_turn: Optional[int] = None
        self._contract_id: Optional[int] = None   # 关联的建造合同ID
        self._target_war_id: Optional[str] = None  # 关联的战争ID（用于建造后自动指派）

    @property
    def target_war_id(self) -> Optional[str]:
        return self._target_war_id

    # 属性访问器
    @property
    def number(self) -> int:
        return self._number

    @property
    def name(self) -> str:
        return self._name

    @property
    def fleet_type(self) -> str:
        return self._fleet_type

    @property
    def status(self) -> FleetStatus:
        return self._status

    @property
    def commander_id(self) -> Optional[int]:
        return self._commander_id

    @commander_id.setter
    def commander_id(self, value: Optional[int]):
        """Fleet 指挥官绑定 setter（G2-WP-G-H §5 / Q 件 E：GA rebind 原语消费；GC 派生 martial）。

        仅维护 _commander_id 收敛 War Commander（G1-20/R-14）；不触碰 _assigned_war_id
        （单战归属持久归 GC）。
        """
        self._commander_id = value

    @property
    def experience(self) -> int:
        return self._experience

    @property
    def is_veteran(self) -> bool:
        return self._is_veteran

    @property
    def assigned_war_id(self) -> Optional[str]:
        return self._assigned_war_id

    @property
    def destroyed_turn(self) -> int:
        return self._destroyed_turn

    @property
    def build_start_turn(self) -> Optional[int]:
        return self._build_start_turn

    @property
    def build_end_turn(self) -> Optional[int]:
        return self._build_end_turn

    @property
    def contract_id(self) -> Optional[int]:
        return self._contract_id

    @property
    def is_building(self) -> bool:
        return self._status == FleetStatus.BUILDING

    # 从配置加载基础战力
    def set_strength_from_config(self, config: dict):
        self._strength_base = config.get("strength_base", 3)

    def get_combat_strength(self, state) -> int:
        """计算舰队战力（基础 + 经验 + 指挥官 martial）。

        G1-20（H 件 §4）：martial 权威 = War Commander（war.commander_id）——
        Fleet._commander_id 为绑定镜像/兼容；无指派（AVAILABLE staging）或
        war.commander_id 为空时回退舰队私有绑定。
        """
        strength = self._strength_base + self._experience
        commander_id = self._commander_id
        ws = getattr(state, "get_war_system", lambda: None)()
        if ws and self._assigned_war_id:
            war = ws.get_war_by_id(self._assigned_war_id)
            if war is not None and war.commander_id is not None:
                commander_id = war.commander_id  # 权威 = War Commander（G1-20）
        if commander_id:
            commander = state.get_member(commander_id)
            if commander:
                strength += commander.martial  # 使用 martial 作为海战加成
        return strength

    def get_maintenance_cost(self, state) -> int:
        """获取维护费（从配置读取）"""
        fleet_config = state.config.get("economic_rules.fleet_types", {}).get(self._fleet_type, {})
        return fleet_config.get("maintenance_cost", 5)

    def assign_to_war(self, war_id: str, mission_type: str, commander_id: Optional[int] = None):
        if self._status != FleetStatus.AVAILABLE:
            return False
        self._assigned_war_id = war_id
        self._assigned_mission_type = mission_type
        self._commander_id = commander_id
        self._status = FleetStatus.ON_MISSION
        return True

    def recall(self):
        self._assigned_war_id = None
        self._assigned_mission_type = None
        self._commander_id = None
        self._status = FleetStatus.AVAILABLE

    def start_building(self, start_turn: int, contract_id: int, build_time: int):
        """开始建造"""
        self._status = FleetStatus.BUILDING
        self._build_start_turn = start_turn
        self._build_end_turn = start_turn + build_time
        self._contract_id = contract_id

    def complete_building(self):
        """建造完成"""
        self._status = FleetStatus.AVAILABLE
        self._build_start_turn = None
        self._build_end_turn = None
        self._contract_id = None

    def mark_destroyed(self, current_turn: int):
        self._status = FleetStatus.DESTROYED
        self._destroyed_turn = current_turn
        self._is_veteran = False
        self._experience = 0
        self._commander_id = None
        self._assigned_war_id = None

    def disband(self):
        """行政退役（G1-13）：正常退役专用，非战斗伤亡（R-11）。

        与 legion.disband 语义对齐：不清 is_veteran/experience（行政退役非伤亡）；
        保留 _target_war_id（单战归属 provenance 持久，G1-12）；DISBANDED 为终端态不可复用。
        """
        self._status = FleetStatus.DISBANDED
        self._commander_id = None
        self._assigned_war_id = None
        self._assigned_mission_type = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_number": self._number,
            "_name": self._name,
            "_fleet_type": self._fleet_type,
            "_status": self._status.value,
            "_commander_id": self._commander_id,
            "_experience": self._experience,
            "_strength_base": self._strength_base,
            "_is_veteran": self._is_veteran,
            "_assigned_war_id": self._assigned_war_id,
            "_assigned_mission_type": self._assigned_mission_type,
            "_location_zone_id": self._location_zone_id,
            "_destroyed_turn": self._destroyed_turn,
            "_build_start_turn": self._build_start_turn,
            "_build_end_turn": self._build_end_turn,
            "_contract_id": self._contract_id,
            "_target_war_id": self._target_war_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Fleet":
        fleet = Fleet(data["_number"], data.get("_name", ""), data.get("_fleet_type", "trireme"))
        fleet._status = FleetStatus(data["_status"])
        fleet._commander_id = data.get("_commander_id")
        fleet._experience = data.get("_experience", 0)
        fleet._strength_base = data.get("_strength_base", 3)
        fleet._is_veteran = data.get("_is_veteran", False)
        fleet._assigned_war_id = data.get("_assigned_war_id")
        fleet._assigned_mission_type = data.get("_assigned_mission_type")
        fleet._location_zone_id = data.get("_location_zone_id")
        fleet._destroyed_turn = data.get("_destroyed_turn", 0)
        fleet._build_start_turn = data.get("_build_start_turn")
        fleet._build_end_turn = data.get("_build_end_turn")
        fleet._contract_id = data.get("_contract_id")
        # O 件 §3：单战归属 provenance 持久（G1-12）；旧存档缺键 → None
        fleet._target_war_id = data.get("_target_war_id")
        return fleet