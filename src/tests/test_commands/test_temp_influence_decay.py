"""
测试决议阶段中的临时影响力衰减
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import GameTurn
from src.ui.commands.phase_resolution import ResolutionCommand


@pytest.fixture
def state():
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    return state


class TestTempInfluenceDecay:
    def test_influence_update(self, state):
        fig = Figure(id=104, name="测试影响力", faction_id="test")
        fig._land_private = 2
        fig.veterans = 1
        fig.popularity = 5
        fig.family_prestige = 2
        fig.office = "ex-consul"
        fig.update_influence()
        base_influence = fig.influence  # 应为 20+10+5+20+20=75
        assert base_influence == 75, f"基础影响力应为75，实际{base_influence}"

        state.add_member(fig)
        # 验证人物在存活列表中
        assert fig in list(state.get_living_members()), "人物未在存活列表中"

        fig.add_temp_influence_task(10, 3)
        fig.update_influence()
        assert fig.get_temp_influence() == 10, "临时影响力应为10"
        assert fig.influence == 85, f"添加任务后影响力应为85，实际{fig.influence}"

        cmd = ResolutionCommand(state)

        # 第一次衰减
        cmd._process_temp_influence_decay()
        assert fig.get_temp_influence() == 10, "第一次衰减后临时影响力仍应为10"
        assert fig.influence == 85, f"第一次衰减后影响力应为85，实际{fig.influence}"

        # 第二次衰减
        cmd._process_temp_influence_decay()
        assert fig.get_temp_influence() == 10, "第二次衰减后临时影响力仍应为10"
        assert fig.influence == 85, f"第二次衰减后影响力应为85，实际{fig.influence}"

        # 第三次衰减（任务应结束）
        cmd._process_temp_influence_decay()
        assert fig.get_temp_influence() == 0, f"第三次衰减后临时影响力应为0，实际{fig.get_temp_influence()}"
        assert fig.influence == 75, f"第三次衰减后影响力应为75，实际{fig.influence}"