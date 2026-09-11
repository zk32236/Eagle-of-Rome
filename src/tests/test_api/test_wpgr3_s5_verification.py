# src/tests/test_api/test_wpgr3_s5_verification.py
"""WP-G-R3 S5（V-01 T16 / V-02 T17 evidence helpers / V-03 T18）— Verification DATA 证据。

冻结设计：SA-Design-WP-G-R3-2026-09-05.md v1.2 §5.1/§5.2/§5.3 + §7.3（Evidence Class=
DATA；RENDER_AUTOMATED 归 SO Work Order WP-G-R3-NATIVE-QT-LIVE-CAPTURE）+ §10 T16/T17/T18。

V-01（T16，SC-R3-06 DATA 部分）——force_battle_result production-path：
- Group 1 `stalemate`：live Store.doSelectWar/doCombatAction → canonical result draw →
  TRUCE + pending treaty（post-result mutation 保留）。
- Group 2 `victory` / `triumph`：同一路径 → RESOLVED/recall/rewards；保留活 Commander +
  soldier_share>0（V-03 的 canonical producer 前置）。
- Group 3 `""`（committed 默认绑定）、absent、invalid → 正常 random CRT 路径（受控骰子，
  记录原骰子/结果/CRT 输入），证明不被工作树 `victory` 现场值覆盖、未经过第二 resolver。
- 隔离：land override 不能跨过无舰队自动 DEFEAT / 海战阻断（R-05）。
- 取证约束：所有 run 在 task-local 内存 config 上显式构造 committed 默认（""）或 key-absent，
  不触碰工作树 `data/config/game_config.json`（Owner R2 override 保留现场；候选不含 override）。

V-02（T17，SC-R3-07）——evidence-only：本文件提供 tech-lock 行为证据
（`pyrrhic_war_won=False` → Forum 零 fleet 合同；True → 恰 1）；完整 source matrix bundle
（MVP0.5-04 §2.1/2.2、wars.json Pyrrhic/First Punic、`_can_build_fleet`、`resolve_war(pyrrhic)`、
Forum/Senate/Combat 时序锚点）见 R3-evidence/SC-R3-07/<run-id>/V02-source-matrix.md。

V-03（T18，SC-R3-08 DATA 部分）——constructible eligibility 全矩阵（public seam =
get_forum_view / vote_triumph / resolve_forum + Store doVoteTriumph/doResolveForum）：
living TRIUMPH+VICTORY / dead before surface / dead after display→refresh / missing /
invalid（war id / commander id）/ zero share / non-RESOLVED / new-Store re-entry / second
resolve 零重复。fixture producer = R1 s5 `_resolved_war_state`（real forced victory/triumph）。
"""
import unittest
from unittest import mock

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import combat_api, forum_api

# 同目录 R1 生产 fixture 复用（同 run producer parity；模块级 helper 无 unittest 副作用）
from test_wpgr1_s1_forced_combat import _base_state as r1s1_base_state
from test_wpgr1_s1_forced_combat import _make_land_war as r1s1_land_war
from test_wpgr1_s1_forced_combat import _naval_state as r1s1_naval_state
from test_wpgr1_s5_triumph_eligibility import _resolved_war_state as r1s5_resolved_war
from test_wpgr1_s5_triumph_eligibility import _kill_commander as r1s5_kill
from test_wpgr1_s5_triumph_eligibility import _remove_commander as r1s5_remove
from test_wpgr1_s5_triumph_eligibility import _forum_rows as r1s5_rows
from test_wpgr1_s5_triumph_eligibility import _vote_ok as r1s5_vote


def _real_player_state():
    """R1-s1 land-war fixture（真实 Player，GuiSessionStore snapshot 需要）。"""
    state, faction, commander = r1s1_base_state()
    war = r1s1_land_war(state, war_id="war_live", strength=5, n_legions=2)
    return state, war, commander


def _store(state, viewer):
    from src.ui.gui.session_store import GuiSessionStore
    store = GuiSessionStore(state)
    store.initialize(viewer)
    return store


# ---------------------------------------------------------------------------
# V-01 Group 1/2：live Store/Adapter 路径 forced stalemate / victory / triumph
# ---------------------------------------------------------------------------

