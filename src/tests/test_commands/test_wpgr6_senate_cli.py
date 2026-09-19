# src/tests/test_commands/test_wpgr6_senate_cli.py
"""WP-G-R6 DA-1（SA §A.4；CLI 单包证据）— CLI 编辑会期本地整包草稿 + 一次 propose_many。

证据分类 = DATA（RENDER 归 SO）。断言方向：
- ``propose`` 只编辑本地整包草稿（不发布）；legacy 单提案入口不再是生产 CLI 路径；
- Proposal 阶段 ``next`` 一次 ``propose_many``（0…N）；两次 draft edit 后 = **一个双 War 包**
  （不是两个已发布单包）；
- CLI 卡表消费同一 WarCardView（含真实 command / 缺 route 不列出）。
"""
import ast
import os
import pathlib
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.entities.province import Province
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_senate import SenateCommand
from src.tests.fixtures.wpgr5_fixtures import build_r5_base, FIXED
from src.tests.fixtures.wpgr6_fixtures import (
    build_f6,
    build_f6_base,
    pool_legion_ids,
    submit_api,
    submit_gui,
)


def _make_cmd(fx) -> SenateCommand:
    cmd = SenateCommand(fx["state"])
    cmd._current_consul_player_id = fx["player_id"]
    cmd._print_proposal_options()  # 构建 _proposals_map（消费 WarCardView）
    return cmd


def _key_for(cmd: SenateCommand, war_id: str, mode: str) -> str:
    for key, (ptype, params) in cmd._proposals_map.items():
        if ptype == "war" and params.get("war_id") == war_id and params.get("mode") == mode:
            return key
    raise AssertionError(f"no CLI key for war={war_id} mode={mode}")


