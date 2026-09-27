# src/tests/test_core/test_wpo_commander_persistence.py
"""WP-O Slice O-S1 — 纠正态持久化连续 + 身份域区分（T06a / T06c-history）。

真实链：真实 Mortality 生产者 → 纠正态 → `GameState.to_dict` → fresh `load_from_dict`
→ raw 权威事实仍为空（不复活死者）。禁手搓 DTO mock。

T06b（TRUCE pending → 重入 production chain）与 T06c 的 fault-rollback 分支属 O-S3；
本切片仅覆盖 ACTIVE 死亡写侧 + 持久化连续（node-id 映射见 Implementation Report）。
"""
import pytest

from src.core.game_state import GameState
from src.tests.test_core.test_wpo_commander_death import (
    build_wpo_state,
    run_mortality_for,
    ALT_ID,
    VICTIM_ID,
    WAR_ID,
    NAVAL_WAR_ID,
)
from src.tests.fixtures.wpo_rng_guard import (  # noqa: F401  (autouse isolation fixture)
    _wpo_preserve_global_random_state,
)

_WAR_SCHEMA_KEYS = (
    "id", "status", "commander_id", "commander_status", "original_commander_id",
    "commander_assigned_turn", "triumph_commander_id", "declared_by",
)


def _war_payload(payload, war_id):
    ws = payload.get("_war_system") or {}
    for container in ("_war_deck", "_war_discard", "_active_wars", "_threats", "_truce_wars"):
        for w in ws.get(container, []):
            if w.get("id") == war_id:
                return w
    return None


# ---------------------------------------------------------------------------
# T06a — ACTIVE 死亡 → 存档 → fresh load → 纠正态保留、无复活（FC-09）
# ---------------------------------------------------------------------------
def test_t06a_mortality_roundtrip_preserves_corrected_absence(monkeypatch):
    ctx = build_wpo_state(naval=True)
    state, war = ctx["state"], ctx["war"]

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    payload = state.to_dict()
    war_payload = _war_payload(payload, NAVAL_WAR_ID)
    assert war_payload is not None
    # schema 键不变（FC-09：无迁移/无新键）
    for key in _WAR_SCHEMA_KEYS:
        assert key in war_payload, f"missing serialized War key: {key}"
    assert war_payload["commander_id"] is None
    assert war_payload["commander_status"] == "killed"
    assert war_payload["original_commander_id"] is None

    restored = GameState.create_for_testing({})
    restored.load_from_dict(payload)

    rws = restored.get_war_system()
    rwar = rws.get_war_by_id(NAVAL_WAR_ID)
    assert rwar is not None
    assert rwar.commander_id is None
    assert rwar.commander_status == "killed"
    assert rwar.original_commander_id is None
    assert restored.get_member(VICTIM_ID).is_dead is True

    rms = restored.get_military_system()
    for l in rms.get_legions_for_battle(NAVAL_WAR_ID):
        assert l.commander_id is None
    rns = restored.naval_system
    for f in rns.get_fleets_by_war(NAVAL_WAR_ID):
        assert f.commander_id is None


# ---------------------------------------------------------------------------
# T06c(history) — 身份域区分：死者 current 清、living original 留；living current 留
# ---------------------------------------------------------------------------
def test_t06c_living_current_preserved_dead_return_pointer_cleared(monkeypatch):
    """current = living alt；original = dead victim → 死者返回指针清，存活现任保留（FC-03）。"""
    ctx = build_wpo_state(naval=False, commander_id=ALT_ID, original_id=VICTIM_ID)
    state, war = ctx["state"], ctx["war"]
    assert war.commander_id == ALT_ID
    assert war.original_commander_id == VICTIM_ID

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    assert war.commander_id == ALT_ID            # 存活现任不被覆盖
    assert war.commander_status == "active"      # 不被死者伤亡标记污染
    assert war.original_commander_id is None     # 匹配死者返回指针清除


def test_t06c_living_return_pointer_preserved_when_current_dies(monkeypatch):
    """current = dead victim；original = living alt → 死者现任清，存活返回指针保留（FC-03）。"""
    ctx = build_wpo_state(naval=False, commander_id=VICTIM_ID, original_id=ALT_ID)
    state, war = ctx["state"], ctx["war"]
    assert war.commander_id == VICTIM_ID
    assert war.original_commander_id == ALT_ID

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert war.original_commander_id == ALT_ID   # 不同存活历史指针不被误清


def test_t06c_roundtrip_keeps_domain_separation(monkeypatch):
    """纠正态（current null / living original 保留）经存档 round-trip 保持域区分。"""
    ctx = build_wpo_state(naval=False, commander_id=VICTIM_ID, original_id=ALT_ID)
    state, war = ctx["state"], ctx["war"]
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rwar = restored.get_war_system().get_war_by_id(WAR_ID)
    assert rwar.commander_id is None
    assert rwar.commander_status == "killed"
    assert rwar.original_commander_id == ALT_ID


# ---------------------------------------------------------------------------
# T06b — TRUCE pending 死亡 → save/load → 真实重入 → save/load → ACTIVE null
#        （FC-09；O-S3；重入链见 test_integration/test_wpo_mortality_reentry.py）
# ---------------------------------------------------------------------------
from unittest import mock

