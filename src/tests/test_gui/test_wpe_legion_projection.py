# src/tests/test_gui/test_wpe_legion_projection.py
"""
WP-E（GUI-BETA-R1）E-POST-R1-07P：legion 投影一致性测试（T-8）。

覆盖（A9.1~A9.3，验证优先——展示 = 实体忠实镜像；Attempt-2 按 ODR-A/B 改实时实体派生）：
- 07P-01：`_war_card` DTO 计数/番号 = 实时军团实体附着派生
  （len(get_legions_for_battle(war.id))，即 legion.war_id == war.id；ODR-A 展示侧投影修正）
- 07P-02：TRUCE 卡忠实——附着实体存在时如实显示（ODR-B ③）；
  召回后（实体 war_id=None）卡不显旧番号（守卫数据源 = 实时实体，
  禁以 war.legion_numbers 列表本身判定存在性，ODR-B ①）
- DEVIATION-DA-01（PM 已 ENDORSED，2026-08-25）：fixtures 改生产路径
  （MilitarySystem(state) + recruit_legion + assign_to_war），镜像语义
  = len(get_legions_for_battle(war.id))；断言意图保留（禁空洞化）
- TRUCE 到期重征正向路径（ODR-B ②）：指派旧号→召回→卡空→到期→重指派新号→[新号] 非空非旧
- re-entry：同一状态重复构建 DTO → 一致
- 实体本身 0 → 底层状态 0（非投影 bug）；投影链无中间丢失
"""
import os
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api


def _make_state_with_war(turn_number=5, status=WarStatus.ACTIVE):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=-260)
    ws = WarSystem(state)
    state._war_system = ws
    state._military_system = MilitarySystem(state)
    state.treasury = 1000  # 生产路径 recruit_legion 需国库 ≥ 征召费用（默认 10）
    war = War(id="w1", name="Test War", start_year=-270, threat_level=5, strength=5)
    war.status = status
    if status == WarStatus.ACTIVE:
        ws._active_wars.append(war)
    elif status == WarStatus.TRUCE:
        ws._truce_wars.append(war)
    return state, ws, war


def _attach_legions(state, war, numbers, commander_id=99):
    """生产路径附着：MilitarySystem.recruit_legion + assign_to_war（实体 war_id 附着）。"""
    ms = state.get_military_system()
    for num in numbers:
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num} failed"
    assigned, _ = ms.assign_to_war(list(numbers), war.id, commander_id)
    assert assigned == len(numbers)
    return ms


def _mirror(state, war):
    """实时实体镜像（DEVIATION-DA-01 冻结语义）：len(get_legions_for_battle(war.id))。"""
    ms = state.get_military_system()
    attached = ms.get_legions_for_battle(war.id) if ms else []
    return len(attached), [legion.number for legion in attached]


# ---------------------------------------------------------------------------
# 1. 07P-01：DTO = 实时军团实体镜像（计数/番号 = len(get_legions_for_battle(war.id))）
# ---------------------------------------------------------------------------

def test_war_card_mirrors_entity_legions():
    """_war_card legion_count/legion_numbers = 实时军团实体附着镜像（生产路径附着）。"""
    state, ws, war = _make_state_with_war()
    _attach_legions(state, war, (1, 2, 3))

    card = combat_api._war_card(war, state)
    count, numbers = _mirror(state, war)

    assert count == 3
    assert card["legion_count"] == count == 3
    assert card["legion_numbers"] == numbers == [1, 2, 3]


def test_war_card_mirrors_zero_legions():
    """无附着军团实体 → DTO 0（权威状态本身为 0，展示一致）。"""
    state, ws, war = _make_state_with_war()

    card = combat_api._war_card(war, state)
    assert card["legion_count"] == 0
    assert card["legion_numbers"] == []


# ---------------------------------------------------------------------------
# 2. 07P-02：TRUCE 卡忠实（附着存在如实显示；召回后守卫隐藏——ODR-B）
# ---------------------------------------------------------------------------

def test_truce_card_preserves_legion_projection():
    """TRUCE 卡附着实体存在 → 如实显示（ODR-B ③：守卫仅在确无附着时隐藏）。"""
    state, ws, war = _make_state_with_war(status=WarStatus.TRUCE)
    _attach_legions(state, war, (1, 2, 3, 4))

    card = combat_api._war_card(war, state)
    count, numbers = _mirror(state, war)
    assert count == 4
    assert card["legion_count"] == count == 4
    assert card["legion_numbers"] == numbers == [1, 2, 3, 4]
    # TRUCE 卡 DTO 新增字段（Slice 7）
    assert "truce_remaining_turns" in card


def test_truce_moves_to_disband_queue_then_clear():
    """G3C 和约批准路径（ODR-CAND-01 方向①）：入解散队列后**立即 clear** war.legion_numbers。"""
    from src.core.systems.political_system import PoliticalSystem

    state, ws, war = _make_state_with_war(status=WarStatus.ACTIVE)
    _attach_legions(state, war, (1, 2))

    # 进入 TRUCE + submitted 条约 → canonical 批准路径（对齐 execute_passed_peace_treaty）
    ws._active_wars.remove(war)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "submitted", "indemnity": 10, "duration": 3, "generated_turn": 1})
    ws._truce_wars.append(war)
    state.turn = None
    from src.core.entities.entities import GameTurn
    state.turn = GameTurn(turn_number=1, year=-264)
    PoliticalSystem(state).execute_passed_peace_treaty(war)

    # enqueue-then-clear（ODR-CAND-01 方向①）：队列入队 + war.legion_numbers 立即清空
    assert sorted(ws._legions_to_disband) == [1, 2]
    assert war.legion_numbers == []


