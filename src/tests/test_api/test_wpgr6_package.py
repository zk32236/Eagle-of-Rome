# src/tests/test_api/test_wpgr6_package.py
"""WP-G-R6 DA-2 B1（SA-Design v1.1 §B.1 / §B.4；AC-14/15 基础面）— 双账本 schema + Context。

本片（B1）独立验收面：
- `_senate_package_ledger` 七索引 schema（`__init__` / `reset` / `create_for_testing` / save-load 同版）；
- `ConsulWarDecision`（服务端 opaque `direct_decision_id`；**无 proposal_id**；FROZEN）；
- `PackageRecord` + `by_session` 同会期唯一；
- `war_items` 跨路由 War 唯一性（两路由共享同一去重面）；
- `_senate_pending["direct_actions"]` 仅已执行边界审计（fail-closed 拒收 FROZEN direct 决策）；
- `SubmissionContext` **真注册**（全真实 War 深值冻结，含无卡 / unchecked / 空包）；
- `clear_senate_pending` 语义收窄（只清投票工作集，不清 packages/contexts/direct/war_items）；
- 复合键 rows/list 编码 + 加载重建校验一致性。

证据分类 = DATA（RENDER 归 SO）。
"""
import copy
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.game_state import (
    GameState,
    CONSUL_DIRECT_DECISION_ID_PREFIX,
    CONSUL_WAR_DECISION_SCHEMA_VERSION,
    SENATE_PACKAGE_SCHEMA_VERSION,
    WAR_ITEM_AUTHORITY_CONSUL_DIRECT,
    WAR_ITEM_AUTHORITY_SENATE_VOTE,
    SenatePackageTransaction,
    WarResolutionTransaction,
    _empty_senate_package_ledger,
)
from src.core.systems.political_system import PoliticalSystem
from src.tests.fixtures.wpgr4_fixtures import _base_config
from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, command_draft, peace_draft, recruit_legions_for_war, submit_request,
    error_codes,
)

LEDGER_INDEXES = {"requests", "war_snapshots", "contexts", "packages", "by_session",
                  "war_items", "consul_war_decisions"}


def _registry(state):
    return state.get_senate_package_registry()


def _frozen_context(state, request_id="req-1", actor="player1", session="S1"):
    """经 request 记录取回本包 SubmissionContext（按 item_ref 重取，不用 display id）。

    R6（§B.4，DA-2 B4）：request key = **(session, actor, request_id)**。
    """
    record = state.get_senate_submit_request(session, actor, request_id)
    assert record is not None, "request record missing"
    context_id = record["submission_context_id"]
    return context_id, state.get_submission_context(context_id)


class _B1Case(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base(with_governor=True)
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)


# ---------------------------------------------------------------------------
# 1) 账本 schema：四条构造路径同版
# ---------------------------------------------------------------------------
class TestSenateLedgerSchema(_B1Case):

    def test_canonical_empty_ledger_has_all_r6_indexes(self):
        self.assertEqual(set(_empty_senate_package_ledger()), LEDGER_INDEXES)

    def test_init_factory_and_reset_share_schema(self):
        # __init__ 路径
        self.assertEqual(set(GameState().get_senate_package_registry()), LEDGER_INDEXES)
        # create_for_testing 路径
        state = GameState.create_for_testing(_base_config())
        self.assertEqual(set(state.get_senate_package_registry()), LEDGER_INDEXES)
        # reset 路径
        state.reset()
        self.assertEqual(set(state.get_senate_package_registry()), LEDGER_INDEXES)

    def test_legacy_save_without_r6_indexes_loads_clean(self):
        data = self.state.to_dict()
        data["_senate_package_ledger"] = {"requests": {}, "war_snapshots": {}, "contexts": {}}
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(copy.deepcopy(data))
        registry = clone.get_senate_package_registry()
        self.assertEqual(set(registry), LEDGER_INDEXES)
        self.assertEqual(registry["packages"], {})
        self.assertEqual(registry["by_session"], {})
        self.assertEqual(registry["war_items"], {})
        self.assertEqual(registry["consul_war_decisions"], {})
        self.assertEqual(clone.validate_senate_ledger_consistency(), [])


# ---------------------------------------------------------------------------
# 2) ConsulWarDecision（§B.1）
# ---------------------------------------------------------------------------
class TestConsulWarDecisionLedger(_B1Case):

    def test_direct_decision_id_is_opaque_typed_and_not_proposal_counter(self):
        before = self.state._senate_pending["proposal_id_counter"]
        ids = {self.state.mint_consul_direct_decision_id() for _ in range(32)}
        self.assertEqual(len(ids), 32, "opaque id 不得碰撞")
        for direct_id in ids:
            self.assertTrue(direct_id.startswith(CONSUL_DIRECT_DECISION_ID_PREFIX), direct_id)
            self.assertFalse(direct_id.isdigit(), "不得以可数 proposal_id 形态伪装")
        self.assertEqual(self.state._senate_pending["proposal_id_counter"], before,
                         "禁借 proposal counter")

    def test_register_normalizes_schema_and_getter_deep_copies(self):
        decision = {"senate_session_id": "S1", "direct_decision_id": "cwd_unit",
                    "war_id": FIXED["war_ongoing"], "mode": "command",
                    "payload": {"target_commander_id": 2, "reinforcement_n": 1}}
        self.assertTrue(self.state.register_consul_war_decision(decision))
        got = self.state.get_consul_war_decisions("S1")
        self.assertEqual(set(got), {"cwd_unit"})
        record = got["cwd_unit"]
        self.assertEqual(record["type"], "consul_war_decision")
        self.assertEqual(record["authority"], WAR_ITEM_AUTHORITY_CONSUL_DIRECT)
        self.assertEqual(record["decision_state"], "FROZEN")
        self.assertEqual(record["schema_version"], CONSUL_WAR_DECISION_SCHEMA_VERSION)
        self.assertNotIn("proposal_id", record)
        got["cwd_unit"]["payload"]["reinforcement_n"] = 999
        self.assertEqual(
            self.state.get_consul_war_decisions("S1")["cwd_unit"]["payload"]["reinforcement_n"], 1,
            "getter 必须返回深拷贝（不得暴露底账）")

    def test_reject_proposal_identity_masquerade_zero_write(self):
        self.assertFalse(self.state.register_consul_war_decision(
            {"senate_session_id": "S1", "direct_decision_id": "cwd_x", "proposal_id": -1}))
        self.assertFalse(self.state.register_consul_war_decision(
            {"senate_session_id": "S1", "direct_decision_id": "cwd_y",
             "proposal_ref": {"proposal_id": 3}}))
        self.assertEqual(self.state.get_consul_war_decisions("S1"), {})

    def test_reject_invalid_schema_zero_write(self):
        invalid = [
            {"senate_session_id": "S1", "direct_decision_id": "cwd_a", "authority": "senate_vote"},
            {"senate_session_id": "S1", "direct_decision_id": "cwd_b", "decision_state": "ENACTED"},
            {"senate_session_id": "S1"},
            {"direct_decision_id": "cwd_c"},
            {"senate_session_id": "S1", "direct_decision_id": ""},
            "not-a-dict",
        ]
        for payload in invalid:
            self.assertFalse(self.state.register_consul_war_decision(payload), payload)
        self.assertEqual(self.state.get_consul_war_decisions("S1"), {})

    def test_session_isolation(self):
        self.assertTrue(self.state.register_consul_war_decision(
            {"senate_session_id": "S1", "direct_decision_id": "cwd_1"}))
        self.assertTrue(self.state.register_consul_war_decision(
            {"senate_session_id": "S2", "direct_decision_id": "cwd_2"}))
        self.assertEqual(set(self.state.get_consul_war_decisions("S1")), {"cwd_1"})
        self.assertEqual(set(self.state.get_consul_war_decisions("S2")), {"cwd_2"})
        self.assertEqual(self.state.get_consul_war_decisions("S3"), {})


