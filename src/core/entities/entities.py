# src/core/entities/entities.py

from typing import List, Optional, Dict, Any, TYPE_CHECKING
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


    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "treasury": self.treasury,
            "is_player": self.is_player,
            "member_ids": self.member_ids.copy(),
            "_total_land": self._total_land,
            "_province_owned": self._province_owned.copy(),
            "_knight_contract_count": self._knight_contract_count,
        }

    @staticmethod
    def from_dict(data: dict) -> "Faction":
        faction = Faction(
            id=data["id"],
            name=data["name"],
            treasury=data.get("treasury", 0),
            is_player=data.get("is_player", False)
        )
        faction.member_ids = data.get("member_ids", []).copy()
        faction._total_land = data.get("_total_land", 0)
        faction._province_owned = data.get("_province_owned", []).copy()
        faction._knight_contract_count = data.get("_knight_contract_count", 0)
        return faction

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

# src/core/entities/entities.py

from typing import List, Optional, Dict, Any

class Province:

    # ⚠️注意：此类定义已废弃，请勿在此添加新功能！
    # 行省实体的正式定义位于 src/core/entities/province.py 中
    # 后续版本将逐渐将次模块的功能迁移统一到province.py中，所有新功能请基于 Province.py 开发。

    """
    行省实体 - MVP 0.5 新增，MVP 0.7-2 扩展征服状态及预留字段
    """


    def __init__(
        self,
        province_id: int,
        name: str,
        total_land: int,
        # ---------- MVP 0.5 原有字段 ----------
        land_public: Optional[int] = None,
        land_private: Optional[int] = None,
        tax_base: int = 0,
        grievance: int = 0,
        tax_contract_id: Optional[int] = None,
        project_contract_id: Optional[int] = None,
        has_project: bool = False,
        turns_since_last_land_distribution: int = 0,
        governor_id: Optional[int] = None,
        old_governor_id: Optional[int] = None,
        governor_since: int = 0,
        governor_type: str = "proconsul",
        governor_designate_id: Optional[int] = None,
        # ---------- MVP 0.7-2 新增字段 ----------
        conquered: bool = False,               # 征服状态
        country_id: int = 0,                    # 归属国家（0=罗马）
        development_level: int = 0,              # 开发度
        infrastructure: Optional[Dict[str, int]] = None,  # 基础设施等级
        resources: Optional[List[str]] = None,               # 资源列表
        culture: str = "latin",                  # 主流文化
        religion: str = "roman_polytheism",       # 主流宗教
        event_flags: Optional[Dict[str, Any]] = None,      # 事件标记
        governor_traits_effect: Optional[Dict[str, Any]] = None,  # 总督特质影响
        loyalty: int = 100,                       # 忠诚度
        garrison: Optional[Dict[str, Any]] = None,            # 驻军信息
    ):
        # 基础属性
        self._province_id = province_id
        self._name = name
        self._total_land = total_land

        # ---------- MVP 0.5 原有字段 ----------
        # 如果未指定公/私地，按 6:4 比例初始化（仅当 total_land>0）
        if land_public is None:
            self._land_public = int(total_land * 0.6)
        else:
            self._land_public = land_public
        if land_private is None:
            self._land_private = int(total_land * 0.4)
        else:
            self._land_private = land_private

        self._tax_base = tax_base
        self._grievance = grievance
        self._tax_contract_id = tax_contract_id
        self._project_contract_id = project_contract_id
        self._has_project = has_project
        self._turns_since_last_land_distribution = turns_since_last_land_distribution

        self._governor_id = governor_id
        self._old_governor_id = old_governor_id
        self._governor_since = governor_since
        self._governor_type = governor_type
        self._governor_designate_id = governor_designate_id

        # ---------- MVP 0.7-2 新增字段 ----------
        self._conquered = conquered
        self._country_id = country_id
        self._development_level = development_level
        self._infrastructure = infrastructure or {"roads": 0, "aqueducts": 0, "ports": 0, "walls": 0}
        self._resources = resources or []
        self._culture = culture
        self._religion = religion
        self._event_flags = event_flags or {}
        self._governor_traits_effect = governor_traits_effect or {}
        self._loyalty = loyalty
        self._garrison = garrison or {}

    # ---------- 属性访问器（只读）----------
    def set_event_flag(self, key: str, value: Any) -> None:
        """设置事件标记"""
        self._event_flags[key] = value

    def clear_event_flag(self, key: str) -> None:
        """清除事件标记"""
        self._event_flags.pop(key, None)

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

    @property
    def turns_since_last_land_distribution(self) -> int:
        return self._turns_since_last_land_distribution

    @property
    def governor_id(self) -> Optional[int]:
        return self._governor_id

    @property
    def old_governor_id(self) -> Optional[int]:
        return self._old_governor_id

    @property
    def governor_since(self) -> int:
        return self._governor_since

    @property
    def governor_type(self) -> str:
        return self._governor_type

    @property
    def governor_designate_id(self) -> Optional[int]:
        return self._governor_designate_id

    # ---------- MVP 0.7-2 新增属性 ----------
    @property
    def conquered(self) -> bool:
        return self._conquered

    @property
    def country_id(self) -> int:
        return self._country_id

    @property
    def development_level(self) -> int:
        return self._development_level

    @property
    def infrastructure(self) -> Dict[str, int]:
        return self._infrastructure.copy()

    @property
    def resources(self) -> List[str]:
        return self._resources.copy()

    @property
    def culture(self) -> str:
        return self._culture

    @property
    def religion(self) -> str:
        return self._religion

    @property
    def event_flags(self) -> Dict[str, Any]:
        return self._event_flags.copy()

    @property
    def governor_traits_effect(self) -> Dict[str, Any]:
        return self._governor_traits_effect.copy()

    @property
    def loyalty(self) -> int:
        return self._loyalty

    @property
    def garrison(self) -> Dict[str, Any]:
        return self._garrison.copy()

    # ---------- 公共方法 ----------
    def update_land_type(self, public_change: int, private_change: int) -> None:
        """调整公地/私地数量，保证非负。"""
        self._land_public = max(0, self._land_public + public_change)
        self._land_private = max(0, self._land_private + private_change)

    def bind_tax_contract(self, contract_id: int) -> None:
        if self._tax_contract_id is not None:
            raise ValueError(f"Province {self._province_id} already has a tax contract (ID: {self._tax_contract_id})")
        self._tax_contract_id = contract_id

    def bind_project_contract(self, contract_id: int) -> None:
        if self._project_contract_id is not None:
            raise ValueError(f"Province {self._province_id} already has a project contract (ID: {self._project_contract_id})")
        self._project_contract_id = contract_id
        self._has_project = True

    def unbind_tax_contract(self) -> None:
        self._tax_contract_id = None

    def unbind_project_contract(self) -> None:
        self._project_contract_id = None
        self._has_project = False

    def set_grievance(self, value: int) -> None:
        if not (0 <= value <= 3):
            raise ValueError(f"Grievance must be between 0 and 3, got {value}")
        self._grievance = value

    def set_governor(self, new_id: Optional[int], turn: int) -> None:
        self._old_governor_id = self._governor_id
        self._governor_id = new_id
        self._governor_since = turn

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        """将行省对象转换为字典，用于存档。"""
        return {
            "province_id": self._province_id,
            "name": self._name,
            "total_land": self._total_land,
            "land_public": self._land_public,
            "land_private": self._land_private,
            "tax_base": self._tax_base,
            "grievance": self._grievance,
            "tax_contract_id": self._tax_contract_id,
            "project_contract_id": self._project_contract_id,
            "has_project": self._has_project,
            "turns_since_last_land_distribution": self._turns_since_last_land_distribution,
            "governor_id": self._governor_id,
            "old_governor_id": self._old_governor_id,
            "governor_since": self._governor_since,
            "governor_type": self._governor_type,
            "governor_designate_id": self._governor_designate_id,
            # MVP 0.7-2 新增字段
            "conquered": self._conquered,
            "country_id": self._country_id,
            "development_level": self._development_level,
            "infrastructure": self._infrastructure.copy(),
            "resources": self._resources.copy(),
            "culture": self._culture,
            "religion": self._religion,
            "event_flags": self._event_flags.copy(),
            "governor_traits_effect": self._governor_traits_effect.copy(),
            "loyalty": self._loyalty,
            "garrison": self._garrison.copy(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Province":
        """从字典重建行省对象。"""
        # 使用 data 中的值，缺失的字段使用默认值
        return Province(
            province_id=data["province_id"],
            name=data["name"],
            total_land=data["total_land"],
            land_public=data.get("land_public"),
            land_private=data.get("land_private"),
            tax_base=data.get("tax_base", 0),
            grievance=data.get("grievance", 0),
            tax_contract_id=data.get("tax_contract_id"),
            project_contract_id=data.get("project_contract_id"),
            has_project=data.get("has_project", False),
            turns_since_last_land_distribution=data.get("turns_since_last_land_distribution", 0),
            governor_id=data.get("governor_id"),
            old_governor_id=data.get("old_governor_id"),
            governor_since=data.get("governor_since", 0),
            governor_type=data.get("governor_type", "proconsul"),
            governor_designate_id=data.get("governor_designate_id"),
            conquered=data.get("conquered", False),
            country_id=data.get("country_id", 0),
            development_level=data.get("development_level", 0),
            infrastructure=data.get("infrastructure"),
            resources=data.get("resources"),
            culture=data.get("culture", "latin"),
            religion=data.get("religion", "roman_polytheism"),
            event_flags=data.get("event_flags"),
            governor_traits_effect=data.get("governor_traits_effect"),
            loyalty=data.get("loyalty", 100),
            garrison=data.get("garrison"),
        )