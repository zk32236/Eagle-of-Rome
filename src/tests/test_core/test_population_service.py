"""
Core-level 单元测试 - population_service.check_and_commit()

FI 矩阵（对照 SA-Development-Task.md §9）:

| ID   | 场景                     | 必须断言                                               |
|:----:|:-------------------------|:------------------------------------------------------|
| FI-01 | 第一个人物更新异常        | 所有人物、campaign、signature、completion 恢复前态；guard 释放 |
| FI-02 | 第二条 campaign 记录异常  | 同 FI-01                                              |
| FI-03 | signature 写入异常        | 完整回滚；重试只扣款一次                                 |
| FI-04 | completion 写入异常        | 完整回滚；其他玩家 completion 不变                      |
| FI-05 | snapshot 读取异常         | 返回 failure；guard 释放；后续批次成功                   |
| FI-06 | rollback 自身异常         | 返回可诊断 failure；guard 仍释放                        |
| FI-07 | 同 signature 重复         | 第一次写入，第二次幂等 success/零写                      |
| FI-08 | 不同 signature 并发       | 一个 ACQUIRED；另一个 BATCH_BUSY，不得 success/零写      |
| FI-09 | 两玩家隔离                | p1 成功不推进 p2；p2 失败不回退 p1                      |
| FI-10 | 存档/恢复                 | active guard 不持久化；恢复后新批次可提交                |
| FI-11 | 非法容器 DTO              | (在 test_population_api.py 中)                         |
| FI-12 | clear 后重提              | 清理后新批次可以正常提交                                 |
"""
import threading

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.service.population_service import apply_batch_campaign, check_and_commit


# ========== Fixtures ==========

@pytest.fixture
def service_state():
    """基础状态供 population_service 测试用。"""
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
        },
    }
    state = GameState.create_for_testing(config)
    state._batch_commit_in_progress = False
    state.turn = GameTurn(turn_number=1, year=-282)

    # 玩家
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(player1)
    # 派系
    faction1 = Faction(id="f1", name="Faction1", treasury=1000)
    state.add_faction(faction1)

    # 人物
    fig1 = Figure.create_nobile(1, "f1", 45)
    fig1.wealth = 100
    fig1.popularity = 10
    fig1.update_influence()
    state.add_member(fig1)

    fig2 = Figure.create_nobile(2, "f1", 50)
    fig2.wealth = 60
    fig2.popularity = 12
    fig2.update_influence()
    state.add_member(fig2)

    fig3 = Figure.create_eques(3, "f1", 35)
    fig3.wealth = 40
    fig3.popularity = 5
    fig3.update_influence()
    state.add_member(fig3)

    # 另一个派系的人物（不在 f1）
    fig4 = Figure.create_plebeian(4, "f2", 30)
    fig4.wealth = 20
    fig4.popularity = 3
    fig4.update_influence()
    state.add_member(fig4)

    return state


# ========== Helper ==========

def _make_entries(state, fig_ids_and_amounts):
    """从 (figure_id, amount) 列表生成 validated_entries。"""
    entries = []
    for fid, amt in fig_ids_and_amounts:
        fig = state.get_member(fid)
        if fig:
            entries.append((fid, amt, fig))
    return entries


# ========== Happy Path (非 FI 编号) ==========

