"""
Combat API 测试
"""
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api


class TestCombatAPI(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("mortality")
        self.state.mark_phase_executed("revenue")
        self.state.mark_phase_executed("forum")
        self.state.mark_phase_executed("population")
        self.state.mark_phase_executed("senate")
        self.state._treasury = 500

        # 初始化系统
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        # 创建派系
        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction1)

        # 创建指挥官
        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.commander.influence = 50
        self.state.add_member(self.commander)
        self.faction1.member_ids.append(1)

        # 创建无指挥官人物
        self.figure2 = Figure(id=2, name="Lucius", faction_id="optimates", age=35)
        self.figure2.martial = 3
        self.figure2.influence = 30
        self.state.add_member(self.figure2)
        self.faction1.member_ids.append(2)

        # 创建玩家
        self.player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)

        # 创建测试战争
        self.war1 = War(
            id="test_war_1",
            name="Test War 1",
            war_type=WarType.FOREIGN,
            strength=8,
            threat_level=3,
            rewards={"treasury": 100},
            disaster_numbers=[2, 3],
        )
        self.war1.commander_id = 1
        self.war1.legions_assigned = 4
        self.war1.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war1)

        # 第二场战争（无指挥官）
        self.war2 = War(
            id="test_war_2",
            name="Test War 2",
            war_type=WarType.FOREIGN,
            strength=5,
            threat_level=1,
            rewards={"treasury": 50},
            disaster_numbers=[2, 3],
        )
        self.war2.legions_assigned = 2
        self.war2.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war2)

        self.state.set_current_player("player_opt")

    # ════════════════════════════════════════════════════════════════════
    # Test 1: get_combat_view with None state
    # ════════════════════════════════════════════════════════════════════
    def test_get_combat_view_no_state(self):
        result = combat_api.get_combat_view(None, "player_opt")
        self.assertFalse(result["success"])

    # ════════════════════════════════════════════════════════════════════
    # Test 2: get_combat_view with no active wars
    # ════════════════════════════════════════════════════════════════════
    def test_get_combat_view_no_active_wars(self):
        self.state._war_system._active_wars.clear()
        result = combat_api.get_combat_view(self.state, "player_opt")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["active_wars"], [])
        self.assertEqual(data["current_step"], "advance")

    # ════════════════════════════════════════════════════════════════════
    # Test 3: get_combat_view with active wars
    # ════════════════════════════════════════════════════════════════════
    def test_get_combat_view_with_active_wars(self):
        result = combat_api.get_combat_view(self.state, "player_opt")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["phase_id"], "combat")
        self.assertEqual(len(data["active_wars"]), 2)
        self.assertEqual(data["current_step"], "select")
        # Verify war card fields
        first_war = data["active_wars"][0]
        self.assertEqual(first_war["war_id"], "test_war_1")
        self.assertEqual(first_war["name"], "Test War 1")
        self.assertTrue(first_war["has_commander"])
        self.assertEqual(first_war["commander_name"], "Marcus")
        self.assertEqual(first_war["commander_martial"], 6)
        self.assertEqual(first_war["legion_count"], 4)
        self.assertEqual(first_war["total_power"], 14)  # 6 (martial) + 4*2 (legions)
        self.assertEqual(first_war["enemy_power"], 8)  # war.strength

        # Verify war card without commander
        second_war = data["active_wars"][1]
        self.assertEqual(second_war["war_id"], "test_war_2")
        self.assertFalse(second_war["has_commander"])
        self.assertEqual(second_war["commander_name"], "")
        self.assertEqual(second_war["commander_martial"], 0)
        self.assertEqual(second_war["total_power"], 4)  # 0 + 2*2

    # ════════════════════════════════════════════════════════════════════
    # Test 4: select_war
    # ════════════════════════════════════════════════════════════════════
    def test_select_war(self):
        result = combat_api.select_war(self.state, "player_opt", "test_war_1")
        self.assertTrue(result["success"])
        # Verify phase data updated
        phase_data = self.state.get_phase_result("combat")
        self.assertIsNotNone(phase_data)
        if isinstance(phase_data, dict):
            self.assertEqual(phase_data.get("selected_war_id"), "test_war_1")

        # View should show step "action" now
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "action")
        self.assertEqual(view["data"]["selected_war_id"], "test_war_1")

    # ════════════════════════════════════════════════════════════════════
    # Test 5: do_combat_action - attack with mock high dice (triumph)
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_do_combat_attack_triumph(self, mock_randint):
        mock_randint.return_value = 10  # High dice for triumph
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["result"], "triumph")
        self.assertGreaterEqual(data["total_score"], 10)
        # Triumph should have bonus loot
        self.assertGreater(data["loot"], 0)
        self.assertTrue(data["triumph"])

    # ════════════════════════════════════════════════════════════════════
    # Test 6: do_combat_action - disaster roll
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_do_combat_attack_disaster(self, mock_randint):
        mock_randint.return_value = 2  # Low dice -> disaster
        war1 = self.state._war_system.get_war_by_id("test_war_1")
        war1._disaster_numbers = [2, 3]
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["result"], "disaster")
        self.assertFalse(data["triumph"])
        # Disaster should have losses
        self.assertGreater(data["losses"], 0)

    # ════════════════════════════════════════════════════════════════════
    # Test 7: do_combat_action - defeat (low roll + low power)
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_do_combat_attack_defeat(self, mock_randint):
        mock_randint.return_value = 3  # Low dice

        # Create a war with very high enemy strength — impossible to beat
        war1 = War(
            id="defeat_war",
            name="Defeat War",
            war_type=WarType.FOREIGN,
            strength=50,  # Very high: dice(3) + martial(0) + legions(0) = 3 < 50
            disaster_numbers=[2],  # 3 is not a disaster roll
        )
        war1.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war1)

        combat_api.select_war(self.state, "player_opt", "defeat_war")
        result = combat_api.do_combat_action(self.state, "player_opt", "defeat_war", "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "defeat")

    # ════════════════════════════════════════════════════════════════════
    # Test 8: do_combat_action - scout
    # ════════════════════════════════════════════════════════════════════
    def test_do_combat_scout(self):
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "scout")
        self.assertTrue(result["success"])
        data = result["data"]
        # Scout should return a result DTO (average dice=7)
        self.assertIn("result", data)
        self.assertIn("dice", data)
        self.assertEqual(data["dice"], 7)

    # ════════════════════════════════════════════════════════════════════
    # Test 9: do_combat_action - defence
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_do_combat_defence(self, mock_randint):
        mock_randint.return_value = 7
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "defence")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIn("result", data)
        # Defence gives +2 bonus
        self.assertGreaterEqual(data["total_attack"], 6 + 4 * 2 + 7 + 2)  # martial + legions + dice + bias

    # ════════════════════════════════════════════════════════════════════
    # Test 10: confirm_battle_result - more wars remain
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_confirm_battle_result_more_wars(self, mock_randint):
        mock_randint.return_value = 7
        # Select and action on war1
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")

        # Confirm result - should return to "select" since war2 remains
        result = combat_api.confirm_battle_result(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["all_resolved"])
        self.assertEqual(result["data"]["next_step"], "select")

        # View should show step "select"
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "select")

    # ════════════════════════════════════════════════════════════════════
    # Test 11: confirm_battle_result - all wars resolved
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_confirm_battle_result_all_resolved(self, mock_randint):
        mock_randint.return_value = 7
        # Resolve both wars
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")

        combat_api.select_war(self.state, "player_opt", "test_war_2")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_2", "attack")

        # Confirm result for war2 - all wars now resolved
        result = combat_api.confirm_battle_result(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["all_resolved"])
        self.assertEqual(result["data"]["next_step"], "advance")

    # ════════════════════════════════════════════════════════════════════
    # Test 12: advance_combat
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_advance_combat(self, mock_randint):
        mock_randint.return_value = 7
        # First resolve all wars
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")

        combat_api.select_war(self.state, "player_opt", "test_war_2")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_2", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")

        # Advance
        result = combat_api.advance_combat(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["next_phase_id"], "resolution")
        self.assertTrue(self.state.is_phase_executed("combat"))

    # ════════════════════════════════════════════════════════════════════
    # Test 13: full multi-war cycle
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_full_multi_war_cycle(self, mock_randint):
        mock_randint.return_value = 8
        # Step 1: Initial state - SELECT
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "select")
        self.assertEqual(len(view["data"]["active_wars"]), 2)

        # Step 2: Select war1 -> ACTION
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "action")

        # Step 3: Attack -> RESULT
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "result")
        self.assertEqual(len(view["data"]["battle_results"]), 1)

        # Step 4: Confirm war1 -> back to SELECT (war2 remains)
        combat_api.confirm_battle_result(self.state, "player_opt")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "select")

        # Step 5: Select war2 -> ACTION -> ATTACK -> RESULT
        combat_api.select_war(self.state, "player_opt", "test_war_2")
        self.assertEqual(
            combat_api.get_combat_view(self.state, "player_opt")["data"]["current_step"],
            "action",
        )
        combat_api.do_combat_action(self.state, "player_opt", "test_war_2", "attack")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "result")

        # Step 6: Confirm war2 -> ADVANCE
        combat_api.confirm_battle_result(self.state, "player_opt")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "advance")
        self.assertTrue(view["data"]["can_advance"])

        # Step 7: Advance -> Resolution
        result = combat_api.advance_combat(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertTrue(self.state.is_phase_executed("combat"))


if __name__ == "__main__":
    unittest.main()
