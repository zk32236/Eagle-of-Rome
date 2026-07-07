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
        r = random.uniform(0.05, 0.20)
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
        r = random.uniform(0.05, 0.20)
        amount = int(contract.base_cost * (1 - r))

        # 获取原始基准成本（合同生成时的预算）
        original_budget = getattr(contract, '_original_budget', contract.base_cost)
        actual_cost = int(amount * (1 - r))
        cost_ratio = actual_cost / original_budget if original_budget > 0 else 1.0

        theoretical_construction = state.get_economic_rule("project_theoretical_construction", 3)
        theoretical_warranty = state.get_economic_rule("project_theoretical_warranty", 10)

        # 实际成本 = 中标金额 * (1 - r)
        actual_cost = int(amount * (1 - r))
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

        return knight, amount, r, actual_construction, actual_warranty

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
        total_budget = getattr(contract, 'total_budget', contract.base_cost)
        r = random.uniform(0.05, 0.20)
        amount = int(total_budget * (1 - r))
        extra.update({
            "knight_id": knight.id,
            "knight_name": knight.name,
            "amount": amount,
            "rate": r,
            "result": "bid"
        })
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_fleet_bid: 舰队合同 {contract.id} 骑士 {knight.name} 出价 {amount} 折扣 {r:.0%}",
            level=logging.DEBUG,
            extra=extra
        )
        return knight, amount, r