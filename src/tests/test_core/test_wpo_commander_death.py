# src/tests/test_core/test_wpo_commander_death.py
"""WP-O Slice O-S1 — 非战斗死亡写侧单一权威解绑（T01/T04/T05 + FC-03/B4）。

RED 证据绑定（long-chain-verification-contract §1 Critical Test Seam）：
  真实 Mortality 生产者 `mortality_api.execute_mortality_phase`
  → `GameState.mark_member_dead` → `WarSystem.clear_deceased_commander_bindings`
  → MilitarySystem/NavalSystem 精确死者 id 镜像清理
  → raw GameState Figure/War/Legion/Fleet 权威事实。

红线（SA 禁止事项）：
- 禁 mock 满足 O-AC-01；禁手置 `is_dead`；禁直接 `commander_id=None` 作主证。
- 断言 raw 权威态，**先于任何读 DTO**。

场景控制 SC-MORT（§3）：内存 config singleton death deck + `death_count=1`；
仅在公开 producer 执行期间替换 `mortality_service.random.sample`（非 service/owner/consumer），
断言 `k==1` 并按 id 定位**真实**对象，立即还原（不依赖 seed）。
"""
import pytest

from src.api import mortality_api
from src.core.entities.war import WarStatus
from src.tests.fixtures.wpgr4_fixtures import (
    make_base_state,
    add_faction,
    add_player,
    make_war,
    attach_active,
    recruit_legions_for_war,
    add_ready_fleets,
    _base_config,
)
from src.tests.fixtures.wpgr5_fixtures import add_figure
from src.tests.fixtures.wpo_rng_guard import (  # noqa: F401  (autouse isolation fixture)
    _wpo_preserve_global_random_state,
)

# 固定标识（SA §3：id=1 living alternative / id=2 deployed victim / id=3 living control）
ALT_ID = 1
VICTIM_ID = 2
CONTROL_ID = 3
WAR_ID = "wpo_death_war"
NAVAL_WAR_ID = "wpo_naval_death_war"
UNRELATED_WAR_ID = "wpo_unrelated"


def _death_config():
    """内存 config（committed 默认语义）+ singleton death deck（SC-MORT）。"""
    cfg = _base_config()
    cfg["mortality_rules"] = {
        "event_deck": [{"name": "WP-O death", "effect": "death", "weight": 1}],
        "event_draw_count": 1,
        "death_count": 1,
    }
    return cfg


def build_wpo_state(naval=False, with_unrelated_war=False, commander_id=VICTIM_ID,
                    original_id=VICTIM_ID, original_assigned_turn=5):
    """真实前驱：ACTIVE War + 公开指派 Legion（+ naval 变体 Fleet）+ 3 个真实 Figure。

    仅声明「已到 Mortality 入口」外生前置（phases_to_senate=False）；
    军团/舰队经既有公开 producer 链生产（recruit+assign / assign_fleet_to_war）。
    """
    state = make_base_state(turn_number=5, year=-280, phases_to_senate=False,
                            config=_death_config())
    state._treasury = 500
    faction = add_faction(state, treasury=500)
    add_player(state, player_id="player1", faction_id="optimates")
    alt = add_figure(state, faction, ALT_ID, "Alternate Commander", office="ex-consul", martial=3)
    victim = add_figure(state, faction, VICTIM_ID, "Deployed Victim",
                        office="proconsul", martial=4, absent=True)
    control = add_figure(state, faction, CONTROL_ID, "Living Control", office="ex-praetor", martial=2)

    war_id = NAVAL_WAR_ID if naval else WAR_ID
    war = make_war(
        war_id, "WP-O Death War", status=WarStatus.ACTIVE,
        naval_required=naval, enemy_naval=12 if naval else 0, enemy_land=6,
        commander_id=commander_id, threat_level=4,
    )
    attach_active(state, war)
    if original_id is not None:
        war.set_original_commander(original_id, original_assigned_turn)
    legions = recruit_legions_for_war(state, war, commander_id, count=2)
    fleets = add_ready_fleets(state, war, count=1) if naval else []

    unrelated = None
    if with_unrelated_war:
        unrelated = make_war(UNRELATED_WAR_ID, "Unrelated War", status=WarStatus.ACTIVE,
                             commander_id=ALT_ID, threat_level=2)
        attach_active(state, unrelated)
        recruit_legions_for_war(state, unrelated, ALT_ID, count=1)

    return {
        "state": state, "faction": faction, "alt": alt, "victim": victim,
        "control": control, "war": war, "legions": legions, "fleets": fleets,
        "unrelated": unrelated, "war_id": war_id,
    }