# ---------------------------------------------------------------------------
# 3) PackageRecord + by_session
# ---------------------------------------------------------------------------
class TestPackageRecordLedger(_B1Case):

    def test_register_defaults_and_by_session_mapping(self):
        self.assertTrue(self.state.register_senate_package_record(
            {"package_id": "pkg-1", "senate_session_id": "S1", "actor_id": "player1"}))
        record = self.state.get_senate_package_record("pkg-1")
        self.assertEqual(record["schema_version"], SENATE_PACKAGE_SCHEMA_VERSION)
        self.assertEqual(record["publication_state"], "COMMITTED")
        self.assertEqual(self.state.get_senate_package_id_for_session("S1"), "pkg-1")
        self.assertIsNone(self.state.get_senate_package_id_for_session("S2"))

    def test_second_package_same_session_rejected(self):
        self.assertTrue(self.state.register_senate_package_record(
            {"package_id": "pkg-1", "senate_session_id": "S1"}))
        self.assertFalse(self.state.register_senate_package_record(
            {"package_id": "pkg-2", "senate_session_id": "S1"}))
        self.assertIsNone(self.state.get_senate_package_record("pkg-2"))
        self.assertEqual(self.state.get_senate_package_id_for_session("S1"), "pkg-1")
        # 同 package_id 重入 = 幂等
        self.assertTrue(self.state.register_senate_package_record(
            {"package_id": "pkg-1", "senate_session_id": "S1"}))
        # 缺身份 → 零写入
        self.assertFalse(self.state.register_senate_package_record({"senate_session_id": "S2"}))
        self.assertFalse(self.state.register_senate_package_record({"package_id": "pkg-3"}))
        self.assertEqual(set(_registry(self.state)["packages"]), {"pkg-1"})

    def test_record_getter_is_deep_copy(self):
        self.state.register_senate_package_record(
            {"package_id": "pkg-1", "senate_session_id": "S1",
             "proposal_refs": [{"proposal_id": 1}], "direct_decision_refs": []})
        record = self.state.get_senate_package_record("pkg-1")
        record["proposal_refs"].append({"proposal_id": 999})
        self.assertEqual(len(self.state.get_senate_package_record("pkg-1")["proposal_refs"]), 1)
        self.assertIsNone(self.state.get_senate_package_record("missing"))


# ---------------------------------------------------------------------------
# 4) war_items 跨路由唯一性
# ---------------------------------------------------------------------------
class TestWarItemsCrossRouteUniqueness(_B1Case):

    def test_second_route_for_same_war_is_rejected(self):
        self.assertTrue(self.state.register_senate_war_item(
            "S1", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_SENATE_VOTE,
            {"kind": "senate_proposal", "proposal_id": 1}))
        self.assertFalse(self.state.register_senate_war_item(
            "S1", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_CONSUL_DIRECT,
            {"kind": "consul_direct", "direct_decision_id": "cwd_1"}),
            "同一 (session, war) 只允许一个 authoritative item")
        items = self.state.get_senate_war_items("S1")
        self.assertEqual(list(items), [("S1", FIXED["war_ongoing"])])
        self.assertEqual(items[("S1", FIXED["war_ongoing"])]["authority"],
                         WAR_ITEM_AUTHORITY_SENATE_VOTE)

    def test_same_item_ref_is_idempotent_other_ref_rejected(self):
        ref = {"kind": "consul_direct", "direct_decision_id": "cwd_1"}
        self.assertTrue(self.state.register_senate_war_item(
            "S1", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_CONSUL_DIRECT, ref))
        self.assertTrue(self.state.register_senate_war_item(
            "S1", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_CONSUL_DIRECT, ref))
        self.assertFalse(self.state.register_senate_war_item(
            "S1", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_CONSUL_DIRECT,
            {"kind": "consul_direct", "direct_decision_id": "cwd_2"}),
            "同 War 第二 direct item 不得登记（跨路由/同路由皆唯一）")

    def test_authority_and_identity_validation_zero_write(self):
        self.assertFalse(self.state.register_senate_war_item("S1", FIXED["war_ongoing"], "banana", {"ref": 1}))
        self.assertFalse(self.state.register_senate_war_item("", FIXED["war_ongoing"],
                                                             WAR_ITEM_AUTHORITY_SENATE_VOTE, {"ref": 1}))
        self.assertFalse(self.state.register_senate_war_item("S1", "",
                                                             WAR_ITEM_AUTHORITY_SENATE_VOTE, {"ref": 1}))
        self.assertEqual(self.state.get_senate_war_items(), {})

    def test_session_scope_and_getter_deep_copy(self):
        self.assertTrue(self.state.register_senate_war_item(
            "S1", "w1", WAR_ITEM_AUTHORITY_CONSUL_DIRECT, {"ref": "d1"}))
        self.assertTrue(self.state.register_senate_war_item(
            "S2", "w1", WAR_ITEM_AUTHORITY_SENATE_VOTE, {"ref": 2}))
        self.assertEqual(set(self.state.get_senate_war_items("S1")), {("S1", "w1")})
        self.assertEqual(len(self.state.get_senate_war_items()), 2)
        items = self.state.get_senate_war_items()
        items[("S1", "w1")]["item_ref"]["ref"] = "mutated"
        self.assertEqual(self.state.get_senate_war_items()[("S1", "w1")]["item_ref"]["ref"], "d1")


# ---------------------------------------------------------------------------
# 5) direct_actions = 仅已执行边界审计
# ---------------------------------------------------------------------------
class TestDirectActionsAreBoundaryAuditOnly(_B1Case):

    def test_frozen_direct_decision_payloads_rejected_zero_write(self):
        payloads = [
            {"action_type": "war_resolution_commit", "type": "consul_war_decision"},
            {"action_type": "war_resolution_commit", "decision_state": "FROZEN"},
            {"action_type": "war_resolution_commit", "authority": WAR_ITEM_AUTHORITY_CONSUL_DIRECT},
            {"action_type": "war_resolution_commit", "direct_decision_id": "cwd_1"},
            {"action_type": "war_resolution_commit", "proposal_id": 7},
            {"action_type": "war_resolution_commit", "proposal_ref": {"proposal_id": 7}},
            "not-a-dict",
        ]
        for payload in payloads:
            self.assertFalse(self.state.record_senate_direct_action(payload), payload)
        self.assertEqual(self.state.get_senate_direct_actions(), [])

    def test_boundary_audit_accepted_and_separate_from_direct_ledger(self):
        self.assertTrue(self.state.record_senate_direct_action({
            "action_type": "war_resolution_commit", "kind": "war_resolution",
            "exactly_once_key": "exec-1", "trigger_source": "human_explicit"}))
        actions = self.state.get_senate_direct_actions()
        self.assertEqual([a["kind"] for a in actions], ["war_resolution"])
        self.assertEqual(self.state.get_consul_war_decisions("S1"), {},
                         "审计列表与 direct 决策账本互不相通")
        actions[0]["kind"] = "mutated"
        self.assertEqual(self.state.get_senate_direct_actions()[0]["kind"], "war_resolution",
                         "审计写入必须深拷贝")


