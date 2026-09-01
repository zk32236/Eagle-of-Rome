# src/api/population_api.py
"""
人口阶段 API 函数 - 完整实现
"""
import hashlib
import json
import logging
import random
from typing import List, Dict, Any, Optional

from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.service.population_service import check_and_commit


def campaign(
    state: GameState,
    player_id: str,
    figure_id: int,
    amount: int,
    bypass_permission: bool = False
) -> dict:
    """
    DEPRECATED — 单条目庆典赞助。

    ⚠️ 此入口直接操作 Figure 字段，不使用原子事务 guard，
       不提供幂等性、回滚或玩家隔离能力。
       仅保留用于 CLI 手动操作和测试兼容。

    新代码必须使用 batch_campaign() 进行原子批量提交。
    GUI 不得通过此入口提交。
    """
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)

    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    if not bypass:
        if figure.faction_id != player.faction_id:
            return api_response(False, i18n.get("error_figure_not_in_your_faction"))

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    if figure.wealth < amount:
        return api_response(False, i18n.get("error_insufficient_wealth", wealth=figure.wealth))

    # 执行庆典：扣财富，加人气，更新影响力
    figure.wealth -= amount
    figure.popularity += amount
    figure.update_influence()

    state.record_population_campaign(player_id, figure_id, amount)

    message = i18n.get("info_campaign_success", name=figure.get_formal_name(), amount=amount)
    state.log_event(
        f"庆典: {figure.name} 花费 {amount}，人气 +{amount}",
        extra={"figure_id": figure_id, "amount": amount}
    )
    return api_response(True, message, data={"figure_id": figure_id, "amount": amount})


