# src/tests/test_gui/test_escg7q1_entry_timing.py
"""ESC-WPJ-G7Q1-01 / ESC-S1 — T-ESC-01 入口瞬间反馈可见（AC-01）。

冻结设计（`02-sa-design/`）：
- FC-ESC-01：入口时点谓词 —— GUI 人口阶段 `get_population_view` 门控块内，
  在 `begin_population_phase` 之前调用 `population_api.process_population_disbandments`。
- FC-ESC-02：exactly-once（marker `population_disbandment`）。
- FC-ESC-05：读模型键 `population_outcome` 形状不变。

真实生产链：`create_gui_prototype_session(start_phase="population")` → 挂 resolved war →
**仅** `get_population_view`（入口；**不调** `resolve_population_slice`）。
改前（无 M1）⇒ outcome 空 shape ⇒ RED；加 M1 后 ⇒ 入口即含凯旋/解散 ⇒ GREEN。
"""
from src.api import session_api, population_api
from src.core.entities.war import War, WarStatus


def _session(start_phase="population"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    return state, viewer


def _attach_resolved_war(state, commander_id, legion_numbers=(), war_id="escg7q1-entry-war"):
    war = War(
        id=war_id, name="对迦太基战争", strength=5, threat_level=3,
        rewards={"treasury": 100, "land": 0, "family_prestige": 0},
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = WarStatus.RESOLVED
    war.set_soldier_share(20)
    war.set_triumph_commander(commander_id)
    war.set_triumph_approved(True)
    ms = state.get_military_system()
    for n in legion_numbers:
        ok, _msg = ms.recruit_legion(n)
        if ok:
            war.add_legion_number(n)
    state.get_war_system()._war_discard.append(war)
    return war


def test_aftermath_visible_on_entry_without_resolve():
    """AC-01 / FC-ESC-01：仅入口 `get_population_view`（不调 resolve）即产凯旋/解散反馈。"""
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))

    # 入口唯一调用（★ 不调 resolve_population_slice）
    resp = session_api.get_population_view(state, viewer)
    assert resp["success"], resp.get("message")
    outcome = resp["data"]["population_outcome"]

    assert any(t["war_name"] == "对迦太基战争" for t in outcome["triumphs"]), \
        "进入人口阶段瞬间即见凯旋（FC-ESC-01/AC-01）"
    assert outcome["legions"]["resolved_wars"]["total"] >= 1, \
        "进入人口阶段瞬间即见军团解散计数（FC-ESC-01/AC-01）"
    assert isinstance(state.get_phase_result("population_disbandment"), dict), \
        "入口置位 marker population_disbandment（FC-ESC-02）"


def test_entry_refresh_idempotent_no_double_mutation():
    """FC-ESC-02：入口重复刷新 → outcome 一致、零二次 mutation。"""
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1,))

    first = session_api.get_population_view(state, viewer)["data"]["population_outcome"]
    assert first["legions"]["resolved_wars"]["total"] >= 1, "首帧入口即产 payload"
    # 二次刷新（幂等 marker）
    second = session_api.get_population_view(state, viewer)["data"]["population_outcome"]
    assert first == second, "入口刷新幂等，无二次 mutation（FC-ESC-02）"
