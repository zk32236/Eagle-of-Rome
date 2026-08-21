# src/tests/test_integration/test_population_5turn_runtime.py
"""
WP-A 5-turn 连续 runtime 集成测试（T1.1-T1.6）。

验证官职归档系统性修复后：当选者跨回合正确演进（现任→ex-、任期进 office_history），
候选人池结构性收敛（ODR-5 ex-consul 溢出机制 + 年龄≥42 censor 条件），
连续 5 回合人口阶段持续推进、无 consul 前置硬阻断。

确定性 seed：所有人物以显式属性构造（零 random 依赖）；resolve_election 的平局
tie-break 用 monkeypatch 冻结 random.choice。
"""
import random

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import population_api

_OFFICES = ["consul", "censor", "praetor", "quaestor", "tribune"]


def _production_political_rules():
    """生产等价 political_rules（对齐 data/config/game_config.json）。"""
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


def _make_runtime_state() -> GameState:
    """确定性种子状态：3 派系，每派系 1 ex-consul / 1 ex-praetor / 1 ex-quaestor
    + 年轻 eques/plebeian 供给（对齐 scenario_loader 结构，零 random）。"""
    state = GameState.create_for_testing({
        "testing": {"bypass_player_check": True},
        "political_rules": _production_political_rules(),
    })
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
        fig = Figure(
            id=fig_counter["n"],
            name=name,
            faction_id=faction_id,
            age=age,
            class_tier=tier,
        )
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
        # ex-consul（quaestor→praetor→consul，高 charisma）
        ec = new_fig(fid, f"ex-consul-{fid}", 50, ClassTier.NOBILE)
        ec.add_office_history("quaestor", -8, -7)
        ec.add_office_history("praetor", -5, -4)
        ec.add_office_history("consul", -2, -1)
        ec.charisma = 9
        # ex-praetor（quaestor→praetor，高 intelligence）
        ep = new_fig(fid, f"ex-praetor-{fid}", 45, ClassTier.NOBILE)
        ep.add_office_history("quaestor", -6, -5)
        ep.add_office_history("praetor", -3, -2)
        ep.intelligence = 9
        # ex-quaestor
        eq = new_fig(fid, f"ex-quaestor-{fid}", 35, ClassTier.NOBILE)
        eq.add_office_history("quaestor", -4, -3)
        eq.martial = 9
        # 年轻 eques/plebeian 供给（tribune / quaestor）
        for k in range(2):
            new_fig(fid, f"eques-{fid}-{k}", 33, ClassTier.EQUES)
        for k in range(2):
            new_fig(fid, f"pleb-{fid}-{k}", 33, ClassTier.PLEBEIAN)

    return state


def _elect(state: GameState, viewer_id: str, cands: dict) -> dict:
    """确定性选举：每 office 投给第一个候选人，resolve_election 计票。"""
    for office in _OFFICES:
        rows = cands.get(office, [])
        if rows:
            state.record_population_vote(viewer_id, office, rows[0]["id"], replace=True)
    result = population_api.resolve_election(state)
    winners = {}
    for er in result.get("data", {}).get("election_results", []):
        winners[er["office"]] = er["figure_id"]
    return winners


def _advance_year(state: GameState) -> None:
    """模拟年度推进：turn+1、清空 phase_results（重置 population_entry marker）、清空投票。"""
    state.turn.advance_year()
    state.clear_population_pending()
    state._phase_results.clear()
    state._executed_phases.clear()


@pytest.fixture(autouse=True)
def _freeze_rng(monkeypatch):
    """冻结 resolve_election 平局 tie-break（确定性）。"""
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])


class TestPopulation5TurnRuntime:
    """WP-A 5-turn 连续 runtime：跨回合归档 + 候选池结构性收敛。"""

    def test_5turn_runtime_t1_1_all_offices_have_candidates(self):
        """T1.1：Turn1 五官职候选池非空。"""
        state = _make_runtime_state()
        population_api.begin_population_phase(state)
        cands = population_api.get_candidates(state)["data"]
        for office in _OFFICES:
            assert len(cands.get(office, [])) >= 1, f"Turn1 {office} 池空"

    def test_5turn_runtime_t1_2_winners_archived_next_turn(self):
        """T1.2：Turn2 入口后上回合当选者 office=ex-*、history+1。"""
        state = _make_runtime_state()
        population_api.begin_population_phase(state)
        cands = population_api.get_candidates(state)["data"]
        winners = _elect(state, "p1", cands)
        assert len(winners) >= 1

        hist_before = {
            office: len(state.get_member(fid).office_history)
            for office, fid in winners.items()
        }
        # 当选者当回合 office=office（非 ex-）
        for office, fid in winners.items():
            assert state.get_member(fid).office == office

        _advance_year(state)
        population_api.begin_population_phase(state)
        for office, fid in winners.items():
            fig = state.get_member(fid)
            assert fig.office == f"ex-{office}"
            assert len(fig.office_history) == hist_before[office] + 1

    def test_5turn_runtime_t2_censor_pool_nonempty(self):
        """T1.3：Turn2 censor 候选池 ≥1（ex-consul 溢出），且年龄≥42（006 闭合）。"""
        state = _make_runtime_state()
        population_api.begin_population_phase(state)
        cands1 = population_api.get_candidates(state)["data"]
        _elect(state, "p1", cands1)
        _advance_year(state)

        population_api.begin_population_phase(state)
        cands2 = population_api.get_candidates(state)["data"]
        censor_ids = [c["id"] for c in cands2.get("censor", [])]
        assert len(censor_ids) >= 1, "Turn2 censor 池为空"
        for fid in censor_ids:
            assert state.get_member(fid).age >= 42, f"censor 候选 {fid} 年龄 < 42"

    def test_5turn_runtime_t3_pools_not_shrunk(self):
        """T1.4：Turn3 consul/censor/praetor 候选池不收缩（008 闭合）。"""
        state = _make_runtime_state()
        for t in range(3):
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            if t == 2:
                for office in ["consul", "censor", "praetor"]:
                    assert len(cands.get(office, [])) >= 1, f"Turn3 {office} 池收缩"
            _elect(state, "p1", cands)
            _advance_year(state)

    def test_5turn_runtime_t4_pools_nonempty_and_advance(self):
        """T1.5：Turn4 三高阶池非空 + resolve + advance 成功（012 闭合）。"""
        state = _make_runtime_state()
        for t in range(4):
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            if t == 3:
                for office in ["consul", "censor", "praetor"]:
                    assert len(cands.get(office, [])) >= 1, f"Turn4 {office} 池空"
            winners = _elect(state, "p1", cands)
            if t == 3:
                assert len(winners) >= 1
            _advance_year(state)
        assert state.turn.turn_number == 5

    def test_5turn_runtime_t5_continues_to_senate(self):
        """T1.6：Turn5 持续推进，无 consul 前置硬阻断。"""
        state = _make_runtime_state()
        for t in range(5):
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            _elect(state, "p1", cands)
            _advance_year(state)
        # 5 回合持续推进，turn 已到 6，且下一轮人口入口仍可正常归档/计算候选
        assert state.turn.turn_number == 6
        population_api.begin_population_phase(state)
        cands = population_api.get_candidates(state)["data"]
        assert set(cands.keys()) == set(_OFFICES)
