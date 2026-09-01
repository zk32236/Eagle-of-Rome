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
        self.war1.legions_assigned = 4  # 兼容 debug 镜像字段（N 件；GB S1 后不再作战力/伤亡权威）
        self.war1.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war1)
        # DEVIATION-DA-02（PM 已 ENDORSED 2026-08-25）：_war_card 计数/番号源 = 实时军团实体
        # 附着（ODR-A/B），生产路径附着真实实体（recruit_legion + assign_to_war）——镜像语义
        # = len(get_legions_for_battle(war.id))；断言意图保留（禁空洞化）。
        # WP-G GB（S1/S2，R-17）：战力/伤亡源 = live 实体（get_legions_for_battle +
        # apply_land_casualties）；legions_assigned 镜像仅兼容读，不再被战斗公式消费。
        ms = self.state._military_system
        for num in (1, 2, 3, 4):
            ok, _ = ms.recruit_legion(num)
            assert ok, f"recruit legion {num} failed"
        assigned, msg = ms.assign_to_war([1, 2, 3, 4], self.war1.id, 1)
        assert assigned == 4, msg

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
        self.war2.legions_assigned = 2  # 兼容 debug 镜像字段（N 件；GB S1 后不再作战斗权威）
        self.war2.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(self.war2)
        for num in (5, 6):
            ok, _ = ms.recruit_legion(num)
            assert ok, f"recruit legion {num} failed"
        assigned, msg = ms.assign_to_war([5, 6], self.war2.id, None)
        assert assigned == 2, msg

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
        # FC-3: DTO 提供 enemy_name（复用 War.name）+ legion_numbers 字段
        self.assertEqual(first_war["enemy_name"], "Test War 1")
        self.assertIn("legion_numbers", first_war)
        self.assertIsInstance(first_war["legion_numbers"], list)

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
        # V-2 增强（INV-C3）：disaster 后 war 保持 ACTIVE（不 resolve/discard）
        self.assertEqual(war1.status, WarStatus.ACTIVE)
        self.assertNotIn(war1, self.state._war_system._war_discard)

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
        # V-1 增强（INV-C3）：defeat 后 war 保持 ACTIVE（不 resolve/discard）
        self.assertEqual(war1.status, WarStatus.ACTIVE)
        self.assertNotIn(war1, self.state._war_system._war_discard)

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
        # FUNC-03 attack-only: scout retained for compatibility but marked DEPRECATED (B-19)
        self.assertTrue(data.get("deprecated"), "scout should be marked deprecated")

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
        # FUNC-03 attack-only: defence retained for compatibility but marked DEPRECATED (B-19)
        self.assertTrue(data.get("deprecated"), "defence should be marked deprecated")

    # ════════════════════════════════════════════════════════════════════
    # Test 10: confirm_battle_result - more wars remain
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_confirm_battle_result_more_wars(self, mock_randint):
        mock_randint.return_value = 7
        # Select and action on war1
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")

        # INV-C3/Δ6 语义（D-8 登记）：war2 仍 ACTIVE 但无指挥官 → 不阻塞 advance
        # （与 _skip_all_unassigned 一致；旧断言 all_resolved=False/select 编码修复前语义）
        result = combat_api.confirm_battle_result(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["all_resolved"])
        self.assertEqual(result["data"]["next_step"], "advance")

        # View should show step "advance"
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "advance")

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

        # Step 4: Confirm war1 -> ADVANCE（war2 无指挥官 → 不阻塞，INV-C3/Δ6，D-8 登记）
        combat_api.confirm_battle_result(self.state, "player_opt")
        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertEqual(view["data"]["current_step"], "advance")
        self.assertTrue(view["data"]["can_advance"])

        # Step 5: Advance -> Resolution（无指挥官 war 跳过，与 _skip_all_unassigned 一致）
        result = combat_api.advance_combat(self.state, "player_opt")
        self.assertTrue(result["success"])
        self.assertTrue(self.state.is_phase_executed("combat"))

    # ════════════════════════════════════════════════════════════════════
    # Test 14: attack idempotency (FC-1 AC-1.3) — double-attack must not re-resolve
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_do_combat_attack_idempotent(self, mock_randint):
        mock_randint.return_value = 8
        first = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertTrue(first["success"])
        # Second attack on the same war must be rejected (already resolved)
        second = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        self.assertFalse(second["success"])
        self.assertIn("已结算", second.get("message", ""))

    # ════════════════════════════════════════════════════════════════════
    # Test 15: unknown action rejected (FC-5 AC-5.2 failure path)
    # ════════════════════════════════════════════════════════════════════
    def test_do_combat_unknown_action_rejected(self):
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "surrender")
        self.assertFalse(result["success"])
        self.assertIn("Unknown action", result.get("message", ""))

    # ════════════════════════════════════════════════════════════════════
    # Test 16/17: scout/defence DEPRECATED (FC-1 AC-1.2 / B-19)
    # ════════════════════════════════════════════════════════════════════
    def test_do_combat_scout_deprecated(self):
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "scout")
        self.assertTrue(result["success"])
        self.assertTrue(result["data"].get("deprecated"), "scout action should be marked deprecated")

    @patch.object(combat_api.random, "randint")
    def test_do_combat_defence_deprecated(self, mock_randint):
        mock_randint.return_value = 7
        result = combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "defence")
        self.assertTrue(result["success"])
        self.assertTrue(result["data"].get("deprecated"), "defence action should be marked deprecated")

    # ════════════════════════════════════════════════════════════════════
    # Test 18: config missing combat_rules → fallback 12/6/-3（FC-2 AC-2.1 降级）
    # ════════════════════════════════════════════════════════════════════
    def test_combat_config_missing_fallback(self):
        # state created via create_for_testing({}) has no combat_rules key
        self.assertIsNone(self.state.config.get("combat_rules.triumph_threshold"))

        war = War(id="fb_war", name="Fallback War", war_type=WarType.FOREIGN, strength=0)
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # no commander → martial=0, legions=0, enemy=0 → score == dice
        self.assertEqual(combat_api._compute_combat_result(war, self.state, 12, "attack")["result"], "triumph")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, 11, "attack")["result"], "victory")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, -3, "attack")["result"], "draw")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, -4, "attack")["result"], "defeat")

    # ════════════════════════════════════════════════════════════════════
    # Test 19/20: Combat DTO enemy_name + legion_numbers（FC-3）
    # ════════════════════════════════════════════════════════════════════
    def test_war_card_has_enemy_name(self):
        """enemy_name == war.name（DTO 别名，不新增实体字段，AC-3.1）"""
        card = combat_api._war_card(self.war1, self.state)
        self.assertIn("enemy_name", card)
        self.assertEqual(card["enemy_name"], self.war1.name)

    def test_war_card_legion_numbers(self):
        """legion_numbers 字段存在且为 List[int]，= 所附实体番号（AC-3.3 / DEVIATION-DA-02）"""
        card = combat_api._war_card(self.war1, self.state)
        self.assertIn("legion_numbers", card)
        self.assertIsInstance(card["legion_numbers"], list)
        # 镜像语义 = 所附实体番号（setUp 生产路径附着 1,2,3,4；原 [3,4] 注入值按实体附着重定）。
        # 召回→重指派全链由 S2 test_truce_expiry_reassign_shows_new_numbers 覆盖（新鲜征召军团）。
        self.assertEqual(card["legion_numbers"], [1, 2, 3, 4])
        self.assertEqual(card["legion_count"], 4)
        self.assertEqual(card["total_power"], 14)  # 6 (martial) + 4*2

    # ════════════════════════════════════════════════════════════════════
    # Test 21: AC-4.3 逐场结果留卡片内 — per-war result DTO 穿透
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_resolved_war_cards_persist_per_war_result(self, mock_randint):
        """多场战争逐场结算后，每张结算卡独立保留本场完整 result 对象。"""
        mock_randint.return_value = 8

        # 逐场结算 war1 → 确认 → war2 → 确认
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_2", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")

        view = combat_api.get_combat_view(self.state, "player_opt")
        self.assertTrue(view["success"])
        data = view["data"]
        self.assertEqual(data["current_step"], "advance")

        cards = data["resolved_war_cards"]
        self.assertEqual(len(cards), 2)

        by_war_id = {c["war_id"]: c for c in cards}
        self.assertIn("test_war_1", by_war_id)
        self.assertIn("test_war_2", by_war_id)

        required_fields = (
            "result", "result_label", "dice", "total_attack",
            "enemy_defence", "total_score", "loot", "treasury_share",
            "commander_share", "faction_share", "soldier_share", "losses",
        )

        for war_id in ("test_war_1", "test_war_2"):
            card = by_war_id[war_id]
            self.assertIn("result", card, f"{war_id} card missing result")
            result = card["result"]
            self.assertEqual(result["war_id"], war_id)
            for field in required_fields:
                self.assertIn(field, result, f"{war_id} result missing {field}")

        # 独立保留：war1 与 war2 的结果互不覆盖，且分类正确
        self.assertEqual(by_war_id["test_war_1"]["result"]["result"], "triumph")
        self.assertEqual(by_war_id["test_war_2"]["result"]["result"], "victory")
        self.assertNotEqual(
            by_war_id["test_war_1"]["result"]["war_id"],
            by_war_id["test_war_2"]["result"]["war_id"],
        )

        # T1（INV-C1/C4）：Victory 结果卡不计入 ongoing（war_count 不触发；active+truce 不含 RESOLVED）
        vc = self.state.check_victory_conditions()
        self.assertFalse(vc["game_over"])
        self.assertEqual([c for c in vc["conditions"] if c["type"] == "war_count"], [])
        ws = self.state._war_system
        self.assertEqual(
            [w for w in ws.get_active_wars() if w.status == WarStatus.RESOLVED], []
        )
        self.assertEqual(
            [w for w in ws.get_truce_wars() if w.status == WarStatus.RESOLVED], []
        )

    # ════════════════════════════════════════════════════════════════════
    # T2（INV-C1）：Victory 下 Combat 重建 → 结果卡清除 + 槽 EMPTY
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_get_combat_view_next_turn_victory_cards_cleared(self, mock_randint):
        mock_randint.return_value = 8
        # 本回合：war1 胜利结算
        combat_api.select_war(self.state, "player_opt", "test_war_1")
        combat_api.do_combat_action(self.state, "player_opt", "test_war_1", "attack")
        combat_api.confirm_battle_result(self.state, "player_opt")

        # 清理 war2（无指挥官，避免干扰 EMPTY 槽断言）
        self.state._war_system._active_wars.remove(self.war2)

        # 下回合（新 Combat 阶段）：phase_data 重建（resolved_wars 清空）
        self.state.record_phase_result("combat", {})

        view = combat_api.get_combat_view(self.state, "player_opt")
        data = view["data"]
        # INV-C1：victory 已终止 war（RESOLVED+discard）不出现在下 Combat active_wars
        self.assertNotIn("test_war_1", [c["war_id"] for c in data["active_wars"]])
        # 本回合结果卡随新 phase_data 清除
        self.assertEqual(data["resolved_war_cards"], [])
        self.assertEqual(data["truce_wars"], [])
        # combatAllWarCards 空 → 槽位 EMPTY（QML model = max(3, 0) = 3 空槽）
        all_cards = data["active_wars"] + data["truce_wars"] + data["resolved_war_cards"]
        self.assertEqual(all_cards, [])
        self.assertEqual(max(3, len(all_cards)), 3)


if __name__ == "__main__":
    unittest.main()
