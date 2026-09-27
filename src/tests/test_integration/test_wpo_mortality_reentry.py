# src/tests/test_integration/test_wpo_mortality_reentry.py
"""WP-O Slice O-S3 — 重入链 / 历史不变 / 持久化回滚（T03a–d + FC-06/09/11）。

RED 证据绑定（long-chain-verification-contract §1 Critical Test Seam / §4 L03–L07）：
  真实 Mortality 生产者 → `GameState.mark_member_dead` → WarSystem 权威解绑
  → 既有公开 Senate 提交/结算/重入 API（propose_many → resolve_senate →
  advance_senate_phase → 真实 political plan/apply → move_truce_war_to_active）
  → Combat 现任视图 / 分区 → `GameState.to_dict` → fresh `load_from_dict`。

覆盖（Development-Task-WP-O §B3；acceptance-traceability T03a/b/c/d）：
  T03a  真实 DRAW → TRUCE pending → 真实死亡 → 拒绝 Peace 生产链 → COMMITTED →
        ACTIVE null + treaty None + 幸存者保留 → save/load 同事实。
  T03b  同链 unchecked pending fallback（无假结果）→ ACTIVE null + 无新兵。
  T03c  真实死亡后独立直调原语：restore_rejected_peace_treaty(default True) 与
        move_truce_war_to_active（container-only，不清 treaty）。
  T03d  真实死亡后经合法 command intent + 真实 Senate 边界显式重绑存活指挥官，
        commander_status → active；get_wars_needing_reassignment 不再仅因死者标记。

红线（SA 禁止事项）：禁 mock 死亡；禁手置 is_dead / 直接 commander_id=None 作主证；
断言 raw 权威态，先于读 DTO。SC-MORT deterministic victim = 内存 singleton death deck +
scoped `random.sample` 控制（断言 k==1，按 id 定位真实对象，立即还原）。
"""
import pytest

from src.api import (senate_api, combat_api, resolution_api, game_api, forum_api,
                     population_api, session_api, mortality_api, revenue_api)
from src.core.entities.war import WarStatus
from src.core.game_state import GameState
from src.tests.fixtures.wpgr4_fixtures import (
    make_base_state,
    add_faction,
    add_player,
    make_war,
    attach_active,
    attach_truce,
    recruit_legions_for_war,
    _base_config,
)
from src.tests.fixtures.wpgr5_fixtures import add_figure, peace_draft, command_draft
from src.tests.test_core.test_wpo_commander_death import (
    build_wpo_state,
    run_mortality_for,
    ALT_ID,
    VICTIM_ID,
    CONTROL_ID,
    WAR_ID,
)
from src.tests.fixtures.wpo_rng_guard import (  # noqa: F401  (autouse isolation fixture)
    _wpo_preserve_global_random_state,
)

PLAYER = "player1"
REENTRY_WAR = "wpo_reentry_war"
TRUCE_WAR = "wpo_truce_war"
CONSUL_ID = 4


def _reentry_config(force_battle="draw"):
    """内存 config（committed 默认语义）+ force draw + singleton death deck（SC-MORT）。"""
    cfg = _base_config()
    cfg["testing"]["force_battle_result"] = force_battle
    cfg["testing"]["force_naval_result"] = ""
    cfg["mortality_rules"] = {
        "event_deck": [{"name": "WP-O death", "effect": "death", "weight": 1}],
        "event_draw_count": 1,
        "death_count": 1,
    }
    return cfg


def _add_consul_candidate(state, faction):
    """population 链 bootstrap：合格 Consul 候选（年龄 45 NOBILE，前 Praetor 任期）。

    `can_hold_office('consul')` 要求 office_history 含 praetor 任期；add_office_history
    会把 office 置 None，故历史后再显式设 ex-praetor。
    """
    fig = add_figure(state, faction, CONSUL_ID, "Consul Aemilius", office="ex-praetor",
                     martial=2, history=[{"office_type": "praetor",
                                          "start_turn": -5, "end_turn": -4}])
    fig.office = "ex-praetor"
    fig.influence = 80
    return fig


