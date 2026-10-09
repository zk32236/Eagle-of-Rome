# src/tests/test_api/test_wpgr12_rebellion_war_senate_venue.py
"""WP-G-R12 A1-venue（venue 修订层）生产链测试 —— 起义战争卡移出元老院提案列表。

冻结设计 = `WP-G-R12/02-sa-design/A1-venue/SA-Development-Task-WP-G-R12-A1-Venue.md`
（FC-R12-A1-01…08；§4 不阻塞证明 NP-1…4）；launch `6222a5a`；ODR-R12-01（Owner FROZEN）。

唯一生产变更 = `PoliticalSystem.build_war_card_views` 内、`authority_by_mode` 计算后
`if not card["authority_by_mode"]: continue`（venue 过滤；零 QML diff / 零 DTO 字段 /
零路由语义改）。今天该规则仅命中起义战（`allowed_modes=[]` ⇒ `authority_by_mode=={}`）。

本文件覆盖（AC 映射）：
- WGR12-A1-AC-01（venue 过滤）：起义卡**不在**元老院 `war_cards`；普通战卡**仍在**。
- WGR12-A1-AC-02（★不阻塞）：NP-1 起义-only 空批 → results → advance；NP-2 混合；
  NP-3 幂等 re-entry（`PACKAGE_ALREADY_SUBMITTED`，不阻塞推进）。
- WGR12-A1-AC-03（可见性 ODR-05）：facts 逐字不变 + 起义战在**战斗阶段**可见（NP-4）。
- WGR12-A1-AC-04（普通零回归 + submit fail-closed 不变）：普通战卡逐字不变；
  手构起义 command 经真实 `propose_many` 仍 fail-closed（`WAR_MODE_INVALID`/`WAR_NOT_PROPOSABLE`）。

纪律：DA 自持 fixture（`GameState.create_for_testing`）；真实入口（`create_rebellion_war` /
`register_rebellion_war` / `senate_api.get_senate_view` / `propose_many` / `resolve_senate` /
`advance_senate_phase` / `combat_api.get_combat_view`）；不 monkeypatch 被测生产者。
Evidence Class = DATA。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import (
    AUTHORITY_CONSUL_DIRECT,
    classify_war_authority,
)
from src.api import senate_api
from src.api import combat_api


# ---------------------------------------------------------------------------
# Fixture（DA 自持；最小生产配方 + senate 为当前相位）
# ---------------------------------------------------------------------------
def _build_base(config=None):
    """基线态：玩家/执政官 + 军团池；已执行 phases 至 population ⇒ senate 为当前相位。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    for phase in ("mortality", "revenue", "forum", "population"):
        state.mark_phase_executed(phase)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)   # 默认 25 UNRAISED 军团
    state._naval_system = NavalSystem(state)
    state.config.economic_rules.senate_war_legions = {
        "default": 4, "min": 1, "cap_mode": "available_pool",
    }

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    consul = Figure(id=1, name="执政官", faction_id="optimates", age=45)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 80
    state.add_member(consul)
    faction.member_ids.append(1)

    player = Player(player_id="player_opt", faction_id="optimates",
                    player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    return state, consul


def _add_rebellion(state, province_id=991, governor_id=None):
    """经真实入口 create_rebellion_war + register_rebellion_war 建 ACTIVE 起义战。"""
    ws = state.get_war_system()
    province = Province(province_id=province_id, name=f"Rebel Province {province_id}",
                        total_land=1000, conquered=True, governor_id=governor_id)
    state.add_province(province)
    war = ws.create_rebellion_war(province)
    ok = ws.register_rebellion_war(war)
    assert ok, "register_rebellion_war 前置失败"
    return war


def _add_active_war(state, war_id="w_normal", name="普通外战", commander_id=None):
    """普通外战（非起义）ACTIVE 战争。"""
    war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5,
              naval_required=False)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    state.get_war_system()._active_wars.append(war)
    return war


def _view(state, viewer="player_opt"):
    view = senate_api.get_senate_view(state, viewer)
    assert view["success"], view.get("message")
    return view["data"]


def _war_card_ids(data):
    return [c["war_id"] for c in data["war_cards"]]


