# src/tests/test_api/test_wpj_groupd_population_outcome.py
"""WP-J Group-D-Aftermath (J-AC-04a) — DATA(PRODUCTION_CHAIN) 投影/谓词/空态测试。

冻结设计 v1.1（`02-sa-design/GroupD/`）：
- FC-D01：战后反馈读模型 `population_outcome` 单一 owner = `session_api.get_population_view()`。
- FC-D02：shape = {triumphs:[{war_id,war_name,commander_id,commander_name}],
                  legions:{resolved_wars:{total},deescalated:{total}}, fleets:[...]}；
          数据源逐字 = 权威 `state.get_phase_result("population_disbandment")`
          （回退 `population` phase result 的 `data.disbandment`）。
- FC-D03：凯旋即「已举行」iff 出现在 `process_triumph_and_disbandment().triumphs[]`。
- FC-D04：人口阶段不呈现「否决」（无 triumph_outcomes 载体）。
- FC-D05：军团/舰队解散 = 权威计数（resolved_wars.total / deescalated.total / fleets.length）。
- FC-D07：payload 空 → 不追加行（outcome 空 shape）。
- FC-D08：QML 零业务重建（投影层逐字透传，零重算）。

No-Test-Assisted-Transition（集成）：目标态经真实生产动作
`population_api.process_population_disbandments()`（GUI/CLI 共享 canonical 入口）到达。
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


def _view(state, viewer):
    resp = session_api.get_population_view(state, viewer)
    assert resp["success"], resp.get("message")
    return resp["data"]


def _empty_outcome():
    return {
        "triumphs": [],
        "legions": {"resolved_wars": {"total": 0}, "deescalated": {"total": 0}},
        "fleets": [],
    }


# ---------------------------------------------------------------------------
# 投影（FC-D01/FC-D02）
# ---------------------------------------------------------------------------

def test_population_outcome_key_present_and_empty_by_default():
    state, viewer = _session()
    data = _view(state, viewer)
    assert "population_outcome" in data, "get_population_view 必须 additive 暴露 population_outcome（FC-D01）"
    assert data["population_outcome"] == _empty_outcome(), "未结算 → 空 shape（FC-D07）"


def test_projection_reads_authoritative_disbandment_phase_result():
    state, viewer = _session()
    payload = {
        "triumphs": [
            {"war_id": "w1", "war_name": "对迦太基战争",
             "commander_id": 11, "commander_name": "阿格里帕"}
        ],
        "legions": {
            "resolved_wars": {"total": 3, "errors": []},
            "deescalated": {"total": 2, "errors": []},
        },
        "fleets": [7, 8],
        "re_entry": False,
    }
    state.record_phase_result("population_disbandment", payload)
    outcome = _view(state, viewer)["population_outcome"]
    assert outcome["triumphs"] == [
        {"war_id": "w1", "war_name": "对迦太基战争",
         "commander_id": 11, "commander_name": "阿格里帕"}
    ], "triumphs 逐字来自 producer DTO（FC-D02/FC-D03）"
    assert outcome["legions"]["resolved_wars"]["total"] == 3
    assert outcome["legions"]["deescalated"]["total"] == 2
    assert outcome["fleets"] == [7, 8]
    # FC-D04：不得重引入 triumph_outcomes（否决载体已撤销）
    assert "triumph_outcomes" not in outcome


def test_projection_falls_back_to_population_phase_result_disbandment():
    state, viewer = _session()
    fallback = {
        "triumphs": [{"war_id": "w2", "war_name": "皮洛士战争",
                      "commander_id": 22, "commander_name": "费边"}],
        "legions": {"resolved_wars": {"total": 1, "errors": []},
                    "deescalated": {"total": 0, "errors": []}},
        "fleets": [],
        "re_entry": False,
    }
    state.record_phase_result("population", {
        "success": True, "message": "Election resolved",
        "data": {"election_results": [], "disbandment": fallback},
    })
    # CS03B A1（仅入径修订）：FC-D02 回退分支 = marker 缺席 → 回退 population.data.disbandment。
    # 【修订】不经 get_population_view（其人口阶段入口现必经 M1，置位空 marker
    #   ⇒ 回退分支被遮蔽）；直调投影（与 get_population_view 同一入参
    #   result_data = 相位 result 的 data）。断言逐条不变，无弱化。
    assert state.get_phase_result("population_disbandment") is None, \
        "本测试前提：marker 缺席（FC-D02 fallback 分支方可达）"
    result_data = state.get_phase_result("population").get("data", {})
    outcome = session_api._project_population_outcome(state, result_data)
    assert outcome["triumphs"][0]["war_name"] == "皮洛士战争", "回退 population.data.disbandment（FC-D02）"
    assert outcome["legions"]["resolved_wars"]["total"] == 1


def test_projection_empty_payload_no_fabrication():
    state, viewer = _session()
    state.record_phase_result("population_disbandment", {
        "triumphs": [],
        "legions": {"resolved_wars": {"total": 0, "errors": []},
                    "deescalated": {"total": 0, "errors": []}},
        "fleets": [],
        "re_entry": False,
    })
    assert _view(state, viewer)["population_outcome"] == _empty_outcome(), "全空 → 空 shape（FC-D07）"


# ---------------------------------------------------------------------------
# 集成：真实生产链（process_population_disbandments = GUI/CLI canonical 入口）
# ---------------------------------------------------------------------------

def _attach_resolved_war(state, commander_id, legion_numbers=()):
    war = War(
        id="wpj-gd-aftermath-war", name="对迦太基战争", strength=5, threat_level=3,
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


def test_production_chain_triumph_and_legion_disbandment_projected():
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))
    disband = population_api.process_population_disbandments(state)
    assert disband["triumphs"], "producer 必须产出已举行的凯旋（FC-D03）"
    assert disband["triumphs"][0]["commander_name"] == commander.name

    outcome = _view(state, viewer)["population_outcome"]
    assert any(t["war_name"] == "对迦太基战争" for t in outcome["triumphs"]), "凯旋行（FC-D03）"
    assert outcome["legions"]["resolved_wars"]["total"] >= 1, "军团解散权威计数（FC-D05）"


def test_production_chain_idempotent_reentry():
    """re-entry/刷新：投影由权威 payload 重算，幂等一致（FC-D01/FC-D08）。"""
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1,))
    population_api.process_population_disbandments(state)
    first = _view(state, viewer)["population_outcome"]
    # 二次调用（幂等 marker）不应重复 mutation
    population_api.process_population_disbandments(state)
    second = _view(state, viewer)["population_outcome"]
    assert first == second, "re-entry 幂等（FC-D01）"


def test_triumph_veto_not_represented_in_population_outcome():
    """FC-D04：人口阶段不呈现否决；批准但指挥官死亡 → 不举行（FC-D03）。"""
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    war = _attach_resolved_war(state, commander.id, legion_numbers=())
    # 死亡 → producer 过滤 → 无「已举行」行
    state.mark_member_dead(commander.id, transfer_land=False, transfer_wealth=False)
    disband = population_api.process_population_disbandments(state)
    assert all(t["war_id"] != war.id for t in disband["triumphs"]), "死亡指挥官凯旋不举行（FC-D03）"
    outcome = _view(state, viewer)["population_outcome"]
    assert outcome["triumphs"] == []
