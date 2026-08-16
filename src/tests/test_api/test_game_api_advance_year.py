# src/tests/test_api/test_game_api_advance_year.py
"""
WP-06 DEV-05 决算年度推进 — use-case 层（game_api.advance_year）回归测试。

覆盖 acceptance-traceability.md §2 的 test identity + PM-Pro P1-01/P1-02 专项：
- test_advance_year_requires_resolution（FC-02 resolution 前置）
- test_advance_year_idempotent_backend（FC-03 后端幂等）
- test_advance_year_reentry_guard（FC-04 重入 guard）
- test_advance_year_no_partial_on_settlement_failure（FC-05 无部分推进）
- test_advance_year_decay_rollback（FC-06 非幂等项快照回滚）
- test_advance_year_retry_single_increment（FC-06 失败重试仅一次推进）
- test_advance_year_double_click_rejected（FC-03/FC-04 双击拒绝）
- test_advance_year_non_current_player_rejected（FC-02 多玩家门禁）
- test_active_war_commander_persists_across_advance（FC-08/FC-09 指挥官跨年保留）
- P1-01: A5/A6/A7 幂等专项（contract/governor/truce）
- P1-02: 回滚覆盖派生影响力（faction 聚合派生状态）
"""
import copy

import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure
from src.api import game_api


def _make_state(year=-260, bypass=True, current_player="p1", turn_number=5):
    """创建一个最小可用 GameState，可选权限 bypass 或显式当前玩家。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=year)
    if bypass:
        state.config._config["testing"] = {"bypass_player_check": True}
    else:
        state._current_player_id = current_player
    return state


# ---------------------------------------------------------------------------
# FC-02 resolution 前置 / 权限门禁
# ---------------------------------------------------------------------------

def test_advance_year_requires_resolution():
    """resolution 未执行且非 force → 结构化失败 resolution_not_executed，零推进。"""
    state = _make_state()
    result = game_api.advance_year(state, "p1")
    assert result["success"] is False
    assert "resolution_not_executed" in result.get("errors", [])
    assert state.turn.year == -260  # 年份未推进
    assert not state.is_phase_executed("resolution")


def test_advance_year_non_current_player_rejected():
    """非当前玩家 advance → error_not_your_turn，零写入。"""
    state = _make_state(bypass=False, current_player="p1")
    state.mark_phase_executed("resolution")
    result = game_api.advance_year(state, "p2")
    assert result["success"] is False
    assert "当前不是您的回合" in result["message"]
    assert state.turn.year == -260


def test_advance_year_force_skips_resolution_precheck():
    """force=True 跳过 resolution 前置（调试逃生门），但不跳过原子 commit。"""
    state = _make_state()
    # resolution 未执行，但 force 跳过前置
    result = game_api.advance_year(state, "p1", force=True)
    assert result["success"] is True
    assert state.turn.year == -259  # 仍推进 +1
    assert not state.is_phase_executed("resolution")


# ---------------------------------------------------------------------------
# FC-03 幂等 / FC-04 重入 / 双击
# ---------------------------------------------------------------------------

def test_advance_year_idempotent_backend():
    """第一次成功，第二次 → resolution_not_executed（token 消费），年份不再增加。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    year_before = state.turn.year

    result1 = game_api.advance_year(state, "p1")
    assert result1["success"] is True
    assert state.turn.year == year_before + 1
    assert not state.is_phase_executed("resolution")  # token 已消费

    result2 = game_api.advance_year(state, "p1")
    assert result2["success"] is False
    assert "resolution_not_executed" in result2.get("errors", [])
    assert state.turn.year == year_before + 1  # 不再推进


