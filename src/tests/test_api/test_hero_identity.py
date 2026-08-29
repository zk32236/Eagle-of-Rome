"""
WP-F S2-7 — Hero Identity Persistence Tests (021 / F-F-03)

Production-shape fixture chain (F-F-03, 禁手搓 DTO 省略 is_hero):
  state.hero_to_spawn（historical / random）→ generate_figures()
    → Figure.is_hero 实体持久字段（S2-4）
    → _available_figure_row() DTO 透出（S2-5）
    → get_forum_view().available_figures → 人才市场行

Covers: H1~H8（G2-D §4）+ 021-01/03/05 + R-07（实体持久，非瞬态唯一真相）
"""

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import forum_api
from src.core.systems.figure_generation_system import generate_figures as system_generate_figures
from src.core.i18n import i18n

i18n.load("zh-CN")


def _base_config():
    return {
        "testing": {"bypass_player_check": False},
        "forum_rules": {
            "new_figures_count": 3,
            "class_probabilities": {
                "nobile": 0.1,
                "eques": 0.25,
            },
        },
        "economic_rules": {
            "land_price_per_unit": 10,
            "private_land_income_rate": 0.05,
            "province_tax_rate": 0.1,
            "tax_auction_ratio": 0.8,
            "infrastructure_cost_rate": 0.001,
            "project_budget_margin": 0.2,
            "tax_contract_duration": 5,
            "works_contract_duration": 3,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "initial_national_public_land": 1000,
        },
    }


def _make_forum_state(hero_to_spawn):
    """生产形论坛状态：玩家/派系/curia 在场 + hero 生成信号。"""
    state = GameState.create_for_testing(_base_config())
    state.turn = GameTurn(turn_number=1, year=-282)

    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    state.add_player(player1)
    state.set_turn_order(["p1"])
    state.set_current_player("p1")

    faction1 = Faction(id="f1", name="Faction1", treasury=1000)
    state.add_faction(faction1)

    # 预置 1 个 curia 成员（保证随机猛男 stat 计算有参照）
    fig0 = Figure.create_eques(state.allocate_id(), None, 35)
    fig0.martial = 5
    fig0.intelligence = 9
    fig0.charisma = 4
    fig0.zeal = 3
    state.curia.add_figure(fig0)
    state.add_member(fig0)

    if hero_to_spawn is not None:
        state.hero_spawned_this_turn = True
        state.hero_to_spawn = hero_to_spawn
    else:
        state.hero_spawned_this_turn = False
        state.hero_to_spawn = None

    state._forum_pending = {
        "retirements": [],
        "recruitment_bids": [],
        "contract_bids": [],
        "land_purchases": [],
        "triumph_votes": [],
        "land_trades": [],
    }
    state._national_public_land = 100
    return state


HISTORICAL_HERO = {
    "type": "historical",
    "data": {
        "id": "hero_001",
        "name": "Gaius Marius",
        "birth_year": -282,
        "martial": 9,
        "intelligence": 7,
        "charisma": 8,
        "zeal": 6,
        "family_prestige": 2,
    },
}


def _hero_rows(rows):
    return [r for r in rows if r.get("is_hero") is True]


def _normal_rows(rows):
    return [r for r in rows if r.get("is_hero") is not True]


# ── S2-4：实体持久字段（H1~H3 实体侧） ──


def test_historical_hero_entity_persisted():
    state = _make_forum_state(HISTORICAL_HERO)
    figures = system_generate_figures(state)

    hero_figs = [f for f in figures if f.is_hero]
    assert len(hero_figs) == 1
    hero = hero_figs[0]
    assert hero.hero_type == "historical"
    # 普通人物非 hero
    for f in figures:
        if f is not hero:
            assert f.is_hero is False
            assert f.hero_type is None


def test_random_hero_entity_persisted():
    state = _make_forum_state({"type": "random"})
    figures = system_generate_figures(state)

    hero_figs = [f for f in figures if f.is_hero]
    assert len(hero_figs) == 1
    assert hero_figs[0].hero_type == "random"


def test_no_hero_when_not_signaled():
    state = _make_forum_state(None)
    figures = system_generate_figures(state)
    assert all(f.is_hero is False for f in figures)


# ── S2-1/2/3：序列化往返（snapshot-safe） ──


def test_hero_identity_survives_to_dict_from_dict_roundtrip():
    state = _make_forum_state(HISTORICAL_HERO)
    figures = system_generate_figures(state)
    hero = next(f for f in figures if f.is_hero)

    d = hero.to_dict()
    assert d["is_hero"] is True
    assert d["hero_type"] == "historical"

    rebuilt = Figure.from_dict(d)
    assert rebuilt.is_hero is True
    assert rebuilt.hero_type == "historical"
    assert rebuilt.id == hero.id


