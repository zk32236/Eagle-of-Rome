# src/tests/test_api/test_ga_dto_exposure.py
"""WP-G GA：DTO 权威接管可用性暴露（Q 件 J / M 件 §2，R-01）测试。

覆盖：
- senate view takeover_options：P1（TRUCE+pending）∪ P2（commanderless ACTIVE）；
  排除 ACTIVE+valid commander；每项含 reason + reinforcement_range
- continue_options：TRUCE+pending+valid commander；can_continue
- can_takeover / can_continue 门控（actionable + consul）
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
from src.api import senate_api


class TestGaDtoExposure(unittest.TestCase):
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

    def _view(self):
        result = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(result["success"])
        return result["data"]

    def test_takeover_options_include_p1_and_p2(self):
        """Q 件 J：takeover_options 含 P1（TRUCE+pending）与 P2（commanderless ACTIVE）。"""
        # P1：TRUCE + pending
        war1 = War(id="w_truce", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        war1.status = WarStatus.TRUCE
        war1.commander_id = 2
        war1.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war1)
        # P2：ACTIVE + 无指挥官
        war2 = War(id="w_active", name="Active War", war_type=WarType.FOREIGN, strength=5)
        war2.status = WarStatus.ACTIVE
        war2.commander_id = None
        self.state._war_system._active_wars.append(war2)

        data = self._view()
        self.assertTrue(data["can_takeover"])
        options = {o["war_id"]: o for o in data["takeover_options"]}
        self.assertIn("w_truce", options)
        self.assertIn("w_active", options)
        for o in options.values():
            self.assertIn("reason", o)
            rng = o["reinforcement_range"]
            self.assertIn("min", rng)
            self.assertIn("max", rng)
            self.assertIn("default", rng)
            self.assertIn("allowed", rng)
            self.assertIn("zero_pool_exception", rng)

    def test_takeover_options_exclude_valid_commander_active(self):
        """禁 ACTIVE+valid commander 任意接管（F 件 §5.1）：不出现在 takeover_options。"""
        war = War(id="w_valid", name="Valid War", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.old_cmd.is_absent = False
        self.old_cmd.office = "consul"
        self.state._war_system._active_wars.append(war)
        data = self._view()
        self.assertFalse(any(o["war_id"] == "w_valid" for o in data["takeover_options"]))

    def test_continue_options_only_valid_commander(self):
        """A5：continue_options 仅 TRUCE+pending+valid commander；ACTIVE 不入列。"""
        self.old_cmd.office = "consul"  # 有效指挥官（TRUCE 保留）
        war_t = War(id="w_ct", name="Continue Truce", war_type=WarType.FOREIGN, strength=5)
        war_t.status = WarStatus.TRUCE
        war_t.commander_id = 2
        war_t.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war_t)
        war_a = War(id="w_ca", name="Active No", war_type=WarType.FOREIGN, strength=5)
        war_a.status = WarStatus.ACTIVE
        war_a.commander_id = None
        self.state._war_system._active_wars.append(war_a)

        data = self._view()
        self.assertTrue(data["can_continue"])
        cont = {o["war_id"] for o in data["continue_options"]}
        self.assertIn("w_ct", cont)
        self.assertNotIn("w_ca", cont)
        opt = next(o for o in data["continue_options"] if o["war_id"] == "w_ct")
        self.assertEqual(opt["commander_id"], 2)
        self.assertIn("reinforcement_range", opt)

    def test_continue_options_exclude_dead_commander(self):
        """无有效 commander（阵亡）→ 不入 continue_options（走 Takeover）。"""
        war = War(id="w_cd", name="Dead Cmd", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.old_cmd.is_dead = True
        self.state._war_system._truce_wars.append(war)
        data = self._view()
        self.assertFalse(any(o["war_id"] == "w_cd" for o in data["continue_options"]))
        # 但可接管（P1）
        self.assertTrue(any(o["war_id"] == "w_cd" for o in data["takeover_options"]))

    def test_can_takeover_requires_consul(self):
        """无执政官 → can_takeover/can_continue False（权限门控）。"""
        war = War(id="w_noc", name="No Consul", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        self.consul.office = None
        data = self._view()
        self.assertFalse(data["can_takeover"])
        self.assertFalse(data["can_continue"])


if __name__ == "__main__":
    unittest.main()