def batch_campaign(
    state: GameState,
    player_id: str,
    entries: List[Dict[str, Any]],
    bypass_permission: bool = False
) -> dict:
    """
    批量庆典赞助——JSON 验证 → DTO 校验 → 业务校验 → Core 原子提交。

    entries: [{"figure_id": int, "amount": int}, ...]

    契约：
    1. JSON 类型验证：entries 必须是 list；拒绝 None/string/dict/int
    2. DTO 类型校验：figure_id/amount 必须是 int，拒绝 bool/float/string；拒绝额外字段
    3. 业务校验：存在、存活、派系、金额正数、财富限制、重复 figure_id
    4. 全部合法 → check_and_commit() 原子事务（guard + snapshot + write + rollback）
    5. BUSY → 结构化 retryable failure (D-11)
    6. 幂等 → ALREADY_COMMITTED success (D-11)
    """
    logger = logging.getLogger("EOR-POPULATION")

    # 入口日志
    state.log_event(
        f"batch_campaign(entries type={type(entries).__name__}, player_id={player_id})",
        level=logging.DEBUG
    )

    # ── 0a. JSON 容器验证（len() / 遍历前） ──
    json_error = _validate_json_container(entries)
    if json_error:
        state.log_event(
            f"BATCH_CAMPAIGN_VALIDATION: JSON container invalid ({json_error[0]['reason']})",
            level=logging.DEBUG
        )
        return api_response(False, "JSON container validation failed", data={
            "failed_entries": json_error,
            "total_spent": 0,
            "total_popularity_gain": 0,
            "figure_results": [],
            "campaign_count": 0,
            "batch_signature": "",
        })

    # 空数组保护（优先于权限检查）
    if not entries:
        state.log_event(
            "batch_campaign: empty entries, returning success with campaign_count=0",
            level=logging.DEBUG
        )
        # WP-03 L5 (P2-02 Option A): 零花费庆典 = 合法 no-op 完成信号。
        # 仅写入 per-player completion 标志；不触碰 check_and_commit 原子提交路径。
        state.set_batch_completed(player_id, True)
        return api_response(True, "No entries to process", data={
            "total_spent": 0,
            "total_popularity_gain": 0,
            "figure_results": [],
            "campaign_count": 0,
            "batch_signature": "",
            "failed_entries": [],
        })

    # ── 0b. DTO 类型校验（JSON 通过后） ──
    dto_errors = _validate_dto_types(entries)
    if dto_errors:
        state.log_event(
            f"BATCH_CAMPAIGN_VALIDATION: DTO type validation failed ({len(dto_errors)} errors)",
            level=logging.DEBUG
        )
        return api_response(False, "DTO type validation failed", data={
            "failed_entries": dto_errors,
            "total_spent": 0,
            "total_popularity_gain": 0,
            "figure_results": [],
            "campaign_count": 0,
            "batch_signature": "",
        })

    # ── 1. 权限检查 ──
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)
    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # ── 计算批次签名（基于规范化后的 entries） ──
    normalized = _normalize_entries(entries)
    sig_input = f"{player_id}:{json.dumps(normalized, sort_keys=True)}"
    batch_signature = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()

    # ── 2. 业务校验 ──
    seen_figure_ids = set()
    failed_entries = []
    validated_entries = []

    for idx, entry in enumerate(entries):
        figure_id = entry.get("figure_id", 0)
        amount = entry.get("amount", 0)

        # 校验：重复 figure_id
        if figure_id in seen_figure_ids:
            failed_entries.append({
                "figure_id": figure_id,
                "amount": amount,
                "index": idx,
                "reason": "duplicate figure_id"
            })
            state.log_event(
                f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} | FAIL duplicate figure_id",
                level=logging.DEBUG
            )
            continue

        seen_figure_ids.add(figure_id)

        # 校验：figure 存在且存活
        figure = state.get_member(figure_id)
        if not figure or figure.is_dead:
            failed_entries.append({
                "figure_id": figure_id,
                "amount": amount,
                "index": idx,
                "reason": "figure not found or dead"
            })
            state.log_event(
                f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} | FAIL figure not found or dead",
                level=logging.DEBUG
            )
            continue

        # 校验：属于当前玩家派系
        if not bypass:
            if figure.faction_id != player.faction_id:
                failed_entries.append({
                    "figure_id": figure_id,
                    "amount": amount,
                    "index": idx,
                    "reason": "figure not in player faction"
                })
                state.log_event(
                    f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} | FAIL figure not in player faction",
                    level=logging.DEBUG
                )
                continue

        # 校验：amount > 0
        if amount <= 0:
            failed_entries.append({
                "figure_id": figure_id,
                "amount": amount,
                "index": idx,
                "reason": "amount must be positive"
            })
            state.log_event(
                f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} | FAIL amount must be positive",
                level=logging.DEBUG
            )
            continue

        # 校验：amount <= figure.wealth
        if figure.wealth < amount:
            failed_entries.append({
                "figure_id": figure_id,
                "amount": amount,
                "index": idx,
                "reason": f"insufficient wealth (wealth={figure.wealth})"
            })
            state.log_event(
                f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} wealth={figure.wealth} | FAIL insufficient wealth",
                level=logging.DEBUG
            )
            continue

        # 校验通过
        validated_entries.append((figure_id, amount, figure))
        state.log_event(
            f"BATCH_CAMPAIGN_VALIDATION: entry[{idx}] figure_id={figure_id} amount={amount} wealth={figure.wealth} | PASS",
            level=logging.DEBUG
        )

    # 总体仲裁日志
    all_passed = len(failed_entries) == 0
    state.log_event(
        f"BATCH_CAMPAIGN_VALIDATION: all_passed={all_passed}, total={len(entries)}, failed={len(failed_entries)}",
        level=logging.DEBUG
    )

    # 任一非法 → 零写入
    if not all_passed:
        state.log_event(
            f"BATCH_CAMPAIGN_SKIP: zero write due to validation failure ({len(failed_entries)} failed entries)",
            level=logging.DEBUG
        )
        return api_response(False, "Validation failed, zero writes", data={
            "failed_entries": failed_entries,
            "total_spent": 0,
            "total_popularity_gain": 0,
            "figure_results": [],
            "campaign_count": 0,
            "batch_signature": batch_signature,
        })

    # ── 3. Core 原子提交 ──
    core_result = check_and_commit(
        state,
        player_id,
        validated_entries,
        batch_signature,
    )

    if not core_result["success"]:
        # BUSY 处理 (D-11)
        errors = core_result.get("errors", [])
        is_busy = any(e.get("code") == "BATCH_BUSY" for e in errors)
        state.log_event(
            f"BATCH_CAMPAIGN_CORE: {'BUSY' if is_busy else 'FAILED'}, "
            f"errors={errors}",
            level=logging.WARNING if is_busy else logging.ERROR
        )
        data = core_result.get("data", {})
        if is_busy:
            # BUSY: 返回结构化 errors（含 code 字段）和 retryable=True (AC-04)
            return api_response(
                False,
                core_result.get("message", "Batch campaign failed"),
                data={
                    "failed_entries": [],
                    "total_spent": 0,
                    "total_popularity_gain": 0,
                    "figure_results": [],
                    "campaign_count": 0,
                    "batch_signature": batch_signature,
                    "retryable": True,
                },
                errors=errors,
            )
        else:
            # 其他失败：保留原有 message 列表
            return api_response(
                False,
                core_result.get("message", "Batch campaign failed"),
                data={
                    "failed_entries": [],
                    "total_spent": 0,
                    "total_popularity_gain": 0,
                    "figure_results": [],
                    "campaign_count": 0,
                    "batch_signature": batch_signature,
                    "retryable": data.get("retryable", False),
                },
                errors=[e["message"] for e in errors if "message" in e],
            )

    # 幂等成功
    core_data = core_result.get("data", {})
    if core_data.get("already_committed"):
        state.log_event(
            f"BATCH_CAMPAIGN_IDEMPOTENT: already committed (sig={batch_signature[:16]}...)",
            level=logging.DEBUG
        )
        return api_response(
            True,
            "Already committed",
            data={
                "total_spent": 0,
                "total_popularity_gain": 0,
                "figure_results": [],
                "campaign_count": 0,
                "batch_signature": batch_signature,
                "failed_entries": [],
                "already_committed": True,
            }
        )

    # 正常成功
    return api_response(
        True,
        core_result.get("message", f"Batch campaign completed"),
        data={
            "total_spent": core_data.get("total_spent", 0),
            "total_popularity_gain": core_data.get("total_popularity_gain", 0),
            "figure_results": core_data.get("figure_results", []),
            "campaign_count": core_data.get("campaign_count", 0),
            "batch_signature": batch_signature,
            "failed_entries": [],
        }
    )


