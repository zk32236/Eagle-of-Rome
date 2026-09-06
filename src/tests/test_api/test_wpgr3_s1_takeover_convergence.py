# src/tests/test_api/test_wpgr3_s1_takeover_convergence.py
"""WP-G-R3 S1（R3-G-01 + T-R3-01/02/03/03b）— Human Takeover Senate 收敛（SC-R3-01，Evidence Class=DATA）。

冻结设计：SA-Design-WP-G-R3-2026-09-05.md v1.2 §1.2/§1.5（FROZEN）+ §10 T01~T03/T03b。

冻结契约（§1.2/§1.5）：
- human `takeover_war` canonical mutation 成功 + provenance 记录后驱动收敛；
- `can_advance = (current_step=="results") and has_real_senate_result and not takeover_required.required`
  （has_real_senate_result = bool(state.get_phase_result("senate"))——不是 current_step=="results"）；
- `senate_settlement_pending = (current_step == "results") and not has_real_senate_result`；
  `can_resolve_settlement = senate_settlement_pending`；
- 唯一恢复入口 `doResolveSenateSettlement()`（结算-only → resolve_senate，零 takeover mutation 重放）；
- resolve_senate 结算 mutation 前 live required 复检 → 结构化 takeover_required 拒绝（不结算不写 phase_result）；
  已存在成功 phase_result → 幂等 no-op success；失败不落盘冒充成功；
- side-effect 计数：execute_war_takeover_direct 恰 1 次；direct_actions/public_announcement 恰 1 份；
  结算重试 0 次新增 War side effects。

红测（ac1d293 上应先红）：现 takeover_war 仅 refresh（无 decision_complete/无空结算 hook）；
get_senate_view can_advance 仅按 current_step=="results" 投影（可无真实 phase_result 冒充完成）；
resolve/advance 无 required 复检（R1 s3 commanderless 捷径即经此绕过）。
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
    """Senate takeover fixture：eligible human consul + commanderless ACTIVE war（可选）。

    确定性构造（FIX-R3-TA，S1）：mortality~population 已 executed → senate 当前 phase；
    零可用军团池 → Reinforcement N=0 例外（G 件 §4 zero_pool_exception），零征召/零扣款，
    使 side-effect 计数聚焦 War mutation 本身；war naval_required=False 免除舰队绑定面。
    """
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
    """T03b/new-Store 变体：真实 Player 对象（GuiSessionStore snapshot 需真实 player）。"""
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


class TestTr01TakeoverConvergence(unittest.TestCase):
    """T-R3-01：human Takeover → 真实 senate result + 正常 advance；mutation 恰一次、零 vote。"""

    def test_human_takeover_converges_real_result_and_advance(self):
        """C 验收主链：一次 mutation → decision complete → 空结算 → 真实 phase_result → advance。"""
        state, consul, war = _build_state()
        dto = _takeover_view(state)
        self.assertTrue(dto["takeover_required"]["required"])  # 活体门禁可见

        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_direct

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_direct", counting):
            result = senate_api.takeover_war(state, P1, "war_a")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(calls["n"], 1, "canonical takeover mutation 必须恰 1 次")

        data = result["data"]
        self.assertIs(data["takeover_applied"], True)
        self.assertIs(data["senate_converged"], True)      # 无提案/无 required → 空结算已收敛
        self.assertIs(data["senate_settlement_pending"], False)

        # 真实 senate result 落盘 + provenance/direct action 恰 1 份
        self.assertTrue(state.get_phase_result("senate"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)                  # 唯一 Consul 出征（mutation side effect）
        # 结算后 pending 清空（clear_senate_pending）；权威 direct_actions 随 phase_result 持久化
        self.assertEqual(len(state.get_senate_direct_actions()), 0)
        self.assertEqual(len(state.get_phase_result("senate")["data"]["direct_actions"]), 1)
        da = state.get_phase_result("senate")["data"]["direct_actions"][0]
        self.assertEqual(da["action_type"], "takeover")
        self.assertEqual(da["trigger_source"], "human_explicit")

        # 零 takeover vote / 零 takeover proposal（直接职权，不进表决链）
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual(state.get_senate_votes_copy(), {})
        # War side effects 恰一次（§1.5 计数）：恰 1 个新征召军团绑定新 Consul + 国库扣款一次
        self.assertEqual(len(war.legion_numbers), 1)
        legion = state.get_military_system().get_legion_by_number(war.legion_numbers[0])
        self.assertEqual(legion.commander_id, consul.id)
        self.assertEqual(legion.war_id, "war_a")

        dto2 = _takeover_view(state)
        self.assertEqual(dto2["current_step"], "results")
        self.assertIs(dto2["can_advance"], True)           # §1.5 冻结公式（真实 result + 无 required）
        self.assertIs(dto2["senate_settlement_pending"], False)
        self.assertIs(dto2["can_resolve_settlement"], False)
        # public_announcement 恰 1 份 direct action（随 phase_result 持久化）
        ann = dto2["senate_result"]["data"]["public_announcement"]
        self.assertEqual(len(ann["direct_actions"]), 1)

        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_repeat_takeover_request_no_second_side_effects(self):
        """E 验收：重复 human click/request → already_taken_over 拒绝，零新增 side effects。"""
        state, consul, war = _build_state()
        senate_api.takeover_war(state, P1, "war_a")

        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_direct

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_direct", counting):
            repeat = senate_api.takeover_war(state, P1, "war_a")
        self.assertFalse(repeat["success"], repeat.get("message"))
        # 重复请求被拒（唯一 Consul 出征后无 eligible consul / 已有有效指挥官——两种拒绝均合法）
        self.assertEqual(calls["n"], 0, "重复请求不得再次进入 mutation")
        # 权威 direct_actions 随 phase_result 持久化（pending 已清）——重复请求零新增
        self.assertEqual(len(state.get_phase_result("senate")["data"]["direct_actions"]), 1)
        self.assertEqual(war.commander_id, consul.id)
        self.assertEqual(len(war.legion_numbers), 1, "重复请求不得二次征召")

    def test_ai_contrast_shared_required_guard(self):
        """F 对照：AI 路径（auto_submit 空批 completion 保留）经同一 resolve/advance guard——
        required=True 时空批结算/推进均不能跳过；接管后同 resolve 成功。"""
        state, _consul, _war = _build_state()
        # AI auto_submit 尾部语义：空批合法 + decision_complete（D-09）；AI 失败不能以空批跳过 required
        state.senate_proposal_decision_complete = True
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertTrue(refused["data"]["takeover_required"]["required"])
        self.assertFalse(state.get_phase_result("senate"), "拒绝路径不得写 phase_result")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])

        # 合法 canonical takeover 后（AI/human 同 mutation owner）→ resolve 成功
        senate_api.takeover_war(state, P1, "war_a")
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))


class TestTr02RequiredCannotBeSkipped(unittest.TestCase):
    """T-R3-02：required=True 时空批 / 旧 result / direct resolve / advance 均不能跳过。"""

    def test_empty_batch_decision_legal_but_resolve_and_advance_refused(self):
        state, _consul, war = _build_state()
        # 空批 = 合法政治决策（D-09 语义保持）→ success + decision_complete
        empty = senate_api.propose_many(state, P1, [])
        self.assertTrue(empty["success"])
        self.assertTrue(state.senate_proposal_decision_complete)

        dto = _takeover_view(state)
        self.assertEqual(dto["current_step"], "results")       # Path A 投影（无真实 result）
        self.assertFalse(dto["senate_result"])                  # 无真实 phase_result
        self.assertIs(dto["can_advance"], False)                # §1.5：不可冒充阶段完成
        self.assertTrue(dto["takeover_required"]["required"])

        # direct resolve → 结构化 takeover_required 拒绝；不结算不写 phase_result
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertIsNotNone(refused["data"].get("takeover_required"))
        self.assertTrue(refused["data"]["takeover_required"]["required"])
        self.assertFalse(state.get_phase_result("senate"), "拒绝不得写 phase_result")
        self.assertIsNone(war.commander_id, "拒绝不得产生 War mutation")

        # advance → 拒绝（无真实 result + required）
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])
        self.assertFalse(state.is_phase_executed("senate"))

        # 活体门禁不可绕过：接管后 required 清（唯一 Consul absent → 无 eligible）→ resolve 成功
        take = senate_api.takeover_war(state, P1, "war_a")
        self.assertTrue(take["success"])
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"])
        self.assertTrue(state.get_phase_result("senate"))

    def test_old_result_present_still_required_blocks_resolve(self):
        """旧 result/cache 不能开启 advance：required=True 时即便已有（旧）phase_result，
        resolve 拒绝（required 检查优先）、advance 拒绝。"""
        state, _consul, _war = _build_state()
        # 旧会期残留 result（模拟 advance_year 未清干净 / 缓存场景）
        state.record_phase_result("senate", {
            "success": True, "message": "stale", "data": {"direct_actions": [], "public_announcement": {}},
        })
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertTrue(refused["data"]["takeover_required"]["required"])
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertFalse(adv["success"])

        # 接管完成 → 幂等 no-op（已有 result 不再重复结算）
        senate_api.takeover_war(state, P1, "war_a")
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"])

    def test_no_eligible_consul_keeps_required_false_no_deadlock(self):
        """无 eligible Consul（absent）→ required=False 保持（无解软锁规避，R1 s4 语义回归）；
        空批结算可正常完成。"""
        state, consul, _war = _build_state()
        consul.is_absent = True
        dto = _takeover_view(state)
        self.assertFalse(dto["takeover_required"]["required"])
        self.assertEqual(len(dto["takeover_required"]["rows"]), 1)
        self.assertFalse(dto["takeover_required"]["rows"][0]["eligible_consul"])

        state.senate_proposal_decision_complete = True
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))

    def test_truce_pending_p1_takeover_also_converges(self):
        """P1（TRUCE+pending）可选 Takeover 成功同样收敛（不把 Continue/Peace 强制改 Takeover）。"""
        state, consul, _war = _build_state(with_war=False)
        truce = War(id="war_p1", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        truce.status = WarStatus.TRUCE
        truce.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        truce.commander_id = None
        state._war_system._truce_wars.append(truce)
        dto = _takeover_view(state)
        self.assertFalse(dto["takeover_required"]["required"], "P1 不计入 required（可选）")
        self.assertTrue(any(o["war_id"] == "war_p1" for o in dto["takeover_options"]))

        result = senate_api.takeover_war(state, P1, "war_p1")
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["data"]["takeover_applied"])
        self.assertEqual(truce.status, WarStatus.ACTIVE)
        self.assertEqual(truce.commander_id, consul.id)
        self.assertTrue(state.get_phase_result("senate"), "P1 接管后同样收敛出真实 result")


class TestTr03RefreshReentryStable(unittest.TestCase):
    """T-R3-03：repeat/refresh/re-entry 不二次征召/绑定/事件；new Store 仍完成；
    失败 settlement 不误称 mutation 未执行。"""

    def test_refresh_reentry_and_new_store_complete(self):
        state, _consul, _war = _build_state()
        senate_api.takeover_war(state, P1, "war_a")

        # refresh ×2 稳定（从 GameState 重建，非 QML 临时布尔）
        for _ in range(2):
            dto = _takeover_view(state)
            self.assertEqual(dto["current_step"], "results")
            self.assertTrue(dto["can_advance"])
            # 权威 direct_actions 随 phase_result 持久化（pending 已清，恰 1 份）
            self.assertEqual(len(dto["senate_result"]["data"]["direct_actions"]), 1)
            self.assertEqual(len(dto["senate_result"]["data"]["public_announcement"]["direct_actions"]), 1)

        # 重复 resolve → 幂等 no-op success（不重复结算、不二次安排副作用）
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"])
        self.assertEqual(len(state.get_senate_direct_actions()), 0)  # 结算后 pending 已清（权威=phase result）
        self.assertTrue(state.get_phase_result("senate"))

        # new Store：fresh GuiSessionStore 重建同一完成态
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(state)
        store.initialize(P1)
        self.assertEqual(store.senateCurrentStep, "results")
        self.assertTrue(store.canAdvanceSenate)
        self.assertFalse(store.senateSettlementPending)
        self.assertFalse(store.canResolveSenateSettlement)

    def test_failed_settlement_does_not_misreport_mutation_unexecuted(self):
        """T03 边界：settlement 失败态下 takeover_war 仍报 takeover_applied（refresh 读权威
        direct action），不诱导重复 mutation（完整恢复链见 T03b）。"""
        state, _consul, war = _build_state()
        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_direct

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        real_resolve = senate_api.resolve_senate

        def flaky_first(state_, vote_decider=None):
            if flaky_first.calls == 0:
                flaky_first.calls += 1
                return {"success": False, "message": "injected settlement failure",
                        "data": {}, "errors": ["injected"]}
            return real_resolve(state_, vote_decider)

        flaky_first.calls = 0
        with mock.patch.object(senate_api, "resolve_senate", flaky_first), \
             mock.patch.object(PoliticalSystem, "execute_war_takeover_direct", counting):
            result = senate_api.takeover_war(state, P1, "war_a")

        self.assertTrue(result["success"], "mutation 成功不得因结算失败反馈成失败")
        self.assertEqual(calls["n"], 1)
        self.assertTrue(result["data"]["takeover_applied"])
        self.assertFalse(result["data"]["senate_converged"])
        self.assertTrue(result["data"]["senate_settlement_pending"])
        self.assertEqual(war.commander_id, 1)
        self.assertFalse(state.get_phase_result("senate"), "失败 phase_result 不落盘")
        self.assertEqual(len(state.get_senate_direct_actions()), 1)


class TestTr03bSettlementPendingRecovery(unittest.TestCase):
    """T-R3-03b（§1.5 红测）：mutation 成功 → 首次空结算失败 → new Store 可见恢复动作 →
    结算成功 → 正常 advance；War mutation 恰 1 次、side effects 不重复、direct_actions/
    public_announcement 恰 1 份、失败 phase_result 不落盘。"""

    def _flaky_resolve(self, real_resolve):
        def flaky(state_, vote_decider=None):
            if flaky.calls == 0:
                flaky.calls += 1
                return {"success": False, "message": "injected settlement failure",
                        "data": {}, "errors": ["injected"]}
            return real_resolve(state_, vote_decider)
        flaky.calls = 0
        return flaky

    def test_settlement_pending_recovery_chain_store_level(self):
        state, consul, war = _real_player_state()
        mutation_calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_direct

        def counting(self_, war_, consul_, reinforcement_n=None):
            mutation_calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        real_resolve = senate_api.resolve_senate
        flaky = self._flaky_resolve(real_resolve)

        with mock.patch.object(senate_api, "resolve_senate", flaky), \
             mock.patch.object(PoliticalSystem, "execute_war_takeover_direct", counting):
            from src.ui.gui.session_store import GuiSessionStore
            store = GuiSessionStore(state)
            store.initialize(P1)

            # live doTakeoverWar（Store 层真入口）→ mutation 成功 + 首次空结算注入失败
            # （MilitarySystem 默认 25 军团池 → 合法 N=1 显式征召 1 个军团，side-effect 可计数）
            feedback = store.doTakeoverWar("war_a", 1)
            self.assertTrue(feedback["success"], feedback.get("message"))
            self.assertEqual(mutation_calls["n"], 1)

            # settlement-pending 可见恢复态：DTO + Store property
            self.assertEqual(store.senateCurrentStep, "results")
            self.assertTrue(store.senateSettlementPending)
            self.assertTrue(store.canResolveSenateSettlement)
            self.assertFalse(store.canAdvanceSenate)          # 无真实 result 禁 advance
            self.assertFalse(state.get_phase_result("senate"))
            self.assertEqual(war.commander_id, consul.id)     # mutation side effect 已落盘不回滚
            self.assertEqual(len(state.get_senate_direct_actions()), 1)

            # 唯一恢复入口 doResolveSenateSettlement（结算-only）→ 成功落盘
            recovery = store.doResolveSenateSettlement()
            self.assertTrue(recovery["success"], recovery.get("message"))
            self.assertTrue(state.get_phase_result("senate"))
            self.assertFalse(store.senateSettlementPending)
            self.assertFalse(store.canResolveSenateSettlement)
            self.assertTrue(store.canAdvanceSenate)

            # side-effect 计数：mutation 恰 1；结算重试 0 次新增 War mutation
            self.assertEqual(mutation_calls["n"], 1)
            self.assertEqual(len(state.get_senate_direct_actions()), 0)  # 结算清 pending（权威=phase result）

            # direct_actions / public_announcement 恰 1 份（随 phase_result 持久化）
            dto = _takeover_view(state)
            phase_ann = dto["senate_result"]["data"]["public_announcement"]
            self.assertEqual(len(phase_ann["direct_actions"]), 1)
            self.assertEqual(phase_ann["direct_actions"][0]["action_type"], "takeover")
            self.assertEqual(len(dto["senate_result"]["data"]["direct_actions"]), 1)

            # 正常 doAdvanceSenate（Store 真入口）→ combat
            adv = store.doAdvanceSenate()
            self.assertTrue(adv["success"], adv.get("message"))
            self.assertTrue(state.is_phase_executed("senate"))

            # 结算后再调恢复入口 → 前置不满足（非 settlement-pending）→ 结构化拒绝
            repeat_recovery = store.doResolveSenateSettlement()
            self.assertFalse(repeat_recovery["success"])

    def test_settlement_pending_api_level_refresh_rebuild(self):
        """API 层对照：mutation 成功 → 空结算失败 → refresh/new Store 重建同一 pending 态 →
        直接 resolve（等价 doResolveSenateSettlement 的 adapter 路径）→ advance。"""
        state, consul, war = _real_player_state()
        mutation_calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_direct

        def counting(self_, war_, consul_, reinforcement_n=None):
            mutation_calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        flaky = self._flaky_resolve(senate_api.resolve_senate)
        with mock.patch.object(senate_api, "resolve_senate", flaky), \
             mock.patch.object(PoliticalSystem, "execute_war_takeover_direct", counting):
            result = senate_api.takeover_war(state, P1, "war_a")
        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["senate_settlement_pending"])
        self.assertEqual(mutation_calls["n"], 1)

        # refresh（同一 state 再建 Store 亦同——上一测试覆盖；此处 API refresh 断言）
        dto = _takeover_view(state)
        self.assertEqual(dto["current_step"], "results")
        self.assertTrue(dto["senate_settlement_pending"])
        self.assertTrue(dto["can_resolve_settlement"])
        self.assertIs(dto["can_advance"], False)
        self.assertFalse(dto["senate_result"])
        self.assertEqual(war.commander_id, consul.id)

        # 结算重试 → 成功（flaky 已只拦首调）→ advance
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertEqual(mutation_calls["n"], 1, "结算重试不得重放 War mutation")
        adv = senate_api.advance_senate_phase(state, P1)
        self.assertTrue(adv["success"])
        self.assertTrue(state.is_phase_executed("senate"))


if __name__ == "__main__":
    unittest.main()
