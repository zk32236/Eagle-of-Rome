"""EOR20261013-02 · PC02-WITHDRAWAL — 后台「先庆典后投票」门（G1）运行时验收。

覆盖冻结验收表 `02-sa-design/PC02-Withdrawal/02-Acceptance-and-Regression.md`：
  AC-PC02W-01 正控（庆典 → 投票 → 成功）
  AC-PC02W-02 负控（未庆典直投 → CAMPAIGN_REQUIRED + Z1–Z9 零写入）★核心
  AC-PC02W-03 反 PC02 锁（无全局屏障：A 可先投，B 未庆典）
  AC-PC02W-04 逐演员锁（拒绝只看本人；补齐后可重试）
  AC-PC02W-05 结构性豁免（本派系零候选人 → 放行 ABSTAIN）
  AC-PC02W-06 顺序不变性（逐座位 vs 全员庆典后投票 → 同一当选者集合）
  AC-PC02W-09 计票时点（只在 resolve_population_slice 内结算 + 幂等）
  AC-PC02W-11 UI/API 谓词同义（can_vote ⟺ 未被门拒绝）
  AC-PC02W-12 重复提交 / 拒后重试（零额外票、零副作用累积）
  AC-PC02W-13 存档往返（含旧档缺键 → fail-closed → 可恢复）

设计源：`01-Design-Delta.md` §2（G1 = `submit_population_votes` 的 per-actor 门）、
        `03-Scope-and-NoTouch.md` §2（测试写面）。

约束：本模块为**新增**测试文件；不改任何既有断言、不 monkeypatch 产品内部、
不直置典礼/计票结果（所有正向结果经真实生产动作到达）。
"""
from __future__ import annotations

import copy
import json
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from src.api import population_api, session_api  # noqa: E402
from src.api import session_turn_service as turn_service  # noqa: E402
from src.core.game_state import GameState  # noqa: E402

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"
OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")
#: AC-06 固定种子：两份等价 state + 两次 resolve 前的 RNG 位置完全一致。
SEED = 20261023


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


# ---------------------------------------------------------------------------
# 构造（全部经真实工厂；无 controller 注入、无 store 直置）
# ---------------------------------------------------------------------------
def _session():
    """真实工厂会话（3 HUMAN，population 阶段）。"""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert len(pids) >= 3, pids
    return state, pids


def _enter_population(state, player_id):
    """走真实 UI 读路径进入人口阶段入口态（`get_population_view` 内含
    `process_population_disbandments` + `begin_population_phase`，`session_api.py:495-498`）。

    目的：让 AC-02 的「零写入」快照采集点位于**玩家已能看到投票界面**之后，
    从而证明拒绝本身不产生任何新增写入（设计 01 §2.4 的诚实披露口径）。
    """
    view = session_api.get_population_view(state, player_id)
    assert view.get("success"), view.get("message")


def _candidates(state):
    res = population_api._get_candidates_impl(state)
    assert res.get("success"), res
    return res["data"]


def _own_candidate_count(state, player_id):
    """与视图 `campaign_done` 第二项同义的读模型（本模块的独立 oracle）。"""
    faction_id = state.get_player(player_id).faction_id
    return sum(
        1 for rows in _candidates(state).values()
        for cand in rows if cand.get("faction_id") == faction_id
    )


def _selection(state):
    """每个有候选人的 office 取第一名候选人（确定性；其余 office 由产品归一为 ABSTAIN）。"""
    return {office: rows[0]["id"]
            for office, rows in _candidates(state).items() if rows}


def _make_own_faction_ineligible(state, player_id):
    """令本派系全员低于全部 min_ages ⇒ 五职候选人映射中本派系 0 行（AC-05 构造）。"""
    faction_id = state.get_player(player_id).faction_id
    members = [m for m in state.get_living_members() if m.faction_id == faction_id]
    assert members, "本派系须有存活成员"
    for member in members:
        member.age = 20