# ---------------------------------------------------------------------------
# WGR12-A1-AC-01（venue 过滤）：起义卡不在 war_cards；普通战卡仍在
# ---------------------------------------------------------------------------
class TestWGR12A1VenueFilter(unittest.TestCase):
    def test_rebellion_card_not_in_senate_war_cards(self):
        """起义战（allowed_modes=[] ⇒ authority_by_mode={}）不入元老院提案列表。"""
        state, _consul = _build_base()
        reb = _add_rebellion(state, province_id=991)
        data = _view(state)
        self.assertNotIn(reb.id, _war_card_ids(data),
                         "起义卡不得出现在元老院 war_cards（venue 移出）")

    def test_ordinary_card_still_in_senate_war_cards(self):
        """普通外战（有合法 route）仍在 war_cards，route 字段逐字不变（零回归）。"""
        state, _consul = _build_base()
        _add_active_war(state, "w_normal", commander_id=None)
        data = _view(state)
        self.assertIn("w_normal", _war_card_ids(data))
        card = [c for c in data["war_cards"] if c["war_id"] == "w_normal"][0]
        self.assertEqual(card["classification"], "ongoing")
        self.assertEqual(card["allowed_modes"], ["command"])
        self.assertEqual(card["authority_by_mode"],
                         {"command": AUTHORITY_CONSUL_DIRECT})


# ---------------------------------------------------------------------------
# WGR12-A1-AC-04（普通零回归 + submit fail-closed 不变）
# ---------------------------------------------------------------------------
class TestWGR12A1ZeroRegressionAndFailClosed(unittest.TestCase):
    def test_manual_rebellion_command_submit_fail_closed_unchanged(self):
        """手构起义 checked command 经真实整包门 propose_many → 仍 fail-closed、零发布。

        B-B 不动 submit 面（不经 build_war_card_views）⇒ 拒绝码/语义逐字不变。
        """
        state, consul = _build_base()
        reb = _add_rebellion(state, province_id=995)
        result = senate_api.propose_many(state, "player_opt", [
            {"type": "war_proposal", "war_id": reb.id, "checked": True, "mode": "command",
             "target_commander_id": consul.id, "reinforcement_n": 0},
        ])
        self.assertFalse(result["success"], "手构起义 consul_direct command 必须被拒")
        codes = {e.get("code") for e in result.get("errors", [])}
        self.assertTrue(codes & {"WAR_MODE_INVALID", "WAR_NOT_PROPOSABLE"},
                        f"期望 WAR_MODE_INVALID/WAR_NOT_PROPOSABLE，实得 {codes}")
        self.assertEqual(state.get_senate_proposals(), [], "零提案发布")
        self.assertIsNone(reb.commander_id, "零早写：起义指挥官不变")


