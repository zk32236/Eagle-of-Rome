# src/tests/test_gui/test_wpgr4_stage_results.py
"""WP-G-R4 — E 文件（senate 侧 S1 初建；combat 侧 S3/S4 追加式演进）。

本 slice（S1）覆盖 T03 的 Store refresh/re-entry/repeat 段（SA v1.7 §8.1 E 归属）：
GuiSessionStore 真实 Player 驱动——doTakeoverWar（Submit/lock 零部署）→ Store 属性
senatePendingTakeoverLocked/canAdvanceSenate/senateCanDeployTakeover → 显式空结束
doSubmitSenateProposals([]) + doResolveSenateSettlement → R 真实 → doAdvanceSenate
部署 exactly-once；repeat advance 拒绝。DATA 断言止于 Store property/DTO（不冒充 render）。
"""
import re
import unittest
from pathlib import Path

from src.ui.gui.session_store import GuiSessionStore
from src.core.entities.war import WarStatus
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1


class TestE03StoreTakeoverDeferredDeployment(unittest.TestCase):
    def _store(self, ctx):
        state = ctx["state"]
        store = GuiSessionStore(state)
        store.initialize(P1)
        return state, store

    def test_store_submit_locks_zero_deploy_then_settlement_then_advance_exactly_once(self):
        ctx = F.build_fix01()
        state, store = self._store(ctx)
        war_a, consul = ctx["war_a"], ctx["consul"]

        feedback = store.doTakeoverWar(war_a.id, 1)
        self.assertTrue(feedback["success"], feedback.get("message"))
        # Submit/lock：零部署 + Store 属性反映 T/V 读模型
        self.assertIsNone(war_a.commander_id)
        self.assertFalse(consul.is_absent)
        self.assertTrue(store.senatePendingTakeoverLocked)
        self.assertEqual(store.senatePendingTakeover.get("war_id"), war_a.id)
        self.assertFalse(store.canAdvanceSenate, "无真实 R → 不可推进")
        self.assertFalse(store.senateCanDeployTakeover)
        # 重复 Submit（同战）→ 已锁定拒绝，无二次副作用
        repeat = store.doTakeoverWar(war_a.id, 1)
        self.assertFalse(repeat["success"])

        # 显式空结束（P）→ settlement 恢复入口 → R 真实 → canDeploy
        empty = store.doSubmitSenateProposals([])
        self.assertTrue(empty["success"], empty.get("message"))
        self.assertTrue(store.senateSettlementPending)
        recovery = store.doResolveSenateSettlement()
        self.assertTrue(recovery["success"], recovery.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertTrue(store.senateCanDeployTakeover)
        self.assertTrue(store.canAdvanceSenate)

        # 显式 advance → 原子部署恰一次；repeat → 拒绝
        adv = store.doAdvanceSenate()
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war_a.commander_id, consul.id)
        self.assertTrue(consul.is_absent)
        self.assertTrue(state.is_phase_executed("senate"))
        again = store.doAdvanceSenate()
        self.assertFalse(again["success"], "repeat advance 拒绝（exactly-once）")
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)

    def test_store_refresh_reentry_no_duplicate(self):
        """refresh（new Store 重建同态）/重入不重复 T/V/D。"""
        ctx = F.build_fix01()
        state, store = self._store(ctx)
        war_a = ctx["war_a"]
        store.doTakeoverWar(war_a.id, 1)
        store.doSubmitSenateProposals([])
        store.doResolveSenateSettlement()
        store.doAdvanceSenate()

        # new Store 重建同一完成态（无重复部署）
        store2 = GuiSessionStore(state)
        store2.initialize(P1)
        self.assertTrue(state.is_phase_executed("senate"))
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)
        adv2 = store2.doAdvanceSenate()
        self.assertFalse(adv2["success"])


# ---------------------------------------------------------------------------
# S3 追加（SA v1.7 §8.1 E 段）：T05-07/T11-14 的 Store/Adapter/DATA 契约段——
# combatBattleResultDetail / combatResolvedWarCards（+truce cards）透传值与 API DTO
# 逐项相同（同一完整 v2 envelope，Store 不加工不丢字段）；无假 0 渲染源（R4-05）。
# DATA 断言止于 Store property/DTO（RENDER 归 SO Work Order，不冒充）。
# ---------------------------------------------------------------------------

