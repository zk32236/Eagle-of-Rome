# src/tests/test_gui/test_wpgr6_feedback.py
"""WP-G-R6 DA-2 B5（SA-Design v1.1 §B.5；AC-16 / N16 / N17）— 反馈 formatter + Store 面。

本片（B5）独立验收面：
- Adapter 唯一 structured error formatter `normalize_error_feedback`
  （dict / legacy str / 未知类型**三态不抛 TypeError**；`error_items` /
  `feedback_message` / `errors_by_scope` 形状齐备）；
- `scope=war_id` 定位到卡；`scope=package` 由 `details.claims/requests` 建相关卡关联；
- Adapter **API 异常与 refresh 异常分离捕获**（refresh 失败不反转 API 成功）；
- Store `senateSubmitErrors` / `senateSubmitErrorsByWar` + draft 按 session+war_id 保留。

证据分类 = DATA（RENDER 归 SO）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import GuiSessionStore
from src.tests.fixtures.wpgr5_fixtures import build_r5_base, FIXED
from src.tests.fixtures.wpgr6_fixtures import (  # noqa: F401
    build_f6_base,
    command_draft,
    pool_legion_ids,
    submit_api,
    card_by_war,
)
from src.core.systems.political_system import PoliticalSystem


class TestNormalizeErrorFeedback(unittest.TestCase):
    """formatter 三态 + 形状（Exit (a) / AC-16 / N16 / N17）。"""

    def test_dict_errors_keep_five_fields_and_details(self):
        errors = [{"code": "LEGION_POOL_EXCEEDED", "scope": "package",
                   "field": "requests", "details": {"requested": 5, "available": 3,
                                                     "reduce_by": 2},
                   "message": "军团池不足"}]
        out = GuiApiAdapter.normalize_error_feedback(errors, "提交失败")
        self.assertEqual(len(out["error_items"]), 1)
        item = out["error_items"][0]
        self.assertEqual(item["code"], "LEGION_POOL_EXCEEDED")
        self.assertEqual(item["scope"], "package")
        self.assertEqual(item["field"], "requests")
        self.assertEqual(item["details"]["reduce_by"], 2)
        self.assertEqual(item["details"]["requested"], 5)
        self.assertEqual(item["details"]["available"], 3)
        self.assertIn("LEGION_POOL_EXCEEDED", out["feedback_message"])
        self.assertIn("军团池不足", out["feedback_message"])
        self.assertIn("package", out["errors_by_scope"])

    def test_missing_message_falls_back_to_code_and_never_stringifies_dict(self):
        out = GuiApiAdapter.normalize_error_feedback(
            [{"code": "WAR_TARGET_INVALID", "scope": "package", "field": "target"}], "提交失败")
        item = out["error_items"][0]
        self.assertIn("WAR_TARGET_INVALID", item["message"])
        self.assertNotIn("{", item["message"], "不得把 dict 直接 stringify 当反馈")

    def test_legacy_string_errors_wrapped(self):
        out = GuiApiAdapter.normalize_error_feedback(["旧式错误一", "旧式错误二"], "提交失败")
        self.assertEqual(len(out["error_items"]), 2)
        for item in out["error_items"]:
            self.assertEqual(item["code"], "LEGACY_ERROR")
            self.assertEqual(item["scope"], "package")
            self.assertIsNone(item["field"])
        raws = sorted(i["details"]["raw"] for i in out["error_items"])
        self.assertEqual(raws, ["旧式错误一", "旧式错误二"])

    def test_unknown_and_none_types_do_not_raise(self):
        for payload in ([None, 42, object()], [{"code": "X"}], None, 3):
            out = GuiApiAdapter.normalize_error_feedback(payload, "提交失败")
            self.assertIsInstance(out["error_items"], list)
            self.assertIsInstance(out["feedback_message"], str)
            self.assertIsInstance(out["errors_by_scope"], dict)

    def test_war_scope_located_and_package_details_link_cards(self):
        errors = [
            {"code": "COMMANDER_TARGET_INVALID", "scope": FIXED["war_ongoing"],
             "field": "target_commander_id", "details": {}, "message": "目标不合法"},
            {"code": "LEGION_POOL_EXCEEDED", "scope": "package", "field": "requests",
             "details": {"claims": [{"war_id": FIXED["war_ongoing"]},
                                    {"war_id": FIXED["war_peace"]}],
                         "requests": [{"war_id": FIXED["war_ongoing"]}]},
             "message": "池不足"},
        ]
        out = GuiApiAdapter.normalize_error_feedback(errors, "提交失败")
        by_scope = out["errors_by_scope"]
        # scope=war_id 直定位该卡（键 = 原始 scope）
        self.assertIn(FIXED["war_ongoing"], by_scope)
        self.assertIn("COMMANDER_TARGET_INVALID",
                      [i["code"] for i in by_scope[FIXED["war_ongoing"]]])
        # scope=package 的 details.claims/requests → 相关卡关联（键 = war:<id>）
        self.assertIn(f"war:{FIXED['war_ongoing']}", by_scope)
        self.assertIn(f"war:{FIXED['war_peace']}", by_scope)
        codes = [i["code"] for i in by_scope[f"war:{FIXED['war_ongoing']}"]]
        self.assertIn("LEGION_POOL_EXCEEDED", codes)
        self.assertEqual(codes.count("LEGION_POOL_EXCEEDED"), 1, "同一 item 不得重复入桶")
        # package 桶保留包级解释
        self.assertIn("LEGION_POOL_EXCEEDED",
                      [i["code"] for i in by_scope["package"]])

    def test_canonical_sorting_by_code_scope_field(self):
        errors = [
            {"code": "WAR_TARGET_INVALID", "scope": "package", "field": "b"},
            {"code": "WAR_TARGET_INVALID", "scope": "package", "field": "a"},
            {"code": "COMMANDER_REQUIRED", "scope": "package", "field": None},
        ]
        out = GuiApiAdapter.normalize_error_feedback(errors, "提交失败")
        keys = [(i["code"], str(i["field"])) for i in out["error_items"]]
        self.assertEqual(keys, [("COMMANDER_REQUIRED", "None"),
                                ("WAR_TARGET_INVALID", "a"),
                                ("WAR_TARGET_INVALID", "b")])


class TestAdapterCallIntegration(unittest.TestCase):
    """Adapter `call()` 结构化反馈 + 异常分离捕获（Exit (a)）。"""

    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]

    def test_call_with_dict_errors_does_not_crash(self):
        adapter = GuiApiAdapter(self.state)

        def api(state, *args, **kwargs):
            return {"success": False, "message": "操作失败",
                    "errors": [{"code": "COMMANDER_CLAIM_DUPLICATE", "scope": "package",
                                "field": "claims", "details": {"claims": []},
                                "message": "重复将领"}]}

        feedback = adapter.call(api, self.state)
        self.assertFalse(feedback["success"])
        self.assertEqual(feedback["feedback_type"], "error")
        self.assertEqual(feedback["error_items"][0]["code"], "COMMANDER_CLAIM_DUPLICATE")
        self.assertIn("errors_by_scope", feedback)

    def test_refresh_exception_does_not_masquerade_as_api_failure(self):
        def boom():
            raise RuntimeError("refresh 挂了")

        adapter = GuiApiAdapter(self.state, refresh_callback=boom)

        def api(state, *args, **kwargs):
            return {"success": True, "message": "已提交整包", "data": {"created": []}}

        feedback = adapter.call(api, self.state)
        self.assertTrue(feedback["success"], "refresh 异常不得反转 API 成功")
        self.assertEqual(feedback["feedback_type"], "warning")
        self.assertIn("refresh 挂了", feedback["refresh_error"])
        self.assertIn("刷新失败", feedback["feedback_message"])

    def test_api_exception_still_error(self):
        adapter = GuiApiAdapter(self.state)

        def api(state, *args, **kwargs):
            raise ValueError("API 崩了")

        feedback = adapter.call(api, self.state)
        self.assertFalse(feedback["success"])
        self.assertEqual(feedback["feedback_type"], "error")


class TestStoreSenateSubmitErrors(unittest.TestCase):
    """Store 结构化错误面 + draft 保留（Exit (b)）。"""

    def setUp(self):
        self.ctx = build_r5_base()
        self.state = self.ctx["state"]
        self.store = GuiSessionStore(self.state)

    def _failure_feedback(self):
        errors = [
            {"code": "COMMANDER_CLAIM_DUPLICATE", "scope": "package", "field": "claims",
             "details": {"claims": [{"war_id": FIXED["war_ongoing"]}]},
             "message": "重复将领"},
            {"code": "REINFORCEMENT_INVALID", "scope": FIXED["war_peace"],
             "field": "reinforcement_n", "details": {}, "message": "N 非法"},
        ]
        normalized = GuiApiAdapter.normalize_error_feedback(errors, "提交失败")
        return {"success": False, "message": "提交失败", "errors": errors,
                "error_items": normalized["error_items"],
                "errors_by_scope": normalized["errors_by_scope"]}

    def test_failure_populates_banner_items_and_card_errors(self):
        self.store._apply_senate_submit_feedback(self._failure_feedback())
        self.assertTrue(self.store.hasSenateSubmitErrors)
        self.assertEqual(len(self.store.senateSubmitErrors), 2)
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", self.store.senateSubmitErrorBanner)
        # scope=war_id 直定位 + package details.claims 相关卡关联
        by_war = self.store.senateSubmitErrorsByWar
        self.assertIn(FIXED["war_peace"], by_war)
        self.assertIn(FIXED["war_ongoing"], by_war)
        self.assertIn("REINFORCEMENT_INVALID",
                      [i["code"] for i in by_war[FIXED["war_peace"]]])
        self.assertIn("COMMANDER_CLAIM_DUPLICATE",
                      [i["code"] for i in by_war[FIXED["war_ongoing"]]])

    def test_success_clears_error_surface(self):
        self.store._apply_senate_submit_feedback(self._failure_feedback())
        self.store._apply_senate_submit_feedback({"success": True, "data": {}})
        self.assertFalse(self.store.hasSenateSubmitErrors)
        self.assertEqual(self.store.senateSubmitErrors, [])
        self.assertEqual(self.store.senateSubmitErrorsByWar, {})
        self.assertEqual(self.store.senateSubmitErrorBanner, "")

    def test_draft_retained_per_session_and_war(self):
        self.store._senate_draft_session_id = "S1"
        draft = {"war_id": FIXED["war_ongoing"], "checked": True, "mode": "command",
                 "target_commander_id": self.ctx["cmd_a"].id, "reinforcement_n": 2}
        self.store.doUpdateSenateDraft(FIXED["war_ongoing"], draft)
        kept = self.store.senateDraftFor(FIXED["war_ongoing"])
        self.assertTrue(kept["checked"])
        self.assertEqual(kept["mode"], "command")
        self.assertEqual(kept["target_commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(kept["reinforcement_n"], 2)
        # session 隔离：切换 session 后同一 war_id 不串档
        self.store._senate_draft_session_id = "S2"
        self.assertEqual(self.store.senateDraftFor(FIXED["war_ongoing"]), {})
        self.store._senate_draft_session_id = "S1"
        self.assertEqual(self.store.senateDraftFor(FIXED["war_ongoing"])["reinforcement_n"], 2)

    def test_failure_feedback_does_not_clear_drafts(self):
        self.store._senate_draft_session_id = "S1"
        draft = {"war_id": FIXED["war_ongoing"], "checked": True, "mode": "command",
                 "target_commander_id": self.ctx["cmd_a"].id, "reinforcement_n": 3}
        self.store.doUpdateSenateDraft(FIXED["war_ongoing"], draft)
        self.store._apply_senate_submit_feedback(self._failure_feedback())
        kept = self.store.senateDraftFor(FIXED["war_ongoing"])
        self.assertTrue(kept["checked"], "失败不得取消 checkbox")
        self.assertEqual(kept["reinforcement_n"], 3, "失败不得 clamp/改 N")
        self.assertEqual(kept["target_commander_id"], self.ctx["cmd_a"].id,
                         "失败不得换将")


def _read_qml(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


class TestB5FeedbackWiring(unittest.TestCase):
    """R6 DA-4 B5（SA §D.3 / §B.5）：三例反馈接线。

    每例：可见 code + message、相关卡定位、checkbox/mode/target/N 不变、更正后成功；
    另证失败不触发破坏性 refresh + 无残留 stale error。
    **仅 QML/源码断言不能替代 render 交互证明**——真实交互 RENDER 归 SO 帧
    （`r6-submit-error-invalid-n` / `r6-submit-error-duplicate-commander` / `r6-submit-error-pool`）。
    """

    def _store(self):
        ctx = build_f6_base()
        store = GuiSessionStore(ctx["state"])
        store.initialize(FIXED["player"])
        return ctx, store

    def _codes(self, store):
        return [i["code"] for i in store.senateSubmitErrors]

    def _item(self, store, code):
        return next(i for i in store.senateSubmitErrors if i["code"] == code)

    def _assert_card_located(self, store, war_id, code):
        by_war = store.senateSubmitErrorsByWar
        self.assertIn(war_id, by_war, f"相关卡未定位: {war_id} ({by_war.keys()})")
        self.assertIn(code, [i["code"] for i in by_war[war_id]])

    def _assert_draft_retained(self, store, war_id, draft):
        kept = store.senateDraftFor(war_id)
        self.assertEqual(kept.get("checked"), draft["checked"], "失败不得取消 checkbox")
        self.assertEqual(kept.get("mode"), draft["mode"], "失败不得改 mode")
        self.assertEqual(kept.get("target_commander_id"), draft["target_commander_id"],
                         "失败不得换将")
        self.assertEqual(kept.get("reinforcement_n"), draft["reinforcement_n"],
                         "失败不得 clamp/改 N")

    # ---- 例 1：invalid N（AC-11）----
    def test_example1_invalid_n_visible_located_retained_then_corrected(self):
        ctx, store = self._store()
        wid = FIXED["war_ongoing"]
        bad = command_draft(wid, ctx["cmd_a"].id, reinforcement_n=-1)
        feedback = store.doSubmitSenateProposals([bad])
        self.assertFalse(feedback["success"])
        # code + message 可见（包级横幅）
        banner = store.senateSubmitErrorBanner
        self.assertIn("REINFORCEMENT_INVALID", banner)
        self.assertIn("Reinforcement N 非法", banner)
        item = self._item(store, "REINFORCEMENT_INVALID")
        self.assertEqual(item["scope"], wid)
        self.assertEqual(item["field"], "reinforcement_n")
        self.assertEqual(item["details"]["supplied_n"], -1)
        # 相关卡定位
        self._assert_card_located(store, wid, "REINFORCEMENT_INVALID")
        # 失败不触发破坏性 refresh（仍在提案步、仍可编辑）
        self.assertEqual(store.senateCurrentStep, "proposal")
        self.assertTrue(store.canCreateSenateProposal)
        # 草稿不变
        self._assert_draft_retained(store, wid, bad)
        # 更正后成功 + 无残留 stale error
        good = command_draft(wid, ctx["cmd_a"].id, reinforcement_n=1)
        feedback2 = store.doSubmitSenateProposals([good])
        self.assertTrue(feedback2["success"], feedback2)
        self.assertFalse(store.hasSenateSubmitErrors)
        self.assertEqual(store.senateSubmitErrorBanner, "")
        self.assertEqual(store.senateSubmitErrorsByWar, {})

    # ---- 例 2：跨 direct+vote 重复将领（AC-12）----
    def test_example2_cross_route_duplicate_commander_two_cards_then_corrected(self):
        ctx, store = self._store()
        w_on, w_th = FIXED["war_ongoing"], FIXED["war_threat"]
        d_on = command_draft(w_on, ctx["cmd_a"].id, reinforcement_n=1)   # direct 路由（ongoing）
        d_th = command_draft(w_th, ctx["cmd_a"].id, reinforcement_n=2)   # vote 路由（主动宣战）
        feedback = store.doSubmitSenateProposals([d_on, d_th])
        self.assertFalse(feedback["success"])
        self.assertIn("COMMANDER_CLAIM_DUPLICATE", store.senateSubmitErrorBanner)
        self.assertIn("同一非 null Commander 被不同 War claim", store.senateSubmitErrorBanner)
        item = self._item(store, "COMMANDER_CLAIM_DUPLICATE")
        self.assertEqual(item["scope"], "package")
        claimed = sorted(str(c["war_id"]) for c in item["details"]["claims"])
        self.assertEqual(claimed, sorted([w_on, w_th]))
        # **两**相关卡按 scope 定位
        self._assert_card_located(store, w_on, "COMMANDER_CLAIM_DUPLICATE")
        self._assert_card_located(store, w_th, "COMMANDER_CLAIM_DUPLICATE")
        # 两卡草稿均不变
        self._assert_draft_retained(store, w_on, d_on)
        self._assert_draft_retained(store, w_th, d_th)
        # 更正（threat 换唯一 consul target）→ 成功
        d_th_ok = command_draft(w_th, ctx["consul_id"], reinforcement_n=2)
        feedback2 = store.doSubmitSenateProposals([d_on, d_th_ok])
        self.assertTrue(feedback2["success"], feedback2)
        self.assertFalse(store.hasSenateSubmitErrors)

    # ---- 例 3：超池 LEGION_POOL_EXCEEDED（AC-11 / AC-15）----
    def test_example3_pool_exceeded_three_values_zero_publish_then_corrected(self):
        ctx, store = self._store()
        state = ctx["state"]
        w_on, w_th = FIXED["war_ongoing"], FIXED["war_threat"]
        available = len(pool_legion_ids(state))
        self.assertGreater(available, 0)
        d_big = command_draft(w_on, ctx["cmd_a"].id, reinforcement_n=available + 1)
        d_th = command_draft(w_th, ctx["consul_id"], reinforcement_n=1)
        feedback = store.doSubmitSenateProposals([d_big, d_th])
        self.assertFalse(feedback["success"])
        self.assertIn("LEGION_POOL_EXCEEDED", store.senateSubmitErrorBanner)
        item = self._item(store, "LEGION_POOL_EXCEEDED")
        # requested / available / reduce_by 三值（Core 权威 details 键）
        self.assertEqual(item["details"]["requested_total"], available + 2)
        self.assertEqual(item["details"]["available_total"], available)
        self.assertEqual(item["details"]["reduce_by"], 2)
        # 零发布：无提案 / 无 direct 决策 / 无 by_session 包
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual(state.get_consul_war_decisions("turn-1"), {})
        self.assertIsNone(state.get_senate_package_id_for_session("turn-1"))
        # 相关卡定位（details.requests 关联两卡）
        self._assert_card_located(store, w_on, "LEGION_POOL_EXCEEDED")
        self._assert_card_located(store, w_th, "LEGION_POOL_EXCEEDED")
        # 草稿保留
        self._assert_draft_retained(store, w_on, d_big)
        self._assert_draft_retained(store, w_th, d_th)
        # 更正（削 reduce_by）→ 成功
        d_ok = command_draft(w_on, ctx["cmd_a"].id, reinforcement_n=available - 1)
        feedback2 = store.doSubmitSenateProposals([d_ok, d_th])
        self.assertTrue(feedback2["success"], feedback2)
        self.assertFalse(store.hasSenateSubmitErrors)

    # ---- 显示路径：pool 三值必须绑定 Core 权威 details 键 ----
    def test_pool_line_binds_core_authoritative_details_keys(self):
        qml = _read_qml("src/ui/gui/qml/components/WarProposalCard.qml")
        self.assertIn("requested_total", qml)
        self.assertIn("available_total", qml)
        self.assertIn("reduce_by", qml)


class TestR_B4_1PAReadOnlySummaryNoElide(unittest.TestCase):
    """PM 窄项 R-B4-1：PA 只读摘要身份行改 wrap / 不 elide（**源码面**）。

    RENDER（最小窗口宽度真实渲染）归 SO 帧 `r6-war-card-long-commander`；本类只锁源码面。
    """

    @classmethod
    def setUpClass(cls):
        cls.qml = _read_qml("src/ui/gui/qml/stages/SenateStage.qml")

    def test_summary_identity_rows_drop_maxline_and_elide(self):
        markers = [
            "root._announcementEnactedText()",
            "root._consulDirectLabel()",
            "root._directActionText()",
            "root._governorSummary()",
            "root._commanderSummary()",
            "root._fleetSummary()",
        ]
        for marker in markers:
            idx = self.qml.find(marker)
            self.assertGreaterEqual(idx, 0, f"marker not found: {marker}")
            block = self.qml[idx:idx + 500]
            self.assertNotIn("maximumLineCount:", block, marker)
            self.assertNotIn("elide: Text.ElideRight", block, marker)
            self.assertIn("wrapMode: Text.Wrap", block, marker)


class TestR_B4_3FrozenTargetLabelProducer(unittest.TestCase):
    """PM 窄项 R-B4-3：`build_war_card_views` 补齐冻结 target label 生产者（增量字段）。

    Card 只读摘要（`WarProposalCard.warCardFrozenCommanderLabel`）依赖
    `card.target_commander_label` —— 生产者 = Core `build_war_card_views`。
    RENDER 归 SO；本类证「提交后卡片只读摘要可取得完整冻结身份」的 DATA/绑定面。
    """

    def _cards(self, state, ctx):
        return PoliticalSystem(state).build_war_card_views(
            {"current_turn": 1, "consul_id": ctx["consul_id"]})

    def test_direct_route_card_carries_frozen_target_label(self):
        ctx = build_f6_base()
        state = ctx["state"]
        result = submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)])
        self.assertTrue(result["success"], result)
        card = card_by_war(self._cards(state, ctx), FIXED["war_ongoing"])
        self.assertEqual(card["target_commander_label"], ctx["cmd_a"].get_formal_name())
        # 未提交的 War 无冻结身份 → 空字符串（不猜名、不冒充 current）
        untouched = card_by_war(self._cards(state, ctx), FIXED["war_peace"])
        self.assertEqual(untouched["target_commander_label"], "")
        # 既有机器身份字段不变（增量新增，非改名）
        self.assertEqual(card["current_commander_label"], ctx["cmd_a"].get_formal_name())

    def test_vote_route_card_carries_frozen_target_label(self):
        ctx = build_f6_base()
        state = ctx["state"]
        result = submit_api(state, [command_draft(FIXED["war_threat"], ctx["consul_id"], 2)])
        self.assertTrue(result["success"], result)
        card = card_by_war(self._cards(state, ctx), FIXED["war_threat"])
        expected = state.get_member(ctx["consul_id"]).get_formal_name()
        self.assertEqual(card["target_commander_label"], expected)

    def test_store_war_cards_expose_frozen_label_after_submit(self):
        ctx = build_f6_base()
        store = GuiSessionStore(ctx["state"])
        store.initialize(FIXED["player"])
        feedback = store.doSubmitSenateProposals(
            [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)])
        self.assertTrue(feedback["success"], feedback)
        card = card_by_war(store.senateWarCards, FIXED["war_ongoing"])
        self.assertIsNotNone(card)
        self.assertEqual(card["target_commander_label"], ctx["cmd_a"].get_formal_name())


if __name__ == "__main__":
    unittest.main()