# ---------------------------------------------------------------------------
# WGR12-A1-AC-02（★不阻塞）：NP-1 / NP-2 / NP-3
# ---------------------------------------------------------------------------
class TestWGR12A1NonBlocking(unittest.TestCase):
    def test_np1_rebellion_only_empty_batch_completes_and_advances(self):
        """NP-1 起义-only：空批合法 → decision_complete → results → advance（无软锁）。"""
        state, _consul = _build_base()
        reb = _add_rebellion(state, province_id=991)

        data = _view(state)
        self.assertNotIn(reb.id, _war_card_ids(data))
        self.assertEqual(data["current_step"], "proposal")
        self.assertTrue(data["can_create_proposal"], "viewer_has_consul ⇒ 可提案")
        self.assertTrue(data["can_finish_empty"], "零提案合法路径保持")

        sub = senate_api.propose_many(state, "player_opt", [])
        self.assertTrue(sub["success"], sub.get("errors"))
        self.assertTrue(state.senate_proposal_decision_complete,
                        "空批提交置完成事实（与 war_cards 解耦）")

        view = _view(state)
        self.assertEqual(view["current_step"], "results")

        res = senate_api.resolve_senate(state)
        self.assertTrue(res["success"], res.get("message"))

        view2 = _view(state)
        self.assertEqual(view2["current_step"], "results")
        self.assertTrue(view2["can_advance"], "有真实 senate result ⇒ 可推进")

        adv = senate_api.advance_senate_phase(state, "player_opt")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertTrue(state.is_phase_executed("senate"))

    def test_np2_mixed_rebellion_and_ordinary_war(self):
        """NP-2 混合：起义战 + 普通 ongoing 战 → 起义卡不在、普通卡在且可提案；推进正常。"""
        state, consul = _build_base()
        reb = _add_rebellion(state, province_id=992)
        _add_active_war(state, "w_normal", commander_id=None)

        data = _view(state)
        ids = _war_card_ids(data)
        self.assertNotIn(reb.id, ids, "起义卡不在元老院提案列表")
        self.assertIn("w_normal", ids, "普通战卡仍在")
        ncard = [c for c in data["war_cards"] if c["war_id"] == "w_normal"][0]
        self.assertEqual(ncard["authority_by_mode"],
                         {"command": AUTHORITY_CONSUL_DIRECT})

        # 其它提案路径可达：提交含普通战 checked 的整包 → success → 结算/推进正常
        sub = senate_api.propose_many(state, "player_opt", [
            {"type": "war_proposal", "war_id": "w_normal", "checked": True, "mode": "command",
             "target_commander_id": consul.id, "reinforcement_n": 0},
        ])
        self.assertTrue(sub["success"], sub.get("errors"))
        res = senate_api.resolve_senate(state)
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(state, "player_opt")
        self.assertTrue(adv["success"], adv.get("message"))

    def test_np3_reentry_idempotent_not_blocking(self):
        """NP-3 幂等 re-entry：同会期二次提交 → PACKAGE_ALREADY_SUBMITTED（既有门），不阻塞推进。"""
        state, _consul = _build_base()
        reb = _add_rebellion(state, province_id=993)

        first = senate_api.propose_many(state, "player_opt", [])
        self.assertTrue(first["success"], first.get("errors"))

        second = senate_api.propose_many(state, "player_opt", [])
        self.assertFalse(second["success"], "同会期二次提交必须被既有门拒")
        codes = {e.get("code") for e in second.get("errors", [])}
        self.assertIn("PACKAGE_ALREADY_SUBMITTED", codes)

        # step 已 results ⇒ 可推进（非软锁）
        res = senate_api.resolve_senate(state)
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(state, "player_opt")
        self.assertTrue(adv["success"], adv.get("message"))
        # 幂等一致：起义卡恒不在元老院提案列表
        self.assertNotIn(reb.id, _war_card_ids(_view(state)))


# ---------------------------------------------------------------------------
# WGR12-A1-AC-03（可见性 ODR-05）：facts 逐字不变 + 战斗阶段可见（NP-4）
# ---------------------------------------------------------------------------
class TestWGR12A1Visibility(unittest.TestCase):
    def test_np4_rebellion_facts_unchanged_and_visible_in_combat(self):
        """NP-4：起义战 facts 逐字不变（真实 ACTIVE War）；元老院不可见但战斗阶段可见。"""
        state, _consul = _build_base()
        reb = _add_rebellion(state, province_id=994)

        facts = state.get_war_system().describe_senate_war(reb.id, {"current_turn": 1})
        self.assertIsNotNone(facts)
        self.assertTrue(facts["is_real_war"], "起义战仍为真实 ACTIVE War（可见）")
        self.assertEqual(facts["classification"], "ongoing")
        self.assertEqual(facts["allowed_modes"], [], "起义战 allowed_modes 必须为空")
        self.assertEqual(classify_war_authority(facts), {},
                         "起义战无任何合法 authority route（逐字不变）")

        # 元老院提案列表：不可见（venue 移出）
        self.assertNotIn(reb.id, _war_card_ids(_view(state)))

        # 战斗阶段：可见（CombatStage 消费 combat view active_wars；零 rebellion 特判）
        cview = combat_api.get_combat_view(state, "player_opt")
        self.assertTrue(cview["success"], cview.get("message"))
        combat_ids = [c["war_id"] for c in cview["data"]["active_wars"]]
        self.assertIn(reb.id, combat_ids, "起义战必须在战斗阶段可见（ODR-05）")


if __name__ == "__main__":
    unittest.main()