def _canon_row(row):
    return tuple(row) if isinstance(row, (list, tuple)) else row


def _zero_write_snapshot(state, player_id):
    """AC-02 的 Z1–Z9 逐面快照（任何写面变化都会让 dict 不相等）。"""
    book = turn_service._book(state)
    schedule = turn_service.obligations(state, "population")
    votes = state.get_population_votes()
    campaigns = state.get_population_campaigns()
    return {
        # Z1 票箱
        "Z1_votes": tuple(sorted(votes)),
        # Z2 庆典流水
        "Z2_campaigns": tuple(sorted(_canon_row(c) for c in campaigns)),
        # Z3 完成标志（本人 batch / vote）
        "Z3_flags": (state.get_batch_completed(player_id),
                     state.get_vote_completed(player_id)),
        # Z4 obligation 满足集（OID 稳定、revision-free）
        "Z4_obligations": tuple(
            (repr(o.obligation_id), o.satisfied) for o in schedule.obligations),
        # Z5 阶段就绪
        "Z5_phase_ready": turn_service.phase_ready(state, "population"),
        # Z6 receipt / committed fact 台账 + 修订号
        "Z6_book": (len(book.receipts), len(book.committed_facts),
                    len(book.consumed_receipts), book.revision_counter),
        # Z7 阶段结果
        "Z7_phase_result": copy.deepcopy(state.get_phase_result("population")),
        # Z8 光标 / 当前玩家
        "Z8_current": state.get_current_player().player_id,
        # Z9 impact / 权重输入（逐人物影响力 + 候选人映射）
        "Z9_figures": tuple(sorted((m.id, m.influence)
                                   for m in state.get_living_members())),
        "Z9_candidates": tuple(sorted(
            (office, tuple(sorted(c["id"] for c in rows)))
            for office, rows in _candidates(state).items())),
    }


def _votes_of(state, player_id):
    return [v for v in state.get_population_votes() if v[0] == player_id]


def _diff(before, after):
    return {key: (before[key], after[key]) for key in before if before[key] != after[key]}


# ===========================================================================
# AC-PC02W-01 正控：庆典 → 投票 → 成功
# ===========================================================================
def test_ac01_campaign_then_vote_succeeds():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    assert _own_candidate_count(state, pid) > 0, "前置：本派系须有候选人"

    camp = population_api.batch_campaign(state, pid, [])
    assert camp.get("success") is True, camp
    assert state.get_batch_completed(pid) is True

    result = session_api.submit_population_votes(state, pid, _selection(state))
    assert result.get("success") is True, result
    assert result["data"]["status"] in ("awaiting_players", "resolved"), result["data"]
    assert len(_votes_of(state, pid)) == 5, _votes_of(state, pid)


# ===========================================================================
# AC-PC02W-02 负控（★核心）：未庆典直投 → typed 拒绝 + 状态零变化
# ===========================================================================
def test_ac02_uncampaigned_direct_vote_is_typed_rejected_with_zero_write():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    # 前置：本派系**有**候选人（否则零候选人豁免会让本负控变空转）
    assert _own_candidate_count(state, pid) > 0, "前置：本派系须有候选人"
    assert state.get_batch_completed(pid) is False

    before = _zero_write_snapshot(state, pid)
    result = session_api.submit_population_votes(state, pid, _selection(state))
    after = _zero_write_snapshot(state, pid)

    # 断言 A：拒绝形状（typed）
    assert result.get("success") is False, result
    errors = result.get("errors") or []
    assert errors and errors[0].get("code") == "CAMPAIGN_REQUIRED", errors
    assert errors[0].get("message"), errors
    assert result["data"].get("campaign_done") is False, result["data"]
    assert result["data"].get("retryable") is True, result["data"]

    # 断言 B：零写入（Z1–Z9 逐面相等）
    assert after == before, _diff(before, after)


