# src/tests/test_api/test_wpj_groupb_triumph_action.py
"""WP-J Group B-1 (J-AC-03 / BL-G7-08) — 凯旋行动作可用性单一权威投影 + viewer_vote。

DATA(PRODUCTION_CHAIN)：RESOLVED 态由真实 producer 构造
（combat_api.do_combat_action → resolve_war 写 soldier_share>0 + triumph_commander_id），
经公开 seam `forum_api.get_forum_view().triumph_wars[]` 断言 FC-B01/B02/B03/B18。

覆盖：
- action.state 边界态矩阵：market+current→actionable(ok)；retirement→vote_window_closed；
  非 forum 相位→not_phase；非当前玩家→not_current_player；resolved→resolved
- viewer_vote 投影：null → true（投票后）；多玩家隔离
- 写语义零改：vote_triumph bool + append 语义不变；resolve_forum 结算不变
- Store 只读透传（forumTriumphWars 携带 action/viewer_vote）
"""
import unittest

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.war_system import WarSystem
from src.api import combat_api, forum_api

_WAR_REWARDS = {"treasury": 100, "land": 0, "family_prestige": 0}


def _resolved_war_state(force="victory"):
    """真实生产链入口态：ACTIVE land war → forced victory/triumph → RESOLVED（同 WP-G-R1 S5）。"""
    state = GameState.create_for_testing({"testing": {"bypass_player_check": True}})
    state.turn = GameTurn(turn_number=8, year=-270)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(101)

    war = War(
        id="war1", name="Land War", strength=5, threat_level=3,
        rewards=dict(_WAR_REWARDS),
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)

    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num}"
    assigned, msg = ms.assign_to_war([1, 2], war.id, 101)
    assert assigned == 2, msg

    state.config.testing.force_battle_result = force
    result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
    assert result["success"], result.get("message")
    assert war.status == WarStatus.RESOLVED
    assert war.triumph_commander_id == 101
    assert war.soldier_share > 0
    return state, war, commander


def _enter_forum_phase(state):
    """推进到 forum 相位（mortality/revenue 已执行）。"""
    for phase in ("mortality", "revenue"):
        state.mark_phase_executed(phase)


def _open_market(state):
    """市场子环节开启标记（get_forum_view current_step == 'market' 的权威载体）。"""
    state.add_forum_action("market_opened", True)


def _rows(state, viewer="player_opt"):
    view = forum_api.get_forum_view(state, viewer)
    assert view["success"], view.get("message")
    return view["data"]["triumph_wars"]


class TestTriumphActionProjection(unittest.TestCase):
    def test_actionable_market_current_player(self):
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        rows = _rows(state)
        assert [r["war_id"] for r in rows] == [war.id]
        r = rows[0]
        self.assertEqual(r["action"], {"state": "actionable", "reason": "ok"})
        self.assertIsNone(r["viewer_vote"])

    def test_readonly_vote_window_closed_in_retirement(self):
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)  # 进入 forum，但市场未开启 → retirement 子环节
        r = _rows(state)[0]
        self.assertEqual(r["action"], {"state": "readonly", "reason": "vote_window_closed"})

    def test_readonly_not_phase_when_forum_not_current(self):
        state, _war, _c = _resolved_war_state()  # 未推任何相位 → 当前相位 mortality
        r = _rows(state)[0]
        self.assertEqual(r["action"], {"state": "readonly", "reason": "not_phase"})

    def test_readonly_not_current_player(self):
        state, _war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        other = Player(player_id="player_pop", faction_id="populares", player_type=PlayerType.HUMAN)
        state.add_player(other)
        state.config.testing.bypass_player_check = False
        state.set_current_player("player_pop")          # viewer 不再是当前玩家
        r = _rows(state, viewer="player_opt")[0]
        self.assertEqual(r["action"], {"state": "readonly", "reason": "not_current_player"})

    def test_readonly_resolved(self):
        state, _war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        state.mark_phase_executed("forum")              # 结算后
        r = _rows(state)[0]
        self.assertEqual(r["action"], {"state": "readonly", "reason": "resolved"})

    def test_viewer_vote_null_then_true_after_vote(self):
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        assert _rows(state)[0]["viewer_vote"] is None
        resp = forum_api.vote_triumph(state, "player_opt", war.id, True)
        assert resp["success"], resp.get("message")
        self.assertIs(_rows(state)[0]["viewer_vote"], True)

    def test_viewer_vote_isolated_per_faction(self):
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        other = Player(player_id="player_pop", faction_id="populares", player_type=PlayerType.HUMAN)
        state.add_player(other)
        # 他方派系投票（bypass_player_check 允许），不应泄漏给 senate viewer
        assert forum_api.vote_triumph(state, "player_pop", war.id, True)["success"]
        self.assertIsNone(_rows(state, viewer="player_opt")[0]["viewer_vote"])
        self.assertIs(_rows(state, viewer="player_pop")[0]["viewer_vote"], True)

    def test_vote_triumph_append_semantics_unchanged(self):
        """写语义零改：vote_triumph bool + append（同派系多次即多条记录）。"""
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        assert forum_api.vote_triumph(state, "player_opt", war.id, True)["success"]
        assert forum_api.vote_triumph(state, "player_opt", war.id, True)["success"]
        votes = state.get_forum_pending()["triumph_votes"]
        self.assertEqual([v for v in votes if v[0] == war.id], [(war.id, "senate", True), (war.id, "senate", True)])
        # viewer_vote = 最新一条（仍 True）
        self.assertIs(_rows(state)[0]["viewer_vote"], True)

    def test_store_passthrough_action_and_viewer_vote(self):
        """Store 只读透传：forumTriumphWars 逐行携带 action/viewer_vote（零本地业务缓存）。"""
        from src.ui.gui.session_store import GuiSessionStore
        state, war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        store = GuiSessionStore(state)
        store.initialize("player_opt")
        rows = store.forumTriumphWars
        assert [r["war_id"] for r in rows] == [str(war.id)]
        self.assertEqual(rows[0]["action"], {"state": "actionable", "reason": "ok"})
        self.assertIsNone(rows[0]["viewer_vote"])
        assert store.doVoteTriumph(war.id, True)["success"]
        rows2 = store.forumTriumphWars
        self.assertIs(rows2[0]["viewer_vote"], True)
        self.assertEqual(rows2[0]["action"], {"state": "actionable", "reason": "ok"})

    def test_action_reason_enum_frozen(self):
        """reason 词表冻结（FC-B02）：所有观测值 ∈ {ok, not_current_player, not_phase,
        vote_window_closed, resolved}。"""
        allowed = {"ok", "not_current_player", "not_phase", "vote_window_closed", "resolved"}
        state, _war, _c = _resolved_war_state()
        _enter_forum_phase(state)
        _open_market(state)
        for row in _rows(state):
            self.assertIn(row["action"]["reason"], allowed)
            self.assertIn(row["action"]["state"], ("actionable", "readonly"))


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
