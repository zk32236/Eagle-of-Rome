# src/tests/test_api/test_wpk_s4_budget_margin.py
"""WP-K S4（OD-K-03）— AI 建造预算加成回归规格 §2.7 测试（v1.4 对齐）。

设计来源（单一权威）：02-sa-design/SA-Development-Task-WP-K-v1.4-2026-10-11.md（FC-K-23…29）。
覆盖 K-AC-12.1…12.8；边界 D-01…D-14（state-boundary-checklist-WP-K-v1.4 §D/E）+ RCC（§8.6）+ F-01 反例（§8.7）。

- 单一取值点：`senate_api.auto_submit_proposals` §4d（**PRODUCTION_CHAIN**）。
- 公式：`modified_budget = int(base_cost × (1 + r))`，`r ~ U(margin_min, margin_max)`。
- config：`economic_rules.public_work_budget_margin_range`（默认 [0.05,0.20]；缺键/畸形/越界 → fail-safe `[0.05,0.20]`，FC-K-29）。
- 人类范围不变量：`[1, int(base×1.5)]`（`_budget_range_for_contract`）不变 → AI 值恒落其中且校验通过。
- 证据路径二值（F-04）：本文件全部 = **PRODUCTION_CHAIN**（真实 `auto_submit_proposals` §4d 取值点 / 真实 `resolve_senate` 表决结算）。
- **FC-K-30 域限定（F-07）**：RNG 等价域仅在 S2 fleet/tax 声明（同函数入口 RNG state 级）；S4 为**显式行为变更**（无等价声明），不主张 phase-seed 级等价。
- **§9.1 No Test-Assisted Transition（N-01）**：K-AC-12.4b 由真实表决（`record_senate_vote`）驱动 production owner
  `senate_api.resolve_senate`（= `finalize_senate_if_ready`）→ 内部 `execute_passed_proposal('budget')`；
  **禁**直调 `execute_passed_proposal` / 改写 `_approved_budget` 冒充 transition。
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
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import senate_api
from src.api.senate_api import _budget_range_for_contract


def _build_state(config=None):
    cfg = {"economic_rules": {"senate_budget": {
        "public_works_min": 1, "public_works_max_ratio": 1.5,
        "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1}}}
    if config:
        cfg["economic_rules"].update(config.get("economic_rules", {}))
        for key, value in config.items():
            if key != "economic_rules":
                cfg[key] = value
    state = GameState.create_for_testing(cfg)
    state.turn = GameTurn(turn_number=1, year=-264)
    state.mark_phase_executed("population")
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    optimates = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(optimates)
    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 50
    state.add_member(consul)
    optimates.member_ids.append(1)
    senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 100
    state.add_member(senator)
    optimates.member_ids.append(2)
    state._players = {
        "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
    }
    state._current_player_id = "player1"
    state._turn_order = ["player1"]
    return state


def _pending_works(state, base=100, is_fleet=False):
    c = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1,
                              base_cost=base, current_turn=1)
    c.status = ContractStatus.PENDING
    if is_fleet:
        c._is_fleet_construction = True
    return c


def _pending_tax(state, base=80):
    c = state.create_contract(ContractType.TAX_FARMING, province_id=1,
                              base_cost=base, current_turn=1)
    c.status = ContractStatus.PENDING
    return c


def _budget_proposals(state):
    result = senate_api.auto_submit_proposals(state, land_proposal_deciders=[])
    assert result["success"], result.get("message")
    return result, [p for p in result["data"].get("proposals", []) if p["type"] == "budget"]


class TestS4BudgetMargin(unittest.TestCase):
    def test_formula_default_margin_patched_r(self):
        """K-AC-12.1：base=100，r=0.10 → int(100×1.10)=110；默认界 (0.05,0.20)。"""
        state = _build_state()
        _pending_works(state, base=100)
        with patch('random.uniform', return_value=0.10) as mu:
            _result, props = _budget_proposals(state)
        self.assertEqual(mu.call_args.args, (0.05, 0.20))
        self.assertEqual(props[0]["modified_budget"], 110)

    def test_boundary_lower_endpoint(self):
        """D-02：r=0.05 → int(base×1.05)。"""
        state = _build_state()
        _pending_works(state, base=100)
        with patch('random.uniform', return_value=0.05):
            _result, props = _budget_proposals(state)
        self.assertEqual(props[0]["modified_budget"], 105)

    def test_boundary_upper_endpoint(self):
        """D-03：r=0.20 → int(base×1.20)。"""
        state = _build_state()
        _pending_works(state, base=100)
        with patch('random.uniform', return_value=0.20):
            _result, props = _budget_proposals(state)
        self.assertEqual(props[0]["modified_budget"], 120)

    def test_config_drives_margin_bounds(self):
        """K-AC-12.2 / D-04：非默认 margin → 以新界 draw。"""
        state = _build_state({"economic_rules": {
            "public_work_budget_margin_range": [0.10, 0.25]}})
        _pending_works(state, base=100)
        with patch('random.uniform', return_value=0.25) as mu:
            _result, props = _budget_proposals(state)
        self.assertEqual(mu.call_args.args, (0.10, 0.25))
        self.assertEqual(props[0]["modified_budget"], 125)

    def test_missing_key_fallback_default(self):
        """K-AC-12.3 / D-05：缺键 → 回退默认 [0.05,0.20]（非回退 randint）。"""
        state = _build_state({})
        _pending_works(state, base=100)
        with patch('random.uniform', return_value=0.10) as mu:
            _result, props = _budget_proposals(state)
        self.assertEqual(mu.call_args.args, (0.05, 0.20))
        self.assertEqual(props[0]["modified_budget"], 110)

    def test_base_one_containment(self):
        """D-07：base=1 → int(1×(1+r))=1（∈ 人类范围 [1,1]）。"""
        state = _build_state()
        c = _pending_works(state, base=1)
        with patch('random.uniform', return_value=0.20):
            _result, props = _budget_proposals(state)
        self.assertEqual(props[0]["modified_budget"], 1)
        rng = _budget_range_for_contract(state, state.get_contract(c.id))
        self.assertEqual(rng["min"], 1)
        self.assertEqual(rng["max"], int(1 * 1.5))

    def test_fleet_same_formula(self):
        """D-08：fleet 合同同分支同公式。"""
        state = _build_state()
        _pending_works(state, base=200, is_fleet=True)
        with patch('random.uniform', return_value=0.10):
            _result, props = _budget_proposals(state)
        self.assertEqual(props[0]["modified_budget"], int(200 * 1.10))  # 220

    def test_tax_no_budget_margin(self):
        """D-10 / K-AC-12.7：TAX_FARMING 不 draw → modified_budget = base_cost（无加成）。"""
        state = _build_state()
        _pending_tax(state, base=80)
        with patch('random.uniform', return_value=0.99) as mu:
            _result, props = _budget_proposals(state)
        self.assertEqual(props[0]["modified_budget"], 80)
        self.assertEqual(mu.call_count, 0, "tax 路径不得 draw margin")

    def test_k_ac_12_4a_value_domain_admission(self):
        """K-AC-12.4a / D-06/D-12：默认 margin 真实 draw → 值 ∈ [105,120] ⊂ 人类范围；

        经真实 §4d → propose_many → submit_proposal_package → `_populate_proposal('budget')` **admitted**
        （errors 空）。证据路径 = PRODUCTION_CHAIN（禁直调 `_populate_proposal` / 手工构造 draft）。
        """
        state = _build_state()
        c = _pending_works(state, base=100)
        result, props = _budget_proposals(state)
        mb = props[0]["modified_budget"]
        rng = _budget_range_for_contract(state, state.get_contract(c.id))
        self.assertGreaterEqual(mb, 1)
        self.assertLessEqual(mb, rng["max"])        # 人类合法上限 int(base×1.5)=150
        self.assertGreaterEqual(mb, rng["min"])
        self.assertIn(mb, range(105, 121))          # [int(base×1.05), int(base×1.20)]
        self.assertEqual(result["errors"], [], "AI 值须经 _populate_proposal 校验通过")
        # 提案已入 state（即 _populate_proposal success）
        stored = [p for p in state.get_senate_proposals() if p.get("type") == "budget"]
        self.assertTrue(stored)

    def test_k_ac_12_4b_pass_execute_persisted_state(self):
        """K-AC-12.4b / D-12b（SC-K-04-3b）：真实表决 PASS → 持久态 B/A/status。

        production owner = `record_senate_vote`（真实表决）→ `senate_api.resolve_senate`
        （= `finalize_senate_if_ready` → `execute_passed_proposal('budget')`）。
        commit-side oracle：`_approved_budget`=值（B）；`_original_budget`（A）**不变**；`status`=BUDGETED。
        证据路径 = PRODUCTION_CHAIN；**禁**直调 `execute_passed_proposal` 冒充 transition（§9.1）。
        """
        state = _build_state({"economic_rules": {
            "senate_budget": {"public_works_min": 1, "public_works_max_ratio": 1.5,
                              "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0,
                              "step": 1}}})
        c = _pending_works(state, base=100)
        _result, props = _budget_proposals(state)
        mb = props[0]["modified_budget"]
        for proposal in state.get_senate_proposals():
            for faction in state.get_active_factions():
                player = state.get_player_by_faction(faction.id)
                if player:
                    state.record_senate_vote(player.player_id, proposal["id"], True)
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        contract = state.get_contract(c.id)
        self.assertEqual(contract._approved_budget, mb)   # B 写入
        self.assertEqual(contract._original_budget, 100)  # A 冻结
        self.assertEqual(contract.status, ContractStatus.BUDGETED)  # status 持久态


# ---------------------------------------------------------------------------
# K-AC-12.3b（F-01 / FC-K-29）— admissible 域反例：畸形/越界 → fail-safe [0.05,0.20]
# ---------------------------------------------------------------------------
_BASE_100 = 100
_SAFE_BOUNDS = (0.05, 0.20)


@pytest.mark.parametrize("bad_margin", [
    [0.6, 0.8],            # 越界 >0.5
    [-0.5, -0.2],          # 越界 <0（base=1 时未 fail-safe 会跌破人类下界 1）
    [0.20, 0.05],          # 反序（min>max）
    [0.05],                # 非二元（过少）
    [0.05, 0.1, 0.2],      # 非二元（过多）
    [float("nan"), 0.2],   # 非有限（NaN）
    [0.05, float("inf")],  # 非有限（Inf）
    ["a", "b"],           # 非数值
    [None, 0.2],           # 非数值（None 元素）
    0.1,                   # 非序列（标量）
    [True, False],         # bool（int 子类，显式拒）
])
def test_k_ac_12_3b_failsafe_malformed_margin(bad_margin):
    """K-AC-12.3b：任一畸形/越界 margin ⇒ fail-safe [0.05,0.20]（与默认逐字一致）。

    断言：draw 界 == (0.05,0.20)；值 ∈ [105,120]（base=100）；提案仍 admitted（errors 空、已入 state）。
    """
    state = _build_state({"economic_rules": {
        "public_work_budget_margin_range": bad_margin}})
    _pending_works(state, base=_BASE_100)
    with patch('random.uniform', return_value=0.10) as mu:
        result, props = _budget_proposals(state)
    assert mu.call_args.args == _SAFE_BOUNDS, f"未 fail-safe: {bad_margin!r}"
    assert props[0]["modified_budget"] == 110
    assert result["errors"] == [], "fail-safe 后提案须仍 admitted（不崩溃/不 fail-closed）"
    assert [p for p in state.get_senate_proposals() if p.get("type") == "budget"]


def test_k_ac_12_3b_missing_key_failsafe():
    """K-AC-12.3b / FC-K-24：缺键 ⇒ fail-safe [0.05,0.20]（非回退 randint）。"""
    state = _build_state({})  # 无 public_work_budget_margin_range 键
    _pending_works(state, base=_BASE_100)
    with patch('random.uniform', return_value=0.10) as mu:
        result, props = _budget_proposals(state)
    assert mu.call_args.args == _SAFE_BOUNDS
    assert props[0]["modified_budget"] == 110
    assert result["errors"] == []


def test_k_ac_12_3b_admissible_values_used_verbatim():
    """K-AC-12.3b（对照）：域内值 [0,0.5] ⇒ 使用原值（不 fail-safe）。"""
    state = _build_state({"economic_rules": {
        "public_work_budget_margin_range": [0.0, 0.5]}})
    _pending_works(state, base=_BASE_100)
    with patch('random.uniform', return_value=0.5) as mu:
        _result, props = _budget_proposals(state)
    assert mu.call_args.args == (0.0, 0.5)
    assert props[0]["modified_budget"] == int(_BASE_100 * 1.5)  # 150，人类上界取等


if __name__ == "__main__":
    unittest.main()
