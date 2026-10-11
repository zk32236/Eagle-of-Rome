# src/tests/test_api/test_wpk_s5_declaration.py
"""WP-K S5（K-D03）— AI 宣战（4a）军团数「敌强匹配」+ 与 S1 增援统一（单一 producer）冻结测试。

设计来源（单一权威）：02-sa-design/SA-Development-Task-WP-K-v1.6-2026-10-11.md
（FC-K-34…44；K-AC-13.1…13.9；LC-K-05 re-based / LC-K-06 / LC-K-07 / LC-K-08）。

覆盖：
- K-AC-13.1…13.4：4a 敌强匹配 / 超池招满 / 零池·剩余不足跳过 / 敌强=0→1。
- K-AC-13.5：多战场 + 混合 4a+4b′（正常 `ΣN ≤ pool`）+ **负测（FC-K-44）** 聚合门 fail-closed。
- K-AC-13.6：确定性（无 random）。
- K-AC-13.7：4a 与 4b′ 同一 producer（单 owner）。
- K-AC-13.8：人类值域/校验不变（`_legion_options_for_war`/`_build_proposal_options`/`_populate_proposal('war')`）。
- K-AC-13.9：公式候选 A（E = `war.get_total_strength()`，Owner S-2=A）。

证据路径：
- Targeted/Affected = PRODUCTION_CHAIN：经真实入口 `senate_api.auto_submit_proposals`（4a 块）
  → 统一 producer → `propose_many`/`submit_proposal_package`；4a/4b′ 同 owner `reinforcement_n_target`。
- LC-K-06：全生命周期（auto_submit → finalize → `advance_senate_phase` 原子激活；ledger N == draft N）。
- LC-K-08：负测 —— 生产草案 → **合法生产池收缩**（征召并绑定消费共享军团）→ 聚合门**拒绝**
  （submit `LEGION_POOL_EXCEEDED` 或 plan `legion_shortfall>0`）；**行使（非绕过）**聚合门，
  不直调 `commit_war_resolution`、不写 `remaining`（§9.1 合规；FC-K-44）。

§9.1 No Test-Assisted Transition：本文件正证一律经真实生产 owner（`auto_submit_proposals` 4a/4b′
→ `propose_many` → `submit_proposal_package`；边界 `advance_senate_phase`）；负测为**拒绝测试**
（要求门触发并拒绝），不直调下游执行 API 顶替生产 transition、不手写内部计数（FC-K-44）。
"""
import os
import sys
import unittest

import random

import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def _isolate_global_rng():
    """不扰动全局 random 序列（防影响后续顺序敏感测试）。"""
    _state = random.getstate()
    yield
    random.setstate(_state)

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import senate_api


