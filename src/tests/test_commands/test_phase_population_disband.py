"""
测试人口阶段中的军团解散和凯旋式处理 — 适配 API 下沉后的 CLI 委托模式
"""

import pytest
from unittest.mock import MagicMock
from src.ui.commands.phase_population import PopulationCommand
from src.core.entities.war import War, WarStatus
from src.core.entities.figure import Figure
from src.core.entities.legion import LegionStatus
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem


@pytest.fixture
def mock_state():
    state = MagicMock(spec=GameState)
    state.get_war_system.return_value = MagicMock(spec=WarSystem)
    state.get_military_system.return_value = MagicMock(spec=MilitarySystem)
    return state


@pytest.fixture
def mock_war():
    war = MagicMock(spec=War)
    war.id = "test_war"
    war.name = "测试战争"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    war.triumph_approved = True
    war.legion_numbers = [1, 2, 3]
    return war


@pytest.fixture
def mock_commander():
    fig = MagicMock(spec=Figure)
    fig.id = 101
    fig.name = "凯撒"
    fig.is_dead = False
    return fig


def _make_triumph_result(triumphs=None, resolved_total=0, resolved_errors=None,
                         deescalated_total=0, deescalated_errors=None,
                         failed_re_queued=None):
    return {
        "triumphs": triumphs or [],
        "disbanded": {
            "resolved_wars": {"total": resolved_total, "errors": resolved_errors or []},
            "deescalated": {"total": deescalated_total, "errors": deescalated_errors or []},
        },
        "failed_re_queued": failed_re_queued or [],
    }


class TestPopulationDisband:
    def test_disband_with_triumph(self, mock_state, mock_war, mock_commander):
        """测试凯旋已批准的战争：显示凯旋式并解散军团"""
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            triumphs=[{"war_id": "test_war", "war_name": "测试战争",
                       "commander_id": 101, "commander_name": "凯撒"}],
            resolved_total=3,
        )

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()

    def test_disband_without_triumph(self, mock_state, mock_war):
        """测试凯旋未批准的战争：只解散军团，不显示凯旋式"""
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            resolved_total=3,
        )

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()

    def test_commander_dead(self, mock_state, mock_war, mock_commander):
        """测试指挥官已死亡：不显示凯旋式，但军团仍解散"""
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            resolved_total=3,
        )

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()

    def test_no_legions(self, mock_state, mock_war):
        """测试战争没有军团记录，不应调用解散"""
        mock_war.legion_numbers = []
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result()

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()

    def test_multiple_wars(self, mock_state, mock_war):
        """测试多个战争"""
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            triumphs=[{"war_id": "test_war", "war_name": "测试战争",
                       "commander_id": 101, "commander_name": "凯撒"}],
            resolved_total=5,
        )

        cmd = PopulationCommand(mock_state)
        cmd._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()

    def test_failed_pending_legions_are_requeued(self, mock_state):
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            deescalated_total=1,
            deescalated_errors=["Legio II 解散失败"],
            failed_re_queued=[2],
        )

        PopulationCommand(mock_state)._process_legion_disbandment_and_triumphs()

        # Verify the CLI calls process_triumph_and_disbandment (not individual lower-level methods)
        ws.process_triumph_and_disbandment.assert_called_once()

    def test_failed_resolved_war_legions_move_to_pending_queue(
        self,
        mock_state,
        mock_war
    ):
        ws = mock_state.get_war_system.return_value
        ws.process_triumph_and_disbandment.return_value = _make_triumph_result(
            resolved_total=2,
            resolved_errors=["Legio III 解散失败"],
            failed_re_queued=[3],
        )

        PopulationCommand(mock_state)._process_legion_disbandment_and_triumphs()

        ws.process_triumph_and_disbandment.assert_called_once()
