# src/tests/test_api/test_wrri_acceptance.py
"""EOR20261009-03 WRRI acceptance suite (mandatory new suite — design §9.5).

Covers the frozen core predicates for the War Reward Authority Integrity task:
- FC-11/FC-12  config share schema + snapshot + fail-safe (WRRI-AC-06/07)
- FC-16        plan vs committed receipt (WRRI-AC-01/02/08/09/10/16)
- FC-13/FC-14  monetary conservation + no-faction routing (WRRI-AC-04/05)
- FC-15/OD-04  veteran pool semantics + conservation (WRRI-AC-12/13)
- FC-07/OD-05  persistent war-reward influence (WRRI-AC-14)
- FC-10        persistence boundary (WRRI-AC-15)
- outcome eligibility matrix (WRRI-AC-03/11/17/18)

These are the core-settlement + DTO projection predicates. Full PUBLIC Long-Chain
(real do_combat_action→resolve_war→to_dict/load_from_dict→public vote_triumph→resolve_forum:
LC-04/05/07/10) and SECC dual-state harness (SS-1/2/3/5/6, independent state oracle) are the
ATTEMPT-2 additions in this same suite (design §9.2/§9.3/§9.7); RENDER closure (AC-16/19
default+compact) lives in 03-da-evidence/S2/render/. See attempts/ATTEMPT-2/.
"""

import copy
import json
import logging

import pytest

from src.core.config import Config
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.entities.war import War, WarStatus
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api, forum_api, session_api, game_api, resolution_api


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _make_state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state._treasury = 1000
    return state


