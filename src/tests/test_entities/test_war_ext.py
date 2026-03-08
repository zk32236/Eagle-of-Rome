# src/tests/test_entities/test_war_ext.py
import pytest
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.game_state import GameState


def test_war_new_fields_defaults():
    """测试 War 新增字段默认值"""
    war = War(id="test", name="Test")
    assert war.naval_required is False
    assert war.enemy_naval_current == 0
    assert war.assigned_fleet_ids == []
    assert war.sea_zone_id is None
    assert war.unanswered_turns == 0
    assert war.indemnity_schedule == []
    assert war.sea_control_ratio == 1.0
    assert war.rebellion_province_id is None

def test_war_new_fields_assignment():
    """测试 War 新增字段赋值"""
    war = War(id="test", name="Test")
    war._naval_required = True
    war._enemy_naval_current = 10
    war.assign_fleet(101)
    war.assign_fleet(102)
    war._sea_zone_id = 5
    war.increment_unanswered_turns()
    war.increment_unanswered_turns()
    war.set_indemnity_schedule([(100, 3), (50, 2)])
    war._sea_control_ratio = 0.7
    war._rebellion_province_id = 2

    assert war.naval_required is True
    assert war.enemy_naval_current == 10
    assert war.assigned_fleet_ids == [101, 102]
    assert war.sea_zone_id == 5
    assert war.unanswered_turns == 2
    assert war.indemnity_schedule == [(100, 3), (50, 2)]
    assert war.sea_control_ratio == 0.7
    assert war.rebellion_province_id == 2

def test_war_assign_remove_fleet():
    """测试 assign_fleet 和 remove_fleet 方法"""
    war = War(id="test", name="Test")
    war.assign_fleet(1)
    war.assign_fleet(2)
    assert war.assigned_fleet_ids == [1, 2]
    war.remove_fleet(1)
    assert war.assigned_fleet_ids == [2]
    # 移除不存在的 ID 不应报错
    war.remove_fleet(999)
    assert war.assigned_fleet_ids == [2]

def test_war_unanswered_turns():
    """测试 increment_unanswered_turns 和 reset_unanswered_turns"""
    war = War(id="test", name="Test")
    assert war.unanswered_turns == 0
    war.increment_unanswered_turns()
    assert war.unanswered_turns == 1
    war.increment_unanswered_turns()
    assert war.unanswered_turns == 2
    war.reset_unanswered_turns()
    assert war.unanswered_turns == 0

def test_war_to_dict_includes_new_fields():
    """测试 to_dict 包含新增字段"""
    war = War(id="test", name="Test")
    war._naval_required = True
    war._enemy_naval_current = 5
    war.assign_fleet(10)
    war._sea_zone_id = 3
    war._unanswered_turns = 2
    war.set_indemnity_schedule([(200, 4)])
    war._sea_control_ratio = 0.8
    war._rebellion_province_id = 1

    d = war.to_dict()
    assert d["_naval_required"] is True
    assert d["_enemy_naval_current"] == 5
    assert d["_assigned_fleet_ids"] == [10]
    assert d["_sea_zone_id"] == 3
    assert d["_unanswered_turns"] == 2
    assert d["_indemnity_schedule"] == [(200, 4)]
    assert d["_sea_control_ratio"] == 0.8
    assert d["_rebellion_province_id"] == 1

def test_war_from_dict_restores_new_fields():
    """测试 from_dict 能恢复新增字段"""
    original = War(id="test", name="Test")
    original._naval_required = True
    original._enemy_naval_current = 8
    original.assign_fleet(20)
    original._sea_zone_id = 2
    original._unanswered_turns = 1
    original.set_indemnity_schedule([(150, 2)])
    original._sea_control_ratio = 0.9
    original._rebellion_province_id = 3

    d = original.to_dict()
    reconstructed = War.from_dict(d)

    assert reconstructed.naval_required == original.naval_required
    assert reconstructed.enemy_naval_current == original.enemy_naval_current
    assert reconstructed.assigned_fleet_ids == original.assigned_fleet_ids
    assert reconstructed.sea_zone_id == original.sea_zone_id
    assert reconstructed.unanswered_turns == original.unanswered_turns
    assert reconstructed.indemnity_schedule == original.indemnity_schedule
    assert reconstructed.sea_control_ratio == original.sea_control_ratio
    assert reconstructed.rebellion_province_id == original.rebellion_province_id

def test_war_status_truce():
    """验证 WarStatus 中有 TRUCE"""
    assert hasattr(WarStatus, 'TRUCE')
    assert WarStatus.TRUCE.value is not None

def test_war_assign_commander():
    war = War(id='test', name='Test')
    war.assign_commander(101, 5)
    assert war.commander_id == 101
    assert war.legions_assigned == 5

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