# ---------------------------------------------------------------------------
# 6) SubmissionContext 真注册（含无卡 / unchecked / 空包）
# ---------------------------------------------------------------------------
class TestSubmissionContextRegistration(_B1Case):

    def test_context_registered_with_frozen_values(self):
        ctx = self.ctx
        legion_numbers = recruit_legions_for_war(self.state, ctx["war_ongoing"], ctx["cmd_a"].id, count=2)
        self.assertTrue(legion_numbers)
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=1)]))
        self.assertTrue(result["success"], result.get("errors"))
        context_id, frozen = _frozen_context(self.state)
        self.assertEqual(len(_registry(self.state)["contexts"]), 1)
        self.assertEqual(frozen["kind"], "submission_context")
        self.assertEqual(frozen["context_id"], context_id)
        self.assertEqual(frozen["senate_session_id"], "S1")
        self.assertEqual(frozen["actor_id"], "player1")
        self.assertEqual(frozen["package_id"], result["data"]["package_id"])
        self.assertEqual(frozen["schema_version"], SENATE_PACKAGE_SCHEMA_VERSION)

        war = frozen["wars"][FIXED["war_ongoing"]]
        self.assertEqual(war["current_commander_id"], ctx["cmd_a"].id)
        self.assertEqual(war["current_commander_label"], ctx["cmd_a"].get_formal_name())
        self.assertEqual(war["status"], "active")
        self.assertEqual(war["activation_origin"], "active_declaration")
        self.assertEqual(war["activation_episode"], ctx["war_ongoing"].activation_episode)
        self.assertEqual(war["commander_assigned_turn"],
                         ctx["war_ongoing"].commander_assigned_turn)
        self.assertEqual(war["survivor_legion_ids"], sorted(legion_numbers))
        self.assertEqual(war["legion_bindings"],
                         {str(number): ctx["cmd_a"].id for number in sorted(legion_numbers)})
        self.assertEqual(war["fleet_ids"], list(ctx["war_ongoing"].assigned_fleet_ids))
        self.assertEqual(war["legion_numbers_field"],
                         list(ctx["war_ongoing"].legion_numbers))

        # 全部真实 War 入冻结面（含 pending-peace）；THREAT（非真实 War）不入
        self.assertEqual(set(frozen["war_ids"]),
                         {FIXED["war_ongoing"], FIXED["war_peace"], FIXED["war_passive"]})
        self.assertNotIn(FIXED["war_threat"], frozen["wars"])
        pending = frozen["wars"][FIXED["war_peace"]]
        self.assertEqual(pending["peace_treaty"], ctx["war_peace"].peace_treaty,
                         "pending treaty 全条款深值冻结")

        # claims / 候选 / Governor 相关事实
        claims = [c for c in frozen["claims"] if c["war_id"] == FIXED["war_ongoing"]]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["commander_id"], ctx["cmd_a"].id)
        self.assertEqual(claims[0]["basis"], "selected_command")
        candidate_ids = [c["figure_id"] for c in frozen["commander_candidates"]]
        self.assertIn(ctx["cmd_a"].id, candidate_ids)
        province = frozen["provinces"][str(FIXED["province"])]
        self.assertEqual(province["governor_id"], ctx["cmd_gov"].id)
        self.assertIsNone(province["governor_designate_id"])
        self.assertEqual(frozen["figures"][str(ctx["cmd_a"].id)]["label"],
                         ctx["cmd_a"].get_formal_name())

    def test_context_is_deep_copy_and_not_a_reservation(self):
        ms = self.state.get_military_system()
        available_before = sorted(legion.number for legion in ms.get_available_legions())
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=2)]))
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(sorted(legion.number for legion in ms.get_available_legions()),
                         available_before, "SubmissionContext 不是 reservation：不扣池")
        _, frozen = _frozen_context(self.state)
        self.assertEqual(frozen["available_legion_ids"], available_before)
        frozen["wars"][FIXED["war_ongoing"]]["current_commander_id"] = 9999
        frozen["claims"].clear()
        _, reread = _frozen_context(self.state)
        self.assertEqual(reread["wars"][FIXED["war_ongoing"]]["current_commander_id"],
                         self.ctx["cmd_a"].id)
        self.assertTrue(reread["claims"], "外部改副本不得影响底账")

    def test_context_includes_no_card_and_unchecked_real_war(self):
        ctx = self.ctx
        # approved TRUCE 不出卡，但仍是真实 War（无卡场景）
        ctx["war_peace"].peace_treaty["status"] = "approved"
        view = senate_api.get_senate_view(self.state, self.ctx["player_id"])
        self.assertTrue(view["success"], view.get("message"))
        card_ids = {card["war_id"] for card in view["data"]["war_cards"]}
        self.assertNotIn(FIXED["war_peace"], card_ids, "approved TRUCE 不出作战卡")
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=0, checked=False)]))
        self.assertTrue(result["success"], result.get("errors"))
        _, frozen = _frozen_context(self.state)
        self.assertIn(FIXED["war_peace"], frozen["war_ids"], "无卡真实 War 仍入冻结面")
        self.assertEqual([draft["war_id"] for draft in frozen["submitted_drafts"]],
                         [FIXED["war_ongoing"]])
        self.assertFalse(frozen["submitted_drafts"][0]["checked"])
        self.assertEqual(self.state.get_senate_proposals(), [], "unchecked 不产生提案")

    def test_empty_package_still_registers_full_context(self):
        result = self.ps.submit_proposal_package("player1", submit_request())
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(result["data"]["created"], [])
        _, frozen = _frozen_context(self.state)
        self.assertEqual(frozen["submitted_drafts"], [])
        self.assertEqual(set(frozen["war_ids"]),
                         {FIXED["war_ongoing"], FIXED["war_peace"], FIXED["war_passive"]})
        self.assertEqual(len(frozen["wars"]), 3)
        self.assertEqual(self.state.get_senate_proposals(), [])


# ---------------------------------------------------------------------------
# 7) clear_senate_pending 语义收窄
# ---------------------------------------------------------------------------
class TestClearSenatePendingNarrowing(_B1Case):

    def test_clear_resets_voting_workspace_only(self):
        ctx = self.ctx
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_threat"], ctx["consul_id"], reinforcement_n=0),
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=1)]))
        self.assertTrue(result["success"], result.get("errors"))
        # 另一会期的 R6 索引条目（DA-2 B2 起 submit 自身已注册本会期 package/war_item；
        # 本用例验证 clear 不触碰这些事实账本）
        self.assertTrue(self.state.register_consul_war_decision(
            {"senate_session_id": "S-SEED", "direct_decision_id": "cwd_keep"}))
        self.assertTrue(self.state.register_senate_package_record(
            {"package_id": "pkg-keep", "senate_session_id": "S-SEED"}))
        self.assertTrue(self.state.register_senate_war_item(
            "S-SEED", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_SENATE_VOTE, {"ref": 1}))
        self.state.record_senate_vote("player1", 1, True)
        self.state.record_senate_veto(1)
        before = _registry(self.state)
        snapshots_before = len(before["war_snapshots"])
        contexts_before = len(before["contexts"])
        self.assertGreater(snapshots_before, 0)
        self.assertEqual(contexts_before, 1)

        self.state.clear_senate_pending()

        # 投票工作集被清
        self.assertEqual(self.state.get_senate_proposals(), [])
        self.assertEqual(self.state.get_senate_votes_copy(), {})
        self.assertEqual(self.state.get_senate_vetoes_copy(), set())
        self.assertEqual(self.state._senate_pending["proposal_id_counter"], 1)
        self.assertIs(self.state.senate_proposal_decision_complete, False)
        self.assertEqual(self.state.get_senate_direct_actions(), [])
        # 事实账本/索引保持
        after = _registry(self.state)
        self.assertEqual(len(after["war_snapshots"]), snapshots_before)
        self.assertEqual(len(after["contexts"]), contexts_before)
        self.assertIn("pkg-keep", after["packages"])
        self.assertIn(("S-SEED", "cwd_keep"), after["consul_war_decisions"])
        self.assertIn(("S-SEED", FIXED["war_ongoing"]), after["war_items"])
        self.assertEqual(after["by_session"]["S-SEED"], "pkg-keep")
        self.assertEqual(self.state.validate_senate_ledger_consistency(), [])


