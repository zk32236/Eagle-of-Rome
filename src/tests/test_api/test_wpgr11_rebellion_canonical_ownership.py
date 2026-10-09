# src/tests/test_api/test_wpgr11_rebellion_canonical_ownership.py
"""WP-G-R11 · R11-S1-A2（Rebellion War Canonical Ownership）生产链测试。

冻结设计：`WP-G-R11/02-sa-design/SA-Design-Amendment-A2-WP-G-R11-2026-10-02.md`
（内容 SHA256 ff70d1168c2d4ab8a101e18d5a4df95d3789a7077e1a82bf5c728bedf31cc8a7）；
母设计 `dd102589…` + Addendum A1 `0b1b9312…`；ODR-G-R11-05（Owner FROZEN）。

本文件覆盖 R11-RBL-01…05（A2 §9.2 / 顾问 §8）：

- R11-RBL-01（DATA）起义作为真实 ACTIVE War **可见**（`is_real_war` / classification==
  "ongoing" / `allowed_modes==[]`），但**无普通 command route**（`classify_war_authority=={}`）。
  唯一 owner = describe_senate_war。
  **WP-G-R12 A1-venue Test Amendment（ODR-R12-01，2026-10-09）：** 原 DTO 级「卡在
  war_cards」断言被 re-supersede——起义卡**不再**出现在元老院提案列表（venue 移出）；
  可见性改由战斗阶段/广场承担（FC-R12-A1-06）。facts 级断言（
  `is_real_war`/`ongoing`/`allowed_modes==[]`/`classify_war_authority=={}`）保留。
- R11-RBL-02（PRODUCTION_CHAIN）手构起义 `consul_direct command` 经**真实整包门**
  `submit_proposal_package`（经 `propose_many`）→ fail-closed（WAR_MODE_INVALID）、整包
  FAIL、零发布。禁直调私有函数替代。
- R11-RBL-03（PRODUCTION_CHAIN）真 `auto_submit_proposals()` → 起义**不产** direct decision；
  `AutoWarTakeoverDecider` 起义守卫仍有效（defense-in-depth）。
- R11-RBL-04（PRODUCTION_CHAIN）commanderless 起义 + governor 候选 + 残余池 → 边界 retained
  `rebellion_assign` **仍成功**（专属机制唯一 owner，语义不变）。
- R11-RBL-05（AFFECTED REGRESSION）普通外战 ongoing → R11 direct-action producer **不变**。

纪律：DA 自持 fixture（`GameState.create_for_testing`）；不 monkeypatch 被测生产者；
R11-RBL-02/03 必走真实入口；禁构造期 mutation。
"""
import os
import random
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
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.api import senate_api


class _PassDecider:
    def decide_vote(self, issue, faction, state):
        return True


