"""
WP-G GB 切片测试 — Legion 序列化原语（T-GB-14，O 件 §4.4 / Q 件 DA-GB 7）

Parent Authority: WP-G v0.8 G3 DESIGN FROZEN
覆盖：Legion.to_dict/from_dict round-trip 无损（is_veteran/war_id/commander_id/
destroyed_turn/legion_type）+ 缺省退化路径（is_veteran 缺省 False，O 件 §3）。
"""
import pytest

from src.core.entities.legion import Legion, LegionStatus


class TestLegionSerialization:
    """T-GB-14：round-trip 无损 + 退化路径容错。"""

    def test_round_trip_full_state(self):
        """全部持久字段 round-trip 无损。"""
        legion = Legion(number=7, name="Legio VII")
        legion.status = LegionStatus.ACTIVE
        legion.is_veteran = True
        legion.commander_id = 42
        legion.war_id = "war_123"
        legion.battles_fought = 5
        legion.battles_won = 2
        legion._destroyed_turn = 9
        legion.set_legion_type("marius")

        data = legion.to_dict()
        restored = Legion.from_dict(data)

        assert restored.number == 7
        assert restored.name == "Legio VII"
        assert restored.status == LegionStatus.ACTIVE
        assert restored.is_veteran is True
        assert restored.commander_id == 42
        assert restored.war_id == "war_123"
        assert restored.battles_fought == 5
        assert restored.battles_won == 2
        assert restored.destroyed_turn == 9
        assert restored.legion_type == "marius"

    def test_round_trip_destroyed_state(self):
        """DESTROYED 状态（含 destroyed_turn）无损；恢复后可再募。"""
        legion = Legion(number=3)
        legion.mark_destroyed(11)
        data = legion.to_dict()
        restored = Legion.from_dict(data)

        assert restored.status == LegionStatus.DESTROYED
        assert restored.destroyed_turn == 11
        assert restored.war_id is None
        assert restored.is_veteran is False

    def test_round_trip_veteran_disbanded(self):
        """DISBANDED + Veteran 保留（G1-19 持久契约）。"""
        legion = Legion(number=5)
        legion.recruit(None)  # UNRAISED → AVAILABLE（disband 前置合法状态）
        legion.promote_to_veteran()
        assert legion.disband() is True  # AVAILABLE → DISBANDED（Veteran 保留）
        restored = Legion.from_dict(legion.to_dict())
        assert restored.status == LegionStatus.DISBANDED
        assert restored.is_veteran is True

    def test_from_dict_missing_keys_degradation(self):
        """缺省退化路径：is_veteran 缺省 False；无 number 不崩；未知 status 回退 UNRAISED。"""
        restored = Legion.from_dict({})
        assert restored.number == 0
        assert restored.status == LegionStatus.UNRAISED
        assert restored.is_veteran is False
        assert restored.war_id is None
        assert restored.commander_id is None
        assert restored.destroyed_turn == 0
        assert restored.legion_type == "polybian"

    def test_from_dict_bad_status_fallback(self):
        """非法 status 值回退 UNRAISED（禁旧存档/脏数据加载崩溃，O 件 §3）。"""
        restored = Legion.from_dict({"number": 9, "status": "banana"})
        assert restored.status == LegionStatus.UNRAISED

    def test_from_dict_partial_old_save(self):
        """旧存档（仅 number/name）加载不崩且字段缺省正确。"""
        restored = Legion.from_dict({"number": 12, "name": "Legio XII"})
        assert restored.number == 12
        assert restored.name == "Legio XII"
        assert restored.status == LegionStatus.UNRAISED
        assert restored.is_veteran is False
