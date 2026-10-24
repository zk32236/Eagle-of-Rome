"""EOR20261013-02 · PC02W — TD-PC02W-02：AC-02 在**真实 masked Store 事务**下的负控。

冻结来源：
  * `02-sa-design/PC02-Withdrawal/03-Scope-and-NoTouch.md` **R-5**（AC-02 必须在
    masked 夹具下再跑一遍）；
  * G5-PC02W **R1**（`04-sa-verify/PC02W/G5-Report-PC02W.md` §3）。

补的缺口（不是重复劳动）：现有 `test_pc02w_campaign_gate.py` 全部走
`session_api.submit_population_votes` **直调**，从未构造 Store、绑定 handoff
barrier、注册/激活 hotseat，也从未断言 masked 路径的拒绝返回 —— 见 G5
`source-audit.md:53`（"It never constructs a Store, binds a handoff barrier,
registers/activates a hotseat handle, or asserts the CAMPAIGN_REQUIRED
business-rejection return through the masked path."）。

本模块用**既有** masked 夹具形态（与 `test_gui/test_rework_d3d6_masked_chain.py`
的 `_prepared` / `_masked_store` 同源）跑同一条拒绝链，证明「未庆典投票」在 GUI
实际路径上：

  ① 得到**业务拒绝** `CAMPAIGN_REQUIRED`（不是 `AI_DRAIN_MASKED_FAILURE`、
     不是 continuation-failure、不落 failure overlay）；
  ② 走 `session_store._masked_business_rejection` 的**同席恢复**
     （座位仍是本人、`SEAT_ACTIVE`、witness 无 `failure` 调用、可继续本席位）；
  ③ **业务面零新增写**（票箱 / campaigns / 完成标志 / obligation / receipt 台账 /
     impact / phase_result / cursor 均不变）。

零写入边界（G5 R1 指定口径）：快照只取**业务面**。masked 事务本身的
`suspend_hotseat_session` / `_activate_seat` / epoch / 覆盖层 / 视图发布属于
**事务簿记**，不是业务提交，因此不在被断言的写面内（否则会把合法簿记误判为违规）。

产品零改动；本模块为新增测试文件：不改任何既有断言、不新增 skip/xfail、
不扩 `EXPECTED_HELPERS`。

WATERMARK: DA-Execute PC02W TD-02 masked negative control (test-only).
"""
from __future__ import annotations

import copy
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

