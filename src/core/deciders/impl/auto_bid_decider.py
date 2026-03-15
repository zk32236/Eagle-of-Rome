#src/core/deciders/impl/
import random
import logging
from src.core.deciders.bid_decider import BidDecider
from src.core.entities.contract import Contract
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from typing import Optional, Tuple


class AutoBidDecider(BidDecider):
    """自动竞标决策器（基础版本）"""

    def decide_tax_bid(self, contract, knights, state):
        if not knights:
            return None
        # 随机选择一个骑士
        knight = random.choice(knights)
        # 随机加价 5%~20%
        r = random.uniform(0.05, 0.20)
        amount = int(contract.base_cost * (1 + r))
        # 移除财富检查：骑士无需垫资
        # if knight.wealth < amount:
        #     return None
        if state:
            state.log_event(
                f"AutoBidDecider: 包税合同 {contract.id} 骑士 {knight.name} 出价 {amount} 加价 {r:.0%}",
                level=logging.DEBUG,
                extra={"contract_id": contract.id, "knight_id": knight.id, "amount": amount, "rate": r}
            )
        return knight, amount, r

    def decide_works_bid(self, contract, knights, state):
        if not knights:
            return None
        knight = random.choice(knights)
        # 随机折扣 5%~20%
        r = random.uniform(0.05, 0.20)
        amount = int(contract.base_cost * (1 - r))
        # 移除财富检查
        # if knight.wealth < amount:
        #     return None
        # 简单工期/质保计算
        construction = 5  # 基础5年
        warranty = 10  # 基础10年
        if state:
            state.log_event(
                f"AutoBidDecider: 工程合同 {contract.id} 骑士 {knight.name} 出价 {amount} 折扣 {r:.0%}",
                level=logging.DEBUG,
                extra={"contract_id": contract.id, "knight_id": knight.id, "amount": amount, "rate": r}
            )
        return knight, amount, r, construction, warranty

    def decide_fleet_bid(self, contract, knights, state):
        if not knights:
            return None
        knight = random.choice(knights)
        r = random.uniform(0.05, 0.20)
        total_budget = getattr(contract, 'total_budget', contract.base_cost)
        amount = int(total_budget * (1 - r))
        # 移除财富检查
        # if knight.wealth < amount:
        #     return None
        if state:
            state.log_event(
                f"AutoBidDecider: 舰队合同 {contract.id} 骑士 {knight.name} 出价 {amount} 折扣 {r:.0%}",
                level=logging.DEBUG,
                extra={"contract_id": contract.id, "knight_id": knight.id, "amount": amount, "rate": r}
            )
        return knight, amount, r