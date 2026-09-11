# src/tests/test_commands/test_wpgr4_senate_cli.py
"""WP-G-R4 S1（SA v1.7 §8.1 G，T-R4-16）— SenateCommand CLI 最小收敛契约（§2.3b）。

Takeover 选择/Submit 经 takeover_war 写 T（不部署）；human 零提案 next/n 先显式空选择
写 P→resolve→真实 R→经 advance_senate_phase 部署→executed+True（正）；M_open 拒 /
resolve 注入失败 / 部署失败 → mark_phase_executed 未调、execute 返回非 True、无额外
副作用、可重试退出；LOCKED T 时 M_open=False 放行；AI canonical 尾部 P=true 保留。
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
        """auto 模式全链：AI canonical 顺序（lock T→P→resolve→advance 部署）→ executed。"""
        state, ctx = self._human_state(auto_senate=True)
        consul, war_a = ctx["consul"], ctx["war_a"]
        cmd = SenateCommand(state)
        result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(state.is_phase_executed("senate"))
        # auto AI 接管锁 T（decider chance=1.0 默认）→ 部署恰一次
        if state.get_takeover_pending() is not None or war_a.commander_id is not None:
            self.assertEqual(war_a.commander_id, consul.id,
                             "部署后 war commander = Consul")
        # 防误：auto 无提案空结束也需合法完成
        self.assertTrue(state.get_phase_result("senate"))

    def test_t16_human_takeover_command_locks_then_next_deploys(self):
        """human CLI：takeover 命令锁 T（零部署）→ next 空选择→resolve→advance 部署→executed。"""
        state, ctx = self._human_state()
        consul, war_a = ctx["consul"], ctx["war_a"]
        with mock.patch("builtins.input", side_effect=["next", "takeover pyrrhic_war 1",
                                                      "next", "next"]):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(war_a.commander_id, consul.id)
        self.assertTrue(consul.is_absent)
        das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
        self.assertEqual(len(das), 1)

    def test_t16_m_open_refusal_does_not_execute(self):
        """M_open（无 LOCKED T 的 commanderless ACTIVE）→ CLI 不推进、不 mark executed。"""
        state, ctx = self._human_state()
        with mock.patch("builtins.input", side_effect=["next", "next", "next"]):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertFalse(result, "M_open 拒绝 → 非 True")
        self.assertFalse(state.is_phase_executed("senate"), "拒绝不得 mark executed")
        self.assertFalse(state.get_phase_result("senate"))

    def test_t16_resolve_failure_does_not_execute(self):
        """resolve 注入失败（无真实 R）→ 部署失败不 mark executed/不 return True。"""
        state, ctx = self._human_state()
        war_a = ctx["war_a"]
        with mock.patch("builtins.input", side_effect=["next", "takeover pyrrhic_war 1",
                                                      "next", "next"]), \
             mock.patch.object(senate_api, "resolve_senate",
                               return_value={"success": False, "message": "injected resolve failure",
                                             "data": {}, "errors": ["injected"]}):
            cmd = SenateCommand(state)
            result = cmd.execute([])
        self.assertFalse(result)
        self.assertFalse(state.is_phase_executed("senate"))
        self.assertIsNone(war_a.commander_id, "部署未发生")
        # 可重试：解除注入后重跑成功
        with mock.patch("builtins.input", side_effect=["next", "next", "next"]):
            cmd2 = SenateCommand(state)
            result2 = cmd2.execute([])
        self.assertTrue(result2, "重试成功路径（LOCKED T 放行）")
        self.assertTrue(state.is_phase_executed("senate"))

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
