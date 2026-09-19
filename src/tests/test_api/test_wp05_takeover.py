# src/tests/test_api/test_wp05_takeover.py
"""WP-05 战争接管（DEV-13）API 层测试 —— R5 统一整包入口改写。

R5 supersede（Plan §4.2 L1；SA §1.2 SUPERSEDED + §3.8；DA-2/DA-4）：旧独立 `senate_api.takeover_war`
（reserve/submit 单槽锁 T）退役——「出征任命/继续作战」统一经唯一整包入口
`senate_api.propose_many`（Core `submit_proposal_package`）提交 War Card command 草案；Submit
零军事写，部署唯一 owner = Senate→Combat 边界 `advance_senate_phase`（receipt exactly-once）。

保留反例：无效 actor / 无执政官 → SUBMIT_NOT_AUTHORIZED；非法 target → COMMANDER_* 拒绝；
Submit 零部署；重入不重复发布；边界前 R 公示不含军事 direct_actions。

R6 迁移（SA §A.1/§A.3，DA-1/DA-2/DA-3；WP-G-R6 DA-6 B1e）：ACTIVE/ongoing 真实 War 的
`command` 草案 route = `consul_direct`（不再产 Senate 提案）——本文件 3 条原「War command 经
整包进 proposal 链 / R 公示 war_proposal」断言迁到 **R6 direct 面**：`created` ∅ +
`consul_direct_decisions` 恰一条 FROZEN（无 `proposal_id`，不入 Vote/Veto）+ 公示 direct 行
`awaiting_boundary` + 边界 receipt 恰一次（exactly-once）。**原命题逐条保留**：直连不绕过元老院
＝ direct 决定不可投票/否决且执行仅经唯一边界；边界恰好一次。
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
        """AC-04/05 → R6：commanderless ACTIVE 卡 command 草案 ⇒ Submit 只冻结 direct 决策
        （零部署 / 零 Senate 提案）→ resolve 收敛真实 R（PA 公示 direct 行 `awaiting_boundary`，
        零 enacted_proposals）→ 边界原子部署 + receipt 恰一次。"""
        war = self._add_active_war()

        view_before = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view_before["success"])
        self.assertNotIn("takeover_options", view_before["data"])
        card = next(c for c in view_before["data"]["war_cards"] if c["war_id"] == war.id)
        self.assertIsNone(card["current_commander_id"])
        self.assertIn("command", card["allowed_modes"])

        result = self._submit_command(war, self.consul.id, n=1)
        self.assertTrue(result["success"], result.get("errors"))
        # R6 双账本：ongoing command ⇒ 无 Senate 提案（created ∅），direct 决策恰一条 FROZEN
        self.assertEqual(result["data"]["created"], [], "ongoing command ⇒ 无 Senate 提案")
        self.assertEqual(self.state.get_senate_proposals(), [])
        # Submit 零部署（R6：冻结 direct 决策承担；执行唯一 owner = 边界）
        self.assertIsNone(war.commander_id)
        self.assertFalse(war.legion_numbers)
        self.assertFalse(self.consul.is_absent)
        self.assertIs(self.state.senate_proposal_decision_complete, True)
        rec = list(self.state.get_consul_war_decisions(
            self.state.get_senate_session()).values())[0]
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")
        self.assertEqual(rec["payload"]["target_commander_id"], self.consul.id)
        self.assertEqual(rec["payload"]["reinforcement_n"], 1)
        row = next(r for r in senate_api.get_senate_view(self.state, "player1")["data"]
                   ["consul_direct_decisions"] if r["war_id"] == war.id)
        self.assertEqual(row["execution"], "awaiting_boundary", "边界前不宣称早执行")

        resolved = senate_api.resolve_senate(self.state, vote_decider=_PassVoteDecider())
        self.assertTrue(resolved["success"], resolved.get("message"))
        ann = resolved["data"]["public_announcement"]
        self.assertEqual(ann["enacted_proposals"], [], "direct 决定不入 Senate 公示（零真提案）")
        self.assertEqual(ann["direct_actions"], [], "边界前 R 公示不含军事 direct_actions")
        self.assertEqual(len(ann["consul_direct_decisions"]), 1)
        self.assertEqual(ann["consul_direct_decisions"][0]["war_id"], war.id)
        self.assertEqual(ann["consul_direct_decisions"][0]["execution"], "awaiting_boundary")

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
        # 同一 `item_ref` 在边界 receipt 后翻成 executed（身份一致，刷新可重取）
        row_after = next(r for r in view_after["data"]["consul_direct_decisions"]
                         if r["war_id"] == war.id)
        self.assertEqual(row_after["item_ref"], row["item_ref"])
        self.assertEqual(row_after["execution"], "executed")

    def test_wp05_takeover_direct_not_proposal(self):
        """AC-04 → R6（SA §A.1/§A.3，DA-1/DA-2/DA-3）：ACTIVE commanderless 真实 War + command
        ⇒ authority=`consul_direct`——**不再产生 Senate 提案**（不进 Vote/Veto 集），只冻结一条
        `ConsulWarDecision`。原命题「不绕过元老院」以 R6 新语义表达：direct 决定 **无
        proposal_id**、不可投票/否决，且执行仅经唯一 Senate→Combat 边界（无旁路军事写）。"""
        war = self._add_active_war()
        proposals_before = len(self.state.get_senate_proposals())
        vetoes_before = len(self.state.get_senate_vetoes_copy())

        result = self._submit_command(war, self.consul.id, n=0)
        self.assertTrue(result["success"], result.get("errors"))
        # R6 双账本：Senate 提案账本零增长（created ∅），direct 账本恰一条 FROZEN
        self.assertEqual(result["data"]["created"], [])
        props = self.state.get_senate_proposals()
        self.assertEqual(len(props), proposals_before)
        decisions = self.state.get_consul_war_decisions(self.state.get_senate_session())
        self.assertEqual(len(decisions), 1)
        rec = list(decisions.values())[0]
        self.assertEqual(rec["authority"], "consul_direct")
        self.assertEqual(rec["decision_state"], "FROZEN")
        self.assertEqual(rec["war_id"], war.id)
        self.assertNotIn("proposal_id", rec, "direct 决定无 proposal_id（身份空间独立）")
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), vetoes_before)
        # 元老院面：direct 决定不在提案/候选集，且不可投票（unknown/direct ID 整次拒绝，零票账写入）
        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        self.assertEqual(view["data"]["submitted_proposals"], [])
        self.assertNotIn(rec["direct_decision_id"], view["data"]["veto_candidate_ids"])
        self.assertIsNone(war.commander_id, "Submit 零部署（执行仅边界）")
        blocked = senate_api.vote(self.state, "player1", [rec["direct_decision_id"]], [True])
        self.assertFalse(blocked["success"], "direct 决定不得进入元老院投票集合")
        self.assertEqual(blocked["data"]["recorded"], 0)

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
        """WP-D AU-5/AU-6 场景 I → R6：整包 command ⇒ 冻结 direct 决策（零 Senate 提案）
        → resolve（PA 以 `consul_direct_decisions` 公示一行 `awaiting_boundary`，
        `enacted_proposals` ∅，D ∅）→ 边界 advance 部署恰一次（receipt 唯一载体）。"""
        war = self._add_active_war()

        result = self._submit_command(war, self.consul.id, n=1)
        self.assertTrue(result["success"], result.get("errors"))
        self.assertEqual(result["data"]["created"], [])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), 0)
        self.assertEqual(len(self.state.get_consul_war_decisions(
            self.state.get_senate_session())), 1)

        resolved = senate_api.resolve_senate(self.state, vote_decider=_PassVoteDecider())
        self.assertTrue(resolved["success"])
        announcement = resolved["data"]["public_announcement"]
        self.assertEqual(announcement["enacted_proposals"], [])
        self.assertEqual(announcement["direct_actions"], [], "边界 D 不回溯 R 公示快照")
        direct_rows = announcement["consul_direct_decisions"]
        self.assertEqual(len(direct_rows), 1)
        self.assertEqual(direct_rows[0]["identity"], "consul_direct_decision")
        self.assertEqual(direct_rows[0]["authority"], "consul_direct")
        self.assertEqual(direct_rows[0]["war_id"], war.id)
        self.assertEqual(direct_rows[0]["target_commander_id"], self.consul.id)
        self.assertEqual(direct_rows[0]["reinforcement_n"], 1)
        self.assertEqual(direct_rows[0]["execution"], "awaiting_boundary")
        self.assertNotIn("proposal_id", direct_rows[0], "direct 行不混用 proposal_id")

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
