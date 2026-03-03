# src/tests/test_entities/test_war_ext.py
import pytest
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.game_state import GameState

def test_war_status_truce():
    """验证 WarStatus 中有 TRUCE"""
    assert hasattr(WarStatus, 'TRUCE')
    assert WarStatus.TRUCE.value is not None

def test_war_assign_commander():
    war = War(id='test', name='Test')
    war.assign_commander(101, 5)
    assert war.commander_id == 101
    assert war.commander_assigned_turn == 5

def test_war_peace_treaty():
    war = War(id='test', name='Test')
    treaty = {'indemnity': 100, 'duration': 5, 'generated_turn': 10}
    war.set_peace_treaty(treaty)
    assert war.peace_treaty == treaty
    assert war.peace_treaty['status'] == 'pending'  # 自动添加

    war.clear_peace_treaty()
    assert war.peace_treaty is None

def test_war_indemnity():
    war = War(id='test', name='Test')
    war.set_indemnity_due(-50)
    assert war.indemnity_due == -50

def test_war_truce_end():
    war = War(id='test', name='Test')
    war.set_truce_end_turn(15)
    assert war.truce_end_turn == 15
    assert war.is_truce_expired(14) is False
    assert war.is_truce_expired(15) is True

def test_war_original_commander():
    war = War(id='test', name='Test')
    war.set_original_commander(202, 8)
    assert war.original_commander_id == 202
    assert war.commander_assigned_turn == 8

def test_war_system_truce_lists():
    state = GameState.create_for_testing({})
    ws = WarSystem(state)
    war = War(id='w1', name='War1')
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)

    # 移到 TRUCE
    assert ws._move_to_truce(war) is True
    assert war in ws._truce_wars
    assert war not in ws._active_wars
    assert war.status == WarStatus.TRUCE

    # 移回 ACTIVE
    assert ws._move_to_active(war) is True
    assert war in ws._active_wars
    assert war not in ws._truce_wars
    assert war.status == WarStatus.ACTIVE

    # 再移到 TRUCE
    ws._move_to_truce(war)
    # 移到 THREAT
    assert ws._move_to_threat(war, threat_level=2) is True
    assert war in ws._threats
    assert war not in ws._truce_wars
    assert war.status == WarStatus.THREAT
    assert war.threat_level == 2

def test_war_system_query_methods():
    state = GameState.create_for_testing({})
    ws = WarSystem(state)
    w1 = War(id='w1', name='W1')
    w2 = War(id='w2', name='W2')
    w3 = War(id='w3', name='W3')

    # 设置不同的草案状态
    w1.set_peace_treaty({'indemnity':10, 'duration':3, 'generated_turn':5})  # pending 自动
    w2.set_peace_treaty({'indemnity':20, 'duration':4, 'generated_turn':5})
    w2._peace_treaty['status'] = 'approved'
    w3.set_peace_treaty({'indemnity':30, 'duration':5, 'generated_turn':5})
    w3._peace_treaty['status'] = 'approved'

    ws._truce_wars = [w1, w2, w3]

    pending = ws.get_truce_wars_with_pending_treaty()
    assert len(pending) == 1
    assert pending[0].id == 'w1'

    approved = ws.get_truce_wars_with_approved_treaty()
    assert len(approved) == 2
    assert {w.id for w in approved} == {'w2', 'w3'}