class TestHappyPath:
    """正常完整路径 — 非故障注入，用于验证基本功能。"""

    def test_single_entry(self, service_state):
        entries = _make_entries(service_state, [(1, 10)])
        sig = "test_sig_01"

        result = apply_batch_campaign(service_state, "p1", entries, sig, 0)

        assert result["total_spent"] == 10
        assert result["total_popularity_gain"] == 10
        assert result["campaign_count"] == 1
        assert len(result["figure_results"]) == 1

        fig = service_state.get_member(1)
        assert fig.wealth == 90  # 100 - 10
        assert fig.popularity == 20  # 10 + 10

        assert service_state.get_batch_completed("p1") is True
        assert service_state.has_committed_batch(sig) is True

    def test_multiple_entries(self, service_state):
        entries = _make_entries(service_state, [(1, 10), (2, 20), (3, 5)])
        sig = "test_sig_multi"

        result = apply_batch_campaign(service_state, "p1", entries, sig, 0)

        assert result["total_spent"] == 35
        assert result["total_popularity_gain"] == 35
        assert result["campaign_count"] == 3

        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)
        fig3 = service_state.get_member(3)
        assert fig1.wealth == 90
        assert fig2.wealth == 40
        assert fig3.wealth == 35
        assert fig1.popularity == 20
        assert fig2.popularity == 32
        assert fig3.popularity == 10

    def test_figure_results_contain_details(self, service_state):
        entries = _make_entries(service_state, [(1, 10)])
        sig = "test_sig_details"

        result = apply_batch_campaign(service_state, "p1", entries, sig, 0)
        fr = result["figure_results"][0]
        assert fr["figure_id"] == 1
        assert fr["amount"] == 10
        assert fr["previous_wealth"] == 100
        assert fr["new_wealth"] == 90

    def test_campaigns_recorded(self, service_state):
        entries = _make_entries(service_state, [(1, 10), (2, 20)])
        sig = "test_sig_campaigns"

        apply_batch_campaign(service_state, "p1", entries, sig, 0)

        campaigns = service_state.get_population_campaigns()
        assert ("p1", 1, 10) in campaigns
        assert ("p1", 2, 20) in campaigns

    def test_batch_completed_after_success(self, service_state):
        entries = _make_entries(service_state, [(1, 10)])
        apply_batch_campaign(service_state, "p1", entries, "sig_bc_01", 0)
        assert service_state.get_batch_completed("p1") is True

    def test_mutex_released_after_success(self, service_state):
        """成功提交后互斥锁应被释放。"""
        entries = _make_entries(service_state, [(1, 10)])
        sig = "sig_mutex_02"

        apply_batch_campaign(service_state, "p1", entries, sig, 0)
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

    def test_mutex_allows_sequential_different_batches(self, service_state):
        """同一玩家的两次不同签名依次通过。"""
        entries1 = _make_entries(service_state, [(1, 10)])
        entries2 = _make_entries(service_state, [(2, 20)])

        r1 = apply_batch_campaign(service_state, "p1", entries1, "seq_sig_1", 0)
        assert r1["campaign_count"] == 1

        r2 = apply_batch_campaign(service_state, "p1", entries2, "seq_sig_2", 1)
        assert r2["campaign_count"] == 1

        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)
        assert fig1.wealth == 90  # 100 - 10
        assert fig2.wealth == 40  # 60 - 20


# ========== FI-01: 第一个人物更新异常 ==========

class TestFI01_FirstFigureUpdateError:
    """
    FI-01: 第一个人物更新异常
    断言: 所有人物、campaign、signature、completion 恢复前态；guard 释放
    """

    def test_rollback_exception_before_marker(self, service_state):
        """
        在写入过程中模拟异常（通过 patch 破坏 update_influence 使之抛出异常），
        验证回滚后字段完全恢复。
        """
        fig1 = service_state.get_member(1)
        old_wealth = fig1.wealth
        old_popularity = fig1.popularity
        old_influence = fig1.influence

        entries = _make_entries(service_state, [(1, 10)])

        # 在 wealth 减法后、popularity 加法前模拟异常
        with patch.object(fig1, 'update_influence', side_effect=ValueError("mock error")):
            with pytest.raises(RuntimeError, match="mock error"):
                apply_batch_campaign(service_state, "p1", entries, "sig_rollback", 0)

        # 验证回滚
        assert fig1.wealth == old_wealth, f"Expected {old_wealth}, got {fig1.wealth}"
        assert fig1.popularity == old_popularity, f"Expected {old_popularity}, got {fig1.popularity}"
        assert fig1.influence == old_influence
        assert service_state.get_batch_completed("p1") is False
        assert service_state.has_committed_batch("sig_rollback") is False
        assert len(service_state.get_population_campaigns()) == 0

    def test_rollback_clears_batch_lock(self, service_state):
        """回滚后 _batch_commit_in_progress 应被释放。"""
        entries = _make_entries(service_state, [(1, 10)])

        with patch.object(fig1 := service_state.get_member(1), 'update_influence',
                          side_effect=ValueError("fail")):
            with pytest.raises(RuntimeError):
                apply_batch_campaign(service_state, "p1", entries, "sig_lock_clear", 0)

        # guard 已释放
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

    def test_batch_completed_false_after_rollback(self, service_state):
        """回滚后 batch_completed 应恢复前态 (False)。"""
        entries = _make_entries(service_state, [(1, 10)])
        fig = service_state.get_member(1)
        with patch.object(fig, 'update_influence', side_effect=Exception("fail")):
            with pytest.raises(Exception):
                apply_batch_campaign(service_state, "p1", entries, "sig_bc_02", 0)
        assert service_state.get_batch_completed("p1") is False

    def test_mutex_released_after_rollback(self, service_state):
        """回滚后互斥锁应被释放。"""
        entries = _make_entries(service_state, [(1, 10)])
        fig = service_state.get_member(1)
        with patch.object(fig, 'update_influence', side_effect=Exception("x")):
            with pytest.raises(Exception):
                apply_batch_campaign(service_state, "p1", entries, "sig_mutex_03", 0)
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()


