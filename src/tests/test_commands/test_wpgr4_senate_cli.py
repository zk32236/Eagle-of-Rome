# src/tests/test_commands/test_wpgr4_senate_cli.py
"""WP-G-R4 S1（SA v1.7 §8.1 G，T-R4-16）— SenateCommand CLI 最小收敛契约（§2.3b）。

R5 supersede（Plan §4.2 L8/L11；SA §5.2 C-M08 + §2.7 A-I14 / §4.10 C-M09，DA-4）：
CLI `takeover`/`cancel_takeover` 子命令与 mandatory M_open 门均已退役；human 经唯一整包
入口（卡 unchecked → next 空结束 → resolve → advance_senate_phase）合法收敛。
本文件保留：auto canonical 空批 P=true 推进；resolve 注入失败不 mark executed 且可重试；
commanderless ACTIVE 不再阻止空结束（保留反例：无 checked 卡不得自动任命/部署）。
"""
import unittest
from unittest import mock

from src.core.systems.political_system import PoliticalSystem
from src.core.entities.war import WarStatus
from src.api import senate_api
from src.ui.commands.phase_senate import SenateCommand
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1


class TestT16SenateCli(unittest.TestCase):
    def _human_state(self, auto_senate=False, **fix_kwargs):
        ctx = F.build_fix01(**fix_kwargs)
        state = ctx["state"]
        state.config._config["testing"]["auto_senate"] = auto_senate
        return state, ctx

    def test_t16_auto_mode_takeover_submit_lock_deploy_via_advance(self):
        """auto 模式全链：AI canonical 顺序（AI 整包 → resolve → advance 部署）→ executed。"""
        state, ctx = self._human_state(auto_senate=True)
        consul, war_a = ctx["consul"], ctx["war_a"]
        cmd = SenateCommand(state)
        result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(state.is_phase_executed("senate"))
        # auto AI 路径零直连接管；若边界确实部署了则 commander = Consul
        if state.get_takeover_pending() is not None or war_a.commander_id is not None:
            self.assertEqual(war_a.commander_id, consul.id,
                             "部署后 war commander = Consul")
        # 防误：auto 无提案空结束也需合法完成
        self.assertTrue(state.get_phase_result("senate"))

    def test_t16_human_takeover_command_locks_then_next_deploys(self):
        """R5 supersede（Plan §4.2 L8；SA §5.2 C-M08，DA-4）：CLI `takeover` 子命令退役——
        human 经「卡 unchecked → next 空结束 → resolve → advance」合法完成；commanderless
        ACTIVE 不再被强制接管（commander 保持 None，无 takeover_deploy）。"""
        state, ctx = self._human_state()
        consul, war_a = ctx["consul"], ctx["war_a"]
        with mock.patch("builtins.input", side_effect=["next", "next", "next"]):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertIsNone(war_a.commander_id, "无 checked 卡 → 不自动任命")
        self.assertIsNone(state.get_takeover_pending(), "旧直连接管已退役")
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(das, [])

    def test_t16_m_open_refusal_does_not_execute(self):
        """R5 supersede（Plan §4.2 L8；SA §2.7 A-I14 / §4.10 C-M09，DA-4）：mandatory M_open
        门拆除——commanderless ACTIVE 不再阻止空结束；旧 `takeover` CLI 命令不再部署。"""
        state, ctx = self._human_state()
        with mock.patch("builtins.input", side_effect=["next", "next", "next"]):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertTrue(result, "R5：无 mandatory 门 → 合法空结束完成")
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertTrue(state.get_phase_result("senate"))
        self.assertIsNone(ctx["war_a"].commander_id, "commanderless 合法（无强制接管）")
        self.assertIsNone(state.get_takeover_pending())

    def test_t16_resolve_failure_does_not_execute(self):
        """resolve 注入失败（无真实 R）→ 部署失败不 mark executed/不 return True。

        R6（DA-6 B3c-cont2）：CLI 唯一 finalization 入口 = `senate_api.finalize_senate_if_ready`
        （`resolve_senate` 已退役为其兼容别名，patch 别名不再拦截）；旧 `takeover` 子命令退役，
        human 经「卡 unchecked → next 空结束 → finalize → advance」合法收敛。
        """
        state, ctx = self._human_state()
        war_a = ctx["war_a"]
        injected = {"success": False, "message": "injected resolve failure",
                    "data": {}, "errors": ["injected"]}
        with mock.patch("builtins.input", side_effect=["next", "next", "next"]), \
             mock.patch.object(senate_api, "finalize_senate_if_ready",
                               return_value=injected):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertFalse(result)
        self.assertFalse(state.is_phase_executed("senate"))
        self.assertIsNone(war_a.commander_id, "部署未发生")
        # 可重试（R6）：包已发布不撤销；解除注入后，同一会期经服务端唯一 finalization
        # 入口 `finalize_senate_if_ready` 补齐（可重试/退出窄路径）→ 边界 advance 推进成功。
        recovered = senate_api.finalize_senate_if_ready(state)
        self.assertTrue(recovered["success"], recovered.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        adv = senate_api.advance_senate_phase(state, F.P1)
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"), "重试成功路径")

    def test_t16_ai_canonical_tail_p_true_preserved(self):
        """AI canonical auto_submit_proposals 尾部 P=true 语义保留（AI 空批可推进）。"""
        state = F.make_base_state(turn_number=1, year=-282, config=F._base_config(auto_senate=True))
        faction = F.add_faction(state, treasury=500)
        F.add_player(state)
        F.add_consul(state, faction)
        state._treasury = 500
        # 无 war/无提案 → AI 空批 → P=true → resolve 空结算 → advance（无 T 普通推进）
        state.config._config["testing"]["auto_senate"] = True
        with mock.patch("builtins.input", side_effect=[]):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(state.get_phase_result("senate"))
        self.assertTrue(state.is_phase_executed("senate"))


if __name__ == "__main__":
    unittest.main()
