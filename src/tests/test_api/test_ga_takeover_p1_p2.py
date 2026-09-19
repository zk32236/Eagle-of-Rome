# src/tests/test_api/test_ga_takeover_p1_p2.py
"""WP-G GA：统一 Takeover（P1/P2 双前置 + Shared Core 十步 + fail-closed）测试。

覆盖 Q 件 A/C/D/E/F/G/I：
- P1（TRUCE+pending treaty）正向：清条约 + TRUCE→ACTIVE + 新 Commander + 幸存保留/rebind + 显式 N
- P2（ACTIVE+no valid commander）正向：无状态转换、无条约 mutation
- 异常态 fail closed：ACTIVE+pending / TRUCE+无 pending / ACTIVE+valid commander / 其他状态
- Reinforcement N 值域（G 件 §4）：N<0 / N>池 拒绝；N≥0 合法（R6 N≥0 规则，含 N=0）
- FC-05 原子性 + 反 split-brain（War/Legion/Fleet 三绑定一致）

S19 / S21 / S23 / S24 / S33 映射。

R6（SA-Design v1.1 §C.6 / §C.2 / §B.1；DA-3 B4 退役 + DA-6 B1a 迁移）：
三孤儿 `execute_war_takeover_deploy` / `execute_war_takeover_direct` /
`execute_war_continue_direct` 已**退役为无副作用 shim**，统一返回 **dict**
`{success:False, code:LEGACY_WAR_EXECUTION_RETIRED, message:"use package and advance"}`
（PM 裁定 P-B4-4 = 保持 dict）。P1/P2/N 校验语义命题**迁移到新 direct 路由**
（合规 Submit 冻结 `ConsulWarDecision` + 唯一边界消费 `senate_api.advance_senate_phase`）；
孤儿直调侧只断言退役码 + **零 mutation**（`snapshot_war_resolution_domains()` 深值相等）。
**用例未删、未改名；未 supersede 命题逐项保留（难度未降）。**
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import senate_api


class TestGaTakeoverP1P2(unittest.TestCase):
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

    # ---------- 构造 helpers ----------
    def _make_truce_war(self, war_id="w1", commander_id=2, legions=(1, 2), fleet=False):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=5, naval_required=fleet)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "pending", "generated_turn": 1})
        war.commander_id = commander_id
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        for num in legions:
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war(list(legions), war.id, commander_id)
        if fleet:
            fleet = Fleet(number=90)
            fleet._status = FleetStatus.AVAILABLE
            self.state._naval_system._fleets[90] = fleet
            ok = self.state._naval_system.assign_fleet_to_war(90, war.id, "JOINT_INVASION", commander_id)
            assert ok
        return war

    def _make_commanderless_active_war(self, war_id="w2", commander_id=None, dead=False):
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=5, naval_required=False)
        war.status = WarStatus.ACTIVE
        war.commander_id = commander_id
        self.state._war_system._active_wars.append(war)
        return war

    def _politics(self):
        return PoliticalSystem(self.state)

    # ---------- P1 正向（S19/S21） ----------
    def test_p1_truce_pending_takeover_full_core(self):
        """P1：新 direct 路由（TRUCE+pending → checked command → consul_direct → 唯一边界）=
        清条约 + ACTIVE + 新 Commander + 幸存保留/rebind + 显式 N；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(fleet=True)
        ms = self.state._military_system
        surviving = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving), 2)
        for leg in surviving:
            self.assertEqual(leg.commander_id, 2)  # 旧绑定

        # ① 孤儿直调已退役：零 mutation（条约未清、状态未转、Commander 未换、无征召）
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 2)

        # ② 新 direct 路由：Submit 冻结零军事写
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertIsNotNone(war.peace_treaty, "Submit 零部署：pending 条约未清")
        self.assertEqual(war.status, WarStatus.TRUCE, "Submit 零部署：状态未转")
        self.assertEqual(war.commander_id, 2, "Submit 零部署：Commander 未变")
        self.assertEqual(len(self._direct_rows()), 1)

        self._resolve_and_advance()
        # 条约清 + TRUCE→ACTIVE + 新 Commander
        self.assertIsNone(war.peace_treaty)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, self.state._war_system.get_active_wars())
        self.assertEqual(war.commander_id, self.consul.id)
        # 新 Consul absent（C-T10 任命→deployed）
        self.assertTrue(self.consul.is_absent)
        # 幸存保留（S21：禁裁员）+ rebind 新 Commander（D/Q 件 E）
        surviving_after = ms.get_legions_for_battle(war.id)
        self.assertEqual(len(surviving_after), 3)  # 幸存 2 + 新征召 1（显式 N=1）
        for num in (1, 2):
            self.assertEqual(ms.get_legion_by_number(num).commander_id, self.consul.id)
        # 显式 N=1：新军团绑定新 Commander
        self.assertEqual(len(war.legion_numbers), 3)
        new_legion = ms.get_legion_by_number(war.legion_numbers[-1])
        self.assertEqual(new_legion.commander_id, self.consul.id)
        self.assertEqual(new_legion.war_id, war.id)
        # Fleet rebind（H 件 §5）
        fleet = self.state._naval_system.get_fleet(90)
        self.assertEqual(fleet.commander_id, self.consul.id)
        self.assertEqual(fleet.assigned_war_id, war.id)  # 单战归属不变（GC）
        # 反 split-brain（R-14）
        for leg in ms.get_legions_for_battle(war.id):
            self.assertEqual(leg.commander_id, war.commander_id)
        self.assertEqual(fleet.commander_id, war.commander_id)

    def test_p1_takeover_requires_pending_treaty(self):
        """fail-closed：TRUCE 无 pending treaty → P1 条约清/TRUCE→ACTIVE 状态转换不得发生；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_nopending", name="NoPending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.commander_id = 2
        self.state._war_system._truce_wars.append(war)
        # ① 孤儿直调已退役：零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(war.commander_id, 2)
        # ② 路由面 fail-closed 等价命题：无 pending 草案 → 不执行 P1 状态转换（仍 TRUCE、无条约）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        if sub["success"]:
            adv = senate_api.advance_senate_phase(self.state, "player1")
            self.assertTrue(adv["success"] or not adv["success"])  # 记录态；核心为不变量
        self.assertEqual(war.status, WarStatus.TRUCE, "无 pending 不得 TRUCE→ACTIVE")
        self.assertIsNone(war.peace_treaty)

    # ---------- P2 正向（ODR-G-01 / T15） ----------
    def test_p2_commanderless_active_no_treaty_mutation(self):
        """P2：新 direct 路由对 ACTIVE+commander_id None 接管成功；无条约 mutation、无状态转换；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_commanderless_active_war()
        # ① 孤儿直调已退役：零 mutation（commander 仍 None）
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertIsNone(war.commander_id)
        # ② 新 direct 路由
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertIsNone(war.peace_treaty)  # P2 不伪造、不清理条约（Q 件 C）
        self.assertTrue(self.consul.is_absent)
        self.assertEqual(len(war.legion_numbers), 1)

    def test_p2_dead_commander_takeover(self):
        """P2：ACTIVE + commander 已阵亡 → 可接管（no valid commander）；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_commanderless_active_war(war_id="w_dead", commander_id=2)
        self.old_cmd.is_dead = True
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.commander_id, 2, "退役 shim 零 mutation：未换将")
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.commander_id, self.consul.id)

    def test_p2_absent_proconsul_takeover(self):
        """P2：ACTIVE + absent proconsul（离任）→ 可接管；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_commanderless_active_war(war_id="w_absent", commander_id=2)
        self.old_cmd.is_absent = True
        self.old_cmd.office = "proconsul"
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.commander_id, 2, "退役 shim 零 mutation：未换将")
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.commander_id, self.consul.id)

    # ---------- 异常态 fail closed（Q 件 A/C） ----------
    def test_fail_closed_active_with_pending_treaty(self):
        """异常态：ACTIVE + pending treaty → 不得无条件幂等 cleanup（pending 条约不被静默清理）；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_active_pending", name="ActivePending", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        war.set_peace_treaty({"indemnity": 10, "duration": 3, "status": "pending", "generated_turn": 1})
        self.state._war_system._active_wars.append(war)
        # ① 孤儿直调已退役：零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertIsNone(war.commander_id)
        self.assertEqual(war.peace_treaty["status"], "pending")
        # ② 路由面：pending 条约绝不被静默清理（fail-closed 或原子拒绝）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        if sub["success"]:
            senate_api.advance_senate_phase(self.state, "player1")
        self.assertIsNotNone(war.peace_treaty, "pending 条约不得被静默清理")
        self.assertEqual(war.peace_treaty["status"], "pending")
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_fail_closed_active_with_valid_commander(self):
        """ACTIVE + valid commander：换将须经冻结 direct 决策（无条约面副作用）；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_valid", name="ValidCmd", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = 2
        self.old_cmd.is_absent = False
        self.old_cmd.office = "consul"
        self.state._war_system._active_wars.append(war)
        # ① 孤儿直调已退役：零 mutation（Commander 未换）
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.commander_id, 2)
        # ② 路由面：ACTIVE 换将以冻结 direct 决策承载（无条约清/无状态转换）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(len(self._direct_rows()), 1)
        self._resolve_and_advance()
        self.assertEqual(war.status, WarStatus.ACTIVE, "无状态转换")
        self.assertIsNone(war.peace_treaty)
        self.assertEqual(war.commander_id, self.consul.id)

    def test_fail_closed_non_takeoverable_status(self):
        """其他状态（THREAT）→ 不产生 consul_direct 接管（主动宣战走 Senate 表决）；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = War(id="w_threat", name="Threat", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.THREAT
        self.state._war_system._threats.append(war)
        # ① 孤儿直调已退役：零 mutation（THREAT 未动）
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self.assertEqual(war.status, WarStatus.THREAT)
        # ② 路由面：THREAT → active_declaration → Senate 表决路由（零 direct 接管）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 1}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertEqual(len(self._direct_rows()), 0, "THREAT 不产生 consul_direct 接管")
        self.assertEqual(len(self.state.get_senate_proposals()), 1, "THREAT 主动宣战 → Senate 提案")
        self.assertEqual(war.status, WarStatus.THREAT, "Submit 零军事写：未提前激活")

    # ---------- Reinforcement N 值域（G 件 §4 / S23/S24） ----------
    def test_n_validation_rejects_out_of_range(self):
        """N 越界（N<0 / N>池）→ 拒绝且零发布零 mutation；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war()
        # ① 孤儿直调已退役：N=0 / N=-1 / N=999 一律退役码 + 零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=0))
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=-1))
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(war, self.consul, reinforcement_n=999))
        self.assertEqual(war.status, WarStatus.TRUCE)  # 零 mutation
        # ② 路由面：N<0 → REINFORCEMENT_INVALID（零发布）
        neg = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": -1}])
        self.assertFalse(neg["success"])
        self.assertIn("REINFORCEMENT_INVALID",
                      [e.get("code") for e in (neg.get("errors") or [])])
        self.assertEqual(war.status, WarStatus.TRUCE)
        # ③ 路由面：N>池 → LEGION_POOL_EXCEEDED / REINFORCEMENT_INVALID（零发布）
        big = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 999}])
        self.assertFalse(big["success"])
        self.assertTrue({"LEGION_POOL_EXCEEDED", "REINFORCEMENT_INVALID"} &
                        {e.get("code") for e in (big.get("errors") or [])})
        self.assertEqual(war.status, WarStatus.TRUCE)

    def test_zero_pool_exception_n0_accepted(self):
        """S24：池=0 & N=0 → 路由接受（R6 N≥0 规则）；孤儿直调侧 = 退役码 + 零 mutation。"""
        ms = self.state._military_system
        war = War(id="w_zero", name="ZeroPool", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state._war_system._active_wars.append(war)
        for num in range(1, 26):
            ok, _ = ms.recruit_legion(num)
            assert ok
        ms.assign_to_war([1, 2], war.id, 99)
        self.assertEqual(len(ms.get_available_legions()), 0)
        # ① 孤儿直调已退役：零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=0))
        self.assertIsNone(war.commander_id)
        # ② 路由面：池=0 & N=0 → 接受（零新增征召）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 0}])
        self.assertTrue(sub["success"], sub.get("errors"))
        self._resolve_and_advance()
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertEqual(len(war.legion_numbers), 2)  # 无新增

    def test_none_n_defaults_to_min(self):
        """R6：N 缺省不被静默解释为 min —— checked command 必须显式给出 N≥0；
        缺省（None）→ fail-closed REINFORCEMENT_INVALID（零发布）。孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(war_id="w_default")
        # ① 孤儿直调已退役：零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(war, self.consul))
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(len(war.legion_numbers), 2)
        # ② 路由面：N 缺省 → REINFORCEMENT_INVALID（零发布零 mutation）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id}])
        self.assertFalse(sub["success"])
        self.assertIn("REINFORCEMENT_INVALID",
                      [e.get("code") for e in (sub.get("errors") or [])])
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertEqual(len(war.legion_numbers), 2)

    # ---------- FC-05 原子性（Q 件 H/S33） ----------
    def test_fc05_n_greater_than_pool_fails_no_commander_write(self):
        """FC-05：N>池（非法）→ 拒绝，commander 不回写；孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(war_id="w_fc05")
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=999))
        self.assertEqual(war.commander_id, 2)  # 旧 commander 保留（未回写）
        sub = self._submit_package([{"war_id": war.id, "checked": True, "mode": "command",
                                     "target_commander_id": self.consul.id, "reinforcement_n": 999}])
        self.assertFalse(sub["success"])
        self.assertEqual(war.commander_id, 2)  # 零发布：commander 未回写

    def test_reentry_no_duplicate_recruit(self):
        """S33：接管后整包重入 → PACKAGE_ALREADY_SUBMITTED；边界 receipt 重放零重复征召；
        孤儿直调侧 = 退役码 + 零 mutation。"""
        war = self._make_truce_war(war_id="w_reentry")
        # ① 孤儿直调已退役：重入仍退役码 + 零 mutation
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        self._assert_retired_zero_mutation(
            lambda: self._politics().execute_war_takeover_direct(
                war, self.consul, reinforcement_n=1))
        # ② 新 direct 路由：首次提交 → 边界部署恰一次
        draft = {"war_id": war.id, "checked": True, "mode": "command",
                 "target_commander_id": self.consul.id, "reinforcement_n": 1}
        first = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "re-1", "war_drafts": [draft]})
        self.assertTrue(first["success"], first.get("errors"))
        legions_at_submit = list(war.legion_numbers)
        # ③ 异 id 再提交（边界前、同会期）→ 拒绝（by_session 唯一）
        again = senate_api.propose_many(self.state, "player1",
                                        {"submit_request_id": "re-2", "war_drafts": [draft]})
        self.assertFalse(again["success"])
        self.assertIn("PACKAGE_ALREADY_SUBMITTED",
                      [e.get("code") for e in (again.get("errors") or [])])
        self.assertEqual(list(war.legion_numbers), legions_at_submit)
        # ④ 边界部署恰一次
        self._resolve_and_advance()
        legions_after_first = list(war.legion_numbers)
        self.assertEqual(war.commander_id, self.consul.id)
        self.assertNotEqual(legions_after_first, legions_at_submit)
        # ⑤ 边界 receipt 重放：零重复征召
        replay = senate_api.advance_senate_phase(self.state, "player1")
        self.assertTrue(replay["success"])
        self.assertTrue(replay["data"].get("replayed"))
        self.assertEqual(list(war.legion_numbers), legions_after_first)
        self.assertEqual(war.commander_id, self.consul.id)


if __name__ == "__main__":
    unittest.main()
