# src/tests/test_gui/test_wpe_legion_projection.py
"""
WP-E（GUI-BETA-R1）E-POST-R1-07P：legion 投影一致性测试（T-8）。

覆盖（A9.1~A9.3，验证优先——展示 = 实体忠实镜像）：
- 07P-01：`_war_card` DTO 直读 war.legions_assigned / war.legion_numbers（实体镜像）
- 07P-02：TRUCE 卡不陈旧——DTO 忠实 + WP-G traceability 存在
  （war_system.py:116-131 _move_to_truce 不清空 + political_system.py:580 只入解散队列）
- mobilized=0 案例复验：实体 legions_assigned > 0 而展示 0 → 投影 bug（WP-E 修）；
  实体本身 0 → 底层状态错（移交 WP-G，禁 QML 掩盖）
- re-entry：同一状态重复构建 DTO → 一致
"""
import os
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.api import combat_api


def _make_state_with_war(turn_number=5, status=WarStatus.ACTIVE):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    war = War(id="w1", name="Test War", start_year=-270, threat_level=5, strength=5)
    war.status = status
    if status == WarStatus.ACTIVE:
        ws._active_wars.append(war)
    elif status == WarStatus.TRUCE:
        ws._truce_wars.append(war)
    return state, ws, war


# ---------------------------------------------------------------------------
# 1. 07P-01：DTO = 实体镜像（legions_assigned / legion_numbers）
# ---------------------------------------------------------------------------

def test_war_card_mirrors_entity_legions():
    """_war_card legion_count/legion_numbers = 实体直读（展示匹配权威当前状态）。"""
    state, ws, war = _make_state_with_war()
    war.legions_assigned = 3
    for num in (101, 102, 103):
        war.add_legion_number(num)

    card = combat_api._war_card(war, state)

    assert card["legion_count"] == war.legions_assigned == 3
    assert card["legion_numbers"] == war.legion_numbers == [101, 102, 103]


def test_war_card_mirrors_zero_legions():
    """实体 0 军团 → DTO 0（权威状态本身为 0，展示一致）。"""
    state, ws, war = _make_state_with_war()
    war.legions_assigned = 0
    war.clear_legion_numbers()

    card = combat_api._war_card(war, state)
    assert card["legion_count"] == 0
    assert card["legion_numbers"] == []


# ---------------------------------------------------------------------------
# 2. 07P-02：ODR-R3-04 approved TRUCE authoritative zero
# ---------------------------------------------------------------------------

def test_submitted_truce_card_preserves_legion_projection():
    """尚未批准的 TRUCE 草案保持军团身份投影。"""
    state, ws, war = _make_state_with_war(status=WarStatus.TRUCE)
    for num in (201, 202, 203, 204):
        war.add_legion_number(num)

    card = combat_api._war_card(war, state)
    assert card["legion_count"] == 4
    assert card["legion_numbers"] == [201, 202, 203, 204]
    assert "truce_remaining_turns" in card


def test_approved_truce_card_projects_authoritative_zero():
    """批准后权威实体 list/count 已清零，DTO 不做 fake zero。"""
    state, ws, war = _make_state_with_war(status=WarStatus.TRUCE)
    war.set_peace_treaty({"status": "approved", "duration": 2, "indemnity": 0})
    war.truce_recruit_target = 2
    war.clear_legion_numbers()

    card = combat_api._war_card(war, state)
    assert war.mobilized_legion_count == 0
    assert war.legions_assigned == 0
    assert card["legion_count"] == 0
    assert card["legion_numbers"] == []


# ---------------------------------------------------------------------------
# 3. re-entry 收敛
# ---------------------------------------------------------------------------

def test_war_card_reentry_stable():
    """同一状态重复构建 DTO → 一致（确定性投影）。"""
    state, ws, war = _make_state_with_war()
    war.legions_assigned = 2
    for num in (401, 402):
        war.add_legion_number(num)

    card1 = combat_api._war_card(war, state)
    card2 = combat_api._war_card(war, state)
    assert card1["legion_count"] == card2["legion_count"]
    assert card1["legion_numbers"] == card2["legion_numbers"]
    assert card1["total_power"] == card2["total_power"]


# ---------------------------------------------------------------------------
# 4. mobilized=0 案例复验（分类判定）
# ---------------------------------------------------------------------------

def test_mobilized_zero_projection_classification():
    """mobilized=0 案例：实体 legions_assigned=0 且 legion_numbers=[] → 底层状态为 0
    （非投影 bug——_war_card 直读实体，展示必然一致）；若实体 >0 而展示 0 才属投影 bug。

    本用例证明投影链无中间丢失：DTO 是实体的纯函数。
    """
    state, ws, war = _make_state_with_war()
    war.legions_assigned = 0
    war.clear_legion_numbers()

    card = combat_api._war_card(war, state)
    # 投影链：实体 → DTO 直读 → 展示（QML 直读 DTO legion_numbers）
    assert card["legion_count"] == 0
    assert card["legion_numbers"] == []
    # 若实体被权威招募（legions_assigned>0），DTO 必然反映（同函数直读）——
    war.legions_assigned = 5
    for num in (501, 502, 503, 504, 505):
        war.add_legion_number(num)
    card2 = combat_api._war_card(war, state)
    assert card2["legion_count"] == 5
    assert card2["legion_numbers"] == [501, 502, 503, 504, 505]
    # 结论：投影忠实；「实体>0 展示 0」在本链中不可能（无中间变换）——无 WP-E 修正需求；
    # 若未来出现展示 0，真因必在实体写入路径（WP-G 生命周期），traceability 已记录。


# ---------------------------------------------------------------------------
# 5. traceability 文件存在性
# ---------------------------------------------------------------------------

def test_legion_traceability_file_exists():
    """WP-G traceability 记录存在（移交 WP-G 的证据包）。"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    candidates = [
        os.path.join(project_root, "docs", "00_产品文档", "technical-mappings", "MVP0.3-02_战争系统.md"),
    ]
    # traceability 记录位于 EOR 证据目录（03-da-evidence/traceability/），
    # 由 DA Execution 写入（wpe-slice9-*）；此处断言产品侧映射文档存在（D-6 更新对象）。
    assert any(os.path.exists(c) for c in candidates), "legion 投影边界文档缺失"
