# src/tests/test_api/test_ga_continue_command.py
"""WP-G GA：Continue Existing Command（G1-21 / F 件 §2.2 / T8）测试。

覆盖：
- Continue 全流（S20）：清条约 + TRUCE→ACTIVE + 现有 commander 保留（禁静默替换）
  + 保留幸存 + 征召 N + 新军团 bind 现有 commander
- fail-closed：TRUCE 无 pending / 无有效 commander / 非 TRUCE → False
- N 值域（S22/S23/S24）
- human API continue_war：权限 + 可执行校验 + N 校验 + direct action provenance
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


class TestGaContinueCommand(unittest.TestCase):
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

        self.commander = Figure(id=2, name="现任指挥官", faction_id="optimates", age=50)
        self.commander.office = "consul"  # TRUCE 后保留的指挥官（出征在外的执政官，H 件绑定有效）
        self.commander.is_absent = True
        self.state.add_member(self.commander)
        self.faction.member_ids.append(2)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"

    def _make_truce_war(self, war_id="w1", commander_id=2, legions=(1, 2)):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        war.commander_id = commander_id
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        for num in legions:
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war(list(legions), war.id, commander_id)
        return war

    def test_continue_full_flow_preserves_commander(self):
        """S20：Continue 全流——条约清 + ACTIVE + 现有 commander 保留 + 幸存保留 + N 征召 bind 现有。"""
        war = self._make_truce_war()
        ms = self.state._military_system
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=2)
        self.assertTrue(ok)
        # 条约清 + TRUCE→ACTIVE
        self.assertIsNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, self.state._war_system.get_active_wars())
        # 现有 commander 保留（禁静默替换，G1-21）
        self.assertEqual(war.commander_id, 2)
        # 幸存保留（S22：禁裁员）
        surviving = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving), 4)  # 幸存 2 + 征召 2
        for leg in surviving:
            self.assertEqual(leg.commander_id, 2)  # 全部绑定现有 commander
        # 新 Consul 未被置位 absent（未出征）
        self.assertFalse(self.consul.is_absent)

    def test_continue_fail_closed_no_pending(self):
        """fail-closed：TRUCE 无 pending treaty → False。"""
        war = War(id="w_np", name="NoPending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        self.state._war_system._truce_wars.append(war)
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_continue_fail_closed_no_valid_commander(self):
        """fail-closed：无有效 commander → False（可考虑接管）。"""
        war = self._make_truce_war(war_id="w_nc", commander_id=None)
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_continue_fail_closed_not_truce(self):
        """fail-closed：非 TRUCE 状态 → False。"""
        war = War(id="w_active", name="Active", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.state._war_system._active_wars.append(war)
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=1)
        self.assertFalse(ok)

    def test_continue_zero_pool_exception(self):
        """S24：池=0 & N=0 → Continue 接受。"""
        ms = self.state._military_system
        war = self._make_truce_war(war_id="w_zero")
        for num in range(3, 26):
            ok, _ = ms.recruit_legion(num)
            assert ok
        self.assertEqual(len(ms.get_available_legions()), 0)
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=0)
        self.assertTrue(ok)
        self.assertEqual(war.commander_id, 2)
        self.assertEqual(len(war.legion_numbers), 2)  # 无新增

    def test_continue_n_validation(self):
        """S23：N=0 且池>0 → 拒绝。"""
        war = self._make_truce_war(war_id="w_n0")
        ok = PoliticalSystem(self.state).execute_war_continue_direct(war, self.consul, reinforcement_n=0)
        self.assertFalse(ok)
        self.assertEqual(war.status, WarStatus.TRUCE)

    # ---------- human API 层（A2） ----------
    def test_continue_war_api_full_flow(self):
        """A2：continue_war API 全流 + direct action provenance（action_type=continue + N）。"""
        war = self._make_truce_war(war_id="w_api")
        result = senate_api.continue_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["war_id"], war.id)
        self.assertEqual(result["data"]["commander_id"], 2)
        self.assertEqual(result["data"]["reinforcement_n"], 1)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        actions = self.state.get_senate_direct_actions()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_type"], "continue")
        self.assertEqual(actions[0]["war_id"], war.id)
        self.assertEqual(actions[0]["commander_id"], 2)
        self.assertEqual(actions[0]["reinforcement_n"], 1)
        self.assertEqual(actions[0]["previous_status"], "truce")
        self.assertEqual(actions[0]["resulting_status"], "active")

    def test_continue_war_api_permission(self):
        """A2：非当前玩家 → 拒绝。"""
        war = self._make_truce_war(war_id="w_perm")
        self.state._current_player_id = "playerX"
        result = senate_api.continue_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertFalse(result["success"])
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_continue_war_api_no_valid_commander(self):
        """A2：无有效 commander → 拒绝（提示可接管）。"""
        war = self._make_truce_war(war_id="w_apinc", commander_id=None)
        result = senate_api.continue_war(self.state, "player1", war.id, reinforcement_n=1)
        self.assertFalse(result["success"])
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_continue_war_api_n_out_of_range(self):
        """A2：N 超出值域 → 拒绝（fail-closed）。"""
        war = self._make_truce_war(war_id="w_apirange")
        result = senate_api.continue_war(self.state, "player1", war.id, reinforcement_n=999)
        self.assertFalse(result["success"])
        self.assertEqual(war.status, WarStatus.TRUCE)


if __name__ == "__main__":
    unittest.main()
