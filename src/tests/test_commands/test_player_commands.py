# src/tests/test_commands/test_player_commands.py
"""
测试玩家命令：players, end_turn
"""
import unittest
from unittest.mock import MagicMock, patch
import io
from contextlib import redirect_stdout
from src.ui.commands.func_player import PlayersCommand, EndTurnCommand
from src.core.game_state import GameState
from src.core.entities.player import Player, PlayerType
from src.core.i18n import i18n


class TestPlayerCommands(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        i18n.load("zh-CN")

    def setUp(self):
        self.state = MagicMock(spec=GameState)
        self.player = Player("p1", "optimates", PlayerType.HUMAN)
        self.state.get_current_player.return_value = self.player

    @patch('src.api.player_api.get_players')
    def test_players_command(self, mock_get_players):
        # 模拟 API 返回值
        mock_get_players.return_value = {
            "success": True,
            "message": "玩家列表:\n  p1 (当前) - 派系: Optimates (human)",
            "data": []
        }
        cmd = PlayersCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()
        self.assertTrue(result)
        self.assertIn("玩家列表", output)
        mock_get_players.assert_called_once_with(self.state)

    @patch('src.api.player_api.next_player')
    def test_end_turn_command_success(self, mock_next_player):
        mock_next_player.return_value = {
            "success": True,
            "message": "已切换到玩家 p2 (派系 Populares)",
            "data": {"new_player_id": "p2"}
        }
        cmd = EndTurnCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()
        self.assertTrue(result)
        self.assertIn("已切换到玩家", output)
        mock_next_player.assert_called_once_with(self.state, "p1")

    @patch('src.api.player_api.next_player')
    def test_end_turn_command_failure(self, mock_next_player):
        mock_next_player.return_value = {
            "success": False,
            "message": "❌ 当前不是您的回合",
            "data": None
        }
        cmd = EndTurnCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()
        self.assertFalse(result)
        self.assertIn("当前不是您的回合", output)

    def test_end_turn_no_current_player(self):
        self.state.get_current_player.return_value = None
        cmd = EndTurnCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            result = cmd.execute([])
        output = f.getvalue()
        self.assertFalse(result)
        self.assertIn("当前没有玩家", output)


if __name__ == "__main__":
    unittest.main()