# ===========================================================================
# AC-PC02W-03 反 PC02 锁：无全局屏障（A 可先投，B 尚未庆典）
# ===========================================================================
def test_ac03_no_global_barrier_a_votes_while_b_never_campaigned():
    state, pids = _session()
    a, b = pids[0], pids[1]
    _enter_population(state, a)
    assert population_api.batch_campaign(state, a, []).get("success") is True
    assert state.get_batch_completed(b) is False

    result = session_api.submit_population_votes(state, a, _selection(state))

    # 若本条失败 ⇒ 说明误引入了「全员庆典后才许投票」的全局屏障（PC02 语义复活）。
    assert result.get("success") is True, result
    assert len(_votes_of(state, a)) == 5, _votes_of(state, a)
    assert state.get_batch_completed(b) is False
    assert _votes_of(state, b) == []


# ===========================================================================
# AC-PC02W-04 逐演员锁：拒绝只看本人；补齐庆典后可重试
# ===========================================================================
def test_ac04_rejection_is_per_actor_and_retry_after_campaign_succeeds():
    state, pids = _session()
    a, b = pids[0], pids[1]
    _enter_population(state, a)
    assert population_api.batch_campaign(state, a, []).get("success") is True
    assert session_api.submit_population_votes(state, a, _selection(state)).get("success") is True

    a_votes = _votes_of(state, a)
    a_campaigns = [_canon_row(c) for c in state.get_population_campaigns() if c[0] == a]

    rejected = session_api.submit_population_votes(state, b, _selection(state))
    assert rejected.get("success") is False, rejected
    assert (rejected.get("errors") or [{}])[0].get("code") == "CAMPAIGN_REQUIRED", rejected
    # A 的既有票/庆典不受影响
    assert _votes_of(state, a) == a_votes
    assert [_canon_row(c) for c in state.get_population_campaigns() if c[0] == a] == a_campaigns
    assert _votes_of(state, b) == []

    assert population_api.batch_campaign(state, b, []).get("success") is True
    retry = session_api.submit_population_votes(state, b, _selection(state))
    assert retry.get("success") is True, retry
    assert len(_votes_of(state, b)) == 5, _votes_of(state, b)


# ===========================================================================
# AC-PC02W-05 结构性豁免：本派系零候选人
# ===========================================================================
def test_ac05_zero_own_candidates_is_structurally_exempt():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    _make_own_faction_ineligible(state, pid)
    assert _own_candidate_count(state, pid) == 0, "构造：本派系候选人必须为 0 行"
    assert state.get_batch_completed(pid) is False

    result = session_api.submit_population_votes(state, pid, {})

    # 视图 `my_candidate_count == 0` 已允许此路径（`session_api.py:593`）⇒ G1 必须同义放行。
    assert result.get("success") is True, result
    votes = _votes_of(state, pid)
    assert len(votes) == 5, votes
    assert all(v[2] == 0 for v in votes), votes


# ===========================================================================
# AC-PC02W-06 顺序不变性：逐座位 vs 全员庆典后投票 → 同一结果
# ===========================================================================
def _outcome(state):
    payload = state.get_phase_result("population") or {}
    election = (payload.get("data") or {}).get("election_results", [])
    influence = {}
    for member in state.get_living_members():
        if member.faction_id:
            influence[member.faction_id] = influence.get(member.faction_id, 0) + member.influence
    return {
        "winners": {row["office"]: row["figure_id"] for row in election},
        "faction_influence": dict(sorted(influence.items())),
        "scores": {row["office"]: tuple(
            (c["figure_id"], c["score"]) for c in row.get("candidates", []))
            for row in election},
        "votes": tuple(sorted(state.get_population_votes())),
    }


