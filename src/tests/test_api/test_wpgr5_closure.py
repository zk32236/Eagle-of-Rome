# src/tests/test_api/test_wpgr5_closure.py
"""WP-G-R5 DA-7（Plan §7.1 / 任务书 §2.2）— §20 收口补测（DATA）。

补齐 B2/B4 未覆盖的剩余 AC 专测：
- B-AC02 PUBLISH 阶段故障注入 → SUBMIT_PUBLISH_FAILED + 整包零发布（保 draft）
- B-AC04 候选资格四角色枚举（排除现任 Governor/Tribune）
- B-AC13 多独立错误稳定排序 + checks_skipped 短路
- C-AC02 输入完整性（缺 target / 重复 target）
- C-AC04 三战循环任命（同时性一次解析）

其余 B-AC/C-AC 面由 test_wpgr5_*.py 既有专测覆盖（见 DA-R5-B5/Ledger-归零对照表.md §AC 归属）。
RENDER（§20 #7/8/9/44 渲染面）归 SO 工单；G7_MANUAL 归 G7 必测清单。
"""
import copy
import random
from unittest import mock

import pytest

from src.core.game_state import GameState
from src.core.systems.political_system import PoliticalSystem
from src.core.entities.war import WarStatus
from src.api import senate_api

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, submit_request, command_draft, peace_draft, error_codes,
)
from src.tests.fixtures.wpgr4_fixtures import make_war, attach_active


@pytest.fixture(autouse=True)
def _preserve_global_rng():
    """隔离：本模块不改变全局 RNG 状态（避免影响后续测试的既有随机序列）。"""
    st = random.getstate()
    yield
    random.setstate(st)


def test_b_ac02_publish_fault_injection_zero_publish():
    """B-AC02：PUBLISH 阶段故障注入 → SUBMIT_PUBLISH_FAILED + 零发布 + 保 draft。

    R6 迁移（B-1 类 route→direct）：War command 分双路由 —— 断言面迁到 R6 双账本：
    (1) Senate 路由（threat 主动宣战）注入 `add_senate_proposal` 故障；
    (2) direct 路由（ongoing War）注入 `register_consul_war_decision` 故障。
    两路均须整包零发布（Proposal 集与 direct 账本均零写）。
    """
    b = build_r5_base()
    state = b["state"]
    ps = PoliticalSystem(state)
    # (1) Senate 路由：真 Senate 提案发布故障
    with mock.patch.object(GameState, "add_senate_proposal", side_effect=RuntimeError("injected")):
        result = ps.submit_proposal_package(
            FIXED["player"],
            submit_request(war_drafts=[command_draft(FIXED["war_threat"], b["consul_id"], 0)]))
    assert result["success"] is False
    assert "SUBMIT_PUBLISH_FAILED" in error_codes(result)
    assert state.get_senate_proposals() == []
    assert result["data"]["draft_preserved"] is True
    # (2) direct 路由：FROZEN ConsulWarDecision 登记故障 → 同样整包零发布
    with mock.patch.object(GameState, "register_consul_war_decision", return_value=False):
        result2 = ps.submit_proposal_package(
            FIXED["player"],
            submit_request(war_drafts=[command_draft(FIXED["war_ongoing"], b["cmd_a"].id, 0)]))
    assert result2["success"] is False
    assert "SUBMIT_PUBLISH_FAILED" in error_codes(result2)
    assert state.get_senate_proposals() == []
    assert not state.get_consul_war_decisions("S1")
    assert result2["data"]["draft_preserved"] is True


def test_b_ac04_candidate_eligibility_four_roles():
    """B-AC04：候选池含 consul / former consul / former praetor；排除现任 Governor / Tribune。"""
    b = build_r5_base(with_governor=True)
    pol = PoliticalSystem(b["state"])
    ids = [r["figure_id"] for r in pol.build_war_commander_candidates({})]
    assert b["consul_id"] in ids
    assert b["cmd_a"].id in ids      # ex-consul
    assert b["cmd_b"].id in ids      # ex-praetor
    assert b["cmd_gov"].id not in ids  # 现任 Province Governor 排除
    # Tribune 排除（构造在职 tribune）
    b["cmd_b"].office = "tribune"
    ids2 = [r["figure_id"] for r in PoliticalSystem(b["state"]).build_war_commander_candidates({})]
    assert b["cmd_b"].id not in ids2


