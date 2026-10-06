# src/tests/test_api/test_wpj_groupb_senate_veto_attribution.py
"""WP-J Group B-2 (J-AC-02 / BL-R2-01) — 保民官否决归属绑权威 veto_control_mode。

DATA(PRODUCTION_CHAIN)：真实 senate 链（politics.resolve_veto_control → senate_api.get_senate_view），
断言 FC-B08/B09/B10/B12/B13 的权威 actor/source 投影（HUMAN/AI/NONE）+ Store 只读透传。
"""
import unittest

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from unittest.mock import MagicMock


class _VetoAttributionBase(unittest.TestCase):
    """optimates(player1) 持 consul；populares(player2) 持 tribune（同 WP-D-R2 配方）。"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)

        self.tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(self.tribune)
        self.faction2.member_ids.append(3)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]

    def _view(self, viewer_id):
        result = senate_api.get_senate_view(self.state, viewer_id)
        self.assertTrue(result["success"], result.get("message"))
        return result["data"]

    def _enter_veto_step(self, current_player="player2", count=2):
        self.state.senate_proposal_decision_complete = True
        for _ in range(count):
            pid = self.state.add_senate_proposal(
                {"type": "land", "act_type": "distribution", "amount_C": 10, "percent": 0.1}
            )
            self.state.record_senate_vote("player1", pid, True)
            self.state.record_senate_vote("player2", pid, True)
        self.state._current_player_id = current_player


class TestVetoControlModeProjection(_VetoAttributionBase):
    def test_human_when_viewer_holds_eligible_tribune(self):
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "HUMAN")
        self.assertEqual(data["veto_actor"], 3)

    def test_ai_when_viewer_lacks_tribune(self):
        data = self._view("player1")
        self.assertEqual(data["veto_control_mode"], "AI")
        self.assertEqual(data["veto_actor"], 3)

    def test_none_when_no_eligible_tribune(self):
        self.tribune.is_dead = True
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "NONE")

    def test_mode_independent_of_can_veto_availability_bit(self):
        """归属（mode）不随可用性位（can_veto）变化——执行后/results/非当前步不塌 AI。

        viewer=player2（持 tribune）→ mode 恒 HUMAN；即便当前步非 tribune_veto（can_veto=False），
        mode 仍 HUMAN。这正是 FC-B10 根因修复（旧 tribuneActionText 绑 canManuallySelectSenateVeto）。
        """
        data = self._view("player2")
        self.assertEqual(data["veto_control_mode"], "HUMAN")
        self.assertFalse(data.get("can_veto", False))
        # 进入 tribune_veto 步后，mode 不变（仍 HUMAN）
        self._enter_veto_step(current_player="player2")
        data2 = self._view("player2")
        self.assertEqual(data2["veto_control_mode"], "HUMAN")
        self.assertTrue(data2.get("can_veto", False))


class TestStoreVetoControlMode(_VetoAttributionBase):
    def _store_mode(self, viewer_id):
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(self.state)
        store._viewer_id = viewer_id
        store._refresh_senate_view()
        return store.senateVetoControlMode

    def test_store_passthrough_human(self):
        self.assertEqual(self._store_mode("player2"), "HUMAN")

    def test_store_passthrough_ai(self):
        self.assertEqual(self._store_mode("player1"), "AI")

    def test_store_passthrough_none(self):
        self.tribune.is_dead = True
        self.assertEqual(self._store_mode("player2"), "NONE")

    def test_store_defaults_none_when_field_missing(self):
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(self.state)
        store._senate_view = {}          # 缺 veto_control_mode → 不伪造 actor（FC-B12）
        self.assertEqual(store.senateVetoControlMode, "NONE")


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