def run_mortality_for(monkeypatch, state, target_id, player_id="player1"):
    """SC-MORT：公开 producer + 受控 victim 选择（断言 k==1，按 id 定位真实对象，立即还原）。"""
    import src.core.service.mortality_service as mortality_service

    real_sample = mortality_service.random.sample
    seen = {}

    def controlled_sample(population, k):
        seen["k"] = k
        ids = [getattr(f, "id", None) for f in population]
        assert k == 1, f"SC-MORT expected k==1, got {k}"
        assert target_id in ids, f"SC-MORT target {target_id} not in population {ids}"
        return [f for f in population if getattr(f, "id", None) == target_id]

    monkeypatch.setattr(mortality_service.random, "sample", controlled_sample)
    try:
        resp = mortality_api.execute_mortality_phase(state, player_id)
    finally:
        monkeypatch.setattr(mortality_service.random, "sample", real_sample)
    assert seen.get("k") == 1, "SC-MORT sampler was not invoked with k==1"
    return resp


# ---------------------------------------------------------------------------
# T01 — 非战斗死亡清权威 War 绑定（FC-01/02/03/10）
# ---------------------------------------------------------------------------
def test_t01_mortality_clears_authoritative_war_binding(monkeypatch):
    ctx = build_wpo_state(naval=False)
    state, war, victim = ctx["state"], ctx["war"], ctx["victim"]
    ms = state.get_military_system()

    # raw 前置（禁手置；真实 producer 前置态）
    assert victim.is_dead is False
    assert victim.is_absent is True
    assert victim in state.get_living_members()
    assert war.commander_id == VICTIM_ID
    assert war.original_commander_id == VICTIM_ID
    assert all(l.commander_id == VICTIM_ID for l in ms.get_legions_for_battle(WAR_ID))

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    event = resp["data"]["events"][0]
    assert event["effect"] == "death"
    assert any(i.get("figure_id") == VICTIM_ID for i in event["impacts"])

    # RAW 权威事实（早于任何读 DTO）
    assert state.get_member(VICTIM_ID).is_dead is True
    assert war.commander_id is None
    assert war.commander_status == "killed"
    assert war.original_commander_id is None
    # 生命周期/制海权/条约不变（FC-06）
    assert war.status == WarStatus.ACTIVE
    assert war.sea_control_acquired is False
    assert war.peace_treaty is None
    # 军团人物镜像清理（FC-04）
    for legion in ms.get_legions_for_battle(WAR_ID):
        assert legion.commander_id is None


def test_t01_naval_mortality_clears_fleet_mirror(monkeypatch):
    ctx = build_wpo_state(naval=True)
    state, war = ctx["state"], ctx["war"]
    ns = state.naval_system
    assert all(f.commander_id == VICTIM_ID for f in ns.get_fleets_by_war(NAVAL_WAR_ID))

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    assert war.commander_id is None
    assert war.commander_status == "killed"
    for fleet in ns.get_fleets_by_war(NAVAL_WAR_ID):
        assert fleet.commander_id is None