# ========== FI-02: 第二条 campaign 记录异常 ==========

class TestFI02_SecondCampaignRecordError:
    """
    FI-02: 第二条 campaign 记录异常
    断言: 同 FI-01 — 所有人物、campaign、signature、completion 恢复前态
    """

    def test_rollback_restores_influence(self, service_state):
        """
        回滚后影响力也应恢复到原始值。
        update_influence 被调用后导致的临时变化应该回滚。
        """
        fig1 = service_state.get_member(1)
        old_influence = fig1.influence

        entries = _make_entries(service_state, [(1, 10)])

        # 在 record_population_campaign 处模拟异常（在影响力和财富写入之后）
        original_record = service_state.record_population_campaign
        call_count = [0]

        def _mock_record(player_id, figure_id, amount):
            call_count[0] += 1
            if call_count[0] > 0:
                raise RuntimeError("mock record failure")
            original_record(player_id, figure_id, amount)

        with patch.object(service_state, 'record_population_campaign', _mock_record):
            with pytest.raises(RuntimeError, match="mock record failure"):
                apply_batch_campaign(service_state, "p1", entries, "sig_influence_rollback", 0)

        assert fig1.wealth == 100  # rolled back
        assert fig1.popularity == 10  # rolled back
        assert fig1.influence == old_influence

    def test_partial_write_and_full_rollback(self, service_state):
        """即使部分写入已发生（第二个 figure 失败），回滚也能完全撤销。"""
        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)
        old_pop_1 = fig1.popularity
        old_pop_2 = fig2.popularity

        entries = _make_entries(service_state, [(1, 10), (2, 20)])

        # 在第二个 figure 的 update_influence 处失败
        original_update = fig2.update_influence
        update_count = [0]

        def _mock_update():
            update_count[0] += 1
            if update_count[0] == 1:
                raise RuntimeError("mock fail on fig2")
            return original_update()

        with patch.object(fig2, 'update_influence', _mock_update):
            with pytest.raises(RuntimeError):
                apply_batch_campaign(service_state, "p1", entries, "sig_partial", 0)

        # fig1 应被回滚
        assert fig1.popularity == old_pop_1
        assert fig2.popularity == old_pop_2
        assert fig1.wealth == 100
        assert fig2.wealth == 60


# ========== FI-03: signature 写入异常 ==========

class TestFI03_SignatureWriteError:
    """
    FI-03: signature 写入异常
    断言: 完整回滚；重试只扣款一次
    """

    def test_rollback_restores_all_fields(self, service_state):
        """多个条目的所有字段在 signature 写入异常后完整回滚。"""
        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)

        snap1 = {"wealth": fig1.wealth, "popularity": fig1.popularity, "influence": fig1.influence}
        snap2 = {"wealth": fig2.wealth, "popularity": fig2.popularity, "influence": fig2.influence}

        entries = _make_entries(service_state, [(1, 10), (2, 20)])

        # 在 record_committed_batch 之前模拟异常（signature 写入异常）
        with patch.object(service_state, 'record_committed_batch',
                          side_effect=RuntimeError("mock marker fail")):
            with pytest.raises(RuntimeError):
                apply_batch_campaign(service_state, "p1", entries, "sig_snap_01", 0)

        # 验证所有字段回滚
        assert fig1.wealth == snap1["wealth"]
        assert fig1.popularity == snap1["popularity"]
        assert fig1.influence == snap1["influence"]
        assert fig2.wealth == snap2["wealth"]
        assert fig2.popularity == snap2["popularity"]
        assert fig2.influence == snap2["influence"]
        assert len(service_state.get_population_campaigns()) == 0

    def test_retry_only_deducts_once(self, service_state):
        """signature 写入失败后重试，财富只扣一次。"""
        fig1 = service_state.get_member(1)
        old_wealth = fig1.wealth
        entries = _make_entries(service_state, [(1, 10)])

        # 第一次：signature 写入异常
        with patch.object(service_state, 'record_committed_batch',
                          side_effect=RuntimeError("mock marker fail")):
            with pytest.raises(RuntimeError):
                apply_batch_campaign(service_state, "p1", entries, "sig_retry_01", 0)

        # 回滚后财富不变
        assert fig1.wealth == old_wealth

        # 第二次：正常提交（相同 entries，不同 signature）
        result = check_and_commit(
            service_state, "p1", entries, "sig_retry_02"
        )
        assert result["success"] is True
        assert fig1.wealth == old_wealth - 10