@pytest.fixture
def ctx():
    state = _make_state()
    faction = Faction(id="optimates", name="Optimates", treasury=500)
    state.add_faction(faction)
    commander = Figure(id=101, name="指挥官", faction_id=faction.id, wealth=0)
    state.add_member(commander)
    faction.member_ids.append(commander.id)
    war = War(
        id="wrri_war",
        name="WRRI 测试战争",
        strength=5,
        rewards={"treasury": 500, "land": 200, "family_prestige": 1, "influence": 30},
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = commander.id
    ws = WarSystem(state)
    ws._active_wars.append(war)
    state._war_system = ws
    return state, ws, war, commander, faction


# --------------------------------------------------------------------------
# WRRI-AC-07 / WRRI-AC-06 — config schema + snapshot + fail-safe (FC-11/FC-12)
# --------------------------------------------------------------------------
def test_production_config_file_has_four_keys_valid():
    """AC-07: production game_config.json defines the four shares summing to 1.0."""
    c = Config("data/config/game_config.json")
    snap = c.get_reward_share_snapshot()
    assert snap["source"] == "file"
    assert snap["valid"] is True
    assert snap["reason"] is None
    assert set(snap["raw"].keys()) == {
        "treasury_share", "faction_share", "commander_share", "soldier_share"}
    assert abs(sum(snap["effective"].values()) - 1.0) < 1e-9
    assert snap["effective"] == {
        "treasury": 0.50, "faction": 0.25, "commander": 0.15, "soldier": 0.10}


def test_config_defaults_snapshot_valid():
    """AC-07: Config(None) → source=defaults, valid, no missing-key reason."""
    c = Config()
    snap = c.get_reward_share_snapshot()
    assert snap["source"] == "defaults"
    assert snap["valid"] is True
    assert snap["effective"]["soldier"] == 0.10


def test_config_public_memory_assignment_syncs_identity():
    """AC-06/§5.4: public combat_rules four-key assignment → source=memory + re-validate."""
    c = Config()
    c.combat_rules.treasury_share = 0.40
    c.combat_rules.faction_share = 0.30
    c.combat_rules.commander_share = 0.20
    c.combat_rules.soldier_share = 0.10
    snap = c.get_reward_share_snapshot()
    assert snap["source"] == "memory"
    assert snap["valid"] is True
    assert snap["effective"]["treasury"] == 0.40


@pytest.mark.parametrize("key,value,reason", [
    ("treasury_share", 1.5, "out_of_range"),
    ("treasury_share", -0.1, "out_of_range"),
    ("treasury_share", True, "invalid_type"),
    ("treasury_share", float("nan"), "nonfinite"),
    ("treasury_share", "0.5", "invalid_type"),
])
def test_config_invalid_share_falls_back_to_frozen_default(key, value, reason):
    """AC-06/BB06: any invalid share → whole-group frozen default + reason (no crash)."""
    c = Config()
    setattr(c.combat_rules, key, value)
    snap = c.get_reward_share_snapshot()
    assert snap["valid"] is False
    assert snap["reason"] == reason
    assert snap["effective"] == {
        "treasury": 0.50, "faction": 0.25, "commander": 0.15, "soldier": 0.10}


def test_config_sum_mismatch_falls_back():
    """AC-06: sum != 1.0 → fallback + sum_mismatch."""
    c = Config()
    c.combat_rules.soldier_share = 0.15  # others default → sum 1.05
    snap = c.get_reward_share_snapshot()
    assert snap["valid"] is False
    assert snap["reason"] == "sum_mismatch"


def test_war_system_get_reward_shares_emits_fallback_warning(ctx):
    """AC-06: invalid config → WarSystem reads defaults + structured WARNING event."""
    state, ws, war, commander, faction = ctx
    state.config.combat_rules.treasury_share = 1.5  # invalid
    shares = ws.get_reward_shares(state)
    assert shares == {"treasury": 0.50, "faction": 0.25, "commander": 0.15, "soldier": 0.10}
    assert any("奖励份额" in m for m in state._event_log)


# --------------------------------------------------------------------------
# WRRI-AC-02 / AC-04 / AC-08 — authoritative settlement + receipt (FC-02/13/16)
# --------------------------------------------------------------------------
def test_triumph_multiplier_receipt_and_conservation(ctx):
    """AC-02/04: triumph base 500 → total 750; receipt committed; conservation holds."""
    state, ws, war, commander, faction = ctx
    t_before = state.treasury
    f_before = faction.treasury
    c_before = commander.wealth

    ws.resolve_war(war.id, True, combat_result="triumph")

    r = war.reward_receipt
    assert r is not None and r["committed"] is True
    assert r["result"] == "triumph" and r["result_multiplier"] == 1.5
    assert r["total_monetary"] == 750
    assert (r["treasury_part"], r["faction_part"], r["commander_part"], r["pool_part"]) == (375, 187, 112, 76)
    assert war.status == WarStatus.RESOLVED
    # conservation: real state deltas == receipt nominal
    assert state.treasury - t_before == 375
    assert faction.treasury - f_before == 187
    assert commander.wealth - c_before == 112
    assert war.soldier_share == 76
    assert (state.treasury - t_before) + (faction.treasury - f_before) + \
        (commander.wealth - c_before) + war.soldier_share == r["total_monetary"]


def test_victory_no_multiplier(ctx):
    """AC-02: VICTORY → total == base (multiplier 1.0)."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="victory")
    assert war.reward_receipt["total_monetary"] == 500
    assert war.reward_receipt["result_multiplier"] == 1.0


def test_core_second_resolve_is_noop(ctx):
    """AC-04/BB05: second core resolve → deterministic no-op, zero monetary write."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    t_after = state.treasury
    res = ws.resolve_war(war.id, True, combat_result="triumph")
    assert res.get("no_op") is True
    assert state.treasury == t_after


def test_no_faction_routes_to_treasury(ctx):
    """AC-05 (OD-03): commander w/o faction → faction_part to treasury; conservation holds."""
    state, ws, war, commander, faction = ctx
    commander.faction_id = None
    t_before = state.treasury
    ws.resolve_war(war.id, True, combat_result="victory")
    r = war.reward_receipt
    # 500 → t=250, f=125, c=75, pool=50 ; faction_part → treasury
    assert r["faction_target"] == "treasury"
    assert state.treasury - t_before == 250 + 125
    assert r["actual_recipients"]["treasury_delta"] == 375
    assert r["actual_recipients"]["faction_delta"] == 0
    assert r["actual_recipients"]["faction_id"] is None
    assert r["treasury_part"] + r["faction_part"] + r["commander_part"] + r["pool_part"] == r["total_monetary"]


def test_dto_reads_receipt_snapshot(ctx):
    """AC-08/AC-10: DTO reward fields derive from the authoritative receipt (no recompute)."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    r = war.reward_receipt
    view = combat_api._reward_view(war, state, ws, "triumph")
    assert view["reward_status"] == "committed"
    assert view["committed"] is True
    assert view["loot"] == r["total_monetary"]
    assert view["treasury_share"] == r["treasury_part"]
    assert view["faction_share"] == r["faction_part"]
    assert view["commander_share"] == r["commander_part"]
    assert view["soldier_share"] == r["pool_part"]
    assert view["actual_recipients"] == r["actual_recipients"]


def test_dto_changes_with_config_shares(ctx):
    """AC-10: DTO/authoritative split follows the config shares (0.4/0.3/0.2/0.1)."""
    state, ws, war, commander, faction = ctx
    state.config.combat_rules.treasury_share = 0.40
    state.config.combat_rules.faction_share = 0.30
    state.config.combat_rules.commander_share = 0.20
    state.config.combat_rules.soldier_share = 0.10
    ws.resolve_war(war.id, True, combat_result="triumph")
    r = war.reward_receipt
    assert (r["treasury_part"], r["faction_part"], r["commander_part"], r["pool_part"]) == (300, 225, 150, 75)


# --------------------------------------------------------------------------
# WRRI-AC-03 / AC-09 / AC-19 — stalemate projected (FC-09/FC-16, OD-02)
# --------------------------------------------------------------------------
def test_stalemate_projected_view_no_receipt(ctx):
    """AC-03/09/19: draw → no receipt; DTO projected/committed=False; loot 0; projected_loot=base."""
    state, ws, war, commander, faction = ctx
    view = combat_api._reward_view(war, state, ws, "draw")
    assert war.reward_receipt is None
    assert view["reward_status"] == "projected"
    assert view["committed"] is False
    assert view["projected"] is True
    assert view["loot"] == 0
    assert view["projected_loot"] == 500  # neutral success expectation = base treasury
    # projected shares computed by FC-12 on projected_loot
    assert view["projected_shares"]["treasury_share"] == 250


def test_scout_projected_uses_multiplier(ctx):
    """AC-01/§5.2: scout forced triumph → projected uses PLAN total (750), committed loot 0."""
    state, ws, war, commander, faction = ctx
    view = combat_api._reward_view(war, state, ws, "triumph")
    assert view["reward_status"] == "projected"
    assert view["loot"] == 0
    assert view["projected_loot"] == 750
    assert view["projected_shares"]["soldier_share"] == 76


def test_history_unrecorded_when_resolved_without_receipt(ctx):
    """AC-01/§5.3: legacy RESOLVED war w/o receipt → history_unrecorded (null, no recompute)."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.RESOLVED
    view = combat_api._reward_view(war, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"
    assert view["loot"] is None
    assert view["committed"] is False and view["projected"] is False


# --------------------------------------------------------------------------
# WRRI-AC-11 / AC-17 / AC-18 — outcome matrix / land·prestige / rebellion
# --------------------------------------------------------------------------
@pytest.mark.parametrize("result,mult", [
    ("triumph", 1.5), ("victory", 1.0), ("draw", 0.0), ("defeat", 0.0), ("disaster", 0.0),
])
def test_outcome_multiplier_matrix(ctx, result, mult):
    """AC-11: PLAN multiplier per outcome; non-success → 0."""
    state, ws, war, commander, faction = ctx
    plan = ws.compute_reward_settlement(war, result, state)
    assert plan["result_multiplier"] == mult
    if mult == 0.0:
        assert plan["total_monetary"] == 0
        assert plan["land"] == 0 and plan["family_prestige"] == 0 and plan["influence"] == 0


def test_legacy_bool_only_is_neutral_victory(ctx):
    """FC-02/AC-11: legacy None success → victory / legacy_unspecified / multiplier 1.0 (no fake triumph)."""
    state, ws, war, commander, faction = ctx
    plan = ws.compute_reward_settlement(war, None, state)
    assert plan["result"] == "victory"
    assert plan["result_identity_source"] == "legacy_unspecified"
    assert plan["result_multiplier"] == 1.0
    assert plan["total_monetary"] == 500


def test_land_and_prestige_unchanged(ctx):
    """AC-17: land → national public land; family_prestige → commander (verbatim)."""
    state, ws, war, commander, faction = ctx
    commander.family_prestige = 3
    land_before = state.get_national_public_land()
    ws.resolve_war(war.id, True, combat_result="victory")
    assert state.get_national_public_land() == land_before + 200
    assert commander.family_prestige == 4


def test_rebellion_victory_no_settlement(ctx):
    """AC-18: rebellion victory → no monetary settlement, no receipt, prestige +1."""
    state, ws, war, commander, faction = ctx
    province = Province(province_id=999, name="Rebel 999", total_land=1000, conquered=True)
    state.add_province(province)
    war._rebellion_province_id = 999
    commander.family_prestige = 3
    t_before = state.treasury
    ws.resolve_war(war.id, True, combat_result="victory")
    assert war.reward_receipt is None
    assert state.treasury == t_before
    assert commander.family_prestige == 4


# --------------------------------------------------------------------------
# WRRI-AC-12 / AC-13 — veteran pool semantics + conservation (FC-15, OD-04)
# --------------------------------------------------------------------------
def test_veteran_pool_alias(ctx):
    """AC-12: veteran_support_pool is the canonical alias of soldier_share (same storage)."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    assert war.veteran_support_pool == war.soldier_share == 76


def test_forum_reject_refunds_pool_to_treasury(ctx):
    """AC-13: triumph rejected → full pool to Rome treasury; pool zeroed (conserved)."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.RESOLVED
    war.set_triumph_commander(commander.id)
    war.set_soldier_share(50)
    ws._war_discard.append(war)
    state._forum_pending["triumph_votes"] = [(war.id, faction.id, False)]
    t_before = state.treasury
    forum_api.resolve_forum(state)
    assert state.treasury - t_before == 50
    assert war.soldier_share == 0


def test_forum_no_votes_refunds_pool(ctx):
    """AC-13: zero votes → full pool to treasury; pool zeroed."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.RESOLVED
    war.set_triumph_commander(commander.id)
    war.set_soldier_share(50)
    ws._war_discard.append(war)
    t_before = state.treasury
    forum_api.resolve_forum(state)
    assert state.treasury - t_before == 50
    assert war.soldier_share == 0


def test_forum_approve_residual_to_treasury(ctx):
    """AC-13/FC-15: approval with pool<duration*per_turn → residual refunded; per_turn×duration+refund==pool."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.RESOLVED
    war.set_triumph_commander(commander.id)
    war.set_soldier_share(12)  # duration default 5 → per_turn 2, residual 2
    commander.influence = 30  # voter influence so the approval branch is reached
    ws._war_discard.append(war)
    state._forum_pending["triumph_votes"] = [(war.id, faction.id, True)]
    t_before = state.treasury
    forum_api.resolve_forum(state)
    assert state.treasury - t_before == 2
    assert war.soldier_share == 0
    assert war.triumph_approved is True
    assert commander.get_temp_influence() == 2  # per_turn×duration == 10 consumed as political quantity


# --------------------------------------------------------------------------
# WRRI-AC-14 / AC-15 — persistent influence + persistence boundary (FC-07/FC-10)
# --------------------------------------------------------------------------
def test_influence_persisted_and_isolated(ctx):
    """AC-14: commander._war_reward_influence += rewards.influence; survives update_influence."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="victory")
    assert commander._war_reward_influence == 30
    # update_influence recomputes deterministically and retains the persistent bonus.
    commander.update_influence()
    v = commander.influence
    commander.update_influence()
    assert commander.influence == v
    assert v >= 30


def test_influence_survives_save_load(ctx):
    """AC-14/15: _war_reward_influence round-trips through Figure.to_dict/from_dict."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="victory")
    clone = Figure.from_dict(commander.to_dict())
    assert clone._war_reward_influence == 30


def test_receipt_survives_war_save_load(ctx):
    """AC-15: receipt (committed) round-trips through War.to_dict/from_dict verbatim."""
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    original = war.reward_receipt
    clone = War.from_dict(war.to_dict())
    assert clone.reward_receipt == original
    assert clone.soldier_share == war.soldier_share


def test_legacy_figure_without_key_defaults_zero():
    """AC-14/FC-10: old Figure dict without _war_reward_influence → 0 (no backfill)."""
    f = Figure(id=7, name="Legacy")
    d = f.to_dict()
    d.pop("_war_reward_influence", None)
    clone = Figure.from_dict(d)
    assert clone._war_reward_influence == 0


# ==========================================================================
# ATTEMPT-2 — Full PUBLIC Long-Chain harness (design §9.2/§9.3; NON unit-only)
# and SECC dual-state formal harness (design §9.7 SS-1..SS-4).
#
# Every transition owner is invoked through its PUBLIC seam:
#   combat_api.do_combat_action → WarSystem.resolve_war ;
#   GameState.to_dict / load_from_dict ;
#   forum_api.get_forum_view → vote_triumph → resolve_forum.
# Forbidden by design (§9.3 "No Test-Assisted Transition"): seeding
# `add_forum_action("triumph_votes", ...)`, hand-setting `war.status=RESOLVED`,
# hand-seeding the veteran pool / receipt, or calling the downstream settle/
# reward functions instead of the public transition owner. NONE are used here.
# Scenario control = `testing.force_battle_result` (canonical producer override)
# and public `vote_triumph` only (design §9.4).
# ==========================================================================


def _attack_state(force="triumph", base_treasury=500, with_faction=True,
                  player_id="player_opt", faction_id="optimates",
                  bonus_influence=30, rebellion_province_id=None):
    """Real producer entry state: ACTIVE land war + live commander/faction/legions
    + legal Combat current player. Nothing is settled until the real attack runs.
    Mirrors the canonical WP-G public producer chain (recruit → assign → attack).

    EOR20261009-03 ATTEMPT-3 R03: **no** `testing.bypass_player_check` — the harness sets
    a *real* current player and every transition runs through the legal public owner
    (design §9.3 "No Test-Assisted Transition")."""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=8, year=-270)
    state._treasury = 1000
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    faction = None
    if with_faction:
        faction = Faction(id=faction_id, name="Faction", treasury=500)
        state.add_faction(faction)
    player = Player(player_id=player_id,
                    faction_id=faction_id if with_faction else None,
                    player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player(player_id)
    commander = Figure(id=101, name="指挥官",
                       faction_id=faction_id if with_faction else None, age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    state.add_member(commander)
    if faction:
        faction.member_ids.append(101)
    war = War(id="lc_war", name="LC War", strength=5, threat_level=3,
              rewards={"treasury": base_treasury, "land": 0,
                       "family_prestige": 0, "influence": bonus_influence},
              naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
              rebellion_province_id=rebellion_province_id)
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)
    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit {num}"
    assigned, msg = ms.assign_to_war([1, 2], war.id, 101)
    assert assigned == 2, msg
    state.config.testing.force_battle_result = force
    return state, war, commander, faction, player_id


def _real_attack(state, war, player_id):
    """Public transition owner (combat_api.do_combat_action = production seam)."""
    attack = combat_api.do_combat_action(state, player_id, war.id, "attack")
    assert attack["success"], attack.get("message")
    return attack


def _set_forum_market_window(state, player_id="player_opt"):
    """Phase-context control (design §9.3): declares the Forum market window for the
    current voter so the public vote window is open. This is NOT a transition bypass —
    vote_triumph / resolve_forum remain the real owners."""
    state.mark_phase_executed("mortality")
    state.mark_phase_executed("revenue")
    state.add_forum_action("market_opened", player_id)


# --------------------------------------------------------------------------
# LC-04 / AC-13 — real attack pool → PUBLIC vote (approve) → resolve_forum
# --------------------------------------------------------------------------
def test_lc04_real_attack_public_vote_approval_pool_political_conversion():
    """LC-04: real attack produces the pool → PUBLIC vote_triumph True → resolve_forum.
    Pool → commander temp influence (political conversion); pool zeroed; conservation
    per_turn*duration + refund == pool."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    pool = war.soldier_share
    assert pool == 76
    _set_forum_market_window(state, pid)
    vote = forum_api.vote_triumph(state, pid, war.id, True)
    assert vote["success"], vote.get("message")
    assert any(v[0] == war.id and v[2] is True
               for v in state.get_forum_pending()["triumph_votes"])
    duration = state.config.get("combat_rules.triumph_veteran_duration", 5)
    per_turn = pool // duration
    refund = pool - per_turn * duration
    t_before = state.treasury
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    assert war.triumph_approved is True
    assert war.soldier_share == 0
    assert state.treasury - t_before == refund
    assert per_turn * duration + refund == pool            # FC-15 metering invariant
    assert commander.get_temp_influence() == per_turn


# --------------------------------------------------------------------------
# LC-05 / AC-13 — real attack pool → PUBLIC vote (reject) → resolve_forum
# --------------------------------------------------------------------------
def test_lc05_real_attack_public_vote_rejection_pool_to_treasury():
    """LC-05: real attack pool → PUBLIC vote_triumph False (support ≤ 50%) → resolve_forum.
    Full pool → Rome treasury; pool zeroed (conserved; money does not vanish)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    pool = war.soldier_share
    assert pool == 76
    _set_forum_market_window(state, pid)
    vote = forum_api.vote_triumph(state, pid, war.id, False)
    assert vote["success"], vote.get("message")
    t_before = state.treasury
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    assert state.treasury - t_before == pool
    assert war.soldier_share == 0
    assert war.triumph_approved is False


# --------------------------------------------------------------------------
# LC-10 / AC-13,AC-15 — small pool → PUBLIC approve → treasury refund, no temp
# --------------------------------------------------------------------------
def test_lc10_small_pool_public_approval_refunds_no_temp_task():
    """LC-10: forced victory base 20 → pool 2 (< duration) → PUBLIC vote True →
    resolve_forum → per_turn 0 → full pool refunded to treasury; pool 0; no temp task."""
    state, war, commander, faction, pid = _attack_state(force="victory", base_treasury=20)
    _real_attack(state, war, pid)
    assert war.soldier_share == 2
    _set_forum_market_window(state, pid)
    assert forum_api.vote_triumph(state, pid, war.id, True)["success"]
    t_before = state.treasury
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    assert state.treasury - t_before == 2
    assert war.soldier_share == 0
    assert commander.get_temp_influence() == 0


# --------------------------------------------------------------------------
# LC-07 / AC-15 (= SECC SS-4) — real attack → serialize → restore → PUBLIC
#   vote_triumph → resolve_forum (full integrated public chain)
# --------------------------------------------------------------------------
def test_lc07_real_attack_serialize_restore_public_vote_resolve():
    """LC-07 / AC-15 / SS-4: real attack → GameState.to_dict/load_from_dict →
    public get_forum_view → vote_triumph → resolve_forum. Pool/receipt/bonus verbatim
    after restore; real vote persisted; single political conversion + refund; receipt
    remains the original committed snapshot (config change does not rewrite history)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    assert war.status == WarStatus.RESOLVED
    receipt_before = dict(war.reward_receipt)
    pool_before = war.soldier_share
    bonus_before = commander._war_reward_influence
    assert receipt_before["committed"] is True
    assert pool_before == 76 and bonus_before == 30

    # real serialization seam (not an approximation of save/load); real current player,
    # NO bypass (ATTEMPT-3 R03)
    data = state.to_dict()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)
    restored.set_current_player(pid)
    rws = restored.get_war_system()
    rwar = rws.get_war_by_id(war.id)
    rcmd = restored.get_member(commander.id)
    assert rwar is not None
    assert rwar.reward_receipt == receipt_before        # verbatim
    assert rwar.soldier_share == pool_before            # verbatim
    assert rcmd._war_reward_influence == bonus_before   # verbatim

    # config change after commit must NOT rewrite the historical receipt snapshot
    restored.config.combat_rules.soldier_share = 0.40
    assert rwar.reward_receipt == receipt_before

    # public Forum chain: view → vote → resolve (real vote, real owner)
    _set_forum_market_window(restored, pid)
    view = forum_api.get_forum_view(restored, pid)
    assert view["success"], view.get("message")
    assert [r["war_id"] for r in view["data"]["triumph_wars"]] == [war.id]
    assert forum_api.vote_triumph(restored, pid, war.id, True)["success"]
    assert any(v[0] == war.id and v[2] is True
               for v in restored.get_forum_pending()["triumph_votes"])

    duration = restored.config.get("combat_rules.triumph_veteran_duration", 5)
    per_turn = pool_before // duration
    refund = pool_before - per_turn * duration
    t_before = restored.treasury
    settled = forum_api.resolve_forum(restored)
    assert settled["success"], settled.get("message")
    assert restored.treasury - t_before == refund
    assert rwar.soldier_share == 0
    assert rwar.triumph_approved is True
    assert restored.get_member(commander.id).get_temp_influence() == per_turn
    assert rwar.reward_receipt == receipt_before        # still original snapshot

    # second resolve: no double reward / no re-approval
    settled2 = forum_api.resolve_forum(restored)
    assert settled2["success"]
    assert "凯旋仪式获得批准" not in " ".join(settled2["data"]["results"])
    assert rwar.soldier_share == 0


# ==========================================================================
# SECC dual-state formal harness (design §9.7 SS-1..SS-3)
#   INPUT → PLAN → APPLY → PERSISTED STATE → DTO, with an INDEPENDENT oracle
#   (= real GameState deltas / receipt fields; NOT the DTO helper recomputing).
# ==========================================================================
def test_secc_ss1_triumph_plan_apply_persisted_dto_parity():
    """SS-1 TRIUMPH (ordinary, base 500): PLAN pure (zero mutation) → APPLY real
    resolver → PERSISTED real deltas → DTO reads receipt; all three equal item-wise."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    ws = state.get_war_system()
    t0, f0, c0 = state.treasury, faction.treasury, commander.wealth

    # PLAN — pure computation, zero mutation
    plan = ws.compute_reward_settlement(war, "triumph", state)
    assert (plan["total_monetary"], plan["treasury_part"], plan["faction_part"],
            plan["commander_part"], plan["pool_part"]) == (750, 375, 187, 112, 76)
    assert plan["committed"] is False
    assert (state.treasury, faction.treasury, commander.wealth) == (t0, f0, c0)

    # APPLY — real public producer
    _real_attack(state, war, pid)
    r = war.reward_receipt

    # PERSISTED STATE — independent oracle = real GameState deltas
    assert state.treasury - t0 == 375
    assert faction.treasury - f0 == 187
    assert commander.wealth - c0 == 112
    assert war.soldier_share == 76
    assert (state.treasury - t0) + (faction.treasury - f0) + \
        (commander.wealth - c0) + war.soldier_share == 750
    assert r["actual_recipients"] == {"treasury_delta": 375, "faction_delta": 187,
                                     "commander_delta": 112, "faction_id": "optimates",
                                     "commander_id": 101, "pool_held": 76}

    # DTO — reads the authoritative receipt snapshot
    view = combat_api._reward_view(war, state, ws, "triumph")
    assert view["committed"] is True and view["reward_status"] == "committed"
    assert view["loot"] == r["total_monetary"] == 750
    assert view["treasury_share"] == r["treasury_part"] == 375
    assert view["faction_share"] == r["faction_part"] == 187
    assert view["commander_share"] == r["commander_part"] == 112
    assert view["soldier_share"] == r["pool_part"] == 76
    # independent influence oracle: persistent war-reward influence = rewards.influence
    assert commander._war_reward_influence == 30


def test_secc_ss2_stalemate_boundary_zero_and_projected():
    """SS-2 STALEMATE (boundary): forced stalemate → draw → TRUCE; no receipt;
    zero monetary delta (independent oracle); DTO projected with committed loot 0."""
    state, war, commander, faction, pid = _attack_state(force="stalemate", base_treasury=500)
    ws = state.get_war_system()
    t0, f0, c0 = state.treasury, faction.treasury, commander.wealth
    _real_attack(state, war, pid)
    assert war.status == WarStatus.TRUCE
    assert war.reward_receipt is None
    # zero-value oracle: real deltas are all zero
    assert (state.treasury, faction.treasury, commander.wealth) == (t0, f0, c0)
    assert war.soldier_share == 0
    # DTO projected (from PLAN), projected_loot = base, committed loot 0
    view = combat_api._reward_view(war, state, ws, "draw")
    assert view["committed"] is False and view["projected"] is True
    assert view["loot"] == 0
    assert view["projected_loot"] == 500
    assert view["projected_shares"] == {"treasury_share": 250, "faction_share": 125,
                                        "commander_share": 75, "soldier_share": 50}


def test_secc_ss3_no_faction_nominal_vs_actual():
    """SS-3 no-faction commander (boundary): nominal split 250/125/75/50 but ACTUAL
    faction_part routed to treasury (375), faction_delta 0 — nominal must NOT be
    equated to actual. Independent oracle = real GameState deltas."""
    state, war, commander, faction, pid = _attack_state(
        force="victory", base_treasury=500, with_faction=False)
    ws = state.get_war_system()
    t0, c0 = state.treasury, commander.wealth

    plan = ws.compute_reward_settlement(war, "victory", state)
    assert (plan["treasury_part"], plan["faction_part"],
            plan["commander_part"], plan["pool_part"]) == (250, 125, 75, 50)
    assert plan["faction_target"] == "treasury"

    _real_attack(state, war, pid)
    r = war.reward_receipt
    # nominal == receipt parts
    assert r["total_monetary"] == 500
    assert (r["treasury_part"], r["faction_part"],
            r["commander_part"], r["pool_part"]) == (250, 125, 75, 50)
    # actual == independent real deltas
    assert state.treasury - t0 == 375
    assert commander.wealth - c0 == 75
    assert war.soldier_share == 50
    assert r["actual_recipients"]["treasury_delta"] == 375
    assert r["actual_recipients"]["faction_delta"] == 0
    assert r["actual_recipients"]["faction_id"] is None
    assert r["actual_recipients"]["commander_delta"] == 75
    # nominal ≠ actual for the rerouted faction part
    assert r["faction_part"] != r["actual_recipients"]["faction_delta"]


# ==========================================================================
# SECC SS5/SS6 — influence preview NEW-term claim dual-state (design §9.7)
#   bonus30 produced by a real attack; components set before production;
#   PREVIEW (_build_resolution_preview, read-only) vs APPLY (game_api.advance_year)
#   with an INDEPENDENT arithmetic oracle (manual arithmetic, NOT _compute_influence).
# ==========================================================================
def _influence_preview_state(task_duration):
    """Single-member faction; persistent bonus30 produced by a real public attack;
    to_dict/load_from_dict restored; components (land2/vet5/pop20/prestige3/quaestor)
    set before production; temp task via public add_temp_influence_task.

    EOR20261009-03 ATTEMPT-3 R03: no `bypass_player_check`; real current player only."""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=8, year=-270)
    state._treasury = 1000
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    faction = Faction(id="optimates", name="Faction", treasury=500)
    state.add_faction(faction)
    state.add_player(Player("player_opt", "optimates", PlayerType.HUMAN))
    state.set_current_player("player_opt")
    commander = Figure(id=101, name="指挥官", faction_id="optimates", age=40)
    commander.martial = 4
    commander._land_private = 2
    commander.veterans = 5
    commander.popularity = 20
    commander.family_prestige = 3
    commander.office = "quaestor"
    commander.is_absent = True
    commander.add_temp_influence_task(7, task_duration)
    state.add_member(commander)
    faction.member_ids.append(101)
    commander.update_influence()
    war = War(id="lc_war", name="LC War", strength=5, threat_level=3,
              rewards={"treasury": 100, "land": 0, "family_prestige": 0, "influence": 30},
              naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99])
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)
    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok
    ms.assign_to_war([1, 2], war.id, 101)
    state.config.testing.force_battle_result = "victory"
    _real_attack(state, war, "player_opt")   # real producer grants persistent bonus30
    data = state.to_dict()
    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)
    restored.set_current_player("player_opt")
    return restored, restored.get_member(101), faction.id, "player_opt"


