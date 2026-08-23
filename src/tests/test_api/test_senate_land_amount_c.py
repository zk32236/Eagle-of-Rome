# src/tests/test_api/test_senate_land_amount_c.py
"""WP-D AU-7: Land amount_C canonical conversion（Grill-Lite D-01 / SA §七 / §16 K/L）。

覆盖：payload 主字段 amount_C（int）→ 值域校验 → 派生 percent 存储 → execute 权威消费（sale quota /
distribution act）→ _build_proposal_options 默认值（config senate_land.default_percent，缺失回退 0.10）
→ _proposal_label 参数文案 → auto_submit AI 路径 percent→amount_C clamp（P2-04）。
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


class TestSenateLandAmountC(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)
        self.state._national_public_land = 1000

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction1)
        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1"]

    # ---------------- 场景 K：land sale amount_C ----------------

    def test_land_sale_payload_and_execute_quota(self):
        """K：amount_C 进 payload → execute → set_pending_land_sale_quota(amount_C)。"""
        result = senate_api.propose(self.state, "player1", "land", act_type="sale", amount_C=300)
        self.assertTrue(result["success"])
        proposals = self.state.get_senate_proposals()
        self.assertEqual(proposals[0]["act_type"], "sale")
        self.assertEqual(proposals[0]["amount_C"], 300)
        self.assertAlmostEqual(proposals[0]["percent"], 0.3)

        executed = senate_api._political_system(self.state).execute_passed_proposal(proposals[0])
        self.assertTrue(executed["success"])
        self.assertEqual(self.state.pending_land_sale_quota, 300)

    # ---------------- 场景 L：land distribution amount_C ----------------

    def test_land_distribution_payload_and_execute_act(self):
        """L：amount_C 进 payload → execute → add_pending_land_act amount == amount_C。"""
        result = senate_api.propose(self.state, "player1", "land", act_type="distribution", amount_C=200)
        self.assertTrue(result["success"])
        proposal = self.state.get_senate_proposals()[0]
        self.assertEqual(proposal["amount_C"], 200)
        self.assertAlmostEqual(proposal["percent"], 0.2)

        executed = senate_api._political_system(self.state).execute_passed_proposal(proposal)
        self.assertTrue(executed["success"])
        acts = self.state.get_pending_land_acts()
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["type"], "distribution")
        self.assertEqual(acts[0]["amount"], 200)
        self.assertAlmostEqual(acts[0]["percent"], 0.2)

    # ---------------- 值域校验（DATA） ----------------

    def test_amount_c_validation_matrix(self):
        """K/L 负向：0 / 超公地总量 / 非整数 / percent-only → 全部权威拒绝。"""
        cases = [
            {"act_type": "sale", "amount_C": 0},
            {"act_type": "sale", "amount_C": 1001},
            {"act_type": "sale", "amount_C": 50.5},
            {"act_type": "sale", "percent": 0.1},
        ]
        for kwargs in cases:
            result = senate_api.propose(self.state, "player1", "land", **kwargs)
            self.assertFalse(result["success"], f"expected rejection for {kwargs}")
            self.assertEqual(len(self.state.get_senate_proposals()), 0)

    def test_amount_c_float_integer_tolerated(self):
        """QML JS 跨槽边界 float（300.0）→ 接受并 int 归一（D-6 同源容忍）。"""
        result = senate_api.propose(self.state, "player1", "land", act_type="sale", amount_C=300.0)
        self.assertTrue(result["success"])
        self.assertEqual(self.state.get_senate_proposals()[0]["amount_C"], 300)

    # ---------------- producer shape（R2-NEW-01 F2：root public_land + nested params.amount_C） ----------------

    def test_build_proposal_options_land_shape(self):
        """F2：land option root public_land + nested params{act_type, amount_C, percent}（不复现 RC-R2-01）。"""
        info = {
            "war_threats": [], "pending_peace_treaties": [],
            "governor_vacancies": {}, "pending_contracts": [],
        }
        options = senate_api._build_proposal_options(self.state, info)
        land_options = [o for o in options if o["type"] == "land"]
        self.assertEqual(len(land_options), 2)
        for opt in land_options:
            self.assertEqual(opt["public_land"], 1000)  # root
            self.assertIn("act_type", opt["params"])
            self.assertIn("amount_C", opt["params"])  # nested 主字段
            self.assertIn("percent", opt["params"])  # nested 派生
            self.assertNotIn("public_land", opt["params"])  # root 元数据不进 params（RC-R2-01 教训）
            self.assertEqual(opt["params"]["amount_C"], 100)  # default 10% × 1000

    def test_land_default_percent_configurable(self):
        """D-1：config economic_rules.senate_land.default_percent 可配置；缺失回退 0.10。"""
        info = {"war_threats": [], "pending_peace_treaties": [], "governor_vacancies": {}, "pending_contracts": []}
        # 缺失 → 0.10 → 100 C
        options = senate_api._build_proposal_options(self.state, info)
        sale = [o for o in options if o["key"] == "land:sale"][0]
        self.assertEqual(sale["params"]["amount_C"], 100)
        # 配置 5% → 50 C
        self.state.config.economic_rules.senate_land = {"default_percent": 0.05, "step": 1}
        options = senate_api._build_proposal_options(self.state, info)
        sale = [o for o in options if o["key"] == "land:sale"][0]
        self.assertEqual(sale["params"]["amount_C"], 50)

    def test_proposal_label_land_has_parameters(self):
        """013/023：land label 带 amount_C + 派生 %（authoritative，禁 QML 推导）。"""
        result = senate_api.propose(self.state, "player1", "land", act_type="sale", amount_C=300)
        self.assertTrue(result["success"])
        label = senate_api._proposal_label(self.state, self.state.get_senate_proposals()[0])
        self.assertIn("出售 300 C", label)
        self.assertIn("30%", label)  # 300/1000 = 30%

    # ---------------- AI 路径（S-8） ----------------

    def test_auto_submit_land_uses_amount_c(self):
        """S-8：AI land 提案 percent → amount_C（payload 主字段统一 amount_C）。"""
        from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
        mock_decider = MagicMock(spec=AutoLandProposalDecider)
        mock_decider.decide_proposal.return_value = ("sale", 0.1)
        result = senate_api.auto_submit_proposals(
            self.state, land_proposal_deciders=[mock_decider]
        )
        self.assertTrue(result["success"])
        land_proposals = [p for p in result["data"]["proposals"] if p["type"] == "land"]
        self.assertGreaterEqual(len(land_proposals), 1)
        self.assertEqual(land_proposals[0]["amount_C"], 100)  # int(1000 * 0.1)
        stored = [p for p in self.state.get_senate_proposals() if p["type"] == "land"]
        self.assertEqual(stored[0]["amount_C"], 100)

    def test_auto_submit_land_clamp_small_public_land(self):
        """P2-04：小公地量 percent→amount_C 为 0 → clamp max(1, ...) 防 0（值域 1≤amount_C）。"""
        from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
        self.state._national_public_land = 10  # int(10 * 0.05) = 0 → clamp 1
        mock_decider = MagicMock(spec=AutoLandProposalDecider)
        mock_decider.decide_proposal.return_value = ("distribution", 0.05)
        result = senate_api.auto_submit_proposals(
            self.state, land_proposal_deciders=[mock_decider]
        )
        self.assertTrue(result["success"])
        stored = [p for p in self.state.get_senate_proposals() if p["type"] == "land"]
        self.assertEqual(stored[0]["amount_C"], 1)


if __name__ == "__main__":
    unittest.main()
