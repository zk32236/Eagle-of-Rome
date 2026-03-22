# src/tests/test_api/test_senate_api.py
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus  # 确保导入 WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class TestSenateAPI(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")
        self.state._treasury = 500

        # 手动初始化战争、军事、海军系统（senate_api 测试需要）
        self.state._war_system = WarSystem(self.state)
        self.state._war_system.load_wars_from_json("wars.json")
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        # 创建派系
        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 创建人物
        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)

        self.senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
        self.senator.class_tier = ClassTier.NOBILE
        self.senator.influence = 100
        self.state.add_member(self.senator)
        self.faction1.member_ids.append(2)

        self.tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(self.tribune)
        self.faction2.member_ids.append(3)

        # 为 populaires 派系也添加一个贵族元老（便于 resolve_senate 测试）
        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        # 设置当前玩家
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human")
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]
        self.assertIsNotNone(self.state.get_war_system())

    def test_get_senate_initial_info(self):
        result = senate_api.get_senate_initial_info(self.state)
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIn("faction_leaders", data)
        self.assertIn("presiding_officer", data)
        self.assertEqual(data["presiding_officer"]["figure_id"], 1)  # 执政官

    def test_propose_war(self):
        # 创建威胁战争，需要提供 war_type 和 strength
        war = War(id="war1", name="测试战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT  # 设置为威胁状态
        ws = self.state.get_war_system()
        ws._threats.append(war)  # 加入威胁列表

        result = senate_api.propose(self.state, "player1", "war", war_id="war1", legions=6)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["proposal_id"], 1)

        proposals = self.state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "war")
        self.assertEqual(proposals[0]["war_id"], "war1")
        self.assertEqual(proposals[0]["legions"], 6)

    def test_propose_not_consul(self):
        # 将当前玩家改为非执政官派系
        self.state._current_player_id = "player2"
        result = senate_api.propose(self.state, "player2", "war", war_id="war1", legions=6)
        self.assertFalse(result["success"])
        self.assertIn("只有执政官可以提出提案", result["message"])

    def test_vote(self):
        # 先添加一个提案
        proposal_id = self.state.add_senate_proposal({"type": "war", "war_id": "war1", "legions": 6})
        result = senate_api.vote(self.state, "player1", [proposal_id], [True])
        self.assertTrue(result["success"])
        # 检查投票记录
        self.assertIn("player1", self.state._senate_pending["votes"])
        self.assertIn(proposal_id, self.state._senate_pending["votes"]["player1"])
        self.assertTrue(self.state._senate_pending["votes"]["player1"][proposal_id])

    def test_vote_twice(self):
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        senate_api.vote(self.state, "player1", [proposal_id], [True])
        result = senate_api.vote(self.state, "player1", [proposal_id], [False])
        self.assertFalse(result["success"])
        self.assertIn("均已投过票", result["message"])

    def test_veto(self):
        # 切换当前玩家为 player2（保民官所在派系）
        self.state._current_player_id = "player2"
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        result = senate_api.veto(self.state, "player2", [proposal_id])
        self.assertTrue(result["success"])
        self.assertIn(proposal_id, self.state._senate_pending["vetoes"])

    def test_veto_not_tribune(self):
        # 当前玩家为 optimates，没有保民官
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        result = senate_api.veto(self.state, "player1", [proposal_id])
        self.assertFalse(result["success"])
        self.assertIn("只有保民官可以行使否决权", result["message"])

    @patch("src.api.senate_api.execute_war_declaration")
    @patch("src.api.senate_api.process_war_takeover")
    def test_resolve_senate(self, mock_takeover, mock_execute):
        # 添加提案、投票、否决
        war_proposal_id = self.state.add_senate_proposal(
            {"type": "war", "war_id": "war1", "legions": 6, "consul_id": 1})
        self.state.record_senate_vote("player1", war_proposal_id, True)  # 支持
        # 模拟另一个派系投票（通过决策器）
        # 使用 mock 决策器返回支持
        mock_decider = MagicMock()
        mock_decider.decide_vote.return_value = True
        result = senate_api.resolve_senate(self.state, vote_decider=mock_decider)
        self.assertTrue(result["success"])
        self.assertIn(war_proposal_id, result["data"]["passed_proposals"])
        mock_execute.assert_called_once()

    def test_propose_peace_manually(self):
        """手动模式下停战提案应将草案状态设置为 submitted"""
        # 创建一个停战战争，并设置 pending 草案
        war = War(id="war_peace_test", name="停战测试战争", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        treaty = {"indemnity": 100, "duration": 3, "status": "pending"}
        war.set_peace_treaty(treaty)

        ws = self.state.get_war_system()
        ws._truce_wars.append(war)

        # 调用 propose 提交停战提案
        result = senate_api.propose(self.state, "player1", "peace", war_id="war_peace_test")

        self.assertTrue(result["success"])
        # 验证草案状态已变为 submitted
        self.assertEqual(war.peace_treaty["status"], "submitted")