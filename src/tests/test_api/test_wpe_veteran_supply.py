# src/tests/test_api/test_wpe_veteran_supply.py
"""
WP-E（GUI-BETA-R1）E-G7-09：veteran supply 供给机制测试（T-VS-1 ~ T-VS-9）。

覆盖（窄设计 §6.1 A 组——单元/定向）：
- T-VS-1 市场保证性（默认配置）
- T-VS-2 censor-anchor 性质（consul 冷却阻断 / censor Eligible）
- T-VS-3 历史/年龄不变量（office is None / 任期无未来 / is_active False / cursus 时序 / 年龄一致）
- T-VS-4 开关关闭（enabled=false → 零注入）
- T-VS-5 参数调优 + clamp（min=max=2 / count=1 / count=0）
- T-VS-6 实况链 generate_figures（含 hero：普通人物 ≥1 资深；hero 零注入；总数不变）
- T-VS-7 资格矩阵（§5.1 全矩阵，含原因串精确匹配）
- T-VS-8 招募链端到端（recruit_figure + resolve_forum → get_candidates censor ≥1 / consul ≥1）
- T-VS-9 跨回合冷却演进（T 注入锚 → T+1 consul 资格恢复）

生产等价 political_rules 快照（对齐 data/config/game_config.json，禁读配置文件全文——
沿用 T-7 harness `_production_political_rules` 既有实证快照）。
"""
import random

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.systems import figure_generation_system as fgs
from src.core.systems.figure_generation_system import (
    generate_figures,
    generate_market_figures,
    _read_veteran_supply_config,
)


def _production_political_rules():
    """生产等价 political_rules（T-7 harness 既有实证快照）。"""
    return {
        "office_cooldowns": {
            "consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2,
        },
        "offices_per_election": {
            "consul": 1, "censor": 1, "praetor": 1, "quaestor": 1, "tribune": 1,
        },
        "candidates_per_election": {
            "consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2,
        },
        "min_ages": {
            "consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30,
        },
        "office_rank": {
            "dictator": 6, "censor": 4, "consul": 5, "praetor": 3, "tribune": 1, "quaestor": 2,
        },
        "office_influence_bonus": {
            "dictator": 60, "censor": 50, "consul": 40, "praetor": 30, "tribune": 20,
            "quaestor": 10, "proconsul": 0, "propraetor": 0,
        },
        "ex_office_influence_bonus": {
            "ex-dictator": 30, "ex-censor": 25, "ex-consul": 20, "ex-praetor": 15,
            "ex-tribune": 10, "ex-quaestor": 5, "ex-proconsul": 20, "ex-propraetor": 15,
        },
        "family_prestige": {
            "Julius": 4, "Cornelius": 4, "Claudius": 3, "Fabius": 3, "Aemilius": 2, "Servilius": 2,
        },
    }


def _make_state(forum_rules_extra=None):
    """确定性种子状态：3 派系 × 3 玩家 + 每派系 1 eques + 1 pleb（无 history）。"""
    cfg = {
        "testing": {"bypass_player_check": True},
        "political_rules": _production_political_rules(),
        "forum_rules": {
            "new_figures_count": 3,
            "class_probabilities": {"nobile": 0.1, "eques": 0.25, "plebeian": 0.65},
        },
    }
    if forum_rules_extra:
        cfg["forum_rules"].update(forum_rules_extra)
    state = GameState.create_for_testing(cfg)
    state.turn = GameTurn(turn_number=1, year=-264)

    for fid, fname in [("f1", "Optimates"), ("f2", "Populares"), ("f3", "Equites")]:
        state.add_faction(Faction(id=fid, name=fname, treasury=1000))
    for pid, fid in [("p1", "f1"), ("p2", "f2"), ("p3", "f3")]:
        state.add_player(Player(player_id=pid, faction_id=fid, player_type=PlayerType.HUMAN))
    state.set_turn_order(["p1", "p2", "p3"])
    state.set_current_player("p1")

    fig_counter = {"n": 0}

    def new_fig(faction_id, name, age, tier):
        fig_counter["n"] += 1
        fig = Figure(id=fig_counter["n"], name=name, faction_id=faction_id, age=age, class_tier=tier)
        fig.charisma = 5
        fig.intelligence = 5
        fig.martial = 5
        fig.zeal = 5
        fig.popularity = 10
        fig.wealth = 50
        fig.update_influence()
        state.add_member(fig)
        faction = state.get_faction(faction_id)
        if faction is not None:
            faction.member_ids.append(fig.id)
        return fig

    for fid in ["f1", "f2", "f3"]:
        new_fig(fid, f"eques-{fid}", 30, ClassTier.EQUES)
        new_fig(fid, f"pleb-{fid}", 30, ClassTier.PLEBEIAN)

    return state


