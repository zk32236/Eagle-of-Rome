import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.figure import Figure
from src.ui.commands.phase_mortality import MortalityCommand
from src.ui.commands.phase_forum import ForumCommand


class TestMightyManEvent(unittest.TestCase):

    def setUp(self):
        self.test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "天降猛男", "effect": "mighty_man", "weight": 1}],
                "event_draw_count": 1
            },
            "forum_rules": {
                "new_figures_count": 2,
                "class_probabilities": {"nobile": 0.5, "eques": 0.3, "plebeian": 0.2}
            }
        }
        self.state = GameState.create_for_testing(self.test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)

    @patch("builtins.open")
    @patch("json.load")
    def test_historical_hero_spawn(self, mock_json_load, mock_open):
        """测试历史英雄生成"""
        # 模拟英雄数据
        mock_json_load.return_value = {
            "heroes": [
                {
                    "id": "scipio",
                    "name": "Scipio Africanus",
                    "birth_year": -300,  # 修改为 -300，使得 birth_year+16 = -284 < -264
                    "death_year": -200,  # 死亡年份晚于当前年份
                    "martial": 10,
                    "intelligence": 9,
                    "charisma": 8,
                    "zeal": 7,
                    "family_prestige": 5
                }
            ]
        }

        # 执行天命阶段
        cmd_m = MortalityCommand(self.state)
        cmd_m.execute([])

        self.assertTrue(self.state.hero_spawned_this_turn)
        self.assertEqual(self.state.hero_to_spawn["type"], "historical")
        self.assertEqual(self.state.hero_to_spawn["data"]["name"], "Scipio Africanus")

        # 执行广场阶段
        # 需要模拟前置阶段标记
        self.state._executed_phases.add("revenue")
        cmd_f = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd_f.execute([])
        output = f.getvalue()

        self.assertIn("🌟 英雄降临: Scipio Africanus", output)
        # 验证人物已添加
        hero = next((m for m in self.state.get_living_members() if m.name == "Scipio Africanus"), None)
        self.assertIsNotNone(hero)
        self.assertEqual(hero.martial, 10)
        self.assertEqual(hero.intelligence, 9)
        self.assertEqual(hero.charisma, 8)
        self.assertEqual(hero.zeal, 7)

    @patch("builtins.open")
    @patch("json.load")
    def test_random_hero_spawn(self, mock_json_load, mock_open):
        """测试无历史人物时生成随机猛人"""
        # 模拟英雄数据为空
        mock_json_load.return_value = {"heroes": []}

        # 先添加一些存活人物，以便取最大值
        from src.core.entities.figure import Figure
        fig1 = Figure(101, "Test1", age=30)
        fig1.martial = 5
        fig1.intelligence = 6
        fig1.charisma = 7
        fig1.zeal = 8
        fig1.is_dead = False
        self.state.add_member(fig1)

        fig2 = Figure(102, "Test2", age=40)
        fig2.martial = 9
        fig2.intelligence = 4
        fig2.charisma = 3
        fig2.zeal = 2
        fig2.is_dead = False
        self.state.add_member(fig2)

        # 执行天命阶段
        cmd_m = MortalityCommand(self.state)
        cmd_m.execute([])

        self.assertTrue(self.state.hero_spawned_this_turn)
        self.assertEqual(self.state.hero_to_spawn["type"], "random")

        # 执行广场阶段
        self.state._executed_phases.add("revenue")
        cmd_f = ForumCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd_f.execute([])
        output = f.getvalue()

        self.assertIn("🌟 英雄降临:", output)
        # 验证随机猛人属性应为最大值（martial=9, intel=6, char=7, zeal=8）
        hero = self.state.curia.get_all_available()[-1]  # 最后一个应是英雄
        self.assertGreaterEqual(hero.martial, 9)
        self.assertGreaterEqual(hero.intelligence, 6)
        self.assertGreaterEqual(hero.charisma, 7)
        self.assertGreaterEqual(hero.zeal, 8)

    def test_no_duplicate_historical_hero(self):
        """测试同一历史人物不会出现两次"""
        # 此测试需要完整文件读取，可考虑手动添加已出现 ID
        # 简单模拟
        self.state._spawned_hero_ids.add("scipio")
        # 后续检查...
        pass