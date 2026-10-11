# src/tests/test_deciders/test_wpk_s2s3_bid_margins.py
"""WP-K S2（OD-K-02 · F-2）fleet/tax 竞价 config 接线 + S3（OD-K-02c）works 单 r 双驱动解耦（v1.4 对齐）。

设计来源（单一权威）：02-sa-design/SA-Development-Task-WP-K-v1.4-2026-10-11.md（FC-K-10…22；FC-K-30）。
覆盖 K-AC-09.*（fleet）、K-AC-10.*（tax）、K-AC-11.*（works）。

- S2 默认等价（零漂移）：fleet/tax 读 config，默认值 = 现状字面量（0.05/0.20）。
- S2 fallback：缺键 → 回退现状字面量。
- S3：works 折扣（定 C）与利润率（定 D）两次独立 draw（不复用）；返回第 3 项 = profit_rate。
- 证据路径二值（F-04）：S2 主证 = **PRODUCTION_CHAIN**（+SECC，见 `test_func_contracts` persisted 断言）；
  本文件 decider-level 断言为 PRODUCTION_CHAIN（真实 decider 入口，禁 mock-only closure）。
- **FC-K-30 域限定（F-07）**："zero-drift / byte-for-byte" = **同函数入口 RNG state 级**局部等价，
  **不**承诺 phase/game-seed 级输出恒等；S1（删 draw）/S3（加 draw）/S4（primitive 变）在**同 seed** 下
  会移位下游全局 RNG 序列 ⇒ 已登记 `GAME_RULE_CHANGE`（G7 可见）。S2 不改 draw 次数/顺序 ⇒ 不引入 shift。
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

from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.api import forum_api


def _state(rules=None):
    rules = rules or {}
    state = MagicMock()
    state.get_economic_rule = MagicMock(
        side_effect=lambda key, default=None: rules.get(key, default))
    state.log_event = MagicMock()
    return state


def _contract(base_cost=80, approved=80, cid=1):
    c = MagicMock(spec=Contract)
    c.id = cid
    c.name = f"C{cid}"
    c.base_cost = base_cost
    c._original_budget = base_cost
    c.approved_budget = approved
    return c


def _knights():
    k = MagicMock(spec=Figure)
    k.id = 10
    k.name = "Knight10"
    return [k]


def _uniform_arg_calls(mock):
    return [c.args for c in mock.call_args_list]


# ---------------------------------------------------------------------------
# S2 — fleet
# ---------------------------------------------------------------------------
class TestS2FleetConfig(unittest.TestCase):
    def test_fleet_default_bounds_are_legacy_literals(self):
        """K-AC-09.1（零漂移）：默认缺键 → 两次独立 draw 均 U(0.05,0.20)。"""
        state = _state()
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', return_value=0.12) as mu:
                result = AutoBidDecider().decide_fleet_bid(_contract(), _knights(), state)
        self.assertEqual(_uniform_arg_calls(mu), [(0.05, 0.20), (0.05, 0.20)])
        _k, amount, rate = result
        self.assertEqual(amount, int(80 * (1 - 0.12)))
        self.assertEqual(rate, 0.12)

    def test_fleet_config_drives_bounds(self):
        """K-AC-09.2（MOCK_AUXILIARY：mock state/contract 单元初筛；不独立关闭 AC）。
        主证 = `test_fleet_config_drives_bounds_persisted`（真实 state/decider/place_bid）。"""
        rules = {
            "project_bid_discount_min": 0.10, "project_bid_discount_max": 0.10,
            "project_bid_profit_rate_min": 0.30, "project_bid_profit_rate_max": 0.30,
        }
        state = _state(rules)
        with patch('random.choice', return_value=_knights()[0]):
            result = AutoBidDecider().decide_fleet_bid(_contract(), _knights(), state)
        _k, amount, rate = result
        self.assertEqual(amount, int(80 * (1 - 0.10)))   # 72
        self.assertEqual(rate, 0.30)

    def test_fleet_config_drives_bounds_persisted(self):
        """K-AC-09.2（PRODUCTION_CHAIN 主证）：非默认 config（discount 0.10 / profit 0.30）
        经**真实 GameState + 真实 AutoBidDecider** → **真实 `forum_api.place_bid`** →
        断言 persisted C（index3）/ D（index7）。

        非默认键经真实 config 路径被消费（min==max ⇒ draw 确定性，无需 patch uniform）。
        """
        economic = {
            "project_bid_discount_min": 0.10, "project_bid_discount_max": 0.10,
            "project_bid_profit_rate_min": 0.30, "project_bid_profit_rate_max": 0.30,
        }
        state, knight, contract = _real_state(
            ContractType.PUBLIC_WORKS, base=200, fleet=True, economic=economic)
        cur = AutoBidDecider().decide_fleet_bid(contract, [knight], state)
        self.assertIsNotNone(cur)
        _k, amount, rate = cur
        self.assertEqual(amount, int(200 * (1 - 0.10)))   # config 折扣驱动 C
        self.assertEqual(rate, 0.30)                       # config 利润率驱动
        bid = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, rate)
        self.assertTrue(bid["success"], bid.get("message"))
        row = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(row[3], amount)                        # C 持久
        self.assertEqual(row[7], int(amount * (1 - rate)))      # D 持久（commit-side）

    def test_fleet_fallback_missing_keys(self):
        """K-AC-09.3：缺键 → 回退现状字面量。"""
        state = _state({})
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', return_value=0.25) as mu:
                AutoBidDecider().decide_fleet_bid(_contract(), _knights(), state)
        self.assertEqual(_uniform_arg_calls(mu), [(0.05, 0.20), (0.05, 0.20)])


# ---------------------------------------------------------------------------
# S2 — tax
# ---------------------------------------------------------------------------
class TestS2TaxConfig(unittest.TestCase):
    def test_tax_default_bounds_are_legacy_literals(self):
        """K-AC-10.1（零漂移）：默认缺键 → 单 draw U(0.05,0.20)（加价）。"""
        state = _state()
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', return_value=0.10) as mu:
                result = AutoBidDecider().decide_tax_bid(_contract(base_cost=100), _knights(), state)
        self.assertEqual(_uniform_arg_calls(mu), [(0.05, 0.20)])
        _k, amount, r = result
        self.assertEqual(amount, int(100 * (1 + 0.10)))
        self.assertEqual(r, 0.10)

    def test_tax_config_drives_bounds(self):
        """K-AC-10.2（MOCK_AUXILIARY：mock state/contract 单元初筛；不独立关闭 AC）。
        主证 = `test_tax_config_drives_bounds_persisted`（真实 state/decider/place_bid）。"""
        state = _state({"tax_bid_increment_min": 0.5, "tax_bid_increment_max": 0.5})
        with patch('random.choice', return_value=_knights()[0]):
            result = AutoBidDecider().decide_tax_bid(_contract(base_cost=100), _knights(), state)
        _k, amount, r = result
        self.assertEqual(r, 0.5)
        self.assertEqual(amount, int(100 * (1 + 0.5)))

    def test_tax_config_drives_bounds_persisted(self):
        """K-AC-10.2（PRODUCTION_CHAIN 主证）：非默认 tax_bid_increment（0.5/0.5）
        经**真实 GameState + 真实 AutoBidDecider** → **真实 `forum_api.place_bid`** →
        断言 persisted C（index3）。
        """
        economic = {"tax_bid_increment_min": 0.5, "tax_bid_increment_max": 0.5}
        state, knight, contract = _real_state(ContractType.TAX_FARMING, base=80, economic=economic)
        cur = AutoBidDecider().decide_tax_bid(contract, [knight], state)
        self.assertIsNotNone(cur)
        _k, amount, r = cur
        self.assertEqual(r, 0.5)                          # config 加价率驱动
        self.assertEqual(amount, int(80 * (1 + 0.5)))     # 120
        bid = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, r)
        self.assertTrue(bid["success"], bid.get("message"))
        row = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(row[3], amount)                  # C 持久（commit-side）

    def test_tax_fallback_missing_keys(self):
        """K-AC-10.3：缺键 → 回退现状字面量。"""
        state = _state({})
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', return_value=0.2) as mu:
                AutoBidDecider().decide_tax_bid(_contract(base_cost=100), _knights(), state)
        self.assertEqual(_uniform_arg_calls(mu), [(0.05, 0.20)])


# ---------------------------------------------------------------------------
# S3 — works 解耦 + config 接线
# ---------------------------------------------------------------------------
class TestS3WorksDecoupling(unittest.TestCase):
    def test_works_default_bounds_legacy_two_independent(self):
        """K-AC-11.*（接线 + 解耦）：默认缺键 → 两次独立 draw 均 U(0.05,0.20)。"""
        state = _state()
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', return_value=0.15) as mu:
                result = AutoBidDecider().decide_works_bid(_contract(base_cost=200), _knights(), state)
        self.assertEqual(_uniform_arg_calls(mu), [(0.05, 0.20), (0.05, 0.20)])
        _k, amount, profit_rate, _c, _w = result
        self.assertEqual(amount, int(200 * (1 - 0.15)))
        self.assertEqual(profit_rate, 0.15)

    def test_works_config_drives_discount_and_profit(self):
        """K-AC-10.3（MOCK_AUXILIARY：mock state/contract 单元初筛；不独立关闭 AC）。
        主证 = `test_works_config_drives_discount_and_profit_persisted`（真实 state/decider/place_bid）。

        折扣读 project_bid_discount_*、利润率读 project_bid_profit_rate_*。
        """
        rules = {
            "project_bid_discount_min": 0.10, "project_bid_discount_max": 0.10,
            "project_bid_profit_rate_min": 0.30, "project_bid_profit_rate_max": 0.30,
        }
        state = _state(rules)
        with patch('random.choice', return_value=_knights()[0]):
            result = AutoBidDecider().decide_works_bid(_contract(base_cost=200), _knights(), state)
        _k, amount, profit_rate, _c, _w = result
        self.assertEqual(amount, int(200 * (1 - 0.10)))   # 180
        self.assertEqual(profit_rate, 0.30)

    def test_works_config_drives_discount_and_profit_persisted(self):
        """K-AC-10.3（PRODUCTION_CHAIN 主证）：非默认 config（discount 0.10 / profit 0.30）
        经**真实 GameState + 真实 AutoBidDecider（works）** → **真实 `forum_api.place_bid`** →
        断言 persisted C（index3）/ D（index7）。
        """
        economic = {
            "project_bid_discount_min": 0.10, "project_bid_discount_max": 0.10,
            "project_bid_profit_rate_min": 0.30, "project_bid_profit_rate_max": 0.30,
        }
        state, knight, contract = _real_state(ContractType.PUBLIC_WORKS, base=200, economic=economic)
        cur = AutoBidDecider().decide_works_bid(contract, [knight], state)
        self.assertIsNotNone(cur)
        _k, amount, profit_rate, _c, _w = cur
        self.assertEqual(amount, int(200 * (1 - 0.10)))   # config 折扣驱动 C
        self.assertEqual(profit_rate, 0.30)                # config 利润率驱动
        bid = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, profit_rate)
        self.assertTrue(bid["success"], bid.get("message"))
        row = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(row[3], amount)                              # C 持久
        self.assertEqual(row[7], int(amount * (1 - profit_rate)))     # D 持久（commit-side）

    def test_works_dvc_positive_independent_draws(self):
        """K-AC-11.1（DVC 正例）：d≠p ⇒ 折扣定 amount、利润率定第 3 项（不复用同一 r）。"""
        state = _state()
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', side_effect=[0.10, 0.30]) as mu:
                result = AutoBidDecider().decide_works_bid(_contract(base_cost=200), _knights(), state)
        self.assertEqual(len(mu.call_args_list), 2, "必须两次独立 draw")
        _k, amount, profit_rate, _c, _w = result
        self.assertEqual(amount, int(200 * (1 - 0.10)))     # 180
        self.assertEqual(profit_rate, 0.30)                  # 若复用单 r 则为 0.10 → 失败
        self.assertNotEqual(amount, int(200 * (1 - 0.30)))   # 折扣 ≠ 利润率

    def test_works_dvc_control_same_value_matches_single_r(self):
        """K-AC-11.*（DVC 对照）：d=p ⇒ 结果与单 r 公式一致（防碰巧）。"""
        state = _state()
        with patch('random.choice', return_value=_knights()[0]):
            with patch('random.uniform', side_effect=[0.15, 0.15]):
                result = AutoBidDecider().decide_works_bid(_contract(base_cost=200), _knights(), state)
        _k, amount, profit_rate, _c, _w = result
        self.assertEqual(amount, int(200 * (1 - 0.15)))
        self.assertEqual(profit_rate, 0.15)


# ---------------------------------------------------------------------------
# SECC（K-AC-09.1 fleet / K-AC-10.1 tax）— 同函数入口 RNG state 级 legacy-vs-current 比较
#   + 至少一侧 place_bid persisted C/D oracle（commit-side）
# ---------------------------------------------------------------------------
# 冻结 legacy oracle：WP-K S2 接线前（字面量 0.05/0.20）的 decider 公式逐字复现。
# 与 current 在**相同函数入口 RNG state** 下运行 ⇒ 默认 config 下输出应逐字相同（FC-K-11/17/30）。

def _legacy_fleet_bid(contract, knights):
    """WP-K 前 fleet 出价公式（字面量）冻结 oracle。"""
    knight = random.choice(knights)
    approved_budget = contract.approved_budget
    if approved_budget is None:
        approved_budget = getattr(contract, "base_cost", 0) or 0
    bid_discount = random.uniform(0.05, 0.20)
    amount = int(approved_budget * (1 - bid_discount))
    profit_rate = random.uniform(0.05, 0.20)
    return knight.id, amount, profit_rate


def _legacy_tax_bid(contract, knights):
    """WP-K 前 tax 出价公式（字面量）冻结 oracle。"""
    knight = random.choice(knights)
    r = random.uniform(0.05, 0.20)
    amount = int(contract.base_cost * (1 + r))
    return knight.id, amount, r


def _real_state(contract_type, base, fleet=False, economic=None):
    """真实 GameState（含派系/玩家/骑士/合同）——供 place_bid persisted oracle 使用。

    ``economic`` 可覆盖 economic_rules（如非默认参数变更键 
    ``project_bid_discount_*`` / ``project_bid_profit_rate_*`` / ``tax_bid_increment_*``）；
    默认仅 ``default_bid_profit_rate``。create_for_testing 直接替换 Config._config
    （不合并 DEFAULTS）——因此缺键 = 真实缺键 fallback，非默认键 = 真实非默认。
    """
    econ = {"default_bid_profit_rate": 0.2}
    if economic:
        econ.update(economic)
    state = GameState.create_for_testing({
        "economic_rules": econ,
        "testing": {"bypass_player_check": True},
    })
    state.turn = GameTurn(turn_number=1, year=-264)
    state._treasury = 500
    faction = Faction(id="populares", name="Populares", treasury=1000)
    state.add_faction(faction)
    player = Player("player1", "populares", PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player1")
    knight = Figure.create_eques(state.allocate_id(), None, age=30)
    knight.faction_id = "populares"
    state.add_member(knight)
    faction.member_ids.append(knight.id)
    contract = state.create_contract(contract_type, province_id=1, base_cost=base, current_turn=1)
    contract.status = ContractStatus.BUDGETED
    if fleet:
        contract._is_fleet_construction = True
    return state, knight, contract


class TestS2FleetSECC(unittest.TestCase):
    def test_fleet_secc_legacy_vs_current_same_entry_state(self):
        """K-AC-09.1 / §8.4 SECC：同函数入口 RNG state 下 legacy-vs-current 输出逐字比较。

        Ordinary（approved=80）+ Boundary（approved=350）：默认 config ⇒ 同 entry 零漂移。
        """
        state = _state()   # 缺键 → 默认字面量
        for approved in (80, 350):
            contract = _contract(base_cost=80, approved=approved)
            random.seed(20261011)
            entry = random.getstate()
            random.setstate(entry)
            legacy = _legacy_fleet_bid(contract, _knights())
            random.setstate(entry)
            cur = AutoBidDecider().decide_fleet_bid(contract, _knights(), state)
            self.assertIsNotNone(cur)
            self.assertEqual(legacy, (cur[0].id, cur[1], cur[2]),
                             f"approved={approved} 同 entry state 输出漂移")

    def test_fleet_secc_persisted_cd_oracle(self):
        """K-AC-09.1 SECC（commit-side oracle）：current fleet 输出经真实 place_bid 持久 C/D。

        同 entry RNG state 下 legacy-vs-current 比较后，以 current 输出经真实
        `forum_api.place_bid` 持久化为 8 元组；断言 C(index3)=amount、D(index7)=int(amount×(1-rate))。
        anti-self-confirmation：oracle 取 persisted enqueue result（非 decider 自返回值）。
        """
        state, knight, contract = _real_state(ContractType.PUBLIC_WORKS, base=200, fleet=True)
        random.seed(20261011)
        entry = random.getstate()
        random.setstate(entry)
        legacy = _legacy_fleet_bid(contract, [knight])
        random.setstate(entry)
        cur = AutoBidDecider().decide_fleet_bid(contract, [knight], state)
        self.assertIsNotNone(cur)
        self.assertEqual(legacy, (cur[0].id, cur[1], cur[2]))
        _k, amount, rate = cur
        bid = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, rate)
        self.assertTrue(bid["success"], bid.get("message"))
        row = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(row[3], amount)                      # C 持久
        self.assertEqual(row[7], int(amount * (1 - rate)))    # D 持久（commit-side）


class TestS2TaxSECC(unittest.TestCase):
    def test_tax_secc_legacy_vs_current_same_entry_state(self):
        """K-AC-10.1 / §8.4 SECC：同函数入口 RNG state 下 legacy-vs-current 输出逐字比较。"""
        state = _state()
        for base in (80, 100):
            contract = _contract(base_cost=base)
            random.seed(20261011)
            entry = random.getstate()
            random.setstate(entry)
            legacy = _legacy_tax_bid(contract, _knights())
            random.setstate(entry)
            cur = AutoBidDecider().decide_tax_bid(contract, _knights(), state)
            self.assertIsNotNone(cur)
            self.assertEqual(legacy, (cur[0].id, cur[1], cur[2]), msg=f"base={base}")

    def test_tax_secc_persisted_c_oracle(self):
        """K-AC-10.1 SECC（commit-side oracle）：current tax 输出经真实 place_bid 持久 C。

        tax 无 D（TAX_FARMING 7 元组）；断言 C(index3)=amount。
        """
        state, knight, contract = _real_state(ContractType.TAX_FARMING, base=80)
        random.seed(20261011)
        entry = random.getstate()
        random.setstate(entry)
        legacy = _legacy_tax_bid(contract, [knight])
        random.setstate(entry)
        cur = AutoBidDecider().decide_tax_bid(contract, [knight], state)
        self.assertIsNotNone(cur)
        self.assertEqual(legacy, (cur[0].id, cur[1], cur[2]))
        _k, amount, r = cur
        bid = forum_api.place_bid(state, "player1", knight.id, contract.id, amount, r)
        self.assertTrue(bid["success"], bid.get("message"))
        row = state.get_forum_pending()["contract_bids"][0]
        self.assertEqual(row[3], amount)   # C 持久


if __name__ == "__main__":
    unittest.main()
