# src/tests/test_api/test_wpgr4_s2_naval_readiness.py
"""WP-G-R4 S2（R4-G-02，SA v1.7 §8.1 B，T-R4-04）— Naval readiness ≠ Naval DEFEAT。

参数化零 ready / 仅非 ready 状态；force DEFEAT/TRIUMPH 不能穿透；全部 battle 副作用
diff=0；API False+code；view 不可攻但可显式 advance；auto 不计 battle（unavailable 名单）。
权威：SA-Design-WP-G-R4 v1.7 §3.1/§3.3/§3.4；R4 任务包 v1.1 §6。
"""
import unittest
from unittest import mock

from src.api import combat_api
from src.core.entities.war import WarStatus
from src.core.entities.fleet import FleetStatus
from src.tests.fixtures import wpgr4_fixtures as F


class TestT04NoReadyFleetIsNotABattle(unittest.TestCase):

    def _baseline(self, naval_force="", land_force="", ready_override=None):
        ctx = F.build_fix02(naval_force=naval_force, land_force=land_force,
                            ready_override=ready_override)
        state, war = ctx["state"], ctx["war"]
        ms = state.get_military_system()
        return state, war, ms, ctx

    def test_t04_zero_ready_returns_naval_not_ready_zero_side_effects(self):
        for naval_force in ("", "DEFEAT", "TRIUMPH"):
            state, war, ms, ctx = self._baseline(naval_force=naval_force)
            legion_before = list(war.legion_numbers)
            duration_before = war.duration
            with mock.patch("src.api.combat_api.random.randint") as dice:
                result = combat_api.do_combat_action(state, F.P1, war.id, "attack")
            dice.assert_not_called()  # 零 Land 骰
            self.assertFalse(result["success"])
            self.assertEqual(result["data"]["code"], "NAVAL_NOT_READY",
                             f"force={naval_force} 不能穿透 readiness")
            self.assertEqual(war.duration, duration_before, "零 duration 增量")
            self.assertEqual(list(war.legion_numbers), legion_before, "零征召/伤亡")
            self.assertEqual(state.get_phase_result("combat"), None, "零 pending/war_results 写入")
            self.assertEqual(state.is_phase_executed("combat"), False)
            self.assertFalse(war.sea_control_acquired)
            self.assertEqual(len(war.assigned_fleet_ids), 0)
            # 结构性非战 envelope（无 battle 数值/损失）
            envelope = result["data"]["attack_result"]
            self.assertEqual(envelope["result"], "NAVAL_NOT_READY")
            self.assertFalse(envelope["naval"]["executed"])
            self.assertFalse(envelope["land"]["executed"])
            self.assertNotIn("dice", envelope.get("land", {}))
            self.assertNotIn("roman_losses", envelope["naval"])

    def test_t04_only_non_ready_statuses_are_not_ready(self):
        for status in ("building", "destroyed", "disbanded", "available", "missing"):
            state, war, ms, ctx = self._baseline(naval_force="TRIUMPH", ready_override=status)
            result = combat_api.do_combat_action(state, F.P1, war.id, "attack")
            self.assertFalse(result["success"], f"{status} 不 ready")
            self.assertEqual(result["data"]["code"], "NAVAL_NOT_READY")

    def test_t04_view_gate_and_explicit_advance(self):
        state, war, ms, ctx = self._baseline(ready_override=None)
        view = combat_api.get_combat_view(state, F.P1)
        self.assertTrue(view["success"])
        slots = view["data"]["war_slots"] or []
        cards = {c["war_id"]: c for c in slots if c}
        card = cards[war.id]
        self.assertFalse(card["attack_available"])
        self.assertEqual(card["attack_disabled_code"], "NAVAL_NOT_READY")
        self.assertTrue(card["attack_disabled_reason"])
        # NOT_READY 战争不阻塞显式 advance（无可执行战斗）
        adv = combat_api.advance_combat(state, F.P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("combat"))

    def test_t04_auto_resolve_unavailable_list_not_battle(self):
        state, war, ms, ctx = self._baseline(ready_override=None)
        auto = combat_api.auto_resolve_combat(state, F.P1)
        self.assertTrue(auto["success"])
        data = auto["data"]
        self.assertEqual(data["battles"], [])
        self.assertEqual(data["wars_resolved"], 0)
        unavail = {u["war_id"]: u for u in data["unavailable_wars"]}
        self.assertIn(war.id, unavail)
        self.assertEqual(unavail[war.id]["code"], "NAVAL_NOT_READY")
        # unavailable 不进入 resolved/battled
        self.assertNotIn(war.id, (state.get_phase_result("combat") or {}).get("resolved_wars", []))

    def test_t04_fleet_ready_retry_after_not_ready_works_once(self):
        """原 NOT_READY 未 battled；舰队就绪后（未 advance）真实新 attack 可执行一次。"""
        state, war, ms, ctx = self._baseline(naval_force="VICTORY", land_force="DEFEAT",
                                            ready_override=None)
        self.assertFalse(combat_api.do_combat_action(state, F.P1, war.id, "attack")["success"])
        # 真实 ready 舰队就绪（canonical assign）
        from src.tests.fixtures import wpgr4_fixtures as Fixtures
        Fixtures.add_ready_fleets(state, war, count=1, start_number=1)
        result = combat_api.do_combat_action(state, F.P1, war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        data = result["data"]
        self.assertTrue(data.get("naval", {}).get("sea_control_acquired") is not False)
        # 已 battled：重复 attack → 拒绝（不二次结算）
        repeat = combat_api.do_combat_action(state, F.P1, war.id, "attack")
        self.assertFalse(repeat["success"])


if __name__ == "__main__":
    unittest.main()
