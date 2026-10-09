# src/tests/test_api/test_wpj_groupc_population_featured.py
"""WP-J Group C-1 (J-AC-05a / BL-G7-07) — 权威 featured 只读投影。

冻结契约（`02-sa-design/GroupC/` v1.1 §4）：
- FC-C01 单一 owner = `session_api.get_population_view()`；office 级
  `featured_candidate_id`（int/null）+ 行级 `is_featured`（bool）。
- FC-C02 谓词：① resolved 且 `election_results` 含该 office → 当选者；
  ② 否则提名集内 `qualification_attribute(office)` 最大 → first-name A-Z →
  figure_id 升序；③ office 空 → none。
- FC-C07 vacant office → 无 featured（不伪造）。

No-Test-Assisted-Transition：resolved 分支经真实生产动作
（`session_api.submit_population_votes` → `resolve_population_slice`）到达，
不直置 store featured / 不 QML 自算 / 不改提名集。
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from src.api import population_api, session_api  # noqa: E402
from src.core.entities.figure import Figure  # noqa: E402

OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")

# FC-C02 权威映射（figure.get_qualification_attribute）
_QUALIFICATION_ATTR = {
    "consul": "charisma",
    "censor": "zeal",
    "praetor": "intelligence",
    "quaestor": "martial",
    "tribune": None,  # 未配置 → 全 0
}


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    """进程级 RNG guard（防 cross-test 泄漏；同 wpm/wpo_rng_guard 机制）。"""
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


def _population_session():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    return state, viewer


def _add_consul_candidates(state, faction_id, praenomina, base_id=880001):
    """确定性 consul 提名候选（prior praetor 满足 cursus prerequisite；charisma 置高保证入选）。"""
    ids = []
    for offset, praenomen in enumerate(praenomina):
        fid = base_id + offset
        if state.get_member(fid) is None:
            fig = Figure.create_nobile_with_history(
                fid, faction_id, previous_office="praetor", age=50
            )
            fig.charisma = 999999  # consul 资格属性（charisma）置顶，保证 top-2 入选
            fig.praenomen = praenomen
            state.add_member(fig)
        else:
            state.get_member(fid).praenomen = praenomen
            state.get_member(fid).charisma = 999999
        ids.append(fid)
    return ids


def _qualification_values(state, office, rows):
    attr = _QUALIFICATION_ATTR.get(office)
    out = {}
    for row in rows:
        fig = state.get_member(row["id"])
        val = fig.get_qualification_attribute(office) if fig is not None else 0
        out[row["id"]] = (val, (fig.praenomen or "") if fig is not None else "")
    return out


# ---------------------------------------------------------------------------
# 未 resolved：每 office 恰 1 featured；featured = 资格属性最大（平局 first-name A-Z）
# ---------------------------------------------------------------------------

def test_featured_unresolved_one_per_office_max_attribute():
    state, viewer = _population_session()
    view = session_api.get_population_view(state, viewer)
    assert view["success"], view.get("message")
    data = view["data"]
    assert "featured_candidate_ids" in data, "缺 office 级 featured_candidate_id 投影（FC-C01）"

    candidates = data["candidates"]
    for office in OFFICES:
        rows = candidates.get(office, [])
        if not rows:
            assert data["featured_candidate_ids"].get(office) is None
            continue
        featured_flags = [r for r in rows if r.get("is_featured")]
        assert len(featured_flags) == 1, f"{office}: 每 office 恰 1 行 is_featured"
        feat_id = data["featured_candidate_ids"][office]
        assert featured_flags[0]["id"] == feat_id, f"{office}: featured_candidate_id 与行使者一致"

        quals = _qualification_values(state, office, rows)
        best_val = max(v[0] for v in quals.values())
        expect = min(
            (fid for fid, (v, _n) in quals.items() if v == best_val),
            key=lambda fid: (quals[fid][1], fid),
        )
        assert feat_id == expect, f"{office}: featured 应为资格属性最高（A-Z 平局）"


# ---------------------------------------------------------------------------
# 平局 → first-name A-Z（确定性）
# ---------------------------------------------------------------------------

def test_featured_tie_break_first_name_az():
    state, viewer = _population_session()
    faction_id = state.get_player(viewer).faction_id
    # 确定性：注入两名 consul 提名候选（同资格属性 → 平局 → first name A-Z）
    ids = _add_consul_candidates(state, faction_id, ["Zzz", "Aaa"])
    data = session_api.get_population_view(state, viewer)["data"]
    rows = data["candidates"]["consul"]
    present = {r["id"] for r in rows}
    assert set(ids).issubset(present), f"确定性候选须入选提名集: {ids} vs {present}"
    assert data["featured_candidate_ids"]["consul"] == ids[1], "平局须取 first name A-Z 第一"
    feat = [r for r in rows if r.get("is_featured")]
    assert len(feat) == 1 and feat[0]["id"] == ids[1]


def test_featured_tie_break_figure_id_final():
    """再平局（同资格属性 + 同 first name）→ figure_id 升序（确定性兜底）。

    用合成行（未注册 figure_id）直接验证谓词最终兜底（tribune 未配置资格属性 → 全 0）。
    """
    state, _viewer = _population_session()
    helper = session_api._derive_featured_candidate_id
    rows = [
        {"id": 900011, "name": "Same · NomenB · CognomenB", "tribune": 0},
        {"id": 900010, "name": "Same · NomenA · CognomenA", "tribune": 0},
    ]
    assert helper(state, "tribune", rows, []) == 900010, "最终平局须取 figure_id 升序"
    rows_swapped = list(reversed(rows))
    assert helper(state, "tribune", rows_swapped, []) == 900010


# ---------------------------------------------------------------------------
# resolved → featured = 当选者（真实生产链）
# ---------------------------------------------------------------------------

def test_featured_resolved_is_election_winner():
    state, viewer = _population_session()
    view = session_api.get_population_view(state, viewer)
    selection = {
        office: rows[0]["id"]
        for office, rows in view["data"]["candidates"].items() if rows
    }
    assert selection, "需可投票 candidate 集"
    resolve = session_api.submit_population_votes(state, viewer, selection)
    assert resolve["success"], resolve.get("message")

    resolved_view = session_api.get_population_view(state, viewer)
    data = resolved_view["data"]
    assert data["resolved"] is True, "真实结算后应 resolved"
    winners = {e["office"]: e["figure_id"] for e in data["election_results"]}
    assert winners, "结算须产出 election_results"
    for office, winner_id in winners.items():
        assert data["featured_candidate_ids"][office] == winner_id, \
            f"{office}: resolved 后 featured 必须 = 当选者（winner 永不隐藏）"
        rows = data["candidates"][office]
        feat = [r for r in rows if r.get("is_featured")]
        assert len(feat) == 1 and feat[0]["id"] == winner_id


# ---------------------------------------------------------------------------
# vacant / 空集 → featured = none（FC-C07）；helper 级
# ---------------------------------------------------------------------------

def test_featured_vacant_office_none():
    state, _viewer = _population_session()
    fn = getattr(session_api, "_derive_featured_candidate_id", None)
    assert callable(fn), "缺 featured 派生 helper（单一 owner = session_api）"
    assert fn(state, "tribune", [], []) is None, "office 空 → featured none（不伪造）"


def test_no_nomination_set_mutation():
    """featured 投影不得改提名集（行数/内容与 get_candidates 一致）。"""
    state, viewer = _population_session()
    raw = population_api.get_candidates(state)
    assert raw["success"], raw.get("message")
    base = {
        office: [(r["id"], r["name"]) for r in rows]
        for office, rows in raw["data"].items()
    }
    view = session_api.get_population_view(state, viewer)
    after = {
        office: [(r["id"], r["name"]) for r in rows]
        for office, rows in view["data"]["candidates"].items()
    }
    assert after == base, "featured 投影为 additive 只读，不得改提名集"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
