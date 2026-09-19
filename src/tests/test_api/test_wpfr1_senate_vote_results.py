# src/tests/test_api/test_wpfr1_senate_vote_results.py
"""WP-F-R1 T-F04~T-F06 / T-F08：Senate 投票支持率全链（R1-F-03）+ GovOps 删除零业务影响（R1-F-04 后端侧）。

DATA 断言（权威已算结果透出，禁重算）：
- T-F04  resolve_senate 返回 vote_results[]（6 字段/提案）；get_senate_view 透传；phase_result 持久化
- T-F05  refresh（get_senate_view ×2）/ re-entry（再 resolve）数字不变；AI 票 reused 0 新决策
- T-F06  展示路径（get_senate_view）不触发 calculate_vote_result（monkeypatch 计数，AC-F03-6）
- T-F08  底层政府结果（governor/rebellion/fleet/public_announcement）不受 R1 改动影响

R6 迁移（SA §A.4/§B.4，DA-2 B2；WP-G-R6 DA-6 B1e）：legacy 单提案入口
``senate_api.propose`` **一次成功即关闭本会期选择**（`by_session` 同会期唯一 ⇒ 同会期二次
调用返回结构化 `PACKAGE_ALREADY_SUBMITTED`，不得循环追加）。故同会期多笔非 War（土地）
提案改经**唯一整包门面** `senate_api.propose_many` 一次提交（0…N），全部原命题逐条保留：

- vote_results 6 字段/提案、透传与持久化一致（T-F04）
- refresh ×2 / re-entry 数字不变 + 结算后重复 resolve 零重掷（T-F05）
- 展示路径零 `calculate_vote_result` 重入（T-F06）
"""
import os
import sys
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

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
        # 注意：get_senate_influence 仅统计 NOBILE 成员——AI 派系成员必须 NOBILE 才有元老院影响力
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


class _CountingVoteDecider:
    """instrumented decider（确定性实例 + 决策计数，非 mock-only）。"""

    def __init__(self, decision=True):
        self.decisions = 0
        self._decision = decision

    def decide_vote(self, issue, faction, state):
        self.decisions += 1
        return self._decision


def _propose_land(state, player_id, amount_C):
    """R6（SA §A.4/§B.4）：单笔土地提案经唯一整包门面 `propose_many` 一次提交。"""
    res = senate_api.propose_many(state, player_id, [
        {"type": "land", "params": {"act_type": "sale", "amount_C": amount_C}}])
    assert res["success"], res.get("errors") or res.get("message")
    return res["data"]["created"][0]["proposal_id"]


def _propose_lands(state, player_id, amounts):
    """R6（SA §A.4/§B.4，DA-2 B2）：同会期唯一整包提交，返回 `created` 顺序的 proposal_id。

    多笔非 War（土地）提案必须以**一次** `propose_many` 整包提交（0…N）；legacy 单提案
    入口 `senate_api.propose` 的**二次**调用即 B-3 失效面——本 helper 显式登记该结构化拒绝
    （`PACKAGE_ALREADY_SUBMITTED`），不静默追加、不改会期唯一性语义。
    """
    specs = [{"type": "land", "params": {"act_type": "sale", "amount_C": amount}}
             for amount in amounts]
    res = senate_api.propose_many(state, player_id, specs)
    assert res["success"], res.get("errors") or res.get("message")
    created = res["data"]["created"]
    assert [c["type"] for c in created] == ["land"] * len(amounts), created
    proposal_ids = [c["proposal_id"] for c in created]
    # B-3 失效面显式登记：同会期 legacy 单提案入口二次提交 ⇒ PACKAGE_ALREADY_SUBMITTED
    retry = senate_api.propose(state, player_id, "land", act_type="sale", amount_C=1)
    assert retry["success"] is False
    assert "PACKAGE_ALREADY_SUBMITTED" in [e.get("code") for e in retry["errors"]], retry
    assert len(state.get_senate_proposals()) == len(amounts)
    return proposal_ids


def _vote_all_humans(state, pids, support=True):
    for pid in state._turn_order:
        if state.get_player(pid).player_type == PlayerType.HUMAN:
            state._current_player_id = pid
            res = senate_api.vote(state, pid, pids, [support] * len(pids))
            assert res["success"], res.get("message")


