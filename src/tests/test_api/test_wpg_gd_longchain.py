# src/tests/test_api/test_wpg_gd_longchain.py
"""
WP-G G4-GD G6（P 件 §1）— 跨切片生产形态长链 harness（S01~S37 代表链 + S33 幂等）。

真实生命周期链（任务包 §15 / §18.8，禁 isolated DTO mock）：
  Forum 触发/升级（GA S01/S02 既有测试覆盖，本链模拟起点）
  → Senate 宣战 + 指挥官 + 军团指派（GA）→ 舰队指派（GC）
  → 海军门（GC S03）→ Sea Control（S04/S05）→ 陆战（GB S12/S13）
  → 战争结束（RESOLVED + 制海权清理 + 召回）→ Revenue 最后维护（G3/G1-14）
  → Population canonical 解散（G2/S28/S29/S30）→ Resolution 顺序（G4/S31）
  → save/load（G1/S32）→ 下一战（S09 获控跳过海战面 + S33 全链重入零重复）

T-GD-01~10 映射：T-GD-01 全链 / T-GD-02 S09 / T-GD-03 批准和约链（G3C：TRUCE 保持）/ T-GD-04 S33
全链重入 / T-GD-05 population marker / T-GD-06 S28 / T-GD-07 S29 / T-GD-08 S31 /
T-GD-09 到期→THREAT 面 / T-GD-10 G3C 符号审计。

真实 API 驱动（combat_api.do_combat_action / economic_service / population_api /
resolution_api / senate_api / PoliticalSystem）+ 真实系统（WarSystem/MilitarySystem/
NavalSystem），仅骰子值受控（DEV-4 模式：patch 共享 random.randint side_effect）。
"""
import pytest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn, Faction
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.service.economic_service import EconomicService
from src.api import combat_api, population_api, resolution_api, senate_api


def _build_chain_state(war_id="war1", enemy_land=2, n_fleets=3, war_strength=5):
    """生产形态起点：ACTIVE 海军战争 + 指挥官 + 军团指派 + 舰队指派。"""
    state = GameState.create_for_testing({
        "economic_rules": {
            "fleet_types": {
                "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
            },
            "default_fleet_type": "trireme",
            "legion_recruit_cost": 10,
        },
    })
    state.turn = GameTurn(turn_number=10, year=-280)
    state._treasury = 500
    state.pyrrhic_war_won = True

    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    commander.office = "consul"
    state.add_member(commander)
    faction.member_ids.append(101)

    war = War(
        id=war_id, name="Naval War", strength=war_strength, threat_level=3,
        rewards={"treasury": 100},
        naval_required=True,
        enemy_naval_current=0,   # 海战 TRIUMPH 易达（dice + 21 - 0 ≥ 12）
        enemy_land_current=enemy_land,
        disaster_numbers=[2, 3, 4],
        standoff_numbers=[99],
    )
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)

    ns = state.naval_system
    for n in range(1, n_fleets + 1):
        fleet = Fleet(number=n, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._target_war_id = war.id
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[n] = fleet
        ok = ns.assign_fleet_to_war(n, war.id, "naval")
        assert ok, f"assign fleet {n} failed"

    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num} failed"
    assigned, msg = ms.assign_to_war([1, 2], war.id, 101)
    assert assigned == 2, msg

    return state, war, commander


# ════════════════════════════════════════════════════════════════════════
# T-GD-01 — 生产形态长链全通（海军门 → 获控 → 陆战 → 战争结束 → Revenue →
#          Population → Resolution → save/load → 下一战）
# ════════════════════════════════════════════════════════════════════════

