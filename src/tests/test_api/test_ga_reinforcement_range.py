# src/tests/test_api/test_ga_reinforcement_range.py
"""WP-G GA：Reinforcement N 值域契约（G 件 §4 / G1-23 / G1-24 / G1-17，A3）测试。

覆盖 S23/S24/S25：
- 池>0 → {min:1, max:pool, default:1, allowed:range(1..pool), zero_pool_exception:False}
- 池=0 → {min:0, max:0, default:0, allowed:[0], zero_pool_exception:True}
- 国库不参与上限（S25）：treasury=0 时值域不变、征召照扣可致国库为负
- API takeover_war 的 N 重校验（fail-closed）
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


class TestGaReinforcementRange(unittest.TestCase):
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
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"

    def _make_commanderless_active_war(self, war_id="w1"):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        return war

    def test_range_pool_positive(self):
        """S23：池>0 → min=1, max=pool, default=1, allowed=range(1..pool)。"""
        war = self._make_commanderless_active_war()
        rng = senate_api.reinforcement_range(self.state, war)
        pool = len(self.state.get_military_system().get_available_legions())
        self.assertEqual(pool, 25)
        self.assertEqual(rng["min"], 1)
        self.assertEqual(rng["max"], 25)
        self.assertEqual(rng["default"], 1)
        self.assertEqual(rng["allowed"], list(range(1, 26)))
        self.assertFalse(rng["zero_pool_exception"])

    def test_range_zero_pool_exception(self):
        """S24：池=0 → min=0, max=0, allowed=[0], zero_pool_exception=True。"""
        ms = self.state._military_system
        for num in range(1, 26):
            ok, _ = ms.recruit_legion(num)
            assert ok
        war = self._make_commanderless_active_war()
        rng = senate_api.reinforcement_range(self.state, war)
        self.assertEqual(rng["min"], 0)
        self.assertEqual(rng["max"], 0)
        self.assertEqual(rng["default"], 0)
        self.assertEqual(rng["allowed"], [0])
        self.assertTrue(rng["zero_pool_exception"])

    def test_range_treasury_irrelevant(self):
        """S25：国库不参与上限——treasury=0 时值域不变（G1-17/R-10）。"""
        self.state._treasury = 0
        war = self._make_commanderless_active_war()
        rng = senate_api.reinforcement_range(self.state, war)
        self.assertEqual(rng["max"], 25)
        self.assertEqual(rng["min"], 1)

    def test_takeover_with_zero_treasury_succeeds_and_goes_negative(self):
        """S25：国库 0 时接管 + N=1 成功，征召扣款照扣（国库可为负）。"""
        self.state._treasury = 0
        war = self._make_commanderless_active_war()
        result = senate_api.takeover_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertTrue(result["success"])
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertEqual(self.state._treasury, -10)  # 征召费 10 照扣

    def test_api_rejects_n_out_of_allowed(self):
        """API 层 fail-closed：N 超出 allowed → 拒绝。"""
        war = self._make_commanderless_active_war()
        for bad_n in (-1, 0, 26, 100):
            result = senate_api.takeover_war(self.state, "player1", war.id, reinforcement_n=bad_n)
            self.assertFalse(result["success"], f"N={bad_n} 应被拒绝")
            self.assertIsNone(war.commander_id)
        # 合法 N 成功
        result = senate_api.takeover_war(self.state, "player1", war.id, reinforcement_n=2)
        self.assertTrue(result["success"])
        self.assertEqual(len(war.legion_numbers), 2)

    def test_api_none_n_defaults_to_min(self):
        """N 缺省 → default（min=1）。"""
        war = self._make_commanderless_active_war()
        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["reinforcement_n"], 1)


if __name__ == "__main__":
    unittest.main()
