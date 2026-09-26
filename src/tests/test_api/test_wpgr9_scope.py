# src/tests/test_api/test_wpgr9_scope.py
"""WP-G-R9 DA（SA-Design v1.1 §3/§5；FC-R9-01…09）— API 顶层 direct 投影作用域收敛。

本片（DATA；RENDER 归 fresh G5 / Owner）锁定「Resolved-War Senate Actionability
Exclusion」的数据面（不含截图）：

- **T01**：真实 `propose_many` 发布 Turn N package/direct → 顶层
  `consul_direct_decisions` 当前会期保留；TRIUMPH/VICTORY → RESOLVED 的 target 不在
  `war_cards`（合法正对照仍在），**同会期 Results 冻结 direct 行仍只读保留**；
  N+1 作用域排除（组件负例，**仅改 turn** ⇒ 标 `MOCK_AUXILIARY`，**不冒充 T04 真实年度链**）。
- **T02**：当前合法 Senate 窗口提交已 RESOLVED war 的 checked draft → `WAR_TARGET_INVALID`，
  all-or-nothing，零 War 突变 / 零奖励重放 / 零将领·军团·舰队重指派 / 零发布；混合合法包整体拒。
- **T03**：canonical 会期**仅**由有效 PackageRecord 证明（**7 类参数化对照，逐例唯一
  expected**，承 PM ADDENDUM 01）：无包一律排除、坏包排除**不 fallback**、未知 custom 排除、
  SaveLoad 同版重判。异常 metadata 用例标 `MOCK_AUXILIARY`（**不声称已证真实 legacy 回归**）。

T05（受影响回归 = R7/R4/authority 既有锚点）无新增文件；T06 全量回归在报告登记。
"""
import copy
import json
import unittest

from src.api import senate_api
from src.core.game_state import GameState
from src.core.entities.war import WarStatus
from src.ui.gui.session_store import GuiSessionStore
from src.tests.fixtures.wpgr5_fixtures import FIXED, command_draft, error_codes, _base_config
from src.tests.fixtures.wpgr6_fixtures import build_f6_base, submit_api


def _view(state, player_id=FIXED["player"]):
    result = senate_api.get_senate_view(state, player_id)
    assert result["success"], result.get("message")
    return result["data"]


def _top_direct_rows(state, player_id=FIXED["player"]):
    return _view(state, player_id)["consul_direct_decisions"]


def _unscoped_rows(state):
    """原 helper（未作用域）——用于证明「排除」由 R9 scope guard（而非空账本）造成。"""
    return senate_api._consul_direct_decision_rows(state)


def _register_direct(state, session_id, direct_id, war_id, turn=None):
    decision = {"senate_session_id": session_id, "direct_decision_id": direct_id,
                "war_id": war_id}
    if turn is not None:
        decision["submitted_at"] = {"turn": turn, "senate_session_id": session_id}
    assert state.register_consul_war_decision(decision), "register_consul_war_decision 拒绝"


def _register_package(state, session_id, package_id, submitted_at):
    record = {"package_id": package_id, "senate_session_id": session_id}
    if submitted_at is not None:
        record["submitted_at"] = submitted_at
    assert state.register_senate_package_record(record), "register_senate_package_record 拒绝"


def _roundtrip(state):
    clone = GameState.create_for_testing(_base_config())
    clone.load_from_dict(json.loads(json.dumps(state.to_dict(), ensure_ascii=False)))
    return clone


