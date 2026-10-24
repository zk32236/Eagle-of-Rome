"""EOR20261013-02 · W4-A1 — D7 canonical market head + PC04 T_B boundary (RED-first).

冻结来源：
  * `01-pm/DA-Task-Brief-W4-A1_2026-10-24.md` §3（RED-first 四项）
  * `00-gates/G4-DA-Exact-WriteFace-W4A1_2026-10-24.md` §1/§4
  * `00-gates/PM-Ruling-W4-A0-Acceptance_2026-10-24.md`（K-1 = C-α；K-2 = S-α）
  * `02-sa-design/W4/02-D7-PC02-Narrow-Design.md` §1.2 / §2.1–§2.2

本模块只做**新增**断言，不修改任何既有断言 / skip / xfail。
产品零改动（本文件先写，随后由 Stage 1–3 实现转绿）。

WATERMARK: DA-Execute W4-A1 RED-first (test-only).
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from src.api import forum_api, session_access, session_api  # noqa: E402
from src.api import session_turn_service as turn_service  # noqa: E402
from src.core.entities.contract import ContractStatus, ContractType  # noqa: E402
from src.core.entities.figure import ClassTier  # noqa: E402
from src.core.entities.war import WarStatus  # noqa: E402
from src.tests.fixtures.wpgr4_fixtures import attach_active, make_war  # noqa: E402

CONFIG_PATH = os.path.join(PROJECT_ROOT, "data", "config", "game_config.json")
SCENARIO_1H2AI = "gui_prototype.json"

#: G4 §4 / Delta §11.2 #8：E_B 逐字四标签（冻结，不增不减）。
EXPECTED_E_B = {"recruit_figure", "place_bid", "buy_land", "vote_triumph"}


# ---------------------------------------------------------------------------
# 夹具：真实工厂会话（不是手搓 GameState；K 由 session_api 捕获）
# ---------------------------------------------------------------------------
def _session(scenario=SCENARIO_1H2AI):
    res = session_api.create_gui_prototype_session(
        config_path=CONFIG_PATH, start_phase="forum", scenario_file=scenario)
    assert res.get("success"), res.get("message")
    return res["data"]["state"]


def _registered(state, principal):
    """登记热座会话（生产工厂之外的唯一服务入口）+ 返回可呈现 handle。"""
    session_access.register_hotseat_session(state, principal, epoch=0)
    ctx = session_access.present_context(state)
    assert ctx is not None
    return ctx


def _faction_player(state, faction_id):
    player = state.get_player_by_faction(faction_id)
    assert player is not None, faction_id
    return player.player_id


def _scope(state):
    return turn_service.mint_scope(state, "forum").scope_id


def _finish(state, pid, substep):
    return turn_service.complete_actor(
        state, None, _scope(state), f"test:w4a1:{substep}:{pid}",
        actor_player_id=pid, substep=substep, phase="forum",
        satisfied_kind=turn_service.KIND_EXPLICIT_FINISH,
        owner_declared=True)


def _finish_all(state, substep):
    for player in state.get_all_players():
        _finish(state, player.player_id, substep)


def _open_receipt(state):
    return turn_service.issue_forum_boundary_receipt(
        state, command_id="open_market", kind="R_OPEN", scope_id=_scope(state))


def _land_pair(state, pid):
    """该玩家派系内一对可交易人物 id（卖家置足土地，交易记录不验财富）。"""
    player = state.get_player(pid)
    faction = state.get_faction(player.faction_id)
    members = faction.get_members(state)
    assert len(members) >= 2, (pid, len(members))
    members[0]._land_private = max(5, getattr(members[0], "_land_private", 0))
    return members[0].id, members[1].id


# ---------------------------------------------------------------------------
# 1) D7 canonical：首席 = optimates（O→P→E），与 dict / HUMAN 列表顺序无关
# ---------------------------------------------------------------------------
def test_d7_canonical_head_is_optimates():
    state = _session()
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    e = _faction_player(state, "equites")
    assert tuple(plan["plan"]) == (o, p, e), plan["plan"]
    assert plan["head"] is not None
    assert plan["head"].actor_player_id == o


def test_d7_canonical_head_detached_from_registry_dict_order():
    """容器重排（_players 插入序反转）不得改变首席 —— K 不是 dict 顺序。"""
    state = _session()
    o = _faction_player(state, "optimates")
    items = list(state._players.items())
    state._players.clear()
    state._players.update(reversed(items))
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    assert plan["head"].actor_player_id == o
    # Stage 3：义务表遍历序同样按 K（而非注册表序）
    snapshot = turn_service.obligations(state, "forum", "market")
    market = [ob for ob in snapshot.obligations if ob.substep == "market"
              and ob.is_executable]
    assert [ob.actor_player_id for ob in market][0] == o


def test_d7_canonical_head_survives_year_reset():
    """跨年：书的 turn/scope 重置不得丢失 session-owned K。"""
    state = _session()
    o = _faction_player(state, "optimates")
    book = turn_service._book(state)
    book.reset_for_new_year()
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    assert plan["head"].actor_player_id == o


def test_d7_canonical_head_advances_after_lawful_none():
    """O 的**合法** NONE（owner-declared explicit finish）→ 首席落 P。"""
    state = _session()
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    assert _finish(state, o, "market").get("success")
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    assert plan["head"].actor_player_id == p


# ---------------------------------------------------------------------------
# 2) T_B：未授权不可达（缺 receipt / 旧 epoch / round 未 SELECTED）
# ---------------------------------------------------------------------------
def test_tb_unreachable_without_open_receipt():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    result = forum_api.start_forum_market_round(
        state, o, market_receipt=None, caller_context=ctx)
    assert result.get("success") is False
    assert result.get("errors"), result


def test_tb_rejects_old_epoch_receipt():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _open_receipt(state)
    # 旧 epoch：签发后 ledger 又前进一格
    turn_service._book(state).revision_counter += 1
    result = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert result.get("success") is False, result


def test_tb_selects_canonical_head_once_and_is_idempotent():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _open_receipt(state)
    first = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert first.get("success"), first
    assert first.get("data", {}).get("actor") == o
    second = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert second.get("success"), second
    assert second.get("data", {}).get("actor") == o
    assert state.get_current_player().player_id == o


# ---------------------------------------------------------------------------
# 3) W0/W1 pending：R_OPEN 已存在而 round 未选择 → 市场动作零写拒绝
# ---------------------------------------------------------------------------
def test_boundary_pending_blocks_transact_land_zero_write():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    state.add_forum_action("market_opened", True)
    _open_receipt(state)

    pending = turn_service.forum_boundary_pending(state)
    assert pending is not None
    assert pending["code"] == "FORUM_BOUNDARY_PENDING"

    seller, buyer = _land_pair(state, o)
    before = list(state.get_forum_pending().get("land_trades", []))
    result = forum_api.transact_land(
        state, o, seller, buyer, 1, 10, caller_context=ctx)
    assert result.get("success") is False, result
    assert "FORUM_BOUNDARY_PENDING" in (result.get("errors") or [])
    assert list(state.get_forum_pending().get("land_trades", [])) == before


def test_boundary_pending_blocks_market_bid_zero_write():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    state.add_forum_action("market_opened", True)
    _open_receipt(state)

    before = list(state.get_forum_pending().get("recruitment_bids", []))
    result = forum_api.recruit_figure(state, o, 10 ** 6, 5, caller_context=ctx)
    assert result.get("success") is False, result
    assert "FORUM_BOUNDARY_PENDING" in (result.get("errors") or [])
    assert list(state.get_forum_pending().get("recruitment_bids", [])) == before


def test_market_action_rejects_non_scheduled_seat():
    """round 已 SELECTED 但调用者不是 K 首席 → MARKET_OBLIGATION_MISMATCH。"""
    state = _session("gr_f_3h.json")      # 3 HUMAN：非首席也必须是真人才能过身份 guard
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, p)          # 本席 = P（非首席）
    state.set_current_player(p)
    scope = _scope(state)
    state.add_forum_action("market_opened", True)
    turn_service.issue_forum_boundary_receipt(
        state, command_id="open_market", kind="R_OPEN", scope_id=scope)
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    boundary = turn_service.issue_forum_boundary_receipt(
        state, command_id="start_forum_market_round", kind="R_BOUNDARY",
        scope_id=scope, actor=plan["head"].actor_player_id)
    turn_service._market_round_registry(state)[scope] = {
        "state": "SELECTED", "receipt_id": boundary["receipt_id"],
        "actor": plan["head"].actor_player_id,
        # TA-W4A1b-01: this node builds the round by hand (no attempt record), so
        # it must DECLARE that legacy origin explicitly. Since P4 the fail-open
        # compatibility branch is gone: an unmarked attempt-less SELECTED round is
        # refused by L0 (FORUM_BOUNDARY_STATE_INVALID / L0_ATTEMPT_MISSING).
        "legacy_manual": True}

    seller, buyer = _land_pair(state, p)
    before = list(state.get_forum_pending().get("land_trades", []))
    result = forum_api.transact_land(
        state, p, seller, buyer, 1, 10, caller_context=ctx)
    assert result.get("success") is False, result
    assert "MARKET_OBLIGATION_MISMATCH" in (result.get("errors") or [])
    assert list(state.get_forum_pending().get("land_trades", [])) == before


# ---------------------------------------------------------------------------
# 4) 第三 registry：未知 root → 空集；三套 keys pairwise disjoint；E_B 逐字不变
# ---------------------------------------------------------------------------
# ===========================================================================
# W4-A1-R2 (G5 RETURN 返修) — 8 组独立负控 / T_B 原子性 / 重复只读 / K 一次绑定
#
# RED-first：本组在 R-01（原子提交 HOLD）与 R-02（K 一次绑定）产品修复**之前**先行
# 落盘并运行，原件为 `03-da-evidence/W4/A1-R2/RED-*.log`（本轮先锁身份再跑 RED）。
# 断言只针对冻结设计（G5 §2.1/§2.2 + PM 裁定 §3），不修改任何既有断言。
# ===========================================================================
BOUNDARY_CODES = (
    "FORUM_BOUNDARY_PENDING",
    "FORUM_BOUNDARY_STATE_INVALID",
    "FORUM_BOUNDARY_RECEIPT_INVALID",
    "FORUM_BOUNDARY_RECEIPT_STALE",
    "FORUM_BOUNDARY_RECEIPT_CONSUMED",
    "FORUM_BOUNDARY_RECEIPT_KIND_MISMATCH",
    "MARKET_OBLIGATION_MISMATCH",
    "MARKET_OBLIGATION_MISSING",
)


def _errors(result):
    out = []
    for err in (result.get("errors") or []):
        out.append(err.get("code") if isinstance(err, dict) else str(err))
    return out


def _receipts(state):
    return dict(getattr(turn_service._book(state), "_forum_boundary_receipts", {}) or {})


def _consumed(state):
    return set(getattr(turn_service._book(state), "_consumed_boundary_receipts", set()) or set())


def _rounds(state):
    return dict(turn_service._market_round_registry(state))


def _pending_digest(state):
    """业务写面快照：每个 pending 键的可比较表示（列表逐项 repr）。"""
    pending = state.get_forum_pending()
    out = {}
    for key, value in pending.items():
        if isinstance(value, list):
            out[key] = tuple(repr(item) for item in value)
        else:
            out[key] = repr(value)
    return out


def _business_ids(state):
    """真实业务 id（有则取活对象，没有则给出形状正确的占位）。"""
    figures = [f.id for f in state.curia.get_all_available()] if state.curia else []
    contracts = [getattr(c, "id", None) for c in getattr(state, "contracts", []) or []]
    wars = [getattr(w, "id", "") for w in getattr(state, "wars", []) or []]
    return {
        "figure_id": figures[0] if figures else 10 ** 6,
        "contract_id": contracts[0] if contracts and contracts[0] is not None else 0,
        "war_id": wars[0] if wars else "",
    }


def _five_actions(state, pid, ctx):
    ids = _business_ids(state)
    return [
        ("transact_land", lambda: forum_api.transact_land(
            state, pid, **_land_pair_kwargs(state, pid), caller_context=ctx)),
        ("recruit_figure", lambda: forum_api.recruit_figure(
            state, pid, ids["figure_id"], 5, caller_context=ctx)),
        ("place_bid", lambda: forum_api.place_bid(
            state, pid, ids["figure_id"], ids["contract_id"], 5,
            caller_context=ctx)),
        ("buy_land", lambda: forum_api.buy_land(
            state, pid, ids["figure_id"], 5, caller_context=ctx)),
        ("vote_triumph", lambda: forum_api.vote_triumph(
            state, pid, ids["war_id"], True, caller_context=ctx)),
    ]


def _land_pair_kwargs(state, pid):
    seller, buyer = _land_pair(state, pid)
    return {"seller_id": seller, "buyer_id": buyer, "land": 1, "price": 10}


def _market_window_open(state, pid, ctx, finish_retirement=True):
    """真实 O_M 链：retirement 完成 → open_market → 签发 R_OPEN（A2 签发点替身）。"""
    if finish_retirement:
        _finish_all(state, "retirement")
    opened = forum_api.open_market(state, pid, caller_context=ctx)
    assert opened.get("success"), opened
    return _open_receipt(state)


# ---------------------------------------------------------------------------
# R-03.1 bypass_permission=True 必须被拒（guard 或 body 显式拒绝，绝不静默放行）
# ---------------------------------------------------------------------------
def test_r2_bypass_permission_true_is_refused_and_zero_write():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    before = _pending_digest(state)
    seller, buyer = _land_pair(state, o)
    result = forum_api.transact_land(
        state, o, seller, buyer, 1, 10, True, caller_context=ctx)
    assert result.get("success") is False, result
    errors = _errors(result)
    assert errors, result
    assert set(errors) & {"DENIED", "FORUM_BOUNDARY_BYPASS_DENIED"}, errors
    assert _pending_digest(state) == before


# ---------------------------------------------------------------------------
# R-03.2 五动作 W1：R_OPEN 未消费、round 未选择 → 全部 FORUM_BOUNDARY_PENDING 零写
# ---------------------------------------------------------------------------
def test_r2_w1_pending_refuses_all_five_actions_zero_write():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _market_window_open(state, o, ctx)
    assert turn_service.forum_boundary_pending(state) is not None
    before = _pending_digest(state)
    for name, call in _five_actions(state, o, ctx):
        result = call()
        assert result.get("success") is False, (name, result)
        assert "FORUM_BOUNDARY_PENDING" in _errors(result), (name, result)
    assert _pending_digest(state) == before
    assert _rounds(state) == {}


# ---------------------------------------------------------------------------
# R-03.2b 五动作 W2 允许测：round SELECTED 且调用者 = K 首席 → 不出现任何边界拒绝
# ---------------------------------------------------------------------------
def test_r2_w2_admits_canonical_head_on_all_five_actions():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    started = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert started.get("success"), started
    assert started["data"]["actor"] == o
    for name, call in _five_actions(state, o, ctx):
        result = call()
        assert not (set(_errors(result)) & set(BOUNDARY_CODES)), (name, result)


# ---------------------------------------------------------------------------
# R-03.2c 五动作 W2 拒绝测：round 已提交但调用者不是 K 首席 → 逐入口 MISMATCH 零写
# ---------------------------------------------------------------------------
def test_r2_w2_non_head_seat_refused_on_all_e_b_actions():
    state = _session("gr_f_3h.json")
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, p)          # 本席 = P（非首席，且是真人以过身份门）
    state.set_current_player(p)
    receipt = _market_window_open(state, p, ctx)
    started = forum_api.start_forum_market_round(
        state, p, market_receipt=receipt, caller_context=ctx)
    assert started.get("success"), started
    assert started["data"]["actor"] == o, started          # 真实 T_B 选中 K 首席 O
    # 夹具：guard 要求 current == principal，把游标放回 P 以模拟「P 的回合」
    state.set_current_player(p)
    before = _pending_digest(state)
    for name, call in _five_actions(state, p, ctx)[1:]:      # 四个 E_B
        result = call()
        assert result.get("success") is False, (name, result)
        assert "MARKET_OBLIGATION_MISMATCH" in _errors(result), (name, result)
    assert _pending_digest(state) == before


# ---------------------------------------------------------------------------
# R-03.3 四 settlement 端点 W1：边界未提交 → 拒绝且零写
# ---------------------------------------------------------------------------
def test_r2_w1_refuses_four_settlement_endpoints_zero_write():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    _finish_all(state, "market")            # 让 owner_barrier 通过，只剩边界门
    opened = forum_api.open_market(state, o, caller_context=ctx)
    assert opened.get("success"), opened
    _open_receipt(state)
    assert state.get_phase_result("forum") is None
    before = _pending_digest(state)
    calls = [
        ("resolve_forum", lambda: forum_api.resolve_forum(state, caller_context=ctx)),
        ("advance_forum_phase", lambda: forum_api.advance_forum_phase(
            state, o, caller_context=ctx)),
        ("resolve_land_trades", lambda: forum_api.resolve_land_trades(
            state, caller_context=ctx)),
        ("execute_land_acts", lambda: forum_api.execute_land_acts(
            state, caller_context=ctx)),
    ]
    for name, call in calls:
        result = call()
        assert result.get("success") is False, (name, result)
        assert "FORUM_BOUNDARY_PENDING" in _errors(result), (name, result)
    assert state.get_phase_result("forum") is None
    assert _pending_digest(state) == before


# ---------------------------------------------------------------------------
# R-03.4 四 initializer 裸调用（无 O_M marker）→ 拒绝
# ---------------------------------------------------------------------------
def test_r2_w1_refuses_four_bare_initializers():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    _open_receipt(state)
    assert turn_service.forum_boundary_pending(state) is not None
    calls = [
        ("initialize_forum_turn", lambda: forum_api.initialize_forum_turn(
            state, caller_context=ctx)),
        ("generate_figures", lambda: forum_api.generate_figures(
            state, caller_context=ctx)),
        ("generate_contracts", lambda: forum_api.generate_contracts(
            state, caller_context=ctx)),
        ("check_province_unrest", lambda: forum_api.check_province_unrest(
            state, caller_context=ctx)),
    ]
    for name, call in calls:
        result = call()
        assert result.get("success") is False, (name, result)
        assert "FORUM_BOUNDARY_PENDING" in _errors(result), (name, result)


# ---------------------------------------------------------------------------
# R-03.5 O_M 允许链：marker 在同步边内设置，finally 必清除（成功 / 抛异常）
# ---------------------------------------------------------------------------
def test_r2_om_marker_cleared_after_success():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    book = turn_service._book(state)
    opened = forum_api.open_market(state, o, caller_context=ctx)
    assert opened.get("success"), opened
    assert getattr(book, "_forum_owner_initialization", None) is None


def test_r2_om_marker_cleared_when_initializer_raises(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    book = turn_service._book(state)

    def _boom(*args, **kwargs):
        # 进入同步边时 marker 必须在位（证明例外只覆盖这一条调用边）
        assert getattr(book, "_forum_owner_initialization", None) == "open_market"
        raise RuntimeError("initializer exploded")

    monkeypatch.setattr(forum_api, "initialize_forum_turn", _boom)
    with pytest.raises(RuntimeError):
        forum_api.open_market(state, o, caller_context=ctx)
    assert getattr(book, "_forum_owner_initialization", None) is None


# ---------------------------------------------------------------------------
# R-03.6 / R-01 失败原子性：cursor 写失败 → receipts/consumed/round/cursor/业务/RNG 守恒
#                 + 可判定 HOLD 使 legacy 放行分支不可达
# ---------------------------------------------------------------------------
def test_r2_failed_tb_commit_is_atomic_and_holds(monkeypatch):
    import random

    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    receipts_before = _receipts(state)
    consumed_before = _consumed(state)
    rounds_before = _rounds(state)
    cursor_before = state.get_current_player().player_id
    business_before = _pending_digest(state)
    rng_before = random.getstate()

    monkeypatch.setattr(state, "set_current_player", lambda *a, **k: False)
    failed = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    monkeypatch.undo()

    assert failed.get("success") is False, failed
    assert "SET_CURRENT_FAILED" in _errors(failed), failed
    # 三个 commit 事实全部回滚（不是只删 round）
    assert _receipts(state) == receipts_before
    assert _consumed(state) == consumed_before
    assert _rounds(state) == rounds_before
    assert state.get_current_player().player_id == cursor_before
    assert _pending_digest(state) == business_before
    assert random.getstate() == rng_before
    # 失败可判定（HOLD），且 legacy 放行分支不可达
    hold = turn_service.forum_market_round_hold(state, scope)
    assert hold is not None, "failure must leave a decidable hold fact"
    assert hold.get("reason") == "SET_CURRENT_FAILED", hold
    pending = turn_service.forum_boundary_pending(state)
    assert pending is not None, "failed commit must NOT fall back to legacy admit"
    assert pending["code"] == "FORUM_BOUNDARY_PENDING", pending
    mismatch = turn_service.market_obligation_matches(state, o)
    assert mismatch is not None and mismatch["code"] == "FORUM_BOUNDARY_PENDING", mismatch
    # R_OPEN 未被吞掉：同一 receipt 可重试（重试是全新提交，不是重复读）
    retried = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert retried.get("success"), retried
    assert turn_service.forum_market_round_hold(state, scope) is None
    assert _consumed(state) == {receipt["receipt_id"]}


def test_r2_failed_tb_commit_by_exception_is_atomic(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)
    receipts_before = _receipts(state)
    consumed_before = _consumed(state)

    def _boom(*args, **kwargs):
        raise RuntimeError("cursor writer exploded")

    monkeypatch.setattr(turn_service, "select_actor", _boom)
    with pytest.raises(RuntimeError):
        forum_api.start_forum_market_round(
            state, o, market_receipt=receipt, caller_context=ctx)
    monkeypatch.undo()

    assert _receipts(state) == receipts_before
    assert _consumed(state) == consumed_before
    assert _rounds(state) == {}
    hold = turn_service.forum_market_round_hold(state, scope)
    assert hold is not None and "exploded" in hold.get("reason", ""), hold
    assert turn_service.forum_boundary_pending(state) is not None


# ---------------------------------------------------------------------------
# R-03.7 真实 retirement → open_market → T_B；非 O 首 outstanding 场景
# ---------------------------------------------------------------------------
def test_r2_real_retirement_open_then_tb_selects_head():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)          # 真实 retirement + O_M
    assert state.get_forum_pending().get("market_opened")   # Core 记录的是 [True]
    started = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert started.get("success"), started
    assert started["data"]["actor"] == o
    assert state.get_current_player().player_id == o
    assert started["data"]["round"] == turn_service.MARKET_ROUND_SELECTED


def test_r2_tb_selects_non_optimates_head_when_first_finished():
    state = _session()
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    assert _finish(state, o, "market").get("success")       # O 合法完成 → 首席前移
    # 合法完成会推进 ledger revision，故 R_OPEN 必须在完成后签发（同串行段语义）
    receipt = _open_receipt(state)
    started = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert started.get("success"), started
    assert started["data"]["actor"] == p, started
    assert state.get_current_player().player_id == p
    mismatch = turn_service.market_obligation_matches(state, o)
    assert mismatch is not None and mismatch["code"] == "MARKET_OBLIGATION_MISMATCH"


# ---------------------------------------------------------------------------
# R-03.8 重复 T_B：只读已提交事实，不新增 cursor 写 / receipt / round
# ---------------------------------------------------------------------------
def test_r2_repeat_tb_reads_committed_fact_without_new_writes(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    first = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert first.get("success"), first
    receipts_after_first = _receipts(state)
    rounds_after_first = _rounds(state)

    writes = []
    original = state.set_current_player

    def _counting(pid):
        writes.append(pid)
        return original(pid)

    monkeypatch.setattr(state, "set_current_player", _counting)
    second = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    monkeypatch.undo()

    assert second.get("success"), second
    assert writes == []                                   # 零 cursor 写
    assert _receipts(state) == receipts_after_first        # 零新 receipt
    assert _rounds(state) == rounds_after_first
    assert (second["data"]["boundary_receipt"]["receipt_id"]
            == first["data"]["boundary_receipt"]["receipt_id"])
    assert second["data"]["actor"] == o


def test_r2_committed_reread_rejects_a_broken_boundary_receipt():
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    started = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert started.get("success"), started
    scope = _scope(state)
    rid = _rounds(state)[scope]["receipt_id"]
    turn_service._book(state)._forum_boundary_receipts.pop(rid)
    again = forum_api.start_forum_market_round(
        state, o, market_receipt=receipt, caller_context=ctx)
    assert again.get("success") is False, again
    assert "FORUM_BOUNDARY_STATE_INVALID" in _errors(again), again


# ---------------------------------------------------------------------------
# R-02 K 一次绑定：同值只读确认 / 不同值 typed 拒绝 / 不得裁席位
# ---------------------------------------------------------------------------
def test_r2_k_rebind_same_value_is_read_only():
    state = _session()
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    same = turn_service.canonical_market_plan(state, bind=tuple(plan["plan"]))
    assert same.get("success"), same
    assert same.get("read_only") is True, same
    assert tuple(same["plan"]) == tuple(plan["plan"])


def test_r2_k_rebind_different_value_is_refused():
    state = _session()
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    e = _faction_player(state, "equites")
    reordered = turn_service.canonical_market_plan(state, bind=(o, e, p))
    assert reordered.get("success") is False, reordered
    assert reordered.get("code") == "CANONICAL_PLAN_ALREADY_BOUND", reordered
    kept = turn_service.canonical_market_plan(state)
    assert tuple(kept["plan"]) == (o, p, e), kept["plan"]


def test_r2_k_bind_cannot_drop_a_seat():
    state = _session()
    o = _faction_player(state, "optimates")
    dropped = turn_service.canonical_market_plan(state, bind=(o,))
    assert dropped.get("success") is False, dropped
    assert dropped.get("code") in (
        "CANONICAL_PLAN_INCOMPLETE", "CANONICAL_PLAN_ALREADY_BOUND"), dropped

    # 未绑定的会话（模拟 capture 点）也不能用 bind 裁掉席位
    fresh = _session()
    o2 = _faction_player(fresh, "optimates")
    delattr(fresh, "_canonical_market_plan")
    cut = turn_service.canonical_market_plan(fresh, bind=(o2,))
    assert cut.get("success") is False, cut
    assert cut.get("code") == "CANONICAL_PLAN_INCOMPLETE", cut
    assert getattr(fresh, "_canonical_market_plan", None) is None


def test_third_registry_unknown_root_is_empty_and_disjoint():
    from src.ui.gui.session_store import GuiSessionStore

    market_round = GuiSessionStore._MARKET_ROUND_LEASE_HELPERS
    legacy = GuiSessionStore._LEASE_HELPERS
    phase_role = GuiSessionStore._PHASE_ROLE_LEASE_HELPERS

    assert GuiSessionStore._helpers_for_owning_command("no_such_root") == frozenset()
    assert GuiSessionStore._helpers_for_owning_command(
        "start_forum_market_round") == frozenset(EXPECTED_E_B)
    assert set(market_round) == {"start_forum_market_round"}
    assert set(market_round) & set(legacy) == set()
    assert set(market_round) & set(phase_role) == set()
    assert set(legacy) & set(phase_role) == set()
    # E_B 逐字冻结：四标签不变，且 transact_land 不在其中
    assert set(legacy["doResolveForum"]) == EXPECTED_E_B
    assert "transact_land" not in set(legacy["doResolveForum"])


# ===========================================================================
# W4-A1b / DA-A1b-TB-01 — Stage R (RED only, product byte-locked)
#
# 设计基线：`EOR_W4_A1b_TB_失败原子性_确定实施方案_v1.1` §5.1–§5.4
# 写面：G4-W4A1b §2 F3（仅追加 T01–T14 + B3-CLOSE + 必要辅助）
# 产品零改动；本段先落盘并取得真实 RED。旧节点/断言逐字保留。
#
# 故障注入纪律：只包真实函数边——先让真实 add / insert / cursor 写落盘，再抛错；
# 不以 mock 返回值自证成功。
# ===========================================================================


def _tb(state, pid, receipt, ctx):
    return forum_api.start_forum_market_round(
        state, pid, market_receipt=receipt, caller_context=ctx)


def _hold(state, scope=None):
    return turn_service.forum_market_round_hold(state, scope or _scope(state))


def _hold_state(state, scope=None):
    hold = _hold(state, scope)
    return (hold or {}).get("state")


def _freeze(value):
    """Deterministic, comparable projection of ORIGINAL (non-DTO) facts."""
    if isinstance(value, dict):
        return tuple(sorted(((repr(k), _freeze(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(item) for item in value))
    try:
        hash(value)
        return value
    except Exception:  # noqa: BLE001
        return repr(value)


def _deep_snapshot(state):
    """R9 oracle: treasury / members / land / contracts / wars / phase result /
    init checkpoint + every independent RNG source (not a production DTO)."""
    import random
    members = []
    for mid in sorted(getattr(state, "_members", {})):
        fig = state._members[mid]
        members.append((
            mid, getattr(fig, "faction_id", None), getattr(fig, "is_dead", None),
            getattr(fig, "wealth", None), getattr(fig, "influence", None),
            getattr(fig, "_land_private", None), str(getattr(fig, "class_tier", None)),
            getattr(fig, "has_active_contract", None),
            getattr(fig, "is_faction_leader", None),
            getattr(fig, "_contract_id", None)))
    provinces = []
    for pid in sorted(getattr(state, "_provinces", {})):
        prov = state._provinces[pid]
        provinces.append((
            pid, getattr(prov, "land_public", None),
            getattr(prov, "_land_private", getattr(prov, "land_private", None)),
            getattr(prov, "conquered", None), getattr(prov, "grievance", None)))
    contracts = []
    for cid, contract in sorted(getattr(state, "_contracts_dict", {}).items()):
        contracts.append((
            cid, str(getattr(contract, "contract_type", None)),
            str(getattr(contract, "status", None)),
            getattr(contract, "province_id", None),
            getattr(contract, "base_cost", None),
            getattr(contract, "awarded_faction", None),
            getattr(contract, "remaining_years", None)))
    wars = []
    war_system = state.get_war_system()
    for war in (war_system.get_all_wars() if war_system else []):
        wars.append((
            str(getattr(war, "id", None)), str(getattr(war, "status", None)),
            getattr(war, "soldier_share", None),
            getattr(war, "triumph_commander_id", None),
            getattr(war, "triumph_approved", None)))
    return {
        "treasury": getattr(state, "_treasury", None),
        "national_public_land": getattr(state, "_national_public_land", None),
        "public_land_total": getattr(state, "_public_land_total", None),
        "turn": (getattr(getattr(state, "_turn", None), "turn_number", None),
                 getattr(getattr(state, "_turn", None), "year", None)),
        "members": tuple(members),
        "provinces": tuple(provinces),
        "contracts": tuple(contracts),
        "wars": tuple(wars),
        "phase_results": _freeze(getattr(state, "_phase_results", {})),
        "executed_phases": _freeze(getattr(state, "_executed_phases", set())),
        "forum_init_checkpoint": _freeze(getattr(state, "_forum_pending", {})),
        "population_checkpoint": _freeze(getattr(state, "_population_pending", {})),
        "senate_checkpoint": _freeze(getattr(state, "_senate_pending", {})),
        "resolution_settlement": _freeze(
            getattr(state, "_resolution_settlement", None)),
        "forum_war_events": _freeze(getattr(state, "_forum_war_events", [])),
        "forum_rebellion_events": _freeze(
            getattr(state, "_forum_rebellion_events", [])),
        "pending_land_acts": _freeze(getattr(state, "_pending_land_acts", [])),
        "pending_land_sale_quota": getattr(
            state, "_pending_land_sale_quota", None),
        "turn_land_sale_total": getattr(state, "_turn_land_sale_total", None),
        "takeover_pending": _freeze(getattr(state, "_takeover_pending", None)),
        "senate_package_ledger": _freeze(
            getattr(state, "_senate_package_ledger", {})),
        "war_execution_ledger": _freeze(
            getattr(state, "_war_execution_ledger", {})),
        "senate_finalization_ledger": _freeze(
            getattr(state, "_senate_finalization_ledger", {})),
        "heroes": _freeze(getattr(state, "_spawned_hero_ids", set())),
        "active_events": _freeze(getattr(state, "_active_events", {})),
        "hero_spawned_this_turn": getattr(state, "_hero_spawned_this_turn", None),
        "hero_to_spawn": _freeze(getattr(state, "_hero_to_spawn", None)),
        "current_player_id": getattr(state, "_current_player_id", None),
        "rng_global": random.getstate(),
        "rng_state_attr": repr(getattr(state, "_rng", None)),
    }


def _snapshot(state):
    import random
    return {
        "receipts": _receipts(state),
        "consumed": _consumed(state),
        "rounds": _rounds(state),
        "cursor": getattr(state.get_current_player(), "player_id", None),
        "business": _pending_digest(state),
        "deep": _deep_snapshot(state),
        "rng": random.getstate(),
    }


def _assert_conserved(before, after):
    assert after["receipts"] == before["receipts"], "receipt registry drifted"
    assert after["consumed"] == before["consumed"], "consumed set drifted"
    assert after["rounds"] == before["rounds"], "round registry drifted"
    assert after["cursor"] == before["cursor"], "cursor drifted"
    assert after["business"] == before["business"], "business tables drifted"
    assert after["deep"] == before["deep"], "deep business/init/RNG oracle drifted"
    assert after["rng"] == before["rng"], "RNG drifted"


def _assert_both_gates_closed(state, actor):
    pending = turn_service.forum_boundary_pending(state)
    assert pending is not None, "W1 gate must stay closed after a failure"
    assert pending["code"] == "FORUM_BOUNDARY_PENDING", pending
    mismatch = turn_service.market_obligation_matches(state, actor)
    assert mismatch is not None, "W2 gate must not admit an uncommitted round"
    assert mismatch["code"] == "FORUM_BOUNDARY_PENDING", mismatch


def _five_errors(state, pid, ctx):
    """Run the five G5 gameplay calls; return {name: (codes, success)}."""
    out = {}
    for name, call in _five_actions(state, pid, ctx):
        try:
            result = call()
            out[name] = (_errors(result), bool(result.get("success")))
        except Exception as exc:                     # noqa: BLE001 - probe only
            out[name] = ([type(exc).__name__], False)
    return out


def _assert_five_refused_by_fence(state, pid, ctx, label):
    observed = _five_errors(state, pid, ctx)
    for name, (codes, ok) in observed.items():
        assert ok is False, (label, name, codes)
        assert "FORUM_BOUNDARY_PENDING" in codes, (label, name, codes)


# ---------------------------------------------------------------------------
# T01 [consume.after_real_add.before_return] — consume 在提交段之外
# ---------------------------------------------------------------------------
def test_a1b_consume_after_real_add_before_return_raises_and_holds(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)
    before = _snapshot(state)

    real = turn_service.consume_forum_boundary_receipt
    seen = []

    def _wrapper(*args, **kwargs):
        result = real(*args, **kwargs)
        seen.append(result)
        assert receipt["receipt_id"] in _consumed(state), \
            "the real add must land before the injected failure"
        raise RuntimeError("injected: consume.after_real_add.before_return")

    monkeypatch.setattr(turn_service, "consume_forum_boundary_receipt", _wrapper)
    with pytest.raises(RuntimeError):
        _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    assert seen and seen[0].get("success"), seen
    after = _snapshot(state)
    assert _hold(state, scope) is not None, \
        "consume failure left NO decidable hold (consume is outside the segment)"
    assert _hold_state(state, scope) in ("RECOVERABLE_HOLD", "UNKNOWN_HOLD"), \
        _hold(state, scope)
    _assert_conserved(before, after)
    _assert_both_gates_closed(state, o)
    _assert_five_refused_by_fence(state, o, ctx, "T01")


# ---------------------------------------------------------------------------
# T02 [issuer.after_real_insert.before_return] — 预放 foreign receipt，禁 orphan
# ---------------------------------------------------------------------------
def test_a1b_boundary_issue_after_real_insert_before_return_raises_no_orphan(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    foreign = turn_service.issue_forum_boundary_receipt(
        state, command_id="test:foreign", kind="R_OPEN", scope_id="foreign-scope")
    scope = _scope(state)
    before = _snapshot(state)

    real = turn_service.issue_forum_boundary_receipt
    inserted = []

    def _wrapper(*args, **kwargs):
        if kwargs.get("kind") != turn_service.BOUNDARY_RECEIPT_BOUNDARY:
            return real(*args, **kwargs)
        result = real(*args, **kwargs)
        inserted.append(result)
        assert result["receipt_id"] in _receipts(state), \
            "the real registry insert must land before the injected failure"
        raise RuntimeError("injected: issuer.after_real_insert.before_return")

    monkeypatch.setattr(turn_service, "issue_forum_boundary_receipt", _wrapper)
    with pytest.raises(RuntimeError):
        _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    assert inserted, "boundary issuer was never exercised"
    after = _snapshot(state)
    assert inserted[0]["receipt_id"] not in _receipts(state), \
        "the really-inserted boundary receipt became an orphan"
    assert foreign["receipt_id"] in _receipts(state), "foreign receipt was deleted"
    assert _hold(state, scope) is not None
    assert _hold_state(state, scope) in ("RECOVERABLE_HOLD", "UNKNOWN_HOLD")
    _assert_conserved(before, after)
    _assert_both_gates_closed(state, o)


# ---------------------------------------------------------------------------
# T03 attempt 先于首效果可见 / 重入与旧 abort 不建第二效果
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edge", [
    "begin.before_install.raises",
    "begin.after_install.before_return.raises",
    "reenter.consume",
    "reenter.issuer",
    "reenter.finalize",
    "stale_abort.after_new_attempt_installed",
], ids=[
    "begin.before_install.raises",
    "begin.after_install.before_return.raises",
    "reenter.consume",
    "reenter.issuer",
    "reenter.finalize",
    "stale_abort.after_new_attempt_installed",
])
def test_a1b_attempt_is_visible_before_first_effect_and_blocks_reentrancy(
        monkeypatch, edge):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)
    before = _snapshot(state)

    if edge == "begin.before_install.raises":
        def _boom(*args, **kwargs):
            raise RuntimeError("injected: begin.before_install")
        monkeypatch.setattr(turn_service, "canonical_market_plan", _boom)
        with pytest.raises(RuntimeError):
            _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        _assert_conserved(before, _snapshot(state))
        assert _hold(state, scope) is None, "pre-install failure must not fabricate a hold"
        # 零 consume：同一 receipt 仍可正常提交
        assert _tb(state, o, receipt, ctx).get("success")
        return

    if edge == "begin.after_install.before_return.raises":
        real_begin = turn_service.begin_tb_attempt
        observed = []

        def _wrapper(*args, **kwargs):
            result = real_begin(*args, **kwargs)
            observed.append(turn_service.forum_boundary_pending(state))
            raise RuntimeError("injected: begin.after_install.before_return")

        monkeypatch.setattr(turn_service, "begin_tb_attempt", _wrapper)
        with pytest.raises(RuntimeError):
            _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        assert observed and observed[0] is not None, \
            "the attempt was NOT visible after the real atomic install"
        assert observed[0].get("reason") == "TB_PREPARING", observed[0]
        assert _hold(state, scope) is not None
        assert _hold_state(state, scope) in ("RECOVERABLE_HOLD", "UNKNOWN_HOLD")
        _assert_conserved(before, _snapshot(state))
        return

    if edge == "stale_abort.after_new_attempt_installed":
        stale_scope = scope
        _trig = _tb(state, o, receipt, ctx)
        assert _trig.get("success"), _trig
        rounds_before = _rounds(state)
        turn_service.abort_forum_market_round(
            state, scope_id=stale_scope,
            consumed_receipt=receipt["receipt_id"],
            boundary_receipt=_rounds(state)[stale_scope]["receipt_id"],
            previous_round=None, reason="stale-abort", actor=o)
        assert _rounds(state) == rounds_before, "old abort erased a COMMITTED round"
        assert state.get_current_player().player_id == o
        return

    # reenter.* : 在真实边内部重入同一 root，内层必须 pending/busy 且零第二效果
    target = {
        "reenter.consume": "consume_forum_boundary_receipt",
        "reenter.issuer": "issue_forum_boundary_receipt",
        "reenter.finalize": "finalize_tb_boundary",
    }[edge]
    real = getattr(turn_service, target)
    inner = []
    state_box = {"busy": False}

    def _wrapper(*args, **kwargs):
        if target == "issue_forum_boundary_receipt" and \
                kwargs.get("kind") != turn_service.BOUNDARY_RECEIPT_BOUNDARY:
            return real(*args, **kwargs)
        if state_box["busy"]:
            return real(*args, **kwargs)
        state_box["busy"] = True
        try:
            if not inner:
                receipts_now = _receipts(state)
                rounds_now = _rounds(state)
                inner.append(_tb(state, o, receipt, ctx))
                assert _receipts(state) == receipts_now, \
                    f"inner re-entry at {edge} created a second receipt"
                assert _rounds(state) == rounds_now, \
                    f"inner re-entry at {edge} created a second round"
        finally:
            state_box["busy"] = False
        return real(*args, **kwargs)

    monkeypatch.setattr(turn_service, target, _wrapper)
    outer = _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    assert inner, f"the injection edge {edge} was never reached"
    assert inner[0].get("success") is False, (edge, inner[0])
    assert outer.get("success"), (edge, outer)
    assert _hold(state, scope) is None


# ---------------------------------------------------------------------------
# T04 HOLD 先于 owner marker（两门）
# ---------------------------------------------------------------------------
def test_a1b_hold_precedes_owner_marker_in_both_gates(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    monkeypatch.setattr(state, "set_current_player", lambda *a, **k: False)
    failed = _tb(state, o, receipt, ctx)
    monkeypatch.undo()
    assert failed.get("success") is False, failed
    assert _hold(state, scope) is not None

    book = turn_service._book(state)
    marker_attr = "_forum_owner_initialization"
    previous = getattr(book, marker_attr, None)
    setattr(book, marker_attr, "open_market")
    try:
        _assert_both_gates_closed(state, o)
        _assert_five_refused_by_fence(state, o, ctx, "T04.marker+HOLD")
        for name in ("initialize_forum_turn", "generate_figures",
                     "generate_contracts", "check_province_unrest"):
            result = getattr(forum_api, name)(state, caller_context=ctx)
            assert result.get("success") is False, (name, result)
            assert "FORUM_BOUNDARY_PENDING" in _errors(result), (name, result)
    finally:
        setattr(book, marker_attr, previous)

    assert turn_service.forum_boundary_pending(state) is not None


# ---------------------------------------------------------------------------
# T04b HOLD matrix (4 fences x 2 markers x 3 round shapes) — HOLD precedes all
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fence", ["PREPARING", "RECOVERABLE_HOLD",
                                    "UNKNOWN_HOLD", "LEGACY_HOLD"])
@pytest.mark.parametrize("marker", ["absent", "truthy"])
@pytest.mark.parametrize("round_shape", ["absent", "provisional", "selected"])
def test_a1b_hold_matrix_precedes_marker_and_round(fence, marker, round_shape):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    scope = _scope(state)
    book = turn_service._book(state)
    holds = turn_service._market_round_holds(book)
    identity = turn_service.new_tb_attempt_identity(state)
    attempt_id = identity["attempt_id"]
    boundary_id = turn_service.new_tb_boundary_receipt_id()
    if fence == "LEGACY_HOLD":
        holds[scope] = {"state": "LEGACY_HOLD", "scope_id": scope}
    else:
        turn_service.begin_tb_attempt(
            state, scope_id=scope, actor=o, open_receipt_id="open-x",
            boundary_receipt_id=boundary_id, cursor_before=o,
            pre_round=None, attempt_id=attempt_id,
            generation=identity["generation"], pre_consumed=set())
        if fence == "RECOVERABLE_HOLD":
            turn_service.tb_finalize_failure(
                state, scope_id=scope, reason="matrix", unknown=False,
                attempt_id=attempt_id)
        elif fence == "UNKNOWN_HOLD":
            turn_service.tb_seal_unknown(
                state, scope, "matrix", attempt_id=attempt_id)
    setattr(book, turn_service._OWNER_INIT_ATTR,
            "open_market" if marker == "truthy" else None)
    if round_shape == "provisional":
        if fence == "LEGACY_HOLD":
            turn_service._market_round_registry(book)[scope] = {
                "state": turn_service.MARKET_ROUND_UNSELECTED,
                "receipt_id": boundary_id, "actor": o}
        else:
            turn_service.stage_round_for_attempt(
                state, scope_id=scope, attempt_id=attempt_id,
                boundary_receipt_id=boundary_id, actor=o)
    elif round_shape == "selected":
        turn_service.issue_forum_boundary_receipt(
            state, command_id="matrix", kind=turn_service.BOUNDARY_RECEIPT_BOUNDARY,
            scope_id=scope, actor=o, receipt_id=boundary_id)
        turn_service._market_round_registry(book)[scope] = {
            "state": turn_service.MARKET_ROUND_SELECTED,
            "receipt_id": boundary_id, "actor": o,
            "attempt_id": attempt_id, "finalized": True}
    try:
        pending = turn_service.forum_boundary_pending(state)
        mismatch = turn_service.market_obligation_matches(state, o)
        assert pending is not None and pending["code"] == "FORUM_BOUNDARY_PENDING", pending
        assert mismatch is not None and mismatch["code"] == "FORUM_BOUNDARY_PENDING", mismatch
        _assert_five_refused_by_fence(state, o, ctx, f"matrix.{fence}.{marker}.{round_shape}")
    finally:
        setattr(book, turn_service._OWNER_INIT_ATTR, None)


def test_a1b_w2_pending_no_round_is_closed_and_marker_is_pending_only():
    """R6/R5: pending+no-round is a REAL pending for W2 (never None), while the
    O_M marker exception remains reachable ONLY from the pending predicate."""
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    _finish_all(state, "retirement")
    _open_receipt(state)
    book = turn_service._book(state)
    setattr(book, turn_service._OWNER_INIT_ATTR, "open_market")
    try:
        assert turn_service.forum_boundary_pending(state) is None
        w2 = turn_service.market_obligation_matches(state, o)
        assert w2 is not None and w2["code"] == "FORUM_BOUNDARY_PENDING", w2
    finally:
        setattr(book, turn_service._OWNER_INIT_ATTR, None)
    pending = turn_service.forum_boundary_pending(state)
    assert pending is not None and pending["code"] == "FORUM_BOUNDARY_PENDING"
    w2 = turn_service.market_obligation_matches(state, o)
    assert w2 is not None and w2["code"] == "FORUM_BOUNDARY_PENDING", w2
    _land_pair(state, o)          # fixture normalisation BEFORE the oracle snapshot
    before = _snapshot(state)
    _assert_five_refused_by_fence(state, o, ctx, "w2.pending.no.round")
    assert _snapshot(state) == before


def test_a1b_w2_committed_l0_checks_initial_binding():
    """R7: W2 itself re-checks decision / committed / session-turn / initial
    binding — not only the duplicate R1 re-read."""
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)
    assert _tb(state, o, receipt, ctx).get("success")
    assert turn_service.market_obligation_matches(state, o) is None
    book = turn_service._book(state)
    attempt = turn_service._tb_attempt_registry(book)[scope]
    original = dict(attempt)
    mutations = [
        ("decision", "UNCOMMITTED"),
        ("session_id", "foreign-session"),
        ("turn", 10 ** 6),
        ("actor", "foreign-actor"),
        ("scope_id", "foreign-scope"),
        ("consumed_receipt_id", "foreign-open"),
    ]
    for field, value in mutations:
        attempt[field] = value
        w2 = turn_service.market_obligation_matches(state, o)
        assert w2 is not None and w2["code"] == "FORUM_BOUNDARY_STATE_INVALID", \
            (field, w2)
        pending = turn_service.forum_boundary_pending(state)
        assert pending is not None and pending["code"] == "FORUM_BOUNDARY_STATE_INVALID", \
            (field, pending)
        attempt.clear()
        attempt.update(original)
    assert turn_service.market_obligation_matches(state, o) is None


# ---------------------------------------------------------------------------
# T05 cursor 写前失败：严格守恒 + 可判 R
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edge", [
    "writer.setter_returns_false.before_write",
    "writer.setter_raises.before_write",
], ids=["writer.setter_returns_false.before_write",
        "writer.setter_raises.before_write"])
def test_a1b_failed_cursor_write_without_mutation_preserves_all_facts(
        monkeypatch, edge):
    # Legal controlled context: the cursor starts at P (so a real head write would
    # CHANGE it), while the market head is O. The guard passes for P, and the
    # independent cursor readback can therefore PROVE "no write" when it stays P.
    state = _session("gr_f_3h.json")
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, p)
    assert state.set_current_player(p)
    receipt = _market_window_open(state, p, ctx)
    scope = _scope(state)
    before = _snapshot(state)
    writes = []

    if edge == "writer.setter_returns_false.before_write":
        def _setter(pid, *a, **k):
            writes.append(pid)
            return False
    else:
        def _setter(pid, *a, **k):
            writes.append(pid)
            raise RuntimeError("injected: writer.setter_raises.before_write")

    monkeypatch.setattr(state, "set_current_player", _setter)
    if edge.endswith("returns_false.before_write"):
        failed = _tb(state, p, receipt, ctx)
    else:
        with pytest.raises(RuntimeError):
            _tb(state, p, receipt, ctx)
        failed = None
    monkeypatch.undo()

    if failed is not None:
        assert failed.get("success") is False, failed
    assert writes, "the sole writer was never invoked"
    after = _snapshot(state)
    _assert_conserved(before, after)
    assert _hold(state, scope) is not None
    assert _hold_state(state, scope) == "RECOVERABLE_HOLD", \
        f"a fully proven no-write failure must be RECOVERABLE, got {_hold(state, scope)}"
    _assert_both_gates_closed(state, o)
    # 同一 R 可重试且只发生一次真实选择
    retried = _tb(state, p, receipt, ctx)
    assert retried.get("success"), retried
    assert retried.get("data", {}).get("actor") == o, retried
    assert _hold(state, scope) is None


# ---------------------------------------------------------------------------
# T06 真实 cursor 写后日志异常 → UNKNOWN_HOLD（不得断言字节回滚）
# ---------------------------------------------------------------------------
def test_a1b_cursor_write_then_log_exception_is_unknown_hold(monkeypatch):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)
    # E4 (TA-W4A1b-02 A1): the fault is injected INSIDE the real setter, on its
    # own ``log_event`` edge — the first statement after the physical cursor
    # write — and never from a wrapper after the real setter returned.
    # ``set_current_player`` itself is NOT replaced, so the call that lands the
    # write is the product one.
    real_log_event = state.log_event
    log_edges = []

    def _log_then_raise(message, *a, **k):
        if str(message).startswith("设置当前玩家"):
            at_edge = getattr(state.get_current_player(), "player_id", None)
            log_edges.append((message, at_edge))
            raise RuntimeError(
                "injected: writer.real_cursor_write.then_log_raises")
        return real_log_event(message, *a, **k)

    monkeypatch.setattr(state, "log_event", _log_then_raise)
    with pytest.raises(RuntimeError):
        _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    assert log_edges, "the real setter's internal log_event edge was never reached"
    assert log_edges[0][1] == o, (
        "the physical cursor write must already be visible ON the log edge, "
        f"got {log_edges[0]}")
    current = state.get_current_player()
    assert getattr(current, "player_id", None) == o, "the real cursor write was reversed"
    hold = _hold(state, scope)
    assert hold is not None
    assert _hold_state(state, scope) == "UNKNOWN_HOLD", \
        f"a real post-write failure must be UNKNOWN_HOLD, got {hold}"
    _assert_both_gates_closed(state, o)
    _assert_five_refused_by_fence(state, o, ctx, "T06")
    # 明确不声称字节回滚
    assert hold.get("cursor_byte_rollback", "NOT_GUARANTEED") != "PASS"


# ---------------------------------------------------------------------------
# T07 暂态 round/boundary 不得授权 gameplay
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edge", [
    "probe.after_consume",
    "probe.after_provisional_boundary",
    "probe.after_provisional_round",
], ids=["probe.after_consume", "probe.after_provisional_boundary",
        "probe.after_provisional_round"])
def test_a1b_provisional_round_and_boundary_cannot_authorize_gameplay(
        monkeypatch, edge):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    if edge == "probe.after_consume":
        target = "consume_forum_boundary_receipt"
    elif edge == "probe.after_provisional_boundary":
        target = "issue_forum_boundary_receipt"
    else:
        target = "select_actor"

    real = getattr(turn_service, target)
    probes = []

    def _wrapper(*args, **kwargs):
        if target == "issue_forum_boundary_receipt" and \
                kwargs.get("kind") != turn_service.BOUNDARY_RECEIPT_BOUNDARY:
            return real(*args, **kwargs)
        if target == "select_actor":
            probes.append(_five_errors(state, o, ctx))
            return real(*args, **kwargs)
        result = real(*args, **kwargs)
        probes.append(_five_errors(state, o, ctx))
        return result

    monkeypatch.setattr(turn_service, target, _wrapper)
    started = _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    assert started.get("success"), started
    assert probes, f"edge {edge} never observed"
    for name, (codes, ok) in probes[0].items():
        assert ok is False, (edge, name, codes)
        assert "FORUM_BOUNDARY_PENDING" in codes, (edge, name, codes)
    assert _hold(state, scope) is None
    assert state.get_current_player().player_id == o


# ---------------------------------------------------------------------------
# T08 finalize/decision 前故障：R 或 U，按注入边锁定
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edge", [
    "round.after_provisional_write.before_writer.raises",
    "readback.head_mismatch.only",
    "readback.cursor_mismatch.only",
    "finalize.after_boundary_flag.before_round_write.raises",
    "finalize.after_both_writes.before_decision.raises",
], ids=[
    "round.after_provisional_write.before_writer.raises",
    "readback.head_mismatch.only",
    "readback.cursor_mismatch.only",
    "finalize.after_boundary_flag.before_round_write.raises",
    "finalize.after_both_writes.before_decision.raises",
])
def test_a1b_finalize_before_decision_fault_rolls_back_and_holds(monkeypatch, edge):
    # P cursor + P context is a legal guard-admissible fixture; the market head is
    # still O, so a real writer call CHANGES the cursor (independent proof).
    state = _session("gr_f_3h.json")
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, p)
    assert state.set_current_player(p)
    receipt = _market_window_open(state, p, ctx)
    scope = _scope(state)
    before = _snapshot(state)

    if edge == "round.after_provisional_write.before_writer.raises":
        def _boom(*args, **kwargs):
            raise RuntimeError("injected: round.after_provisional_write")
        monkeypatch.setattr(turn_service, "select_actor", _boom)
        with pytest.raises(RuntimeError):
            _tb(state, p, receipt, ctx)
        monkeypatch.undo()
        _assert_conserved(before, _snapshot(state))
        assert _hold_state(state, scope) == "RECOVERABLE_HOLD", _hold(state, scope)
        _assert_both_gates_closed(state, o)
        return

    if edge == "readback.head_mismatch.only":
        real = turn_service.select_actor

        def _mismatch(*args, **kwargs):
            real(*args, **kwargs)
            return {"success": True, "actor": "not-the-canonical-head"}

        monkeypatch.setattr(turn_service, "select_actor", _mismatch)
        failed = _tb(state, p, receipt, ctx)
        monkeypatch.undo()
        assert failed.get("success") is False, failed
        assert "HEAD_READBACK_MISMATCH" in _errors(failed), failed
        assert _hold_state(state, scope) == "UNKNOWN_HOLD", _hold(state, scope)
        _assert_both_gates_closed(state, o)
        return

    if edge == "readback.cursor_mismatch.only":
        # R10 legal construction: O cursor + O context pass the guard; the REAL
        # select runs; only the subsequent Core cursor READBACK lies. The real
        # getter (captured before the lie) is the independent oracle.
        state = _session()
        o = _faction_player(state, "optimates")
        ctx = _registered(state, o)
        receipt = _market_window_open(state, o, ctx)
        scope = _scope(state)
        real_get = state.get_current_player
        real_select = turn_service.select_actor

        class _Liar:
            player_id = "injected-cursor-value"

        def _select_then_lie(*args, **kwargs):
            result = real_select(*args, **kwargs)
            monkeypatch.setattr(state, "get_current_player",
                                lambda *a, **k: _Liar())
            return result

        monkeypatch.setattr(turn_service, "select_actor", _select_then_lie)
        failed = _tb(state, o, receipt, ctx)
        observed_injected = state.get_current_player().player_id
        real_value = real_get().player_id
        monkeypatch.undo()
        assert failed.get("success") is False, failed
        assert "CURSOR_READBACK_MISMATCH" in _errors(failed), failed
        assert observed_injected == "injected-cursor-value"
        assert real_value == o, "the REAL Core cursor was not the canonical head"
        assert state.get_current_player().player_id == o
        assert _hold_state(state, scope) == "UNKNOWN_HOLD", _hold(state, scope)
        _assert_both_gates_closed(state, o)
        return

    if edge == "finalize.after_boundary_flag.before_round_write.raises":
        def _round_boom(*args, **kwargs):
            raise RuntimeError(
                "injected: finalize.after_boundary_flag.before_round_write")
        monkeypatch.setattr(turn_service, "_tb_write_round_finalized", _round_boom)
        with pytest.raises(RuntimeError):
            _tb(state, p, receipt, ctx)
        monkeypatch.undo()
        hold = _hold(state, scope)
        assert hold is not None and hold.get("state") == "UNKNOWN_HOLD", hold
        assert state.get_current_player().player_id == o, "the real writer did not run"
        assert _rounds(state).get(scope) is None, \
            "the provisional round was not compensated"
        finalized = getattr(turn_service._book(state),
                            turn_service._BOUNDARY_FINALIZED_ATTR, set()) or set()
        assert finalized, "the physical boundary flag write did not happen"
        _assert_both_gates_closed(state, o)
        return

    # finalize.after_both_writes.before_decision.raises
    real_finalize = turn_service.finalize_tb_boundary

    def _finish_then_raise(*args, **kwargs):
        real_finalize(*args, **kwargs)
        raise RuntimeError("injected: finalize.after_both_writes.before_decision")

    monkeypatch.setattr(turn_service, "finalize_tb_boundary", _finish_then_raise)
    with pytest.raises(RuntimeError):
        _tb(state, p, receipt, ctx)
    monkeypatch.undo()
    assert state.get_current_player().player_id == o, "the real writer did not run"
    hold = _hold(state, scope)
    assert hold is not None and hold.get("state") == "UNKNOWN_HOLD", hold
    finalized = getattr(turn_service._book(state),
                        turn_service._BOUNDARY_FINALIZED_ATTR, set()) or set()
    assert finalized, "both physical finalize writes must have happened"
    assert _rounds(state).get(scope) is None, \
        "the provisional round was not compensated"
    _assert_both_gates_closed(state, o)


# ---------------------------------------------------------------------------
# T09 COMMITTED 不可降级；重复只读
# ---------------------------------------------------------------------------
def _assert_committed_initial_bound(state, receipt, scope):
    assert _hold(state, scope) is None, \
        "a COMMITTED decision was downgraded into a HOLD"
    record = _rounds(state).get(scope)
    assert record is not None and record.get("state") == turn_service.MARKET_ROUND_SELECTED, \
        f"the commit was rolled back: {record}"
    committed_receipt = _receipts(state).get(record.get("receipt_id"))
    assert committed_receipt is not None, "the committed boundary receipt was deleted"
    assert receipt["receipt_id"] in _consumed(state)
    attempt = turn_service._tb_attempt_registry(turn_service._book(state)).get(scope)
    assert attempt is not None
    assert attempt.get("decision") == turn_service.TB_DECISION_COMMITTED, attempt
    assert attempt.get("session_id") == turn_service._session_ns(state)
    assert int(attempt.get("turn", -1)) == int(turn_service._book(state).turn_number)
    assert attempt.get("scope_id") == scope
    assert attempt.get("receipt_id") == record.get("receipt_id")
    return record


@pytest.mark.parametrize("edge", [
    "commit.before_decision_write.raises",
    "commit.after_real_decision_write.before_return.raises",
    "response.after_commit.build_raises",
    "response.after_commit.serialize_raises",
    "live.after_real_O_finish.P_current.reread",
    "live.after_real_P_finish.E_current.reread",
], ids=[
    "commit.before_decision_write.raises",
    "commit.after_real_decision_write.before_return.raises",
    "response.after_commit.build_raises",
    "response.after_commit.serialize_raises",
    "live.after_real_O_finish.P_current.reread",
    "live.after_real_P_finish.E_current.reread",
])
def test_a1b_committed_then_response_raises_duplicate_is_readonly(monkeypatch, edge):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    if edge.startswith("commit."):
        real_leaf = turn_service._tb_apply_committed_decision
        if edge == "commit.before_decision_write.raises":
            def _leaf(*args, **kwargs):
                raise RuntimeError("injected: commit.before_decision_write")
        else:
            def _leaf(*args, **kwargs):
                real_leaf(*args, **kwargs)
                raise RuntimeError(
                    "injected: commit.after_real_decision_write.before_return")
        monkeypatch.setattr(turn_service, "_tb_apply_committed_decision", _leaf)
        with pytest.raises(RuntimeError):
            _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        if edge == "commit.before_decision_write.raises":
            hold = _hold(state, scope)
            assert hold is not None and hold.get("state") == "UNKNOWN_HOLD", hold
            assert _rounds(state).get(scope) is None, \
                "a pre-decision commit failure left a SELECTED round"
            assert state.get_current_player().player_id == o, \
                "the real writer effect must be recorded, not reversed"
            _assert_both_gates_closed(state, o)
            return
        record = _assert_committed_initial_bound(state, receipt, scope)
        snapshot = _snapshot(state)
        writes = []
        original = state.set_current_player
        monkeypatch.setattr(state, "set_current_player",
                            lambda pid: (writes.append(pid), original(pid))[1])
        again = _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        assert again.get("success"), again
        assert writes == [], "duplicate T_B wrote the cursor again"
        assert again["data"]["boundary_receipt"]["receipt_id"] == record["receipt_id"]
        assert _snapshot(state) == snapshot, "duplicate T_B changed committed facts"
        return

    if edge.startswith("response."):
        real_resp = forum_api.api_response
        if edge == "response.after_commit.build_raises":
            def _resp(success, message="", data=None, **kwargs):
                if message == "Market round started":
                    raise RuntimeError("injected: response.build_raises")
                return real_resp(success, message, data, **kwargs)
            monkeypatch.setattr(forum_api, "api_response", _resp)
            with pytest.raises(RuntimeError):
                _tb(state, o, receipt, ctx)
            monkeypatch.undo()
        else:
            def _resp(success, message="", data=None, **kwargs):
                if message == "Market round started":
                    return {"success": True,
                            "data": {"not_serializable": object()}}
                return real_resp(success, message, data, **kwargs)
            monkeypatch.setattr(forum_api, "api_response", _resp)
            result = _tb(state, o, receipt, ctx)
            monkeypatch.undo()
            with pytest.raises(TypeError):
                json.dumps(result)
        _assert_committed_initial_bound(state, receipt, scope)
        return

    # ---- live progression: real owner finish -> existing continuation -> reread --
    first = _tb(state, o, receipt, ctx)
    assert first.get("success"), first
    initial_receipt = first["data"]["boundary_receipt"]["receipt_id"]
    assert _finish(state, o, "market").get("success")
    p = _faction_player(state, "populares")
    stepped = turn_service.select_actor(state, scope)
    assert stepped.get("success"), stepped
    assert stepped.get("actor") == p, stepped
    # L1 is the LIVE obligation oracle: P is admitted, the initial actor O is not.
    assert turn_service.market_obligation_matches(state, p) is None
    assert (turn_service.market_obligation_matches(state, o) or {}).get("code") \
        == "MARKET_OBLIGATION_MISMATCH"
    # The duplicate R1 uses the registered O principal (controlled context) but the
    # committed re-read must return the ORIGINAL binding, never select the live P.
    assert state.set_current_player(o)
    again_p = _tb(state, o, receipt, ctx)
    assert again_p.get("success"), again_p
    assert again_p["data"]["actor"] == o, \
        "the reread selected the LIVE head instead of the initial receipt"
    assert again_p["data"]["boundary_receipt"]["receipt_id"] == initial_receipt
    assert state.get_current_player().player_id == o, \
        "the readonly reread performed a new selection"
    if edge == "live.after_real_O_finish.P_current.reread":
        return
    assert _finish(state, p, "market").get("success")
    e = _faction_player(state, "equites")
    stepped = turn_service.select_actor(state, scope)
    assert stepped.get("success"), stepped
    assert stepped.get("actor") == e, stepped
    assert turn_service.market_obligation_matches(state, e) is None
    assert (turn_service.market_obligation_matches(state, p) or {}).get("code") \
        == "MARKET_OBLIGATION_MISMATCH"
    assert state.set_current_player(o)
    again_e = _tb(state, o, receipt, ctx)
    assert again_e.get("success"), again_e
    assert again_e["data"]["actor"] == o
    assert again_e["data"]["boundary_receipt"]["receipt_id"] == initial_receipt
    assert state.get_current_player().player_id == o


# ---------------------------------------------------------------------------
# T10 无效/陈旧 OPEN receipt：零 attempt、零效果
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", [
    "wrong_session", "wrong_scope", "wrong_turn", "wrong_revision",
    "already_consumed", "forged_id", "wrong_kind",
], ids=["wrong_session", "wrong_scope", "wrong_turn", "wrong_revision",
        "already_consumed", "forged_id", "wrong_kind"])
def test_a1b_invalid_or_stale_open_receipt_creates_no_attempt_or_effect(case):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    presented = dict(receipt)
    if case == "wrong_session":
        presented["session_id"] = "foreign-session"
    elif case == "wrong_scope":
        presented["scope_id"] = "foreign-scope"
    elif case == "wrong_turn":
        presented["turn"] = 10 ** 6
    elif case == "wrong_revision":
        presented["core_revision"] = 10 ** 6
        presented["revision"] = 10 ** 6
    elif case == "already_consumed":
        consumed = turn_service.consume_forum_boundary_receipt(
            state, receipt, scope_id=scope, kind=turn_service.BOUNDARY_RECEIPT_OPEN)
        assert consumed.get("success"), consumed
    elif case == "forged_id":
        presented["receipt_id"] = "forged-receipt-id"
    elif case == "wrong_kind":
        presented["kind"] = turn_service.BOUNDARY_RECEIPT_BOUNDARY

    before = _snapshot(state)
    result = _tb(state, o, presented, ctx)
    after = _snapshot(state)

    assert result.get("success") is False, (case, result)
    codes = _errors(result)
    assert codes, (case, result)
    assert set(codes) <= set(BOUNDARY_CODES) | {"DENIED"}, (case, codes)
    assert after["rounds"] == before["rounds"], (case, after["rounds"])
    assert after["receipts"] == before["receipts"], case
    assert after["consumed"] == before["consumed"], case
    assert after["cursor"] == before["cursor"], case
    assert after["business"] == before["business"], case
    assert _hold(state, scope) is None, (case, _hold(state, scope))


# ---------------------------------------------------------------------------
# T11 补偿异常不得抹掉围栏 / 不得回落 legacy
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edge", [
    "abort.entry_wrapper.before_body.raises",
    "abort.after_unknown_fence.before_compensation.raises",
    "abort.after_boundary_remove.raises",
    "abort.after_consumed_restore.raises",
    "abort.after_round_restore.before_proof.raises",
    "abort.ownership_conflict",
], ids=["abort.entry_wrapper.before_body.raises",
        "abort.after_unknown_fence.before_compensation.raises",
        "abort.after_boundary_remove.raises",
        "abort.after_consumed_restore.raises",
        "abort.after_round_restore.before_proof.raises",
        "abort.ownership_conflict"])
def test_a1b_rollback_exception_cannot_erase_hold_or_fall_back_legacy(
        monkeypatch, edge):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    real_abort = turn_service.abort_forum_market_round

    if edge == "abort.entry_wrapper.before_body.raises":
        def _abort(*args, **kwargs):
            raise RuntimeError("injected: abort.entry_wrapper")
        monkeypatch.setattr(turn_service, "abort_forum_market_round", _abort)
    elif edge == "abort.ownership_conflict":
        def _abort(*args, **kwargs):
            kwargs["scope_id"] = "foreign-scope"
            return real_abort(*args, **kwargs)
        monkeypatch.setattr(turn_service, "abort_forum_market_round", _abort)
    elif edge == "abort.after_consumed_restore.raises":
        real_helper = turn_service._tb_abort_restore_consumed

        def _helper(*args, **kwargs):
            real_helper(*args, **kwargs)
            raise RuntimeError("injected: abort.after_consumed_restore")
        monkeypatch.setattr(turn_service, "_tb_abort_restore_consumed", _helper)
    elif edge == "abort.after_round_restore.before_proof.raises":
        real_helper = turn_service._tb_abort_restore_round

        def _helper(*args, **kwargs):
            real_helper(*args, **kwargs)
            raise RuntimeError("injected: abort.after_round_restore.before_proof")
        monkeypatch.setattr(turn_service, "_tb_abort_restore_round", _helper)
    elif edge == "abort.after_unknown_fence.before_compensation.raises":
        # E4 (TA-W4A1b-02 A2): stop ON the first compensation leaf's entry — the
        # UNKNOWN fence is already sealed and NO compensation leaf has run yet.
        def _no_compensation(*args, **kwargs):
            raise RuntimeError(
                "injected: abort.after_unknown_fence.before_compensation")
        monkeypatch.setattr(turn_service, "_tb_abort_remove_boundary",
                            _no_compensation)
    else:
        # E4 (TA-W4A1b-02 A2): ``abort.after_boundary_remove`` — the FIRST
        # compensation leaf really runs (the boundary receipt leaves the
        # registry), then the fault stops the compensation chain at that step.
        real_remove = turn_service._tb_abort_remove_boundary

        def _remove_then_raise(*args, **kwargs):
            real_remove(*args, **kwargs)
            raise RuntimeError("injected: abort.after_boundary_remove")
        monkeypatch.setattr(turn_service, "_tb_abort_remove_boundary",
                            _remove_then_raise)

    monkeypatch.setattr(turn_service, "select_actor",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("writer failed")))
    with pytest.raises(Exception):                          # noqa: B017 - injection
        _tb(state, o, receipt, ctx)
    monkeypatch.undo()

    hold = _hold(state, scope)
    assert hold is not None, \
        f"{edge}: the fence disappeared when the compensation itself failed"
    assert _hold_state(state, scope) == "UNKNOWN_HOLD", hold
    _assert_both_gates_closed(state, o)
    _assert_five_refused_by_fence(state, o, ctx, f"T11.{edge}")


# ---------------------------------------------------------------------------
# T12 RECOVERABLE_HOLD 重试：窗口关闭到新 COMMIT
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", [
    "retry.probe.begin",
    "retry.probe.consume",
    "retry.probe.issuer",
    "retry.probe.round",
    "retry.probe.readback",
    "retry.probe.finalize",
    "retry.stale_old_abort.after_new_install",
    "retry.stale_old_abort.after_new_commit",
    "retry.stale_old_commit",
    "retry.stale_admission.denied",
], ids=[
    "retry.probe.begin", "retry.probe.consume", "retry.probe.issuer",
    "retry.probe.round", "retry.probe.readback", "retry.probe.finalize",
    "retry.stale_old_abort.after_new_install",
    "retry.stale_old_abort.after_new_commit",
    "retry.stale_old_commit", "retry.stale_admission.denied",
])
def test_a1b_recoverable_hold_retry_keeps_window_closed_until_commit(
        monkeypatch, case):
    state = _session()
    o = _faction_player(state, "optimates")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    scope = _scope(state)

    monkeypatch.setattr(state, "set_current_player", lambda *a, **k: False)
    first = _tb(state, o, receipt, ctx)
    monkeypatch.undo()
    assert first.get("success") is False
    hold = _hold(state, scope)
    assert hold is not None, "no recoverable hold to retry from"
    old_id = hold.get("attempt_id")
    assert old_id
    assert turn_service.forum_boundary_pending(state) is not None

    if case == "retry.stale_admission.denied":
        turn_service._book(state).revision_counter += 1
        denied = _tb(state, o, receipt, ctx)
        assert denied.get("success") is False, denied
        after = _hold(state, scope)
        assert after is not None and after.get("attempt_id") == old_id, after
        assert after.get("state") == "RECOVERABLE_HOLD", after
        return

    observed = []
    target_map = {
        "retry.probe.begin": "begin_tb_attempt",
        "retry.probe.consume": "consume_forum_boundary_receipt",
        "retry.probe.issuer": "issue_forum_boundary_receipt",
        "retry.probe.round": "stage_round_for_attempt",
        "retry.probe.readback": "_tb_verify_cursor_readback",
        "retry.probe.finalize": "finalize_tb_boundary",
    }

    if case in target_map:
        target = target_map[case]
        real = getattr(turn_service, target)

        def _wrapper(*args, **kwargs):
            if target == "issue_forum_boundary_receipt" and \
                    kwargs.get("kind") != turn_service.BOUNDARY_RECEIPT_BOUNDARY:
                return real(*args, **kwargs)
            before_hold = _hold(state, scope)
            observed.append(before_hold)
            result = real(*args, **kwargs)
            if target == "begin_tb_attempt":
                observed[-1] = _hold(state, scope)
            return result

        monkeypatch.setattr(turn_service, target, _wrapper)
        retried = _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        assert retried.get("success"), retried
        assert observed, f"retry never reached {case}"
        probe = observed[0]
        assert probe is not None
        assert probe.get("state") == "TB_PREPARING", \
            f"retry did not install the new PREPARING before {case}: {probe}"
        assert probe.get("attempt_id") != old_id
    elif case == "retry.stale_old_abort.after_new_install":
        real = turn_service.consume_forum_boundary_receipt

        def _wrapper(*args, **kwargs):
            stale = turn_service.abort_forum_market_round(
                state, scope_id=scope, attempt_id=old_id,
                reason="stale-old-abort", actor=o)
            assert stale.get("refused"), stale
            observed.append(_hold(state, scope))
            return real(*args, **kwargs)

        monkeypatch.setattr(turn_service, "consume_forum_boundary_receipt", _wrapper)
        retried = _tb(state, o, receipt, ctx)
        monkeypatch.undo()
        assert retried.get("success"), retried
        assert observed and observed[0].get("state") == "TB_PREPARING"
        assert observed[0].get("attempt_id") != old_id
    else:
        retried = _tb(state, o, receipt, ctx)
        assert retried.get("success"), retried
        rounds_before = _rounds(state)
        committed = _rounds(state)[scope]
        if case == "retry.stale_old_abort.after_new_commit":
            stale = turn_service.abort_forum_market_round(
                state, scope_id=scope, attempt_id=old_id,
                consumed_receipt=receipt["receipt_id"],
                boundary_receipt=committed["receipt_id"],
                previous_round=None, reason="stale", actor=o)
            assert stale.get("refused"), stale
        else:  # retry.stale_old_commit
            stale = turn_service.tb_commit_attempt(
                state, scope_id=scope,
                boundary_receipt_id=committed["receipt_id"],
                actor=o, attempt_id=old_id)
            assert stale.get("success") is False, stale
        assert _rounds(state) == rounds_before, "a stale callback changed the new C"

    assert _hold(state, scope) is None
    assert state.get_current_player().player_id == o


# ---------------------------------------------------------------------------
# T13 市场 head 与退休 cursor 不同源（尾席 E → 市场 O）
# ---------------------------------------------------------------------------
def test_a1b_market_head_differs_from_retirement_cursor():
    state = _session()
    o = _faction_player(state, "optimates")
    e = _faction_player(state, "equites")
    ctx = _registered(state, o)

    # 真实退休链：O → P 完成后，cursor 必落在尾席 E（最后未完成的退休义务）
    p = _faction_player(state, "populares")
    assert _finish(state, o, "retirement").get("success")
    advanced = turn_service.select_actor(state, _scope(state))
    assert advanced.get("success"), advanced
    assert advanced.get("actor") == p, advanced
    assert _finish(state, p, "retirement").get("success")
    advanced = turn_service.select_actor(state, _scope(state))
    assert advanced.get("success"), advanced
    assert advanced.get("actor") == e, advanced
    retirement_tail = state.get_current_player().player_id
    assert retirement_tail == e, \
        ("the retirement cursor never reaches the real tail seat E "
         f"(stays at {retirement_tail}); market head and retirement cursor "
         "are not independently evidenced")
    assert _finish(state, e, "retirement").get("success")
    # 退休义务全部完成后，continuation 的唯一 cursor writer 把席位交给市场首席 O。
    advanced = turn_service.select_actor(state, _scope(state))
    assert advanced.get("success"), advanced
    assert advanced.get("actor") == o, advanced

    opened = forum_api.open_market(state, o, caller_context=ctx)
    assert opened.get("success"), opened
    receipt = _open_receipt(state)
    plan = turn_service.canonical_market_plan(state)
    assert plan.get("success"), plan
    assert plan["head"].actor_player_id == o, plan["head"]

    started = _tb(state, o, receipt, ctx)
    assert started.get("success"), started
    assert started["data"]["actor"] == o
    assert state.get_current_player().player_id == o
    assert _hold(state, _scope(state)) is None


# ---------------------------------------------------------------------------
# T14 跨 session / scope / epoch 不得恢复旧 attempt
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case", [
    "cross.two_real_sessions.foreign_receipt",
    "cross.two_real_sessions.old_abort",
    "epoch.old_admission.late_root",
], ids=["cross.two_real_sessions.foreign_receipt",
        "cross.two_real_sessions.old_abort",
        "epoch.old_admission.late_root"])
def test_a1b_scope_turn_and_old_epoch_cannot_resume_old_attempt(case):
    state_a = _session()
    o_a = _faction_player(state_a, "optimates")
    ctx_a = _registered(state_a, o_a)
    receipt_a = _market_window_open(state_a, o_a, ctx_a)

    state_b = _session()
    o_b = _faction_player(state_b, "optimates")
    ctx_b = _registered(state_b, o_b)
    receipt_b = _market_window_open(state_b, o_b, ctx_b)
    scope_b = _scope(state_b)
    before_b = _snapshot(state_b)

    if case == "cross.two_real_sessions.foreign_receipt":
        result = _tb(state_b, o_b, receipt_a, ctx_b)
        assert result.get("success") is False, result
        assert _errors(result), result
        assert _snapshot(state_b) == before_b
        assert _hold(state_b, scope_b) is None
        return

    if case == "cross.two_real_sessions.old_abort":
        started = _tb(state_b, o_b, receipt_b, ctx_b)
        assert started.get("success"), started
        rounds_before = _rounds(state_b)
        turn_service.abort_forum_market_round(
            state_b, scope_id=_scope(state_a),
            consumed_receipt=receipt_a["receipt_id"],
            boundary_receipt=None, previous_round=None,
            reason="cross-session", actor=o_a)
        assert _rounds(state_b) == rounds_before, "foreign abort touched this session"
        assert state_b.get_current_player().player_id == o_b
        return

    # epoch.old_admission.late_root：旧 revision 的 receipt 不得重开窗口
    state_c = _session()
    o_c = _faction_player(state_c, "optimates")
    ctx_c = _registered(state_c, o_c)
    receipt_c = _market_window_open(state_c, o_c, ctx_c)
    turn_service._book(state_c).revision_counter += 1
    before_c = _snapshot(state_c)
    result = _tb(state_c, o_c, receipt_c, ctx_c)
    assert result.get("success") is False, result
    assert _snapshot(state_c) == before_c


# ---------------------------------------------------------------------------
# B3-CLOSE (AC05) — 五动作 W1 / W2 / 非首席 三联
# ---------------------------------------------------------------------------
def _b3_session():
    state = _session("gr_f_3h.json")
    o = _faction_player(state, "optimates")
    p = _faction_player(state, "populares")
    ctx = _registered(state, o)
    receipt = _market_window_open(state, o, ctx)
    return state, o, p, ctx, receipt


def _b3_w2_effect(state, action, pid, ctx):
    if action == "recruit_figure":
        _b3_ensure_recruitment_vacancy(state, pid, ctx)
        figure_id = _business_ids(state)["figure_id"]
        before = list(state.get_forum_pending().get("recruitment_bids", []))
        result = forum_api.recruit_figure(state, pid, figure_id, 5,
                                          caller_context=ctx)
        after = list(state.get_forum_pending().get("recruitment_bids", []))
        return result, len(after) == len(before) + 1, "recruitment_bids"
    if action == "transact_land":
        before = list(state.get_forum_pending().get("land_trades", []))
        result = forum_api.transact_land(
            state, pid, **_land_pair_kwargs(state, pid), caller_context=ctx)
        after = list(state.get_forum_pending().get("land_trades", []))
        return result, len(after) == len(before) + 1, "land_trades"
    if action == "place_bid":
        contract = _b3_budgeted_contract(state)
        knight = _b3_faction_member(state, pid, eques=True)
        before = list(state.get_forum_pending().get("contract_bids", []))
        result = forum_api.place_bid(state, pid, knight.id,
                                     contract.id, contract.base_cost,
                                     caller_context=ctx)
        after = list(state.get_forum_pending().get("contract_bids", []))
        return result, len(after) == len(before) + 1, "contract_bids"
    if action == "buy_land":
        _b3_prepare_land_sale(state, pid)
        buyer = _b3_faction_member(state, pid)
        before = list(state.get_forum_pending().get("land_purchases", []))
        result = forum_api.buy_land(state, pid, buyer.id, 1,
                                    caller_context=ctx)
        after = list(state.get_forum_pending().get("land_purchases", []))
        return result, len(after) == len(before) + 1, "land_purchases"
    war = _b3_eligible_war(state, pid)
    before = list(state.get_forum_pending().get("triumph_votes", []))
    result = forum_api.vote_triumph(state, pid, war.id, True,
                                    caller_context=ctx)
    after = list(state.get_forum_pending().get("triumph_votes", []))
    return result, len(after) == len(before) + 1, "triumph_votes"


def _b3_faction_member(state, pid, *, eques=False):
    """真实派系成员（仅选存活/在派系者）；骑士项按 ClassTier 过滤。"""
    player = state.get_player(pid)
    faction = state.get_faction(player.faction_id)
    members = [m for m in faction.get_members(state) if not m.is_dead]
    if eques:
        members = [m for m in members if m.class_tier == ClassTier.EQUES]
    assert members, ("B3_W2_PRECONDITION_UNMET: no eligible faction member",
                     pid, eques)
    return members[0]


def _b3_ensure_recruitment_vacancy(state, pid, ctx):
    """用真实 retire_figure 公开入口腾出物理空位（派系满员时）。"""
    player = state.get_player(pid)
    faction_id = player.faction_id
    if state.get_remaining_recruitment_slots(faction_id) > 0:
        return
    faction = state.get_faction(faction_id)
    candidates = [m for m in faction.get_members(state)
                  if not m.is_faction_leader and not m.has_active_contract]
    assert candidates, ("B3_W2_PRECONDITION_UNMET: full faction has no "
                        "retirable non-leader member", faction_id)
    retired = forum_api.retire_figure(
        state, pid, candidates[-1].id, caller_context=ctx)
    assert retired.get("success"), retired
    assert state.get_remaining_recruitment_slots(faction_id) > 0


def _b3_budgeted_contract(state):
    """真实 Core create_contract 工厂 + BUDGETED 状态（Senate 批准后的持久态）。"""
    contract = state.create_contract(
        ContractType.TAX_FARMING, 0, 10, state.turn.turn_number)
    contract.name = "TB02 budgeted tax"
    contract.duration_years = 5
    contract.status = ContractStatus.BUDGETED
    return contract


def _b3_prepare_land_sale(state, pid):
    """真实 GameState setter（political_system 卖地法案通过后的同一写点）。"""
    if int(getattr(state, "pending_land_sale_quota", 0) or 0) <= 0:
        state.set_pending_land_sale_quota(10)
    buyer = _b3_faction_member(state, pid)
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    if buyer.wealth < land_price:
        buyer.wealth = land_price


def _b3_eligible_war(state, pid):
    """真实 War 实体 + 既有测试 factory（make_war/attach_active）。"""
    war_system = state.get_war_system()
    for war in war_system.get_all_wars():
        if (war.status == WarStatus.RESOLVED and war.soldier_share > 0
                and war.triumph_commander_id is not None):
            commander = state.get_member(war.triumph_commander_id)
            if commander is not None and not commander.is_dead:
                return war
    commander = _b3_faction_member(state, pid)
    war = make_war(war_id="tb02-triumph-war", name="TB02 Triumph War",
                   status=WarStatus.RESOLVED, commander_id=commander.id)
    war._soldier_share = 10
    war._triumph_commander_id = commander.id
    attach_active(state, war)
    return war


@pytest.mark.parametrize("action", [
    "recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land",
], ids=["recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land"])
def test_a1b_b3_close_w1_all_five_pending_zero_write(action):
    state, o, _p, ctx, _receipt = _b3_session()
    before = _snapshot(state)
    ids = _business_ids(state)
    call = dict(_five_actions(state, o, ctx))[action]()
    assert call.get("success") is False, (action, call)
    assert "FORUM_BOUNDARY_PENDING" in _errors(call), (action, call)
    after = _snapshot(state)
    assert after["receipts"] == before["receipts"], action
    assert after["consumed"] == before["consumed"], action
    assert after["rounds"] == before["rounds"], action
    assert after["cursor"] == before["cursor"], action
    assert after["business"] == before["business"], action
    assert ids  # fixture sanity


@pytest.mark.parametrize("action", [
    "recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land",
], ids=["recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land"])
def test_a1b_b3_close_w2_scheduled_real_effect(action):
    state, o, _p, ctx, receipt = _b3_session()
    started = _tb(state, o, receipt, ctx)
    assert started.get("success"), started
    assert state.get_current_player().player_id == o
    result, exact_one, table = _b3_w2_effect(state, action, o, ctx)
    assert result.get("success") is True, (action, table, result)
    assert exact_one, (action, table, "expected exactly one new row")
    assert _hold(state, _scope(state)) is None


@pytest.mark.parametrize("action", [
    "recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land",
], ids=["recruit_figure", "place_bid", "buy_land", "vote_triumph", "transact_land"])
def test_a1b_b3_close_non_head_all_five_mismatch(action):
    state, o, p, _ctx, receipt = _b3_session()
    started = _tb(state, o, receipt, _ctx)
    assert started.get("success"), started
    ctx_p = _registered(state, p)
    assert state.set_current_player(p)
    before = _snapshot(state)
    call = dict(_five_actions(state, p, ctx_p))[action]()
    assert call.get("success") is False, (action, call)
    assert "MARKET_OBLIGATION_MISMATCH" in _errors(call), (action, call)
    after = _snapshot(state)
    assert after["receipts"] == before["receipts"], action
    assert after["consumed"] == before["consumed"], action
    assert after["rounds"] == before["rounds"], action
    assert after["business"] == before["business"], action
