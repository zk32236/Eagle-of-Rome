# src/tests/test_api/test_ga_idempotency.py
"""WP-G GA：re-entry / retry 幂等（Q 件 H / S33）测试。

覆盖：
- Takeover/Continue 直连重入：第二次拒绝，无重复征召/rebind
- AI 路径重入：R5 整包 Submit 重入（第二包 → PACKAGE_ALREADY_SUBMITTED）不重复发布/零军事写
- 征召总数守恒（25 池上限不因重入重复消耗）

R5 supersede（Plan §4.2 L12；SA §4.10 C-M08）：AI 直连接管（plan_ai_takeovers /
execute_ai_takeover_direct_action）与 human takeover_war 入口已退役——重入语义经唯一
整包入口 `senate_api.propose_many`（Core `submit_proposal_package`）。

R6（SA-Design v1.1 §C.6 / §C.2；DA-3 B4 退役 + DA-6 B1a 迁移）：
三孤儿 `execute_war_takeover_deploy` / `execute_war_takeover_direct` /
`execute_war_continue_direct` 已**退役为无副作用 shim**，统一返回 **dict**
`{success:False, code:LEGACY_WAR_EXECUTION_RETIRED, message:"use package and advance"}`
（PM 裁定 P-B4-4 = 保持 dict）。旧「直调重入 = 第二次拒绝、无重复征召」语义命题
**迁移到新 direct 路由**（Submit 冻结 `ConsulWarDecision` + 唯一边界消费；重入 = by_session
唯一 → `PACKAGE_ALREADY_SUBMITTED`；边界 = 同执行身份 receipt 重放零再部署）；
孤儿直调侧只断言退役码 + **零 mutation**。**用例未删、未改名。**
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


class TestGaIdempotency(unittest.TestCase):
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

    # ---------- R6（DA-6 B1a）迁移 helper ----------
    def _assert_retired_zero_mutation(self, call):
        """孤儿退役 shim：dict {success/code/message} + 零 mutation（快照深值相等）。"""
        before = self.state.snapshot_war_resolution_domains()
        result = call()
        after = self.state.snapshot_war_resolution_domains()
        self.assertIsInstance(result, dict)
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], PoliticalSystem.LEGACY_WAR_EXECUTION_RETIRED)
        self.assertEqual(result["message"], "use package and advance")
        self.assertEqual(before, after, "退役 shim 必须零 mutation")
        return result

    def _resolve_and_advance(self):
        res = senate_api.resolve_senate(self.state)
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        return adv

    def _make_truce_war(self, war_id="w1"):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        ok, _ = ms.recruit_legion(1)
        assert ok
        ms.assign_to_war([1], war.id, 2)
        return war

    def test_takeover_reentry_no_duplicate(self):
        """S33：整包重入拒绝（PACKAGE_ALREADY_SUBMITTED）+ 边界 receipt 重放零重复征召/rebind；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war()
        politics = PoliticalSystem(self.state)
        # ① 孤儿直调已退役：两次直调均退役码、零 mutation（无重复征召/rebind）
        self._assert_retired_zero_mutation(
            lambda: politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=2))
        self._assert_retired_zero_mutation(
            lambda: politics.execute_war_takeover_direct(war, self.consul, reinforcement_n=2))
        self.assertEqual(list(war.legion_numbers), [1])
        # ② 新 direct 路由：首次提交 → 边界部署恰一次
        draft = {"war_id": war.id, "checked": True, "mode": "command",
                 "target_commander_id": self.consul.id, "reinforcement_n": 2}
        first = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "tk-1", "war_drafts": [draft]})
        self.assertTrue(first["success"], first.get("errors"))
        legions_at_submit = list(war.legion_numbers)
        assigned_at_submit = {l.number: l.commander_id
                              for l in self.state._military_system.get_legions_for_battle(war.id)}
        # ③ 异 id 再提交（边界前、同会期）→ 拒绝（by_session 唯一）
        again = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "tk-2", "war_drafts": [draft]})
        self.assertFalse(again["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (again.get("errors") or [])])
        # 拒绝态零军事写（提交期军面不变）
        self.assertEqual(list(war.legion_numbers), legions_at_submit)
        # ④ 边界部署恰一次
        self._resolve_and_advance()
        legions_after = list(war.legion_numbers)
        assigned_after = {l.number: l.commander_id
                          for l in self.state._military_system.get_legions_for_battle(war.id)}
        # 对照：Submit 零军事写（提交时与部署后不同 == 部署恰一次）
        self.assertNotEqual(legions_at_submit, legions_after)
        self.assertNotEqual(assigned_at_submit, assigned_after)
        # ⑤ 边界 receipt 重放：零重复征召/rebind
        replay = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(replay["success"])
        self.assertTrue(replay["data"].get("replayed"))
        self.assertEqual(list(war.legion_numbers), legions_after)
        self.assertEqual({l.number: l.commander_id
                          for l in self.state._military_system.get_legions_for_battle(war.id)},
                         assigned_after)
        self.assertEqual(war.commander_id, self.consul.id)

    def test_continue_reentry_no_duplicate(self):
        """S33：Continue 语义（保留现任指挥官）经冻结 direct 决策承载；重入拒绝、无重复征召；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        self.old_cmd.office = "consul"  # 有效指挥官（Continue 前置）
        war = self._make_truce_war(war_id="w_cont")
        politics = PoliticalSystem(self.state)
        # ① 孤儿直调已退役：两次直调均退役码、零 mutation
        self._assert_retired_zero_mutation(
            lambda: politics.execute_war_continue_direct(war, self.consul, reinforcement_n=1))
        self._assert_retired_zero_mutation(
            lambda: politics.execute_war_continue_direct(war, self.consul, reinforcement_n=1))
        self.assertEqual(list(war.legion_numbers), [1])
        self.assertEqual(war.status, WarStatus.TRUCE)
        # ② 新 direct 路由：checked command target=现任指挥官 → 边界 = 保留现任 + 征召 N
        draft = {"war_id": war.id, "checked": True, "mode": "command",
                 "target_commander_id": 2, "reinforcement_n": 1}
        first = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "ct-1", "war_drafts": [draft]})
        self.assertTrue(first["success"], first.get("errors"))
        self._resolve_and_advance()
        legions_after = list(war.legion_numbers)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, 2)
        # ③ 异 id 再提交 → 拒绝
        again = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "ct-2", "war_drafts": [draft]})
        self.assertFalse(again["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (again.get("errors") or [])])
        # ④ 边界 receipt 重放：零重复征召
        replay = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(replay["success"])
        self.assertTrue(replay["data"].get("replayed"))
        self.assertEqual(list(war.legion_numbers), legions_after)
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_human_api_reentry(self):
        """R5（Plan §4.2 L12；SA §3.8）：human 整包 Submit → 提案冻结且零军事写；部署唯一
        owner = advance_senate_phase。重入：同 id 同意图 → 重放（无新增）；异 id 再提交 →
        PACKAGE_ALREADY_SUBMITTED（不重复发布/零军事写）。"""
        war = self._make_truce_war(war_id="w_api")
        env = {"submit_request_id": "req-1", "war_drafts": [
            {"war_id": war.id, "checked": True, "mode": "command",
             "target_commander_id": 2, "reinforcement_n": 0}]}
        first = senate_api.propose_many(self.state, "player1", env)
        self.assertTrue(first["success"], first.get("errors"))
        # 冻结但零军事写：war 保持 TRUCE+pending、Commander 不变（2）
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.commander_id, 2, "Submit 零部署：Commander 未变")
        self.assertIs(self.state.senate_proposal_decision_complete, True)
        self.assertEqual(self.state.get_senate_direct_actions(), [])

        # 重入（同 id 同意图）→ 重放，无新增提案
        n = len(self.state.get_senate_proposals())
        replay = senate_api.propose_many(self.state, "player1", env)
        self.assertTrue(replay["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), n)
        # 重入（异 id 再提交）→ PACKAGE_ALREADY_SUBMITTED
        reuse = senate_api.propose_many(self.state, "player1", {
            "submit_request_id": "req-2", "war_drafts": [
                {"war_id": war.id, "checked": True, "mode": "command",
                 "target_commander_id": 2, "reinforcement_n": 0}]})
        self.assertFalse(reuse["success"], "已提交后重入拒绝")
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (reuse.get("errors") or [])])
        self.assertEqual(self.state.get_senate_direct_actions(), [])

    def test_ai_reentry_skips_already_locked(self):
        """R5（Plan §4.2 L12；SA §4.10 C-M08）：AI 接管直连退位——AI 意图经唯一整包
        propose_many；重入（第二包）→ PACKAGE_ALREADY_SUBMITTED，不重复发布/零军事 mutation。"""
        war = self._make_truce_war(war_id="w_ai")
        env = {"submit_request_id": "ai-1", "war_drafts": [
            {"war_id": war.id, "checked": True, "mode": "command",
             "target_commander_id": 2, "reinforcement_n": 0}]}
        first = senate_api.propose_many(self.state, "player1", env)
        self.assertTrue(first["success"], first.get("errors"))
        self.assertEqual(war.commander_id, 2, "Submit 零部署（旧 Commander 未动）")
        self.assertIs(self.state.senate_proposal_decision_complete, True)
        self.assertEqual(self.state.get_senate_direct_actions(), [], "部署前无 D")
        # 重入：异 id 再提交 → 不重复发布（零新增提案/零军事写）
        n = len(self.state.get_senate_proposals())
        again = senate_api.propose_many(self.state, "player1", {
            "submit_request_id": "ai-2", "war_drafts": [
                {"war_id": war.id, "checked": True, "mode": "command",
                 "target_commander_id": 2, "reinforcement_n": 0}]})
        self.assertFalse(again["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (again.get("errors") or [])])
        self.assertEqual(len(self.state.get_senate_proposals()), n)
        self.assertEqual(war.commander_id, 2)


if __name__ == "__main__":
    unittest.main()
