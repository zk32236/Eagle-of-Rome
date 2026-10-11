# src/tests/test_api/test_wpk_s1_reinforcement.py
"""WP-K S1（OD-K-01）— AI 军团增援 N「敌强匹配」冻结规则测试（v1.4 对齐）。

设计来源（单一权威）：02-sa-design/SA-Development-Task-WP-K-v1.4-2026-10-11.md（FC-K-01…09；FC-K-31）。
覆盖 K-AC-08.1…08.8；边界 B-01…B-13（state-boundary-checklist-WP-K-v1.4 §A + §G）。

- Targeted：`senate_api.reinforcement_n_target`（module-level 单一 producer）。
- PRODUCTION_CHAIN：`senate_api.auto_submit_proposals` 4b′ → consul_direct decision
  payload `reinforcement_n`（真实入口，不 monkeypatch 被测生产者）。
- LC-K-05（F-08 / FC-K-31）：4a no-touch 负测 + 混合 4a（宣战）+ 4b′（增援）包 `ΣN ≤ pool`
  经真实 `_legion_options_for_war` / `random.randint`（4a 自有 draw）+ `propose_many`/`submit_proposal_package` 聚合校验。
- §9.1 No Test-Assisted Transition（N-01）：本文件全部经真实生产 owner（`auto_submit_proposals`），
  禁直调 `_validate_reinforcement_n`/`commit_war_resolution` 冒充生产链。

N 目标 = clamp(ceil(E/u), 1, min(remaining, pool))；零池 → 0；
E = war.get_total_strength()（陆战敌强，Owner S-2=A）；u = config
economic_rules.legion_strength_base（默认 2）。
"""
import os
import sys
import unittest

import random

import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def _isolate_global_rng():
    """不扰动全局 random 序列（防影响后续顺序敏感测试）。"""
    _state = random.getstate()
    yield
    random.setstate(_state)

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import senate_api


# ---------------------------------------------------------------------------
# Targeted：producer 单元（不确定 + 边界）
# ---------------------------------------------------------------------------
def _fake(state_u=2, enemy=5):
    state = MagicMock()
    state.get_economic_rule = MagicMock(return_value=state_u)
    war = MagicMock()
    war.get_total_strength = MagicMock(return_value=enemy)
    return state, war


class TestReinforcementNTarget(unittest.TestCase):
    def _n(self, state_u=2, enemy=5, remaining=10, pool=25):
        state, war = _fake(state_u, enemy)
        return senate_api.reinforcement_n_target(state, war, remaining, pool)

    def test_normal_enemy_matched(self):
        """B-01：ceil(5/2)=3，落池内 → 3。"""
        self.assertEqual(self._n(enemy=5, state_u=2), 3)

    def test_ceil_rounding(self):
        """FC-K-04：ceil(7/2)=4（非 3）。"""
        self.assertEqual(self._n(enemy=7, state_u=2), 4)

    def test_over_pool_clamped(self):
        """B-02：超池 → N=pool。"""
        self.assertEqual(self._n(enemy=100, state_u=2, remaining=10, pool=10), 10)

    def test_insufficient_available_fill(self):
        """B-02b：可用不足（remaining<pool）→ 招满 = remaining。"""
        self.assertEqual(self._n(enemy=100, state_u=2, remaining=3, pool=10), 3)

    def test_zero_pool(self):
        """B-03：零池 → 0。"""
        self.assertEqual(self._n(enemy=5, pool=0, remaining=0), 0)

    def test_enemy_zero_pool_positive(self):
        """B-04：E=0 且池>0 → 1（镜像舰队先例）。"""
        self.assertEqual(self._n(enemy=0, pool=10, remaining=10), 1)

    def test_enemy_zero_zero_pool(self):
        """B-05：E=0 且池=0 → 0。"""
        self.assertEqual(self._n(enemy=0, pool=0, remaining=0), 0)

    def test_remaining_exhausted(self):
        """B-07：残余池不足单战（remaining<1）→ 0。"""
        self.assertEqual(self._n(enemy=5, pool=10, remaining=0), 0)

    def test_u_degenerate_treated_as_one(self):
        """B-12：u<=0 → 视为 1（禁除零）。"""
        self.assertEqual(self._n(enemy=5, state_u=0), 5)

    def test_default_u_when_key_absent(self):
        """FC-K-03：缺键 → 默认 u=2。"""
        state, war = _fake(enemy=5)
        state.get_economic_rule = MagicMock(side_effect=lambda key, default=None: default)
        self.assertEqual(senate_api.reinforcement_n_target(state, war, 10, 25), 3)

    def test_determinism_repeated(self):
        """B-08 / FC-K-07：相同输入重复 → 同 N（无 random）。"""
        vals = {self._n(enemy=9, state_u=2, remaining=20, pool=20) for _ in range(5)}
        self.assertEqual(vals, {5})

    def test_enemy_field_missing_skips(self):
        """B-09：敌强源不可读 → 返回 None（跳过该战，不造伪值）。"""
        state = MagicMock()
        state.get_economic_rule = MagicMock(return_value=2)
        war = MagicMock()
        war.get_total_strength = MagicMock(side_effect=AttributeError("missing"))
        self.assertIsNone(senate_api.reinforcement_n_target(state, war, 10, 25))