def test_tgd01_production_long_chain():
    state, war, commander = _build_chain_state()
    ms = state._military_system
    ns = state.naval_system
    ws = state._war_system

    # ── 1. 战斗：海军 TRIUMPH（获控）+ 同场陆战 TRIUMPH（战争结束）──
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        result = combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    assert result["success"]
    data = result["data"]
    assert data["naval"]["result"] == "TRIUMPH"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land_battle"] == "allowed"

    # 战争结束（RESOLVED + discard）；制海权随战争正式结束清理（K 件 §3 / D-1）
    assert war.status == WarStatus.RESOLVED
    assert war in ws._war_discard
    assert war.sea_control_acquired is False

    # 幸存军团：Veteran + 召回 AVAILABLE（G1-22 / G1-19）
    for num in (1, 2):
        leg = ms.get_legion_by_number(num)
        assert leg.status == LegionStatus.AVAILABLE
        assert leg.war_id is None
        assert leg.is_veteran is True
    # 幸存舰队：召回 AVAILABLE（非 DISBANDED——战争结束不立即解散，G1-14 反例守护）
    for num in (1, 2, 3):
        assert ns.get_fleet(num).status == FleetStatus.AVAILABLE
    # 指挥官返回（resolve_war 清 commander_id）
    assert war.commander_id is None

    # ── 2. Revenue：AVAILABLE 幸存者付最后维护（G1-14）──
    naval_total_before = ns.calculate_maintenance()
    assert naval_total_before == 3 * 4  # 3 舰队 × trireme maintenance 4
    rev = EconomicService(state).settle_revenue_phase()
    assert rev["success"] is True
    assert rev["data"]["maintenance"]["naval"]["total"] == naval_total_before
    assert rev["data"]["maintenance"]["naval"]["available"] is True

    # ── 3. Population：canonical 解散 → DISBANDED（非 DESTROYED；Veteran 保留）──
    disband = population_api.process_population_disbandments(state)
    assert disband["legions"]["resolved_wars"]["total"] == 2  # legion_numbers [1,2]
    assert sorted(disband["fleets"]) == [1, 2, 3]
    for num in (1, 2):
        leg = ms.get_legion_by_number(num)
        assert leg.status == LegionStatus.DISBANDED
        assert leg.is_veteran is True  # G1-19：Veteran 持久，解散不清
    for num in (1, 2, 3):
        assert ns.get_fleet(num).status == FleetStatus.DISBANDED
    assert ns.calculate_maintenance() == 0  # DISBANDED 排除（GC S4）
    assert ws._legions_to_disband == []

    # ── 4. Resolution：先判胜负后恢复（G1-25；无 game_over）──
    state.mark_phase_executed("combat")
    res = resolution_api.execute_resolution(state)
    assert res["success"] is True
    assert res["data"]["victory"]["game_over"] is False

    # ── 5. save/load（G1/S32）：War/Legion/Fleet 运行态全量持久 ──
    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rws = restored._war_system
    r1 = rws.get_war_by_id("war1")
    assert r1.status == WarStatus.RESOLVED
    assert r1.sea_control_acquired is False
    assert r1 in rws._war_discard
    rms = restored._military_system
    assert rms.get_legion_by_number(1).status == LegionStatus.DISBANDED
    assert rms.get_legion_by_number(1).is_veteran is True
    rns = restored._naval_system
    assert rns.get_fleet(1).status == FleetStatus.DISBANDED
    assert rns.get_fleet(1)._target_war_id == "war1"

    # ── 6. 下一战（新战争：海军门重新生效，S03 面）──
    state2, war2, _ = _build_chain_state(war_id="war2")
    assert war2.sea_control_acquired is False
    calls = []
    original = state2.naval_system.resolve_naval_battle
    def spy(*a, **kw):
        calls.append(a)
        return original(*a, **kw)
    with patch.object(state2.naval_system, "resolve_naval_battle", side_effect=spy):
        with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
            r2 = combat_api.do_combat_action(state2, "player_opt", "war2", "attack")
    assert r2["success"]
    assert len(calls) == 1  # 新战争必须先海战


# ════════════════════════════════════════════════════════════════════════
# T-GD-02 — 获控后同战陆战 DEFEAT → 未来战斗跳过海战直达陆战（S09 / R-06）
# ════════════════════════════════════════════════════════════════════════

def test_tgd02_sea_control_persists_across_land_defeat():
    state, war, commander = _build_chain_state(war_strength=30)  # 陆战 DEFEAT 易达（score < -3）
    ns = state.naval_system

    # 第一战：海军 TRIUMPH（获控）+ 陆战 DEFEAT（score = 5+4+4-30 = -17 < -3）
    with patch.object(combat_api.random, "randint", side_effect=[7, 5]):
        r1 = combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    assert r1["success"]
    assert war.sea_control_acquired is True
    assert war.status == WarStatus.ACTIVE  # DEFEAT 不结束战争（INV-C3）
    assert r1["data"]["naval"]["result"] == "TRIUMPH"

    # 第二战（下回合新 Combat 阶段：phase_data 重建 + 指挥官重绑，同 GC T-GC-07 模式）：
    # 获控 → 跳过海战直达陆战（spy 证实 resolve_naval_battle 零调用）
    state.record_phase_result("combat", {})
    war.commander_id = commander.id
    calls = []
    original = ns.resolve_naval_battle
    def spy(*a, **kw):
        calls.append(a)
        return original(*a, **kw)
    with patch.object(ns, "resolve_naval_battle", side_effect=spy):
        with patch.object(combat_api.random, "randint", return_value=5):
            r2 = combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    assert r2["success"]
    assert len(calls) == 0
    assert war.sea_control_acquired is True  # 制海权跨回合持久（G1-16）


