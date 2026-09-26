# src/tests/test_api/test_wpi_forum_capacity.py
"""
WP-I — Forum Recruitment Capacity Integrity（Attempt-1：S1 + S2）

覆盖（Task Package v1.4 §16.1 / SA-Baseline-acceptance-traceability §3）：
- T-I01 容量 resolver：3 / 4 / 6 / default
- T-I02 满派系拒绝首个 new distinct 目标（零 pending 写入 / 零成员变更）
- T-I03 5/6：接受一个，拒第二个 distinct
- T-I04 4/6：接受两个，拒第三个
- T-I05 pending 按派系隔离
- T-I06 同目标重复记录不占多槽（+ C3 补充：remaining==0 同目标重提仍接受）
- T-I07 Auto 路目标数 <= 权威剩余槽位（处理器 vacancy 源收敛 resolver）
- T-I08 CLI 收敛 canonical API 结果（无第二张容量表；R-I08）
- T-I09 Forum DTO 暴露权威槽位态（viewer_recruitment / viewer_pending_recruitment_target_ids）
- T-I11 legal 结算不超上限
- T-I12 malformed/legacy 溢出 pending fail-safe（cap-guard + 显式 INVARIANT_VIOLATION）
- T-I15 历史 6→7 失败类：真实生产链（recruit_figure + resolve_forum；禁 mock / 禁手设终态）
- T-I16 refresh/re-entry 保同一 remaining
- T-I17 下一 Forum 周期按真实成员重算
- T-I20 / N20 SaveLoad 往返（真实 to_dict/load_from_dict）：pending 招募随存档存活；
  读档后 remaining 由当前权威状态**重算**（非陈旧缓存）
- N1/N2/N3/N16/N18/N22/N23/N24 负向/边界

性质：恢复既有规则（vacancy-bounded recruitment）；不新增玩法规则。
"""
import logging
from unittest.mock import MagicMock

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.systems.war_system import WarSystem
from src.core.i18n import i18n
from src.api import forum_api
from src.ui.commands.phase_forum import ForumCommand
from src.ui.processors.auto_player_processor import AutoPlayerProcessor

i18n.load("zh-CN")


def _base_config():
    return {
        "testing": {"bypass_player_check": True},
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 1000,
            "default_bid_profit_rate": 0.2,
            "project_theoretical_construction": 3,
            "project_theoretical_warranty": 10,
        },
        "combat_rules": {"triumph_veteran_duration": 5},
    }


def _build_state(faction_members, curia_ids=(), dead_counts=None):
    """确定性 Forum 状态构建器（保留被测的权威生产变更路径）。

    faction_members: {faction_id: living_member_count}
    curia_ids     : 广场可招募目标 figure_id 列表（同时登记为全局成员）
    dead_counts   : {faction_id: dead_member_count}（加入派系但标记 is_dead；N16）
    返回 (state, first_player_id)
    """
    dead_counts = dead_counts or {}
    state = GameState.create_for_testing(_base_config())
    state.turn = GameTurn(turn_number=1, year=-282)

    next_id = 1
    order = []
    first_player = None
    for idx, fid in enumerate(faction_members):
        state.add_faction(Faction(id=fid, name=f"Faction-{fid}", treasury=1000))
        pid = f"p{idx + 1}"
        state.add_player(Player(player_id=pid, faction_id=fid, player_type=PlayerType.HUMAN))
        order.append(pid)
        if first_player is None:
            first_player = pid

        mids = []
        for _ in range(faction_members[fid]):
            fig = Figure.create_plebeian(next_id, fid, 30)
            fig.wealth = 100
            fig.update_influence()
            state.add_member(fig)
            mids.append(next_id)
            next_id += 1
        for _ in range(dead_counts.get(fid, 0)):
            fig = Figure.create_plebeian(next_id, fid, 30)
            fig.is_dead = True
            fig.wealth = 100
            state.add_member(fig)
            mids.append(next_id)
            next_id += 1
        state.get_faction(fid).member_ids = mids

    state.set_turn_order(order)
    state.set_current_player(first_player)

    for cid in curia_ids:
        fig = Figure.create_eques(cid, None, 35)
        fig.wealth = 100
        fig.update_influence()
        state.curia.add_figure(fig)
        state.add_member(fig)

    war_system = MagicMock(spec=WarSystem)
    war_system.get_resolved_wars.return_value = []
    war_system.get_active_wars.return_value = []
    war_system.get_war_by_id = MagicMock(return_value=None)
    state.get_war_system = MagicMock(return_value=war_system)

    state._forum_pending = {
        "retirements": [],
        "recruitment_bids": [],
        "contract_bids": [],
        "land_purchases": [],
        "triumph_votes": [],
        "land_trades": [],
        "market_opened": [],
        "forum_initialized": [],
    }
    return state, first_player


