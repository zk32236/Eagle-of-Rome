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

    def test_own_faction_candidate(self, test_state, faction):
        """有本派系候选人时，选择影响力最高的"""
        # 创建几个本派系候选人，影响力不同
        fig1 = Figure.create_nobile(101, faction.id, 40)
        fig1.influence = 100
        fig2 = Figure.create_nobile(102, faction.id, 45)
        fig2.influence = 80
        fig3 = Figure.create_nobile(103, faction.id, 38)
        fig3.influence = 120  # 最高
        test_state.add_member(fig1)
        test_state.add_member(fig2)
        test_state.add_member(fig3)

        # 其他派系候选人
        fig4 = Figure.create_nobile(104, "other_faction", 50)
        fig4.influence = 200
        test_state.add_member(fig4)

        candidates = [fig1, fig2, fig3, fig4]
        decider = AutoVoteDecider()
        chosen_id = decider.decide_vote("consul", candidates, faction, test_state)
        # 应选择影响力最高的 fig3 (ID 103)
        assert chosen_id == 103

    def test_no_own_faction_candidate(self, test_state, faction):
        """无本派系候选人时，从所有候选人中随机选择（可mock随机固定结果）"""
        # 创建两个其他派系候选人
        fig1 = Figure.create_nobile(105, "f2", 40)
        fig1.influence = 50
        fig2 = Figure.create_nobile(106, "f3", 45)
        fig2.influence = 60
        test_state.add_member(fig1)
        test_state.add_member(fig2)
        candidates = [fig1, fig2]

        decider = AutoVoteDecider()
        with patch('random.choice') as mock_choice:
            mock_choice.return_value = fig1
            chosen_id = decider.decide_vote("consul", candidates, faction, test_state)
            assert chosen_id == 105
            mock_choice.assert_called_once_with(candidates)

    def test_logging(self, test_state, faction):
        """检查是否记录了DEBUG日志"""
        fig1 = Figure.create_nobile(107, faction.id, 40)
        fig1.influence = 50
        test_state.add_member(fig1)
        candidates = [fig1]

        decider = AutoVoteDecider()
        with patch.object(test_state, 'log_event') as mock_log:
            result = decider.decide_vote("consul", candidates, faction, test_state)
            mock_log.assert_called_once()