# ---------------------------------------------------------------------------
# PRODUCTION_CHAIN：auto_submit_proposals 4b′ → consul_direct decision
# ---------------------------------------------------------------------------
def _build_state(config=None):
    """R11 生产链基线态（真实 War + 军团池 25 UNRAISED + 合法 Commander 候选）。"""
    state = GameState.create_for_testing(config or {})
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
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


def _add_active_war(state, strength=5, commander_id=9, war_id="w1"):
    war = War(id=war_id, name="第一次布匿战争", war_type=WarType.FOREIGN,
              strength=strength, naval_required=False)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    state.get_war_system()._active_wars.append(war)
    return war


def _add_threat_war(state, strength=5):
    war = War(id="w_threat", name="威胁战争", war_type=WarType.FOREIGN,
              strength=strength, naval_required=False)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    return war


def _reinforcement_n(state):
    result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
    assert result["success"], result.get("message")
    session_id = state.get_senate_session()
    decisions = state.get_consul_war_decisions(session_id)
    assert len(decisions) == 1, f"expected 1 consul_direct decision, got {list(decisions)}"
    return list(decisions.values())[0]["payload"]["reinforcement_n"]


class TestReinforcementProductionChain(unittest.TestCase):
    def test_enemy_matched_default_u(self):
        """K-AC-08.1：E=5，u=2（默认）→ N=3（真实 4b′）。"""
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        _add_active_war(state, strength=5)
        self.assertEqual(_reinforcement_n(state), 3)

    def test_config_u_drives_n(self):
        """K-AC-08.1 + FC-K-03：u=4 → ceil(5/4)=2。"""
        state = _build_state({
            "combat_rules": {"war_takeover_chance": 1.0},
            "economic_rules": {"legion_strength_base": 4},
        })
        _add_active_war(state, strength=5)
        self.assertEqual(_reinforcement_n(state), 2)

    def test_over_pool_clamped_production(self):
        """B-02（生产链）：E=100，u=2 → 目标 50 > 池 25 → N=25。"""
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        _add_active_war(state, strength=100)
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(_reinforcement_n(state), pool)

    def test_zero_pool_production(self):
        """B-03（生产链）：池=0 → N=0。"""
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        ms = state.get_military_system()
        for number in range(1, 26):
            ms.recruit_legion(number)
        self.assertEqual(len(ms.get_available_legions()), 0)
        _add_active_war(state, strength=5)
        self.assertEqual(_reinforcement_n(state), 0)

    def test_enemy_zero_production(self):
        """K-AC-08.5（生产入口）：E=0 且池>0 → N=1（真实 4b′，非 helper）。"""
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        _add_active_war(state, strength=0)
        self.assertEqual(_reinforcement_n(state), 1)

    def test_determinism_production(self):
        """K-AC-08.6（生产入口）：不同 RNG seed ⇒ 相同输入产相同 N（无 random 依赖）。

        经真实 `auto_submit_proposals` 4b′（生产入口）两次独立构造（不同 seed）⇒ 同 N。
        """
        values = []
        for seed in (111, 222):
            random.seed(seed)
            state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
            _add_active_war(state, strength=9)   # ceil(9/2)=5
            values.append(_reinforcement_n(state))
        self.assertEqual(values, [5, 5])


