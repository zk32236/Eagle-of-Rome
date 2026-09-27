# src/tests/test_api/test_wpo_commander_consumers.py
"""WP-O Slice O-S2 — 读侧消费者闭合（T02a/T02b + FC-11）。

RED 证据绑定（long-chain-verification-contract §5）：
  真实死亡写侧（O-S1）后，**所有现任指挥官身份消费者**经既有 live 谓词
  `GameState.get_living_member` 解析；死者不得作为现任统帅呈现/使用。

覆盖（Development-Task-WP-O §B2 R01–R15 子集，逐项见 Implementation Report）：
  R01 combat_api._war_card / _compute_combat_result（DTO 哨兵一致）
  R02 combat_api._actionable_wars / auto_resolve 分区（invalid current = absent）
  R03 gui_query_api._war_summary（None/空名，无数字 id fallback）
  R04 game_state.build_submission_context（新 current/return/镜像事实用 live）
  R05 war_system.describe_senate_war / get_war_by_commander / without_commander /
      needing_reassignment（F-03）
  R06 political_system _current_command_war_ids / build_war_card_views /
      build_commander_claims 保留支 / build_war_resolution_plan c0
  R07 senate_api.auto_propose_all used_commanders（仅 live 保留现任占用）
  R08 fleet.get_combat_strength / naval_system.get_fleet_strength_breakdown
      （current 或 fallback-private 身份均需 living）

纪律：真实生产路径；T02a 用 O-S1 真实死亡写侧（无 mock death）；T02b 的参数化
非法身份为 **FAULT_INJECTION（MOCK_AUXILIARY）**，只读函数断言零 mutation。
"""
import pytest

from src.api import combat_api, gui_query_api
from src.core.systems.political_system import PoliticalSystem
from src.tests.test_core.test_wpo_commander_death import (
    build_wpo_state,
    run_mortality_for,
    ALT_ID,
    VICTIM_ID,
    CONTROL_ID,
    WAR_ID,
    NAVAL_WAR_ID,
)
from src.tests.fixtures.wpo_rng_guard import (  # noqa: F401  (autouse isolation fixture)
    _wpo_preserve_global_random_state,
)

PLAYER = "player1"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _combat_card(resp, war_id):
    for card in (resp.get("data") or {}).get("active_wars", []):
        if card.get("war_id") == war_id:
            return card
    return None


def _war_summary(state, war_id):
    resp = gui_query_api.get_global_query_result(state, PLAYER, "war_list")
    data = resp.get("data") or {}
    for entry in (data.get("summary") or {}).get("wars", []):
        if entry.get("id") == war_id:
            return entry
    return None


def _dead_current_state(monkeypatch, naval=True):
    """真实 O-S1 死亡写侧：victim(2) 真死 + War/Fleet/legion 现任解绑。"""
    ctx = build_wpo_state(naval=naval)
    state = ctx["state"]
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    return ctx