def _authority_snapshot(state, war):
    """关键权威对象深值快照（T02 零 mutation 对照）。"""
    ms = state.get_military_system()
    session = state.get_senate_session()
    return {
        "war_status": str(war.status),
        "war_commander": war.commander_id,
        "war_legions": sorted(war.legion_numbers or []),
        "war_fleets": sorted(war.assigned_fleet_ids or []),
        "treasury": state.treasury,
        "faction_treasuries": {f.id: f.treasury for f in state.get_active_factions()},
        "war_rewards": copy.deepcopy(getattr(war, "rewards", None)),
        "proposals": copy.deepcopy(state.get_senate_proposals()),
        "decision_complete": state.senate_proposal_decision_complete,
        "session": session,
        "package_registry": copy.deepcopy(state.get_senate_package_registry()),
        "package_for_session": (state.get_senate_package_id_for_session(session)
                                if session else None),
        "direct_ledger": copy.deepcopy(state.get_consul_war_decisions(session)
                                       if session else {}),
        "receipt": copy.deepcopy(state.get_war_execution_receipt_for_session(session)
                                 if session else None),
        "available_legions": sorted(l.number for l in ms.get_available_legions()) if ms else [],
    }


# ===========================================================================
# T01 — 当前会期保留 / 次回合排除（组件 MOCK_AUXILIARY）/ 终结结果两源排除
# ===========================================================================
class TestT01CurrentScopeProjection(unittest.TestCase):
    """顶层 direct 投影 = canonical 当前会期；终结 War 不在当前行动面。"""

    def test_t01_turn_n_results_retained_api_and_store(self):
        ctx = build_f6_base(turn_number=1)
        state = ctx["state"]
        publish = submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)])
        self.assertTrue(publish["success"], publish)
        # 顶层 API：当前会期（package.submitted_at.turn == current turn）保留
        rows = _top_direct_rows(state)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["war_id"], FIXED["war_ongoing"])
        self.assertNotIn("proposal_id", rows[0])
        self.assertEqual(rows[0]["execution"], "awaiting_boundary")
        # Store 只读透传同值
        store = GuiSessionStore(state)
        store.initialize(FIXED["player"])
        self.assertEqual(len(store.senateConsulDirectDecisions), 1)
        self.assertEqual(store.senateConsulDirectDecisions[0]["war_id"], FIXED["war_ongoing"])

    def test_t01_next_turn_scope_excludes_component_mock_auxiliary(self):
        """`MOCK_AUXILIARY`：**仅改 turn_number** 的组件负例（不冒充 T04 真实年度链）。

        证明顶层作用域判据 = 「current turn vs package.submitted_at.turn」；真实跨回合生产链
        见 `src/tests/test_integration/test_wpgr9_terminal_next_senate.py`。
        """
        ctx = build_f6_base(turn_number=1)
        state = ctx["state"]
        submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)])
        self.assertEqual(len(_top_direct_rows(state)), 1)
        state.turn.turn_number = 2                     # ← MOCK_AUXILIARY：仅改 turn
        self.assertEqual(_top_direct_rows(state), [])
        store = GuiSessionStore(state)
        store.initialize(FIXED["player"])
        self.assertEqual(store.senateConsulDirectDecisions, [])

    def test_t01_terminal_war_excluded_from_actionable_surfaces(self):
        """TRIUMPH / VICTORY → RESOLVED：war_cards 无 target（合法正对照在）；同会期 Results
        冻结 direct 行仍只读保留（FC-R9-05）。"""
        for result in ("triumph", "victory"):
            with self.subTest(combat_result=result):
                ctx = build_f6_base(turn_number=1)
                state = ctx["state"]
                war = ctx["war_ongoing"]
                publish = submit_api(state, [command_draft(war.id, ctx["cmd_a"].id, 1)])
                self.assertTrue(publish["success"], publish)
                state.get_war_system().resolve_war(war.id, True, combat_result=result)
                self.assertEqual(war.status, WarStatus.RESOLVED)
                view = _view(state)
                card_wars = {c["war_id"] for c in view["war_cards"]}
                self.assertNotIn(war.id, card_wars, "终结 War 不得在可操作 war_cards")
                self.assertIn(FIXED["war_peace"], card_wars, "合法正对照（TRUCE+pending）仍在")
                # 同会期 Results：direct 冻结行只读保留（有效 current-turn package）
                rows = view["consul_direct_decisions"]
                self.assertEqual([r["war_id"] for r in rows], [war.id])
                self.assertNotIn("proposal_id", rows[0])
                self.assertTrue(rows[0]["item_ref"])


