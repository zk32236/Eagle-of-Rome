# src/tests/test_api/test_ga_dto_exposure.py
"""WP-G GA：DTO 权威接管可用性暴露（Q 件 J / M 件 §2，R-01）→ R5 卡投影改写。

R5 supersede（Plan §4.2 L10；SA §5.1）：`takeover_options` / `continue_options` /
`can_takeover` / `can_continue` 键退役——War 生命周期事实统一经 `get_senate_view`.`war_cards`
（§2.1 五事实 + `defaults` + `commander_candidates` + `allowed_modes`）。

保留反例：现任 Commander 不可被任意替换（defaults 保留现任）；commander 有效性经
`is_war_commander_valid` 判定；无执政官 → 无提名权（SUBMIT_NOT_AUTHORIZED / defaults None）。
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

    def _card(self, war_id):
        for card in self._view()["war_cards"]:
            if card["war_id"] == war_id:
                return card
        raise AssertionError(f"card missing: {war_id}")

    def test_takeover_options_include_p1_and_p2(self):
        """Q 件 J → R5：war_cards 含 P1（pending-peace）与 P2（commanderless ACTIVE），
        各卡带 defaults/候选/模式能力（替代旧 takeover_options）。"""
        war1 = War(id="w_truce", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        war1.status = WarStatus.TRUCE
        war1.commander_id = 2
        war1.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war1)
        war2 = War(id="w_active", name="Active War", war_type=WarType.FOREIGN, strength=5)
        war2.status = WarStatus.ACTIVE
        war2.commander_id = None
        self.state._war_system._active_wars.append(war2)

        data = self._view()
        self.assertNotIn("takeover_options", data)
        self.assertNotIn("can_takeover", data)
        ids = [c["war_id"] for c in data["war_cards"]]
        self.assertIn("w_truce", ids)
        self.assertIn("w_active", ids)

        truce_card = self._card("w_truce")
        self.assertEqual(truce_card["classification"], "pending_peace")
        self.assertEqual(truce_card["allowed_modes"], ["command", "peace"])
        self.assertIs(truce_card["peace_capability"], True)
        self.assertIn("defaults", truce_card)
        self.assertIn("commander_candidates", truce_card)

        active_card = self._card("w_active")
        self.assertEqual(active_card["classification"], "ongoing")
        self.assertIsNone(active_card["current_commander_id"])
        self.assertEqual(active_card["defaults"]["target_commander_id"], self.consul.id)

    def test_takeover_options_exclude_valid_commander_active(self):
        """禁 ACTIVE+valid commander 任意接管（F 件 §5.1）→ R5：卡默认保留现任指挥官。"""
        war = War(id="w_valid", name="Valid War", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.old_cmd.is_absent = False
        self.old_cmd.office = "consul"
        self.state._war_system._active_wars.append(war)
        card = self._card("w_valid")
        self.assertEqual(card["current_commander_id"], 2)
        self.assertEqual(card["defaults"]["target_commander_id"], 2)  # 禁静默替换

    def test_continue_options_only_valid_commander(self):
        """A5 → R5：pending-peace 卡默认现任 Commander；commanderless ACTIVE 卡默认 Consul。"""
        self.old_cmd.office = "consul"
        war_t = War(id="w_ct", name="Continue Truce", war_type=WarType.FOREIGN, strength=5)
        war_t.status = WarStatus.TRUCE
        war_t.commander_id = 2
        war_t.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war_t)
        war_a = War(id="w_ca", name="Active No", war_type=WarType.FOREIGN, strength=5)
        war_a.status = WarStatus.ACTIVE
        war_a.commander_id = None
        self.state._war_system._active_wars.append(war_a)

        truce_card = self._card("w_ct")
        self.assertEqual(truce_card["classification"], "pending_peace")
        self.assertEqual(truce_card["current_commander_id"], 2)
        self.assertEqual(truce_card["defaults"]["target_commander_id"], 2)
        self.assertIn("reinforcement_n", truce_card["defaults"])

        active_card = self._card("w_ca")
        self.assertIsNone(active_card["current_commander_id"])
        self.assertEqual(active_card["defaults"]["target_commander_id"], self.consul.id)
        self.assertNotIn("peace", active_card["allowed_modes"])

    def test_continue_options_exclude_dead_commander(self):
        """无有效 commander（阵亡）→ is_war_commander_valid False；dead 不入候选池。"""
        war = War(id="w_cd", name="Dead Cmd", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.old_cmd.is_dead = True
        self.state._war_system._truce_wars.append(war)

        self.assertFalse(PoliticalSystem(self.state).is_war_commander_valid(war))
        card = self._card("w_cd")
        self.assertNotIn(2, [c["figure_id"] for c in card["commander_candidates"]])
        self.assertEqual(card["classification"], "pending_peace")

    def test_can_takeover_requires_consul(self):
        """无执政官 → 无提名权（cards 默认目标 None；整包提交 SUBMIT_NOT_AUTHORIZED）。"""
        war = War(id="w_noc", name="No Consul", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        self.consul.office = None
        card = self._card("w_noc")
        self.assertIsNone(card["defaults"]["target_commander_id"])
        result = senate_api.propose_many(self.state, "player1", {"war_drafts": [
            {"war_id": "w_noc", "checked": True, "mode": "command",
             "target_commander_id": 1, "reinforcement_n": 0}]})
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED",
                      [e.get("code") for e in (result.get("errors") or [])])


if __name__ == "__main__":
    unittest.main()