def _veterans(figures):
    """注入者 = office_history 非空者。"""
    return [f for f in figures if f.office_history]


class TestVeteranSupplyMarketGuarantee:
    """T-VS-1 / T-VS-2 / T-VS-3：市场保证性 + 锚性质 + 不变量。"""

    def test_tvs1_market_guarantee_default_config(self):
        """默认配置（代码默认生效）：len==3；≥1 资深贵族含 consul/praetor；ex-consul ≥1。"""
        state = _make_state()
        figs = generate_market_figures(state)
        assert len(figs) == 3
        veterans = _veterans(figs)
        assert len(veterans) >= 1
        assert all(f.class_tier == ClassTier.NOBILE for f in veterans)
        assert any(
            any(t.office_type in ("consul", "praetor") for t in f.office_history)
            for f in veterans
        )
        ex_consuls = [
            f for f in veterans if any(t.office_type == "consul" for t in f.office_history)
        ]
        assert len(ex_consuls) >= 1  # min_ex_consul_count=1

    def test_tvs2_censor_anchor_property(self):
        """censor-anchor：存在 consul 任期距今 == censor_anchor_years_ago 者；
        对其 censor Eligible、consul 冷却阻断。"""
        state = _make_state()
        figs = generate_market_figures(state)
        ct = state.turn.turn_number
        anchor_ago = 1
        anchors = [
            f for f in figs
            if any(
                t.office_type == "consul" and ct - t.start_turn == anchor_ago
                for t in f.office_history
            )
        ]
        assert len(anchors) >= 1, "censor-anchor 必须存在（槽 1 确定性）"
        anchor = anchors[0]
        ok, reason = anchor.can_hold_office("censor", ct, state.config)
        assert (ok, reason) == (True, "Eligible")
        ok, reason = anchor.can_hold_office("consul", ct, state.config)
        assert ok is False
        assert reason == "Cooldown: 1/2 years"

    def test_tvs3_history_age_invariants(self):
        """全注入者不变量：office is None；每任期 start < end <= ct；is_active False；
        cursus 时序升序；consul 当年年龄 ≥40；现年龄 ≥42（censor 门槛）。"""
        state = _make_state()
        figs = generate_market_figures(state)
        ct = state.turn.turn_number
        veterans = _veterans(figs)
        assert len(veterans) >= 1
        min_ages = state.config.get("political_rules", {}).get("min_ages", {})
        for f in veterans:
            assert f.office is None
            starts = []
            for term in f.office_history:
                assert term.start_turn < ct, "任期必须严格过去"
                assert term.end_turn <= ct, "无未来年份"
                assert term.start_turn < term.end_turn
                assert term.is_active is False
                starts.append(term.start_turn)
            assert starts == sorted(starts), "cursus 时序升序"
            consul_terms = [t for t in f.office_history if t.office_type == "consul"]
            if consul_terms:
                consul_start = consul_terms[0].start_turn
                # 任职当年年龄 = 现年龄 - 距今回合数 >= min_ages.consul
                assert f.age - (ct - consul_start) >= min_ages["consul"]
            assert f.age >= min_ages["censor"]


