# src/tests/test_api/test_wpfr2_senate.py
"""WP-F-R2 T-R2-01~11：Senate 中间 vote_results 投影 + passed-only 否决候选 + fail-closed + zero-passed 收敛。

DATA 断言（权威 producer 复用，禁重算/重掷）：
- T-R2-01  投票完成 → 中间 vote_results 行可用（每 submitted proposal 一行，resolve 前）
- T-R2-02  passed 提案 → 支持率稳定（support_influence/total_influence 正确）
- T-R2-03  failed 提案 → 支持率稳定
- T-R2-04  混合 PASS/FAIL → veto_candidate_ids == PASS only
- T-R2-05  failed 提案 absent from veto_candidate_ids DTO
- T-R2-06  直连 veto() failed 提案 → 拒绝、vetoes 零变更、rejected_ids 返回（fail-closed）
- T-R2-07  zero passed → current_step="results"、无否决候选、流程收敛（can_advance）
- T-R2-08  passed 提案仍可被 eligible Tribune 否决（权威不变）
- T-R2-09  refresh/re-entry → 支持率不变（幂等）
- T-R2-10  视图刷新不触发 AI 投票重掷（vote_source 注册表无新增 created 决策于已冻结票）
- T-R2-11  投票阈值/权重不变（>0.5 边界 + 无第二算法静态审计）
"""
import unittest
from unittest.mock import patch

from src.api import senate_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.war_system import WarSystem

VOTE_RESULT_KEYS = {
    "proposal_id", "support_influence", "oppose_influence",
    "total_influence", "passed", "vetoed",
}


def _build_state(with_ai_faction=False):
    """optimates(player1, 影响力 150) / populares(player2, 影响力 80)；可选 AI 派系 equites(60)。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    f1 = Faction(id="optimates", name="Optimates", treasury=50)
    f2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(f1)
    state.add_faction(f2)

    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    f1.member_ids.append(1)
    senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 100
    state.add_member(senator)
    f1.member_ids.append(2)
    tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(3)
    ps = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
    ps.class_tier = ClassTier.NOBILE
    ps.influence = 80
    state.add_member(ps)
    f2.member_ids.append(4)

    players = {
        "player1": Player("player1", "optimates", PlayerType.HUMAN),
        "player2": Player("player2", "populares", PlayerType.HUMAN),
    }
    if with_ai_faction:
        f3 = Faction(id="equites", name="Equites", treasury=20)
        state.add_faction(f3)
        ai = Figure(id=5, name="骑士元老", faction_id="equites", age=48)
        ai.class_tier = ClassTier.NOBILE
        ai.influence = 60
        state.add_member(ai)
        f3.member_ids.append(5)
        players["player3"] = Player("player3", "equites", PlayerType.AI)
    state._players = players
    state._current_player_id = "player1"
    state._turn_order = list(players)
    return state


def _propose_land(state, player_id, amount_C):
    res = senate_api.propose(state, player_id, "land", act_type="sale", amount_C=amount_C)
    assert res["success"], res.get("message")
    return res["data"]["proposal_id"]


def _vote_all_humans(state, pids, support=True):
    for pid in state._turn_order:
        if state.get_player(pid).player_type == PlayerType.HUMAN:
            state._current_player_id = pid
            res = senate_api.vote(state, pid, pids, [support] * len(pids))
            assert res["success"], res.get("message")


def _vote(state, player_id, pids, votes):
    """指定玩家按指定票型投票（每玩家只投一次，幂等契约禁止重复投票）。"""
    state._current_player_id = player_id
    res = senate_api.vote(state, player_id, pids, votes)
    assert res["success"], res.get("message")


class TestWpFr2SenateIntermediateProjection(unittest.TestCase):
    """T-R2-01~05：中间投影 + veto_candidate_ids 权威集。"""

    def test_r2_01_vote_complete_intermediate_rows_available(self):
        """T-R2-01：投票完成（resolve 前）→ 中间 vote_results 每 submitted proposal 一行。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        _vote_all_humans(state, [pid1, pid2])
        view = senate_api.get_senate_view(state, "player1")
        self.assertTrue(view["success"], view.get("message"))
        data = view["data"]
        vr = data["vote_results"]
        self.assertIsInstance(vr, list)
        self.assertEqual(len(vr), 2, "每 submitted proposal 一行中间结果")
        by_id = {r["proposal_id"]: r for r in vr}
        self.assertEqual(set(by_id), {pid1, pid2})
        for pid in (pid1, pid2):
            self.assertTrue(VOTE_RESULT_KEYS <= set(by_id[pid]), f"row {pid} 缺字段")
        # 全部投支持 → 通过 → 进 tribune_veto
        self.assertEqual(data["current_step"], "tribune_veto")
        self.assertEqual(data["vote_results"], vr)

    def test_r2_02_passed_proposal_stable_support_rate(self):
        """T-R2-02：passed 提案支持率稳定（influence 权威和 = total）。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        state.senate_proposal_decision_complete = True
        _vote_all_humans(state, [pid1], support=True)  # 150 + 80 = 230 全支持
        view = senate_api.get_senate_view(state, "player1")
        row = next(r for r in view["data"]["vote_results"] if r["proposal_id"] == pid1)
        self.assertTrue(row["passed"])
        self.assertEqual(row["support_influence"], 230)
        self.assertEqual(row["oppose_influence"], 0)
        self.assertEqual(row["total_influence"], 230)
        self.assertFalse(row["vetoed"])
        # 与权威 producer 同值（唯一计算源）
        from src.core.systems.political_system import PoliticalSystem
        proposal = next(p for p in state.get_senate_proposals() if p["id"] == pid1)
        direct = PoliticalSystem(state).calculate_vote_result(proposal)
        self.assertEqual(row["support_influence"], direct["support_influence"])
        self.assertEqual(row["passed"], direct["passed"])

    def test_r2_03_failed_proposal_stable_support_rate(self):
        """T-R2-03：failed 提案支持率稳定（support < 50%）。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        state.senate_proposal_decision_complete = True
        # player1 反对（150 oppose）、player2 支持（80 support）→ 80/230 = 34.8% → failed
        _vote(state, "player1", [pid1], [False])
        _vote(state, "player2", [pid1], [True])
        view = senate_api.get_senate_view(state, "player1")
        row = next(r for r in view["data"]["vote_results"] if r["proposal_id"] == pid1)
        self.assertFalse(row["passed"])
        self.assertEqual(row["support_influence"], 80)
        self.assertEqual(row["oppose_influence"], 150)
        self.assertEqual(row["total_influence"], 230)

    def test_r2_04_mixed_pass_fail_candidates_pass_only(self):
        """T-R2-04：混合 PASS/FAIL → veto_candidate_ids == PASS only。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        pid3 = _propose_land(state, "player1", 20)
        state.senate_proposal_decision_complete = True
        _vote(state, "player1", [pid1, pid2, pid3], [True, False, True])
        # pid2：player1 反对（150 oppose）+ player2 支持（80 support）→ 80/230 = 34.8% 未通过；pid1/pid3 通过
        _vote(state, "player2", [pid1, pid2, pid3], [True, True, True])
        view = senate_api.get_senate_view(state, "player1")
        data = view["data"]
        self.assertEqual(set(data["veto_candidate_ids"]), {pid1, pid3})
        rows = {r["proposal_id"]: r for r in data["vote_results"]}
        self.assertTrue(rows[pid1]["passed"])
        self.assertFalse(rows[pid2]["passed"])
        self.assertTrue(rows[pid3]["passed"])

    def test_r2_05_failed_absent_from_veto_candidate_dto(self):
        """T-R2-05：failed 提案 absent from veto_candidate_ids DTO。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        _vote(state, "player1", [pid1, pid2], [True, False])
        _vote(state, "player2", [pid1, pid2], [True, True])  # pid2 未通过（80/230）
        view = senate_api.get_senate_view(state, "player1")
        self.assertNotIn(pid2, view["data"]["veto_candidate_ids"])
        self.assertIn(pid1, view["data"]["veto_candidate_ids"])


