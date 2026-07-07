# src/tests/test_api/test_game_api.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import game_api
from src.core.entities.entities import GameTurn
from src.core.i18n import i18n

# 在所有测试开始前加载 i18n（确保消息文本正确）
i18n.load("zh-CN")

@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.treasury = 1000
    state.get_living_members.return_value = [MagicMock() for _ in range(5)]
    state.factions = {"f1": MagicMock(), "f2": MagicMock()}
    state.turn = MagicMock(spec=GameTurn)
    state.turn.year = -264
    state.turn.turn_number = 10
    state.get_economic_rule.side_effect = lambda key, default: {
        "land_price_per_unit": 10,
        "national_public_land_tax_rate": 0.02
    }.get(key, default)
    state.get_national_public_land.return_value = 1000
    # 默认是当前玩家（测试权限时覆盖）
    state.is_current_player.return_value = True
    # 配置相关：确保 bypass_player_check 为 False
    state.config.get.return_value = False
    # 阶段执行状态：默认未执行
    state.is_phase_executed.return_value = False
    return state

def test_get_status_summary(mock_state):
    result = game_api.get_status_summary(mock_state)
    assert result["success"] is True
    assert "📊 游戏状态摘要" in result["message"]
    assert "国库: 1000 塔兰特" in result["message"]
    assert "存活人物: 5 人" in result["message"]
    assert "派系数: 2 个" in result["message"]
    assert result["data"]["treasury"] == 1000

def test_get_public_land_info(mock_state):
    result = game_api.get_public_land_info(mock_state)
    assert result["success"] is True
    assert "🏞️ 国家公地信息" in result["message"]
    assert "公地数量: 1000 C" in result["message"]
    assert "年收益: 200 Talents" in result["message"]  # 1000*10*0.02 = 200
    assert result["data"]["national_land"] == 1000

@pytest.fixture
def mock_phase_commands(monkeypatch):
    """替换 game_api.PHASE_COMMAND_MAP 中的命令类为 mock 类"""
    mock_mortality = MagicMock()
    mock_instance = MagicMock()
    mock_instance.execute.return_value = True
    mock_mortality.return_value = mock_instance

    # 保存原始映射（monkeypatch 会自动恢复）
    monkeypatch.setitem(game_api.PHASE_COMMAND_MAP, "mortality", mock_mortality)
    # 可根据需要添加其他阶段 mock

    yield mock_mortality, mock_instance

def test_execute_phase_success(mock_state, mock_phase_commands):
    """测试 execute_phase 成功执行阶段"""
    mock_state.is_current_player.return_value = True
    mock_mortality, mock_instance = mock_phase_commands
    result = game_api.execute_phase(mock_state, "mortality", "player1")
    assert result["success"] is True
    assert "message" in result
    mock_mortality.assert_called_once_with(mock_state)
    mock_instance.execute.assert_called_once_with([])

def test_execute_phase_not_current_player(mock_state):
    """测试 execute_phase 权限失败"""
    mock_state.is_current_player.return_value = False
    result = game_api.execute_phase(mock_state, "mortality", "player1")
    assert result["success"] is False
    assert "当前不是您的回合" in result["message"]

def test_execute_phase_invalid(mock_state):
    """测试 execute_phase 传入无效阶段名"""
    mock_state.is_current_player.return_value = True
    result = game_api.execute_phase(mock_state, "invalid", "player1")
    assert result["success"] is False
    assert "未知阶段" in result["message"]

def test_execute_phase_exception(mock_state, mock_phase_commands):
    """测试阶段执行抛出异常"""
    mock_state.is_current_player.return_value = True
    mock_mortality, mock_instance = mock_phase_commands
    mock_instance.execute.side_effect = ValueError("模拟错误")
    result = game_api.execute_phase(mock_state, "mortality", "player1")
    assert result["success"] is False
    assert "阶段执行异常" in result["message"]

def test_execute_turn_all_phases(mock_state):
    """测试 execute_turn 执行所有阶段"""
    mock_state.is_current_player.return_value = True
    mock_state.is_phase_executed.return_value = False  # 所有阶段未执行
    with patch('src.api.game_api.execute_phase') as mock_exec:
        mock_exec.return_value = {"success": True, "message": "ok"}
        result = game_api.execute_turn(mock_state, "player1")
        assert result["success"] is True
        assert mock_exec.call_count == 7

def test_execute_turn_partial(mock_state):
    """测试 execute_turn 跳过已执行阶段"""
    mock_state.is_current_player.return_value = True
    def is_executed_side_effect(phase):
        return phase in ["mortality", "revenue"]
    mock_state.is_phase_executed.side_effect = is_executed_side_effect
    with patch('src.api.game_api.execute_phase') as mock_exec:
        mock_exec.return_value = {"success": True, "message": "ok"}
        result = game_api.execute_turn(mock_state, "player1")
        assert result["success"] is True
        # 应执行剩余5个阶段
        assert mock_exec.call_count == 5

def test_execute_turn_not_current_player(mock_state):
    """测试 execute_turn 权限失败"""
    mock_state.is_current_player.return_value = False
    result = game_api.execute_turn(mock_state, "player1")
    assert result["success"] is False
    assert "当前不是您的回合" in result["message"]

def test_advance_year(mock_state):
    """测试 advance_year 推进回合"""
    mock_state.is_current_player.return_value = True
    mock_state.turn = MagicMock()
    mock_state.turn.get_year_display.return_value = "281 BC"
    result = game_api.advance_year(mock_state, "player1")
    assert result["success"] is True
    assert result["message"] == "已推进至 281 BC"
    mock_state.advance_year.assert_called_once()

def test_advance_year_not_current_player(mock_state):
    """测试 advance_year 权限失败"""
    mock_state.is_current_player.return_value = False
    result = game_api.advance_year(mock_state, "player1")
    assert result["success"] is False
    assert "当前不是您的回合" in result["message"]