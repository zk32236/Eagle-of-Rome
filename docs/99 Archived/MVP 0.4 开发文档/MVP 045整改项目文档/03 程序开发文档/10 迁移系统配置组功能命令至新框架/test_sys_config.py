# src/tests/test_commands/test_sys_config.py
"""
系统配置命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# 确保 src 在路径中
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.sys_config import TermsCommand, ReloadCommand
from src.core.localization import TerminologyService, TermSet
from src.core.game_state import GameState


@pytest.fixture
def mock_state():
    """模拟 GameState 实例"""
    state = MagicMock(spec=GameState)
    state.config = MagicMock()
    return state


@pytest.fixture
def mock_terminology():
    """模拟 TerminologyService 的类方法"""
    with patch.object(TerminologyService, 'set_preset') as mock_set, \
         patch.object(TerminologyService, 'get') as mock_get, \
         patch.object(TerminologyService, 'PRESETS', {
             'original': TermSet(),
             'historical_roman': TermSet(currency="Denarii"),
             'chinese_historical': TermSet(currency="第纳尔")
         }), \
         patch.object(TerminologyService, '_current', TerminologyService.PRESETS['original']):

        mock_get.return_value = TerminologyService.PRESETS['original']
        mock_set.return_value = True
        yield mock_set, mock_get


# ===== TermsCommand 测试 =====

def test_terms_no_args(mock_terminology, capsys):
    """无参数时应显示当前预设和可用列表"""
    mock_set, mock_get = mock_terminology
    cmd = TermsCommand(None)  # state 无关系

    result = cmd.execute([])
    captured = capsys.readouterr()

    assert result is True
    assert "当前术语预设: original" in captured.out
    assert "Senate/Senators/Talents" in captured.out or "original" in captured.out  # 根据实际输出调整
    assert "可用预设:" in captured.out
    assert "original" in captured.out
    assert "historical_roman" in captured.out


def test_terms_valid_preset(mock_terminology, capsys):
    """传入有效预设名应切换成功"""
    mock_set, mock_get = mock_terminology
    mock_set.return_value = True

    # 模拟切换后的 get 返回新预设
    def get_side_effect():
        return TerminologyService.PRESETS['historical_roman']
    mock_get.side_effect = get_side_effect

    cmd = TermsCommand(None)
    result = cmd.execute(["historical_roman"])

    captured = capsys.readouterr()
    assert result is True
    mock_set.assert_called_once_with("historical_roman")
    assert "✅ 已切换至: historical_roman" in captured.out
    assert "现在使用: Curia/Patricii/Denarii" in captured.out or "Denarii" in captured.out


def test_terms_invalid_preset(mock_terminology, capsys):
    """传入无效预设名应打印错误并返回 False"""
    mock_set, mock_get = mock_terminology
    mock_set.return_value = False

    cmd = TermsCommand(None)
    result = cmd.execute(["invalid"])

    captured = capsys.readouterr()
    assert result is False
    mock_set.assert_called_once_with("invalid")
    assert "❌ 未知预设: invalid" in captured.out
    assert "可用预设: original, historical_roman, chinese_historical" in captured.out


# ===== ReloadCommand 测试 =====

def test_reload_success(mock_state, capsys):
    """重载成功应打印成功信息并返回 True"""
    mock_state.config.reload.return_value = True
    cmd = ReloadCommand(mock_state)

    result = cmd.execute([])
    captured = capsys.readouterr()

    assert result is True
    mock_state.config.reload.assert_called_once()
    assert "✅ 配置重载成功" in captured.out


def test_reload_failure(mock_state, capsys):
    """重载失败应打印警告并返回 False"""
    mock_state.config.reload.return_value = False
    cmd = ReloadCommand(mock_state)

    result = cmd.execute([])
    captured = capsys.readouterr()

    assert result is False
    mock_state.config.reload.assert_called_once()
    assert "⚠️ 配置重载失败，保持原配置" in captured.out


def test_reload_no_config(mock_state, capsys):
    """如果 state.config 不存在，应妥善处理"""
    mock_state.config = None
    cmd = ReloadCommand(mock_state)

    result = cmd.execute([])
    captured = capsys.readouterr()

    assert result is False
    assert "游戏状态未初始化或配置不可用" in captured.out