def _fid_of(state, player_id):
    return state.get_player(player_id).faction_id


# =====================================================================
# T-I01 / T-I18 — 容量 resolver（3→6 / 4→5 / 6→4 / other→5）
# =====================================================================
@pytest.mark.parametrize("n_factions,expected", [
    (3, 6), (4, 5), (6, 4), (2, 5), (5, 5), (7, 5),
])
def test_ti01_capacity_resolver_table(n_factions, expected):
    state, _ = _build_state({f"f{i + 1}": 0 for i in range(n_factions)})
    assert state.get_faction_count_for_capacity() == n_factions
    assert state.get_faction_capacity() == expected


def test_ti01_capacity_ignores_legacy_config():
    """R-I02：容量不再读 config `faction_member_limit`（固定 6 退役）。"""
    state, _ = _build_state({"f1": 0, "f2": 0, "f3": 0})
    state._config._config["economic_rules"]["faction_member_limit"] = 999
    assert state.get_faction_capacity() == 6  # 3 派系 → 6，config 无关


def test_ti01_capacity_authority_is_registered_count_not_active():
    """C1：口径 = 注册派系数（不是 get_active_factions() 存活过滤）。"""
    state, _ = _build_state({"f1": 5, "f2": 0, "f3": 0})
    assert len(state.factions) == 3
    assert state.get_faction_count_for_capacity() == 3
    assert state.get_faction_capacity() == 6


# =====================================================================
# T-I02 / N1 — 满派系拒绝首个 new distinct 目标
# =====================================================================
def test_ti02_full_faction_rejects_first_new_distinct_target():
    state, p1 = _build_state({"f1": 6, "f2": 0, "f3": 0}, curia_ids=[1001])
    assert state.get_remaining_recruitment_slots("f1") == 0  # N1：6/6

    before_members = list(state.get_faction("f1").member_ids)
    resp = forum_api.recruit_figure(state, p1, 1001, 50)

    assert resp["success"] is False
    assert "error_faction_full" in resp["message"] or "已满" in resp["message"]
    assert state.get_forum_pending()["recruitment_bids"] == []  # 零 pending 写入
    assert state.get_faction("f1").member_ids == before_members  # 零成员变更


# =====================================================================
# T-I03 / N2 — 5/6：接受一个，拒第二个 distinct
# =====================================================================
def test_ti03_five_of_six_accept_one_reject_second():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    assert state.get_remaining_recruitment_slots("f1") == 1  # N2：一个空位

    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    assert state.get_remaining_recruitment_slots("f1") == 0

    second = forum_api.recruit_figure(state, p1, 1002, 50)
    assert second["success"] is False
    assert state.get_forum_pending()["recruitment_bids"] == [("f1", 1001, 50)]


# =====================================================================
# T-I04 / N3 — 4/6：接受两个，拒第三个
# =====================================================================
def test_ti04_four_of_six_accept_two_reject_third():
    state, p1 = _build_state({"f1": 4, "f2": 0, "f3": 0}, curia_ids=[1001, 1002, 1003])
    assert state.get_remaining_recruitment_slots("f1") == 2  # N3：两个空位

    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    assert forum_api.recruit_figure(state, p1, 1002, 50)["success"] is True
    third = forum_api.recruit_figure(state, p1, 1003, 50)

    assert third["success"] is False
    assert state.get_remaining_recruitment_slots("f1") == 0
    assert state.get_forum_pending()["recruitment_bids"] == [
        ("f1", 1001, 50), ("f1", 1002, 50)
    ]


