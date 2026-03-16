# src/tests/test_api/test_population_api.py
"""
API层单元测试 - 人口阶段相关API骨架
"""
import pytest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.player import Player, PlayerType
from src.api import population_api


@pytest.fixture
def test_state():
    """使用 create_for_testing 创建基础游戏状态"""
    config = {
        "testing": {"bypass_player_check": False},
    }
    state = GameState.create_for_testing(config)

    # 添加玩家
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    player2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.AI)
    state.add_player(player1)
    state.add_player(player2)
    state.set_turn_order(["p1", "p2"])
    state.set_current_player("p1")

    # 确保 _population_pending 已初始化
    state._population_pending = {"campaigns": [], "votes": []}

    return state


class TestCampaign:
    """测试 campaign API"""

    def test_function_exists_and_returns_dict(self, test_state):
        result = population_api.campaign(test_state, "p1", 1, 10)
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result
        assert "data" in result
        assert "errors" in result

    def test_not_current_player(self, test_state):
        result = population_api.campaign(test_state, "p2", 1, 10)
        assert result["success"] is False
        # 暂不检查具体消息，因未实现


class TestVote:
    """测试 vote API"""

    def test_function_exists_and_returns_dict(self, test_state):
        result = population_api.vote(test_state, "p1", "consul", 1)
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result

    def test_not_current_player(self, test_state):
        result = population_api.vote(test_state, "p2", "consul", 1)
        assert result["success"] is False


class TestGetCandidates:
    """测试 get_candidates API"""

    def test_function_exists_and_returns_dict(self, test_state):
        result = population_api.get_candidates(test_state)
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "data" in result
        assert isinstance(result["data"], dict)
        # 检查包含所有公职键
        expected_keys = ["consul", "censor", "praetor", "quaestor", "tribune"]
        for key in expected_keys:
            assert key in result["data"]