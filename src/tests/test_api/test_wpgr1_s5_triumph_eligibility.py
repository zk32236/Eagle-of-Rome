# src/tests/test_api/test_wpgr1_s5_triumph_eligibility.py
"""WP-G-R1 S5（R1-G-07）— Triumph Eligibility 三层同源（dead Commander 三层一致拒绝）。

冻结设计：SA-Design-WP-G-R1 v1.6 §2.7 + §3 T-R1-10 + §7.2 SC-06 + §7.10.2-B。

覆盖（T-R1-10 / SC-06，public seam = get_forum_view / vote_triumph / resolve_forum）：
- 单一 `_triumph_eligibility` 谓词矩阵（RESOLVED/soldier_share/triumph_commander 存在/
  commander alive/dead/missing；VICTORY 与 TRIUMPH result 维度均 eligible）
- Layer 1 `_triumph_war_rows`（经 get_forum_view triumph_wars）：alive → 展示行；
  dead/missing → 无行
- Layer 2 `vote_triumph` 入口：alive → 接受并记录；dead/missing → 拒绝（零记录）
- Layer 3 `resolve_forum` settlement：alive + 支持票 → 凯旋批准（triumph_approved）；
  dead/missing → 凯旋失效归零（soldier_share==0），与 row/入口三层同源一致
- 状态迁移一致：alive 投票后 commander 阵亡再结算 → 结算层仍拒绝（凯旋失效）

证据形态：RESOLVED 态由真实 producer 构造（forced victory/triumph via
combat_api.do_combat_action → resolve_war 写 soldier_share>0 + triumph_commander_id，
SC-01 前置 seam）；三层一致断言（DATA，无视觉分支）。
"""
from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.war_system import WarSystem
from src.api import combat_api, forum_api

_WAR_REWARDS = {"treasury": 100, "land": 0, "family_prestige": 0}


def _resolved_war_state(force="victory", rewards=None):
    """SC-06 入口态（真实 producer）：ACTIVE land war → forced victory/triumph → RESOLVED。

    RESOLVED 战争带 soldier_share>0 + triumph_commander_id=101（resolve_war 胜利分支
    对 VICTORY/TRIUMPH 均写入——v1.6 §2.7 result 维度不变）。
    """
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
        rewards=dict(rewards or _WAR_REWARDS),
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


def _kill_commander(state, commander):
    """生产死亡原语（transfer=False 防 land/wealth 转移副作用干扰断言无关状态）。"""
    state.mark_member_dead(commander.id, transfer_land=False, transfer_wealth=False)
    assert commander.is_dead is True


def _remove_commander(state, commander):
    """missing：人物从 _members 彻底移除（存档/数据缺失形态）。"""
    del state._members[commander.id]


def _forum_rows(state):
    view = forum_api.get_forum_view(state, "player_opt")
    assert view["success"], view.get("message")
    return view["data"]["triumph_wars"]


def _vote_ok(state, war_id):
    return forum_api.vote_triumph(state, "player_opt", war_id, True)


# ---------------------------------------------------------------------------
# 1. 单一谓词矩阵（_triumph_eligibility；纯实现落点单测，验收 seam = 公开三层）
# ---------------------------------------------------------------------------

def test_eligibility_reason_matrix_victory_and_triumph():
    """VICTORY 与 TRIUMPH result 维度均 eligible；soldier_share/commander 态逐因映射。"""
    state, war, commander = _resolved_war_state(force="victory")
    elig = forum_api._triumph_eligibility(state, war)
    assert elig == {"eligible": True, "reason": None}

    # TRIUMPH result 维度同样 eligible（resolve_war 对二者同写 soldier_share）
    state2, war2, _c2 = _resolved_war_state(force="triumph")
    assert forum_api._triumph_eligibility(state2, war2)["eligible"] is True
    assert war2.soldier_share > 0 and war2.triumph_commander_id == 101

    # soldier_share=0 → no_soldier_share
    war.set_soldier_share(0)
    assert forum_api._triumph_eligibility(state, war)["reason"] == "no_soldier_share"
    war.set_soldier_share(10)

    # triumph_commander_id=None → no_triumph_commander
    war._triumph_commander_id = None
    assert forum_api._triumph_eligibility(state, war)["reason"] == "no_triumph_commander"
    war._triumph_commander_id = 101

    # commander missing → commander_missing（先 dead 后 missing 独立态）
    _remove_commander(state, commander)
    assert forum_api._triumph_eligibility(state, war)["reason"] == "commander_missing"