# ========== FI-04: completion 写入异常 ==========

class TestFI04_CompletionWriteError:
    """
    FI-04: completion 写入异常
    断言: 完整回滚；其他玩家 completion 不变
    """

    def test_completion_error_rollback_other_player_unchanged(self, service_state):
        """
        set_batch_completed 失败时回滚所有修改，
        且其他玩家的完成状态不受影响（D-12 隔离）。
        """
        # 先设置 p2 已完成
        service_state.set_batch_completed("p2", True)
        assert service_state.get_batch_completed("p2") is True

        fig1 = service_state.get_member(1)
        old_wealth = fig1.wealth
        entries = _make_entries(service_state, [(1, 10)])

        # 在 set_batch_completed("p1", True) 处模拟异常
        original_set = service_state.set_batch_completed

        def _failing_set(player_id, value):
            if player_id == "p1" and value is True:
                raise RuntimeError("mock completion write failure")
            return original_set(player_id, value)

        with patch.object(service_state, 'set_batch_completed', _failing_set):
            result = check_and_commit(
                service_state, "p1", entries, "sig_fi04_01"
            )

        # 必须返回 failure
        assert result["success"] is False

        # p1 人物回滚
        assert fig1.wealth == old_wealth
        assert service_state.get_batch_completed("p1") is False

        # p2 完成状态不受影响 (D-12)
        assert service_state.get_batch_completed("p2") is True

        # guard 释放
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

        # 无 campaign 写入
        assert len(service_state.get_population_campaigns()) == 0

    def test_completion_error_rollback_campaigns(self, service_state):
        """completion 失败时 campaign 记录也要回滚"""
        service_state.set_batch_completed("p2", True)
        entries = _make_entries(service_state, [(1, 10), (2, 20)])

        def _failing_set(player_id, value):
            if player_id == "p1" and value is True:
                raise RuntimeError("mock completion fail")
            # 正常

        with patch.object(service_state, 'set_batch_completed', _failing_set):
            result = check_and_commit(
                service_state, "p1", entries, "sig_fi04_02"
            )

        assert result["success"] is False
        assert len(service_state.get_population_campaigns()) == 0
        assert service_state.has_committed_batch("sig_fi04_02") is False
        assert service_state.get_batch_completed("p2") is True
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()


# ========== FI-05: snapshot 读取异常 ==========

class TestFI05_SnapshotReadError:
    """
    FI-05: snapshot 读取异常
    断言: 返回 failure；guard 释放；后续批次成功
    """

    def test_snapshot_error_returns_failure_and_releases_guard(self, service_state):
        """snapshot_campaign_figures 异常时返回 structured failure"""
        entries = _make_entries(service_state, [(1, 10)])

        with patch.object(
            service_state, 'snapshot_campaign_figures',
            side_effect=RuntimeError("snapshot read failure")
        ):
            result = check_and_commit(
                service_state, "p1", entries, "sig_fi05_01"
            )

        assert result["success"] is False
        assert len(result["errors"]) >= 1
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

    def test_after_snapshot_error_subsequent_batch_succeeds(self, service_state):
        """snapshot 失败后释放 guard，后续正常批次可以成功"""
        fig1 = service_state.get_member(1)
        old_wealth = fig1.wealth

        entries = _make_entries(service_state, [(1, 10)])

        # 第一次：snapshot 异常
        with patch.object(
            service_state, 'snapshot_campaign_figures',
            side_effect=RuntimeError("snapshot fail")
        ):
            result1 = check_and_commit(
                service_state, "p1", entries, "sig_fi05_fail"
            )
        assert result1["success"] is False
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

        # 第二次：正常提交（guard 已释放、幂等未命中）
        result2 = check_and_commit(
            service_state, "p1", entries, "sig_fi05_success"
        )
        assert result2["success"] is True
        assert service_state.get_member(1).wealth == old_wealth - 10
        assert result2["data"]["campaign_count"] == 1


# ========== FI-05b: getter 故障保护 (AC-05 ATTEMPT-5) ==========