class TestR3V01LiveForcedLandPath(unittest.TestCase):
    """T16：live Store.doCombatAction → Adapter → public do_combat_action → canonical
    resolver consume override → 正常 post-result mutation（GUI 生产入口同 seam）。"""

    def _act(self, forced):
        state, war, _commander = _real_player_state()
        # 取证：显式 task-local 内存 override；工作树 game_config.json 现场值不参与
        state.config.testing.force_battle_result = forced
        store = _store(state, "player_opt")
        sel = store.doSelectWar(war.id)
        self.assertTrue(sel["success"], sel.get("message"))
        fb = store.doCombatAction(war.id, "attack")
        self.assertTrue(fb["success"], fb.get("message"))
        self.assertTrue(store.combatView, "combat view must refresh after live action")
        return state, war, _commander, store, fb["data"]

    def test_live_stalemate_draw_truce_pending(self):
        """Group1：live stalemate → draw → TRUCE + pending treaty；commander 保留。"""
        state, war, _commander, store, data = self._act("stalemate")
        self.assertEqual(data["result"], "draw")
        self.assertFalse(data["triumph"])
        self.assertEqual(data["losses"], 0)
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, state._war_system._truce_wars)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.peace_treaty.get("status"), "pending")
        self.assertEqual(war.commander_id, 1)
        # Store DTO 同源（live 层 battle detail 与结果一致）
        detail = store.combatBattleResultDetail
        self.assertEqual(detail.get("result"), "draw")

    def test_live_victory_resolves_keeps_commander_share(self):
        """Group2a：live victory → RESOLVED + recall + soldier_share>0（V-03 producer）。
        胜利结算清 war.commander_id（指挥官返罗马）——V-03 的 Triumph 权威 = 活 Figure +
        war.triumph_commander_id + soldier_share（R1 s5 同源）。"""
        state, war, commander, _store_obj, data = self._act("victory")
        self.assertEqual(data["result"], "victory")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertIn(war, state._war_system._war_discard)
        self.assertFalse(commander.is_dead)               # 活 Commander 保留
        self.assertEqual(war.triumph_commander_id, 1)     # Triumph 行权威（V-03 producer）
        self.assertGreater(war.soldier_share, 0)

    def test_live_triumph_resolves_bonus_share(self):
        """Group2b：live triumph → RESOLVED + loot bonus；活 Commander + share 保留。"""
        state, war, commander, _store_obj, data = self._act("triumph")
        self.assertEqual(data["result"], "triumph")
        self.assertTrue(data["triumph"])
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertFalse(commander.is_dead)
        self.assertEqual(war.triumph_commander_id, 1)
        self.assertGreater(war.soldier_share, 0)


# ---------------------------------------------------------------------------
# V-01 Group 3："" / absent / invalid → 正常 random（committed-default 绑定）
# ---------------------------------------------------------------------------

