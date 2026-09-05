# src/tests/test_api/test_wpg_g3c_treaty_lifecycle.py
"""
WP-G G3C（Owner Correction 2026-09-01）— Treaty Lifecycle 单一修复包 T1~T9 回归。

冻结语义（Change Record DC-TREATY-LIFECYCLE-CORRECTION-01 §3 / 评审意见 §13）：
  Approved Treaty = TEMPORARY TRUCE（非战争结束）→ War 保持 TRUCE + approved +
  truce_end_turn + Commander 返回 + Legion/Fleet 释放 + enqueue-then-clear
  （ODR-CAND-01 方向①）+ Revenue 最后维护 + Population DISBANDED（exactly-once）
  Treaty Expiry → TRUCE→THREAT（threat_level=1，commander_id=None，不恢复旧绑定，
  Sea Control 保持）→ escalate_threats（≥3 爆发）→ ACTIVE
  TRIUMPH/VICTORY → RESOLVED（独立生命周期）
  Rejected → TRUCE→ACTIVE（restore_rejected_peace_treaty 既有语义不变）

T1  Approved stays TRUCE          T2  Force release
T3  Enqueue-then-clear            T4  Revenue final maintenance
T5  Population exactly-once       T6  Retry/re-entry
T7  同编号重募回归（ODR-CAND-01 核心）
T8  Treaty expiry → THREAT → escalation → ACTIVE（反回归：旧 Commander 不恢复）
T9  Victory vs Treaty 对照
"""
import unittest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import population_api