# ---------------------------------------------------------------------------
# 3. re-entry 收敛（真实断言，禁空洞化——DEVIATION-DA-01 条件③）
# ---------------------------------------------------------------------------

def test_war_card_reentry_stable():
    """同一状态重复构建 DTO → 一致，且值真实（非双 0 空洞相等）。"""
    state, ws, war = _make_state_with_war()
    _attach_legions(state, war, (1, 2))

    card1 = combat_api._war_card(war, state)
    card2 = combat_api._war_card(war, state)
    assert card1["legion_count"] == 2
    assert card1["legion_numbers"] == [1, 2]
    assert card1["legion_count"] == card2["legion_count"] == 2
    assert card1["legion_numbers"] == card2["legion_numbers"] == [1, 2]
    assert card1["total_power"] == card2["total_power"]
    # 无指挥官 → commander_martial=0；total_power = 0 + 2*2 = 4（实体派生）
    assert card1["total_power"] == 4


# ---------------------------------------------------------------------------
# 4. mobilized=0 案例复验（分类判定：投影链无中间丢失）
# ---------------------------------------------------------------------------

def test_mobilized_zero_projection_classification():
    """mobilized=0 案例：无附着实体 → 展示 0；生产路径附着后 → 展示实体数（投影忠实）。

    本用例证明投影链无中间丢失：DTO 是实时实体状态的纯函数。
    """
    state, ws, war = _make_state_with_war()
    card = combat_api._war_card(war, state)
    # 投影链：实时实体 → DTO 派生 → 展示（QML 直读 DTO legion_numbers）
    assert card["legion_count"] == 0
    assert card["legion_numbers"] == []

    # 生产路径权威征召+指派（实体附着）→ DTO 必然反映
    _attach_legions(state, war, (1, 2, 3, 4, 5))
    card2 = combat_api._war_card(war, state)
    count, numbers = _mirror(state, war)
    assert count == 5
    assert card2["legion_count"] == count == 5
    assert card2["legion_numbers"] == numbers == [1, 2, 3, 4, 5]
    # 结论：投影忠实；「实体>0 展示 0」在本链中不可能（无中间变换）——无 WP-E 修正需求；
    # 若未来出现展示 0，真因必在实体写入路径（WP-G 生命周期），traceability 已记录。


# ---------------------------------------------------------------------------
# 5. ODR-B ②：TRUCE 到期重征/重指派正向路径（卡面 = 新番号，非空非旧）
# ---------------------------------------------------------------------------

def test_truce_expiry_reassign_shows_new_numbers():
    """ODR-B ②（Owner 硬要求）：和约召回 → 卡空 → 到期 → 重指派新号 → 卡面 = [新号] 非空非旧。

    守卫数据源 = 实时军团实体附着（legion.war_id == war.id），禁以 war.legion_numbers
    列表本身判定存在性（ODR-B ①）——残留旧号列表被 DTO 忽略，新指派如实显示。
    """
    state, ws, war = _make_state_with_war(status=WarStatus.ACTIVE)
    ms = _attach_legions(state, war, (1, 2))  # 指派旧号
    assert combat_api._war_card(war, state)["legion_numbers"] == [1, 2]  # 附着存在 → 如实显示

    # 和约批准 → TRUCE + 召回（真实 recall 路径：实体 war_id=None；此处模拟召回后形态）
    ws._active_wars.remove(war)
    war.status = WarStatus.TRUCE
    ws._truce_wars.append(war)
    recalled = ms.recall_from_war(war.id)
    assert recalled == 2
    # 手动召回模拟（非 canonical 批准路径）：war.legion_numbers 保留，验证 DTO 守卫
    assert war.legion_numbers == [1, 2]
    # ODR-B 守卫：无附着实体 → 卡不显旧番号
    assert combat_api._war_card(war, state)["legion_numbers"] == []

    # TRUCE 战争再起（G3C：到期 → THREAT 后由 escalate/activate 回 ACTIVE；此处手动容器
    # 迁移仅模拟 re-escalation 场景，验证 DTO 投影忠实——卡面数据源 = 实时实体）
    ws._truce_wars.remove(war)
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)

    # 重指派新号（新鲜征召 = 生产路径 recruit_legion + assign_to_war）
    _attach_legions(state, war, (7, 8))
    card = combat_api._war_card(war, state)
    assert card["legion_numbers"] == [7, 8]  # 非空非旧
    assert 1 not in card["legion_numbers"]
    assert 2 not in card["legion_numbers"]
    assert card["legion_count"] == 2
    assert card["total_power"] == 4  # 0 (martial) + 2*2
    # 残留列表含旧号+新号（不清空），但 DTO 只读实时实体 —— 守卫正确性核心
    assert war.legion_numbers == [1, 2, 7, 8]


# ---------------------------------------------------------------------------
# 6. traceability 文件存在性
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
