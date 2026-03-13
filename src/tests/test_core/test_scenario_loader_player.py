# src/tests/test_core/test_scenario_loader_player.py
"""
测试场景加载器中的玩家创建功能
"""
import unittest
from unittest.mock import patch, MagicMock
from src.core.game_state import GameState
from src.core.scenario_loader import ScenarioLoader
from src.core.entities.player import Player


class TestScenarioLoaderPlayers(unittest.TestCase):

    def setUp(self):
        self.state = GameState()
        # 模拟配置，包含派系
        self.config = {
            "initial_state": {
                "factions": [
                    {"id": "optimates", "name": "Optimates", "treasury": 10, "is_player": True},
                    {"id": "populares", "name": "Populares", "treasury": 10, "is_player": False},
                    {"id": "equites", "name": "Equites", "treasury": 10, "is_player": False},
                ]
            }
        }

    @patch.object(ScenarioLoader, '_load_factions')
    @patch.object(ScenarioLoader, '_load_figures')
    @patch.object(ScenarioLoader, '_assign_initial_governors')
    def test_create_players_from_factions(self, mock_assign, mock_figures, mock_factions):
        # 直接调用辅助方法，而不依赖整个 load_scenario
        from src.core.scenario_loader import ScenarioLoader

        # 手动添加派系到 state（模拟 _load_factions 的效果）
        from src.core.entities.entities import Faction
        self.state.add_faction(Faction(id="optimates", name="Optimates", treasury=10, is_player=True))
        self.state.add_faction(Faction(id="populares", name="Populares", treasury=10, is_player=False))
        self.state.add_faction(Faction(id="equites", name="Equites", treasury=10, is_player=False))

        # 调用玩家创建方法
        ScenarioLoader._create_players_from_factions(self.state)

        players = self.state.get_all_players()
        self.assertEqual(len(players), 3)

        # 检查玩家ID和派系关联
        player_ids = [p.player_id for p in players]
        self.assertIn("player_optimates", player_ids)
        self.assertIn("player_populares", player_ids)
        self.assertIn("player_equites", player_ids)

        # 检查回合顺序
        self.assertEqual(self.state._turn_order, ["player_optimates", "player_populares", "player_equites"])

        # 检查当前玩家为第一个
        current = self.state.get_current_player()
        self.assertEqual(current.player_id, "player_optimates")
        self.assertEqual(current.faction_id, "optimates")

    def test_no_factions_no_players(self):
        # 无派系时不应创建玩家
        ScenarioLoader._create_players_from_factions(self.state)
        self.assertEqual(len(self.state.get_all_players()), 0)
        self.assertIsNone(self.state.get_current_player())


if __name__ == "__main__":
    unittest.main()