# ---------------------------------------------------------------------------
# Fixture（DA 自持；最小生产配方）
# ---------------------------------------------------------------------------
def _build_base(config=None):
    """R11-A2 基线态：真实玩家/执政官 + 军团池（25 UNRAISED）。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
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


def _add_governor(state, figure_id=4, name="起义总督"):
    """在城非死总督候选（专属起义机制 owner 对象）。"""
    gov = Figure(id=figure_id, name=name, faction_id="optimates", age=50)
    gov.office = "proconsul"
    gov.class_tier = ClassTier.NOBILE
    gov.influence = 40
    state.add_member(gov)
    state.get_faction("optimates").member_ids.append(figure_id)
    return gov


def _add_rebellion(state, province_id=991, governor_id=None, governor_designate_id=None):
    """经真实入口 create_rebellion_war + register_rebellion_war 建 ACTIVE 起义战。"""
    ws = state.get_war_system()
    province = Province(province_id=province_id, name=f"Rebel Province {province_id}",
                        total_land=1000, conquered=True,
                        governor_id=governor_id,
                        governor_designate_id=governor_designate_id)
    state.add_province(province)
    war = ws.create_rebellion_war(province)
    ok = ws.register_rebellion_war(war)
    assert ok, "register_rebellion_war 前置失败"
    return war


def _add_active_war(state, war_id="w1", name="普通外战", commander_id=None):
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


def _card(state, war_id, viewer="player_opt"):
    data = _view(state, viewer)
    for card in data["war_cards"]:
        if card["war_id"] == war_id:
            return card
    raise AssertionError(f"card missing for {war_id}: "
                         f"{[c['war_id'] for c in data['war_cards']]}")


# ---------------------------------------------------------------------------
# R11-RBL-01（DATA）起义可见但无普通 command route
# WP-G-R12 A1-venue re-supersede：起义卡由「在 war_cards」改为「不在 war_cards」
# （venue 移出）；可见性位点改由战斗阶段/广场承担（ODR-R12-01 / FC-R12-A1-06）。
# ---------------------------------------------------------------------------
class TestR11RBL01RebellionVisibleNoRoute(unittest.TestCase):
    def test_rebellion_card_visible_but_no_command_route(self):
        state, _consul = _build_base()
        reb = _add_rebellion(state, province_id=991)

        # canonical facts：可见（is_real_war=True / ongoing）但非 command 能力
        facts = state.get_war_system().describe_senate_war(reb.id, {"current_turn": 1})
        self.assertIsNotNone(facts)
        self.assertTrue(facts["is_real_war"], "起义战必须仍为真实 ACTIVE War（可见）")
        self.assertEqual(facts["classification"], "ongoing")
        self.assertEqual(facts["allowed_modes"], [], "起义战 allowed_modes 必须为空")
        # route producer（不改）派生：能力面 ∩ 表 = 空
        self.assertEqual(classify_war_authority(facts), {},
                         "起义战无任何合法 authority route")

        # WP-G-R12 A1-venue Test Amendment（ODR-R12-01）：Human GUI 真实视图——起义卡
        # **不再**出现在元老院提案列表（war_cards）。原 DTO 级断言
        # `card = _card(state, reb.id)` +（is_real_war/ongoing/allowed_modes==[]/
        # authority_by_mode=={}）即 venue 移出前的死卡面，已由「不在 war_cards」取代；
        # 可见性改由战斗阶段（CombatStage）/ 广场（Forum 起义警示）承担（FC-R12-A1-06）。
        # facts 级三断言（上方）保留，无 route 语义不变。
        data = _view(state)
        war_ids = [c["war_id"] for c in data["war_cards"]]
        self.assertNotIn(reb.id, war_ids,
                         "起义卡不得出现在元老院提案列表（venue 移出）")


# ---------------------------------------------------------------------------
# R11-RBL-02（PRODUCTION_CHAIN）手构 submit → fail-closed 整包 FAIL 零发布
# ---------------------------------------------------------------------------
class TestR11RBL02ManualSubmitFailClosed(unittest.TestCase):
    def test_manual_rebellion_command_submit_fail_closed_zero_publish(self):
        state, consul = _build_base()
        reb = _add_rebellion(state, province_id=992)
        ms = state.get_military_system()
        pool_before = len(ms.get_available_legions())
        wars_before = sorted(w.id for w in state.get_war_system().get_active_wars())

        # 真实整包门（propose_many → submit_proposal_package），服务端重取 route
        result = senate_api.propose_many(state, "player_opt", [
            {"type": "war_proposal", "war_id": reb.id, "checked": True, "mode": "command",
             "target_commander_id": consul.id, "reinforcement_n": 0},
        ])
        self.assertFalse(result["success"], "手构起义 consul_direct command 必须被拒")
        codes = {e.get("code") for e in result.get("errors", [])}
        self.assertTrue(codes & {"WAR_MODE_INVALID", "WAR_NOT_PROPOSABLE"},
                        f"期望 WAR_MODE_INVALID/WAR_NOT_PROPOSABLE，实得 {codes}")

        # 整包 FAIL → 零发布 / 零军事写（原子性）
        self.assertEqual(state.get_senate_proposals(), [], "零提案发布")
        self.assertEqual(state.get_consul_war_decisions("turn-1"), {}, "零 direct decision")
        self.assertIsNone(state.get_senate_package_id_for_session("turn-1"), "零包注册")
        self.assertIsNone(reb.commander_id, "零早写：起义指挥官不变")
        self.assertEqual(len(ms.get_available_legions()), pool_before, "零军团消耗")
        self.assertEqual(sorted(w.id for w in state.get_war_system().get_active_wars()),
                         wars_before)


# ---------------------------------------------------------------------------
# R11-RBL-03（PRODUCTION_CHAIN）真 auto_submit_proposals 不产起义 decision
# ---------------------------------------------------------------------------
class TestR11RBL03AiProducerNoRebellion(unittest.TestCase):
    def test_real_ai_producer_no_rebellion_direct_decision(self):
        random.seed(20261002)
        state, consul = _build_base({"combat_rules": {"war_takeover_chance": 1.0}})
        reb = _add_rebellion(state, province_id=993)
        normal = _add_active_war(state, "w_normal", name="普通外战")

        result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()
        self.assertIsNotNone(session_id)

        decisions = state.get_consul_war_decisions(session_id)
        war_ids = {d.get("war_id") for d in decisions.values()}
        self.assertNotIn(reb.id, war_ids, "AI 不得对起义战产 direct decision")
        # 正控：普通外战仍被 producer 处理（族未失效）
        self.assertIn(normal.id, war_ids, "普通外战 producer 应仍工作")

        # defense-in-depth：decider 起义守卫保留（返回 False）
        self.assertFalse(AutoWarTakeoverDecider().decide_takeover(reb, consul, None, state))


# ---------------------------------------------------------------------------
# R11-RBL-04（PRODUCTION_CHAIN）专属机制保持：commanderless 起义 retained assign
# ---------------------------------------------------------------------------
class TestR11RBL04DedicatedMechanismPreserved(unittest.TestCase):
    def test_commanderless_rebellion_retained_assign_succeeds(self):
        state, _consul = _build_base()
        _add_governor(state, figure_id=4)
        reb = _add_rebellion(state, province_id=994, governor_id=4)
        ms = state.get_military_system()

        sub = senate_api.propose_many(state, "player_opt", [])
        self.assertTrue(sub["success"], sub.get("errors"))
        res = senate_api.resolve_senate(state, vote_decider=_PassDecider())
        self.assertTrue(res["success"], res.get("message"))
        adv = senate_api.advance_senate_phase(state, "player_opt")
        self.assertTrue(adv["success"], adv.get("message"))

        receipt = state.get_war_execution_receipt(adv["data"]["execution_id"])
        self.assertIsNotNone(receipt)
        es = receipt["effect_summary"]
        # 专属 intent 登记 + apply 成功（唯一 normal owner 语义不变）
        self.assertEqual([i["kind"] for i in es["retained_effect_intents"]],
                         ["rebellion_assign"])
        self.assertEqual(es["retained_effects_deferred"], [])
        self.assertEqual(len(es["retained_effects"]), 1)
        applied = es["retained_effects"][0]
        self.assertEqual(applied["war_id"], reb.id)
        self.assertEqual(applied["commander_id"], 4)
        # 边界后：起义指挥官 = governor 候选；新绑定军团数 == min(起义征召量, 残余)
        self.assertEqual(reb.commander_id, 4)
        expected = min((state.config.get("combat_rules.rebellion_strength", 5) + 1) // 2,
                       len(ms.get_available_legions()) + len(applied["legion_numbers"]))
        self.assertEqual(len(ms.get_legions_for_battle(reb.id)),
                         len(applied["legion_numbers"]))
        self.assertGreaterEqual(len(applied["legion_numbers"]), 1)
        self.assertLessEqual(len(applied["legion_numbers"]), expected)
        # 起义战仍无普通 route（专属机制拥有；A2 未破坏）
        facts = state.get_war_system().describe_senate_war(reb.id, {"current_turn": 1})
        self.assertEqual(classify_war_authority(facts), {})


# ---------------------------------------------------------------------------
# R11-RBL-05（AFFECTED REGRESSION）普通外战 ongoing → R11 producer 不变
# ---------------------------------------------------------------------------
class TestR11RBL05OrdinaryOngoingUnchanged(unittest.TestCase):
    def test_ordinary_ongoing_war_route_and_producer_unchanged(self):
        random.seed(20261002)
        state, _consul = _build_base({"combat_rules": {"war_takeover_chance": 1.0}})
        normal = _add_active_war(state, "w_normal", name="普通外战")

        # 卡 route 逐字不变（普通外战不受 A2 影响）
        card = _card(state, "w_normal")
        self.assertEqual(card["classification"], "ongoing")
        self.assertEqual(card["allowed_modes"], ["command"])
        self.assertEqual(card["authority_by_mode"], {"command": AUTHORITY_CONSUL_DIRECT})

        # R11 direct-action producer 仍工作
        result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        decisions = list(state.get_consul_war_decisions(state.get_senate_session()).values())
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["war_id"], normal.id)
        self.assertEqual(decisions[0]["authority"], AUTHORITY_CONSUL_DIRECT)
        self.assertEqual(decisions[0]["mode"], "command")


if __name__ == "__main__":
    unittest.main()
