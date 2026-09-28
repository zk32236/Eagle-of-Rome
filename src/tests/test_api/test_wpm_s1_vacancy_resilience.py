# src/tests/test_api/test_wpm_s1_vacancy_resilience.py
"""WP-M / Slice M-S1 — Election Candidate Supply & Vacant-Office Resilience.

Acceptance Test Set = SC-1 … SC-6（真实生产路径；禁 monkeypatch 函数本体；禁手改 office holder）。

- SC-1 consul 空缺（censor 在城同派系）→ 提案可提交（human_presiding_officer）
- SC-2 回退主持提交 AUTHORITY_CONSUL_DIRECT 草案 → 整包拒绝 host_no_direct_authority（零部分发布）
- SC-3 无主持人（FC-01=0）→ 结构性跳过（senate_no_host / can_advance / finalize 豁免 / advance）
- SC-4 多回合（≥2）无 vacancy 软锁
- SC-5 主持人 tie-break 四级确定性（重跑同结果）
- SC-6 censor 供给配置生效（冻结值 vs 基线；资格契约不变）

冻结设计 = SA pack v1.5（FC-01…10 / D1–D8 / M-AC-01…07）。
"""
import json
import os
import unittest

from src.api import senate_api, population_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import WarStatus
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.tests.fixtures.wpgr4_fixtures import make_base_state, make_war, attach_active
from src.tests.fixtures.wpm_rng_guard import (  # noqa: F401  (autouse isolation fixture)
    _wpm_preserve_global_random_state,
)


def _add_figure(state, faction, figure_id, name, office="ex-consul", age=50,
                influence=30, absent=False, **attrs):
    fig = Figure(id=figure_id, name=name, faction_id=faction.id, age=age)
    fig.office = office
    fig.class_tier = ClassTier.NOBILE
    fig.influence = influence
    fig.is_absent = absent
    for k, v in attrs.items():
        setattr(fig, k, v)
    state.add_member(fig)
    faction.member_ids.append(figure_id)
    return fig


def _host_state(*, consul_absent=True, with_censor=True):
    """Base: optimates(player1) + consul(absent) + censor(host) [+ direct/ongoing war + threat]."""
    state = make_base_state(turn_number=1, year=-282)
    faction = Faction(id="optimates", name="Optimates", treasury=500)
    state.add_faction(faction)
    state.add_player(Player("player1", "optimates", PlayerType.HUMAN))
    state.set_turn_order(["player1"])
    state.set_current_player("player1")

    state._war_system = state.get_war_system() or WarSystem(state)
    state._military_system = state.get_military_system() or MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    consul = _add_figure(state, faction, 1, "Consul Aemilius", office="consul",
                         age=45, influence=80, absent=consul_absent)
    host = None
    if with_censor:
        host = _add_figure(state, faction, 5, "Censor Host", office="censor",
                           age=50, influence=40)
    cmd_a = _add_figure(state, faction, 2, "Commander A", office="ex-consul", age=45)

    # direct（ongoing）真实 War → consul_direct 路由
    war_ongoing = make_war("pyrrhic_war", "Pyrrhic War", status=WarStatus.ACTIVE,
                           enemy_land=6, threat_level=4)
    attach_active(state, war_ongoing)
    # THREAT → active_declaration → senate_vote 路由
    war_threat = make_war("threat_war", "Threat War", status=WarStatus.THREAT, threat_level=2)
    state._war_system._threats.append(war_threat)

    state.add_national_public_land(500)
    return {
        "state": state, "faction": faction, "player_id": "player1",
        "consul": consul, "host": host, "cmd_a": cmd_a,
        "war_ongoing": war_ongoing, "war_threat": war_threat,
    }


class TestSC1FallbackHostSubmits(unittest.TestCase):
    """SC-1：consul 空缺 + censor 在城同派系 → host 回退主持，非 direct 提案可提交。"""

    def test_sc1_host_fallback_submit_non_direct(self):
        ctx = _host_state()
        state = ctx["state"]
        politics = senate_api._political_system(state)

        control = politics.resolve_proposal_control("player1")
        self.assertEqual(control["mode"], "HUMAN")
        self.assertEqual(control["actor"], 5)
        self.assertEqual(control["authority_reason"], "human_presiding_officer")

        view = senate_api.get_senate_view(state, "player1")
        self.assertTrue(view["success"], view.get("message"))
        self.assertIs(view["data"]["viewer_has_consul"], True)
        self.assertIs(view["data"]["can_create_proposal"], True)

        result = senate_api.propose_many(
            state, "player1",
            {"senate_session_id": "sc1", "submit_request_id": "sc1-req",
             "war_drafts": [],
             "proposals": [{"type": "land", "params": {"act_type": "sale", "amount_C": 10}}]},
        )
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(len(result["data"]["created"]), 1)
        self.assertTrue(state.senate_proposal_decision_complete)