# ===========================================================================
# T02 — RESOLVED war 的 checked draft：fail-closed + 零 mutation（AC-R9-02）
# ===========================================================================
class TestT02ResolvedDraftFailClosed(unittest.TestCase):
    def _resolved_state(self):
        ctx = build_f6_base(turn_number=1)
        war = ctx["war_ongoing"]
        ctx["state"].get_war_system().resolve_war(war.id, True, combat_result="triumph")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        return ctx, war

    def test_t02_stale_resolved_checked_draft_rejected_zero_mutation(self):
        ctx, war = self._resolved_state()
        state = ctx["state"]
        before = _authority_snapshot(state, war)
        result = submit_api(state, [command_draft(war.id, ctx["cmd_a"].id, 1)])
        self.assertFalse(result["success"], "已 RESOLVED war 的 checked draft 必须拒")
        self.assertIn("WAR_TARGET_INVALID", error_codes(result))
        self.assertEqual(_authority_snapshot(state, war), before,
                         "拒后 War/奖励/人物/军团/舰队/包/提案/receipt 深值须一致")
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual(state.get_consul_war_decisions(state.get_senate_session()), {})

    def test_t02_mixed_package_whole_rejected(self):
        ctx, war = self._resolved_state()
        state = ctx["state"]
        before = _authority_snapshot(state, war)
        drafts = [
            command_draft(FIXED["war_threat"], ctx["consul_id"], 1),   # 合法（THREAT 宣战）
            command_draft(war.id, ctx["cmd_a"].id, 1),                # 非法（RESOLVED）
        ]
        result = submit_api(state, drafts)
        self.assertFalse(result["success"], "混合包含非法项 → 整包拒")
        self.assertEqual(_authority_snapshot(state, war), before)
        self.assertEqual((result.get("data") or {}).get("created"), [])
        self.assertEqual(state.get_senate_proposals(), [])