class TestFI05b_GetterFailureProtection:
    """
    FI-05b: getter 故障保护 (AC-05 ATTEMPT-5 修复)
    两个前态 getter 必须对称证明：故障零写、跨线程 guard 释放、恢复后单次重试。
    """

    @pytest.mark.parametrize(
        ("getter_name", "failure_message"),
        [
            ("get_population_campaigns", "campaigns getter exploded"),
            ("get_batch_completed", "completion getter exploded"),
        ],
    )
    def test_getter_failure_is_atomic_releases_guard_and_retries_once(
        self,
        service_state,
        getter_name,
        failure_message,
    ):
        """两个 getter 故障场景均完整保护前态，并允许跨线程获取 guard。"""
        # 非空 campaigns、completion=True、Figure/signature 前态。
        service_state.set_batch_completed("p1", True)
        service_state.record_population_campaign("p1", 1, 5)
        service_state.record_committed_batch("sig_fi05b_legacy")
        campaigns_before = service_state.get_population_campaigns()
        signatures_before = service_state.get_committed_batches()
        completion_before = service_state.get_batch_completed("p1")
        fig1 = service_state.get_member(1)
        figure_before = (fig1.wealth, fig1.popularity, fig1.influence)
        entries = _make_entries(service_state, [(1, 10)])
        failed_signature = f"sig_fi05b_fail_{getter_name}"
        retry_signature = f"sig_fi05b_retry_{getter_name}"

        # 仅本次 getter 调用故障；离开 patch 后恢复真实 getter。
        with patch.object(service_state, getter_name, side_effect=RuntimeError(failure_message)):
            failed_result = check_and_commit(
                service_state, "p1", entries, failed_signature
            )

        assert failed_result["success"] is False
        assert any(
            error.get("code") == "GETTER_FAILURE"
            for error in failed_result.get("errors", [])
        )

        # 故障后逐项与前态完全一致。
        assert service_state.get_population_campaigns() == campaigns_before
        assert service_state.get_batch_completed("p1") is completion_before
        assert (fig1.wealth, fig1.popularity, fig1.influence) == figure_before
        assert service_state.get_committed_batches() == signatures_before
        assert service_state.has_committed_batch(failed_signature) is False

        # RLock 在同线程可重入；必须由真实另一线程证明 guard 已释放。
        guard_result = []

        def acquire_guard_in_other_thread():
            acquired = service_state.try_acquire_batch_guard()
            guard_result.append(acquired)
            if acquired:
                service_state.release_batch_guard()

        guard_thread = threading.Thread(target=acquire_guard_in_other_thread)
        guard_thread.start()
        guard_thread.join(timeout=2)
        assert guard_thread.is_alive() is False
        assert guard_result == [True]

        # getter 已恢复；仅执行一次正常重试。
        retry_result = check_and_commit(
            service_state, "p1", entries, retry_signature
        )
        assert retry_result["success"] is True
        assert retry_result["data"]["campaign_count"] == 1

        # 原有记录不变，且只新增一条 campaign / signature、只扣一次财富。
        campaigns_after_retry = service_state.get_population_campaigns()
        assert campaigns_after_retry == campaigns_before + [("p1", 1, 10)]
        assert fig1.wealth == figure_before[0] - 10
        assert fig1.popularity == figure_before[1] + 10
        assert service_state.get_batch_completed("p1") is True
        assert service_state.get_committed_batches() == signatures_before | {retry_signature}
        assert service_state.has_committed_batch(failed_signature) is False


# ========== FI-06: rollback 自身异常 ==========

class TestFI06_RollbackSelfError:
    """
    FI-06: rollback 自身异常
    断言: 返回可诊断 failure；guard 仍释放
    """

    def test_rollback_self_error_still_releases_guard(self, service_state):
        """rollback 抛出异常时 guard 仍通过 finally 释放"""
        fig1 = service_state.get_member(1)
        entries = _make_entries(service_state, [(1, 10)])

        # 先模拟提交失败（update_influence 抛异常），再模拟回滚也失败。
        with patch.object(service_state, 'restore_campaign_figures',
                          side_effect=RuntimeError("restore failed")):
            with patch.object(fig1, 'update_influence',
                              side_effect=ValueError("commit failed")):
                result = check_and_commit(
                    service_state, "p1", entries, "sig_fi06_01"
                )

        # 返回 failure（提交失败 → 回滚 → 回滚也失败）
        assert result["success"] is False

        # guard 必须释放（finally 保证）
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

        # 应有错误信息
        assert len(result["errors"]) >= 1

    def test_rollback_restore_failure_diagnostic(self, service_state):
        """rollback 失败后仍返回 failure；guard 释放"""
        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)
        entries = _make_entries(service_state, [(1, 10), (2, 20)])

        def _failing_restore(snaps):
            raise RuntimeError("restore exploded")

        with patch.object(
            service_state, 'restore_campaign_figures', _failing_restore
        ):
            with patch.object(fig2, 'update_influence',
                              side_effect=ValueError("commit fail after fig1")):
                result = check_and_commit(
                    service_state, "p1", entries, "sig_fi06_diag"
                )

        assert result["success"] is False
        assert len(result.get("errors", [])) >= 1
        # guard 释放
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()


