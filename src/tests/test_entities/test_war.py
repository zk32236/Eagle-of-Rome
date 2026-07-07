import pytest
from src.core.entities.war import War, WarType, WarStatus

class TestWar:
    """测试 War 实体（包括 MVP 0.7-2 新增字段）"""

    def test_war_creation_without_unlocked(self):
        war = War(
            id="test1",
            name="Test War",
            description="A test war",
            war_type=WarType.FOREIGN,
            strength=10,
        )
        assert war.id == "test1"
        assert war.name == "Test War"
        assert war.unlocked_provinces == []  # 默认空列表

    def test_war_creation_with_unlocked(self):
        war = War(
            id="test2",
            name="Punic War",
            unlocked_provinces=[1, 2]
        )
        assert war.unlocked_provinces == [1, 2]
        # 确保返回的是副本
        provs = war.unlocked_provinces
        provs.append(3)
        assert war.unlocked_provinces == [1, 2]  # 原列表不变

    def test_war_to_dict_and_from_dict(self):
        original = War(
            id="war123",
            name="Gallic War",
            description="Gaul uprising",
            war_type=WarType.BARBARIAN,
            start_year=-58,
            threat_level=2,
            auto_escalate=True,
            escalate_rate=1,
            strength=8,
            naval_support_required=False,
            naval_strength=0,
            land_battle=True,
            disaster_numbers=[2, 3],
            standoff_numbers=[4, 5, 6],
            rewards={"treasury": 100},
            penalties={"unrest": 1},
            is_imminent=False,
            matched_war_id=None,
            unlocked_provinces=[3, 4, 5]
        )
        # 设置一些运行时字段
        original.status = WarStatus.ACTIVE
        original.commander_id = 101
        original.legions_assigned = 4
        original.activation_turn = 10

        data = original.to_dict()
        reconstructed = War.from_dict(data)

        # 比较静态属性
        assert reconstructed.id == original.id
        assert reconstructed.name == original.name
        assert reconstructed.description == original.description
        assert reconstructed.war_type == original.war_type
        assert reconstructed.start_year == original.start_year
        assert reconstructed.threat_level == original.threat_level
        assert reconstructed.auto_escalate == original.auto_escalate
        assert reconstructed.escalate_rate == original.escalate_rate
        assert reconstructed.strength == original.strength
        assert reconstructed.naval_support_required == original.naval_support_required
        assert reconstructed.naval_strength == original.naval_strength
        assert reconstructed.land_battle == original.land_battle
        assert reconstructed.disaster_numbers == original.disaster_numbers
        assert reconstructed.standoff_numbers == original.standoff_numbers
        assert reconstructed.rewards == original.rewards
        assert reconstructed.penalties == original.penalties
        assert reconstructed.is_imminent == original.is_imminent
        assert reconstructed.matched_war_id == original.matched_war_id
        assert reconstructed.unlocked_provinces == original.unlocked_provinces

        # 比较运行时字段
        assert reconstructed.status == original.status
        assert reconstructed.commander_id == original.commander_id
        assert reconstructed.legions_assigned == original.legions_assigned
        assert reconstructed.activation_turn == original.activation_turn
        # 其他字段可类似验证