class TestWpgG3cTreatyLifecycle(unittest.TestCase):
    """T1~T9 单一修复包回归（approved = temporary truce 全链）。"""

    def setUp(self):
        self.state = GameState.create_for_testing({
            "economic_rules": {
                "fleet_types": {
                    "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
                },
                "default_fleet_type": "trireme",
                "legion_recruit_cost": 10,
                # WP-G-R1 T-R1-12（2026-09-05）：显式军团维护基数（防生产 config 漂移；
                # 值 = Legion.get_maintenance_cost 既有默认 2 / vet+1）
                "legion_maintenance_base": 2,
                "veteran_maintenance_bonus": 1,
            },
        })
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 1000
        self.state.pyrrhic_war_won = True
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)
        self.commander = Figure(id=1, name="指挥官", faction_id="optimates", age=50)
        self.commander.office = "proconsul"
        self.commander.is_absent = True
        self.commander.class_tier = ClassTier.NOBILE
        self.state.add_member(self.commander)
        self.faction.member_ids.append(1)

    # ------------------------------------------------------------------
    # 工具：构造「TRUCE + submitted 条约 + 军团/舰队/指挥官绑定」的战争
    # ------------------------------------------------------------------
    def _make_submitted_truce_war(self, war_id="w_treaty", legion_numbers=(1, 2), fleet_numbers=(1,)):
        war = War(id=war_id, name="Treaty War", war_type=WarType.FOREIGN, strength=5,
                  naval_required=True, enemy_naval_current=5, enemy_land_current=5)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 100, "duration": 3, "status": "submitted", "generated_turn": 1})
        war.commander_id = 1
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        for num in legion_numbers:
            ok, _ = ms.recruit_legion(num)
            assert ok
        if legion_numbers:
            assigned, _ = ms.assign_to_war(list(legion_numbers), war.id, 1)
            assert assigned == len(legion_numbers)
        ns = self.state._naval_system
        for num in fleet_numbers:
            fleet = Fleet(number=num, fleet_type="trireme")
            fleet._strength_base = 3
            fleet._status = FleetStatus.AVAILABLE
            ns._fleets[num] = fleet
            ok = ns.assign_fleet_to_war(num, war.id, "naval")
            assert ok, f"fleet {num} assign failed"
        return war

    def _approve_treaty(self, war):
        PoliticalSystem(self.state).execute_passed_peace_treaty(war)
        return war

    # ════════════════════════════════════════════════════════════════════
    # T1 — Approved stays TRUCE
    # ════════════════════════════════════════════════════════════════════
    def test_t1_approved_stays_truce(self):
        """T1：approved → war.status==TRUCE / 在 _truce_wars / 不在 _war_discard /
        peace_treaty.status==approved / truce_end_turn!=None。"""
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ws = self.state._war_system

        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, ws._truce_wars)
        self.assertNotIn(war, ws._war_discard)
        self.assertEqual(war.peace_treaty["status"], "approved")
        self.assertIsNotNone(war.truce_end_turn)
        self.assertEqual(war.truce_end_turn, 4)  # turn 1 + duration 3

    # ════════════════════════════════════════════════════════════════════
    # T2 — Force release
    # ════════════════════════════════════════════════════════════════════
    def test_t2_force_release(self):
        """T2：批准后 Commander 返回 / Legion AVAILABLE / Fleet AVAILABLE。"""
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ms = self.state._military_system
        ns = self.state._naval_system

        # Commander 返回罗马（war.commander_id=None + is_absent=False）
        self.assertIsNone(war.commander_id)
        self.assertFalse(self.commander.is_absent)
        self.assertEqual(self.commander.office, "ex-consul")
        # Legion AVAILABLE
        for num in (1, 2):
            legion = ms.get_legion_by_number(num)
            self.assertEqual(legion.status, LegionStatus.AVAILABLE)
            self.assertIsNone(legion.war_id)
            self.assertIsNone(legion.commander_id)
        # Fleet AVAILABLE
        for num in (1,):
            fleet = ns.get_fleet(num)
            self.assertEqual(fleet.status, FleetStatus.AVAILABLE)

    # ════════════════════════════════════════════════════════════════════
    # T3 — Enqueue-then-clear
    # ════════════════════════════════════════════════════════════════════
    def test_t3_enqueue_then_clear(self):
        """T3：批准后 _legions_to_disband==释放编号 / war.legion_numbers==[]（ODR-CAND-01 方向①）。"""
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ws = self.state._war_system

        self.assertEqual(sorted(ws._legions_to_disband), [1, 2])
        self.assertEqual(war.legion_numbers, [])
        # 无双入残留：war.legion_numbers 已清，Population 不会经 resolved-wars 面重复解散
        self.assertEqual(war.legion_numbers, [])

    # ════════════════════════════════════════════════════════════════════
    # T4 — Revenue final maintenance
    # ════════════════════════════════════════════════════════════════════
    def test_t4_revenue_final_maintenance(self):
        """T4：Revenue 前释放单元按权威规则付最后维护（AVAILABLE 幸存者计费）。

        WP-G-R1 R1-G-02 / T-R1-12 定向更新（v1.6 §7.10.3-D / §7.12.3）：军团维护集 =
        ACTIVE + released survivors（AVAILABLE via recall，pending Population retirement）
        + RECALLING；排除 UNRAISED/DISBANDED/DESTROYED。旧断言
        `ms.calculate_maintenance()[0] == 0`（ACTIVE-only 同集）已被 Owner 新证据推翻——
        released AVAILABLE Legion 产生最后维护（2 军团 × base 2 = 4）。
        """
        from src.core.service.economic_service import EconomicService
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ns = self.state._naval_system
        ms = self.state._military_system

        # AVAILABLE 幸存者仍计维护（G1-14：下个 Revenue 最后一次；R1-G-02 军团侧同集）
        self.assertEqual(ns.calculate_maintenance(), 4)  # 1 艘 trireme
        # 2 个 released AVAILABLE 军团（非 veteran）→ 2 × legion_maintenance_base(2) = 4
        legion_total, _ = ms.calculate_maintenance()
        self.assertEqual(legion_total, 4)
        rev = EconomicService(self.state).settle_revenue_phase()
        self.assertEqual(rev["data"]["maintenance"]["naval"]["total"], 4)
        self.assertEqual(rev["data"]["maintenance"]["military"]["total"], 4)
        # Population 行政解散（deescalated 面，exactly-once）后停计（DISBANDED 排除，R1-08）
        disband = population_api.process_population_disbandments(self.state)
        self.assertEqual(disband["legions"]["deescalated"]["total"], 2)
        self.assertEqual(ms.calculate_maintenance()[0], 0)
        # 再下一 Revenue：0 重复维护（Legion + Fleet 均已 DISBANDED 排除）
        rev2 = EconomicService(self.state).settle_revenue_phase()
        self.assertEqual(rev2["data"]["maintenance"]["military"]["total"], 0)
        self.assertEqual(rev2["data"]["maintenance"]["naval"]["total"], 0)

    # ════════════════════════════════════════════════════════════════════
    # T5 — Population exactly-once
    # ════════════════════════════════════════════════════════════════════
    def test_t5_population_exactly_once(self):
        """T5：Legion→DISBANDED / _legions_to_disband==[] / 无重复错误 / 无 requeue。"""
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ws = self.state._war_system
        ms = self.state._military_system

        disband = population_api.process_population_disbandments(self.state)
        # approved TRUCE 非 RESOLVED → 解散走 deescalated（队列）面
        self.assertEqual(disband["legions"]["resolved_wars"]["total"], 0)
        self.assertEqual(disband["legions"]["deescalated"]["total"], 2)
        self.assertEqual(disband["legions"]["deescalated"]["errors"], [])
        for num in (1, 2):
            self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
        # 队列消费完毕（T5 核心：exactly-once，无残留、无 requeue）
        self.assertEqual(ws._legions_to_disband, [])

    # ════════════════════════════════════════════════════════════════════
    # T6 — Retry / re-entry
    # ════════════════════════════════════════════════════════════════════
    def test_t6_retry_reentry_no_second_disband(self):
        """T6：重复 Population 处理零二次解散 / 零队列再生 / 零错误。"""
        war = self._make_submitted_truce_war()
        self._approve_treaty(war)
        ws = self.state._war_system
        ms = self.state._military_system

        first = population_api.process_population_disbandments(self.state)
        again = population_api.process_population_disbandments(self.state)
        # marker 幂等：结果一致，零重复 mutation
        self.assertEqual(again, first)
        self.assertEqual(ws._legions_to_disband, [])
        for num in (1, 2):
            self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
        # 底层原语重入亦零重复
        empty = ws.process_triumph_and_disbandment()
        self.assertEqual(empty["disbanded"]["deescalated"]["total"], 0)
        self.assertEqual(empty["disbanded"]["deescalated"]["errors"], [])

    # ════════════════════════════════════════════════════════════════════
    # T7 — 同编号重募回归（ODR-CAND-01 核心）
    # ════════════════════════════════════════════════════════════════════
    def test_t7_same_number_rerecruit_not_disbanded_by_stale_queue(self):
        """T7：批准→Population 解散→重募 #N→指派新 War→下个 Population→#N 保持新生命周期。

        ODR-CAND-01 反回归：旧队列引用不得影响新征召生命周期（enqueue-then-clear 消除残留）。
        """
        ms = self.state._military_system
        ws = self.state._war_system

        # 1) 批准和约（legion 1/2 入队）
        war1 = self._make_submitted_truce_war("w_old", legion_numbers=(1, 2), fleet_numbers=())
        self._approve_treaty(war1)
        # 2) Population 解散
        population_api.process_population_disbandments(self.state)
        self.assertEqual(ws._legions_to_disband, [])
        self.assertEqual(ms.get_legion_by_number(1).status, LegionStatus.DISBANDED)

        # 3) 重募 #1 → 指派新 War（新生命周期）
        ok, _ = ms.recruit_legion(1)
        self.assertTrue(ok)
        war2 = War(id="w_new", name="New War", war_type=WarType.FOREIGN, strength=5)
        war2.status = WarStatus.ACTIVE
        ws._active_wars.append(war2)
        assigned, _ = ms.assign_to_war([1], war2.id, 1)
        self.assertEqual(assigned, 1)
        self.assertEqual(ms.get_legion_by_number(1).war_id, "w_new")

        # 4) 下个 Population（新年度 marker 重置，模拟 advance_year 清空 _phase_results）
        self.state._phase_results.clear()
        disband = population_api.process_population_disbandments(self.state)
        self.assertEqual(disband["legions"]["deescalated"]["total"], 0)
        self.assertEqual(disband["legions"]["resolved_wars"]["total"], 0)
        self.assertEqual(ms.get_legion_by_number(1).status, LegionStatus.ACTIVE)
        self.assertEqual(ms.get_legion_by_number(1).war_id, "w_new")
        # 旧编号 2 已 DISBANDED 且未被 requeue（无僵尸队列）
        self.assertEqual(ms.get_legion_by_number(2).status, LegionStatus.DISBANDED)
        self.assertEqual(ws._legions_to_disband, [])

    # ════════════════════════════════════════════════════════════════════
    # T8 — Treaty expiry：approved TRUCE → THREAT → escalation → ACTIVE
    # ════════════════════════════════════════════════════════════════════
    def test_t8_treaty_expiry_to_threat_then_active(self):
        """T8：approved TRUCE→到 truce_end_turn→THREAT（threat_level=1，commander_id=None，
        无旧绑定，Sea Control 保持）→escalation→ACTIVE；反回归：旧 Commander 不自动恢复。"""
        from src.core.entities.entities import GameTurn as GT
        ws = self.state._war_system
        ms = self.state._military_system
        ns = self.state._naval_system

        # 构造 approved TRUCE 战争（sea_control_acquired=True 模拟海战获控后批准）
        war = self._make_submitted_truce_war(legion_numbers=(1, 2), fleet_numbers=(1,))
        self._approve_treaty(war)
        war._sea_control_acquired = True
        # 到期：truce_end_turn = 1（当前 turn 1 即到期）
        war.set_truce_end_turn(1)

        expired = self.state.process_truce_expiry()
        self.assertEqual(expired, ["Treaty War"])

        # 到期 → THREAT（禁 direct ACTIVE / preserve_commander）
        self.assertEqual(war.status, WarStatus.THREAT)
        self.assertIn(war, ws._threats)
        self.assertNotIn(war, ws._truce_wars)
        self.assertNotIn(war, ws._active_wars)
        self.assertEqual(war.threat_level, 1)  # 权威默认（deactivate_war_to_threat）
        self.assertIsNone(war.commander_id)  # 不恢复旧 Commander
        # 无旧 Legion/Fleet 绑定恢复
        for num in (1, 2):
            self.assertIsNone(ms.get_legion_by_number(num).war_id)
        fleet = ns.get_fleet(1)
        self.assertNotEqual(fleet.status, FleetStatus.ON_MISSION)  # 已召回，未重派
        # Sea Control 保持（same-War persistent，禁清 False）
        self.assertTrue(war.sea_control_acquired)

        # 正常威胁自动升级（≥3 爆发 → ACTIVE）：_triggered_this_turn 先复位再升级
        war._triggered_this_turn = False
        ws.escalate_threats()
        self.assertEqual(war.threat_level, 2)
        ws.escalate_threats()
        self.assertEqual(war.threat_level, 3)
        ws.escalate_threats()
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, ws._active_wars)
        self.assertNotIn(war, ws._threats)
        # 反回归：旧 Commander 不自动恢复
        self.assertIsNone(war.commander_id)
        # Sea Control 跨 TRUCE→THREAT→ACTIVE 保持（未 formal termination）
        self.assertTrue(war.sea_control_acquired)

    def test_t8b_old_commander_not_restored_after_expiry(self):
        """T8 反回归（独立用例）：到期后旧 Commander 绑定不恢复，legion 不重绑。"""
        ws = self.state._war_system
        ms = self.state._military_system
        war = self._make_submitted_truce_war(legion_numbers=(1,), fleet_numbers=())
        self._approve_treaty(war)
        self.assertIsNone(war.commander_id)
        war.set_truce_end_turn(1)
        self.state.process_truce_expiry()
        self.assertEqual(war.status, WarStatus.THREAT)
        self.assertIsNone(war.commander_id)
        self.assertIsNone(ms.get_legion_by_number(1).war_id)
        self.assertIsNone(ms.get_legion_by_number(1).commander_id)

    # ════════════════════════════════════════════════════════════════════
    # T9 — Victory vs Treaty 对照
    # ════════════════════════════════════════════════════════════════════
    def test_t9_victory_resolved_vs_treaty_truce(self):
        """T9：TRIUMPH/VICTORY→RESOLVED；Approved→TRUCE（不同生命周期）。"""
        from src.core.systems.political_system import PoliticalSystem as PS

        # 对照战争 A：和约批准 → TRUCE
        war_treaty = self._make_submitted_truce_war("w_peace", legion_numbers=(1,), fleet_numbers=())
        PS(self.state).execute_passed_peace_treaty(war_treaty)
        self.assertEqual(war_treaty.status, WarStatus.TRUCE)
        self.assertIn(war_treaty, self.state._war_system._truce_wars)

        # 对照战争 B：TRIUMPH → RESOLVED（resolve_war 胜利分支）
        war_victory = War(id="w_victory", name="Victory War", war_type=WarType.FOREIGN, strength=5)
        war_victory.commander_id = 1
        war_victory.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war_victory)
        with patch.object(self.state._war_system, "resolve_war", wraps=self.state._war_system.resolve_war) as spy:
            self.state._war_system.resolve_war(war_victory.id, victory=True)
        self.assertEqual(war_victory.status, WarStatus.RESOLVED)
        self.assertIn(war_victory, self.state._war_system._war_discard)
        self.assertNotIn(war_victory, self.state._war_system._truce_wars)
        # 生命周期区分：TRUCE（treaty）≠ RESOLVED（victory）
        self.assertNotEqual(war_treaty.status, war_victory.status)

    # ════════════════════════════════════════════════════════════════════
    # T9b — Rejected treaty 保持既有语义（对照：TRUCE→ACTIVE preserve commander）
    # ════════════════════════════════════════════════════════════════════
    def test_t9b_rejected_treaty_active_preserves_commander(self):
        """Rejected 对照（不变语义）：TRUCE→ACTIVE，commander 连续性保留。"""
        ws = self.state._war_system
        war = self._make_submitted_truce_war("w_reject", legion_numbers=(1,), fleet_numbers=())
        self.assertTrue(ws.restore_rejected_peace_treaty(war.id, preserve_commander=True))
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, ws.get_active_wars())
        self.assertEqual(war.commander_id, 1)  # 保留 commander
        self.assertIsNone(war.peace_treaty)


