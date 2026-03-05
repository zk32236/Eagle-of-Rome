# src/tests/test_commands/test_phase_senate_governor.py
import pytest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.entities import Province, Faction, GameTurn
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
    for p in provinces:
        p._conquered = True
    cmd = SenateCommand(state)
    # 清除保民官
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True

    # 修改候选人列表，确保 Consul B (202) 是唯一可用的前执政官，Praetor A(203) 和 B(204) 是唯二可用的前大法官
    # 手动设置 office_history 确保排序正确
    # 此处略，原有代码已设好

    cmd._process_governor_appointments(None)
    proposals = cmd.proposed_governors
    # 现在由于去重，同一个候选人不会同时出现在两个类型中，所以总提案数可能为2（如果执政官只有一个且大法官有两个，且执政官也符合大法官资格，但会被分配到一个类型后不再出现）
    # 因此需要根据实际情况调整断言
    # 假设 Consul B (202) 被分配到 proconsul 行省，Praetor A (203) 和 Praetor B (204) 分配到两个 propraetor 行省，总提案数应为3
    assert len(proposals) == 3
    # 验证 Consul B (202) 被选中
    found_202 = any(p['new_governor_id'] == 202 for p in proposals)
    assert found_202
    # 验证两个大法官被选中
    praetor_ids = {203, 204}
    selected_praetors = [p['new_governor_id'] for p in proposals if p['new_governor_id'] in praetor_ids]
    assert len(selected_praetors) == 2

def test_tribune_veto_some(state, provinces, figures):
    """测试保民官否决部分任命"""
    for p in provinces:
        p._conquered = True
    cmd = SenateCommand(state)
    # 添加保民官
    tribune = Figure(id=301, name="Tribune", faction_id="plebs", age=35)
    tribune.office = "tribune"
    state.add_member(tribune)

    # 模拟否决决策器：只否决第一个提案
    mock_veto = MagicMock(spec=TribuneVetoDecider)
    def veto_side_effect(issue, tribune_id, s):
        if isinstance(issue, dict) and issue.get('type') == 'governor_appointment' and issue.get('province_id') == 1:
            return True
        return False
    mock_veto.decide_veto.side_effect = veto_side_effect
    cmd.veto_decider = mock_veto

    # 先收集提案
    cmd._process_governor_appointments(None)
    proposals_before = cmd.proposed_governors.copy()
    assert len(proposals_before) == 3

    # 模拟执行整个元老院阶段（简化，只调用否决和执行部分）
    tribune = cmd._get_tribune()
    new_governors = []
    for gov in cmd.proposed_governors:
        issue = {'type': 'governor_appointment', 'province_id': gov['province_id'],
                 'new_governor_id': gov['new_governor_id'], 'old_governor_id': gov['old_governor_id']}
        if cmd.veto_decider.decide_veto(issue, tribune.id, state):
            print(f"否决 province {gov['province_id']}")
        else:
            new_governors.append(gov)
    cmd.proposed_governors = new_governors

    # 执行任命
    cmd._execute_governor_appointments()

    # 验证被否决的行省（ID1）没有候任总督
    sicily = state.get_province(1)
    assert sicily.governor_designate_id is None

    # 验证其他行省有候任总督且旧总督仍在任
    for gov in new_governors:
        prov = state.get_province(gov['province_id'])
        assert prov.governor_id == gov['old_governor_id']  # 旧总督仍在任
        assert prov.governor_designate_id == gov['new_governor_id']  # 候任总督已设置
        new_fig = state.get_member(gov['new_governor_id'])
        assert new_fig.is_absent is True
        assert prov._old_governor_id == gov['old_governor_id']

def test_governor_return_in_resolution(state, provinces, figures):
    """测试决算阶段旧总督返回"""
    from src.ui.commands.phase_resolution import ResolutionCommand

    # 先执行一次任命（无否决）
    cmd = SenateCommand(state)
    # 移除保民官
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True
    cmd._process_governor_appointments(None)
    cmd._execute_governor_appointments()

    # 记录旧总督
    old_ids = [p['old_governor_id'] for p in cmd.proposed_governors]
    # 检查旧总督记录在 province._old_governor_id
    for p in cmd.proposed_governors:
        prov = state.get_province(p['province_id'])
        assert prov._old_governor_id == p['old_governor_id']

    # 模拟决算阶段
    res_cmd = ResolutionCommand(state)
    # 调用返回方法
    res_cmd._process_governor_return()

    # 验证旧总督回到罗马
    for oid in old_ids:
        if oid:
            old_fig = state.get_member(oid)
            assert old_fig.is_absent is False
    # 验证 province._old_governor_id 已清空
    for prov in state.get_all_provinces():
        assert prov._old_governor_id is None

def test_no_candidates_for_propreator(state, provinces, figures):
    """测试大法官候选人不足时，剩余行省留任原总督"""
    # 将两个大法官标记死亡（通过 state.get_member 获取人物对象）
    for fig_id in [203, 204]:
        fig = state.get_member(fig_id)
        if fig:
            fig.is_dead = True

    cmd = SenateCommand(state)
    # 移除保民官
    for fig in state.get_living_members():
        if fig.office == "tribune":
            fig.is_dead = True

    cmd._process_governor_appointments(None)

    # 大法官行省应无任命（候选人不足）
    prop_assignments = [gov for gov in cmd.proposed_governors if gov['governor_type'] == 'propraetor']
    assert len(prop_assignments) == 0

    # 执行任命（不会改变任何大法官行省）
    cmd._execute_governor_appointments()
    # 检查原总督仍为原值
    for pid in [2, 3]:
        prov = state.get_province(pid)
        assert prov.governor_id in (102, 103)   # 原总督