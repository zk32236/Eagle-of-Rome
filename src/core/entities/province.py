# src/core/entities/province.py
from typing import List, Optional, Dict, Any

class Province:
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
        # ---------- 城市系统扩展（原 province.py 保留）----------
        adjacent_provinces: Optional[List[int]] = None,
        city_ids: Optional[List[int]] = None,
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

        # ---------- 城市系统扩展 ----------
        self._adjacent_provinces = adjacent_provinces or []
        self._city_ids = city_ids or []

    # ---------- 属性访问器（只读）----------
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

    # ---------- 新增属性：城市系统扩展 ----------
    @property
    def adjacent_provinces(self) -> List[int]:
        return self._adjacent_provinces.copy()

    @property
    def city_ids(self) -> List[int]:
        return self._city_ids.copy()

    # ---------- 公共方法 ----------

    def recalc_total_land(self):
        """根据公地和私地重新计算总土地"""
        self._total_land = self._land_public + self._land_private

    def reset_turns_since_last_distribution(self):
        """重置自上次分地以来的回合数（用于意大利本土）"""
        self._turns_since_last_land_distribution = 0

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

    def set_governor_designate(self, new_governor_id: Optional[int], old_governor_id: Optional[int] = None) -> None:
        """设置候任总督，并记录本轮将被替换的旧总督。"""
        self._governor_designate_id = new_governor_id
        self._old_governor_id = old_governor_id

    def clear_governor_designate(self) -> None:
        """清空候任总督记录。"""
        self._governor_designate_id = None
        self._old_governor_id = None

    def complete_governor_transition(
        self,
        turn: int,
        promote_designate: bool = True
    ) -> tuple[Optional[int], Optional[int]]:
        """完成候任总督交接并清理本轮临时记录。"""
        old_governor_id = self._old_governor_id
        designate_id = self._governor_designate_id
        if designate_id is not None and promote_designate:
            self._governor_id = designate_id
            self._governor_since = turn
        self._governor_designate_id = None
        self._old_governor_id = None
        return old_governor_id, designate_id

    def set_event_flag(self, key: str, value: Any) -> None:
        """设置事件标记"""
        self._event_flags[key] = value

    def clear_event_flag(self, key: str) -> None:
        """清除事件标记"""
        self._event_flags.pop(key, None)

    # ---------- 城市系统扩展方法 ----------
    def add_city_id(self, city_id: int) -> None:
        """添加城市ID到行省"""
        if city_id not in self._city_ids:
            self._city_ids.append(city_id)

    def remove_city_id(self, city_id: int) -> None:
        """从行省移除城市ID"""
        if city_id in self._city_ids:
            self._city_ids.remove(city_id)

    def set_infrastructure(self, key: str, value: int) -> None:
        """设置基础设施等级"""
        self._infrastructure[key] = value

    def add_resource(self, resource: str) -> None:
        """添加资源"""
        if resource not in self._resources:
            self._resources.append(resource)

    def remove_resource(self, resource: str) -> None:
        """移除资源"""
        if resource in self._resources:
            self._resources.remove(resource)

    def set_governor_trait_effect(self, key: str, value: Any) -> None:
        """设置总督特质效果"""
        self._governor_traits_effect[key] = value

    def set_garrison(self, key: str, value: Any) -> None:
        """设置驻军信息"""
        self._garrison[key] = value

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
            # 城市系统扩展
            "adjacent_provinces": self._adjacent_provinces.copy(),
            "city_ids": self._city_ids.copy(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Province":
        """从字典重建行省对象。"""
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
            adjacent_provinces=data.get("adjacent_provinces"),
            city_ids=data.get("city_ids"),
        )

    def __repr__(self) -> str:
        status = "🏛️" if self._conquered else "⛔"
        gov = f"总督:{self._governor_id}" if self._governor_id else ""
        return f"{status} {self._name}(ID:{self._province_id}) {gov} 民怨:{self._grievance}"