class TestWpFr2SenateFailClosed(unittest.TestCase):
    """T-R2-06~08：record_veto fail-closed 四条件 + 权威不变。"""

    def _mixed_state(self):
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        _vote(state, "player1", [pid1, pid2], [True, False])
        _vote(state, "player2", [pid1, pid2], [True, True])  # pid2 failed（80/230）
        return state, pid1, pid2

    def test_r2_06_direct_veto_failed_rejected_no_mutation(self):
        """T-R2-06：直连 veto() failed 提案 → 拒绝、vetoes 零变更、rejected_ids 明细。"""
        state, pid1, pid2 = self._mixed_state()
        before = set(state.get_senate_vetoes_copy())
        result = senate_api.veto(state, "player2", [pid2])
        self.assertFalse(result["success"], result.get("message"))
        data = result["data"]
        self.assertEqual(data["vetoed"], [])
        self.assertEqual(
            data["rejected_ids"],
            [{"proposal_id": pid2, "reason": "not_passed"}],
        )
        self.assertEqual(set(state.get_senate_vetoes_copy()), before, "拒绝分支零否决状态变更")

    def test_r2_07_zero_passed_converges_to_results(self):
        """T-R2-07：zero passed → current_step="results"、无否决候选、流程收敛。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        # 双方全投反对 → 全 failed
        _vote_all_humans(state, [pid1, pid2], support=False)
        view = senate_api.get_senate_view(state, "player1")
        data = view["data"]
        self.assertEqual(data["current_step"], "results", "zero-passed 跳过 tribune_veto 直接收敛")
        self.assertEqual(data["veto_candidate_ids"], [])
        self.assertIs(data["can_advance"], True)
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], False)
        rows = {r["proposal_id"]: r for r in data["vote_results"]}
        self.assertFalse(rows[pid1]["passed"])
        self.assertFalse(rows[pid2]["passed"])
        # 结算仍可走 resolve_senate（自然全拒零副作用）
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        self.assertEqual(resolved["data"]["passed_proposals"], [])

    def test_r2_08_passed_still_vetoable_by_eligible_tribune(self):
        """T-R2-08：passed 提案仍可被 eligible Tribune 否决（权威不变）。"""
        state, pid1, pid2 = self._mixed_state()
        result = senate_api.veto(state, "player2", [pid1])
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn(pid1, state.get_senate_vetoes_copy())
        self.assertNotIn(pid2, state.get_senate_vetoes_copy())
        # 否决后 view 权威行标记 vetoed（唯一 producer 同源）
        view = senate_api.get_senate_view(state, "player2")
        row = next(r for r in view["data"]["vote_results"] if r["proposal_id"] == pid1)
        self.assertTrue(row["vetoed"])
        self.assertFalse(row["passed"])


class TestWpFr2SenateIdempotency(unittest.TestCase):
    """T-R2-09~11：幂等 / 无重掷 / 阈值不变。"""

    def test_r2_09_refresh_reentry_stable(self):
        """T-R2-09：refresh ×2 / 另一 viewer 进入 → 支持率不变（幂等）。"""
        state = _build_state()
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        _vote_all_humans(state, [pid1, pid2], support=True)
        v1 = senate_api.get_senate_view(state, "player1")
        v2 = senate_api.get_senate_view(state, "player1")
        v3 = senate_api.get_senate_view(state, "player2")
        self.assertEqual(v1["data"]["vote_results"], v2["data"]["vote_results"])
        self.assertEqual(v1["data"]["vote_results"], v3["data"]["vote_results"])
        self.assertEqual(v1["data"]["veto_candidate_ids"], v2["data"]["veto_candidate_ids"])

    def test_r2_10_refresh_no_ai_vote_reroll(self):
        """T-R2-10：视图刷新不触发 AI 投票重掷（vote_source 注册表无新增 created 决策）。"""
        state = _build_state(with_ai_faction=True)
        pid1 = _propose_land(state, "player1", 50)
        pid2 = _propose_land(state, "player1", 30)
        state.senate_proposal_decision_complete = True
        _vote_all_humans(state, [pid1, pid2], support=True)
        # 首次投影：AI 派系（equites/player3）首次决策并持久化（created once）
        v1 = senate_api.get_senate_view(state, "player1")
        self.assertEqual(len(v1["data"]["vote_results"]), 2)
        snapshot1 = {k: dict(v) for k, v in state._senate_pending["vote_source"].items()}
        ai_sources = [
            src for pids in snapshot1.values() for src in pids.values()
        ]
        self.assertTrue(ai_sources, "首次投影应触发 AI 首次决策持久化")
        # 再次刷新：纯读已冻结票，零新决策
        v2 = senate_api.get_senate_view(state, "player1")
        snapshot2 = {k: dict(v) for k, v in state._senate_pending["vote_source"].items()}
        self.assertEqual(snapshot1, snapshot2, "刷新不得新增 AI 决策（零重掷）")
        self.assertEqual(v1["data"]["vote_results"], v2["data"]["vote_results"])

    def test_r2_11_threshold_weights_unchanged(self):
        """T-R2-11：投票阈值/权重不变（>0.5 边界行为 + 无第二算法静态审计）。"""
        # 边界行为：support == 50% → passed=False（阈值仍为严格 >0.5）
        state = _build_state()
        extra = Figure(id=6, name="平民派元老二", faction_id="populares", age=44)
        extra.class_tier = ClassTier.NOBILE
        extra.influence = 70
        state.add_member(extra)
        state.get_faction("populares").member_ids.append(6)  # populares 影响力 80+70=150
        pid1 = _propose_land(state, "player1", 50)
        state.senate_proposal_decision_complete = True
        _vote(state, "player1", [pid1], [True])
        _vote(state, "player2", [pid1], [False])  # 150 vs 150 → 50%
        view = senate_api.get_senate_view(state, "player1")
        row = next(r for r in view["data"]["vote_results"] if r["proposal_id"] == pid1)
        self.assertEqual(row["total_influence"], 300)
        self.assertEqual(row["support_influence"], 150)
        self.assertFalse(row["passed"], "support==50% 不得通过（阈值仍为严格 >0.5）")
        # 静态审计：无第二投票算法 / 阈值常量未被改
        import os
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        src_path = os.path.join(base, "src", "core", "systems", "political_system.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("support_influence / total_influence > 0.5", src)
        self.assertNotIn("support_influence / total_influence >= 0.5", src)
        self.assertNotIn("support_influence / total_influence > 0.6", src)


if __name__ == "__main__":
    unittest.main()
