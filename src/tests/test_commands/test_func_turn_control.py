# src/tests/test_commands/test_func_turn_control.py
"""
回合控制命令单元测试
"""

import pytest
from unittest.mock import MagicMock, patch, call
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.commands.func_turn_control import NextCommand, TurnCommand, StepCommand, PHASE_SEQUENCE
from src.core.game_state import GameState


@pytest.fixture
def mock_state():
    """模拟 GameState"""
    state = MagicMock(spec=GameState)
    state.is_phase_executed.return_value = False
    state.executed_phases = set()
    state.turn.turn_number = 1
    state.turn.year = -264
    state.advance_year = MagicMock()
    # 模拟 config.get 返回合理数值，避免阶段命令内部出错（备用）
    state.config.get.return_value = 1
    state.get_living_members.return_value = []  # 避免除零错误
    return state


@pytest.fixture
def mock_phase_commands(monkeypatch):
    """模拟所有阶段命令类，替换 PHASE_COMMAND_CLASSES 字典"""
    import src.ui.commands.func_turn_control as turn_control
    mocks = {}
    for phase in PHASE_SEQUENCE:
        mock_cmd_class = MagicMock()
        mock_cmd_instance = MagicMock()
        mock_cmd_instance.execute.return_value = True
        mock_cmd_class.return_value = mock_cmd_instance
        mocks[phase] = mock_cmd_class
        # 替换字典中的条目
        monkeypatch.setitem(turn_control.PHASE_COMMAND_CLASSES, phase, mock_cmd_class)
    return mocks


# ========== NextCommand 测试 ==========

def test_next_success_all_done(mock_state):
    """所有阶段已执行，next 应推进回合"""
    mock_state.is_phase_executed.return_value = True
    # 设置 executed_phases 包含所有阶段
    mock_state.executed_phases = set(PHASE_SEQUENCE)
    cmd = NextCommand(mock_state)

    result = cmd.execute([])

    assert result is True
    mock_state.advance_year.assert_called_once()


def test_next_missing_phases_no_force(mock_state):
    """有阶段未执行，无 force，返回 False"""
    # 默认 executed_phases 为空
    cmd = NextCommand(mock_state)

    result = cmd.execute([])

    assert result is False
    mock_state.advance_year.assert_not_called()


def test_next_force(mock_state):
    """有阶段未执行但有 force，应推进"""
    cmd = NextCommand(mock_state)

    result = cmd.execute(["force"])

    assert result is True
    mock_state.advance_year.assert_called_once()


def test_next_force_case_insensitive(mock_state):
    """force 参数不区分大小写"""
    cmd = NextCommand(mock_state)

    result = cmd.execute(["FORCE"])

    assert result is True
    mock_state.advance_year.assert_called_once()


# ========== TurnCommand 测试 ==========

def test_turn_execute_all_phases(mock_state, mock_phase_commands):
    """turn 应执行所有未执行阶段"""
    cmd = TurnCommand(mock_state)
    # 所有阶段都未执行
    mock_state.executed_phases = set()

    result = cmd.execute([])

    assert result is True
    # 验证每个阶段的命令类被实例化并执行
    for phase in PHASE_SEQUENCE:
        mock_cmd_class = mock_phase_commands[phase]
        mock_cmd_class.assert_called_once_with(mock_state)
        mock_cmd_class.return_value.execute.assert_called_once_with([])


def test_turn_skip_already_executed(mock_state, mock_phase_commands):
    """已执行的阶段应跳过"""
    cmd = TurnCommand(mock_state)
    # 设置 mortality 和 revenue 已执行
    mock_state.executed_phases = {"mortality", "revenue"}

    result = cmd.execute([])

    assert result is True
    # 只有未执行的阶段应该被调用
    for phase in PHASE_SEQUENCE:
        mock_cmd_class = mock_phase_commands[phase]
        if phase in ["mortality", "revenue"]:
            mock_cmd_class.assert_not_called()
        else:
            mock_cmd_class.assert_called_once_with(mock_state)


def test_turn_all_done(mock_state):
    """所有阶段已执行，应提示并返回 True"""
    mock_state.executed_phases = set(PHASE_SEQUENCE)
    cmd = TurnCommand(mock_state)

    result = cmd.execute([])

    assert result is True
    # 不应调用任何阶段命令（由于 mock_phase_commands 未注入，无需验证）


# ========== StepCommand 测试 ==========

def test_step_execute_with_input(mock_state, mock_phase_commands, monkeypatch):
    """step 应执行阶段并等待输入"""
    # 模拟 input 函数，返回空字符串
    input_mock = MagicMock(return_value="")
    monkeypatch.setattr("builtins.input", input_mock)

    cmd = StepCommand(mock_state)
    mock_state.executed_phases = set()

    result = cmd.execute([])

    assert result is True
    # 每个阶段命令都应执行
    for phase in PHASE_SEQUENCE:
        mock_cmd_class = mock_phase_commands[phase]
        mock_cmd_class.assert_called_once_with(mock_state)
        mock_cmd_class.return_value.execute.assert_called_once_with([])

    # input 应该被调用 7 次（每个阶段后一次）
    assert input_mock.call_count == 7


def test_step_interrupt(mock_state, mock_phase_commands, monkeypatch):
    """用户中断（KeyboardInterrupt）应优雅退出"""
    def input_side_effect(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", input_side_effect)

    cmd = StepCommand(mock_state)
    mock_state.executed_phases = set()

    result = cmd.execute([])

    assert result is False  # 中断后返回 False


def test_step_skip_executed(mock_state, mock_phase_commands, monkeypatch):
    """已执行的阶段应跳过"""
    input_mock = MagicMock(return_value="")
    monkeypatch.setattr("builtins.input", input_mock)

    cmd = StepCommand(mock_state)
    # 假设 mortality 已执行
    mock_state.executed_phases = {"mortality"}

    result = cmd.execute([])

    assert result is True
    # mortality 不应调用
    mock_phase_commands["mortality"].assert_not_called()
    # 其他阶段应调用
    for phase in PHASE_SEQUENCE[1:]:
        mock_phase_commands[phase].assert_called_once_with(mock_state)

    # input 调用次数应为 6（因为跳过一个阶段）
    assert input_mock.call_count == 6


def test_next_clears_curia():
    """测试 next 命令执行时，清除广场中未被招募的人物"""
    from src.core.game_state import GameState
    from src.core.entities.figure import Figure
    from src.core.entities.entities import GameTurn
    from src.ui.commands.func_turn_control import NextCommand

    # 创建测试用的 GameState
    state = GameState.create_for_testing({})

    # 添加两个平民人物到 curia 和 _members（模拟未被招募的新人物）
    fig1 = Figure.create_plebeian(999, None, age=20)
    fig2 = Figure.create_plebeian(1000, None, age=25)
    state.curia.add_figure(fig1)
    state.curia.add_figure(fig2)
    state._members[999] = fig1
    state._members[1000] = fig2

    # 设置回合信息（create_for_testing 可能未设置 turn）
    state.turn = GameTurn(turn_number=1, year=-264)

    # 标记所有阶段已执行，以便 next 允许推进
    for phase in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        state.mark_phase_executed(phase)

    cmd = NextCommand(state)
    result = cmd.execute([])

    assert result is True
    # 验证广场已清空
    assert state.curia.is_empty() is True
    # 验证人物已从成员字典中移除
    assert 999 not in state._members
    assert 1000 not in state._members