# =====================================================================
# T-I05 — pending 按派系隔离
# =====================================================================
def test_ti05_pending_isolation_between_factions():
    state, p1 = _build_state({"f1": 5, "f2": 5, "f3": 0}, curia_ids=[1001, 1002])
    p2 = "p2"
    assert _fid_of(state, p2) == "f2"

    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    assert state.get_remaining_recruitment_slots("f1") == 0
    # f2 的槽位不被 f1 的 pending 消耗
    assert state.get_remaining_recruitment_slots("f2") == 1
    assert state.get_pending_recruitment_target_ids("f2") == []

    assert forum_api.recruit_figure(state, p2, 1002, 50)["success"] is True
    assert state.get_pending_recruitment_target_ids("f1") == [1001]
    assert state.get_pending_recruitment_target_ids("f2") == [1002]


# =====================================================================
# T-I06 / N9 — 同目标重复记录不占多槽；C3 补充：remaining==0 同目标重提仍接受
# =====================================================================
def test_ti06_duplicate_same_target_consumes_one_slot():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])

    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    # 同目标重提（已 distinct 内）→ 不占新槽、不拒
    assert forum_api.recruit_figure(state, p1, 1001, 70)["success"] is True

    pending = state.get_forum_pending()["recruitment_bids"]
    assert pending == [("f1", 1001, 50), ("f1", 1001, 70)]  # 记录仍在（schema 不变）
    assert state.get_pending_recruitment_target_count("f1") == 1  # distinct = 1
    assert state.get_remaining_recruitment_slots("f1") == 0
    # 但 new distinct 目标仍被拒
    assert forum_api.recruit_figure(state, p1, 1002, 50)["success"] is False


# =====================================================================
# T-I09 — Forum DTO 权威槽位读模型
# =====================================================================
def test_ti09_forum_dto_exposes_authoritative_slots():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    view = forum_api.get_forum_view(state, p1)
    assert view["success"] is True
    r = view["data"]["viewer_recruitment"]

    assert r == {
        "capacity": 6,
        "current_member_count": 5,
        "physical_vacancies": 1,
        "pending_recruitment_target_count": 0,
        "remaining_recruitment_slots": 1,
        "can_submit_recruitment_bid": True,
    }
    assert view["data"]["viewer_pending_recruitment_target_ids"] == []
    # 既有 pending_actions 记录条数保持不动
    assert view["data"]["pending_actions"]["recruitment_bids"] == 0

    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    view2 = forum_api.get_forum_view(state, p1)
    r2 = view2["data"]["viewer_recruitment"]
    assert r2["pending_recruitment_target_count"] == 1
    assert r2["remaining_recruitment_slots"] == 0
    assert r2["can_submit_recruitment_bid"] is False
    assert view2["data"]["viewer_pending_recruitment_target_ids"] == [1001]


# =====================================================================
# T-I16 — refresh / re-entry 权威一致（无陈旧缓存）
# =====================================================================
def test_ti16_refresh_reentry_is_authoritative():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True

    r1 = forum_api.get_forum_view(state, p1)["data"]["viewer_recruitment"]
    r2 = forum_api.get_forum_view(state, p1)["data"]["viewer_recruitment"]
    assert r1 == r2
    assert r1["remaining_recruitment_slots"] == 0


# =====================================================================
# T-I11 — legal 结算不超上限
# =====================================================================
def test_ti11_legal_settlement_never_exceeds_capacity():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True

    result = forum_api.resolve_forum(state)
    assert result["success"] is True

    faction = state.get_faction("f1")
    assert faction.get_living_member_count(state) == 6
    assert faction.get_living_member_count(state) <= state.get_faction_capacity()
    assert 1001 in faction.member_ids


