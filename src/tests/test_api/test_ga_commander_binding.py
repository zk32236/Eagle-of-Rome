# src/tests/test_api/test_ga_commander_binding.py
"""WP-G GA：Commander 绑定反 split-brain 不变式（H 件 §3 / R-14 / G1-20）测试。

覆盖 S19/S21：
- Takeover 后 War/Legion/Fleet 三绑定一致（全量幸存 rebind）
- Continue 后绑定收敛现有 Commander
- P2（commanderless ACTIVE）接管同样收敛
- pre-GD 状态内一致性（Q 件 I：不依赖 save/load）

R6（SA-Design v1.1 §C.6 / §C.2；DA-3 B4 退役 + DA-6 B1a 迁移）：
三孤儿 `execute_war_takeover_deploy` / `execute_war_takeover_direct` /
`execute_war_continue_direct` 已**退役为无副作用 shim**，统一返回 **dict**
`{success:False, code:LEGACY_WAR_EXECUTION_RETIRED, message:"use package and advance"}`
（PM 裁定 P-B4-4 = 保持 dict）。本文件旧「直调孤儿 → 三绑定收敛」语义命题
**迁移到新 direct 路由**（合规 Submit 冻结 `ConsulWarDecision` + 唯一边界消费
`senate_api.advance_senate_phase`）；孤儿直调侧只断言退役码 + **零 mutation**
（`snapshot_war_resolution_domains()` 深值相等）。**用例未删、未改名、难度未降。**
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
from src.api import senate_api


class TestGaCommanderBinding(unittest.TestCase):
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

    # ---------- R6（DA-6 B1a）迁移 helper ----------

    def _assert_retired_zero_mutation(self, call):
        """孤儿退役 shim：dict {success/code/message} + 零 mutation（快照深值相等）。"""
        before = self.state.snapshot_war_resolution_domains()
        result = call()
        after = self.state.snapshot_war_resolution_domains()
        self.assertIsInstance(result, dict)
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], PoliticalSystem.LEGACY_WAR_EXECUTION_RETIRED)
        self.assertEqual(result["message"], "use package and advance")
        self.assertEqual(before, after, "退役 shim 必须零 mutation")
        return result

    def _submit_package(self, drafts):
        return senate_api.propose_many(self.state, "player1", {"war_drafts": drafts})

    def _resolve_and_advance(self):
        res = senate_api.resolve_senate(self.state)
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        return adv

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
        """S19/S21：新 direct 路由（checked command → consul_direct → 唯一边界）接管后
        War/Legion/Fleet 全收敛新 Consul（含幸存 Fleet rebind）；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_war_with_assets()
        # ① 孤儿直调已退役：统一退役码 + 零 mutation（三绑定不收敛）
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.commander_id, 2)
        # ② 新 direct 路由：Submit 冻结零军事写 → 唯一边界消费接管
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(war.commander_id, 2, "Submit 零部署：Commander 未变")
        self.assertEqual(
            len(self.state.get_consul_war_decisions(self.state.get_senate_session())), 1,
            "checked command 冻结为唯一 ConsulWarDecision")
        self._resolve_and_advance()
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
        """P2（commanderless ACTIVE）：新 direct 路由接管后三绑定收敛；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_p2", name="P2 War", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        ms = self.state._military_system
        for num in (5, 6):
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war([5, 6], war.id, 2)  # 幸存者 commander 暂指旧值（H 件 §3 例外）
        # ① 孤儿直调已退役：零 mutation（commander 仍 None，旧绑定未收敛）
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertIsNone(war.commander_id)
        # ② 新 direct 路由：ACTIVE 换将/接管经唯一边界收敛
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.commander_id, self.consul.id)
        self._assert_single_authority(war)

    def test_pre_gd_invariant_holds_after_mutation(self):
        """Q 件 I（pre-GD）：mutation 后状态内一致性（不依赖 save/load）；
        孤儿直调侧 = 退役码 + 零 mutation（状态一致性亦成立）。"""
        war = self._make_war_with_assets(war_id="w_inv")
        # ① 孤儿直调已退役：零 mutation 后状态内一致性（无 split-brain）
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_takeover_direct(
                war, self.consul, reinforcement_n=2))
        self._assert_single_authority(war)
        # ② 新 direct 路由 mutation 后一致性
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 2}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self._assert_single_authority(war)
        # 独立复核：三处读取同一 id
        self.assertEqual(war.commander_id, self.consul.id)
        legion_ids = {leg.commander_id for leg in self.state._military_system.get_legions_for_battle(war.id)}
        fleet_ids = {f.commander_id for f in self.state._naval_system.get_fleets_by_war(war.id)}
        self.assertEqual(legion_ids, {self.consul.id})
        self.assertEqual(fleet_ids, {self.consul.id})


if __name__ == "__main__":
    unittest.main()