from src.api import population_api, session_access, session_api  # noqa: E402
from src.api import session_turn_service as turn_service  # noqa: E402
from src.core.game_state import GameState  # noqa: E402
from src.ui.gui.session_store import (  # noqa: E402
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_3H = "gr_f_3h.json"


@pytest.fixture(autouse=True)
def _restore_rng():
    state = random.getstate()
    try:
        yield
    finally:
        random.setstate(state)


# ---------------------------------------------------------------------------
# 既有 masked 夹具（与 test_gui/test_rework_d3d6_masked_chain.py 同形）
# ---------------------------------------------------------------------------
class _Receiver:
    """即时 ack 的 query-invalidation 接收者（真实 Store 要求有人 ack）。"""

    def __init__(self, store):
        self.store = store
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


class _SyncWitness:
    """同步的 barrier/witness provider（生产由 GameShell 实现）。"""

    def __init__(self):
        self.calls = []

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return True

    def show_pending(self, txn, faction):
        self.calls.append(("pending", txn, faction))
        return True

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return True

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


def _prepared():
    """真实工厂 3-HUMAN 人口阶段会话 + 已注册 hotseat（唯一产品路径）。"""
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="population", scenario_file=SCENARIO_3H)
    assert res.get("success"), res.get("message")
    state = res["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert len(pids) == 3, pids
    state.set_current_player(pids[0])
    session_access.register_hotseat_session(state, pids[0], epoch=0)
    return state, pids


def _masked_store(state, viewer):
    """真实 `GuiSessionStore` + 绑定 barrier ⇒ `submitPopulationVotes` 走
    `_masked_submit_population_votes`（session_store.py:1435/5129）。"""
    store = GuiSessionStore(state)
    _Receiver(store)
    witness = _SyncWitness()
    store.setHandoffBarrierProvider(witness)
    store.initialize(viewer)
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == viewer
    return store, witness


# ---------------------------------------------------------------------------
# 读模型 oracle（独立于 Store 缓存，直接读 Core 权威状态）
# ---------------------------------------------------------------------------
def _candidates(state):
    impl = population_api._get_candidates_impl(state)
    assert impl.get("success"), impl
    return impl["data"]


def _own_candidate_count(state, player_id):
    faction_id = state.get_player(player_id).faction_id
    return sum(
        1 for rows in _candidates(state).values()
        for cand in rows if cand.get("faction_id") == faction_id
    )


def _selection(state):
    return {office: rows[0]["id"]
            for office, rows in _candidates(state).items() if rows}


def _row(row):
    return tuple(row) if isinstance(row, (list, tuple)) else row


def _votes_of(state, player_id):
    return [v for v in state.get_population_votes() if v[0] == player_id]


def _business_snapshot(state):
    """③ 的被断言写面：票箱/campaigns/flag/obligation/receipt/impact/
    phase_result/cursor（不含 masked 事务簿记）。"""
    book = turn_service._book(state)
    schedule = turn_service.obligations(state, "population")
    pids = [p.player_id for p in state.get_all_players()]
    return {
        # 票箱
        "votes": tuple(sorted(state.get_population_votes())),
        # 庆典流水
        "campaigns": tuple(sorted(_row(c) for c in state.get_population_campaigns())),
        # 每人完成标志（batch / vote）
        "flags": tuple(sorted(
            (pid, state.get_batch_completed(pid), state.get_vote_completed(pid))
            for pid in pids)),
        # obligation 满足集
        "obligations": tuple(
            (repr(o.obligation_id), o.satisfied) for o in schedule.obligations),
        "phase_ready": turn_service.phase_ready(state, "population"),
        # receipt / committed fact / consumed / revision
        "book": (len(book.receipts), len(book.committed_facts),
                 len(book.consumed_receipts), book.revision_counter),
        # 阶段结果
        "phase_result": copy.deepcopy(state.get_phase_result("population")),
        # 光标 / 当前玩家
        "current": state.get_current_player().player_id,
        # impact（逐人物影响力）+ 候选人映射
        "influence": tuple(sorted((m.id, m.influence)
                                  for m in state.get_living_members())),
        "candidates": tuple(sorted(
            (office, tuple(sorted(c["id"] for c in rows)))
            for office, rows in _candidates(state).items())),
    }


def _diff(before, after):
    return {key: (before[key], after[key])
            for key in before if before[key] != after[key]}


def _error_codes(feedback):
    return [e.get("code") for e in (feedback.get("errors") or [])
            if isinstance(e, dict)]


# ===========================================================================
# AC-02（masked）★ R-5/R1 核心：业务拒绝 + 同席恢复 + 业务面零新增写
# ===========================================================================
def test_ac02w_masked_uncampaigned_vote_is_business_rejection_same_seat_zero_write():
    state, pids = _prepared()
    pid = pids[0]
    store, witness = _masked_store(state, pid)

    # 前置：本派系**有**候选人（否则零候选人豁免会让本负控空转），且尚未庆典。
    assert _own_candidate_count(state, pid) > 0, "前置：本派系须有候选人"
    assert state.get_batch_completed(pid) is False, "前置：本席位尚未完成庆典"

    # 玩家已经处在「看得到投票界面」的入口态（Store 初始发布即真实读路径产物）。
    before_view = store.populationView
    assert before_view.get("campaign_done") is False, before_view.get("campaign_done")
    assert before_view.get("my_candidate_count") == _own_candidate_count(state, pid)

    before = _business_snapshot(state)
    feedback = store.submitPopulationVotes(_selection(state))
    after = _business_snapshot(state)

    # ── ① 业务拒绝（typed），不是 continuation-failure ────────────────────
    assert feedback.get("success") is False, feedback
    assert "CAMPAIGN_REQUIRED" in _error_codes(feedback), feedback
    data = feedback.get("data") or {}
    assert data.get("campaign_done") is False, data
    assert data.get("retryable") is True, data
    # 「续跑失败 / masked failure」的判别标记一个都不许出现。
    assert "AI_DRAIN_MASKED_FAILURE" not in _error_codes(feedback), feedback
    assert data.get("status") != "masked_failure", data
    # 四要素公开字段保持（同席恢复失败时会被改写的正是这四项之外的东西）。
    assert {"success", "message", "errors", "data"} <= set(feedback), sorted(feedback)

    # ── ② 同席恢复（不是 failure overlay）────────────────────────────────
    assert store.seatLifecycle == SEAT_ACTIVE, store.seatLifecycle
    assert store.seatLifecycle != SEAT_MASKED_FAILURE
    assert store.handoffFailureKind == "", store.handoffFailureKind
    assert not [c for c in witness.calls if c[0] == "failure"], witness.calls
    # 事务确凿走过 masked 机（arm 覆盖 + 同席重新激活的 unmask 见证），
    # 而非未加掩码的直通分支。
    assert [c for c in witness.calls if c[0] == "arm"], witness.calls
    assert [c for c in witness.calls if c[0] == "unmask"], witness.calls
    assert store.viewerPlayerId == pid, store.viewerPlayerId
    # 拒绝后仍是本席位、仍可继续（视图重新发布且 campaign 仍可做）。
    assert store.populationView.get("campaign_done") is False
    assert store.canCampaign is True, "同席恢复后玩家必须能继续本席位"

    # ── ③ 业务面零新增写 ────────────────────────────────────────────────
    assert after == before, _diff(before, after)
    assert _votes_of(state, pid) == []


# ===========================================================================
# AC-02（masked）恢复：真实庆典提交后重投 → 成功（同席位可继续）
# ===========================================================================
def test_ac02w_masked_rejection_then_campaign_then_retry_succeeds():
    state, pids = _prepared()
    pid = pids[0]
    store, witness = _masked_store(state, pid)
    assert state.get_batch_completed(pid) is False

    rejected = store.submitPopulationVotes(_selection(state))
    assert rejected.get("success") is False, rejected
    assert "CAMPAIGN_REQUIRED" in _error_codes(rejected), rejected
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pid

    # 走真实 Store 命令（adapter → population_api.batch_campaign）完成本席庆典。
    campaign = store.doBatchCampaign([])
    assert campaign.get("success") is True, campaign
    assert state.get_batch_completed(pid) is True

    accepted = store.submitPopulationVotes(_selection(state))
    assert accepted.get("success") is True, accepted
    assert len(_votes_of(state, pid)) == 5, _votes_of(state, pid)
    # 3 HUMAN：真实路径切到下一席（masked pending），没有 failure overlay。
    assert store.seatLifecycle != SEAT_MASKED_FAILURE, store.seatLifecycle
    assert not [c for c in witness.calls if c[0] == "failure"], witness.calls


# ===========================================================================
# RED-first 证明（非产品改动）：去掉 G1 条件后，本负控即失效
# ===========================================================================
def test_red_proof_gate_absence_removes_the_business_rejection(monkeypatch):
    """证明本用例**确实能捕获 G1 缺失**，且证明手段不碰产品文件。

    做法：在测试进程内把门所读的唯一判据 `GameState.get_batch_completed`
    临时改为恒 True（等价于「产品里没有 G1」），再跑同一条真实 masked 路径。
    若门存在，则此构造下必然**不再**出现 `CAMPAIGN_REQUIRED`，且票会被真实写入
    —— 于是上面 `test_ac02w_masked_*` 的断言在门缺失时会失败（RED 可捕获）。
    monkeypatch 由 pytest 在测试结束时自动还原，产品文件零改动。
    """
    state, pids = _prepared()
    pid = pids[0]
    store, witness = _masked_store(state, pid)
    assert state.get_batch_completed(pid) is False

    monkeypatch.setattr(GameState, "get_batch_completed",
                        lambda self, player_id: True)

    feedback = store.submitPopulationVotes(_selection(state))

    # 门缺失 ⇒ 不再有业务拒绝（AC-02 的断言在此状态下会失败）。
    assert "CAMPAIGN_REQUIRED" not in _error_codes(feedback), feedback
    # 门缺失 ⇒ 业务写真实发生（正是 ③ 要挡住的东西）。
    assert len(_votes_of(state, pid)) == 5, _votes_of(state, pid)
    assert state.get_population_votes(), "门缺失时票箱必须发生变化"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
