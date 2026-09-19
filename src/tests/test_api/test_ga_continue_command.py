# src/tests/test_api/test_ga_continue_command.py
"""WP-G GA：Continue Existing Command（G1-21 / F 件 §2.2 / T8）测试。

覆盖：
- Continue 全流（S20）：清条约 + TRUCE→ACTIVE + 现有 commander 保留（禁静默替换）
  + 保留幸存 + 征召 N + 新军团 bind 现有 commander
- fail-closed：TRUCE 无 pending / 无有效 commander / 非 TRUCE → 拒绝
- N 值域（S22/S23/S24）
- human API continue_war：权限 + 可执行校验 + N 校验 + direct action provenance

R6（SA-Design v1.1 §C.6 / §C.2；DA-3 B4 退役 + DA-6 B1a 迁移）：
三孤儿 `execute_war_takeover_deploy` / `execute_war_takeover_direct` /
`execute_war_continue_direct` 已**退役为无副作用 shim**，统一返回 **dict**
`{success:False, code:LEGACY_WAR_EXECUTION_RETIRED, message:"use package and advance"}`
（PM 裁定 P-B4-4 = 保持 dict）。Continue 语义命题**迁移到新 direct 路由**
（checked command target=现任指挥官 → 冻结 `ConsulWarDecision` + 唯一边界消费
`senate_api.advance_senate_phase`：清条约 + ACTIVE + 保留现任 + 幸存保留 + 征召 N）；
孤儿直调侧只断言退役码 + **零 mutation**。**用例未删、未改名；未 supersede 命题逐项保留。**
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

    def _submit_package(self, drafts):
        return senate_api.propose_many(self.state, "player1", {"war_drafts": drafts})

    def _resolve_and_advance(self):
        res = senate_api.resolve_senate(self.state)
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        return adv

    def _direct_rows(self):
        return self.state.get_consul_war_decisions(self.state.get_senate_session()) or {}

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
        """S20：Continue 全流（新 direct 路由）——条约清 + ACTIVE + 现有 commander 保留 +
        幸存保留 + N 征召 bind 现有；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war()
        ms = self.state._military_system
        # ① 孤儿直调已退役：零 mutation（条约未清、状态未转）
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=2))
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.TRUCE)
        # ② 新 direct 路由：checked command target=现任指挥官（Continue 语义）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": 2, "reinforcement_n": 2}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertIsNotNone(war.peace_treaty, "Submit 零部署：pending 条约未清")
        self.assertEqual(war.commander_id, 2)
        self._resolve_and_advance()
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
        """fail-closed：TRUCE 无 pending treaty → Continue 条约清/TRUCE→ACTIVE 状态转换不得发生；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_np", name="NoPending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        self.state._war_system._truce_wars.append(war)
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.status, WarStatus.TRUCE)
        # 路由面等价命题：无 pending 草案 → 不执行 Continue 状态转换（仍 TRUCE、无条约）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": 2, "reinforcement_n": 1}])
        if sub["success"]:
            senate_api.advance_senate_phase(self.state, "player1")
        self.assertEqual(war.status, WarStatus.TRUCE, "无 pending 不得 TRUCE→ACTIVE")
        self.assertIsNone(war.peace_treaty)

    def test_continue_fail_closed_no_valid_commander(self):
        """fail-closed：无有效 commander → Continue 不成立（checked command 必须显式 target）；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(war_id="w_nc", commander_id=None)
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.status, WarStatus.TRUCE)
        # 路由面等价命题：commander 缺省（None）→ COMMANDER_REQUIRED（零发布零 mutation）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": None, "reinforcement_n": 1}])
        self.assertFalse(sub["success"])
        self.assertIn("COMMANDER_REQUIRED",
                      [e.get("code") for e in (sub.get("errors") or [])])
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIsNone(war.commander_id)

    def test_continue_fail_closed_not_truce(self):
        """fail-closed：非 TRUCE 状态 → 不承载 Continue 语义（无条约面副作用，状态不变）；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_active", name="Active", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.state._war_system._active_wars.append(war)
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.status, WarStatus.ACTIVE)
        # 路由面等价命题：ACTIVE 的 command 意图 = consul_direct 换将重指派（非 Senate 提案/非 Continue）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(len(self._direct_rows()), 1)
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        self._resolve_and_advance()
        self.assertEqual(war.status, WarStatus.ACTIVE, "无状态转换")
        self.assertIsNone(war.peace_treaty)

    def test_continue_zero_pool_exception(self):
        """S24：池=0 & N=0 → Continue 接受（R6 N≥0 规则）；孤儿直调侧 = 退役码 + 零 mutation。"""
        ms = self.state._military_system
        war = self._make_truce_war(war_id="w_zero")
        for num in range(3, 26):
            ok, _ = ms.recruit_legion(num)
            assert ok
        self.assertEqual(len(ms.get_available_legions()), 0)
        # ① 孤儿直调已退役：零 mutation
        result = self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=0))
        self.assertEqual(result["success"], False)
        self.assertEqual(war.commander_id, 2)
        self.assertEqual(len(war.legion_numbers), 2)  # 无新增
        # ② 路由面：池=0 & N=0 → 接受（零新增征召，现任 commander 保留）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": 2, "reinforcement_n": 0}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.commander_id, 2)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(len(war.legion_numbers), 2)  # 无新增

    def test_continue_n_validation(self):
        """S23 → R6（N≥0 规则）：N=0 且池>0 合法（不再拒绝）；Continue 以 0 征召执行；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(war_id="w_n0")
        self._assert_retired_zero_mutation(
            lambda: PoliticalSystem(self.state).execute_war_continue_direct(
                war, self.consul, reinforcement_n=0))
        self.assertEqual(war.status, WarStatus.TRUCE)
        # 路由面：N=0（池>0）→ 发布成功、零新增征召、Continue 正常落地
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": 2, "reinforcement_n": 0}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, 2)
        self.assertEqual(len(war.legion_numbers), 2)

    # ---------- human API 层（A2）→ R5 唯一整包入口 ----------
    # R5 supersede（Plan §4.2 L4；SA §1.2 SUPERSEDED + §4.10 C-M06，DA-4）：即时 continue_war
    # 独立执行入口退役。「沿用现有指挥官续战」= pending-peace 卡的 unchecked fallback，由边界
    # 唯一事务 advance_senate_phase 统一执行（Submit/Vote/Veto/Results 零军事写）。
    def test_continue_war_api_full_flow(self):
        """A2 → R5：pending-peace 卡 unchecked → Submit 零军事写；边界 fallback 清条约 +
        TRUCE→ACTIVE + 现任 Commander 保留 + 幸存保留（旧即时 continue_war 语义由边界承担）。"""
        war = self._make_truce_war(war_id="w_api")
        ms = self.state._military_system
        sub = self._submit_package([{"war_id": war.id, "checked": False, "mode": "command",
                                     "target_commander_id": 2, "reinforcement_n": 0}])
        self.assertTrue(sub["success"], sub.get("errors"))
        # Submit 零军事写：条约/状态/Commander 未变
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.commander_id, 2)
        adv = self._resolve_and_advance()
        self.assertTrue(adv.get("success"))
        # 边界：清条约 + ACTIVE + 现任 commander 保留（禁静默替换，G1-21）+ 幸存保留
        self.assertIsNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, 2)
        surviving = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving), 2)
        for leg in surviving:
            self.assertEqual(leg.commander_id, 2)
        self.assertFalse(self.consul.is_absent)
        # 边界唯一执行凭证（旧 direct-action provenance 由 receipt 承担）
        self.assertIsNotNone(self.state.get_war_execution_receipt_for_session(
            self.state.get_senate_session()))

    def test_continue_war_api_permission(self):
        """A2 → R5：身份门 = 执政官权威——无效 actor → SUBMIT_NOT_AUTHORIZED（fail-closed）。"""
        war = self._make_truce_war(war_id="w_perm")
        result = senate_api.propose_many(self.state, "playerX", {"war_drafts": [
            {"war_id": war.id, "checked": True, "mode": "command",
             "target_commander_id": 2, "reinforcement_n": 1}]})
        self.assertFalse(result["success"])
        self.assertIn("SUBMIT_NOT_AUTHORIZED",
                      [e.get("code") for e in (result.get("errors") or [])])
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_continue_war_api_no_valid_commander(self):
        """A2 → R5（A-I14）：commanderless pending-peace 不再强制接管/软锁——边界 fallback 合法续战
        （Commander 保持 None，无 mandatory 门阻止 advance）。"""
        war = self._make_truce_war(war_id="w_apinc", commander_id=None)
        sub = self._submit_package([{"war_id": war.id, "checked": False, "mode": "command",
                                     "target_commander_id": None, "reinforcement_n": 0}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(war.status, WarStatus.TRUCE)
        self._resolve_and_advance()
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIsNone(war.commander_id)
        self.assertTrue(self.state.is_phase_executed("senate"))

    def test_continue_war_api_n_out_of_range(self):
        """A2 → R5（§3.6）：checked command N 超池 → 整包零发布拒绝（LEGION_POOL_EXCEEDED）。"""
        war = self._make_truce_war(war_id="w_apirange")
        result = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                        "target_commander_id": 2, "reinforcement_n": 999}])
        self.assertFalse(result["success"])
        self.assertTrue({"LEGION_POOL_EXCEEDED", "REINFORCEMENT_INVALID"} &
                        {e.get("code") for e in (result.get("errors") or [])})
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 2)


if __name__ == "__main__":
    unittest.main()