def _ss56_run(task_duration, temp_after, expect_after):
    restored, rcmd, fid, pid = _influence_preview_state(task_duration)
    # pre-decay (post-attack) baseline — independent arithmetic oracle (no _compute_influence)
    before = 2 * 10 + 5 * 10 + 20 + 3 * 10 + 10 + 7 + 30
    assert before == 167
    assert rcmd.influence == before
    assert rcmd._war_reward_influence == 30

    # PREVIEW — PUBLIC read-only projection (`session_api.get_resolution_view`);
    # independent arithmetic oracle (manual, NOT _compute_influence)
    view = session_api.get_resolution_view(restored, pid)
    assert view["success"], view.get("message")
    row = next(r for r in view["data"]["preview"]["faction_influence"]
               if r["faction_id"] == fid)
    after_manual = 2 * 10 + 4 * 10 + 10 + 3 * 10 + 10 + temp_after + 30
    assert row["influence_before"] == before
    assert row["influence_after"] == after_manual == expect_after
    assert row["influence_delta"] == expect_after - before
    assert rcmd.influence == before            # preview zero mutation

    # APPLY — real public annual owner: combat done → resolution phase → advance_year.
    # No direct phase marker / private apply; combat consumed by public advance owner.
    assert combat_api.advance_combat(restored, pid)["success"]
    assert resolution_api.execute_resolution(restored, pid)["success"]
    res = game_api.advance_year(restored, pid)
    assert res["success"], res.get("message")
    # PERSISTED observable
    assert rcmd.influence == expect_after
    assert rcmd._war_reward_influence == 30    # bonus survives
    assert rcmd.office == "quaestor" and rcmd.get_office_influence_bonus() == 10  # office fixed
    assert rcmd.family_prestige == 3           # prestige fixed
    settlement = restored.get_resolution_settlement()
    decay_row = next(r for r in settlement["decay"] if r["figure_id"] == 101)
    assert decay_row["influence_after"] == expect_after
    assert decay_row["influence_delta_decay"] == expect_after - before
    # save/load round-trip retains the persisted influence + bonus
    clone = GameState.create_for_testing({})
    clone.load_from_dict(restored.to_dict())
    assert clone.get_member(101).influence == expect_after
    assert clone.get_member(101)._war_reward_influence == 30