# ---------------------------------------------------------------------------
# 生产链基线（与 test_wpk_s1_reinforcement 同型；自持 builder，不复用测试模块）
# ---------------------------------------------------------------------------
def _build_state(config=None):
    """R11 生产链基线态（真实 War + 军团池 25 UNRAISED + 合法 Commander 候选）。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    state.config.economic_rules.senate_war_legions = {
        "default": 4, "min": 1, "cap_mode": "available_pool",
    }
    optimates = Faction(id="optimates", name="Optimates", treasury=50)
    populares = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(optimates)
    state.add_faction(populares)
    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    optimates.member_ids.append(1)
    exconsul = Figure(id=2, name="前执政官", faction_id="optimates", age=52)
    exconsul.office = "ex-consul"
    exconsul.class_tier = ClassTier.NOBILE
    exconsul.influence = 90
    state.add_member(exconsul)
    optimates.member_ids.append(2)
    tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    populares.member_ids.append(3)
    dead = Figure(id=9, name="阵亡统帅", faction_id="optimates", age=60)
    dead.class_tier = ClassTier.NOBILE
    dead.is_dead = True
    state.add_member(dead)
    optimates.member_ids.append(9)
    state._players = {
        "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
    }
    state._current_player_id = "player1"
    state._turn_order = ["player1", "player2"]
    return state


def _add_threat_war(state, strength=5, war_id="w_threat", naval_required=False):
    war = War(id=war_id, name=f"威胁战争{war_id}", war_type=WarType.FOREIGN,
              strength=strength, naval_required=naval_required)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    return war


def _add_active_war(state, strength=5, commander_id=9, war_id="w1"):
    war = War(id=war_id, name=f"进行中战争{war_id}", war_type=WarType.FOREIGN,
              strength=strength, naval_required=False)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    state.get_war_system()._active_wars.append(war)
    return war


def _declare(config_extra=None, threats=(), actives=()):
    """构造基线态 → 加威胁/进行中战 → 经真实 `auto_submit_proposals`（4a+4b′ 生产链）。"""
    config = {"combat_rules": {"war_takeover_chance": 1.0}, "testing": {"always_declare": True}}
    if config_extra:
        for section, keys in config_extra.items():
            config.setdefault(section, {}).update(keys)
    state = _build_state(config)
    for kwargs in threats:
        _add_threat_war(state, **kwargs)
    for kwargs in actives:
        _add_active_war(state, **kwargs)
    result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
    return state, result


def _war_proposals(result):
    return {p["war_id"]: p["legions"] for p in result["data"]["proposals"] if p["type"] == "war"}


# ---------------------------------------------------------------------------
# K-AC-13.1 / 13.4 / 13.9 — 4a 敌强匹配（selected formula A）
# ---------------------------------------------------------------------------
class TestS5DeclarationEnemyMatched(unittest.TestCase):
    def test_kac_13_1_enemy_matched_ceil(self):
        """K-AC-13.1：4a 生产链 N = ceil(E/u)——E=12,u=2 ⇒ 6（真实 4a 块）。"""
        state, result = _declare(threats=[{"strength": 12, "war_id": "w_threat"}])
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(_war_proposals(result).get("w_threat"), 6)

    def test_kac_13_1_ceil_rounding(self):
        """K-AC-13.1 / FC-K-04：ceil(7/2)=4（非 3）。"""
        state, result = _declare(threats=[{"strength": 7, "war_id": "w_threat"}])
        self.assertEqual(_war_proposals(result).get("w_threat"), 4)

    def test_kac_13_9_selected_formula_A(self):
        """K-AC-13.9：S-2=A —— E = war.get_total_strength()（陆战敌强）；
        N == 单一 producer 同参输出（selected formula）。"""
        state, result = _declare(threats=[{"strength": 12, "war_id": "w_threat"}])
        war = state.get_war_system().get_war_by_id("w_threat")
        pool = len(state.get_military_system().get_available_legions())
        expected = senate_api.reinforcement_n_target(state, war, 25, pool)
        self.assertEqual(expected, 6)
        self.assertEqual(_war_proposals(result).get("w_threat"), expected)

    def test_kac_13_4_enemy_zero(self):
        """K-AC-13.4 / FC-K-38③：E=0 且池>0 ⇒ N=1。"""
        state, result = _declare(threats=[{"strength": 0, "war_id": "w_threat"}])
        self.assertEqual(_war_proposals(result).get("w_threat"), 1)


# ---------------------------------------------------------------------------
# K-AC-13.2 / 13.3 — 边界（超池 / 零池·剩余不足）
# ---------------------------------------------------------------------------
class TestS5DeclarationBoundaries(unittest.TestCase):
    def test_kac_13_2_over_pool_fill(self):
        """K-AC-13.2 / FC-K-38②：超池 ⇒ N = min(remaining, pool) = pool（招满）。"""
        state, result = _declare(threats=[{"strength": 1000, "war_id": "w_threat"}])
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(_war_proposals(result).get("w_threat"), pool)

    def test_kac_13_3_zero_pool_skips(self):
        """K-AC-13.3 / FC-K-38①：零池 ⇒ 跳过宣战（不产 war draft）；不提交 N=0。"""
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0},
                              "testing": {"always_declare": True}})
        ms = state.get_military_system()
        for number in range(1, 26):
            ms.recruit_legion(number)
        self.assertEqual(len(ms.get_available_legions()), 0)
        _add_threat_war(state, strength=5, war_id="w_threat")
        result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(_war_proposals(result), {})   # 零池 ⇒ 无 4a draft

    def test_kac_13_3_remaining_insufficient_skips(self):
        """K-AC-13.3 / FC-K-38①：共享 remaining 被前战耗尽（remaining<1）⇒ 后续战跳过。"""
        state, result = _declare(threats=[
            {"strength": 1000, "war_id": "w1"},   # N = pool（耗尽 remaining）
            {"strength": 1000, "war_id": "w2"},   # remaining<1 ⇒ 跳过
        ])
        by_war = _war_proposals(result)
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(by_war.get("w1"), pool)
        self.assertNotIn("w2", by_war)


# ---------------------------------------------------------------------------
# K-AC-13.5（正常路径）/ 13.6 / 13.7 — 多战场 + 混合 + 确定性 + 统一 producer
# ---------------------------------------------------------------------------
class TestS5UnifiedProducer(unittest.TestCase):
    def test_kac_13_7_4a_and_4bp_same_producer(self):
        """K-AC-13.7 / FC-K-34：4a（宣战）与 4b′（增援）为**同一 producer**（单 owner）。

        同敌强 E=10、同池 ⇒ 两调用点 N 相同（皆 = `reinforcement_n_target` 输出）；4a 不再 random。
        """
        state, result = _declare(
            threats=[{"strength": 10, "war_id": "w_threat"}],
            actives=[{"strength": 10, "war_id": "w1"}],
        )
        self.assertTrue(result["success"], result.get("message"))
        by_war = _war_proposals(result)
        pool = len(state.get_military_system().get_available_legions())
        threat_war = state.get_war_system().get_war_by_id("w_threat")
        active_war = state.get_war_system().get_war_by_id("w1")
        # 4a 生产链 N（w_threat）== 单一 producer 输出
        self.assertEqual(by_war.get("w_threat"),
                         senate_api.reinforcement_n_target(state, threat_war, pool, pool))
        # 4b′ 生产链 N（w1，consul_direct decision）== 同一 producer 输出
        decisions = state.get_consul_war_decisions(state.get_senate_session())
        self.assertEqual(len(decisions), 1, list(decisions))
        reinforce_n = list(decisions.values())[0]["payload"]["reinforcement_n"]
        self.assertEqual(reinforce_n, senate_api.reinforcement_n_target(state, active_war, pool, pool))
        # 统一：同 E 同池 ⇒ 4a == 4b′
        self.assertEqual(by_war.get("w_threat"), reinforce_n)
        self.assertEqual(by_war.get("w_threat"), 5)

    def test_kac_13_6_determinism_no_random(self):
        """K-AC-13.6 / FC-K-43：重复（不同 seed）⇒ identical N（4a 无 random 依赖）。"""
        values = []
        for seed in (111, 222):
            random.seed(seed)
            state, result = _declare(threats=[{"strength": 9, "war_id": "w_threat"}])
            values.append(_war_proposals(result).get("w_threat"))
        self.assertEqual(values, [5, 5])

    def test_kac_13_5_lc_k_07_multi_threat_sequential(self):
        """LC-K-07 / K-AC-13.5：≥2 THREAT wars，ΣN_target>pool ⇒ 4a 顺序消费共享 remaining，ΣN ≤ pool。"""
        state, result = _declare(threats=[
            {"strength": 30, "war_id": "w1"},   # target 15
            {"strength": 30, "war_id": "w2"},   # target 15 → remaining 10 ⇒ 10
        ])
        self.assertTrue(result["success"], result.get("message"))
        by_war = _war_proposals(result)
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(by_war.get("w1"), 15)
        self.assertEqual(by_war.get("w2"), 10)
        self.assertEqual(sum(by_war.values()), pool)
        self.assertLessEqual(sum(by_war.values()), pool)

    def test_kac_13_5_mixed_4a_and_4bp_shared_pool(self):
        """K-AC-13.5 / LC-K-05（re-based）：同 run 4a+4b′ 共享 remaining，ΣN ≤ pool，包 admitted。"""
        state, result = _declare(
            threats=[{"strength": 30, "war_id": "w_threat"}],   # 4a target 15
            actives=[{"strength": 30, "war_id": "w1"}],          # 4b′ target 15 → remaining 10 ⇒ 10
        )
        self.assertTrue(result["success"], result.get("message"))
        by_war = _war_proposals(result)
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(by_war.get("w_threat"), 15)
        self.assertEqual(by_war.get("w1"), 10)
        self.assertEqual(sum(by_war.values()), pool)
        self.assertLessEqual(sum(by_war.values()), pool)


# ---------------------------------------------------------------------------
# K-AC-13.8 — 人类值域/校验不变（FC-K-39）
# ---------------------------------------------------------------------------
class TestS5HumanRangeUnchanged(unittest.TestCase):
    def test_kac_13_8_legion_options_for_war_unchanged(self):
        """K-AC-13.8：`_legion_options_for_war` 人类值域输出不变（min=1,max=pool,default=4）。"""
        state = _build_state()
        pool = len(state.get_military_system().get_available_legions())
        threat = _add_threat_war(state, strength=5)
        options = senate_api._legion_options_for_war(state, threat)
        self.assertEqual(options["min"], 1)
        self.assertEqual(options["max"], pool)
        self.assertEqual(options["default"], min(4, pool))
        self.assertEqual(options["allowed"], list(range(1, pool + 1)))

    def test_kac_13_8_build_proposal_options_unchanged(self):
        """K-AC-13.8：`_build_proposal_options` 人类默认 legions 不变（= senate_war_legions.default 4）。"""
        state = _build_state()
        options = senate_api._build_proposal_options(
            state, {"war_threats": [{"war_id": "w_threat", "name": "威胁战争", "threat_level": 2}]})
        war_opts = [o for o in options if o.get("key", "").startswith("war:")]
        self.assertEqual(len(war_opts), 1, options)
        self.assertEqual(war_opts[0]["params"]["legions"], 4)

    def test_kac_13_8_populate_proposal_war_predicate_unchanged(self):
        """K-AC-13.8：`_populate_proposal('war')` 校验谓词不变（拒 legions<1 / >pool）。"""
        state = _build_state()
        threat = _add_threat_war(state, strength=5, war_id="w_threat")
        pool = len(state.get_military_system().get_available_legions())
        ps = PoliticalSystem(state)
        self.assertTrue(ps._populate_proposal({}, "war", war_id="w_threat", legions=1)["success"])
        self.assertTrue(ps._populate_proposal({}, "war", war_id="w_threat", legions=pool)["success"])
        self.assertFalse(ps._populate_proposal({}, "war", war_id="w_threat", legions=0)["success"])
        self.assertFalse(ps._populate_proposal({}, "war", war_id="w_threat", legions=pool + 1)["success"])


# ---------------------------------------------------------------------------
# LC-K-06 — 4a 全生命周期（auto_submit → finalize → advance 原子激活；ledger N == draft N）
# ---------------------------------------------------------------------------
class _PassVote:
    def decide_vote(self, issue, faction, state):
        return True


class TestS5LongChainLifecycle(unittest.TestCase):
    def test_lc_k_06_4a_declaration_full_lifecycle(self):
        """LC-K-06 / K-AC-13.1：THREAT war + pool>0 ⇒ 4a → producer → draft → finalize →
        `advance_senate_phase` 原子激活；绑定 Legion 数 == draft N（敌强匹配）。

        Transition Owner = `senate_api.auto_submit_proposals`（4a producer）→ `propose_many`
        → `submit_proposal_package` → `finalize_senate_if_ready` → `advance_senate_phase`
        （唯一原子军事执行 owner）。证据路径 = PRODUCTION_CHAIN。
        """
        state, result = _declare(threats=[{"strength": 6, "war_id": "w_threat"}])
        self.assertTrue(result["success"], result.get("message"))
        draft_n = _war_proposals(result).get("w_threat")
        self.assertEqual(draft_n, 3)   # ceil(6/2)
        finalize = senate_api.finalize_senate_if_ready(state, vote_decider=_PassVote())
        self.assertTrue(finalize["success"], finalize.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        war = state.get_war_system().get_war_by_id("w_threat")
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.activation_origin, "active_declaration")
        bound = state.get_military_system().get_legions_for_battle("w_threat")
        self.assertEqual(len(bound), draft_n)   # 冻结 ledger N == draft N


# ---------------------------------------------------------------------------
# LC-K-08 / K-AC-13.5（负测）— 聚合门 fail-closed（FC-K-44；§9.1 合规）
# ---------------------------------------------------------------------------
class TestS5NegativeLegionPool(unittest.TestCase):
    def test_lc_k_08_submit_gate_rejects_after_legal_contraction(self):
        """LC-K-08（route A observable）/ K-AC-13.5：生产草案 → 合法生产池收缩 → submit 门拒绝。

        做法（FC-K-44 范围界定，非绕过）：
          ① 经**真实 4a producer** 取本战合法 N（= 生产会输出的敌强匹配值）；
          ② **合法生产池收缩**——征召并绑定（`military_system.recruit_legion` +
             `assign_to_war`），消费共享军团使 live 池 < N；
          ③ 经**真实生产入口** `senate_api.propose_many`（→ `submit_proposal_package`）
             投递该「生产可采纳的超预算包输入」，断言门**行使并拒绝**（`LEGION_POOL_EXCEEDED`）。
        不直调 `commit_war_resolution`、不手写 `remaining`（§9.1 合规）。
        """
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0},
                              "testing": {"always_declare": True}})
        pool = len(state.get_military_system().get_available_legions())
        threat = _add_threat_war(state, strength=1000, war_id="w_threat")
        # ① 单一 producer 产本战合法 N（= pool，超池招满）
        n = senate_api.reinforcement_n_target(state, threat, pool, pool)
        self.assertEqual(n, pool)
        # ② 合法生产池收缩：征召并绑定 1 个军团（UNRAISED→ACTIVE→绑定）
        ms = state.get_military_system()
        consume = ms.get_available_legions()[0]
        ok, _ = ms.recruit_legion(consume.number)
        self.assertTrue(ok)
        ms.assign_to_war([consume.number], "w_threat", 1)
        available = len(ms.get_available_legions())
        self.assertLess(available, n)   # live 池 < ΣN（合法收缩可达）
        # ③ 真实生产入口递交生产可采纳的超预算包 → 聚合门行使拒绝
        request = {
            "war_drafts": [{
                "war_id": "w_threat", "checked": True, "mode": "command",
                "target_commander_id": 1, "reinforcement_n": n,
            }],
            "proposals": [],
        }
        result = senate_api.propose_many(state, "player1", request)
        self.assertFalse(result["success"])
        codes = [e.get("code") for e in (result.get("errors") or [])]
        self.assertIn("LEGION_POOL_EXCEEDED", codes, result.get("errors"))
        err = next(e for e in result["errors"] if e["code"] == "LEGION_POOL_EXCEEDED")
        self.assertEqual(err["details"]["requested_total"], n)
        self.assertEqual(err["details"]["available_total"], available)
        # 零发布：war 仍 THREAT（门拒绝，未激活）
        self.assertEqual(threat.status, WarStatus.THREAT)

    def test_lc_k_08_plan_gate_rejects_after_legal_contraction(self):
        """LC-K-08（route B observable）/ K-AC-13.5：包已 admit → 合法池收缩 → plan 门 fail-closed。

        生产草案（真实 `auto_submit_proposals`，ΣN ≤ 生产时点池）→ 征召并绑定收缩 live 池
        → `finalize_senate_if_ready` → `advance_senate_phase`（生产边界 owner）在
        `build_war_resolution_plan` 处重读 live 池 ⇒ `legion_shortfall>0` ⇒ fail-closed、
        **零军事写**（war 不激活）。不直调 `commit_war_resolution`、不写 `remaining`（§9.1 合规）。
        """
        state, result = _declare(threats=[{"strength": 1000, "war_id": "w_threat"}])
        self.assertTrue(result["success"], result.get("message"))
        pool = len(state.get_military_system().get_available_legions())
        draft_n = _war_proposals(result).get("w_threat")
        self.assertEqual(draft_n, pool)   # 生产草案 ΣN == 生产时点池（admit 成功）
        # 合法生产池收缩：征召并绑定 1 个军团
        ms = state.get_military_system()
        consume = ms.get_available_legions()[0]
        ok, _ = ms.recruit_legion(consume.number)
        self.assertTrue(ok)
        ms.assign_to_war([consume.number], "w_threat", 1)
        self.assertLess(len(ms.get_available_legions()), draft_n)
        finalize = senate_api.finalize_senate_if_ready(state, vote_decider=_PassVote())
        self.assertTrue(finalize["success"], finalize.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertFalse(adv["success"], adv)
        # plan 门 fail-closed（legion_pool 上下文变更）
        self.assertEqual(adv["data"].get("failed_stage"), "plan", adv["data"])
        self.assertIn("legion_pool", adv["data"].get("changed_domains", []), adv["data"])
        # 零军事写：war 不激活
        threat = state.get_war_system().get_war_by_id("w_threat")
        self.assertEqual(threat.status, WarStatus.THREAT)


if __name__ == "__main__":
    unittest.main()
