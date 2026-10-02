# src/tests/test_api/test_wpgr11_ai_direct_action_parity.py
"""WP-G-R11 · R11-S1（AI Existing-War Direct-Action Producer Parity）生产链测试。

冻结设计：`WP-G-R11/02-sa-design/SA-Design-WP-G-R11-2026-10-02.md`
（内容 SHA256 dd1025894ad651ef6c9e7601204491ee96356343a2c1b1b0f3465cb083ee397b）。

本文件覆盖 R11-SC-01…05（SA §8 场景矩阵）：

- R11-SC-01（强制）灾难损失 → AI 恢复接管：**必须经真实 AI 构造入口**
  `senate_api.auto_submit_proposals()` → `propose_many` → `submit_proposal_package`
  → `advance_senate_phase`（唯一 Senate→Combat 原子边界）。
  **禁** monkeypatch `auto_submit_proposals` 本体 / 禁手改 route / 禁手搓 package 顶替。
- R11-SC-02（强制）AI 合法拒绝（`war_takeover_chance=0.0`）→ 无 direct decision。
- R11-SC-03 无可用军团池（池=0）→ N=0（遵循保留值域契约），仍绑定 Commander。
- R11-SC-04 现有指挥官 Continue/Reassign → 保留现任（无强制替换）。
- R11-SC-05（强制）Active Declaration 控制 → THREAT 仍走 Senate Vote，未被转为 Direct Action。

纪律：DA 自持 fixture（`GameState.create_for_testing`）；不 monkeypatch 被测生产者；
N 为随机值 → 测试 seed `random` + 断言合法性（N ∈ 值域 ∧ ΣN ≤ 池）。
"""
import os
import random
import sys
import unittest

from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import (
    AUTHORITY_CONSUL_DIRECT,
    AUTHORITY_SENATE_VOTE,
    classify_war_authority,
)
from src.api import senate_api


