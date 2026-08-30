# src/tests/test_api/test_senate_zero_proposal.py
"""WP-D AU-3: Zero-Proposal / Empty-Set 三路径（Grill-Lite §6 / SA §三 / §16 B/E/F/G）。

- Path A：执政官 0 提案 → decision_complete=True → step=results（0 提案跳过 vote/veto）→ resolve 空结算 → advance 可过
- Path B：投票全否决 → veto 步空集 → resolve → enacted ∅
- Path C：否决全否决 → enacted ∅
- Path E：AI 0 提案 → success + decision_complete
- C 场景（非执政官 → AI proposer）session_store 层路由 + resolve hook（P2-01）
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class TestSenateZeroProposal(unittest.TestCase):
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

    # ---------------- Path A：执政官 0 提案 ----------------

    def test_propose_many_empty_batch_sets_decision_complete(self):
        """Path A 入口：空批 → success + decision_complete=True + view step=results（0 提案跳过 vote/veto）。"""
        result = senate_api.propose_many(self.state, "player1", [])
        self.assertTrue(result["success"])
        self.assertIn("未提交法案", result["message"])
        self.assertEqual(result["data"]["created"], [])
        self.assertTrue(self.state.senate_proposal_decision_complete)

        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        self.assertEqual(view["data"]["current_step"], "results")
        self.assertFalse(view["data"]["can_vote"])

    def test_path_a_full_chain_empty_resolve_then_advance(self):
        """Path A 全链：空批 → resolve 空结算 → record_phase_result → advance_senate_phase 通过（无死锁）。"""
        feedback = senate_api.propose_many(self.state, "player1", [])
        self.assertTrue(feedback["success"])

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        self.assertEqual(resolved["data"]["passed_proposals"], [])
        self.assertEqual(resolved["data"]["rejected_proposals"], [])
        self.assertEqual(resolved["data"]["vetoed_proposals"], [])
        self.assertEqual(resolved["data"]["public_announcement"]["enacted_proposals"], [])
        self.assertEqual(resolved["data"]["public_announcement"]["direct_actions"], [])

        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"])
        self.assertEqual(adv["data"]["next_phase_id"], "combat")

    def test_view_step_states_before_and_after_decision(self):
        """状态机：未决策 → proposal；已决策为空 → results。"""
        view_before = senate_api.get_senate_view(self.state, "player1")
        self.assertEqual(view_before["data"]["current_step"], "proposal")
        self.assertFalse(self.state.senate_proposal_decision_complete)

        senate_api.propose_many(self.state, "player1", [])
        view_after = senate_api.get_senate_view(self.state, "player1")
        self.assertEqual(view_after["data"]["current_step"], "results")

    # ---------------- Path B：投票全否决（Zero Survivor） ----------------

    def test_path_b_all_rejected_zero_survivor(self):
        """Path B：全部 passed=False → zero-passed 收敛（results，跳过否决空集）→ resolve → enacted ∅；rejected 留 history。

        WP-F R2-01（Task Package §7.4）：零通过提案不进入 tribune_veto——禁止「否决空集」幽灵工作。
        """
        self.state.senate_proposal_decision_complete = True
        pid = self.state.add_senate_proposal({"type": "war", "war_id": "w1", "legions": 4, "consul_id": 1})
        self.state.record_senate_vote("player1", pid, False)
        self.state.record_senate_vote("player2", pid, False)

        view = senate_api.get_senate_view(self.state, "player1")
        # WP-F R2-01：zero-passed → current_step="results"（跳过 tribune_veto，流程直接收敛）
        self.assertEqual(view["data"]["current_step"], "results")
        self.assertEqual(view["data"]["veto_candidate_ids"], [])
        self.assertIs(view["data"]["can_advance"], True)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        self.assertEqual(resolved["data"]["passed_proposals"], [])
        self.assertEqual(resolved["data"]["rejected_proposals"], [pid])
        self.assertEqual(resolved["data"]["public_announcement"]["enacted_proposals"], [])

        # rejected 保留在 history（view submitted_proposals 标记 result=rejected）
        view2 = senate_api.get_senate_view(self.state, "player1")
        rows = view2["data"]["submitted_proposals"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["result"], "rejected")

    # ---------------- Path C：否决全否决（Zero Enacted） ----------------

    def test_path_c_all_vetoed_empty_enacted(self):
        """Path C：全部通过但全部被保民官否决 → enacted ∅；announcement 无 enacted。"""
        self.state.senate_proposal_decision_complete = True
        pid = self.state.add_senate_proposal({"type": "war", "war_id": "w1", "legions": 4, "consul_id": 1})
        self.state.record_senate_vote("player1", pid, True)
        self.state.record_senate_vote("player2", pid, True)
        self.state.record_senate_veto(pid)

        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        self.assertEqual(resolved["data"]["passed_proposals"], [])
        self.assertEqual(resolved["data"]["vetoed_proposals"], [pid])
        self.assertEqual(resolved["data"]["public_announcement"]["enacted_proposals"], [])

    # ---------------- Path E：AI 0 提案 ----------------

    def test_path_e_ai_zero_proposals(self):
        """Path E：AI proposer 0 提案 → success + decision_complete=True（空批合法）。"""
        self.state.config.testing.propose_war_chance = 0.0
        self.state.config.testing.always_declare = False
        self.state.config.political_rules.land_proposal.sale_chance = 0.0
        self.state.config.political_rules.land_proposal.distribution_chance = 0.0

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["proposals"], [])
        self.assertTrue(self.state.senate_proposal_decision_complete)

        view = senate_api.get_senate_view(self.state, "player1")
        self.assertEqual(view["data"]["current_step"], "results")

    # ---------------- C 场景：session_store 层 AI 路由 + resolve hook（P2-01） ----------------

    def test_session_store_ai_routing_and_resolve_hook(self):
        """场景 C（P2-01）：非执政官 doSubmitSenateProposals → AI proposer → 空批自动 resolve → results。"""
        from src.ui.gui.session_store import GuiSessionStore
        # 关闭全部 AI 提案源，保证 AI proposer 产出 0 提案（确定性空批）
        self.state.config.testing.propose_war_chance = 0.0
        self.state.config.testing.always_declare = False
        self.state.config.political_rules.land_proposal.sale_chance = 0.0
        self.state.config.political_rules.land_proposal.distribution_chance = 0.0
        self.state._current_player_id = "player2"
        store = GuiSessionStore(self.state)
        store.initialize("player2")

        self.assertTrue(store.canTriggerAIProposer)
        self.assertFalse(store.canCreateSenateProposal)
        self.assertFalse(store.canSelectSenateProposal)

        feedback = store.doSubmitSenateProposals([])
        self.assertTrue(feedback["success"])
        # AI proposer 已执行（0 提案）；resolve hook 已触发 → phase_result 存在 → results 步
        self.assertEqual(store.senateCurrentStep, "results")
        self.assertTrue(store.canAdvanceSenate)

    def test_session_store_consul_empty_batch_resolve_hook(self):
        """Path A（P2-01）：执政官空批 → propose_many 空批合法 → resolve hook → results 可推进。

        注：resolve_senate 内 clear_senate_pending 会重置 decision_complete 标记（其职责仅在
        提交后、结算前区分「未决策/已决策为空」）；结算后由 result_data 驱动 results 步。
        """
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(self.state)
        store.initialize("player1")

        self.assertTrue(store.canCreateSenateProposal)
        feedback = store.doSubmitSenateProposals([])
        self.assertTrue(feedback["success"])
        # 提交空批合法（无死锁）；resolve hook 已触发 → results 可推进
        self.assertEqual(store.senateCurrentStep, "results")
        self.assertTrue(store.canAdvanceSenate)


if __name__ == "__main__":
    unittest.main()
