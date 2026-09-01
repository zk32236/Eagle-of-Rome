# src/tests/test_api/test_ga_treaty_gate.py
"""WP-G GA：条约仅 STALEMATE（G1-08 / R-07）CLI+GUI 双路径测试。

覆盖（S14/S17 系）：
- CLI `_maybe_generate_treaty`：仅 STALEMATE 生成（VICTORY/DEFEAT/DISASTER/TRIUMPH fail-closed）
- GUI `_generate_peace_treaty`：仅 "draw"（STALEMATE 归一）生成（fail-closed 守卫）
- `_generate_peace_treaty` 内部守卫：victory/defeat/disaster/triumph → None
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api
from src.ui.commands.phase_combat import CombatCommand
from src.core.deciders.peace_treaty_decider import PeaceTreatyDecider
from src.core.localization import TerminologyService


class TestGaTreatyGate(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for ph in ["mortality", "revenue", "forum", "population", "senate"]:
            self.state.mark_phase_executed(ph)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.war = War(id="w_gate", name="Gate War", war_type=WarType.FOREIGN,
                       strength=5, threat_level=3, disaster_numbers=[12])
        self.state._war_system._active_wars.append(self.war)

    # ---------- CLI 路径（C1） ----------
    def test_cli_only_stalemate_generates(self):
        """CLI：仅 STALEMATE 调用 decide_treaty/enter_truce；其余结果 fail-closed。"""
        mock_decider = MagicMock(spec=PeaceTreatyDecider)
        mock_decider.decide_treaty.return_value = {
            "indemnity": 0, "duration": 3, "generated_turn": 1,
        }
        cmd = CombatCommand(self.state, peace_treaty_decider=mock_decider)
        ws = self.state._war_system
        terms = TerminologyService.get()

        cmd._maybe_generate_treaty(ws, self.war, "STALEMATE", terms)
        self.assertEqual(mock_decider.decide_treaty.call_count, 1)
        self.assertIn(self.war, ws._truce_wars)
        self.assertEqual(self.war.status, WarStatus.TRUCE)

        for result in ("TRIUMPH", "VICTORY", "DEFEAT", "DISASTER"):
            cmd._maybe_generate_treaty(ws, self.war, result, terms)
        self.assertEqual(mock_decider.decide_treaty.call_count, 1)  # 无新增

    # ---------- GUI 路径（G1） ----------
    def test_gui_generate_only_draw(self):
        """GUI `_generate_peace_treaty`：仅 "draw"（STALEMATE）生成条约。"""
        war = War(id="w_draw", name="Draw War", war_type=WarType.FOREIGN, strength=14)
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        treaty = combat_api._generate_peace_treaty(war, "draw", self.state)
        self.assertIsNotNone(treaty)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(treaty["indemnity"], 0)
        self.assertEqual(treaty["duration"], 3)  # duration_stalemate

    def test_gui_generate_fail_closed_non_draw(self):
        """GUI：victory/defeat/disaster/triumph → None（fail-closed，R-07）。"""
        for result in ("triumph", "victory", "defeat", "disaster"):
            war = War(id=f"w_{result}", name=result, war_type=WarType.FOREIGN, strength=5)
            war.status = WarStatus.ACTIVE
            self.state._war_system._active_wars.append(war)
            treaty = combat_api._generate_peace_treaty(war, result, self.state)
            self.assertIsNone(treaty, f"{result} 不应生成条约")
            self.assertEqual(war.status, WarStatus.ACTIVE)
            self.assertNotIn(war, self.state._war_system._truce_wars)

    def test_do_combat_action_draw_generates_treaty(self):
        """GUI do_combat_action：draw → TRUCE + pending treaty（S14）。"""
        from unittest.mock import patch
        war = War(id="w_combat_draw", name="Combat Draw", war_type=WarType.FOREIGN,
                  strength=14, threat_level=3, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 0
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        commander = MagicMock(id=1, martial=6, influence=0)
        self.state.add_member(commander)
        player = MagicMock(player_id="p1", faction_id="optimates", player_type="human")
        self.state.add_player(player)
        self.state.set_current_player("p1")
        with patch.object(combat_api.random, "randint", return_value=7):
            result = combat_api.do_combat_action(self.state, "p1", war.id, "attack")
        self.assertTrue(result["success"])
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.peace_treaty["status"], "pending")


if __name__ == "__main__":
    unittest.main()
