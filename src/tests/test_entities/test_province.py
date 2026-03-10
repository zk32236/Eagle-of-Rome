import pytest
from src.core.entities.entities import Province

class TestProvince:
    """测试 Province 实体（包括 MVP 0.7-2 新增字段）"""

    def test_province_governor_type_from_json(self):
        """验证从 JSON 加载的行省包含正确的 governor_type"""
        # 模拟从 provinces.json 加载的数据
        data = {
            "province_id": 1,
            "name": "西西里",
            "total_land": 10000,
            "governor_type": "proconsul",
            "conquered": True,
        }
        province = Province.from_dict(data)
        assert province.governor_type == "proconsul"

        data2 = {
            "province_id": 2,
            "name": "撒丁-科西嘉",
            "total_land": 16000,
            "governor_type": "propraetor",
            "conquered": True,
        }
        province2 = Province.from_dict(data2)
        assert province2.governor_type == "propraetor"

    def test_province_creation_with_defaults(self):
        """使用最小参数创建，检查默认值是否正确。"""
        p = Province(province_id=1, name="Test", total_land=1000)
        assert p.province_id == 1
        assert p.name == "Test"
        assert p.total_land == 1000
        assert p.land_public == 600   # 6:4 比例
        assert p.land_private == 400
        assert p.conquered is False
        assert p.country_id == 0
        assert p.development_level == 0
        assert p.infrastructure == {"roads": 0, "aqueducts": 0, "ports": 0, "walls": 0}
        assert p.resources == []
        assert p.culture == "latin"
        assert p.religion == "roman_polytheism"
        assert p.event_flags == {}
        assert p.governor_traits_effect == {}
        assert p.loyalty == 100
        assert p.garrison == {}

    def test_province_creation_with_all_fields(self):
        """使用完整参数创建，验证字段赋值。"""
        p = Province(
            province_id=2,
            name="Sicily",
            total_land=800,
            land_public=500,
            land_private=300,
            conquered=True,
            country_id=0,
            development_level=20,
            infrastructure={"roads": 1, "aqueducts": 0, "ports": 1, "walls": 0},
            resources=["grain", "silver"],
            culture="greek",
            religion="greek_polytheism",
            event_flags={"plague": 2},
            governor_traits_effect={"corruption": 0.1},
            loyalty=80,
            garrison={"legion": 123}
        )
        assert p.province_id == 2
        assert p.name == "Sicily"
        assert p.total_land == 800
        assert p.land_public == 500
        assert p.land_private == 300
        assert p.conquered is True
        assert p.country_id == 0
        assert p.development_level == 20
        assert p.infrastructure == {"roads": 1, "aqueducts": 0, "ports": 1, "walls": 0}
        assert p.resources == ["grain", "silver"]
        assert p.culture == "greek"
        assert p.religion == "greek_polytheism"
        assert p.event_flags == {"plague": 2}
        assert p.governor_traits_effect == {"corruption": 0.1}
        assert p.loyalty == 80
        assert p.garrison == {"legion": 123}

    def test_province_to_dict_and_from_dict(self):
        """测试序列化与反序列化的一致性。"""
        original = Province(
            province_id=3,
            name="Corsica",
            total_land=600,
            conquered=False,
            development_level=10,
            resources=["wood"],
            loyalty=90
        )
        data = original.to_dict()
        reconstructed = Province.from_dict(data)

        # 比较每个字段
        assert reconstructed.province_id == original.province_id
        assert reconstructed.name == original.name
        assert reconstructed.total_land == original.total_land
        assert reconstructed.land_public == original.land_public
        assert reconstructed.land_private == original.land_private
        assert reconstructed.conquered == original.conquered
        assert reconstructed.development_level == original.development_level
        assert reconstructed.resources == original.resources
        assert reconstructed.loyalty == original.loyalty
        # 基础设施应恢复为默认字典
        assert reconstructed.infrastructure == {"roads": 0, "aqueducts": 0, "ports": 0, "walls": 0}
        # 其他默认字段也应正确
        assert reconstructed.country_id == 0
        assert reconstructed.culture == "latin"
        assert reconstructed.religion == "roman_polytheism"

    def test_province_grievance_setter(self):
        p = Province(1, "Test", 1000)
        p.set_grievance(2)
        assert p.grievance == 2
        with pytest.raises(ValueError):
            p.set_grievance(5)

    def test_province_conquered_property(self):
        p = Province(1, "Test", 1000, conquered=False)
        assert p.conquered is False
        # 不能直接修改，只能通过构造函数设置（或未来提供 setter，目前不提供）
        # 但为了测试，我们假设内部可以通过其他方式修改（例如征服方法将调用私有字段）
        # 这里仅测试 property 只读
        with pytest.raises(AttributeError):
            p.conquered = True