def test_ac06_order_invariance_per_seat_vs_all_campaign_first():
    # 两份等价 state：同一固定种子下由真实工厂构建 ⇒ 候选人映射/影响力完全相同。
    random.seed(SEED)
    state_x, pids_x = _session()
    random.seed(SEED)
    state_y, pids_y = _session()
    assert pids_x == pids_y

    for state in (state_x, state_y):
        _enter_population(state, state.get_current_player().player_id)

    selection_x = _selection(state_x)
    selection_y = _selection(state_y)
    assert selection_x == selection_y, "两份 state 的候选人映射必须完全相同"

    def _campaign(state, pid):
        assert population_api.batch_campaign(state, pid, []).get("success") is True

    def _vote(state, pid, selection):
        return session_api.submit_population_votes(state, pid, selection)

    # 顺序 X（逐座位）：A 庆典 → A 投票 → B 庆典 → B 投票 → C 庆典 → C 投票（末位投票时结算）
    for pid in pids_x:
        _campaign(state_x, pid)
        outcome = _vote(state_x, pid, selection_x)
        assert outcome.get("success") is True, outcome

    # 顺序 Y（全员庆典后投票）：全员庆典 → A/B/C 依次投票
    for pid in pids_y:
        _campaign(state_y, pid)
    random.seed(SEED)  # 与 X 的 resolve 前 RNG 位置对齐（仅用于平局兜底，不改变输入）
    for pid in pids_y:
        outcome = _vote(state_y, pid, selection_y)
        assert outcome.get("success") is True, outcome

    outcome_x = _outcome(state_x)
    outcome_y = _outcome(state_y)

    assert outcome_x["winners"], "结算必须产出当选者"
    assert outcome_y["winners"] == outcome_x["winners"], "两种顺序必须选出同一当选者集合"
    assert outcome_y["faction_influence"] == outcome_x["faction_influence"]
    assert outcome_y["scores"] == outcome_x["scores"]
    assert outcome_y["votes"] == outcome_x["votes"]


# ===========================================================================
# AC-PC02W-09 计票时点：只在 resolve_population_slice 内结算（+ 幂等）
# ===========================================================================
def test_ac09_settlement_only_at_slice_resolve():
    state, pids = _session()
    _enter_population(state, pids[0])

    for pid in pids[:2]:
        assert population_api.batch_campaign(state, pid, []).get("success") is True
        res = session_api.submit_population_votes(state, pid, _selection(state))
        assert res.get("success") is True, res
        assert state.get_phase_result("population") is None, "部分人类投票不得结算"

    last = pids[2]
    assert population_api.batch_campaign(state, last, []).get("success") is True
    res = session_api.submit_population_votes(state, last, _selection(state))
    assert res.get("success") is True, res
    assert res["data"]["status"] == "resolved", res["data"]

    payload = state.get_phase_result("population")
    assert payload is not None
    election = (payload.get("data") or {}).get("election_results", [])
    offices = {row["office"] for row in election}
    assert offices, "结算必须产出 election_results"
    assert offices <= set(OFFICES), offices

    again = session_api.resolve_population_slice(state)
    assert again.get("success") is True, again
    assert "already resolved" in (again.get("message") or ""), again.get("message")


# ===========================================================================
# AC-PC02W-11 UI/API 谓词同义：can_vote ⟺ 未被 G1 拒绝（4 格矩阵，双向）
# ===========================================================================
@pytest.mark.parametrize("campaigned,zero_own", [
    (False, False),
    (True, False),
    (False, True),
    (True, True),
])
def test_ac11_view_can_vote_iff_not_rejected_by_the_gate(campaigned, zero_own):
    state, pids = _session()
    pid = pids[0]
    state.set_current_player(pid)
    _enter_population(state, pid)
    if zero_own:
        _make_own_faction_ineligible(state, pid)
    assert (_own_candidate_count(state, pid) == 0) is zero_own
    if campaigned:
        assert population_api.batch_campaign(state, pid, []).get("success") is True
    assert state.get_batch_completed(pid) is campaigned

    view = session_api.get_population_view(state, pid)
    assert view.get("success"), view.get("message")
    can_vote = view["data"]["can_vote"]

    result = session_api.submit_population_votes(state, pid, _selection(state))
    rejected = (result.get("success") is False and
                (result.get("errors") or [{}])[0].get("code") == "CAMPAIGN_REQUIRED")

    assert can_vote == (not rejected), (can_vote, rejected, result)
    if can_vote:
        assert result.get("success") is True, result