def _add_death_figures(state, faction):
    """固定标识：id=1 living alternative / id=2 deployed victim / id=3 living control
    + id=4 留城 Consul 候选（population 链 bootstrap）。"""
    alt = add_figure(state, faction, ALT_ID, "Alternate Commander", office="ex-consul", martial=3)
    victim = add_figure(state, faction, VICTIM_ID, "Deployed Victim",
                        office="proconsul", martial=4, absent=True)
    control = add_figure(state, faction, CONTROL_ID, "Living Control", office="ex-praetor", martial=2)
    consul = _add_consul_candidate(state, faction)
    return alt, victim, control, consul


# ---------------------------------------------------------------------------
# T03a / T03b — 真实 DRAW → TRUCE pending → 死亡 → 拒绝/unchecked Peace 重入链
# ---------------------------------------------------------------------------
def _build_reentry_state():
    """合法 Combat 入口：ACTIVE 陆战（commander=victim）+ 真实 Legion + 3 真实 Figure。"""
    state = make_base_state(turn_number=1, year=-264, phases_to_senate=True,
                            config=_reentry_config(force_battle="draw"))
    state.mark_phase_executed("senate")     # 外生前置：已到合法 Combat 入口
    state._treasury = 500
    faction = add_faction(state, treasury=500)
    add_player(state, player_id=PLAYER, faction_id="optimates")
    alt, victim, control, consul = _add_death_figures(state, faction)
    war = make_war(REENTRY_WAR, "WP-O Reentry War", status=WarStatus.ACTIVE,
                   naval_required=False, enemy_land=6, commander_id=VICTIM_ID, threat_level=4)
    attach_active(state, war)
    legions = recruit_legions_for_war(state, war, VICTIM_ID, count=2)
    return {"state": state, "faction": faction, "alt": alt, "victim": victim,
            "control": control, "consul": consul, "war": war, "legions": legions}


def _draw_to_truce(state):
    """真实 producer：forced land DRAW → `_generate_peace_treaty` → TRUCE pending。"""
    attack = combat_api.do_combat_action(state, PLAYER, REENTRY_WAR, "attack")
    assert attack["success"], attack.get("message")
    war = state.get_war_system().get_war_by_id(REENTRY_WAR)
    assert war.status == WarStatus.TRUCE, war.status
    assert war.peace_treaty is not None and war.peace_treaty.get("status") == "pending", war.peace_treaty
    assert war.commander_id == VICTIM_ID
    assert war.original_commander_id == VICTIM_ID      # enter_truce 捕获返回指针
    assert combat_api.confirm_battle_result(state, PLAYER)["success"]
    assert combat_api.advance_combat(state, PLAYER)["success"]
    assert resolution_api.execute_resolution(state)["success"]
    adv = game_api.advance_year(state, PLAYER)
    assert adv["success"], adv.get("message")
    assert state.turn.turn_number == 2
    return war


def _drive_phases_after_mortality(state, player=PLAYER):
    """mortality 已 execute（有 phase_result）→ 真实推进 revenue/forum/population 到 Senate。"""
    assert mortality_api.advance_mortality_phase(state, player)["success"]
    assert revenue_api.execute_revenue_phase(state, player)["success"]
    assert revenue_api.advance_revenue_phase(state, player)["success"]
    assert forum_api.resolve_forum(state)["success"]
    assert forum_api.advance_forum_phase(state, player)["success"]
    population_api.begin_population_phase(state)
    cand = population_api.get_candidates(state)
    assert cand["success"], cand.get("message")
    entries = [{"office": o, "figure_id": 0}
               for o in ["consul", "censor", "praetor", "quaestor", "tribune"]]
    consul_cands = [c for c in (cand["data"].get("consul") or [])
                    if c.get("faction_id") == "optimates"
                    and state.get_member(c["id"]) is not None
                    and not state.get_member(c["id"]).is_dead]
    if consul_cands:
        entries[0]["figure_id"] = sorted(c["id"] for c in consul_cands)[0]
    vote = population_api.batch_vote(state, player, entries, bypass_permission=True)
    assert vote["success"], f"batch_vote failed: {vote.get('message')} {vote.get('errors')}"
    assert session_api.resolve_population_slice(state)["success"]
    assert session_api.advance_population_phase(state, player)["success"]


class _FailWar:
    """目标 War 的 Peace 一律否决（其余通过）——确定性 rejection，非伪造结果。"""

    def __init__(self, fail_ids):
        self.fail = set(fail_ids)

    def decide_vote(self, issue, faction, state):
        wid = issue.get("war_id") if isinstance(issue, dict) else None
        return wid not in self.fail