# ---------------------------------------------------------------------------
# T02a — 真实死亡后消费者无 dead current 泄漏（正样本；FC-07/08；O-AC-02）
# ---------------------------------------------------------------------------
def test_t02a_consumers_hide_dead_current_after_real_death(monkeypatch):
    ctx = _dead_current_state(monkeypatch, naval=True)
    state, war_id = ctx["state"], ctx["war_id"]
    war = ctx["war"]
    assert war.commander_id is None  # O-S1 write side (precondition)

    # R01 combat card sentinel tuple 一致（含 faction）；dead martial = 0
    view = combat_api.get_combat_view(state, PLAYER)
    assert view["success"], view
    card = _combat_card(view, war_id)
    assert card is not None
    assert (card["commander_id"], card["commander_name"], card["commander_martial"],
            card["has_commander"], card["commander_faction_id"]) == (-1, "", 0, False, None)

    # R03 GUI summary：None / 空名（无数字 id fallback label）
    summ = _war_summary(state, war_id)
    assert summ["commander_id"] is None
    assert summ["commander_name"] == ""

    # R05/R06 Senate facts + card view：current id None / label ""
    pol = PoliticalSystem(state)
    facts = state.get_war_system().describe_senate_war(war_id, {"current_turn": 5})
    assert facts["current_commander_id"] is None
    cards = pol.build_war_card_views({})
    vcard = next(c for c in cards if c["war_id"] == war_id)
    assert vcard["current_commander_id"] is None
    assert vcard["current_commander_label"] == ""

    # R06 保留 claim：死者不占现任 claim
    real_wars = pol._real_wars()
    claims = pol.build_commander_claims(real_wars, canonical_drafts=[])
    assert all(c["commander_id"] != VICTIM_ID for c in claims)
    assert pol._current_command_war_ids(VICTIM_ID) == []

    # R06 plan c0/final：不保留死者现任
    plan = pol.build_war_resolution_plan({
        "current_turn": 5, "session_id": "S1", "real_wars": real_wars,
        "available_legion_ids": [], "pending_war_ids": []})
    assert plan["final_commander_by_war"][war_id] is None

    # R04 新冻结上下文：current/return/镜像事实无死现任
    frozen = state.build_submission_context(
        context_id="c1", senate_session_id="S1", actor_id=PLAYER,
        package_id="p1", turn=5, revision=1, war_ids=[war_id])
    row = frozen["wars"][war_id]
    assert row["current_commander_id"] is None
    assert row["current_commander_label"] is None
    assert all(v is None for v in row["legion_bindings"].values())
    assert all(b["commander_id"] is None for b in row["fleet_bindings"].values())

    # R01/R08 陆战 + 海军 martial 无死者；live 力量仍保留
    legions = state.get_military_system().get_legions_for_battle(war_id)
    assert len(legions) >= 1
    live_legion_power = sum(l.get_combat_strength() for l in legions)
    assert live_legion_power > 0
    assert card["total_power"] == card["commander_martial"] + live_legion_power
    assert card["fleet_commander_bonus"] == 0
    assert card["fleet_nominal_strength"] > 0
    assert card["fleet_effective_combat_strength"] > 0
    for fleet in state.naval_system.get_fleets_by_war(war_id):
        assert fleet.get_combat_strength(state) == fleet.quality_adjusted_base + fleet.experience


# ---------------------------------------------------------------------------
# T02b — 身份参数化：dead/missing/null/living-absent/living-nonabsent
#          （FAULT_INJECTION = MOCK_AUXILIARY；read 零 mutation）
# ---------------------------------------------------------------------------
_IDENTITIES = ["null", "missing", "dead", "living_absent", "living_nonabsent"]
_LIVING = {"living_absent", "living_nonabsent"}


def _apply_identity(ctx, kind):
    """在真实死亡后的 state 上注入现任身份（FAULT_INJECTION，标注 MOCK_AUXILIARY）。"""
    state, war = ctx["state"], ctx["war"]
    fleet = state.naval_system.get_fleets_by_war(ctx["war_id"])[0]
    if kind == "null":
        cid = None
    elif kind == "missing":
        cid = 9999
    elif kind == "dead":
        cid = VICTIM_ID
    elif kind == "living_absent":
        ctx["alt"].is_absent = True
        cid = ALT_ID
    elif kind == "living_nonabsent":
        cid = CONTROL_ID
    else:  # pragma: no cover
        raise AssertionError(kind)
    war.commander_id = cid
    fleet._commander_id = cid  # 镜像同注入
    war.reset_commander_status_to_active()  # 隔离「身份存活」谓词，不问 killed 标记
    return state, war, fleet, cid


@pytest.mark.parametrize("kind", _IDENTITIES)
def test_t02b_get_war_by_commander_is_live_only(monkeypatch, kind):
    ctx = _dead_current_state(monkeypatch, naval=True)
    state, war, fleet, cid = _apply_identity(ctx, kind)
    ws = state.get_war_system()
    living_expected = kind in _LIVING
    before = war.commander_id  # write-back guard

    # F-03：None 查询恒 None；dead/missing 查询 None
    assert ws.get_war_by_commander(None) is None
    if cid is None:
        assert ws.get_war_by_commander(None) is None
    elif living_expected:
        assert ws.get_war_by_commander(cid) is war
    else:
        assert ws.get_war_by_commander(cid) is None

    # R05 无现任集合：invalid current 视同无现任
    without = ws.get_active_wars_without_commander()
    assert (war in without) == (cid is None or not living_expected)

    # R05 dead/missing 现任 → 需重指派（旧 status/mirror 计数之外的身份谓词）
    if kind in ("dead", "missing"):
        assert war in ws.get_wars_needing_reassignment()
    if living_expected:
        assert war not in ws.get_wars_needing_reassignment()

    assert war.commander_id == before


