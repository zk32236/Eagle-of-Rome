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
        """A1 幂等：human takeover_war 第二次 → 拒绝；direct_actions 仅 1 条。"""
        war = self._make_truce_war(war_id="w_api")
        first = senate_api.takeover_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertTrue(first["success"])
        second = senate_api.takeover_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertFalse(second["success"])
        self.assertEqual(len(self.state.get_senate_direct_actions()), 1)

    def test_ai_reentry_skips_already_commanded(self):
        """AI 路径：已接管战争（ACTIVE+valid commander）不再被重复接管。"""
        war = self._make_truce_war(war_id="w_ai")
        politics = PoliticalSystem(self.state)
        records = politics.execute_ai_takeover_direct_action()
        self.assertEqual(len(records), 1)
        # 再次调用：war 已 ACTIVE+valid commander → 候选集排除 → 无新接管
        records2 = politics.execute_ai_takeover_direct_action()
        self.assertEqual(len(records2), 0)
        self.assertEqual(len(self.state.get_senate_direct_actions()), 1)


if __name__ == "__main__":
    unittest.main()