# ===========================================================================
# T03 — canonical 会期支持范围（7 类对照；ADDENDUM 01）
# ===========================================================================
class TestT03CanonicalSupportBoundary(unittest.TestCase):
    def _base(self):
        return build_f6_base(turn_number=1)["state"]

    # —— 案例 1：current canonical valid → 保留 ————————————————————————
    def test_case1_current_canonical_valid_retained(self):
        ctx = build_f6_base(turn_number=1)
        state = ctx["state"]
        res = submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)],
                         session_id="S1")
        self.assertTrue(res["success"], res)
        rows = _top_direct_rows(state)
        self.assertEqual([r["war_id"] for r in rows], [FIXED["war_ongoing"]])

    # —— 案例 2：current custom valid → 保留 ——————————————————————————
    def test_case2_current_custom_valid_retained(self):
        ctx = build_f6_base(turn_number=1)
        state = ctx["state"]
        res = submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)],
                         session_id="senate-custom-3")
        self.assertTrue(res["success"], res)
        self.assertEqual(state.get_senate_session(), "senate-custom-3")
        rows = _top_direct_rows(state)
        self.assertEqual([r["war_id"] for r in rows], [FIXED["war_ongoing"]])

    # —— 案例 3：no-package canonical current → 排除 ——————————————————
    def test_case3_no_package_canonical_current_excluded(self):
        state = self._base()
        # direct 自身带有效 turn；仅缺 PackageRecord ⇒ 一律排除（不 fallback）
        _register_direct(state, "turn-1", "dd-1", FIXED["war_ongoing"], turn=1)
        state.set_senate_session("turn-1")
        self.assertEqual(len(_unscoped_rows(state)), 1, "账本非空（原 helper 可见该行）")
        self.assertEqual(_top_direct_rows(state), [], "scope guard：无包排除")

    # —— 案例 4：no-package canonical stale → 排除 ————————————————————
    def test_case4_no_package_canonical_stale_excluded(self):
        state = self._base()
        _register_direct(state, "turn-0", "dd-1", FIXED["war_ongoing"], turn=0)
        state.set_senate_session("turn-0")
        self.assertEqual(len(_unscoped_rows(state)), 1)
        self.assertEqual(_top_direct_rows(state), [], "scope guard：无包排除")

    # —— 案例 5：package 存在但 turn 缺失/非法/不匹配 → 排除（不 fallback）——
    def test_case5_package_bad_metadata_excluded_no_fallback(self):
        variants = {
            "turn_missing": None,
            "turn_str": {"turn": "1"},
            "turn_bool": {"turn": True},
            "turn_not_current": {"turn": 99},
            "turn_dict": {"turn": {"nested": 1}},
        }
        for name, submitted_at in variants.items():
            with self.subTest(variant=name):
                state = self._base()
                _register_package(state, "turn-1", "pkg-1", submitted_at)
                _register_direct(state, "turn-1", "dd-1", FIXED["war_ongoing"], turn=1)
                state.set_senate_session("turn-1")
                self.assertEqual(len(_unscoped_rows(state)), 1)
                self.assertEqual(_top_direct_rows(state), [], "scope guard：坏包排除（不 fallback）")

    def test_case5_session_mismatch_excluded_no_fallback(self):
        """`MOCK_AUXILIARY`：by_session[s] 指向身份不匹配的坏包（损坏账本，非真实 legacy 回归）。"""
        state = self._base()
        _register_package(state, "other-session", "pkg-1", {"turn": 1})
        # 直接注入不一致映射（MOCK_AUXILIARY）：by_session[s] → senate_session_id != s 的包
        state._senate_package_ledger["by_session"]["turn-1"] = "pkg-1"
        _register_direct(state, "turn-1", "dd-1", FIXED["war_ongoing"], turn=1)
        state.set_senate_session("turn-1")
        self.assertEqual(len(_unscoped_rows(state)), 1)
        self.assertEqual(_top_direct_rows(state), [], "scope guard：身份不匹配排除")

    # —— 案例 6：unknown custom → 排除 ——————————————————————————————
    def test_case6_unknown_custom_excluded(self):
        state = self._base()
        _register_direct(state, "custom-unknown", "dd-1", FIXED["war_ongoing"], turn=1)
        state.set_senate_session("custom-unknown")
        self.assertEqual(len(_unscoped_rows(state)), 1)
        self.assertEqual(_top_direct_rows(state), [], "scope guard：未知 custom 排除")

    # —— 案例 7：SaveLoad 同版重判 ————————————————————————————————
    def test_case7_save_load_reapplies_rule(self):
        # (a) 有效包：重载后仍保留
        ctx = build_f6_base(turn_number=1)
        state = ctx["state"]
        submit_api(state, [command_draft(FIXED["war_ongoing"], ctx["cmd_a"].id, 1)],
                   session_id="S1")
        before = _top_direct_rows(state)
        self.assertEqual(len(before), 1)
        clone = _roundtrip(state)
        after = _top_direct_rows(clone)
        self.assertEqual(after, before, "同版重载后 canonical 判定一致（保留）")
        # (b) 无包：重载后仍排除
        state2 = build_f6_base(turn_number=1)["state"]
        _register_direct(state2, "turn-1", "dd-1", FIXED["war_ongoing"], turn=1)
        state2.set_senate_session("turn-1")
        self.assertEqual(len(_unscoped_rows(state2)), 1)
        clone2 = _roundtrip(state2)
        self.assertEqual(_top_direct_rows(clone2), [], "无包状态重载后仍排除")


if __name__ == "__main__":
    unittest.main()