# ---------------------------------------------------------------------------
# 8) save/load：复合键 rows/list 编码 + 加载重建校验
# ---------------------------------------------------------------------------
class TestLedgerCompositeKeyRoundTrip(_B1Case):

    def test_roundtrip_encodes_rows_and_rebuilds_indexes(self):
        ctx = self.ctx
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_threat"], ctx["consul_id"], reinforcement_n=0),
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=1)]))
        self.assertTrue(result["success"], result.get("errors"))
        # 另一会期的 R6 条目（da-2 B2：本会期 package/war_items 已由 submit 注册）
        self.assertTrue(self.state.register_consul_war_decision(
            {"senate_session_id": "S-SEED", "direct_decision_id": "cwd_1",
             "war_id": FIXED["war_ongoing"]}))
        self.assertTrue(self.state.register_senate_war_item(
            "S-SEED", FIXED["war_ongoing"], WAR_ITEM_AUTHORITY_SENATE_VOTE, {"ref": 1}))
        self.assertTrue(self.state.register_senate_package_record(
            {"package_id": "pkg-1", "senate_session_id": "S-SEED"}))

        data = self.state.to_dict()
        raw = data["_senate_package_ledger"]
        self.assertIsInstance(raw["war_snapshots"], list)
        self.assertEqual(set(raw["war_snapshots"][0]),
                         {"senate_session_id", "war_id", "snapshot"})
        self.assertEqual(set(raw["war_items"][0]),
                         {"senate_session_id", "war_id", "authority", "item_ref"})
        self.assertEqual(set(raw["consul_war_decisions"][0]),
                         {"senate_session_id", "direct_decision_id", "decision"})

        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(copy.deepcopy(data))
        self.assertEqual(set(clone.get_senate_package_registry()["war_snapshots"]),
                         set(_registry(self.state)["war_snapshots"]))
        self.assertEqual(set(clone.get_senate_package_registry()["contexts"]),
                         set(_registry(self.state)["contexts"]))
        self.assertEqual(clone.get_consul_war_decisions("S-SEED")["cwd_1"]["war_id"],
                         FIXED["war_ongoing"])
        self.assertIn(("S1", FIXED["war_ongoing"]), clone.get_senate_war_items("S1"))
        self.assertEqual(clone.get_senate_package_id_for_session("S-SEED"), "pkg-1")
        self.assertEqual(clone.get_senate_package_record("pkg-1")["schema_version"],
                         SENATE_PACKAGE_SCHEMA_VERSION)
        self.assertEqual(clone.get_senate_session(), "S1")
        self.assertEqual(clone.validate_senate_ledger_consistency(), [])

    def test_war_execution_ledger_decisions_rows_roundtrip(self):
        self.state.record_war_decision("S1", 3, {"war_id": "w1", "outcome": "ENACTED"})
        data = self.state.to_dict()
        rows = data["_war_execution_ledger"]["decisions"]
        self.assertIsInstance(rows, list)
        self.assertEqual(rows, [{"senate_session_id": "S1", "proposal_id": 3,
                                 "decision": {"war_id": "w1", "outcome": "ENACTED"}}])
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(copy.deepcopy(data))
        self.assertEqual(clone.get_war_decisions(),
                         {("S1", 3): {"war_id": "w1", "outcome": "ENACTED"}})
        self.assertEqual(clone.validate_senate_ledger_consistency(), [])

    def test_legacy_mapping_shape_still_loads(self):
        data = self.state.to_dict()
        data["_senate_package_ledger"]["war_snapshots"] = {
            ("S1", "w1"): {"war_id": "w1", "type": "war_proposal"}}
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(copy.deepcopy(data))
        self.assertEqual(clone.get_submitted_war_snapshot("S1", "w1"),
                         {"war_id": "w1", "type": "war_proposal"})
        self.assertEqual(clone.validate_senate_ledger_consistency(), [])


# ---------------------------------------------------------------------------
# 9) DA-2 B2：21 code 机器身份 + route → direct 发布会 + claims 5 行
# ---------------------------------------------------------------------------
SUBMIT_ERROR_CODES_B2 = (
    "SUBMIT_REQUEST_INVALID", "SUBMIT_NOT_AUTHORIZED", "SUBMIT_PHASE_INVALID",
    "PACKAGE_ALREADY_SUBMITTED", "SUBMIT_REQUEST_REUSED", "WAR_PROPOSAL_DUPLICATE",
    "WAR_TARGET_INVALID", "WAR_NOT_PROPOSABLE", "WAR_MODE_INVALID", "COMMANDER_REQUIRED",
    "COMMANDER_TARGET_INVALID", "COMMANDER_INELIGIBLE", "REINFORCEMENT_INVALID",
    "PEACE_DRAFT_INVALID", "COMMANDER_CLAIM_DUPLICATE", "GOVERNOR_COMMANDER_CONFLICT",
    "GOVERNOR_NOMINATION_DUPLICATE", "NON_WAR_PROPOSAL_INVALID", "LEGION_POOL_EXCEEDED",
    "SUBMIT_CONTEXT_CHANGED", "SUBMIT_PUBLISH_FAILED",
)


