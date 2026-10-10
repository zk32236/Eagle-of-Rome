# src/tests/test_api/test_escg7q1_phase_invariance.py
"""ESC-WPJ-G7Q1-01 / ESC-S1 — T-ESC-03 相位不变 / 无业务差异（AC-03）。

冻结设计（`02-sa-design/`）：
- FC-ESC-03：相位不变 —— 处理仍在 Population 阶段内部；不改 `PHASE_SEQUENCE` /
  `mark_phase_executed` / `advance_population_phase` 门。
- FC-ESC-04 / FC-ESC-06：入口路径与结算侧 canonical → 同一解散 mutation 集（无业务差异）。

守护：入口处理（M1）不改变当前阶段、不 mark phase executed；入口触发路径与结算侧直调
canonical（镜像路径）产生逐字一致的解散 mutation 集。
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


def _attach_resolved_war(state, commander_id, legion_numbers=(), war_id="escg7q1-phase-war"):
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


def test_entry_processing_does_not_change_phase_state():
    """FC-ESC-03：入口处理不改变当前阶段、不 mark phase executed。"""
    state, viewer = _session()
    commander = next(m for m in state.get_living_members())
    _attach_resolved_war(state, commander.id, legion_numbers=(1, 2))

    phase_before = session_api._infer_current_phase_id(state)
    executed_before = state.is_phase_executed("population")
    assert phase_before == "population"
    assert executed_before is False

    session_api.get_population_view(state, viewer)  # 入口处理（M1）

    assert session_api._infer_current_phase_id(state) == "population", \
        "入口处理不改变当前阶段（FC-ESC-03）"
    assert state.is_phase_executed("population") is False, \
        "入口处理不 mark phase executed（FC-ESC-03）"


def test_entry_and_resolve_paths_same_disbandment_mutation_set():
    """FC-ESC-03/FC-ESC-06：入口路径与结算侧 canonical → 相同解散 mutation 集（无业务差异）。"""
    # A：入口触发（M1 路径）
    sA, vA = _session()
    cA = next(m for m in sA.get_living_members())
    _attach_resolved_war(sA, cA.id, legion_numbers=(1, 2))
    session_api.get_population_view(sA, vA)
    outA = sA.get_phase_result("population_disbandment")

    # B：结算侧直调 canonical（处理在「结算」——镜像路径）
    sB, vB = _session()
    cB = next(m for m in sB.get_living_members())
    _attach_resolved_war(sB, cB.id, legion_numbers=(1, 2))
    outB = population_api.process_population_disbandments(sB)

    assert isinstance(outA, dict) and isinstance(outB, dict)
    assert len(outA["triumphs"]) == len(outB["triumphs"]), "入口/结算凯旋集一致（无业务差异）"
    assert [t["war_id"] for t in outA["triumphs"]] == [t["war_id"] for t in outB["triumphs"]]
    assert outA["legions"]["resolved_wars"]["total"] == outB["legions"]["resolved_wars"]["total"]
    assert outA["legions"]["deescalated"]["total"] == outB["legions"]["deescalated"]["total"]
    assert outA["fleets"] == outB["fleets"], "入口/结算舰队解散集一致（无业务差异）"