# ---------------------------------------------------------------------------
# T04 — 资产保全：仅匹配死者镜像改变（FC-03/04 精确 id）
# ---------------------------------------------------------------------------
def test_t04_asset_preservation_and_only_matching_mirror(monkeypatch):
    ctx = build_wpo_state(naval=True, with_unrelated_war=True)
    state, war, unrelated = ctx["state"], ctx["war"], ctx["unrelated"]
    ms = state.get_military_system()
    ns = state.naval_system

    legions_before = {l.number: (l.war_id, l.status, l.is_veteran)
                      for l in ms.get_legions_for_battle(NAVAL_WAR_ID)}
    fleets_before = {f.number: (f.assigned_war_id, f.status, f.experience,
                                f.quality_adjusted_base, f.target_war_id)
                     for f in ns.get_fleets_by_war(NAVAL_WAR_ID)}
    unrelated_before = {l.number: (l.war_id, l.commander_id)
                        for l in ms.get_legions_for_battle(UNRELATED_WAR_ID)}
    war_fields_before = (war.status, war.sea_control_acquired, war.peace_treaty, war.name,
                         war.legions_assigned)

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp

    # 仅匹配死者人物镜像改变；附着/状态/老兵/经验/质量/target 保留
    for l in ms.get_legions_for_battle(NAVAL_WAR_ID):
        w, s, v = legions_before[l.number]
        assert l.commander_id is None
        assert (l.war_id, l.status, l.is_veteran) == (w, s, v)
    for f in ns.get_fleets_by_war(NAVAL_WAR_ID):
        aw, st, ex, q, tw = fleets_before[f.number]
        assert f.commander_id is None
        assert (f.assigned_war_id, f.status, f.experience) == (aw, st, ex)
        assert f.quality_adjusted_base == q
        assert f.target_war_id == tw

    assert (war.status, war.sea_control_acquired, war.peace_treaty, war.name,
            war.legions_assigned) == war_fields_before

    # 无关 War 及其资产零变化（精确 id）
    assert unrelated.commander_id == ALT_ID
    assert unrelated.commander_status == "active"
    for l in ms.get_legions_for_battle(UNRELATED_WAR_ID):
        assert (l.war_id, l.commander_id) == unrelated_before[l.number]


# ---------------------------------------------------------------------------
# T05 — 无自动替补 + 幂等 + 非指挥官死亡不波及无关 War（FC-05/10，含 F-04 共享写点幂等）
# ---------------------------------------------------------------------------
def test_t05_no_replacement_then_idempotent(monkeypatch):
    ctx = build_wpo_state(naval=False)
    state, war, alt = ctx["state"], ctx["war"], ctx["alt"]

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    assert war.commander_id is None
    assert war.commander_id != ALT_ID  # 无自动替补（存活候选在场但不指派）

    # 重复死亡 → False，无二次领域变更（FC-10）
    treasury_after = state.treasury
    land_after = state._national_public_land
    assert state.mark_member_dead(VICTIM_ID) is False
    assert state.treasury == treasury_after
    assert state._national_public_land == land_after
    assert war.commander_id is None
    assert war.commander_status == "killed"

    # 直接 cleanup 重复 = no-op（F-04 共享写点幂等）
    ws = state.get_war_system()
    assert ws.clear_deceased_commander_bindings(VICTIM_ID) == 0
    ms = state.get_military_system()
    for l in ms.get_legions_for_battle(WAR_ID):
        assert l.commander_id is None

    # 缺失人物 → False（现行为）
    assert state.mark_member_dead(99999) is False


def test_t05_noncommander_death_leaves_wars_untouched(monkeypatch):
    ctx = build_wpo_state(naval=True)
    state, war = ctx["state"], ctx["war"]
    ms = state.get_military_system()
    ns = state.naval_system

    resp = run_mortality_for(monkeypatch, state, CONTROL_ID)
    assert resp["success"], resp
    assert state.get_member(CONTROL_ID).is_dead is True

    # 非指挥官死亡 → War/资产不变（精确 id 保护无关绑定）
    assert war.commander_id == VICTIM_ID
    assert war.original_commander_id == VICTIM_ID
    assert war.commander_status == "active"
    for l in ms.get_legions_for_battle(NAVAL_WAR_ID):
        assert l.commander_id == VICTIM_ID
    for f in ns.get_fleets_by_war(NAVAL_WAR_ID):
        assert f.commander_id == VICTIM_ID


# ---------------------------------------------------------------------------
# B4/FC-03 — 显式存活指派重置 commander_status=active（伤亡标记非永久属性）
# ---------------------------------------------------------------------------
def test_b4_explicit_command_resets_casualty_marker(monkeypatch):
    ctx = build_wpo_state(naval=False)
    state, war = ctx["state"], ctx["war"]
    ws = state.get_war_system()

    assert war.commander_status == "active"
    assert war not in ws.get_wars_needing_reassignment()

    resp = run_mortality_for(monkeypatch, state, VICTIM_ID)
    assert resp["success"], resp
    assert war.commander_status == "killed"
    assert war in ws.get_wars_needing_reassignment()  # 死者指挥 → 需重指派

    # 显式成功指派存活 Figure → 恢复 active，不再因死者指挥被标记
    assert ws.assign_commander(WAR_ID, ALT_ID, legions=2, fleets=0) is True
    assert war.commander_id == ALT_ID
    assert war.commander_status == "active"
    assert war not in ws.get_wars_needing_reassignment()