# =====================================================================
# T-I12 / N18 — malformed/legacy 溢出 pending → cap-guard fail-safe
# =====================================================================
def test_ti12_malformed_overflow_pending_fails_safe():
    state, p1 = _build_state({"f1": 6, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    # 手造"遗留溢出"pending（绕过提交侧）——两个 otherwise-legit winner 争 0 槽
    state._forum_pending["recruitment_bids"] = [("f1", 1001, 50), ("f1", 1002, 60)]

    result = forum_api.resolve_forum(state)
    assert result["success"] is True

    faction = state.get_faction("f1")
    # 不变量：超上限被禁（终态不超 cap），且无部分变更
    assert faction.get_living_member_count(state) == 6
    assert 1001 not in faction.member_ids
    assert 1002 not in faction.member_ids
    # 显式诊断证据（结构化 + 结果行），无静默
    assert "容量守卫" in result["message"]
    log_text = "\n".join(state._event_log)
    assert "INVARIANT_VIOLATION" in log_text
    # 两人物仍在广场（未 remove_figure）
    available_ids = {f.id for f in state.curia.get_all_available()}
    assert {1001, 1002}.issubset(available_ids)


# =====================================================================
# T-I15 — 历史 6→7 失败类（真实生产链）
# =====================================================================
def test_ti15_historical_6_to_7_class_closed_via_production_chain():
    """3 派系容量 6；f1 = 5/6（合法退役 1 人后 1 空位）。
    生产链：recruit_figure 目标 A（占用最后槽）→ 目标 B 提交前即被拒
    → resolve_forum 结算 → 终态 living ≤ 6（不再 6→7）。"""
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    assert state.get_faction_capacity() == 6

    # 目标 A：占用最后槽
    a = forum_api.recruit_figure(state, p1, 1001, 50)
    assert a["success"] is True
    assert state.get_remaining_recruitment_slots("f1") == 0

    # 目标 B：new distinct → 提交前即被拒（零新增 pending）
    b = forum_api.recruit_figure(state, p1, 1002, 60)
    assert b["success"] is False
    assert state.get_forum_pending()["recruitment_bids"] == [("f1", 1001, 50)]

    # 结算：终态 ≤ capacity（历史缺陷为 6→7）
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"] is True
    faction = state.get_faction("f1")
    assert faction.get_living_member_count(state) <= 6
    assert 1001 in faction.member_ids
    assert 1002 not in faction.member_ids


# =====================================================================
# T-I17 — 下一 Forum 周期按真实成员重算（无陈旧预留）
# =====================================================================
def test_ti17_next_cycle_recomputes_from_actual_membership():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    assert state.get_remaining_recruitment_slots("f1") == 0

    # Forum 周期滚转：pending 清空 → 槽位由真实成员重算（成员仍 5 → 回到 1）
    state.clear_forum_pending()
    assert state.get_remaining_recruitment_slots("f1") == 1


# =====================================================================
# N16 — 死亡成员不计入 living / 不占容量
# =====================================================================
def test_n16_dead_members_not_counted_for_capacity():
    state, p1 = _build_state({"f1": 4, "f2": 0, "f3": 0}, dead_counts={"f1": 2})
    faction = state.get_faction("f1")
    assert len(faction.member_ids) == 6      # 4 living + 2 dead
    assert faction.get_living_member_count(state) == 4
    assert state.get_faction_physical_vacancies("f1") == 2  # 6 - 4


# =====================================================================
# N22 / N23 / N24 — 负向：未授权 / 非法金额 / 目标不可用
# =====================================================================
def test_n22_unauthorized_player_rejected():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    state._config._config["testing"]["bypass_player_check"] = False
    state.set_current_player("p1")
    resp = forum_api.recruit_figure(state, "p_none", 1001, 50)
    assert resp["success"] is False


def test_n23_invalid_amount_rejected():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    for amount in (0, -5):
        resp = forum_api.recruit_figure(state, p1, 1001, amount)
        assert resp["success"] is False
        assert i18n.get("error_invalid_amount") in resp["message"]


def test_n24_target_not_available_rejected():
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001])
    resp = forum_api.recruit_figure(state, p1, 9999, 50)
    assert resp["success"] is False
    assert i18n.get("error_figure_not_in_curia") in resp["message"]


# =====================================================================
# T-I07 — Auto 路目标数 <= 权威剩余槽位（处理器 vacancy 源收敛 resolver）
# =====================================================================
class _RecordingRecruitmentDecider:
    """轻量记录型 decider：捕获处理器传入的 `vacancies`（选择策略本身不在本测试范围）。

    返回前 `vacancies` 个可用目标各 1 注——模拟既有 AutoRecruitmentDecider 的
    vacancy-bounded 选择，使下游 `recruit_figure` 真实生产路径可被验证。
    """

    def __init__(self):
        self.calls = []

    def decide_bids(self, faction, available_figures, vacancies, state):
        self.calls.append({"faction_id": faction.id, "vacancies": vacancies})
        return {fig.id: 10 for fig in available_figures[:max(0, vacancies)]}


def _make_processor(state, recruitment_decider):
    return AutoPlayerProcessor(
        state,
        retirement_decider=MagicMock(),
        recruitment_decider=recruitment_decider,
        bid_decider=MagicMock(),
        triumph_decider=MagicMock(),
    )


