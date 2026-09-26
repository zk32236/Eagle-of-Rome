# src/tests/test_integration/test_wpgr9_terminal_next_senate.py
"""WP-G-R9 DA（SA-Design v1.1 §6；FC-R9-01/02/05/10）— 终结 War 跨回合生产链（T04，AC-R9-01/04）。

**真实 production advance**（不手写 turn/phase、不 inject RESOLVED/DTO）：Turn N Senate 提交
合法 command → 边界 `COMMITTED` → 真实 `combat_api.do_combat_action` 终结（triumph / victory
两独立 run）→ resolution → `game_api.advance_year` → mortality/revenue/forum/population 正常
推进 → **Turn N+1 Senate（尚未首次 submit）**。

状态 front-load 只用既有 builder 声明「已到合法 Senate 入口」外生前置（mortality~population
executed）＋ 真实 War/Figure 实体；N→N+1 的年度推进**全部**由真实 API producer 完成（不手写
turn/phase、不 inject 结果）。target = ACTIVE 陆战（本年真实终结）；positive control =
ACTIVE `naval_required` 且**零 ready 舰队**的战争（readiness 门 ⇒ 不阻塞 combat advance，
跨年仍在 `war_cards`）。

断言 NEXT_SENATE：target 在 `war_cards` 与 `consul_direct_decisions` **两源均无**；合法正对照
仍在 `war_cards`；refresh / 离开重入（新 Store）稳定。

本片 = integration（DATA source）；真实截图（RENDER_AUTOMATED）归 fresh G5 / Owner（设计 §6.1）。
"""
import unittest

from src.api import (senate_api, combat_api, resolution_api, game_api,
                     forum_api, population_api, session_api,
                     mortality_api, revenue_api)
from src.core.entities.war import WarStatus
from src.tests.fixtures.wpgr5_fixtures import (FIXED, command_draft, make_base_state,
                                              add_faction, add_player, add_consul,
                                              add_figure, make_war, attach_active)
from src.tests.fixtures.wpgr6_fixtures import submit_api
from src.ui.gui.session_store import GuiSessionStore

TARGET_WAR = "r9_target_war"
CONTROL_WAR = "r9_control_war"
P1 = FIXED["player"]


class _PassDecider:
    """所有议题通过（direct-only 包无真提案；确定性 approve 防 AI 分支漂移）。"""

    def decide_vote(self, issue, faction, state):
        return True


def _build_state():
    """Turn N 合法 Senate 入口：target（ACTIVE 陆战，本年终结）+ control（ACTIVE naval，
    零 ready 舰队 ⇒ readiness 门不阻塞）＋ 真实 Consul/Commander 实体。"""
    state = make_base_state(turn_number=1, year=-264)
    faction = add_faction(state, treasury=500)
    add_player(state)
    add_consul(state, faction, figure_id=1, name="Consul Aemilius")
    cmd_a = add_figure(state, faction, 2, "Commander A", office="ex-consul")
    add_figure(state, faction, 3, "Commander B", office="ex-praetor")
    target = make_war(TARGET_WAR, "R9 Target War", status=WarStatus.ACTIVE,
                      naval_required=False, enemy_land=6, commander_id=cmd_a.id)
    attach_active(state, target)
    control = make_war(CONTROL_WAR, "R9 Control War", status=WarStatus.ACTIVE,
                       naval_required=True, enemy_naval=20, commander_id=3)
    attach_active(state, control)
    return state, target, control


def _view(state, player_id=P1):
    result = senate_api.get_senate_view(state, player_id)
    assert result["success"], result.get("message")
    return result["data"]


def _card_war_ids(state):
    return {c["war_id"] for c in _view(state)["war_cards"]}


def _population_round(state, player_id):
    """真实人口链：begin → get_candidates → human ABSTAIN×5 → resolve → advance。"""
    population_api.begin_population_phase(state)
    cand = population_api.get_candidates(state)
    assert cand["success"], cand.get("message")
    entries = [{"office": office, "figure_id": 0}
               for office in ["consul", "censor", "praetor", "quaestor", "tribune"]]
    vote = population_api.batch_vote(state, player_id, entries, bypass_permission=True)
    assert vote["success"], f"batch_vote failed: {vote.get('message')} {vote.get('errors')}"
    resolved = session_api.resolve_population_slice(state)
    assert resolved["success"], f"resolve_population_slice failed: {resolved.get('message')}"
    advance = session_api.advance_population_phase(state, player_id)
    assert advance["success"], f"advance_population_phase failed: {advance.get('message')}"