# ---------------------------------------------------------------------------
# Fixture（DA 自持；沿用既有 R1/Senate 生产配方的最小形态）
# ---------------------------------------------------------------------------
def _build_r11_state(config=None):
    """R11 生产链基线态：真实 War + 军团池（25 UNRAISED）+ 合法 Commander 候选。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)   # 默认 25 UNRAISED 军团
    state._naval_system = NavalSystem(state)

    # 权威宣战值域（4a 需要；与既有配方一致）
    state.config.economic_rules.senate_war_legions = {
        "default": 4, "min": 1, "cap_mode": "available_pool",
    }

    optimates = Faction(id="optimates", name="Optimates", treasury=50)
    populares = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(optimates)
    state.add_faction(populares)

    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    optimates.member_ids.append(1)

    exconsul = Figure(id=2, name="前执政官", faction_id="optimates", age=52)
    exconsul.office = "ex-consul"
    exconsul.class_tier = ClassTier.NOBILE
    exconsul.influence = 90
    state.add_member(exconsul)
    optimates.member_ids.append(2)

    tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    populares.member_ids.append(3)

    # 灾难阵亡的前任统帅（模型化 post-disaster：commander_id 指向死者）
    dead = Figure(id=9, name="阵亡统帅", faction_id="optimates", age=60)
    dead.class_tier = ClassTier.NOBILE
    dead.is_dead = True
    state.add_member(dead)
    optimates.member_ids.append(9)

    state._players = {
        "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
    }
    state._current_player_id = "player1"
    state._turn_order = ["player1", "player2"]
    return state


def _add_active_war(state, war_id="w1", name="第一次布匿战争", commander_id=None):
    war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    state.get_war_system()._active_wars.append(war)
    return war


def _add_threat_war(state, war_id="t1", name="皮洛士战争"):
    war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    return war


def _only_decision(state, session_id):
    decisions = state.get_consul_war_decisions(session_id)
    assert len(decisions) == 1, f"expected exactly 1 consul_direct decision, got {list(decisions)}"
    return list(decisions.values())[0]


class _R11ProducerParityBase(unittest.TestCase):
    """共享断言：真实 AI 生产链的零早写 / direct-only 发布 / 边界原子执行。"""

    def _submit_via_real_ai(self, state):
        """经真实 AI 构造入口（auto_submit_proposals）产出整包。"""
        return senate_api.auto_submit_proposals(state, land_proposal_deciders=[])

    def _assert_direct_not_vote(self, state, session_id, war_id):
        """R11-AC-03/07：checked command → FROZEN ConsulWarDecision（无 proposal_id，不进 Vote/Veto）。"""
        for proposal in state.get_senate_proposals():
            if isinstance(proposal, dict) and proposal.get("type") == "war_proposal":
                self.assertNotEqual(proposal.get("war_id"), war_id,
                                    "consul_direct 不得产出 Senate War proposal")
        item = (state.get_senate_war_items(session_id) or {}).get((session_id, war_id)) or {}
        self.assertEqual(item.get("authority"), AUTHORITY_CONSUL_DIRECT,
                         "war item 权威必须为 consul_direct")


# ---------------------------------------------------------------------------
# R11-SC-01（强制）灾难损失 → AI 恢复接管（真实 auto_submit_proposals 链）
# ---------------------------------------------------------------------------
class TestR11SC01PostDisasterAiTakeover(_R11ProducerParityBase):
    def test_sc01_post_disaster_ai_takeover_through_producer(self):
        random.seed(20261002)
        state = _build_r11_state({"combat_rules": {"war_takeover_chance": 1.0}})
        # 真实 ACTIVE 战；现任指挥官已阵亡（非现任）
        war = _add_active_war(state, commander_id=9)
        self.assertIsNone(state.get_war_system().get_live_current_commander_id(war),
                          "前置：旧指挥官非现任")

        # 真实 AI 构造入口
        result = self._submit_via_real_ai(state)
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()
        self.assertIsNotNone(session_id)

        # direct decision 存在（authority=consul_direct，无 proposal_id）
        decision = _only_decision(state, session_id)
        self.assertEqual(decision.get("authority"), AUTHORITY_CONSUL_DIRECT)
        self.assertEqual(decision.get("mode"), "command")
        self.assertEqual(decision.get("war_id"), war.id)
        self.assertIsNone(decision.get("proposal_id"))
        target = decision["payload"]["target_commander_id"]
        n = decision["payload"]["reinforcement_n"]
        self.assertIsNotNone(target, "替补 Commander 必须存在")
        self.assertTrue(state.get_member(target) is not None and not state.get_member(target).is_dead)

        # N 合法性：N ∈ 值域 ∧ ΣN ≤ 池
        pool = len(state.get_military_system().get_available_legions())
        self.assertGreaterEqual(n, 0)
        self.assertLessEqual(n, pool)
        if pool > 0:
            self.assertGreaterEqual(n, 1)

        # 不进 Vote/Veto + 零早写
        self._assert_direct_not_vote(state, session_id, war.id)
        self.assertEqual(war.commander_id, 9, "Submit 期不得改 War commander（零早写）")
        self.assertEqual(state.get_military_system().get_legions_for_battle(war.id), [],
                         "Submit 期零军团绑定")
        self.assertFalse(state.get_member(target).is_absent, "Submit 期指挥官不得外派")

        # 边界原子执行（唯一 Senate→Combat 入口）
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))

        # 边界后：War commander == target；指挥官外派；新绑定军团数 == N
        self.assertEqual(war.commander_id, target, "边界后 War Commander 必须为 decision target")
        self.assertTrue(state.get_member(target).is_absent, "边界后指挥官出征")
        bound = state.get_military_system().get_legions_for_battle(war.id)
        self.assertEqual(len(bound), n, "新绑定 Legion 数必须等于请求合法 N")

        # receipt exactly-once：direct_decision_refs 含本 direct decision
        receipt = state.get_war_execution_receipt_for_session(session_id)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.get("status"), "COMMITTED")
        ref_ids = [r.get("direct_decision_id") for r in receipt.get("direct_decision_refs", [])]
        self.assertIn(decision.get("direct_decision_id"), ref_ids)


# ---------------------------------------------------------------------------
# R11-SC-02（强制）AI 合法拒绝（war_takeover_chance=0.0）
# ---------------------------------------------------------------------------
class TestR11SC02AiLegalRefusal(_R11ProducerParityBase):
    def test_sc02_no_action_no_direct_decision(self):
        random.seed(20261002)
        state = _build_r11_state({"combat_rules": {"war_takeover_chance": 0.0}})
        war = _add_active_war(state, commander_id=9)

        result = self._submit_via_real_ai(state)
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()

        # NO ACTION → 无 direct decision / 无 fake proposal / 无强制 Commander / 无军团
        self.assertEqual(state.get_consul_war_decisions(session_id), {},
                         "chance=0.0 → 不得产出 consul_direct decision")
        self.assertEqual(state.get_war_system().get_live_current_commander_id(war), None)
        self.assertEqual(war.commander_id, 9)
        self.assertEqual(state.get_military_system().get_legions_for_battle(war.id), [])

        # Senate 仍可完成（R6 Q5：commanderless/legionless 合法）
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        # 无 direct → 边界不得新绑定 Commander（死者非现任，边界仅回退 F=None）
        self.assertIsNone(state.get_war_system().get_live_current_commander_id(war),
                          "无 direct → 边界后仍无有效现任（未强制换将）")
        self.assertEqual(state.get_military_system().get_legions_for_battle(war.id), [],
                         "无 direct → 边界零征召")
        self.assertTrue(state.is_phase_executed("senate"))


# ---------------------------------------------------------------------------
# R11-SC-03 无可用军团池（池=0）→ N=0（仍绑定 Commander）
# ---------------------------------------------------------------------------
class TestR11SC03ZeroPool(_R11ProducerParityBase):
    def test_sc03_zero_pool_n_zero_still_bind_commander(self):
        random.seed(20261002)
        state = _build_r11_state({"combat_rules": {"war_takeover_chance": 1.0}})
        ms = state.get_military_system()
        for number in range(1, 26):
            ok, _msg = ms.recruit_legion(number)
            self.assertTrue(ok, f"清池前置失败: {number}")
        self.assertEqual(len(ms.get_available_legions()), 0, "前置：池=0")

        war = _add_active_war(state, commander_id=9)
        result = self._submit_via_real_ai(state)
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()

        decision = _only_decision(state, session_id)
        n = decision["payload"]["reinforcement_n"]
        self.assertEqual(n, 0, "池=0 → N=0（保留值域契约）")
        target = decision["payload"]["target_commander_id"]
        self.assertIsNotNone(target)

        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))

        # 零池：仍绑定 Commander；零幻影征召；无池溢出
        self.assertEqual(war.commander_id, target)
        self.assertEqual(ms.get_legions_for_battle(war.id), [], "池=0 → 零征召")


# ---------------------------------------------------------------------------
# R11-SC-04 现有指挥官 Continue/Reassign → 保留现任（无强制替换）
# ---------------------------------------------------------------------------
class TestR11SC04ContinueExistingCommander(_R11ProducerParityBase):
    def test_sc04_continue_existing_valid_commander(self):
        random.seed(20261002)
        state = _build_r11_state({"combat_rules": {"war_takeover_chance": 1.0}})
        war = _add_active_war(state, commander_id=2)  # 有效现任（前执政官 id=2，存活）

        result = self._submit_via_real_ai(state)
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()

        decision = _only_decision(state, session_id)
        target = decision["payload"]["target_commander_id"]
        self.assertEqual(target, 2, "有效现任存在 → Continue 保留现任（无强制替换）")

        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, "player1")
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(war.commander_id, 2, "边界后保留现任")


# ---------------------------------------------------------------------------
# R11-SC-05（强制）Active Declaration 控制 → THREAT 仍走 Senate Vote
# ---------------------------------------------------------------------------
class TestR11SC05DeclarationControl(_R11ProducerParityBase):
    def test_sc05_threat_still_senate_vote_not_direct(self):
        random.seed(20261002)
        state = _build_r11_state({
            "combat_rules": {"war_takeover_chance": 1.0},
            "testing": {"always_declare": True, "propose_war_chance": 1.0},
        })
        threat = _add_threat_war(state)

        # 控制声明：THREAT → active_declaration → command == senate_vote
        facts = state.get_war_system().describe_senate_war(threat.id, {"current_turn": 1})
        self.assertEqual(classify_war_authority(facts).get("command"), AUTHORITY_SENATE_VOTE)

        result = self._submit_via_real_ai(state)
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()

        # THREAT 仍为普通 Senate proposal（war_proposal / senate_vote），未被转为 Direct Action
        war_props = [p for p in state.get_senate_proposals()
                     if isinstance(p, dict) and p.get("type") == "war_proposal"
                     and p.get("war_id") == threat.id]
        self.assertEqual(len(war_props), 1, "THREAT 必须走 Senate Vote proposal")
        self.assertEqual(state.get_consul_war_decisions(session_id), {},
                         "新 AI loop 不得把 THREAT 转为 Direct Action")
        item = (state.get_senate_war_items(session_id) or {}).get((session_id, threat.id)) or {}
        self.assertEqual(item.get("authority"), AUTHORITY_SENATE_VOTE)


if __name__ == "__main__":
    unittest.main()