class TestB2SubmitRoute(_B1Case):

    def test_21_code_machine_identity_unchanged(self):
        self.assertEqual(len(PoliticalSystem._SUBMIT_ERROR_CODES), 21)
        self.assertEqual(PoliticalSystem._SUBMIT_ERROR_CODES, SUBMIT_ERROR_CODES_B2)

    def test_ongoing_command_generates_consul_war_decision_without_proposal_id(self):
        ctx = self.ctx
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=0)]))
        self.assertTrue(result["success"], result.get("errors"))
        # Senate 提案集不得混入 direct 项
        self.assertEqual(self.state.get_senate_proposals(), [])
        decisions = self.state.get_consul_war_decisions("S1")
        self.assertEqual(len(decisions), 1, decisions)
        rec = list(decisions.values())[0]
        self.assertEqual(rec["type"], "consul_war_decision")
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")
        self.assertNotIn("proposal_id", rec)
        self.assertNotIn("proposal_ref", rec)
        self.assertEqual(rec["war_id"], FIXED["war_ongoing"])
        self.assertEqual(result["data"]["direct_decisions"][0]["direct_decision_id"],
                         rec["direct_decision_id"])
        # 跨路由 war_items + PackageRecord 真注册
        self.assertIn(("S1", FIXED["war_ongoing"]),
                      self.state.get_senate_war_items("S1"))
        record = self.state.get_senate_package_record(
            self.state.get_senate_package_id_for_session("S1"))
        self.assertEqual(record["direct_decision_refs"],
                         [rec["direct_decision_id"]])
        self.assertEqual(record["proposal_refs"], [])

    def test_mixed_threat_and_ongoing_route_separation(self):
        ctx = self.ctx
        result = self.ps.submit_proposal_package("player1", submit_request(war_drafts=[
            command_draft(FIXED["war_threat"], ctx["consul_id"], reinforcement_n=0),
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=0)]))
        self.assertTrue(result["success"], result.get("errors"))
        snaps = self.state.get_senate_proposals()
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["authority"], "senate_vote")
        self.assertEqual(snaps[0]["war_id"], FIXED["war_threat"])
        self.assertNotIn("direct_decision_id", snaps[0])
        self.assertEqual(len(self.state.get_consul_war_decisions("S1")), 1)

    def test_commander_claims_five_rows(self):
        ctx = self.ctx
        war_ongoing, war_peace, war_threat = (ctx["war_ongoing"], ctx["war_peace"],
                                              ctx["war_threat"])
        real_wars = self.ps._real_wars()
        # 行1（unchecked）+ 行3（Peace）
        claims = self.ps.build_commander_claims(real_wars, [
            {"war_id": war_ongoing.id, "checked": False, "mode": "command",
             "target_commander_id": None, "reinforcement_n": 0},
            {"war_id": war_peace.id, "checked": True, "mode": "peace",
             "target_commander_id": None, "reinforcement_n": None},
        ], [{"war_id": war_threat.id}])
        by = {c["war_id"]: c for c in claims}
        self.assertEqual(by[war_ongoing.id]["basis"], "retained_unchecked")
        self.assertEqual(by[war_ongoing.id]["commander_id"], war_ongoing.commander_id)
        self.assertEqual(by[war_peace.id]["basis"], "retained_peace")
        self.assertEqual(by[war_peace.id]["commander_id"], war_peace.commander_id)
        # 行4：未成真 active candidate unchecked → 无 claim
        self.assertNotIn(war_threat.id, by)
        # 行2：真实 War command direct → selected target 取代旧 claim
        by2 = {c["war_id"]: c for c in self.ps.build_commander_claims(real_wars, [
            {"war_id": war_ongoing.id, "checked": True, "mode": "command",
             "target_commander_id": ctx["cmd_b"].id, "reinforcement_n": 1}], [])}
        self.assertEqual(by2[war_ongoing.id]["basis"], "selected_command")
        self.assertEqual(by2[war_ongoing.id]["commander_id"], ctx["cmd_b"].id)
        # 行5：active candidate checked → selected target
        by3 = {c["war_id"]: c for c in self.ps.build_commander_claims(real_wars, [
            {"war_id": war_threat.id, "checked": True, "mode": "command",
             "target_commander_id": ctx["consul_id"], "reinforcement_n": 0}],
            [{"war_id": war_threat.id}])}
        self.assertEqual(by3[war_threat.id]["basis"], "selected_declaration")
        self.assertEqual(by3[war_threat.id]["commander_id"], ctx["consul_id"])

    def test_empty_package_via_api_registers_context_and_package(self):
        res = senate_api.propose_many(self.state, self.ctx["player_id"], [])
        self.assertTrue(res["success"], res)
        self.assertEqual(res["data"]["created"], [])
        self.assertEqual(res["data"].get("direct_decisions"), [])
        session = self.state.get_senate_session()
        package_id = self.state.get_senate_package_id_for_session(session)
        self.assertIsNotNone(package_id, "空包必须真注册 PackageRecord（D-1 收口）")
        record = self.state.get_senate_package_record(package_id)
        self.assertIsNotNone(self.state.get_submission_context(record["submission_context_id"]))
        self.assertEqual(record["proposal_refs"], [])
        self.assertEqual(record["direct_decision_refs"], [])
        self.assertTrue(self.state.senate_proposal_decision_complete)


# ---------------------------------------------------------------------------
# 10) DA-2 B3：发布事务（SenatePackageTransaction）+ 快照域 + 故障矩阵
# ---------------------------------------------------------------------------
def _raise_fault(*args, **kwargs):
    raise RuntimeError("injected publish fault")


def _false_fault(*args, **kwargs):
    return False


def _senate_only_false(session_id, war_id, authority, item_ref=None):
    """只让 Senate 路由的 war_item 登记失败（direct 正常）→ 专测 commit 前断言闭包。"""
    return authority != WAR_ITEM_AUTHORITY_SENATE_VOTE


def _military_signature(state):
    """军事域零 diff 只读签名（primitive 化，避开对象 __eq__ 身份陷阱）。"""
    ws = state.get_war_system()
    ms = state.get_military_system()
    ns = state.naval_system
    return {
        "treasury": state.treasury,
        "wars": {w.id: [str(w.status), w.commander_id, w.original_commander_id,
                        w.activation_origin, w.activation_turn] for w in ws.get_all_wars()},
        "legions": {lg.number: [lg.war_id, lg.commander_id] for lg in ms.get_all_legions()},
        "fleets": {ft.number: [ft.assigned_war_id, ft.commander_id]
                   for ft in ns.get_all_fleets()},
        "available": sorted(lg.number for lg in ms.get_available_legions()),
    }


class _B3Case(_B1Case):
    """B3 基面：混合包（2 Senate vote 项 + 1 direct 项）。"""

    def _fault_drafts(self):
        ctx = self.ctx
        return [
            command_draft(FIXED["war_threat"], ctx["consul_id"], reinforcement_n=0),  # vote
            peace_draft(FIXED["war_peace"]),                                           # vote
            command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=0),  # direct
        ]

    def _inject(self, name, replacement):
        original = getattr(self.state, name)
        setattr(self.state, name, replacement)
        return lambda: setattr(self.state, name, original)

    def _submit(self, request_id="req-1"):
        return self.ps.submit_proposal_package(
            "player1", submit_request(war_drafts=self._fault_drafts(), request_id=request_id))

    def _run_fault(self, inject):
        s0 = self.state.snapshot_senate_publication_domains()
        mil0 = _military_signature(self.state)
        undo = inject()
        try:
            result = self._submit()
        finally:
            undo()
        self.assertFalse(result["success"], "注入故障必须整包失败")
        self.assertEqual([e["code"] for e in result["errors"]], ["SUBMIT_PUBLISH_FAILED"])
        # S0 深值相等（政治域包含 _senate_session_id）+ 军事域零 diff
        self.assertEqual(self.state.snapshot_senate_publication_domains(), s0,
                         "S0 深值必须完全相等（含 _senate_session_id）")
        self.assertEqual(_military_signature(self.state), mil0, "军事域必须零 diff")
        # 零部分发布
        self.assertEqual(self.state.get_senate_proposals(), [])
        self.assertEqual(self.state.get_consul_war_decisions("S1"), {})
        self.assertEqual(self.state.get_senate_war_items("S1"), {})
        self.assertIsNone(self.state.get_senate_package_id_for_session("S1"))
        self.assertIs(self.state.senate_proposal_decision_complete, False)
        self.assertEqual(self.state._senate_pending["proposal_id_counter"], 1)
        self.assertEqual(self.state.validate_senate_ledger_consistency(), [])
        self.assertIsNone(self.state._senate_transaction_owner, "失败后必须释放锁（非嵌套）")
        return result


class TestB3SnapshotDomain(_B3Case):

    def test_snapshot_domain_is_pending_ledger_and_session_id(self):
        self.state.set_senate_session("S-PRE")
        snap = self.state.snapshot_senate_publication_domains()
        self.assertEqual(set(snap),
                         {"senate_pending", "senate_package_ledger", "senate_session_id"})
        self.assertEqual(snap["senate_session_id"], "S-PRE")
        # 既有边界快照**不**捕获 _senate_session_id → 本事务不得误用它
        self.assertNotIn("_senate_session_id", self.state.snapshot_war_resolution_domains())
        # 确定性恢复
        self.state.set_senate_session("S-MUT")
        self.state.add_senate_proposal({"type": "governor"})
        self.state.register_senate_package_record(
            {"package_id": "pkg-mut", "senate_session_id": "S-MUT"})
        self.state.restore_senate_publication_domains(snap)
        self.assertEqual(self.state.get_senate_session(), "S-PRE")
        self.assertEqual(self.state.get_senate_proposals(), [])
        self.assertIsNone(self.state.get_senate_package_record("pkg-mut"))

    def test_failed_publish_restores_pre_existing_session_id(self):
        # 预置一个已冻结会期身份：故障回滚后必须保持该值（证明 _senate_session_id 在域内）
        self.state.set_senate_session("S0-KEEP")
        result = self._run_fault(lambda: self._inject("set_senate_session", _raise_fault))
        self.assertFalse(result["success"])
        self.assertEqual(self.state.get_senate_session(), "S0-KEEP")


