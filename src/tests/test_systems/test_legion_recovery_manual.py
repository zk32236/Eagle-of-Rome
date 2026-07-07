# test_legion_recovery_manual.py
"""
测试军团恢复机制的独立脚本
运行: pytest test_legion_recovery_manual.py -v
"""

import pytest
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.entities.legion import LegionStatus
from src.core.entities.entities import GameTurn


@pytest.fixture
def test_setup():
    """创建测试环境：GameState 和 MilitarySystem，国库充足，配置恢复间隔为3回合便于快速测试"""
    config = {
        "combat_rules": {
            "legion_recovery_interval": 3
        }
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-264)
    state.treasury = 1000  # 确保有足够资金征召
    ms = MilitarySystem(state)
    return state, ms


def test_legion_recovery(test_setup):
    """测试被摧毁的军团能否在指定回合后恢复"""
    state, ms = test_setup

    # 1. 征召几个军团（例如1,2,3号）
    for num in [1, 2, 3]:
        success, msg = ms.recruit_legion(num)
        assert success, f"征召军团 {num} 失败: {msg}"

    # 2. 模拟战斗灾难：将它们全部摧毁，记录摧毁回合
    current_turn = state.turn.turn_number  # 当前第1回合
    for num in [1, 2, 3]:
        legion = ms.get_legion_by_number(num)
        legion.mark_destroyed(current_turn)
        assert legion.status == LegionStatus.DESTROYED
        assert legion.destroyed_turn == current_turn

    # 3. 推进回合，但尚未达到恢复间隔，检查不应恢复
    # 第2回合
    recovered = ms._process_legion_recovery(2)
    assert recovered == [], "第2回合不应有军团恢复"
    for num in [1, 2, 3]:
        legion = ms.get_legion_by_number(num)
        assert legion.status == LegionStatus.DESTROYED

    # 第3回合（摧毁于第1回合，3-1=2 < 3，仍不满足）
    recovered = ms._process_legion_recovery(3)
    assert recovered == [], "第3回合仍不应恢复"
    for num in [1, 2, 3]:
        legion = ms.get_legion_by_number(num)
        assert legion.status == LegionStatus.DESTROYED

    # 第4回合（4-1=3 >= 3，应恢复一个最老的，即1号）
    recovered = ms._process_legion_recovery(4)
    assert recovered == [1], "第4回合应恢复1号军团"
    # 验证1号已恢复，其他仍摧毁
    legion1 = ms.get_legion_by_number(1)
    assert legion1.status == LegionStatus.DISBANDED
    assert legion1.destroyed_turn == 0
    legion2 = ms.get_legion_by_number(2)
    assert legion2.status == LegionStatus.DESTROYED
    legion3 = ms.get_legion_by_number(3)
    assert legion3.status == LegionStatus.DESTROYED

    # 第5回合（5-2=3，应恢复2号）
    recovered = ms._process_legion_recovery(5)
    assert recovered == [2], "第5回合应恢复2号军团"
    legion2 = ms.get_legion_by_number(2)
    assert legion2.status == LegionStatus.DISBANDED
    legion3 = ms.get_legion_by_number(3)
    assert legion3.status == LegionStatus.DESTROYED

    # 第6回合（6-3=3，应恢复3号）
    recovered = ms._process_legion_recovery(6)
    assert recovered == [3], "第6回合应恢复3号军团"
    legion3 = ms.get_legion_by_number(3)
    assert legion3.status == LegionStatus.DISBANDED

    # 第7回合无更多摧毁军团
    recovered = ms._process_legion_recovery(7)
    assert recovered == [], "无更多可恢复的军团"


def test_legion_recovery_with_interval_config(test_setup):
    """测试配置恢复间隔为5的情况"""
    state, ms = test_setup
    # 修改配置间隔为5
    state.config._config["combat_rules"]["legion_recovery_interval"] = 5

    # 征召并摧毁1号军团于第1回合
    ms.recruit_legion(1)
    legion = ms.get_legion_by_number(1)
    legion.mark_destroyed(1)

    # 第6回合（6-1=5）应恢复
    recovered = ms._process_legion_recovery(6)
    assert recovered == [1]
    assert legion.status == LegionStatus.DISBANDED

    # 第5回合（5-1=4）不应恢复
    # 重新摧毁再测
    legion.mark_destroyed(1)  # 再次摧毁
    recovered = ms._process_legion_recovery(5)
    assert recovered == []
    assert legion.status == LegionStatus.DESTROYED


def test_legion_recovery_zero_interval(test_setup):
    """测试恢复间隔为0（禁用恢复）"""
    state, ms = test_setup
    state.config._config["combat_rules"]["legion_recovery_interval"] = 0

    ms.recruit_legion(1)
    legion = ms.get_legion_by_number(1)
    legion.mark_destroyed(1)

    # 任意回合后都不应恢复
    recovered = ms._process_legion_recovery(100)
    assert recovered == []
    assert legion.status == LegionStatus.DESTROYED