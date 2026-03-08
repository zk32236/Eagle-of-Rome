# src/core/entities/sea_zone.py
from typing import List, Optional, Dict, Any

class SeaZone:
    """海区实体（预留版本）"""

    def __init__(self, zone_id: int, name: str, adjacent_provinces: List[int]):
        self._zone_id = zone_id
        self._name = name
        self._adjacent_provinces = adjacent_provinces
        self._controlled_by: str = "neutral"      # "rome" / "enemy"
        self._garrison_fleet_ids: List[int] = []
        self._enemy_fleet_present: bool = False

    @property
    def zone_id(self) -> int: return self._zone_id
    @property
    def name(self) -> str: return self._name
    @property
    def adjacent_provinces(self) -> List[int]: return self._adjacent_provinces.copy()
    @property
    def controlled_by(self) -> str: return self._controlled_by
    @property
    def garrison_fleet_ids(self) -> List[int]: return self._garrison_fleet_ids.copy()

    def add_fleet(self, fleet_id: int):
        if fleet_id not in self._garrison_fleet_ids:
            self._garrison_fleet_ids.append(fleet_id)

    def remove_fleet(self, fleet_id: int):
        if fleet_id in self._garrison_fleet_ids:
            self._garrison_fleet_ids.remove(fleet_id)

    def set_control(self, controller: str):
        self._controlled_by = controller

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_zone_id": self._zone_id,
            "_name": self._name,
            "_adjacent_provinces": self._adjacent_provinces.copy(),
            "_controlled_by": self._controlled_by,
            "_garrison_fleet_ids": self._garrison_fleet_ids.copy(),
            "_enemy_fleet_present": self._enemy_fleet_present,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SeaZone":
        zone = SeaZone(data["_zone_id"], data["_name"], data["_adjacent_provinces"])
        zone._controlled_by = data.get("_controlled_by", "neutral")
        zone._garrison_fleet_ids = data.get("_garrison_fleet_ids", []).copy()
        zone._enemy_fleet_present = data.get("_enemy_fleet_present", False)
        return zone