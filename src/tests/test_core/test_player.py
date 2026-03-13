# src/tests/test_core/test_player.py
"""
测试 Player 实体和 GameState 玩家管理功能
"""
import unittest
from src.core.game_state import GameState
from src.core.entities.player import Player, PlayerType
from src.core.entities.entities import Faction
from src.core.i18n import i18n


class TestPlayerEntity(unittest.TestCase):
    """测试 Player 实体"""

    def setUp(self):
        # 确保 i18n 加载（可选，因为 Player 不使用 i18n）
        pass

    def test_player_creation(self):
        player = Player(
            player_id="player_1",
            faction_id="optimates",
            player_type=PlayerType.HUMAN,
            is_online=True,
            connection_id="conn123"
        )
        self.assertEqual(player.player_id, "player_1")
        self.assertEqual(player.faction_id, "optimates")
        self.assertEqual(player.player_type, PlayerType.HUMAN)
        self.assertTrue(player.is_online)
        self.assertEqual(player.connection_id, "conn123")

    def test_player_setters(self):
        player = Player("p1")
        player.is_online = True
        player.connection_id = "conn456"
        self.assertTrue(player.is_online)
        self.assertEqual(player.connection_id, "conn456")

    def test_player_to_dict_from_dict(self):
        original = Player(
            player_id="p2",
            faction_id="populares",
            player_type=PlayerType.AI,
            is_online=False,
            connection_id=None
        )
        data = original.to_dict()
        self.assertEqual(data["player_id"], "p2")
        self.assertEqual(data["faction_id"], "populares")
        self.assertEqual(data["player_type"], "ai")
        self.assertFalse(data["is_online"])
        self.assertIsNone(data["connection_id"])

        restored = Player.from_dict(data)
        self.assertEqual(restored.player_id, "p2")
        self.assertEqual(restored.faction_id, "populares")
        self.assertEqual(restored.player_type, PlayerType.AI)
        self.assertFalse(restored.is_online)
        self.assertIsNone(restored.connection_id)


class TestGameStatePlayerManagement(unittest.TestCase):
    """测试 GameState 中的玩家管理方法"""

    def setUp(self):
        self.state = GameState()
        # 添加一些派系，用于关联玩家
        self.faction1 = Faction(id="optimates", name="Optimates")
        self.faction2 = Faction(id="populares", name="Populares")
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        self.player1 = Player("p1", "optimates")
        self.player2 = Player("p2", "populares")
        self.player3 = Player("p3", None)  # 观察者或无派系

    def test_add_and_get_player(self):
        self.state.add_player(self.player1)
        self.assertEqual(self.state.get_player("p1"), self.player1)
        self.assertIsNone(self.state.get_player("nonexistent"))

    def test_get_all_players(self):
        self.state.add_player(self.player1)
        self.state.add_player(self.player2)
        players = self.state.get_all_players()
        self.assertEqual(len(players), 2)
        self.assertIn(self.player1, players)
        self.assertIn(self.player2, players)

    def test_get_player_by_faction(self):
        self.state.add_player(self.player1)
        self.state.add_player(self.player2)
        self.assertEqual(self.state.get_player_by_faction("optimates"), self.player1)
        self.assertEqual(self.state.get_player_by_faction("populares"), self.player2)
        self.assertIsNone(self.state.get_player_by_faction("nonexistent"))

    def test_remove_player(self):
        self.state.add_player(self.player1)
        self.state.set_turn_order(["p1"])
        self.state.set_current_player("p1")
        self.assertTrue(self.state.remove_player("p1"))
        self.assertIsNone(self.state.get_player("p1"))
        self.assertIsNone(self.state.get_current_player())
        self.assertEqual(self.state._turn_order, [])

        # 移除不存在的玩家
        self.assertFalse(self.state.remove_player("p2"))

    def test_turn_order_and_current_player(self):
        self.state.add_player(self.player1)
        self.state.add_player(self.player2)
        self.state.set_turn_order(["p1", "p2"])
        self.state.set_current_player("p1")
        self.assertEqual(self.state.get_current_player(), self.player1)

        # 切换下一个
        next_id = self.state.next_player()
        self.assertEqual(next_id, "p2")
        self.assertEqual(self.state.get_current_player(), self.player2)

        # 再切换下一个（回到第一个）
        next_id = self.state.next_player()
        self.assertEqual(next_id, "p1")
        self.assertEqual(self.state.get_current_player(), self.player1)

    def test_next_player_empty_turn_order(self):
        self.assertIsNone(self.state.next_player())

    def test_next_player_current_not_in_order(self):
        self.state.add_player(self.player1)
        self.state.add_player(self.player2)
        self.state.set_turn_order(["p1", "p2"])
        self.state.set_current_player("p3")  # 不存在
        next_id = self.state.next_player()
        self.assertEqual(next_id, "p1")  # 应重置到第一个

    def test_is_current_player(self):
        self.state.add_player(self.player1)
        self.state.set_current_player("p1")
        self.assertTrue(self.state.is_current_player("p1"))
        self.assertFalse(self.state.is_current_player("p2"))

    def test_serialization(self):
        # 准备数据
        self.state.add_player(self.player1)
        self.state.add_player(self.player2)
        self.state.set_turn_order(["p1", "p2"])
        self.state.set_current_player("p1")

        # 序列化
        data = self.state.to_dict()

        # 反序列化到新状态
        new_state = GameState()
        new_state.load_from_dict(data)

        # 验证
        self.assertEqual(len(new_state.get_all_players()), 2)
        self.assertEqual(new_state.get_player("p1").faction_id, "optimates")
        self.assertEqual(new_state.get_player("p2").faction_id, "populares")
        self.assertEqual(new_state._turn_order, ["p1", "p2"])
        self.assertEqual(new_state._current_player_id, "p1")


if __name__ == "__main__":
    unittest.main()