class TestVeteranSupplyConfig:
    """T-VS-4 / T-VS-5：开关 + 参数 clamp。"""

    def test_tvs4_disabled_zero_injection(self):
        """enabled=false → 零注入（全部新人 office_history 为空，现状保持）。"""
        state = _make_state({"veteran_supply": {"enabled": False}})
        figs = generate_market_figures(state)
        assert len(figs) == 3
        assert all(f.office_history == [] for f in figs)

    def test_tvs5_min_max_2_exactly_two_veterans(self):
        """min=max=2 → 恰 2 资深（k 恒定）。"""
        state = _make_state({
            "veteran_supply": {"min_veteran_nobiles": 2, "max_veteran_nobiles": 2},
        })
        figs = generate_market_figures(state)
        assert len(figs) == 3
        assert len(_veterans(figs)) == 2

    def test_tvs5_count1_clamp(self):
        """count=1 → k ≤ 1（clamp 到 count）。"""
        state = _make_state({"new_figures_count": 1})
        figs = generate_market_figures(state)
        assert len(figs) == 1
        assert len(_veterans(figs)) == 1  # k = randint(1, min(2,1)=1) = 1

    def test_tvs5_count0_zero_figures(self):
        """count=0 → k=0（零注入语义）。

        注：generate_market_figures 的 count 解析为既有 `or 3` 回退语义
        （new_figures_count=0 → 3，产品现状，非本机制变更面）——本用例直接验证
        k 解析单元（零注入、零生成），实现级注记见实施报告。
        """
        state = _make_state({"new_figures_count": 0})
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        assert fgs._resolve_veteran_slot_count(0, plan) == 0


class TestVeteranSupplyLiveChain:
    """T-VS-6 / T-VS-8 / T-VS-9：实况链 + 招募端到端 + 跨回合演进。"""

    def test_tvs6_generate_figures_with_hero(self):
        """generate_figures 含 hero：普通人物 ≥1 资深；hero 零注入；总数 count+hero 不变。"""
        state = _make_state()
        state.hero_spawned_this_turn = True
        state.hero_to_spawn = {"type": "random"}
        figs = generate_figures(state)
        assert len(figs) == 4  # 3 普通 + 1 hero
        normal = figs[:-1]
        hero = figs[-1]
        assert len(_veterans(normal)) >= 1
        assert hero.office_history == []  # hero 路径零注入

    def test_tvs8_recruit_chain_end_to_end(self):
        """招募链端到端：generate → recruit_figure → resolve_forum → faction_id 就位
        → get_candidates censor ≥1 / consul ≥1。"""
        from src.api import forum_api, population_api

        state = _make_state({
            "veteran_supply": {"min_veteran_nobiles": 2, "max_veteran_nobiles": 2},
        })
        figs = generate_market_figures(state)
        assert len(figs) == 3
        # 真实招募链：p1 对每个新人出价 → resolve_forum 结算
        for fig in figs:
            resp = forum_api.recruit_figure(state, "p1", fig.id, 10)
            assert resp["success"] is True
        forum_api.resolve_forum(state)
        for fig in figs:
            assert fig.faction_id == "f1", "resolve_forum 后新人必须入派系"
        population_api.begin_population_phase(state)
        cands = population_api.get_candidates(state)["data"]
        assert len(cands["censor"]) >= 1, "锚（ex-consul）保证 censor ≥1"
        assert len(cands["consul"]) >= 1, "槽 2（ex-consul/ex-praetor）保证 consul ≥1"

    def test_tvs9_cross_turn_cooldown_evolution(self):
        """跨回合冷却演进：T 注入锚 → T+1 起 consul 资格恢复（years_ago=2）。"""
        state = _make_state()
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        anchor = fgs._create_veteran_nobile(state, 0, plan)
        state.add_member(anchor)
        ct1 = state.turn.turn_number  # 1
        ok, reason = anchor.can_hold_office("consul", ct1, state.config)
        assert ok is False
        assert reason == "Cooldown: 1/2 years"
        state.turn.advance_year()  # T+1
        ct2 = state.turn.turn_number  # 2
        ok, reason = anchor.can_hold_office("consul", ct2, state.config)
        assert (ok, reason) == (True, "Eligible")


