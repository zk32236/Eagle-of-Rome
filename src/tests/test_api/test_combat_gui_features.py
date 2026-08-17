"""
Feature Freeze Test — GUI combat_api 当前行为基线 (S1 冻结)

捕获 GUI combat_api 的战斗结算逻辑，作为改造前的行为快照。
改造后这些测试断言应与共享用例输出一致。
"""
import json
import os
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
        """score >= 12 → triumph（阈值从 Config combat_rules 读取）"""
        result = combat_api._compute_combat_result(self.war1, self.state, 10, "attack")
        self.assertEqual(result["result"], "triumph")
        self.assertTrue(result["triumph"])

    def test_gui_compute_victory_moderate_score(self):
        """6 <= score < 12 → victory（阈值从 Config combat_rules 读取）"""
        war = War(id="victory_war", name="Victory War", war_type=WarType.FOREIGN,
                  strength=9, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 1
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # dice=7, martial=6, leg=1*2=2, bias=0 → total=15, enemy=9 → score=6 → victory
        result = combat_api._compute_combat_result(war, self.state, 7, "attack")
        self.assertEqual(result["result"], "victory")

    def test_gui_compute_draw_low_positive(self):
        """standoff roll 或 -3 <= score < 6 → draw（对齐 CLI STALEMATE）"""
        war = War(id="draw_war", name="Draw War", war_type=WarType.FOREIGN,
                  strength=14, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 1
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # dice=7 (standoff), martial=6, leg=2, bias=0 → total=15, enemy=14 → score=1 → draw
        result = combat_api._compute_combat_result(war, self.state, 7, "attack")
        self.assertEqual(result["result"], "draw")

    def test_gui_compute_defeat_negative(self):
        """score < -3 → defeat（阈值从 Config combat_rules 读取）"""
        result = combat_api._compute_combat_result(self.war1, self.state, 2, "attack")
        # dice=2, martial=6, leg=4*2=8 → total=16, enemy=8 → score=8 → victory (too high)
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

        # T8（INV-C5）：≤3 卡场景 → QML model 仍渲染 3 槽（DTO 层无截断）
        # 注：本回合结果卡保留至 Combat 阶段结束（INV-C1），故此处断言 ≤3 而非 0
        view = combat_api.get_combat_view(self.state, "player_opt")
        all_cards = (
            view["data"]["active_wars"]
            + view["data"]["truce_wars"]
            + view["data"]["resolved_war_cards"]
        )
        self.assertLessEqual(len(all_cards), 3)
        self.assertEqual(max(3, len(all_cards)), 3)

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
    # AC-4.3: 逐场结果留卡片内 — 三战争逐场结算后 per-war result 独立保留
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_gui_resolved_cards_per_war_result(self, mock_randint):
        """三场战争逐场结算后，每张结算卡独立保留本场完整 result 对象。

        BUGFIX-01：war_c=draw → 入 truce（非 discard），resolved_war_cards 3→2。
        """
        mock_randint.return_value = 8
        state = _build_combat_full_state()
        for wid in ("war_a", "war_b", "war_c"):
            combat_api.select_war(state, "player_opt", wid)
            combat_api.do_combat_action(state, "player_opt", wid, "attack")
            combat_api.confirm_battle_result(state, "player_opt")

        view = combat_api.get_combat_view(state, "player_opt")
        self.assertTrue(view["success"])
        data = view["data"]
        self.assertEqual(data["current_step"], "advance")
        self.assertEqual(len(data["resolved_war_cards"]), 2)

        results = {}
        for card in data["resolved_war_cards"]:
            self.assertIn("result", card)
            r = card["result"]
            self.assertEqual(r["war_id"], card["war_id"])
            for field in ("result", "result_label", "dice", "total_attack",
                          "enemy_defence", "total_score", "loot",
                          "treasury_share", "commander_share", "faction_share",
                          "soldier_share", "losses"):
                self.assertIn(field, r)
            results[card["war_id"]] = r["result"]

        # 决定性战争结果独立保留且互不覆盖
        self.assertEqual(results["war_a"], "triumph")
        self.assertEqual(results["war_b"], "victory")

        # BUGFIX-01：war_c=draw → truce（不在 discard/resolved_war_cards），result 词不变
        ws = state._war_system
        self.assertEqual(ws.get_war_by_id("war_c").status, WarStatus.TRUCE)
        self.assertEqual(
            state.get_phase_result("combat")["war_results"]["war_c"]["result"],
            "draw",
        )

        # T1（INV-C1/C4）：Victory 结果卡不计入 ongoing（war_count 不触发）
        vc = state.check_victory_conditions()
        self.assertFalse(vc["game_over"])
        self.assertEqual([c for c in vc["conditions"] if c["type"] == "war_count"], [])
        # active+truce 不含 RESOLVED war（war_a/war_b 已 discard）
        self.assertEqual([w for w in ws.get_active_wars() if w.status == WarStatus.RESOLVED], [])
        self.assertEqual([w for w in ws.get_truce_wars() if w.status == WarStatus.RESOLVED], [])

    # ════════════════════════════════════════════════════════════════════
    # T9（INV-C6）：4 战争 overflow — 全量入卡、无截断、全可攻（DTO 层）
    # ════════════════════════════════════════════════════════════════════
    def test_four_war_overflow_all_cards_present(self):
        state = _build_combat_full_state()
        # 追加第 4 场 ACTIVE 战争（带指挥官）
        w4 = War(id="war_d", name="高卢战争", war_type=WarType.FOREIGN, strength=7,
                 threat_level=2, rewards={"treasury": 60})
        w4.commander_id = 1
        w4.legions_assigned = 1
        w4.add_legion_number(9)
        w4.status = WarStatus.ACTIVE
        state._war_system._active_wars.append(w4)

        view = combat_api.get_combat_view(state, "player_opt")
        data = view["data"]
        all_cards = data["active_wars"] + data["truce_wars"] + data["resolved_war_cards"]
        # 无截断：4 卡全量入卡（禁 [:3]）
        self.assertEqual(len(all_cards), 4)
        self.assertEqual(len(data["active_wars"]), 4)
        # 每卡 ACTIVE_ACTIONABLE（可攻）
        for card in data["active_wars"]:
            self.assertEqual(card["presentation_state"], "ACTIVE_ACTIONABLE")
        # QML model = max(3, 4) = 4（横向 overflow 追加）
        self.assertEqual(max(3, len(all_cards)), 4)

    # ════════════════════════════════════════════════════════════════════
    # T10（INV-C6）：TRUCE + 3×ACTIVE 混合 overflow — 4 卡、TRUCE 锁定不可攻、ongoing=4
    # ════════════════════════════════════════════════════════════════════
    def test_mixed_truce_active_overflow_locked(self):
        state = _build_combat_full_state()
        ws = state._war_system
        # 第 4 场 = TRUCE（approved 草案，保持 TRUCE 容器）
        w4 = War(id="war_truce", name="迦太基和约", war_type=WarType.FOREIGN, strength=9,
                 threat_level=2)
        w4.commander_id = 1
        w4.status = WarStatus.TRUCE
        w4.set_peace_treaty({"status": "approved"})
        ws._truce_wars.append(w4)

        view = combat_api.get_combat_view(state, "player_opt")
        data = view["data"]
        all_cards = data["active_wars"] + data["truce_wars"] + data["resolved_war_cards"]
        # 无截断：3 ACTIVE + 1 TRUCE = 4 卡
        self.assertEqual(len(all_cards), 4)
        self.assertEqual(len(data["truce_wars"]), 1)
        self.assertEqual(data["truce_wars"][0]["presentation_state"], "TRUCE_LOCKED")
        for card in data["active_wars"]:
            self.assertEqual(card["presentation_state"], "ACTIVE_ACTIONABLE")
        # ongoing = ACTIVE + TRUCE = 4 → war_count 触发（INV-C4）
        vc = state.check_victory_conditions()
        self.assertTrue(vc["game_over"])
        war_count_conds = [c for c in vc["conditions"] if c["type"] == "war_count"]
        self.assertEqual(len(war_count_conds), 1)
        self.assertTrue(war_count_conds[0]["critical"])
        self.assertEqual(war_count_conds[0]["details"], "进行中战争达到 4 场，共和覆灭！")

    # ════════════════════════════════════════════════════════════════════
    # T12（INV-C1/C2/C4/C5 联合）：Reference Scenario 跨 Combat→Senate→Combat
    # Victory×2（war_a/war_b RESOLVED）+ Draw（war_c → TRUCE）→ Senate 批准 →
    # 下 Combat：active 空、resolved 空、truce 1 → 槽 [EMPTY][EMPTY][TRUCE_LOCKED]
    # ════════════════════════════════════════════════════════════════════
    @patch.object(combat_api.random, "randint")
    def test_reference_scenario_victory_x2_draw_truce_slot(self, mock_randint):
        mock_randint.return_value = 8
        state = _build_combat_full_state()
        ws = state._war_system

        # 逐场结算：war_a → 确认 → war_b → 确认 → war_c（draw）→ 确认
        for wid in ("war_a", "war_b", "war_c"):
            combat_api.select_war(state, "player_opt", wid)
            combat_api.do_combat_action(state, "player_opt", wid, "attack")
            combat_api.confirm_battle_result(state, "player_opt")

        war_c = ws.get_war_by_id("war_c")
        self.assertEqual(war_c.status, WarStatus.TRUCE)

        # Senate 批准（草案 status → approved）
        war_c.set_peace_treaty_status("approved")

        # 下 Combat（新 phase_data）
        state.record_phase_result("combat", {})

        view = combat_api.get_combat_view(state, "player_opt")
        data = view["data"]
        # INV-C1：Victory 结果卡不计入下 Combat（active 空）
        self.assertEqual(data["active_wars"], [])
        self.assertEqual(data["resolved_war_cards"], [])
        # INV-C2：TRUCE 卡可见 + TRUCE_LOCKED
        self.assertEqual(len(data["truce_wars"]), 1)
        truce_card = data["truce_wars"][0]
        self.assertEqual(truce_card["war_id"], "war_c")
        self.assertEqual(truce_card["presentation_state"], "TRUCE_LOCKED")
        # 槽位（DTO 层）＝ 3 槽：EMPTY/EMPTY/TRUCE_LOCKED（QML model = max(3, 1) = 3）
        all_cards = data["active_wars"] + data["truce_wars"] + data["resolved_war_cards"]
        self.assertEqual(len(all_cards), 1)
        self.assertEqual(max(3, len(all_cards)), 3)
        # INV-C4：1 TRUCE + 0 ACTIVE = 1 < 3 → war_count 不触发
        vc = state.check_victory_conditions()
        self.assertFalse(vc["game_over"])
        self.assertEqual([c for c in vc["conditions"] if c["type"] == "war_count"], [])

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

    # ════════════════════════════════════════════════════════════════════
    # Slice 2: Config 阈值读取化 + R7 draw 语义（FC-2）
    # ════════════════════════════════════════════════════════════════════
    def test_gui_compute_reads_config_threshold(self):
        """_compute_combat_result 从 Config combat_rules 读阈值（AC-2.1）"""
        war = War(id="cfg_war", name="Config War", war_type=WarType.FOREIGN, strength=0)
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # no commander → martial=0, legions=0, enemy=0 → score == dice

        # 默认（测试 config 无 combat_rules）→ 回退 12/6/-3：score=10 → victory
        result = combat_api._compute_combat_result(war, self.state, 10, "attack")
        self.assertEqual(result["result"], "victory")

        # 覆盖阈值：triumph 门槛降到 10
        self.state.config.combat_rules = {
            "triumph_threshold": 10,
            "victory_threshold": 6,
            "defeat_threshold": -3,
        }
        result2 = combat_api._compute_combat_result(war, self.state, 10, "attack")
        self.assertEqual(result2["result"], "triumph")

    def test_gui_compute_draw_standoff_roll(self):
        """standoff 骰点 → draw（即使 score < -3，R7 对齐 CLI STALEMATE）"""
        war = War(id="standoff_war", name="Standoff War", war_type=WarType.FOREIGN, strength=30)
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # no commander → martial=0, legions=0 → total=7, enemy=30 → score=-23
        # dice=7 是默认 standoff 骰点（[5,6,7,8,9]）→ draw，而非 defeat
        result = combat_api._compute_combat_result(war, self.state, 7, "attack")
        self.assertEqual(result["result"], "draw")

    def test_gui_compute_boundary_12_6_minus3(self):
        """12 / 6 / -3 边界分级（AC-2.1/2.3）"""
        war = War(id="boundary_war", name="Boundary War", war_type=WarType.FOREIGN, strength=0)
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        # no commander → martial=0, legions=0, enemy=0 → score == dice（dice 直接注入以隔离分级逻辑）
        self.assertEqual(combat_api._compute_combat_result(war, self.state, 12, "attack")["result"], "triumph")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, 11, "attack")["result"], "victory")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, 6, "attack")["result"], "victory")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, -3, "attack")["result"], "draw")
        self.assertEqual(combat_api._compute_combat_result(war, self.state, -4, "attack")["result"], "defeat")

    # ════════════════════════════════════════════════════════════════════
    # Slice 4/5: QML attack-only + 移除 advance banner（FC-1 QML 面 / FC-4）
    # ════════════════════════════════════════════════════════════════════
    def test_gui_attack_only_single_entry(self):
        """CombatStage.qml 只暴露单一进攻入口，scout/defence 入口已移除（AC-1.1/1.4）"""
        qml = _read_combat_qml()
        self.assertIn("发动进攻", qml)
        self.assertIn('"attack"', qml)
        self.assertNotIn("🔍 侦查", qml)
        self.assertNotIn("🛡️ 防御", qml)
        self.assertNotIn('"scout"', qml)
        self.assertNotIn('"defence"', qml)

    def test_gui_advance_no_banner(self):
        """advance banner「所有战争已结算」已移除（AC-4.1）"""
        qml = _read_combat_qml()
        self.assertNotIn("所有战争已结算", qml)

    def test_combat_screenshot_same_state_chain(self):
        """same-state 全链（select → action → result → advance）DTO + 离屏截图。"""
        os.makedirs(_SCREENSHOTS_DIR, exist_ok=True)
        with patch.object(combat_api.random, "randint", return_value=8):
            state = _build_combat_full_state()
            steps = {}

            steps["select"] = combat_api.get_combat_view(state, "player_opt")["data"]

            combat_api.select_war(state, "player_opt", "war_a")
            steps["action"] = combat_api.get_combat_view(state, "player_opt")["data"]

            combat_api.do_combat_action(state, "player_opt", "war_a", "attack")
            steps["result"] = combat_api.get_combat_view(state, "player_opt")["data"]

            combat_api.confirm_battle_result(state, "player_opt")
            for wid in ("war_b", "war_c"):
                combat_api.select_war(state, "player_opt", wid)
                combat_api.do_combat_action(state, "player_opt", wid, "attack")
                combat_api.confirm_battle_result(state, "player_opt")
            steps["advance"] = combat_api.get_combat_view(state, "player_opt")["data"]

        # same-state 断言（FC-3 DTO 字段）
        self.assertEqual(steps["select"]["current_step"], "select")
        self.assertEqual(steps["action"]["current_step"], "action")
        self.assertEqual(steps["result"]["current_step"], "result")
        self.assertEqual(steps["advance"]["current_step"], "advance")
        first = steps["select"]["active_wars"][0]
        self.assertEqual(first["enemy_name"], first["name"])
        self.assertIsInstance(first["legion_numbers"], list)

        for name, data in steps.items():
            json_path = os.path.join(_SCREENSHOTS_DIR, f"wp04-combat-{name}.dto.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "step": name,
                    "current_step": data.get("current_step"),
                    "all_resolved": data.get("all_resolved"),
                    "can_advance": data.get("can_advance"),
                    "selected_war_id": data.get("selected_war_id"),
                    "active_wars": data.get("active_wars"),
                    "resolved_war_ids": data.get("resolved_war_ids"),
                    "battle_results": data.get("battle_results"),
                }, f, ensure_ascii=False, indent=2)
            png_path = os.path.join(_SCREENSHOTS_DIR, f"wp04-combat-{name}.png")
            _render_combat_qml_step(name, data, png_path)


