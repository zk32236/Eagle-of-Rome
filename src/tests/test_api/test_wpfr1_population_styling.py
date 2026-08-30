# src/tests/test_api/test_wpfr1_population_styling.py
"""WP-F-R1 T-F01~T-F03：Population 候选人 / 当选者派系着色（R1-F-01 / R1-F-02）。

DATA 断言（权威身份）+ QML 源码断言（消费点修正）：
- T-F01  candidate DTO 权威 faction_id（population_api.get_candidates）+ PopulationStage
         投票面板消费裸 modelData.faction_id（L629 parent.modelData → modelData，R1-F-01）
- T-F02  election_results 权威 faction_id（resolve_election）+ 当选者颜色走
         factionColor(result.faction_id)（R1-F-02；✅ text / font.bold winner 通道保留断言）
- T-F03  运行时面（PopulationStage）无硬编码通用绿 #008000、无 parent.modelData；
         ElectionResultView.qml（NOT_USED 死文件，app.py 不再实例化）原样保留 → WP-H 候选。
"""
import os

import pytest

from src.api import population_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
POPULATION_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "PopulationStage.qml")
ELECTION_RESULT_VIEW_QML = os.path.join(
    PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "ElectionResultView.qml"
)


def _read_qml(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def state():
    """三派系 × 3 候选人（9 人）：consul/censor/quaestor 各 top3 全量覆盖三派系。

    cursus honorum：consul 需 prior praetor；censor 需 prior consul（censor 豁免高阶检查）；
    quaestor 无前置要求。candidates_per_election 覆盖为 3 使三派系均入候选。
    """
    config = {
        "political_rules": {
            "candidates_per_election": {
                "consul": 3, "censor": 3, "praetor": 3, "quaestor": 3, "tribune": 3,
            },
        },
    }
    s = GameState.create_for_testing(config)
    s.turn = GameTurn(turn_number=1, year=-282)
    s._population_pending = {
        "campaigns": [],
        "votes": [],
        "committed_batches": set(),
        "committed_vote_batches": set(),
    }
    for fid, name in (("f1", "Optimates"), ("f2", "Populares"), ("f3", "Equites")):
        s.add_faction(Faction(id=fid, name=name, treasury=500))
    # consul 候选人（prior praetor，按 charisma 取 top3）
    for fig_id, fid, age, val in ((11, "f1", 45, 100), (21, "f2", 46, 95), (31, "f3", 47, 85)):
        fig = Figure.create_nobile_with_history(fig_id, fid, previous_office="praetor", age=age)
        fig.charisma = val
        fig.update_influence()
        s.add_member(fig)
    # censor 候选人（prior consul，按 zeal 取 top3；censor 豁免高阶职务检查）
    for fig_id, fid, age, val in ((12, "f1", 44, 90), (22, "f2", 43, 85), (32, "f3", 42, 75)):
        fig = Figure.create_nobile_with_history(fig_id, fid, previous_office="consul", age=age)
        fig.zeal = val
        fig.update_influence()
        s.add_member(fig)
    # quaestor 候选人（无前置要求，按 intelligence 取 top3）
    for fig_id, fid, age, val in ((41, "f1", 40, 100), (42, "f2", 39, 90), (43, "f3", 38, 80)):
        fig = Figure.create_nobile(fig_id, fid, age)
        fig.intelligence = val
        fig.update_influence()
        s.add_member(fig)
    for pid, fid in (("p1", "f1"), ("p2", "f2"), ("p3", "f3")):
        s.add_player(Player(player_id=pid, faction_id=fid, player_type=PlayerType.HUMAN))
    s.set_turn_order(["p1", "p2", "p3"])
    s.set_current_player("p1")
    return s


def test_tf01_candidate_renderer_authoritative_faction_identity(state):
    """T-F01（AC-F01-1/2/3/5）：candidate DTO 权威 faction_id；QML 消费裸 modelData.faction_id。"""
    res = population_api.get_candidates(state)
    assert res["success"], res.get("message")
    all_cands = [c for rows in res["data"].values() for c in rows]
    assert len(all_cands) >= 6
    for c in all_cands:
        assert "faction_id" in c, f"candidate {c.get('id')} lacks authoritative faction_id"
    assert {c["faction_id"] for c in all_cands} == {"f1", "f2", "f3"}

    src = _read_qml(POPULATION_QML)
    assert "parent.modelData" not in src  # R1-F-01 修正后全仓唯一命中点消除
    assert "factionStyle.factionColor(modelData.faction_id)" in src  # 投票面板 RadioButton contentItem


def test_tf02_winner_authoritative_faction_identity(state):
    """T-F02（AC-F02-1/2/3/4）：election_results 权威 faction_id；QML 走 factionColor(result.faction_id)。"""
    state.record_population_vote("p1", "consul", 11)
    state.record_population_vote("p2", "censor", 22)
    state.record_population_vote("p3", "quaestor", 43)
    res = population_api.resolve_election(state)
    assert res["success"], res.get("message")
    results = res["data"].get("election_results") or []
    assert len(results) >= 2, "fixture must produce multi-office election results"
    members = {m.id: m for m in state.get_living_members()}
    for r in results:
        assert "faction_id" in r, f"election result {r.get('office')} lacks authoritative faction_id"
        assert members[r["figure_id"]].faction_id == r["faction_id"]  # winner 派系一致
    assert len({r["faction_id"] for r in results}) >= 2  # 多派系当选者

    src = _read_qml(POPULATION_QML)
    assert "factionStyle.factionColor(result.faction_id)" in src  # R1-F-02 修正点
    # AC-F02-4：winner 状态通道保留（✅ 前缀 + font.bold）
    assert 'text: result ? ("✅ " + result.figure_name) : "—"' in src
    assert "font.bold: !!result" in src


def test_tf03_no_hardcoded_universal_green_runtime_surface(state):
    """T-F03（AC-F02-5）：运行时面无 #008000 / parent.modelData；死文件不改（WP-H 候选）。"""
    src = _read_qml(POPULATION_QML)
    assert "#008000" not in src
    assert "parent.modelData" not in src
    # 归档死文件 ElectionResultView.qml（NOT_USED，2026-08-09 AC-12 M2-BUG2）保留原样：
    # 其 #008000 属 WP-H 清理候选，不属 R1-F-02 运行时面（不处理、不越界）。
    dead = _read_qml(ELECTION_RESULT_VIEW_QML)
    assert "NOT_USED" in dead
    assert "#008000" in dead