class TestB3TransactionLock(_B3Case):

    def test_non_reentrant_and_cross_transaction_no_nesting(self):
        with SenatePackageTransaction(self.state):
            self.assertEqual(self.state._senate_transaction_owner, "senate_package_publish")
            with self.assertRaises(RuntimeError):
                with SenatePackageTransaction(self.state):
                    pass
            with self.assertRaises(RuntimeError):
                with WarResolutionTransaction(self.state):
                    pass
        self.assertIsNone(self.state._senate_transaction_owner)
        # 释放后可重新进入（单次外层持锁）
        with SenatePackageTransaction(self.state):
            pass
        with WarResolutionTransaction(self.state):
            pass

    def test_publish_holds_lock_and_commits(self):
        result = self._submit()
        self.assertTrue(result["success"], result.get("errors"))
        self.assertIsNone(self.state._senate_transaction_owner, "成功路径必须释放锁")


class TestB3SuccessClosure(_B3Case):

    def test_success_path_closure_refs_ids_counts_route_immutability(self):
        result = self._submit()
        self.assertTrue(result["success"], result.get("errors"))
        created = result["data"]["created"]
        direct = result["data"]["direct_decisions"]
        session_id = self.state.get_senate_session()
        self.assertEqual(session_id, "S1")
        record = self.state.get_senate_package_record(
            self.state.get_senate_package_id_for_session(session_id))
        # counts + IDs/refs
        self.assertEqual(len(created), 2)
        self.assertEqual(len(direct), 1)
        self.assertEqual(record["proposal_refs"], [c["proposal_id"] for c in created])
        self.assertEqual(record["direct_decision_refs"], [d["direct_decision_id"] for d in direct])
        self.assertEqual(record["publication_state"], "COMMITTED")
        # route 分离
        self.assertEqual([s["authority"] for s in self.state.get_senate_proposals()],
                         ["senate_vote", "senate_vote"])
        self.assertEqual([d["authority"] for d in
                          self.state.get_consul_war_decisions(session_id).values()],
                         ["consul_direct"])
        items = self.state.get_senate_war_items(session_id)
        self.assertEqual(items[(session_id, FIXED["war_threat"])]["authority"], "senate_vote")
        self.assertEqual(items[(session_id, FIXED["war_peace"])]["authority"], "senate_vote")
        self.assertEqual(items[(session_id, FIXED["war_ongoing"])]["authority"], "consul_direct")
        # SubmissionContext 真注册且与包同身份
        context = self.state.get_submission_context(record["submission_context_id"])
        self.assertIsNotNone(context)
        self.assertEqual(context["package_id"], record["package_id"])
        # immutability：冻结快照重读与冻结值一致
        frozen = self.state.get_submitted_war_snapshot(session_id, FIXED["war_threat"])
        self.assertEqual(frozen["payload"]["target_commander_id"], self.ctx["consul_id"])
        direct_rec = list(self.state.get_consul_war_decisions(session_id).values())[0]
        self.assertNotIn("proposal_id", direct_rec)
        self.assertEqual(direct_rec["decision_state"], "FROZEN")


class TestB3FaultMatrix(_B3Case):

    def test_each_publish_substep_fault_rolls_back(self):
        cases = {
            "ledger_add_proposal": lambda: self._inject("add_senate_proposal", _raise_fault),
            "war_items_register": lambda: self._inject("register_senate_war_item", _false_fault),
            "direct_decision_register": lambda: self._inject(
                "register_consul_war_decision", _false_fault),
            "package_record_register": lambda: self._inject(
                "register_senate_package_record", _false_fault),
            "session_complete_mark": lambda: self._inject("set_senate_session", _raise_fault),
            "snapshot_register": lambda: self._inject(
                "register_submitted_war_snapshot", _raise_fault),
            "context_register": lambda: self._inject("register_submission_context", _raise_fault),
            "request_binding_register": lambda: self._inject("register_senate_package", _raise_fault),
            "closure_gate_senate_war_item_missing": lambda: self._inject(
                "register_senate_war_item", _senate_only_false),
        }
        for name, inject in cases.items():
            with self.subTest(fault=name):
                self.setUp()
                self._run_fault(inject)

    def test_fault_on_second_vote_add_rolls_back(self):
        calls = {"n": 0}
        original = self.state.add_senate_proposal

        def flaky(proposal):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected fault on second vote add")
            return original(proposal)

        self._run_fault(lambda: self._inject("add_senate_proposal", flaky))
        self.assertEqual(calls["n"], 2)

    def test_after_fault_rollback_system_is_reusable(self):
        self._run_fault(lambda: self._inject("register_senate_package_record", _false_fault))
        # 锁已释放 + 账本已恢复 → 同身份重试可成功
        result = self._submit(request_id="req-retry")
        self.assertTrue(result["success"], result.get("errors"))
        self.assertIsNone(self.state._senate_transaction_owner)
        self.assertEqual(len(result["data"]["created"]), 2)


def _publication_artifacts(state, session_id):
    """DA-2 B4：提交后冻结面只读快照（承载 route / authority / claims / N）。

    全部经**深拷贝 getter** 取回，故任何后续意图改写底账 → 本 dict 不再相等。
    """
    registry = state.get_senate_package_registry()
    package_id = state.get_senate_package_id_for_session(session_id)
    record = state.get_senate_package_record(package_id) if package_id else None
    return {
        "package_id": package_id,
        "record": record,
        "context": (state.get_submission_context(record["submission_context_id"])
                    if record else None),
        "proposals": state.get_senate_proposals(),
        "war_items": state.get_senate_war_items(session_id),
        "consul_war_decisions": state.get_consul_war_decisions(session_id),
        "war_snapshots": {k: v for k, v in registry["war_snapshots"].items()
                          if k[0] == session_id},
    }