# ========== FI-07: 同 signature 重复 ==========

class TestFI07_IdempotentRetry:
    """
    FI-07: 同 signature 重复
    断言: 第一次写入，第二次幂等 success/零写
    """

    def test_same_signature_idempotent(self, service_state):
        entries = _make_entries(service_state, [(1, 10)])
        sig = "test_sig_idemp"

        # 第一次：正常写入
        result1 = apply_batch_campaign(service_state, "p1", entries, sig, 0)
        assert result1["campaign_count"] == 1

        # 第二次：幂等命中，返回零写入
        result2 = apply_batch_campaign(service_state, "p1", entries, sig, 0)
        assert result2["campaign_count"] == 0
        assert result2["total_spent"] == 0

        # 财富不变
        fig = service_state.get_member(1)
        assert fig.wealth == 90  # 只扣了一次

    def test_different_signature_ok(self, service_state):
        entries1 = _make_entries(service_state, [(1, 10)])
        entries2 = _make_entries(service_state, [(1, 20)])

        result1 = apply_batch_campaign(service_state, "p1", entries1, "sig_diff_a", 0)
        assert result1["campaign_count"] == 1

        # 不同内容的签名——正常写入
        result2 = apply_batch_campaign(service_state, "p1", entries2, "sig_diff_b", 1)
        assert result2["campaign_count"] == 1
        fig = service_state.get_member(1)
        assert fig.wealth == 70  # 100 - 10 - 20


# ========== FI-08: 不同 signature 并发 ==========

class TestFI08_ConcurrentDifferentSignature:
    """
    FI-08: 不同 signature 并发
    断言: 一个 ACQUIRED；另一个 BATCH_BUSY，不得 success/零写
    """

    def test_mutex_prevents_concurrent_commit(self, service_state):
        """
        当 guard 被另一线程持有 (RLock) 时，
        check_and_commit 应返回 BATCH_BUSY。
        """
        import threading
        import time
        entries = _make_entries(service_state, [(1, 10)])
        sig = "sig_mutex_01"

        got_busy = []
        hold_guard = threading.Event()

        def holder():
            service_state.try_acquire_batch_guard()
            hold_guard.set()
            time.sleep(0.5)
            service_state.release_batch_guard()

        def caller():
            hold_guard.wait(timeout=2)
            r = check_and_commit(
                service_state, "p1", entries, sig
            )
            got_busy.append(r["success"] is False and
                            any(e.get("code") == "BATCH_BUSY"
                                for e in r.get("errors", [])))

        t1 = threading.Thread(target=holder, daemon=True)
        t2 = threading.Thread(target=caller, daemon=True)
        t1.start()
        t2.start()
        t2.join(timeout=3)
        t1.join(timeout=2)

        assert got_busy and got_busy[0] is True
        assert service_state.has_committed_batch(sig) is False
        assert service_state._batch_guard_lock is not None

    def test_concurrent_guard_rejects_second(self, service_state):
        """
        第一个批次持有 guard，第二个批次收到 BATCH_BUSY。
        使用 threading.Thread + 信号量确保时序。
        """
        import threading
        import time

        entries1 = _make_entries(service_state, [(1, 10)])
        entries2 = _make_entries(service_state, [(2, 20)])

        hold_guard = threading.Event()
        can_release = threading.Event()
        results = {}

        def thread1():
            acquired = service_state.try_acquire_batch_guard()
            results["t1_acquired"] = acquired
            hold_guard.set()
            can_release.wait(timeout=3)
            service_state.release_batch_guard()

        def thread2():
            hold_guard.wait(timeout=3)
            acquired = service_state.try_acquire_batch_guard()
            results["t2_acquired"] = acquired

        t1 = threading.Thread(target=thread1, daemon=True)
        t2 = threading.Thread(target=thread2, daemon=True)

        t1.start()
        t2.start()

        t2.join(timeout=5)
        can_release.set()
        t1.join(timeout=2)

        assert results.get("t1_acquired") is True
        assert results.get("t2_acquired") is False

        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

    def test_concurrent_guard_with_check_and_commit(self, service_state):
        """
        使用 threading 模拟一线程持有 guard 另一线程调用 check_and_commit。
        第二个线程应返回 BATCH_BUSY。
        """
        import threading
        import time

        fig1 = service_state.get_member(1)
        fig2 = service_state.get_member(2)
        old_wealth_1 = fig1.wealth
        old_wealth_2 = fig2.wealth

        entries1 = _make_entries(service_state, [(1, 10)])
        entries2 = _make_entries(service_state, [(2, 20)])

        results = {}
        guard_held = threading.Event()

        def holder():
            service_state.try_acquire_batch_guard()
            guard_held.set()
            time.sleep(0.5)
            service_state.release_batch_guard()

        def caller():
            guard_held.wait(timeout=3)
            try:
                r = check_and_commit(
                    service_state, "p1", entries1, "sig_fi08_concurrent"
                )
                results["caller"] = r
            except Exception as e:
                results["caller"] = {"error": str(e)}

        t1 = threading.Thread(target=holder, daemon=True)
        t2 = threading.Thread(target=caller, daemon=True)

        t1.start()
        t2.start()

        t2.join(timeout=5)
        t1.join(timeout=5)

        assert "caller" in results
        r = results["caller"]
        assert r is not None

        # 第二个线程应被拒绝（BATCH_BUSY）
        assert r.get("success") is False, f"Expected BUSY but got success: {r}"
        busy_codes = [
            e.get("code")
            for e in r.get("errors", [])
        ]
        assert "BATCH_BUSY" in busy_codes

        # guard 最终释放
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

        # 无数据写入
        assert service_state.has_committed_batch("sig_fi08_concurrent") is False


