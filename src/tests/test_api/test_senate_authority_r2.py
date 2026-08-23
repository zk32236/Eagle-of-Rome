# src/tests/test_api/test_senate_authority_r2.py
"""WP-D-R2 Senate Authority Consolidation — 单一 authority root（AC-R2-01~12）。

覆盖（DA Plan §5 生产链测试）：
- F1~F5 fixture 矩阵（权威确定性）
- 零调用 spy/call-count（AC-R2-04 硬证据）：人类 Tribune → AutoTribuneVetoDecider 实例化=0/调用=0；
  AI Tribune → 实例化=1 + decide_veto 调用=len(passed)（禁概率证明）
- §11 负向矩阵（Proposal 10 / Veto 9 / Cross 4）
- 跨回合 / refresh 确定性（AC-R2-03）+ DTO 契约（R2-NEW-01：mode/actor/authority_reason 逐对）
- R2-A-1 幂等（正常路径 cached no-op / 漂移路径首档 / 双调用幂等）
- store 路由权威化（veto_control_mode；stale can_auto_veto 双层兜底）
"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class _DeciderSpy:
    """AutoTribuneVetoDecider 计数替身：类级计数器（实例化 + decide_veto 调用）。

    零调用铁证（Task Package §13 / Red Line #13）：非「AI 恰选同结果」充证明——
    直接断言 decider 未实例化 / 未调用。
    """

    instances = 0
    calls = 0

    def __init__(self, *args, **kwargs):
        type(self).instances += 1

    def decide_veto(self, *args, **kwargs):
        type(self).calls += 1
        return False


class _SenateAuthorityR2Base(unittest.TestCase):
    """共享配方：optimates(player1) 持 consul，populares(player2) 持 tribune。

    F1 = player1（HUMAN proposal / AI veto）；F2 = player2（AI proposal / HUMAN veto）。
    """

    def setUp(self):
        _DeciderSpy.instances = 0
        _DeciderSpy.calls = 0
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)

        self.senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
        self.senator.class_tier = ClassTier.NOBILE
        self.senator.influence = 100
        self.state.add_member(self.senator)
        self.faction1.member_ids.append(2)

        self.tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(self.tribune)
        self.faction2.member_ids.append(3)

        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]

    # ---------------- helpers ----------------

    def _politics(self):
        from src.core.systems.political_system import PoliticalSystem
        return PoliticalSystem(self.state)

    def _enter_veto_step(self, current_player="player2", count=2):
        """进入 tribune_veto 步：N 个已通过提案（land）+ 决策完成 + 双方已投票。"""
        self.state.senate_proposal_decision_complete = True
        pids = []
        for _ in range(count):
            pid = self.state.add_senate_proposal(
                {"type": "land", "act_type": "distribution", "amount_C": 10, "percent": 0.1}
            )
            pids.append(pid)
            self.state.record_senate_vote("player1", pid, True)
            self.state.record_senate_vote("player2", pid, True)
        self.state._current_player_id = current_player
        return pids

    def _view(self, viewer_id):
        result = senate_api.get_senate_view(self.state, viewer_id)
        self.assertTrue(result["success"], result.get("message"))
        return result["data"]


# ══════════════════════════════════════════════════════════════════════
# AU-R2-1：Resolver 直接单测矩阵（{mode, actor, authority_reason} 逐断言）
# ══════════════════════════════════════════════════════════════════════

class TestR2Resolver(_SenateAuthorityR2Base):
    """resolve_proposal_control / resolve_veto_control 五态矩阵。"""

    # ---- proposal ----
    def test_proposal_human(self):
        c = self._politics().resolve_proposal_control("player1")
        self.assertEqual(c, {"mode": "HUMAN", "actor": 1, "authority_reason": "human_eligible_consul"})

    def test_proposal_ai(self):
        c = self._politics().resolve_proposal_control("player2")
        self.assertEqual(c, {"mode": "AI", "actor": 1, "authority_reason": "ai_eligible_consul"})

    def test_proposal_none_no_eligible_consul(self):
        self.consul.is_dead = True
        c = self._politics().resolve_proposal_control("player1")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "no_eligible_consul"})

    def test_proposal_missing_viewer(self):
        c = self._politics().resolve_proposal_control("missing_player")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "missing_viewer"})

    def test_proposal_missing_faction(self):
        ghost = MagicMock(player_id="player3", faction_id="ghost", player_type="human")
        self.state._players["player3"] = ghost
        c = self._politics().resolve_proposal_control("player3")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "missing_faction"})

    def test_proposal_consul_absent_not_eligible(self):
        self.consul.is_absent = True
        c = self._politics().resolve_proposal_control("player1")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "no_eligible_consul"})

    # ---- veto ----
    def test_veto_human(self):
        c = self._politics().resolve_veto_control("player2")
        self.assertEqual(c, {"mode": "HUMAN", "actor": 3, "authority_reason": "human_eligible_tribune"})

    def test_veto_ai(self):
        c = self._politics().resolve_veto_control("player1")
        self.assertEqual(c, {"mode": "AI", "actor": 3, "authority_reason": "ai_eligible_tribune"})

    def test_veto_none_no_eligible_tribune(self):
        self.tribune.is_dead = True
        c = self._politics().resolve_veto_control("player2")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "no_eligible_tribune"})

    def test_veto_missing_viewer(self):
        c = self._politics().resolve_veto_control("missing_player")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "missing_viewer"})

    def test_veto_missing_faction(self):
        ghost = MagicMock(player_id="player3", faction_id="ghost", player_type="human")
        self.state._players["player3"] = ghost
        c = self._politics().resolve_veto_control("player3")
        self.assertEqual(c, {"mode": "NONE", "actor": None, "authority_reason": "missing_faction"})


# ══════════════════════════════════════════════════════════════════════
# F1/F2/F4 + §11 Proposal 负向矩阵
# ══════════════════════════════════════════════════════════════════════

class TestR2ProposalAuthority(_SenateAuthorityR2Base):
    """R2-A Proposal Authority（AC-R2-01/02/08 + §11 Proposal 矩阵）。"""

    def test_f1_human_consul_proposal_control(self):
        """F1（AC-R2-01）：player1 有 consul → HUMAN 提案控制四字段齐备。"""
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "HUMAN")
        self.assertEqual(data["proposal_actor"], 1)
        self.assertIs(data["actionable"], True)
        self.assertIs(data["viewer_has_consul"], True)
        self.assertIs(data["can_create_proposal"], True)
        self.assertIs(data["can_select_proposal"], True)
        self.assertIs(data["can_trigger_ai_proposer"], False)

    def test_f2_ai_consul_proposal_locked(self):
        """F2（AC-R2-02）：player2 无 consul（consul 属 optimates）→ 手动权锁定 + AI 路由。"""
        self.state._current_player_id = "player2"
        data = self._view("player2")
        self.assertEqual(data["proposal_control_mode"], "AI")
        self.assertEqual(data["proposal_actor"], 1)
        self.assertIs(data["viewer_has_consul"], False)
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], True)

    def test_consul_dead_fail_closed(self):
        """§11：Consul 死 → NONE → 双 False（D-3：NONE 不再暴露 AI 入口）。"""
        self.consul.is_dead = True
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "NONE")
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], False)

    def test_consul_absent_fail_closed(self):
        """§11：Consul 缺席 → NONE（D-3 收严：can_trigger_ai 仅 mode==AI）。"""
        self.consul.is_absent = True
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "NONE")
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], False)

    def test_consul_absent_but_ai_consul_elsewhere_triggers_ai(self):
        """§11：本派系 consul 缺席但全局另有 eligible consul → AI 路由（actor=AI consul）。"""
        ai_consul = Figure(id=5, name="AI执政官", faction_id="populares", age=40)
        ai_consul.office = "consul"
        ai_consul.class_tier = ClassTier.NOBILE
        ai_consul.influence = 50
        self.state.add_member(ai_consul)
        self.faction2.member_ids.append(5)
        self.consul.is_absent = True
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "AI")
        self.assertEqual(data["proposal_actor"], 5)
        self.assertIs(data["can_trigger_ai_proposer"], True)

    def test_office_changes_next_turn(self):
        """§11：下回合换人（consul 迁至 populares）→ mode 随权威 state 翻转（AC-R2-03）。"""
        self.consul.office = "ex-consul"
        new_consul = Figure(id=6, name="新执政官", faction_id="populares", age=40)
        new_consul.office = "consul"
        new_consul.class_tier = ClassTier.NOBILE
        new_consul.influence = 60
        self.state.add_member(new_consul)
        self.faction2.member_ids.append(6)
        data1 = self._view("player1")
        self.assertEqual(data1["proposal_control_mode"], "AI")
        self.assertEqual(data1["proposal_actor"], 6)
        data2 = self._view("player2")
        self.assertEqual(data2["proposal_control_mode"], "HUMAN")
        self.assertEqual(data2["proposal_actor"], 6)

    def test_viewer_missing_fail_closed(self):
        """§11：viewer 缺失 → get_senate_view 拒绝（resolver NONE missing_viewer）。"""
        result = senate_api.get_senate_view(self.state, "missing_player")
        self.assertFalse(result["success"])
        c = self._politics().resolve_proposal_control("missing_player")
        self.assertEqual(c["mode"], "NONE")

    def test_faction_missing_fail_closed(self):
        """§11：faction 缺失 → NONE(missing_faction) → 能力位 False。"""
        ghost = MagicMock(player_id="player3", faction_id="ghost", player_type="human")
        self.state._players["player3"] = ghost
        self.state._current_player_id = "player3"
        data = self._view("player3")
        self.assertEqual(data["proposal_control_mode"], "NONE")
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], False)

    def test_non_consul_api_mutation_rejected(self):
        """AC-R2-02：非执政官派系直调 propose/propose_many → fail-closed。"""
        self.state._current_player_id = "player2"
        self.state.turn.leader_ids = [1]
        result = senate_api.propose(self.state, "player2", "land", act_type="sale", amount_C=50)
        self.assertFalse(result["success"])
        self.assertIn("只有执政官", result["message"])


# ══════════════════════════════════════════════════════════════════════
# F1/F2/F4 + §11 Veto 负向矩阵 + AC-R2-05 端到端
# ══════════════════════════════════════════════════════════════════════

class TestR2VetoAuthority(_SenateAuthorityR2Base):
    """R2-B Tribune Veto Authority（AC-R2-05/06/08 + §11 Veto 矩阵）。"""

    def test_f2_human_tribune_veto_control(self):
        """F2：player2 持 eligible Tribune → HUMAN veto（can_veto True / can_auto_veto False）。"""
        pids = self._enter_veto_step(current_player="player2")
        data = self._view("player2")
        self.assertEqual(data["current_step"], "tribune_veto")
        self.assertEqual(data["veto_control_mode"], "HUMAN")
        self.assertEqual(data["veto_actor"], 3)
        self.assertIs(data["viewer_has_tribune"], True)
        self.assertIs(data["can_veto"], True)
        self.assertIs(data["can_auto_veto"], False)

    def test_f1_ai_tribune_veto_route(self):
        """F1：player1 无 Tribune（Tribune 属 populares）→ AI veto 路由。"""
        self._enter_veto_step(current_player="player1")
        data = self._view("player1")
        self.assertEqual(data["veto_control_mode"], "AI")
        self.assertEqual(data["veto_actor"], 3)
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], True)

    def test_tribune_dead_none_fail_closed(self):
        """§11：Tribune 死 → NONE → 双 False（D-3）。"""
        self.tribune.is_dead = True
        self._enter_veto_step(current_player="player2")
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "NONE")
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], False)

    def test_no_tribune_none_fail_closed(self):
        """§11：无 Tribune（office 清空）→ NONE → 双 False。"""
        self.tribune.office = None
        self._enter_veto_step(current_player="player2")
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "NONE")
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], False)

    def test_human_veto_survives_to_resolution(self):
        """AC-R2-05（多通过提案）：人类否决 1 / 放行 1 → 结算读否决决定。"""
        pids = self._enter_veto_step(current_player="player2", count=2)
        result = senate_api.veto(self.state, "player2", [pids[0]])
        self.assertTrue(result["success"])
        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        data = resolved["data"]
        self.assertIn(pids[0], data["vetoed_proposals"])
        self.assertNotIn(pids[1], data["vetoed_proposals"])
        self.assertIn(pids[1], data["passed_proposals"])
        self.assertNotIn(pids[0], data["passed_proposals"])

    def test_veto_one_allow_all_matrix(self):
        """§11：否决一 / 全部同意两态（record_veto 幂等 + 零通过跳过）。"""
        # 全部同意 → 无 veto 记录
        pids = self._enter_veto_step(current_player="player2", count=2)
        resolved = senate_api.resolve_senate(self.state)
        self.assertEqual(resolved["data"]["vetoed_proposals"], [])
        self.assertEqual(len(resolved["data"]["passed_proposals"]), 2)
        # 否决一（fresh 会期）
        self.state.clear_senate_pending()
        self.state.senate_proposal_decision_complete = True
        self.state.add_senate_proposal(
            {"type": "land", "act_type": "distribution", "amount_C": 10, "percent": 0.1}
        )
        self.state.record_senate_vote("player1", pids[0], True)
        self.state.record_senate_vote("player2", pids[0], True)
        self.state._current_player_id = "player2"
        result = senate_api.veto(self.state, "player2", [pids[0]])
        self.assertTrue(result["success"])
        self.assertIn(pids[0], self.state.get_senate_vetoes_copy())

    def test_zero_passed_proposals_ai_skips(self):
        """§11：零通过提案 → AI 否决跳过（不崩、不伪造否决）。"""
        self._enter_veto_step(current_player="player2", count=0)
        result = senate_api.apply_auto_tribune_vetoes(self.state, None, "player1")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["vetoed"], [])

    def test_refresh_before_resolution_consistent(self):
        """§11：结算前刷新 → can_veto/can_auto_veto 与 resolver 一致（AC-R2-03）。"""
        pids = self._enter_veto_step(current_player="player2")
        v1 = self._view("player2")
        v2 = self._view("player2")
        v3 = self._view("player2")
        for v in (v1, v2, v3):
            self.assertEqual(v["veto_control_mode"], "HUMAN")
            self.assertIs(v["can_veto"], True)
            self.assertIs(v["can_auto_veto"], False)
        # 权威 state 变化（tribune 死亡）→ 刷新后翻转
        self.tribune.is_dead = True
        v4 = self._view("player2")
        self.assertEqual(v4["veto_control_mode"], "NONE")
        self.assertIs(v4["can_veto"], False)
        self.assertIs(v4["can_auto_veto"], False)


# ══════════════════════════════════════════════════════════════════════
# 零调用 spy / call-count（AC-R2-04 硬证据）
# ══════════════════════════════════════════════════════════════════════

class TestR2ZeroInvocation(_SenateAuthorityR2Base):
    """AutoTribuneVetoDecider 人类场景零实例化零调用（guard 前置 :437）。"""

    def test_f2_human_tribune_decider_zero_invocation(self):
        """F2（人类 Tribune，多 passed）：decider 实例化=0 + 调用=0 + False + WARNING 日志。"""
        pids = self._enter_veto_step(current_player="player2", count=3)
        with patch("src.api.senate_api.AutoTribuneVetoDecider", _DeciderSpy):
            result = senate_api.apply_auto_tribune_vetoes(self.state, None, "player2")
        self.assertFalse(result["success"])
        self.assertIn("人类保民官拥有否决权", result["message"])
        self.assertEqual(result["data"], {"vetoed": [], "decisions": []})
        self.assertEqual(_DeciderSpy.instances, 0)
        self.assertEqual(_DeciderSpy.calls, 0)
        self.assertTrue(
            any("AI 保民官否决被拒" in m for m in self.state._event_log),
            "guard WARNING 日志缺失（tribune_veto_human_guard）",
        )
        # 人类否决端到端仍有效（AC-R2-05）
        veto_result = senate_api.veto(self.state, "player2", [pids[0]])
        self.assertTrue(veto_result["success"])

    def test_f3_human_both_decider_zero_invocation(self):
        """F3（人类都有）：双 HUMAN → decider 实例化=0 + 调用=0。"""
        self._enter_veto_step(current_player="player1", count=2)
        # F3：player1 也持 tribune
        tribune2 = Figure(id=7, name="第二保民官", faction_id="optimates", age=35)
        tribune2.office = "tribune"
        tribune2.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(tribune2)
        self.faction1.member_ids.append(7)
        with patch("src.api.senate_api.AutoTribuneVetoDecider", _DeciderSpy):
            result = senate_api.apply_auto_tribune_vetoes(self.state, None, "player1")
        self.assertFalse(result["success"])
        self.assertEqual(_DeciderSpy.instances, 0)
        self.assertEqual(_DeciderSpy.calls, 0)
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "HUMAN")
        self.assertEqual(data["veto_control_mode"], "HUMAN")

    def test_f1_ai_tribune_decider_invoked_per_passed(self):
        """F1（AI Tribune）：实例化=1 + decide_veto 调用=len(passed)。"""
        pids = self._enter_veto_step(current_player="player1", count=2)
        with patch("src.api.senate_api.AutoTribuneVetoDecider", _DeciderSpy):
            result = senate_api.apply_auto_tribune_vetoes(self.state, None, "player1")
        self.assertTrue(result["success"])
        self.assertEqual(_DeciderSpy.instances, 1)
        self.assertEqual(_DeciderSpy.calls, len(pids))
        self.assertEqual(len(result["data"]["decisions"]), len(pids))

    def test_f4_ai_tribune_decider_invoked(self):
        """F4（人类都无 → AI Tribune）：decider 正常实例化调用（AI 路径可用，AC-R2-06）。"""
        self.consul.is_dead = True
        self.tribune.office = None
        ai_tribune = Figure(id=8, name="AI保民官", faction_id="populares", age=35)
        ai_tribune.office = "tribune"
        ai_tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(ai_tribune)
        self.faction2.member_ids.append(8)
        self._enter_veto_step(current_player="player1", count=1)
        with patch("src.api.senate_api.AutoTribuneVetoDecider", _DeciderSpy):
            result = senate_api.apply_auto_tribune_vetoes(self.state, None, "player1")
        self.assertTrue(result["success"])
        self.assertEqual(_DeciderSpy.instances, 1)
        self.assertEqual(_DeciderSpy.calls, 1)

    def test_cli_no_viewer_auto_mode_unchanged(self):
        """CLI 兼容（FACT-8）：viewer_player_id=None → guard 不触发，auto 行为不变。"""
        pids = self._enter_veto_step(current_player="player1", count=2)
        # player1 无 tribune → AI 路径照旧（即便人类 player2 持 tribune，CLI 无 viewer 概念）
        with patch("src.api.senate_api.AutoTribuneVetoDecider", _DeciderSpy):
            result = senate_api.apply_auto_tribune_vetoes(self.state)
        self.assertTrue(result["success"])
        self.assertEqual(_DeciderSpy.instances, 1)
        self.assertEqual(_DeciderSpy.calls, len(pids))


# ══════════════════════════════════════════════════════════════════════
# DTO 契约（R2-NEW-01 逐对 + C5 can_select guard + provenance）
# ══════════════════════════════════════════════════════════════════════

class TestR2DTOContract(_SenateAuthorityR2Base):
    """AC-R2-07：DTO == API 权限；provenance 5 字段形状（D-2）。"""

    def test_provenance_fields_shape(self):
        """provenance 5 字段：mode/actor/authority_reason（JSON dict 形状）。"""
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "HUMAN")
        self.assertEqual(data["veto_control_mode"], "AI")
        self.assertEqual(data["proposal_actor"], 1)
        self.assertEqual(data["veto_actor"], 3)
        reason = data["authority_reason"]
        self.assertIsInstance(reason, dict)
        self.assertEqual(reason["proposal"], "human_eligible_consul")
        self.assertEqual(reason["veto"], "ai_eligible_tribune")
        # JSON 可序列化（api_response/data 透传安全）
        import json
        json.dumps(reason)

    def test_can_select_guard_matches_can_create(self):
        """C5：非 proposal 步 → can_select False（三重 guard 对齐 can_create）。"""
        # senate_vote 步：decision_complete + 有提案 + viewer(player1) 未全投
        self.state.senate_proposal_decision_complete = True
        pid = self.state.add_senate_proposal(
            {"type": "land", "act_type": "distribution", "amount_C": 10, "percent": 0.1}
        )
        self.state.record_senate_vote("player2", pid, True)  # player1（viewer）未投
        self.state._current_player_id = "player1"
        data = self._view("player1")
        self.assertEqual(data["current_step"], "senate_vote")
        self.assertIs(data["viewer_has_consul"], True)
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_select_proposal"], False)  # step != proposal → guard 生效

    def test_dto_matches_api_mutation_boundary(self):
        """AC-R2-07：can_create/can_select == mutation guard 边界（交叉断言）。"""
        self.state._current_player_id = "player2"
        data = self._view("player2")
        self.assertIs(data["can_select_proposal"], False)
        result = senate_api.propose_many(
            self.state, "player2",
            [{"type": "land", "params": {"act_type": "sale", "amount_C": 50}}],
        )
        self.assertFalse(result["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)

    def test_refresh_determinism_same_state(self):
        """AC-R2-03：同 state 多次 DTO 刷新 → capability 不变（无随机/无 stale 复活）。"""
        self._enter_veto_step(current_player="player2")
        snapshots = [self._view("player2") for _ in range(3)]
        for key in ("proposal_control_mode", "veto_control_mode", "proposal_actor", "veto_actor",
                    "can_create_proposal", "can_select_proposal", "can_trigger_ai_proposer",
                    "can_veto", "can_auto_veto"):
            values = {s[key] for s in snapshots}
            self.assertEqual(len(values), 1, f"field {key} 刷新后漂移: {values}")


# ══════════════════════════════════════════════════════════════════════
# F4/F5 权威切换 + Cross 矩阵
# ══════════════════════════════════════════════════════════════════════

class TestR2CrossAuthority(_SenateAuthorityR2Base):
    """Cross 4 态 + F5 跨回合权威切换（AC-R2-03）。"""

    def test_cross_human_consul_only(self):
        """Cross：有 Consul 无 Tribune → HUMAN/AI（F1）。"""
        data = self._view("player1")
        self.assertEqual((data["proposal_control_mode"], data["veto_control_mode"]), ("HUMAN", "AI"))

    def test_cross_human_tribune_only(self):
        """Cross：有 Tribune 无 Consul → AI/HUMAN（F2）。"""
        data = self._view("player2")
        self.assertEqual((data["proposal_control_mode"], data["veto_control_mode"]), ("AI", "HUMAN"))

    def test_cross_human_both(self):
        """Cross：都有 → HUMAN/HUMAN（F3）。"""
        tribune2 = Figure(id=7, name="第二保民官", faction_id="optimates", age=35)
        tribune2.office = "tribune"
        tribune2.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(tribune2)
        self.faction1.member_ids.append(7)
        data = self._view("player1")
        self.assertEqual((data["proposal_control_mode"], data["veto_control_mode"]), ("HUMAN", "HUMAN"))

    def test_cross_human_neither_none(self):
        """Cross：都无 → NONE/NONE（fail-closed，AC-R2-08）。"""
        self.consul.is_dead = True
        self.tribune.is_dead = True
        data = self._view("player1")
        self.assertEqual((data["proposal_control_mode"], data["veto_control_mode"]), ("NONE", "NONE"))
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], False)
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], False)

    def test_f5_authority_switches_between_turns(self):
        """F5：T1 人类 Consul → T2 AI Consul → T3 人类 Tribune（mode 随权威 state 翻转）。"""
        # T1：player1 持 consul
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "HUMAN")
        # T2：consul 迁至 populares（player2 派系）
        self.consul.office = "ex-consul"
        new_consul = Figure(id=6, name="新执政官", faction_id="populares", age=40)
        new_consul.office = "consul"
        new_consul.class_tier = ClassTier.NOBILE
        new_consul.influence = 60
        self.state.add_member(new_consul)
        self.faction2.member_ids.append(6)
        data = self._view("player1")
        self.assertEqual(data["proposal_control_mode"], "AI")
        self.assertEqual(data["proposal_actor"], 6)
        data = self._view("player2")
        self.assertEqual(data["proposal_control_mode"], "HUMAN")
        # T3：tribune 归属不变 → veto HUMAN 恒为 player2 / AI 恒为 player1
        self._enter_veto_step(current_player="player2")
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "HUMAN")
        data = self._view("player1")
        self.assertEqual(data["veto_control_mode"], "AI")


# ══════════════════════════════════════════════════════════════════════
# R2-A-1：resolve_population_slice 尾部幂等 begin_population_phase（C1）
# ══════════════════════════════════════════════════════════════════════

def _make_empty_population_state():
    """无候选人人口阶段状态（office 键齐备但均空 → HUMAN 平凡完成）。"""
    from src.core.entities.entities import Faction
    from src.core.entities.player import Player, PlayerType
    config = {
        "testing": {"bypass_player_check": True},
        "political_rules": {
            "min_ages": {"consul": 40},
            "office_rank": {"consul": 5},
            "office_influence_bonus": {"consul": 40},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    state.treasury = 200
    faction = Faction(id="Optimates", name="贵族派")
    state._factions["Optimates"] = faction
    player = Player(player_id="player_1", faction_id="Optimates", player_type=PlayerType.HUMAN)
    state._players["player_1"] = player
    state._current_player_id = "player_1"
    state._turn_order = ["player_1"]
    state._provinces = {}
    return state


def _seed_current_consul(state):
    """置一个现任执政官（模拟上回合当选者），返回该人物。"""
    fig = Figure(id=9001, name="现任执政官", faction_id="Optimates", age=45)
    fig.office = "consul"
    fig.class_tier = ClassTier.NOBILE
    fig.influence = 60
    state.add_member(fig)
    state._factions["Optimates"].member_ids.append(fig.id)
    if fig.id not in state.turn.leader_ids:
        state.turn.leader_ids.append(fig.id)
    return fig


class TestR2A1PopulationArchiveIdempotent(unittest.TestCase):
    """C1（R2-A-1）：结算尾段幂等 begin_population_phase（archive→convert→resolve 全序）。"""

    def test_normal_path_tail_noop_no_double_archive(self):
        """正常路径：顶部门控已 archive → 尾部 cached no-op，无二次归档。"""
        from src.api import session_api
        state = _make_empty_population_state()
        fig = _seed_current_consul(state)
        hist_before = len(fig.office_history)

        resolve1 = session_api.resolve_population_slice(state)
        self.assertTrue(resolve1["success"], resolve1.get("message"))
        # 顶部门控归档恰好一次（history +1，非 +2）
        self.assertEqual(fig.office, "ex-consul")
        self.assertEqual(len(fig.office_history), hist_before + 1)
        # 尾部 conversion DTO 形状保持 {converted, total}
        conv = resolve1["data"]["battlefield_commander_conversion"]
        self.assertIsInstance(conv, dict)
        self.assertIn("converted", conv)
        self.assertIn("total", conv)

        # 双调用幂等：第二次 early return，无二次归档
        resolve2 = session_api.resolve_population_slice(state)
        self.assertTrue(resolve2["success"])
        self.assertIn("already resolved", resolve2["message"])
        self.assertEqual(fig.office, "ex-consul")
        self.assertEqual(len(fig.office_history), hist_before + 1)

    def test_drift_path_tail_archives_before_resolve(self):
        """漂移路径：阶段推断跳过顶部门控 → 尾部 begin_population_phase 首档（R2-04 根因闭合）。"""
        from src.api import session_api
        state = _make_empty_population_state()
        fig = _seed_current_consul(state)
        hist_before = len(fig.office_history)
        # 构造漂移：population 已标记 executed（推断跳过门控）但无 phase result
        state.mark_phase_executed("population")
        self.assertNotEqual(session_api._infer_current_phase_id(state), "population")

        resolve1 = session_api.resolve_population_slice(state)
        self.assertTrue(resolve1["success"], resolve1.get("message"))
        # 尾部首档：现任 consul → ex-consul（archive→convert→resolve 全序无条件先于结算）
        self.assertEqual(fig.office, "ex-consul")
        self.assertEqual(len(fig.office_history), hist_before + 1)
        self.assertIn("converted", resolve1["data"]["battlefield_commander_conversion"])

        # 双调用幂等
        resolve2 = session_api.resolve_population_slice(state)
        self.assertTrue(resolve2["success"])
        self.assertEqual(fig.office, "ex-consul")
        self.assertEqual(len(fig.office_history), hist_before + 1)


# ══════════════════════════════════════════════════════════════════════
# AU-R2-3b：store 路由权威化（R2-B-2，C3）——veto_control_mode 不信任 cached can_auto_veto
# ══════════════════════════════════════════════════════════════════════

class TestR2StoreRouting(_SenateAuthorityR2Base):
    """doSubmitSenateVetoes 路由矩阵（HUMAN→submit / AI→apply_auto(viewer_id) / NONE→resolve 直结）。"""

    def _make_store(self, viewer_id):
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(self.state)
        store.initialize(viewer_id)
        return store

    def test_stale_can_auto_veto_true_but_mode_human_goes_human_branch(self):
        """stale 缓存：cached can_auto_veto=True 但 veto_control_mode=HUMAN → 走 human 分支（双层兜底）。"""
        from src.ui.gui.session_store import GuiSessionStore
        pids = self._enter_veto_step(current_player="player2")
        store = self._make_store("player2")
        # 人为构造 stale 缓存
        stale_view = dict(store._senate_view)
        stale_view["can_auto_veto"] = True  # stale（旧字段）
        stale_view["veto_control_mode"] = "HUMAN"  # resolver-backed 权威
        store._senate_view = stale_view

        with patch.object(store._adapter, "submit_senate_vetoes",
                          wraps=store._adapter.submit_senate_vetoes) as spy_submit, \
             patch.object(store._adapter, "resolve_senate",
                          return_value={"success": True, "message": "resolved"}) as spy_resolve:
            feedback = store.doSubmitSenateVetoes([pids[0]])
        self.assertTrue(feedback["success"])
        spy_submit.assert_called_once()
        self.assertEqual(spy_submit.call_args[0][0], "player2")
        self.assertEqual(spy_submit.call_args[0][1], [pids[0]])
        spy_resolve.assert_called_once()
        # 人类否决已记录（权威 mutation 边界生效）
        self.assertIn(pids[0], self.state.get_senate_vetoes_copy())

    def test_mode_ai_routes_apply_auto_with_viewer_id(self):
        """mode=AI → apply_auto 分支，经 adapter.call 直传 viewer_id（R2-B-1 guard 兜底）。"""
        pids = self._enter_veto_step(current_player="player1")
        store = self._make_store("player1")
        ai_view = dict(store._senate_view)
        ai_view["veto_control_mode"] = "AI"
        store._senate_view = ai_view

        with patch.object(store._adapter, "call",
                          wraps=store._adapter.call) as spy_call, \
             patch.object(store._adapter, "resolve_senate",
                          return_value={"success": True, "message": "resolved"}) as spy_resolve:
            feedback = store.doSubmitSenateVetoes([pids[0]])
        self.assertTrue(feedback["success"])
        # apply_auto_tribune_vetoes(state, None, viewer_id) 直传
        applied = [c for c in spy_call.call_args_list if c[0][0].__name__ == "apply_auto_tribune_vetoes"]
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0][0][1:], (self.state, None, "player1"))
        spy_resolve.assert_called_once()

    def test_mode_none_resolves_directly(self):
        """mode=NONE → 无 tribune 跳过否决，resolve 直接结算（无分支调用）。"""
        self.tribune.is_dead = True
        self._enter_veto_step(current_player="player2")
        store = self._make_store("player2")
        none_view = dict(store._senate_view)
        none_view["veto_control_mode"] = "NONE"
        store._senate_view = none_view

        with patch.object(store._adapter, "submit_senate_vetoes") as spy_submit, \
             patch.object(store._adapter, "resolve_senate",
                          return_value={"success": True, "message": "resolved"}) as spy_resolve:
            feedback = store.doSubmitSenateVetoes([self.state.get_senate_proposals()[0]["id"]])
        self.assertTrue(feedback["success"])
        spy_submit.assert_not_called()
        spy_resolve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
