"""
WP-02b v2.1 投票批量结算 — FV-01~FV-21 永久回归测试

对照 SA-Development-Task.md v2.1 §8 永久故障回归矩阵:

| ID   | 场景                              | 必须断言                                         |
|:----:|:---------------------------------|:------------------------------------------------|
| FV-01 | 第一个投票记录写入异常              | vote records/completion 恢复前态；guard 释放       |
| FV-02 | 第二条 vote record 写入异常       | 同 FV-01                                         |
| FV-03 | signature 写入异常               | 完整回滚；重试只投一次                            |
| FV-04 | completion 写入异常              | 完整回滚；其他玩家 completion 不变                 |
| FV-05 | snapshot 读取异常                | 返回 failure；guard 释放；后续批次成功             |
| FV-06 | rollback 自身异常                | 返回可诊断 failure；guard 仍释放                   |
| FV-07 | 同 signature 重复                | 第一次写入，第二次幂等 success/零写                |
| FV-08 | 不同 signature 并发              | 一个 ACQUIRED；另一个 BATCH_BUSY                  |
| FV-09 | 两玩家隔离                       | p1 成功不推进 p2；p2 失败不回退 p1                |
| FV-10 | 存档/恢复                        | active guard 不持久化；恢复后新批次可提交          |
| FV-11 | 非法容器 DTO                     | None/int/string/dict 全部结构化 failure            |
| FV-12 | 非法 office / figure_id 值        | 非法 office、缺失字段、额外字段 → 结构化 error     |
| FV-13 | 弃权 ABSTAIN 显式写入            | figure_id=0 写入；计入 vote_done                  |
| FV-14 | 结算 resolution 由 resolve_population_slice 触发 | batch_vote 不触发结算               |
| FV-15 | 结算触发前的投票记录完整性         | 多玩家投票全部参与加权计票                        |
| FV-16 | clear 后重投                     | 清理后新批次正常提交；old signatures 不拦截        |
| FV-17 | office="" 回归测试               | vote records 的 office 不为 ""                     |
| FV-18 | ABSTAIN 不影响其他 office        | consul 弃权不影响 praetor 等正常投票+结算          |
| FV-19 | 空 batch 拒绝 [v2.1 NEW]         | batch_vote([]) → structured failure, zero write    |
| FV-20 | 部分 office batch 拒绝 [v2.1 NEW]| 缺失 office → structured failure, zero write       |
| FV-21 | 重复 office 拒绝 [v2.1 NEW]       | duplicate office → DUPLICATE_OFFICE, zero write    |
"""
import threading
import pytest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.service.population_service import check_and_commit_vote
from src.api.population_api import batch_vote, _validate_vote_json_container, _validate_vote_dto_types


# ========== Fixtures ==========

@pytest.fixture
def vote_state():
    """基础状态供 batch_vote v2.1 测试用。"""
    config = {
        "testing": {"bypass_player_check": True, "auto_population": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "faction_initial_treasury": 100,
            "faction_member_limit": 6,
        },
        "political_rules": {
            "min_festival_age": 30,
            "office_cooldowns": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
            "offices_per_election": {"consul": 1, "censor": 1, "praetor": 1, "quaestor": 1, "tribune": 1},
            "min_ages": {"consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30},
            "office_rank": {"dictator": 6, "censor": 4, "consul": 5, "praetor": 3, "tribune": 1, "quaestor": 2},
            "office_influence_bonus": {"dictator": 60, "censor": 50, "consul": 40, "praetor": 30, "tribune": 20, "quaestor": 10},
            "ex_office_influence_bonus": {"ex-dictator": 30, "ex-censor": 25, "ex-consul": 20, "ex-praetor": 15, "ex-tribune": 10, "ex-quaestor": 5},
            "family_prestige": {"Julius": 4, "Cornelius": 4, "Claudius": 3, "Fabius": 3, "Aemilius": 2, "Servilius": 2},
            "candidates_per_election": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)

    # 玩家
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(player1)
    player2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.HUMAN)
    state.add_player(player2)

    # 派系
    faction1 = Faction(id="f1", name="Optimates", treasury=1000)
    state.add_faction(faction1)
    faction2 = Faction(id="f2", name="Populares", treasury=1000)
    state.add_faction(faction2)

    # 人物 — f1 (至少 5 个，每 office 一个候选人)
    # ATTEMPT-2 R2: create_nobile() 含 random.randint() 导致三方面非确定性：
    #   ① influence 随机 (random family_prestige via 随机 nomen)
    #   ② candidate 资格属性随机 (martial/charisma… → get_candidates 排序随机)
    # 修复：create+update 后将 influence + 资格属性全部显式固定。
    # f1: influence=120/fig, 资格属性高位确保 quaestor 候选
    for i in range(1, 6):
        fig = Figure.create_nobile(i, "f1", 40 + i)
        fig.wealth = 100
        fig.popularity = 10
        fig.martial = 10 if i == 1 else 5    # R2: deterministic candidate sorting
        fig.charisma = 10 if i == 1 else 5
        fig.intelligence = 10 if i == 1 else 5
        fig.zeal = 10 if i == 1 else 5
        fig.update_influence()
        fig.influence = 120  # R2: deterministic fixed influence (dominant)
        state.add_member(fig)

    # 人物 — f2
    # f2: influence=100/fig, 资格属性略低于 f1 但确保第二名在 quaestor 候选
    for i in range(6, 11):
        fig = Figure.create_nobile(i, "f2", 40 + i)
        fig.wealth = 80
        fig.popularity = 8
        fig.martial = 9 if i == 6 else 5     # R2: deterministic candidate sorting
        fig.charisma = 9 if i == 6 else 5
        fig.intelligence = 9 if i == 6 else 5
        fig.zeal = 9 if i == 6 else 5
        fig.update_influence()
        fig.influence = 100  # R2: deterministic fixed influence (weaker)
        state.add_member(fig)

    state.set_current_player("p1")
    return state


def _make_v21_entries():
    """构建 v2.1 格式的合法 5-office entries (all ABSTAIN=0 for simplicity)."""
    return [
        {"office": "consul", "figure_id": 0},
        {"office": "censor", "figure_id": 0},
        {"office": "praetor", "figure_id": 0},
        {"office": "quaestor", "figure_id": 0},
        {"office": "tribune", "figure_id": 0},
    ]


def _make_v21_entry_tuples(entries=None):
    """Convert v2.1 entries to (office, figure_id) tuples for check_and_commit_vote."""
    if entries is None:
        entries = _make_v21_entries()
    return [(e["office"], e["figure_id"]) for e in entries]


# ========== FV-01: 第一个投票记录写入异常 ==========

def test_fv01_first_vote_write_exception_rollback(vote_state):
    """FV-01: 第一个 record_population_vote 调用异常 → 完整回滚 + guard 释放。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv01_v21_sig"

    original_vote_completed = state.get_vote_completed("p1")

    # Mock record_population_vote to raise on first call
    call_count = [0]
    original_rpv = state.record_population_vote
    def failing_rpv(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Simulated first vote write failure")
        return original_rpv(*args, **kwargs)

    with patch.object(state, 'record_population_vote', side_effect=failing_rpv):
        result = check_and_commit_vote(state, "p1",
            _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    assert "rolled back" in result["message"].lower()
    # Completion not set
    assert state.get_vote_completed("p1") == original_vote_completed
    # Guard released
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()


# ========== FV-02: 第二条 vote record 写入异常 ==========

def test_fv02_second_vote_write_exception_rollback(vote_state):
    """FV-02: 第二条 vote record 写入异常 → 完整回滚 + guard 释放。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv02_v21_sig"

    original_vote_completed = state.get_vote_completed("p1")

    call_count = [0]
    original_rpv = state.record_population_vote
    def failing_rpv(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("Simulated second vote write failure")
        return original_rpv(*args, **kwargs)

    with patch.object(state, 'record_population_vote', side_effect=failing_rpv):
        result = check_and_commit_vote(state, "p1",
            _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    assert not state.has_committed_vote_batch(sig)
    assert state.get_vote_completed("p1") == original_vote_completed
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()


# ========== FV-03: signature 写入异常 ==========

def test_fv03_signature_write_exception_rollback(vote_state):
    """FV-03: signature 写入异常 → 完整回滚；重试只投一次。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv03_v21_sig"

    original_votes_len = len(state.snapshot_vote_state())

    with patch.object(state, 'record_committed_vote_batch',
                      side_effect=RuntimeError("Signature write failure")):
        result = check_and_commit_vote(state, "p1",
            _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    # Votes rolled back to original length
    assert len(state.snapshot_vote_state()) == original_votes_len
    assert not state.has_committed_vote_batch(sig)
    # Guard released
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()

    # Retry succeeds and only writes once
    result2 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig)
    assert result2["success"] is True
    assert result2["data"]["vote_count"] == 5


# ========== FV-04: completion 写入异常 ==========

def test_fv04_completion_write_exception_rollback(vote_state):
    """FV-04: completion 写入异常 → 完整回滚；其他玩家 completion 不变。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv04_v21_sig"

    # Set p2 as already completed
    state.set_vote_completed("p2", True)
    p2_completed_before = state.get_vote_completed("p2")

    with patch.object(state, 'set_vote_completed',
                      side_effect=RuntimeError("Completion write failure")):
        result = check_and_commit_vote(state, "p1",
            _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    # p2 completion unchanged
    assert state.get_vote_completed("p2") == p2_completed_before
    # p1 completion not set
    assert not state.get_vote_completed("p1")
    assert not state.has_committed_vote_batch(sig)
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()


# ========== FV-05: snapshot 读取异常 ==========

def test_fv05_snapshot_read_exception(vote_state):
    """FV-05: snapshot 读取异常 → 返回 failure；guard 释放；后续批次成功。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv05_v21_sig"

    with patch.object(state, 'snapshot_vote_state',
                      side_effect=RuntimeError("Snapshot read failure")):
        result = check_and_commit_vote(state, "p1",
            _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    # Guard released
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()

    # Subsequent batch succeeds
    result2 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig + "_retry")
    assert result2["success"] is True


# ========== FV-06: rollback 自身异常 ==========

def test_fv06_rollback_self_exception_guard_released(vote_state):
    """FV-06: rollback 自身异常 → 返回可诊断 failure；guard 仍释放。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv06_v21_sig"

    # Make restore_vote_state fail
    with patch.object(state, 'restore_vote_state',
                      side_effect=RuntimeError("Restore failure")):
        # Also make record_population_vote fail to trigger rollback path
        with patch.object(state, 'record_population_vote',
                          side_effect=RuntimeError("Vote write failure")):
            result = check_and_commit_vote(state, "p1",
                _make_v21_entry_tuples(entries), sig)

    assert result["success"] is False
    # Guard still released despite rollback failure
    assert state.try_acquire_batch_guard() is True
    state.release_batch_guard()


# ========== FV-07: 同 signature 重复 ==========

def test_fv07_same_signature_idempotent(vote_state):
    """FV-07: 同 signature 重复 → 第一次写入，第二次幂等 success/零写。"""
    state = vote_state
    entries = _make_v21_entries()
    sig = "test_fv07_v21_sig"

    # First call — should write
    result1 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig)
    assert result1["success"] is True
    assert result1["data"]["vote_count"] == 5

    votes_after_first = len(state.snapshot_vote_state())

    # Second call — idempotent, zero write
    result2 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig)
    assert result2["success"] is True
    assert result2["data"].get("already_committed") is True
    assert result2["data"]["vote_count"] == 0

    # No new votes written
    assert len(state.snapshot_vote_state()) == votes_after_first


# ========== FV-08: 不同 signature 并发 ==========

def test_fv08_concurrent_different_signatures_busy(vote_state):
    """FV-08: 不同 signature 并发 → 一个 ACQUIRED；另一个 BATCH_BUSY。"""
    state = vote_state
    entries = _make_v21_entries()

    barrier = threading.Barrier(2)
    results = [None, None]
    original_snapshot = state.snapshot_vote_state

    def slow_snapshot(*args, **kwargs):
        import time
        time.sleep(0.05)
        return original_snapshot(*args, **kwargs)

    def worker(idx, sig):
        barrier.wait()
        with patch.object(state, 'snapshot_vote_state', side_effect=slow_snapshot):
            result = check_and_commit_vote(state, "p1",
                _make_v21_entry_tuples(entries), sig)
        results[idx] = result

    t1 = threading.Thread(target=worker, args=(0, "test_fv08_v21_sig_a"))
    t2 = threading.Thread(target=worker, args=(1, "test_fv08_v21_sig_b"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    successes = [r for r in results if r and r["success"]]
    busies = [r for r in results if r and not r["success"] and
              any(e.get("code") == "BATCH_BUSY" for e in r.get("errors", []))]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(busies) == 1, f"Expected exactly 1 BUSY, got {len(busies)}"
    assert busies[0]["data"].get("retryable") is True


# ========== FV-09: 两玩家隔离 ==========

def test_fv09_player_isolation(vote_state):
    """FV-09: p1 成功不推进 p2；p2 失败不回退 p1。"""
    state = vote_state
    entries = _make_v21_entries()

    # p1 succeeds
    result1 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), "test_fv09_v21_p1_sig")
    assert result1["success"] is True
    assert state.get_vote_completed("p1") is True
    # p2 not affected
    assert state.get_vote_completed("p2") is False

    # p2 fails
    with patch.object(state, 'record_population_vote',
                      side_effect=RuntimeError("p2 vote failure")):
        result2 = check_and_commit_vote(state, "p2",
            _make_v21_entry_tuples(entries), "test_fv09_v21_p2_sig")
    assert result2["success"] is False
    # p1 still completed
    assert state.get_vote_completed("p1") is True
    # p2 not completed
    assert state.get_vote_completed("p2") is False


# ========== FV-10: 存档/恢复 ==========

def test_fv10_save_restore_guard_not_persisted(vote_state):
    """FV-10: active guard 不持久化；恢复后新批次可提交。"""
    state = vote_state
    entries = _make_v21_entries()

    # First batch succeeds
    result1 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), "test_fv10_v21_sig")
    assert result1["success"] is True

    # Serialize and deserialize
    data = state.to_dict()
    restored = GameState.create_for_testing(state.config.to_dict() if hasattr(state.config, 'to_dict') else {})
    restored.load_from_dict(data)

    # Guard should be unlocked after restore
    assert restored.try_acquire_batch_guard() is True
    restored.release_batch_guard()

    # New batch can be submitted with a different signature
    with patch.dict(restored.config._config, {"testing": {"bypass_player_check": True}}):
        pass  # ensure bypass is set

    result2 = check_and_commit_vote(restored, "p2",
        _make_v21_entry_tuples(entries), "test_fv10_v21_sig_new")
    assert result2["success"] is True

    # Old signature is idempotent after restore
    result3 = check_and_commit_vote(restored, "p1",
        _make_v21_entry_tuples(entries), "test_fv10_v21_sig")
    assert result3["success"] is True
    assert result3["data"].get("already_committed") is True


