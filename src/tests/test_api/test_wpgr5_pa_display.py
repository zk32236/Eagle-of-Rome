# src/tests/test_api/test_wpgr5_pa_display.py
"""WP-G-R5 DA-B3（DA-5 §5.1/§5.3）——PA 文案 + Store 只读投影（五事实分离）。

断言方向（DATA / 静态）：
- War Proposal 标签/公示文案 = 政治决议语义，禁「已宣战部署/已召回」（D-SC06）；
- 公示标题含「获批 · 待边界执行」（G7 目检素材的字符串锚点）；
- Store 暴露 senateWarCards / senateWarExecution 只读投影（D-SC01/§5.1），
  且不持有 draft 真值（draft 在 QML 局部）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.tests.fixtures.wpgr5_fixtures import build_r5_base


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


BANNED = ("已宣战部署", "已召回", "已部署")


class TestWarProposalAnnouncement(unittest.TestCase):

    def test_command_label_is_political_not_deployed(self):
        fx = build_r5_base()
        proposal = {
            "type": "war_proposal", "war_id": "threat_war", "war_label": "Threat War",
            "mode": "command",
            "payload": {"target_commander_id": 1, "target_commander_label": "Consul Aemilius",
                        "reinforcement_n": 2},
        }
        label = senate_api._proposal_label(fx["state"], proposal)
        self.assertIn("战争决议", label)
        for bad in BANNED:
            self.assertNotIn(bad, label)

    def test_peace_label_is_political_not_recalled(self):
        fx = build_r5_base()
        proposal = {
            "type": "war_proposal", "war_id": "first_punic_war", "war_label": "First Punic War",
            "mode": "peace",
            "payload": {"treaty_snapshot": {"indemnity": 80, "duration": 3,
                                            "treaty_ref": {"war_id": "first_punic_war", "version": 1}}},
        }
        label = senate_api._proposal_label(fx["state"], proposal)
        self.assertIn("停战决议", label)
        for bad in BANNED:
            self.assertNotIn(bad, label)

    def test_announcement_key_params_expose_frozen_fields(self):
        fx = build_r5_base()
        proposal = {
            "type": "war_proposal", "war_id": "threat_war", "war_label": "Threat War",
            "mode": "command",
            "payload": {"target_commander_id": 1, "target_commander_label": "Consul Aemilius",
                        "reinforcement_n": 2},
        }
        params = senate_api._announcement_key_params(proposal)
        self.assertEqual(params["war_id"], "threat_war")
        self.assertEqual(params["mode"], "command")
        self.assertEqual(params["reinforcement_n"], 2)
        self.assertEqual(params["target_commander_label"], "Consul Aemilius")

    def test_pa_enacted_title_marks_pending_boundary(self):
        src = _read("src/api/senate_api.py")
        self.assertIn("获批 · 待边界执行", src)
        for bad in BANNED:
            self.assertNotIn(f'"{bad}', src)


class TestStoreReadModels(unittest.TestCase):

    def test_store_projects_war_cards_and_receipt_only(self):
        src = _read("src/ui/gui/session_store.py")
        self.assertIn("senateWarCards", src)
        self.assertIn("senateWarExecution", src)
        # 五事实分离：Store 不持有 draft 真值（draft 仅 QML 局部 warCardDrafts）
        self.assertNotIn("senateWarCardDrafts", src)

    def test_view_exposes_war_cards_and_receipt_slot(self):
        fx = build_r5_base()
        data = senate_api.get_senate_view(fx["state"], fx["player_id"])["data"]
        self.assertIn("war_cards", data)
        cards = data["war_cards"]
        self.assertTrue(any(c["war_id"] == "threat_war" for c in cards))
        for card in cards:
            self.assertIn("defaults", card)
            self.assertIn("view_revision", card)
            self.assertEqual(card["defaults"]["checked"], False)
            self.assertIn("allowed_modes", card)


if __name__ == "__main__":
    unittest.main()