def test_secc_ss5_influence_preview_ordinary_task_survives():
    """SS5 ordinary: temp task remaining 2 → survives decay → after 147 / delta -20."""
    _ss56_run(task_duration=2, temp_after=7, expect_after=147)


def test_secc_ss6_influence_preview_boundary_task_expires():
    """SS6 boundary: temp task remaining 1 → expires → after 140 / delta -27."""
    _ss56_run(task_duration=1, temp_after=0, expect_after=140)


# ==========================================================================
# ATTEMPT-3 (R01/R02/R03) — receipt fail-closed, public DTO / reload / CLI /
# malformed·history / idempotency / real-production closure (design §5.3/§9.2/§9.3).
# No `testing.bypass_player_check`; public transitions only.
# ==========================================================================

# ---- R01: receipt fail-closed (persistence + DTO) ----

def test_reward_view_malformed_receipt_fail_closed_no_crash(ctx):
    """R01/§5.3: present-but-malformed receipt ({"committed":true}) is NOT committed and
    must NOT crash (old code did receipt["total_monetary"] → KeyError); DTO fails closed to
    history_unrecorded + structured WARNING on the same event log."""
    state, ws, war, commander, faction = ctx
    war.set_reward_receipt({"committed": True})   # malformed (missing required keys)
    view = combat_api._reward_view(war, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"
    assert view["committed"] is False and view["projected"] is False
    assert view["loot"] is None and view["treasury_share"] is None
    assert any("receipt 校验失败" in m for m in state._event_log)
    assert war.has_valid_receipt() is False


def test_war_load_malformed_receipt_fail_closed(ctx):
    """R01/§5.3: malformed / wrong-war_id receipt survives load but is never authoritative;
    raw preserved; DTO history_unrecorded."""
    state, ws, war, commander, faction = ctx
    d = war.to_dict()
    d["reward_receipt"] = {"committed": True, "war_id": "other"}
    clone = War.from_dict(d)
    assert clone.reward_receipt == {"committed": True, "war_id": "other"}   # raw preserved
    assert clone.has_valid_receipt() is False
    view = combat_api._reward_view(clone, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"


def test_war_load_empty_receipt_preserved_distinct_from_none(ctx):
    """R01: empty {} receipt is preserved (present) — NOT collapsed to None — so the raw
    present-but-malformed diagnostic distinguishes it from an absent receipt."""
    state, ws, war, commander, faction = ctx
    d = war.to_dict()
    d["reward_receipt"] = {}
    assert War.from_dict(d).reward_receipt == {}      # preserved, not None
    d2 = war.to_dict()
    d2["reward_receipt"] = None
    assert War.from_dict(d2).reward_receipt is None


def test_core_guard_historical_resolved_no_resettle(ctx):
    """R01/FC-06: historical RESOLVED without receipt must never become re-settleable."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.RESOLVED
    t0, f0 = state.treasury, faction.treasury
    res = ws.resolve_war(war.id, True, combat_result="victory")
    assert res.get("no_op") is True
    assert war.reward_receipt is None
    assert (state.treasury, faction.treasury) == (t0, f0)


def test_core_guard_defeated_history_no_resettle(ctx):
    """R01/FC-06: retired DEFEATED history without receipt → no-op (no new settlement)."""
    state, ws, war, commander, faction = ctx
    war.status = WarStatus.DEFEATED
    t0 = state.treasury
    assert ws.resolve_war(war.id, True, combat_result="victory").get("no_op") is True
    assert state.treasury == t0


def test_core_guard_discard_membership_no_resettle(ctx):
    """R01/FC-06: war in _war_discard (ended membership) → no-op even if status is stale."""
    state, ws, war, commander, faction = ctx
    ws._war_discard.append(war)
    war.status = WarStatus.ACTIVE      # stale status field after a real end
    t0 = state.treasury
    assert ws.resolve_war(war.id, True, combat_result="victory").get("no_op") is True
    assert state.treasury == t0


def test_receipt_validator_combination_and_finite(ctx):
    """R01/§5.1: validator enforces result↔source↔multiplier combination, finite shares,
    wrong war_id — not independent membership checks (NaN cannot pass the sum)."""
    from src.core.entities.war import validate_reward_receipt
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    good = war.reward_receipt
    assert validate_reward_receipt(good, war.id) is True
    bad = dict(good)
    bad["result_multiplier"] = 1.0            # triumph must be 1.5
    assert validate_reward_receipt(bad, war.id) is False
    bad2 = copy.deepcopy(good)
    bad2["identity_capture"]["shares_effective"]["treasury"] = float("nan")
    assert validate_reward_receipt(bad2, war.id) is False
    assert validate_reward_receipt(good, "not_this_war") is False
    bad3 = copy.deepcopy(good)
    bad3["identity_capture"]["shares_effective"]["treasury"] = True
    assert validate_reward_receipt(bad3, war.id) is False


# ---- R02: public DTO (get_combat_view) + envelope.land aliases ----

def test_public_combat_view_resolved_card_reads_receipt():
    """R02/AC-08/AC-10: public `get_combat_view` resolved card + battle_results carry the
    authoritative committed reward (NOT the private `_reward_view` helper)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    rec = war.reward_receipt
    view = combat_api.get_combat_view(state, pid)
    assert view["success"], view.get("message")
    card = next(c for c in view["data"]["resolved_war_cards"] if c["war_id"] == war.id)
    land = card["result"]["land"]
    assert land["reward_status"] == "committed" and land["committed"] is True
    assert land["loot"] == rec["total_monetary"] == 750
    assert land["treasury_share"] == rec["treasury_part"] == 375
    assert land["faction_share"] == rec["faction_part"] == 187
    assert land["commander_share"] == rec["commander_part"] == 112
    assert land["soldier_share"] == rec["pool_part"] == 76
    assert land["actual_recipients"] == rec["actual_recipients"]


def test_envelope_land_alias_equals_toplevel_and_receipt():
    """R02/§5.2: `do_combat_action` envelope.land reward fields are equal to the top-level
    aliases and to the authoritative receipt (no independent recomputation)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    attack = _real_attack(state, war, pid)
    env = attack["data"]
    rec = war.reward_receipt
    land = env["land"]
    for k in ("loot", "treasury_share", "faction_share", "commander_share",
              "soldier_share", "reward_status", "committed", "actual_recipients"):
        assert land[k] == env[k], k
    assert land["loot"] == rec["total_monetary"]
    assert env["result"] == "triumph" and env["land"]["executed"] is True


# ---- R02: T7 rounding / FC-01 missing key ----

def test_rounding_total_101_conservation():
    """R02/T7/FC-12: total 101 → floor three parts + pool residual; conservation holds."""
    state, war, commander, faction, pid = _attack_state(force="victory", base_treasury=101)
    _real_attack(state, war, pid)
    rec = war.reward_receipt
    assert rec["total_monetary"] == 101
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (50, 25, 15, 11)
    assert (rec["treasury_part"] + rec["faction_part"] + rec["commander_part"]
            + rec["pool_part"]) == 101


def test_missing_reward_treasury_key_zero():
    """R02/FC-01: missing treasury key → 0 (no write); committed receipt total 0."""
    state, war, commander, faction, pid = _attack_state(force="victory", base_treasury=0)
    war._rewards = {"land": 5}      # no treasury/influence keys
    attack = _real_attack(state, war, pid)
    rec = war.reward_receipt
    assert rec["total_monetary"] == 0
    assert attack["data"]["land"]["loot"] == 0


# ---- R02: config reload consumed by next real attack (BB06) ----

def test_config_file_reload_consumed_by_next_real_attack(tmp_path):
    """R02/BB06: valid file reload (new identity hash) is consumed by the next real attack;
    failed reload (bad JSON) preserves raw/effective/hash verbatim."""
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"combat_rules": {
        "treasury_share": 0.40, "faction_share": 0.30,
        "commander_share": 0.20, "soldier_share": 0.10}}), encoding="utf-8")

    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=1000)
    cfg = state.config
    cfg._config_path = str(cfg_path)
    assert cfg.reload() is True
    snap = cfg.get_reward_share_snapshot()
    assert snap["valid"] is True and snap["source"] == "file"
    assert snap["effective"]["treasury"] == 0.40
    v_hash = snap["config_version"]

    state.config.testing.force_battle_result = "triumph"   # reload reset config; re-arm control
    _real_attack(state, war, pid)
    rec = war.reward_receipt
    # base 1000 × 1.5 = 1500 → 600/450/300/150
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (600, 450, 300, 150)
    assert rec["identity_capture"]["config_version"] == v_hash

    cfg_path.write_text("{ not json", encoding="utf-8")
    assert cfg.reload() is False
    assert cfg.get_reward_share_snapshot()["config_version"] == v_hash


def test_config_reload_invalid_shares_uses_default(tmp_path):
    """R02/BB06: legal JSON but invalid shares (sum≠1.0) → load succeeds, whole group default."""
    cfg_path = tmp_path / "cfg2.json"
    cfg_path.write_text(json.dumps({"combat_rules": {
        "treasury_share": 0.50, "faction_share": 0.25,
        "commander_share": 0.15, "soldier_share": 0.15}}), encoding="utf-8")   # sum 1.05
    c = Config(str(cfg_path))
    snap = c.get_reward_share_snapshot()
    assert snap["valid"] is False and snap["reason"] == "sum_mismatch"
    assert snap["effective"]["soldier"] == 0.10   # frozen default


def test_share_inf_fallback_warning_and_attack_uses_default():
    """R02/BB06: +Inf share → fallback default + structured WARNING; next real attack uses
    the frozen default shares (375/187/112/76 on base 500)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    state.config.combat_rules.treasury_share = float("inf")
    state.config.combat_rules.faction_share = 0.25
    state.config.combat_rules.commander_share = 0.15
    state.config.combat_rules.soldier_share = 0.10
    snap = state.config.get_reward_share_snapshot()
    assert snap["valid"] is False and snap["reason"] == "nonfinite"
    assert snap["effective"] == {"treasury": 0.50, "faction": 0.25,
                                 "commander": 0.15, "soldier": 0.10}
    _real_attack(state, war, pid)
    rec = war.reward_receipt
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (375, 187, 112, 76)
    assert any("奖励份额" in m for m in state._event_log)


# ---- R02: CLI public seam (LC-11) ----

def test_cli_combat_command_execute_produces_receipt():
    """R02/LC-11: CLI `CombatCommand.execute` → `auto_resolve_combat` → `resolve_war`
    produces the authoritative committed receipt (public CLI seam)."""
    from src.ui.commands.phase_combat import CombatCommand
    state, war, commander, faction, pid = _attack_state(force="victory", base_treasury=200)
    state.mark_phase_executed("senate")     # phase-context control (senate precedes combat)
    assert CombatCommand(state).execute([]) is True
    assert war.status == WarStatus.RESOLVED
    rec = war.reward_receipt
    assert rec is not None and rec["committed"] is True
    assert rec["total_monetary"] == 200
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (100, 50, 30, 20)


# ---- R02: real rebellion public path (T16) ----

def test_rebellion_public_attack_no_reward_grievance_cleared():
    """R02/AC-18/T16: real rebellion attack victory → no monetary settlement / no receipt,
    grievance → 0, rebellion flag cleared, commander family_prestige +1."""
    state, war, commander, faction, pid = _attack_state(
        force="victory", rebellion_province_id=999)
    prov = Province(province_id=999, name="Rebel", total_land=1000, conquered=True)
    state.add_province(prov)
    prov.set_grievance(3)
    prov.set_event_flag("rebellion_active", True)
    commander.family_prestige = 3
    t0 = state.treasury
    _real_attack(state, war, pid)
    assert war.reward_receipt is None
    assert state.treasury == t0
    assert prov.grievance == 0
    assert not prov.event_flags.get("rebellion_active")
    assert commander.family_prestige == 4


# ---- R02: real no-vote / invalid-commander refund variants (AC-13/T13) ----

def test_forum_no_vote_real_attack_refunds_pool():
    """R02/AC-13/T13: real attack pool + NO public vote → resolve_forum refunds full pool;
    pool zeroed; no temp influence."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    assert war.soldier_share == 76
    _set_forum_market_window(state, pid)
    t0 = state.treasury
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    assert state.treasury - t0 == 76
    assert war.soldier_share == 0
    assert commander.get_temp_influence() == 0


def test_forum_dead_commander_real_attack_refunds_pool():
    """R02/AC-13/T13: real attack pool → commander dies (post-attack scenario event) →
    public resolve_forum refunds the full pool; pool zeroed."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    assert war.soldier_share == 76
    commander.is_dead = True     # scenario event control (design §9.3)
    _set_forum_market_window(state, pid)
    t0 = state.treasury
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    assert state.treasury - t0 == 76
    assert war.soldier_share == 0


# ---- R02: idempotency (BB05 + LC12) ----

def test_repeat_attack_and_core_idempotency_no_double_write():
    """R02/BB05+LC12: second real attack is refused (combat guard) AND a second direct core
    resolve is a no-op; balances / bonus / pool / receipt unchanged."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    t1 = state.treasury
    bonus1 = commander._war_reward_influence
    rec1 = copy.deepcopy(war.reward_receipt)
    assert bonus1 == 30
    second = combat_api.do_combat_action(state, pid, war.id, "attack")
    assert second["success"] is False
    assert state.get_war_system().resolve_war(
        war.id, True, combat_result="triumph").get("no_op") is True
    assert state.treasury == t1
    assert commander._war_reward_influence == bonus1
    assert war.reward_receipt == rec1


# ==========================================================================
# ATTEMPT-4 (evidence-contract addendum v3.1) — public read-boundary receipt
# fail-closed, public mandatory conjunctions (BB01/02/03/04/06, modified-share
# consumer, public draw confirm), and validator bool-hardening.
# All load-bearing seams = PUBLIC; no `testing.bypass_player_check` (BYPASS=NONE).
# ==========================================================================

def _capture_events(state):
    """Independent test-side observation of structured `log_event` calls (extra shape).
    Wraps the method; does not alter production behaviour (message still delivered)."""
    captured = []
    orig = state.log_event

    def _rec(message, level=logging.INFO, extra=None):
        captured.append({"message": message, "level": level, "extra": dict(extra or {})})
        orig(message, level=level, extra=extra)

    state.log_event = _rec
    return captured


# ---- F01.1 (ATTEMPT-4): non-dict persisted receipt fail-closed on the DTO boundary ----

@pytest.mark.parametrize("bad", [[], "garbage", 5, True])
def test_non_dict_persisted_receipt_fail_closed_public_read(bad):
    """F01/addendum §1.4(4): a persisted NON-dict malformed receipt on an ACTIVE (unsettled)
    war must fail-closed to history_unrecorded at the DTO read boundary; it must NOT fall
    through to PLAN/projected (the pre-fix bug G5 F01.1)."""
    state = _make_state()
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w_bad", name="Bad", strength=5, rewards={"treasury": 500})
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)
    war.set_reward_receipt(bad)          # present, persisted-shape, invalid
    assert war.has_valid_receipt() is False
    view = combat_api._reward_view(war, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"
    assert view["committed"] is False and view["projected"] is False
    assert view["loot"] is None
    assert any("receipt 校验失败" in m for m in state._event_log)


def test_non_dict_persisted_receipt_survives_load_then_fail_closed(ctx):
    """F01: a JSON-list persisted receipt round-trips verbatim (raw-preserved for audit) but
    is never authoritative; DTO fails closed."""
    state, ws, war, commander, faction = ctx
    d = war.to_dict()
    d["reward_receipt"] = []
    clone = War.from_dict(d)
    assert clone.reward_receipt == []          # verbatim
    assert clone.has_valid_receipt() is False
    view = combat_api._reward_view(clone, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"
    assert view["loot"] is None


# ---- F01.2 (ATTEMPT-4): public read boundary downgrades stale committed results ----

def test_public_read_boundary_downgrades_stale_committed_result():
    """F01.2/addendum §1.4(4) E-SECC-5: a loaded stale committed result paired with an
    absent receipt must NOT remain player-visible committed at the public read boundary
    (`get_combat_view`), including pending_result + war_results."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    # legacy archive: the persisted receipt is lost while the stale committed DTO remains
    data = state.to_dict()
    for wd in data["_war_system"]["_war_discard"]:
        if wd["id"] == war.id:
            wd["reward_receipt"] = None
    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)
    restored.set_current_player(pid)
    rws = restored.get_war_system()
    rwar = rws.get_war_by_id(war.id)
    assert rwar is not None and rwar.reward_receipt is None
    view = combat_api.get_combat_view(restored, pid)
    assert view["success"], view.get("message")
    card = next(c for c in view["data"]["resolved_war_cards"] if c["war_id"] == war.id)
    land = card["result"]["land"]
    assert land["reward_status"] == "history_unrecorded"
    assert land["committed"] is False and land["loot"] is None
    for b in view["data"]["battle_results"]:
        if b.get("war_id") == war.id:
            assert b["land"]["reward_status"] == "history_unrecorded"
            assert b["committed"] is False


# ---- F01.3 (ATTEMPT-4): validator rejects bool schema_version / bool multiplier ----

def test_validator_rejects_bool_schema_and_multiplier(ctx):
    """F01.3: bool `True` (== 1 / == 1.0 in Python) must NOT satisfy schema/multiplier."""
    from src.core.entities.war import validate_reward_receipt
    state, ws, war, commander, faction = ctx
    ws.resolve_war(war.id, True, combat_result="triumph")
    good = war.reward_receipt
    assert validate_reward_receipt(good, war.id) is True
    b1 = copy.deepcopy(good)
    b1["schema_version"] = True
    assert validate_reward_receipt(b1, war.id) is False
    b2 = copy.deepcopy(good)
    b2["result"] = "victory"
    b2["result_multiplier"] = True
    assert validate_reward_receipt(b2, war.id) is False


# ---- BB01 (AC-01,08,09): public scout → zero write / no receipt / projected 750 ----

def test_bb01_public_scout_zero_write_no_receipt_projected_750():
    """BB01/§5.2: public scout (forced triumph) is preview-only — zero mutation, no receipt,
    war stays ACTIVE; DTO projected with committed loot 0 and projected_loot 750."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    t0, f0, c0 = state.treasury, faction.treasury, commander.wealth
    res = combat_api.do_combat_action(state, pid, war.id, "scout")
    assert res["success"], res.get("message")
    data = res["data"]
    assert (state.treasury, faction.treasury, commander.wealth) == (t0, f0, c0)
    assert war.reward_receipt is None
    assert war.status == WarStatus.ACTIVE
    assert war.soldier_share == 0
    assert data["reward_status"] == "projected" and data["committed"] is False
    assert data["loot"] == 0
    assert data["projected_loot"] == 750
    assert data["projected_shares"] == {"treasury_share": 375, "faction_share": 187,
                                        "commander_share": 112, "soldier_share": 76}


# ---- BB02 (AC-08,15): public view retains receipt after commander clear + reload ----

def test_bb02_public_view_retains_receipt_after_commander_cleared_and_reload(tmp_path):
    """BB02/§5.3: real attack → commander cleared → successful reload of NEW shares → the
    public `get_combat_view` still surfaces the ORIGINAL committed receipt/DTO, and Forum
    keeps the original nominal pool."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    rec = copy.deepcopy(war.reward_receipt)
    assert rec["committed"] is True and war.soldier_share == 76
    assert war.commander_id is None            # real resolver cleared the commander
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"combat_rules": {
        "treasury_share": 0.40, "faction_share": 0.30,
        "commander_share": 0.20, "soldier_share": 0.10}}), encoding="utf-8")
    state.config._config_path = str(cfg_path)
    assert state.config.reload() is True
    assert state.config.get_reward_share_snapshot()["effective"]["treasury"] == 0.40
    view = combat_api.get_combat_view(state, pid)
    assert view["success"], view.get("message")
    card = next(c for c in view["data"]["resolved_war_cards"] if c["war_id"] == war.id)
    land = card["result"]["land"]
    assert land["reward_status"] == "committed" and land["committed"] is True
    assert land["loot"] == rec["total_monetary"] == 750
    assert (land["treasury_share"], land["faction_share"], land["commander_share"],
            land["soldier_share"]) == (375, 187, 112, 76)
    assert war.reward_receipt == rec            # historical snapshot not rewritten
    assert war.soldier_share == 76              # original nominal pool retained


