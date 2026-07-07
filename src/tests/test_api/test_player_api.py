# src/tests/test_api/test_player_api.py
"""
测试玩家 API
"""
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.player import Player, PlayerType
from src.core.entities.entities import Faction
from src.api import player_api
from src.core.i18n import i18n


class TestPlayerAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 加载 i18n 以便获取真实消息（也可用 mock）
        i18n.load("zh-CN")

    def setUp(self):
        self.state = MagicMock(spec=GameState)
        # 模拟一些玩家
        self.player1 = Player("p1", "optimates", PlayerType.HUMAN)
        self.player2 = Player("p2", "populares", PlayerType.HUMAN)
        self.faction1 = Faction(id="optimates", name="Optimates")
        self.faction2 = Faction(id="populares", name="Populares")

        self.state.get_all_players.return_value = [self.player1, self.player2]
        self.state.get_current_player.return_value = self.player1
        self.state._current_player_id = "p1"
        self.state.is_current_player.side_effect = lambda pid: pid == "p1"
        self.state.get_faction.side_effect = lambda fid: self.faction1 if fid == "optimates" else self.faction2
        # 确保 bypass_player_check 为 False
        self.state.config.get.return_value = False

    def test_get_players(self):
        result = player_api.get_players(self.state)
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["player_id"], "p1")
        self.assertTrue(data[0]["is_current"])
        self.assertEqual(data[1]["player_id"], "p2")
        self.assertFalse(data[1]["is_current"])
        # 检查消息字符串（可选）
        self.assertIn("玩家列表", result["message"])

    def test_get_current_player_success(self):
        result = player_api.get_current_player(self.state)
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["player_id"], "p1")
        self.assertEqual(data["faction_id"], "optimates")
        self.assertIn("当前玩家", result["message"])

    def test_get_current_player_no_player(self):
        self.state.get_current_player.return_value = None
        result = player_api.get_current_player(self.state)
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], i18n.get("error_no_current_player"))

    def test_next_player_success(self):
        self.state.next_player.return_value = "p2"
        result = player_api.next_player(self.state, "p1")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["new_player_id"], "p2")
        self.assertIn("已切换到玩家", result["message"])
        self.state.next_player.assert_called_once()
        self.state.log_event.assert_called_once()

    def test_next_player_not_current(self):
        result = player_api.next_player(self.state, "p2")  # p2 不是当前
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], i18n.get("error_not_your_turn"))
        self.state.next_player.assert_not_called()

    def test_next_player_no_next(self):
        self.state.is_current_player.return_value = True
        self.state.next_player.return_value = None
        result = player_api.next_player(self.state, "p1")
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], i18n.get("error_no_next_player"))

    def test_end_turn_alias(self):
        # 测试 end_turn 是否等同 next_player
        self.state.next_player.return_value = "p2"
        result = player_api.end_turn(self.state, "p1")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["new_player_id"], "p2")


if __name__ == "__main__":
    unittest.main()