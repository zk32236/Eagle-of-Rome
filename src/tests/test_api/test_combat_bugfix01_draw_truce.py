"""
WP03-BUGFIX-01 定向测试（TS-BF-01 ~ TS-BF-08）

覆盖：
- Fix-A：draw → STALEMATE 归一化（复用 decider 词表，无第四套结果模型）
- Fix-B：非决定性（draw）不调用 resolve_war（war/commander continuity 保留）
- Fix-C：treaty 连续性（do_combat_action non-decisive 分支内联 _generate_peace_treaty）
- 决定性（victory/defeat/triumph/disaster）回归不变

test identity：由 oc-pytest-run evidence mode 产出（eor-pytest-identity/v1）。
"""
import unittest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api


class TestBugfix01DrawTruce(unittest.TestCase):
    """BUGFIX-01：draw 归一化 + 非决定性不 resolve + treaty 连续性"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for ph in ["mortality", "revenue", "forum", "population", "senate"]:
            self.state.mark_phase_executed(ph)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)

        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.state.add_member(self.commander)
        self.faction.member_ids.append(1)

        self.player = Player(player_id="player_opt", faction_id="optimates",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

    def _make_draw_war(self, war_id="draw_war", commander_id=1, strength=14):
        """构造带指挥官、dice=7 时判定为 draw 的 war。

        dice=7 + martial=6 + legions=1(→2) = 15；enemy=14 → score=1；
        7 ∈ standoff_numbers → draw。
        """
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=strength, threat_level=3, disaster_numbers=[12])
        war.commander_id = commander_id
        war.legions_assigned = 1
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        return war

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-01（unit）：draw → STALEMATE 归一化 + treaty 生成 + commander 保留
    # ════════════════════════════════════════════════════════════════════
    def test_bf01_generate_peace_treaty_draw_normalizes_to_stalemate(self):
        war = self._make_draw_war()
        treaty = combat_api._generate_peace_treaty(war, "draw", self.state)
        self.assertIsNotNone(treaty)
        self.assertEqual(treaty["indemnity"], 0)
        self.assertEqual(treaty["duration"], 3)  # duration_stalemate 默认值
        self.assertIn(war, self.state._war_system._truce_wars)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 1)
        self.assertEqual(war.original_commander_id, 1)

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-02（unit）：决定性结果仍不生成条约
    # ════════════════════════════════════════════════════════════════════
    def test_bf02_decisive_results_still_no_treaty(self):
        war_t = self._make_draw_war("war_triumph")
        self.assertIsNone(combat_api._generate_peace_treaty(war_t, "triumph", self.state))
        war_d = self._make_draw_war("war_disaster")
        self.assertIsNone(combat_api._generate_peace_treaty(war_d, "disaster", self.state))

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-03（unit）：draw 下不调用 resolve_war（war 不入 discard）
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint", return_value=7)
    def test_bf03_do_combat_action_draw_skips_resolve(self, mock_randint):
        war = self._make_draw_war()
        with patch.object(WarSystem, "resolve_war") as mock_resolve:
            result = combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        mock_resolve.assert_not_called()
        self.assertNotIn(war, self.state._war_system._war_discard)
        self.assertIsNotNone(war.commander_id)
        self.assertIn(war.status, (WarStatus.ACTIVE, WarStatus.TRUCE))

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-04（unit/E2E）：draw 后 commander continuity 保留
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint", return_value=7)
    def test_bf04_draw_preserves_commander_continuity(self, mock_randint):
        self.commander.office = "consul"
        self.commander.is_absent = True
        war = self._make_draw_war()
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        ws = self.state._war_system
        self.assertIs(ws.get_war_by_commander(1), war)
        self.assertTrue(self.commander.is_absent)
        self.assertEqual(self.commander.office, "consul")

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-05（E2E）：auto_resolve_combat draw → truce + same war 命中
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint", return_value=7)
    def test_bf05_auto_resolve_draw_truce_continuity(self, mock_randint):
        war = self._make_draw_war()
        result = combat_api.auto_resolve_combat(self.state, "player_opt")
        self.assertTrue(result["success"])
        ws = self.state._war_system
        self.assertIs(ws.get_war_by_commander(1), war)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 1)
        # treaties DTO 来源冻结：draw 条约经 do_combat_action 副作用落地，不入 treaties 列表
        self.assertEqual(result["data"]["treaties"], [])

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-06（unit）：victory/defeat 决定性回归不变
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_bf06_victory_and_defeat_still_resolve(self, mock_randint):
        ws = self.state._war_system

        # victory：dice=7 + martial=6 + legions=0 → total=13，enemy=5 → score=8 → victory
        self.commander.office = "consul"
        self.commander.is_absent = True
        vwar = War(id="victory_war", name="Victory", war_type=WarType.FOREIGN,
                   strength=5, threat_level=3, disaster_numbers=[12])
        vwar.commander_id = 1
        vwar.legions_assigned = 0
        vwar.status = WarStatus.ACTIVE
        ws._active_wars.append(vwar)
        mock_randint.return_value = 7
        combat_api.do_combat_action(self.state, "player_opt", vwar.id, "attack")
        self.assertEqual(vwar.status, WarStatus.RESOLVED)
        self.assertIn(vwar, ws._war_discard)
        self.assertIsNone(self.commander.office)
        self.assertFalse(self.commander.is_absent)

        # defeat：dice=2 + martial=6 + legions=0 → total=8，enemy=50 → score=-42 → defeat
        dwar = War(id="defeat_war", name="Defeat", war_type=WarType.FOREIGN,
                   strength=50, threat_level=3, disaster_numbers=[12])
        dwar.commander_id = 1
        dwar.legions_assigned = 0
        dwar.status = WarStatus.ACTIVE
        ws._active_wars.append(dwar)
        mock_randint.return_value = 2
        combat_api.do_combat_action(self.state, "player_opt", dwar.id, "attack")
        self.assertEqual(dwar.status, WarStatus.DEFEATED)
        self.assertIn(dwar, ws._war_discard)
        self.assertIsNone(dwar.commander_id)

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-07（unit）：triumph/disaster 仍 resolve（不入 truce、不生成条约）
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_bf07_triumph_disaster_still_resolved_no_truce(self, mock_randint):
        ws = self.state._war_system

        # triumph：dice=7 + martial=6 → total=13，enemy=0 → score=13 → triumph
        twar = War(id="triumph_war", name="Triumph", war_type=WarType.FOREIGN,
                   strength=0, threat_level=3, disaster_numbers=[12])
        twar.commander_id = 1
        twar.legions_assigned = 0
        twar.status = WarStatus.ACTIVE
        ws._active_wars.append(twar)
        mock_randint.return_value = 7
        combat_api.do_combat_action(self.state, "player_opt", twar.id, "attack")
        self.assertEqual(twar.status, WarStatus.RESOLVED)
        self.assertNotIn(twar, ws._truce_wars)

        # disaster：dice=2 ∈ disaster_numbers → disaster → RESOLVED（非 truce）
        dwar = War(id="disaster_war", name="Disaster", war_type=WarType.FOREIGN,
                   strength=0, threat_level=3, disaster_numbers=[2, 3])
        dwar.commander_id = 1
        dwar.legions_assigned = 1
        dwar.status = WarStatus.ACTIVE
        ws._active_wars.append(dwar)
        mock_randint.return_value = 2
        combat_api.do_combat_action(self.state, "player_opt", dwar.id, "attack")
        self.assertEqual(dwar.status, WarStatus.RESOLVED)
        self.assertNotIn(dwar, ws._truce_wars)

    # ════════════════════════════════════════════════════════════════════
    # TS-BF-08（integration）：HUMAN 交互路径 draw 无死锁（can_advance）
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint", return_value=7)
    def test_bf08_human_path_draw_no_deadlock(self, mock_randint):
        war = self._make_draw_war()
        self.assertTrue(combat_api.select_war(self.state, "player_opt", war.id)["success"])
        self.assertTrue(combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")["success"])
        self.assertTrue(combat_api.confirm_battle_result(self.state, "player_opt")["success"])

        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertTrue(view["data"]["all_resolved"])
        self.assertTrue(view["data"]["can_advance"])
        self.assertEqual(view["data"]["current_step"], "advance")

        # 关键不变量：draw 离开 active 且入 truce（非 discard），commander 保留
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, self.state._war_system._truce_wars)
        self.assertNotIn(war, self.state._war_system._war_discard)
        self.assertEqual(war.commander_id, 1)

        self.assertTrue(combat_api.advance_combat(self.state, "player_opt")["success"])


if __name__ == "__main__":
    unittest.main()
