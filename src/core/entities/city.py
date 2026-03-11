# src/core/entities/city.py
"""
城市实体 - 为未来城市化需求预留
"""
from typing import Dict, Optional, Any


class City:
    """城市实体，包含基础设施等属性"""

    def __init__(self, city_id: int, name: str, infrastructure: Optional[Dict[str, int]] = None):
        self._city_id = city_id
        self._name = name
        # 基础设施字典，包含预留的键名
        default_infra = {
            "roads": 0,
            "aqueducts": 0,
            "forum": 0,
            "temple": 0,
            "theater": 0,
            "baths": 0
        }
        if infrastructure:
            # 用传入的值更新默认字典（传入的键覆盖默认值，缺失的键保留默认值）
            default_infra.update(infrastructure)
        self._infrastructure = default_infra

    # ---------- 属性访问器 ----------
    @property
    def city_id(self) -> int:
        return self._city_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def infrastructure(self) -> Dict[str, int]:
        """返回基础设施字典的副本"""
        return self._infrastructure.copy()

    def set_infrastructure(self, key: str, value: int) -> None:
        """设置指定基础设施等级"""
        if key in self._infrastructure:
            self._infrastructure[key] = value
        else:
            raise ValueError(f"未知的基础设施类型: {key}")

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "city_id": self._city_id,
            "name": self._name,
            "infrastructure": self._infrastructure.copy()
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "City":
        return City(
            city_id=data["city_id"],
            name=data["name"],
            infrastructure=data.get("infrastructure")
        )

    def __repr__(self) -> str:
        return f"City(ID:{self._city_id}, {self._name})"