# ========== FV-11: 非法容器 DTO ==========

@pytest.mark.parametrize("bad_entries,reason_fragment", [
    (None, "None"),
    (42, "int"),
    ("string", "string"),
    ({"office": "consul"}, "dict"),
    (True, "bool"),
])
def test_fv11_invalid_container_dto(bad_entries, reason_fragment):
    """FV-11: 非法容器 DTO → 结构化 failure。"""
    errors = _validate_vote_json_container(bad_entries)
    assert len(errors) == 1
    assert reason_fragment in errors[0]["reason"]


# ========== FV-12: 非法 office / figure_id 值 ==========

@pytest.mark.parametrize("entry,expect_error", [
    ({"office": "consul", "figure_id": 1}, False),
    ({"office": "consul", "figure_id": 0}, False),  # ABSTAIN valid
    ({"figure_id": 1}, True),                         # missing office
    ({"office": "consul"}, True),                     # missing figure_id
    ({"office": "consul", "figure_id": 1, "choice": "FOR"}, True),  # extra field
    ({"office": "consul", "figure_id": 1.5}, True),   # float figure_id
    ({"office": "consul", "figure_id": True}, True),   # bool figure_id
    ({"office": "consul", "figure_id": "42"}, True),   # string figure_id
    ({"office": 123, "figure_id": 1}, True),           # int office
])
def test_fv12_dto_type_validation(entry, expect_error):
    """FV-12: DTO 类型校验 v2.1 — {office, figure_id}。"""
    errors = _validate_vote_dto_types([entry])
    if expect_error:
        assert len(errors) >= 1, f"Expected error for entry={entry}"
    else:
        assert len(errors) == 0, f"Unexpected error for entry={entry}"


# ========== FV-13: 弃权 ABSTAIN 显式写入 ==========

def test_fv13_abstain_explicitly_written(vote_state):
    """FV-13: figure_id=0 ABSTAIN 记录持久化；参与 vote_done 计算。
    使用 check_and_commit_vote 直调绕过 API 候选人校验（测试核心事务层）。"""
    state = vote_state
    entry_tuples = [
        ("consul", 0),       # ABSTAIN
        ("censor", 0),        # ABSTAIN
        ("praetor", 1),       # FOR
        ("quaestor", 2),       # FOR
        ("tribune", 3),        # FOR
    ]
    sig = "test_fv13_v21_sig"

    result = check_and_commit_vote(state, "p1", entry_tuples, sig)
    assert result["success"] is True
    assert result["data"]["vote_count"] == 5

    votes = state.get_population_votes()
    p1_votes = [v for v in votes if v[0] == "p1"]
    assert len(p1_votes) == 5

    # All records are 3-tuples (v2.1)
    for v in p1_votes:
        assert len(v) == 3, f"Vote record should be 3-tuple, got {len(v)}: {v}"
        assert v[1] in {"consul", "censor", "praetor", "quaestor", "tribune"}

    # ABSTAIN entries exist with figure_id=0
    abstains = [v for v in p1_votes if v[2] == 0]
    assert len(abstains) == 2

    # vote_done=true (completion set)
    assert state.get_vote_completed("p1") is True

    # office not empty string (FV-17)
    offices = {v[1] for v in p1_votes}
    assert "" not in offices