class _Pass:
    def decide_vote(self, issue, faction, state):
        return True


def _submit_peace(state, checked=True):
    return senate_api.propose_many(state, PLAYER, {
        "senate_session_id": "S1", "submit_request_id": "req-1",
        "war_drafts": [peace_draft(REENTRY_WAR, checked=checked)], "proposals": []})


def _reentry_via_rejected_peace(monkeypatch):
    """T03a 全生产链 → 返回 (state, war)。"""
    ctx = _build_reentry_state()
    state, war = ctx["state"], ctx["war"]
    _draw_to_truce(state)
    # P2：下一年 death 前置（TRUCE pending 保持）
    assert war.status == WarStatus.TRUCE and war.peace_treaty["status"] == "pending"
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    # P3：raw 权威态 — 死者现任/返回指针清，TRUCE/treaty 保持
    assert war.status == WarStatus.TRUCE
    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert war.original_commander_id is None
    assert war.peace_treaty is not None and war.peace_treaty["status"] == "pending"
    _drive_phases_after_mortality(state)
    # P4：新冻结上下文（Senate 入口）→ 现任 null
    assert state.get_war_system().get_war_by_id(REENTRY_WAR).commander_id is None
    return ctx


def test_t03a_rejected_peace_reentry_active_null(monkeypatch):
    ctx = _reentry_via_rejected_peace(monkeypatch)
    state, war = ctx["state"], ctx["war"]
    survivors_before = len(state.get_military_system().get_legions_for_battle(REENTRY_WAR))
    assert survivors_before >= 1

    sub = _submit_peace(state, checked=True)
    assert sub["success"], sub.get("errors")
    res = senate_api.resolve_senate(state, vote_decider=_FailWar([REENTRY_WAR]))
    assert res["success"], res.get("message")
    adv = senate_api.advance_senate_phase(state, PLAYER)
    assert adv["success"], adv.get("message")
    receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
    assert receipt is not None and receipt["status"] == "COMMITTED", receipt

    # P5：ACTIVE null + treaty None + 幸存者保留
    assert war.status == WarStatus.ACTIVE
    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert war.peace_treaty is None
    assert len(state.get_military_system().get_legions_for_battle(REENTRY_WAR)) == survivors_before

    # P6：save/load → 同事实
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rwar = restored.get_war_system().get_war_by_id(REENTRY_WAR)
    assert rwar.status == WarStatus.ACTIVE
    assert rwar.commander_id is None
    assert rwar.commander_status == "killed"
    assert restored.get_member(VICTIM_ID).is_dead is True
    assert len(restored.get_military_system().get_legions_for_battle(REENTRY_WAR)) == survivors_before


def test_t03b_unchecked_pending_fallback_reentry(monkeypatch):
    ctx = _reentry_via_rejected_peace(monkeypatch)
    state, war = ctx["state"], ctx["war"]
    ms = state.get_military_system()
    pool_before = sorted(l.number for l in ms.get_available_legions())

    sub = _submit_peace(state, checked=False)          # unchecked → 不产提案/不追和约
    assert sub["success"], sub.get("errors")
    res = senate_api.resolve_senate(state, vote_decider=_Pass())
    assert res["success"], res.get("message")
    adv = senate_api.advance_senate_phase(state, PLAYER)
    assert adv["success"], adv.get("message")
    receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
    assert receipt and receipt["status"] == "COMMITTED"

    assert war.status == WarStatus.ACTIVE
    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert war.peace_treaty is None
    # 无新兵/无新指派
    assert sorted(l.number for l in ms.get_available_legions()) == pool_before