# ========== FI-09: 两玩家隔离 ==========

class TestFI09_TwoPlayerIsolation:
    """
    FI-09: 两玩家隔离
    断言: p1 成功不推进 p2；p2 失败不回退 p1
    """

    def test_p1_success_does_not_advance_p2(self, service_state):
        """p1 成功提交后 p2 的 completion 仍为 False"""
        entries = _make_entries(service_state, [(1, 10)])

        result = check_and_commit(
            service_state, "p1", entries, "sig_fi09_p1"
        )
        assert result["success"] is True

        # p1 完成
        assert service_state.get_batch_completed("p1") is True

        # p2 未完成
        assert service_state.get_batch_completed("p2") is False

    def test_p2_failure_does_not_rollback_p1(self, service_state):
        """p2 失败后 p1 的已完成状态不受影响"""
        # 先让 p1 成功
        service_state.set_batch_completed("p1", True)
        assert service_state.get_batch_completed("p1") is True

        # 让 p2 的提交失败（使用 player_id="p2"，patch fig4.update_influence）
        fig4 = service_state.get_member(4)
        entries_p2 = [(4, 10, fig4)]

        with patch.object(fig4, 'update_influence', side_effect=ValueError("p2 fail")):
            result = check_and_commit(
                service_state, "p2", entries_p2, "sig_fi09_p2_fail"
            )

        assert result["success"] is False

        # p1 完成状态不变（D-12 隔离）
        assert service_state.get_batch_completed("p1") is True

    def test_player_completion_independent_markers(self, service_state):
        """两个玩家各自维护独立的 completion 标记"""
        service_state.set_batch_completed("p1", True)
        service_state.set_batch_completed("p2", True)

        assert service_state.get_batch_completed("p1") is True
        assert service_state.get_batch_completed("p2") is True

        # 清空后两个都清空
        service_state.clear_all_batch_completed()
        assert service_state.get_batch_completed("p1") is False
        assert service_state.get_batch_completed("p2") is False


# ========== FI-10: 存档/恢复 ==========