def test_advance_year_double_click_rejected():
    """连续两次 advance → 仅推进一次，第二次被拒绝。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    year_before = state.turn.year

    game_api.advance_year(state, "p1")
    second = game_api.advance_year(state, "p1")
    assert second["success"] is False
    assert "resolution_not_executed" in second.get("errors", [])
    assert state.turn.year == year_before + 1


def test_advance_year_reentry_guard():
    """_year_advance_in_progress=True 时二次调用 → advance_in_progress（fail-closed）。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    state._year_advance_in_progress = True
    result = game_api.advance_year(state, "p1")
    assert result["success"] is False
    assert "advance_in_progress" in result.get("errors", [])
    assert state.turn.year == -260


def test_advance_year_guard_reset_after_success():
    """成功后 _year_advance_in_progress 复位为 False。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    game_api.advance_year(state, "p1")
    assert state._year_advance_in_progress is False


# ---------------------------------------------------------------------------
# FC-05/FC-06 失败无部分推进 / 快照回滚 / 重试
# ---------------------------------------------------------------------------

def test_advance_year_no_partial_on_settlement_failure(monkeypatch):
    """结算异常 → 年份未推进、resolution token 保留、guard 复位。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    year_before = state.turn.year

    def boom():
        raise RuntimeError("settlement failure")

    monkeypatch.setattr(state, "process_contract_expiration", boom)
    result = game_api.advance_year(state, "p1")

    assert result["success"] is False
    assert "advance_failed" in result.get("errors", [])
    assert state.turn.year == year_before  # 年份未推进
    assert state.is_phase_executed("resolution")  # token 保留
    assert state._year_advance_in_progress is False  # guard 复位