class TestB4IdentityReplayImmutability(_B3Case):
    """DA-2 B4（SA §B.4）：request key / intent fingerprint / 重放语义 / success data 形状 / 不可变。

    独立验收面：
    - (a) request key = `(session, actor, request_id)`；intent fingerprint 规范序列化
          （order-independent；忽略 unchecked 缓存 / Peace target-N / 客户端自报 route）；
    - (b) 同键同意图重放 → 返回既有结果（不重复发布、refs 不变）；同键异意图 → 拒绝；
          重放判定**先于**「已非 Proposal」门（会期完成门 / 阶段门）；
    - (c) success data 五字段齐备；`created` 只含真 Senate 提案（不混 direct）；
    - (d) 提交后快照（route / authority / claims / N）不可被后续意图改写。
    """

    # ---------------- (a) request key + fingerprint ----------------

    def test_request_key_binds_session_actor_request_id(self):
        key = GameState.senate_submit_request_key("S1", "player1", "req-1")
        self.assertEqual(key, GameState.senate_submit_request_key("S1", "player1", "req-1"))
        self.assertNotEqual(key, GameState.senate_submit_request_key("S2", "player1", "req-1"))
        self.assertNotEqual(key, GameState.senate_submit_request_key("S1", "player2", "req-1"))
        self.assertNotEqual(key, GameState.senate_submit_request_key("S1", "player1", "req-2"))

    def test_request_index_is_keyed_by_full_triple_not_bare_request_id(self):
        result = self._submit()
        self.assertTrue(result["success"], result.get("errors"))
        keys = set(_registry(self.state)["requests"])
        self.assertIn(GameState.senate_submit_request_key("S1", "player1", "req-1"), keys)
        self.assertNotIn("req-1", keys, "不得只以 request_id 作键（跨会期/跨身份命中面）")
        self.assertEqual(
            _registry(self.state)["requests"][
                GameState.senate_submit_request_key("S1", "player1", "req-1")]["actor_id"],
            "player1")

    def test_requests_lookup_does_not_cross_session_or_actor(self):
        result = self._submit()
        self.assertTrue(result["success"], result.get("errors"))
        package_id = result["data"]["package_id"]
        self.assertEqual(
            self.state.get_senate_submit_request("S1", "player1", "req-1")["package_id"],
            package_id)
        # 跨会期 / 跨 actor 的同名 request_id **不命中**（baseline 会误报重放）
        self.assertIsNone(self.state.get_senate_submit_request("S2", "player1", "req-1"))
        self.assertIsNone(self.state.get_senate_submit_request("S1", "player2", "req-1"))

    def test_same_request_id_in_other_session_is_not_a_replay(self):
        first = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), session="S2", request_id="req-1"))
        self.assertTrue(first["success"], first.get("errors"))
        # 同一 (actor, request_id)、异会期 → **不是**重放：若沿用 baseline「只按 request_id 命中」
        # 会误报 replayed=True 并返回 S2 的包身份；此处必须落到会期完成门。
        second = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), session="S1", request_id="req-1"))
        self.assertFalse(second["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", error_codes(second))
        self.assertFalse(second["data"].get("replayed"))
        self.assertIsNone(self.state.get_senate_submit_request("S1", "player1", "req-1"))
        self.assertEqual(
            self.state.get_senate_submit_request("S2", "player1", "req-1")["package_id"],
            first["data"]["package_id"])

    def test_fingerprint_order_independent(self):
        ctx = self.ctx
        d_threat = command_draft(FIXED["war_threat"], ctx["consul_id"], reinforcement_n=0)
        d_peace = peace_draft(FIXED["war_peace"])
        d_ongoing = command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=1)
        base = self.ps._package_fingerprint([d_threat, d_peace, d_ongoing], [])
        self.assertEqual(base, self.ps._package_fingerprint([d_ongoing, d_threat, d_peace], []))
        self.assertEqual(base, self.ps._package_fingerprint([d_peace, d_ongoing, d_threat], []))
        # 普通提案：列表顺序 + params 插入序均不影响
        p1 = {"type": "governor", "params": {"province_id": 10, "candidate_id": 4}}
        p2 = {"type": "governor", "params": {"candidate_id": 4, "province_id": 10}}
        self.assertEqual(self.ps._package_fingerprint([], [p1, p2]),
                         self.ps._package_fingerprint([], [p2, p1]))

    def test_fingerprint_ignores_unchecked_cache_peace_target_n_and_client_route(self):
        ctx = self.ctx
        base = [
            peace_draft(FIXED["war_peace"]),
            {"war_id": FIXED["war_passive"], "checked": False, "mode": "command",
             "target_commander_id": ctx["cmd_a"].id, "reinforcement_n": 2},
        ]
        # Peace 的 UI target/N 变化 + unchecked 缓存 mode/target/N 变化 + 客户端自报 route
        mutated = [
            {"war_id": FIXED["war_peace"], "checked": True, "mode": "peace",
             "target_commander_id": ctx["cmd_b"].id, "reinforcement_n": 7},
            {"war_id": FIXED["war_passive"], "checked": False, "mode": "peace",
             "target_commander_id": ctx["cmd_b"].id, "reinforcement_n": 5,
             "route": "consul_direct", "authority": "consul_direct"},
        ]
        self.assertEqual(self.ps._package_fingerprint(base, []),
                         self.ps._package_fingerprint(mutated, []))
        # 客户端自报 route/authority 不改变指纹（route 由服务端权威重取）
        a = command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, reinforcement_n=0)
        b = dict(a, route="senate_vote", authority="senate_vote")
        self.assertEqual(self.ps._package_fingerprint([a], []),
                         self.ps._package_fingerprint([b], []))
        # 但 checked 有效意图变化 → 不同指纹
        self.assertNotEqual(self.ps._package_fingerprint([a], []),
                            self.ps._package_fingerprint(
                                [command_draft(FIXED["war_ongoing"], ctx["cmd_b"].id,
                                               reinforcement_n=0)], []))
        self.assertNotEqual(self.ps._package_fingerprint([a], []),
                            self.ps._package_fingerprint(
                                [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id,
                                               reinforcement_n=3)], []))

    # ---------------- (b) 重放语义 ----------------

    def test_same_key_same_intent_replays_without_republish(self):
        r1 = self._submit()
        self.assertTrue(r1["success"], r1.get("errors"))
        self.assertTrue(self.state.senate_proposal_decision_complete)
        before = _publication_artifacts(self.state, "S1")
        n = len(self.state.get_senate_proposals())
        r2 = self._submit()
        self.assertTrue(r2["success"], r2.get("errors"))
        self.assertIs(r2["data"]["replayed"], True)
        self.assertEqual(r2["data"]["package_id"], r1["data"]["package_id"])
        self.assertEqual(r2["data"]["created"], r1["data"]["created"])
        self.assertEqual(r2["data"]["direct_decisions"], r1["data"]["direct_decisions"])
        self.assertEqual(len(self.state.get_senate_proposals()), n, "不得重复发布")
        self.assertEqual(_publication_artifacts(self.state, "S1"), before, "重放不得改写冻结面")

    def test_same_key_diff_intent_rejected_before_completion_gate(self):
        r1 = self._submit()
        self.assertTrue(r1["success"], r1.get("errors"))
        # 同键异意图：原包 3 行 → 此处只 1 行（不同断言）
        r2 = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=[command_draft(FIXED["war_threat"], self.ctx["consul_id"],
                                      reinforcement_n=0)], request_id="req-1"))
        self.assertFalse(r2["success"])
        self.assertEqual(error_codes(r2), ["SUBMIT_REQUEST_REUSED"],
                         "同键异意图必须先于会期完成门被拒")
        self.assertNotIn("PACKAGE_ALREADY_SUBMITTED", error_codes(r2))

    def test_replay_precedes_phase_gate(self):
        r1 = self._submit()
        self.assertTrue(r1["success"], r1.get("errors"))
        # 阶段已非 proposal，但同键同意图重放仍应返回既有结果（重放先于阶段门）
        r2 = self.ps.submit_proposal_package(
            "player1", submit_request(war_drafts=self._fault_drafts(), request_id="req-1"),
            context={"current_step": "combat"})
        self.assertTrue(r2["success"], r2.get("errors"))
        self.assertIs(r2["data"]["replayed"], True)
        self.assertEqual(r2["data"]["package_id"], r1["data"]["package_id"])

    def test_failed_submit_does_not_bind_request_key(self):
        bad = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], None, reinforcement_n=0)],
            request_id="req-retry"))
        self.assertFalse(bad["success"])
        self.assertIsNone(self.state.get_senate_submit_request("S1", "player1", "req-retry"),
                          "失败编辑不得占用 request key（可沿用同一尝试 ID 修正后重提）")
        good = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), request_id="req-retry"))
        self.assertTrue(good["success"], good.get("errors"))

    # ---------------- (c) success data 形状 ----------------

    def test_success_data_five_fields_and_created_excludes_direct(self):
        result = self._submit()
        self.assertTrue(result["success"], result.get("errors"))
        data = result["data"]
        for field in ("created", "direct_decisions", "package_id",
                      "submission_context_id", "submit_request_id"):
            self.assertIn(field, data, f"success data 缺字段 {field}")
        self.assertTrue(data["package_id"])
        self.assertTrue(data["submission_context_id"])
        self.assertEqual(data["submit_request_id"], "req-1")
        self.assertIs(data["submitted"], True)
        self.assertIs(data["replayed"], False)
        # created 只含真 Senate 提案
        self.assertEqual(sorted(c["war_id"] for c in data["created"]),
                         sorted([FIXED["war_threat"], FIXED["war_peace"]]))
        self.assertEqual({c["type"] for c in data["created"]}, {"war_proposal"})
        for created in data["created"]:
            self.assertNotIn("direct_decision_id", created)
        # direct 走 direct_decisions，不得混入 created
        self.assertNotIn(FIXED["war_ongoing"], [c["war_id"] for c in data["created"]])
        self.assertEqual(len(data["direct_decisions"]), 1)
        self.assertEqual(data["direct_decisions"][0]["type"], "consul_war_decision")
        self.assertNotIn("proposal_id", data["direct_decisions"][0])

    # ---------------- (d) 提交后不可变 ----------------

    def test_frozen_publication_immutable_across_later_intents(self):
        r1 = self._submit()
        self.assertTrue(r1["success"], r1.get("errors"))
        package_id = r1["data"]["package_id"]
        before = _publication_artifacts(self.state, "S1")
        # 后续意图 1：异 request id 同会期 → 结构化拒绝
        r2 = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], self.ctx["cmd_b"].id,
                                      reinforcement_n=1)], request_id="req-2"))
        self.assertFalse(r2["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", error_codes(r2))
        # 后续意图 2：同键异意图 → 拒绝
        r3 = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=[peace_draft(FIXED["war_ongoing"])], request_id="req-1"))
        self.assertFalse(r3["success"])
        self.assertIn("SUBMIT_REQUEST_REUSED", error_codes(r3))
        # 后续意图 3：同键同意图重放 → 成功但零改写
        r4 = self._submit()
        self.assertTrue(r4["success"], r4.get("errors"))
        self.assertIs(r4["data"]["replayed"], True)
        self.assertEqual(_publication_artifacts(self.state, "S1"), before,
                         "route / authority / claims / N 均不得被后续意图改写")
        # 逐项实证（不只整体相等）
        record = self.state.get_senate_package_record(package_id)
        self.assertEqual(self.state.get_senate_package_id_for_session("S1"), package_id)
        threat_snap = self.state.get_submitted_war_snapshot("S1", FIXED["war_threat"])
        self.assertEqual(threat_snap["authority"], "senate_vote")
        self.assertEqual(threat_snap["payload"]["target_commander_id"], self.ctx["consul_id"])
        peace_snap = self.state.get_submitted_war_snapshot("S1", FIXED["war_peace"])
        self.assertEqual(peace_snap["mode"], "peace")
        self.assertEqual(peace_snap["authority"], "senate_vote")
        self.assertEqual(peace_snap["payload"]["treaty_snapshot"]["treaty_ref"]["war_id"],
                         FIXED["war_peace"])
        direct_id = record["direct_decision_refs"][0]
        direct_rec = self.state.get_consul_war_decisions("S1")[direct_id]
        self.assertEqual(direct_rec["authority"], "consul_direct")
        self.assertEqual(direct_rec["payload"]["target_commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(direct_rec["payload"]["reinforcement_n"], 0)
        context = self.state.get_submission_context(record["submission_context_id"])
        claims = {c["war_id"]: c for c in context["claims"]}
        self.assertEqual(claims[FIXED["war_ongoing"]]["basis"], "selected_command")
        self.assertEqual(claims[FIXED["war_ongoing"]]["commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(claims[FIXED["war_threat"]]["commander_id"], self.ctx["consul_id"])
        drafts = {d["war_id"]: d for d in context["submitted_drafts"]}
        self.assertEqual(drafts[FIXED["war_ongoing"]]["reinforcement_n"], 0)

    def test_second_session_does_not_touch_first_session_artifacts(self):
        first = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), session="S1", request_id="req-1"))
        self.assertTrue(first["success"], first.get("errors"))
        before = _publication_artifacts(self.state, "S1")
        # 另一会期有自己独立的包身份（by_session 按会期隔离），不触碰 S1 冻结面
        self.assertNotEqual(
            self.state.senate_submit_request_key("S1", "player1", "req-1"),
            self.state.senate_submit_request_key("S2", "player1", "req-1"))
        self.assertEqual(_publication_artifacts(self.state, "S1"), before)


# ---------------------------------------------------------------------------
# B5 — 错误码口径落地（B4-PM-1 裁决 B 窄项；21 code 身份不变）
# ---------------------------------------------------------------------------


class TestB5ErrorCodeLanding(_B3Case):
    """B4-PM-1 裁决 B 落地：M4（legacy 无 request id 同会期二次提交）→ 既有
    `PACKAGE_ALREADY_SUBMITTED`；`retryable` 收窄（仅确证可重试故障为 true）；
    21 code 身份不变。"""

    def test_legacy_second_submit_returns_package_already_submitted(self):
        # legacy 兼容客户端：不提供 request id（服务端不补生成、不绑定）
        first = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), request_id=None))
        self.assertTrue(first["success"], first.get("errors"))
        n = len(self.state.get_senate_proposals())
        before = _publication_artifacts(self.state, "S1")
        # 第二次 legacy 提交 → **既有** structured code（不再伪报 SUBMIT_PUBLISH_FAILED）
        second = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=self._fault_drafts(), request_id=None))
        self.assertFalse(second["success"])
        self.assertEqual(error_codes(second), ["PACKAGE_ALREADY_SUBMITTED"])
        self.assertNotIn("SUBMIT_PUBLISH_FAILED", error_codes(second))
        self.assertEqual(len(self.state.get_senate_proposals()), n, "不得重复发布")
        self.assertEqual(_publication_artifacts(self.state, "S1"), before,
                         "第二次 legacy 提交不得改写冻结面")

    def test_genuine_publish_fault_stays_retryable(self):
        s0 = self.state.snapshot_senate_publication_domains()
        undo = self._inject("register_senate_package_record", _false_fault)
        try:
            result = self._submit(request_id="req-1")
        finally:
            undo()
        self.assertFalse(result["success"])
        self.assertEqual(error_codes(result), ["SUBMIT_PUBLISH_FAILED"])
        details = result["errors"][0]["details"]
        self.assertEqual(details["stage"], "publish")
        # 确证未提交（S0 已精确恢复、by_session 未被占）→ retryable True
        self.assertIs(details["retryable"], True)
        self.assertEqual(self.state.snapshot_senate_publication_domains(), s0)
        self.assertIsNone(self.state.get_senate_package_id_for_session("S1"))

    def test_21_code_identity_unchanged_and_gate_uses_existing_code(self):
        codes = list(PoliticalSystem._SUBMIT_ERROR_CODES)
        self.assertEqual(len(codes), 21)
        self.assertEqual(len(set(codes)), 21, "21 code 机器身份不变（无新增/改名/删除）")
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", codes)
        self.assertIn("SUBMIT_PUBLISH_FAILED", codes)
        # 落地窄项未引入任何新 code：一切错误 codes 均属既有 21 集
        bad = self.ps.submit_proposal_package("player1", submit_request(
            war_drafts=[command_draft(FIXED["war_ongoing"], None, reinforcement_n=0)],
            request_id="req-x"))
        self.assertFalse(bad["success"])
        self.assertTrue(set(error_codes(bad)) <= set(codes))


if __name__ == "__main__":
    unittest.main()