# ========== FV-14: 结算不在 batch_vote 内触发 ==========

def test_fv14_batch_vote_no_inline_resolution(vote_state):
    """FV-14: check_and_commit_vote 返回成功但无 resolution 字段 (FC-09)。"""
    state = vote_state
    entry_tuples = _make_v21_entry_tuples()
    sig = "test_fv14_v21_sig"

    result = check_and_commit_vote(state, "p1", entry_tuples, sig)
    assert result["success"] is True
    # v2.1: resolution 不在 batch_vote 返回值中 (FC-09)
    data = result["data"]
    assert "resolution" not in data, "FC-09 violation: resolution should not be in batch_vote result"
    assert data["vote_count"] == 5
    assert "offices_voted" in data


# ========== FV-15: 多玩家结算完整性 ==========

def test_fv15_multi_player_vote_integrity(vote_state):
    """FV-15: 多玩家 batch_vote → 投票记录完整，office 字段正确。"""
    state = vote_state
    entries_p1 = [
        ("consul", 1),
        ("censor", 2),
        ("praetor", 3),
        ("quaestor", 4),
        ("tribune", 5),
    ]

    # p1 votes via core
    result1 = check_and_commit_vote(state, "p1", entries_p1, "test_fv15_p1_sig")
    assert result1["success"] is True

    # p2 votes (ABSTAIN all)
    entries_p2 = [("consul", 0), ("censor", 0), ("praetor", 0), ("quaestor", 0), ("tribune", 0)]
    result2 = check_and_commit_vote(state, "p2", entries_p2, "test_fv15_p2_sig")
    assert result2["success"] is True

    votes = state.get_population_votes()
    assert len(votes) == 10  # 5 + 5

    # Each vote record has correct office
    offices_seen = set()
    for v in votes:
        if v[0] == "p1":
            offices_seen.add(v[1])
    assert len(offices_seen) == 5


# ========== FV-16: clear 后重投 ==========

def test_fv16_clear_and_revote(vote_state):
    """FV-16: 清理后新批次可以正常提交；old signatures 不幂等拦截新批次。"""
    state = vote_state
    entries = _make_v21_entries()
    sig1 = "test_fv16_v21_sig_1"

    # First batch
    result1 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig1)
    assert result1["success"] is True
    assert state.get_vote_completed("p1") is True

    # Clear
    state.clear_population_pending()
    assert not state.get_vote_completed("p1")
    assert len(state.get_population_votes()) == 0

    # New batch with same entries (FC-08: old signatures don't block after clear)
    result2 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), sig1)
    assert result2["success"] is True
    assert result2["data"]["vote_count"] == 5
    assert state.get_vote_completed("p1") is True


# ========== FV-17: office="" 回归测试 ==========

def test_fv17_office_not_empty_string(vote_state):
    """FV-17: vote records 的 office 字段必须为真实公职名，不得为 ""。
    使用 check_and_commit_vote 直调测试核心事务层 office 写入。"""
    state = vote_state
    entry_tuples = [
        ("consul", 1),
        ("censor", 0),
        ("praetor", 0),
        ("quaestor", 0),
        ("tribune", 0),
    ]
    sig = "test_fv17_v21_sig"

    result = check_and_commit_vote(state, "p1", entry_tuples, sig)
    assert result["success"] is True

    votes = state.get_population_votes()
    p1_votes = [v for v in votes if v[0] == "p1"]
    offices = {v[1] for v in p1_votes}

    # No empty-string office
    assert "" not in offices, "BUG: office='' found in vote records (v1.1 regression)"
    # All offices are valid
    for office in offices:
        assert office in {"consul", "censor", "praetor", "quaestor", "tribune"}, f"Invalid office: {office!r}"


# ========== FV-18: ABSTAIN 不影响其他 office ==========

def test_fv18_abstain_does_not_affect_other_offices(vote_state):
    """FV-18: 玩家对 consul 弃权，不影响 praetor 等 office 的正常投票。
    使用 check_and_commit_vote 直调绕过 API 候选人校验。"""
    state = vote_state
    entry_tuples = [
        ("consul", 0),        # ABSTAIN
        ("censor", 0),         # ABSTAIN
        ("praetor", 1),        # FOR fig1
        ("quaestor", 2),        # FOR fig2
        ("tribune", 3),         # FOR fig3
    ]

    result = check_and_commit_vote(state, "p1", entry_tuples, "test_fv18_v21_sig")
    assert result["success"] is True

    votes = state.get_population_votes()
    p1_votes = {v[1]: v[2] for v in votes if v[0] == "p1"}

    # ABSTAIN offices have figure_id=0
    assert p1_votes["consul"] == 0
    assert p1_votes["censor"] == 0
    # Voted offices have real figure_ids
    assert p1_votes["praetor"] == 1
    assert p1_votes["quaestor"] == 2
    assert p1_votes["tribune"] == 3

    # Completion set correctly
    assert state.get_vote_completed("p1") is True
    assert state.get_vote_completed("p2") is False


# ========== FV-19: 空 batch 拒绝 [NEW v2.1] ==========

def test_fv19_empty_batch_rejected(vote_state):
    """FV-19: batch_vote([]) → structured failure, zero write (FC-01)."""
    state = vote_state
    result = batch_vote(state, "p1", [], bypass_permission=True)
    assert result["success"] is False
    errors = result.get("errors", [])
    assert len(errors) >= 1
    assert any("INVALID_BATCH" in e.get("code", "") or "5 entries" in e.get("message", "")
               for e in errors)
    # Zero write
    assert not state.get_vote_completed("p1")
    assert len(state.get_population_votes()) == 0


# ========== FV-20: 部分 office batch 拒绝 [NEW v2.1] ==========

def test_fv20_partial_batch_rejected(vote_state):
    """FV-20: 缺失 office → structured failure, zero write (FC-01)."""
    state = vote_state
    entries = [
        {"office": "consul", "figure_id": 1},
        {"office": "tribune", "figure_id": 3},
        # Missing: censor, praetor, quaestor
    ]

    result = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result["success"] is False
    errors = result.get("errors", [])
    assert len(errors) >= 1
    # FC-01: partial batch must fail with INVALID_BATCH
    assert any("missing" in e.get("message", "").lower() or "INVALID_BATCH" in e.get("code", "")
               for e in errors)
    # Zero write
    assert not state.get_vote_completed("p1")
    assert len(state.get_population_votes()) == 0


# ========== FV-21: 重复 office 拒绝 [NEW v2.1] ==========

def test_fv21_duplicate_office_rejected(vote_state):
    """FV-21: 同批重复 office → DUPLICATE_OFFICE structured failure, zero write (FC-04)."""
    state = vote_state
    entries = [
        {"office": "consul", "figure_id": 1},
        {"office": "consul", "figure_id": 2},  # duplicate
        {"office": "censor", "figure_id": 3},
        {"office": "praetor", "figure_id": 4},
        {"office": "quaestor", "figure_id": 5},
        {"office": "tribune", "figure_id": 0},
    ]

    result = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result["success"] is False
    errors = result.get("errors", [])
    assert len(errors) >= 1
    assert any("DUPLICATE_OFFICE" in e.get("code", "") for e in errors)
    # Zero write
    assert not state.get_vote_completed("p1")
    assert len(state.get_population_votes()) == 0


# ========================================================================
# G5 R1→R2 TESTS — FC-07 同线程重入(生产路径) / FC-06 frozenset / FC-09 全玩家 / FV-15 加权
# ============================================================================================

# ========== FV-08a: 同线程重入 [G5-R1] ==========

def test_fv08a_same_thread_reentry_busy(vote_state):
    """FV-08a G5-R1→R2: 同线程重入 → BATCH_BUSY, retryable=true, zero write (FC-07).

    使用 threading.Lock（非可重入）验证同线程第二次获取 guard 返回 BUSY。
    与 FV-08（双线程并发）分开，独立测试同线程重入场景。
    """
    state = vote_state
    entries = _make_v21_entries()

    # Acquire guard manually to simulate active transaction
    acquired = state.try_acquire_batch_guard("test_reentry")
    assert acquired is True

    # Same-thread reentry: should return BUSY (Lock is not reentrant)
    acquired2 = state.try_acquire_batch_guard("test_reentry_again")
    assert acquired2 is False, "FC-07: same-thread reentry must return BUSY (Lock non-reentrant)"

    # Release original guard
    state.release_batch_guard()

    # After release, can acquire again
    acquired3 = state.try_acquire_batch_guard("test_after_release")
    assert acquired3 is True
    state.release_batch_guard()


