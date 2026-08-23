# src/tests/test_api/test_senate_r1.py
"""GUI-BETA-R1 WP-D-R1（G7 Focused Correction）生产链测试（F-R1-01/03/04 + §13.1 targeted 1/6/7/8）。

覆盖 AC-R1-01/02/05/06（DATA 侧）：
- F-R1-01  Human Consul 全链：多提案 → 提交 → 投票 → 否决路由 → resolve → 公示
           （amount_C/legions/budget 端到端一致 + 公示 enacted key_parameters）
- F-R1-03  Vote stability：AI 决策 created once → persisted → reused（Veto/resolve 单决策不重掷）
           + 幂等 guard（C3）+ vote_source/decision_state provenance（AU-R1-02c/06a）
- F-R1-04  Takeover Direct Action：真实 ACTIVE 战争 + 需换指挥官 + eligible Consul——
           resolve_senate 零接管 → auto_submit_proposals（AI 流）恰 1 mutation + 1 direct_actions
           （trigger_source="ai_auto" provenance，AU-R1-05b/c，C1/C4）
- F-R1-05  zero-proposal 回归沿用 test_senate_zero_proposal.py（本文件不重复）
"""
import logging
import os
import sys
import unittest

from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


def _build_r1_state(config=None):
    """WP-D-R1 生产链配方（对齐 test_senate_api.py setUp + _build_real_senate_state 权威值域）。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._war_system.load_wars_from_json("wars.json")
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    # 权威值域（ODR-ED-01/02）：budget_range {min:1,max:150,step:1,default:100}；legion [1..pool]
    state.config.economic_rules.senate_budget = {
        "public_works_min": 1, "public_works_max_ratio": 1.5,
        "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
    }
    state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

    faction1 = Faction(id="optimates", name="Optimates", treasury=50)
    faction2 = Faction(id="populares", name="Populares", treasury=30)
    state.add_faction(faction1)
    state.add_faction(faction2)

    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    faction1.member_ids.append(1)

    senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 100
    state.add_member(senator)
    faction1.member_ids.append(2)

    tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    faction2.member_ids.append(3)

    populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
    populares_senator.class_tier = ClassTier.NOBILE
    populares_senator.influence = 80
    state.add_member(populares_senator)
    faction2.member_ids.append(4)

    state._players = {
        "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
    }
    state._current_player_id = "player1"
    state._turn_order = ["player1", "player2"]
    return state


def _add_threat_war(state, war_id="w1", name="皮洛士战争"):
    war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    return war


def _add_active_war(state, war_id="w1", name="第一次布匿战争", commander_id=None):
    war = War(id=war_id, name=name, war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    state.get_war_system()._active_wars.append(war)
    return war


class _CountingVoteDecider:
    """instrumented decider（parity-proof：真实链注入确定性实例 + 计数，非 mock-only）。"""

    def __init__(self, decision=True):
        self.decisions = 0
        self._decision = decision

    def decide_vote(self, issue, faction, state):
        self.decisions += 1
        return self._decision


class _CaptureHandler(logging.Handler):
    """捕获 state._logger 结构化记录（log_event extra 展平进 message，key=value 可断言）。"""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


# ---------------------------------------------------------------------------
# F-R1-01 — Human Consul 全链（AC-R1-01/07）
# ---------------------------------------------------------------------------

class TestFR1HumanConsulFullChain(unittest.TestCase):
    def test_human_consul_full_chain_continuity(self):
        """F-R1-01：配置多提案 → 提交 → 投票 → 否决路由 → resolve → 公示。

        断言 amount_C/legions/budget 端到端一致；公示 enacted 仅 final enacted
        （否决的 war 不进公示）；land key_parameters.amount_C / budget key_parameters.modified_budget。
        """
        state = _build_r1_state()
        _add_threat_war(state)
        contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING

        # 配置阶段（authoritative 参数）
        war_result = senate_api.propose(state, "player1", "war", war_id="w1", legions=4)
        self.assertTrue(war_result["success"], war_result.get("message"))
        pid_war = war_result["data"]["proposal_id"]
        land_result = senate_api.propose(state, "player1", "land", act_type="sale", amount_C=50)
        self.assertTrue(land_result["success"], land_result.get("message"))
        pid_land = land_result["data"]["proposal_id"]
        budget_result = senate_api.propose(state, "player1", "budget", contract_id=contract.id, modified_budget=120)
        self.assertTrue(budget_result["success"], budget_result.get("message"))
        pid_budget = budget_result["data"]["proposal_id"]

        proposals = {p["id"]: p for p in state.get_senate_proposals()}
        self.assertEqual(proposals[pid_war]["legions"], 4)
        self.assertEqual(proposals[pid_land]["amount_C"], 50)
        self.assertEqual(proposals[pid_land]["percent"], 50 / 1000)
        self.assertEqual(proposals[pid_budget]["modified_budget"], 120)

        # 投票阶段（human 双派系全投支持 → 无 AI 随机性）
        vote1 = senate_api.vote(state, "player1", [pid_war, pid_land, pid_budget], [True, True, True])
        self.assertTrue(vote1["success"], vote1.get("message"))
        state._current_player_id = "player2"
        vote2 = senate_api.vote(state, "player2", [pid_war, pid_land, pid_budget], [True, True, True])
        self.assertTrue(vote2["success"], vote2.get("message"))

        # 否决路由：保民官（populares）否决 war 提案
        veto_result = senate_api.veto(state, "player2", [pid_war])
        self.assertTrue(veto_result["success"], veto_result.get("message"))

        # resolve → 公示
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        data = resolved["data"]
        self.assertEqual(sorted(data["passed_proposals"]), sorted([pid_land, pid_budget]))
        self.assertIn(pid_war, data["rejected_proposals"])
        self.assertIn(pid_war, data["vetoed_proposals"])

        announcement = data["public_announcement"]
        enacted_by_id = {p["proposal_id"]: p for p in announcement["enacted_proposals"]}
        self.assertNotIn(pid_war, enacted_by_id)  # D-06：vetoed 不进公示
        self.assertEqual(enacted_by_id[pid_land]["key_parameters"]["amount_C"], 50)
        self.assertEqual(enacted_by_id[pid_land]["type"], "land")
        self.assertEqual(enacted_by_id[pid_budget]["key_parameters"]["modified_budget"], 120)
        # 连续性：rejected snapshot 保留权威参数（label 同源）
        war_snapshot = [p for p in data["rejected_proposals_snapshot"] if p["id"] == pid_war][0]
        self.assertEqual(war_snapshot["legions"], 4)


# ---------------------------------------------------------------------------
# F-R1-03 — Vote stability（AC-R1-02 BLOCKER，AU-R1-02a/b/c）
# ---------------------------------------------------------------------------

class TestFR1VoteStability(unittest.TestCase):
    def _setup(self):
        state = _build_r1_state()
        _add_threat_war(state)
        pid1 = senate_api.propose(state, "player1", "war", war_id="w1", legions=4)["data"]["proposal_id"]
        pid2 = senate_api.propose(state, "player1", "land", act_type="sale", amount_C=50)["data"]["proposal_id"]
        # human 票（player1 权威）
        senate_api.vote(state, "player1", [pid1, pid2], [True, True])
        return state, pid1, pid2

    def _active_ai_faction_count(self, state, proposal_ids):
        """活跃 AI 派系数：有影响力、有玩家、且无 human 票的派系数（决定 decide_vote 期望次数）。"""
        votes = state.get_senate_votes_copy()
        count = 0
        for faction in state.get_active_factions():
            influence = faction.get_senate_influence(state)
            if influence == 0:
                continue
            player = state.get_player_by_faction(faction.id)
            if not player:
                continue
            if any(pid not in votes.get(player.player_id, {}) for pid in proposal_ids):
                count += 1
        return count

    def test_veto_then_resolve_no_reroll(self):
        """变体 A：Veto 消费（_passed_proposals_for_veto）先持久化 → resolve 复用（0 新决策）。"""
        state, pid1, pid2 = self._setup()
        expected = self._active_ai_faction_count(state, [pid1, pid2])  # populares 无 human 票 → 1

        # Veto 路径消费（内部 AutoSenateVoteDecider 决策并持久化 AI 票）
        senate_api._passed_proposals_for_veto(state)

        # resolve 复用同一存储——注入计数 decider：0 次新决策（vote 稳定性核心断言）
        decider1 = _CountingVoteDecider(decision=True)
        resolved1 = senate_api.resolve_senate(state, vote_decider=decider1)
        self.assertTrue(resolved1["success"])
        self.assertEqual(decider1.decisions, 0, "Veto 已持久化后 resolve 不得重掷")
        self.assertEqual(resolved1["data"]["passed_proposals"], [pid1, pid2])  # 双支持 → 双通过

        # 重复 resolve（§11 negative：repeated view refresh 不 re-vote）——仍 0 新决策
        decider2 = _CountingVoteDecider(decision=True)
        resolved2 = senate_api.resolve_senate(state, vote_decider=decider2)
        self.assertTrue(resolved2["success"])
        self.assertEqual(decider2.decisions, 0)
        _ = expected  # 计数断言在变体 B（resolve 首次）承载

    def test_resolve_first_then_veto_then_resolve(self):
        """变体 B：resolve 首次 → 决策计数 == 活跃 AI 派系数；之后 Veto/resolve 0 新决策。"""
        state, pid1, pid2 = self._setup()
        expected = self._active_ai_faction_count(state, [pid1, pid2])
        self.assertEqual(expected, 1, "fixture 必须恰有 1 个活跃 AI 派系")

        decider1 = _CountingVoteDecider(decision=True)
        resolved1 = senate_api.resolve_senate(state, vote_decider=decider1)
        self.assertTrue(resolved1["success"])
        # 每个 proposal × 活跃 AI 派系恰一次决策（2 提案 × 1 AI 派系）
        self.assertEqual(decider1.decisions, expected * 2)

        # Veto 消费 + 再 resolve：0 新决策（全 reused）
        senate_api._passed_proposals_for_veto(state)
        decider2 = _CountingVoteDecider(decision=True)
        resolved2 = senate_api.resolve_senate(state, vote_decider=decider2)
        self.assertTrue(resolved2["success"])
        self.assertEqual(decider2.decisions, 0, "持久化后不得重掷")
        # 注册表随会期 clear_senate_pending 重置（C3 无跨会话泄漏语义；含 AI 票来源的注册
        # 断言见 test_vote_source_registry_round_trip_and_clear——不经过 resolve 的会期）
        self.assertEqual(state.get_senate_vote_source("player2", pid1), None)
        self.assertEqual(state.get_senate_vote_source("player1", pid1), None)

    def test_idempotent_guard_duplicate_returns_false(self):
        """C3：record_senate_vote 重复返回 False（幂等契约先天成立，AI 写回不覆盖 human/既有票）。"""
        state, pid1, _ = self._setup()
        self.assertFalse(state.record_senate_vote("player1", pid1, False, source="ai"),
                         "重复投票必须返回 False（human 权威不被 AI 写回覆盖）")
        self.assertTrue(state.get_senate_votes_copy()["player1"][pid1])
        self.assertEqual(state.get_senate_vote_source("player1", pid1), "human")

    def test_vote_source_registry_round_trip_and_clear(self):
        """AU-R1-02b：注册表存档往返（to_dict→load_from_dict）+ clear 无泄漏（C3）。

        注意：使用真实 Player 对象（MagicMock player 的 to_dict 不可序列化）。
        """
        from src.core.entities.player import Player, PlayerType
        state = _build_r1_state()
        state._players = {
            "player1": Player("player1", "optimates", PlayerType.HUMAN),
            "player2": Player("player2", "populares", PlayerType.HUMAN),
        }
        state._current_player_id = "player1"
        state._turn_order = ["player1", "player2"]
        pid1 = senate_api.propose(state, "player1", "land", act_type="sale", amount_C=50)["data"]["proposal_id"]
        senate_api.vote(state, "player1", [pid1], [True])
        senate_api._passed_proposals_for_veto(state)  # AI 票持久化
        self.assertEqual(state.get_senate_vote_source("player1", pid1), "human")
        self.assertEqual(state.get_senate_vote_source("player2", pid1), "ai")

        # 存档往返：vote_source 随 to_dict/load_from_dict 保留
        data = state.to_dict()
        restored = GameState.create_for_testing({})
        restored.load_from_dict(data)
        self.assertEqual(restored.get_senate_vote_source("player2", pid1), "ai")
        self.assertEqual(restored.get_senate_vote_source("player1", pid1), "human")

        # 旧存档缺 vote_source 键 → 空 dict（向后兼容，不崩）
        legacy_data = data.copy()
        legacy_data["_senate_pending"] = {k: v for k, v in data["_senate_pending"].items() if k != "vote_source"}
        restored2 = GameState.create_for_testing({})
        restored2.load_from_dict(legacy_data)
        self.assertIsNone(restored2.get_senate_vote_source("player2", pid1))

        # clear_senate_votes / clear_senate_pending 镜像清除（无跨会话泄漏）
        state.clear_senate_votes()
        self.assertIsNone(state.get_senate_vote_source("player2", pid1))
        state.record_senate_vote("player2", pid1, True, source="ai")
        state.clear_senate_pending()
        self.assertIsNone(state.get_senate_vote_source("player2", pid1))

    def test_provenance_log_created_and_reused(self):
        """AU-R1-02c/06a：结构化 log_event（type=senate_vote_decision + extra 5 字段）。"""
        config = {"logging": {"enabled": True, "file_path": "/tmp/eor-r1-test.log", "log_level": "INFO"}}
        state, pid1, pid2 = self._setup()
        # 重新启用日志（create_for_testing 后补开 logger）
        state._config._config["logging"] = config["logging"]
        state._setup_logging()
        self.assertIsNotNone(state._logger)
        handler = _CaptureHandler()
        state._logger.addHandler(handler)
        try:
            # 生产序：Veto 消费先持久化（created），resolve 复用（reused）
            senate_api._passed_proposals_for_veto(state)
            decider1 = _CountingVoteDecider(decision=True)
            resolved = senate_api.resolve_senate(state, vote_decider=decider1)
            self.assertTrue(resolved["success"])
            self.assertEqual(decider1.decisions, 0, "Veto 已持久化后 resolve 不得重掷")

            decision_msgs = [r.getMessage() for r in handler.records if "type=senate_vote_decision" in r.getMessage()]
            self.assertTrue(len(decision_msgs) >= 6, f"决策日志不足: {len(decision_msgs)}")

            created = [m for m in decision_msgs if "decision_state=created" in m]
            reused = [m for m in decision_msgs if "decision_state=reused" in m]
            # 2 提案 × 1 AI 派系 = 2 created（首次决策即持久化，vote_source=ai；决策值由内部
            # AutoSenateVoteDecider 随机，只断言可溯源字段）
            self.assertEqual(len(created), 2, created)
            for m in created:
                self.assertIn("vote_source=ai", m)
                self.assertIn("vote=", m)
            # reused 路径含 AI 票（vote_source=ai，resolve 复用 populares）+ human 票（vote_source=human）
            self.assertTrue(any("vote_source=ai" in m for m in reused), reused)
            self.assertTrue(any("vote_source=human" in m for m in reused), reused)
            self.assertTrue(any("faction_id=populares" in m for m in reused), reused)
        finally:
            state._logger.removeHandler(handler)
            handler.close()
            state.close_logging()


# ---------------------------------------------------------------------------
# F-R1-04 — Takeover Direct Action（AC-R1-05 BLOCKER，AU-R1-05a/b/c，C1/C4）
# ---------------------------------------------------------------------------

class TestFR1TakeoverDirectAction(unittest.TestCase):
    def setUp(self):
        # war_takeover_chance=1.0 → 默认 AutoWarTakeoverDecider 确定性接管（非 mock）
        self.state = _build_r1_state({"combat_rules": {"war_takeover_chance": 1.0}})
        self.war = _add_active_war(self.state)

    def test_resolve_does_not_takeover(self):
        """§11 negative + AC-R1-05：普通 resolve 不执行接管（commander 不变 + direct_actions 空）。"""
        resolved = senate_api.resolve_senate(self.state)
        self.assertTrue(resolved["success"])
        self.assertIsNone(self.war.commander_id, "resolve 不得隐藏接管")
        self.assertEqual(self.state.get_senate_direct_actions(), [])

        # 重复 resolve 也不能静默接管
        senate_api.resolve_senate(self.state)
        self.assertIsNone(self.war.commander_id)
        self.assertEqual(self.state.get_senate_direct_actions(), [])

    def test_ai_auto_takeover_via_auto_submit_proposals(self):
        """F-R1-04 AI 分支（C1，D-1）：auto_submit_proposals 尾部恰 1 次 AI 接管 + provenance。"""
        # resolve 先行（零接管）→ AI 流 auto_submit_proposals 触发 1 接管
        senate_api.resolve_senate(self.state)
        self.assertIsNone(self.war.commander_id)

        result = senate_api.auto_submit_proposals(
            self.state,
            land_proposal_deciders=[],  # 0 提案批（聚焦 takeover 副作用）
        )
        self.assertTrue(result["success"], result.get("message"))

        # 恰 1 mutation：consul（id=1）被指派 + 置位 absent
        self.assertEqual(self.war.commander_id, 1)
        self.assertTrue(self.state.get_member(1).is_absent)
        self.assertTrue(self.war.legion_numbers)

        # 恰 1 direct_actions + provenance（trigger_source=ai_auto / action / previous/resulting_status）
        actions = self.state.get_senate_direct_actions()
        self.assertEqual(len(actions), 1)
        record = actions[0]
        self.assertEqual(record["action_type"], "takeover")
        self.assertEqual(record["action"], "takeover")
        self.assertEqual(record["war_id"], self.war.id)
        self.assertEqual(record["commander_id"], 1)
        self.assertEqual(record["trigger_source"], "ai_auto")
        self.assertEqual(record["previous_status"], "active")
        self.assertEqual(record["resulting_status"], "active")
        self.assertEqual(record["legions"], list(self.war.legion_numbers))

        # C4：view DTO dict 透传零破坏
        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        self.assertEqual(len(view["data"]["direct_actions"]), 1)
        self.assertEqual(view["data"]["direct_actions"][0]["trigger_source"], "ai_auto")

    def test_ai_takeover_skips_war_with_valid_commander(self):
        """§11 negative：已有有效指挥官 → AI 自动接管跳过（零 mutation）。"""
        self.war.commander_id = 2  # senator 2（非 absent/非死）→ 有效指挥官
        result = senate_api.auto_submit_proposals(self.state, land_proposal_deciders=[])
        self.assertTrue(result["success"])
        self.assertEqual(self.war.commander_id, 2)
        self.assertEqual(self.state.get_senate_direct_actions(), [])


if __name__ == "__main__":
    unittest.main()
