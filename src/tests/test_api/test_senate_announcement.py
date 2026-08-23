# src/tests/test_api/test_senate_announcement.py
"""WP-D AU-5/AU-6: Public Announcement 统一 DTO（Grill-Lite §12 / SA §六 / §16 G/H/I/J）。

规则：enacted_proposals 仅 final enacted（带关键参数）；direct_actions 为已直接生效动作；
rejected/vetoed 不进公示、留在 history（D-06）。
覆盖：H 混合结果 / G 全否决 / I 仅 takeover / J takeover + 普通提案 / _announcement_key_params per-type。
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class TestSenateAnnouncement(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)
        self.state._national_public_land = 1000

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

        self.senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
        self.senator.class_tier = ClassTier.NOBILE
        self.senator.influence = 100
        self.state.add_member(self.senator)
        self.faction1.member_ids.append(2)

        self.tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(self.tribune)
        self.faction2.member_ids.append(3)

        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]

    def _add_proposal(self, spec):
        """直接注入提案（绕过校验，spec 需含完整字段）。"""
        pid = self.state.add_senate_proposal(spec)
        self.state.record_senate_vote("player1", pid, True)
        self.state.record_senate_vote("player2", pid, True)
        return pid

    def test_announcement_key_params_per_type(self):
        """S-10：per-type 关键参数映射（值来自 authoritative proposal dict）。"""
        land = {"type": "land", "act_type": "sale", "amount_C": 300, "percent": 0.3}
        war = {"type": "war", "war_id": "w1", "legions": 6}
        budget = {"type": "budget", "contract_id": "c1", "modified_budget": 120}
        governor = {"type": "governor", "province_id": 10, "candidate_id": 5}
        peace = {"type": "peace", "war_id": "w1"}

        self.assertEqual(
            senate_api._announcement_key_params(land),
            {"act_type": "sale", "amount_C": 300, "percent": 0.3},
        )
        self.assertEqual(senate_api._announcement_key_params(war), {"war_id": "w1", "legions": 6})
        self.assertEqual(
            senate_api._announcement_key_params(budget),
            {"contract_id": "c1", "modified_budget": 120},
        )
        self.assertEqual(
            senate_api._announcement_key_params(governor),
            {"province_id": 10, "candidate_id": 5},
        )
        self.assertEqual(senate_api._announcement_key_params(peace), {"war_id": "w1"})
        self.assertEqual(senate_api._announcement_key_params({"type": "unknown"}), {})

    # ---------------- 场景 G：全通过但 Tribune 全否决 → enacted ∅ ----------------

    def test_scenario_g_all_vetoed_no_enacted(self):
        """G：enacted ∅；rejected 不进 announcement、留 history。"""
        self.state.senate_proposal_decision_complete = True
        pid = self._add_proposal({"type": "land", "act_type": "sale", "amount_C": 300, "percent": 0.3})
        self.state.record_senate_veto(pid)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual(announcement["enacted_proposals"], [])
        self.assertEqual(announcement["direct_actions"], [])

    # ---------------- 场景 H：混合（rejected + vetoed + enacted） ----------------

    def test_scenario_h_mixed_announcement_only_enacted(self):
        """H：enacted 进公示（带参数）；rejected/vetoed 不进公示、留 history。"""
        self.state.senate_proposal_decision_complete = True
        # enacted：land sale 300（双方赞成，无否决）
        pid_enacted = self._add_proposal({"type": "land", "act_type": "sale", "amount_C": 300, "percent": 0.3})
        # senate-rejected：war（双方反对）
        pid_rejected = self.state.add_senate_proposal({"type": "war", "war_id": "w1", "legions": 6, "consul_id": 1})
        self.state.record_senate_vote("player1", pid_rejected, False)
        self.state.record_senate_vote("player2", pid_rejected, False)
        # tribune-vetoed：budget（赞成但被否决）
        pid_vetoed = self.state.add_senate_proposal(
            {"type": "budget", "contract_id": "c1", "modified_budget": 120, "consul_id": 1}
        )
        self.state.record_senate_vote("player1", pid_vetoed, True)
        self.state.record_senate_vote("player2", pid_vetoed, True)
        self.state.record_senate_veto(pid_vetoed)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        enacted = announcement["enacted_proposals"]
        # 仅 enacted 进公示
        self.assertEqual([p["proposal_id"] for p in enacted], [pid_enacted])
        self.assertEqual(enacted[0]["type"], "land")
        self.assertEqual(enacted[0]["key_parameters"]["amount_C"], 300)
        self.assertIn("出售 300 C", enacted[0]["title"])

        # rejected/vetoed 留 history（view submitted_proposals result 标记）
        view = senate_api.get_senate_view(self.state, "player1")
        rows = {r["id"]: r["result"] for r in view["data"]["submitted_proposals"]}
        self.assertEqual(rows[pid_rejected], "rejected")
        self.assertEqual(rows[pid_vetoed], "rejected")

    # ---------------- 场景 I：仅 takeover ----------------

    def test_scenario_i_takeover_only(self):
        """I：仅接管 → direct_actions 进公示；无 vote/veto 痕迹；enacted ∅。"""
        war = War(id="war_takeover_i", name="接管测试战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        self.state.get_war_system()._active_wars.append(war)

        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), 0)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual(announcement["enacted_proposals"], [])
        self.assertEqual(len(announcement["direct_actions"]), 1)
        da = announcement["direct_actions"][0]
        self.assertEqual(da["action_type"], "takeover")
        self.assertEqual(da["war_id"], war.id)
        self.assertEqual(da["commander_id"], 1)

    # ---------------- 场景 J：takeover + 普通提案 ----------------

    def test_scenario_j_takeover_plus_ordinary(self):
        """J：混合公示（enacted + direct_actions 同区展示）。"""
        self.state.senate_proposal_decision_complete = True
        pid = self._add_proposal({"type": "land", "act_type": "distribution", "amount_C": 200, "percent": 0.2})

        war = War(id="war_takeover_j", name="接管测试战争J", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        self.state.get_war_system()._active_wars.append(war)
        result = senate_api.takeover_war(self.state, "player1", war.id)
        self.assertTrue(result["success"])

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual([p["proposal_id"] for p in announcement["enacted_proposals"]], [pid])
        self.assertEqual(len(announcement["direct_actions"]), 1)
        self.assertEqual(announcement["direct_actions"][0]["action_type"], "takeover")

        # view 回读（公示随 phase_result 持久化）
        view = senate_api.get_senate_view(self.state, "player1")
        pa = view["data"]["public_announcement"]
        self.assertEqual(len(pa["enacted_proposals"]), 1)
        self.assertEqual(len(pa["direct_actions"]), 1)
        # 实时 pending 列表已随 clear_senate_pending 清空；持久副本在 public_announcement
        self.assertEqual(view["data"]["direct_actions"], [])


if __name__ == "__main__":
    unittest.main()