def test_ti07_auto_target_count_bounded_by_authoritative_remaining_slots():
    """4 派系 → 容量 5（≠ 旧固定 6）；f1 = 4/5 → 权威剩余 1。

    处理器必须把 resolver 的剩余槽位（1）传入 decider；不得回退固定 6（R-I02）。
    """
    state, p1 = _build_state(
        {"f1": 4, "f2": 0, "f3": 0, "f4": 0}, curia_ids=[1001, 1002, 1003]
    )
    assert state.get_faction_capacity() == 5           # 4 派系 → 5
    remaining_before = state.get_remaining_recruitment_slots("f1")
    assert remaining_before == 1

    recorder = _RecordingRecruitmentDecider()
    processor = _make_processor(state, recorder)
    processor.process_market(p1, state.get_faction("f1"))

    assert recorder.calls, "decider 未被调用"
    assert recorder.calls[-1]["vacancies"] == remaining_before   # 权威剩余槽位传入
    assert state.get_pending_recruitment_target_count("f1") <= remaining_before


def test_ti07_auto_no_over_recruit_when_slots_exhausted():
    """4 派系 → 容量 5；f1 = 5/5 → 权威剩余 0 ⇒ Auto 不产生新目标。"""
    state, p1 = _build_state(
        {"f1": 5, "f2": 0, "f3": 0, "f4": 0}, curia_ids=[1001, 1002, 1003]
    )
    assert state.get_remaining_recruitment_slots("f1") == 0

    recorder = _RecordingRecruitmentDecider()
    processor = _make_processor(state, recorder)
    processor.process_market(p1, state.get_faction("f1"))

    assert recorder.calls[-1]["vacancies"] == 0
    assert state.get_pending_recruitment_target_count("f1") == 0


# =====================================================================
# T-I08 — CLI 收敛 canonical API 结果（无第二张容量表；R-I08）
# =====================================================================
def _make_forum_cmd(state, player_id):
    cmd = ForumCommand(
        state,
        retirement_decider=MagicMock(),
        recruitment_decider=MagicMock(),
        bid_decider=MagicMock(),
        land_trade_decider=MagicMock(),
        triumph_decider=MagicMock(),
    )
    cmd._players = [player_id]
    cmd._current_player_index = 0
    return cmd


def test_ti08_cli_converges_to_canonical_api_result(capsys):
    state_cli, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    state_api, _ = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    cmd = _make_forum_cmd(state_cli, p1)

    # (1) 占用最后一槽：CLI 与 API 同为接受
    assert cmd._handle_recruit(["1001", "50"]) is True
    capsys.readouterr()
    assert forum_api.recruit_figure(state_api, p1, 1001, 50)["success"] is True

    # (2) remaining==0 下同目标重提：CLI 与 API 同为接受（同目标语义不变，§C3）
    assert cmd._handle_recruit(["1001", "70"]) is True
    capsys.readouterr()
    assert forum_api.recruit_figure(state_api, p1, 1001, 70)["success"] is True

    # (3) new distinct 目标：CLI 与 API 同为拒绝，且 CLI 给出精确槽位耗尽文案
    assert cmd._handle_recruit(["1002", "50"]) is False
    out_reject = capsys.readouterr().out
    assert i18n.get("error_recruitment_slots_exhausted") in out_reject
    assert forum_api.recruit_figure(state_api, p1, 1002, 50)["success"] is False

    # CLI 与 canonical API 结果/终态一致
    assert (state_cli.get_forum_pending()["recruitment_bids"]
            == state_api.get_forum_pending()["recruitment_bids"])


def test_ti08_cli_true_full_uses_faction_full_message(capsys):
    """真满员（physical_vacancies == 0）仍用 error_faction_full。"""
    state, p1 = _build_state({"f1": 6, "f2": 0, "f3": 0}, curia_ids=[1001])
    cmd = _make_forum_cmd(state, p1)
    assert cmd._handle_recruit(["1001", "50"]) is False
    out = capsys.readouterr().out
    assert i18n.get("error_faction_full") in out


def test_ti08_cli_has_no_inline_capacity_table():
    """R-I08：CLI 内联容量表彻底删除（不得留第二张表）。"""
    import pathlib

    phase_forum_src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "ui" / "commands" / "phase_forum.py"
    )
    text = phase_forum_src.read_text(encoding="utf-8")
    assert "max_members" not in text
    assert "num_factions == 3" not in text
    assert "num_factions == 4" not in text
    assert "num_factions == 6" not in text