# ---------------------------------------------------------------------------
# T03c — 真实死亡后独立直调原语（restore_rejected default / move-only）
# ---------------------------------------------------------------------------
def _build_truce_death_state():
    """合法前驱（ACTIVE + 真实 Legion）→ 直建 TRUCE+pending（supplementary 组件面）。"""
    state = make_base_state(turn_number=5, year=-280, phases_to_senate=False,
                            config=_reentry_config(force_battle=""))
    state._treasury = 500
    faction = add_faction(state, treasury=500)
    add_player(state, player_id=PLAYER, faction_id="optimates")
    alt, victim, control, consul = _add_death_figures(state, faction)
    war = make_war(TRUCE_WAR, "WP-O Truce War", status=WarStatus.ACTIVE,
                   naval_required=False, enemy_land=6, commander_id=VICTIM_ID, threat_level=3)
    attach_active(state, war)
    legions = recruit_legions_for_war(state, war, VICTIM_ID, count=2)
    # 组件面：置 TRUCE + pending（supplementary；primary 链见 T03a）
    state.get_war_system()._active_wars.remove(war)
    war.status = WarStatus.TRUCE
    attach_truce(state, war)
    war.set_peace_treaty({"indemnity": 60, "duration": 3, "status": "pending", "generated_turn": 5})
    war.set_original_commander(VICTIM_ID, 5)
    return {"state": state, "war": war, "legions": legions, "alt": alt}


def test_t03c_restore_rejected_preserves_cleaned_current(monkeypatch):
    ctx = _build_truce_death_state()
    state, war = ctx["state"], ctx["war"]
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    assert war.status == WarStatus.TRUCE
    assert war.commander_id is None and war.commander_status == "killed"
    assert war.original_commander_id is None

    # restore_rejected_peace_treaty 默认 preserve_commander=True → 保留已清 null（不回退原将）
    ws = state.get_war_system()
    assert ws.restore_rejected_peace_treaty(TRUCE_WAR) is True
    assert war.status == WarStatus.ACTIVE
    assert war.commander_id is None
    assert war.commander_status == "killed"           # 重入本身不复位
    assert war.peace_treaty is None
    assert len(state.get_military_system().get_legions_for_battle(TRUCE_WAR)) >= 1
    # 单成员：既不在 truce 也不重复在 active
    assert war not in ws._truce_wars
    assert ws._active_wars.count(war) == 1


def test_t03c_move_truce_war_to_active_is_container_only(monkeypatch):
    ctx = _build_truce_death_state()
    state, war = ctx["state"], ctx["war"]
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    ws = state.get_war_system()
    # move-only 原语：仅容器 + status；不清 treaty（提交/终止草案由别处负责）
    assert ws.move_truce_war_to_active(war) is True
    assert war.status == WarStatus.ACTIVE
    assert war.commander_id is None
    assert war.peace_treaty is not None and war.peace_treaty["status"] == "pending"


# ---------------------------------------------------------------------------
# T03d — 真实死亡后显式合法 command 重绑存活指挥官（非 mortality 替补）
# ---------------------------------------------------------------------------
def test_t03d_explicit_command_rebinds_survivors(monkeypatch):
    ctx = build_wpo_state(naval=True)             # ACTIVE 陆/海军 War + 真实 Legion/Fleet
    state, war = ctx["state"], ctx["war"]
    _add_consul_candidate(state, ctx["faction"])  # population 链所需 Consul 候选
    ms = state.get_military_system()
    ns = state.naval_system
    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    assert war.commander_id is None and war.commander_status == "killed"
    _drive_phases_after_mortality(state)

    ws = state.get_war_system()
    assert war in ws.get_wars_needing_reassignment()          # 死者指挥 → 需重指派

    sub = senate_api.propose_many(state, PLAYER, {
        "senate_session_id": "S1", "submit_request_id": "req-1",
        "war_drafts": [command_draft(ctx["war_id"], ALT_ID, 0)], "proposals": []})
    assert sub["success"], sub.get("errors")
    # Submit 零部署
    assert war.commander_id is None
    res = senate_api.resolve_senate(state, vote_decider=_Pass())
    assert res["success"], res.get("message")
    adv = senate_api.advance_senate_phase(state, PLAYER)
    assert adv["success"], adv.get("message")

    # 真实边界显式重绑存活指挥官 → commander_status active；幸存 Legion/Fleet 一并重绑
    assert war.commander_id == ALT_ID
    assert war.commander_status == "active"
    assert war not in ws.get_wars_needing_reassignment()
    for legion in ms.get_legions_for_battle(ctx["war_id"]):
        assert legion.commander_id == ALT_ID
    for fleet in ns.get_fleets_by_war(ctx["war_id"]):
        assert fleet.commander_id == ALT_ID
