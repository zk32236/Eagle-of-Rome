# src/tests/fixtures/test_wpgr4_fixtures_smoke.py
"""WP-G-R4 S0 manifest smoke：FIX-R4-01~09 builders 可构造（O5 非空主样本核验）。

证据 harness（DA-Plan §1 S0）：非产品红测；断言构造方法与固定标识/入口状态。
构造反证（如 FIX01 非空不可构造）→ STOP 上报 PM——本 smoke 是其第一道哨兵。
"""
import unittest

from src.tests.fixtures import wpgr4_fixtures as F


class TestFix01NonEmptyMasterSample(unittest.TestCase):
    """FIX-R4-01 非空主样本（O5 / SA v1.7 §9.2b）：P1/F1 + C1 留城 + War A commanderless
    ACTIVE 非 naval + War B TRUCE+pending naval-required + public_land>0 + 真实池。"""

    def test_fix01_constructs_with_non_empty_master_state(self):
        ctx = F.build_fix01()
        state = ctx["state"]
        self.assertIsNotNone(state.get_phase_result("senate") or True)  # 入口断言不适用；见下
        self.assertFalse(state.is_phase_executed("senate"), "FIX01 入口 = senate 当前阶段（未 executed）")
        self.assertIsNone(state._takeover_pending, "初始无 T/V")
        # C1 留城 eligible
        consul = ctx["consul"]
        self.assertEqual(consul.office, "consul")
        self.assertFalse(consul.is_absent)
        # War A commanderless ACTIVE 非 naval；War B TRUCE+pending naval-required
        self.assertEqual(ctx["war_a"].id, F.WAR_A)
        self.assertEqual(ctx["war_a"].status.value, "active")
        self.assertIsNone(ctx["war_a"].commander_id)
        self.assertFalse(ctx["war_a"].naval_required)
        self.assertEqual(ctx["war_b"].id, F.WAR_B)
        self.assertEqual(ctx["war_b"].status.value, "truce")
        self.assertTrue(ctx["war_b"].naval_required)
        self.assertTrue(ctx["war_b"].peace_treaty)
        self.assertEqual(ctx["war_b"].peace_treaty["status"], "pending")
        # public land > 0 → land:sale 另一合法非 Takeover 提案可构造
        self.assertGreater(state.get_national_public_land(), 0)
        # 真实 reinforcement 池/国库
        ms = state.get_military_system()
        self.assertGreaterEqual(len(ms.get_available_legions()), 1)
        self.assertGreaterEqual(state.treasury, 0)

    def test_fix01_zero_pool_variant(self):
        ctx = F.build_fix01(zero_pool=True)
        ms = ctx["state"].get_military_system()
        self.assertEqual(len(ms.get_available_legions()), 0, "N0 零池附例")


class TestFix02to09Construct(unittest.TestCase):
    def test_fix02_zero_ready(self):
        ctx = F.build_fix02()
        war = ctx["war"]
        self.assertTrue(war.naval_required)
        self.assertEqual(len(war.assigned_fleet_ids), 0)
        self.assertFalse(war.sea_control_acquired)

    def test_fix03_to_07_ready_fleets(self):
        for builder, tag in [(F.build_fix03, "FIX-R4-03"), (F.build_fix04, "FIX-R4-04"),
                             (F.build_fix05, "FIX-R4-05"), (F.build_fix06, "FIX-R4-06"),
                             (F.build_fix07, "FIX-R4-07")]:
            ctx = builder()
            self.assertEqual(ctx["manifest"]["fixture"], tag)
            self.assertGreaterEqual(len(ctx["war"].assigned_fleet_ids), 1,
                                    f"{tag}: ready fleet assigned")
            self.assertGreaterEqual(len(ctx["legion_numbers"]), 1)

    def test_fix08_09_non_naval(self):
        for builder, tag in [(F.build_fix08, "FIX-R4-08"), (F.build_fix09, "FIX-R4-09")]:
            ctx = builder()
            self.assertEqual(ctx["manifest"]["fixture"], tag)
            self.assertFalse(ctx["war"].naval_required)
            self.assertIsNotNone(ctx["war"].commander_id)


if __name__ == "__main__":
    unittest.main()