class TestSC2HostDirectDenied(unittest.TestCase):
    """SC-2：回退主持提交含 AUTHORITY_CONSUL_DIRECT 的 checked war_draft → 整包拒绝。"""

    def test_sc2_host_direct_package_rejected(self):
        ctx = _host_state()
        state = ctx["state"]
        result = senate_api.propose_many(
            state, "player1",
            {"senate_session_id": "sc2", "submit_request_id": "sc2-req",
             "war_drafts": [{"war_id": ctx["war_ongoing"].id, "checked": True,
                             "mode": "command", "target_commander_id": ctx["cmd_a"].id,
                             "reinforcement_n": 0}],
             "proposals": []},
        )
        self.assertFalse(result["success"])
        reasons = [e.get("details", {}).get("reason") for e in (result.get("errors") or [])]
        self.assertIn("host_no_direct_authority", reasons)
        # 零部分发布
        self.assertEqual(state.get_senate_proposals(), [])
        self.assertEqual(state.get_consul_war_decisions("sc2"), {})
        self.assertFalse(state.senate_proposal_decision_complete)

    def test_sc2b_host_non_direct_draft_allowed(self):
        """对照：同一 host 提交 senate_vote 路由草案（THREAT command）→ 允许。"""
        ctx = _host_state()
        state = ctx["state"]
        result = senate_api.propose_many(
            state, "player1",
            {"senate_session_id": "sc2b", "submit_request_id": "sc2b-req",
             "war_drafts": [{"war_id": ctx["war_threat"].id, "checked": True,
                             "mode": "command", "target_commander_id": ctx["cmd_a"].id,
                             "reinforcement_n": 1}],
             "proposals": []},
        )
        self.assertTrue(result["success"], result.get("errors"))


class TestSC3NoHostStructuralSkip(unittest.TestCase):
    """SC-3：无主持人（FC-01=0）→ senate_no_host；finalize 豁免；advance 通过；无守卫拒绝。"""

    def test_sc3_no_host_structural_skip(self):
        ctx = _host_state(with_censor=False)
        state = ctx["state"]
        self.assertIsNone(state.get_presiding_officer())

        view = senate_api.get_senate_view(state, "player1")
        self.assertTrue(view["success"], view.get("message"))
        self.assertIs(view["data"]["senate_no_host"], True)
        self.assertEqual(view["data"]["proposal_control_mode"], "NONE")
        self.assertEqual(view["data"]["authority_reason"]["proposal"], "no_eligible_host")
        self.assertIs(view["data"]["can_create_proposal"], False)
        self.assertIs(view["data"]["can_finish_empty"], False)
        self.assertIs(view["data"]["can_advance"], True)

        final = senate_api.resolve_senate(state)
        self.assertTrue(final["success"], final.get("message"))
        self.assertNotIn("proposal_selection_not_complete", json.dumps(final.get("data", {})))
        self.assertTrue(state.get_phase_result("senate"))

        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))