class TestR3V01EmptyAbsentInvalidRandom(unittest.TestCase):
    """T16 Group3：空/缺/非法 override 均走正常 2d6 CRT；每 run 记录受控骰子与 CRT 输入。
    取证绑定：committed 默认 = `""`（工作树 `victory` 是 Owner R2 现场，测试显式构造默认态）。"""

    def test_empty_committed_default_preserves_crt(self):
        """force_battle_result=''（committed 默认绑定）→ 高敌力 + dice=2 ∈ disaster → disaster。"""
        state, _faction, _commander = r1s1_base_state()
        state.config.testing.force_battle_result = ""       # committed-default（非现场 victory）
        self.assertEqual(state.config.get("testing.force_battle_result", "SENTINEL"), "")
        war = r1s1_land_war(state, war_id="war_empty", strength=30, n_legions=2)
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=2):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # dice=2（原骰子）∈ disaster_numbers[2,3] → CRT disaster（与 forced 无关）
        self.assertEqual(result["data"]["dice"], 2)
        self.assertEqual(result["data"]["result"], "disaster")
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_absent_key_preserves_crt(self):
        """配置键缺省（absent；默认 "" 语义）→ 低敌力 + dice=7 → CRT triumph（score>=12）。"""
        state, _faction, _commander = r1s1_base_state()
        # 不设置 force_battle_result（key absent）→ 默认空
        war = r1s1_land_war(state, war_id="war_absent", strength=0, n_legions=2)
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=7):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # 7(martial6 + legion4 =17) − 0 → 17 → triumph（CRT，非 forced 恒定）
        self.assertEqual(result["data"]["result"], "triumph")
        self.assertEqual(war.status, WarStatus.RESOLVED)

    def test_invalid_value_fail_closed_random(self):
        """非法值 → None → 正常随机（不报错、不落 STALEMATE 默认、不经第二 resolver）。"""
        state, _faction, _commander = r1s1_base_state()
        state.config.testing.force_battle_result = "banana"
        war = r1s1_land_war(state, war_id="war_invalid", strength=30, n_legions=2)
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=5):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # dice=5 非 standoff(99)；score=5+6+4−30=−15 < −3 → defeat
        self.assertEqual(result["data"]["result"], "defeat")
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_land_override_does_not_bypass_naval_gate(self):
        """隔离（WP-G-R4 supersede，SA v1.7 §8.3/§3.1）：land override（victory）不能穿透
        readiness——无 ready 舰队 = NAVAL_NOT_READY（非 DEFEAT、零 battle 副作用）。"""
        state, war = r1s1_naval_state(enemy_naval=20, n_fleets=0)
        state.config.testing.force_battle_result = "victory"   # 仅 land override
        state.config.testing.force_naval_result = ""           # naval 默认（committed 空）
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["code"], "NAVAL_NOT_READY")
        self.assertEqual(war.status, WarStatus.ACTIVE, "land victory override 未生效（未 RESOLVED）")
        self.assertEqual(war.duration, 0)

    def test_live_naval_gate_store_level_default(self):
        """live Store 层（WP-G-R4 supersede）：naval-required + 无 ready 舰队 → Store 反馈
        readiness 拒绝（只读刷新，不写 battle victory/defeat data）。"""
        state, war = r1s1_naval_state(enemy_naval=20, n_fleets=0)
        state.config.testing.force_battle_result = "victory"
        state.config.testing.force_naval_result = ""
        store = _store(state, "player_opt")
        sel = store.doSelectWar(war.id)
        self.assertTrue(sel["success"], sel.get("message"))
        fb = store.doCombatAction(war.id, "attack")
        self.assertFalse(fb["success"], "readiness 拒绝 → False")
        self.assertEqual(fb["data"]["code"], "NAVAL_NOT_READY")
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertFalse(war.sea_control_acquired)


# ---------------------------------------------------------------------------
# V-02 evidence helpers（source reconciliation；source matrix 文档另见 evidence bundle）
# ---------------------------------------------------------------------------

class TestR3V02TechLockTimingEvidence(unittest.TestCase):
    """T17：Pyrrhic 技术锁 → Forum 合同生成时序行为证据（零产品代码变更）。

    anchors：wars.json pyrrhic_war（start_year -282, naval_required=false, enemy 3）→
    war_system.resolve_war pyrrhic 分支写 state.pyrrhic_war_won=True；naval_system._can_build_fleet
    （L86-88）读该标记；forum_api.initialize_forum_turn → generate_contracts → naval generator
    （construction 走 THREAT wars / replacement 走 ACTIVE deficit，均先查 tech lock）。
    本证据使用 S3 生产-shaped builder（valid-commander ACTIVE naval war, enemy 20）：
    lock（pyrrhic False）→ Forum init 零 fleet 合同；unlock（生产写入点置 True）→ 恰一份
    PENDING（7 trireme / A280 / target）。不修改起年/解锁条件/敌战力；外生入口 = 显式标记
    （真实解锁路径 = Pyrrhic resolve_war，S3/S4 FC 链 fixture 亦用同一标记）。
    """

    def _forum_state(self, unlocked):
        from test_wpgr3_s3_fleet_economics import _build_fleet_chain_state
        state, ctx = _build_fleet_chain_state()   # pyrrhic_war_won=True 生产形态（ACTIVE war enemy20）
        state.pyrrhic_war_won = unlocked          # lock 侧显式关闭（外生 fixture，与文件无关）
        return state, ctx["war"]

    def test_lock_no_contract_before_pyrrhic(self):
        """lock：pyrrhic_war_won=False → Forum init 零 fleet 合同（_can_build_fleet 门）。"""
        state, war = self._forum_state(unlocked=False)
        self.assertFalse(state.pyrrhic_war_won)
        res = forum_api.initialize_forum_turn(state)
        self.assertTrue(res["success"], res.get("message"))
        fleet_contracts = [
            c for c in state.get_all_contracts()
            if getattr(c, "_is_fleet_construction", False)
        ]
        self.assertEqual(fleet_contracts, [], "tech lock → 不得生成 fleet 合同")

    def test_unlock_generates_exactly_one_after_pyrrhic(self):
        """unlock：pyrrhic_war_won=True（resolve_war pyrrhic 分支生产写入语义）→ 恰 1 份
        PENDING 合同（target 20 → 7 trireme、A280、target war 绑定）。"""
        state, war = self._forum_state(unlocked=True)
        res = forum_api.initialize_forum_turn(state)
        self.assertTrue(res["success"], res.get("message"))
        fleet_contracts = [
            c for c in state.get_all_contracts()
            if getattr(c, "_is_fleet_construction", False)
        ]
        self.assertEqual(len(fleet_contracts), 1, fleet_contracts)
        c = fleet_contracts[0]
        self.assertEqual(getattr(c, "_target_war_id", None), war.id)
        self.assertEqual(c._original_budget, 280)  # 7 × trireme 40（enemy20 → ceil(20/3)=7）
        self.assertEqual(c.recommended_fleet_composition, [{"type": "trireme", "count": 7}])