_TOP_LAND_STATS = ["dice", "total_attack", "enemy_defence", "total_score", "losses",
                   "loot", "treasury_share", "commander_share", "faction_share", "soldier_share"]


def _combat_store(ctx):
    state = ctx["state"]
    store = GuiSessionStore(state)
    store.initialize(P1)
    return state, store


def _store_attack(state, store, war):
    sel = store.doSelectWar(war.id)
    assert sel["success"], sel.get("message")
    fb = store.doCombatAction(war.id, "attack")
    return fb


def _card_by_id(store, war_id):
    for c in store.combatView.get("active_wars", []) + store.combatView.get("truce_wars", []) \
            + store.combatResolvedWarCards:
        if c.get("war_id") == war_id:
            return c
    return None


class TestE05NavalBlockStoreCardsNoFakeLandStats(unittest.TestCase):
    """T05/06/07 DATA 契约：Store 消费同一 naval-block envelope；无顶层 Land 统计透传
    （QML/S4 消费源将读 nested stage——此处断言 DATA 面零假 0）。"""

    def _block_flow(self, fixture_builder):
        ctx = fixture_builder()
        state, store = _combat_store(ctx)
        war = ctx["war"]
        fb = _store_attack(state, store, war)
        self.assertTrue(fb["success"], fb.get("message"))
        data = fb["data"]
        self.assertEqual(data["schema_version"], 2)
        self.assertFalse(data["land"]["executed"])
        # Store property == API DTO（逐项相同）
        self.assertEqual(store.combatBattleResultDetail, data)
        # 卡（CURRENT_TURN_RESULT）附同一 result
        card = _card_by_id(store, war.id)
        self.assertIsNotNone(card)
        self.assertEqual(card["result"], data)
        # DATA 面零假 Land 统计（R4-05）：未执行不落顶层 Land 数字键
        for key in _TOP_LAND_STATS:
            self.assertNotIn(key, data, f"land=false 顶层 Land 统计必须 absent: {key}")
        return state, store, war, data

    def test_e05_stalemate_store_card(self):
        state, store, war, data = self._block_flow(lambda: F.build_fix03())
        self.assertEqual(data["naval"]["result"], "STALEMATE")
        self.assertEqual(data["result"], "naval_stalemate")
        # confirm → 仅 pending 清；卡保留完整 envelope
        cf = store.doConfirmBattleResult()
        self.assertTrue(cf["success"], cf.get("message"))
        self.assertEqual(store.combatBattleResultDetail, {})
        card = _card_by_id(store, war.id)
        self.assertEqual(card["result"]["land"]["executed"], False)
        self.assertEqual(card["result"]["naval"]["result"], "STALEMATE")

    def test_e06_defeat_store_card_loss_ids_consistent(self):
        import unittest.mock as mock
        ctx = F.build_fix04(n_fleets=5, naval_force="DEFEAT", land_force="TRIUMPH")
        with mock.patch("src.core.systems.naval_system.random.sample",
                        side_effect=lambda population, k: population[:k]):
            state, store, war, data = self._block_flow(lambda: ctx)
        self.assertEqual(data["naval"]["roman_losses"], 3)
        self.assertEqual(sorted(data["naval"]["casualty_fleet_ids"]), [1, 2, 3])
        # 实体一致（Store 不改变实体；损失逐舰一致）
        destroyed = [f for f in state.naval_system.get_all_fleets() if f.status.value == "destroyed"]
        self.assertEqual(sorted(f.number for f in destroyed), [1, 2, 3])

    def test_e07_disaster_store_card(self):
        state, store, war, data = self._block_flow(lambda: F.build_fix04(
            n_fleets=5, naval_force="DISASTER", land_force="TRIUMPH"))
        self.assertEqual(data["naval"]["roman_losses"], 5)
        self.assertEqual(sorted(data["naval"]["casualty_fleet_ids"]), [1, 2, 3, 4, 5])


