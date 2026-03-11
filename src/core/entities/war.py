# src/core/entities/war.py

from typing import List, Optional, Dict, Any,Tuple
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
            # ---------- MVP 0.7-4 新增 ----------
            naval_required: bool = False,
            enemy_naval_current: int = 0,
            enemy_naval_max: int = 0,
            enemy_land_current: int = 0,
            enemy_land_max: int = 0,
            enemy_budget_initial: int = 0,
            enemy_recovery_per_turn: int = 0,
            enemy_maintenance_cost_per_unit: int = 0,
            sea_zone_id: Optional[int] = None,
            mission_type: str = "JOINT_INVASION",
            rebellion_province_id: Optional[int] = None,
            # ---------- MVP 0.7 战斗统计预留 ----------
            battles_fought: int = 0,
            battles_won: int = 0,
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

        # ---------- MVP 0.7-4 新增字段 ----------
        self._naval_required = naval_required
        self._enemy_naval_current = enemy_naval_current
        self._enemy_naval_max = enemy_naval_max
        self._enemy_land_current = enemy_land_current
        self._enemy_land_max = enemy_land_max
        self._enemy_budget_initial = enemy_budget_initial
        self._enemy_budget_remaining = enemy_budget_initial  # 初始值与预算相同
        self._enemy_recovery_per_turn = enemy_recovery_per_turn
        self._enemy_maintenance_cost_per_unit = enemy_maintenance_cost_per_unit
        self._sea_zone_id = sea_zone_id
        self._mission_type = mission_type
        self._rebellion_province_id = rebellion_province_id

        # 以下字段没有参数传入，直接初始化为默认值
        self._assigned_fleet_ids: List[int] = []  # 我方指派舰队编号
        self._unanswered_turns: int = 0  # 连续未应战回合数
        self._indemnity_schedule: List[Tuple[int, int]] = []  # 战争赔款分期
        self._sea_control_ratio: float = 1.0  # 当前制海权比例
        self._battles_fought = battles_fought
        self._battles_won = battles_won



    # ---------- 属性访问器 ----------

    @property
    def battles_fought(self) -> int:
        return self._battles_fought

    @property
    def battles_won(self) -> int:
        return self._battles_won

    # ---------- MVP 0.7-4 新增字段开始----------
    @property
    def naval_required(self) -> bool: return self._naval_required
    @property
    def enemy_naval_current(self) -> int: return self._enemy_naval_current
    @property
    def assigned_fleet_ids(self) -> List[int]: return self._assigned_fleet_ids.copy()
    @property
    def sea_zone_id(self) -> Optional[int]: return self._sea_zone_id
    @property
    def unanswered_turns(self) -> int: return self._unanswered_turns
    @property
    def indemnity_schedule(self) -> List[Tuple[int, int]]: return self._indemnity_schedule.copy()
    @property
    def sea_control_ratio(self) -> float: return self._sea_control_ratio
    @property
    def rebellion_province_id(self) -> Optional[int]: return self._rebellion_province_id

    # ---------- MVP 0.7-4 新增字段结束 ----------

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

    # ---------- MVP 0.7-4 新增方法开始----------

    def assign_fleet(self, fleet_id: int) -> None:
        if fleet_id not in self._assigned_fleet_ids:
            self._assigned_fleet_ids.append(fleet_id)

    def remove_fleet(self, fleet_id: int) -> None:
        if fleet_id in self._assigned_fleet_ids:
            self._assigned_fleet_ids.remove(fleet_id)

    def apply_naval_losses(self, result: str, fleet_ids: List[int], enemy_naval_loss: int) -> None:
        """应用海战损失（当前版本占位）"""
        # 具体实现留空，仅保留接口
        pass

    def apply_land_losses(self, result: str, legion_numbers: List[int], enemy_land_loss: int) -> None:
        """应用陆战损失（当前版本占位）"""
        pass

    def increment_unanswered_turns(self) -> None:
        self._unanswered_turns += 1

    def reset_unanswered_turns(self) -> None:
        self._unanswered_turns = 0

    def process_enemy_reinforcements(self, state) -> None:
        """处理敌军增援（预留，当前版本留空）"""
        pass

    def set_indemnity_schedule(self, schedule: List[Tuple[int, int]]) -> None:
        self._indemnity_schedule = schedule

    # ---------- MVP 0.7-4 新增方法结束----------


    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        """将战争对象转换为字典，用于存档。"""
        data = {
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

            # MVP 0.7-4 战争系统新增
            "_naval_required": self._naval_required,
            "_enemy_naval_current": self._enemy_naval_current,
            "_assigned_fleet_ids": self._assigned_fleet_ids.copy(),
            "_sea_zone_id": self._sea_zone_id,
            "_enemy_naval_max": self._enemy_naval_max,
            "_enemy_land_current": self._enemy_land_current,
            "_enemy_land_max": self._enemy_land_max,
            "_enemy_budget_initial": self._enemy_budget_initial,
            "_enemy_budget_remaining": self._enemy_budget_remaining,
            "_enemy_recovery_per_turn": self._enemy_recovery_per_turn,
            "_enemy_maintenance_cost_per_unit": self._enemy_maintenance_cost_per_unit,
            "_mission_type": self._mission_type,
            "_unanswered_turns": self._unanswered_turns,
            "_indemnity_schedule": self._indemnity_schedule.copy(),
            "_sea_control_ratio": self._sea_control_ratio,
            "_rebellion_province_id": self._rebellion_province_id,
            "_battles_fought": self._battles_fought,
            "_battles_won": self._battles_won,
        }
        return data

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

        # MVP 0.7-4 设置新增字段
        war._naval_required = data.get("_naval_required", False)
        war._enemy_naval_current = data.get("_enemy_naval_current", 0)
        war._assigned_fleet_ids = data.get("_assigned_fleet_ids", []).copy()
        war._sea_zone_id = data.get("_sea_zone_id")
        war._enemy_naval_max = data.get("_enemy_naval_max", 0)
        war._enemy_land_current = data.get("_enemy_land_current", 0)
        war._enemy_land_max = data.get("_enemy_land_max", 0)
        war._enemy_budget_initial = data.get("_enemy_budget_initial", 0)
        war._enemy_budget_remaining = data.get("_enemy_budget_remaining", 0)
        war._enemy_recovery_per_turn = data.get("_enemy_recovery_per_turn", 0)
        war._enemy_maintenance_cost_per_unit = data.get("_enemy_maintenance_cost_per_unit", 0)
        war._mission_type = data.get("_mission_type", "JOINT_INVASION")
        war._unanswered_turns = data.get("_unanswered_turns", 0)
        war._indemnity_schedule = data.get("_indemnity_schedule", [])
        war._sea_control_ratio = data.get("_sea_control_ratio", 1.0)
        war._rebellion_province_id = data.get("_rebellion_province_id")

        war._battles_fought = data.get("_battles_fought", 0)
        war._battles_won = data.get("_battles_won", 0)

        return war