# ────────── WP-02b v2.1: batch_vote ──────────

VALID_OFFICES = frozenset({"consul", "censor", "praetor", "quaestor", "tribune"})

def batch_vote(
    state: GameState,
    player_id: str,
    entries: List[Dict[str, Any]],
    bypass_permission: bool = False
) -> dict:
    """
    WP-02b v2.1 批量投票提交——JSON 验证 → DTO 校验 → 业务校验 → Core 原子提交。

    v2.1 变更（vs v1.1）：
      - Entry DTO: {office: str, figure_id: int}，移除 choice 字段。
      - ABSTAIN: figure_id=0 (FC-03)。
      - Batch 完整性：恰好 5 条 entry，每 office 一条 (FC-01)。
      - 重复 office: structured failure DUPLICATE_OFFICE (FC-04)。
      - 空 batch: structured failure (FC-01)。
      - 部分 batch: structured failure (FC-01)。
      - 不含 resolution（FC-09：由 resolve_population_slice 统一触发）。

    契约：
    1. JSON 类型验证：entries 必须是 list；拒绝 None/string/dict/int
    2. DTO 类型校验：office 必须是 str，figure_id 必须是 int（拒绝 bool/float/string）；
       拒绝 extra fields（如 choice 残留）
    3. 业务校验：office 合法值；批次完整性（FC-01）；同批无重复 office（FC-04）；
       figure_id != 0 时 figure 必须存在/存活/是合法候选人（ABSTAIN figure_id=0 跳过）
    4. 全部合法 → check_and_commit_vote() 原子事务（guard + snapshot + write + rollback）
    5. BUSY → 结构化 retryable failure
    6. 幂等 → ALREADY_COMMITTED success
    """
    logger = logging.getLogger("EOR-POPULATION")

    state.log_event(
        f"batch_vote v2.1(entries type={type(entries).__name__}, player_id={player_id})",
        level=logging.DEBUG
    )

    # ── 0a. JSON 容器验证（len() / 遍历前） ──
    json_error = _validate_vote_json_container(entries)
    if json_error:
        state.log_event(
            f"BATCH_VOTE_VALIDATION: JSON container invalid ({json_error[0]['reason']})",
            level=logging.DEBUG
        )
        return api_response(False, "JSON container validation failed", data={
            "vote_count": 0,
            "failed_entries": json_error,
        }, errors=json_error)

    # ── 0b. 空 batch 拒绝（FC-01: empty → structured failure, zero write） ──
    if not entries:
        state.log_event(
            "batch_vote v2.1: empty entries → structured failure (FC-01)",
            level=logging.DEBUG
        )
        return api_response(False, "Empty batch rejected (FC-01)", data={
            "vote_count": 0,
        }, errors=[{
            "code": "INVALID_BATCH",
            "message": "Batch must contain exactly 5 entries, one per office (FC-01)",
        }])

    # ── 0c. DTO 类型校验 ──
    dto_errors = _validate_vote_dto_types(entries)
    if dto_errors:
        state.log_event(
            f"BATCH_VOTE_VALIDATION: DTO type validation failed ({len(dto_errors)} errors)",
            level=logging.DEBUG
        )
        return api_response(False, "DTO type validation failed", data={
            "vote_count": 0,
            "failed_entries": dto_errors,
        }, errors=dto_errors)

    # ── 1. 权限检查 ──
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)
    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # ── 2. Batch 完整性校验（FC-01: 恰好 5 office，每 office 一条） ──
    offices_in_batch = set()
    validated_entries = []
    batch_errors = []

    for idx, entry in enumerate(entries):
        office = entry.get("office", "")
        figure_id = entry.get("figure_id", 0)

        # FC-01: 非法 office 值
        if office not in VALID_OFFICES:
            batch_errors.append({
                "index": idx,
                "office": office,
                "figure_id": figure_id,
                "reason": f"invalid office '{office}'; must be one of {sorted(VALID_OFFICES)}"
            })
            continue

        # FC-04: 同批重复 office
        if office in offices_in_batch:
            batch_errors.append({
                "index": idx,
                "office": office,
                "figure_id": figure_id,
                "reason": f"duplicate office '{office}'"
            })
            continue

        offices_in_batch.add(office)

        # ABSTAIN (figure_id=0, FC-03): 跳过候选人校验
        if figure_id == 0:
            validated_entries.append((office, figure_id))
            state.log_event(
                f"BATCH_VOTE_VALIDATION: entry[{idx}] office={office} figure_id=0 (ABSTAIN) | PASS",
                level=logging.DEBUG
            )
            continue

        # figure 存在且存活
        figure = state.get_member(figure_id)
        if not figure or figure.is_dead:
            batch_errors.append({
                "index": idx,
                "office": office,
                "figure_id": figure_id,
                "reason": "figure not found or dead"
            })
            continue

        # figure 是该 office 的合法候选人
        cand_result = get_candidates(state)
        candidates = cand_result.get("data", {}) if cand_result.get("success") else {}
        cand_ids = {c["id"] for c in candidates.get(office, [])}
        if figure_id not in cand_ids:
            batch_errors.append({
                "index": idx,
                "office": office,
                "figure_id": figure_id,
                "reason": f"figure not a candidate for office '{office}'"
            })
            continue

        validated_entries.append((office, figure_id))
        state.log_event(
            f"BATCH_VOTE_VALIDATION: entry[{idx}] office={office} figure_id={figure_id} | PASS",
            level=logging.DEBUG
        )

    # FC-01: 部分 batch 拒绝（缺失 office）
    if not batch_errors:
        missing_offices = VALID_OFFICES - offices_in_batch
        if missing_offices:
            batch_errors.append({
                "index": -1,
                "office": "(batch)",
                "figure_id": 0,
                "reason": f"missing offices: {sorted(missing_offices)}; batch must include all 5 offices (FC-01)"
            })

    # 有错误 → 零写入
    if batch_errors:
        code = "DUPLICATE_OFFICE" if any("duplicate office" in e.get("reason", "") for e in batch_errors) else "INVALID_BATCH"
        state.log_event(
            f"BATCH_VOTE_SKIP: zero write due to validation failure ({len(batch_errors)} errors, code={code})",
            level=logging.DEBUG
        )
        return api_response(False, "Validation failed, zero writes", data={
            "vote_count": 0,
            "failed_entries": batch_errors,
        }, errors=[{"code": code, "message": e["reason"]} for e in batch_errors])

    # ── 计算批次签名（FC-06 G5-R2: frozen value = (player_id, frozenset((office, figure_id)...))） ──
    batch_signature = (player_id, frozenset(validated_entries))

    # ── 3. Core 原子提交 ──
    from src.core.service.population_service import check_and_commit_vote
    core_result = check_and_commit_vote(
        state,
        player_id,
        validated_entries,
        batch_signature,
    )

    if not core_result["success"]:
        errors = core_result.get("errors", [])
        is_busy = any(e.get("code") == "BATCH_BUSY" for e in errors)
        state.log_event(
            f"BATCH_VOTE_CORE: {'BUSY' if is_busy else 'FAILED'}, errors={errors}",
            level=logging.WARNING if is_busy else logging.ERROR
        )
        data = core_result.get("data", {})
        return api_response(
            False,
            core_result.get("message", "Batch vote failed"),
            data={
                "vote_count": 0,
                "retryable": data.get("retryable", False),
            },
            errors=errors,
        )

    # 幂等成功
    core_data = core_result.get("data", {})
    if core_data.get("already_committed"):
        state.log_event(
            f"BATCH_VOTE_IDEMPOTENT: already committed (player={player_id})",
            level=logging.DEBUG
        )
        return api_response(
            True,
            "Already voted",
            data={
                "vote_count": 0,
                "already_committed": True,
            }
        )

    # 正常成功
    return api_response(
        True,
        core_result.get("message", "Votes recorded"),
        data={
            "vote_count": core_data.get("vote_count", 0),
            "offices_voted": core_data.get("offices_voted", []),
        }
    )