@pytest.mark.parametrize("kind", _IDENTITIES)
def test_t02b_dto_plan_and_martial_consumers_are_live_only(monkeypatch, kind):
    ctx = _dead_current_state(monkeypatch, naval=True)
    state, war, fleet, cid = _apply_identity(ctx, kind)
    war_id = ctx["war_id"]
    ws = state.get_war_system()
    pol = PoliticalSystem(state)
    living_expected = kind in _LIVING
    expected_id = cid if living_expected else None
    before = war.commander_id  # write-back guard

    # R05 describe_senate_war
    facts = ws.describe_senate_war(war_id, {"current_turn": 5})
    assert facts["current_commander_id"] == expected_id

    # R01/R03 DTO 哨兵
    card = _combat_card(combat_api.get_combat_view(state, PLAYER), war_id)
    if living_expected:
        assert card["commander_id"] == cid
        assert card["commander_martial"] == state.get_member(cid).martial
        assert card["has_commander"] is True
    else:
        assert (card["commander_id"], card["commander_name"], card["commander_martial"],
                card["has_commander"], card["commander_faction_id"]) == (-1, "", 0, False, None)
    summ = _war_summary(state, war_id)
    assert summ["commander_id"] == expected_id
    if living_expected:
        assert summ["commander_name"] == state.get_member(cid).get_formal_name()
    else:
        assert summ["commander_name"] == ""

    # R06 card view label / 保留 claim / plan c0
    vcard = next(c for c in pol.build_war_card_views({}) if c["war_id"] == war_id)
    assert vcard["current_commander_id"] == expected_id
    assert vcard["current_commander_label"] == (
        state.get_member(cid).get_formal_name() if living_expected else "")

    claims = pol.build_commander_claims(pol._real_wars(), canonical_drafts=[])
    claim_ids = [c["commander_id"] for c in claims if c["war_id"] == war_id]
    if living_expected:
        assert claim_ids == [cid]
    else:
        assert claim_ids == []

    plan = pol.build_war_resolution_plan({
        "current_turn": 5, "session_id": "S1", "real_wars": pol._real_wars(),
        "available_legion_ids": [], "pending_war_ids": []})
    assert plan["final_commander_by_war"][war_id] == expected_id

    # R08 Fleet martial：current 或 fallback-private 均需 living
    base = fleet.quality_adjusted_base + fleet.experience
    if living_expected:
        assert fleet.get_combat_strength(state) == base + state.get_member(cid).martial
    else:
        assert fleet.get_combat_strength(state) == base

    # R08 Naval 聚合 commander_bonus
    ms = state.get_military_system()
    breakdown = state.naval_system.get_fleet_strength_breakdown(
        state.naval_system.get_fleets_by_war(war_id))
    if living_expected:
        assert breakdown["commander_bonus"] == state.get_member(cid).martial
    else:
        assert breakdown["commander_bonus"] == 0

    # read 函数零 mutation
    assert war.commander_id == before


def test_t02b_fleet_fallback_private_identity_requires_living(monkeypatch):
    """R08：War 无现任（None）时回退 Fleet 私有绑定，私有身份同样须 living。"""
    ctx = _dead_current_state(monkeypatch, naval=True)
    state, war = ctx["state"], ctx["war"]
    war_id = ctx["war_id"]
    fleet = state.naval_system.get_fleets_by_war(war_id)[0]
    war.commander_id = None
    # 私有回退 = 死者 → 不得加成
    fleet._commander_id = VICTIM_ID
    assert fleet.get_combat_strength(state) == fleet.quality_adjusted_base + fleet.experience
    assert state.naval_system.get_fleet_strength_breakdown([fleet])["commander_bonus"] == 0
    # 私有回退 = 存活 → 保持原加成（每 Fleet 一次）
    fleet._commander_id = CONTROL_ID
    assert fleet.get_combat_strength(state) == (
        fleet.quality_adjusted_base + fleet.experience + state.get_member(CONTROL_ID).martial)
    assert state.naval_system.get_fleet_strength_breakdown([fleet])["commander_bonus"] == \
        state.get_member(CONTROL_ID).martial


