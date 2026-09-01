# src/tests/test_api/test_ga_takeover_p1_p2.py
"""WP-G GA：统一 Takeover（P1/P2 双前置 + Shared Core 十步 + fail-closed）测试。

覆盖 Q 件 A/C/D/E/F/G/I：
- P1（TRUCE+pending treaty）正向：清条约 + TRUCE→ACTIVE + 新 Commander + 幸存保留/rebind + 显式 N
- P2（ACTIVE+no valid commander）正向：无状态转换、无条约 mutation
- 异常态 fail closed：ACTIVE+pending / TRUCE+无 pending / ACTIVE+valid commander / 其他状态
- Reinforcement N 值域（G 件 §4）：N<0 / N=0(池>0) / N>池 拒绝；池=0 & N=0 接受
- FC-05 原子性 + 反 split-brain（War/Legion/Fleet 三绑定一致）

S19 / S21 / S23 / S24 / S33 映射。
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem


class TestGaTakeoverP1P2(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for ph in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(ph)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)

        self.consul = Figure(id=1, name="新执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction.member_ids.append(1)

        self.old_cmd = Figure(id=2, name="旧指挥官", faction_id="optimates", age=50)
        self.old_cmd.office = "proconsul"
        self.old_cmd.is_absent = True
        self.state.add_member(self.old_cmd)
        self.faction.member_ids.append(2)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"

    # ---------- 构造 helpers ----------
    def _make_truce_war(self, war_id="w1", commander_id=2, legions=(1, 2), fleet=False):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=5, naval_required=fleet)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        war.commander_id = commander_id
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        for num in legions:
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war(list(legions), war.id, commander_id)
        if fleet:
            fleet = Fleet(number=90)
            fleet._status = FleetStatus.AVAILABLE
            self.state._naval_system._fleets[90] = fleet
            ok = self.state._naval_system.assign_fleet_to_war(90, war.id, "JOINT_INVASION", commander_id)
            assert ok
        return war

    def _make_commanderless_active_war(self, war_id="w2", commander_id=None, dead=False):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        war.commander_id = commander_id
        self.state._war_system._active_wars.append(war)
        return war

    def _politics(self):
        return PoliticalSystem(self.state)

    # ---------- P1 正向（S19/S21） ----------
    def test_p1_truce_pending_takeover_full_core(self):
        """P1：TRUCE+pending → 清条约 + ACTIVE + 新 Commander + 幸存保留/rebind + 显式 N。"""
        war = self._make_truce_war(fleet=True)
        ms = self.state._military_system
        surviving = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving), 2)
        for leg in surviving:
            self.assertEqual(leg.commander_id, 2)  # 旧绑定

        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)

        # 条约清 + TRUCE→ACTIVE + 新 Commander
        self.assertIsNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, self.state._war_system.get_active_wars())
        self.assertEqual(war.commander_id, self.consul.id)
        # 旧指挥官返回（absent 解除 + proconsul → ex-consul）
        self.assertFalse(self.old_cmd.is_absent)
        self.assertEqual(self.old_cmd.office, "ex-consul")
        # 新 Consul absent
        self.assertTrue(self.consul.is_absent)
        # 幸存保留（S21：禁裁员）+ rebind 新 Commander（D/Q 件 E）
        surviving_after = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving_after), 3)  # 幸存 2 + 新征召 1（显式 N=1）
        for num in (1, 2):
            self.assertEqual(ms.get_legion_by_number(num).commander_id, self.consul.id)
        # 显式 N=1：新军团绑定新 Commander
        self.assertEqual(len(war.legion_numbers), 3)
        new_legion = ms.get_legion_by_number(war.legion_numbers[-1])
        self.assertEqual(new_legion.commander_id, self.consul.id)
        self.assertEqual(new_legion.war_id, war.id)
        # Fleet rebind（H 件 §5）
        fleet = self.state._naval_system.get_fleet(90)
        self.assertEqual(fleet.commander_id, self.consul.id)
        self.assertEqual(fleet.assigned_war_id, war.id)  # 单战归属不变（GC）
        # 反 split-brain（R-14）
        for leg in ms.get_legions_for_battle(war.id):
            self.assertEqual(leg.commander_id, war.commander_id)
        self.assertEqual(fleet.commander_id, war.commander_id)

    def test_p1_takeover_requires_pending_treaty(self):
        """fail-closed：TRUCE 但无 pending treaty → False，无 mutation。"""
        war = War(id="w_nopending", name="NoPending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        self.state._war_system._truce_wars.append(war)
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 2)

    # ---------- P2 正向（ODR-G-01 / T15） ----------
    def test_p2_commanderless_active_no_treaty_mutation(self):
        """P2：ACTIVE + commander_id None → 接管成功；无条约 mutation、无状态转换（仍 ACTIVE）。"""
        war = self._make_commanderless_active_war()
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertIsNone(war.peace_treaty)  # P2 不伪造、不清理条约（Q 件 C）
        self.assertTrue(self.consul.is_absent)
        self.assertEqual(len(war.legion_numbers), 1)

    def test_p2_dead_commander_takeover(self):
        """P2：ACTIVE + commander 已阵亡 → 可接管（no valid commander）。"""
        war = self._make_commanderless_active_war(war_id="w_dead", commander_id=2)
        self.old_cmd.is_dead = True
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, self.consul.id)

    def test_p2_absent_proconsul_takeover(self):
        """P2：ACTIVE + absent proconsul（离任）→ 可接管。"""
        war = self._make_commanderless_active_war(war_id="w_absent", commander_id=2)
        self.old_cmd.is_absent = True
        self.old_cmd.office = "proconsul"
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, self.consul.id)

    # ---------- 异常态 fail closed（Q 件 A/C） ----------
    def test_fail_closed_active_with_pending_treaty(self):
        """异常态：ACTIVE + pending treaty → False（禁无条件幂等 cleanup）。"""
        war = War(id="w_active_pending", name="ActivePending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._active_wars.append(war)
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)
        self.assertIsNone(war.commander_id)
        self.assertEqual(war.peace_treaty["status"], "pending")  # 条约未被静默清理

    def test_fail_closed_active_with_valid_commander(self):
        """禁 ACTIVE+valid commander 任意接管（幂等/重入拒绝，F 件 §5.1）。"""
        war = War(id="w_valid", name="ValidCmd", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.old_cmd.is_absent = False
        self.old_cmd.office = "consul"
        self.state._war_system._active_wars.append(war)
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)
        self.assertEqual(war.commander_id, 2)

    def test_fail_closed_non_takeoverable_status(self):
        """其他状态（THREAT）→ False。"""
        war = War(id="w_threat", name="Threat", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.THREAT
        self.state._war_system._threats.append(war)
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)

    # ---------- Reinforcement N 值域（G 件 §4 / S23/S24） ----------
    def test_n_validation_rejects_out_of_range(self):
        war = self._make_truce_war()
        politics = self._politics()
        self.assertFalse(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=0))  # 池>0 & N=0
        self.assertEqual(war.status, WarStatus.TRUCE)  # 拒绝后无 mutation
        self.assertFalse(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=-1))
        self.assertFalse(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=999))  # >池

    def test_zero_pool_exception_n0_accepted(self):
        """S24：池=0 & N=0 → 接受（G1-24）；无幸存也按冻结公式（R8 只判池）。"""
        # 征召全部 25 军团使池 = 0，2 个指派到战争
        ms = self.state._military_system
        war = War(id="w_zero", name="ZeroPool", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        for num in range(1, 26):
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war([1, 2], war.id, 99)
        self.assertEqual(len(ms.get_available_legions()), 0)
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=0)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertEqual(len(war.legion_numbers), 2)  # 无新增

    def test_none_n_defaults_to_min(self):
        """N 缺省 → 冻结默认（池>0 → 1）。"""
        war = self._make_truce_war(war_id="w_default")
        ok = self._politics().execute_war_takeover_direct(war, self.consul)
        self.assertTrue(ok)
        self.assertEqual(len(war.legion_numbers), 3)  # 幸存 2 + 默认 1

    # ---------- FC-05 原子性（Q 件 H/S33） ----------
    def test_fc05_n_greater_than_pool_fails_no_commander_write(self):
        """FC-05：N>池（非法）→ False，commander 不回写。"""
        war = self._make_truce_war(war_id="w_fc05")
        ok = self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=999)
        self.assertFalse(ok)
        self.assertEqual(war.commander_id, 2)  # 旧 commander 保留（未回写）

    def test_reentry_no_duplicate_recruit(self):
        """S33：接管后重入（war 已 ACTIVE+valid commander）→ 拒绝；无重复征召。"""
        war = self._make_truce_war(war_id="w_reentry")
        politics = self._politics()
        self.assertTrue(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=1))
        legions_after_first = list(war.legion_numbers)
        self.assertFalse(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=1))
        self.assertEqual(list(war.legion_numbers), legions_after_first)
        self.assertEqual(war.commander_id, self.consul.id)


if __name__ == "__main__":
    unittest.main()
