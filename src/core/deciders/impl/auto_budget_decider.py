import random
from typing import List
from src.core.deciders.budget_decider import BudgetDecider
from src.core.entities.contract import Contract
from src.core.game_state import GameState

class AutoBudgetDecider(BudgetDecider):
    """自动预算决策器：随机选取部分合同，随机表决"""

    def decide_proposals(self, pending_contracts: List[Contract], state: GameState) -> List[Contract]:
        if not pending_contracts:
            return []
        # 随机选择 1 到所有合同数之间的数量
        num = random.randint(1, len(pending_contracts))
        return random.sample(pending_contracts, num)

    def decide_vote(self, contract: Contract, state: GameState) -> bool:
        # 简单随机：50% 通过
        return random.random() < 0.5