def _validate_vote_json_container(entries: Any) -> List[Dict]:
    """JSON 容器验证 for batch_vote v2.1。"""
    if entries is None:
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": "entries is None"}]
    if isinstance(entries, bool):
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": "entries must be a list, got bool"}]
    if isinstance(entries, (int, float)):
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": f"entries must be a list, got {type(entries).__name__}"}]
    if isinstance(entries, str):
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": "entries must be a list, got string"}]
    if isinstance(entries, dict):
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": "entries must be a list, got dict"}]
    if not isinstance(entries, list):
        return [{"index": -1, "office": "(none)", "figure_id": 0, "reason": f"entries must be a list, got {type(entries).__name__}"}]
    return []


def _validate_vote_dto_types(entries: List[Any]) -> List[Dict]:
    """DTO 类型校验 for batch_vote v2.1 entries: {office, figure_id}。"""
    errors = []

    if not isinstance(entries, list):
        return [{"index": -1, "office": "(invalid)", "figure_id": "(invalid)", "reason": "entries must be a list"}]

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append({
                "index": idx,
                "office": "(invalid)",
                "figure_id": "(invalid)",
                "reason": "entry must be a dict"
            })
            continue

        allowed_keys = {"office", "figure_id"}
        extra_keys = set(entry.keys()) - allowed_keys
        if extra_keys:
            errors.append({
                "index": idx,
                "office": entry.get("office", "(unknown)"),
                "figure_id": entry.get("figure_id", "(unknown)"),
                "reason": f"unexpected fields: {sorted(extra_keys)}"
            })
            continue

        # office 字段校验
        if "office" not in entry:
            errors.append({
                "index": idx,
                "office": "(missing)",
                "figure_id": entry.get("figure_id", "(unknown)"),
                "reason": "missing required field 'office'"
            })
            continue

        if "figure_id" not in entry:
            errors.append({
                "index": idx,
                "office": entry.get("office", "(unknown)"),
                "figure_id": "(missing)",
                "reason": "missing required field 'figure_id'"
            })
            continue

        office = entry.get("office")
        figure_id = entry.get("figure_id")

        if not isinstance(office, str):
            errors.append({
                "index": idx,
                "office": str(office),
                "figure_id": figure_id,
                "reason": f"office must be str, got {type(office).__name__}"
            })
            continue

        if not isinstance(figure_id, int) or isinstance(figure_id, bool):
            errors.append({
                "index": idx,
                "office": office,
                "figure_id": figure_id,
                "reason": f"figure_id must be int, got {type(figure_id).__name__}"
            })
            continue

    return errors