# ---------------------------------------------------------------------------
# LC-K-03（K-AC-08.4）— ≥2 active wars 4b′ 顺序消费共享池（PRODUCTION_CHAIN）
# ---------------------------------------------------------------------------
class TestS1LongChainMultiWar(unittest.TestCase):
    def test_lc_k_03_multi_active_wars_sequential_consumption(self):
        """LC-K-03 / K-AC-08.4：≥2 active wars，pool < ΣN_target ⇒ 共享池顺序消费。

        production owner = `auto_submit_proposals`（4b′ 共享 `remaining` 顺序消费）→ `propose_many`
        → `submit_proposal_package`（聚合校验 `ΣN ≤ pool`）。证据路径 = PRODUCTION_CHAIN。
        禁直调 `reinforcement_n_target`/手工构造多 draft 冒充顺序消费（§9.1）。

        E=30, u=2 ⇒ N_target=15 each；pool=25 < 30 ⇒ 顺序消费：w1=15、w2=min(15,25-15)=10；
        ΣN=25=pool（守恒且不超池）。
        """
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        pool = len(state.get_military_system().get_available_legions())
        _add_active_war(state, strength=30, commander_id=None, war_id="w1")
        _add_active_war(state, strength=30, commander_id=None, war_id="w2")
        result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        session_id = state.get_senate_session()
        decisions = state.get_consul_war_decisions(session_id)
        self.assertEqual(len(decisions), 2, f"expected 2 consul_direct decisions, got {list(decisions)}")
        by_war = {d["war_id"]: d["payload"]["reinforcement_n"] for d in decisions.values()}
        self.assertEqual(by_war["w1"], 15, by_war)
        self.assertEqual(by_war["w2"], 10, by_war)
        self.assertLessEqual(sum(by_war.values()), pool, by_war)
        self.assertEqual(sum(by_war.values()), pool, by_war)   # 顺序消费至池耗尽
        self.assertEqual(result["errors"], [], result["errors"])
        # per-war N 合法（均在值域 [1, pool] 内）
        for n in by_war.values():
            self.assertGreaterEqual(n, 1)
            self.assertLessEqual(n, pool)


# ---------------------------------------------------------------------------
# LC-K-04（K-AC-08.7）— 完整生产生命周期 nodeid（PRODUCTION_CHAIN）
# ---------------------------------------------------------------------------
class TestS1LongChainLifecycle(unittest.TestCase):
    def test_lc_k_04_full_lifecycle_nodeid(self):
        """LC-K-04 / K-AC-08.7：完整生命周期 nodeid —— 经**真实 CLI glue** 驱动 transition。

        Transition Owner = CLI `src/ui/commands/phase_senate.py::SenateCommand.execute`
        （尾部 `phase_senate.py:118-133`；`:129` 自动调用 `advance_senate_phase` = 唯一
        Senate→Combat mutation owner）。CLI 内部链：`auto_submit_proposals`（4b′ producer）
        → `propose_many` → `submit_proposal_package` → 真实表决
        `finalize_senate_if_ready`（= `resolve_senate`）→ `advance_senate_phase`
        → `commit_war_resolution`（唯一原子军事执行 owner）。

        断言：CLI 执行完成后 `senate` 已 executed；冻结 ConsulWarDecision 快照 N == 边界后
        绑定 Legion 数；receipt COMMITTED 且 `direct_decision_refs` 含本 direct decision。
        证据路径 = PRODUCTION_CHAIN。

        §9.1 No Test-Assisted Transition：本测试**不**直调 `advance_senate_phase` /
        `resolve_senate` / `commit_war_resolution` / `_validate_reinforcement_n`；transition
        一律由真实 CLI owner 触发（CLI advance glue 若被移除/损坏 → 本 nodeid 失败）。
        """
        from src.ui.commands.phase_senate import SenateCommand
        state = _build_state({"combat_rules": {"war_takeover_chance": 1.0}})
        _add_active_war(state, strength=5, commander_id=9)   # 现任已阵亡 → Takeover
        cmd = SenateCommand(state, land_proposal_deciders=[])
        completed = cmd.execute([])
        self.assertTrue(completed, "CLI glue 未完成 senate 阶段（尾部 advance 未成功）")
        # CLI 尾部 `advance_senate_phase` 已 mark senate executed（唯一外部 mutation）
        self.assertTrue(state.is_phase_executed("senate"))
        session_id = state.get_senate_session()
        # 冻结 ledger 快照（ConsulWarDecision FROZEN payload）== 4b′ draft N
        decisions = state.get_consul_war_decisions(session_id)
        self.assertEqual(len(decisions), 1, list(decisions))
        decision = list(decisions.values())[0]
        draft_n = decision["payload"]["reinforcement_n"]
        self.assertEqual(draft_n, 3, decision)   # ceil(5/2)
        target = decision["payload"]["target_commander_id"]
        self.assertIsNotNone(target)
        # 边界后：War commander == target；绑定 Legion 数 == draft N
        war = state.get_war_system().get_war_by_id("w1")
        self.assertEqual(war.commander_id, target)
        bound = state.get_military_system().get_legions_for_battle("w1")
        self.assertEqual(len(bound), draft_n)
        # receipt exactly-once（commit-side）
        receipt = state.get_war_execution_receipt_for_session(session_id)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.get("status"), "COMMITTED")
        ref_ids = [r.get("direct_decision_id") for r in receipt.get("direct_decision_refs", [])]
        self.assertIn(decision["direct_decision_id"], ref_ids)


