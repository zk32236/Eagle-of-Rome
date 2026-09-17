# src/tests/test_api/test_wp05_takeover.py
"""WP-05 战争接管（DEV-13）API 层测试 —— R5 统一整包入口改写。

R5 supersede（Plan §4.2 L1；SA §1.2 SUPERSEDED + §3.8；DA-2/DA-4）：旧独立 `senate_api.takeover_war`
（reserve/submit 单槽锁 T）退役——「出征任命/继续作战」统一经唯一整包入口
`senate_api.propose_many`（Core `submit_proposal_package`）提交 War Card command 草案；Submit
零军事写，部署唯一 owner = Senate→Combat 边界 `advance_senate_phase`（receipt exactly-once）。

保留反例：无效 actor / 无执政官 → SUBMIT_NOT_AUTHORIZED；非法 target → COMMANDER_* 拒绝；
Submit 零部署；重入不重复发布；边界前 R 公示不含军事 direct_actions。
"""
import os
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


class _PassVoteDecider:
    """R5 边界测试用：所有议题均通过。"""

    def decide_vote(self, issue, faction, state):
        return True


def _codes(result):
    return [e.get("code") for e in (result.get("errors") or [])]


class TestWP05Takeover(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._treasury = 500

        self.state._war_system = WarSystem(self.state)
        self.state._war_system.load_wars_from_json("wars.json")
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

    def _add_active_war(self, war_id="war_takeover", name="接管测试战争",
                        commander_id=None, status=WarStatus.ACTIVE):
        war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5,
                  naval_required=False)
        war.status = status
        war.commander_id = commander_id
        self.state.get_war_system()._active_wars.append(war)
        return war

    def _submit_command(self, war, target, n=0, request_id=None, actor="player1"):
        env = {"war_drafts": [{"war_id": war.id, "checked": True, "mode": "command",
                               "target_commander_id": target, "reinforcement_n": n}]}
        if request_id:
            env["submit_request_id"] = request_id
        return senate_api.propose_many(self.state, actor, env)

    # ------------------------------------------------------------------ #

    def test_wp05_takeover_permission(self):
        """R5（Plan §4.2 L1；SA §1.2 SUPERSEDED）：任命权经整包入口身份门——无效 actor /
        无执政官 / 执政官 absent → SUBMIT_NOT_AUTHORIZED（fail-closed，零发布/零部署）。"""
        war = self._add_active_war()

        result = self._submit_command(war, 1, actor="player2")  # populares 仅有 tribune
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED", _codes(result))
        self.assertIsNone(war.commander_id)
        self.assertEqual(len(self.state.get_senate_proposals()), 0)

        self.consul.office = None
        result = self._submit_command(war, 1)
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED", _codes(result))
        self.assertIsNone(war.commander_id)

        self.consul.office = "consul"
        self.consul.is_absent = True
        result = self._submit_command(war, 1)
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED", _codes(result))
        self.assertIsNone(war.commander_id)
        self.assertEqual(len(self.state.get_senate_proposals()), 0)

    def test_wp05_takeover_executable(self):
        """R5：不可提案 War / 非法 Commander target → 整包拒绝（零发布）。"""
        result = self._submit_command(War(id="no_such", name="x", war_type=WarType.FOREIGN,
                                          strength=1), 1)
        self.assertFalse(result["success"])
        self.assertTrue({"WAR_TARGET_INVALID", "WAR_NOT_PROPOSABLE"} & set(_codes(result)))

        war = self._add_active_war(war_id="war_bad_target")
        result = self._submit_command(war, 9999)
        self.assertFalse(result["success"])
        self.assertIn("COMMANDER_TARGET_INVALID", _codes(result))
        self.assertIsNone(war.commander_id)

    def test_wp05_takeover_execute(self):
        """AC-04/05 → R5：commanderless ACTIVE 卡 command 草案 → Submit 零部署 → resolve
        （R 公示 war_proposal「获批 · 待边界执行」，D ∅）→ 边界原子部署 + receipt 恰一次。"""
        war = self._add_active_war()

        view_before = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view_before["success"])
        self.assertNotIn("takeover_options", view_before["data"])
        card = next(c for c in view_before["data"]["war_cards"] if c["war_id"] == war.id)
        self.assertIsNone(card["current_commander_id"])
        self.assertIn("command", card["allowed_modes"])

        result = self._submit_command(war, self.consul.id, n=1)
        self.assertTrue(result["success"], result.get("errors"))
        # Submit 零部署（R5：旧「Submit 锁 T」由提案冻结承担）
        self.assertIsNone(war.commander_id)
        self.assertFalse(war.legion_numbers)
        self.assertFalse(self.consul.is_absent)
        self.assertIs(self.state.senate_proposal_decision_complete, True)

        resolved = senate_api.resolve_senate(self.state, vote_decider=_PassVoteDecider())
        self.assertTrue(resolved["success"], resolved.get("message"))
        ann = resolved["data"]["public_announcement"]
        self.assertEqual(len(ann["enacted_proposals"]), 1)
        self.assertIn("待边界执行", ann["enacted_proposals"][0]["title"])
        self.assertEqual(ann["direct_actions"], [], "边界前 R 公示不含军事 direct_actions")

        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertTrue(war.legion_numbers)
        self.assertTrue(self.consul.is_absent)
        receipt = self.state.get_war_execution_receipt_for_session(
            self.state.get_senate_session())
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["status"], "COMMITTED")

        view_after = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view_after["success"])
        self.assertEqual(len(view_after["data"]["direct_actions"]), 1)

    def test_wp05_takeover_direct_not_proposal(self):
        """AC-01 → R5：无独立接管直连——checked command 必须经整包进入 proposal 链
        （可投票/可 veto），不再绕过元老院。"""
        war = self._add_active_war()
        proposals_before = len(self.state.get_senate_proposals())
        vetoes_before = len(self.state.get_senate_vetoes_copy())

        result = self._submit_command(war, self.consul.id, n=0)
        self.assertTrue(result["success"], result.get("errors"))
        props = self.state.get_senate_proposals()
        self.assertEqual(len(props), proposals_before + 1)
        self.assertEqual(props[-1]["type"], "war_proposal")
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), vetoes_before)

        # 保留反例：spec 无 takeover 语义
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        spec_path = os.path.join(project_root, "docs", "00_产品文档", "specifications", "MVP0.5-09_保民官否决权.md")
        with open(spec_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertNotIn("战争接管", content)
        self.assertNotIn("takeover", content)

    def test_wp05_takeover_reentry(self):
        """R5：Submit 零部署；重入（异 request id）→ PACKAGE_ALREADY_SUBMITTED，Commander/
        legions 零变化（部署仅边界）。"""
        war = self._add_active_war()
        first = self._submit_command(war, self.consul.id, n=1, request_id="req-a")
        self.assertTrue(first["success"], first.get("errors"))
        self.assertIsNone(war.commander_id)
        legions_after_first = list(war.legion_numbers)

        second = self._submit_command(war, self.consul.id, n=1, request_id="req-b")
        self.assertFalse(second["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", _codes(second))
        self.assertIsNone(war.commander_id)
        self.assertEqual(list(war.legion_numbers), legions_after_first)

    def test_wp05_takeover_resolve_announcement_direct_action(self):
        """WP-D AU-5/AU-6 场景 I → R5：整包 command → resolve（war_proposal 进 R 公示，D ∅）
        → 边界 advance 部署恰一次（receipt 唯一载体）。"""
        war = self._add_active_war()

        result = self._submit_command(war, self.consul.id, n=1)
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(len(self.state.get_senate_proposals()), 1)
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), 0)

        resolved = senate_api.resolve_senate(self.state, vote_decider=_PassVoteDecider())
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual(len(announcement["enacted_proposals"]), 1)
        self.assertEqual(announcement["direct_actions"], [], "边界 D 不回溯 R 公示快照")

        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        receipt = self.state.get_war_execution_receipt_for_session(
            self.state.get_senate_session())
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["status"], "COMMITTED")

        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        self.assertEqual(view["data"]["current_step"], "results")
        self.assertEqual(len(view["data"]["direct_actions"]), 1)


if __name__ == "__main__":
    unittest.main()