def _drive_terminal_year(state, target_war_id, terminal, player_id=P1):
    """驱动一个真实终结年界：Senate → Combat(终结) → Resolution → advance_year →
    Mortality → Revenue → Forum → Population → Turn N+1 Senate。返回 N+1 turn_number。"""
    state.config.testing.force_battle_result = terminal
    state.set_current_player(player_id)

    # —— Turn N Senate：真实整包 Submit（合法 command → 冻结 ConsulDirect）——
    publish = submit_api(state, [command_draft(target_war_id, FIXED["cmd_a"], 1)])
    assert publish["success"], publish
    # 同会期 Results 冻结 direct 行可见（N Results 保留）
    assert len(_view(state)["consul_direct_decisions"]) == 1
    resolved = senate_api.resolve_senate(state, vote_decider=_PassDecider())
    assert resolved["success"], resolved.get("message")
    advance = senate_api.advance_senate_phase(state, player_id)
    assert advance["success"], advance.get("message")
    receipt = state.get_war_execution_receipt_for_session(state.get_senate_session())
    assert receipt and receipt["status"] == "COMMITTED", receipt

    # —— Combat：真实 attack 终结 target（其余 naval-not-ready 战争不阻塞）——
    action = combat_api.do_combat_action(state, player_id, target_war_id, "attack")
    assert action["success"], action.get("message")
    assert combat_api.confirm_battle_result(state, player_id)["success"]
    assert combat_api.advance_combat(state, player_id)["success"]

    # —— Resolution → 真实年度推进 ——
    assert resolution_api.execute_resolution(state)["success"]
    year_adv = game_api.advance_year(state, player_id)
    assert year_adv["success"], year_adv.get("message")

    # —— Mortality / Revenue / Forum / Population（正常执行与 advance）——
    assert mortality_api.execute_mortality_phase(state, player_id)["success"]
    assert mortality_api.advance_mortality_phase(state, player_id)["success"]
    assert revenue_api.execute_revenue_phase(state, player_id)["success"]
    assert revenue_api.advance_revenue_phase(state, player_id)["success"]
    assert forum_api.resolve_forum(state)["success"]
    assert forum_api.advance_forum_phase(state, player_id)["success"]
    _population_round(state, player_id)
    return state.turn.turn_number


class TestR9TerminalNextSenate(unittest.TestCase):
    """triumph / victory 两独立 run：终结 War 在 Turn N+1 两源均不在。"""

    def _run(self, terminal):
        state, target, control = _build_state()
        n0 = state.turn.turn_number
        n1 = _drive_terminal_year(state, target.id, terminal)
        self.assertEqual(n1, n0 + 1, "年度推进必须真实 +1（非手写）")
        self.assertEqual(target.status, WarStatus.RESOLVED)
        return state, target.id, control.id

    def _assert_next_senate(self, state, target_war_id, control_war_id):
        view = _view(state)
        card_wars = {c["war_id"] for c in view["war_cards"]}
        self.assertNotIn(target_war_id, card_wars,
                         "Turn N+1 可操作 war_cards 不得含已终结 target")
        self.assertIn(control_war_id, card_wars, "合法正对照仍在 war_cards")
        self.assertEqual(view["consul_direct_decisions"], [],
                         "Turn N+1 顶层 direct 投影须排除旧会期（N Results 冻结行）")
        # RED 判别 + FC-R9-06：旧会期 ledger/底账仍保留（未删）——仅顶层 scope 排除
        self.assertEqual(len(senate_api._consul_direct_decision_rows(state)), 1,
                         "旧会期 direct ledger 保留（未被删除）；排除仅由顶层 scope 造成")
        self.assertEqual(view["current_step"], "proposal", "N+1 尚未首次 submit")

    def test_t04_triumph_terminal_absent_next_senate(self):
        state, target_id, control_id = self._run("triumph")
        self._assert_next_senate(state, target_id, control_id)

    def test_t04_victory_terminal_absent_next_senate(self):
        state, target_id, control_id = self._run("victory")
        self._assert_next_senate(state, target_id, control_id)

    def test_t04_reentry_and_refresh_stable(self):
        """refresh / 离开重入（新 Store）后 target 不复现；合法正对照可达。"""
        state, target_id, control_id = self._run("triumph")
        first = _view(state)["consul_direct_decisions"]
        again = _view(state)["consul_direct_decisions"]        # repeated GET
        self.assertEqual(first, again)
        store = GuiSessionStore(state)
        store.initialize(P1)
        self.assertEqual(list(store.senateConsulDirectDecisions), [])
        card_war_ids = {c["war_id"] for c in store.senateWarCards}
        self.assertIn(control_id, card_war_ids)
        self.assertNotIn(target_id, card_war_ids)


if __name__ == "__main__":
    unittest.main()