class TestE11T14StoreDualStageCards(unittest.TestCase):
    """T11/T12/T13/T14 DATA 契约：Store/Adapter 透传两阶段完整 envelope 至 detail 与各类卡。"""

    def test_e11_victory_defeat_active_card_two_stages(self):
        ctx = F.build_fix05()
        state, store = _combat_store(ctx)
        war = ctx["war"]
        fb = _store_attack(state, store, war)
        self.assertTrue(fb["success"], fb.get("message"))
        data = fb["data"]
        self.assertEqual(store.combatBattleResultDetail, data)
        self.assertEqual(data["land"]["result"], "defeat")
        self.assertEqual(data["naval"]["result"], "VICTORY")
        self.assertEqual(war.status.value, "active")
        # active 卡 CURRENT_TURN_RESULT 附同一 envelope
        card = _card_by_id(store, war.id)
        self.assertEqual(card["result"], data)
        self.assertEqual(card["presentation_state"], "CURRENT_TURN_RESULT")
        # confirm → detail 清空但卡保留双阶段（Store 不透传丢字段）
        store.doConfirmBattleResult()
        self.assertEqual(store.combatBattleResultDetail, {})
        card2 = _card_by_id(store, war.id)
        self.assertEqual(card2["result"]["naval"]["result"], "VICTORY")
        self.assertEqual(card2["result"]["land"]["result"], "defeat")

    def test_e12_truce_card_keeps_two_results_after_confirm_newstore(self):
        ctx = F.build_fix06()  # Naval TRIUMPH + Land draw → TRUCE pending
        state, store = _combat_store(ctx)
        war = ctx["war"]
        fb = _store_attack(state, store, war)
        self.assertTrue(fb["success"], fb.get("message"))
        data = fb["data"]
        self.assertEqual(war.status.value, "truce")
        cf = store.doConfirmBattleResult()
        self.assertTrue(cf["success"], cf.get("message"))
        # TRUCE 锁定卡保留两结果（SA v1.7 §5.4：TRUCE_LOCKED 不阻止看历史结果）
        card = _card_by_id(store, war.id)
        self.assertIsNotNone(card)
        self.assertEqual(card["presentation_state"], "TRUCE_LOCKED")
        self.assertEqual(card["result"], data)
        self.assertEqual(card["result"]["naval"]["result"], "TRIUMPH")
        self.assertEqual(card["result"]["land"]["result"], "draw")
        # new Store 重建同值（TRUCE 卡两结果仍在；无重新 roll/resolve）
        _, store2 = _combat_store(ctx)
        card2 = _card_by_id(store2, war.id)
        self.assertEqual(card2["result"], data)

    def test_e13_resolved_card_keeps_two_results_new_store(self):
        ctx = F.build_fix07()  # Naval VICTORY + Land TRIUMPH → RESOLVED
        state, store = _combat_store(ctx)
        war = ctx["war"]
        fb = _store_attack(state, store, war)
        self.assertTrue(fb["success"], fb.get("message"))
        data = fb["data"]
        self.assertEqual(war.status.value, "resolved")
        store.doConfirmBattleResult()
        card = _card_by_id(store, war.id)
        self.assertIsNotNone(card)
        self.assertEqual(card["result"], data)
        self.assertEqual(card["result"]["naval"]["sea_control_acquired"], True)
        self.assertEqual(card["result"]["war_outcome"]["sea_control_after"], False)
        _, store2 = _combat_store(ctx)
        card2 = _card_by_id(store2, war.id)
        self.assertEqual(card2["result"], data)

    def test_e14_second_war_does_not_overwrite_a_via_store(self):
        """第二场 war 经 Store 结算后 A 卡 result 逐字段不变（war_results 每 war 独立缓存）。"""
        from src.core.entities.war import War, WarType
        from src.core.entities.figure import Figure
        ctx = F.build_fix05()
        state, store = _combat_store(ctx)
        war_a = ctx["war"]
        fb = _store_attack(state, store, war_a)
        self.assertTrue(fb["success"], fb.get("message"))
        store.doConfirmBattleResult()
        card_a = _card_by_id(store, war_a.id)
        envelope_a = card_a["result"]

        # 追加第二场非海军战并结算
        war_b = War(id="land_war_b2", name="Land War B2", war_type=WarType.FOREIGN,
                    strength=4, threat_level=3, rewards={"treasury": 80},
                    naval_required=False, enemy_land_current=2,
                    disaster_numbers=[99], standoff_numbers=[99])
        war_b.status = WarStatus.ACTIVE
        commander_b = Figure(id=203, name="Commander B2", faction_id="optimates", age=38)
        commander_b.martial = 3
        commander_b.office = "proconsul"
        commander_b.is_absent = True
        state.add_member(commander_b)
        ctx["faction"].member_ids.append(203)
        war_b.commander_id = 203
        state.get_war_system()._active_wars.append(war_b)
        F.recruit_legions_for_war(state, war_b, 203, count=2)
        state.config.testing.force_battle_result = "VICTORY"
        fb2 = _store_attack(state, store, war_b)
        self.assertTrue(fb2["success"], fb2.get("message"))
        self.assertEqual(war_b.status.value, "resolved")
        # A 不覆盖
        card_a2 = _card_by_id(store, war_a.id)
        self.assertEqual(card_a2["result"], envelope_a)
        # 新 Store 同态
        _, store2 = _combat_store(ctx)
        self.assertEqual(_card_by_id(store2, war_a.id)["result"], envelope_a)
        self.assertEqual(_card_by_id(store2, war_b.id)["result"], fb2["data"])


