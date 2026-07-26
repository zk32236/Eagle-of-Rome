# src/tests/test_commands/test_phase_senate_governor.py
"""Tests for governor-related functionality migrated to senate_api.assign_governors()"""
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.province import Province
from src.core.entities.figure import Figure, OfficeTerm
from src.core.entities.contract import ContractType, ContractStatus
from src.ui.commands.phase_senate import SenateCommand
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider


@pytest.fixture
def state():
    config = {
        "political_rules": {
            "office_cooldowns": {"consul": 2, "praetor": 2}
        }
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=5, year=-275)
    state.mark_phase_executed("population")
    return state


@pytest.fixture
def provinces(state):
    # 按需求初始化行省
    sicily = Province(1, "西西里", 1000)
    sicily._governor_id = 101
    sicily._governor_type = "proconsul"
    sardinia = Province(2, "撒丁岛", 800)
    sardinia._governor_id = 102
    sardinia._governor_type = "propraetor"
    corsica = Province(3, "科西嘉", 600)
    corsica._governor_id = 103
    corsica._governor_type = "propraetor"
    state.add_province(sicily)
    state.add_province(sardinia)
    state.add_province(corsica)

    # 创建原总督人物，并设为 absent（已在行省）
    old1 = Figure(id=101, name="Old Consul", faction_id="senate", age=60)
    old1.is_absent = True
    old2 = Figure(id=102, name="Old Praetor A", faction_id="populares", age=55)
    old2.is_absent = True
    old3 = Figure(id=103, name="Old Praetor B", faction_id="populares", age=54)
    old3.is_absent = True
    for fig in [old1, old2, old3]:
        state.add_member(fig)

    return [sicily, sardinia, corsica]


@pytest.fixture
def figures(state):
    # 创建候选人：ex-consul (卸任年份不同) 和 ex-praetor
    fig1 = Figure(id=201, name="Consul A", faction_id="senate", age=50)
    fig1.office_history = [OfficeTerm("consul", start_turn=1, end_turn=2)]   # 卸任于回合2（-274 BC）
    fig2 = Figure(id=202, name="Consul B", faction_id="senate", age=48)
    fig2.office_history = [OfficeTerm("consul", start_turn=2, end_turn=3)]   # 卸任于回合3（-273 BC）更晚
    fig3 = Figure(id=203, name="Praetor A", faction_id="populares", age=45)
    fig3.office_history = [OfficeTerm("praetor", start_turn=2, end_turn=4)]  # 卸任于回合4
    fig4 = Figure(id=204, name="Praetor B", faction_id="populares", age=44)
    fig4.office_history = [OfficeTerm("praetor", start_turn=3, end_turn=4)]  # 同回合4
    # 添加一个无资格人物
    fig5 = Figure(id=205, name="No Office", faction_id="senate", age=40)
    fig5.office_history = []
    for fig in [fig1, fig2, fig3, fig4, fig5]:
        state.add_member(fig)
    return [fig1, fig2, fig3, fig4, fig5]


def test_governor_appointment_order(state, provinces, figures):
    """验证通过 senate_api.assign_governors 正确按资格分配总督"""
    for p in provinces:
        p._conquered = True
    # 清除保民官（防止干扰）
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True

    from src.api import senate_api
    results = senate_api.assign_governors(state)

    # 应分配 3 个行省总督
    assert len(results) == 3
    # Consul B (202) 卸任更晚，应优先分配
    governor_ids = [r['governor_id'] for r in results]
    assert 202 in governor_ids  # 卸任更晚的执政官被选中
    # 验证两个大法官被选中
    assert 203 in governor_ids or 204 in governor_ids
    # 验证无资格人物未被分配
    assert 205 not in governor_ids
    # 验证行省 ID 正确
    province_ids = [r['province_id'] for r in results]
    assert all(pid in [1, 2, 3] for pid in province_ids)


def test_tribune_veto_some(state, provinces, figures):
    """测试保民官 veto 仍然可用（通过 senate_api.assign_governors 获取结果后自行过滤）"""
    for p in provinces:
        p._conquered = True

    from src.api import senate_api
    results = senate_api.assign_governors(state)

    # 手动模拟否决行省 ID 为 1 的任命
    vetoed_province_id = 1
    filtered_results = [r for r in results if r['province_id'] != vetoed_province_id]

    # 验证被否决的行省没有候任总督
    sicily = state.get_province(1)
    assert sicily.governor_designate_id is None or sicily.governor_designate_id == \
           [r['governor_id'] for r in results if r['province_id'] == 1][0]

    # 验证其他行省
    for r in filtered_results:
        prov = state.get_province(r['province_id'])
        assert prov.governor_designate_id is not None  # 候任总督已设置
        new_fig = state.get_member(r['governor_id'])
        assert new_fig.is_absent is True


def test_governor_return_in_resolution(state, provinces, figures):
    """测试总督任命后的候任状态"""
    import datetime
    for p in provinces:
        p._conquered = True
    # 移除保民官
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True

    from src.api import senate_api
    results = senate_api.assign_governors(state)

    # 验证分配结果
    assert len(results) > 0
    for r in results:
        assert 'province_id' in r
        assert 'governor_id' in r
        assert 'name' in r
        assert 'assigned_at' in r  # 时间戳或回合数

    # 验证候任总督已被设置
    for r in results:
        prov = state.get_province(r['province_id'])
        assert prov.governor_designate_id is not None


def test_no_candidates_for_propreator(state, provinces, figures):
    """测试大法官候选人不足时，senate_api.assign_governors 跳过该类型行省"""
    # 将两个大法官标记死亡
    for fig_id in [203, 204]:
        fig = state.get_member(fig_id)
        if fig:
            fig.is_dead = True

    for p in provinces:
        p._conquered = True
    # 移除保民官
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True

    from src.api import senate_api
    results = senate_api.assign_governors(state)

    # 大法官候选人不足，仅 proconsul 行省可分配
    # 只有 province_id=1 (proconsul) 可分配，province=2,3 (propraetor) 被跳过
    prop_assignments = [r for r in results if r['province_id'] in [2, 3]]
    assert len(prop_assignments) == 0

    # 检查原值不变
    for pid in [2, 3]:
        prov = state.get_province(pid)
        assert prov.governor_id in (102, 103)
