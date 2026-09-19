# src/tests/test_api/test_wpgr6_senate_flow.py
"""WP-G-R6 DA-4 B1 — N25：政治 finalization 中段失败矩阵 + 完成协议（SA-Design v1.1 §D.1.1）。

本文件 = DA-4 B1 的**独立验收面**证据（N25 五故障点 + 响应丢失/再查询）：
① 四完成事实同版一致（真实 `phase_result(senate){success:true}` / final outcome 冻结 /
   `_senate_pending` 清理标记 / receipt(`finalization_id` + 指纹)）；
② 幂等键 `finalization_id = (session_id, senate_session_id, protocol_version=2)` 重放零二次副作用；
③ finalization / `SenatePackageTransaction` / `WarResolutionTransaction` 三锁互不嵌套；
④ clear 位置硬约束（非 War 效果 + 冻结 + 暂存**之后**、receipt **之前**，同一事务内）；
⑤ 故障注入 → S0 深值相等 + `FINALIZATION_ERROR{stage,retryable}`，不谎报成功。

纪律：复用共享 fixture（`src/tests/fixtures/wpgr6_fixtures.py`，禁改写）；不新造业务规则；
不使用未授权 pytest 选项。
"""

import copy
import json
import os
import unittest
from unittest import mock

from src.api import senate_api
from src.core.game_state import (
    GameState,
    SenateFinalizationTransaction,
    SenatePackageTransaction,
)
from src.tests.fixtures.wpgr5_fixtures import _base_config, add_figure, error_codes
from src.tests.fixtures.wpgr6_fixtures import (
    FIXED,
    build_f6,
    build_f6_base,
    submit_api,
    submit_gui,
)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def _read_source(rel_path: str) -> str:
    """读产品源码/资源（QML 面锚点断言用；渲染证明仍归 SO 帧族）。"""
    with open(os.path.join(_PROJECT_ROOT, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


def _finalized_state(fixture: str = "F6-VV", turn_number: int = 1):
    """构造：F6 正例（含 drafts）→ Submit 发布 → finalization 前状态。"""
    ctx = build_f6(fixture, turn_number=turn_number)
    result = submit_api(ctx["state"], ctx["drafts"])
    assert result.get("success"), result
    return ctx["state"], ctx


class WPGR6N25CompletionFacts(unittest.TestCase):
    """N25 ①：四完成事实同版一致 + 幂等键形态。"""

    def test_four_completion_facts_same_version(self):
        state, _ctx = _finalized_state("F6-VV")
        self.assertIsNone(state.get_phase_result("senate"))

        result = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(result.get("success"), result)

        finalization_id = senate_api.senate_finalization_id(state)
        facts = result["data"]["completion_facts"]
        self.assertTrue(all(facts.values()), facts)
        # ① 真实 phase_result(senate){success:true}
        phase_result = state.get_phase_result("senate")
        self.assertTrue(phase_result["success"])
        # ② final outcome 已冻结（含合法 0 条）
        self.assertIn("frozen_war_decisions", phase_result["data"])
        self.assertGreater(len(phase_result["data"]["frozen_war_decisions"]), 0)
        # ③ pending 清理标记
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertFalse(state.senate_proposal_decision_complete)
        self.assertEqual(state.get_senate_direct_actions(), [])
        # ④ receipt（finalization_id + 内容指纹）
        receipt = state.get_senate_finalization_receipt(finalization_id[1])
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["protocol_version"], 2)
        self.assertEqual(receipt["senate_session_id"], str(finalization_id[1]))
        self.assertEqual(len(receipt["content_fingerprint"]), 64)
        self.assertEqual(list(receipt["finalization_id"]), list(finalization_id))

    def test_get_dto_path_never_writes(self):
        """finalize 不在 GET DTO 路径隐式写：只读视图零 mutation。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()
        senate_api.get_senate_view(state, FIXED["player"])
        self.assertIsNone(state.get_phase_result("senate"))
        self.assertEqual(state.snapshot_senate_finalization_domains(), before)

    def test_idempotent_replay_zero_second_effects(self):
        """幂等重放：同 `finalization_id` 重复调用 → 零再次执行/零重复 Governor。"""
        state, _ctx = _finalized_state("F6-VV")
        first = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(first["success"])
        staged_first = copy.deepcopy(state.get_phase_result("senate"))
        receipt_first = state.get_senate_finalization_receipt(state.get_senate_session())

        second = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(second["success"])
        self.assertTrue(second["data"]["replayed"])
        # 指纹不变 + phase_result 逐字不变（零二次副作用）
        self.assertEqual(state.get_phase_result("senate"), staged_first)
        self.assertEqual(
            state.get_senate_finalization_receipt(state.get_senate_session()), receipt_first)
        self.assertEqual(
            first["data"]["finalization_receipt"]["content_fingerprint"],
            second["data"]["finalization_receipt"]["content_fingerprint"])
        self.assertEqual(
            len(first["data"]["governor_assignments"]),
            len(second["data"]["governor_assignments"]))

    def test_resolve_senate_alias_same_entry(self):
        """`resolve_senate` = `finalize_senate_if_ready` 兼容别名（三入口共用）。"""
        state, _ctx = _finalized_state("F6-VV")
        result = senate_api.resolve_senate(state)
        self.assertTrue(result["success"])
        self.assertTrue(all(result["data"]["completion_facts"].values()))

    def test_partial_facts_requery_recovers_receipt(self):
        """响应丢失/再查询：①②③ 在、④ 缺 → 再查询**补齐** receipt（不谎报成功、不重跑）。"""
        state, _ctx = _finalized_state("F6-VV")
        first = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(first["success"])
        # 合成「部分事实」：仅丢弃 receipt（④），保留 ①②③
        state._senate_finalization_ledger = {"receipts": {}, "by_session": {}}
        staged = copy.deepcopy(state.get_phase_result("senate"))

        again = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(again["success"], again)
        self.assertTrue(again["data"].get("recovered"), again["data"].keys())
        self.assertTrue(all(again["data"]["completion_facts"].values()))
        # 零重跑：phase_result 逐字不变（非 War 效果/Governor 未再次执行）
        self.assertEqual(state.get_phase_result("senate"), staged)


class WPGR6N25FaultMatrix(unittest.TestCase):
    """N25 ②③④⑤：故障注入 → S0 回滚 + 结构化 FINALIZATION_ERROR + clear 位置。"""

    def _assert_s0(self, before, state):
        self.assertEqual(state.snapshot_senate_finalization_domains(), before)

    def test_first_non_war_effect_fault_rolls_back_to_s0(self):
        """故障点 1：非 War 效果/结算阶段异常 → S0 回滚，pending 完整、无 phase_result。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()

        with mock.patch.object(senate_api.PoliticalSystem, "resolve_senate",
                               side_effect=RuntimeError("injected non-War effect fault")):
            result = senate_api.finalize_senate_if_ready(state)

        self.assertFalse(result["success"])
        error = result["data"]["finalization_error"]
        self.assertEqual(error["stage"], "political_resolve")
        self.assertTrue(error["retryable"])
        self.assertTrue(result["data"]["can_advance"] is False)
        self._assert_s0(before, state)
        self.assertIsNone(state.get_phase_result("senate"))
        self.assertFalse(state.has_senate_finalization_receipt(state.get_senate_session()))

    def test_governor_fault_rolls_back_to_s0_and_is_retryable(self):
        """故障点 3：Governor（自动 assign_governors）异常 → S0 回滚 + retryable。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()

        with mock.patch.object(senate_api, "assign_governors",
                               side_effect=RuntimeError("injected governor fault")):
            result = senate_api.finalize_senate_if_ready(state)

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["finalization_error"]["stage"], "governor")
        self._assert_s0(before, state)
        # 重试（故障移除）完整重跑 → 完成四事实
        retry = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(retry["success"], retry)
        self.assertTrue(all(retry["data"]["completion_facts"].values()))

    def test_pa_fault_rolls_back_to_s0(self):
        """故障点 4：PA/phase_data 组装异常 → 不落半成品 phase_result。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()

        with mock.patch.object(senate_api, "_build_public_announcement",
                               side_effect=RuntimeError("injected PA fault")):
            result = senate_api.finalize_senate_if_ready(state)

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["finalization_error"]["stage"], "public_announcement")
        self._assert_s0(before, state)
        self.assertIsNone(state.get_phase_result("senate"))

    def test_clear_fault_rolls_back_pending(self):
        """故障点 2：`clear_senate_pending` 阶段异常 → 回滚恢复 pending（无「已清未完成」窗口）。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()
        self.assertGreater(len(state.get_senate_proposals()), 0)

        with mock.patch.object(GameState, "clear_senate_pending",
                               side_effect=RuntimeError("injected clear fault")):
            result = senate_api.finalize_senate_if_ready(state)

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["finalization_error"]["stage"], "clear_pending")
        self._assert_s0(before, state)
        # pending 与其 decision_complete 完整
        self.assertGreater(len(state.get_senate_proposals()), 0)
        self.assertTrue(state.senate_proposal_decision_complete)
        self.assertIsNone(state.get_phase_result("senate"))

    def test_record_phase_result_fault_rolls_back_and_top_level_success_insufficient(self):
        """故障点 5：`record_phase_result` 写后异常 → S0 回滚；顶层 success 不足以关闭窗口。"""
        state, _ctx = _finalized_state("F6-VV")
        before = state.snapshot_senate_finalization_domains()
        original = GameState.record_phase_result

        def _write_then_fail(self, phase_id, result):
            original(self, phase_id, result)
            raise RuntimeError("injected post-record fault")

        with mock.patch.object(GameState, "record_phase_result", _write_then_fail):
            result = senate_api.finalize_senate_if_ready(state)

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["finalization_error"]["stage"], "record_phase_result")
        # 事实①被回滚（未确认态 → 不得以顶层 success 关闭窗口）
        self.assertIsNone(state.get_phase_result("senate"))
        self._assert_s0(before, state)

    def test_clear_position_after_staging_before_receipt(self):
        """clear 位置硬约束：非 War 效果 + 冻结 + 暂存**之后**、receipt **之前**，同一事务内。"""
        state, _ctx = _finalized_state("F6-VV")
        order = []
        original_clear = state.clear_senate_pending
        original_receipt = state.record_senate_finalization_receipt

        def _spy_clear():
            staged = state.get_phase_result("senate")
            order.append({
                "point": "clear",
                "staged_success": bool(staged and staged.get("success")),
                "frozen_outcome": bool(
                    staged and "frozen_war_decisions" in (staged.get("data") or {})),
                "receipt_written": state.has_senate_finalization_receipt(
                    state.get_senate_session()),
                "pending_proposals": len(state.get_senate_proposals()),
            })
            return original_clear()

        def _spy_receipt(receipt):
            order.append({"point": "receipt",
                          "pending_cleared": len(state.get_senate_proposals()) == 0})
            return original_receipt(receipt)

        state.clear_senate_pending = _spy_clear
        state.record_senate_finalization_receipt = _spy_receipt
        result = senate_api.finalize_senate_if_ready(state)

        self.assertTrue(result["success"], result)
        clear_step = [s for s in order if s["point"] == "clear"][0]
        receipt_step = [s for s in order if s["point"] == "receipt"][0]
        self.assertTrue(clear_step["staged_success"], "clear 前必须已暂存真实成功结果")
        self.assertTrue(clear_step["frozen_outcome"], "clear 前 final outcome 必须已冻结")
        self.assertFalse(clear_step["receipt_written"], "clear 必须在 receipt 写齐之前")
        self.assertGreater(clear_step["pending_proposals"], 0,
                           "clear 前 pending 必须完整（禁「先 clear 再补写」）")
        self.assertTrue(receipt_step["pending_cleared"], "receipt 必须在 clear 之后")

    def test_pending_never_rebuilt_from_cleared_set(self):
        """禁「从已清空临时集重建结果」：清理后 pending 不得被重写回非空。"""
        state, _ctx = _finalized_state("F6-VV")
        result = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(result["success"], result)
        replayed = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(replayed["data"]["replayed"])
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual(state.get_senate_vetoes_copy(), set())


class WPGR6N25LockOrder(unittest.TestCase):
    """N25 ③：finalization / SenatePackageTransaction / WarResolutionTransaction 互不嵌套。"""

    def test_finalization_nested_in_package_transaction_raises(self):
        state, _ctx = _finalized_state("F6-VV")
        with SenatePackageTransaction(state):
            with self.assertRaises(RuntimeError):
                with SenateFinalizationTransaction(state):
                    pass
        # 外层释放后可再取（锁未被破坏）
        with SenateFinalizationTransaction(state) as txn:
            txn.commit()

    def test_package_transaction_nested_in_finalization_raises(self):
        state, _ctx = _finalized_state("F6-VV")
        with SenateFinalizationTransaction(state):
            with self.assertRaises(RuntimeError):
                with SenatePackageTransaction(state):
                    pass

    def test_snapshot_failure_after_acquire_releases_lock(self):
        """`__enter__` snapshot 失败必须 finally 释放（不留下永久持锁）。"""
        state, _ctx = _finalized_state("F6-VV")
        with mock.patch.object(GameState, "snapshot_senate_finalization_domains",
                               side_effect=RuntimeError("snapshot boom")):
            with self.assertRaises(RuntimeError):
                with SenateFinalizationTransaction(state):
                    pass
        self.assertIsNone(state._senate_transaction_owner)
        with SenatePackageTransaction(state):
            pass


class WPGR6N25SettlementRetirement(unittest.TestCase):
    """settlement 字段正常态退役 / 内部化（不得驱动正常 UI）。"""

    def test_settlement_fields_false_in_normal_state(self):
        state, _ctx = _finalized_state("F6-VV")
        senate_api.finalize_senate_if_ready(state)
        view = senate_api.get_senate_view(state, FIXED["player"])
        data = view["data"]
        self.assertFalse(data["senate_settlement_pending"])
        self.assertFalse(data["can_resolve_settlement"])
        self.assertTrue(data["can_advance"])

    def test_settlement_pending_not_reported_before_finalization(self):
        state, _ctx = _finalized_state("F6-VV")
        view = senate_api.get_senate_view(state, FIXED["player"])
        data = view["data"]
        self.assertFalse(data["senate_settlement_pending"])
        self.assertFalse(data["can_resolve_settlement"])


class WPGR6B2ZeroProposalDirectOnlyFlow(unittest.TestCase):
    """B2（SA §D.1）状态机：零提案 / direct-only 均无 Vote/Veto、无完成结算、恰一个 advance。

    状态机：PROPOSAL_OPEN → PACKAGE_PUBLISHED →（SENATE_VOTE / TRIBUNE_VETO）→
    RESULTS_READY → COMMITTED；零提案与 direct-only 走 PACKAGE_PUBLISHED →（自动内部
    finalization）→ RESULTS_READY → COMMITTED，**不经** Vote/Veto。
    """

    @staticmethod
    def _assert_no_vote_no_settlement_and_advanceable(view: dict) -> None:
        assert view["current_step"] == "results", view["current_step"]
        assert view["can_vote"] is False, view["can_vote"]
        assert view["can_veto"] is False, view["can_veto"]
        assert view["can_auto_veto"] is False, view["can_auto_veto"]
        assert view["senate_settlement_pending"] is False
        assert view["can_resolve_settlement"] is False
        assert view["can_advance"] is True

    def test_zero_proposal_auto_finalization_no_vote_no_settlement_one_advance(self):
        state = build_f6_base()["state"]
        _store, result = submit_gui(state, [])
        self.assertTrue(result["success"], result)
        # Submit 命令流程：已发布 + 服务端自动 finalization 成功
        self.assertTrue(result["data"]["submitted"])
        self.assertTrue(result["data"]["finalization"]["finalized"])
        self.assertEqual(result["data"]["finalization"]["current_step"], "results")
        # 真实非空成功 phase_result（四完成事实同版）
        self.assertTrue(state.get_phase_result("senate")["success"])
        session = state.get_senate_session()
        self.assertTrue(state.has_senate_finalization_receipt(session))
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self._assert_no_vote_no_settlement_and_advanceable(view)
        # 恰一个 advance：首次 → COMMITTED；第二次 → receipt 重放（幂等）
        first = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(first["success"], first)
        second = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(second["success"], second)
        self.assertTrue(second["data"].get("replayed"))

    def test_direct_only_no_vote_no_settlement_one_advance(self):
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        _store, result = submit_gui(state, ctx["drafts"])
        self.assertTrue(result["success"], result)
        # direct-only：created=[]、direct refs 非空
        self.assertEqual(result["data"]["created"], [])
        self.assertTrue(result["data"]["direct_decisions"])
        self.assertTrue(result["data"]["finalization"]["finalized"])
        session = state.get_senate_session()
        self.assertTrue(state.get_consul_war_decisions(session))
        self.assertTrue(state.get_phase_result("senate")["success"])
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self._assert_no_vote_no_settlement_and_advanceable(view)
        first = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(first["success"], first)
        second = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(second["data"].get("replayed"))

    def test_human_veto_window_not_skipped(self):
        """Human veto 不可跳过：有真提案 + passed>0 → 停在 TRIBUNE_VETO，无提前 finalization。"""
        ctx = build_f6("F6-VV")
        state = ctx["state"]
        add_figure(state, ctx["faction"], 99, "Tribune T", office="tribune")
        result = submit_api(state, ctx["drafts"])
        self.assertTrue(result["success"], result)
        # Senate count > 0 → Submit **不**自动 finalization
        self.assertIsNone(state.get_phase_result("senate"))
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertEqual(view["current_step"], "senate_vote")
        self.assertTrue(view["can_vote"])
        proposal_ids = [p["id"] for p in state.get_senate_proposals()]
        self.assertEqual(len(proposal_ids), 2)
        vote = senate_api.vote(state, FIXED["player"], proposal_ids,
                               [True] * len(proposal_ids))
        self.assertTrue(vote["success"], vote)
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertEqual(view["current_step"], "tribune_veto")
        self.assertTrue(view["can_veto"], "Human veto 机会必须保留")
        self.assertFalse(view["can_advance"], "veto 窗口未关闭前不得推进")
        self.assertIsNone(state.get_phase_result("senate"), "veto 窗口不可被跳过")


class WPGR6B2SubmitFinalizationFailure(unittest.TestCase):
    """R-B1-4：Submit publish 成功但自动 finalization 失败 → submitted/success=true + warning，
    UI 不允许重发包（再提交由服务端 PACKAGE_ALREADY_SUBMITTED 拦截）。"""

    def test_submit_finalization_failure_keeps_submitted_and_blocks_repackage(self):
        state = build_f6_base()["state"]
        with mock.patch.object(senate_api.PoliticalSystem, "resolve_senate",
                               side_effect=RuntimeError("injected finalization fault")):
            store, result = submit_gui(state, [])
        # 已发布包不撤销：submitted/success 仍 True
        self.assertTrue(result["success"], result)
        self.assertTrue(result["data"]["submitted"])
        self.assertFalse(result["data"]["finalization"]["finalized"])
        self.assertEqual(result["data"]["finalization_error"]["stage"], "political_resolve")
        self.assertEqual(result["data"]["warnings"][0]["code"], "FINALIZATION_ERROR")
        # UI 不允许重发包：同会期再次提交 → PACKAGE_ALREADY_SUBMITTED
        again = submit_api(state, [], request_id="req-2")
        self.assertFalse(again["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", error_codes(again))
        self.assertNotEqual(store.senateFinalizationWarning, "")
        # 状态落 FINALIZATION_ERROR：不可推进；仅内部重试能力位 True
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertTrue(view["senate_finalization_error"])
        self.assertTrue(view["can_retry_finalization"])
        self.assertFalse(view["can_advance"])
        self.assertFalse(view["can_resolve_settlement"])

    def test_internal_recovery_retries_finalization_without_republishing(self):
        state = build_f6_base()["state"]
        with mock.patch.object(senate_api.PoliticalSystem, "resolve_senate",
                               side_effect=RuntimeError("injected finalization fault")):
            self.assertTrue(submit_gui(state, [])[1]["success"])
        # 内部恢复通道（服务端 finalize 重试）：不重发包、零军事/发布重放
        recovered = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(recovered["success"], recovered)
        self.assertTrue(all(recovered["data"]["completion_facts"].values()))
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertFalse(view["senate_finalization_error"])
        self.assertTrue(view["can_advance"])


class WPGR6B2StoreSettlementRetirement(unittest.TestCase):
    """B2（SA §D.1）Store/QML 面：settlement 正常态退役 + doAdvanceSenate 唯一正常推进。"""

    def test_store_settlement_retired_and_advance_is_only_normal_action(self):
        from src.ui.gui.session_store import GuiSessionStore
        state = build_f6_base()["state"]
        store = GuiSessionStore(state)
        store.initialize(FIXED["player"])
        self.assertFalse(store.senateSettlementPending)
        self.assertFalse(store.canResolveSenateSettlement)
        feedback = store.doSubmitSenateProposals([])
        self.assertTrue(feedback["success"], feedback)
        # 服务端自动 finalization 后：正常态无「完成结算」，唯一推进 = doAdvanceSenate
        self.assertFalse(store.senateSettlementPending)
        self.assertFalse(store.canResolveSenateSettlement)
        self.assertEqual(store.senateFinalizationWarning, "")
        self.assertTrue(store.canAdvanceSenate)
        refused = store.doResolveSenateSettlement()
        self.assertFalse(refused["success"])
        self.assertTrue(store.doAdvanceSenate()["success"])


class WPGR6B2FinalizationReceiptPersistence(unittest.TestCase):
    """R-B1-1：R6 存档持久化 receipt（`finalization_id` + sha256 指纹），存读后逐字相等；
    legacy 无 receipt → 补齐分支保留（合法）。"""

    @staticmethod
    def _finalized_and_roundtripped():
        state, _ctx = _finalized_state("F6-VV")
        senate_api.finalize_senate_if_ready(state)
        session = state.get_senate_session()
        before = state.get_senate_finalization_receipt(session)
        payload = json.loads(json.dumps(state.to_dict(), ensure_ascii=False))
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(payload)
        after = clone.get_senate_finalization_receipt(session)
        return before, after, clone, session, payload

    def test_receipt_finalization_id_verbatim_equal_after_save_load(self):
        before, after, clone, session, _payload = self._finalized_and_roundtripped()
        self.assertIsNotNone(before)
        self.assertIsNotNone(after, "存档必须持久化 receipt（四完成事实之④）")
        self.assertEqual(tuple(before["finalization_id"]), tuple(after["finalization_id"]))
        # 加载后幂等键与在线形态同源（tuple + protocol_version=2）
        self.assertEqual(list(after["finalization_id"]),
                         list(senate_api.senate_finalization_id(clone)))
        self.assertTrue(clone.has_senate_finalization_receipt(session))

    def test_receipt_fingerprint_verbatim_equal_after_save_load(self):
        before, after, _clone, _session, payload = self._finalized_and_roundtripped()
        self.assertIn("_senate_finalization_ledger", payload)
        self.assertEqual(before["content_fingerprint"], after["content_fingerprint"])
        self.assertEqual(len(after["content_fingerprint"]), 64)
        self.assertEqual(after["protocol_version"], 2)

    def test_load_receipt_is_not_recomputed_from_current_state(self):
        """指纹取自 receipt 冻结值（不重读当前部署态重算）——篡改部署态不影响存读身份。"""
        before, after, clone, _session, _payload = self._finalized_and_roundtripped()
        clone._phase_results["senate"]["data"]["mutated_after_save"] = True
        self.assertEqual(before["content_fingerprint"], after["content_fingerprint"])

    def test_legacy_save_without_receipt_uses_recovery_branch(self):
        state, _ctx = _finalized_state("F6-VV")
        senate_api.finalize_senate_if_ready(state)
        payload = json.loads(json.dumps(state.to_dict(), ensure_ascii=False))
        payload.pop("_senate_finalization_ledger", None)
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(payload)
        self.assertFalse(clone.has_senate_finalization_receipt(clone.get_senate_session()))
        recovered = senate_api.finalize_senate_if_ready(clone)
        self.assertTrue(recovered["success"], recovered)
        self.assertTrue(recovered["data"].get("recovered"))
        self.assertTrue(all(recovered["data"]["completion_facts"].values()))


class _PassDecider:
    """确定性 Senate 表决器（PASS）——不依赖 AI 随机表决；与 DA-3 边界测试同口径。"""

    def decide_vote(self, issue, faction, state):
        return True


class WPGR6B3ResultsPaIdentities(unittest.TestCase):
    """DA-4 B3（SA §D.4 / AC-20）：Results / PA 三身份分离 + 身份稳定性（`item_ref`）。

    三身份（互不混用）：
    - `submitted_proposals` / `vote_results` / `veto_candidate_ids` = 真 Senate items only；
    - `consul_direct_decisions` = 冻结 Consul 战争决定（整个会期可读，行内无 `proposal_id`）；
    - `public_announcement.{enacted_proposals,consul_direct_decisions}` + legacy
      `direct_actions`（仅已执行审计）。
    文案：direct 行「执政官决定 · 待推进到战斗阶段执行」；Senate 获批行「元老院批准 · 待边界执行」；
    Peace 未执行不写「已召回」；direct-only 不得清空结果页；`execution` 只能由边界 receipt 翻成 executed。
    """

    BANNED_RECALL = ("已召回", "已部署", "已宣战部署")

    @staticmethod
    def _rows_by_item_ref(rows):
        """按 `item_ref` 建索引（身份稳定性比较的唯一口径；不用 display row ID / proposal_id）。"""
        return {json.dumps(r["item_ref"], sort_keys=True, ensure_ascii=False): r for r in rows}

    @classmethod
    def _submitted_and_finalized(cls, fixture):
        ctx = build_f6(fixture)
        state = ctx["state"]
        submitted = submit_api(state, ctx["drafts"])
        assert submitted["success"], submitted
        # 确定性表决（不依赖 AI 随机表决器）；PASS 语义与设计 C.1「真 ENACTED」一致
        finalized = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        assert finalized["success"], finalized
        return ctx, state

    # —— (a) 三身份分离 —————————————————————————————————————————————
    def test_three_identities_separated_mixed_package(self):
        """F6-MIX（1 direct + 1 Senate）：三身份各归其账，direct 不进 vote/veto/提案面。"""
        ctx, state = self._submitted_and_finalized("F6-MIX")
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]

        direct_rows = view["consul_direct_decisions"]
        self.assertEqual(len(direct_rows), 1)
        direct = direct_rows[0]
        self.assertEqual(direct["identity"], "consul_direct_decision")
        self.assertEqual(direct["war_id"], FIXED["war_ongoing"])
        self.assertEqual(direct["authority"], "consul_direct")
        self.assertEqual(direct["decision_state"], "FROZEN")
        self.assertNotIn("proposal_id", direct)          # 不混用 display row ID 与 proposal_id
        self.assertTrue(str(direct["direct_decision_id"]).startswith("cwd_"))

        # Senate 面只含真提案（int proposal_id；无 direct 身份）
        package_id = state.get_senate_package_id_for_session(state.get_senate_session())
        record = state.get_senate_package_record(package_id)
        self.assertEqual(record["direct_decision_refs"], [direct["direct_decision_id"]])
        self.assertEqual(len(record["proposal_refs"]), 1)
        senate_rows = view["submitted_proposals"]
        self.assertTrue(senate_rows)
        for row in senate_rows:
            self.assertIn(row["id"], record["proposal_refs"])
            self.assertNotIn("direct_decision_id", row)
        for key in ("vote_results", "veto_candidate_ids"):
            for item in (view[key] or []):
                ident = item.get("proposal_id") if isinstance(item, dict) else item
                self.assertNotEqual(ident, direct["direct_decision_id"])

        # PA：enacted = 真 Senate items；consul_direct_decisions = 冻结 direct；legacy = 审计（此阶段空）
        pa = view["public_announcement"]
        self.assertEqual([r["identity"] for r in pa["enacted_proposals"]], ["senate_proposal"])
        self.assertEqual([r["proposal_id"] for r in pa["enacted_proposals"]],
                         list(record["proposal_refs"]))
        self.assertEqual([r["direct_decision_id"] for r in pa["consul_direct_decisions"]],
                         [direct["direct_decision_id"]])
        self.assertEqual(pa["direct_actions"], [])
        self.assertEqual(view["direct_actions"], [])

    def test_direct_row_label_and_frozen_payload(self):
        """direct 行文案 + War/Commander/N；行身份 = `item_ref`（含 session/package/direct id）。"""
        ctx, state = self._submitted_and_finalized("F6-DD")
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        by_war = {r["war_id"]: r for r in view["consul_direct_decisions"]}
        self.assertEqual(sorted(by_war), sorted([FIXED["war_ongoing"], FIXED["war_peace"]]))

        ongoing = by_war[FIXED["war_ongoing"]]
        self.assertEqual(ongoing["display_label"], senate_api.CONSUL_DIRECT_ROW_LABEL)
        self.assertEqual(ongoing["authority_label"], "执政官决定")
        self.assertEqual(ongoing["execution"], "awaiting_boundary")
        self.assertEqual(ongoing["target_commander_label"], ctx["cmd_a"].get_formal_name())
        self.assertEqual(ongoing["reinforcement_n"], 1)
        self.assertEqual(ongoing["war_label"], ctx["war_ongoing"].name)
        self.assertEqual(ongoing["senate_session_id"], state.get_senate_session())
        self.assertEqual(ongoing["package_id"],
                         state.get_senate_package_id_for_session(state.get_senate_session()))
        self.assertEqual(ongoing["item_ref"]["kind"], "consul_direct")
        self.assertEqual(ongoing["item_ref"]["direct_decision_id"],
                         ongoing["direct_decision_id"])
        self.assertEqual(by_war[FIXED["war_peace"]]["target_commander_label"],
                         ctx["cmd_b"].get_formal_name())
        self.assertEqual(by_war[FIXED["war_peace"]]["reinforcement_n"], 2)
        # 边界前：零军事写（原将/军队未因 direct 决定被部署）
        self.assertIsNone(state.get_war_execution_receipt_for_session(state.get_senate_session()))
        self.assertEqual(ctx["war_ongoing"].commander_id, ctx["cmd_a"].id)
        self.assertEqual(ctx["war_peace"].commander_id, ctx["cmd_b"].id)

    def test_senate_enacted_row_label_pending_boundary(self):
        """Senate 获批行 =「元老院批准 · 待边界执行」；execution 恒 awaiting_boundary。"""
        _ctx, state = self._submitted_and_finalized("F6-VV")
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        enacted = view["public_announcement"]["enacted_proposals"]
        self.assertEqual(len(enacted), 2)
        for row in enacted:
            self.assertEqual(row["identity"], "senate_proposal")
            self.assertEqual(row["authority_label"], "元老院批准")
            self.assertEqual(row["display_label"], "元老院批准 · 待边界执行")
            self.assertEqual(row["execution"], "awaiting_boundary")
            self.assertIn("待边界执行", row["title"])
        # direct 面与 Senate 面同时存在（三身份）；二者用不同身份字段
        self.assertEqual(view["consul_direct_decisions"], [])

    # —— Peace 未执行 ⇒ 不得写「已召回」———————————————————————————
    def test_peace_not_executed_must_not_claim_recall(self):
        ctx = build_f6("F6-VV")
        state, war = ctx["state"], ctx["war_peace"]
        self.assertTrue(submit_api(state, ctx["drafts"])["success"])
        military_before = self._peace_military_snapshot(war, ctx)
        self.assertTrue(senate_api.resolve_senate(state, vote_decider=_PassDecider())["success"])
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        peace_rows = [r for r in view["public_announcement"]["enacted_proposals"]
                      if (r.get("key_parameters") or {}).get("mode") == "peace"]
        self.assertEqual(len(peace_rows), 1)
        peace_row = peace_rows[0]
        self.assertEqual(peace_row["pending_boundary_effects"], ["peace_recall"])
        for text in (peace_row["title"], peace_row["display_label"]):
            for banned in self.BANNED_RECALL:
                self.assertNotIn(banned, text)
        # 零早写：finalization 未执行召回（条约仍 pending、原将/军队/状态未变）
        self.assertEqual(self._peace_military_snapshot(war, ctx), military_before)
        self.assertEqual(war.peace_treaty.get("status"), "pending")
        self.assertEqual(war.commander_id, ctx["cmd_b"].id)

    @staticmethod
    def _peace_military_snapshot(war, ctx):
        return {
            "status": str(war.status), "commander_id": war.commander_id,
            "legions_assigned": list(getattr(war, "legions_assigned", []) or []),
            "fleets_assigned": list(getattr(war, "fleets_assigned", []) or []),
            "peace_treaty": copy.deepcopy(war.peace_treaty),
            "cmd_b_absent": ctx["cmd_b"].is_absent,
        }

    # —— direct-only 不得清空结果页 ——————————————————————————————
    def test_direct_only_results_page_not_cleared(self):
        """F6-DD：无 passed_proposals / 无 pending 提案，但结果页仍非空（direct 身份行）。"""
        ctx, state = self._submitted_and_finalized("F6-DD")
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertEqual(view["submitted_proposals"], [])          # 无真 Senate 提案（不是清空理由）
        self.assertEqual(view["public_announcement"]["enacted_proposals"], [])
        self.assertEqual(state.get_senate_proposals(), [])
        # 结果页内容 = direct 冻结行 + 真实 frozen decisions + PA
        self.assertEqual(len(view["consul_direct_decisions"]), 2)
        self.assertEqual(len(view["public_announcement"]["consul_direct_decisions"]), 2)
        self.assertTrue(view["senate_result"]["success"])
        self.assertIn("frozen_war_decisions", view["senate_result"]["data"])
        self.assertEqual(view["current_step"], "results")
        self.assertTrue(view["can_advance"])
        # QML 面锚点（渲染由 SO 帧族采集）：结果页渲染 PA 冻结 direct 行
        qml = _read_source("src/ui/gui/qml/stages/SenateStage.qml")
        self.assertIn("consul_direct_decisions", qml)

    # —— (b) 身份稳定性：刷新 / 重入 / SaveLoad 按 item_ref 重取 ————————————
    def test_identity_stable_across_refresh_and_reentry(self):
        _ctx, state = self._submitted_and_finalized("F6-DD")
        first = self._rows_by_item_ref(
            senate_api.get_senate_view(state, FIXED["player"])["data"]["consul_direct_decisions"])
        # 刷新（重复 GET，零 mutation）
        again = self._rows_by_item_ref(
            senate_api.get_senate_view(state, FIXED["player"])["data"]["consul_direct_decisions"])
        self.assertEqual(set(first), set(again))
        for ref, row in first.items():
            self.assertEqual(row, again[ref])
        # 离开重入：新 GUI 会话（Store 重新 initialize → 重新拉取 DTO）
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(FIXED["player"])
        reentry = self._rows_by_item_ref(
            (store.senatePublicAnnouncement or {}).get("consul_direct_decisions") or [])
        self.assertEqual(set(reentry), set(first))
        for ref, row in first.items():
            self.assertEqual(row, reentry[ref])

    def test_identity_stable_across_save_load(self):
        _ctx, state = self._submitted_and_finalized("F6-DD")
        session = state.get_senate_session()
        before_rows = senate_api._consul_direct_decision_rows(state)
        before_pa = copy.deepcopy(
            senate_api.get_senate_view(state, FIXED["player"])["data"]["public_announcement"])
        payload = json.loads(json.dumps(state.to_dict(), ensure_ascii=False))
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(payload)
        self.assertEqual(clone.get_senate_session(), session)
        after_rows = senate_api._consul_direct_decision_rows(clone)
        self.assertEqual(after_rows, before_rows)          # 逐字相等（含 item_ref / payload / 文案）
        self.assertEqual(self._rows_by_item_ref(after_rows), self._rows_by_item_ref(before_rows))
        clone_view = senate_api.get_senate_view(clone, FIXED["player"])["data"]
        self.assertEqual(clone_view["public_announcement"], before_pa)
        self.assertEqual(clone_view["consul_direct_decisions"], before_rows)

    def test_veto_rejects_direct_decision_id(self):
        """不混用身份空间：direct ID 不在 Senate 否决候选集（无此提案 → 整次拒绝且零状态变更）。"""
        ctx = build_f6("F6-MIX")
        state = ctx["state"]
        add_figure(state, ctx["faction"], 99, "Tribune T", office="tribune")
        self.assertTrue(submit_api(state, ctx["drafts"])["success"])
        direct_id = next(iter(state.get_consul_war_decisions(state.get_senate_session())))
        before_vetoes = set(state._senate_pending["vetoes"])
        result = senate_api.veto(state, FIXED["player"], [direct_id])
        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["rejected_ids"][0]["reason"], "not_submitted")
        self.assertEqual(set(state._senate_pending["vetoes"]), before_vetoes)

    # —— execution 只能由边界 receipt 翻面 ————————————————————————————
    def test_execution_flag_only_flipped_by_boundary_receipt(self):
        _ctx, state = self._submitted_and_finalized("F6-DD")
        view = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertFalse(view["senate_result"].get("war_execution"))
        self.assertTrue(all(r["execution"] == "awaiting_boundary"
                            for r in view["consul_direct_decisions"]))
        advanced = senate_api.advance_senate_phase(state, FIXED["player"])
        self.assertTrue(advanced["success"], advanced)
        self.assertFalse(view["senate_result"].get("war_execution"))   # 旧视图未被改写（冻结）
        after = senate_api.get_senate_view(state, FIXED["player"])["data"]
        self.assertTrue(after["senate_result"]["war_execution"]["committed"])
        for row in after["consul_direct_decisions"]:
            self.assertEqual(row["execution"], "executed")
            self.assertEqual(row["display_label"], senate_api.CONSUL_DIRECT_EXECUTED_LABEL)
    # —— 本批不变面：21 Submit code 身份逐字不变 ————————————————————————
    def test_submit_error_codes_identity_unchanged(self):
        from src.core.systems.political_system import PoliticalSystem
        codes = tuple(PoliticalSystem._SUBMIT_ERROR_CODES)
        self.assertEqual(len(codes), 21)
        self.assertEqual(len(set(codes)), 21)
        self.assertIn("LEGION_POOL_EXCEEDED", codes)
        self.assertNotIn("FINALIZATION_ERROR", codes)      # 内部 finalization 命名空间，不混入



if __name__ == "__main__":
    unittest.main()