# ---------------------------------------------------------------------------
# R02 — 分区：invalid current identity 视同 absent（不改 action policy）
# ---------------------------------------------------------------------------
def test_t02b_actionable_partition_treats_dead_binding_as_absent(monkeypatch):
    ctx = _dead_current_state(monkeypatch, naval=True)
    state, war = ctx["state"], ctx["war"]
    war_id = ctx["war_id"]
    ws = state.get_war_system()
    # FAULT_INJECTION：原始态残留死者现任（MOCK_AUXILIARY）
    war.commander_id = VICTIM_ID
    war.reset_commander_status_to_active()
    phase_data = {}
    assert war not in combat_api._actionable_wars(ws, phase_data, state=state)
    # null 现任同样不计入
    war.commander_id = None
    assert war not in combat_api._actionable_wars(ws, phase_data, state=state)


# ---------------------------------------------------------------------------
# FC-11 — 历史冻结不可变；新建 current 用 live；失效选中目标仍可见并 fail
# ---------------------------------------------------------------------------
def test_fc11_frozen_history_immutable_new_context_uses_live(monkeypatch):
    ctx = build_wpo_state(naval=False)
    state, war_id = ctx["state"], ctx["war_id"]
    war = ctx["war"]
    assert war.commander_id == VICTIM_ID

    # 冻结（存活时）→ 历史事实保留死者现任身份
    frozen_alive = state.build_submission_context(
        context_id="hist", senate_session_id="S0", actor_id=PLAYER,
        package_id="p0", turn=5, revision=1, war_ids=[war_id])
    assert frozen_alive["wars"][war_id]["current_commander_id"] == VICTIM_ID

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    # 历史冻结件不可变（同一 dict 对象内容不因死亡而改写）
    assert frozen_alive["wars"][war_id]["current_commander_id"] == VICTIM_ID
    assert frozen_alive["wars"][war_id]["current_commander_label"] is not None

    # 新建 current-command 上下文用 live → 无死者现任
    frozen_new = state.build_submission_context(
        context_id="new", senate_session_id="S1", actor_id=PLAYER,
        package_id="p1", turn=6, revision=2, war_ids=[war_id])
    assert frozen_new["wars"][war_id]["current_commander_id"] is None

    # 失效选中目标仍可见（不静默丢弃）：selected_command claim 保留死者 target
    pol = PoliticalSystem(state)
    selected = {"war_id": war_id, "checked": True, "mode": "command",
                "target_commander_id": VICTIM_ID, "reinforcement_n": 0}
    claims = pol.build_commander_claims(pol._real_wars(), canonical_drafts=[selected])
    sel = [c for c in claims if c["war_id"] == war_id]
    assert sel and sel[0]["commander_id"] == VICTIM_ID      # 可见，不静默丢弃
    assert sel[0]["basis"] == "selected_command"
    plan = pol.build_war_resolution_plan({
        "current_turn": 6, "session_id": "S1", "real_wars": pol._real_wars(),
        "available_legion_ids": [], "pending_war_ids": []})
    assert plan["final_commander_by_war"][war_id] is None    # retained c0 用 live（非死者）


# ---------------------------------------------------------------------------
# FC-11（fail 支）— 选中失效目标在 submit 校验可见并 fail（不静默丢弃）
# ---------------------------------------------------------------------------
def test_fc11_selected_dead_target_rejected_by_validation():
    from src.tests.fixtures.wpgr5_fixtures import (
        build_r5_base, add_figure, submit_request, command_draft, error_codes, FIXED)
    b = build_r5_base()
    state = b["state"]
    add_figure(state, b["faction"], 77, "Dead Cmd", office="ex-consul")
    assert state.mark_member_dead(77) is True
    pol = PoliticalSystem(state)
    result = pol.submit_proposal_package(FIXED["player"], submit_request(
        war_drafts=[command_draft(b["war_ongoing"].id, 77, 0)]))
    assert result["success"] is False
    assert "COMMANDER_TARGET_INVALID" in error_codes(result)