# ---------------------------------------------------------------------------
# S4 追加（SA v1.7 §5.5 / DA-Plan §1 S4，E consumer 段）— QML 源码绑定契约
# DATA-source：CombatStage.qml 的 resultBox（结果页）与 WarCard.cardResult（war 卡）
# 两个结果区共用同一 stage renderer（inline 组件/函数，纯 display），绑定字段与 v2
# envelope schema 对齐（naval/land 并列 executed）；未执行 stage 无数值行、无 ||0
# fallback（R4-05）；executed 字段缺失 → 「未记录」（暴露 DTO contract failure，不制造零）；
# 色彩按阶段读 result（禁顶层 success 两阶段同绿 / final War.RESOLVED 改写 Naval label）；
# readiness 不读 attack_available；无第二个确认钮（R4-02/R4-19）。
#
# 不冒充 RENDER：真实 Qt 渲染（两区域截图/滚动/可见性）归 SO Work Order
# WP-G-R4-NATIVE-QT-DUAL-STAGE-CAPTURE（G5 Required_By）——本类只断言源码绑定契约。
# ---------------------------------------------------------------------------

_QML = Path(__file__).resolve().parents[3] / "src" / "ui" / "gui" / "qml" / "stages" / "CombatStage.qml"

# v2 schema 绑定字段（SA v1.7 §5.1）——renderer 必须消费的 nested 键
_REQUIRED_STAGE_BINDINGS = [
    "naval.executed",
    "land.executed",
    "naval.result",
    "land.result",
    "sea_control_acquired",
]

# 固定语义文案（SA v1.7 §5.5 原文）
_REQUIRED_STAGE_TEXTS = [
    "海战: ",
    "陆战: 未执行 — 海战门未通过",
    "海军未就绪",
    "本战无需海军",
    "已获取制海权，本场跳过海战",
    "未记录",
]

# 旧 flat fallback 形态（制造假零的读取模式）——禁出现在源码中
_FORBIDDEN_FALLBACK_PATTERNS = [
    r"result\.dice \|\| 0",
    r"cardResult\.dice \|\| 0",
    r"result\.losses \|\| 0",
    r"cardResult\.losses \|\| 0",
    r"result\.loot \|\| 0",
]