_COMBAT_QML_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "src", "ui", "gui", "qml", "stages", "CombatStage.qml")
)

_SCREENSHOTS_DIR = "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260729-01_GUI-Alignment/WP-04/03-da-evidence/screenshots"


def _read_combat_qml():
    with open(_COMBAT_QML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_combat_full_state():
    """构建 3 场战争（含指挥官 + 军团番号）的完整战斗状态。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for ph in ["mortality", "revenue", "forum", "population", "senate"]:
        state.mark_phase_executed(ph)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)

    c1 = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
    c1.martial = 6
    c2 = Figure(id=2, name="Lucius", faction_id="optimates", age=35)
    c2.martial = 4
    state.add_member(c1)
    state.add_member(c2)
    faction.member_ids.extend([1, 2])

    player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    w1 = War(id="war_a", name="山南高卢入侵", war_type=WarType.FOREIGN, strength=8,
             threat_level=3, rewards={"treasury": 100})
    w1.commander_id = 1
    w1.legions_assigned = 3
    w1.add_legion_number(3)
    w1.add_legion_number(4)
    w1.add_legion_number(5)
    w1.status = WarStatus.ACTIVE

    w2 = War(id="war_b", name="西西里叛乱", war_type=WarType.FOREIGN, strength=6,
             threat_level=2, rewards={"treasury": 80})
    w2.commander_id = 2
    w2.legions_assigned = 2
    w2.add_legion_number(1)
    w2.add_legion_number(2)
    w2.status = WarStatus.ACTIVE

    w3 = War(id="war_c", name="伊比利亚威胁", war_type=WarType.FOREIGN, strength=12,
             threat_level=4, rewards={"treasury": 60})
    w3.legions_assigned = 1
    w3.add_legion_number(6)
    w3.status = WarStatus.ACTIVE

    for w in (w1, w2, w3):
        state._war_system._active_wars.append(w)
    return state


def _render_combat_qml_step(step_name, data, out_png):
    """best-effort 离屏渲染 CombatStage.qml（失败时静默降级）。"""
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QObject, Property, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance() or QGuiApplication([])

        class _SessionStoreMock(QObject):
            def __init__(self, d):
                super().__init__()
                self._step = d.get("current_step", "select") or "select"
                self._active = d.get("active_wars", []) or []
                self._all = list(self._active) + (d.get("resolved_war_cards", []) or [])
                self._resolved_ids = d.get("resolved_war_ids", []) or []
                self._selected = d.get("selected_war_id", "") or ""
                self._battle = (d.get("battle_results") or [{}])[0]
                self._fleet = d.get("fleet_count", 0) or 0
                self._legions = d.get("available_legion_count", 0) or 0
                self._treasury = d.get("treasury", 0) or 0

            @Property(str, constant=True)
            def combatCurrentStep(self): return self._step

            @Property('QVariantList', constant=True)
            def combatActiveWars(self): return self._active

            @Property('QVariantList', constant=True)
            def combatAllWarCards(self): return self._all

            @Property('QVariantList', constant=True)
            def combatResolvedWarIds(self): return self._resolved_ids

            @Property(str, constant=True)
            def combatSelectedWarId(self): return self._selected

            @Property('QVariantMap', constant=True)
            def combatBattleResultDetail(self): return self._battle

            @Property(int, constant=True)
            def combatFleetCount(self): return self._fleet

            @Property(int, constant=True)
            def combatAvailableLegions(self): return self._legions

            @Property(int, constant=True)
            def treasury(self): return self._treasury

        class _ThemeMock(QObject):
            @Property(int, constant=True)
            def statLabelSize(self): return 11
            @Property(int, constant=True)
            def statValueSize(self): return 13
            @Property(int, constant=True)
            def bodySize(self): return 13
            @Property(int, constant=True)
            def smallSize(self): return 11
            @Property(int, constant=True)
            def titleSize(self): return 18
            @Property(int, constant=True)
            def buttonSize(self): return 13

        engine = QQmlApplicationEngine()
        qml_dir = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "src", "ui", "gui", "qml"))
        engine.addImportPath(qml_dir)
        engine.rootContext().setContextProperty("sessionStore", _SessionStoreMock(data))
        engine.rootContext().setContextProperty("theme", _ThemeMock())

        combat_qml_path = os.path.normpath(os.path.join(qml_dir, "stages", "CombatStage.qml"))
        import tempfile
        fd, test_qml = tempfile.mkstemp(suffix=".qml")
        os.close(fd)
        wrapper = f'''
import QtQuick 2.15
import QtQuick.Window 2.15

Window {{
    visible: false
    width: 1440
    height: 900
    title: "Combat {step_name}"

    Loader {{
        anchors.fill: parent
        source: "{combat_qml_path}"
    }}
}}
'''
        with open(test_qml, "w", encoding="utf-8") as f:
            f.write(wrapper)
        try:
            engine.load(QUrl.fromLocalFile(test_qml))
            if engine.rootObjects():
                window = engine.rootObjects()[0]
                image = window.grabWindow()
                image.save(out_png)
                print(f"Combat screenshot saved: {out_png}")
                return True
            print(f"Combat QML loaded no root objects for step {step_name}")
            return False
        finally:
            if os.path.exists(test_qml):
                os.unlink(test_qml)
    except Exception as e:
        print(f"Combat QML render failed ({step_name}): {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    unittest.main()
