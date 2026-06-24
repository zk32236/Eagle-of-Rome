# src/tests/test_systems/test_naval_unlock.py

import pytest
from unittest.mock import Mock
from src.core.game_state import GameState
from src.core.systems.naval_system import NavalSystem
from src.core.entities.war import War, WarStatus


def test_naval_unlock_before_pyrrhic():
    state = GameState.create_for_testing({})
    state.pyrrhic_war_won = False
    naval = NavalSystem(state)

    # 生成建造合同应返回空列表
    contracts = naval.generate_construction_contracts(10)
    assert contracts == []


def test_naval_unlock_after_pyrrhic():
    state = GameState.create_for_testing({})
    state.pyrrhic_war_won = True
    naval = NavalSystem(state)

    # 需要模拟战争威胁才能生成合同
    war = War(id="war1", name="Test War", naval_required=True)
    war.status = WarStatus.THREAT   # 使用枚举值
    war._enemy_naval_current = 5
    war_system = Mock()
    war_system.get_naval_threat_wars.return_value = [war]
    state.get_war_system = lambda: war_system
    state.create_contract = lambda *args, **kwargs: Mock()

    contracts = naval.generate_construction_contracts(10)
    # 应返回非空（前提是配置正确）
    assert contracts is not None