# ---------------------------------------------------------------------------
# V-03：constructible eligibility 全矩阵扩展（public seam + Store）
# ---------------------------------------------------------------------------

class TestR3V03MatrixExtensions(unittest.TestCase):
    """T18 扩展（R1 s5 已有 alive/dead/missing 三层同源；本类补 §5.3 其余矩阵行 +
    Store refresh/re-entry 层）。"""

    # ---- living：market/clickable 上下文 + Store 层记录与结算 ----
    def test_living_market_context_and_store_flow(self):
        """living：rows 存在於 market step（可点上下文）+ Store doVoteTriumph 记录 →
        doResolveForum 批准 → share 恰一次消费 → fresh view/new Store 同值零残留。"""
        state, war, _commander = r1s5_resolved_war(force="victory")
        # 可点上下文：记录合法 vote → pending triumph_votes → forum view step=market
        self.assertTrue(r1s5_vote(state, war.id)["success"])
        view = forum_api.get_forum_view(state, "player_opt")["data"]
        self.assertEqual(view["current_step"], "market")
        self.assertEqual(view["pending_actions"]["triumph_votes"], 1)
        self.assertEqual([r["war_id"] for r in view["triumph_wars"]], [str(war.id)])
        self.assertEqual(view["triumph_wars"][0]["commander_id"], 101)

        # Store 层：同一 live eligibility（fresh Store 读同 rows、投票成功）
        store = _store(state, "player_opt")
        self.assertEqual([r["war_id"] for r in store.forumTriumphWars], [str(war.id)])
        self.assertTrue(store.doVoteTriumph(war.id, True)["success"])
        self.assertEqual(store.forumView["pending_actions"]["triumph_votes"], 2)

        # settlement（既有影响力多数规则）→ 批准；share 恰一次消费
        settled = store.doResolveForum()
        self.assertTrue(settled["success"], settled.get("message"))
        results_text = " ".join(settled["data"]["results"])
        self.assertIn("凯旋仪式获得批准", results_text)
        self.assertTrue(war.triumph_approved)
        self.assertEqual(war.soldier_share, 0)

        # refresh / new Store / re-entry：已消费 share 不再出现、无重复副作用
        view2 = forum_api.get_forum_view(state, "player_opt")["data"]
        self.assertEqual(view2["triumph_wars"], [])
        store2 = _store(state, "player_opt")
        self.assertEqual(store2.forumTriumphWars, [])
        self.assertFalse(r1s5_vote(state, war.id)["success"])     # no_soldier_share 拒
        pending = state.get_forum_pending()["triumph_votes"]
        self.assertFalse(any(v[0] == war.id for v in pending), "已结算凯旋不再入票")
        # 二次 resolve 幂等 no-op（无二次奖励）
        again = forum_api.resolve_forum(state)
        self.assertTrue(again["success"])
        self.assertFalse(any("凯旋仪式获得批准" in r for r in again["data"]["results"]))
        self.assertEqual(war.soldier_share, 0)

    # ---- VICTORY result 维度（R1 s5 已盖；此处补 Store 层 smoke） ----
    def test_victory_result_store_layer_eligible(self):
        state, war, _ = r1s5_resolved_war(force="victory")
        store = _store(state, "player_opt")
        self.assertEqual([r["war_id"] for r in store.forumTriumphWars], [str(war.id)])
        self.assertTrue(store.doVoteTriumph(war.id, True)["success"])

    # ---- dead after display → refresh 移除 + 后端重验拒绝 + settlement 失效 ----
    def test_dead_after_display_store_refresh_and_reentry(self):
        """dead-after-display：vote 已记录后 commander 阵亡 → Store refresh 后行移除；
        新投票拒绝；settlement 同源失效（无死者 reward）；new Store 同值。"""
        state, war, commander = r1s5_resolved_war(force="triumph")
        store = _store(state, "player_opt")
        self.assertEqual(len(store.forumTriumphWars), 1)      # display 面可见
        self.assertTrue(store.doVoteTriumph(war.id, True)["success"])
        r1s5_kill(state, commander)                            # 展示后 / settlement 前死亡
        # 触发 refresh 的任一 forum 动作后 rows 消失（后端重验，非仅缓存）
        rejected = store.doVoteTriumph(war.id, True)
        self.assertFalse(rejected["success"], rejected.get("message"))
        self.assertEqual(store.forumTriumphWars, [])
        store2 = _store(state, "player_opt")                   # new Store 重建同值
        self.assertEqual(store2.forumTriumphWars, [])
        # settlement：dead → 凯旋失效，零临时影响力 reward
        settled = forum_api.resolve_forum(state)
        results_text = " ".join(settled["data"]["results"])
        self.assertIn("凯旋失效", results_text)
        self.assertEqual(war.soldier_share, 0)
        self.assertFalse(war.triumph_approved)

    # ---- missing entity / invalid id：fail-closed 不崩溃 ----
    def test_missing_and_invalid_ids_fail_closed(self):
        """missing commander entity / invalid war id / invalid commander id → 拒绝不异常，
        不留可点行；None/invalid 等 ineligible 原因保留。"""
        state, war, commander = r1s5_resolved_war(force="victory")
        r1s5_remove(state, commander)
        self.assertEqual(r1s5_rows(state), [])
        self.assertFalse(r1s5_vote(state, war.id)["success"])

        # invalid war id：vote 入口拒绝（war_not_found），零记录、不崩溃
        state2, war2, _c2 = r1s5_resolved_war(force="victory")
        resp = forum_api.vote_triumph(state2, "player_opt", "no_such_war", True)
        self.assertFalse(resp["success"])
        self.assertEqual(state2.get_forum_pending()["triumph_votes"], [])

        # invalid commander id（triumph_commander_id 指向不存在人物）→ commander_missing 族
        state3, war3, _c3 = r1s5_resolved_war(force="victory")
        war3._triumph_commander_id = 404040
        self.assertEqual(r1s5_rows(state3), [])
        r3 = forum_api.vote_triumph(state3, "player_opt", war3.id, True)
        self.assertFalse(r3["success"], r3.get("message"))

        # missing-entity settlement 同源（凯旋失效，soldier_share 归零）——R1 s5 已证，零重复

    # ---- share=0 / non-RESOLVED：无行 + 入口拒绝 ----
    def test_zero_share_and_non_resolved_no_rows(self):
        state, war, _c = r1s5_resolved_war(force="victory")
        war.set_soldier_share(0)
        self.assertEqual(r1s5_rows(state), [])
        r0 = forum_api.vote_triumph(state, "player_opt", war.id, True)
        self.assertFalse(r0["success"])

        state2, war2, _c2 = r1s5_resolved_war(force="victory")
        war2.status = WarStatus.ACTIVE          # 非 RESOLVED 异常态
        self.assertEqual(r1s5_rows(state2), [])
        r1 = forum_api.vote_triumph(state2, "player_opt", war2.id, True)
        self.assertFalse(r1["success"])
        # 无死锁：修复状态后同源恢复
        war2.status = WarStatus.RESOLVED
        self.assertEqual([r["war_id"] for r in r1s5_rows(state2)], ["war1"])


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