def test_tf04_vote_result_dto_full_chain():
    """T-F04（AC-F03-1/2/3）：vote_results 6 字段/提案；透传 + 持久化一致。"""
    state = _build_state()
    pid1, pid2, pid3 = _propose_lands(state, "player1", [50, 30, 20])
    _vote_all_humans(state, [pid1, pid2, pid3])
    state._current_player_id = "player2"
    assert senate_api.veto(state, "player2", [pid3])["success"]

    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    data = resolved["data"]
    vr = data.get("vote_results")
    assert isinstance(vr, list) and len(vr) == 3
    by_id = {r["proposal_id"]: r for r in vr}
    assert set(by_id) == {pid1, pid2, pid3}
    for pid in (pid1, pid2, pid3):
        assert VOTE_RESULT_KEYS <= set(by_id[pid]), f"vote_results row {pid} missing fields"
        assert by_id[pid]["support_influence"] + by_id[pid]["oppose_influence"] == by_id[pid]["total_influence"]
    # 双支持 → 通过；保民官否决短路 → vetoed=True + total=0（QML「支持率 —」数据侧）
    assert by_id[pid1]["passed"] is True and by_id[pid1]["vetoed"] is False
    assert by_id[pid2]["passed"] is True and by_id[pid2]["vetoed"] is False
    assert by_id[pid3]["vetoed"] is True and by_id[pid3]["passed"] is False
    assert by_id[pid3]["total_influence"] == 0

    # get_senate_view 透传 + phase_result 持久化（同一权威存储值）
    view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    assert view["data"]["vote_results"] == vr
    persisted = state.get_phase_result("senate")
    assert persisted["data"]["vote_results"] == vr


def test_tf05_refresh_and_reentry_stable():
    """T-F05（AC-F03-4/5）：refresh ×2 / re-entry 数字不变；AI 票 reused 0 新决策。"""
    state = _build_state(with_ai_faction=True)
    pid1, pid2 = _propose_lands(state, "player1", [50, 30])
    _vote_all_humans(state, [pid1, pid2])

    decider1 = _CountingVoteDecider(decision=True)
    resolved1 = senate_api.resolve_senate(state, vote_decider=decider1)
    assert resolved1["success"]
    vr1 = resolved1["data"]["vote_results"]
    assert len(vr1) == 2
    # 首次 resolve：每提案 × 1 活跃 AI 派系（equites）恰一次决策
    assert decider1.decisions == 2

    # refresh 稳定性：get_senate_view 两次 → 数字一致（读持久化 phase_result）
    view1 = senate_api.get_senate_view(state, "player1")
    view2 = senate_api.get_senate_view(state, "player1")
    assert view1["data"]["vote_results"] == vr1
    assert view2["data"]["vote_results"] == vr1

    # stage re-entry：另一 viewer 再进入（重新 get_senate_view）→ 数字仍一致（持久化存储，无重算）
    view3 = senate_api.get_senate_view(state, "player2")
    assert view3["data"]["vote_results"] == vr1

    # 权威存储值仍在 phase_result（resolve 后立即读）
    persisted = state.get_phase_result("senate")
    assert persisted["data"]["vote_results"] == vr1

    # 结算后重复 resolve 不重掷 AI 票（0 新决策）——resolve 本身会清空 pending（C3 无跨会话
    # 泄漏语义），故此处只断言不重掷（AC-F03-6 展示无重入由 T-F06 承载）
    decider2 = _CountingVoteDecider(decision=True)
    resolved2 = senate_api.resolve_senate(state, vote_decider=decider2)
    assert resolved2["success"]
    assert decider2.decisions == 0, "结算后重复 resolve 不得重掷 AI 票"


def test_tf06_display_path_no_decider_reentry():
    """T-F06（AC-F03-6）：展示路径 get_senate_view 不触发二次 calculate_vote_result。"""
    from src.core.systems.political_system import PoliticalSystem

    state = _build_state(with_ai_faction=True)
    pid1, pid2 = _propose_lands(state, "player1", [50, 30])
    _vote_all_humans(state, [pid1, pid2])
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"]
    assert len(resolved["data"]["vote_results"]) == 2

    real = PoliticalSystem.calculate_vote_result
    calls = {"n": 0}

    def counting(self, proposal, vote_decider):
        calls["n"] += 1
        return real(self, proposal, vote_decider)

    with patch.object(PoliticalSystem, "calculate_vote_result", counting):
        view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    assert calls["n"] == 0, "展示路径不得触发二次 calculate_vote_result / decider 重入"
    assert view["data"]["vote_results"]


def test_tf08_underlying_government_results_unchanged():
    """T-F08（AC-F04-3/4/5）：GovOps 卡删除后后端政府结果/执行零改动。"""
    state = _build_state()
    pid1 = _propose_land(state, "player1", 50)
    _vote_all_humans(state, [pid1])
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    data = resolved["data"]
    # 政府业务结果仍在（governor/rebellion/fleet 执行零改动，R1-F-04 仅删展示卡）
    assert isinstance(data.get("governor_assignments"), list)
    assert isinstance(data.get("rebellion_commander_assignments"), list)
    assert isinstance(data.get("fleet_assignments"), list)
    ann = data.get("public_announcement") or {}
    enacted = ann.get("enacted_proposals") or []
    assert [p["proposal_id"] for p in enacted] == [pid1]  # 通过提案正常公示
    assert "vote_results" in data  # 追加键不破坏既有键
    view = senate_api.get_senate_view(state, "player1")
    assert view["success"]
    assert view["data"]["senate_result"]  # 权威结果仍可读