class TestE4QmlDualStageSourceBindingContract(unittest.TestCase):
    """T04~T15 consumer 段：CombatStage.qml 源码绑定契约（DATA-source，非 RENDER）。"""

    @classmethod
    def setUpClass(cls):
        cls.qml = _QML.read_text(encoding="utf-8")

    def test_qml_file_exists_and_readable(self):
        self.assertTrue(_QML.exists(), f"CombatStage.qml not found: {_QML}")
        self.assertGreater(len(self.qml), 5000)

    def test_two_result_areas_share_one_stage_renderer(self):
        """resultBox 与 WarCard.cardResult 两区域使用同一 stage renderer（R4-03/R4-14 窄改）。"""
        # inline component 声明恰一次 + 两个结果区各实例化一次
        self.assertEqual(self.qml.count("component StageResultBlock"), 1,
                         "stage renderer 必须只声明一次（共用）")
        self.assertGreaterEqual(self.qml.count("StageResultBlock {"), 2,
                                "resultBox 与 cardResult 两区域都要实例化同一 renderer")
        # resultBox 区域与 card 结果区都引用（粗定位：声明之后的两处实例化）
        instantiations = [m.start() for m in re.finditer(r"StageResultBlock \{", self.qml)]
        self.assertGreaterEqual(len(instantiations), 2)

    def test_stage_bindings_aligned_with_v2_schema(self):
        """renderer 绑定字段与 v2 envelope schema 对齐（naval/land 并列 executed）。"""
        for binding in _REQUIRED_STAGE_BINDINGS:
            self.assertIn(binding, self.qml,
                          f"QML stage renderer 必须绑定 v2 schema 字段: {binding}")

    def test_fixed_stage_texts_present(self):
        """Land 未执行固定文案 / NOT_READY / Naval bypass 原因 / 缺失→未记录（R4-05）。"""
        for text in _REQUIRED_STAGE_TEXTS:
            self.assertIn(text, self.qml, f"缺少固定阶段文案: {text}")

    def test_no_fake_zero_fallback_patterns(self):
        """未执行 stage 不得以 ||0 fallback 制造假零（SA v1.7 §5.5/R4-05）。"""
        for pattern in _FORBIDDEN_FALLBACK_PATTERNS:
            self.assertIsNone(re.search(pattern, self.qml),
                              f"发现制造假零的旧读取模式: {pattern}")
        # 整体禁 result 数值直读 ||0（旧 resultBox 形态）；数字键只在 executed 分支读
        self.assertNotIn("dice || 0", self.qml)

    def test_stage_colors_read_per_stage_result(self):
        """outcome 色彩/图标按阶段读 result（禁顶层 success 两阶段同绿/禁 War.RESOLVED 改写 Naval）。"""
        self.assertIn("function stageResultColor", self.qml)
        # Naval 与 Land 两阶段的色彩函数调用点均存在（非单层 success 颜色）
        self.assertGreaterEqual(self.qml.count("stageResultColor("), 2)

    def test_readiness_not_read_from_attack_available(self):
        """readiness 渲染禁用从 API attack_available 读（SA v1.7 §5.5/§3.3）——未执行文案
        由 stage.reason 驱动（NO_READY_ASSIGNED_FLEET / NOT_REQUIRED / SEA_CONTROL_ALREADY_ACQUIRED）。"""
        self.assertNotIn("attack_available", self.qml,
                         "未执行 stage 渲染不得读 attack_available")
        self.assertIn("NO_READY_ASSIGNED_FLEET", self.qml)

    def test_single_confirm_button_no_second_confirmation(self):
        """整次 action 一个确认钮（R4-02/R4-19）：文件内恰一个 ActionButton（确认战果）。"""
        self.assertEqual(self.qml.count("ActionButton {"), 1,
                         "不得出现第二确认按钮")
        self.assertEqual(self.qml.count("确认战果"), 1)

    def test_card_result_uses_same_renderer_not_flat_duplicate(self):
        """WarCard.cardResult 结果区不再维护 flat 重复渲染块（共用 renderer 防两区域漂移）。"""
        # 旧 AC-4.3 flat 重复块（cardResult.dice 直读）应已被 renderer 替换
        self.assertNotIn("cardResult.dice", self.qml)
        self.assertNotIn("cardResult.losses", self.qml)


if __name__ == "__main__":
    unittest.main()
