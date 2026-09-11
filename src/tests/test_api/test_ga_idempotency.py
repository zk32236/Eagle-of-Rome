# src/tests/test_api/test_ga_idempotency.py
"""WP-G GA：re-entry / retry 幂等（Q 件 H / S33）测试。

覆盖：
- Takeover 重入：第二次拒绝（ACTIVE+valid commander），无重复征召/rebind
- Continue 重入：执行后 war 离开 TRUCE → 第二次拒绝，无重复 mutation
- AI 路径重入：已接管战争不再被 AI 重复接管
- 征召总数守恒（25 池上限不因重入重复消耗）
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import senate_api


class TestGaIdempotency(unittest.TestCase):
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
        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
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

    def _make_truce_war(self, war_id="w1"):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        ok, _ = ms.recruit_legion(1)
        assert ok
        ms.assign_to_war([1], war.id, 2)
        return war

    def test_takeover_reentry_no_duplicate(self):
        """S33：接管 → 重入拒绝；无重复征召/rebind。"""
        war = self._make_truce_war()
        politics = PoliticalSystem(self.state)
        self.assertTrue(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=2))
        legions_after = list(war.legion_numbers)
        assigned_after = {l.number: l.commander_id
                          for l in self.state._military_system.get_legions_for_battle(war.id)}
        self.assertFalse(politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=2))
        self.assertEqual(list(war.legion_numbers), legions_after)
        assigned_re = {l.number: l.commander_id
                       for l in self.state._military_system.get_legions_for_battle(war.id)}
        self.assertEqual(assigned_re, assigned_after)

    def test_continue_reentry_no_duplicate(self):
        """S33：Continue 执行后 war 离开 TRUCE → 第二次拒绝，无重复征召。"""
        self.old_cmd.office = "consul"  # 有效指挥官（Continue 前置）
        war = self._make_truce_war(war_id="w_cont")
        politics = PoliticalSystem(self.state)
        self.assertTrue(politics.execute_war_continue_direct(war, self.consul, reinforcement_n=1))
        legions_after = list(war.legion_numbers)
        self.assertFalse(politics.execute_war_continue_direct(war, self.consul, reinforcement_n=1))
        self.assertEqual(list(war.legion_numbers), legions_after)
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_human_api_reentry(self):
        """WP-G-R4 supersede（OD-R4-05/06，SA v1.7 §2.4b）：human takeover_war Submit = 锁 T
        零部署；部署唯一 owner = advance_senate_phase。重入：L O C K E D 后重复 submit 拒绝。"""
        war = self._make_truce_war(war_id="w_api")
        first = senate_api.takeover_war(self.state, "player1", war.id, 1, action="reserve")
        self.assertTrue(first["success"])
        locked = senate_api.takeover_war(self.state, "player1", war.id, 1, action="submit")
        self.assertTrue(locked["success"], locked.get("message"))
        # 锁 T 零部署：war 保持 TRUCE+pending、Commander 不变（2）、无 D、无 R
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.commander_id, 2, "Submit 零部署：Commander 未变")
        self.assertEqual(self.state.get_takeover_pending()["status"], "LOCKED")
        self.assertEqual(self.state.get_senate_direct_actions(), [])

        second = senate_api.takeover_war(self.state, "player1", war.id, 1, action="submit")
        self.assertFalse(second["success"], "LOCKED 后重复 submit 拒绝")
        self.assertEqual(self.state.get_takeover_pending()["status"], "LOCKED")
        self.assertEqual(self.state.get_senate_direct_actions(), [])

    def test_ai_reentry_skips_already_locked(self):
        """WP-G-R4 supersede（R4-24）：AI 锁 T 后重入——同一 LOCKED commitment 存在 → 不重复
        锁定（records 0）；部署前零 D/mutation（废弃直连）。"""
        war = self._make_truce_war(war_id="w_ai")
        politics = PoliticalSystem(self.state)
        records = politics.execute_ai_takeover_direct_action()
        self.assertLessEqual(len(records), 1)
        pending = self.state.get_takeover_pending()
        self.assertIsNotNone(pending, "AI 单 commitment 锁 T")
        self.assertEqual(pending["status"], "LOCKED")
        self.assertEqual(pending["war_id"], war.id)
        self.assertEqual(war.commander_id, 2, "锁 T 零部署（旧 Commander 未动）")
        self.assertEqual(self.state.get_senate_direct_actions(), [], "部署前无 D")
        # 重入：LOCKED 已存在 → 不重复锁定（records 空）
        records2 = politics.execute_ai_takeover_direct_action()
        self.assertEqual(records2, [])
        self.assertEqual(self.state.get_takeover_pending()["status"], "LOCKED")


if __name__ == "__main__":
    unittest.main()