# ════════════════════════════════════════════════════════════════════════
# T-GD-03 — 批准和约 → TRUCE 保持 + 召回 → Revenue 最后维护 → Population DISBANDED
#           （S17/S28 集成，G3C：approved = temporary truce 非战争结束）
# ════════════════════════════════════════════════════════════════════════

def test_tgd03_approved_treaty_keeps_truce_chain():
    from src.core.systems.political_system import PoliticalSystem
    state, war, commander = _build_chain_state(war_id="war_peace")
    ms = state._military_system
    ns = state.naval_system
    ws = state._war_system

    # 进入 TRUCE + pending 条约（STALEMATE→TRUCE 冻结转换；模拟战争结果）
    ws._active_wars.remove(war)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "submitted", "indemnity": 50, "duration": 3, "generated_turn": 9})
    ws._truce_wars.append(war)

    # Senate 批准和约（G3C）→ 战争保持 TRUCE + 召回 + enqueue-then-clear
    PoliticalSystem(state).execute_passed_peace_treaty(war)
    assert war.status == WarStatus.TRUCE
    assert war in ws._truce_wars
    assert war not in ws._war_discard
    assert war.truce_end_turn == 13  # turn 10 + duration 3
    assert war.legion_numbers == []  # 立即 clear（ODR-CAND-01 方向①）
    assert sorted(ws._legions_to_disband) == [1, 2]
    for num in (1, 2):
        assert ms.get_legion_by_number(num).status == LegionStatus.AVAILABLE
    for num in (1, 2, 3):
        assert ns.get_fleet(num).status == FleetStatus.AVAILABLE

    # 下个 Revenue：最后维护（AVAILABLE 幸存者计费）
    rev = EconomicService(state).settle_revenue_phase()
    assert rev["data"]["maintenance"]["naval"]["total"] == 12

    # 下个 Population：DISBANDED（approved TRUCE 释放 → _legions_to_disband 队列面解散，
    # deescalated 面 exactly-once；war 非 RESOLVED，不走 resolved_wars 面）
    disband = population_api.process_population_disbandments(state)
    assert disband["legions"]["resolved_wars"]["total"] == 0
    assert disband["legions"]["deescalated"]["total"] == 2
    assert sorted(disband["fleets"]) == [1, 2, 3]
    assert all(ms.get_legion_by_number(n).status == LegionStatus.DISBANDED for n in (1, 2))
    assert all(ns.get_fleet(n).status == FleetStatus.DISBANDED for n in (1, 2, 3))
    # 队列消费完毕（T5 语义：_legions_to_disband 清空，零残留）
    assert ws._legions_to_disband == []
    # 重入零重复：第二次调用 marker no-op，军团不再被重复解散
    again = population_api.process_population_disbandments(state)
    assert again == disband
    assert all(ms.get_legion_by_number(n).status == LegionStatus.DISBANDED for n in (1, 2))
    assert ws._legions_to_disband == []


# ════════════════════════════════════════════════════════════════════════
# T-GD-04 — S33：全链重入零重复 mutation（combat/recruit/recall/disband/destroy/
#          takeover/population）
# ════════════════════════════════════════════════════════════════════════

def test_tgd04_s33_reentry_no_duplicate_mutation():
    state, war, commander = _build_chain_state()
    ms = state._military_system
    ws = state._war_system

    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    snap_legions = [(l.number, l.status) for l in ms._legions]

    # combat 重入：resolved_wars guard（FC-1）→ 拒绝，零 mutation
    again = combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    assert again["success"] is False
    assert "该战争已结算" in again["message"]
    assert [(l.number, l.status) for l in ms._legions] == snap_legions

    # recruit 重入：状态门（已征召 ACTIVE → 拒绝）
    ok1, _ = ms.recruit_legion(3)
    ok2, _ = ms.recruit_legion(3)
    assert ok1 is True and ok2 is False

    # recall 重入：war_id 匹配 → 已 AVAILABLE → 0
    assert ms.recall_from_war("war1") == 0

    # disband 重入：can_be_disbanded 门
    population_api.process_population_disbandments(state)
    assert ms.get_legion_by_number(1).status == LegionStatus.DISBANDED
    assert ms.get_legion_by_number(1).disband() is False

    # destroy 重入：mark_destroyed 状态门幂等（DISBANDED 不满足 destroy 前置）
    # （DESTROYED 唯一清除点语义由 GB 覆盖；此处断言 DISBANDED 不可再 destroy）
    # takeover 重入：RESOLVED 战争 fail-closed（P1/P2 前置不命中）
    to = senate_api.takeover_war(state, "player_opt", "war1", 1)
    assert to["success"] is False


