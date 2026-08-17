"""
API层单元测试 - session_api DTO 函数
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import session_api


def _make_minimal_state():
    """创建一个最小化游戏状态，包含 resolution 所需的最小实体集。"""
    config = {
        "testing": {"bypass_player_check": True, "auto_forum": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "faction_initial_treasury": 100,
            "faction_member_limit": 6,
        },
        "political_rules": {
            "min_ages": {"consul": 40},
            "office_rank": {"consul": 5},
            "office_influence_bonus": {"consul": 40},
        },
    }
    # 使用工厂方法避免文件依赖
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    state.treasury = 200

    # 派系
    faction_opt = Faction(id="Optimates", name="贵族派")
    faction_pop = Faction(id="Populares", name="平民派")
    state._factions["Optimates"] = faction_opt
    state._factions["Populares"] = faction_pop

    # 玩家
    player = Player(
        player_id="player_1",
        faction_id="Optimates",
        player_type=PlayerType.HUMAN,
    )
    state._players["player_1"] = player
    state._current_player_id = "player_1"
    state._turn_order = ["player_1"]

    # 人物（存到 _members 供 get_member / get_living_members 使用）
    fig1 = Figure(
        id=1,
        name="Marcus Tullius",
        faction_id="Optimates",
        age=45, wealth=50, popularity=60,
        class_tier=ClassTier.NOBILE,
        is_faction_leader=True,
    )
    fig1._influence = 80
    fig2 = Figure(
        id=2,
        name="Gaius Julius",
        faction_id="Populares",
        age=40, wealth=30, popularity=70,
        class_tier=ClassTier.NOBILE,
        is_faction_leader=True,
    )
    fig2._influence = 60
    fig3 = Figure(
        id=3,
        name="Lucius Cornelius",
        faction_id="Optimates",
        age=50, wealth=20, popularity=40,
        class_tier=ClassTier.PLEBEIAN,
    )
    fig3._influence = 30
    for fig in (fig1, fig2, fig3):
        state.add_member(fig)

    faction_opt.member_ids = [1, 3]
    faction_pop.member_ids = [2]

    # 空的行省字典（测试 DTO 不依赖行省数据）
    state._provinces = {}

    return state, "player_1"


# ===========================================================================
# T-01: Resolution View DTO 正常（结算完成，有数据）
# ===========================================================================

class TestResolutionViewSuccess:
    """T-01: 结算完成后 DTO 包含所有业务字段。"""

    def test_returns_success_with_correct_structure(self):
        state, viewer_id = _make_minimal_state()
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)

        assert result["success"] is True
        data = result["data"]

        # 顶层结构
        assert "resolved" in data
        assert "step_statuses" in data
        assert "results" in data
        assert "warnings" in data
        assert "summary" in data
        assert "is_current_player" in data

        # resolved = True
        assert data["resolved"] is True

        # step_statuses: 五步，全部 completed
        assert len(data["step_statuses"]) == 5
        assert all(s["status"] == "completed" for s in data["step_statuses"])

        # results
        results = data["results"]
        assert "governor_transitions" in results
        assert "contracts_expired" in results
        assert "truce_expired" in results
        assert "dominant_faction" in results
        assert "treasury" in results
        assert "legion_status" in results

        # warnings
        assert isinstance(data["warnings"], list)

        # summary
        summary = data["summary"]
        assert "dominant_faction" in summary
        assert "treasury" in summary
        assert "next_year" in summary
        assert "decay_applied" in summary
        assert "current_year" in summary
        assert data["is_current_player"] is True

    def test_step_statuses_have_correct_labels(self):
        state, viewer_id = _make_minimal_state()
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)
        steps = result["data"]["step_statuses"]

        expected_names = [
            "governor_return", "contract_expiry", "risk_check",
            "annual_decay", "next_year",
        ]
        expected_displays = [
            "总督返回", "合同到期", "风险检查", "年度衰减", "决算完成",
        ]
        for i, step in enumerate(steps):
            assert step["step"] == i + 1
            assert step["name"] == expected_names[i]
            assert step["display"] == expected_displays[i]
            assert step["status"] == "completed"

    def test_resolution_step5_display_name(self):
        """步骤 5 display =「决算完成」（语义修正：不与「推进下一年度」混滑）"""
        state, viewer_id = _make_minimal_state()
        result = session_api.get_resolution_view(state, viewer_id)
        steps = result["data"]["step_statuses"]
        step5 = next(s for s in steps if s["step"] == 5)
        assert step5["name"] == "next_year"
        assert step5["display"] == "决算完成"


# ===========================================================================
# T-02: Resolution View DTO 空状态（结算未完成）
# ===========================================================================

class TestResolutionViewEmpty:
    """T-02: 结算未完成时返回空列表/空字典，不抛异常。"""

    def test_returns_success_when_not_resolved(self):
        state, viewer_id = _make_minimal_state()
        # 不执行 resolution

        result = session_api.get_resolution_view(state, viewer_id)

        assert result["success"] is True
        data = result["data"]

        assert data["resolved"] is False
        assert all(s["status"] == "pending" for s in data["step_statuses"])
        assert data["results"]["governor_transitions"] == []
        assert data["results"]["contracts_expired"] == 0
        assert data["warnings"] == []
        assert data["summary"]["dominant_faction"] is None

    def test_handles_missing_player_gracefully(self):
        state, _ = _make_minimal_state()

        result = session_api.get_resolution_view(state, "nonexistent_player")

        assert result["success"] is False

    def test_reports_is_current_player_correctly(self):
        state, viewer_id = _make_minimal_state()
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)
        assert result["data"]["is_current_player"] is True

        # 非当前玩家
        other_player = Player(
            player_id="player_2", faction_id="Populares",
            player_type=PlayerType.HUMAN,
        )
        state._players["player_2"] = other_player
        result2 = session_api.get_resolution_view(state, "player_2")
        assert result2["data"]["is_current_player"] is False


# ===========================================================================
# T-03: Resolution View DTO 多警告
# ===========================================================================

class TestResolutionViewWarnings:
    """T-03: warnings 列表包含多条记录。"""

    def test_warnings_includes_treasury_deficit(self):
        state, viewer_id = _make_minimal_state()
        state.treasury = -100  # 赤字
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)

        assert result["success"] is True
        warnings = result["data"]["warnings"]
        deficit_warnings = [w for w in warnings if "赤字" in w["message"]]
        assert len(deficit_warnings) >= 1

    def test_warnings_includes_dominant_faction_risk(self):
        state, viewer_id = _make_minimal_state()
        # 让 Optimates 影响力远大于 Populares，触发独裁风险
        fig1 = state.get_member(1)
        fig1.influence = 300
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)

        warnings = result["data"]["warnings"]
        opt_warnings = [
            w for w in warnings
            if "贵族派" in w["message"] or "Optimates" in w["message"]
        ]
        assert len(opt_warnings) >= 1


# ===========================================================================
# T-04: Resolution View DTO 只读（非当前玩家）
# ===========================================================================

class TestResolutionViewReadonly:
    """T-04: 非当前玩家可查看数据，无权限字段正确标记。"""

    def test_non_current_player_can_view_resolution_data(self):
        state, viewer_id = _make_minimal_state()
        # 添加第二个玩家
        other_player = Player(
            player_id="player_2", faction_id="Populares",
            player_type=PlayerType.HUMAN,
        )
        state._players["player_2"] = other_player
        state.mark_phase_executed("resolution")

        # 非当前玩家查看
        result = session_api.get_resolution_view(state, "player_2")

        assert result["success"] is True
        data = result["data"]
        assert data["resolved"] is True
        assert data["is_current_player"] is False
        # 业务数据仍然可见
        assert len(data["step_statuses"]) == 5


# ===========================================================================
# 边界：步数完整性
# ===========================================================================

class TestResolutionViewStepCount:
    """验证五步进度条完整性。"""

    def test_exactly_five_steps(self):
        state, viewer_id = _make_minimal_state()
        state.mark_phase_executed("resolution")

        result = session_api.get_resolution_view(state, viewer_id)
        assert len(result["data"]["step_statuses"]) == 5


# ===========================================================================
# WP-03 Slice 5/7 — population liveness predicate + 读模型（DA-Execute）
# ===========================================================================

def _make_empty_population_state():
    """创建无任何候选人（全 office 空）的人口阶段状态，含一个 HUMAN 玩家。"""
    config = {
        "testing": {"bypass_player_check": True},
        "political_rules": {
            "min_ages": {"consul": 40},
            "office_rank": {"consul": 5},
            "office_influence_bonus": {"consul": 40},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    state.treasury = 200

    faction = Faction(id="Optimates", name="贵族派")
    state._factions["Optimates"] = faction

    player = Player(
        player_id="player_1",
        faction_id="Optimates",
        player_type=PlayerType.HUMAN,
    )
    state._players["player_1"] = player
    state._current_player_id = "player_1"
    state._turn_order = ["player_1"]
    state._provinces = {}
    return state, "player_1"


class TestPopulationLivenessPredicates:
    """WP-03 Slice 5：empty-state completion predicate 修复。"""

    def test_all_human_votes_complete_empty_offices(self):
        """TS-05.1：空 required_offices → True（HUMAN 平凡完成）。"""
        state, viewer_id = _make_empty_population_state()
        assert session_api._all_human_population_votes_complete(state) is True

    def test_drain_ai_population_turns_empty_offices(self):
        """TS-05.2：空 required_offices → success 且 AI vote_completed=True（非 terminal）。"""
        state, viewer_id = _make_empty_population_state()
        # 追加一个 AI 玩家
        ai_faction = Faction(id="Populares", name="平民派")
        state._factions["Populares"] = ai_faction
        ai = Player(player_id="ai_1", faction_id="Populares", player_type=PlayerType.AI)
        state._players["ai_1"] = ai

        result = session_api._drain_ai_population_turns(state, None)
        assert result["success"] is True
        assert state.get_vote_completed("ai_1") is True

    def test_get_population_view_empty_state(self):
        """TS-05.3：空态读模型 campaign_done/vote_done/vacant_offices/my_candidate_count。"""
        state, viewer_id = _make_empty_population_state()
        result = session_api.get_population_view(state, viewer_id)
        assert result["success"] is True
        data = result["data"]
        assert data["office_count"] == 0
        assert data["my_candidate_count"] == 0
        assert data["vacant_offices"] == ["consul", "censor", "praetor", "quaestor", "tribune"]
        assert data["campaign_done"] is True
        assert data["vote_done"] is True
        assert data["current_step"] == "vote"

    def test_conversion_dto_persists_across_refresh(self):
        """TS-07：转换 DTO 存 phase_result，refresh 不丢且不二次转换。"""
        from src.core.systems.war_system import WarSystem
        from src.core.entities.war import War, WarStatus, WarType
        state, viewer_id = _make_empty_population_state()
        fig = Figure.create_nobile(1, "Optimates", 45)
        fig.office = "consul"
        fig.is_absent = True
        state.add_member(fig)
        ws = WarSystem(state)
        war = War(id="war_1", name="Test War", war_type=WarType.FOREIGN)
        war.status = WarStatus.ACTIVE
        war.commander_id = fig.id
        war.set_commander_assigned_turn(0)
        ws._active_wars = [war]
        state._war_system = ws

        from src.api import population_api
        population_api.convert_battlefield_commanders(state)

        v1 = session_api.get_population_view(state, viewer_id)
        v2 = session_api.get_population_view(state, viewer_id)
        assert v1["data"]["battlefield_commander_conversion"]["total"] == 1
        assert v1["data"]["battlefield_commander_conversion"] == v2["data"]["battlefield_commander_conversion"]
        # 不二次转换：figure.office 仍为 proconsul，total 仍 1
        assert fig.office == "proconsul"