# ---------------------------------------------------------------------------
# LC-K-05（F-08 / FC-K-31 / K-AC-08.8）— 4a no-touch 负测 + 混合 4a+4b′ 聚合包
# ---------------------------------------------------------------------------
class TestS1LongChain4aNoTouch(unittest.TestCase):
    def test_4a_options_unchanged(self):
        """B-10 / FC-K-31：S1 不改 4a 值域——`_legion_options_for_war` 输出不变。"""
        state = _build_state()
        pool = len(state.get_military_system().get_available_legions())
        threat = _add_threat_war(state)
        options = senate_api._legion_options_for_war(state, threat)
        self.assertEqual(options["min"], 1)
        self.assertEqual(options["max"], pool)
        self.assertEqual(options["default"], min(4, pool))
        self.assertEqual(options["allowed"], list(range(1, pool + 1)))

    def test_4a_random_draw_preserved(self):
        """B-10 / FC-K-31：4a 宣战军团数仍用自有 `random.randint`（不经敌强匹配）。"""
        state = _build_state({
            "combat_rules": {"war_takeover_chance": 1.0},
            "testing": {"always_declare": True},
        })
        _add_threat_war(state, strength=5)
        with patch('random.randint', return_value=7) as mri:
            result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        declared = [p for p in result["data"]["proposals"] if p["type"] == "war"]
        self.assertEqual(len(declared), 1, result["data"].get("proposals"))
        self.assertEqual(declared[0]["legions"], 7)  # 4a 自有 random draw 未被替换
        self.assertTrue(mri.called, "4a 宣战路径须仍调用 random.randint")
        decisions = state.get_consul_war_decisions(state.get_senate_session())
        self.assertEqual(len(decisions), 0)

    def test_mixed_4a_and_4bp_package_pool_invariant(self):
        """LC-K-05：同 run 含 4a（宣战）+ 4b′（增援）；混合包聚合池校验 `ΣN ≤ pool` 且 submit 成功。

        production owner = `auto_submit_proposals`（4a + 4b′ 同 run）→ `propose_many` →
        `submit_proposal_package` 聚合校验（LEGION_POOL_EXCEEDED 门）。证据路径 = PRODUCTION_CHAIN。
        """
        state = _build_state({
            "combat_rules": {"war_takeover_chance": 1.0},
            "testing": {"always_declare": True},
        })
        pool = len(state.get_military_system().get_available_legions())
        _add_threat_war(state, strength=5)      # 4a 宣战（senate_vote 路径）
        _add_active_war(state, strength=5)      # 4b′ 增援（consul_direct 路径）
        with patch('random.randint', return_value=7):
            result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
        self.assertTrue(result["success"], result.get("message"))
        declared = [p for p in result["data"]["proposals"] if p["type"] == "war"]
        by_war = {p["war_id"]: p["legions"] for p in declared}
        # 4a：宣战（w_threat）legions == 7（自有 random draw）
        self.assertEqual(by_war.get("w_threat"), 7, declared)
        # 4b′：增援（w1）N = ceil(5/2) = 3（敌强匹配）
        self.assertEqual(by_war.get("w1"), 3, declared)
        decisions = state.get_consul_war_decisions(state.get_senate_session())
        self.assertEqual(len(decisions), 1, list(decisions))
        reinforce_n = list(decisions.values())[0]["payload"]["reinforcement_n"]
        self.assertEqual(reinforce_n, 3)
        # 聚合池不变量：ΣN ≤ pool（混合 4a+4b′ 包经真实 submit 校验通过）
        self.assertLessEqual(by_war["w_threat"] + reinforce_n, pool)


if __name__ == "__main__":
    unittest.main()
