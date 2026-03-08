# src/tests/test_entities/test_sea_zone.py
from src.core.entities.sea_zone import SeaZone


class TestSeaZone:
    def test_sea_zone_creation(self):
        zone = SeaZone(zone_id=1, name="Tyrrhenian Sea", adjacent_provinces=[1, 2])
        assert zone.zone_id == 1
        assert zone.name == "Tyrrhenian Sea"
        assert zone.adjacent_provinces == [1, 2]
        assert zone.controlled_by == "neutral"
        assert zone.garrison_fleet_ids == []
        assert zone._enemy_fleet_present is False  # 私有，但测试可访问

    def test_add_remove_fleet(self):
        zone = SeaZone(zone_id=2, name="Adriatic", adjacent_provinces=[3])
        zone.add_fleet(101)
        zone.add_fleet(102)
        assert zone.garrison_fleet_ids == [101, 102]
        zone.remove_fleet(101)
        assert zone.garrison_fleet_ids == [102]
        zone.remove_fleet(999)  # 不存在的 ID 应忽略
        assert zone.garrison_fleet_ids == [102]

    def test_set_control(self):
        zone = SeaZone(zone_id=3, name="Ionian", adjacent_provinces=[4])
        zone.set_control("rome")
        assert zone.controlled_by == "rome"

    def test_to_dict_and_from_dict(self):
        zone = SeaZone(zone_id=4, name="Aegean", adjacent_provinces=[5, 6])
        zone.add_fleet(201)
        zone.set_control("enemy")
        zone._enemy_fleet_present = True

        d = zone.to_dict()
        reconstructed = SeaZone.from_dict(d)

        assert reconstructed.zone_id == zone.zone_id
        assert reconstructed.name == zone.name
        assert reconstructed.adjacent_provinces == zone.adjacent_provinces
        assert reconstructed.controlled_by == zone.controlled_by
        assert reconstructed.garrison_fleet_ids == zone.garrison_fleet_ids
        assert reconstructed._enemy_fleet_present == zone._enemy_fleet_present