class TestVeteranSupplyEligibilityMatrix:
    """T-VS-7：§5.1 全资格矩阵（含原因串精确匹配）。"""

    def _make_anchor(self, state, plan):
        return fgs._create_veteran_nobile(state, 0, plan)

    def _make_ex_consul(self, state, plan):
        # min_ex_consul_count=2 → slot 1 强制 ex-consul（h ∈ [2,8]）
        plan2 = dict(plan, min_ex_consul_count=2)
        return fgs._create_veteran_nobile(state, 1, plan2)

    def _make_ex_praetor(self, state, plan):
        # ex_consul_probability=0 → slot 1 必掷 ex-praetor
        plan2 = dict(plan, ex_consul_probability=0.0)
        return fgs._create_veteran_nobile(state, 1, plan2)

    def test_tvs7_anchor_matrix(self):
        """censor-anchor：consul 冷却 ✗ / censor ✓ / praetor·quaestor·tribune 高阶禁选 ✗。"""
        state = _make_state()
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        fig = self._make_anchor(state, plan)
        ct = state.turn.turn_number
        assert fig.can_hold_office("consul", ct, state.config) == (False, "Cooldown: 1/2 years")
        assert fig.can_hold_office("censor", ct, state.config) == (True, "Eligible")
        assert fig.can_hold_office("praetor", ct, state.config) == (
            False, "Has held higher office: consul")
        assert fig.can_hold_office("quaestor", ct, state.config) == (
            False, "Has held higher office: praetor")
        assert fig.can_hold_office("tribune", ct, state.config) == (
            False, "Has held higher office: quaestor")

    def test_tvs7_ex_consul_matrix(self):
        """ex-consul（h ≥ 2）：consul ✓ / censor ✓ / praetor·quaestor·tribune 高阶禁选 ✗。"""
        state = _make_state()
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        fig = self._make_ex_consul(state, plan)
        ct = state.turn.turn_number
        assert fig.can_hold_office("consul", ct, state.config) == (True, "Eligible")
        assert fig.can_hold_office("censor", ct, state.config) == (True, "Eligible")
        assert fig.can_hold_office("praetor", ct, state.config) == (
            False, "Has held higher office: consul")
        assert fig.can_hold_office("quaestor", ct, state.config) == (
            False, "Has held higher office: praetor")
        assert fig.can_hold_office("tribune", ct, state.config) == (
            False, "Has held higher office: quaestor")

    def test_tvs7_ex_praetor_matrix(self):
        """ex-praetor：consul ✓ / censor ✗ Requires prior Consul service / praetor ✓ /
        quaestor·tribune 高阶禁选 ✗。"""
        state = _make_state()
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        fig = self._make_ex_praetor(state, plan)
        ct = state.turn.turn_number
        assert fig.can_hold_office("consul", ct, state.config) == (True, "Eligible")
        assert fig.can_hold_office("censor", ct, state.config) == (
            False, "Requires prior Consul service")
        assert fig.can_hold_office("praetor", ct, state.config) == (True, "Eligible")
        assert fig.can_hold_office("quaestor", ct, state.config) == (
            False, "Has held higher office: praetor")
        assert fig.can_hold_office("tribune", ct, state.config) == (
            False, "Has held higher office: quaestor")

    def test_tvs7_ex_consul_eligibility_reason_detail(self):
        """ex-consul 的 consul 冷却放行原因核验：h ∈ [2,8] → years_ago ≥ 2。"""
        state = _make_state()
        plan = _read_veteran_supply_config(state.config.get("forum_rules", {}))
        for _ in range(20):
            fig = self._make_ex_consul(state, plan)
            ct = state.turn.turn_number
            consul_terms = [t for t in fig.office_history if t.office_type == "consul"]
            assert len(consul_terms) == 1
            years_ago = ct - consul_terms[0].start_turn
            assert years_ago >= 2
            assert fig.can_hold_office("consul", ct, state.config) == (True, "Eligible")