# ---- BB03 (AC-01,15): loaded history no receipt → core no-op + public history_unrecorded ----

def test_bb03_loaded_history_no_receipt_public_history_unrecorded_core_noop():
    """BB03/§5.3: a loaded historical RESOLVED war with no receipt → core resolve is a no-op
    (zero re-issue) → public `get_combat_view` surfaces history_unrecorded."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    _real_attack(state, war, pid)
    data = state.to_dict()
    for wd in data["_war_system"]["_war_discard"]:
        if wd["id"] == war.id:
            wd["reward_receipt"] = None
    restored = GameState.create_for_testing({})
    restored.load_from_dict(data)
    restored.set_current_player(pid)
    rws = restored.get_war_system()
    rwar = rws.get_war_by_id(war.id)
    assert rwar is not None and rwar.reward_receipt is None
    t0 = restored.treasury
    assert rws.resolve_war(war.id, True, combat_result="victory").get("no_op") is True
    assert restored.treasury == t0
    view = combat_api.get_combat_view(restored, pid)
    assert view["success"], view.get("message")
    card = next(c for c in view["data"]["resolved_war_cards"] if c["war_id"] == war.id)
    land = card["result"]["land"]
    assert land["reward_status"] == "history_unrecorded"
    assert land["committed"] is False and land["loot"] is None


# ---- BB04 (AC-01,15): malformed / wrong-war_id receipt fail-closed, zero write ----

def test_bb04_malformed_wrong_war_id_receipt_public_fail_closed(ctx):
    """BB04/§5.3: malformed / wrong-war_id receipt survives load verbatim but is never
    committed at the public/DTO boundary (no crash, no projected fall-through)."""
    state, ws, war, commander, faction = ctx
    d = war.to_dict()
    d["reward_receipt"] = {"committed": True, "war_id": "other"}
    clone = War.from_dict(d)
    assert clone.reward_receipt == {"committed": True, "war_id": "other"}
    assert clone.has_valid_receipt() is False
    view = combat_api._reward_view(clone, state, ws, "victory")
    assert view["reward_status"] == "history_unrecorded"
    assert view["committed"] is False and view["loot"] is None
    assert any("receipt 校验失败" in m for m in state._event_log)


# ---- BB06 (AC-06,07,10): raw missing share key → default + structured WARNING ----

def test_bb06_raw_missing_share_key_default_and_structured_warning(tmp_path):
    """BB06/§5.4: raw JSON combat_rules missing one share key (merged config still carries it
    from DEFAULTS) → raw-layer missing detected → frozen default + structured WARNING
    (type/reason/raw/effective); the next real attack consumes the default."""
    cfg_path = tmp_path / "cfg_miss.json"
    cfg_path.write_text(json.dumps({"combat_rules": {
        "treasury_share": 0.40, "faction_share": 0.30, "commander_share": 0.20}}),
        encoding="utf-8")                     # soldier_share missing at the raw layer
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    state.config._config_path = str(cfg_path)
    assert state.config.reload() is True       # legal JSON — load succeeds
    snap = state.config.get_reward_share_snapshot()
    assert snap["valid"] is False and snap["reason"] == "missing"
    assert snap["raw"]["soldier_share"] == {"type": "missing"}
    assert snap["effective"] == {"treasury": 0.50, "faction": 0.25,
                                 "commander": 0.15, "soldier": 0.10}
    events = _capture_events(state)
    state.config.testing.force_battle_result = "triumph"   # reload reset testing; re-arm
    _real_attack(state, war, pid)
    w = next(e for e in events if e["extra"].get("type") == "reward_share_fallback")
    assert w["level"] == logging.WARNING
    assert w["extra"]["reason"] == "missing"
    assert w["extra"]["raw"]["soldier_share"] == {"type": "missing"}
    assert w["extra"]["effective"] == {"treasury": 0.50, "faction": 0.25,
                                        "commander": 0.15, "soldier": 0.10}
    rec = war.reward_receipt
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (375, 187, 112, 76)


# ---- AC-10 (modified shares): public consumer + confirm through get_combat_view ----

def test_ac10_modified_shares_public_consumer_and_confirm():
    """AC-10/§5.2: public combat_rules share assignment (0.40/0.30/0.20/0.10) → real attack
    → public `get_combat_view` committed DTO reflects the modified shares (no independent
    recompute; the load-bearing seam is the public view, not a private helper)."""
    state, war, commander, faction, pid = _attack_state(force="triumph", base_treasury=500)
    cfg = state.config
    cfg.combat_rules.treasury_share = 0.40
    cfg.combat_rules.faction_share = 0.30
    cfg.combat_rules.commander_share = 0.20
    cfg.combat_rules.soldier_share = 0.10
    snap = cfg.get_reward_share_snapshot()
    assert snap["valid"] is True and snap["source"] == "memory"
    _real_attack(state, war, pid)
    rec = war.reward_receipt
    assert (rec["treasury_part"], rec["faction_part"],
            rec["commander_part"], rec["pool_part"]) == (300, 225, 150, 75)
    assert rec["identity_capture"]["shares_effective"] == {
        "treasury": 0.40, "faction": 0.30, "commander": 0.20, "soldier": 0.10}
    view = combat_api.get_combat_view(state, pid)
    assert view["success"], view.get("message")
    b = view["data"]["battle_results"][0]
    assert b["war_id"] == war.id
    land = b["land"]
    assert (land["treasury_share"], land["faction_share"],
            land["commander_share"], land["soldier_share"]) == (300, 225, 150, 75)
    assert land["loot"] == 750 and land["committed"] is True
    card = next(c for c in view["data"]["resolved_war_cards"] if c["war_id"] == war.id)
    assert card["result"]["land"]["loot"] == 750


# ---- AC-09 (public draw confirm): projected DTO survives public confirm ----

def test_ac09_public_draw_projected_dto_and_confirm():
    """AC-09/§5.2/§8.2: forced stalemate → draw → TRUCE; public `get_combat_view` DTO projected
    (committed False, loot 0, projected present); public `confirm_battle_result` clears pending
    without rewriting the projected values."""
    state, war, commander, faction, pid = _attack_state(force="stalemate", base_treasury=500)
    _real_attack(state, war, pid)
    assert war.status == WarStatus.TRUCE
    assert war.reward_receipt is None
    view = combat_api.get_combat_view(state, pid)
    assert view["success"], view.get("message")
    b = view["data"]["battle_results"][0]
    land = b["land"]
    assert land["reward_status"] == "projected" and land["committed"] is False
    assert land["projected"] is True
    assert land["loot"] == 0
    assert land["projected_loot"] == 500
    assert land["projected_shares"] == {"treasury_share": 250, "faction_share": 125,
                                        "commander_share": 75, "soldier_share": 50}
    conf = combat_api.confirm_battle_result(state, pid)
    assert conf["success"], conf.get("message")
    view2 = combat_api.get_combat_view(state, pid)
    assert view2["data"]["battle_results"] == []
    card = next(c for c in view2["data"]["truce_wars"] if c["war_id"] == war.id)
    assert card["result"]["land"]["reward_status"] == "projected"
    assert card["result"]["land"]["loot"] == 0