class TestFI10_SaveRestore:
    """
    FI-10: 存档/恢复
    断言: active guard 不持久化；恢复后新批次可提交
    """

    def test_batch_completed_persists_after_roundtrip(self, service_state):
        """成功标记后，to_dict / load_from_dict 序列化保留。"""
        entries = _make_entries(service_state, [(1, 10)])
        apply_batch_campaign(service_state, "p1", entries, "sig_ser_01", 0)
        assert service_state.get_batch_completed("p1") is True

        data = service_state.to_dict()
        assert data.get("_batch_completed_by_player", {}).get("p1") is True

        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(data)
        assert new_state.get_batch_completed("p1") is True
        assert new_state.has_committed_batch("sig_ser_01") is True

    def test_rollback_field_persists_after_roundtrip(self, service_state):
        """回滚后 batch_completed=False 序列化保留。"""
        service_state.set_batch_completed("p1", True)
        service_state.set_batch_completed("p1", False)

        data = service_state.to_dict()
        # p1 不应再标记为完成
        assert data.get("_batch_completed_by_player", {}).get("p1") is not True

        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(data)
        assert new_state.get_batch_completed("p1") is False
        # runtime guard 不序列化，新状态应可获取 guard
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()

    def test_raw_field_in_dict(self, service_state):
        """
        to_dict 应包含 _batch_completed_by_player。
        注意：_batch_commit_in_progress (runtime guard) 不序列化。
        """
        service_state.set_batch_completed("p1", True)

        data = service_state.to_dict()
        assert "_batch_completed_by_player" in data
        assert data["_batch_completed_by_player"].get("p1") is True
        # runtime guard 不序列化，但新加载的实例可正常获取 guard
        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(data)
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()

    def test_guard_not_persisted_in_to_dict(self, service_state):
        """_batch_commit_in_progress 在 to_dict 输出中的值无关紧要，
        但加载后必须 False（因为 RLock 无法序列化）。"""
        service_state._batch_commit_in_progress = True

        data = service_state.to_dict()

        # 加载到新 state
        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(data)

        # guard 必须为 False
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()
        assert new_state._batch_guard_lock is not None
        # 锁必须可用
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()

    def test_guard_unlocked_after_save_load(self, service_state):
        """保存加载后 guard 可被正常获取"""
        # 正常使用
        entries = _make_entries(service_state, [(1, 10)])
        result = check_and_commit(
            service_state, "p1", entries, "sig_fi10_guard"
        )
        assert result["success"] is True

        # 序列化
        data = service_state.to_dict()

        # 新 state 加载
        new_state = GameState.create_for_testing({})
        new_state.load_from_dict(data)

        # guard 可用
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()
        assert new_state.try_acquire_batch_guard() is True
        new_state.release_batch_guard()

        # 可以正常提交新批次
        new_state.add_player(Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN))
        f1 = Faction(id="f1", name="Faction1", treasury=1000)
        new_state.add_faction(f1)
        fig_new = Figure.create_nobile(10, "f1", 40)
        fig_new.wealth = 100
        fig_new.popularity = 10
        fig_new.update_influence()
        new_state.add_member(fig_new)

        entries2 = [(10, 20, fig_new)]
        result2 = check_and_commit(
            new_state, "p1", entries2, "sig_fi10_new_batch"
        )
        assert result2["success"] is True
        assert result2["data"]["campaign_count"] == 1
        assert new_state.get_batch_completed("p1") is True


# ========== FI-12: clear 后重提 ==========

class TestFI12_ClearAndResubmit:
    """
    FI-12: clear 后重提
    断言: 清理后新批次可以正常提交
    """

    def test_clear_pending_resets_batch_completed(self, service_state):
        """clear_population_pending 后 batch_completed 重置且可重新提交。"""
        entries = _make_entries(service_state, [(1, 10)])
        apply_batch_campaign(service_state, "p1", entries, "sig_bc_03", 0)
        assert service_state.get_batch_completed("p1") is True

        service_state.clear_population_pending()
        assert service_state.get_batch_completed("p1") is False
        assert service_state.try_acquire_batch_guard() is True
        service_state.release_batch_guard()

    def test_resubmit_after_clear(self, service_state):
        """clear 后可以正常提交新批次。"""
        entries = _make_entries(service_state, [(1, 10)])
        apply_batch_campaign(service_state, "p1", entries, "sig_clear_01", 0)
        assert service_state.get_batch_completed("p1") is True

        # 清空
        service_state.clear_population_pending()
        assert service_state.get_batch_completed("p1") is False
        assert service_state.has_committed_batch("sig_clear_01") is False

        # 重新提交（相同 entries，新 signature）
        fig1 = service_state.get_member(1)
        fig1.wealth = 100  # reset for test
        fig1.popularity = 10
        fig1.update_influence()

        entries2 = _make_entries(service_state, [(1, 15)])
        result = check_and_commit(
            service_state, "p1", entries2, "sig_clear_02"
        )
        assert result["success"] is True
        assert result["data"]["campaign_count"] == 1
        assert service_state.get_batch_completed("p1") is True
        assert service_state.get_member(1).wealth == 85  # 100 - 15
