# src/tests/test_api/test_wpgr11_g7r_store_finalization.py
"""WP-G-R11 · R11-S1-G7R（AI Direct-Only GUI Finalization Soft-Lock 窄修正）生产链测试。

冻结契约：`WP-G-R11/02-sa-design/SA-Design-G7R-Correction-WP-G-R11-2026-10-02.md`
（内容 SHA256 97e54d0a84013d4b8661c13d96ab612791fa2ef93ba0e91e090c14f5ecd32a0a）。

覆盖：

- R11-G7R-01（强制 · PRODUCTION-SHAPE）AI direct-only → 真实
  `GuiSessionStore.doSubmitSenateProposals` 链 → 单一 canonical 谓词（`data["created"] == []`）
  → Store 自动 finalization（**唯一 Transition Owner**：`_auto_finalize_after_submit`
  → `adapter.resolve_senate` → `finalize_senate_if_ready`）→ results finalized +
  `can_advance=True` → 真实 `store.doAdvanceSenate()` → Senate→Combat 边界 COMMITTED。
  **禁**手接 `senate_api.resolve_senate` / `finalize_senate_if_ready`（Manual bridge FORBIDDEN）。
- R11-G7R-02（控制）AI 真提案包 → `data["created"] != []` → **不**在 submit 期早 finalize
  （保留 Vote/Veto 生命周期）。

纪律：真实 Store 链（禁 mock transition owner / 禁手改 route）；fixture =
`GameState.create_for_testing` 配方（DIRECT_PRODUCTION，零 monkeypatch 被测生产者）；
N 为随机值 → seed `random` + 断言合法性（N ∈ 值域 ∧ ΣN ≤ 池）。
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
from src.core.systems.political_system import AUTHORITY_CONSUL_DIRECT
from src.api import senate_api
from src.ui.gui.session_store import GuiSessionStore


# ---------------------------------------------------------------------------
# Fixture（DA 自持；沿用 R11-SC 生产配方的最小形态）
# ---------------------------------------------------------------------------
def _build_g7r_state(config=None):
    """R11-G7R 生产链基线态：真实 ACTIVE War + 军团池（25 UNRAISED）+ 合法 Commander 候选。

    当前玩家 = viewer = player2（非执政官派系：populares 无 consul）→
    `GuiSessionStore.doSubmitSenateProposals` 走 AI proposer 路由。
    """
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    # senate 为当前可行动阶段（前四阶段已执行）
    for phase in ["mortality", "revenue", "forum", "population"]:
        state.mark_phase_executed(phase)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)   # 默认 25 UNRAISED 军团
    state._naval_system = NavalSystem(state)

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
    # viewer = current player = player2（非执政官派系）→ AI proposer 路由
    state._current_player_id = "player2"
    state._turn_order = ["player2", "player1"]
    return state


def _disable_ai_other_sources(state):
    """关闭全部其它 AI 提案源（保证 direct-only / 空包的确定性）。"""
    state.config.testing.propose_war_chance = 0.0
    state.config.testing.always_declare = False
    state.config.political_rules.land_proposal.sale_chance = 0.0
    state.config.political_rules.land_proposal.distribution_chance = 0.0


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


# ---------------------------------------------------------------------------
# R11-G7R-01（强制 · PRODUCTION-SHAPE）AI direct-only 软锁闭合
# ---------------------------------------------------------------------------
class TestR11G7R01AiDirectOnlySoftLockClosure(unittest.TestCase):
    def test_g7r01_ai_direct_only_through_real_store_chain(self):
        """真实 GuiSessionStore.doSubmitSenateProposals 链 → canonical 谓词 → 唯一 Transition
        Owner（_auto_finalize_after_submit）→ results finalized + can_advance → 真实
        doAdvanceSenate → 边界 COMMITTED。**禁**手接 resolve_senate / finalize_senate_if_ready。
        """
        random.seed(20261002)
        state = _build_g7r_state({"combat_rules": {"war_takeover_chance": 1.0}})
        _disable_ai_other_sources(state)
        war = _add_active_war(state, commander_id=9)
        self.assertIsNone(state.get_war_system().get_live_current_commander_id(war),
                          "前置：旧指挥官（id=9 已阵亡）非现任")

        store = GuiSessionStore(state)
        store.initialize("player2")
        # 前置：非执政官派系 → AI proposer 路由（viewer 不控制元老院提案权）
        self.assertTrue(store.canTriggerAIProposer, "非执政官派系必须暴露 AI proposer 入口")
        self.assertFalse(store.canCreateSenateProposal)

        feedback = store.doSubmitSenateProposals([])
        self.assertTrue(feedback.get("success"), feedback.get("message"))
        data = feedback.get("data") or {}
        session_id = state.get_senate_session()
        self.assertIsNotNone(session_id)

        # 缺陷前提：canonical 真提案 refs == 0，而 AI 展示/动作摘要允许非空
        self.assertEqual(data.get("created"), [],
                         "canonical 真元老院提案 refs 必须为 0（direct-only）")
        self.assertTrue(data.get("proposals"),
                        "AI 展示/动作摘要非空（复现旧谓词 `created or proposals` 缺陷前提）")

        # direct decision 存在（authority=consul_direct；不进 Vote/Veto）
        decisions = state.get_consul_war_decisions(session_id)
        self.assertEqual(len(decisions), 1,
                         f"expected exactly 1 consul_direct decision, got {list(decisions)}")
        decision = list(decisions.values())[0]
        self.assertEqual(decision.get("authority"), AUTHORITY_CONSUL_DIRECT)
        self.assertEqual(decision.get("mode"), "command")
        self.assertEqual(decision.get("war_id"), war.id)
        self.assertIsNone(decision.get("proposal_id"))
        target = decision["payload"]["target_commander_id"]
        n = decision["payload"]["reinforcement_n"]
        self.assertIsNotNone(target, "替补 Commander 必须存在")
        self.assertIsNotNone(state.get_member(target))
        self.assertFalse(state.get_member(target).is_dead)
        pool = len(state.get_military_system().get_available_legions())
        self.assertGreaterEqual(n, 0)
        self.assertLessEqual(n, pool)

        # Store 自动 finalization 实际执行（唯一 Transition Owner 在位）
        self.assertTrue((data.get("finalization") or {}).get("finalized"),
                        "R11-G7R-01：direct-only 必须触发既有 _auto_finalize_after_submit")
        self.assertTrue(state.get_phase_result("senate"),
                        "真实成功 phase_result('senate') 必须落盘")
        self.assertEqual(store.senateCurrentStep, "results")
        self.assertTrue(store.canAdvanceSenate,
                        "R11-G7R-01：direct-only 不得软锁——can_advance 必须为 True")

        view = senate_api.get_senate_view(state, "player2")["data"]
        self.assertFalse(view["can_vote"])
        self.assertFalse(view["can_veto"])
        self.assertFalse(view["can_auto_veto"])
        # 一致性不变式：无真提案 → 无 submitted_proposals
        self.assertEqual(store.senateSubmittedProposals, [])

        # Store.doAdvanceSenate() **之前**：零早写
        self.assertEqual(war.commander_id, 9, "Submit 期不得早写 War commander")
        self.assertEqual(state.get_military_system().get_legions_for_battle(war.id), [],
                         "Submit 期零军团绑定")
        self.assertFalse(state.get_member(target).is_absent, "Submit 期指挥官不得外派")

        # 真实 Store doAdvanceSenate → Senate→Combat 边界（唯一军事 mutation 点）
        adv = store.doAdvanceSenate()
        self.assertTrue(adv.get("success"), adv.get("message"))
        self.assertEqual(war.commander_id, target,
                         "边界后 War Commander 必须为 frozen direct-decision target")
        self.assertTrue(state.get_member(target).is_absent, "边界后指挥官出征")
        bound = state.get_military_system().get_legions_for_battle(war.id)
        self.assertEqual(len(bound), n, "新绑定 Legion 数必须等于请求合法 N")
        receipt = state.get_war_execution_receipt_for_session(session_id)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.get("status"), "COMMITTED")


# ---------------------------------------------------------------------------
# R11-G7R-02（控制）AI 真提案包 → 不早 finalize（保留 Vote/Veto）
# ---------------------------------------------------------------------------
class TestR11G7R02AiRealProposalNotEarlyFinalized(unittest.TestCase):
    def test_g7r02_ai_true_proposal_keeps_vote_lifecycle(self):
        random.seed(20261002)
        state = _build_g7r_state({
            "combat_rules": {"war_takeover_chance": 0.0},
            "testing": {"always_declare": True, "propose_war_chance": 1.0},
        })
        _disable_ai_other_sources(state)
        # 覆盖：确定性产出 1 个真 Senate 提案（THREAT 宣战 → senate_vote 权威）
        state.config.testing.always_declare = True
        state.config.testing.propose_war_chance = 1.0
        _add_threat_war(state)

        store = GuiSessionStore(state)
        store.initialize("player2")
        self.assertTrue(store.canTriggerAIProposer)

        feedback = store.doSubmitSenateProposals([])
        self.assertTrue(feedback.get("success"), feedback.get("message"))
        data = feedback.get("data") or {}

        self.assertTrue(data.get("created"), "本控制包必须含 >=1 真元老院提案")
        # 未早 finalize（保留 Vote/Veto）
        self.assertFalse((data.get("finalization") or {}).get("finalized"))
        self.assertFalse(state.get_phase_result("senate"),
                         "R11-G7R-02：真提案包不得在 submit 期 finalize")
        self.assertIn(store.senateCurrentStep, ("senate_vote", "tribune_veto"))
        self.assertFalse(store.canAdvanceSenate)
        # 一致性不变式：submitted_proposals == canonical created 同源同数
        self.assertEqual(len(store.senateSubmittedProposals), len(data["created"]))


if __name__ == "__main__":
    unittest.main()
