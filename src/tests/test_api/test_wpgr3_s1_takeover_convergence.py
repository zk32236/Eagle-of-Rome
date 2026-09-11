# src/tests/test_api/test_wpgr3_s1_takeover_convergence.py
"""WP-G-R3 S1（R3-G-01）— WP-G-R4 S1 supersession（OD-R4-05/06，SA v1.7 §8.3）。

R4 supersede R3 §1（Takeover 自动关闭 selection/自动空结算/立即部署）：本文件旧断言
（Takeover 自己 P=True / R 存在 / advance 可用 / 立即部署 / 内部空结算 / D 随 R 落盘）
已逐条改为 R4 生命周期（Submit 锁 T 零部署 → 显式空选择 P → resolve 真实 R →
显式 advance_senate_phase 原子部署 exactly-once；D_Takeover 部署后恰一次不回溯 R）。
R3 T03b 失败注入点由「Takeover 内部空 resolve」移动到「显式空结束 / advance 部署」。
Authority: WP-G-R4 任务包 v1.1 §0.1/§3.1（OD-R4-05/06 FROZEN）；SA-Design-WP-G-R4 v1.7。
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


def _build_state(commanderless=True, consul_absent=False, with_war=True):
    """Senate takeover fixture（FIX-R3-TA 结构保留；语义 = R4 Senate 入口前置）。"""
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
        war = War(id="war_a", name="Commanderless War", war_type=WarType.FOREIGN,
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


def _lock_then_r(state, war_id, n=1):
    """R4 标准链：reserve+Submit（锁 T 零部署）→ 显式空选择 P → resolve 真实 R。"""
    assert senate_api.takeover_war(state, P1, war_id, n, action="reserve")["success"]
    locked = senate_api.takeover_war(state, P1, war_id, n, action="submit")
    assert locked["success"], locked.get("message")
    assert senate_api.propose_many(state, P1, [])["success"]
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    return locked


class TestTr01TakeoverConvergence(unittest.TestCase):
    """R4 supersession：Submit 锁 T 零部署 → 显式 advance 原子部署恰一次（无自动空结算）。"""

    def test_human_takeover_locks_then_advance_deploys_once(self):
        state, consul, war = _build_state()
        dto = _takeover_view(state)
        self.assertTrue(dto["takeover_required"]["required"])  # M_open 活体门禁可见

        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_deploy

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        # Submit/lock 零部署（部署 owner spy 0 次）
        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            result = senate_api.takeover_war(state, P1, "war_a", 1, action="reserve")
            self.assertTrue(result["success"], result.get("message"))
            locked = senate_api.takeover_war(state, P1, "war_a", 1, action="submit")
            self.assertTrue(locked["success"], locked.get("message"))
        self.assertEqual(calls["n"], 0, "Submit 零部署（R4 supersede R3 §1 立即部署）")
        self.assertTrue(state.get_takeover_pending()["status"] == "LOCKED")
        self.assertFalse(state.senate_proposal_decision_complete, "Takeover 不写 P")
        self.assertFalse(state.get_phase_result("senate"), "无隐式空结算")
        self.assertIsNone(war.commander_id)
        self.assertFalse(consul.is_absent, "R4-17：执政官留城")

        # 显式空结束 → resolve（pending-aware M 放行）→ 真实 R → advance 原子部署恰一次
        self.assertTrue(senate_api.propose_many(state, P1, [])["success"])
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(calls["n"], 1, "部署恰一次（advance 唯一 owner）")
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)   # O5：仅部署边界 absent
        self.assertTrue(state.is_phase_executed("senate"))
        # D_Takeover 恰一次（POST-COMMIT AUDIT；不回溯改写 R）
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)
        self.assertEqual(len(war.legion_numbers), 1, "完整 N 兑现")
        legion = state.get_military_system().get_legion_by_number(war.legion_numbers[0])
        self.assertEqual(legion.commander_id, consul.id)

        dto2 = _takeover_view(state)
        self.assertEqual(dto2["current_step"], "results")
        # executed 后重复 advance → 后端 exactly-once guard 拒绝（DTO can_advance 非阶段门，见 R3 既有）
        again = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(again["success"], "重复 advance no-op")
        self.assertEqual(state.get_takeover_pending()["status"], "CONSUMED")

    def test_repeat_takeover_request_locked_no_second_side_effects(self):
        state, consul, war = _build_state()
        _lock_then_r(state, "war_a", n=1)
        # LOCKED T：重复 reserve/submit → 拒绝（reserve 拒绝已锁定配置），零新增副作用
        repeat = senate_api.takeover_war(state, P1, "war_a", 1, action="submit")
        self.assertFalse(repeat["success"], repeat.get("message"))
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertEqual(len(war.legion_numbers), 1, "重复请求不得二次征召")
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)

    def test_ai_contrast_shared_required_guard(self):
        state, _consul, _war = _build_state()
        state.senate_proposal_decision_complete = True
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertTrue(refused["data"]["takeover_required"]["m_open"])
        self.assertFalse(state.get_phase_result("senate"), "拒绝路径不得写 phase_result")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])

        # 合法锁定后（pending-aware M 放行）→ resolve 成功 → advance 部署
        _lock_then_r(state, "war_a", n=1)
        adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr02RequiredCannotBeSkipped(unittest.TestCase):
    """R4 pending-aware：M_open 时空批 resolve/advance 不能跳过；LOCKED T 放行。"""

    def test_empty_batch_decision_legal_but_resolve_and_advance_refused_when_m_open(self):
        state, _consul, war = _build_state()
        empty = senate_api.propose_many(state, P1, [])
        self.assertTrue(empty["success"])
        self.assertTrue(state.senate_proposal_decision_complete)

        dto = _takeover_view(state)
        self.assertEqual(dto["current_step"], "results")
        self.assertFalse(dto["senate_result"])
        self.assertIs(dto["can_advance"], False)
        self.assertTrue(dto["takeover_required"]["required"])  # == M_open

        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertTrue(refused["data"]["takeover_required"]["required"])
        self.assertFalse(state.get_phase_result("senate"), "拒绝不得写 phase_result")
        self.assertIsNone(war.commander_id, "拒绝不得产生 War mutation")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self.assertFalse(state.is_phase_executed("senate"))

        # LOCKED T（覆盖 C 战）→ M_open False → resolve 放行（无死锁 R4-18）
        _lock_then_r(state, "war_a", n=1)
        self.assertTrue(state.get_phase_result("senate"))

    def test_old_result_present_still_blocks_when_m_open(self):
        state, _consul, _war = _build_state()
        state.record_phase_result("senate", {
            "success": True, "message": "stale", "data": {"direct_actions": [], "public_announcement": {}},
        })
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertTrue(refused["data"]["takeover_required"]["required"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        # LOCKED T → 幂等 no-op（旧 R 存在）
        _lock_then_r(state, "war_a", n=1)
        self.assertTrue(state.get_phase_result("senate"))

    def test_no_eligible_consul_keeps_required_false_no_deadlock(self):
        state, consul, _war = _build_state()
        consul.is_absent = True
        dto = _takeover_view(state)
        self.assertFalse(dto["takeover_required"]["required"])
        state.senate_proposal_decision_complete = True
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))

    def test_truce_pending_p1_takeover_locks_then_advance_deploys(self):
        """P1（TRUCE+pending）可选 Takeover（C 空时）→ Submit 锁 T 零部署 → advance 部署。"""
        state, consul, _war = _build_state(with_war=False)
        truce = War(id="war_p1", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        truce.status = WarStatus.TRUCE
        truce.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        truce.commander_id = None
        state._war_system._truce_wars.append(truce)
        dto = _takeover_view(state)
        self.assertFalse(dto["takeover_required"]["required"], "P1 不计入 required")
        self.assertTrue(any(o["war_id"] == "war_p1" for o in dto["takeover_options"]))

        result = senate_api.takeover_war(state, P1, "war_p1", 1, action="reserve")
        self.assertTrue(result["success"], result.get("message"))
        locked = senate_api.takeover_war(state, P1, "war_p1", 1, action="submit")
        self.assertTrue(locked["success"], locked.get("message"))
        # Submit 零部署（R4-18）：条约/TRUCE/Commander 未变
        self.assertEqual(truce.status, WarStatus.TRUCE)
        self.assertIsNotNone(truce.peace_treaty)
        self.assertIsNone(truce.commander_id)
        # 显式空结束 + resolve + advance → 部署（P1：treaty clear → ACTIVE + commander）
        self.assertTrue(senate_api.propose_many(state, P1, [])["success"])
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(truce.status, WarStatus.ACTIVE)
        self.assertEqual(truce.commander_id, consul.id)
        self.assertIsNone(truce.peace_treaty)
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr03RefreshReentryStable(unittest.TestCase):
    """R4：refresh/重入不二次部署/绑定/事件；重复 resolve 幂等。"""

    def test_refresh_reentry_and_new_store_complete(self):
        state, consul, war = _build_state()
        _lock_then_r(state, "war_a", n=1)
        for _ in range(2):
            dto = _takeover_view(state)
            self.assertTrue(dto["can_advance"])
            self.assertTrue(dto["pending_takeover_locked"])
            self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)

        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(P1)
        self.assertTrue(state.is_phase_executed("senate"))
        # executed 后显式推进 → 后端 exactly-once guard 拒绝（重复 advance no-op）
        again = store.doAdvanceSenate()
        self.assertFalse(again["success"])

    def test_failed_advance_does_not_misreport_deployment(self):
        """部署失败（注入）→ advance False + T 回 LOCKED；重试成功恰一次。"""
        state, consul, war = _real_player_state()
        _lock_then_r(state, "war_a", n=1)
        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_deploy

        def flaky(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("injected deploy failure")
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", flaky):
            adv = senate_api.advance_senate_phase(state, P1)
            self.assertFalse(adv["success"])
            self.assertFalse(state.is_phase_executed("senate"))
            self.assertIsNone(war.commander_id, "部署失败不留部分态")
            self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
            self.assertEqual(state.get_senate_direct_actions(), [], "no D")
            # 重试（同 patch 内：flaky 只拦首调）→ 部署 exactly once
            adv2 = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv2["success"], adv2.get("message"))
        self.assertEqual(calls["n"], 2, "首调失败 + 重试成功各计一次")
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))


class TestTr03bSettlementPendingRecovery(unittest.TestCase):
    """R4 恢复链：显式空结束后的 resolve 失败 → 恢复动作可见且只调 resolve；
    T/V/招募/treasury 恒定；结算重试不重放部署。"""

    def test_settlement_pending_recovery_chain_store_level(self):
        state, consul, war = _real_player_state()
        _lock_then_r(state, "war_a", n=1)
        # 结算后再调恢复入口 → 前置不满足（非 settlement-pending）→ 结构化拒绝
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(P1)
        self.assertFalse(store.senateSettlementPending)
        repeat_recovery = store.doResolveSenateSettlement()
        self.assertFalse(repeat_recovery["success"])
        # 正常 advance 部署
        adv = store.doAdvanceSenate()
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))

    def test_settlement_pending_api_level_refresh_rebuild(self):
        """resolve 注入失败（显式空结束已写 P 后）→ settlement-pending 保持，T 恒定；
        恢复只调 resolve（不重放部署），成功后 advance。"""
        state, consul, war = _real_player_state()
        r = senate_api.takeover_war(state, P1, "war_a", 1, action="reserve")
        self.assertTrue(r["success"])
        self.assertTrue(senate_api.takeover_war(state, P1, "war_a", 1, action="submit")["success"])
        self.assertTrue(senate_api.propose_many(state, P1, [])["success"])

        real_resolve = senate_api.resolve_senate
        mutation_calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_deploy

        def counting(self_, war_, consul_, reinforcement_n=None):
            mutation_calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        flaky = self._flaky_resolve(real_resolve)
        with mock.patch.object(senate_api, "resolve_senate", flaky), \
             mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            result = senate_api.resolve_senate(state)
        self.assertFalse(result["success"])
        self.assertFalse(state.get_phase_result("senate"))
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED", "T 恒定")
        self.assertEqual(mutation_calls["n"], 0, "结算失败不重放部署")
        # refresh 后 DTO 可见 settlement-pending + LOCKED T；恢复 resolve → R → advance 部署恰一次
        dto = _takeover_view(state)
        self.assertEqual(dto["current_step"], "results")
        self.assertTrue(dto["senate_settlement_pending"])
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(mutation_calls["n"], 1, "部署恰一次")
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(state.is_phase_executed("senate"))

    def _flaky_resolve(self, real_resolve):
        def flaky(state_, vote_decider=None):
            if flaky.calls == 0:
                flaky.calls += 1
                return {"success": False, "message": "injected settlement failure",
                        "data": {}, "errors": ["injected"]}
            return real_resolve(state_, vote_decider)
        flaky.calls = 0
        return flaky


if __name__ == "__main__":
    unittest.main()