class TestCliLocalPackageDraft(unittest.TestCase):
    def test_propose_edits_draft_without_publishing(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        with mock.patch.object(senate_api, "propose",
                               side_effect=AssertionError("CLI must not use legacy single propose")):
            cmd._handle_propose([_key_for(cmd, FIXED["war_ongoing"], "command"),
                                 str(fx["cmd_a"].id), "0"])
            cmd._handle_propose([_key_for(cmd, FIXED["war_passive"], "command"),
                                 str(fx["consul_id"]), "0"])
        self.assertEqual(len(cmd._package_drafts), 2)
        self.assertEqual(fx["state"].get_senate_proposals(), [], "编辑草稿阶段不得发布")

    def test_two_draft_edits_then_next_is_one_dual_war_package(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        cmd._handle_propose([_key_for(cmd, FIXED["war_ongoing"], "command"),
                             str(fx["cmd_a"].id), "0"])
        cmd._handle_propose([_key_for(cmd, FIXED["war_passive"], "command"),
                             str(fx["consul_id"]), "0"])
        calls = []

        def _capture(state, player_id, proposals):
            calls.append(proposals)
            return {"success": True, "message": "ok", "data": {"created": []}, "errors": []}

        with mock.patch.object(senate_api, "propose_many", side_effect=_capture):
            ok = cmd._submit_local_package()
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1, "next 必须只提交一个整包（propose_many 恰一次）")
        war_drafts = [d for d in calls[0] if d.get("type") == "war_proposal"]
        self.assertEqual(len(war_drafts), 2, "两次 draft edit 后包内应有两个 War 草案")

    def test_real_submit_shares_single_package_id(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        cmd._handle_propose([_key_for(cmd, FIXED["war_ongoing"], "command"),
                             str(fx["cmd_a"].id), "0"])
        cmd._handle_propose([_key_for(cmd, FIXED["war_passive"], "command"),
                             str(fx["consul_id"]), "0"])
        self.assertTrue(cmd._submit_local_package())
        # R6（SA §A.1，DA-2 B2）：ongoing/passive 真实 War 的 command 项 → consul_direct，
        # 不再落为 Senate 提案；两个 direct 共享同一个整包 package_id。
        proposals = fx["state"].get_senate_proposals()
        self.assertEqual(proposals, [], "真实 War command 不得发 Senate 提案")
        decisions = fx["state"].get_consul_war_decisions(fx["state"].get_senate_session())
        self.assertEqual(len(decisions), 2, decisions)
        package_ids = {d.get("package_id") for d in decisions.values()}
        self.assertEqual(len(package_ids), 1, "两次 draft edit 必须是同一个整包")
        for d in decisions.values():
            self.assertNotIn("proposal_id", d)
            self.assertEqual(d["decision_state"], "FROZEN")
        self.assertTrue(fx["state"].senate_proposal_decision_complete)

    def test_repeat_propose_same_war_overwrites_not_appends(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        key = _key_for(cmd, FIXED["war_ongoing"], "command")
        cmd._handle_propose([key, str(fx["cmd_a"].id), "0"])
        cmd._handle_propose([key, str(fx["cmd_b"].id), "0"])
        war_drafts = [d for d in cmd._package_drafts if d.get("type") == "war_proposal"]
        self.assertEqual(len(war_drafts), 1, "一个 (session, war_id) 最多一个 authoritative item")


class TestCliWarCardProjection(unittest.TestCase):
    def test_map_includes_real_command_cards_with_route(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        mapped_war_ids = {params.get("war_id") for t, params in cmd._proposals_map.values()
                          if t == "war"}
        # 含真实 command（ongoing/passive）——不只是 THREAT
        self.assertIn(FIXED["war_ongoing"], mapped_war_ids)
        self.assertIn(FIXED["war_passive"], mapped_war_ids)
        # pending_peace 同时列 command 与 peace 两种 mode
        peace_entries = [params.get("mode") for t, params in cmd._proposals_map.values()
                         if t == "war" and params.get("war_id") == FIXED["war_peace"]]
        self.assertIn("command", peace_entries)
        self.assertIn("peace", peace_entries)

    def test_missing_route_card_not_listed(self):
        fx = build_r5_base(turn_number=1)
        cmd = _make_cmd(fx)
        for t, params in cmd._proposals_map.values():
            if t != "war":
                continue
            card = params.get("card") or {}
            authority = (card.get("authority_by_mode") or {}).get(params.get("mode"))
            self.assertIn(authority, ("senate_vote", "consul_direct"))


# ===========================================================================
# DA-3 B4（SA v1.1 §C.5.2 / §C.6；DA-Plan §2 DA-3 B4）— CLI 第二调用退役（N23）+ 静态负测
# ===========================================================================

class _PassDecider:
    def decide_vote(self, issue, faction, state):
        return True


def _add_rebellion(state, province_id=991, governor_id=None):
    """新增 commanderless 起义（province governor = 自动层候选）+ 登记 active。"""
    ws = state.get_war_system()
    province = Province(province_id=province_id, name=f"Rebel Province {province_id}",
                        total_land=1000, conquered=True,
                        governor_id=governor_id, governor_designate_id=None)
    state.add_province(province)
    war = ws.create_rebellion_war(province)
    ws._active_wars.append(war)
    return war


def _military_projection(state):
    """军事投影（War 容器 + Commander + Legion 绑定 + Fleet 绑定）——跨入口 diff 对象。"""
    ws = state.get_war_system()
    ms = state.get_military_system()
    proj = {}
    for war in ws.get_all_wars():
        proj[war.id] = {
            "status": war.status.value,
            "commander_id": war.commander_id,
            "legion_numbers": sorted(getattr(war, "legion_numbers", []) or []),
            "legion_bindings": sorted(l.number for l in ms.get_legions_for_battle(war.id)),
            "assigned_fleet_ids": sorted(getattr(war, "assigned_fleet_ids", []) or []),
        }
    return proj


def _effect_summary(state, adv):
    receipt = state.get_war_execution_receipt(adv["data"]["execution_id"])
    return receipt["effect_summary"]


def _cli_cmd(state):
    cmd = SenateCommand(state)
    cmd._current_consul_player_id = FIXED["player"]
    return cmd


class TestCliSecondCallRetirement(unittest.TestCase):
    """N23：触发 `_handle_step_5` → 无独立军事写；API/CLI 同 `execution_id` 公式 + 同投影。"""

    def test_step5_source_has_no_direct_hook_calls(self):
        """静态面：`_handle_step_5` 方法体内不得再出现三个 hook 的直接调用（含打印分支）。"""
        from src.ui.commands import phase_senate as mod
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        body = src.split("def _handle_step_5", 1)[1].split("def _handle_next", 1)[0]
        self.assertNotIn("assign_fleets_to_active_wars", body)
        self.assertNotIn("assign_governors", body)
        self.assertNotIn("assign_rebellion_commanders", body)

    def test_step5_does_not_call_fleet_or_rebellion_hooks(self):
        """动态面：`_handle_step_5` 内 Fleet / 起义 hook 调用 = 0（且军事投影不变）。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        sub = submit_api(state, ctx["drafts"])
        self.assertTrue(sub["success"], sub.get("errors"))
        before = _military_projection(state)
        with mock.patch.object(senate_api, "assign_fleets_to_active_wars",
                               side_effect=AssertionError("CLI 不得再直接调用 Fleet hook")), \
                mock.patch.object(WarSystem, "assign_rebellion_commanders",
                                  side_effect=AssertionError("CLI 不得再直接调用起义 hook")):
            _cli_cmd(state)._handle_step_5()
        # 零独立军事写（pre-boundary 军事投影不变）；服务端 resolve 已落 phase_result
        self.assertEqual(_military_projection(state), before)
        self.assertTrue(state.get_phase_result("senate"))

    def test_step5_governor_finalization_runs_once_server_side(self):
        """Governor 政治步骤只由服务端 `resolve_senate` 执行一次（CLI 不再二次调用）。"""
        ctx = build_f6("F6-DD")
        state = ctx["state"]
        self.assertTrue(submit_api(state, ctx["drafts"])["success"])
        real = senate_api.assign_governors
        calls = []

        def _spy(state_arg):
            calls.append(1)
            return real(state_arg)

        with mock.patch.object(senate_api, "assign_governors", side_effect=_spy):
            _cli_cmd(state)._handle_step_5()
        self.assertEqual(len(calls), 1, "服务端 finalization 内恰一次；CLI 无第二次")

    def test_api_cli_gui_same_execution_identity_and_retained_effects(self):
        """API 路径 == CLI 路径 == GUI 路径：同 `execution_id` 公式、同 `retained_effects[]`、军事 diff = 0。"""
        api_ctx = build_f6("F6-DD")
        cli_ctx = build_f6("F6-DD")
        gui_ctx = build_f6("F6-DD")
        a_state, c_state, g_state = (api_ctx["state"], cli_ctx["state"], gui_ctx["state"])
        # API 提交面
        self.assertTrue(submit_api(a_state, api_ctx["drafts"])["success"])
        self.assertTrue(submit_api(c_state, cli_ctx["drafts"])["success"])
        # GUI 提交面（Store → Adapter → API）
        _store, fb = submit_gui(g_state, gui_ctx["drafts"])
        self.assertTrue(fb["success"], fb.get("message"))
        # 双路径注入同一自动层对象（起义），使 `retained_effects[]` 非空、可比
        for ctx, state in ((api_ctx, a_state), (cli_ctx, c_state), (gui_ctx, g_state)):
            _add_rebellion(state, governor_id=ctx["cmd_gov"].id)
        self.assertTrue(senate_api.resolve_senate(a_state, vote_decider=_PassDecider())["success"])
        _cli_cmd(c_state)._handle_step_5()          # CLI 消费路径（无第二军事执行者）
        self.assertTrue(senate_api.resolve_senate(g_state, vote_decider=_PassDecider())["success"])
        adv = {"api": senate_api.advance_senate_phase(a_state, FIXED["player"]),
               "cli": senate_api.advance_senate_phase(c_state, FIXED["player"]),
               "gui": senate_api.advance_senate_phase(g_state, FIXED["player"])}
        for leg, res in adv.items():
            self.assertTrue(res["success"], f"{leg}: {res.get('message')}")
        es = {leg: _effect_summary(st, adv[leg]) for leg, st in
              (("api", a_state), ("cli", c_state), ("gui", g_state))}
        # 同 `retained_effects[]` / `deferred[]`（自动层效果不因入口而变）
        self.assertEqual(es["api"]["retained_effects"], es["cli"]["retained_effects"])
        self.assertEqual(es["api"]["retained_effects"], es["gui"]["retained_effects"])
        self.assertEqual(es["api"]["retained_effects_deferred"],
                         es["cli"]["retained_effects_deferred"])
        self.assertEqual(es["api"]["retained_effects_deferred"],
                         es["gui"]["retained_effects_deferred"])
        self.assertTrue(es["api"]["retained_effects"], "本 fixture 应产生自动层效果以证明可比性")
        # 军事投影 diff = 0（三入口两两相等）
        self.assertEqual(_military_projection(a_state), _military_projection(c_state))
        self.assertEqual(_military_projection(a_state), _military_projection(g_state))
        # 同 `execution_id` 公式：身份 = (session, package_id, stage, protocol)，与入口无关
        for leg, st in (("api", a_state), ("cli", c_state), ("gui", g_state)):
            session = st.get_senate_session()
            pkg = st.get_senate_package_id_for_session(session)
            self.assertEqual(adv[leg]["data"]["execution_id"],
                             f"{session}:{pkg}:senate_to_combat:v2")
        # CLI 不产生第二执行身份：重放返回同一 execution_id（零再部署）
        adv_again = senate_api.advance_senate_phase(c_state, FIXED["player"])
        self.assertEqual(adv_again["data"]["execution_id"], adv["cli"]["data"]["execution_id"])
        self.assertTrue(adv_again["data"].get("replayed"))


class TestStaticNegativeZeroCallers(unittest.TestCase):
    """DA-Plan R-1 / G3 P2-1：`_execute_war_declaration` 零调用者；`auto_recruit_and_assign` 零生产引用。"""

    @staticmethod
    def _refs(name):
        root = pathlib.Path(PROJECT_ROOT) / "src"
        hits = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == name:
                    hits.append(f"{path.relative_to(root)}:{node.lineno}")
                elif isinstance(node, ast.Name) and node.id == name:
                    hits.append(f"{path.relative_to(root)}:{node.lineno}")
        return hits

    def test_execute_war_declaration_has_zero_callers(self):
        """死代码：零调用者（保留签名 = 无副作用失败 shim）。"""
        self.assertEqual(self._refs("_execute_war_declaration"), [])

    def test_auto_recruit_and_assign_zero_production_callers(self):
        """非经冻结层/自动层契约调用：零引用（唯一旧调用者已退役为 shim）。"""
        self.assertEqual(self._refs("auto_recruit_and_assign"), [])

    def test_auto_recruit_and_assign_absent_from_frozen_auto_contract(self):
        """可选写集合核对：自动层/冻结层契约源不得出现该 helper。"""
        from src.core.systems import political_system as pol_mod
        src = pathlib.Path(pol_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("auto_recruit_and_assign", src)


if __name__ == "__main__":
    unittest.main()
