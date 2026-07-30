# src/core/service/population_service.py
"""
WP-02a v3 庆典原子提交 — Core 层事务协调。

check_and_commit() 是单入口事务方法，语义：

  1. 幂等检查 —— 相同 batch_signature 已提交 → ALREADY_COMMITTED
  2. 获取运行时 RLock guard —— 失败 → BATCH_BUSY
  3. 快照全部受影响的 Figure 公开字段
  4. 应用 Figure 变更（wealth/popularity）
  5. 写入 campaign 记录
  6. 写入 committed marker
  7. 设置当前玩家 completion

  任一步异常：
    a) 用公开 API 恢复所有 Figure 字段+influence
    b) 还原 campaign 列表、已提交签名集、完成状态
    c) finally 释放 guard
    d) 返回结构化 failure

依赖方向：
  Core service → GameState 公开 API / Figure 公开属性
  绝不写私有字段（._*）
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.game_state import GameState
from src.core.entities.figure import Figure


_logger = logging.getLogger("EOR-POPULATION-CORE")


def check_and_commit(
    state: GameState,
    player_id: str,
    validated_entries: List[Tuple[int, int, 'Figure']],
    batch_signature: str,
) -> Dict[str, Any]:
    """
    Core-level 原子提交入口。

    Args:
        state:              GameState 实例
        player_id:          当前玩家 ID
        validated_entries:  [(figure_id, amount, Figure), ...]
                            已通过 API 层业务校验。
        batch_signature:    API 层生成的 sha256 签名（幂等 key）。

    Returns:
        {
            "success": bool,
            "message": str,
            "data": {
                "total_spent": int,
                "total_popularity_gain": int,
                "figure_results": list[dict],
                "campaign_count": int,
                "batch_signature": str,
                "already_committed": bool,   # 仅幂等返回
                "retryable": bool,           # 仅 BUSY 返回
            } | None,
            "errors": list[dict],
        }

    结构化 failure 语义：
      - success=False, errors[0].code="BATCH_BUSY", data.retryable=True
      - success=False, errors[0].code="SNAPSHOT_FAILURE" 等
      - success=True,  data.already_committed=True  幂等
    """
    state.log_event(
        f"check_and_commit: entries={len(validated_entries)}, sig={batch_signature[:16]}..., "
        f"player_id={player_id}",
        level=logging.DEBUG
    )

    # ── Phase 1: 幂等检查（guard 前） ──
    if state.has_committed_batch(batch_signature):
        _log(state, "ALREADY_COMMITTED: skipping", level=logging.DEBUG)
        return _result(
            success=True,
            message="Already committed",
            data={
                "total_spent": 0,
                "total_popularity_gain": 0,
                "figure_results": [],
                "campaign_count": 0,
                "already_committed": True,
            },
        )

    # ── Phase 2: 获取运行时互斥 guard (RLock, 不持久化) ──
    if not state.try_acquire_batch_guard():
        _log(state, "BATCH_BUSY: guard denied", level=logging.WARNING)
        return _result(
            success=False,
            message="Batch campaign is busy; retry later",
            data={"retryable": True},
            errors=[{
                "code": "BATCH_BUSY",
                "message": "Another batch is in progress",
            }],
        )

    # ── Phase 3~7: 受保护边界 ──
    # 所有初始化和读取操作都在 try 块内，确保任何异常都能触发 finally 释放 guard。
    try:
        # 初始化回滚状态（安全默认值，确保 except 块可安全引用）
        snapshot_data: Optional[Dict[int, Dict[str, int]]] = None
        original_campaigns_len = 0
        original_batch_completed = False
        committed_marker_written = False

        # 读取前态（getter 失败时跳过整个事务，不返回假默认值覆盖真实状态）
        try:
            original_campaigns_len = len(state.get_population_campaigns())
            original_batch_completed = state.get_batch_completed(player_id)
        except Exception as getter_err:
            _log(state, f"GETTER_FAILURE: campaigns/completion getter failed: {getter_err}",
                 level=logging.ERROR)
            return _result(
                success=False,
                message=f"Batch campaign aborted: state getter failure: {getter_err}",
                data={},
                errors=[{
                    "code": "GETTER_FAILURE",
                    "message": str(getter_err),
                }],
            )

        # Phase 3: 快照（只读公开属性）
        snapshot_data = state.snapshot_campaign_figures(validated_entries)
        _log(state, f"snapshot: {len(snapshot_data)} figures", level=logging.DEBUG)

        # Phase 4: 应用变更
        total_spent = 0
        total_popularity_gain = 0
        figure_results = []

        for fid, amount, figure in validated_entries:
            figure.wealth -= amount
            figure.popularity += amount
            figure.update_influence()

            # Phase 5: 写入 campaign 记录
            state.record_population_campaign(player_id, fid, amount)

            total_spent += amount
            total_popularity_gain += amount
            figure_results.append({
                "figure_id": fid,
                "amount": amount,
                "previous_wealth": figure.wealth + amount,
                "new_wealth": figure.wealth,
            })

            state.log_event(
                f"庆典: {figure.name} 花费 {amount}，人气 +{amount}",
                extra={"figure_id": fid, "amount": amount}
            )

        # Phase 6: 写入 committed marker（最后一步——不可失败步骤）
        state.record_committed_batch(batch_signature)
        committed_marker_written = True

        # Phase 7: 设置当前玩家 completion (D-12 隔离)
        state.set_batch_completed(player_id, True)

        campaign_count = len(validated_entries)
        state.log_event(
            f"BATCH_CAMPAIGN_SUCCESS: {campaign_count} entries, "
            f"total_spent={total_spent}, player={player_id}",
            level=logging.DEBUG
        )

        return _result(
            success=True,
            message=f"Batch campaign completed: {campaign_count} entries, "
                    f"{total_spent} spent",
            data={
                "total_spent": total_spent,
                "total_popularity_gain": total_popularity_gain,
                "figure_results": figure_results,
                "campaign_count": campaign_count,
            },
        )

    except Exception as e:
        # ── 回滚 ──
        _log(state, f"ROLLBACK: exception={type(e).__name__}: {e}",
             level=logging.WARNING)

        # Phase 6a: 回滚 Figure 字段（使用公开 API）
        if snapshot_data is not None:
            try:
                state.restore_campaign_figures(snapshot_data)
            except Exception as rollback_err:
                _log(state, f"ROLLBACK_RESTORE_FAILED: {rollback_err}",
                     level=logging.ERROR)

        # Phase 6b: 回滚 campaign 列表（使用公开 API）
        try:
            state.truncate_population_campaigns(original_campaigns_len)
        except Exception as camp_err:
            _log(state, f"ROLLBACK_CAMPAIGNS_FAILED: {camp_err}",
                 level=logging.ERROR)

        # Phase 6c: 回滚 committed_batches（若恰好已写入）
        if committed_marker_written:
            try:
                state.remove_committed_batch(batch_signature)
            except Exception as sig_err:
                _log(state, f"ROLLBACK_SIG_FAILED: {sig_err}",
                     level=logging.ERROR)

        # Phase 6d: 回退 completion 到前态值 (D-12 / AC-03)
        try:
            state.set_batch_completed(player_id, original_batch_completed)
        except Exception as comp_err:
            _log(state, f"ROLLBACK_COMPLETION_FAILED: {comp_err}",
             level=logging.ERROR)

        error_info = {
            "code": type(e).__name__,
            "message": str(e),
        }
        return _result(
            success=False,
            message=f"Batch campaign failed and rolled back: {e}",
            data={},
            errors=[error_info],
        )

    finally:
        # ── 始终释放 guard ──
        state.release_batch_guard()


# ──────────── 旧入口兼容 ────────────

def apply_batch_campaign(
    state: GameState,
    player_id: str,
    validated_entries: List[Tuple[int, int, 'Figure']],
    batch_signature: str,
    original_campaigns_len: int,
) -> dict:
    """
    DEPRECATED — 旧版入口，保留用于测试兼容。
    新代码请直接调用 check_and_commit()。
    """
    result = check_and_commit(state, player_id, validated_entries, batch_signature)
    if result["success"]:
        d = result["data"]
        return {
            "total_spent": d.get("total_spent", 0),
            "total_popularity_gain": d.get("total_popularity_gain", 0),
            "figure_results": d.get("figure_results", []),
            "campaign_count": d.get("campaign_count", 0),
        }
    raise RuntimeError(result.get("message", "Batch campaign failed"))


# ──────────── 内部辅助 ────────────

def _log(state: GameState, msg: str, level: int = logging.DEBUG) -> None:
    """便捷日志辅助。"""
    state.log_event(f"POPULATION_CORE: {msg}", level=level)


def _result(
    success: bool,
    message: str = "",
    data: Optional[Dict] = None,
    errors: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """统一内部返回值格式。"""
    return {
        "success": success,
        "message": message,
        "data": data or {},
        "errors": errors or [],
    }