def _normalize_vote_entries(entries: List[Dict]) -> List[Dict]:
    """规范化 vote entries v2.1 用于签名计算。按 office 排序。"""
    normalized = []
    for entry in entries:
        normalized.append({
            "office": str(entry.get("office", "")),
            "figure_id": int(entry.get("figure_id", 0)),
        })
    return sorted(normalized, key=lambda e: e["office"])


def _validate_json_container(entries: Any) -> List[Dict]:
    """
    JSON 容器验证：在 len() 或遍历前检查 entries 是否为 list。
    拒绝 None/int/float/string/dict。
    Returns: 错误列表，空列表表示全部通过。
    """
    if entries is None:
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": "entries is None"}]
    if isinstance(entries, bool):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": "entries must be a list, got bool"}]
    if isinstance(entries, (int, float)):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": f"entries must be a list, got {type(entries).__name__}"}]
    if isinstance(entries, str):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": "entries must be a list, got string"}]
    if isinstance(entries, dict):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": "entries must be a list, got dict"}]
    if not isinstance(entries, list):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": f"entries must be a list, got {type(entries).__name__}"}]
    return []


def _validate_dto_types(entries: List[Any]) -> List[Dict]:
    """
    DTO 类型校验：严格验证 figure_id/amount 为 int，拒绝 bool/float/string/额外字段。
    Returns: 错误列表，空列表表示全部通过。
    """
    errors = []

    if not isinstance(entries, list):
        return [{"index": -1, "figure_id": 0, "amount": 0, "reason": "entries must be a list"}]

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append({
                "index": idx,
                "figure_id": "(invalid)",
                "amount": "(invalid)",
                "reason": "entry must be a dict"
            })
            continue

        # 检查额外字段
        allowed_keys = {"figure_id", "amount"}
        extra_keys = set(entry.keys()) - allowed_keys
        if extra_keys:
            errors.append({
                "index": idx,
                "figure_id": entry.get("figure_id", "(unknown)"),
                "amount": entry.get("amount", "(unknown)"),
                "reason": f"unexpected fields: {sorted(extra_keys)}"
            })
            continue

        figure_id = entry.get("figure_id", 0)
        amount = entry.get("amount", 0)

        # figure_id 类型校验
        if not isinstance(figure_id, int) or isinstance(figure_id, bool):
            errors.append({
                "index": idx,
                "figure_id": figure_id,
                "amount": amount,
                "reason": f"figure_id must be int, got {type(figure_id).__name__}"
            })
            continue

        # amount 类型校验
        if not isinstance(amount, int) or isinstance(amount, bool):
            errors.append({
                "index": idx,
                "figure_id": figure_id,
                "amount": amount,
                "reason": f"amount must be int, got {type(amount).__name__}"
            })
            continue

    return errors


def _normalize_entries(entries: List[Dict]) -> List[Dict]:
    """规范化 entries 用于签名计算，只保留 figure_id 和 amount 字段。"""
    normalized = []
    for entry in entries:
        normalized.append({
            "figure_id": int(entry.get("figure_id", 0)),
            "amount": int(entry.get("amount", 0)),
        })
    return sorted(normalized, key=lambda e: e["figure_id"])


