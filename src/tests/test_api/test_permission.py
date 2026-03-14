import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import forum_api, game_api, player_api
from src.core.i18n import i18n

# 加载语言包（确保测试时可用）
i18n.load("zh-CN")


@pytest.fixture
def mock_state():
    """创建一个可配置的 GameState mock 对象"""
    state = MagicMock(spec=GameState)
    # 模拟 config.get 方法
    state.config.get = MagicMock(return_value=False)
    # 模拟 is_current_player：仅当 player_id 为 "current" 时返回 True
    state.is_current_player.side_effect = lambda pid: pid == "current"
    # 模拟 next_player 等（用于 player_api）
    state.next_player = MagicMock(return_value="next_player")
    # 模拟 get_player 等（按需）
    return state


def test_player_api_next_permission_bypass(mock_state):
    """测试 player_api.next_player 的权限绕过"""
    # 1. 开关关闭，使用非当前玩家 -> 应失败
    mock_state.config.get.return_value = False
    result = player_api.next_player(mock_state, "other")
    assert result["success"] is False
    assert "不是您的回合" in result["message"]

    # 2. 开关关闭，使用当前玩家 -> 应成功（但需确保后续逻辑正常）
    mock_state.config.get.return_value = False
    result = player_api.next_player(mock_state, "current")
    assert result["success"] is True
    mock_state.next_player.assert_called_once()

    # 3. 开关开启，使用非当前玩家 -> 应成功（绕过检查）
    mock_state.config.get.return_value = True
    mock_state.next_player.reset_mock()
    result = player_api.next_player(mock_state, "other")
    assert result["success"] is True
    mock_state.next_player.assert_called_once()


def test_forum_api_retire_permission_bypass(mock_state):
    """测试 forum_api.retire_figure 的权限绕过"""
    # 模拟玩家对象（可复用，因为玩家不会变）
    mock_player = MagicMock()
    mock_player.faction_id = "faction1"
    mock_state.get_player.return_value = mock_player

    # 模拟派系对象
    mock_faction = MagicMock()
    mock_state.get_faction.return_value = mock_faction

    # 模拟 curia
    mock_state.curia = MagicMock()

    # 辅助函数：每次创建新的人物 mock
    def create_figure():
        return MagicMock(
            faction_id="faction1",
            is_faction_leader=False,
            has_active_contract=False,
            is_dead=False,
            get_formal_name=lambda: "Test"
        )

    # 1. 开关关闭，非当前玩家 -> 失败
    mock_state.config.get.return_value = False
    mock_state.get_member.return_value = create_figure()
    result = forum_api.retire_figure(mock_state, "other", 1)
    assert result["success"] is False
    assert "不是您的回合" in result["message"]

    # 2. 开关关闭，当前玩家 -> 成功
    mock_state.config.get.return_value = False
    mock_state.get_member.return_value = create_figure()
    result = forum_api.retire_figure(mock_state, "current", 1)
    assert result["success"] is True

    # 3. 开关开启，非当前玩家 -> 成功
    mock_state.config.get.return_value = True
    mock_state.get_member.return_value = create_figure()
    result = forum_api.retire_figure(mock_state, "other", 1)
    assert result["success"] is True


def test_game_api_execute_phase_permission_bypass(mock_state):
    """测试 game_api.execute_phase 的权限绕过"""
    # 模拟命令类
    with patch("src.api.game_api.PHASE_COMMAND_MAP", {"test": MagicMock()}) as mock_map:
        mock_cmd_class = mock_map["test"]
        mock_cmd_instance = MagicMock()
        mock_cmd_class.return_value = mock_cmd_instance
        mock_cmd_instance.execute.return_value = True

        # 1. 开关关闭，非当前玩家 -> 失败
        mock_state.config.get.return_value = False
        result = game_api.execute_phase(mock_state, "test", "other")
        assert result["success"] is False
        assert "不是您的回合" in result["message"]

        # 2. 开关关闭，当前玩家 -> 成功
        mock_state.config.get.return_value = False
        result = game_api.execute_phase(mock_state, "test", "current")
        assert result["success"] is True

        # 3. 开关开启，非当前玩家 -> 成功
        mock_state.config.get.return_value = True
        result = game_api.execute_phase(mock_state, "test", "other")
        assert result["success"] is True