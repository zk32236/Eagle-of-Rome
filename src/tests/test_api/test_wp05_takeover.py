# src/tests/test_api/test_wp05_takeover.py
"""WP-05 战争接管直接职权（DEV-13）API 层测试。

对齐 test_senate_api.py 的 setUp 模式（unittest 风格）。
覆盖：AC-01 / AC-02 / AC-03 / AC-04 / AC-05 / AC-06。
"""
import os
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class TestWP05Takeover(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")
        self.state._treasury = 500

        self.state._war_system = WarSystem(self.state)
        self.state._war_system.load_wars_from_json("wars.json")
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

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

        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]

    def _add_active_war(self, war_id="war_takeover", name="接管测试战争",
                        commander_id=None, rebellion_province_id=None,
                        status=WarStatus.ACTIVE):
        war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5,
                  naval_required=False, rebellion_province_id=rebellion_province_id)
        war.status = status
        war.commander_id = commander_id
        self.state.get_war_system()._active_wars.append(war)
        return war

    def test_wp05_takeover_permission(self):
        war = self._add_active_war()

        # 非当前玩家
        result = senate_api.takeover_war(self.state, "player2", war.id)
        self.assertFalse(result["success"])
        self.assertIsNone(war.commander_id)
        self.assertEqual(len(self.state.get_senate_proposals()), 0)

        # 无执政官
        self.consul.office = None
        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertFalse(result["success"])
        self.assertIsNone(war.commander_id)

        # 执政官 absent
        self.consul.office = "consul"
        self.consul.is_absent = True
        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertFalse(result["success"])
        self.assertIsNone(war.commander_id)
        self.assertEqual(len(self.state.get_senate_proposals()), 0)

    def test_wp05_takeover_executable(self):
        # 非活跃战争
        war = self._add_active_war(status=WarStatus.THREAT)
        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertFalse(result["success"])
        self.assertIsNone(war.commander_id)

        # 起义战争
        war2 = self._add_active_war(war_id="war_rebellion", rebellion_province_id=5)
        result = senate_api.takeover_war(self.state, "player1", war2.id)
        self.assertFalse(result["success"])
        self.assertIsNone(war2.commander_id)

        # 已有有效指挥官
        war3 = self._add_active_war(war_id="war_commander", commander_id=2)
        result = senate_api.takeover_war(self.state, "player1", war3.id)
        self.assertFalse(result["success"])
        self.assertEqual(war3.commander_id, 2)

    def test_wp05_takeover_execute(self):
        # 设置 senate 为当前阶段，使 DTO actionable（AC-04 穿透）
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)

        war = self._add_active_war()

        # AC-04: DTO 返回 can_takeover + takeover_options 正确 shape
        view_before = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view_before["success"])
        self.assertIs(view_before["data"]["can_takeover"], True)
        opt_before = view_before["data"]["takeover_options"]
        self.assertTrue(any(o["war_id"] == war.id for o in opt_before))
        for o in opt_before:
            self.assertIn("war_id", o)
            self.assertIn("name", o)
            self.assertIn("reason", o)

        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["war_id"], war.id)
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertTrue(war.legion_numbers)
        self.assertTrue(self.consul.is_absent)

        # WP-D AU-5：成功接管 → direct_actions 记录（含 war_name/commander_name/legions）
        actions = self.state.get_senate_direct_actions()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_type"], "takeover")
        self.assertEqual(actions[0]["war_id"], war.id)
        self.assertEqual(actions[0]["war_name"], war.name)
        self.assertEqual(actions[0]["commander_id"], self.consul.id)
        self.assertEqual(actions[0]["commander_name"], self.consul.get_formal_name())
        self.assertEqual(actions[0]["legions"], list(war.legion_numbers))
        # AU-R1-05c（G3 C4）：provenance 4 字段与既有字段并存（dict 透传零破坏）
        self.assertEqual(actions[0]["action"], "takeover")
        self.assertEqual(actions[0]["trigger_source"], "human_explicit")
        self.assertEqual(actions[0]["previous_status"], "active")
        self.assertEqual(actions[0]["resulting_status"], "active")

        # AC-05: 刷新后 takeover_options 移除该 war
        view_after = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view_after["success"])
        opt_after = view_after["data"]["takeover_options"]
        self.assertFalse(any(o["war_id"] == war.id for o in opt_after))
        # WP-D AU-5：view DTO 透传 direct_actions
        self.assertEqual(len(view_after["data"]["direct_actions"]), 1)

    def test_wp05_takeover_direct_not_proposal(self):
        war = self._add_active_war()
        proposals_before = self.state.get_senate_proposals()
        vetoes_before = self.state.get_senate_vetoes_copy()

        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])

        # AC-01: 接管不进入 proposal/veto 链
        self.assertEqual(self.state.get_senate_proposals(), proposals_before)
        self.assertEqual(self.state.get_senate_vetoes_copy(), vetoes_before)

        # AC-01: 否决 spec 无 takeover 类型
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        spec_path = os.path.join(project_root, "docs", "00_产品文档", "specifications", "MVP0.5-09_保民官否决权.md")
        with open(spec_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertNotIn("战争接管", content)
        self.assertNotIn("takeover", content)

    def test_wp05_takeover_reentry(self):
        war = self._add_active_war()

        first = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(first["success"])
        commander_after_first = war.commander_id
        legions_after_first = list(war.legion_numbers)

        # 连续两次接管同一 war → 第二次被幂等拒绝，commander/legions 不变
        second = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertFalse(second["success"])
        self.assertEqual(war.commander_id, commander_after_first)
        self.assertEqual(list(war.legion_numbers), legions_after_first)

    def test_wp05_takeover_resolve_announcement_direct_action(self):
        """WP-D AU-5/AU-6 场景 I：接管 → resolve → public_announcement.direct_actions 含接管（无 vote/veto 痕迹）。"""
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        war = self._add_active_war()

        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])
        # 接管不进入 proposal/veto 链
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), 0)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual(announcement["enacted_proposals"], [])
        self.assertEqual(len(announcement["direct_actions"]), 1)
        self.assertEqual(announcement["direct_actions"][0]["action_type"], "takeover")
        self.assertEqual(announcement["direct_actions"][0]["war_id"], war.id)
        # AU-R1-05c（G3 C4）：provenance 经 direct_actions → public_announcement dict 透传不破坏
        self.assertEqual(announcement["direct_actions"][0]["trigger_source"], "human_explicit")
        self.assertEqual(announcement["direct_actions"][0]["action"], "takeover")
        self.assertIn("previous_status", announcement["direct_actions"][0])
        self.assertIn("resulting_status", announcement["direct_actions"][0])

        # view 回读公示（随 phase_result 持久化）
        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        self.assertEqual(view["data"]["current_step"], "results")
        self.assertEqual(len(view["data"]["public_announcement"]["direct_actions"]), 1)
        # 实时 pending 列表在 resolve（clear_senate_pending）后被清空；持久副本在 public_announcement
        self.assertEqual(view["data"]["direct_actions"], [])


if __name__ == "__main__":
    unittest.main()
