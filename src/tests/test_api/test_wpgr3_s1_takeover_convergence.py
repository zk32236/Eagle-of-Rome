# src/tests/test_api/test_wpgr3_s1_takeover_convergence.py
"""WP-G-R3 S1（R3-G-01）→ WP-G-R5 整包/边界改写（Plan §4.2 L2；SA §2.7 A-I14 / §4.10 C-M09）。

R5 supersede：旧 R4 「Submit 锁 T → pending 部署单元 → advance 部署」链路退役——Commander
任命/续战统一经唯一整包入口 `senate_api.propose_many`（Submit 零军事写）→ resolve
（R 只 finalize Decision）→ Senate→Combat 边界 `advance_senate_phase` 原子部署
（receipt exactly-once）。`takeover_required` / `takeover_options` 只读态与 mandatory 门退役，
War 事实统一经 `war_cards` 投影。

保留反例：Submit 零部署；重复提交/重入不重复发布；无 eligible consul 不软锁；部署失败全回滚
且可重试；receipt 重放不重复部署。
"""
import unittest
from unittest import mock
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import senate_api

P1 = "player1"
WAR_A = "war_a"


class _PassVoteDecider:
    def decide_vote(self, issue, faction, state):
        return True


def _build_state(commanderless=True, consul_absent=False, with_war=True):
    """Senate 入口前置 fixture（FIX-R3-TA 结构保留；语义 = R5 Senate 入口前置）。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=500)
    state.add_faction(faction)

    consul = Figure(id=1, name="Consul Aemilius", faction_id="optimates", age=45)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 80
    state.add_member(consul)
    faction.member_ids.append(1)
    if consul_absent:
        consul.is_absent = True

    state._players = {
        P1: MagicMock(player_id=P1, faction_id="optimates", player_type="human"),
    }
    state._current_player_id = P1
    state._turn_order = [P1]

    war = None
    if with_war:
        war = War(id=WAR_A, name="Commanderless War", war_type=WarType.FOREIGN,
                  strength=5, threat_level=3, naval_required=False)
        war.status = WarStatus.ACTIVE  # commanderless
        state._war_system._active_wars.append(war)
    return state, consul, war


def _real_player_state():
    """T03b/new-Store 变体：真实 Player 对象。"""
    state, consul, war = _build_state()
    state._players = {
        P1: Player(P1, "optimates", PlayerType.HUMAN),
    }
    state._turn_order = [P1]
    state.set_current_player(P1)
    return state, consul, war


def _takeover_view(state):
    view = senate_api.get_senate_view(state, P1)
    assert view["success"], view.get("message")
    return view["data"]


def _command_draft(war_id, target, n=1):
    return {"war_id": war_id, "checked": True, "mode": "command",
            "target_commander_id": target, "reinforcement_n": n}


def _submit(state, drafts, request_id=None):
    env = {"war_drafts": drafts}
    if request_id:
        env["submit_request_id"] = request_id
    return senate_api.propose_many(state, P1, env)


def _resolve(state):
    return senate_api.resolve_senate(state, vote_decider=_PassVoteDecider())


def _receipt(state):
    return state.get_war_execution_receipt_for_session(state.get_senate_session())


class TestTr01TakeoverConvergence(unittest.TestCase):
    """R5 supersession：Submit 零部署 → resolve → 边界 advance 原子部署恰一次。"""

    def test_human_takeover_locks_then_advance_deploys_once(self):
        state, consul, war = _build_state()
        dto = _takeover_view(state)
        card = next(c for c in dto["war_cards"] if c["war_id"] == WAR_A)
        self.assertIsNone(card["current_commander_id"])

        sub = _submit(state, [_command_draft(WAR_A, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertIsNone(war.commander_id)
        self.assertFalse(consul.is_absent, "R5：Submit 零部署，执政官留城")
        self.assertFalse(state.get_phase_result("senate"), "Submit 不收敛 R")
        self.assertFalse(state.is_phase_executed("senate"))

        resolved = _resolve(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))

        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)   # O5：仅部署边界 absent
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(len(war.legion_numbers), 1, "完整 N 兑现")
        legion = state.get_military_system().get_legion_by_number(war.legion_numbers[0])
        self.assertEqual(legion.commander_id, consul.id)
        self.assertIsNotNone(_receipt(state))
        self.assertEqual(_receipt(state)["status"], "COMMITTED")

        dto2 = _takeover_view(state)
        self.assertEqual(dto2["current_step"], "results")
        # executed 后重复 advance → receipt 重放（不重复部署）
        again = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(again["success"])
        self.assertIs(again["data"]["replayed"], True)
        self.assertEqual(len(war.legion_numbers), 1)

    def test_repeat_takeover_request_locked_no_second_side_effects(self):
        state, consul, war = _build_state()
        first = _submit(state, [_command_draft(WAR_A, consul.id, 1)], request_id="req-1")
        self.assertTrue(first["success"], first.get("errors"))
        n = len(state.get_senate_proposals())
        # 同 id 同意图 → 重放（无新增）
        replay = _submit(state, [_command_draft(WAR_A, consul.id, 1)], request_id="req-1")
        self.assertTrue(replay["success"])
        self.assertIs(replay["data"].get("replayed"), True)
        self.assertEqual(len(state.get_senate_proposals()), n)
        # 异 id 再提交 → PACKAGE_ALREADY_SUBMITTED（零新增）
        reuse = _submit(state, [_command_draft(WAR_A, consul.id, 1)], request_id="req-2")
        self.assertFalse(reuse["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (reuse.get("errors") or [])])
        self.assertEqual(len(state.get_senate_proposals()), n)

        self.assertTrue(_resolve(state)["success"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertEqual(len(war.legion_numbers), 1, "重复提交不得二次征召")

    def test_mandatory_gate_removed_resolve_and_advance_allowed(self):
        """R5（DA-3 / SA §2.7 A-I14 / §4.10 C-M09；Plan §4.2 L2 归零）：mandatory Takeover
        门拆除——commanderless ACTIVE 不阻止 Senate settle/advance（旧 R4 断言拒绝已 supersede）。
        """
        state, _consul, _war = _build_state()
        state.senate_proposal_decision_complete = True
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr02RequiredCannotBeSkipped(unittest.TestCase):
    """R5：commanderless 不阻止结算/推进；pending-peace fallback 于边界统一执行。"""

    def test_empty_batch_legal_and_resolve_advance_allowed_when_commanderless(self):
        """R5（Plan §4.2 L2 归零）：空批合法；commanderless 不再拒绝 resolve/advance。"""
        state, _consul, war = _build_state()
        empty = senate_api.propose_many(state, P1, [])
        self.assertTrue(empty["success"])
        self.assertTrue(state.senate_proposal_decision_complete)

        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertIsNone(war.commander_id, "P2 不强制任命")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_old_result_present_idempotent_noop_then_advance(self):
        """R5（Plan §4.2 L2 归零）：R 存在 → resolve 幂等 no-op；advance 仍可推进。

        R6（DA-6 B3c-cont2）：finalization 内部化后，幂等重放要求四完成事实**同版**
        （真实 phase_result + finalization_receipt）；孤立 stale R 不构成完成事实。
        故以真实 finalization 完成后 resolve 重放（replayed=True）表达同一命题。
        """
        state, _consul, _war = _build_state()
        sub = _submit(state, [])
        self.assertTrue(sub["success"], sub.get("errors"))
        first = _resolve(state)
        self.assertTrue(first["success"], first.get("message"))
        self.assertEqual(first["data"]["public_announcement"]["enacted_proposals"], [])
        self.assertTrue(state.get_phase_result("senate"))
        # 重入：四事实同版 → 幂等重放（零二次结算 / 原结果返回）
        replay = _resolve(state)
        self.assertTrue(replay["success"], replay.get("message"))
        self.assertTrue(replay["data"]["replayed"], "R6：完成事实同版 → 幂等重放")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_no_eligible_consul_keeps_required_false_no_deadlock(self):
        """R5：无 eligible consul → 卡默认目标 None；不引入无解软锁（resolve 仍放行）。"""
        state, consul, _war = _build_state()
        consul.is_absent = True
        dto = _takeover_view(state)
        self.assertNotIn("takeover_required", dto)
        card = next(c for c in dto["war_cards"] if c["war_id"] == WAR_A)
        self.assertIsNone(card["defaults"]["target_commander_id"])
        state.senate_proposal_decision_complete = True
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))

    def test_truce_pending_p1_takeover_locks_then_advance_deploys(self):
        """R5：pending-peace 卡 unchecked → 边界 fallback：清条约 + TRUCE→ACTIVE + 现任保留。"""
        state, consul, _war = _build_state(with_war=False)
        truce = War(id="war_p1", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        truce.status = WarStatus.TRUCE
        truce.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        truce.commander_id = None
        state._war_system._truce_wars.append(truce)
        dto = _takeover_view(state)
        self.assertNotIn("takeover_required", dto)
        card = next(c for c in dto["war_cards"] if c["war_id"] == "war_p1")
        self.assertEqual(card["classification"], "pending_peace")
        self.assertIn("peace", card["allowed_modes"])

        # unchecked 卡（默认）→ 边界 fallback 续战（treaty clear → ACTIVE）
        sub = senate_api.propose_many(state, P1, {"war_drafts": [
            {"war_id": "war_p1", "checked": False, "mode": "command",
             "target_commander_id": None, "reinforcement_n": 0}]})
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(truce.status, WarStatus.TRUCE)
        self.assertIsNotNone(truce.peace_treaty)
        self.assertIsNone(truce.commander_id)

        self.assertTrue(_resolve(state)["success"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(truce.status, WarStatus.ACTIVE)
        self.assertIsNone(truce.commander_id)  # commanderless 合法续战（不强制任命）
        self.assertIsNone(truce.peace_treaty)
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr03RefreshReentryStable(unittest.TestCase):
    """R5：refresh/重入不二次部署；receipt 重放；失败注入全回滚 + 可重试。"""

    def test_refresh_reentry_and_new_store_complete(self):
        state, consul, war = _build_state()
        sub = _submit(state, [_command_draft(WAR_A, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))
        resolved = _resolve(state)
        self.assertTrue(resolved["success"])

        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(P1)
        adv = store.doAdvanceSenate()
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)
        # 重入（新 Store）→ receipt 重放，不重复部署
        store2 = GuiSessionStore(state)
        store2.initialize(P1)
        again = store2.doAdvanceSenate()
        self.assertTrue(again["success"])
        self.assertEqual(len(war.legion_numbers), 1)

    def test_failed_advance_does_not_misreport_deployment(self):
        """部署失败（注入）→ advance False + 零部分变更；重试成功恰一次。"""
        state, consul, war = _real_player_state()
        sub = _submit(state, [_command_draft(WAR_A, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(_resolve(state)["success"])

        calls = {"n": 0}
        original = PoliticalSystem._strict_recruit_and_bind

        def flaky(self_, war_, commander_, planned_ids):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("injected deploy failure")
            return original(self_, war_, commander_, planned_ids)

        with mock.patch.object(PoliticalSystem, "_strict_recruit_and_bind", flaky):
            adv = senate_api.advance_senate_phase(state, P1)
            self.assertFalse(adv["success"])
            self.assertFalse(state.is_phase_executed("senate"))
            self.assertIsNone(war.commander_id, "部署失败不留部分态")
            self.assertFalse(consul.is_absent)
            self.assertIsNone(_receipt(state), "零部分提交（receipt 回滚）")
            # 重试（同 patch 内：flaky 只拦首调）→ 部署 exactly once
            adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertEqual(calls["n"], 2, "首调失败 + 重试成功各计一次")
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr03bSettlementPendingRecovery(unittest.TestCase):
    """R5：结算失败（R 未生成）保持可重试；恢复只调 resolve（不重放部署）。"""

    def test_settlement_pending_recovery_chain_store_level(self):
        state, consul, war = _real_player_state()
        sub = _submit(state, [_command_draft(WAR_A, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(_resolve(state)["success"])

        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(P1)
        # 已结算 → settlement-pending 不成立；恢复入口结构化拒绝（不重放部署）
        self.assertFalse(store.senateSettlementPending)
        repeat_recovery = store.doResolveSenateSettlement()
        self.assertFalse(repeat_recovery["success"])

        adv = store.doAdvanceSenate()
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(len(war.legion_numbers), 1)

    def test_settlement_pending_api_level_refresh_rebuild(self):
        """resolve 注入失败（无真实 R）→ phase_result 未落盘；恢复只调 resolve（不重放部署），
        成功后 advance 部署恰一次。"""
        state, consul, war = _real_player_state()
        sub = _submit(state, [_command_draft(WAR_A, consul.id, 1)])
        self.assertTrue(sub["success"], sub.get("errors"))

        real_resolve = senate_api.resolve_senate
        mutation_calls = {"n": 0}
        original = PoliticalSystem._strict_recruit_and_bind

        def counting(self_, war_, commander_, planned_ids):
            mutation_calls["n"] += 1
            return original(self_, war_, commander_, planned_ids)

        def flaky(state_, vote_decider=None):
            return {"success": False, "message": "injected settlement failure",
                    "data": {}, "errors": ["injected"]}

        with mock.patch.object(senate_api, "resolve_senate", flaky), \
             mock.patch.object(PoliticalSystem, "_strict_recruit_and_bind", counting):
            result = senate_api.resolve_senate(state)
        self.assertFalse(result["success"])
        self.assertFalse(state.get_phase_result("senate"))
        self.assertIsNone(war.commander_id, "结算失败不重放部署")
        self.assertEqual(mutation_calls["n"], 0)

        resolved = senate_api.resolve_senate(state, vote_decider=_PassVoteDecider())
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        with mock.patch.object(PoliticalSystem, "_strict_recruit_and_bind", counting):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(mutation_calls["n"], 1, "部署恰一次")
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))


if __name__ == "__main__":
    unittest.main()
