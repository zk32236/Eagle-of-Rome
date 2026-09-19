# src/tests/test_api/test_wpgr6_f6_dual_war.py
"""WP-G-R6 DA-2 B6（SA-Design v1.1 §B.6；AC-13 运行证据面）— F6 合法双 War 双层实测。

本片（DA-2 收口批）独立验收面：
- 四个 F6 fixture 在位且可复用（`build_f6` / `F6_NAMES`）；
- **F6-DD / F6-MIX / F6-VV 三正例在 API 层 + GUI 层均成功**：
  `created` / `direct_decisions` / claims / pool IDs / errors / refs 逐条实测；
- F6-ZERO-SWAP 两变体（zero / swap）均成功；
- **21 code 身份不变**。

证据分类 = DATA（RENDER 归 SO；`〔r〕` 帧不在本批自产）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api  # noqa: F401  (保留 API 层显式导入面)
from src.core.systems.political_system import PoliticalSystem
from src.tests.fixtures.wpgr5_fixtures import FIXED, build_r5_base
from src.tests.fixtures.wpgr6_fixtures import (
    F6_NAMES,
    build_f6,
    build_f6_base,
    build_f6_zero_swap,
    check_expect,
    error_codes,
    frozen_record,
    pool_legion_ids,
    submit_api,
    submit_gui,
)

F6_POSITIVES = ("F6-DD", "F6-MIX", "F6-VV")
SUBMIT_ERROR_CODES_21 = (
    "SUBMIT_REQUEST_INVALID", "SUBMIT_NOT_AUTHORIZED", "SUBMIT_PHASE_INVALID",
    "PACKAGE_ALREADY_SUBMITTED", "SUBMIT_REQUEST_REUSED", "WAR_PROPOSAL_DUPLICATE",
    "WAR_TARGET_INVALID", "WAR_NOT_PROPOSABLE", "WAR_MODE_INVALID", "COMMANDER_REQUIRED",
    "COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE", "REINFORCEMENT_INVALID",
    "PEACE_DRAFT_INVALID", "COMMANDER_CLAIM_DUPLICATE", "GOVERNOR_COMMANDER_CONFLICT",
    "GOVERNOR_NOMINATION_DUPLICATE", "NON_WAR_PROPOSAL_INVALID", "LEGION_POOL_EXCEEDED",
    "SUBMIT_CONTEXT_CHANGED", "SUBMIT_PUBLISH_FAILED",
)


class TestF6FixtureInventory(unittest.TestCase):
    """Exit (a)：四个 fixture 在位且可复用；既有 R5 fixture 未改名/未改写。"""

    def test_four_fixtures_in_place_and_buildable(self):
        self.assertEqual(F6_NAMES, ("F6-DD", "F6-MIX", "F6-VV", "F6-ZERO-SWAP"))
        for name in ("F6-DD", "F6-MIX", "F6-VV"):
            ctx = build_f6(name)
            self.assertEqual(ctx["fixture"], name)
            self.assertTrue(ctx["drafts"], name)
            self.assertTrue(ctx["expect"], name)
            self.assertEqual(len(ctx["state"].get_senate_proposals()), 0, "构造期零发布")
        zs = build_f6("F6-ZERO-SWAP")
        self.assertEqual(set(zs["variants"]), {"zero", "swap"})
        self.assertEqual(zs["fixture"], "F6-ZERO-SWAP")

    def test_r5_fixture_not_renamed_or_rewritten(self):
        # 既有 R5 fixture 名称/语义保留：build_r5_base 仍可用且默认带 passive
        r5 = build_r5_base()
        self.assertIsNotNone(r5["war_passive"])
        self.assertEqual(r5["manifest"]["fixture"], "R5-BASE")
        self.assertEqual(FIXED["war_ongoing"], "pyrrhic_war")
        self.assertEqual(FIXED["war_peace"], "first_punic_war")

    def test_f6_base_shape_per_design_b6(self):
        ctx = build_f6_base()
        self.assertIsNone(ctx["war_passive"], "passive=null（SA §B.6）")
        self.assertIsNone(ctx["province"], "Province 无 Governor/designate（SA §B.6）")
        self.assertGreaterEqual(len(pool_legion_ids(ctx["state"])), 3, "权威池至少 3")
        self.assertEqual(ctx["consul"].id, FIXED["consul"])
        self.assertEqual(ctx["cmd_a"].id, FIXED["cmd_a"])
        self.assertEqual(ctx["cmd_b"].id, FIXED["cmd_b"])
        self.assertEqual(ctx["war_ongoing"].commander_id, FIXED["cmd_a"])
        self.assertEqual(ctx["war_peace"].commander_id, FIXED["cmd_b"])


class TestF6ApiLayer(unittest.TestCase):
    """Exit (b)：F6 三正例 **API 层**（`senate_api.propose_many`）实测。"""

    def _run(self, name, session_id="S1"):
        ctx = build_f6(name)
        state = ctx["state"]
        pool_before = pool_legion_ids(state)
        result = submit_api(state, ctx["drafts"], session_id=session_id, request_id="req-1")
        record = frozen_record(state, result, session_id=session_id, pool_before=pool_before)
        self.assertTrue(result["success"], (name, error_codes(result)))
        self.assertEqual(check_expect(record, ctx["expect"]), [],
                         (name, check_expect(record, ctx["expect"]), record))
        return ctx, record

    def test_f6_dd_api(self):
        _ctx, record = self._run("F6-DD")
        self.assertEqual(record["created"], [])
        self.assertEqual(len(record["direct_decisions"]), 2)
        for d in record["direct_decisions"]:
            self.assertEqual(d["authority"], "consul_direct")
        # pending treaty 未清（Submit 只冻结，不执行边界/Peace 召回）
        self.assertEqual(_ctx["war_peace"].peace_treaty["status"], "pending")
        self.assertEqual(record["direct_decision_refs"],
                         [d["direct_decision_id"] for d in record["direct_decisions"]])

    def test_f6_mix_api(self):
        _ctx, record = self._run("F6-MIX")
        self.assertEqual([c["war_id"] for c in record["created"]], [FIXED["war_threat"]])
        self.assertEqual(record["created"][0]["authority"], "senate_vote")
        self.assertEqual([d["war_id"] for d in record["direct_decisions"]],
                         [FIXED["war_ongoing"]])
        self.assertEqual(record["direct_decisions"][0]["authority"], "consul_direct")
        self.assertEqual(_ctx["war_threat"].status.value, "threat", "无提前宣战")

    def test_f6_vv_api(self):
        _ctx, record = self._run("F6-VV")
        self.assertEqual(sorted(c["war_id"] for c in record["created"]),
                         sorted([FIXED["war_threat"], FIXED["war_peace"]]))
        self.assertEqual({c["authority"] for c in record["created"]}, {"senate_vote"})
        self.assertEqual(record["direct_decisions"], [])
        self.assertEqual(_ctx["war_peace"].peace_treaty["status"], "pending",
                         "Peace 提案保留 pending（ENACTED 仅边界释放召回）")


class TestF6GuiLayer(unittest.TestCase):
    """Exit (b)：F6 三正例 **GUI 层**（Store → Adapter → senate_api）实测。"""

    def _run(self, name):
        ctx = build_f6(name)
        state = ctx["state"]
        pool_before = pool_legion_ids(state)
        store, feedback = submit_gui(state, ctx["drafts"])
        self.assertTrue(store._senate_view.get("viewer_has_consul"), "Human/consul 路径")
        self.assertTrue(feedback.get("success"), (name, feedback.get("errors")))
        session_id = store._senate_view.get("senate_session_id") or state.get_senate_session()
        record = frozen_record(state, feedback, session_id=session_id, pool_before=pool_before)
        self.assertEqual(check_expect(record, ctx["expect"]), [],
                         (name, check_expect(record, ctx["expect"]), record))
        return ctx, store, record

    def test_f6_dd_gui(self):
        _ctx, store, record = self._run("F6-DD")
        self.assertEqual(record["created"], [])
        self.assertEqual(len(record["direct_decisions"]), 2)
        self.assertEqual(record["package_record_state"], "COMMITTED")
        self.assertEqual(store.senateSubmitErrors, [])
        self.assertFalse(store.hasSenateSubmitErrors)

    def test_f6_mix_gui(self):
        _ctx, _store, record = self._run("F6-MIX")
        self.assertEqual([c["war_id"] for c in record["created"]], [FIXED["war_threat"]])
        self.assertEqual([d["war_id"] for d in record["direct_decisions"]],
                         [FIXED["war_ongoing"]])

    def test_f6_vv_gui(self):
        _ctx, _store, record = self._run("F6-VV")
        self.assertEqual(len(record["created"]), 2)
        self.assertEqual(record["direct_decisions"], [])


class TestF6ZeroSwap(unittest.TestCase):
    """Exit (a)：F6-ZERO-SWAP 两变体均成功（submit 阶段无换绑）。"""

    def test_zero_variant_succeeds(self):
        variant = build_f6_zero_swap()["variants"]["zero"]
        state = variant["state"]
        war_ongoing_cmd = variant["war_ongoing"].commander_id
        result = submit_api(state, variant["drafts"])
        record = frozen_record(state, result, session_id="S1")
        self.assertTrue(result["success"], error_codes(result))
        self.assertEqual(check_expect(record, variant["expect"]), [],
                         (check_expect(record, variant["expect"]), record))
        self.assertEqual(variant["war_ongoing"].commander_id, war_ongoing_cmd,
                         "submit 阶段冻结，不改 War.commander_id")

    def test_swap_variant_succeeds(self):
        variant = build_f6_zero_swap()["variants"]["swap"]
        state = variant["state"]
        before = (variant["war_ongoing"].commander_id, variant["war_peace"].commander_id)
        result = submit_api(state, variant["drafts"])
        record = frozen_record(state, result, session_id="S1")
        self.assertTrue(result["success"], error_codes(result))
        self.assertEqual(check_expect(record, variant["expect"]), [],
                         (check_expect(record, variant["expect"]), record))
        self.assertEqual((variant["war_ongoing"].commander_id,
                          variant["war_peace"].commander_id), before,
                         "swap 只边界生效：Submit 后 live 绑定不变")


class TestF6CodeIdentity(unittest.TestCase):
    """Exit (c)：21 code 身份不变（不得新增/改名/删除）。"""

    def test_21_code_identity_unchanged(self):
        codes = list(PoliticalSystem._SUBMIT_ERROR_CODES)
        self.assertEqual(len(codes), 21)
        self.assertEqual(len(set(codes)), 21)
        self.assertEqual(tuple(codes), SUBMIT_ERROR_CODES_21)

    def test_f6_success_errors_empty(self):
        ctx = build_f6("F6-DD")
        result = submit_api(ctx["state"], ctx["drafts"])
        self.assertTrue(result["success"])
        self.assertEqual(error_codes(result), [])


if __name__ == "__main__":
    unittest.main()