def test_advance_year_decay_rollback(monkeypatch):
    """衰减后结算异常 → member 年龄/影响力/临时影响力/声望/老兵值回滚。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    fig = Figure(id=1, name="Marcus", age=40, veterans=100, popularity=80)
    state.add_member(fig)
    age_before = fig.age
    veterans_before = fig.veterans
    popularity_before = fig.popularity

    def boom():
        raise RuntimeError("boom after decay")

    monkeypatch.setattr(state, "process_contract_expiration", boom)
    result = game_api.advance_year(state, "p1")

    assert result["success"] is False
    assert fig.age == age_before
    assert fig.veterans == veterans_before
    assert fig.popularity == popularity_before
    assert state.turn.year == -260


def test_advance_year_retry_single_increment(monkeypatch):
    """失败（结算异常）→ 修复后重试 → 成功且仅 +1 年。"""
    state = _make_state()
    state.mark_phase_executed("resolution")

    def boom():
        raise RuntimeError("transient failure")

    monkeypatch.setattr(state, "process_truce_expiry", boom)
    result1 = game_api.advance_year(state, "p1")
    assert result1["success"] is False
    assert state.turn.year == -260
    assert state.is_phase_executed("resolution")

    monkeypatch.undo()  # 修复
    result2 = game_api.advance_year(state, "p1")
    assert result2["success"] is True
    assert state.turn.year == -259  # 仅 +1
    assert not state.is_phase_executed("resolution")


# ---------------------------------------------------------------------------
# FC-08/FC-09 active war 指挥官跨年保留
# ---------------------------------------------------------------------------

def test_active_war_commander_persists_across_advance():
    """active war 的 commander_id 跨年保留，指挥官仍存活。"""
    from src.core.entities.war import War, WarStatus
    from src.core.systems.war_system import WarSystem

    state = _make_state()
    state.mark_phase_executed("resolution")
    commander = Figure(id=10, name="Commander", age=35)
    state.add_member(commander)

    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Active War", start_year=-265, threat_level=2, strength=10)
    war.status = WarStatus.ACTIVE
    war.assign_commander(10, legions=2)
    ws._active_wars.append(war)

    result = game_api.advance_year(state, "p1")
    assert result["success"] is True
    # 指挥官关系跨年保留（FC-08/FC-09，by omission 无丢失）
    assert war.commander_id == 10
    assert commander.is_dead is False
    assert 10 in [m.id for m in state.get_living_members()]


# ---------------------------------------------------------------------------
# P1-01: A5/A6/A7 结算步骤幂等专项（二次执行/重试不重复结算）
# ---------------------------------------------------------------------------

def test_contract_expiration_idempotent():
    """A5 合同过期：连续两次调用第二次无副作用。"""
    from src.core.entities.contract import ContractType, ContractStatus

    state = _make_state()  # turn_number=5
    contract = state.create_contract(ContractType.TAX_FARMING, 1, 90, 2)
    assert contract.status == ContractStatus.PENDING

    expired1 = state.process_contract_expiration()
    assert contract.status == ContractStatus.EXPIRED
    assert expired1 >= 1

    expired2 = state.process_contract_expiration()
    assert expired2 == 0  # 不再重复过期
    assert contract.status == ContractStatus.EXPIRED


def test_governor_transition_idempotent():
    """A6 总督交接：连续两次调用第二次无副作用。"""
    from src.core.entities.province import Province

    state = _make_state()
    old_gov = Figure(id=101, name="Old", is_absent=True, office="proconsul")
    designate = Figure(id=102, name="New", office=None)
    state._members[101] = old_gov
    state._members[102] = designate
    province = Province(
        province_id=1, name="P", total_land=500,
        governor_id=101, governor_designate_id=102, old_governor_id=101,
        governor_type="proconsul",
    )
    state.add_province(province)

    state.process_governor_transitions()
    assert designate.office == "proconsul"
    assert old_gov.office is None
    assert old_gov.is_absent is False

    # 第二次调用：无副作用（designate 已清空）
    state.process_governor_transitions()
    assert designate.office == "proconsul"
    assert old_gov.office is None
    assert old_gov.is_absent is False


def test_truce_expiry_idempotent():
    """A7 和约到期：连续两次调用第二次无副作用。"""
    from src.core.entities.war import War, WarStatus
    from src.core.systems.war_system import WarSystem

    state = _make_state()  # turn_number=5
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Truce War", start_year=-270, threat_level=0, strength=5)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved"})
    war.set_truce_end_turn(4)  # 4 <= 5 → 已到期
    ws._truce_wars.append(war)

    expired1 = state.process_truce_expiry()
    assert war in ws._threats
    assert war not in ws._truce_wars
    assert expired1

    expired2 = state.process_truce_expiry()
    assert expired2 == []  # 不再重复到期
    assert war in ws._threats


# ---------------------------------------------------------------------------
# P1-02: 回滚覆盖 A4 update_influence 的派生/聚合影响力（faction 派生状态）
# ---------------------------------------------------------------------------

def test_advance_year_rollback_restores_faction_derived_influence(monkeypatch):
    """A4 update_influence 不回写 faction 聚合字段（派生求和），但回滚须恢复 member
    影响力，从而 faction 派生影响力（get_total_influence）也恢复。"""
    state = _make_state()
    state.mark_phase_executed("resolution")
    faction = Faction(id="f1", name="F1")
    state.add_faction(faction)
    fig = Figure(id=1, name="Marcus", faction_id="f1", age=40, veterans=100, popularity=80)
    fig.add_temp_influence_task(per_turn=10, duration=5)
    state.add_member(fig)
    faction.member_ids.append(1)
    fig.update_influence()

    age_before = fig.age
    veterans_before = fig.veterans
    popularity_before = fig.popularity
    influence_before = fig.influence
    temp_tasks_before = copy.deepcopy(fig._temp_influence_tasks)
    faction_influence_before = faction.get_total_influence(state)

    def boom():
        raise RuntimeError("boom after temp influence decay")

    monkeypatch.setattr(state, "process_contract_expiration", boom)
    result = game_api.advance_year(state, "p1")

    assert result["success"] is False
    assert fig.age == age_before
    assert fig.veterans == veterans_before
    assert fig.popularity == popularity_before
    assert fig.influence == influence_before
    assert fig._temp_influence_tasks == temp_tasks_before
    # faction 派生影响力（on-demand 求和）随 member 影响力回滚而恢复
    assert faction.get_total_influence(state) == faction_influence_before
    assert state.turn.year == -260


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