def test_b_ac13_error_order_and_checks_skipped():
    """B-AC13：多个独立错误 → 稳定排序 + checks_skipped（前置不足短路）。"""
    b = build_r5_base()
    state = b["state"]
    ps = PoliticalSystem(state)
    result = ps.submit_proposal_package(FIXED["player"], submit_request(war_drafts=[
        command_draft(FIXED["war_ongoing"], None),          # COMMANDER_REQUIRED
        command_draft(FIXED["war_peace"], 9999),            # COMMANDER_TARGET_INVALID
    ]))
    assert result["success"] is False
    codes = error_codes(result)
    assert "COMMANDER_REQUIRED" in codes
    assert "COMMANDER_TARGET_INVALID" in codes
    assert codes == sorted(codes), "错误按 code 稳定排序"
    assert result["data"]["checks_skipped"], "前置不足 → checks_skipped 记录"

    # 合法包（无错误）→ 无 checks_skipped 阻断、成功发布
    ok = ps.submit_proposal_package(FIXED["player"], submit_request(war_drafts=[
        command_draft(FIXED["war_ongoing"], b["cmd_a"].id, 0)]))
    assert ok["success"], ok.get("errors")


def test_c_ac02_decision_integrity_missing_and_duplicate_target():
    """C-AC02：Plan 输入完整性——command 决策缺 target → 不崩（final None）；重复 target → 结构化拒绝。"""
    b = build_r5_base()
    state = b["state"]
    pol = PoliticalSystem(state)
    real_wars = pol._real_wars()
    decisions = [
        {"proposal_id": 1, "war_id": b["war_ongoing"].id, "outcome": "ENACTED",
         "mode": "command", "source": "ongoing",
         "payload": {"target_commander_id": None, "reinforcement_n": 0}, "snapshot_ref": {}},
        {"proposal_id": 2, "war_id": b["war_passive"].id, "outcome": "ENACTED",
         "mode": "command", "source": "ongoing",
         "payload": {"target_commander_id": b["cmd_a"].id, "reinforcement_n": 0}, "snapshot_ref": {}},
        {"proposal_id": 3, "war_id": "universe_extra", "outcome": "ENACTED",
         "mode": "command", "source": "ongoing",
         "payload": {"target_commander_id": b["cmd_a"].id, "reinforcement_n": 0}, "snapshot_ref": {}},
    ]
    plan = pol.build_war_resolution_plan({
        "current_turn": 1, "session_id": "S1", "decisions": decisions,
        "real_wars": real_wars, "available_legion_ids": [], "pending_war_ids": []})
    # 缺 target 的 war → final None（不崩）；重复 target → duplicate_targets 结构化拒绝
    assert plan["final_commander_by_war"][b["war_ongoing"].id] is None
    assert plan["duplicate_targets"] == [b["cmd_a"].id]
    with pytest.raises(RuntimeError):
        pol.commit_war_resolution(plan, None)


def test_c_ac04_three_war_cycle_single_resolution():
    """C-AC04：三战循环任命（A→B、B→A、新战→Consul）→ 边界一次解析全部生效。"""
    b = build_r5_base()
    state = b["state"]
    war_c = make_war("war_third", "Third War", status=WarStatus.ACTIVE, commander_id=None)
    attach_active(state, war_c)
    drafts = [
        command_draft(b["war_ongoing"].id, b["cmd_b"].id, 0),
        command_draft(b["war_peace"].id, b["cmd_a"].id, 0),
        command_draft("war_third", b["consul_id"], 0),
    ]
    sub = senate_api.propose_many(state, FIXED["player"], {"war_drafts": drafts})
    assert sub["success"], sub.get("errors")
    # Submit 零部署（三者 commander 均未变）
    assert b["war_ongoing"].commander_id == b["cmd_a"].id
    assert b["war_peace"].commander_id == b["cmd_b"].id
    assert war_c.commander_id is None

    class _Pass:
        def decide_vote(self, issue, faction, st):
            return True

    res = senate_api.resolve_senate(state, vote_decider=_Pass())
    assert res["success"], res.get("message")
    adv = senate_api.advance_senate_phase(state, FIXED["player"])
    assert adv["success"], adv.get("message")
    assert b["war_ongoing"].commander_id == b["cmd_b"].id
    assert b["war_peace"].commander_id == b["cmd_a"].id
    assert war_c.commander_id == b["consul_id"]
