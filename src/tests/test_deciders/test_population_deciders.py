# src/tests/test_deciders/test_population_deciders.py
"""
决策器单元测试 - 自动庆典决策器和自动投票决策器
"""
import pytest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider


@pytest.fixture
def test_state():
    """创建基础测试状态"""
    config = {
        "testing": {},
        "political_rules": {
            "min_festival_age": 30,
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    return state


@pytest.fixture
def faction(test_state):
    """创建测试派系"""
    faction = Faction(id="f1", name="TestFaction", treasury=1000)
    test_state.add_faction(faction)
    return faction


@pytest.fixture
def candidates(test_state, faction):
    """创建多个候选人人物"""
    # 符合条件的人物1
    fig1 = Figure.create_nobile(1, faction.id, 35)
    fig1.wealth = 100
    test_state.add_member(fig1)

    # 符合条件的人物2
    fig2 = Figure.create_nobile(2, faction.id, 40)
    fig2.wealth = 200
    test_state.add_member(fig2)

    # 财富不足的人物
    fig3 = Figure.create_nobile(3, faction.id, 45)
    fig3.wealth = 0
    test_state.add_member(fig3)

    # 年龄不足的人物
    fig4 = Figure.create_nobile(4, faction.id, 25)
    fig4.wealth = 150
    test_state.add_member(fig4)

    # 其他派系人物（不应被本派系决策器选中）
    fig5 = Figure.create_nobile(5, "f2", 38)
    fig5.wealth = 120
    test_state.add_member(fig5)

    return [fig1, fig2, fig3, fig4, fig5]


# ========== TestAutoFestivalDecider ==========

class TestAutoFestivalDecider:
    """自动庆典决策器测试"""

    def test_no_candidates(self, test_state, faction):
        """无候选人时返回空字典"""
        decider = AutoFestivalDecider()
        result = decider.decide_festivals(faction, [], test_state)
        assert result == {}

    def test_candidates_with_insufficient_wealth(self, test_state, faction, candidates):
        """候选人财富不足时跳过"""
        # fig3 财富为0，不应被选中
        decider = AutoFestivalDecider()
        result = decider.decide_festivals(faction, candidates, test_state)
        # 结果应只包含 fig1 和 fig2（可能随机选部分或全部）
        assert len(result) >= 1
        for fig_id, amount in result.items():
            fig = test_state.get_member(fig_id)
            assert fig.wealth >= amount
            # 不应包含财富为0的人物
            assert fig_id != 3

    def test_candidates_below_min_age(self, test_state, faction, candidates):
        """低于最低年龄的候选人跳过"""
        # fig4 年龄25 < 30，不应被选中
        decider = AutoFestivalDecider()
        result = decider.decide_festivals(faction, candidates, test_state)
        for fig_id in result:
            assert fig_id != 4

    def test_normal(self, test_state, faction, candidates):
        """正常情况为部分候选人随机花费"""
        # 只取本派系候选人
        own_candidates = [fig for fig in candidates if fig.faction_id == faction.id]
        decider = AutoFestivalDecider()
        result = decider.decide_festivals(faction, own_candidates, test_state)
        # 应至少有一个决定
        assert len(result) > 0
        for fig_id, amount in result.items():
            assert amount > 0
            fig = test_state.get_member(fig_id)
            assert amount <= fig.wealth
            assert fig.faction_id == faction.id

    def test_logging(self, test_state, faction, candidates):
        """检查是否记录了DEBUG日志"""
        decider = AutoFestivalDecider()
        with patch.object(test_state, 'log_event') as mock_log:
            result = decider.decide_festivals(faction, candidates, test_state)
            # 至少记录了一次日志（开始和结束）
            assert mock_log.call_count >= 2


# ========== TestAutoVoteDecider ==========

class TestAutoVoteDecider:
    """自动投票决策器测试"""

    def test_no_candidates(self, test_state, faction):
        """无候选人时返回None"""
        decider = AutoVoteDecider()
        result = decider.decide_vote("consul", [], faction, test_state)
        assert result is None

    def test_own_faction_candidate(self, test_state, faction, candidates):
        """有本派系候选人时，随机选本派系"""
        # 候选人列表包含本派系和其他派系
        all_candidates = candidates  # 包含本派系和其他派系
        decider = AutoVoteDecider()
        # 多次调用，确保有时选到本派系（理论上总是选本派系，因为本派系存在）
        chosen = decider.decide_vote("consul", all_candidates, faction, test_state)
        chosen_fig = test_state.get_member(chosen)
        assert chosen_fig.faction_id == faction.id

    def test_no_own_faction_candidate(self, test_state, faction):
        """无本派系候选人时，从所有候选人中随机选"""
        # 创建两个其他派系的候选人
        fig1 = Figure.create_nobile(10, "f2", 40)
        fig1.wealth = 100
        test_state.add_member(fig1)
        fig2 = Figure.create_nobile(11, "f3", 45)
        fig2.wealth = 200
        test_state.add_member(fig2)
        candidates = [fig1, fig2]

        decider = AutoVoteDecider()
        chosen = decider.decide_vote("consul", candidates, faction, test_state)
        assert chosen in [10, 11]

    def test_logging(self, test_state, faction, candidates):
        """检查是否记录了DEBUG日志"""
        decider = AutoVoteDecider()
        with patch.object(test_state, 'log_event') as mock_log:
            result = decider.decide_vote("consul", candidates, faction, test_state)
            assert mock_log.call_count >= 1