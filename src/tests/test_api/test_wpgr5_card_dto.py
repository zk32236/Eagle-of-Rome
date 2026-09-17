# src/tests/test_api/test_wpgr5_card_dto.py
"""WP-G-R5 DA-1 (§2.1/§2.2/§2.4) — War Card View / DTO 默认值与候选。

覆盖 Owner §20 #1 / #3 / #4 / #5 / #15；设计契约 §2.1（五事实）、§2.2（分类/defaults）、
§2.4（候选 producer）、§5.1（DTO `war_cards`）。
"""
import unittest

from src.api import senate_api
from src.core.systems.political_system import PoliticalSystem

from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, card_by_war,
)


class TestWarCardDefaults(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base(turn_number=1)
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _cards(self):
        return self.ps.build_war_card_views({"current_turn": 1, "consul_id": self.ctx["consul_id"]})

    def test_defaults_unchecked(self):
        """§20 #1：所有卡默认 unchecked（checked=False, mode=command）。"""
        for card in self._cards():
            self.assertIs(card["defaults"]["checked"], False, card["war_id"])
            self.assertEqual(card["defaults"]["mode"], "command", card["war_id"])

    def test_existing_defaults(self):
        """§20 #3：existing War 默认现任 Commander；commanderless → 当前 Consul。"""
        cards = self._cards()
        ongoing = card_by_war(cards, FIXED["war_ongoing"])
        self.assertEqual(ongoing["defaults"]["target_commander_id"], self.ctx["cmd_a"].id)
        self.assertEqual(ongoing["classification"], "ongoing")

        # commanderless real war → 默认当前 Consul
        self.ctx["war_ongoing"].commander_id = None
        cards = self._cards()
        ongoing = card_by_war(cards, FIXED["war_ongoing"])
        self.assertEqual(ongoing["defaults"]["target_commander_id"], self.ctx["consul_id"])

    def test_active_defaults(self):
        """§20 #4：新战（active-declaration candidate）默认当前 Consul 且 N=4。"""
        cards = self._cards()
        threat = card_by_war(cards, FIXED["war_threat"])
        self.assertEqual(threat["classification"], "active_declaration")
        self.assertEqual(threat["defaults"]["target_commander_id"], self.ctx["consul_id"])
        self.assertEqual(threat["defaults"]["reinforcement_n"], 4)

    def test_ongoing_defaults(self):
        """§20 #5：existing War 默认 N=0。"""
        cards = self._cards()
        ongoing = card_by_war(cards, FIXED["war_ongoing"])
        self.assertEqual(ongoing["defaults"]["reinforcement_n"], 0)

    def test_peace_card_capability(self):
        """§2.2：pending-peace 卡 allowed_modes=[command,peace]，peace_capability=True。"""
        cards = self._cards()
        peace = card_by_war(cards, FIXED["war_peace"])
        self.assertEqual(peace["classification"], "pending_peace")
        self.assertIs(peace["peace_capability"], True)
        self.assertEqual(peace["allowed_modes"], ["command", "peace"])
        self.assertEqual(peace["defaults"]["target_commander_id"], self.ctx["cmd_b"].id)
        self.assertEqual(peace["defaults"]["reinforcement_n"], 0)

    def test_passive_classification(self):
        """§2.2：本会期新被动爆发 → passive_declaration（defaults Consul/N=4）。"""
        cards = self._cards()
        passive = card_by_war(cards, FIXED["war_passive"])
        self.assertEqual(passive["classification"], "passive_declaration")
        self.assertEqual(passive["defaults"]["target_commander_id"], self.ctx["consul_id"])
        self.assertEqual(passive["defaults"]["reinforcement_n"], 4)

    def test_legacy_unknown_origin_projects_ongoing(self):
        """§2.2/DD-02：无 origin 的真实 War → legacy_unknown → ongoing（不猜 N=4）。"""
        self.ctx["war_ongoing"]._activation_origin = None
        cards = self._cards()
        ongoing = card_by_war(cards, FIXED["war_ongoing"])
        self.assertEqual(ongoing["activation_origin"], "legacy_unknown")
        self.assertEqual(ongoing["classification"], "ongoing")
        self.assertEqual(ongoing["defaults"]["reinforcement_n"], 0)

    def test_seven_fields_present(self):
        """§2.1：WarCardView 必需字段齐备 + view_revision。"""
        cards = self._cards()
        self.assertTrue(cards)
        required = {
            "war_id", "war_name", "classification", "is_real_war", "war_status",
            "activation_origin", "activation_turn", "current_commander_id",
            "current_commander_label", "surviving_legion_count", "peace_capability",
            "commander_candidates", "defaults", "allowed_modes", "view_revision",
        }
        for card in cards:
            self.assertTrue(required.issubset(set(card.keys())), card.get("war_id"))


class TestWarCardDto(unittest.TestCase):
    def test_war_cards_key_in_senate_view(self):
        """§5.1：get_senate_view 暴露 war_cards（含 view_revision）。"""
        ctx = build_r5_base()
        view = senate_api.get_senate_view(ctx["state"], ctx["player_id"])
        self.assertTrue(view["success"], view.get("message"))
        self.assertIn("war_cards", view["data"])
        cards = view["data"]["war_cards"]
        self.assertTrue(cards)
        for card in cards:
            self.assertIn("view_revision", card)


class TestCommanderCandidates(unittest.TestCase):
    def setUp(self):
        self.ctx = build_r5_base(with_governor=True)
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def test_governor_excluded(self):
        """§20 #15 / §2.4：现任 Province governor 不出现在 Commander candidates。"""
        rows = self.ps.build_war_commander_candidates({})
        ids = [r["figure_id"] for r in rows]
        self.assertNotIn(self.ctx["cmd_gov"].id, ids, "现任总督必须被排除")
        # Consul + 两名 ex- 将 eligible
        self.assertIn(self.ctx["consul_id"], ids)

    def test_absent_not_excluded(self):
        """§2.4：军事 absent 本身不排除候选。"""
        self.ctx["cmd_a"].is_absent = True
        rows = self.ps.build_war_commander_candidates({})
        ids = [r["figure_id"] for r in rows]
        self.assertIn(self.ctx["cmd_a"].id, ids)

    def test_tribune_excluded(self):
        """§2.4：现任 Tribune 不可为 Commander 候选。"""
        self.ctx["cmd_b"].office = "tribune"
        rows = self.ps.build_war_commander_candidates({})
        ids = [r["figure_id"] for r in rows]
        self.assertNotIn(self.ctx["cmd_b"].id, ids)

    def test_ordered_by_figure_id(self):
        rows = self.ps.build_war_commander_candidates({})
        ids = [r["figure_id"] for r in rows]
        self.assertEqual(ids, sorted(ids))


if __name__ == "__main__":
    unittest.main()