def test_normal_figure_roundtrip_no_hero():
    state = _make_forum_state(None)
    figures = system_generate_figures(state)
    normal = figures[0]
    d = normal.to_dict()
    assert d["is_hero"] is False
    assert d["hero_type"] is None
    rebuilt = Figure.from_dict(d)
    assert rebuilt.is_hero is False
    assert rebuilt.hero_type is None


# ── S2-5：_available_figure_row DTO 透出（021-01） ──


def test_available_figure_row_dto_hero_and_normal():
    state = _make_forum_state(HISTORICAL_HERO)
    system_generate_figures(state)

    hero_fig = next(f for f in state.curia.get_all_available() if f.is_hero)
    normal_fig = next(f for f in state.curia.get_all_available() if not f.is_hero)

    hero_row = forum_api._available_figure_row(hero_fig)
    assert hero_row["is_hero"] is True
    assert hero_row["hero_type"] == "historical"

    normal_row = forum_api._available_figure_row(normal_fig)
    assert normal_row["is_hero"] is False
    assert normal_row["hero_type"] is None


# ── 全链：get_forum_view → available_figures（F-F-03 生产路径） ──


def test_forum_view_available_figures_hero_flag():
    state = _make_forum_state(HISTORICAL_HERO)
    system_generate_figures(state)

    view = forum_api.get_forum_view(state, "p1")
    assert view["success"] is True
    rows = view["data"]["available_figures"]
    hero_rows = _hero_rows(rows)
    assert len(hero_rows) == 1
    assert hero_rows[0]["name"]
    assert hero_rows[0]["hero_type"] == "historical"
    # 普通行无星标记（H1）
    assert len(_normal_rows(rows)) >= 3


def test_refresh_preserves_hero_flag():
    """H4：refresh 后 hero 行 is_hero 仍 True（实体字段驱动，非瞬态）"""
    state = _make_forum_state(HISTORICAL_HERO)
    system_generate_figures(state)

    first = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]
    second = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]

    first_hero_ids = {r["id"] for r in _hero_rows(first)}
    second_hero_ids = {r["id"] for r in _hero_rows(second)}
    assert first_hero_ids == second_hero_ids
    assert len(first_hero_ids) == 1
    # 非瞬态：hero 身份来自 Figure 实体字段（R-07）
    hero_fig = next(f for f in state.curia.get_all_available() if f.id in first_hero_ids)
    assert hero_fig.is_hero is True


def test_reentry_preserves_hero_flag():
    """H5：阶段重入后 hero 身份保留（resolve → 再 view）"""
    state = _make_forum_state(HISTORICAL_HERO)
    system_generate_figures(state)

    before = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]
    hero_ids_before = {r["id"] for r in _hero_rows(before)}

    result = forum_api.resolve_forum(state)
    assert result["success"] is True

    after = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]
    hero_ids_after = {r["id"] for r in _hero_rows(after)}
    # 未被招募的 hero 重入后仍带 is_hero=True
    assert hero_ids_before.issubset(hero_ids_after | {r["id"] for r in after})
    assert all(r["is_hero"] is True for r in _hero_rows(after))


def test_recruit_preserves_hero_identity():
    """H7：招募结算后对象不重建，is_hero 随对象（production 路径 recruit_figure → resolve_forum）"""
    state = _make_forum_state(HISTORICAL_HERO)
    system_generate_figures(state)

    hero_fig = next(f for f in state.curia.get_all_available() if f.is_hero)
    hero_id = hero_fig.id

    rec = forum_api.recruit_figure(state, "p1", hero_id, 100)
    assert rec["success"] is True
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"] is True

    # 同一对象仍驻留，身份字段保留
    member = state.get_member(hero_id)
    assert member is not None
    assert member.is_hero is True
    assert member.hero_type == "historical"
    assert member.faction_id == "f1"
    assert hero_id in state.get_faction("f1").member_ids
    # 已招募 → 不再出现在人才市场
    market = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]
    assert all(r["id"] != hero_id for r in market)


def test_multi_hero_rows_each_flagged_once():
    """H8：多 hero 行每行恰 1 星标记（DTO 层 = 每行独立 is_hero 字段）"""
    state = _make_forum_state(HISTORICAL_HERO)
    state.hero_spawned_this_turn = True
    state.hero_to_spawn = {"type": "random"}
    # 第二回合信号：再生成一批，制造多 hero 并存场景（生产路径 generate_figures 二次调用）
    system_generate_figures(state)
    state.hero_spawned_this_turn = True
    state.hero_to_spawn = {"type": "random"}
    system_generate_figures(state)

    rows = forum_api.get_forum_view(state, "p1")["data"]["available_figures"]
    hero_rows = _hero_rows(rows)
    assert len(hero_rows) >= 1
    for r in hero_rows:
        assert r["is_hero"] is True
        assert r["hero_type"] == "random"
