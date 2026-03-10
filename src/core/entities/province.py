# src/core/entities/province.py
from typing import List, Optional, Dict, Any


class Province:
    """行省实体"""

    def __init__(
        self,
        province_id: int,
        name: str,
        total_land: int,
        land_public: Optional[int] = None,
        land_private: Optional[int] = None,
        tax_base: int = 0,
        grievance: int = 0,
        conquered: bool = False,
        # 总督相关
        governor_id: Optional[int] = None,
        governor_type: str = "",  # "proconsul" / "propraetor"
        old_governor_id: Optional[int] = None,
        governor_designate_id: Optional[int] = None,
        # 合同相关
        tax_contract_id: Optional[int] = None,
        project_contract_id: Optional[int] = None,
        has_project: bool = False,
        # 新增字段（来自 provinces.json）
        adjacent_provinces: Optional[List[int]] = None,
        country_id: int = 0,
        development_level: int = 0,
        infrastructure: Optional[Dict[str, int]] = None,
        resources: Optional[List[str]] = None,
        culture: str = "",
        religion: str = "",
        event_flags: Optional[Dict[str, Any]] = None,
        governor_traits_effect: Optional[Dict[str, Any]] = None,
        loyalty: int = 100,
        garrison: Optional[Dict[str, Any]] = None,
    ):
        self._province_id = province_id
        self._name = name
        self._total_land = total_land

        # 土地分配，若未指定则按 6:4 比例分配
        if land_public is None or land_private is None:
            self._land_public = int(total_land * 0.6)
            self._land_private = int(total_land * 0.4)
        else:
            self._land_public = land_public
            self._land_private = land_private

        self._tax_base = tax_base
        self._grievance = grievance
        self._conquered = conquered

        # 总督相关
        self._governor_id = governor_id
        self._governor_type = governor_type
        self._old_governor_id = old_governor_id
        self._governor_designate_id = governor_designate_id

        # 合同相关
        self._tax_contract_id = tax_contract_id
        self._project_contract_id = project_contract_id
        self._has_project = has_project

        # 新增字段
        self._adjacent_provinces = adjacent_provinces or []
        self._country_id = country_id
        self._development_level = development_level
        self._infrastructure = infrastructure or {}
        self._resources = resources or []
        self._culture = culture
        self._religion = religion
        self._event_flags = event_flags or {}
        self._governor_traits_effect = governor_traits_effect or {}
        self._loyalty = loyalty
        self._garrison = garrison or {}

        print(f"[DEBUG] Province {self._name} (ID:{self._province_id}) governor_type = {self._governor_type}")

    # ---------- 基础属性 ----------
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

    @tax_base.setter
    def tax_base(self, value: int):
        self._tax_base = value

    @property
    def grievance(self) -> int:
        return self._grievance

    @property
    def conquered(self) -> bool:
        return self._conquered

    @conquered.setter
    def conquered(self, value: bool):
        self._conquered = value

    # ---------- 总督相关 ----------
    @property
    def governor_id(self) -> Optional[int]:
        return self._governor_id

    @governor_id.setter
    def governor_id(self, value: Optional[int]):
        self._governor_id = value

    @property
    def governor_type(self) -> str:
        return self._governor_type

    @governor_type.setter
    def governor_type(self, value: str):
        self._governor_type = value

    @property
    def old_governor_id(self) -> Optional[int]:
        return self._old_governor_id

    @old_governor_id.setter
    def old_governor_id(self, value: Optional[int]):
        self._old_governor_id = value

    @property
    def governor_designate_id(self) -> Optional[int]:
        return self._governor_designate_id

    @governor_designate_id.setter
    def governor_designate_id(self, value: Optional[int]):
        self._governor_designate_id = value

    # ---------- 合同相关 ----------
    @property
    def tax_contract_id(self) -> Optional[int]:
        return self._tax_contract_id

    @property
    def project_contract_id(self) -> Optional[int]:
        return self._project_contract_id

    @property
    def has_project(self) -> bool:
        return self._has_project

    # ---------- 新增字段 ----------
    @property
    def adjacent_provinces(self) -> List[int]:
        return self._adjacent_provinces.copy()

    @property
    def country_id(self) -> int:
        return self._country_id

    @country_id.setter
    def country_id(self, value: int):
        self._country_id = value

    @property
    def development_level(self) -> int:
        return self._development_level

    @development_level.setter
    def development_level(self, value: int):
        self._development_level = value

    @property
    def infrastructure(self) -> Dict[str, int]:
        return self._infrastructure.copy()

    @property
    def resources(self) -> List[str]:
        return self._resources.copy()

    @property
    def culture(self) -> str:
        return self._culture

    @culture.setter
    def culture(self, value: str):
        self._culture = value

    @property
    def religion(self) -> str:
        return self._religion

    @religion.setter
    def religion(self, value: str):
        self._religion = value

    @property
    def event_flags(self) -> Dict[str, Any]:
        return self._event_flags.copy()

    @property
    def governor_traits_effect(self) -> Dict[str, Any]:
        return self._governor_traits_effect.copy()

    @property
    def loyalty(self) -> int:
        return self._loyalty

    @loyalty.setter
    def loyalty(self, value: int):
        self._loyalty = max(0, min(100, value))  # 限定 0-100

    @property
    def garrison(self) -> Dict[str, Any]:
        return self._garrison.copy()

    # ---------- 修改方法 ----------
    def update_land_type(self, public_change: int, private_change: int) -> None:
        """调整公地/私地数量，保证非负"""
        self._land_public = max(0, self._land_public + public_change)
        self._land_private = max(0, self._land_private + private_change)

    def set_grievance(self, value: int) -> None:
        """设置民怨值，范围 0-3"""
        if not (0 <= value <= 3):
            raise ValueError("Grievance must be between 0 and 3")
        self._grievance = value

    def bind_tax_contract(self, contract_id: int) -> None:
        """绑定包税权合同"""
        if self._tax_contract_id is not None:
            raise ValueError("Province already has a tax contract")
        self._tax_contract_id = contract_id

    def unbind_tax_contract(self) -> None:
        """解绑包税权合同"""
        self._tax_contract_id = None

    def bind_project_contract(self, contract_id: int) -> None:
        """绑定公共工程合同"""
        if self._project_contract_id is not None:
            raise ValueError("Province already has a project contract")
        self._project_contract_id = contract_id
        self._has_project = True

    def unbind_project_contract(self) -> None:
        """解绑公共工程合同"""
        self._project_contract_id = None
        self._has_project = False

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

    def set_event_flag(self, key: str, value: Any) -> None:
        """设置事件标记"""
        self._event_flags[key] = value

    def clear_event_flag(self, key: str) -> None:
        """清除事件标记"""
        self._event_flags.pop(key, None)

    def set_governor_trait_effect(self, key: str, value: Any) -> None:
        """设置总督特质效果"""
        self._governor_traits_effect[key] = value

    def set_garrison(self, key: str, value: Any) -> None:
        """设置驻军信息"""
        self._garrison[key] = value

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "province_id": self._province_id,
            "name": self._name,
            "total_land": self._total_land,
            "land_public": self._land_public,
            "land_private": self._land_private,
            "tax_base": self._tax_base,
            "grievance": self._grievance,
            "conquered": self._conquered,
            "governor_id": self._governor_id,
            "governor_type": self._governor_type,
            "old_governor_id": self._old_governor_id,
            "governor_designate_id": self._governor_designate_id,
            "tax_contract_id": self._tax_contract_id,
            "project_contract_id": self._project_contract_id,
            "has_project": self._has_project,
            "adjacent_provinces": self._adjacent_provinces.copy(),
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
        province = Province(
            province_id=data["province_id"],
            name=data["name"],
            total_land=data["total_land"],
            land_public=data.get("land_public"),
            land_private=data.get("land_private"),
            tax_base=data.get("tax_base", 0),
            grievance=data.get("grievance", 0),
            conquered=data.get("conquered", False),
            governor_id=data.get("governor_id"),
            governor_type=data.get("governor_type", ""),
            old_governor_id=data.get("old_governor_id"),
            governor_designate_id=data.get("governor_designate_id"),
            tax_contract_id=data.get("tax_contract_id"),
            project_contract_id=data.get("project_contract_id"),
            has_project=data.get("has_project", False),
            adjacent_provinces=data.get("adjacent_provinces", []),
            country_id=data.get("country_id", 0),
            development_level=data.get("development_level", 0),
            infrastructure=data.get("infrastructure", {}),
            resources=data.get("resources", []),
            culture=data.get("culture", ""),
            religion=data.get("religion", ""),
            event_flags=data.get("event_flags", {}),
            governor_traits_effect=data.get("governor_traits_effect", {}),
            loyalty=data.get("loyalty", 100),
            garrison=data.get("garrison", {}),
        )
        return province

    def __repr__(self) -> str:
        status = "🏛️" if self._conquered else "⛔"
        gov = f"总督:{self._governor_id}" if self._governor_id else ""
        return f"{status} {self._name}(ID:{self._province_id}) {gov} 民怨:{self._grievance}"