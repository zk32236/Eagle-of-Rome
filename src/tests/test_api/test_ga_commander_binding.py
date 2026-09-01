# src/tests/test_api/test_ga_commander_binding.py
"""WP-G GA：Commander 绑定反 split-brain 不变式（H 件 §3 / R-14 / G1-20）测试。

覆盖 S19/S21：
- Takeover 后 War/Legion/Fleet 三绑定一致（全量幸存 rebind）
- Continue 后绑定收敛现有 Commander
- P2（commanderless ACTIVE）接管同样收敛
- pre-GD 状态内一致性（Q 件 I：不依赖 save/load）
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


class TestGaCommanderBinding(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)
        self.consul = Figure(id=1, name="新执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.state.add_member(self.consul)
        self.faction.member_ids.append(1)
        self.old_cmd = Figure(id=2, name="旧指挥官", faction_id="optimates", age=50)
        self.old_cmd.office = "proconsul"
        self.old_cmd.is_absent = True
        self.state.add_member(self.old_cmd)
        self.faction.member_ids.append(2)

    def _assert_single_authority(self, war):
        """H 件 §3 不变式：所有 assigned Legion/Fleet 绑定 == war.commander_id。"""
        ms = self.state._military_system
        for leg in ms.get_legions_for_battle(war.id):
            self.assertEqual(leg.commander_id, war.commander_id,
                             f"Legion {leg.number} 绑定不一致")
        for fleet in self.state._naval_system.get_fleets_by_war(war.id):
            self.assertEqual(fleet.commander_id, war.commander_id,
                             f"Fleet {fleet.number} 绑定不一致")

    def _make_war_with_assets(self, war_id="w1", fleet=True):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=5, naval_required=fleet)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        war.commander_id = 2
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        for num in (1, 2, 3):
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war([1, 2, 3], war.id, 2)
        if fleet:
            fleet = Fleet(number=80)
            fleet._status = FleetStatus.AVAILABLE
            self.state._naval_system._fleets[80] = fleet
            ok = self.state._naval_system.assign_fleet_to_war(80, war.id, "JOINT_INVASION", 2)
            assert ok
        return war

    def test_takeover_converges_war_legion_fleet(self):
        """S19/S21：Takeover 后 War/Legion/Fleet 全收敛新 Consul（含幸存 Fleet rebind）。"""
        war = self._make_war_with_assets()
        ok = PoliticalSystem(self.state).execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, self.consul.id)
        self._assert_single_authority(war)
        # 新征召军团也绑定新 Commander
        for leg in self.state._military_system.get_legions_for_battle(war.id):
            self.assertEqual(leg.commander_id, self.consul.id)

    def test_continue_converges_existing_commander(self):
        """Continue 后 War/Legion/Fleet 收敛现有 Commander（不变式保持）。"""
        self.old_cmd.office = "consul"  # TRUCE 后保留的有效指挥官（Continue 前置）
        war = self._make_war_with_assets(war_id="w_cont")
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, 2)  # 保留现有
        self._assert_single_authority(war)

    def test_p2_takeover_converges(self):
        """P2（commanderless ACTIVE）：接管后三绑定收敛。"""
        war = War(id="w_p2", name="P2 War", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        ms = self.state._military_system
        for num in (5, 6):
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war([5, 6], war.id, 2)  # 幸存者 commander 暂指旧值（H 件 §3 例外）
        ok = PoliticalSystem(self.state).execute_war_takeover_direct(war, self.consul, reinforcement_n=1)
        self.assertTrue(ok)
        self._assert_single_authority(war)

    def test_pre_gd_invariant_holds_after_mutation(self):
        """Q 件 I（pre-GD）：mutation 后状态内一致性（不依赖 save/load）。"""
        war = self._make_war_with_assets(war_id="w_inv")
        PoliticalSystem(self.state).execute_war_takeover_direct(war, self.consul, reinforcement_n=2)
        self._assert_single_authority(war)
        # 独立复核：三处读取同一 id
        self.assertEqual(war.commander_id, self.consul.id)
        legion_ids = {leg.commander_id for leg in self.state._military_system.get_legions_for_battle(war.id)}
        fleet_ids = {f.commander_id for f in self.state._naval_system.get_fleets_by_war(war.id)}
        self.assertEqual(legion_ids, {self.consul.id})
        self.assertEqual(fleet_ids, {self.consul.id})


if __name__ == "__main__":
    unittest.main()
