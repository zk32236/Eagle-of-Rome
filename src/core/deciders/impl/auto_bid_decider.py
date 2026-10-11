# src/core/deciders/impl/auto_bid_decider.py
import random
import logging
from src.core.deciders.bid_decider import BidDecider
from src.core.entities.contract import Contract
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from typing import Optional, Tuple

class AutoBidDecider(BidDecider):
    def decide_tax_bid(self, contract, knights, state):
        extra = {
            "function": "decide_tax_bid",
            "decider": self.__class__.__name__,
            "contract_id": contract.id,
            "contract_name": contract.name,
            "base_cost": contract.base_cost,
            "knights_count": len(knights) if knights else 0
        }
        if not knights:
            extra["result"] = None
            extra["reason"] = "no_knights"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_tax_bid: 合同 {contract.id} 无骑士可用",
                level=logging.DEBUG,
                extra=extra
            )
            return None
        knight = random.choice(knights)
        # WP-K S2（OD-K-02 · F-2，FC-K-10/13/17）：tax 加价率 r 经 config 驱动
        # （键 tax_bid_increment_min/max，默认 0.05/0.20 = 现状字面量，零漂移）；
        # 缺键 → 回退现状字面量。单 draw 单用（加价，语义不变）。
        inc_min = state.get_economic_rule("tax_bid_increment_min", 0.05)
        inc_max = state.get_economic_rule("tax_bid_increment_max", 0.20)
        r = random.uniform(inc_min, inc_max)
        amount = int(contract.base_cost * (1 + r))
        extra.update({
            "knight_id": knight.id,
            "knight_name": knight.name,
            "amount": amount,
            "rate": r,
            "result": "bid"
        })
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_tax_bid: 合同 {contract.id} 骑士 {knight.name} 出价 {amount} 加价 {r:.0%}",
            level=logging.DEBUG,
            extra=extra
        )
        return knight, amount, r

    def decide_works_bid(self, contract, knights, state):
        state.log_event(
            f"AutoBidDecider: 合同 {contract.id} 预算 {contract.base_cost}",
            level=logging.DEBUG,
            extra={"contract_id": contract.id, "budget": contract.base_cost}
        )
        extra = {
            "function": "decide_works_bid",
            "decider": self.__class__.__name__,
            "contract_id": contract.id,
            "contract_name": contract.name,
            "base_cost": contract.base_cost,
            "knights_count": len(knights) if knights else 0
        }
        if not knights:
            extra["result"] = None
            extra["reason"] = "no_knights"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_works_bid: 工程合同 {contract.id} 无骑士可用",
                level=logging.DEBUG,
                extra=extra
            )
            return None
        knight = random.choice(knights)
        # WP-K S2 + S3（OD-K-02c，FC-K-10/12/13/18/19）：折扣读 project_bid_discount_min/max、
        # 利润率读 project_bid_profit_rate_min/max（默认 0.05/0.20 = 现状字面量）；
        # 两者为两次独立 draw（不复用 —— 旧单一 r 双驱动缺陷），折扣定中标额 C，利润率定实际成本 D。
        disc_min = state.get_economic_rule("project_bid_discount_min", 0.05)
        disc_max = state.get_economic_rule("project_bid_discount_max", 0.20)
        prof_min = state.get_economic_rule("project_bid_profit_rate_min", 0.05)
        prof_max = state.get_economic_rule("project_bid_profit_rate_max", 0.20)
        works_discount = random.uniform(disc_min, disc_max)
        amount = int(contract.base_cost * (1 - works_discount))

        # 获取原始基准成本（合同生成时的预算）
        original_budget = getattr(contract, '_original_budget', contract.base_cost)
        profit_rate = random.uniform(prof_min, prof_max)
        actual_cost = int(amount * (1 - profit_rate))
        cost_ratio = actual_cost / original_budget if original_budget > 0 else 1.0

        theoretical_construction = state.get_economic_rule("project_theoretical_construction", 3)
        theoretical_warranty = state.get_economic_rule("project_theoretical_warranty", 10)

        # 实际成本 = 中标金额 * (1 - profit_rate)
        actual_cost = int(amount * (1 - profit_rate))
        # 实际工期 = 理论工期 * (基准成本 / 实际成本)
        if actual_cost > 0:
            actual_construction = int(theoretical_construction * original_budget / actual_cost)
        else:

            actual_construction = theoretical_construction
        actual_construction = max(1, actual_construction)

        # 质保期基于成本比例计算
        actual_warranty = int(theoretical_warranty * cost_ratio)
        actual_warranty = max(0, actual_warranty)

        # 日志记录成本比例
        state.log_event(
            f"AutoBidDecider: 合同 {contract.id} 原始预算 {original_budget}，中标价 {amount}，实际成本 {actual_cost}，成本比例 {cost_ratio:.2f}，质保期 {actual_warranty}",
            level=logging.DEBUG
        )

        return knight, amount, profit_rate, actual_construction, actual_warranty

    def decide_fleet_bid(self, contract, knights, state):
        extra = {
            "function": "decide_fleet_bid",
            "decider": self.__class__.__name__,
            "contract_id": contract.id,
            "contract_name": contract.name,
            "knights_count": len(knights) if knights else 0
        }
        if not knights:
            extra["result"] = None
            extra["reason"] = "no_knights"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_fleet_bid: 舰队建造合同 {contract.id} 无骑士可用",
                level=logging.DEBUG,
                extra=extra
            )
            return None
        knight = random.choice(knights)
        # R3-G-03（§3.4，FROZEN）：bid ceiling = Senate B（approved_budget；legacy BUDGETED
        # fallback = base_cost，§3.2）；stale total_budget（A）不被读作 ceiling（R3-09）。
        approved_budget = contract.approved_budget
        if approved_budget is None:
            approved_budget = getattr(contract, "base_cost", 0) or 0
        # 两次独立 draw（R3-10）：bid_discount 定 C；profit_rate 第二次独立 uniform——不复用
        # bid_discount（旧单一 r 双驱动缺陷）。边际范围/整数截断/Eques 选择保持（R3-11 零重平衡）。
        # WP-K S2（FC-K-10/12/13）：折扣读 project_bid_discount_min/max、利润率读
        # project_bid_profit_rate_min/max（默认 0.05/0.20 = 现状字面量，零漂移）。
        disc_min = state.get_economic_rule("project_bid_discount_min", 0.05)
        disc_max = state.get_economic_rule("project_bid_discount_max", 0.20)
        prof_min = state.get_economic_rule("project_bid_profit_rate_min", 0.05)
        prof_max = state.get_economic_rule("project_bid_profit_rate_max", 0.20)
        bid_discount = random.uniform(disc_min, disc_max)
        amount = int(approved_budget * (1 - bid_discount))
        profit_rate = random.uniform(prof_min, prof_max)
        extra.update({
            "knight_id": knight.id,
            "knight_name": knight.name,
            "amount": amount,
            "rate": profit_rate,
            "discount": bid_discount,
            "approved_budget": approved_budget,
            "result": "bid"
        })
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_fleet_bid: 舰队合同 {contract.id} 骑士 {knight.name} "
            f"出价 {amount} 折扣 {bid_discount:.0%} 利润率 {profit_rate:.0%}（B={approved_budget}）",
            level=logging.DEBUG,
            extra=extra
        )
        return knight, amount, profit_rate