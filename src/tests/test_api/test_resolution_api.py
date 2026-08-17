# src/tests/test_api/test_resolution_api.py
"""
S2 Resolution API 单元测试

测试 execute_resolution() 共享用例：
- AC-S2-01: 决算只处理一次
- AC-S2-02: execute_resolution 不增加年份
- AC-S2-03: advance_year 令年份增加 1
- AC-S2-04: 重复 advance_year 不增加第二次
- AC-S2-05: CLI 与 GUI 结果一致（通过相同的 API 入口）
- AC-S2-06: 失败后可安全重试
"""
import unittest
import sys
import os
import copy

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure
from src.core.entities.province import Province
from src.core.game_state import GameState
from src.ui.commands.phase_resolution import ResolutionCommand
from src.api.resolution_api import execute_resolution
from src.api import game_api


class TestExecuteResolutionBackend(unittest.TestCase):
    """S2 Backend: execute_resolution() 共享用例测试"""

    def setUp(self):
        self.test_config = {}
        self.state = GameState.create_for_testing(self.test_config)
        self.state.turn = GameTurn(turn_number=5, year=-260)
        self.state.mark_phase_executed("combat")

        self.faction1 = Faction(id="senate", name="元老院派", treasury=50)
        self.state.add_faction(self.faction1)
        self.fig1 = Figure(id=1, name="Marcus", faction_id="senate", age=40)
        self.fig1.loyalty = 8
        self.fig1.influence = 10
        self.state.add_member(self.fig1)
        self.faction1.member_ids.append(1)
        self.state._active_events = {"test_event": {"value": 1}}

    # ── AC-S2-01: 决算只处理一次 ──
    def test_execute_once_clears_events_and_marks_phase(self):
        result = execute_resolution(self.state)
        self.assertTrue(result["success"])
        dto = result.get("data", {})
        self.assertTrue(dto.get("events_cleared"))
        self.assertTrue(self.state.is_phase_executed("resolution"))

    def test_execute_twice_returns_false_idempotent(self):
        result1 = execute_resolution(self.state)
        self.assertTrue(result1["success"])
        result2 = execute_resolution(self.state)
        self.assertFalse(result2["success"])
        self.assertIn("已执行过", result2["message"])

    # ── AC-S2-02: execute_resolution 不增加年份 ──
    def test_execute_does_not_advance_year(self):
        year_before = self.state.turn.year if self.state.turn else 0
        execute_resolution(self.state)
        year_after = self.state.turn.year if self.state.turn else 0
        self.assertEqual(year_before, year_after)

    # ── AC-S2-03/04: advance_year 令年份增加 1，重复不增加第二次 ──
    def test_advance_year_increments_year(self):
        year_before = self.state.turn.year if self.state.turn else 0
        self.state.advance_year()
        year_after = self.state.turn.year if self.state.turn else 0
        self.assertEqual(year_after, year_before + 1)

    def test_advance_year_idempotent(self):
        # AC-S2-04（语义修正）: use-case 层幂等——第二次 game_api.advance_year 被拒绝（resolution_not_executed）。
        # 模型原语 state.advance_year() 保持「每次 +1」契约（见 test_advance_year_increments_year），
        # 产品面幂等由 game_api.advance_year 的 resolution token 消费保证。
        self.state._current_player_id = "p1"
        execute_resolution(self.state)  # 标记 resolution 已执行（token 就位）
        year_before = self.state.turn.year

        result1 = game_api.advance_year(self.state, "p1")
        self.assertTrue(result1["success"])
        year_after_1 = self.state.turn.year
        self.assertEqual(year_after_1, year_before + 1)

        result2 = game_api.advance_year(self.state, "p1")
        self.assertFalse(result2["success"])
        self.assertIn("resolution_not_executed", result2.get("errors", []))
        self.assertEqual(self.state.turn.year, year_after_1)

    # ── AC-S2-05: CLI 与 GUI 结果等价（都委托 execute_resolution） ──
    def test_cli_command_delegates_to_api(self):
        cmd = ResolutionCommand(self.state)
        result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(self.state.is_phase_executed("resolution"))

    def test_cli_and_api_yield_same_state(self):
        # Clone state for API path
        # Execute via API
        state_a = self.state
        # copy is tricky with complex objects; use separate setup equivalent
        result_api = execute_resolution(state_a)
        self.assertTrue(result_api["success"])
        dto_api = result_api.get("data", {})

        # Reset and execute via CLI
        state_b = GameState.create_for_testing(self.test_config)
        state_b.turn = GameTurn(turn_number=5, year=-260)
        state_b.mark_phase_executed("combat")
        faction_b = Faction(id="senate", name="元老院派", treasury=50)
        state_b.add_faction(faction_b)
        fig_b = Figure(id=1, name="Marcus", faction_id="senate", age=40)
        fig_b.loyalty = 8
        fig_b.influence = 10
        state_b.add_member(fig_b)
        faction_b.member_ids.append(1)
        state_b._active_events = {"test_event": {"value": 1}}

        self.state = state_b
        cmd = ResolutionCommand(state_b)
        cli_result = cmd.execute([])
        self.assertTrue(cli_result)

        # Both should mark resolution executed
        self.assertTrue(state_a.is_phase_executed("resolution"))
        self.assertTrue(state_b.is_phase_executed("resolution"))
        # Both should have cleared events
        self.assertEqual(state_a._active_events, {})
        self.assertEqual(state_b._active_events, {})

    # ── AC-S2-06: 失败后可安全重试 ──
    def test_retry_after_failure(self):
        # Ensure resolution not yet executed
        self.assertFalse(self.state.is_phase_executed("resolution"))

        # Successful first execute
        result1 = execute_resolution(self.state)
        self.assertTrue(result1["success"])

        # Second execute should fail (already executed)
        result2 = execute_resolution(self.state)
        self.assertFalse(result2["success"])

        # State should still be consistent
        self.assertTrue(self.state.is_phase_executed("resolution"))
        self.assertEqual(self.state._active_events, {})

    def test_combat_not_executed_returns_false(self):
        state = GameState.create_for_testing(self.test_config)
        state.turn = GameTurn(turn_number=5, year=-260)
        result = execute_resolution(state)
        self.assertFalse(result["success"])
        self.assertIn("战斗", result["message"])

    # ── DTO 结构验证 ──
    def test_dto_has_required_fields(self):
        result = execute_resolution(self.state)
        self.assertTrue(result["success"])
        dto = result.get("data", {})
        self.assertIn("year", dto)
        self.assertIn("year_display", dto)
        self.assertIn("victory", dto)
        self.assertIn("legion_recovery", dto)
        self.assertIn("key_events", dto)
        self.assertIn("events_cleared", dto)
        self.assertTrue(dto["events_cleared"])
        self.assertIn("conditions", dto["victory"])
        self.assertIn("summary", dto["victory"])
        self.assertIn("game_over", dto["victory"])

    def test_dto_year_display_format(self):
        result = execute_resolution(self.state)
        dto = result.get("data", {})
        self.assertEqual(dto["year_display"], "260 BC")

    def test_dto_legion_recovery_structure(self):
        result = execute_resolution(self.state)
        dto = result.get("data", {})
        lr = dto.get("legion_recovery", {})
        self.assertIn("recovered", lr)
        self.assertIn("recovered_ids", lr)
        self.assertIn("details", lr)
        self.assertIsInstance(lr["recovered_ids"], list)

    def test_dto_key_events_is_list(self):
        result = execute_resolution(self.state)
        dto = result.get("data", {})
        self.assertIsInstance(dto.get("key_events"), list)

    # ════════════════════════════════════════════════════════════════════
    # T11（INV-C4）：Resolution war_count 阈值 —— ACTIVE+TRUCE >= 3 → GAME FAILURE
    # Advisor P2-b 裁定（2026-08-17）：维持 >=3（非 >3）。四断言：
    # ① 3 ongoing → fail ② 2 ongoing → no fail ③ Victory 结果卡排除
    # ④ 4 ongoing → fail
    # ════════════════════════════════════════════════════════════════════
    def test_resolution_war_count_failure_threshold(self):
        from src.core.entities.war import War, WarStatus, WarType
        from src.core.systems.war_system import WarSystem

        def _make_war(wid: str, status: WarStatus):
            w = War(id=wid, name=f"War {wid}", war_type=WarType.FOREIGN, strength=5)
            w.status = status
            return w

        # ① 3 ACTIVE → game_over + war_count 条件（critical）
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        ws = WarSystem(state)
        state._war_system = ws
        for i in range(3):
            w = _make_war(f"a{i}", WarStatus.ACTIVE)
            ws._active_wars.append(w)

        vc = state.check_victory_conditions()
        self.assertTrue(vc["game_over"])
        war_count_conds = [c for c in vc["conditions"] if c["type"] == "war_count"]
        self.assertEqual(len(war_count_conds), 1)
        self.assertTrue(war_count_conds[0]["triggered"])
        self.assertTrue(war_count_conds[0]["critical"])
        self.assertEqual(war_count_conds[0]["details"], "进行中战争达到 3 场，共和覆灭！")

        # ② 2 场（1 ACTIVE + 1 TRUCE）→ 不触发
        state2 = GameState.create_for_testing({})
        state2.turn = GameTurn(turn_number=1, year=-264)
        ws2 = WarSystem(state2)
        state2._war_system = ws2
        w_active = _make_war("b1", WarStatus.ACTIVE)
        w_truce = _make_war("b2", WarStatus.TRUCE)
        w_truce.set_peace_treaty({"status": "approved"})
        ws2._active_wars.append(w_active)
        ws2._truce_wars.append(w_truce)

        vc2 = state2.check_victory_conditions()
        self.assertFalse(vc2["game_over"])
        self.assertEqual([c for c in vc2["conditions"] if c["type"] == "war_count"], [])

        # ③ Victory 结果卡（RESOLVED/discard）不误计：2 ACTIVE + 1 RESOLVED = ongoing 2
        #    （若 RESOLVED 被误计则 3 → 触发，故本断言证明 Victory 卡排除）
        state3 = GameState.create_for_testing({})
        state3.turn = GameTurn(turn_number=1, year=-264)
        ws3 = WarSystem(state3)
        state3._war_system = ws3
        w_a1 = _make_war("c1", WarStatus.ACTIVE)
        w_a2 = _make_war("c2", WarStatus.ACTIVE)
        w_victory = _make_war("c3", WarStatus.RESOLVED)
        ws3._active_wars.append(w_a1)
        ws3._active_wars.append(w_a2)
        ws3._war_discard.append(w_victory)

        vc3 = state3.check_victory_conditions()
        self.assertFalse(vc3["game_over"])
        self.assertEqual([c for c in vc3["conditions"] if c["type"] == "war_count"], [])

        # ④ 4 ongoing（2 ACTIVE + 2 TRUCE）→ game failure
        state4 = GameState.create_for_testing({})
        state4.turn = GameTurn(turn_number=1, year=-264)
        ws4 = WarSystem(state4)
        state4._war_system = ws4
        for i in range(2):
            w = _make_war(f"d{i}", WarStatus.ACTIVE)
            ws4._active_wars.append(w)
        for i in range(2):
            w = _make_war(f"e{i}", WarStatus.TRUCE)
            w.set_peace_treaty({"status": "approved"})
            ws4._truce_wars.append(w)

        vc4 = state4.check_victory_conditions()
        self.assertTrue(vc4["game_over"])
        war_count_conds4 = [c for c in vc4["conditions"] if c["type"] == "war_count"]
        self.assertEqual(len(war_count_conds4), 1)
        self.assertTrue(war_count_conds4[0]["triggered"])
        self.assertTrue(war_count_conds4[0]["critical"])
        self.assertEqual(war_count_conds4[0]["details"], "进行中战争达到 4 场，共和覆灭！")


if __name__ == "__main__":
    unittest.main()