from src.api import senate_api  # noqa: E402
from src.tests.test_integration.test_wpo_mortality_reentry import (  # noqa: E402
    PLAYER,
    TRUCE_WAR as _TRUCE_WAR,
    _add_consul_candidate,
    _build_truce_death_state,
    _drive_phases_after_mortality,
    _FailWar,
    _Pass,
)


def test_t06b_truce_death_roundtrip_then_production_reentry(monkeypatch):
    """TRUCE pending 死亡 → save/load（TRUCE null killed）→ 真实拒绝 Peace 重入 →
    save/load → ACTIVE null，附着/幸存者稳定（FC-09）。"""
    ctx = _build_truce_death_state()
    state, war = ctx["state"], ctx["war"]
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    legions_before = len(state.get_military_system().get_legions_for_battle(_TRUCE_WAR))

    # --- 存档 #1：TRUCE pending 保持，现任 null / killed ---
    restored1 = GameState.create_for_testing({})
    restored1.load_from_dict(state.to_dict())
    rwar1 = restored1.get_war_system().get_war_by_id(_TRUCE_WAR)
    assert rwar1.status.value == "truce"
    assert rwar1.commander_id is None
    assert rwar1.commander_status == "killed"
    assert rwar1.original_commander_id is None
    assert rwar1.peace_treaty is not None and rwar1.peace_treaty["status"] == "pending"
    assert len(restored1.get_military_system().get_legions_for_battle(_TRUCE_WAR)) == legions_before

    # --- 真实生产重入（同一 state）：拒绝 Peace → 边界 COMMITTED → ACTIVE null ---
    _drive_phases_after_mortality(state, player=PLAYER)
    sub = senate_api.propose_many(state, PLAYER, {
        "senate_session_id": "S1", "submit_request_id": "req-1",
        "war_drafts": [{"war_id": _TRUCE_WAR, "checked": True, "mode": "peace",
                        "target_commander_id": None, "reinforcement_n": 0}], "proposals": []})
    assert sub["success"], sub.get("errors")
    assert senate_api.resolve_senate(state, vote_decider=_FailWar([_TRUCE_WAR]))["success"]
    adv = senate_api.advance_senate_phase(state, PLAYER)
    assert adv["success"], adv.get("message")
    receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
    assert receipt and receipt["status"] == "COMMITTED"
    assert war.status.value == "active"
    assert war.commander_id is None and war.peace_treaty is None

    # --- 存档 #2：ACTIVE null 保持，幸存者稳定 ---
    restored2 = GameState.create_for_testing({})
    restored2.load_from_dict(state.to_dict())
    rwar2 = restored2.get_war_system().get_war_by_id(_TRUCE_WAR)
    assert rwar2.status.value == "active"
    assert rwar2.commander_id is None
    assert rwar2.commander_status == "killed"
    assert rwar2.peace_treaty is None
    assert len(restored2.get_military_system().get_legions_for_battle(_TRUCE_WAR)) == legions_before


# ---------------------------------------------------------------------------
# T06c(fault) — 死亡后 Senate 边界故障回滚：commander_status 一并恢复为 killed
#                （FC-03/09；O-S3 snapshot/restore additive commander_status）
# ---------------------------------------------------------------------------
def test_t06c_fault_rollback_restores_casualty_marker(monkeypatch):
    """死亡后真实 Senate 边界（重绑存活指挥官）中途故障 → 全域回滚，
    commander_status 恢复为死亡后基线 `killed`（非边界内的 active）。"""
    ctx = build_wpo_state(naval=False)
    state, war = ctx["state"], ctx["war"]
    _add_consul_candidate(state, ctx["faction"])   # population 链所需 Consul 候选
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    assert war.commander_id is None and war.commander_status == "killed"
    _drive_phases_after_mortality(state)

    sub = senate_api.propose_many(state, PLAYER, {
        "senate_session_id": "S1", "submit_request_id": "req-1",
        "war_drafts": [{"war_id": WAR_ID, "checked": True, "mode": "command",
                        "target_commander_id": ALT_ID, "reinforcement_n": 0}], "proposals": []})
    assert sub["success"], sub.get("errors")
    assert senate_api.resolve_senate(state, vote_decider=_Pass())["success"]

    # 故障注入（既有 supported seam）：边界 commit 内 mark_phase_executed 抛错 → 回滚 S0
    with mock.patch.object(GameState, "mark_phase_executed",
                           side_effect=RuntimeError("inject:t06c-fault")):
        adv = senate_api.advance_senate_phase(state, PLAYER)
    assert adv["success"] is False
    assert adv["data"]["code"] == "WAR_EXECUTION_APPLY_FAILED"
    # 全域回滚：现任还原 null + 伤亡标记还原 killed（additive snapshot 生效）
    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert state.get_war_execution_receipt_for_session(state.get_senate_session()) is None
    assert state.is_phase_executed("senate") is False
    # 同身份重试（无故障）→ 恰一次生效，commander_status → active
    adv2 = senate_api.advance_senate_phase(state, PLAYER)
    assert adv2["success"], adv2.get("message")
    assert war.commander_id == ALT_ID
    assert war.commander_status == "active"
