# src/tests/test_api/test_wpfr3_senate_results.py
"""WP-F-R3 T-R3-01~04：Senate 结算分类快照（vetoed/failed 拆分）+ DTO 标签三分 + 旧存档容错 + 零否决镜像。

DATA 断言（后端权威产出，禁重算/重掷）：
- T-R3-01  resolve_senate 分类快照：vetoed/failed 快照不相交、并集 == rejected 快照；新增键对称
- T-R3-02  get_senate_view 结果态标签三分：passed/vetoed/rejected（缺陷 B）
- T-R3-03  旧存档容错：无 vetoed/failed 新字段 → 退化 rejected，不崩溃
- T-R3-04  零否决 + failed 场景（G7 实机镜像）：vetoed 快照空，failed 快照 == failed（缺陷 A/B 核心验收）
"""
import os
import sys

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


def _build_state():
    """optimates(player1, 影响力 150) / populares(player2, 影响力 80)；总影响力 230。"""
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

    state._players = {
        "player1": Player("player1", "optimates", PlayerType.HUMAN),
        "player2": Player("player2", "populares", PlayerType.HUMAN),
    }
    state._current_player_id = "player1"
    state._turn_order = ["player1", "player2"]
    return state


def _propose_land(state, player_id, amount_C):
    res = senate_api.propose(state, player_id, "land", act_type="sale", amount_C=amount_C)
    assert res["success"], res.get("message")
    return res["data"]["proposal_id"]


def _vote(state, player_id, pids, votes):
    state._current_player_id = player_id
    res = senate_api.vote(state, player_id, pids, votes)
    assert res["success"], res.get("message")


def test_tr3_01_resolve_senate_classification_snapshots():
    """T-R3-01：vetoed/failed 快照不相交、并集 == rejected 快照；新增键（id list）对称。"""
    state = _build_state()
    pid_pass = _propose_land(state, "player1", 50)
    pid_fail = _propose_land(state, "player1", 30)
    pid_veto = _propose_land(state, "player1", 20)
    # 投票：pid_pass/pid_veto 双支持（230 → passed），pid_fail player1 反对（80/230 → failed）
    _vote(state, "player1", [pid_pass, pid_fail, pid_veto], [True, False, True])
    _vote(state, "player2", [pid_pass, pid_fail, pid_veto], [True, True, True])
    # 对 passed 提案 record_veto（否决短路清零）
    state.record_senate_veto(pid_veto)

    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    data = resolved["data"]

    vetoed_ids = [p["id"] for p in data["vetoed_proposals_snapshot"]]
    failed_ids = [p["id"] for p in data["failed_proposals_snapshot"]]
    rejected_ids = [p["id"] for p in data["rejected_proposals_snapshot"]]
    assert vetoed_ids == [pid_veto]
    assert failed_ids == [pid_fail]
    # 不相交
    assert set(vetoed_ids) & set(failed_ids) == set()
    # 并集 == rejected 快照（backward-compat 聚合，逐字保留）
    assert set(rejected_ids) == set(vetoed_ids) | set(failed_ids)
    # 新增 id list 对称
    assert data["vetoed_proposals"] == [pid_veto]
    assert data["failed_proposals"] == [pid_fail]
    # passed 快照不变
    assert [p["id"] for p in data["passed_proposals_snapshot"]] == [pid_pass]
    # vote_results 每提案一行，passed/vetoed 字段正确（不变）
    by_id = {r["proposal_id"]: r for r in data["vote_results"]}
    assert set(by_id) == {pid_pass, pid_fail, pid_veto}
    assert by_id[pid_pass]["passed"] is True and by_id[pid_pass]["vetoed"] is False
    assert by_id[pid_fail]["passed"] is False and by_id[pid_fail]["vetoed"] is False
    assert by_id[pid_veto]["passed"] is False and by_id[pid_veto]["vetoed"] is True


def test_tr3_02_get_senate_view_result_labels():
    """T-R3-02：get_senate_view 结果态标签三分（passed/vetoed/rejected）+ veto_candidate_ids 空。"""
    state = _build_state()
    pid_pass = _propose_land(state, "player1", 50)
    pid_fail = _propose_land(state, "player1", 30)
    pid_veto = _propose_land(state, "player1", 20)
    _vote(state, "player1", [pid_pass, pid_fail, pid_veto], [True, False, True])
    _vote(state, "player2", [pid_pass, pid_fail, pid_veto], [True, True, True])
    state.record_senate_veto(pid_veto)
    assert senate_api.resolve_senate(state)["success"]

    view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    data = view["data"]
    assert data["current_step"] == "results"
    assert data["veto_candidate_ids"] == []

    by_id = {r["id"]: r for r in data["submitted_proposals"]}
    assert set(by_id) == {pid_pass, pid_fail, pid_veto}
    assert by_id[pid_pass]["result"] == "passed"
    assert by_id[pid_veto]["result"] == "vetoed"
    assert by_id[pid_fail]["result"] == "rejected"


def test_tr3_03_legacy_save_degradation():
    """T-R3-03：旧存档无 vetoed/failed 新字段 → 退化 rejected 全部 "rejected"，不崩溃。"""
    state = _build_state()
    passed_prop = {"id": 1, "type": "land", "act_type": "sale", "amount_C": 50, "percent": 0.05}
    rejected_prop = {"id": 2, "type": "land", "act_type": "sale", "amount_C": 30, "percent": 0.03}
    # 旧存档 result_data：仅 passed + rejected 快照（无 vetoed/failed 新字段）
    state.record_phase_result("senate", {
        "success": True,
        "message": "",
        "data": {
            "passed_proposals_snapshot": [passed_prop],
            "rejected_proposals_snapshot": [rejected_prop],
        },
    })

    view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    by_id = {r["id"]: r for r in view["data"]["submitted_proposals"]}
    assert set(by_id) == {1, 2}
    assert by_id[1]["result"] == "passed"
    assert by_id[2]["result"] == "rejected"


def test_tr3_04_zero_veto_failed_scenario():
    """T-R3-04：零否决 + failed 场景（G7 实机镜像）——vetoed 快照空，failed 快照 == failed。"""
    state = _build_state()
    pid_war = _propose_land(state, "player1", 50)
    pid_build = _propose_land(state, "player1", 40)
    pid_land = _propose_land(state, "player1", 30)
    # 宣战/建造双支持（passed），卖地双反对（0% failed）；无真实 veto
    _vote(state, "player1", [pid_war, pid_build, pid_land], [True, True, False])
    _vote(state, "player2", [pid_war, pid_build, pid_land], [True, True, False])

    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    data = resolved["data"]
    assert data["vetoed_proposals_snapshot"] == []
    assert data["vetoed_proposals"] == []
    assert [p["id"] for p in data["failed_proposals_snapshot"]] == [pid_land]
    assert [p["id"] for p in data["passed_proposals_snapshot"]] == [pid_war, pid_build]

    view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    by_id = {r["id"]: r for r in view["data"]["submitted_proposals"]}
    assert by_id[pid_land]["result"] == "rejected"
    assert by_id[pid_war]["result"] == "passed"
    assert by_id[pid_build]["result"] == "passed"
    # 「进入否决环节」集合（passed ∪ vetoed）== [宣战, 建造]，卖地不在其中（缺陷 A/B 核心验收）
    veto_stage_ids = [r["id"] for r in view["data"]["submitted_proposals"] if r["result"] in ("passed", "vetoed")]
    assert set(veto_stage_ids) == {pid_war, pid_build}
    assert pid_land not in veto_stage_ids
