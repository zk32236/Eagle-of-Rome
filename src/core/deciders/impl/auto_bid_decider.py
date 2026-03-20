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
        construction = 5
        warranty = 10
        extra.update({
            "knight_id": knight.id,
            "knight_name": knight.name,
            "amount": amount,
            "rate": r,
            "construction": construction,
            "warranty": warranty,
            "result": "bid"
        })
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_works_bid: 工程合同 {contract.id} 骑士 {knight.name} 出价 {amount} 折扣 {r:.0%}",
            level=logging.DEBUG,
            extra=extra
        )
        return knight, amount, r, construction, warranty

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