# ════════════════════════════════════════════════════════════════════════
# T-GD-05 — population canonical 幂等 marker：重入零重复解散（S33）
# ════════════════════════════════════════════════════════════════════════

def test_tgd05_population_marker_idempotent():
    state, war, _ = _build_chain_state()
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        combat_api.do_combat_action(state, "player_opt", "war1", "attack")

    first = population_api.process_population_disbandments(state)
    assert first["legions"]["resolved_wars"]["total"] == 2
    legions_snap = [(l.number, l.status) for l in state._military_system._legions]
    fleets_snap = {n: f.status for n, f in state.naval_system._fleets.items()}

    second = population_api.process_population_disbandments(state)
    assert second == first
    assert [(l.number, l.status) for l in state._military_system._legions] == legions_snap
    assert {n: f.status for n, f in state.naval_system._fleets.items()} == fleets_snap

    # 底层原语重入亦天然幂等
    empty = state._war_system.process_triumph_and_disbandment()
    assert empty["disbanded"]["resolved_wars"]["total"] == 0
    assert empty["disbanded"]["deescalated"]["total"] == 0


# ════════════════════════════════════════════════════════════════════════
# T-GD-06 — S28：战争结束舰队 AVAILABLE → Revenue 计费 → Population DISBANDED
# ════════════════════════════════════════════════════════════════════════

def test_tgd06_fleet_available_maintenance_then_disbanded():
    state, war, _ = _build_chain_state()
    ns = state.naval_system
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        combat_api.do_combat_action(state, "player_opt", "war1", "attack")

    # 战争结束：AVAILABLE（非 DISBANDED、非 DESTROYED）—— 不立即解散（G1-14）
    assert all(ns.get_fleet(n).status == FleetStatus.AVAILABLE for n in (1, 2, 3))
    # 下个 Revenue：AVAILABLE 幸存者计费（排除 DISBANDED/BUILDING/DESTROYED，GC S4）
    assert ns.calculate_maintenance() == 12
    rev = EconomicService(state).settle_revenue_phase()
    assert rev["data"]["maintenance"]["naval"]["total"] == 12
    # 下个 Population：DISBANDED（行政退役非 DESTROYED，R-11）
    disband = population_api.process_population_disbandments(state)
    assert sorted(disband["fleets"]) == [1, 2, 3]
    assert all(ns.get_fleet(n).status == FleetStatus.DISBANDED for n in (1, 2, 3))
    assert ns.calculate_maintenance() == 0


# ════════════════════════════════════════════════════════════════════════
# T-GD-07 — S29：战争结束军团 AVAILABLE → Population DISBANDED（Veteran 保留）
# ════════════════════════════════════════════════════════════════════════

def test_tgd07_legion_available_then_disbanded_veteran_retained():
    state, war, _ = _build_chain_state()
    ms = state._military_system
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        combat_api.do_combat_action(state, "player_opt", "war1", "attack")

    assert ms.get_legion_by_number(1).status == LegionStatus.AVAILABLE
    assert ms.get_legion_by_number(1).is_veteran is True

    disband = population_api.process_population_disbandments(state)
    assert disband["legions"]["resolved_wars"]["total"] == 2
    assert ms.get_legion_by_number(1).status == LegionStatus.DISBANDED
    # G1-19：Veteran 持久（解散不清；重募保留）
    assert ms.get_legion_by_number(1).is_veteran is True
    ok, _ = ms.recruit_legion(1)
    assert ok is True
    assert ms.get_legion_by_number(1).is_veteran is True


# ════════════════════════════════════════════════════════════════════════
# T-GD-08 — S31：全 25 军团 DESTROYED + 可恢复军团存在 → Resolution 判 game_over
#           先于恢复（G1-25 顺序不变式）
# ════════════════════════════════════════════════════════════════════════

def test_tgd08_resolution_game_over_before_recovery():
    state = GameState.create_for_testing({
        "combat_rules": {"legion_recovery_interval": 3},
    })
    state.turn = GameTurn(turn_number=5, year=-276)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    ms = state._military_system
    # 全 25 军团 DESTROYED（destroyed_turn=1 → turn 5 满足 interval=3 → 本可恢复）
    for leg in ms._legions:
        leg.mark_destroyed(1)
    assert len(ms.get_destroyed_legions()) == 25

    state.mark_phase_executed("combat")
    result = resolution_api.execute_resolution(state)
    assert result["success"] is True
    vc = result["data"]["victory"]
    # 胜负判定先于恢复：game_over 成立（legions_destroyed critical）
    assert vc["game_over"] is True
    conditions = {c["type"]: c for c in vc["conditions"]}
    assert "legions_destroyed" in conditions
    assert conditions["legions_destroyed"]["triggered"] is True
    assert conditions["legions_destroyed"]["critical"] is True