# ════════════════════════════════════════════════════════════════════════
# Save/load round-trip（E 项）：approved TRUCE 一致，不恢复已释放绑定
# ════════════════════════════════════════════════════════════════════════

def test_saveload_approved_truce_roundtrip_consistent():
    """E 项：approved TRUCE 战争（TRUCE + approved + truce_end_turn + _truce_wars +
    sea_control_acquired）save/load 后一致；不恢复已释放 Commander/Legion/Fleet 绑定。"""
    from src.core.entities.player import Player, PlayerType
    from src.core.entities.legion import LegionStatus as LS

    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-270)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="p1", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("p1")
    commander = Figure(id=101, name="Cmd", faction_id="senate", age=40)
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    ws = state._war_system
    ms = state._military_system
    war = War(id="w_truce", name="Truce War", strength=5, threat_level=0)
    war.status = WarStatus.TRUCE
    war.set_peace_treaty({"status": "approved", "indemnity": 50, "duration": 3, "generated_turn": 3})
    war.set_truce_end_turn(8)
    war._sea_control_acquired = True
    # 已释放绑定（批准后形态）：commander_id=None，legion AVAILABLE 无 war_id
    war.commander_id = None
    ok, _ = ms.recruit_legion(1)
    assert ok
    legion = ms.get_legion_by_number(1)
    legion.status = LS.AVAILABLE
    legion.war_id = None
    legion.commander_id = None
    ws._truce_wars.append(war)
    ws.add_legions_to_disband([1])
    # 已释放绑定（批准后形态）：Fleet AVAILABLE、无战争指派、无指挥官绑定、无单战归属
    ns = state._naval_system
    fleet = Fleet(number=1, fleet_type="trireme")
    fleet._strength_base = 3
    fleet._status = FleetStatus.AVAILABLE
    fleet._assigned_war_id = None
    fleet._commander_id = None
    fleet._target_war_id = None
    ns._fleets[1] = fleet

    restored = GameState.create_for_testing({})
    restored.load_from_dict(state.to_dict())
    rws = restored._war_system
    r1 = rws.get_war_by_id("w_truce")
    assert r1.status == WarStatus.TRUCE
    assert r1 in rws._truce_wars
    assert r1.peace_treaty["status"] == "approved"
    assert r1.truce_end_turn == 8
    assert r1.sea_control_acquired is True
    assert r1.commander_id is None  # 不恢复已释放 Commander
    assert rws._legions_to_disband == [1]
    rms = restored._military_system
    rleg = rms.get_legion_by_number(1)
    assert rleg.status == LS.AVAILABLE
    assert rleg.war_id is None  # 不恢复已释放 Legion 绑定
    rns = restored._naval_system
    rfleet = rns.get_fleet(1)
    assert rfleet.status == FleetStatus.AVAILABLE  # 非 ON_MISSION（已释放）
    assert rfleet._assigned_war_id is None  # 不恢复已释放战争指派
    assert rfleet._commander_id is None  # 不恢复已释放指挥官绑定
    assert rfleet._target_war_id is None  # 不恢复单战归属（本 fixture 无 provenance）


if __name__ == "__main__":
    unittest.main()