def vote(
    state: GameState,
    player_id: str,
    office: str,
    figure_id: int,
    bypass_permission: bool = False
) -> dict:
    """
    为指定公职的候选人投票。
    权限：当前玩家（除非 bypass_player_check=True）。
    规则：每个玩家在每个官职只能投一次，重复投票将报错。
    """
    bypass = bypass_permission or state.config.get("testing.bypass_player_check", False)

    if not bypass:
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 验证公职名称
    valid_offices = ["consul", "censor", "praetor", "quaestor", "tribune"]
    if office not in valid_offices:
        return api_response(False, i18n.get("error_invalid_office"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    # 检查候选人资格
    cand_result = get_candidates(state)
    if cand_result["success"]:
        candidates = cand_result["data"].get(office, [])
        if not any(c["id"] == figure_id for c in candidates):
            return api_response(False, i18n.get("error_figure_not_candidate"))

    if not state.record_population_vote(
        player_id,
        office,
        figure_id,
        replace=bypass_permission
    ):
        return api_response(False, i18n.get("error_already_voted", office=office.upper()))

    message = i18n.get("info_vote_recorded", office=office.upper(), name=figure.get_formal_name())
    state.log_event(
        f"投票: 玩家 {player_id} 为 {office} 投给 {figure.name}",
        extra={"player_id": player_id, "office": office, "figure_id": figure_id}
    )
    return api_response(True, message, data={"office": office, "figure_id": figure_id})


def get_candidates(state: GameState) -> dict:
    """
    获取所有公职的候选人列表（结构化数据）。
    按官职优先级从高到低处理，每个官职从所有符合资格且未被更高官职录用的人选中选出前N名。
    """
    office_priority = ["consul", "censor", "praetor", "quaestor", "tribune"]  # 从高到低
    final_data = {office: [] for office in office_priority}
    used_figure_ids = set()  # 已入选更高官职的人物ID

    current_turn = state.turn.turn_number

    for office in office_priority:
        # 收集所有存活且未占用且符合该官职资格的人物
        candidates = []
        for fig in state.get_living_members():
            if fig.is_absent:
                continue
            if fig.faction_id is None:  # curia 中无派系新人不应参选
                continue
            if fig.id in used_figure_ids:
                continue
            can_hold, _ = fig.can_hold_office(office, current_turn, state.config)
            if can_hold:
                candidates.append(fig)

        # 按资格属性排序
        sorted_candidates = sorted(
            candidates,
            key=lambda fig: fig.get_qualification_attribute(office),
            reverse=True
        )

        # 取前N名
        num_candidates = state.config.get("political_rules", {}).get("candidates_per_election", {}).get(office, 2)
        top_candidates = sorted_candidates[:num_candidates]

        # 记录录用者
        for fig in top_candidates:
            used_figure_ids.add(fig.id)

        # 构建输出列表
        cand_list = []
        for fig in top_candidates:
            faction = state.get_faction(fig.faction_id) if fig.faction_id else None
            cand_list.append({
                "id": fig.id,
                "name": fig.get_formal_name(),
                "faction_id": fig.faction_id,
                "faction_name": faction.name if faction else "无",
                "martial": fig.martial,
                "intelligence": fig.intelligence,
                "charisma": fig.charisma,
                "zeal": fig.zeal,
                "influence": fig.influence,
                "wealth": fig.wealth,
            })
        final_data[office] = cand_list

    message = _format_candidates_message(final_data)
    return api_response(True, message, data=final_data)


def _get_eligible_for_office(state: GameState, office_type: str) -> List[Figure]:
    """获取指定公职的合格候选人（复用原逻辑）"""
    current_turn = state.turn.turn_number
    eligible = []
    for fig in state.get_living_members():
        if fig.is_absent:  # 不在罗马不能参选
            continue
        can_hold, _ = fig.can_hold_office(office_type, current_turn, state.config)
        if can_hold:
            eligible.append(fig)
    return eligible


def _format_candidates_message(data: Dict[str, List[Dict]]) -> str:
    """格式化候选人消息，与设计文档一致（包括图标、缩进、属性）"""
    lines = []
    office_names = {
        "consul": "🏛️ CONSUL",
        "censor": "📜 CENSOR",
        "praetor": "⚖ PRAETOR",
        "quaestor": "💰 QUAESTOR",
        "tribune": "🛡️ TRIBUNE"
    }
    for office, cands in data.items():
        # 每个官职标题一行
        lines.append(f"\n   {office_names.get(office, office.upper())}: ")
        if not cands:
            # 若无候选人，可选择不显示或显示占位，当前可能不显示该官职，但设计文档要求显示标题？我们保持现状。
            continue
        for c in cands:
            faction_disp = f"({c['faction_name']})" if c['faction_name'] != "无" else ""
            # 缩进6空格，格式：ID:1 姓名 (派系) 军略X 智略X 魅力X 热忱X
            lines.append(
                f"      ID:{c['id']} {c['name']} {faction_disp} "
                f"军略{c['martial']} 智略{c['intelligence']} 魅力{c['charisma']} 热忱{c['zeal']}"
            )
    if not lines:
        return "\n   📋 当前无候选人"
    return "\n".join(lines)

def resolve_election(state: GameState) -> dict:
    """
    统计投票结果，确定当选者，授予官职。
    根据人口阶段投票记录进行加权计票。
    """
    votes = state.get_population_votes()
    if not votes:
        return api_response(True, "无投票记录", data={})

    # 按公职分组投票
    votes_by_office = {}
    cand_result = get_candidates(state)
    candidates_by_office = cand_result.get("data", {}) if cand_result.get("success") else {}
    candidate_ids_by_office = {
        office: {c["id"] for c in candidates} for office, candidates in candidates_by_office.items()
    }
    for player_id, office, fig_id in votes:
        # ABSTAIN skip (FC-03): figure_id=0 不计入加权计票
        if fig_id == 0:
            continue
        votes_by_office.setdefault(office, []).append((player_id, fig_id))

    # 获取所有存活人物
    living_members = {m.id: m for m in state.get_living_members()}

    # 计算每个派系的总影响力（直接遍历所有存活人物）
    faction_influence = {}
    for member in state.get_living_members():
        if member.faction_id:
            faction_influence[member.faction_id] = faction_influence.get(member.faction_id, 0) + member.influence

    results = []
    elected_figures = []
    election_results = []

    election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
    for office in election_order:
        office_votes = votes_by_office.get(office, [])
        if not office_votes:
            continue

        # 计算每位候选人获得的加权票数
        valid_candidate_ids = candidate_ids_by_office.get(office, set())
        score = {}
        for player_id, fig_id in office_votes:
            if fig_id not in valid_candidate_ids:
                continue
            player = state.get_player(player_id)
            if not player:
                continue
            faction_id = player.faction_id
            if not faction_id:
                continue
            influence = faction_influence.get(faction_id, 0)
            if influence > 0:
                score[fig_id] = score.get(fig_id, 0) + influence

        if not score:
            continue

        max_score = max(score.values())
        top_candidates = [fig_id for fig_id, s in score.items() if s == max_score]
        if len(top_candidates) > 1:
            winner_id = random.choice(top_candidates)
        else:
            winner_id = top_candidates[0]

        winner = living_members.get(winner_id)
        if winner:
            winner.office = office
            winner.update_influence()
            if office == "consul":
                # 将执政官加入 leader_ids（如果不在的话）
                if winner.id not in state.turn.leader_ids:
                    state.turn.leader_ids.append(winner.id)
            elected_figures.append(winner)

            faction = state.get_faction(winner.faction_id)
            faction_name = faction.name if faction else "无"
            # ATTEMPT-3 (Owner Option A): per-candidate scores — 来自 L990-998 生产路径
            candidates_list = []
            for fig_id, s in sorted(score.items(), key=lambda x: x[1], reverse=True):
                fig = living_members.get(fig_id)
                if fig:
                    candidates_list.append({
                        "figure_id": fig_id,
                        "figure_name": fig.get_formal_name(),
                        "faction_id": fig.faction_id,
                        "score": s
                    })
            election_results.append({
                "office": office,
                "figure_id": winner.id,
                "figure_name": winner.get_formal_name(),
                "faction_id": winner.faction_id,
                "faction_name": faction_name,
                "faction_short_name": faction_name[:3] if faction_name != "无" else "",
                "score": score.get(winner.id, 0),
                "candidates": candidates_list,
            })
            results.append(f"      {office.upper()}: {winner.get_formal_name()} ({faction_name})")
            state.log_event(
                f"选举结果: {office} 当选者 {winner.name}",
                extra={"type": "election", "office": office, "figure_id": winner.id}
            )

    # 更新派系领袖
    for faction in state.factions.values():
        faction.update_faction_leader(state)

    if results:
        message = "\n   📋 选举结果：\n" + "\n".join(results)
    else:
        message = "   📋 无有效选举结果"

    return api_response(True, message, data={"elected": [f.id for f in elected_figures], "election_results": election_results})


def convert_battlefield_commanders(state: GameState) -> dict:
    """
    Convert battlefield commanders (consul\u2192proconsul, praetor\u2192propraetor).

    Scans all living members for absent consuls/praetors, finds their war,
    records office history, converts the office, updates influence,
    and updates war.commander_assigned_turn.

    Idempotent: only performs conversion once per population phase.
    Results are stored in state._phase_results["battlefield_commander_conversion"]
    so subsequent calls return the same DTO without re-executing.

    Returns:
        dict: {
            "converted": [
                {
                    "figure_id": int,
                    "name": str,
                    "old_office": str,
                    "new_office": str,
                    "war_id": str | None,
                },
                ...
            ],
            "total": int,
        }
    """
    # Idempotent guard: if results already stored, return them
    # Use isinstance check to distinguish real dict results from MagicMock returns
    stored = state.get_phase_result("battlefield_commander_conversion")
    if isinstance(stored, dict) and "converted" in stored:
        return stored

    current_turn = state.turn.turn_number
    war_system = state.get_war_system()
    converted = []

    if not war_system:
        result = {"converted": [], "total": 0}
        state.record_phase_result("battlefield_commander_conversion", result)
        return result

    for figure in state.get_living_members():
        if not figure.is_absent:
            continue
        if figure.office not in ("consul", "praetor"):
            continue

        old_office = figure.office
        war = war_system.get_war_by_commander(figure.id)

        # Determine assigned turn
        if war and war.commander_assigned_turn is not None:
            assigned_turn = war.commander_assigned_turn
        else:
            assigned_turn = current_turn - 1

        # Record office history
        figure.add_office_history(old_office, assigned_turn, current_turn - 1)

        # Convert office
        new_office = "proconsul" if old_office == "consul" else "propraetor"
        figure.office = new_office
        figure.update_influence()

        # Update war commander_assigned_turn if applicable
        if war:
            war.set_commander_assigned_turn(current_turn)

        converted.append({
            "figure_id": figure.id,
            "name": figure.get_formal_name() if hasattr(figure, "get_formal_name") else figure.name,
            "old_office": old_office,
            "new_office": new_office,
            "war_id": war.id if war else None,
        })

    result = {"converted": converted, "total": len(converted)}
    # Persist DTO for GUI consumption
    state.record_phase_result("battlefield_commander_conversion", result)
    return result


def archive_office_holders(state: GameState) -> dict:
    """卸任所有现任官员（对齐 CLI _remove_office_holders 语义）。

    战场指挥官（is_absent 的 consul/praetor）跳过——由
    convert_battlefield_commanders 处理（置 proconsul/propraetor 而非 ex-，
    历史 end=current_turn-1）。调用顺序约束：本函数必须先于
    convert_battlefield_commanders 执行（P1-1b）。
    """
    current_turn = state.turn.turn_number
    election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
    archived = []
    for office_type in election_order:
        for fig in state.get_living_members():
            if fig.office != office_type:
                continue
            # P1-1（对齐 phase_population.py:175）：缺席战场指挥官跳过
            if fig.is_absent and office_type in ("consul", "praetor"):
                continue
            # P2-1 顺序依赖：add_office_history 内部置 office=None（figure.py:558），
            # 下方 office=f"ex-{...}" 是强制第二步，不可省略
            fig.add_office_history(office_type, current_turn - 1, current_turn)  # 对齐 :179
            fig.office = f"ex-{office_type}"                                      # 对齐 :180
            fig.update_influence()                                                # 对齐 :181
            if office_type == "consul" and fig.id in state.turn.leader_ids:
                state.turn.leader_ids.remove(fig.id)                              # 对齐 :183-184
            archived.append({
                "figure_id": fig.id,
                "name": fig.name,
                "office": office_type,
                "start_turn": current_turn - 1,
                "end_turn": current_turn,
            })
    return {"archived": archived, "total": len(archived)}


def begin_population_phase(state: GameState) -> dict:
    """人口阶段入口共享用例：curia 清理 + 现任归档 + 战场指挥官转换。

    幂等：以 phase-result marker "population_entry" 守卫（对齐
    convert_battlefield_commanders 的 "battlefield_commander_conversion"
    幂等模式）。年度推进 _commit_settlement 清空 _phase_results → 每年重新 armed。
    调用顺序（P1-1b）：先归档在场者（archive_office_holders），
    再转换 absent 指挥官（convert_battlefield_commanders）——两条路径
    语义不同且互补，is_absent 跳过保证无双处理。
    """
    stored = state.get_phase_result("population_entry")
    if isinstance(stored, dict) and "archived" in stored:
        return stored

    # 1) curia 清理（对齐 CLI phase_population.py:120-128；P1-2 scope 内）
    curia = state.curia
    if not curia.is_empty():
        ids_to_remove = [fig.id for fig in curia.get_all_available()]
        for fid in ids_to_remove:
            if fid in state._members:
                del state._members[fid]
        curia.clear()

    # 2) 归档在场现任官员（必须先于转换，P1-1b）
    archive_result = archive_office_holders(state)

    # 3) 转换缺席战场指挥官（自带 "battlefield_commander_conversion" 幂等）
    conversion_result = convert_battlefield_commanders(state)

    result = {
        "archived": archive_result.get("archived", []),
        "converted": conversion_result.get("converted", []),
        "curia_cleared": True,
    }
    state.record_phase_result("population_entry", result)
    return result


def process_population_disbandments(state: GameState) -> dict:
    """人口阶段解散生命周期共享用例（§11.5 GUI/CLI 对等，WP-G G4-GD G2）。

    单一 canonical：军团（war_system.process_triumph_and_disbandment，Veteran 保留，
    G1-19） + 舰队（naval_system.disband_unused_fleets → GC disband()，行政退役非
    DESTROYED，G1-13）。

    幂等：phase-result marker "population_disbandment" 守卫（S33，禁双调用/重入重复
    mutation）；底层原语亦天然幂等（resolved wars 的 legion_numbers 已清空 / DISBANDED
    不再命中 decider）。年度推进 _commit_settlement 清空 _phase_results → 每年重新 armed。
    GUI（session_api.resolve_population_slice）与 CLI（phase_population._handle_step_0）
    共享同一入口 → 双入口同 mutation 集（S28/S29/S30）。
    """
    stored = state.get_phase_result("population_disbandment")
    if isinstance(stored, dict) and {"triumphs", "legions", "fleets"} <= set(stored):
        return stored

    ws = state.get_war_system()
    ns = getattr(state, "naval_system", None)
    result = {
        "triumphs": [],
        "legions": {
            "resolved_wars": {"total": 0, "errors": []},
            "deescalated": {"total": 0, "errors": []},
        },
        "fleets": [],
        "re_entry": False,
    }
    if ws and state.get_military_system():
        # ⚠️ S33 exactly-once：单次调用取返回（triumphs + disbanded 同源），禁双调用；
        # 军事系统缺席守卫 = process_triumph_and_disbandment 内部 `if not ms` 同语义
        # （旧 CLI _process_legion_disbandment_and_triumphs 同款早退，禁 MagicMock 炸点）
        disband_result = ws.process_triumph_and_disbandment()
        result["triumphs"] = disband_result.get("triumphs", [])
        result["legions"] = disband_result.get("disbanded", result["legions"])
    if ns:
        from src.core.deciders.impl.auto_fleet_disband_decider import AutoFleetDisbandDecider
        current_turn = state.turn.turn_number if state.turn else 0
        result["fleets"] = ns.disband_unused_fleets(current_turn, AutoFleetDisbandDecider())
    state.record_phase_result("population_disbandment", result)
    return result