class TestSC4MultiTurnNoSoftLock(unittest.TestCase):
    """SC-4：多回合（≥2）senate 链在 vacancy 下无软锁。"""

    def _cycle(self, state, turn_number):
        state.turn = GameTurn(turn_number=turn_number, year=-282 + turn_number)
        state._executed_phases.discard("senate")
        state._executed_phases.discard("combat")
        state._executed_phases.discard("resolution")
        state.clear_phase_result("senate")
        # elect 面只读触达（不改 office → host 保持）
        population_api.get_candidates(state)
        session = f"turn-{turn_number}"
        result = senate_api.propose_many(
            state, "player1",
            {"senate_session_id": session, "submit_request_id": f"{session}-req",
             "war_drafts": [],
             "proposals": [{"type": "land", "params": {"act_type": "sale", "amount_C": 5}}]},
        )
        self.assertTrue(result["success"], result.get("errors"))
        final = senate_api.resolve_senate(state)
        self.assertTrue(final["success"], final.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_sc4_two_turns_no_soft_lock(self):
        ctx = _host_state()
        state = ctx["state"]
        for turn_number in (1, 2):
            self._cycle(state, turn_number)
        self.assertTrue(state.is_phase_executed("senate"))


class TestSC5TieBreakDeterminism(unittest.TestCase):
    """SC-5：主办 host tie-break 四级（rank↓ → influence↓ → attr_sum↓ → id↑）确定性。"""

    def _base(self):
        state = make_base_state(turn_number=1, year=-282)
        faction = Faction(id="optimates", name="Optimates", treasury=10)
        state.add_faction(faction)
        state.add_player(Player("player1", "optimates", PlayerType.HUMAN))
        return state, faction

    def test_sc5_attr_sum_then_id(self):
        state, faction = self._base()
        # 同 rank(censor=4)/同 influence(50)：attr_sum 25 者胜；再者同 attr_sum → id 小者胜
        a = _add_figure(state, faction, 10, "Censor A", office="censor", age=50, influence=50,
                        martial=5, intelligence=5, charisma=5, zeal=5)
        b = _add_figure(state, faction, 11, "Censor B", office="censor", age=50, influence=50,
                        martial=7, intelligence=6, charisma=6, zeal=6)
        c = _add_figure(state, faction, 12, "Censor C", office="censor", age=50, influence=50,
                        martial=7, intelligence=6, charisma=6, zeal=6)
        results = {state.get_presiding_officer().id for _ in range(5)}
        self.assertEqual(results, {11})  # B（attr_sum=25，id 11 < 12）唯一胜出

    def test_sc5_rank_dominates(self):
        state, faction = self._base()
        _add_figure(state, faction, 20, "Praetor", office="praetor", age=45, influence=999,
                    martial=9, intelligence=9, charisma=9, zeal=9)
        censor = _add_figure(state, faction, 21, "Censor", office="censor", age=50, influence=1,
                             martial=1, intelligence=1, charisma=1, zeal=1)
        self.assertEqual(state.get_presiding_officer().id, censor.id)

    def test_sc5_influence_then_attr(self):
        state, faction = self._base()
        _add_figure(state, faction, 30, "LowInf", office="censor", age=50, influence=10,
                    martial=9, intelligence=9, charisma=9, zeal=9)
        hi = _add_figure(state, faction, 31, "HighInf", office="censor", age=50, influence=99,
                         martial=1, intelligence=1, charisma=1, zeal=1)
        self.assertEqual(state.get_presiding_officer().id, hi.id)


class TestSC6CensorSupplyConfig(unittest.TestCase):
    """SC-6：censor 供给配置（D7 冻结 2/3/2/0.7）生效 + 资格契约不变。"""

    def _state_with_vs(self, vs):
        cfg = {
            "testing": {"bypass_player_check": True},
            "political_rules": {
                "min_ages": {"consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30},
                "office_cooldowns": {k: 2 for k in ("consul", "censor", "praetor", "quaestor", "tribune")},
                "office_rank": {"dictator": 6, "consul": 5, "censor": 4, "praetor": 3, "quaestor": 2, "tribune": 1},
            },
            "forum_rules": {
                "new_figures_count": 3,
                "class_probabilities": {"nobile": 0.1, "eques": 0.25, "plebeian": 0.65},
                "veteran_supply": vs,
            },
        }
        state = GameState.create_for_testing(cfg)
        state.turn = GameTurn(turn_number=1, year=-264)
        return state

    def test_sc6_frozen_default_guarantees_at_least_two_ex_consuls(self):
        from src.core.systems import figure_generation_system as fgs
        frozen = {"enabled": True, "min_veteran_nobiles": 2, "max_veteran_nobiles": 3,
                  "min_ex_consul_count": 2, "censor_anchor_years_ago": 1,
                  "history_years_ago_min": 2, "history_years_ago_max": 8,
                  "ex_consul_probability": 0.7, "age_min": 45, "age_max": 58}
        state = self._state_with_vs(frozen)
        for _ in range(10):
            figs = fgs.generate_market_figures(state)
            ex_consuls = [f for f in figs if any(t.office_type == "consul" for t in f.office_history)]
            self.assertGreaterEqual(len(ex_consuls), 2)  # min_ex_consul_count=2 确定性

    def test_sc6_code_default_matches_frozen(self):
        from src.core.systems import figure_generation_system as fgs
        d = fgs._DEFAULT_VETERAN_SUPPLY
        self.assertEqual(d["min_veteran_nobiles"], 2)
        self.assertEqual(d["max_veteran_nobiles"], 3)
        self.assertEqual(d["min_ex_consul_count"], 2)
        self.assertEqual(d["ex_consul_probability"], 0.7)

    def test_sc6_shipped_config_value(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        with open(os.path.join(root, "data", "config", "game_config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        vs = cfg["forum_rules"]["veteran_supply"]
        self.assertEqual(vs["min_veteran_nobiles"], 2)
        self.assertEqual(vs["max_veteran_nobiles"], 3)
        self.assertEqual(vs["min_ex_consul_count"], 2)
        self.assertEqual(vs["ex_consul_probability"], 0.7)

    def test_sc6_qualification_contract_unchanged(self):
        frozen = {"enabled": True, "min_veteran_nobiles": 2, "max_veteran_nobiles": 3,
                  "min_ex_consul_count": 2, "ex_consul_probability": 0.7}
        state = self._state_with_vs(frozen)
        with_consul = Figure(id=901, name="ExConsul", faction_id=None, age=55)
        with_consul.add_office_history("consul", -3, -2)
        self.assertEqual(with_consul.can_hold_office("censor", 1, state.config), (True, "Eligible"))
        no_consul = Figure(id=902, name="NoConsul", faction_id=None, age=55)
        self.assertEqual(no_consul.can_hold_office("censor", 1, state.config),
                         (False, "Requires prior Consul service"))


if __name__ == "__main__":
    unittest.main()