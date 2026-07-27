"""
Feature Freeze Test — GUI combat_api 当前行为基线 (S1 冻结)

捕获 GUI combat_api 的战斗结算逻辑，作为改造前的行为快照。
改造后这些测试断言应与共享用例输出一致。
"""
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.legion import Legion, LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api


class TestGUICombatFeatures(unittest.TestCase):
    """GUI combat_api 特征冻结——捕获当前行为基线"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("mortality")
        self.state.mark_phase_executed("revenue")
        self.state.mark_phase_executed("forum")
        self.state.mark_phase_executed("population")
        self.state.mark_phase_executed("senate")
        self.state._treasury = 500

        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction1)

        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.commander.influence = 50
        self.state.add_member(self.commander)
        self.faction1.member_ids.append(1)

        self.player = Player(player_id="player_opt", faction_id="optimates",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

        # 创建测试战争
        self.war1 = War(
            id="test_war_1", name="Test War 1",
            war_type=WarType.FOREIGN, strength=8, threat_level=3,
            rewards={"treasury": 100},
            disaster_numbers=[2, 3],
        )
        self.war1.commander_id = 1
        self.war1.legions_assigned = 4
        self.war1.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war1)

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 1: _compute_combat_result 结果分类冻结
    # ════════════════════════════════════════════════════════════════════
    def test_gui_compute_triumph_high_score(self):
        """score >= 10 → triumph"""
        result = combat_api._compute_combat_result(self.war1, self.state, 10, "attack")
        self.assertEqual(result["result"], "triumph")
        self.assertTrue(result["triumph"])

    def test_gui_compute_victory_moderate_score(self):
        """5 <= score < 10 → victory"""
        # dice=8, martial=6, legion=4*2=8 → total_attack=22, enemy=8 → score=14 → triumph, too high
        # Need different setup: less power
        war = War(id="tight_war", name="Tight War", war_type=WarType.FOREIGN,
                  strength=20)  # enemy 20, dice=7, mart=6, leg=0 → score=-7 → defeat
        war.commander_id = 1
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # dice=8, martial=6, leg=0, action_bias=0 → total=14, enemy=20 → score=-6 → defeat
        # Try dice=10: total=16, enemy=20 → score=-4 → defeat
        # We need exactly 5 <= score < 10
        # dice=9: total=15, enemy=10 → score=5 → victory
        war2 = War(id="victory_war", name="Victory War", war_type=WarType.FOREIGN,
                   strength=10, disaster_numbers=[12])
        war2.commander_id = 1
        war2.legions_assigned = 1
        war2.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war2)
        # dice=7, martial=6, leg=1*2=2, bias=0 → total=15, enemy=10 → score=5 → victory
        result = combat_api._compute_combat_result(war2, self.state, 7, "attack")
        self.assertEqual(result["result"], "victory")

    def test_gui_compute_draw_low_positive(self):
        """0 <= score < 5 → draw"""
        war = War(id="draw_war", name="Draw War", war_type=WarType.FOREIGN,
                  strength=14, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 1
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # dice=7, martial=6, leg=2, bias=0 → total=15, enemy=14 → score=1 → draw
        result = combat_api._compute_combat_result(war, self.state, 7, "attack")
        self.assertEqual(result["result"], "draw")

    def test_gui_compute_defeat_negative(self):
        """score < 0 → defeat"""
        result = combat_api._compute_combat_result(self.war1, self.state, 2, "attack")
        # dice=2, martial=6, leg=4*2=8 → total=16, enemy=8 → score=8 → DETECTED: 8>5 so victory!
        # Need weaker setup
        war = War(id="defeat_war", name="Defeat War", war_type=WarType.FOREIGN,
                  strength=50, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # dice=2, martial=6, leg=0 → total=8, enemy=50 → score=-42 → defeat
        result = combat_api._compute_combat_result(war, self.state, 2, "attack")
        self.assertEqual(result["result"], "defeat")

    def test_gui_compute_disaster_roll(self):
        """disaster roll → disaster"""
        # war1 has disaster_numbers=[2,3], dice=2 → disaster
        result = combat_api._compute_combat_result(self.war1, self.state, 2, "attack")
        self.assertEqual(result["result"], "disaster")
        self.assertFalse(result["triumph"])
        self.assertGreater(result["losses"], 0)

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 2: 战斗力公式 = legions_assigned * 2
    # ════════════════════════════════════════════════════════════════════
    def test_gui_legion_power_formula(self):
        """legion_power = legions_assigned * 2"""
        result = combat_api._compute_combat_result(self.war1, self.state, 7, "attack")
        self.assertEqual(result["legion_power"], 8)  # 4 * 2
        self.assertEqual(result["commander_martial"], 6)

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 3: do_combat_action 分类（小写命名）
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_gui_action_result_triumph_lowercase(self, mock_randint):
        """GUI 结果使用小写命名: triumph/victory/draw/defeat/disaster"""
        mock_randint.return_value = 10
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "triumph")

    @patch.object(combat_api.random, "randint")
    def test_gui_action_result_disaster_lowercase(self, mock_randint):
        mock_randint.return_value = 2
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "disaster")

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 4: confirm_battle_result 与 advance_combat 流程
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_gui_full_cycle(self, mock_randint):
        """GUI select → action → confirm → advance 完整流程"""
        mock_randint.return_value = 8

        # Step 1: Select
        r1 = combat_api.select_war(self.state, "player_opt", "test_war_1")
        self.assertTrue(r1["success"])

        # Step 2: Action
        r2 = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(r2["success"])

        # Step 3: Confirm
        r3 = combat_api.confirm_battle_result(self.state, "player_opt")
        self.assertTrue(r3["success"])
        self.assertIn("next_step", r3["data"])

        # Step 4: Advance
        r4 = combat_api.advance_combat(self.state, "player_opt")
        self.assertTrue(r4["success"])
        self.assertTrue(self.state.is_phase_executed("combat"))

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 5: 战斗结果包含 loot 分配字段
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_gui_battle_result_has_loot_fields(self, mock_randint):
        """GUI battle result → 包含 loot 分配字段"""
        mock_randint.return_value = 10
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        data = result["data"]
        self.assertIn("loot", data)
        self.assertIn("treasury_share", data)
        self.assertIn("commander_share", data)
        self.assertIn("faction_share", data)
        self.assertIn("soldier_share", data)

    # ════════════════════════════════════════════════════════════════════
    # GUI 特征 6: auto_resolve_combat (adapter 方法)
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_gui_adapter_auto_resolve(self, mock_randint):
        """GUI adapter.auto_resolve_combat 绕过校验 (auto=True)"""
        mock_randint.return_value = 8
        from src.ui.gui.api_adapter import GuiApiAdapter

        adapter = GuiApiAdapter(self.state)
        result = adapter.auto_resolve_combat("player_opt")
        self.assertIsInstance(result, dict)
        # Should have success or reasonable error
        self.assertIn("success", result)


if __name__ == "__main__":
    unittest.main()