# ===========================================================================
# AC-PC02W-12 重复提交 / 拒后重试：零额外票、零副作用累积
# ===========================================================================
def test_ac12_double_submit_adds_no_ballot_and_no_extra_completion():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    assert population_api.batch_campaign(state, pid, []).get("success") is True
    assert session_api.submit_population_votes(state, pid, _selection(state)).get("success") is True

    votes_before = tuple(sorted(state.get_population_votes()))
    revision_before = turn_service._book(state).revision_counter

    second = session_api.submit_population_votes(state, pid, _selection(state))

    assert second.get("success") is False, second          # 非当前席位重提：既有准入拒绝
    assert tuple(sorted(state.get_population_votes())) == votes_before
    assert turn_service._book(state).revision_counter == revision_before


def test_ac12b_rejection_then_campaign_then_retry_without_side_effect_accumulation():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    before = _zero_write_snapshot(state, pid)

    for _attempt in range(2):
        rejected = session_api.submit_population_votes(state, pid, _selection(state))
        assert rejected.get("success") is False, rejected
        assert (rejected.get("errors") or [{}])[0].get("code") == "CAMPAIGN_REQUIRED", rejected
        assert _zero_write_snapshot(state, pid) == before, "拒绝不得累积副作用"

    assert population_api.batch_campaign(state, pid, []).get("success") is True
    accepted = session_api.submit_population_votes(state, pid, _selection(state))
    assert accepted.get("success") is True, accepted
    assert len(_votes_of(state, pid)) == 5


# ===========================================================================
# AC-PC02W-13 存档往返（含旧档缺键 → fail-closed → 可恢复）
# ===========================================================================
def _archive(state):
    # 真实序列化往返（与产品存档同形：先 JSON 再回填）
    return json.loads(json.dumps(state.to_dict(), ensure_ascii=False))


def test_ac13a_archive_roundtrip_keeps_completion_flag_and_allows_vote():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)
    assert population_api.batch_campaign(state, pid, []).get("success") is True

    restored = GameState(CONFIG_PATH)
    restored.load_from_dict(_archive(state))

    assert restored.get_batch_completed(pid) is True, "庆典完成标志必须随存档往返"
    result = session_api.submit_population_votes(restored, pid, _selection(restored))
    assert result.get("success") is True, result
    assert len(_votes_of(restored, pid)) == 5


def test_ac13b_legacy_archive_without_completion_key_fails_closed_then_recovers():
    state, pids = _session()
    pid = pids[0]
    _enter_population(state, pid)

    blob = _archive(state)
    blob.pop("_batch_completed_by_player", None)      # 模拟更早版本（无该键）的旧档
    legacy = GameState(CONFIG_PATH)
    legacy.load_from_dict(blob)
    assert legacy.get_batch_completed(pid) is False

    rejected = session_api.submit_population_votes(legacy, pid, _selection(legacy))
    assert rejected.get("success") is False, rejected      # fail-closed
    assert (rejected.get("errors") or [{}])[0].get("code") == "CAMPAIGN_REQUIRED", rejected
    assert legacy.get_population_votes() == []

    # 可恢复（非死锁）：一次合法零花费庆典即可。
    assert population_api.batch_campaign(legacy, pid, []).get("success") is True
    accepted = session_api.submit_population_votes(legacy, pid, _selection(legacy))
    assert accepted.get("success") is True, accepted
    assert len(_votes_of(legacy, pid)) == 5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