def test_fv08b_same_thread_reentry_via_check_and_commit(vote_state):
    """FV-08b G5-R1→R2: 同线程通过 check_and_commit_vote 重入 → BATCH_BUSY。

    模拟：一个事务正在持有 guard，同线程再次调用 check_and_commit_vote → BUSY。
    """
    state = vote_state
    entries = _make_v21_entries()

    # Acquire guard to simulate another transaction in progress (same thread)
    assert state.try_acquire_batch_guard("simulated_txn") is True

    # Same-thread call to check_and_commit_vote should get BUSY
    result = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), ("p1", ()))
    assert result["success"] is False
    errors = result.get("errors", [])
    assert any(e.get("code") == "BATCH_BUSY" for e in errors), \
        f"Expected BATCH_BUSY, got {errors}"
    assert result["data"].get("retryable") is True

    # Zero write: no votes, no completion, no marker
    assert not state.get_vote_completed("p1")
    assert len(state.get_population_votes()) == 0

    # Release simulated transaction
    state.release_batch_guard()

    # Now it should work
    result2 = check_and_commit_vote(state, "p1",
        _make_v21_entry_tuples(entries), ("p1", frozenset(_make_v21_entry_tuples(entries))))
    assert result2["success"] is True


# ========== FC-06 Signature Tests [G5-R1→R2: frozenset] ==========

def test_fv06a_same_signature_idempotent_tuple(vote_state):
    """FC-06 G5-R2: 同 signature (player_id, frozenset(...)) → 幂等。

    使用 batch_vote API（生成 tuple signature）验证重复调用幂等。
    """
    state = vote_state
    entries = [
        {"office": "consul", "figure_id": 0},
        {"office": "censor", "figure_id": 0},
        {"office": "praetor", "figure_id": 0},
        {"office": "quaestor", "figure_id": 0},
        {"office": "tribune", "figure_id": 0},
    ]

    # First call — writes
    result1 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result1["success"] is True
    assert result1["data"]["vote_count"] == 5

    # Second call — idempotent (same player, same entries)
    result2 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result2["success"] is True
    assert result2["data"].get("already_committed") is True
    assert result2["data"]["vote_count"] == 0


def test_fv06b_different_signature_already_committed_player(vote_state):
    """FC-06 G5-R2: 异签名（不同 frozenset）但 player 已 committed → 拒绝 + 零写。

    第二批至少一个 office 使用不同 figure_id，形成真正不同的 frozenset。
    已提交玩家再次提交异签名 → record_population_vote reject → rollback, zero write。
    """
    state = vote_state
    # Batch 1: all ABSTAIN
    entries1 = [("consul", 0), ("censor", 0), ("praetor", 0),
                ("quaestor", 0), ("tribune", 0)]
    # Batch 2: truly different — tribune figure_id=1 (different from batch 1's 0)
    entries2 = [("consul", 0), ("censor", 0), ("praetor", 0),
                ("quaestor", 0), ("tribune", 1)]

    sig1 = ("p1", frozenset(entries1))
    sig2 = ("p1", frozenset(entries2))

    # Verify signatures are truly different
    assert sig1 != sig2, "FV-06b G5-R2: signatures must be different"

    # First submission — success (all ABSTAIN)
    result1 = check_and_commit_vote(state, "p1", entries1, sig1)
    assert result1["success"] is True
    assert result1["data"]["vote_count"] == 5
    votes_after_1 = len(state.get_population_votes())
    assert state.get_vote_completed("p1") is True

    # Second submission with DIFFERENT signature → record_population_vote rejects
    # (player already voted for tribune with different figure_id, replace=False)
    result2 = check_and_commit_vote(state, "p1", entries2, sig2)
    # Should be rejected — different signature, player already committed
    assert result2["success"] is False, \
        f"FV-06b G5-R2: different signature must be rejected, got {result2}"
    errors = result2.get("errors", [])
    # Must not be BATCH_BUSY (that's FC-07 reentrant, not FC-06 idempotency)
    assert not any(e.get("code") == "BATCH_BUSY" for e in errors), \
        f"FV-06b G5-R2: should be rejected by duplicate vote guard, not BUSY"
    # Zero write: no additional votes
    assert len(state.get_population_votes()) == votes_after_1, \
        f"FV-06b: zero write on different signature; votes grew from {votes_after_1} to {len(state.get_population_votes())}"


def test_fv06c_signature_serialization_roundtrip(vote_state):
    """FC-06 G5-R2: 签名持久化（frozenset）→ 存档恢复后幂等检查仍然有效。"""
    state = vote_state
    entries = [{"office": o, "figure_id": 0} for o in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]

    # Submit via batch_vote (generates frozenset signature)
    result1 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result1["success"] is True

    # Serialize and restore
    data = state.to_dict()
    restored = GameState.create_for_testing(state.config.to_dict() if hasattr(state.config, 'to_dict') else {})
    restored.load_from_dict(data)

    # Same entries after restore should be idempotent
    result2 = batch_vote(restored, "p1", entries, bypass_permission=True)
    assert result2["success"] is True
    assert result2["data"].get("already_committed") is True
    assert result2["data"]["vote_count"] == 0

    # Different player can still vote
    result3 = batch_vote(restored, "p2", entries, bypass_permission=True)
    assert result3["success"] is True
    assert result3["data"]["vote_count"] == 5


# ========== FV-14 REWRITE [G5-R1→R2]: actually call resolve_population_slice ==========

def test_fv14_resolve_population_slice_incomplete_blocked(vote_state):
    """FV-14 G5-R1→R2: 未全完成时 resolve_population_slice() → structured failure (FC-09).

    实际调用 session_api.resolve_population_slice()，
    断言：只有一个玩家完成时拒绝结算。
    """
    from src.api import session_api
    state = vote_state
    entries = [{"office": o, "figure_id": 0} for o in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]

    # Only p1 votes
    result = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result["success"] is True

    # p2 has NOT voted → resolve should be blocked
    resolve_result = session_api.resolve_population_slice(state)
    assert resolve_result["success"] is False
    errors = resolve_result.get("errors", [])
    assert any(e.get("code") == "VOTE_NOT_ALL_COMPLETE" for e in errors), \
        f"Expected VOTE_NOT_ALL_COMPLETE, got {errors}"


def test_fv14b_resolve_population_slice_all_completed(vote_state):
    """FV-14b G5-R1→R2: 全完成时 resolve_population_slice() → 成功，只结算一次。

    实际调用 session_api.resolve_population_slice()，
    断言：两玩家都完成投票后结算成功。
    """
    from src.api import session_api
    state = vote_state
    entries = [{"office": o, "figure_id": 0} for o in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]

    # Both players vote
    result1 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result1["success"] is True
    result2 = batch_vote(state, "p2", entries, bypass_permission=True)
    assert result2["success"] is True

    # Resolve should succeed
    resolve_result = session_api.resolve_population_slice(state)
    assert resolve_result["success"] is True
    data = resolve_result.get("data", {})
    assert "election_results" in data

    # Phase result recorded (but phase not executed)
    assert state.is_phase_executed("population") is False


# ========== FV-15 REWRITE [G5-R2]: weighted votes in results ==========