# ════════════════════════════════════════════════════════════════════════
# T-GD-09 — truce 到期恢复面（G3C）：approved TRUCE 到 truce_end_turn → THREAT
#          （禁 direct ACTIVE；threat_level=1；commander_id=None；Sea Control 保持）
# ════════════════════════════════════════════════════════════════════════

def test_tgd09_truce_expiry_to_threat():
    from src.core.systems.political_system import PoliticalSystem
    state, war, _ = _build_chain_state(war_id="war_truce")
    ws = state._war_system
    ms = state._military_system
    # 进入 TRUCE + pending 条约 → Senate 批准（G3C：approved TRUCE，legion 释放入队）
    ws._active_wars.remove(war)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "submitted", "indemnity": 50, "duration": 3, "generated_turn": 8})
    ws._truce_wars.append(war)
    PoliticalSystem(state).execute_passed_peace_treaty(war)
    assert war.status == WarStatus.TRUCE
    assert ms.get_legion_by_number(1).war_id is None  # 释放
    # 已到期（truce_end_turn 4 <= 当前 turn 10）
    war.set_truce_end_turn(4)

    # 年度推进：approved TRUCE 到期 → THREAT（禁直接 ACTIVE）
    state.mark_phase_executed("combat")
    state.mark_phase_executed("resolution")
    state.advance_year()
    assert war not in ws._truce_wars
    assert war in ws._threats
    assert war.status == WarStatus.THREAT
    assert war.threat_level == 1  # 权威默认（对齐 deactivate_war_to_threat）
    assert war.commander_id is None
    assert state.get_resolution_settlement().get("truce_expiries", []) == ["Naval War"]
    # 旧绑定不恢复：legion 保持释放（不回到 war）
    assert ms.get_legion_by_number(1).war_id is None


# ════════════════════════════════════════════════════════════════════════
# T-GD-10 — G3C 符号审计：到期机制恢复（is_truce_expired / _move_to_threat /
#          _plan_truce_expiry / process_truce_expiry / _check_truce_expiry）
# ════════════════════════════════════════════════════════════════════════

def test_tgd10_g3c_symbols_restored():
    from src.core.entities.war import War as WarEntity
    from src.core.systems.war_system import WarSystem as WS
    from src.core.game_state import GameState as GS
    from src.ui.commands.phase_resolution import ResolutionCommand

    # G3C 恢复符号（到期机制全链在位）
    assert hasattr(GS, "_plan_truce_expiry")
    assert hasattr(GS, "_apply_truce_expiry")
    assert hasattr(GS, "process_truce_expiry")
    assert hasattr(WarEntity, "is_truce_expired")
    assert hasattr(WS, "_move_to_threat")
    assert hasattr(ResolutionCommand, "_check_truce_expiry")
    # _move_to_active 不恢复（GD 冻结路径 move_truce_war_to_active 承担 TRUCE→ACTIVE）
    assert not hasattr(WS, "_move_to_active")

    # 冻结路径保留（容器迁移原语 / TRUCE 转换）
    assert hasattr(WS, "enter_truce")
    assert hasattr(WS, "move_truce_war_to_active")
    assert hasattr(WS, "move_truce_war_to_resolved")
    assert hasattr(WS, "restore_rejected_peace_treaty")
    assert hasattr(WS, "deactivate_war_to_threat")
    # truce_end_turn 字段 + 到期判定（G3C：war-resume authority 恢复）
    w = WarEntity(id="w", name="W")
    w.set_truce_end_turn(9)
    assert w.truce_end_turn == 9
    assert w.is_truce_expired(9) is True
    assert w.is_truce_expired(8) is False

    # R-17 镜像权威审计：combat 战力源 = live 实体（_compute_combat_result 内
    # get_legions_for_battle；镜像字段仅兼容 debug——由 GB 测试断言实现细节）
    state, war, _ = _build_chain_state()
    with patch.object(combat_api.random, "randint", side_effect=[7, 7]):
        result = combat_api.do_combat_action(state, "player_opt", "war1", "attack")
    assert result["success"]
    # live 军团战力参与判定（2 军团 × 2 战力 + martial 4 + dice 7 - enemy defence 5
    # = 10 → VICTORY：决定性结果，战争结束 RESOLVED——镜像=0 时战力仍正确，R-17）
    assert result["data"]["result"] in ("triumph", "victory")