# =====================================================================
# T-I20 / N20 — SaveLoad pending-slot continuity（真实 to_dict/load_from_dict 往返）
# =====================================================================
def _save_load_roundtrip(state):
    """真实存档往返：state.to_dict() → 新建 GameState.load_from_dict(...)。

    不 mock、不手设终态、不注入假后置：往返后一切经权威 resolver 由活状态派生。
    """
    data = state.to_dict()
    restored = GameState.create_for_testing(_base_config())
    restored.load_from_dict(data)
    return data, restored


def test_ti20_saveload_pending_slot_continuity():
    # 3 派系 → 容量 6；f1 = 5/6（合法退役 1 人后）⇒ 物理空位 1
    state, p1 = _build_state({"f1": 5, "f2": 0, "f3": 0}, curia_ids=[1001, 1002])
    assert state.get_faction_capacity() == 6
    assert state.get_remaining_recruitment_slots("f1") == 1

    # --- ① 提交目标 A → remaining==0 → 存档 → 读档 ---
    assert forum_api.recruit_figure(state, p1, 1001, 50)["success"] is True
    assert state.get_remaining_recruitment_slots("f1") == 0

    data0, restored0 = _save_load_roundtrip(state)

    # 存档不含任何「槽位/容量缓存」——pending 载体只有 _forum_pending（重算来源）
    assert "_forum_pending" in data0
    assert "remaining_recruitment_slots" not in data0
    assert "physical_vacancies" not in data0
    assert "viewer_recruitment" not in data0

    # 读档后 pending 招募目标随存档存活
    assert restored0.get_faction_capacity() == 6
    assert restored0.get_pending_recruitment_target_ids("f1") == [1001]
    assert restored0.get_remaining_recruitment_slots("f1") == 0     # 仍 == 0（重算）
    assert restored0.get_forum_pending()["recruitment_bids"] == [("f1", 1001, 50)]

    # new distinct B 读档后仍被真实生产 API 拒绝（零新增 pending）
    b = forum_api.recruit_figure(restored0, p1, 1002, 60)
    assert b["success"] is False
    assert "error_faction_full" in b["message"] or "已满" in b["message"]
    assert restored0.get_forum_pending()["recruitment_bids"] == [("f1", 1001, 50)]

    # 读模型 parity（读档态）
    view0 = forum_api.get_forum_view(restored0, p1)["data"]["viewer_recruitment"]
    assert view0["remaining_recruitment_slots"] == 0
    assert view0["can_submit_recruitment_bid"] is False

    # --- ② 合法淘汰 1 人（真实生产路径 retire_figure）→ 存档 → 读档 ---
    victim = state.get_faction("f1").get_members(state)[0].id
    before_living = state.get_faction("f1").get_living_member_count(state)
    retired = forum_api.retire_figure(state, p1, victim)
    assert retired["success"] is True
    assert state.get_faction("f1").get_living_member_count(state) == before_living - 1
    # 即时重算：物理空位 2 − pending distinct 1 ⇒ 1
    assert state.get_remaining_recruitment_slots("f1") == 1

    data1, restored1 = _save_load_roundtrip(state)

    # 读档后 remaining == 1（重算，非陈旧缓存 0）
    assert restored1.get_pending_recruitment_target_ids("f1") == [1001]
    assert restored1.get_faction_physical_vacancies("f1") == 2
    assert restored1.get_remaining_recruitment_slots("f1") == 1

    view1 = forum_api.get_forum_view(restored1, p1)["data"]["viewer_recruitment"]
    assert view1["remaining_recruitment_slots"] == 1
    assert view1["can_submit_recruitment_bid"] is True

    # 同一 pending、不同成员 → 不同 remaining：证明槽位是 derived（非持久化缓存）
    assert (data0["_forum_pending"]["recruitment_bids"]
            == data1["_forum_pending"]["recruitment_bids"] == [("f1", 1001, 50)])
    assert restored0.get_remaining_recruitment_slots("f1") == 0
    assert restored1.get_remaining_recruitment_slots("f1") == 1

    # 读档后 new distinct B 重新可用（真生产链接受，且占满最后一槽）
    b2 = forum_api.recruit_figure(restored1, p1, 1002, 60)
    assert b2["success"] is True
    assert restored1.get_remaining_recruitment_slots("f1") == 0