def test_fv15_weighted_votes_in_results(vote_state):
    """FV-15 ATTEMPT-2 R2 (ASSERTION-REAL): 加权票真实断言 — 确定性 fixture + 禁止跨派系 fallback。

    两玩家使用 fixture 中真实候选人（非零 figure_id），各自派系 influence 严格不同。
    ATTEMPT-2 R2 修复：
    ① fixture 显式固定 influence（f1=120/fig, f2=100/fig → f1 恒为 dominant）
    ② 禁止跨派系 fallback：p1 只投 f1 候选人，p2 只投 f2 候选人
       （某 office 缺某派候选人 → 该玩家 ABSTAIN，不投另一派候选人）
    断言 f1_influence != f2_influence（不可用"均非零"替代）；
    读取 election_results 并核对 winner 的 faction 与 vote power 权重一致
    （更高 influence 的派系候选人应赢得至少一个 office）。
    """
    from src.api import session_api, population_api
    state = vote_state

    # Get actual candidates from the fixture
    cand_result = population_api.get_candidates(state)
    candidates_by_office = cand_result.get("data", {}) if cand_result.get("success") else {}

    # Map each office to available candidates sorted by faction
    office_candidates = {}
    for office, cands in candidates_by_office.items():
        if cands:
            office_candidates[office] = [(c["id"], c.get("faction_id", "")) for c in cands]

    if not office_candidates:
        pytest.fail("FV-15 ATTEMPT-3: fixture failure — no candidates available (AR-2: no skip)")

    # ATTEMPT-2 R2: 确定性 fixture + 禁止跨派系 fallback。
    # p1 只投 f1 候选人，p2 只投 f2 候选人。
    # 某 office 缺某派候选人 → 该玩家 ABSTAIN（figure_id=0），不 fallback 到投另一派。
    # 保证两派在至少一个 office 都有候选人（否则 skip——无法验证加权投票方向）。
    entries_p1 = []
    entries_p2 = []
    offices_both = []
    for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
        cands = office_candidates.get(office, [])
        f1_cands = [(fid, fid_str) for fid, fid_str in cands if fid_str == "f1"]
        f2_cands = [(fid, fid_str) for fid, fid_str in cands if fid_str == "f2"]
        if f1_cands and f2_cands:
            offices_both.append(office)
        # p1 → f1; p2 → f2; 缺失侧 ABSTAIN（禁止跨派系 fallback）
        entries_p1.append((office, f1_cands[0][0] if f1_cands else 0))
        entries_p2.append((office, f2_cands[0][0] if f2_cands else 0))

    if not offices_both:
        pytest.fail(
            "FV-15 ATTEMPT-3: fixture failure — no dual-faction office (AR-2: no skip)"
        )

    # Verify at least one non-zero figure_id per player (exclude all-abstain degenerate case)
    assert any(fid != 0 for _, fid in entries_p1), \
        "FV-15 ATTEMPT-2 R2: p1 must have at least one non-ABSTAIN vote"
    assert any(fid != 0 for _, fid in entries_p2), \
        "FV-15 ATTEMPT-2 R2: p2 must have at least one non-ABSTAIN vote"

    # Get pre-resolve faction influences (assert strictly different)
    f1_influence_pre = 0
    f2_influence_pre = 0
    for m in state.get_living_members():
        if m.faction_id == "f1":
            f1_influence_pre += getattr(m, 'influence', 0)
        elif m.faction_id == "f2":
            f2_influence_pre += getattr(m, 'influence', 0)
    assert f1_influence_pre > 0, "FV-15 ATTEMPT-2 R2: faction f1 must have non-zero influence"
    assert f2_influence_pre > 0, "FV-15 ATTEMPT-2 R2: faction f2 must have non-zero influence"

    # FV-15 ATTEMPT-2 R2 (ASSERTION-REAL): 两派 influence 严格不同（不可降为"均非零"）
    # 确定性 fixture 保证 f1=600 f2=500 恒成立
    assert f1_influence_pre != f2_influence_pre, \
        f"FV-15 ATTEMPT-2 R2: faction influences must be distinguishable (f1={f1_influence_pre}, f2={f2_influence_pre})"

    # Determine which faction has more vote power
    dominant_faction = "f1" if f1_influence_pre > f2_influence_pre else "f2"
    dominant_influence = f1_influence_pre if dominant_faction == "f1" else f2_influence_pre
    weaker_influence = f2_influence_pre if dominant_faction == "f1" else f1_influence_pre

    # p1 and p2 vote with real candidates
    result1 = check_and_commit_vote(state, "p1", entries_p1,
        ("p1", frozenset(entries_p1)))
    assert result1["success"] is True
    result2 = check_and_commit_vote(state, "p2", entries_p2,
        ("p2", frozenset(entries_p2)))
    assert result2["success"] is True

    votes = state.get_population_votes()
    assert len(votes) == 10
    non_abstain = [v for v in votes if v[2] != 0]
    assert len(non_abstain) > 0, \
        "FV-15 ATTEMPT-2 R2: must have non-ABSTAIN votes for weighted counting"

    # FV-15 CLOSEOUT (RO-1 裁决1 Path A): 直接调用 resolve_election() + 显式断言 success
    resolve_election_result = population_api.resolve_election(state)
    assert resolve_election_result["success"] is True, \
        f"FV-15 ATTEMPT-3: resolve_election() must succeed, got {resolve_election_result.get('errors')}"

    # CI-3: from resolve_election() direct return, not wrapper data wrapper
    raw_data = resolve_election_result.get("data", {})
    election_results = raw_data.get("election_results", [])

    # Wrapper resolve for settlement completion (phase result recording)
    resolve_result = session_api.resolve_population_slice(state)
    assert resolve_result["success"] is True, \
        f"FV-15 ATTEMPT-2 R2: resolve must succeed, got {resolve_result.get('errors')}"

    # ATTEMPT-3 (A-02/A-03): per-candidate score from DTO — production path, not test-recomputed
    # AR-2: no conditional bypass — assertion must execute unconditionally
    assert len(election_results) > 0, \
        "FV-15 ATTEMPT-3: election_results must be non-empty (AR-2: no conditional bypass)"

    # CI-3: read per-candidate scores from DTO, verify against expected faction influence
    verified_office_count = 0
    for er in election_results:
        office = er.get("office")
        candidates = er.get("candidates", [])
        winner_score = er.get("score")
        winner_id = er.get("figure_id")

        if not candidates:
            continue

        # Validate each candidate's score field
        candidate_scores = {}
        for c in candidates:
            fid = c["figure_id"]
            s = c["score"]
            assert isinstance(s, int) and s > 0, \
                f"FV-15 ATTEMPT-3: {office} candidate {fid} invalid score={s} (type={type(s).__name__})"
            candidate_scores[fid] = s

        # winner.score == max(scores) — direct max assertion (not directional)
        max_score = max(candidate_scores.values())
        assert winner_score == max_score, \
            f"FV-15 ATTEMPT-3: {office} winner {winner_id} score={winner_score} != max_score={max_score}"
        assert winner_id in [fid for fid, s in candidate_scores.items() if s == max_score], \
            f"FV-15 ATTEMPT-3: {office} winner {winner_id} not among tied max-score candidates"

        # Dual-faction office: per-candidate score == expected faction influence
        faction_ids_present = set(c["faction_id"] for c in candidates)
        if len(faction_ids_present) >= 2:
            verified_office_count += 1
            for c in candidates:
                expected = f1_influence_pre if c["faction_id"] == "f1" else f2_influence_pre
                assert c["score"] == expected, (
                    f"FV-15 ATTEMPT-3: {office} candidate {c['figure_id']} "
                    f"(f={c['faction_id']}) score={c['score']} != expected_influence={expected}")

    # VM-2: fixture must yield at least one verifiable dual-faction office
    assert verified_office_count >= 1, \
        f"FV-15 ATTEMPT-3: no dual-faction office verified (got {verified_office_count}; VM-2 fixture check)"

    # Phase result must be recorded after successful resolve
    phase_result = state.get_phase_result("population")
    assert phase_result is not None, \
        "FV-15 ATTEMPT-2 R2: phase_result must be recorded after resolve"


# ========== FV-15b: 并列（Tie）场景 [CLOSEOUT SA裁决2] ==========

