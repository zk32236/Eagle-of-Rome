# src/tests/test_commands/test_wpgr4_combat_parity.py
"""WP-G-R4 S2（SA v1.7 §6.1 Parity/§8.1 F 初建）— legacy `_resolve_battle`/`_apply_battle_result`
直接测试：NOT_READY / 已获控 skip / identity 窄补不能因主 execute 未用而漏测；T04 CLI 面。

权威：SA-Design-WP-G-R4 v1.7 §3.1/§4.2/§6.1（legacy 窄 parity，不改 CLI 架构 R4-01）。
"""
import io
import unittest
from unittest import mock
from contextlib import redirect_stdout

from src.core.entities.war import WarStatus
from src.ui.commands.phase_combat import CombatCommand
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1


class TestLegacyResolveBattleNarrowParity(unittest.TestCase):
    def _legacy_cmd(self, ctx):
        state = ctx["state"]
        cmd = CombatCommand(state)
        return cmd, state

    def test_legacy_resolve_battle_not_ready_zero_side_effects(self):
        ctx = F.build_fix02(naval_force="TRIUMPH", ready_override=None)
        state, war = ctx["state"], ctx["war"]
        cmd, state = self._legacy_cmd(ctx)
        ms = state.get_military_system()
        ws = state.get_war_system()
        duration_before = war.duration
        with io.StringIO() as buf, redirect_stdout(buf):
            cmd._resolve_battle(ws, war, cmd._get_terms() if hasattr(cmd, "_get_terms") else None)
        # NOT_READY：不加 duration、不解除/指派 commander、无陆战伤亡
        self.assertEqual(war.duration, duration_before, "NOT_READY 零副作用（不加 duration）")
        self.assertIsNotNone(war.commander_id, "Commander 保持")
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_legacy_resolve_battle_sea_control_skip(self):
        """已获控 → 跳过海战（BYPASSED），直接陆战路径（有陆战战力）不触发海军 resolver。"""
        ctx = F.build_fix03(naval_force="VICTORY", land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        # 预置已获控（模拟上一回合 TRIUMPH）
        war._sea_control_acquired = True
        cmd, state = self._legacy_cmd(ctx)
        ws = state.get_war_system()
        ns = state.naval_system
        with mock.patch.object(ns, "resolve_naval_battle",
                               side_effect=AssertionError("已获控不得再触发海战")):
            with io.StringIO() as buf, redirect_stdout(buf):
                cmd._resolve_battle(ws, war, None)
        # 陆战正常结算（无 mock 海战调用即通过；结果可能终结战争）
        self.assertTrue(True)

    def test_legacy_apply_battle_result_passes_explicit_identity(self):
        """_apply_battle_result 两个成功分支显式传 CRT 词（wrap WarSystem.resolve_war 断言）。"""
        ctx = F.build_fix08(land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        ms = state.get_military_system()
        commander = state.get_member(war.commander_id)
        legions = ms.get_legions_for_battle(war.id)
        ws = state.get_war_system()
        seen = {}
        orig = ws.resolve_war

        def spy(war_id, victory, **kwargs):
            seen["kwargs"] = kwargs
            return orig(war_id, victory, **kwargs)

        cmd, state = self._legacy_cmd(ctx)
        with mock.patch.object(ws, "resolve_war", spy):
            cmd._apply_battle_result(ws, war, commander, "VICTORY", None, ms,
                                     legions, sum(l.get_combat_strength() for l in legions))
        self.assertEqual(seen.get("kwargs", {}).get("combat_result"), "victory")


# ---------------------------------------------------------------------------
# S3 追加（SA v1.7 §8.1 F 段：公开 CLI/auto 同 DTO 消费段）——auto_resolve_combat
# （CLI CombatCommand.execute 与 Adapter.auto 共享入口）消费同一 v2 envelope：naval-block
# 战与双阶段战均按真实 envelope 结算/推进；CLI 不崩溃、结果与 API DTO 同值。
# ---------------------------------------------------------------------------

class TestS3PublicCLIAndAutoConsumeSameDTO(unittest.TestCase):
    def test_auto_resolve_naval_victory_land_defeat_envelope(self):
        """auto（公开 seam）→ battles 消费同一完整 envelope（land defeat + naval victory）。"""
        ctx = F.build_fix05()  # Naval VICTORY + Land DEFEAT
        state, war = ctx["state"], ctx["war"]
        from src.api import combat_api
        res = combat_api.auto_resolve_combat(state, P1)
        self.assertTrue(res["success"], res.get("message"))
        data = res["data"]
        self.assertEqual(data["wars_resolved"], 1)
        self.assertEqual(len(data["battles"]), 1)
        battle = data["battles"][0]
        self.assertEqual(battle["schema_version"], 2)
        self.assertEqual(battle["land"]["result"], "defeat")
        self.assertEqual(battle["naval"]["result"], "VICTORY")
        # 持久同值（auto 路径亦写 pending/war_results 同一完整 envelope）
        phase = state.get_phase_result("combat") or {}
        self.assertEqual(phase["war_results"][war.id], battle)
        # War ACTIVE（land DEFEAT 不终结）；sea 保持
        self.assertEqual(war.status.value, "active")
        self.assertTrue(war.sea_control_acquired)
        self.assertTrue(data["completed"])
        self.assertTrue(state.is_phase_executed("combat"))

    def test_cli_execute_naval_block_stalemate_completes(self):
        """CLI CombatCommand.execute → auto_resolve_combat：naval-block envelope 消费不崩溃。"""
        ctx = F.build_fix03()  # Naval STALEMATE + Land TRIUMPH（未消费）
        state, war = ctx["state"], ctx["war"]
        cmd = CombatCommand(state)
        out = io.StringIO()
        with redirect_stdout(out):
            ok = cmd.execute([])
        self.assertTrue(ok)
        text = out.getvalue()
        # land 未执行 → 无「军团损失/战利品」假渲染源；阶段完成
        self.assertTrue(state.is_phase_executed("combat"))
        self.assertEqual(war.status.value, "active")
        phase = state.get_phase_result("combat") or {}
        envelope = phase["war_results"][war.id]
        self.assertFalse(envelope["land"]["executed"])
        self.assertEqual(envelope["naval"]["result"], "STALEMATE")
        self.assertNotIn("Legion losses: 0", text)

    def test_cli_execute_naval_victory_land_defeat_prints_land_result(self):
        """CLI 消费 land-executed envelope（顶层 alias 兼容旧 renderer 读取，S4 改 nested）。"""
        ctx = F.build_fix05()  # Naval VICTORY + Land DEFEAT
        state, war = ctx["state"], ctx["war"]
        cmd = CombatCommand(state)
        out = io.StringIO()
        with redirect_stdout(out):
            ok = cmd.execute([])
        self.assertTrue(ok)
        text = out.getvalue()
        self.assertIn("战败", text)  # land result_label（顶层 alias）
        self.assertEqual(war.status.value, "active")
        self.assertTrue(state.is_phase_executed("combat"))


# ---------------------------------------------------------------------------
# S4 追加（SA v1.7 §5.5 / DA-Plan §1 S4，F consumer 段）——主 CLI execute nested 两
# stage 文本渲染：consume 同一 v2 envelope（与 DATA 同 run 值一致，数值逐项取自
# land/naval stage，非旧顶层 alias 推断）；未执行 stage 固定文案；unavailable 提示。
# ---------------------------------------------------------------------------


class TestS4MainCliNestedDualStageText(unittest.TestCase):
    """T04~T15 CLI consumer 段：CombatCommand.execute → auto_resolve_combat → nested 文本。"""

    def _run_cli(self, ctx):
        state = ctx["state"]
        cmd = CombatCommand(state)
        out = io.StringIO()
        with redirect_stdout(out):
            ok = cmd.execute([])
        self.assertTrue(ok, out.getvalue())
        return state, out.getvalue()

    def test_cli_naval_victory_land_defeat_two_stage_lines(self):
        """T11 CLI 面：Naval VICTORY + Land DEFEAT → 两 stage 文本与 envelope 同值。"""
        ctx = F.build_fix05()
        state, text = self._run_cli(ctx)
        war = ctx["war"]
        envelope = (state.get_phase_result("combat") or {})["war_results"][war.id]
        self.assertIn("海战: 胜利", text)
        self.assertIn("陆战: 战败", text)
        # 数值与 DATA envelope 逐项一致（舰队损失/海权阶段结果）
        self.assertIn(f"舰队损失: {envelope['naval']['roman_losses']} 艘", text)
        self.assertIn("海权: 已获取制海权", text)
        # 无假顶行：naval 阶段读 naval.result（VICTORY ≠ TRIUMPH）
        self.assertNotIn("海战: 大胜", text)

    def test_cli_naval_stalemate_block_land_not_executed_fixed_text(self):
        """T05 CLI 面：Naval STALEMATE → Land 未执行固定文案；无 Land 数值行（R4-05）。"""
        ctx = F.build_fix03()
        state, text = self._run_cli(ctx)
        war = ctx["war"]
        self.assertIn("海战: 僵持", text)
        self.assertIn("陆战: 未执行 — 海战门未通过", text)
        self.assertIn("海权: 未获取制海权", text)
        self.assertNotIn("骰子:", text)
        self.assertNotIn("军团损失:", text)
        self.assertNotIn("战利品:", text)
        self.assertEqual(war.status.value, "active")

    def test_cli_no_ready_unavailable_not_battle_no_land_rows(self):
        """T04 CLI 面：零 ready → unavailable 提示（非 battles）；无任何 Land 数值行。"""
        ctx = F.build_fix02(naval_force="TRIUMPH", land_force="TRIUMPH", ready_override=None)
        state = ctx["state"]
        state.mark_phase_executed("senate")  # fix02 未预标 senate（combat 入口前置，同 fix03+）
        state, text = self._run_cli(ctx)
        war = ctx["war"]
        # force TRIUMPH 不穿透；unavailable 名单输出（含战名/原因）
        self.assertIn("海军未就绪", text)
        self.assertIn(war.name, text)
        self.assertIn("NAVAL_NOT_READY", text)
        self.assertNotIn("陆战: 胜利", text)
        self.assertNotIn("陆战: 大胜", text)
        self.assertNotIn("骰子:", text)
        self.assertTrue(state.is_phase_executed("combat"))

    def test_cli_non_naval_bypass_reason_not_victory(self):
        """T15 CLI 面：非海军 war → Naval bypass（NOT_REQUIRED）说明原因，不渲染作海战胜利。"""
        ctx = F.build_fix08(land_force="VICTORY")
        state, text = self._run_cli(ctx)
        war = ctx["war"]
        self.assertIn("海战: 未执行 — 本战无需海军", text)
        self.assertIn("陆战: 胜利", text)
        self.assertNotIn("海战: 胜利", text)
        self.assertEqual(war.status.value, "resolved")

    def test_cli_sea_acquired_bypass_reason(self):
        """已获制海权 → Naval bypass（SEA_CONTROL_ALREADY_ACQUIRED）说明原因；Land 正常执行。"""
        ctx = F.build_fix05()
        state = ctx["state"]
        war = ctx["war"]
        war._sea_control_acquired = True  # 已获控（上一回合 TRIUMPH 合法持续态）
        _, text = self._run_cli(ctx)
        self.assertIn("海战: 未执行 — 已获取制海权，本场跳过海战", text)
        self.assertIn("陆战: 战败", text)

    def test_cli_naval_triumph_land_draw_truce_two_stage_lines(self):
        """T12 CLI 面：Naval TRIUMPH + Land draw → TRUCE pending；两 stage 文本齐全。"""
        ctx = F.build_fix06()
        state, text = self._run_cli(ctx)
        war = ctx["war"]
        envelope = (state.get_phase_result("combat") or {})["war_results"][war.id]
        self.assertIn("海战: 大胜", text)
        self.assertIn("陆战: 僵持", text)
        self.assertEqual(envelope["land"]["result"], "draw")
        self.assertEqual(envelope["naval"]["result"], "TRIUMPH")
        self.assertEqual(war.status.value, "truce")


if __name__ == "__main__":
    unittest.main()