def test_eligibility_not_resolved_and_dead_reasons():
    """非 RESOLVED / commander dead 逐因映射。"""
    state, war, commander = _resolved_war_state(force="victory")
    # 非 RESOLVED（RESOLVED → ACTIVE 状态回退属异常态，直接谓词单测）
    war.status = WarStatus.ACTIVE
    assert forum_api._triumph_eligibility(state, war)["reason"] == "not_resolved"
    war.status = WarStatus.RESOLVED
    _kill_commander(state, commander)
    assert forum_api._triumph_eligibility(state, war)["reason"] == "commander_dead"


# ---------------------------------------------------------------------------
# 2. alive → 三层均接受（row 展示 + 入口接受 + 结算通过）
# ---------------------------------------------------------------------------

def test_alive_commander_three_layers_consistent():
    """alive：Forum rows 展示 + vote 入口接受记录 + settlement 凯旋批准（三层一致）。"""
    state, war, _commander = _resolved_war_state(force="victory")
    # Layer 1：row 展示
    rows = _forum_rows(state)
    assert [r["war_id"] for r in rows] == [war.id]
    assert rows[0]["commander_id"] == 101
    # Layer 2：vote 入口接受 + 记录
    resp = _vote_ok(state, war.id)
    assert resp["success"] is True
    pending = state.get_forum_pending()
    assert any(v[0] == war.id and v[2] is True for v in pending["triumph_votes"])
    # Layer 3：settlement 通过（支持率 1.0 > 0.5 → approved + soldier_share 归零）
    settled = forum_api.resolve_forum(state)
    assert settled["success"] is True
    results_text = " ".join(settled["data"]["results"])
    assert "凯旋仪式获得批准" in results_text
    assert war.triumph_approved is True
    assert war.soldier_share == 0


def test_victory_and_triumph_both_eligible_layers():
    """result 维度：forced TRIUMPH 与 forced VICTORY 均为 eligible（rows + 入口）。"""
    for force in ("victory", "triumph"):
        state, war, _ = _resolved_war_state(force=force)
        rows = _forum_rows(state)
        assert [r["war_id"] for r in rows] == [war.id], f"force={force}"
        resp = _vote_ok(state, war.id)
        assert resp["success"] is True, f"force={force}: {resp.get('message')}"


# ---------------------------------------------------------------------------
# 3. dead / missing → 三层一致拒绝（无 row + 入口拒绝 + 结算失效）
# ---------------------------------------------------------------------------

def test_dead_commander_three_layers_reject():
    """dead：无凯旋行 + vote 入口拒绝（零记录）+ settlement 凯旋失效归零。"""
    state, war, commander = _resolved_war_state(force="victory")
    _kill_commander(state, commander)

    # Layer 1：row 过滤（dead 不再展示）
    rows = _forum_rows(state)
    assert rows == []
    # Layer 2：vote 入口拒绝 + 零记录
    resp = _vote_ok(state, war.id)
    assert resp["success"] is False
    pending = state.get_forum_pending()
    assert all(v[0] != war.id for v in pending["triumph_votes"])
    # Layer 3：settlement 同源 → 凯旋失效（soldier_share 归零、无批准）
    settled = forum_api.resolve_forum(state)
    assert settled["success"] is True
    results_text = " ".join(settled["data"]["results"])
    assert "凯旋失效" in results_text
    assert war.soldier_share == 0
    assert war.triumph_approved is False


def test_missing_commander_three_layers_reject():
    """missing：同 dead——无 row + 入口拒绝 + 结算失效。"""
    state, war, commander = _resolved_war_state(force="victory")
    _remove_commander(state, commander)

    rows = _forum_rows(state)
    assert rows == []
    resp = _vote_ok(state, war.id)
    assert resp["success"] is False
    settled = forum_api.resolve_forum(state)
    results_text = " ".join(settled["data"]["results"])
    assert "凯旋失效" in results_text
    assert war.soldier_share == 0
    assert war.triumph_approved is False


def test_state_transition_vote_then_death_settlement_rejects():
    """状态迁移一致：alive 时投票记录后 commander 阵亡 → settlement 仍同源拒绝（凯旋失效）。

    三层语义：row/入口在 commander 死亡后即时失效（刷新/新投票拒绝）；结算在死亡后
    不接受已记录的赞成票（dead 检查先于投票计数——v1.6 §2.7 既有语义保留）。
    """
    state, war, commander = _resolved_war_state(force="victory")
    assert _vote_ok(state, war.id)["success"] is True   # alive 时入口接受
    _kill_commander(state, commander)
    # 死亡后刷新：row 消失
    assert _forum_rows(state) == []
    # 死亡后再投票：入口拒绝
    assert _vote_ok(state, war.id)["success"] is False
    # settlement：dead → 凯旋失效（已记录的赞成票不生效）
    settled = forum_api.resolve_forum(state)
    results_text = " ".join(settled["data"]["results"])
    assert "凯旋失效" in results_text
    assert war.soldier_share == 0
    assert war.triumph_approved is False


if __name__ == "__main__":
    import unittest

    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