def _make_tie_state():
    """Build a tie state: f1_influence == f2_influence == 100, fixed random.seed(42)."""
    import random
    random.seed(42)  # 确定性随机（tie 时 random.choice）
    config = {
        "testing": {"bypass_player_check": True, "auto_population": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "faction_initial_treasury": 100,
            "faction_member_limit": 6,
        },
        "political_rules": {
            "min_festival_age": 30,
            "office_cooldowns": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
            "offices_per_election": {"consul": 1, "censor": 1, "praetor": 1, "quaestor": 1, "tribune": 1},
            "min_ages": {"consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30},
            "office_rank": {"dictator": 6, "censor": 4, "consul": 5, "praetor": 3, "tribune": 1, "quaestor": 2},
            "office_influence_bonus": {"dictator": 60, "censor": 50, "consul": 40, "praetor": 30, "tribune": 20, "quaestor": 10},
            "ex_office_influence_bonus": {"ex-dictator": 30, "ex-censor": 25, "ex-consul": 20, "ex-praetor": 15, "ex-tribune": 10, "ex-quaestor": 5},
            "family_prestige": {"Julius": 4, "Cornelius": 4, "Claudius": 3, "Fabius": 3, "Aemilius": 2, "Servilius": 2},
            "candidates_per_election": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    # 玩家
    p1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(p1)
    p2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.HUMAN)
    state.add_player(p2)
    # 派系
    f1 = Faction(id="f1", name="Optimates", treasury=1000)
    state.add_faction(f1)
    f2 = Faction(id="f2", name="Populares", treasury=1000)
    state.add_faction(f2)
    # f1 figures: influence=100, 资格属性确保入选
    for i in range(1, 6):
        fig = Figure.create_nobile(i, "f1", 40 + i)
        fig.wealth = 100
        fig.popularity = 10
        fig.martial = 10 if i == 1 else 5
        fig.charisma = 10 if i == 1 else 5
        fig.intelligence = 10 if i == 1 else 5
        fig.zeal = 10 if i == 1 else 5
        fig.update_influence()
        fig.influence = 100  # VM-2: fixed equal influence
        state.add_member(fig)
    # f2 figures: influence=100 (exactly equal to f1)
    for i in range(6, 11):
        fig = Figure.create_nobile(i, "f2", 40 + i)
        fig.wealth = 80
        fig.popularity = 8
        fig.martial = 9 if i == 6 else 5
        fig.charisma = 9 if i == 6 else 5
        fig.intelligence = 9 if i == 6 else 5
        fig.zeal = 9 if i == 6 else 5
        fig.update_influence()
        fig.influence = 100  # VM-2: fixed equal influence (tie condition)
        state.add_member(fig)
    state.set_current_player("p1")
    return state


@pytest.fixture
def tie_vote_state():
    """FV-15b 并列 fixture: f1_influence == f2_influence == 100, fixed random.seed."""
    return _make_tie_state()


def test_fv15b_tie_score_equal(tie_vote_state):
    """FV-15b CLOSEOUT (裁决2): 并列 (tie) 场景 — f1_influence == f2_influence == 100.

    4 项通过标准（SA 澄清函 §裁决2）:
    ① score_p1 == score_p2（严格相等）
    ② winner_id 为候选人之一（不要求特定 winner）
    ③ winner_score == max_score 仍成立（max = tie 值）
    ④ 可复现（固定 random.seed(42)，两次运行赢家一致）
    """
    import random as _random_mod
    from src.api import session_api, population_api
    state = tie_vote_state

    # Get candidates
    cand_result = population_api.get_candidates(state)
    candidates_by_office = cand_result.get("data", {}) if cand_result.get("success") else {}
    assert candidates_by_office, "FV-15b: fixture must have candidates (AR-2: no skip)"

    # Build votes: p1→f1, p2→f2 (same pattern as FV-15 main)
    entries_p1 = []
    entries_p2 = []
    for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
        cands = candidates_by_office.get(office, [])
        f1_cands = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f1"]
        f2_cands = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f2"]
        entries_p1.append((office, f1_cands[0][0] if f1_cands else 0))
        entries_p2.append((office, f2_cands[0][0] if f2_cands else 0))

    result1 = check_and_commit_vote(state, "p1", entries_p1, ("p1", frozenset(entries_p1)))
    assert result1["success"] is True
    result2 = check_and_commit_vote(state, "p2", entries_p2, ("p2", frozenset(entries_p2)))
    assert result2["success"] is True

    # Direct resolve_election (裁决1 Path A pattern)
    resolve_election_result = population_api.resolve_election(state)
    assert resolve_election_result["success"] is True, \
        f"FV-15b: resolve_election() must succeed, got {resolve_election_result.get('errors')}"
    raw_data = resolve_election_result.get("data", {})
    election_results = raw_data.get("election_results", [])
    assert len(election_results) > 0, "FV-15b: election_results must be non-empty (AR-2)"

    # ① For dual-faction offices: score_p1 == score_p2 (strict equality)
    tie_verified = 0
    for er in election_results:
        candidates = er.get("candidates", [])
        if len(candidates) < 2:
            continue
        faction_ids = set(c["faction_id"] for c in candidates)
        if len(faction_ids) < 2:
            continue
        tie_verified += 1
        scores = {c["faction_id"]: c["score"] for c in candidates}
        f1_score = scores.get("f1", 0)
        f2_score = scores.get("f2", 0)
        # ①: scores equal (both 100 influence, 1 vote each)
        assert f1_score == f2_score, \
            f"FV-15b ①: tie scores must be equal, got f1={f1_score} f2={f2_score}"
        # ③: winner_score == max_score
        winner_score = er.get("score")
        max_score = max(scores.values())
        assert winner_score == max_score, \
            f"FV-15b ③: winner_score={winner_score} != max_score={max_score}"
        # ②: winner_id is one of the candidates
        winner_id = er.get("figure_id")
        candidate_ids = [c["figure_id"] for c in candidates]
        assert winner_id in candidate_ids, \
            f"FV-15b ②: winner {winner_id} not in candidates {candidate_ids}"
    assert tie_verified >= 1, "FV-15b: no dual-faction office with tie (VM-2 fixture check)"

    # ④ 可复现: create a fresh state with same seed, re-vote, re-resolve
    _random_mod.seed(42)
    # Build a fresh state using the same pattern as tie_vote_state fixture
    state2 = _make_tie_state()
    # Re-get candidates on fresh state
    cand_result2 = population_api.get_candidates(state2)
    candidates2 = cand_result2.get("data", {}) if cand_result2.get("success") else {}
    entries_p1_2 = []
    entries_p2_2 = []
    for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
        cands = candidates2.get(office, [])
        f1_c = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f1"]
        f2_c = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f2"]
        entries_p1_2.append((office, f1_c[0][0] if f1_c else 0))
        entries_p2_2.append((office, f2_c[0][0] if f2_c else 0))
    r1 = check_and_commit_vote(state2, "p1", entries_p1_2, ("p1", frozenset(entries_p1_2)))
    assert r1["success"]
    r2 = check_and_commit_vote(state2, "p2", entries_p2_2, ("p2", frozenset(entries_p2_2)))
    assert r2["success"]
    rerun_result = population_api.resolve_election(state2)
    assert rerun_result["success"] is True
    rerun_data = rerun_result.get("data", {})
    rerun_election_results = rerun_data.get("election_results", [])
    # ④: same result cardinality and winners across two runs (deterministic tie-breaking)
    assert len(rerun_election_results) == len(election_results), \
        ("FV-15b ④: rerun election_results length differs: "
         f"r1={len(election_results)} r2={len(rerun_election_results)}")
    rerun_by_office = {er["office"]: er for er in rerun_election_results}
    assert set(rerun_by_office) == {er["office"] for er in election_results}, \
        "FV-15b ④: rerun office keys differ from the first run"
    for er in election_results:
        rerun_er = rerun_by_office[er["office"]]
        assert er["figure_id"] == rerun_er["figure_id"], \
            f"FV-15b ④: {er['office']} winner not reproducible: r1={er['figure_id']} r2={rerun_er['figure_id']}"

    # Complete settlement
    wrap_result = session_api.resolve_population_slice(state)
    assert wrap_result["success"] is True
    phase_result = state.get_phase_result("population")
    assert phase_result is not None, "FV-15b: phase_result must be recorded"


# ========== FV-15c: 资格过滤（Qualification Filter）[CLOSEOUT SA裁决2] ==========

@pytest.fixture
def filter_vote_state():
    """FV-15c 资格过滤 fixture: figure age=25 (低于所有 office min_age) + 合法候选人."""
    config = {
        "testing": {"bypass_player_check": True, "auto_population": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "faction_initial_treasury": 100,
            "faction_member_limit": 6,
        },
        "political_rules": {
            "min_festival_age": 30,
            "office_cooldowns": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
            "offices_per_election": {"consul": 1, "censor": 1, "praetor": 1, "quaestor": 1, "tribune": 1},
            "min_ages": {"consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30},
            "office_rank": {"dictator": 6, "censor": 4, "consul": 5, "praetor": 3, "tribune": 1, "quaestor": 2},
            "office_influence_bonus": {"dictator": 60, "censor": 50, "consul": 40, "praetor": 30, "tribune": 20, "quaestor": 10},
            "ex_office_influence_bonus": {"ex-dictator": 30, "ex-censor": 25, "ex-consul": 20, "ex-praetor": 15, "ex-tribune": 10, "ex-quaestor": 5},
            "family_prestige": {"Julius": 4, "Cornelius": 4, "Claudius": 3, "Fabius": 3, "Aemilius": 2, "Servilius": 2},
            "candidates_per_election": {"consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    p1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(p1)
    p2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.HUMAN)
    state.add_player(p2)
    f1 = Faction(id="f1", name="Optimates", treasury=1000)
    state.add_faction(f1)
    f2 = Faction(id="f2", name="Populares", treasury=1000)
    state.add_faction(f2)
    # f1: 1 ineligible (age=25) + 4 eligible (age=40)
    fig_young = Figure.create_nobile(1, "f1", 25)  # age=25: below all min_ages
    fig_young.wealth = 100
    fig_young.popularity = 10
    fig_young.influence = 120
    state.add_member(fig_young)
    for i in range(2, 6):
        fig = Figure.create_nobile(i, "f1", 40 + i)
        fig.wealth = 100
        fig.popularity = 10
        fig.martial = 10 if i == 2 else 5
        fig.charisma = 10 if i == 2 else 5
        fig.intelligence = 10 if i == 2 else 5
        fig.zeal = 10 if i == 2 else 5
        fig.update_influence()
        fig.influence = 120
        state.add_member(fig)
    # f2: 5 eligible figures
    for i in range(6, 11):
        fig = Figure.create_nobile(i, "f2", 40 + i)
        fig.wealth = 80
        fig.popularity = 8
        fig.martial = 9 if i == 6 else 5
        fig.charisma = 9 if i == 6 else 5
        fig.intelligence = 9 if i == 6 else 5
        fig.zeal = 9 if i == 6 else 5
        fig.update_influence()
        fig.influence = 100
        state.add_member(fig)
    state.set_current_player("p1")
    return state


def test_fv15c_qualification_filter(filter_vote_state):
    """FV-15c CLOSEOUT (裁决2): 资格过滤 — figure age=25 被所有 office 过滤.

    3 项通过标准（SA 澄清函 §裁决2）:
    ① 被过滤候选不在 election_results[office]["candidates"] 中
    ② 该候选人不在 winner 判定中被考虑
    ③ 剩余合法候选人的 score 正确（= 各派 influence × 得票数）
    """
    from src.api import session_api, population_api
    state = filter_vote_state

    # The age=25 figure's id
    filtered_figure_id = 1  # figure with age=25 (create_nobile(1, "f1", 25))

    # Confirm the figure exists and has age 25
    filtered_fig = state.get_member(filtered_figure_id)
    assert filtered_fig is not None, "FV-15c: filtered figure must exist"
    assert filtered_fig.age == 25, f"FV-15c: filtered figure age must be 25, got {filtered_fig.age}"

    # Verify age=25 is below all office min_ages (30 quaestor/tribune minimum)
    min_ages = state.config.get("political_rules", {}).get("min_ages", {})
    for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
        min_age = min_ages.get(office, 30)
        assert filtered_fig.age < min_age, \
            f"FV-15c: figure age {filtered_fig.age} not below {office} min_age={min_age}"

    # ① Verify filtered figure is NOT in get_candidates result
    cand_result = population_api.get_candidates(state)
    candidates_by_office = cand_result.get("data", {}) if cand_result.get("success") else {}
    all_candidate_ids = set()
    for office, cands in candidates_by_office.items():
        for c in cands:
            all_candidate_ids.add(c["id"])
    assert filtered_figure_id not in all_candidate_ids, \
        f"FV-15c ①: filtered figure {filtered_figure_id} should NOT appear in get_candidates"

    # Build votes: p1→f1, p2→f2
    entries_p1 = []
    entries_p2 = []
    for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
        cands = candidates_by_office.get(office, [])
        f1_cands = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f1"]
        f2_cands = [(c["id"], c.get("faction_id", "")) for c in cands if c.get("faction_id") == "f2"]
        entries_p1.append((office, f1_cands[0][0] if f1_cands else 0))
        entries_p2.append((office, f2_cands[0][0] if f2_cands else 0))

    result1 = check_and_commit_vote(state, "p1", entries_p1, ("p1", frozenset(entries_p1)))
    assert result1["success"] is True
    result2 = check_and_commit_vote(state, "p2", entries_p2, ("p2", frozenset(entries_p2)))
    assert result2["success"] is True

    # Direct resolve_election
    resolve_election_result = population_api.resolve_election(state)
    assert resolve_election_result["success"] is True, \
        f"FV-15c: resolve_election() must succeed, got {resolve_election_result.get('errors')}"
    raw_data = resolve_election_result.get("data", {})
    election_results = raw_data.get("election_results", [])
    assert len(election_results) > 0, "FV-15c: election_results must be non-empty (AR-2)"

    # ① Verify filtered figure NOT in election_results candidates
    for er in election_results:
        office = er.get("office")
        candidates = er.get("candidates", [])
        candidate_ids = [c["figure_id"] for c in candidates]
        assert filtered_figure_id not in candidate_ids, \
            f"FV-15c ①: filtered figure {filtered_figure_id} found in {office} candidates"

    # ② Filtered figure not in winner — check all winners
    all_winner_ids = [er["figure_id"] for er in election_results]
    assert filtered_figure_id not in all_winner_ids, \
        f"FV-15c ②: filtered figure {filtered_figure_id} should NOT be a winner"

    # ③ Remaining eligible candidates have correct scores (CI-3: from production path)
    # faction_influence = sum of all living members' influence in that faction
    f1_total_influence = 600  # 5 figures × 120
    f2_total_influence = 500  # 5 figures × 100
    verified_count = 0
    for er in election_results:
        candidates = er.get("candidates", [])
        if len(candidates) < 2:
            continue
        faction_ids = set(c["faction_id"] for c in candidates)
        if len(faction_ids) < 2:
            continue
        verified_count += 1
        for c in candidates:
            expected = f2_total_influence if c["faction_id"] == "f2" else f1_total_influence
            assert c["score"] == expected, (
                f"FV-15c ③: {er['office']} cand {c['figure_id']} "
                f"(f={c['faction_id']}) score={c['score']} != expected={expected}")
    assert verified_count >= 1, "FV-15c: no dual-faction office to verify scores (VM-2 fixture check)"

    # Filtered figure must not hold any office after election
    assert getattr(filtered_fig, "office", None) is None, \
        f"FV-15c ②: filtered figure should hold no office, got {filtered_fig.office}"

    # Complete settlement
    wrap_result = session_api.resolve_population_slice(state)
    assert wrap_result["success"] is True
    phase_result = state.get_phase_result("population")
    assert phase_result is not None, "FV-15c: phase_result must be recorded"


# ========== FC-07 Production Path Reentrant Tests [ATTEMPT-2 四路径补全] ==========

def test_fv08b_init_path_reentry_busy():
    """FC-07 ATTEMPT-2 (CI-2): 正常 GameState() __init__ 构造路径 → Lock 非可重入。

    使用标准 GameState() 构造函数（不走 reset/load/factory），
    在任何显式 reset/load/factory 操作前验证：
    ① 首次 try_acquire_batch_guard 成功；
    ② 同线程二次 acquire 返回 BUSY（False — Lock 非 RLock）；
    ③ release 后可再次 acquire 成功。
    此为 CI-2 要求的四路径之一（__init__ 正常构造路径），
    由 GameState.__init__ 末尾调用 self.reset() 正确设置 Lock。
    """
    from src.core.game_state import GameState

    # Normal constructor — __init__ → self.reset() → Lock set
    state = GameState()

    # ① First acquire must succeed
    assert state.try_acquire_batch_guard("test_init") is True, \
        "FC-07 ATTEMPT-2: __init__ path guard must be acquirable on first attempt"

    # ② Same-thread reentry → BUSY (Lock not RLock)
    assert state.try_acquire_batch_guard("test_init_reentry") is False, \
        "FC-07 ATTEMPT-2: __init__ path same-thread reentry must return BUSY"

    state.release_batch_guard()

    # ③ After release, can re-acquire
    assert state.try_acquire_batch_guard("test_init_after") is True, \
        "FC-07 ATTEMPT-2: __init__ path guard must be re-acquirable after release"
    state.release_batch_guard()

def test_fv08d_factory_constructor_path_reentry_busy():
    """FC-07 ATTEMPT-2 (CI-2): create_for_testing() 工厂路径 → Lock 非可重入。

    使用 GameState.create_for_testing() 工厂方法（绕过 __init__，
    直接通过 cls.__new__(cls) 创建）。验证同线程第二次 acquire 返回 BUSY。
    此为 CI-2 要求的四路径之一的独立覆盖（create_for_testing 工厂路径）。
    ⚠️ 此路径不是正常 __init__ 构造路径——工厂使用 __new__ 绕过 __init__。
    """
    from src.core.game_state import GameState
    # Minimal test config for create_for_testing
    test_config = {
        "game_config": {"log_level": "INFO"},
        "economic_rules": {"initial_national_public_land": 1000},
    }
    state = GameState.create_for_testing(test_config)
    assert state is not None, \
        "FC-07 G5-R2: create_for_testing() must return valid GameState"
    # First acquire — must succeed
    assert state.try_acquire_batch_guard("test_constructor") is True, \
        "FC-07 G5-R2: constructor path guard must be acquirable"
    # Same-thread reentry → BUSY (Lock not RLock)
    assert state.try_acquire_batch_guard("test_constructor_reentry") is False, \
        "FC-07 G5-R2: constructor path same-thread reentry must return BUSY"
    state.release_batch_guard()
    # After release, can re-acquire
    assert state.try_acquire_batch_guard("test_constructor_after") is True
    state.release_batch_guard()


def test_fv08e_reset_path_reentry_busy(vote_state):
    """FC-07 ATTEMPT-2 (CI-2): reset() 恢复路径 → Lock 非可重入。

    使用 vote_state fixture 调用 reset() 验证生产 reset 路径 guard。
    此为 CI-2 要求的四路径之一的独立覆盖（reset 路径）。
    """
    state = vote_state
    state.reset()
    assert state.try_acquire_batch_guard("test_reset") is True, \
        "FC-07 G5-R2: post-reset guard must be acquirable"
    # Same-thread reentry → BUSY (Lock not RLock)
    assert state.try_acquire_batch_guard("test_reset_reentry") is False, \
        "FC-07 G5-R2: post-reset same-thread reentry must return BUSY"
    state.release_batch_guard()
    # After release, can re-acquire
    assert state.try_acquire_batch_guard("test_reset_after") is True
    state.release_batch_guard()


def test_fv08f_load_path_reentry_busy(vote_state):
    """FC-07 ATTEMPT-2 (CI-2): load_from_dict() 加载路径 → Lock 非可重入。

    序列化 → load_from_dict → 验证 guard 为 Lock。
    此为 CI-2 要求的四路径之一的独立覆盖（load_from_dict 路径）。
    """
    state = vote_state
    data = state.to_dict()
    restored = GameState()
    restored.load_from_dict(data)
    assert restored.try_acquire_batch_guard("test_load") is True
    assert restored.try_acquire_batch_guard("test_load_reentry") is False, \
        "FC-07 G5-R2: post-load same-thread reentry must return BUSY"
    restored.release_batch_guard()
    assert restored.try_acquire_batch_guard("test_load_after") is True
    restored.release_batch_guard()


# ========== FC-09 All-Player + One-Time Protection Tests [NEW G5-R2] ==========

def test_fv09_ai_incomplete_blocked_resolve(vote_state):
    """FC-09 G5-R2 (VERIFY-MATCH): AI 未完成时 resolve_population_slice() 返回结构化 failure。

    构造场景：p1/p2 人类玩家完成投票，ai1 AI 玩家未投票。
    调用 session_api.resolve_population_slice(state) → 断言返回 failure，
    错误码 VOTE_NOT_ALL_COMPLETE，incomplete_players 含 ai1，phase 未 executed。
    直接调用被测入口，非仅检查 marker。
    """
    from src.core.entities.player import PlayerType, Player
    from src.api import session_api
    state = vote_state

    # Add an AI player
    ai_player = Player(player_id="ai1", faction_id="f1", player_type=PlayerType.AI)
    state.add_player(ai_player)

    # Human players complete voting
    entries = [{"office": o, "figure_id": 0} for o in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]
    result1 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result1["success"] is True
    result2 = batch_vote(state, "p2", entries, bypass_permission=True)
    assert result2["success"] is True

    # AI has NOT voted — verify vote_completed is False
    assert state.get_vote_completed("ai1") is False, \
        "FC-09 G5-R2: AI player must not be vote_completed"

    # Verify human players are completed
    assert state.get_vote_completed("p1") is True
    assert state.get_vote_completed("p2") is True

    # FC-09 G5-R2 (VERIFY-MATCH): 实际调用 resolve_population_slice()
    resolve_result = session_api.resolve_population_slice(state)
    assert resolve_result["success"] is False, \
        "FC-09 G5-R2: resolve must fail when AI player is incomplete"
    errors = resolve_result.get("errors", [])
    assert len(errors) > 0, "FC-09 G5-R2: must have error entries"
    assert any(e.get("code") == "VOTE_NOT_ALL_COMPLETE" for e in errors), \
        f"FC-09 G5-R2: expected VOTE_NOT_ALL_COMPLETE, got {errors}"
    incomplete = resolve_result.get("data", {}).get("incomplete_players", [])
    assert "ai1" in incomplete, \
        f"FC-09 G5-R2: ai1 must be in incomplete_players, got {incomplete}"
    # Phase must NOT be executed after blocked resolve
    assert state.is_phase_executed("population") is False, \
        "FC-09 G5-R2: phase must not be executed after blocked resolve"


def test_fv14c_second_resolve_no_double_settle(vote_state):
    """FC-09 G5-R2 (CI-1 + VERIFY-MATCH): 全局一次性结算 — 二次 resolve 幂等返回。

    所有玩家完成投票 → 第一次 resolve_population_slice() 正常结算。
    第二次 resolve_population_slice() → 幂等返回（once guard 生效），
    不重复调用 resolve_election()，phase result 不重复写入。
    """
    from src.api import session_api
    state = vote_state
    entries = [{"office": o, "figure_id": 0} for o in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]

    result1 = batch_vote(state, "p1", entries, bypass_permission=True)
    assert result1["success"] is True
    result2 = batch_vote(state, "p2", entries, bypass_permission=True)
    assert result2["success"] is True

    votes_before = len(state.get_population_votes())
    assert votes_before == 10, f"Expected 10 votes, got {votes_before}"

    # First resolve — must succeed
    resolve1 = session_api.resolve_population_slice(state)
    assert resolve1["success"] is True, \
        f"FC-09 G5-R2: first resolve must succeed, got errors={resolve1.get('errors')}"
    data1 = resolve1.get("data", {})
    assert "election_results" in data1, \
        "FC-09 G5-R2: first resolve must include election_results"

    # Phase result must be recorded after first resolve (not necessarily phase_executed)
    phase_result = state.get_phase_result("population")
    assert phase_result is not None, \
        "FC-09 G5-R2: phase result must be recorded after first resolve"

    # Vote records unchanged after resolve (records are preserved, not cleared)
    votes_after_first = len(state.get_population_votes())
    assert votes_after_first == votes_before, \
        f"FC-09 G5-R2: vote records preserved after first resolve " \
        f"({votes_before} before, {votes_after_first} after)"

    # Second resolve — must be idempotent (once guard returns cached result)
    resolve2 = session_api.resolve_population_slice(state)
    assert resolve2["success"] is True, \
        f"FC-09 G5-R2: second resolve must be idempotent, got errors={resolve2.get('errors')}"
    data2 = resolve2.get("data", {})
    # Both resolves should return consistent election_results
    assert "election_results" in data2, \
        "FC-09 G5-R2: second resolve must include election_results"

    # Vote records must still be unchanged after second resolve
    votes_after_second = len(state.get_population_votes())
    assert votes_after_second == votes_before, \
        f"FC-09 G5-R2: vote records unchanged after second resolve " \
        f"({votes_before} before, {votes_after_second} after)"

    # Verify message indicates already resolved (exact phrase from once guard)
    message2 = resolve2.get("message", "")
    assert "Population phase already resolved" in message2, \
        f"FC-09 G5-R2: second resolve must return idempotent message, got '{message2}'"


# ========================================================================
# WP-02b v3.0 — Session selection-map normalization and orchestration seam
# ========================================================================


def test_v3_submit_population_votes_partial_map_normalizes_fixed_five(vote_state):
    from src.api import session_api

    state = vote_state
    state.set_turn_order(["p1", "p2"])
    captured = []

    def capture_batch(_state, player_id, entries):
        captured.extend(entries)
        return {
            "success": True,
            "message": "captured",
            "data": {"vote_count": 5},
            "errors": [],
        }

    with patch.object(session_api.population_api, "batch_vote", side_effect=capture_batch), \
            patch.object(session_api, "complete_population_player", return_value={
                "success": True,
                "message": "handoff",
                "data": {"new_player_id": "p2"},
                "errors": [],
            }):
        result = session_api.submit_population_votes(
            state,
            "p1",
            {"consul": 1, "praetor": 3},
        )

    assert result["success"] is True
    assert len(captured) == 5
    offices = [entry["office"] for entry in captured]
    assert len(offices) == 5
    assert offices == ["consul", "censor", "praetor", "quaestor", "tribune"]
    assert len(set(offices)) == 5
    assert {entry["office"] for entry in captured} == {
        "consul", "censor", "praetor", "quaestor", "tribune"
    }
    by_office = {entry["office"]: entry["figure_id"] for entry in captured}
    assert len(by_office) == 5
    assert by_office["consul"] == 1
    assert by_office["praetor"] == 3
    assert [figure_id for figure_id in by_office.values() if figure_id == 0] == [0, 0, 0]


def test_v3_submit_population_votes_empty_map_all_abstain_and_complete(vote_state):
    from src.api import session_api

    state = vote_state
    players = state.get_all_players()
    assert len(players) == 2
    assert [player.player_id for player in players] == ["p1", "p2"]
    assert all(player.player_type == PlayerType.HUMAN for player in players)
    state.set_turn_order(["p1", "p2"])

    result = session_api.submit_population_votes(state, "p1", {})

    assert result["success"] is True
    assert result["data"]["status"] == "awaiting_players"
    votes = [vote for vote in state.get_population_votes() if vote[0] == "p1"]
    assert len(votes) == 5
    assert len({vote[1] for vote in votes}) == 5
    assert {vote[1] for vote in votes} == {
        "consul", "censor", "praetor", "quaestor", "tribune"
    }
    assert all(vote[2] == 0 for vote in votes)
    assert state.get_vote_completed("p1") is True
    assert state.get_current_player().player_id == "p2"


@pytest.mark.parametrize("selection", [
    {"consul": 0},
    {"consul": None},
    {"consul": True},
    {"consul": -1},
    {"dictator": 1},
])
def test_v3_submit_population_votes_rejects_explicit_zero_null_bool_negative_unknown_office(
    vote_state,
    selection,
):
    from src.api import session_api

    state = vote_state
    state.set_turn_order(["p1", "p2"])
    players = state.get_all_players()
    assert len(players) == 2
    assert state.get_current_player().player_id == "p1"

    result = session_api.submit_population_votes(state, "p1", selection)

    assert result["success"] is False
    errors = result.get("errors", [])
    assert len(errors) >= 1
    assert errors[0]["code"] == "INVALID_SELECTION_MAP"
    assert len(state.get_population_votes()) == 0
    assert state.get_vote_completed("p1") is False
    assert state.get_vote_completed("p2") is False
    assert state.get_current_player().player_id == "p1"


def test_v3_submit_population_votes_batch_failure_no_handoff_no_resolve(vote_state):
    from src.api import session_api

    state = vote_state
    state.set_turn_order(["p1", "p2"])
    backend_failure = {
        "success": False,
        "message": "backend rejected",
        "data": {"vote_count": 0},
        "errors": [{"code": "INVALID_BATCH", "message": "rejected"}],
    }
    with patch.object(session_api.population_api, "batch_vote", return_value=backend_failure), \
            patch.object(session_api, "complete_population_player") as complete_spy, \
            patch.object(session_api, "resolve_population_slice") as resolve_spy:
        result = session_api.submit_population_votes(state, "p1", {})

    assert result == backend_failure
    assert complete_spy.call_count == 0
    assert resolve_spy.call_count == 0
    assert len(state.get_population_votes()) == 0
    assert state.get_current_player().player_id == "p1"


def test_v3_submit_population_votes_multi_human_handoff(vote_state):
    from src.api import session_api

    state = vote_state
    players = state.get_all_players()
    assert len(players) == 2
    assert [player.player_type for player in players] == [PlayerType.HUMAN, PlayerType.HUMAN]
    state.set_turn_order(["p1", "p2"])

    with patch.object(session_api, "resolve_population_slice", wraps=session_api.resolve_population_slice) as resolve_spy:
        result = session_api.submit_population_votes(state, "p1", {})

    assert result["success"] is True
    data = result["data"]
    assert data["status"] == "awaiting_players"
    assert data["awaiting_player_id"] == "p2"
    assert data["resolved"] is False
    assert state.get_current_player().player_id == "p2"
    assert state.get_phase_result("population") is None
    assert resolve_spy.call_count == 0

